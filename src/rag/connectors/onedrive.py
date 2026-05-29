"""OneDrive connector (Composio transport, Microsoft Graph item shapes).

list_changes  -> ONE_DRIVE_ONEDRIVE_LIST_ITEMS (paginated) -> CloudItem -> diff_items
fetch_content -> ONE_DRIVE_DOWNLOAD_FILE -> RawDoc
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

_LIST_ACTION = "ONE_DRIVE_ONEDRIVE_LIST_ITEMS"
_DOWNLOAD_ACTION = "ONE_DRIVE_DOWNLOAD_FILE"


def _parse_graph_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class OneDriveConnector:
    name = "onedrive"

    def __init__(
        self,
        client: ComposioClient,
        connected_accounts: dict[str, str],
        state_dir,
        mime_filter: list[str] | None = None,
    ) -> None:
        self.client = client
        self.connected_accounts = connected_accounts
        self.manifest = ManifestStore(state_dir)
        self.mime_filter = mime_filter

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ca = resolve_connected_account(self.connected_accounts, account)
        items = self._list_items(ca)
        yield from diff_items(self.name, account, items, since, self.manifest)

    def _list_items(self, connected_account_id: str) -> list[CloudItem]:
        items: list[CloudItem] = []
        skip_token: str | None = None
        while True:
            params: dict = {}
            if skip_token:
                params["skip_token"] = skip_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for it in data.get("value", []):
                if "file" not in it:  # folders / non-file items
                    continue
                mime = it.get("file", {}).get("mimeType")
                if self.mime_filter and mime not in self.mime_filter:
                    continue
                size = it.get("size")
                items.append(
                    CloudItem(
                        doc_id=it["id"],
                        source_url=it.get("webUrl", ""),
                        last_modified=_parse_graph_time(it.get("lastModifiedDateTime")),
                        size_bytes=int(size) if size is not None else None,
                        mime=mime,
                        filename=it.get("name", ""),
                    )
                )
            skip_token = data.get("@odata.nextLink")
            if not skip_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        data = self.client.execute(
            _DOWNLOAD_ACTION, {"item_id": doc_id}, connected_account_id=ca
        )
        content = base64.b64decode(data["content_b64"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webUrl", ""),
            mime=data.get("file", {}).get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
