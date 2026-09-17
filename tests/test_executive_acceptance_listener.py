"""Truthful TCP-listener observation for the privileged Executive acceptance harness."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "acceptance.py"
SPEC = importlib.util.spec_from_file_location("executive_acceptance_listener", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acceptance
SPEC.loader.exec_module(acceptance)

HEADER = b"COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
ROW = b"python 123 _mastermind_exec 9u IPv4 0x1 0t0 TCP 127.0.0.1:9000 (LISTEN)\n"


class _Socket:
    def __init__(self, present: bool = True):
        self.present = present

    def is_socket(self) -> bool:
        return self.present


def _completed(returncode: int, *, stdout: bytes = b"", stderr: bytes = b""):
    return subprocess.CompletedProcess(["lsof"], returncode, stdout=stdout, stderr=stderr)


def _bind(monkeypatch: pytest.MonkeyPatch, outcomes, *, sockets: bool = True):
    calls = []
    queued = iter(outcomes)

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return next(queued)

    monkeypatch.setattr(acceptance, "_run", fake_run)
    monkeypatch.setattr(acceptance, "CONTROL_SOCKET", _Socket(sockets))
    monkeypatch.setattr(acceptance, "WORKER_SOCKET", _Socket(sockets))
    return object.__new__(acceptance.Acceptance), calls


def test_listener_scan_accepts_only_exact_empty_no_match(monkeypatch):
    instance, calls = _bind(monkeypatch, [_completed(1), _completed(1)])

    instance._assert_no_public_listener()

    assert len(calls) == 2
    assert [call[0][4] for call in calls] == [acceptance.CONTROL_USER, acceptance.WORKER_USER]
    assert all(call[1]["check"] is False for call in calls)


@pytest.mark.parametrize(
    "outcome",
    [
        _completed(1, stderr=b"lsof: observation incomplete\n"),
        _completed(2),
        _completed(127),
        _completed(0),
        _completed(0, stdout=HEADER),
        _completed(0, stdout=b"COMMAND WRONG USER FD TYPE DEVICE SIZE/OFF NODE NAME\n" + ROW),
        _completed(0, stdout=b"not an lsof table\nsecond line\n"),
    ],
)
def test_listener_scan_refuses_ambiguous_or_malformed_observation(monkeypatch, outcome):
    instance, calls = _bind(monkeypatch, [outcome, outcome])

    with pytest.raises(acceptance.AcceptanceError, match="did not produce a complete observation"):
        instance._assert_no_public_listener()

    assert len(calls) == 1


def test_listener_scan_rejects_a_valid_listener_observation(monkeypatch):
    instance, calls = _bind(monkeypatch, [_completed(0, stdout=HEADER + ROW)])

    with pytest.raises(acceptance.AcceptanceError, match="owns a TCP listener"):
        instance._assert_no_public_listener()

    assert len(calls) == 1


def test_listener_scan_does_not_leak_lsof_diagnostics(monkeypatch):
    secretish = b"diagnostic-with-sensitive-host-detail"
    instance, _ = _bind(monkeypatch, [_completed(1, stderr=secretish), _completed(1, stderr=secretish)])

    with pytest.raises(acceptance.AcceptanceError) as raised:
        instance._assert_no_public_listener()

    assert secretish.decode() not in str(raised.value)


def test_private_unix_sockets_remain_required(monkeypatch):
    instance, calls = _bind(monkeypatch, [_completed(1), _completed(1)], sockets=False)

    with pytest.raises(acceptance.AcceptanceError, match="private Unix launchd sockets are unavailable"):
        instance._assert_no_public_listener()

    assert len(calls) == 2
