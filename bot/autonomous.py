"""US Brain v2 — the sole active US stock-alpha paper portfolio.

Once per trading day (after the close), the Brain:
  1. sees its current book (cash, holdings, live P&L) + the macro regime,
  2. researches freely — our macro-dashboard data tools OR web search, its choice,
  3. submits an explicit, auditable target book with one rationale per holding and explicit exits,
  4. and the deterministic layer rebalances the paper account to those weights at the latest
     close, marks NAV vs SPY, and logs the day's decision with the per-name rationale.

Prophet, Sector Central, Neural Web, Golden Oracle, Terminal technicals, and the wider Macro
stack are research/context planes rather than automatic buy authority. The Brain selects and
ranks common stocks; a deterministic allocator owns weights, and deterministic firebreaks own
paper execution. Silence is not a sell instruction, ETFs are rejected, and very early reversals
require a hard reason. Everything is scoped to portfolio_id="autonomous" so archived books are
never touched.

Run:  python -m bot.autonomous        (or the APScheduler 'autonomous_daily' job, or
                                        POST /api/autonomous/run)
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import bot  # noqa: F401  -> vendor/macro onto sys.path

PORTFOLIO_ID = "autonomous"
SLEEVE = "brain"
_ROOT = Path(__file__).resolve().parent.parent
_MAX_TURNS = int(os.environ.get("AUTONOMOUS_MAX_TURNS", "30"))
_ADVISOR_PROPOSAL_LIMIT = 24


def _firm_clamp_freeze_autonomous(priceable: dict[str, float], exc: Exception) -> dict[str, float]:
    """Exception-arm for the autonomous firm-clamp block (Charter P2).

    Called when ``firm_exposure.clamp_book`` raises inside ``run_autonomous``.  Returns
    ``priceable`` frozen to the prior published state: no new adds, no weight increases.

    Prior weights come from ``firm_exposure.published_weights(PORTFOLIO_ID)`` (the
    last-published latest.json, which carries explicit per-ticker weights).

    Downstream: ``execute_or_queue`` / ``rebalance`` treats absent names as liquidate-to-zero,
    so prior-only names are RETAINED in the output at prior weight (freeze = do-not-trade).

    Never raises.
    """
    from portfolio.freeze import freeze_to_prior as _ftp
    prior: dict[str, float] = {}
    try:
        from portfolio import firm_exposure as _fe
        prior = _fe.published_weights(PORTFOLIO_ID)
    except Exception:  # noqa: BLE001
        pass
    try:
        frozen = _ftp(priceable, prior)
    except Exception:  # noqa: BLE001
        frozen = {k: v for k, v in priceable.items() if k in prior}
    try:
        from control_plane.guardrail import GuardrailResult, Severity
        GuardrailResult.failed(
            "firm_clamp",
            Severity.FREEZE,
            detail=f"clamp_book raised: {exc!r}"[:200],
            action_taken="frozen to prior book (no new adds, no weight increases)",
        ).log(job="autonomous_build", book=PORTFOLIO_ID)
    except Exception:  # noqa: BLE001
        pass
    return frozen


# ---------------------------------------------------------------------------
# the daily entrypoint
# ---------------------------------------------------------------------------

def run_autonomous(asof: str | None = None, *, force: bool = False, armed: bool = True,
                   directive: str | None = None) -> dict:
    """Run one autonomous turn end-to-end. Best-effort: every step degrades gracefully so a
    missing credential / price never leaves the book in a half-traded state."""
    from portfolio import market_calendar, paper_account, registry

    asof = asof or date.today().isoformat()
    out: dict = {"portfolio_id": PORTFOLIO_ID, "asof": asof,
                 "ran_at": datetime.now(timezone.utc).isoformat()}
    # An operator-authorized legacy-ETF migration is an exact executable
    # instruction, not yesterday's ordinary PM queue.  Do not let a nightly
    # model turn clear or supersede it before the open settlement consumes it.
    try:
        from portfolio import autonomous_migration
        if autonomous_migration.is_pending_migration():
            return {
                **out,
                "skipped": "legacy_etf_migration_pending",
                "decided": False,
                "queued_for_open": True,
                "paper_only": True,
            }
    except Exception as exc:  # noqa: BLE001 - an unreadable fence fails closed
        return {
            **out,
            "skipped": "legacy_etf_migration_fence_unavailable",
            "error": repr(exc)[:200],
            "decided": False,
        }
    today = _safe_date(asof)
    out["trading_day"] = market_calendar.is_trading_day(today) if today else None

    state0 = paper_account._load_account(PORTFOLIO_ID)
    inaugural = not _has_history() and not (state0.get("positions") or {})
    out["inaugural"] = inaugural

    # 0. NIGHTLY COST TRIPWIRE (before the Brain). The armed Opus seat below is the dominant
    #    cost (~$1+). If this book has already hit the configured per-night USD cap, SKIP the seat
    #    and carry the book unchanged — same shape as the feed-health abort. OFF by default (cap
    #    <= 0 → over_budget always False) so this is a no-op and the run is byte-identical.
    from brain import cost_guard
    if armed and cost_guard.over_budget(PORTFOLIO_ID, asof):
        print(f"autonomous turn {asof} — nightly cost cap hit "
              f"(${cost_guard.spent(PORTFOLIO_ID, asof):.2f} / ${cost_guard.cap():.2f}); "
              "skipping the Brain and carrying the book unchanged.")
        armed = False
        out["cost_capped"] = True

    # Snapshot only the proposals this PM turn is allowed to review. New proposals that arrive
    # while the Brain is running remain pending for the next cycle instead of being silently
    # marked not-selected without ever appearing in its context.
    advisor_proposal_ids: list[str] = []
    if armed:
        try:
            from portfolio import advisor_trade
            pending = advisor_trade.pending_proposals(limit=_ADVISOR_PROPOSAL_LIMIT)
            advisor_proposal_ids = [row["id"] for row in pending]
            out["advisor_proposals_presented"] = len(advisor_proposal_ids)
        except Exception as exc:  # noqa: BLE001 - optional context must never block the nightly PM
            out["advisor_proposal_context_error"] = repr(exc)[:200]

    # 1. run the Brain (armed) → it researches and submits a target book with rationales
    from brain import autonomous_mcp
    autonomous_mcp.clear_submission(PORTFOLIO_ID)   # never replay yesterday's decision
    brain: dict = {"ok": False, "skipped": not armed}
    if armed:
        try:
            # directive is an optional ad-hoc override (overnight reviews) — pass it through only when set
            brain = _run_brain(asof, inaugural, directive=directive) if directive else _run_brain(asof, inaugural)
        except Exception as e:                       # noqa: BLE001
            brain = {"ok": False, "error": repr(e)[:300]}
        # record this seat's known cost + token usage against the nightly per-book ledger.
        _usg = brain.get("usage") or {}
        cost_guard.record(
            PORTFOLIO_ID, brain.get("cost_usd"), asof,
            seat="autonomous_brain",
            model=str(brain.get("model") or ""),
            input_tokens=int(_usg.get("input_tokens") or 0),
            output_tokens=int(_usg.get("output_tokens") or 0),
            cache_read_tokens=int(_usg.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(_usg.get("cache_creation_input_tokens") or 0),
        )
    out["brain"] = {k: brain.get(k) for k in ("ok", "cost_usd", "tools_used", "error", "run_id", "model")}

    # 2. read the submitted book
    submission = autonomous_mcp.read_submission(PORTFOLIO_ID)
    # An all-cash target can be a valid explicit decision (for example, every current name has
    # a reviewed hard exit). Presence of the v2 holdings list—not its truthiness—is the decision
    # boundary; ``None`` still means the manager failed to submit and the prior book is carried.
    decided = bool(submission and isinstance(submission.get("holdings"), list))
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
        except Exception as exc:  # noqa: BLE001 - citations fail closed; no trace can grant authority
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
        # Average cost proves the account still owns the line, but it is not a safe
        # execution mark. Preserve the whole account until every held line is quoted.
        decided = False
        out["decided"] = False
        out["decision_boundary_frozen"] = {
            "reason": "held_position_quote_fallback",
            "tickers": quote_fallbacks,
        }
        target_status = "frozen_held_quote_fallback"

    # 2b. PACKET GATE (ruling R6, Charter P2/P3/P8) — wire the DecisionPacket boundary.
    # Gate mode is controlled by MASTERMIND_PACKET_GATE (off | shadow[default] | enforce).
    # Shadow: build+validate+ledger but never reject; enforce: reject invalid → carry-forward.
    # The fallback on rejection is IDENTICAL to the Brain-errored path (decided=False → no
    # trade, book unchanged) so a rejection can never increase exposure vs the error path (P2).
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
                    # Mandate, falsifiers, and expected_failure_mode come from the Brain's
                    # submission narrative fields (shadow-mode accrual — Brains are prompted to
                    # supply these via tool description enrichment below; sentinel in v1 is OK
                    # for mandate/liquidity_notes but NOT for falsifiers once enforce is on).
                    "mandate":               (submission.get("mandate") or
                                              "Manage the autonomous paper book with full discretion."),
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
                # ENFORCE mode + invalid packet → fall back to no-proposal path (P2: no new risk)
                decided = False
                out["decided"] = decided
                out["packet_rejected"] = True
                target_status = "rejected_packet_gate"
        except Exception as _pg_exc:   # noqa: BLE001 — gate must never block the book
            out["packet_gate_error"] = repr(_pg_exc)[:200]

    # 3. price the universe we might trade (targets ∪ held ∪ SPY benchmark)
    held = list((paper_account._load_account(PORTFOLIO_ID).get("positions") or {}).keys())
    held_set = set(held)
    target = {h["ticker"]: float(h.get("weight") or 0.0)
              for h in (submission.get("holdings") if decided else [])}
    prices: dict[str, float] = {}
    for t in set(target) | set(held) | {"SPY"}:
        px = paper_account._current_price(t)
        if px and px > 0:
            prices[t] = px

    # 4. EXECUTE — market-hours-aware, with the safety de-gross firebreak applied to the target.
    #    First the ONE risk firebreak over the free-form Brain: a SUBTRACT-ONLY safety de-gross — if
    #    the Brain's target book measures fragile (deep drawdown / high beta / one-factor
    #    concentration / low score), scale it down and let the freed weight stay cash. Never levers
    #    up, never changes which names — risk control, not a second opinion on selection.
    #    Then route the (possibly de-grossed) target through the market-hours-aware settle: OPEN →
    #    rebalance to the target at the live mark; CLOSED (the normal post-close run, or any off-hours
    #    run) → QUEUE the target to settle at the next open, booking NO fills now. So the book never
    #    trades off-hours and re-running a closed session can't churn it (bot/settle.py + the
    #    scheduler's open settle). Unpriceable names are skipped (and surfaced honestly).
    from bot import settle as _settle
    executed: list[dict] = []
    skipped: list[str] = []
    queued = False
    _safety = None
    _safety_overlay = {"gross_mult": 1.0}
    _execution_quote_blocked = False
    _settlement_receipt_id: str | None = None
    _outstanding_settlement_receipt_id: str | None = None
    _settlement_projection_block: str | None = None
    _queued_decision_projected = False
    if decided:
        # A second quote read can transiently miss even though the trusted submission normalized a
        # held line moments earlier.  Never turn that miss into target omission: retain held rows so
        # a closed-market queue still carries them into the next open.  Only genuinely new,
        # unpriceable additions are skipped.
        carried_unpriceable = sorted(t for t in target if t in held_set and t not in prices)
        priceable = {
            t: w for t, w in target.items()
            if t in prices or t in held_set
        }
        skipped = sorted(t for t in target if t not in prices and t not in held_set)
        if carried_unpriceable:
            out["carried_unpriceable_holdings"] = carried_unpriceable
        try:
            from portfolio import safety as _safety_mod
            if priceable:
                _inv = round(sum(priceable.values()), 4)
                _safety = _safety_mod.compute_safety(
                    PORTFOLIO_ID, asof=asof, weights=priceable,
                    cash_weight=round(max(0.0, 1.0 - _inv), 4), bootstrap=True, network=False)
                _safety_overlay = _safety_mod.gross_overlay(_safety)
                _gm = float(_safety_overlay.get("gross_mult", 1.0))
                if _gm < 1.0:
                    priceable = {t: round(w * _gm, 4) for t, w in priceable.items()}
                _safety["overlay"] = {**_safety_overlay, "applied": _gm < 1.0}
                try:
                    _safety_mod.persist(_safety, PORTFOLIO_ID)
                except Exception:
                    pass
        except Exception as e:                           # noqa: BLE001 — never block the book
            out["safety_error"] = repr(e)[:200]
        # W3 B1 — FIRM-WIDE headroom clamp (Stage 6.3). Clamp this book's target DOWN so the firm-wide
        # cluster/name caps hold across active books. Archived US books are excluded by the
        # registry-aware exposure reader. Runs after safety de-gross and before settle; freed weight
        # stays cash. It is subtract-only and best-effort.
        try:
            from portfolio import firm_exposure as _firm
            if _firm.caps_enabled():
                _fc = _firm.clamp_book(priceable, PORTFOLIO_ID)
                priceable = _fc["positions"]
                if _fc.get("bound"):
                    out["firm_clamp"] = {"book": PORTFOLIO_ID, "freed": _fc["freed"],
                                         "clamped": _fc["clamped"]}
        except Exception as e:                           # noqa: BLE001 — a firm cap must never block the book
            # GuardrailResult.FREEZE: freeze to prior book — no new adds, no weight increases.
            # Uses _firm_clamp_freeze_autonomous (module-level) so the logic is testable.
            priceable = _firm_clamp_freeze_autonomous(priceable, e)
            out["firm_clamp_error"] = repr(e)[:200]
        res = _settle.execute_or_queue(
            PORTFOLIO_ID,
            priceable,
            prices,
            asof,
            decision_snapshot=submission,
            queued_projection_locked=lambda accepted_target: _append_decision_log(
                asof,
                submission,
                [],
                skipped,
                brain,
                packet_id=(_pgr.packet_id if _pgr else None),
                target_status="queued",
                effective_target=accepted_target,
                _locked=True,
            ),
        )
        executed = res.get("executed") or []
        queued = bool(res.get("queued"))
        accepted_target = res.get("accepted_target")
        _settlement_receipt_id = res.get("settlement_receipt_id")
        _outstanding_settlement_receipt_id = res.get(
            "outstanding_settlement_receipt_id"
        )
        _settlement_projection_block = _settle.settlement_projection_block_reason(res)
        _queued_decision_projected = bool(res.get("queued_projection_written"))
        if _settlement_projection_block:
            out["settlement_state_blocked"] = True
            out["settlement_state_block_reason"] = _settlement_projection_block
        if res.get("settlement_receipt_error"):
            out["settlement_receipt_error"] = res["settlement_receipt_error"]
        if res.get("receipt_retained") is True and not _outstanding_settlement_receipt_id:
            out["settlement_receipt_retained"] = True
        if _outstanding_settlement_receipt_id:
            out["outstanding_settlement_receipt_id"] = (
                _outstanding_settlement_receipt_id
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
            _execution_quote_blocked = True
            out["pending_target_retained"] = bool(res.get("pending_retained"))
        if _settlement_projection_block:
            target_status = (
                f"rejected_{res.get('skipped') or _settlement_projection_block}"
            )
        elif queued:
            target_status = "queued"
            effective_target = dict(accepted_target or priceable)
        elif res.get("error"):
            target_status = "rejected_execution_error"
        elif res.get("skipped"):
            target_status = f"rejected_{res['skipped']}"
        else:
            target_status = "executed"
            effective_target = dict(accepted_target or priceable)
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
                settlement_receipt_id=_settlement_receipt_id,
            )
        except Exception as exc:  # noqa: BLE001 - observational trace never changes the target
            lesson_application = {
                "ok": False,
                "recorded": False,
                "error": f"application_trace_error:{type(exc).__name__}",
            }
        out["lesson_application"] = lesson_application
        if _queued_decision_projected and target_status == "queued":
            try:
                from bot import decision_rows
                out["decision_lesson_links"] = decision_rows.refresh_lesson_links(
                    PORTFOLIO_ID, asof, submission, target_status="queued"
                )
            except Exception as exc:  # noqa: BLE001 - keep executable queue and surface audit lag
                out["decision_lesson_links"] = {
                    "ok": False, "error": repr(exc)[:200]
                }

    # A proposal is consumed only after the trusted target has actually been accepted by the
    # paper execution boundary.  A syntactically valid submission can still be frozen by quote
    # recovery, rejected by the packet gate, or fail settlement; those proposals must remain
    # pending so the next PM turn can review them again instead of losing context for a trade that
    # never became an executable target.
    if advisor_proposal_ids and target_status in {"executed", "queued"}:
        try:
            from portfolio import advisor_trade
            out["advisor_proposal_review"] = advisor_trade.review_submitted_book(
                submission,
                asof=asof,
                portfolio_id=PORTFOLIO_ID,
                proposal_ids=advisor_proposal_ids,
            )
        except Exception as exc:  # noqa: BLE001 - proposal review cannot affect the final book
            out["advisor_proposal_review"] = {
                "ok": False,
                "reviewed": 0,
                "error": repr(exc)[:200],
            }
    elif advisor_proposal_ids:
        out["advisor_proposal_review"] = {
            "ok": True,
            "reviewed": 0,
            "deferred": True,
            "reason": f"target_not_accepted:{target_status}",
            "executed": False,
        }
    out["executed"] = executed
    out["queued_for_open"] = queued
    out["market_open"] = _settle.is_open(PORTFOLIO_ID)
    out["skipped_unpriceable"] = skipped

    # 5. mark NAV vs SPY (idempotent per date)
    if _settlement_receipt_id:
        # The shared receipt finalizer marks from immutable settlement evidence.  Do not perform a
        # second scratch-price projection here; the receipt must remain until every projection lands.
        out["mark_deferred_to_settlement_receipt"] = True
    elif _settlement_projection_block:
        # execute_or_queue rejected this run before accepting its target.  The older committed
        # receipt/state is the sole projection authority; never mark from this run's scratch quotes.
        out["mark_skipped"] = _settlement_projection_block
    elif _execution_quote_blocked:
        # Keep the account boundary entirely write-free on an unpriceable intended exit.  A mark can
        # initialize benchmark fields in account.json, so even that benign write waits for retry.
        out["mark_skipped"] = "execution_quote_guard"
    else:
        try:
            paper_account.mark(prices, asof, portfolio_id=PORTFOLIO_ID)
        except Exception as e:                           # noqa: BLE001
            out["mark_error"] = repr(e)[:200]

    # 6. publish the book contract + 7. append the daily decision log
    out["target_status"] = target_status
    out["decision_effective"] = target_status in {"executed", "queued"}
    out["safety_overlay"] = _safety_overlay
    _publish_ok = False
    if _settlement_receipt_id:
        out["publish_deferred_to_settlement_receipt"] = True
    elif _settlement_projection_block:
        out["publish_skipped"] = _settlement_projection_block
    else:
        payload = _build_payload(
            asof,
            submission,
            prices,
            executed,
            skipped,
            brain,
            target_status=target_status,
        )
        payload["safety"] = _safety              # consumed risk backtest (drove the de-gross)
        payload["safety_overlay"] = _safety_overlay
        try:
            from bridge import build_portfolio
            out["paths"] = build_portfolio.write(payload, portfolio_id=PORTFOLIO_ID)
            _publish_ok = True
        except Exception as e:                       # noqa: BLE001
            out["write_error"] = repr(e)[:200]
    _decision_log_ok = False
    if _queued_decision_projected:
        _decision_log_ok = True
    elif _settlement_projection_block:
        out["decision_log_skipped"] = _settlement_projection_block
    else:
        try:
            _append_decision_log(
                asof,
                submission,
                executed,
                skipped,
                brain,
                packet_id=(_pgr.packet_id if _pgr else None),
                target_status=target_status,
                effective_target=effective_target,
            )
            _decision_log_ok = True
        except Exception as exc:
            out["decision_log_error"] = repr(exc)[:240]

    # A direct market-open run uses the same exact-receipt finalizer as scheduler recovery.  This
    # makes position projection (including zero fills), mark, publication + learning, and decision
    # reconciliation hard ACK prerequisites and removes scratch-price/provenance duplication.
    if _settlement_receipt_id:
        try:
            _receipt_finalization = _settle.finalize_direct_settlement_receipt(
                PORTFOLIO_ID, _settlement_receipt_id
            )
        except Exception as exc:  # noqa: BLE001 - receipt remains the retry authority
            _receipt_finalization = {
                "ok": False,
                "receipt_retained": True,
                "finalization_errors": [repr(exc)[:240]],
            }
        out["settlement_receipt_finalization"] = _receipt_finalization
        if _receipt_finalization.get("ok") is True:
            out["settlement_receipt_acknowledged"] = bool(
                _receipt_finalization.get("receipt_acknowledged")
            )
            out["decision_receipt_reconciliation"] = (
                _receipt_finalization.get("decision_reconciliation")
            )
            # Preserve an explicit empty receipt fill-set: zero-fill is settlement truth, not a
            # signal to fall back to a mutable before/after diff from the runner.
            if "executed" in _receipt_finalization:
                out["executed"] = _receipt_finalization["executed"]
        else:
            out["settlement_receipt_retained"] = True
    elif _outstanding_settlement_receipt_id:
        # A previous run committed the numeric transaction but crashed before every durable
        # projection landed.  Finish that exact immutable receipt; this run remains rejected and
        # must not masquerade as the owner of the older fills or decision row.
        try:
            _outstanding_finalization = _settle.finalize_direct_settlement_receipt(
                PORTFOLIO_ID, _outstanding_settlement_receipt_id
            )
        except Exception as exc:  # noqa: BLE001 - receipt remains the retry authority
            _outstanding_finalization = {
                "ok": False,
                "receipt_retained": True,
                "finalization_errors": [repr(exc)[:240]],
            }
        out["outstanding_settlement_receipt_finalization"] = _outstanding_finalization
        _outstanding_acknowledged = bool(
            _outstanding_finalization.get("ok") is True
            and _outstanding_finalization.get("receipt_acknowledged") is True
        )
        out["outstanding_settlement_receipt_acknowledged"] = _outstanding_acknowledged
        out["outstanding_settlement_receipt_retained"] = not _outstanding_acknowledged
        out["settlement_receipt_retained"] = not _outstanding_acknowledged

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
        _mp.emit_run_event(_pkt, PORTFOLIO_ID, job="autonomous_daily")
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
    "You are the accountable PM for US BRAIN v2, the sole active US stock-alpha PAPER portfolio. "
    "The failed Flagship, Heavyweight and ETF boards are archived evidence, not peers to imitate. "
    "Your job is capital preservation AND positive alpha: cash is a deliberate risk position, never "
    "the default reward, and ETFs are prohibited substitutes for stock selection. There are usually "
    "winning stocks even under a weak index; search defensives, rotation beneficiaries and idiosyncratic "
    "leaders before accepting high cash. Only a verified crash or degraded evidence plane justifies a "
    "low-gross posture, and you must state the rejected opportunities and cash opportunity cost.\n\n"
    "Start with your current book, the compact market packet, Prophet board and Sector Central. Prophet "
    "has already filtered useful setups, but it is discovery and plan geometry—not buy authority. Select "
    "among its ideas intelligently, corroborate with sector leadership, fundamentals/narrative, Golden "
    "Oracle and MACD-RSI/Stoch-RSI multi-timeframe timing, and investigate outside Prophet when the "
    "evidence points elsewhere. Do not chase an extended entry. Let winners run while their sector, "
    "trend and thesis remain intact; prefer trim-and-trail to reflexive full exits.\n\n"
    "For independent read-heavy work, explicitly delegate at most three bounded tasks: signal-scout for "
    "batch extraction, narrative-analyst for a small finalist set, and quant-coder only for a data-contract "
    "question. Wait for their compact findings and synthesize the final decision yourself. Subagents are "
    "read-only and may never call submit_book or determine size. You alone call submit_book exactly once.\n\n"
    "Every submitted holding row is an explicit ADD, HOLD, or TRIM decision; TRIM needs evidence and an "
    "ordinal intensity, while a full EXIT belongs only in exit_decisions. Omission never sells; provide an explicit exit "
    "record with evidence and why-now. Reversing within three trading sessions requires a hard falsifier, technical "
    "break, risk limit or material thesis change. Your proposed weights are advisory: the deterministic "
    "allocator owns final sizing. Submit a structured decision memo covering funnel, selected/rejected "
    "names, timing, alternatives, risks, context gaps and lessons applied. Do not reveal hidden chain-of-"
    "thought; provide concise decision-relevant evidence and conclusions."
)


def _run_brain(asof: str, inaugural: bool, directive: str | None = None) -> dict:
    from brain import autonomous_mcp, cli_bridge
    from brain import self_mirror, risk_lens, student   # lazy; all flag-gated, byte-identical OFF
    prompt = _build_prompt(asof, inaugural, directive=directive)
    prompt = student.inject(prompt, _safe_date(asof))   # #3 fast numeric prior (MASTERMIND_STUDENT; OFF→unchanged)
    persona = self_mirror.inject(_PERSONA, "autonomous", _safe_date(asof))
    persona = risk_lens.govern_persona(persona, "autonomous")   # RISK GOVERNOR mandate; OFF → unchanged
    coro = cli_bridge.reason(
        prompt,
        role="deep",                 # opus, per config/agents.yml
        arm=True,
        append_system=persona,
        mcp_servers=autonomous_mcp.build_servers(),
        allowed_tools=autonomous_mcp.allowed_tools(),
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

    lines = [f"# US Brain v2 — nightly stock-selection decision for {asof}", ""]
    if directive:
        lines += ["## ⚠ PRIORITY DIRECTIVE FOR THIS RUN", directive.strip(), ""]
    if regime:
        lines += [f"Macro regime (in-house read): {regime}", ""]
    try:
        from portfolio import advisor_trade
        advisor_context = advisor_trade.prompt_context(limit=_ADVISOR_PROPOSAL_LIMIT)
        if advisor_context:
            lines += [advisor_context, ""]
    except Exception:  # noqa: BLE001 - additive advisor context must not block the PM
        advisor_context = ""
    try:
        from brain import portfolio_learning
        lines += [portfolio_learning.prompt_block(PORTFOLIO_ID, asof=asof), ""]
    except Exception:
        pass
    # RISK GOVERNOR — the live risk-state block that governs sizing/gross (flag-gated; OFF → "").
    from brain import risk_lens
    brief = risk_lens.briefing("autonomous", regime=_regime_dict(), asof=asof, held=sorted(positions))
    if brief:
        lines += [brief, ""]
    # E2.5 — POSTURE block (flag-independent read-only prompt enrichment).
    # The autonomous Brain sees the shadow posture so it can observe whether it would have agreed.
    # Missing/absent artifact → section omitted (degrade silently; never blocks the book).
    try:
        from brain import posture_decider as _pd
        _posture_block = _pd.render_directive()
        if _posture_block:
            lines += [_posture_block]
    except Exception:  # noqa: BLE001 — additive; never block the book
        pass
    if inaugural:
        lines += [
            "This is the US v2 launch run. Build a stock-only portfolio from scratch. Call the compact "
            "market, Prophet and sector tools first; do not backfill with ETFs. The deterministic layer "
            "will convert conviction to weights.",
            "",
        ]
    else:
        lines += [f"Your current book: ${cash:,.0f} cash across {len(positions)} holdings "
                  f"({', '.join(sorted(positions)) or 'none'}). Call mcp__desk__get_my_book for the "
                  "full picture (weights, live P&L, and the rationale you last gave each name).", ""]
    lines += [
        "Use the typed in-house packets before the web. Delegate only genuinely independent finalist "
        "research, synthesize it yourself, then call mcp__desk__submit_book exactly once with every "
        "required governance field, ADD/HOLD/TRIM intent for each row, and explicit full exits. You are accountable for decision quality and NAV; "
        "the trusted allocator is accountable for weight and execution.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# publish + log helpers
# ---------------------------------------------------------------------------

def _build_payload(asof: str, submission: dict | None, prices: dict, executed: list,
                   skipped: list, brain: dict, *, target_status: str = "executed") -> dict:
    from portfolio import market_calendar, paper_account, position_log, registry
    from brain import decision_submission
    state = paper_account._load_account(PORTFOLIO_ID)
    pnl = paper_account.positions_pnl(prices, PORTFOLIO_ID)
    nav = paper_account.nav(prices, PORTFOLIO_ID)
    cash = float(state.get("cash") or 0.0)
    rationale_by_tk = {h["ticker"].upper(): h for h in ((submission or {}).get("holdings") or [])}
    migration_exits = {
        str(row.get("ticker") or "").upper().strip(): row
        for row in ((submission or {}).get("exit_decisions") or [])
        if isinstance(row, dict)
        and row.get("reason_code") == "legacy_instrument_migration"
    }

    positions = []
    for tk, rec in pnl.items():
        mv = rec.get("market_value")
        h = rationale_by_tk.get(tk, {})
        migration = migration_exits.get(tk)
        migration_pending = bool(migration) and target_status == "queued"
        rationale = h.get("rationale") or ((migration or {}).get("reason"))
        entry = position_log.get_entry_info(SLEEVE, tk, portfolio_id=PORTFOLIO_ID)
        positions.append({
            "ticker": tk,
            "sleeve": SLEEVE,
            "weight": round(mv / nav, 4) if (mv and nav) else None,
            "verdict": (
                "exit_pending"
                if migration_pending
                else "mandate_violation"
                if migration
                else "hold"
            ),
            "migration_pending": migration_pending,
            "mandate_status": (
                "legacy_etf_exit_queued"
                if migration_pending
                else "legacy_etf_exit_blocked"
                if migration
                else None
            ),
            "conviction": h.get("conviction"),
            "rationale": rationale,
            "opened_at": entry.get("opened_at"),
            "held_days": entry.get("held_days"),
            "cost_basis": rec.get("avg_cost"),
            "current_price": rec.get("current_price"),
            "market_value": mv,
            "unrealized_pnl": rec.get("unrealized_pnl"),
            "unrealized_pct": rec.get("unrealized_pct"),
            # shaped so the dashboard's existing position renderer shows the rationale
            "thesis_full": {"summary": rationale, "why_now": rationale, "bull": [], "bear": []}
            if rationale else None,
        })
    positions.sort(key=lambda p: (p.get("weight") or 0.0), reverse=True)

    gross = round(sum((p.get("weight") or 0.0) for p in positions), 4)
    decisions = []
    narrative = decision_submission.effective_narrative_fields(submission, target_status)
    summary = narrative.get("summary")
    if summary:
        decisions.append({"subject": "Autonomous book", "lean": summary,
                          "thesis": narrative.get("sold_note") or "",
                          "logged_at": datetime.now(timezone.utc).isoformat()})
    try:
        from brain import portfolio_learning
        lesson_links = portfolio_learning.trace_links(submission, target_status=target_status)
    except Exception:
        lesson_links = {}
    payload = {
        "as_of": asof,
        "portfolio_id": PORTFOLIO_ID,
        "manager": "Mastermind Portfolio US Brain (Codex-first)",
        "kind": "us_brain_v2",
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
        "market_status": market_calendar.status(),
        "brain": {k: brain.get(k) for k in ("cost_usd", "tools_used", "model")},
        **lesson_links,
    }
    operator_migration = (
        (submission or {}).get("operator_migration")
        if isinstance(submission, dict)
        else None
    )
    if isinstance(operator_migration, dict):
        actual_legacy_etfs = sorted(
            set(migration_exits) & set(pnl)
        )
        payload["legacy_etf_migration"] = {
            "schema": operator_migration.get("schema"),
            "migration_id": operator_migration.get("migration_id"),
            "paper_only": True,
            "legacy_etfs": operator_migration.get("legacy_etfs") or [],
            "preserved_common_stocks": operator_migration.get(
                "preserved_common_stocks"
            )
            or [],
            "actual_legacy_etfs_remaining": actual_legacy_etfs,
            "status": (
                "pending"
                if target_status == "queued"
                else "settled"
                if target_status == "executed" and not actual_legacy_etfs
                else "blocked"
            ),
            "target_status": target_status,
        }
    return payload


def _append_decision_log(asof: str, submission: dict | None, executed: list,
                         skipped: list, brain: dict,
                         *, packet_id: str | None = None,
                         target_status: str = "rejected_unspecified",
                         effective_target: dict[str, float] | None = None,
                         _locked: bool = False) -> None:
    from portfolio import registry
    from brain import decision_submission
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
        "holdings": [decision_submission.holding_audit_fields(h)
                     for h in ((submission or {}).get("holdings") or [])],
        "executed": executed,
        "skipped_unpriceable": skipped,
        # the Brain's closing reasoning + a pointer to the FULL step-trace (every tool it called +
        # what it pulled + its reasoning steps), retrievable via /api/runlog?run_id=<run_id>.
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
    # idempotent per date: keep exactly one entry per asof (latest SUBSTANTIVE run wins — a
    # failed re-run must not erase a good book; see bot/decision_rows)
    from portfolio import paper_account
    def _persist() -> None:
        existing = decision_rows.read_rows(p)
        rows = decision_rows.replace_for_asof(existing, entry, asof)
        decision_rows.write_rows(p, rows)
    if _locked:
        _persist()
    else:
        with paper_account._paper_transaction_lock(PORTFOLIO_ID):
            _persist()


def load_decisions(limit: int = 60) -> list[dict]:
    """The daily decision log, NEWEST first. Backs /api/decisions."""
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


def republish(
    asof: str | None = None,
    *,
    submission: dict | None = None,
    settlement_prices: dict[str, float] | None = None,
) -> dict:
    """Re-emit the autonomous book's published contract from an accepted submission + current marks —
    no Brain call. Used by the open settle (bot/settle.py) so the dashboard reflects freshly-filled
    positions.  Settlement passes the hash-bound queued snapshot; an explicit ``None`` falls back
    to the current scratch submission only for manual compatibility. Idempotent per asof."""
    from portfolio import paper_account
    asof = asof or date.today().isoformat()
    if submission is None:
        from brain import autonomous_mcp
        submission = autonomous_mcp.read_submission(PORTFOLIO_ID)
    held = list((paper_account._load_account(PORTFOLIO_ID).get("positions") or {}).keys())
    target = {h["ticker"]: float(h.get("weight") or 0.0) for h in ((submission or {}).get("holdings") or [])}
    prices: dict[str, float] = dict(settlement_prices or {})
    if settlement_prices is None:
        for t in set(target) | set(held) | {"SPY"}:
            px = paper_account._current_price(t)
            if px and px > 0:
                prices[t] = px
    payload = _build_payload(
        asof,
        submission,
        prices,
        [],
        [],
        {},
        target_status="executed",
    )
    try:
        from bridge import build_portfolio
        build_portfolio.write(payload, portfolio_id=PORTFOLIO_ID)
        try:
            from brain import portfolio_learning
            lesson_transition = portfolio_learning.settle_application(
                PORTFOLIO_ID, submission, asof
            )
        except Exception as exc:  # noqa: BLE001 - fills/publish remain authoritative
            lesson_transition = {
                "ok": False,
                "transitioned": False,
                "error": f"application_transition_error:{type(exc).__name__}",
            }
        try:
            lesson_finalization = portfolio_learning.application_finalization_status(
                PORTFOLIO_ID, submission
            )
        except Exception as exc:  # noqa: BLE001 - finalizer must retain the receipt
            lesson_finalization = {
                "ok": False,
                "required": True,
                "error": f"application_finalization_error:{type(exc).__name__}",
            }
        if not lesson_finalization.get("ok"):
            return {
                "ok": False,
                "error": "lesson_application_not_durable",
                "holdings": len(target),
                "lesson_application": lesson_transition,
                "lesson_finalization": lesson_finalization,
            }
        return {
            "ok": True,
            "holdings": len(target),
            "lesson_application": lesson_transition,
            "lesson_finalization": lesson_finalization,
        }
    except Exception as e:                               # noqa: BLE001
        return {"ok": False, "error": repr(e)[:200]}


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
    # lens_row() is golden-output tested to be byte-identical to the old 3-liner.
    from brain.regime_frame import lens_row
    return lens_row("us")


def _regime_brief() -> str:
    """The persona's regime line — upgraded from the bare label to the full perception read.

    HOT PATCH (charter P1, 2026-07-02 incident): on 07-02 this brief fed the Brain exactly
    'Goldilocks Q1, liquidity expanding' and it re-risked into semis two days into the breakdown
    while the cycles/radar/confidence planes all disagreed with the label. The Brain must see the
    SAME enriched slice the judgment seats get (pm_conviction._full_regime_slice, W4) — the label
    plus its own uncertainty and the planes that contradict it. Degrades to the old one-liner on
    any failure (P2: missing data coarsens, never inflates).

    E1.1 (W-E.1): now appends the market_view brief + label_vs_planes line from the E0.3 organ
    AFTER the existing W4 frame read.  Compose, don't duplicate: the frame fields above are kept
    as-is; the view block is an ADDITIVE tail section.  Absent view → section omitted (byte-identical
    to current behavior when the organ hasn't been built yet).
    """
    raw = _read_regime()
    if not raw:
        return ""
    label = ", ".join(p for p in (
        raw.get("quad_name") or raw.get("quad"),
        f"liquidity {raw['liquidity_overlay']}" if raw.get("liquidity_overlay") else None) if p)
    try:
        from brain.pm_conviction import _full_regime_slice
        fr = _full_regime_slice(raw)
        lines = [f"REGIME LABEL: {label}"]
        conf = fr.get("confidence")
        if conf is not None:
            lines.append(f"label confidence: {conf} — LOW confidence means the label itself is suspect")
        if fr.get("transition_state"):
            lines.append(f"transition: {fr['transition_state']}")
        contra = fr.get("contradicting") or []
        if contra:
            lines.append(f"legs CONTRADICTING the label: {', '.join(map(str, contra))}")
        cyc = fr.get("cycles") or {}
        if cyc.get("late_cycle"):
            lines.append(f"cycle engine reads LATE-CYCLE (do not add): {', '.join(cyc['late_cycle'])}")
        if cyc.get("entry_favored"):
            lines.append(f"cycle engine favors ENTRY: {', '.join(cyc['entry_favored'])}")
        mrs = fr.get("macro_risk") or {}
        if mrs.get("state"):
            lines.append(f"risk state (dwell): {mrs['state']}, fragility {mrs.get('fragility')}")
        lines.append("Charter P1: never size off the label alone — cite at least one more plane "
                     "(cycles / risk state / contradicting legs) agreeing with any add.")
        # E1.1 — market_view perception layer (ADDITIVE tail; absent view → section omitted).
        # Read the market_view enrichment from _full_regime_slice (it's already computed there);
        # do NOT re-read the artifact (W2: consume once per call chain).
        _mv = fr.get("market_view") or {}
        if _mv.get("label_vs_planes_line"):
            lines.append("")
            lines.append(f"PERCEPTION LAYER (market_view): {_mv['label_vs_planes_line']}")
            _mvb = _mv.get("market_view_brief") or {}
            if _mvb.get("posture_implication"):
                lines.append(f"Posture implication: {_mvb['posture_implication']}")
            if _mvb.get("wheres_the_risk"):
                lines.append(f"Where the risk is: {_mvb['wheres_the_risk']}")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — degrade to the legacy one-liner
        return label


def _read_regime() -> dict:
    try:
        p = _ROOT / "vendor" / "macro" / "data" / "regime" / "latest.json"
        if p.exists():
            return json.loads(p.read_text())
    except Exception:
        pass
    return {}


def _run_coro(coro):
    """Run an async coroutine to completion from a sync context (no running loop expected —
    this is called from the scheduler thread / a worker thread, never inside the event loop)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # a loop is already running in this thread — run the coro on a fresh loop in a worker thread
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


if __name__ == "__main__":
    import sys
    _armed = "--offline" not in sys.argv
    o = run_autonomous(armed=_armed)
    print(f"=== autonomous {o['asof']} (inaugural={o['inaugural']}, trading_day={o['trading_day']}) ===")
    print("brain:", "ok" if o["brain"].get("ok") else o["brain"].get("error", "skipped"),
          "| decided:", o.get("decided"), "| holdings:", o.get("holdings"))
    print("executed:", len(o.get("executed") or []), "trades | skipped:", o.get("skipped_unpriceable"))
    print("nav:", o.get("nav"), "| paths:", (o.get("paths") or {}).get("hub"))
