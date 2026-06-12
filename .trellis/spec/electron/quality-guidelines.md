# Quality Guidelines

## Required Checks

Run from `electron/`:

```bash
pnpm typecheck
pnpm test
pnpm build
```

CI also runs targeted e2e sidecar lifecycle coverage:

```bash
pnpm test -- --run tests/e2e/sidecar-lifecycle.test.ts
```

## Unit Test Boundaries

Electron tests use Vitest in Node mode (`electron/vitest.config.ts`). Prefer pure functions and injectable dependencies so tests do not need to spawn real Electron windows or Python processes.

Reference examples:

- `electron/tests/sidecar.test.ts`: regex, Python path resolution, venv site-packages, environment construction, timeout behavior.
- `electron/tests/startup.test.ts`: renderer URL decisions.
- `electron/tests/deeplink.test.ts`: deep link parsing.
- `electron/tests/external-links.test.ts`: navigation guard behavior.

## Sidecar Changes Need Regression Tests

Any change to these areas needs tests:

- `SIDECAR_READY_RE`
- timeout behavior
- production Python path / `PYTHONPATH` construction
- sidecar restart info/status shape
- frontend path injection through `XREAD_FRONTEND_DIR`
- renderer URL readiness decisions

## Packaging Awareness

Packaging scripts and release workflows expect frontend and backend resources under Electron resources:

- bundled Python interpreter
- bundled Python venv
- backend source
- frontend dist

When changing build scripts, check `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `electron/scripts`, and `electron/build/README.md`.

## Anti-Patterns

- Do not add tests that require a real packaged app unless they are isolated under an explicit e2e path.
- Do not rely on `process.resourcesPath` in tests without injecting a resources path.
- Do not make startup behavior depend on DevTools or dev-only globals.
- Do not change import/output module format without checking `electron/package.json`, tsconfig, and build scripts.
