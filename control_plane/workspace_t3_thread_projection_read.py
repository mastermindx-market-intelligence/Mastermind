"""Read-only, honest T3 thread-list projection over the company adapter store.

This is a READ producer only.  It projects the durable T3 threads the company
adapter launched into ONE closed document
(``mastermind.t3_thread_projection_list.v1``) so the UI lane can feed its
``t3ThreadProjection`` host source from a real read path.  It launches,
interrupts, sends to, retries or bridges nothing, owns no listener, queue,
registry, cache or store, and writes no state: the incumbent adapter store is
opened ``mode=ro`` and the environment fact is a caller-installed attested
observation, never a defaulted or invented id.

Honesty rules (binding):

* **environment** — projected ONLY from one persisted/attested
  ``mastermind.t3_environment_observation/v1`` fact (validated through the
  incumbent :func:`T3EnvironmentObservation.from_dict`).  The environment is
  row-level constant for this host, so it is read once.  If no environment fact
  source is installed/readable, the document is ``UNAVAILABLE`` with
  ``T3_ENVIRONMENT_SOURCE_UNAVAILABLE`` naming the missing source — an
  environment id is never defaulted.
* **runState** — derived ONLY from the observed native status through the
  adapter's own vocabulary (mirrors ``_T3_STATUS_MAP`` in
  ``control_plane/t3_execution_adapter.py``): the adapter's non-terminal launch
  classes (``preparing``/``queued``/``starting``/``running``/``waiting``/
  ``in_progress``) are a live run → ``running``; every terminal class
  (``succeeded``/``completed``/``failed``/``cancelled``/``interrupted``/
  ``rolled_back``/``timed_out``) has settled → ``idle``; an unmapped or absent
  status is ``unknown`` (a missing status is never ``idle``).  ``blocked`` is
  admitted by the vocabulary but never emitted: no persisted adapter status
  honestly distinguishes an approval-blocked run from any other.  Note that the
  adapter's own ``_run_status`` falls back to ``RUNNING`` for an unmapped
  status; this read deliberately does NOT copy that fallback — asserting a live
  run from absent evidence would be invented state, so ``unknown`` is served.
* **title** — the persisted launch-envelope ``title`` when present, else null.
  A present but wire-invalid title (>240 chars, wrong type) is malformed
  evidence → typed refusal, never a silent truncation.
* **lastActivity** — the persisted receipt ``created_at`` when it is a valid
  ISO-8601 instant, else null (never a guess).
* **prLink** — the persisted receipt ``link`` ONLY when it is an https URL,
  else null.
* **repository** — the adapter store persists no attested ``owner/name``
  repository fact (receipt/envelope/spec carry thread/project/workspace ids,
  not a repository), so this field is always null rather than inferred.
* **companyManaged** — every row in this store was launched by the company T3
  adapter (the table exists solely to durably record those launches), so it is
  true for every projected row.
* **effect-unknown** — a row with a launch intent but no receipt has no honest
  thread identity (the launch may or may not have minted a thread); it is
  OMITTED from this thread-list projection.  Its effect-unknown state is owned
  by the per-attempt fleet read, not duplicated here.

A missing adapter-state file is an honestly EMPTY store (``AVAILABLE`` with
``threads: []``); a corrupt/unreadable store is a typed refusal document; an
over-cap (>64 distinct threads) list is refused (``THREADS_OVER_CAP``) rather
than silently truncated — never a partial projection.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from common import workspace_t3_thread_projection_contract as wire
from common.executive_workspace_contract import error
from control_plane.t3_environment_projection import (
    T3EnvironmentObservation,
    T3ProjectionError,
)
from control_plane.workspace_read_service import await_owned, permission_stamp

_ADAPTER_TABLE = "t3_adapter_runs"
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}\Z")
_STATUS_RE = re.compile(r"[A-Za-z0-9_ -]{1,32}\Z")

#: Native status → UI runState, derived from the adapter's own status
#: vocabulary (``control_plane/t3_execution_adapter.py`` ``_T3_STATUS_MAP``).
#: Non-terminal launch classes are a live run; every terminal class is settled
#: and therefore idle.  Anything else (unmapped/absent) is handled as unknown.
_RUN_STATE_BY_NATIVE = {
    "preparing": "running",
    "queued": "running",
    "starting": "running",
    "running": "running",
    "waiting": "running",
    "in_progress": "running",
    "succeeded": "idle",
    "completed": "idle",
    "failed": "idle",
    "cancelled": "idle",
    "canceled": "idle",
    "interrupted": "idle",
    "rolled_back": "idle",
    "timed_out": "idle",
    "timeout": "idle",
}


class T3ThreadProjectionError(ValueError):
    """A closed, typed projection refusal (never carries evidence content)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise T3ThreadProjectionError(code)


