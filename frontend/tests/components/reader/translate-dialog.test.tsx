// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TranslateDialog } from "@/components/reader/translate-dialog";

interface MockSocket {
  url: string;
  emit: (data: unknown) => Promise<void>;
  emitError: () => Promise<void>;
  close: () => void;
}

function makeWebSocketFactory(): {
  factory: (url: string) => WebSocket;
  sockets: MockSocket[];
} {
  const sockets: MockSocket[] = [];
  const factory = (url: string): WebSocket => {
    const listeners: Record<string, ((arg: unknown) => void)[]> = {};
    const ws = {
      url,
      readyState: 1,
      addEventListener: (
        event: string,
        listener: (arg: unknown) => void,
      ): void => {
        listeners[event] = [...(listeners[event] ?? []), listener];
      },
      close: vi.fn(),
    };
    const handle: MockSocket = {
      url,
      emit: (data: unknown) =>
        act(async () => {
          const list = listeners.message ?? [];
          for (const fn of list) {
            fn({ data: JSON.stringify(data) });
          }
          await Promise.resolve();
        }),
      emitError: () =>
        act(async () => {
          const list = listeners.error ?? [];
          for (const fn of list) {
            fn(new Event("error"));
          }
          await Promise.resolve();
        }),
      close: () => {
        ws.close();
      },
    };
    sockets.push(handle);
    return ws as unknown as WebSocket;
  };
  return { factory, sockets };
}

describe("TranslateDialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts /translate, subscribes WS, and reports finish", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ jobId: "job-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { factory, sockets } = makeWebSocketFactory();
    const onFinish = vi.fn();
    const user = userEvent.setup();

    render(
      <TranslateDialog
        open
        onOpenChange={() => undefined}
        workspacePath="/tmp/ws"
        sourcePath="/tmp/ws/raw/alpha.pdf"
        onFinish={onFinish}
        websocketFactory={factory}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^translate$/i }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
    const call = fetchSpy.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/translate$/);
    expect(init?.method).toBe("POST");

    await waitFor(() => {
      expect(sockets.length).toBe(1);
    });
    const socket = sockets[0]!;
    expect(socket.url).toMatch(/\/ws\/jobs\/job-1$/);

    // Engine download events render the overlay.
    await socket.emit({
      type: "model_download_start",
      asset: "doclayout-yolo.onnx",
      bytes_downloaded: 0,
      bytes_total: 50_000_000,
      ts: "2026-05-25T00:00:00Z",
    });
    expect(await screen.findByText(/preparing translation engine/i)).toBeInTheDocument();
    await socket.emit({
      type: "model_download_done",
      asset: "doclayout-yolo.onnx",
      bytes_downloaded: 50_000_000,
      bytes_total: 50_000_000,
      ts: "2026-05-25T00:00:01Z",
    });

    // Stage events advance the checklist.
    await socket.emit({
      type: "stage_start",
      stage: "parsing",
      page: null,
      percent: 0,
      payload: {},
      ts: "2026-05-25T00:00:02Z",
    });
    await socket.emit({
      type: "stage_end",
      stage: "parsing",
      page: null,
      percent: 25,
      payload: {},
      ts: "2026-05-25T00:00:03Z",
    });
    await waitFor(() => {
      const parsing = document.querySelector("li[data-stage='parsing']");
      expect(parsing?.getAttribute("data-status")).toBe("done");
    });

    // Finish event triggers the callback and the success banner.
    await socket.emit({
      type: "finish",
      mono_path: "translations/alpha.mono.pdf",
      dual_path: "translations/alpha.dual.pdf",
      duration_s: 12.5,
      cached: false,
      ts: "2026-05-25T00:00:10Z",
    });
    await waitFor(() => {
      expect(onFinish).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText(/translation complete/i)).toBeInTheDocument();
  });

  it("renders error events from the WS stream", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ jobId: "job-2" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const { factory, sockets } = makeWebSocketFactory();
    const user = userEvent.setup();

    render(
      <TranslateDialog
        open
        onOpenChange={() => undefined}
        workspacePath="/tmp/ws"
        sourcePath="/tmp/ws/raw/alpha.pdf"
        websocketFactory={factory}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^translate$/i }));
    await waitFor(() => {
      expect(sockets.length).toBe(1);
    });
    const socket = sockets[0]!;
    await socket.emit({
      type: "error",
      stage: "translation",
      message: "BabelDOC blew up",
      traceback_excerpt: null,
      ts: "2026-05-25T00:00:05Z",
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/BabelDOC blew up/);
  });

  it("surfaces a POST error without opening a socket", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("nope", { status: 422 }),
    );
    const { factory, sockets } = makeWebSocketFactory();
    const user = userEvent.setup();

    render(
      <TranslateDialog
        open
        onOpenChange={() => undefined}
        workspacePath="/tmp/ws"
        sourcePath="/tmp/ws/raw/alpha.pdf"
        websocketFactory={factory}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^translate$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/422/);
    expect(sockets.length).toBe(0);
  });
});
