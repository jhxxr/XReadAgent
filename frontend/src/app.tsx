// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useEffect } from "react";

import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LanguageProvider } from "@/lib/i18n";
import { onDeepLink, onMenuNavigate, onOpenWorkspace } from "@/lib/platform";
import { ThemeProvider } from "@/lib/theme";
import { router } from "@/router";
import { writeWorkspacePath } from "@/lib/workspace";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

interface AppProvidersProps {
  children?: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <ThemeProvider defaultTheme="system">
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <TooltipProvider delayDuration={200}>
            {children}
            <Toaster position="bottom-right" richColors />
          </TooltipProvider>
        </LanguageProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export function App() {
  // ---------------------------------------------------------------------------
  // Electron IPC listeners — deep links, workspace open, menu navigation
  // ---------------------------------------------------------------------------

  useEffect(() => {
    // Listen for deep link navigation (xread:// URLs and .xread file opens).
    const cleanupDeepLink = onDeepLink((action) => {
      if (action.type === "navigate") {
        void router.navigate({ to: action.path });
      } else if (action.type === "open-workspace") {
        // For .xread files, the path is the file itself. The workspace
        // directory is the parent. Set the workspace path and navigate home.
        const workspacePath = action.path;
        writeWorkspacePath(workspacePath);
        void router.navigate({ to: "/workspace" });
      }
    });

    // Listen for workspace open requests from the Electron menu.
    const cleanupOpenWorkspace = onOpenWorkspace((workspacePath) => {
      writeWorkspacePath(workspacePath);
      void router.navigate({ to: "/workspace" });
    });

    // Listen for menu-driven navigation (e.g. Preferences).
    const cleanupMenuNavigate = onMenuNavigate((path) => {
      void router.navigate({ to: path });
    });

    return () => {
      cleanupDeepLink();
      cleanupOpenWorkspace();
      cleanupMenuNavigate();
    };
  }, []);

  return (
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
