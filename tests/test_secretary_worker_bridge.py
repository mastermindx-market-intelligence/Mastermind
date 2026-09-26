from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from control_plane.worker_execution_contract import (
    ArtifactReceipt,
    BinaryAttestation,
    CollectionReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)
from integrations.mastermind_secretary_mcp.decision_provider_contract import (
    build_secretary_provider_request,
)

try:
    from integrations import secretary_worker_bridge as worker_bridge
except ImportError:
    worker_bridge = None


def snapshot(**overrides):
    value = {
        "schema": "mastermind.secretary_decision_snapshot/v1",
        "operation_key": "mastermind-os-frontier-company-convergence-20260925-sol-001",
        "responsibility_ref": "WS:CHAIRMAN-CONTROL-ROOM",
        "trigger": "TURN_COMPLETED",
        "mission_state": "MORE_WORK",
        "turn_state": "TERMINAL",
        "effect_state": "CLEAR",
        "context_state": "HEALTHY",
        "checkpoint_state": "NONE",
        "binding_state": "EXACT_CURRENT",
        "capability_state": "SERVICEABLE",
        "human_gate": "NONE",
        "current_mode": "EXTRA_HIGH",
        "mode_recommendation": "NONE",
        "outstanding_children": 0,
        "ready_returns": 0,
        "fanout_candidates": [],
        "source_refs": ["runtime:binding-current", "github:pr-989"],
        "observed_at_ms": 10_000,
        "expires_at_ms": 50_000,
    }
    value.update(overrides)
    return value


def recommendation(
    action="CONTINUE_CURRENT_SESSION",
    reason_code="MORE_WORK",
    *,
    requested_mode=None,
    fanout_candidate_ids=None,
    rationale="Continue the same exact current CEO responsibility.",
):
    return {
        "schema": "mastermind.secretary_decision_recommendation/v1",
        "action": action,
        "reason_code": reason_code,
        "requested_mode": requested_mode,
        "fanout_candidate_ids": [] if fanout_candidate_ids is None else fanout_candidate_ids,
        "rationale": rationale,
    }


def provider_request(snap=None, now_ms=20_000):
    return build_secretary_provider_request(
        snapshot() if snap is None else snap,
        now_ms=now_ms,
    )


def launch_spec(request=None, **overrides):
    request = provider_request() if request is None else request
    values = {
        "run_id": "secretary-run-001",
        "job_id": "secretary-job-001",
        "worker_id": "secretary-worker-001",
        "workspace_path": Path("/tmp/mastermind-secretary-workspace"),
        "run_dir": Path("/tmp/mastermind-secretary-run"),
        "prompt": request.prompt,
        "result_schema_path": Path("/tmp/mastermind-secretary-run/output-schema.json"),
        "authorities": ("READ",),
        "authority": None,
        "allowed_artifact_paths": (),
    }
    values.update(overrides)
    return WorkerLaunchSpec(**values)


def binary_attestation():
    return BinaryAttestation(
        path="/usr/bin/true",
        real_path="/usr/bin/true",
        version="1",
        sha256="a" * 64,
        team_identifier=None,
        size=1,
        device=1,
        inode=1,
        mode=0o755,
        uid=501,
        gid=20,
        mtime_ns=1,
    )


def process_ref(spec):
    return WorkerProcessRef(
        run_id=spec.run_id,
        pid=1234,
        pgid=1234,
        process_start_identity="proc-start-001",
        boot_session_id="boot-session-001",
        launch_nonce="launch-nonce-123456",
        provider_session_id=None,
        stdout_path="/tmp/stdout",
        stderr_path="/tmp/stderr",
        result_path="/tmp/result",
        started_at="2026-09-26T07:00:00Z",
        binary=binary_attestation(),
        base_sha="b" * 40,
    )


def collection(spec, *, output=None, status=WorkerRunStatus.SUCCEEDED, **overrides):
    ref = process_ref(spec)
    result = WorkerResult(
        job_id=overrides.pop("job_id", spec.job_id),
        run_id=overrides.pop("run_id", spec.run_id),
        worker_id=overrides.pop("worker_id", spec.worker_id),
        status=status,
        structured_output=recommendation() if output is None else output,
        artifact_manifest=overrides.pop("artifact_manifest", ()),
        git_manifest=overrides.pop(
            "git_manifest",
            {
                "base_sha": "b" * 40,
                "head_sha": "b" * 40,
                "status_sha256": "c" * 64,
                "changed_paths": [],
            },
        ),
        usage={},
        provider_session_id=None,
        exit_code=overrides.pop("exit_code", 0 if status is WorkerRunStatus.SUCCEEDED else 1),
        started_at="2026-09-26T07:00:00Z",
        finished_at="2026-09-26T07:00:01Z",
        error=overrides.pop("error", None if status is WorkerRunStatus.SUCCEEDED else "failed"),
    )
    assert not overrides
    return CollectionReceipt(
        process_ref=ref,
        result=result,
        stdout_sha256="d" * 64,
        stderr_sha256="e" * 64,
        result_sha256="f" * 64 if status is WorkerRunStatus.SUCCEEDED else None,
    )


