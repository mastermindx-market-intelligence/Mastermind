"""Bounded full-arm startup observation; no service or host effects."""

from __future__ import annotations

import copy
import json
import subprocess

import pytest

from ops.executive_os import autonomy_control as control
from tests import test_executive_autonomy_control as fixtures


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def observed_host(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(control, "time", clock)
    host = control.ProductionTransactionHost()
    phases = []
    host._active_transaction = object()
    monkeypatch.setattr(host, "_persist_phase", lambda tx, phase: phases.append(phase))
    return host, clock, phases


def install_process_observer(monkeypatch, clock, status, *, loaded=None):
    """Replace only the subprocess boundary, retaining the real READY parser."""
    calls = []
    loaded = loaded or {control.CONTROL_LABEL: True, control.WORKER_LABEL: True}

    def run(argv, **kwargs):
        calls.append((tuple(argv), kwargs["timeout"], clock.now))
        assert kwargs["timeout"] > 0
        if argv[0] == "/bin/launchctl":
            assert argv[1] == "print"
            label = argv[2].removeprefix("system/")
            return subprocess.CompletedProcess(argv, 0 if loaded[label] else 113)
        assert argv[0] == "/usr/bin/sudo" and argv[-1] == "status"
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        return status(argv, kwargs["timeout"])

    monkeypatch.setattr(control.subprocess, "run", run)
    return calls


def response(argv, state="READY", *, ok=True, returncode=0):
    return subprocess.CompletedProcess(
        argv, returncode, json.dumps({"ok": ok, "result": {"service_state": state}}).encode()
    )


@pytest.mark.parametrize("ready_after", [241, 301])
def test_actual_ready_after_workspace_and_broker_startup_exceeds_old_45_second_wait(
    monkeypatch, observed_host, ready_after,
):
    host, clock, phases = observed_host
    calls = install_process_observer(
        monkeypatch, clock,
        lambda argv, timeout: response(argv, "READY" if clock.now >= ready_after else "STARTING"),
    )

    host.prove_services_ready(fixtures.SHA)

    assert clock.now == ready_after
    assert phases == ["READY_PROVEN"]
    assert len([argv for argv, _, _ in calls if argv[-1] == "status"]) == ready_after + 1


def test_blocked_status_probe_is_transient_until_a_real_ready_response(
    monkeypatch, observed_host,
):
    host, clock, phases = observed_host
    attempts = []

    def status(argv, timeout):
        attempts.append(clock.now)
        if len(attempts) == 1:
            clock.now += timeout
            raise subprocess.TimeoutExpired(argv, timeout)
        return response(argv)

    install_process_observer(monkeypatch, clock, status)
    host.prove_services_ready(fixtures.SHA)

    assert attempts == [0, 11]
    assert phases == ["READY_PROVEN"]


def test_normal_status_still_propagates_its_existing_probe_timeout(
    monkeypatch, observed_host,
):
    host, clock, phases = observed_host
    error = subprocess.TimeoutExpired("status", 10)

    def status(argv, timeout):
        assert timeout == 10
        raise error

    install_process_observer(monkeypatch, clock, status)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        host._service_state(fixtures.SHA)
    assert raised.value is error
    assert phases == []


@pytest.mark.parametrize(
    "status",
    [
        lambda argv, timeout: response(argv, "AWAITING_CANARY"),
        lambda argv, timeout: response(argv, ok=False),
        lambda argv, timeout: response(argv, ok=1),
        lambda argv, timeout: response(argv, returncode=1),
        lambda argv, timeout: subprocess.CompletedProcess(argv, 0, b"not-json"),
    ],
)
def test_no_non_ready_or_invalid_response_becomes_success(monkeypatch, observed_host, status):
    host, clock, phases = observed_host
    install_process_observer(monkeypatch, clock, status)

    with pytest.raises(RuntimeError, match="Executive services did not reach READY"):
        host.prove_services_ready(fixtures.SHA)

    assert clock.now == 360
    assert phases == []


@pytest.mark.parametrize("loaded", [(False, False), (True, False), (False, True)])
def test_both_registered_services_remain_required(monkeypatch, observed_host, loaded):
    host, clock, phases = observed_host
    calls = install_process_observer(
        monkeypatch, clock, lambda *args: pytest.fail("status must not run"),
        loaded=dict(zip((control.CONTROL_LABEL, control.WORKER_LABEL), loaded)),
    )

    with pytest.raises(RuntimeError, match="Executive services did not reach READY"):
        host.prove_services_ready(fixtures.SHA)

    assert all(argv[0] == "/bin/launchctl" for argv, _, _ in calls)
    assert clock.now == 360
    assert phases == []


def test_every_observation_and_sleep_is_capped_by_one_remaining_deadline(
    monkeypatch, observed_host,
):
    host, clock, phases = observed_host
    calls = []

    def run(argv, **kwargs):
        calls.append((argv[0], kwargs["timeout"], clock.now))
        if len(calls) == 1:
            clock.now = 359.5  # Scheduling delay consumes the shared allowance.
            return subprocess.CompletedProcess(argv, 0)
        if len(calls) == 2:
            assert kwargs["timeout"] == 0.5
            clock.now += 0.25
            return subprocess.CompletedProcess(argv, 0)
        assert argv[-1] == "status" and kwargs["timeout"] == 0.25
        clock.now += kwargs["timeout"]
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(control.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Executive services did not reach READY"):
        host.prove_services_ready(fixtures.SHA)

    assert clock.now == 360
    assert len(calls) == 3
    assert clock.sleeps == []
    assert phases == []


def test_ready_returning_after_deadline_is_not_accepted(monkeypatch, observed_host):
    host, clock, phases = observed_host

    def late_status(argv, timeout):
        clock.now = 360.01
        return response(argv)

    install_process_observer(monkeypatch, clock, late_status)
    with pytest.raises(RuntimeError, match="Executive services did not reach READY"):
        host.prove_services_ready(fixtures.SHA)
    assert phases == []


@pytest.mark.parametrize("failure", ["deadline", "unexpected", "launchctl_timeout"])
def test_startup_failure_retains_normal_arm_rollback(monkeypatch, observed_host, failure):
    production, clock, phases = observed_host
    production._active_transaction = None
    transaction = fixtures.FakeTransactionHost()
    before_control = copy.deepcopy(transaction.control_config)
    before_worker = copy.deepcopy(transaction.worker_config)
    transaction.prove_services_ready = production.prove_services_ready
    error = OSError("synthetic status execution failure")

    def status(argv, timeout):
        if failure == "unexpected":
            raise error
        clock.now += timeout
        raise subprocess.TimeoutExpired(argv, timeout)

    install_process_observer(monkeypatch, clock, status)
    if failure == "launchctl_timeout":
        error = subprocess.TimeoutExpired("launchctl", 5)

        def launchctl_failure(argv, **kwargs):
            assert argv[0] == "/bin/launchctl"
            raise error

        monkeypatch.setattr(control.subprocess, "run", launchctl_failure)

    with pytest.raises(control.ArmTransactionError, match="arm_rolled_back") as raised:
        control.execute_arm(transaction, fixtures._arm_request(), now=fixtures.NOW)

    if failure == "deadline":
        assert type(raised.value.__cause__) is RuntimeError
        assert clock.now == 360
    else:
        assert raised.value.__cause__ is error
        assert clock.now == 0
    assert transaction.control_config == before_control
    assert transaction.worker_config == before_worker
    assert transaction.receipt["state"] == "DISARMED"
    assert transaction.services == "STOPPED"
    assert transaction.service_starts == 1
    assert transaction.marker is False
    assert phases == []
