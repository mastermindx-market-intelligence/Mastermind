"""Canonical Runtime completions remain readable across the App gateway."""
from __future__ import annotations

import copy
import asyncio
import dataclasses
import os
import pwd
import json
from pathlib import Path

import pytest

from control_plane.executive_orchestration_result import canonical_digest
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import (
    Runtime, StateConflict, _validated_sealed_worker_launch_material,
)
from control_plane import worker_execution_contract as recovery_owner
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_worker_broker import RemoteCodexWorkerAdapter
from control_plane.worker_execution_contract import OrchestrationLaunchSpec
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.schemas import ServerMode, bound_job_document
from integrations.mastermind_executive_app.gateway import WebCeoV2CeoIngressReadGateway
from tests.test_executive_terminal_return import (
    _completed_planner, _PlannerSealedWorkerAdapter, _SEALED_WORKER_SECRET_CANARY,
)
from tests.test_fabric_result_projection import bound_sealed_worker_planner
from tests.test_executive_os_phase1fc import _register, _v2_intent
from tests.test_executive_supervisor import FakeInspector, FakeProcessController


def _produced_job(runtime, job_id, tmp_path):
    repo = tmp_path / "reader-repo"
    repo.mkdir(exist_ok=True)
    gateway = ExecutiveMcpGateway(
        GatewayConfig(
            mode=ServerMode.READONLY,
            repo_root=repo,
            read_runtime_root=runtime.store.root,
        ),
    )
    return gateway._read("executive_job", {"job_id": job_id}, "2026-10-11T00:00:00Z")


def _accepted(document):
    return WebCeoV2CeoIngressReadGateway._valid_job_data(
        document["data"],
        arguments={"job_id": document["data"]["job"]["job_id"]},
        bounded=document["bounded"],
    )


