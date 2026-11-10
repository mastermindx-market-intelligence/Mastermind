"""Explicit paid-only Supervisor composition; no provider or lifecycle owner.

The canonical adapter authenticates its original remote receipts. Runtime owns
claim, pin, principal sealing and terminal acceptance. These helpers persist
only the actual Control inputs and returned evidence; legacy CLI helpers stay
on their existing path.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from control_plane.paid_model_execution_contract import (
    ADAPTER_ID, ATTESTATION_SCHEMA, PROFILE_ID, canonical, digest,
)


def is_paid_adapter(adapter: Any) -> bool:
    # A flag, schema string or class-name lookalike cannot select this route.
    try:
        from control_plane.executive_paid_fabric_adapter import CanonicalPaidFabricWorkerAdapter
    except ModuleNotFoundError as exc:
        if exc.name == "control_plane.executive_paid_fabric_adapter":
            return False
        raise
    return type(adapter) is CanonicalPaidFabricWorkerAdapter


def require_paid_adapter(supervisor: Any) -> None:
    from control_plane.executive_supervisor import SupervisorError
    if not is_paid_adapter(supervisor.adapter):
        raise SupervisorError("paid composition requires its exact canonical adapter")


def launch_metadata(supervisor, *, job, lease, spec, process_ref,
                    effective_grant, recovery_prompt_path):
    from control_plane.executive_supervisor import SupervisorError, _write_private_json
    from control_plane.executive_runtime import REMOTE_LAUNCH_IDENTITY_KEY
    from control_plane.paid_model_recovery import PaidModelRecoveryBinding
    from control_plane.worker_execution_contract import PaidModelProcessRef

    require_paid_adapter(supervisor)
    if (type(process_ref) is not PaidModelProcessRef or effective_grant is None
            or job.constraints.get("execution_profile_id") != PROFILE_ID
            or job.orchestration_role not in {"work", "repair"}
            or set(effective_grant["authorities"]) not in ({"READ"}, {"READ", "RESEARCH"})
            or effective_grant["write_paths"] != [] or effective_grant["validation_argv"] != []
            or recovery_prompt_path is None):
        raise SupervisorError("paid launch differs from its exact source contract")
    quota = supervisor.runtime.workers.get_quota_class(lease.attempt.worker_id,
                                                     lease.attempt.quota_class)
    if quota is None:
        raise SupervisorError("paid launch lost its claimed quota")
    attestation = supervisor.adapter.launch_attestation(process_ref)
    if hasattr(attestation, "to_dict"):
        attestation = attestation.to_dict()
    identity = supervisor.adapter.paid_launch_identity(process_ref)
    if (type(attestation) is not dict or attestation.get("schema_version") != ATTESTATION_SCHEMA
            or type(identity) is not dict or set(identity) != {"physical_binding_sha256", "request"}
            or attestation.get("binding", {}).get("effective_grant_digest")
            != lease.attempt.effective_grant_digest
            or attestation.get("evidence", {}).get("control_input_isolation_manifest_sha256")
            != spec.isolation_manifest_sha256
            or attestation.get("evidence", {}).get("prompt_sha256")
            != hashlib.sha256(spec.prompt.encode("utf-8")).hexdigest()):
        raise SupervisorError("paid launch did not attest its actual sealed inputs")
    identity_sha = digest(identity)
    current = supervisor.runtime.attempts.get_attempt(lease.attempt.attempt_id)
    pin = current.launch_metadata.get(REMOTE_LAUNCH_IDENTITY_KEY) if current else None
    if not isinstance(pin, dict) or pin.get("sha256") != identity_sha:
        raise SupervisorError("paid launch differs from its original Runtime pin")
    context = supervisor.adapter.control_recovery_context(spec)
    source = identity["request"]["paid_source_config"]
    binding = PaidModelRecoveryBinding.bind(
        adapter_id=ADAPTER_ID, spec=spec, process_ref=process_ref,
        prompt_path=recovery_prompt_path, control_recovery=context,
        launch_attestation_sha256=digest(attestation),
        launch_identity_sha256=identity_sha, capture_root=source["capture_root"],
    )
    receipt_path = supervisor._receipt_path(
        lease.attempt.attempt_id, "launch-attestation.json",
        legacy=supervisor._run_dir(lease.attempt.attempt_id) / "input" / "launch-attestation.json",
    )
    _write_private_json(receipt_path, attestation)
    qm = quota.metadata
    result = {
        "schema_version": "mastermind.executive_paid_process_launch/v1",
        "launch_attestation": attestation,
        "launch_attestation_sha256": digest(attestation),
        "launch_attestation_path": str(receipt_path),
        "authority_policy_hash": lease.attempt.authority_policy_hash,
        "authorities": list(effective_grant["authorities"]),
        "effective_grant_digest": lease.attempt.effective_grant_digest,
        "write_paths": list(effective_grant["write_paths"]),
        "validation_argv": list(effective_grant["validation_argv"]),
        "quota_class": lease.attempt.quota_class,
        "routing": {
            "policy_version": job.constraints.get("routing_policy_version"),
            "preferred_model_aliases": job.constraints.get("preferred_model_aliases", []),
            "selected_model_alias": qm.get("model_alias"),
            "provider_alias": qm.get("provider_alias"),
            "adapter_id": qm.get("adapter_id"),
            **{k: job.constraints.get(k) for k in (
                "execution_profile_id", "execution_profile_digest",
                "capability_policy_version", "capability_policy_digest",
            )},
        },
        "paid_recovery_binding": binding.to_dict(),
        "paid_launch_identity": identity,
        "paid_launch_identity_sha256": identity_sha,
        REMOTE_LAUNCH_IDENTITY_KEY: pin,
    }
    # Canonical serialization is checked before writing any launch metadata.
    canonical(result)
    return result


def validated_recovery_binding(supervisor, attempt):
    from control_plane.executive_supervisor import SupervisorError
    from control_plane.executive_paid_runtime import validated_paid_launch_material
    from control_plane.paid_model_recovery import PaidModelRecoveryBinding, PaidModelRecoveryRefused
    from control_plane.worker_execution_contract import OrchestrationLaunchSpec

    require_paid_adapter(supervisor)
    raw = attempt.launch_metadata.get("paid_recovery_binding")
    try:
        binding = PaidModelRecoveryBinding.from_dict(raw).validate_wire()
    except (PaidModelRecoveryRefused, TypeError, ValueError) as exc:
        raise SupervisorError("paid original recovery binding did not validate") from exc
    job = supervisor._job(attempt.job_id)
    expected_context = {
        "input_root": str((supervisor._run_dir(attempt.attempt_id) / "input").resolve(strict=False)),
        "source_workspace": str(Path(str(job.worktree)).resolve(strict=False)),
    }
    if dict(binding.control_recovery) != expected_context:
        raise SupervisorError("paid recovery Control coordinates differ from the durable Job")
    # Check original metadata/claim before opening its private prompt.
    with supervisor.runtime.store.read() as connection:
        row = connection.execute("SELECT * FROM attempts WHERE attempt_id=?",
                                 (attempt.attempt_id,)).fetchone()
        if row is None:
            raise SupervisorError("paid recovery lost its original Attempt")
        validated_paid_launch_material(connection, row,
                                       allow_unsealed_principal=attempt.status.value == "CLAIMED")
    try:
        spec = binding.recover_launch_spec(OrchestrationLaunchSpec)
    except (PaidModelRecoveryRefused, TypeError, ValueError, OSError) as exc:
        raise SupervisorError("paid original recovery prompt or launch input changed") from exc
    grant = supervisor._effective_grant(job, attempt)
    if (spec.run_id != attempt.attempt_id or spec.job_id != attempt.job_id
            or spec.worker_id != attempt.worker_id
            or Path(spec.workspace_path).resolve(strict=False) != Path(str(job.worktree)).resolve(strict=False)
            or Path(spec.run_dir).resolve(strict=False) != supervisor._run_dir(attempt.attempt_id).resolve(strict=False)
            or spec.effective_grant_digest != attempt.effective_grant_digest
            or grant is None or list(spec.authorities) != grant["authorities"]
            or list(spec.allowed_artifact_paths) != grant["write_paths"]):
        raise SupervisorError("paid recovery differs from its immutable Control inputs")
    supervisor.adapter.validate_remote_recovery_coordinates(spec, binding)
    # The paid Runtime join above revalidated the actual immutable profile
    # and claim. No invented lease/token is constructed for a convenience call.
    supervisor._validate_aggregation_schema(job=job, attempt=attempt,
        effective_grant=grant, schema_path=spec.result_schema_path)
    return binding, spec, grant


def owned_terminal_cleanup(supervisor, ref):
    """Read the original owner's cached proof; never invent a UID sweep."""
    from control_plane.executive_supervisor import SupervisorError
    require_paid_adapter(supervisor)
    observed = supervisor.adapter.paid_terminal_observation(ref)
    if type(observed) is not dict or set(observed) != {
        "launch_identity", "owned_launch", "owned_terminal", "capture",
    }:
        raise SupervisorError("paid terminal owner did not supply its exact observation")
    frame = observed["owned_terminal"]
    if type(frame) is not dict or type(frame.get("terminal")) is not dict:
        raise SupervisorError("paid terminal owner supplied an invalid terminal frame")
    cleanup = frame["terminal"].get("cleanup")
    if (type(cleanup) is not dict or cleanup.get("census_proven") is not True
            or cleanup.get("identity_verified") is not True
            or type(cleanup.get("residual_count")) is not int or cleanup["residual_count"] != 0
            or cleanup.get("status") not in {"not_needed", "terminated"}
            or cleanup.get("session_id") != ref.session_id):
        raise SupervisorError("paid original process cleanup is not proven")
    return cleanup


