"""Prospective phase observability for the Executive acceptance harness.

Each guarded acceptance phase retains a write-once ``phase-<phase>-started``
receipt before its body and a ``phase-<phase>-finished`` receipt only after
the body returns normally, through the ordinary guarded receipt producer.
These tests prove the sanitized closed receipt schema (no job, path, payload,
or error detail; no acceptance verdict), the deterministic clock contract,
the failure semantics (a failed body keeps STARTED, never gains FINISHED,
and propagates the original exception), the write-once reuse refusal, and -
via a fully stubbed ``Acceptance.run`` - that the real run emits the phases
in order and that a failed phase leaves no later FINISHED receipt and no
acceptance summary.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "ops" / "executive_os" / "acceptance.py"
SPEC = importlib.util.spec_from_file_location(
    "executive_acceptance_phase_observability", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
acceptance = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = acceptance
SPEC.loader.exec_module(acceptance)


PHASE_SCHEMA = "mastermind.executive_acceptance_phase.v1"
CLOSED_FIELDS = {
    "schema_version",
    "phase",
    "state",
    "elapsed_seconds",
    "cpu_seconds",
    "observation_only",
}
PHASE_BODIES = {"maintenance.verify", "backup_restore", "leakage_scan", "maintenance.finish"}
PHASE_SEQUENCE_WITH_MAINTENANCE = [
    "write phase-maintenance_before_backup-started.json",
    "maintenance.verify",
    "write phase-maintenance_before_backup-finished.json",
    "write phase-backup_restore-started.json",
    "backup_restore",
    "write phase-backup_restore-finished.json",
    "write phase-maintenance_after_backup-started.json",
    "maintenance.verify",
    "write phase-maintenance_after_backup-finished.json",
    "write phase-credential_leakage_scan-started.json",
    "leakage_scan",
    "write phase-credential_leakage_scan-finished.json",
    "write phase-maintenance_finish-started.json",
    "maintenance.finish",
]
DIGEST = "a" * 64


class _FakePw:
    def __init__(self, uid: int) -> None:
        self.pw_uid = uid


class _FakeGr:
    def __init__(self, gid: int) -> None:
        self.gr_gid = gid


def _acceptance(tmp_path: Path):
    """An ``Acceptance`` bound only to what the receipt producer reads.

    ``Acceptance.__init__`` resolves the four dedicated host principals
    through ``pwd``/``grp``; those accounts exist only on the reviewed Mac
    Studio, so the hermetic tests bind the handful of attributes the guarded
    receipt path touches.
    """

    instance = object.__new__(acceptance.Acceptance)
    instance.receipt_root = tmp_path / "receipts"
    instance.receipt_root.mkdir(mode=0o700, parents=True)
    os.chmod(instance.receipt_root, 0o700)
    instance.control_identity = _FakePw(os.geteuid())
    instance.worker_identity = _FakePw(os.geteuid())
    instance.control_group = _FakeGr(os.getegid())
    instance.worker_group = _FakeGr(os.getegid())
    return instance


def _receipt(name: str, receipt_root: Path) -> dict:
    return json.loads((receipt_root / name).read_text(encoding="utf-8"))


def _assert_closed_receipt(receipt: dict, *, phase: str, state: str) -> None:
    assert set(receipt) == CLOSED_FIELDS
    assert receipt["schema_version"] == PHASE_SCHEMA
    assert receipt["phase"] == phase
    assert receipt["state"] == state
    assert receipt["observation_only"] is True
    for field in ("elapsed_seconds", "cpu_seconds"):
        value = receipt[field]
        assert isinstance(value, float)
        assert value >= 0.0
        assert math.isfinite(value)


def _phase_events(events: list[str]) -> list[str]:
    return [
        event for event in events
        if event in PHASE_BODIES or event.startswith("write phase-")
    ]


# ---------------------------------------------------------------------------
# Helper-level: sanitized closed schema and no input leakage
# ---------------------------------------------------------------------------


def test_phase_receipts_carry_only_closed_fields_and_never_body_values(tmp_path):
    instance = _acceptance(tmp_path)
    marker = "job-7f3a /var/db/private payload-secret"
    started_name = "phase-backup_restore-started.json"
    finished_name = "phase-backup_restore-finished.json"

    with instance._phase_observability("backup_restore"):
        pass  # the body may hold sensitive values; none may reach a receipt

    assert (instance.receipt_root / started_name).is_file()
    assert (instance.receipt_root / finished_name).is_file()
    started = _receipt(started_name, instance.receipt_root)
    finished = _receipt(finished_name, instance.receipt_root)
    _assert_closed_receipt(started, phase="backup_restore", state="STARTED")
    _assert_closed_receipt(finished, phase="backup_restore", state="FINISHED")
    # STARTED counters are zero; FINISHED measures real, finite, nonnegative
    # deltas from phase start under the unpatched clocks.
    assert started["elapsed_seconds"] == 0
    assert started["cpu_seconds"] == 0
    for name in (started_name, finished_name):
        raw = (instance.receipt_root / name).read_bytes()
        assert marker.encode("utf-8") not in raw
        assert b'"passed"' not in raw
    # The receipts reuse the guarded producer exactly: control-owned, 0o400.
    for name in (started_name, finished_name):
        info = (instance.receipt_root / name).stat()
        assert stat.S_IMODE(info.st_mode) == 0o400
        assert info.st_uid == os.geteuid()
        assert info.st_gid == os.getegid()
    # A phase receipt alone is never an acceptance summary.
    assert not (instance.receipt_root / "acceptance-summary.json").exists()


def test_unknown_phase_name_is_refused_before_any_receipt(tmp_path):
    instance = _acceptance(tmp_path)
    with pytest.raises(acceptance.AcceptanceError, match="unknown acceptance phase name"):
        with instance._phase_observability("unlisted_phase"):
            raise AssertionError("body must never run for an unknown phase")
    assert list(instance.receipt_root.iterdir()) == []


# ---------------------------------------------------------------------------
# Helper-level: deterministic clock contract
# ---------------------------------------------------------------------------


def test_finished_receipt_measures_monotonic_and_process_time_from_phase_start(
    tmp_path, monkeypatch
):
    instance = _acceptance(tmp_path)
    monotonic_values = iter([100.0, 102.5])
    process_time_values = iter([7.0, 9.25])
    monkeypatch.setattr(acceptance.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(acceptance.time, "process_time", lambda: next(process_time_values))

    with instance._phase_observability("maintenance_after_backup"):
        pass

    started = _receipt("phase-maintenance_after_backup-started.json", instance.receipt_root)
    finished = _receipt("phase-maintenance_after_backup-finished.json", instance.receipt_root)
    assert started["elapsed_seconds"] == 0
    assert started["cpu_seconds"] == 0
    assert finished["elapsed_seconds"] == 2.5
    assert finished["cpu_seconds"] == 2.25


def test_identical_clocks_produce_byte_identical_finished_receipts(tmp_path, monkeypatch):
    def measured(root: Path, monotonic_values, process_time_values) -> bytes:
        instance = _acceptance(root)
        monkeypatch.setattr(acceptance.time, "monotonic", lambda: next(monotonic_values))
        monkeypatch.setattr(
            acceptance.time, "process_time", lambda: next(process_time_values)
        )
        with instance._phase_observability("credential_leakage_scan"):
            pass
        finished = instance.receipt_root / "phase-credential_leakage_scan-finished.json"
        return finished.read_bytes()

    first = measured(tmp_path / "first", iter([10.0, 11.0]), iter([1.0, 1.5]))
    second = measured(tmp_path / "second", iter([900.0, 901.0]), iter([50.0, 50.5]))
    assert first == second


# ---------------------------------------------------------------------------
# Helper-level: failure semantics
# ---------------------------------------------------------------------------


def test_failed_phase_keeps_started_without_finished_and_propagates_original(tmp_path):
    instance = _acceptance(tmp_path)
    original = RuntimeError("original phase failure")

    with pytest.raises(RuntimeError) as raised:
        with instance._phase_observability("credential_leakage_scan"):
            raise original

    assert raised.value is original
    assert (instance.receipt_root / "phase-credential_leakage_scan-started.json").is_file()
    assert not (
        instance.receipt_root / "phase-credential_leakage_scan-finished.json"
    ).exists()
    # No exception detail may reach any receipt.
    for path in instance.receipt_root.iterdir():
        raw = path.read_bytes()
        assert b"original phase failure" not in raw
        assert b"RuntimeError" not in raw


def test_clock_failure_after_the_body_writes_no_finished_receipt(tmp_path, monkeypatch):
    instance = _acceptance(tmp_path)
    real_monotonic = time.monotonic
    calls = {"count": 0}

    def failing_monotonic() -> float:
        calls["count"] += 1
        if calls["count"] > 1:
            raise OSError("simulated clock failure")
        return real_monotonic()

    monkeypatch.setattr(acceptance.time, "monotonic", failing_monotonic)

    with pytest.raises(OSError, match="simulated clock failure"):
        with instance._phase_observability("maintenance_after_backup"):
            pass

    assert calls["count"] == 2
    assert (instance.receipt_root / "phase-maintenance_after_backup-started.json").is_file()
    assert not (
        instance.receipt_root / "phase-maintenance_after_backup-finished.json"
    ).exists()


def test_failed_start_receipt_refuses_to_run_the_body(tmp_path):
    instance = _acceptance(tmp_path)
    started = instance.receipt_root / "phase-backup_restore-started.json"
    started.write_bytes(b"pre-existing receipt\n")
    ran: list[bool] = []

    with pytest.raises(acceptance.AcceptanceError, match="acceptance receipt already exists"):
        with instance._phase_observability("backup_restore"):
            ran.append(True)

    assert ran == []
    assert started.read_bytes() == b"pre-existing receipt\n"


def test_phase_reuse_is_refused_by_the_write_once_receipt_path(tmp_path):
    instance = _acceptance(tmp_path)
    with instance._phase_observability("maintenance_before_backup"):
        pass
    started = instance.receipt_root / "phase-maintenance_before_backup-started.json"
    finished = instance.receipt_root / "phase-maintenance_before_backup-finished.json"
    started_before = started.read_bytes()
    finished_before = finished.read_bytes()

    with pytest.raises(acceptance.AcceptanceError, match="acceptance receipt already exists"):
        with instance._phase_observability("maintenance_before_backup"):
            raise AssertionError("body must never run when the start receipt is refused")

    # The refused reuse neither clobbers nor extends the retained receipts.
    assert started.read_bytes() == started_before
    assert finished.read_bytes() == finished_before
    assert sorted(path.name for path in instance.receipt_root.iterdir()) == [
        "phase-maintenance_before_backup-finished.json",
        "phase-maintenance_before_backup-started.json",
    ]


# ---------------------------------------------------------------------------
# Run-level: controlled ``Acceptance.run`` with stubbed host effects
# ---------------------------------------------------------------------------


def _stub_run(harness, tmp_path: Path, events: list[str]) -> None:
    """Bind stubs for every host effect ``run`` touches, keeping the real
    guarded receipt producer, phase helper, and ordering logic live."""

    harness.release = tmp_path / "release"
    harness.expected_sha = "b" * 40
    harness.nonexecutive_disabled_before = DIGEST

    def record(name: str):
        return lambda *args, **kwargs: events.append(name)

    def start_and_attest_services():
        events.append("start_and_attest_services")
        return 101, 202

    def successful_job() -> str:
        events.append("successful_job")
        return "success-job"

    def restart_after_completion(job_id: str, old_pid: int) -> int:
        events.append("restart_after_completion")
        return 1024

    def interrupted_job(control_pid: int, worker_pid: int):
        events.append("interrupted_job")
        return "interrupted-job", 2048, 4096

    def wait_control() -> int:
        events.append("wait_control")
        return 2048

    def wait_pid(label: str) -> int:
        events.append("wait_worker")
        return 4096

    def nonexecutive_disabled_digest() -> str:
        events.append("nonexecutive_digest")
        return DIGEST

    def fake_run_recorded(argv, *, label, **kwargs):
        events.append(label)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=b"ok\n", stderr=b"")

    def recording_write_json(name, value, *, replace=False):
        events.append(f"write {name}")
        return real_write_json(name, value, replace=replace)

    harness.validate_install = record("validate_install")
    harness.initialize_runtime_and_fixtures = record("initialize_runtime_and_fixtures")
    harness.start_and_attest_services = start_and_attest_services
    harness.successful_job = successful_job
    harness.restart_after_completion = restart_after_completion
    harness.interrupted_job = interrupted_job
    harness.backup_restore = record("backup_restore")
    harness._wait_control = wait_control
    harness._wait_pid = wait_pid
    harness._control_request = lambda command, *values, persist=None: {
        "result": {"service_state": "READY"}
    }
    harness._nonexecutive_disabled_digest = nonexecutive_disabled_digest
    harness._assert_no_public_listener = record("assert_no_public_listener")
    harness.leakage_scan = record("leakage_scan")
    harness._run_recorded = fake_run_recorded

    real_write_json = harness._write_json
    harness._write_json = recording_write_json


def _maintenance_stub(events: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        predecessor_recovery_required=False,
        verify=lambda proof_ids: events.append("maintenance.verify"),
        finish=lambda proof_ids, summary: events.append("maintenance.finish"),
    )


def test_run_emits_phase_receipts_and_preserves_summary_carry_order(tmp_path):
    harness = _acceptance(tmp_path)
    events: list[str] = []
    _stub_run(harness, tmp_path, events)
    harness.maintenance = _maintenance_stub(events)

    harness.run()

    assert _phase_events(events) == PHASE_SEQUENCE_WITH_MAINTENANCE
    # The summary is written by the pre-existing path, after the last host
    # phase finishes and before the final maintenance phase starts, and it
    # remains the only acceptance verdict.
    assert events.index("write acceptance-summary.json") > events.index(
        "write phase-credential_leakage_scan-finished.json"
    )
    assert events.index("write acceptance-summary.json") < events.index(
        "write phase-maintenance_finish-started.json"
    )
    written = sorted(path.name for path in harness.receipt_root.iterdir())
    assert written == [
        "acceptance-summary.json",
        "final-host-status.txt",
        "nonexecutive-launchd-after.json",
        "phase-backup_restore-finished.json",
        "phase-backup_restore-started.json",
        "phase-credential_leakage_scan-finished.json",
        "phase-credential_leakage_scan-started.json",
        "phase-maintenance_after_backup-finished.json",
        "phase-maintenance_after_backup-started.json",
        "phase-maintenance_before_backup-finished.json",
        "phase-maintenance_before_backup-started.json",
        "phase-maintenance_finish-started.json",
    ]
    summary = _receipt("acceptance-summary.json", harness.receipt_root)
    assert summary["passed"] is True
    assert summary["schema_version"] == acceptance.SCHEMA_VERSION
    for name in written:
        if name.startswith("phase-"):
            assert "passed" not in _receipt(name, harness.receipt_root)


def test_run_without_maintenance_emits_only_non_maintenance_phases(tmp_path):
    harness = _acceptance(tmp_path)
    events: list[str] = []
    _stub_run(harness, tmp_path, events)
    harness.maintenance = None

    harness.run()

    assert _phase_events(events) == [
        "write phase-backup_restore-started.json",
        "backup_restore",
        "write phase-backup_restore-finished.json",
        "write phase-credential_leakage_scan-started.json",
        "leakage_scan",
        "write phase-credential_leakage_scan-finished.json",
    ]
    assert "maintenance.finish" not in events
    assert sorted(path.name for path in harness.receipt_root.iterdir()) == [
        "acceptance-summary.json",
        "final-host-status.txt",
        "nonexecutive-launchd-after.json",
        "phase-backup_restore-finished.json",
        "phase-backup_restore-started.json",
        "phase-credential_leakage_scan-finished.json",
        "phase-credential_leakage_scan-started.json",
    ]


def test_run_failed_phase_leaves_no_later_phase_receipts_or_summary(tmp_path):
    harness = _acceptance(tmp_path)
    events: list[str] = []
    _stub_run(harness, tmp_path, events)
    harness.maintenance = _maintenance_stub(events)
    original = RuntimeError("leakage scan failed")

    def failing_leakage_scan(control_pid):
        events.append("leakage_scan")
        raise original

    harness.leakage_scan = failing_leakage_scan

    with pytest.raises(RuntimeError) as raised:
        harness.run()

    assert raised.value is original
    # The failing phase is reached last among host phases; nothing after it ran.
    assert _phase_events(events) == PHASE_SEQUENCE_WITH_MAINTENANCE[:11]
    assert "maintenance.finish" not in events
    receipt_root = harness.receipt_root
    # Earlier phases completed normally.
    assert _receipt(
        "phase-maintenance_after_backup-finished.json", receipt_root
    )["state"] == "FINISHED"
    # The failing phase keeps its STARTED receipt only.
    assert (receipt_root / "phase-credential_leakage_scan-started.json").is_file()
    assert not (receipt_root / "phase-credential_leakage_scan-finished.json").exists()
    # No later phase receipt and no acceptance summary may exist.
    for name in (
        "phase-maintenance_finish-started.json",
        "acceptance-summary.json",
        "final-host-status.txt",
    ):
        assert not (receipt_root / name).exists()


def test_canonical_finish_has_no_followup_progress_write_or_clock_read(tmp_path, monkeypatch):
    harness = _acceptance(tmp_path)
    events: list[str] = []
    _stub_run(harness, tmp_path, events)
    harness.maintenance = _maintenance_stub(events)
    canonical_carry = tmp_path / "canonical-carry.json"
    committed = False
    real_write_json = harness._write_json
    real_monotonic = acceptance.time.monotonic
    real_process_time = acceptance.time.process_time

    def finish(proof_ids, summary):
        nonlocal committed
        events.append("maintenance.finish")
        canonical_carry.write_text('{"passed": true}\n', encoding="utf-8")
        committed = True

    def write_json(name, value, **kwargs):
        if committed:
            raise AssertionError("progress write after canonical finish")
        return real_write_json(name, value, **kwargs)

    def monotonic():
        if committed:
            raise AssertionError("progress clock read after canonical finish")
        return real_monotonic()

    def process_time():
        if committed:
            raise AssertionError("progress CPU clock read after canonical finish")
        return real_process_time()

    harness.maintenance.finish = finish
    harness._write_json = write_json
    monkeypatch.setattr(acceptance.time, "monotonic", monotonic)
    monkeypatch.setattr(acceptance.time, "process_time", process_time)

    harness.run()

    assert committed
    assert json.loads(canonical_carry.read_text()) == {"passed": True}
    assert events.count("maintenance.finish") == 1
    assert events[-1] == "maintenance.finish"
    started = _receipt("phase-maintenance_finish-started.json", harness.receipt_root)
    _assert_closed_receipt(started, phase="maintenance_finish", state="STARTED")
    assert not (harness.receipt_root / "phase-maintenance_finish-finished.json").exists()


def test_actual_canonical_finish_error_propagates_without_finished_progress(tmp_path):
    harness = _acceptance(tmp_path)
    events: list[str] = []
    _stub_run(harness, tmp_path, events)
    harness.maintenance = _maintenance_stub(events)
    original = RuntimeError("canonical finish refused")

    def finish(proof_ids, summary):
        raise original

    harness.maintenance.finish = finish
    with pytest.raises(RuntimeError) as raised:
        harness.run()

    assert raised.value is original
    started = _receipt("phase-maintenance_finish-started.json", harness.receipt_root)
    _assert_closed_receipt(started, phase="maintenance_finish", state="STARTED")
    assert not (harness.receipt_root / "phase-maintenance_finish-finished.json").exists()
    assert "passed" not in started and "error" not in started
    # The pre-existing summary-before-carry order stays unchanged; phase STARTED
    # does not substitute for the canonical carry that this finish refused.
    assert (harness.receipt_root / "acceptance-summary.json").is_file()
