"""Deterministic performance projection for Mastermind Bot Renewal Stage 00B.

Pure standard library: no files, network, model, clock, NumPy, or account
helpers.  Every input is an already-loaded Python object and ``today`` is an
explicit ISO date supplied by the caller, so the module stays reproducible and
side-effect free.  Inputs are never mutated and no output object aliases an
input object.

Qualification philosophy
------------------------
A safe zero is a real observation, not a missing one.  Numeric observations
must be finite ``int``/``float`` and never ``bool`` or numeric strings.  A mark
is only ever a caller supplied price; ``avg_cost`` is deliberately never read,
and a historical NAV row may only serve as a *last recorded snapshot* with its
own matching cash and its own date.  Returns are only compared against a
benchmark when both series share an exact start (inception) and end (snapshot)
date; an undated valuation is never paired with a dated benchmark.

``avg_cost`` is never used as a mark, a current price is never inferred from a
historical NAV row, and row order in ``realized_rows`` never decides which row
is latest: rows are validated, sorted chronologically, exact duplicates are
collapsed, and conflicting duplicates on one date exclude that date.

Availability issue vocabulary (safe, fixed, deterministic codes)
---------------------------------------------------------------
invalid_today, missing_baseline, invalid_inception, future_inception,
account_unavailable, account_invalid, transaction_pending, missing_cash,
unpriced_holdings, nonfinite_valuation, stale_valuation,
unsupplied_quote_clock, history_unavailable, history_partial, history_before_inception,
benchmark_unavailable, benchmark_partial, return_comparison_unavailable
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from collections import namedtuple
from collections.abc import Mapping

__all__ = ["project_performance", "ISSUE_CODES", "CHART_CAP"]

_DATE_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")

CHART_CAP = 91

ISSUE_INVALID_TODAY = "invalid_today"
ISSUE_MISSING_BASELINE = "missing_baseline"
ISSUE_INVALID_INCEPTION = "invalid_inception"
ISSUE_FUTURE_INCEPTION = "future_inception"
ISSUE_ACCOUNT_UNAVAILABLE = "account_unavailable"
ISSUE_ACCOUNT_INVALID = "account_invalid"
ISSUE_TRANSACTION_PENDING = "transaction_pending"
ISSUE_MISSING_CASH = "missing_cash"
ISSUE_UNPRICED_HOLDINGS = "unpriced_holdings"
ISSUE_NONFINITE_VALUATION = "nonfinite_valuation"
ISSUE_STALE_VALUATION = "stale_valuation"
ISSUE_UNSUPPLIED_QUOTE_CLOCK = "unsupplied_quote_clock"
ISSUE_HISTORY_UNAVAILABLE = "history_unavailable"
ISSUE_HISTORY_PARTIAL = "history_partial"
ISSUE_HISTORY_BEFORE_INCEPTION = "history_before_inception"
ISSUE_BENCHMARK_UNAVAILABLE = "benchmark_unavailable"
ISSUE_BENCHMARK_PARTIAL = "benchmark_partial"
ISSUE_RETURN_COMPARISON_UNAVAILABLE = "return_comparison_unavailable"

ISSUE_CODES = (
    ISSUE_INVALID_TODAY,
    ISSUE_MISSING_BASELINE,
    ISSUE_INVALID_INCEPTION,
    ISSUE_FUTURE_INCEPTION,
    ISSUE_ACCOUNT_UNAVAILABLE,
    ISSUE_ACCOUNT_INVALID,
    ISSUE_TRANSACTION_PENDING,
    ISSUE_MISSING_CASH,
    ISSUE_UNPRICED_HOLDINGS,
    ISSUE_NONFINITE_VALUATION,
    ISSUE_STALE_VALUATION,
    ISSUE_UNSUPPLIED_QUOTE_CLOCK,
    ISSUE_HISTORY_UNAVAILABLE,
    ISSUE_HISTORY_PARTIAL,
    ISSUE_HISTORY_BEFORE_INCEPTION,
    ISSUE_BENCHMARK_UNAVAILABLE,
    ISSUE_BENCHMARK_PARTIAL,
    ISSUE_RETURN_COMPARISON_UNAVAILABLE,
)

BASIS_PROVIDED_PRICES = "provided_prices"
BASIS_CASH_ONLY = "cash_only"
BASIS_LAST_RECORDED_NAV = "last_recorded_nav"
BASIS_UNAVAILABLE = "unavailable"

_Row = namedtuple("_Row", "date nav cash invested")


def _is_number(value):
    """Finite int/float only: bool and numeric strings are not observations."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _parse_iso_date(value):
    """Strict ``YYYY-MM-DD`` calendar date, or ``None`` when unqualified."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        return _dt.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def _norm_word(value):
    """Lower-cased non-empty status word, or ``None`` when unqualifiable."""
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped:
            return stripped
    return None


def _iso(day):
    return day.isoformat()


def _echo_benchmark(benchmark):
    """Echo the requested benchmark symbol verbatim when it is a usable name."""
    if isinstance(benchmark, str) and benchmark.strip():
        return benchmark
    return None


def _qualified_rows(realized_rows, today):
    """Validate NAV rows, sort chronologically, collapse/flag duplicates.

    Returns ``(rows, excluded_any, complete)``.  Row order in the input never
    decides which observation is latest: rows are sorted by date.  Exact
    duplicates collapse silently; conflicting duplicates exclude the date and
    mark the history partial.  Future or malformed rows are excluded.
    """
    if not isinstance(realized_rows, (list, tuple)):
        return [], True, False
    by_date = {}
    conflicts = set()
    excluded = False
    for row in realized_rows:
        if not isinstance(row, Mapping):
            excluded = True
            continue
        day = _parse_iso_date(row.get("date"))
        if day is None or day > today:
            excluded = True
            continue
        raw_nav = row.get("nav")
        if not _is_number(raw_nav) or raw_nav < 0:
            excluded = True
            continue
        raw_cash = row.get("cash")
        if raw_cash is None:
            cash = None
        elif _is_number(raw_cash):
            cash = float(raw_cash)
        else:
            excluded = True
            continue
        raw_invested = row.get("invested")
        if raw_invested is None:
            invested = None
        elif _is_number(raw_invested):
            invested = float(raw_invested)
        else:
            excluded = True
            continue
        if cash is not None and invested is not None:
            components = cash + invested
            if not math.isfinite(components) or not math.isclose(
                float(raw_nav), components, rel_tol=1e-12, abs_tol=0.02
            ):
                excluded = True
                continue
        entry = _Row(day, float(raw_nav), cash, invested)
        previous = by_date.get(day)
        if previous is None:
            by_date[day] = entry
        elif previous != entry:
            conflicts.add(day)
            excluded = True
    for day in conflicts:
        by_date.pop(day, None)
    rows = [by_date[day] for day in sorted(by_date)]
    return rows, excluded, not excluded


def _qualified_benchmark(benchmark_history, today):
    """Validate ``(date, positive close)`` observations up to ``today``.

    Returns ``(closes, excluded_any, readable)`` where ``closes`` maps date to
    close.  Malformed, non-positive and future values are filtered without
    inventing winners for conflicting same-date observations.
    """
    if not isinstance(benchmark_history, (list, tuple)):
        return {}, True, False
    by_date = {}
    conflicts = set()
    excluded = False
    for entry in benchmark_history:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            excluded = True
            continue
        day = _parse_iso_date(entry[0])
        raw_close = entry[1]
        if day is None or day > today or not _is_number(raw_close) or raw_close <= 0:
            excluded = True
            continue
        close = float(raw_close)
        previous = by_date.get(day)
        if previous is None:
            by_date[day] = close
        elif previous != close:
            conflicts.add(day)
            excluded = True
    for day in conflicts:
        by_date.pop(day, None)
    return by_date, excluded, True


def _build_series(rows, closes, starting_nav, inception, inception_qualified):
    """Chart points over the sorted union of NAV dates and last chart dates.

    Benchmark closes normalise to ``starting_nav`` at the first benchmark date
    that survives the chart cap; without a baseline ``spy_nav`` stays null.
    Pre-inception dates may carry ``starting_nav`` only as an explicit
    ``pre_inception`` reference.  On or after inception an absent date is
    ``nav=None`` with ``kind="unavailable"`` - no flat rows are fabricated.
    """
    nav_by_date = {row.date: row.nav for row in rows}
    benchmark_items = sorted(closes.items())[-CHART_CAP:]
    union = sorted(set(nav_by_date) | {day for day, _ in benchmark_items})[-CHART_CAP:]
    chart_dates = set(union)
    benchmark_in_chart = {
        day: close for day, close in benchmark_items if day in chart_dates
    }
    base_close = None
    if benchmark_in_chart and starting_nav is not None and starting_nav > 0:
        base_close = benchmark_in_chart[min(benchmark_in_chart)]
    points = []
    for day in union:
        if day in nav_by_date:
            nav = nav_by_date[day]
            kind = "realized"
        elif (
            inception_qualified
            and inception is not None
            and starting_nav is not None
            and day < inception
        ):
            nav = starting_nav
            kind = "pre_inception"
        else:
            nav = None
            kind = "unavailable"
        spy_nav = None
        if base_close is not None and day in benchmark_in_chart:
            normalised = benchmark_in_chart[day] / base_close * starting_nav
            if math.isfinite(normalised):
                spy_nav = normalised
        points.append(
            {"date": _iso(day), "nav": nav, "spy_nav": spy_nav, "kind": kind}
        )
    return points


def _empty_result(benchmark, account_echo, history_echo, issues):
    """Fail-safe shape used when the observed clock itself is unusable."""
    return {
        "inception_date": None,
        "starting_nav": None,
        "current_nav": None,
        "cash": None,
        "invested": None,
        "total_return_pct": None,
        "vs_benchmark_pct": None,
        "vs_spy_pct": None,
        "benchmark": _echo_benchmark(benchmark),
        "benchmark_as_of": None,
        "day_change_pct": None,
        "max_drawdown_pct": None,
        "day_change_window": None,
        "drawdown_window": None,
        "realized_since": None,
        "series": [],
        "availability": {
            "status": "unavailable",
            "account_status": account_echo,
            "history_status": history_echo,
            "valuation_basis": BASIS_UNAVAILABLE,
            "as_of": None,
            "issues": list(issues),
        },
    }


def project_performance(
    state,
    realized_rows,
    benchmark_history,
    *,
    benchmark,
    today,
    prices=None,
    account_status="available",
    history_status="available",
    transaction_pending=False,
):
    """Project account performance from reduced, already-loaded contracts.

    ``state`` is the account snapshot (``inception_date``, ``starting_nav``,
    ``cash``, ``positions`` of ``{ticker: {"shares": ..., "avg_cost": ...}}``),
    ``realized_rows`` the dated NAV history, and ``benchmark_history`` pairs of
    ``(ISO date, positive close)``.  ``today`` is an explicit ISO date; the
    module never reads a wall clock.  ``prices`` are optional caller supplied
    marks in book base currency with no independent quote clock.
    """
    issues = []

    def flag(code):
        if code not in issues:
            issues.append(code)

    account_word = _norm_word(account_status)
    account_echo = account_word if account_word in (
        "available", "missing", "invalid", "unavailable"
    ) else "unavailable"
    history_word = _norm_word(history_status)
    history_echo = history_word if history_word in ("available", "partial") else "unavailable"

    today_d = _parse_iso_date(today)
    if today_d is None:
        # A malformed observed clock must fail safely, never guess "now".
        return _empty_result(
            benchmark, account_echo, history_echo, [ISSUE_INVALID_TODAY]
        )

    # ---------------------------------------------------------------- baseline
    inception_d = None
    inception_qualified = False
    starting_nav = None
    state_map = state if isinstance(state, Mapping) else None
    if state_map is None:
        flag(ISSUE_MISSING_BASELINE)
        flag(ISSUE_INVALID_INCEPTION)
    else:
        raw_nav = state_map.get("starting_nav")
        if _is_number(raw_nav) and raw_nav > 0:
            starting_nav = float(raw_nav)
        else:
            flag(ISSUE_MISSING_BASELINE)
        inception_d = _parse_iso_date(state_map.get("inception_date"))
        if inception_d is None:
            flag(ISSUE_INVALID_INCEPTION)
        elif inception_d > today_d:
            flag(ISSUE_FUTURE_INCEPTION)
        else:
            inception_qualified = True
    baseline_ok = inception_qualified and starting_nav is not None

    # ----------------------------------------------------------- account state
    cash = None
    shares = {}
    account_valid = False
    if account_echo != "available":
        flag(ISSUE_ACCOUNT_UNAVAILABLE)
    elif state_map is None:
        account_echo = "invalid"
        flag(ISSUE_ACCOUNT_INVALID)
    else:
        account_valid = True
        raw_cash = state_map.get("cash")
        if raw_cash is None:
            account_valid = False
            flag(ISSUE_MISSING_CASH)
        elif _is_number(raw_cash):
            cash = float(raw_cash)
        else:
            account_valid = False
        if account_valid:
            raw_positions = state_map.get("positions")
            if raw_positions is None:
                account_valid = False
            elif isinstance(raw_positions, Mapping):
                for ticker, lot in raw_positions.items():
                    raw_shares = lot.get("shares") if isinstance(lot, Mapping) else None
                    if (
                        not isinstance(ticker, str)
                        or not ticker.strip()
                        or not isinstance(lot, Mapping)
                        or not _is_number(raw_shares)
                        or raw_shares < 0
                    ):
                        account_valid = False
                        break
                    shares[ticker] = float(raw_shares)
            else:
                account_valid = False
        if not account_valid:
            account_echo = "invalid"
            flag(ISSUE_ACCOUNT_INVALID)

    # ----------------------------------------------------------------- history
    pending = bool(transaction_pending)
    if pending:
        flag(ISSUE_TRANSACTION_PENDING)

    rows = []
    history_complete = False
    if history_echo == "unavailable":
        flag(ISSUE_HISTORY_UNAVAILABLE)
    else:
        rows, excluded, history_complete = _qualified_rows(realized_rows, today_d)
        if excluded or history_echo == "partial":
            history_complete = False
            history_echo = "partial"
            flag(ISSUE_HISTORY_PARTIAL)

    # An older account episode cannot supply this account\'s NAV or return window.
    # No episode identity is invented: same-book dates are only a minimum eligibility check.
    if inception_qualified:
        episode_rows = [row for row in rows if row.date >= inception_d]
        if len(episode_rows) != len(rows):
            flag(ISSUE_HISTORY_BEFORE_INCEPTION)
        rows = episode_rows

    # --------------------------------------------------------------- benchmark
    closes, bench_excluded, bench_readable = _qualified_benchmark(
        benchmark_history, today_d
    )
    if not bench_readable or not closes:
        flag(ISSUE_BENCHMARK_UNAVAILABLE)
    if bench_excluded:
        flag(ISSUE_BENCHMARK_PARTIAL)
    benchmark_as_of_d = max(closes) if closes else None

    # ---------------------------------------------------------------- valuation
    basis = BASIS_UNAVAILABLE
    current_nav = None
    out_cash = None
    invested = None
    as_of_d = None

    if pending or not account_valid:
        pass
    else:
        nonzero = {ticker: lot for ticker, lot in shares.items() if lot > 0.0}
        marks = {}
        marks_complete = bool(nonzero)
        if nonzero:
            price_map = prices if isinstance(prices, Mapping) else {}
            for ticker in nonzero:
                raw_price = price_map.get(ticker)
                if _is_number(raw_price) and raw_price > 0:
                    marks[ticker] = float(raw_price)
                else:
                    marks_complete = False
                    break
        # Report the observation gap itself, whether or not a historical
        # snapshot below can still rescue an aggregate valuation.
        if nonzero and not marks_complete:
            flag(ISSUE_UNPRICED_HOLDINGS)
        if cash is None:
            flag(ISSUE_MISSING_CASH)

        if nonzero and marks_complete and cash is not None:
            market_value = 0.0
            for ticker, lot in nonzero.items():
                market_value += lot * marks[ticker]
            if not (
                math.isfinite(market_value)
                and math.isfinite(cash)
                and math.isfinite(cash + market_value)
            ):
                flag(ISSUE_NONFINITE_VALUATION)
            else:
                basis = BASIS_PROVIDED_PRICES
                current_nav = cash + market_value
                invested = market_value
                out_cash = cash
                # Quote clocks are not supplied, so a marked valuation is
                # provisional even though it is complete.
                flag(ISSUE_UNSUPPLIED_QUOTE_CLOCK)
        elif not nonzero and cash is not None:
            basis = BASIS_CASH_ONLY
            current_nav = cash
            invested = 0.0
            out_cash = cash

        if basis == BASIS_UNAVAILABLE and rows:
            # Last recorded snapshot only: the row's own cash and date travel
            # with it, never today's cash against a historical NAV.
            latest = rows[-1]
            basis = BASIS_LAST_RECORDED_NAV
            current_nav = latest.nav
            as_of_d = latest.date
            out_cash = latest.cash
            if latest.invested is not None:
                invested = latest.invested
            elif latest.cash is not None:
                derived = latest.nav - latest.cash
                if math.isfinite(derived):
                    invested = derived
            flag(ISSUE_STALE_VALUATION)

        if basis == BASIS_UNAVAILABLE:
            # Known current cash can remain visible without an aggregate NAV.
            out_cash = cash

    if pending or account_echo != "available" or basis == BASIS_UNAVAILABLE:
        status = "unavailable"
    elif basis in (BASIS_PROVIDED_PRICES, BASIS_LAST_RECORDED_NAV):
        status = "provisional"
    else:
        status = "available"

    # ----------------------------------------------------------------- returns
    total_return_pct = None
    if baseline_ok and current_nav is not None and not pending:
        candidate = (current_nav - starting_nav) / starting_nav * 100.0
        if math.isfinite(candidate):
            total_return_pct = candidate

    vs_benchmark_pct = None
    if pending or current_nav is None or total_return_pct is None:
        pass
    elif not baseline_ok:
        pass  # baseline issues already qualify the comparison
    elif basis != BASIS_LAST_RECORDED_NAV or as_of_d is None:
        # An undated valuation has no quote clock to pair with the benchmark.
        flag(ISSUE_RETURN_COMPARISON_UNAVAILABLE)
    else:
        start_close = closes.get(inception_d)
        end_close = closes.get(as_of_d)
        if start_close is None or end_close is None or not as_of_d > inception_d:
            flag(ISSUE_RETURN_COMPARISON_UNAVAILABLE)
        else:
            benchmark_return = (end_close / start_close - 1.0) * 100.0
            candidate = total_return_pct - benchmark_return
            if math.isfinite(candidate):
                vs_benchmark_pct = candidate

    # -------------------------------------------------------------- statistics
    day_change_pct = None
    if (
        not pending
        and account_valid
        and history_complete
        and len(rows) >= 2
        and basis == BASIS_LAST_RECORDED_NAV
    ):
        prior, latest = rows[-2], rows[-1]
        if prior.nav > 0:
            candidate = (latest.nav - prior.nav) / prior.nav * 100.0
            if math.isfinite(candidate):
                day_change_pct = candidate

    max_drawdown_pct = None
    if history_complete and len(rows) >= 2:
        peak = None
        worst = 0.0
        for row in rows:
            if peak is None or row.nav > peak:
                peak = row.nav
            if peak > 0:
                drawdown = (row.nav - peak) / peak * 100.0
                if drawdown < worst:
                    worst = drawdown
        if peak is not None and peak > 0 and math.isfinite(worst):
            max_drawdown_pct = worst

    day_change_window = (
        {"from": _iso(rows[-2].date), "to": _iso(rows[-1].date)}
        if day_change_pct is not None else None
    )
    drawdown_window = (
        {"from": _iso(rows[0].date), "to": _iso(rows[-1].date)}
        if max_drawdown_pct is not None else None
    )
    series = _build_series(
        rows, closes, starting_nav, inception_d, inception_qualified
    )

    return {
        "inception_date": _iso(inception_d) if inception_d is not None else None,
        "starting_nav": starting_nav,
        "current_nav": current_nav,
        "cash": out_cash,
        "invested": invested,
        "total_return_pct": total_return_pct,
        "vs_benchmark_pct": vs_benchmark_pct,
        "vs_spy_pct": vs_benchmark_pct,
        "benchmark": _echo_benchmark(benchmark),
        "benchmark_as_of": _iso(benchmark_as_of_d)
        if benchmark_as_of_d is not None
        else None,
        "day_change_pct": day_change_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "day_change_window": day_change_window,
        "drawdown_window": drawdown_window,
        "realized_since": _iso(rows[0].date) if rows else None,
        "series": series,
        "availability": {
            "status": status,
            "account_status": account_echo,
            "history_status": history_echo,
            "valuation_basis": basis,
            "as_of": _iso(as_of_d) if as_of_d is not None else None,
            "issues": list(issues),
        },
    }
