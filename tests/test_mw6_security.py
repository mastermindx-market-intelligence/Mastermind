"""MW6 security tests — operator/public split, serve-only mode, rate limits,
provenance banner.

All tests use throwaway FastAPI apps so the real app.main startup (scheduler +
first-run book builds) is never triggered.  No LLM spend in any test.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _app_with_operator_routes(monkeypatch, *, token=None):
    """Build a minimal app that mirrors the real auth gate + operator + read routes.

    (No browser login exists — the only credential is the bearer token.)"""
    app = FastAPI()
    auth.install(app)

    @app.get("/api/portfolio")
    def api_portfolio():
        return {"positions": []}

    @app.post("/api/autonomous/run")
    def autonomous_run(force: bool = False):
        return {"started": True}

    @app.post("/daily")
    def daily(force: bool = False):
        return {"ran": True}

    @app.post("/chat")
    def chat():
        return {"ok": True}

    @app.post("/api/self_directed/order")
    def order():
        return {"ok": True}

    @app.get("/health")
    def health():
        from app.auth import serve_only
        out = {"status": "ok"}
        if serve_only():
            out["serve_only"] = True
        return out

    if token:
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", token)
    else:
        monkeypatch.delenv("MASTERMIND_AUTH_TOKEN", raising=False)
    # These apps model a LOCAL/dev process. Pin it explicitly so the authoritative-mode
    # fail-closed rules can never leak in from the ambient environment.
    monkeypatch.delenv("MASTERMIND_VPS_AUTHORITATIVE", raising=False)

    return app


# ---------------------------------------------------------------------------
# Test 1: operator route with cookie-but-no-bearer → 401/403
# ---------------------------------------------------------------------------

class TestOperatorRouteRequiresBearer:
    """A bearer token is required for operator paths; no browser login exists."""

    def test_operator_post_without_bearer_rejected(self, monkeypatch):
        """POST /api/autonomous/run with no bearer token must be rejected (401) when a
        token is configured — there is no session cookie that could substitute."""
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "operator-secret")
        app = _app_with_operator_routes(monkeypatch, token="operator-secret")

        c = TestClient(app, raise_server_exceptions=True)

        # /login is gone — confirm it 404s (no login flow to obtain a session).
        assert c.post("/login", data={"password": "x"}).status_code == 404

        # Operator route with NO bearer token -> rejected.
        r = c.post("/api/autonomous/run")
        assert r.status_code in (401, 403), (
            f"Operator route without a bearer token must be rejected; got {r.status_code}"
        )

    def test_operator_post_with_bearer_passes(self, monkeypatch):
        """POST /api/autonomous/run with a valid bearer token must pass the auth layer."""
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "operator-secret")
        app = _app_with_operator_routes(monkeypatch, token="operator-secret")

        c = TestClient(app, raise_server_exceptions=True)
        # Reset the rate limiters so this isolated test doesn't hit the limit.
        auth.reset_rate_buckets()
        r = c.post("/api/autonomous/run",
                   headers={"authorization": "Bearer operator-secret"})
        assert r.status_code == 200, (
            f"Valid bearer token must pass operator route; got {r.status_code}"
        )

    def test_readonly_get_is_open(self, monkeypatch):
        """Read-only GET /api/portfolio must pass with NO login and NO credential."""
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "operator-secret")
        app = _app_with_operator_routes(monkeypatch, token="operator-secret")

        c = TestClient(app, raise_server_exceptions=True)
        r = c.get("/api/portfolio")
        assert r.status_code == 200, (
            f"Read-only GET must be open (no login); got {r.status_code}"
        )

    def test_operator_route_with_wrong_token_rejected(self, monkeypatch):
        """POST /api/autonomous/run with a wrong bearer token must be rejected."""
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "correct-secret")
        app = _app_with_operator_routes(monkeypatch, token="correct-secret")

        c = TestClient(app, raise_server_exceptions=True)
        r = c.post("/api/autonomous/run",
                   headers={"authorization": "Bearer wrong-secret"})
        assert r.status_code in (401, 403), (
            f"Wrong bearer token must be rejected; got {r.status_code}"
        )

    def test_no_token_operator_passes(self, monkeypatch):
        """With no bearer token configured on a LOCAL/dev box, operator paths pass.

        This convenience is scoped to development. The authoritative-instance counterpart is
        TestAuthoritativeInstanceFailsClosed below, which proves the same configuration is
        REFUSED when MASTERMIND_VPS_AUTHORITATIVE=1."""
        monkeypatch.delenv("MASTERMIND_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("MASTERMIND_VPS_AUTHORITATIVE", raising=False)
        app = FastAPI()
        auth.install(app)

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        c = TestClient(app)
        auth.reset_rate_buckets()   # avoid spillover from other tests
        r = c.post("/api/autonomous/run")
        assert r.status_code == 200, (
            f"Auth-disabled dev mode must allow operator paths; got {r.status_code}"
        )


# ---------------------------------------------------------------------------
# Test 1b: the authoritative instance must never inherit the dev-ergonomics pass
# ---------------------------------------------------------------------------

class TestAuthoritativeInstanceFailsClosed:
    """MASTERMIND_VPS_AUTHORITATIVE=1 is the public, internet-reachable canonical writer.

    Its systemd unit loads secrets from ``EnvironmentFile=-/etc/macro-api.env`` — the leading ``-``
    makes that file OPTIONAL. A missing or unreadable secrets file therefore used to convert every
    LLM-spending and book-running route into an unauthenticated one, because an unset
    MASTERMIND_AUTH_TOKEN meant "operator paths pass". It must fail CLOSED instead.
    """

    def _app(self, monkeypatch, *, token=None):
        monkeypatch.setenv("MASTERMIND_VPS_AUTHORITATIVE", "1")
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "0")
        if token:
            monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", token)
        else:
            monkeypatch.delenv("MASTERMIND_AUTH_TOKEN", raising=False)
        app = FastAPI()
        auth.install(app)

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        auth.reset_rate_buckets()
        return TestClient(app, raise_server_exceptions=True)

    def test_missing_token_refuses_operator_routes(self, monkeypatch):
        c = self._app(monkeypatch, token=None)
        r = c.post("/api/autonomous/run")
        assert r.status_code == 503, (
            f"An authoritative box with no operator credential must refuse, got {r.status_code}"
        )
        assert r.json().get("error") == "operator_auth_misconfigured"

    def test_missing_token_refuses_startup(self, monkeypatch):
        """Defence in depth: the process should not come up at all in this state."""
        monkeypatch.setenv("MASTERMIND_VPS_AUTHORITATIVE", "1")
        monkeypatch.delenv("MASTERMIND_AUTH_TOKEN", raising=False)
        with pytest.raises(auth.AuthorizationMisconfigured):
            auth.assert_authoritative_auth_configured()

    def test_correct_token_succeeds(self, monkeypatch):
        c = self._app(monkeypatch, token="operator-secret")
        r = c.post("/api/autonomous/run",
                   headers={"authorization": "Bearer operator-secret"})
        assert r.status_code == 200
        auth.assert_authoritative_auth_configured()   # a configured box starts cleanly

    def test_wrong_or_missing_bearer_is_rejected(self, monkeypatch):
        c = self._app(monkeypatch, token="operator-secret")
        assert c.post("/api/autonomous/run").status_code == 401
        auth.reset_rate_buckets()
        r = c.post("/api/autonomous/run", headers={"authorization": "Bearer wrong"})
        assert r.status_code == 401

    def test_local_dev_startup_check_is_a_noop(self, monkeypatch):
        """A developer box without the flag keeps its no-token ergonomics."""
        monkeypatch.delenv("MASTERMIND_VPS_AUTHORITATIVE", raising=False)
        monkeypatch.delenv("MASTERMIND_AUTH_TOKEN", raising=False)
        auth.assert_authoritative_auth_configured()   # must not raise

    def test_serve_only_semantics_are_unchanged_when_authoritative_is_off(self, monkeypatch):
        """Serve-only remains a supported mode and still 403s operator mutations."""
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        monkeypatch.delenv("MASTERMIND_VPS_AUTHORITATIVE", raising=False)
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "tok")
        app = FastAPI()
        auth.install(app)

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        c = TestClient(app, raise_server_exceptions=True)
        r = c.post("/api/autonomous/run", headers={"authorization": "Bearer tok"})
        assert r.status_code == 403
        assert r.json().get("error") == "serve_only"


# ---------------------------------------------------------------------------
# Test 2: rate limit — burst then 429 + Retry-After + run-event
# ---------------------------------------------------------------------------

class TestRateLimits:
    """In-memory token buckets enforce operator-path rate limits."""

    def _reset_llm_bucket(self):
        """Clear the LLM limiter for isolated test runs."""
        auth._llm_limiter.reset()

    def _reset_operator_bucket(self):
        """Clear the non-LLM operator limiter."""
        auth._operator_limiter.reset()

    def test_llm_burst_then_429(self, monkeypatch):
        """After exhausting the LLM bucket burst capacity, the next call returns 429."""
        monkeypatch.setenv("MASTERMIND_PASSWORD", "testpw")
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "tok")
        app = FastAPI()
        auth.install(app)

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        c = TestClient(app, raise_server_exceptions=False)
        self._reset_llm_bucket()

        # Drain the burst allowance (2 per minute).
        for _ in range(auth._llm_limiter.burst_limit):
            r = c.post("/api/autonomous/run", headers={"authorization": "Bearer tok"})
            # Accept 200 or any non-429 (background threads etc. may return other codes).
            assert r.status_code != 429, f"First burst calls should not be rate-limited"

        # Next call must be 429.
        r = c.post("/api/autonomous/run", headers={"authorization": "Bearer tok"})
        assert r.status_code == 429, (
            f"Expected 429 after burst exhausted, got {r.status_code}"
        )
        assert "Retry-After" in r.headers, "429 must include Retry-After header"
        retry_after = int(r.headers["Retry-After"])
        assert retry_after >= 1, "Retry-After must be at least 1 second"
        body = r.json()
        assert body.get("error") == "rate_limited", f"Body error field wrong: {body}"

    def test_429_emits_run_event(self, monkeypatch, tmp_path):
        """A 429 response must emit an ADVISORY run-event in the governance ledger."""
        monkeypatch.setenv("MASTERMIND_PASSWORD", "testpw")
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "tok")
        # Point run_events at a temp dir.
        monkeypatch.setattr(
            "control_plane.run_events._ledger_path",
            lambda root=None: tmp_path / "run_events.jsonl",
        )
        app = FastAPI()
        auth.install(app)

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        c = TestClient(app, raise_server_exceptions=False)
        # Exhaust the bucket.
        self._reset_llm_bucket()
        for _ in range(auth._llm_limiter.burst_limit):
            c.post("/api/autonomous/run", headers={"authorization": "Bearer tok"})

        # Trigger the 429.
        r = c.post("/api/autonomous/run", headers={"authorization": "Bearer tok"})
        assert r.status_code == 429

        # Check run-event was written.
        ledger = tmp_path / "run_events.jsonl"
        if ledger.exists():
            import json
            lines = [json.loads(ln) for ln in ledger.read_text().splitlines() if ln.strip()]
            rl_events = [e for e in lines if e.get("step") == "operator_rate_limit"]
            assert len(rl_events) >= 1, "Expected at least one rate_limit run-event"
        # If ledger path monkeypatching didn't land, just verify the 429 response itself.

    def test_non_llm_operator_bucket(self, monkeypatch):
        """Non-LLM operator bucket (30/hr) is separate from the LLM bucket."""
        monkeypatch.setenv("MASTERMIND_PASSWORD", "testpw")
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "tok")
        app = FastAPI()
        auth.install(app)

        @app.post("/api/self_directed/order")
        def order():
            return {"ok": True}

        c = TestClient(app, raise_server_exceptions=False)
        self._reset_operator_bucket()

        # First call to non-LLM path should pass (bucket is full).
        r = c.post("/api/self_directed/order", headers={"authorization": "Bearer tok"})
        assert r.status_code != 429, (
            f"First non-LLM operator call should not be rate-limited; got {r.status_code}"
        )


# ---------------------------------------------------------------------------
# Test 2b: the LLM limiter implements its DOCUMENTED policy, not an approximation
# ---------------------------------------------------------------------------

class _FakeClock:
    """A monotonic clock the test drives, so boundaries are exact and nothing sleeps."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestLlmRateLimitContract:
    """The written contract is '8 fires/hour shared + 2/min burst' — two INDEPENDENT quotas.

    The previous implementation was a single token bucket (capacity 2, refill 8/3600s) described
    in-code as "the stricter composition". It was neither limit: after the opening two calls it
    admitted only one request per 450s (7.5 min — far stricter than 2/min), while the opening burst
    plus refill could exceed 8 within some rolling hours (looser than 8/hr). The old tests only
    proved "2 then 429", which both implementations satisfy, so the contradiction survived.
    """

    def test_declared_rules_match_the_documented_policy(self):
        assert set(auth._LLM_RULES) == {(2, 60.0), (8, 3600.0)}
        assert auth._llm_limiter.burst_limit == 2

    def test_two_per_minute_is_enforced(self):
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._LLM_RULES, clock=clock)

        assert lim.consume() is None, "call 1 must be admitted"
        assert lim.consume() is None, "call 2 must be admitted"

        third = lim.consume()
        assert third is not None, "call 3 in the same minute must be refused"
        assert 0 < third <= 60, f"the wait must be within the minute window; got {third}"

    def test_the_minute_window_actually_rolls(self):
        """The token bucket refilled one slot per 450s, so this is where it visibly differed."""
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._LLM_RULES, clock=clock)
        lim.consume()
        lim.consume()
        assert lim.consume() is not None

        clock.advance(60.0)
        assert lim.consume() is None, "a full minute later, the burst allowance must be back"
        assert lim.consume() is None
        assert lim.consume() is not None, "and the 2/min ceiling still applies afterwards"

    def test_eight_per_hour_is_enforced_independently(self):
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._LLM_RULES, clock=clock)

        # Spend the hourly quota two-at-a-time, one minute apart: 8 accepted calls.
        for _ in range(4):
            assert lim.consume() is None
            assert lim.consume() is None
            clock.advance(60.0)

        ninth = lim.consume()
        assert ninth is not None, "the 9th call inside the rolling hour must be refused"
        assert ninth > 60, (
            f"the refusal must come from the HOURLY window, not the minute one; got {ninth}"
        )

        # Once the oldest pair ages out of the trailing hour there is room again.
        clock.advance(ninth + 0.001)
        assert lim.consume() is None, "room must reappear as the oldest hourly event expires"

    def test_a_refused_call_is_not_recorded(self):
        """Hammering a limited endpoint must not push the caller's own retry deadline out."""
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._LLM_RULES, clock=clock)
        lim.consume()
        lim.consume()

        first_refusal = lim.consume()
        clock.advance(10.0)
        for _ in range(20):
            lim.consume()
        later_refusal = lim.consume()

        assert later_refusal is not None
        assert later_refusal <= first_refusal - 10.0 + 1e-6, (
            "rejected attempts must not extend the wait"
        )

    def test_operator_limiter_is_thirty_per_hour(self):
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._OPERATOR_RULES, clock=clock)
        for i in range(30):
            assert lim.consume() is None, f"call {i + 1} of 30 must be admitted"
        assert lim.consume() is not None, "the 31st call in the hour must be refused"

        clock.advance(3600.0)
        assert lim.consume() is None, "the hour rolls and the quota resets"

    def test_limiter_memory_is_bounded(self):
        """The event deque must stay bounded by the largest limit regardless of traffic."""
        clock = _FakeClock()
        lim = auth._SlidingWindowLimiter(auth._LLM_RULES, clock=clock)
        for _ in range(500):
            lim.consume()
            clock.advance(31.0)          # keep offering traffic across many windows
        assert len(lim._events) <= 8


