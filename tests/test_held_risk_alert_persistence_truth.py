from __future__ import annotations

import json
import os
import stat
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
    """The canonical lock is process-visible, not only protected by the local RLock."""
    import fcntl
    import multiprocessing as mp

    hra = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    attempting = ctx.Event()
    release = ctx.Event()
    contended = ctx.Value("b", False)
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with hra._governor_lock():
            entered.set()
            assert release.wait(timeout=5)

    def waiter():
        assert entered.wait(timeout=5)
        # Prove this independently scheduled process observed the actual held
        # OS lock before checking that the owning context waits for release.
        with hra._lock_path().open("a+", encoding="utf-8") as probe:
            try:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                contended.value = True
            else:
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        attempting.set()
        with hra._governor_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    try:
        first.start()
        assert entered.wait(timeout=5)
        second.start()
        assert attempting.wait(timeout=5), "waiter must reach the actual lock"
        assert bool(contended.value), "independent process must observe the held OS lock"
        assert second.is_alive()
        assert first.pid != second.pid and os.getpid() not in (first.pid, second.pid)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

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


def _governor_row(hra, *, role="monitor", day="2026-09-18", lanes=None):
    active = ["macro_sensitivity"] if lanes is None else sorted(lanes)
    return {
        "alert_id": hra._make_alert_id("AAPL", role, day, active),
        "source": "portfolio_desk", "ticker": "AAPL", "type": role,
        "position_id": "aapl", "lanes": active, "headline": "AAPL review evidence",
        "detail": "test", "reasons": ["test"], "ts": "1999-01-01T00:00:00+00:00",
    }


def _write_rows(hra, rows):
    hra._ALERTS_LOG_PATH.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _write_state(hra, *, cursor="2026-09-18", cooldown=None):
    state = {"as_of": cursor, "cooldown": cooldown or {}, "last_roles": {}, "last_lanes": {}}
    hra._ALERT_STATE_PATH.write_text(json.dumps(state))
    return state


def _cooldown(hra):
    return json.loads(hra._ALERT_STATE_PATH.read_text())["cooldown"].get("AAPL")


def _fail_state_once(hra, monkeypatch, boundary="replace"):
    real_replace, real_fsync = os.replace, os.fsync
    observed = {"failed": False, "last_replace": None}

    def replace(src, dst):
        if Path(dst) == hra._ALERT_STATE_PATH and boundary == "replace" and not observed["failed"]:
            observed["failed"] = True
            raise OSError("state publication unavailable")
        result = real_replace(src, dst)
        observed["last_replace"] = Path(dst)
        return result

    def fsync(fd):
        if (boundary == "fsync" and stat.S_ISDIR(os.fstat(fd).st_mode)
                and observed["last_replace"] == hra._ALERT_STATE_PATH and not observed["failed"]):
            observed["failed"] = True
            raise OSError("state directory durability unconfirmed")
        return real_fsync(fd)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "fsync", fsync)
    return observed


@pytest.mark.parametrize("boundary", ["replace", "fsync"])
def test_advanced_snapshot_retry_heals_without_resending(tmp_path, monkeypatch, boundary):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    observed = _fail_state_once(hra, monkeypatch, boundary)
    previous, current = _state("ok"), _state("monitor", "elevated")

    with pytest.raises(OSError):
        hra.run_alerts(previous, current, today=date(2026, 9, 18))

    assert observed["failed"] is True
    assert len(sent) == 1
    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    assert len(original_log.splitlines()) == 1
    # The actual caller has already advanced its risk snapshot after catching the failure.
    assert hra.run_alerts(current, current, today=date(2026, 9, 18)) == []
    assert _cooldown(hra) == {"role": "monitor", "last_alert": "2026-09-18", "sessions_since": 0}
    assert hra.run_alerts(current, current, today=date(2026, 9, 18)) == []
    assert _cooldown(hra)["sessions_since"] == 0
    assert hra.run_alerts(current, current, today=date(2026, 9, 19)) == []
    assert _cooldown(hra)["sessions_since"] == 1
    assert hra.run_alerts(current, current, today=date(2026, 9, 19)) == []
    assert _cooldown(hra)["sessions_since"] == 1
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert len(sent) == 1


@pytest.mark.parametrize("boundary", ["open", "fsync"])
def test_alert_directory_failure_retains_effect_and_retry_does_not_notify(tmp_path, monkeypatch, boundary):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    real_replace, real_open, real_fsync = os.replace, os.open, os.fsync
    observed = {"published": False, "failed": False}

    def replace(src, dst):
        result = real_replace(src, dst)
        if Path(dst) == hra._ALERTS_LOG_PATH:
            observed["published"] = True
        return result

    def open_directory(path, flags, *args, **kwargs):
        if (boundary == "open" and Path(path) == tmp_path
                and observed["published"] and not observed["failed"]):
            observed["failed"] = True
            raise OSError("alert directory open unavailable")
        return real_open(path, flags, *args, **kwargs)

    def fsync(fd):
        if (boundary == "fsync" and stat.S_ISDIR(os.fstat(fd).st_mode)
                and observed["published"] and not observed["failed"]):
            observed["failed"] = True
            raise OSError("alert directory durability unconfirmed")
        return real_fsync(fd)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "open", open_directory)
    monkeypatch.setattr(os, "fsync", fsync)
    current = _state("monitor", "elevated")

    with pytest.raises(OSError):
        hra.run_alerts(_state("ok"), current, today=date(2026, 9, 18))

    assert observed == {"published": True, "failed": True}
    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    assert len(original_log.splitlines()) == 1
    assert not hra._ALERT_STATE_PATH.exists()
    assert sent == []
    assert not list(tmp_path.glob(".*.tmp"))
    assert hra.run_alerts(current, current, today=date(2026, 9, 18)) == []
    assert _cooldown(hra) == {"role": "monitor", "last_alert": "2026-09-18", "sessions_since": 0}
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert sent == []


