"""`rag` command — query, sync, status, dlq list/replay."""
from __future__ import annotations

import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from rag.config import (
    Config,
    GdriveSource,
    GmailSource,
    LocalfsSource,
    OneDriveSource,
    OutlookSource,
    load_config,
)
from rag.connectors.localfs import LocalfsConnector
from rag.dlq import DeadLetterQueue
from rag.embedder import OllamaEmbedder
from rag.index import VectorIndex
from rag.llm import ClaudeCLIBackend, OllamaBackend
from rag.metadata import MetadataStore
from rag.query import QueryEngine
from rag.sync import SyncOrchestrator

console = Console()

_INDEX_DIM = 384  # bge-small-en-v1.5

# Cloud source kind -> (connector class, extra-kwarg builder from the source model).
_CLOUD_KINDS = {
    GdriveSource: ("gdrive", "GdriveConnector",
                   lambda s: {"include_paths": s.include_paths, "mime_filter": s.mime_filter}),
    OneDriveSource: ("onedrive", "OneDriveConnector",
                     lambda s: {"mime_filter": s.mime_filter}),
    GmailSource: ("gmail", "GmailConnector",
                  lambda s: {"mime_filter": s.mime_filter}),
    OutlookSource: ("outlook", "OutlookConnector",
                    lambda s: {"mime_filter": s.mime_filter}),
}


def _build(cfg_path: Path):
    cfg = load_config(cfg_path)
    meta = MetadataStore(cfg.paths.metadata)
    dlq = DeadLetterQueue(cfg.paths.dlq)
    index_path = cfg.paths.bundle_dir / "index.tq"
    index = VectorIndex.load(dim=_INDEX_DIM, path=index_path)
    embedder = OllamaEmbedder(model=cfg.embedding.model,
                              base_url=cfg.embedding.ollama_url,
                              batch_size=cfg.embedding.batch_size)
    return cfg, meta, dlq, index, embedder


def _composio_client(cfg: Config):
    """Build the real Composio transport (lazy import — `composio` is an optional dep)."""
    if cfg.composio is None:
        raise click.ClickException(
            "cloud sources are configured but config has no `composio:` block"
        )
    key = os.environ.get(cfg.composio.api_key_env)
    if not key:
        raise click.ClickException(
            f"environment variable {cfg.composio.api_key_env} is not set "
            "(install the cloud extra with `uv pip install -e \".[cloud]\"` and export the key)"
        )
    try:
        from rag.connectors.composio_client import ComposioSDKClient
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise click.ClickException(
            "the `composio` package is not installed; run `uv pip install -e \".[cloud]\"`"
        ) from e
    return ComposioSDKClient(api_key=key)


def _build_connectors(cfg: Config):
    """Instantiate every configured connector and its account list.

    Returns ``(connectors, accounts_per_connector)`` keyed by source name. The Composio
    client is built once and shared, only when at least one cloud source is present.
    """
    connectors: dict = {}
    accounts: dict[str, list[str]] = {}
    client = None
    state_dir = cfg.paths.bundle_dir / "manifests"
    for s in cfg.sources:
        if isinstance(s, LocalfsSource):
            connectors["localfs"] = LocalfsConnector(roots=s.paths)
            accounts.setdefault("localfs", []).append("default")
            continue
        spec = _CLOUD_KINDS.get(type(s))
        if spec is None:
            raise click.ClickException(f"unsupported source kind: {type(s).__name__}")
        name, cls_name, kwargs_fn = spec
        if name not in connectors:
            if client is None:
                client = _composio_client(cfg)
            import importlib
            mod = importlib.import_module(f"rag.connectors.{name}")
            conn_cls = getattr(mod, cls_name)
            connectors[name] = conn_cls(
                client=client,
                connected_accounts=cfg.composio.connected_accounts,
                state_dir=state_dir,
                **kwargs_fn(s),
            )
        accounts.setdefault(name, []).extend(s.accounts)
    return connectors, accounts


@click.group()
def main() -> None:
    """Super RAG CLI."""