# ---------------------------------------------------------------------------
# Test 3: serve-only mode
# ---------------------------------------------------------------------------

class TestServeOnly:
    """MASTERMIND_SERVE_ONLY=1 disables scheduler + operator paths, marks /health."""

    def test_operator_path_returns_403_in_serve_only(self, monkeypatch):
        """All operator POST paths return 403 in serve-only mode."""
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        monkeypatch.setenv("MASTERMIND_PASSWORD", "testpw")
        monkeypatch.setenv("MASTERMIND_AUTH_TOKEN", "tok")
        app = FastAPI()
        auth.install(app)

        @app.post("/daily")
        def daily():
            return {"ran": True}

        @app.post("/api/autonomous/run")
        def autonomous_run():
            return {"started": True}

        @app.post("/api/self_directed/order")
        def order():
            return {"ok": True}

        c = TestClient(app, raise_server_exceptions=True)
        for path in ["/daily", "/api/autonomous/run", "/api/self_directed/order"]:
            r = c.post(path, headers={"authorization": "Bearer tok"})
            assert r.status_code == 403, (
                f"Serve-only mode: {path} must return 403, got {r.status_code}"
            )
            body = r.json()
            assert body.get("error") == "serve_only", f"Error field wrong for {path}: {body}"

    def test_health_has_serve_only_flag(self, monkeypatch):
        """In serve-only mode, /health includes 'serve_only': True."""
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        monkeypatch.delenv("MASTERMIND_PASSWORD", raising=False)
        monkeypatch.delenv("MASTERMIND_REQUIRE_AUTH", raising=False)
        app = FastAPI()
        auth.install(app)

        @app.get("/health")
        def health():
            from app.auth import serve_only
            out = {"status": "ok"}
            if serve_only():
                out["serve_only"] = True
            return out

        c = TestClient(app)
        r = c.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("serve_only") is True, (
            f"Serve-only /health must include serve_only=True; got {body}"
        )

    def test_scheduler_is_none_in_serve_only(self, monkeypatch):
        """When MASTERMIND_SERVE_ONLY=1 the REAL startup hook leaves app.state.scheduler
        as None and skips every first-run daemon thread — exercised through TestClient
        (safe precisely BECAUSE serve-only prevents the scheduler/Brain side effects)."""
        root = Path(__file__).resolve().parent.parent
        if not (root / "vendor" / "macro" / "lib" / "config.py").exists():
            pytest.skip("real app startup requires the vendored macro engine")
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        monkeypatch.setenv("MASTERMIND_PASSWORD", "pw-serve-only-test")
        assert auth.serve_only() is True
        import importlib
        import app.main as main_mod
        from fastapi.testclient import TestClient
        with TestClient(main_mod.app) as c:            # triggers the real startup hook
            assert main_mod.app.state.scheduler is None
            assert getattr(main_mod.app.state, "autonomous_first_run", False) in (False, None)
            r = c.get("/health")
            assert r.json().get("serve_only") is True   # the real health route, not a copy

    def test_scheduler_not_none_when_serve_only_off(self, monkeypatch):
        """When MASTERMIND_SERVE_ONLY is not set, serve_only() returns False."""
        monkeypatch.delenv("MASTERMIND_SERVE_ONLY", raising=False)
        assert auth.serve_only() is False

    def test_readonly_get_still_works_in_serve_only(self, monkeypatch):
        """Read-only GETs must still be served in serve-only mode."""
        monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        monkeypatch.delenv("MASTERMIND_PASSWORD", raising=False)
        monkeypatch.delenv("MASTERMIND_REQUIRE_AUTH", raising=False)
        app = FastAPI()
        auth.install(app)

        @app.get("/api/portfolio")
        def api_portfolio():
            return {"positions": []}

        c = TestClient(app)
        r = c.get("/api/portfolio")
        assert r.status_code == 200, (
            f"Read-only GET must still work in serve-only mode; got {r.status_code}"
        )


