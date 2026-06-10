# Release v0.0.7

## Goal

Publish a new XReadAgent patch release that includes the latest PDF import error-detail fix and
follows the existing tag-driven GitHub Actions release workflow.

## What I Already Know

* User requested publishing a new release.
* Remote tags were refreshed with `git fetch --tags origin`.
* Latest local and remote release tag is `v0.0.6`; the next patch release is `v0.0.7`.
* Current release metadata sources are all `0.0.6`:
  `pyproject.toml`, `uv.lock`, `frontend/package.json`, `electron/package.json`, and
  `backend/src/xreadagent/__init__.py`.
* Local `main` is 3 commits ahead of `origin/main`, including the import error-detail fix and
  Trellis archive/journal commits.
* `.github/workflows/release.yml` triggers on `v*` tags, builds the Windows installer, and creates
  the GitHub Release with generated notes. The macOS job remains intentionally disabled.

## Requirements

* Bump XReadAgent release metadata from `0.0.6` to `0.0.7`.
* Keep `uv.lock` synchronized with `pyproject.toml` because release CI runs `uv sync --frozen`.
* Commit the version bump on `main`.
* Push `main` to `origin`.
* Create and push tag `v0.0.7` to trigger the Release workflow.
* Verify that the remote tag exists and, when possible, inspect the GitHub Actions run status.

## Acceptance Criteria

* [x] `pyproject.toml` version is `0.0.7`.
* [x] `uv.lock` editable `xreadagent` package version is `0.0.7`.
* [x] `frontend/package.json` version is `0.0.7`.
* [x] `electron/package.json` version is `0.0.7`.
* [x] `backend/src/xreadagent/__init__.py` `__version__` is `0.0.7`.
* [x] Local release-relevant checks pass.
* [x] Commit containing the version bump is created.
* [x] `main` is pushed to `origin`.
* [x] Tag `v0.0.7` is pushed to `origin`.
* [x] Release workflow trigger/status is checked if credentials/tools allow it.

## Definition of Done

* Version metadata is consistent across first-party package/app files.
* Existing release workflow is not changed unless inspection reveals a blocker.
* Release tag is pushed, or a concrete external blocker is reported.
* Trellis task is archived after the publish attempt is complete.
* Session progress is recorded in the developer journal.

## Technical Approach

Follow the established patch release flow: bump metadata to `0.0.7`, regenerate/check the lockfile,
run targeted release checks, commit the bump, push `main`, create `v0.0.7` at the release commit,
then push the tag.

## Decision (ADR-lite)

**Context**: The latest published tag is `v0.0.6`, and `main` contains a user-facing PDF import
error-detail fix not included in that release.

**Decision**: Publish `v0.0.7` as a patch release from current `main`.

**Consequences**: The release will include all current commits ahead of `origin/main`, and
publication depends on GitHub Actions completing the Windows-only release workflow.

## Out of Scope

* Re-enabling macOS packaging.
* Changing installer signing, auto-update, artifact naming, or release-note policy.
* Upgrading dependencies unrelated to the version bump.

## Technical Notes

* Relevant spec: `.trellis/spec/electron/index.md`, especially Release Packaging & Publish
  Contract.
* Relevant workflow: `.github/workflows/release.yml`.
* Prior release reference: `.trellis/tasks/archive/2026-06/06-09-release-new-version/`.
* Version bump commit: `106037c`.
* Release workflow run: `https://github.com/jhxxr/XReadAgent/actions/runs/27250830127`.
* GitHub Release: `https://github.com/jhxxr/XReadAgent/releases/tag/v0.0.7`.
* Windows installer asset: `XReadAgent-Setup-0.0.7.exe`.
