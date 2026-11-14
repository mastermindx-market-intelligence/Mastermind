"""Existing Workspace permission boundary for the per-attempt T3 fleet read.

Pure composition of Director G's closed projection: one attempt id → one
read-only adapter-state open (``mode=ro``), one bounded process census, one
``project_attempt`` → ``validate_attempt``-checked ``mastermind.t3_attempt_fleet/v1``
document.  This module never launches, interrupts, kills or sends to any T3
thread or process, owns no listener, queue, registry or store, and creates no
new facts: unreadable or corrupt evidence is a typed refusal document, never a
partial projection or a traceback.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from common import workspace_t3_attempt_fleet_contract as wire
from common.executive_workspace_contract import error
from control_plane.t3_attempt_fleet_projection import (
    T3AttemptFleetError,
    project_attempt,
    read_adapter_attempt_rows,
    validate_attempt,
)
from control_plane.t3_process_census import take_census
from control_plane.workspace_read_service import await_owned, permission_stamp


@dataclass(frozen=True)
class ExistingT3AttemptFleetSource:
    """Installed read adapter over the incumbent durable adapter state.

    ``adapter_state_path`` is the host-selected durable state file (the
    production default is ``default_t3_adapter_state_path()``); the file is
    opened READ-ONLY (``mode=ro``) and a missing file is an honestly empty
    store, never an error.  ``census`` defaults to one bounded live ``ps``
    observation per read; ``clock`` defaults to UTC now.  Every callable is
    installed composition — no path, callable or option arrives from HTTP.
    """

    adapter_state_path: Path
    census: Callable = take_census
    clock: Callable = lambda: datetime.now(timezone.utc)

    def __post_init__(self):
        if not isinstance(self.adapter_state_path, Path) or not self.adapter_state_path.is_absolute():
            raise ValueError("installed_absolute_adapter_state_path_required")
        if any(not callable(value) for value in (self.census, self.clock)):
            raise ValueError("installed_readers_required")

    def read(self, attempt_id: str) -> dict:
        """Compose one attempt projection; unknowns stay unknown, refusals stay typed."""
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            now = datetime.now(timezone.utc)
        now = now.astimezone(timezone.utc)
        try:
            rows = read_adapter_attempt_rows(self.adapter_state_path)
            try:
                census = self.census()
            except Exception:
                # A failed observation is absent evidence (note CENSUS_ABSENT),
                # never a fabricated census and never a dead read.
                census = None
            view = project_attempt(
                attempt_id,
                rows=[row for row in rows if row.run_id == attempt_id],
                all_rows=rows,
                census=census,
                clock=now,
            )
            attempt = validate_attempt(view.to_dict())
        except T3AttemptFleetError as exc:
            # Fail-closed, honest refusal: no partial projection of corrupt or
            # unreadable evidence; the typed code carries no evidence content.
            return wire.refusal_document(exc.code)
        notes = []
        if not rows:
            notes.append("ADAPTER_STATE_EMPTY")
        if census is None:
            notes.append("CENSUS_ABSENT")
        return {
            "schema": wire.FLEET_SCHEMA,
            "evaluated_at_utc": now.isoformat(timespec="seconds"),
            "attempts": [attempt],
            "notes": notes,
        }


def validated_document(body) -> dict:
    """Envelope validation plus the projection's own per-attempt validator."""
    return wire.validate_document(body, attempt_validator=validate_attempt)


def default_source() -> ExistingT3AttemptFleetSource:
    """The installed default read: incumbent durable adapter state + live census.

    Pure composition of the A3-owned default path (``mode=ro`` open, missing
    file honestly empty); installs no source by itself — a service that never
    installs one keeps serving the typed SOURCE_UNAVAILABLE refusal.
    """
    from control_plane.t3_execution_adapter import default_t3_adapter_state_path
    return ExistingT3AttemptFleetSource(
        adapter_state_path=Path(default_t3_adapter_state_path())
    )


async def handle_t3_attempt_fleet_frame(owner, frame):
    """Frame handler over the installed source; mirrors the capacity fabric read."""
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, authorizer = frame["principal"], owner.authorize
    source = owner._t3_attempt_fleet_source
    try:
        if authorizer(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(authorizer, principal)
        if stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    if type(source) is not ExistingT3AttemptFleetSource:
        return {"ok": True, "result": wire.refusal_document("SOURCE_UNAVAILABLE")}
    task = asyncio.create_task(asyncio.to_thread(source.read, frame["selection"]))
    try:
        document = await await_owned(task)
    except Exception:
        document = wire.refusal_document("SOURCE_UNAVAILABLE")
    try:
        if (owner.authorize is not authorizer or authorizer(principal) is not True
                or permission_stamp(authorizer, principal) != stamp):
            return error("access_denied", 403)
        if owner._t3_attempt_fleet_source is not source:
            return {"ok": True, "result": wire.refusal_document("SOURCE_CHANGED")}
    except Exception:
        return error("access_denied", 403)
    try:
        validated = wire.validate_document(document, attempt_validator=validate_attempt)
    except Exception:
        return {"ok": True, "result": wire.refusal_document("SOURCE_UNAVAILABLE")}
    return {"ok": True, "result": validated}
