# IPC And Security

## Window Security Defaults

Main windows should keep:

```ts
contextIsolation: true
nodeIntegration: false
preload: path.join(__dirname, "preload.js")
```

Reference file: `electron/src/main.ts`.

## Preload Boundary

`electron/src/preload.ts` exposes a minimal typed `ElectronAPI` through `contextBridge.exposeInMainWorld("electronAPI", api)`.

When adding native capability:

- Add a typed method or listener to `ElectronAPI`.
- Implement the IPC call in preload.
- Implement the matching `ipcMain.handle` or `ipcMain.on` in `main.ts`.
- Update `electron/src/preload.d.ts` / frontend Electron types if needed.
- Consume it through `frontend/src/lib/platform.ts` or a narrow wrapper, not direct random component access.

## Dialogs And File Paths

Native folder/file selection belongs in Electron main process IPC handlers. Current filters for document import accept `pdf`, `docx`, `html`, `htm`, `md`, and `txt`. Frontend drag-and-drop suffix checks mirror this list in `frontend/src/lib/use-workspace-actions.ts`; update both together.

`webUtils.getPathForFile(file)` is exposed through preload for dropped files. Renderer code should treat an empty string as failure to resolve a real filesystem path.

## External Navigation

Install external link handlers on the main window. Allowed local renderer origins are:

- Vite dev origin.
- `http://127.0.0.1:{sidecarPort}` for packaged sidecar-served UI.

External `http(s)` links should open in the system browser; navigation away from local renderer origins should be blocked.

Reference file: `electron/src/external-links.ts`.

## Deep Links And File Opens

Deep links and `.xread` file opens target the React router. `main.ts` queues them when the current window is still the loading screen and dispatches them after the renderer `did-finish-load`.

Do not send router messages to `data:` loading screens.

Reference files: `electron/src/main.ts`, `electron/src/deeplink.ts`, `electron/src/startup.ts`.

## Anti-Patterns

- Do not enable Node integration in the renderer.
- Do not expose raw `ipcRenderer` to the renderer.
- Do not pass arbitrary user strings into `executeJavaScript`; the current sidecar-port injection is a trusted number only.
- Do not create broad preload APIs when a narrow method will do.
- Do not duplicate Electron IPC event names without centralizing types.
