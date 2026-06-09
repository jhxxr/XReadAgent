// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeftIcon, LanguagesIcon } from "lucide-react";
import * as React from "react";

import { PdfViewer } from "@/components/reader/pdf-viewer";
import { PdfToolbar } from "@/components/reader/pdf-toolbar";
import { TranslateDialog } from "@/components/reader/translate-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { buildWorkspaceFileUrl, getPaper, getTranslationsManifest } from "@/lib/api";
import { notifyOnCompletion } from "@/lib/notifications";
import { readWorkspacePath } from "@/lib/workspace";
import type {
  FinishEvent,
  TranslationEntry,
  TranslationsManifest,
  WikiPageResponse,
} from "@/types/api";
import type { PdfToolbarProps } from "@/components/reader/pdf-toolbar";

type ReaderTab = "original" | "dual" | "translated";

interface SourcesInfo {
  original: string | null;
  sourcePath: string | null;
  sourceKind: string;
  mono: string | null;
  dual: string | null;
}

function selectTranslationForSlug(
  manifest: TranslationsManifest | undefined,
  slug: string,
): TranslationEntry | null {
  if (manifest === undefined) return null;
  for (const entry of manifest.entries) {
    if (entry.sourceSlug === slug) return entry;
  }
  return null;
}

function buildSources(
  workspacePath: string,
  paper: WikiPageResponse | undefined,
  entry: TranslationEntry | null,
): SourcesInfo {
  const sourcePath = paper?.sourcePath ?? null;
  const sourceKind = paper?.sourceKind ?? "";
  const hasPdfSource = sourcePath?.toLowerCase().endsWith(".pdf") ?? false;
  const pdfSourcePath = hasPdfSource ? sourcePath : null;
  return {
    original:
      pdfSourcePath !== null && workspacePath.length > 0
        ? buildWorkspaceFileUrl(workspacePath, pdfSourcePath)
        : null,
    sourcePath,
    sourceKind,
    mono:
      entry?.monoPath !== undefined && entry.monoPath !== null && workspacePath.length > 0
        ? buildWorkspaceFileUrl(workspacePath, entry.monoPath)
        : null,
    dual:
      entry?.dualPath !== undefined && entry.dualPath !== null && workspacePath.length > 0
        ? buildWorkspaceFileUrl(workspacePath, entry.dualPath)
        : null,
  };
}

function defaultTab(sources: SourcesInfo): ReaderTab {
  if (sources.dual !== null) return "dual";
  if (sources.original !== null) return "original";
  if (sources.mono !== null) return "translated";
  return "original";
}

