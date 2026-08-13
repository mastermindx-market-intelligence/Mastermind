"""The China portfolio — a free-form Opus Brain managing its own $1M all-China paper book.

The Greater-China sibling of ``bot/autonomous.py``. Once per Asia trading day (after the
A-share close), the China Brain:
  1. sees its current book (cash, holdings, live USD P&L) + the China macro regime,
  2. researches freely — the macro-dashboard China desks (regime, standouts, intake, brief)
     OR web search, its choice,
  3. submits a COMPLETE target book, one rationale per holding (no gate, no research paper),
  4. and the deterministic layer rebalances the paper account to those weights at the latest
     close, marks NAV in CNY vs the CSI 300, and logs the day.

The executable universe is positively verified single-company mainland A-shares (``*.SS`` /
``*.SZ``) only. ETFs, index funds, pooled products, warrants, Hong Kong listings, and ADRs are
context at most and can never become holdings. The book is marked natively in CNY. Everything is
scoped to portfolio_id="china" so no other book is touched.

Run:  python -m bot.china        (or the APScheduler 'china_daily' job, or POST /api/china/run)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import bot  # noqa: F401  -> vendor/macro onto sys.path

log = logging.getLogger(__name__)

PORTFOLIO_ID = "china"
SLEEVE = "brain"
_ROOT = Path(__file__).resolve().parent.parent
_MAX_TURNS = int(os.environ.get("CHINA_MAX_TURNS", "30"))

# Base currency + tradeable venue are registry-driven so the HK sibling (bot/hk.py) shares this code
# unchanged. The China book is mainland A-shares ONLY, marked natively in CNY (no cross-FX).
from portfolio import registry as _registry
BENCHMARK = _registry.benchmark(PORTFOLIO_ID)            # CSI 300 (000300.SS)
CURRENCY = _registry.currency(PORTFOLIO_ID)            # "CNY"
ALLOWED_VENUES = set(_registry.venues(PORTFOLIO_ID))   # {"A-share"} — empty set = unrestricted


# ---------------------------------------------------------------------------
# the daily entrypoint
# ---------------------------------------------------------------------------

def run_china(asof: str | None = None, *, force: bool = False, armed: bool = True,
              directive: str | None = None) -> dict:
    """Run one China turn end-to-end. Best-effort: every step degrades gracefully so a missing
    credential / price never leaves the book in a half-traded state."""
    from portfolio import china_calendar, paper_account

    asof = asof or date.today().isoformat()
    out: dict = {"portfolio_id": PORTFOLIO_ID, "asof": asof,
                 "ran_at": datetime.now(timezone.utc).isoformat()}
    today = _safe_date(asof)
    out["trading_day"] = china_calendar.is_trading_day(today) if today else None

    state0 = paper_account._load_account(PORTFOLIO_ID)
    inaugural = not _has_history() and not (state0.get("positions") or {})
    out["inaugural"] = inaugural

    # 0. FEED-HEALTH GATE (before the Brain). The A-share live feed (Tushare `daily`) is
    #    all-or-nothing: one bulk call prices the WHOLE market. When it is DOWN, currently-held
    #    names still mark off the stale vendored snapshot while brand-new candidates return
    #    priceable=false — an ASYMMETRIC map. On 2026-06-22 that fooled the Brain into parking
    #    ~48% cash citing a (false) "no investable candidates" constraint. Detect the outage as a
    #    first-class condition and refuse to transact on it: skip the Brain (it never sees the
    #    corrupted map) and carry the book unchanged. `force=True` overrides (operator escape hatch).
    from data_layer import feed_health
    venue = next(iter(ALLOWED_VENUES), "A-share")
    out["feed_health"] = feed_health.status(venue, asof)
    if armed and not force and out["feed_health"]["status"] == "down":
        log.warning(
            "China turn %s ABORTED — the %s live feed is unavailable. Held names would price off "
            "the stale snapshot while fresh candidates return priceable=false (an asymmetric map); "
            "skipping the Brain and carrying the book unchanged. Re-run with force=True to override.",
            asof, venue)
        armed = False
        out["feed_aborted"] = True

    # 0b. NIGHTLY COST TRIPWIRE (before the Brain). The armed Opus seat below is the dominant cost
    #    (~$1+). If this book has already hit the configured per-night USD cap, SKIP the seat and
    #    carry the book unchanged — same posture as the feed-health abort above. OFF by default
    #    (cap <= 0 → over_budget always False) so this is a no-op and the run is byte-identical.
    from brain import cost_guard
    if armed and cost_guard.over_budget(PORTFOLIO_ID, asof):
        log.warning("China turn %s — nightly cost cap hit ($%.2f / $%.2f); skipping the Brain and "
                    "carrying the book unchanged.", asof,
                    cost_guard.spent(PORTFOLIO_ID, asof), cost_guard.cap())
        armed = False
        out["cost_capped"] = True

    # 1. run the Brain (armed) → it researches and submits a target book with rationales
    from brain import china_mcp
    china_mcp.clear_submission()                 # never replay yesterday's decision
    brain: dict = {"ok": False, "skipped": not armed}
    if armed:
        try:
            # directive is an optional ad-hoc override (overnight reviews) — pass it through only when set
            brain = _run_brain(asof, inaugural, directive=directive) if directive else _run_brain(asof, inaugural)
        except Exception as e:                   # noqa: BLE001
            brain = {"ok": False, "error": repr(e)[:300]}
        # record this seat's known cost + token usage against the nightly per-book ledger.
        _usg = brain.get("usage") or {}
        cost_guard.record(
            PORTFOLIO_ID, brain.get("cost_usd"), asof,
            seat="china_brain",
            model=str(brain.get("model") or ""),
            input_tokens=int(_usg.get("input_tokens") or 0),
            output_tokens=int(_usg.get("output_tokens") or 0),
            cache_read_tokens=int(_usg.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(_usg.get("cache_creation_input_tokens") or 0),
        )
    out["brain"] = {k: brain.get(k) for k in ("ok", "cost_usd", "tools_used", "error", "run_id", "model")}

    # 2. read the normalized submitted book.  decision_submission rejects new off-venue adds.
    #    Keep the narrow filter below as defence in depth for malformed/legacy payloads, but never
    #    turn a trusted omission-carry row for an existing legacy position into an implicit sale.
    submission = china_mcp.read_submission()
    if submission and ALLOWED_VENUES:
        from brain import china_intake as _intake
        all_h = submission.get("holdings") or []
        held_at_start = set((state0.get("positions") or {}).keys())

        def _trusted_legacy_carry(h: dict) -> bool:
            ticker = str(h.get("ticker") or "").upper().strip()
            return bool(
                ticker in held_at_start
                and h.get("carried_forward") is True
                and h.get("action_effective") == "hold"
                and h.get("weight_source") == "omission_carry.v1"
                and h.get("carry_reason") == "missing_explicit_exit_decision"
            )

        kept = [
            h for h in all_h
            if _intake._venue(h.get("ticker")) in ALLOWED_VENUES
            or _trusted_legacy_carry(h)
        ]
        rejected = [
            h.get("ticker") for h in all_h
            if _intake._venue(h.get("ticker")) not in ALLOWED_VENUES
            and not _trusted_legacy_carry(h)
        ]
        normalized_rejected = [
            rec.get("ticker")
            for rec in ((submission.get("submission_audit") or {}).get("rejected") or [])
            if isinstance(rec, dict) and rec.get("reason") == "off_venue"
        ]
        if rejected:
            submission = {**submission, "holdings": kept}
        if rejected or normalized_rejected:
            out["rejected_offvenue"] = sorted(
                {str(ticker) for ticker in rejected + normalized_rejected if ticker}
            )
    # A fully explicit 100%-cash target is valid. Missing submission still carries the prior book.
    decided = bool(
        submission
        and isinstance(submission.get("holdings"), list)
        and (submission.get("summary") or "").strip()
    )
    out["decided"] = decided
    target_status = "proposed" if decided else "rejected_no_submission"
    effective_target: dict[str, float] | None = None
    lesson_validation: dict = {"ok": True, "cited_ids": []}
    if decided:
        try:
            from brain import portfolio_learning
            lesson_validation = portfolio_learning.attach_lesson_trace(
                PORTFOLIO_ID, asof, submission
            )
        except Exception as exc:  # noqa: BLE001 - non-empty citations fail closed
            raw_lessons = ((submission.get("decision_memo") or {}).get("lessons_applied")
                           if isinstance(submission.get("decision_memo"), dict) else None)
            lesson_validation = (
                {"ok": True, "cited_ids": [],
                 "warning": f"empty_trace_unavailable:{type(exc).__name__}"}
                if not raw_lessons
                else {"ok": False, "error": f"trace_validation_error:{type(exc).__name__}"}
            )
        out["lesson_citations"] = {
            key: lesson_validation.get(key)
            for key in ("ok", "error", "warning", "presentation_id", "cited_ids")
            if lesson_validation.get(key) is not None
        }
        if lesson_validation.get("decision_id"):
            out["lesson_citations"]["planned_decision_id"] = lesson_validation["decision_id"]
        if lesson_validation.get("application_id"):
            out["lesson_citations"]["planned_lesson_application_id"] = lesson_validation["application_id"]
        if not lesson_validation.get("ok"):
            decided = False
            out["decided"] = False
            target_status = "rejected_lesson_citations"
    quote_fallbacks = sorted(
        h.get("ticker")
        for h in ((submission or {}).get("holdings") or [])
        if h.get("holding_mark_source") == "account_avg_cost_fallback"
    )
    if decided and quote_fallbacks:
        # Average cost establishes inventory but cannot authorize a rebalance.
        # Freeze the complete account until every held line has a trusted quote.
        decided = False
        out["decided"] = False
        out["decision_boundary_frozen"] = {
            "reason": "held_position_quote_fallback",
            "tickers": quote_fallbacks,
        }
        target_status = "frozen_held_quote_fallback"

    # 2c. PACKET GATE (ruling R6, Charter P2/P3/P8). Boundary is AFTER the venue filter
    # (trusted Python) but BEFORE pricing + execute. On enforce+invalid → decided=False
    # (carry-forward), the same path the book takes when the Brain errors out (P2).
    _pgr = None
    if decided:
        try:
            from control_plane.packet_gate import process as _packet_process
            _pgr = _packet_process(
                PORTFOLIO_ID,
                submission,
                paper_account._load_account(PORTFOLIO_ID),
                extras={
                    "run_id":                brain.get("run_id") if isinstance(brain, dict) else "",
                    "asof":                  asof,
                    "mandate":               (submission.get("mandate") or
                                              "Manage the China A-share paper book with full discretion."),
                    "evidence_planes":       submission.get("evidence_planes") or [],
                    "source_provenance":     submission.get("source_provenance") or [],
                    "falsifiers":            submission.get("falsifiers") or [],
                    "liquidity_notes":       submission.get("liquidity_notes") or "<not provided>",
                    "expected_failure_mode": submission.get("expected_failure_mode") or "<not provided>",
                },
            )
            out["packet_id"]   = _pgr.packet_id
            out["packet_meta"] = _pgr.to_meta()
            if not _pgr.ok:
                decided = False
                out["decided"] = decided
                out["packet_rejected"] = True
                target_status = "rejected_packet_gate"
        except Exception as _pg_exc:   # noqa: BLE001 — gate must never block the book
            out["packet_gate_error"] = repr(_pg_exc)[:200]

    # 3. price the universe we might trade (targets ∪ held ∪ benchmark) — all converted to CNY,
    #    the book's base currency. The shared price store returns USD (A-share/HK already FX'd to
    #    USD there); we convert that to CNY so A-shares stay native CNY, HK (HKD) and US ADRs (USD)
    #    are marked at the prevailing rate, and the CSI 300 benchmark is marked in CNY too.
    from portfolio import fx
    held = list((paper_account._load_account(PORTFOLIO_ID).get("positions") or {}).keys())
    held_set = set(held)
    target = {h["ticker"]: float(h.get("weight") or 0.0)
              for h in (submission.get("holdings") if decided else [])}
    prices: dict[str, float] = {}
    _warm_live(set(target) | set(held))
    for t in set(target) | set(held) | {BENCHMARK}:
        base = fx.usd_to(paper_account._current_price(t), CURRENCY)
        if base and base > 0:
            prices[t] = base

    # 4. EXECUTE — market-hours-aware (A-share session). OPEN → rebalance to the target at the live
    #    CNY mark; CLOSED (the normal post-close run, or any off-hours run) → QUEUE the target to
    #    settle at the next A-share open, booking NO fills now — so the book never trades off-hours
    #    and re-running a closed session can't churn it (bot/settle.py + the scheduler's open settle).
    #    A missing second quote cannot erase an existing holding, but it also cannot leave a latent
    #    BUY in the queue: unpriceable held rows flow through unchanged; unpriceable new rows do not.
    from bot import settle as _settle
    executed: list[dict] = []
    skipped: list[str] = []
    queued = False
    execution_quote_blocked = False
    settlement_receipt_id: str | None = None
    outstanding_settlement_receipt_id: str | None = None
    settlement_projection_block: str | None = None
    queued_decision_projected = False
    if decided:
        carried_unpriceable = sorted(
            t for t in target if t in held_set and t not in prices
        )
        execution_target = {
            t: weight for t, weight in target.items()
            if t in prices or t in held_set
        }
        skipped = sorted(
            t for t in target if t not in prices and t not in held_set
        )
        if carried_unpriceable:
            out["carried_unpriceable_holdings"] = carried_unpriceable
        res = _settle.execute_or_queue(
            PORTFOLIO_ID,
            execution_target,
            prices,
            asof,
            decision_snapshot=submission,
            queued_projection_locked=lambda accepted_target: _append_decision_log(
                asof,
                submission,
                [],
                skipped,
                brain,
                feed_health=out.get("feed_health"),
                packet_id=(_pgr.packet_id if _pgr else None),
                target_status="queued",
                effective_target=accepted_target,
                _locked=True,
            ),
        )
        executed = res.get("executed") or []
        queued = bool(res.get("queued"))
        accepted_target = res.get("accepted_target")
        settlement_receipt_id = res.get("settlement_receipt_id")
        outstanding_settlement_receipt_id = res.get(
            "outstanding_settlement_receipt_id"
        )
        settlement_projection_block = _settle.settlement_projection_block_reason(res)
        queued_decision_projected = bool(res.get("queued_projection_written"))
        if settlement_projection_block:
            out["settlement_state_blocked"] = True
            out["settlement_state_block_reason"] = settlement_projection_block
        if res.get("settlement_receipt_error"):
            out["settlement_receipt_error"] = res["settlement_receipt_error"]
        if res.get("receipt_retained") is True and not outstanding_settlement_receipt_id:
            out["settlement_receipt_retained"] = True
        if outstanding_settlement_receipt_id:
            out["outstanding_settlement_receipt_id"] = (
                outstanding_settlement_receipt_id
            )
        if res.get("error"):
            out["rebalance_error"] = res["error"]
        if res.get("skipped"):
            out["execution_skipped"] = res["skipped"]
        if res.get("unpriceable_exits"):
            out["unpriceable_exits"] = res["unpriceable_exits"]
        if res.get("unpriceable_targets"):
            out["unpriceable_targets"] = res["unpriceable_targets"]
        if res.get("skipped") in {
            "unpriceable_exit_prices", "unpriceable_target_prices"
        }:
            execution_quote_blocked = True
            out["pending_target_retained"] = bool(res.get("pending_retained"))
        if settlement_projection_block:
            target_status = (
                f"rejected_{res.get('skipped') or settlement_projection_block}"
            )
        elif queued:
            target_status = "queued"
            effective_target = dict(accepted_target or execution_target)
        elif res.get("error"):
            target_status = "rejected_execution_error"
        elif res.get("skipped"):
            target_status = f"rejected_{res['skipped']}"
        else:
            target_status = "executed"
            effective_target = dict(accepted_target or execution_target)
    lesson_application: dict | None = None
    if target_status in {"executed", "queued"}:
        try:
            from brain import portfolio_learning
            lesson_application = portfolio_learning.record_application(
                PORTFOLIO_ID,
                asof,
                submission,
                effective_target,
                target_status=target_status,
                executed_trades=executed,
                settlement_receipt_id=settlement_receipt_id,
            )
        except Exception as exc:  # noqa: BLE001 - observational trace never changes the target
            lesson_application = {
                "ok": False,
                "recorded": False,
                "error": f"application_trace_error:{type(exc).__name__}",
            }
        out["lesson_application"] = lesson_application
        if queued_decision_projected and target_status == "queued":
            try:
                from bot import decision_rows
                out["decision_lesson_links"] = decision_rows.refresh_lesson_links(
                    PORTFOLIO_ID, asof, submission, target_status="queued"
                )
            except Exception as exc:  # noqa: BLE001
                out["decision_lesson_links"] = {
                    "ok": False, "error": repr(exc)[:200]
                }
    out["executed"] = executed
    out["queued_for_open"] = queued
    out["market_open"] = _settle.is_open(PORTFOLIO_ID)
    out["skipped_unpriceable"] = skipped

    # 5. mark NAV vs CSI 300 (benchmark auto-resolved per-book from the registry)
    if settlement_receipt_id:
        out["mark_deferred_to_settlement_receipt"] = True
    elif settlement_projection_block:
        out["mark_skipped"] = settlement_projection_block
    elif execution_quote_blocked:
        # mark() may initialize benchmark fields in account.json. Keep the whole paper account
        # write-free until the retained exit target has a trusted market price.
        out["mark_skipped"] = "execution_quote_guard"
    else:
        try:
            paper_account.mark(prices, asof, portfolio_id=PORTFOLIO_ID)
        except Exception as e:                       # noqa: BLE001
            out["mark_error"] = repr(e)[:200]

    # 6. publish the book contract + 7. append the daily decision log
    out["target_status"] = target_status
    out["decision_effective"] = target_status in {"executed", "queued"}
    publish_ok = False
    if settlement_receipt_id:
        out["publish_deferred_to_settlement_receipt"] = True
    elif settlement_projection_block:
        out["publish_skipped"] = settlement_projection_block
    else:
        payload = _build_payload(
            asof,
            submission,
            prices,
            executed,
            skipped,
            brain,
            feed_health=out.get("feed_health"),
            target_status=target_status,
        )
        try:
            from bridge import build_portfolio
            out["paths"] = build_portfolio.write(payload, portfolio_id=PORTFOLIO_ID)
            publish_ok = True
        except Exception as e:                   # noqa: BLE001
            out["write_error"] = repr(e)[:200]
    decision_log_ok = False
    if queued_decision_projected:
        decision_log_ok = True
    elif settlement_projection_block:
        out["decision_log_skipped"] = settlement_projection_block
    else:
        try:
            _append_decision_log(
                asof,
                submission,
                executed,
                skipped,
                brain,
                feed_health=out.get("feed_health"),
                packet_id=(_pgr.packet_id if _pgr else None),
                target_status=target_status,
                effective_target=effective_target,
            )
            decision_log_ok = True
        except Exception as exc:
            out["decision_log_error"] = repr(exc)[:240]

    if settlement_receipt_id:
        try:
            receipt_finalization = _settle.finalize_direct_settlement_receipt(
                PORTFOLIO_ID, settlement_receipt_id
            )
        except Exception as exc:  # noqa: BLE001 - receipt remains the retry authority
            receipt_finalization = {
                "ok": False,
                "receipt_retained": True,
                "finalization_errors": [repr(exc)[:240]],
            }
        out["settlement_receipt_finalization"] = receipt_finalization
        if receipt_finalization.get("ok") is True:
            out["settlement_receipt_acknowledged"] = bool(
                receipt_finalization.get("receipt_acknowledged")
            )
            out["decision_receipt_reconciliation"] = (
                receipt_finalization.get("decision_reconciliation")
            )
            if "executed" in receipt_finalization:
                out["executed"] = receipt_finalization["executed"]
        else:
            out["settlement_receipt_retained"] = True
    elif outstanding_settlement_receipt_id:
        try:
            outstanding_finalization = _settle.finalize_direct_settlement_receipt(
                PORTFOLIO_ID, outstanding_settlement_receipt_id
            )
        except Exception as exc:  # noqa: BLE001 - receipt remains the retry authority
            outstanding_finalization = {
                "ok": False,
                "receipt_retained": True,
                "finalization_errors": [repr(exc)[:240]],
            }
        out["outstanding_settlement_receipt_finalization"] = outstanding_finalization
        outstanding_acknowledged = bool(
            outstanding_finalization.get("ok") is True
            and outstanding_finalization.get("receipt_acknowledged") is True
        )
        out["outstanding_settlement_receipt_acknowledged"] = outstanding_acknowledged
        out["outstanding_settlement_receipt_retained"] = not outstanding_acknowledged
        out["settlement_receipt_retained"] = not outstanding_acknowledged

    # 8. delegate the Chinese translation of today's report to the Haiku tier so the dashboard
    #    renders zh the moment it's toggled — automatic after every run, never blocks the book.
    if settlement_projection_block:
        out["translation_skipped"] = settlement_projection_block
    else:
        try:
            out["translated"] = _translate_report(submission, brain)
        except Exception:
            out["translated"] = False

    try:
        out["nav"] = round(paper_account.nav(prices, PORTFOLIO_ID), 2)
    except Exception:
        out["nav"] = None
    out["holdings"] = len(target)

    # ── MW5: mandate-compliance packet (ADVISORY ONLY — never gates) ──────
    try:
        from portfolio import mandate_packet as _mp
        _pkt = _mp.build(PORTFOLIO_ID, out)
        out["mandate_packet"] = _pkt
        _mp.write_packet(_pkt, PORTFOLIO_ID)
        _mp.emit_run_event(_pkt, PORTFOLIO_ID, job="china_daily")
    except Exception:  # noqa: BLE001
        pass

    try:
        from brain import portfolio_learning
        post = portfolio_learning.refresh_post_sell(PORTFOLIO_ID, asof)
        lessons = portfolio_learning.derive_lessons(PORTFOLIO_ID)
        out["learning"] = {"post_sell": post.get("summary"),
                           "lessons_n": len(lessons.get("lessons") or [])}
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# the Brain
# ---------------------------------------------------------------------------

_PERSONA = (
    "You are the CHINA A-SHARE PORTFOLIO MANAGER of a real-money-style ¥1,000,000 PAPER book, marked "
    "in CNY (renminbi). You run once per Asia trading day, after the mainland A-share close. You have "
    "accountable discretion over names, ordinal conviction, ADD/HOLD/TRIM/EXIT intent, and risk posture. "
    "The operating doctrine and evidence contract apply; the trusted incremental allocator alone turns "
    "your ordinal decisions into weights and never uses model numbers as authority. It preserves reviewed "
    "holds and omissions, and never invents marginal trades merely to fill gross. \n\n"
    "Capital preservation and positive alpha are co-equal goals. Cash is allowed but is not a rewarded "
    "default: before holding more than 40%, search the corroborated intake and defensive A-share leaders, "
    "then document the rejected opportunities and opportunity cost. Only verified crash conditions or "
    "degraded feeds justify retreating primarily to cash. Preserve the market-specific process that has "
    "worked; do not import US or HK patterns without local evidence. \n\n"
    "Your universe is MAINLAND CHINA A-SHARES ONLY — Shanghai (``*.SS``) and Shenzhen (``*.SZ``) "
    "single-company shares positively verified by the trusted local stock master, quoted in CNY "
    "(e.g. 600519.SS, 300750.SZ, 601318.SS). ETFs, index funds, pooled products, and warrants are "
    "PROHIBITED holdings even when their ticker has an allowed suffix; they may be context only. "
    "You MAY NOT hold Hong Kong "
    "(``*.HK``) names or US-listed ADRs — those belong to the separate HK book, and any non-A-share "
    "ticker you submit will be REJECTED by the desk. A-shares are native CNY; reason about portfolio "
    "impact and conviction, while the trusted layer owns exact CNY-NAV weights. \n\n"
    "You have two research channels and may use EITHER or BOTH: (1) the in-house macro China desks "
    "via mcp__china__* tools — get_china_regime (top-down quad + PBoC liquidity), get_china_intake "
    "(the unified, corroborated A-share candidate funnel across the buy board, alpha leaders, and "
    "reversal watch), get_china_standouts, get_china_brief — and (2) the open web via WebSearch / "
    "WebFetch. Form your own view; you are not obliged to agree with the in-house engine. \n\n"
    "ALWAYS confirm a name is eligible and priceable with mcp__china__get_quote before you rely on "
    "it — it returns trusted identity status, venue, and CNY price; eligible=false or "
    "priceable=false means it cannot enter the book. When you are done researching, call "
    "mcp__china__submit_book ONCE with your COMPLETE target book for today: every A-share you want to "
    "hold, its ADD/HOLD/TRIM intent, ordinal conviction, and a clear one-paragraph rationale for EACH holding. "
    "A TRIM must include evidence and light/standard/deep intensity; the allocator derives the reduction. "
    "Omission never sells: give every intended full exit an explicit exit_decisions record with reason, "
    "evidence and why-now. Submit the structured decision memo and evidence provenance required by the "
    "tool. Let winners run while their local sector, tape and thesis persist; review trim-and-trail before "
    "a full exit. Be decisive and concrete; this book is graded on its realized CNY NAV vs the CSI 300. \n\n"
    "When independent research would benefit, delegate at most three read-only tasks to signal-scout or "
    "narrative-analyst, wait for compact findings, and synthesize the final book yourself. Subagents never "
    "submit or size. Do not expose hidden chain-of-thought; record concise evidence, alternatives and the "
    "decision-relevant conclusion. \n\n"
    "NAMING — in EVERY piece of prose you write (each holding's rationale, the overall summary, the "
    "sold note, and your closing write-up / decision log), refer to a company by its NAME alongside "
    "the ticker, e.g. write '贵州茅台 (600519.SS)', never a bare '600519.SS'. get_my_book, get_quote, "
    "the buy board, and the intake funnel all return the Chinese name for every A-share ticker — use "
    "it. Never leave a stock code unnamed in the decision log."
)


def _run_brain(asof: str, inaugural: bool, directive: str | None = None) -> dict:
    from brain import china_mcp, cli_bridge
    from brain import self_mirror, risk_lens   # lazy (package-attr lesson); both flag-gated, byte-identical OFF
    prompt = _build_prompt(asof, inaugural, directive=directive)
    persona = self_mirror.inject(_PERSONA, "china", _safe_date(asof))
    persona = risk_lens.govern_persona(persona, "china")        # RISK GOVERNOR mandate; OFF → unchanged
    coro = cli_bridge.reason(
        prompt,
        role="deep",                 # opus, per config/agents.yml
        arm=True,
        append_system=persona,
        mcp_servers=china_mcp.build_servers(),
        allowed_tools=china_mcp.allowed_tools(),
        max_turns=_MAX_TURNS,
        book=PORTFOLIO_ID,           # bot records against cost_guard; skip bridge double-count
    )
    return _run_coro(coro)


def _build_prompt(asof: str, inaugural: bool, directive: str | None = None) -> str:
    from portfolio import paper_account
    state = paper_account._load_account(PORTFOLIO_ID)
    cash = float(state.get("cash") or 0.0)
    positions = state.get("positions") or {}
    regime = _regime_brief()

    lines = [f"# China book — daily decision for {asof}", ""]
    if directive:
        lines += ["## ⚠ PRIORITY DIRECTIVE FOR THIS RUN", directive.strip(), ""]
    if regime:
        lines += [f"China macro regime (in-house read): {regime}", ""]
    try:
        from brain import portfolio_learning
        lines += [portfolio_learning.prompt_block(PORTFOLIO_ID, asof=asof), ""]
    except Exception:
        pass
    # E2.5 — POSTURE block (flag-independent read-only prompt enrichment).
    # The China Brain sees the shadow posture so it can observe whether it would have agreed.
    # Missing/absent artifact → section omitted (degrade silently; never blocks the book).
    try:
        from brain import posture_decider as _pd
        _posture_block = _pd.render_directive()
        if _posture_block:
            lines += [_posture_block]
    except Exception:  # noqa: BLE001 — additive; never block the book
        pass
    # RISK GOVERNOR — the live risk-state block that governs sizing/gross (flag-gated; OFF → "").
    from brain import risk_lens
    brief = risk_lens.briefing("china", regime=_regime_dict(), asof=asof, held=sorted(positions))
    if brief:
        lines += [brief, ""]
    if inaugural:
        lines += [
            "This is your INAUGURAL run. The book is 100% cash: ¥1,000,000 (CNY). Build the "
            "A-share portfolio from scratch — select positively verified single-company mainland "
            "stocks (*.SS / *.SZ) you are "
            "convinced of and label each ADD with ordinal conviction. The trusted allocator will size "
            "only those approved names; it will not force weak ideas. No ETFs, funds, indices, "
            "warrants, HK names, or ADRs.",
            "",
        ]
    else:
        lines += [f"Your current book: ¥{cash:,.0f} cash across {len(positions)} holdings "
                  f"({', '.join(sorted(positions)) or 'none'}). Call mcp__china__get_my_book for the "
                  "full picture (weights, live CNY P&L, and the rationale you last gave each name).", ""]
    lines += [
        "Do your research now (the in-house China desks and/or the web — your call), then submit "
        "your complete target book for today via mcp__china__submit_book, with a one-paragraph "
        "rationale per holding, ADD/HOLD/TRIM intent, all governance fields, a structured decision memo, and an explicit record "
        "for every exit. Confirm each name is priceable with get_quote first. Search deeper before choosing "
        "high cash; every holding must be a positively verified single-company stock, never an ETF "
        "or fund. You are accountable for selection and CNY NAV vs the CSI 300, while exact weights "
        "remain deterministic.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# publish + log helpers
# ---------------------------------------------------------------------------

def _build_payload(asof: str, submission: dict | None, prices: dict, executed: list,
                   skipped: list, brain: dict, feed_health: dict | None = None,
                   *, target_status: str = "executed") -> dict:
    from portfolio import china_calendar, paper_account, position_log
    from brain import china_intake, decision_submission
    state = paper_account._load_account(PORTFOLIO_ID)
    pnl = paper_account.positions_pnl(prices, PORTFOLIO_ID)
    nav = paper_account.nav(prices, PORTFOLIO_ID)
    cash = float(state.get("cash") or 0.0)
    rationale_by_tk = {h["ticker"].upper(): h for h in ((submission or {}).get("holdings") or [])}

    positions = []
    for tk, rec in pnl.items():
        mv = rec.get("market_value")
        h = rationale_by_tk.get(tk, {})
        rationale = h.get("rationale")
        entry = position_log.get_entry_info(SLEEVE, tk, portfolio_id=PORTFOLIO_ID)
        positions.append({
            "ticker": tk,
            "name": china_intake.display_name(tk),     # Chinese for A-shares, English for HK/ADR
            "sleeve": SLEEVE,
            "venue": china_intake._venue(tk),
            "weight": round(mv / nav, 4) if (mv and nav) else None,
            "verdict": "hold",
            "conviction": h.get("conviction"),
            "rationale": rationale,
            "opened_at": entry.get("opened_at"),
            "held_days": entry.get("held_days"),
            "cost_basis": rec.get("avg_cost"),
            "current_price": rec.get("current_price"),
            "market_value": mv,
            "unrealized_pnl": rec.get("unrealized_pnl"),
            "unrealized_pct": rec.get("unrealized_pct"),
            "thesis_full": {"summary": rationale, "why_now": rationale, "bull": [], "bear": []}
            if rationale else None,
        })
    positions.sort(key=lambda p: (p.get("weight") or 0.0), reverse=True)

    gross = round(sum((p.get("weight") or 0.0) for p in positions), 4)
    decisions = []
    narrative = decision_submission.effective_narrative_fields(submission, target_status)
    summary = narrative.get("summary")
    if summary:
        decisions.append({"subject": "China book", "lean": summary,
                          "thesis": narrative.get("sold_note") or "",
                          "logged_at": datetime.now(timezone.utc).isoformat()})
    try:
        from brain import portfolio_learning
        lesson_links = portfolio_learning.trace_links(submission, target_status=target_status)
    except Exception:
        lesson_links = {}
    return {
        "as_of": asof,
        "portfolio_id": PORTFOLIO_ID,
        "manager": "Mastermind Portfolio CN Brain (Codex-first)",
        "kind": "china_brain",
        "currency": CURRENCY,
        "benchmark": BENCHMARK,
        "regime": _regime_dict(),
        "gross": gross,
        "cash": round(1.0 - gross, 4) if gross <= 1.0 else 0.0,
        "cash_usd": round(cash, 2),
        "nav": round(nav, 2),
        **narrative,
        "positions": positions,
        "decisions": decisions,
        "executed_today": executed,
        "skipped_unpriceable": skipped,
        "feed_health": feed_health,
        "market_status": china_calendar.status(),
        "brain": {k: brain.get(k) for k in ("cost_usd", "tools_used", "model")},
        **lesson_links,
    }


def _append_decision_log(asof: str, submission: dict | None, executed: list,
                         skipped: list, brain: dict, feed_health: dict | None = None,
                         *, packet_id: str | None = None,
                         target_status: str = "rejected_unspecified",
                         effective_target: dict[str, float] | None = None,
                         _locked: bool = False) -> None:
    from portfolio import registry
    from brain import china_intake as _intake_mod, decision_submission
    p = registry.data_dir(PORTFOLIO_ID) / "decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        from brain import portfolio_learning
        lesson_links = portfolio_learning.trace_links(submission, target_status=target_status)
    except Exception:
        lesson_links = {}
    from bot import decision_rows
    entry = {
        "asof": asof,
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": (submission or {}).get("summary"),
        "sold_note": (submission or {}).get("sold_note"),
        "feed_health": feed_health,
        "holdings": [{**decision_submission.holding_audit_fields(h),
                      "name": _intake_mod.display_name(h.get("ticker"))}
                     for h in ((submission or {}).get("holdings") or [])],
        "executed": [{**e, "name": _intake_mod.display_name(e.get("ticker"))} for e in (executed or [])],
        "skipped_unpriceable": skipped,
        "brain_text": (brain.get("text") or "")[:6000] if isinstance(brain, dict) else None,
        "run_id": brain.get("run_id") if isinstance(brain, dict) else None,
        "tools_used": brain.get("tools_used") if isinstance(brain, dict) else None,
        "cost_usd": brain.get("cost_usd") if isinstance(brain, dict) else None,
        "model": brain.get("model") if isinstance(brain, dict) else None,
        "error": brain.get("error") if isinstance(brain, dict) else None,
        "packet_id": packet_id,
        **decision_submission.target_status_fields(target_status),
        **decision_rows.accepted_identity_fields(
            PORTFOLIO_ID, asof, submission, effective_target, target_status
        ),
        "effective_holdings": decision_submission.effective_holding_audit(
            submission, effective_target, target_status
        ),
        **decision_submission.audit_fields(submission),
        **lesson_links,
    }
    from portfolio import paper_account
    def _persist() -> None:
        existing = decision_rows.read_rows(p)
        # Idempotent per asof — but a FAILED re-run must not erase a good book. See bot/decision_rows.
        rows = decision_rows.replace_for_asof(existing, entry, asof)
        decision_rows.write_rows(p, rows)
    if _locked:
        _persist()
    else:
        with paper_account._paper_transaction_lock(PORTFOLIO_ID):
            _persist()


def _translate_report(submission: dict | None, brain: dict | None) -> bool:
    """Warm the Simplified-Chinese cache for every translatable string in today's report by
    delegating to the Haiku tier (``brain.translate.translate_and_cache`` → role="scout"). Covers
    the overall summary, the sold note, the Brain's closing write-up, and EACH holding's rationale
    — exactly the strings ``/api/decisions`` and the book view re-render in zh via ``cached_zh``.
    Best-effort: returns True if it ran, False on any miss; never raises, never blocks publishing.

    Display NAMES are intentionally NOT translated — A-share names are already Chinese and HK/ADR
    names are English proper nouns that should read the same under either toggle."""
    try:
        from brain import translate
    except Exception:
        return False
    texts: list[str] = []
    sub = submission or {}
    for k in ("summary", "sold_note"):
        v = sub.get(k)
        if v and isinstance(v, str):
            texts.append(v)
    for h in (sub.get("holdings") or []):
        r = h.get("rationale")
        if r and isinstance(r, str):
            texts.append(r)
    bt = (brain or {}).get("text")
    if bt and isinstance(bt, str):
        texts.append(bt[:6000])
    if not texts:
        return False
    try:
        translate.translate_and_cache(texts)
        return True
    except Exception:
        return False


def republish(
    asof: str | None = None,
    *,
    submission: dict | None = None,
    settlement_prices: dict[str, float] | None = None,
) -> dict:
    """Re-emit the CURRENT book's published contract (with display names) + re-warm the zh cache
    from the LAST submission and today's CNY marks — WITHOUT a new Brain call. Use to refresh the
    live book after a code change (e.g. names / translation) or an FX move. Idempotent per asof."""
    from portfolio import fx, paper_account
    from brain import china_mcp
    asof = asof or date.today().isoformat()
    if submission is None:
        submission = china_mcp.read_submission()
    if submission is None or not isinstance(submission.get("holdings"), list):
        return {"ok": False, "error": "no current submission to republish"}
    held = list((paper_account._load_account(PORTFOLIO_ID).get("positions") or {}).keys())
    target = {h["ticker"]: float(h.get("weight") or 0.0) for h in (submission.get("holdings") or [])}
    prices: dict[str, float] = dict(settlement_prices or {})
    if settlement_prices is None:
        _warm_live(set(target) | set(held))
        for t in set(target) | set(held) | {BENCHMARK}:
            base = fx.usd_to(paper_account._current_price(t), CURRENCY)
            if base and base > 0:
                prices[t] = base
    payload = _build_payload(
        asof, submission, prices, [], [], {}, target_status="executed"
    )
    out: dict = {"ok": True, "holdings": len(target)}
    try:
        from bridge import build_portfolio
        build_portfolio.write(payload, portfolio_id=PORTFOLIO_ID)
    except Exception as e:                           # noqa: BLE001
        return {"ok": False, "error": repr(e)[:200]}
    try:
        from brain import portfolio_learning
        out["lesson_application"] = portfolio_learning.settle_application(
            PORTFOLIO_ID, submission, asof
        )
    except Exception as exc:  # noqa: BLE001 - fills/publish remain authoritative
        out["lesson_application"] = {
            "ok": False,
            "transitioned": False,
            "error": f"application_transition_error:{type(exc).__name__}",
        }
    try:
        out["lesson_finalization"] = portfolio_learning.application_finalization_status(
            PORTFOLIO_ID, submission
        )
    except Exception as exc:  # noqa: BLE001 - finalizer must retain the receipt
        out["lesson_finalization"] = {
            "ok": False,
            "required": True,
            "error": f"application_finalization_error:{type(exc).__name__}",
        }
    if not out["lesson_finalization"].get("ok"):
        out["ok"] = False
        out["error"] = "lesson_application_not_durable"
        return out
    # republish has no live Brain object, so recover its closing write-up from the decision log
    # to translate it too (the automated run_china path passes the live brain directly).
    brain = {}
    try:
        decs = load_decisions(1)
        if decs and decs[0].get("brain_text"):
            brain = {"text": decs[0]["brain_text"]}
    except Exception:
        pass
    out["translated"] = _translate_report(submission, brain)
    return out


def load_decisions(limit: int = 60) -> list[dict]:
    """The daily decision log, NEWEST first. Backs /api/decisions?portfolio=china."""
    from portfolio import registry
    p = registry.data_dir(PORTFOLIO_ID) / "decisions.jsonl"
    rows: list[dict] = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)
    return rows[:limit]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _has_history() -> bool:
    from portfolio import registry
    nav_path = registry.data_dir(PORTFOLIO_ID) / "nav_history.jsonl"
    try:
        return nav_path.exists() and bool(nav_path.read_text().strip())
    except Exception:
        return False


def _warm_live(tickers) -> None:
    """Batch-prefetch A-share Yahoo marks in one request.

    Yahoo quotes ``*.SS``/``*.SZ`` in native CNY and is the reachable VPS
    fallback when the Tushare endpoint cannot be routed from this region.
    """
    try:
        from data_layer import yahoo_feed

        yahoo_feed.warm([
            t for t in tickers
            if (t or "").upper().endswith((".SS", ".SZ"))
        ])
    except Exception:
        pass


def _diff_trades(before: dict, after: dict, prices: dict) -> list[dict]:
    trades = []
    for t in sorted(set(before) | set(after)):
        b = float((before.get(t) or {}).get("shares") or 0.0)
        a = float((after.get(t) or {}).get("shares") or 0.0)
        d = a - b
        if abs(d) < 1e-6:
            continue
        px = prices.get(t)
        trades.append({
            "ticker": t,
            "side": "buy" if d > 0 else "sell",
            "shares": round(abs(d), 4),
            "price": round(px, 4) if px else None,
            "value": round(abs(d) * px, 2) if px else None,
        })
    return trades


def _safe_date(asof: str):
    try:
        return date.fromisoformat(asof)
    except Exception:
        return None


def _regime_dict() -> dict:
    # Delegated to the single regime reader (architecture Stage 1, W1).
    # China brain uses lens_row("china") which routes to china_regime/latest.json.
    # lens_row() is golden-output tested to be byte-identical to the old 3-liner.
    from brain.regime_frame import lens_row
    return lens_row("china")


def _regime_brief() -> str:
    raw = _read_china_regime()
    if not raw:
        return ""
    parts = [raw.get("quad_name") or raw.get("quad")]
    if raw.get("liquidity_overlay"):
        parts.append(f"PBoC liquidity {raw['liquidity_overlay']}")
    return ", ".join(p for p in parts if p)


def _read_china_regime() -> dict:
    try:
        p = _ROOT / "vendor" / "macro" / "data" / "china_regime" / "latest.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def _run_coro(coro):
    """Run an async coroutine to completion from a sync context (no running loop expected —
    called from the scheduler thread / a worker thread, never inside the event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


if __name__ == "__main__":
    import sys
    _armed = "--offline" not in sys.argv
    o = run_china(armed=_armed)
    print(f"=== china {o['asof']} (inaugural={o['inaugural']}, trading_day={o['trading_day']}) ===")
    print("brain:", "ok" if o["brain"].get("ok") else o["brain"].get("error", "skipped"),
          "| decided:", o.get("decided"), "| holdings:", o.get("holdings"))
    print("executed:", len(o.get("executed") or []), "trades | skipped:", o.get("skipped_unpriceable"))
    print("nav:", o.get("nav"), "| paths:", (o.get("paths") or {}).get("hub"))
