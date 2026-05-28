// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangleIcon, CheckCircle2Icon, CopyIcon, Loader2Icon, RefreshCwIcon, ServerIcon, XCircleIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getElectronAPI, isElectron, onSidecarRestarting } from "@/lib/platform";
import type { SidecarRestartInfo, SidecarStatus } from "@/types/electron";

/** Status tone mapping for the badge. */
const STATUS_TONE: Record<
  SidecarStatus["status"],
  "success" | "warning" | "destructive" | "secondary"
> = {
  running: "success",
  starting: "warning",
  idle: "secondary",
  stopped: "destructive",
  crashed: "destructive",
};

const STATUS_LABEL: Record<SidecarStatus["status"], string> = {
  running: "Running",
  starting: "Starting",
  idle: "Idle",
  stopped: "Stopped",
  crashed: "Crashed",
};

const STATUS_ICON: Record<SidecarStatus["status"], typeof CheckCircle2Icon | null> = {
  running: CheckCircle2Icon,
  starting: Loader2Icon,
  idle: null,
  stopped: XCircleIcon,
  crashed: AlertTriangleIcon,
};

/**
 * SidecarTab shows the current sidecar process status, logs, and a restart
 * button. Only renders meaningful content inside Electron — in browser dev
 * mode, it shows a placeholder notice.
 */
export function SidecarTab() {
  if (!isElectron()) {
    return <BrowserModeNotice />;
  }
  return <SidecarPanel />;
}

function BrowserModeNotice() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ServerIcon className="size-4" />
          Sidecar
        </CardTitle>
        <CardDescription>
          The sidecar status panel is only available when running inside the Electron desktop app.
          In browser dev mode, the Python sidecar runs separately on localhost:8765.
        </CardDescription>
      </CardHeader>
    </Card>
  );
}

