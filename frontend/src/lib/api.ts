// SPDX-License-Identifier: AGPL-3.0-or-later
import type {
  HealthzResponse,
  TranslateRequest,
  TranslateResponse,
  TranslationsManifest,
} from "@/types/api";

/**
 * Fixed dev-mode base for the Python sidecar.
 *
 * In dev (Vite), `/api/*` is proxied to `http://localhost:8765/*` (see
 * `vite.config.ts`). The Electron production wrapper (Phase 3) will inject
 * the random port the sidecar reports via `SIDECAR_READY port=<N>` and the
 * renderer will read it from `window.__XREAD_API__`.
 */
export const apiBase: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

/**
 * Base for the WebSocket proxy. Vite proxies `/ws/*` to
 * `ws://localhost:8765/*` (see `vite.config.ts`). Phase 3 will mirror
 * `apiBase`'s injection mechanism.
 */
export const wsBase: string =
  (import.meta.env.VITE_WS_BASE as string | undefined) ??
  // Default: resolve relative to the current origin. The Vite proxy handles
  // the actual upgrade to `ws://localhost:8765` in dev mode.
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`
    : "ws://localhost:5173");

export class ApiError extends Error {
  override readonly name = "ApiError";
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    throw new ApiError(
      `Network error contacting sidecar at ${url}: ${(cause as Error).message}`,
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(`Sidecar returned ${response.status} on ${path}`, response.status);
  }

  return (await response.json()) as T;
}

export async function getHealthz(): Promise<HealthzResponse> {
  return request<HealthzResponse>("/healthz");
}

/**
 * Fetch the translations manifest for a given workspace.
 *
 * Returns an empty manifest on 404 — the workspace may simply have no
 * translations yet, which is the steady-state for a freshly-ingested wiki.
 * Other non-2xx statuses surface as `ApiError`.
 */
export async function getTranslationsManifest(
  workspacePath: string,
): Promise<TranslationsManifest> {
  const url = `${apiBase}/translations/manifest?workspacePath=${encodeURIComponent(
    workspacePath,
  )}`;
  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" } });
  } catch (cause) {
    throw new ApiError(
      `Network error contacting sidecar at ${url}: ${(cause as Error).message}`,
      0,
    );
  }
  if (response.status === 404) {
    return { version: 1, entries: [] };
  }
  if (!response.ok) {
    throw new ApiError(
      `Sidecar returned ${response.status} on /translations/manifest`,
      response.status,
    );
  }
  return (await response.json()) as TranslationsManifest;
}

/**
 * Build the URL that resolves to a PDF file on disk inside the given
 * workspace. The backend serves these via the same `/translations/file`
 * (or `/raw/file`) routes that ship with the static-file mount.
 *
 * `relativePath` is the workspace-relative POSIX path stored on the
 * manifest (`translations/<slug>.dual.pdf` or `raw/<source>.pdf`).
 */
export function buildWorkspaceFileUrl(workspacePath: string, relativePath: string): string {
  const params = new URLSearchParams({
    workspacePath,
    path: relativePath,
  });
  return `${apiBase}/workspaces/file?${params.toString()}`;
}

/** Start a translation job. Returns the new `jobId` on success. */
export async function postTranslate(req: TranslateRequest): Promise<TranslateResponse> {
  return request<TranslateResponse>("/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/** Build the WS URL for streaming events of `jobId`. */
export function buildJobEventsWsUrl(jobId: string): string {
  return `${wsBase}/ws/jobs/${encodeURIComponent(jobId)}`;
}
