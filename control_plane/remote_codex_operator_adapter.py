"""Control-side Operator Harness adapter over the existing worker broker.

The concrete Codex App Server process stays inside the dedicated worker UID.
This object is a synchronous typed proxy used by
``OperatorHarnessOrchestrator``; it owns no Job, Attempt, lease, epoch, or
session state.  Those identities are supplied by Executive Runtime and are
rechecked on both sides of the Unix socket.
"""
from __future__ import annotations

from collections.abc import Mapping
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
from control_plane.worker_browser_b1 import (
    BrowserReviewError,
    BrowserReviewReceipt,
    browser_review_receipt,
)


TurnInputLoader = Callable[[TurnRef], str]


class RemoteCodexOperatorAdapter:
    """Typed, one-request-per-call proxy for the worker-local App Server."""

    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION

    def __init__(
        self,
        client: WorkerBrokerClient,
        *,
        turn_input_loader: TurnInputLoader,
    ) -> None:
        self.client = client
        self.turn_input_loader = turn_input_loader
        self._start_receipts: dict[str, dict[str, Any]] = {}
        self._turn_results: dict[str, dict[str, Any]] = {}
        self._artifact_receipts: dict[str, BrowserReviewReceipt | None] = {}

    @staticmethod
    def _mapping(value: Any, *, name: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise BrokerProtocolError(f"remote {name} must be an object")
        return dict(value)

    def describe_capabilities(self) -> HarnessAdapterCapabilities:
        return HarnessAdapterCapabilities(
            interface_version=self.interface_version,
            supported_required_operations=(
                "start_session",
                "begin_turn",
                "read_events",
                "interrupt_turn",
                "collect_candidate_result",
                "graceful_stop",
                "cancel",
                "reconcile",
            ),
            supported_optional_operations=("resume_session",),
            supports_native_resume=True,
            supports_native_fork=False,
            supports_steering=False,
            supports_approval_response=False,
            supports_checkpoint=False,
            supports_config_staging=False,
            supports_subagent_capability_ceiling=True,
            supports_structured_events=True,
            supports_provider_native_idempotency=False,
            provider_capability_ids=("codex-app-server-stdio",),
        )

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
            raise BrokerProtocolError("remote Codex operator does not stage config")
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


__all__ = ["RemoteCodexOperatorAdapter"]
