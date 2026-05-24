// SPDX-License-Identifier: AGPL-3.0-or-later
import { MoonIcon, SunIcon, SunMoonIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useTheme, type Theme } from "@/lib/theme";

const NEXT: Record<Theme, Theme> = {
  light: "dark",
  dark: "system",
  system: "light",
};

const LABEL: Record<Theme, string> = {
  light: "Light theme",
  dark: "Dark theme",
  system: "System theme",
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={LABEL[theme]}
          onClick={() => {
            setTheme(NEXT[theme]);
          }}
        >
          {theme === "light" && <SunIcon className="size-4" />}
          {theme === "dark" && <MoonIcon className="size-4" />}
          {theme === "system" && <SunMoonIcon className="size-4" />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{LABEL[theme]} (click to cycle)</TooltipContent>
    </Tooltip>
  );
}
