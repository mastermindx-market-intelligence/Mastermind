"""Durable episode thesis + amendment records for PBR (shadow, append-only).

Spec: ``docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md``
§3 (``pbr.thesis.v1`` / ``pbr.thesis_amendment.v1``), amended by the seat
rulings of 2026-10-22 (Q1 amendment watching / conviction observations; Q4
amendment reason codes).

Granularity: one ThesisRecord per **position episode** — open at the first
entry fill, closed when the position reaches zero — linked to actual entry
fill ids.  This is a different granularity from ``brain/ledger.py`` (one open
thesis per subject, ``close()`` rewrites, feeding FORGE calibration): that
ledger stays the accountability spine and is neither read nor written here
(frozen law 28 — no duplicate stores; this is not a mirror of it).

Storage: ONLY under a caller-supplied ``store_dir: Path`` — three append-only
JSONL files (``theses.jsonl``, ``amendments.jsonl``, ``observations.jsonl``).
There is no default path, no module-level data path and no writer other than
the ``record_*`` functions, in deliberate contrast to ``brain/ledger.py``'s
fixed ``_LEDGER``.  Nothing here routes to a pending target, an order/fill
writer or a settlement call; records are shadow artifacts in this wave.

Seat ruling Q1 (binding): the amendment watched set is thesis-semantic ONLY —
``AMENDMENT_WATCHED_FIELDS`` maps each watched thesis field to the holding-row
field it watches (thesis_statement←rationale, falsifiers←falsifier,
check_by/time_stop←expected_horizon, exit_conditions←exit_plan,
size_cap/target_weight←proposed_weight, catalyst←why_now).  A null/absent
``proposed_weight`` in the later row means "not restated", not a change.
Realised ``weight`` and ``weight_source`` are never watched.  **Conviction is
NOT watched**: it is a per-cycle observation, recorded append-only in
``observations.jsonl`` (schema ``pbr.thesis_observation.v1``), and it never
produces an amendment or an UNRECORDED_AMENDMENT finding.
:func:`check_continuity` turns a watched change without a covering
AmendmentRecord into a ``REJECTED_UNRECORDED_AMENDMENT`` verdict — a shadow
verdict on the lineage that leaves the stored thesis unchanged; it is never a
live-action veto.

Seat ruling Q4 (binding): terminal amendments (INVALIDATED / EXCLUDED) REQUIRE
a ``reason_code`` from the closed enum ``AMENDMENT_REASON_CODES``; every
amendment that carries one is validated against the same enum.  An optional
free-text ``note`` is accepted by the runtime API as a plain string (runtime
records live off-repo); tests pass a ``pbr.prose_digest.v1``-shaped dict
(sha256 + length) or omit it — a note is never production prose in-repo.

Point-in-time discipline: an amendment whose ``effective_at`` precedes the
originating decision's asof is rejected (``retroactive_amendment_rejected``),
so an amendment can never retroactively rewrite an earlier failed prediction
(MASTERPLAN §7.8).  The originating decision's asof is supplied by the caller
(``originating_decision_asof``) because it is a property of the decision row,
not of this store.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence, TypedDict

SCHEMA_VERSION = "pbr.thesis.v1"
AMENDMENT_SCHEMA_VERSION = "pbr.thesis_amendment.v1"
OBSERVATION_SCHEMA_VERSION = "pbr.thesis_observation.v1"

THESES_FILENAME = "theses.jsonl"
AMENDMENTS_FILENAME = "amendments.jsonl"
OBSERVATIONS_FILENAME = "observations.jsonl"

#: Closed vocabulary for ``position_role``.
POSITION_ROLES = ("starter", "established", "risk_reduction")

#: Closed vocabulary for ``local_thesis_status`` (spec §3.2).
LOCAL_THESIS_STATUSES = ("ACTIVE", "AMENDED", "INVALIDATED", "EXCLUDED", "NONE_RECORDED")

#: Closed vocabulary for ``provider_plan_status`` (spec §3.2).
PROVIDER_PLAN_STATUSES = ("active_plan", "held_without_active_plan", "unavailable")

#: Finding emitted when the provider packet lacks a plan while a local thesis exists.
FINDING_PROVIDER_PLAN_MISSING = "PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT"

#: Finding emitted when consecutive holdings rows change thesis semantics without
#: a linking amendment record (spec §3.3).
UNRECORDED_AMENDMENT = "UNRECORDED_AMENDMENT"

#: Seat ruling Q1: thesis field -> the holding-row field it watches.  The set of
#: watched holding-row fields is the mapping's image; realised ``weight`` and
#: ``weight_source`` are absent by construction, and conviction is never a
#: watched thesis field (it is an observation, not an amendment).
AMENDMENT_WATCHED_FIELDS: dict[str, str] = {
    "thesis_statement": "rationale",
    "falsifiers": "falsifier",
    "check_by": "expected_horizon",
    "time_stop": "expected_horizon",
    "exit_conditions": "exit_plan",
    "size_cap": "proposed_weight",
    "target_weight": "proposed_weight",
    "catalyst": "why_now",
}

#: The holding-row fields watched for amendment-lineage changes (fixed order).
WATCHED_HOLDING_ROW_FIELDS = tuple(dict.fromkeys(AMENDMENT_WATCHED_FIELDS.values()))

#: Seat ruling Q1: a null/absent ``proposed_weight`` in the later row means the
#: size intent was not restated, not that it changed.
NOT_RESTATEMENT_FIELD = "proposed_weight"

#: Closed vocabulary for ``AmendmentRecord.reason_code`` (seat ruling Q4).
AMENDMENT_REASON_CODES = ("FALSIFIED", "TIME_STOP", "EXIT_PLAN_HIT", "SUPERSEDED", "MANUAL")

#: Terminal amendment statuses: these REQUIRE a ``reason_code`` (seat ruling Q4).
TERMINAL_AMENDMENT_STATUSES = ("INVALIDATED", "EXCLUDED")

#: The structured field a terminal amendment changes.
EPISODE_STATUS_FIELD = "episode_status"

#: Verdict statuses returned by :func:`check_continuity` (seat ruling Q1).
CONTINUITY_ACCEPTED_UNCHANGED = "ACCEPTED_NO_WATCHED_CHANGE"
CONTINUITY_ACCEPTED_AMENDED = "ACCEPTED_AMENDMENT_RECORDED"
CONTINUITY_REJECTED_UNRECORDED = "REJECTED_UNRECORDED_AMENDMENT"
CONTINUITY_STATUSES = (
    CONTINUITY_REJECTED_UNRECORDED,
    CONTINUITY_ACCEPTED_AMENDED,
    CONTINUITY_ACCEPTED_UNCHANGED,
)

#: Holding-row fields that carry per-cycle observations rather than thesis state.
OBSERVED_ROW_FIELDS = ("conviction",)


class ThesisRecord(TypedDict, total=False):
    thesis_id: str
    book: str
    ticker: str
    episode_open_date: str
    episode_close_date: str | None
    entry_fill_ids: list[str]
    why_now: str
    fact_ids: list[str]
    horizon: str | None
    falsifiers: list[str]
    exit_conditions: list[str]
    position_role: str
    originating_decision_id: str
    created_at: str
    schema: str


class AmendmentRecord(TypedDict, total=False):
    amendment_id: str
    thesis_id: str
    changes: dict
    reason: str
    reason_code: str
    note: Any
    evidence_refs: list[str]
    effective_at: str
    recorded_at: str
    accountable_decision_id: str
    schema: str


class ObservationRecord(TypedDict, total=False):
    schema: str
    thesis_id: str | None
    cycle_id: str
    asof: str
    field: str
    value: Any
    previous_value: Any
    recorded_at: str


class ThesisStoreError(RuntimeError):
    """Base error; ``code`` carries the stable finding/error code."""

    code = "thesis_store_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class RetroactiveAmendmentError(ThesisStoreError):
    code = "retroactive_amendment_rejected"


class ThesisNotFound(ThesisStoreError):
    code = "thesis_not_found"


# ────────────────────────────── atomic appends ──────────────────────────────


def _append_line(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        raise ThesisStoreError("missing timestamp", code="invalid_timestamp")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ThesisStoreError(
            f"unparseable timestamp {value!r}", code="invalid_timestamp"
        ) from exc


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ThesisStoreError(
            f"unparseable date {value!r}", code="invalid_date"
        ) from exc


def _canon(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


# ─────────────────────────────── thesis records ─────────────────────────────


def make_thesis_id(
    book: str, ticker: str, episode_open_date: str, originating_decision_id: str
) -> str:
    """Deterministic episode id: sha256 over the episode key, truncated to 16 hex."""
    payload = _canon(
        {
            "book": book,
            "ticker": ticker,
            "episode_open_date": str(episode_open_date),
            "originating_decision_id": originating_decision_id,
        }
    )
    return "thesis.v1." + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_thesis(store_dir: Path, record: Mapping) -> ThesisRecord:
    """Validate and append one ThesisRecord (append-only; duplicates refused)."""
    out = dict(record)
    missing = [
        key
        for key in (
            "book",
            "ticker",
            "episode_open_date",
            "originating_decision_id",
            "created_at",
        )
        if not out.get(key)
    ]
    if missing:
        raise ThesisStoreError(
            f"thesis record missing required fields: {missing}",
            code="invalid_thesis_record",
        )
    role = str(out.get("position_role") or "").strip()
    if role not in POSITION_ROLES:
        raise ThesisStoreError(
            f"position_role must be one of {POSITION_ROLES}, got {role!r}",
            code="invalid_thesis_record",
        )
    out.setdefault("schema", SCHEMA_VERSION)
    if out["schema"] != SCHEMA_VERSION:
        raise ThesisStoreError(
            f"schema must be {SCHEMA_VERSION}", code="invalid_thesis_record"
        )
    out.setdefault(
        "thesis_id",
        make_thesis_id(
            str(out["book"]),
            str(out["ticker"]),
            str(out["episode_open_date"]),
            str(out["originating_decision_id"]),
        ),
    )
    out["entry_fill_ids"] = [str(x) for x in (out.get("entry_fill_ids") or [])]
    out["fact_ids"] = [str(x) for x in (out.get("fact_ids") or [])]
    out["falsifiers"] = [str(x) for x in (out.get("falsifiers") or [])]
    out["exit_conditions"] = [str(x) for x in (out.get("exit_conditions") or [])]
    _parse_date(out["episode_open_date"])
    if out.get("episode_close_date"):
        _parse_date(out["episode_close_date"])
    _parse_dt(out["created_at"])
    existing = {
        item.get("thesis_id")
        for item in _read_lines(Path(store_dir) / THESES_FILENAME)
    }
    if out["thesis_id"] in existing:
        raise ThesisStoreError(
            f"thesis {out['thesis_id']} already recorded (append-only store)",
            code="duplicate_thesis",
        )
    _append_line(Path(store_dir) / THESES_FILENAME, out)
    return out  # type: ignore[return-value]


def load_theses(store_dir: Path) -> list[ThesisRecord]:
    return _read_lines(Path(store_dir) / THESES_FILENAME)  # type: ignore[return-value]


def thesis_for_episode(
    store_dir: Path, book: str, ticker: str, episode_open_date: str
) -> ThesisRecord | None:
    """The episode thesis for (book, ticker, episode_open_date), or None."""
    want = _parse_date(episode_open_date)
    for record in load_theses(store_dir):
        if (
            str(record.get("book")) == str(book)
            and str(record.get("ticker")) == str(ticker)
            and _parse_date(record.get("episode_open_date")) == want
        ):
            return record
    return None


def thesis_for_fill(store_dir: Path, fill_id: str) -> ThesisRecord | None:
    """The episode thesis whose entry fills include ``fill_id``, or None."""
    want = str(fill_id or "").strip()
    if not want:
        return None
    for record in load_theses(store_dir):
        if want in [str(x) for x in record.get("entry_fill_ids") or []]:
            return record
    return None


def _get_thesis(store_dir: Path, thesis_id: str) -> ThesisRecord:
    for record in load_theses(store_dir):
        if str(record.get("thesis_id")) == str(thesis_id):
            return record
    raise ThesisNotFound(f"no thesis {thesis_id!r} in store", code="thesis_not_found")


# ────────────────────────────── amendment records ───────────────────────────


def make_amendment_id(
    thesis_id: str, changes: Mapping, effective_at: str, accountable_decision_id: str
) -> str:
    """Deterministic amendment id: sha256 over the lineage key, truncated to 16 hex."""
    payload = _canon(
        {
            "thesis_id": thesis_id,
            "changes": dict(changes or {}),
            "effective_at": str(effective_at),
            "accountable_decision_id": accountable_decision_id,
        }
    )
    return "amendment.v1." + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _terminal_new_statuses(changes: Mapping) -> list[str]:
    """Terminal statuses introduced by an amendment's ``changes`` (if any)."""
    out: list[str] = []
    for change in (changes or {}).values():
        if isinstance(change, Mapping) and change.get("new") in TERMINAL_AMENDMENT_STATUSES:
            out.append(str(change.get("new")))
    return out


