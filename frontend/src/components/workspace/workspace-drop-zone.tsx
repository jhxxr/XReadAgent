// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Drop zone wrapper for the workspace view.
 *
 * Accepts files dragged from the OS and forwards them to the caller (which
 * routes them into the existing ingest mutation). Also blocks the browser's
 * default drop behavior window-wide so a stray drop outside the zone doesn't
 * navigate the renderer away from the app.
 */
import * as React from "react";
import { FileDownIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface WorkspaceDropZoneProps {
  onDropFiles: (files: File[]) => void;
  children: React.ReactNode;
  className?: string;
}

function containsFiles(event: React.DragEvent | DragEvent): boolean {
  const types = event.dataTransfer?.types;
  return types != null && Array.from(types).includes("Files");
}

export function WorkspaceDropZone({ onDropFiles, children, className }: WorkspaceDropZoneProps) {
  const [isDragActive, setIsDragActive] = React.useState(false);
  // dragenter/dragleave fire for every child element crossed; a depth counter
  // keeps the overlay stable until the pointer actually leaves the zone.
  const dragDepthRef = React.useRef(0);

  React.useEffect(() => {
    const preventDefault = (event: DragEvent) => {
      if (containsFiles(event)) {
        event.preventDefault();
      }
    };
    // Without these, dropping a file outside the zone makes the renderer
    // navigate to the file (losing all app state).
    window.addEventListener("dragover", preventDefault);
    window.addEventListener("drop", preventDefault);
    return () => {
      window.removeEventListener("dragover", preventDefault);
      window.removeEventListener("drop", preventDefault);
    };
  }, []);

  const handleDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    if (!containsFiles(event)) return;
    event.preventDefault();
    dragDepthRef.current += 1;
    setIsDragActive(true);
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    if (!containsFiles(event)) return;
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (!containsFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    if (!containsFiles(event)) return;
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) {
      onDropFiles(files);
    }
  };

  return (
    <div
      data-slot="workspace-drop-zone"
      className={cn("relative", className)}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}
      {isDragActive && (
        <div
          role="status"
          aria-live="polite"
          // pointer-events-none: the overlay must not steal drag events from the wrapper.
          className="bg-background/80 pointer-events-none absolute inset-0 z-50 flex items-center justify-center p-6 backdrop-blur-sm"
        >
          <div className="border-primary/60 bg-card/90 flex flex-col items-center gap-3 rounded-xl border-2 border-dashed px-12 py-10 text-center shadow-sm">
            <FileDownIcon className="text-primary size-8" />
            <p className="text-sm font-medium">Drop to import</p>
            <p className="text-muted-foreground text-xs">PDF, DOCX, HTML, Markdown, or text</p>
          </div>
        </div>
      )}
    </div>
  );
}
