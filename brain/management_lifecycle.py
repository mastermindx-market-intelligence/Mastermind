"""brain.management_lifecycle — ONE honest disposition per manager cycle (READ-ONLY projection).

A manager cycle is one scheduled portfolio decision for one book on one day. Its truth lives in
three separate existing records, none of which answers the operator's question by itself:

  1. the scheduler run ledger — ``run_started`` / ``run_finished`` / ``run_skipped`` records
     written by ``control_plane.run_ledger`` through ``app.scheduler._ledger_start`` /
     ``_ledger_end``, whose status/reason/target vocabulary comes from ``_brain_job_outcome``;
  2. the submission boundary — ``packet_accepted`` written by ``control_plane.packet_gate``;
  3. the per-book decision row — ``bot.decision_rows``, one row per (book, asof), whose
     ``target_status`` a later settlement may advance (queued -> executed) and whose earlier row a
     later *substantive* run may replace.

On 2026-10-16 a whole CN cycle vanished with no record at all, which is exactly what this module
is for: the absence of evidence is reported as a state, not silently dropped.

IT IS A PROJECTION, NOT A SECOND STATE MACHINE
----------------------------------------------
* PURE — every input is injected (``run_events``, ``decision_rows``, ``now``); nothing is read
  from or written to disk, no clock is read from the wall, no state is kept between calls. Same
  inputs, same output, every time.
* INERT — nothing here may ever be read by retry, failover, scheduling or submission code. The
  deterministic engines own sizing, the ledger owns run truth, the retry policy owns re-runs.
  This module only NAMES what already happened, for humans and dashboards.
  ``classify_failure_text`` is DISPLAY ONLY: a provider-text guess never arms anything, and the
  machine-readable outcome stays the ledger's own status/reason.
* CONSERVATIVE — it never borrows evidence across cycles. Records are matched by job/book identity
  and by run_id, inside a time window anchored on the opportunity (see ``_records`` / ``_match_*``).
  Anything it cannot attribute becomes ``incomplete_uncertain`` with a reason that says which
  record is missing; a decision row that belongs to a *different* run of the same date is reported
  through ``decision_row_superseded`` instead of being adopted.

Vocabulary is copied from ``app.scheduler._brain_job_outcome`` and
``brain.decision_submission.ACCEPTED_TARGET_STATUSES`` deliberately WITHOUT importing either, so
this read plane cannot create an import edge into the execution plane. The drift guard lives in
``tests/test_management_lifecycle.py``: if an accepted target status changes there and this module
was not updated, that test fails.

    from brain import management_lifecycle as ML
    rows = ML.project_cycles(opportunities, run_events, decision_rows, now=now)

Best-effort throughout: a malformed or missing record degrades the disposition toward
``incomplete_uncertain``; it never raises and never invents a success.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA = "mastermind.bot.management_cycle_disposition.v1"

STATES = (
    "not_due",
    "disabled",
    "started",
    "accepted_no_change",
    "accepted_change",
    "rejected",
    "failed",
    "incomplete_uncertain",
)

# Defaults mirror the scheduler it observes: the book jobs are registered with
# misfire_grace_time=3600, and a Brain run that has not finished by ~2 h is not legitimately still
# running. An opportunity may override either.
DEFAULT_START_GRACE_S = 3600.0
DEFAULT_FINISH_DEADLINE_S = 7200.0
START_WINDOW_BACK_S = 60.0     # a start stamp may land a minute before the cron instant
EVIDENCE_TAIL_S = 60.0         # boundary/row evidence may land a minute after the finish

# Reasons the ledger records for a job that legitimately had nothing to decide (status "skip").
LEDGER_SKIP_REASONS = frozenset({
    "market_closed",
    "nothing_queued",
    "legacy_etf_migration_pending",
})
# Reasons the ledger records for a run that definitively did not produce a decision.
LEDGER_FAILURE_REASONS = frozenset({
    "rejected_execution_error",
    "runner_failed",
    "invalid_result",
    "inconsistent_result",
})
# Reasons the ledger records when the run's own projection is unfinished or unproven.
LEDGER_UNCERTAIN_REASONS = frozenset({
    "projection_failed",
    "settlement_finalization_incomplete",
})
# Accepted-target statuses (mirrors brain.decision_submission.ACCEPTED_TARGET_STATUSES).
ACCEPTED_TARGETS = frozenset({"queued", "executed"})

DISPLAY_ONLY_FAILURE_KINDS = ("credential", "quota", "availability", "transport", "application",
                              "unclassified")

# Display-only failure-text labels, in precedence order. Case-insensitive needle match, first hit
# wins; the needle (never the caller's text) is what we return as evidence.
FAILURE_NEEDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("credential", ("401", "revoked", "authentication_failed", "invalid api key", "unauthorized")),
    ("quota", ("weekly limit", "session limit", "usage limit", "rate_limit", "429")),
    ("availability", ("all pool keys cooling", "all pool keys dead", "overloaded", "529")),
    ("transport", ("timeout", "connection reset", "cliconnectionerror")),
)
# The SDK reports subtype "success" on an error result. The word is not evidence of success.
ERROR_RESULT_MARKER = "error result: success"
EVIDENCE_MAX_CHARS = 80


# ---------------------------------------------------------------------------
# input coercion (never mutates a caller record; never raises)
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    """Caller text as a stripped string; anything absent becomes ""."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _clock(value: Any) -> datetime | None:
    """Parse an ISO string or datetime into an aware UTC datetime, or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _seconds(value: Any, default: float) -> float:
    """A non-negative window in seconds, falling back to the documented default."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return float(default)
    if seconds != seconds or seconds < 0:  # NaN / negative windows are not usable
        return float(default)
    return seconds


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extra(event: dict) -> dict:
    nested = event.get("extra")
    return nested if isinstance(nested, dict) else {}


