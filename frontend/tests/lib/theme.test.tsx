// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ThemeProvider, useTheme } from "@/lib/theme";

function ThemeProbe() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button type="button" onClick={() => setTheme("dark")}>
        go dark
      </button>
      <button type="button" onClick={() => setTheme("light")}>
        go light
      </button>
    </div>
  );
}

describe("ThemeProvider", () => {
  it("toggles the dark class on <html>", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider defaultTheme="light">
        <ThemeProbe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    await act(async () => {
      await user.click(screen.getByText("go dark"));
    });

    expect(screen.getByTestId("resolved").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    await act(async () => {
      await user.click(screen.getByText("go light"));
    });

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
