# Research: 用户体验 / UI 改进候选项

- **Query**: 调研 XReadAgent 前端 + Electron 的 UX/UI 改进候选项
- **Scope**: internal（frontend/src、electron/src、.trellis/spec/frontend、backend API 行为）
- **Date**: 2026-06-11
- **排除范围**: Settings 页面重构 + 语言切换基础设施已由进行中任务
  `.trellis/tasks/06-10-redesign-settings-ux-language-switch/` 覆盖（含 i18n Provider、
  settings 路由分区、语言持久化），以下候选项均不与其重叠。该任务的 Out of Scope 明确
  说明"MVP 只覆盖 settings 和主导航 chrome 的字符串"，因此"其余界面的全面本地化"不属于
  其范围，可作为后续候选（见候选 12）。

## 现状用户流程地图

路由（`frontend/src/router.tsx:14-88`，TanStack Router，根布局 `AppShell`）：

| 路由 | 组件 | 功能现状 |
|---|---|---|
| `/` | redirect → `/workspace` | — |
| `/workspace` | `routes/workspace.tsx` | 主页：Papers/Concepts/Queries 三个标签 + Import 按钮 |
| `/paper` | `routes/paper-index.tsx` | **静态说明卡片，不列出任何论文** |
| `/paper/$slug` | `routes/paper.tsx` | 论文 wiki 页（markdown + frontmatter） |
| `/paper/$slug/read` | `routes/paper-read.tsx` | PDF 阅读器（Original/Dual/Translated 三标签）+ 翻译对话框 |
| `/concept/$slug` | `routes/concept.tsx` | 概念 wiki 页 |
| `/queries` | `routes/queries.tsx` | **静态说明卡片，不列出任何查询** |
| `/query/$topic/$slug` | `routes/query-detail.tsx` | 查询归档详情 |
| `/settings` | `routes/settings.tsx` | （由另一任务重构中，排除） |

外壳（`components/shell/app-shell.tsx:8-21`）：左侧 `AppSidebar`（260px，工作区切换 +
三个导航项 + Settings）、顶部 `HealthBanner`（常驻）、右侧 `CopilotSidebar`（浮动按钮 +
滑入面板，单轮问答带证据引用）。

核心动作：
- 导入文档：`lib/use-workspace-actions.ts:56-73` → 原生文件对话框 → `postIngest`
  （`lib/api.ts:262-268`，单次阻塞 POST；后端 `backend/src/xreadagent/api/wiki_router.py:276`
  同步执行 LLM ingest agent）。
- 翻译：`components/reader/translate-dialog.tsx` → `POST /api/translate` + WS
  `/ws/jobs/{jobId}` 流式进度（分阶段清单 + 百分比 + 引擎资产下载进度）。
- Copilot 问答：`components/shell/copilot-sidebar.tsx:248-290` → `postQuery` 单次 POST。

---

## 候选改进项

### 1. Workspace 页头部标签与内容标签未关联（功能性 Bug）

- **现状**：`routes/workspace.tsx` 中存在两个相互独立的 Radix `Tabs` 根：头部的
  `TabsList`（252-267 行，含 Papers/Concepts/Queries 触发器）和内容区的
  `Tabs`（285-295 行，含三个 `TabsContent`）。`ui/tabs.tsx:7` 的 `Tabs` 即
  `TabsPrimitive.Root`，两个根各自维护 `defaultValue="papers"` 的非受控状态，互不联动。
  点击头部的 Concepts/Queries 触发器只改变头部根的状态，内容区永远停留在 Papers。
  此外头部标签 `hidden sm:block`（252 行），小窗口下没有任何替代入口。
- **建议**：提升 `value`/`onValueChange` 到 `WorkspaceRoute` 的 state，两处共用受控值；
  或把 TabsList 移入同一个 Tabs 根内。
- **用户价值**：高（Concepts 与 Queries 列表当前实际不可达，只能靠 Copilot 引用链接进入）
- **工作量**：S
- **风险**：低；需补一条切换标签的测试

### 2. Ingest（导入）无进度反馈，长时间 LLM 操作只有按钮文案

- **现状**：导入触发后唯一反馈是按钮文案 "Importing..."（`routes/workspace.tsx:280`、
  `components/workspace/workspace-empty-state.tsx:59`）和结束时的 toast
  （`lib/use-workspace-actions.ts:28-32`）。`postIngest` 是单次阻塞 HTTP POST
  （`lib/api.ts:262-268`），后端同步运行 ingest agent（写 10-15 个 wiki 页面，
  通常需要数分钟）。没有阶段进度、没有可取消、没有完成时的桌面通知
  （`lib/notifications.ts` 的 `notifyOnCompletion` 目前只在翻译完成时调用，
  见 `routes/paper-read.tsx:150`）。用户切到别的页面后没有任何"正在导入"的全局指示。
