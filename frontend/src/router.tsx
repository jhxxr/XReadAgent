// SPDX-License-Identifier: AGPL-3.0-or-later
import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";

import { AppShell } from "@/components/shell/app-shell";
import { ConceptRoute } from "@/routes/concept";
import { PaperIndexRoute } from "@/routes/paper-index";
import { PaperReadRoute } from "@/routes/paper-read";
import { PaperRoute } from "@/routes/paper";
import { QueriesRoute } from "@/routes/queries";
import { QueryDetailRoute } from "@/routes/query-detail";
import { WorkspaceRoute } from "@/routes/workspace";

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
  component: PaperIndexRoute,
});

const paperRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/paper/$slug",
  component: PaperRoute,
});

const paperReadRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/paper/$slug/read",
  component: PaperReadRoute,
});

const conceptRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/concept/$slug",
  component: ConceptRoute,
});

const queriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/queries",
  component: QueriesRoute,
});

const queryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/query/$topic/$slug",
  component: QueryDetailRoute,
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
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
