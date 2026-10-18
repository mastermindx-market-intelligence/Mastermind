"""Acceptance failure cleanup must always reach the service stop.

S2 acceptance (release 08d7887335ee8aea11f0809e0660a5298c3ef68c) failed, then
``cleanup_after_failure`` -> ``_capture_failure_observability`` ->
``_control_request("status")`` hit the 90 s control-client timeout. The capture
catches only ``AcceptanceError``; ``subprocess.TimeoutExpired`` propagated and the
``service-control.sh stop`` below it never ran, leaving launchd respawning Control.

Inert: ``_run`` and ``os.kill`` are replaced; nothing is spawned or signalled.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.test_executive_acceptance_observability import _acceptance_stub, _completed, acceptance

HELPER_PID = 424242


def _cleanup_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, control_request):
    (tmp_path / "ops" / "executive_os").mkdir(parents=True)
    (tmp_path / "ops" / "executive_os" / "service-control.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    instance = _acceptance_stub(tmp_path)
    instance.persisted = {}
    instance._write_json = instance.persisted.__setitem__
    instance.helper_pid = HELPER_PID
    instance.services_started = True
    instance.release = tmp_path
    instance._pid_exists = lambda pid: pid == HELPER_PID
    instance._control_request = control_request
    runs: list[list] = []
    kills: list[tuple] = []

    def fake_run(argv, **kwargs):
        runs.append([str(part) for part in argv])
        return _completed(returncode=0)

    monkeypatch.setattr(acceptance, "_run", fake_run)
    monkeypatch.setattr(acceptance.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    return instance, runs, kills


def test_status_timeout_does_not_skip_helper_kill_or_service_stop(tmp_path, monkeypatch, capsys):
    def timed_out(command, *values, persist=None):
        assert command == "status"
        raise subprocess.TimeoutExpired(["control", "status"], 90.0, output=b"SECRET-OUTPUT")

    instance, runs, kills = _cleanup_instance(tmp_path, monkeypatch, timed_out)
    instance.cleanup_after_failure()
    assert kills == [(HELPER_PID, acceptance.signal.SIGKILL)]
    assert len(runs) == 1
    assert runs[0][0] == "/bin/bash"
    assert runs[0][1].endswith("ops/executive_os/service-control.sh")
    assert runs[0][-1] == "stop"
    assert instance.persisted == {}
    err = capsys.readouterr().err
    assert "failure observability capture raised TimeoutExpired" in err
    assert "SECRET-OUTPUT" not in err and "90" not in err  # type name only, no exception text


def test_unexpected_capture_error_does_not_skip_service_stop(tmp_path, monkeypatch, capsys):
    def broken(command, *values, persist=None):
        raise OSError("fixture: control socket vanished")

    instance, runs, kills = _cleanup_instance(tmp_path, monkeypatch, broken)
    instance.cleanup_after_failure()
    assert runs and runs[-1][-1] == "stop"
    assert kills == [(HELPER_PID, acceptance.signal.SIGKILL)]
    err = capsys.readouterr().err
    assert "raised OSError" in err and "socket vanished" not in err


def test_refused_status_still_stops_without_noise(tmp_path, monkeypatch, capsys):
    def refused(command, *values, persist=None):
        raise acceptance.AcceptanceError("control command status failed")

    instance, runs, kills = _cleanup_instance(tmp_path, monkeypatch, refused)
    instance.cleanup_after_failure()
    assert runs and runs[-1][-1] == "stop"
    assert capsys.readouterr().err == ""  # the existing AcceptanceError path is unchanged


def test_not_started_services_are_not_stopped_or_queried(tmp_path, monkeypatch):
    def forbidden(command, *values, persist=None):
        raise AssertionError("status must not be requested before services start")

    instance, runs, kills = _cleanup_instance(tmp_path, monkeypatch, forbidden)
    instance.services_started = False
    instance.cleanup_after_failure()
    assert runs == []
    assert kills == [(HELPER_PID, acceptance.signal.SIGKILL)]
