// SPDX-License-Identifier: AGPL-3.0-or-later
import { PaperclipIcon } from "lucide-react";

import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceEmptyState } from "@/components/workspace/workspace-empty-state";

export function WorkspaceRoute() {
  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="border-border/60 flex h-14 items-center gap-4 border-b px-6">
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold leading-tight">Default Workspace</h1>
          <p className="text-muted-foreground text-xs">
            Local-first &middot; LLM-Wiki memory
          </p>
        </div>
        <Tabs defaultValue="papers" className="ml-6 hidden sm:block">
          <TabsList>
            <TabsTrigger value="papers">Papers</TabsTrigger>
            <TabsTrigger value="concepts">Concepts</TabsTrigger>
            <TabsTrigger value="queries">Queries</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <Separator orientation="vertical" className="mx-1 h-6" />
          <Button size="sm" className="gap-2" disabled>
            <PaperclipIcon className="size-3.5" />
            Import
          </Button>
        </div>
      </header>

      <Tabs defaultValue="papers" className="flex min-h-0 flex-1 flex-col">
        <TabsContent value="papers" className="m-0 flex-1">
          <WorkspaceEmptyState />
        </TabsContent>
        <TabsContent value="concepts" className="m-0 flex-1">
          <WorkspaceEmptyState />
        </TabsContent>
        <TabsContent value="queries" className="m-0 flex-1">
          <WorkspaceEmptyState />
        </TabsContent>
      </Tabs>
    </div>
  );
}
