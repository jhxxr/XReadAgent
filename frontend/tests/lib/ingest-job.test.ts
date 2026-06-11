// SPDX-License-Identifier: AGPL-3.0-or-later
import { beforeEach, describe, expect, it, vi } from "vitest";

import { runIngestJob } from "@/lib/ingest-job";

const { buildJobEventsWsUrl, postIngest } = vi.hoisted(() => ({
  buildJobEventsWsUrl: vi.fn((jobId: string) => `ws://sidecar/ws/jobs/${jobId}`),
  postIngest: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ buildJobEventsWsUrl, postIngest }));

interface MockSocket {
  url: string;
  close: ReturnType<typeof vi.fn>;
  emit: (data: unknown) => void;
  emitRaw: (data: string) => void;
  emitError: () => void;
  emitClose: () => void;
}

function makeWebSocketFactory(): { factory: (url: string) => WebSocket; sockets: MockSocket[] } {
  const sockets: MockSocket[] = [];
  const factory = (url: string): WebSocket => {
    const listeners: Record<string, ((arg: unknown) => void)[]> = {};
    const ws = {
      url,
      readyState: 1,
      addEventListener: (event: string, listener: (arg: unknown) => void): void => {
        listeners[event] = [...(listeners[event] ?? []), listener];
      },
      close: vi.fn(),
    };
    const dispatch = (event: string, arg: unknown) => {
      for (const fn of listeners[event] ?? []) fn(arg);
    };
    sockets.push({
      url,
      close: ws.close,
      emit: (data: unknown) => {
        dispatch("message", { data: JSON.stringify(data) });
      },
      emitRaw: (data: string) => {
        dispatch("message", { data });
      },
      emitError: () => {
        dispatch("error", new Event("error"));
      },
      emitClose: () => {
        dispatch("close", new Event("close"));
      },
    });
    return ws as unknown as WebSocket;
  };
  return { factory, sockets };
}

const finishEvent = {
  type: "finish",
  slug: "alpha-aaaaaaaaaaaa",
  title: "Alpha Paper",
  cache_hit: false,
  files_touched: ["wiki/papers/alpha-aaaaaaaaaaaa.md"],
  duration_s: 12.5,
  ts: "2026-06-11T00:00:00Z",
} as const;

describe("runIngestJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    postIngest.mockResolvedValue({ jobId: "job-1" });
  });

  it("posts /ingest, subscribes the job WS, reports stages, and resolves on finish", async () => {
    const { factory, sockets } = makeWebSocketFactory();
    const onStage = vi.fn();

    const promise = runIngestJob(
      { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
      { onStage, websocketFactory: factory },
    );

    await vi.waitFor(() => {
      expect(sockets.length).toBe(1);
    });
    const socket = sockets[0]!;
    expect(postIngest).toHaveBeenCalledWith({
      workspacePath: "/tmp/ws",
      filePath: "/tmp/paper.pdf",
    });
    expect(socket.url).toBe("ws://sidecar/ws/jobs/job-1");

    socket.emit({ type: "stage_start", stage: "converting", ts: "t1" });
    socket.emit({ type: "stage_end", stage: "converting", ts: "t2" });
    socket.emit({ type: "stage_start", stage: "analyzing", ts: "t3" });
    socket.emit(finishEvent);

    await expect(promise).resolves.toEqual(finishEvent);
    expect(onStage.mock.calls.map(([stage]) => stage as string)).toEqual([
      "converting",
      "analyzing",
    ]);
    expect(socket.close).toHaveBeenCalled();
  });

  it("rejects with the backend message on an error event", async () => {
    const { factory, sockets } = makeWebSocketFactory();
    const promise = runIngestJob(
      { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
      { websocketFactory: factory },
    );
    await vi.waitFor(() => {
      expect(sockets.length).toBe(1);
    });

    sockets[0]!.emit({
      type: "error",
      stage: "converting",
      message: "MinerU exploded",
      traceback_excerpt: null,
      ts: "t1",
    });

    await expect(promise).rejects.toThrow("MinerU exploded");
  });

  it("rejects when the POST fails without opening a socket", async () => {
    postIngest.mockRejectedValue(new Error("Sidecar returned 422 on /ingest"));
    const { factory, sockets } = makeWebSocketFactory();

    await expect(
      runIngestJob(
        { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
        { websocketFactory: factory },
      ),
    ).rejects.toThrow(/422/);
    expect(sockets.length).toBe(0);
  });

  it("rejects on a socket error", async () => {
    const { factory, sockets } = makeWebSocketFactory();
    const promise = runIngestJob(
      { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
      { websocketFactory: factory },
    );
    await vi.waitFor(() => {
      expect(sockets.length).toBe(1);
    });

    sockets[0]!.emitError();

    await expect(promise).rejects.toThrow(/lost connection/i);
  });

  it("rejects when the stream closes before a terminal event", async () => {
    const { factory, sockets } = makeWebSocketFactory();
    const promise = runIngestJob(
      { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
      { websocketFactory: factory },
    );
    await vi.waitFor(() => {
      expect(sockets.length).toBe(1);
    });

    sockets[0]!.emit({ type: "stage_start", stage: "converting", ts: "t1" });
    sockets[0]!.emitClose();

    await expect(promise).rejects.toThrow(/closed before the job finished/i);
  });

  it("ignores malformed frames and still resolves on finish", async () => {
    const { factory, sockets } = makeWebSocketFactory();
    const promise = runIngestJob(
      { workspacePath: "/tmp/ws", filePath: "/tmp/paper.pdf" },
      { websocketFactory: factory },
    );
    await vi.waitFor(() => {
      expect(sockets.length).toBe(1);
    });

    sockets[0]!.emitRaw("not json at all");
    sockets[0]!.emit(finishEvent);

    await expect(promise).resolves.toEqual(finishEvent);
  });
});
