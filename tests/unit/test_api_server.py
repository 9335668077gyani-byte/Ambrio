# tests/unit/test_api_server.py
"""
Unit tests for ambrio.api — REST endpoints and Pydantic models.
The WebSocket endpoint requires a fully initialised SessionManager (DB +
ChromaStore) so it is NOT tested here; that belongs in integration tests.

Strategy: we build a *minimal* FastAPI app from the route functions themselves
(bypassing the lifespan context manager) so the tests never touch the DB or
ChromaStore.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: a lightweight FastAPI app that wires up the two REST routes
# without triggering the lifespan startup (no DB, no Chroma).
# ---------------------------------------------------------------------------

@pytest.fixture()
def rest_client():
    """Return a TestClient backed by a bare FastAPI app (no lifespan)."""
    import ambrio.api.server as srv_mod

    bare_app = FastAPI(title="Ambrio-test")

    # Re-register the route functions on the bare app
    @bare_app.get("/health")
    async def health():
        from ambrio.api.models import HealthResponse
        return HealthResponse(status="ok", version=srv_mod.VERSION)

    @bare_app.get("/sessions")
    async def list_sessions():
        if not srv_mod._session_manager:
            return []
        return srv_mod._session_manager.list_session_ids()  # Fix 4 — public API

    with TestClient(bare_app) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests — /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_ok(self, rest_client):
        response = rest_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "4.0.0"

    def test_health_content_type_json(self, rest_client):
        response = rest_client.get("/health")
        assert "application/json" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Tests — /sessions
# ---------------------------------------------------------------------------

class TestSessionsEndpoint:
    def test_sessions_returns_empty_when_no_manager(self, rest_client):
        """When _session_manager is None, /sessions returns []."""
        # Fix 7 — use patch() instead of manual global mutation
        with patch("ambrio.api.server._session_manager", None):
            response = rest_client.get("/sessions")

        assert response.status_code == 200
        assert response.json() == []

    def test_sessions_returns_session_ids(self, rest_client):
        """When a mock session manager exists, /sessions returns its keys."""
        mock_sm = MagicMock()
        mock_sm.list_session_ids.return_value = ["abc123", "def456"]  # Fix 4 + Fix 7
        # Fix 7 — use patch() instead of manual global mutation
        with patch("ambrio.api.server._session_manager", mock_sm):
            response = rest_client.get("/sessions")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert set(body) == {"abc123", "def456"}


# ---------------------------------------------------------------------------
# Tests — Pydantic models
# ---------------------------------------------------------------------------

class TestModels:
    def test_chat_done_model_dump(self):
        from ambrio.api.models import ChatDone
        done = ChatDone(model="multi-agent", tokens=42, elapsed=1.5)
        d = done.model_dump()
        assert d["type"] == "done"
        assert d["model"] == "multi-agent"
        assert d["tokens"] == 42
        assert d["elapsed"] == 1.5
        assert d["tool"] is None

    def test_error_msg_model_dump(self):
        from ambrio.api.models import ErrorMsg
        err = ErrorMsg(message="something failed")
        d = err.model_dump()
        assert d["type"] == "error"
        assert d["message"] == "something failed"

    def test_health_response_model(self):
        from ambrio.api.models import HealthResponse
        h = HealthResponse(status="ok", version="4.0.0")
        assert h.status == "ok"
        assert h.version == "4.0.0"

    def test_chat_request_optional_session(self):
        from ambrio.api.models import ChatRequest
        req = ChatRequest(content="hello")
        assert req.content == "hello"
        assert req.session_id is None

    def test_chat_request_with_session(self):
        from ambrio.api.models import ChatRequest
        req = ChatRequest(content="hi", session_id="sess-001")
        assert req.session_id == "sess-001"

    def test_chat_token_defaults(self):
        from ambrio.api.models import ChatToken
        tok = ChatToken(data="hello")
        assert tok.type == "token"
        assert tok.data == "hello"


# ---------------------------------------------------------------------------
# Tests — VERSION constant
# ---------------------------------------------------------------------------

class TestVersionConstant:
    def test_version_constant_is_string(self):
        import ambrio.api.server as srv_mod
        assert isinstance(srv_mod.VERSION, str)
        assert srv_mod.VERSION == "4.0.0"
