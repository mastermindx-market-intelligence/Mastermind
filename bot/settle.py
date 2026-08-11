"""Market-hours discipline for the free-form Brain books — queue on close, settle at the open.

The active Brain books (autonomous, china, hk) each submit a COMPLETE target book once per trading
day, AFTER their market's close. Booking those as instantaneous fills at a stale / overnight price
is wrong — and re-running the build churns the book with phantom trims. Instead each book's run
calls ``execute_or_queue``: when its market is OPEN it rebalances at the live mark (real fills); when
CLOSED it QUEUES the decided target (``paper_account.save_pending_target``) and books NOTHING. The
scheduler then calls ``settle_open`` at the next open, which fills the queued target with ONE
rebalance at the live open marks. This mirrors the flagship's queue_orders/fill_pending discipline
(bot/phase2.py), generalized to a full target (sells + trims + buys) via ``paper_account.settle_target``.

**Open-price semantics (A4a fix):** the settle job runs at ~15:00 UTC (10 am ET), which means
``yahoo_feed.warm`` returns the LAST print of the still-open partial-day bar rather than the
true session open (9:30 ET), while the flagship (phase2.py) fills via ``paper_account.fill_pending``
which inherits the live mark at queue time — roughly the open.  To unify semantics, the USD-book
``_price`` helper now tries:
  1. ``polygon.day_open(ticker)`` — the snapshot ``day.o`` field, the flagship's semantic.
  2. ``yahoo_feed.open_price_local(ticker)`` — the latest daily bar's Open column.
  3. ``paper_account._current_price(ticker)`` — today's Close/last (previous behaviour).
Each fill gets a ``fill_price_source`` stamp (``polygon_open`` / ``yahoo_open`` / ``last_price``)
so mixed semantics are at least auditable when the fallback fires.

Calendars: the US book (autonomous) uses ``portfolio.market_calendar`` (NYSE); the Greater-China
books (china, hk) use ``portfolio.china_calendar`` (A-share session). Both expose ``is_open()``.
"""
from __future__ import annotations

from datetime import date

import bot  # noqa: F401  -> vendor/macro onto sys.path

_ASIA = {"china", "hk"}


def _calendar(pid: str):
    if pid in _ASIA:
        from portfolio import china_calendar
        return china_calendar
    from portfolio import market_calendar
    return market_calendar


def is_open(pid: str) -> bool:
    """True iff `pid`'s market is open right now. Defaults to False (queue) on any calendar error —
    fail SAFE: never book an off-hours fill because the calendar hiccuped. The HK book gates on the
    HKEX calendar+hours (venue='HK'); china_calendar otherwise defaults to the A-share session, which
    would read HKEX-only holidays as open and the 15:00–16:00 HK hour as closed."""
    try:
        cal = _calendar(pid)
        if pid == "hk":
            return bool(cal.is_open(venue="HK"))
        return bool(cal.is_open())
    except Exception:
        return False


def _diff_trades(before: dict, after: dict, prices: dict,
                 sources: dict | None = None) -> list[dict]:
    """Compute the executed trade list from a before/after positions snapshot.

    ``sources`` is an optional ``{ticker: fill_price_source}`` map.  When provided,
    each trade record gains a ``fill_price_source`` field (``'polygon_open'``,
    ``'yahoo_open'``, or ``'last_price'``) so mixed-semantics fills are auditable."""
    trades = []
    for t in sorted(set(before) | set(after)):
        b = float((before.get(t) or {}).get("shares") or 0.0)
        a = float((after.get(t) or {}).get("shares") or 0.0)
        d = a - b
        if abs(d) < 1e-6:
            continue
        px = prices.get(t)
        row: dict = {
            "ticker": t,
            "side": "buy" if d > 0 else "sell",
            "shares": round(abs(d), 4),
            "price": round(px, 4) if px else None,
            "value": round(abs(d) * px, 2) if px else None,
        }
        if sources is not None:
            row["fill_price_source"] = sources.get(t, "last_price")
        trades.append(row)
    return trades


