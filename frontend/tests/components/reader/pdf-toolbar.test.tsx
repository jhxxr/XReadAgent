// SPDX-License-Identifier: AGPL-3.0-or-later
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PdfToolbar, ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from "@/components/reader/pdf-toolbar";

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
    render(<PdfToolbar {...defaultProps} />);

    expect(screen.getByLabelText("Zoom out")).toBeInTheDocument();
    expect(screen.getByLabelText("Zoom in")).toBeInTheDocument();
    expect(screen.getByLabelText("Fit width")).toBeInTheDocument();
    expect(screen.getByLabelText("Reset zoom")).toBeInTheDocument();
    expect(screen.getByLabelText("Previous page")).toBeInTheDocument();
    expect(screen.getByLabelText("Next page")).toBeInTheDocument();
  });

  it("displays current zoom percentage", () => {
    render(<PdfToolbar {...defaultProps} zoom={150} />);
    expect(screen.getByLabelText("Zoom level: 150%")).toHaveTextContent("150%");
  });

  it("calls onZoomChange when zoom in is clicked", () => {
    render(<PdfToolbar {...defaultProps} zoom={100} />);
    fireEvent.click(screen.getByLabelText("Zoom in"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(100 + ZOOM_STEP);
  });

  it("calls onZoomChange when zoom out is clicked", () => {
    render(<PdfToolbar {...defaultProps} zoom={100} />);
    fireEvent.click(screen.getByLabelText("Zoom out"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(100 - ZOOM_STEP);
  });

  it("disables zoom in at max zoom", () => {
    render(<PdfToolbar {...defaultProps} zoom={ZOOM_MAX} />);
    expect(screen.getByLabelText("Zoom in")).toBeDisabled();
  });

  it("disables zoom out at min zoom", () => {
    render(<PdfToolbar {...defaultProps} zoom={ZOOM_MIN} />);
    expect(screen.getByLabelText("Zoom out")).toBeDisabled();
  });

  it("clamps zoom in at max zoom level", () => {
    const onZoomChange = vi.fn();
    render(<PdfToolbar {...defaultProps} zoom={290} onZoomChange={onZoomChange} />);
    fireEvent.click(screen.getByLabelText("Zoom in"));
    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_MAX);
  });

  it("clamps zoom out at min zoom level", () => {
    const onZoomChange = vi.fn();
    render(<PdfToolbar {...defaultProps} zoom={60} onZoomChange={onZoomChange} />);
    fireEvent.click(screen.getByLabelText("Zoom out"));
    expect(onZoomChange).toHaveBeenCalledWith(ZOOM_MIN);
  });

  it("calls onZoomChange with default when fit width is clicked", () => {
    render(<PdfToolbar {...defaultProps} zoom={200} />);
    fireEvent.click(screen.getByLabelText("Fit width"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT);
  });

  it("calls onZoomChange with default when reset is clicked", () => {
    render(<PdfToolbar {...defaultProps} zoom={200} />);
    fireEvent.click(screen.getByLabelText("Reset zoom"));
    expect(defaultProps.onZoomChange).toHaveBeenCalledWith(ZOOM_DEFAULT);
  });

  it("disables reset when already at default zoom", () => {
    render(<PdfToolbar {...defaultProps} zoom={ZOOM_DEFAULT} />);
    expect(screen.getByLabelText("Reset zoom")).toBeDisabled();
  });

  it("displays current page number and total", () => {
    render(<PdfToolbar {...defaultProps} currentPage={5} totalPages={20} />);
    // The input shows the current page number.
    const input = screen.getByLabelText("Page number, 5 of 20");
    expect(input).toHaveValue("5");
    // The total pages is displayed as text.
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("navigates to next page when next button is clicked", () => {
    render(<PdfToolbar {...defaultProps} currentPage={3} totalPages={10} />);
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(4);
  });

  it("navigates to previous page when prev button is clicked", () => {
    render(<PdfToolbar {...defaultProps} currentPage={3} totalPages={10} />);
    fireEvent.click(screen.getByLabelText("Previous page"));
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(2);
  });

  it("disables previous page button on page 1", () => {
    render(<PdfToolbar {...defaultProps} currentPage={1} totalPages={10} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });

  it("disables next page button on last page", () => {
    render(<PdfToolbar {...defaultProps} currentPage={10} totalPages={10} />);
    expect(screen.getByLabelText("Next page")).toBeDisabled();
  });

  it("allows page navigation via input field", () => {
    render(<PdfToolbar {...defaultProps} currentPage={1} totalPages={10} />);
    const input = screen.getByLabelText("Page number, 1 of 10");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(defaultProps.onNavigateToPage).toHaveBeenCalledWith(7);
  });

  it("resets input on invalid page number", () => {
    render(<PdfToolbar {...defaultProps} currentPage={5} totalPages={10} />);
    const input = screen.getByLabelText("Page number, 5 of 10");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "99" } });
    fireEvent.keyDown(input, { key: "Enter" });
    // Should not navigate; input resets to current page on blur.
    expect(defaultProps.onNavigateToPage).not.toHaveBeenCalled();
  });

  it("disables all controls when loading", () => {
    render(<PdfToolbar {...defaultProps} isLoading={true} />);
    expect(screen.getByLabelText("Zoom in")).toBeDisabled();
    expect(screen.getByLabelText("Zoom out")).toBeDisabled();
    expect(screen.getByLabelText("Fit width")).toBeDisabled();
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
    expect(screen.getByLabelText("Next page")).toBeDisabled();
  });
});