// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * pdf.js worker bootstrap.
 *
 * Loaded eagerly by `PdfViewer` so the worker URL is registered with
 * pdfjs-dist before any `getDocument(...)` call. Vite's `?url` import
 * resolves to a hashed URL string under `/assets/...` in the production
 * build and to a dev-server URL in dev mode.
 */
import { GlobalWorkerOptions } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

let configured = false;

/**
 * Idempotent worker init. Safe to call from every viewer mount — only the
 * first call wires the worker URL into the pdfjs-dist module.
 */
export function ensurePdfWorker(): void {
  if (configured) return;
  GlobalWorkerOptions.workerSrc = workerSrc;
  configured = true;
}
