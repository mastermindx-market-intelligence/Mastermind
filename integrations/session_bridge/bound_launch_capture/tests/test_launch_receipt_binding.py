"""Focused atomic launch-binding correlation tests.

Child programs are local inert fixtures, never providers. Kernel identity and
session census are mocked; no host effect, live identity read or provider
request is made. The new binding keys are receipt-only correlation and never
authorize or alter the launch.
"""
import inspect
import hashlib
import json
import os
import stat
import subprocess
import sys
import threading

import pytest

import lane_runtime as lr

FULL_BINDING = {
    "root_id": "binding-root-01a11e90",
    "job_id": "job-binding-fixture",
    "attempt_id": "attempt-1",
    "effective_grant_sha256": "a" * 64,
    "commission_sha256": "b" * 64,
    "physical_binding_sha256": "c" * 64,
    "start_request_sha256": "d" * 64,
}
LEGACY_KEYS = ("root_id", "job_id", "attempt_id",
               "effective_grant_sha256", "commission_sha256")
BINDING_KEYS = ("physical_binding_sha256", "start_request_sha256")
LEGACY_ONLY = {k: FULL_BINDING[k] for k in LEGACY_KEYS}
ORIGINAL_ALL = frozenset({
    "HostAdmissionSnapshot", "LaneOccupancySnapshot", "read_lane_occupancy",
    "LaneAdmissionRefused", "LaneLease", "LaneRuntimeConfig",
    "LaneRuntimeConfigError", "LaneRuntimeError", "ProcessCensusError",
    "OwnedProcessResult", "cancel_current_owned_process",
    "cleanup_receipt_is_proven", "evaluate_admission",
    "enforce_remote_first_lane_launch", "install_signal_cleanup",
    "load_runtime_config", "process_exists", "run_owned_process",
})


def identity(pid):
    return {
        "pid": pid, "pgid": pid, "session_id": pid,
        "boot_id": "fixture-boot", "process_start_identity": "fixture-generation-1",
        "effective_uid": os.geteuid(), "effective_gid": os.getegid(),
        "real_uid": os.getuid(), "real_gid": os.getgid(),
    }


@pytest.fixture(autouse=True)
def only_owned_fixture_processes(monkeypatch):
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


def command(marker):
    return [sys.executable, "-c",
            "from pathlib import Path; import sys; "
            "Path(sys.argv[1]).write_text('executed'); print('fixture-complete')",
            str(marker)]


def forbidden(*args, **kwargs):
    pytest.fail("refused metadata reached a spawn")


@pytest.fixture
def no_spawn(monkeypatch):
    monkeypatch.setattr(lr.subprocess, "Popen", forbidden)


def test_complete_binding_launch_succeeds_with_exact_receipt_mapping(tmp_path):
    launch = tmp_path / "launch.json"
    terminal = tmp_path / "terminal.jsonl"
    marker = tmp_path / "target-executed"
    result = lr.run_owned_process(
        command(marker), timeout=3, receipt_path=terminal,
        launch_receipt_path=launch, launch_receipt_metadata=dict(FULL_BINDING))
    assert result.returncode == 0
    assert marker.read_text() == "executed"
    assert FULL_BINDING["physical_binding_sha256"] not in result.stdout
    assert FULL_BINDING["start_request_sha256"] not in result.stdout
    receipt = json.loads(launch.read_text())
    assert receipt["schema"] == "mastermind.local_owned_process_launch.v1"
    assert receipt["phase"] == "PRE_EXEC_HANDSHAKE"
    assert receipt["correlation"] == FULL_BINDING
    assert set(receipt["correlation"]) == set(FULL_BINDING)
    assert receipt["correlation_is_authority"] is False
    assert receipt["provider_execution_attested"] is False
    assert receipt["executable_kind"] == "isolated-python-exec-gate"
    assert receipt["process_identity"]["pid"] == result.pid
    assert stat.S_IMODE(launch.stat().st_mode) == 0o400
    record = json.loads(terminal.read_text().splitlines()[-1])
    assert record["pid"] == result.pid
    assert record["returncode"] == 0
    assert "correlation" not in record


