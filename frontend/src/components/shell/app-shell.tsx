// SPDX-License-Identifier: AGPL-3.0-or-later
import { Outlet } from "@tanstack/react-router";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { CopilotSidebar } from "@/components/shell/copilot-sidebar";
import { HealthBanner } from "@/components/shell/health-banner";

export function AppShell() {
  return (
    <div className="bg-background flex h-screen w-screen overflow-hidden">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <HealthBanner />
        <main className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <CopilotSidebar />
    </div>
  );
}
