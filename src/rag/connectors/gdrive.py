"""Google Drive connector (Composio transport).

list_changes  -> GOOGLEDRIVE_FIND_FILE (paginated) -> CloudItem -> diff_items
fetch_content -> GOOGLEDRIVE_DOWNLOAD_FILE -> RawDoc
"""
from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import datetime

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_ACTION = "GOOGLEDRIVE_FIND_FILE"
_DOWNLOAD_ACTION = "GOOGLEDRIVE_DOWNLOAD_FILE"


def _parse_drive_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class GdriveConnector:
    name = "gdrive"

    def __init__(
        self,
        client: ComposioClient,
        connected_accounts: dict[str, str],
        state_dir,
        include_paths: list[str] | None = None,
        mime_filter: list[str] | None = None,
    ) -> None:
        self.client = client
        self.connected_accounts = connected_accounts
        self.manifest = ManifestStore(state_dir)
        self.include_paths = include_paths or ["/"]
        self.mime_filter = mime_filter

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ca = resolve_connected_account(self.connected_accounts, account)
        items = self._list_items(ca)
        yield from diff_items(self.name, account, items, since, self.manifest)

    def _list_items(self, connected_account_id: str) -> list[CloudItem]:
        items: list[CloudItem] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for f in data.get("files", []):
                mime = f.get("mimeType")
                if self.mime_filter and mime not in self.mime_filter:
                    continue
                size = f.get("size")
                items.append(
                    CloudItem(
                        doc_id=f["id"],
                        source_url=f.get("webViewLink", ""),
                        last_modified=_parse_drive_time(f.get("modifiedTime")),
                        size_bytes=int(size) if size is not None else None,
                        mime=mime,
                        filename=f.get("name", ""),
                    )
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        data = self.client.execute(
            _DOWNLOAD_ACTION, {"file_id": doc_id}, connected_account_id=ca
        )
        content = base64.b64decode(data["content_b64"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webViewLink", ""),
            mime=data.get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
