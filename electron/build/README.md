# XReadAgent App Icons

This directory contains application icons for the Electron build.

## Required files for electron-builder

| File | Size | Purpose |
|------|------|---------|
| `icon.ico` | 256x256 | Windows app icon (NSIS installer + taskbar) |
| `icon.png` | 512x512 | Linux AppImage icon |
| `icon.icns` | multi-size | macOS app icon (DMG + dock) |
| `tray-icon-template.png` | 44x44 | macOS tray icon (@2x retina, template image) |
| `tray-icon-template@1x.png` | 22x22 | macOS tray icon (@1x, template image) |
| `entitlements.mac.plist` | - | macOS entitlements (hardened runtime) |
| `entitlements.mac.inherit.plist` | - | macOS entitlements (child processes) |

## Generating icons

Run `pnpm generate-icons` to create all icon files from the programmatic generator.

The generator creates:
- `icon-256.png` — 256x256 PNG (ICO source)
- `icon.png` — 512x512 PNG (Linux + ICNS source)
- `icon.ico` — Windows ICO file
- `icon.icns` — macOS ICNS file (multi-size)
- `tray-icon-template.png` — macOS tray template icon (@2x)
- `tray-icon-template@1x.png` — macOS tray template icon (@1x)

### Manual icon generation from SVG

The source vector is `icon.svg`. To generate raster icons manually:

```bash
# PNG 256x256 (Windows ICO source, Linux)
inkscape icon.svg -w 256 -h 256 -o icon-256.png
inkscape icon.svg -w 512 -h 512 -o icon.png

# ICO (Windows)
convert icon-256.png icon.ico

# ICNS (macOS, run on macOS)
# Create iconset directory with required sizes, then use iconutil
mkdir icon.iconset
inkscape icon.svg -w 16 -h 16 -o icon.iconset/icon_16x16.png
inkscape icon.svg -w 32 -h 32 -o icon.iconset/icon_16x16@2x.png
inkscape icon.svg -w 32 -h 32 -o icon.iconset/icon_32x32.png
inkscape icon.svg -w 64 -h 64 -o icon.iconset/icon_32x32@2x.png
inkscape icon.svg -w 128 -h 128 -o icon.iconset/icon_128x128.png
inkscape icon.svg -w 256 -h 256 -o icon.iconset/icon_128x128@2x.png
inkscape icon.svg -w 256 -h 256 -o icon.iconset/icon_256x256.png
inkscape icon.svg -w 512 -h 512 -o icon.iconset/icon_256x256@2x.png
inkscape icon.svg -w 512 -h 512 -o icon.iconset/icon_512x512.png
inkscape icon.svg -w 1024 -h 1024 -o icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
```

## macOS entitlements

The `entitlements.mac.plist` and `entitlements.mac.inherit.plist` files define
the macOS hardened runtime entitlements required for:

- `com.apple.security.cs.allow-jit` — V8 JavaScript engine needs JIT
- `com.apple.security.cs.allow-unsigned-executable-memory` — Electron internals
- `com.apple.security.network.server` — Python sidecar HTTP listener on localhost
- `com.apple.security.network.client` — Outbound LLM API calls

When building without Apple Developer certificates, electron-builder will create
an unsigned build. The app will show a Gatekeeper warning when launched. To
sign and notarize, set the environment variables:
- `CSC_LINK` — base64-encoded .p12 certificate
- `CSC_KEY_PASSWORD` — password for the .p12 certificate
- `APPLE_ID` — Apple Developer email
- `APPLE_APP_SPECIFIC_PASSWORD` — app-specific password
- `APPLE_TEAM_ID` — Apple Developer team ID

## Current status

The placeholder icon.svg is a simple book/reader design. A proper icon should be
designed by a graphic designer before the v1 release.

During development, electron-builder will use a default icon if these files
are missing. The NSIS installer will still build without a custom icon.