# Electron 桌面客户端 (Electron + Python sidecar)

## Goal

将现有的 React + FastAPI 架构包装进 Electron 桌面应用，使 XReadAgent 成为一个独立运行的桌面客户端，而非浏览器标签页中的 Web 应用。Electron 主进程负责窗口管理、Python sidecar 生命周期、原生对话框和自动更新；渲染进程复用现有 frontend/ 代码不变。

## What I already know

* **架构决策已做**：原始 plan.md D 系列决策中确认 Electron + Python sidecar 为 Phase 3 方案（参见 `research/desktop-shell.md`）
* **已有前端**：React 19 + Vite + TanStack Router + Tailwind v4 + shadcn/ui，运行在 `localhost:5173`（dev）或由 FastAPI serve 静态文件
* **已有后端**：Python FastAPI sidecar，`127.0.0.1:0` 绑定，启动时打印 `SIDECAR_READY port=<N>`
* **已有 IPC 模式**：前端通过 `/api/*` (JSON) 和 `/ws/*` (WebSocket) 与后端通信 — Electron 层不需要重写这些
* **项目许可**：AGPL-3.0-or-later
* **目标平台**：Windows 11 优先（用户环境）
* **用户明确需求**：美观（Linear/Notion/Cursor 级 UI）、功能强大、本地优先

## Assumptions (temporary)

- A1. Phase 1–2 的 React 前端代码不做大规模重构，直接在 Electron BrowserWindow 中渲染
- A2. Electron 主进程代码量 <1000 LoC（参考 Cursor/Reor 模式）
- A3. 不在 v1 中嵌入离线 LLM（BabelDOC ONNX 除外）— cloud-only LLM
- A4. 不在 v1 中 ship torch — 优先 ONNX Runtime
- A5. 不在 v1 中支持 macOS/Linux — Windows-first，macOS 可后续加
- A6. 安装包大小目标 ≤250 MB（不含 ML 模型，模型首次运行时下载）

## Decisions

- **D1. 项目结构**：根目录新增独立 `electron/` 目录，包含 main process、preload、electron-builder 配置。前端代码仍在 `frontend/` 不动。构建时 Electron 引用 `frontend/dist/`。理由：职责分离清晰，Cursor/Cherry Studio 等项目均采用此模式。
- **D2. 热更新策略**：dev 模式 Electron 加载 Vite HMR URL (`http://localhost:5173`)，Python sidecar 单独启动；production 模式 Electron 加载 FastAPI serve 的静态文件。标准混合模式，electron-vite 内置支持。
- **D3. Python sidecar 分发**：`python-build-standalone`（astral-sh）捆绑方案 — 将 CPython 3.12 解释器 + 项目依赖打包进 `resources/python/`。零门槛安装，保留 Python 可导入性（为未来插件系统留空间）。
- **D4. 自动更新**：v1 不含自动更新，先通过 GitHub Releases 手动分发。`electron-updater` 基础设施延后到 v1.1/v2，届时有真实用户反馈再决定更新策略。
- **D5. 原生功能范围**：v1 完整集 — 窗口管理 + sidecar 生命周期 + 系统对话框 + 应用菜单（File > Open Workspace / Preferences / Quit）+ 最小化到系统托盘（关闭窗口时后台运行 sidecar）+ `.xread` 文件关联 + `xread://` 深链接 + 系统通知（翻译完成等）。

## Open Questions

(none — all major questions resolved)

## Requirements (evolving)

### R-SHELL: Electron 壳

- Electron main process 管理 BrowserWindow 生命周期
- 启动时 spawn Python sidecar，等待 `SIDECAR_READY port=<N>` + `/healthz` 200
- 退出时优雅关闭 sidecar（SIGTERM → 超时 → SIGKILL）
- Splash/loading 窗口显示 sidecar 启动进度
- 最小化到系统托盘：关闭窗口时隐藏到托盘，不杀 sidecar；托盘菜单可恢复窗口或真正退出

### R-IPC: 渲染进程与后端通信

- 渲染进程通过 `http://127.0.0.1:<port>/api/*` 和 `ws://127.0.0.1:<port>/ws/*` 与 Python 通信（与 dev 模式相同）
- Electron preload bridge 暴露 OS API：打开文件/文件夹对话框、获取平台信息、显示系统通知、处理深链接

### R-MENU: 应用菜单

- 简单菜单栏：File > Open Workspace / Preferences / Quit
- Edit 菜单：Copy / Paste / Select All（标准 Electron 默认即可）

