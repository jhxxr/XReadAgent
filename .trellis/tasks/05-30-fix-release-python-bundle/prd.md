# Fix Release Python Bundle Failure

## Goal

Fix the Release workflow failure reported from GitHub Actions run `26645229773`, job
`78528836517`, where the `Build (Windows)` job fails during the `Bundle Python` step.
The same run also shows `Build (macOS)` failing at the same step, so the fix should make
the Python bundling script robust for both release targets.

## Requirements

* Correct the Electron Python bundling script so it uses python-build-standalone asset
  names and archive layouts that actually exist for Windows and macOS.
* Keep the packaged runtime layout contract unchanged:
  * Windows: `electron/resources/python/python.exe`
  * macOS: `electron/resources/python/bin/python3`
* Keep the release workflow command unchanged unless the script cannot reasonably own
  the fix: `cd electron && pnpm pack:python`.
* Add a lightweight verification path so archive URL generation can be tested without
  downloading and installing the full Python runtime.

## Acceptance Criteria

* [x] `electron/scripts/bundle-python.mjs` generates a valid Windows x64
  python-build-standalone asset URL for tag `20241219`.
* [x] The script still generates valid macOS x64 and arm64 asset URLs for tag `20241219`.
* [x] The script extracts `.tar.gz` archives whose top-level directory is `python/`
  on Windows as well as POSIX platforms.
* [x] A local check verifies URL generation and/or archive metadata without requiring a
  full release build.
* [x] Electron typecheck/tests relevant to the touched script pass, or any unavailable
  checks are documented.

## Definition of Done

* The failure cause is documented in the task research notes.
* The code change is scoped to release Python bundling behavior.
* Quality checks are run after the change.
* Any reusable knowledge is considered for `.trellis/spec/` update.

## Technical Approach

Update `electron/scripts/bundle-python.mjs` to map Windows to the
`x86_64-pc-windows-msvc` python-build-standalone platform suffix and to use the release's
`.tar.gz` archive format instead of a non-existent `.zip`. Preserve the post-extraction
layout by extracting to a temporary directory, locating the archive's `python/` directory,
and moving its contents into `electron/resources/python/`.

If the script gains a tiny test mode or exported helper, prefer a low-impact CLI flag over
introducing a new test framework dependency.

## Decision (ADR-lite)

**Context**: The GitHub Actions job metadata shows both platform build jobs failing in
`Bundle Python`. The full logs require repository admin rights, but GitHub's public release
asset API confirms the script's Windows archive filename does not exist.

**Decision**: Fix the filename/platform mapping in the bundling script and add a lightweight
verification path for generated metadata.

**Consequences**: Release CI should reach the venv/dependency installation phase instead of
failing immediately on archive download/extraction. Future python-build-standalone asset
renames can be caught without running the full packager.

## Out of Scope

* Changing the Electron installer configuration unrelated to Python bundling.
* Reworking backend dependency selection or removing heavyweight optional dependencies.
* Signing/notarization changes for macOS artifacts.

## Research References

* [`research/python-build-standalone-assets.md`](research/python-build-standalone-assets.md)
  records the release asset names checked for the failing run.

## Technical Notes

* Failing run: <https://github.com/jhxxr/XReadAgent/actions/runs/26645229773/job/78528836517>
* Job API showed `Build (Windows)` and `Build (macOS)` both failed at step `Bundle Python`.
* Full Actions logs could not be downloaded anonymously; GitHub API returned `403 Must have
  admin rights to Repository`.
* Relevant spec: `.trellis/spec/electron/index.md`, especially the Release Python Bundle
  Contract.
* Local full `pnpm pack:python` could not run because this machine has no `uv` on PATH; the
  release workflow installs `uv` before running the same command. Lightweight URL checks,
  metadata tests, Electron tests, and Electron typecheck passed.
