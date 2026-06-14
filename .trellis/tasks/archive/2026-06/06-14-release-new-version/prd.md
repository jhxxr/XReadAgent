# Release v0.0.11

## Goal

Publish the next XReadAgent release by bumping the project version from 0.0.10 to
0.0.11, committing the version bump, tagging `v0.0.11`, and pushing the commit
and tag so the GitHub Release workflow can build and publish the installer.

## Requirements

* Use the repository release flow documented in `README.md`.
* Bump all tracked version locations via `node scripts/bump-version.mjs 0.0.11`.
* Keep version locations synchronized: `pyproject.toml`, frontend/electron
  `package.json`, `backend/src/xreadagent/__init__.py`, and `uv.lock`.
* Commit the version bump with the existing release commit style.
* Create tag `v0.0.11` on the release bump commit.
* Push `main` and `v0.0.11` to `origin` to trigger the Release workflow.

## Acceptance Criteria

* [ ] Version files all report `0.0.11`.
* [ ] Working tree is clean after the release commit and tag.
* [ ] `main` is pushed to `origin`.
* [ ] Tag `v0.0.11` exists locally and is pushed to `origin`.

## Definition of Done

* Version bump command succeeds.
* Targeted release sanity checks pass.
* Commit and tag are created.
* Remote push succeeds or any authentication/network blocker is reported clearly.

## Technical Approach

Use the existing release helper rather than editing files by hand. Because the
existing tags progress sequentially from `v0.0.1` through `v0.0.10`, the new
release is the next patch release, `v0.0.11`.

## Decision (ADR-lite)

Context: The user requested a new release without specifying a version. The repo
uses sequential pre-1.0 patch releases and has a helper script for synchronized
version updates.

Decision: Publish `v0.0.11` using the documented helper, commit, tag, and push
flow.

Consequences: The GitHub Release workflow remains the source of release asset
creation. If the remote rejects the push, local commit/tag state will still be
available for retry.

## Out of Scope

* Manual GitHub Release creation outside the existing workflow.
* Changing release workflow behavior.
* Adding release notes beyond GitHub's generated release notes.

## Technical Notes

* Latest fetched local tag before this task: `v0.0.10`.
* `README.md` says project version lives in five places and must be bumped with
  `node scripts/bump-version.mjs <version>`.
* `.github/workflows/release.yml` triggers on `v*` tag pushes and verifies the
  tag version matches `pyproject.toml`.
