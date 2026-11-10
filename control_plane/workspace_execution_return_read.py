"""Existing Workspace permission boundary for the execution-return read.

Read-only, honest projection of the persisted delivery state for ONE attempt.
Given the installed executive store handle and one attempt id, this module
reads the ONE ``EXECUTION_RETURN_DELIVERY`` events row the seam
(:mod:`control_plane.execution_return_wiring`) persists per attempt — keyed by
the deterministic command id ``execution-return:{attempt_id}`` — and projects
it into the closed ``mastermind.execution_return_read/v1`` document:

* **missing event** → the honest unavailable document
  (``EXECUTION_RETURN_NOT_RECORDED``) — never an error, never a zero receipt;
* **present receipt** → the receipt fields VERBATIM (the closed validator
  proves shape, never rewrites a byte), plus the optional persisted ``stage``
  and ``refusal_detail``;
* **original_requester** — the v1.2 block from the admission JOB_CREATED
  provenance, joined when the receipt row's ``job_id`` reaches it through the
  existing read APIs (``list_events`` + ``get_event_by_command_id``, the same
  two-hop chase the seam's ``_admission_provenance`` composes at write time).
  When any hop is not reachable read-only the field is ``null`` — the join is
  honestly not-projected, never guessed;
* **malformed payload / unreadable store** → the typed refusal document
  (``RECEIPT_PAYLOAD_MALFORMED`` / ``STORE_READ_FAILED``) — never a partial
  projection, never a traceback.

This module delivers nothing, retries nothing, owns no listener, queue,
registry, cache or store, and never opens a write transaction: the store is
touched ONLY through its existing read APIs.  It is directly importable and
callable from plain Python (``default_source().read(attempt_id)``) so a
Paperclip module worker can read REAL return state without any HTTP hop.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from common import workspace_execution_return_contract as wire
from common.executive_workspace_contract import error
from control_plane.workspace_read_service import await_owned, permission_stamp

#: Closed payload keys of the seam's receipt row (``_record_receipt`` writes
#: ``{"delivery": receipt, "stage"?: str}``; ``_record_refusal`` writes
#: ``{"delivery": refused-receipt, "refusal_detail": str}``).  Anything else
#: in the row is a foreign shape — typed refusal, never partially served.
_PAYLOAD_KEYS = frozenset({"delivery", "stage", "refusal_detail"})


def _now_iso(clock: Callable[[], datetime]) -> str:
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None:
        now = datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ExistingExecutionReturnSource:
    """Installed read adapter over the incumbent executive event store.

    ``store`` is the installed executive store handle (a ``RuntimeStore`` in
    production — the read-only ``create=False`` accessor is the installed
    default through :func:`default_source`); it is only ever touched through
    ``get_event_by_command_id`` / ``list_events`` — READ-ONLY APIs, never
    ``transaction()``.  ``clock`` defaults to UTC now.  Every attribute is
    installed composition; nothing arrives from HTTP.
    """

    store: Any
    clock: Callable = lambda: datetime.now(timezone.utc)

    def __post_init__(self):
        if any(not callable(getattr(self.store, name, None))
               for name in ("get_event_by_command_id", "list_events")):
            raise ValueError("installed_read_store_required")
        if not callable(self.clock):
            raise ValueError("installed_readers_required")

    # ── the admission-provenance join (read-only mirror of the seam's) ──────

    def _original_requester(self, job_id) -> dict | None:
        """The v1.2 ``original_requester`` block behind this receipt's job.

        Exactly the seam's ``_admission_provenance`` chase, read-only: the
        placement Job's own JOB_CREATED provenance → admission command id →
        admission Job's JOB_CREATED provenance → ``original_requester``.  When
        any hop is not reachable through the existing read APIs the join is
        honestly not-projected (``None``) — never guessed.
        """
        if not job_id:
            return None
        try:
            provenance = None
            for event in self.store.list_events(job_id=str(job_id)):
                if event.event_type != "JOB_CREATED":
                    continue
                payload = event.payload if isinstance(event.payload, dict) else {}
                block = payload.get("provenance")
                provenance = block if isinstance(block, dict) else None
                break
            if not isinstance(provenance, dict):
                return None
            composition = provenance.get("child_placement_composition")
            admission_command_id = None
            if isinstance(composition, dict):
                candidate = composition.get("admission_command_id")
                if isinstance(candidate, str) and candidate:
                    admission_command_id = candidate
            if admission_command_id is None:
                # A directly admitted Job: its own provenance is the record.
                return wire.validate_requester(provenance.get("original_requester"))
            admission_event = self.store.get_event_by_command_id(admission_command_id)
            if admission_event is None or not getattr(admission_event, "job_id", None):
                return None
            for event in self.store.list_events(job_id=str(admission_event.job_id)):
                if event.event_type != "JOB_CREATED":
                    continue
                payload = event.payload if isinstance(event.payload, dict) else {}
                block = payload.get("provenance")
                return wire.validate_requester(
                    block.get("original_requester") if isinstance(block, dict) else None)
            return None
        except Exception:
            # The receipt facts themselves already read; an unreachable join
            # is absence of the join, never a dead read or a guessed block.
            return None

    # ── the read ────────────────────────────────────────────────────────────

    def read(self, attempt_id_value: str) -> dict:
        """Project the persisted delivery state for one attempt."""
        wire.attempt_id(attempt_id_value)
        read_at = _now_iso(self.clock)
        from control_plane.execution_return_wiring import (
            EXECUTION_RETURN_DELIVERY_EVENT,
            execution_return_receipt_command_id,
        )
        try:
            event = self.store.get_event_by_command_id(
                execution_return_receipt_command_id(attempt_id_value))
        except Exception:
            # An unreadable/refusing store is a typed refusal, never a dead
            # read and never an invented receipt.
            return wire.unavailable(attempt_id_value, "STORE_READ_FAILED", read_at)
        if event is None:
            # No receipt row for this attempt: the honest unknown.
            return wire.unavailable(
                attempt_id_value, "EXECUTION_RETURN_NOT_RECORDED", read_at)
        payload = getattr(event, "payload", None)
        if (getattr(event, "event_type", None) != EXECUTION_RETURN_DELIVERY_EVENT
                or not isinstance(payload, dict)
                or not set(payload) <= _PAYLOAD_KEYS):
            return wire.unavailable(
                attempt_id_value, "RECEIPT_PAYLOAD_MALFORMED", read_at)
        stage = payload.get("stage")
        if stage is not None and (type(stage) is not str or not stage
                                  or len(stage) > 64):
            return wire.unavailable(
                attempt_id_value, "RECEIPT_PAYLOAD_MALFORMED", read_at)
        detail = payload.get("refusal_detail")
        if detail is not None and (type(detail) is not str
                                   or len(detail) > 512):
            return wire.unavailable(
                attempt_id_value, "RECEIPT_PAYLOAD_MALFORMED", read_at)
        # The owning job id comes from the persisted event row itself (the
        # seam writes ``job.job_id`` there); a row whose column is not a
        # valid job id degrades to ``null`` job_id — never a poisoned read.
        row_job_id = getattr(event, "job_id", None)
        try:
            row_job_id = wire.job_id(row_job_id) if type(row_job_id) is str else None
        except ValueError:
            row_job_id = None
        requester = self._original_requester(row_job_id)
        try:
            return wire.available(
                attempt_id_value,
                job_id_value=row_job_id,
                delivery=payload.get("delivery"),
                stage=stage,
                refusal_detail=detail,
                original_requester=requester,
                read_at_utc=read_at,
            )
        except ValueError:
            # Malformed receipt (not the closed delivery shape, absent
            # ``delivery`` key, over-cap fields): fail-closed, never partial.
            return wire.unavailable(
                attempt_id_value, "RECEIPT_PAYLOAD_MALFORMED", read_at)


def validated_document(body) -> dict:
    """Envelope validation (the wire's own closed document validator)."""
    return wire.validate_document(body)


def default_source() -> ExistingExecutionReturnSource:
    """The installed default read: the incumbent executive store, read-only.

    Pure composition of the incumbent default root — ``RuntimeStore`` with
    ``create=False`` is the projection's read-only accessor: it never creates
    the database or its directory, never migrates, never chmods, and refuses
    ``transaction()``.  Installs no source by itself — a service that never
    installs one keeps serving the typed ``SOURCE_UNAVAILABLE`` refusal.
    """
    from control_plane.executive_runtime import RuntimeStore
    return ExistingExecutionReturnSource(store=RuntimeStore(create=False))


async def handle_execution_return_frame(owner, frame):
    """Frame handler over the installed source; mirrors the fleet read handler."""
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, authorizer = frame["principal"], owner.authorize
    source = owner._execution_return_source
    try:
        if authorizer(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(authorizer, principal)
        if stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    if type(source) is not ExistingExecutionReturnSource:
        return {"ok": True, "result": wire.unavailable(
            frame["selection"], "SOURCE_UNAVAILABLE",
            _now_iso(lambda: datetime.now(timezone.utc)))}
    task = asyncio.create_task(asyncio.to_thread(source.read, frame["selection"]))
    try:
        document = await await_owned(task)
    except Exception:
        document = wire.unavailable(
            frame["selection"], "SOURCE_UNAVAILABLE",
            _now_iso(lambda: datetime.now(timezone.utc)))
    try:
        if (owner.authorize is not authorizer or authorizer(principal) is not True
                or permission_stamp(authorizer, principal) != stamp):
            return error("access_denied", 403)
        if owner._execution_return_source is not source:
            return {"ok": True, "result": wire.unavailable(
                frame["selection"], "SOURCE_CHANGED",
                _now_iso(lambda: datetime.now(timezone.utc)))}
    except Exception:
        return error("access_denied", 403)
    try:
        validated = wire.validate_document(document)
    except Exception:
        return {"ok": True, "result": wire.unavailable(
            frame["selection"], "SOURCE_UNAVAILABLE",
            _now_iso(lambda: datetime.now(timezone.utc)))}
    return {"ok": True, "result": validated}


__all__ = [
    "ExistingExecutionReturnSource",
    "default_source",
    "handle_execution_return_frame",
    "validated_document",
]
