# Research: 运行时性能优化候选项

- **Query**: 调查 XReadAgent 运行时性能优化候选项(启动路径 / 后端导入 / 前端打包与渲染 / 翻译流程 / API 轮询)
- **Scope**: internal(全部基于源码阅读 + 实测 `python -X importtime`)
- **Date**: 2026-06-11

---

## 一、应用 / Sidecar 启动路径(Electron)

### 现状

启动链条是**完全串行**的(`electron/src/main.ts`):

1. `app.whenReady()` → 建托盘、菜单 → `showSplashAndStartSidecar()`(main.ts:57-71)
2. 显示 splash → `sidecarManager.start()`(main.ts:250-263)
3. `start()` 内部:spawn Python → 等 stdout 的 `SIDECAR_READY port=N` 标记(sidecar.ts:267-303)→ 再轮询 `/healthz`,间隔 200ms(sidecar.ts:305-332)
4. 全部成功后才 `createMainWindow()`(main.ts:263)→ `loadURL` → `ready-to-show` 才显示窗口(main.ts:317-321)

关键参数:

| 参数 | 值 | 位置 |
|---|---|---|
| Sidecar 启动超时 | 30 秒 | sidecar.ts:16 `SIDECAR_STARTUP_TIMEOUT_MS` |
| healthz 轮询间隔 | 200ms | sidecar.ts:307 |
| 优雅退出超时 | 5 秒 | sidecar.ts:19 |
| 崩溃重启 | 最多 3 次,指数退避 1s 起 | sidecar.ts:25-28 |

### 性能问题

- **主窗口创建被 Python 启动完全阻塞**。开发模式下渲染器由 Vite 提供(main.ts:332),完全可以与 sidecar 启动并行;但代码强制等 sidecar ready 才 `createMainWindow()`。生产模式下前端由 sidecar 托管静态文件(main.ts:329),窗口加载确实依赖端口,但 BrowserWindow 的创建、preload 编译本身可以提前做。
- **冷启动有超时风险**:实测后端模块**冷缓存**导入耗时极高(见下节,首次约 78 秒,含 pyc 编译 + Windows Defender 扫描),而 `SIDECAR_READY` 是在 uvicorn lifespan 启动时才打印(backend/src/xreadagent/api/__main__.py:34-38),即所有模块导入完成之后。30 秒超时在"装机后第一次启动"场景下可能直接打到 splash 错误页。

### 优化候选

| 项 | 用户可见收益 | 工作量 | 风险 |
|---|---|---|---|
| 窗口创建/渲染器加载与 sidecar 启动并行(至少开发模式;生产模式可先建窗口、拿到端口后再 loadURL) | 中(感知启动时间缩短 1-3 秒) | S | 低;需处理"sidecar 启动失败但窗口已开"的 UI 态 |
| 提高/分级启动超时(首启检测,或以 stderr 活动作为心跳延长超时) | 高(避免首启误报失败) | S | 低 |

---

## 二、后端启动:导入图实测

### 实测数据(`.venv/Scripts/python.exe -X importtime -c "import xreadagent.api.main"`)

- **冷缓存(首次)**:累计 **约 77.8 秒**(含 pyc 编译与杀软扫描,Windows 11 实测)
- **热缓存**:累计 **约 0.86 秒**,分解如下:

| 模块 | 热缓存累计耗时 | 原因 |
|---|---|---|
| `xreadagent`(包 `__init__`) | ~523 ms | **罪魁**:`backend/src/xreadagent/__init__.py:4-17` 顶层 `from xreadagent.agents import ...` |
| └ `xreadagent.agents` → `agents.tools` | ~374 ms | `agents/tools.py:21` 顶层 `from langchain_core.tools import ...`,连带拉入 langsmith(单 `langsmith.schemas` 即 ~55ms)、requests、httpx、chardet |
| `xreadagent.api.main` 自身 | ~339 ms | 其中 `xreadagent.mcp` ~205 ms(`mcp.types` 单项 ~52ms)、fastapi ~103 ms |

### 关键事实

