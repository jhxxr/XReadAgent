// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Deep link and file association handling for XReadAgent.
 *
 * Parses `xread://` URLs and `.xread` file paths, producing navigation
 * commands that the renderer can act on via TanStack Router.
 *
 * Supported deep link routes:
 * - `xread://paper/{slug}`  -> navigate to `/paper/{slug}`
 * - `xread://query/{id}`    -> navigate to `/query/{id}` (note: the route
 *   uses `/query/{topic}/{slug}`, so `{id}` here is the full path segment)
 *
 * File associations:
 * - Double-clicking a `.xread` file sends the file path to the renderer,
 *   which can extract the workspace path from the file's parent directory
 *   or content.
 */

/** Parsed result of a deep link or file-open event. */
export type DeepLinkAction =
  | { type: "navigate"; path: string }
  | { type: "open-workspace"; path: string };

/** Protocol prefix for XReadAgent deep links. */
const XREAD_PROTOCOL = "xread://";

/**
 * Check whether a path segment contains path traversal sequences.
 * Rejects segments with `..` which could navigate outside the app's routes.
 */
function hasTraversal(segment: string): boolean {
  return segment.split("/").some((part) => part === "..");
}

/**
 * Parse a `xread://` URL and return a navigation action.
 *
 * @param url - The raw URL string from `open-url` or command-line.
 * @returns A `DeepLinkAction` describing what the renderer should do, or
 *   `null` if the URL is not a valid XReadAgent deep link.
 */
export function parseDeepLink(url: string): DeepLinkAction | null {
  if (!url.startsWith(XREAD_PROTOCOL)) {
    return null;
  }

  // Strip the protocol and leading slash to get the route path.
  const routePath = url.slice(XREAD_PROTOCOL.length);

  // Reject path traversal attempts.
  if (hasTraversal(routePath)) return null;

  // Handle known routes.
  // xread://paper/{slug} -> navigate to /paper/{slug}
  if (routePath.startsWith("paper/")) {
    const slug = routePath.slice("paper/".length).replace(/\/$/, "");
    if (slug.length === 0) return null;
    return { type: "navigate", path: `/paper/${slug}` };
  }

  // xread://query/{topic}/{slug} -> navigate to /query/{topic}/{slug}
  // Also handle xread://query/{id} where id could be a single segment.
  if (routePath.startsWith("query/")) {
    const rest = routePath.slice("query/".length).replace(/\/$/, "");
    if (rest.length === 0) return null;
    return { type: "navigate", path: `/query/${rest}` };
  }

  // xread://workspace -> navigate to /workspace
  if (routePath === "workspace" || routePath === "workspace/") {
    return { type: "navigate", path: "/workspace" };
  }

  // xread://settings -> navigate to /settings
  if (routePath === "settings" || routePath === "settings/") {
    return { type: "navigate", path: "/settings" };
  }

  return null;
}

/**
 * Parse a `.xread` file path and return an open-workspace action.
 *
 * In v1, `.xread` files are simple markers — the workspace is the directory
 * containing the file. The renderer receives the file path and can decide
 * how to open it (e.g. set the workspace path and navigate there).
 *
 * @param filePath - Absolute path to the `.xread` file.
 * @returns A `DeepLinkAction` for opening the workspace.
 */
export function parseXreadFile(filePath: string): DeepLinkAction {
  return { type: "open-workspace", path: filePath };
}