@pytest.fixture(scope="module")
def operator_job(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("operator-job-reader")
    runtime, job, _attempt = _completed_planner(tmp_path)
    return _produced_job(runtime, job.job_id, tmp_path)


def test_canonical_operator_terminal_result_survives_job_reader(operator_job):
    assert operator_job["bounded"] == []
    assert operator_job["data"]["job"]["result"]["execution_mode"] == "OPERATOR_HARNESS"
    assert _accepted(operator_job)


def test_requeued_lost_attempt_is_history_not_an_active_claim(operator_job):
    """The canonical LOST -> QUEUED read keeps history without a fake current Attempt."""
    data = copy.deepcopy(operator_job)
    job = data["data"]["job"]
    job["status"] = "QUEUED"
    job["result"] = None
    job["current_attempt_id"] = None
    job["assigned_worker_id"] = None
    job["assigned_quota_class"] = None
    for attempt in data["data"]["attempts"]:
        attempt["status"] = "LOST"
        attempt["result"] = None
    data["data"]["latest_attempt"] = copy.deepcopy(data["data"]["attempts"][-1])
    assert _accepted(data)
    # A cleared current reference is only lawful for the narrow requeued LOST
    # state. Never accept a foreign current pointer, a live attempt, or a
    # completed job whose last worker is being hidden from the consumer.
    for variant in ("foreign_current", "running", "completed", "failed"):
        foreign = copy.deepcopy(data)
        if variant == "foreign_current":
            foreign["data"]["job"]["current_attempt_id"] = "ATT-foreign"
        elif variant == "running":
            foreign["data"]["latest_attempt"]["status"] = "RUNNING"
            foreign["data"]["attempts"][-1]["status"] = "RUNNING"
        elif variant == "completed":
            foreign["data"]["job"]["status"] = "COMPLETED"
        else:
            foreign["data"]["job"]["status"] = "FAILED"
        assert not _accepted(foreign), variant


def test_real_runtime_lost_requeue_roundtrip(tmp_path):
    """A real LOST->QUEUED transition must survive Runtime, MCP, and Web reader."""
    from tests.test_remote_attempt_transport import _lost_requeued_runtime

    runtime, job, lost = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert document["bounded"] == []
    assert document["data"]["job"]["status"] == "QUEUED"
    assert document["data"]["job"]["current_attempt_id"] is None
    assert document["data"]["job"]["assigned_worker_id"] is None
    assert document["data"]["job"]["assigned_quota_class"] is None
    assert document["data"]["latest_attempt"]["status"] == "LOST"
    assert document["data"]["latest_attempt"]["error"] == {
        "reason": "process identity absent during supervisor restart",
        "verified_process_absent": True,
    }
    assert _accepted(document)


@pytest.mark.parametrize("bad_pin", [
    "bad_digest", "bad_schema", "foreign_field", "active_status",
])
def test_real_remote_lost_pin_never_reinterprets_active_or_foreign_launch(
    tmp_path, bad_pin,
):
    from tests.test_remote_attempt_transport import _lost_requeued_runtime

    runtime, job, lost = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    pin = document["data"]["latest_attempt"]["launch_metadata"][
        "remote_launch_identity"
    ]
    if bad_pin == "bad_digest":
        pin["sha256"] = "not-hex"
    elif bad_pin == "bad_schema":
        pin["schema_version"] = "foreign-schema"
    elif bad_pin == "foreign_field":
        pin["foreign"] = True
    else:
        document["data"]["latest_attempt"]["status"] = "RUNNING"
        document["data"]["attempts"][0]["status"] = "RUNNING"
    assert not _accepted(document)


def test_real_runtime_lease_expiry_requeue_roundtrip(tmp_path):
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    runtime.attempts.reconcile_expired(now_ms=runtime.store.now_ms() + 120_000)
    runtime.jobs.requeue_job(job.job_id)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert document["data"]["job"]["status"] == "QUEUED"
    assert document["data"]["latest_attempt"]["error"]["reason"] == "lease_expired"
    assert _accepted(document)


@pytest.mark.parametrize("status", [
    "CLAIMED", "RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED",
    "CANCELLED",
])
def test_requeued_job_rejects_any_earlier_live_attempt(tmp_path, status):
    from tests.test_remote_attempt_transport import _lost_requeued_runtime

    runtime, job, lost = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    history = document["data"]["attempts"]
    first = copy.deepcopy(history[-1])
    first["attempt_id"] = "ATT-" + "b" * 32
    first["attempt_number"] = 1
    first["status"] = status
    first["error"] = None
    history[-1]["attempt_number"] = 2
    document["data"]["latest_attempt"]["attempt_number"] = 2
    history.insert(0, first)
    document["data"]["job"]["attempt_count"] = 2
    document["data"]["attempt_count"] = 2
    # The synthetic second Attempt must retain a lawful third-attempt budget.
    document["data"]["job"]["attempt_limit"] = 3
    document["data"]["attempt_limit"] = 3
    # Confirm this synthetic multi-attempt history is otherwise readable.
    first["status"] = "LOST"
    first["error"] = copy.deepcopy(history[-1]["error"])
    assert _accepted(document)
    first["status"] = status
    first["error"] = None
    assert not _accepted(document)


@pytest.mark.parametrize("mutation", [
    "latest_status", "latest_error", "foreign_assignment", "extra_error_key",
])
def test_requeued_lost_history_rejects_divergence(tmp_path, mutation):
    from tests.test_remote_attempt_transport import _lost_requeued_runtime

    runtime, job, lost = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    latest = document["data"]["latest_attempt"]
    if mutation == "latest_status":
        latest["status"] = "CLAIMED"
    elif mutation == "latest_error":
        latest["error"]["reason"] = "changed-but-valid"
    elif mutation == "foreign_assignment":
        document["data"]["job"]["assigned_worker_id"] = "worker-a"
        document["data"]["job"]["assigned_quota_class"] = "default"
    else:
        latest["error"]["private"] = "not-a-runtime-error"
        document["data"]["attempts"][-1]["error"]["private"] = "not-a-runtime-error"
    assert not _accepted(document)


def test_real_lost_history_survives_reclaim_and_completion(tmp_path):
    """Real Runtime LOST history remains readable after a subsequent Attempt."""
    from control_plane.executive_runtime import JobPayload
    from tests.test_remote_attempt_transport import (
        _lost_requeued_runtime, QUOTA, PROVIDER, _join,
    )

    runtime, job, _lost = _lost_requeued_runtime(tmp_path)
    assert _accepted(_produced_job(runtime, job.job_id, tmp_path))
    runtime.workers.register_worker(
        "worker-b", provider=PROVIDER, account_label="second",
        worker_type="fixture", capabilities=["research"],
        quota_classes={
            QUOTA: {"capabilities": ["research"],
                    "metadata": {"capacity_join": _join("host-b")}},
        },
    )
    lease = runtime.attempts.claim_job(
        job.job_id, worker_id="worker-b", quota_class=QUOTA,
        lease_owner="second",
    )
    assert lease is not None
    assert _accepted(_produced_job(runtime, job.job_id, tmp_path))
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="second-session",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert _accepted(_produced_job(runtime, job.job_id, tmp_path))
    runtime.attempts.complete_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload=JobPayload(summary="done", current_state="finished"),
    )
    terminal = _produced_job(runtime, job.job_id, tmp_path)
    assert terminal["data"]["job"]["status"] == "COMPLETED"
    assert terminal["data"]["attempts"][0]["status"] == "LOST"
    assert _accepted(terminal)


