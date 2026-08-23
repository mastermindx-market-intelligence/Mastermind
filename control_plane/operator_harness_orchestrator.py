"""Production-inert composition for the frozen Operator Harness contract.

The orchestrator deliberately owns no durable state.  Every state-changing
adapter call is preceded by a successful RuntimePort call that represents the
committed Executive INTENT transaction.  The concrete Executive runtime remains
the only Job/Attempt authority; this module does not import it so schema and
runtime work can evolve independently behind the narrow port.

This module is importable but is not registered with worker routing, a service,
or a scheduler.  Importing it performs no I/O and starts no process.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from control_plane.operator_harness_contract import (
    CandidateResult,
    EventCursor,
    LaunchComparison,
    LaunchDecision,
    NormalizedEvent,
    ObservedHarnessAttestation,
    OperationId,
    OperatorHarnessAdapter,
    ProcessGenerationRef,
    ProfileValidation,
    ProviderSessionHandoff,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    compare_launch,
)
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    OperatorPrincipalObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import (
    RawRoleResultAdapter,
    RawRoleResultObservation,
)


class OperatorHarnessOrchestrationError(RuntimeError):
    """A rich-harness operation could not be completed safely."""


class OperatorEffectUnknown(OperatorHarnessOrchestrationError):
    """A provider side effect may have occurred and must not be replayed."""


class OperatorOperationApplied(OperatorHarnessOrchestrationError):
    """The Executive receipt is APPLIED despite a later local failure."""


class OperatorLaunchRefused(OperatorHarnessOrchestrationError):
    """Static validation or observed launch attestation refused work."""


class OperatorStartRefused(OperatorLaunchRefused):
    """A started generation needs cleanup but has no authority to run turns."""

    def __init__(self, message: str, handle: "OperatorStartHandle") -> None:
        super().__init__(message)
        self.handle = handle


class RuntimePort(Protocol):
    """Narrow adapter over Executive TX APIs; not a second lifecycle contract."""

    def seal_operator_attempt(
        self, attempt_id: str, requested: RequestedExecutionProfile
    ) -> None: ...

    def extend_operator_lease(self, attempt_id: str, minimum_seconds: int) -> None: ...

    def begin_operator_session(
        self, attempt_id: str, operation_id: OperationId
    ) -> tuple[SessionEpochRef, ProcessGenerationRef]: ...

    def bind_operator_session(
        self,
        attempt_id: str,
        operation_id: OperationId,
        observation: SessionStartObservation,
    ) -> None: ...

    def seal_operator_attestation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        observed: ObservedHarnessAttestation,
        launch: LaunchComparison,
        principal: OperatorPrincipalObservation | None = None,
    ) -> None: ...

    def operator_principal_required(self, attempt_id: str) -> bool: ...

    def existing_operator_principal(
        self, attempt_id: str, generation: ProcessGenerationRef
    ) -> OperatorPrincipalObservation | None: ...

    def begin_operator_turn(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
    ) -> TurnRef: ...

    def apply_operator_turn(
        self,
        attempt_id: str,
        operation_id: OperationId,
        observation: TurnStartObservation,
    ) -> None: ...

    def record_operator_effect_unknown(
        self,
        attempt_id: str,
        operation_id: OperationId,
        phase: str,
        detail: str,
    ) -> bool: ...

    def finish_operator_candidate(
        self,
        attempt_id: str,
        turn: TurnRef,
        candidate: CandidateResult,
        events: Sequence[NormalizedEvent],
        cursor: EventCursor,
    ) -> None: ...

    def seal_operator_role_result(
        self,
        attempt_id: str,
        turn: TurnRef,
        observation: RawRoleResultObservation,
    ) -> None: ...

    def begin_operator_generation_operation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None: ...

    def graceful_stop_operator_generation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: ReconcileObservation,
    ) -> None: ...

    def cancel_operator_generation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: ReconcileObservation,
    ) -> None: ...

    def observe_operator_reconcile(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
    ) -> None: ...

    def begin_operator_resume(
        self,
        attempt_id: str,
        epoch: SessionEpochRef,
        operation_id: OperationId,
    ) -> ProcessGenerationRef: ...

    def bind_operator_resume(
        self,
        attempt_id: str,
        operation_id: OperationId,
        handoff: ProviderSessionHandoff,
        observation: SessionStartObservation,
    ) -> None: ...

    def commit_operator_resume_dispatch(
        self, attempt_id: str, operation_id: OperationId
    ) -> bool: ...

    def commit_operator_provider_dispatch(
        self, attempt_id: str, operation_id: OperationId, operation_kind: str
    ) -> bool: ...

    def begin_operator_turn_operation(
        self,
        attempt_id: str,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None: ...

    def apply_operator_turn_operation(
        self,
        attempt_id: str,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None: ...


AttestationReader = Callable[
    [OperatorHarnessAdapter, ProcessGenerationRef], ObservedHarnessAttestation
]


@dataclass(frozen=True)
class OperatorSessionReceipt:
    attempt_id: str
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    observation: SessionStartObservation
    observed: ObservedHarnessAttestation
    launch: LaunchComparison


@dataclass(frozen=True)
class OperatorStartHandle:
    attempt_id: str
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    observation: SessionStartObservation


@dataclass(frozen=True)
class OperatorTurnReceipt:
    attempt_id: str
    turn: TurnRef
    start: TurnStartObservation
    events: tuple[NormalizedEvent, ...]
    cursor: EventCursor
    candidate: CandidateResult


class OperatorHarnessOrchestrator:
    """Coordinate one rich-harness Attempt without owning durable authority."""

    def __init__(
        self,
        runtime: RuntimePort,
        adapter: OperatorHarnessAdapter,
        *,
        attestation_reader: AttestationReader,
    ) -> None:
        self.runtime = runtime
        self.adapter = adapter
        self.attestation_reader = attestation_reader
        # Process-local tripwire only.  Durable non-replayability remains the
        # RuntimePort's OperationId/Event responsibility across restart.
        self._effect_unknown: set[str] = set()
        self._applied_after_failure: set[str] = set()

    def _assert_replayable(self, operation_id: OperationId) -> None:
        if operation_id.command_id in self._effect_unknown:
            raise OperatorEffectUnknown(
                f"operation {operation_id.command_id} has unknown external effect"
            )
        if operation_id.command_id in self._applied_after_failure:
            raise OperatorOperationApplied(
                f"operation {operation_id.command_id} is already durably applied"
            )

    def _mark_effect_unknown(
        self,
        *,
        attempt_id: str,
        operation_id: OperationId,
        phase: str,
        error: Exception,
    ) -> None:
        failure_class = getattr(error, "failure_class", None)
        failure_code = getattr(failure_class, "value", failure_class)
        detail = f"exception_type={type(error).__name__}"
        if failure_code:
            detail += f";failure_class={str(failure_code)[:64]}"
        recorded = self.runtime.record_operator_effect_unknown(
            attempt_id, operation_id, phase, detail
        )
        if recorded:
            self._effect_unknown.add(operation_id.command_id)
            return
        self._applied_after_failure.add(operation_id.command_id)
        raise OperatorOperationApplied(
            f"operation {operation_id.command_id} was durably applied before local failure"
        ) from error

    def start_attempt(
        self,
        *,
        attempt_id: str,
        requested: RequestedExecutionProfile,
        operation_id: OperationId,
    ) -> OperatorSessionReceipt:
        """Seal, issue, bind, and attest one Executive-allocated session start."""

        self._assert_replayable(operation_id)
        validation: ProfileValidation = self.adapter.validate_requested_profile(
            requested
        )
        if not validation.accepted:
            raise OperatorLaunchRefused(
                "requested profile refused: " + ", ".join(validation.reasons)
            )
        self.runtime.seal_operator_attempt(attempt_id, requested)
        self.runtime.extend_operator_lease(attempt_id, 210)
        # Successful return is the RuntimePort's proof that TX-2 INTENT and its
        # writer fence committed.  The adapter is never called before this line.
        epoch, generation = self.runtime.begin_operator_session(
            attempt_id, operation_id
        )
        if not self.runtime.commit_operator_provider_dispatch(
            attempt_id, operation_id, "start_session"
        ):
            self._effect_unknown.add(operation_id.command_id)
            raise OperatorEffectUnknown("start dispatch was previously committed")
        try:
            observation = self.adapter.start_session(
                operation_id=operation_id,
                requested=requested,
                epoch=epoch,
                generation=generation,
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=attempt_id,
                operation_id=operation_id,
                phase="start_session",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "start_session external effect is unknown"
            ) from exc

        if not str(observation.provider_session_id or "").strip():
            exc = OperatorEffectUnknown("start_session returned no provider session")
            self._mark_effect_unknown(
                attempt_id=attempt_id,
                operation_id=operation_id,
                phase="bind_start_result",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "start_session returned no provider session"
            ) from exc
        try:
            self.runtime.bind_operator_session(attempt_id, operation_id, observation)
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=attempt_id,
                operation_id=operation_id,
                phase="bind_start_result",
                error=exc,
            )
            raise OperatorEffectUnknown("start result could not be bound") from exc

        handle = OperatorStartHandle(attempt_id, epoch, generation, observation)

        try:
            observed = self.attestation_reader(self.adapter, generation)
            launch = compare_launch(requested, observed)
            principal: OperatorPrincipalObservation | None = None
            principal_required = bool(
                getattr(self.runtime, "operator_principal_required", lambda _value: False)(
                    attempt_id
                )
            )
            if principal_required:
                existing_principal = getattr(
                    self.runtime,
                    "existing_operator_principal",
                    lambda _attempt_id, _generation: None,
                )(attempt_id, generation)
                if existing_principal is not None and not isinstance(
                    existing_principal, OperatorPrincipalObservation
                ):
                    raise OperatorHarnessOrchestrationError(
                        "runtime returned untyped principal replay evidence"
                    )
                credential_reader = getattr(
                    self.adapter, "observe_process_credentials", None
                )
                home_reader = getattr(
                    self.adapter, "observe_provider_home_identity", None
                )
                if existing_principal is None and (
                    not callable(credential_reader) or not callable(home_reader)
                ):
                    raise OperatorHarnessOrchestrationError(
                        "orchestration adapter lacks typed principal observations"
                    )
                if existing_principal is not None:
                    principal = existing_principal
                else:
                    credentials = credential_reader(generation)
                    home = home_reader(generation)
                    if not isinstance(credentials, OSProcessCredentialObservation) or not isinstance(
                        home, ProviderHomeIdentityObservation
                    ):
                        raise OperatorHarnessOrchestrationError(
                            "orchestration adapter returned untyped principal evidence"
                        )
                    process = observation.process
                    expected_process = {
                        "pid": process.pid,
                        "pgid": process.pgid,
                        "process_start_identity": process.process_start_identity,
                        "boot_id": process.boot_id,
                    }
                    if credentials.process_identity != expected_process:
                        raise OperatorHarnessOrchestrationError(
                            "principal process credentials do not match TX-3 observation"
                        )
                    principal = OperatorPrincipalObservation.from_dict(
                        {
                            "schema_version": "mastermind.operator_principal_observation/v1",
                            "attempt_id": attempt_id,
                            "worker_id": generation.worker_id,
                            "process_generation_id": generation.process_generation_id,
                            "provider_session_id": observation.provider_session_id,
                            "process_identity": credentials.process_identity,
                            "os_principal_name": credentials.os_principal_name,
                            "os_principal_uid": credentials.os_principal_uid,
                            "provider_home_identity": home.provider_home_identity,
                            "observed_at_ms": int(time.time() * 1000),
                        }
                    )
                self.runtime.seal_operator_attestation(
                    attempt_id, generation, observed, launch, principal
                )
            else:
                self.runtime.seal_operator_attestation(
                    attempt_id, generation, observed, launch
                )
        except Exception as exc:
            raise OperatorStartRefused(
                "started session requires cleanup after attestation error", handle
            ) from exc
        if launch.decision is not LaunchDecision.ALLOW:
            raise OperatorStartRefused(
                "started session failed observed attestation: " + launch.decision.value,
                handle,
            )
        return OperatorSessionReceipt(
            attempt_id=attempt_id,
            epoch=epoch,
            generation=generation,
            observation=observation,
            observed=observed,
            launch=launch,
        )

    def run_turn(
        self,
        session: OperatorSessionReceipt,
        *,
        operation_id: OperationId,
        cursor: EventCursor | None = None,
        timeout_seconds: float = 30.0,
    ) -> OperatorTurnReceipt:
        """Issue one turn and persist only a candidate result, never Job completion."""

        self._assert_replayable(operation_id)
        bounded_timeout = float(timeout_seconds)
        if (
            not math.isfinite(bounded_timeout)
            or bounded_timeout <= 0
            or bounded_timeout > 300.0
        ):
            raise OperatorHarnessOrchestrationError(
                "turn timeout must be finite and within (0, 300] seconds"
            )
        if session.launch.decision is not LaunchDecision.ALLOW:
            raise OperatorLaunchRefused(
                "work turn refused by observed launch comparison: "
                + session.launch.decision.value
            )
        turn = self.runtime.begin_operator_turn(
            session.attempt_id, session.generation, operation_id
        )
        self.runtime.extend_operator_lease(session.attempt_id, 90)
        if not self.runtime.commit_operator_provider_dispatch(
            session.attempt_id, operation_id, "begin_turn"
        ):
            self._effect_unknown.add(operation_id.command_id)
            raise OperatorEffectUnknown("turn dispatch was previously committed")
        try:
            started = self.adapter.begin_turn(
                operation_id=operation_id,
                turn=turn,
                generation=session.generation,
                launch=session.launch,
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="begin_turn",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "begin_turn external effect is unknown"
            ) from exc
        if not started.acknowledged:
            exc = OperatorEffectUnknown("provider did not acknowledge begin_turn")
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="begin_turn_ack",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "provider did not acknowledge begin_turn"
            ) from exc
        try:
            self.runtime.apply_operator_turn(session.attempt_id, operation_id, started)
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="bind_turn_result",
                error=exc,
            )
            raise OperatorEffectUnknown("turn result could not be bound") from exc

        current = cursor or EventCursor(
            attempt_id=session.attempt_id,
            session_epoch_id=session.epoch.session_epoch_id,
            process_generation_id=session.generation.process_generation_id,
            turn_id=turn.turn_id,
        )
        self.runtime.extend_operator_lease(
            session.attempt_id, int(math.ceil(bounded_timeout)) + 30
        )
        try:
            events, next_cursor = self.adapter.read_events(
                current, timeout_seconds=bounded_timeout
            )
            candidate = self.adapter.collect_candidate_result(turn)
            if candidate.complete_job_permitted:
                raise OperatorHarnessOrchestrationError(
                    "adapter candidate attempted to claim Executive completion"
                )
            self.runtime.finish_operator_candidate(
                session.attempt_id, turn, candidate, events, next_cursor
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="collect_turn_result",
                error=exc,
            )
            raise OperatorEffectUnknown("turn result effect is unknown") from exc
        if bool(
            getattr(self.runtime, "operator_principal_required", lambda _value: False)(
                session.attempt_id
            )
        ):
            if not isinstance(self.adapter, RawRoleResultAdapter):
                raise OperatorHarnessOrchestrationError(
                    "orchestration adapter lacks the raw role-result extension"
                )
            try:
                raw_observation = self.adapter.observe_raw_role_result(turn)
                self.runtime.seal_operator_role_result(
                    session.attempt_id, turn, raw_observation
                )
            except Exception as exc:
                raise OperatorHarnessOrchestrationError(
                    "orchestration role result could not be sealed"
                ) from exc
        return OperatorTurnReceipt(
            attempt_id=session.attempt_id,
            turn=turn,
            start=started,
            events=tuple(events),
            cursor=next_cursor,
            candidate=candidate,
        )

    def graceful_stop(
        self,
        session: OperatorSessionReceipt | OperatorStartHandle,
        *,
        operation_id: OperationId,
    ) -> ReconcileObservation:
        self._assert_replayable(operation_id)
        self.runtime.begin_operator_generation_operation(
            session.attempt_id,
            session.generation,
            operation_id,
            "graceful_stop",
        )
        self.runtime.extend_operator_lease(session.attempt_id, 60)
        try:
            observed = self.adapter.graceful_stop(
                session.generation, operation_id=operation_id
            )
            self.runtime.graceful_stop_operator_generation(
                session.attempt_id,
                session.generation,
                operation_id,
                observed,
            )
            return observed
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="graceful_stop",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "graceful_stop external effect is unknown"
            ) from exc

    def cancel(
        self,
        session: OperatorSessionReceipt | OperatorStartHandle,
        *,
        operation_id: OperationId,
        reason: str,
    ) -> ReconcileObservation:
        self._assert_replayable(operation_id)
        self.runtime.begin_operator_generation_operation(
            session.attempt_id, session.generation, operation_id, "cancel"
        )
        self.runtime.extend_operator_lease(session.attempt_id, 60)
        try:
            observed = self.adapter.cancel(
                session.generation, reason=reason, operation_id=operation_id
            )
            self.runtime.cancel_operator_generation(
                session.attempt_id,
                session.generation,
                operation_id,
                observed,
            )
            return observed
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="cancel",
                error=exc,
            )
            raise OperatorEffectUnknown("cancel external effect is unknown") from exc

    def interrupt_turn(
        self,
        session: OperatorSessionReceipt,
        turn: TurnRef,
        *,
        operation_id: OperationId,
    ) -> None:
        self._assert_replayable(operation_id)
        interrupt = getattr(self.adapter, "interrupt_turn", None)
        if not callable(interrupt):
            raise OperatorLaunchRefused("adapter does not support turn interruption")
        self.runtime.begin_operator_turn_operation(
            session.attempt_id, turn, operation_id, "interrupt_turn"
        )
        self.runtime.extend_operator_lease(session.attempt_id, 60)
        if not self.runtime.commit_operator_provider_dispatch(
            session.attempt_id, operation_id, "interrupt_turn"
        ):
            self._effect_unknown.add(operation_id.command_id)
            raise OperatorEffectUnknown("interrupt dispatch was previously committed")
        try:
            interrupt(turn, operation_id=operation_id)
            self.runtime.apply_operator_turn_operation(
                session.attempt_id, turn, operation_id, "interrupt_turn"
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="interrupt_turn",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "interrupt_turn external effect is unknown"
            ) from exc

    def reconcile(
        self, session: OperatorSessionReceipt | OperatorStartHandle
    ) -> ReconcileObservation:
        self.runtime.extend_operator_lease(session.attempt_id, 60)
        observed = self.adapter.reconcile(session.generation)
        self.runtime.observe_operator_reconcile(
            session.attempt_id, session.generation, observed
        )
        return observed

    def resume(
        self,
        session: OperatorSessionReceipt,
        *,
        operation_id: OperationId,
        handoff: ProviderSessionHandoff,
    ) -> OperatorSessionReceipt:
        """TX-10/TX-11 resume of bound S1 on an Executive-allocated G2."""

        self._assert_replayable(operation_id)
        resume = getattr(self.adapter, "resume_session", None)
        if not callable(resume):
            raise OperatorLaunchRefused("adapter does not support session resume")
        generation = self.runtime.begin_operator_resume(
            session.attempt_id, session.epoch, operation_id
        )
        self.runtime.extend_operator_lease(session.attempt_id, 210)
        if not self.runtime.commit_operator_provider_dispatch(
            session.attempt_id, operation_id, "resume_session"
        ):
            self._effect_unknown.add(operation_id.command_id)
            raise OperatorEffectUnknown(
                "resume dispatch was previously committed without a terminal receipt"
            )
        try:
            observation = resume(
                operation_id=operation_id,
                epoch=session.epoch,
                generation=generation,
                provider_session=handoff,
                requested=session.launch.requested,
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="resume_session",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "resume_session external effect is unknown"
            ) from exc
        if observation.provider_session_id != handoff.provider_session_id:
            exc = OperatorEffectUnknown("resume observation did not preserve bound S1")
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="bind_resume_result",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "resume observation did not preserve bound S1"
            ) from exc
        try:
            self.runtime.bind_operator_resume(
                session.attempt_id, operation_id, handoff, observation
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="bind_resume_result",
                error=exc,
            )
            raise OperatorEffectUnknown("resume result could not be bound") from exc

        try:
            observed = self.attestation_reader(self.adapter, generation)
            launch = compare_launch(session.launch.requested, observed)
            self.runtime.seal_operator_attestation(
                session.attempt_id, generation, observed, launch
            )
        except Exception as exc:
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="attest_resume_result",
                error=exc,
            )
            raise OperatorEffectUnknown("resume attestation effect is unknown") from exc
        if launch.decision is not LaunchDecision.ALLOW:
            exc = OperatorLaunchRefused(
                "observed resume mismatch: " + launch.decision.value
            )
            self._mark_effect_unknown(
                attempt_id=session.attempt_id,
                operation_id=operation_id,
                phase="attest_resume_mismatch",
                error=exc,
            )
            raise OperatorEffectUnknown(
                "resumed session failed observed attestation"
            ) from exc
        return OperatorSessionReceipt(
            attempt_id=session.attempt_id,
            epoch=session.epoch,
            generation=generation,
            observation=observation,
            observed=observed,
            launch=launch,
        )


__all__ = [
    "AttestationReader",
    "OperatorEffectUnknown",
    "OperatorHarnessOrchestrationError",
    "OperatorHarnessOrchestrator",
    "OperatorLaunchRefused",
    "OperatorOperationApplied",
    "OperatorSessionReceipt",
    "OperatorStartHandle",
    "OperatorStartRefused",
    "OperatorTurnReceipt",
    "RuntimePort",
]
