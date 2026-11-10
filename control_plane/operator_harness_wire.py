"""Closed JSON wire codecs for the existing Operator Harness value objects.

The Executive worker broker is a transport boundary, not a source of lifecycle
authority.  These codecs therefore do only two things: project the frozen OHF
dataclasses to JSON data and reconstruct them with exact-key checks on the
control side.  They allocate no identities, read no credentials, and persist
nothing.
"""
from __future__ import annotations

import dataclasses
import enum
import re
from collections.abc import Mapping
from typing import Any, Callable, TypeVar

from control_plane.codex_operator_adapter import (
    CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST,
    CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION,
    CONSUMPTION_EVIDENCE_SCOPE,
    CONSUMPTION_EVIDENCE_SHAPE,
    RetainedPlainInputEvidence,
)
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.operator_harness_contract import (
    AdapterFailureClass,
    AttentionTurnObservation,
    AttentionCompanyReadProjection,
    AuthIdentityConfidence,
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityIdentity,
    CapabilityManifest,
    EventCursor,
    LaunchComparison,
    LaunchDecision,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedCapabilityIdentity,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    WorkerLocalWakeAckProjection,
    WorkspaceIdentity,
)


class OperatorHarnessWireError(ValueError):
    """A broker value is outside the closed Operator Harness wire."""


# Selects the retained plain-input digest observation on the existing
# ohf-begin-turn/ohf-collect-turn path only.  It is never a request field, it
# grants no ACK authority, and the parent uses the same prefix for trusted
# capsule delivery.
CONTINUATION_OPERATION_PREFIX = "ohf-op:continuation:"


T = TypeVar("T")


