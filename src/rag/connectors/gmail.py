"""Gmail attachments connector (Composio transport).

Indexes attachments, not bodies. doc_id = "{message_id}:{attachment_id}".
list_changes  -> GMAIL_FETCH_EMAILS (query has:attachment, paginated) -> CloudItem
fetch_content -> GMAIL_GET_ATTACHMENT (url-safe base64) -> RawDoc
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

_LIST_ACTION = "GMAIL_FETCH_EMAILS"
_ATTACHMENT_ACTION = "GMAIL_GET_ATTACHMENT"
_PERMALINK = "https://mail.google.com/mail/u/0/#all/{message_id}"


def _parse_internal_date(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.utcfromtimestamp(int(value) / 1000.0)
    except (ValueError, TypeError):
        return datetime.utcnow()


class GmailConnector:
    name = "gmail"

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
        page_token: str | None = None
        while True:
            params: dict = {"query": "has:attachment", "max_results": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for msg in data.get("messages", []):
                mid = msg["messageId"]
                mtime = _parse_internal_date(msg.get("internalDate"))
                url = _PERMALINK.format(message_id=mid)
                for att in msg.get("attachments", []):
                    mime = att.get("mimeType")
                    if self.mime_filter and mime not in self.mime_filter:
                        continue
                    items.append(
                        CloudItem(
                            doc_id=f"{mid}:{att['attachmentId']}",
                            source_url=url,
                            last_modified=mtime,
                            size_bytes=att.get("size"),
                            mime=mime,
                            filename=att.get("filename", ""),
                        )
                    )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        message_id, _, attachment_id = doc_id.partition(":")
        data = self.client.execute(
            _ATTACHMENT_ACTION,
            {"message_id": message_id, "attachment_id": attachment_id},
            connected_account_id=ca,
        )
        content = base64.urlsafe_b64decode(data["data"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=_PERMALINK.format(message_id=message_id),
            mime=data.get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("filename", doc_id),
            last_modified=datetime.utcnow(),
        )