def retain_control_assignment(supervisor, active):
    """Seal only real Control input/result retention, independently of remote cleanup."""
    from control_plane.executive_supervisor import _write_or_verify_private_json
    from control_plane.executive_workspace import seal_control_owned_paths
    import os
    require_paid_adapter(supervisor)
    owned_terminal_cleanup(supervisor, active.process_ref)
    attempt = active.lease.attempt
    job = supervisor._job(attempt.job_id)
    path = supervisor._terminal_assignment_receipt_path(attempt.attempt_id)
    if path.exists():
        from control_plane.executive_supervisor import SupervisorError
        import stat
        existing = supervisor._read_private_receipt(path, name="paid Control retention seal")
        if (set(existing) != {"schema_version", "attempt_id", "job_id",
                             "effective_grant_digest", "control_seal"}
                or existing["schema_version"] != "mastermind.paid_model_control_retention/v1"
                or existing["attempt_id"] != attempt.attempt_id
                or existing["job_id"] != attempt.job_id
                or existing["effective_grant_digest"] != attempt.effective_grant_digest):
            raise SupervisorError("paid Control retention identity changed")
        seal = existing["control_seal"]
        if (type(seal) is not dict or set(seal) != {
                "schema_version", "sealed_at", "control_uid", "paths", "passed"}
                or seal["schema_version"] != "mastermind.executive_assignment_seal/v1"
                or seal["passed"] is not True or seal["control_uid"] != os.geteuid()
                or type(seal["paths"]) is not dict or set(seal["paths"]) != {"run", "workspace"}):
            raise SupervisorError("paid Control retention seal is invalid")
        for label, raw_path in {"run": supervisor._run_dir(attempt.attempt_id),
                                "workspace": Path(str(job.worktree))}.items():
            observed = raw_path.lstat()
            record = seal["paths"][label]
            if type(record) is not dict or type(record.get("after")) is not dict:
                raise SupervisorError("paid Control retention path receipt is invalid")
            after = record["after"]
            actual = {"path": str(raw_path.resolve(strict=True)), "device": observed.st_dev,
                      "inode": observed.st_ino, "mode": stat.S_IMODE(observed.st_mode),
                      "uid": observed.st_uid, "gid": observed.st_gid,
                      "mtime_ns": observed.st_mtime_ns}
            if (not stat.S_ISDIR(observed.st_mode) or stat.S_ISLNK(observed.st_mode)
                    or after != actual or actual["mode"] != 0o700
                    or actual["uid"] != os.geteuid()):
                raise SupervisorError("paid Control retention filesystem identity changed")
        return path
    seal = seal_control_owned_paths({"run": supervisor._run_dir(attempt.attempt_id),
                                     "workspace": str(job.worktree)}, control_uid=os.geteuid())
    payload = {
        "schema_version": "mastermind.paid_model_control_retention/v1",
        "attempt_id": attempt.attempt_id, "job_id": attempt.job_id,
        "effective_grant_digest": attempt.effective_grant_digest, "control_seal": seal,
    }
    path = supervisor._terminal_assignment_receipt_path(attempt.attempt_id)
    _write_or_verify_private_json(path, payload, name="paid Control retention seal")
    return path


