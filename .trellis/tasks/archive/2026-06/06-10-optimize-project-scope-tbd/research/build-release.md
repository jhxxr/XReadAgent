# Research: 构建 / 发布工程优化候选项

- **Query**: 调查 CI/Release 工作流、打包、依赖管理、版本管理、开发体验中的优化候选项
- **Scope**: internal（仓库配置实读，未做外部联网验证）
- **Date**: 2026-06-11

## 范围排除说明

两个进行中的任务已存在，其范围从本文候选项中排除：

- `.trellis/tasks/06-01-fix-sidecar-serve-frontend-spa-and-remove-404-not-found-at/` — sidecar 提供前端 SPA、消除 `/` 404。两个任务目录中只有 `task.json` + jsonl 日志，**没有 prd.md / plan.md**，范围只能从标题推断。
- `.trellis/tasks/06-01-release-v0-0-4-sidecar-fix-push-tag-let-ci-build-publish/` — 推 v0.0.4 tag 让 CI 构建发布。注意：仓库 tag 已到 **v0.0.7**（`git tag` 列表 v0.0.1–v0.0.7），该任务状态仍为 `in_progress`，疑似过期未关闭。

凡候选项触及上述范围处会单独标注。

---

## 一、CI 工作流现状（.github/workflows/ci.yml）

结构：4 个 job —— `backend`（ubuntu, uv sync + ruff + mypy + pytest）、`frontend`（pnpm lint/typecheck/test/build）、`electron`（pnpm typecheck/test/build）、`e2e`（`needs: [backend, frontend, electron]`，串行长尾）。有 concurrency 取消（ci.yml:12-14）。

### 候选 C1：e2e job 缺少 pnpm 缓存 + 串行依赖全部三个 job

- **现状**：ci.yml:131-133 的 `actions/setup-node@v6` 没有 `cache: pnpm`（backend/frontend/electron job 都有，ci.yml:58-62 / 93-97）；e2e 还重复执行 `uv sync --frozen`（ci.yml:135-136）和 `pnpm install`（ci.yml:138-139）。`needs: [backend, frontend, electron]`（ci.yml:115）使总 CI 时长 ≈ max(三个 job) + e2e 全量重装。
- **建议**：给 e2e 的 setup-node 加 `cache: pnpm` + `cache-dependency-path: electron/pnpm-lock.yaml`；评估 e2e 是否真的需要等 frontend job（它不装 frontend 依赖，只跑 sidecar 生命周期测试，ci.yml:141-142）——可改为 `needs: [backend, electron]` 或并行。
- **价值**: 中 | **工作量**: S | **风险**: 低（纯 CI 配置）

### 候选 C2：uv 缓存与 setup-python 冗余

- **现状**：`astral-sh/setup-uv@v8.1.0`（ci.yml:24-25 等 3 处）v8 默认 `enable-cache: auto`，在 GitHub 托管 runner 上**通常已启用** uv 缓存（未显式配置，建议实测一次 run log 确认）；紧随其后的 `actions/setup-python@v6`（ci.yml:27-30）与 setup-uv 的 `python-version` 输入功能重复——uv 自己能装管 Python 3.12。
- **建议**：显式声明 `enable-cache: true` + `cache-dependency-glob: uv.lock`（消除歧义），并用 setup-uv 的 `python-version: "3.12"` 替代 setup-python，少一个 step × 4 处（含 release.yml）。
- **价值**: 低 | **工作量**: S | **风险**: 低

### 候选 C3：frontend job 的 `pnpm build` 产物未复用

- **现状**：ci.yml:76-77 构建 frontend dist 仅作验证，无 artifact 上传；release 流程里 `pack.mjs` 又会重建（electron/scripts/pack.mjs:66-72）。CI 与 Release 是不同触发，复用价值有限。
- **建议**：保持现状即可，或仅当未来 e2e 需要前端静态资源时再上传 artifact。
- **价值**: 低 | **工作量**: S | **风险**: 低

---

## 二、Release 工作流与打包（.github/workflows/release.yml + electron/）

结构：tag `v*` 触发；`build-windows`（NSIS x64）→ `release`（softprops/action-gh-release）。`build-macos` 整体禁用（release.yml:69 `if: false`，原因：`universal` target 与单架构捆绑 Python 的 mach-o 数量不匹配，release.yml:65-68 注释）。Linux 仅在 electron-builder.yml:151-155 预留。

