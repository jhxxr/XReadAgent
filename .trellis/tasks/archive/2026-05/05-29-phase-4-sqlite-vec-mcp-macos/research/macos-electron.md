# Research: macOS Electron Support for XReadAgent

- **Query**: macOS support for XReadAgent's Electron app -- packaging, python-build-standalone, code signing, notarization, CI/CD
- **Scope**: Internal + External (mixed)
- **Date**: 2026-05-29

## Findings

### Files Found

| File Path | Description |
|---|---|
| `electron/electron-builder.yml` | Current build config; has stub `mac:` section (line 94-96), Windows-only targets |
| `electron/scripts/bundle-python.mjs` | Python bundler; has `darwin` platform branches but uses WRONG naming convention for python-build-standalone |
| `electron/src/sidecar.ts` | Sidecar manager; already has `process.platform !== "win32"` branches (POSIX paths), mostly macOS-ready |
| `electron/src/main.ts` | Main process; has macOS `open-url`, `open-file`, `activate` handlers already |
| `electron/src/preload.ts` | Exposes `process.platform` (line 71), macOS values will work |
| `electron/src/menu.ts` | Uses `CmdOrCtrl+` accelerators, macOS compatible |
| `electron/src/splash.ts` | Splash window; no platform-specific code, works on macOS |
| `electron/package.json` | Dependencies; electron-builder ^25.1.8 supports macOS |
| `electron/build/icon.svg` | SVG icon source; needs `.icns` conversion for macOS |

### Code Patterns

#### 1. bundle-python.mjs uses WRONG naming convention for macOS (CRITICAL BUG)

The `getPythonArchiveUrl()` function at line 47-72 generates macOS filenames as `macos-{arch}`:

```js
} else if (PLATFORM === "darwin") {
    platformSuffix = `macos-${psArch}`;
}
```

This produces filenames like `cpython-3.12.8+20241219-macos-aarch64-install_only.tar.gz`.

However, **python-build-standalone uses `aarch64-apple-darwin` and `x86_64-apple-darwin`** as the platform suffix, NOT `macos-aarch64` / `macos-x86_64`. Verified against the actual release assets for tag `20241219` (the tag currently used by the script):

- Correct: `cpython-3.12.8+20241219-aarch64-apple-darwin-install_only.tar.gz`
- Correct: `cpython-3.12.8+20241219-x86_64-apple-darwin-install_only.tar.gz`
- Wrong (what the script generates): `cpython-3.12.8+20241219-macos-aarch64-install_only.tar.gz`

The Windows naming convention (`windows-x86_64`) does appear correct based on actual release assets.

**The tar.gz extraction logic** (line 195-198) uses `--strip-components=2` for tar.gz, which should work for macOS since the archive structure is the same as Linux (the inner `python/` dir has `bin/python3`, `lib/python3.12/`, etc.).

#### 2. sidecar.ts already handles macOS paths correctly

`resolvePythonPath()` at line 468-471:
```ts
if (process.platform === "win32") {
    return path.join(resPath, "python", "python.exe");
}
return path.join(resPath, "python", "bin", "python3");
```

`resolveSidecarPaths()` similarly uses the POSIX `bin/` path for venv.

`killProcess()` at line 370-397 uses SIGTERM/SIGKILL on non-Windows, which is correct for macOS.

`spawnProcess()` at line 242-245 uses `path.join(venvPath, "bin")` for POSIX, correct for macOS.

#### 3. main.ts has macOS event handlers already

- `app.on("open-url")` at line 95-98 -- handles `xread://` deep links on macOS
- `app.on("open-file")` at line 105-108 -- handles `.xread` file association on macOS
- `app.on("activate")` at line 84-88 -- re-creates window on dock icon click
- `app.on("window-all-closed")` at line 74-76 -- does not quit (correct for macOS tray behavior)

The `process.platform === "win32"` check at line 131 for argv parsing correctly limits Windows-specific argv scanning.

