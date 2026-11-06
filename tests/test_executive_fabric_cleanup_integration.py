"""Inert Supervisor/Fabric composition; fixtures are no live host proof."""
import copy
import asyncio
import dataclasses
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
import control_plane.executive_supervisor as owner
from tests.test_executive_supervisor import (_runtime_and_job, FakeAdapter, FakeInspector,
                                             RestartCapableFakeAdapter, _supervisor)
from tests.test_fabric_cleanup_contract import example


def _policy():
    assert hasattr(owner, "CleanupPolicy"), "Supervisor lacks opt-in cleanup policy"
    return owner.CleanupPolicy.FABRIC_PROCESS_GROUP


@pytest.fixture
def composed(tmp_path, example, monkeypatch):
    runtime, job_id, workspace = _runtime_and_job(tmp_path)
    job = runtime.jobs.get_job(job_id)
    attempt = SimpleNamespace(attempt_id="ATT-1", job_id=job_id,
                              effective_grant_digest="a" * 64, pid=100, pgid=100,
                              process_start_identity="ticks:200", boot_id="boot-1")
    example["receipt"]["binding"].update(root_id=job.root_job_id, job_id=job_id)
    example["expected_binding"].update(root_id=job.root_job_id, job_id=job_id)
    adapter = AttendedFabricWorkerAdapter(runtime, lambda *_args: None)
    expectation = dict(binding=example["expected_binding"],
                       physical_binding_sha256=example["expected_physical_binding_sha256"],
                       process_identity=example["expected_process_identity"],
                       worker_uid=501, worker_gid=20)
    package = dict(schema_version="mastermind.executive_fabric_cleanup_evidence/v1",
                   operation="terminal", observed_at="2026-10-11T10:00:20+00:00",
                   worker_uid=501, worker_gid=20, receipt=example["receipt"],
                   lane_receipt_utf8=example["lane_receipt_bytes"].decode())
    calls = []

    def retained(subject, *, operation, observed_after):
        calls.append((operation, observed_after))
        return copy.deepcopy(package)

    adapter.fabric_cleanup_expectation = lambda subject: copy.deepcopy(expectation)
    adapter.fabric_cleanup_receipt = retained
    adapter.fabric_cleanup_receipt_readback = lambda subject, *, operation: copy.deepcopy(package)
    supervisor = ExecutiveSupervisor(runtime, adapter, cleanup_policy=_policy(),
        require_complete_launch_attestation=True, runs_root=tmp_path / "runs")
    ref = SimpleNamespace(run_id="ATT-1", started_at="2026-10-11T10:00:00+00:00",
                          **example["expected_process_identity"])
    active = SimpleNamespace(lease=SimpleNamespace(attempt=attempt), process_ref=ref)
    return SimpleNamespace(supervisor=supervisor, adapter=adapter, attempt=attempt,
        ref=ref, active=active, package=package, expectation=expectation, calls=calls,
        workspace=workspace, monkeypatch=monkeypatch)


def test_existing_dedicated_uid_default_is_unchanged(tmp_path):
    runtime, _, _ = _runtime_and_job(tmp_path)
    adapter = FakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    assert getattr(supervisor, "cleanup_policy", None) == owner.CleanupPolicy.DEDICATED_UID
    assert supervisor.require_complete_launch_attestation is True


def test_fabric_policy_rejects_other_adapter_class(tmp_path):
    runtime, _, _ = _runtime_and_job(tmp_path)
    with pytest.raises(SupervisorError):
        ExecutiveSupervisor(runtime, FakeAdapter(FakeInspector()), cleanup_policy=_policy(),
                            require_complete_launch_attestation=True)


def test_fabric_policy_requires_full_launch_attestation(tmp_path):
    runtime, _, _ = _runtime_and_job(tmp_path)
    adapter = AttendedFabricWorkerAdapter(runtime, lambda *_args: None)
    with pytest.raises(SupervisorError):
        ExecutiveSupervisor(runtime, adapter, cleanup_policy=_policy())


def test_fabric_policy_rejects_subclass_and_foreign_runtime(tmp_path):
    runtime, _, _ = _runtime_and_job(tmp_path)
    class Unreviewed(AttendedFabricWorkerAdapter):
        pass
    for adapter in (Unreviewed(runtime, lambda *_args: None),
                    AttendedFabricWorkerAdapter(runtime, lambda *_args: None)):
        if type(adapter) is AttendedFabricWorkerAdapter:
            adapter.runtime = object()
        with pytest.raises(SupervisorError):
            ExecutiveSupervisor(runtime, adapter, cleanup_policy=_policy(),
                                require_complete_launch_attestation=True)


