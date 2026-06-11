// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  buildJobEventsWsUrl,
  buildWorkspaceFileUrl,
  getConcept,
  getConcepts,
  getHealthz,
  getPaper,
  getPapers,
  getQueries,
  getQueryPage,
  getSettings,
  getTranslationsManifest,
  postIngest,
  postQuery,
  postTranslate,
  putSettings,
} from "@/lib/api";

async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    if (error instanceof ApiError) {
      return error;
    }
    throw error;
  }
  throw new Error("Expected API call to reject with ApiError");
}

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses a healthz response", async () => {
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok", version: "0.0.1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getHealthz();

    expect(result).toEqual({ status: "ok", version: "0.0.1" });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/healthz$/);
    expect(init?.headers).toEqual(expect.objectContaining({ Accept: "application/json" }));
  });

  it("throws an ApiError on non-2xx responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("nope", { status: 503 }));

    const error = await expectApiError(getHealthz());
    expect(error.message).toBe("Sidecar returned 503 on /healthz");
    expect(error.status).toBe(503);
  });

  it("includes FastAPI detail text in ApiError messages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: "No model specified. Pass `model` in the request body, configure it in settings.",
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const error = await expectApiError(
      postIngest({
        workspacePath: "/tmp/ws",
        filePath: "/tmp/paper.pdf",
      }),
    );
    expect(error.name).toBe("ApiError");
    expect(error.message).toContain("No model specified");
    expect(error.status).toBe(422);
  });

  it("formats FastAPI validation detail arrays in ApiError messages", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail: [
            { loc: ["body", "workspacePath"], msg: "Field required", type: "missing" },
            { loc: ["body", "filePath"], msg: "Field required", type: "missing" },
          ],
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const error = await expectApiError(
      postIngest({
        workspacePath: "",
        filePath: "",
      }),
    );
    expect(error.message).toContain("Field required; Field required");
    expect(error.status).toBe(422);
  });

  it("wraps network errors as ApiError with status 0", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(getHealthz()).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
    });
  });

  it("fetches the translations manifest", async () => {
    const manifest = {
      version: 1,
      entries: [
        {
          sourceSlug: "alpha-aaaaaaaaaaaa",
          sourceHash: "h1",
          targetLang: "zh",
          model: "anthropic:claude-3-7-sonnet-latest",
          monoPath: "translations/alpha-aaaaaaaaaaaa.mono.pdf",
          dualPath: "translations/alpha-aaaaaaaaaaaa.dual.pdf",
          translatedAt: "2026-05-25T10:00:00Z",
          durationS: 12.5,
          babeldocVersion: "0.6.2",
        },
      ],
    };
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(manifest), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getTranslationsManifest("/tmp/ws");
    expect(result).toEqual(manifest);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/translations\/manifest\?workspacePath=/);
  });

  it("returns an empty manifest on 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("missing", { status: 404 }));

    const result = await getTranslationsManifest("/tmp/ws");
    expect(result).toEqual({ version: 1, entries: [] });
  });

  it("posts /translate and returns the jobId", async () => {
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ jobId: "job-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await postTranslate({
      workspacePath: "/tmp/ws",
      sourcePath: "/tmp/ws/raw/alpha.pdf",
      model: "anthropic:claude-3-7-sonnet-latest",
    });
    expect(result).toEqual({ jobId: "job-1" });
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/translate$/);
    expect(init?.method).toBe("POST");
  });

  it("builds workspace file URLs that encode the path", () => {
    const url = buildWorkspaceFileUrl("/tmp/ws", "translations/alpha.dual.pdf");
    expect(url).toContain("/workspaces/file?");
    expect(url).toContain("workspacePath=%2Ftmp%2Fws");
    expect(url).toContain("path=translations%2Falpha.dual.pdf");
  });

  it("builds a job-events WS URL keyed on the job id", () => {
    const url = buildJobEventsWsUrl("job-1");
    expect(url).toMatch(/\/ws\/jobs\/job-1$/);
  });

  // ---------------------------------------------------------------------------
  // Wiki read API
  // ---------------------------------------------------------------------------

  it("fetches papers list", async () => {
    const papers = [
      {
        slug: "attention-aaa",
        title: "Attention Is All You Need",
        authors: ["Vaswani"],
        year: 2017,
        ingestedAt: "2026-05-27T00:00:00Z",
        sourcePath: "raw/_processed/attention-aaa.pdf",
        sourceKind: "pdf",
      },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(papers), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getPapers("/tmp/ws");
    expect(result).toEqual(papers);
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(call).toBeDefined();
    const [url] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/wiki\/papers\?workspacePath=/);
  });

  it("fetches a single paper page", async () => {
    const page = {
      slug: "attention-aaa",
      content: "# Hello",
      frontmatter: { title: "Hello" },
      sourcePath: "raw/_processed/attention-aaa.pdf",
      sourceKind: "pdf",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(page), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getPaper("/tmp/ws", "attention-aaa");
    expect(result).toEqual(page);
  });

  it("fetches concepts list", async () => {
    const concepts = [
      { slug: "self-attention", title: "Self-Attention", aliases: [], paperCount: 1 },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(concepts), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getConcepts("/tmp/ws");
    expect(result).toEqual(concepts);
  });

  it("fetches a single concept page", async () => {
    const page = {
      slug: "self-attention",
      content: "# Self-Attention",
      frontmatter: { title: "Self-Attention" },
      sourcePath: null,
      sourceKind: "",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(page), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getConcept("/tmp/ws", "self-attention");
    expect(result).toEqual(page);
  });

  it("fetches queries list", async () => {
    const queries = [
      {
        id: "general/what-is-attention",
        question: "What is attention?",
        topic: "general",
        archivedAt: "2026-05-27T00:00:00Z",
      },
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(queries), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getQueries("/tmp/ws");
    expect(result).toEqual(queries);
  });

  it("fetches a single query page", async () => {
    const page = {
      slug: "general/what-is-attention",
      content: "# Answer",
      frontmatter: { question: "What is attention?" },
      sourcePath: null,
      sourceKind: "",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(page), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await getQueryPage("/tmp/ws", "general", "what-is-attention");
    expect(result).toEqual(page);
  });

  it("posts /ingest and returns the job id", async () => {
    const jobResponse = { jobId: "ingest-job-1" };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(jobResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await postIngest({
      workspacePath: "/tmp/ws",
      filePath: "/tmp/ws/raw/paper.pdf",
      model: "anthropic:claude-fake",
    });
    expect(result).toEqual(jobResponse);
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(call).toBeDefined();
    const [, init] = call!;
    expect(init?.method).toBe("POST");
  });

  it("posts /query and returns the result", async () => {
    const queryResult = {
      question: "What?",
      answer: "A mechanism.",
      confidence: "high",
      sourcesCited: [],
      queryPagePath: "",
      filesTouched: [],
      durationS: 0.5,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(queryResult), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await postQuery({
      workspacePath: "/tmp/ws",
      question: "What?",
      model: "anthropic:claude-fake",
    });
    expect(result).toEqual(queryResult);
    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(call).toBeDefined();
    const [, init] = call!;
    expect(init?.method).toBe("POST");
  });

  // ---------------------------------------------------------------------------
  // Settings API
  // ---------------------------------------------------------------------------

  it("fetches current settings via GET /settings", async () => {
    const settings = { model: "openai:gpt-4o", workspacePath: "/tmp/ws", language: "zh" };
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(settings), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getSettings();
    expect(result).toEqual(settings);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/settings$/);
    expect(init?.method).toBeUndefined(); // GET has no method set
  });

  it("updates settings via PUT /settings", async () => {
    const saved = {
      model: "anthropic:claude-3-7-sonnet-latest",
      workspacePath: "/new/ws",
      language: "zh",
    };
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(saved), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await putSettings({
      model: "anthropic:claude-3-7-sonnet-latest",
      language: "zh",
    });
    expect(result).toEqual(saved);
    const call = mockFetch.mock.calls[0];
    expect(call).toBeDefined();
    const [url, init] = call!;
    const urlText = typeof url === "string" ? url : url instanceof URL ? url.toString() : "";
    expect(urlText).toMatch(/\/settings$/);
    expect(init?.method).toBe("PUT");
  });
});
