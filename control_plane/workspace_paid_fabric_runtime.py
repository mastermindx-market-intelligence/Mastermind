"""Host-only, bounded references to existing principal-owned paid Fabric runs.

The Runtime is the sole Job/Attempt/launch authority. This module neither
authenticates a browser nor grants a Fabric read: the installed source owner
must supply its current principal/mission identity before and after the actual
native read. Raw launch material stays inside that owner and is never a public
catalog/status wire. Finite attended adapters and ordinary CEO roots are not
silently promoted into this narrower original-native-run binding.
"""
from __future__ import annotations

import copy
import dataclasses
import sqlite3
from typing import Any

from control_plane import executive_runtime as er
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_orchestration_status import _provenance
from control_plane.coo_principal_request import principal_intent_id
from control_plane.executive_paid_runtime import (
    PAID_PROFILE_ID,
    _validated_paid_launch_evidence,
)


PAID_FABRIC_READ_LIMIT = 8
PAID_FABRIC_READ_SCHEMA = "mastermind.workspace_paid_fabric_runtime/v1"


class PaidFabricRootNotBound(er.RuntimeReadUnavailable):
    """A validated ordinary CEO root has no admitted principal Fabric binding.

    Catch only inside the observation context, then require its finalized SAME
    receipt. Missing/corrupt evidence and foreign/current-generation mismatches
    never produce this classification and cannot be omitted as an empty scope.
    """

    def __init__(self, root_job_id: str, root_creation_digest: str) -> None:
        super().__init__("validated ordinary CEO root has no principal Fabric binding")
        self.root_job_id = root_job_id
        self.root_creation_digest = root_creation_digest
        self.snapshot_digest = er._bounded_runtime_snapshot_digest({
            "kind": "ORDINARY_CEO_ROOT_NOT_PRINCIPAL_BOUND",
            "root_job_id": root_job_id, "root_creation_digest": root_creation_digest,
        })
        self.observation_source_identity: str | None = None


@dataclasses.dataclass(frozen=True)
class PaidFabricRunReference:
    """Detached host material, not serializable browser authority."""

    job_id: str
    attempt_id: str
    run_id: str
    root_id: str
    parent_run_id: str
    remote_launch_identity_sha256: str
    physical_binding_sha256: str
    process_ref_sha256: str
    effective_grant_digest: str
    execution_principal_snapshot_digest: str
    attempt_version: int
    fence_generation: int
    # These include private prompt/path/source observations. Deliberately no
    # public to_dict() and no automatic repr of the retained launch request.
    launch_request: dict[str, Any] = dataclasses.field(repr=False)
    physical_binding: dict[str, Any] = dataclasses.field(repr=False)
    process_ref: dict[str, Any] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class BoundedPaidFabricSnapshot:
    schema_version: str
    root_job_id: str
    runs: tuple[PaidFabricRunReference, ...]
    limit: int
    selected_count: int
    unlaunched_count: int
    truncated: bool
    partial: bool
    root_creation_digest: str
    snapshot_digest: str
    observation_source_identity: str | None = None