1. **`xreadagent/__init__.py` 把 agents 层(langchain_core/langsmith)变成了"必加载"**(backend/src/xreadagent/__init__.py:4-17)。`api/wiki_router.py` 已经刻意把 agent 导入做成请求级懒加载(wiki_router.py:283-284, 319-320),但任何 `import xreadagent.*` 都会先执行包 `__init__`,懒加载被**完全架空**。
2. 重型库本体(`langchain.chat_models`、`deepagents`、`babeldoc`)确实是懒加载的:
   - `langchain.chat_models.init_chat_model` 只在函数内导入(agents/ingest.py:626、translation/worker.py:228 等)
   - `babeldoc` 只在 worker 子进程内导入(translation/babeldoc_adapter.py:613, 666;模块 docstring 明确说明)
3. **MCP 在 `create_app()` 里急切导入并 mount**(api/main.py:242-249),热缓存 ~205ms;且 **app 被构造两次**:`api/main.py:414` 模块级 `app = create_app()`(供 `uvicorn xreadagent.api.main:app` 用),而 `python -m xreadagent.api` 的 `__main__.py:40` 又调用一次 `create_app()` —— sidecar 进程实际执行了两遍 MCP server 构建与路由注册。

### 优化候选

| 项 | 现状 | 收益 | 工作量 | 风险 |
|---|---|---|---|---|
| 清空 `xreadagent/__init__.py` 的 agents 顶层 re-export(改为 `__getattr__` 懒导出或直接删除) | __init__.py:4-17 | **高**:热启动 -0.4s,冷启动(首启)减少最多;直接降低 30s 超时风险 | S | 中:`from xreadagent import IngestAgent` 的调用方(CLI/tests)需排查;PEP 562 `__getattr__` 可保持兼容 |
| 删除 `api/main.py:414` 的模块级 `app = create_app()` 或让 `__main__` 复用它 | 双重构建 | 低-中(省一次 MCP 构建 ~0.2s) | S | 低;需确认无外部以 `xreadagent.api.main:app` 方式部署 |
| MCP mount 延后(后台任务/首个 `/mcp` 请求时挂载) | main.py:242-249 | 低(~0.2s) | M | 中:FastAPI mount 通常要求启动前完成,需用 lifespan 后台化,易引入竞态 |

---

## 三、前端:打包与 PDF 渲染

### 3.1 打包 / 代码分割:完全没有

- `frontend/vite.config.ts` 无任何 `build.rollupOptions.manualChunks` 配置(全文 34 行,只有 alias + dev proxy)。
- `frontend/src/router.tsx:4-12` **静态导入全部 8 个路由组件**;全仓库 `grep lazy\(|import\(` 仅命中 0 处(无 `React.lazy`、无动态 `import()`)。
- 后果:`pdfjs-dist`(5.4.149,主库 gzip 后约 300-400KB)经 `pdf-viewer.tsx:3-8`、`use-page-renderer.ts:2`、`lib/pdfjs.ts:10` 静态进入主 bundle;`react-markdown` + `remark-gfm`(wiki-markdown.tsx:15)同样在主 bundle。唯一分离的是 pdf worker(`lib/pdfjs.ts:11` 用 `?url`,worker 文件独立)。
- 影响:首屏(workspace 页)被迫下载/解析 reader 页才需要的 pdfjs 与 markdown 渲染链,生产模式下由 Python sidecar 的 `StaticFiles` 同步吐出(api/main.py:286-288)。

**候选**:路由级 `React.lazy` + `Suspense`(至少 `paper-read`、`paper`/`concept` 的 markdown 部分),或 `manualChunks` 把 `pdfjs-dist`、`react-markdown` 拆为独立 chunk。收益:中-高(首屏 JS 体积估计可减 40%+);工作量 S-M;风险低(桌面端本地加载,延迟可控,需注意 Suspense fallback 闪烁)。

### 3.2 PDF 阅读器(pdf-viewer.tsx,739 行)

**已做对的**:用 `@tanstack/react-virtual` 做行级虚拟化(pdf-viewer.tsx:405-410),overscan 3,只渲染视口附近页面;页面渲染委托 `usePageRenderer`,有 RenderTask 取消逻辑(use-page-renderer.ts:93-97)。

**问题点**:

1. **切 Tab 即销毁整个文档**:`paper-read.tsx:230-283` 用 Radix `TabsContent`(非 forceMount),original/dual/translated 三个 `PdfViewer` 互斥挂载。切 Tab → PdfViewer 卸载 → `loadingTask.destroy()`(pdf-viewer.tsx:219-225)→ 切回时**重新走 HTTP 下载 + PDF 解析 + 渲染全流程**。用户在原文/双语之间来回对照时每次都要等。
   - 候选:`forceMount` + CSS 隐藏,或在模块级缓存 `url → PDFDocumentProxy`。收益:**高**(对照阅读是核心场景);工作量 S-M;风险:内存占用上升(三份文档常驻),需 LRU 或限制。
