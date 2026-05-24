// SPDX-License-Identifier: AGPL-3.0-or-later
import { useQuery } from "@tanstack/react-query";
import { AlertTriangleIcon, CheckCircle2Icon, Loader2Icon } from "lucide-react";

import { ApiError, getHealthz } from "@/lib/api";
import { cn } from "@/lib/utils";

interface BannerState {
  tone: "ok" | "error" | "loading";
  label: string;
  hint: string;
}

function selectState({
  isPending,
  isError,
  error,
  version,
}: {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  version: string | undefined;
}): BannerState {
  if (isPending) {
    return {
      tone: "loading",
      label: "Connecting to sidecar",
      hint: "Polling /healthz on the Python backend.",
    };
  }
  if (isError) {
    const detail =
      error instanceof ApiError
        ? error.message
        : error instanceof Error
          ? error.message
          : "Unknown error";
    return {
      tone: "error",
      label: "Sidecar unreachable",
      hint: detail,
    };
  }
  return {
    tone: "ok",
    label: "Sidecar ready",
    hint: version ? `xreadagent v${version}` : "Connected.",
  };
}

export function HealthBanner() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["healthz"],
    queryFn: getHealthz,
    refetchInterval: 5_000,
    retry: false,
  });

  const state = selectState({ isPending, isError, error, version: data?.version });

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="health-banner"
      data-tone={state.tone}
      className={cn(
        "flex items-center gap-2 border-b px-4 py-1.5 text-xs",
        state.tone === "ok" && "border-success/30 bg-success/10 text-success",
        state.tone === "error" && "border-destructive/30 bg-destructive/10 text-destructive",
        state.tone === "loading" && "border-border bg-muted text-muted-foreground",
      )}
    >
      {state.tone === "ok" && <CheckCircle2Icon className="size-3.5" />}
      {state.tone === "error" && <AlertTriangleIcon className="size-3.5" />}
      {state.tone === "loading" && <Loader2Icon className="size-3.5 animate-spin" />}
      <span className="font-medium">{state.label}</span>
      <span className="text-muted-foreground/90 truncate">{state.hint}</span>
    </div>
  );
}
