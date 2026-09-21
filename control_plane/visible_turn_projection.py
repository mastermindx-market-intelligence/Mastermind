"""In-memory, bounded hot-window projection of explicitly visible turn items.

``VisibleItem.source_item_id`` is the stable identity of the source item and
``source_sequence`` carries its display position. ``publication_sequence`` is
instead a monotonically advancing change order: a partial-to-completed update is
an UPSERT of that same source item and emits another publication sequence to an
existing reader. A normal short page advances the returned cursor until more
retained items are available; only a retained gap or publication-epoch change
reports ``RESYNC_REQUIRED`` (an actual cursor reset).

Viewer grants are internal, projection-scoped reader handles. They are not user
or authentication tokens and confer no permission to send anything to the
provider. When the last viewer for a turn is revoked, its bounded in-memory
hot-window state is discarded; it is not history.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Mapping


MAX_ITEMS_PER_TURN = 256
MAX_ITEM_BYTES = 16_384
MAX_RETAINED_TURNS = 4
MAX_RETAINED_TURN_BYTES = 1024 * 1024
MAX_ENCODED_READ_BYTES = 512 * 1024
MAX_READ_ITEMS = 64
MAX_PREBIND_ITEMS = 8
MAX_PREBIND_BYTES = 64 * 1024
PREBIND_TTL_SECONDS = 2.0
MAX_VIEWERS = 2

_ID_BYTES = 18
_MAX_ID_LENGTH = 256
_MAX_REASON_LENGTH = 128
_CURSOR_JSON_BYTES = frozenset(
    b'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-",:{}[] '
)


class ProjectionError(ValueError):
    """A projection request or input violated the frozen read-model contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class TurnKey:
    attempt_id: str
    session_epoch_id: str
    process_generation_id: str
    generation_number: int
    worker_id: str
    local_turn_id: str
    native_turn_id: str


@dataclass(frozen=True, slots=True)
class VisibleItem:
    source_item_id: str
    source_sequence: int
    state: str
    text: str
    byte_length: int
    publication_sequence: int


@dataclass(frozen=True, slots=True)
class GapRecord:
    from_publication_sequence: int
    to_publication_sequence: int
    reason: str


@dataclass(frozen=True, slots=True)
class ReadResult:
    items: tuple[VisibleItem, ...]
    next_cursor: str
    gaps: tuple[GapRecord, ...]
    terminal: bool
    publication_epoch: str
    retained_scope: tuple[str, str]
    resync_required: bool


@dataclass(frozen=True, slots=True)
class _TurnRecord:
    projection_id: str
    publication_epoch: str
    key: TurnKey
    items: tuple[VisibleItem, ...]
    gaps: tuple[GapRecord, ...]
    terminal: bool
    retained_bytes: int
    next_publication_sequence: int


@dataclass(frozen=True, slots=True)
class PrebindItem:
    source_item_id: str
    source_sequence: int
    state: str
    text: str
    byte_length: int


@dataclass
class _Prebind:
    request_id: int
    armed_at: float
    items: list[PrebindItem] = field(default_factory=list)
    retained_bytes: int = 0
    gap_from: int = 1

    def record(self, reason: str) -> GapRecord:
        return GapRecord(self.gap_from, max(self.gap_from, len(self.items)), reason)


@dataclass(frozen=True, slots=True)
class _Grant:
    key: TurnKey
    viewer_id: str
    binding: tuple[str, str, str, str] | None = None
    state: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class _Cursor:
    projection_id: str
    publication_epoch: str
    publication_sequence: int