def record_amendment(
    store_dir: Path,
    amendment: Mapping,
    *,
    originating_decision_asof: str,
) -> AmendmentRecord:
    """Validate and append one AmendmentRecord.

    ``originating_decision_asof`` is the asof of the decision that opened the
    episode; an amendment effective before it is rejected
    (``retroactive_amendment_rejected``) so history cannot be rewritten under
    an earlier failed prediction.

    Seat ruling Q4: ``reason_code`` (closed enum ``AMENDMENT_REASON_CODES``) is
    REQUIRED for terminal amendments (INVALIDATED / EXCLUDED) and validated
    whenever present; ``note`` is optional free text (plain string at runtime;
    tests pass a digest-shaped mapping or omit it).
    """
    out = dict(amendment)
    thesis_id = str(out.get("thesis_id") or "")
    if not thesis_id:
        raise ThesisStoreError("amendment needs thesis_id", code="invalid_amendment")
    _get_thesis(store_dir, thesis_id)  # must reference a recorded episode
    changes = out.get("changes") or {}
    if not isinstance(changes, Mapping) or not changes:
        raise ThesisStoreError(
            "amendment changes must be a non-empty {field: {old, new}} mapping",
            code="invalid_amendment",
        )
    normalized_changes: dict[str, dict] = {}
    for field, change in changes.items():
        if (
            not isinstance(change, Mapping)
            or "old" not in change
            or "new" not in change
        ):
            raise ThesisStoreError(
                f"change for {field!r} must carry old and new", code="invalid_amendment"
            )
        normalized_changes[str(field)] = {"old": change.get("old"), "new": change.get("new")}
    out["changes"] = normalized_changes
    effective = _parse_dt(out.get("effective_at"))
    _parse_dt(out.get("recorded_at") or out.get("effective_at"))
    if not str(out.get("accountable_decision_id") or "").strip():
        raise ThesisStoreError(
            "amendment needs accountable_decision_id", code="invalid_amendment"
        )
    reason_code = out.get("reason_code")
    if reason_code is not None and str(reason_code) not in AMENDMENT_REASON_CODES:
        raise ThesisStoreError(
            f"reason_code {reason_code!r} is outside the closed enum "
            f"{AMENDMENT_REASON_CODES}",
            code="invalid_amendment",
        )
    if _terminal_new_statuses(normalized_changes) and not str(reason_code or "").strip():
        raise ThesisStoreError(
            "terminal amendment (INVALIDATED/EXCLUDED) requires a reason_code from "
            f"{AMENDMENT_REASON_CODES} (seat ruling Q4)",
            code="invalid_amendment",
        )
    note = out.get("note")
    if note is not None and not isinstance(note, (str, Mapping)):
        raise ThesisStoreError(
            "note must be a plain string or a digest-shaped mapping",
            code="invalid_amendment",
        )
    origin_asof = _parse_date(originating_decision_asof)
    if effective.date() < origin_asof:
        raise RetroactiveAmendmentError(
            "retroactive_amendment_rejected: amendment effective_at "
            f"{effective.date().isoformat()} precedes the originating decision's "
            f"asof {origin_asof.isoformat()}; history is not rewritten",
            code="retroactive_amendment_rejected",
        )
    out.setdefault("schema", AMENDMENT_SCHEMA_VERSION)
    if out["schema"] != AMENDMENT_SCHEMA_VERSION:
        raise ThesisStoreError(
            f"schema must be {AMENDMENT_SCHEMA_VERSION}", code="invalid_amendment"
        )
    out.setdefault(
        "amendment_id",
        make_amendment_id(
            thesis_id, out["changes"], str(out.get("effective_at")), str(out["accountable_decision_id"])
        ),
    )
    out["evidence_refs"] = [str(x) for x in (out.get("evidence_refs") or [])]
    _append_line(Path(store_dir) / AMENDMENTS_FILENAME, out)
    return out  # type: ignore[return-value]