def _bounded(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse(code)
    return value


# ── durable adapter-state read (mode=ro, mirrors the fleet reader shape) ─────


@dataclasses.dataclass(frozen=True)
class ThreadStateRow:
    """The closed slice of one durable ``t3_adapter_runs`` row this view reads.

    ``thread_id``/``native_status``/``created_at``/``link`` come from the
    persisted launch receipt (with the terminal status preferring
    ``result_ref_json.native_status`` when a result was ledgered); ``title``
    from the persisted intent's launch envelope.  A row with an intent but no
    receipt is the adapter's effect-unknown zone: ``thread_id`` stays None and
    the row is omitted from this projection.
    """

    run_id: str
    thread_id: str | None = None
    title: str | None = None
    native_status: str | None = None
    created_at: str | None = None
    link: str | None = None
    has_receipt: bool = False


def _row_json(raw: Any) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if type(raw) is not str:
        _refuse("ADAPTER_ROW_MALFORMED")
    try:
        parsed = json.loads(raw)
    except ValueError:
        _refuse("ADAPTER_ROW_MALFORMED")
    if not isinstance(parsed, dict):
        _refuse("ADAPTER_ROW_MALFORMED")
    return parsed


def _optional_string(value: Any, maximum: int) -> str | None:
    """Return a trimmed non-empty string within ``maximum``, else None/refuse.

    ``None``/``""`` mean absent.  A present value of the wrong type or over the
    wire cap is malformed evidence: the wire cannot carry it truthfully, and a
    silent truncation would falsify it, so it is refused.
    """
    if value is None or value == "":
        return None
    if type(value) is not str or len(value) > maximum:
        _refuse("ADAPTER_ROW_MALFORMED")
    return value


def _normalize_row(
    run_id_raw: Any, intent_json: Any, receipt_json: Any, result_ref_json: Any
) -> ThreadStateRow:
    run_id = _bounded(run_id_raw, _RUN_ID_RE, "ADAPTER_ROW_MALFORMED")
    intent = _row_json(intent_json)
    receipt = _row_json(receipt_json)
    result_ref = _row_json(result_ref_json)

    title: str | None = None
    if intent is not None:
        envelope = intent.get("envelope")
        if envelope is not None:
            if not isinstance(envelope, dict):
                _refuse("ADAPTER_ROW_MALFORMED")
            title = _optional_string(envelope.get("title"), 240)

    thread_id: str | None = None
    native_status: str | None = None
    created_at: str | None = None
    link: str | None = None
    if receipt is not None:
        raw_thread = receipt.get("thread_id")
        if raw_thread not in (None, ""):
            # A receipt thread id the frozen wire grammar cannot represent is a
            # genuine contract violation, not a row to silently omit.
            if not _wire_thread_id(raw_thread):
                _refuse("ADAPTER_ROW_MALFORMED")
            thread_id = raw_thread
        raw_status = receipt.get("status")
        if raw_status not in (None, ""):
            native_status = _bounded(raw_status, _STATUS_RE, "ADAPTER_ROW_MALFORMED")
        created_at = _optional_string(receipt.get("created_at"), 40)
        link = _optional_string(receipt.get("link"), 512)

    # A ledgered terminal status is the most current observed status.
    if result_ref is not None:
        terminal = result_ref.get("native_status")
        if terminal not in (None, ""):
            native_status = _bounded(terminal, _STATUS_RE, "ADAPTER_ROW_MALFORMED")

    return ThreadStateRow(
        run_id=run_id,
        thread_id=thread_id,
        title=title,
        native_status=native_status,
        created_at=created_at,
        link=link,
        has_receipt=receipt is not None,
    )


def _wire_thread_id(value: Any) -> bool:
    return type(value) is str and wire.THREAD_ID.fullmatch(value) is not None


def read_thread_state_rows(
    path: str | Path, *, connection: sqlite3.Connection | None = None
) -> tuple[ThreadStateRow, ...]:
    """Read every thread row from the durable adapter state, READ-ONLY.

    Opens the existing ``t3_adapter_runs`` table with a ``mode=ro`` URI (never
    the writable store class, whose construction writes schema).  A missing
    file is an honestly empty store; a file that is not the adapter's schema is
    a typed refusal, as is any malformed row.
    """
    opened = False
    if connection is None:
        file_path = Path(path)
        if not file_path.exists():
            return ()
        uri = f"file:{quote(str(file_path))}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            opened = True
        except sqlite3.Error:
            _refuse("ADAPTER_STATE_UNREADABLE")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if _ADAPTER_TABLE not in tables:
            _refuse("ADAPTER_STATE_SCHEMA_UNKNOWN")
        cursor = connection.execute(
            "SELECT run_id, intent_json, receipt_json, result_ref_json"
            " FROM " + _ADAPTER_TABLE + " ORDER BY rowid"
        )
        rows: list[ThreadStateRow] = []
        for record in cursor.fetchall():
            rows.append(_normalize_row(*record))
        return tuple(rows)
    except sqlite3.Error:
        _refuse("ADAPTER_STATE_UNREADABLE")
    finally:
        if opened and connection is not None:
            connection.close()


# ── pure projection ─────────────────────────────────────────────────────────


def map_run_state(native_status: Any) -> str:
    """Map one native status onto the closed UI runState vocabulary."""
    if type(native_status) is not str:
        return "unknown"
    return _RUN_STATE_BY_NATIVE.get(native_status.strip().lower(), "unknown")


def _valid_iso(value: Any) -> str | None:
    if type(value) is not str:
        return None
    try:
        wire._iso(value)
    except ValueError:
        return None
    return value


def _valid_https(value: Any) -> str | None:
    if type(value) is not str:
        return None
    try:
        wire._https(value)
    except ValueError:
        return None
    return value


def project_threads(
    rows: tuple[ThreadStateRow, ...] | list[ThreadStateRow], environment_id: str
) -> list[dict[str, Any]]:
    """Project durable rows into closed projection rows for one environment.

    Effect-unknown rows (intent, no receipt → no thread id) are omitted; a
    thread projected more than once (e.g. an adopted replay) collapses to its
    first observation.  An over-cap list is refused, never truncated.
    """
    wire.environment_id(environment_id)
    projected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not row.has_receipt or row.thread_id is None:
            continue
        if row.thread_id in seen:
            continue
        seen.add(row.thread_id)
        projected.append({
            "threadId": row.thread_id,
            "environment": environment_id,
            "title": row.title,
            "runState": map_run_state(row.native_status),
            "lastActivity": _valid_iso(row.created_at),
            "prLink": _valid_https(row.link),
            # No persisted attested repository fact exists in this store.
            "repository": None,
            # Every row in the company adapter store is a company launch.
            "companyManaged": True,
        })
    if len(projected) > wire.MAX_THREADS:
        _refuse("THREADS_OVER_CAP")
    return projected


# ── installed composition + frame handler ───────────────────────────────────


class _EnvironmentUnavailable(Exception):
    """The installed environment fact source is absent or unreadable."""


@dataclasses.dataclass(frozen=True)
class ExistingT3ThreadProjectionSource:
    """Installed read adapter over the incumbent durable adapter state.

    ``adapter_state_path`` is the host-selected durable state file (the
    production default is ``default_t3_adapter_state_path()``); it is opened
    READ-ONLY (``mode=ro``) and a missing file is an honestly empty store.
    ``environment_path`` is the installed attested
    ``mastermind.t3_environment_observation/v1`` fact file; when it is absent,
    unreadable or invalid the projection is honestly ``UNAVAILABLE`` naming the
    missing source — an environment id is never invented or defaulted.  Every
    path is installed composition; none arrives from HTTP.
    """

    adapter_state_path: Path
    environment_path: Path | None = None

    def __post_init__(self) -> None:
        if (not isinstance(self.adapter_state_path, Path)
                or not self.adapter_state_path.is_absolute()):
            raise ValueError("installed_absolute_adapter_state_path_required")
        if self.environment_path is not None and (
            not isinstance(self.environment_path, Path)
            or not self.environment_path.is_absolute()
        ):
            raise ValueError("installed_absolute_environment_path_required")

    def _environment_id(self) -> str:
        if self.environment_path is None:
            raise _EnvironmentUnavailable
        try:
            raw = self.environment_path.read_text(encoding="utf-8")
            document = json.loads(raw)
        except (OSError, ValueError):
            raise _EnvironmentUnavailable from None
        try:
            observation = T3EnvironmentObservation.from_dict(document)
        except (T3ProjectionError, TypeError, ValueError):
            raise _EnvironmentUnavailable from None
        return observation.environment_id

    def read(self) -> dict:
        """Compose the thread-list document; typed refusals never partial rows."""
        try:
            environment_id = self._environment_id()
        except _EnvironmentUnavailable:
            return wire.unavailable("T3_ENVIRONMENT_SOURCE_UNAVAILABLE")
        try:
            rows = read_thread_state_rows(self.adapter_state_path)
            threads = project_threads(rows, environment_id)
        except T3ThreadProjectionError as exc:
            return wire.unavailable(exc.code)
        return wire.available(threads)


def default_source(environment_path: Path | None = None) -> ExistingT3ThreadProjectionSource:
    """The installed default read: incumbent durable adapter state (+ observation).

    Pure composition of the A3-owned default state path (``mode=ro`` open,
    missing file honestly empty).  ``environment_path`` is the installed
    attested environment fact; omitting it keeps the read honestly
    ``UNAVAILABLE`` — the source is not invented for it.
    """
    from control_plane.t3_execution_adapter import default_t3_adapter_state_path
    return ExistingT3ThreadProjectionSource(
        adapter_state_path=Path(default_t3_adapter_state_path()),
        environment_path=environment_path if environment_path is None
        else Path(environment_path),
    )


async def handle_t3_thread_projection_frame(owner, frame):
    """Frame handler over the installed source; mirrors the fleet read handler."""
    try:
        wire.validate_frame(frame)
    except (TypeError, ValueError):
        return error("invalid_input", 400)
    principal, authorizer = frame["principal"], owner.authorize
    source = owner._t3_thread_projection_source
    try:
        if authorizer(principal) is not True:
            return error("access_denied", 403)
        stamp = permission_stamp(authorizer, principal)
        if stamp is None:
            return error("access_denied", 403)
    except Exception:
        return error("access_denied", 403)
    if type(source) is not ExistingT3ThreadProjectionSource:
        return {"ok": True, "result": wire.unavailable("SOURCE_UNAVAILABLE")}
    task = asyncio.create_task(asyncio.to_thread(source.read))
    try:
        document = await await_owned(task)
    except Exception:
        document = wire.unavailable("SOURCE_UNAVAILABLE")
    try:
        if (owner.authorize is not authorizer or authorizer(principal) is not True
                or permission_stamp(authorizer, principal) != stamp):
            return error("access_denied", 403)
        if owner._t3_thread_projection_source is not source:
            return {"ok": True, "result": wire.unavailable("SOURCE_CHANGED")}
    except Exception:
        return error("access_denied", 403)
    try:
        validated = wire.validate_document(document)
    except Exception:
        return {"ok": True, "result": wire.unavailable("SOURCE_UNAVAILABLE")}
    return {"ok": True, "result": validated}


__all__ = [
    "ExistingT3ThreadProjectionSource",
    "T3ThreadProjectionError",
    "ThreadStateRow",
    "default_source",
    "handle_t3_thread_projection_frame",
    "map_run_state",
    "project_threads",
    "read_thread_state_rows",
]
