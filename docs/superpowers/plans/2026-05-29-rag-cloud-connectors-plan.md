# RAG Cloud Connectors Implementation Plan (Plan 2 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Composio-backed cloud connectors (Google Drive, OneDrive, Gmail attachments, Outlook attachments) to the existing RAG pipeline so `rag sync` can ingest documents from cloud sources alongside local files — using the same `Connector` protocol, `ChangeEvent`/`RawDoc` contracts, and per-source/per-doc failure isolation already shipped in Plan 1.

**Architecture:** Each cloud connector depends on an injected `ComposioClient` interface (a thin `execute(action, params, connected_account_id)` transport), which makes all connector logic hermetically unit-testable with a fake client. The real Composio SDK binding (`ComposioSDKClient`) is a small, integration-gated adapter — unit tests never touch the network. Cloud sources share helpers in `connectors/_cloud.py`: account-alias resolution, a JSON manifest store for delete detection (mirroring `localfs`), and a `diff_items` function that turns a listed file set into `ChangeEvent`s. Connectors list the current file set (filtered by `since` for upserts), diff against the prior manifest for deletes, and `fetch_content` returns `RawDoc` bytes. This stays within the existing `since: datetime` orchestrator contract; token-based deltas (Drive `changes.list`, OneDrive `delta()`, Gmail `history.list`) are a deliberate future refinement (see Non-Goals).

**Tech Stack:** Python 3.12, pydantic (config), httpx (already a dep; used to GET attachment/file URLs when Composio returns a link), pytest + respx (existing test stack), composio (new optional runtime dep, lazy-imported, integration-only).

**Prerequisites (one-time, not plan tasks):**
- Plan 1 complete (it is — Tasks 1–15 shipped; `pytest` green).
- For the *integration* tier only (skipped by default): `pip install composio`, a `COMPOSIO_API_KEY` env var, and at least one Composio connected account per source you want to test. Unit tests require none of this.

## Non-Goals (explicit, to prevent overbuilding)

- **Token-based incremental deltas.** MVP lists the current file set each run and filters by `since` for upserts + manifest diff for deletes, exactly like `localfs`. Drive `changes.list` / OneDrive `delta()` / Gmail `history.list` are out of scope for Plan 2.
- **The bundle-sync / VPS / Tailscale plane** (that is Plan 4).
- **The MCP server** (`rag.serve.mcp`) — that is Plan 3.
- **Reranking, eval tier** — unchanged from Plan 1.
- Do **not** modify any Plan 1 module behavior except the two explicitly listed integration points (`config.py`, `serve/cli.py`).

---

## File Structure

```
src/rag/
├── config.py                        # MODIFY — add optional ComposioConfig block
├── connectors/
│   ├── __init__.py                  # UNCHANGED (Connector protocol + error classes already exist)
│   ├── localfs.py                   # UNCHANGED (reference impl)
│   ├── composio_client.py           # Task 2 — ComposioClient protocol + unwrap_response + ComposioSDKClient
│   ├── _cloud.py                    # Task 3 — CloudItem, resolve_connected_account, ManifestStore, diff_items
│   ├── gdrive.py                    # Task 4
│   ├── onedrive.py                  # Task 5
│   ├── gmail.py                     # Task 6
│   └── outlook.py                   # Task 7
└── serve/
    └── cli.py                       # MODIFY (Task 8) — build cloud connectors from config

tests/
├── unit/
│   ├── test_config_composio.py      # Task 1
│   ├── test_composio_client.py      # Task 2
│   ├── test_cloud_helpers.py        # Task 3
│   ├── test_gdrive.py               # Task 4
│   ├── test_onedrive.py             # Task 5
│   ├── test_gmail.py                # Task 6
│   ├── test_outlook.py              # Task 7
│   └── test_cli_connectors.py       # Task 8
└── integration/
    └── test_cloud_connectors.py     # Task 9 (gated by RAG_INTEGRATION=1)
```

**Contracts you must conform to (already shipped in Plan 1 — do not change them):**

`Connector` protocol (`src/rag/connectors/__init__.py`):
```python
class Connector(Protocol):
    name: str
    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]: ...
    def fetch_content(self, account: str, doc_id: str) -> RawDoc: ...
```
Errors: `ConnectorError`, `ConnectorAuthError`, `ConnectorRateLimitError` (subclasses, already defined).

`ChangeEvent` and `RawDoc` (`src/rag/types.py`):
```python
@dataclass
class ChangeEvent:
    source: str; account: str; doc_id: str; operation: str  # "upsert" | "delete"
    source_url: str; last_modified: datetime
    size_bytes: int | None = None; mime: str | None = None

@dataclass
class RawDoc:
    doc_id: str; source: str; account: str; source_url: str
    mime: str; content: bytes; filename: str; last_modified: datetime
```

The orchestrator (`sync.py`) calls `conn.list_changes(account, since)` then, per non-delete event, `conn.fetch_content(account, doc_id)`. Auth failures must raise `ConnectorAuthError` (the orchestrator catches it per-source and continues).

---

## Task 1: Config — optional Composio block

**Files:**
- Modify: `src/rag/config.py`
- Modify: `config.example.yaml`
- Test: `tests/unit/test_config_composio.py`

The source models (`GdriveSource`, `OneDriveSource`, `GmailSource`, `OutlookSource`) already exist and are registered. This task only adds the top-level `composio:` block that maps account aliases to Composio connected-account IDs and names the env var holding the API key. It must be **optional** so existing localfs-only configs (Plan 1) keep loading.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config_composio.py`:

```python
from pathlib import Path
from rag.config import Config, ComposioConfig, load_config


