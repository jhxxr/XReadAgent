# Optimize XReadAgent: 性能 + UX + 构建/发布（12 项）

## Goal

按用户确认的三个方向优化 XReadAgent：运行时性能（启动与阅读体验）、用户体验（修 bug + 关键流程反馈）、构建/发布工程化（可复现、提速、瘦身）。代码质量/大文件重构明确不在本任务范围。

## Requirements（用户已全选确认，2026-06-11）

### A. 运行时性能
* A1 后端懒加载：`backend/src/xreadagent/__init__.py` 不再顶层 eager import agents/langchain 链，消除冷启动 ~78s / sidecar 30s 超时风险
* A2 前端 code-splitting：路由级懒加载，pdfjs-dist 等重依赖按需加载
* A3 阅读器保留 PDF：tab 切换（forceMount）不再销毁/重新下载 PDF 文档
* A4 Electron 并行启动：窗口创建不阻塞在 Python sidecar ready

### B. 用户体验
* B1 修复 workspace Tabs 断连 bug：`frontend/src/routes/workspace.tsx:252` 与 `:285` 两个 Tabs 根不连通，Concepts/Queries 列表不可达
* B2 外链走系统浏览器：electron `setWindowOpenHandler` + `shell.openExternal`
* B3 Ingest 进度反馈：复用 translate 已有的 job + WebSocket 进度设施
* B4 拖拽 PDF 导入：兑现空态文案 "Drop a PDF" 的承诺

### C. 构建/发布
* C1 release 构建锁定 uv.lock：`electron/scripts/bundle-python.mjs:307` 不再绕过锁文件，产物可复现
* C2 版本号单源化：bump 脚本同步 5 处版本（pyproject、frontend/electron package.json、`__init__.py`、uv.lock）+ release 校验 tag==版本；顺带消除 `worker.py:68`/`service.py:51` 的 babeldoc 版本二次硬编码
* C3 CI/release 提速：补 pnpm/CPython/Electron 缓存、删 release.yml 无用的 `uv sync --frozen`、e2e job 依赖精简
* C4 打包瘦身：剔除 `__pycache__`/.pyc 与重复的 xreadagent 源码副本

## Acceptance Criteria

* [x] A1：`import xreadagent` 不再拉起 langchain/agents 链（test_lazy_imports.py 子进程守卫）；warm import 0.512s→0.006s；pytest 全绿（e741a3c）
* [x] A2：首屏 chunk 538 kB（原 1176 kB，-54%），pdfjs-dist 拆入 paper-read chunk；对比记录在 research/runtime-performance.md（9cedaa7）
* [x] A3：tab 切换 forceMount 保留 PDF，测试证明 getDocument 不重复调用（2fadffe）
* [x] A4：窗口立即显示加载页，sidecar 并行启动，失败有错误页+重试；splash 期 deep link 排队派发（7d16a5d）
* [x] B1：Concepts/Queries 标签受控状态打通，4 个组件测试（d7d0b2f）
* [x] B2：外链经 setWindowOpenHandler/will-navigate 交系统浏览器，9 个测试（53e6c26）
* [x] B3：ingest job 化 + WS 阶段进度（converting/analyzing/writing）+ toast 反馈，完成/失败均有终态（207849f）
* [x] B4：拖拽 PDF 导入复用 ingest 流程，busy 守卫跨实例生效（9380cb4）
* [x] C1：bundle venv 从 uv.lock 安装（uv export --locked，含锁文件新鲜度门禁）（e162b4b）
* [x] C2：scripts/bump-version.mjs 单命令同步 5 处版本；release 校验 tag==版本；babeldoc 版本改由元数据派生（dcac3ad）
* [x] C3：CI/release 补 pnpm/CPython/electron-builder 缓存、删无用 uv sync、e2e 依赖精简（8ed026e）
* [x] C4：打包剔除 __pycache__/.pyc 与重复源码副本，三层过滤（e162b4b）
* [x] 全部：ruff + mypy strict + pytest（391）、eslint + tsc + vitest（前端 179）、electron（93）全绿

## Definition of Done

* 各项改动配套测试（尤其 A1 的 import 守护测试、B1 的组件测试）
* Lint / typecheck / 测试 / CI 全绿
* README 或相关 docs 随行为变化更新（如 bump 脚本用法）

## Technical Approach

按层分批小 PR 实施，互不阻塞：

* **PR1（C 组，纯工程化，风险最低）**：C2 版本单源化 → C1 uv.lock 锁定 → C4 打包瘦身 → C3 CI 缓存
* **PR2（速赢组）**：B1 Tabs bug、B2 外链、A3 PDF 保留 —— 三个 S 级改动
* **PR3（启动性能）**：A1 后端懒加载 + A4 Electron 并行启动（同为"启动路径"主题，需联调 sidecar 等待逻辑）
* **PR4（前端较大改动）**：A2 code-splitting、B4 拖拽导入
* **PR5（跨层最大项）**：B3 ingest 进度（backend job 化 + WS + 前端进度 UI）

## Decision (ADR-lite)

**Context**: "优化项目"方向开放，需收敛。
**Decision**: 用户选定性能/UX/构建三方向并全选 12 个候选项；排除代码重构（未选）、A5 翻译子进程复用（L 级工作量）、B5 Electron polish、在途任务范围（settings UX、sidecar SPA 修复、v0.0.4 发布）。
**Consequences**: 范围较大，按 5 个小 PR 分批落地；B3 跨三层，放最后；若时间紧可在 PR3 后截断，前三个 PR 已覆盖最高价值项。

## Out of Scope

* 大文件重构（babeldoc_adapter.py / pdf-viewer.tsx / ingest.py 拆分）
* A5 翻译子进程复用、B5 Electron polish（窗口持久化/tray 图标）
* Settings UX / 语言切换（在途任务 06-10-redesign-settings-ux-language-switch）
* sidecar SPA 修复与 v0.0.4 发布（在途任务 06-01-*）

## Technical Notes

* 调研详情见 `research/runtime-performance.md`、`research/ux-ui.md`、`research/build-release.md`（含 file:line 引用与测量数据）
* 重依赖约束：babeldoc==0.6.2 精确钉死（API 不稳定，bump 须过 smoke-PDF 测试）；deepagents 0.x
* 注：v0.0.4 release 在途任务疑似已过期（tag 已到 v0.0.7），实施 C2 时留意
