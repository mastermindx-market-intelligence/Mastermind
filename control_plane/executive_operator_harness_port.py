"""Constructor-only bridge from OHF orchestration to Executive transactions.

This module is deliberately not imported by the Executive service, supervisor,
worker broker, flags, or route configuration.  Constructing a port performs no
I/O.  Each method delegates authority to ``OperatorHarnessRegistry`` using the
one supplied ``AttemptLease``; it never calls a provider or mutates Job status.
"""

from __future__ import annotations

from collections.abc import Sequence

from control_plane.executive_runtime import AttemptLease, Runtime, StateConflict
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.operator_harness_contract import (
    CandidateResult,
    EventCursor,
    LaunchComparison,
    NormalizedEvent,
    ObservedHarnessAttestation,
    OperationId,
    OperationKind,
    ProcessGenerationRef,
    ProviderSessionHandoff,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    compare_launch,
)


class ExecutiveOperatorHarnessPort:
    """Bind one leased Attempt to the real Executive OHF Event/SQLite plane."""

    def __init__(self, runtime: Runtime, lease: AttemptLease) -> None:
        self.runtime = runtime
        self.lease = lease

    @property
    def attempt_id(self) -> str:
        return self.lease.attempt.attempt_id

    @property
    def fence_generation(self) -> int:
        return self.lease.attempt.fence_generation

    @property
    def lease_token(self) -> str:
        return self.lease.lease_token

    def _require_attempt(self, attempt_id: str) -> None:
        if attempt_id != self.attempt_id:
            raise StateConflict("RuntimePort is bound to a different AttemptLease")

    def seal_operator_attempt(
        self, attempt_id: str, requested: RequestedExecutionProfile
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.seal_operator_harness_attempt(
            attempt_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            requested=requested,
        )

    def extend_operator_lease(self, attempt_id: str, minimum_seconds: int) -> None:
        self._require_attempt(attempt_id)
        self.runtime.attempts.heartbeat_attempt(
            attempt_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            extend_seconds=minimum_seconds,
        )

    def begin_operator_session(
        self, attempt_id: str, operation_id: OperationId
    ) -> tuple[SessionEpochRef, ProcessGenerationRef]:
        self._require_attempt(attempt_id)
        return self.runtime.operator_harness.reserve_start(
            attempt_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            operation_id=operation_id,
        )

    def bind_operator_session(
        self,
        attempt_id: str,
        operation_id: OperationId,
        observation: SessionStartObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        if not observation.provider_session_id:
            raise StateConflict("start observation has no provider session")
        intent = self.runtime.events.get_event_by_command_id(operation_id.command_id)
        if intent is None:
            raise StateConflict("start INTENT is missing")
        epoch, generation = self.runtime.operator_harness.generation_refs(
            str(intent.payload.get("process_generation_id") or "")
        )
        self.runtime.operator_harness.bind_start_result(
            epoch=epoch,
            generation=generation,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            provider_session_id=observation.provider_session_id,
            process=observation.process,
        )

    def seal_operator_attestation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        observed: ObservedHarnessAttestation,
        launch: LaunchComparison,
        principal: OperatorPrincipalObservation | None = None,
    ) -> None:
        self._require_attempt(attempt_id)
        derived = compare_launch(launch.requested, observed)
        if launch != derived:
            raise StateConflict("caller launch comparison is not derivable")
        self.runtime.operator_harness.seal_attestation(
            generation=generation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            requested=launch.requested,
            attestation=observed,
            principal_observation=principal,
        )

    def operator_principal_required(self, attempt_id: str) -> bool:
        self._require_attempt(attempt_id)
        job = self.runtime.jobs.get_job(self.lease.attempt.job_id)
        if job is None:
            raise StateConflict("Attempt lost its Job")
        return job.orchestration_role is not None

    def existing_operator_principal(
        self, attempt_id: str, generation: ProcessGenerationRef
    ) -> OperatorPrincipalObservation | None:
        self._require_attempt(attempt_id)
        return self.runtime.operator_harness.admitted_principal_observation(generation)

    def begin_operator_turn(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
    ) -> TurnRef:
        self._require_attempt(attempt_id)
        epoch, stored = self.runtime.operator_harness.generation_refs(
            generation.process_generation_id
        )
        if stored != generation:
            raise StateConflict("turn generation does not match durable identity")
        return self.runtime.operator_harness.reserve_turn(
            epoch=epoch,
            generation=generation,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def apply_operator_turn(
        self,
        attempt_id: str,
        operation_id: OperationId,
        observation: TurnStartObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        if not observation.acknowledged:
            raise StateConflict("turn was not acknowledged")
        intent = self.runtime.events.get_event_by_command_id(operation_id.command_id)
        if intent is None:
            raise StateConflict("turn INTENT is missing")
        payload = intent.payload
        turn = TurnRef(
            str(payload.get("turn_id") or ""),
            str(payload.get("session_epoch_id") or ""),
            str(payload.get("process_generation_id") or ""),
            attempt_id,
        )
        self.runtime.operator_harness.acknowledge_turn(
            turn=turn,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            observation=observation,
        )

    def record_operator_effect_unknown(
        self,
        attempt_id: str,
        operation_id: OperationId,
        phase: str,
        detail: str,
    ) -> bool:
        self._require_attempt(attempt_id)
        return self.runtime.operator_harness.record_effect_unknown(
            attempt_id=attempt_id,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            phase=phase,
            detail=detail,
        )

    def finish_operator_candidate(
        self,
        attempt_id: str,
        turn: TurnRef,
        candidate: CandidateResult,
        events: Sequence[NormalizedEvent],
        cursor: EventCursor,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.record_candidate_evidence(
            turn=turn,
            candidate=candidate,
            events=events,
            cursor=cursor,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def seal_operator_role_result(
        self,
        attempt_id: str,
        turn: TurnRef,
        observation: RawRoleResultObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.seal_orchestration_role_result(
            turn=turn,
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def begin_operator_generation_operation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.reserve_generation_operation(
            generation=generation,
            operation_id=operation_id,
            operation_kind=operation_kind,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def graceful_stop_operator_generation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: ReconcileObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.apply_generation_operation(
            generation=generation,
            operation_id=operation_id,
            operation_kind="graceful_stop",
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def cancel_operator_generation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: ReconcileObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.apply_generation_operation(
            generation=generation,
            operation_id=operation_id,
            operation_kind="cancel",
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def observe_operator_reconcile(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.record_reconcile_observation(
            generation=generation,
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def begin_operator_resume(
        self,
        attempt_id: str,
        epoch: SessionEpochRef,
        operation_id: OperationId,
    ) -> ProcessGenerationRef:
        self._require_attempt(attempt_id)
        old_generation = self.runtime.operator_harness.current_writer_generation(epoch)
        return self.runtime.operator_harness.reserve_same_epoch_resume(
            epoch=epoch,
            old_generation=old_generation,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def bind_operator_resume(
        self,
        attempt_id: str,
        operation_id: OperationId,
        handoff: ProviderSessionHandoff,
        observation: SessionStartObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        if (
            handoff.worker_id != self.lease.attempt.worker_id
            or observation.provider_session_id != handoff.provider_session_id
        ):
            raise StateConflict("resume handoff/result identity mismatch")
        intent = self.runtime.events.get_event_by_command_id(operation_id.command_id)
        if intent is None:
            raise StateConflict("resume INTENT is missing")
        epoch, generation = self.runtime.operator_harness.generation_refs(
            str(intent.payload.get("process_generation_id") or "")
        )
        self.runtime.operator_harness.bind_resume_result(
            epoch=epoch,
            generation=generation,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            provider_session_id=handoff.provider_session_id,
            process=observation.process,
        )

    def commit_operator_resume_dispatch(
        self, attempt_id: str, operation_id: OperationId
    ) -> bool:
        self._require_attempt(attempt_id)
        return self.runtime.operator_harness.commit_provider_dispatch(
            attempt_id=attempt_id,
            operation_id=operation_id,
            operation_kind=OperationKind.RESUME_SESSION,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def commit_operator_provider_dispatch(
        self, attempt_id: str, operation_id: OperationId, operation_kind: str
    ) -> bool:
        self._require_attempt(attempt_id)
        return self.runtime.operator_harness.commit_provider_dispatch(
            attempt_id=attempt_id,
            operation_id=operation_id,
            operation_kind=operation_kind,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def begin_operator_turn_operation(
        self,
        attempt_id: str,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.reserve_turn_operation(
            turn=turn,
            operation_id=operation_id,
            operation_kind=operation_kind,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def apply_operator_turn_operation(
        self,
        attempt_id: str,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.apply_turn_operation(
            turn=turn,
            operation_id=operation_id,
            operation_kind=operation_kind,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )


__all__ = ["ExecutiveOperatorHarnessPort"]
