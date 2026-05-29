# MCP 协议集成

## Goal

将 XReadAgent 的核心能力（ingest、query、translate、wiki 浏览）通过 MCP 协议暴露给外部 AI 工具（Claude Desktop、Cursor 等），使 XReadAgent 成为 AI 生态中的知识源和工具服务器。

## What I already know

* **MCP SDK v1.27.1** — Python SDK，零依赖冲突，可直接添加到 pyproject.toml
* **可挂载到现有 FastAPI** — `app.mount("/mcp", mcp_server.streamable_http_app())`
* **agents/ 层规则** — MCP tools 必须调用 wiki/ 原语，不能直接调用 agents/tools.py 中的 LangChain 工具
* **elicit 安全机制** — 昂贵操作（ingest、translate）需人类确认
* **翻译进度** — MCP tool 调用返回单结果，WS 流不适合直接映射，需设计替代方案

## Research References

* [`research/mcp-protocol.md`](../05-29-phase-4-sqlite-vec-mcp-macos/research/mcp-protocol.md) — MCP 协议详细调研

## Decisions

- **D1. 传输方式**：HTTP 挂载到现有 FastAPI + stdio for Claude Desktop
- **D2. 安全**：昂贵操作使用 elicit 确认，只读操作直接执行
- **D3. 模块位置**：`backend/src/xreadagent/mcp/` 独立模块

## Requirements

### R-MCP-SERVER: MCP 服务器

- `xreadagent.mcp` 模块：FastMCP 服务器实例
- 挂载到 FastAPI：`app.mount("/mcp", mcp.streamable_http_app())`
- stdio 传输：用于 Claude Desktop 本地集成

### R-MCP-TOOLS: MCP 工具

| Tool | 描述 | 安全级别 |
|------|------|---------|
| `ingest_paper` | 导入论文到 wiki | elicit（昂贵+不可逆） |
| `query_wiki` | 语义搜索 wiki | 直接执行 |
| `translate_paper` | 翻译 PDF | elicit（昂贵+耗时） |
| `get_paper_summary` | 获取论文摘要 | 直接执行 |
| `list_papers` | 列出工作区论文 | 直接执行 |
| `browse_wiki` | 浏览 wiki 页面内容 | 直接执行 |

### R-MCP-RESOURCES: MCP 资源

- `xread://papers` — 论文列表资源
- `xread://paper/{slug}` — 单篇论文资源
- `xread://wiki/{path}` — wiki 页面内容

### R-MCP-CONFIG: 配置

- Claude Desktop 配置示例：`claude_desktop_config.json`
- Cursor 配置示例
- 环境变量控制 MCP 启用/禁用

## Acceptance Criteria

- [ ] Claude Desktop 可通过 MCP 调用 XReadAgent 工具
- [ ] ingest/translate 需人类确认
- [ ] 只读工具可自由调用
- [ ] MCP 服务器可与 FastAPI 共存

## Out of Scope

- MCP Prompts（模板）功能
- MCP Sampling（让服务端请求 LLM）
- 翻译进度的实时推送（使用轮询替代）

## Technical Notes

- MCP tools 调用 wiki/ 原语，不调用 agents/ 层
- elicit 通过 Context 对象实现
- HTTP 传输与 FastAPI 共享端口