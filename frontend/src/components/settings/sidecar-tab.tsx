// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { AlertTriangleIcon, RefreshCwIcon, ServerIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getElectronAPI, isElectron } from "@/lib/platform";
import type { SidecarStatus } from "@/types/electron";

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
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    if (!api) return;
    try {
      const result = await api.getSidecarStatus();
      setStatus(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query sidecar status");
    }
  };

  const fetchLogs = async () => {
    if (!api) return;
    try {
      const lines = await api.getSidecarLogs();
      setLogs(lines);
    } catch {
      // Logs are best-effort; don't surface errors for this.
    }
  };

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!api) {
    return <BrowserModeNotice />;
  }

  const currentStatus = status?.status ?? "idle";
  const badgeVariant = STATUS_TONE[currentStatus];
  const badgeLabel = STATUS_LABEL[currentStatus];

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
              <Badge variant={badgeVariant}>{badgeLabel}</Badge>
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
              disabled={restarting || currentStatus === "starting"}
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
          <CardTitle className="text-base">Logs</CardTitle>
          <CardDescription>Recent sidecar stdout and stderr output.</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-64 w-full rounded-md border">
            <div className="bg-muted/50 p-3 font-mono text-xs leading-relaxed">
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
