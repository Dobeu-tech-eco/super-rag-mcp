import httpx
import pytest
import respx

from rag.connectors.gdrive import GdriveConnector
from rag.types import RawDoc


class FakeClient:
    """Records calls and returns canned Composio-style normalized data dicts."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def execute(self, action, params, *, connected_account_id):
        self.calls.append((action, params, connected_account_id))
        resp = self._responses[action]
        return resp.pop(0) if isinstance(resp, list) else resp


def _drive_file(fid, name, mtime, mime="application/pdf"):
    return {"id": fid, "name": name, "modifiedTime": mtime,
            "mimeType": mime, "size": "100",
            "webViewLink": f"https://drive.google.com/file/d/{fid}/view"}


def test_list_changes_maps_files_to_upserts(tmp_path):
    client = FakeClient({
        "GOOGLEDRIVE_FIND_FILE": {
            "files": [_drive_file("f1", "a.pdf", "2026-05-20T00:00:00Z")],
            "nextPageToken": None,
        }
    })
    conn = GdriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                           state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert len(events) == 1
    e = events[0]
    assert e.source == "gdrive" and e.doc_id == "f1" and e.operation == "upsert"
    assert e.source_url == "https://drive.google.com/file/d/f1/view"
    assert e.mime == "application/pdf"
    # Verify the connected account id was actually used.
    assert client.calls[0][2] == "ca_1"


def test_list_changes_paginates(tmp_path):
    client = FakeClient({
        "GOOGLEDRIVE_FIND_FILE": [
            {"files": [_drive_file("f1", "a.pdf", "2026-05-20T00:00:00Z")],
             "nextPageToken": "tok2"},
            {"files": [_drive_file("f2", "b.pdf", "2026-05-21T00:00:00Z")],
             "nextPageToken": None},
        ]
    })
    conn = GdriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                           state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"f1", "f2"}
    # Second page request must carry the page token under the live param name.
    assert client.calls[1][1].get("pageToken") == "tok2"


def test_list_changes_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = GdriveConnector(client=FakeClient({}), connected_accounts={},
                           state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))


@respx.mock
def test_fetch_content_downloads_via_s3url(tmp_path):
    payload = b"%PDF-1.4 fake"
    s3url = "https://s3.amazonaws.com/composio/f1.pdf"
    respx.get(s3url).mock(return_value=httpx.Response(200, content=payload))
    client = FakeClient({
        "GOOGLEDRIVE_DOWNLOAD_FILE": {
            "name": "a.pdf", "mimeType": "application/pdf",
            "downloaded_file_content": {"s3url": s3url},
            "webViewLink": "https://drive.google.com/file/d/f1/view",
        }
    })
    conn = GdriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                           state_dir=tmp_path)
    raw = conn.fetch_content("acct", "f1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload
    assert raw.doc_id == "f1" and raw.source == "gdrive"
    assert raw.mime == "application/pdf" and raw.filename == "a.pdf"
    # Download must use the live param name `fileId`.
    assert client.calls[0][1] == {"fileId": "f1"}
