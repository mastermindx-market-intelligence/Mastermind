"""Exact read-only service observations for pre-census qualification."""

from itertools import product
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as maintenance


LABELS = (
    "com.mastermind.executive.control",
    "com.mastermind.executive.worker.codex",
    "com.mastermind.executive.sol-state-relay",
)


def _absent(label):
    return f'Could not find service "{label}" in domain for system\n'.encode("ascii")


def _observations(monkeypatch, replies):
    calls = []

    def observe(argv, *, capture_output, timeout):
        index = len(calls)
        assert index < len(LABELS), "unexpected process observation"
        assert argv == ["/bin/launchctl", "print", "system/" + LABELS[index]]
        assert capture_output is True and timeout == 10
        calls.append(LABELS[index])
        reply = replies[index]
        if isinstance(reply, BaseException):
            raise reply
        return SimpleNamespace(returncode=reply[0], stdout=reply[1], stderr=reply[2])

    monkeypatch.setattr(maintenance.subprocess, "run", observe)
    return calls


@pytest.mark.parametrize("prefixed", list(product((False, True), repeat=3)))
def test_exact_absence_forms_for_all_three_services(monkeypatch, prefixed):
    # The prefixed Relay response is the exact retained Darwin host form.
    replies = [
        (113, b"", (b"Bad request.\n" if prefix else b"") + _absent(label))
        for label, prefix in zip(LABELS, prefixed)
    ]
    calls = _observations(monkeypatch, replies)
    maintenance._require_pre_census_stopped()
    assert calls == list(LABELS)


@pytest.mark.parametrize(
    "reply",
    [
        (0, b"", _absent(LABELS[2])),
        (1, b"", _absent(LABELS[2])),
        (112, b"", _absent(LABELS[2])),
        (113, b"unexpected", _absent(LABELS[2])),
        (113, b"", b""),
        (113, b"", _absent("com.mastermind.executive.foreign")),
        (113, b"", b"Bad request.\n" + _absent(LABELS[0])),
        (113, b"", b"arbitrary\n" + _absent(LABELS[2])),
        (113, b"", b"Bad request.\nBad request.\n" + _absent(LABELS[2])),
        (113, b"", _absent(LABELS[2]) + b"extra"),
        (113, b"", b"Bad request.\n" + _absent(LABELS[2]) + b"\n"),
        (113, b"", _absent(LABELS[2]).rstrip(b"\n")),
    ],
)
def test_relay_requires_exact_status_empty_stdout_and_exact_stderr(monkeypatch, reply):
    replies = [(113, b"", _absent(label)) for label in LABELS]
    replies[2] = reply
    calls = _observations(monkeypatch, replies)
    with pytest.raises(maintenance.MaintenanceError):
        maintenance._require_pre_census_stopped()
    assert calls == list(LABELS)


@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize(
    "reply",
    [(0, b"", b""), (113, b"output", b""), (113, b"", b"foreign service\n")],
)
def test_control_or_worker_refusal_still_prevents_relay_observation(monkeypatch, index, reply):
    replies = [(113, b"", _absent(label)) for label in LABELS]
    replies[index] = reply
    calls = _observations(monkeypatch, replies)
    with pytest.raises(maintenance.MaintenanceError):
        maintenance._require_pre_census_stopped()
    assert calls == list(LABELS[: index + 1])


@pytest.mark.parametrize("index", (0, 1, 2))
def test_observation_error_cannot_prove_absence(monkeypatch, index):
    replies = [(113, b"", _absent(label)) for label in LABELS]
    replies[index] = OSError("fixture observation unavailable")
    calls = _observations(monkeypatch, replies)
    with pytest.raises((maintenance.MaintenanceError, OSError)):
        maintenance._require_pre_census_stopped()
    assert calls == list(LABELS[: index + 1])