2. **缩放 = 全量重渲**:`pageWidth = round(720 * zoom/100)`(pdf-viewer.tsx:343),`pageWidth` 变化使 `canvasRef` 回调身份变化(use-page-renderer.ts:91-178 依赖 `[doc, pageNumber, pageWidth]`),所有可见页重新 `getPage + render + TextLayer`。连续点缩放按钮时无防抖、无"先 CSS transform 缩放后重渲"的过渡。收益:中;工作量 M;风险:中(CSS 缩放期间文字模糊,需要 settle 后重渲)。
3. **canvas 未乘 devicePixelRatio**:use-page-renderer.ts:135-138 直接 `canvas.width = viewport.width`(CSS 像素)。HiDPI 屏上输出偏糊 —— 这是"性能换清晰度"的现状;若将来修清晰度,渲染成本会 ×dpr²,与第 2 点联动考虑。
4. **滚动时高频 setState 链**:pdf-viewer.tsx:416-443 的 effect 依赖 `virtualItems`(每次渲染都是新数组),滚动中持续计算"视口中心行"并回调 `onCurrentPageChange` → paper-read.tsx:159-164 `setPageStates` → 父组件重渲 → PdfViewer 全树 reconcile(canvas 因 ref 身份未变不会重画,但 React 工作量恒定存在)。`PdfPage` 未用 `React.memo`。收益:低-中;工作量 S;风险:低。

### 3.3 API 轮询 / WebSocket

- 全局 react-query 默认:`staleTime: 30s`、`refetchOnWindowFocus: false`(app.tsx:18-19)—— 合理。
- **唯一的常驻轮询**:`health-banner.tsx:56` `refetchInterval: 5_000`,每 5 秒打一次 `/healthz`,永不停止。成本极低(本地回环 + 简单 JSON),但 Electron 主进程其实已有 sidecar 状态推送通道(`sidecar-status` IPC 广播,main.ts:603-615),前端是双轨。收益:低;工作量 S;风险:低。
- 翻译进度走 **WebSocket**(`/ws/jobs/{job_id}`,api/main.py:199-220;前端 translate-dialog.tsx:144-167),事件实时推送,**无轮询**,设计良好。

---

## 四、翻译流程(service / worker / babeldoc_adapter)

### 现状

- **缓存**:`TranslationService.start_translation`(service.py:107-177)按 `(source_hash, target_lang, model)` 查 `TranslationsIndex`,命中且 PDF 仍在盘上则返回合成 finish 事件,**零子进程、零 LLM 调用**(service.py:126-143)—— 缓存设计良好。
- **子进程成本**:缓存未命中时,每个 job 用 `multiprocessing.get_context("spawn")` **新起一个子进程**(worker.py:135-172, 305)。worker.py:24 自述"Windows 上仅 spawn 启动就 ~2s";子进程内再 `import babeldoc`(babeldoc_adapter.py:613, 666,拉 pymupdf/onnxruntime/huggingface_hub)+ `DocLayoutModel.load_onnx()` 加载布局模型(babeldoc_adapter.py:523)。即**每次翻译任务都重复付一遍"spawn + babeldoc 全量导入 + ONNX 模型加载"的钱**,估计 5-15 秒(机器相关),之后才开始真正翻译。
- **首次运行**:warmup 下载 ~80MB ONNX + 字体资产(babeldoc_adapter.py:34-40, 598-603),已通过 monkey-patch httpx 把下载进度转成 `model_download_*` 事件推给 UI —— 首启体验已有处理,资产缓存于 `~/.cache/babeldoc/`。
- **进度流**:BabelDOC 异步生成器在子进程内的独立线程 + 独立 event loop 中驱动,逐事件推 multiprocessing queue(babeldoc_adapter.py:581-646);父进程用 50ms 轮询 `queue.get`(worker.py:369-397, poll_interval=0.05)经 `run_in_executor` 转 async。事件延迟毫秒级,无明显问题。
- **事件循环阻塞点**:`POST /api/translate` 是 `async def`(api/main.py:139),但内部同步调用 `compute_content_hash(source_path)`(service.py:121)对整个 PDF 做哈希 + 同步读 manifest。大 PDF(几十 MB)时会**阻塞 uvicorn 事件循环几百毫秒**,期间 healthz/其他请求卡顿。