def _unpriceable_target_stop(
    pid: str,
    requirements: dict[str, list[str]],
    *,
    pending_retained: bool,
) -> dict:
    """Structured fail-closed result for an incompletely priceable target."""
    blocked = sorted({str(t).upper() for t in requirements.get("tickers") or []})
    exits = sorted({str(t).upper() for t in requirements.get("exit_tickers") or []})
    positive = sorted(
        {str(t).upper() for t in requirements.get("positive_target_tickers") or []}
    )
    exit_only = bool(blocked) and set(blocked) == set(exits)
    try:
        from control_plane.guardrail import GuardrailResult, Severity
        GuardrailResult.failed(
            "unpriceable_complete_target",
            Severity.HARD_STOP,
            detail=f"missing trusted target price: {', '.join(blocked)}"[:200],
            action_taken=(
                "no account write; pending target retained for retry"
                if pending_retained
                else "no account write; target not executed"
            ),
        ).log(job="settle_execution_price_guard", book=pid)
    except Exception:  # noqa: BLE001 - audit failure never re-enables execution
        pass
    return {
        "executed": [],
        "queued": False,
        "skipped": (
            "unpriceable_exit_prices" if exit_only else "unpriceable_target_prices"
        ),
        "unpriceable_targets": blocked,
        "unpriceable_exits": exits,
        "unpriceable_positive_targets": positive,
        "pending_retained": bool(pending_retained),
    }


def _unpriceable_exception_stop(pid: str, exc, *, pending_retained: bool) -> dict:
    return _unpriceable_target_stop(
        pid,
        {
            "tickers": list(exc.tickers),
            "exit_tickers": list(getattr(exc, "exit_tickers", [])),
            "positive_target_tickers": list(
                getattr(exc, "positive_target_tickers", [])
            ),
        },
        pending_retained=pending_retained,
    )