def test_fabric_policy_cannot_use_local_process_controller(composed):
    with pytest.raises(SupervisorError):
        ExecutiveSupervisor(composed.adapter.runtime, composed.adapter,
            cleanup_policy=_policy(), require_complete_launch_attestation=True,
            process_controller=object())


def test_cached_positive_same_run_receipt_is_separate_from_uid_proof(composed):
    # Evidence can predate this cached read; it must still follow the actual launch.
    evidence = composed.supervisor._active_terminal_uid_sweep(composed.active)
    assert evidence["schema_version"] == "mastermind.executive_fabric_cleanup_evidence/v1"
    assert evidence == composed.package
    assert composed.calls == [("terminal", datetime(2026, 10, 11, 10, tzinfo=timezone.utc).timestamp())]
    with pytest.raises(owner.TerminalAssignmentSealError):
        composed.supervisor._validate_terminal_uid_sweep(evidence)


@pytest.mark.parametrize("field,value", [("worker_uid", 502), ("worker_gid", 21),
    ("operation", "restart_absence"), ("observed_at", "2026-10-11T09:59:59+00:00"),
    ("observed_at", "2999-10-11T10:00:00+00:00"), ("observed_at", "not-a-time")])
def test_foreign_principal_operation_or_observation_is_refused(composed, field, value):
    composed.package[field] = value
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


@pytest.mark.parametrize("field,value", [("root_id", "foreign-root"),
    ("attempt_id", "ATT-2"), ("effective_grant_digest", "e" * 64)])
def test_foreign_owner_contract_never_satisfies_supervisor(composed, field, value):
    composed.package["receipt"]["binding"][field] = value
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


def test_absent_actual_source_bytes_are_refused(composed):
    composed.package["lane_receipt_utf8"] = ""
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


def test_second_receipt_must_equal_retained_authenticated_package(composed):
    other = copy.deepcopy(composed.package)
    other["observed_at"] = "2026-10-11T10:00:21+00:00"
    composed.adapter.fabric_cleanup_receipt_readback = lambda *_args, **_kwargs: other
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


def test_expected_principal_drift_between_reads_is_refused(composed):
    def readback(*_args, **_kwargs):
        composed.expectation["worker_uid"] = 502
        return copy.deepcopy(composed.package)
    composed.adapter.fabric_cleanup_receipt_readback = readback
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


@pytest.mark.parametrize("operation", ["restart_absence", "unbound_absence"])
def test_old_receipt_cannot_prove_fresh_restart_or_unbound_absence(composed, operation):
    composed.package["operation"] = operation
    with pytest.raises(SupervisorError):
        if operation == "restart_absence":
            composed.supervisor._restart_uid_sweep(composed.attempt)
        else:
            composed.supervisor._cleanup_unbound_claim(composed.attempt)


@pytest.mark.parametrize("operation", ["restart_absence", "unbound_absence"])
def test_fresh_same_run_restart_evidence_is_accepted_without_uid_sweep(composed, operation):
    composed.package["operation"] = operation
    retained = composed.adapter.fabric_cleanup_receipt
    def fresh(subject, *, operation, observed_after):
        composed.package["observed_at"] = datetime.now(timezone.utc).isoformat()
        return retained(subject, operation=operation, observed_after=observed_after)
    composed.adapter.fabric_cleanup_receipt = fresh
    evidence = (composed.supervisor._restart_uid_sweep(composed.attempt)
        if operation == "restart_absence" else composed.supervisor._cleanup_unbound_claim(composed.attempt))
    assert evidence["operation"] == operation


@pytest.mark.parametrize("require_uid_sweep", [None, False])
def test_group_cleanup_cannot_invent_assignment_revocation(composed, tmp_path, monkeypatch, require_uid_sweep):
    evidence = composed.supervisor._active_terminal_uid_sweep(composed.active)
    # Even valid cleanup must not call the UID-dependent local chmod helper.
    monkeypatch.setattr(owner, "seal_control_owned_paths", lambda *_args, **_kwargs:
        pytest.fail("Fabric must not claim local UID-based traversal revocation"))
    with pytest.raises(owner.TerminalAssignmentSealError, match="UNAVAILABLE"):
        composed.supervisor._seal_terminal_assignment(attempt_id="ATT-1",
            job_id=composed.attempt.job_id, workspace=composed.workspace,
            run_dir=tmp_path / "runs" / "ATT-1", uid_sweep=evidence,
            require_uid_sweep=require_uid_sweep)
    assert not composed.supervisor._terminal_assignment_receipt_path("ATT-1").exists()


