// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LanguagesIcon, SaveIcon, ServerIcon, SettingsIcon, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { SidecarTab } from "@/components/settings/sidecar-tab";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getSettings, putSettings } from "@/lib/api";
import { LANGUAGE_OPTIONS, useI18n, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { writeWorkspacePath } from "@/lib/workspace";

type SettingsTabValue = "general" | "language" | "sidecar";

interface SettingsTabItem {
  value: SettingsTabValue;
  labelKey: TranslationKey;
  descriptionKey: TranslationKey;
  icon: LucideIcon;
}

const SETTINGS_TABS: readonly SettingsTabItem[] = [
  {
    value: "general",
    labelKey: "settings.tabs.general",
    descriptionKey: "settings.tabs.generalDescription",
    icon: SettingsIcon,
  },
  {
    value: "language",
    labelKey: "settings.tabs.language",
    descriptionKey: "settings.tabs.languageDescription",
    icon: LanguagesIcon,
  },
  {
    value: "sidecar",
    labelKey: "settings.tabs.sidecar",
    descriptionKey: "settings.tabs.sidecarDescription",
    icon: ServerIcon,
  },
] as const;

export function SettingsRoute() {
  const { t } = useI18n();

  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="border-border/60 flex h-14 items-center gap-4 border-b px-6">
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold leading-tight">{t("settings.title")}</h1>
          <p className="text-muted-foreground text-xs">{t("settings.subtitle")}</p>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <Tabs
          defaultValue="general"
          orientation="vertical"
          className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[230px_minmax(0,1fr)]"
        >
          <TabsList className="bg-background h-auto w-full flex-col items-stretch justify-start gap-1 rounded-none border-0 p-0 lg:sticky lg:top-0">
            {SETTINGS_TABS.map(({ value, labelKey, descriptionKey, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="data-[state=active]:border-border data-[state=active]:bg-muted/60 data-[state=active]:shadow-none flex h-auto w-full justify-start gap-3 rounded-md border border-transparent px-3 py-2.5 text-left"
              >
                <Icon className="mt-0.5 size-4 shrink-0" />
                <span className="flex min-w-0 flex-col items-start gap-0.5">
                  <span className="text-sm font-medium">{t(labelKey)}</span>
                  <span className="text-muted-foreground truncate text-xs font-normal">
                    {t(descriptionKey)}
                  </span>
                </span>
              </TabsTrigger>
            ))}
          </TabsList>

          <div className="min-w-0">
            <TabsContent value="general" className="mt-0">
              <GeneralTab />
            </TabsContent>

            <TabsContent value="language" className="mt-0">
              <LanguageTab />
            </TabsContent>

            <TabsContent value="sidecar" className="mt-0">
              <SidecarTab />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}

function GeneralTab() {
  const queryClient = useQueryClient();
  const { t } = useI18n();

  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const [model, setModel] = useState("");
  const [workspacePath, setWorkspacePath] = useState("");

  useEffect(() => {
    if (data) {
      setModel(data.model);
      setWorkspacePath(data.workspacePath);
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: putSettings,
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings"], saved);
      if (saved.workspacePath) {
        writeWorkspacePath(saved.workspacePath);
      }
      toast.success(t("settings.saved"));
    },
    onError: () => {
      toast.error(t("settings.saveFailed"));
    },
  });

  const handleSave = () => {
    mutation.mutate({ model: model.trim(), workspacePath: workspacePath.trim() });
  };

  if (isLoading) {
    return (
      <div className="text-muted-foreground py-8 text-center text-sm">{t("settings.loading")}</div>
    );
  }

  if (error) {
    return (
      <div className="text-destructive py-8 text-center text-sm">{t("settings.loadError")}</div>
    );
  }

  return (
    <Card className="rounded-md shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SettingsIcon className="size-4" />
          {t("settings.general.title")}
        </CardTitle>
        <CardDescription>{t("settings.general.description")}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-medium">{t("settings.model.title")}</h2>
            <p className="text-muted-foreground mt-1 text-sm">{t("settings.model.description")}</p>
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="settings-model">
              {t("settings.model.label")}
            </label>
            <Input
              id="settings-model"
              className="mt-1.5"
              placeholder={t("settings.model.placeholder")}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
            <p className="text-muted-foreground mt-1.5 text-xs">
              {t("settings.model.helpPrefix")} <code>provider:model</code>{" "}
              {t("settings.model.helpExample")} <code>openai:gpt-4o</code>.
            </p>
            <p className="text-muted-foreground mt-1 text-xs">{t("settings.model.secretHelp")}</p>
          </div>
        </section>

        <Separator />

        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-medium">{t("settings.workspace.title")}</h2>
            <p className="text-muted-foreground mt-1 text-sm">
              {t("settings.workspace.description")}
            </p>
          </div>
          <div>
            <label className="text-sm font-medium" htmlFor="settings-workspace">
              {t("settings.workspace.label")}
            </label>
            <Input
              id="settings-workspace"
              className="mt-1.5"
              placeholder={t("settings.workspace.placeholder")}
              value={workspacePath}
              onChange={(e) => setWorkspacePath(e.target.value)}
            />
          </div>
        </section>

        <Separator />

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={mutation.isPending} className="gap-2">
            <SaveIcon className="size-4" />
            {mutation.isPending ? t("settings.saving") : t("settings.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function LanguageTab() {
  const { language, setLanguage, isSavingLanguage, t } = useI18n();

  return (
    <Card className="rounded-md shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <LanguagesIcon className="size-4" />
          {t("settings.language.title")}
        </CardTitle>
        <CardDescription>{t("settings.language.description")}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div
          role="radiogroup"
          aria-label={t("settings.language.current")}
          className="grid gap-3 sm:grid-cols-2"
        >
          {LANGUAGE_OPTIONS.map((option) => {
            const selected = option.value === language;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => setLanguage(option.value)}
                className={cn(
                  "flex min-h-24 items-start gap-3 rounded-md border p-4 text-left transition-colors",
                  selected
                    ? "border-primary bg-primary/5 text-foreground"
                    : "border-border/70 hover:bg-muted/60 text-muted-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-1 size-2.5 rounded-full border",
                    selected ? "border-primary bg-primary" : "border-muted-foreground/50",
                  )}
                />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-foreground text-sm font-medium">{option.label}</span>
                  <span className="text-sm">{t(option.descriptionKey)}</span>
                </span>
              </button>
            );
          })}
        </div>

        <p className="text-muted-foreground text-xs" aria-live="polite">
          {isSavingLanguage ? t("settings.language.saving") : t("settings.language.saved")}
        </p>
      </CardContent>
    </Card>
  );
}
