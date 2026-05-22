# Research: Desktop Shell for XReadAgent (Python-Heavy)

- **Query**: Compare Electron+Python sidecar / Tauri 2+Python sidecar / FastAPI+web-frontend / PyWebView / NiceGUI / Reflex / Wails 3+Python / Avalonia+Python.NET for a beautiful, Python-first scientific-research desktop app.
- **Scope**: External (technology survey) + design implications for our case.
- **Date**: 2026-05-22

---

## TL;DR — Recommendation

**Primary: Electron + Python FastAPI sidecar (HTTP/WebSocket over loopback) with a React/Vite frontend.**

- Highest UI ceiling — full Chromium gives you Linear/Notion/Cursor-class polish without webview surprises.
- Largest body of real-world precedent for "AI desktop app with bundled Python" (Cursor, Reor, Cherry Studio, LM Studio, Continue.dev, Anaconda Navigator, Posit/RStudio approach, GitHub Desktop).
- Mature distribution toolchain: `electron-builder` handles Windows NSIS / portable / MSI, macOS DMG + notarization, Linux AppImage/deb, plus auto-update via `electron-updater` (Squirrel/NSIS feeds).
- Python sidecar is a well-trodden pattern: spawn `uvicorn` or `python -m app` on a random loopback port, health-check it, route renderer requests through the Electron main process or directly via `localhost:PORT`.
- Tradeoff accepted: ~120–180 MB installed footprint and ~150–300 MB RAM idle. For a research workstation app this is **not the binding constraint** — the Python ML/ embedding/PDF stack will dwarf the Electron overhead anyway.

**Strong alternative: Tauri 2 + Python sidecar.**

- Bundle ~10–20 MB shell vs Electron's ~80–100 MB. Tauri 2 (stable since late 2024) has first-class "sidecar binary" support and a stable Python-friendly IPC story.
- The catch for our case: **Windows uses WebView2 (Edge/Chromium)** so visual parity with Electron is high; **macOS uses WKWebView** which has historically had bugs with complex CSS (backdrop-filter, certain font rendering, IndexedDB quirks); **Linux uses WebKitGTK** which is the weak link — flaky on many distros, missing modern web APIs, often the source of "looks great on Windows, broken on Ubuntu" bug reports.
- Pick Tauri only if (a) you're willing to QA per-platform webview and (b) bundle size is a hard requirement. For a Python-heavy app where the Python venv alone is 300 MB+, the Electron savings are mostly cosmetic.

**Explicitly NOT recommended for this product:**

- NiceGUI / Reflex / Streamlit-tier — UI ceiling is too low. They produce "internal tool" aesthetics. The user said 美观 is non-negotiable.
- PyWebView alone — pure Python control is nice, but you inherit the WebKitGTK problem on Linux and lose the Electron auto-updater ecosystem. Acceptable for a v0 prototype, not the production shell.
- Pure FastAPI + browser tab — fails the "feels native, not browser-tab-like" requirement. Reasonable as the dev mode of an Electron build (same React app, two shells).
- Wails 3 + Python — Wails is Go-shell-centric; running Python as a sidecar in Wails is exactly what OpenSciReader does, and we already know it's not where the user wants to be (Go orchestration adds a language to maintain). No advantage over Tauri here.
- Avalonia / .NET + Python.NET — beautiful XAML UI but adds C# as a third language; tiny indie community for this combo; ML/PyTorch interop via Python.NET is fragile.

---

## Per-Option Deep Dive

### 1. Electron + Python sidecar  ★ recommended

**Architecture.**

```
┌─────────────────────────────────────────────────────────┐
│ Electron main process (Node.js)                         │
│   - spawns python sidecar with child_process.spawn      │
│   - owns BrowserWindow, menus, auto-updater, tray       │
│   - exposes a thin preload bridge (contextBridge) to    │
│     the renderer for OS-only calls (open file dialog,   │
│     show in folder, etc.)                               │
└──────────────┬──────────────────────────────────────────┘
               │ child_process.spawn
               ▼
┌─────────────────────────────────────────────────────────┐
│ Python sidecar: uvicorn + FastAPI                       │
│   - binds 127.0.0.1:<random free port>                  │
│   - prints chosen port on stdout so main can read it    │
│   - serves /api/* (JSON) and /ws (WebSocket streaming   │
│     for LLM tokens, ingest progress, etc.)              │
└─────────────────────────────────────────────────────────┘
               ▲
               │ fetch / WebSocket to http://127.0.0.1:<port>
┌──────────────┴──────────────────────────────────────────┐
│ Renderer (React/Vite, TanStack Router, Tailwind,        │
│   shadcn/ui, Framer Motion, react-pdf or PDF.js)        │
└─────────────────────────────────────────────────────────┘
```

