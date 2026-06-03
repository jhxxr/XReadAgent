// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { postIngest } from "@/lib/api";
import { getElectronAPI, isElectron } from "@/lib/platform";
import { useWorkspacePath, writeWorkspacePath } from "@/lib/workspace";

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

interface IngestArgs {
  filePath: string;
  workspacePath: string;
}

export function useWorkspaceActions() {
  const queryClient = useQueryClient();
  const workspacePath = useWorkspacePath();

  const ingestMutation = useMutation({
    mutationFn: ({ filePath, workspacePath }: IngestArgs) => postIngest({ workspacePath, filePath }),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["papers"] });
      void queryClient.invalidateQueries({ queryKey: ["concepts"] });
      void queryClient.invalidateQueries({ queryKey: ["queries"] });
      toast.success(`Imported ${result.title}`);
    },
    onError: (error) => {
      toast.error("Import failed", { description: describeError(error) });
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

  return {
    importDocument,
    isImporting: ingestMutation.isPending,
    selectWorkspace,
    workspacePath,
  };
}
