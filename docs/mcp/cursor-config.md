# XReadAgent MCP Configuration for Cursor

Add the following to your project's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "python",
      "args": ["-m", "xreadagent.mcp"],
      "env": {
        "XREAD_AGENT_WORKSPACE": "/path/to/XReadAgent-Workspace"
      }
    }
  }
}
```

Or use the `xreadagent` CLI directly:

```json
{
  "mcpServers": {
    "xreadagent": {
      "command": "xreadagent",
      "args": ["mcp"],
      "env": {
        "XREAD_AGENT_WORKSPACE": "/path/to/XReadAgent-Workspace"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `ingest_paper` | Ingest a scientific paper into the workspace wiki (requires confirmation) |
| `query_wiki` | Ask a question against the knowledge base |
| `translate_paper` | Translate a PDF with layout preservation (requires confirmation) |
| `check_translation_status` | Check the status of a translation job |
| `get_paper_summary` | Get a paper summary by slug |
| `list_papers` | List all ingested papers |
| `list_concepts` | List all concepts |
| `browse_wiki` | Read a wiki page by path |
| `semantic_search` | Search wiki pages using hybrid vector + FTS5 |

## Available Resources

| Resource URI | Description |
|-------------|-------------|
| `xread://papers` | Paper index |
| `xread://paper/{slug}` | Single paper page content |
| `xread://wiki/{path}` | Any wiki page by relative path |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `XREAD_AGENT_WORKSPACE` | Default workspace path (required if not passed per-tool) |
| `XREAD_AGENT_MODEL` | Default LLM model (e.g. `anthropic:claude-sonnet-4-6`) |