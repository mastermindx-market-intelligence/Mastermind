"""Transient status reads stay inside the existing bounded admission proof.

No service, root configuration, marker, or provider is changed by these tests.
"""
import os
import subprocess

import pytest

from ops.executive_os import autonomy_control as control
import test_executive_autonomy_control as fixture


def test_status_timeout_is_failed_read_not_early_transaction_abort(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    calls = []
    def timed_out(*args, **kwargs):
        calls.append((args, kwargs))
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    def forbidden(*args, **kwargs):
        raise AssertionError("No attestation or config read follows an absent status witness")
    monkeypatch.setattr(control.subprocess, "run", timed_out)
    monkeypatch.setattr(control, "_root_json", forbidden)
    assert host._ceo_admission_probe(fixture.SHA, fixture._CONFIG_DIGEST) is False
    assert len(calls) == 1
    assert calls[0][1]["timeout"] == 10


def test_same_bounded_wait_accepts_only_a_later_complete_witness(monkeypatch, tmp_path):
    host = control.ProductionCeoSubmitHost()
    fixture._drive_probe(monkeypatch, tmp_path=tmp_path,
        attestation_doc=fixture._good_attestation_doc(), inspector=fixture._LiveFakeInspector())
    calls = []
    def read_status(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
        return fixture._FakeCompletedProcess(stdout=fixture._probe_status_body(
            service_state="AWAITING_CANARY", socket_path=os.fspath(control.CONTROL_SOCKET)))
    monkeypatch.setattr(control.subprocess, "run", read_status)
    monkeypatch.setattr(host, "_loaded", lambda _: True)
    _, sleeps = fixture._install_fake_clock(monkeypatch)
    assert host._await_control_admission_bound(fixture.SHA, fixture._CONFIG_DIGEST) is None
    assert len(calls) == 2 and sleeps.calls == [1.0]
    assert all("status" in args[0] for args, _ in calls)


def test_persistent_status_timeouts_still_exhaust_original_bound(monkeypatch):
    host = control.ProductionCeoSubmitHost()
    clock = [0.0]
    calls = []
    def timed_out(*args, **kwargs):
        calls.append((args, kwargs))
        clock[0] += kwargs["timeout"]
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(control.subprocess, "run", timed_out)
    monkeypatch.setattr(host, "_loaded", lambda _: True)
    monkeypatch.setattr(control.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(control.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    with pytest.raises(RuntimeError, match="did not bind"):
        host._await_control_admission_bound(fixture.SHA, fixture._CONFIG_DIGEST)
    # Existing 45-second loop plus at most one 10-second status read and sleep.
    assert len(calls) == 5 and clock[0] == 55.0


@pytest.mark.parametrize("failure", [PermissionError("status executable refused"), KeyboardInterrupt()])
def test_denial_and_interruption_are_not_reclassified_as_transient(monkeypatch, failure):
    host = control.ProductionCeoSubmitHost()
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(control.subprocess, "run", fail)
    with pytest.raises(type(failure)):
        host._ceo_admission_probe(fixture.SHA, fixture._CONFIG_DIGEST)
