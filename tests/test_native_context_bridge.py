"""In-process bridge fixture tests, not upstream compiler or source-owner proof."""
import sys
from pathlib import Path

import pytest

from integrations.native_context.adapter import Binding, MAX_READER_BYTES
from integrations.native_context.bridge import CanonicalBootReader

MASTER = "b" * 40
ROOT = Path("/installed/Mastermind")
BINDING = Binding("EXAMPLE-CONTEXT", Path("/approved/Macro"), "a" * 40, MASTER)


def test_bridge_preserves_exact_stdout_and_never_relays_stderr():
    calls = []
    def main(argv):
        calls.append(argv)
        sys.stdout.write('{"producer":"fixture"}\n')
        sys.stderr.write("PRIVATE DIAGNOSTIC")
        return 0
    reader = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: MASTER)
    result = reader(BINDING, 4000, 10)
    assert result.ok and result.raw == b'{"producer":"fixture"}\n'
    assert len(calls) == 1 and calls[0][0] == "--workstream"
    assert "PRIVATE" not in result.raw.decode()


def test_pin_mismatch_stops_before_main():
    calls = []
    reader = CanonicalBootReader(root=ROOT, main=lambda a: calls.append(a), git_sha=lambda _: "c" * 40)
    assert not reader(BINDING, 4000, 10).ok
    assert calls == []


def test_pin_drift_withholds_even_successful_output():
    pins = iter([MASTER, "c" * 40])
    def main(_):
        print("VALID_BUT_UNSETTLED")
        return 0
    result = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: next(pins))(BINDING, 4000, 10)
    assert not result.ok and result.raw == b""


@pytest.mark.parametrize("code", [1, 2, None, True, False, "0"])
def test_only_actual_integer_zero_is_success(code):
    def main(_):
        print("PARTIAL_PRIVATE_DATA")
        return code
    result = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: MASTER)(BINDING, 4000, 10)
    assert not result.ok and result.raw == b""


def test_older_cli_failure_does_not_trigger_global_brief():
    calls = []
    def main(argv):
        calls.append(argv)
        raise SystemExit(2)
    result = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: MASTER)(BINDING, 4000, 10)
    assert not result.ok and len(calls) == 1 and calls[0]


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_diagnostic_and_payload_floods_are_bounded(stream):
    def main(_):
        getattr(sys, stream).write("X" * (MAX_READER_BYTES + 2))
        return 0
    result = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: MASTER)(BINDING, 4000, 10)
    assert not result.ok and result.raw == b""


def test_exception_restores_process_streams():
    original = (sys.stdout, sys.stderr)
    def main(_):
        raise RuntimeError("sensitive reason")
    result = CanonicalBootReader(root=ROOT, main=main, git_sha=lambda _: MASTER)(BINDING, 4000, 10)
    assert not result.ok and result.raw == b""
    assert original == (sys.stdout, sys.stderr)


@pytest.mark.parametrize("fail", [False, True])
def test_dependency_import_diagnostics_cannot_corrupt_hook_json(monkeypatch, capsys, fail):
    import builtins
    import types
    from integrations.native_context.bridge import installed_reader
    original = builtins.__import__
    def noisy_import(name, *args, **kwargs):
        if name in ("control_plane.ceo_boot_packet", "scripts.ceo_boot_packet"):
            print("PRIVATE_IMPORT_DIAGNOSTIC")
            print("PRIVATE_IMPORT_ERROR", file=sys.stderr)
            if fail:
                raise ImportError("PRIVATE_IMPORT_FAILURE")
            return types.SimpleNamespace(git_sha=lambda _: MASTER, main=lambda _: 0)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", noisy_import)
    if fail:
        with pytest.raises(ImportError):
            installed_reader(ROOT)
    else:
        assert isinstance(installed_reader(ROOT), CanonicalBootReader)
    observed = capsys.readouterr()
    assert observed.out == "" and observed.err == ""
