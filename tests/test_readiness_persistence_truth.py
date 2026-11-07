from __future__ import annotations

import json
import os
import stat
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
    try:
        assert entered.wait(timeout=5)
        second.start()
        time.sleep(0.15)
        assert second.is_alive()
        release.set()
        first.join(timeout=5)
        second.join(timeout=5)

        assert first.exitcode == 0 and second.exitcode == 0
        assert bool(acquired_after_release.value)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                assert not process.is_alive()


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


def test_no_crossing_does_not_create_alert_or_state_files(tmp_path, monkeypatch):
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
    assert r._readiness_lock_path().is_file()


def test_corrupt_alert_history_makes_api_readiness_unavailable(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    from app import web

    r._ALERTS.write_text("{broken alert evidence\n", encoding="utf-8")
    response = web.api_readiness()
    payload = json.loads(response.body)

    assert payload["read_status"] == "unavailable"
    assert payload["alerts"] is None
    assert payload["error"] == "readiness_unavailable"


@pytest.mark.parametrize("raw", [b"\xff", b"[]\n", b'{"date": "2026-09-18"}\n'])
def test_unreadable_or_wrong_shaped_alerts_preserve_canonical_bytes(tmp_path, monkeypatch, raw):
    r = _wire(tmp_path, monkeypatch)
    r._ALERTS.write_bytes(raw)
    prior_state = '{"calibration_forge": true}'
    r._STATE.write_text(prior_state)

    with pytest.raises(Exception):
        r.alerts()
    result = r.check_and_record("2026-09-18")

    assert result == {
        "new": [], "flags": {"prediction_xsec": True},
        "pending_new": ["prediction_xsec"], "persistence_status": "unavailable",
        "error": "readiness_alert_ledger_unavailable",
    }
    assert r._ALERTS.read_bytes() == raw
    assert r._STATE.read_text() == prior_state


def test_dangling_alert_ledger_is_not_absent_or_replaced(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    missing = tmp_path / "missing-alerts.jsonl"
    r._ALERTS.symlink_to(missing)
    r._STATE.write_text('{"calibration_forge": true}')
    prior_state = r._STATE.read_bytes()

    with pytest.raises(FileNotFoundError):
        r.alerts()
    result = r.check_and_record("2026-09-18")

    assert result["new"] == []
    assert result["error"] == "readiness_alert_ledger_unavailable"
    assert r._ALERTS.is_symlink()
    assert r._ALERTS.readlink() == missing
    assert not missing.exists()
    assert r._STATE.read_bytes() == prior_state


def test_dangling_alert_ancestor_is_unavailable_not_missing(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    missing = tmp_path / "missing-store"
    linked = tmp_path / "linked-store"
    linked.symlink_to(missing, target_is_directory=True)
    monkeypatch.setattr(r, "_ALERTS", linked / "alerts.jsonl")

    with pytest.raises(OSError):
        r.alerts()

    assert linked.is_symlink()
    assert not missing.exists()


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requires non-root POSIX permissions")
def test_inaccessible_alert_target_preserves_link_state_and_history(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    target = hidden / "alerts.jsonl"
    prior = json.dumps(_alert("calibration_forge")) + "\n"
    target.write_text(prior)
    r._ALERTS.symlink_to(target)
    r._STATE.write_text('{"calibration_forge": true}')
    prior_state = r._STATE.read_bytes()
    mode = stat.S_IMODE(hidden.stat().st_mode)
    try:
        hidden.chmod(0)
        with pytest.raises(PermissionError):
            r.alerts()
        result = r.check_and_record("2026-09-18")
        assert result["new"] == []
        assert result["error"] == "readiness_alert_ledger_unavailable"
        assert r._ALERTS.is_symlink()
        assert r._ALERTS.readlink() == target
        assert r._STATE.read_bytes() == prior_state
    finally:
        hidden.chmod(mode)

    assert target.read_text() == prior
    assert r._ALERTS.is_symlink()


def test_alert_appearing_after_failed_read_is_not_fabricated_empty(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    prior = json.dumps(_alert("calibration_forge")) + "\n"
    real_read = Path.read_text
    reads = []

    def fail_then_publish(self, *args, **kwargs):
        if self == r._ALERTS:
            reads.append("alert")
            self.write_text(prior)
            raise FileNotFoundError("read did not observe the newly published ledger")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_then_publish)
    result = r.check_and_record("2026-09-18")

    assert reads == ["alert"]
    assert result["new"] == []
    assert result["error"] == "readiness_alert_ledger_unavailable"
    assert r._ALERTS.read_bytes() == prior.encode()
    assert not r._STATE.exists()


def test_failed_absence_probe_stays_unavailable(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    real_lstat = Path.lstat

    def fail_target(self, *args, **kwargs):
        if self == r._ALERTS:
            raise PermissionError("private absence probe unavailable")
        return real_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fail_target)
    result = r.check_and_record("2026-09-18")

    assert result["new"] == []
    assert result["error"] == "readiness_alert_ledger_unavailable"
    assert not r._ALERTS.exists()
    assert not r._STATE.exists()


@pytest.mark.parametrize("failure", ["mkdir", "open", "flock"])
def test_lock_entry_failure_returns_fixed_safe_result(tmp_path, monkeypatch, failure):
    r = _wire(tmp_path, monkeypatch)
    prior = json.dumps(_alert("calibration_forge")) + "\n"
    r._ALERTS.write_text(prior)
    r._STATE.write_text('{"calibration_forge": true}')
    state = r._STATE.read_bytes()
    if failure == "mkdir":
        original = Path.mkdir

        def fail(self, *args, **kwargs):
            if self == r._ALERTS.parent:
                raise PermissionError("secret private lock directory")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fail)
    elif failure == "open":
        original = Path.open

        def fail(self, *args, **kwargs):
            if self == r._readiness_lock_path():
                raise PermissionError("secret private lock file")
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fail)
    else:
        original = r.fcntl.flock

        def fail(fd, operation):
            if operation == r.fcntl.LOCK_EX:
                raise OSError("secret private lock acquisition")
            return original(fd, operation)

        monkeypatch.setattr(r.fcntl, "flock", fail)

    result = r.check_and_record("2026-09-18")

    assert result == {
        "new": [], "flags": {"prediction_xsec": True},
        "pending_new": ["prediction_xsec"], "persistence_status": "unavailable",
        "error": "readiness_lock_unavailable",
    }
    assert "secret" not in json.dumps(result)
    assert r._ALERTS.read_text() == prior
    assert r._STATE.read_bytes() == state


@pytest.mark.parametrize("failure", ["alert", "state"])
def test_parent_fsync_failure_preserves_visible_effect_and_deduplicates(
    tmp_path, monkeypatch, failure,
):
    r = _wire(tmp_path, monkeypatch)
    real_fsync = os.fsync
    directories = []

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directories.append("directory")
            target = 1 if failure == "alert" else 2
            if len(directories) == target:
                raise OSError("directory durability unconfirmed")
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_directory)
        first = r.check_and_record("2026-09-18")

    rows = r.alerts()
    assert len(rows) == 1 and rows[0]["flag"] == "prediction_xsec"
    if failure == "alert":
        assert first["new"] == []
        assert first["pending_new"] == ["prediction_xsec"]
        assert first["persistence_status"] == "unavailable"
        assert first["error"] == "readiness_alert_write_failed"
        assert not r._STATE.exists()
    else:
        assert first["new"] == ["prediction_xsec"]
        assert first["persistence_status"] == "partial"
        assert first["state_heal_pending"] is True
        assert first["error"] == "readiness_state_write_failed"
        assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}
    assert not list(tmp_path.glob(".*.tmp"))

    second = r.check_and_record("2026-09-19")
    assert second == {"new": [], "flags": {"prediction_xsec": True}}
    assert r.alerts() == rows
    assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}


