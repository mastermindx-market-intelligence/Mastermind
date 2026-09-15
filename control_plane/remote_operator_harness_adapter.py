"""Provider-neutral control-side Operator Harness proxy.

The Executive side targets one already-claimed worker realm and supplies its
reviewed capability profile. This proxy never selects a provider, account,
harness implementation, fallback realm, lifecycle owner, or credential.
"""
from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from typing import Any, Callable

from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.executive_worker_broker import (
    BrokerProtocolError,
    WorkerBrokerClient,
)
from control_plane.operator_harness_contract import (
    OPERATOR_HARNESS_INTERFACE_VERSION,
    AttentionTurnObservation,
    CandidateResult,
    EventCursor,
    HarnessAdapterCapabilities,
    LaunchComparison,
    NormalizedEvent,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProfileValidation,
    ProviderSessionHandoff,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    StageConfigReceipt,
    TurnRef,
    TurnStartObservation,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError,
    attention_turn_observation,
    candidate_result,
    event_cursor,
    normalized_event,
    observed_harness_attestation,
    process_credential_observation,
    profile_validation,
    provider_home_observation,
    raw_role_result_observation,
    reconcile_observation,
    session_start_observation,
    to_wire,
    turn_start_observation,
)
from control_plane.operator_materialization_receipt import (
    OperatorMaterializationReceiptError,
    OperatorMaterializationStatusObservation,
    operator_materialization_status,
    requested_profile_digest,
    validate_materialization_request,
)
from control_plane.worker_browser_b1 import (
    BrowserReviewError,
    BrowserReviewReceipt,
    browser_review_receipt,
)


TurnInputLoader = Callable[[TurnRef], str]


_REQUIRED_REMOTE_OPERATIONS = (
    "start_session",
    "begin_turn",
    "read_events",
    "interrupt_turn",
    "collect_candidate_result",
    "graceful_stop",
    "cancel",
    "reconcile",
)
_OPTIONAL_REMOTE_OPERATIONS = frozenset({"resume_session"})


def _validate_remote_capabilities(capabilities: HarnessAdapterCapabilities) -> None:
    if not isinstance(capabilities, HarnessAdapterCapabilities):
        raise TypeError("capabilities must be HarnessAdapterCapabilities")
    if capabilities.interface_version != OPERATOR_HARNESS_INTERFACE_VERSION:
        raise BrokerProtocolError("remote operator interface version is unsupported")
    if (
        tuple(capabilities.supported_required_operations)
        != _REQUIRED_REMOTE_OPERATIONS
    ):
        raise BrokerProtocolError("remote operator required-operation profile is unsupported")
    optional = tuple(capabilities.supported_optional_operations)
    if optional != ("resume_session",):
        raise BrokerProtocolError("remote operator optional-operation profile is unsupported")
    if capabilities.supports_native_resume is not True:
        raise BrokerProtocolError("remote operator resume capability disagrees with operation profile")
    if any((
        capabilities.supports_native_fork,
        capabilities.supports_steering,
        capabilities.supports_approval_response,
        capabilities.supports_checkpoint,
        capabilities.supports_config_staging,
    )):
        raise BrokerProtocolError("remote operator advertises an unsupported optional capability")
    if not capabilities.supports_structured_events:
        raise BrokerProtocolError("remote operator requires structured event support")


