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

import json
import math
import os
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
_DIR = _ROOT / "data" / "portfolio_learning"
ACTIVE_BRAINS = ("autonomous", "china", "hk")
HORIZONS = (5, 10, 21, 63)

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


def _decision_exit(book: str, ticker: str, fill_date: str) -> dict:
    """Best matching explicit exit memo at or before a fill (the decision is often prior-close)."""
    try:
        from portfolio import registry
        path = registry.data_dir(book) / "decisions.jsonl"
        candidates = []
        for row in _read_jsonl(path):
            if str(row.get("asof") or "")[:10] > str(fill_date)[:10]:
                continue
            for rec in row.get("exit_decisions") or []:
                if str(rec.get("ticker") or "").upper() == ticker.upper():
                    candidates.append((str(row.get("asof") or ""), rec))
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
        exit_id = f"{b}:{fill_date}:{ticker}:{int(fill.get('_seq') or 0)}"
        row = dict(by_id.get(exit_id) or {})
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
        memo = _decision_exit(b, ticker, fill_date)
        if memo:
            row["decision"] = {
                k: memo.get(k) for k in
                ("action", "reason", "evidence", "falsifier", "why_now") if memo.get(k) is not None
            }

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
    metrics = _behaviour(b)
    lessons: list[dict] = []
    closed_n = int(metrics.get("closed_n") or 0)
    quick_n = int(metrics.get("three_days_or_less_n") or 0)
    if closed_n >= 8 and quick_n / closed_n >= 0.35:
        lessons.append({
            "code": "churn_hysteresis",
            "scope": b,
            "shareability": "universal",
            "status": "active",
            "rule": ("Do not reverse a new position inside three sessions unless its explicit falsifier, "
                     "a hard price/technical break, or a material thesis change has fired."),
            "evidence": {"closed_n": closed_n, "closed_within_3d_n": quick_n,
                         "rate": round(quick_n / closed_n, 4)},
        })

    h21_all = (metrics.get("post_sell") or {}).get("by_horizon", {}).get("21", {})
    # A full-exit lesson must not be trained on routine rebalance trims. Older ledgers lack the
    # nested split, so retain their aggregate only as a compatibility fallback.
    h21 = h21_all.get("full_exits") if isinstance(h21_all.get("full_exits"), dict) else h21_all
    if int(h21.get("n") or 0) >= 5 and float(h21.get("mean_relative_return") or 0.0) >= 0.03:
        lessons.append({
            "code": "premature_exit_review",
            "scope": b,
            "shareability": "universal",
            "status": "active",
            "rule": ("Before a full exit, test trim-and-trail as the alternative; prior sales have "
                     "subsequently outperformed the local benchmark."),
            "evidence": h21,
        })

    cash = metrics.get("cash")
    if isinstance(cash, (int, float)) and cash >= 0.50:
        lessons.append({
            "code": "cash_opportunity_cost",
            "scope": b,
            "shareability": "market_specific",
            "status": "watch",
            "rule": ("Cash above 50% requires an explicit crash/degraded-data justification and a record "
                     "of which market-specific candidates were rejected after deeper search."),
            "evidence": {"cash": cash},
        })

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


def _validated_universal_lessons() -> list[dict]:
    by_code: dict[str, list[dict]] = {}
    for book in ACTIVE_BRAINS:
        payload = _read_json(_book_dir(book) / "lessons.json", {})
        for lesson in payload.get("lessons") or []:
            if lesson.get("shareability") == "universal" and lesson.get("status") == "active":
                by_code.setdefault(str(lesson.get("code")), []).append(lesson)
    # Cross-market transfer requires recurrence in at least two independent books.
    return [rows[0] | {"validated_in_books": sorted({r.get("scope") for r in rows})}
            for rows in by_code.values() if len({r.get("scope") for r in rows}) >= 2]


def prompt_block(book: str, max_chars: int = 2600) -> str:
    """Compact self-mirror injected into the next portfolio decision, never raw history."""
    b = _clean_book(book)
    own = _read_json(_book_dir(b) / "lessons.json", {})
    post = _read_json(_book_dir(b) / "post_sell.json", {})
    lines = ["## PORTFOLIO META-MEMORY (measured; advisory)"]
    metrics = own.get("metrics") or {}
    lines.append("Own behaviour: " + json.dumps({
        "gross": metrics.get("gross"),
        "closed_n": metrics.get("closed_n"),
        "closed_within_3d_n": metrics.get("three_days_or_less_n"),
        "median_held_days": metrics.get("median_held_days"),
    }, separators=(",", ":")))
    for lesson in own.get("lessons") or []:
        lines.append(f"- [{lesson.get('status')}] {lesson.get('rule')} Evidence: "
                     f"{json.dumps(lesson.get('evidence') or {}, separators=(',', ':'))}")
    for lesson in _validated_universal_lessons():
        if b not in (lesson.get("validated_in_books") or []):
            lines.append(f"- [cross-market execution lesson; validated in "
                         f"{','.join(lesson.get('validated_in_books') or [])}] {lesson.get('rule')}")
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
    lines.append("Market-specific lessons stay local. This memory informs judgment; it is not sizing authority.")
    return "\n".join(lines)[:max(400, int(max_chars))]


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
        } for b in ACTIVE_BRAINS},
        "validated_universal_lessons": _validated_universal_lessons(),
        "context_requests": context_requests(limit=50),
        "note": ("This is Mastermind Portfolio learning. The public user chatbot remains Mastermind AI "
                 "and has separate state and authority."),
    }
