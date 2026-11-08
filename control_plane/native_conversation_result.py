"""Native conversation evidence alongside the existing role-result contract.

The original Runtime seals/accepts evidence. This closed observation carries no
Job completion, current authority, account grant or copied transcript. Its digest
covers the native claim and flushed terminal facts actually observed by ACP.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Protocol, runtime_checkable

from control_plane.executive_orchestration_result import RESULT_SCHEMA
from control_plane.operator_harness_contract import (
    OperationId, ProcessGenerationRef, RequestedExecutionProfile, TurnRef, TurnStartObservation,
    HarnessAdapterCapabilities, OPERATOR_HARNESS_INTERFACE_VERSION,
)
from control_plane.native_conversation_protocol import (
    NativeClaim, NativeProtocolError, NativeResult, NativeTerminal, native_id,
)

NATIVE_CONVERSATION_RESULT_SCHEMA = "mastermind.dsh_native_conversation_result/v1"
ROLE_RESULT_CONTRACT = RESULT_SCHEMA
DSH_NATIVE_RESULT_CONTRACT = "mastermind.dsh_native_conversation/v1"
DSH_NATIVE_HARNESS_KIND = "dsh-native-web-acp"


def native_operator_capabilities(*, interface_version=OPERATOR_HARNESS_INTERFACE_VERSION):
    """Static original adapter facts; never a process or admission factory."""
    return HarnessAdapterCapabilities(
        interface_version,
        ("describe_capabilities", "validate_requested_profile", "start_session", "begin_turn",
         "read_events", "interrupt_turn", "collect_candidate_result", "graceful_stop", "cancel", "reconcile"),
        ("resume_session",), True, False, False, False, False, False, False, True,
    )


def result_contract_for_profile(requested: RequestedExecutionProfile) -> str:
    """Codec selection from an already validated, sealed profile; no admission."""
    if not isinstance(requested, RequestedExecutionProfile):
        raise NativeConversationResultError("sealed requested profile required")
    if requested.harness_kind == DSH_NATIVE_HARNESS_KIND:
        if requested.provider != "acp":
            raise NativeConversationResultError("native conversation provider tuple differs")
        return DSH_NATIVE_RESULT_CONTRACT
    return ROLE_RESULT_CONTRACT


class NativeConversationResultError(ValueError):
    """The closed native observation is absent, inconsistent or substituted."""


NATIVE_CONVERSATION_BEGIN_SCHEMA = "mastermind.dsh_native_conversation_begin/v1"
NATIVE_CONVERSATION_BEGIN_STATUS_SCHEMA = "mastermind.dsh_native_begin_status/v1"


@dataclass(frozen=True)
class NativeConversationBeginObservation:
    """Original accepted claim and source seals; never a new dispatch grant."""
    turn: TurnRef
    generation: ProcessGenerationRef
    native_claim: NativeClaim
    requested_profile_digest: str
    observed_attestation_digest: str
    schema_version: str = field(default=NATIVE_CONVERSATION_BEGIN_SCHEMA, init=False)

    def __post_init__(self):
        if (type(self.turn) is not TurnRef or type(self.generation) is not ProcessGenerationRef
                or type(self.native_claim) is not NativeClaim
                or self.turn.session_epoch_id != self.generation.session_epoch_id
                or self.turn.process_generation_id != self.generation.process_generation_id
                or type(self.generation.generation_number) is not int
                or not 1 <= self.generation.generation_number <= 2**53-1):
            raise NativeConversationResultError("original native begin identities required")
        try:
            for value in (*asdict(self.turn).values(), self.generation.worker_id):
                native_id(value)
            NativeClaim.parse(self.native_claim.to_wire())
        except (NativeProtocolError, TypeError) as exc:
            raise NativeConversationResultError("native begin identity is invalid") from exc
        for value in (self.requested_profile_digest, self.observed_attestation_digest):
            if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise NativeConversationResultError("native begin source seal is invalid")

    @property
    def start(self) -> TurnStartObservation:
        return TurnStartObservation(str(self.native_claim.native_turn), True)

    def require_origin(self, operation_id, turn, generation, provider_session_id=None):
        if (type(operation_id) is not OperationId or self.native_claim.operation_id != operation_id.command_id
                or self.turn != turn or self.generation != generation
                or (provider_session_id is not None and self.native_claim.session_id != provider_session_id)):
            raise NativeConversationResultError("native begin belongs to another original operation")

    def to_wire(self):
        return {"schema_version": self.schema_version, "turn": asdict(self.turn),
                "generation": asdict(self.generation), "native_claim": self.native_claim.to_wire(),
                "requested_profile_digest": self.requested_profile_digest,
                "observed_attestation_digest": self.observed_attestation_digest}

    @classmethod
    def from_wire(cls, value):
        if (type(value) is not dict or set(value) != {
                "schema_version", "turn", "generation", "native_claim",
                "requested_profile_digest", "observed_attestation_digest"}
                or value["schema_version"] != NATIVE_CONVERSATION_BEGIN_SCHEMA):
            raise NativeConversationResultError("closed native begin observation required")
        from control_plane.operator_harness_wire import (
            OperatorHarnessWireError, process_generation_ref, turn_ref,
        )
        try:
            return cls(turn_ref(value["turn"]), process_generation_ref(value["generation"]),
                       NativeClaim.parse(value["native_claim"]), value["requested_profile_digest"],
                       value["observed_attestation_digest"])
        except (OperatorHarnessWireError, NativeProtocolError, TypeError) as exc:
            raise NativeConversationResultError("native begin observation is invalid") from exc


@dataclass(frozen=True)
class NativeConversationResultObservation:
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    turn_id: str
    provider_session_id: str
    provider_native_turn_id: str
    native_claim: NativeClaim
    native_terminal: NativeTerminal
    stop_reason: str
    provider_turn_artifact_digest: str
    schema_version: str = field(default=NATIVE_CONVERSATION_RESULT_SCHEMA, init=False)

    def __post_init__(self) -> None:
        try:
            for value in (self.attempt_id, self.session_epoch_id, self.process_generation_id,
                          self.turn_id, self.provider_session_id):
                native_id(value)
            if not isinstance(self.native_claim, NativeClaim) or not isinstance(self.native_terminal, NativeTerminal):
                raise NativeConversationResultError("typed native claim and terminal required")
            result = NativeResult(self.stop_reason, self.native_terminal)
            if (self.native_terminal.claim != self.native_claim
                    or self.native_claim.session_id != self.provider_session_id
                    or self.provider_native_turn_id != str(self.native_claim.native_turn)
                    or self.provider_turn_artifact_digest != result.artifact_digest):
                raise NativeConversationResultError("native observation identity or digest differs")
        except (NativeProtocolError, TypeError) as exc:
            raise NativeConversationResultError("native observation is invalid") from exc

    @classmethod
    def from_native(cls, turn: TurnRef, provider_session_id: str, result: NativeResult):
        if not isinstance(turn, TurnRef) or not isinstance(result, NativeResult) or result.terminal.claim is None:
            raise NativeConversationResultError("acknowledged original native result required")
        claim = result.terminal.claim
        return cls(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id, turn.turn_id,
                   provider_session_id, str(claim.native_turn), claim, result.terminal,
                   result.stop_reason, result.artifact_digest)

    def require_turn(self, turn: TurnRef) -> None:
        if not isinstance(turn, TurnRef) or (self.attempt_id, self.session_epoch_id, self.process_generation_id, self.turn_id) != (
                turn.attempt_id, turn.session_epoch_id, turn.process_generation_id, turn.turn_id):
            raise NativeConversationResultError("native observation belongs to another original turn")

    def to_wire(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "attempt_id": self.attempt_id,
            "session_epoch_id": self.session_epoch_id, "process_generation_id": self.process_generation_id,
            "turn_id": self.turn_id, "provider_session_id": self.provider_session_id,
            "provider_native_turn_id": self.provider_native_turn_id, "native_claim": self.native_claim.to_wire(),
            "native_terminal": self.native_terminal.to_wire(), "stop_reason": self.stop_reason,
            "provider_turn_artifact_digest": self.provider_turn_artifact_digest,
        }

    @classmethod
    def from_wire(cls, value: Any):
        fields = {"schema_version", "attempt_id", "session_epoch_id", "process_generation_id", "turn_id",
                  "provider_session_id", "provider_native_turn_id", "native_claim", "native_terminal",
                  "stop_reason", "provider_turn_artifact_digest"}
        if type(value) is not dict or set(value) != fields or value["schema_version"] != NATIVE_CONVERSATION_RESULT_SCHEMA:
            raise NativeConversationResultError("closed native observation required")
        try:
            return cls(value["attempt_id"], value["session_epoch_id"], value["process_generation_id"], value["turn_id"],
                       value["provider_session_id"], value["provider_native_turn_id"], NativeClaim.parse(value["native_claim"]),
                       NativeTerminal.parse(value["native_terminal"]), value["stop_reason"], value["provider_turn_artifact_digest"])
        except (NativeProtocolError, TypeError) as exc:
            raise NativeConversationResultError("native observation is invalid") from exc


@runtime_checkable
class NativeConversationResultAdapter(Protocol):
    def observe_native_conversation_result(self, turn: TurnRef) -> NativeConversationResultObservation: ...


NATIVE_CONVERSATION_REF_SCHEMA = "mastermind.dsh_native_conversation_result_ref/v1"
NATIVE_CONVERSATION_SEAL_SCHEMA = "mastermind.dsh_native_conversation_result_seal/v1"
NATIVE_CONVERSATION_RECOVERED_SEAL_SCHEMA = "mastermind.dsh_native_conversation_result_seal/v2"
NATIVE_CONVERSATION_TERMINAL_SCHEMA = "mastermind.dsh_native_conversation_terminal/v1"


@dataclass(frozen=True)
class NativeConversationResultRef:
    """Exact original Runtime Event reference, never current authority."""
    command_id: str
    event_id: int
    seal_digest: str
    observation_digest: str
    schema_version: str = field(default=NATIVE_CONVERSATION_REF_SCHEMA, init=False)

    def __post_init__(self):
        prefix = "ohf-native-result:"
        if (type(self.command_id) is not str or not self.command_id.startswith(prefix)
                or type(self.event_id) is not int or not 1 <= self.event_id <= 2**53-1):
            raise NativeConversationResultError("native result Event reference is malformed")
        try:
            native_id(self.command_id)
            native_id(self.command_id[len(prefix):])
        except NativeProtocolError as exc:
            raise NativeConversationResultError("native result command is malformed") from exc
        for value in (self.seal_digest, self.observation_digest):
            if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise NativeConversationResultError("native result reference digest is malformed")

    def to_wire(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "command_id": self.command_id,
                "event_id": self.event_id, "seal_digest": self.seal_digest,
                "observation_digest": self.observation_digest}

    @classmethod
    def from_wire(cls, value: Any):
        if (type(value) is not dict or set(value) != {
                "schema_version", "command_id", "event_id", "seal_digest", "observation_digest"}
                or value["schema_version"] != NATIVE_CONVERSATION_REF_SCHEMA):
            raise NativeConversationResultError("closed native result reference required")
        return cls(value["command_id"], value["event_id"], value["seal_digest"], value["observation_digest"])
