// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SaveIcon, ServerIcon, SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { SidecarTab } from "@/components/settings/sidecar-tab";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getSettings, putSettings } from "@/lib/api";
import { writeWorkspacePath } from "@/lib/workspace";

export function SettingsRoute() {
  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="border-border/60 flex h-14 items-center gap-4 border-b px-6">
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold leading-tight">Settings</h1>
          <p className="text-muted-foreground text-xs">Configure XReadAgent</p>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-xl">
          <Tabs defaultValue="general">
            <TabsList className="w-full">
              <TabsTrigger value="general" className="flex-1 gap-1.5">
                <SettingsIcon className="size-3.5" />
                General
              </TabsTrigger>
              <TabsTrigger value="sidecar" className="flex-1 gap-1.5">
                <ServerIcon className="size-3.5" />
                Sidecar
              </TabsTrigger>
            </TabsList>

            <TabsContent value="general">
              <GeneralTab />
            </TabsContent>

            <TabsContent value="sidecar">
              <SidecarTab />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}

function GeneralTab() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const [model, setModel] = useState("");
  const [workspacePath, setWorkspacePath] = useState("");

  // Sync fetched data into local state.
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
      // Keep localStorage in sync so existing workspace reads work.
      if (saved.workspacePath) {
        writeWorkspacePath(saved.workspacePath);
      }
      toast.success("Settings saved");
    },
    onError: () => {
      toast.error("Failed to save settings");
    },
  });

  const handleSave = () => {
    mutation.mutate({ model: model.trim(), workspacePath: workspacePath.trim() });
  };

  if (isLoading) {
    return <div className="text-muted-foreground py-8 text-center text-sm">Loading...</div>;
  }

  if (error) {
    return (
      <div className="text-destructive py-8 text-center text-sm">Failed to load settings.</div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <SettingsIcon className="size-4" />
            LLM Configuration
          </CardTitle>
          <CardDescription>
            Set the default model used for ingest and query operations. Format:{" "}
            <code className="text-xs">provider:model</code> (e.g.{" "}
            <code className="text-xs">openai:gpt-4o</code>).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label className="text-sm font-medium" htmlFor="settings-model">
            Model
          </label>
          <Input
            id="settings-model"
            className="mt-1.5"
            placeholder="provider:model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <p className="text-muted-foreground mt-1.5 text-xs">
            API keys are read from environment variables and are not stored in settings.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Workspace</CardTitle>
          <CardDescription>
            Absolute path to the workspace directory where papers, concepts, and queries are stored.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <label className="text-sm font-medium" htmlFor="settings-workspace">
            Workspace Path
          </label>
          <Input
            id="settings-workspace"
            className="mt-1.5"
            placeholder="/path/to/workspace"
            value={workspacePath}
            onChange={(e) => setWorkspacePath(e.target.value)}
          />
        </CardContent>
      </Card>

      <Separator />

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={mutation.isPending} className="gap-2">
          <SaveIcon className="size-4" />
          {mutation.isPending ? "Saving..." : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}
