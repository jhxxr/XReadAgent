// SPDX-License-Identifier: AGPL-3.0-or-later
import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { runIngestJob } from "@/lib/ingest-job";
import { getElectronAPI, isElectron } from "@/lib/platform";
import { useWorkspacePath, writeWorkspacePath } from "@/lib/workspace";
import type { IngestStageName } from "@/types/api";

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

/**
 * File suffixes accepted for drag-and-drop import. Mirrors the filter list of
 * the native open-file dialog (`show-open-file-dialog` in electron/src/main.ts)
 * so both import paths accept the same document types.
 */
const SUPPORTED_IMPORT_SUFFIXES = [".pdf", ".docx", ".html", ".htm", ".md", ".txt"] as const;

function isSupportedDocument(file: File): boolean {
  const name = file.name.toLowerCase();
  return SUPPORTED_IMPORT_SUFFIXES.some((suffix) => name.endsWith(suffix));
}

interface IngestArgs {
  filePath: string;
  workspacePath: string;
}

/**
 * Shared mutation key so the in-flight guard and `isImporting` see ingests
 * started by ANY `useWorkspaceActions` instance (the workspace header, the
 * empty state, and the drop zone each render their own instance). The
 * mutation stays pending for the WHOLE background job (POST + WS stream),
 * so "busy" means "job in flight", not just "request in flight".
 */
const INGEST_MUTATION_KEY = ["ingest"] as const;

/**
 * Stable toast id: the loading toast is updated in place as the job reports
 * phases, then replaced by the success / error toast. Only one ingest can
 * run at a time (see the in-flight guard), so a single id is enough.
 */
const INGEST_TOAST_ID = "ingest-progress";

const INGEST_STAGE_LABEL: Record<IngestStageName, string> = {
  converting: "Converting the document to markdown…",
  analyzing: "Analyzing the paper with the model…",
  writing: "Writing wiki pages…",
};

export function useWorkspaceActions() {
  const queryClient = useQueryClient();
  const workspacePath = useWorkspacePath();
  const ingestsInFlight = useIsMutating({ mutationKey: INGEST_MUTATION_KEY });

  const ingestMutation = useMutation({
    mutationKey: INGEST_MUTATION_KEY,
    mutationFn: ({ filePath, workspacePath }: IngestArgs) => {
      toast.loading("Importing document", {
        id: INGEST_TOAST_ID,
        description: "Starting the import job…",
      });
      return runIngestJob(
        { workspacePath, filePath },
        {
          onStage: (stage) => {
            toast.loading("Importing document", {
              id: INGEST_TOAST_ID,
              description: INGEST_STAGE_LABEL[stage],
            });
          },
        },
      );
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["papers"] });
      void queryClient.invalidateQueries({ queryKey: ["concepts"] });
      void queryClient.invalidateQueries({ queryKey: ["queries"] });
      toast.success(`Imported ${result.title}`, {
        id: INGEST_TOAST_ID,
        description: result.cache_hit
          ? "Already in the wiki — nothing changed."
          : undefined,
      });
    },
    onError: (error) => {
      toast.error("Import failed", {
        id: INGEST_TOAST_ID,
        description: describeError(error),
      });
    },
  });

  const pickWorkspace = async (): Promise<string | null> => {
    if (!isElectron()) {
      toast.error("Workspace picker is only available in the desktop app");
      return null;
    }

    const api = getElectronAPI();
    if (!api) return null;
    const selectedPaths = await api.showOpenFolderDialog("Open Workspace");
    const selectedPath = selectedPaths[0];
    if (!selectedPath) return null;
    writeWorkspacePath(selectedPath);
    return selectedPath;
  };

  const selectWorkspace = async () => {
    const selectedPath = await pickWorkspace();
    if (!selectedPath) return;
    toast.success("Workspace opened");
  };

  const importDocument = async () => {
    const targetWorkspacePath = workspacePath || (await pickWorkspace());
    if (!targetWorkspacePath) {
      return;
    }

    if (!isElectron()) {
      toast.error("Import is only available in the desktop app");
      return;
    }

    const api = getElectronAPI();
    if (!api) return;
    const selectedPaths = await api.showOpenFileDialog("Import Paper");
    const selectedPath = selectedPaths[0];
    if (!selectedPath) return;
    ingestMutation.mutate({ workspacePath: targetWorkspacePath, filePath: selectedPath });
  };

  /**
   * Import documents dropped onto the window. Reuses the same path-based
   * ingest mutation as the file-picker flow — the dropped `File` objects are
   * resolved to absolute paths via the Electron preload bridge.
   *
   * The ingest API handles one document per request, so only the first
   * supported file is imported; extra files are reported via toast.
   */
  const importDroppedFiles = async (files: readonly File[]) => {
    if (files.length === 0) return;

    // Imperative cross-instance check: `ingestMutation.isPending` is a
    // per-render, per-instance snapshot and would miss an import started from
    // another component (e.g. the empty-state button) or in the same tick.
    if (queryClient.isMutating({ mutationKey: INGEST_MUTATION_KEY }) > 0) {
      toast.error("Import already in progress", {
        description: "Wait for the current import to finish before dropping another document.",
      });
      return;
    }

    if (!isElectron()) {
      toast.error("Import is only available in the desktop app");
      return;
    }

    const supported = files.filter(isSupportedDocument);
    const firstSupported = supported[0];
    if (!firstSupported) {
      toast.error("Unsupported file type", {
        description: `Supported documents: ${SUPPORTED_IMPORT_SUFFIXES.join(", ")}`,
      });
      return;
    }

    const targetWorkspacePath = workspacePath || (await pickWorkspace());
    if (!targetWorkspacePath) {
      return;
    }

    const api = getElectronAPI();
    if (!api) return;
    const filePath = api.getPathForFile(firstSupported);
    if (!filePath) {
      toast.error("Import failed", {
        description: `Could not resolve a filesystem path for ${firstSupported.name}.`,
      });
      return;
    }

    if (files.length > 1) {
      toast.info(`Importing ${firstSupported.name}`, {
        description: "Documents are imported one at a time; drop the others again afterwards.",
      });
    }
    ingestMutation.mutate({ workspacePath: targetWorkspacePath, filePath });
  };

  return {
    importDocument,
    importDroppedFiles,
    isImporting: ingestsInFlight > 0,
    selectWorkspace,
    workspacePath,
  };
}