def test_real_remote_pin_readable_before_process_start_and_before_requeue(
    tmp_path,
):
    """The Runtime pin is an opaque read value, not an invocation receipt."""
    from tests.test_remote_attempt_transport import (
        _claimed_runtime, _host_binding, _pin_remote_claim,
    )

    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    _pin_remote_claim(runtime, lease, _host_binding(tmp_path))
    pinned = _produced_job(runtime, job.job_id, tmp_path)
    assert pinned["data"]["job"]["status"] == "RUNNING"
    assert pinned["data"]["latest_attempt"]["status"] == "CLAIMED"
    assert _accepted(pinned)
    runtime.attempts.record_process(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="live",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    assert _accepted(_produced_job(runtime, job.job_id, tmp_path))
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="process identity absent during supervisor restart",
        verified_process_absent=True,
    )
    before_requeue = _produced_job(runtime, job.job_id, tmp_path)
    assert before_requeue["data"]["job"]["status"] == "LOST"
    assert _accepted(before_requeue)


@pytest.mark.parametrize("mutation", [
    "exhausted", "completed_history", "latest_divergence",
])
def test_requeued_history_refuses_impossible_runtime_topology(
    tmp_path, mutation,
):
    from tests.test_remote_attempt_transport import _lost_requeued_runtime

    runtime, job, _ = _lost_requeued_runtime(tmp_path)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert _accepted(document)
    data = document["data"]
    if mutation == "exhausted":
        data["job"]["attempt_limit"] = data["job"]["attempt_count"]
        data["attempt_limit"] = data["job"]["attempt_limit"]
    elif mutation == "completed_history":
        data["attempts"][0]["status"] = "COMPLETED"
        data["latest_attempt"]["status"] = "COMPLETED"
    else:
        data["latest_attempt"]["worker_id"] = "foreign-worker"
    assert not _accepted(document)


