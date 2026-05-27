// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Markdown renderer for wiki pages with wiki-link (`[[...]]`) support.
 *
 * Converts `[[target|text]]` and `[[target]]` wiki-links into clickable
 * internal links before passing the content to `react-markdown`.  The
 * link resolution maps wiki paths to TanStack Router routes:
 *
 * - `[[papers/slug|text]]` -> `/paper/slug`
 * - `[[concepts/slug|text]]` -> `/concept/slug`
 * - `[[queries/topic/slug|text]]` -> `/query/topic/slug`
 */

import { Link } from "@tanstack/react-router";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Regex that matches `[[target]]` or `[[target|display text]]`. */
const WIKILINK_RE = /\[\[([^\]|]+?)(?:\|([^\]]*?))?\]\]/g;

/**
 * Replace wiki-link syntax with markdown links using a `wikilink:` URI scheme.
 *
 * The custom link component below intercepts `wikilink:` hrefs and renders
 * them as TanStack Router `<Link>` elements.
 */
function preprocessWikilinks(markdown: string): string {
  return markdown.replace(WIKILINK_RE, (_match, target: string, text?: string) => {
    const display = text?.trim() ?? target.trim();
    return `[${display}](wikilink:${target.trim()})`;
  });
}

/** Map a wiki-link target to a TanStack Router `to` path. */
function resolveWikilinkTarget(target: string): string {
  // Normalise: strip leading `wiki/` if present.
  const normalised = target.replace(/^wiki\//, "");

  if (normalised.startsWith("papers/")) {
    const slug = normalised.slice("papers/".length);
    return `/paper/${slug}`;
  }
  if (normalised.startsWith("concepts/")) {
    const slug = normalised.slice("concepts/".length);
    return `/concept/${slug}`;
  }
  if (normalised.startsWith("queries/")) {
    // queries/topic/slug -> /query/topic/slug
    const rest = normalised.slice("queries/".length);
    return `/query/${rest}`;
  }
  // Fallback: treat as a paper slug.
  return `/paper/${normalised}`;
}

/** Props for the markdown renderer. */
interface WikiMarkdownProps {
  /** Raw markdown content (may contain wiki-link syntax). */
  content: string;
}

/**
 * Render wiki-flavoured markdown.
 *
 * Preprocesses wiki-links, then delegates to `react-markdown` with GFM
 * support.  Links whose href starts with `wikilink:` are rendered as
 * internal `<Link>` elements; all other links open in a new tab.
 */
export function WikiMarkdown({ content }: WikiMarkdownProps) {
  const processed = preprocessWikilinks(content);

  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children, ...props }) {
            if (href?.startsWith("wikilink:")) {
              const target = href.slice("wikilink:".length);
              const to = resolveWikilinkTarget(target);
              return (
                <Link
                  to={to}
                  className="text-primary font-medium underline underline-offset-4 hover:text-primary/80"
                >
                  {children}
                </Link>
              );
            }
            // External / regular links open in a new tab.
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-4 hover:text-primary/80"
                {...props}
              >
                {children}
              </a>
            );
          },
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="bg-muted rounded px-1.5 py-0.5 text-xs" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return (
              <pre className="bg-muted overflow-x-auto rounded-lg border p-4 text-sm">
                {children}
              </pre>
            );
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">{children}</table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th className="border-border bg-muted border px-3 py-2 text-left font-medium">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="border-border border px-3 py-2">{children}</td>;
          },
          hr() {
            return <hr className="border-border my-6" />;
          },
          h1({ children }) {
            return <h1 className="mt-8 mb-4 text-2xl font-bold first:mt-0">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="mt-6 mb-3 text-xl font-semibold">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="mt-5 mb-2 text-lg font-medium">{children}</h3>;
          },
          ul({ children }) {
            return <ul className="list-inside list-disc space-y-1">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-inside list-decimal space-y-1">{children}</ol>;
          },
          li({ children }) {
            return <li className="text-foreground/90">{children}</li>;
          },
          blockquote({ children }) {
            return (
              <blockquote className="border-primary/30 text-muted-foreground border-l-4 pl-4 italic">
                {children}
              </blockquote>
            );
          },
          p({ children }) {
            return <p className="text-foreground/90 leading-relaxed">{children}</p>;
          },
          strong({ children }) {
            return <strong className="text-foreground font-semibold">{children}</strong>;
          },
          em({ children }) {
            return <em className="text-foreground/80 italic">{children}</em>;
          },
        }}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}
