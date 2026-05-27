// SPDX-License-Identifier: AGPL-3.0-or-later
import { FilePlusIcon, NotebookTextIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function WorkspaceEmptyState() {
  const [explainerOpen, setExplainerOpen] = useState(false);

  return (
    <div className="flex h-full items-center justify-center px-6 py-12">
      <Card className="w-full max-w-xl border-dashed shadow-none">
        <CardContent className="flex flex-col items-center gap-6 px-10 py-14 text-center">
          <div className="bg-muted text-muted-foreground flex size-16 items-center justify-center rounded-2xl">
            <NotebookTextIcon className="size-7" />
          </div>

          <div className="flex flex-col gap-2">
            <h2 className="text-2xl font-semibold tracking-tight">Your wiki is empty</h2>
            <p className="text-muted-foreground max-w-sm text-sm leading-relaxed">
              Drop a PDF, DOCX, or HTML to start building your second brain. Each source touches
              10&ndash;15 wiki pages so synthesis compounds.
            </p>
          </div>

          <Button size="lg" className="gap-2" disabled>
            <FilePlusIcon className="size-4" />
            Import paper
            <span className="text-primary-foreground/70 ml-2 text-[0.65rem] uppercase tracking-wider">
              Phase 2
            </span>
          </Button>

          <button
            type="button"
            onClick={() => {
              setExplainerOpen(true);
            }}
            className="text-muted-foreground hover:text-foreground text-xs underline-offset-4 transition-colors hover:underline"
          >
            What is an LLM Wiki?
          </button>
        </CardContent>
      </Card>

      <Dialog open={explainerOpen} onOpenChange={setExplainerOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>What is an LLM Wiki?</DialogTitle>
            <DialogDescription>
              The compounding-memory pattern from Andrej Karpathy.
            </DialogDescription>
          </DialogHeader>
          <div className="text-foreground/90 flex flex-col gap-3 text-sm leading-relaxed">
            <p>
              An LLM Wiki is a folder of markdown pages that an agent maintains on your behalf. Each
              ingested source touches roughly ten to fifteen pages &mdash; a paper page, a few
              concept pages, the index, the log &mdash; so the synthesis happens once and compounds,
              instead of being re-derived every time you ask a question.
            </p>
            <p>
              Queries read from the wiki and archive their answers under{" "}
              <code className="bg-muted rounded px-1 py-0.5 text-xs">wiki/queries/</code>. Archives
              never auto-modify the synthesis pages; promoting a Q&amp;A into the wiki is an
              explicit <code className="bg-muted rounded px-1 py-0.5 text-xs">/crystallize</code>{" "}
              step you control.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
