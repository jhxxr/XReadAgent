// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  GripVerticalIcon,
  PencilIcon,
  PlugIcon,
  PlusIcon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { ApiError, fetchProviderModels, getSettings, putSettings, testProviderModel } from "@/lib/api";
import { useI18n, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  FeatureModels,
  FeatureName,
  ModelEntry,
  ModelRef,
  Provider,
  ProviderFormat,
} from "@/types/api";

const FEATURES: readonly FeatureName[] = ["ingest", "query", "translate"] as const;
const FEATURE_LABEL_KEY: Record<FeatureName, TranslationKey> = {
  ingest: "settings.models.feature.ingest",
  query: "settings.models.feature.query",
  translate: "settings.models.feature.translate",
};

function emptyFeatureModels(): FeatureModels {
  return { ingest: null, query: null, translate: null };
}

function reorder<T>(list: readonly T[], from: number, to: number): T[] {
  const next = list.slice();
  const [moved] = next.splice(from, 1);
  if (moved !== undefined) next.splice(to, 0, moved);
  return next;
}

function formatLabelKey(format: ProviderFormat): TranslationKey {
  return format === "anthropic"
    ? "settings.models.format.anthropic"
    : "settings.models.format.openai";
}

/** Drop a feature assignment that points at a now-missing provider/model. */
function pruneAssignments(
  featureModels: FeatureModels,
  providers: readonly Provider[],
): FeatureModels {
  const valid = (ref: ModelRef | null): ModelRef | null => {
    if (!ref) return null;
    const provider = providers.find((p) => p.id === ref.providerId);
    if (!provider?.models.some((m) => m.id === ref.modelId)) return null;
    return ref;
  };
  return {
    ingest: valid(featureModels.ingest),
    query: valid(featureModels.query),
    translate: valid(featureModels.translate),
  };
}

