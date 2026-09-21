"""Wake ledger persistence over the existing Executive OS events table.

This is not a store.  Writes use ``RuntimeStore.transaction()`` /
``append_event()``.  There is no Wake table, queue, or mutable state row.
"""
from __future__ import annotations

import dataclasses
from typing import Sequence

from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
from control_plane.executive_runtime import Event, Runtime, RuntimeStore, StateConflict
from control_plane.wake_events import WakeObligation
from control_plane.wake_ledger import (
    ATTEMPT_PHASES,
    LedgerPhase,
    WAKE_AGGREGATE_TYPE,
    WAKE_EVENT_ACTOR,
    WakeLedgerError,
    WakeLedgerRecord,
    assert_causal,
    event_payload_for,
    parse_ledger_record,
    payloads_equivalent,
    wake_record_from_event,
)


@dataclasses.dataclass(frozen=True)
class PersistedWakeEvent:
    event: Event
    record: WakeLedgerRecord
    obligation: WakeObligation | None = None
    inserted: bool = False


class WakeLedgerRepository:
    """Narrow adapter.  One Executive OS events stream per obligation."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self.store: RuntimeStore = runtime.store

    def get_by_command_id(self, command_id: str) -> PersistedWakeEvent | None:
        event = self.runtime.events.get_event_by_command_id(command_id)
        if event is None:
            return None
        return self._hydrate(event)

    def list_records(self, obligation_id: str) -> tuple[PersistedWakeEvent, ...]:
        return self.list_wake_events(aggregate_id=obligation_id)

    def list_wake_events(
        self, *, aggregate_id: str | None = None
    ) -> tuple[PersistedWakeEvent, ...]:
        events = self.runtime.events.list_events(
            aggregate_type=WAKE_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
        )
        hydrated: list[PersistedWakeEvent] = []
        for event in events:
            hydrated.append(self._hydrate(event))
        if aggregate_id is not None:
            assert_causal(tuple(item.record for item in hydrated))
        return tuple(hydrated)

    def append_record(
        self,
        record: WakeLedgerRecord,
        *,
        obligation: WakeObligation | None = None,
        actor: str = WAKE_EVENT_ACTOR,
    ) -> PersistedWakeEvent:
        rows = self.append_records_atomic(
            ((record, obligation),),
            actor=actor,
        )
        return rows[0]

    def append_records_atomic(
        self,
        items: Sequence[tuple[WakeLedgerRecord, WakeObligation | None]],
        *,
        actor: str = WAKE_EVENT_ACTOR,
    ) -> tuple[PersistedWakeEvent, ...]:
        with self.store.transaction() as connection:
            return self.append_records_on_connection(
                connection,
                items,
                actor=actor,
            )

    def list_ledger_records_on_connection(
        self,
        connection,
        obligation_id: str,
    ) -> tuple[WakeLedgerRecord, ...]:
        if not connection.in_transaction:
            raise StateConflict(
                "Wake ledger connection read requires an active transaction"
            )
        return tuple(self._records_on_connection(connection, obligation_id))

    def append_records_on_connection(
        self,
        connection,
        items: Sequence[tuple[WakeLedgerRecord, WakeObligation | None]],
        *,
        actor: str = WAKE_EVENT_ACTOR,
    ) -> tuple[PersistedWakeEvent, ...]:
        if not connection.in_transaction:
            raise StateConflict(
                "Wake ledger connection append requires an active transaction"
            )
        if not items:
            raise WakeLedgerError("append_records_atomic requires at least one record")
        proposed_by_oid: dict[str, list[WakeLedgerRecord]] = {}
        proposed_physical_sources: list[PhysicalDialogueSourceIdentity] = []
        for record, _obligation in items:
            parse_ledger_record(record)
            oid = record.command_id.split(":", 1)[0]
            proposed_by_oid.setdefault(oid, []).append(record)
            if (
                record.phase is LedgerPhase.WAKE_REQUESTED
                and record.physical_source is not None
            ):
                physical = record.physical_source
                self.assert_physical_source_request_available_on_connection(
                    connection,
                    physical,
                    obligation_id=oid,
                )
                for prior in proposed_physical_sources:
                    if (
                        _physical_source_scope(prior)
                        == _physical_source_scope(physical)
                        and prior.digest != physical.digest
                    ):
                        raise WakeLedgerError(
                            "physical source already requested with a different identity"
                        )
                proposed_physical_sources.append(physical)
        for oid, proposed in proposed_by_oid.items():
            existing = self._records_on_connection(connection, oid)
            existing_commands = {item.command_id for item in existing}
            combined = list(existing) + [
                record
                for record in proposed
                if record.command_id not in existing_commands
            ]
            assert_causal(combined)
        out = []
        for record, obligation in items:
            out.append(
                self._append_one(
                    connection,
                    record,
                    obligation=obligation,
                    actor=actor,
                )
            )
        return tuple(out)

    def assert_physical_source_request_available_on_connection(
        self,
        connection,
        physical_source: PhysicalDialogueSourceIdentity,
        *,
        obligation_id: str,
    ) -> None:
        """Fence one physical predecessor against a second logical request."""

        if not connection.in_transaction:
            raise StateConflict(
                "physical source collision read requires an active transaction"
            )
        if type(physical_source) is not PhysicalDialogueSourceIdentity:
            raise WakeLedgerError("physical source identity is malformed")
        wanted_scope = _physical_source_scope(physical_source)
        rows = connection.execute(
            "SELECT command_id FROM events "
            "WHERE aggregate_type=? AND event_type=? "
            "AND json_extract(payload_json,'$.physical_source.workspace_id')=? "
            "AND json_extract(payload_json,'$.physical_source.channel_id')=? "
            "AND json_extract(payload_json,'$.physical_source.thread_ts')=? "
            "AND json_extract(payload_json,'$.physical_source.parent_fingerprint')=? "
            "AND json_extract(payload_json,'$.physical_source.operation_key')=? "
            "AND json_extract(payload_json,'$.physical_source.predecessor_message_key')=? "
            "AND json_extract(payload_json,'$.physical_source.target_seat')=? "
            "ORDER BY event_id LIMIT 2",
            (
                WAKE_AGGREGATE_TYPE,
                LedgerPhase.WAKE_REQUESTED.value,
                *wanted_scope,
            ),
        ).fetchall()
        for (command_id,) in rows:
            event = self.store.get_event_by_command_id(
                str(command_id), connection=connection
            )
            if event is None:
                continue
            prior = self._hydrate(event).record.physical_source
            if prior is None or _physical_source_scope(prior) != wanted_scope:
                continue
            if (
                prior.obligation_id != obligation_id
                or prior.digest != physical_source.digest
            ):
                raise WakeLedgerError(
                    "physical source already requested with a different identity"
                )

    def _append_one(
        self,
        connection,
        record: WakeLedgerRecord,
        *,
        obligation: WakeObligation | None,
        actor: str,
    ) -> PersistedWakeEvent:
        payload = event_payload_for(record, obligation=obligation)
        oid = record.command_id.split(":", 1)[0]
        job_id, attempt_id = _correlation(obligation, record)
        existing = self.store.get_event_by_command_id(
            record.command_id, connection=connection
        )
        if existing is not None:
            self._assert_replay(existing, record, payload, job_id, attempt_id)
            return self._hydrate(existing)
        self.store.append_event(
            connection,
            aggregate_type=WAKE_AGGREGATE_TYPE,
            aggregate_id=oid,
            event_type=record.phase.value,
            actor=actor,
            job_id=job_id,
            attempt_id=attempt_id,
            payload=payload,
            command_id=record.command_id,
        )
        written = self.store.get_event_by_command_id(
            record.command_id, connection=connection
        )
        if written is None:
            raise StateConflict("wake event did not persist")
        return dataclasses.replace(self._hydrate(written), inserted=True)

    def _assert_replay(
        self,
        existing: Event,
        record: WakeLedgerRecord,
        payload: dict[str, object],
        job_id: str | None,
        attempt_id: str | None,
    ) -> None:
        oid = record.command_id.split(":", 1)[0]
        if existing.aggregate_type != WAKE_AGGREGATE_TYPE:
            raise StateConflict(
                "command_id collision: existing event is not a wake aggregate"
            )
        if existing.aggregate_id != oid:
            raise StateConflict(
                "command_id collision: existing event aggregate_id disagrees"
            )
        if existing.event_type != record.phase.value:
            raise StateConflict(
                "command_id collision: existing event_type disagrees"
            )
        if existing.job_id != job_id or existing.attempt_id != attempt_id:
            raise StateConflict(
                "command_id collision: existing correlation disagrees"
            )
        if not payloads_equivalent(existing.payload, payload, phase=record.phase):
            raise StateConflict(
                "command_id collision: existing payload disagrees"
            )

    def _hydrate(self, event: Event) -> PersistedWakeEvent:
        if event.command_id.startswith("WAKE-") and event.aggregate_type != WAKE_AGGREGATE_TYPE:
            raise StateConflict(
                "foreign Executive event stole a Wake command id"
            )
        record = wake_record_from_event(event)
        obligation = None
        if record.phase is LedgerPhase.WAKE_REQUESTED:
            obligation = record.obligation
        return PersistedWakeEvent(event=event, record=record, obligation=obligation)

    def _records_on_connection(self, connection, obligation_id: str) -> list[WakeLedgerRecord]:
        rows = connection.execute(
            "SELECT command_id FROM events "
            "WHERE aggregate_type=? AND aggregate_id=? ORDER BY event_id",
            (WAKE_AGGREGATE_TYPE, obligation_id),
        ).fetchall()
        records: list[WakeLedgerRecord] = []
        for (command_id,) in rows:
            event = self.store.get_event_by_command_id(command_id, connection=connection)
            if event is None:
                continue
            records.append(self._hydrate(event).record)
        return records


def _correlation(
    obligation: WakeObligation | None, record: WakeLedgerRecord
) -> tuple[str | None, str | None]:
    if obligation is not None:
        attempt = obligation.attempt_id
        if attempt and attempt.startswith("ATT-"):
            return obligation.job_id, attempt
        return obligation.job_id, None
    if record.phase in ATTEMPT_PHASES:
        return None, None
    return None, None


def _physical_source_scope(
    physical_source: PhysicalDialogueSourceIdentity,
) -> tuple[str, str, str, str, str, str, str]:
    return (
        physical_source.workspace_id,
        physical_source.channel_id,
        physical_source.thread_ts,
        physical_source.parent_fingerprint,
        physical_source.operation_key,
        physical_source.predecessor_message_key,
        physical_source.target_seat,
    )


__all__ = [
    "PersistedWakeEvent",
    "WakeLedgerRepository",
]