@pytest.mark.parametrize("predecessor", ["FAILED", "RATE_LIMITED"])
def test_real_requeue_terminal_variants_remain_readable(tmp_path, predecessor):
    from control_plane.executive_runtime import JobPayload, WorkerStatus

    runtime = Runtime.at(tmp_path / "runtime")
    quota = "codex-native"
    worker = "worker-a"
    runtime.workers.register_worker(
        worker, provider="codex", account_label="fixture",
        worker_type="fixture", capabilities=["research"],
        quota_classes={quota: {
            "capabilities": ["research"],
            "metadata": {"capacity_join": {
                "host_ref": "host-a", "worker_id": worker, "quota_class": quota,
            }},
        }},
    )
    job = runtime.jobs.create_job(
        "terminal retry variant", requested_authorities=["READ"],
        constraints={"eligible_quota_classes": [quota]}, attempt_limit=3,
    )
    if predecessor == "RATE_LIMITED":
        runtime.jobs.assign_job(job.job_id, worker, quota_class=quota)
        runtime.jobs.checkpoint_job(
            job.job_id, JobPayload(summary="partial", current_state="retryable"),
        )
        runtime.workers.set_worker_status(
            worker, WorkerStatus.RATE_LIMITED, quota_class=quota,
        )
    else:
        lease = runtime.attempts.claim_job(
            job.job_id, worker_id=worker, quota_class=quota,
            lease_owner="fixture",
        )
        assert lease is not None
        runtime.attempts.record_process(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, provider_session_id="session",
        )
        runtime.attempts.mark_running(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        runtime.attempts.fail_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=JobPayload(summary="partial", current_state="retryable"),
        )
    runtime.jobs.requeue_job(job.job_id)
    doc = _produced_job(runtime, job.job_id, tmp_path)
    assert doc["data"]["job"]["status"] == "QUEUED"
    assert doc["data"]["latest_attempt"]["status"] == predecessor
    assert _accepted(doc)


def test_bounded_real_lost_checkpoint_retains_projection_parity(tmp_path):
    """A receipt's field path differs across duplicate historical projections."""
    from control_plane.executive_runtime import JobPayload
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    runtime.attempts.record_process(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="large-session",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.checkpoint_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload=JobPayload(
            summary="large checkpoint", current_state="working",
            completed_steps=[
                f"step-{n:06d} " + "x" * 200 for n in range(1400)
            ],
        ),
    )
    runtime.attempts.reconcile_expired(
        now_ms=runtime.store.now_ms() + 120_000,
    )
    runtime.jobs.requeue_job(job.job_id)
    doc = _produced_job(runtime, job.job_id, tmp_path)
    assert doc["bounded"]
    assert not (doc["data"]["attempts"][-1] ==
                doc["data"]["latest_attempt"])
    assert _accepted(doc)
    # A forged returned preview may not match its duplicated projection.
    fake = copy.deepcopy(doc)
    for name in ("attempts[0].checkpoint", "latest_attempt.checkpoint"):
        found = next((entry for entry in fake["bounded"]
                      if entry["field"] == name), None)
        if found is not None:
            node = (fake["data"]["attempts"][0]["checkpoint"]
                    if name.startswith("attempts") else
                    fake["data"]["latest_attempt"]["checkpoint"])
            assert node["bounded"] is True
            node["preview"] = "foreign" + node["preview"][7:]
            assert not _accepted(fake)
            break
    else:
        raise AssertionError("expected bounded Attempt checkpoint receipt")


def test_canonical_sealed_worker_result_and_launch_survive_job_reader(
    bound_sealed_worker_planner, tmp_path,
):
    runtime, _root, completion, _reader = bound_sealed_worker_planner
    document = _produced_job(runtime, completion.job.job_id, tmp_path)
    assert document["bounded"] == []
    assert document["data"]["job"]["result"]["execution_mode"] == "SEALED_WORKER"
    assert document["data"]["latest_attempt"]["launch_metadata"]["schema_version"] == (
        "mastermind.executive_process_launch/v1"
    )
    assert _accepted(document)
    for name, value in (
        ("launch_attestation_sha256", "a" * 64),
        ("effective_grant_digest", "a" * 64),
        ("quota_class", "foreign-quota"),
    ):
        foreign = copy.deepcopy(document)
        foreign["data"]["latest_attempt"]["launch_metadata"][name] = value
        assert not _accepted(foreign), name
    foreign = copy.deepcopy(document)
    metadata = foreign["data"]["attempts"][0]["launch_metadata"]
    metadata["launch_attestation"]["process_identity"]["pid"] += 1
    metadata["launch_attestation_sha256"] = canonical_digest(metadata["launch_attestation"])
    assert not _accepted(foreign)


