import base64

import pytest

from rag.connectors.onedrive import OneDriveConnector
from rag.types import RawDoc


class FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def execute(self, action, params, *, connected_account_id):
        self.calls.append((action, params, connected_account_id))
        resp = self._responses[action]
        return resp.pop(0) if isinstance(resp, list) else resp


def _od_file(iid, name, mtime, mime="application/pdf"):
    return {"id": iid, "name": name, "lastModifiedDateTime": mtime,
            "size": 100, "webUrl": f"https://onedrive.live.com/{iid}",
            "file": {"mimeType": mime}}


def _od_folder(iid, name):
    return {"id": iid, "name": name, "lastModifiedDateTime": "2026-05-01T00:00:00Z",
            "folder": {"childCount": 3}}


def test_list_changes_maps_files_skips_folders(tmp_path):
    client = FakeClient({
        "ONE_DRIVE_ONEDRIVE_LIST_ITEMS": {
            "value": [_od_file("i1", "a.pdf", "2026-05-20T00:00:00Z"),
                      _od_folder("d1", "subdir")],
            "@odata.nextLink": None,
        }
    })
    conn = OneDriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                             state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert [e.doc_id for e in events] == ["i1"]
    assert events[0].source == "onedrive"
    assert events[0].source_url == "https://onedrive.live.com/i1"


def test_list_changes_paginates_with_skip_token(tmp_path):
    client = FakeClient({
        "ONE_DRIVE_ONEDRIVE_LIST_ITEMS": [
            {"value": [_od_file("i1", "a.pdf", "2026-05-20T00:00:00Z")],
             "@odata.nextLink": "skip999"},
            {"value": [_od_file("i2", "b.pdf", "2026-05-21T00:00:00Z")],
             "@odata.nextLink": None},
        ]
    })
    conn = OneDriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                             state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"i1", "i2"}
    assert client.calls[1][1].get("skip_token") == "skip999"


def test_fetch_content_decodes_base64(tmp_path):
    payload = b"%PDF onedrive"
    client = FakeClient({
        "ONE_DRIVE_DOWNLOAD_FILE": {
            "name": "a.pdf", "file": {"mimeType": "application/pdf"},
            "content_b64": base64.b64encode(payload).decode(),
            "webUrl": "https://onedrive.live.com/i1",
        }
    })
    conn = OneDriveConnector(client=client, connected_accounts={"acct": "ca_1"},
                             state_dir=tmp_path)
    raw = conn.fetch_content("acct", "i1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload and raw.mime == "application/pdf"
    assert raw.source == "onedrive" and raw.filename == "a.pdf"
    assert client.calls[0][1] == {"item_id": "i1"}


def test_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = OneDriveConnector(client=FakeClient({}), connected_accounts={},
                             state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))
