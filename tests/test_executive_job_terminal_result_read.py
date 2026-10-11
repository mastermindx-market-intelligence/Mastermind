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
