// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { WikiMarkdown } from "@/components/wiki/wiki-markdown";
import { getConcept } from "@/lib/api";
import { readWorkspacePath } from "@/lib/workspace";

export function ConceptRoute() {
  const { slug } = useParams({ from: "/concept/$slug" });
  const workspacePath = readWorkspacePath();

  const { data, isLoading, error } = useQuery({
    queryKey: ["concept", workspacePath, slug],
    queryFn: () => getConcept(workspacePath, slug),
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
          <Badge variant="outline">concept</Badge>
          <Skeleton className="h-4 w-32" />
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
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
        <p className="text-destructive text-sm">Failed to load concept.</p>
      </div>
    );
  }

  const fm = data.frontmatter;
  const title = typeof fm.title === "string" ? fm.title : slug;
  // Narrow from unknown[] — backend guarantees string elements.
  const aliases = Array.isArray(fm.aliases) ? (fm.aliases as string[]) : [];

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
      {/* Header bar */}
      <div className="flex items-center gap-3">
        <Badge variant="outline">concept</Badge>
        <span className="text-muted-foreground font-mono text-xs">{slug}</span>
      </div>

      {/* Frontmatter header */}
      <Card>
        <CardHeader className="pb-4">
          <h1 className="text-xl font-bold">{title}</h1>
          {aliases.length > 0 && (
            <p className="text-muted-foreground text-sm">Also known as: {aliases.join(", ")}</p>
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
