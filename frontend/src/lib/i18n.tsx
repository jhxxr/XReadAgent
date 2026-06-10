// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getSettings, putSettings } from "@/lib/api";
import type { AppLanguage, AppSettings } from "@/types/api";

export const DEFAULT_LANGUAGE: AppLanguage = "zh";

export const LANGUAGE_OPTIONS: readonly {
  value: AppLanguage;
  label: string;
  descriptionKey: TranslationKey;
}[] = [
  { value: "en", label: "English", descriptionKey: "settings.language.optionEnglish" },
  { value: "zh", label: "简体中文", descriptionKey: "settings.language.optionChinese" },
] as const;

const STORAGE_KEY = "xreadagent.language";

const EN_MESSAGES = {
  "nav.workspace": "Workspace",
  "nav.papers": "Papers",
  "nav.queries": "Queries",
  "nav.settings": "Settings",
  "nav.defaultWorkspace": "Default",
  "settings.title": "Settings",
  "settings.subtitle": "Configure XReadAgent",
  "settings.tabs.general": "General",
  "settings.tabs.generalDescription": "Model and workspace defaults",
  "settings.tabs.language": "Language",
  "settings.tabs.languageDescription": "Interface language",
  "settings.tabs.sidecar": "Sidecar",
  "settings.tabs.sidecarDescription": "Backend process status",
  "settings.loading": "Loading...",
  "settings.loadError": "Failed to load settings.",
  "settings.general.title": "General",
  "settings.general.description": "Defaults used by ingest, query, and workspace views.",
  "settings.model.title": "LLM Configuration",
  "settings.model.description": "Default model used for ingest and query operations.",
  "settings.model.label": "Model",
  "settings.model.placeholder": "provider:model",
  "settings.model.helpPrefix": "Format:",
  "settings.model.helpExample": "e.g.",
  "settings.model.secretHelp": "API keys are read from environment variables and are not stored.",
  "settings.workspace.title": "Workspace",
  "settings.workspace.description":
    "Absolute path to the workspace directory where papers, concepts, and queries are stored.",
  "settings.workspace.label": "Workspace Path",
  "settings.workspace.placeholder": "/path/to/workspace",
  "settings.save": "Save Settings",
  "settings.saving": "Saving...",
  "settings.saved": "Settings saved",
  "settings.saveFailed": "Failed to save settings",
  "settings.language.title": "Language",
  "settings.language.description": "Choose the interface language for the renderer.",
  "settings.language.current": "Current language",
  "settings.language.optionEnglish": "Use English interface text.",
  "settings.language.optionChinese": "Use Simplified Chinese interface text.",
  "settings.language.saving": "Saving language...",
  "settings.language.saved": "Language is saved automatically.",
  "settings.sidecar.browserTitle": "Sidecar",
  "settings.sidecar.browserDescription":
    "The sidecar status panel is only available when running inside the Electron desktop app. In browser dev mode, the Python sidecar runs separately on localhost:8765.",
  "settings.sidecar.processTitle": "Sidecar Process",
  "settings.sidecar.processDescription":
    "Python backend process that powers ingestion, queries, and translation.",
  "settings.sidecar.status": "Status",
  "settings.sidecar.status.running": "Running",
  "settings.sidecar.status.starting": "Starting",
  "settings.sidecar.status.idle": "Idle",
  "settings.sidecar.status.stopped": "Stopped",
  "settings.sidecar.status.crashed": "Crashed",
  "settings.sidecar.pid": "PID",
  "settings.sidecar.port": "Port",
  "settings.sidecar.started": "Started",
  "settings.sidecar.restarts": "Restarts",
  "settings.sidecar.restartAttempt": "Restart attempt",
  "settings.sidecar.startingIn": "starting in",
  "settings.sidecar.startingSoon": "starting...",
  "settings.sidecar.autoRestartSuffix": "auto-restart(s) this session",
  "settings.sidecar.restartSidecar": "Restart Sidecar",
  "settings.sidecar.restarting": "Restarting...",
  "settings.sidecar.logs": "Logs",
  "settings.sidecar.logsDescription": "Recent sidecar stdout and stderr output.",
  "settings.sidecar.copy": "Copy",
  "settings.sidecar.copied": "Copied",
  "settings.sidecar.noLogs": "No logs yet.",
  "settings.sidecar.queryFailed": "Failed to query sidecar status",
  "settings.sidecar.restartFailed": "Restart failed",
} as const;

export type TranslationKey = keyof typeof EN_MESSAGES;

