"""Constructor-only bridge from OHF orchestration to Executive transactions.

This module is deliberately not imported by the Executive service, supervisor,
worker broker, flags, or route configuration.  Constructing a port performs no
I/O.  Each method delegates authority to ``OperatorHarnessRegistry`` using the
one supplied ``AttemptLease``; it never calls a provider or mutates Job status.
"""

from __future__ import annotations

from collections.abc import Sequence

from control_plane.operator_continuation import (
    ContinuationAck, OperatorContinuation, OperatorContinuationDraft,
)

from control_plane.executive_runtime import (
    AttemptLease, AttemptStatus, Runtime, StateConflict,
    _interactive_tx5_admitted, orchestration_digest,
)
from control_plane.executive_orchestration_principal import OperatorPrincipalObservation
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.native_conversation_result import (
    NativeConversationResultObservation, NativeConversationResultRef, result_contract_for_profile,
)
from control_plane.operator_harness_contract import (
    CandidateResult,
    CheckpointObservation,
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

    def prepare_operator_continuation(
        self, attempt_id: str, draft: "OperatorContinuationDraft"
    ) -> "OperatorContinuation":
        """Prepare once through the existing fenced Runtime Event transaction."""
        self._require_attempt(attempt_id)
        return self.runtime.prepare_operator_continuation(
            attempt_id, fence_generation=self.fence_generation,
            lease_token=self.lease_token, draft=draft,
        )

    def acknowledge_operator_continuation(
        self, attempt_id: str, ack: "ContinuationAck"
    ) -> None:
        """Record exact consumption evidence, not lifecycle or Wake completion."""
        self._require_attempt(attempt_id)
        self.runtime.acknowledge_operator_continuation(
            attempt_id, fence_generation=self.fence_generation,
            lease_token=self.lease_token, ack=ack,
        )

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

    def existing_interactive_plan_seal(
        self, attempt_id: str, generation: ProcessGenerationRef
    ) -> str | None:
        """Project an existing initial seal; never grant or start another turn.

        Reuse the Runtime owner's lease, lineage and seal validators. This
        read-only projection lets the driver distinguish the immutable plan
        from later candidate evidence without attempting a second plan seal.
        Ordinary roles and an interactive first turn retain normal sealing.
        """
        self._require_attempt(attempt_id)
        registry = self.runtime.operator_harness
        epoch, stored = registry.generation_refs(generation.process_generation_id)
        if stored != generation or epoch.attempt_id != attempt_id:
            raise StateConflict("interactive seal generation is outside the lease")
        with self.runtime.store.read() as connection:
            row = registry._leased(
                connection, attempt_id=attempt_id,
                fence_generation=self.fence_generation,
                lease_token=self.lease_token,
                timestamp=self.runtime.store.now_ms(),
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            job = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if job is None:
                raise StateConflict("interactive seal lost its Job")
            if not _interactive_tx5_admitted(job, connection=connection):
                return None
            registry._owned_generation(
                connection, leased=row, epoch=epoch, generation=generation,
                require_current=True, require_writer=True,
            )
            if registry._event(
                connection, f"orchestration-result-seal:{attempt_id}"
            ) is None:
                return None
            seal = registry._validate_interactive_active_plan_seal(
                connection, attempt_row=row, job_row=job,
            )
            if seal["process_generation_id"] != generation.process_generation_id:
                raise StateConflict("interactive seal belongs to another generation")
            return orchestration_digest(seal)

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


    def original_operator_native_turn(self, attempt_id, generation, operation_id):
        """Read the original committed target under this same current lease."""
        self._require_attempt(attempt_id)
        from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT
        from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
        if self.operator_result_contract(attempt_id) != DSH_NATIVE_RESULT_CONTRACT:
            raise StateConflict("native recovery requires the original native contract")
        harness = self.runtime.operator_harness
        epoch, stored = harness.generation_refs(generation.process_generation_id)
        if generation != stored or epoch.attempt_id != attempt_id:
            raise StateConflict("native recovery generation differs")
        with self.runtime.store.read() as connection:
            row = harness._leased(connection, attempt_id=attempt_id, fence_generation=self.fence_generation,
                lease_token=self.lease_token, timestamp=self.runtime.store.now_ms(),
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
            durable = harness._owned_generation(connection, leased=row, epoch=epoch, generation=generation,
                                                 require_current=True, require_writer=True)
            harness._require_active_orchestration_generation(connection, row=row,
                                                             generation_id=generation.process_generation_id)
            harness._require_no_native_close_intent(connection, generation=generation)
            _event, payload = harness._native_operation_event(connection, row=row, operation=operation_id,
                kind=OperationReceiptKind.INTENT, command_id=operation_id.command_id)
            turn = TurnRef(str(payload.get("turn_id") or ""), epoch.session_epoch_id,
                           generation.process_generation_id, attempt_id)
            if payload != {
                    "schema_version": "mastermind.operator_harness_turn_intent/v1", "operation_kind": "begin_turn",
                    "attempt_id": attempt_id, "session_epoch_id": epoch.session_epoch_id,
                    "process_generation_id": generation.process_generation_id, "worker_id": row["worker_id"],
                    "provider_session_id": durable["provider_session_id"], "turn_id": turn.turn_id}:
                raise StateConflict("native recovery original target differs")
            dispatch, value = harness._native_operation_event(connection, row=row, operation=operation_id,
                kind="OHF_PROVIDER_DISPATCH_COMMITTED", command_id=operation_id.command_id+":dispatch")
            if (value != {"schema_version": "mastermind.operator_harness_provider_dispatch/v1", "operation_kind": "begin_turn"}
                    or int(dispatch["event_id"]) <= int(_event["event_id"])):
                raise StateConflict("native recovery has no original committed dispatch")
            return turn


    def prepare_operator_native_begin_recovery(self, attempt_id, generation, operation_id, expected_turn):
        """Reconcile a missing uncertainty write on this exact original call."""
        from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
        if (type(expected_turn) is not TurnRef
                or self.original_operator_native_turn(attempt_id, generation, operation_id) != expected_turn):
            raise StateConflict("native recovery differs from its retained original turn")
        harness = self.runtime.operator_harness
        with self.runtime.store.read() as connection:
            receipts = {kind: harness._event(connection, operation_receipt_command_id(operation_id, kind))
                        for kind in (OperationReceiptKind.APPLIED, OperationReceiptKind.EFFECT_UNKNOWN,
                                     OperationReceiptKind.RECONCILED, OperationReceiptKind.REFUSED)}
            if receipts[OperationReceiptKind.REFUSED] is not None:
                raise StateConflict("native recovery has an original refusal")
            if (receipts[OperationReceiptKind.RECONCILED] is not None
                    and receipts[OperationReceiptKind.EFFECT_UNKNOWN] is None):
                raise StateConflict("native recovery reconciliation lost its original uncertainty source")
            missing = all(receipt is None for receipt in receipts.values())
        if missing:
            # The existing writer rechecks the lease/effect budget and rejects
            # conflicting concurrent receipts. No existing receipt is rewritten.
            self.record_operator_effect_unknown(attempt_id, operation_id, "begin_turn_dispatch",
                                                "dispatch_committed_without_terminal_receipt")
        if self.original_operator_native_turn(attempt_id, generation, operation_id) != expected_turn:
            raise StateConflict("native recovery original target changed")

    def operator_native_turn_result_material(self, attempt_id, turn, operation_id):
        """Read an existing original candidate/seal before any recovery RPC."""
        self._require_attempt(attempt_id)
        from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT
        from control_plane.operator_harness_wire import candidate_result, event_cursor, normalized_event
        if self.operator_result_contract(attempt_id) != DSH_NATIVE_RESULT_CONTRACT:
            raise StateConflict("native material requires its original contract")
        harness = self.runtime.operator_harness
        with self.runtime.store.read() as connection:
            row = harness._leased(connection, attempt_id=attempt_id, fence_generation=self.fence_generation,
                lease_token=self.lease_token, timestamp=self.runtime.store.now_ms(),
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
            if harness._event(connection, f"ohf-candidate:{turn.turn_id}") is None:
                return None
            operation, _intent, _value, _ack, payload = harness._validated_tx5_receipts(connection, row=row, turn=turn)
            if operation != operation_id:
                raise StateConflict("native candidate belongs to another original operation")
            _candidate, value = harness._validated_candidate_event(connection, row=row, turn=turn)
            reference = None
            if harness._event(connection, f"ohf-native-result:{turn.turn_id}") is not None:
                event, seal = harness._validated_native_turn_result(connection, row=row, turn=turn)
                reference = harness._native_result_ref(event, seal)
            return (TurnStartObservation(payload["provider_native_turn_id"], True),
                    candidate_result(value["candidate"]), tuple(normalized_event(event) for event in value["events"]),
                    event_cursor(value["cursor"]), reference)

    def reconcile_operator_native_begin(self, attempt_id, operation_id, observation):
        self._require_attempt(attempt_id)
        if observation.turn.attempt_id != attempt_id:
            raise StateConflict("native begin observation is outside the bound Attempt")
        return self.runtime.operator_harness.reconcile_native_begin(
            turn=observation.turn, operation_id=operation_id, observation=observation,
            fence_generation=self.fence_generation, lease_token=self.lease_token)

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

    def operator_result_contract(self, attempt_id: str) -> str:
        self._require_attempt(attempt_id)
        attempt = self.runtime.attempts.get_attempt(attempt_id)
        if attempt is None or attempt.job_id != self.lease.attempt.job_id:
            raise StateConflict("operator result Attempt identity differs")
        contract = self.runtime.jobs.operator_result_contract(attempt.job_id)
        from control_plane.operator_harness_wire import requested_execution_profile
        if result_contract_for_profile(requested_execution_profile(
                attempt.requested_execution_profile)) != contract:
            raise StateConflict("sealed profile differs from original result contract")
        return contract

    def seal_operator_native_result(
        self, attempt_id: str, turn: TurnRef, observation: NativeConversationResultObservation,
    ) -> NativeConversationResultRef:
        self._require_attempt(attempt_id)
        if turn.attempt_id != attempt_id:
            raise StateConflict("native result turn is outside the bound Attempt")
        return self.runtime.operator_harness.seal_native_conversation_result(
            turn=turn, observation=observation,
            fence_generation=self.fence_generation, lease_token=self.lease_token)

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
        *,
        native_idle_result: NativeConversationResultRef | None = None,
        native_terminal_result: NativeConversationResultRef | None = None,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.reserve_generation_operation(
            generation=generation,
            operation_id=operation_id,
            operation_kind=operation_kind,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            native_idle_result=native_idle_result,
            native_terminal_result=native_terminal_result,
        )

    def begin_operator_checkpoint(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.reserve_checkpoint_operation(
            generation=generation,
            operation_id=operation_id,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def apply_operator_checkpoint(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: CheckpointObservation,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.apply_checkpoint_operation(
            generation=generation,
            operation_id=operation_id,
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
        )

    def graceful_stop_operator_generation(
        self,
        attempt_id: str,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        observation: ReconcileObservation,
        *,
        native_idle_result: NativeConversationResultRef | None = None,
        native_terminal_result: NativeConversationResultRef | None = None,
    ) -> None:
        self._require_attempt(attempt_id)
        self.runtime.operator_harness.apply_generation_operation(
            generation=generation,
            operation_id=operation_id,
            operation_kind="graceful_stop",
            observation=observation,
            fence_generation=self.fence_generation,
            lease_token=self.lease_token,
            native_idle_result=native_idle_result,
            native_terminal_result=native_terminal_result,
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
