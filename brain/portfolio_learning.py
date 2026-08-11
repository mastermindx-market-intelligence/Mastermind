"""Mastermind Portfolio learning substrate for the three active regional Brains.

This module is deliberately separate from :mod:`brain.mastermind_ai`, which is the
legacy Neural-Web/orchestrator coordinator and was historically confused with the
public Mastermind AI chat product.  The scope here is narrow and auditable:

* maintain a forward ledger after every sell (5/10/21/63 trading bars),
* derive compact, evidence-labelled behavioural lessons for each paper book,
* share only execution lessons that have repeated in at least two markets, and
* queue bounded requests for missing context instead of granting a portfolio LLM
  arbitrary filesystem or infrastructure authority.

The module never trades, sizes, changes prompts on disk, or edits code.  Its only
effect on a Brain is the compact ``prompt_block`` returned to the next run.  All
runtime artifacts live under ``data/portfolio_learning/`` and are intentionally
excluded from releases.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
_DIR = _ROOT / "data" / "portfolio_learning"
ACTIVE_BRAINS = ("autonomous", "china", "hk")
HORIZONS = (5, 10, 21, 63)
BOOK_SCOPES = {
    "autonomous": "US_ONLY",
    "china": "CN_ONLY",
    "hk": "HK_ONLY",
}
LESSON_SCOPES = frozenset({
    "US_ONLY",
    "CN_ONLY",
    "HK_ONLY",
    "CROSS_MARKET_CANDIDATE",
})
LESSON_AUTHORITY = "research_request_only"
APPLICATION_AUTHORITY = "observational_only"
LESSON_TRACE_COHORT = "portfolio_v2_lesson_trace"
_ACTIVE_PRESENTATIONS: dict[tuple[str, str], str] = {}
_LESSON_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_LESSON_ID_RE = re.compile(
    r"^lesson\.v1\.(US_ONLY|CN_ONLY|HK_ONLY|CROSS_MARKET_CANDIDATE)\."
    r"[a-z][a-z0-9_]{1,63}$"
)
_DECISION_ID_RE = re.compile(r"^decision\.v1\.[0-9a-f]{24}$")
_APPLICATION_ID_RE = re.compile(r"^application\.v1\.[0-9a-f]{24}$")
_PRESENTATION_ID_RE = re.compile(r"^presentation\.v1\.[0-9a-f]{24}$")
_TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{64}$")

# Context requests are intentionally typed and bounded.  A Brain may identify a
# missing plane; a separate orchestrator/operator still decides whether to build it.
_PLANE_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_MAX_REASON = 280
_CONTEXT_STATUSES = {
    "queued_for_orchestrator_review",
    "directive_queued",
    "published_to_orchestrator",
    "acknowledged_by_orchestrator",
    "expired_unacknowledged",
    "resolved_available",
    "rejected",
}
_CONTEXT_STATUS_RANK = {
    "queued_for_orchestrator_review": 0,
    "directive_queued": 1,
    "published_to_orchestrator": 2,
    "acknowledged_by_orchestrator": 3,
    "expired_unacknowledged": 3,
    "resolved_available": 4,
    "rejected": 4,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _book_dir(book: str) -> Path:
    return _DIR / _clean_book(book)


def _clean_book(book: str) -> str:
    b = str(book or "").strip().lower()
    if b not in ACTIVE_BRAINS:
        raise ValueError(f"unsupported portfolio-learning book: {b!r}")
    return b


def _scope_for_book(book: str) -> str:
    return BOOK_SCOPES[_clean_book(book)]


def _stable_lesson_id(scope: str, code: str) -> str:
    """Return the transparent, stable identity for one measured mechanism."""
    clean_scope = str(scope or "").strip().upper()
    clean_code = str(code or "").strip().lower()
    if clean_scope not in LESSON_SCOPES or not _LESSON_CODE_RE.fullmatch(clean_code):
        raise ValueError("invalid lesson scope/code")
    return f"lesson.v1.{clean_scope}.{clean_code}"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _target_sha256(target: dict[str, float]) -> str:
    clean = {
        str(ticker).upper().strip(): float(weight)
        for ticker, weight in (target or {}).items()
    }
    return _sha256(clean)


@contextmanager
def _trace_lock(book: str):
    """Serialize presentation/application dedupe for one regional runtime ledger."""
    path = _book_dir(book) / ".lesson_trace.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            return value
    except Exception:
        pass
    return default


def _write_json(path: Path, value: Any) -> None:
    """Crash-resistant local runtime write.  Never leaves a partially-written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except Exception:
                continue
    except Exception:
        pass
    return rows


def _append_jsonl(path: Path, row: dict) -> bool:
    """Append one complete transition and report whether it reached the local ledger."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except Exception:
        return False


def _series(ticker: str):
    """Use Mastermind's canonical point-in-time price reader; never fetch the web here."""
    try:
        from portfolio.paper_account import _fetch_price_series
        s = _fetch_price_series((ticker or "").upper().strip())
        if s is None or len(s) == 0:
            return None
        return s.sort_index()
    except Exception:
        return None


def _dated_prices(series) -> dict[str, float]:
    """Exact session-date prices; the last valid duplicate observation wins deterministically."""
    out: dict[str, float] = {}
    if series is None:
        return out
    try:
        for stamp, value in zip(series.index, series, strict=False):
            day = str(stamp.date()) if hasattr(stamp, "date") else str(stamp)[:10]
            price = float(value)
            if day and math.isfinite(price) and price > 0:
                out[day] = price
    except Exception:
        return {}
    return out


def _same_session_grade(
    stock_series,
    benchmark_series,
    exit_date: str,
    horizon: int,
    *,
    fill_price: float | None,
    available_through: str | date | None = None,
) -> dict:
    """Grade one sale on a benchmark-defined market-session window.

    The immutable fill remains the absolute opportunity-cost basis.  Relative performance uses
    exact close-to-close prices for both instruments on the *same* exit and target sessions.  A
    missing/suspended stock bar therefore stays ungraded instead of silently shifting the stock to
    a later date while leaving the benchmark on the original horizon.
    """
    cutoff = str(available_through or date.today())[:10]
    exit_day = str(exit_date or "")[:10]
    stock = _dated_prices(stock_series)
    benchmark = _dated_prices(benchmark_series)
    benchmark_days = sorted(benchmark)
    base = {
        "return": None,
        "stock_session_return": None,
        "benchmark_return": None,
        "relative_return": None,
        "bar_date": None,
        "benchmark_bar_date": None,
        "canonical_target_date": None,
        "status": "pending",
        "stock_return_basis": "immutable_paper_fill_to_canonical_session_close",
        "relative_return_basis": "same_session_close_to_close",
        "available_through": cutoff,
    }
    if exit_day not in benchmark:
        return {**base, "pending_reason": "missing_benchmark_exit_session"}
    try:
        target_pos = benchmark_days.index(exit_day) + int(horizon)
    except (TypeError, ValueError):
        return {**base, "pending_reason": "invalid_horizon"}
    if target_pos >= len(benchmark_days):
        return {**base, "pending_reason": "benchmark_target_not_available"}
    target_day = benchmark_days[target_pos]
    base["canonical_target_date"] = target_day
    base["benchmark_bar_date"] = target_day
    if target_day > cutoff:
        return {**base, "pending_reason": "target_after_available_through"}

    stock_target = stock.get(target_day)
    if stock_target is None:
        return {**base, "pending_reason": "missing_stock_target_session"}
    base["bar_date"] = target_day
    if isinstance(fill_price, (int, float)) and not isinstance(fill_price, bool) and fill_price > 0:
        base["return"] = round(stock_target / float(fill_price) - 1.0, 6)

    stock_start = stock.get(exit_day)
    if stock_start is None:
        return {**base, "pending_reason": "missing_stock_exit_session"}
    benchmark_start = benchmark[exit_day]
    benchmark_target = benchmark[target_day]
    stock_return = round(stock_target / stock_start - 1.0, 6)
    benchmark_return = round(benchmark_target / benchmark_start - 1.0, 6)
    return {
        **base,
        "stock_session_return": stock_return,
        "benchmark_return": benchmark_return,
        "relative_return": round(stock_return - benchmark_return, 6),
        "status": "graded",
    }


def _accepted_decision_row(row: dict) -> bool:
    if row.get("decision_effective") is False:
        return False
    status_value = row.get("target_status")
    return status_value is None or status_value in {"queued", "executed"}


def _decision_record(row: dict, ticker: str) -> dict:
    records = list(row.get("exit_decisions") or []) + list(row.get("holdings") or [])
    for record in records:
        if (
            isinstance(record, dict)
            and str(record.get("ticker") or "").upper() == ticker.upper()
        ):
            return dict(record)
    return {}


