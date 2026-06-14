// SPDX-License-Identifier: AGPL-3.0-or-later
import type {
  AppSettings,
  BuildWikiRequest,
  CreateWorkspaceRequest,
  CreateWorkspaceResponse,
  HealthzResponse,
  IngestRequest,
  IngestJobResponse,
  PaperSummary,
  ConceptSummary,
  FetchModelsRequest,
  FetchModelsResponse,
  QuerySummary,
  QueryRequest,
  QueryResultResponse,
  RegisterRequest,
  SourceSummary,
  TestModelRequest,
  TestModelResponse,
  TranslateRequest,
  TranslateResponse,
  TranslationsManifest,
  UpdateSettingsRequest,
  WikiPageResponse,
} from "@/types/api";
import { getApiBaseUrl, getWsBaseUrl, getSidecarBaseUrl } from "@/lib/platform";

/**
 * Base URL for all HTTP API calls to the Python sidecar.
 *
 * Resolved dynamically so that Electron production mode (direct `127.0.0.1`
 * connection) and browser dev mode (Vite proxy) both work without code
 * changes. Prefer `getApiBaseUrl()` from `platform.ts` for new code.
 */
export function getApiBase(): string {
  return (import.meta.env.VITE_API_BASE as string | undefined) ?? getApiBaseUrl();
}

/**
 * Base URL for WebSocket connections to the Python sidecar.
 *
 * In browser dev mode this resolves to `ws://localhost:{vitePort}` (Vite
 * proxies the upgrade). In Electron it resolves to `ws://127.0.0.1:{port}`.
 */
export function getWsBase(): string {
  return (import.meta.env.VITE_WS_BASE as string | undefined) ?? getWsBaseUrl();
}

export class ApiError extends Error {
  override readonly name = "ApiError";
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatDetailValue(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }
  if (Array.isArray(value)) {
    const messages = value
      .map((item) => (isRecord(item) && typeof item.msg === "string" ? item.msg : null))
      .filter((message): message is string => Boolean(message?.trim()));
    return messages.length > 0 ? messages.join("; ") : null;
  }
  if (isRecord(value)) {
    const message = value.message ?? value.msg ?? value.error;
    return typeof message === "string" ? message.trim() || null : null;
  }
  return null;
}

async function buildApiError(response: Response, path: string): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const raw = await response.text();
    if (raw.trim()) {
      const body = JSON.parse(raw) as unknown;
      detail = isRecord(body) ? formatDetailValue(body.detail) : formatDetailValue(body);
    }
  } catch {
    detail = null;
  }

  const base = `Sidecar returned ${response.status} on ${path}`;
  return new ApiError(detail ? `${base}: ${detail}` : base, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase();
  const url = `${base}${path}`;
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
    throw await buildApiError(response, path);
  }

  return (await response.json()) as T;
}

/**
 * Fetch the sidecar health check.
 *
 * The `/healthz` endpoint is the only sidecar route NOT under `/api`, so it
 * needs a different base URL from the rest of the API.
 */
export async function getHealthz(): Promise<HealthzResponse> {
  const base = (import.meta.env.VITE_SIDECAR_BASE as string | undefined) ?? getSidecarBaseUrl();
  const url = `${base}/healthz`;
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    throw new ApiError(
      `Network error contacting sidecar at ${url}: ${(cause as Error).message}`,
      0,
    );
  }
  if (!response.ok) {
    throw await buildApiError(response, "/healthz");
  }
  return (await response.json()) as HealthzResponse;
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
  const url = `${getApiBase()}/translations/manifest?workspacePath=${encodeURIComponent(workspacePath)}`;
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
    throw await buildApiError(response, "/translations/manifest");
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
  return `${getApiBase()}/workspaces/file?${params.toString()}`;
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
  return `${getWsBase()}/ws/jobs/${encodeURIComponent(jobId)}`;
}

/**
 * Seed the canonical layout at an (Electron-allocated) workspace path. The
 * directory itself is created by the Electron registry; this endpoint writes
 * the seed wiki files. Idempotent — `created: false` when already initialized.
 */