@pytest.mark.parametrize("field,value", [
    ("job_id", "foreign-job"),
    ("attempt_id", "foreign-attempt"),
    ("orchestration_role", "work"),
    ("result_envelope_digest", "a" * 64),
    ("effective_grant_digest", "a" * 64),
    ("terminal_evidence_digest", "invalid"),
])
def test_terminal_result_rejects_foreign_identity_and_bad_digest(operator_job, field, value):
    document = copy.deepcopy(operator_job)
    result = document["data"]["job"]["result"]
    result[field] = value
    if field != "terminal_evidence_digest":
        result["terminal_evidence_digest"] = canonical_digest({
            key: item for key, item in result.items() if key != "terminal_evidence_digest"
        })
    assert not _accepted(document)


@pytest.mark.parametrize("field,value", [
    ("worker_id", "foreign-worker"),
    ("role_result", {}),
    ("private_field", "private-value"),
])
def test_terminal_result_reuses_closed_canonical_envelope(operator_job, field, value):
    document = copy.deepcopy(operator_job)
    result = document["data"]["attempts"][0]["result"]
    result["result_envelope"][field] = value
    result["result_envelope_digest"] = canonical_digest(result["result_envelope"])
    result["terminal_evidence_digest"] = canonical_digest({
        key: item for key, item in result.items() if key != "terminal_evidence_digest"
    })
    assert not _accepted(document)


def test_canonical_terminal_result_retains_aggregate_bounds(operator_job):
    document = copy.deepcopy(operator_job)
    data, receipts = bound_job_document(document["data"], limit=12000)
    assert receipts
    document.update(data=data, bounded=receipts)
    assert _accepted(document)
    document["bounded"].append({**receipts[0], "field": "job.private"})
    assert not _accepted(document)


@pytest.fixture
def remote_launch(tmp_path):
    """Real remote facade and Supervisor; the provider performs no OS launch."""
    runtime = Runtime.at(tmp_path / "runtime")
    _register(runtime, "worker-a")
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "planner"
    workspace.mkdir(parents=True, mode=0o700)
    admitted = submit_intent(runtime, _v2_intent(
        intent_id="CEO-REMOTE-RECOVERY-WIRE",
        execution_contract={
            "requested_authorities": ["READ"], "worktree": str(workspace),
            "attempt_limit": 2, "constraints": {"base_sha": "b" * 40},
        },
    ), workspace_root=workspace_root)
    planner = runtime.jobs.create_cycle_planner(
        admitted["job_id"],
        command_id=f"coo-cycle:{admitted['job_id']}:create-planner:0",
    )
    provider_home = tmp_path / "provider-home"
    provider_home.mkdir(mode=0o700)
    provider = _PlannerSealedWorkerAdapter(
        FakeInspector(), root_job_id=admitted["job_id"], provider_home=provider_home,
    )

    class InertBrokerClient:
        start_calls = 0

        async def request(self, operation, payload):
            assert operation == "start"
            self.start_calls += 1
            fields = dict(payload["launch_spec"])
            for name in ("workspace_path", "run_dir", "result_schema_path"):
                fields[name] = Path(fields[name])
            ref = await provider.start(OrchestrationLaunchSpec(**fields))
            return {
                "adapter_id": "codex-cli", "process_ref": dataclasses.asdict(ref),
                "launch_attestation": provider.launch_attestation(ref),
                "startup_sweep": {
                    "schema_version": "mastermind.executive_uid_sweep/v2",
                    "passed": True, "residual_pids_before": [],
                    "residual_pids_after": [], "found_residuals": False,
                    "ambient_attribution": "absent", "ambient_pids": [],
                    "ambient_identities": [], "broker_pid": 54321,
                    "worker_uid": os.geteuid(),
                },
            }

    client = InertBrokerClient()
    adapter = RemoteCodexWorkerAdapter(client)
    uid, gid = os.geteuid(), os.getegid()
    supervisor = ExecutiveSupervisor(
        runtime, adapter, runs_root=tmp_path / "runs",
        isolation_roots=(workspace_root, tmp_path / "runs"),
        worker_user=pwd.getpwuid(uid).pw_name, worker_uid=uid, worker_gid=gid,
        inspector=provider.inspector,
        process_controller=FakeProcessController(provider.inspector),
        secret_canary_verdict=_SEALED_WORKER_SECRET_CANARY,
        require_complete_launch_attestation=True, instance_id="remote-wire-fixture",
    )
    active = asyncio.run(supervisor.start_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{admitted['job_id']}:dispatch:{planner.job_id}:attempt:1",
    ))
    return runtime, active, client