@main.command()
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def sync(config: str) -> None:
    """Run a sync pass: pull deltas, parse, embed, index."""
    cfg, meta, dlq, index, embedder = _build(Path(config))
    connectors, accounts = _build_connectors(cfg)
    orch = SyncOrchestrator(
        connectors=connectors, accounts_per_connector=accounts,
        embedder=embedder, index=index, metadata=meta, dlq=dlq,
        chunk_size=cfg.chunking.fallback_size, overlap=cfg.chunking.overlap,
        ocr_strategy=cfg.ocr.strategy if cfg.ocr.enabled else "never",
    )
    result = orch.run()
    index.save()
    console.print(f"[green]Sync complete[/]: processed={result.docs_processed} "
                  f"failed={result.docs_failed} chunks={result.chunks_indexed}")


@main.command()
@click.argument("question", nargs=-1, required=True)
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
@click.option("-k", "--top-k", default=5, type=int)
def query(question: tuple[str, ...], config: str, top_k: int) -> None:
    """Ask a question. Prefix with 'private:' to keep generation local."""
    q = " ".join(question)
    cfg, meta, _dlq, index, embedder = _build(Path(config))
    claude = ClaudeCLIBackend()
    ollama = OllamaBackend(model=cfg.llm.ollama_model, base_url=cfg.embedding.ollama_url)
    qe = QueryEngine(
        embedder=embedder, index=index, metadata=meta,
        claude=claude, ollama=ollama, top_k=top_k,
        private_prefix=cfg.llm.private_prefix,
        default_backend=cfg.llm.default,
        private_routes_to=cfg.llm.private_tag_routes_to,
    )
    ans = qe.ask(q)
    console.rule("[bold]Answer")
    console.print(ans.text)
    console.rule("[bold]Citations")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Page")
    table.add_column("Score")
    table.add_column("Excerpt", overflow="fold")
    for c in ans.citations:
        table.add_row(c.source_url, str(c.page or ""), f"{c.score:.3f}", c.excerpt)
    console.print(table)
    if ans.private:
        console.print("[yellow]Generated locally (private mode)[/]")


@main.command()
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def status(config: str) -> None:
    """Show last run + DLQ counts."""
    _cfg, meta, dlq, _, _ = _build(Path(config))
    runs = meta.list_runs()
    console.print(f"Total runs: {len(runs)}")
    if runs:
        last = runs[0]
        console.print(f"Last: {last['started_at']} → {last['finished_at']} "
                      f"[{last['status']}] docs={last['docs_processed']} chunks={last['chunks_indexed']}")
    dlq_count = sum(1 for _ in dlq.iter_entries())
    console.print(f"DLQ entries: {dlq_count}")


@main.group("dlq")
def dlq_group() -> None:
    """Dead-letter queue inspection and replay."""


@dlq_group.command("list")
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def dlq_list(config: str) -> None:
    _cfg, _meta, dlq, _idx, _emb = _build(Path(config))
    for e in dlq.iter_entries():
        console.print(json.dumps(e, indent=2))


@dlq_group.command("replay")
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def dlq_replay(config: str) -> None:
    """Re-attempt every document currently in the DLQ (append-only log is not pruned)."""
    cfg, meta, dlq, index, embedder = _build(Path(config))
    connectors, accounts = _build_connectors(cfg)
    orch = SyncOrchestrator(
        connectors=connectors, accounts_per_connector=accounts,
        embedder=embedder, index=index, metadata=meta, dlq=dlq,
        chunk_size=cfg.chunking.fallback_size, overlap=cfg.chunking.overlap,
        ocr_strategy=cfg.ocr.strategy if cfg.ocr.enabled else "never",
    )
    ok = failed = 0
    for e in list(dlq.iter_entries()):
        try:
            orch.replay_doc(e["source"], e["account"], e["doc_id"])
            ok += 1
        except Exception as ex:
            failed += 1
            console.print(f"[red]replay failed[/] {e.get('source')}/{e.get('doc_id')}: {ex}")
    index.save()
    console.print(f"[green]Replay complete[/]: reprocessed={ok} still_failing={failed}")


if __name__ == "__main__":
    main()