- **建议**：复用已有的 job + WebSocket 基础设施（翻译已实现
  `POST /api/translate` + `/ws/jobs/{jobId}`，`backend/src/xreadagent/api/main.py:199`），
  把 ingest 改为异步 job 并流式上报阶段；前端加全局进度指示（如侧边栏角标或
  toast 进度条）+ 完成桌面通知。
- **用户价值**：高（导入是核心流程，目前体验最差的等待点）
- **工作量**：L（涉及后端 job 化 + 前端订阅）；折中方案 M（仅加"不确定进度"全局指示 + 完成通知）
- **风险**：中；后端 ingest 同步接口已有调用方（MCP tools、CLI），需保持兼容

### 3. 外部链接在 Electron 内打开新裸窗口而非系统浏览器

- **现状**：`components/wiki/wiki-markdown.tsx:91-101` 对外部链接渲染
  `target="_blank"`；而 `electron/src/main.ts` 全文没有
  `setWindowOpenHandler`/`shell.openExternal`/`will-navigate` 处理
  （全仓 grep 无匹配）。Electron 默认行为是为 `_blank` 新开一个无菜单的子
  BrowserWindow，用户会被困在一个裸窗口里浏览外部网页，也有安全隐患。
- **建议**：在 `createMainWindow` 中加
  `webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: "deny" }; })`
  并拦截 `will-navigate` 到非本地地址。
- **用户价值**：高（论文 wiki 页常含 arXiv/DOI 链接）
- **工作量**：S
- **风险**：低

### 4. 空状态文案承诺"拖拽导入"但全应用无 drag-drop 实现

- **现状**：`components/workspace/workspace-empty-state.tsx:31` 文案为
  "Drop a PDF, DOCX, or HTML to start building your second brain"，但全仓没有任何
  `onDrop`/`dragover` 处理（grep 无匹配）。用户拖文件进窗口会触发浏览器默认行为
  （直接在窗口里打开文件，等于丢失当前应用状态）。
- **建议**：在 `AppShell` 或 workspace 页注册 drop zone，取
  `event.dataTransfer.files` 的 `path`（Electron 下可用 `webUtils.getPathForFile`），
  走现有 `ingestMutation`；至少要 `preventDefault` 阻断默认导航。
- **用户价值**：高（桌面工具最自然的导入方式，且文案已承诺）
- **工作量**：M（含 Electron preload 暴露文件路径）
- **风险**：低-中（浏览器 dev 模式拿不到绝对路径，需平台分支处理）

### 5. 窗口状态不持久化 + 窗口/托盘图标为占位

- **现状**：`electron/src/main.ts:284-297` 固定 `1280x800`，每次启动重置窗口大小
  和位置（无 bounds 保存/恢复）；`BrowserWindow` 未设置 `icon`；托盘图标是程序化
  生成的蓝色方块占位（`main.ts:400-434`，注释自述 "temporary placeholder; replace
  with a proper icon asset"）。
- **建议**：保存/恢复窗口 bounds（自写 JSON 或 `electron-window-state`）；提供正式
  的 app icon 资产（window/taskbar/tray 三处）。
- **用户价值**：中-高（每天打开都要重新调窗口；占位托盘图标影响产品感知与可发现性）
- **工作量**：S（bounds 持久化）+ S（图标资产接入，设计资产另计）
- **风险**：低

### 6. 关闭按钮静默隐藏到托盘，无任何提示或选项

- **现状**：`electron/src/main.ts:300-305` 在 `close` 事件 `preventDefault` 并
  `hide()`，配合占位托盘图标，用户点 X 后应用"消失"但进程和 Python sidecar 仍在
  运行，且没有首次提示（无气泡通知）、没有"关闭即退出"的设置项。
- **建议**：首次隐藏时用已有的 `Notification` IPC 发一条"已最小化到托盘"提示；
  长期可在 Settings 增加关闭行为选项（注意与 Settings 重构任务协调落点，但该任务
  范围不含此功能项）。
- **用户价值**：中（桌面应用常见困惑点；尤其托盘图标目前几乎认不出来）
- **工作量**：S
- **风险**：低

### 7. 翻译任务无法取消、关闭对话框即丢失进度且无法重新挂接

