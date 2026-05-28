// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "@/lib/theme";
import { PaperIndexRoute } from "@/routes/paper-index";

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

function renderPaperIndex() {
  return render(
    <ThemeProvider defaultTheme="light">
      <PaperIndexRoute />
    </ThemeProvider>,
  );
}

describe("PaperIndexRoute", () => {
  beforeEach(() => {
    stubMatchMedia();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    stubMatchMedia();
  });

  it("renders the Papers card title and description", () => {
    renderPaperIndex();

    expect(screen.getByText("Papers")).toBeInTheDocument();
    expect(
      screen.getByText(/per-source synthesis pages live here/i),
    ).toBeInTheDocument();
  });

  it("renders the explanatory body text about paper-curator template", () => {
    renderPaperIndex();

    expect(screen.getByText(/paper-curator template/i)).toBeInTheDocument();
  });

  it("renders the code reference for paper slug path", () => {
    renderPaperIndex();

    expect(screen.getByText(/papers\/<slug>\.md/i)).toBeInTheDocument();
  });
});