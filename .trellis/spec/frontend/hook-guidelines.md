# Hook Guidelines

> How hooks are used in the renderer.

---

## Built-in hook usage

Standard React 19 rules, plus:

- Always destructure `useState` setters at the call site; don't store the setter on a ref to "share it later" — pass it down explicitly or use Context.
- `useEffect` for browser API subscriptions only (`matchMedia` listener in `lib/theme.tsx`). Don't use `useEffect` to derive state from props; compute it inline (e.g. `const resolvedTheme = theme === "system" ? system : theme;` in `theme.tsx`).
- `useMemo` / `useCallback` are used when the value is the body of a Context (`theme.tsx` memoizes the context value). Don't add them speculatively to other call sites — they cost more than they save when the inputs are primitives.
- Hooks may only be declared inside components or other hooks; the ESLint plugin `react-hooks` (configured in `eslint.config.js`) catches violations.

---

## Custom hook patterns

Only one custom hook exists so far: `useTheme()` in `frontend/src/lib/theme.tsx`. It is also the template for any future "shared stateful logic" hook. The pattern:

1. Define a `Context` with a value type and a `null` default — never a fake "valid" default value; that masks missing-provider bugs.
2. Co-locate the `Provider` component in the same file. The provider owns the `useState` / `useEffect` machinery and exposes a stable, memoized object via `value`.
3. Export the hook (`useFoo`) and the provider (`FooProvider`) from the same file. Add `// eslint-disable-next-line react-refresh/only-export-components` directly above the hook export — fast refresh treats the file as a non-component module otherwise.
4. The hook calls `useContext(FooContext)` and throws if it returns `null`: `throw new Error("useFoo must be used inside <FooProvider>")`. This converts the "forgot the provider" bug from a runtime null-deref into a clear error.

```tsx
// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
```

When SSR-safety is relevant (storage, `matchMedia`), guard `typeof window === "undefined"` (`readSystem`, `readStored` in `theme.tsx`). The renderer runs only in a browser/Electron context today, but keeping the guard means tests stay clean and Phase 3 doesn't have to retrofit.

---

## Data fetching: TanStack Query

All sidecar reads go through `@tanstack/react-query`. The provider is mounted in `app.tsx` with:

```tsx
defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } }
```

Two project-wide rules:

- **Always provide a `queryKey` as a literal array** — `["healthz"]`, `["paper", slug]`, `["queries", topic]`. Strings only; don't put functions, objects, or `new Date()` into a key.
- **Always pass the typed `queryFn` from `lib/api.ts`** — never inline `fetch` calls in components. The api layer is the only place that knows about `ApiError`, `apiBase`, and the JSON contract.

`HealthBanner` (`frontend/src/components/shell/health-banner.tsx`) is the canonical example: a `useQuery` with `refetchInterval: 5_000`, `retry: false` (the sidecar is local — retries hide a real failure), and a `selectState` helper that maps `{ isPending, isError, error, version }` to a presentational state. Keep the mapping pure and outside the component when it gets non-trivial — it makes the unit easy to test.

**Mutations** (`useMutation`) land in Phase 2 when ingest/crystallize endpoints exist. When you add them: `onSuccess` invalidates the relevant query keys via `queryClient.invalidateQueries({ queryKey: ["..."] })`. Don't optimistically mutate cache values until there's a real product reason — the sidecar is local and round-trip is cheap.

---

## Data streaming: WebSocket subscriptions

Some sidecar endpoints push events instead of returning a value — `WS /ws/jobs/{job_id}` streams BabelDOC stage events through the lifetime of a translation job. Push streams are the **only** carve-out from "all sidecar reads go through TanStack Query": there is no request/response to cache, and the data flow is reduce-into-state, not snapshot-and-render.

The canonical example is `components/reader/translate-dialog.tsx`. The pattern, in order:

