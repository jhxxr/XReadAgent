// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider, useI18n } from "@/lib/i18n";

const { getSettings, putSettings } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  putSettings: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getSettings,
  putSettings,
}));

function LanguageProbe() {
  const { language, setLanguage, t } = useI18n();

  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="settings-title">{t("settings.title")}</span>
      <button type="button" onClick={() => setLanguage("zh")}>
        switch zh
      </button>
    </div>
  );
}

function renderProbe() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <LanguageProbe />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe("LanguageProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    getSettings.mockResolvedValue({ model: "", workspacePath: "", language: "zh" });
    putSettings.mockImplementation((req: { language?: "en" | "zh" }) => ({
      model: "",
      workspacePath: "",
      language: req.language ?? "zh",
    }));
  });

  it("loads the saved language and persists language changes", async () => {
    const user = userEvent.setup();
    renderProbe();

    expect(await screen.findByTestId("language")).toHaveTextContent("zh");
    expect(screen.getByTestId("settings-title")).toHaveTextContent("设置");

    await user.click(screen.getByRole("button", { name: /switch zh/i }));

    expect(putSettings).toHaveBeenCalledWith({ language: "zh" });
    await waitFor(() => {
      expect(screen.getByTestId("settings-title")).toHaveTextContent("设置");
    });
    expect(window.localStorage.getItem("xreadagent.language")).toBe("zh");
  });
});
