"""OneDrive connector (Composio transport, Microsoft Graph item shapes).

list_changes  -> ONE_DRIVE_LIST_FOLDER_CHILDREN (recursive walk) -> CloudItem -> diff_items
fetch_content -> ONE_DRIVE_DOWNLOAD_FILE -> content.s3url -> RawDoc

Listing walks the connected account's own drive (``use_me_drive=True``) starting at root
and recursing into subfolders; each page returns ``value[]`` DriveItems with an
``@odata.nextLink`` for continuation. Download takes ``item_id`` + ``file_name`` and
returns a presigned ``content.s3url`` (NOT inline base64).
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_bytes,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_ACTION = "ONE_DRIVE_LIST_FOLDER_CHILDREN"
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
        """Recursively walk the drive from root, collecting file DriveItems."""
        items: list[CloudItem] = []
        # Queue of folders to descend into; None sentinel means the drive root.
        pending: list[str | None] = [None]
        seen_folders: set[str] = set()
        while pending:
            folder_id = pending.pop()
            for it in self._list_folder(connected_account_id, folder_id):
                if "folder" in it:  # descend into subfolders
                    fid = it.get("id")
                    if fid and fid not in seen_folders:
                        seen_folders.add(fid)
                        pending.append(fid)
                    continue
                if "file" not in it:  # skip packages / other non-file items
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
        return items

    def _list_folder(
        self, connected_account_id: str, folder_id: str | None
    ) -> Iterator[dict]:
        """Yield all child DriveItems of one folder, following pagination."""
        next_link: str | None = None
        while True:
            params: dict = {"use_me_drive": True, "top": 200}
            if folder_id is None:
                params["folder_path"] = "/"
            else:
                params["folder_item_id"] = folder_id
            if next_link:
                params["next_link"] = next_link
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            yield from data.get("value", [])
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        data = self.client.execute(
            _DOWNLOAD_ACTION,
            {"item_id": doc_id, "file_name": doc_id},
            connected_account_id=ca,
        )
        content = resolve_bytes(data, "content.s3url", b64_path="content_b64")
        content_meta = data.get("content", {}) if isinstance(data.get("content"), dict) else {}
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webUrl", ""),
            mime=content_meta.get("mimetype")
            or data.get("file", {}).get("mimeType", "application/octet-stream"),
            content=content,
            filename=content_meta.get("name") or data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
