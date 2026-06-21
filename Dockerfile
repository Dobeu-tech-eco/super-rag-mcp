# Dockerfile — remote RAG MCP server (HTTP transport).
#
# Privacy note: this serves the index over the network. The vector index and
# embeddings live in the image/volume — mount config.yaml and the bundle_dir at
# runtime so your data stays on a volume you control, e.g.:
#
#   docker build -t super-rag-mcp .
#   docker run --rm -p 8000:8000 \
#     -e COMPOSIO_API_KEY=$COMPOSIO_API_KEY \
#     -v /host/rag-data:/data \
#     super-rag-mcp
#
# COMPOSIO_API_KEY is passed at runtime (-e) and is never baked into the image.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system -e ".[mcp,cloud]"
EXPOSE 8000
ENV RAG_CONFIG=/data/config.yaml
CMD ["rag-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
