"""Rootless CREATE selector read over original workspace source-operation events.

This module adds no store, registry, lifecycle, acceptance or authentication.
It selects one principal's own already-retained ``SOURCE_OBSERVED`` CREATE
publication metadata from the incumbent ``SourceOperationEvents`` owner,
through the same identity and immutable-chain checks that owner already
enforces, and retains a canonical snapshot that can later be reread and
compared. Every read is one fixed bounded SELECT; no private body,
compilation, Git, Runtime Job or provider material is ever touched.

A retained candidate is a selector only. It is never publication proof, never
a default and never a source: the canonical DATA owner must separately
qualify each original/current protected Git postimage and READ/latest.
``guard`` is the trusted current-read seam of the qualified integration
factory; it is composition integrity for these reads, never authentication of
public input. Every failure raises the single generic
``PROJECT_DISCOVERY_UNAVAILABLE`` value error and never carries event,
payload or store detail.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from common.workspace_source_operation_contract import validate_lookup
from control_plane.executive_runtime import RuntimeStore, _event_from_row
from control_plane.workspace_source_operations import (
    AGGREGATE,
    SCHEMA,
    SourceOperationEvents,
    _identity,
)

DOCUMENT_SCHEMA = "mastermind.project_creation_candidates.v1"
LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1"
UNAVAILABLE = "PROJECT_DISCOVERY_UNAVAILABLE"

_ACTION = "publish_project_proposal"
_EVENT_TYPE = "PROJECT_SOURCE_SOURCE_OBSERVED"
_KIND = "SOURCE_OBSERVED"
_PHASE = "PUBLICATION"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_MAX_ROW_PAYLOAD_BYTES = 65536
_MAX_SELECTED_METADATA_BYTES = 262144
_MAX_RAW_ROWS = 64
_MAX_WORK_SELECTORS = 8
_READ_LIMIT = _MAX_RAW_ROWS + 1

# One fixed selector: own-principal CREATE publication source observations,
# newest first, read one row past the raw bound so overflow is observable.
_SELECT = (
    "SELECT * FROM events"
    " WHERE aggregate_type=? AND event_type='PROJECT_SOURCE_SOURCE_OBSERVED'"
    " AND json_extract(payload_json,'$.schema')=?"
    " AND json_extract(payload_json,'$.identity.principal_scope')=?"
    " AND json_extract(payload_json,'$.identity.action')='publish_project_proposal'"
    " AND json_extract(payload_json,'$.kind')='SOURCE_OBSERVED'"
    " AND json_extract(payload_json,'$.phase')='PUBLICATION'"
    " ORDER BY event_id DESC LIMIT 65"
)


class _IssuanceSeal:
    """Factory-private issuance seal; the capture factory is the only issuer."""

    __slots__ = ()


_SEAL = _IssuanceSeal()


def _fail():
    raise ValueError(UNAVAILABLE)


def _canonical(value):
    # Byte-identical to the owner's canonical serializer so both digest the
    # same retained metadata identically.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_guard(guard):
    if guard() is not True:
        _fail()


def _require_scope(value):
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        _fail()
    return value


def _row_value(row, name):
    try:
        return row[name]
    except (IndexError, KeyError, TypeError):
        _fail()


@dataclass(frozen=True)
class _Selector:
    """One deduplicated CREATE work selector and its exact retained Event."""

    lookup: dict
    event_id: int
    event_sha256: str


@dataclass(frozen=True)
class _Snapshot:
    """Canonical retained selector metadata; compared exactly on reread."""

    selectors: tuple
    has_more: bool
    high_water: int


def _selector(events, connection, row, principal_scope):
    """Validate one selected row as an original Event of the owner's chain.

    The row is never silently dropped: any unexpected, missing or conflicting
    field in an owned match makes the whole selection unavailable.
    """
    event_id = _row_value(row, "event_id")
    if type(event_id) is not int or event_id <= 0:
        _fail()
    event = _event_from_row(row)
    if (event.event_id != event_id or event.event_type != _EVENT_TYPE
            or event.aggregate_type != AGGREGATE
            or event.job_id is not None or event.attempt_id is not None
            or event.worker_id is not None):
        _fail()
    payload = event.payload
    if type(payload) is not dict:
        _fail()
    identity = payload.get("identity")
    if (payload.get("schema") != SCHEMA or payload.get("kind") != _KIND
            or payload.get("phase") != _PHASE or type(identity) is not dict
            or identity.get("principal_scope") != principal_scope
            or identity.get("action") != _ACTION):
        _fail()
    try:
        candidate = {"schema": LOOKUP_SCHEMA, "action": identity["action"],
                     "request_id": identity["request_id"],
                     "work_ref": identity["work_ref"]}
        lookup = validate_lookup(candidate)
        expected = _identity(lookup, principal_scope)
        chain = events(expected, connection)
    except Exception as error:  # owner grammar/chain failures stay generic
        raise ValueError(UNAVAILABLE) from error
    if expected != identity or event not in chain:
        _fail()
    return _Selector(lookup=dict(lookup), event_id=event.event_id,
                     event_sha256=_digest(payload))


def _select(store, events, principal_scope, guard):
    """Run the one fixed bounded read and build the canonical snapshot."""
    _require_guard(guard)
    with store.read() as connection:
        rows = connection.execute(_SELECT, (AGGREGATE, SCHEMA, principal_scope)).fetchall()
        if type(rows) is not list or len(rows) > _READ_LIMIT:
            _fail()
        selectors = []
        seen = set()
        total = 0
        high_water = 0
        for row in rows:
            payload_json = _row_value(row, "payload_json")
            if type(payload_json) is not str:
                _fail()
            total += len(payload_json.encode("utf-8"))
            if len(payload_json.encode("utf-8")) > _MAX_ROW_PAYLOAD_BYTES or total > _MAX_SELECTED_METADATA_BYTES:
                _fail()
            selector = _selector(events, connection, row, principal_scope)
            if selector.event_id > high_water:
                high_water = selector.event_id
            # Latest valid selector per work: rows arrive newest first, so the
            # first occurrence wins and later originals never displace it.
            if selector.lookup["work_ref"] in seen:
                continue
            seen.add(selector.lookup["work_ref"])
            selectors.append(selector)
    _require_guard(guard)
    has_more = len(rows) > _MAX_RAW_ROWS or len(selectors) > _MAX_WORK_SELECTORS
    return _Snapshot(tuple(selectors[:_MAX_WORK_SELECTORS]), has_more, high_water)


@dataclass(frozen=True, slots=True)
class CreatedProjectCandidates:
    """Factory-issued retained selector snapshot; never caller-mintable.

    The private seal keeps construction out of caller reach, and the captured
    owner, store, method and guard identity keep a later ``check`` from being
    satisfied through any replacement. Holding this object claims only that
    this exact bounded selector read happened: it grants no publication,
    default, source or lifecycle authority and exposes no mutator.
    """

    _seal: Any = field(repr=False, compare=False)
    _owner: SourceOperationEvents = field(repr=False, compare=False)
    _store: RuntimeStore = field(repr=False, compare=False)
    _principal_scope: str = field(repr=False, compare=False)
    _guard: Callable = field(repr=False, compare=False)
    _events: Any = field(repr=False, compare=False)
    _snapshot: _Snapshot = field(repr=False, compare=False)

    def document(self):
        """Return the deeply detached safe selector document."""
        if self._seal is not _SEAL:
            _fail()
        return {"schema": DOCUMENT_SCHEMA,
                "lookups": [dict(selector.lookup) for selector in self._snapshot.selectors],
                "has_more": self._snapshot.has_more,
                "high_water": self._snapshot.high_water}

    def check(self, principal_scope):
        """Reread the same bounded selection and reject any selector change.

        A new matching Event, a changed selected Event, a foreign principal, a
        replaced owner/store/method or a withdrawn guard seam all fail closed.
        """
        if self._seal is not _SEAL:
            _fail()
        _require_scope(principal_scope)
        if principal_scope != self._principal_scope:
            _fail()
        _require_guard(self._guard)
        if (type(self._owner) is not SourceOperationEvents
                or type(self._store) is not RuntimeStore
                or self._owner.store is not self._store
                or self._events != self._owner._events):
            _fail()
        snapshot = _select(self._store, self._events, principal_scope, self._guard)
        _require_guard(self._guard)
        if snapshot != self._snapshot:
            _fail()
        return True


def capture_created_project_candidates(events, principal_scope, *, guard):
    """Read the principal's own retained CREATE selectors; never a proof.

    ``events`` must be the incumbent ``SourceOperationEvents`` owner over an
    actual ``RuntimeStore`` and ``guard`` its trusted current-read seam,
    rechecked before and after every read. The returned snapshot carries the
    captured environment identity so a replacement cannot satisfy ``check``.
    """
    if type(events) is not SourceOperationEvents or not callable(guard):
        _fail()
    _require_scope(principal_scope)
    store = events.store
    if type(store) is not RuntimeStore:
        _fail()
    bound = getattr(events, "_events", None)
    if not callable(bound):
        _fail()
    _require_guard(guard)
    snapshot = _select(store, bound, principal_scope, guard)
    _require_guard(guard)
    return CreatedProjectCandidates(_seal=_SEAL, _owner=events, _store=store,
                                    _principal_scope=principal_scope, _guard=guard,
                                    _events=bound, _snapshot=snapshot)
