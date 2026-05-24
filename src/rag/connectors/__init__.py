"""Connector base — every source implements this."""
from __future__ import annotations
from datetime import datetime
from typing import Iterator, Protocol
from rag.types import ChangeEvent, RawDoc


class Connector(Protocol):
    """A source-of-documents implementation.

    Implementations MUST:
    - Make list_changes idempotent — calling it with the same `since` is safe.
    - Make fetch_content idempotent — same doc_id always returns equivalent content (modulo source changes).
    - Never raise on individual missing docs; instead, yield ChangeEvent(operation='delete').
    - Surface auth failures by raising ConnectorAuthError so the orchestrator can notify.
    """

    name: str  # e.g. "localfs", "gdrive"

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ...

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ...


class ConnectorError(Exception):
    """Base class for connector errors."""


class ConnectorAuthError(ConnectorError):
    """Source authentication expired or invalid."""


class ConnectorRateLimitError(ConnectorError):
    """Source rate-limited the request."""
