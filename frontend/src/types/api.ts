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
export type TranslationEvent =
  | StageEvent
  | ModelDownloadEvent
  | FinishEvent
  | ErrorEvent;