class RemoteOperatorHarnessAdapter:
    """Provider-neutral typed proxy over one already-claimed worker realm."""

    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION

    def __init__(
        self,
        client: WorkerBrokerClient,
        *,
        turn_input_loader: TurnInputLoader,
        capabilities: HarnessAdapterCapabilities,
    ) -> None:
        _validate_remote_capabilities(capabilities)
        self.client = client
        self.turn_input_loader = turn_input_loader
        self._capabilities = capabilities
        self._start_receipts: dict[str, dict[str, Any]] = {}
        self._turn_results: dict[str, dict[str, Any]] = {}
        self._artifact_receipts: dict[str, BrowserReviewReceipt | None] = {}

    @staticmethod
    def _mapping(value: Any, *, name: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise BrokerProtocolError(f"remote {name} must be an object")
        return dict(value)

    def describe_capabilities(self) -> HarnessAdapterCapabilities:
        return self._capabilities

    def validate_requested_profile(
        self, requested: RequestedExecutionProfile
    ) -> ProfileValidation:
        result = self.client.request_sync(
            "ohf-validate", {"requested": to_wire(requested)}
        )
        try:
            return profile_validation(result.get("validation"))
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError("remote OHF profile validation is invalid") from exc

    def _start(
        self,
        *,
        operation_name: str,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        provider_session: ProviderSessionHandoff | None = None,
    ) -> SessionStartObservation:
        payload = {
            "operation_id": to_wire(operation_id),
            "requested": to_wire(requested),
            "epoch": to_wire(epoch),
            "generation": to_wire(generation),
        }
        if provider_session is not None:
            payload["provider_session"] = to_wire(provider_session)
        result = self.client.request_sync(operation_name, payload, timeout_seconds=240)
        try:
            observation = session_start_observation(result.get("observation"))
            receipt = {
                "attestation": observed_harness_attestation(
                    result.get("attestation")
                ),
                "process_credentials": process_credential_observation(
                    result.get("process_credentials")
                ),
                "provider_home": provider_home_observation(
                    result.get("provider_home")
                ),
            }
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError("remote OHF start receipt is invalid") from exc
        self._start_receipts[generation.process_generation_id] = receipt
        return observation

    def start_session(
        self,
        *,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        staged_config_receipt: StageConfigReceipt | None = None,
    ) -> SessionStartObservation:
        if staged_config_receipt is not None:
            raise BrokerProtocolError("remote operator capability profile does not stage config")
        return self._start(
            operation_name="ohf-start",
            operation_id=operation_id,
            requested=requested,
            epoch=epoch,
            generation=generation,
        )

    def resume_session(
        self,
        *,
        operation_id: OperationId,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        provider_session: ProviderSessionHandoff,
        requested: RequestedExecutionProfile,
    ) -> SessionStartObservation:
        return self._start(
            operation_name="ohf-resume",
            operation_id=operation_id,
            requested=requested,
            epoch=epoch,
            generation=generation,
            provider_session=provider_session,
        )

    def materialization_status(
        self,
        *,
        operation_id: OperationId,
        requested: RequestedExecutionProfile,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        provider_session: ProviderSessionHandoff | None = None,
    ) -> OperatorMaterializationStatusObservation:
        """Read one exact receipt status without invoking or mutating a provider."""

        operation_kind = (
            "resume_session" if provider_session is not None else "start_session"
        )
        expected_provider_session_id = (
            provider_session.provider_session_id
            if provider_session is not None
            else None
        )
        if (
            requested.worker_id != epoch.worker_id
            or generation.worker_id != epoch.worker_id
            or generation.session_epoch_id != epoch.session_epoch_id
            or (
                provider_session is not None
                and provider_session.worker_id != epoch.worker_id
            )
        ):
            raise BrokerProtocolError(
                "remote OHF materialization request identity is inconsistent"
            )
        try:
            validate_materialization_request(
                operation_command_id=operation_id.command_id,
                operation_kind=operation_kind,
                attempt_id=epoch.attempt_id,
                worker_id=epoch.worker_id,
                session_epoch_id=epoch.session_epoch_id,
                process_generation_id=generation.process_generation_id,
                generation_number=generation.generation_number,
                expected_provider_session_id=expected_provider_session_id,
            )
        except OperatorMaterializationReceiptError as exc:
            raise BrokerProtocolError(
                "remote OHF materialization request identity is invalid"
            ) from exc
        payload = {
            "operation_id": to_wire(operation_id),
            "requested": to_wire(requested),
            "epoch": to_wire(epoch),
            "generation": to_wire(generation),
        }
        if provider_session is not None:
            payload["provider_session"] = to_wire(provider_session)
        result = self.client.request_sync(
            "ohf-materialization-status", payload, timeout_seconds=30
        )
        try:
            status = operator_materialization_status(result)
        except OperatorMaterializationReceiptError as exc:
            raise BrokerProtocolError(
                "remote OHF materialization status is invalid"
            ) from exc
        receipt = status.receipt
        if receipt is not None and not (
            receipt.operation_command_id == operation_id.command_id
            and receipt.operation_kind == operation_kind
            and receipt.attempt_id == epoch.attempt_id
            and receipt.worker_id == epoch.worker_id
            and receipt.session_epoch_id == epoch.session_epoch_id
            and receipt.process_generation_id == generation.process_generation_id
            and receipt.generation_number == generation.generation_number
            and receipt.requested_profile_digest
            == requested_profile_digest(to_wire(requested))
            and (
                expected_provider_session_id is None
                or receipt.provider_session_id == expected_provider_session_id
            )
        ):
            raise BrokerProtocolError(
                "remote OHF materialization receipt identity is invalid"
            )
        return status

    def _receipt(self, generation: ProcessGenerationRef) -> dict[str, Any]:
        try:
            return self._start_receipts[generation.process_generation_id]
        except KeyError as exc:
            raise BrokerProtocolError(
                "remote OHF generation has no start receipt"
            ) from exc

    def observed_attestation(self, generation: ProcessGenerationRef) -> Any:
        return self._receipt(generation)["attestation"]

    def observe_process_credentials(
        self, generation: ProcessGenerationRef
    ) -> OSProcessCredentialObservation:
        return self._receipt(generation)["process_credentials"]

    def observe_provider_home_identity(
        self, generation: ProcessGenerationRef
    ) -> ProviderHomeIdentityObservation:
        return self._receipt(generation)["provider_home"]

    def begin_turn(
        self,
        *,
        operation_id: OperationId,
        turn: TurnRef,
        generation: ProcessGenerationRef,
        launch: LaunchComparison,
    ) -> TurnStartObservation:
        prompt = self.turn_input_loader(turn)
        result = self.client.request_sync(
            "ohf-begin-turn",
            {
                "operation_id": to_wire(operation_id),
                "turn": to_wire(turn),
                "generation": to_wire(generation),
                "launch": to_wire(launch),
                "prompt": prompt,
            },
            timeout_seconds=90,
        )
        try:
            return turn_start_observation(result.get("observation"))
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError("remote OHF turn-start receipt is invalid") from exc

    def deliver_attention(
        self,
        *,
        generation: ProcessGenerationRef,
        attempt_id: str,
        binding_id: str,
        binding_generation: int,
        provider_session_id: str,
        nudge_id: str,
        opaque_ids: tuple[str, ...],
        instruction: str,
        completion_timeout_seconds: float,
    ) -> AttentionTurnObservation:
        result = self.client.request_sync(
            "ohf-deliver-attention",
            {
                "generation": to_wire(generation),
                "attempt_id": attempt_id,
                "binding_id": binding_id,
                "binding_generation": binding_generation,
                "provider_session_id": provider_session_id,
                "nudge_id": nudge_id,
                "opaque_ids": list(opaque_ids),
                "instruction": instruction,
                "completion_timeout_seconds": float(completion_timeout_seconds),
            },
            timeout_seconds=float(completion_timeout_seconds) + 30.0,
        )
        try:
            return attention_turn_observation(result.get("observation"))
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError(
                "remote OHF attention receipt is invalid"
            ) from exc

    def read_events(
        self, cursor: EventCursor, *, timeout_seconds: float = 30.0
    ) -> tuple[tuple[NormalizedEvent, ...], EventCursor]:
        if not cursor.turn_id:
            raise BrokerProtocolError("remote OHF collection requires a bound turn")
        turn = TurnRef(
            turn_id=cursor.turn_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id,
            attempt_id=cursor.attempt_id,
        )
        result = self.client.request_sync(
            "ohf-collect-turn",
            {
                "turn": to_wire(turn),
                "cursor": to_wire(cursor),
                "timeout_seconds": float(timeout_seconds),
            },
            timeout_seconds=float(timeout_seconds) + 150,
        )
        events_raw = result.get("events")
        if not isinstance(events_raw, list):
            raise BrokerProtocolError("remote OHF events must be an array")
        try:
            events = tuple(normalized_event(item) for item in events_raw)
            next_cursor = event_cursor(result.get("cursor"))
            cached = {
                "candidate": candidate_result(result.get("candidate")),
                "raw_role_result": raw_role_result_observation(
                    result.get("raw_role_result")
                ),
            }
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError("remote OHF turn receipt is invalid") from exc
        self._turn_results[turn.turn_id] = cached
        return events, next_cursor

    def _turn_result(self, turn: TurnRef, field: str) -> Any:
        try:
            return self._turn_results[turn.turn_id][field]
        except KeyError as exc:
            raise BrokerProtocolError(
                "remote OHF turn result was not collected in protocol order"
            ) from exc

    def collect_candidate_result(self, turn: TurnRef) -> CandidateResult:
        return self._turn_result(turn, "candidate")

    def observe_raw_role_result(self, turn: TurnRef) -> RawRoleResultObservation:
        return self._turn_result(turn, "raw_role_result")

    def interrupt_turn(self, turn: TurnRef, *, operation_id: OperationId) -> None:
        result = self.client.request_sync(
            "ohf-interrupt",
            {"operation_id": to_wire(operation_id), "turn": to_wire(turn)},
            timeout_seconds=30,
        )
        if result.get("interrupted") is not True:
            raise BrokerProtocolError("remote OHF interrupt receipt is invalid")

    def graceful_stop(
        self, generation: ProcessGenerationRef, *, operation_id: OperationId
    ) -> ReconcileObservation:
        result = self.client.request_sync(
            "ohf-stop",
            {
                "operation_id": to_wire(operation_id),
                "generation": to_wire(generation),
            },
            timeout_seconds=90,
        )
        try:
            observation = reconcile_observation(result.get("observation"))
            raw_receipt = result.get("artifact_receipt")
            receipt = (
                None
                if raw_receipt is None
                else browser_review_receipt(raw_receipt)
            )
        except (OperatorHarnessWireError, BrowserReviewError) as exc:
            raise BrokerProtocolError("remote OHF stop receipt is invalid") from exc
        self._artifact_receipts[generation.process_generation_id] = receipt
        return observation

    def terminal_artifact_receipt(
        self, generation: ProcessGenerationRef
    ) -> BrowserReviewReceipt | None:
        if generation.process_generation_id not in self._artifact_receipts:
            raise BrokerProtocolError(
                "remote OHF terminal artifact receipt was not observed in protocol order"
            )
        return self._artifact_receipts[generation.process_generation_id]

    def cancel(
        self,
        generation: ProcessGenerationRef,
        *,
        reason: str,
        operation_id: OperationId,
    ) -> ReconcileObservation:
        result = self.client.request_sync(
            "ohf-cancel",
            {
                "operation_id": to_wire(operation_id),
                "generation": to_wire(generation),
                "reason": reason,
            },
            timeout_seconds=90,
        )
        try:
            return reconcile_observation(result.get("observation"))
        except OperatorHarnessWireError as exc:
            raise BrokerProtocolError("remote OHF cancel receipt is invalid") from exc

    def reconcile(self, generation: ProcessGenerationRef) -> ReconcileObservation:
        result = self.client.request_sync(
            "ohf-reconcile",
            {"generation": to_wire(generation)},
            timeout_seconds=30,
        )
        try:
            observation = reconcile_observation(result.get("observation"))
            if result.get("terminal") is True:
                raw_receipt = result.get("artifact_receipt")
                self._artifact_receipts[generation.process_generation_id] = (
                    None
                    if raw_receipt is None
                    else browser_review_receipt(raw_receipt)
                )
        except (OperatorHarnessWireError, BrowserReviewError) as exc:
            raise BrokerProtocolError(
                "remote OHF reconciliation receipt is invalid"
            ) from exc
        return observation

    def reconcile_absence(
        self,
        generation: ProcessGenerationRef,
        *,
        process: ProcessIdentityObservation,
        provider_session_id: str,
        config_digest: str,
    ) -> ReconcileObservation:
        """Request a fresh dedicated-UID absence proof after broker restart."""

        result = self.client.request_sync(
            "ohf-reconcile-absence",
            {
                "generation": to_wire(generation),
                "process": to_wire(process),
                "provider_session_id": provider_session_id,
                "config_digest": config_digest,
            },
            timeout_seconds=90,
        )
        try:
            observation = reconcile_observation(result.get("observation"))
            raw_receipt = result.get("artifact_receipt")
            self._artifact_receipts[generation.process_generation_id] = (
                None
                if raw_receipt is None
                else browser_review_receipt(raw_receipt)
            )
        except (OperatorHarnessWireError, BrowserReviewError) as exc:
            raise BrokerProtocolError(
                "remote OHF absence receipt is invalid"
            ) from exc
        return observation


__all__ = ["RemoteOperatorHarnessAdapter", "TurnInputLoader"]