def record_terminal_amendment(
    store_dir: Path,
    thesis_id: str,
    *,
    status: str,
    reason_code: str,
    effective_at: str,
    recorded_at: str,
    accountable_decision_id: str,
    reason: str | None = None,
    note: Any = None,
    evidence_refs: Sequence[str] = (),
    originating_decision_asof: str | None = None,
) -> AmendmentRecord:
    """Record an INVALIDATED / EXCLUDED terminal amendment.

    Seat ruling Q4: the terminal kind is the structured ``episode_status``
    change and ``reason_code`` is REQUIRED from the closed enum
    ``AMENDMENT_REASON_CODES``; ``reason``/``note`` stay free text (a future
    contract may require a linked fact outcome instead of prose).
    """
    if status not in TERMINAL_AMENDMENT_STATUSES:
        raise ThesisStoreError(
            f"terminal status must be one of {TERMINAL_AMENDMENT_STATUSES}",
            code="invalid_amendment",
        )
    record = _get_thesis(store_dir, thesis_id)
    current = _status_of(record, [])
    kwargs: dict[str, Any] = {}
    if originating_decision_asof is not None:
        kwargs["originating_decision_asof"] = originating_decision_asof
    return record_amendment(
        store_dir,
        {
            "thesis_id": thesis_id,
            "changes": {EPISODE_STATUS_FIELD: {"old": current, "new": status}},
            "reason": str(reason).strip() if reason else None,
            "reason_code": str(reason_code),
            "note": note,
            "evidence_refs": list(evidence_refs),
            "effective_at": effective_at,
            "recorded_at": recorded_at,
            "accountable_decision_id": accountable_decision_id,
            "schema": AMENDMENT_SCHEMA_VERSION,
        },
        **kwargs,
    )


