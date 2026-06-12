# Improve Trellis Project Guidelines

## Goal

Refresh `.trellis/spec/` so future AI development sessions get practical, project-specific guidance for XReadAgent's actual architecture: Python backend sidecar, React/Vite renderer, Electron desktop shell, workspace filesystem, job/event protocol, and cross-layer contracts.

## Requirements

- Replace template-style spec prose with evidence-backed conventions from the current repository.
- Keep the work scoped to Trellis metadata and specs; do not modify product source code.
- Restore or create spec layers that match the actual codebase: backend, frontend, electron, and cross-layer guidance.
- Update `.trellis/config.yaml` package mapping if needed so `get_context.py --mode packages` reflects the real backend/frontend/electron ownership boundaries.
- Preserve existing user WIP and uncommitted product-code changes.
- Ensure spec indexes match the final guideline files and contain clear pre-development and quality-check guidance.

## Acceptance Criteria

- [x] `.trellis/spec/` contains no template placeholders such as "To fill", "To be filled", or "Replace with your actual structure".
- [x] Backend specs document local FastAPI/Pydantic/workspace/job/LLM lazy-import/testing conventions with source file references.
- [x] Frontend specs document local React/TanStack Query/API/platform/UI/testing conventions with source file references.
- [x] Electron specs document sidecar lifecycle, preload IPC, security boundaries, startup/restart behavior, packaging paths, and tests with source file references.
- [x] Cross-layer specs document shared HTTP/WS casing, workspace path safety, job event contracts, and sidecar/frontend integration points.
- [x] `python ./.trellis/scripts/get_context.py --mode packages` shows useful package/spec-layer discovery for future tasks.

## Definition of Done

- Specs are source-backed and concise enough to be loaded during implementation.
- Index files link to all relevant guideline files.
- Package discovery works after config updates.
- Placeholder search passes.
- A final quality pass records any remaining risks.

## Technical Approach

Use the `trellis-spec-bootstarp` workflow: inspect the real code first, then reshape `.trellis/spec/` around actual ownership boundaries. The repo evidence already shows three active implementation areas:

- `backend/src/xreadagent` and `backend/tests`: FastAPI sidecar, agents, workspace/wiki storage, translation, MCP, CLI.
- `frontend/src` and `frontend/tests`: React 19, Vite, TanStack Query/Router, shadcn/Radix-style UI, renderer-side API and Electron platform boundary.
- `electron/src` and `electron/tests`: Electron main/preload, Python sidecar lifecycle, app startup, tray/menu/deep links, packaging scripts.

## Out of Scope

- Product code edits under `backend/`, `frontend/`, or `electron/`.
- Rewriting the Trellis workflow engine or scripts.
- Restoring archived task data that is currently deleted in the working tree.
- Running heavy integration tests such as BabelDOC or MinerU.

## Technical Notes

- Existing backend spec files are mostly template placeholders.
- Existing frontend/electron spec directories are deleted in the current working tree; new specs should be regenerated from current source rather than copied from a template.
- There are many unrelated uncommitted changes in this workspace, including product-code WIP. Treat them as user-owned unless this task explicitly touches them.