def test_snapshot_digest_and_exact_early_receipt_are_retained_in_terminal(tmp_path):
    launch, terminal = tmp_path / "launch.json", tmp_path / "terminal.jsonl"
    result = lr.run_owned_process(command(tmp_path / "marker"), timeout=3,
        receipt_path=terminal, launch_receipt_path=launch,
        launch_receipt_metadata=dict(FULL_BINDING), launch_receipt_context_sha256="e" * 64)
    assert result.returncode == 0
    receipt = json.loads(launch.read_text())
    row = json.loads(terminal.read_text().splitlines()[-1])
    assert receipt["context_sha256"] == "e" * 64
    assert row["launch_capture"]["receipt_sha256"] == hashlib.sha256(launch.read_bytes()).hexdigest()
    assert row["launch_capture"]["context_sha256"] == receipt["context_sha256"]


@pytest.mark.parametrize("stage", ["construct_stdout", "construct_stderr", "start_stdout", "start_stderr"])
def test_collector_startup_failure_closes_gate_and_preserves_failed_capture(tmp_path, monkeypatch, stage):
    original = lr._BoundedStreamCollector
    processes = []
    popen = lr.subprocess.Popen
    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process
    def collector(stream, limit, name):
        if stage == "construct_" + name:
            raise RuntimeError("inert collector constructor failure")
        result = original(stream, limit, name)
        if stage == "start_" + name:
            def fail():
                raise RuntimeError("inert collector start failure")
            result.start = fail
        return result
    monkeypatch.setattr(lr.subprocess, "Popen", capture)
    monkeypatch.setattr(lr, "_BoundedStreamCollector", collector)
    marker, launch, terminal = tmp_path / "marker", tmp_path / "launch.json", tmp_path / "terminal.jsonl"
    with pytest.raises(RuntimeError, match="inert collector"):
        lr.run_owned_process(command(marker), timeout=3, receipt_path=terminal,
            launch_receipt_path=launch, launch_receipt_metadata=dict(FULL_BINDING))
    assert len(processes) == 1 and processes[0].poll() is not None
    assert not marker.exists() and not launch.exists()
    row = json.loads(terminal.read_text().splitlines()[-1])
    assert row["returncode"] != 0
    assert not lr.cleanup_receipt_is_proven(row["cleanup"])
    assert row["cleanup"]["stderr_capture_complete"] is False
    assert lr._CURRENT_PROCESS is None
    assert row["launch_capture"]["provider_execution_attested"] is False
    assert row["launch_capture"]["phase"] == "PRE_EXEC_HANDSHAKE"


@pytest.mark.parametrize("digest", ["", "F" * 64, "g" * 64, "a" * 63, 42])
def test_invalid_context_digest_refuses_before_spawn(tmp_path, no_spawn, digest):
    with pytest.raises(lr.LaneRuntimeError, match="launch_context_digest_invalid"):
        lr.run_owned_process(command(tmp_path / "marker"), timeout=1,
            launch_receipt_path=tmp_path / "launch.json",
            launch_receipt_metadata=dict(FULL_BINDING), launch_receipt_context_sha256=digest)


def test_context_digest_without_receipt_refuses_before_spawn(tmp_path, no_spawn):
    with pytest.raises(lr.LaneRuntimeError, match="launch_context_digest_invalid"):
        lr.run_owned_process(command(tmp_path / "marker"), timeout=1,
                             launch_receipt_context_sha256="a" * 64)