def _legacy_lesson_links(row: dict) -> dict:
    """Admit trace links on a legacy fill only when the row is explicitly in the v2 cohort."""
    application_ids = row.get("lesson_application_ids")
    lesson_ids = row.get("lesson_ids_cited")
    if (
        row.get("lesson_trace_cohort") != LESSON_TRACE_COHORT
        or not _DECISION_ID_RE.fullmatch(str(row.get("decision_id") or ""))
        or not _PRESENTATION_ID_RE.fullmatch(str(row.get("lesson_presentation_id") or ""))
        or not isinstance(application_ids, list)
        or not application_ids
        or not all(_APPLICATION_ID_RE.fullmatch(str(value or "")) for value in application_ids)
        or not isinstance(lesson_ids, list)
        or not lesson_ids
        or not all(_LESSON_ID_RE.fullmatch(str(value or "")) for value in lesson_ids)
    ):
        return {}
    return {
        "decision_id": row["decision_id"],
        "lesson_application_ids": list(application_ids),
        "lesson_ids_cited": list(lesson_ids),
        "lesson_presentation_id": row["lesson_presentation_id"],
        "lesson_trace_cohort": LESSON_TRACE_COHORT,
        "lesson_trace_status": str(row.get("lesson_trace_status") or "accepted_legacy_fill"),
    }


def _decision_exit(
    book: str,
    ticker: str,
    fill_date: str,
    *,
    transaction_id: str | None = None,
    fill_id: str | None = None,
    fill: dict | None = None,
) -> dict:
    """Bind a sell to its exact application transaction; use dates only for legacy fills."""
    try:
        from portfolio import registry
        path = registry.data_dir(book) / "decisions.jsonl"
        rows = _read_jsonl(path)
        transaction = str(transaction_id or "")
        bound_fill_id = str(fill_id or "")
        if transaction:
            lineage = {
                "method": "settlement_transaction",
                "settlement_transaction_id": transaction,
                "fill_id": bound_fill_id or None,
                "status": "unbound_no_lesson_application",
            }
            if not _TRANSACTION_ID_RE.fullmatch(transaction):
                return {"_decision_lineage": {**lineage, "status": "malformed_transaction_id"}}
            if not _TRANSACTION_ID_RE.fullmatch(bound_fill_id):
                return {"_decision_lineage": {**lineage, "status": "missing_or_malformed_fill_id"}}
            transaction_applications = [
                row for row in applications(book)
                if row.get("executed") is True
                and row.get("settlement_verified") is True
                and row.get("settlement_transaction_id") == transaction
            ]
            matched = [
                row for row in transaction_applications
                if any(
                    proof.get("transaction_id") == transaction
                    and proof.get("fill_id") == bound_fill_id
                    for proof in (row.get("settled_fills") or [])
                    if isinstance(proof, dict)
                )
            ]
            if len(matched) != 1:
                if len(matched) > 1:
                    lineage["status"] = "ambiguous_lesson_applications"
                elif transaction_applications:
                    lineage["status"] = "unbound_fill_not_in_settlement_proof"
                return {"_decision_lineage": lineage}
            application = matched[0]
            settled_fill = next(
                proof for proof in application["settled_fills"]
                if proof.get("transaction_id") == transaction
                and proof.get("fill_id") == bound_fill_id
            )
            observed_fill = fill or {}
            if any(
                observed_fill.get(key) != settled_fill.get(key)
                for key in ("date", "ticker", "side", "shares", "price", "value")
            ):
                return {"_decision_lineage": {**lineage, "status": "fill_proof_mismatch"}}
            decision_id = str(application["decision_id"])
            memo: dict = {}
            for row in rows:
                if row.get("decision_id") == decision_id and _accepted_decision_row(row):
                    candidate = _decision_record(row, ticker)
                    if candidate:
                        memo = candidate
                        break
            memo["_lesson_trace_links"] = {
                "decision_id": decision_id,
                "lesson_application_ids": [application["application_id"]],
                "lesson_ids_cited": list(application.get("lesson_ids") or []),
                "lesson_presentation_id": application["presentation_id"],
                "lesson_trace_cohort": LESSON_TRACE_COHORT,
                "lesson_trace_status": "accepted_executed",
                "settlement_transaction_id": transaction,
                "fill_id": bound_fill_id,
            }
            memo["_decision_lineage"] = {
                **lineage,
                "status": "bound_lesson_application",
                "decision_id": decision_id,
                "lesson_application_id": application["application_id"],
            }
            return memo

        # A fill without transaction/fill identity predates the WAL settlement contract.  Retain the
        # historical nearest-prior-decision heuristic, and label it so it cannot be mistaken for an
        # exact post-v2 binding.
        candidates = []
        for row in rows:
            if str(row.get("asof") or "")[:10] > str(fill_date)[:10]:
                continue
            if not _accepted_decision_row(row):
                continue
            memo = _decision_record(row, ticker)
            if memo:
                links = _legacy_lesson_links(row)
                if links:
                    memo["_lesson_trace_links"] = links
                memo["_decision_lineage"] = {
                    "method": "legacy_date_heuristic",
                    "status": "legacy_unverified",
                    "decision_asof": str(row.get("asof") or "")[:10],
                }
                candidates.append((str(row.get("asof") or ""), memo))
        return sorted(candidates, key=lambda x: x[0])[-1][1] if candidates else {}
    except Exception:
        return {}


def refresh_post_sell(book: str, asof: str | date | None = None) -> dict:
    """Reconcile every sell fill into the book's forward opportunity-cost ledger.

    The exit price comes from the immutable paper fill.  Forward returns use exact
    trading-bar offsets in the same price store used by Mastermind's other outcome
    graders.  Missing future bars remain pending; they are never back-filled with the
    latest price.
    """
    b = _clean_book(book)
    from portfolio import registry, trade_history

    benchmark = registry.benchmark(b)
    path = _book_dir(b) / "post_sell.json"
    available_through = str(asof or datetime.now(UTC).date())[:10]
    prior = _read_json(path, {})
    by_id = {
        str(r.get("exit_id")): r
        for r in (prior.get("exits") or [])
        if r.get("exit_id") and str(r.get("exit_date") or "")[:10] <= available_through
    }
    fills = trade_history._load_fills(b)  # canonical fill source; adds stable _seq
    open_shares: dict[str, float] = {}
    for fill in fills:
        side = str(fill.get("side") or "").lower()
        ticker = str(fill.get("ticker") or "").upper().strip()
        shares = max(0.0, float(fill.get("shares") or 0.0))
        if side == "buy":
            if ticker:
                open_shares[ticker] = open_shares.get(ticker, 0.0) + shares
            continue
        if side != "sell":
            continue
        fill_date = str(fill.get("date") or "")[:10]
        if not ticker or not fill_date:
            continue
        if fill_date > available_through:
            continue
        held_before = max(0.0, open_shares.get(ticker, 0.0))
        held_after = max(0.0, held_before - shares)
        open_shares[ticker] = held_after
        sale_kind = (
            "unknown_sale" if held_before <= 0
            else "full_exit" if held_after <= 1e-9
            else "partial_trim"
        )
        transaction_id = str(fill.get("transaction_id") or "")
        fill_id = str(fill.get("fill_id") or "")
        legacy_exit_id = f"{b}:{fill_date}:{ticker}:{int(fill.get('_seq') or 0)}"
        exit_id = f"{b}:fill:{fill_id}" if fill_id else legacy_exit_id
        row = dict(by_id.get(exit_id) or by_id.get(legacy_exit_id) or {})
        if exit_id != legacy_exit_id:
            by_id.pop(legacy_exit_id, None)
        row.update({
            "exit_id": exit_id,
            "book": b,
            "ticker": ticker,
            "exit_date": fill_date,
            "exit_price": fill.get("price"),
            "shares": fill.get("shares"),
            "value": fill.get("value"),
            "benchmark": benchmark,
            "sale_kind": sale_kind,
            "held_shares_before": round(held_before, 8),
            "held_shares_after": round(held_after, 8),
            "fraction_of_position_sold": (
                round(min(1.0, shares / held_before), 6) if held_before > 0 else None
            ),
        })
        for stale_key in ("decision", "decision_lineage", "lesson_trace"):
            row.pop(stale_key, None)
        if fill_id:
            row["fill_id"] = fill_id
        else:
            row.pop("fill_id", None)
        if transaction_id:
            row["settlement_transaction_id"] = transaction_id
        else:
            row.pop("settlement_transaction_id", None)
        memo = (
            _decision_exit(
                b,
                ticker,
                fill_date,
                transaction_id=transaction_id,
                fill_id=fill_id,
                fill=fill,
            )
            if transaction_id
            else _decision_exit(b, ticker, fill_date)
        )
        if memo:
            decision = {
                k: memo.get(k) for k in
                (
                    "action", "action_requested", "action_effective", "reason", "rationale",
                    "evidence", "falsifier", "why_now", "prior_target_weight", "weight",
                )
                if memo.get(k) is not None
            }
            if decision:
                row["decision"] = decision
            if memo.get("_decision_lineage"):
                row["decision_lineage"] = memo["_decision_lineage"]
            if memo.get("_lesson_trace_links"):
                row["lesson_trace"] = memo["_lesson_trace_links"]

        stock_s = _series(ticker)
        bench_s = _series(benchmark)
        grades: dict[str, dict] = {}
        try:
            fill_price = float(fill.get("price"))
        except (TypeError, ValueError):
            fill_price = None
        for horizon in HORIZONS:
            grades[str(horizon)] = _same_session_grade(
                stock_s,
                bench_s,
                fill_date,
                horizon,
                fill_price=fill_price,
                available_through=available_through,
            )
        row["forward"] = grades
        row["status"] = ("complete" if all(g["status"] == "graded" for g in grades.values())
                         else "partial" if any(g["status"] == "graded" for g in grades.values())
                         else "pending")
        row["updated_at"] = _now()
        by_id[exit_id] = row

    rows = sorted(by_id.values(), key=lambda r: (r.get("exit_date") or "", r.get("exit_id") or ""))
    result = {
        "schema": "portfolio.post_sell.v1",
        "book": b,
        "generated_at": _now(),
        "asof": available_through,
        "horizons_sessions": list(HORIZONS),
        "exits": rows,
    }
    result["summary"] = _post_sell_summary(rows)
    _write_json(path, result)
    return result