def _day(value: datetime | None) -> str | None:
    return value.date().isoformat() if value is not None else None


# ---------------------------------------------------------------------------
# display-only failure labelling (NEVER a retry/failover input)
# ---------------------------------------------------------------------------

def classify_failure_text(text: str | None) -> dict:
    """Label one failure string for DISPLAY. Returns ``{"kind", "evidence", "label_misleading"}``.

    Case-insensitive, first match wins, in the order credential -> quota -> availability ->
    transport. ``evidence`` is the matched needle, never the caller's full text, capped at
    :data:`EVIDENCE_MAX_CHARS`. An error result whose subtype reads "success" is
    ``unclassified`` with ``label_misleading`` True — that word is not evidence of success.
    """
    haystack = _text(text).lower()
    if not haystack:
        return {"kind": "unclassified", "evidence": None, "label_misleading": False}
    for kind, needles in FAILURE_NEEDLES:
        for needle in needles:
            if needle in haystack:
                return {"kind": kind, "evidence": _clip(needle), "label_misleading": False}
    if ERROR_RESULT_MARKER in haystack:
        return {"kind": "unclassified", "evidence": _clip(ERROR_RESULT_MARKER),
                "label_misleading": True}
    return {"kind": "unclassified", "evidence": None, "label_misleading": False}


def _clip(value: str) -> str:
    return value[:EVIDENCE_MAX_CHARS]


# ---------------------------------------------------------------------------
# matching (identity first, then time window; never borrow across cycles)
# ---------------------------------------------------------------------------

def _records(events: list[dict], *, kind: str, job: str = "", book: str = "",
             lo: datetime | None = None, hi: datetime | None = None) -> list[tuple]:
    """Time-sorted ``(ts, index, event)`` triples for one kind inside ``[lo, hi]``.

    A job-scoped ledger kind matches on ``job`` when the record carries one and on ``book``
    otherwise; a book-scoped kind (the submission boundary) must carry the same book. A record
    without a parseable ``ts`` is not evidence about when it happened, so it is excluded.
    """
    scoped = [
        (index, event)
        for index, event in enumerate(events)
        if _text(event.get("kind")).lower() == kind and _in_scope(event, job=job, book=book)
    ]
    stamped = [(_clock(event.get("ts")), index, event) for index, event in scoped]
    return sorted(
        (ts, index, event)
        for ts, index, event in stamped
        if ts is not None and (lo is None or ts >= lo) and (hi is None or ts <= hi)
    )


def _in_scope(event: dict, *, job: str, book: str) -> bool:
    if job:
        record_job = _text(event.get("job"))
        if record_job:
            return record_job == job
    if book:
        return _text(event.get("book")) == book
    return not job


