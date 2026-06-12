# Thinking Guides

Use these guides before and during implementation to catch cross-layer drift and accidental duplication in XReadAgent.

## Available Guides

| Guide | Purpose | When To Use |
| --- | --- | --- |
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | Find existing helpers, constants, components, and service patterns before adding new ones. | Before creating utilities, protocol constants, UI primitives, or repeated tests. |
| [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) | Trace data across backend, frontend, Electron, and workspace storage boundaries. | When a change touches API schemas, job events, sidecar startup, native file flows, or persisted workspace files. |

## Quick Triggers

Read the cross-layer guide when:

- A feature touches two or more of `backend/`, `frontend/`, and `electron/`.
- A backend Pydantic model or frontend API type changes.
- A WebSocket event, settings payload, or translation/ingest job shape changes.
- Workspace-relative paths, served files, or native file selection behavior changes.
- Browser dev mode and Electron mode both need to keep working.

Read the code reuse guide when:

- You are adding a new helper, hook, component primitive, service, event type, or constant.
- You are copying a value such as supported file suffixes, route prefixes, stage names, model/provider fields, or workspace directory names.
- You are making similar edits in multiple files.

## Pre-Modification Rule

Before changing any shared value or contract, search first:

```bash
rg "value_or_contract_name" .
```

For cross-layer contracts, search both sides of the boundary. Examples:

```bash
rg "jobId|job_id" backend frontend electron
rg "workspacePath" backend frontend
rg "SIDECAR_READY|sidecarPort" backend frontend electron
```

## How To Use This Directory

1. Read the relevant layer spec index first, such as `.trellis/spec/backend/index.md`.
2. Use these guides when the task crosses layers or starts to duplicate existing patterns.
3. If a bug teaches a new durable rule, update the owning layer spec or guide in the same task.