- **现状**：`components/reader/translate-dialog.tsx:112-120` 在对话框关闭时直接
  `ws.close()` 并把状态重置为 `INITIAL_STATE`；后端 job 继续运行但前端再也看不到
  进度，也没有取消接口调用；Footer 的 Close 按钮在 busy 时被禁用（287 行），
  用户被锁在对话框里直到完成或失败。另外目标语言和模型是自由文本输入框
  （197-218 行），没有下拉选项或校验。
- **建议**：（a）busy 时允许"后台运行"关闭，并支持按 jobId 重连 WS（后端 WS 已按
  jobId 寻址）；（b）增加取消按钮（需后端补 cancel 端点）；（c）目标语言改为常见
  语言下拉 + 模型从 settings 默认带出。
- **用户价值**：中-高（翻译动辄数分钟，锁死对话框体验差）
- **工作量**：M（重连）/ L（含后端取消）
- **风险**：中（job 生命周期管理）

### 8. `/paper` 与 `/queries` 导航页是静态占位卡片

- **现状**：侧边栏 "Papers"（`/paper`）和 "Queries"（`/queries`）是一级导航项
  （`components/shell/app-sidebar.tsx:25-29`），但 `routes/paper-index.tsx:4-23` 和
  `routes/queries.tsx:4-30` 只渲染一段解释文案，不展示任何列表。真正的列表只存在
  于 workspace 页的标签里（而该标签切换目前还是坏的，见候选 1）。用户点导航得到
  "说明书"而非内容。
- **建议**：让 `/paper`、`/queries` 复用 workspace 页已有的 `PapersTab`/`QueriesTab`
  数据展示（含 skeleton/error/empty 三态，这部分实现已经很完整），说明文案降级为
  空状态附注。
- **用户价值**：高（导航与内容不符是当前信息架构最大断点）
- **工作量**:M
- **风险**：低

### 9. PDF 阅读器缺少适配宽度缩放、文本搜索与滚轮缩放

- **现状**：`components/reader/pdf-viewer.tsx:340` 基准宽度固定 720px，
  `containerWidthRef`（335、490-501 行）已跟踪容器宽度但注释自述 fit-width 未实现；
  工具栏只有 50–300% 步进缩放（`pdf-toolbar.tsx:21-24`）。已有键盘快捷键
  （Ctrl+=/-/0、PageUp/Down/Home/End，`pdf-viewer.tsx:504-560`）但需要先点击容器
  获得焦点才生效（563-565 行），且没有 Ctrl+滚轮缩放。文本层已渲染
  （`pdf-viewer.tsx:732-736`）但没有文档内搜索（Ctrl+F）和目录/缩略图侧栏。
- **建议**：优先级排序：fit-width 模式（容器宽度已有）> Ctrl+滚轮缩放 > 文档内
  文本搜索 > 目录侧栏。
- **用户价值**：中-高（阅读是产品核心场景；fit-width 是 PDF 阅读器的基本预期）
- **工作量**：fit-width S、滚轮缩放 S、搜索 L、目录 M
- **风险**：低-中（搜索需遍历 textContent，注意大文档性能）

### 10. 阅读页"无工作区"提示文案过时且指引开发者操作

- **现状**：`routes/paper-read.tsx:306-318` `NoWorkspaceState` 文案写着工作区选择器
  "coming in Phase 3"，并指导用户手写 `localStorage` 的
  `xreadagent.workspacePath`——而工作区选择器其实早已实现（侧边栏
  `app-sidebar.tsx:50-67` 和菜单 Ctrl+O 都可用）。
- **建议**：替换为带"打开工作区"按钮的标准空状态（复用 `useWorkspaceActions`）。
- **用户价值**：中（文案误导且暴露内部实现）
- **工作量**：S
- **风险**：无

### 11. Copilot 面板：单轮问答、无流式输出、刷新即丢历史、无快捷键

- **现状**：`components/shell/copilot-sidebar.tsx`：每次提问只发当前问题
  （248-255 行，`postQuery` 不带对话历史），后续问题无法追问；回答非流式，等待期
  只有 "Thinking..."（211-218 行）；消息存于组件 state（226 行），刷新/重启即丢；
  输入是单行 `Input`（393-401 行）无多行支持；没有打开面板的键盘快捷键，也没有
  复制回答按钮。
- **建议**：MVP 顺序：会话历史持久化到 localStorage（S）→ 打开/聚焦快捷键如
  Ctrl+K 或 Ctrl+J（S）→ 复制按钮（S）→ 多轮上下文与流式输出（需要后端配合，L）。
- **用户价值**：中（问答可用但"像个表单"，不像助手）
- **工作量**：S–L 分级
- **风险**：多轮/流式涉及后端协议，单独评估