def test_real_remote_supervisor_recovery_wire_reaches_running(remote_launch, tmp_path, monkeypatch):
    runtime, active, client = remote_launch
    attempt = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert client.start_calls == 1
    # start_cycle_job crosses RUNNING, then persists its first checkpoint.
    assert attempt.status.value == "CHECKPOINTED"
    events = [event.event_type for event in runtime.events.list_events(
        attempt_id=attempt.attempt_id,
    )]
    assert events.index("ATTEMPT_PROCESS_RECORDED") < events.index("ATTEMPT_RUNNING")
    assert events.index("ATTEMPT_RUNNING") < events.index("JOB_CHECKPOINTED")
    assert attempt.launch_metadata["worker_recovery_binding"]["adapter_id"] == "codex-cli"
    assert _accepted(_produced_job(runtime, attempt.job_id, tmp_path))
    def forbidden_prompt_read(*_args):
        raise AssertionError("pure wire validation must not open the private prompt")
    monkeypatch.setattr(recovery_owner, "_recovery_prompt_bytes", forbidden_prompt_read)
    row = attempt.to_dict()
    for name in (
        "launch_metadata", "effective_grant", "placement_snapshot",
        "execution_principal_snapshot",
    ):
        row[f"{name}_json"] = json.dumps(
            row[name], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
    assert _validated_sealed_worker_launch_material(row)
    wire = attempt.launch_metadata["worker_recovery_binding"]
    binding = recovery_owner.WorkerRecoveryBinding.from_dict(wire).validate_wire()
    assert binding.to_dict() == wire
    for section, field, value in (
        ("fields", "job_id", "foreign-job"),
        ("fields", "worker_id", "foreign-worker"),
        ("fields", "authorities", ["READ", "WRITE"]),
        ("fields", "allowed_artifact_paths", ["private/**"]),
        ("fields", "effective_grant_digest", "a" * 64),
        ("fields", "run_dir", "/foreign/run"),
        ("fields", "result_schema_path", "/foreign/schema.json"),
        ("fields", "result_schema_path", str(active.launch_spec.run_dir / "input" / ".." / "escape")),
        ("fields", "private_field", "private-value"),
        ("process_ref", "pid", attempt.pid + 1),
        ("process_ref", "launch_nonce", "foreign-nonce"),
        ("process_ref", "result_path", "/foreign/result.json"),
        ("binding", "launch_spec_sha256", "a" * 64),
        ("binding", "private_field", "private-value"),
    ):
        changed = copy.deepcopy(attempt.launch_metadata)
        recovery = changed["worker_recovery_binding"]
        if section == "fields":
            recovery["launch_spec"]["fields"][field] = value
            recovery["launch_spec_sha256"] = canonical_digest({
                **recovery["launch_spec"]["fields"],
                "prompt_sha256": recovery["launch_spec"]["prompt_sha256"],
            })
        elif section == "process_ref":
            recovery["process_ref"][field] = value
        else:
            recovery[field] = value
        foreign = {**row, "launch_metadata_json": json.dumps(
            changed, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )}
        with pytest.raises(StateConflict, match="recovery"):
            _validated_sealed_worker_launch_material(foreign)
        document = _produced_job(runtime, attempt.job_id, tmp_path)
        document["data"]["latest_attempt"]["launch_metadata"] = changed
        assert not _accepted(document), (section, field)


def test_real_operator_harness_expiry_fence_keeps_active_job_readable(tmp_path):
    """Use a temporary Runtime's actual OHF expiry producer, not a fabricated error."""
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    # Use the Runtime writer to seal a real canonical operator profile. No
    # synthetic JSON/digest pair is accepted as a production OHF projection.
    from tests.test_ohf_p1b_runtime import _profile

    runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        requested=_profile(lease),
    )
    runtime.attempts.reconcile_expired(
        now_ms=runtime.store.now_ms() + 120_000,
    )
    document = _produced_job(runtime, job.job_id, tmp_path)
    current = document["data"]
    assert current["job"]["status"] == "RUNNING"
    assert current["job"]["current_attempt_id"] == lease.attempt.attempt_id
    assert current["latest_attempt"]["status"] == "CLAIMED"
    assert current["latest_attempt"]["execution_mode"] == "OPERATOR_HARNESS"
    assert current["latest_attempt"]["error"]["reason"] == "ohf_lease_expired_fenced"
    assert _accepted(document)

    for variant in (
        "wrong_mode", "foreign_pointer", "wrong_job_status",
        "other_expiry_reason", "invalid_timestamp",
    ):
        forged = copy.deepcopy(document)
        candidate = forged["data"]
        history = candidate["attempts"][-1]
        latest = candidate["latest_attempt"]
        if variant == "wrong_mode":
            history["execution_mode"] = latest["execution_mode"] = "SEALED_WORKER"
        elif variant == "foreign_pointer":
            candidate["job"]["current_attempt_id"] = "ATT-foreign"
        elif variant == "wrong_job_status":
            candidate["job"]["status"] = "QUEUED"
        elif variant == "other_expiry_reason":
            history["error"]["reason"] = latest["error"]["reason"] = "lease_expired"
        else:
            history["error"]["expired_at_ms"] = latest["error"]["expired_at_ms"] = -1
        assert not _accepted(forged), variant


