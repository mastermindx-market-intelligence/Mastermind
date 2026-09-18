from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from portfolio import readiness as r
    monkeypatch.setattr(r, "_STATE", tmp_path / "readiness_state.json")
    monkeypatch.setattr(r, "_ALERTS", tmp_path / "readiness_alerts.jsonl")
    monkeypatch.setattr(
        r,
        "status",
        lambda: {
            "flags": {"prediction_xsec": True},
            "detail": {"prediction_xsec": {"independent_clusters": 8, "need": 8}},
        },
    )
    return r


def _alert(flag="prediction_xsec", day="2026-09-18"):
    return {"date": day, "flag": flag, "message": "ready"}


def test_corrupt_alert_ledger_is_failed_evidence_not_empty(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    r._ALERTS.write_text(json.dumps(_alert()) + "\n{broken secret token=do-not-return\n")

    with pytest.raises(Exception):
        r.alerts()


def test_failed_alert_publish_does_not_claim_crossing(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    real_replace = os.replace

    def fail_alert_replace(src, dst):
        if Path(dst) == r._ALERTS:
            raise OSError("secret /Users/private/readiness token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_alert_replace)
    result = r.check_and_record("2026-09-18")

    assert result["new"] == []
    assert result["pending_new"] == ["prediction_xsec"]
    assert result["persistence_status"] == "unavailable"
    assert not r._ALERTS.exists()
    assert not r._STATE.exists()


def test_state_publish_failure_cannot_duplicate_durable_alert(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    real_replace = os.replace

    def fail_state_replace(src, dst):
        if Path(dst) == r._STATE:
            raise OSError("state projection unavailable")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_state_replace)
    first = r.check_and_record("2026-09-18")
    assert first["new"] == ["prediction_xsec"]
    assert first["persistence_status"] == "partial"
    assert first["state_heal_pending"] is True
    assert first["error"] == "readiness_state_write_failed"
    assert len(r.alerts()) == 1

    monkeypatch.setattr(os, "replace", real_replace)
    second = r.check_and_record("2026-09-19")
    assert second == {"new": [], "flags": {"prediction_xsec": True}}
    assert len(r.alerts()) == 1
    assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}


def test_corrupt_state_projection_heals_from_canonical_alert_ledger(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    r._ALERTS.write_text(json.dumps(_alert()) + "\n")
    r._STATE.write_text("{broken state projection\n")

    result = r.check_and_record("2026-09-19")

    assert result == {"new": [], "flags": {"prediction_xsec": True}}
    assert len(r.alerts()) == 1
    assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}


def test_readiness_mutation_lock_serializes_independent_processes(tmp_path, monkeypatch):
    import multiprocessing as mp
    import time

    r = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with r._readiness_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with r._readiness_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    time.sleep(0.15)
    assert second.is_alive()
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0 and second.exitcode == 0
    assert bool(acquired_after_release.value)


def test_successful_crossing_retains_existing_public_shape(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    result = r.check_and_record("2026-09-18")

    assert result == {"new": ["prediction_xsec"], "flags": {"prediction_xsec": True}}
    assert len(r.alerts()) == 1


def test_daily_build_surfaces_typed_readiness_persistence_errors():
    source = Path("bot/phase2.py").read_text(encoding="utf-8")
    assert 'if _rr.get("error"):' in source
    assert '"readiness persistence degraded"' in source
    assert "f\"error={_rr['error']}\"" in source


def test_no_crossing_does_not_create_persistence_files(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(
        r,
        "status",
        lambda: {"flags": {"prediction_xsec": False}, "detail": {}},
    )

    assert r.check_and_record("2026-09-18") == {
        "new": [], "flags": {"prediction_xsec": False}
    }
    assert not r._ALERTS.exists()
    assert not r._STATE.exists()


def test_corrupt_alert_history_makes_api_readiness_unavailable(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    from app import web

    r._ALERTS.write_text("{broken alert evidence\n", encoding="utf-8")
    response = web.api_readiness()
    payload = json.loads(response.body)

    assert payload["read_status"] == "unavailable"
    assert payload["alerts"] is None
    assert payload["error"] == "readiness_unavailable"