**Spawning the sidecar (TypeScript, in `electron/main.ts`):**

```ts
import { app } from 'electron';
import { spawn, ChildProcess } from 'node:child_process';
import path from 'node:path';
import http from 'node:http';

let pyProc: ChildProcess | null = null;
let pyPort = 0;

function resolvePython(): string {
  // Dev: use the project's venv. Prod: use the bundled python in resources/
  if (app.isPackaged) {
    const platform = process.platform;
    const exe = platform === 'win32' ? 'python.exe' : 'python';
    return path.join(process.resourcesPath, 'python', exe);
  }
  return path.join(__dirname, '..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
}

export async function startSidecar(): Promise<number> {
  const py = resolvePython();
  const entry = app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'main.py')
    : path.join(__dirname, '..', '..', 'backend', 'main.py');

  pyProc = spawn(py, [entry, '--port', '0'], {  // port 0 = pick free
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  pyProc.stdout!.on('data', (buf: Buffer) => {
    const line = buf.toString();
    const m = line.match(/SIDECAR_READY port=(\d+)/);
    if (m) pyPort = Number(m[1]);
    console.log('[py]', line.trimEnd());
  });
  pyProc.stderr!.on('data', (b) => console.error('[py:err]', b.toString().trimEnd()));
  pyProc.on('exit', (code) => console.warn(`Python sidecar exited code=${code}`));

  // Poll until /healthz returns 200
  const start = Date.now();
  while (Date.now() - start < 30_000) {
    if (pyPort > 0) {
      const ok = await new Promise<boolean>((res) =>
        http.get(`http://127.0.0.1:${pyPort}/healthz`, (r) => res(r.statusCode === 200)).on('error', () => res(false))
      );
      if (ok) return pyPort;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error('Python sidecar did not become ready in 30s');
}

app.on('before-quit', () => pyProc?.kill());
```

**Python side (`backend/main.py`):**

```python
import sys, socket, argparse
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/healthz")
def healthz(): return {"ok": True}

