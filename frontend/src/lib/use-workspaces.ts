// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Managed-workspace actions for the renderer.
 *
 * Workspaces live under the app-managed data directory (`<userData>/workspaces`)
 * and are tracked by the Electron registry (see `electron/src/workspaces.ts`).
 * Creation is a two-step orchestration that this hook owns:
 *
 *   1. Electron allocates a slugged directory + registry entry.
 *   2. The backend seeds the canonical wiki layout into that directory.
 *
 * If step 2 fails we roll back step 1 so a half-created workspace never lingers
 * in the switcher. The active workspace path is still stored via
 * `lib/workspace` (localStorage) so the rest of the app keeps working unchanged.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { createWorkspace as seedWorkspaceLayout } from "@/lib/api";
import { getElectronAPI, isElectron } from "@/lib/platform";
import { useWorkspacePath, writeWorkspacePath } from "@/lib/workspace";
import type { WorkspaceEntry } from "@/types/electron";

const WORKSPACES_QUERY_KEY = ["workspaces"] as const;

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

/** Invalidate every query that is scoped to the active workspace. */
function invalidateWorkspaceScopedQueries(queryClient: ReturnType<typeof useQueryClient>): void {
  for (const key of ["papers", "concepts", "queries"]) {
    void queryClient.invalidateQueries({ queryKey: [key] });
  }
}

export function useWorkspaces() {
  const queryClient = useQueryClient();
  const activeWorkspacePath = useWorkspacePath();

  const workspacesQuery = useQuery({
    queryKey: WORKSPACES_QUERY_KEY,
    queryFn: async (): Promise<WorkspaceEntry[]> => {
      const api = getElectronAPI();
      if (!api) return [];
      return api.listWorkspaces();
    },
    enabled: isElectron(),
  });

  const refreshList = () =>
    void queryClient.invalidateQueries({ queryKey: WORKSPACES_QUERY_KEY });

  const createMutation = useMutation({
    mutationFn: async (name: string): Promise<WorkspaceEntry> => {
      const api = getElectronAPI();
      if (!api) throw new Error("Workspaces are only available in the desktop app");
      // Step 1: Electron allocates the directory + registry entry.
      const entry = await api.createWorkspace(name);
      try {
        // Step 2: backend seeds the canonical layout into that directory.
        await seedWorkspaceLayout({ workspacePath: entry.path, title: name });
      } catch (error) {
        // Roll back the half-created workspace so the switcher stays clean.
        await api.deleteWorkspace(entry.id).catch(() => undefined);
        throw error;
      }
      return entry;
    },
    onSuccess: (entry) => {
      writeWorkspacePath(entry.path);
      refreshList();
      invalidateWorkspaceScopedQueries(queryClient);
      toast.success(`Created workspace "${entry.name}"`);
    },
    onError: (error) => {
      toast.error("Could not create workspace", { description: describeError(error) });
    },
  });

  const openWorkspace = async (entry: WorkspaceEntry) => {
    const api = getElectronAPI();
    await api?.touchWorkspace(entry.id).catch(() => undefined);
    writeWorkspacePath(entry.path);
    refreshList();
    invalidateWorkspaceScopedQueries(queryClient);
  };

  const renameWorkspace = async (id: string, name: string) => {
    const api = getElectronAPI();
    if (!api) return;
    try {
      await api.renameWorkspace(id, name);
      refreshList();
    } catch (error) {
      toast.error("Could not rename workspace", { description: describeError(error) });
    }
  };

  const removeWorkspace = async (entry: WorkspaceEntry) => {
    const api = getElectronAPI();
    if (!api) return;
    try {
      await api.deleteWorkspace(entry.id);
      if (entry.path === activeWorkspacePath) {
        writeWorkspacePath("");
        invalidateWorkspaceScopedQueries(queryClient);
      }
      refreshList();
      toast.success(`Deleted workspace "${entry.name}"`);
    } catch (error) {
      toast.error("Could not delete workspace", { description: describeError(error) });
    }
  };

  const revealWorkspace = async (id: string) => {
    const api = getElectronAPI();
    await api?.revealWorkspace(id).catch(() => undefined);
  };

  return {
    workspaces: workspacesQuery.data ?? [],
    isLoading: workspacesQuery.isLoading,
    activeWorkspacePath,
    createWorkspace: (name: string) => createMutation.mutateAsync(name),
    isCreating: createMutation.isPending,
    openWorkspace,
    renameWorkspace,
    removeWorkspace,
    revealWorkspace,
  };
}
