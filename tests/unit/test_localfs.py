from datetime import datetime, timedelta
from pathlib import Path
from rag.connectors.localfs import LocalfsConnector


def _touch(p: Path, content: str = "x") -> None:
    p.write_text(content, encoding="utf-8")


def test_list_changes_picks_up_new_files(tmp_path: Path):
    _touch(tmp_path / "a.txt", "hello")
    _touch(tmp_path / "b.pdf")  # not a real PDF but extension drives MIME guess
    conn = LocalfsConnector(roots=[tmp_path])
    changes = list(conn.list_changes(account="default", since=None))
    assert len(changes) == 2
    assert all(c.operation == "upsert" for c in changes)
    assert {Path(c.doc_id).name for c in changes} == {"a.txt", "b.pdf"}


def test_list_changes_respects_since(tmp_path: Path):
    f = tmp_path / "a.txt"
    _touch(f, "hello")
    conn = LocalfsConnector(roots=[tmp_path])
    future = datetime.utcnow() + timedelta(days=1)
    changes = list(conn.list_changes(account="default", since=future))
    assert len(changes) == 0


def test_fetch_content_returns_bytes(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    conn = LocalfsConnector(roots=[tmp_path])
    raw = conn.fetch_content(account="default", doc_id=str(f))
    assert raw.content == b"hello world"
    assert raw.source == "localfs"
    assert raw.mime == "text/plain"


def test_deleted_files_emit_delete_event(tmp_path: Path):
    f = tmp_path / "a.txt"
    _touch(f)
    conn = LocalfsConnector(roots=[tmp_path])
    seen = list(conn.list_changes(account="default", since=None))
    assert seen[0].operation == "upsert"

    f.unlink()
    # The connector remembers previously-seen files via a manifest beside the root
    # so deletes are observable on the next list_changes call.
    second = list(conn.list_changes(account="default", since=None))
    assert any(c.operation == "delete" for c in second)
