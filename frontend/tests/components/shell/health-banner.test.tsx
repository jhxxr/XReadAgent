// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HealthBanner } from "@/components/shell/health-banner";
import { ThemeProvider } from "@/lib/theme";

// vi.hoisted ensures the mock function is available during vi.mock factory
// execution (factories are hoisted above top-level const declarations).
const { mockGetHealthz } = vi.hoisted(() => ({
  mockGetHealthz: vi.fn().mockResolvedValue({ status: "ok", version: "0.1.0" }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  // eslint-disable-next-line @typescript-eslint/consistent-type-imports -- vi.mock factory cannot use type-only import syntax
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getHealthz: mockGetHealthz,
  };
});

/** Install the matchMedia stub required by ThemeProvider. */
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

function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <HealthBanner />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("HealthBanner", () => {
  beforeEach(() => {
    window.localStorage.clear();
    stubMatchMedia();
    // Reset to the default happy-path mock before each test.
    mockGetHealthz.mockResolvedValue({ status: "ok", version: "0.1.0" });
  });

  it("renders the ok state when the sidecar is healthy", async () => {
    renderBanner();

    expect(await screen.findByText("Sidecar ready")).toBeInTheDocument();
    expect(screen.getByText(/xreadagent v0\.1\.0/)).toBeInTheDocument();
  });

  it("renders the error state when the sidecar is unreachable", async () => {
    mockGetHealthz.mockRejectedValue(new Error("Network error"));

    renderBanner();

    expect(await screen.findByText("Sidecar unreachable")).toBeInTheDocument();
  });

  it("has role=status for accessibility", async () => {
    renderBanner();

    const banner = await screen.findByRole("status");
    expect(banner).toBeInTheDocument();
  });

  it("has data-testid=health-banner", async () => {
    renderBanner();

    const banner = await screen.findByTestId("health-banner");
    expect(banner).toBeInTheDocument();
  });

  it("sets data-tone=ok when sidecar is healthy", async () => {
    renderBanner();

    await waitFor(() => {
      expect(screen.getByTestId("health-banner")).toHaveAttribute("data-tone", "ok");
    });
  });

  it("sets data-tone=error when sidecar is unreachable", async () => {
    mockGetHealthz.mockRejectedValue(new Error("Network error"));

    renderBanner();

    await waitFor(() => {
      expect(screen.getByTestId("health-banner")).toHaveAttribute("data-tone", "error");
    });
  });
});