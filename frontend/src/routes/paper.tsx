// SPDX-License-Identifier: AGPL-3.0-or-later
import { Link, useParams } from "@tanstack/react-router";
import { BookOpenIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function PaperRoute() {
  const { slug } = useParams({ from: "/paper/$slug" });
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-6 py-10">
      <div className="flex items-center gap-3">
        <Badge variant="outline">paper</Badge>
        <span className="text-muted-foreground font-mono text-xs">{slug}</span>
        <Button size="sm" className="ml-auto gap-2" asChild>
          <Link to="/paper/$slug/read" params={{ slug }}>
            <BookOpenIcon className="size-3.5" />
            Read in PDF
          </Link>
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Paper view placeholder</CardTitle>
          <CardDescription>
            Phase 2 will render the seven-section paper page here, alongside a dual-column PDF
            reader.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-foreground/90 text-sm leading-relaxed">
            The page will hydrate from{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">wiki/papers/{slug}.md</code>{" "}
            once the read endpoint lands. Concept wikilinks resolve client-side via TanStack
            Router.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
