from datetime import datetime
from pathlib import Path

import pytest

from rag.connectors import ConnectorAuthError
from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)


def test_resolve_connected_account_returns_id():
    assert resolve_connected_account({"alias": "ca_1"}, "alias") == "ca_1"


def test_resolve_connected_account_missing_raises_auth():
    with pytest.raises(ConnectorAuthError):
        resolve_connected_account({}, "alias")


def _item(doc_id: str, mtime: datetime) -> CloudItem:
    return CloudItem(
        doc_id=doc_id, source_url=f"https://x/{doc_id}", last_modified=mtime,
        size_bytes=10, mime="application/pdf", filename=f"{doc_id}.pdf",
    )


def test_diff_items_emits_upsert_for_new_items_first_run(tmp_path: Path):
    store = ManifestStore(tmp_path)
    items = [_item("a", datetime(2026, 5, 1)), _item("b", datetime(2026, 5, 2))]
    events = list(diff_items("gdrive", "acct", items, since=None, manifest_store=store))
    assert {e.doc_id for e in events} == {"a", "b"}
    assert all(e.operation == "upsert" for e in events)
    assert all(e.source == "gdrive" and e.account == "acct" for e in events)


def test_diff_items_skips_items_older_than_since(tmp_path: Path):
    store = ManifestStore(tmp_path)
    items = [_item("old", datetime(2026, 5, 1)), _item("new", datetime(2026, 6, 1))]
    events = list(diff_items("gdrive", "acct", items, since=datetime(2026, 5, 15),
                             manifest_store=store))
    assert [e.doc_id for e in events] == ["new"]


def test_diff_items_emits_delete_for_vanished_items(tmp_path: Path):
    store = ManifestStore(tmp_path)
    # First run records a and b.
    list(diff_items("gdrive", "acct",
                    [_item("a", datetime(2026, 5, 1)), _item("b", datetime(2026, 5, 1))],
                    since=None, manifest_store=store))
    # Second run: b is gone.
    events = list(diff_items("gdrive", "acct", [_item("a", datetime(2026, 5, 1))],
                             since=datetime(2026, 5, 2), manifest_store=store))
    deletes = [e for e in events if e.operation == "delete"]
    assert [e.doc_id for e in deletes] == ["b"]


def test_manifest_persists_across_instances(tmp_path: Path):
    ManifestStore(tmp_path).save("gdrive", "acct", {"a": {"mtime": "x"}})
    assert ManifestStore(tmp_path).load("gdrive", "acct") == {"a": {"mtime": "x"}}


def test_manifest_load_missing_returns_empty(tmp_path: Path):
    assert ManifestStore(tmp_path).load("gdrive", "acct") == {}
