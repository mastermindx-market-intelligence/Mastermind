"""/health must not claim "ok" while its own readiness fields say otherwise.

The handler computed ``scheduler_running`` / ``scheduled_runtime_expected`` /
``scheduled_runtime_ok`` and then opened the payload with a hardcoded ``"status": "ok"``. Its own
comment records that uptime probes check ``status == "ok"`` only — so a canonical instance whose
scheduler had died reported OK to simple monitoring while simultaneously publishing
``scheduled_runtime_ok: false``. scripts/deploy_code_to_vps.sh greps the readiness field directly
and was therefore protected; generic uptime monitoring was not.

Contract now:
  * /health  — LIVENESS + provenance. Always 200 while the process answers (the deploy probe uses
    ``curl -fsS`` and AGENTS.md requires HTTP 200), but ``status`` is honest: "ok" or "degraded".
  * /ready   — READINESS. 200 when ready, 503 when a runtime this instance is expected to run is
    missing. A serve-only mirror is ready WITHOUT a scheduler; that absence is intentional there.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class _StoppedScheduler:
    running = False


class _RunningScheduler:
    running = True


@pytest.fixture()
def health_client(monkeypatch):
    """The REAL /health and /ready handlers, without firing the startup hook."""
    import app.main as main_mod

    def _client(*, serve_only: bool, scheduler) -> TestClient:
        if serve_only:
            monkeypatch.setenv("MASTERMIND_SERVE_ONLY", "1")
        else:
            monkeypatch.delenv("MASTERMIND_SERVE_ONLY", raising=False)
        monkeypatch.setattr(main_mod.app.state, "scheduler", scheduler, raising=False)
        return TestClient(main_mod.app, raise_server_exceptions=True)

    return _client


# ---------------------------------------------------------------------------
# the reported defect
# ---------------------------------------------------------------------------

def test_status_is_not_ok_when_scheduled_runtime_is_not_ok(health_client):
    c = health_client(serve_only=False, scheduler=_StoppedScheduler())
    body = c.get("/health").json()

    assert body["scheduled_runtime_expected"] is True
    assert body["scheduled_runtime_ok"] is False
    assert body["status"] != "ok", (
        "a canonical instance with no running scheduler must not tell an uptime probe it is ok"
    )
    assert body["status"] == "degraded"


def test_status_is_ok_when_the_scheduler_is_running(health_client):
    c = health_client(serve_only=False, scheduler=_RunningScheduler())
    body = c.get("/health").json()
    assert body["scheduled_runtime_ok"] is True
    assert body["status"] == "ok"


def test_missing_scheduler_object_is_also_degraded(health_client):
    """A startup that never assigned app.state.scheduler is the same fault as a dead one."""
    c = health_client(serve_only=False, scheduler=None)
    body = c.get("/health").json()
    assert body["scheduler_running"] is False
    assert body["status"] == "degraded"


# ---------------------------------------------------------------------------
# serve-only: no scheduler is EXPECTED, so it is healthy and ready
# ---------------------------------------------------------------------------

def test_serve_only_is_healthy_without_a_scheduler(health_client):
    c = health_client(serve_only=True, scheduler=None)
    body = c.get("/health").json()
    assert body.get("serve_only") is True
    assert body["scheduled_runtime_expected"] is False
    assert body["scheduled_runtime_ok"] is True
    assert body["status"] == "ok", "scheduler absence is intentional on a read mirror"


def test_serve_only_is_ready_without_a_scheduler(health_client):
    c = health_client(serve_only=True, scheduler=None)
    r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


# ---------------------------------------------------------------------------
# /ready is the hard signal
# ---------------------------------------------------------------------------

def test_ready_is_503_when_the_scheduler_is_absent(health_client):
    c = health_client(serve_only=False, scheduler=_StoppedScheduler())
    r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["ready"] is False


def test_ready_is_200_when_the_scheduler_runs(health_client):
    c = health_client(serve_only=False, scheduler=_RunningScheduler())
    r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["ready"] is True


def test_ready_is_open_and_never_gated(health_client):
    """Probes carry no credential; /ready must be in the always-open path set."""
    from app import auth
    assert "/ready" in auth._OPEN_PATHS
    assert "/health" in auth._OPEN_PATHS


# ---------------------------------------------------------------------------
# the deployment probe's contract must keep working
# ---------------------------------------------------------------------------

def test_health_stays_http_200_in_every_state(health_client):
    """scripts/deploy_code_to_vps.sh fetches /health with `curl -fsS`, which FAILS on a non-2xx.
    Readiness therefore has to be expressed in the body (and /ready), not in /health's status code."""
    for serve_only, scheduler in ((False, _StoppedScheduler()), (False, _RunningScheduler()),
                                  (True, None), (False, None)):
        c = health_client(serve_only=serve_only, scheduler=scheduler)
        assert c.get("/health").status_code == 200


def test_health_still_exposes_the_fields_the_deploy_probe_greps(health_client):
    c = health_client(serve_only=False, scheduler=_RunningScheduler())
    body = c.get("/health").json()
    for field in ("reasoning_policy_ok", "scheduled_runtime_ok"):
        assert field in body, f"deploy probe greps {field!r} out of the /health body"


def test_health_leaks_no_filesystem_paths(health_client):
    c = health_client(serve_only=False, scheduler=_RunningScheduler())
    body = c.get("/health").json()
    for key, value in body.items():
        if isinstance(value, str):
            assert not value.startswith(("/", "\\")), f"/health leaks a path in {key}: {value!r}"
