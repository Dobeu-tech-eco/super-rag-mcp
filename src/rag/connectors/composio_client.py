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
