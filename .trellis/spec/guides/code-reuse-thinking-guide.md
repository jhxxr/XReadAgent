# Code Reuse Thinking Guide

Use this guide before creating new helpers, constants, components, event shapes, or service abstractions.

## Search First

Prefer `rg`:

```bash
rg "function_or_constant_name" backend frontend electron
rg "similar keyword" backend frontend electron
```

Search for both protocol spellings when relevant:

```bash
rg "jobId|job_id" backend frontend electron
rg "targetLang|target_lang" backend frontend
```

## Common Duplication Risks In This Repo

### API And Event Shapes

Backend Pydantic models and frontend TypeScript interfaces must stay aligned. Before adding a field to a backend response, search `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`, and route/component consumers.

### Sidecar URLs And Ports

Do not duplicate sidecar URL construction. Use `frontend/src/lib/platform.ts` and `frontend/src/lib/api.ts`.

### Workspace Layout

Do not duplicate workspace directory names outside backend `wiki/paths.py` and `wiki/workspace.py` unless the value is part of a documented cross-layer contract.

### Supported File Types

Import suffixes are mirrored in Electron dialog filters and frontend drag/drop filtering. Search before changing:

```bash
rg "pdf|docx|html|htm|md|txt" frontend/src/lib/use-workspace-actions.ts electron/src/main.ts
```

### UI Primitives

Check `frontend/src/components/ui` before creating a new component primitive. Existing primitives cover buttons, cards, dialogs, inputs, scroll areas, separators, tabs, tooltips, badges, and skeletons.

## When To Abstract

Abstract when:

- The same behavior appears in three or more places.
- A protocol or path value must stay synchronized across layers.
- Tests already need an injection seam for heavy dependencies or platform APIs.

Do not abstract when:

- The logic is a one-off route/component detail.
- The abstraction would hide a boundary that should remain explicit, such as backend HTTP mapping or Electron IPC.

## After Batch Changes

- Run `rg` for the old name/value.
- Check the owning spec index for the affected layer.
- Update cross-layer docs when a duplicated value is intentionally mirrored.