1. **Hold the socket in a `useRef`, not state**. Re-creating the socket on every render leaks connections; storing it in state retriggers reducers when the WS identity changes. The ref holds `WebSocket | null`.
2. **Reduce events into a single state shape**. `setRun((prev) => reduce(prev, payload))` — a pure reducer mapping `(state, event) -> state` is easy to unit-test in isolation and keeps the component body small. Don't sprinkle `setX(...)` calls across an `if`-ladder over `event.type`.
3. **Two cleanup effects, not one**:
   - On the open/close flag flipping to closed: `wsRef.current?.close()` and reset state to the initial reducer value. This handles the user dismissing the dialog mid-job.
   - On unmount: a second `useEffect(() => () => wsRef.current?.close(), [])` so a parent unmount during an in-flight job still tears the socket down. The two effects look redundant but cover different paths.
4. **Inject the constructor for tests**. Accept an optional `websocketFactory?: (url: string) => WebSocket` prop; default to `(u) => new WebSocket(u)`. Tests pass a mock socket whose `dispatchEvent` triggers reducer transitions deterministically. Don't reach for `vi.stubGlobal("WebSocket", ...)` — per-component injection is local and composable.
5. **Build the URL through the api layer**. `buildJobEventsWsUrl(jobId)` lives in `lib/api.ts` alongside `apiBase` / `wsBase`; components never concatenate `ws://localhost:...` by hand. Same rationale as `lib/api.ts` ownership of HTTP URLs: dev proxy + future Electron port resolution change once.
6. **Swallow parse failures, surface socket failures**. The backend serializes events through Pydantic — a malformed payload would be a backend bug, not a UI signal, so the `JSON.parse` catch block silently drops it. A `socket.onerror` event, by contrast, is real network state and must flip the reducer into `errored`.

```tsx
const wsRef = React.useRef<WebSocket | null>(null);

React.useEffect(() => {
  if (!open && wsRef.current !== null) {
    wsRef.current.close();
    wsRef.current = null;
    setRun(INITIAL_STATE);
  }
}, [open]);

React.useEffect(() => () => { wsRef.current?.close(); wsRef.current = null; }, []);

const start = async () => {
  const { jobId } = await postTranslate({ /* ... */ });
  const factory = websocketFactory ?? ((u) => new WebSocket(u));
  const socket = factory(buildJobEventsWsUrl(jobId));
  wsRef.current = socket;
  socket.addEventListener("message", (e: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(e.data) as TranslationEvent;
      setRun((prev) => reduce(prev, payload));
    } catch { /* malformed — backend bug, not UI signal */ }
  });
  socket.addEventListener("error", () => {
    setRun((prev) => ({ ...prev, status: "errored", errorMessage: "WebSocket error" }));
  });
};
```

When NOT to use this pattern:

- One-shot reads (`/healthz`, `/api/translations/manifest`) → TanStack Query.
- Mutations that don't stream progress (`POST /api/crystallize` if it just returns a result) → `useMutation`.
- Anything you'd want to cache across components → cache doesn't fit a push stream.

---

## Router hooks

- `useRouterState()` for reading the current location (e.g. computing sidebar active state — see `app-sidebar.tsx`).
- `useParams({ from: "/paper/$slug" })` for typed route params (`paper.tsx`).
- Don't read `window.location` directly. The router's `Register` augmentation in `router.tsx` makes all of these strongly typed; bypassing them throws away that safety.

---

## Naming conventions

- `useFoo` for all hooks (enforced by `react-hooks` ESLint plugin via the `use*` rule).
- One hook per file in `lib/` (no batched `hooks.ts`). Pair with its provider/context in the same file when the hook reads context.
- Test files mirror the source path: `tests/lib/theme.test.tsx` for `lib/theme.tsx`.

---

## Common mistakes

- **Calling `setState` inside `useMemo`** — React 19 will throw "setState while rendering". If derived state needs a callback, model it as `useState(() => initial)` for one-time init, or `useEffect` for subscriptions.
- **Inlining `fetch` in a component to "save a hop"** — breaks `ApiError` handling and bypasses the dev proxy. Add the call to `lib/api.ts` first.
- **Using `useEffect` to sync URL state into local state** — use `useRouterState` / `useParams` instead.
- **Forgetting the `useTheme` provider check** when you copy-paste the pattern — without the `if (!ctx) throw` the consumer crashes with a confusing `Cannot read property of null` instead of a useful message.
- **Storing TanStack Query data in `useState`** to "make it easier to mutate". The query cache is already mutable via `queryClient.setQueryData`. Duplicating it desyncs the UI.