function SidecarPanel() {
  const api = getElectronAPI();

  const [status, setStatus] = useState<SidecarStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [restarting, setRestarting] = useState(false);
  const [restartInfo, setRestartInfo] = useState<SidecarRestartInfo | null>(null);
  const [restartCountdown, setRestartCountdown] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const logScrollRef = useRef<HTMLDivElement>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!api) return;
    try {
      const result = await api.getSidecarStatus();
      setStatus(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query sidecar status");
    }
  }, [api]);

  const fetchLogs = useCallback(async () => {
    if (!api) return;
    try {
      const lines = await api.getSidecarLogs();
      setLogs(lines);
    } catch {
      // Logs are best-effort; don't surface errors for this.
    }
  }, [api]);

  const fetchRestartInfo = useCallback(async () => {
    if (!api) return;
    try {
      const info = await api.getSidecarRestartInfo();
      setRestartInfo(info);
    } catch {
      // Best-effort.
    }
  }, [api]);

  const handleRestart = async () => {
    if (!api) return;
    setRestarting(true);
    setError(null);
    try {
      await api.restartSidecar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Restart failed");
    } finally {
      setRestarting(false);
      // Refresh status after restart attempt.
      await fetchStatus();
    }
  };

  const handleCopyLogs = async () => {
    if (logs.length === 0) return;
    try {
      await navigator.clipboard.writeText(logs.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access denied — ignore.
    }
  };

  // Poll sidecar status every 3 seconds.
  useEffect(() => {
    const poll = () => {
      void fetchStatus();
      void fetchLogs();
    };
    poll();
    const interval = setInterval(poll, 3_000);
    return () => {
      clearInterval(interval);
    };
  }, [fetchStatus, fetchLogs]);

  // Listen for sidecar restart events from the main process.
  useEffect(() => {
    const cleanup = onSidecarRestarting((info) => {
      setRestartInfo(info);
      setRestartCountdown(Math.ceil(info.delayMs / 1000));

      // Clear any existing countdown.
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }

      // Start a countdown timer.
      countdownRef.current = setInterval(() => {
        setRestartCountdown((prev) => {
          if (prev === null || prev <= 1) {
            if (countdownRef.current) {
              clearInterval(countdownRef.current);
              countdownRef.current = null;
            }
            return null;
          }
          return prev - 1;
        });
      }, 1000);

      // Re-fetch status to show the restarting state.
      void fetchStatus();
    });

    // Also fetch restart info on mount.
    void fetchRestartInfo();

    return cleanup;
  }, [fetchStatus, fetchRestartInfo]);

  // Clean up the countdown interval on unmount.
  useEffect(() => {
    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, []);

  // Clear restart info when sidecar is running.
  useEffect(() => {
    if (status?.status === "running" && restartInfo) {
      setRestartInfo(null);
      setRestartCountdown(null);
    }
  }, [status?.status, restartInfo]);

  // Auto-scroll logs to the bottom when new lines arrive.
  useEffect(() => {
    const el = logScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs]);

  if (!api) {
    return <BrowserModeNotice />;
  }

  const currentStatus = status?.status ?? "idle";
  const badgeVariant = STATUS_TONE[currentStatus];
  const badgeLabel = STATUS_LABEL[currentStatus];
  const StatusIcon = STATUS_ICON[currentStatus];

  // Determine if the restart button should be disabled.
  const isRestartDisabled =
    restarting ||
    currentStatus === "starting" ||
    (restartInfo !== null && restartInfo.attempt > 0);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ServerIcon className="size-4" />
            Sidecar Process
          </CardTitle>
          <CardDescription>
            Python backend process that powers ingestion, queries, and translation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">Status</span>
              <Badge variant={badgeVariant} className="gap-1.5">
                {StatusIcon && currentStatus === "starting" ? (
                  <StatusIcon className="size-3 animate-spin" />
                ) : StatusIcon ? (
                  <StatusIcon className="size-3" />
                ) : null}
                {badgeLabel}
              </Badge>
              {restartInfo && restartCountdown !== null && (
                <span className="text-warning text-xs">
                  Restart attempt {restartInfo.attempt}/{restartInfo.maxAttempts}
                  {restartCountdown > 0 ? ` — starting in ${restartCountdown}s` : " — starting..."}
                </span>
              )}
            </div>

            {status?.pid != null && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">PID</span>
                <span className="text-muted-foreground font-mono text-sm">{status.pid}</span>
              </div>
            )}

            {status?.port != null && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">Port</span>
                <span className="text-muted-foreground font-mono text-sm">{status.port}</span>
              </div>
            )}

            {status?.startedAt && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">Started</span>
                <span className="text-muted-foreground text-sm">
                  {new Date(status.startedAt).toLocaleString()}
                </span>
              </div>
            )}

            {status?.restartCount != null && status.restartCount > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">Restarts</span>
                <span className="text-warning text-sm">{status.restartCount} auto-restart(s) this session</span>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="text-destructive bg-destructive/10 border-destructive/30 flex items-center gap-2 rounded-md border p-3 text-xs"
              >
                <AlertTriangleIcon className="size-4 shrink-0" />
                {error}
              </div>
            )}

            <Button
              onClick={() => {
                void handleRestart();
              }}
              disabled={isRestartDisabled}
              variant="outline"
              className="gap-2"
            >
              <RefreshCwIcon className={`size-4 ${restarting ? "animate-spin" : ""}`} />
              {restarting ? "Restarting..." : "Restart Sidecar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Logs</CardTitle>
              <CardDescription>Recent sidecar stdout and stderr output.</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => void handleCopyLogs()}
              disabled={logs.length === 0}
            >
              <CopyIcon className="size-3" />
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-64 w-full rounded-md border">
            <div ref={logScrollRef} className="bg-muted/50 p-3 font-mono text-xs leading-relaxed">
              {logs.length === 0 ? (
                <span className="text-muted-foreground">No logs yet.</span>
              ) : (
                logs.map((line, i) => (
                  <div key={i} className="whitespace-pre-wrap break-all">
                    {line}
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
