"""Connection-local paid SEALED_WORKER evidence joins for the Executive Runtime.

This leaf re-derives the complete immutable evidence of one canonical paid
``fabric.paid.glm.sealed-input.v1`` attempt from the existing durable rows and
events without owning any transition:

* :func:`paid_claim_binding` projects the selected capacity's registry
  metadata into the exact closed ``JOB_CLAIMED`` binding DATA for paid
  dispatch.  It chooses no route and mints nothing.
* :func:`is_paid_attempt` classifies one Attempt for dispatch and refuses any
  paid schema or profile marker on a non-paid Job, so a paid-looking receipt
  can never downgrade to ordinary dispatch.
* :func:`validated_paid_launch_material` re-derives the paid launch
  attestation, execution principal, placement snapshot and effective grant
  from the closed launch metadata, the immutable claim Event, the original
  remote-launch pin Event, the request's worker source document and the
  sealed-input descriptor compiled by the canonical paid contract owner.
* :func:`paid_sealed_worker_result_payload` builds the paid seal-equivalent
  receipt from terminal evidence validated by the paid terminal owner.
* :func:`validated_paid_terminal_evidence` re-validates the terminal event
  history against an already-built paid receipt.

Boundaries kept:

* Read-only SQL over the existing store.  No IO, provider, credential, lease,
  start, config, migration, registry or proof minting happens here; only the
  existing parent Runtime owns transitions.
* Every owner is reused, never reimplemented: the Executive Runtime owners
  are imported dynamically inside the functions
  (``control_plane.executive_runtime`` as ``er``) to avoid a module-load
  cycle, and the paid contract, bridge, typed recovery classes and terminal
  validator are imported from their own modules.  Absent owners refuse
  closed; nothing is simulated.
* All refusals are secret-free :class:`er.StateConflict` raises with static
  messages; receipt bytes, prompts and provider material are never echoed.
* The supervisor-authenticated remote collection supplies the launch
  attestation receipt and the ``source_manifest_sha256`` receipt hash: their
  provider-side origin is the bridge owner's documented trust boundary, not
  something this read side re-proves or self-certifies.  Everything joinable
  to durable rows, events and compiled bytes is joined here.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any

from control_plane.executive_capacity_join import (
    CapacityJoin,
    CapacityJoinError,
    validate_capacity_join,
)
from control_plane.executive_orchestration_principal import (
    OrchestrationPrincipalError,
    digest as orchestration_digest,
    validate_placement_snapshot,
)

__all__ = [
    "PAID_ADAPTER_ID",
    "PAID_CAPACITY_BINDING_SCHEMA",
    "PAID_LAUNCH_ATTESTATION_SCHEMA",
    "PAID_LAUNCH_METADATA_SCHEMA",
    "PAID_MODELS",
    "PAID_PHYSICAL_BINDING_SCHEMA",
    "PAID_PROFILE_ID",
    "PAID_PROVIDER",
    "PAID_RESULT_RECEIPT_SCHEMA",
    "PAID_TERMINAL_EVIDENCE_SCHEMA",
    "PAID_WORKER_SOURCE_SCHEMA",
    "is_paid_attempt",
    "paid_claim_binding",
    "paid_launch_binding_identity",
    "paid_physical_binding_from_worker_source",
    "paid_sealed_worker_result_payload",
    "validated_paid_launch_material",
    "validated_paid_terminal_evidence",
    "validated_paid_worker_source_document",
]

# Frozen profile constants of the canonical paid surface.  The owning
# ``control_plane.paid_model_execution_contract`` module re-proves these
# literals on every paid validation (see :func:`_paid_contract`), so drift
# between this read side and the contract owner refuses closed.
PAID_PROFILE_ID = "fabric.paid.glm.sealed-input.v1"
PAID_ADAPTER_ID = "canonical-paid-fabric"
PAID_PROVIDER = "glm"
PAID_MODELS = frozenset({"glm-5.3", "glm-5.3-flash"})

PAID_LAUNCH_METADATA_SCHEMA = "mastermind.executive_paid_process_launch/v1"
PAID_LAUNCH_ATTESTATION_SCHEMA = (
    "mastermind.executive_paid_model_launch_attestation/v1")
PAID_CAPACITY_BINDING_SCHEMA = "mastermind.paid_capacity_binding/v1"
PAID_WORKER_SOURCE_SCHEMA = "mastermind.paid_worker_source/v1"
PAID_PHYSICAL_BINDING_SCHEMA = "mastermind.paid_fabric_host_binding/v1"
PAID_RESULT_RECEIPT_SCHEMA = (
    "mastermind.paid_model_sealed_worker_result_receipt/v1")
PAID_TERMINAL_EVIDENCE_SCHEMA = (
    "mastermind.paid_model_sealed_worker_terminal_evidence/v1")

_EFFECTIVE_GRANT_SCHEMA = "mastermind.executive_effective_grant/v1"
_PAID_ROLES = frozenset({"work", "repair"})
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_USER_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}\Z")

_PAID_PROFILE_KEYS = (
    "execution_profile_id",
    "execution_profile_digest",
    "capability_policy_version",
    "capability_policy_digest",
)
_PAID_METADATA_COMMON_KEYS = frozenset({
    "schema_version",
    "launch_attestation",
    "launch_attestation_sha256",
    "launch_attestation_path",
    "authority_policy_hash",
    "authorities",
    "effective_grant_digest",
    "write_paths",
    "validation_argv",
    "quota_class",
    "routing",
})
_PAID_METADATA_PAID_KEYS = frozenset({
    "paid_recovery_binding",
    "paid_launch_identity",
    "paid_launch_identity_sha256",
})
_PAID_CLAIM_BINDING_KEYS = frozenset({
    "schema_version",
    "worker_id",
    "quota_class",
    "provider",
    "account_label",
    "adapter_id",
    "capacity_join",
    "execution_profile_id",
    "execution_profile_digest",
    "capability_policy_version",
    "capability_policy_digest",
})
_PAID_REQUEST_KEYS = frozenset({
    "binding",
    "physical_binding_sha256",
    "launch_spec",
    "validation_commands",
    "paid_route",
    "paid_input",
    "paid_physical_binding",
    "paid_source_config",
    "paid_account",
    "paid_quota_class",
    "control_recovery",
})
_PAID_REQUEST_OPTIONAL_KEYS = frozenset({
    "control_start",
    "start_request_sha256",
})
_PAID_ROUTE_KEYS = frozenset({"provider", "host_ref", "model", "parent_job_id"})
_PAID_SOURCE_KEYS = frozenset({
    "schema_version",
    "worker_id",
    "provider",
    "host_ref",
    "model",
    "worker_uid",
    "worker_gid",
    "worker_user",
    "binary",
    "permission_profile_sha256",
    "execution_profile_digest",
    "service_source_sha256",
    "bridge_uid",
    "socket_path",
    "capacity_capability_id",
    "capture_root",
    "qualification",
})
_PAID_BINARY_KEYS = frozenset({
    "path",
    "real_path",
    "version",
    "sha256",
    "team_identifier",
    "size",
    "device",
    "inode",
    "mode",
    "uid",
    "gid",
    "mtime_ns",
})
_PAID_COMPILER_KEYS = (
    "binding",
    "physical_binding_sha256",
    "launch_spec",
    "validation_commands",
    "paid_route",
    "paid_input",
    "control_recovery",
)
# The exact closed key set of :func:`paid_sealed_worker_result_payload`.
_PAID_RECEIPT_KEYS = frozenset({
    "schema_version",
    "job_id",
    "attempt_id",
    "worker_id",
    "quota_class",
    "orchestration_role",
    "session_epoch_id",
    "process_generation_id",
    "turn_id",
    "provider_session_id",
    "provider_native_turn_id",
    "provider_turn_artifact_digest",
    "raw_result_observation_digest",
    "canonical_result_byte_length",
    "candidate_event_command_id",
    "candidate_event_digest",
    "result_envelope",
    "result_envelope_digest",
    "role_result_digest",
    "work_admission_command_id",
    "observed_attestation_digest",
    "execution_principal_snapshot_digest",
    "placement_snapshot_digest",
    "effective_grant_digest",
    "policy_sha",
})


def _refuse(message: str) -> None:
    """Raise the existing Runtime conflict with one static, secret-free line."""
    import control_plane.executive_runtime as er

    raise er.StateConflict(message)


def _row_value(row: sqlite3.Row, name: str) -> Any:
    """Read one optionally-present joined column; ``None`` when absent."""
    try:
        return row[name]
    except IndexError:
        return None


def _canonical_absolute_path(value: Any) -> str:
    """Accept one canonical absolute POSIX path string, DATA only."""
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or not value.startswith("/")
    ):
        _refuse("paid launch path is not an absolute string")
    if any(part in ("", ".", "..") for part in value.split("/")[1:]):
        _refuse("paid launch path is not canonical")
    return value


def _sha256_of_prompt(prompt: str) -> str:
    import hashlib

    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _paid_contract():
    """Bind the canonical paid contract owner and re-prove the frozen profile."""
    try:
        from control_plane import paid_model_execution_contract as contract
    except ImportError:
        _refuse("the canonical paid model contract owner is unavailable")
    if (
        contract.PROFILE_ID != PAID_PROFILE_ID
        or contract.ADAPTER_ID != PAID_ADAPTER_ID
        or contract.ATTESTATION_SCHEMA != PAID_LAUNCH_ATTESTATION_SCHEMA
        or set(contract.MODELS) != set(PAID_MODELS)
    ):
        _refuse("the paid contract owner drifted from the runtime joins")
    return contract


def _paid_metadata_markers(metadata: Any) -> bool:
    """Whether one launch-metadata object carries any paid schema/profile mark."""
    if not isinstance(metadata, dict):
        return False
    attestation = metadata.get("launch_attestation")
    routing = metadata.get("routing")
    return (
        metadata.get("schema_version") == PAID_LAUNCH_METADATA_SCHEMA
        or (
            isinstance(attestation, dict)
            and attestation.get("schema_version") == PAID_LAUNCH_ATTESTATION_SCHEMA
        )
        or (
            isinstance(routing, dict)
            and (
                routing.get("adapter_id") == PAID_ADAPTER_ID
                or routing.get("execution_profile_id") == PAID_PROFILE_ID
            )
        )
    )


def paid_claim_binding(
    capacity: sqlite3.Row,
    constraints: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Project the selected capacity into paid ``JOB_CLAIMED`` binding DATA.

    Returns ``None`` unless the dispatch constraints carry the exact canonical
    paid execution profile.  For a paid profile the selected capacity row must
    prove the closed paid identity: present worker/quota/provider/account
    strings, provider and worker provider ``glm``, a paid model, the
    ``canonical-paid-fabric`` adapter, the four profile identities equal to
    the dispatch constraints, and a valid capacity join.  The returned DATA is
    exactly what the claim Event stores; no route is chosen and nothing is
    minted.
    """
    if not isinstance(constraints, Mapping):
        _refuse("paid dispatch constraints must be a mapping")
    if constraints.get("execution_profile_id") != PAID_PROFILE_ID:
        return None
    import control_plane.executive_runtime as er

    worker_id = capacity["worker_id"]
    quota_class = capacity["quota_class"]
    provider = capacity["provider"]
    worker_provider = _row_value(capacity, "worker_provider")
    account_label = _row_value(capacity, "account_label")
    model = capacity["model"]
    if (
        type(worker_id) is not str or not worker_id
        or type(quota_class) is not str or not quota_class
        or type(account_label) is not str or not account_label
        or provider != PAID_PROVIDER or worker_provider != PAID_PROVIDER
        or type(model) is not str or model not in PAID_MODELS
    ):
        _refuse("selected paid capacity identity is invalid")
    metadata = er._strict_canonical_json_loads(
        str(capacity["metadata_json"]),
        name="paid selected capacity metadata",
    )
    if not isinstance(metadata, dict):
        _refuse("paid selected capacity metadata is not an object")
    try:
        capacity_join = validate_capacity_join(metadata.get("capacity_join"))
    except CapacityJoinError:
        _refuse("paid selected capacity join is invalid")
    profile_identities = {key: metadata.get(key) for key in _PAID_PROFILE_KEYS}
    if (
        metadata.get("adapter_id") != PAID_ADAPTER_ID
        or any(
            type(value) is not str or not value
            for value in profile_identities.values()
        )
        or any(
            profile_identities[key] != constraints.get(key)
            for key in _PAID_PROFILE_KEYS
        )
    ):
        _refuse(
            "paid selected capacity profile differs from the dispatch constraints"
        )
    return {
        "schema_version": PAID_CAPACITY_BINDING_SCHEMA,
        "worker_id": worker_id,
        "quota_class": quota_class,
        "provider": provider,
        "account_label": account_label,
        "adapter_id": PAID_ADAPTER_ID,
        "capacity_join": capacity_join.to_dict(),
        "execution_profile_id": profile_identities["execution_profile_id"],
        "execution_profile_digest": profile_identities["execution_profile_digest"],
        "capability_policy_version": profile_identities[
            "capability_policy_version"
        ],
        "capability_policy_digest": profile_identities[
            "capability_policy_digest"
        ],
    }


