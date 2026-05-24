// SPDX-License-Identifier: AGPL-3.0-or-later
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function PaperIndexRoute() {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>Papers</CardTitle>
          <CardDescription>Per-source synthesis pages live here.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm leading-relaxed">
            Once you ingest a source, the agent writes a{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">papers/&lt;slug&gt;.md</code>{" "}
            page using the seven-section paper-curator template (Background, Challenges,
            Solution, Positioning, Key Concepts, Experiments, Open Questions).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
