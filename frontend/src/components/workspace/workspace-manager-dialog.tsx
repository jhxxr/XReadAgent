// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  CheckIcon,
  FolderOpenIcon,
  FolderSearchIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWorkspaces } from "@/lib/use-workspaces";
import { cn } from "@/lib/utils";
import type { WorkspaceEntry } from "@/types/electron";

interface WorkspaceManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Workspace switcher + manager. Lists every managed workspace, lets the user
 * open / rename / delete / reveal each one, and create new ones — all under the
 * app-managed data directory. Replaces the old "open an arbitrary folder"
 * native dialog so wiki artifacts never land in Downloads.
 */
export function WorkspaceManagerDialog({ open, onOpenChange }: WorkspaceManagerDialogProps) {
  const {
    workspaces,
    activeWorkspacePath,
    createWorkspace,
    isCreating,
    openWorkspace,
    renameWorkspace,
    removeWorkspace,
    revealWorkspace,
  } = useWorkspaces();

  const [newName, setNewName] = useState("");

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await createWorkspace(name);
      setNewName("");
      onOpenChange(false);
    } catch {
      // Errors are surfaced via toast inside the hook; keep the dialog open.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Workspaces</DialogTitle>
          <DialogDescription>
            Each workspace is a self-contained vault stored in the app data folder.
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-72 -mx-2 px-2">
          <ul className="flex flex-col gap-1">
            {workspaces.length === 0 && (
              <li className="text-muted-foreground px-1 py-6 text-center text-sm">
                No workspaces yet. Create one below.
              </li>
            )}
            {workspaces.map((entry) => (
              <WorkspaceRow
                key={entry.id}
                entry={entry}
                active={entry.path === activeWorkspacePath}
                onOpen={() => {
                  void openWorkspace(entry);
                  onOpenChange(false);
                }}
                onRename={(name) => void renameWorkspace(entry.id, name)}
                onDelete={() => void removeWorkspace(entry)}
                onReveal={() => void revealWorkspace(entry.id)}
              />
            ))}
          </ul>
        </ScrollArea>

        <div className="flex items-center gap-2 border-t pt-4">
          <Input
            value={newName}
            placeholder="New workspace name"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleCreate();
            }}
            disabled={isCreating}
          />
          <Button
            className="gap-1.5"
            disabled={isCreating || !newName.trim()}
            onClick={() => void handleCreate()}
          >
            <PlusIcon className="size-4" />
            {isCreating ? "Creating…" : "Create"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface WorkspaceRowProps {
  entry: WorkspaceEntry;
  active: boolean;
  onOpen: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  onReveal: () => void;
}

function WorkspaceRow({ entry, active, onOpen, onRename, onDelete, onReveal }: WorkspaceRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  if (editing) {
    const commit = () => {
      const next = draft.trim();
      if (next && next !== entry.name) onRename(next);
      setEditing(false);
    };
    return (
      <li className="flex items-center gap-2 rounded-md px-2 py-1.5">
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }}
          className="h-8"
        />
        <Button size="icon" variant="ghost" className="size-8" onClick={commit} aria-label="Save name">
          <CheckIcon className="size-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="size-8"
          onClick={() => setEditing(false)}
          aria-label="Cancel rename"
        >
          <XIcon className="size-4" />
        </Button>
      </li>
    );
  }

  return (
    <li
      className={cn(
        "group hover:bg-accent flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors",
        active && "bg-accent/60",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
      >
        <FolderOpenIcon className="text-muted-foreground size-4 shrink-0" />
        <span className="truncate text-sm font-medium">{entry.name}</span>
        {active && <CheckIcon className="text-primary size-4 shrink-0" aria-label="Active" />}
      </button>

      {confirmingDelete ? (
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="destructive"
            className="h-7"
            onClick={() => {
              onDelete();
              setConfirmingDelete(false);
            }}
          >
            Delete
          </Button>
          <Button size="sm" variant="ghost" className="h-7" onClick={() => setConfirmingDelete(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            onClick={onReveal}
            aria-label="Reveal in file manager"
          >
            <FolderSearchIcon className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            onClick={() => {
              setDraft(entry.name);
              setEditing(true);
            }}
            aria-label="Rename workspace"
          >
            <PencilIcon className="size-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="text-destructive size-7"
            onClick={() => setConfirmingDelete(true)}
            aria-label="Delete workspace"
          >
            <Trash2Icon className="size-4" />
          </Button>
        </div>
      )}
    </li>
  );
}
