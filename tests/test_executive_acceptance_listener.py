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


# The 6.4 parametrization: every TCP listener shape that the harness must refuse
# even when only one of the two accounts reports it. The fix is an explicit
# row with the canonical 10-token Darwin lsof layout, returned with rc 0 for
# the affected account and the ordinary rc-1/empty shape for the other.
LISTENER_NAMES = (
    "*:8787",
    "127.0.0.1:8787",
    "127.0.0.1:1",
    "127.0.0.1:65535",
    "[::1]:8787",
    "[::]:443",
    "0.0.0.0:8787",
    "*:1",
    "*:65535",
    "localhost:8787",
)


def _listener_row(account: str, name: str) -> bytes:
    return (
        f"Python 1327 {account} 5u IPv4 0x1 0t0 TCP {name} (LISTEN)\n"
    ).encode("ascii")


@pytest.mark.parametrize("account", [acceptance.CONTROL_USER, acceptance.WORKER_USER])
@pytest.mark.parametrize("name", LISTENER_NAMES)
def test_listener_scan_refuses_every_tcp_listener_shape(monkeypatch, account, name):
    row = _listener_row(account, name)
    if account == acceptance.CONTROL_USER:
        outcomes = [_completed(0, stdout=HEADER + row), _completed(1)]
        expected_calls = 1
    else:
        outcomes = [_completed(1), _completed(0, stdout=HEADER + row)]
        expected_calls = 2
    instance, calls = _bind(monkeypatch, outcomes)

    with pytest.raises(acceptance.AcceptanceError, match="owns a TCP listener"):
        instance._assert_no_public_listener()

    assert len(calls) == expected_calls


# The 6.5 partial / unparseable / non-empty observations the harness must fail
# closed on rather than treating as "zero listeners".
@pytest.mark.parametrize(
    "outcome",
    [
        _completed(0, stdout=HEADER),
        _completed(0, stdout=HEADER + b"Python 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787 \n"),
        _completed(0, stdout=HEADER + b"Python 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787 ESTABLISHED\n"),
        _completed(0, stdout=b"COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"),
        _completed(0, stdout=b"garbled header\nPython 1327 _mastermind_exec 5u IPv4 0x1 0t0 TCP *:4787 (LISTEN)\n"),
        _completed(1, stderr=b"lsof: permission denied\n"),
        _completed(1, stdout=b"some leftover line\n"),
        _completed(2),
        _completed(0),
    ],
)
def test_listener_scan_refuses_unknown_observation(monkeypatch, outcome):
    instance, calls = _bind(monkeypatch, [outcome, outcome])

    with pytest.raises(acceptance.AcceptanceError, match="did not produce a complete observation"):
        instance._assert_no_public_listener()

    assert len(calls) == 1


def test_listener_scan_accepts_both_empty_zero_observations(monkeypatch):
    instance, calls = _bind(monkeypatch, [_completed(1), _completed(1)])

    instance._assert_no_public_listener()

    assert len(calls) == 2