def load_amendments(store_dir: Path) -> list[AmendmentRecord]:
    return _read_lines(Path(store_dir) / AMENDMENTS_FILENAME)  # type: ignore[return-value]


# ───────────────────────────── observation records ──────────────────────────


def record_observation(store_dir: Path, observation: Mapping) -> ObservationRecord:
    """Validate and append one per-cycle observation (seat ruling Q1).

    Conviction (and any other per-cycle holding-row observation) is recorded
    append-only under the caller's ``store_dir``; an observation never produces
    an amendment and never an UNRECORDED_AMENDMENT finding.
    """
    out = dict(observation)
    out["schema"] = OBSERVATION_SCHEMA_VERSION
    missing = [
        key
        for key in ("cycle_id", "asof", "field")
        if not str(out.get(key) or "").strip()
    ]
    if missing:
        raise ThesisStoreError(
            f"observation missing required fields: {missing}",
            code="invalid_observation",
        )
    if out.get("field") not in OBSERVED_ROW_FIELDS:
        raise ThesisStoreError(
            f"observation field {out.get('field')!r} is not a per-cycle observation "
            f"field {OBSERVED_ROW_FIELDS}; watched thesis fields change only through "
            "amendments",
            code="invalid_observation",
        )
    _parse_dt(out.get("asof"))
    if out.get("recorded_at"):
        _parse_dt(out.get("recorded_at"))
    out.setdefault("recorded_at", out["asof"])
    _append_line(Path(store_dir) / OBSERVATIONS_FILENAME, out)
    return out  # type: ignore[return-value]


