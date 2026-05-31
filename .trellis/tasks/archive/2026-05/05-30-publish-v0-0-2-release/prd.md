# Publish v0.0.2 Release

## Goal

Publish a new patch release that includes the Release workflow Python bundling fix committed
in `eeb58c5`.

## Requirements

* Bump project package versions from `0.0.1` to `0.0.2` for the release-facing packages.
* Commit the version bump before tagging.
* Push `main` to `origin`.
* Create and push tag `v0.0.2` so the Release workflow runs from the fixed commit.
* Verify the GitHub Actions release run starts, and report the run URL/status.

## Acceptance Criteria

* [x] `pyproject.toml` version is `0.0.2`.
* [x] `backend/src/xreadagent/__init__.py` version is `0.0.2`.
* [x] `electron/package.json` version is `0.0.2`.
* [x] `frontend/package.json` version is `0.0.2`.
* [ ] `main` is pushed to `origin`.
* [ ] Tag `v0.0.2` exists on the remote.
* [ ] Release workflow is triggered for tag `v0.0.2`.

## Definition of Done

* Version bump is committed.
* Release tag is pushed.
* Workflow status/run link is reported to the user.

## Technical Approach

Patch the four version sources directly, run lightweight checks that do not require full
packaging, commit as `chore(release): bump version to v0.0.2`, push `main`, tag the release
commit as `v0.0.2`, then push the tag.

## Out of Scope

* Feature changes.
* Changing release workflow behavior beyond what was already fixed.
* Reusing or moving the existing `v0.0.1` tag.

## Technical Notes

* Current remote tag: `v0.0.1` points at `6e467e2`.
* Local `main` includes:
  * `eeb58c5 fix(release): correct python bundle archive handling`
  * `99edc43 chore(task): archive 05-30-fix-release-python-bundle`
  * `d527472 chore: record journal`
* Verification before release:
  * version consistency check passed
  * `python -m uv lock --check`
  * `python -m pytest backend/tests/test_cli.py backend/tests/test_api.py`
  * `cd electron && pnpm typecheck`
  * `cd electron && pnpm test -- bundle-python.test.ts`
  * `cd frontend && pnpm typecheck`
  * `cd frontend && pnpm test`
