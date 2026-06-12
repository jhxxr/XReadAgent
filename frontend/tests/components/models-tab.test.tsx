// SPDX-License-Identifier: AGPL-3.0-or-later
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelsTab } from "@/components/settings/models-tab";
import { LanguageProvider } from "@/lib/i18n";
import type { AppSettings, Provider } from "@/types/api";

const { getSettings, putSettings, fetchProviderModels, testProviderModel } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  putSettings: vi.fn(),
  fetchProviderModels: vi.fn(),
  testProviderModel: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return { ...actual, getSettings, putSettings, fetchProviderModels, testProviderModel };
});

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function baseSettings(overrides: Partial<AppSettings> = {}): AppSettings {
  return {
    model: "",
    workspacePath: "",
    language: "en",
    providers: [],
    featureModels: { ingest: null, query: null, translate: null },
    ...overrides,
  };
}

function deepseek(models: Provider["models"] = []): Provider {
  return {
    id: "ds",
    name: "DeepSeek",
    format: "openai",
    baseUrl: "https://api.deepseek.com/v1",
    apiKey: "sk-test",
    enabled: true,
    models,
  };
}

function renderModelsTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <ModelsTab />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("ModelsTab", () => {
  beforeEach(() => {
    getSettings.mockResolvedValue(baseSettings());
    putSettings.mockImplementation((req: Partial<AppSettings>) => baseSettings(req));
  });

  it("renders the empty state and an add-provider button", async () => {
    renderModelsTab();
    expect(await screen.findByText(/No providers yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add Provider/i })).toBeInTheDocument();
  });

  it("adds a provider through the editor dialog", async () => {
    const user = userEvent.setup();
    renderModelsTab();

    await user.click(await screen.findByRole("button", { name: /Add Provider/i }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "DeepSeek");
    await user.click(within(dialog).getByRole("button", { name: /^Save$/i }));

    expect(await screen.findByText("DeepSeek")).toBeInTheDocument();
  });

  it("fetches the model list from a provider", async () => {
    const user = userEvent.setup();
    getSettings.mockResolvedValue(baseSettings({ providers: [deepseek()] }));
    fetchProviderModels.mockResolvedValue({ models: [{ id: "deepseek-chat", name: "" }] });

    renderModelsTab();
    await screen.findByText("DeepSeek");

    await user.click(screen.getByRole("button", { name: /Fetch Models/i }));

    expect(fetchProviderModels).toHaveBeenCalledWith({
      format: "openai",
      baseUrl: "https://api.deepseek.com/v1",
      apiKey: "sk-test",
    });
    // The fetched model appears as a selectable row (auto-expanded list).
    expect(await screen.findByLabelText("select deepseek-chat")).toBeInTheDocument();
  });

  it("assigns a feature model and persists it on save", async () => {
    const user = userEvent.setup();
    getSettings.mockResolvedValue(
      baseSettings({ providers: [deepseek([{ id: "deepseek-chat", name: "DeepSeek Chat" }])] }),
    );

    renderModelsTab();
    await screen.findByText("DeepSeek");

    await user.selectOptions(screen.getByLabelText("Ingest"), "ds::deepseek-chat");
    await user.click(screen.getByRole("button", { name: /Save Settings/i }));

    expect(putSettings).toHaveBeenCalledTimes(1);
    const arg = (putSettings.mock.calls[0]?.[0] ?? {}) as Partial<AppSettings>;
    expect(arg.featureModels?.ingest).toEqual({ providerId: "ds", modelId: "deepseek-chat" });
    expect(arg.providers?.[0]?.id).toBe("ds");
  });

  it("deletes a provider", async () => {
    const user = userEvent.setup();
    getSettings.mockResolvedValue(baseSettings({ providers: [deepseek()] }));

    renderModelsTab();
    await screen.findByText("DeepSeek");

    await user.click(screen.getByRole("button", { name: /^Delete$/i }));

    expect(screen.queryByText("DeepSeek")).not.toBeInTheDocument();
    expect(await screen.findByText(/No providers yet/i)).toBeInTheDocument();
  });
});
