"""The overnight watch loop — let the Brain books re-decide on the LIVE overnight tape before the open.

A human trader watches the overnight tape (US index futures, the Asia→Europe handoff, vol) and adjusts
their open position as it develops. The Brain books, by contrast, decide ONCE post-close and queue a
target (``bot/settle.py``) that settles at the open. This module lets them KEEP WATCHING: on a
scheduled overnight tick it reads the live tape (``data_layer.overnight``); if the tape is MATERIAL —
a deterministic tripwire (overnight risk elevated/stressed; free, no LLM) — it re-prompts the book's
Brain (Opus) with an overnight directive built from the tape, which REVISES the queued target. The
revised target then settles at the open via the existing queue→settle machinery.

Cheap by construction: the deterministic tripwire gates the Opus call, so the Brain fires only on a
material overnight move (~a couple nights a week), never on a calm tape. Never raises into the scheduler.
"""
from __future__ import annotations

import importlib
from datetime import date

import bot  # noqa: F401  -> vendor/macro onto sys.path

# pid → (module, daily-entrypoint) — each accepts a `directive=` (the ad-hoc overnight instruction)
_RUNNERS = {
    "autonomous": ("bot.autonomous", "run_autonomous"),
    "china": ("bot.china", "run_china"),
    "hk": ("bot.hk", "run_hk"),
}


_REFINED_FIELDS = (
    "decided", "queued_for_open", "holdings", "brain", "run_id", "fabric_held",
    "target_status", "decision_effective", "skipped", "error", "cost_capped",
    "publish_error", "write_error", "decision_log_error", "mark_error",
    "settlement_receipt_finalization", "settlement_receipt_retained",
)


def _watch_kwargs(handle, pid: str) -> dict:
    from brain import fabric_portfolio, runlog
    kwargs = fabric_portfolio.caller_kwargs(handle, book=pid)
    if "run_id" in kwargs:
        # One existing watch job covers two books; their original operations are distinct.
        kwargs["run_id"] = runlog.portfolio_id(kwargs["run_id"] + ":" + pid)
    return kwargs


def _overnight_directive(pid: str, t: dict) -> str:
    """Build the Brain's overnight reconsideration prompt from the live tape."""
    groups = t.get("groups") or {}
    risk = t.get("risk") or {}

    def _fmt(g):
        return ", ".join(f"{r['name']} {r['change_pct']:+.2f}%"
                         for r in groups.get(g, []) if r.get("change_pct") is not None) or "n/a"

    # MACRO RISK OFFICER brief (best-effort) — the top-down DEFENSE read + driver-aware defensive tilt,
    # so the Brain's overnight reconsideration knows the risk state, the hard gross cap, and WHERE
    # defense lives for the driver that's cracking. Degrades silently if the seat is unavailable.
    macro_line = ""
    try:
        from brain import macro_risk
        from portfolio import defensive_playbook
        rs = macro_risk.risk_state(date.today().isoformat(), None)
        if rs.get("state") != "risk_on":
            macro_line = (f" MACRO RISK OFFICER: state {str(rs.get('state')).upper()} "
                          f"(fragility {rs.get('fragility')}); hard gross cap {rs.get('gross_cap')} "
                          f"(adds {'BLOCKED' if rs.get('allow_adds') is False else 'allowed'}). "
                          + defensive_playbook.brief(rs.get('defensive_tilt')) + " ")
    except Exception:  # noqa: BLE001
        macro_line = ""

    return (
        "OVERNIGHT REVIEW — the LIVE overnight tape has moved materially since you last decided, and the "
        f"in-house dashboard is STALE and can't see it. Live tape now — risk_state {risk.get('state')}: "
        f"US index futures [{_fmt('us_futures')}]; international [{_fmt('international')}]; "
        f"vol [{_fmt('vol')}]; FX/rates [{_fmt('fx_rates')}].{macro_line}"
        "You currently have a target QUEUED to settle at the next open. Review your current book (get_my_book) "
        "and this live tape (US books can also call get_overnight_tape for the full picture), then reconsider "
        "that queued target with fresh eyes: HOLD it as-is, or REVISE it — de-risk toward cash / safer assets "
        "if the overnight tape is selling off, or lean back in if it has stabilized. Respect the macro gross "
        "cap and the defensive tilt above if present. Submit your updated book via submit_book; it settles at "
        "the OPEN, not now. Cite what the live overnight tape is actually doing."
    )


