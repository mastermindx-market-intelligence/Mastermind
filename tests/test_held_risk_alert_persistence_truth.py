from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from portfolio import held_risk_alerts as hra
    monkeypatch.setattr(hra, "_ALERTS_LOG_PATH", tmp_path / "alerts.jsonl")
    monkeypatch.setattr(hra, "_ALERT_STATE_PATH", tmp_path / "alert_state.json")
    return hra


def _record(alert_id="pfolio:AAPL:monitor:2026-09-18:ma"):
    return {
        "alert_id": alert_id,
        "ticker": "AAPL",
        "type": "monitor",
        "headline": "AAPL monitor",
        "ts": "2026-09-18",
        "lanes": ["macro_sensitivity"],
    }


def _state(role, lane_state="ok"):
    return {
        "positions": [{
            "position_id": "aapl",
            "ticker": "AAPL",
            "role": role,
            "lanes": {
                "macro_sensitivity": {
                    "state": lane_state,
                    "reasons": ["test"],
                }
            },
        }]
    }


def test_corrupt_alert_state_is_failed_evidence_not_reset(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    raw = "{broken secret token=do-not-return\n"
    hra._ALERT_STATE_PATH.write_text(raw)
    monkeypatch.setattr(hra, "_send_discord", lambda *_args, **_kwargs: None)

    with pytest.raises(Exception):
        hra.run_alerts(
            _state("ok"),
            _state("monitor", "elevated"),
            today=date(2026, 9, 18),
        )

    assert hra._ALERT_STATE_PATH.read_text() == raw
    assert not hra._ALERTS_LOG_PATH.exists()


def test_corrupt_alert_log_is_failed_evidence_not_extended(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    raw = json.dumps(_record("old")) + "\n{broken\n"
    hra._ALERTS_LOG_PATH.write_text(raw)

    with pytest.raises(Exception):
        hra._append_alert(_record("new"))

    assert hra._ALERTS_LOG_PATH.read_text() == raw


def test_exact_id_dedup_does_not_use_raw_substring_search(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    target = "pfolio:AAPL:monitor:2026-09-18:ma"
    prior = _record("different-id")
    prior["headline"] = f"diagnostic mentions {target} but is not that alert"
    hra._ALERTS_LOG_PATH.write_text(json.dumps(prior) + "\n")

    assert hra._append_alert(_record(target)) is True

    rows = [
        json.loads(line)
        for line in hra._ALERTS_LOG_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert [row["alert_id"] for row in rows] == ["different-id", target]


def test_alert_replace_failure_preserves_prior_complete_bytes(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    prior = json.dumps(_record("old")) + "\n"
    hra._ALERTS_LOG_PATH.write_text(prior)
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == hra._ALERTS_LOG_PATH:
            raise OSError("secret /Users/private/alert token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        hra._append_alert(_record("new"))

    assert hra._ALERTS_LOG_PATH.read_text() == prior
    assert not list(tmp_path.glob(".*.tmp"))


def test_state_replace_failure_preserves_prior_complete_bytes(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    previous = {
        "as_of": "2026-09-17",
        "cooldown": {},
        "last_roles": {},
        "last_lanes": {},
    }
    hra._ALERT_STATE_PATH.write_text(json.dumps(previous))
    prior_bytes = hra._ALERT_STATE_PATH.read_text()
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == hra._ALERT_STATE_PATH:
            raise OSError("secret /Users/private/state token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        hra._save_alert_state({"as_of": "2026-09-18", "cooldown": {}})

    assert hra._ALERT_STATE_PATH.read_text() == prior_bytes
    assert not list(tmp_path.glob(".*.tmp"))


def test_governor_lock_serializes_independent_processes(tmp_path, monkeypatch):
    import multiprocessing as mp
    import time

    hra = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with hra._governor_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with hra._governor_lock():
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


def test_state_failure_after_alert_effect_is_retry_healable(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    real_replace = os.replace
    failed = {"done": False}

    def fail_state_once(src, dst):
        if Path(dst) == hra._ALERT_STATE_PATH and not failed["done"]:
            failed["done"] = True
            raise OSError("state publish unavailable")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_state_once)
    prev = _state("ok")
    new = _state("monitor", "elevated")

    with pytest.raises(OSError):
        hra.run_alerts(prev, new, today=date(2026, 9, 18))

    rows = [
        json.loads(line)
        for line in hra._ALERTS_LOG_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert len(sent) == 1

    fired = hra.run_alerts(prev, new, today=date(2026, 9, 18))
    assert fired == []

    rows2 = [
        json.loads(line)
        for line in hra._ALERTS_LOG_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows2) == 1
    assert len(sent) == 1

    state = json.loads(hra._ALERT_STATE_PATH.read_text())
    assert state["cooldown"]["AAPL"] == {
        "role": "monitor",
        "last_alert": "2026-09-18",
        "sessions_since": 0,
    }


def test_missing_state_and_log_remain_legitimate_first_run(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(hra, "_send_discord", lambda *_args, **_kwargs: None)

    fired = hra.run_alerts(
        _state("ok"),
        _state("monitor", "elevated"),
        today=date(2026, 9, 18),
    )

    assert len(fired) == 1
    assert hra._ALERTS_LOG_PATH.exists()
    assert hra._ALERT_STATE_PATH.exists()