def to_wire(value: Any) -> Any:
    """Return recursively JSON-compatible data without changing semantics."""

    if dataclasses.is_dataclass(value):
        return {
            field.name: to_wire(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if not (type(value) is TurnStartObservation
                    and field.name == "planner_custody" and value.planner_custody is None)
        }
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): to_wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_wire(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise OperatorHarnessWireError(
        f"unsupported Operator Harness wire value: {type(value).__name__}"
    )


def _closed(value: Any, cls: type[Any], *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatorHarnessWireError(f"{name} must be an object")
    expected = {field.name for field in dataclasses.fields(cls)}
    actual = set(value)
    if actual != expected:
        raise OperatorHarnessWireError(
            f"{name} fields drifted; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )
    return dict(value)


def _construct(cls: type[T], value: Any, *, name: str, **updates: Any) -> T:
    raw = _closed(value, cls, name=name)
    raw.update(updates)
    try:
        return cls(**raw)
    except (TypeError, ValueError) as exc:
        raise OperatorHarnessWireError(f"{name} is invalid") from exc


def _enum(kind: type[T], value: Any, *, name: str) -> T:
    try:
        return kind(value)
    except (TypeError, ValueError) as exc:
        raise OperatorHarnessWireError(f"{name} is invalid") from exc


def _tuple(value: Any, loader: Callable[[Any], T], *, name: str) -> tuple[T, ...]:
    if not isinstance(value, list):
        raise OperatorHarnessWireError(f"{name} must be an array")
    return tuple(loader(item) for item in value)


def workspace_identity(value: Any) -> WorkspaceIdentity:
    return _construct(WorkspaceIdentity, value, name="workspace identity")


def capability_identity(value: Any) -> CapabilityIdentity:
    identity = _construct(CapabilityIdentity, value, name="capability identity")
    digest = identity.resource_contract_digest
    if identity.kind == "resource":
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise OperatorHarnessWireError(
                "resource contract digest must be exact lowercase SHA-256"
            )
    elif digest is not None:
        raise OperatorHarnessWireError(
            "resource contract digest is valid only for resource capabilities"
        )
    return identity


def observed_capability_identity(value: Any) -> ObservedCapabilityIdentity:
    identity = _construct(
        ObservedCapabilityIdentity, value, name="observed capability identity"
    )
    digest = identity.resource_contract_digest
    if identity.kind == "resource":
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise OperatorHarnessWireError(
                "resource contract digest must be exact lowercase SHA-256"
            )
    elif digest is not None:
        raise OperatorHarnessWireError(
            "resource contract digest is valid only for resource capabilities"
        )
    return identity


def capability_manifest(value: Any) -> CapabilityManifest:
    raw = _closed(value, CapabilityManifest, name="capability manifest")
    return _construct(
        CapabilityManifest,
        raw,
        name="capability manifest",
        required=_tuple(
            raw["required"], capability_identity, name="required capabilities"
        ),
        allowed_ambient=_tuple(
            raw["allowed_ambient"],
            capability_identity,
            name="ambient capabilities",
        ),
        forbidden=_tuple(raw["forbidden"], _wire_text, name="forbidden capabilities"),
    )


def auth_realm_fact(value: Any) -> AuthRealmFact:
    raw = _closed(value, AuthRealmFact, name="auth realm fact")
    return _construct(
        AuthRealmFact,
        raw,
        name="auth realm fact",
        identity_confidence=_enum(
            AuthIdentityConfidence,
            raw["identity_confidence"],
            name="auth identity confidence",
        ),
    )


def requested_execution_profile(value: Any) -> RequestedExecutionProfile:
    raw = _closed(value, RequestedExecutionProfile, name="requested profile")
    return _construct(
        RequestedExecutionProfile,
        raw,
        name="requested profile",
        workspace=workspace_identity(raw["workspace"]),
        capabilities=capability_manifest(raw["capabilities"]),
        native_helper_policy=_enum(
            NativeHelperPolicy,
            raw["native_helper_policy"],
            name="native helper policy",
        ),
        auth_realm_requirement=_enum(
            AuthRealmRequirement,
            raw["auth_realm_requirement"],
            name="auth realm requirement",
        ),
        allowed_write_paths=_tuple(
            raw["allowed_write_paths"], _wire_text, name="allowed write paths"
        ),
    )


def observed_harness_attestation(value: Any) -> ObservedHarnessAttestation:
    raw = _closed(value, ObservedHarnessAttestation, name="observed attestation")
    return _construct(
        ObservedHarnessAttestation,
        raw,
        name="observed attestation",
        capabilities=_tuple(
            raw["capabilities"],
            observed_capability_identity,
            name="observed capabilities",
        ),
        effective_skills=_tuple(
            raw["effective_skills"], _wire_text, name="effective skills"
        ),
        effective_mcp=_tuple(
            raw["effective_mcp"], _wire_text, name="effective MCP"
        ),
        effective_plugins_or_apps=_tuple(
            raw["effective_plugins_or_apps"],
            _wire_text,
            name="effective plugins",
        ),
        auth=auth_realm_fact(raw["auth"]),
        workspace=(
            None if raw["workspace"] is None else workspace_identity(raw["workspace"])
        ),
        supports_subagent_capability_ceiling=_enum(
            ObservedTriState,
            raw["supports_subagent_capability_ceiling"],
            name="subagent capability ceiling",
        ),
        unknown_fields=_tuple(
            raw["unknown_fields"], _wire_text, name="unknown attestation fields"
        ),
    )


def session_epoch_ref(value: Any) -> SessionEpochRef:
    return _construct(SessionEpochRef, value, name="session epoch ref")


def process_generation_ref(value: Any) -> ProcessGenerationRef:
    return _construct(ProcessGenerationRef, value, name="process generation ref")


def process_identity_observation(value: Any) -> ProcessIdentityObservation:
    return _construct(
        ProcessIdentityObservation, value, name="process identity observation"
    )


def operation_id(value: Any) -> OperationId:
    return _construct(OperationId, value, name="operation id")


def turn_ref(value: Any) -> TurnRef:
    return _construct(TurnRef, value, name="turn ref")


def event_cursor(value: Any) -> EventCursor:
    return _construct(EventCursor, value, name="event cursor")


def normalized_event(value: Any) -> NormalizedEvent:
    raw = _closed(value, NormalizedEvent, name="normalized event")
    payload = raw["payload_redacted"]
    if not isinstance(payload, Mapping):
        raise OperatorHarnessWireError("normalized event payload must be an object")
    return _construct(
        NormalizedEvent,
        raw,
        name="normalized event",
        payload_redacted=dict(payload),
    )


def candidate_result(value: Any) -> CandidateResult:
    return _construct(CandidateResult, value, name="candidate result")


def session_start_observation(value: Any) -> SessionStartObservation:
    raw = _closed(value, SessionStartObservation, name="session start observation")
    return _construct(
        SessionStartObservation,
        raw,
        name="session start observation",
        process=process_identity_observation(raw["process"]),
        initialization_notes=_tuple(
            raw["initialization_notes"], _wire_text, name="initialization notes"
        ),
    )


def provider_session_handoff(value: Any) -> ProviderSessionHandoff:
    return _construct(
        ProviderSessionHandoff, value, name="provider session handoff"
    )


def turn_start_observation(value: Any) -> TurnStartObservation:
    if not isinstance(value, Mapping) or set(value) not in (
        {"provider_native_turn_id", "acknowledged"},
        {"provider_native_turn_id", "acknowledged", "planner_custody"},
    ):
        raise OperatorHarnessWireError("turn start observation fields are invalid")
    raw = dict(value)
    if "planner_custody" in raw:
        if (type(raw["provider_native_turn_id"]) is not str
                or not raw["provider_native_turn_id"].strip()):
            raise OperatorHarnessWireError("planner custody requires exact native turn identity")
        raw["planner_custody"] = planner_turn_custody(raw["planner_custody"],
            provider_native_turn_id=raw["provider_native_turn_id"])
        if raw["acknowledged"] is not True:
            raise OperatorHarnessWireError("planner custody requires native acknowledgment")
    return TurnStartObservation(**raw)


def planner_turn_custody(value: Any, *, producer=None, operation_id=None,
                         turn=None, provider_session_id=None, provider_native_turn_id=None):
    """Decode exact request/ACK evidence; this never asserts a native schema echo.

    Acknowledgment alone does not validate the returned plan or admit children.
    Runtime still owns the TX-5, result seal and CooCycle admission transactions.
    """
    from control_plane.claude_operator_helper_protocol import native_plan_contract
    from control_plane.operator_materialization_receipt import (
        canonical_json_bytes, planner_producer_selection,
    )
    import json
    fields = {"schema_version", "evidence_kind", "operation_id", "job_id", "attempt_id",
              "session_epoch_id", "process_generation_id", "turn_id", "provider_session_id",
              "provider_native_turn_id", "planner_producer_binding_digest",
              "native_result_contract", "native_request_digest"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OperatorHarnessWireError("planner turn custody fields are invalid")
    raw = dict(value)
    if (raw["schema_version"] != "mastermind.operator_planner_turn_custody/v1"
            or raw["evidence_kind"] != "NATIVE_REQUEST_ACK"):
        raise OperatorHarnessWireError("planner turn custody schema is invalid")
    for key in fields - {"native_result_contract"}:
        if (type(raw[key]) is not str or not 1 <= len(raw[key]) <= 256
                or raw[key] != raw[key].strip()):
            raise OperatorHarnessWireError("planner turn custody identity is invalid")
    for key in ("native_request_digest", "planner_producer_binding_digest"):
        if re.fullmatch(r"[0-9a-f]{64}", raw[key]) is None:
            raise OperatorHarnessWireError("planner turn custody digest is invalid")
    try:
        contract = native_plan_contract(raw["native_result_contract"]["name"])
        if raw["native_result_contract"] != contract:
            raise ValueError("different contract")
        if producer is not None:
            selected = planner_producer_selection(producer, job_id=raw["job_id"], attempt_id=raw["attempt_id"])
            if (selected["planner_producer_binding_digest"] != raw["planner_producer_binding_digest"]
                    or selected["planner_producer_binding"]["native_result_contract"] != contract):
                raise ValueError("different producer")
    except (KeyError, TypeError, ValueError) as exc:
        raise OperatorHarnessWireError("planner turn custody contract differs") from exc
    if operation_id is not None and raw["operation_id"] != operation_id.command_id:
        raise OperatorHarnessWireError("planner turn custody operation differs")
    if turn is not None and any(raw[key] != getattr(turn, key) for key in (
            "attempt_id", "session_epoch_id", "process_generation_id", "turn_id")):
        raise OperatorHarnessWireError("planner turn custody target differs")
    if ((provider_session_id is not None and raw["provider_session_id"] != provider_session_id)
            or (provider_native_turn_id is not None and raw["provider_native_turn_id"] != provider_native_turn_id)):
        raise OperatorHarnessWireError("planner turn custody native identity differs")
    return json.loads(canonical_json_bytes(raw))


def build_planner_turn_custody(*, producer, operation_id, turn, provider_session_id,
                               provider_native_turn_id, native_request):
    from control_plane.claude_operator_helper_protocol import native_plan_schema
    from control_plane.operator_materialization_receipt import planner_producer_selection
    from control_plane.executive_orchestration_result import canonical_digest
    selected = planner_producer_selection(producer, attempt_id=turn.attempt_id)
    if (not isinstance(native_request, Mapping)
            or native_request.get("threadId") != provider_session_id
            or native_request.get("outputSchema") != native_plan_schema(
                selected["planner_producer_binding"]["native_result_contract"]["name"])):
        raise OperatorHarnessWireError("native planner request differs from selected schema")
    return planner_turn_custody({
        "schema_version": "mastermind.operator_planner_turn_custody/v1",
        "evidence_kind": "NATIVE_REQUEST_ACK", "operation_id": operation_id.command_id,
        "job_id": selected["job_id"], **to_wire(turn),
        "provider_session_id": provider_session_id, "provider_native_turn_id": provider_native_turn_id,
        "planner_producer_binding_digest": selected["planner_producer_binding_digest"],
        "native_result_contract": selected["planner_producer_binding"]["native_result_contract"],
        "native_request_digest": canonical_digest(native_request),
    }, producer=selected, operation_id=operation_id, turn=turn,
        provider_session_id=provider_session_id, provider_native_turn_id=provider_native_turn_id)


def attention_turn_observation(value: Any) -> AttentionTurnObservation:
    raw = _closed(value, AttentionTurnObservation, name="attention turn observation")
    projection = raw["wake_ack_projection"]
    nested = None
    if projection is not None:
        nested_raw = _closed(
            projection,
            WorkerLocalWakeAckProjection,
            name="worker-local Wake ACK projection",
        )
        nested = _construct(
            WorkerLocalWakeAckProjection,
            nested_raw,
            name="worker-local Wake ACK projection",
            obligation_ids=_tuple(
                nested_raw["obligation_ids"],
                _wire_text,
                name="worker-local Wake ACK obligation ids",
            ),
        )
    return _construct(
        AttentionTurnObservation,
        raw,
        name="attention turn observation",
        wake_ack_projection=nested,
        company_read_projection=(
            None if raw["company_read_projection"] is None else _construct(
                AttentionCompanyReadProjection, raw["company_read_projection"],
                name="attention Company read projection",
            )
        ),
    )


def reconcile_observation(value: Any) -> ReconcileObservation:
    raw = _closed(value, ReconcileObservation, name="reconcile observation")
    failure = raw["recommended_failure_class"]
    late_raw = raw["late_attention_observation"]
    return _construct(
        ReconcileObservation,
        raw,
        name="reconcile observation",
        process_liveness=_enum(
            ProcessLiveness, raw["process_liveness"], name="process liveness"
        ),
        observed_process=process_identity_observation(raw["observed_process"]),
        provider_writer_state=_enum(
            ProviderWriterState,
            raw["provider_writer_state"],
            name="provider writer state",
        ),
        recommended_failure_class=(
            None
            if failure is None
            else _enum(AdapterFailureClass, failure, name="adapter failure class")
        ),
        late_attention_observation=(
            None
            if late_raw is None
            else attention_turn_observation(late_raw)
        ),
    )


def launch_comparison(value: Any) -> LaunchComparison:
    raw = _closed(value, LaunchComparison, name="launch comparison")
    return _construct(
        LaunchComparison,
        raw,
        name="launch comparison",
        requested=requested_execution_profile(raw["requested"]),
        observed=observed_harness_attestation(raw["observed"]),
        decision=_enum(LaunchDecision, raw["decision"], name="launch decision"),
        mismatch_reasons=_tuple(
            raw["mismatch_reasons"], _wire_text, name="launch mismatch reasons"
        ),
        missing_required=_tuple(
            raw["missing_required"], _wire_text, name="missing required capabilities"
        ),
        forbidden_present=_tuple(
            raw["forbidden_present"], _wire_text, name="forbidden capabilities"
        ),
        unclassified=_tuple(
            raw["unclassified"], _wire_text, name="unclassified capabilities"
        ),
        unknown_required_observations=_tuple(
            raw["unknown_required_observations"],
            _wire_text,
            name="unknown required observations",
        ),
    )


def profile_validation(value: Any) -> ProfileValidation:
    raw = _closed(value, ProfileValidation, name="profile validation")
    return _construct(
        ProfileValidation,
        raw,
        name="profile validation",
        requested=requested_execution_profile(raw["requested"]),
        reasons=_tuple(raw["reasons"], _wire_text, name="validation reasons"),
    )


def raw_role_result_observation(value: Any) -> RawRoleResultObservation:
    return _construct(
        RawRoleResultObservation, value, name="raw role result observation"
    )


def process_credential_observation(value: Any) -> OSProcessCredentialObservation:
    return _construct(
        OSProcessCredentialObservation, value, name="process credential observation"
    )


def provider_home_observation(value: Any) -> ProviderHomeIdentityObservation:
    return _construct(
        ProviderHomeIdentityObservation, value, name="provider home observation"
    )


def retained_plain_input_evidence(value: Any) -> RetainedPlainInputEvidence:
    """Reconstruct the closed digest-only retained plain-input evidence.

    The frozen value object is owned by the byte-identical accepted extractor,
    so this codec reconstructs exactly that class and nothing else.  The wire
    grammar is closed and digest-only: no acceptance boolean, no retained or
    expected text, no caller build attestation, and no ACK authority field can
    be expressed, because every other key is refused.  A canonical SHA-256
    input digest, a positive byte length, and the accepted extractor's own
    provenance constants are required; anything else is outside the wire.
    """

    evidence = _construct(
        RetainedPlainInputEvidence, value, name="retained plain input evidence"
    )
    if any(
        not isinstance(item, str) or not item
        for item in (
            evidence.attempt_id,
            evidence.session_epoch_id,
            evidence.process_generation_id,
            evidence.turn_id,
            evidence.provider_session_id,
            evidence.provider_native_turn_id,
            evidence.harness_version,
        )
    ):
        raise OperatorHarnessWireError(
            "retained plain input evidence identities must be nonempty strings"
        )
    if (
        not isinstance(evidence.retained_input_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", evidence.retained_input_digest) is None
    ):
        raise OperatorHarnessWireError(
            "retained input digest must be exact lowercase SHA-256"
        )
    length = evidence.retained_input_byte_length
    if type(length) is not int or length <= 0:
        raise OperatorHarnessWireError(
            "retained input byte length must be a positive integer count"
        )
    if evidence.harness_version != CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION:
        raise OperatorHarnessWireError(
            "retained input harness version pin is unknown"
        )
    if evidence.harness_binary_digest != CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST:
        raise OperatorHarnessWireError(
            "retained input harness binary pin is unknown"
        )
    if evidence.input_shape != CONSUMPTION_EVIDENCE_SHAPE:
        raise OperatorHarnessWireError("retained input shape constant is unknown")
    if evidence.scope != CONSUMPTION_EVIDENCE_SCOPE:
        raise OperatorHarnessWireError("retained input scope constant is unknown")
    return evidence


def _wire_text(value: Any) -> str:
    if not isinstance(value, str):
        raise OperatorHarnessWireError("wire text must be a string")
    return value


__all__ = [
    "CONTINUATION_OPERATION_PREFIX",
    "OperatorHarnessWireError",
    "RetainedPlainInputEvidence",
    "attention_turn_observation",
    "candidate_result",
    "event_cursor",
    "launch_comparison",
    "normalized_event",
    "observed_harness_attestation",
    "operation_id",
    "process_credential_observation",
    "process_generation_ref",
    "process_identity_observation",
    "profile_validation",
    "provider_home_observation",
    "provider_session_handoff",
    "raw_role_result_observation",
    "reconcile_observation",
    "requested_execution_profile",
    "retained_plain_input_evidence",
    "session_epoch_ref",
    "session_start_observation",
    "to_wire",
    "turn_ref",
    "turn_start_observation",
    "workspace_identity",
]
