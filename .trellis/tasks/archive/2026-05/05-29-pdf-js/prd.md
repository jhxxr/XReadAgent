# PDF.js 阅读器 + 翻译对话框增强

## Goal

增强 XReadAgent 的 PDF 阅读体验，从"能看"升级到"好用"。核心改进：虚拟滚动、文本选择、缩放控制、页面导航、PDF 加载进度。翻译对话框和 3-tab 阅读器已完整，不需要重写。

## What I already know

* **PDF.js 已集成**：`pdfjs-dist 5.4.149` + worker bootstrap (`lib/pdfjs.ts`)
* **PdfViewer 已有**：canvas 渲染，single/dual 模式，但无虚拟滚动/文本层/缩放/导航
* **TranslateDialog 已完成**：完整的 BabelDOC 翻译进度追踪
* **3-tab 阅读器已完成**：Original/Dual/Translated + 自动切换
* **所有后端 API 已完成**：translate, manifest, file serve, WS events
* **源码注释明确指出 Phase 2B 需要增强**：虚拟滚动、缩放、导航等（见 `pdf-viewer.tsx:39-44`）

## Research References

* [`research/pdfjs-integration-in-react-electron.md`](research/pdfjs-integration-in-react-electron.md) — XReadAgent 直接使用 pdfjs-dist，不依赖 react-pdf
* [`research/dual-column-pdf-reader-ux-patterns.md`](research/dual-column-pdf-reader-ux-patterns.md) — BabelDOC 交替页面单 PDF 模式，无需滚动同步
* [`research/frontend-existing.md`](research/frontend-existing.md) — 完整的现有代码清单和缺口分析
* [`research/xreadagent-translation-pipeline.md`](research/xreadagent-translation-pipeline.md) — 翻译管线完整追踪

## Assumptions (temporary)

- A1. 不引入新的 PDF 渲染库（react-pdf、@react-pdf-viewer 等），继续用 pdfjs-dist 直接集成
- A2. 文本层使用 pdfjs-dist 内置的 `TextLayerBuilder`，不需要注解层
- A3. 虚拟滚动使用 `@tanstack/react-virtual`（项目已有 TanStack 依赖生态）
- A4. 缩放范围 50%–300%，支持 fit-width

## Decisions

- **D1. 页面导航**：页码输入 + 上下页按钮，无缩略图侧边栏。工具栏显示 "12 / 87"，可点击输入跳转。轻量方案，不占阅读空间。

## Open Questions

(none — requirements clear from research)

## Requirements (evolving)

### R-VIRTUAL: 虚拟滚动

- 只渲染当前视口内 + 缓冲区的页面，不渲染全部页面
- 滚动时动态加载/卸载页面 canvas
- 大 PDF（100+ 页）流畅滚动，内存占用合理

### R-TEXT: 文本选择层

- 启用 pdfjs-dist TextLayer，覆盖在 canvas 上方
- 用户可以选中文本、复制
- 文本层透明度/样式匹配阅读体验

### R-ZOOM: 缩放控制

- 工具栏：放大 / 缩小 / 适合宽度 / 重置
- 支持键盘快捷键（Ctrl+/Ctrl-）
- 缩放范围 50%–300%
- 缩放时保持当前页位置

### R-NAV: 页面导航

- 页码显示：当前页 / 总页数
- 页码输入跳转
- 上/下页按钮
- 键盘快捷键：Page Up/Down, Home/End

### R-PROGRESS: PDF 加载进度

- 大 PDF 下载时显示进度条
- 页面渲染时显示加载状态

### R-ROBUST: 健壮性

- 加密 PDF 显示友好错误（"此 PDF 需要密码，暂不支持"）
- 损坏的 PDF 或渲染失败的页面显示错误占位符而非崩溃
- 超大 PDF（500+ 页）内存保护：虚拟滚动确保不渲染全部页面

### R-STATE: 跨 tab 状态保持

- 缩放级别在 Original/Dual/Translated tab 切换时保持
- 当前页位置在 tab 切换时尽量保持（按页码，非像素偏移）
- 翻译完成后自动切换到 dual tab 时，保持当前阅读位置

### R-FUTURE: 未来预留

- 虚拟滚动使用抽象 page-renderer 接口，为未来搜索高亮预留渲染钩子
- TextLayer 渲染独立于 canvas 层，未来可独立切换显示/隐藏

- 大 PDF 下载时显示进度条
- 页面渲染时显示加载状态

## Acceptance Criteria (evolving)

- [ ] 100 页 PDF 滚动流畅，内存 <500 MB
- [ ] 可以选中 PDF 文本并复制到剪贴板
- [ ] 缩放 50%–300%，快捷键正常工作
- [ ] 页码输入跳转到指定页
- [ ] PDF 加载时有进度反馈
- [ ] 加密/损坏 PDF 显示友好错误而非崩溃
- [ ] 缩放级别在 tab 切换时保持
- [ ] 翻译完成后切换 tab 时保持阅读位置

## Definition of Done

- Tests added/updated (unit/integration where appropriate)
- Lint / typecheck / CI green
- Docs/notes updated if behavior changes
- 100+ 页 PDF 性能测试

## Out of Scope (explicit)

- PDF 注解/批注/高亮
- PDF 搜索（Ctrl+F）
- 缩略图侧边栏
- PDF 书签/目录
- 触摸手势/移动端适配
- 源路径发现 API（需要后端改动，独立任务）
- PDF 打印
- PDF 搜索高亮（v2 预留架构，不实现 UI）
- 文本层显示/隐藏切换（v2）

## Technical Notes

- `pdfjs-dist 5.4.149` 已安装，worker 已配置
- `PdfViewer` 在 `frontend/src/components/reader/pdf-viewer.tsx`
- `paper-read.tsx` 是 3-tab 阅读器路由
- 项目使用 TanStack 系列库，`@tanstack/react-virtual` 可用于虚拟滚动
- BabelDOC dual PDF 使用交替页面模式，dual 模式下页面按索引配对
- 前端 spec 要求：shadcn/ui 组件、CVA variants、`cn()` utility