def _same_run(event: dict, run_id: str) -> bool:
    """run_finished belongs to exactly the run we matched, by its own ``extra.run_id``."""
    return bool(run_id) and _text(_extra(event).get("run_id")) == run_id


def _evidence_clock(events: list[dict], rows: list[dict]) -> datetime | None:
    """Freshest stamp any record carries — the deterministic stand-in when ``now`` is unusable."""
    stamps = [_clock(event.get("ts")) for event in events] + [_clock(row.get("ts")) for row in rows]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return max(stamps) if stamps else None


# ---------------------------------------------------------------------------
# the projection
# ---------------------------------------------------------------------------

def project_cycle(opportunity: dict, run_events: list[dict], decision_rows: list[dict], *,
                  now: datetime, evidence_text: str | None = None) -> dict:
    """One disposition dict for one (job, book, due_at) cycle. Pure; never raises.

    ``opportunity`` carries job / book / due_at / enabled / start_grace_s / finish_deadline_s
    (grace default 3600 = the scheduler's misfire grace, deadline default 7200). ``run_events``
    and ``decision_rows`` are the existing records, injected; ``now`` is the clock;
    ``evidence_text`` is an optional operator-visible failure string (display only).
    """
    return _project(opportunity, run_events, decision_rows, now=now, evidence_text=evidence_text)


def project_cycles(opportunities: list[dict], run_events: list[dict], decision_rows: list[dict], *,
                   now: datetime, evidence_by_run_id: dict | None = None) -> list[dict]:
    """One disposition per opportunity, in the caller's order.

    ``evidence_by_run_id`` maps a scheduler OR brain run id to a failure string; each cycle picks
    its own entry by its matched run ids, so one operator note never labels another cycle.
    """
    table = evidence_by_run_id if isinstance(evidence_by_run_id, dict) else {}
    # One row per opportunity, in the caller's order — a malformed opportunity is projected too,
    # so a bad schedule entry shows up as an uncertain cycle instead of silently disappearing.
    return [
        _project(opportunity, run_events, decision_rows, now=now, evidence_by_run_id=table)
        for opportunity in (opportunities or [])
    ]


