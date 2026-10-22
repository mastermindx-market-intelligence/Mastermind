"""Hermetic receipt tests; child programs are local inert fixtures, never providers."""
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading

import pytest

import lane_runtime as lr


def identity(pid):
    return {
        "pid": pid, "pgid": pid, "session_id": pid,
        "boot_id": "fixture-boot", "process_start_identity": "fixture-generation-1",
        "effective_uid": os.geteuid(), "effective_gid": os.getegid(),
        "real_uid": os.getuid(), "real_gid": os.getgid(),
    }


@pytest.fixture(autouse=True)
def only_owned_fixture_processes(monkeypatch):
    # Kernel metadata and global census are not probed in these tests.
    monkeypatch.setattr(lr, "_observe_owned_launch_identity", identity, raising=False)
    monkeypatch.setattr(lr, "_session_pids", lambda pgid: ())

    def wait(proc, pgid, timeout):
        try:
            proc.wait(timeout=timeout)
            return "completed"
        except subprocess.TimeoutExpired:
            return "timeout"

    def terminate(proc, pgid, *, grace, reason):
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=2)
        return {"status": "settled", "reason": reason, "identity_verified": True,
                "census_proven": True, "residual_count": 0}

    monkeypatch.setattr(lr, "_wait_owned_process_with_fuse", wait)
    monkeypatch.setattr(lr, "_terminate_verified_group", terminate)


def command(marker, extra=""):
    return [sys.executable, "-c",
            "from pathlib import Path; import sys; "
            "Path(sys.argv[1]).write_text('executed'); print('fixture-complete')",
            str(marker), extra]


def test_receipt_is_published_before_target_exec_while_controller_is_alive(tmp_path, monkeypatch):
    launch = tmp_path / "launch.json"
    terminal = tmp_path / "terminal.jsonl"
    marker = tmp_path / "target-executed"
    before_publication = threading.Event()
    continue_publication = threading.Event()
    outcome = {}
    original = getattr(lr, "_publish_owned_launch_receipt", None)

    def pause(*args, **kwargs):
        before_publication.set()
        assert continue_publication.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(lr, "_publish_owned_launch_receipt", pause, raising=False)

    def run():
        try:
            outcome["result"] = lr.run_owned_process(
                command(marker, "private-argument-fixture"), timeout=3,
                receipt_path=terminal, launch_receipt_path=launch,
                launch_receipt_metadata={"root_id": "original-root", "attempt_id": "attempt-1",
                                         "effective_grant_sha256": "a" * 64},
            )
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    observed = before_publication.wait(1)
    try:
        assert observed, outcome.get("error")
        assert thread.is_alive()
        assert not marker.exists(), "target executed before immutable receipt"
        assert not launch.exists()
    finally:
        continue_publication.set()
        thread.join(4)
    assert "error" not in outcome, outcome.get("error")
    receipt = json.loads(launch.read_text())
    assert receipt["schema"] == "mastermind.local_owned_process_launch.v1"
    assert receipt["phase"] == "PRE_EXEC_HANDSHAKE"
    assert receipt["process_identity"]["pid"] == outcome["result"].pid
    assert receipt["process_identity"]["process_start_identity"] == "fixture-generation-1"
    assert receipt["correlation"]["attempt_id"] == "attempt-1"
    assert receipt["correlation_is_authority"] is False
    assert stat.S_IMODE(launch.stat().st_mode) == 0o400
    assert "private-argument-fixture" not in launch.read_text()
    assert marker.read_text() == "executed"
    assert outcome["result"].returncode == 0
    final = json.loads(terminal.read_text().splitlines()[-1])
    assert final["schema"] == "mastermind.local_owned_process_receipt.v1"
    assert final["pid"] == receipt["process_identity"]["pid"]
    assert final["returncode"] == 0
    assert final["cleanup"]["residual_count"] == 0


def test_existing_receipt_refuses_before_any_child_and_is_not_overwritten(tmp_path):
    launch = tmp_path / "launch.json"
    launch.write_bytes(b"original-immutable-receipt")
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(marker), timeout=1, launch_receipt_path=launch)
    assert launch.read_bytes() == b"original-immutable-receipt"
    assert not marker.exists()


@pytest.mark.parametrize("metadata", [
    {"authorities": ["ADMIN"]}, {"pid": 99}, {"root_id": "untrusted prompt\nroot"},
    {"effective_grant_sha256": "not-a-digest"}, {"attempt_id": ""},
])
def test_invalid_or_authority_shaped_metadata_refuses_before_target(tmp_path, metadata):
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=metadata)
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()


def test_generation_change_refuses_publication_and_target_exec(tmp_path, monkeypatch):
    calls = 0

    def moving(pid):
        nonlocal calls
        calls += 1
        return {**identity(pid), "process_start_identity": f"changed-{calls}"}

    monkeypatch.setattr(lr, "_observe_owned_launch_identity", moving)
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             receipt_path=tmp_path / "terminal.jsonl")
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()
    terminal = json.loads((tmp_path / "terminal.jsonl").read_text().splitlines()[-1])
    assert terminal["cleanup"]["reason"] == "parent_exception"


