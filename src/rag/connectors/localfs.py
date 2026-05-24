"""Local filesystem connector. Walks configured roots, emits ChangeEvents.

Maintains a tiny per-root manifest file (`.rag-localfs-manifest.json`) inside
each root so deletes become observable across runs.
"""
from __future__ import annotations
import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Iterator
from rag.types import ChangeEvent, RawDoc

_MANIFEST_NAME = ".rag-localfs-manifest.json"
_SUPPORTED_EXTS = {".pdf", ".txt", ".md", ".docx"}


class LocalfsConnector:
    name = "localfs"

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(r) for r in roots]

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        for root in self.roots:
            yield from self._scan_root(root, account, since)

    def _scan_root(self, root: Path, account: str,
                   since: datetime | None) -> Iterator[ChangeEvent]:
        if not root.exists():
            return
        manifest_path = root / _MANIFEST_NAME
        previous: dict[str, dict] = {}
        if manifest_path.exists():
            previous = json.loads(manifest_path.read_text())
        current: dict[str, dict] = {}

        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if path.name == _MANIFEST_NAME:
                continue
            if path.suffix.lower() not in _SUPPORTED_EXTS:
                continue

            stat = path.stat()
            mtime = datetime.utcfromtimestamp(stat.st_mtime)
            doc_id = str(path)
            current[doc_id] = {"mtime": mtime.isoformat(), "size": stat.st_size}

            if since and mtime <= since:
                continue

            mime, _ = mimetypes.guess_type(path.name)
            if mime is None:
                mime = "application/octet-stream"

            yield ChangeEvent(
                source=self.name,
                account=account,
                doc_id=doc_id,
                operation="upsert",
                source_url=path.as_uri(),
                last_modified=mtime,
                size_bytes=stat.st_size,
                mime=mime,
            )

        # Emit deletes for anything seen before but not now.
        for prev_id in previous:
            if prev_id not in current:
                yield ChangeEvent(
                    source=self.name,
                    account=account,
                    doc_id=prev_id,
                    operation="delete",
                    source_url=Path(prev_id).as_uri() if prev_id else "",
                    last_modified=datetime.utcnow(),
                )

        manifest_path.write_text(json.dumps(current, indent=2))

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        path = Path(doc_id)
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        if mime is None:
            mime = "application/octet-stream"
        stat = path.stat()
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=path.as_uri(),
            mime=mime,
            content=content,
            filename=path.name,
            last_modified=datetime.utcfromtimestamp(stat.st_mtime),
        )