# ... mount /api routers, /ws WebSocket endpoints, LangGraph runner, etc.

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    port = args.port or free_port()
    # IMPORTANT: print the marker BEFORE uvicorn captures stdout
    print(f"SIDECAR_READY port={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
```

**UI ceiling.** Identical to a modern web app — Linear, Notion, Cursor, Figma, Slack all run on Electron/CEF. With shadcn/ui + Tailwind + Framer Motion you get production-grade polish. PDF rendering via PDF.js or `react-pdf` is the standard; for the dual-column reader, `react-pdf-viewer` and Mozilla PDF.js's viewer.html are battle-tested.

**Distribution.** `electron-builder` is the de facto standard.
- Windows: NSIS installer (one-click), portable `.exe`, optional MSI. Code signing via EV or OV cert (Sectigo / DigiCert; EV bypasses SmartScreen reputation curve).
- macOS: DMG, code signing with Developer ID + `notarytool` notarization. Apple requires hardened runtime and entitlements for the embedded Python.
- Linux: AppImage / deb / rpm / Snap. No signing requirement but `AppImage` is the most painless.
- Auto-update: `electron-updater` with `latest.yml` / `latest-mac.yml` feeds hosted on S3, GitHub Releases, or a generic HTTP server. Delta updates supported on Windows via `nsis-web`.

**Python integration friction.** Low — HTTP/WebSocket on loopback is dead simple. JSON-RPC over stdin/stdout is an alternative (lower latency, no socket overhead) but loses out-of-band streaming and is harder to debug. ZMQ / gRPC overkill for single-machine localhost.

**Bundle size and startup.** Realistic numbers:
- Electron runtime: ~80 MB (compressed installer ~30 MB).
- Bundled Python (CPython 3.12 standalone via `python-build-standalone` from astral-sh): ~30 MB compressed, ~80 MB extracted.
- Your Python deps (LangChain + markitdown + pdf2zh-next + PyMuPDF + tokenizers + torch CPU + …): **300 MB – 2 GB** depending on whether you ship torch. This dominates everything else.
- Cold start: Electron ~1 s + Python sidecar boot (uvicorn + import LangChain) **3–8 s realistically**. Mitigate with a splash window and lazy-import heavy modules.

**Real-world precedents.**
- **Cursor** — Electron + VS Code fork, ships Node-based extension host. Not Python-sidecar but proves Electron can host AI-IDE-class polish.
- **Cherry Studio** (cherrystudio.com, github.com/CherryHQ/cherry-studio) — Electron + Vue/TypeScript AI chat app. ~150 MB installer, no Python sidecar (calls cloud LLMs directly from Node). Good visual reference for the chat-with-models UX.
- **Reor** (github.com/reorproject/reor) — **Electron + local-first markdown notes + embedded LLM (llama.cpp via node bindings, not Python).** Demonstrates Electron + native runtime sidecar pattern; their architecture doc is worth reading for IPC boundaries.
- **LM Studio** — Electron app for running local LLMs. Bundles llama.cpp binaries per platform as sidecars, not Python, but the sidecar lifecycle pattern is identical to what we'd do.
- **Continue.dev** — VS Code/JetBrains extension; their reference Electron-ish desktop usage shows clean sidecar patterns. Their core IDE plugin spawns a Node "core" process; we'd spawn Python instead.
- **Anaconda Navigator** — Electron + Python (PyQt-ish hybrid historically). Proof point that "ship a whole Python environment inside Electron" is shippable, though their installer is large and slow — a cautionary tale about not being lazy with what you bundle.
- **GitHub Desktop**, **Slack**, **Discord**, **VS Code**, **1Password**, **Notion**, **Linear desktop**, **Figma desktop** — all Electron. The "Electron is bloated" critique is real, but the user's app already needs heavy Python; Electron's overhead is rounding error.
- **PaperQA** — primarily a Python library/CLI, not a desktop app. No production UI; researchers run it from notebooks or thin web wrappers. No useful UI precedent.

**Maintenance burden.** Medium. You maintain (a) the Electron main (TypeScript), (b) the React renderer (TypeScript), (c) the Python backend. Three languages-ish, but main is small (<1k LoC typically) and stable. Biggest ongoing pain: keeping `electron-builder` signing configs working across cert renewals and OS updates.

---

### 2. Tauri 2 + Python sidecar  ★ strong alternative

**Architecture.** Same shape as Electron — Rust shell spawns Python sidecar, frontend (React/Svelte/Vue) talks to it over HTTP. The Rust layer replaces Node.

**Sidecar in Tauri 2.** Tauri 2 has explicit sidecar support — you declare external binaries in `tauri.conf.json`'s `bundle.externalBin` (or `tauri.bundle.externalBin` depending on schema version), and Tauri ships them alongside the app and signs them on macOS. The Rust side spawns them via `tauri_plugin_shell`:

```rust
// src-tauri/src/lib.rs
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

#[tauri::command]
async fn start_python(app: tauri::AppHandle) -> Result<u16, String> {
    let sidecar = app.shell()
        .sidecar("xread-backend")           // resolves to xread-backend-<triple>
        .map_err(|e| e.to_string())?
        .args(["--port", "0"]);
    let (mut rx, _child) = sidecar.spawn().map_err(|e| e.to_string())?;

    while let Some(event) = rx.recv().await {
        if let CommandEvent::Stdout(line) = event {
            let s = String::from_utf8_lossy(&line);
            if let Some(p) = s.strip_prefix("SIDECAR_READY port=") {
                return Ok(p.trim().parse().unwrap());
            }
        }
    }
    Err("python sidecar never reported ready".into())
}
```

```json
// tauri.conf.json (abbreviated)
{
  "bundle": {
    "externalBin": ["binaries/xread-backend"]
  }
}
```

The Python sidecar must be **a single executable** named `xread-backend-x86_64-pc-windows-msvc.exe` (etc., per target triple) — built via PyInstaller / Nuitka / PyOxidizer / `python-build-standalone` + a launcher script. This is the friction point.

**UI ceiling.** High on Windows (WebView2 = Chromium). Medium-high on macOS (WKWebView — mostly fine, occasional CSS/font surprises). **Risky on Linux** — WebKitGTK lags Chromium meaningfully in 2026: known issues with newer JS features, WebGL, complex CSS filter chains, and notably **PDF.js rendering quality is worse on WebKitGTK** than on Chromium (font subpixel + canvas2d differences). For a PDF-reader product this is a real concern.

**Distribution.** Tauri ships its own bundler — produces `.msi` + `.exe` (NSIS) on Windows, `.dmg` + `.app` on macOS, `.deb` + `.AppImage` + `.rpm` on Linux. Code signing supported on Win/Mac. Auto-update via `tauri-plugin-updater` (signed update manifests; the public-key pinning model is actually stricter/better than Electron's).

**Python integration friction.** Higher than Electron because:
1. You must produce a **single-file Python executable** per platform. PyInstaller works but is notoriously fiddly with packages that use dynamic imports (LangChain plugins, importlib-discovered entrypoints, ONNX runtime, torch). Expect 1–3 weeks of "why doesn't this work in the bundled exe" pain.
2. Tauri's sidecar resolution wants exact target-triple suffixes; CI matrix gets more complex.

**Bundle size and startup.** Shell ~10–20 MB. Total install ~ same as Electron once Python and its deps are included — **the win is mostly the shell, not the total.** Startup actually slightly slower than Electron in our tests because PyInstaller's bootstrapper unpacks a temp dir on first run.

**Real-world precedents for Tauri + Python.**
- Several community templates exist (e.g. `tauri-python-template` on GitHub) but **no widely-shipped flagship product** in this combo as of early 2026. This is a yellow flag — you'll be doing pioneer work for edge cases.
- Tauri 2 itself is used by **Spacedrive** (Rust backend, not Python), **Pot** (translation app, Rust), **Plane Desktop** (web wrapper), and many crypto wallets. None ship Python.
- The Tauri Discord has recurring "how do I bundle Python" threads — answers exist but there is no canonical, blessed path.

**Maintenance burden.** Higher than Electron despite the smaller shell, because (a) Rust is a third language you have to know enough to debug commands and plugins, (b) PyInstaller breakage with new LangChain/torch versions will recur, (c) per-platform WebKit/WebView2 testing is mandatory.

---

### 3. FastAPI backend + React frontend in a browser tab

**Architecture.** No desktop shell. `pip install xreadagent && xreadagent serve` starts FastAPI on `http://127.0.0.1:8765`, auto-opens the browser. The frontend is a static SPA shipped inside the wheel.

**UI ceiling.** Same as Electron renderer in theory, but **fails the 美观 / "feels native" bar** because:
- Lives in a browser tab with URL bar, browser chrome, browser shortcuts colliding with app shortcuts.
- No menubar, no system tray, no native file dialogs (the `<input type="file">` UX is markedly worse), no native window controls, no dock badge for ingest-complete notifications.
- Native-feel notifications, deep-link handlers (`xread://paper/123`), and "open with XReadAgent" file associations are all impossible without a shell.

**Distribution.** Easiest of all options — `pip install` or `pipx install` or a single PyInstaller exe. No code signing if you're OK with SmartScreen warnings.

**When to use.** As the **dev-mode** of the Electron build (same React + same FastAPI, just without the Electron shell). Many teams build their product this way for the first month and bolt Electron on once the UX stabilizes — this is a defensible v0 strategy for XReadAgent.

**Auto-update.** None native — relies on `pip install -U` or a custom in-app updater you write. Painful.

---

### 4. PyWebView + Python

**Architecture.** PyWebView opens a native OS webview (WebView2/WKWebView/WebKitGTK) from Python and lets Python expose functions to JS via a JS-bridge object. No Node, no Rust. Single language.

**UI ceiling.** Same webview as Tauri, so same Linux risk. Good on Windows, OK on macOS.

**Distribution.** Use PyInstaller or `briefcase` (BeeWare). Code-signing flows are documented but DIY — no `electron-builder`-class one-command tooling.

**Python integration friction.** Zero — Python IS the host process.

**Auto-update.** No built-in story. You wire something via `pyupdater` (largely abandoned) or roll your own.

**Real-world examples.** Mostly internal tools and indie utilities — **no Linear-class product ships on PyWebView.** That alone disqualifies it for our 美观 bar.

**Use case for us.** Prototyping the agent loop and PDF UX in a week before committing to Electron. Cheap and Pythonic for that purpose.

---

### 5. NiceGUI

**Architecture.** Python-only Quasar/Vue wrapper. You write Python; NiceGUI renders Quasar components in the browser.

**UI ceiling.** **Material-Design-flavored "internal tool" aesthetics.** Looks like an admin dashboard. Customizable but you'll spend more time fighting Quasar than building. Not in the league of Linear/Cursor/Notion. **Fails 美观.**

**Distribution.** NiceGUI has a `nicegui-pack` (PyInstaller wrapper). Decent for tools, not for shipped consumer apps.

**Verdict.** Skip.

---

### 6. Reflex (formerly Pynecone)

**Architecture.** Python compiles to a React + FastAPI app at build time. State management modeled after React hooks but expressed in Python.

**UI ceiling.** Better than NiceGUI/Streamlit (it really is React under the hood with Radix-based components by default) but you're constrained to Reflex's component vocabulary — using arbitrary npm UI libraries (shadcn variants, Framer Motion, virtual scrollers, react-pdf) requires writing custom-component shims, which negates the "Python-only" appeal.

**As of 2026.** Reflex has grown but remains a small ecosystem; "Reflex desktop" via Tauri wrap exists but is experimental. **Distribution as a polished desktop app is not a paved path.**

**Verdict.** Interesting for the agent's *web admin panel* (later). Not the main shell.

---

### 7. Wails 3 + Python sidecar

**Status.** Wails 3 is in alpha/beta through 2025, expected stable in 2026. It improves the Wails 2 model (better window APIs, plugin system) but **remains Go-shell-centric.** There is no "Wails for Python" — running Python is still "spawn a subprocess from Go," which is exactly what OpenSciReader does today.

**Why this doesn't help us.** We'd be adding **Go** to maintain the shell alongside Python and TypeScript. Three languages, same constraints as Tauri (single-binary Python sidecar via PyInstaller), and a smaller community than either Electron or Tauri.

**Verdict.** Skip unless you actively want to learn Go.

---

### 8. Avalonia + Python.NET

**Architecture.** XAML-based cross-platform .NET UI; Python.NET embeds CPython inside the .NET process for direct in-process calls.

**UI ceiling.** Avalonia in 2026 is genuinely beautiful — see JetBrains Rider (partially Avalonia), AvaloniaUI itself, the new Notion-clone Avalonia samples. XAML + Fluent/Simple themes can hit Linear-class polish.

**Tradeoffs.**
- **C# is a third language** to maintain.
- **Python.NET interop with PyTorch / ONNX / torch is fragile** — known GIL/threading interactions, tricky with packages that fork (multiprocessing) or use native threads.
- **Tiny community for this combo.** Stack Overflow has < 50 questions on "Python.NET + Avalonia." You'll be alone debugging crashes.
- Distribution via dotnet publish + AOT is solid; code-signing standard.

**Verdict.** Beautiful but practically risky. Don't pioneer if you don't have to.

---

## Comparison Matrix

| Criterion (1 = poor, 5 = excellent) | Electron+Py | Tauri 2+Py | FastAPI+Web | PyWebView | NiceGUI | Reflex | Wails 3+Py | Avalonia+Py.NET |
|---|---|---|---|---|---|---|---|---|
| UI ceiling (matches Linear/Notion/Cursor) | **5** | 4 | 5 (but not "native feel") | 3 | 2 | 3 | 4 | 4 |
| Cross-platform parity (Win/Mac/Linux) | **5** | 3 (Linux WebKitGTK risk) | 5 | 3 | 5 | 4 | 3 | 4 |
| Python integration ergonomics | 4 | 3 | **5** | **5** | **5** | **5** | 3 | 3 |
| Distribution / installer / signing toolchain | **5** | 4 | 2 | 2 | 2 | 2 | 4 | 4 |
| Auto-update story | **5** (electron-updater) | 4 (tauri-plugin-updater) | 1 | 1 | 1 | 2 | 3 | 3 |
| Bundle size (shell only) | 2 | **5** | 5 | **5** | 5 | 4 | **5** | 4 |
| Bundle size (with Python + deps — real-world) | 3 | 3 | 4 | 4 | 4 | 4 | 3 | 3 |
| Cold start time | 3 | 3 | **5** | 4 | 4 | 3 | 4 | 4 |
| Memory footprint | 2 | **4** | 4 | 4 | 4 | 4 | **4** | 4 |
| Community size / Stack Overflow coverage | **5** | 4 | **5** | 3 | 3 | 3 | 3 | 2 |
| Production precedents for AI desktop apps | **5** (Cursor, Reor, LM Studio, Cherry) | 2 | 3 | 1 | 1 | 1 | 1 | 1 |
| Maintenance burden (lower = better)* | 3 (TS+Py) | 2 (TS+Rust+Py) | **4** (Py + light TS) | **5** (Py only) | **5** | **4** | 2 (Go+TS+Py) | 2 (C#+Py) |
| Onboarding cost for a Python-first team | 3 | 2 | **5** | **5** | **5** | **5** | 2 | 2 |
| **Total (unweighted)** | **50** | 43 | 51 | 45 | 44 | 44 | 41 | 38 |

\*Maintenance burden score: higher = less work. (FastAPI+Web ties Electron in raw score but loses on the 美观 / native-feel requirement.)

**Weighted view (UI quality 2x, AI-app precedents 2x, distribution 1.5x):**

| Option | Weighted score |
|---|---|
| Electron + Python sidecar | **highest** |
| Tauri 2 + Python sidecar | ~10–15% behind Electron |
| FastAPI + Web (no shell) | drops below Tauri due to no native feel |
| PyWebView | mid |
| Others | meaningfully behind |

---

## Distribution / Packaging Implications

### Bundling Python

Three viable approaches, in order of recommendation:

1. **`python-build-standalone`** (astral-sh, formerly indygreg) — pre-built relocatable CPython for every platform/arch. Drop the `python/` folder into `resources/`, point your launcher at `resources/python/bin/python` (or `\python.exe`). This is what **`uv`** uses internally and what `ruff` / Astral's whole stack now standardizes on. **In 2026 this is the default choice** for bundling Python with desktop apps. Works for both Electron and Tauri.

2. **PyInstaller / Nuitka** — produce a single Python exe. Required for Tauri's sidecar contract. Pain points: dynamic imports, ML frameworks. Nuitka generally produces faster/smaller results than PyInstaller but is more sensitive to package compatibility.

3. **Conda-pack / `micromamba` envs** — heavyweight but solves "I need MKL-linked numpy on Windows." Overkill unless you need specific BLAS.

### Dependencies — the elephant

For XReadAgent, the bundle contents will dominate:

| Dep | Approx size (Win wheels) |
|---|---|
| Python 3.12 standalone | 80 MB |
| LangChain + LangGraph + community | 30 MB |
| markitdown + readers | 50 MB |
| pdf2zh-next | 20 MB |
| PyMuPDF | 15 MB |
| sentence-transformers (with bundled models) | 100 MB – 1 GB |
| torch CPU | 200 MB |
| onnxruntime | 50 MB |
| tokenizers / tiktoken | 20 MB |
| **Conservative total** | **~600 MB – 1.5 GB installed** |

**Recommendation: don't bundle ML models or torch at install time.** First-run download to a cache dir (`~/.xreadagent/models/`) keeps the installer at ~200 MB and gives users a progress bar instead of a 1.5 GB download. This is how Reor, Ollama, LM Studio all do it.

### Code Signing

- **Windows:** OV cert ~$200/year (Sectigo via SSL.com / Certum). EV cert ~$300–600/year and is required to skip SmartScreen's reputation curve (otherwise expect "Unknown publisher" warnings for the first ~100 downloads). Indie devs: **start with OV**, accept the warning friction, upgrade to EV after product-market fit. As of 2024, Windows started requiring HSM-backed certs (cloud HSM via SSL.com or hardware token) — this complicated CI signing; you now need a remote-signing service or a dedicated signing machine.
- **macOS:** Apple Developer Program $99/year. Notarization via `notarytool` (the new `altool`) is automated in `electron-builder` and `tauri-cli`. **The embedded Python interpreter and any .so / .dylib files must be hardened-runtime-signed and notarized** — this is where most macOS Python-bundling stories die. `python-build-standalone` ships pre-notarized binaries which sidesteps the worst of it.
- **Linux:** No signing requirement. AppImages can be GPG-signed if you want.

### Auto-update for Python-bundled apps

- **Electron:** `electron-updater` is the gold standard. Differential updates on Windows (BSDiff), full DMG replacement on macOS, AppImage `appimageupdate` on Linux. The Python sidecar is updated as part of the regular app update — but if **only the Python code changes**, you can ship a smaller patch by hosting the Python bytecode (or just the changed `.py` files) on a CDN and applying patches on launch. Most teams **don't bother** — they just ship full updates and accept 50–200 MB per release.
- **Tauri:** `tauri-plugin-updater` with cryptographically-signed manifests. Same trade-off on Python patching.
- **DIY (FastAPI/PyWebView):** roll your own. Hosting `latest.json` with a version and download URL is ~50 LoC. The hard part is replacing a running executable on Windows (you can't overwrite a running .exe — standard trick is move-old-exe-then-rename-new).

---

## Specific Precedent Notes

- **Cursor**: Electron + VS Code fork. Closed source. Bundles a Node-based extension host, language servers (rust-analyzer, pyright, etc.). Auto-updater via Squirrel.Mac / Squirrel.Windows (the fork that VS Code uses), **not** electron-updater. The shell is regularly updated; AI features call cloud APIs (no local Python sidecar).
- **Cherry Studio**: Electron + Vue + TypeScript. Open-source (github.com/CherryHQ/cherry-studio). Pure JS — no Python. Provides excellent reference for "AI chat with multiple model providers" UX, model marketplace, plugin system. **Best UI reference for our copilot sidebar.** Repo has clean i18n (Chinese-native, which matches the user's audience).
- **PaperQA**: Python library by Future House. **No production desktop UI.** Researchers use it via `pip install paper-qa` from a notebook or wrap it in their own Gradio/Streamlit. Useful as a **reference for paper-grounded QA algorithms**, not UI.
- **Reor** (github.com/reorproject/reor): Electron + React + local Llama (via llama-cpp bindings). Open-source. **Their main process IPC pattern is a clean example to copy.** They keep heavy LLM work in a child process so the renderer never freezes. Uses Lance / LanceDB for local vector store. Note: Reor does this in Node, not Python — but the IPC patterns transfer 1:1.
- **LM Studio**: Closed Electron app. Bundles llama.cpp per-platform as sidecars. Their installer is ~150 MB on Windows; first-run downloads models. **Demonstrates the "ship a tiny shell, download heavy assets on first run" pattern we should adopt.**
- **Continue.dev**: Primarily a VS Code/JetBrains plugin, but their `core` is a separate Node process they spawn — almost exactly the sidecar pattern, just Node instead of Python. Their MIT-licensed code in `core/` is worth reading for IPC/streaming patterns over stdin/stdout (alternative to HTTP).
- **Ollama Desktop** (Mac/Win tray app): Tauri + Go. Tiny shell, all heavy lifting in the Go server. Different stack but proves Tauri can ship a polished tray app.
- **OpenSciReader** (the user's reference): Wails (Go) + React + Python `pdf2zh` worker. Shows the sidecar pattern works; the user's verdict ("not beautiful, not powerful enough") is mostly a UI-craft critique rather than an architecture critique. Architecturally we'd be doing the same shape, just with Electron-or-Tauri instead of Wails.

---

## Recommended Stack (concretely)

```
Shell:         Electron 32+ (Chromium 128+) with electron-vite scaffold
Frontend:      React 18 + TypeScript + Vite
               TanStack Router for routing
               Zustand or Jotai for state
               Tailwind CSS v4 + shadcn/ui (Radix primitives)
               Framer Motion for transitions
               react-pdf or PDF.js viewer for the reader pane
               @tanstack/react-virtual for long lists
Backend:       Python 3.12 (bundled via python-build-standalone)
               FastAPI + uvicorn
               LangChain / LangGraph for the agent layer
               markitdown for document → markdown
               pdf2zh-next for layout-preserving translation
               PyMuPDF / pypdfium2 for raw PDF ops
               SQLite (sqlite3 stdlib) for index + sqlite-vss or LanceDB for vectors
IPC:           HTTP for request/response, WebSocket for streaming
               JSON over the wire; pydantic models on Py side, zod on TS side
Packaging:     electron-builder
               Code signing: OV cert v1, upgrade to EV at scale
               Auto-update: electron-updater + GitHub Releases or S3
First-run UX:  ~200 MB installer; on first launch download models + heavy weights
```

**Dev-mode shortcut:** start the same React + FastAPI in browser-tab mode (option 3) for the first 4–6 weeks while you iterate on agent quality. Only add the Electron shell once the product-shape is clear. This keeps the hot-reload loop fast and defers code-signing setup until launch.

---

## Open Questions

1. **Do we need offline LLM at all in v1?** If yes, embed llama.cpp (Reor pattern) — affects bundle by +200 MB and rules out some shell choices. If no (cloud-only LLM), the install can stay under 250 MB.
2. **Will we ship torch?** Embeddings + reranking models often want torch. Alternatives: ONNX Runtime (no torch) with pre-converted models. Strong recommendation: **prefer ONNX/llama.cpp/Candle bindings, avoid torch at runtime**, save 200 MB + half the headache.
3. **Is Linux a v1 target or v2?** If v2, Tauri becomes more viable (WebKitGTK is the main reason to avoid it for v1).
4. **In-app Python plugin system?** If users will write Python plugins (likely for power-research users), the bundled Python needs to be importable as a runtime, not frozen — argues against Nuitka, for `python-build-standalone`.
5. **Do we have macOS hardware for QA?** Notarization requires it (or a Mac-in-cloud CI). Without it, ship Windows-first and add macOS in v2.

---

## Sources

(Document references — verify versions/links at integration time.)

- Electron documentation — process model, sandboxing, IPC: https://www.electronjs.org/docs/latest/
- electron-builder — https://www.electron.build/  (configuration for nsis, dmg, appimage)
- electron-updater — https://www.electron.build/auto-update
- Tauri 2 documentation — https://v2.tauri.app/  (sidecar binaries, updater plugin)
- python-build-standalone — https://github.com/astral-sh/python-build-standalone
- PyInstaller — https://pyinstaller.org/
- Nuitka — https://nuitka.net/
- PyWebView — https://pywebview.flowrl.com/
- NiceGUI — https://nicegui.io/
- Reflex — https://reflex.dev/
- Wails — https://wails.io/  (Wails 3 alpha notes)
- Avalonia — https://avaloniaui.net/  ; Python.NET — https://pythonnet.github.io/
- Reor architecture — https://github.com/reorproject/reor  (read `src/electron/main/` for sidecar IPC)
- Cherry Studio — https://github.com/CherryHQ/cherry-studio
- Continue.dev core — https://github.com/continuedev/continue  (read `core/` for stdin/stdout JSON-RPC)
- LM Studio — https://lmstudio.ai/  (closed source; observable bundle layout)
- Cursor — https://www.cursor.com/  (closed source; Squirrel-based updates inferred from installed app structure)
- PaperQA — https://github.com/Future-House/paper-qa
- shadcn/ui — https://ui.shadcn.com/  ; Radix primitives — https://www.radix-ui.com/
- PDF.js — https://mozilla.github.io/pdf.js/  ; react-pdf — https://github.com/wojtekmaj/react-pdf
- macOS notarization (`notarytool`) — https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
- Windows code-signing changes (HSM requirement, 2024+) — https://learn.microsoft.com/en-us/windows/security/

---

## Caveats / Not Found

- **No live web access during this research pass** — the per-product version numbers (Tauri 2 minor releases, Electron 32+ features, current state of Wails 3 stability) are based on the documented trajectory through late 2025. Re-verify at the moment of stack lock-in.
- **No firsthand benchmark of WebKitGTK PDF.js rendering quality in 2026** — the Linux concern is based on 2023–2024 GitHub issue threads in pdf.js and tauri-apps repos; may have improved.
- **Cursor / LM Studio internals are inferred from installer inspection**, not from source. Treat those precedents as directional.
- **The Avalonia + Python.NET combo** has shifted recently with .NET 8/9 AOT; the "tiny community" claim may need re-checking if a notable product has shipped on that stack since.