打包方式：**非 PyInstaller**。`bundle-python.mjs` 下载 python-build-standalone CPython 3.12.8（electron/scripts/bundle-python.mjs:40-41）→ `uv venv` + `uv pip install <repo根>`（bundle-python.mjs:294, 307）→ 复制 backend 源码；electron-builder 将 `python/`、`python-venv/`、`backend/`、`frontend/dist` 作为 extraResources 平铺（electron/electron-builder.yml:39-60），asar 仅含 esbuild 产物 dist/（files 配置，electron-builder.yml:33-35）。

体积驱动：venv 内 langchain 全家桶（uv.lock: langchain 1.3.1 + langgraph + anthropic/openai SDK）、**onnxruntime 1.20.1**（uv.lock:2122，babeldoc 传递依赖）、**pymupdf 1.27.2.3**（uv.lock:2755）、markitdown[pdf,docx,pptx,xlsx] 全 extras（pyproject.toml:24）；再加 CPython 本体。BabelDOC 的 ~80MB ONNX 模型**不打进安装包**，运行时下载（backend/src/xreadagent/translation/worker.py:5 注释、worker.py:472-474 `model_download_*` 事件）——对体积有利，对离线首译体验是已知 tradeoff。前端 pdfjs-dist 5.4.149（frontend/package.json:34）只影响 frontend/dist 几 MB，非主要驱动。

### 候选 R1：发布 venv 不按 uv.lock 解析（可复现性缺口）★

- **现状**：bundle-python.mjs:307 用 `uv pip install --python <venv> "<rootDir>"` 从 pyproject.toml **现场解析**依赖，完全绕过 uv.lock。同一 tag 在不同日期重跑 Release，装进安装包的传递依赖版本可能不同（babeldoc==0.6.2 是精确 pin 没问题，但 langchain/fastapi/onnxruntime 等都是范围约束）。
- **建议**：改为 `uv export --frozen --no-dev -o requirements.txt && uv pip install -r requirements.txt`（或 `uv sync --frozen --no-dev` 指向该 venv），使安装包依赖与 uv.lock 一致。
- **价值**: 高 | **工作量**: S | **风险**: 低（行为更确定）

### 候选 R2：release.yml 中 `uv sync --frozen` 是死步骤

- **现状**：release.yml:46-47「Install backend dependencies: uv sync --frozen」在仓库根创建 .venv，但后续 `pnpm pack:python`（bundle-python.mjs）自建独立 venv，`pnpm dist`（pack.mjs）全程不碰根 .venv。该步骤在 Windows runner 上白装一遍全量依赖（含 onnxruntime 等大包），估计浪费 2-5 分钟。macOS job 同样存在（release.yml:98-99，当前禁用）。
- **建议**：删除该 step（若采纳 R1 的 `uv export` 方案则保留 uv 本体安装即可）。
- **价值**: 中 | **工作量**: S | **风险**: 低（需跑一次 release 验证无隐式依赖）

### 候选 R3：CPython 归档每次发布重新下载，无缓存

- **现状**：bundle-python.mjs:219-226 每次 `pnpm pack:python` 用 curl 下载 python-build-standalone 归档（~30-60MB），CI 无 `actions/cache`。electron-builder 自身的 Electron 二进制缓存也未显式配置（默认 `~/.cache/electron`，Windows `%LOCALAPPDATA%`，未被 cache action 覆盖，每次重下 Electron 34 ~100MB）。
- **建议**：release.yml 增加 `actions/cache`：key 含 `PYTHON_RELEASE_TAG`（20241219）+ platform，path 指向归档落点；另加一条缓存 electron 与 electron-builder 缓存目录（key 用 electron/pnpm-lock.yaml hash）。
- **价值**: 中 | **工作量**: S | **风险**: 低

### 候选 R4：release pnpm 缓存 key 只含 electron 锁文件