def execute_or_queue(
    pid: str,
    target: dict[str, float],
    prices: dict[str, float],
    asof: str,
    *,
    market_open: bool | None = None,
    decision_snapshot: dict | None = None,
) -> dict:
    """Market-hours-aware execution for a Brain book. OPEN → settle any target queued on a prior
    closed session, then rebalance to `target` at the live marks (real fills). CLOSED → persist
    `target` to settle at the next open; book NO fills (no off-hours trading, no churn on re-run).
    Returns {executed: [...], queued: bool, market_open: bool, error?}. `prices` is the same marks
    the book uses for NAV, so fills and NAV stay consistent."""
    from portfolio import registry
    if registry.is_archived(pid):
        return {
            "executed": [],
            "queued": False,
            "market_open": False,
            **registry.archived_run_result(pid, asof),
        }
    from portfolio import paper_account
    try:
        target = paper_account.validate_target_weights(target)
    except paper_account.InvalidTargetWeights as exc:
        return {
            "executed": [],
            "queued": False,
            "market_open": bool(market_open),
            "skipped": "invalid_target_weights",
            "error": str(exc),
            "invalid_target_reason": exc.reason,
        }
    if market_open is None:
        market_open = is_open(pid)
    out: dict = {"executed": [], "queued": False, "market_open": bool(market_open)}
    try:
        recovered_at_entry = paper_account.recover_paper_transaction(pid)
        outstanding_receipts = paper_account.pending_settlement_receipts(pid)
    except Exception as exc:  # noqa: BLE001 - never layer new intent over unresolved execution
        return {
            **out,
            "skipped": "settlement_recovery_failed",
            "error": repr(exc)[:240],
        }
    if outstanding_receipts:
        receipt = outstanding_receipts[0]
        return {
            **out,
            "skipped": "settlement_finalization_pending",
            "settlement_recovered": True,
            "settlement_receipt_id": receipt.get("transaction_id"),
            "receipt_retained": True,
        }
    before = dict((paper_account._load_account(pid).get("positions") or {}))
    if market_open:
        # Preserve the autonomous cutover fence before considering quote gaps.  A malformed or v1
        # queue is quarantined even when the current target also happens to contain an unpriceable
        # exit; quote safety must never become a route around executable-state validation.
        preflight = paper_account.preflight_pending_target(pid)
        if not preflight["ok"]:
            out.update({k: v for k, v in preflight.items() if k != "pending"})
            return out
        pending = preflight["pending"]

        # Validate the current target against one pre-write account snapshot.  In particular, do
        # not settle an older queue first and only then discover that the current target intended
        # an unpriceable exit: that would turn an atomic daily decision into two partial writes.
        current_missing = paper_account.unpriceable_target_requirements(
            target,
            prices,
            portfolio_id=pid,
            state={"positions": before},
        )
        if current_missing["tickers"]:
            retained = False
            retry_queued = False
            retry_error = None
            stale_quarantine = None
            # The current PM target was built from the still-unmodified account, so it supersedes
            # every older queue.  Atomically replace stale pending intent even when the old target,
            # rather than the current one, is what needs the missing quote.  Retaining the old queue
            # could later sell a name the newest decision explicitly kept (or vice versa).
            try:
                paper_account.save_pending_target(
                    target,
                    asof,
                    portfolio_id=pid,
                    decision_snapshot=decision_snapshot,
                )
                retained = True
                retry_queued = True
            except Exception as exc:  # noqa: BLE001 - execution remains stopped either way
                retry_error = repr(exc)[:200]
                # Atomic replacement preserves the old file on failure, but that is precisely the
                # superseded intent we must not let a later settle execute. Recoverably isolate it;
                # the account remains untouched and an operator can inspect/restore the artifact.
                if pending:
                    try:
                        stale_quarantine = paper_account.quarantine_pending_target(
                            pid,
                            "latest_target_replacement_failed",
                            pending,
                        )
                    except Exception as quarantine_exc:  # noqa: BLE001 - remain stopped and surface it
                        stale_quarantine = {
                            "status": "quarantine_failed",
                            "recoverable": paper_account.pending_target_file_exists(pid),
                            "error": repr(quarantine_exc)[:200],
                        }
            out.update(
                _unpriceable_target_stop(
                    pid, current_missing, pending_retained=retained
                )
            )
            out["queued"] = retry_queued
            out["retry_target_queued"] = retry_queued
            if retry_error:
                out["retry_queue_error"] = retry_error
            if stale_quarantine:
                out["stale_pending_quarantine"] = stale_quarantine
                out["stale_pending_executable"] = (
                    stale_quarantine.get("status") != "quarantined"
                )
            return out
        # A direct open-session PM run carries a newer complete target than any target left in the
        # overnight queue.  Never execute the old queue and then rebalance again: that creates a
        # hidden sell/buy round trip, corrupts average cost, and attributes fills to an intent the
        # PM has already superseded.  Persist the current target atomically first (so a crash leaves
        # the newest recoverable intent), then settle that one target exactly once.  ``settle_open``
        # remains the only entry point that executes an already-queued target without a newer PM
        # decision in hand.
        try:
            paper_account.save_pending_target(
                target,
                asof,
                portfolio_id=pid,
                decision_snapshot=decision_snapshot,
            )
        except Exception as exc:  # noqa: BLE001 - no account mutation is allowed after this failure
            out.update({
                "error": repr(exc)[:200],
                "skipped": "latest_target_queue_failed",
                "pending_retained": False,
            })
            if pending:
                try:
                    quarantine = paper_account.quarantine_pending_target(
                        pid,
                        "latest_target_replacement_failed",
                        pending,
                    )
                    out["stale_pending_quarantine"] = quarantine
                    out["stale_pending_executable"] = (
                        quarantine.get("status") != "quarantined"
                    )
                except Exception as quarantine_exc:  # noqa: BLE001 - remain stopped and surface it
                    out["stale_pending_quarantine"] = {
                        "status": "quarantine_failed",
                        "recoverable": paper_account.pending_target_file_exists(pid),
                        "error": repr(quarantine_exc)[:200],
                    }
                    out["stale_pending_executable"] = True
            try:
                from control_plane.guardrail import GuardrailResult, Severity
                GuardrailResult.failed(
                    "latest_target_queue_write",
                    Severity.HARD_STOP,
                    detail=f"save_pending_target raised: {exc!r}"[:200],
                    action_taken="no account write; superseded queue quarantined when present",
                ).log(job="execute_or_queue", book=pid)
            except Exception:  # noqa: BLE001
                pass
            return out
        try:
            paper_account.settle_target(prices, asof, portfolio_id=pid)
        except paper_account.PendingTargetQuarantined as exc:
            # A v1 autonomous target must never be followed by the current-session rebalance in the
            # same call: quarantine is an explicit fail-closed outcome, not a partial success.
            out.update({
                "skipped": "pending_target_quarantined",
                "quarantined": True,
                "quarantine": exc.result,
            })
            return out
        except paper_account.UnpriceableExitPrices as exc:
            # settle_target checks the queued target at the lowest full-target boundary.  It raises
            # before rebalance and deliberately leaves pending_target.json intact for the next open.
            out.update(_unpriceable_exception_stop(pid, exc, pending_retained=True))
            return out
        except Exception as e:                                            # noqa: BLE001
            recovery = None
            recovery_error = None
            try:
                recovery = paper_account.recover_paper_transaction(pid)
            except Exception as recovery_exc:  # noqa: BLE001 - remain fail-closed, do not auto-read
                recovery_error = repr(recovery_exc)[:200]
            if recovery and recovery.get("status") == "committed":
                out["settlement_recovered"] = True
                out["transaction_id"] = recovery.get("transaction_id")
            else:
                out["error"] = repr(e)[:200]
                out["skipped"] = "settle_failed"
                out["pending_retained"] = paper_account.pending_target_file_exists(pid)
                if recovery_error:
                    out["recovery_error"] = recovery_error
            try:
                if recovery and recovery.get("status") == "committed":
                    from control_plane import run_events
                    run_events.append({
                        "kind": "paper_transaction_recovered",
                        "job": "execute_or_queue",
                        "book": pid,
                        "status": "pass",
                        "severity": "INFO",
                        "actor": "deterministic_engine",
                        "extra": {"transaction_id": recovery.get("transaction_id")},
                    })
                else:
                    from control_plane.guardrail import GuardrailResult, Severity
                    GuardrailResult.failed(
                        "settle_account_write",
                        Severity.HARD_STOP,
                        detail=f"settle/rebalance raised mid-flight: {e!r}"[:200],
                        action_taken="transaction remains unresolved; no account read or further execution",
                    ).log(job="execute_or_queue", book=pid)
            except Exception:  # noqa: BLE001
                pass
            if not recovery or recovery.get("status") != "committed":
                return out
        after = dict((paper_account._load_account(pid).get("positions") or {}))
        out["executed"] = _diff_trades(before, after, prices)
        try:
            receipts = paper_account.pending_settlement_receipts(pid)
            if receipts:
                out["settlement_receipt_id"] = receipts[0].get("transaction_id")
        except Exception as exc:  # noqa: BLE001 - committed state remains fenced by its receipt
            out["settlement_receipt_error"] = repr(exc)[:240]
    else:
        try:
            paper_account.save_pending_target(
                target,
                asof,
                portfolio_id=pid,
                decision_snapshot=decision_snapshot,
            )
            out["queued"] = True
        except Exception as e:                                            # noqa: BLE001
            out["error"] = repr(e)[:200]
            try:
                from control_plane.guardrail import GuardrailResult, Severity
                GuardrailResult.failed(
                    "settle_queue_write",
                    Severity.HARD_STOP,
                    detail=f"save_pending_target raised: {e!r}"[:200],
                    action_taken="target NOT queued; book will not settle at next open",
                ).log(job="execute_or_queue", book=pid)
            except Exception:  # noqa: BLE001
                pass
    return out


