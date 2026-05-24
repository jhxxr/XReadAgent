// SPDX-License-Identifier: AGPL-3.0-or-later
import type { HealthzResponse } from "@/types/api";

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
