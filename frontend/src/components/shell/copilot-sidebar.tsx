// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Copilot sidebar — non-modal slide-in panel for asking questions about
 * the wiki.  Replaces the Phase 1 placeholder with a functional
 * conversational research interface.
 */

import { Link } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  FileTextIcon,
  Loader2Icon,
  SendIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { WikiMarkdown } from "@/components/wiki/wiki-markdown";
import { postQuery } from "@/lib/api";
import { readWorkspacePath } from "@/lib/workspace";
import { cn } from "@/lib/utils";
import type { CitedEvidence, QueryResultResponse } from "@/types/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  readonly id: string;
  readonly role: "user" | "assistant";
  readonly content: string;
  readonly confidence?: string;
  readonly sourcesCited?: readonly string[];
  readonly evidence?: readonly CitedEvidence[];
  readonly error?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map a wiki-relative path (e.g. `papers/slug`) to a router path. */
function wikiPathToRoute(path: string): string {
  const normalized = path.replace(/^wiki\//, "");
  if (normalized.startsWith("papers/")) {
    return `/paper/${normalized.slice("papers/".length)}`;
  }
  if (normalized.startsWith("concepts/")) {
    return `/concept/${normalized.slice("concepts/".length)}`;
  }
  if (normalized.startsWith("queries/")) {
    return `/query/${normalized.slice("queries/".length)}`;
  }
  return `/paper/${normalized}`;
}

/** Return a display label for a wiki path (strip the prefix). */
function wikiPathLabel(path: string): string {
  const normalized = path.replace(/^wiki\//, "");
  const parts = normalized.split("/");
  return parts[parts.length - 1] ?? normalized;
}

/** Map a confidence string to a Badge variant. */
function confidenceVariant(confidence: string): "success" | "warning" | "destructive" {
  switch (confidence) {
    case "high":
      return "success";
    case "medium":
      return "warning";
    case "low":
      return "destructive";
    default:
      return "warning";
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface UserMessageBubbleProps {
  content: string;
}

function UserMessageBubble({ content }: UserMessageBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 text-sm">
        {content}
      </div>
    </div>
  );
}

interface AssistantMessageBubbleProps {
  content: string;
  confidence?: string;
  sourcesCited?: readonly string[];
  evidence?: readonly CitedEvidence[];
}

function AssistantMessageBubble({
  content,
  confidence,
  sourcesCited,
  evidence,
}: AssistantMessageBubbleProps) {
  return (
    <div className="flex flex-col gap-3">
      {/* Answer */}
      <div className="bg-muted rounded-2xl rounded-bl-md px-3.5 py-2.5">
        <WikiMarkdown content={content} />
      </div>

      {/* Confidence badge */}
      {confidence && (
        <div className="flex items-center gap-2 pl-1">
          <span className="text-muted-foreground text-xs">Confidence:</span>
          <Badge variant={confidenceVariant(confidence)}>{confidence}</Badge>
        </div>
      )}

      {/* Evidence / Sources */}
      {evidence && evidence.length > 0 ? (
        <EvidencePanel evidence={evidence} />
      ) : sourcesCited && sourcesCited.length > 0 ? (
        <SourcesList sources={sourcesCited} />
      ) : null}
    </div>
  );
}

interface EvidencePanelProps {
  evidence: readonly CitedEvidence[];
}

function EvidencePanel({ evidence }: EvidencePanelProps) {
  return (
    <div className="bg-muted/50 space-y-2.5 rounded-lg border border-border/60 p-3">
      <h4 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        Evidence
      </h4>
      {evidence.map((item, idx) => (
        <div key={idx} className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Link
              to={wikiPathToRoute(item.sourceWikiPath)}
              className="text-primary flex items-center gap-1.5 text-xs font-medium underline underline-offset-2 hover:text-primary/80"
            >
              <FileTextIcon className="size-3" />
              {wikiPathLabel(item.sourceWikiPath)}
            </Link>
            <Badge variant={confidenceVariant(item.confidence)} className="text-[10px]">
              {item.confidence}
            </Badge>
          </div>
          {item.quote && (
            <p className="text-muted-foreground border-primary/20 border-l-2 pl-2.5 text-xs italic">
              {item.quote}
            </p>
          )}
          {idx < evidence.length - 1 && <Separator className="my-1" />}
        </div>
      ))}
    </div>
  );
}

interface SourcesListProps {
  sources: readonly string[];
}

function SourcesList({ sources }: SourcesListProps) {
  return (
    <div className="bg-muted/50 space-y-1.5 rounded-lg border border-border/60 p-3">
      <h4 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Sources</h4>
      <ul className="space-y-1">
        {sources.map((path, idx) => (
          <li key={idx}>
            <Link
              to={wikiPathToRoute(path)}
              className="text-primary flex items-center gap-1.5 text-xs font-medium underline underline-offset-2 hover:text-primary/80"
            >
              <FileTextIcon className="size-3" />
              {wikiPathLabel(path)}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2">
      <AlertCircleIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
      <p className="text-destructive text-sm">{message}</p>
    </div>
  );
}

function LoadingIndicator() {
  return (
    <div className="flex items-center gap-2 pl-1">
      <Loader2Icon className="text-muted-foreground size-4 animate-spin" />
      <span className="text-muted-foreground text-xs">Thinking...</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CopilotSidebar() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  // Focus input when sidebar opens.
  useEffect(() => {
    if (open) {
      // Small delay to let the panel animate in.
      const timer = setTimeout(() => inputRef.current?.focus(), 200);
      return () => clearTimeout(timer);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: (question: string) => {
      const workspacePath = readWorkspacePath();
      if (!workspacePath) {
        throw new Error("No workspace configured. Set a workspace path first.");
      }
      return postQuery({ workspacePath, question });
    },
    onSuccess: (data: QueryResultResponse) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: data.answer,
          confidence: data.confidence,
          sourcesCited: data.sourcesCited,
          evidence: data.evidence,
        },
      ]);
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : "Query failed. Please try again.";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          error: message,
        },
      ]);
    },
  });

  const handleSubmit = useCallback(() => {
    const question = input.trim();
    if (!question || mutation.isPending) return;

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: question }]);
    setInput("");
    mutation.mutate(question);
  }, [input, mutation]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleClear = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <>
      {/* Floating trigger button */}
      <button
        type="button"
        aria-label="Open copilot"
        data-testid="copilot-trigger"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "bg-primary text-primary-foreground fixed right-6 bottom-6 z-40 inline-flex size-12 items-center justify-center rounded-full shadow-lg transition-transform hover:scale-105 active:scale-95",
          open && "scale-90 opacity-70",
        )}
      >
        <SparklesIcon className="size-5" />
      </button>

      {/* Slide-in panel */}
      <div
        data-slot="copilot-sidebar"
        data-testid="copilot-sidebar"
        className={cn(
          "bg-background fixed top-0 right-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border/80 shadow-xl transition-transform duration-200 ease-in-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <SparklesIcon className="size-4" />
            Copilot
          </h2>
          <div className="flex items-center gap-1">
            {messages.length > 0 && (
              <Button variant="ghost" size="sm" onClick={handleClear} aria-label="Clear chat">
                Clear
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setOpen(false)}
              aria-label="Close copilot"
            >
              <XIcon className="size-4" />
            </Button>
          </div>
        </div>

        {/* Message area */}
        <ScrollArea className="flex-1">
          <div ref={scrollRef} className="flex flex-col gap-4 p-4">
            {messages.length === 0 && (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center">
                <div className="bg-muted text-muted-foreground flex size-12 items-center justify-center rounded-full">
                  <SparklesIcon className="size-5" />
                </div>
                <h3 className="text-base font-semibold tracking-tight">Ask about your wiki</h3>
                <p className="text-muted-foreground max-w-xs text-sm leading-relaxed">
                  Type a question below to search your ingested documents and get answers with cited
                  evidence.
                </p>
              </div>
            )}

            {messages.map((msg) =>
              msg.role === "user" ? (
                <UserMessageBubble key={msg.id} content={msg.content} />
              ) : msg.error ? (
                <ErrorMessage key={msg.id} message={msg.error} />
              ) : (
                <AssistantMessageBubble
                  key={msg.id}
                  content={msg.content}
                  confidence={msg.confidence}
                  sourcesCited={msg.sourcesCited}
                  evidence={msg.evidence}
                />
              ),
            )}

            {mutation.isPending && <LoadingIndicator />}
          </div>
        </ScrollArea>

        {/* Input area */}
        <div className="border-t border-border/80 p-3">
          <div className="flex items-center gap-2">
            <Input
              ref={inputRef}
              type="text"
              placeholder="Ask a question..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={mutation.isPending}
            />
            <Button
              size="icon"
              onClick={handleSubmit}
              disabled={!input.trim() || mutation.isPending}
              aria-label="Send question"
            >
              {mutation.isPending ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <SendIcon className="size-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