def test_config_without_composio_block_still_loads(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources:
  - kind: localfs
    paths: [/tmp/docs]
embedding: {model: bge-small-en-v1.5, ollama_url: http://localhost:11434, batch_size: 32}
chunking: {primary: sentence, fallback_size: 512, overlap: 64}
ocr: {enabled: true, strategy: auto_detect, min_chars_per_page: 100}
llm: {default: claude-cli, private_prefix: "private:", private_tag_routes_to: ollama, ollama_model: q}
paths: {bundle_dir: /tmp/b, dlq: /tmp/d.jsonl, metadata: /tmp/m.sqlite}
"""
    )
    cfg = load_config(cfg_file)
    assert cfg.composio is None


def test_config_with_composio_block(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources:
  - kind: gdrive
    accounts: [personal-jeremy]
embedding: {model: bge-small-en-v1.5, ollama_url: http://localhost:11434, batch_size: 32}
chunking: {primary: sentence, fallback_size: 512, overlap: 64}
ocr: {enabled: true, strategy: auto_detect, min_chars_per_page: 100}
llm: {default: claude-cli, private_prefix: "private:", private_tag_routes_to: ollama, ollama_model: q}
paths: {bundle_dir: /tmp/b, dlq: /tmp/d.jsonl, metadata: /tmp/m.sqlite}
composio:
  api_key_env: COMPOSIO_API_KEY
  connected_accounts:
    personal-jeremy: ca_abc123
    work-baldor: ca_def456
"""
    )
    cfg = load_config(cfg_file)
    assert isinstance(cfg.composio, ComposioConfig)
    assert cfg.composio.api_key_env == "COMPOSIO_API_KEY"
    assert cfg.composio.connected_accounts["personal-jeremy"] == "ca_abc123"


def test_composio_config_defaults():
    c = ComposioConfig()
    assert c.api_key_env == "COMPOSIO_API_KEY"
    assert c.connected_accounts == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config_composio.py -v`
Expected: FAIL with `ImportError: cannot import name 'ComposioConfig'`.

- [ ] **Step 3: Implement the change in `src/rag/config.py`**

Add this class immediately after `PathsConfig` (before `class Config`):

```python
class ComposioConfig(BaseModel):
    api_key_env: str = "COMPOSIO_API_KEY"
    connected_accounts: dict[str, str] = Field(default_factory=dict)
```

Then add one field to `class Config` (after `paths: PathsConfig`):

```python
    composio: ComposioConfig | None = None
```

No other change to `config.py`. `Field` is already imported.

- [ ] **Step 4: Update `config.example.yaml`**

Append this block to the end of `config.example.yaml`:

```yaml

# Composio auth for cloud connectors (Plan 2). Omit entirely for localfs-only setups.
# api_key_env names the environment variable holding your Composio API key.
# connected_accounts maps each source account alias to its Composio connected-account ID.
composio:
  api_key_env: COMPOSIO_API_KEY
  connected_accounts:
    personal-jeremy: ca_REPLACE_ME
    work-baldor: ca_REPLACE_ME
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_config_composio.py -v`
Expected: 3 passed.

- [ ] **Step 6: Confirm no Plan 1 regression**

Run: `pytest tests/unit/test_config.py -v`
Expected: 2 passed (existing config tests unaffected).

- [ ] **Step 7: Commit**

```bash
git add src/rag/config.py config.example.yaml tests/unit/test_config_composio.py
git commit -m "[CONFIG] Plan 2 Task 1: optional Composio config block

- ComposioConfig (api_key_env + connected_accounts alias->id map)
- Config.composio is Optional so localfs-only configs still load
- config.example.yaml documents the block

Tests: 3 new unit tests; existing config tests still green
Feature ID: P2-1"
```

---

## Task 2: Composio client (transport interface + response unwrap + real adapter)

**Files:**
- Create: `src/rag/connectors/composio_client.py`
- Test: `tests/unit/test_composio_client.py`

The connectors call Composio through a tiny interface so they can be unit-tested with a fake. The only logic worth unit-testing here is **response unwrapping + error mapping**, which is a pure function. The real SDK adapter is integration-gated and lazy-imports `composio`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_composio_client.py`:

```python
import pytest
from rag.connectors import ConnectorAuthError, ConnectorError, ConnectorRateLimitError
from rag.connectors.composio_client import unwrap_response


def test_unwrap_returns_data_on_success():
    resp = {"successful": True, "data": {"files": [{"id": "1"}]}}
    assert unwrap_response(resp) == {"files": [{"id": "1"}]}


def test_unwrap_treats_missing_successful_as_success():
    # Some actions omit the flag; presence of data with no error means success.
    assert unwrap_response({"data": {"x": 1}}) == {"x": 1}


def test_unwrap_returns_empty_dict_when_data_missing():
    assert unwrap_response({"successful": True}) == {}


def test_unwrap_raises_auth_on_401():
    with pytest.raises(ConnectorAuthError):
        unwrap_response({"successful": False, "error": "HTTP 401 Unauthorized"})


def test_unwrap_raises_auth_on_expired_token():
    with pytest.raises(ConnectorAuthError):
        unwrap_response({"successful": False, "error": "invalid_grant: token expired"})


def test_unwrap_raises_rate_limit_on_429():
    with pytest.raises(ConnectorRateLimitError):
        unwrap_response({"successful": False, "error": "HTTP 429 too many requests"})


def test_unwrap_raises_generic_error_otherwise():
    with pytest.raises(ConnectorError) as exc:
        unwrap_response({"successful": False, "error": "boom"})
    # Must be the base ConnectorError, not an auth/rate subclass.
    assert not isinstance(exc.value, (ConnectorAuthError, ConnectorRateLimitError))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_composio_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors.composio_client'`.

- [ ] **Step 3: Implement `src/rag/connectors/composio_client.py`**

```python
"""Composio transport for cloud connectors.

Connectors depend on the ``ComposioClient`` Protocol, never on the composio SDK
directly, so they stay hermetically unit-testable with a fake client. The only
logic exercised by unit tests is ``unwrap_response`` (response + error mapping).
``ComposioSDKClient`` is the real, integration-gated binding.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rag.connectors import ConnectorAuthError, ConnectorError, ConnectorRateLimitError

_AUTH_MARKERS = ("401", "403", "unauthor", "invalid_grant", "expired", "auth")
_RATE_MARKERS = ("429", "rate limit", "too many requests", "rate_limit")


@runtime_checkable
class ComposioClient(Protocol):
    """Executes one Composio action against one connected account."""

    def execute(
        self, action: str, params: dict[str, Any], *, connected_account_id: str
    ) -> dict[str, Any]:
        ...


def unwrap_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Return the ``data`` payload, or raise a typed connector error.

    Composio responses look like ``{"successful": bool, "data": {...}, "error": ...}``.
    A missing ``successful`` flag is treated as success (some actions omit it).
    """
    successful = resp.get("successful", True)
    if not successful:
        message = str(resp.get("error") or "composio execution failed")
        low = message.lower()
        if any(m in low for m in _RATE_MARKERS):
            raise ConnectorRateLimitError(message)
        if any(m in low for m in _AUTH_MARKERS):
            raise ConnectorAuthError(message)
        raise ConnectorError(message)
    data = resp.get("data")
    return data if isinstance(data, dict) else {}


class ComposioSDKClient:
    """Real Composio transport. Integration-gated; never used by unit tests.

    NOTE for implementer/integrator: confirm the exact SDK call signature and the
    response envelope against the installed ``composio`` package version (use
    context7 or the Composio docs) before relying on this in production. The
    connectors only assume the *normalized* shape produced by ``unwrap_response``.
    """

    def __init__(self, api_key: str) -> None:
        from composio import Composio  # lazy: composio is an optional runtime dep

        self._client = Composio(api_key=api_key)

    def execute(
        self, action: str, params: dict[str, Any], *, connected_account_id: str
    ) -> dict[str, Any]:
        resp = self._client.tools.execute(
            action, connected_account_id=connected_account_id, arguments=params
        )
        if not isinstance(resp, dict):
            resp = {
                "successful": getattr(resp, "successful", True),
                "data": getattr(resp, "data", None),
                "error": getattr(resp, "error", None),
            }
        return unwrap_response(resp)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_composio_client.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/composio_client.py tests/unit/test_composio_client.py
git commit -m "[COMPOSIO] Plan 2 Task 2: Composio transport interface + error mapping

- ComposioClient Protocol (execute(action, params, connected_account_id))
- unwrap_response: pure data/error mapper -> Connector{Auth,RateLimit,}Error
- ComposioSDKClient: lazy-imported real adapter (integration-only)

Tests: 7 unit tests (pure unwrap logic; no network)
Feature ID: P2-2"
```

---

## Task 3: Cloud helpers (shared listing/diff/manifest)

**Files:**
- Create: `src/rag/connectors/_cloud.py`
- Test: `tests/unit/test_cloud_helpers.py`

All four cloud connectors share: resolving an account alias to a connected-account ID, persisting a per-(source, account) manifest for delete detection, and turning a listed item set into `ChangeEvent`s. This mirrors `localfs`'s manifest approach but stores manifests in a passed-in `state_dir` (cloud sources have no on-disk root).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cloud_helpers.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cloud_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors._cloud'`.

- [ ] **Step 3: Implement `src/rag/connectors/_cloud.py`**

```python
"""Shared helpers for Composio-backed cloud connectors.

- resolve_connected_account: alias -> Composio connected-account id (auth error if absent)
- ManifestStore: per-(source, account) JSON snapshot for delete detection
- diff_items: turn a current item set into upsert/delete ChangeEvents (mirrors localfs)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from rag.connectors import ConnectorAuthError
from rag.types import ChangeEvent


@dataclass
class CloudItem:
    """One listed object from a cloud source (pre-fetch)."""

    doc_id: str
    source_url: str
    last_modified: datetime
    size_bytes: int | None = None
    mime: str | None = None
    filename: str = ""


def resolve_connected_account(connected_accounts: dict[str, str], account: str) -> str:
    ca = connected_accounts.get(account)
    if not ca:
        raise ConnectorAuthError(
            f"no Composio connected account configured for alias {account!r}"
        )
    return ca


class ManifestStore:
    """Persists the last-seen item set per (source, account) so deletes are observable."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, source: str, account: str) -> Path:
        safe = account.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.state_dir / f"{source}-{safe}-manifest.json"

    def load(self, source: str, account: str) -> dict[str, dict]:
        p = self._path(source, account)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def save(self, source: str, account: str, current: dict[str, dict]) -> None:
        self._path(source, account).write_text(
            json.dumps(current, indent=2), encoding="utf-8"
        )


def diff_items(
    source: str,
    account: str,
    items: list[CloudItem],
    since: datetime | None,
    manifest_store: ManifestStore,
) -> Iterator[ChangeEvent]:
    """Yield upsert events for new/modified items and delete events for vanished ones.

    Upserts are filtered by ``since`` (items modified at or before ``since`` are skipped,
    matching the localfs connector). Deletes come from comparing against the prior manifest.
    The manifest is rewritten to the current set at the end.
    """
    previous = manifest_store.load(source, account)
    current: dict[str, dict] = {}

    for it in items:
        current[it.doc_id] = {
            "mtime": it.last_modified.isoformat(),
            "size": it.size_bytes,
        }
        if since and it.last_modified <= since:
            continue
        yield ChangeEvent(
            source=source,
            account=account,
            doc_id=it.doc_id,
            operation="upsert",
            source_url=it.source_url,
            last_modified=it.last_modified,
            size_bytes=it.size_bytes,
            mime=it.mime,
        )

    for prev_id in previous:
        if prev_id not in current:
            yield ChangeEvent(
                source=source,
                account=account,
                doc_id=prev_id,
                operation="delete",
                source_url="",
                last_modified=datetime.utcnow(),
            )

    manifest_store.save(source, account, current)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cloud_helpers.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/_cloud.py tests/unit/test_cloud_helpers.py
git commit -m "[CLOUD] Plan 2 Task 3: shared cloud connector helpers

- CloudItem dataclass (listed object pre-fetch)
- resolve_connected_account: alias -> connected-account id, ConnectorAuthError if missing
- ManifestStore: per-(source,account) JSON snapshot in state_dir
- diff_items: current set -> upsert/delete ChangeEvents (localfs-style, since-filtered)

Tests: 7 unit tests
Feature ID: P2-3"
```

---

## Task 4: Google Drive connector

**Files:**
- Create: `src/rag/connectors/gdrive.py`
- Test: `tests/unit/test_gdrive.py`

Lists files via `GOOGLEDRIVE_FIND_FILE` (paginated), maps each to a `CloudItem`, diffs via Task 3 helpers, and downloads via `GOOGLEDRIVE_DOWNLOAD_FILE` (the connector expects the action's normalized data to carry the file content as base64 under `content_b64`, OR a fetchable URL under `file_url`). The fake client in the test returns these shapes; the integration adapter (Task 9 notes) must confirm real field names.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gdrive.py`:

```python
import base64
from datetime import datetime

import pytest

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
    # Second page request must carry the page token.
    assert client.calls[1][1].get("page_token") == "tok2"


def test_list_changes_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = GdriveConnector(client=FakeClient({}), connected_accounts={},
                           state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))


def test_fetch_content_decodes_base64(tmp_path):
    payload = b"%PDF-1.4 fake"
    client = FakeClient({
        "GOOGLEDRIVE_DOWNLOAD_FILE": {
            "name": "a.pdf", "mimeType": "application/pdf",
            "content_b64": base64.b64encode(payload).decode(),
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
    assert client.calls[0][1] == {"file_id": "f1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gdrive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors.gdrive'`.

- [ ] **Step 3: Implement `src/rag/connectors/gdrive.py`**

```python
"""Google Drive connector (Composio transport).

list_changes  -> GOOGLEDRIVE_FIND_FILE (paginated) -> CloudItem -> diff_items
fetch_content -> GOOGLEDRIVE_DOWNLOAD_FILE -> RawDoc
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Iterator

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_ACTION = "GOOGLEDRIVE_FIND_FILE"
_DOWNLOAD_ACTION = "GOOGLEDRIVE_DOWNLOAD_FILE"


def _parse_drive_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class GdriveConnector:
    name = "gdrive"

    def __init__(
        self,
        client: ComposioClient,
        connected_accounts: dict[str, str],
        state_dir,
        include_paths: list[str] | None = None,
        mime_filter: list[str] | None = None,
    ) -> None:
        self.client = client
        self.connected_accounts = connected_accounts
        self.manifest = ManifestStore(state_dir)
        self.include_paths = include_paths or ["/"]
        self.mime_filter = mime_filter

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ca = resolve_connected_account(self.connected_accounts, account)
        items = self._list_items(ca)
        yield from diff_items(self.name, account, items, since, self.manifest)

    def _list_items(self, connected_account_id: str) -> list[CloudItem]:
        items: list[CloudItem] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for f in data.get("files", []):
                mime = f.get("mimeType")
                if self.mime_filter and mime not in self.mime_filter:
                    continue
                size = f.get("size")
                items.append(
                    CloudItem(
                        doc_id=f["id"],
                        source_url=f.get("webViewLink", ""),
                        last_modified=_parse_drive_time(f.get("modifiedTime")),
                        size_bytes=int(size) if size is not None else None,
                        mime=mime,
                        filename=f.get("name", ""),
                    )
                )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        data = self.client.execute(
            _DOWNLOAD_ACTION, {"file_id": doc_id}, connected_account_id=ca
        )
        content = base64.b64decode(data["content_b64"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webViewLink", ""),
            mime=data.get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_gdrive.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/gdrive.py tests/unit/test_gdrive.py
git commit -m "[GDRIVE] Plan 2 Task 4: Google Drive connector via Composio

- list_changes: GOOGLEDRIVE_FIND_FILE paginated -> CloudItem -> diff_items
- mime_filter applied at list time; webViewLink as source_url
- fetch_content: GOOGLEDRIVE_DOWNLOAD_FILE -> base64 -> RawDoc
- auth failure for unconfigured alias via resolve_connected_account

Tests: 4 unit tests (fake Composio client; no network)
Feature ID: P2-4"
```

---

## Task 5: OneDrive connector

**Files:**
- Create: `src/rag/connectors/onedrive.py`
- Test: `tests/unit/test_onedrive.py`

Lists via `ONE_DRIVE_ONEDRIVE_LIST_ITEMS` (paginated by `skip_token`), downloads via `ONE_DRIVE_DOWNLOAD_FILE`. Microsoft Graph items carry `id`, `name`, `lastModifiedDateTime`, `size`, `webUrl`, and a `file.mimeType` nested field; folders lack the `file` key and are skipped.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_onedrive.py`:

```python
import base64
from datetime import datetime

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_onedrive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors.onedrive'`.

- [ ] **Step 3: Implement `src/rag/connectors/onedrive.py`**

```python
"""OneDrive connector (Composio transport, Microsoft Graph item shapes).

list_changes  -> ONE_DRIVE_ONEDRIVE_LIST_ITEMS (paginated) -> CloudItem -> diff_items
fetch_content -> ONE_DRIVE_DOWNLOAD_FILE -> RawDoc
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Iterator

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_ACTION = "ONE_DRIVE_ONEDRIVE_LIST_ITEMS"
_DOWNLOAD_ACTION = "ONE_DRIVE_DOWNLOAD_FILE"


def _parse_graph_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class OneDriveConnector:
    name = "onedrive"

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
        skip_token: str | None = None
        while True:
            params: dict = {}
            if skip_token:
                params["skip_token"] = skip_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for it in data.get("value", []):
                if "file" not in it:  # folders / non-file items
                    continue
                mime = it.get("file", {}).get("mimeType")
                if self.mime_filter and mime not in self.mime_filter:
                    continue
                size = it.get("size")
                items.append(
                    CloudItem(
                        doc_id=it["id"],
                        source_url=it.get("webUrl", ""),
                        last_modified=_parse_graph_time(it.get("lastModifiedDateTime")),
                        size_bytes=int(size) if size is not None else None,
                        mime=mime,
                        filename=it.get("name", ""),
                    )
                )
            skip_token = data.get("@odata.nextLink")
            if not skip_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        data = self.client.execute(
            _DOWNLOAD_ACTION, {"item_id": doc_id}, connected_account_id=ca
        )
        content = base64.b64decode(data["content_b64"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webUrl", ""),
            mime=data.get("file", {}).get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_onedrive.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/onedrive.py tests/unit/test_onedrive.py
git commit -m "[ONEDRIVE] Plan 2 Task 5: OneDrive connector via Composio

- list_changes: ONE_DRIVE_ONEDRIVE_LIST_ITEMS paginated (skip_token); folders skipped
- mime_filter on file.mimeType; webUrl as source_url
- fetch_content: ONE_DRIVE_DOWNLOAD_FILE -> base64 -> RawDoc

Tests: 4 unit tests (fake Composio client)
Feature ID: P2-5"
```

---

## Task 6: Gmail attachments connector

**Files:**
- Create: `src/rag/connectors/gmail.py`
- Test: `tests/unit/test_gmail.py`

Email connectors index **attachments**, not message bodies. One message may carry several attachments, so `doc_id = "{message_id}:{attachment_id}"`. Lists via `GMAIL_FETCH_EMAILS` (query `has:attachment`, paginated by `page_token`), iterating each message's attachment list; downloads via `GMAIL_GET_ATTACHMENT`. Gmail base64 is URL-safe.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_gmail.py`:

```python
import base64
from datetime import datetime

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gmail.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors.gmail'`.

- [ ] **Step 3: Implement `src/rag/connectors/gmail.py`**

```python
"""Gmail attachments connector (Composio transport).

Indexes attachments, not bodies. doc_id = "{message_id}:{attachment_id}".
list_changes  -> GMAIL_FETCH_EMAILS (query has:attachment, paginated) -> CloudItem
fetch_content -> GMAIL_GET_ATTACHMENT (url-safe base64) -> RawDoc
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Iterator

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_ACTION = "GMAIL_FETCH_EMAILS"
_ATTACHMENT_ACTION = "GMAIL_GET_ATTACHMENT"
_PERMALINK = "https://mail.google.com/mail/u/0/#all/{message_id}"


def _parse_internal_date(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.utcfromtimestamp(int(value) / 1000.0)
    except (ValueError, TypeError):
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
            params: dict = {"query": "has:attachment", "max_results": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.client.execute(
                _LIST_ACTION, params, connected_account_id=connected_account_id
            )
            for msg in data.get("messages", []):
                mid = msg["messageId"]
                mtime = _parse_internal_date(msg.get("internalDate"))
                url = _PERMALINK.format(message_id=mid)
                for att in msg.get("attachments", []):
                    mime = att.get("mimeType")
                    if self.mime_filter and mime not in self.mime_filter:
                        continue
                    items.append(
                        CloudItem(
                            doc_id=f"{mid}:{att['attachmentId']}",
                            source_url=url,
                            last_modified=mtime,
                            size_bytes=att.get("size"),
                            mime=mime,
                            filename=att.get("filename", ""),
                        )
                    )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        message_id, _, attachment_id = doc_id.partition(":")
        data = self.client.execute(
            _ATTACHMENT_ACTION,
            {"message_id": message_id, "attachment_id": attachment_id},
            connected_account_id=ca,
        )
        content = base64.urlsafe_b64decode(data["data"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=_PERMALINK.format(message_id=message_id),
            mime=data.get("mimeType", "application/octet-stream"),
            content=content,
            filename=data.get("filename", doc_id),
            last_modified=datetime.utcnow(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_gmail.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/gmail.py tests/unit/test_gmail.py
git commit -m "[GMAIL] Plan 2 Task 6: Gmail attachments connector via Composio

- doc_id = message_id:attachment_id; one ChangeEvent per attachment
- list: GMAIL_FETCH_EMAILS query has:attachment, paginated; mime_filter applied
- fetch: GMAIL_GET_ATTACHMENT url-safe base64 -> RawDoc; Gmail permalink as source_url

Tests: 5 unit tests (fake Composio client)
Feature ID: P2-6"
```

---

## Task 7: Outlook attachments connector

**Files:**
- Create: `src/rag/connectors/outlook.py`
- Test: `tests/unit/test_outlook.py`

Same attachment model as Gmail. Lists messages via `OUTLOOK_LIST_MAIL_FOLDER_MESSAGES` (folder `inbox`, paginated by `skip`), then per message lists attachments via `OUTLOOK_LIST_OUTLOOK_ATTACHMENTS`; downloads via `OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT`. `doc_id = "{message_id}:{attachment_id}"`. Graph attachment bytes come back as standard base64 in `contentBytes`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_outlook.py`:

```python
import base64
from datetime import datetime

import pytest

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


def test_list_changes_one_event_per_attachment(tmp_path):
    client = FakeClient({
        "OUTLOOK_LIST_MAIL_FOLDER_MESSAGES": {
            "value": [
                {"id": "m1", "lastModifiedDateTime": "2026-05-20T00:00:00Z",
                 "hasAttachments": True,
                 "webLink": "https://outlook.office.com/mail/m1"},
            ],
            "@odata.nextLink": None,
        },
        "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS": {
            "value": [
                {"id": "a1", "name": "x.pdf", "contentType": "application/pdf", "size": 10},
            ]
        },
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path, mime_filter=["application/pdf"])
    events = list(conn.list_changes("acct", since=None))
    assert [e.doc_id for e in events] == ["m1:a1"]
    assert events[0].source == "outlook"
    assert events[0].source_url == "https://outlook.office.com/mail/m1"


def test_list_changes_skips_messages_without_attachments(tmp_path):
    client = FakeClient({
        "OUTLOOK_LIST_MAIL_FOLDER_MESSAGES": {
            "value": [
                {"id": "m1", "lastModifiedDateTime": "2026-05-20T00:00:00Z",
                 "hasAttachments": False, "webLink": "https://outlook.office.com/mail/m1"},
            ],
            "@odata.nextLink": None,
        },
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert events == []
    # Attachment listing must not be called when hasAttachments is False.
    assert all(c[0] != "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS" for c in client.calls)


def test_list_changes_paginates_messages(tmp_path):
    client = FakeClient({
        "OUTLOOK_LIST_MAIL_FOLDER_MESSAGES": [
            {"value": [{"id": "m1", "lastModifiedDateTime": "2026-05-20T00:00:00Z",
                        "hasAttachments": True, "webLink": "u1"}],
             "@odata.nextLink": "skip50"},
            {"value": [{"id": "m2", "lastModifiedDateTime": "2026-05-21T00:00:00Z",
                        "hasAttachments": True, "webLink": "u2"}],
             "@odata.nextLink": None},
        ],
        "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS": [
            {"value": [{"id": "a1", "name": "x.pdf", "contentType": "application/pdf", "size": 1}]},
            {"value": [{"id": "a1", "name": "y.pdf", "contentType": "application/pdf", "size": 1}]},
        ],
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    events = list(conn.list_changes("acct", since=None))
    assert {e.doc_id for e in events} == {"m1:a1", "m2:a1"}
    msg_calls = [c for c in client.calls if c[0] == "OUTLOOK_LIST_MAIL_FOLDER_MESSAGES"]
    assert msg_calls[1][1].get("skip") == "skip50"


def test_fetch_content_decodes_contentbytes(tmp_path):
    payload = b"%PDF outlook"
    client = FakeClient({
        "OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT": {
            "name": "x.pdf", "contentType": "application/pdf",
            "contentBytes": base64.b64encode(payload).decode(),
        }
    })
    conn = OutlookConnector(client=client, connected_accounts={"acct": "ca_1"},
                            state_dir=tmp_path)
    raw = conn.fetch_content("acct", "m1:a1")
    assert isinstance(raw, RawDoc)
    assert raw.content == payload and raw.mime == "application/pdf"
    assert raw.source == "outlook" and raw.doc_id == "m1:a1"
    assert client.calls[0][1] == {"message_id": "m1", "attachment_id": "a1"}


def test_unknown_account_raises_auth(tmp_path):
    from rag.connectors import ConnectorAuthError
    conn = OutlookConnector(client=FakeClient({}), connected_accounts={},
                            state_dir=tmp_path)
    with pytest.raises(ConnectorAuthError):
        list(conn.list_changes("nope", since=None))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_outlook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.connectors.outlook'`.

- [ ] **Step 3: Implement `src/rag/connectors/outlook.py`**

```python
"""Outlook attachments connector (Composio transport, Microsoft Graph shapes).

Indexes attachments, not bodies. doc_id = "{message_id}:{attachment_id}".
list_changes  -> OUTLOOK_LIST_MAIL_FOLDER_MESSAGES (paginated) then, per message
                 with attachments, OUTLOOK_LIST_OUTLOOK_ATTACHMENTS -> CloudItem
fetch_content -> OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT (base64 contentBytes) -> RawDoc
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Iterator

from rag.connectors._cloud import (
    CloudItem,
    ManifestStore,
    diff_items,
    resolve_connected_account,
)
from rag.connectors.composio_client import ComposioClient
from rag.types import ChangeEvent, RawDoc

_LIST_MESSAGES_ACTION = "OUTLOOK_LIST_MAIL_FOLDER_MESSAGES"
_LIST_ATTACHMENTS_ACTION = "OUTLOOK_LIST_OUTLOOK_ATTACHMENTS"
_DOWNLOAD_ACTION = "OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT"


def _parse_graph_time(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


class OutlookConnector:
    name = "outlook"

    def __init__(
        self,
        client: ComposioClient,
        connected_accounts: dict[str, str],
        state_dir,
        folder: str = "inbox",
        mime_filter: list[str] | None = None,
    ) -> None:
        self.client = client
        self.connected_accounts = connected_accounts
        self.manifest = ManifestStore(state_dir)
        self.folder = folder
        self.mime_filter = mime_filter

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ca = resolve_connected_account(self.connected_accounts, account)
        items = self._list_items(ca)
        yield from diff_items(self.name, account, items, since, self.manifest)

    def _list_items(self, connected_account_id: str) -> list[CloudItem]:
        items: list[CloudItem] = []
        skip: str | None = None
        while True:
            params: dict = {"folder": self.folder}
            if skip:
                params["skip"] = skip
            data = self.client.execute(
                _LIST_MESSAGES_ACTION, params, connected_account_id=connected_account_id
            )
            for msg in data.get("value", []):
                if not msg.get("hasAttachments"):
                    continue
                mid = msg["id"]
                mtime = _parse_graph_time(msg.get("lastModifiedDateTime"))
                url = msg.get("webLink", "")
                att_data = self.client.execute(
                    _LIST_ATTACHMENTS_ACTION,
                    {"message_id": mid},
                    connected_account_id=connected_account_id,
                )
                for att in att_data.get("value", []):
                    mime = att.get("contentType")
                    if self.mime_filter and mime not in self.mime_filter:
                        continue
                    items.append(
                        CloudItem(
                            doc_id=f"{mid}:{att['id']}",
                            source_url=url,
                            last_modified=mtime,
                            size_bytes=att.get("size"),
                            mime=mime,
                            filename=att.get("name", ""),
                        )
                    )
            skip = data.get("@odata.nextLink")
            if not skip:
                break
        return items

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ca = resolve_connected_account(self.connected_accounts, account)
        message_id, _, attachment_id = doc_id.partition(":")
        data = self.client.execute(
            _DOWNLOAD_ACTION,
            {"message_id": message_id, "attachment_id": attachment_id},
            connected_account_id=ca,
        )
        content = base64.b64decode(data["contentBytes"])
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=data.get("webLink", ""),
            mime=data.get("contentType", "application/octet-stream"),
            content=content,
            filename=data.get("name", doc_id),
            last_modified=datetime.utcnow(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_outlook.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/rag/connectors/outlook.py tests/unit/test_outlook.py
git commit -m "[OUTLOOK] Plan 2 Task 7: Outlook attachments connector via Composio

- doc_id = message_id:attachment_id; skips messages without attachments
- list: OUTLOOK_LIST_MAIL_FOLDER_MESSAGES paginated + OUTLOOK_LIST_OUTLOOK_ATTACHMENTS
- fetch: OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT base64 contentBytes -> RawDoc

Tests: 5 unit tests (fake Composio client)
Feature ID: P2-7"
```

---

## Task 8: CLI wiring — build cloud connectors from config

**Files:**
- Modify: `src/rag/serve/cli.py`
- Test: `tests/unit/test_cli_connectors.py`

Replace the localfs-only loop in the `sync` command with a reusable `build_connectors(cfg, state_dir)` helper that constructs every configured source's connector and its account list. Cloud sources need a `ComposioClient`; build a `ComposioSDKClient` from `cfg.composio` when any cloud source is present. The helper is unit-tested with a fake client injected, so no network/SDK is needed in tests.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_connectors.py`:

```python
from pathlib import Path

import pytest

from rag.config import (
    ComposioConfig,
    Config,
    EmbeddingConfig,
    ChunkingConfig,
    GdriveSource,
    GmailSource,
    LlmConfig,
    LocalfsSource,
    OcrConfig,
    OneDriveSource,
    OutlookSource,
    PathsConfig,
)
from rag.serve.cli import build_connectors


def _cfg(sources, composio=None, tmp_path=None) -> Config:
    return Config(
        sources=sources,
        embedding=EmbeddingConfig(model="m", ollama_url="http://x", batch_size=1),
        chunking=ChunkingConfig(),
        ocr=OcrConfig(),
        llm=LlmConfig(),
        paths=PathsConfig(
            bundle_dir=tmp_path / "b", dlq=tmp_path / "d.jsonl",
            metadata=tmp_path / "m.sqlite",
        ),
        composio=composio,
    )


def test_build_connectors_localfs_only(tmp_path):
    cfg = _cfg([LocalfsSource(kind="localfs", paths=[tmp_path / "docs"])], tmp_path=tmp_path)
    connectors, accounts = build_connectors(cfg, state_dir=tmp_path)
    assert set(connectors) == {"localfs"}
    assert accounts["localfs"] == ["default"]


def test_build_connectors_all_cloud_sources(tmp_path):
    fake_client = object()
    cfg = _cfg(
        [
            GdriveSource(kind="gdrive", accounts=["personal-jeremy"]),
            OneDriveSource(kind="onedrive", accounts=["work"]),
            GmailSource(kind="gmail", accounts=["me@x.com"]),
            OutlookSource(kind="outlook", accounts=["work-baldor"]),
        ],
        composio=ComposioConfig(connected_accounts={
            "personal-jeremy": "ca_1", "work": "ca_2",
            "me@x.com": "ca_3", "work-baldor": "ca_4",
        }),
        tmp_path=tmp_path,
    )
    connectors, accounts = build_connectors(cfg, state_dir=tmp_path, composio_client=fake_client)
    assert set(connectors) == {"gdrive", "onedrive", "gmail", "outlook"}
    assert accounts["gdrive"] == ["personal-jeremy"]
    assert accounts["outlook"] == ["work-baldor"]
    # Cloud connectors must have received the injected client.
    assert connectors["gdrive"].client is fake_client


def test_build_connectors_cloud_without_client_raises(tmp_path):
    cfg = _cfg([GdriveSource(kind="gdrive", accounts=["a"])],
               composio=ComposioConfig(connected_accounts={"a": "ca_1"}), tmp_path=tmp_path)
    with pytest.raises(ValueError, match="composio"):
        build_connectors(cfg, state_dir=tmp_path, composio_client=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_connectors.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_connectors'`.

- [ ] **Step 3: Implement the change in `src/rag/serve/cli.py`**

Add these imports near the existing connector import (after `from rag.connectors.localfs import LocalfsConnector`):

```python
from rag.config import (
    GdriveSource,
    GmailSource,
    OneDriveSource,
    OutlookSource,
)
from rag.connectors.gdrive import GdriveConnector
from rag.connectors.gmail import GmailConnector
from rag.connectors.onedrive import OneDriveConnector
from rag.connectors.outlook import OutlookConnector
```

Add this helper after the `_build` function:

```python
def build_connectors(cfg, state_dir: Path, composio_client=None):
    """Construct {name: connector} and {name: [account aliases]} from config.

    Cloud sources require a ComposioClient; pass one in (the sync command builds a
    real ComposioSDKClient). Raises ValueError if a cloud source is configured
    without a client.
    """
    connectors: dict = {}
    accounts: dict[str, list[str]] = {}

    def _need_client(kind: str):
        if composio_client is None:
            raise ValueError(
                f"source {kind!r} needs composio config, but no Composio client was built"
            )
        return composio_client

    for s in cfg.sources:
        ca_map = cfg.composio.connected_accounts if cfg.composio else {}
        if isinstance(s, LocalfsSource):
            connectors["localfs"] = LocalfsConnector(roots=s.paths)
            accounts["localfs"] = ["default"]
        elif isinstance(s, GdriveSource):
            connectors["gdrive"] = GdriveConnector(
                client=_need_client("gdrive"), connected_accounts=ca_map,
                state_dir=state_dir, include_paths=s.include_paths,
                mime_filter=s.mime_filter,
            )
            accounts["gdrive"] = s.accounts
        elif isinstance(s, OneDriveSource):
            connectors["onedrive"] = OneDriveConnector(
                client=_need_client("onedrive"), connected_accounts=ca_map,
                state_dir=state_dir, mime_filter=s.mime_filter,
            )
            accounts["onedrive"] = s.accounts
        elif isinstance(s, GmailSource):
            connectors["gmail"] = GmailConnector(
                client=_need_client("gmail"), connected_accounts=ca_map,
                state_dir=state_dir, mime_filter=s.mime_filter,
            )
            accounts["gmail"] = s.accounts
        elif isinstance(s, OutlookSource):
            connectors["outlook"] = OutlookConnector(
                client=_need_client("outlook"), connected_accounts=ca_map,
                state_dir=state_dir, mime_filter=s.mime_filter,
            )
            accounts["outlook"] = s.accounts

    return connectors, accounts
```

Then rewrite the body of the `sync` command. Replace the existing connector-building loop:

```python
    connectors: dict = {}
    accounts: dict[str, list[str]] = {}
    for s in cfg.sources:
        if isinstance(s, LocalfsSource):
            connectors["localfs"] = LocalfsConnector(roots=s.paths)
            accounts["localfs"] = ["default"]
        # Other source kinds are added in Plan 2.
```

with:

```python
    import os
    composio_client = None
    has_cloud = any(not isinstance(s, LocalfsSource) for s in cfg.sources)
    if has_cloud:
        if cfg.composio is None:
            raise click.ClickException("cloud sources configured but no 'composio' block in config")
        api_key = os.environ.get(cfg.composio.api_key_env)
        if not api_key:
            raise click.ClickException(
                f"environment variable {cfg.composio.api_key_env} is not set"
            )
        from rag.connectors.composio_client import ComposioSDKClient
        composio_client = ComposioSDKClient(api_key=api_key)
    connectors, accounts = build_connectors(
        cfg, state_dir=cfg.paths.bundle_dir, composio_client=composio_client
    )
```

Leave the rest of the `sync` command (the `SyncOrchestrator(...)` construction and below) unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_cli_connectors.py -v`
Expected: 3 passed.

- [ ] **Step 5: Confirm no Plan 1 regression**

Run: `pytest -q`
Expected: all unit tests pass (Plan 1 + Plan 2), 2 skipped (the existing OCR + integration skips). No failures.

- [ ] **Step 6: Commit**

```bash
git add src/rag/serve/cli.py tests/unit/test_cli_connectors.py
git commit -m "[CLI] Plan 2 Task 8: wire cloud connectors into sync

- build_connectors(cfg, state_dir, composio_client) constructs all source kinds
- sync builds a ComposioSDKClient from cfg.composio + api_key_env when cloud sources present
- clear ClickException when cloud configured without composio block / API key

Tests: 3 unit tests; full suite green
Feature ID: P2-8"
```

---

## Task 9: Integration test scaffold + docs + agent state

**Files:**
- Create: `tests/integration/test_cloud_connectors.py`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `.agent/progress.md`
- Modify: `.agent/state.json`

The integration test is gated and skipped by default (no creds in CI). It documents the real end-to-end expectation and is the place to verify Composio response shapes against live actions. Docs/state updates record Plan 2 as shipped.

- [ ] **Step 1: Write the gated integration test**

`tests/integration/test_cloud_connectors.py`:

```python
"""Live cloud-connector checks. Skipped unless RAG_INTEGRATION=1 and Composio creds exist.

This is the place to confirm real Composio response shapes (field names like
content_b64 / contentBytes / data, pagination tokens). If a live shape differs
from the unit-test fakes, adjust the connector's parsing in one place and update
the corresponding unit test.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_RUN = os.environ.get("RAG_INTEGRATION") == "1"
_KEY = os.environ.get("COMPOSIO_API_KEY")
_GDRIVE_CA = os.environ.get("RAG_TEST_GDRIVE_CA")


@pytest.mark.skipif(
    not (_RUN and _KEY and _GDRIVE_CA),
    reason="needs RAG_INTEGRATION=1, COMPOSIO_API_KEY, RAG_TEST_GDRIVE_CA",
)
def test_gdrive_list_and_fetch_roundtrip(tmp_path):
    from rag.connectors.composio_client import ComposioSDKClient
    from rag.connectors.gdrive import GdriveConnector

    client = ComposioSDKClient(api_key=_KEY)
    conn = GdriveConnector(
        client=client, connected_accounts={"test": _GDRIVE_CA}, state_dir=tmp_path
    )
    events = list(conn.list_changes("test", since=None))
    assert events, "expected at least one file in the test Drive folder"

    upserts = [e for e in events if e.operation == "upsert"]
    assert upserts
    raw = conn.fetch_content("test", upserts[0].doc_id)
    assert raw.content, "fetched document had no bytes"
    assert raw.source == "gdrive"
```

- [ ] **Step 2: Run it to confirm it is collected and skipped**

Run: `pytest tests/integration/test_cloud_connectors.py -v`
Expected: 1 skipped (reason mentions RAG_INTEGRATION). No errors, no failures.

- [ ] **Step 3: Update `README.md`**

Under the "Status" or sources section, add a line noting cloud connectors. Find the Phase/Status text and add:

```markdown
Phase 2 (cloud connectors) shipped: Google Drive, OneDrive, Gmail attachments,
and Outlook attachments are available via Composio. Configure them with a
`composio:` block in `config.yaml` (see `config.example.yaml`) and run `rag sync`.
```

- [ ] **Step 4: Update `docs/ARCHITECTURE.md`**

Add a short subsection under the connectors/extension-points area:

```markdown
### Cloud connectors (Plan 2)

`gdrive`, `onedrive`, `gmail`, `outlook` implement the same `Connector` protocol as
`localfs`. They share `connectors/_cloud.py` (CloudItem, ManifestStore, diff_items,
resolve_connected_account) and reach their sources through a `ComposioClient`
(`connectors/composio_client.py`). The real binding is `ComposioSDKClient` (lazy
import of the `composio` package); unit tests inject a fake client. Delete detection
uses a per-(source, account) JSON manifest in the bundle dir, mirroring `localfs`.
Account aliases map to Composio connected-account IDs via the `composio` config block.
Email connectors index attachments only, with `doc_id = "{message_id}:{attachment_id}"`.
```

- [ ] **Step 5: Update `.agent/progress.md`**

Append:

```markdown

## 2026-05-29 — Plan 2 (cloud connectors) complete
- Composio-backed connectors shipped: gdrive, onedrive, gmail, outlook.
- Shared cloud helpers (_cloud.py) + ComposioClient transport interface.
- Config gained optional `composio` block (alias -> connected-account id map).
- CLI `sync` builds cloud connectors when configured; localfs-only configs unchanged.
- Unit tests hermetic (fake Composio client); integration tier gated by RAG_INTEGRATION=1.
- Next: Plan 3 — MCP server (rag.serve.mcp) exposing search_docs/get_doc/list_sources/force_sync.
```

- [ ] **Step 6: Update `.agent/state.json`**

Set its contents to:

```json
{
  "working_directory": "C:\\Users\\jswil\\repos\\super-rag-gdrive-onedrive",
  "platform": "Cowork on Windows",
  "model": "claude-opus-4-8",
  "current_plan": "docs/superpowers/plans/2026-05-29-rag-cloud-connectors-plan.md",
  "current_task": "complete",
  "git": {"branch": "main", "last_commit": "see git log"},
  "build_status": "passing",
  "test_status": "passing (unit; integration gated by RAG_INTEGRATION=1)",
  "connections": ["ollama (local)", "claude-cli (local)", "composio (cloud connectors)"],
  "handoff_notes": "Plan 2 complete: gdrive/onedrive/gmail/outlook connectors via Composio. Next: Plan 3 (MCP server)."
}
```

- [ ] **Step 7: Run the full suite one more time**

Run: `pytest -q`
Expected: all unit tests pass; skips are the OCR fixture, the Plan 1 e2e integration, and the new cloud integration test. No failures.

- [ ] **Step 8: Commit**

```bash
git add tests/integration/test_cloud_connectors.py README.md docs/ARCHITECTURE.md .agent/progress.md .agent/state.json
git commit -m "[E2E+DOCS] Plan 2 Task 9: gated cloud integration test + docs/state

- tests/integration/test_cloud_connectors.py (skipped without RAG_INTEGRATION + creds)
- README + ARCHITECTURE document the cloud connectors and composio config
- .agent progress/state mark Plan 2 complete

Tests: full suite green (integration skipped by default)
Feature ID: P2-9"
```

---

## Self-Review (against spec section 4.1 + 5 + 6)

- **Spec §4.1 (one module per source, Connector protocol):** Tasks 4–7 implement gdrive/onedrive/gmail/outlook against the existing protocol. ✓
- **Spec §4.1 (Composio is auth + transport; multi-account via alias):** Task 2 client + Task 1 `connected_accounts` alias map + `resolve_connected_account`. ✓
- **Spec §5.2 (deletions flow through):** `diff_items` emits delete events; orchestrator already calls `mark_deleted` + `index.delete_by_doc_id`. ✓
- **Spec §6 (per-source auth isolation):** connectors raise `ConnectorAuthError`; orchestrator already catches per-source. ✓
- **Spec §6 (rate limits):** `unwrap_response` raises `ConnectorRateLimitError`. (Retry/backoff orchestration remains as in Plan 1; not expanded here.) ✓
- **Spec §7 (unit hermetic, integration gated):** all connector unit tests use a fake client; Task 9 integration test gated by `RAG_INTEGRATION=1`. ✓
- **Deferred by design (noted in Non-Goals):** token-based deltas, MCP server (Plan 3), bundle sync (Plan 4), reranker/eval changes.

**Known integration risk (flagged, not a unit-test gap):** exact Composio response field names (`content_b64` vs `data` vs `contentBytes`, pagination token keys) must be confirmed against live actions in Task 9; each connector isolates parsing to one method so a shape fix is localized.
