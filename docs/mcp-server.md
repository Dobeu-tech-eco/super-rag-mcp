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

## HTTP transport & Docker (optional)

`rag-mcp` defaults to stdio (local, private). For remote hosting, switch transport:

```bash
rag-mcp -c config.yaml --transport streamable-http --host 0.0.0.0 --port 8000
```

Or run it in a container (installs the `[mcp,cloud]` extras):

```bash
docker build -t super-rag-mcp .
docker run --rm -p 8000:8000 \
  -e COMPOSIO_API_KEY="$COMPOSIO_API_KEY" \
  -v /host/rag-data:/data \
  super-rag-mcp
```

The image reads `config.yaml` from `/data` (`RAG_CONFIG=/data/config.yaml`); mount
your `bundle_dir` there too. `COMPOSIO_API_KEY` is passed at runtime (`-e`) and is
never baked into the image.

> **Privacy:** HTTP transport moves the index and embeddings off the local machine.
> Keep stdio for fully local setups; only enable HTTP when you intend to serve remotely.

## Cloud dev environment (Ona / Gitpod)

`.gitpod.yml` provisions a reproducible workspace (uv install of `.[dev,mcp,cloud]`,
Tesseract/Poppler, Ollama with the embedding + generation models). `.devcontainer/devcontainer.json`
gives the equivalent for Codespaces/Ona devcontainer mode. Copy `config.example.yaml`
to `config.yaml`, then run `rag-mcp -c config.yaml`.
