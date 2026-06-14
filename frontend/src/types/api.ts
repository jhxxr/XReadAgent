// SPDX-License-Identifier: AGPL-3.0-or-later

/** Shape of `GET /healthz` on the Python sidecar. */
export interface HealthzResponse {
  status: string;
  version: string;
}

/**
 * Placeholder shape — populated when the wiki/paper endpoint lands in
 * Phase 2. Keep fields aligned with the Pydantic `Paper` schema.
 */
export interface PaperSummary {
  slug: string;
  title: string;
  authors: readonly string[];
  year: number | null;
  /** ISO 8601 UTC timestamp. */
  ingestedAt: string;
  /** Workspace-relative canonical source path, usually `raw/_processed/<slug>.pdf`. */
  sourcePath: string | null;
  /** Source kind from `state/sources.json`, e.g. `pdf` or `office`. */
  sourceKind: string;
}

/**
 * Placeholder shape for concept pages. Phase 2 will wire to the real
 * `concepts/{slug}.md` reader.
 */
export interface ConceptSummary {
  slug: string;
  title: string;
  aliases: readonly string[];
  paperCount: number;
}

/**
 * Placeholder shape for archived queries (`wiki/queries/{topic}/...`).
 * Phase 2 will replace with the real archive payload.
 */
export interface QuerySummary {
  id: string;
  question: string;
  topic: string;
  /** ISO 8601 UTC timestamp. */
  archivedAt: string;
}

/**
 * One row in `translations/manifest.json` — mirrors the Pydantic
 * `TranslationEntry` schema (camelCase) in
 * `backend/src/xreadagent/translation/manifest.py`.
 *
 * Paths are relative to the workspace root (e.g.
 * `translations/attention-aaa.dual.pdf`).
 */
export interface TranslationEntry {
  sourceSlug: string;
  sourceHash: string;
  targetLang: string;
  model: string;
  monoPath: string | null;
  dualPath: string | null;
  /** ISO 8601 UTC timestamp. */
  translatedAt: string;
  durationS: number;
  babeldocVersion: string;
}

/** Top-level container persisted at `translations/manifest.json`. */
export interface TranslationsManifest {
  version: number;
  entries: readonly TranslationEntry[];
}

/**
 * Body of `POST /api/translate` — mirrors the Pydantic `TranslateRequest`
 * schema (camelCase) in `backend/src/xreadagent/api/main.py`.
 */
export interface TranslateRequest {
  workspacePath: string;
  sourcePath: string;
  model: string;
  targetLang?: string;
  sourceLang?: string;
  mono?: boolean;
  dual?: boolean;
  headers?: Record<string, string>;
  maxTokens?: number | null;
  apiKey?: string | null;
  baseUrl?: string | null;
}

export interface TranslateResponse {
  jobId: string;
}

/** Body of `POST /api/workspaces/create`. Mirrors backend `CreateWorkspaceRequest`. */
export interface CreateWorkspaceRequest {
  workspacePath: string;
  title?: string;
}

/** Response of `POST /api/workspaces/create`. */
export interface CreateWorkspaceResponse {
  workspacePath: string;
  title: string;
  created: boolean;
}

/** One registered document with derived status. Mirrors `SourceSummaryResponse`. */
export interface SourceSummary {
  slug: string;
  title: string;
  kind: string;
  sourcePath: string | null;
  ingestedAt: string;
  pageCount: number | null;
  wikiBuilt: boolean;
  translated: boolean;
}

/** Body of `POST /api/sources/register` (convert-only import; no model). */
export interface RegisterRequest {
  workspacePath: string;
  filePath: string;
  title?: string;
}

/** Body of `POST /api/sources/{slug}/build`. */
export interface BuildWikiRequest {
  workspacePath: string;
  model?: string;
}

/**
 * BabelDOC's 13-stage pipeline collapsed onto stable protocol tokens.
 * Mirrors `StageName` in `backend/src/xreadagent/translation/events.py`.
 */
export type StageName =
  | "loading"
  | "parsing"
  | "ocr"
  | "layout"
  | "translation"
  | "typesetting"
  | "rendering"
  | "saving"
  | "finalize";

/** One of `stage_start` / `stage_progress` / `stage_end`. */
export interface StageEvent {
  type: "stage_start" | "stage_progress" | "stage_end";
  stage: StageName;
  page: number | null;
  percent: number | null;
  payload: Record<string, unknown>;
  ts: string;
}

/** Lazy first-run asset download progress events. */
export interface ModelDownloadEvent {
  type: "model_download_start" | "model_download_progress" | "model_download_done";
  asset: string;
  bytes_downloaded: number | null;
  bytes_total: number | null;
  ts: string;
}

/** Terminal success event. */
export interface FinishEvent {
  type: "finish";
  mono_path: string | null;
  dual_path: string | null;
  duration_s: number;
  cached: boolean;
  ts: string;
}

/** Terminal failure event. */
export interface ErrorEvent {
  type: "error";
  stage: string | null;
  message: string;
  traceback_excerpt: string | null;
  ts: string;
}

/** Discriminated union of all WS events the backend pushes. */
export type TranslationEvent = StageEvent | ModelDownloadEvent | FinishEvent | ErrorEvent;

