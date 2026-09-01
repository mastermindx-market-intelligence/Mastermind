"""Exact-session Wake acknowledgement ingress over existing Executive owners."""
from __future__ import annotations

import dataclasses

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import (
    BINDING_ID_RE,
    SessionTargetError,
    SessionTargetRegistry,
)
from control_plane.wake_events import ATTEMPT_ID_RE, WAKE_ID_RE
from control_plane.wake_ledger import (
    NUDGE_ID_RE,
    AckMode,
    LedgerPhase,
    TrustedAckContext,
    WakeLedgerError,
    ack_record,
    acknowledge,
)
from control_plane.wake_persist import PersistedWakeEvent, WakeLedgerRepository


class WakeAckIngressError(ValueError):
    """A target claim or trusted current-writer projection is not admissible."""


@dataclasses.dataclass(frozen=True)
class WakeAckClaim:
    """The entire model-authored surface: opaque canonical Wake ids only."""

    obligation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        ids = tuple(self.obligation_ids)
        if not ids:
            raise WakeAckIngressError("Wake ACK claim must not be empty")
        if ids != tuple(sorted(set(ids))):
            raise WakeAckIngressError(
                "Wake ACK claim identities must be unique and sorted"
            )
        if any(WAKE_ID_RE.fullmatch(item) is None for item in ids):
            raise WakeAckIngressError(
                "Wake ACK claim contains a malformed obligation_id"
            )
        object.__setattr__(self, "obligation_ids", ids)


@dataclasses.dataclass(frozen=True)
class TrustedWorkerWakeAckProjection:
    """Closed current-writer evidence; no raw provider output crosses this seam."""

    target_attempt_id: str
    process_generation_id: str
    binding_id: str
    binding_generation: int
    provider_session_id: str
    provider_native_turn_id: str
    nudge_id: str
    obligation_ids: tuple[str, ...]
    terminal_ack_trailer: bool

    def __post_init__(self) -> None:
        if ATTEMPT_ID_RE.fullmatch(str(self.target_attempt_id or "")) is None:
            raise WakeAckIngressError("target_attempt_id is malformed")
        for name in (
            "process_generation_id",
            "provider_session_id",
            "provider_native_turn_id",
        ):
            value = str(getattr(self, name) or "").strip()
            if not value or value != getattr(self, name):
                raise WakeAckIngressError(f"{name} is required and must be trimmed")
        if BINDING_ID_RE.fullmatch(str(self.binding_id or "")) is None:
            raise WakeAckIngressError("binding_id is malformed")
        if (
            type(self.binding_generation) is not int
            or isinstance(self.binding_generation, bool)
            or self.binding_generation < 1
        ):
            raise WakeAckIngressError("binding_generation must be an integer >= 1")
        if NUDGE_ID_RE.fullmatch(str(self.nudge_id or "")) is None:
            raise WakeAckIngressError("nudge_id is malformed")
        ids = tuple(self.obligation_ids)
        if not ids or ids != tuple(sorted(set(ids))):
            raise WakeAckIngressError(
                "trusted projection obligation identities must be unique and sorted"
            )
        if any(WAKE_ID_RE.fullmatch(item) is None for item in ids):
            raise WakeAckIngressError(
                "trusted projection contains a malformed obligation_id"
            )
        object.__setattr__(self, "obligation_ids", ids)
        if self.terminal_ack_trailer is not True:
            raise WakeAckIngressError("trusted projection requires a terminal ACK trailer")


