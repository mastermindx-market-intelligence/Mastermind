"""The HK portfolio — a free-form Opus Brain managing its own $1M Hong Kong paper book.

The HK sibling of ``bot/china.py``. Once per Asia trading day (after the HK session
closes), the HK Brain:
  1. sees its current book (cash, holdings, live HKD P&L) + the China macro regime,
  2. researches freely — the macro-dashboard HK desks (regime, standouts, intake, brief)
     OR web search, its choice,
  3. submits a COMPLETE target book, one rationale per holding (no gate, no research paper),
  4. and the deterministic layer rebalances the paper account to those weights at the latest
     close, marks NAV in HKD vs the Hang Seng Index, and logs the day.

The universe is HONG KONG listed names only: ``*.HK`` tickers quoted in HKD. The book's
base currency is **HKD**: prices are sourced via Yahoo Finance (``data_layer.yahoo_feed``),
and the NAV stays in HKD throughout — there is NO cross-FX conversion to CNY (unlike the
China book, which converts HKD and USD prices to CNY). Everything is scoped to
portfolio_id="hk" so no other book is touched.

Run:  python -m bot.hk        (or the APScheduler 'hk_daily' job, or POST /api/hk/run)
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

PORTFOLIO_ID = "hk"
SLEEVE = "brain"
_ROOT = Path(__file__).resolve().parent.parent
_MAX_TURNS = int(os.environ.get("HK_MAX_TURNS", "30"))

# Base currency + tradeable venue are registry-driven (portfolio.registry, id="hk").
# The HK book is Hong Kong listings ONLY (*.HK), marked natively in HKD — no cross-FX.
from portfolio import registry as _registry
BENCHMARK = _registry.benchmark(PORTFOLIO_ID)            # Hang Seng Index (^HSI)
CURRENCY = _registry.currency(PORTFOLIO_ID)            # "HKD"
ALLOWED_VENUES = set(_registry.venues(PORTFOLIO_ID))   # {"HK"} — Hong Kong listings only


# ---------------------------------------------------------------------------
# the daily entrypoint
# ---------------------------------------------------------------------------

def run_hk(asof: str | None = None, *, force: bool = False, armed: bool = True,
           directive: str | None = None) -> dict:
    """Run one HK turn end-to-end. Best-effort: every step degrades gracefully so a missing
    credential / price never leaves the book in a half-traded state."""
    from portfolio import china_calendar, paper_account, position_log

    asof = asof or date.today().isoformat()
    out: dict = {"portfolio_id": PORTFOLIO_ID, "asof": asof,
                 "ran_at": datetime.now(timezone.utc).isoformat()}
    today = _safe_date(asof)
    out["trading_day"] = china_calendar.is_trading_day(today, venue="HK") if today else None

    state0 = paper_account._load_account(PORTFOLIO_ID)
    inaugural = not _has_history() and not (state0.get("positions") or {})
    out["inaugural"] = inaugural

    # 0. FEED-HEALTH GATE (before the Brain). The HK live feed (Yahoo) is effectively
    #    all-or-nothing for a basket. When it is DOWN, currently-held names still mark off the
    #    stale vendored snapshot while brand-new candidates return priceable=false — an ASYMMETRIC
    #    map (the China leg hit exactly this on 2026-06-22, parking ~48% cash on a false "no
    #    investable candidates"). Detect the outage and refuse to transact on it: skip the Brain
    #    and carry the book unchanged. `force=True` overrides (operator escape hatch).
    from data_layer import feed_health
    venue = next(iter(ALLOWED_VENUES), "HK")
    out["feed_health"] = feed_health.status(venue, asof)
    if armed and not force and out["feed_health"]["status"] == "down":
        log.warning(
            "HK turn %s ABORTED — the %s live feed is unavailable. Held names would price off the "
            "stale snapshot while fresh candidates return priceable=false (an asymmetric map); "
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
        log.warning("HK turn %s — nightly cost cap hit ($%.2f / $%.2f); skipping the Brain and "
                    "carrying the book unchanged.", asof,
                    cost_guard.spent(PORTFOLIO_ID, asof), cost_guard.cap())
        armed = False
        out["cost_capped"] = True

    # 1. run the Brain (armed) → it researches and submits a target book with rationales
    from brain import hk_mcp as china_mcp
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
            seat="hk_brain",
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
    # An empty holdings list is a valid, explicit 100%-cash target. Distinguish
    # that from no submission at all so a legitimate all-cash decision can be
    # queued/executed and the published target cannot diverge from the account.
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

    # 2b. PACKET GATE (ruling R6, Charter P2/P3/P8)
    _pgr = None
    if decided:
        try:
            from control_plane.packet_gate import process as _packet_process
            _pgr = _packet_process(
                PORTFOLIO_ID, submission, paper_account._load_account(PORTFOLIO_ID),
                extras={
                    "run_id": brain.get("run_id") if isinstance(brain, dict) else "",
                    "asof": asof,
                    "mandate": (submission.get("mandate") or "Manage the HK paper book with full discretion."),
                    "evidence_planes": submission.get("evidence_planes") or [],
                    "source_provenance": submission.get("source_provenance") or [],
                    "falsifiers": submission.get("falsifiers") or [],
                    "liquidity_notes": submission.get("liquidity_notes") or "<not provided>",
                    "expected_failure_mode": submission.get("expected_failure_mode") or "<not provided>",
                },
            )
            out["packet_id"] = _pgr.packet_id
            out["packet_meta"] = _pgr.to_meta()
            if not _pgr.ok:
                decided = False
                out["decided"] = decided
                out["packet_rejected"] = True
                target_status = "rejected_packet_gate"
        except Exception as _pg_exc:
            out["packet_gate_error"] = repr(_pg_exc)[:200]

    # 3. price the universe we might trade (targets ∪ held ∪ benchmark) in the book's HKD base
    #    currency. The shared accessor returns USD-equivalent marks for Hong Kong symbols; convert
    #    them back to HKD so holdings and the Hang Seng benchmark stay on one native-currency basis.
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

    # 4. EXECUTE — market-hours-aware (HK session, on the A-share calendar). OPEN → rebalance to the
    #    target at the live HKD mark; CLOSED (the normal post-close run, or any off-hours run) → QUEUE
    #    the target to settle at the next open, booking NO fills now — so the book never trades
    #    off-hours and re-running a closed session can't churn it (bot/settle.py + the open settle).
    #    A missing second quote cannot erase an existing holding, but it also cannot leave a latent
    #    BUY in the queue: unpriceable held rows flow through unchanged; unpriceable new rows do not.
    from bot import settle as _settle
    executed: list[dict] = []
    skipped: list[str] = []
    queued = False
    execution_quote_blocked = False
    settlement_receipt_id: str | None = None
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
        )
        executed = res.get("executed") or []
        queued = bool(res.get("queued"))
        settlement_receipt_id = res.get("settlement_receipt_id")
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
        if res.get("error"):
            target_status = "rejected_execution_error"
        elif res.get("skipped") and not queued:
            target_status = f"rejected_{res['skipped']}"
        elif queued:
            target_status = "queued"
            effective_target = dict(execution_target)
        else:
            target_status = "executed"
            effective_target = dict(execution_target)
        if executed:
            ledger_positions = [{"ticker": t, "sleeve": SLEEVE, "weight": w, "entry_price": prices.get(t)}
                                for t, w in execution_target.items()]
            try:
                position_log.update(ledger_positions, asof, portfolio_id=PORTFOLIO_ID)
            except Exception:
                pass
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
    out["executed"] = executed
    out["queued_for_open"] = queued
    out["market_open"] = _settle.is_open(PORTFOLIO_ID)
    out["skipped_unpriceable"] = skipped

    # 5. mark NAV vs Hang Seng (benchmark auto-resolved per-book from the registry)
    if execution_quote_blocked:
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
    publish_ok = False
    try:
        from bridge import build_portfolio
        out["paths"] = build_portfolio.write(payload, portfolio_id=PORTFOLIO_ID)
        publish_ok = True
    except Exception as e:                       # noqa: BLE001
        out["write_error"] = repr(e)[:200]
    decision_log_ok = False
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
    except Exception:
        pass
    lesson_receipt_finalization = {"ok": True, "required": False}
    if settlement_receipt_id:
        try:
            from brain import portfolio_learning
            lesson_receipt_finalization = portfolio_learning.application_finalization_status(
                PORTFOLIO_ID,
                submission,
                settlement_receipt_id=settlement_receipt_id,
            )
        except Exception as exc:  # noqa: BLE001 - receipt remains the retry outbox
            lesson_receipt_finalization = {
                "ok": False,
                "required": True,
                "error": f"application_finalization_error:{type(exc).__name__}",
            }
        out["lesson_receipt_finalization"] = lesson_receipt_finalization
        if not lesson_receipt_finalization.get("ok"):
            out["settlement_receipt_retained"] = True
    if (
        settlement_receipt_id
        and publish_ok
        and decision_log_ok
        and not out.get("mark_error")
        and lesson_receipt_finalization.get("ok") is True
    ):
        try:
            paper_account.acknowledge_settlement_receipt(
                settlement_receipt_id, PORTFOLIO_ID
            )
            out["settlement_receipt_acknowledged"] = True
        except Exception as exc:  # noqa: BLE001 - receipt remains available for open-settle retry
            out["settlement_receipt_ack_error"] = repr(exc)[:200]

    # 8. delegate the Chinese translation of today's report to the Haiku tier so the dashboard
    #    renders zh the moment it's toggled — automatic after every run, never blocks the book.
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
        _mp.emit_run_event(_pkt, PORTFOLIO_ID, job="hk_daily")
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
    "You are the HONG KONG PORTFOLIO MANAGER of a real-money-style HK$1,000,000 PAPER book, marked "
    "in HKD (Hong Kong dollars). You run once per Asia trading day, after the HK close. You have "
    "accountable discretion over names, ordinal conviction, ADD/HOLD/TRIM/EXIT intent, and risk posture. "
    "The operating doctrine and evidence contract apply; the trusted incremental allocator alone turns "
    "your ordinal decisions into weights and never uses model numbers as authority. It preserves reviewed "
    "holds and omissions, and never invents marginal trades merely to fill gross. \n\n"
    "Capital preservation and positive alpha are co-equal goals. Cash is allowed but is not a rewarded "
    "default: before holding more than 40%, search the corroborated HK intake and defensive local leaders, "
    "then document rejected opportunities and opportunity cost. Only verified crash conditions or degraded "
    "feeds justify retreating primarily to cash. Preserve HK-specific market structure and do not import "
    "mainland or US patterns without local evidence. \n\n"
    "Your universe is HONG KONG LISTINGS ONLY — names with the ``*.HK`` suffix, quoted in HKD "
    "(e.g. 0700.HK Tencent, 9988.HK Alibaba, 3690.HK Meituan, 0939.HK CCB). You MAY NOT hold "
    "mainland A-shares (``*.SS`` / ``*.SZ``) or US-listed ADRs — those belong to the separate China "
    "book, and any non-HK ticker you submit will be REJECTED by the desk. HK names are native HKD; reason "
    "about portfolio impact and conviction, while the trusted layer owns exact HKD-NAV weights. \n\n"
    "You have two research channels and may use EITHER or BOTH: (1) the in-house macro China desks "
    "via mcp__hk__* tools — get_china_regime (top-down quad + PBoC liquidity), get_china_intake "
    "(the corroborated HK candidate funnel), get_china_standouts (the Hong-Kong buy board), "
    "get_china_brief — and (2) the open web via WebSearch / WebFetch. Form your own view; you are not "
    "obliged to agree with the in-house engine. \n\n"
    "ALWAYS confirm a name is priceable with mcp__hk__get_quote before you rely on it — it "
    "returns the venue, the local-currency price, and the HKD price the book will actually transact "
    "at; a name with priceable=false will be SKIPPED. When you are done researching, call "
    "mcp__hk__submit_book ONCE with your COMPLETE target book for today: every HK name you want to "
    "hold, its ADD/HOLD/TRIM intent, ordinal conviction, and a clear one-paragraph rationale for EACH holding. "
    "A TRIM must include evidence and light/standard/deep intensity; the allocator derives the reduction. "
    "Omission never sells: give every intended full exit an explicit exit_decisions record with reason, "
    "evidence and why-now. Submit the structured decision memo and evidence provenance required by the "
    "tool. Let winners run while their local sector, tape and thesis persist; review trim-and-trail before "
    "a full exit. Be decisive and concrete; this book is graded on HKD NAV vs the Hang Seng Index. \n\n"
    "When independent research would benefit, delegate at most three read-only tasks to signal-scout or "
    "narrative-analyst, wait for compact findings, and synthesize the final book yourself. Subagents never "
    "submit or size. Do not expose hidden chain-of-thought; record concise evidence, alternatives and the "
    "decision-relevant conclusion. \n\n"
    "NAMING — in EVERY piece of prose you write (each holding's rationale, the overall summary, the "
    "sold note, and your closing write-up / decision log), refer to a company by its NAME alongside "
    "the ticker, e.g. write 'Tencent (0700.HK)', never a bare '0700.HK'. get_my_book, get_quote, and "
    "the HK buy board all return the English name for every HK ticker — use it. Never leave a stock "
    "code unnamed in the decision log."
)


def _run_brain(asof: str, inaugural: bool, directive: str | None = None) -> dict:
    from brain import hk_mcp as china_mcp, cli_bridge
    from brain import self_mirror, risk_lens   # lazy (package-attr lesson); both flag-gated, byte-identical OFF
    prompt = _build_prompt(asof, inaugural, directive=directive)
    persona = self_mirror.inject(_PERSONA, "hk", _safe_date(asof))
    persona = risk_lens.govern_persona(persona, "hk")          # RISK GOVERNOR mandate; OFF → unchanged
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

    lines = [f"# HK book — daily decision for {asof}", ""]
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
    # The HK Brain sees the shadow posture so it can observe whether it would have agreed.
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
    brief = risk_lens.briefing("hk", regime=_regime_dict(), asof=asof, held=sorted(positions))
    if brief:
        lines += [brief, ""]
    if inaugural:
        lines += [
            "This is your INAUGURAL run. The book is 100% cash: HK$1,000,000 (HKD). Build the "
            "Hong-Kong portfolio from scratch — buy whatever HK listings (*.HK) you are "
            "convinced of and label each ADD with ordinal conviction. The trusted allocator will size "
            "only those approved names; it will not force weak ideas. No A-share or ADR names.",
            "",
        ]
    else:
        lines += [f"Your current book: HK${cash:,.0f} cash across {len(positions)} holdings "
                  f"({', '.join(sorted(positions)) or 'none'}). Call mcp__hk__get_my_book for the "
                  "full picture (weights, live HKD P&L, and the rationale you last gave each name).", ""]
    lines += [
        "Do your research now (the in-house China desks and/or the web — your call), then submit "
        "your complete target book for today via mcp__hk__submit_book, with a one-paragraph "
        "rationale per holding, ADD/HOLD/TRIM intent, all governance fields, a structured decision memo, and an explicit record "
        "for every exit. Confirm each name is priceable with get_quote first. Search deeper before choosing "
        "high cash; you are accountable for selection and HKD NAV vs the Hang Seng Index, while exact weights remain deterministic.",
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
            "name": china_intake.display_name(tk),
            "name_zh": china_intake.display_name_zh(tk),
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
        "manager": "Mastermind Portfolio HK Brain (Codex-first)",
        "kind": "hk_brain",
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
        "market_status": china_calendar.status(venue="HK"),
        "brain": {k: brain.get(k) for k in ("cost_usd", "tools_used", "model")},
        **lesson_links,
    }


def _append_decision_log(asof: str, submission: dict | None, executed: list,
                         skipped: list, brain: dict, feed_health: dict | None = None,
                         *, packet_id: str | None = None,
                         target_status: str = "rejected_unspecified",
                         effective_target: dict[str, float] | None = None) -> None:
    from portfolio import registry
    from brain import china_intake as _intake_mod, decision_submission
    p = registry.data_dir(PORTFOLIO_ID) / "decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        from brain import portfolio_learning
        lesson_links = portfolio_learning.trace_links(submission, target_status=target_status)
    except Exception:
        lesson_links = {}
    entry = {
        "asof": asof,
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": (submission or {}).get("summary"),
        "sold_note": (submission or {}).get("sold_note"),
        "feed_health": feed_health,
        "holdings": [{**decision_submission.holding_audit_fields(h),
                      "name": _intake_mod.display_name(h.get("ticker")),
                      "name_zh": _intake_mod.display_name_zh(h.get("ticker"))}
                     for h in ((submission or {}).get("holdings") or [])],
        "executed": [{**e, "name": _intake_mod.display_name(e.get("ticker")),
                      "name_zh": _intake_mod.display_name_zh(e.get("ticker"))}
                     for e in (executed or [])],
        "skipped_unpriceable": skipped,
        "brain_text": (brain.get("text") or "")[:6000] if isinstance(brain, dict) else None,
        "run_id": brain.get("run_id") if isinstance(brain, dict) else None,
        "tools_used": brain.get("tools_used") if isinstance(brain, dict) else None,
        "cost_usd": brain.get("cost_usd") if isinstance(brain, dict) else None,
        "model": brain.get("model") if isinstance(brain, dict) else None,
        "error": brain.get("error") if isinstance(brain, dict) else None,
        "packet_id": packet_id,
        **decision_submission.target_status_fields(target_status),
        "effective_holdings": decision_submission.effective_holding_audit(
            submission, effective_target, target_status
        ),
        **decision_submission.audit_fields(submission),
        **lesson_links,
    }
    from bot import decision_rows
    existing = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing.append(json.loads(line))
            except Exception:
                continue
    # Idempotent per asof — but a FAILED re-run must not erase a good book (2026-07-24: the
    # overnight-review job's session-limit stub wiped that day's real HK book). See bot/decision_rows.
    rows = decision_rows.replace_for_asof(existing, entry, asof)
    p.write_text("\n".join(json.dumps(r, default=str, ensure_ascii=False) for r in rows) + "\n")


def _translate_report(submission: dict | None, brain: dict | None) -> bool:
    """Warm the Simplified-Chinese cache for every translatable string in today's report by
    delegating to the Haiku tier (``brain.translate.translate_and_cache`` → role="scout"). Covers
    the overall summary, the sold note, the Brain's closing write-up, and EACH holding's rationale
    — exactly the strings ``/api/decisions`` and the book view re-render in zh via ``cached_zh``.
    Best-effort: returns True if it ran, False on any miss; never raises, never blocks publishing.

    Display names are not machine-translated: HK rows carry the exchange-native
    ``name_zh`` from the bilingual market universe alongside their English name."""
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


def republish(asof: str | None = None, *, submission: dict | None = None) -> dict:
    """Re-emit the CURRENT book's published contract (with display names) + re-warm the zh cache
    from the LAST submission and today's CNY marks — WITHOUT a new Brain call. Use to refresh the
    live book after a code change (e.g. names / translation) or an FX move. Idempotent per asof."""
    from portfolio import fx, paper_account
    from brain import hk_mcp as china_mcp
    asof = asof or date.today().isoformat()
    if submission is None:
        submission = china_mcp.read_submission()
    if submission is None or not isinstance(submission.get("holdings"), list):
        return {"ok": False, "error": "no current submission to republish"}
    held = list((paper_account._load_account(PORTFOLIO_ID).get("positions") or {}).keys())
    target = {h["ticker"]: float(h.get("weight") or 0.0) for h in (submission.get("holdings") or [])}
    prices: dict[str, float] = {}
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
    """Batch-prefetch live HK marks so building the price map is ONE Yahoo request, not one per name
    (Yahoo can throttle rapid single-symbol calls). Best-effort; never raises."""
    try:
        from data_layer import yahoo_feed
        yahoo_feed.warm([t for t in tickers if (t or "").upper().endswith(".HK")])
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
    # HK uses the China regime frame; lens_row("hk") routes to china_regime/latest.json.
    # lens_row() is golden-output tested to be byte-identical to the old 3-liner.
    from brain.regime_frame import lens_row
    return lens_row("hk")


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
    o = run_hk(armed=_armed)
    print(f"=== hk {o['asof']} (inaugural={o['inaugural']}, trading_day={o['trading_day']}) ===")
    print("brain:", "ok" if o["brain"].get("ok") else o["brain"].get("error", "skipped"),
          "| decided:", o.get("decided"), "| holdings:", o.get("holdings"))
    print("executed:", len(o.get("executed") or []), "trades | skipped:", o.get("skipped_unpriceable"))
    print("nav:", o.get("nav"), "| paths:", (o.get("paths") or {}).get("hub"))
