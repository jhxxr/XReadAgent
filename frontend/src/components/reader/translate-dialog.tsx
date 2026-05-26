// SPDX-License-Identifier: AGPL-3.0-or-later
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, buildJobEventsWsUrl, postTranslate } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  FinishEvent,
  StageName,
  TranslationEvent,
} from "@/types/api";

/** Stages we render in the per-stage progress checklist, in pipeline order. */
const STAGE_ORDER: readonly StageName[] = [
  "loading",
  "parsing",
  "ocr",
  "layout",
  "translation",
  "typesetting",
  "rendering",
  "saving",
  "finalize",
] as const;

const STAGE_LABEL: Record<StageName, string> = {
  loading: "Loading",
  parsing: "Parsing",
  ocr: "OCR",
  layout: "Layout",
  translation: "Translation",
  typesetting: "Typesetting",
  rendering: "Rendering",
  saving: "Saving",
  finalize: "Finalize",
};

type StageStatus = "pending" | "active" | "done";

export interface TranslateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspacePath: string;
  sourcePath: string;
  /** Default model token (e.g. `anthropic:claude-3-7-sonnet-latest`). */
  defaultModel?: string;
  /** Called with the finish event when translation completes. */
  onFinish?: (event: FinishEvent) => void;
  /**
   * Override for tests: provide a WebSocket constructor that does not hit
   * the network. Defaults to the global `WebSocket`.
   */
  websocketFactory?: (url: string) => WebSocket;
}

interface RunState {
  status:
    | "idle"
    | "starting"
    | "downloading"
    | "running"
    | "finished"
    | "errored";
  jobId: string | null;
  /** Per-stage status; only stages we've heard about appear here. */
  stages: Partial<Record<StageName, StageStatus>>;
  /** Current overall percent if BabelDOC reports one (0-100). */
  percent: number | null;
  /** Active stage label for the headline. */
  activeStage: StageName | null;
  /** Asset download bytes (engine-prep phase). */
  download: {
    asset: string;
    bytesDownloaded: number | null;
    bytesTotal: number | null;
  } | null;
  errorMessage: string | null;
}

const INITIAL_STATE: RunState = {
  status: "idle",
  jobId: null,
  stages: {},
  percent: null,
  activeStage: null,
  download: null,
  errorMessage: null,
};

/**
 * Translate dialog: collects target language + model, POSTs `/api/translate`,
 * subscribes the WS stream, and renders per-stage progress until the job
 * finishes or errors out.
 */
