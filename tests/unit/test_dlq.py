import json
from pathlib import Path
from rag.dlq import DeadLetterQueue


def test_write_and_iter(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="abc", source="localfs", account="default",
              error="ValueError: bad pdf", traceback_str="Traceback...")
    dlq.write(doc_id="def", source="localfs", account="default",
              error="OSError: file gone", traceback_str="Traceback...")
    entries = list(dlq.iter_entries())
    assert len(entries) == 2
    assert entries[0]["doc_id"] == "abc"
    assert entries[0]["retry_count"] == 0


def test_replay_increments_retry(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="abc", source="localfs", account="default",
              error="x", traceback_str="t")
    dlq.mark_retried("abc", "localfs", "default")
    entries = list(dlq.iter_entries())
    assert entries[0]["retry_count"] == 1


def test_filter_by_source(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="a", source="localfs", account="x", error="e", traceback_str="t")
    dlq.write(doc_id="b", source="gdrive", account="y", error="e", traceback_str="t")
    locals_ = list(dlq.iter_entries(source="localfs"))
    assert len(locals_) == 1 and locals_[0]["doc_id"] == "a"