# ---------------------------------------------------------------------------
# the open-session settle (scheduler-driven)
# ---------------------------------------------------------------------------

def _held(pid: str) -> set[str]:
    from portfolio import paper_account
    return set((paper_account._load_account(pid).get("positions") or {}).keys())


def _open_price_usd(ticker: str,
                    *,
                    _polygon=None,
                    _yahoo=None,
                    _paper=None) -> tuple[float | None, str]:
    """Best-estimate USD session-OPEN price for a US-listed ticker, with source attribution.

    Priority (A4a): polygon day-open (snapshot ``day.o``) → yahoo daily-bar Open → last price
    (today's Close / vendored snapshot).  Returns ``(price_or_None, source_label)`` where
    ``source_label`` is one of ``'polygon_open'``, ``'yahoo_open'``, or ``'last_price'``.

    The ``_polygon`` / ``_yahoo`` / ``_paper`` kwargs are injection points for tests: pass
    callables with the same signatures as the real functions to avoid network calls.
    """
    # Allow tests to inject stubs; default to the real modules (lazy to avoid import cost
    # on the Asia/non-USD code paths that call _price with ccy!='USD').
    if _polygon is None:
        try:
            from data_layer import polygon as _pg
            _polygon = _pg.day_open
        except Exception:
            _polygon = lambda t: None  # noqa: E731

    if _yahoo is None:
        try:
            from data_layer import yahoo_feed as _yf
            _yahoo = _yf.open_price_local
        except Exception:
            _yahoo = lambda t: None  # noqa: E731

    if _paper is None:
        try:
            from portfolio import paper_account as _pa
            _paper = _pa._current_price
        except Exception:
            _paper = lambda t: None  # noqa: E731

    t = (ticker or "").upper().strip()
    if not t:
        return None, "last_price"

    try:
        px = _polygon(t)
        if px and float(px) > 0:
            return float(px), "polygon_open"
    except Exception:
        pass

    try:
        px = _yahoo(t)
        if px and float(px) > 0:
            return float(px), "yahoo_open"
    except Exception:
        pass

    try:
        px = _paper(t)
        if px and float(px) > 0:
            return float(px), "last_price"
    except Exception:
        pass

    return None, "last_price"