def test_publication_failure_keeps_target_gated_and_terminal_cleanup(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise lr.LaneRuntimeError("fixture-publication-failure")

    monkeypatch.setattr(lr, "_publish_owned_launch_receipt", fail)
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="fixture-publication-failure"):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             receipt_path=tmp_path / "terminal.jsonl")
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()
    terminal = json.loads((tmp_path / "terminal.jsonl").read_text().splitlines()[-1])
    assert terminal["cleanup"]["residual_count"] == 0


def test_legacy_call_keeps_terminal_behavior_without_launch_receipt(tmp_path):
    marker = tmp_path / "target-executed"
    result = lr.run_owned_process(command(marker), timeout=2, receipt_path=tmp_path / "terminal.jsonl")
    assert result.returncode == 0
    assert result.stdout.strip() == "fixture-complete"
    assert marker.exists()
    assert not (tmp_path / "launch.json").exists()


def test_receipt_parent_symlink_refuses_before_target(tmp_path):
    parent = tmp_path / "real"
    parent.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(marker), timeout=1, launch_receipt_path=alias / "launch.json")
    assert not marker.exists()


def test_metadata_without_receipt_path_refuses_before_target(tmp_path):
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(marker), timeout=1, launch_receipt_metadata={"root_id": "root"})
    assert not marker.exists()


def test_atomic_publication_never_overwrites_racing_receipt(tmp_path):
    launch = tmp_path / "launch.json"
    launch.write_bytes(b"racing-owner")
    with pytest.raises(lr.LaneRuntimeError):
        lr._write_immutable_launch_receipt(launch, {"schema": "fixture"})
    assert launch.read_bytes() == b"racing-owner"



@pytest.mark.parametrize("metadata", [[], [("root_id", "root")], 1, "root"])
def test_non_mapping_correlation_refuses_before_spawn(tmp_path, monkeypatch, metadata):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid correlation attempted a spawn")
    monkeypatch.setattr(lr.subprocess, "Popen", forbidden)
    with pytest.raises(lr.LaneRuntimeError, match="launch_correlation_invalid"):
        lr.run_owned_process([sys.executable, "-c", "pass"], timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=metadata)


def test_launch_gate_preserves_stdin_nonzero_exit_and_shell_argument_semantics(tmp_path):
    direct = lr.run_owned_process(
        [sys.executable, "-c", "import sys; print(sys.stdin.read()); sys.exit(7)"],
        input_text="inert fixture input", timeout=2,
        launch_receipt_path=tmp_path / "direct.json")
    assert direct.stdout.strip() == "inert fixture input"
    assert direct.returncode == 7
    shell = lr.run_owned_process(
        ['printf "%s" "$1"', "fixture-shell", "argument with spaces"],
        shell=True, timeout=2, launch_receipt_path=tmp_path / "shell.json")
    assert shell.returncode == 0
    assert shell.stdout == "argument with spaces"


def test_launch_gate_timeout_retains_early_and_terminal_receipts(tmp_path):
    result = lr.run_owned_process(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=.05, receipt_path=tmp_path / "terminal.jsonl",
        launch_receipt_path=tmp_path / "launch.json")
    assert result.timed_out is True
    assert result.cleanup["reason"] == "timeout"
    assert result.returncode == -9
    assert json.loads((tmp_path / "launch.json").read_text())["phase"] == "PRE_EXEC_HANDSHAKE"
    assert json.loads((tmp_path / "terminal.jsonl").read_text())["timed_out"] is True


def test_failed_publication_does_not_promote_unproven_cleanup(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise lr.LaneRuntimeError("publication-failed-fixture")
    def unproven(proc, pgid, *, grace, reason):
        proc.terminate()
        proc.wait(timeout=2)
        return {"status": "unproven", "reason": reason, "identity_verified": False,
                "census_proven": False, "residual_count": None}
    monkeypatch.setattr(lr, "_publish_owned_launch_receipt", fail)
    monkeypatch.setattr(lr, "_terminate_verified_group", unproven)
    with pytest.raises(lr.LaneRuntimeError):
        lr.run_owned_process(command(tmp_path / "target"), timeout=1,
            receipt_path=tmp_path / "terminal.jsonl",
            launch_receipt_path=tmp_path / "launch.json")
    terminal = json.loads((tmp_path / "terminal.jsonl").read_text())
    assert terminal["cleanup"]["census_proven"] is False
    assert terminal["cleanup"]["residual_count"] is None
    assert not (tmp_path / "target").exists()


def test_world_readable_parent_refuses_without_permission_repair(tmp_path, monkeypatch):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe directory attempted a spawn")
    monkeypatch.setattr(lr.subprocess, "Popen", forbidden)
    with pytest.raises(lr.LaneRuntimeError, match="launch_receipt_directory_unsafe"):
        lr.run_owned_process([sys.executable, "-c", "pass"], timeout=1,
                             launch_receipt_path=parent / "launch.json")
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755
