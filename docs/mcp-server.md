# RAG MCP server

Exposes the Super-RAG pipeline as MCP tools so Hermes, Cursor, and other MCP
clients can query and sync the index. Pairs with the generic Composio bridge
(`one-composio-mcp`) as a second server in the same client config.

## Install & run

```bash
uv pip install -e ".[dev,mcp]"
rag-mcp -c config.yaml          # serves over stdio
# or: RAG_CONFIG=/path/config.yaml rag-mcp
```

## Tools

| Tool | Annotations | Args | Returns |
|------|-------------|------|---------|
| `rag_query` | read-only, idempotent | `question: str`, `top_k: int=5` | `{answer, private, citations[]}` |
| `rag_sync` | write, non-idempotent | `full: bool=False` | `{docs_processed, docs_failed, chunks_indexed}` |
| `rag_status` | read-only, idempotent | — | `{total_runs, last_run, dlq_entries}` |
| `rag_dlq_list` | read-only, idempotent | `limit: int=50` | list of dead-letter entries |

- Prefix a question with the configured private prefix (default `private:`) to
  force local-only generation via Ollama — queries stay off the cloud.
- `rag_sync` only needs `COMPOSIO_API_KEY` (and a `composio:` config block) when
  cloud sources are configured; local-only setups don't.
- Failures surface an actionable hint (Ollama down, missing config, missing key).

## Wiring with the generic Composio bridge

`examples/hermes-mcp.json.example` registers **two** servers:

- `super-rag` — this stdio server (local, private).
- `composio-unified` — the HTTP block emitted by
  `one-composio-mcp mcp-emit` (paste its `mcpServers` entry beside `super-rag`).

Merge that JSON into your MCP client config (e.g. `~/.cursor/mcp.json`).

## Remote hosting (optional)

See the implementation plan's Phase 2 for an HTTP transport + Dockerfile and an
Ona/Gitpod multi-repo dev environment. Note: remote hosting moves the index and
embeddings off the local machine, changing the privacy posture.