def watch(pid: str, asof: str | None = None, *, force: bool = False,
          run_id: str | None = None, before_provider_start=None) -> dict:
    """One overnight watch tick for book `pid`. No-op (and free) unless the market is CLOSED, a target
    is QUEUED, and the live tape is MATERIAL — only then does it fire the Opus re-decision that revises
    the queued target. Never raises. `force` bypasses the tripwire (manual re-prompt)."""
    from portfolio import registry
    asof = asof or date.today().isoformat()
    out: dict = {"pid": pid, "asof": asof}
    try:
        if registry.is_archived(pid):
            return {**out, "skipped": "portfolio_archived",
                    "superseded_by": registry.get(pid).get("superseded_by")}
        mod_name, fn_name = _RUNNERS.get(pid, (None, None))
        if not mod_name:
            return {**out, "skipped": "unknown_book"}
        kwargs = {}
        if run_id is not None:
            kwargs["run_id"] = run_id
        if before_provider_start is not None:
            kwargs["before_provider_start"] = before_provider_start
        from brain import runlog
        if runlog.portfolio_lookup(run_id, book=pid) is not None:
            # Recover the same original before tripwire, de-risk, or queue mutations.
            fn = getattr(importlib.import_module(mod_name), fn_name)
            res = fn(asof=asof, **kwargs) or {}
            out["refined"] = {key: res.get(key) for key in _REFINED_FIELDS}
            return out
        if pid == "autonomous":
            from portfolio import autonomous_migration
            if autonomous_migration.is_pending_migration():
                return {
                    **out,
                    "skipped": "legacy_etf_migration_pending",
                    "queued_for_open": True,
                    "paper_only": True,
                }
        from bot import settle
        from data_layer import overnight
        from portfolio import paper_account
        if settle.is_open(pid):
            return {**out, "skipped": "market_open"}        # in-session: the normal daily run handles it
        preflight = paper_account.preflight_pending_target(pid)
        if not preflight["ok"]:
            return {
                **out,
                "skipped": preflight["skipped"],
                "quarantined": True,
                "quarantine": preflight["quarantine"],
            }
        if not preflight["pending"]:
            return {**out, "skipped": "nothing_queued"}     # no queued decision to refine
        # FAST DE-RISK (deterministic, free, no LLM) — on a CONFIRMED unwind, revise the queued target
        # down to the gross cap + away from the cracking chains BEFORE the Opus refine, so the book
        # de-risks even if the model is down. Flag-gated (MASTERMIND_FAST_DERISK); no-op otherwise.
        try:
            from bot import derisk
            if derisk.enabled():
                out["derisk"] = derisk.derisk_brain(pid, asof)
        except Exception:  # noqa: BLE001 — additive; the deterministic de-risk never blocks the watch
            pass
        t = overnight.tape(force=force)
        out["overnight_risk"] = (t.get("risk") or {}).get("state")
        out["tape_brief"] = overnight.brief(t)
        if not (force or overnight.is_material(t)):
            return {**out, "skipped": "tape_calm"}          # deterministic tripwire → free, no LLM
        # MATERIAL overnight move → re-prompt the Brain (Opus) to refine the queued target
        fn = getattr(importlib.import_module(mod_name), fn_name)
        res = fn(asof=asof, directive=_overnight_directive(pid, t), **kwargs) or {}
        out["refined"] = {key: res.get(key) for key in _REFINED_FIELDS}
        return out
    except Exception as e:                                   # noqa: BLE001 — a watch miss must never kill the scheduler
        return {**out, "error": repr(e)[:200]}


def watch_us(asof: str | None = None, *, handle=None) -> dict:
    """Overnight watch tick for the one active US Brain (scheduler job)."""
    return {"autonomous": watch("autonomous", asof, **_watch_kwargs(handle, "autonomous"))}


def watch_asia(asof: str | None = None, *, handle=None) -> dict:
    """Overnight watch tick for the Greater-China Brain books (scheduler job)."""
    return {pid: watch(pid, asof, **_watch_kwargs(handle, pid)) for pid in ("china", "hk")}
