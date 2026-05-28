// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/lib/theme";
import { QueriesRoute } from "@/routes/queries";

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

function renderQueries() {
  return render(
    <ThemeProvider defaultTheme="light">
      <QueriesRoute />
    </ThemeProvider>,
  );
}

describe("QueriesRoute", () => {
  beforeEach(() => {
    stubMatchMedia();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    stubMatchMedia();
  });

  it("renders the Query archive card title and description", () => {
    renderQueries();

    expect(screen.getByText("Query archive")).toBeInTheDocument();
    expect(
      screen.getByText(/answers are isolated from synthesis until you crystallize them/i),
    ).toBeInTheDocument();
  });

  it("renders the explanatory body text about query archiving", () => {
    renderQueries();

    expect(screen.getByText(/each question you ask is archived under/i)).toBeInTheDocument();
  });

  it("renders the crystallize code reference", () => {
    renderQueries();

    expect(screen.getByText(/\/crystallize/)).toBeInTheDocument();
  });

  it("renders code references for isolated directories", () => {
    renderQueries();

    expect(screen.getByText(/^papers\/$/)).toBeInTheDocument();
    expect(screen.getByText(/^concepts\/$/)).toBeInTheDocument();
  });
});