// ---------------------------------------------------------------------------
// Wiki read API types
// ---------------------------------------------------------------------------

/** Response shape for `GET /api/wiki/papers/{slug}` (and concept/query equivalents). */
export interface WikiPageResponse {
  slug: string;
  content: string;
  frontmatter: Record<string, unknown>;
  /** Workspace-relative canonical source path when this page maps to a source row. */
  sourcePath: string | null;
  /** Source kind from `state/sources.json`; empty for pages without source rows. */
  sourceKind: string;
}

/** Body of `POST /api/ingest`. */
export interface IngestRequest {
  workspacePath: string;
  filePath: string;
  title?: string;
  model?: string;
}

/**
 * Response shape for `POST /api/ingest` — the ingest now runs as a background
 * job (same contract as `POST /api/translate`); progress streams over
 * `/ws/jobs/{jobId}`.
 */
export interface IngestJobResponse {
  jobId: string;
}

/**
 * Phase-level ingest pipeline tokens, in execution order. Mirrors
 * `IngestStageName` in `backend/src/xreadagent/api/ingest_jobs.py`.
 */
export type IngestStageName = "converting" | "analyzing" | "writing";

/** One of `stage_start` / `stage_end` for an ingest phase. */
export interface IngestStageEvent {
  type: "stage_start" | "stage_end";
  stage: IngestStageName;
  ts: string;
}

/** Terminal success event for an ingest job. */
export interface IngestFinishEvent {
  type: "finish";
  slug: string;
  title: string;
  cache_hit: boolean;
  files_touched: string[];
  duration_s: number;
  ts: string;
}

/**
 * Discriminated union of all WS events an ingest job pushes. The terminal
 * failure event reuses the translation `ErrorEvent` shape.
 */
export type IngestJobEvent = IngestStageEvent | IngestFinishEvent | ErrorEvent;

/** Body of `POST /api/query`. */
export interface QueryRequest {
  workspacePath: string;
  question: string;
  topic?: string;
  model?: string;
}

/** A single piece of evidence backing a query answer. */
export interface CitedEvidence {
  sourceWikiPath: string;
  quote: string;
  confidence: string;
}

/** Response shape for `POST /api/query`. */
export interface QueryResultResponse {
  question: string;
  answer: string;
  confidence: string;
  sourcesCited: string[];
  /** Structured evidence trail — may be absent if the backend omits it. */
  evidence?: CitedEvidence[];
  queryPagePath: string;
  filesTouched: string[];
  durationS: number;
}

// ---------------------------------------------------------------------------
// Settings API types
// ---------------------------------------------------------------------------

/** Supported renderer UI languages persisted through `/api/settings`. */
export type AppLanguage = "en" | "zh";

/**
 * API wire format a provider speaks. `openai` covers every OpenAI-compatible
 * endpoint; `anthropic` covers the Anthropic Messages API. Mirrors
 * `ProviderFormat` in `backend/src/xreadagent/api/settings.py`.
 */
export type ProviderFormat = "openai" | "anthropic";

/** Features that can each be pointed at a different model. */
export type FeatureName = "ingest" | "query" | "translate";

/** One model offered by a provider. `id` is sent to the API; `name` is a label. */
export interface ModelEntry {
  id: string;
  name: string;
}

/**
 * A configured model provider. Mirrors the Pydantic `Provider` (camelCase)
 * in `backend/src/xreadagent/api/settings.py`. `id` is a stable slug referenced
 * by `ModelRef.providerId`. Provider list order is display order.
 */
export interface Provider {
  id: string;
  name: string;
  format: ProviderFormat;
  baseUrl: string;
  apiKey: string;
  enabled: boolean;
  models: ModelEntry[];
}

/** A pointer to one model of one provider, used for per-feature assignment. */
export interface ModelRef {
  providerId: string;
  modelId: string;
}

/** Per-feature model assignment; `null` means the feature is unassigned. */
export interface FeatureModels {
  ingest: ModelRef | null;
  query: ModelRef | null;
  translate: ModelRef | null;
}

/** Response shape for `GET /api/settings`. */
export interface AppSettings {
  model: string;
  workspacePath: string;
  language: AppLanguage;
  providers: Provider[];
  featureModels: FeatureModels;
}

/** Body of `PUT /api/settings` — partial update. */
export interface UpdateSettingsRequest {
  model?: string;
  workspacePath?: string;
  language?: AppLanguage;
  providers?: Provider[];
  featureModels?: FeatureModels;
}

/** Body of `POST /api/providers/models` — fetch a provider's model list. */
export interface FetchModelsRequest {
  format: ProviderFormat;
  baseUrl: string;
  apiKey?: string;
  headers?: Record<string, string>;
}

/** Response shape for `POST /api/providers/models`. */
export interface FetchModelsResponse {
  models: ModelEntry[];
}

/** Body of `POST /api/providers/test` — verify a model is reachable. */
export interface TestModelRequest {
  format: ProviderFormat;
  baseUrl: string;
  modelId: string;
  apiKey?: string;
  headers?: Record<string, string>;
}

/** Response shape for `POST /api/providers/test`. */
export interface TestModelResponse {
  ok: boolean;
  latencyMs: number | null;
  error: string | null;
}