def load_observations(store_dir: Path) -> list[ObservationRecord]:
    return _read_lines(Path(store_dir) / OBSERVATIONS_FILENAME)  # type: ignore[return-value]


def _resolve_thesis_id(store_dir: Path, rows: Sequence[Mapping]) -> str | None:
    """Best-effort thesis id for the episode the rows belong to (for observations).

    Matches book (when the rows agree on one) and ticker; prefers the episode
    whose open date is the latest at or before the later row's asof, falling
    back to the unique (book, ticker) record when no episode date fits.  A
    miss resolves to None — the observation is still recorded, with the null
    link carried honestly.
    """
    tickers = {str(row.get("ticker") or "") for row in rows if isinstance(row, Mapping)}
    tickers.discard("")
    if len(tickers) != 1:
        return None
    ticker = next(iter(tickers))
    books = {str(row.get("book") or "") for row in rows if isinstance(row, Mapping)}
    book = books.pop() if len(books) == 1 else ""
    candidates = [
        record
        for record in load_theses(store_dir)
        if str(record.get("ticker")) == ticker
        and (not book or str(record.get("book")) == book)
    ]
    if not candidates:
        return None
    asof = None
    for row in rows:
        if isinstance(row, Mapping) and row.get("asof"):
            try:
                parsed = _parse_date(row.get("asof"))
            except ThesisStoreError:
                parsed = None
            if parsed and (asof is None or parsed > asof):
                asof = parsed
    if asof is not None:
        opened = [
            record
            for record in candidates
            if _parse_date(record.get("episode_open_date")) <= asof
        ]
        if opened:
            return str(
                max(opened, key=lambda r: _parse_date(r.get("episode_open_date")))[
                    "thesis_id"
                ]
            )
    if len(candidates) == 1:
        return str(candidates[0].get("thesis_id"))
    return None


# ─────────────────────────── retrieval / as-of view ─────────────────────────


def _status_of(record: Mapping, applied: Sequence[Mapping]) -> str:
    """Local thesis status from the record + applicable amendments (spec §3.2).

    ACTIVE: record exists, unamended, episode open.  AMENDED: >=1 amendment.
    INVALIDATED / EXCLUDED: terminal amendments with those reasons — the latest
    status change wins.  (A closed, unamended episode still reports ACTIVE:
    the enum describes thesis-record state, and episode closure is visible in
    ``episode_close_date``.)
    """
    status = "ACTIVE"
    amended = False
    for amendment in applied:
        change = (amendment.get("changes") or {}).get(EPISODE_STATUS_FIELD)
        if change and change.get("new") in TERMINAL_AMENDMENT_STATUSES:
            status = change["new"]
        amended = True
    if amended and status == "ACTIVE":
        status = "AMENDED"
    return status