### R-NATIVE: 原生集成

- `.xread` 文件关联：双击 `.xread` 文件打开 XReadAgent 并导航到对应工作区
- `xread://` 深链接：`xread://paper/{slug}` 导航到论文，`xread://query/{id}` 导航到查询
- 系统通知：翻译完成、导入完成等长时间操作完成时发送 Windows 通知

### R-ROBUST: 健壮性

- Sidecar 崩溃后自动重启（最多 3 次，指数退避）
- 端口冲突处理：`--port 0` 已让 OS 分配空闲端口，若绑定失败则重试
- 捆绑 Python 未找到时显示友好错误页（不闪退）
- Sidecar 启动超时（30s）时显示错误页 + 重试按钮

### R-STATUS: Sidecar 状态页

- Settings 中新增"Sidecar"tab，显示：运行状态（running/stopped/error）、PID、端口号、启动时间
- 侧边栏日志查看（最近 N 行 stdout/stderr）
- 手动重启 sidecar 按钮

### R-FUTURE: 未来预留

- BrowserWindow 创建使用工厂函数，为未来多窗口（论文阅读器独立窗口）预留
- 注册 `xread://` 协议处理器，为深链接路由预留
- Preload bridge 使用 `contextBridge` 严格隔离，为未来插件 API 预留安全边界

### R-DIST: 打包与分发

- `electron-builder` 生成 Windows NSIS 安装包
- 捆绑 `python-build-standalone` CPython 3.12 + 项目 venv 依赖
- 安装包大小目标 ≤250 MB（不含 ML 模型）
- 首次运行时下载 BabelDOC ONNX 模型等大文件
- v1 不做代码签名，接受 SmartScreen 警告

### R-DEV: 开发体验

- dev 模式：Electron 加载 Vite HMR URL (`http://localhost:5173`)，Python sidecar 单独启动
- `pnpm dev` 同时启动 Vite + Electron，支持 HMR
- `pnpm build` 构建前端静态文件 + Electron 打包
- TypeScript 严格模式，ESLint

## Acceptance Criteria (evolving)

- [ ] `pnpm dev` 启动 Electron 窗口，显示现有 React UI
- [ ] Electron 启动时自动 spawn Python sidecar，加载页显示启动状态
- [ ] 关闭窗口时隐藏到系统托盘，托盘菜单可恢复或真正退出
- [ ] 真正退出时 sidecar 进程被清理
- [ ] 所有现有前端功能（论文浏览、翻译、设置）在 Electron 中正常工作
- [ ] `.xread` 文件双击打开应用并导航到工作区
- [ ] `xread://` 深链接在浏览器中触发应用导航
- [ ] 翻译/导入完成时发送系统通知
- [ ] 应用菜单：File > Open Workspace / Preferences / Quit
- [ ] Sidecar 崩溃后自动重启（最多 3 次）
- [ ] 捆绑 Python 未找到时显示友好错误页
- [ ] Settings 中新增 Sidecar 状态页（运行状态、PID、端口、日志、重启按钮）
- [ ] `pnpm build` 生成 Windows NSIS 安装包 (.exe)

## Definition of Done

- [ ] 代码通过 ESLint + TypeScript 类型检查
- [ ] 新增代码有单元/集成测试覆盖
- [ ] 更新相关文档（README、spec）
- [ ] 考虑回滚策略（安装包可卸载、sidecar 独立可终止）

## Out of Scope (explicit)

- macOS/Linux 打包和代码签名（v1 Windows-only）
- 代码签名证书（v1 不做，SmartScreen 警告可接受）
- 离线 LLM 嵌入（llama.cpp）
- torch 捆绑
- 自动更新（v1 不含，延后到 v1.1/v2）
- 多窗口 UI（v1 预留架构但不实现独立论文窗口）
- 插件系统（v1 预留安全边界但不暴露插件 API）
- 拖拽文件到窗口打开工作区（v2）
- macOS notarization

## Technical Notes

- 已有详细技术调研：`research/desktop-shell.md`（Electron + Python sidecar 为推荐方案）
- Electron 版本选择：32+（Chromium 128+），使用 electron-vite 或 electron-forge 脚手架
- Python 捆绑：`python-build-standalone`（astral-sh）为推荐方案，优于 PyInstaller/Nuitka
- 侧边栏/加载页参考：Cursor 启动画面、LM Studio 首次运行下载 UX
- 前端 Vite 代理配置已指向 `localhost:8765`（dev 模式）