### 12. 其余主界面字符串未本地化（与 Settings 任务的边界外延）

- **现状**：进行中任务只本地化 settings、settings sidecar 面板和主侧边栏
  （其 prd.md "Out of Scope" 明示不覆盖其余界面）。Workspace 页、阅读器工具栏、
  翻译对话框、Copilot、空状态等仍是硬编码英文（如 `workspace.tsx:233-234`、
  `translate-dialog.tsx:186-190`、`copilot-sidebar.tsx:362-366`）。i18n 基础设施
  （`lib/i18n.tsx` 字典 + `t(key)`）已就位。
- **建议**：在 Settings 任务合并后，按页面分批把高频界面字符串迁入字典。
  注意只扩展字典，不改动该任务建立的机制。
- **用户价值**：中（默认语言是 zh，但大部分界面仍显示英文，体验割裂）
- **工作量**：M（机械性大、风险低，可拆分）
- **风险**：低；需等待前置任务合并避免冲突

### 13. 健康横幅常驻占用空间；菜单 About 为占位行为

- **现状**：`components/shell/health-banner.tsx:62-81` 在 sidecar 正常时也常驻显示
  "Sidecar ready" 一行横幅（每 5 秒轮询）。菜单 Help > About 实际是跳转 `/settings`
  （`electron/src/menu.ts:130-133`），"Check for Updates" 永久禁用（80-86 行）；
  File 菜单没有 "Import Paper" 项/快捷键（导入只能从页面按钮触发）。
- **建议**：横幅改为仅在 loading/error 时显示，正常态收纳为侧边栏底部状态点；
  About 改为 `app.showAboutPanel()` 或简单对话框；File 菜单补 Import Paper
  （Ctrl+I）转发 IPC 到 renderer。
- **用户价值**：低-中（视觉噪音与细节打磨）
- **工作量**：S
- **风险**：低（注意 e2e/测试中可能依赖 `data-testid="health-banner"` 常驻）

### 14. 缺少全局搜索 / 命令面板

- **现状**：没有任何跨论文/概念/查询的搜索入口（全仓无相关实现）；工作区列表无
  过滤框；查找一篇论文只能滚动卡片网格（`workspace.tsx:56-85`）。
- **建议**：先做工作区列表的客户端过滤输入框（数据已全量拉取，S）；后续可做
  Ctrl+P 命令面板（聚合 papers/concepts/queries 导航，M）。
- **用户价值**：中（库变大后将成为高价值项，当前库小则价值有限）
- **工作量**：S（过滤）/ M（命令面板）
- **风险**：低

## 相关 Spec 约束

- `.trellis/spec/frontend/component-guidelines.md`（commit de6d3c2 新增）："Desktop App
  UX, Not Website UX"——新界面须是工具型表面：清晰导航、紧凑信息层级、可预期控件、
  工作流优先；禁止 hero 区、营销卡片等落地页模式。上述候选 8/10/13 与该约束直接呼应
  （占位说明卡片与营销式空状态正是被点名的模式）。
- 前端代码中无 TODO/FIXME 标记（grep 无匹配）；唯一的代码内自述欠账是托盘占位图标
  （`electron/src/main.ts:402`）与 fit-width 未实现（`pdf-viewer.tsx:338-339` 注释）。

## Top 5 排名（按 价值/工作量 综合）

1. **候选 1：修复 Workspace 标签联动 Bug**——Concepts/Queries 列表当前不可达，S 工作量修复核心断点。
2. **候选 3：外部链接走系统浏览器**——S 工作量消除安全隐患 + 明显的桌面体验缺陷。
3. **候选 8：让 /paper、/queries 导航页展示真实列表**——修复信息架构断点，复用已有 Tab 实现。
4. **候选 2：Ingest 进度反馈**——核心流程最痛的等待体验；可先做 M 级折中（全局指示 + 完成通知）。
5. **候选 4 + 5 打包：拖拽导入 + 窗口状态持久化/正式图标**——共同构成"像正经桌面应用"的基本盘。

## Caveats / Not Found

- 未实际运行应用验证候选 1 的运行时表现（基于 Radix Tabs 非受控双根的代码事实推断，
  置信度高，建议实现前手动复现一次）。
- 未审查 `routes/concept.tsx`、`routes/query-detail.tsx` 的细节（与 paper.tsx 模式
  推断一致）；`routes/settings.tsx` 按要求排除。
- 后端 ingest 改异步 job 的工作量估算未深入核对 orchestrator 的可中断性。