def _apply_change(record: dict, fields: dict, field: str, change: Mapping) -> None:
    """Fold one amendment change into the as-of record and flat field view."""
    new = change.get("new")
    if field == "falsifier":
        record["falsifiers"] = [str(new)]
        fields["falsifier"] = new
    elif field == "exit_plan":
        record["exit_conditions"] = [str(new)]
        fields["exit_plan"] = new
    elif field == "horizon":
        record["horizon"] = new
        fields["horizon"] = new
    elif field == "position_role":
        record["position_role"] = new
        fields["position_role"] = new
    else:
        # Any other recorded change travels on the flat view only.
        fields[field] = new


def thesis_as_of(store_dir: Path, thesis_id: str, at: Any) -> dict:
    """Non-retroactive view: every field as of ``at`` (spec §3.1).

    The latest amendment with ``effective_at <= at`` wins.  Returns the applied
    record, a flat canonical field view (``falsifier``/``exit_plan``/``horizon``/
    ``position_role``), the local thesis status, and the applied amendment ids.
    Conviction is not part of this view: it is per-cycle observation state
    (seat ruling Q1), never thesis state.
    """
    record = dict(_get_thesis(store_dir, thesis_id))
    at_dt = _parse_dt(at)
    applicable = sorted(
        (
            amendment
            for amendment in load_amendments(store_dir)
            if str(amendment.get("thesis_id")) == str(thesis_id)
            and _parse_dt(amendment.get("effective_at")) <= at_dt
        ),
        key=lambda a: (
            _parse_dt(a.get("effective_at")),
            _parse_dt(a.get("recorded_at") or a.get("effective_at")),
            str(a.get("amendment_id")),
        ),
    )
    falsifiers = [str(x) for x in record.get("falsifiers") or []]
    exits = [str(x) for x in record.get("exit_conditions") or []]
    fields: dict[str, Any] = {
        "falsifier": falsifiers[0] if falsifiers else None,
        "exit_plan": exits[0] if exits else None,
        "horizon": record.get("horizon"),
        "position_role": record.get("position_role"),
    }
    for amendment in applicable:
        for field, change in (amendment.get("changes") or {}).items():
            _apply_change(record, fields, str(field), change)
    return {
        "thesis_id": record.get("thesis_id"),
        "as_of": at_dt.date().isoformat() if not at_dt.tzinfo else at_dt.isoformat(),
        "record": record,
        "fields": fields,
        "local_thesis_status": _status_of(record, applicable),
        "applied_amendment_ids": [str(a.get("amendment_id")) for a in applicable],
    }


# ─────────────────────── UNRECORDED_AMENDMENT detection ─────────────────────


def _norm_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return _canon(value)


def materially_different(old: Any, new: Any) -> bool:
    """Whitespace-insensitive material difference between two recorded values."""
    return _norm_value(old) != _norm_value(new)


def thesis_fields_for_row_field(row_field: str) -> list[str]:
    """The watched thesis fields that map to one holding-row field (seat ruling Q1)."""
    return sorted(k for k, v in AMENDMENT_WATCHED_FIELDS.items() if v == row_field)


def _watched_diff(prior_row: Mapping, new_row: Mapping) -> tuple[dict, dict]:
    """Watched-field diff between two consecutive holding rows.

    Returns ``(changes, exempted)``.  ``changes`` holds one {old, new} entry per
    watched holding-row field that materially differs; ``exempted`` records the
    fields skipped by the seat-ruling-Q1 not-a-restatement rule (a null/absent
    ``proposed_weight`` in the later row).
    """
    changes: dict[str, dict] = {}
    exempted: dict[str, str] = {}
    for field in WATCHED_HOLDING_ROW_FIELDS:
        old = prior_row.get(field)
        new = new_row.get(field)
        if field == NOT_RESTATEMENT_FIELD and (new is None or str(new).strip() == ""):
            if materially_different(old, new):
                exempted[field] = (
                    "later row leaves proposed_weight null/absent: not restated, "
                    "not a change (seat ruling Q1)"
                )
            continue
        if materially_different(old, new):
            changes[field] = {"old": old, "new": new}
    return changes, exempted


