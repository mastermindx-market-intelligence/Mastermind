"""Hermetic admission, refusal, and observer tests for the existing M2 watchdog."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def wd():
    source = Path(__file__).resolve().parents[1] / "ops" / "runner_connectivity_watchdog.py"
    spec = importlib.util.spec_from_file_location("mmx_runner_watchdog_source_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


@pytest.fixture
def one(wd, tmp_path):
    return wd.RunnerSpec("mac-test-one", "actions.runner.test.one", tmp_path)


def test_launchctl_timeout_refuses_without_exception(wd, one):
    logs = []
    with patch.object(wd, "_run", side_effect=subprocess.TimeoutExpired(["launchctl"], 10)), \
         patch.object(wd, "log", side_effect=logs.append):
        assert wd.service_loaded(one) is None
    assert logs and logs[0].startswith("INDETERMINATE")
    assert "TimeoutExpired" in logs[0]


def test_launchctl_error_and_definite_loaded_states(wd, one):
    with patch.object(wd, "_run", side_effect=OSError("unavailable")):
        assert wd.service_loaded(one) is None
    with patch.object(wd, "_run", return_value=subprocess.CompletedProcess([], 0)):
        assert wd.service_loaded(one) is True
    with patch.object(wd, "_run", return_value=subprocess.CompletedProcess([], 1)):
        assert wd.service_loaded(one) is False


@pytest.mark.parametrize("github,worker,eligible", [
    ({"status": "offline", "busy": True}, False, False),
    ({"status": "offline", "busy": False}, True, False),
    ({"status": "offline", "busy": False}, False, True),
    ({"status": "online", "busy": False}, False, False),
])
def test_restart_admission_requires_authenticated_idle_and_no_worker(
    wd, one, github, worker, eligible
):
    rows = wd.restart_candidates(
        {one.name: github}, [one],
        loaded={one.name: True}, workers={one.name: worker},
    )
    assert rows == ([one] if eligible else [])


def test_unreadable_launchd_always_blocks_restart(wd, one):
    rows = wd.restart_candidates(
        {one.name: {"status": "offline", "busy": False}}, [one],
        loaded={one.name: None}, workers={one.name: False},
    )
    assert rows == []


def test_broker_log_reader_bounds_window_and_filenames(wd, one):
    logs = one.root / "_diag"
    logs.mkdir()
    (logs / "Runner_20261013-062000-utc.log").write_text(
        "[2026-10-13 05:00:00Z INFO BrokerMessageListener] "
        "Retriable exception: The HTTP request timed out after 00:01:40.\n"
        "[2026-10-13 06:10:00Z INFO BrokerMessageListener] "
        "Retriable exception: The HTTP request timed out after 00:01:40.\n"
        "[2026-10-13 06:10:38Z INFO JobDispatcher] "
        "Shutting down JobDispatcher. Make sure all WorkerDispatcher has finished.\n",
        encoding="utf-8",
    )
    now = datetime(2026, 10, 13, 6, 25, tzinfo=timezone.utc)
    assert wd.recent_broker_faults((one,), now=now) == (
        ["mac-test-one:poll_timeouts=1,self_shutdowns=1"], []
    )
    later = datetime(2026, 10, 13, 7, 10, tzinfo=timezone.utc)
    assert wd.recent_broker_faults((one,), now=later) == ([], [])


def test_unreadable_broker_log_is_indeterminate(wd, tmp_path):
    spec = wd.RunnerSpec("missing", "unused", tmp_path / "absent")
    assert wd.recent_broker_faults((spec,)) == ([], ["missing"])


@pytest.mark.parametrize("status,busy,worker,degraded", [
    ("offline", True, True, True),
    ("offline", False, True, True),
    ("online", True, True, False),
])
def test_busy_or_worker_risk_reports_without_restart(
    wd, one, status, busy, worker, degraded
):
    rows = {one.name: {"status": status, "busy": busy}}
    logs = []
    with patch.object(wd, "github_snapshot", return_value=rows), \
         patch.object(wd, "local_state", return_value=({one.name: True}, {one.name: worker})), \
         patch.object(wd, "recent_broker_faults", return_value=([], [])), \
         patch.object(wd, "kickstart", side_effect=AssertionError("forbidden restart")), \
         patch.object(wd, "log", side_effect=logs.append):
        assert wd.run_watchdog("irrelevant", (one,), confirm_seconds=0,
                               verify_seconds=0, dry_run=False) == 0
    assert any(s.startswith("DEGRADED offline runners") for s in logs) == degraded
    if degraded:
        assert not any(s.startswith("HEALTHY") for s in logs)


def test_double_confirmed_offline_idle_keeps_single_runner_restart_path(wd, one):
    rows = {one.name: {"status": "offline", "busy": False}}
    logs = []
    with patch.object(wd, "github_snapshot", side_effect=[rows, rows]), \
         patch.object(wd, "local_state", return_value=({one.name: True}, {one.name: False})), \
         patch.object(wd, "kickstart", side_effect=AssertionError("dry-run only")), \
         patch.object(wd, "log", side_effect=logs.append):
        assert wd.run_watchdog("irrelevant", (one,), confirm_seconds=0,
                               verify_seconds=0, dry_run=True) == 0
    assert sum("DRY-RUN would kickstart" in s for s in logs) == 1


def test_multiple_runner_outage_does_not_trigger_fleet_restart(wd, one, tmp_path):
    two = wd.RunnerSpec("mac-test-two", "actions.runner.test.two", tmp_path / "two")
    rows = {spec.name: {"status": "offline", "busy": False} for spec in (one, two)}
    flags = {name: True for name in rows}
    workers = {name: False for name in rows}
    logs = []
    with patch.object(wd, "github_snapshot", return_value=rows), \
         patch.object(wd, "local_state", return_value=(flags, workers)), \
         patch.object(wd, "kickstart", side_effect=AssertionError("no fleet restart")), \
         patch.object(wd, "log", side_effect=logs.append):
        assert wd.run_watchdog("irrelevant", (one, two),
                               confirm_seconds=0, verify_seconds=0, dry_run=False) == 0
    assert any("refusing fleet-wide restart" in s for s in logs)


def test_github_api_blindness_never_restarts(wd, one):
    with patch.object(wd, "github_snapshot", return_value=None), \
         patch.object(wd, "kickstart", side_effect=AssertionError("no restart")):
        assert wd.run_watchdog("irrelevant", (one,),
                               confirm_seconds=0, verify_seconds=0, dry_run=False) == 0


def test_broker_degraded_does_not_change_restart_admission(wd, one):
    rows = {one.name: {"status": "online", "busy": True}}
    logs = []
    with patch.object(wd, "github_snapshot", return_value=rows), \
         patch.object(wd, "local_state", return_value=({one.name: True}, {one.name: True})), \
         patch.object(wd, "recent_broker_faults", return_value=([f"{one.name}:poll_timeouts=2,self_shutdowns=0"], [])), \
         patch.object(wd, "kickstart", side_effect=AssertionError("no restart")), \
         patch.object(wd, "log", side_effect=logs.append):
        assert wd.run_watchdog("irrelevant", (one,), confirm_seconds=0,
                               verify_seconds=0, dry_run=False) == 0
    assert any(s.startswith("DEGRADED recent broker listener faults:") for s in logs)
    assert not any(s.startswith("HEALTHY") for s in logs)