def is_paid_attempt(
    connection: sqlite3.Connection,
    attempt_row: sqlite3.Row,
) -> bool:
    """Classify one Attempt for paid dispatch without weakening any label.

    The Job's immutable execution profile decides: a paid Job dispatches
    paid.  Any paid schema or routing marker on a non-paid Job refuses
    closed, so a paid-looking launch receipt can never downgrade to ordinary
    dispatch.  The main paid caller additionally checks paid dispatch itself
    whenever the required schema is not passed.
    """
    import control_plane.executive_runtime as er

    job_row = connection.execute(
        "SELECT constraints_json FROM jobs WHERE job_id=?",
        (attempt_row["job_id"],),
    ).fetchone()
    if job_row is None:
        _refuse("paid dispatch lost its Job")
    constraints = er._strict_canonical_json_loads(
        str(job_row["constraints_json"]),
        name="paid dispatch Job constraints",
    )
    if not isinstance(constraints, dict):
        _refuse("paid dispatch Job constraints are not an object")
    if constraints.get("execution_profile_id") == PAID_PROFILE_ID:
        return True
    metadata = er._strict_canonical_json_loads(
        str(attempt_row["launch_metadata_json"]),
        name="paid dispatch attempt metadata",
    )
    if _paid_metadata_markers(metadata):
        _refuse("paid launch markers on a non-paid Job refuse label downgrade")
    return False


