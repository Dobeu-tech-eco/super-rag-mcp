import base64

import pytest

from rag.connectors.gmail import GmailConnector
from rag.types import RawDoc


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def execute(self, action, params, *, connected_account_id):
        self.calls.append((action, params, connected_account_id))
        resp = self._responses[action]
        return resp.pop(0) if isinstance(resp, list) else resp


def _msg(mid, atts, ts="1716163200000"):
    # internalDate is epoch millis as a string (Gmail convention).
    return {"messageId": mid, "internalDate": ts, "attachments": atts}


def test_list_changes_emits_one_event_per_attachment(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": {
            "messages": [
                _msg("m1", [
                    {"attachmentId": "a1", "filename": "x.pdf", "mimeType": "application/pdf", "size": 10},
                    {"attachmentId": "a2", "filename": "y.pdf", "mimeType": "application/pdf", "size": 20},
                ]),
            ],
            "nextPageToken": None,
        }
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m1:a2"}
    assert all(e.source == "gmail" and e.operation == "upsert" for e in events)
    assert events[0].source_url == "https://mail.google.com/mail/u/0/#all/m1"


def test_list_changes_respects_mime_filter(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": {
            "messages": [
                _msg("m1", [
                    {"attachmentId": "a1", "filename": "x.pdf", "mimeType": "application/pdf", "size": 10},
                    {"attachmentId": "a2", "filename": "z.png", "mimeType": "image/png", "size": 5},
                ]),
            ],
            "nextPageToken": None,
        }
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert [e.doc_id for e in events] == ["m1:a1"]


def test_list_changes_paginates(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": [
            {"messages": [_msg("m1", [{"attachmentId": "a1", "filename": "x.pdf",
                                       "mimeType": "application/pdf", "size": 1}])],
             "nextPageToken": "p2"},
            {"messages": [_msg("m2", [{"attachmentId": "a1", "filename": "y.pdf",
                                       "mimeType": "application/pdf", "size": 1}])],
             "nextPageToken": None},
        ]
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m2:a1"}
    assert client.calls[1][1].get("page_token") == "p2"


def test_fetch_content_splits_docid_and_decodes(tmp_path):
    payload = b"%PDF gmail attachment"
    client = FakeClient({
        "GMAIL_GET_ATTACHMENT": {
            "data": base64.urlsafe_b64encode(payload).decode(),
            "filename": "x.pdf", "mimeType": "application/pdf",
        }
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path)
    raw = conn.fetch_content("acct", "m1:a1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload and raw.mime == "application/pdf"
    assert raw.source == "gmail" and raw.doc_id == "m1:a1"
    # message_id and attachment_id must both be passed through.
    assert client.calls[0][1] == {"message_id": "m1", "attachment_id": "a1"}


def test_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = GmailConnector(client=FakeClient({}), connected_accounts={},
                          state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))