def amendment_covers(
    amendment: Mapping,
    from_decision_id: str,
    to_decision_id: str,
    changed_fields: Sequence[str],
) -> bool:
    """Whether one explicit amendment record links the two decision ids and covers the diff.

    Linking means: ``accountable_decision_id`` is the later decision and the
    earlier decision id appears in ``evidence_refs`` (the record names the
    superseded decision).  Coverage means every materially changed watched
    field appears in ``changes``.
    """
    if str(amendment.get("accountable_decision_id")) != str(to_decision_id):
        return False
    refs = [str(x) for x in amendment.get("evidence_refs") or []]
    if str(from_decision_id) not in refs:
        return False
    return set(changed_fields).issubset(set(amendment.get("changes") or {}))


def detect_unrecorded_amendments(
    rows: Sequence[Mapping],
    amendments: Sequence[Mapping] = (),
) -> list[dict]:
    """Compare consecutive accepted holdings rows of one held episode (spec §3.3, ruling Q1).

    Emits a ``UNRECORDED_AMENDMENT`` finding (with the field diff) when any
    watched holding-row field materially differs between consecutive rows and
    no AmendmentRecord links the two decision ids.  Conviction is NOT watched
    and never appears in a finding: it is per-cycle observation state.  A
    null/absent later-row ``proposed_weight`` is a not-a-restatement, not a
    change.  Detection is a finding on the lineage, not a live-action veto.
    ``rows`` are already episode-scoped and in order; each carries at least
    ``ticker``, ``decision_id``, ``asof`` plus the watched holding-row fields.
    An explicit covering amendment suppresses the finding.
    """
    findings: list[dict] = []
    ordered = [row for row in (rows or ()) if isinstance(row, Mapping)]
    for prev, nxt in zip(ordered, ordered[1:]):
        diffs, exempted = _watched_diff(prev, nxt)
        if not diffs:
            continue
        from_id = str(prev.get("decision_id") or "")
        to_id = str(nxt.get("decision_id") or "")
        if any(
            amendment_covers(amendment, from_id, to_id, sorted(diffs))
            for amendment in (amendments or ())
        ):
            continue
        findings.append(
            {
                "code": UNRECORDED_AMENDMENT,
                "ticker": str(nxt.get("ticker") or prev.get("ticker") or ""),
                "from_decision_id": from_id,
                "to_decision_id": to_id,
                "from_asof": str(prev.get("asof") or ""),
                "to_asof": str(nxt.get("asof") or ""),
                "changes": diffs,
                "thesis_fields": sorted(
                    {name for field in diffs for name in thesis_fields_for_row_field(field)}
                ),
                "exempted_fields": exempted,
                "watched_holding_row_fields": list(WATCHED_HOLDING_ROW_FIELDS),
                "watched_fields": dict(AMENDMENT_WATCHED_FIELDS),
                "message": (
                    "watched thesis fields changed between consecutive accepted "
                    f"holdings rows ({', '.join(sorted(diffs))}) with no AmendmentRecord "
                    "linking the two decision ids; conviction is per-cycle observation "
                    "state and is never part of this finding (seat ruling Q1)"
                ),
            }
        )
    return findings


# ───────────────────────────── continuity verdict ───────────────────────────


def check_continuity(
    store_dir: Path,
    prior_row: Mapping,
    new_row: Mapping,
    *,
    thesis_id: str | None = None,
) -> dict:
    """Continuity verdict for two consecutive held-episode rows (seat ruling Q1).

    Reads the stored AmendmentRecords; when a watched thesis field changed
    between the rows and no record links the two decision ids the verdict is
    ``REJECTED_UNRECORDED_AMENDMENT`` carrying the ``UNRECORDED_AMENDMENT``
    finding, and the stored thesis is left untouched (``thesis_as_of`` keeps
    returning the pre-change falsifier/exit conditions).  A covering
    AmendmentRecord yields ``ACCEPTED_AMENDMENT_RECORDED``; no watched change
    yields ``ACCEPTED_NO_WATCHED_CHANGE``.  A conviction change between the
    rows is recorded as a ``pbr.thesis_observation.v1`` observation (append-only,
    ``cycle_id`` = the later row's decision id) and never amends anything.

    This is a shadow verdict on the lineage — never a live-action veto — and
    the only writes it performs are observation lines under ``store_dir``.
    """
    store_dir = Path(store_dir)
    prior_row = prior_row if isinstance(prior_row, Mapping) else {}
    new_row = new_row if isinstance(new_row, Mapping) else {}
    stored = load_amendments(store_dir)
    findings = detect_unrecorded_amendments([prior_row, new_row], stored)
    watched_changes, exempted = _watched_diff(prior_row, new_row)
    covered = bool(watched_changes) and not findings

    observations: list[dict] = []
    old_conviction = prior_row.get("conviction")
    new_conviction = new_row.get("conviction")
    conviction_changed = materially_different(old_conviction, new_conviction)
    if conviction_changed:
        resolved = thesis_id or _resolve_thesis_id(store_dir, [prior_row, new_row])
        observations.append(
            record_observation(
                store_dir,
                {
                    "thesis_id": resolved,
                    "cycle_id": str(new_row.get("decision_id") or ""),
                    "asof": str(new_row.get("asof") or ""),
                    "field": "conviction",
                    "value": new_conviction,
                    "previous_value": old_conviction,
                    "recorded_at": str(new_row.get("ts") or new_row.get("asof") or ""),
                },
            )
        )

    if findings:
        status = CONTINUITY_REJECTED_UNRECORDED
    elif covered:
        status = CONTINUITY_ACCEPTED_AMENDED
    else:
        status = CONTINUITY_ACCEPTED_UNCHANGED
    return {
        "status": status,
        "from_decision_id": str(prior_row.get("decision_id") or ""),
        "to_decision_id": str(new_row.get("decision_id") or ""),
        "watched_changes": watched_changes,
        "exempted_fields": exempted,
        "conviction_change": (
            {"old": old_conviction, "new": new_conviction}
            if conviction_changed
            else None
        ),
        "findings": findings,
        "observations": observations,
        "amendment_covered": covered,
        "thesis_unchanged": True,
        "watched_fields": dict(AMENDMENT_WATCHED_FIELDS),
    }


