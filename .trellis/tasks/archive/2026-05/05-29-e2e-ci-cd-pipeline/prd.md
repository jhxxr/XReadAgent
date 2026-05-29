# E2E 集成测试与 CI/CD Pipeline

## Goal

为 XReadAgent 建立端到端集成测试和 GitHub Actions CI/CD pipeline，确保 Electron → sidecar → 翻译 → 阅读器的完整流程可验证、可自动化。

## What I already know

- 项目是 polyglot 架构：Python backend (FastAPI sidecar) + React frontend + Electron shell
- 现有测试：pytest (46 backend tests) + Vitest (21 frontend + 4 electron tests)，全部是单元测试
- 无 CI/CD — 没有 `.github/` 目录，无 GitHub Actions
- Electron 通过 `SidecarManager` spawn Python sidecar，通信协议：stdout `SIDECAR_READY port=<N>` + HTTP healthz + WebSocket
- 构建流程：frontend build → electron build (esbuild) → electron-builder (NSIS/DMG)
- 三个包各自独立管理：backend (uv), frontend (pnpm), electron (pnpm)

## Assumptions (temporary)

- 使用 GitHub Actions（项目已 hosted on GitHub）
- CI 覆盖 lint + typecheck + test + build 验证
- CD：tag 触发自动构建并上传到 GitHub Releases（Windows NSIS + macOS DMG）
- E2E 测试先聚焦 Electron ↔ sidecar 链路，不涉及真实 LLM 调用

## Open Questions

- CI/CD 的 scope 边界是什么？（仅 CI 测试 vs 包含构建/发布）
- E2E 测试要覆盖哪些场景？

## Requirements (evolving)

- GitHub Actions CI workflow (push/PR): lint + typecheck + unit tests + build 验证（三个包）
- GitHub Actions CD workflow (tag `v*` push): 构建 Windows NSIS + macOS DMG，上传到 GitHub Releases
- 端到端集成测试：Electron 启动 → sidecar 就绪 → 前端可访问
- CD 版本号从 tag 自动提取

## Acceptance Criteria (evolving)

- [x] `ci.yml` 在 push/PR 时自动运行
- [x] 三个包的 lint/typecheck/test 全部在 CI 中通过
- [x] CI 中 pnpm 和 uv 依赖有缓存
- [x] E2E 测试验证 sidecar 启动和健康检查
- [x] `release.yml` 在 tag `v*` push 时自动构建并上传到 GitHub Releases
- [x] Windows NSIS 安装包和 macOS DMG 正确生成
- [x] 构建产物自动上传到 GitHub Releases assets

## Definition of Done

- Tests added/updated (E2E test for sidecar lifecycle)
- CI green on GitHub
- Docs updated (README 中添加 CI badge 和发布说明)

## Decision (ADR-lite)

**Context**: 项目无 CI/CD，需要自动化测试和发布流程
**Decision**: GitHub Actions CI + CD，tag 触发发布，macOS 暂不签名
**Consequences**: macOS 用户会看到 Gatekeeper 警告；后续需配置 Apple 证书消除警告

## Out of Scope (explicit)

- Linux 构建（reserved for future v2）
- 自动 changelog 生成
- macOS 代码签名（暂不签名，后续配置）
- 真实 LLM API 调用的集成测试
- 性能基准测试
- Playwright/Cypress UI 测试

## Technical Notes

- Backend 测试运行：`uv run pytest -xvs`
- Frontend 测试运行：`cd frontend && pnpm test`
- Electron 测试运行：`cd electron && pnpm test`
- Python 版本：3.11+ (pyproject.toml target)，CI 使用 3.12
- Node 版本：>=20 (frontend engines)
- 构建依赖：`uv` (Python bundling)、`pnpm`、`node 20`
- bundle-python.mjs 下载 python-build-standalone CPython 3.12.8，创建 venv，安装 backend deps
- macOS 代码签名：暂不签名，构建未签名版本（用户会看到 Gatekeeper 警告），后续再配置
- CD 构建矩阵：Windows NSIS (windows-latest) + macOS DMG (macos-latest, universal binary)
- electron-builder 支持跨平台构建，但 macOS 签名需要 macOS runner
- E2E 测试通过 `XREADAGENT_E2E=1` 环境变量启用，默认跳过
- E2E 测试使用 60s 超时（Python 冷启动需要加载 heavy deps）
- CI workflow 使用 concurrency group 防止重复运行
- CD workflow 使用 `softprops/action-gh-release@v2` 自动创建 release