### 优化候选

| 项 | 收益 | 工作量 | 风险 |
|---|---|---|---|
| 常驻 warm worker 进程(预 spawn 一个已 import babeldoc + 已 load_onnx 的进程池,任务复用) | 中(每次翻译省 5-15s 启动税;但相对整体翻译耗时数分钟,比例有限) | L | 中-高:进程长驻后崩溃隔离语义变化(现在"一个坏 PDF 只坏一个 job"是刻意设计,worker.py:4-8);内存常驻 ~80MB+ |
| 翻译发起后**预热**:用户打开 TranslateDialog 时即后台 spawn 进程做 import(不等点击开始) | 中(感知等待缩短) | M | 中 |
| `compute_content_hash` 移到 `run_in_executor` / `anyio.to_thread` | 低-中(消除事件循环卡顿) | S | 低 |

---

## 五、Top-5 排序(按"用户可见收益 ÷ 工作量"综合)

1. **清理 `backend/src/xreadagent/__init__.py:4-17` 的 agents 顶层导入(改 PEP 562 懒导出)** —— 收益:高(sidecar 热启动 -0.4s,冷启动/首启大幅缩短,直接缓解 30s 启动超时风险);工作量 S;风险中(需兼容 `from xreadagent import X` 调用方)。这是单点改动收益最大的项。
2. **PDF 文档跨 Tab 缓存(paper-read.tsx Tabs forceMount 或 `url → PDFDocumentProxy` 缓存)** —— 收益:高(原文/双语对照切换从"数秒重载"变为即时);工作量 S-M;风险低-中(内存)。
3. **前端代码分割(router.tsx 路由级 React.lazy + pdfjs-dist/react-markdown 独立 chunk)** —— 收益:中-高(首屏 JS 显著减小、主窗口 ready-to-show 提前);工作量 S-M;风险低。
4. **Electron 窗口创建与 sidecar 启动并行 + 首启超时分级** —— 收益:中(感知启动快 1-3s,消除首启误报);工作量 S;风险低。
5. **缩放渲染优化(防抖 + CSS transform 过渡)与翻译子进程预热** —— 并列第五:前者收益中/工作量 M,后者收益中/工作量 M-L;均为体验打磨级,建议放在前四项之后。

## Caveats / Not Found

- 冷启动 78s 是开发机(Windows 11 + Defender)单次实测,含 `-X importtime` 自身开销与 pyc 编译;打包产物(预编译 pyc、不同杀软策略)下数值会不同,但量级结论(冷启动远超热启动、可能触及 30s 超时)成立。
- 未实测前端 bundle 实际体积(未运行 `vite build`);pdfjs-dist/react-markdown 体积为经验估值。
- `deepagents` 未在任何模块顶层导入(grep 仅命中注释/文档),不构成启动成本。
- 生产打包模式下 sidecar 的 StaticFiles 吞吐未测;本地回环下大概率不是瓶颈。

---

## A2 实施结果(2026-06-11)

实现方式:`router.tsx` 改用 TanStack Router `lazyRouteComponent`(`/workspace` 首屏路由保持 eager,其余 7 个路由按需动态 import);`copilot-sidebar.tsx` 的 `WikiMarkdown`(shell 常驻组件中唯一的 react-markdown 静态引用)改为 `React.lazy` + `Suspense`(fallback 为纯文本)。未改 vite 配置(无需 manualChunks,Rollup 自动按动态 import 边界拆分)。

### Before(`pnpm build`,单一 entry chunk)

| 文件 | 大小 | gzip |
|---|---|---|
| `assets/index-CDRd6HPI.js`(entry) | 1,175.93 kB | 354.46 kB |
| `assets/pdf.worker.min-r-TJsTTt.mjs`(原本就独立) | 1,039.21 kB | — |
| `assets/index-BM5vGNWU.css` | 47.12 kB | 8.54 kB |

### After

