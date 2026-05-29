# sqlite-vec 语义搜索

## Goal

为 XReadAgent 的 wiki 添加语义向量检索能力，让 query agent 从关键词导航升级为语义搜索，显著提升跨论文关联发现和问题回答质量。

## What I already know

* **sqlite-vec v0.1.9** — 轻量 SQLite 向量扩展，~292KB wheel，vec0 虚拟表，KNN 查询需 `k=?` 参数
* **FTS5 + vec0 混合检索** — BM25 全文 + 向量 KNN + RRF 融合，已验证可用
* **嵌入模型** — `all-MiniLM-L6-v2`（384d, ONNX, ~50ms/query）为推荐默认；`specter2_base`（768d）为学术域增强
* **torch 依赖问题** — sentence-transformers 传递依赖 torch，需用 optimum 直接加载 ONNX 避免引入 torch
* **wiki 结构** — 页面级嵌入，在 ingest 时生成，`vec.sqlite` 存放在 `{workspace}/state/vec.sqlite`
* **可重建缓存** — vec.sqlite 可从 wiki 页面完全重建，不需要持久化到 git
* **现有约束** — backend spec 硬规则："No vector tier in v1" — Phase 4 才引入

## Research References

* [`research/sqlite-vec.md`](../05-29-phase-4-sqlite-vec-mcp-macos/research/sqlite-vec.md) — sqlite-vec 详细调研

## Decisions

- **D1. 向量存储**：sqlite-vec + vec0 虚拟表，存储在 `{workspace}/state/vec.sqlite`
- **D2. 嵌入模型**：`all-MiniLM-L6-v2` ONNX 为默认，通过 optimum 加载（不引入 torch）
- **D3. 嵌入粒度**：页面级嵌入（每个 wiki .md 文件一个向量），段落级留到后续
- **D4. 嵌入时机**：ingest 时嵌入（在 `apply_plan` 写入 wiki 后）
- **D5. 检索方式**：FTS5 + vec0 混合检索 + RRF 融合

## Requirements

### R-VEC-STORE: 向量存储层

- `wiki/vector.py` 模块：管理 vec.sqlite 生命周期
- vec0 虚拟表：`CREATE VIRTUAL TABLE vec_pages USING vec0(page_slug text primary key, embedding float[384])`
- 插入/删除/查询接口
- 向量存储与 wiki 页面同步：新增页面 → 嵌入 → 插入；删除页面 → 删除向量

### R-EMBED: 嵌入引擎

- 使用 `optimum.onnxruntime` 加载 ONNX 嵌入模型
- 默认模型：`all-MiniLM-L6-v2`（384 维）
- 首次运行时下载模型到 `~/.xreadagent/models/embeddings/`
- 嵌入查询：~50ms/query，批量嵌入页面：~100 pages/s

### R-SEARCH: 语义搜索

- FTS5 全文索引 + vec0 向量 KNN + RRF 融合
- `semantic_search(query, workspace, top_k=10)` → 返回排序后的 wiki 页面列表
- query agent 的 `semantic_search` 工具替代当前的 `index.md` 导航
- 结果包含：page_slug, title, score, snippet

### R-INGEST-EMBED: Ingest 时嵌入

- 在 `apply_plan` 写入 wiki 后，自动嵌入新增/修改的页面
- 嵌入失败不应阻塞 ingest 流程（降级到无向量搜索）

### R-REBUILD: 向量索引重建

- `xreadagent reindex <workspace>` CLI 命令：扫描所有 wiki 页面，重建 vec.sqlite
- 前端 API：`POST /api/reindex` 触发重建
- 重建进度通过 WS 推送

## Acceptance Criteria

- [ ] `semantic_search` 返回相关 wiki 页面，质量优于纯关键词搜索
- [ ] ingest 后自动嵌入新页面，不影响 ingest 性能
- [ ] FTS5 + vec0 混合检索 + RRF 融合正常工作
- [ ] `xreadagent reindex` CLI 命令可重建索引
- [ ] 不引入 torch 运行时依赖

## Out of Scope

- 段落级嵌入（后续迭代）
- 嵌入模型选择 UI（使用默认模型）
- 向量索引版本迁移（v1 不需要）
- macOS arm64 ONNX 模型适配（Phase 4 后续）

## Technical Notes

- sqlite-vec KNN 查询必须使用 `k = ?` 参数，不能用裸 `LIMIT`
- sentence-transformers 传递依赖 torch，必须用 optimum 直接加载 ONNX
- vec.sqlite 存放在 state/ 目录，可重建，不需要 git 跟踪
- query archive 页面不应嵌入（隔离的 Q&A，非研究知识）