def acknowledge_consumed_wakes(
    runtime: Runtime,
    registry: SessionTargetRegistry,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWorkerWakeAckProjection,
) -> tuple[PersistedWakeEvent, ...]:
    """Atomically bind exact prior deliveries to the current OHF writer and ACK."""

    if not isinstance(runtime, Runtime):
        raise WakeAckIngressError("ACK ingress requires an Executive Runtime")
    if not isinstance(registry, SessionTargetRegistry):
        raise WakeAckIngressError("ACK ingress requires a SessionTargetRegistry")
    if not isinstance(claim, WakeAckClaim):
        raise WakeAckIngressError("ACK ingress requires a WakeAckClaim")
    if not isinstance(trusted, TrustedWorkerWakeAckProjection):
        raise WakeAckIngressError(
            "ACK ingress requires a trusted current-writer projection"
        )
    if trusted.obligation_ids != claim.obligation_ids:
        raise WakeAckIngressError(
            "trusted projection obligation ids do not match the claim"
        )

    repository = WakeLedgerRepository(runtime)
    try:
        with runtime.store.transaction() as connection:
            records_to_append = []
            batch_identity = None
            for obligation_id in claim.obligation_ids:
                records = repository.list_ledger_records_on_connection(
                    connection, obligation_id
                )
                requests = [
                    record
                    for record in records
                    if record.phase is LedgerPhase.WAKE_REQUESTED
                    and record.obligation is not None
                ]
                if len(requests) != 1:
                    raise WakeAckIngressError(
                        "ACK ingress requires exactly one WAKE_REQUESTED obligation"
                    )
                obligation = requests[0].obligation
                assert obligation is not None
                if obligation.attempt_id == trusted.target_attempt_id:
                    raise WakeAckIngressError(
                        "target Attempt cannot be inferred from the Wake source Attempt"
                    )

                deliveries = [
                    record
                    for record in records
                    if record.phase is LedgerPhase.DELIVERED
                    and record.nudge_id == trusted.nudge_id
                ]
                if len(deliveries) != 1:
                    raise WakeAckIngressError(
                        "ACK ingress requires exactly one matching DELIVERED record"
                    )
                delivered = deliveries[0]
                try:
                    target = registry.get(str(delivered.session_alias or ""))
                except SessionTargetError as exc:
                    raise WakeAckIngressError(
                        "DELIVERED session alias has no canonical target"
                    ) from exc
                if target.target_seat != obligation.declared_target_seat:
                    raise WakeAckIngressError(
                        "DELIVERED target seat does not match the obligation"
                    )
                if target.reasoning_surface != delivered.reasoning_surface:
                    raise WakeAckIngressError(
                        "DELIVERED reasoning surface does not match the target"
                    )

                try:
                    binding = project_runtime_binding(
                        runtime,
                        trusted.target_attempt_id,
                        target,
                        connection=connection,
                    )
                except StateConflict as exc:
                    raise WakeAckIngressError(
                        f"target Attempt/current RuntimeBinding is not exact: {exc}"
                    ) from exc

                if binding.session_alias != delivered.session_alias:
                    raise WakeAckIngressError(
                        "current binding session alias does not match DELIVERED"
                    )
                if binding.reasoning_surface != delivered.reasoning_surface:
                    raise WakeAckIngressError(
                        "current binding reasoning surface does not match DELIVERED"
                    )
                if (
                    binding.binding_id != delivered.binding_id
                    or binding.binding_generation != delivered.binding_generation
                    or trusted.binding_id != binding.binding_id
                    or trusted.binding_generation != binding.binding_generation
                ):
                    raise WakeAckIngressError(
                        "current/trusted binding does not match DELIVERED"
                    )
                if binding.native_handle != trusted.provider_session_id:
                    raise WakeAckIngressError(
                        "trusted provider session does not match current binding"
                    )
                _require_current_process_generation(
                    connection,
                    trusted=trusted,
                    binding_generation=binding.binding_generation,
                )

                identity = (
                    delivered.nudge_id,
                    delivered.destination_digest,
                    delivered.session_alias,
                    delivered.reasoning_surface,
                    delivered.wake_transport,
                    delivered.binding_id,
                    delivered.binding_generation,
                    trusted.target_attempt_id,
                    trusted.process_generation_id,
                    trusted.provider_session_id,
                    trusted.provider_native_turn_id,
                )
                if batch_identity is None:
                    batch_identity = identity
                elif batch_identity != identity:
                    raise WakeAckIngressError(
                        "coalesced Wake ACK claim crosses trusted delivery identity"
                    )

                existing_acks = [
                    record
                    for record in records
                    if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
                ]
                if len(existing_acks) > 1:
                    raise WakeAckIngressError(
                        "Wake ledger contains duplicate acknowledgement records"
                    )
                acknowledged_at = None
                if existing_acks and existing_acks[0].ack is not None:
                    acknowledged_at = existing_acks[0].ack.acknowledged_at
                ack = acknowledge(
                    obligation,
                    trusted=TrustedAckContext(
                        ack_mode=AckMode.REASONING_SESSION,
                        target_seat=obligation.declared_target_seat,
                        session_alias=str(binding.session_alias),
                        reasoning_surface=str(binding.reasoning_surface),
                        binding_id=binding.binding_id,
                        binding_generation=binding.binding_generation,
                        acknowledged_at=acknowledged_at,
                    ),
                    claimed_obligation_ids=claim.obligation_ids,
                    delivered_command_id=delivered.command_id,
                )
                records_to_append.append((ack_record(obligation, ack), None))

            return repository.append_records_on_connection(
                connection,
                tuple(records_to_append),
            )
    except WakeAckIngressError:
        raise
    except (SessionTargetError, WakeLedgerError, StateConflict) as exc:
        raise WakeAckIngressError(f"Wake ACK ingress refused: {exc}") from exc


def _require_current_process_generation(
    connection,
    *,
    trusted: TrustedWorkerWakeAckProjection,
    binding_generation: int,
) -> None:
    """Bind the sealed generation id to the writer validated by RuntimeBinding."""

    rows = connection.execute(
        """
        SELECT g.process_generation_id,g.generation_number,g.provider_session_id,
               e.attempt_id,e.state
        FROM process_generations g
        JOIN harness_session_epochs e
          ON e.session_epoch_id=g.session_epoch_id
        WHERE g.process_generation_id=?
          AND e.attempt_id=?
          AND e.state='CURRENT'
          AND g.executive_writer_held=1
          AND g.ended_at_ms IS NULL
        """,
        (trusted.process_generation_id, trusted.target_attempt_id),
    ).fetchall()
    if len(rows) != 1:
        raise WakeAckIngressError(
            "trusted process generation is not the exact current Executive writer"
        )
    row = rows[0]
    if int(row["generation_number"]) != binding_generation:
        raise WakeAckIngressError(
            "trusted process generation number does not match current binding"
        )
    if row["provider_session_id"] != trusted.provider_session_id:
        raise WakeAckIngressError(
            "trusted process generation provider session does not match"
        )


__all__ = [
    "TrustedWorkerWakeAckProjection",
    "WakeAckClaim",
    "WakeAckIngressError",
    "acknowledge_consumed_wakes",
]
