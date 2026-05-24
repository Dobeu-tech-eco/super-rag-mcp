"""`rag` command — query, sync, status, dlq replay."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rag.config import load_config, LocalfsSource
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


@click.group()
def main() -> None:
    """Super RAG CLI."""


@main.command()
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def sync(config: str) -> None:
    """Run a sync pass: pull deltas, parse, embed, index."""
    cfg, meta, dlq, index, embedder = _build(Path(config))
    connectors: dict = {}
    accounts: dict[str, list[str]] = {}
    for s in cfg.sources:
        if isinstance(s, LocalfsSource):
            connectors["localfs"] = LocalfsConnector(roots=s.paths)
            accounts["localfs"] = ["default"]
        # Other source kinds are added in Plan 2.
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
    cfg, meta, dlq, index, embedder = _build(Path(config))
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
    table.add_column("Source"); table.add_column("Page"); table.add_column("Score")
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
    cfg, meta, dlq, _, _ = _build(Path(config))
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


if __name__ == "__main__":
    main()