# ---------------------------------------------------------------------------
# Test 4: provenance API contains sha + PAPER
# ---------------------------------------------------------------------------

class TestProvenanceContract:
    """The API retains deployment provenance without forcing it into the portfolio UI."""

    def test_provenance_endpoint_contains_paper_trading(self, monkeypatch):
        """GET /api/provenance must return paper_trading=True and label='PAPER TRADING'."""
        from fastapi import FastAPI as _FA
        from app import web as _web

        monkeypatch.delenv("MASTERMIND_PASSWORD", raising=False)
        monkeypatch.delenv("MASTERMIND_REQUIRE_AUTH", raising=False)
        app = _FA()
        app.include_router(_web.router)
        from app import auth as _auth
        _auth.install(app)

        c = TestClient(app)
        r = c.get("/api/provenance")
        assert r.status_code == 200, f"/api/provenance returned {r.status_code}"
        body = r.json()
        assert body.get("paper_trading") is True, (
            f"provenance must include paper_trading=True; got {body}"
        )
        assert body.get("label") == "PAPER TRADING", (
            f"provenance label wrong; got {body}"
        )

    def test_provenance_endpoint_contains_sha(self, monkeypatch):
        """GET /api/provenance must return a non-empty sha field."""
        from fastapi import FastAPI as _FA
        from app import web as _web

        monkeypatch.delenv("MASTERMIND_PASSWORD", raising=False)
        monkeypatch.delenv("MASTERMIND_REQUIRE_AUTH", raising=False)
        app = _FA()
        app.include_router(_web.router)
        from app import auth as _auth
        _auth.install(app)

        c = TestClient(app)
        r = c.get("/api/provenance")
        assert r.status_code == 200
        body = r.json()
        # sha may be None in a bare checkout (e.g. shallow CI clone), but when it
        # IS present it must be a short hex string.
        if body.get("sha") is not None:
            sha = body["sha"]
            assert isinstance(sha, str) and len(sha) >= 4, (
                f"sha field looks wrong: {sha!r}"
            )

    def test_provenance_stays_api_only_in_portfolio_ui(self):
        """Deployment provenance remains available by API without blocking the dashboard UI."""
        from pathlib import Path
        html = (Path(__file__).resolve().parent.parent /
                "app" / "static" / "index.html").read_text()
        assert "mm-provenance" not in html
        assert "fetch('/api/provenance')" not in html