def _price_and_sources(pid: str, syms,
                       *,
                       _open_price_fn=None) -> tuple[dict[str, float], dict[str, str]]:
    """Live marks for `syms` in `pid`'s base currency plus per-ticker source labels.

    For USD books (autonomous): prefer session open price (A4a) via ``_open_price_usd``.
    For the ETF book: the dedicated live-Yahoo Close pricer (its own warm logic).
    For HKD/CNY books: FX-converted last price (unchanged — no open semantics after Asia close).

    Returns ``(prices, sources)`` where ``sources`` maps ticker → source label
    (``'polygon_open'`` | ``'yahoo_open'`` | ``'last_price'`` | ``'etf_universe'``).
    ``_open_price_fn`` is an injection point for tests (same signature as ``_open_price_usd``).
    """
    from portfolio import paper_account, registry
    prices: dict[str, float] = {}
    sources: dict[str, str] = {}

    if pid == "etf":
        # ETF book: the dedicated live-Yahoo pricer (unchanged — has its own warm logic).
        from portfolio import etf_universe
        etf_universe.warm(syms)
        for t in syms:
            px = etf_universe.price(t)
            if px and px > 0:
                prices[t] = px
                sources[t] = "etf_universe"
        return prices, sources

    ccy = registry.currency(pid)
    if ccy == "USD":
        # USD Brain books (autonomous): prefer session open so fill semantics match the flagship.
        # The source label is stamped on each executed trade for auditability.
        price_fn = _open_price_fn or _open_price_usd
        for t in syms:
            px, src = price_fn(t)
            if px and px > 0:
                prices[t] = px
                sources[t] = src
        return prices, sources

    from portfolio import fx
    for t in syms:
        base = fx.usd_to(paper_account._current_price(t), ccy)
        if base and base > 0:
            prices[t] = base
            sources[t] = "last_price"
    return prices, sources