def paid_launch_binding_identity(
    *,
    root_job_id: str,
    job_id: str,
    attempt_id: str,
    effective_grant_digest: str,
    commission_sha256: str,
) -> dict[str, str]:
    """Build the exact five-key immutable binding one paid launch joins to.

    Every paid request, descriptor and attestation must carry exactly this
    binding: the root Job, the dispatched Job, the Attempt, the effective
    grant digest and the canonical root-commission digest.
    """
    if (
        type(root_job_id) is not str or not root_job_id
        or type(job_id) is not str or not job_id
        or type(attempt_id) is not str or not attempt_id
        or type(effective_grant_digest) is not str
        or _DIGEST_RE.fullmatch(effective_grant_digest) is None
        or type(commission_sha256) is not str
        or _DIGEST_RE.fullmatch(commission_sha256) is None
    ):
        _refuse("paid launch binding identity is invalid")
    return {
        "root_id": root_job_id,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "effective_grant_digest": effective_grant_digest,
        "commission_sha256": commission_sha256,
    }


def validated_paid_worker_source_document(
    value: Any,
    *,
    claim: Mapping[str, Any],
    claim_join: CapacityJoin,
    expected_model: Any,
) -> dict[str, Any]:
    """Join the request's paid worker source document to the immutable claim.

    The document must be the closed ``mastermind.paid_worker_source/v1`` wire,
    carry a strictly-shaped binary attestation, and hash exactly to the
    claimed capacity join's ``worker_source_config_digest`` with the exact
    host and capability identity.  No substitution of service, source-config
    or capability facts is accepted.
    """
    if not isinstance(claim_join, CapacityJoin):
        claim_join = validate_capacity_join(claim_join)
    if (
        type(value) is not dict
        or set(value) != _PAID_SOURCE_KEYS
        or value["schema_version"] != PAID_WORKER_SOURCE_SCHEMA
    ):
        _refuse("paid worker source document is not the closed wire")
    binary = value["binary"]
    if type(binary) is not dict or set(binary) != _PAID_BINARY_KEYS:
        _refuse("paid worker source binary attestation is not the closed wire")
    if (
        type(binary["path"]) is not str or not binary["path"]
        or type(binary["real_path"]) is not str or not binary["real_path"]
        or type(binary["version"]) is not str or not binary["version"]
        or type(binary["sha256"]) is not str
        or _DIGEST_RE.fullmatch(binary["sha256"]) is None
        or not (
            binary["team_identifier"] is None
            or (
                type(binary["team_identifier"]) is str
                and bool(binary["team_identifier"])
            )
        )
        or type(binary["size"]) is not int or binary["size"] <= 0
        or any(
            type(binary[name]) is not int or binary[name] < 0
            for name in ("device", "inode", "mode", "uid", "gid", "mtime_ns")
        )
    ):
        _refuse("paid worker source binary attestation is invalid")
    if (
        value["worker_id"] != claim["worker_id"]
        or value["provider"] != claim["provider"]
        or value["model"] != expected_model
        or value["host_ref"] != claim_join.host_ref
        or value["capacity_capability_id"] != claim_join.capacity_capability_id
        or value["execution_profile_digest"] != claim["execution_profile_digest"]
        or type(value["worker_user"]) is not str
        or _USER_RE.fullmatch(value["worker_user"]) is None
        or type(value["worker_uid"]) is not int or value["worker_uid"] <= 0
        or type(value["worker_gid"]) is not int or value["worker_gid"] <= 0
        or type(value["bridge_uid"]) is not int or value["bridge_uid"] <= 0
        or type(value["permission_profile_sha256"]) is not str
        or _DIGEST_RE.fullmatch(value["permission_profile_sha256"]) is None
        or type(value["service_source_sha256"]) is not str
        or _DIGEST_RE.fullmatch(value["service_source_sha256"]) is None
    ):
        _refuse("paid worker source document differs from the claimed capacity")
    _canonical_absolute_path(value["socket_path"])
    _canonical_absolute_path(value["capture_root"])
    if orchestration_digest(value) != claim_join.worker_source_config_digest:
        _refuse("paid worker source document lost the claimed config digest")
    return dict(value)


def paid_physical_binding_from_worker_source(
    worker_source: Mapping[str, Any],
    *,
    worker_source_config_digest: Any,
) -> dict[str, Any]:
    """Derive the exact physical host-binding facts from a validated source.

    The physical binding repeats every source fact except the capacity
    capability id, adds the source-config digest and carries the paid fabric
    host-binding schema.
    """
    if (
        not isinstance(worker_source, Mapping)
        or set(worker_source) != _PAID_SOURCE_KEYS
        or type(worker_source_config_digest) is not str
        or _DIGEST_RE.fullmatch(worker_source_config_digest) is None
    ):
        _refuse("paid physical host binding derivation refused")
    physical = {
        key: worker_source[key]
        for key in _PAID_SOURCE_KEYS
        if key not in ("schema_version", "capacity_capability_id")
    }
    physical["schema_version"] = PAID_PHYSICAL_BINDING_SCHEMA
    physical["worker_source_config_digest"] = worker_source_config_digest
    return physical


def _paid_compiler_subset(request: Mapping[str, Any]) -> dict[str, Any]:
    """The exact subset of the pinned request the sealed-input compiler owns.

    The parent's start channel may carry ``control_start`` and
    ``start_request_sha256``; those are not sealed-input facts and never
    enter the compiled descriptor.
    """
    return {key: request[key] for key in _PAID_COMPILER_KEYS}


