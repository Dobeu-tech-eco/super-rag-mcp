import httpx
import pytest
import respx

from rag.connectors.outlook import OutlookConnector
from rag.types import RawDoc


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def execute(self, action, params, *, connected_account_id):
        self.calls.append((action, params, connected_account_id))
        resp = self._responses[action]
        return resp.pop(0) if isinstance(resp, list) else resp


def _search_page(hit_ids, more=False):
    return {"value": [{"hitsContainers": [
        {"moreResultsAvailable": more, "hits": [{"hitId": h} for h in hit_ids]}
    ]}]}


def _att(aid, name, mime="application/pdf", inline=False,
         odata="#microsoft.graph.fileAttachment"):
    return {"id": aid, "name": name, "contentType": mime, "isInline": inline,
            "@odata.type": odata, "size": 10,
            "lastModifiedDateTime": "2026-05-20T00:00:00Z"}


def _att_response(atts):
    return {"response_data": {"value": atts}}


def test_list_changes_maps_attachments(tmp_path):
    client = FakeClient({
        "OUTLOOK_SEARCH_MESSAGES": _search_page(["m1"]),
        "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS": _att_response([_att("a1", "x.pdf"),
                                                           _att("a2", "y.pdf")]),
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m1:a2"}
    assert all(e.source == "outlook" and e.operation == "upsert" for e in events)
    assert client.calls[0][1].get("query") == "hasattachment:yes"


def test_list_skips_inline_and_non_file_attachments(tmp_path):
    client = FakeClient({
        "OUTLOOK_SEARCH_MESSAGES": _search_page(["m1"]),
        "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS": _att_response([
            _att("a1", "x.pdf"),
            _att("sig", "logo.png", mime="image/png", inline=True),
            _att("emb", "embedded", odata="#microsoft.graph.itemAttachment"),
        ]),
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert [e.doc_id for e in events] == ["m1:a1"]


def test_search_paginates(tmp_path):
    client = FakeClient({
        "OUTLOOK_SEARCH_MESSAGES": [
            _search_page(["m1"], more=True),
            _search_page(["m2"], more=False),
        ],
        "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS": _att_response([_att("a1", "x.pdf")]),
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m2:a1"}
    search_calls = [c for c in client.calls if c[0] == "OUTLOOK_SEARCH_MESSAGES"]
    assert search_calls[1][1].get("from_index") == 25


@respx.mock
def test_fetch_content_downloads_via_s3url(tmp_path):
    payload = b"%PDF outlook"
    s3url = "https://s3.amazonaws.com/composio/m1_a1"
    respx.get(s3url).mock(return_value=httpx.Response(200, content=payload))
    client = FakeClient({
        "OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT": {
            "file": {"s3url": s3url, "mimetype": "application/pdf", "name": "x.pdf"},
        }
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    raw = conn.fetch_content("acct", "m1:a1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload and raw.source == "outlook"
    assert raw.doc_id == "m1:a1" and raw.mime == "application/pdf"
    assert client.calls[0][1] == {
        "message_id": "m1", "attachment_id": "a1", "file_name": "m1_a1"
    }


def test_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = OutlookConnector(client=FakeClient({}), connected_accounts={},
                            state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))