#### 4. electron-builder.yml mac section is minimal stub

Current macOS config (lines 93-96):
```yaml
mac:
  category: public.app-category.productivity
  icon: build/icon.icns
```

Missing: `target` (DMG), `hardenedRuntime`, `entitlements`, `entitlementsInherit`, `identity`, `binaries` (for Python interpreter), `extendInfo` (for protocol handler registration via Info.plist).

#### 5. macOS tray icon differences

The `createTrayIcon()` function (line 388-422) creates a 16x16 pixel buffer icon. On macOS, tray icons should be template images (monochrome, 22x22 for retina 44x44). The current approach of generating a colored PNG buffer will work but will look wrong on macOS -- macOS expects a template icon that adapts to light/dark mode. Electron's `tray.setIgnoreDoubleClickEvents(true)` may also be needed on macOS.

#### 6. No CI/CD configuration exists

No `.github/workflows/` directory or any CI configuration files found in the repo.

### External References

#### electron-builder macOS Configuration

Per electron-builder docs (https://www.electron.build/docs/mac, fetched 2026-05-29):

**macOS targets supported by electron-builder:**
- `dmg` -- Standard consumer distribution (signed + notarized)
- `zip` -- For update servers (electron-updater)
- `pkg` -- System-level installs
- `mas` -- Mac App Store
- `dir` -- Unpacked (debugging)

**Default targets**: `zip` and `dmg` (both required for Squirrel.Mac auto-update).

**Architecture support:**
- `x64` -- Intel 64-bit
- `arm64` -- Apple Silicon (M1/M2/M3/M4)
- `universal` -- Fat binary containing both x64 and arm64

**Universal binary config:**
```yaml
mac:
  target:
    - target: dmg
      arch: universal
  mergeASARs: true
  singleArchFiles: "**/*.node"
```

**Key properties for our app:**
- `hardenedRuntime: true` (default, required for notarization on macOS 10.15+)
- `entitlements` -- path to `build/entitlements.mac.plist`
- `entitlementsInherit` -- path to `build/entitlements.mac.inherit.plist` (for helper processes like Python)
- `identity` -- signing certificate name, or use `CSC_LINK` + `CSC_KEY_PASSWORD` env vars
- `binaries` -- paths to additional native binaries that need signing (CRITICAL for bundled Python)
- `extendInfo` -- inject Info.plist keys (for URL scheme registration, file type association)

**Recommended: Build per-arch on correct hardware** -- arm64 on Apple Silicon, x64 on Intel. Universal builds work best when both arches are produced natively and merged.

#### macOS Code Signing Requirements

Per electron-builder docs and Apple developer documentation:

1. **Apple Developer Program** -- $99/year. Required for Developer ID certificates and notarization.

2. **Developer ID Application certificate** -- Used to sign apps distributed outside the Mac App Store. Created via Xcode > Settings > Accounts, or via `security` CLI on a Mac.

3. **Certificate storage for CI** -- Export the certificate as `.p12` file, base64-encode it, store as `CSC_LINK` env var. `CSC_KEY_PASSWORD` holds the p12 password. electron-builder automatically imports and uses these.

4. **Hardened Runtime** -- Required for notarization (macOS 10.15+). Enabled by default in electron-builder. Restricts what the app can do; entitlements grant exceptions.

5. **Entitlements required for Electron + Python sidecar:**
   - `com.apple.security.cs.allow-jit` -- Always needed; V8 requires JIT
   - `com.apple.security.cs.allow-unsigned-executable-memory` -- Some Electron internals
   - `com.apple.security.cs.allow-dyld-environment-variables` -- May be needed for Python to find shared libraries via DYLD_* paths; REMOVE for production notarized builds (Apple may reject)
   - `com.apple.security.network.client` -- If app makes outgoing connections (sandboxed apps)
   - `com.apple.security.network.server` -- If app listens for connections (our sidecar does this on localhost)

6. **The Python interpreter and all .dylib files MUST be signed** -- electron-builder's `binaries` option lists paths of additional native binaries to sign. The bundled Python interpreter and all shared libraries in `python/lib/` need this.

7. **Notarization via `notarytool`** -- electron-builder automates this with env vars:
   - `APPLE_ID` -- Apple Developer email
   - `APPLE_APP_SPECIFIC_PASSWORD` -- App-specific password (not the Apple ID password)
   - `APPLE_TEAM_ID` -- Team ID from developer account

8. **Ad-hoc signing** -- `identity: "-"` creates an ad-hoc signature. App only runs on the build machine. `identity: null` skips signing entirely. Both are unsuitable for distribution.

#### python-build-standalone macOS Support

Verified via GitHub API (2026-05-29) for both the currently-used release tag `20241219` and the latest release `20260510`:

**Available macOS builds for Python 3.12:**
- `cpython-3.12.8+20241219-aarch64-apple-darwin-install_only.tar.gz` (Apple Silicon)
- `cpython-3.12.8+20241219-x86_64-apple-darwin-install_only.tar.gz` (Intel)
- `cpython-3.12.13+20260510-aarch64-apple-darwin-install_only.tar.gz` (latest, Apple Silicon)
- `cpython-3.12.13+20260510-x86_64-apple-darwin-install_only.tar.gz` (latest, Intel)

**Naming convention**: `{arch}-apple-darwin` (e.g., `aarch64-apple-darwin`, `x86_64-apple-darwin`). NOT `macos-{arch}` as the current `bundle-python.mjs` generates.

**Archive format**: `.tar.gz` (same as Linux). NOT `.zip` (Windows only).

**Archive layout** (install_only): Same as Linux -- extracts to `cpython-...-install_only/python/` with subdirectories:
- `python/bin/python3` (symlink or binary)
- `python/lib/python3.12/` (stdlib)
- `python/lib/libpython3.12.dylib` (shared library)

**python-build-standalone and macOS code signing**: The research from `desktop-shell.md` noted that "python-build-standalone ships pre-notarized binaries which sidesteps the worst of it." This means the Python interpreter binaries themselves may already have valid code signatures. However, when bundled inside an Electron app's `extraResources`, the entire app bundle must be re-signed as a unit -- the `binaries` option in electron-builder ensures all embedded Mach-O files get re-signed with the Developer ID certificate.

#### macOS-specific Electron Issues

1. **Window management**: Already handled in `main.ts` via `activate` event (line 84-88) and `window-all-closed` override (line 74-76).

2. **Tray icon**: macOS tray icons should be **template images** (monochrome, 22x22 @1x, 44x44 @2x). The current code generates a colored 16x16 PNG which will render but look incorrect. Electron's `nativeImage.createFromBuffer` does not automatically create template images. Use `nativeImage.createFromPath` with a proper `.png` file and mark it as a template: `image.setTemplateImage(true)` (macOS only).

3. **Deep links on macOS**: Already handled via `app.on("open-url")` (line 95-98). For macOS, the `xread://` URL scheme must be registered in `Info.plist` via `CFBundleURLTypes`. electron-builder handles this automatically from the `protocols` config, but only for macOS builds (it is already configured at line 55-58 in electron-builder.yml).

4. **File associations on macOS**: Already handled via `app.on("open-file")` (line 105-108). The `fileAssociations` config (line 61-65) will generate `CFBundleDocumentTypes` in Info.plist automatically.

5. **Menu behavior on macOS**: The current menu uses `CmdOrCtrl+` accelerators which resolves to `Cmd` on macOS. However, macOS apps conventionally have the app name as the first menu item. Electron handles this automatically -- the first `label` in the menu template becomes the app menu on macOS. The current "File" menu is standard but could benefit from adding `{ role: 'about' }` and `{ role: 'quit' }` in the macOS app menu. Electron's default behavior adds these roles.

6. **App sandbox**: NOT needed for Developer ID distribution (only required for Mac App Store). Our app opens network connections and spawns processes, which makes sandboxing impractical.

7. **DMG background**: electron-builder can create DMG with custom background. Default is sufficient for v1.

#### CI/CD for macOS Builds

**GitHub Actions macOS runners:**
- `macos-latest` -- currently macOS 14 (Sonoma) on Apple Silicon (M1)
- `macos-13` -- macOS 13 (Ventura) on Intel
- `macos-14` -- macOS 14 (Sonoma) on Apple Silicon (M1)
- `macos-15` -- macOS 15 (Sequoia) on Apple Silicon

**For universal builds, need both architectures:**
```yaml
strategy:
  matrix:
    include:
      - os: macos-14
        arch: arm64
      - os: macos-13
        arch: x64
```

Then merge with `electron-builder --universal` or use the `afterAllArtifactBuild` hook.

**Alternative: Build on Apple Silicon only with `--universal` flag** -- cross-compilation for x64 on arm64 usually works for Electron apps but may fail with native modules. Since XReadAgent's Python sidecar is in `extraResources` (not compiled), cross-compilation should work. But for reliability, native builds are preferred.

**Notarization in CI** requires:
- `APPLE_ID` env var (Apple Developer email)
- `APPLE_APP_SPECIFIC_PASSWORD` env var (generate at appleid.apple.com)
- `APPLE_TEAM_ID` env var
- `CSC_LINK` env var (base64-encoded .p12 certificate)
- `CSC_KEY_PASSWORD` env var

These should be stored as GitHub Secrets.

**Typical macOS CI build step:**
```yaml
- name: Build Electron app (macOS)
  env:
    CSC_LINK: ${{ secrets.MAC_CERT_P12_BASE64 }}
    CSC_KEY_PASSWORD: ${{ secrets.MAC_CERT_PASSWORD }}
    APPLE_ID: ${{ secrets.APPLE_ID }}
    APPLE_APP_SPECIFIC_PASSWORD: ${{ secrets.APPLE_APP_SPECIFIC_PASSWORD }}
    APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
  run: |
    cd electron
    pnpm pack:python
    pnpm dist
```

### Related Specs

- `.trellis/spec/electron/index.md` -- Electron development guidelines; describes current architecture as Windows-only
- `.trellis/spec/guides/cross-layer-thinking-guide.md` -- Cross-layer data flow; Electron boundary docs
- `.trellis/tasks/archive/2026-05/05-22-build-sciresearch-agent-literature-reading-knowledge-base/research/desktop-shell.md` -- Original desktop shell research; noted macOS code signing + notarization requirements

## Summary of Required Changes for macOS Support

### 1. electron-builder.yml (HIGH PRIORITY)

The `mac:` section needs significant expansion:
```yaml
mac:
  target:
    - target: dmg
      arch: [arm64, x64]   # or [universal] for fat binary
  category: public.app-category.productivity
  icon: build/icon.icns
  hardenedRuntime: true
  entitlements: build/entitlements.mac.plist
  entitlementsInherit: build/entitlements.mac.inherit.plist
  binaries:
    - Contents/Resources/python/bin/python3
    # All .dylib files in python/lib/ also need signing
    # Use glob: Contents/Resources/python/lib/**/*.dylib
  extendInfo:
    CFBundleURLTypes:
      - CFBundleURLSchemes:
          - xread
        CFBundleURLName: com.xreadagent.desktop
```

### 2. bundle-python.mjs (CRITICAL BUG FIX)

The `getPythonArchiveUrl()` function generates wrong macOS filenames. The `darwin` branch at lines 52-53 and 63 must use `{arch}-apple-darwin` instead of `macos-{arch}`:
```js
} else if (PLATFORM === "darwin") {
    psArch = ARCH === "arm64" ? "aarch64" : "x86_64";
    platformSuffix = `${psArch}-apple-darwin`;
}
```

Also, the tar.gz extraction with `--strip-components=2` (line 198) should work correctly for macOS install_only archives since they have the same two-level directory structure as Linux.

### 3. Entitlements Files (NEW)

Need to create two new files:

**build/entitlements.mac.plist:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
  <key>com.apple.security.network.server</key>
  <true/>
</dict>
</plist>
```

**build/entitlements.mac.inherit.plist:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.network.client</key>
  <true/>
  <key>com.apple.security.network.server</key>
  <true/>
</dict>
</plist>
```

`network.server` is needed because the Python sidecar listens on localhost. `network.client` is needed for outgoing HTTP requests to LLM APIs.

### 4. Icon Generation (MODERATE)

Need `build/icon.icns` for macOS. Options:
- Use `iconutil` on macOS to create `.icns` from a set of `.png` files at various sizes
- Use the existing `icon.svg` + `generate-icons.mjs` to add `.icns` output
- Use `electron-icon-maker` or `png2icns` npm packages

### 5. Tray Icon (LOW PRIORITY for v1)

The `createTrayIcon()` function should be updated for macOS to produce a template image:
```ts
if (process.platform === "darwin") {
  icon = nativeImage.createFromPath(path.join(__dirname, "..", "build", "tray-icon-template.png"));
  icon.setTemplateImage(true);
} else {
  icon = createTrayIcon(); // existing Windows/Linux code
}
```

### 6. main.ts: macOS App Menu Convention (LOW PRIORITY)

On macOS, the first menu should be the app menu. Electron adds this automatically when you use `Menu.setApplicationMenu()`, but verify the current `buildApplicationMenu()` output looks correct on macOS.

### 7. CI/CD (NEW)

Create `.github/workflows/build-macos.yml` or extend a general build workflow with macOS matrix entries. Requires Apple Developer credentials as GitHub Secrets.

## Caveats / Not Found

- **Could not access electron-builder code-signing documentation page** -- URLs tried (`/docs/code-signing`, `/code-signing`, `/code-signing/mac`, `/features/code-signing`) all returned 404. The site structure may have changed. The code-signing info was inferred from the macOS docs page and general knowledge.
- **python-build-standalone macOS code signature status** -- The desktop-shell.md research claims they ship "pre-notarized binaries" but this could not be independently verified via API. The actual signatures on the `.tar.gz` contents would need to be checked on a Mac with `codesign -vv`.
- **Universal binary feasibility** -- Building a universal binary requires either building on both architectures in CI and merging, or cross-compiling. Cross-compilation's reliability depends on whether any native Node modules with compiled components are used. The current `electron/package.json` shows zero production dependencies (only devDependencies), so cross-compilation should work.
- **Apple Silicon python-build-standalone compatibility with binary wheels** -- Some Python packages (e.g., PyMuPDF, tokenizers) ship pre-compiled `.so` files as wheels. These should work on arm64 if arm64 wheels exist on PyPI. Most major packages now ship arm64 macOS wheels. The `uv pip install` step in `bundle-python.mjs` should automatically select the correct platform wheel.
- **DYLD environment variables and notarization** -- The sidecar's `spawnProcess()` sets `VIRTUAL_ENV` and `PATH` but does NOT set `DYLD_LIBRARY_PATH` or `DYLD_FRAMEWORK_PATH`. On macOS with SIP, DYLD vars are stripped for system processes. Since the sidecar is spawned by the Electron app (not a system process), this should be fine. However, if Python needs to find `.dylib` files outside its standard search paths, additional configuration may be needed.
- **macOS App Translocation** -- macOS 10.12+ "quarantines" apps downloaded from the internet and runs them from a random read-only DMG location. This means relative paths may break during the first launch from a DMG. Users must drag the app to `/Applications/` before the sidecar paths will resolve correctly. electron-builder DMG config can include a "drag to Applications" shortcut.