def _principal_root(loader: Any, root_token: str, context: PrincipalAdmissionContext):
    root = loader.execute("SELECT * FROM jobs WHERE job_id=?", (root_token,)).fetchone()
    if root is None:
        raise er.RuntimeReadUnavailable("paid Fabric root is unavailable")
    role, cycle, digest = er._decode_orchestration_job_fields(root)
    if (role != "aggregation" or root["parent_job_id"] is not None
            or root["root_job_id"] != root_token or root["depth"] != 0
            or not isinstance(cycle, dict)
            or er._orchestration_root_creator(cycle) not in {
                er.CEO_ORCHESTRATION_ROOT_CREATOR, er.PRINCIPAL_ORCHESTRATION_ROOT_CREATOR}
            or cycle.get("job_id") != root_token or cycle.get("root_job_id") != root_token
            or cycle.get("parent_job_id") is not None or cycle.get("role") != role
            or digest != er.orchestration_digest(cycle)):
        raise er.RuntimeReadUnavailable("paid Fabric requires a principal-governed root")
    # Check both identity directions and the canonical command, so an extra or
    # misbound creation cannot be hidden by selecting only the good envelope.
    rows = loader.execute(
        "SELECT * FROM events WHERE event_type='JOB_CREATED' AND "
        "(job_id=? OR (aggregate_type='job' AND aggregate_id=?) OR command_id=?) "
        "ORDER BY event_id LIMIT 2",
        (root_token, root_token, cycle.get("command_id")),
    ).fetchall()
    if len(rows) != 1:
        raise er.RuntimeReadUnavailable("paid Fabric root creation is not exact")
    event = rows[0]
    payload = er._strict_canonical_json_loads(
        str(event["payload_json"]), name="paid Fabric root creation"
    )
    if (event["aggregate_type"] != "job" or event["aggregate_id"] != root_token
            or event["job_id"] != root_token or event["command_id"] != cycle.get("command_id")
            or any(event[key] is not None for key in ("attempt_id", "worker_id", "quota_class"))
            or not isinstance(payload, dict) or payload.get("root_job_id") != root_token
            or "parent_job_id" not in payload or payload["parent_job_id"] is not None
            or type(payload.get("depth")) is not int or payload["depth"] != 0
            or payload.get("status") != "QUEUED"
            or payload.get("orchestration_role") != "aggregation"
            or payload.get("orchestration_provenance_digest") != digest):
        raise er.RuntimeReadUnavailable("paid Fabric root creation identity differs")
    provenance = payload.get("provenance")
    if cycle["creator"] == er.CEO_ORCHESTRATION_ROOT_CREATOR:
        from control_plane.fabric_job_view import _bounded_provenance

        event_value = dataclasses.replace(er._event_from_row(event), payload=payload)
        admitted, warning = _bounded_provenance(None, er._job_from_row(root),
            creation_event_reader=lambda _command: event_value)
        ordinary_required = {"schema", "intent_id", "actor", "fingerprint", "grounding"}
        ordinary_allowed = ordinary_required | {"workstream", "frontier_model_alias",
            "frontier_selection", "frontier_selection_digest", "dialogue_source", "dialogue_source_digest"}
        if (warning is not None or not isinstance(admitted, dict)
                or not isinstance(provenance, dict)
                or not ordinary_required <= set(provenance) <= ordinary_allowed
                or admitted.get("schema") != "mastermind.ceo_intent.v2"
                or admitted.get("workstream") != context.work_ref):
            raise er.RuntimeReadUnavailable("paid Fabric ordinary root provenance is unavailable")
        # Validate any optional original commission too; corruption is never a
        # reason to silently omit an otherwise recognizable ordinary root.
        er._dialogue_source_from_root_creation(loader, root_job_id=root_token)
        raise PaidFabricRootNotBound(root_token, er._bounded_runtime_snapshot_digest(dict(event)))
    try:
        request_ref = provenance.get("request_ref") if isinstance(provenance, dict) else None
        intent_id = principal_intent_id(request_ref)
        admitted = _provenance(provenance, request_ref=request_ref,
            intent_id=intent_id, work_ref=context.work_ref)
    except (TypeError, ValueError) as exc:
        raise er.RuntimeReadUnavailable("paid Fabric principal origin is unavailable") from exc
    if (cycle.get("source_id") != intent_id
            or cycle.get("command_id") != "ceo-intent:" + intent_id
            or cycle.get("source_digest") != admitted["bundle_digest"]
            or any(admitted[key] != getattr(context, key) for key in (
                "principal_binding_digest", "mission_authority_ref", "authority_generation_digest"))):
        raise er.RuntimeReadUnavailable("paid Fabric principal authority generation differs")
    # The same original commission is required even for an empty selection.
    if er._dialogue_source_from_root_creation(loader, root_job_id=root_token) is None:
        raise er.RuntimeReadUnavailable("paid Fabric root has no original commission")
    return er._bounded_runtime_snapshot_digest(dict(event))