def _project(opportunity: dict, run_events: list[dict], decision_rows: list[dict], *,
             now: Any, evidence_text: str | None = None,
             evidence_by_run_id: dict | None = None) -> dict:
    opp = opportunity if isinstance(opportunity, dict) else {}
    events = [event for event in (run_events or []) if isinstance(event, dict)]
    rows = [row for row in (decision_rows or []) if isinstance(row, dict)]

    job, book = _text(opp.get("job")), _text(opp.get("book"))
    due = _clock(opp.get("due_at"))
    grace = _seconds(opp.get("start_grace_s"), DEFAULT_START_GRACE_S)
    deadline = _seconds(opp.get("finish_deadline_s"), DEFAULT_FINISH_DEADLINE_S)
    out = _blank(job, book, due)

    if not opp.get("enabled", True):
        return _fill(out, state="disabled")

    moment = _clock(now) or _evidence_clock(events, rows) or due
    if due is None or moment is None:
        # Without a due instant there is no window to attribute anything to. Say so, loudly.
        return _fill(out, state="incomplete_uncertain", reason="missing_due_at")
    if moment < due:
        return _fill(out, state="not_due")

    lo = due - timedelta(seconds=START_WINDOW_BACK_S)
    hi = due + timedelta(seconds=grace)

    starts = _records(events, kind="run_started", job=job, book=book, lo=lo, hi=hi)
    if not starts:
        locked = [triple for triple in _records(
            events, kind="run_skipped", job=job, book=book, lo=lo, hi=hi)
            if _text(triple[2].get("status")) == "lock_held"]
        if locked:
            out["sources"] = out["sources"] + ["run_skipped"]
            # The book lock was held: something else owned the slot; we cannot tell what it decided.
            return _fill(out, state="incomplete_uncertain", reason="skipped_lock_held")
        if moment <= hi:
            return _fill(out, state="incomplete_uncertain", reason="awaiting_start")
        return _fill(out, state="incomplete_uncertain", reason="no_start_record", overdue=True)

    started_ts, _started_index, started = starts[0]
    scheduler_run_id = _text(_extra(started).get("run_id")) or None
    out["sources"] = out["sources"] + ["run_started"]
    out["scheduler_run_id"] = scheduler_run_id

    finishes = [
        triple for triple in _records(events, kind="run_finished", lo=started_ts)
        if _same_run(triple[2], scheduler_run_id or "")
    ]
    finish = finishes[0][2] if finishes else None
    finish_ts = _clock(finish.get("ts")) if finish is not None else None
    if finish is not None:
        out["sources"] = out["sources"] + ["run_finished"]
    tail = (finish_ts or moment) + timedelta(seconds=EVIDENCE_TAIL_S)

    accepted = _records(events, kind="packet_accepted", book=book, lo=started_ts, hi=tail)
    packet = accepted[-1][2] if accepted else None
    packet_extra = _extra(packet) if packet is not None else {}
    brain_run_id = _text(packet_extra.get("run_id")) or None
    packet_id = _text(packet_extra.get("packet_id")) or None
    packet_asof = _text(packet_extra.get("asof")) or None
    if packet is not None:
        out["sources"] = out["sources"] + ["packet_accepted"]
        out["brain_run_id"], out["packet_id"], out["asof"] = brain_run_id, packet_id, packet_asof

    cycle_asofs = [value for value in (packet_asof, _day(due)) if value]
    row = _match_row(rows, book=book, brain_run_id=brain_run_id, lo=started_ts, hi=tail,
                     asofs=cycle_asofs)
    if row is None and brain_run_id:
        out["decision_row_superseded"] = _was_superseded(
            rows, book=book, brain_run_id=brain_run_id, asofs=cycle_asofs)
    if row is not None:
        out["sources"] = out["sources"] + ["decision_row"]
        out["brain_run_id"] = out["brain_run_id"] or _text(row.get("run_id")) or None
        out["packet_id"] = out["packet_id"] or _text(row.get("packet_id")) or None
        out["asof"] = out["asof"] or _text(row.get("asof")) or None

    hint = _hint(evidence_text, evidence_by_run_id, out["scheduler_run_id"], out["brain_run_id"])

    if finish is None:
        if moment <= started_ts + timedelta(seconds=deadline):
            return _fill(out, state="started")
        return _fill(out, state="incomplete_uncertain", reason="no_finish_record", overdue=True)

    status = _text(finish.get("status")).lower()
    extra = _extra(finish)
    reason = _text(extra.get("reason")).lower()
    target = _text(extra.get("target_status")).lower()
    return _map_finished(out, status=status, reason=reason, target=target, row=row, hint=hint)


def _blank(job: str, book: str, due: datetime | None) -> dict:
    """The disposition record: every documented key present, with nothing yet claimed.

    schema, job, book, due_at, state, reason, failure_kind, failure_evidence, label_misleading,
    settlement, scheduler_run_id, brain_run_id, packet_id, asof, decision_row_superseded, overdue,
    sources — the key set tests/test_management_lifecycle.py pins.
    """
    return {
        "schema": SCHEMA,
        "job": job or None,
        "book": book or None,
        "due_at": _iso(due),
        "state": None,
        "reason": None,
        "failure_kind": None,
        "failure_evidence": None,
        "label_misleading": False,
        "settlement": None,
        "scheduler_run_id": None,
        "brain_run_id": None,
        "packet_id": None,
        "asof": None,
        "decision_row_superseded": False,
        "overdue": False,
        "sources": [],
    }


def _fill(out: dict, **fields: Any) -> dict:
    out.update(fields)
    return out


def _match_row(rows: list[dict], *, book: str, brain_run_id: str | None,
               lo: datetime, hi: datetime, asofs: list[str]) -> dict | None:
    """The decision row belonging to THIS cycle, or None.

    Identity wins: with a brain run id the row must carry exactly that run_id. Only when the
    submission boundary left no run id do we fall back to the row written inside this cycle's own
    time window. A row for the same date belonging to another run is never used here.
    """
    for_book = [row for row in rows if _text(row.get("book")) == book]
    if brain_run_id:
        exact = [row for row in for_book if _text(row.get("run_id")) == brain_run_id]
        if not exact:
            return None
        return _newest_row(exact)
    stamped = [(_clock(row.get("ts")), index, row) for index, row in enumerate(for_book)]
    inside = [item for item in stamped if item[0] is not None and lo <= item[0] <= hi]
    if not inside:
        return None
    return _newest_row([row for _ts, _index, row in inside])


