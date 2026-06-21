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

## HTTP transport (remote URL)

`rag-mcp` defaults to stdio (local, private). To expose it as a URL any MCP client can
call, switch to the `streamable-http` transport. **A bearer token is required** — the HTTP
endpoint exposes your corpus, so the server refuses to start without `RAG_MCP_TOKEN`:

```bash
export RAG_MCP_TOKEN="$(openssl rand -hex 32)"      # any strong secret
rag-mcp -c config.yaml --transport streamable-http --host 127.0.0.1 --port 8000
# serves at  http://127.0.0.1:8000/mcp
```

- Keep `--host 127.0.0.1` and reach it through a tunnel/reverse proxy (below). Only bind
  `--host 0.0.0.0` when something authenticated sits in front of the port.
- **Read-only by default:** over HTTP, only the read tools (`rag_query`, `rag_status`,
  `rag_dlq_list`) are exposed. Set `RAG_MCP_ALLOW_SYNC=1` to additionally expose the
  `rag_sync` write tool.

Clients send the token as a header:

```json
"super-rag": {
  "url": "https://<your-host>/mcp",
  "headers": { "Authorization": "Bearer <RAG_MCP_TOKEN>" }
}
```

### Get a public URL with a tunnel

The cheapest path keeps generation (Ollama + Claude CLI) on your machine and just forwards
requests in — your corpus never leaves disk, so `private:` stays truly local.

```bash
# instant, ephemeral, no account ($0):
cloudflared tunnel --url http://localhost:8000      # -> https://<rand>.trycloudflare.com/mcp

# stable low-cost alternatives:
ngrok http 8000                                     # free static domain + your Bearer token
# or a cloudflared *named* tunnel if you own a domain
```

The Bearer token protects the URL even while the tunnel is public.

## Docker (optional, for a remote host)

```bash
docker build -t super-rag-mcp .
docker run --rm -p 8000:8000 \
  -e RAG_MCP_TOKEN="$RAG_MCP_TOKEN" \
  -e COMPOSIO_API_KEY="$COMPOSIO_API_KEY" \
  -v /host/rag-data:/data \
  super-rag-mcp
```

The image reads `config.yaml` from `/data` (`RAG_CONFIG=/data/config.yaml`); mount your
`bundle_dir` there too. Secrets are passed at runtime (`-e`), never baked into the image.

> **Heads-up:** the current image installs only `.[mcp,cloud]` — it has no Ollama and no
> authenticated Claude CLI, so `rag_query`/`rag_sync` need a generation backend provided to
> the container (a co-located/remote Ollama, or a future API backend). For a fully private,
> always-on URL at ~$0, prefer the **local server + tunnel** above.

> **Privacy:** any remote *container* deployment moves the index and embeddings off your
> machine, which voids the `private:`-stays-local guarantee. The tunnel approach does not.

## Cloud dev environment (Ona / Gitpod)

`.gitpod.yml` provisions a reproducible workspace (uv install of `.[dev,mcp,cloud]`,
Tesseract/Poppler, Ollama with the embedding + generation models). `.devcontainer/devcontainer.json`
gives the equivalent for Codespaces/Ona devcontainer mode. Copy `config.example.yaml`
to `config.yaml`, then run `rag-mcp -c config.yaml`.
