"""Mastermind Bot Stage 00A: decision availability selector.

Pure, standard-library-only selection logic separating the last valid
originating portfolio decision (``last_valid``) from the latest safely
book-bound attempt (``latest_attempt``).

Contract highlights:
- inputs are supplied objects; no I/O, no implicit clock, no mutation;
- ``decision_rows`` is already book-bound by its canonical per-book journal
  source; ``bound_attempts`` must explicitly declare the matching book
  (titles/summaries never establish binding);
- future, malformed, nonfinite or ambiguous evidence is excluded and
  degrades ``coverage_status`` instead of being silently resolved;
- retained rows are deep copies; target_status, timestamps, ids, holdings
  and error fields are never rewritten (parent sanitizes for publication).

Date-only ``asof`` rows are interpreted on UTC day boundaries: such a row
is strictly ordered against instants outside its day and ambiguous against
instants inside it.  The fixed observation clock is the caller-supplied
``observed_at``.
"""

from __future__ import annotations

import copy
import datetime
import math
import re

__all__ = ["select_decision_records"]

_UTC = datetime.timezone.utc

_DECISION_ID_RE = re.compile(r"^decision\.v1\.[0-9a-f]{24}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_ACCEPTED_TARGET_STATUS = frozenset({"queued", "executed"})
_FAILED_TARGET_STATUS = "rejected_no_submission"
# Emitted by the shared regional decision boundary; prose and guessed flags are not evidence.
_CARRY_TARGET_STATUS = frozenset({"frozen_held_quote_fallback"})
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9_.:+-]{1,160}\Z")
_ERROR_FIELDS = ("error", "error_code", "adapter_error")
_LINEAGE_FIELDS = ("run_id", "submission_sha256", "target_sha256")
_BOOK_FIELDS = ("portfolio_id", "book")

# history_status -> baseline coverage_status when not "available".
_HISTORY_STATUS_COVERAGE = {
    "partial": "partial",
    "incomplete": "partial",
    "missing": "missing",
    "corrupt": "invalid",
    "invalid": "invalid",
    "unknown": "unknown",
    "unavailable": "unknown",
}

_COVERAGE_RANK = {
    "available": 0,
    "partial": 1,
    "missing": 2,
    "invalid": 3,
    "unknown": 4,
}

# Codes that do not qualify a clean history.  Every other issue code is a
# qualification: an "available" history with any other issue degrades to
# at least "partial".
_INFORMATIONAL_CODES = frozenset({"empty_history"})


def _worse(current, other):
    return current if _COVERAGE_RANK[current] >= _COVERAGE_RANK[other] else other


class _Candidate:
    """Internal per-row selection record (never exposed)."""

    __slots__ = ("row", "content", "run_id", "lo", "hi", "accepted", "kind")

    def __init__(self, row, content, run_id):
        self.row = row
        self.content = content
        self.run_id = run_id
        self.lo = None
        self.hi = None
        self.accepted = False
        self.kind = "unknown"


def _canonical(obj):
    """Order-independent structural key; bool vs numeric stay distinct."""
    if isinstance(obj, dict):
        return ("map", tuple(sorted((str(k), _canonical(v)) for k, v in obj.items())))
    if isinstance(obj, (list, tuple)):
        return ("seq", tuple(_canonical(v) for v in obj))
    if isinstance(obj, bool):
        return ("bool", obj)
    if isinstance(obj, float):
        return ("float", repr(obj))
    if isinstance(obj, int):
        return ("int", repr(obj))
    if obj is None:
        return ("none",)
    if isinstance(obj, str):
        return ("str", obj)
    return ("other", repr(obj))


def _row_faults(obj, active=None, depth=0):
    """Accept JSON-shaped values only, without calling repr on arbitrary objects."""
    if depth > 64:
        return {"row_shape_invalid"}
    if obj is None or isinstance(obj, (str, bool)):
        return set()
    if isinstance(obj, int):
        return {"row_shape_invalid"} if obj.bit_length() > 4096 else set()
    if isinstance(obj, float):
        return set() if math.isfinite(obj) else {"row_nonfinite"}
    if not isinstance(obj, (dict, list)):
        return {"row_shape_invalid"}
    active = set() if active is None else active
    identity = id(obj)
    if identity in active:
        return {"row_shape_invalid"}
    active.add(identity)
    faults = set()
    if isinstance(obj, dict):
        if any(not isinstance(key, str) for key in obj):
            faults.add("row_shape_invalid")
        values = obj.values()
    else:
        values = obj
    for value in values:
        faults.update(_row_faults(value, active, depth + 1))
    active.remove(identity)
    return faults


