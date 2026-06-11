// SPDX-License-Identifier: AGPL-3.0-or-later
import { buildJobEventsWsUrl, postIngest } from "@/lib/api";
import type {
  IngestFinishEvent,
  IngestJobEvent,
  IngestRequest,
  IngestStageName,
} from "@/types/api";

export interface RunIngestJobOptions {
  /** Called whenever the backend reports a new ingest phase starting. */
  onStage?: (stage: IngestStageName) => void;
  /**
   * Override for tests: provide a WebSocket constructor that does not hit
   * the network. Defaults to the global `WebSocket`. Mirrors the seam the
   * translate dialog exposes.
   */
  websocketFactory?: (url: string) => WebSocket;
}

/**
 * Run an ingest end to end through the job API: `POST /api/ingest` to get a
 * `jobId`, then subscribe to `/ws/jobs/{jobId}` until the terminal event.
 *
 * Resolves with the `finish` event and rejects with an `Error` when the job
 * reports `error`, the socket fails, or the stream closes before a terminal
 * event — so callers (the TanStack mutation in `use-workspace-actions.ts`)
 * stay "in flight" for the whole job, not just the initial POST.
 */
export async function runIngestJob(
  req: IngestRequest,
  options: RunIngestJobOptions = {},
): Promise<IngestFinishEvent> {
  const { jobId } = await postIngest(req);
  const factory = options.websocketFactory ?? ((url: string) => new WebSocket(url));

  return new Promise<IngestFinishEvent>((resolve, reject) => {
    const socket = factory(buildJobEventsWsUrl(jobId));
    let settled = false;
    const settle = (complete: () => void) => {
      if (settled) return;
      settled = true;
      complete();
      socket.close();
    };

    socket.addEventListener("message", (event: MessageEvent<string>) => {
      let payload: IngestJobEvent;
      try {
        payload = JSON.parse(event.data) as IngestJobEvent;
      } catch {
        // The backend strictly serializes events through Pydantic, so a
        // malformed frame should never happen; ignore rather than fail the job.
        return;
      }
      if (payload.type === "stage_start") {
        options.onStage?.(payload.stage);
      } else if (payload.type === "finish") {
        settle(() => {
          resolve(payload);
        });
      } else if (payload.type === "error") {
        settle(() => {
          reject(new Error(payload.message));
        });
      }
    });
    socket.addEventListener("error", () => {
      settle(() => {
        reject(new Error("Lost connection to the import job"));
      });
    });
    socket.addEventListener("close", () => {
      settle(() => {
        reject(new Error("Import stream closed before the job finished"));
      });
    });
  });
}