def test_binding_publication_precedes_target_exec(tmp_path, monkeypatch):
    launch = tmp_path / "launch.json"
    marker = tmp_path / "target-executed"
    observed = {}
    original = lr._publish_owned_launch_receipt

    def checked(path, proc, label, context):
        observed["context"] = context
        observed["target_executed"] = marker.exists()
        return original(path, proc, label, context)

    monkeypatch.setattr(lr, "_publish_owned_launch_receipt", checked, raising=False)
    result = lr.run_owned_process(
        command(marker), timeout=3, launch_receipt_path=launch,
        launch_receipt_metadata=dict(FULL_BINDING))
    assert result.returncode == 0
    assert observed["target_executed"] is False
    assert observed["context"] == FULL_BINDING
    assert marker.exists()


def test_launch_receipt_input_accepts_complete_binding(tmp_path):
    destination, context = lr._launch_receipt_input(
        tmp_path / "launch.json", dict(FULL_BINDING))
    assert destination == tmp_path / "launch.json"
    assert context == FULL_BINDING


def test_launch_receipt_input_refuses_binding_key_alone(tmp_path):
    with pytest.raises(lr.LaneRuntimeError, match="launch_binding_incomplete"):
        lr._launch_receipt_input(
            tmp_path / "launch.json", {"physical_binding_sha256": "c" * 64})


@pytest.mark.parametrize("partial", (
    [{k: FULL_BINDING[k] for k in BINDING_KEYS},
     {k: FULL_BINDING[k] for k in ("physical_binding_sha256",)},
     {k: FULL_BINDING[k] for k in ("start_request_sha256",)}]
    + [{k: v for k, v in FULL_BINDING.items() if k != missing}
       for missing in LEGACY_KEYS]
))
def test_partial_binding_refuses_before_spawn(tmp_path, no_spawn, partial):
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="launch_binding_incomplete"):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=partial)
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()


@pytest.mark.parametrize("override", (
    ("physical_binding_sha256", "C" * 64),
    ("physical_binding_sha256", "z" * 64),
    ("start_request_sha256", "d" * 63),
    ("start_request_sha256", "d" * 65),
    ("effective_grant_sha256", "not-a-digest"),
    ("root_id", "untrusted prompt\nroot"),
    ("job_id", ""),
    ("attempt_id", 12),
))
def test_binding_invalid_values_refuse_before_spawn(tmp_path, no_spawn, override):
    metadata = dict(FULL_BINDING)
    key, value = override
    metadata[key] = value
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="launch_correlation_invalid"):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=metadata)
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()


def test_unknown_field_with_binding_refuses_before_spawn(tmp_path, no_spawn):
    metadata = {**FULL_BINDING, "grant_sha256": "e" * 64}
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="launch_correlation_invalid"):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=metadata)
    assert not marker.exists()


def test_binding_metadata_without_receipt_path_refuses_before_spawn(tmp_path, no_spawn):
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="launch_metadata_without_receipt"):
        lr.run_owned_process(command(marker), timeout=1,
                             launch_receipt_metadata=dict(FULL_BINDING))
    assert not marker.exists()


def test_legacy_subset_metadata_remains_compatible(tmp_path):
    launch = tmp_path / "launch.json"
    marker = tmp_path / "target-executed"
    legacy = {"root_id": "original-root", "attempt_id": "attempt-1",
              "effective_grant_sha256": "a" * 64}
    result = lr.run_owned_process(command(marker), timeout=3,
                                  launch_receipt_path=launch,
                                  launch_receipt_metadata=legacy)
    assert result.returncode == 0
    assert marker.exists()
    receipt = json.loads(launch.read_text())
    assert receipt["correlation"] == legacy
    assert not (set(receipt["correlation"]) & set(BINDING_KEYS))
    assert receipt["correlation_is_authority"] is False


def test_full_legacy_set_without_binding_keys_remains_compatible(tmp_path):
    launch = tmp_path / "launch.json"
    marker = tmp_path / "target-executed"
    result = lr.run_owned_process(command(marker), timeout=3,
                                  launch_receipt_path=launch,
                                  launch_receipt_metadata=dict(LEGACY_ONLY))
    assert result.returncode == 0
    assert marker.exists()
    assert json.loads(launch.read_text())["correlation"] == LEGACY_ONLY


