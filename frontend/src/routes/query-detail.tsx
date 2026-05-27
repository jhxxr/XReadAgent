// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { SparklesIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { WikiMarkdown } from "@/components/wiki/wiki-markdown";
import { getQueryPage } from "@/lib/api";
import { readWorkspacePath } from "@/lib/workspace";

export function QueryDetailRoute() {
  const { topic, slug } = useParams({ from: "/query/$topic/$slug" });
  const workspacePath = readWorkspacePath();

  const { data, isLoading, error } = useQuery({
    queryKey: ["query", workspacePath, topic, slug],
    queryFn: () => getQueryPage(workspacePath, topic, slug),
    enabled: !!workspacePath,
  });

  if (!workspacePath) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-muted-foreground text-sm">No workspace configured.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
        <div className="flex items-center gap-3">
          <Badge variant="outline">query</Badge>
          <Skeleton className="h-4 w-32" />
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-3/4" />
          </CardHeader>
        </Card>
        <div className="space-y-4">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">Failed to load query.</p>
      </div>
    );
  }

  const fm = data.frontmatter;
  const question = typeof fm.question === "string" ? fm.question : slug;
  const date = typeof fm.date === "string" ? fm.date : undefined;

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
      {/* Header bar */}
      <div className="flex items-center gap-3">
        <Badge variant="outline">query</Badge>
        <span className="text-muted-foreground font-mono text-xs">
          {topic}/{slug}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" className="gap-2" disabled>
            <SparklesIcon className="size-3.5" />
            Crystallize
            <span className="text-muted-foreground ml-1 text-[0.6rem] uppercase tracking-wider">
              Phase 2
            </span>
          </Button>
        </div>
      </div>

      {/* Question header */}
      <Card>
        <CardHeader className="pb-4">
          <h1 className="text-xl font-bold">{question}</h1>
          {date && (
            <p className="text-muted-foreground text-sm">
              {date}
            </p>
          )}
        </CardHeader>
      </Card>

      {/* Markdown content */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="pb-10">
          <WikiMarkdown content={data.content} />
        </div>
      </ScrollArea>
    </div>
  );
}