def validated_paid_launch_material(
    connection: sqlite3.Connection,
    attempt_row: sqlite3.Row,
    *,
    allow_unsealed_principal: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Re-derive the paid principal from its complete launch receipt.

    Returns the same common four-part contract as the sealed-worker launch
    material owner: the launch attestation, the execution principal, the
    placement snapshot and the effective grant.  The first principal sealing
    of a fresh Attempt passes ``allow_unsealed_principal``; no persisted
    receipt is ever backfilled.
    """
    evidence = _validated_paid_launch_evidence(
        connection,
        attempt_row,
        allow_unsealed_principal=allow_unsealed_principal,
    )
    return (
        evidence["attestation"],
        evidence["principal"],
        evidence["placement"],
        evidence["grant"],
    )


def _validated_paid_launch_evidence(
    connection: sqlite3.Connection,
    attempt_row: sqlite3.Row,
    *,
    allow_unsealed_principal: bool,
) -> dict[str, Any]:
    """Join every paid launch plane; internal, returns the full evidence map."""
    import control_plane.executive_runtime as er

    contract = _paid_contract()
    metadata = er._strict_canonical_json_loads(
        str(attempt_row["launch_metadata_json"]),
        name="paid launch metadata",
    )
    pin_key = er.REMOTE_LAUNCH_IDENTITY_KEY
    if (
        type(metadata) is not dict
        or set(metadata)
        != _PAID_METADATA_COMMON_KEYS | _PAID_METADATA_PAID_KEYS | {pin_key}
    ):
        _refuse("paid launch metadata is not the closed wire")
    if metadata["schema_version"] != PAID_LAUNCH_METADATA_SCHEMA:
        _refuse("paid launch metadata schema is invalid")
    pin = metadata[pin_key]
    if (
        type(pin) is not dict
        or set(pin) != {"schema_version", "sha256"}
        or pin["schema_version"] != er.REMOTE_LAUNCH_IDENTITY_SCHEMA
        or type(pin["sha256"]) is not str
        or _DIGEST_RE.fullmatch(pin["sha256"]) is None
        or metadata["paid_launch_identity_sha256"] != pin["sha256"]
    ):
        _refuse("paid remote launch pin is invalid")
    attestation = metadata["launch_attestation"]
    if (
        type(attestation) is not dict
        or attestation.get("schema_version") != PAID_LAUNCH_ATTESTATION_SCHEMA
        or metadata["launch_attestation_sha256"] != orchestration_digest(attestation)
    ):
        _refuse("paid launch attestation is invalid")
    _canonical_absolute_path(metadata["launch_attestation_path"])
    if (
        metadata["authority_policy_hash"] != attempt_row["authority_policy_hash"]
        or metadata["effective_grant_digest"] != attempt_row["effective_grant_digest"]
        or metadata["quota_class"] != attempt_row["quota_class"]
        or type(metadata["authorities"]) is not list
        or type(metadata["write_paths"]) is not list
        or type(metadata["validation_argv"]) is not list
        or metadata["validation_argv"] != []
        or type(metadata["routing"]) is not dict
    ):
        _refuse("paid launch metadata lost its Attempt bindings")
    routing = metadata["routing"]
    if (
        set(routing) != {"adapter_id", "policy_version", "preferred_model_aliases",
                            "selected_model_alias", "provider_alias", *_PAID_PROFILE_KEYS}
        or routing["adapter_id"] != PAID_ADAPTER_ID
        or any(type(routing[key]) is not str or not routing[key]
               for key in _PAID_PROFILE_KEYS)
    ):
        _refuse("paid launch routing identity is invalid")

    job_row = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (attempt_row["job_id"],)
    ).fetchone()
    if job_row is None:
        _refuse("paid launch lost its Job")
    constraints = er._strict_canonical_json_loads(
        str(job_row["constraints_json"]),
        name="paid launch Job constraints",
    )
    if (
        type(constraints) is not dict
        or constraints.get("execution_profile_id") != PAID_PROFILE_ID
        or any(constraints.get(key) != routing[key] for key in _PAID_PROFILE_KEYS)
    ):
        _refuse("paid launch requires the canonical paid execution profile")
    if (routing['policy_version'] != constraints.get('routing_policy_version')
            or routing['preferred_model_aliases'] != constraints.get('preferred_model_aliases', [])
            or routing['selected_model_alias'] not in routing['preferred_model_aliases']
            or routing['provider_alias'] != PAID_PROVIDER):
        _refuse("paid routing differs from its immutable catalog selection")
    if job_row["orchestration_role"] not in _PAID_ROLES:
        _refuse("paid launch accepts work and repair Jobs only")
    job_validation_commands = er._strict_canonical_json_loads(
        str(job_row["validation_commands_json"]),
        name="paid launch Job validation commands",
    )
    if job_validation_commands != []:
        _refuse("paid launch accepts sealed-input Jobs without shell validations")

    try:
        grant = er._load_canonical_digest_pair(
            attempt_row["effective_grant_json"],
            attempt_row["effective_grant_digest"],
            name="paid effective grant",
        )
        placement = validate_placement_snapshot(
            er._load_canonical_digest_pair(
                attempt_row["placement_snapshot_json"],
                attempt_row["placement_snapshot_digest"],
                name="paid placement snapshot",
            )
        )
    except (OrchestrationPrincipalError, er.PersistenceError) as exc:
        _refuse(f"paid immutable launch evidence is invalid: {type(exc).__name__}")
    authorities = grant.get("authorities") if isinstance(grant, dict) else None
    if (
        type(grant) is not dict
        or grant.get("schema_version") != _EFFECTIVE_GRANT_SCHEMA
        or grant.get("job_id") != attempt_row["job_id"]
        or grant.get("policy_sha") != attempt_row["authority_policy_hash"]
        or metadata["authorities"] != grant.get("authorities")
        or metadata["write_paths"] != grant.get("write_paths")
        or metadata["validation_argv"] != grant.get("validation_argv")
        or grant.get("write_paths") != [] or grant.get("validation_argv") != []
        or grant.get("role") != job_row["orchestration_role"]
    ):
        _refuse("paid placement/grant launch binding is invalid")
    if (
        type(authorities) is not list
        or any(type(item) is not str for item in authorities)
        or len(authorities) != len(set(authorities))
        or set(authorities) not in ({"READ"}, {"READ", "RESEARCH"})
    ):
        _refuse("paid grant authorities are READ with optional RESEARCH only")
    if (
        placement["worker_id"] != attempt_row["worker_id"]
        or placement["quota_class"] != attempt_row["quota_class"]
    ):
        _refuse("paid placement lost the claimed quota")

    claim_events = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='JOB_CLAIMED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_row["attempt_id"],),
    ).fetchall()
    if len(claim_events) != 1:
        _refuse("paid launch claim cardinality is not exact")
    claim_event = claim_events[0]
    if (
        claim_event["aggregate_type"] != "job"
        or claim_event["aggregate_id"] != attempt_row["job_id"]
        or claim_event["job_id"] != attempt_row["job_id"]
        or claim_event["attempt_id"] != attempt_row["attempt_id"]
        or claim_event["worker_id"] != attempt_row["worker_id"]
        or claim_event["quota_class"] != attempt_row["quota_class"]
    ):
        _refuse("paid launch claim Event lost the claimed quota")
    claim_payload = er._strict_canonical_json_loads(
        str(claim_event["payload_json"]),
        name="paid launch claim payload",
    )
    claim = (
        claim_payload.get("paid_capacity_binding")
        if isinstance(claim_payload, dict)
        else None
    )
    if type(claim) is not dict or set(claim) != _PAID_CLAIM_BINDING_KEYS:
        _refuse("paid launch claim capacity binding is not the closed wire")
    if (
        claim["schema_version"] != PAID_CAPACITY_BINDING_SCHEMA
        or claim["worker_id"] != attempt_row["worker_id"]
        or claim["quota_class"] != attempt_row["quota_class"]
        or claim["provider"] != PAID_PROVIDER
        or claim["adapter_id"] != PAID_ADAPTER_ID
        or type(claim["account_label"]) is not str or not claim["account_label"]
        or any(type(claim[key]) is not str or not claim[key]
               for key in _PAID_PROFILE_KEYS)
    ):
        _refuse("paid launch claim capacity binding is invalid")
    try:
        claim_join = validate_capacity_join(claim["capacity_join"])
    except CapacityJoinError:
        _refuse("paid launch claim capacity join is invalid")
    if (
        placement["provider"] != claim["provider"]
        or placement["account_label"] != claim["account_label"]
        or any(claim[key] != constraints.get(key) for key in _PAID_PROFILE_KEYS)
        or any(claim[key] != routing[key] for key in _PAID_PROFILE_KEYS)
        or any(claim_payload.get(key) != claim[key] for key in _PAID_PROFILE_KEYS)
    ):
        _refuse("paid claim profile or account differs from the immutable claim")

    identity = metadata["paid_launch_identity"]
    if (
        type(identity) is not dict
        or set(identity) != {"physical_binding_sha256", "request"}
        or type(identity["physical_binding_sha256"]) is not str
        or _DIGEST_RE.fullmatch(identity["physical_binding_sha256"]) is None
        or orchestration_digest(identity) != metadata["paid_launch_identity_sha256"]
    ):
        _refuse("paid launch identity is invalid")
    request = identity["request"]
    if (
        type(request) is not dict
        or not _PAID_REQUEST_KEYS <= set(request)
        or set(request) - _PAID_REQUEST_KEYS - _PAID_REQUEST_OPTIONAL_KEYS
    ):
        _refuse("paid launch request is not the closed wire")
    launch_spec = request["launch_spec"]
    paid_input = request["paid_input"]
    if (
        type(request["validation_commands"]) is not list
        or request["validation_commands"] != job_validation_commands
        or request["physical_binding_sha256"] != identity["physical_binding_sha256"]
        or type(launch_spec) is not dict
        or type(launch_spec.get("prompt")) is not str
        or not launch_spec["prompt"]
        or type(paid_input) is not dict
        or set(paid_input) != {"prompt", "result_schema"}
        or paid_input["prompt"] != launch_spec["prompt"]
        or type(paid_input["result_schema"]) is not dict
        or not paid_input["result_schema"]
    ):
        _refuse("paid sealed input differs from the pinned launch request")

    route = request["paid_route"]
    if (
        type(route) is not dict
        or set(route) != _PAID_ROUTE_KEYS
        or route["provider"] != PAID_PROVIDER
        or route["provider"] != claim["provider"]
        or type(route["model"]) is not str or route["model"] not in PAID_MODELS
        or type(route["host_ref"]) is not str
        or route["host_ref"] != claim_join.host_ref
        or route["parent_job_id"] != job_row["parent_job_id"]
        or (route["parent_job_id"] is None)
        != (str(job_row["job_id"]) == str(job_row["root_job_id"]))
    ):
        _refuse("paid launch route differs from the claimed capacity")

    worker_source = validated_paid_worker_source_document(
        request["paid_source_config"],
        claim=claim,
        claim_join=claim_join,
        expected_model=route["model"],
    )
    physical = request["paid_physical_binding"]
    expected_physical = paid_physical_binding_from_worker_source(
        worker_source,
        worker_source_config_digest=claim_join.worker_source_config_digest,
    )
    if (
        type(physical) is not dict
        or set(physical) != set(expected_physical)
        or physical != expected_physical
        or orchestration_digest(expected_physical)
        != request["physical_binding_sha256"]
    ):
        _refuse("paid physical host binding differs from the worker source")
    paid_account = request["paid_account"]
    if (type(paid_account) is not str or paid_account != claim['account_label']
            or request['paid_quota_class'] != claim['quota_class']):
        _refuse("paid launch account differs from the immutable claim")
    try:
        from control_plane.paid_fabric_wire import require_paid_physical, PaidWireRefused
        require_paid_physical(request)
    except PaidWireRefused:
        _refuse("paid qualified physical source contract refused")

    try:
        descriptor = contract.descriptor(_paid_compiler_subset(request))
    except contract.PaidModelContractRefused:
        _refuse("paid sealed input does not compile under the canonical contract")
    if descriptor["binding"] != request["binding"]:
        _refuse("paid compiled descriptor differs from the pinned request binding")

    evidence_map = attestation.get("evidence")
    isolation_sha256 = launch_spec.get("isolation_manifest_sha256")
    expected_evidence = {
        "policy_sha256": descriptor["policy_sha256"],
        "prompt_sha256": descriptor["prompt_sha256"],
        "request_body_sha256": descriptor["request_body_sha256"],
        "result_schema_sha256": descriptor["result_schema_sha256"],
        "physical_binding_sha256": descriptor["physical_binding_sha256"],
        "pin_identity_sha256": metadata["paid_launch_identity_sha256"],
        "python_sha256": worker_source["binary"]["sha256"],
        "control_input_isolation_manifest_sha256": isolation_sha256,
    }
    # ``source_manifest_sha256`` is the authenticated remote collection's own
    # receipt hash on a different plane from the service source digest; it is
    # shape-checked here and never compared to itself as owner proof.
    if (
        type(evidence_map) is not dict
        or any(evidence_map.get(key) != value
               for key, value in expected_evidence.items())
        or type(evidence_map.get("source_manifest_sha256")) is not str
        or _DIGEST_RE.fullmatch(evidence_map["source_manifest_sha256"]) is None
    ):
        _refuse("paid launch evidence differs from the compiled sealed input")
    if type(isolation_sha256) is not str or _DIGEST_RE.fullmatch(
        isolation_sha256
    ) is None:
        _refuse("paid launch lost the Control input isolation manifest digest")

    worker_identity = attestation.get("process_identity")
    process_identity = attestation.get("process_identity")
    if (
        type(worker_identity) is not dict
        or type(process_identity) is not dict
        or worker_identity.get("observed_user") != worker_source["worker_user"]
        or worker_identity.get("effective_uid") != worker_source["worker_uid"]
        or worker_identity.get("effective_gid") != worker_source["worker_gid"]
        or worker_identity.get("real_uid") != worker_source["worker_uid"]
        or worker_identity.get("real_gid") != worker_source["worker_gid"]
        or type(process_identity.get("pid")) is not int
        or process_identity["pid"] <= 0
        or type(process_identity.get("pgid")) is not int
        or process_identity["pgid"] <= 0
        or process_identity["pid"] != attempt_row["pid"]
        or process_identity["pgid"] != attempt_row["pgid"]
        or process_identity.get("start_identity")
        != attempt_row["process_start_identity"]
        or process_identity.get("boot_id") != attempt_row["boot_id"]
        or type(process_identity.get("start_identity")) is not str
        or not process_identity["start_identity"]
        or type(process_identity.get("boot_id")) is not str
        or not process_identity["boot_id"]
        or attempt_row["provider_session_id"] is not None
    ):
        _refuse("paid launch OS/process identity is invalid")

    pin_events = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='ATTEMPT_REMOTE_LAUNCH_PINNED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_row["attempt_id"],),
    ).fetchall()
    if len(pin_events) != 1:
        _refuse("paid launch pin cardinality is not exact")
    pin_event = pin_events[0]
    pin_payload = er._strict_canonical_json_loads(
        str(pin_event["payload_json"]),
        name="paid launch pin receipt",
    )
    if (
        type(pin_payload) is not dict
        or pin_payload.get("identity_digest")
        != metadata["paid_launch_identity_sha256"]
        or type(pin_payload.get("paid_runtime_pin_version")) is not int
        or pin_payload["paid_runtime_pin_version"] <= 0
        or type(pin_payload.get("paid_runtime_fence_generation")) is not int
        or pin_payload["paid_runtime_fence_generation"] <= 0
        or pin_event["actor"] != "supervisor"
        or pin_event["aggregate_type"] != "attempt"
        or pin_event["aggregate_id"] != attempt_row["attempt_id"]
        or pin_event["job_id"] != attempt_row["job_id"]
        or pin_event["worker_id"] != attempt_row["worker_id"]
        or pin_event["quota_class"] != attempt_row["quota_class"]
    ):
        _refuse("paid launch pin receipt is invalid")
    # The pin Event froze the lease's pin-time state.  The durable fence must
    # still equal it; the parent-added lease pin version must match too when
    # this schema carries the column.  The Attempt row's own version is never
    # compared: heartbeat bookkeeping legitimately advances it after the pin.
    launch_fence = pin_payload['paid_runtime_fence_generation']
    if claim_payload.get('fence_generation') != launch_fence:
        _refuse('paid original pin differs from its actual claim fence')
    current_fence = launch_fence
    current_owner = claim_payload.get('lease_owner')
    for adoption in connection.execute(
            "SELECT * FROM events WHERE event_type='ATTEMPT_ADOPTED' AND attempt_id=? ORDER BY event_id",
            (attempt_row['attempt_id'],)).fetchall():
        payload = er._strict_canonical_json_loads(str(adoption['payload_json']), name='paid adoption receipt')
        if (type(payload) is not dict or set(payload) != {'previous_fence_generation','fence_generation',
                'previous_lease_owner','lease_owner','lease_expires_at_ms'}
                or adoption['event_id'] <= pin_event['event_id']
                or adoption['actor'] != 'supervisor' or adoption['aggregate_type'] != 'attempt'
                or adoption['aggregate_id'] != attempt_row['attempt_id']
                or any(adoption[key] != attempt_row[key] for key in ('job_id','worker_id','quota_class'))
                or type(payload['previous_fence_generation']) is not int
                or type(payload['fence_generation']) is not int
                or payload['previous_fence_generation'] != current_fence
                or payload['fence_generation'] != current_fence + 1
                or payload['previous_lease_owner'] != current_owner
                or type(payload['lease_owner']) is not str or not payload['lease_owner']
                or type(payload['lease_expires_at_ms']) is not int or payload['lease_expires_at_ms'] <= 0):
            _refuse('paid adoption chain differs from the original owner history')
        current_fence = payload['fence_generation']
        current_owner = payload['lease_owner']
    if attempt_row['fence_generation'] != current_fence:
        _refuse('paid current fence has no exact original adoption history')
    row_owner = _row_value(attempt_row, 'lease_owner')
    if row_owner is not None and row_owner != current_owner:
        _refuse('paid current owner differs from its exact adoption history')

    # The canonical commission is read from the immutable root creation Event
    # by the existing Runtime owner; no alternate source resolution exists.
    dialogue_source = er._dialogue_source_from_root_creation(
        connection, root_job_id=str(job_row["root_job_id"])
    )
    if dialogue_source is None:
        _refuse("paid launch lost the canonical commission")
    expected_binding = paid_launch_binding_identity(
        root_job_id=str(job_row["root_job_id"]),
        job_id=str(attempt_row["job_id"]),
        attempt_id=str(attempt_row["attempt_id"]),
        effective_grant_digest=str(attempt_row["effective_grant_digest"]),
        commission_sha256=str(dialogue_source.commission_ref.content_sha256),
    )
    if (
        request["binding"] != expected_binding
        or descriptor["binding"] != expected_binding
    ):
        _refuse("paid launch binding differs from the immutable commission")

    from control_plane.worker_execution_contract import (
        PaidModelProcessRef,
        WorkerRecoveryContractError,
    )

    from control_plane.paid_model_recovery import PaidModelRecoveryBinding
    try:
        recovery = (
            PaidModelRecoveryBinding.from_dict(metadata["paid_recovery_binding"])
            .validate_wire()
        )
        if recovery.to_dict() != metadata["paid_recovery_binding"]:
            raise ValueError("paid recovery binding is not the closed wire")
        recovery_material = recovery.to_dict()
        launch_spec_material = recovery_material["launch_spec"]
        fields = launch_spec_material["fields"]
        process_ref = PaidModelProcessRef.from_dict(
            recovery_material["process_ref"]
        )
        ref = process_ref.to_dict()
    except (WorkerRecoveryContractError, TypeError, ValueError) as exc:
        _refuse(f"paid recovery binding is invalid: {type(exc).__name__}")
    field_pins = {
        "job_id": str(attempt_row["job_id"]),
        "run_id": str(attempt_row["attempt_id"]),
        "worker_id": str(attempt_row["worker_id"]),
        "model": route["model"],
        "effective_grant_digest": str(attempt_row["effective_grant_digest"]),
        "authorities": list(authorities),
        "allowed_artifact_paths": grant["write_paths"],
    }
    expected_prompt_sha256 = _sha256_of_prompt(launch_spec["prompt"])
    expected_control_recovery = getattr(recovery, "control_recovery", None)
    if expected_control_recovery is None and isinstance(
        launch_spec_material, Mapping
    ):
        expected_control_recovery = launch_spec_material.get("control_recovery")
    # The existing launch-wire serializer omits the empty legacy canary
    # mapping, while recovery retains every LaunchSpec field. Paid execution
    # never admits a canary claim; normalize only that known empty omission.
    recovered_fields = dict(fields) if isinstance(fields, Mapping) else {}
    if recovered_fields.get("subscription_canary_claim") == {}:
        recovered_fields.pop("subscription_canary_claim")
    if (
        not isinstance(fields, Mapping)
        or any(fields.get(name) != value for name, value in field_pins.items())
        or {key: value for key, value in launch_spec.items() if key != "prompt"}
        != recovered_fields
        or launch_spec_material.get("prompt_sha256") != expected_prompt_sha256
        or expected_control_recovery is None
        or request["control_recovery"] != expected_control_recovery
    ):
        _refuse("paid recovery binding lost its launch identity")
    if (
        ref.get("run_id") != str(attempt_row["attempt_id"])
        or ref.get("pid") != attempt_row["pid"]
        or ref.get("pgid") != attempt_row["pgid"]
        or ref.get("process_start_identity")
        != attempt_row["process_start_identity"]
        or ref.get("boot_session_id") != attempt_row["boot_id"]
        or ref.get("effective_uid") != worker_source["worker_uid"]
        or ref.get("effective_gid") != worker_source["worker_gid"]
        or ref.get("real_uid") != worker_source["worker_uid"]
        or ref.get("real_gid") != worker_source["worker_gid"]
        or recovery.capture_root != worker_source['capture_root']
        or ref.get("binary") != worker_source['binary']
        or ref.get("provider_session_id") is not None
        # Cross-plane ref facts are compared whenever the typed reference
        # carries them; the reference class owns their exact closed shape.
        or ("worker_user" in ref and ref["worker_user"]
            != worker_source["worker_user"])
        or ("host_ref" in ref and ref["host_ref"] != worker_source["host_ref"])
        or (
            "binary_sha256" in ref
            and ref["binary_sha256"] != worker_source["binary"]["sha256"]
        )
        or (
            isinstance(ref.get("binary"), dict)
            and ref["binary"].get("sha256")
            != worker_source["binary"]["sha256"]
        )
    ):
        _refuse("paid process reference differs from the durable Attempt")

    expected_process = {
        "pid": attempt_row["pid"], "pgid": attempt_row["pgid"],
        "session_id": ref['session_id'], "start_identity": attempt_row["process_start_identity"],
        "boot_id": attempt_row["boot_id"], "observed_user": worker_source["worker_user"],
        "effective_uid": worker_source["worker_uid"], "effective_gid": worker_source["worker_gid"],
        "real_uid": worker_source["worker_uid"], "real_gid": worker_source["worker_gid"],
        "launch_nonce": ref['launch_nonce'],
    }
    # Lease id/controller generation and these three remote-owner digests are
    # retained authenticated owner receipt DATA, not independently observed by
    # this SQL reader. The actual typed adapter qualifies their origin; this
    # reader additionally joins every immutable Runtime/account/source fact.
    raw_lease = attestation.get('lease_binding')
    if type(raw_lease) is not dict:
        _refuse('paid original owner lease receipt is missing')
    expected_lease_binding = dict(raw_lease)
    expected_lease_binding.update(orchestrator_id=str(job_row['root_job_id']),
        account=claim['account_label'],host_ref=worker_source['host_ref'],model=route['model'],
        runtime_pin_version=int(pin_payload['paid_runtime_pin_version']),
        runtime_fence_generation=int(pin_payload['paid_runtime_fence_generation']))
    for key in ('source_manifest_sha256','capsule_binding_sha256','capture_contract_sha256'):
        expected_evidence[key] = evidence_map.get(key)
    try:
        from control_plane.paid_model_execution_principal import (
            build_paid_model_principal,
            validate_paid_model_attestation,
        )

        validate_paid_model_attestation(
            attestation,
            expected_binding=expected_binding,
            expected_route=route,
            expected_worker_id=str(attempt_row["worker_id"]),
            expected_quota_class=str(attempt_row["quota_class"]),
            expected_process=expected_process,
            expected_lease_binding=expected_lease_binding,
            expected_evidence=expected_evidence,
        )
        principal = build_paid_model_principal(
            attestation, placement, str(attempt_row["attempt_id"])
        )
    except (TypeError, ValueError, KeyError) as exc:
        _refuse(
            "paid launch attestation failed bridge validation: "
            f"{type(exc).__name__}"
        )
    stored_principal = er._load_canonical_digest_pair(
        attempt_row["execution_principal_snapshot_json"],
        attempt_row["execution_principal_snapshot_digest"],
        name="paid execution principal snapshot",
    )
    if stored_principal is None:
        if not allow_unsealed_principal:
            _refuse("paid launch has no immutable principal snapshot")
    elif (
        stored_principal != principal
        or attempt_row["execution_principal_snapshot_digest"]
        != orchestration_digest(principal)
    ):
        _refuse("paid principal snapshot drifted from launch")
    return {
        "attestation": dict(attestation),
        "principal": principal,
        "placement": placement,
        "grant": grant,
        "metadata": metadata,
        "claim": claim,
        "claim_payload": claim_payload,
        "claim_join": claim_join,
        "route": route,
        "worker_source": worker_source,
        "physical_binding": physical,
        "recovery": recovery,
        "process_ref": process_ref,
        "expected_binding": expected_binding,
        "descriptor": descriptor,
        "expected_process": expected_process,
        "expected_lease_binding": expected_lease_binding,
        "expected_evidence": expected_evidence,
        "pin_payload": pin_payload,
    }


def paid_sealed_worker_result_payload(
    connection: sqlite3.Connection,
    attempt_row: sqlite3.Row,
    *,
    expected_role: str,
    terminal_payload: Any,
) -> dict[str, Any]:
    """Build the paid seal-equivalent receipt from validated terminal evidence.

    Requires the work or repair role and the complete validated paid launch
    material, delegates the terminal evidence itself to the paid terminal
    owner, and returns the sealed-worker-shaped receipt with honest synthetic
    instrumentation references: no provider identity is minted, the paid
    attempt carries no provider session, and the artifact receipt is empty.
    The common parent completion owner continues to handle role lineage.
    """
    import control_plane.executive_runtime as er

    if expected_role not in _PAID_ROLES:
        _refuse("paid sealed results require the work or repair role")
    evidence = _validated_paid_launch_evidence(
        connection, attempt_row, allow_unsealed_principal=False
    )
    if not isinstance(terminal_payload, dict):
        _refuse("paid terminal payload is not an object")
    envelope = terminal_payload.get("result_envelope")
    if type(envelope) is not dict:
        _refuse("paid terminal result envelope is invalid")
    result_evidence = terminal_payload.get("result_evidence")
    try:
        from control_plane.paid_model_terminal_evidence import (
            validate_paid_model_terminal_evidence,
        )

        validate_paid_model_terminal_evidence(
            result_evidence,
            expected_binding=evidence["expected_binding"],
            expected_process_ref=evidence["process_ref"],
            expected_launch_attestation=evidence["attestation"],
            expected_launch_identity_sha256=evidence["metadata"][
                "paid_launch_identity_sha256"
            ],
            expected_result_envelope=envelope,
            expected_grant=evidence["grant"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        _refuse(
            "paid terminal evidence failed original-owner validation: "
            f"{type(exc).__name__}"
        )
    if (
        terminal_payload.get("result_envelope_digest")
        != orchestration_digest(envelope)
        or result_evidence.get("collection_receipt", {}).get("collection", {}).get("result", {}).get("artifact_manifest") != []
        or terminal_payload.get("artifact_receipt_digest")
        != orchestration_digest([])
        or type(result_evidence) is not dict
        or terminal_payload.get("validation_receipt_digest")
        != result_evidence.get("validation_receipts_digest")
    ):
        _refuse("paid terminal receipt digests are invalid")
    job_row = connection.execute(
        "SELECT result_json FROM jobs WHERE job_id=?", (attempt_row["job_id"],)
    ).fetchone()
    if job_row is None:
        _refuse("paid result lost its Job")
    if (
        job_row["result_json"] is not None
        and er._strict_canonical_json_loads(
            str(job_row["result_json"]), name="paid Job terminal receipt"
        )
        != terminal_payload
    ):
        _refuse("paid terminal receipt differs from the stored Job result")
    role_result = envelope.get("role_result")
    if (
        type(role_result) is not dict
        or role_result.get("artifacts") not in (None, [])
    ):
        _refuse("paid sealed results declare no artifacts")
    envelope_digest = orchestration_digest(envelope)
    result_evidence_digest = orchestration_digest(result_evidence)
    return {
        "schema_version": PAID_RESULT_RECEIPT_SCHEMA,
        "job_id": str(attempt_row["job_id"]),
        "attempt_id": str(attempt_row["attempt_id"]),
        "worker_id": str(attempt_row["worker_id"]),
        "quota_class": str(attempt_row["quota_class"]),
        "orchestration_role": expected_role,
        "session_epoch_id": f"sealed-worker:{attempt_row['attempt_id']}",
        "process_generation_id": f"sealed-worker:{attempt_row['attempt_id']}",
        "turn_id": f"sealed-worker-turn:{attempt_row['attempt_id']}",
        "provider_session_id": None,
        "provider_native_turn_id": None,
        "provider_turn_artifact_digest": result_evidence_digest,
        "raw_result_observation_digest": result_evidence_digest,
        "canonical_result_byte_length": len(
            er._json_dumps(envelope).encode("utf-8")
        ),
        "candidate_event_command_id": f"sealed-worker-result:{attempt_row['attempt_id']}",
        "candidate_event_digest": result_evidence_digest,
        "result_envelope": envelope,
        "result_envelope_digest": envelope_digest,
        "role_result_digest": orchestration_digest(role_result),
        "work_admission_command_id": f"sealed-worker-launch:{attempt_row['attempt_id']}",
        "observed_attestation_digest": orchestration_digest(
            evidence["attestation"]
        ),
        "execution_principal_snapshot_digest": str(
            attempt_row["execution_principal_snapshot_digest"]
        ),
        "placement_snapshot_digest": str(
            attempt_row["placement_snapshot_digest"]
        ),
        "effective_grant_digest": str(attempt_row["effective_grant_digest"]),
        "policy_sha": er._job_coo_policy(
            connection, str(attempt_row["job_id"])
        ).policy_sha256,
    }


def validated_paid_terminal_evidence(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    seal: Mapping[str, Any],
) -> dict[str, Any]:
    """Re-validate the paid terminal history against one built paid receipt.

    Requires the exact single supervisor exit Event with exit code zero, one
    running Event and no harness, admission or seal events, and a seal whose
    launch, principal, grant, placement and policy facts are unchanged.  The
    returned terminal evidence is distinct paid DATA: no provider home, no
    provider identity and no canary projection.
    """
    import control_plane.executive_runtime as er

    if (
        not isinstance(seal, dict)
        or set(seal) != _PAID_RECEIPT_KEYS
        or seal["schema_version"] != PAID_RESULT_RECEIPT_SCHEMA
        or seal["orchestration_role"] not in _PAID_ROLES
    ):
        _refuse("paid terminal seal is not the paid result receipt")
    evidence = _validated_paid_launch_evidence(
        connection, attempt_row, allow_unsealed_principal=False
    )
    attestation = evidence["attestation"]
    principal = evidence["principal"]
    placement = evidence["placement"]
    grant = evidence["grant"]
    attestation_digest = orchestration_digest(attestation)
    attempt_id = str(attempt_row["attempt_id"])
    exit_events = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='ATTEMPT_PROCESS_EXITED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_row["attempt_id"],),
    ).fetchall()
    seal_event_count = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    harness_rows = connection.execute(
        """
        SELECT COUNT(*) FROM harness_session_epochs WHERE attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    admission_rows = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ORCHESTRATION_WORK_ADMITTED' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    running_rows = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ATTEMPT_RUNNING' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    worker_identity = attestation.get("process_identity")
    process_identity = attestation.get("process_identity")
    if (
        seal["observed_attestation_digest"] != attestation_digest
        or seal["work_admission_command_id"] != f"sealed-worker-launch:{attempt_id}"
        or seal["candidate_event_command_id"] != f"sealed-worker-result:{attempt_id}"
        or seal["session_epoch_id"] != f"sealed-worker:{attempt_id}"
        or seal["provider_session_id"] is not None
        or seal["provider_native_turn_id"] is not None
        or seal["execution_principal_snapshot_digest"]
        != attempt_row["execution_principal_snapshot_digest"]
        or seal["placement_snapshot_digest"]
        != attempt_row["placement_snapshot_digest"]
        or seal["effective_grant_digest"] != attempt_row["effective_grant_digest"]
        or seal["policy_sha"]
        != er._job_coo_policy(connection, str(attempt_row["job_id"])).policy_sha256
        or not isinstance(placement, dict)
        or placement.get("worker_id") != attempt_row["worker_id"]
        or placement.get("quota_class") != attempt_row["quota_class"]
        or not isinstance(principal, dict)
        or orchestration_digest(principal)
        != seal["execution_principal_snapshot_digest"]
        or not isinstance(grant, dict)
        or grant.get("job_id") != attempt_row["job_id"]
        or not isinstance(worker_identity, dict)
        or not isinstance(process_identity, dict)
        or process_identity.get("pid") != attempt_row["pid"]
        or process_identity.get("pgid") != attempt_row["pgid"]
        or process_identity.get("start_identity")
        != attempt_row["process_start_identity"]
        or process_identity.get("boot_id") != attempt_row["boot_id"]
        or attempt_row["provider_session_id"] is not None
        or type(attempt_row["exit_code"]) is not int
        or attempt_row["exit_code"] != 0
        or len(exit_events) != 1
        or exit_events[0]["actor"] != "supervisor"
        or exit_events[0]["aggregate_type"] != "attempt"
        or exit_events[0]["aggregate_id"] != attempt_row["attempt_id"]
        or exit_events[0]["job_id"] != attempt_row["job_id"]
        or exit_events[0]["attempt_id"] != attempt_row["attempt_id"]
        or exit_events[0]["worker_id"] != attempt_row["worker_id"]
        or exit_events[0]["quota_class"] != attempt_row["quota_class"]
        or er._strict_canonical_json_loads(
            str(exit_events[0]["payload_json"]), name="paid exit receipt"
        )
        != {"exit_code": 0}
        or int(seal_event_count) != 0
        or int(harness_rows) != 0
        or int(admission_rows) != 0
        or int(running_rows) != 1
    ):
        _refuse("paid terminal evidence is invalid")
    return {
        "schema_version": PAID_TERMINAL_EVIDENCE_SCHEMA,
        "attempt_id": attempt_id,
        "launch_attestation_digest": str(attestation_digest),
        "process_exit_event_id": int(exit_events[0]["event_id"]),
    }
