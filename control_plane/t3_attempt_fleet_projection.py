"""Closed, read-only per-attempt T3 fleet projection (``mastermind.t3_attempt_fleet/v1``).

This module joins four already-collected facts per company attempt and reports
the DONE_WHEN-row-3 invariant honestly: **exactly one qualified T3 thread and
one selected harness/provider process per attempt, with no duplicate direct
DSH/Codex launcher beside the T3-owned run**.

Inputs (all injectable; the projection performs no I/O of its own):

(a) adapter state rows for an attempt — normalized from the durable
    ``t3_adapter_runs`` table owned by ``control_plane/t3_execution_adapter.py``
    (read through :func:`read_adapter_attempt_rows`, a READ-ONLY ``mode=ro``
    connection; that store's public API intentionally has no read-only open —
    its SQLite class writes schema at construction — which is recorded here as
    the API gap this helper fills).  Rows may be absent.
(b) a T3 thread read result through an injected port (may be unknown or
    unreachable — unknown, never guessed).
(c) a process census snapshot (``control_plane/t3_process_census.py``; may be
    absent or stale — then unknown, never healthy).
(d) a clock.

Honesty rules (same family as the environment projection and WO-04 thermal):

* ``UNKNOWN`` never collapses to healthy: a missing harness is UNKNOWN, not a
  violation (the provider may run the harness remotely, or it already exited);
  a stale or absent census makes every process-side fact UNKNOWN.
* ``PROVEN`` is only ever derived from readable evidence: one durable receipt
  thread for the (key, namespace), or exactly one correlated harness-process
  tree root under a fresh census.
* ``VIOLATED`` needs positive evidence: two distinct threads minted under one
  (key, namespace), or two harness trees correlated with one thread's
  workspace.
* Malformed evidence is a typed refusal, never a silent skip or a guess.

The idempotency identity is ``(client_request_id, request_namespace)`` — the
live proof (Rev 5 finding 1) showed the same ``clientRequestId`` under two
OAuth clients minting two DIFFERENT threads, so the namespace is part of the
identity: the same key under a different namespace is a different attempt,
never a violation.

This module owns no launch, interrupt, send, retry, queue or registry; it is a
projection.  Pure standard library.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from control_plane.t3_process_census import (
    CENSUS_SCHEMA,
    CensusProcess,
    CensusSnapshot,
    Classification,
    KIND_CODEX_CLI,
    KIND_DSH_DIRECT,
    KIND_OTHER,
    KIND_T3_HARNESS,
    PROCESS_KINDS,
    T3ProcessCensusError,
    census_from_dict,
    classify,
)

FLEET_SCHEMA = "mastermind.t3_attempt_fleet/v1"

#: Evidence freshness states (closed).
FRESH = "fresh"
STALE = "stale"
ABSENT = "absent"
UNKNOWN = "unknown"
FRESHNESS_STATES = frozenset({FRESH, STALE, ABSENT, UNKNOWN})

#: Invariant verdicts (closed).  UNKNOWN never collapses to PROVEN.
PROVEN = "PROVEN"
VIOLATED = "VIOLATED"
INVARIANT_UNKNOWN = "UNKNOWN"
INVARIANT_STATES = frozenset({PROVEN, VIOLATED, INVARIANT_UNKNOWN})

#: Duplicate-launcher kinds (closed).
DUPLICATE_KINDS = frozenset(
    {"dsh_direct", "codex_cli", "second_t3_thread", "other"}
)

DEFAULT_FRESHNESS_WINDOW_S = 45.0
MAX_ATTEMPTS = 256
MAX_EVIDENCE_REFS = 24

ATTEMPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:=/%-]{0,255}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:=/-]{0,255}$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:=/-]{0,255}$")
_WORKSPACE_RE = re.compile(r"^[A-Za-z0-9/~][A-Za-z0-9_./:-]{0,511}$")
_STATUS_RE = re.compile(r"^[A-Za-z0-9_ -]{1,32}$")
#: provider/model names carry dots and slashes (e.g. glm-5.3, openai/gpt-5.2)
_PROVIDER_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+ -]{0,63}$")

_ADAPTER_TABLE = "t3_adapter_runs"


class T3AttemptFleetError(ValueError):
    """A closed, typed projection refusal (never carries evidence content)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise T3AttemptFleetError(code)