def _parse_aware_dt(value):
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(_UTC)
    except (ValueError, OverflowError):
        return None


def _parse_iso_date(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _DATE_RE.match(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _declared_books(row):
    """Explicit book declarations on a row; non-string values are malformed."""
    books = set()
    malformed = False
    for field in _BOOK_FIELDS:
        if field not in row:
            continue
        value = row[field]
        if isinstance(value, str) and value:
            books.add(value)
        else:
            malformed = True
    return books, malformed


def _is_accepted_origin(row):
    if row.get("decision_effective") is not True:
        return False
    if (not isinstance(row.get("target_status"), str)
            or row["target_status"] not in _ACCEPTED_TARGET_STATUS):
        return False
    if not isinstance(row.get("holdings"), list):
        return False
    decision_id = row.get("decision_id")
    if not isinstance(decision_id, str) or not _DECISION_ID_RE.fullmatch(decision_id):
        return False
    return True


def _acceptance_faults(row):
    """Safe codes for rows whose own metadata contradicts acceptance."""
    faults = set()
    effective = row.get("decision_effective")
    if "decision_effective" in row and not isinstance(effective, bool):
        faults.add("invalid_decision_fields")
    status = row.get("target_status")
    if status is not None and not isinstance(status, str):
        faults.add("invalid_decision_fields")
    status_is_accepted = isinstance(status, str) and status in _ACCEPTED_TARGET_STATUS
    if status_is_accepted != (effective is True):
        faults.add("invalid_decision_fields")
    if effective is True and not isinstance(row.get("holdings"), list):
        faults.add("invalid_decision_fields")
    decision_id = row.get("decision_id")
    if decision_id is not None and not (
        isinstance(decision_id, str) and _DECISION_ID_RE.fullmatch(decision_id)
    ):
        faults.add("invalid_decision_fields")
    return faults


def _classify(cand):
    row = cand.row
    if cand.accepted:
        if any(bool(row.get(f)) for f in _ERROR_FIELDS):
            return "accepted_with_error"
        return "accepted"
    status = row.get("target_status")
    if status == _FAILED_TARGET_STATUS:
        return "failed"
    if isinstance(status, str) and status in _CARRY_TARGET_STATUS:
        return "protective_carry"
    return "unknown"


def _lineage_status(last, history_status):
    if last is None:
        return "unavailable"
    if history_status in ("missing", "corrupt"):
        return "unavailable"
    row = last.row
    if (isinstance(row.get("run_id"), str) and _RUN_ID_RE.fullmatch(row["run_id"])
            and all(isinstance(row.get(field), str) and _SHA256_RE.fullmatch(row[field])
                    for field in ("submission_sha256", "target_sha256"))):
        return "complete"
    return "partial"


def _require_observed_at(value):
    parsed = _parse_aware_dt(value)
    if parsed is None:
        raise ValueError("observed_at must be a timezone-aware ISO8601 timestamp")
    return parsed


def _normalize_sequence(value, *, optional, missing_code, shape_code, element_code, issues):
    if value is None:
        if not optional:
            issues.add(missing_code)
        return [], False
    if isinstance(value, (list, tuple)):
        rows = []
        for item in value:
            if isinstance(item, dict):
                rows.append(item)
            else:
                issues.add(element_code)
        return rows, False
    issues.add(shape_code)
    return [], True


def _build_candidates(rows, attempts, book, issues):
    candidates = []
    foreign_books = {}
    evidence = [(row, "journal") for row in rows]
    evidence.extend((row, "attempt") for row in attempts)
    for row, source in evidence:
        faults = _row_faults(row)
        if faults:
            issues.update(faults)
            continue
        books, malformed = _declared_books(row)
        declared_run = row.get("run_id")
        if isinstance(declared_run, str) and declared_run and any(b != book for b in books):
            foreign_books[declared_run] = books
        if malformed:
            issues.add("row_binding_malformed")
            continue
        if len(books) > 1:
            issues.add("binding_contradiction")
            continue
        if books:
            declared = next(iter(books))
            if declared != book:
                code = "foreign_book_row" if source == "journal" else "attempt_foreign_book"
                issues.add(code)
                run_id = row.get("run_id")
                if isinstance(run_id, str) and run_id:
                    foreign_books[run_id] = declared
                continue
        if source == "attempt" and row.get("portfolio_id") != book:
            # The global run-log has no canonical portfolio_id. A title or a guessed book alias
            # cannot bind it; separately supplied attempts need that explicit producer field.
            issues.add("attempt_unbound")
            continue
        run_id = row.get("run_id")
        run_id = run_id if isinstance(run_id, str) and run_id else None
        candidates.append(_Candidate(row, _canonical(row), run_id))
    return candidates, foreign_books


def _dedupe(candidates):
    seen = set()
    unique = []
    for cand in candidates:
        if cand.content in seen:
            continue
        seen.add(cand.content)
        unique.append(cand)
    return unique


def _drop_identity_conflicts(candidates, foreign_books, issues):
    by_run, by_decision = {}, {}
    for cand in candidates:
        if cand.run_id:
            by_run.setdefault(cand.run_id, []).append(cand)
        decision_id = cand.row.get("decision_id")
        if isinstance(decision_id, str) and _DECISION_ID_RE.fullmatch(decision_id):
            by_decision.setdefault(decision_id, []).append(cand)
    conflicted_runs = {
        run_id for run_id, group in by_run.items()
        if len({cand.content for cand in group}) > 1 or run_id in foreign_books
    }
    conflicted_decisions = set()
    for decision_id, group in by_decision.items():
        for field in ("asof", "submission_sha256", "target_sha256", "holdings", "summary"):
            values = {_canonical(c.row[field]) for c in group if c.row.get(field) is not None}
            if len(values) > 1:
                conflicted_decisions.add(decision_id)
                break
    if conflicted_runs or conflicted_decisions:
        issues.add("identity_conflict")
    return [c for c in candidates if c.run_id not in conflicted_runs and not (
        isinstance(c.row.get("decision_id"), str)
        and c.row["decision_id"] in conflicted_decisions)]


def _row_clock(row, observed):
    asof = row.get("asof")
    if asof is not None:
        parsed_day = _parse_iso_date(asof)
        if parsed_day is None:
            return None, None, "row_asof_malformed"
        if parsed_day > observed.date():
            return None, None, "row_future_event"
    # A supplied malformed/null ts is not permission to silently switch clocks.
    if "ts" in row:
        parsed = _parse_aware_dt(row["ts"])
        if parsed is None:
            return None, None, "row_ts_malformed"
        if parsed > observed:
            return None, None, "row_future_event"
        return parsed, parsed, None
    asof = row.get("asof")
    if asof is not None and asof != "":
        day = _parse_iso_date(asof)
        if day is None:
            return None, None, "row_asof_malformed"
        lo = datetime.datetime(day.year, day.month, day.day, tzinfo=_UTC)
        if lo > observed:
            return None, None, "row_future_event"
        try:
            hi = lo + datetime.timedelta(days=1)
        except OverflowError:
            return None, None, "row_asof_malformed"
        return lo, hi, None
    return None, None, "row_clock_missing"


def _apply_clocks(candidates, observed, issues):
    kept = []
    for cand in candidates:
        lo, hi, code = _row_clock(cand.row, observed)
        if code is not None:
            issues.add(code)
            continue
        cand.lo = lo
        cand.hi = hi
        cand.accepted = _is_accepted_origin(cand.row)
        issues.update(_acceptance_faults(cand.row))
        kept.append(cand)
    return kept


def _clock_cmp(a, b):
    """-1 / 0 / 1, or None when interval overlap leaves order unknowable."""
    if a.lo == b.lo and a.hi == b.hi:
        return 0
    if a.hi < b.lo or (a.hi == b.lo and a.lo < a.hi):
        return -1
    if b.hi < a.lo or (b.hi == a.lo and b.lo < b.hi):
        return 1
    return None


def _select_latest(candidates):
    """Unique interval-maximal candidate, or (None, True) on a true tie."""
    if not candidates:
        return None, False
    survivors = []
    for cand in candidates:
        dominated = False
        for other in candidates:
            if other is cand:
                continue
            order = _clock_cmp(cand, other)
            if order is not None and order < 0:
                dominated = True
                break
        if not dominated:
            survivors.append(cand)
    if len(survivors) == 1:
        return survivors[0], False
    if not survivors:
        return None, False
    # Exact duplicates were already removed, so several survivors mean
    # conflicting equal-clock or overlapping-interval evidence.
    return None, True


def select_decision_records(
    portfolio_id,
    decision_rows,
    *,
    observed_at,
    bound_attempts=None,
    history_status="available",
):
    """Select the last valid originating decision and latest bound attempt.

    ``portfolio_id`` is the requested book; ``decision_rows`` are journal
    rows already bound to it.  ``bound_attempts`` are separately supplied
    rows that must each explicitly declare the same book.  ``observed_at``
    is the fixed timezone-aware observation instant.  ``history_status``
    qualifies the upstream history ("available", "partial", "incomplete",
    "missing", "corrupt", or any other string meaning unknown).

    Raises ValueError only for caller-contract violations of
    ``portfolio_id``, ``observed_at`` or ``history_status`` types; all row
    data problems are surfaced through ``issues`` and ``coverage_status``.
    """
    observed = _require_observed_at(observed_at)
    if not isinstance(portfolio_id, str) or not portfolio_id:
        raise ValueError("portfolio_id must be a non-empty string")
    if not isinstance(history_status, str):
        raise ValueError("history_status must be a string")

    issues = set()

    base = "available"
    if history_status != "available":
        base = _HISTORY_STATUS_COVERAGE.get(history_status, "unknown")
        if base == "unknown":
            issues.add("history_unknown_status")

    rows, rows_shape_bad = _normalize_sequence(
        decision_rows,
        optional=False,
        missing_code="rows_missing",
        shape_code="rows_shape_invalid",
        element_code="row_shape_invalid",
        issues=issues,
    )
    attempts, attempts_shape_bad = _normalize_sequence(
        bound_attempts,
        optional=True,
        missing_code="attempts_missing",
        shape_code="attempts_shape_invalid",
        element_code="attempt_shape_invalid",
        issues=issues,
    )
    if rows_shape_bad or attempts_shape_bad:
        base = _worse(base, "invalid")
    if decision_rows is None:
        base = _worse(base, "missing")
    elif history_status == "missing" and rows:
        issues.add("history_rows_contradiction")
        base = _worse(base, "invalid")

    candidates, foreign_books = _build_candidates(rows, attempts, portfolio_id, issues)
    candidates = _dedupe(candidates)
    candidates = _drop_identity_conflicts(candidates, foreign_books, issues)
    candidates = _apply_clocks(candidates, observed, issues)

    latest, latest_tie = _select_latest(candidates)
    if latest is not None:
        latest.kind = _classify(latest)
    if latest_tie:
        issues.add("ambiguous_latest_tie")

    accepted = [cand for cand in candidates if cand.accepted]
    last, last_tie = _select_latest(accepted)
    if last_tie:
        issues.add("ambiguous_latest_tie")

    coverage = base
    if history_status == "available" and not rows:
        issues.add("empty_history")
    if coverage == "available" and (issues - _INFORMATIONAL_CODES):
        coverage = "partial"

    return {
        "last_valid": copy.deepcopy(last.row) if last is not None else None,
        "latest_attempt": copy.deepcopy(latest.row) if latest is not None else None,
        "latest_attempt_kind": latest.kind if latest is not None else "unknown",
        "coverage_status": coverage,
        "attempt_coverage": "partial",
        "issues": sorted(issues),
        "origin_lineage_status": _lineage_status(last, history_status),
    }