def _post_sell_summary(rows: list[dict]) -> dict:
    full = [row for row in rows if row.get("sale_kind", "full_exit") == "full_exit"]
    trims = [row for row in rows if row.get("sale_kind") == "partial_trim"]
    summary: dict[str, Any] = {
        "n_sales": len(rows),
        "n_exits": len(full),
        "n_partial_trims": len(trims),
        "by_horizon": {},
    }

    def aggregate(source: list[dict], horizon: int) -> dict:
        rel = [r.get("forward", {}).get(str(horizon), {}).get("relative_return") for r in source]
        rel = [float(x) for x in rel if isinstance(x, (int, float)) and not isinstance(x, bool)]
        return {
            "n": len(rel),
            "mean_relative_return": round(sum(rel) / len(rel), 6) if rel else None,
            "sold_before_outperformance_rate": (
                round(sum(x > 0 for x in rel) / len(rel), 4) if rel else None
            ),
        }

    for horizon in HORIZONS:
        summary["by_horizon"][str(horizon)] = {
            **aggregate(rows, horizon),
            "full_exits": aggregate(full, horizon),
            "partial_trims": aggregate(trims, horizon),
        }
    return summary


def _behaviour(book: str) -> dict:
    from portfolio import position_log, registry, trade_history

    closed = position_log.closed_positions(book)
    held_days = [r.get("held_days") for r in closed if isinstance(r.get("held_days"), int)]
    fills = trade_history._load_fills(book)
    latest = _read_json(registry.data_dir(book) / "latest.json", {})
    gross = latest.get("gross")
    post = _read_json(_book_dir(book) / "post_sell.json", {})
    return {
        "closed_n": len(closed),
        "one_day_or_less_n": sum(d <= 1 for d in held_days),
        "three_days_or_less_n": sum(d <= 3 for d in held_days),
        "median_held_days": (sorted(held_days)[len(held_days) // 2] if held_days else None),
        "fills_n": len(fills),
        "gross": float(gross) if isinstance(gross, (int, float)) else None,
        "cash": (round(1.0 - float(gross), 4) if isinstance(gross, (int, float)) else None),
        "post_sell": post.get("summary") or {},
    }


def derive_lessons(book: str) -> dict:
    """Derive measured behavioural lessons.  Every rule carries its evidence and scope."""
    b = _clean_book(book)
    scope = _scope_for_book(b)
    metrics = _behaviour(b)
    lessons: list[dict] = []

    def lesson(
        code: str,
        rule: str,
        evidence: dict,
        *,
        shareability: str,
        evidence_status: str,
    ) -> dict:
        # Evidence can make a request worth presenting.  It cannot approve itself.
        return {
            "id": _stable_lesson_id(scope, code),
            "code": code,
            "scope": scope,
            "source_book": b,
            "shareability": shareability,
            "status": "requested",
            "approval_status": "requested",
            "authority": LESSON_AUTHORITY,
            "evidence_status": evidence_status,
            "evidence_cohort": "portfolio_v2_lesson_generation",
            "rule": rule,
            "evidence": evidence,
        }

    closed_n = int(metrics.get("closed_n") or 0)
    quick_n = int(metrics.get("three_days_or_less_n") or 0)
    if closed_n >= 8 and quick_n / closed_n >= 0.35:
        lessons.append(lesson(
            "churn_hysteresis",
            "Do not reverse a new position inside three sessions unless its explicit falsifier, "
            "a hard price/technical break, or a material thesis change has fired.",
            {"closed_n": closed_n, "closed_within_3d_n": quick_n,
             "rate": round(quick_n / closed_n, 4)},
            shareability="cross_market_candidate",
            evidence_status="threshold_met",
        ))

    h21_all = (metrics.get("post_sell") or {}).get("by_horizon", {}).get("21", {})
    # A full-exit lesson must not be trained on routine rebalance trims. Older ledgers lack the
    # nested split, so retain their aggregate only as a compatibility fallback.
    h21 = h21_all.get("full_exits") if isinstance(h21_all.get("full_exits"), dict) else h21_all
    if int(h21.get("n") or 0) >= 5 and float(h21.get("mean_relative_return") or 0.0) >= 0.03:
        lessons.append(lesson(
            "premature_exit_review",
            "Before a full exit, test trim-and-trail as the alternative; prior sales have "
            "subsequently outperformed the local benchmark.",
            h21,
            shareability="cross_market_candidate",
            evidence_status="threshold_met",
        ))

    cash = metrics.get("cash")
    if isinstance(cash, (int, float)) and cash >= 0.50:
        lessons.append(lesson(
            "cash_opportunity_cost",
            "Cash above 50% requires an explicit crash/degraded-data justification and a record "
            "of which market-specific candidates were rejected after deeper search.",
            {"cash": cash},
            shareability="market_specific",
            evidence_status="watch",
        ))

    payload = {
        "schema": "portfolio.lessons.v1",
        "book": b,
        "generated_at": _now(),
        "metrics": metrics,
        "lessons": lessons,
    }
    _write_json(_book_dir(b) / "lessons.json", payload)
    return payload


def refresh_all(asof: str | date | None = None) -> dict:
    """Advance post-sell outcomes and behavioural lessons for all active Brain books."""
    out = {"schema": "portfolio.learning_refresh.v1", "generated_at": _now(), "books": {}}
    for book in ACTIVE_BRAINS:
        try:
            post = refresh_post_sell(book, asof)
            lessons = derive_lessons(book)
            out["books"][book] = {"ok": True, "post_sell": post.get("summary"),
                                  "lessons_n": len(lessons.get("lessons") or [])}
        except Exception as exc:  # learning must never interrupt trading or the scheduler
            out["books"][book] = {"ok": False, "error": type(exc).__name__}
    _write_json(_DIR / "status.json", out)
    return out


def _operator_approvals() -> dict[str, dict]:
    """Read explicit operator state; a generated lesson can never approve itself."""
    payload = _read_json(_DIR / "operator_lesson_state.json", {})
    raw = payload.get("lessons") if isinstance(payload, dict) else None
    if isinstance(raw, dict):
        rows = [
            {**value, "id": key}
            for key, value in raw.items()
            if isinstance(value, dict)
        ]
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []
    approved: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        lesson_id = str(row.get("id") or "")
        if (
            _LESSON_ID_RE.fullmatch(lesson_id)
            and row.get("status") == "approved"
            and str(row.get("approved_by") or "").strip()
            and str(row.get("approved_at") or "").strip()
        ):
            approved[lesson_id] = {
                "approval_status": "approved",
                "status": "approved",
                "approved_by": str(row["approved_by"])[:120],
                "approved_at": str(row["approved_at"])[:40],
                "authority": "operator_approved_advisory",
            }
    return approved


def _normalise_local_lesson(book: str, value: Any) -> dict | None:
    """Validate a generated local lesson and upgrade pre-trace rows without granting authority."""
    if not isinstance(value, dict):
        return None
    b = _clean_book(book)
    code = str(value.get("code") or "").strip().lower()
    if not _LESSON_CODE_RE.fullmatch(code):
        return None
    expected_scope = _scope_for_book(b)
    raw_scope = str(value.get("scope") or "").strip()
    # Compatibility with pre-trace runtime rows: old scope values were book ids.  They remain
    # request-only and are never counted as application evidence until presented by this schema.
    scope = expected_scope if raw_scope in {"", b, expected_scope} else raw_scope
    if scope != expected_scope:
        return None
    lesson_id = _stable_lesson_id(scope, code)
    row = {
        **value,
        "id": lesson_id,
        "code": code,
        "scope": scope,
        "source_book": b,
        "status": "requested",
        "approval_status": "requested",
        "authority": LESSON_AUTHORITY,
        "evidence_cohort": value.get("evidence_cohort") or "pre_trace_unclassified",
    }
    row.update(_operator_approvals().get(lesson_id) or {})
    return row


def _validated_universal_lessons() -> list[dict]:
    """Return repeated mechanisms as hypotheses, never as auto-approved universal rules."""
    by_code: dict[str, list[dict]] = {}
    for book in ACTIVE_BRAINS:
        payload = _read_json(_book_dir(book) / "lessons.json", {})
        for value in payload.get("lessons") or []:
            lesson = _normalise_local_lesson(book, value)
            if lesson is None:
                continue
            shareability = lesson.get("shareability")
            old_active = value.get("status") == "active"
            if shareability in {"cross_market_candidate", "universal"} and (
                lesson.get("evidence_status") == "threshold_met" or old_active
            ):
                by_code.setdefault(lesson["code"], []).append(lesson)

    approvals = _operator_approvals()
    candidates: list[dict] = []
    for code, rows in sorted(by_code.items()):
        source_books = sorted({str(row.get("source_book") or "") for row in rows if row.get("source_book")})
        if len(source_books) < 2:
            continue
        candidate_id = _stable_lesson_id("CROSS_MARKET_CANDIDATE", code)
        candidate = {
            "id": candidate_id,
            "code": code,
            "scope": "CROSS_MARKET_CANDIDATE",
            "source_book": None,
            "source_books": source_books,
            "validated_in_books": source_books,
            "shareability": "cross_market_candidate",
            "status": "requested",
            "approval_status": "requested",
            "authority": LESSON_AUTHORITY,
            "evidence_status": "repeated_in_two_or_more_markets",
            "source_evidence_cohorts": sorted({
                str(row.get("evidence_cohort") or "pre_trace_unclassified") for row in rows
            }),
            "rule": rows[0].get("rule"),
            "evidence": {
                "recurrence_n": len(source_books),
                "basis": [
                    {
                        "lesson_id": row.get("id"),
                        "scope": row.get("scope"),
                        "source_book": row.get("source_book"),
                        "evidence_cohort": row.get("evidence_cohort"),
                        "evidence": row.get("evidence") or {},
                    }
                    for row in rows
                ],
            },
        }
        candidate.update(approvals.get(candidate_id) or {})
        candidates.append(candidate)
    return candidates


def accessible_lessons(book: str) -> list[dict]:
    """Exact lesson records that this book may see and later cite."""
    b = _clean_book(book)
    payload = _read_json(_book_dir(b) / "lessons.json", {})
    own = [
        lesson
        for value in (payload.get("lessons") or [])
        if (lesson := _normalise_local_lesson(b, value)) is not None
    ]
    return sorted(own + _validated_universal_lessons(), key=lambda row: str(row.get("id") or ""))


def _record_presentation(book: str, asof: str, lessons: list[dict]) -> dict:
    b = _clean_book(book)
    day = str(asof or "")[:10]
    lesson_ids = [str(row["id"]) for row in lessons]
    lesson_snapshots = [
        {
            key: lesson.get(key)
            for key in (
                "id", "code", "scope", "status", "approval_status", "authority",
                "approved_by", "approved_at", "shareability", "rule", "evidence_status",
                "evidence", "evidence_cohort", "source_book", "source_books",
                "source_evidence_cohorts",
            )
            if lesson.get(key) is not None
        }
        for lesson in lessons
    ]
    presentation_id = f"presentation.v1.{_sha256([b, day, lesson_snapshots])[:24]}"
    row = {
        "schema": "portfolio.lesson_presentation.v1",
        "presentation_id": presentation_id,
        "book": b,
        "book_scope": _scope_for_book(b),
        "asof": day,
        "presented_at": _now(),
        "lesson_ids": lesson_ids,
        "lessons": lesson_snapshots,
        "evidence_cohort": "portfolio_v2_lesson_trace",
        "authority": APPLICATION_AUTHORITY,
    }
    path = _book_dir(b) / "presentations.jsonl"
    with _trace_lock(b):
        prior = _read_jsonl(path)
        if any(existing.get("presentation_id") == presentation_id for existing in prior):
            return next(existing for existing in prior if existing.get("presentation_id") == presentation_id)
        if not _append_jsonl(path, row):
            raise OSError("lesson_presentation_write_failed")
    return row


def _latest_presentation(book: str, asof: str) -> dict | None:
    b = _clean_book(book)
    day = str(asof or "")[:10]
    rows = [
        row for row in _read_jsonl(_book_dir(b) / "presentations.jsonl")
        if row.get("book") == b and str(row.get("asof") or "")[:10] == day
    ]
    return rows[-1] if rows else None


def prompt_block(book: str, max_chars: int = 2600, *, asof: str | None = None) -> str:
    """Compact advisory memory plus the exact bounded lesson ids the next PM may cite."""
    b = _clean_book(book)
    presentation_key = (b, str(asof or "")[:10])
    if asof is not None:
        # A stale same-day presentation from an earlier attempted turn must never authorize the
        # current PM.  Re-arm the key only after the exact current block is durably recorded.
        _ACTIVE_PRESENTATIONS.pop(presentation_key, None)
    own = _read_json(_book_dir(b) / "lessons.json", {})
    post = _read_json(_book_dir(b) / "post_sell.json", {})
    limit = max(400, int(max_chars))
    lines = ["## PORTFOLIO META-MEMORY (measured; advisory/request-only)"]
    metrics = own.get("metrics") or {}
    lines.append("Own behaviour: " + json.dumps({
        "gross": metrics.get("gross"),
        "closed_n": metrics.get("closed_n"),
        "closed_within_3d_n": metrics.get("three_days_or_less_n"),
        "median_held_days": metrics.get("median_held_days"),
    }, separators=(",", ":")))
    included_lessons: list[dict] = []
    for lesson in accessible_lessons(b):
        line = (
            f"- [ID {lesson['id']}][{lesson['scope']}][{lesson['approval_status']}] "
            f"{lesson.get('rule')} Evidence: "
            f"{json.dumps(lesson.get('evidence') or {}, separators=(',', ':'))}"
        )
        if len("\n".join(lines + [line])) > limit - 300:
            continue
        lines.append(line)
        included_lessons.append(lesson)
    recent = list(post.get("exits") or [])[-5:]

    def compact_sales(source: list[dict]) -> list[dict]:
        rows = []
        for rec in source:
            h = (rec.get("forward") or {}).get("21") or {}
            rows.append({
                "ticker": rec.get("ticker"),
                "sale_date": rec.get("exit_date"),
                "sale_kind": rec.get("sale_kind") or "unknown_sale",
                "fraction_sold": rec.get("fraction_of_position_sold"),
                "rel_21d": h.get("relative_return"),
                "status": h.get("status"),
            })
        return rows

    full_exits = [rec for rec in recent if rec.get("sale_kind") == "full_exit"]
    partial_trims = [rec for rec in recent if rec.get("sale_kind") == "partial_trim"]
    other_sales = [rec for rec in recent if rec.get("sale_kind") not in {"full_exit", "partial_trim"}]
    if full_exits:
        lines.append("Recent full-exit audit: " + json.dumps(compact_sales(full_exits), separators=(",", ":")))
    if partial_trims:
        lines.append("Recent partial-trim audit: " + json.dumps(compact_sales(partial_trims), separators=(",", ":")))
    if other_sales:
        lines.append("Recent unclassified-sale audit: " + json.dumps(compact_sales(other_sales), separators=(",", ":")))
    lines.append(
        "To cite a lesson, set decision_memo.lessons_applied to a JSON array containing only exact "
        "IDs shown above; use [] when none. Unknown, malformed, or foreign-market IDs reject the "
        "target. Lessons are advisory and never sizing or execution authority."
    )
    block = "\n".join(lines)[:limit]
    if asof is not None:
        presentation = _record_presentation(b, str(asof), included_lessons)
        _ACTIVE_PRESENTATIONS[presentation_key] = str(presentation["presentation_id"])
    return block


def _citation_ids(submission: dict | None) -> tuple[list[str], str | None]:
    memo = (submission or {}).get("decision_memo")
    raw = memo.get("lessons_applied") if isinstance(memo, dict) else None
    # Pre-trace submissions and explicit empty containers mean "no lesson cited".  Once a PM
    # attempts a non-empty citation, the shape and every id become fail-closed.
    if not raw:
        return [], None
    if not isinstance(raw, list):
        return [], "non_empty_lessons_applied_must_be_an_array"
    ids: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not _LESSON_ID_RE.fullmatch(value):
            return [], "malformed_lesson_id"
        if value not in ids:
            ids.append(value)
    return sorted(ids), None


def _submission_sha256(submission: dict | None) -> str:
    clean = dict(submission or {})
    clean.pop("_lesson_trace", None)
    return _sha256(clean)


def prepare_lesson_trace(book: str, asof: str, submission: dict | None) -> dict:
    """Validate citations against the exact persisted prompt presentation.

    This function is read-only.  It prepares stable ids, but no application exists until the
    trusted execution boundary later reports ``queued`` or ``executed``.
    """
    b = _clean_book(book)
    cited_ids, error = _citation_ids(submission)
    if error:
        return {"ok": False, "error": error, "cited_ids": []}
    if not cited_ids:
        return {"ok": True, "cited_ids": [], "application_required": False}
    active_id = _ACTIVE_PRESENTATIONS.get((b, str(asof or "")[:10]))
    presentation = next(
        (
            row
            for row in reversed(_read_jsonl(_book_dir(b) / "presentations.jsonl"))
            if row.get("presentation_id") == active_id
            and row.get("book") == b
            and str(row.get("asof") or "")[:10] == str(asof or "")[:10]
        ),
        None,
    )
    if presentation is None:
        return {
            "ok": False,
            "error": "no_current_persisted_lesson_presentation",
            "cited_ids": cited_ids,
        }
    presented = {
        str(row.get("id") or ""): row
        for row in (presentation.get("lessons") or [])
        if isinstance(row, dict)
    }
    expected_scopes = {_scope_for_book(b), "CROSS_MARKET_CANDIDATE"}
    for lesson_id in cited_ids:
        lesson = presented.get(lesson_id)
        if lesson is None:
            return {
                "ok": False,
                "error": "lesson_id_not_presented_or_foreign",
                "cited_ids": cited_ids,
                "rejected_id": lesson_id,
            }
        if lesson.get("scope") not in expected_scopes:
            return {
                "ok": False,
                "error": "lesson_scope_not_accessible_to_book",
                "cited_ids": cited_ids,
                "rejected_id": lesson_id,
            }
    day = str(asof or "")[:10]
    submission_hash = _submission_sha256(submission)
    presentation_id = str(presentation.get("presentation_id") or "")
    decision_id = f"decision.v1.{_sha256([b, day, presentation_id, submission_hash])[:24]}"
    application_id = f"application.v1.{_sha256([decision_id, presentation_id, cited_ids])[:24]}"
    return {
        "ok": True,
        "schema": "portfolio.lesson_trace_pointer.v1",
        "book": b,
        "book_scope": _scope_for_book(b),
        "accepted_asof": day,
        "presentation_id": presentation_id,
        "cited_ids": cited_ids,
        "lessons": [presented[lesson_id] for lesson_id in cited_ids],
        "submission_sha256": submission_hash,
        "decision_id": decision_id,
        "application_id": application_id,
        "application_required": True,
        "authority": APPLICATION_AUTHORITY,
        "evidence_cohort": "portfolio_v2_lesson_trace",
    }


def attach_lesson_trace(book: str, asof: str, submission: dict | None) -> dict:
    """Sanitize any model-supplied trace metadata and attach only a trusted pointer."""
    if not isinstance(submission, dict):
        return {"ok": True, "cited_ids": [], "application_required": False}
    submission.pop("_lesson_trace", None)
    prepared = prepare_lesson_trace(book, asof, submission)
    if prepared.get("ok") and prepared.get("application_required"):
        submission["_lesson_trace"] = {
            key: prepared[key]
            for key in (
                "schema", "book", "book_scope", "accepted_asof", "presentation_id",
                "cited_ids", "submission_sha256", "decision_id", "application_id",
                "authority", "evidence_cohort",
            )
        }
    return prepared


def _trace_pointer(submission: dict | None) -> dict | None:
    """Return only a structurally trusted pointer attached by :func:`attach_lesson_trace`."""
    trace = (submission or {}).get("_lesson_trace")
    if not isinstance(trace, dict):
        return None
    decision_id = str(trace.get("decision_id") or "")
    application_id = str(trace.get("application_id") or "")
    presentation_id = str(trace.get("presentation_id") or "")
    cited_ids = trace.get("cited_ids")
    if (
        not _DECISION_ID_RE.fullmatch(decision_id)
        or not _APPLICATION_ID_RE.fullmatch(application_id)
        or not _PRESENTATION_ID_RE.fullmatch(presentation_id)
        or not isinstance(cited_ids, list)
        or not all(isinstance(value, str) and _LESSON_ID_RE.fullmatch(value) for value in cited_ids)
    ):
        return None
    return trace


def _lesson_citation_requested(submission: dict | None) -> bool:
    memo = (submission or {}).get("decision_memo")
    if not isinstance(memo, dict):
        return False
    value = memo.get("lessons_applied")
    return value not in (None, [], {}, "")


def trace_links(submission: dict | None, *, target_status: str | None = None) -> dict:
    """Outcome links, gated so planned/rejected intent never masquerades as an application."""
    trace = _trace_pointer(submission)
    if trace is None:
        return {}
    decision_id = str(trace["decision_id"])
    application_id = str(trace["application_id"])
    cited_ids = list(trace["cited_ids"])
    base = {
        "lesson_presentation_id": trace["presentation_id"],
        "lesson_trace_cohort": LESSON_TRACE_COHORT,
    }
    accepted = target_status in {"queued", "executed"}
    if not accepted:
        return {
            **base,
            "lesson_trace_status": "planned_not_accepted",
            "planned_decision_id": decision_id,
            "planned_lesson_application_id": application_id,
            "lesson_ids_planned": cited_ids,
        }
    book = str(trace.get("book") or "")
    try:
        application = next(
            (row for row in applications(book) if row.get("application_id") == application_id),
            None,
        )
    except Exception:
        application = None
    if application is None:
        return {
            **base,
            "lesson_trace_status": "accepted_application_pending",
            "planned_decision_id": decision_id,
            "planned_lesson_application_id": application_id,
            "lesson_ids_planned": cited_ids,
        }
    return {
        **base,
        "lesson_trace_status": (
            "accepted_executed" if application.get("executed") is True else "accepted_queued"
        ),
        "decision_id": decision_id,
        "lesson_application_ids": [application_id],
        "lesson_ids_cited": cited_ids,
    }


def _material_difference(
    submission: dict,
    effective_target: dict[str, float],
    executed_trades: list[dict] | None = None,
) -> dict:
    actions = {name: [] for name in ("adds", "holds", "trims")}
    weight_changes: dict[str, dict] = {}
    for holding in submission.get("holdings") or []:
        if not isinstance(holding, dict):
            continue
        ticker = str(holding.get("ticker") or "").upper().strip()
        action = str(
            holding.get("action_effective")
            or holding.get("action_requested")
            or holding.get("action")
            or ""
        ).lower()
        if ticker and action in {"add", "hold", "trim"}:
            actions[f"{action}s"].append(ticker)
        before = holding.get("prior_target_weight")
        after = effective_target.get(ticker)
        try:
            before_n = float(before)
            after_n = float(after) if after is not None else None
        except (TypeError, ValueError):
            continue
        if after_n is not None and abs(after_n - before_n) > 1e-8:
            weight_changes[ticker] = {
                "from": round(before_n, 8),
                "to": round(after_n, 8),
            }
    exits = sorted({
        str(row.get("ticker") or "").upper().strip()
        for row in (submission.get("exit_decisions") or [])
        if isinstance(row, dict) and str(row.get("action") or "").lower() == "exit"
        and str(row.get("ticker") or "").strip()
    })
    compact_trades = [
        {
            key: trade.get(key)
            for key in ("ticker", "side", "shares", "price", "value", "fill_price_source")
            if trade.get(key) is not None
        }
        for trade in (executed_trades or [])
        if isinstance(trade, dict)
    ]
    result = {
        **{key: sorted(set(values)) for key, values in actions.items()},
        "exits": exits,
        "weights": {
            str(ticker).upper().strip(): round(float(weight), 8)
            for ticker, weight in sorted((effective_target or {}).items())
        },
        "weight_changes": weight_changes,
        "executed_trades": compact_trades,
    }
    result["no_change"] = not bool(
        result["adds"] or result["trims"] or exits or weight_changes or compact_trades
    )
    return result


def _valid_iso_day(value: Any) -> bool:
    text = str(value or "")
    if len(text) != 10:
        return False
    try:
        return date.fromisoformat(text).isoformat() == text
    except (TypeError, ValueError):
        return False


def _valid_initial_application(row: dict, book: str, application_id: str) -> bool:
    decision_id = str(row.get("decision_id") or "")
    presentation_id = str(row.get("presentation_id") or "")
    accepted_asof = str(row.get("accepted_asof") or "")
    submission_hash = str(row.get("submission_sha256") or "")
    target_hash = str(row.get("target_sha256") or "")
    lesson_ids = row.get("lesson_ids")
    lesson_basis = row.get("lesson_basis")
    expected_scopes = {_scope_for_book(book), "CROSS_MARKET_CANDIDATE"}
    if (
        row.get("schema") != "portfolio.lesson_application.v1"
        or row.get("book_scope") != _scope_for_book(book)
        or row.get("target_status") != "queued"
        or row.get("executed") is not False
        or row.get("executed_at") is not None
        or not _valid_iso_day(accepted_asof)
        or not _DECISION_ID_RE.fullmatch(decision_id)
        or not _PRESENTATION_ID_RE.fullmatch(presentation_id)
        or not _TRANSACTION_ID_RE.fullmatch(submission_hash)
        or not _TRANSACTION_ID_RE.fullmatch(target_hash)
        or not isinstance(lesson_ids, list)
        or not lesson_ids
        or not all(
            isinstance(value, str)
            and _LESSON_ID_RE.fullmatch(value)
            and value.split(".", 4)[2] in expected_scopes
            for value in lesson_ids
        )
        or not isinstance(lesson_basis, list)
        or [str(value.get("id") or "") for value in lesson_basis if isinstance(value, dict)]
        != lesson_ids
        or not isinstance(row.get("material_difference"), dict)
    ):
        return False
    expected_decision_id = (
        f"decision.v1.{_sha256([book, accepted_asof, presentation_id, submission_hash])[:24]}"
    )
    expected_application_id = (
        f"application.v1.{_sha256([decision_id, presentation_id, lesson_ids])[:24]}"
    )
    return decision_id == expected_decision_id and application_id == expected_application_id


def _valid_settled_fills(value: Any, transaction_id: str, executed_at: str) -> bool:
    if not isinstance(value, list):
        return False
    seen: set[str] = set()
    for fill in value:
        if not isinstance(fill, dict):
            return False
        fill_id = str(fill.get("fill_id") or "")
        ticker = str(fill.get("ticker") or "")
        if (
            not _TRANSACTION_ID_RE.fullmatch(fill_id)
            or fill_id in seen
            or fill.get("transaction_id") != transaction_id
            or str(fill.get("date") or "")[:10] != executed_at
            or not ticker
            or ticker != ticker.upper()
            or str(fill.get("side") or "").lower() not in {"buy", "sell"}
        ):
            return False
        try:
            shares = float(fill.get("shares"))
            price = float(fill.get("price"))
            fill_value = float(fill.get("value"))
        except (TypeError, ValueError):
            return False
        if (
            not math.isfinite(shares)
            or shares <= 0
            or not math.isfinite(price)
            or price <= 0
            or not math.isfinite(fill_value)
            or fill_value < 0
        ):
            return False
        seen.add(fill_id)
    return True


def _execution_proof_sha256(row: dict) -> str:
    """Digest the compact receipt-derived fields retained after the outbox is acknowledged."""
    proof = {
        key: row.get(key)
        for key in (
            "schema", "application_id", "decision_id", "presentation_id", "book",
            "accepted_asof", "target_sha256", "target_status", "executed", "executed_at",
            "settlement_transaction_id", "settlement_verified", "execution_evidence",
            "settlement_receipt_sha256", "settled_fills", "authority", "evidence_cohort",
        )
    }
    return _sha256(proof)


def _valid_execution_transition(current: dict, row: dict) -> bool:
    transaction_id = str(row.get("settlement_transaction_id") or "")
    executed_at = str(row.get("executed_at") or "")
    if (
        row.get("schema") != "portfolio.lesson_application_transition.v1"
        or row.get("target_status") != "executed"
        or row.get("executed") is not True
        or row.get("settlement_verified") is not True
        or row.get("execution_evidence") != "hash_bound_paper_settlement_receipt"
        or not _valid_iso_day(executed_at)
        or not _TRANSACTION_ID_RE.fullmatch(transaction_id)
        or not _TRANSACTION_ID_RE.fullmatch(str(row.get("settlement_receipt_sha256") or ""))
        or not _TRANSACTION_ID_RE.fullmatch(str(row.get("execution_proof_sha256") or ""))
        or row.get("execution_proof_sha256") != _execution_proof_sha256(row)
        or row.get("application_id") != current.get("application_id")
        or row.get("decision_id") != current.get("decision_id")
        or row.get("presentation_id") != current.get("presentation_id")
        or row.get("accepted_asof") != current.get("accepted_asof")
        or row.get("target_sha256") != current.get("target_sha256")
        or not _valid_settled_fills(row.get("settled_fills"), transaction_id, executed_at)
    ):
        return False
    if current.get("executed") is True:
        return (
            current.get("settlement_transaction_id") == transaction_id
            and current.get("settlement_receipt_sha256") == row.get("settlement_receipt_sha256")
            and current.get("settled_fills") == row.get("settled_fills")
        )
    return True


def applications(book: str) -> list[dict]:
    """Latest verified v2 state for each stable application id, oldest decision first.

    Cohort-less/pre-v2 rows are deliberately invisible.  An ``executed`` bit is accepted only from
    the typed, receipt-verified transition that follows an initial application row; a malformed or
    standalone transition can therefore never manufacture post-v2 evidence on read.
    """
    b = _clean_book(book)
    by_id: dict[str, dict] = {}
    for row in _read_jsonl(_book_dir(b) / "applications.jsonl"):
        application_id = str(row.get("application_id") or "")
        if (
            not _APPLICATION_ID_RE.fullmatch(application_id)
            or row.get("evidence_cohort") != LESSON_TRACE_COHORT
            or row.get("authority") != APPLICATION_AUTHORITY
            or row.get("book") != b
        ):
            continue
        if row.get("schema") == "portfolio.lesson_application.v1":
            if not _valid_initial_application(row, b, application_id):
                continue
            current = by_id.get(application_id)
            if current is None:
                by_id[application_id] = dict(row)
            elif any(
                current.get(key) != row.get(key)
                for key in (
                    "decision_id", "presentation_id", "accepted_asof", "submission_sha256",
                    "target_sha256", "lesson_ids", "lesson_basis", "material_difference",
                )
            ):
                continue
            continue
        if row.get("schema") != "portfolio.lesson_application_transition.v1":
            continue
        current = by_id.get(application_id)
        if current is None or not _valid_execution_transition(current, row):
            continue
        by_id[application_id] = {**current, **row}
    return sorted(
        by_id.values(),
        key=lambda row: (str(row.get("accepted_asof") or ""), str(row.get("application_id") or "")),
    )


def _receipt_for_application(book: str, application_id: str) -> dict | None:
    try:
        from portfolio import paper_account

        for receipt in paper_account.pending_settlement_receipts(book):
            decision = receipt.get("decision_snapshot") or {}
            submission = decision.get("submission") if isinstance(decision, dict) else None
            trace = submission.get("_lesson_trace") if isinstance(submission, dict) else None
            if isinstance(trace, dict) and trace.get("application_id") == application_id:
                return receipt
    except Exception:
        return None
    return None


def _execution_transition_payload(
    book: str,
    application: dict,
    receipt: dict,
    *,
    settled_asof: str,
) -> dict:
    expected_hash = str(application.get("target_sha256") or "")
    receipt_hash = str(receipt.get("target_sha256") or "")
    receipt_target = receipt.get("target")
    decision = receipt.get("decision_snapshot") or {}
    bound_hash = str(decision.get("target_sha256") or "") if isinstance(decision, dict) else ""
    if (
        receipt.get("schema") != "paper_settlement_receipt.v1"
        or not isinstance(receipt_target, dict)
        or not expected_hash
        or receipt_hash != expected_hash
        or bound_hash != expected_hash
        or _target_sha256(receipt_target) != expected_hash
    ):
        return {"ok": False, "error": "settlement_target_hash_mismatch"}
    transaction_id = str(receipt.get("transaction_id") or "")
    if not _TRANSACTION_ID_RE.fullmatch(transaction_id):
        return {"ok": False, "error": "malformed_settlement_transaction_id"}
    receipt_submission = decision.get("submission") if isinstance(decision, dict) else None
    receipt_trace = _trace_pointer(receipt_submission)
    if (
        receipt.get("portfolio_id") != book
        or receipt_trace is None
        or receipt_trace.get("book") != book
        or receipt_trace.get("application_id") != application.get("application_id")
        or receipt_trace.get("decision_id") != application.get("decision_id")
        or receipt_trace.get("presentation_id") != application.get("presentation_id")
        or str(decision.get("accepted_asof") or "")[:10]
        != str(application.get("accepted_asof") or "")[:10]
    ):
        return {"ok": False, "error": "settlement_decision_lineage_mismatch"}
    fills = receipt.get("fills")
    if not isinstance(fills, list) or any(
        not isinstance(fill, dict)
        or str(fill.get("transaction_id") or "") != transaction_id
        or not _TRANSACTION_ID_RE.fullmatch(str(fill.get("fill_id") or ""))
        for fill in fills
    ):
        return {"ok": False, "error": "settlement_fill_transaction_mismatch"}
    settlement_day = str(receipt.get("settlement_asof") or "")[:10]
    if not settlement_day or (
        settled_asof and str(settled_asof)[:10] != settlement_day
    ):
        return {"ok": False, "error": "settlement_asof_mismatch"}
    transition = {
        "schema": "portfolio.lesson_application_transition.v1",
        "application_id": application["application_id"],
        "decision_id": application["decision_id"],
        "presentation_id": application["presentation_id"],
        "book": book,
        "accepted_asof": application.get("accepted_asof"),
        "transitioned_at": _now(),
        "target_status": "executed",
        "executed": True,
        "executed_at": settlement_day,
        "settlement_transaction_id": transaction_id,
        "settlement_verified": True,
        "execution_evidence": "hash_bound_paper_settlement_receipt",
        "settlement_receipt_sha256": _sha256(receipt),
        "target_sha256": receipt_hash,
        "settled_fills": [
            {
                key: fill.get(key)
                for key in (
                    "fill_id", "transaction_id", "date", "ticker", "side",
                    "shares", "price", "value",
                )
                if fill.get(key) is not None
            }
            for fill in fills
        ],
        "authority": APPLICATION_AUTHORITY,
        "evidence_cohort": LESSON_TRACE_COHORT,
    }
    transition["execution_proof_sha256"] = _execution_proof_sha256(transition)
    return {"ok": True, "transition": transition}


def _append_execution_transition(
    book: str,
    application: dict,
    receipt: dict,
    *,
    settled_asof: str,
) -> dict:
    built = _execution_transition_payload(
        book, application, receipt, settled_asof=settled_asof
    )
    if not built.get("ok"):
        return built
    transition = built["transition"]
    if not _append_jsonl(_book_dir(book) / "applications.jsonl", transition):
        return {"ok": False, "error": "application_transition_write_failed"}
    return {"ok": True, "application": {**application, **transition}, "transitioned": True}


def _recover_application_from_receipt(
    book: str,
    submission: dict,
    receipt: dict,
) -> dict:
    """Rebuild the missing initial row after a crash, using only sealed receipt provenance."""
    trace = _trace_pointer(submission)
    if trace is None:
        return {"ok": False, "error": "missing_receipt_lesson_trace"}
    cited_ids = trace.get("cited_ids")
    if (
        trace.get("book") != book
        or trace.get("book_scope") != _scope_for_book(book)
        or not isinstance(cited_ids, list)
        or not cited_ids
        or not all(isinstance(value, str) and _LESSON_ID_RE.fullmatch(value) for value in cited_ids)
    ):
        return {"ok": False, "error": "malformed_receipt_lesson_trace"}
    presentation_id = str(trace.get("presentation_id") or "")
    presentation = next(
        (
            row
            for row in _read_jsonl(_book_dir(book) / "presentations.jsonl")
            if row.get("presentation_id") == presentation_id
            and row.get("book") == book
            and str(row.get("asof") or "")[:10] == str(trace.get("accepted_asof") or "")[:10]
        ),
        None,
    )
    if presentation is None:
        return {"ok": False, "error": "missing_receipt_presentation"}
    presented = {
        str(row.get("id") or ""): row
        for row in (presentation.get("lessons") or [])
        if isinstance(row, dict)
    }
    expected_scopes = {_scope_for_book(book), "CROSS_MARKET_CANDIDATE"}
    if any(
        lesson_id not in presented or presented[lesson_id].get("scope") not in expected_scopes
        for lesson_id in cited_ids
    ):
        return {"ok": False, "error": "receipt_lesson_not_presented_or_foreign"}
    submission_hash = _submission_sha256(submission)
    accepted_asof = str(trace.get("accepted_asof") or "")[:10]
    decision_id = f"decision.v1.{_sha256([book, accepted_asof, presentation_id, submission_hash])[:24]}"
    application_id = f"application.v1.{_sha256([decision_id, presentation_id, cited_ids])[:24]}"
    if any(
        trace.get(key) != expected
        for key, expected in (
            ("submission_sha256", submission_hash),
            ("decision_id", decision_id),
            ("application_id", application_id),
        )
    ):
        return {"ok": False, "error": "receipt_lesson_trace_identity_mismatch"}
    target = receipt.get("target")
    if not isinstance(target, dict):
        return {"ok": False, "error": "receipt_target_missing"}
    target_hash = _target_sha256(target)
    decision = receipt.get("decision_snapshot") or {}
    if (
        receipt.get("target_sha256") != target_hash
        or not isinstance(decision, dict)
        or decision.get("target_sha256") != target_hash
        or str(decision.get("accepted_asof") or "")[:10] != accepted_asof
    ):
        return {"ok": False, "error": "receipt_target_or_asof_mismatch"}
    row = {
        "schema": "portfolio.lesson_application.v1",
        "application_id": application_id,
        "decision_id": decision_id,
        "presentation_id": presentation_id,
        "book": book,
        "book_scope": _scope_for_book(book),
        "accepted_asof": accepted_asof,
        "recorded_at": _now(),
        "recovered_from_settlement_receipt": True,
        "lesson_ids": cited_ids,
        "lesson_basis": [presented[lesson_id] for lesson_id in cited_ids],
        "submission_sha256": submission_hash,
        "target_sha256": target_hash,
        "target_status": "queued",
        "executed": False,
        "executed_at": None,
        "material_difference": _material_difference(submission, target),
        "authority": APPLICATION_AUTHORITY,
        "execution_trace_status": "queued",
        "evidence_cohort": LESSON_TRACE_COHORT,
    }
    if not _append_jsonl(_book_dir(book) / "applications.jsonl", row):
        return {"ok": False, "error": "recovered_application_write_failed"}
    return {"ok": True, "application": row}


def record_application(
    book: str,
    asof: str,
    submission: dict | None,
    effective_target: dict[str, float] | None,
    *,
    target_status: str,
    executed_trades: list[dict] | None = None,
    settlement_receipt_id: str | None = None,
) -> dict:
    """Create one idempotent application only after the target was accepted by execution."""
    b = _clean_book(book)
    if target_status not in {"queued", "executed"}:
        return {"ok": True, "recorded": False, "reason": "target_not_accepted"}
    if not isinstance(submission, dict) or not isinstance(effective_target, dict):
        return {"ok": False, "recorded": False, "error": "missing_accepted_target"}
    prepared = prepare_lesson_trace(b, asof, submission)
    trace = submission.get("_lesson_trace")
    if not prepared.get("ok"):
        return {"ok": False, "recorded": False, "error": prepared.get("error")}
    if not prepared.get("application_required"):
        return {"ok": True, "recorded": False, "reason": "no_lesson_cited"}
    if not isinstance(trace, dict) or any(
        trace.get(key) != prepared.get(key)
        for key in ("presentation_id", "cited_ids", "submission_sha256", "decision_id", "application_id")
    ):
        return {"ok": False, "recorded": False, "error": "trusted_lesson_trace_mismatch"}

    target_hash = _target_sha256(effective_target)
    row = {
        "schema": "portfolio.lesson_application.v1",
        "application_id": prepared["application_id"],
        "decision_id": prepared["decision_id"],
        "presentation_id": prepared["presentation_id"],
        "book": b,
        "book_scope": _scope_for_book(b),
        "accepted_asof": str(asof or "")[:10],
        "recorded_at": _now(),
        "lesson_ids": prepared["cited_ids"],
        "lesson_basis": prepared["lessons"],
        "submission_sha256": prepared["submission_sha256"],
        "target_sha256": target_hash,
        "target_status": "queued",
        "accepted_target_status": target_status,
        "execution_trace_status": (
            "pending_receipt_transition" if target_status == "executed" else "queued"
        ),
        "executed": False,
        "executed_at": None,
        "material_difference": _material_difference(
            submission, effective_target, executed_trades
        ),
        "authority": APPLICATION_AUTHORITY,
        "evidence_cohort": LESSON_TRACE_COHORT,
    }
    receipt: dict | None = None
    if target_status == "executed":
        receipt_id = str(settlement_receipt_id or "")
        if not _TRANSACTION_ID_RE.fullmatch(receipt_id):
            return {
                "ok": False,
                "recorded": False,
                "error": "executed_application_requires_settlement_receipt",
            }
        receipt = _receipt_for_application(b, row["application_id"])
        if receipt is None or str(receipt.get("transaction_id") or "") != receipt_id:
            return {
                "ok": False,
                "recorded": False,
                "error": "executed_application_receipt_not_found",
            }
        verified = _execution_transition_payload(b, row, receipt, settled_asof=asof)
        if not verified.get("ok"):
            return {"recorded": False, **verified}
    with _trace_lock(b):
        current = next(
            (value for value in applications(b) if value.get("application_id") == row["application_id"]),
            None,
        )
        if current is not None:
            if current.get("target_sha256") != target_hash:
                return {"ok": False, "recorded": False, "error": "application_target_conflict"}
            if target_status == "executed":
                if current.get("executed") is True:
                    if current.get("settlement_transaction_id") != receipt.get("transaction_id"):
                        return {
                            "ok": False,
                            "recorded": False,
                            "error": "application_settlement_transaction_conflict",
                        }
                    return {
                        "ok": True,
                        "recorded": False,
                        "deduplicated": True,
                        "application": current,
                    }
                return _append_execution_transition(b, current, receipt, settled_asof=asof)
            return {"ok": True, "recorded": False, "deduplicated": True, "application": current}
        if not _append_jsonl(_book_dir(b) / "applications.jsonl", row):
            return {"ok": False, "recorded": False, "error": "application_write_failed"}
        if target_status == "executed":
            result = _append_execution_transition(b, row, receipt, settled_asof=asof)
            result["recorded_initial"] = True
            return result
    return {"ok": True, "recorded": True, "application": row}


def settle_application(book: str, submission: dict | None, asof: str) -> dict:
    """Advance a queued application only through its exact hash-bound settlement receipt."""
    b = _clean_book(book)
    trace = _trace_pointer(submission)
    if trace is None:
        if (submission or {}).get("_lesson_trace") is not None or _lesson_citation_requested(submission):
            return {
                "ok": False,
                "transitioned": False,
                "error": "missing_or_malformed_trusted_lesson_trace",
            }
        return {"ok": True, "transitioned": False, "reason": "no_lesson_application"}
    if trace.get("book") != b:
        return {"ok": False, "transitioned": False, "error": "lesson_trace_book_mismatch"}
    application_id = str(trace["application_id"])
    with _trace_lock(b):
        current = next(
            (row for row in applications(b) if row.get("application_id") == application_id),
            None,
        )
        receipt = _receipt_for_application(b, application_id)
        if current is not None and current.get("executed") is True:
            if receipt is not None:
                verified = _execution_transition_payload(
                    b, current, receipt, settled_asof=asof
                )
                if not verified.get("ok"):
                    return {"transitioned": False, **verified}
                if current.get("settlement_transaction_id") != receipt.get("transaction_id"):
                    return {
                        "ok": False,
                        "transitioned": False,
                        "error": "application_settlement_transaction_conflict",
                    }
            return {"ok": True, "transitioned": False, "deduplicated": True, "application": current}
        if receipt is None:
            return {"ok": False, "transitioned": False, "error": "missing_settlement_receipt"}
        if current is None:
            recovered = _recover_application_from_receipt(b, submission or {}, receipt)
            if not recovered.get("ok"):
                return {"ok": False, "transitioned": False, "error": recovered.get("error")}
            current = recovered["application"]
        return _append_execution_transition(b, current, receipt, settled_asof=asof)


def application_finalization_status(
    book: str,
    submission: dict | None,
    *,
    settlement_receipt_id: str | None = None,
) -> dict:
    """Prove that a cited application is durably executed before receipt acknowledgement.

    Empty/no-lesson decisions remain backward compatible.  Once a lesson was cited, however, only
    the typed executed transition for this exact presentation and (when supplied) transaction can
    satisfy finalization.  Callers must retain the settlement receipt when ``ok`` is false.
    """
    b = _clean_book(book)
    trace = _trace_pointer(submission)
    if trace is None:
        if (submission or {}).get("_lesson_trace") is not None or _lesson_citation_requested(submission):
            return {
                "ok": False,
                "required": True,
                "error": "missing_or_malformed_trusted_lesson_trace",
            }
        return {"ok": True, "required": False, "reason": "no_lesson_application"}
    if trace.get("book") != b:
        return {"ok": False, "required": True, "error": "lesson_trace_book_mismatch"}
    current = next(
        (
            row for row in applications(b)
            if row.get("application_id") == trace.get("application_id")
        ),
        None,
    )
    if current is None:
        return {"ok": False, "required": True, "error": "lesson_application_missing"}
    if (
        current.get("decision_id") != trace.get("decision_id")
        or current.get("presentation_id") != trace.get("presentation_id")
        or current.get("executed") is not True
        or current.get("settlement_verified") is not True
    ):
        return {"ok": False, "required": True, "error": "lesson_application_not_executed"}
    transaction_id = str(current.get("settlement_transaction_id") or "")
    if not _TRANSACTION_ID_RE.fullmatch(transaction_id):
        return {"ok": False, "required": True, "error": "lesson_application_transaction_invalid"}
    expected_receipt_id = str(settlement_receipt_id or "")
    if expected_receipt_id and expected_receipt_id != transaction_id:
        return {"ok": False, "required": True, "error": "lesson_application_receipt_mismatch"}
    return {
        "ok": True,
        "required": True,
        "application_id": current["application_id"],
        "decision_id": current["decision_id"],
        "presentation_id": current["presentation_id"],
        "settlement_transaction_id": transaction_id,
        "deduplicated_or_durable": True,
    }


def request_context(book: str, plane: str, reason: str, ticker: str | None = None) -> dict:
    """Queue a bounded context-access request for later orchestrator review."""
    b = _clean_book(book)
    p = str(plane or "").strip().lower()
    why = " ".join(str(reason or "").split())[:_MAX_REASON]
    tk = str(ticker or "").upper().strip()[:16] or None
    if not _PLANE_RE.fullmatch(p):
        return {"ok": False, "error": "plane must be a lowercase typed identifier"}
    if len(why) < 20:
        return {"ok": False, "error": "reason must explain the decision-relevant gap"}
    existing = context_requests(limit=500)
    dedupe = (b, p, tk, why.lower())
    if any((r.get("book"), r.get("plane"), r.get("ticker"), str(r.get("reason") or "").lower()) == dedupe
           for r in existing[-200:]):
        return {"ok": True, "deduped": True}
    row = {"schema": "portfolio.context_request.v1", "id": f"ctx-{uuid.uuid4().hex[:16]}",
           "ts": _now(), "book": b, "plane": p, "ticker": tk, "reason": why,
           "status": "queued_for_orchestrator_review", "authority": "request_only"}
    if not _append_jsonl(_DIR / "context_requests.jsonl", row):
        return {"ok": False, "error": "context_request_write_failed"}
    return {"ok": True, "request": row}


def context_requests(limit: int | None = 50) -> list[dict]:
    """Return the latest transition for each typed request, oldest first."""
    by_id: dict[str, dict] = {}
    for row in _read_jsonl(_DIR / "context_requests.jsonl"):
        request_id = str(row.get("id") or "")
        if request_id:
            by_id[request_id] = {**by_id.get(request_id, {}), **row}
    rows = sorted(by_id.values(), key=lambda row: str(row.get("ts") or ""))
    if limit is None:
        return rows
    return rows[-max(1, min(int(limit), 500)):]


def advance_context_request(
    request_id: str,
    status_value: str,
    *,
    directive_id: str | None = None,
    note: str | None = None,
) -> bool:
    """Append one audited request transition; never grants data or code authority."""
    rid = str(request_id or "")
    status_value = str(status_value or "")
    if not rid.startswith("ctx-") or status_value not in _CONTEXT_STATUSES:
        return False
    existing = next((row for row in context_requests(limit=None) if row.get("id") == rid), None)
    if existing is None:
        return False
    if (existing.get("status") == status_value and
            (not directive_id or existing.get("directive_id") == str(directive_id)[:40])):
        return True
    current_status = str(existing.get("status") or "")
    current_rank = _CONTEXT_STATUS_RANK.get(current_status, -1)
    target_rank = _CONTEXT_STATUS_RANK.get(status_value, -1)
    # Reconciliation may observe an older directive delta after the request has already advanced.
    # Treat that as satisfied, never append a regressive state transition. Conflicting terminal
    # states remain fail-closed and require explicit operator resolution.
    if current_rank > target_rank:
        return True
    if current_rank == target_rank and current_status != status_value:
        return False
    row = {
        "schema": "portfolio.context_request_transition.v1",
        "id": rid,
        "ts": _now(),
        "status": status_value,
        "authority": "request_only",
    }
    if directive_id:
        row["directive_id"] = str(directive_id)[:40]
    if note:
        row["note"] = " ".join(str(note).split())[:280]
    return _append_jsonl(_DIR / "context_requests.jsonl", row)


def acknowledge_context_directives(directive_ids: set[str] | list[str] | tuple[str, ...]) -> int:
    """Mirror Macro's directive acknowledgements onto their originating context requests."""
    seen = {str(value) for value in directive_ids if value}
    advanced = 0
    for row in context_requests(limit=None):
        if (row.get("directive_id") in seen and
                row.get("status") in {"directive_queued", "published_to_orchestrator"}):
            advanced += int(advance_context_request(
                row["id"], "acknowledged_by_orchestrator", directive_id=row.get("directive_id")
            ))
    return advanced


def status() -> dict:
    return {
        "schema": "mastermind_portfolio_learning.v1",
        "generated_at": _now(),
        "books": {b: {
            "lessons": _read_json(_book_dir(b) / "lessons.json", {}),
            "post_sell": _read_json(_book_dir(b) / "post_sell.json", {}).get("summary") or {},
            "lesson_applications": applications(b),
            "lesson_presentations_n": len(_read_jsonl(_book_dir(b) / "presentations.jsonl")),
        } for b in ACTIVE_BRAINS},
        "validated_universal_lessons": _validated_universal_lessons(),
        "context_requests": context_requests(limit=50),
        "note": ("This is Mastermind Portfolio learning. The public user chatbot remains Mastermind AI "
                 "and has separate state and authority."),
    }
