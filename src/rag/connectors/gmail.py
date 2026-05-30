"""Gmail attachments connector (Composio transport).

Indexes attachments, not bodies. doc_id = "{message_id}:{attachment_id}".
list_changes  -> GMAIL_FETCH_EMAILS (has:attachment) then GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID
                 (format=full) per message to read attachmentList -> CloudItem
fetch_content -> GMAIL_GET_ATTACHMENT -> file.s3url -> RawDoc

Attachment IDs are not reliably present on the lightweight fetch_emails listing, so each
message is hydrated with format='full' to read ``attachmentList`` (filename, attachmentId,
mimeType). The download action returns a presigned ``file.s3url`` (NOT inline bytes).
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

_LIST_ACTION = "GMAIL_FETCH_EMAILS"
_MESSAGE_ACTION = "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID"
_ATTACHMENT_ACTION = "GMAIL_GET_ATTACHMENT"
_PERMALINK = "https://mail.google.com/mail/u/0/#all/{message_id}"


def _msg_time(msg: dict) -> datetime:
    """Best-effort message timestamp from internalDate (epoch ms) or messageTimestamp."""
    raw = msg.get("internalDate")
    if raw is not None:
        try:
            return datetime.utcfromtimestamp(int(raw) / 1000.0)
        except (ValueError, TypeError):
            pass
    ts = msg.get("messageTimestamp")
    if ts:
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
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
            params: dict = {
                "query": "has:attachment",
                "max_results": 100,
                "verbose": True,
                "include_payload": True,
            }
            if page_token:
                params["page_token"] = page_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for msg in data.get("messages", []) or []:
                mid = msg.get("messageId")
                if not mid:
                    continue
                items.extend(
                    self._attachments_for(connected_account_id, mid, _msg_time(msg))
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    def _attachments_for(
        self, connected_account_id: str, message_id: str, mtime: datetime
    ) -> Iterator[CloudItem]:
        """Hydrate one message (format=full) and yield a CloudItem per file attachment."""
        full = self.client.execute(
            _MESSAGE_ACTION,
            {"message_id": message_id, "format": "full"},
            connected_account_id=connected_account_id,
        )
        url = _PERMALINK.format(message_id=message_id)
        for att in full.get("attachmentList", []) or []:
            att_id = att.get("attachmentId")
            if not att_id:
                continue
            mime = att.get("mimeType")
            if self.mime_filter and mime not in self.mime_filter:
                continue
            yield CloudItem(
                doc_id=f"{message_id}:{att_id}",
                source_url=url,
                last_modified=mtime,
                size_bytes=att.get("size"),
                mime=mime,
                filename=att.get("filename", ""),
            )

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        message_id, _, attachment_id = doc_id.partition(":")
        data = self.client.execute(
            _ATTACHMENT_ACTION,
            {
                "message_id": message_id,
                "attachment_id": attachment_id,
                "file_name": doc_id.replace(":", "_"),
            },
            connected_account_id=ca,
        )
        content = resolve_bytes(
            data, "file.s3url", b64_path="data", urlsafe_b64=True
        )
        file_meta = data.get("file", {}) if isinstance(data.get("file"), dict) else {}
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=_PERMALINK.format(message_id=message_id),
            mime=file_meta.get("mimetype") or data.get("mimeType", "application/octet-stream"),
            content=content,
            filename=file_meta.get("name") or data.get("filename", doc_id),
            last_modified=datetime.utcnow(),
        )
