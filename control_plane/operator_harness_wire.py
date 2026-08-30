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
from collections.abc import Mapping
from typing import Any, Callable, TypeVar

from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.operator_harness_contract import (
    AdapterFailureClass,
    AttentionTurnObservation,
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
    WorkspaceIdentity,
)


class OperatorHarnessWireError(ValueError):
    """A broker value is outside the closed Operator Harness wire."""


T = TypeVar("T")


def to_wire(value: Any) -> Any:
    """Return recursively JSON-compatible data without changing semantics."""

    if dataclasses.is_dataclass(value):
        return {
            field.name: to_wire(getattr(value, field.name))
            for field in dataclasses.fields(value)
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
    return _construct(CapabilityIdentity, value, name="capability identity")


def observed_capability_identity(value: Any) -> ObservedCapabilityIdentity:
    return _construct(
        ObservedCapabilityIdentity, value, name="observed capability identity"
    )


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
    return _construct(TurnStartObservation, value, name="turn start observation")


def attention_turn_observation(value: Any) -> AttentionTurnObservation:
    return _construct(
        AttentionTurnObservation, value, name="attention turn observation"
    )


def reconcile_observation(value: Any) -> ReconcileObservation:
    raw = _closed(value, ReconcileObservation, name="reconcile observation")
    failure = raw["recommended_failure_class"]
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


def _wire_text(value: Any) -> str:
    if not isinstance(value, str):
        raise OperatorHarnessWireError("wire text must be a string")
    return value


__all__ = [
    "OperatorHarnessWireError",
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
    "session_epoch_ref",
    "session_start_observation",
    "to_wire",
    "turn_ref",
    "turn_start_observation",
    "workspace_identity",
]
