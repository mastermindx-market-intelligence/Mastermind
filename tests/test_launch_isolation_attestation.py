"""Real launch receipts bind isolation without changing historical evidence."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.worker_execution_contract import LaunchAttestation, WorkerRunStatus
from tests.test_worker_execution_contract import _binary
from tests.test_executive_supervisor import (
    FakeAdapter, FakeInspector, _runtime_and_job, _supervisor,
)


def _attestation():
    return LaunchAttestation(
        "mastermind.executive_launch_attestation/v1", "2026-10-03T00:00:00Z",
        "/fixture/provider", _binary(), ("provider", "exec"), ("HOME",),
        "a" * 64, "b" * 64, "c" * 40, "c" * 40,
        {"path": "/workspace"}, {"uid": 451}, {"path": "/provider-home"},
        {"passed": True}, "nonce", {"pid": 12, "pgid": 12},
    )


@pytest.mark.parametrize("digest", ["1" * 64, "e" * 64])
@pytest.mark.parametrize("canary", [False, True])
def test_shared_receipt_preserves_exact_isolation_and_optional_canary(digest, canary):
    original = _attestation()
    before = original.to_dict()
    changes = {"isolation_manifest_sha256": digest}
    if canary:
        changes.update(subscription_canary_observation_digest="f" * 64,
                       subscription_canary_binding_id="canary-id",
                       subscription_canary_model="fixture-model")
    updated = dataclasses.replace(original, **changes).to_dict()
    assert updated["isolation_manifest_sha256"] == digest
    assert updated["process_identity"] == before["process_identity"]
    assert ("subscription_canary_binding_id" in updated) == canary
    assert original.to_dict() == before
    assert "isolation_manifest_sha256" not in before


def _isolated_spec(spec, tmp_path):
    """Use the production manifest owner over real assignment directories."""
    workspace_root = tmp_path / "assignments"
    run_root = tmp_path / "executions"
    workspace_root.mkdir(mode=0o700)
    run_root.mkdir(mode=0o700)
    workspace = workspace_root / "current"
    run = run_root / "current"
    schema_relative = spec.result_schema_path.relative_to(spec.run_dir)
    spec.workspace_path.rename(workspace)
    spec.run_dir.rename(run)
    denied, manifest, digest = ExecutiveSupervisor._isolation_manifest(
        (workspace_root, run_root), workspace=workspace, run_dir=run,
    )
    return dataclasses.replace(
        spec, workspace_path=workspace, run_dir=run,
        result_schema_path=run / schema_relative,
        isolation_roots=(workspace_root, run_root), isolation_denied_paths=denied,
        isolation_manifest=manifest, isolation_manifest_sha256=digest,
    )


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_real_subprocess_adapter_receipt_carries_validated_isolation(tmp_path, provider):
    if provider == "codex":
        from tests.test_executive_codex_worker import _fixture
        adapter, spec, _, _ = _fixture(tmp_path)
    else:
        from tests.test_executive_claude_worker import (
            _fixture_claude_binary, _adapter, _workspace_and_spec,
        )
        binary = _fixture_claude_binary(tmp_path)
        (tmp_path / "mode").write_text("success")
        adapter = _adapter(tmp_path, binary)
        spec = _workspace_and_spec(tmp_path)
    spec = _isolated_spec(spec, tmp_path)

    async def execute():
        ref = await adapter.start(spec)
        try:
            document = adapter.launch_attestation(ref).to_dict()
            receipt = await adapter.collect_result(ref)
            return document, receipt
        finally:
            await adapter.cancel(ref, "test cleanup")

    document, receipt = asyncio.run(execute())
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    assert document["isolation_manifest_sha256"] == spec.isolation_manifest_sha256
    assert "isolation_manifest" not in document
    assert "lease_token" not in json.dumps(document)


@pytest.mark.parametrize("bad_digest", [None, "0" * 64, "G" * 64, "short"])
@pytest.mark.parametrize("require_complete", [False, True])
def test_supervisor_rejects_unbound_receipt_before_process_record(tmp_path, bad_digest, require_complete):
    class BadReceipt(FakeAdapter):
        def launch_attestation(self, ref):
            value = super().launch_attestation(ref)
            if bad_digest is None:
                value.pop("isolation_manifest_sha256")
            else:
                value["isolation_manifest_sha256"] = bad_digest
            return value

    runtime, job_id, _ = _runtime_and_job(tmp_path)
    adapter = BadReceipt(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    supervisor.require_complete_launch_attestation = require_complete
    with pytest.raises(SupervisorError, match="isolation manifest"):
        asyncio.run(supervisor.start_job(job_id))
    attempts = runtime.attempts.list_attempts(job_id)
    assert len(attempts) == 1
    assert attempts[0].pid is None
    assert not attempts[0].launch_metadata.get("launch_attestation")
    events = runtime.events.list_events(attempt_id=attempts[0].attempt_id)
    assert not {"ATTEMPT_PROCESS_RECORDED", "ATTEMPT_RUNNING"} & {e.event_type for e in events}


def _replace_persisted_digest(runtime, attempt_id, digest):
    import hashlib
    import sqlite3
    with sqlite3.connect(runtime.store.path) as connection:
        raw = connection.execute(
            "SELECT launch_metadata_json FROM attempts WHERE attempt_id=?", (attempt_id,),
        ).fetchone()[0]
        metadata = json.loads(raw)
        if digest is None:
            metadata["launch_attestation"].pop("isolation_manifest_sha256")
        else:
            metadata["launch_attestation"]["isolation_manifest_sha256"] = digest
        encoded = json.dumps(metadata["launch_attestation"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        metadata["launch_attestation_sha256"] = hashlib.sha256(encoded.encode()).hexdigest()
        connection.execute(
            "UPDATE attempts SET launch_metadata_json=? WHERE attempt_id=?",
            (json.dumps(metadata, sort_keys=True, separators=(",", ":")), attempt_id),
        )


@pytest.mark.parametrize("bad_digest", [None, "short", "G" * 64])
def test_runtime_refuses_incomplete_isolation_before_running(tmp_path, bad_digest):
    from control_plane.executive_runtime import StateConflict, AttemptStatus
    from tests.test_executive_supervisor import (
        RestartCapableFakeAdapter, _persist_recoverable_launch_boundary,
    )
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    adapter = RestartCapableFakeAdapter(FakeInspector())
    supervisor = _supervisor(runtime, tmp_path, adapter)
    lease = asyncio.run(_persist_recoverable_launch_boundary(
        supervisor, adapter, job_id, mark_running=False,
    ))
    _replace_persisted_digest(runtime, lease.attempt.attempt_id, bad_digest)
    with pytest.raises(StateConflict, match="complete launch attestation|isolation_manifest_sha256"):
        runtime.attempts.mark_running(
            lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            required_launch_attestation_schema="mastermind.executive_launch_attestation/v1",
        )
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status is AttemptStatus.CLAIMED


@pytest.mark.parametrize("bad_digest", [None, "0" * 64])
def test_restart_quarantines_isolation_drift_without_reattach_or_relaunch(tmp_path, bad_digest):
    from control_plane.executive_runtime import Runtime
    from control_plane.executive_supervisor import ReconcileStatus
    from tests.test_executive_supervisor import (
        RestartCapableFakeAdapter, _persist_recoverable_launch_boundary,
    )
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    first = _supervisor(runtime, tmp_path, first_adapter)
    lease = asyncio.run(_persist_recoverable_launch_boundary(
        first, first_adapter, job_id, mark_running=True,
    ))
    _replace_persisted_digest(runtime, lease.attempt.attempt_id, bad_digest)
    reopened = Runtime.at(tmp_path, lease_seconds=30)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=False)
    assert len(outcomes) == 1
    assert outcomes[0].status is ReconcileStatus.LIVE_QUARANTINED
    assert "does not bind the admitted isolation manifest" in outcomes[0].error
    assert second_adapter.reattach_calls == []
    assert second_adapter.start_calls == 0
    assert restarted.take_recovered_runs() == ()
