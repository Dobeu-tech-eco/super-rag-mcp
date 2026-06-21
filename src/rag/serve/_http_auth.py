# src/rag/serve/_http_auth.py
"""Bearer-token auth for the HTTP (streamable-http) MCP transport.

A *pure-ASGI* middleware — deliberately NOT Starlette's ``BaseHTTPMiddleware``,
which buffers the response body and would break the streamable-HTTP / SSE stream.
Non-HTTP scopes (``lifespan``, ``websocket``) pass straight through; HTTP requests
must carry a matching ``Authorization: Bearer <token>`` header or get a 401.
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class BearerAuthMiddleware:
    """Reject HTTP requests lacking a matching ``Authorization: Bearer`` header."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        if not token:
            raise ValueError("Bearer token must be a non-empty string")
        self._app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"").decode("latin-1")
        if not hmac.compare_digest(provided, self._expected):
            await _send_401(send)
            return
        await self._app(scope, receive, send)


async def _send_401(send: Send) -> None:
    body = json.dumps({"error": "unauthorized"}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="super-rag"'),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