- **现状**：release.yml:26-30 `cache-dependency-path: electron/pnpm-lock.yaml`，但 job 同时安装 frontend 依赖（release.yml:40-41），frontend/pnpm-lock.yaml 变更不会失效缓存、frontend 包也未必命中 store。
- **建议**：`cache-dependency-path` 写成多行同时含 `frontend/pnpm-lock.yaml` 与 `electron/pnpm-lock.yaml`（CI 的 frontend/electron job 已各自正确，ci.yml:62/97）。
- **价值**: 低-中 | **工作量**: S | **风险**: 低

### 候选 R5：安装包瘦身（venv 修剪 + 源码去重）

- **现状**：extraResources 对 `python-venv` 全量 `**/*` 复制（electron-builder.yml:47-50），包含 `__pycache__`/`.pyc`、`*.dist-info`、测试文件；且 xreadagent 包被装进 venv site-packages（bundle-python.mjs:307 非 editable 安装）**又**复制到 `resources/backend/xreadagent`（bundle-python.mjs:330-331），运行时靠 PYTHONPATH 让后者优先（bundle-python.mjs:297-299 注释）——双份源码。NSIS 打包数万小文件也拖慢 electron-builder 阶段。
- **建议**：(a) extraResources filter 排除 `**/__pycache__/**`、`**/*.pyc`、`**/tests/**`；(b) `uv pip install --no-compile`；(c) venv 安装后删除 site-packages 里的 xreadagent（保留 dist-info 或改 `--no-deps` 拆开装依赖）。预估可减 10-20% 体积并加快打包。
- **价值**: 中 | **工作量**: M | **风险**: 中（需安装后冒烟验证 sidecar 启动 + 翻译 worker）

### 候选 R6：macOS 构建恢复（arm64-only）

- **现状**：release.yml:69 `if: false` 禁用；根因是 electron-builder.yml:106-113 mac target 为 `universal`，与单架构捆绑 Python 冲突（release.yml:65-68 注释，"Tracked separately"）。
- **建议**：mac target 改 `arch: [arm64]` + dmg/zip，即可重启 macos job。**注意**：注释称已单独跟踪，落地前确认无重复任务；与两个排除任务无重叠。
- **价值**: 高（恢复整个平台）| **工作量**: M | **风险**: 中（无签名 Gatekeeper 提示已有处理，CSC_IDENTITY_AUTO_DISCOVERY=false，release.yml:106-108）

---

## 三、依赖管理

- **babeldoc==0.6.2 精确 pin**：pyproject.toml:34-39 有充分理由注释（BabelDOC API 全内部，升级=破坏性事件）。**但** 版本字符串又硬编码在 backend/src/xreadagent/translation/worker.py:68（`babeldoc_version: str = "0.6.2"`）和 service.py:51（`_BABELDOC_VERSION_DEFAULT = "0.6.2"`）两处 —— 升级时三处要同步，见候选 V1。
- **deepagents 策略**：pyproject.toml:30 `>=0.6,<1.0`，注释明确（等 1.0 稳定再升），uv.lock 锁 0.6.3（uv.lock:664-665）。策略本身合理，无需动。
- **uv.lock 新鲜度**：最后更新于 0.0.7 版本提交（106037c，2026-06-10），与 pyproject 同步，**新鲜**。
- **疑似可瘦身**：markitdown 启用了 `[pdf,docx,pptx,xlsx]` 全部 extras（pyproject.toml:24）——若产品只走 PDF 链路可减 extras（需先 grep 确认 docx/pptx/xlsx 路径是否被 ingest 用到，本次未深查，标记为待验证）。hyperscan 为 babeldoc 传递依赖、x86-only（pyproject.toml:38 注释），mac arm64 打包时需确认可解析（与 R6 关联）。
- **前端依赖**：frontend/package.json 干净，无重复 UI 库；最重为 pdfjs-dist 5.4.149（精确 pin，frontend/package.json:34）。vite.config.ts 无 manualChunks 配置（frontend/vite.config.ts 全文 35 行，仅 proxy/alias）——bundle 拆分属低优先级。
- **monorepo 结构**：frontend 与 electron 各有独立 pnpm-lock.yaml（无根 workspace），typescript/vitest/@types/node 各装一份。统一为根 pnpm-workspace 可去重并简化 CI 缓存，但改动面大（pack 脚本路径、CI 4 处），价值/工作量比一般，列为可选。

---

## 四、版本管理

