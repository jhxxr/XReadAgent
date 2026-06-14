// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { BookOpenIcon, FileQuestionIcon, FilesIcon, LightbulbIcon, PaperclipIcon } from "lucide-react";
import * as React from "react";

import { ThemeToggle } from "@/components/shell/theme-toggle";
import { DocumentsTab } from "@/components/workspace/documents-tab";
import { WorkspaceDropZone } from "@/components/workspace/workspace-drop-zone";
import { WorkspaceEmptyState } from "@/components/workspace/workspace-empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getConcepts, getPapers, getQueries } from "@/lib/api";
import { useWorkspaceActions } from "@/lib/use-workspace-actions";
import type { ConceptSummary, PaperSummary, QuerySummary } from "@/types/api";

function PapersTab({ workspacePath }: { workspacePath: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["papers", workspacePath],
    queryFn: () => getPapers(workspacePath),
  });

  if (isLoading) {
    return (
      <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-3/4" />
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-1/3" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">Failed to load papers.</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <WorkspaceEmptyState />;
  }

  return (
    <ScrollArea className="h-full">
      <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((paper: PaperSummary) => (
          <Link key={paper.slug} to="/paper/$slug" params={{ slug: paper.slug }} className="block">
            <Card className="hover:border-primary/40 transition-colors">
              <CardHeader className="pb-3">
                <CardTitle className="line-clamp-2 text-base">
                  {paper.title || paper.slug}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground space-y-1.5 text-xs">
                {paper.authors.length > 0 && (
                  <p className="line-clamp-1">
                    {paper.authors.slice(0, 3).join(", ")}
                    {paper.authors.length > 3 && " et al."}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  {paper.year && <Badge variant="secondary">{paper.year}</Badge>}
                  {paper.ingestedAt && (
                    <span>{new Date(paper.ingestedAt).toLocaleDateString()}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </ScrollArea>
  );
}

function ConceptsTab({ workspacePath }: { workspacePath: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["concepts", workspacePath],
    queryFn: () => getConcepts(workspacePath),
  });

  if (isLoading) {
    return (
      <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-3/4" />
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-4 w-1/2" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">Failed to load concepts.</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <WorkspaceEmptyState />;
  }

  return (
    <ScrollArea className="h-full">
      <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((concept: ConceptSummary) => (
          <Link
            key={concept.slug}
            to="/concept/$slug"
            params={{ slug: concept.slug }}
            className="block"
          >
            <Card className="hover:border-primary/40 transition-colors">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{concept.title || concept.slug}</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground space-y-1.5 text-xs">
                {concept.aliases.length > 0 && (
                  <p className="line-clamp-1">Aliases: {concept.aliases.join(", ")}</p>
                )}
                <p>
                  {concept.paperCount} related paper{concept.paperCount !== 1 ? "s" : ""}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </ScrollArea>
  );
}

function QueriesTab({ workspacePath }: { workspacePath: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["queries", workspacePath],
    queryFn: () => getQueries(workspacePath),
  });

  if (isLoading) {
    return (
      <div className="space-y-3 p-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="py-4">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="mt-2 h-4 w-1/2" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">Failed to load queries.</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return <WorkspaceEmptyState />;
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-3 p-6">
        {data.map((query: QuerySummary) => {
          // id is "topic/slug" — split for the route.
          const parts = query.id.split("/");
          const topic = parts[0] ?? "";
          const slug = parts.slice(1).join("/");
          return (
            <Link
              key={query.id}
              to="/query/$topic/$slug"
              params={{ topic, slug }}
              className="block"
            >
              <Card className="hover:border-primary/40 transition-colors">
                <CardContent className="flex items-start gap-3 py-4">
                  <FileQuestionIcon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm font-medium">{query.question}</p>
                    <div className="text-muted-foreground mt-1 flex items-center gap-2 text-xs">
                      <Badge variant="outline" className="text-xs">
                        {query.topic}
                      </Badge>
                      {query.archivedAt && (
                        <span>{new Date(query.archivedAt).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </ScrollArea>
  );
}

export function WorkspaceRoute() {
  const { importDocument, importDroppedFiles, isImporting, workspacePath } = useWorkspaceActions();
  // The header TabsList and the content TabsContent live in two separate
  // Radix Tabs roots (the trigger row sits inside the <header> bar). Share
  // one controlled value so clicking a header trigger switches the content.
  const [tab, setTab] = React.useState("documents");

  const handleDropFiles = (files: File[]) => {
    void importDroppedFiles(files);
  };

  if (!workspacePath) {
    return (
      <WorkspaceDropZone className="flex h-full min-w-0 flex-col" onDropFiles={handleDropFiles}>
        <header className="border-border/60 flex h-14 items-center gap-4 border-b px-6">
          <div className="flex flex-col">
            <h1 className="text-sm font-semibold leading-tight">Default Workspace</h1>
            <p className="text-muted-foreground text-xs">Local-first &middot; LLM-Wiki memory</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
          </div>
        </header>
        <WorkspaceEmptyState />
      </WorkspaceDropZone>
    );
  }

  return (
    <WorkspaceDropZone className="flex h-full min-w-0 flex-col" onDropFiles={handleDropFiles}>
      <header className="border-border/60 flex h-14 items-center gap-4 border-b px-6">
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold leading-tight">Default Workspace</h1>
          <p className="text-muted-foreground text-xs">Local-first &middot; LLM-Wiki memory</p>
        </div>
        <Tabs value={tab} onValueChange={setTab} className="ml-6 hidden sm:block">
          <TabsList>
            <TabsTrigger value="documents" className="gap-1.5">
              <FilesIcon className="size-3.5" />
              Documents
            </TabsTrigger>
            <TabsTrigger value="papers" className="gap-1.5">
              <BookOpenIcon className="size-3.5" />
              Papers
            </TabsTrigger>
            <TabsTrigger value="concepts" className="gap-1.5">
              <LightbulbIcon className="size-3.5" />
              Concepts
            </TabsTrigger>
            <TabsTrigger value="queries" className="gap-1.5">
              <FileQuestionIcon className="size-3.5" />
              Queries
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <Separator orientation="vertical" className="mx-1 h-6" />
          <Button
            size="sm"
            className="gap-2"
            disabled={isImporting}
            onClick={() => {
              void importDocument();
            }}
          >
            <PaperclipIcon className="size-3.5" />
            {isImporting ? "Importing..." : "Import"}
          </Button>
        </div>
      </header>

      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <TabsContent value="documents" className="m-0 flex-1">
          <DocumentsTab workspacePath={workspacePath} />
        </TabsContent>
        <TabsContent value="papers" className="m-0 flex-1">
          <PapersTab workspacePath={workspacePath} />
        </TabsContent>
        <TabsContent value="concepts" className="m-0 flex-1">
          <ConceptsTab workspacePath={workspacePath} />
        </TabsContent>
        <TabsContent value="queries" className="m-0 flex-1">
          <QueriesTab workspacePath={workspacePath} />
        </TabsContent>
      </Tabs>
    </WorkspaceDropZone>
  );
}
