// SPDX-License-Identifier: AGPL-3.0-or-later
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { SparklesIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CopilotSidebar() {
  const [open, setOpen] = useState(false);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label="Open copilot"
          data-testid="copilot-trigger"
          className={cn(
            "bg-primary text-primary-foreground fixed right-6 bottom-6 z-40 inline-flex size-12 items-center justify-center rounded-full shadow-lg transition-transform hover:scale-105 active:scale-95",
          )}
        >
          <SparklesIcon className="size-5" />
        </button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            "fixed inset-0 z-50 bg-black/40 backdrop-blur-[1px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          )}
        />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className={cn(
            "bg-background fixed top-0 right-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border/80 shadow-xl",
            "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right data-[state=closed]:duration-200 data-[state=open]:duration-200",
          )}
        >
          <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5">
            <DialogPrimitive.Title className="flex items-center gap-2 text-sm font-semibold">
              <SparklesIcon className="size-4" />
              Copilot
            </DialogPrimitive.Title>
            <DialogPrimitive.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close copilot">
                <XIcon className="size-4" />
              </Button>
            </DialogPrimitive.Close>
          </div>
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
              <SparklesIcon className="size-5" />
            </div>
            <h3 className="text-base font-semibold tracking-tight">Coming in Phase 2</h3>
            <p className="text-muted-foreground max-w-xs text-sm leading-relaxed">
              Ask, evidence, and crystallize will land here once the streaming agent contract
              is finalized.
            </p>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