def _newest_row(rows: list[dict]) -> dict | None:
    """The most recently stamped row — settlement rewrites the row it advances in place."""
    stamped = [(_clock(row.get("ts")), index, row) for index, row in enumerate(rows)]
    usable = [item for item in stamped if item[0] is not None]
    if usable:
        return max(usable)[2]
    return rows[-1] if rows else None


def _was_superseded(rows: list[dict], *, book: str, brain_run_id: str, asofs: list[str]) -> bool:
    """True when this date's only row belongs to a DIFFERENT run (a later run replaced it).

    ``bot.decision_rows.replace_for_asof`` lets a later substantive run drop the earlier row for
    the same ``asof``. That is a real fact about the cycle — its own row is gone — and it must be
    reported as such instead of letting the replacement row speak for this cycle. Only the
    boundary's own run id can prove a row is foreign: with no brain run id this stays False and
    an out-of-window row counts as unmatched, never adopted.
    """
    wanted = set(asofs)
    for row in rows:
        if _text(row.get("book")) != book:
            continue
        if _text(row.get("asof")) not in wanted:
            continue
        if _text(row.get("run_id")) != brain_run_id:
            return True
    return False


def _hint(evidence_text: str | None, table: dict | None, *run_ids: str | None) -> str | None:
    """This cycle's own operator note: the explicit text, else the table entry for its run ids."""
    if evidence_text is not None:
        return evidence_text
    if not isinstance(table, dict):
        return None
    for run_id in run_ids:
        if run_id and run_id in table:
            return table[run_id]
    return None


def _map_finished(out: dict, *, status: str, reason: str, target: str,
                  row: dict | None, hint: str | None) -> dict:
    """Ledger status/reason/target, refined by the matched decision row. First match wins."""
    if status == "skip" and reason in LEDGER_SKIP_REASONS:
        return _fill(out, state="not_due", reason=reason)
    if reason == "cost_capped":
        return _fill(out, state="rejected", reason="cost_capped")
    if status == "ok" and target in ACCEPTED_TARGETS:
        return _map_accepted(out, target=target, row=row)
    if reason == "missing_submission":
        labelled = classify_failure_text(hint or (row or {}).get("error"))
        return _fill(out, state="failed", reason=reason, failure_kind=labelled["kind"],
                     failure_evidence=labelled["evidence"],
                     label_misleading=labelled["label_misleading"])
    if reason in LEDGER_FAILURE_REASONS or (status == "error" and not reason):
        # The exception path ends the ledger with status "error" and no reason/target at all.
        # kind "application" is the ledger's own claim: the run raised. No provider needle was
        # matched, so failure_evidence stays empty rather than smuggling raw text into a label.
        return _fill(out, state="failed", reason=reason or None, failure_kind="application",
                     failure_evidence=None, label_misleading=False)
    if reason in LEDGER_UNCERTAIN_REASONS:
        # Checked before the rejection bucket on purpose: projection_failed /
        # settlement_finalization_incomplete means the run's own record did not land, and an
        # unfinished projection is never a clean rejection, rejected_* target notwithstanding.
        return _fill(out, state="incomplete_uncertain", reason=reason)
    if status == "warn" and (target.startswith("rejected_") or target.startswith("frozen_")
                             or reason.startswith("rejected_") or reason.startswith("frozen_")):
        # The ledger's own warn bucket: the gate refused or froze the proposal. Nothing accepted.
        return _fill(out, state="rejected", reason=target or reason)
    return _fill(out, state="incomplete_uncertain", reason="unrecognized_outcome")


def _map_accepted(out: dict, *, target: str, row: dict | None) -> dict:
    """A target was accepted at the boundary. Whether it changes holdings is a settlement fact.

    ``queued`` means the target waits for the next session: a change is intended, the outcome is
    not yet known, so it is NEVER "no change". Only a row that has actually settled with zero fills
    earns ``accepted_no_change``.
    """
    row_target = _text((row or {}).get("target_status")).lower()
    settled_target = row_target if row_target in ACCEPTED_TARGETS else target
    if settled_target == "queued":
        return _fill(out, state="accepted_change", settlement="pending")
    executed_n = _as_int((row or {}).get("executed_n"))
    if executed_n == 0:
        return _fill(out, state="accepted_no_change", settlement="settled")
    return _fill(out, state="accepted_change", settlement="settled")
