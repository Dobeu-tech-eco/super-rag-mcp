from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from rag.serve._http_auth import BearerAuthMiddleware


def _client(token: str = "secret") -> TestClient:
    async def ok(request):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/mcp", ok)])
    return TestClient(BearerAuthMiddleware(inner, token))


def test_missing_authorization_is_401():
    resp = _client().get("/mcp")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert resp.headers["www-authenticate"].startswith("Bearer")


def test_wrong_token_is_401():
    resp = _client().get("/mcp", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_correct_token_passes_through():
    resp = _client().get("/mcp", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
    assert resp.text == "ok"


def test_empty_token_rejected_at_construction():
    with pytest.raises(ValueError):
        BearerAuthMiddleware(lambda scope, receive, send: None, "")
