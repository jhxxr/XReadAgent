# Component Guidelines

> How components are built in the renderer.

---

## Component Structure

Every TSX file starts with the SPDX header and uses named exports (no default exports). The standard shape:

```tsx
// SPDX-License-Identifier: AGPL-3.0-or-later
import * as React from "react";          // only if you need React.* types
import { cn } from "@/lib/utils";         // every component that takes className

interface FooProps extends React.HTMLAttributes<HTMLDivElement> {
  // domain props
}

export function Foo({ className, ...props }: FooProps) {
  return <div className={cn("base-classes", className)} {...props} />;
}
```

See `frontend/src/components/ui/card.tsx` for the canonical form.

---

## Function vs `React.forwardRef`

| Choose `function` declaration | Choose `React.forwardRef` |
|-------------------------------|---------------------------|
| Default for UI primitives that don't need an external ref (Card, Badge, DialogHeader, Tabs wrappers that don't expose the underlying primitive). | When the consumer needs the DOM/primitive ref **and** the primitive itself uses refs — e.g. wrappers around Radix primitives with `data-state` animation control (`DialogContent`, `DialogTitle`, `DialogDescription`). |
| Faster to read, fewer generics. | Always set `displayName = <PrimitiveName>.displayName` so React DevTools and Radix portals work — see `frontend/src/components/ui/dialog.tsx:25`. |

`Button` is a `forwardRef` because it supports `asChild` via `@radix-ui/react-slot` — see `frontend/src/components/ui/button.tsx`.

Don't sprinkle `forwardRef` defensively. If nothing currently needs the ref, use `function`.

---

## Props Conventions

- Define a named `interface FooProps` (not `type Foo = ...`) so editors render a stable name. `BadgeProps`, `ButtonProps`, etc.
- Extend the corresponding DOM attributes when the component is a "div with classes" — `React.HTMLAttributes<HTMLDivElement>`, `React.ButtonHTMLAttributes<HTMLButtonElement>`. This pulls in `className`, `onClick`, ARIA attrs, etc. for free.
- For Radix wrappers, type props as `React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>` (and ref as `React.ComponentRef<typeof DialogPrimitive.Content>`). See `dialog.tsx`.
- Always destructure `className` separately and run it through `cn(...)` so callers can extend styling.
- `asChild?: boolean` is the standard composition escape hatch — implemented with `<Slot>` from `@radix-ui/react-slot` (`Button`).
- `readonly T[]` for arrays of static config (e.g. `NAV_ITEMS` in `app-sidebar.tsx`).

Don't accept `style={...}` props through your APIs — utility classes via `className` are the only styling surface.

---

## Styling Patterns

**Tailwind 4 + `cn()` + CVA**. There is no CSS module, no styled-components, no inline `style` (except dynamic, like `colorScheme` in `theme.tsx`).

### The `cn` helper

`cn(...inputs: ClassValue[])` (`frontend/src/lib/utils.ts`) is `twMerge(clsx(...))`. Use it everywhere class lists are conditional or extensible — even for "just one class" if a `className` prop is being merged.

### CVA for variant tables

Use `class-variance-authority` when a primitive has multiple visual variants (variant + size). The pattern:

```tsx
const buttonVariants = cva("base classes", {
  variants: { variant: { default: "...", outline: "..." }, size: { default: "...", sm: "..." } },
  defaultVariants: { variant: "default", size: "default" },
});

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}
```

Reference: `frontend/src/components/ui/button.tsx`, `badge.tsx`. Always export the `<name>Variants` function alongside the component (suppress `react-refresh/only-export-components` with a single-line `eslint-disable-next-line` directly above the export — see `button.tsx`).

### Tokens, not hex

All colors come from CSS custom properties declared in `frontend/src/styles/globals.css` (`oklch(...)` values). Use Tailwind utilities backed by those tokens — `bg-primary`, `text-muted-foreground`, `border-border/60`, `bg-success/15`, etc. Never write `bg-[#aabbcc]` in component code.

### `data-slot` attribute

Local primitives set `data-slot="<name>"` on their root element so downstream styling and tests can target the slot without hardcoding the tag — see `Button`, `Card`, `CardHeader`, etc. Match the slot name to the component's lowercase name (`data-slot="card-header"`).

### `data-testid` attribute

Reserved for spots that need stable test targets where role/text queries are too brittle — currently `HealthBanner` (`data-testid="health-banner"`) and `CopilotSidebar` trigger (`data-testid="copilot-trigger"`). Prefer Testing Library role/text queries first; add `data-testid` only when the query would be ambiguous.

---

## Icons

`lucide-react` only. Import individual icons (`SparklesIcon`, `XIcon`, …) — never `import * as Icons`. Default size class is `size-4` (matches the global selector `[&_svg:not([class*='size-'])]:size-4` baked into `buttonVariants`); explicitly set `size-3.5` / `size-5` when the surrounding density warrants it.

---

## Accessibility

- Every actionable icon button has either visible text or an `aria-label` — see `ThemeToggle`'s `aria-label={LABEL[theme]}` and `CopilotSidebar`'s `aria-label="Open copilot"`.
- Decorative icons get no label (they sit next to text).
- Use Radix primitives for anything stateful (dialog, tabs, tooltip, scroll-area). They handle focus trapping, ESC, ARIA attrs.
- Live regions: status banners use `role="status"` + `aria-live="polite"` (see `HealthBanner`).
- Tooltip wrapper requires a `TooltipProvider` in the tree — already mounted in `app.tsx`. New tooltips must use `<Tooltip><TooltipTrigger asChild>...</TooltipTrigger><TooltipContent>...</TooltipContent></Tooltip>` (see `theme-toggle.tsx`).

---

## Common Mistakes

- **Wrapping `<button>` in `<Link>` (or vice versa)**. Use `<Link>` for navigation and `<Button asChild><Link to=...>` if a button-styled link is needed. Never nest two interactive elements.
- **Throwing in `beforeLoad`**. TanStack Router uses `throw redirect(...)` as control flow (`router.tsx` `/` route). Suppress the `@typescript-eslint/only-throw-error` rule with a one-line eslint-disable directly above the `throw`. Don't disable the rule project-wide.
- **Forgetting `defaultVariants`** in a `cva()` definition — the resulting `<Button />` without a variant prop will render with no styles.
- **Using arbitrary color values** (`bg-[oklch(...)]` or `text-[#...]`). Add a token to `globals.css` instead, or compose with `/<opacity>` modifiers (`bg-success/15`, `text-muted-foreground/90`).
- **Re-exporting Radix primitives as their own component** without setting `displayName` — devtools and Radix portal lookups silently break.