def test_fabric_validation_persistence_names_capability_explicitly(composed, tmp_path):
    composed.package["operation"] = "validation"
    composed.active.launch_spec = SimpleNamespace(run_dir=tmp_path / "runs" / "ATT-1")
    composed.active.effective_grant = None
    path = composed.supervisor._persist_validations(composed.active, ())
    payload = json.loads(path.read_text())
    assert payload["fabric_cleanup"] == composed.package
    assert "uid_sweep" not in payload


def test_launch_principal_cannot_be_replaced_by_a_matching_owner_assertion(composed):
    composed.ref.effective_uid = 502
    with pytest.raises(SupervisorError):
        composed.supervisor._active_terminal_uid_sweep(composed.active)


@pytest.mark.parametrize("requires_attempt_lease,requires_recovery_lease", [(True, False), (True, True)])
def test_only_explicit_recovery_flag_passes_the_adopted_lease(
        tmp_path, requires_attempt_lease, requires_recovery_lease):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first = RestartCapableFakeAdapter(inspector)
    active = asyncio.run(_supervisor(runtime, tmp_path, first).start_job(job_id))
    second = RestartCapableFakeAdapter(inspector)
    second.requires_attempt_lease = requires_attempt_lease
    second.requires_recovery_lease = requires_recovery_lease
    original = second.reattach
    passed_leases = []
    if requires_recovery_lease:
        def leased(spec, binding, *, lease):
            passed_leases.append(lease)
            assert lease.attempt.attempt_id == active.lease.attempt.attempt_id
            assert lease.attempt.fence_generation == active.lease.attempt.fence_generation + 1
            return original(spec, binding)
        second.reattach = leased
    restarted = _supervisor(runtime, tmp_path, second)
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert [item.status for item in outcomes] == [owner.ReconcileStatus.LIVE_RECOVERED]
    assert len(passed_leases) == int(requires_recovery_lease)
    assert second.start_calls == 0