export function ModelsTab() {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const [providers, setProviders] = useState<Provider[]>([]);
  const [featureModels, setFeatureModels] = useState<FeatureModels>(emptyFeatureModels());
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState<{ provider: Provider; isNew: boolean } | null>(null);
  const [modelEditing, setModelEditing] = useState<{
    providerId: string;
    model: ModelEntry;
    isNew: boolean;
  } | null>(null);

  const dragProvider = useRef<number | null>(null);

  useEffect(() => {
    if (!data) return;
    setProviders(data.providers ?? []);
    setFeatureModels(data.featureModels ?? emptyFeatureModels());
    setDirty(false);
  }, [data]);

  const mutation = useMutation({
    mutationFn: () => putSettings({ providers, featureModels }),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings"], saved);
      setDirty(false);
      toast.success(t("settings.saved"));
    },
    onError: () => toast.error(t("settings.saveFailed")),
  });

  // -- provider mutations (local state; persisted via Save) ----------------

  const updateProvider = (id: string, patch: Partial<Provider>) => {
    setProviders((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)));
    setDirty(true);
  };

  const upsertProvider = (provider: Provider, isNew: boolean) => {
    setProviders((prev) =>
      isNew ? [...prev, provider] : prev.map((p) => (p.id === provider.id ? provider : p)),
    );
    setDirty(true);
  };

  const deleteProvider = (id: string) => {
    setProviders((prev) => {
      const next = prev.filter((p) => p.id !== id);
      setFeatureModels((fm) => pruneAssignments(fm, next));
      return next;
    });
    setDirty(true);
  };

  const duplicateProvider = (id: string) => {
    setProviders((prev) => {
      const source = prev.find((p) => p.id === id);
      if (!source) return prev;
      let copyId = `${source.id}-copy`;
      let n = 2;
      while (prev.some((p) => p.id === copyId)) copyId = `${source.id}-copy-${n++}`;
      const clone: Provider = {
        ...source,
        id: copyId,
        name: source.name ? `${source.name} (copy)` : copyId,
        models: source.models.map((m) => ({ ...m })),
      };
      return [...prev, clone];
    });
    setDirty(true);
  };

  const setProviderModels = (id: string, models: ModelEntry[]) => {
    setProviders((prev) => prev.map((p) => (p.id === id ? { ...p, models } : p)));
    setDirty(true);
  };

  const upsertModel = (providerId: string, model: ModelEntry, isNew: boolean) => {
    setProviders((prev) =>
      prev.map((p) => {
        if (p.id !== providerId) return p;
        const models = isNew
          ? [...p.models, model]
          : p.models.map((m) => (m.id === model.id ? model : m));
        return { ...p, models };
      }),
    );
    setDirty(true);
  };

  const setFeature = (feature: FeatureName, ref: ModelRef | null) => {
    setFeatureModels((prev) => ({ ...prev, [feature]: ref }));
    setDirty(true);
  };

  const handleAddProvider = () => {
    let id = "provider";
    let n = 1;
    while (providers.some((p) => p.id === id)) id = `provider-${++n}`;
    setEditing({
      provider: {
        id,
        name: "",
        format: "openai",
        baseUrl: "",
        apiKey: "",
        enabled: true,
        models: [],
      },
      isNew: true,
    });
  };

  const handleProviderDrop = (index: number) => {
    const from = dragProvider.current;
    dragProvider.current = null;
    if (from === null || from === index) return;
    setProviders((prev) => reorder(prev, from, index));
    setDirty(true);
  };

  if (isLoading) {
    return (
      <div className="text-muted-foreground py-8 text-center text-sm">
        {t("settings.loading")}
      </div>
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
          <PlugIcon className="size-4" />
          {t("settings.models.title")}
        </CardTitle>
        <CardDescription>{t("settings.models.description")}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="flex justify-end">
          <Button variant="outline" size="sm" className="gap-2" onClick={handleAddProvider}>
            <PlusIcon className="size-4" />
            {t("settings.models.addProvider")}
          </Button>
        </div>

        {providers.length === 0 ? (
          <p className="text-muted-foreground rounded-md border border-dashed py-8 text-center text-sm">
            {t("settings.models.empty")}
          </p>
        ) : (
          <div className="space-y-3">
            {providers.map((provider, index) => (
              <ProviderCard
                key={provider.id}
                provider={provider}
                onDragStart={() => (dragProvider.current = index)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleProviderDrop(index)}
                onToggleEnabled={(enabled) => updateProvider(provider.id, { enabled })}
                onEdit={() => setEditing({ provider, isNew: false })}
                onDuplicate={() => duplicateProvider(provider.id)}
                onDelete={() => deleteProvider(provider.id)}
                onModelsChange={(models) => setProviderModels(provider.id, models)}
                onAddModel={() =>
                  setModelEditing({
                    providerId: provider.id,
                    model: { id: "", name: "" },
                    isNew: true,
                  })
                }
                onEditModel={(model) =>
                  setModelEditing({ providerId: provider.id, model, isNew: false })
                }
              />
            ))}
          </div>
        )}

        <Separator />

        <FeatureAssignment
          providers={providers}
          featureModels={featureModels}
          onChange={setFeature}
        />

        <Separator />

        <div className="flex justify-end">
          <Button onClick={() => mutation.mutate()} disabled={!dirty || mutation.isPending} className="gap-2">
            <SaveIcon className="size-4" />
            {mutation.isPending ? t("settings.saving") : t("settings.save")}
          </Button>
        </div>
      </CardContent>

      {editing && (
        <ProviderEditorDialog
          initial={editing.provider}
          isNew={editing.isNew}
          existingIds={providers.map((p) => p.id)}
          onClose={() => setEditing(null)}
          onSubmit={(provider) => {
            upsertProvider(provider, editing.isNew);
            setEditing(null);
          }}
        />
      )}

      {modelEditing && (
        <ModelEditorDialog
          initial={modelEditing.model}
          isNew={modelEditing.isNew}
          onClose={() => setModelEditing(null)}
          onSubmit={(model) => {
            upsertModel(modelEditing.providerId, model, modelEditing.isNew);
            setModelEditing(null);
          }}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Provider card
// ---------------------------------------------------------------------------

interface ProviderCardProps {
  provider: Provider;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onModelsChange: (models: ModelEntry[]) => void;
  onAddModel: () => void;
  onEditModel: (model: ModelEntry) => void;
}

function ProviderCard({
  provider,
  onDragStart,
  onDragOver,
  onDrop,
  onToggleEnabled,
  onEdit,
  onDuplicate,
  onDelete,
  onModelsChange,
  onAddModel,
  onEditModel,
}: ProviderCardProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [fetching, setFetching] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const dragModel = useRef<number | null>(null);

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleFetch = async () => {
    setFetching(true);
    try {
      const res = await fetchProviderModels({
        format: provider.format,
        baseUrl: provider.baseUrl,
        apiKey: provider.apiKey,
      });
      onModelsChange(res.models);
      setSelected(new Set());
      setOpen(true);
      toast.success(t("settings.models.fetchSuccess"));
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : String(err);
      toast.error(`${t("settings.models.fetchFailed")}: ${detail}`);
    } finally {
      setFetching(false);
    }
  };

  const handleTest = async (model: ModelEntry) => {
    setTestingId(model.id);
    try {
      const res = await testProviderModel({
        format: provider.format,
        baseUrl: provider.baseUrl,
        apiKey: provider.apiKey,
        modelId: model.id,
      });
      if (res.ok) {
        const suffix = res.latencyMs != null ? ` (${res.latencyMs}ms)` : "";
        toast.success(`${t("settings.models.testOk")}${suffix}`);
      } else {
        toast.error(`${t("settings.models.testFailed")}: ${res.error ?? ""}`);
      }
    } finally {
      setTestingId(null);
    }
  };

  const handleBatchDelete = () => {
    if (selected.size === 0) return;
    onModelsChange(provider.models.filter((m) => !selected.has(m.id)));
    setSelected(new Set());
  };

  const deleteModel = (id: string) => {
    onModelsChange(provider.models.filter((m) => m.id !== id));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const duplicateModel = (model: ModelEntry) => {
    let copyId = `${model.id}-copy`;
    let n = 2;
    while (provider.models.some((m) => m.id === copyId)) copyId = `${model.id}-copy-${n++}`;
    onModelsChange([...provider.models, { id: copyId, name: model.name }]);
  };

  const handleModelDrop = (index: number) => {
    const from = dragModel.current;
    dragModel.current = null;
    if (from === null || from === index) return;
    onModelsChange(reorder(provider.models, from, index));
  };

  return (
    <div
      className={cn(
        "rounded-md border",
        provider.enabled ? "border-border/70" : "border-border/40 opacity-70",
      )}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <div className="flex items-start gap-2 p-3">
        <button
          type="button"
          aria-label="reorder"
          draggable
          onDragStart={onDragStart}
          className="text-muted-foreground hover:text-foreground mt-0.5 cursor-grab"
        >
          <GripVerticalIcon className="size-4" />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold">
              {provider.name || provider.id}
            </span>
            <Badge variant="secondary">{t(formatLabelKey(provider.format))}</Badge>
          </div>
          <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 text-xs">
            <span>ID: {provider.id}</span>
            {provider.baseUrl && (
              <>
                <span aria-hidden>·</span>
                <span className="truncate">{provider.baseUrl}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            role="switch"
            aria-checked={provider.enabled}
            aria-label={t("settings.models.enable")}
            onClick={() => onToggleEnabled(!provider.enabled)}
            className={cn(
              "relative h-5 w-9 shrink-0 rounded-full transition-colors",
              provider.enabled ? "bg-primary" : "bg-muted-foreground/30",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 size-4 rounded-full bg-white transition-transform",
                provider.enabled ? "translate-x-4" : "translate-x-0.5",
              )}
            />
          </button>
          <Button variant="ghost" size="icon" aria-label={t("settings.models.edit")} onClick={onEdit}>
            <PencilIcon className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("settings.models.duplicate")}
            onClick={onDuplicate}
          >
            <CopyIcon className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("settings.models.delete")}
            onClick={onDelete}
          >
            <Trash2Icon className="text-destructive size-4" />
          </Button>
        </div>
      </div>

      <Separator />

      <div className="p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 text-sm font-medium"
          >
            {open ? (
              <ChevronDownIcon className="size-4" />
            ) : (
              <ChevronRightIcon className="size-4" />
            )}
            {t("settings.models.modelList")} ({provider.models.length})
          </button>

          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5"
              disabled={selected.size === 0}
              onClick={handleBatchDelete}
            >
              <Trash2Icon className="size-3.5" />
              {t("settings.models.batchDelete")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5"
              disabled={fetching}
              onClick={() => void handleFetch()}
            >
              <DownloadIcon className="size-3.5" />
              {fetching ? t("settings.models.fetching") : t("settings.models.fetchModels")}
            </Button>
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={onAddModel}>
              <PlusIcon className="size-3.5" />
              {t("settings.models.addModel")}
            </Button>
          </div>
        </div>

        {open && (
          <div className="mt-3 space-y-1.5">
            {provider.models.length === 0 ? (
              <p className="text-muted-foreground py-3 text-center text-xs">
                {t("settings.models.noModels")}
              </p>
            ) : (
              provider.models.map((model, index) => (
                <div
                  key={model.id}
                  className="border-border/60 flex items-center gap-2 rounded-md border px-2.5 py-1.5"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => handleModelDrop(index)}
                >
                  <button
                    type="button"
                    aria-label="reorder model"
                    draggable
                    onDragStart={() => (dragModel.current = index)}
                    className="text-muted-foreground hover:text-foreground cursor-grab"
                  >
                    <GripVerticalIcon className="size-3.5" />
                  </button>
                  <input
                    type="checkbox"
                    aria-label={`select ${model.id}`}
                    checked={selected.has(model.id)}
                    onChange={() => toggleSelected(model.id)}
                    className="size-3.5"
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {model.name || model.id}
                    {model.name && (
                      <span className="text-muted-foreground ml-1.5 text-xs">({model.id})</span>
                    )}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1.5"
                    disabled={testingId === model.id}
                    onClick={() => void handleTest(model)}
                  >
                    <PlugIcon className="size-3.5" />
                    {testingId === model.id ? t("settings.models.testing") : t("settings.models.test")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t("settings.models.edit")}
                    onClick={() => onEditModel(model)}
                  >
                    <PencilIcon className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t("settings.models.duplicate")}
                    onClick={() => duplicateModel(model)}
                  >
                    <CopyIcon className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t("settings.models.delete")}
                    onClick={() => deleteModel(model.id)}
                  >
                    <Trash2Icon className="text-destructive size-3.5" />
                  </Button>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feature → model assignment
// ---------------------------------------------------------------------------

interface FeatureAssignmentProps {
  providers: readonly Provider[];
  featureModels: FeatureModels;
  onChange: (feature: FeatureName, ref: ModelRef | null) => void;
}

function FeatureAssignment({ providers, featureModels, onChange }: FeatureAssignmentProps) {
  const { t } = useI18n();
  const enabled = providers.filter((p) => p.enabled && p.models.length > 0);

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-medium">{t("settings.models.assignTitle")}</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          {t("settings.models.assignDescription")}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {FEATURES.map((feature) => {
          const current = featureModels[feature];
          const value = current ? `${current.providerId}::${current.modelId}` : "";
          return (
            <label key={feature} className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t(FEATURE_LABEL_KEY[feature])}</span>
              <select
                aria-label={t(FEATURE_LABEL_KEY[feature])}
                value={value}
                onChange={(e) => {
                  if (!e.target.value) {
                    onChange(feature, null);
                    return;
                  }
                  const [providerId = "", modelId = ""] = e.target.value.split("::");
                  onChange(feature, { providerId, modelId });
                }}
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              >
                <option value="">{t("settings.models.assignNone")}</option>
                {enabled.map((provider) => (
                  <optgroup key={provider.id} label={provider.name || provider.id}>
                    {provider.models.map((model) => (
                      <option key={model.id} value={`${provider.id}::${model.id}`}>
                        {model.name || model.id}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Provider editor dialog
// ---------------------------------------------------------------------------

interface ProviderEditorDialogProps {
  initial: Provider;
  isNew: boolean;
  existingIds: readonly string[];
  onClose: () => void;
  onSubmit: (provider: Provider) => void;
}

function ProviderEditorDialog({
  initial,
  isNew,
  existingIds,
  onClose,
  onSubmit,
}: ProviderEditorDialogProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<Provider>(initial);

  const submit = () => {
    if (!draft.name.trim() || !draft.id.trim()) {
      toast.error(t("settings.models.editor.nameRequired"));
      return;
    }
    if (draft.id !== initial.id && existingIds.includes(draft.id)) {
      toast.error(t("settings.models.editor.duplicateId"));
      return;
    }
    onSubmit({ ...draft, id: draft.id.trim(), name: draft.name.trim() });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isNew ? t("settings.models.editor.newTitle") : t("settings.models.editor.editTitle")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Field label={t("settings.models.editor.name")}>
            <Input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Field>
          <Field label={t("settings.models.editor.id")} help={t("settings.models.editor.idHelp")}>
            <Input value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} />
          </Field>
          <Field label={t("settings.models.editor.format")}>
            <select
              aria-label={t("settings.models.editor.format")}
              value={draft.format}
              onChange={(e) => setDraft({ ...draft, format: e.target.value as ProviderFormat })}
              className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
            >
              <option value="openai">{t("settings.models.format.openai")}</option>
              <option value="anthropic">{t("settings.models.format.anthropic")}</option>
            </select>
          </Field>
          <Field label={t("settings.models.editor.baseUrl")}>
            <Input
              value={draft.baseUrl}
              placeholder="https://api.example.com/v1"
              onChange={(e) => setDraft({ ...draft, baseUrl: e.target.value })}
            />
          </Field>
          <Field label={t("settings.models.editor.apiKey")} help={t("settings.models.editor.apiKeyHelp")}>
            <Input
              type="password"
              value={draft.apiKey}
              onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
            />
          </Field>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button className="gap-2" onClick={submit}>
            <CheckIcon className="size-4" />
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Model editor dialog
// ---------------------------------------------------------------------------

interface ModelEditorDialogProps {
  initial: ModelEntry;
  isNew: boolean;
  onClose: () => void;
  onSubmit: (model: ModelEntry) => void;
}

function ModelEditorDialog({ initial, isNew, onClose, onSubmit }: ModelEditorDialogProps) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<ModelEntry>(initial);

  const submit = () => {
    if (!draft.id.trim()) {
      toast.error(t("settings.models.modelEditor.idRequired"));
      return;
    }
    onSubmit({ id: draft.id.trim(), name: draft.name.trim() });
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isNew
              ? t("settings.models.modelEditor.newTitle")
              : t("settings.models.modelEditor.editTitle")}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Field label={t("settings.models.modelEditor.id")}>
            <Input
              value={draft.id}
              placeholder="gpt-4o"
              onChange={(e) => setDraft({ ...draft, id: e.target.value })}
            />
          </Field>
          <Field label={t("settings.models.modelEditor.name")}>
            <Input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </Field>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button className="gap-2" onClick={submit}>
            <CheckIcon className="size-4" />
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block">
        <span className="text-sm font-medium">{label}</span>
        <div className="mt-1.5">{children}</div>
      </label>
      {help && <p className="text-muted-foreground mt-1 text-xs">{help}</p>}
    </div>
  );
}
