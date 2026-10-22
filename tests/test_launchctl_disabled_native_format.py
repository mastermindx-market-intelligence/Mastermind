"""Observed macOS framing with no live launchctl or service effects."""
import time
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from control_plane import executive_recovery_host_observation as h
from control_plane import executive_recovery_observation_normalization as n

# Reduced from the retained 2026-10-15 root print-disabled observation. Keep
# the exact leading blank line, header/closing indentation and two-tab rows.
NATIVE = (b'\n\tdisabled services = {\n'
          b'\t\t"com.mastermind.executive.privileged" => disabled\n\t}\n')
FLAT = (b'disabled services = {\n'
        b'\t"com.mastermind.executive.privileged" => true\n}\n')


@pytest.mark.parametrize("raw", [NATIVE, FLAT])
def test_disabled_documents_retain_exact_target_evidence(raw):
    assert n.normalize_disabled(0, raw, b'') == 'DISABLED'


def test_actual_installer_join_accepts_native_disabled_and_exact_unloaded(monkeypatch):
    monkeypatch.setattr(h, 'sys', S(platform='darwin'))
    monkeypatch.setattr(h, 'os', S(geteuid=lambda: 0))
    command = Mock(side_effect=[(0, NATIVE, b''), (
        113, b'', b'Bad request.\nCould not find service "com.mastermind.executive.privileged" in domain for system\n')])
    monkeypatch.setattr(h.release, '_command', command)
    monkeypatch.setattr(h.release.subprocess, 'Popen', Mock(side_effect=AssertionError('no native child')))
    h._wait_installer_unloaded(n.LABEL, deadline_monotonic_ns=time.monotonic_ns() + 2_000_000_000)
    assert command.call_count == 2
    assert [call.args[0] for call in command.call_args_list] == [
        h.release._PRINT_DISABLED_ARGV, ('/bin/launchctl', 'print', 'system/' + n.LABEL)]


@pytest.mark.parametrize("raw", [
    b'warning\n' + NATIVE,
    NATIVE + b'\n',
    NATIVE + NATIVE,
    NATIVE[:-1],
    NATIVE.replace(b'\t}\n', b'}\n'),
    NATIVE.replace(b'\t\t"', b'\t"'),
    NATIVE.replace(b'=> disabled', b'=> enabled'),
    NATIVE.replace(n.LABEL.encode(), b'com.example.other'),
    NATIVE.replace(b'\t}\n', b'\t\t"com.mastermind.executive.privileged" => enabled\n\t}\n'),
    NATIVE.replace(b'\t}\n', b'\t\t"com.mastermind.executive.privileged" => disabled\n\t}\n'),
    NATIVE.replace(b'disabled\n', b'unknown\n'),
    NATIVE.replace(b'\t}\n', b'\t\twarning\n\t}\n'),
])
def test_native_document_noise_ambiguity_and_missing_disable_are_rejected(raw):
    with pytest.raises(n.ObservationRejected):
        n.normalize_disabled(0, raw, b'')


@pytest.mark.parametrize("rc,err", [(1, b''), (True, b''), (0, b'warning\n')])
def test_native_shape_cannot_override_unsuccessful_command(rc, err):
    with pytest.raises(n.ObservationRejected):
        n.normalize_disabled(rc, NATIVE, err)