def test_absent_fabric_cleanup_never_terminalizes_durable_attempt(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    fake = FakeAdapter(FakeInspector())
    active = asyncio.run(_supervisor(runtime, tmp_path, fake).start_job(job_id))
    collection = asyncio.run(fake.collect_result(active.process_ref))
    collection = dataclasses.replace(collection, result=dataclasses.replace(
        collection.result, status=owner.WorkerRunStatus.FAILED, exit_code=1))
    actual_adapter = AttendedFabricWorkerAdapter(runtime, lambda *_args: None)
    supervisor = ExecutiveSupervisor(runtime, actual_adapter, cleanup_policy=_policy(),
        require_complete_launch_attestation=True, runs_root=tmp_path / "runs")
    with pytest.raises(SupervisorError):
        asyncio.run(supervisor._terminalize(active, collection, tmp_path / "collection.json"))
    assert runtime.attempts.get_attempt(active.lease.attempt.attempt_id).status is owner.AttemptStatus.CHECKPOINTED
    assert runtime.jobs.get_job(job_id).status is owner.JobStatus.CHECKPOINTED
    assert runtime.attempts.get_attempt(active.lease.attempt.attempt_id).exit_code == 1
    assert not supervisor._terminal_assignment_receipt_path(active.lease.attempt.attempt_id).exists()


@pytest.mark.parametrize("kind", ["collection", "validation"])
def test_cleanup_failure_preserves_unqualified_received_evidence(tmp_path, kind):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    fake = FakeAdapter(FakeInspector())
    active = asyncio.run(_supervisor(runtime, tmp_path, fake).start_job(job_id))
    collection = asyncio.run(fake.collect_result(active.process_ref))
    adapter = AttendedFabricWorkerAdapter(runtime, lambda *_args: None)
    supervisor = ExecutiveSupervisor(runtime, adapter, cleanup_policy=_policy(),
        require_complete_launch_attestation=True, runs_root=tmp_path / "runs")
    async def collected(_ref):
        return collection
    adapter.collect_result = collected
    async def validated(*_args, **_kwargs):
        from control_plane.worker_execution_contract import ValidationReceipt
        return ValidationReceipt(argv=("/usr/bin/true",), exit_code=0, stdout_sha256="a"*64,
            stdout_size=0, stderr_sha256="b"*64, stderr_size=0, timed_out=False, error=None)
    adapter.run_validation_argv = validated
    with pytest.raises(SupervisorError):
        if kind == "collection":
            asyncio.run(supervisor.finish_job(active))
        else:
            job = dataclasses.replace(runtime.jobs.get_job(job_id), validation_commands=[["/usr/bin/true"]])
            asyncio.run(supervisor._run_supervisor_validations(active, job))
    path = supervisor._receipt_path(active.lease.attempt.attempt_id,
        f"fabric-unqualified-{kind}.json",
        legacy=active.launch_spec.run_dir / "output" / f"fabric-unqualified-{kind}.json")
    assert path.exists(), "independently received evidence must survive failed cleanup retrieval"
    retained = json.loads(path.read_text())
    assert retained["eligible_for_terminalization"] is False
    assert retained["attempt_id"] == active.lease.attempt.attempt_id
    assert retained["evidence"]
    assert runtime.attempts.get_attempt(active.lease.attempt.attempt_id).status is owner.AttemptStatus.CHECKPOINTED
    assert not supervisor._terminal_assignment_receipt_path(active.lease.attempt.attempt_id).exists()


def test_unknown_unbound_fabric_run_stays_quarantined_without_fence_rotation(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    claimed = runtime.broker.claim(job_id, lease_owner="inert-original-owner")
    adapter = AttendedFabricWorkerAdapter(runtime, lambda *_args: None)
    adapter.presence = lambda _attempt: owner.ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _attempt: False
    adapter.terminate = lambda _attempt: pytest.fail("unknown original run must not be signalled")
    supervisor = ExecutiveSupervisor(runtime, adapter, cleanup_policy=_policy(),
        require_complete_launch_attestation=True, runs_root=tmp_path / "runs")
    outcomes = supervisor.reconcile_restart(requeue_lost=True)
    assert [item.status for item in outcomes] == [owner.ReconcileStatus.IDENTITY_AMBIGUOUS]
    current = runtime.attempts.get_attempt(claimed.attempt.attempt_id)
    assert current.status is owner.AttemptStatus.CLAIMED
    assert current.fence_generation == claimed.attempt.fence_generation
    assert runtime.jobs.get_job(job_id).status is owner.JobStatus.RUNNING


@pytest.mark.parametrize("from_grant", [False, True])
def test_empty_fabric_validation_plan_keeps_terminal_readback_without_inventing_validation(
        composed, tmp_path, from_grant):
    active = composed.active
    active.launch_spec = SimpleNamespace(run_dir=tmp_path / "runs" / "ATT-1")
    active.effective_grant = {"validation_argv": []} if from_grant else None
    job = composed.supervisor._job(active.lease.attempt.job_id)
    if not from_grant:
        job = dataclasses.replace(job, validation_commands=[])
        composed.supervisor._job = lambda _job_id: job
    observed = []

    async def prepare(_ref, *, operation, observed_after):
        observed.append(operation)
        if operation != "terminal":
            raise AssertionError("no validation process was assigned or executed")
        assert observed_after > 0

    composed.adapter.prepare_fabric_cleanup = prepare
    composed.supervisor._retain_unqualified_fabric_evidence = lambda *_args, **_kwargs: pytest.fail(
        "empty argv cannot generate unqualified validation execution evidence")
    receipts, path, error = asyncio.run(
        composed.supervisor._run_supervisor_validations(active, job))
    payload = json.loads(path.read_text())
    assert receipts == () and error is None
    assert payload["commands"] == []
    assert "fabric_cleanup" not in payload and "uid_sweep" not in payload
    assert observed == ["terminal"]
    # Actual terminal evidence is still independently adjudicated, never
    # relabelled as validation cleanup.
    assert composed.supervisor._active_terminal_uid_sweep(active) == composed.package


def test_nonempty_fabric_validation_plan_still_requires_actual_cleanup(composed, tmp_path):
    composed.active.launch_spec = SimpleNamespace(run_dir=tmp_path / "runs" / "ATT-1")
    composed.active.effective_grant = None
    # Fixture job has a real argv requirement; its terminal package may not
    # substitute for validation evidence, even with zero returned receipts.
    with pytest.raises(SupervisorError):
        composed.supervisor._persist_validations(composed.active, ())