export function PaperReadRoute() {
  const { slug } = useParams({ from: "/paper/$slug/read" });
  const [workspacePath] = React.useState<string>(() => readWorkspacePath());
  const queryClient = useQueryClient();

  const manifestQuery = useQuery({
    queryKey: ["translations-manifest", workspacePath],
    queryFn: () => getTranslationsManifest(workspacePath),
    enabled: workspacePath.length > 0,
  });

  const paperQuery = useQuery({
    queryKey: ["paper", workspacePath, slug],
    queryFn: () => getPaper(workspacePath, slug),
    enabled: workspacePath.length > 0,
  });

  const entry = selectTranslationForSlug(manifestQuery.data, slug);
  const sources = buildSources(workspacePath, paperQuery.data, entry);
  const absoluteSourcePath =
    sources.original !== null && sources.sourcePath !== null
      ? joinWorkspacePath(workspacePath, sources.sourcePath)
      : null;

  const initialTab = defaultTab(sources);
  const [tab, setTab] = React.useState<ReaderTab>(initialTab);
  const [tabPinned, setTabPinned] = React.useState(false);
  const [translateOpen, setTranslateOpen] = React.useState(false);

  // Persist zoom level and current page across tab switches.
  // Each tab has its own page tracking, but zoom is shared.
  const [zoom, setZoom] = React.useState(100);
  const [pageStates, setPageStates] = React.useState<Record<ReaderTab, number>>({
    original: 1,
    dual: 1,
    translated: 1,
  });

  // Refs for accessing latest state inside callbacks without re-creating them.
  const pageStatesRef = React.useRef(pageStates);
  pageStatesRef.current = pageStates;
  const tabRef = React.useRef(tab);
  tabRef.current = tab;

  // After manifest data arrives, recompute the default tab — unless the
  // user has already picked a tab, in which case we leave their choice
  // alone. This handles "open /read with no dual yet → translate completes
  // → swap to dual".
  React.useEffect(() => {
    if (tabPinned) return;
    setTab(defaultTab(sources));
  }, [sources, tabPinned]);

  const handleFinish = React.useCallback(
    (event: FinishEvent) => {
      // Refetch the manifest so the new mono/dual paths land.
      void queryClient.invalidateQueries({
        queryKey: ["translations-manifest", workspacePath],
      });
      // Preserve the current reading position when auto-switching tabs.
      const currentPageNumber = pageStatesRef.current[tabRef.current];
      if (event.dual_path !== null) {
        setPageStates((prev) => ({ ...prev, dual: currentPageNumber }));
        setTab("dual");
        setTabPinned(true);
      } else if (event.mono_path !== null) {
        setPageStates((prev) => ({ ...prev, translated: currentPageNumber }));
        setTab("translated");
        setTabPinned(true);
      }
      // Send a desktop notification for the completed translation.
      notifyOnCompletion("Translation complete", `Paper "${slug}" has been translated.`);
      // Close the dialog on the next tick so the success toast can flash.
      setTimeout(() => {
        setTranslateOpen(false);
      }, 600);
    },
    [queryClient, workspacePath, slug],
  );

  const handleCurrentPageChange = React.useCallback(
    (page: number) => {
      setPageStates((prev) => ({ ...prev, [tab]: page }));
    },
    [tab],
  );

  const renderToolbar = React.useCallback(
    (props: PdfToolbarProps) => {
      return <PdfToolbar {...props} />;
    },
    [],
  );

  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="border-border/60 flex h-14 items-center gap-3 border-b px-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/paper/$slug" params={{ slug }} className="gap-2">
            <ArrowLeftIcon className="size-3.5" />
            Back to wiki page
          </Link>
        </Button>
        <Badge variant="outline">read</Badge>
        <span className="text-muted-foreground font-mono text-xs">{slug}</span>
        <div className="ml-auto flex items-center gap-2">
          {workspacePath.length > 0 && absoluteSourcePath === null && !paperQuery.isLoading && (
            <span className="text-muted-foreground text-xs">No PDF source</span>
          )}
          <Button
            size="sm"
            className="gap-2"
            onClick={() => {
              setTranslateOpen(true);
            }}
            disabled={workspacePath.length === 0 || absoluteSourcePath === null}
          >
            <LanguagesIcon className="size-3.5" />
            Translate
          </Button>
        </div>
      </header>

      {workspacePath.length === 0 ? (
        <NoWorkspaceState />
      ) : manifestQuery.isError ? (
        <ManifestErrorState message={manifestQuery.error.message} />
      ) : paperQuery.isError ? (
        <ManifestErrorState message={paperQuery.error.message} />
      ) : (
        <Tabs
          value={tab}
          onValueChange={(value) => {
            setTab(value as ReaderTab);
            setTabPinned(true);
          }}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="border-border/60 flex items-center border-b px-4 py-2">
            <TabsList>
              <TabsTrigger value="original" disabled={sources.original === null}>
                Original
              </TabsTrigger>
              <TabsTrigger value="dual" disabled={sources.dual === null}>
                Dual
              </TabsTrigger>
              <TabsTrigger value="translated" disabled={sources.mono === null}>
                Translated
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="original" className="m-0 min-h-0 flex-1 overflow-hidden">
            {sources.original !== null ? (
              <PdfViewer
                url={sources.original}
                mode="single"
                zoom={zoom}
                onZoomChange={setZoom}
                currentPage={pageStates.original}
                onCurrentPageChange={handleCurrentPageChange}
                renderToolbar={renderToolbar}
              />
            ) : (
              <EmptyPaneState>
                {paperQuery.isLoading
                  ? "Loading source metadata..."
                  : "No PDF source is available for this paper."}
              </EmptyPaneState>
            )}
          </TabsContent>
          <TabsContent value="dual" className="m-0 min-h-0 flex-1 overflow-hidden">
            {sources.dual !== null ? (
              <PdfViewer
                url={sources.dual}
                mode="dual"
                zoom={zoom}
                onZoomChange={setZoom}
                currentPage={pageStates.dual}
                onCurrentPageChange={handleCurrentPageChange}
                renderToolbar={renderToolbar}
              />
            ) : (
              <EmptyPaneState>
                No dual PDF yet. Click <span className="font-medium">Translate</span> to create one.
              </EmptyPaneState>
            )}
          </TabsContent>
          <TabsContent value="translated" className="m-0 min-h-0 flex-1 overflow-hidden">
            {sources.mono !== null ? (
              <PdfViewer
                url={sources.mono}
                mode="single"
                zoom={zoom}
                onZoomChange={setZoom}
                currentPage={pageStates.translated}
                onCurrentPageChange={handleCurrentPageChange}
                renderToolbar={renderToolbar}
              />
            ) : (
              <EmptyPaneState>
                No translated-only PDF yet. Click <span className="font-medium">Translate</span> to
                create one.
              </EmptyPaneState>
            )}
          </TabsContent>
        </Tabs>
      )}

      {workspacePath.length > 0 && absoluteSourcePath !== null && (
        <TranslateDialog
          open={translateOpen}
          onOpenChange={setTranslateOpen}
          workspacePath={workspacePath}
          sourcePath={absoluteSourcePath}
          onFinish={handleFinish}
        />
      )}
    </div>
  );
}

function joinWorkspacePath(workspacePath: string, relativePath: string): string {
  const normalizedWorkspace = workspacePath.replaceAll("\\", "/").replace(/\/+$/, "");
  const normalizedRelative = relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
  return `${normalizedWorkspace}/${normalizedRelative}`;
}

function NoWorkspaceState() {
  return (
    <div className="text-muted-foreground mx-auto flex max-w-md flex-col items-center justify-center gap-2 px-6 py-16 text-center text-sm">
      <p className="text-foreground font-medium">No workspace selected</p>
      <p>
        The reader needs a workspace path to fetch original and translated PDFs from. Set one via
        the workspace picker (coming in Phase 3) or by writing
        <code className="bg-muted mx-1 rounded px-1 py-0.5 text-xs">xreadagent.workspacePath</code>
        into <code>localStorage</code>.
      </p>
    </div>
  );
}

function ManifestErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="text-destructive bg-destructive/10 border-destructive/30 mx-6 mt-6 rounded-md border p-3 text-xs"
    >
      Could not load translations manifest: {message}
    </div>
  );
}

function EmptyPaneState({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted-foreground flex h-full items-center justify-center px-6 py-12 text-center text-sm">
      <p>{children}</p>
    </div>
  );
}