def test_binding_metadata_still_gates_target_on_publication_failure(
        tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise lr.LaneRuntimeError("fixture-publication-failure")

    monkeypatch.setattr(lr, "_publish_owned_launch_receipt", fail)
    marker = tmp_path / "target-executed"
    with pytest.raises(lr.LaneRuntimeError, match="fixture-publication-failure"):
        lr.run_owned_process(command(marker), timeout=1,
                             receipt_path=tmp_path / "terminal.jsonl",
                             launch_receipt_path=tmp_path / "launch.json",
                             launch_receipt_metadata=dict(FULL_BINDING))
    assert not marker.exists()
    assert not (tmp_path / "launch.json").exists()
    terminal = json.loads((tmp_path / "terminal.jsonl").read_text().splitlines()[-1])
    assert terminal["cleanup"]["reason"] == "parent_exception"


INSTALLED_SYMBOLS = (
    "_preexec_incident_contract", "_preexec_original_identity",
    "_preexec_service_bindings", "validate_preexec_settlement_receipt",
    "_linux_cpu_tctl_c", "_owned_shell", "_append_process_receipt",
    "_scan_lane_markers", "_BoundedStreamCollector", "_start_input_writer",
    "read_lane_occupancy", "evaluate_admission",
    "enforce_remote_first_lane_launch", "install_signal_cleanup",
    "settle_owned_process_session", "cancel_current_owned_process",
    "cleanup_receipt_is_proven", "process_exists", "load_runtime_config",
    "parse_bounded_seconds", "LaneLease", "OwnedProcessResult",
    "OwnedProcessStartError", "HostAdmissionSnapshot",
)


def test_installed_surface_and_signature_preserved():
    assert set(lr.__all__) == ORIGINAL_ALL
    for name in INSTALLED_SYMBOLS:
        assert hasattr(lr, name), name
    parameters = inspect.signature(lr.run_owned_process).parameters
    assert tuple(parameters) == (
        "command", "cwd", "timeout", "input_text", "shell", "env", "nice",
        "terminate_grace", "label", "receipt_path", "timeout_returncode",
        "capture_limit_bytes", "receipt_diagnostics", "launch_receipt_path",
        "launch_receipt_metadata", "launch_receipt_context_sha256",
        "owned_capture_run_dir", "owned_capture_result_schema_json", "owned_capture_assignment")
    assert lr.LAUNCH_RECEIPT_SCHEMA == "mastermind.local_owned_process_launch.v1"
    assert lr._LAUNCH_BINDING_FIELDS == frozenset(BINDING_KEYS)


def test_preexec_incident_contracts_still_closed():
    with pytest.raises(lr.LaneRuntimeError, match="preexec_incident_refused"):
        lr._preexec_incident_contract("unknown-run")
    expected, required = lr._preexec_incident_contract(None)
    assert expected[0] == "paper-01a1101f-qualifier-review-r2"
    assert required["schema"] == "mastermind.exact-preexec-recovery.v1"
    with pytest.raises(lr.LaneRuntimeError, match="preexec_receipt_shape"):
        lr.validate_preexec_settlement_receipt({})


def test_terminal_capture_and_cleanup_behavior_preserved(tmp_path):
    marker = tmp_path / "target-executed"
    terminal = tmp_path / "terminal.jsonl"
    diagnostics = {"operator": "fixture"}
    result = lr.run_owned_process(command(marker), timeout=3,
                                  receipt_path=terminal,
                                  receipt_diagnostics=lambda: dict(diagnostics))
    assert result.stdout.strip() == "fixture-complete"
    assert result.stdout_bytes > 0
    assert result.cleanup["residual_count"] == 0
    assert lr.cleanup_receipt_is_proven(result.cleanup)
    record = json.loads(terminal.read_text().splitlines()[-1])
    assert record["returncode"] == 0
    assert record["runtime_failure_code"] is None
    assert record["operator_hook_diagnostics"] == diagnostics
    assert record["stdout_sha256"] is not None
    assert marker.exists()
