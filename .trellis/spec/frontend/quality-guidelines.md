# Quality Guidelines

## Required Checks

Run from `frontend/`:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

CI runs the same sequence after `pnpm install --frozen-lockfile`.

## Testing Patterns

Frontend tests use Vitest + jsdom + Testing Library. The config is `frontend/vitest.config.ts`, and setup lives in `frontend/tests/setup.ts`.

Test at the same boundary the change affects:

- API helpers: `frontend/tests/lib/api.test.ts`.
- Platform behavior: `frontend/tests/lib/platform.test.ts`.
- Job stream behavior: `frontend/tests/lib/ingest-job.test.ts`.
- Routes: `frontend/tests/routes/*.test.tsx`.
- Shared components: `frontend/tests/components/**`.

Use injection seams such as `websocketFactory` rather than real network sockets in unit tests.

## Type Safety

- Keep `frontend/src/types/api.ts` aligned with backend Pydantic models.
- Prefer readonly arrays in API types where the frontend should not mutate response data.
- Use explicit discriminated unions for event streams.
- Do not use `any`; if a backend payload is unknown, parse/narrow it at the boundary.

## Build And Bundle Awareness

Keep expensive dependencies lazy. Route-level lazy loading protects the initial workspace screen from `pdfjs-dist`, `react-markdown`, and similar route-specific packages.

When adding a large dependency, document where it loads and add a test if routing/lazy behavior matters.

## Anti-Patterns

- Do not rely on real Electron APIs in jsdom tests; mock or inject the boundary.
- Do not let TypeScript errors hide behind Vite build success; run `pnpm typecheck`.
- Do not duplicate API response parsing across components.
- Do not update backend API shape without frontend type and test updates.