export async function createWorkspace(
  req: CreateWorkspaceRequest,
): Promise<CreateWorkspaceResponse> {
  return request<CreateWorkspaceResponse>("/workspaces/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Wiki read API
// ---------------------------------------------------------------------------

/** Fetch all papers for a workspace. */
export async function getPapers(workspacePath: string): Promise<PaperSummary[]> {
  return request<PaperSummary[]>(`/wiki/papers?workspacePath=${encodeURIComponent(workspacePath)}`);
}

/** Fetch a single paper page by slug. */
export async function getPaper(workspacePath: string, slug: string): Promise<WikiPageResponse> {
  return request<WikiPageResponse>(
    `/wiki/papers/${encodeURIComponent(slug)}?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch all concepts for a workspace. */
export async function getConcepts(workspacePath: string): Promise<ConceptSummary[]> {
  return request<ConceptSummary[]>(
    `/wiki/concepts?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch a single concept page by slug. */
export async function getConcept(workspacePath: string, slug: string): Promise<WikiPageResponse> {
  return request<WikiPageResponse>(
    `/wiki/concepts/${encodeURIComponent(slug)}?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch all archived queries for a workspace. */
export async function getQueries(workspacePath: string): Promise<QuerySummary[]> {
  return request<QuerySummary[]>(
    `/wiki/queries?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch a single query page by topic and slug. */
export async function getQueryPage(
  workspacePath: string,
  topic: string,
  slug: string,
): Promise<WikiPageResponse> {
  return request<WikiPageResponse>(
    `/wiki/queries/${encodeURIComponent(topic)}/${encodeURIComponent(slug)}?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch the wiki index page content. */
export async function getWikiIndex(workspacePath: string): Promise<{ content: string }> {
  return request<{ content: string }>(
    `/wiki/index?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/** Fetch the wiki overview page content. */
export async function getWikiOverview(workspacePath: string): Promise<{ content: string }> {
  return request<{ content: string }>(
    `/wiki/overview?workspacePath=${encodeURIComponent(workspacePath)}`,
  );
}

/**
 * Start an ingest job for a document. Returns the new `jobId` on success;
 * subscribe to `/ws/jobs/{jobId}` (see `lib/ingest-job.ts`) for progress.
 */
export async function postIngest(req: IngestRequest): Promise<IngestJobResponse> {
  return request<IngestJobResponse>("/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Sources (registered documents) API
// ---------------------------------------------------------------------------

/** List registered documents (from `state/sources.json`) with derived status. */
export async function getSources(workspacePath: string): Promise<SourceSummary[]> {
  return request<SourceSummary[]>(`/sources?workspacePath=${encodeURIComponent(workspacePath)}`);
}

/**
 * Register (convert-only) a document — no LLM, no model. Returns a `jobId`
 * streamed over `/ws/jobs/{jobId}` (only the `converting` stage fires).
 */
export async function postRegister(req: RegisterRequest): Promise<IngestJobResponse> {
  return request<IngestJobResponse>("/sources/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/** Build the wiki page for an already-registered document, by slug. */
export async function postBuildWiki(
  slug: string,
  req: BuildWikiRequest,
): Promise<IngestJobResponse> {
  return request<IngestJobResponse>(`/sources/${encodeURIComponent(slug)}/build`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/** Answer a question using the wiki knowledge base. */
export async function postQuery(req: QueryRequest): Promise<QueryResultResponse> {
  return request<QueryResultResponse>("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

// ---------------------------------------------------------------------------
// Settings API
// ---------------------------------------------------------------------------

/** Fetch current application settings. */
export async function getSettings(): Promise<AppSettings> {
  return request<AppSettings>("/settings");
}

/** Update application settings (partial merge). */
export async function putSettings(req: UpdateSettingsRequest): Promise<AppSettings> {
  return request<AppSettings>("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/**
 * Fetch the model list a provider exposes. Sends an unsaved provider draft so
 * the UI can fetch before persisting; throws {@link ApiError} on failure.
 */
export async function fetchProviderModels(
  req: FetchModelsRequest,
): Promise<FetchModelsResponse> {
  return request<FetchModelsResponse>("/providers/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/**
 * Test that a provider/model is reachable. Returns `{ ok, latencyMs, error }`;
 * a failed round-trip is reported as `ok: false` (HTTP 200), not an exception.
 */
export async function testProviderModel(
  req: TestModelRequest,
): Promise<TestModelResponse> {
  return request<TestModelResponse>("/providers/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}
