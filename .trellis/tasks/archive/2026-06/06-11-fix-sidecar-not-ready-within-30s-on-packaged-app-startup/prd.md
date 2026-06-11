# fix sidecar not ready within 30s on packaged app startup

## Background / Root Cause

打包应用（v0.0.8，Windows NSIS 安装）首次启动报错：
`Sidecar did not report ready within 30s`（截图见用户报告）。

本机复现（G:\software\XReadAgent，v0.0.8）：

- 冷缓存首跑：`python -m xreadagent.api --port 0` **120 秒零输出**（stdout/stderr 均无）。
- 同一命令在缓存预热后重跑：**0.5–1.2 秒**打印 `SIDECAR_READY`。

根因：**安装后首次启动，Windows Defender 实时扫描逐个扫描 venv 中数千个文件**
（pydantic_core/numpy 等大 .pyd/.dll + 全部 .py，且打包时 bytecode 被剪除），
首次导入风暴远超 30 秒固定预算；扫描结果缓存后续启动恢复秒级。
慢的不是我们的代码——是冷 I/O + AV，固定 30s 超时无法覆盖这一合法场景。

次级问题：`python -m xreadagent.api` 在 `__main__.py` 执行前先跑
`xreadagent/api/__init__.py`，它**急切导入** `create_app`（整条 FastAPI 链），
因此 ready 前没有任何早期信号可供 Electron 区分"正在爬导入"和"彻底挂死"。

## Requirements

1. **后端：早期 boot 标记**
   - `xreadagent/api/__init__.py` 改为 PEP 562 懒导出 `create_app`（与根包 `__init__.py` 同模式）。
   - `__main__.py` 在任何重导入（uvicorn/fastapi/create_app/TranslationService）之前，
     先向 stdout 打印并 flush `SIDECAR_BOOT`；重导入移入函数内部。
   - 契约变为：`SIDECAR_BOOT`（python 存活，stdlib 级耗时）→ `SIDECAR_READY port=<N>`（server 已起）。

2. **Electron：分级超时取代固定 30s**
   - `sidecar.ts` `waitForReady`：
     - **boot 预算 45s**：从 spawn 起 45 秒内必须看到任意 stdout/stderr 输出
       （含 `SIDECAR_BOOT`），否则判定真挂起，报错（语义同现错误）。
     - **ready 预算 240s**：看到输出后，总截止放宽到 240 秒等待 `SIDECAR_READY`
       （覆盖 Defender 冷扫描实测 >120s）。
     - 看到 boot 标记时 emit 状态（如 `booting`），splash 显示
       "First launch can take a few minutes (antivirus scan)..." 类提示。
   - 进程退出/spawn error 仍然立即失败（现行为不变）。
   - `pollHealthz` 预算独立保留（ready 后 healthz 应秒级响应，不需要 240s）。
   - 兼容性：`SIDECAR_READY` 同时清除 boot 与 ready 计时（旧后端无 boot 标记也能工作）。

3. **Splash 文案**
   - 超时错误信息提及首次启动/杀毒扫描场景，引导 Retry。

## Acceptance Criteria

- [ ] `python -m xreadagent.api --port 0` 先打印 `SIDECAR_BOOT` 再打印 `SIDECAR_READY port=<N>`（flush 即时）
- [ ] `import xreadagent.api` 不再把 `fastapi`/`uvicorn`/`xreadagent.api.main` 拉进 sys.modules（test_lazy_imports 扩展）
- [ ] `from xreadagent.api import create_app` 仍然可用（PEP 562）
- [ ] sidecar.ts：无任何输出 45s → 报错；有输出后 240s 内等 ready；进程退出立即失败
- [ ] backend 测试（test_api.py 契约 + test_lazy_imports.py）通过：`uv run pytest backend/tests/test_api.py backend/tests/test_lazy_imports.py`
- [ ] electron 测试通过：`cd electron && pnpm test`
- [ ] electron type-check/build 通过

## Out of Scope

- 预热/预编译 bytecode、安装器白名单 Defender（另行评估）
- macOS 构建
- 发布 v0.0.9（独立 release 任务）

## Technical Notes

- 实测数据：冷启动 >120s 无输出（NVMe + 现代 CPU 的开发机）；低端 HDD 机器可能更久，故 ready 预算取 240s。
- boot 标记只依赖 stdlib（argparse/socket/sys），冷扫描下也应远快于 45s。
- `PYTHONUNBUFFERED=1` 已由 `buildSidecarEnv` 注入，boot/ready 标记另加显式 flush。
- spec 契约文档 `.trellis/spec/electron/index.md` 的 Sidecar Lifecycle Contract 需同步更新（boot 标记 + 分级超时）。