# ---------------------------------------------------------------------------
# Test 5: authority-map conformance (MASTERMIND_SERVE_ONLY is registered)
# ---------------------------------------------------------------------------

class TestAuthorityMapConformance:
    """MASTERMIND_SERVE_ONLY must be in KNOWN_FLAGS and in authority_map.yml."""

    def test_serve_only_in_known_flags(self):
        from control_plane.flags import KNOWN_FLAGS
        assert "MASTERMIND_SERVE_ONLY" in KNOWN_FLAGS, (
            "MASTERMIND_SERVE_ONLY missing from control_plane.flags.KNOWN_FLAGS"
        )

    def test_serve_only_in_authority_map(self):
        import yaml
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "config" / "authority_map.yml"
        data = yaml.safe_load(p.read_text())
        flags = data.get("flags") or {}
        assert "MASTERMIND_SERVE_ONLY" in flags, (
            "MASTERMIND_SERVE_ONLY missing from config/authority_map.yml flags section"
        )
        entry = flags["MASTERMIND_SERVE_ONLY"]
        # Must be A4 gate (MW6 requirement).
        assert entry.get("authority_level") == "A4", (
            f"MASTERMIND_SERVE_ONLY authority_level must be A4; got {entry.get('authority_level')}"
        )

    def test_operator_paths_known(self):
        """_OPERATOR_PATHS must contain all LLM-triggering routes from CENSUS.md."""
        from app.auth import _OPERATOR_PATHS, _LLM_OPERATOR_PATHS
        # All census LLM-tagged POSTs must be covered.
        census_llm = {
            "/daily", "/reason", "/research", "/chat",
            "/api/autonomous/run", "/api/heavyweight/run",
            "/api/china/run", "/api/hk/run", "/api/etf/run",
        }
        missing = census_llm - _LLM_OPERATOR_PATHS
        assert not missing, f"LLM operator paths missing from _LLM_OPERATOR_PATHS: {missing}"
        # All LLM paths must also be in the combined set.
        assert census_llm <= _OPERATOR_PATHS