# ────────────────────────────── the retrieval view ──────────────────────────


def _provider_plan_status(ticker: str, provider_packet: Mapping | None) -> str:
    """Provider plan status derived ONLY from the Prophet packet (spec §3.2)."""
    if not isinstance(provider_packet, Mapping) or not provider_packet:
        return "unavailable"
    if provider_packet.get("feed_active") is not True:
        return "unavailable"
    held = [str(x) for x in provider_packet.get("held_without_active_plan") or []]
    if str(ticker) in held:
        return "held_without_active_plan"
    planned = [str(x) for x in provider_packet.get("management") or []] + [
        str(x) for x in provider_packet.get("discovery") or []
    ]
    if str(ticker) in planned:
        return "active_plan"
    # Feed live but the packet carries no row for this name: no plan information.
    return "unavailable"


def thesis_view(
    store_dir: Path,
    book: str,
    ticker: str,
    episode_open_date: str,
    provider_packet: Mapping | None,
    as_of: Any,
) -> dict:
    """Local thesis status + provider plan status + findings (spec §3.2).

    Separation rule (binding): ``NONE_RECORDED`` requires the absence of a
    local ThesisRecord and nothing else — a missing provider plan can never
    produce it.  The packet is context-only, so it can add a finding but never
    erase local state.  Symmetrically, a stale local thesis does not block an
    authorized exit (rule iv of spec §2.2 is owned by ``brain.facts``).
    """
    record = thesis_for_episode(store_dir, book, ticker, episode_open_date)
    as_of_dt = _parse_dt(as_of)
    findings: list[dict] = []
    if record is None:
        local_status = "NONE_RECORDED"
        applied: list[Mapping] = []
    else:
        thesis_id = str(record.get("thesis_id"))
        applicable = sorted(
            (
                amendment
                for amendment in load_amendments(store_dir)
                if str(amendment.get("thesis_id")) == thesis_id
                and _parse_dt(amendment.get("effective_at")) <= as_of_dt
            ),
            key=lambda a: (
                _parse_dt(a.get("effective_at")),
                _parse_dt(a.get("recorded_at") or a.get("effective_at")),
                str(a.get("amendment_id")),
            ),
        )
        local_status = _status_of(record, applicable)
        applied = applicable
    provider_status = _provider_plan_status(ticker, provider_packet)
    if record is not None and provider_status != "active_plan":
        findings.append(
            {
                "code": FINDING_PROVIDER_PLAN_MISSING,
                "detail": (
                    f"provider plan status is {provider_status!r} while a local episode "
                    f"thesis ({record.get('thesis_id')}) exists for {book}/{ticker}; a "
                    "missing provider plan is not evidence there was never a local thesis"
                ),
                "provider_plan_status": provider_status,
                "thesis_id": record.get("thesis_id"),
            }
        )
    return {
        "book": str(book),
        "ticker": str(ticker),
        "episode_open_date": _parse_date(episode_open_date).isoformat(),
        "as_of": as_of_dt.isoformat(),
        "local_thesis_status": local_status,
        "provider_plan_status": provider_status,
        "findings": findings,
        "thesis": record,
        "applied_amendment_ids": [str(a.get("amendment_id")) for a in applied],
    }
