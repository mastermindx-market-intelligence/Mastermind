"""Real maintenance entrypoints refuse uncertain launchd observations before effects."""
import subprocess
from types import SimpleNamespace

import pytest

from ops.executive_os import acceptance_maintenance as m

_LABELS = ("com.mastermind.executive.control", "com.mastermind.executive.worker.codex")
_BAD = [
    (0, 113), (113, 0), (0, 0),
    (5, 113), (113, 5), (5, 5), (113, 1), (113, -9),
    (OSError("observation unavailable"), 113),
    (113, subprocess.TimeoutExpired("launchctl", 10)),
    ((113, b"", b"permission denied\n"), 113),
    (113, (113, b"", b"permission denied\n")),
    (113, (113, b"", b"")),
    (113, (113, b"", b'Could not find service "wrong-label" in domain for system\n')),
    (113, (113, b"loaded service", b'Could not find service "com.mastermind.executive.worker.codex" in domain for system\n')),
]


def _observations(monkeypatch, values):
    calls = []
    def run(command, **kwargs):
        index = len(calls)
        assert command == ["/bin/launchctl", "print", "system/" + _LABELS[index]]
        assert kwargs == {"capture_output": True, "timeout": 10}
        calls.append(command)
        result = values[index]
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, tuple):
            code, stdout, stderr = result
            return subprocess.CompletedProcess(command, code, stdout, stderr)
        absent = f'Could not find service "{_LABELS[index]}" in domain for system\n'.encode()
        return subprocess.CompletedProcess(command, result, b"", absent)
    monkeypatch.setattr(m.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("prefix", [b"", b"Bad request.\n"])
def test_both_exact_absence_observations_are_required(monkeypatch, prefix):
    values = tuple((113, b"", prefix + f'Could not find service "{label}" in domain for system\n'.encode()) for label in _LABELS)
    calls = _observations(monkeypatch, values)
    m.require_stopped()
    assert len(calls) == 2


@pytest.mark.parametrize("values", _BAD)
@pytest.mark.parametrize("entrypoint", ["prepare", "initialize"])
def test_uncertain_observation_precedes_descriptor_or_run_publication(
    tmp_path, monkeypatch, values, entrypoint,
):
    calls = _observations(monkeypatch, values)
    system_root = tmp_path / "host-system"
    monkeypatch.setattr(m, "SYSTEM_ROOT", system_root)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "platform", "darwin")
    published = []
    monkeypatch.setattr(m, "write_sealed", lambda *args, **kwargs: published.append(args))
    descriptor = {"schema_version": m.SCHEMA_V2}
    monkeypatch.setattr(m, "descriptor_for", lambda sha: descriptor)
    monkeypatch.setattr(m, "validate_prior_carry_binding", lambda value: None)
    config = {key: False for key in (
        "ceo_submit_armed", "coo_autonomy_armed", "coo_operator_harness_armed",
    )}
    with pytest.raises(m.MaintenanceError, match="absence"):
        if entrypoint == "prepare":
            m.prepare(SimpleNamespace(successor_sha="b" * 40))
        else:
            m.Maintenance("b" * 40, m.digest(descriptor), config)
    assert calls
    assert published == []
    assert not system_root.exists()
