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
