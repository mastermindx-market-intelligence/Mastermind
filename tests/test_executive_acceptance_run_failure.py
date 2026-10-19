"""Bounded diagnostic capture for the privileged Executive acceptance harness.

The host-status `_run` calls previously discarded the failing command's
stdout/stderr so a status.sh failure left nothing diagnosable. This module
proves the bounded, redacted, Control-owned artifact that the harness now
records on CommandFailure / TimeoutExpired, and that the unchanged success
path is unaffected.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "acceptance.py"
SPEC = importlib.util.spec_from_file_location(
    "executive_acceptance_run_failure", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acceptance
SPEC.loader.exec_module(acceptance)


SENTINEL = "MASTERMIND_CANARY_SENTINEL_VALUE_AAAA"
HEX_RUN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
ORDINARY_LINE = "ordinary line that should appear verbatim"


class _FakePw:
    def __init__(self, uid: int) -> None:
        self.pw_uid = uid


class _FakeGr:
    def __init__(self, gid: int) -> None:
        self.gr_gid = gid


def _acceptance(tmp_path: Path, *, sentinel_paths: list[Path] | None = None):
    instance = object.__new__(acceptance.Acceptance)
    instance.receipt_root = tmp_path / "receipts"
    instance.receipt_root.mkdir(mode=0o700)
    os.chmod(instance.receipt_root, 0o700)
    instance.control_identity = _FakePw(os.geteuid())
    instance.worker_identity = _FakePw(os.geteuid())
    instance.control_group = _FakeGr(os.getegid())
    instance.worker_group = _FakeGr(os.getegid())
    instance.operator_identity = _FakePw(os.geteuid())
    instance.config = {
        "runtime_root": str(tmp_path / "rt"),
        "receipts_root": str(tmp_path / "rcpts"),
        "worker_runs_root": str(tmp_path / "wr"),
        "proof_workspace_root": str(tmp_path / "ws"),
        "proof_source_repository": str(tmp_path / "src"),
        "worker_provider_home": str(tmp_path / "workerhome"),
    }
    for key, value in instance.config.items():
        Path(value).mkdir(parents=True, exist_ok=True)
    instance.release = tmp_path / "release"
    instance.release.mkdir(parents=True, exist_ok=True)
    instance.canary_value = SENTINEL

    def _sources():
        return list(sentinel_paths or [])

    instance._sentinel_sources = _sources  # type: ignore[assignment]
    return instance


def _write_fake_status(release: Path, *, script: str) -> Path:
    ops = release / "ops" / "executive_os"
    ops.mkdir(parents=True, exist_ok=True)
    fake = ops / "status.sh"
    fake.write_text(script)
    fake.chmod(0o755)
    return fake


FAILING_STATUS = textwrap.dedent(
    f"""\
    #!/bin/bash
    echo "{SENTINEL}"
    echo "{HEX_RUN}"
    echo "{ORDINARY_LINE}"
    echo "lsof: fake failure" 1>&2
    exit 1
    """
)


def test_command_failure_carries_payload_and_keeps_message(tmp_path: Path):
    instance = _acceptance(tmp_path)
    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", "-c", "echo diagnostic; exit 3"],
            label="host service status",
        )
    assert isinstance(raised.value, acceptance.AcceptanceError)
    assert str(raised.value) == "host service status failed with exit 3"
    assert raised.value.label == "host service status"
    assert raised.value.returncode == 3
    assert b"diagnostic" in raised.value.stdout
    assert raised.value.argv[0] == "/bin/bash"


def test_failing_status_leaves_bounded_artifact(tmp_path: Path):
    instance = _acceptance(tmp_path)
    _write_fake_status(instance.release, script=FAILING_STATUS)

    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
        )
    assert str(raised.value) == "host service status failed with exit 1"

    artifact = instance.receipt_root / "host-service-status-failure.txt"
    assert artifact.exists()
    info = artifact.lstat()
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert stat.S_IMODE(info.st_mode) == 0o400
    assert info.st_nlink == 1

    payload = artifact.read_text(encoding="utf-8")
    assert "returncode: 1" in payload
    assert "host service status" in payload
    assert ORDINARY_LINE in payload
    assert "lsof: fake failure" in payload
    assert SENTINEL not in payload
    assert HEX_RUN not in payload
    assert not (instance.receipt_root / "host-status.txt").exists()


def test_failing_final_status_leaves_final_artifact(tmp_path: Path):
    instance = _acceptance(tmp_path)
    _write_fake_status(instance.release, script=FAILING_STATUS)

    with pytest.raises(acceptance.CommandFailure):
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="final host status",
        )

    artifact = instance.receipt_root / "final-host-status-failure.txt"
    assert artifact.exists()
    assert "returncode: 1" in artifact.read_text(encoding="utf-8")
    assert SENTINEL not in artifact.read_text(encoding="utf-8")
    assert not (instance.receipt_root / "final-host-status.txt").exists()


def test_stream_bounds_truncate_large_output(tmp_path: Path):
    instance = _acceptance(tmp_path)
    payload_size = 300 * 1024
    big_status = (
        "#!/bin/bash\n"
        f"python3 -c 'import sys; sys.stdout.write(\". \"*{payload_size}); sys.exit(1)'\n"
    )
    _write_fake_status(instance.release, script=big_status)

    with pytest.raises(acceptance.CommandFailure):
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
        )

    artifact = instance.receipt_root / "host-service-status-failure.txt"
    info = artifact.lstat()
    assert info.st_size <= acceptance._FAILURE_ARTIFACT_LIMIT

    body = artifact.read_text(encoding="utf-8")
    assert acceptance._REFUSAL_TRUNCATION_MARKER in body


def test_secret_straddling_truncation_point_still_redacted(tmp_path: Path):
    instance = _acceptance(tmp_path)
    padding = "x" * (acceptance._FAILURE_STREAM_LIMIT - 8)
    straddling_secret = padding + "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    script = f"#!/bin/bash\necho '{straddling_secret}'\nexit 1\n"
    _write_fake_status(instance.release, script=script)

    with pytest.raises(acceptance.CommandFailure):
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
        )

    artifact = instance.receipt_root / "host-service-status-failure.txt"
    body = artifact.read_text(encoding="utf-8")
    assert "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" not in body
    assert acceptance._REFUSAL_REDACTION in body


def test_timeout_artifact_records_partial_output(tmp_path: Path):
    instance = _acceptance(tmp_path)
    script = "#!/bin/bash\necho started-line\nsleep 5\nexit 0\n"
    _write_fake_status(instance.release, script=script)

    with pytest.raises(subprocess.TimeoutExpired) as raised:
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
            timeout=0.5,
        )

    assert isinstance(raised.value, subprocess.TimeoutExpired)
    artifact = instance.receipt_root / "host-service-status-failure.txt"
    body = artifact.read_text(encoding="utf-8")
    assert "returncode: timeout after" in body


def test_recording_failure_keeps_original_exception(monkeypatch, tmp_path: Path):
    instance = _acceptance(tmp_path)
    _write_fake_status(instance.release, script=FAILING_STATUS)

    def _raise(name, payload):
        raise OSError("disk full")

    monkeypatch.setattr(instance, "_write_bytes", _raise)

    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", instance.release / "ops" / "executive_os" / "status.sh"],
            label="host service status",
        )

    notes = getattr(raised.value, "__notes__", ())
    assert any(
        "failure artifact not recorded: OSError" == note for note in notes
    ), notes


def test_unknown_label_refuses_without_subprocess(monkeypatch, tmp_path: Path):
    instance = _acceptance(tmp_path)

    def _no_subprocess(*args, **kwargs):
        raise AssertionError("subprocess must not be invoked for an unknown label")

    monkeypatch.setattr(acceptance, "_run", _no_subprocess)

    with pytest.raises(acceptance.AcceptanceError):
        instance._run_recorded(
            ["/bin/bash", "anything"],
            label="no such label",
        )


def _bootstrap_leakage_env(tmp_path: Path, monkeypatch, sentinel: Path) -> tuple:
    instance = _acceptance(tmp_path, sentinel_paths=[sentinel])

    def _empty_ps(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(acceptance, "_run", _empty_ps)
    return instance, acceptance


def test_leakage_scan_passes_with_clean_receipts(monkeypatch, tmp_path: Path):
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text(SENTINEL, encoding="utf-8")
    instance, _acc = _bootstrap_leakage_env(tmp_path, monkeypatch, sentinel)

    instance._write_bytes("host-service-status-failure.txt", b"clean artifact body\n")
    instance.leakage_scan(control_pid=99999)

    summary = json.loads(
        (instance.receipt_root / "leakage-scan.json").read_text(encoding="utf-8")
    )
    assert summary["passed"] is True


def test_leakage_scan_fails_when_canary_escapes(monkeypatch, tmp_path: Path):
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text(SENTINEL, encoding="utf-8")
    instance, _acc = _bootstrap_leakage_env(tmp_path, monkeypatch, sentinel)

    instance._write_bytes("host-service-status-failure.txt", SENTINEL.encode("utf-8"))

    with pytest.raises(acceptance.AcceptanceError, match="canary value escaped"):
        instance.leakage_scan(control_pid=99999)


# -- A1: byte-bounded failure artifact for non-UTF-8 streams --------------------

def test_failure_artifact_bounds_non_utf8_streams_by_bytes():
    """A real bug: the decoded-text slice was ~3x too generous after U+FFFD expansion."""
    instance = object.__new__(acceptance.Acceptance)
    instance.config = {
        "runtime_root": "/dev/null",
        "receipts_root": "/dev/null",
        "worker_runs_root": "/dev/null",
        "proof_workspace_root": "/dev/null",
        "proof_source_repository": "/dev/null",
        "worker_provider_home": "/dev/null",
    }
    instance._sentinel_sources = lambda: []  # type: ignore[assignment]
    instance.canary_value = ""
    payload = instance._build_failure_payload(
        label="host service status",
        argv=["/bin/bash", "/tmp/anything"],
        returncode=1,
        stdout=b"\xff" * 200000,
        stderr=b"\xfe" * 200000,
    )
    assert isinstance(payload, bytes)
    assert len(payload) <= acceptance._FAILURE_ARTIFACT_LIMIT
    text = payload.decode("utf-8", errors="replace")
    stdout_marker = text.find("--- stdout (")
    stderr_marker = text.find("--- stderr (")
    stdout_section = text[stdout_marker:text.find("--- stderr", stdout_marker)]
    stderr_section = text[stderr_marker:]
    assert acceptance._REFUSAL_TRUNCATION_MARKER in stdout_section
    assert acceptance._REFUSAL_TRUNCATION_MARKER in stderr_section


# -- A2: preserve newline/tab structure, neutralise other control chars, prefix lines ---

def test_failure_artifact_preserves_lines_and_neutralises_controls():
    instance = object.__new__(acceptance.Acceptance)
    instance.config = {
        "runtime_root": "/dev/null",
        "receipts_root": "/dev/null",
        "worker_runs_root": "/dev/null",
        "proof_workspace_root": "/dev/null",
        "proof_source_repository": "/dev/null",
        "worker_provider_home": "/dev/null",
    }
    instance._sentinel_sources = lambda: []  # type: ignore[assignment]
    instance.canary_value = ""
    stdout_blob = b"one\ntwo\tx\x1b[31my\rz\nreturncode: 0"
    payload = instance._build_failure_payload(
        label="host service status",
        argv=["/bin/bash", "/tmp/anything"],
        returncode=0,
        stdout=stdout_blob,
        stderr=b"",
    )
    text = payload.decode("utf-8")
    stdout_marker = text.find("--- stdout (")
    stdout_section = text[stdout_marker:text.find("--- stderr", stdout_marker)]
    expected = "| one\n| two\tx [31my z\n| returncode: 0"
    assert expected in stdout_section
    header_returns = [
        line for line in text.splitlines() if line.startswith("returncode: ")
    ]
    assert len(header_returns) == 1
    assert header_returns[0] == "returncode: 0"


# -- A3: positive: a real recorded CommandFailure artifact must pass leakage_scan ---

def _acceptance_with_real_roots(tmp_path: Path, sentinel_paths: list[Path]):
    instance = object.__new__(acceptance.Acceptance)
    instance.receipt_root = tmp_path / "receipts"
    instance.receipt_root.mkdir(mode=0o700)
    os.chmod(instance.receipt_root, 0o700)
    instance.control_identity = _FakePw(os.geteuid())
    instance.worker_identity = _FakePw(os.geteuid())
    instance.control_group = _FakeGr(os.getegid())
    instance.worker_group = _FakeGr(os.getegid())
    instance.operator_identity = _FakePw(os.geteuid())
    instance.config = {
        "runtime_root": str(tmp_path / "rt"),
        "receipts_root": str(tmp_path / "rcpts"),
        "worker_runs_root": str(tmp_path / "wr"),
        "proof_workspace_root": str(tmp_path / "ws"),
        "proof_source_repository": str(tmp_path / "src"),
        "worker_provider_home": str(tmp_path / "workerhome"),
    }
    for key, value in instance.config.items():
        Path(value).mkdir(parents=True, exist_ok=True)
    instance.release = tmp_path / "release"
    instance.release.mkdir(parents=True, exist_ok=True)
    instance.canary_value = SENTINEL

    def _sources():
        return list(sentinel_paths or [])

    instance._sentinel_sources = _sources  # type: ignore[assignment]
    return instance


def _mock_leakage_scan_subprocess(monkeypatch):
    """The real leakage_scan invokes /bin/ps with BSD-only flags; on Linux the
    harness's existing tests stub _run to return an empty process table. The
    script that produces the artifact still runs through the real
    _run_recorded; only the subprocess that walks the live process list is stubbed."""

    calls: list[list[str]] = []

    def _capture_ps(argv, **kwargs):
        label = kwargs.get("label")
        if label == "process argv/environment leakage scan":
            calls.append([os.fspath(value) for value in argv])
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return _orig_run(argv, **kwargs)

    _orig_run = acceptance._run
    monkeypatch.setattr(acceptance, "_run", _capture_ps)
    return calls


def test_failing_status_artifact_passes_leakage_scan(monkeypatch, tmp_path: Path):
    sentinel_a = tmp_path / "sentinel-a.txt"
    sentinel_a.write_text("SENTINEL-ALPHA-7c1e", encoding="utf-8")
    sentinel_b = tmp_path / "sentinel-b.txt"
    sentinel_b.write_text("SENTINEL-BETA-93fd", encoding="utf-8")
    instance = _acceptance_with_real_roots(tmp_path, [sentinel_a, sentinel_b])
    _mock_leakage_scan_subprocess(monkeypatch)

    status_script = tmp_path / "status.sh"
    status_script.write_text(
        "#!/bin/bash\n"
        'echo "status line SENTINEL-ALPHA-7c1e"\n'
        'echo "err SENTINEL-BETA-93fd" 1>&2\n'
        "exit 3\n"
    )
    status_script.chmod(0o755)

    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", str(status_script)],
            label="host service status",
        )
    assert str(raised.value) == "host service status failed with exit 3"

    artifact = instance.receipt_root / "host-service-status-failure.txt"
    assert artifact.exists()
    info = artifact.lstat()
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert stat.S_IMODE(info.st_mode) == 0o400
    body = artifact.read_text(encoding="utf-8")
    assert "returncode: 3" in body
    assert "| status line <redacted>" in body
    assert "SENTINEL-ALPHA-7c1e" not in body
    assert "SENTINEL-BETA-93fd" not in body

    instance.leakage_scan(control_pid=os.getpid())


def test_failing_final_status_artifact_passes_leakage_scan(
    monkeypatch, tmp_path: Path
):
    sentinel_a = tmp_path / "sentinel-a.txt"
    sentinel_a.write_text("SENTINEL-ALPHA-7c1e", encoding="utf-8")
    sentinel_b = tmp_path / "sentinel-b.txt"
    sentinel_b.write_text("SENTINEL-BETA-93fd", encoding="utf-8")
    instance = _acceptance_with_real_roots(tmp_path, [sentinel_a, sentinel_b])
    _mock_leakage_scan_subprocess(monkeypatch)

    status_script = tmp_path / "final-status.sh"
    status_script.write_text(
        "#!/bin/bash\n"
        'echo "final line SENTINEL-ALPHA-7c1e"\n'
        'echo "err SENTINEL-BETA-93fd" 1>&2\n'
        "exit 7\n"
    )
    status_script.chmod(0o755)

    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", str(status_script)],
            label="final host status",
        )
    assert str(raised.value) == "final host status failed with exit 7"

    artifact = instance.receipt_root / "final-host-status-failure.txt"
    assert artifact.exists()


# -- A3 negative: a leaking artifact must be caught by leakage_scan -------------

def test_leakage_scan_catches_an_unredacted_failure_artifact(
    monkeypatch, tmp_path: Path
):
    sentinel_a = tmp_path / "sentinel-a.txt"
    sentinel_a.write_text("SENTINEL-ALPHA-7c1e", encoding="utf-8")
    sentinel_b = tmp_path / "sentinel-b.txt"
    sentinel_b.write_text("SENTINEL-BETA-93fd", encoding="utf-8")
    instance = _acceptance_with_real_roots(tmp_path, [sentinel_a, sentinel_b])
    _mock_leakage_scan_subprocess(monkeypatch)

    monkeypatch.setattr(
        acceptance.Acceptance,
        "_redact_failure_stream",
        lambda self, payload: payload.decode("utf-8", "replace"),
    )

    status_script = tmp_path / "status.sh"
    status_script.write_text(
        "#!/bin/bash\n"
        'echo "status line SENTINEL-ALPHA-7c1e"\n'
        'echo "err SENTINEL-BETA-93fd" 1>&2\n'
        "exit 3\n"
    )
    status_script.chmod(0o755)

    with pytest.raises(acceptance.CommandFailure):
        instance._run_recorded(
            ["/bin/bash", str(status_script)],
            label="host service status",
        )

    artifact = instance.receipt_root / "host-service-status-failure.txt"
    assert artifact.exists()

    with pytest.raises(
        acceptance.AcceptanceError,
        match="canary value escaped",
    ):
        instance.leakage_scan(control_pid=os.getpid())