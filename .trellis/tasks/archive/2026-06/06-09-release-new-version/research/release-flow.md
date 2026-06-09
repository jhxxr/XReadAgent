# Release Flow Research

## Question

Which version values and release workflow contracts need to be checked before publishing a new
XReadAgent release?

## Findings

* `git fetch --tags origin` completed successfully before version selection.
* `git ls-remote --tags origin` shows remote tags through `v0.0.5`.
* Local `git tag --sort=-v:refname` also shows `v0.0.5` as the highest semver tag.
* `pyproject.toml`, `frontend/package.json`, and `electron/package.json` are at `0.0.5`.
* `uv.lock` stores the editable first-party package version and is updated when `uv run` rebuilds
  the local project after the `pyproject.toml` version bump.
* `backend/src/xreadagent/__init__.py` is stale at `__version__ = "0.0.2"` even though runtime
  API/CLI version output primarily uses installed package metadata through `importlib.metadata`.
* `.github/workflows/release.yml` triggers on pushed tags matching `v*`.
* The release workflow runs `uv sync --frozen`, builds Windows artifacts, uploads
  `electron/release/*.exe`, then creates the GitHub Release with `softprops/action-gh-release`.
* The macOS job is intentionally disabled (`if: false`) per the Electron release spec.
* `.trellis/spec/electron/index.md` requires `electron-builder` packaging steps to avoid publish
  mode and keep GitHub Release creation in the dedicated release job.

## Recommendation

Publish `v0.0.6` as the next patch release. Update all first-party version metadata discovered by
the search, include `uv.lock`, commit the bump, tag that commit, push `main`, then push `v0.0.6`
to trigger the release workflow.