# ── (a) adapter state rows (read-only) ───────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class AttemptAdapterRow:
    """The closed slice of one durable ``t3_adapter_runs`` row this view reads.

    ``key``/``namespace`` come from the persisted launch intent (falling back
    to the receipt's echoes); ``thread_id``/``native_run_id`` from the persisted
    launch receipt; ``workspace_path`` from the persisted launch spec.  A row
    with an intent but no receipt is the adapter's effect-unknown zone: the
    thread fact stays unknown here too.
    """

    run_id: str
    key: str | None = None
    namespace: str | None = None
    thread_id: str | None = None
    native_run_id: str | None = None
    workspace_path: str | None = None
    model_selection: str | None = None
    has_intent: bool = False
    has_receipt: bool = False
    terminal_native_status: str | None = None


def _bounded_id(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse(code)
    return value


def _row_json(raw: Any, code: str) -> dict[str, Any] | None:
    if raw is None or raw == "":
        return None
    if type(raw) is not str:
        _refuse(code)
    try:
        parsed = json.loads(raw)
    except ValueError:
        _refuse(code)
    if not isinstance(parsed, dict):
        _refuse(code)
    return parsed


def _row_field(doc: dict[str, Any], name: str) -> Any:
    return doc.get(name)


def _normalize_row(
    run_id_raw: Any,
    intent_json: Any,
    receipt_json: Any,
    spec_json: Any,
    result_ref_json: Any,
) -> AttemptAdapterRow:
    run_id = _bounded_id(run_id_raw, ATTEMPT_ID_RE, "ADAPTER_ROW_MALFORMED")

    intent = _row_json(intent_json, "ADAPTER_ROW_MALFORMED")
    receipt = _row_json(receipt_json, "ADAPTER_ROW_MALFORMED")
    spec = _row_json(spec_json, "ADAPTER_ROW_MALFORMED")
    result_ref = _row_json(result_ref_json, "ADAPTER_ROW_MALFORMED")

    key: str | None = None
    namespace: str | None = None
    model_selection: str | None = None
    if intent is not None:
        intent_run = _row_field(intent, "run_id")
        if intent_run != run_id:
            _refuse("ADAPTER_ROW_MALFORMED")
        key = _bounded_id(
            _row_field(intent, "client_request_id"), _KEY_RE,
            "ADAPTER_ROW_MALFORMED",
        )
        namespace = _bounded_id(
            _row_field(intent, "request_namespace"), _NAMESPACE_RE,
            "ADAPTER_ROW_MALFORMED",
        )
        envelope = _row_field(intent, "envelope")
        if envelope is not None:
            if not isinstance(envelope, dict):
                _refuse("ADAPTER_ROW_MALFORMED")
            selection = _row_field(envelope, "model_selection")
            if selection not in (None, ""):
                model_selection = _bounded_id(
                    selection, _PROVIDER_MODEL_RE, "ADAPTER_ROW_MALFORMED"
                )

    thread_id: str | None = None
    native_run_id: str | None = None
    if receipt is not None:
        raw_thread = _row_field(receipt, "thread_id")
        raw_native = _row_field(receipt, "run_id")
        if raw_thread not in (None, ""):
            thread_id = _bounded_id(
                raw_thread, _ID_RE, "ADAPTER_ROW_MALFORMED"
            )
        if raw_native not in (None, ""):
            native_run_id = _bounded_id(
                raw_native, _ID_RE, "ADAPTER_ROW_MALFORMED"
            )
        echo_key = _row_field(receipt, "client_request_id")
        echo_ns = _row_field(receipt, "request_namespace")
        if echo_key not in (None, ""):
            echoed_key = _bounded_id(
                echo_key, _KEY_RE, "ADAPTER_ROW_MALFORMED"
            )
            if key is not None and echoed_key != key:
                # A durable receipt echoing a foreign idempotency key is
                # corrupt evidence about this attempt: refuse, never guess.
                _refuse("ADAPTER_ROW_MALFORMED")
            if key is None:
                key = echoed_key
        if echo_ns not in (None, ""):
            echoed_ns = _bounded_id(
                echo_ns, _NAMESPACE_RE, "ADAPTER_ROW_MALFORMED"
            )
            if namespace is not None and echoed_ns != namespace:
                _refuse("ADAPTER_ROW_MALFORMED")
            if namespace is None:
                namespace = echoed_ns

    workspace_path: str | None = None
    if spec is not None:
        raw_workspace = _row_field(spec, "workspace_path")
        if raw_workspace not in (None, ""):
            if type(raw_workspace) is str:
                raw_workspace = raw_workspace.rstrip("/") or raw_workspace
            workspace_path = _bounded_id(
                raw_workspace, _WORKSPACE_RE, "ADAPTER_ROW_MALFORMED"
            )

    terminal_native_status: str | None = None
    if result_ref is not None:
        raw_status = _row_field(result_ref, "native_status")
        if raw_status not in (None, ""):
            terminal_native_status = _bounded_id(
                raw_status, _STATUS_RE, "ADAPTER_ROW_MALFORMED"
            )

    return AttemptAdapterRow(
        run_id=run_id,
        key=key,
        namespace=namespace,
        thread_id=thread_id,
        native_run_id=native_run_id,
        workspace_path=workspace_path,
        model_selection=model_selection,
        has_intent=intent is not None,
        has_receipt=receipt is not None,
        terminal_native_status=terminal_native_status,
    )


def read_adapter_attempt_rows(
    path: str | Path, *, connection: sqlite3.Connection | None = None
) -> tuple[AttemptAdapterRow, ...]:
    """Read every attempt row from the durable adapter state, READ-ONLY.

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
            "SELECT run_id, intent_json, receipt_json, spec_json,"
            " result_ref_json FROM " + _ADAPTER_TABLE + " ORDER BY rowid"
        )
        rows: list[AttemptAdapterRow] = []
        for record in cursor.fetchall():
            rows.append(_normalize_row(*record))
        return tuple(rows)
    except sqlite3.Error:
        _refuse("ADAPTER_STATE_UNREADABLE")
    finally:
        if opened and connection is not None:
            connection.close()


# ── (b) thread read port ─────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class ThreadReadFact:
    """One closed thread-read result (already collected; may be stale)."""

    thread_id: str
    run_id: str | None = None
    native_status: str | None = None
    read_at_utc: str = ""


@runtime_checkable
class T3ThreadReadPort(Protocol):
    """Injectable read side for one thread; unknown is a real return value."""

    def read(self, thread_id: str) -> ThreadReadFact | None: ...


class SavedThreadReads:
    """A port over saved ``t3_thread_read`` results (offline composition)."""

    def __init__(self, facts: Mapping[str, Mapping[str, Any]]) -> None:
        self._facts: dict[str, ThreadReadFact] = {}
        for thread_id, doc in facts.items():
            fact = _thread_read_fact(doc)
            if fact.thread_id != thread_id:
                _refuse("THREAD_READ_INVALID")
            self._facts[thread_id] = fact

    def read(self, thread_id: str) -> ThreadReadFact | None:
        return self._facts.get(thread_id)


def _thread_read_fact(doc: Any) -> ThreadReadFact:
    if not isinstance(doc, Mapping):
        _refuse("THREAD_READ_INVALID")
    keys = {"thread_id", "run_id", "native_status", "read_at_utc"}
    if not keys <= set(doc):
        _refuse("THREAD_READ_INVALID")
    thread_id = _bounded_id(doc.get("thread_id"), _ID_RE, "THREAD_READ_INVALID")
    run_id = doc.get("run_id")
    if run_id not in (None, ""):
        run_id = _bounded_id(run_id, _ID_RE, "THREAD_READ_INVALID")
    else:
        run_id = None
    status = doc.get("native_status")
    if status not in (None, ""):
        status = _bounded_id(status, _STATUS_RE, "THREAD_READ_INVALID")
    else:
        status = None
    read_at = doc.get("read_at_utc")
    if type(read_at) is not str or not read_at:
        _refuse("THREAD_READ_INVALID")
    try:
        parsed = datetime.fromisoformat(
            read_at[:-1] + "+00:00" if read_at.endswith("Z") else read_at
        )
    except ValueError:
        _refuse("THREAD_READ_INVALID")
    if parsed.tzinfo is None:
        _refuse("THREAD_READ_INVALID")
    return ThreadReadFact(
        thread_id=thread_id,
        run_id=run_id,
        native_status=status,
        read_at_utc=read_at,
    )


# ── (c) census normalization ─────────────────────────────────────────────────


def _census(value: CensusSnapshot | Mapping[str, Any] | None) -> CensusSnapshot | None:
    if value is None:
        return None
    if isinstance(value, CensusSnapshot):
        return value
    try:
        return census_from_dict(value)
    except T3ProcessCensusError:
        _refuse("CENSUS_INVALID")


def _classification(process: CensusProcess) -> Classification:
    return classify(process.argv)


def _correlated(processes: Sequence[CensusProcess], workspace: str) -> list[CensusProcess]:
    """Processes whose (redacted) argv references the attempt workspace."""
    matched: list[CensusProcess] = []
    for process in processes:
        if any(workspace in token for token in process.argv):
            matched.append(process)
    return matched


# ── (d) clock + freshness ────────────────────────────────────────────────────


def _now(clock: Any) -> datetime:
    value = clock() if callable(clock) else clock
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            _refuse("CLOCK_INVALID")
        return value.astimezone(timezone.utc)
    if type(value) in (int, float):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    _refuse("CLOCK_INVALID")


def _parse_utc(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00" if text.endswith("Z") else text
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _freshness(
    observed_at_utc: str, now: datetime, window_s: float
) -> str:
    if type(observed_at_utc) is not str or not observed_at_utc:
        return UNKNOWN
    observed = _parse_utc(observed_at_utc)
    if observed is None:
        return UNKNOWN
    age = (now - observed).total_seconds()
    if 0 <= age <= window_s:
        return FRESH
    return STALE


# ── per-attempt projection ───────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class T3AttemptFleetView:
    """The closed per-attempt projection; every unknown carries its reason."""

    attempt_id: str
    idempotency: Mapping[str, Any]
    t3_thread: Mapping[str, Any]
    harness_process: Mapping[str, Any]
    thread_count_for_key: int | None
    thread_count_reason: str | None
    harness_count_for_thread: int | None
    harness_count_reason: str | None
    duplicate_launcher: Mapping[str, Any]
    invariant: Mapping[str, str]
    freshness: Mapping[str, str]
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "idempotency": dict(self.idempotency),
            "t3_thread": dict(self.t3_thread),
            "harness_process": dict(self.harness_process),
            "thread_count_for_key": self.thread_count_for_key,
            "thread_count_reason": self.thread_count_reason,
            "harness_count_for_thread": self.harness_count_for_thread,
            "harness_count_reason": self.harness_count_reason,
            "duplicate_launcher": dict(self.duplicate_launcher),
            "invariant": dict(self.invariant),
            "freshness": dict(self.freshness),
            "evidence_refs": list(self.evidence_refs[:MAX_EVIDENCE_REFS]),
        }


def _harness_roots(
    correlated: Sequence[CensusProcess],
) -> list[CensusProcess]:
    """Collapse each harness process TREE to one root (wrapper + exec child).

    T3 launches the agent through a ``/bin/sh -c '... exec ...'`` wrapper that
    keeps living beside the agent process (observed live, lane ledger): parent
    and child share the workspace markers.  Counting both would report two
    harnesses for one thread, so a correlated process whose ppid is ALSO a
    correlated harness process is the same tree, not a second one.
    """
    pids = {process.pid for process in correlated}
    return [
        process for process in correlated if process.ppid not in pids
    ]


def project_attempt(
    attempt_id: str | None = None,
    *,
    rows: Sequence[AttemptAdapterRow] | None = None,
    all_rows: Sequence[AttemptAdapterRow] | None = None,
    thread_read_port: T3ThreadReadPort | None = None,
    census: CensusSnapshot | Mapping[str, Any] | None = None,
    clock: Any = None,
    freshness_window_s: float = DEFAULT_FRESHNESS_WINDOW_S,
) -> T3AttemptFleetView:
    """Project one attempt from the four evidence inputs.

    ``rows`` are the attempt's own adapter rows (usually one); ``all_rows`` the
    full store read, used to count sibling rows minted under the SAME
    (key, namespace) — the second-T3-thread duplicate is readable from the
    durable state alone, with no census and no native call.
    """
    if type(freshness_window_s) not in (int, float) or freshness_window_s <= 0:
        _refuse("FRESHNESS_WINDOW_INVALID")
    now = _now(clock)
    snapshot = _census(census)

    own_rows: list[AttemptAdapterRow] = list(rows or [])
    if attempt_id is None:
        if not own_rows:
            _refuse("ATTEMPT_ID_INVALID")
        attempt_id = own_rows[0].run_id
    attempt_id = _bounded_id(attempt_id, ATTEMPT_ID_RE, "ATTEMPT_ID_INVALID")
    own_rows = [row for row in own_rows if row.run_id == attempt_id]

    key: str | None = None
    namespace: str | None = None
    thread_id: str | None = None
    native_run_id: str | None = None
    workspace: str | None = None
    model_selection: str | None = None
    terminal_status: str | None = None
    has_intent = False
    has_receipt = False
    for row in own_rows:
        key = row.key or key
        namespace = row.namespace or namespace
        thread_id = row.thread_id or thread_id
        native_run_id = row.native_run_id or native_run_id
        workspace = row.workspace_path or workspace
        model_selection = row.model_selection or model_selection
        terminal_status = row.terminal_native_status or terminal_status
        has_intent = has_intent or row.has_intent
        has_receipt = has_receipt or row.has_receipt

    evidence: list[str] = []
    if rows is not None:
        evidence.append("adapter_state:read")

    # ── thread count for (key, namespace) — durable-state evidence alone ────
    thread_ids_for_key: set[str] = set()
    thread_count: int | None = None
    thread_count_reason: str | None = None
    if key is not None and namespace is not None:
        for row in all_rows or own_rows:
            if row.key == key and row.namespace == namespace:
                if row.thread_id:
                    thread_ids_for_key.add(row.thread_id)
        if thread_ids_for_key:
            thread_count = len(thread_ids_for_key)
            evidence.append("adapter_state:key:" + key[:12])
        else:
            thread_count = None
            thread_count_reason = "NO_RECEIPT_THREAD"
    else:
        thread_count_reason = "NO_IDEMPOTENCY_IDENTITY"

    # ── thread read (injectable port; unknown is a real value) ──────────────
    read_fact: ThreadReadFact | None = None
    thread_read_freshness = ABSENT
    if thread_read_port is not None and thread_id is not None:
        try:
            read_fact = thread_read_port.read(thread_id)
        except T3AttemptFleetError:
            raise
        except Exception:
            read_fact = None
        if read_fact is not None:
            evidence.append("thread_read:" + thread_id[:24])
            thread_read_freshness = _freshness(
                read_fact.read_at_utc, now, freshness_window_s
            )
        else:
            thread_read_freshness = UNKNOWN

    state = None
    if read_fact is not None and read_fact.native_status:
        state = read_fact.native_status
    elif terminal_status:
        state = terminal_status
    t3_thread: dict[str, Any] = {
        "thread_id": thread_id,
        "run_id": native_run_id,
        "state": state,
        "unknown_reason": (
            None if thread_id is not None else (
                "NO_ADAPTER_ROW" if not own_rows else "NO_RECEIPT"
            )
        ),
    }
    if thread_id is not None and native_run_id is None and read_fact is not None:
        t3_thread["run_id"] = read_fact.run_id

    # ── census side: harness correlation + duplicate launchers ──────────────
    census_freshness = UNKNOWN if snapshot is None else _freshness(
        snapshot.observed_at_utc, now, freshness_window_s
    )
    harness_count: int | None = None
    harness_count_reason: str | None = None
    harness_process: dict[str, Any] = {
        "pid": None, "provider": None, "model": None, "start_time": None,
        "unknown_reason": None,
    }
    duplicate_kinds: list[str] = []
    duplicate_observed: bool | None = None
    duplicate_reason: str | None = None

    correlated_duplicate_processes: list[tuple[str, CensusProcess]] = []
    census_usable = snapshot is not None and census_freshness == FRESH
    if census_usable:
        assert snapshot is not None
        if thread_id is None:
            harness_count_reason = "NO_THREAD_TO_CORRELATE"
        elif workspace is None:
            harness_count_reason = "NO_WORKSPACE_IN_SPEC"
        else:
            correlated = [
                process for process in snapshot.processes
                if _classification(process).kind == KIND_T3_HARNESS
                and any(workspace in token for token in process.argv)
            ]
            roots = _harness_roots(correlated)
            harness_count = len(roots)
            for process in sorted(roots, key=lambda item: item.pid):
                evidence.append(f"census:pid:{process.pid}")
            if roots:
                root = sorted(roots, key=lambda item: item.pid)[0]
                classification = _classification(root)
                harness_process = {
                    "pid": root.pid,
                    "provider": classification.provider,
                    "model": classification.model or model_selection,
                    "start_time": datetime.fromtimestamp(
                        root.started_epoch_s, tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                    "unknown_reason": None,
                }
            else:
                harness_count_reason = "HARNESS_NOT_OBSERVED"
            # duplicate launchers: DIRECT kinds (and agent-shaped others)
            # correlated with the same workspace
            for process in snapshot.processes:
                classification = _classification(process)
                if classification.kind == KIND_T3_HARNESS:
                    continue
                if classification.kind in (KIND_DSH_DIRECT, KIND_CODEX_CLI):
                    if any(workspace in token for token in process.argv):
                        correlated_duplicate_processes.append(
                            (classification.kind, process)
                        )
                        evidence.append(f"census:pid:{process.pid}")
                elif (
                    classification.kind == KIND_OTHER
                    and classification.provider is not None
                    and any(workspace in token for token in process.argv)
                ):
                    correlated_duplicate_processes.append(
                        ("other", process)
                    )
                    evidence.append(f"census:pid:{process.pid}")
    else:
        harness_count_reason = (
            "CENSUS_ABSENT" if snapshot is None else "CENSUS_STALE"
        )

    if thread_count is not None and thread_count >= 2:
        duplicate_kinds.append("second_t3_thread")
    duplicate_kinds.extend(sorted({kind for kind, _ in correlated_duplicate_processes}))

    if duplicate_kinds:
        duplicate_observed = True
        duplicate_reason = None
    elif thread_count == 1 and census_usable and workspace is not None and thread_id is not None:
        duplicate_observed = False
        duplicate_reason = None
    elif thread_count == 1:
        duplicate_observed = None
        duplicate_reason = (
            harness_count_reason or "CENSUS_SIDE_UNKNOWN"
        )
    else:
        duplicate_observed = None
        duplicate_reason = (
            "THREAD_COUNT_UNKNOWN" if thread_count is None else "THREAD_SIDE_UNKNOWN"
        )

    duplicate_launcher: dict[str, Any] = {
        "observed": duplicate_observed,
        "kinds": duplicate_kinds,
        "evidence_refs": [
            ref for ref in evidence if ref.startswith(("census:", "adapter_state:", "thread_read:"))
        ][:MAX_EVIDENCE_REFS],
        "unknown_reason": duplicate_reason,
    }

    # ── invariants ──────────────────────────────────────────────────────────
    if thread_count is not None and thread_count >= 2:
        exactly_one_thread = VIOLATED
    elif thread_count == 1 and thread_id is not None:
        exactly_one_thread = PROVEN
    else:
        exactly_one_thread = INVARIANT_UNKNOWN

    # A harness count of 0 under a fresh census is NOT a violation: the
    # provider may run the harness remotely or it already exited — UNKNOWN.
    if harness_count is None or harness_count == 0:
        exactly_one_harness = INVARIANT_UNKNOWN
    elif harness_count == 1:
        exactly_one_harness = PROVEN
    else:
        exactly_one_harness = VIOLATED

    # An unobserved harness always carries its reason (never a bare null).
    if harness_process["pid"] is None and harness_process["unknown_reason"] is None:
        harness_process["unknown_reason"] = (
            harness_count_reason or "HARNESS_NOT_OBSERVED"
        )

    freshness: dict[str, str] = {
        "adapter_state": FRESH if rows is not None else UNKNOWN,
        "census": census_freshness,
        "thread_read": thread_read_freshness,
    }

    return T3AttemptFleetView(
        attempt_id=attempt_id,
        idempotency={"key": key, "namespace": namespace},
        t3_thread=t3_thread,
        harness_process=harness_process,
        thread_count_for_key=thread_count,
        thread_count_reason=thread_count_reason,
        harness_count_for_thread=harness_count,
        harness_count_reason=harness_count_reason,
        duplicate_launcher=duplicate_launcher,
        invariant={
            "exactly_one_thread": exactly_one_thread,
            "exactly_one_harness": exactly_one_harness,
        },
        freshness=freshness,
        evidence_refs=tuple(evidence),
    )


def project_fleet(
    all_rows: Sequence[AttemptAdapterRow] | None = None,
    *,
    thread_read_port: T3ThreadReadPort | None = None,
    census: CensusSnapshot | Mapping[str, Any] | None = None,
    clock: Any = None,
    freshness_window_s: float = DEFAULT_FRESHNESS_WINDOW_S,
    attempt_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Project every attempt in the store (plus any explicitly named ids).

    One shared census and one clock; per-attempt views in ``run_id`` order.
    The result is the full ``mastermind.t3_attempt_fleet/v1`` document.
    """
    now = _now(clock)
    rows = list(all_rows or ())
    if len(rows) > MAX_ATTEMPTS:
        _refuse("TOO_MANY_ATTEMPTS")
    ids = [row.run_id for row in rows]
    if attempt_ids is not None:
        for attempt_id in attempt_ids:
            if attempt_id not in ids:
                ids.append(attempt_id)
    if len(ids) > MAX_ATTEMPTS:
        _refuse("TOO_MANY_ATTEMPTS")
    attempts = [
        project_attempt(
            attempt_id,
            rows=[row for row in rows if row.run_id == attempt_id],
            all_rows=rows,
            thread_read_port=thread_read_port,
            census=census,
            clock=now,
            freshness_window_s=freshness_window_s,
        ).to_dict()
        for attempt_id in sorted(set(ids))
    ]
    snapshot = _census(census)
    notes: list[str] = []
    if not rows:
        notes.append("ADAPTER_STATE_EMPTY")
    if snapshot is None:
        notes.append("CENSUS_ABSENT")
    return {
        "schema": FLEET_SCHEMA,
        "evaluated_at_utc": now.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "attempts": attempts,
        "notes": notes,
    }


def validate_attempt(value: Any) -> dict[str, Any]:
    """Closed-set validation of one attempt document (TS-parser mirror)."""
    if not isinstance(value, Mapping):
        _refuse("ATTEMPT_FIELDS_INVALID")
    expected = {
        "attempt_id", "idempotency", "t3_thread", "harness_process",
        "thread_count_for_key", "thread_count_reason",
        "harness_count_for_thread", "harness_count_reason",
        "duplicate_launcher", "invariant", "freshness", "evidence_refs",
    }
    if set(value) != expected:
        _refuse("ATTEMPT_FIELDS_INVALID")
    _bounded_id(value["attempt_id"], ATTEMPT_ID_RE, "ATTEMPT_ID_INVALID")

    idempotency = value["idempotency"]
    if not isinstance(idempotency, Mapping) or set(idempotency) != {"key", "namespace"}:
        _refuse("IDEMPOTENCY_FIELDS_INVALID")
    for field in ("key", "namespace"):
        item = idempotency[field]
        if item is not None:
            _bounded_id(item, _KEY_RE, "IDEMPOTENCY_FIELDS_INVALID")

    thread = value["t3_thread"]
    if not isinstance(thread, Mapping) or set(thread) != {
        "thread_id", "run_id", "state", "unknown_reason"
    }:
        _refuse("THREAD_FIELDS_INVALID")
    for field in ("thread_id", "run_id"):
        if thread[field] is not None:
            _bounded_id(thread[field], _ID_RE, "THREAD_FIELDS_INVALID")
    if thread["state"] is not None:
        _bounded_id(thread["state"], _STATUS_RE, "THREAD_FIELDS_INVALID")
    if thread["unknown_reason"] is not None:
        _bounded_id(thread["unknown_reason"], _STATUS_RE, "THREAD_FIELDS_INVALID")
    if thread["thread_id"] is None and thread["unknown_reason"] is None:
        _refuse("THREAD_FIELDS_INVALID")

    harness = value["harness_process"]
    if not isinstance(harness, Mapping) or set(harness) != {
        "pid", "provider", "model", "start_time", "unknown_reason"
    }:
        _refuse("HARNESS_FIELDS_INVALID")
    if harness["pid"] is not None and (
        type(harness["pid"]) is not int or harness["pid"] < 1
    ):
        _refuse("HARNESS_FIELDS_INVALID")
    for field in ("provider", "model"):
        if harness[field] is not None:
            _bounded_id(harness[field], _PROVIDER_MODEL_RE, "HARNESS_FIELDS_INVALID")
    if harness["start_time"] is not None:
        if _parse_utc(str(harness["start_time"])) is None:
            _refuse("HARNESS_FIELDS_INVALID")
    if harness["pid"] is None and harness["unknown_reason"] is None:
        _refuse("HARNESS_FIELDS_INVALID")

    for field, code in (
        ("thread_count_for_key", "THREAD_COUNT_INVALID"),
        ("harness_count_for_thread", "HARNESS_COUNT_INVALID"),
    ):
        count = value[field]
        if count is not None and (type(count) is not int or count < 0):
            _refuse(code)
    for field in ("thread_count_reason", "harness_count_reason"):
        reason = value[field]
        if reason is not None:
            _bounded_id(reason, _STATUS_RE, "REASON_FIELDS_INVALID")

    duplicate = value["duplicate_launcher"]
    if not isinstance(duplicate, Mapping) or set(duplicate) != {
        "observed", "kinds", "evidence_refs", "unknown_reason"
    }:
        _refuse("DUPLICATE_FIELDS_INVALID")
    if duplicate["observed"] is not None and type(duplicate["observed"]) is not bool:
        _refuse("DUPLICATE_FIELDS_INVALID")
    kinds = duplicate["kinds"]
    if type(kinds) is not list or any(kind not in DUPLICATE_KINDS for kind in kinds):
        _refuse("DUPLICATE_FIELDS_INVALID")
    refs = duplicate["evidence_refs"]
    if type(refs) is not list or len(refs) > MAX_EVIDENCE_REFS or any(
        type(ref) is not str or len(ref) > 160 or "\n" in ref for ref in refs
    ):
        _refuse("DUPLICATE_FIELDS_INVALID")
    if duplicate["observed"] is None and duplicate["unknown_reason"] is None:
        _refuse("DUPLICATE_FIELDS_INVALID")
    if duplicate["observed"] is True and not kinds:
        _refuse("DUPLICATE_FIELDS_INVALID")

    invariant = value["invariant"]
    if not isinstance(invariant, Mapping) or set(invariant) != {
        "exactly_one_thread", "exactly_one_harness"
    }:
        _refuse("INVARIANT_FIELDS_INVALID")
    for verdict in invariant.values():
        if verdict not in INVARIANT_STATES:
            _refuse("INVARIANT_FIELDS_INVALID")

    freshness = value["freshness"]
    if not isinstance(freshness, Mapping) or set(freshness) != {
        "adapter_state", "census", "thread_read"
    }:
        _refuse("FRESHNESS_FIELDS_INVALID")
    for state in freshness.values():
        if state not in FRESHNESS_STATES:
            _refuse("FRESHNESS_FIELDS_INVALID")

    evidence = value["evidence_refs"]
    if type(evidence) is not list or len(evidence) > MAX_EVIDENCE_REFS or any(
        type(ref) is not str or len(ref) > 160 or "\n" in ref for ref in evidence
    ):
        _refuse("EVIDENCE_FIELDS_INVALID")
    return dict(value)


__all__ = [
    "ABSENT",
    "AttemptAdapterRow",
    "DEFAULT_FRESHNESS_WINDOW_S",
    "DUPLICATE_KINDS",
    "FLEET_SCHEMA",
    "FRESH",
    "FRESHNESS_STATES",
    "INVARIANT_STATES",
    "INVARIANT_UNKNOWN",
    "PROVEN",
    "SavedThreadReads",
    "STALE",
    "T3AttemptFleetError",
    "T3AttemptFleetView",
    "T3ThreadReadPort",
    "ThreadReadFact",
    "UNKNOWN",
    "VIOLATED",
    "project_attempt",
    "project_fleet",
    "read_adapter_attempt_rows",
    "validate_attempt",
]
