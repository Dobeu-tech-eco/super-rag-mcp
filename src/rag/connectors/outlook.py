"""Outlook attachments connector (Composio transport, Microsoft Graph shapes).

Indexes attachments, not bodies. doc_id = "{message_id}:{attachment_id}".
list_changes  -> OUTLOOK_SEARCH_MESSAGES (hasattachment:yes) then
                 OUTLOOK_LIST_OUTLOOK_ATTACHMENTS per message -> CloudItem -> diff_items
fetch_content -> OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT -> file.s3url -> RawDoc

Search returns hits under ``value[].hitsContainers[].hits[]`` (message id at ``hitId``)
with ``moreResultsAvailable`` for paging (window capped at from_index+size <= 1000;
M365/Enterprise mailboxes only). Attachment listing nests under ``response_data.value``
(with fallbacks); only non-inline fileAttachments are downloadable. Download returns a
presigned ``file.s3url`` (NOT inline bytes).
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    dig,
    resolve_bytes,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_SEARCH_ACTION = "OUTLOOK_SEARCH_MESSAGES"
_LIST_ATT_ACTION = "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS"
_DOWNLOAD_ACTION = "OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT"
_FILE_ATTACHMENT_TYPE = "#microsoft.graph.fileAttachment"
_PAGE_SIZE = 25
_WINDOW_LIMIT = 1000  # Graph: from_index + size cannot exceed 1000


def _parse_graph_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.utcnow()


def _attachment_list(data: dict) -> list[dict]:
    """Pull the attachment array across the known Composio nesting variants."""
    return (
        dig(data, "response_data.value")
        or data.get("value")
        or []
    )


class OutlookConnector:
    name = "outlook"

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
        for message_id in self._message_ids(connected_account_id):
            items.extend(self._attachments_for(connected_account_id, message_id))
        return items

    def _message_ids(self, connected_account_id: str) -> Iterator[str]:
        """Page through messages that have attachments, yielding message ids."""
        from_index = 0
        seen: set[str] = set()
        while from_index < _WINDOW_LIMIT:
            data = self.client.execute(
                _SEARCH_ACTION,
                {"query": "hasattachment:yes", "size": _PAGE_SIZE, "from_index": from_index},
                connected_account_id=connected_account_id,
            )
            more = False
            for container in data.get("value", []) or []:
                for hc in container.get("hitsContainers", []) or []:
                    more = more or bool(hc.get("moreResultsAvailable"))
                    for hit in hc.get("hits", []) or []:
                        mid = hit.get("hitId")
                        if mid and mid not in seen:
                            seen.add(mid)
                            yield mid
            if not more:
                break
            from_index += _PAGE_SIZE

    def _attachments_for(
        self, connected_account_id: str, message_id: str
    ) -> Iterator[CloudItem]:
        data = self.client.execute(
            _LIST_ATT_ACTION,
            {"message_id": message_id},
            connected_account_id=connected_account_id,
        )
        for att in _attachment_list(data):
            if att.get("isInline"):
                continue
            odata_type = att.get("@odata.type")
            if odata_type and odata_type != _FILE_ATTACHMENT_TYPE:
                continue  # itemAttachment / referenceAttachment are not downloadable
            att_id = att.get("id")
            if not att_id:
                continue
            mime = att.get("contentType")
            if self.mime_filter and mime not in self.mime_filter:
                continue
            yield CloudItem(
                doc_id=f"{message_id}:{att_id}",
                source_url="",  # Graph attachments have no stable web permalink
                last_modified=_parse_graph_time(att.get("lastModifiedDateTime")),
                size_bytes=att.get("size"),
                mime=mime,
                filename=att.get("name", ""),
            )

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        message_id, _, attachment_id = doc_id.partition(":")
        data = self.client.execute(
            _DOWNLOAD_ACTION,
            {
                "message_id": message_id,
                "attachment_id": attachment_id,
                "file_name": doc_id.replace(":", "_"),
            },
            connected_account_id=ca,
        )
        content = resolve_bytes(data, "file.s3url", b64_path="contentBytes")
        file_meta = data.get("file", {}) if isinstance(data.get("file"), dict) else {}
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url="",
            mime=file_meta.get("mimetype")
            or data.get("contentType", "application/octet-stream"),
            content=content,
            filename=file_meta.get("name") or data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
