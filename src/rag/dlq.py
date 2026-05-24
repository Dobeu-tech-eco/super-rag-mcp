"""Dead-letter queue stored as JSONL."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator


class DeadLetterQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def write(self, doc_id: str, source: str, account: str,
              error: str, traceback_str: str) -> None:
        # Check if entry already exists; if so, do nothing here (mark_retried updates).
        for entry in self.iter_entries():
            if entry["doc_id"] == doc_id and entry["source"] == source and entry["account"] == account:
                return
        record = {
            "doc_id": doc_id,
            "source": source,
            "account": account,
            "error": error,
            "traceback": traceback_str,
            "retry_count": 0,
            "first_failed_at": datetime.utcnow().isoformat(),
            "last_failed_at": datetime.utcnow().isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def iter_entries(self, source: str | None = None) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if source and rec["source"] != source:
                    continue
                yield rec

    def mark_retried(self, doc_id: str, source: str, account: str) -> None:
        entries = list(self.iter_entries())
        for e in entries:
            if e["doc_id"] == doc_id and e["source"] == source and e["account"] == account:
                e["retry_count"] = e.get("retry_count", 0) + 1
                e["last_failed_at"] = datetime.utcnow().isoformat()
        with self.path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