def read_paid_fabric_runs_bounded(
    acquisition: er.BoundedRuntimeAcquisition,
    vm_guard: er._RuntimeReadProgressGuard,
    *,
    root_job_id: str,
    work_ref: str,
    principal_binding_digest: str,
    mission_authority_ref: str,
    authority_generation_digest: str,
) -> BoundedPaidFabricSnapshot:
    """One Runtime-owned selection, sharing all existing read/VM budgets.

    The identity arguments must come from the installed current owner, never
    browser labels. The returned snapshot is usable only with its finalized
    SAME observation receipt, after the caller exits observe_bounded_read().
    """
    root_token = er._bounded_acquisition_identifier(root_job_id, name="root")
    try:
        context = PrincipalAdmissionContext(work_ref, principal_binding_digest,
            mission_authority_ref, authority_generation_digest)
    except (TypeError, ValueError) as exc:
        raise er.RuntimeReadUnavailable("paid Fabric owner identity is invalid") from exc
    acquisition._require_open()
    loader = er._BoundedRoleResultLoader(acquisition._connection)
    vm_guard.activate()
    try:
        creation_digest = _principal_root(loader, root_token, context)
        candidates = loader.execute(
            "SELECT a.attempt_id FROM jobs AS j JOIN attempts AS a ON a.job_id=j.job_id "
            "WHERE j.root_job_id=? AND json_extract(j.constraints_json,'$.execution_profile_id')=? "
            "ORDER BY a.created_at_ms DESC,a.attempt_id LIMIT ?",
            (root_token, PAID_PROFILE_ID, PAID_FABRIC_READ_LIMIT + 1),
        ).fetchall()
        truncated = len(candidates) > PAID_FABRIC_READ_LIMIT
        references: list[PaidFabricRunReference] = []
        unlaunched = 0
        selected_evidence: list[dict[str, Any]] = []
        for candidate in candidates[:PAID_FABRIC_READ_LIMIT]:
            attempt = loader.execute("SELECT * FROM attempts WHERE attempt_id=?",
                (candidate["attempt_id"],)).fetchone()
            if attempt is None:
                raise er.RuntimeReadUnavailable("paid Fabric selected Attempt disappeared")
            metadata = er._strict_canonical_json_loads(
                str(attempt["launch_metadata_json"]), name="paid Fabric selected launch")
            selected_evidence.append({"attempt_id": attempt["attempt_id"],
                "version": attempt["version"], "fence_generation": attempt["fence_generation"],
                "status": attempt["status"]})
            if (metadata == {} and all(attempt[key] is None for key in (
                    "pid", "pgid", "process_start_identity", "boot_id", "provider_session_id",
                    "execution_principal_snapshot_json", "execution_principal_snapshot_digest"))):
                # Claim before the mandatory remote pin has not acquired an
                # original run. A pin with a lost reply must instead fail the
                # full evidence join below; never return a guessed reference.
                previous_launch = loader.execute(
                    "SELECT event_id FROM events WHERE attempt_id=? AND event_type IN "
                    "('ATTEMPT_REMOTE_LAUNCH_PINNED','ATTEMPT_PROCESS_RECORDED') LIMIT 1",
                    (attempt["attempt_id"],),
                ).fetchone()
                if previous_launch is not None:
                    raise er.RuntimeReadUnavailable("paid Fabric original launch material is missing")
                unlaunched += 1
                continue
            evidence = _validated_paid_launch_evidence(
                loader, attempt, allow_unsealed_principal=False)
            binding = evidence["expected_binding"]
            if binding["root_id"] != root_token:
                raise er.RuntimeReadUnavailable("paid Fabric launch belongs to another root")
            identity = evidence["metadata"]["paid_launch_identity"]
            process_ref = evidence["process_ref"].to_dict()
            references.append(PaidFabricRunReference(
                job_id=binding["job_id"], attempt_id=binding["attempt_id"],
                run_id=binding["attempt_id"], root_id=binding["root_id"],
                parent_run_id=evidence["route"]["parent_job_id"] or binding["root_id"],
                remote_launch_identity_sha256=evidence["metadata"]["paid_launch_identity_sha256"],
                physical_binding_sha256=identity["physical_binding_sha256"],
                process_ref_sha256=er.orchestration_digest(process_ref),
                effective_grant_digest=binding["effective_grant_digest"],
                execution_principal_snapshot_digest=str(attempt["execution_principal_snapshot_digest"]),
                attempt_version=int(attempt["version"]),
                fence_generation=int(attempt["fence_generation"]),
                launch_request=copy.deepcopy(identity["request"]),
                physical_binding=copy.deepcopy(evidence["physical_binding"]),
                process_ref=copy.deepcopy(process_ref),
            ))
        digest_material = {"root_job_id": root_token, "root_creation_digest": creation_digest,
            "owner": dataclasses.asdict(context), "selected": selected_evidence,
            "runs": [{key: value for key, value in dataclasses.asdict(ref).items()
                if key not in {"launch_request", "physical_binding", "process_ref"}} for ref in references],
            "limit": PAID_FABRIC_READ_LIMIT, "unlaunched_count": unlaunched, "truncated": truncated}
        return BoundedPaidFabricSnapshot(
            PAID_FABRIC_READ_SCHEMA, root_token, tuple(references), PAID_FABRIC_READ_LIMIT,
            min(len(candidates), PAID_FABRIC_READ_LIMIT), unlaunched, truncated,
            truncated or unlaunched > 0, creation_digest,
            er._bounded_runtime_snapshot_digest(digest_material),
        )
    except sqlite3.OperationalError as exc:
        if vm_guard.tripped:
            raise er.RuntimeRoleResultOverBudget() from exc
        raise
    finally:
        vm_guard.deactivate()