const MESSAGES: Record<AppLanguage, Record<TranslationKey, string>> = {
  en: EN_MESSAGES,
  zh: {
    "nav.workspace": "工作区",
    "nav.papers": "论文",
    "nav.queries": "问答",
    "nav.settings": "设置",
    "nav.defaultWorkspace": "默认",
    "settings.title": "设置",
    "settings.subtitle": "配置 XReadAgent",
    "settings.tabs.general": "通用",
    "settings.tabs.generalDescription": "模型和工作区默认值",
    "settings.tabs.language": "语言",
    "settings.tabs.languageDescription": "界面语言",
    "settings.tabs.sidecar": "后端进程",
    "settings.tabs.sidecarDescription": "后端进程状态",
    "settings.loading": "加载中...",
    "settings.loadError": "设置加载失败。",
    "settings.general.title": "通用",
    "settings.general.description": "用于导入、问答和工作区视图的默认配置。",
    "settings.model.title": "LLM 配置",
    "settings.model.description": "导入和问答操作使用的默认模型。",
    "settings.model.label": "模型",
    "settings.model.placeholder": "provider:model",
    "settings.model.helpPrefix": "格式：",
    "settings.model.helpExample": "例如",
    "settings.model.secretHelp": "API 密钥从环境变量读取，不会存入设置。",
    "settings.workspace.title": "工作区",
    "settings.workspace.description": "用于存储论文、概念和问答的工作区目录绝对路径。",
    "settings.workspace.label": "工作区路径",
    "settings.workspace.placeholder": "/path/to/workspace",
    "settings.save": "保存设置",
    "settings.saving": "保存中...",
    "settings.saved": "设置已保存",
    "settings.saveFailed": "设置保存失败",
    "settings.language.title": "语言",
    "settings.language.description": "选择渲染界面的显示语言。",
    "settings.language.current": "当前语言",
    "settings.language.optionEnglish": "使用英文界面文本。",
    "settings.language.optionChinese": "使用简体中文界面文本。",
    "settings.language.saving": "正在保存语言...",
    "settings.language.saved": "语言会自动保存。",
    "settings.sidecar.browserTitle": "后端进程",
    "settings.sidecar.browserDescription":
      "后端进程状态面板仅在 Electron 桌面应用中可用。浏览器开发模式下，Python 后端会独立运行在 localhost:8765。",
    "settings.sidecar.processTitle": "后端进程",
    "settings.sidecar.processDescription": "负责导入、问答和翻译的 Python 后端进程。",
    "settings.sidecar.status": "状态",
    "settings.sidecar.status.running": "运行中",
    "settings.sidecar.status.starting": "启动中",
    "settings.sidecar.status.idle": "空闲",
    "settings.sidecar.status.stopped": "已停止",
    "settings.sidecar.status.crashed": "已崩溃",
    "settings.sidecar.pid": "PID",
    "settings.sidecar.port": "端口",
    "settings.sidecar.started": "启动时间",
    "settings.sidecar.restarts": "重启",
    "settings.sidecar.restartAttempt": "重启尝试",
    "settings.sidecar.startingIn": "将在",
    "settings.sidecar.startingSoon": "正在启动...",
    "settings.sidecar.autoRestartSuffix": "本会话自动重启",
    "settings.sidecar.restartSidecar": "重启后端",
    "settings.sidecar.restarting": "重启中...",
    "settings.sidecar.logs": "日志",
    "settings.sidecar.logsDescription": "最近的后端 stdout 和 stderr 输出。",
    "settings.sidecar.copy": "复制",
    "settings.sidecar.copied": "已复制",
    "settings.sidecar.noLogs": "暂无日志。",
    "settings.sidecar.queryFailed": "查询后端状态失败",
    "settings.sidecar.restartFailed": "重启失败",
  },
};

interface LanguageContextValue {
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  isSavingLanguage: boolean;
  t: (key: TranslationKey) => string;
}

interface LanguageProviderProps {
  children: React.ReactNode;
  defaultLanguage?: AppLanguage;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

function isAppLanguage(value: string | null): value is AppLanguage {
  return value === "en" || value === "zh";
}

function readStoredLanguage(): AppLanguage | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isAppLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

function writeStoredLanguage(language: AppLanguage): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // localStorage is a convenience cache; the backend setting remains canonical.
  }
}

export function LanguageProvider({
  children,
  defaultLanguage = DEFAULT_LANGUAGE,
}: LanguageProviderProps) {
  const queryClient = useQueryClient();
  const [language, setLanguageState] = useState<AppLanguage>(
    () => readStoredLanguage() ?? defaultLanguage,
  );

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const savedLanguage = settingsQuery.data?.language;

  useEffect(() => {
    if (!savedLanguage) return;
    setLanguageState(savedLanguage);
    writeStoredLanguage(savedLanguage);
  }, [savedLanguage]);

  const languageMutation = useMutation({
    mutationFn: (nextLanguage: AppLanguage) => putSettings({ language: nextLanguage }),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings"], saved);
      setLanguageState(saved.language);
      writeStoredLanguage(saved.language);
    },
    onError: () => {
      const saved = queryClient.getQueryData<AppSettings>(["settings"]);
      const fallback = saved?.language ?? DEFAULT_LANGUAGE;
      setLanguageState(fallback);
      writeStoredLanguage(fallback);
    },
  });

  const setLanguage = useCallback(
    (nextLanguage: AppLanguage) => {
      setLanguageState(nextLanguage);
      writeStoredLanguage(nextLanguage);
      languageMutation.mutate(nextLanguage);
    },
    [languageMutation],
  );

  const t = useCallback((key: TranslationKey) => MESSAGES[language][key], [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      isSavingLanguage: languageMutation.isPending,
      t,
    }),
    [language, languageMutation.isPending, setLanguage, t],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useI18n must be used inside <LanguageProvider>");
  return ctx;
}
