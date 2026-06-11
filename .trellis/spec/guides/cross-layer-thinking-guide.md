# Cross-Layer Thinking Guide

> **Purpose**: Think through data flow across layers before implementing.

---

## The Problem

**Most bugs happen at layer boundaries**, not within layers.

Common cross-layer bugs:
- API returns format A, frontend expects format B
- Database stores X, service transforms to Y, but loses data
- Multiple layers implement the same logic differently

---

## Before Implementing Cross-Layer Features

### Step 1: Map the Data Flow

Draw out how data moves:

```
Source → Transform → Store → Retrieve → Transform → Display
```

For each arrow, ask:
- What format is the data in?
- What could go wrong?
- Who is responsible for validation?

### Step 2: Identify Boundaries

| Boundary | Common Issues |
|----------|---------------|
| API ↔ Service | Type mismatches, missing fields |
| Service ↔ Database | Format conversions, null handling |
| Backend ↔ Frontend | Serialization, date formats |
| Component ↔ Component | Props shape changes |

### Step 3: Define Contracts

For each boundary:
- What is the exact input format?
- What is the exact output format?
- What errors can occur?

### Step 4: Long-running operation? Use the job + WS pattern

If the backend work can take more than a couple of seconds (LLM call, subprocess, conversion), do NOT design a blocking POST. Reuse the established job contract — POST returns `{jobId}`, progress streams over `WS /ws/jobs/{job_id}`, snake_case events, buffered replay. Two reference implementations exist: translation (`translation/service.py` ↔ `translate-dialog.tsx`) and ingest (`api/ingest_jobs.py` ↔ `lib/ingest-job.ts`). Full contract: `backend/quality-guidelines.md` → "Background job + /ws/jobs progress contract".

---

## Electron ↔ Renderer Boundary (Phase 3)

The Electron shell adds a new cross-layer boundary between the main process (Node.js) and the renderer (React). This boundary has its own contract:

### Data Flow

```
Python sidecar ←─HTTP/WS──→ Renderer (React)
                                 ↕ IPC (contextBridge)
                           Main process (Node.js)
```

The renderer talks to the Python sidecar directly via HTTP/WebSocket (using `platform.ts` URLs). The main process only handles OS concerns (tray, menu, file dialogs, notifications). **Never route sidecar API calls through IPC.**

### Key Rules

1. **All renderer↔main communication goes through `window.electronAPI`** — defined in `electron/src/preload.ts`, typed in `frontend/src/types/electron.d.ts`. Never use `require()` or `nodeIntegration` in the renderer.

2. **`platform.ts` is the single source of truth for dual-environment URLs** — `getApiBaseUrl()` returns `/api` in browser mode and `http://127.0.0.1:{port}/api` in Electron mode. Never hardcode `localhost:8765` in frontend code.

3. **Deep links go through IPC** — `xread://` URLs arrive at main process, get parsed by `deeplink.ts`, and forwarded to renderer via `onDeepLink()`. The renderer uses TanStack Router to navigate.

4. **Sidecar lifecycle is managed by the main process** — The renderer can query status (`getSidecarStatus()`), read logs (`getSidecarLogs()`), and request restart (`restartSidecar()`), but spawn/shutdown/health-check happen exclusively in `SidecarManager`.

5. **WebSocket URL construction** — `getWsBaseUrl()` returns the correct base for the environment. `buildJobEventsWsUrl()` appends `/ws/jobs/{id}`. Never double-prefix (`/ws/ws/...`).

6. **The `/healthz` endpoint** is NOT under `/api` — it lives at the sidecar root. Use `getSidecarBaseUrl()` (not `getApiBaseUrl()`) for health checks in Electron mode.

### Common Mistakes

- **Double-prefixing WebSocket URLs** — `getWsBaseUrl()` returns `ws://127.0.0.1:{port}` (no `/ws` suffix). `buildJobEventsWsUrl()` adds `/ws/jobs/{id}`. Result: `ws://127.0.0.1:{port}/ws/jobs/{id}`. If `getWsBaseUrl()` returned `ws://.../ws`, you'd get `ws://.../ws/ws/jobs/{id}`.

- **Using `/api/healthz`** — The healthz endpoint is at `/healthz`, not `/api/healthz`. In browser dev mode this works because Vite proxy strips `/api`, but in Electron production mode it returns 404. Use `getSidecarBaseUrl()` for health checks.

---

## Common Cross-Layer Mistakes

### Mistake 1: Implicit Format Assumptions

**Bad**: Assuming date format without checking

**Good**: Explicit format conversion at boundaries

### Mistake 2: Scattered Validation

**Bad**: Validating the same thing in multiple layers

**Good**: Validate once at the entry point

### Mistake 3: Leaky Abstractions

**Bad**: Component knows about database schema

