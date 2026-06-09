// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { ThemeProvider } from "@/lib/theme";
import { ConceptRoute } from "@/routes/concept";

/** Re-install the matchMedia stub that afterEach/restoreAllMocks tears down. */
function stubMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

vi.mock("@/lib/workspace", () => ({
  readWorkspacePath: vi.fn(() => "/tmp/test-workspace"),
}));

const MOCK_CONCEPT = {
  slug: "test-concept",
  content: "This is the concept body.",
  frontmatter: {
    title: "Test Concept Title",
    aliases: ["alias-one", "alias-two"],
  },
  sourcePath: null,
  sourceKind: "",
};

function renderConcept() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  const rootRoute = createRootRoute();
  const conceptRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/concept/$slug",
    component: ConceptRoute,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([conceptRoute]),
    history: createMemoryHistory({ initialEntries: ["/concept/test-concept"] }),
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("ConceptRoute", () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubMatchMedia();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    stubMatchMedia();
  });

  it("renders the concept title and slug after loading", async () => {
    vi.spyOn(api, "getConcept").mockResolvedValue(MOCK_CONCEPT);

    renderConcept();

    expect(await screen.findByText("Test Concept Title")).toBeInTheDocument();
    expect(screen.getByText("test-concept")).toBeInTheDocument();
  });

  it("renders concept aliases from frontmatter", async () => {
    vi.spyOn(api, "getConcept").mockResolvedValue(MOCK_CONCEPT);

    renderConcept();

    expect(await screen.findByText(/alias-one, alias-two/)).toBeInTheDocument();
  });

  it("renders the concept badge", async () => {
    vi.spyOn(api, "getConcept").mockResolvedValue(MOCK_CONCEPT);

    renderConcept();

    expect(await screen.findByText("concept")).toBeInTheDocument();
  });

  it("renders the concept body content", async () => {
    vi.spyOn(api, "getConcept").mockResolvedValue(MOCK_CONCEPT);

    renderConcept();

    expect(await screen.findByText("This is the concept body.")).toBeInTheDocument();
  });

  it("shows an error state when the API call fails", async () => {
    vi.spyOn(api, "getConcept").mockRejectedValue(new Error("Network error"));

    renderConcept();

    expect(await screen.findByText(/failed to load concept/i)).toBeInTheDocument();
  });
});