def terminal_evidence(supervisor, active, *, collection, validations, assignment, envelope):
    from control_plane.executive_supervisor import SupervisorError
    from control_plane.paid_model_terminal_evidence import validate_paid_model_terminal_evidence
    require_paid_adapter(supervisor)
    observation = supervisor.adapter.paid_terminal_observation(active.process_ref)
    evidence = {
        "schema_version": "mastermind.paid_model_sealed_worker_result_evidence/v1",
        **observation,
        "collection_receipt": collection, "collection_receipt_digest": digest(collection),
        "validation_receipts": validations, "validation_receipts_digest": digest(validations),
        "assignment_seal_receipt": assignment, "assignment_seal_receipt_digest": digest(assignment),
    }
    attestation = supervisor.adapter.launch_attestation(active.process_ref)
    if hasattr(attestation, "to_dict"):
        attestation = attestation.to_dict()
    try:
        return validate_paid_model_terminal_evidence(
            evidence, expected_binding=attestation["binding"],
            expected_process_ref=active.process_ref.to_dict(),
            expected_launch_attestation=attestation,
            expected_launch_identity_sha256=digest(observation["launch_identity"]),
            expected_result_envelope=envelope, expected_grant=active.effective_grant,
        )
    except (TypeError, ValueError) as exc:
        raise SupervisorError("paid terminal evidence did not validate") from exc
