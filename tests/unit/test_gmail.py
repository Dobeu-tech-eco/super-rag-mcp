import httpx
import pytest
import respx

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


def _att(aid, filename, mime="application/pdf", size=10):
    return {"attachmentId": aid, "filename": filename, "mimeType": mime, "size": size}


def test_list_changes_emits_one_event_per_attachment(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": {
            "messages": [{"messageId": "m1", "internalDate": "1716163200000"}],
            "nextPageToken": None,
        },
        "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID": {
            "attachmentList": [_att("a1", "x.pdf"), _att("a2", "y.pdf")],
        },
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m1:a2"}
    assert all(e.source == "gmail" and e.operation == "upsert" for e in events)
    assert events[0].source_url == "https://mail.google.com/mail/u/0/#all/m1"
    # The message is hydrated with format=full to read attachmentList reliably.
    hydrate = [c for c in client.calls if c[0] == "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID"]
    assert hydrate[0][1] == {"message_id": "m1", "format": "full"}


def test_list_changes_respects_mime_filter(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": {
            "messages": [{"messageId": "m1", "internalDate": "1716163200000"}],
            "nextPageToken": None,
        },
        "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID": {
            "attachmentList": [_att("a1", "x.pdf"),
                               _att("a2", "z.png", mime="image/png", size=5)],
        },
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert [e.doc_id for e in events] == ["m1:a1"]


def test_list_changes_paginates(tmp_path):
    client = FakeClient({
        "GMAIL_FETCH_EMAILS": [
            {"messages": [{"messageId": "m1", "internalDate": "1716163200000"}],
             "nextPageToken": "p2"},
            {"messages": [{"messageId": "m2", "internalDate": "1716163200000"}],
             "nextPageToken": None},
        ],
        "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID": {
            "attachmentList": [_att("a1", "x.pdf", size=1)],
        },
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m2:a1"}
    fetch_calls = [c for c in client.calls if c[0] == "GMAIL_FETCH_EMAILS"]
    assert fetch_calls[1][1].get("page_token") == "p2"


@respx.mock
def test_fetch_content_splits_docid_and_downloads(tmp_path):
    payload = b"%PDF gmail attachment"
    s3url = "https://s3.amazonaws.com/composio/m1_a1"
    respx.get(s3url).mock(return_value=httpx.Response(200, content=payload))
    client = FakeClient({
        "GMAIL_GET_ATTACHMENT": {
            "file": {"s3url": s3url, "mimetype": "application/pdf", "name": "x.pdf"},
        }
    })
    conn = GmailConnector(client=client, connected_accounts={"acct": "ca_1"},
                          state_dir=tmp_path)
    raw = conn.fetch_content("acct", "m1:a1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload and raw.mime == "application/pdf"
    assert raw.source == "gmail" and raw.doc_id == "m1:a1"
    # message_id, attachment_id and the required file_name must all be passed.
    assert client.calls[0][1] == {
        "message_id": "m1", "attachment_id": "a1", "file_name": "m1_a1"
    }


def test_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = GmailConnector(client=FakeClient({}), connected_accounts={},
                          state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))
