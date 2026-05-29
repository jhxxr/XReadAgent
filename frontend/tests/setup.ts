// SPDX-License-Identifier: AGPL-3.0-or-later
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// jsdom does not implement matchMedia; install a stub so theme code can
// consult the system preference without throwing.
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

// jsdom does not implement window.scrollTo; TanStack Router's
// scroll-restoration plugin calls it during route mounts in tests.
Object.defineProperty(window, "scrollTo", {
  writable: true,
  configurable: true,
  value: vi.fn(),
});

// jsdom does not implement ResizeObserver; PdfViewer uses it to track
// container width for fit-width calculations.
class ResizeObserverMock {
  constructor(_callback: ResizeObserverCallback) {
    // callback is intentionally unused in test mock
  }
  observe(): void {
    // no-op in tests
  }
  unobserve(): void {
    // no-op in tests
  }
  disconnect(): void {
    // no-op in tests
  }
}

Object.defineProperty(window, "ResizeObserver", {
  writable: true,
  configurable: true,
  value: ResizeObserverMock,
});

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
});

afterEach(() => {
  cleanup();
});
