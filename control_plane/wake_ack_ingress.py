"""Exact-session Wake acknowledgement ingress over existing Executive owners."""
from __future__ import annotations

import dataclasses
import re

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
    WakeLedgerRecord,
    ack_record,
    acknowledge,
    ledger_command_id,
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
            prepared: list[
                tuple[
                    object,
                    WakeLedgerRecord,
                    WakeLedgerRecord | None,
                ]
            ] = []
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
                existing_acks = [
                    record
                    for record in records
                    if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
                ]
                if len(existing_acks) > 1:
                    raise WakeAckIngressError(
                        "Wake ledger contains duplicate acknowledgement records"
                    )
                prepared.append(
                    (
                        obligation,
                        deliveries[0],
                        existing_acks[0] if existing_acks else None,
                    )
                )

            existing_count = sum(existing is not None for _, _, existing in prepared)
            if existing_count:
                if existing_count != len(prepared):
                    raise WakeAckIngressError(
                        "coalesced Wake ACK replay is only partially persisted"
                    )
                replay_records = tuple(
                    (
                        _reconcile_existing_ack(
                            obligation,
                            delivered,
                            existing,
                            claim=claim,
                            trusted=trusted,
                        ),
                        None,
                    )
                    for obligation, delivered, existing in prepared
                    if existing is not None
                )
                return repository.append_records_on_connection(
                    connection,
                    replay_records,
                )

            records_to_append = []
            batch_identity = None
            for obligation, delivered, _existing in prepared:
                if obligation.attempt_id == trusted.target_attempt_id:
                    raise WakeAckIngressError(
                        "target Attempt cannot be inferred from the Wake source Attempt"
                    )
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

                ack = acknowledge(
                    obligation,
                    trusted=TrustedAckContext(
                        ack_mode=AckMode.REASONING_SESSION,
                        target_seat=obligation.declared_target_seat,
                        session_alias=str(binding.session_alias),
                        reasoning_surface=str(binding.reasoning_surface),
                        binding_id=binding.binding_id,
                        binding_generation=binding.binding_generation,
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


def _reconcile_existing_ack(
    obligation,
    delivered: WakeLedgerRecord,
    existing: WakeLedgerRecord,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWorkerWakeAckProjection,
) -> WakeLedgerRecord:
    """Return one exact durable ACK replay without requiring its writer to stay current."""

    ack = existing.ack
    if ack is None or ack.ack_mode is not AckMode.REASONING_SESSION:
        raise WakeAckIngressError(
            "existing acknowledgement is not a reasoning-session ACK"
        )
    if (
        ack.claimed_obligation_ids != claim.obligation_ids
        or ack.target_seat != obligation.declared_target_seat
        or ack.session_alias != delivered.session_alias
        or ack.reasoning_surface != delivered.reasoning_surface
        or ack.binding_id != delivered.binding_id
        or ack.binding_generation != delivered.binding_generation
        or ack.delivered_command_id != delivered.command_id
        or trusted.binding_id != ack.binding_id
        or trusted.binding_generation != ack.binding_generation
    ):
        raise WakeAckIngressError(
            "existing ACK semantic payload conflicts with replay"
        )
    return ack_record(obligation, ack)


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


#: Web-Sol is a fixed single-surface continuation plane; neither value is
#: caller-selectable and no other surface or transport may reach this seam.
WEB_SOL_REASONING_SURFACE = "chatgpt-sol"
WEB_SOL_WAKE_TRANSPORT = "chatgpt-gui"

_WEB_SOL_NATIVE_HANDLE_RE = re.compile(r"^wsx-runtime-[0-9a-f]{16}$")
_WEB_SOL_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclasses.dataclass(frozen=True)
class TrustedWebSolWakeAckProjection:
    """Closed exact-conversation evidence for one Web-Sol parent consumption.

    Shape is validated here; *identity* is not.  These values are only claims
    until :func:`acknowledge_consumed_web_sol_wakes` discriminates every one of
    them against the current runtime-only lease, because a syntactically valid
    handle or digest can still name another conversation or another host life.
    """

    session_alias: str
    reasoning_surface: str
    binding_id: str
    binding_generation: int
    native_handle: str
    runtime_binding_fingerprint: str
    conversation_fingerprint: str
    nudge_id: str
    obligation_ids: tuple[str, ...]
    terminal_ack_trailer: bool

    def __post_init__(self) -> None:
        alias = str(self.session_alias or "").strip()
        if not alias or alias != self.session_alias:
            raise WakeAckIngressError("session_alias is required and must be trimmed")
        if self.reasoning_surface != WEB_SOL_REASONING_SURFACE:
            raise WakeAckIngressError(
                f"Web-Sol ACK reasoning surface must be {WEB_SOL_REASONING_SURFACE}"
            )
        if BINDING_ID_RE.fullmatch(str(self.binding_id or "")) is None:
            raise WakeAckIngressError("binding_id is malformed")
        if (
            type(self.binding_generation) is not int
            or isinstance(self.binding_generation, bool)
            or self.binding_generation < 1
        ):
            raise WakeAckIngressError("binding_generation must be an integer >= 1")
        if _WEB_SOL_NATIVE_HANDLE_RE.fullmatch(str(self.native_handle or "")) is None:
            raise WakeAckIngressError("native_handle is not a Web-Sol runtime handle")
        for name in ("runtime_binding_fingerprint", "conversation_fingerprint"):
            if _WEB_SOL_DIGEST_RE.fullmatch(str(getattr(self, name) or "")) is None:
                raise WakeAckIngressError(f"{name} is not a canonical digest")
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
            raise WakeAckIngressError(
                "trusted projection requires a terminal ACK trailer"
            )


def _require_exact_web_sol_lease(
    lease: object,
    *,
    trusted: TrustedWebSolWakeAckProjection,
) -> None:
    """Discriminate the trusted projection against the current live lease.

    Web-Sol's accepted lease is runtime-only, detached and never persisted, so
    unlike the worker seam there is no durable RuntimeBinding to project.  The
    caller therefore supplies the current lease as the live proof.  The lease
    self-proves its own runtime-binding fingerprint at construction, so exact
    equality against it refuses valid-but-wrong native handles, runtime-binding
    fingerprints and conversation fingerprints, and refuses any binding minted
    by a different native-host life.  Nothing here is written anywhere.
    """

    if lease is None:
        raise WakeAckIngressError(
            "Web-Sol ACK first persistence requires the current RuntimeBinding lease"
        )
    binding = getattr(lease, "runtime_binding", None)
    target = getattr(lease, "target", None)
    fingerprint = getattr(lease, "runtime_binding_fingerprint", None)
    if binding is None or target is None or not isinstance(fingerprint, str):
        raise WakeAckIngressError(
            "Web-Sol ACK proof is not an accepted RuntimeBinding lease"
        )
    conversation_fingerprint = getattr(target, "conversation_fingerprint", None)
    if not isinstance(conversation_fingerprint, str):
        raise WakeAckIngressError(
            "Web-Sol ACK lease carries no exact conversation fingerprint"
        )
    if getattr(binding, "reasoning_surface", None) != WEB_SOL_REASONING_SURFACE:
        raise WakeAckIngressError(
            "Web-Sol ACK lease is not bound to the Web-Sol reasoning surface"
        )
    if (
        getattr(binding, "session_alias", None) != trusted.session_alias
        or getattr(binding, "binding_id", None) != trusted.binding_id
        or getattr(binding, "binding_generation", None) != trusted.binding_generation
    ):
        raise WakeAckIngressError(
            "trusted Web-Sol binding is not the current RuntimeBinding lease"
        )
    if getattr(binding, "native_handle", None) != trusted.native_handle:
        raise WakeAckIngressError(
            "trusted native handle is not the current Web-Sol host life"
        )
    if fingerprint != trusted.runtime_binding_fingerprint:
        raise WakeAckIngressError(
            "trusted runtime-binding fingerprint is not the current lease fingerprint"
        )
    if conversation_fingerprint != trusted.conversation_fingerprint:
        raise WakeAckIngressError(
            "trusted conversation fingerprint is not the exact leased conversation"
        )


def acknowledge_consumed_web_sol_wakes(
    runtime: Runtime,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWebSolWakeAckProjection,
    lease: object | None = None,
) -> tuple[PersistedWakeEvent, ...]:
    """Atomically ACK one complete Web-Sol nudge group as the exact bound parent.

    ``lease`` is the current :class:`WebSolRuntimeBindingLease` and is required
    for any first persistence.  An already-persisted identical ACK still replays
    idempotently without it, so a later host life can re-report a consumption it
    already durably recorded without being able to mint a new one.
    """

    if not isinstance(runtime, Runtime):
        raise WakeAckIngressError("ACK ingress requires an Executive Runtime")
    if not isinstance(claim, WakeAckClaim):
        raise WakeAckIngressError("ACK ingress requires a WakeAckClaim")
    if not isinstance(trusted, TrustedWebSolWakeAckProjection):
        raise WakeAckIngressError(
            "ACK ingress requires a trusted Web-Sol exact-session projection"
        )
    if trusted.obligation_ids != claim.obligation_ids:
        raise WakeAckIngressError(
            "trusted projection obligation ids do not match the claim"
        )

    repository = WakeLedgerRepository(runtime)
    try:
        with runtime.store.transaction() as connection:
            prepared: list[
                tuple[object, WakeLedgerRecord, WakeLedgerRecord | None]
            ] = []
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
                existing_acks = [
                    record
                    for record in records
                    if record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
                ]
                if len(existing_acks) > 1:
                    raise WakeAckIngressError(
                        "Wake ledger contains duplicate acknowledgement records"
                    )
                prepared.append(
                    (
                        obligation,
                        deliveries[0],
                        existing_acks[0] if existing_acks else None,
                    )
                )

            existing_count = sum(existing is not None for _, _, existing in prepared)
            if existing_count:
                if existing_count != len(prepared):
                    raise WakeAckIngressError(
                        "coalesced Wake ACK replay is only partially persisted"
                    )
                replay_records = tuple(
                    (
                        _reconcile_existing_web_sol_ack(
                            obligation,
                            delivered,
                            existing,
                            claim=claim,
                            trusted=trusted,
                        ),
                        None,
                    )
                    for obligation, delivered, existing in prepared
                    if existing is not None
                )
                return repository.append_records_on_connection(
                    connection, replay_records
                )

            _require_exact_web_sol_lease(lease, trusted=trusted)

            group = tuple(prepared[0][1].nudge_attempt_command_ids)
            expected_members = set()
            records_to_append = []
            for obligation, delivered, _existing in prepared:
                if tuple(delivered.nudge_attempt_command_ids) != group:
                    raise WakeAckIngressError(
                        "coalesced Wake ACK claim crosses more than one nudge group"
                    )
                if delivered.wake_transport != WEB_SOL_WAKE_TRANSPORT:
                    raise WakeAckIngressError(
                        "DELIVERED wake transport is not "
                        f"{WEB_SOL_WAKE_TRANSPORT}"
                    )
                if delivered.reasoning_surface != WEB_SOL_REASONING_SURFACE:
                    raise WakeAckIngressError(
                        "DELIVERED reasoning surface is not "
                        f"{WEB_SOL_REASONING_SURFACE}"
                    )
                if (
                    delivered.session_alias != trusted.session_alias
                    or delivered.binding_id != trusted.binding_id
                    or delivered.binding_generation != trusted.binding_generation
                ):
                    raise WakeAckIngressError(
                        "current/trusted binding does not match DELIVERED"
                    )
                expected_members.add(
                    ledger_command_id(
                        obligation.obligation_id,
                        LedgerPhase.DELIVERY_ATTEMPT,
                        attempt_n=delivered.attempt_n,
                    )
                )

                ack = acknowledge(
                    obligation,
                    trusted=TrustedAckContext(
                        ack_mode=AckMode.REASONING_SESSION,
                        target_seat=obligation.declared_target_seat,
                        session_alias=str(delivered.session_alias),
                        reasoning_surface=str(delivered.reasoning_surface),
                        binding_id=str(delivered.binding_id),
                        binding_generation=int(delivered.binding_generation),
                    ),
                    claimed_obligation_ids=claim.obligation_ids,
                    delivered_command_id=delivered.command_id,
                )
                records_to_append.append((ack_record(obligation, ack), None))

            if not group or expected_members != set(group):
                raise WakeAckIngressError(
                    "Web-Sol ACK must cover the complete nudge group exactly once"
                )

            return repository.append_records_on_connection(
                connection, tuple(records_to_append)
            )
    except WakeAckIngressError:
        raise
    except (SessionTargetError, WakeLedgerError, StateConflict) as exc:
        raise WakeAckIngressError(f"Wake ACK ingress refused: {exc}") from exc


def _reconcile_existing_web_sol_ack(
    obligation,
    delivered: WakeLedgerRecord,
    existing: WakeLedgerRecord,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWebSolWakeAckProjection,
) -> WakeLedgerRecord:
    """Return one exact durable ACK replay without a still-current lease."""

    ack = existing.ack
    if ack is None or ack.ack_mode is not AckMode.REASONING_SESSION:
        raise WakeAckIngressError(
            "existing acknowledgement is not a reasoning-session ACK"
        )
    if (
        ack.claimed_obligation_ids != claim.obligation_ids
        or ack.target_seat != obligation.declared_target_seat
        or ack.session_alias != delivered.session_alias
        or ack.reasoning_surface != delivered.reasoning_surface
        or ack.binding_id != delivered.binding_id
        or ack.binding_generation != delivered.binding_generation
        or ack.delivered_command_id != delivered.command_id
        or trusted.session_alias != ack.session_alias
        or trusted.binding_id != ack.binding_id
        or trusted.binding_generation != ack.binding_generation
    ):
        raise WakeAckIngressError("existing ACK semantic payload conflicts with replay")
    return ack_record(obligation, ack)


__all__ = [
    "TrustedWebSolWakeAckProjection",
    "TrustedWorkerWakeAckProjection",
    "WakeAckClaim",
    "WakeAckIngressError",
    "WEB_SOL_REASONING_SURFACE",
    "WEB_SOL_WAKE_TRANSPORT",
    "acknowledge_consumed_wakes",
    "acknowledge_consumed_web_sol_wakes",
]