| 文件 | 大小 | gzip | 加载时机 |
|---|---|---|---|
| `assets/index-B0_Tf1-b.js`(entry) | 537.78 kB | 167.79 kB | 启动 |
| `assets/paper-read-Di4mrXVe.js`(含 pdfjs-dist) | 462.11 kB | 135.90 kB | 进入阅读器 |
| `assets/wiki-markdown-low0GguP.js`(react-markdown + remark-gfm) | 159.44 kB | 48.29 kB | 打开 wiki 页 / copilot 首条回答 |
| `assets/settings-FN0aUo8G.js` | 14.04 kB | 3.92 kB | 进入设置 |
| `paper / query-detail / concept / queries / paper-index / languages` 各 chunk | 0.49–2.46 kB | — | 按路由 |
| `assets/pdf.worker.min-r-TJsTTt.mjs` | 1,039.21 kB | — | 不变(`?url` worker) |

### 结论

- entry chunk **1,175.93 kB → 537.78 kB(-54%)**,gzip **354.46 kB → 167.79 kB(-53%)**。
- `grep pdfjs|GlobalWorkerOptions|micromark` 在 entry chunk 中 **0 命中** —— pdfjs-dist 完全移入 `paper-read` chunk,react-markdown 移入 `wiki-markdown` chunk(AC 达成)。
- 守护测试:`tests/routes/router-lazy.test.tsx`(eager 首页渲染 + 懒路由导航可达)。

---

## A1 实施结果(2026-06-11)

实现方式:`backend/src/xreadagent/__init__.py` 与 `backend/src/xreadagent/agents/__init__.py` 全部改为 PEP 562 `__getattr__` 懒导出(公开名单不变,`from xreadagent import IngestAgent` / `from xreadagent.agents import X` 仍可用,`__version__` 保持模块级字面量供 bump 脚本正则匹配);CLI 侧 `ingest_cmd.py` / `query_cmd.py` 把 `IngestAgent` / `QueryAgent` / 编排器移入 `run()` / `_build_agent()` 内,`llm_flags.py` 的 `PlannerMethod` 移到 `TYPE_CHECKING`(`cli/stubs.py` 仅引 schema 子模块,agents 包懒化后自动变轻)。

### 实测(warm,`.venv/Scripts/python.exe -c "import time; ...; import <module>"`,Windows 11 开发机)

| 模块 | Before | After | 变化 |
|---|---|---|---|
| `import xreadagent` | 0.512 s | **0.006 s** | -99% |
| `import xreadagent.api.main`(sidecar 启动路径) | 0.860–0.864 s | **0.628–0.630 s** | -0.23 s(余量为 fastapi+mcp+translation,见调研第二节;langchain/langsmith 链已完全移出) |
| `import xreadagent.cli.main`(CLI 派发) | 0.547 s | **0.181 s** | -67% |

冷启动未重测(需清 pyc + 杀软冷缓存),但调研中冷启动的最大头(langchain/langsmith/requests 链的首次 pyc 编译 + Defender 扫描)已不在 sidecar 启动路径上,30s 超时风险相应消除。

### 守护测试

`backend/tests/test_lazy_imports.py`:子进程导入 `xreadagent` / `xreadagent.api.main` / `xreadagent.cli.main` 后断言 `sys.modules` 中无 `langchain*/langgraph*/deepagents*/langsmith*`;另含懒导出兼容性与未知属性 AttributeError 测试。已验证:临时在 `__init__.py` 重新加回 eager `from xreadagent.agents.tools import ...` 时 3 个守护测试全部失败(随后还原)。

---

## A4 实施结果(2026-06-11)

实现方式:`electron/src/main.ts` 改为 `whenReady` 后**立即** `createMainWindow()`(加载内联 SPLASH_HTML 作为窗内 loading 态)并与 `sidecarManager.start()` 并行;sidecar ready 后在同一窗口 `loadRenderer()`(dev→Vite URL,packaged→`http://127.0.0.1:<port>/`,决策抽到可测的 `electron/src/startup.ts: resolveRendererUrl`);失败时向窗口发 `splash-error` 显示错误详情 + Retry(复用原 splash 的错误 UI 与 `splash-retry` IPC,重试改为模块级注册)。独立 splash 窗口删除;deep link 派发从 `ready-to-show` 移到 renderer 的 `did-finish-load`;托盘 Restart Sidecar 在窗口仍停留于 loading 页(data: URL)时会直接换入 renderer。新增测试 `electron/tests/startup.test.ts`。loading 页为 data: URL 内联 HTML,无需 electron-builder `files:` 变更。
