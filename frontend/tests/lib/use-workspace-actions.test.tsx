// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceActions } from "@/lib/use-workspace-actions";
import { writeWorkspacePath } from "@/lib/workspace";

const { postIngest, toast } = vi.hoisted(() => ({
  postIngest: vi.fn(),
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({ postIngest }));
vi.mock("sonner", () => ({ toast }));

const getPathForFile = vi.fn();

function installElectronApi() {
  (window as unknown as { electronAPI: unknown }).electronAPI = { getPathForFile };
}

function removeElectronApi() {
  delete (window as unknown as { electronAPI?: unknown }).electronAPI;
}

function makeFile(name: string): File {
  return new File(["content"], name, { type: "application/octet-stream" });
}

function renderActions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useWorkspaceActions(), { wrapper });
}

/** Two independent hook instances sharing one QueryClient (mirrors the real
 * UI: the workspace header and the empty state each call the hook). */
function renderTwoActionInstances() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => ({ a: useWorkspaceActions(), b: useWorkspaceActions() }), { wrapper });
}

describe("useWorkspaceActions.importDroppedFiles", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    writeWorkspacePath("/tmp/ws");
    installElectronApi();
    getPathForFile.mockReturnValue("C:\\papers\\paper.pdf");
    postIngest.mockResolvedValue({
      slug: "paper",
      title: "Paper",
      cacheHit: false,
      filesTouched: [],
      durationS: 1,
    });
  });

  afterEach(() => {
    removeElectronApi();
  });

  it("ingests a dropped PDF through the same path-based API as the picker flow", async () => {
    const { result } = renderActions();
    const file = makeFile("paper.pdf");

    await act(async () => {
      await result.current.importDroppedFiles([file]);
    });

    expect(getPathForFile).toHaveBeenCalledWith(file);
    await waitFor(() => {
      expect(postIngest).toHaveBeenCalledWith({
        workspacePath: "/tmp/ws",
        filePath: "C:\\papers\\paper.pdf",
      });
    });
  });

  it("rejects unsupported file types with a toast and no ingest call", async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.importDroppedFiles([makeFile("malware.exe")]);
    });

    expect(toast.error).toHaveBeenCalledWith("Unsupported file type", expect.anything());
    expect(postIngest).not.toHaveBeenCalled();
  });

  it("imports only the first supported file when several are dropped", async () => {
    const { result } = renderActions();
    const first = makeFile("first.pdf");
    const second = makeFile("second.docx");

    await act(async () => {
      await result.current.importDroppedFiles([first, second]);
    });

    expect(getPathForFile).toHaveBeenCalledTimes(1);
    expect(getPathForFile).toHaveBeenCalledWith(first);
    expect(toast.info).toHaveBeenCalled();
    await waitFor(() => {
      expect(postIngest).toHaveBeenCalledTimes(1);
    });
  });

  it("skips unsupported leading files and imports the first supported one", async () => {
    const { result } = renderActions();
    const unsupported = makeFile("notes.exe");
    const supported = makeFile("paper.pdf");

    await act(async () => {
      await result.current.importDroppedFiles([unsupported, supported]);
    });

    expect(getPathForFile).toHaveBeenCalledWith(supported);
  });

  it("shows a desktop-only error in browser mode", async () => {
    removeElectronApi();
    const { result } = renderActions();

    await act(async () => {
      await result.current.importDroppedFiles([makeFile("paper.pdf")]);
    });

    expect(toast.error).toHaveBeenCalledWith("Import is only available in the desktop app");
    expect(postIngest).not.toHaveBeenCalled();
  });

  it("surfaces an error when the file path cannot be resolved", async () => {
    getPathForFile.mockReturnValue("");
    const { result } = renderActions();

    await act(async () => {
      await result.current.importDroppedFiles([makeFile("paper.pdf")]);
    });

    expect(toast.error).toHaveBeenCalledWith("Import failed", expect.anything());
    expect(postIngest).not.toHaveBeenCalled();
  });

  it("blocks a second drop while an import is already running", async () => {
    postIngest.mockReturnValue(new Promise(() => undefined));
    const { result } = renderActions();

    await act(async () => {
      await result.current.importDroppedFiles([makeFile("first.pdf")]);
    });
    await waitFor(() => {
      expect(result.current.isImporting).toBe(true);
    });

    await act(async () => {
      await result.current.importDroppedFiles([makeFile("second.pdf")]);
    });

    expect(toast.error).toHaveBeenCalledWith("Import already in progress", expect.anything());
    expect(postIngest).toHaveBeenCalledTimes(1);
  });

  it("blocks a drop while an import started by ANOTHER hook instance is running", async () => {
    postIngest.mockReturnValue(new Promise(() => undefined));
    const { result } = renderTwoActionInstances();

    await act(async () => {
      await result.current.a.importDroppedFiles([makeFile("first.pdf")]);
    });
    // Both instances must report the shared in-flight import.
    await waitFor(() => {
      expect(result.current.b.isImporting).toBe(true);
    });

    await act(async () => {
      await result.current.b.importDroppedFiles([makeFile("second.pdf")]);
    });

    expect(toast.error).toHaveBeenCalledWith("Import already in progress", expect.anything());
    expect(postIngest).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the drop contains no files", async () => {
    const { result } = renderActions();

    await act(async () => {
      await result.current.importDroppedFiles([]);
    });

    expect(postIngest).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