@pytest.mark.parametrize("missing_result_scope", ["job", "job_and_attempt"])
def test_completed_job_or_attempt_cannot_omit_persisted_result(
    operator_job, missing_result_scope,
):
    document = copy.deepcopy(operator_job)
    assert _accepted(document)
    document["data"]["job"]["result"] = None
    if missing_result_scope == "job_and_attempt":
        document["data"]["attempts"][-1]["result"] = None
        document["data"]["latest_attempt"]["result"] = None
    assert not _accepted(document)


@pytest.mark.parametrize("source", ["real_lost_requeue", "real_completed"])
def test_terminal_attempt_without_finished_at_is_not_certified(
    tmp_path, operator_job, source,
):
    """Mirror Runtime's terminal status <=> finished_at_ms storage CHECK."""
    if source == "real_lost_requeue":
        from tests.test_remote_attempt_transport import _lost_requeued_runtime

        runtime, job, _lost = _lost_requeued_runtime(tmp_path)
        document = _produced_job(runtime, job.job_id, tmp_path)
        assert document["data"]["latest_attempt"]["status"] == "LOST"
    else:
        document = copy.deepcopy(operator_job)
        assert document["data"]["latest_attempt"]["status"] == "COMPLETED"

    assert _accepted(document)
    assert document["data"]["latest_attempt"]["finished_at"]

    # Mirror the same forged omission in both of the independently projected
    # rows so aggregate parity cannot mask the Runtime status invariant.
    for row in (
        document["data"]["attempts"][-1],
        document["data"]["latest_attempt"],
    ):
        row["finished_at"] = ""
    assert not _accepted(document)


