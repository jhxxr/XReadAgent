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
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { WorkspaceManagerDialog } from "@/components/workspace/workspace-manager-dialog";
import { useWorkspaces } from "@/lib/use-workspaces";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useI18n, type TranslationKey } from "@/lib/i18n";

interface NavItem {
  to: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: "/workspace", labelKey: "nav.workspace", icon: LayoutDashboardIcon },
  { to: "/paper", labelKey: "nav.papers", icon: LibraryBigIcon },
  { to: "/queries", labelKey: "nav.queries", icon: MessagesSquareIcon },
] as const;

export function AppSidebar() {
  const { t } = useI18n();
  const router = useRouterState();
  const pathname = router.location.pathname;
  const { workspaces, activeWorkspacePath } = useWorkspaces();
  const [managerOpen, setManagerOpen] = useState(false);
  const activeEntry = workspaces.find((w) => w.path === activeWorkspacePath);
  const workspaceLabel = activeEntry?.name ?? t("nav.defaultWorkspace");

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
          onClick={() => setManagerOpen(true)}
          className={cn(
            "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm transition-colors",
          )}
          data-slot="workspace-switcher"
        >
          <div className="flex min-w-0 flex-col">
            <span className="text-muted-foreground text-[0.7rem] uppercase tracking-wider">
              {t("nav.workspace")}
            </span>
            <span className="truncate font-medium">{workspaceLabel}</span>
          </div>
          <ChevronDownIcon className="text-muted-foreground size-4 shrink-0" />
        </button>
      </div>

      <Separator />

      <nav className="flex-1 px-2 py-3">
        <ul className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(({ to, labelKey, icon: Icon }) => {
            const label = t(labelKey);
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
            {t("nav.settings")}
          </Link>
        </Button>
      </div>

      <WorkspaceManagerDialog open={managerOpen} onOpenChange={setManagerOpen} />
    </aside>
  );
}