def _identity(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_ID_LENGTH:
        raise ProjectionError("TURN_NOT_BOUND", f"{name} is invalid")
    return value


def _reason(value: str) -> str:
    return value[:_MAX_REASON_LENGTH]


def _decode_cursor(value: object) -> _Cursor:
    if not isinstance(value, str) or not value:
        raise ProjectionError("CURSOR_STALE", "cursor is missing")
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
        if not decoded or any(byte not in _CURSOR_JSON_BYTES for byte in decoded):
            raise ValueError("cursor is not canonical JSON")
        raw = json.loads(decoded)
        projection_id = raw["p"]
        publication_epoch = raw["e"]
        publication_sequence = raw["s"]
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
        raise ProjectionError("CURSOR_STALE", "cursor is invalid") from None
    if (
        not isinstance(projection_id, str)
        or not isinstance(publication_epoch, str)
        or type(publication_sequence) is not int
        or publication_sequence < 0
    ):
        raise ProjectionError("CURSOR_STALE", "cursor fields are invalid")
    return _Cursor(projection_id, publication_epoch, publication_sequence)


def _encode_cursor(record: _TurnRecord, sequence: int) -> str:
    payload = json.dumps(
        {
            "p": record.projection_id,
            "e": record.publication_epoch,
            "s": sequence,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


class VisibleTurnProjection:
    """Thread-safe projection owner; performs no controller or network I/O."""

    def __init__(self, *, clock=time.monotonic) -> None:
        self._lock = threading.RLock()
        self._turns: dict[str, _TurnRecord] = {}
        self._prebind: _Prebind | None = None
        self._grants: dict[str, _Grant] = {}
        self._viewers_by_turn: dict[TurnKey, set[str]] = {}
        self._refusals: list[tuple[TurnKey | None, str, float]] = []
        self._parser_gaps: list[GapRecord] = []
        self._clock = clock

    def attach(self) -> None:
        """Compatibility lifecycle hook for an App Server publication owner."""

    def detach(self) -> None:
        with self._lock:
            self._prebind = None

    def arm_prebind(self, request_id: int) -> None:
        with self._lock:
            self._prebind = _Prebind(request_id, self._clock())

    def prebind(
        self,
        request_id: int,
        *,
        method: object,
        params: object,
        native_turn_id: object = None,
    ) -> None:
        with self._lock:
            buffer = self._prebind
            if buffer is None or buffer.request_id != request_id:
                return
            if (
                method == "turn/completed"
                and isinstance(native_turn_id, str)
                and native_turn_id
            ):
                return
            try:
                item = _parse_visible_item(method, params)
            except ProjectionError:
                buffer.items.append(
                    PrebindItem("", buffer.gap_from + len(buffer.items), "gap", "", 0)
                )
                self._drop_prebind_locked("parser_failure")
                return
            if item is None:
                return
            if len(buffer.items) >= MAX_PREBIND_ITEMS:
                self._drop_prebind_locked("prebind_item_overflow")
                return
            item_bytes = item.byte_length
            if buffer.retained_bytes + item_bytes > MAX_PREBIND_BYTES:
                self._drop_prebind_locked("prebind_byte_overflow")
                return
            if self._clock() - buffer.armed_at >= PREBIND_TTL_SECONDS:
                self._drop_prebind_locked("prebind_expired")
                return
            buffer.items.append(item)
            buffer.retained_bytes += item_bytes

    def prebind_frame(
        self,
        request_id: int,
        *,
        method: object,
        params: object,
    ) -> None:
        self.prebind(request_id, method=method, params=params)

    def publish_demultiplexed(self, request_id: int, *, payload: object) -> None:
        del request_id
        if not isinstance(payload, Mapping):
            return
        method = payload.get("method")
        params = payload.get("params")
        native_turn_id = None
        if isinstance(params, Mapping) and any(
            method == candidate
            for candidate in ("item/updated", "item/completed")
        ):
            native_turn_id = params.get("turnId")
        elif method == "turn/completed":
            turn = params.get("turn") if isinstance(params, Mapping) else None
            native_turn_id = (
                turn.get("id") if isinstance(turn, Mapping) else None
            )
        if not isinstance(native_turn_id, str) or not native_turn_id:
            return
        with self._lock:
            key = next(
                (
                    candidate
                    for candidate in self._viewers_by_turn
                    if candidate.native_turn_id == native_turn_id
                ),
                None,
            )
        if key is not None:
            self.publish(
                key,
                method=method,
                params=params,
                native_turn_id=native_turn_id,
            )

    def record_parser_failure(self) -> None:
        # Parser failures intentionally do not touch controller transport state.
        self._parser_gaps.append(GapRecord(0, 0, "parser_failure"))

    def parser_gaps(self) -> tuple[GapRecord, ...]:
        with self._lock:
            return tuple(self._parser_gaps)

    def drop_prebind(self, reason: str) -> GapRecord | None:
        with self._lock:
            return self._drop_prebind_locked(reason)

    def drop_expired_prebind(self) -> GapRecord | None:
        with self._lock:
            buffer = self._prebind
            if buffer is not None and self._clock() - buffer.armed_at >= PREBIND_TTL_SECONDS:
                return self._drop_prebind_locked("prebind_timeout")
            return None

    def active_prebind_request_id(self) -> int | None:
        with self._lock:
            return self._prebind.request_id if self._prebind is not None else None

    def commit_prebind(
        self,
        request_id: int,
        key: TurnKey,
        *,
        native_turn_id: str,
    ) -> GapRecord | None:
        with self._lock:
            buffer = self._prebind
            self._prebind = None
            if buffer is None:
                return None
            if (
                buffer.request_id != request_id
                or key.native_turn_id != native_turn_id
            ):
                return buffer.record("prebind_identity_mismatch")
            record = self._create_turn_locked(key)
            for item in buffer.items:
                record = self._turns[record.key.native_turn_id]
                self._append_locked(record, item, gap_on_bounds=False)
            return None

    def publish(
        self,
        key: TurnKey,
        *,
        method: object,
        params: object,
        native_turn_id: object = None,
    ) -> None:
        with self._lock:
            if not self._viewers_by_turn.get(key):
                return
            record = self._turns.get(_identity(key.native_turn_id, "native turn"))
            if record is None or record.key != key:
                return
            if (
                method == "turn/completed"
                and isinstance(native_turn_id, str)
                and native_turn_id == key.native_turn_id
            ):
                self._turns[record.key.native_turn_id] = _TurnRecord(
                    record.projection_id,
                    record.publication_epoch,
                    record.key,
                    record.items,
                    record.gaps,
                    True,
                    record.retained_bytes,
                    record.next_publication_sequence,
                )
                return
            try:
                item = _parse_visible_item(method, params)
                if item is None:
                    return
                self._append_locked(record, item, gap_on_bounds=True)
            except ProjectionError:
                self._add_gap_locked(record, _reason("parser_failure"))

    def mint_grant(self, key: TurnKey) -> str:
        with self._lock:
            existing = self._viewers_by_turn.get(key)
            if existing is None:
                existing = set()
                self._viewers_by_turn[key] = existing
            if len(existing) >= MAX_VIEWERS:
                raise ProjectionError("OVER_BUDGET", "turn viewer budget is full")
            grant = str(uuid.uuid4())
            self._grants[grant] = _Grant(key, grant)
            existing.add(grant)
            self._create_turn_locked(key)
            return grant

    @staticmethod
    def _observer_binding(operation_id, profile_digest, permission_digest, viewer_binding_digest):
        values = (operation_id, profile_digest, permission_digest, viewer_binding_digest)
        if (not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 256
                or any(not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None
                       for v in values[1:])):
            raise ProjectionError("OBSERVER_CONFLICT", "OBSERVER_CONFLICT")
        return values

    def _observer_entry(self, key, binding):
        for handle, grant in self._grants.items():
            if grant.binding is not None and grant.binding[0] == binding[0]:
                if grant.key != key or grant.binding != binding:
                    raise ProjectionError("OBSERVER_CONFLICT", "OBSERVER_CONFLICT")
                return handle, grant
        return None, None

    @staticmethod
    def _observer_wire(handle, grant):
        return {"status": grant.state if grant else "ABSENT",
                "reader_grant": handle if grant and grant.state == "ACTIVE" else None,
                "turn_key": asdict(grant.key) if grant else None,
                "grant_generation": handle if grant else None}

    def observer_status(self, key, **binding):
        bound = self._observer_binding(**binding)
        with self._lock:
            handle, grant = self._observer_entry(key, bound)
            if grant and grant.state == "ACTIVE":
                record = self._turns.get(key.native_turn_id)
                if record is None or record.key != key:
                    grant = replace(grant, state="INVALIDATED")
                    self._grants[handle] = grant
            return self._observer_wire(handle, grant)

    @staticmethod
    def _observer_identity(key: TurnKey) -> tuple[str, str, str, str]:
        return (
            key.attempt_id,
            key.session_epoch_id,
            key.process_generation_id,
            key.local_turn_id,
        )

    def _observer_entry_by_binding(
        self, identity: tuple[str, str, str, str], binding: tuple[str, str, str, str]
    ) -> tuple[str | None, _Grant | None]:
        """Exact existing-registry lookup without a caller-supplied key.

        Used only when no active operator run can reconstruct the native turn
        key: the key comes from the already-bound grant itself. A binding whose
        operation matches but whose full tuple or turn identity does not is a
        conflict, never a miss; nothing is minted or guessed on absence."""
        for handle, grant in self._grants.items():
            if grant.binding is None or grant.binding[0] != binding[0]:
                continue
            if grant.binding != binding or self._observer_identity(grant.key) != identity:
                raise ProjectionError("OBSERVER_CONFLICT", "OBSERVER_CONFLICT")
            return handle, grant
        return None, None

    def observer_status_by_binding(
        self, identity: tuple[str, str, str, str], **binding
    ):
        bound = self._observer_binding(**binding)
        with self._lock:
            handle, grant = self._observer_entry_by_binding(identity, bound)
            if grant and grant.state == "ACTIVE":
                record = self._turns.get(grant.key.native_turn_id)
                if record is None or record.key != grant.key:
                    grant = replace(grant, state="INVALIDATED")
                    self._grants[handle] = grant
            return self._observer_wire(handle, grant)

    def revoke_observer_by_binding(
        self, identity: tuple[str, str, str, str], **binding
    ):
        bound = self._observer_binding(**binding)
        with self._lock:
            handle, grant = self._observer_entry_by_binding(identity, bound)
            if grant and grant.state == "ACTIVE":
                self.revoke_grant(handle)
                grant = self._grants.get(handle)
            return self._observer_wire(handle, grant)

    def enroll_observer(self, key, **binding):
        bound = self._observer_binding(**binding)
        with self._lock:
            handle, existing = self._observer_entry(key, bound)
            if existing is not None:
                return self.observer_status(key, **binding)
            # Tombstones stay in the existing registry until process restart.
            # Never evict them and accidentally turn a replay into enrollment.
            if sum(g.binding is not None for g in self._grants.values()) >= 128:
                raise ProjectionError("OVER_BUDGET", "observer operation budget is full")
            handle = self.mint_grant(key)
            self._grants[handle] = replace(self._grants[handle], binding=bound)
            return self._observer_wire(handle, self._grants[handle])

    def revoke_observer(self, key, **binding):
        bound = self._observer_binding(**binding)
        with self._lock:
            handle, grant = self._observer_entry(key, bound)
            if grant and grant.state == "ACTIVE":
                self.revoke_grant(handle)
            return self.observer_status(key, **binding)

    def check_observer_binding(self, reader_grant, binding):
        with self._lock:
            grant = self._grants.get(reader_grant)
            if grant is None or grant.state != "ACTIVE":
                return False
            if grant.binding is None:
                return not binding
            try:
                return grant.binding == self._observer_binding(**binding)
            except (TypeError, ProjectionError):
                return False

    def revoke_grant(self, reader_grant: str) -> None:
        with self._lock:
            grant = self._grants.get(reader_grant)
            if grant is None:
                return
            if grant.binding is None:
                self._grants.pop(reader_grant, None)
            else:
                self._grants[reader_grant] = replace(grant, state="REVOKED")
            viewers = self._viewers_by_turn.get(grant.key)
            if viewers is not None:
                viewers.discard(reader_grant)
                if not viewers:
                    self._viewers_by_turn.pop(grant.key, None)
                    # A late old-generation revoke cannot remove a newer turn.
                    record = self._turns.get(grant.key.native_turn_id)
                    if record is not None and record.key == grant.key:
                        self._turns.pop(grant.key.native_turn_id, None)
                        self._prebind = None

    def check_grant(self, reader_grant: object) -> TurnKey | None:
        if not isinstance(reader_grant, str):
            return None
        with self._lock:
            grant = self._grants.get(reader_grant)
            return grant.key if grant is not None and grant.state == "ACTIVE" else None

    def read(
        self,
        key: TurnKey,
        *,
        reader_grant: object,
        cursor: object,
        max_items: object,
    ) -> ReadResult:
        grant_key = self.check_grant(reader_grant)
        if grant_key is None:
            self._refuse(key, "READER_REVOKED")
        if grant_key != key:
            self._refuse(key, "GENERATION_INVALID")
        if type(max_items) is not int or not 1 <= max_items <= MAX_READ_ITEMS:
            self._refuse(key, "OVER_BUDGET")
        decoded = _decode_cursor(cursor) if cursor is not None else None
        with self._lock:
            live_grant = (
                self._grants.get(reader_grant)
                if isinstance(reader_grant, str) else None
            )
            if live_grant is None or live_grant.state != "ACTIVE" or live_grant.key != key:
                self._refuse(key, "READER_REVOKED")
            record = self._turns.get(key.native_turn_id)
            if record is None or record.key != key:
                self._refuse(key, "TURN_NOT_BOUND")
            if decoded is not None and decoded.projection_id != record.projection_id:
                self._refuse(key, "CURSOR_STALE")
            if decoded is not None and decoded.publication_epoch != record.publication_epoch:
                self._refuse(key, "RESYNC_REQUIRED")
            sequence = 0 if decoded is None else decoded.publication_sequence
            if sequence > record.next_publication_sequence:
                self._refuse(key, "CURSOR_OUT_OF_RANGE")
            eligible_pub = sorted(
                (item for item in record.items if item.publication_sequence > sequence),
                key=lambda i: i.publication_sequence,
            )
            gaps = [
                gap
                for gap in record.gaps
                if gap.to_publication_sequence > sequence
            ]
            page: tuple[VisibleItem, ...] = ()
            last_served_pub = sequence
            for index in range(min(max_items, len(eligible_pub))):
                candidate_pub = tuple(eligible_pub[: index + 1])
                candidate_source = tuple(
                    sorted(
                        candidate_pub,
                        key=lambda i: (i.source_sequence, i.publication_sequence),
                    )
                )
                candidate_result = ReadResult(
                    candidate_source,
                    _encode_cursor(record, candidate_pub[-1].publication_sequence),
                    tuple(gaps),
                    record.terminal,
                    record.publication_epoch,
                    (record.key.process_generation_id, record.key.native_turn_id),
                    False,
                )
                encoded_size = len(
                    json.dumps(
                        asdict(candidate_result), separators=(",", ":")
                    ).encode("utf-8")
                )
                if encoded_size > MAX_ENCODED_READ_BYTES:
                    break
                page = candidate_source
                last_served_pub = candidate_pub[-1].publication_sequence
            if eligible_pub and not page:
                self._refuse(key, "OVER_BUDGET")
            return ReadResult(
                page,
                _encode_cursor(record, last_served_pub),
                tuple(gaps),
                record.terminal,
                record.publication_epoch,
                (record.key.process_generation_id, record.key.native_turn_id),
                bool(gaps),
            )

    def invalidate_generation(self, key: TurnKey, reason: str = "generation_invalid") -> None:
        with self._lock:
            # Native turn IDs may repeat across epochs; compare the full key.
            record = self._turns.get(key.native_turn_id)
            if record is not None and record.key == key:
                self._turns.pop(key.native_turn_id, None)
                self._prebind = None
            self._viewers_by_turn.pop(key, None)
            for handle, grant in list(self._grants.items()):
                if grant.key == key:
                    if grant.binding is not None:
                        self._grants[handle] = replace(grant, state="INVALIDATED")

    def refusal_receipts(self) -> tuple[tuple[str, str, int], ...]:
        with self._lock:
            return tuple(
                (
                    receipt_key.to_wire()
                    if hasattr(receipt_key, "to_wire")
                    else str(receipt_key),
                    code,
                    int(timestamp),
                )
                for receipt_key, code, timestamp in self._refusals
            )

    def _refuse(self, key: TurnKey, code: str) -> None:
        with self._lock:
            self._refusals.append((key, code, self._clock()))
        raise ProjectionError(code, code)

    def _create_turn_locked(
        self, key: TurnKey, *, reuse_empty: bool = False
    ) -> _TurnRecord:
        record = self._turns.get(key.native_turn_id)
        if record is not None and record.key == key:
            return record
        identity_material = json.dumps(
            {
                "attempt": key.attempt_id,
                "epoch": key.session_epoch_id,
                "generation": key.process_generation_id,
                "generation_number": key.generation_number,
                "worker": key.worker_id,
                "local_turn": key.local_turn_id,
                "native_turn": key.native_turn_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        projection_id = hashlib.sha256(identity_material).hexdigest()
        publication_epoch = str(uuid.uuid4())
        record = _TurnRecord(
            projection_id,
            publication_epoch,
            key,
            (),
            (),
            False,
            0,
            0,
        )
        self._turns[key.native_turn_id] = record
        while len(self._turns) > MAX_RETAINED_TURNS:
            self._turns.pop(next(iter(self._turns)), None)
        return record

    def _append_locked(
        self,
        record: _TurnRecord,
        item: PrebindItem,
        *,
        gap_on_bounds: bool,
    ) -> None:
        if item.state == "gap":
            self._add_gap_locked(record, _reason("prebind_dropped"))
            return
        if item.byte_length > MAX_ITEM_BYTES:
            if gap_on_bounds:
                self._add_gap_locked(record, "item_byte_overflow")
            return
        replacement = None
        if item.state in {"partial", "completed"}:
            replacement = next(
                (
                    existing
                    for existing in reversed(record.items)
                    if existing.source_item_id == item.source_item_id
                ),
                None,
            )
        if replacement is not None:
            if (
                item.state == "partial"
                and replacement.state == "completed"
            ):
                return
            identical = (
                item.state == replacement.state
                and item.source_sequence == replacement.source_sequence
                and item.text == replacement.text
                and item.byte_length == replacement.byte_length
            )
            if identical:
                return
            sequence = record.next_publication_sequence + 1
            updated = VisibleItem(
                item.source_item_id,
                item.source_sequence,
                item.state,
                item.text,
                item.byte_length,
                sequence,
            )
            items = tuple(
                updated if existing is replacement else existing for existing in record.items
            )
            retained = record.retained_bytes - replacement.byte_length + item.byte_length
            new_record = _TurnRecord(
                record.projection_id,
                record.publication_epoch,
                record.key,
                items,
                record.gaps,
                record.terminal,
                retained,
                sequence,
            )
            # Eviction — same retention contract as the append branch below. Drop from
            # the FRONT (oldest first), record one ``turn_byte_overflow`` GapRecord per
            # eviction. The item just written by THIS replacement (the ``updated``
            # VisibleItem) is NEVER the one evicted: if it would be the oldest, evict
            # the next-oldest instead, and if it is the ONLY retained item, stop
            # rather than silently dropping the final.
            while (
                new_record.retained_bytes > MAX_RETAINED_TURN_BYTES
                and new_record.items
            ):
                items_list = list(new_record.items)
                if items_list[0] is updated and len(items_list) > 1:
                    evict_index = 1
                elif items_list[0] is updated:
                    break
                else:
                    evict_index = 0
                oldest = items_list[evict_index]
                new_items = tuple(
                    items_list[:evict_index] + items_list[evict_index + 1:]
                )
                new_retained = new_record.retained_bytes - oldest.byte_length
                new_gaps = (*new_record.gaps, GapRecord(
                    sequence,
                    sequence,
                    _reason("turn_byte_overflow"),
                ))
                new_record = _TurnRecord(
                    new_record.projection_id,
                    new_record.publication_epoch,
                    new_record.key,
                    new_items,
                    new_gaps,
                    new_record.terminal,
                    new_retained,
                    sequence,
                )
            self._turns[record.key.native_turn_id] = new_record
            return
        sequence = record.next_publication_sequence + 1
        visible = VisibleItem(
            item.source_item_id,
            item.source_sequence,
            item.state,
            item.text,
            item.byte_length,
            sequence,
        )
        retained = record.retained_bytes + item.byte_length
        while len(record.items) >= MAX_ITEMS_PER_TURN and record.items:
            oldest = record.items[0]
            retained -= oldest.byte_length
            record = self._turns[record.key.native_turn_id] = _TurnRecord(
                record.projection_id,
                record.publication_epoch,
                record.key,
                record.items[1:],
                record.gaps,
                record.terminal,
                retained,
                record.next_publication_sequence,
            )
            self._add_gap_locked(record, "turn_item_overflow")
        while retained > MAX_RETAINED_TURN_BYTES and record.items:
            oldest = record.items[0]
            retained -= oldest.byte_length
            record = self._turns[record.key.native_turn_id] = _TurnRecord(
                record.projection_id,
                record.publication_epoch,
                record.key,
                record.items[1:],
                record.gaps,
                record.terminal,
                retained,
                record.next_publication_sequence,
            )
            self._add_gap_locked(record, "turn_byte_overflow")
        record = self._turns[record.key.native_turn_id]
        self._turns[record.key.native_turn_id] = _TurnRecord(
            record.projection_id,
            record.publication_epoch,
            record.key,
            (*record.items, visible),
            record.gaps,
            record.terminal,
            record.retained_bytes + item.byte_length,
            sequence,
        )

    def _add_gap_locked(self, record: _TurnRecord, reason: str) -> None:
        from_sequence = record.next_publication_sequence + 1
        to_sequence = from_sequence
        self._turns[record.key.native_turn_id] = _TurnRecord(
            record.projection_id,
            record.publication_epoch,
            record.key,
            record.items,
            (*record.gaps, GapRecord(from_sequence, to_sequence, _reason(reason))),
            record.terminal,
            record.retained_bytes,
            to_sequence,
        )

    def _drop_prebind_locked(self, reason: str) -> GapRecord | None:
        buffer = self._prebind
        self._prebind = None
        return buffer.record(_reason(reason)) if buffer is not None else None


def _parse_visible_item(method: object, params: object) -> PrebindItem | None:
    if method not in {"item/updated", "item/completed"} or not isinstance(params, Mapping):
        return None
    item = params.get("item")
    if not isinstance(item, Mapping) or item.get("type") != "agentMessage":
        return None
    source_item_id = _identity(item.get("id"), "source item identity")
    source_sequence = item.get("sequence")
    text = item.get("text")
    if (
        type(source_sequence) is not int
        or source_sequence < 0
        or not isinstance(text, str)
    ):
        raise ProjectionError("parser_failure", "visible item fields are unsupported")
    byte_length = len(text.encode("utf-8"))
    if byte_length > MAX_ITEM_BYTES:
        raise ProjectionError("parser_failure", "visible item exceeds byte bound")
    state = "partial" if method == "item/updated" else "completed"
    return PrebindItem(source_item_id, source_sequence, state, text, byte_length)


__all__ = [
    "GapRecord",
    "MAX_READ_ITEMS",
    "MAX_VIEWERS",
    "PrebindItem",
    "ProjectionError",
    "ReadResult",
    "TurnKey",
    "VisibleItem",
    "VisibleTurnProjection",
]
