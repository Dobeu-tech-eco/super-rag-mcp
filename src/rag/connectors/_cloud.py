"""Shared helpers for Composio-backed cloud connectors.

- resolve_connected_account: alias -> Composio connected-account id (auth error if absent)
- ManifestStore: per-(source, account) JSON snapshot for delete detection
- diff_items: turn a current item set into upsert/delete ChangeEvents (mirrors localfs)
"""
from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from rag.connectors import ConnectorAuthError, ConnectorError
from rag.types import ChangeEvent


@dataclass
class CloudItem:
    """One listed object from a cloud source (pre-fetch)."""

    doc_id: str
    source_url: str
    last_modified: datetime
    size_bytes: int | None = None
    mime: str | None = None
    filename: str = ""


def resolve_connected_account(connected_accounts: dict[str, str], account: str) -> str:
    ca = connected_accounts.get(account)
    if not ca:
        raise ConnectorAuthError(
            f"no Composio connected account configured for alias {account!r}"
        )
    return ca


def dig(data: Any, dotted: str) -> Any:
    """Return ``data[a][b][c]`` for ``dotted='a.b.c'``, or None if any hop is absent."""
    cur = data
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def download_bytes(url: str, *, timeout: float = 60.0) -> bytes:
    """Fetch the raw bytes behind a (short-lived) Composio ``s3url`` download locator.

    Composio's file/attachment download actions do NOT return inline content — they
    return a temporary presigned URL that must be fetched promptly. Callers should
    invoke this immediately after the download action while the URL is still valid.
    """
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ConnectorError(f"download from locator URL failed: {e}") from e
    return resp.content


def resolve_bytes(
    data: dict[str, Any],
    s3url_path: str,
    *,
    b64_path: str | None = None,
    urlsafe_b64: bool = False,
) -> bytes:
    """Resolve a download action's normalized payload to raw bytes.

    Prefers the presigned ``s3url`` locator at ``s3url_path`` (the live-API path).
    Falls back to an inline base64 field at ``b64_path`` when present (defensive —
    some actions occasionally inline small payloads). Raises if neither is found.
    """
    url = dig(data, s3url_path)
    if isinstance(url, str) and url:
        return download_bytes(url)
    if b64_path:
        raw = dig(data, b64_path)
        if isinstance(raw, str) and raw:
            padded = raw + "=" * (-len(raw) % 4)
            decoder = base64.urlsafe_b64decode if urlsafe_b64 else base64.b64decode
            return decoder(padded)
    raise ConnectorError(
        f"download response had no content (no {s3url_path!r}"
        + (f" or {b64_path!r}" if b64_path else "")
        + ")"
    )


class ManifestStore:
    """Persists the last-seen item set per (source, account) so deletes are observable."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, source: str, account: str) -> Path:
        safe = account.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.state_dir / f"{source}-{safe}-manifest.json"

    def load(self, source: str, account: str) -> dict[str, dict]:
        p = self._path(source, account)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def save(self, source: str, account: str, current: dict[str, dict]) -> None:
        self._path(source, account).write_text(
            json.dumps(current, indent=2), encoding="utf-8"
        )


def diff_items(
    source: str,
    account: str,
    items: list[CloudItem],
    since: datetime | None,
    manifest_store: ManifestStore,
) -> Iterator[ChangeEvent]:
    """Yield upsert events for new/modified items and delete events for vanished ones.

    Upserts are filtered by ``since`` (items modified at or before ``since`` are skipped,
    matching the localfs connector). Deletes come from comparing against the prior manifest.
    The manifest is rewritten to the current set at the end.
    """
    previous = manifest_store.load(source, account)
    current: dict[str, dict] = {}

    for it in items:
        current[it.doc_id] = {
            "mtime": it.last_modified.isoformat(),
            "size": it.size_bytes,
        }
        if since and it.last_modified <= since:
            continue
        yield ChangeEvent(
            source=source,
            account=account,
            doc_id=it.doc_id,
            operation="upsert",
            source_url=it.source_url,
            last_modified=it.last_modified,
            size_bytes=it.size_bytes,
            mime=it.mime,
        )

    for prev_id in previous:
        if prev_id not in current:
            yield ChangeEvent(
                source=source,
                account=account,
                doc_id=prev_id,
                operation="delete",
                source_url="",
                last_modified=datetime.utcnow(),
            )

    manifest_store.save(source, account, current)
