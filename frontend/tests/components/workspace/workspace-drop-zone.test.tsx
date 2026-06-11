// SPDX-License-Identifier: AGPL-3.0-or-later
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceDropZone } from "@/components/workspace/workspace-drop-zone";

function makeFile(name: string): File {
  return new File(["content"], name, { type: "application/octet-stream" });
}

/** Minimal DataTransfer stand-in — jsdom does not implement the real one. */
function filesTransfer(files: File[]) {
  return { types: ["Files"], files, dropEffect: "none" };
}

function renderZone(onDropFiles = vi.fn()) {
  const view = render(
    <WorkspaceDropZone onDropFiles={onDropFiles}>
      <div>workspace content</div>
    </WorkspaceDropZone>,
  );
  const zone = view.container.querySelector('[data-slot="workspace-drop-zone"]');
  if (!zone) throw new Error("drop zone root not rendered");
  return { onDropFiles, zone };
}

describe("WorkspaceDropZone", () => {
  it("renders children and no overlay initially", () => {
    renderZone();
    expect(screen.getByText("workspace content")).toBeInTheDocument();
    expect(screen.queryByText("Drop to import")).not.toBeInTheDocument();
  });

  it("shows the overlay while dragging files over the zone", () => {
    const { zone } = renderZone();
    fireEvent.dragEnter(zone, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    expect(screen.getByText("Drop to import")).toBeInTheDocument();
  });

  it("hides the overlay when the drag leaves the zone", () => {
    const { zone } = renderZone();
    fireEvent.dragEnter(zone, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    fireEvent.dragLeave(zone, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    expect(screen.queryByText("Drop to import")).not.toBeInTheDocument();
  });

  it("keeps the overlay visible while crossing nested children", () => {
    const { zone } = renderZone();
    const child = screen.getByText("workspace content");
    fireEvent.dragEnter(zone, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    fireEvent.dragEnter(child, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    fireEvent.dragLeave(child, { dataTransfer: filesTransfer([makeFile("a.pdf")]) });
    expect(screen.getByText("Drop to import")).toBeInTheDocument();
  });

  it("ignores drags that carry no files (e.g. selected text)", () => {
    const { zone } = renderZone();
    fireEvent.dragEnter(zone, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(screen.queryByText("Drop to import")).not.toBeInTheDocument();
  });

  it("forwards dropped files and hides the overlay", () => {
    const { onDropFiles, zone } = renderZone();
    const file = makeFile("paper.pdf");
    fireEvent.dragEnter(zone, { dataTransfer: filesTransfer([file]) });
    fireEvent.drop(zone, { dataTransfer: filesTransfer([file]) });

    expect(onDropFiles).toHaveBeenCalledTimes(1);
    expect(onDropFiles).toHaveBeenCalledWith([file]);
    expect(screen.queryByText("Drop to import")).not.toBeInTheDocument();
  });

  it("does not forward drops that carry no files", () => {
    const { onDropFiles, zone } = renderZone();
    fireEvent.drop(zone, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(onDropFiles).not.toHaveBeenCalled();
  });
});
