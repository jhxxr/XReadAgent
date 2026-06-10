// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CopyIcon,
  Loader2Icon,
  RefreshCwIcon,
  ServerIcon,
  XCircleIcon,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import { getElectronAPI, isElectron, onSidecarRestarting } from "@/lib/platform";
import type { SidecarRestartInfo, SidecarStatus } from "@/types/electron";

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

const STATUS_LABEL_KEY: Record<SidecarStatus["status"], TranslationKey> = {
  running: "settings.sidecar.status.running",
  starting: "settings.sidecar.status.starting",
  idle: "settings.sidecar.status.idle",
  stopped: "settings.sidecar.status.stopped",
  crashed: "settings.sidecar.status.crashed",
};

const STATUS_ICON: Record<SidecarStatus["status"], LucideIcon | null> = {
  running: CheckCircle2Icon,
  starting: Loader2Icon,
  idle: null,
  stopped: XCircleIcon,
  crashed: AlertTriangleIcon,
};

export function SidecarTab() {
  if (!isElectron()) {
    return <BrowserModeNotice />;
  }
  return <SidecarPanel />;
}

function BrowserModeNotice() {
  const { t } = useI18n();

  return (
    <Card className="rounded-md shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ServerIcon className="size-4" />
          {t("settings.sidecar.browserTitle")}
        </CardTitle>
        <CardDescription>{t("settings.sidecar.browserDescription")}</CardDescription>
      </CardHeader>
    </Card>
  );
}

function SidecarPanel() {
  const { t } = useI18n();
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
      setError(err instanceof Error ? err.message : t("settings.sidecar.queryFailed"));
    }
  }, [api, t]);

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
      setError(err instanceof Error ? err.message : t("settings.sidecar.restartFailed"));
    } finally {
      setRestarting(false);
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
      // Clipboard access denied; ignore.
    }
  };

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

  useEffect(() => {
    const cleanup = onSidecarRestarting((info) => {
      setRestartInfo(info);
      setRestartCountdown(Math.ceil(info.delayMs / 1000));

      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }

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

      void fetchStatus();
    });

    void fetchRestartInfo();

    return cleanup;
  }, [fetchStatus, fetchRestartInfo]);

  useEffect(() => {
    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
        countdownRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (status?.status === "running" && restartInfo) {
      setRestartInfo(null);
      setRestartCountdown(null);
    }
  }, [status?.status, restartInfo]);

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
  const badgeLabel = t(STATUS_LABEL_KEY[currentStatus]);
  const StatusIcon = STATUS_ICON[currentStatus];
  const isRestartDisabled =
    restarting ||
    currentStatus === "starting" ||
    (restartInfo !== null && restartInfo.attempt > 0);

  return (
    <div className="space-y-4">
      <Card className="rounded-md shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ServerIcon className="size-4" />
            {t("settings.sidecar.processTitle")}
          </CardTitle>
          <CardDescription>{t("settings.sidecar.processDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium">{t("settings.sidecar.status")}</span>
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
                  {t("settings.sidecar.restartAttempt")} {restartInfo.attempt}/
                  {restartInfo.maxAttempts}
                  {restartCountdown > 0
                    ? ` - ${t("settings.sidecar.startingIn")} ${restartCountdown}s`
                    : ` - ${t("settings.sidecar.startingSoon")}`}
                </span>
              )}
            </div>

            {status?.pid != null && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{t("settings.sidecar.pid")}</span>
                <span className="text-muted-foreground font-mono text-sm">{status.pid}</span>
              </div>
            )}

            {status?.port != null && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{t("settings.sidecar.port")}</span>
                <span className="text-muted-foreground font-mono text-sm">{status.port}</span>
              </div>
            )}

            {status?.startedAt && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{t("settings.sidecar.started")}</span>
                <span className="text-muted-foreground text-sm">
                  {new Date(status.startedAt).toLocaleString()}
                </span>
              </div>
            )}

            {status?.restartCount != null && status.restartCount > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium">{t("settings.sidecar.restarts")}</span>
                <span className="text-warning text-sm">
                  {status.restartCount} {t("settings.sidecar.autoRestartSuffix")}
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
              disabled={isRestartDisabled}
              variant="outline"
              className="gap-2"
            >
              <RefreshCwIcon className={`size-4 ${restarting ? "animate-spin" : ""}`} />
              {restarting
                ? t("settings.sidecar.restarting")
                : t("settings.sidecar.restartSidecar")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-md shadow-none">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{t("settings.sidecar.logs")}</CardTitle>
              <CardDescription>{t("settings.sidecar.logsDescription")}</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => void handleCopyLogs()}
              disabled={logs.length === 0}
            >
              <CopyIcon className="size-3" />
              {copied ? t("settings.sidecar.copied") : t("settings.sidecar.copy")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-64 w-full rounded-md border">
            <div
              ref={logScrollRef}
              className="bg-muted/50 p-3 font-mono text-xs leading-relaxed"
            >
              {logs.length === 0 ? (
                <span className="text-muted-foreground">{t("settings.sidecar.noLogs")}</span>
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
