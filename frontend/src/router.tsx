// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
} from "@tanstack/react-router";

import { AppShell } from "@/components/shell/app-shell";
import { WorkspaceRoute } from "@/routes/workspace";

// All routes except the home (`/workspace`) load lazily so heavy dependencies
// (pdfjs-dist in the reader, react-markdown in the wiki pages) stay out of the
// initial bundle and only download when the user navigates to them.
const rootRoute = createRootRoute({
  component: AppShell,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    // TanStack Router uses `throw redirect(...)` as a control-flow primitive.
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    throw redirect({ to: "/workspace" });
  },
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workspace",
  component: WorkspaceRoute,
});

const paperIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/paper",
  component: lazyRouteComponent(() => import("@/routes/paper-index"), "PaperIndexRoute"),
});

const paperRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/paper/$slug",
  component: lazyRouteComponent(() => import("@/routes/paper"), "PaperRoute"),
});

const paperReadRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/paper/$slug/read",
  component: lazyRouteComponent(() => import("@/routes/paper-read"), "PaperReadRoute"),
});

const conceptRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/concept/$slug",
  component: lazyRouteComponent(() => import("@/routes/concept"), "ConceptRoute"),
});

const queriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/queries",
  component: lazyRouteComponent(() => import("@/routes/queries"), "QueriesRoute"),
});

const queryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/query/$topic/$slug",
  component: lazyRouteComponent(() => import("@/routes/query-detail"), "QueryDetailRoute"),
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: lazyRouteComponent(() => import("@/routes/settings"), "SettingsRoute"),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  workspaceRoute,
  paperIndexRoute,
  paperRoute,
  paperReadRoute,
  conceptRoute,
  queriesRoute,
  queryDetailRoute,
  settingsRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
