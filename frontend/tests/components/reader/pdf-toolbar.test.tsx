// SPDX-License-Identifier: AGPL-3.0-or-later
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { PdfToolbar, ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from "@/components/reader/pdf-toolbar";

function renderWithTooltip(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("PdfToolbar", () => {
  const defaultProps = {
    zoom: 100,
    onZoomChange: vi.fn(),
    currentPage: 1,
    totalPages: 10,
    onNavigateToPage: vi.fn(),
    isLoading: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders zoom controls and page navigation", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} />);

    expect(screen.getByLabelText("Zoom out")).toBeInTheDocument();
    expect(screen.getByLabelText("Zoom in")).toBeInTheDocument();
    expect(screen.getByLabelText("Fit width")).toBeInTheDocument();
    expect(screen.getByLabelText("Reset zoom")).toBeInTheDocument();
    expect(screen.getByLabelText("Previous page")).toBeInTheDocument();
    expect(screen.getByLabelText("Next page")).toBeInTheDocument();
  });

  it("displays current zoom percentage", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={150} />);
    expect(screen.getByLabelText("Zoom level: 150%")).toHaveTextContent("150%");
  });

  it("calls onZoomChange when zoom in is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={100} />);
    fireEvent.click(screen.getByLabelText("Zoom in"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(100 + ZOOM_STEP);
  });

  it("calls onZoomChange when zoom out is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={100} />);
    fireEvent.click(screen.getByLabelText("Zoom out"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(100 - ZOOM_STEP);
  });

  it("disables zoom in at max zoom", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={ZOOM_MAX} />);
    expect(screen.getByLabelText("Zoom in")).toBeDisabled();
  });

  it("disables zoom out at min zoom", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={ZOOM_MIN} />);
    expect(screen.getByLabelText("Zoom out")).toBeDisabled();
  });

  it("clamps zoom in at max zoom level", () => {
    const onZoomChange = vi.fn();
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={290} onZoomChange={onZoomChange} />);
    fireEvent.click(screen.getByLabelText("Zoom in"));
    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_MAX);
  });

  it("clamps zoom out at min zoom level", () => {
    const onZoomChange = vi.fn();
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={60} onZoomChange={onZoomChange} />);
    fireEvent.click(screen.getByLabelText("Zoom out"));
    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_MIN);
  });

  it("calls onZoomChange with default when fit width is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={200} />);
    fireEvent.click(screen.getByLabelText("Fit width"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT);
  });

  it("calls onZoomChange with default when reset is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={200} />);
    fireEvent.click(screen.getByLabelText("Reset zoom"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT);
  });

  it("disables reset when already at default zoom", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={ZOOM_DEFAULT} />);
    expect(screen.getByLabelText("Reset zoom")).toBeDisabled();
  });

  it("displays current page number and total", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={5} totalPages={20} />);
    // The input shows the current page number.
    const input = screen.getByLabelText("Page number, 5 of 20");
    expect(input).toHaveValue("5");
    // The total pages is displayed as text.
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("navigates to next page when next button is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={3} totalPages={10} />);
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(4);
  });

  it("navigates to previous page when prev button is clicked", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={3} totalPages={10} />);
    fireEvent.click(screen.getByLabelText("Previous page"));
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(2);
  });

  it("disables previous page button on page 1", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={1} totalPages={10} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });

  it("disables next page button on last page", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={10} totalPages={10} />);
    expect(screen.getByLabelText("Next page")).toBeDisabled();
  });

  it("allows page navigation via input field", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={1} totalPages={10} />);
    const input = screen.getByLabelText("Page number, 1 of 10");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(7);
  });

  it("resets input on invalid page number", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={5} totalPages={10} />);
    const input = screen.getByLabelText("Page number, 5 of 10");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "99" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // Should not navigate; input resets to current page on blur.
    expect(defaultProps.onNavigateToPage).not.toHaveBeenCalled();
  });

  it("disables all controls when loading", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} isLoading={true} />);
    expect(screen.getByLabelText("Zoom in")).toBeDisabled();
    expect(screen.getByLabelText("Zoom out")).toBeDisabled();
    expect(screen.getByLabelText("Fit width")).toBeDisabled();
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
    expect(screen.getByLabelText("Next page")).toBeDisabled();
  });

  it("shows rendering indicator when isRendering is true", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} isRendering={true} />);
    expect(screen.getByText(/Rendering\.\.\./)).toBeInTheDocument();
  });

  it("shows large document indicator when isRendering and isLargeDocument are true", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} isRendering={true} isLargeDocument={true} />);
    expect(screen.getByText(/Rendering large document\.\.\./)).toBeInTheDocument();
  });

  it("does not show rendering indicator when isRendering is false", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} isRendering={false} />);
    expect(screen.queryByText(/Rendering/)).not.toBeInTheDocument();
  });

  it("does not disable controls when isRendering is true", () => {
    renderWithTooltip(
      <PdfToolbar {...defaultProps} isRendering={true} currentPage={5} totalPages={10} />,
    );
    expect(screen.getByLabelText("Zoom in")).not.toBeDisabled();
    expect(screen.getByLabelText("Zoom out")).not.toBeDisabled();
    expect(screen.getByLabelText("Previous page")).not.toBeDisabled();
    expect(screen.getByLabelText("Next page")).not.toBeDisabled();
  });

  it("wraps zoom in button in tooltip trigger", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} />);
    // Radix TooltipTrigger sets data-state on the trigger element (with asChild).
    const zoomInButton = screen.getByLabelText("Zoom in");
    expect(zoomInButton).toHaveAttribute("data-state", "closed");
  });

  it("wraps zoom out button in tooltip trigger", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} />);
    const zoomOutButton = screen.getByLabelText("Zoom out");
    expect(zoomOutButton).toHaveAttribute("data-state", "closed");
  });

  it("wraps reset zoom button in tooltip trigger", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} zoom={200} />);
    const resetButton = screen.getByLabelText("Reset zoom");
    expect(resetButton).toHaveAttribute("data-state", "closed");
  });

  it("wraps previous page button in tooltip trigger", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={2} />);
    const prevButton = screen.getByLabelText("Previous page");
    expect(prevButton).toHaveAttribute("data-state", "closed");
  });

  it("wraps next page button in tooltip trigger", () => {
    renderWithTooltip(<PdfToolbar {...defaultProps} currentPage={1} totalPages={10} />);
    const nextButton = screen.getByLabelText("Next page");
    expect(nextButton).toHaveAttribute("data-state", "closed");
  });
});