def test_active_attempt_with_forged_finished_at_is_not_certified(tmp_path):
    """Runtime refuses a completed timestamp while an Attempt is nonterminal."""
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, _lease = _claimed_runtime(tmp_path, attempt_limit=2)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert document["data"]["latest_attempt"]["status"] == "CLAIMED"
    assert document["data"]["latest_attempt"]["finished_at"] == ""
    assert _accepted(document)

    for row in (
        document["data"]["attempts"][-1],
        document["data"]["latest_attempt"],
    ):
        row["finished_at"] = row["started_at"] or "2026-10-22T00:00:00+00:00"
    assert not _accepted(document)


@pytest.mark.parametrize("field", [
    "lease_expires_at", "heartbeat_at", "started_at", "finished_at",
])
def test_attempt_row_malformed_timestamp_is_not_certified(tmp_path, field):
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, lease = _claimed_runtime(tmp_path, attempt_limit=2)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert _accepted(document)
    document["data"]["attempts"][-1][field] = "not-a-timestamp"
    document["data"]["latest_attempt"][field] = "not-a-timestamp"
    assert not _accepted(document)


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_job_row_malformed_timestamp_is_not_certified(tmp_path, field):
    from tests.test_remote_attempt_transport import _claimed_runtime

    runtime, job, _lease = _claimed_runtime(tmp_path, attempt_limit=2)
    document = _produced_job(runtime, job.job_id, tmp_path)
    assert _accepted(document)
    document["data"]["job"][field] = "not-a-timestamp"
    assert not _accepted(document)


def test_job_and_attempt_timestamp_order_must_be_consistent(operator_job):
    document = copy.deepcopy(operator_job)
    assert _accepted(document)
    job_order = copy.deepcopy(document)
    job_order["data"]["job"]["created_at"] = "2026-10-11T00:00:02+00:00"
    job_order["data"]["job"]["updated_at"] = "2026-10-11T00:00:01+00:00"
    assert not _accepted(job_order)

    attempt_order = copy.deepcopy(document)
    for attempt in (
        attempt_order["data"]["attempts"][-1],
        attempt_order["data"]["latest_attempt"],
    ):
        attempt["started_at"] = "2026-10-11T00:00:02+00:00"
        attempt["finished_at"] = "2026-10-11T00:00:01+00:00"
    assert not _accepted(attempt_order)


@pytest.mark.parametrize("job_id", ["JOB-002", "JOB-025"])
def test_installed_job_readback_regression_when_captured(job_id):
    """Post-install LIVE gate, never a simulated success on hosted CI.

    Supply a directory containing exact decoded readonly Executive MCP envelopes
    JOB-002.json and JOB-025.json from the installed executive_job tool. No raw
    database access, credentials or provider operation is involved. When no
    captured live envelopes are available, report SKIP, not live acceptance.
    """
    root = os.environ.get("MMX_EXECUTIVE_LIVE_READBACK_DIR")
    if not root:
        pytest.skip("live Executive readback captures not supplied")
    document = json.loads((Path(root) / f"{job_id}.json").read_text())
    assert document.get("ok") is True, (job_id, document.get("error"))
    assert document.get("tool") == "executive_job"
    assert document.get("mode") == "readonly"
    assert document["data"]["job"]["job_id"] == job_id
    assert _accepted(document)


@pytest.mark.parametrize("job_id", ["JOB-002", "JOB-025"])
def test_installed_job_readback_capture_gate_rejects_backend_unavailable(
    tmp_path, monkeypatch, job_id,
):
    """Previously observed installed failure must be a RED post-release gate."""
    document = {
        "schema": "mastermind.executive_mcp_result.v1",
        "tool": "executive_job",
        "mode": "readonly",
        "ok": False,
        "data": None,
        "error": {
            "code": "backend_unavailable",
            "message": "Executive reader returned an invalid response.",
        },
    }
    (tmp_path / f"{job_id}.json").write_text(json.dumps(document))
    monkeypatch.setenv("MMX_EXECUTIVE_LIVE_READBACK_DIR", str(tmp_path))
    with pytest.raises(AssertionError, match="backend_unavailable"):
        test_installed_job_readback_regression_when_captured(job_id)