def test_failed_replace_preserves_existing_alert_history_and_state(tmp_path, monkeypatch):
    r = _wire(tmp_path, monkeypatch)
    prior = json.dumps(_alert("calibration_forge")) + "\n"
    r._ALERTS.write_text(prior)
    r._STATE.write_text('{"calibration_forge": true}')
    prior_state = r._STATE.read_bytes()
    real_replace = os.replace

    def fail_target(src, dst):
        if Path(dst) == r._ALERTS:
            raise OSError("alert publish unavailable")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_target)
    result = r.check_and_record("2026-09-18")

    assert result["new"] == []
    assert result["pending_new"] == ["prediction_xsec"]
    assert result["error"] == "readiness_alert_write_failed"
    assert r._ALERTS.read_text() == prior
    assert r._STATE.read_bytes() == prior_state
    assert not list(tmp_path.glob(".*.tmp"))


def test_lock_cleanup_failure_does_not_reclassify_a_reached_publication(tmp_path, monkeypatch):
    from contextlib import contextmanager

    r = _wire(tmp_path, monkeypatch)

    @contextmanager
    def failed_cleanup():
        yield
        raise OSError("lock cleanup unconfirmed")

    monkeypatch.setattr(r, "_readiness_lock", failed_cleanup)
    with pytest.raises(OSError, match="lock cleanup unconfirmed"):
        r.check_and_record("2026-09-18")

    assert len(r.alerts()) == 1
    assert r.alerts()[0]["flag"] == "prediction_xsec"
    assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}


def test_concurrent_same_crossing_is_recorded_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    r = _wire(tmp_path, monkeypatch)
    ready = Barrier(4)

    def check():
        ready.wait(timeout=5)
        return r.check_and_record("2026-09-18")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(check) for _ in range(4)]
        results = [future.result(timeout=5) for future in futures]

    assert sum(result["new"] == ["prediction_xsec"] for result in results) == 1
    assert sum(result["new"] == [] for result in results) == 3
    assert len(r.alerts()) == 1
    assert json.loads(r._STATE.read_text()) == {"prediction_xsec": True}
