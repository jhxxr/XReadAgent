# macOS Electron 打包 + 代码签名

## Goal

将 XReadAgent Electron 桌面客户端扩展到 macOS（Apple Silicon + Intel），包括代码签名和 notarization。

## What I already know

* **现有代码大部分已 macOS 兼容** — sidecar.ts、main.ts、menu.ts、splash.ts 已有平台分支
* **bundle-python.mjs 有 macOS 命名 bug** — 使用 `macos-{arch}` 而非正确的 `aarch64-apple-darwin` / `x86_64-apple-darwin`
* **icon 需要 .icns 格式** — 当前只有 .ico（Windows）和 .png
* **electron-builder.yml mac 配置是 stub** — 需要完善 DMG、hardened runtime、entitlements
* **研究文件** — `archive/05-29-phase-4-sqlite-vec-mcp-macos/research/macos-electron.md`

## Decisions

- **D1. 目标架构**：Universal binary (arm64 + x64)，使用 electron-builder 的 mac universal 选项
- **D2. 代码签名**：需要 Apple Developer ID 证书（$99/年），notarization 是必须的
- **D3. entitlements**：JIT + unsigned executable memory + network（sidecar HTTP + LLM API 调用）
- **D4. 先支持 unsigned 开发版**：没有证书时也能构建 macOS .app（只是会有 Gatekeeper 警告）

## Requirements

### R-MAC-BUILD: macOS 构建

- electron-builder.yml mac 配置：DMG target, hardened runtime, entitlements
- 修复 bundle-python.mjs 中 macOS 文件名 bug
- macOS icon (.icns) 生成
- resolvePythonPath 和 resolveSidecarPaths 的 macOS 路径验证
- macOS 上的 sidecar 启动、健康检查、关闭全流程验证

### R-MAC-SIGN: 代码签名和 Notarization

- entitlements.mac.plist：JIT + unsigned executable memory + network client/server
- electron-builder notarization 配置
- 环境变量：CSC_LINK, CSC_KEY_PASSWORD, APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
- 未签名构建支持（无证书时跳过签名）

### R-MAC-TEST: macOS 测试验证

- 在 macOS 上启动 Electron app
- Sidecar spawn/shutdown 验证
- 文件关联 (.xread) 和深链接 (xread://) 验证
- 系统托盘和菜单验证

## Acceptance Criteria

- [ ] `pnpm pack --mac` 生成 macOS .app + .dmg
- [ ] bundle-python.mjs 正确下载 macOS arm64/x64 python-build-standalone
- [ ] macOS 上 Electron 启动、sidecar spawn、UI 正常
- [ ] 有证书时：代码签名 + notarization 通过
- [ ] 无证书时：构建成功但有 Gatekeeper 警告

## Out of Scope

- macOS App Store 分发
- macOS CI/CD pipeline（手动构建先行）
- Auto-update（v1 不包含）
- Linux 打包

## Technical Notes

- python-build-standalone macOS 文件名：`aarch64-apple-darwin` 和 `x86_64-apple-darwin`
- entitlements 需要：com.apple.security.cs.allow-jit, com.apple.security.cs.allow-unsigned-executable-memory, com.apple.security.network.server, com.apple.security.network.client
- macOS tray icon 需要模板图片（黑白适配深浅色）