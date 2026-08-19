"""The personal Supabase portfolio panel must never be reachable unauthenticated.

/api/pfolio/* takes NO caller identity: app/pfolio.py resolves the operator's UUID itself and
performs every read/write with the Supabase SERVICE-ROLE key. So "did the request reach the
handler" IS the security question — a handler that runs at all acts as the operator.

The gate used to key on ``serve_only()`` alone. That was only safe while the canonical instance was
localhost-bound and the public box was the read mirror. The VPS cutover inverted it: the public,
internet-reachable instance now runs MASTERMIND_SERVE_ONLY=0 with MASTERMIND_VPS_AUTHORITATIVE=1
(ops/mastermind-vps.service.d/authoritative.conf), so the serve-only branch is inert there and the
whole CRUD surface — GET/POST/PATCH/DELETE — was open to any network caller.

These tests pin the fixed boundary. Every rejection is additionally proven to be a rejection
BEFORE the handler: the Supabase readiness probe is never called and no HTTP request is issued.

No network, no Supabase, no LLM.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, pfolio


_PFOLIO_METHODS = (
    ("GET", "/api/pfolio/positions", None),
    ("POST", "/api/pfolio/positions", {"ticker": "AAPL", "shares": 1}),
    ("PATCH", "/api/pfolio/positions/abc-123", {"shares": 2}),
    ("DELETE", "/api/pfolio/positions/abc-123", None),
)


@pytest.fixture()
def tripwires(monkeypatch):
    """Record any attempt to reach the Supabase-touching layer.

    ``_sb_ready`` is the first statement of every CRUD handler, so a call to it means the handler
    ran. The httpx entrypoints catch any request that somehow bypassed it.
    """
    calls: dict[str, list] = {"handler": [], "http": []}

    def _spy_sb_ready() -> bool:
        calls["handler"].append("_sb_ready")
        return False

    monkeypatch.setattr(pfolio, "_sb_ready", _spy_sb_ready)

    import httpx

    def _make_http_tripwire(verb: str):
        def _tripwire(*args, **kwargs):
            calls["http"].append(verb)
            raise AssertionError(f"a rejected pfolio request issued httpx.{verb}")
        return _tripwire

    for verb in ("get", "post", "patch", "delete", "put", "request"):
        monkeypatch.setattr(httpx, verb, _make_http_tripwire(verb), raising=False)
    return calls


def _client(monkeypatch, *, serve_only=None, authoritative=None, token=None):
    """A throwaway app carrying the REAL pfolio router behind the REAL auth gate."""
    for name, value in (("MASTERMIND_SERVE_ONLY", serve_only),
                        ("MASTERMIND_VPS_AUTHORITATIVE", authoritative),
                        ("MASTERMIND_AUTH_TOKEN", token)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    # The panel must be unreachable on its own merits, never merely because Supabase is unconfigured.
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)

    app = FastAPI()
    app.include_router(pfolio.router)
    auth.install(app)          # added last => outermost, exactly as app/main.py wires it
    return TestClient(app, raise_server_exceptions=True)


def _call(client, method, path, body):
    return client.request(method, path, json=body) if body is not None else client.request(method, path)


# ---------------------------------------------------------------------------
# 1-5: authoritative VPS (SERVE_ONLY=0) — no credential reaches no handler
# ---------------------------------------------------------------------------

class TestAuthoritativeVpsBlocksUnauthenticatedCrud:
    """MASTERMIND_VPS_AUTHORITATIVE=1 + MASTERMIND_SERVE_ONLY=0 — the live public posture."""

    @pytest.mark.parametrize("method,path,body", _PFOLIO_METHODS)
    def test_unauthenticated_crud_cannot_reach_handler(self, monkeypatch, tripwires,
                                                       method, path, body):
        c = _client(monkeypatch, serve_only="0", authoritative="1", token="operator-secret")
        r = _call(c, method, path, body)

        assert r.status_code in (401, 403), (
            f"{method} {path} must be refused on the authoritative VPS without a bearer; "
            f"got {r.status_code} {r.text}"
        )
        assert r.json().get("error") == "operator_bearer_required"
        # 5) the rejection happened BEFORE any Supabase work
        assert tripwires["handler"] == [], f"{method} {path} reached the CRUD handler"
        assert tripwires["http"] == [], f"{method} {path} issued a Supabase HTTP request"

    @pytest.mark.parametrize("method,path,body", _PFOLIO_METHODS)
    def test_wrong_bearer_is_refused(self, monkeypatch, tripwires, method, path, body):
        c = _client(monkeypatch, serve_only="0", authoritative="1", token="operator-secret")
        headers = {"authorization": "Bearer not-the-secret"}
        r = (c.request(method, path, json=body, headers=headers) if body is not None
             else c.request(method, path, headers=headers))
        assert r.status_code in (401, 403)
        assert r.json().get("error") == "operator_bearer_required"
        assert tripwires["handler"] == []
        assert tripwires["http"] == []

    @pytest.mark.parametrize("method,path,body", _PFOLIO_METHODS)
    def test_no_token_configured_blocks_outright(self, monkeypatch, tripwires,
                                                 method, path, body):
        """Fail CLOSED, not open: an authoritative box whose secrets file failed to load has no
        credential to authenticate against, so the surface is disabled rather than exposed."""
        c = _client(monkeypatch, serve_only="0", authoritative="1", token=None)
        r = _call(c, method, path, body)

        assert r.status_code == 403
        assert r.json().get("error") == "pfolio_unauthenticated_surface_disabled"
        assert tripwires["handler"] == []
        assert tripwires["http"] == []

    def test_valid_bearer_reaches_the_handler(self, monkeypatch):
        """The operator credential still works — the panel is gated, not amputated."""
        c = _client(monkeypatch, serve_only="0", authoritative="1", token="operator-secret")
        r = c.get("/api/pfolio/positions",
                  headers={"authorization": "Bearer operator-secret"})
        assert r.status_code == 200
        # Supabase is deliberately unconfigured here, so the handler's own fail-soft answer proves
        # the request got through the gate.
        assert r.json() == {"ok": False, "error": "supabase_unavailable"}


# ---------------------------------------------------------------------------
# 6: local / non-authoritative dev box — intended behaviour preserved
# ---------------------------------------------------------------------------

class TestLocalDevBoxUnchanged:
    """Neither flag set: a developer box keeps the open panel it has always had."""

    @pytest.mark.parametrize("method,path,body", _PFOLIO_METHODS)
    def test_crud_reaches_handler_without_credential(self, monkeypatch, method, path, body):
        c = _client(monkeypatch, serve_only=None, authoritative=None, token=None)
        r = _call(c, method, path, body)
        assert r.status_code == 200, f"{method} {path} should pass the gate locally"
        assert r.json().get("error") == "supabase_unavailable", (
            "the handler must have run and returned its own fail-soft payload"
        )

    def test_open_even_when_a_bearer_token_is_configured(self, monkeypatch):
        """Configuring a token on a dev box gates operator POSTs, not the local pfolio panel."""
        c = _client(monkeypatch, serve_only=None, authoritative=None, token="dev-token")
        r = c.get("/api/pfolio/positions")
        assert r.status_code == 200
        assert r.json().get("error") == "supabase_unavailable"


# ---------------------------------------------------------------------------
# 7: serve-only read mirror — unchanged
# ---------------------------------------------------------------------------

class TestServeOnlyMirrorStillBlocked:
    @pytest.mark.parametrize("method,path,body", _PFOLIO_METHODS)
    def test_all_methods_403(self, monkeypatch, tripwires, method, path, body):
        c = _client(monkeypatch, serve_only="1", authoritative=None, token="operator-secret")
        r = _call(c, method, path, body)
        assert r.status_code == 403
        assert r.json().get("error") == "serve_only"
        assert tripwires["handler"] == []
        assert tripwires["http"] == []

    def test_even_a_valid_bearer_does_not_open_the_mirror(self, monkeypatch, tripwires):
        c = _client(monkeypatch, serve_only="1", authoritative=None, token="operator-secret")
        r = c.get("/api/pfolio/positions",
                  headers={"authorization": "Bearer operator-secret"})
        assert r.status_code == 403
        assert r.json().get("error") == "serve_only"
        assert tripwires["handler"] == []


# ---------------------------------------------------------------------------
# the alerts sub-route shares the prefix and must share the boundary
# ---------------------------------------------------------------------------

def test_alerts_route_is_covered_by_the_same_gate(monkeypatch):
    """/api/pfolio/alerts is on the protected prefix; it must not be an unguarded side door."""
    c = _client(monkeypatch, serve_only="0", authoritative="1", token="operator-secret")
    assert c.get("/api/pfolio/alerts").status_code in (401, 403)
    ok = c.get("/api/pfolio/alerts", headers={"authorization": "Bearer operator-secret"})
    assert ok.status_code == 200
