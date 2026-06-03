// SPDX-License-Identifier: AGPL-3.0-or-later
import { Link, useRouterState } from "@tanstack/react-router";
import {
  ChevronDownIcon,
  LayoutDashboardIcon,
  LibraryBigIcon,
  type LucideIcon,
  MessagesSquareIcon,
  SettingsIcon,
  SparklesIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useWorkspaceActions } from "@/lib/use-workspace-actions";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: "/workspace", label: "Workspace", icon: LayoutDashboardIcon },
  { to: "/paper", label: "Papers", icon: LibraryBigIcon },
  { to: "/queries", label: "Queries", icon: MessagesSquareIcon },
] as const;

export function AppSidebar() {
  const router = useRouterState();
  const pathname = router.location.pathname;
  const { selectWorkspace, workspacePath } = useWorkspaceActions();
  const workspaceLabel = workspacePath.trim() || "Default";

  return (
    <aside className="bg-sidebar text-sidebar-foreground border-sidebar-border flex h-full w-[260px] flex-col border-r">
      <div className="flex h-14 items-center gap-2 px-4">
        <div className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-md">
          <SparklesIcon className="size-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight">XReadAgent</span>
      </div>

      <Separator />

      <div className="px-3 py-3">
        <button
          type="button"
          onClick={() => {
            void selectWorkspace();
          }}
          className={cn(
            "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors",
          )}
          data-slot="workspace-switcher"
        >
          <div className="flex flex-col">
            <span className="text-muted-foreground text-[0.7rem] uppercase tracking-wider">
              Workspace
            </span>
            <span className="truncate font-medium">{workspaceLabel}</span>
          </div>
          <ChevronDownIcon className="text-muted-foreground size-4" />
        </button>
      </div>

      <Separator />

      <nav className="flex-1 px-2 py-3">
        <ul className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            const active =
              pathname === to ||
              (to !== "/workspace" && pathname.startsWith(to)) ||
              (to === "/workspace" && pathname === "/");
            return (
              <li key={to}>
                <Link
                  to={to}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  )}
                >
                  <Icon className="size-4" />
                  <span>{label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <Separator />

      <div className="p-3">
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground w-full justify-start gap-2"
          asChild
        >
          <Link to="/settings">
            <SettingsIcon className="size-4" />
            Settings
          </Link>
        </Button>
      </div>
    </aside>
  );
}