**Good**: Each layer only knows its neighbors

---

## Checklist for Cross-Layer Features

Before implementation:
- [ ] Mapped the complete data flow
- [ ] Identified all layer boundaries
- [ ] Defined format at each boundary
- [ ] Decided where validation happens

After implementation:
- [ ] Tested with edge cases (null, empty, invalid)
- [ ] Verified error handling at each boundary
- [ ] Checked data survives round-trip

---

## Cross-Platform Template Consistency

In Trellis, command templates (e.g., `record-session.md`) exist in **multiple platforms** with identical or near-identical content. This is a cross-layer boundary.

### Checklist: After Modifying Any Command Template

- [ ] Find all platforms with the same command: `find src/templates/*/commands/trellis/ -name "<command>.*"`
- [ ] Update all platform copies (Markdown `.md` and TOML `.toml`)
- [ ] For Gemini TOML: adapt line continuations (`\\` vs `\`) and triple-quoted strings
- [ ] Run `/trellis:check-cross-layer` to verify nothing was missed

**Real-world example**: Updated `record-session.md` in Claude to use `--mode record`, but forgot iFlow, Kilo, OpenCode, and Gemini — caught by cross-layer check.

---

## Generated Runtime Template Upgrade Consistency

Some generated files are both documentation and runtime input. In Trellis,
`.trellis/workflow.md` is parsed by `get_context.py`, `workflow_phase.py`,
SessionStart filters, and per-turn hooks. Template changes must be validated
against both fresh init and upgrade paths.

### Checklist: After Modifying A Runtime-Parsed Template

- [ ] Identify every runtime parser that reads the template, not just the file
  writer that installs it
- [ ] Check whether relevant syntax lives outside obvious managed regions
  such as tag blocks
- [ ] Verify fresh `init` output and a versioned `update` scenario that writes
  the older `.trellis/.version`
- [ ] Add an upgrade regression using an older pristine template fixture, then
  assert the installed file reaches the current packaged shape
- [ ] Update the backend spec that owns the runtime contract

**Real-world example**: Codex inline mode changed workflow platform markers from
`[Codex]` / `[Kilo, Antigravity, Windsurf]` to `[codex-sub-agent]` /
`[codex-inline, Kilo, Antigravity, Windsurf]`. Fresh init was correct, but
`trellis update` only merged `[workflow-state:*]` blocks and preserved stale
markers outside those blocks. Result: upgraded projects got new hook scripts
but old workflow routing, so `get_context.py --mode phase --platform codex`
could return empty Phase 2.1 detail.

---

## Mode-Detection Probe Checklist

When a CLI auto-detects a mode by probing a remote resource (e.g., checking if `index.json` exists to decide marketplace vs direct download):

### Before implementing:
- [ ] Probe runs in **ALL** code paths that use the result (interactive, `-y`, `--flag` combos)
- [ ] 404 vs transient error are distinguished — don't treat both as "not found"
- [ ] Transient errors **abort or retry**, never silently switch modes
- [ ] Shared state (caches, prefetched data) is **reset** when context changes (e.g., user switches source)
- [ ] **Shortcut paths** (e.g., `--template` skipping picker) must have the same error-handling quality as the probed path — check that downstream functions don't call catch-all wrappers

### After implementing:
- [ ] Trace every path from probe result to the mode-decision branch — no fallthrough
- [ ] External format contracts (giget URI, raw URLs) are tested or at least documented as comments
- [ ] Metadata reads consume a complete response or use a streaming parser — never parse a fixed-size prefix as full JSON
- [ ] When reconstructing a composite identifier from parsed parts, verify **all** fields are included and in the **correct position** (e.g., `provider:repo/path#ref` not `provider:repo#ref/path`)
- [ ] Verify that **action functions** called after a shortcut don't internally use the old catch-all fetch — they must use the probe-quality variant when error distinction matters

**Real-world example**: Custom registry flow had 8 bugs across 3 review rounds: (1) probe only ran in interactive mode, (2) transient errors fell through to wrong mode, (3) giget URI had `#ref` in wrong position, (4) prefetched templates leaked across source switches, (5) `--template` shortcut bypassed probe but `downloadTemplateById` internally used catch-all `fetchTemplateIndex`, turning timeouts into "Template not found".

**Real-world example**: Agent-session update hints fetched npm `latest` metadata with `response.read(4096)` and then parsed it as complete JSON. The `@mindfoldhq/trellis` package metadata exceeded 4 KB, so the JSON was truncated, parse failed silently, and the first session injection showed no update hint. Fix: read the complete response before parsing, and add a regression where `version` is followed by an 8 KB metadata tail.

---

## When to Create Flow Documentation

Create detailed flow docs when:
- Feature spans 3+ layers
- Multiple teams are involved
- Data format is complex
- Feature has caused bugs before
