// SPDX-License-Identifier: AGPL-3.0-or-later
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function QueriesRoute() {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>Query archive</CardTitle>
          <CardDescription>
            Answers are isolated from synthesis until you crystallize them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-foreground/90 text-sm leading-relaxed">
            Each question you ask is archived under{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">
              wiki/queries/&lt;topic&gt;/&lt;date&gt;-&lt;slug&gt;.md
            </code>
            . Archives never auto-modify{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">papers/</code>,{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">concepts/</code>, or the
            index &mdash; promoting an answer into the wiki is an explicit{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">/crystallize</code> step.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
