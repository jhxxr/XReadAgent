// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CopilotSidebar } from "@/components/shell/copilot-sidebar";
import { ThemeProvider } from "@/lib/theme";

vi.mock("@/lib/api", () => ({
  postQuery: vi.fn(),
}));

vi.mock("@/lib/workspace", () => ({
  readWorkspacePath: vi.fn(() => "/test/workspace"),
}));

function renderCopilot() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  return render(
    <ThemeProvider defaultTheme="light">
      <QueryClientProvider client={queryClient}>
        <CopilotSidebar />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

describe("CopilotSidebar", () => {
  it("renders the floating trigger button", () => {
    renderCopilot();
    const trigger = screen.getByTestId("copilot-trigger");
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-label", "Open copilot");
  });

  it("opens the sidebar panel when trigger is clicked", async () => {
    const user = userEvent.setup();
    renderCopilot();

    const trigger = screen.getByTestId("copilot-trigger");
    await user.click(trigger);

    expect(screen.getByTestId("copilot-sidebar")).toHaveClass("translate-x-0");
    expect(screen.getByText("Ask about your wiki")).toBeInTheDocument();
  });

  it("closes the sidebar when close button is clicked", async () => {
    const user = userEvent.setup();
    renderCopilot();

    // Open
    await user.click(screen.getByTestId("copilot-trigger"));
    expect(screen.getByTestId("copilot-sidebar")).toHaveClass("translate-x-0");

    // Close
    await user.click(screen.getByRole("button", { name: "Close copilot" }));
    expect(screen.getByTestId("copilot-sidebar")).toHaveClass("translate-x-full");
  });

  it("shows the empty state message when no messages exist", async () => {
    const user = userEvent.setup();
    renderCopilot();

    await user.click(screen.getByTestId("copilot-trigger"));

    expect(screen.getByText("Ask about your wiki")).toBeInTheDocument();
    expect(
      screen.getByText(/type a question below to search your ingested documents/i),
    ).toBeInTheDocument();
  });

  it("renders the input field and send button", async () => {
    const user = userEvent.setup();
    renderCopilot();

    await user.click(screen.getByTestId("copilot-trigger"));

    expect(screen.getByPlaceholderText("Ask a question...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send question" })).toBeInTheDocument();
  });
});
