# Frontend Development Guidelines

Applies to React/TypeScript code under `frontend/src` and tests under `frontend/tests`.

The frontend is a Vite + React 19 renderer that runs both in browser dev mode and inside Electron. It talks to the Python sidecar through HTTP and WebSocket APIs, and it reaches native desktop capabilities only through the preload bridge exposed as `window.electronAPI`.

## Pre-Development Checklist

- Read [Architecture](./architecture.md) before adding routes, API calls, or platform behavior.
- Read [State And API](./state-and-api.md) before changing TanStack Query usage, sidecar requests, WebSocket jobs, or workspace path state.
- Read [UI Guidelines](./ui-guidelines.md) before changing components or routes.
- Read [Quality Guidelines](./quality-guidelines.md) before finishing frontend work.
- For backend contract changes, also read `../cross-layer/index.md`.

## Quality Check

Run commands from `frontend/`:

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Use targeted Vitest files while iterating, especially for routes, API helpers, platform detection, and job streams.

## Local Rules At A Glance

- Use `@/` imports for source modules; Vite and Vitest both map it to `frontend/src`.
- Use `frontend/src/lib/api.ts` for sidecar HTTP/WS calls; do not hardcode sidecar URLs in components.
- Use `frontend/src/lib/platform.ts` for browser-vs-Electron behavior.
- Use TanStack Query for server state and mutations.
- Keep Electron-only workflows gated by `isElectron()` and provide browser-mode fallbacks.
- Keep route modules lazy when they pull heavy dependencies such as `pdfjs-dist` or `react-markdown`.
