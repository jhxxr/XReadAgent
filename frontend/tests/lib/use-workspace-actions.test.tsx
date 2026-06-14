// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspaceActions } from "@/lib/use-workspace-actions";
import { writeWorkspacePath } from "@/lib/workspace";
import type { IngestFinishEvent, IngestStageName } from "@/types/api";

const { runIngestJob, toast } = vi.hoisted(() => ({
  runIngestJob: vi.fn(),
  toast: {
    error: vi.fn(),
    info: vi.fn(),
    loading: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/lib/ingest-job", () => ({ runIngestJob }));
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

function makeFinishEvent(): IngestFinishEvent {
  return {
    type: "finish",
    slug: "paper",
    title: "Paper",
    cache_hit: false,
    files_touched: [],
    duration_s: 1,
    ts: "2026-06-11T00:00:00Z",
  };
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

async function triggerDrop(importDroppedFiles: (files: readonly File[]) => void, files: readonly File[]) {
  await act(async () => {
    importDroppedFiles(files);
    await Promise.resolve();
  });
}

describe("useWorkspaceActions.importDroppedFiles", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    writeWorkspacePath("/tmp/ws");
    installElectronApi();
    getPathForFile.mockReturnValue("C:\\papers\\paper.pdf");
    runIngestJob.mockResolvedValue(makeFinishEvent());
  });

  afterEach(() => {
    removeElectronApi();
  });

  it("starts an ingest job for a dropped PDF through the same path-based flow as the picker", async () => {
    const { result } = renderActions();
    const file = makeFile("paper.pdf");

    await triggerDrop(result.current.importDroppedFiles, [file]);

    expect(getPathForFile).toHaveBeenCalledWith(file);
    await waitFor(() => {
      expect(runIngestJob).toHaveBeenCalledWith(
        {
          workspacePath: "/tmp/ws",
          filePath: "C:\\papers\\paper.pdf",
        },
        expect.objectContaining({ onStage: expect.any(Function) as unknown }),
      );
    });
  });

  it("shows job phase progress through the loading toast and success on finish", async () => {
    runIngestJob.mockImplementation(
      (_req: unknown, opts: { onStage?: (stage: IngestStageName) => void }) => {
        opts.onStage?.("converting");
        opts.onStage?.("writing");
        return Promise.resolve(makeFinishEvent());
      },
    );
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("paper.pdf")]);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Imported Paper",
        expect.objectContaining({ id: "ingest-progress" }),
      );
    });
    expect(toast.loading).toHaveBeenCalledWith(
      "Importing document",
      expect.objectContaining({ description: expect.stringMatching(/converting/i) as string }),
    );
    expect(toast.loading).toHaveBeenCalledWith(
      "Importing document",
      expect.objectContaining({ description: expect.stringMatching(/writing wiki pages/i) as string }),
    );
  });

  it("surfaces a job failure through the error toast", async () => {
    runIngestJob.mockRejectedValue(new Error("MarkItDown blew up"));
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("paper.pdf")]);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Import failed",
        expect.objectContaining({ description: "MarkItDown blew up" }),
      );
    });
  });

  it("rejects unsupported file types with a toast and no ingest call", async () => {
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("malware.exe")]);

    expect(toast.error).toHaveBeenCalledWith("Unsupported file type", expect.anything());
    expect(runIngestJob).not.toHaveBeenCalled();
  });

  it("imports only the first supported file when several are dropped", async () => {
    const { result } = renderActions();
    const first = makeFile("first.pdf");
    const second = makeFile("second.docx");

    await triggerDrop(result.current.importDroppedFiles, [first, second]);

    expect(getPathForFile).toHaveBeenCalledTimes(1);
    expect(getPathForFile).toHaveBeenCalledWith(first);
    expect(toast.info).toHaveBeenCalled();
    await waitFor(() => {
      expect(runIngestJob).toHaveBeenCalledTimes(1);
    });
  });

  it("skips unsupported leading files and imports the first supported one", async () => {
    const { result } = renderActions();
    const unsupported = makeFile("notes.exe");
    const supported = makeFile("paper.pdf");

    await triggerDrop(result.current.importDroppedFiles, [unsupported, supported]);

    expect(getPathForFile).toHaveBeenCalledWith(supported);
  });

  it("shows a desktop-only error in browser mode", async () => {
    removeElectronApi();
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("paper.pdf")]);

    expect(toast.error).toHaveBeenCalledWith("Import is only available in the desktop app");
    expect(runIngestJob).not.toHaveBeenCalled();
  });

  it("surfaces an error when the file path cannot be resolved", async () => {
    getPathForFile.mockReturnValue("");
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("paper.pdf")]);

    expect(toast.error).toHaveBeenCalledWith("Import failed", expect.anything());
    expect(runIngestJob).not.toHaveBeenCalled();
  });

  it("blocks a second drop while an import job is already running", async () => {
    runIngestJob.mockReturnValue(new Promise(() => undefined));
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, [makeFile("first.pdf")]);
    await waitFor(() => {
      expect(result.current.isImporting).toBe(true);
    });

    await triggerDrop(result.current.importDroppedFiles, [makeFile("second.pdf")]);

    expect(toast.error).toHaveBeenCalledWith("Import already in progress", expect.anything());
    expect(runIngestJob).toHaveBeenCalledTimes(1);
  });

  it("blocks a drop while a job started by ANOTHER hook instance is running", async () => {
    runIngestJob.mockReturnValue(new Promise(() => undefined));
    const { result } = renderTwoActionInstances();

    await triggerDrop(result.current.a.importDroppedFiles, [makeFile("first.pdf")]);
    // Both instances must report the shared in-flight import.
    await waitFor(() => {
      expect(result.current.b.isImporting).toBe(true);
    });

    await triggerDrop(result.current.b.importDroppedFiles, [makeFile("second.pdf")]);

    expect(toast.error).toHaveBeenCalledWith("Import already in progress", expect.anything());
    expect(runIngestJob).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the drop contains no files", async () => {
    const { result } = renderActions();

    await triggerDrop(result.current.importDroppedFiles, []);

    expect(runIngestJob).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