def test_secretary_worker_bridge_apis_are_available() -> None:
    assert callable(getattr(worker_bridge, "bind_secretary_worker_launch", None))
    assert callable(getattr(worker_bridge, "validate_secretary_worker_collection", None))


if worker_bridge is not None:
    def bound_pair(snap=None):
        snap = snapshot() if snap is None else snap
        req = provider_request(snap)
        spec = launch_spec(req)
        binding = worker_bridge.bind_secretary_worker_launch(
            req,
            spec,
            req.output_schema_json,
        )
        return snap, req, spec, binding


    def test_exact_read_only_launch_binding_is_transient_and_non_authoritative() -> None:
        _snap, req, spec, binding = bound_pair()
        assert binding.status == "READY"
        assert binding.refusal_code is None
        assert binding.snapshot_digest == req.snapshot_digest
        assert binding.prompt_sha256 == req.prompt_sha256
        assert binding.output_schema_sha256 == hashlib.sha256(
            req.output_schema_json.encode("utf-8")
        ).hexdigest()
        assert len(binding.worker_launch_spec_sha256) == 64
        assert binding.run_id == spec.run_id
        assert binding.job_id == spec.job_id
        assert binding.worker_id == spec.worker_id
        assert binding.worker_started is False
        assert binding.execution_authorized is False
        assert binding.schema_version == "mastermind.secretary_worker_launch_binding/v1"


    def test_launch_binding_refuses_prompt_or_schema_tampering() -> None:
        _snap, req, spec, _binding = bound_pair()
        bad_prompt = dataclasses.replace(spec, prompt=req.prompt + "\nextra")
        refused_prompt = worker_bridge.bind_secretary_worker_launch(
            req, bad_prompt, req.output_schema_json
        )
        assert refused_prompt.status == "REFUSED"
        assert refused_prompt.refusal_code == "LAUNCH_PROMPT_MISMATCH"

        refused_schema = worker_bridge.bind_secretary_worker_launch(
            req, spec, "{}"
        )
        assert refused_schema.status == "REFUSED"
        assert refused_schema.refusal_code == "LAUNCH_SCHEMA_MISMATCH"


    def test_launch_binding_requires_exact_read_only_no_artifact_authority() -> None:
        _snap, req, spec, _binding = bound_pair()
        write_spec = dataclasses.replace(spec, authorities=("READ", "WRITE_BRANCH"))
        refused_write = worker_bridge.bind_secretary_worker_launch(
            req, write_spec, req.output_schema_json
        )
        assert refused_write.refusal_code == "LAUNCH_AUTHORITY_INVALID"

        artifact_spec = dataclasses.replace(spec, allowed_artifact_paths=("result.txt",))
        refused_artifact = worker_bridge.bind_secretary_worker_launch(
            req, artifact_spec, req.output_schema_json
        )
        assert refused_artifact.refusal_code == "LAUNCH_ARTIFACT_PATHS_FORBIDDEN"


    def test_successful_collection_correlates_worker_identity_but_not_provider_identity() -> None:
        snap, req, spec, binding = bound_pair()
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap,
            req,
            binding,
            collection(spec),
            now_ms=20_000,
        )
        assert receipt.status == "ACCEPTED"
        assert receipt.refusal_code is None
        assert receipt.worker_collection_correlated is True
        assert receipt.provider_result_attested is False
        assert receipt.execution_authorized is False
        assert receipt.requires_owner_admission is True
        assert receipt.action == "CONTINUE_CURRENT_SESSION"
        assert receipt.reason_code == "MORE_WORK"
        assert receipt.result_sha256 == "f" * 64
        assert receipt.schema_version == "mastermind.secretary_worker_collection_validation/v1"


    def test_collection_refuses_run_job_or_worker_identity_mismatch() -> None:
        snap, req, spec, binding = bound_pair()
        cases = (
            collection(spec, run_id="other-run"),
            collection(spec, job_id="other-job"),
            collection(spec, worker_id="other-worker"),
        )
        for item in cases:
            receipt = worker_bridge.validate_secretary_worker_collection(
                snap, req, binding, item, now_ms=20_000
            )
            assert receipt.status == "REFUSED"
            assert receipt.refusal_code == "COLLECTION_IDENTITY_MISMATCH"


    def test_collection_refuses_failed_result_or_nonzero_success_claim() -> None:
        snap, req, spec, binding = bound_pair()
        failed = worker_bridge.validate_secretary_worker_collection(
            snap,
            req,
            binding,
            collection(spec, status=WorkerRunStatus.FAILED),
            now_ms=20_000,
        )
        assert failed.refusal_code == "COLLECTION_NOT_SUCCEEDED"

        bad_exit = worker_bridge.validate_secretary_worker_collection(
            snap,
            req,
            binding,
            collection(spec, exit_code=7),
            now_ms=20_000,
        )
        assert bad_exit.refusal_code == "COLLECTION_NOT_SUCCEEDED"


    def test_collection_refuses_invalid_hash_evidence() -> None:
        snap, req, spec, binding = bound_pair()
        item = dataclasses.replace(collection(spec), result_sha256="bad")
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap, req, binding, item, now_ms=20_000
        )
        assert receipt.refusal_code == "COLLECTION_HASH_INVALID"


    def test_collection_refuses_artifacts_or_workspace_changes() -> None:
        snap, req, spec, binding = bound_pair()
        artifact = ArtifactReceipt(path="result.txt", sha256="1" * 64, size=1)
        with_artifact = collection(spec, artifact_manifest=(artifact,))
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap, req, binding, with_artifact, now_ms=20_000
        )
        assert receipt.refusal_code == "COLLECTION_WRITE_EVIDENCE"

        changed = collection(
            spec,
            git_manifest={
                "base_sha": "b" * 40,
                "head_sha": "b" * 40,
                "status_sha256": "c" * 64,
                "changed_paths": ["unexpected.txt"],
            },
        )
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap, req, binding, changed, now_ms=20_000
        )
        assert receipt.refusal_code == "COLLECTION_WRITE_EVIDENCE"


    def test_collection_refuses_current_snapshot_or_launch_binding_drift() -> None:
        snap, req, spec, binding = bound_pair()
        changed_snapshot = snapshot(
            trigger="MATERIAL_RETURN",
            observed_at_ms=11_000,
            expires_at_ms=51_000,
        )
        receipt = worker_bridge.validate_secretary_worker_collection(
            changed_snapshot, req, binding, collection(spec), now_ms=20_000
        )
        assert receipt.refusal_code == "PROVIDER_REQUEST_MISMATCH"

        changed_binding = dataclasses.replace(binding, prompt_sha256="0" * 64)
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap, req, changed_binding, collection(spec), now_ms=20_000
        )
        assert receipt.refusal_code == "LAUNCH_BINDING_MISMATCH"


    def test_collection_projects_task6_semantic_refusal_without_rationale_leakage() -> None:
        snap = snapshot(effect_state="EFFECT_UNKNOWN", trigger="EFFECT_RECONCILIATION")
        req = provider_request(snap)
        spec = launch_spec(req)
        binding = worker_bridge.bind_secretary_worker_launch(req, spec, req.output_schema_json)
        unsafe = recommendation(
            rationale="worker-bridge-private-rationale-needle"
        )
        receipt = worker_bridge.validate_secretary_worker_collection(
            snap,
            req,
            binding,
            collection(spec, output=unsafe),
            now_ms=20_000,
        )
        assert receipt.status == "REFUSED"
        assert receipt.refusal_code == "SECRETARY_RETURN_REFUSED"
        assert receipt.return_refusal_code == "RECOMMENDATION_REFUSED"
        assert receipt.semantic_refusal_code == "EFFECT_HOLD_REQUIRED"
        assert receipt.worker_collection_correlated is True
        assert receipt.execution_authorized is False
        assert "worker-bridge-private-rationale-needle" not in json.dumps(
            receipt.to_dict(), sort_keys=True
        )


    def test_worker_bridge_source_has_no_lifecycle_provider_or_io_execution_surface() -> None:
        source = Path(worker_bridge.__file__).read_text(encoding="utf-8")
        forbidden = (
            "create_job",
            "create_attempt",
            "claim_job",
            "start(",
            "subprocess",
            "requests.",
            "httpx",
            "socket",
            "open(",
            "write_text",
            "write_bytes",
            "ModelRouter",
            "Capacity",
            "chrome.",
            "document.",
        )
        for token in forbidden:
            assert token not in source