export function TranslateDialog({
  open,
  onOpenChange,
  workspacePath,
  sourcePath,
  defaultModel = "anthropic:claude-3-7-sonnet-latest",
  onFinish,
  websocketFactory,
}: TranslateDialogProps) {
  const [target, setTarget] = React.useState("zh");
  const [model, setModel] = React.useState(defaultModel);
  const [mono, setMono] = React.useState(true);
  const [dual, setDual] = React.useState(true);
  const [run, setRun] = React.useState<RunState>(INITIAL_STATE);

  const wsRef = React.useRef<WebSocket | null>(null);

  // Tear down the socket if the dialog closes mid-job.
  React.useEffect(() => {
    if (!open && wsRef.current !== null) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (!open) {
      setRun(INITIAL_STATE);
    }
  }, [open]);

  // Always close the socket on unmount.
  React.useEffect(() => {
    return () => {
      if (wsRef.current !== null) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  const handleStart = React.useCallback(async () => {
    setRun({ ...INITIAL_STATE, status: "starting" });
    try {
      const { jobId } = await postTranslate({
        workspacePath,
        sourcePath,
        model,
        targetLang: target,
        mono,
        dual,
      });
      setRun((prev) => ({ ...prev, jobId }));
      const url = buildJobEventsWsUrl(jobId);
      const factory = websocketFactory ?? ((u: string) => new WebSocket(u));
      const socket = factory(url);
      wsRef.current = socket;
      socket.addEventListener("message", (event: MessageEvent<string>) => {
        try {
          const payload = JSON.parse(event.data) as TranslationEvent;
          setRun((prev) => reduce(prev, payload));
          if (payload.type === "finish") {
            onFinish?.(payload);
          }
        } catch {
          // Ignore malformed payloads — the backend strictly serializes
          // events through Pydantic so this should never happen in
          // practice. Surfacing the raw text would be noise.
        }
      });
      socket.addEventListener("error", () => {
        setRun((prev) => ({
          ...prev,
          status: "errored",
          errorMessage: "WebSocket error",
        }));
      });
    } catch (cause) {
      const message =
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "Failed to start translation";
      setRun({ ...INITIAL_STATE, status: "errored", errorMessage: message });
    }
  }, [dual, mono, model, onFinish, sourcePath, target, websocketFactory, workspacePath]);

  const busy =
    run.status === "starting" ||
    run.status === "downloading" ||
    run.status === "running";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Translate paper</DialogTitle>
          <DialogDescription>
            Hand the original PDF off to BabelDOC. The output preserves
            layout — figures, tables and equations stay in place.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5 text-xs font-medium">
              <span>Target language</span>
              <Input
                type="text"
                value={target}
                onChange={(e) => {
                  setTarget(e.currentTarget.value);
                }}
                disabled={busy}
                aria-label="Target language"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-xs font-medium">
              <span>Model</span>
              <Input
                type="text"
                value={model}
                onChange={(e) => {
                  setModel(e.currentTarget.value);
                }}
                disabled={busy}
                aria-label="Model"
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs font-medium">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={mono}
                onChange={(e) => {
                  setMono(e.currentTarget.checked);
                }}
                disabled={busy}
              />
              <span>Mono PDF (translated only)</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={dual}
                onChange={(e) => {
                  setDual(e.currentTarget.checked);
                }}
                disabled={busy}
              />
              <span>Dual PDF (alternating pages)</span>
            </label>
          </div>

          {run.status === "downloading" && (
            <DownloadOverlay
              asset={run.download?.asset ?? "engine assets"}
              bytesDownloaded={run.download?.bytesDownloaded ?? null}
              bytesTotal={run.download?.bytesTotal ?? null}
            />
          )}

          {(run.status === "running" || run.status === "finished") && (
            <StageChecklist
              stages={run.stages}
              activeStage={run.activeStage}
              percent={run.percent}
            />
          )}

          {run.status === "errored" && (
            <div
              role="alert"
              className="text-destructive bg-destructive/10 border-destructive/30 rounded-md border p-3 text-xs"
            >
              {run.errorMessage ?? "Translation failed."}
            </div>
          )}

          {run.status === "finished" && (
            <div
              role="status"
              className="text-success bg-success/10 border-success/30 rounded-md border p-3 text-xs"
            >
              Translation complete. Switching to the dual reader…
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
            disabled={busy}
          >
            Close
          </Button>
          <Button
            onClick={() => {
              void handleStart();
            }}
            disabled={busy || (!mono && !dual)}
          >
            {busy ? "Translating…" : "Translate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function reduce(state: RunState, event: TranslationEvent): RunState {
  switch (event.type) {
    case "model_download_start":
      return {
        ...state,
        status: "downloading",
        download: {
          asset: event.asset,
          bytesDownloaded: event.bytes_downloaded,
          bytesTotal: event.bytes_total,
        },
      };
    case "model_download_progress":
      return {
        ...state,
        status: "downloading",
        download: {
          asset: event.asset,
          bytesDownloaded: event.bytes_downloaded,
          bytesTotal: event.bytes_total,
        },
      };
    case "model_download_done":
      return {
        ...state,
        status: "running",
        download: null,
      };
    case "stage_start": {
      const nextStages: Partial<Record<StageName, StageStatus>> = { ...state.stages };
      nextStages[event.stage] = "active";
      return {
        ...state,
        status: "running",
        activeStage: event.stage,
        stages: nextStages,
        percent: event.percent ?? state.percent,
      };
    }
    case "stage_progress":
      return {
        ...state,
        status: "running",
        activeStage: event.stage,
        percent: event.percent ?? state.percent,
      };
    case "stage_end": {
      const nextStages: Partial<Record<StageName, StageStatus>> = { ...state.stages };
      nextStages[event.stage] = "done";
      return {
        ...state,
        status: "running",
        stages: nextStages,
        percent: event.percent ?? state.percent,
      };
    }
    case "finish":
      return {
        ...state,
        status: "finished",
        percent: 100,
      };
    case "error":
      return {
        ...state,
        status: "errored",
        errorMessage: event.message,
      };
  }
}

interface StageChecklistProps {
  stages: Partial<Record<StageName, StageStatus>>;
  activeStage: StageName | null;
  percent: number | null;
}

function StageChecklist({ stages, activeStage, percent }: StageChecklistProps) {
  return (
    <div className="flex flex-col gap-2" data-slot="stage-checklist">
      {percent !== null && (
        <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
          <div
            className="bg-primary h-full transition-all"
            style={{ width: `${Math.min(100, Math.max(0, percent)).toString()}%` }}
            aria-hidden
          />
        </div>
      )}
      <ul className="flex flex-col gap-1 text-xs">
        {STAGE_ORDER.map((name) => {
          const status: StageStatus =
            stages[name] ?? (name === activeStage ? "active" : "pending");
          return (
            <li
              key={name}
              data-stage={name}
              data-status={status}
              className={cn(
                "flex items-center gap-2",
                status === "done" && "text-success",
                status === "active" && "text-primary font-medium",
                status === "pending" && "text-muted-foreground",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "inline-block size-2 rounded-full",
                  status === "done" && "bg-success",
                  status === "active" && "bg-primary animate-pulse",
                  status === "pending" && "bg-muted-foreground/40",
                )}
              />
              {STAGE_LABEL[name]}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface DownloadOverlayProps {
  asset: string;
  bytesDownloaded: number | null;
  bytesTotal: number | null;
}

function DownloadOverlay({ asset, bytesDownloaded, bytesTotal }: DownloadOverlayProps) {
  const percent =
    bytesTotal !== null && bytesTotal > 0 && bytesDownloaded !== null
      ? Math.min(100, Math.round((bytesDownloaded / bytesTotal) * 100))
      : null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-slot="download-overlay"
      className="bg-muted/40 border-border/60 flex flex-col gap-2 rounded-md border p-3 text-xs"
    >
      <span className="font-medium">Preparing translation engine…</span>
      <span className="text-muted-foreground">{asset}</span>
      {percent !== null && (
        <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
          <div
            className="bg-primary h-full transition-all"
            style={{ width: `${percent.toString()}%` }}
            aria-hidden
          />
        </div>
      )}
    </div>
  );
}
