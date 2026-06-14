// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheckIcon, FileTextIcon, LanguagesIcon, SparklesIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { TranslateDialog } from "@/components/reader/translate-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { getSources, postBuildWiki } from "@/lib/api";
import { runIngestJob } from "@/lib/ingest-job";
import type { IngestStageName, SourceSummary } from "@/types/api";

const BUILD_TOAST_ID = "build-wiki-progress";
const BUILD_MUTATION_KEY = ["build-wiki"] as const;

const BUILD_STAGE_LABEL: Record<IngestStageName, string> = {
  converting: "Preparing the document…",
  analyzing: "Analyzing with the model…",
  writing: "Writing wiki pages…",
};

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Unknown error";
}

export function DocumentsTab({ workspacePath }: { workspacePath: string }) {
  const queryClient = useQueryClient();
  const [translateSlug, setTranslateSlug] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["sources", workspacePath],
    queryFn: () => getSources(workspacePath),
  });

  const buildMutation = useMutation({
    mutationKey: BUILD_MUTATION_KEY,
    mutationFn: (slug: string) => {
      toast.loading("Building wiki", { id: BUILD_TOAST_ID, description: "Starting…" });
      return runIngestJob(
        { workspacePath, filePath: "" },
        {
          submit: () => postBuildWiki(slug, { workspacePath }),
          onStage: (stage) => {
            toast.loading("Building wiki", {
              id: BUILD_TOAST_ID,
              description: BUILD_STAGE_LABEL[stage],
            });
          },
        },
      );
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
      void queryClient.invalidateQueries({ queryKey: ["papers"] });
      void queryClient.invalidateQueries({ queryKey: ["concepts"] });
      toast.success(`Wiki built for ${result.title}`, { id: BUILD_TOAST_ID });
    },
    onError: (err) => {
      toast.error("Build failed", { id: BUILD_TOAST_ID, description: describeError(err) });
    },
  });

  const translateSource = data?.find((s) => s.slug === translateSlug) ?? null;

  if (isLoading) {
    return (
      <div className="space-y-3 p-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="py-4">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="mt-2 h-4 w-1/3" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">Failed to load documents.</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <p className="text-muted-foreground text-sm">
          No documents yet. Import a PDF, DOCX, or HTML to register it here.
        </p>
      </div>
    );
  }

  return (
    <>
      <ScrollArea className="h-full">
        <div className="space-y-3 p-6">
          {data.map((source: SourceSummary) => (
            <Card key={source.slug}>
              <CardContent className="flex items-center gap-4 py-4">
                <FileTextIcon className="text-muted-foreground size-5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{source.title || source.slug}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {source.wikiBuilt ? (
                      <Badge variant="secondary" className="gap-1">
                        <BookOpenCheckIcon className="size-3" />
                        Wiki built
                      </Badge>
                    ) : (
                      <Badge variant="outline">Registered</Badge>
                    )}
                    {source.translated && (
                      <Badge variant="secondary" className="gap-1">
                        <LanguagesIcon className="size-3" />
                        Translated
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5"
                    disabled={!source.sourcePath}
                    onClick={() => setTranslateSlug(source.slug)}
                  >
                    <LanguagesIcon className="size-4" />
                    Translate
                  </Button>
                  {!source.wikiBuilt && (
                    <Button
                      size="sm"
                      className="gap-1.5"
                      disabled={buildMutation.isPending}
                      onClick={() => buildMutation.mutate(source.slug)}
                    >
                      <SparklesIcon className="size-4" />
                      Build Wiki
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </ScrollArea>

      {translateSource?.sourcePath && (
        <TranslateDialog
          open={translateSlug !== null}
          onOpenChange={(open) => {
            if (!open) setTranslateSlug(null);
          }}
          workspacePath={workspacePath}
          sourcePath={translateSource.sourcePath}
        />
      )}
    </>
  );
}