@pytest.mark.parametrize("target", ["state", "log"])
def test_dangling_canonical_alert_path_is_not_absent(tmp_path, monkeypatch, target):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    path = hra._ALERT_STATE_PATH if target == "state" else hra._ALERTS_LOG_PATH
    other = hra._ALERTS_LOG_PATH if target == "state" else hra._ALERT_STATE_PATH
    missing = tmp_path / "missing-canonical-target"
    path.symlink_to(missing)

    with pytest.raises(FileNotFoundError):
        hra.run_alerts(_state("ok"), _state("monitor", "elevated"), today=date(2026, 9, 18))

    assert path.is_symlink()
    assert path.readlink() == missing
    assert not missing.exists()
    assert not other.exists()
    assert sent == []


def test_duplicate_effect_preserves_existing_cooldown_counter(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    previous, current = _state("ok"), _state("monitor", "elevated")
    assert len(hra.run_alerts(previous, current, today=date(2026, 9, 18))) == 1
    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    # Existing callers/tests may advance a retained cooldown counter directly.
    _write_state(hra, cooldown={"AAPL": {
        "role": "monitor", "last_alert": "2026-09-18", "sessions_since": 9,
    }})

    assert hra.run_alerts(previous, current, today=date(2026, 9, 18)) == []

    assert _cooldown(hra)["sessions_since"] == 9
    assert hra.run_alerts(current, current, today=date(2026, 9, 19)) == []
    assert _cooldown(hra)["sessions_since"] == 10
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert len(sent) == 1


def test_newer_same_role_effect_recovers_after_expired_cooldown(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    previous = _state("monitor", "elevated")
    assert len(hra.run_alerts(_state("ok"), previous, today=date(2026, 9, 18))) == 1
    _write_state(hra, cooldown={"AAPL": {
        "role": "monitor", "last_alert": "2026-09-18", "sessions_since": 9,
    }})
    current = _state("monitor", "elevated")
    current["positions"][0]["lanes"]["price_trend"] = {"state": "elevated", "reasons": ["test"]}
    _fail_state_once(hra, monkeypatch)

    with pytest.raises(OSError):
        hra.run_alerts(previous, current, today=date(2026, 9, 28))

    assert len(sent) == 2
    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    assert len(original_log.splitlines()) == 2
    assert hra.run_alerts(current, current, today=date(2026, 9, 28)) == []
    assert _cooldown(hra) == {"role": "monitor", "last_alert": "2026-09-28", "sessions_since": 0}
    assert hra.run_alerts(current, current, today=date(2026, 9, 28)) == []
    assert _cooldown(hra)["sessions_since"] == 0
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert len(sent) == 2


@pytest.mark.parametrize("first_role,last_role", [("monitor", "review"), ("review", "monitor")])
def test_same_date_recovery_uses_recorded_order_not_current_role(tmp_path, monkeypatch, first_role, last_role):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    first = _state(first_role, "elevated")
    assert len(hra.run_alerts(_state("ok"), first, today=date(2026, 9, 18))) == 1
    _fail_state_once(hra, monkeypatch)

    with pytest.raises(OSError):
        hra.run_alerts(_state("ok"), _state(last_role, "elevated"), today=date(2026, 9, 18))

    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    assert len(original_log.splitlines()) == 2
    assert len(sent) == 2
    # An older current-position match cannot erase the later recorded effect.
    assert hra.run_alerts(first, first, today=date(2026, 9, 18)) == []
    assert _cooldown(hra) == {"role": last_role, "last_alert": "2026-09-18", "sessions_since": 0}
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert len(sent) == 2


def test_older_record_does_not_replace_newer_cooldown(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    _write_rows(hra, [_governor_row(hra)])
    newer = {"role": "review", "last_alert": "2026-09-19", "sessions_since": 3}
    _write_state(hra, cursor="2026-09-20", cooldown={"AAPL": newer})
    current = _state("monitor", "elevated")
    original_log = hra._ALERTS_LOG_PATH.read_bytes()

    assert hra.run_alerts(current, current, today=date(2026, 9, 20)) == []

    assert _cooldown(hra) == newer
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert sent == []


@pytest.mark.parametrize("field,value", [
    ("source", "another_owner"), ("position_id", "different-position"), ("lanes", ["macro_shift"]),
])
def test_same_id_different_identity_cannot_heal_current_effect(tmp_path, monkeypatch, field, value):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    record = _governor_row(hra)
    record[field] = value
    _write_rows(hra, [record])
    original_log = hra._ALERTS_LOG_PATH.read_bytes()
    current = _state("monitor", "elevated")

    with pytest.raises(ValueError, match="conflicting recorded identity"):
        hra.run_alerts(current, current, today=date(2026, 9, 18))

    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert not hra._ALERT_STATE_PATH.exists()
    assert sent == []


@pytest.mark.parametrize("cursor", ["2026-09-17", "2026-09-18"])
def test_delayed_recovery_counts_one_observed_session(tmp_path, monkeypatch, cursor):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    _write_rows(hra, [_governor_row(hra)])
    _write_state(hra, cursor=cursor)
    current = _state("monitor", "elevated")
    original_log = hra._ALERTS_LOG_PATH.read_bytes()

    assert hra.run_alerts(current, current, today=date(2026, 9, 21)) == []

    assert _cooldown(hra) == {"role": "monitor", "last_alert": "2026-09-18", "sessions_since": 1}
    assert hra.run_alerts(current, current, today=date(2026, 9, 21)) == []
    assert _cooldown(hra)["sessions_since"] == 1
    assert hra.run_alerts(current, current, today=date(2026, 9, 22)) == []
    assert _cooldown(hra)["sessions_since"] == 2
    assert hra._ALERTS_LOG_PATH.read_bytes() == original_log
    assert sent == []


@pytest.mark.parametrize("cursor", [None, "2026-09-19"])
def test_indeterminate_recovery_preserves_retained_evidence(tmp_path, monkeypatch, cursor):
    hra = _wire(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(hra, "_send_discord", lambda headline: sent.append(headline))
    _write_rows(hra, [_governor_row(hra)])
    if cursor is not None:
        _write_state(hra, cursor=cursor)
    prior_state = hra._ALERT_STATE_PATH.read_bytes() if hra._ALERT_STATE_PATH.exists() else None
    prior_log = hra._ALERTS_LOG_PATH.read_bytes()
    current = _state("monitor", "elevated")

    with pytest.raises(ValueError, match="recovery history is unavailable"):
        hra.run_alerts(current, current, today=date(2026, 9, 21))

    assert hra._ALERTS_LOG_PATH.read_bytes() == prior_log
    if prior_state is None:
        assert not hra._ALERT_STATE_PATH.exists()
    else:
        assert hra._ALERT_STATE_PATH.read_bytes() == prior_state
    assert sent == []


def test_same_date_unanchored_cooldown_is_not_overwritten(tmp_path, monkeypatch):
    hra = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(hra, "_send_discord", lambda *_args: pytest.fail("must not notify"))
    _write_rows(hra, [_governor_row(hra)])
    _write_state(hra, cooldown={"AAPL": {
        "role": "review", "last_alert": "2026-09-18", "sessions_since": 0,
    }})
    prior_state, prior_log = hra._ALERT_STATE_PATH.read_bytes(), hra._ALERTS_LOG_PATH.read_bytes()
    current = _state("monitor", "elevated")

    with pytest.raises(ValueError, match="same-date cooldown ordering is unavailable"):
        hra.run_alerts(current, current, today=date(2026, 9, 18))

    assert hra._ALERT_STATE_PATH.read_bytes() == prior_state
    assert hra._ALERTS_LOG_PATH.read_bytes() == prior_log


@pytest.mark.parametrize("invalid", [
    "cursor_rewind", "future_event", "bad_alert_date", "bad_cursor", "negative_counter", "boolean_counter",
])
def test_invalid_recovery_chronology_or_counter_fails_without_rewrite(tmp_path, monkeypatch, invalid):
    hra = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(hra, "_send_discord", lambda *_args: pytest.fail("must not notify"))
    row = _governor_row(hra, day="2026-09-19" if invalid == "future_event" else "2026-09-18")
    if invalid == "bad_alert_date":
        row["alert_id"] = row["alert_id"].replace("2026-09-18", "2026-02-30")
    _write_rows(hra, [row])
    cursor = "2026-09-19" if invalid == "cursor_rewind" else "" if invalid == "bad_cursor" else "2026-09-18"
    cooldown = {}
    if invalid in ("negative_counter", "boolean_counter"):
        cooldown["AAPL"] = {"role": "monitor", "last_alert": "2026-09-17",
                            "sessions_since": -1 if invalid == "negative_counter" else True}
    _write_state(hra, cursor=cursor, cooldown=cooldown)
    prior_state, prior_log = hra._ALERT_STATE_PATH.read_bytes(), hra._ALERTS_LOG_PATH.read_bytes()
    current = _state("monitor", "elevated")

    with pytest.raises(ValueError):
        hra.run_alerts(current, current, today=date(2026, 9, 18))

    assert hra._ALERT_STATE_PATH.read_bytes() == prior_state
    assert hra._ALERTS_LOG_PATH.read_bytes() == prior_log