def _price(pid: str, syms, *, _open_price_fn=None) -> dict[str, float]:
    """Prices only — thin wrapper over ``_price_and_sources`` for callers that don't need sources."""
    prices, _ = _price_and_sources(pid, syms, _open_price_fn=_open_price_fn)
    return prices


def _finalize_settlement_receipt(
    pid: str,
    receipt: dict,
    *,
    _open_price_fn=None,
    recovered: bool,
) -> dict:
    """Idempotently finish the non-numeric side effects of a committed paper settlement.

    Account and fills are already authoritative at this point.  The receipt remains until the
    position ledger, NAV mark, and rationale-bearing published contract all succeed; a restart can
    therefore retry those projections without ever replaying a fill.
    """
    from portfolio import paper_account, position_log, registry

    transaction_id = str(receipt.get("transaction_id") or "")
    settlement_asof = str(receipt.get("settlement_asof") or date.today().isoformat())[:10]
    target = paper_account.validate_target_weights(
        receipt.get("target") or {}, require_canonical_tickers=True
    )
    before = dict(receipt.get("account_before_positions") or {})
    after = dict(receipt.get("account_after_positions") or {})
    bench = registry.benchmark(pid)
    symbols = set(before) | set(after) | set(target) | {bench}
    prices, sources = _price_and_sources(
        pid, symbols, _open_price_fn=_open_price_fn
    )
    # If a live quote vanished after the fill committed, the immutable paper-fill price remains a
    # truthful mark for completing this recovery projection.  It is never used to invent a fill.
    for fill in receipt.get("fills") or []:
        if not isinstance(fill, dict):
            continue
        ticker = str(fill.get("ticker") or "").upper()
        try:
            price = float(fill.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        if ticker and price > 0 and ticker not in prices:
            prices[ticker] = price
            sources[ticker] = "committed_fill"

    executed = _diff_trades(before, after, prices, sources=sources)
    decision = receipt.get("decision_snapshot") or {}
    submission = (
        decision.get("submission")
        if isinstance(decision, dict) and isinstance(decision.get("submission"), dict)
        else None
    )
    failures: list[str] = []
    try:
        position_log.update(
            [
                {
                    "ticker": ticker,
                    "sleeve": "brain",
                    "weight": weight,
                    "entry_price": prices.get(ticker),
                }
                for ticker, weight in target.items()
                if ticker in prices
            ],
            settlement_asof,
            portfolio_id=pid,
        )
    except Exception as exc:  # noqa: BLE001 - keep receipt for a later exact retry
        failures.append(f"position_log:{exc!r}"[:240])
    try:
        paper_account.mark(prices, settlement_asof, portfolio_id=pid)
    except Exception as exc:  # noqa: BLE001 - keep receipt for a later exact retry
        failures.append(f"mark:{exc!r}"[:240])
    republished = (
        _republish(pid, settlement_asof, submission=submission)
        if submission is not None
        else _republish(pid, settlement_asof)
    )
    if isinstance(republished, dict) and republished.get("ok") is False:
        failures.append(f"republish:{republished.get('error') or 'failed'}"[:240])

    if failures:
        return {
            "ok": False,
            "skipped": "settlement_finalization_pending",
            "executed": executed,
            "settled_to": sorted(target),
            "transaction_id": transaction_id,
            "settlement_recovered": recovered,
            "receipt_retained": True,
            "finalization_errors": failures,
            "republish": republished,
        }
    try:
        paper_account.acknowledge_settlement_receipt(transaction_id, pid)
    except Exception as exc:  # noqa: BLE001 - projections succeeded; retry only the acknowledgement
        return {
            "ok": False,
            "skipped": "settlement_receipt_ack_pending",
            "executed": executed,
            "settled_to": sorted(target),
            "transaction_id": transaction_id,
            "settlement_recovered": recovered,
            "receipt_retained": True,
            "finalization_errors": [f"ack:{exc!r}"[:240]],
            "republish": republished,
        }
    result = {
        "ok": True,
        "executed": executed,
        "settled_to": sorted(target),
        "transaction_id": transaction_id,
        "receipt_acknowledged": True,
    }
    if republished is not None:
        result["republish"] = republished
    if recovered:
        result["settlement_recovered"] = True
    return result


def settle_open(pid: str, asof: str | None = None,
                *,
                _open_price_fn=None) -> dict:
    """At `pid`'s market OPEN, fill the queued target (decided on a prior closed session) with one
    rebalance at the live open marks, re-mark NAV, and republish the book contract so the dashboard
    shows the filled positions. No-op (safe) if the market is closed or nothing is queued.

    For USD Brain books the fill prices are the session OPEN (polygon day.o → yahoo Open → last
    price fallback); each trade in ``executed`` carries a ``fill_price_source`` stamp so mixed
    semantics are auditable in the blotter.  ``_open_price_fn`` is an injection point for tests.
    """
    from portfolio import registry
    asof = asof or date.today().isoformat()
    if registry.is_archived(pid):
        return {"ok": False, **registry.archived_run_result(pid, asof)}
    from portfolio import paper_account, position_log
    if not is_open(pid):
        return {"ok": False, "skipped": "market_closed"}
    try:
        recovered_before_preflight = paper_account.recover_paper_transaction(pid)
        receipts = paper_account.pending_settlement_receipts(pid)
    except Exception as exc:  # noqa: BLE001 - unresolved executable state is a hard stop
        return {
            "ok": False,
            "skipped": "settlement_recovery_failed",
            "error": repr(exc)[:240],
        }
    if receipts:
        return _finalize_settlement_receipt(
            pid,
            receipts[0],
            _open_price_fn=_open_price_fn,
            recovered=True,
        )
    preflight = paper_account.preflight_pending_target(pid)
    if not preflight["ok"]:
        return {"ok": False, **{k: v for k, v in preflight.items() if k != "pending"}}
    pending = preflight["pending"]
    if not pending:
        return {"ok": False, "skipped": "nothing_queued"}
    decision_record = pending.get("decision_snapshot") or {}
    settled_submission = (
        decision_record.get("submission")
        if isinstance(decision_record, dict)
        and isinstance(decision_record.get("submission"), dict)
        else None
    )
    bench = registry.benchmark(pid)
    sym_set = set(_held(pid)) | {bench} | set(pending.get("target") or {})
    prices, sources = _price_and_sources(pid, sym_set, _open_price_fn=_open_price_fn)
    before = dict((paper_account._load_account(pid).get("positions") or {}))
    missing_prices = paper_account.unpriceable_target_requirements(
        pending.get("target") or {},
        prices,
        portfolio_id=pid,
        state={"positions": before},
    )
    if missing_prices["tickers"]:
        return {
            "ok": False,
            "market_open": True,
            **_unpriceable_target_stop(
                pid, missing_prices, pending_retained=True
            ),
        }
    recovered_transaction = None
    try:
        target = paper_account.settle_target(prices, asof, portfolio_id=pid) or {}
    except paper_account.PendingTargetQuarantined as exc:
        # The target changed between preflight and settlement.  The paper-account boundary rechecked
        # it and quarantined the incompatible replacement before any account write.
        return {
            "ok": False,
            "skipped": "pending_target_quarantined",
            "quarantined": True,
            "quarantine": exc.result,
        }
    except paper_account.UnpriceableExitPrices as exc:
        # TOCTOU recheck at paper_account.settle_target: still no account write and no queue clear.
        return {
            "ok": False,
            "market_open": True,
            **_unpriceable_exception_stop(pid, exc, pending_retained=True),
        }
    except Exception as _se:
        recovery = None
        recovery_error = None
        try:
            recovery = paper_account.recover_paper_transaction(pid)
        except Exception as recovery_exc:  # noqa: BLE001 - do not mask with an auto-recovering read
            recovery_error = repr(recovery_exc)[:200]
        try:
            if recovery and recovery.get("status") == "committed":
                from control_plane import run_events
                run_events.append({
                    "kind": "paper_transaction_recovered",
                    "job": "settle_open",
                    "book": pid,
                    "status": "pass",
                    "severity": "INFO",
                    "actor": "deterministic_engine",
                    "extra": {"transaction_id": recovery.get("transaction_id")},
                })
            else:
                from control_plane.guardrail import GuardrailResult, Severity
                GuardrailResult.failed(
                    "settle_open_account_write",
                    Severity.HARD_STOP,
                    detail=f"settle_target raised mid-flight: {_se!r}"[:200],
                    action_taken="transaction remains unresolved; settle aborted without account read",
                ).log(job="settle_open", book=pid)
        except Exception:  # noqa: BLE001
            pass
        if recovery and recovery.get("status") == "committed":
            target = dict(pending.get("target") or {})
            recovered_transaction = recovery
        else:
            result = {
                "ok": False,
                "error": repr(_se)[:200],
                "skipped": "settle_failed",
                "pending_retained": paper_account.pending_target_file_exists(pid),
            }
            if recovery_error:
                result["recovery_error"] = recovery_error
            return result
    try:
        receipts = paper_account.pending_settlement_receipts(pid)
    except Exception as exc:  # noqa: BLE001 - committed trade remains recoverable via its receipt
        return {
            "ok": False,
            "skipped": "settlement_receipt_unreadable",
            "error": repr(exc)[:240],
        }
    if receipts:
        return _finalize_settlement_receipt(
            pid,
            receipts[0],
            _open_price_fn=_open_price_fn,
            recovered=recovered_transaction is not None,
        )
    after = dict((paper_account._load_account(pid).get("positions") or {}))
    # Pass sources so each trade row is stamped with fill_price_source for auditability.
    executed = _diff_trades(before, after, prices, sources=sources)
    try:
        position_log.update([{"ticker": t, "sleeve": "brain", "weight": w, "entry_price": prices.get(t)}
                             for t, w in target.items() if t in prices], asof, portfolio_id=pid)
    except Exception:
        pass
    try:
        paper_account.mark(prices, asof, portfolio_id=pid)
    except Exception:
        pass
    republished = (
        _republish(pid, asof, submission=settled_submission)
        if settled_submission is not None
        else _republish(pid, asof)
    )
    result = {"ok": True, "executed": executed, "settled_to": sorted(target)}
    if republished is not None:
        result["republish"] = republished
    if recovered_transaction is not None:
        result["settlement_recovered"] = True
        result["transaction_id"] = recovered_transaction.get("transaction_id")
    return result


def _republish(pid: str, asof: str, *, submission: dict | None = None) -> dict | None:
    """Re-emit the book's published contract after a settle (so the dashboard reflects the fills),
    via the book module's republish(). Best-effort; never raises."""
    try:
        import importlib
        mod = importlib.import_module(f"bot.{pid}")
        if hasattr(mod, "republish"):
            return mod.republish(asof, submission=submission)
    except Exception as exc:  # noqa: BLE001 - settlement is committed; surface publish failure
        return {"ok": False, "error": repr(exc)[:200]}
    return None


def settle_us(asof: str | None = None) -> dict:
    """Settle the successor US Brain at the US open; archived ETF state stays frozen."""
    return {"autonomous": settle_open("autonomous", asof)}


def settle_asia(asof: str | None = None) -> dict:
    """Settle the queued targets for the Greater-China Brain books at the A-share open (scheduler job)."""
    return {pid: settle_open(pid, asof) for pid in ("china", "hk")}