### 候选 V1：版本号 5 处手工同步，无 bump 脚本 ★

- **现状**：`grep`/`git show 106037c --stat` 证实 0.0.7 bump 手工改了 **5 个文件**：pyproject.toml:3、frontend/package.json:4、electron/package.json:3、backend/src/xreadagent/__init__.py:35、uv.lock。仓库无任何 bump 脚本（根目录无 scripts/、无 Makefile/justfile/根 package.json；electron/scripts 与 backend/scripts 均无 bump 相关内容）。再加 babeldoc 版本字符串 2 处硬编码（worker.py:68、service.py:51，应改为读 `importlib.metadata.version("babeldoc")` 或集中常量）。
- **发布流程**：手工 bump → commit → 推 `v*` tag → release.yml 触发。无 tag 与文件版本一致性校验（推错 tag 不报错，安装包文件名用 electron/package.json 版本，electron-builder.yml:95 `${version}`）。
- **建议**：新增 `scripts/bump_version.py`（改 5 处 + `uv lock` 刷新），并在 release.yml 加一步校验 `tag == pyproject version`，不一致即 fail-fast。
- **价值**: 高 | **工作量**: S | **风险**: 低
- **与排除任务的关系**：「release v0.0.4 push tag」任务即是这种手工流程的执行实例（且已过期，tag 已到 v0.0.7）；本候选改流程不改该任务范围，但落地后建议顺手关闭该过期任务。

---

## 五、开发体验

### 候选 D1：无根级一键 lint/test 入口

- **现状**：根目录无 Makefile/justfile/Taskfile/package.json。跑全量检查需手工三段：`uv run ruff/mypy/pytest`（根）、`cd frontend && pnpm lint/typecheck/test`、`cd electron && pnpm typecheck/test`。CI 的 step 命令（ci.yml:36-42, 67-77, 102-109）就是这套命令的复写，本地与 CI 无单一事实来源。electron 的 `lint` 实际是 `tsc -b --noEmit` 的别名（electron/package.json:21），无真正 linter。
- **建议**：加根级 `justfile`（或 Makefile）：`just lint / typecheck / test / check-all`，CI step 改调 just 目标；顺带给 electron 接入 eslint（复用 frontend 配置）可另列小任务。
- **价值**: 中 | **工作量**: S | **风险**: 低

---

## Top-5 排名（价值/工作量/风险综合）

| # | 候选 | 一句话 | 价值 | 工作量 | 风险 |
|---|------|--------|------|--------|------|
| 1 | **R1** | 发布 venv 改按 uv.lock 安装（bundle-python.mjs:307 现绕过锁文件），消除发布不可复现 | 高 | S | 低 |
| 2 | **V1** | 单一来源版本 bump 脚本（现 5 文件手工 + babeldoc 版本 2 处硬编码）+ tag/版本一致性校验 | 高 | S | 低 |
| 3 | **R2+R3+R4** | Release 工作流提速包：删冗余 `uv sync`、缓存 CPython 归档与 Electron 二进制、补 frontend 锁文件缓存 key | 中 | S | 低 |
| 4 | **D1** | 根级 justfile 统一三层 lint/test，CI 与本地共用命令 | 中 | S | 低 |
| 5 | **R5** | 安装包瘦身：venv 修剪 pyc/__pycache__ + xreadagent 双份源码去重 | 中 | M | 中 |

（R6 macOS arm64 恢复价值最高但注释称"Tracked separately"，落地前需先确认是否已有跟踪任务，故不入榜。）

## Caveats / Not Found

- 两个排除任务无 prd.md/plan.md，范围由标题与 jsonl 推断；v0.0.4 release 任务疑似过期（tag 已至 v0.0.7）。
- 无外部搜索工具可用（exa MCP 未挂载），setup-uv v8 `enable-cache` 默认 auto 的判断来自模型知识，建议看一次实际 CI run log 确认 uv 缓存是否命中。
- markitdown extras 实际使用面（docx/pptx/xlsx）未逐一 grep 验证。
- 本地 electron/release 与 electron/resources 为空，无法实测当前安装包体积；体积驱动结论基于 uv.lock 依赖图与脚本注释（worker.py:5 的 ~80MB 模型为运行时下载）。
