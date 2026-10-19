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

import hashlib
import importlib
import math
from datetime import date, datetime, timezone

import bot  # noqa: F401  -> vendor/macro onto sys.path

# pid → (module, daily-entrypoint) — each accepts a `directive=` (the ad-hoc overnight instruction)
_RUNNERS = {
    "autonomous": ("bot.autonomous", "run_autonomous"),
    "china": ("bot.china", "run_china"),
    "hk": ("bot.hk", "run_hk"),
}


class OvernightSourceUnavailable(ValueError):
    """No new Brain/model effect is authorized by this ephemeral source."""


class QualifiedOvernightDirective(str):
    """Existing runner's directive plus the private original, bounded source.

    The model receives only the string. The same in-memory carrier holds a
    detached verified observation, its canonical-byte digest and the
    *first-admission* monotonic expiry. It is not a durable grant, queue, or
    second Data OS identity/rights authority.
    """
    def __new__(
        cls, directive: str, observation: dict,
        *, source_deadline: float | None = None,
    ):
        from data_layer import overnight as owner
        if (not isinstance(directive, str)
                or not directive.strip().casefold().startswith("overnight review")):
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence directive format"
            )
        first_wall = datetime.now(timezone.utc)
        first_mono = owner._monotonic_clock()
        private = owner.qualified_live_snapshot(observation)
        if private is None:
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence directive source"
            )
        if source_deadline is None:
            source_deadline = owner._initial_source_deadline(
                private, first_wall, first_mono
            )
        if (type(source_deadline) not in (int, float)
                or not math.isfinite(source_deadline)
                or owner._monotonic_clock() > source_deadline):
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence expired before directive construction"
            )
        encoded = owner._bounded_observation_json(private)
        if encoded is None:
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence cannot be sealed"
            )
        result = str.__new__(cls, directive)
        result._source_observation = private
        result._source_deadline = float(source_deadline)
        result._source_digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        result._source_revoked = False
        return result


def require_overnight_source_at_dispatch(directive: str | None) -> None:
    """Refuse unqualified/expired overnight evidence immediately before a model effect.

    Normal daily prompts are unchanged. A model start still requires the
    existing bridge's own admission and credential permissions; this local
    fence never declares a provider or paper-book modification accepted.
    """
    if type(directive) is QualifiedOvernightDirective:
        from data_layer import overnight as owner
        encoded = owner._bounded_observation_json(directive._source_observation)
        if (encoded is None
                or hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                != directive._source_digest
                or owner._monotonic_clock() > directive._source_deadline
                or owner.qualified_live_snapshot(directive._source_observation)
                is None
                # Host verification itself can consume the last milliseconds
                # of the FIRST monotonic grant. Never extend it by rechecking
                # only the mutable wall clock inside the verifier.
                or owner._monotonic_clock() > directive._source_deadline):
            directive._source_revoked = True
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence revoked before model dispatch"
            )
        return
    if (isinstance(directive, str)
            and directive.strip().casefold().startswith("overnight review")):
        # Rendering strips whitespace. Classification must use the SAME
        # normalized directive, otherwise a leading newline bypasses source
        # verification before becoming a priority instruction in the prompt.
        raise OvernightSourceUnavailable(
            "unqualified overnight evidence without verified source"
        )


def _overnight_directive(
    pid: str, t: dict, *, forced: bool = False,
    source_deadline: float | None = None,
) -> str:
    """Build one truthful directive under its original monotonic source fence."""
    from data_layer import overnight as observed_source
    first_wall = datetime.now(timezone.utc)
    first_mono = observed_source._monotonic_clock()
    admitted = observed_source.qualified_live_snapshot(t)
    if source_deadline is None:
        source_deadline = observed_source._initial_source_deadline(
            admitted, first_wall, first_mono
        )
    if (admitted is None or source_deadline is None
            or observed_source._monotonic_clock() > source_deadline):
        raise OvernightSourceUnavailable(
            "unqualified overnight evidence cannot build a Brain directive"
        )
    # The macro lookup below may yield or take time. Prompt instruments and
    # risk state come from one private detached observation, not a producer
    # dictionary that another actor can change after admission.
    groups = admitted["groups"]
    risk = admitted["risk"]

    def _fmt(group):
        # Display labels must come from the reviewed instrument universe, not
        # untrusted optional provider fields. The qualified risk gate has
        # already checked every value the prompt may display for finiteness.
        labels = dict(observed_source.GROUPS[group])
        return ", ".join(
            f"{labels[row['ticker']]} {float(row['change_pct']):+.2f}%"
            for row in groups.get(group, [])
            if row.get("change_pct") is not None
        ) or "n/a"

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

    # Macro and defensive-playbook lookups above may consume enough time for
    # the original source receipt to expire or be revoked. A standalone
    # directive must not claim LIVE once that authority has changed.
    if (observed_source._monotonic_clock() > source_deadline
            or observed_source.qualified_live_snapshot(admitted) is None
            or observed_source._monotonic_clock() > source_deadline):
        raise OvernightSourceUnavailable(
            "unqualified overnight evidence revoked before directive completion"
        )

    introduction = (
        "OVERNIGHT REVIEW — manually requested reconsideration of a source-qualified LIVE overnight tape; "
        "no materiality threshold was required for this request. "
        if forced else
        "OVERNIGHT REVIEW — source-qualified LIVE overnight tape moved materially by the "
        "current risk tripwire threshold. "
    )
    return (
        introduction
        + f"Current qualified risk_state {risk.get('state')}: "
        f"US index futures [{_fmt('us_futures')}]; international [{_fmt('international')}]; "
        f"vol [{_fmt('vol')}]; FX/rates [{_fmt('fx_rates')}].{macro_line}"
        "You currently have a target QUEUED to settle at the next open. Review your current book (get_my_book) "
        "and this live tape (US books can also call get_overnight_tape for the full picture), then reconsider "
        "that queued target with fresh eyes: HOLD it as-is, or REVISE it — de-risk toward cash / safer assets "
        "if the overnight tape is selling off, or lean back in if it has stabilized. Respect the macro gross "
        "cap and the defensive tilt above if present. Submit your updated book via submit_book; it settles at "
        "the OPEN, not now. Cite what the live overnight tape is actually doing."
    )


def watch(pid: str, asof: str | None = None, *, force: bool = False) -> dict:
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
        # Snapshot the EXACT admitted source before reading its risk or
        # constructing a prompt. Provider-owned mutable dictionaries never
        # become the authoritative reference passed to the model.
        observed = overnight.tape(force=force)
        # Establish an irreversible expiry at FIRST admission. Rechecking a
        # later host verdict may revoke this authority, never extend its
        # original elapsed-time lifetime after a backward wall-clock jump.
        initial_wall = datetime.now(timezone.utc)
        initial_mono = overnight._monotonic_clock()
        t = overnight.qualified_live_snapshot(observed)
        expiry = overnight._initial_source_deadline(
            t, initial_wall, initial_mono
        )
        out["overnight_risk"] = t["risk"]["state"] if t is not None else "unknown"
        out["tape_brief"] = (
            overnight.brief(t) if t is not None
            else "Overnight tape unavailable (historical closes or unqualified evidence are not live risk)."
        )
        if (t is None or expiry is None
                or overnight._monotonic_clock() > expiry):
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence expired before consideration"
            )
        # force bypasses ONLY the risk materiality threshold. Its identity,
        # source rights, original elapsed-time fence and queued-book authority
        # remain mandatory for all autonomous and human-requested reviews.
        if not force:
            # is_material() by itself returns False both for a qualified calm
            # tape AND for a revoked/missing source. Distinguish those cases
            # with one further verified copy of the original observation.
            material_check = overnight.qualified_live_snapshot(t)
            if (material_check is None
                    or overnight._monotonic_clock() > expiry):
                raise OvernightSourceUnavailable(
                    "unqualified overnight evidence revoked during materiality"
                )
            if material_check["risk"]["state"] not in ("elevated", "stressed"):
                return {**out, "skipped": "tape_calm"}
        mod_name, fn_name = _RUNNERS.get(pid, (None, None))
        if not mod_name:
            return {**out, "skipped": "unknown_book"}
        fn = getattr(importlib.import_module(mod_name), fn_name)
        directive = _overnight_directive(
            pid, t, forced=force, source_deadline=expiry
        )
        latest = overnight.qualified_live_snapshot(t)
        if (latest is None or overnight._monotonic_clock() > expiry):
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence revoked before original runner"
            )
        if not force and latest["risk"]["state"] not in ("elevated", "stressed"):
            return {**out, "skipped": "tape_calm"}
        # Carry both the exact original evidence and its first monotonic
        # expiry through the existing source-compatible directive argument.
        bound_directive = QualifiedOvernightDirective(
            directive, latest, source_deadline=expiry
        )
        res = fn(asof=asof, directive=bound_directive) or {}
        if bound_directive._source_revoked:
            # The original runner may catch a pre-provider refusal and return
            # a normal failed Brain record. It cannot make revoked risk look
            # freshly stressed or like an authorized target refinement.
            raise OvernightSourceUnavailable(
                "unqualified overnight evidence revoked inside original runner"
            )
        out["refined"] = {k: res.get(k) for k in ("decided", "queued_for_open", "holdings", "brain")}
        return out
    except OvernightSourceUnavailable:
        # An earlier independent fast-de-risk decision (if present) remains
        # separately attributed; only the unqualified overnight label and
        # new model refinement are disallowed here.
        return {**out, "overnight_risk": "unknown",
                "tape_brief": "Overnight tape unavailable (source expired or authorization revoked).",
                "skipped": "tape_unavailable"}
    except Exception as e:                                   # noqa: BLE001 — a watch miss must never kill the scheduler
        return {**out, "error": repr(e)[:200]}


def watch_us(asof: str | None = None) -> dict:
    """Overnight watch tick for the one active US Brain (scheduler job)."""
    return {"autonomous": watch("autonomous", asof)}


def watch_asia(asof: str | None = None) -> dict:
    """Overnight watch tick for the Greater-China Brain books (scheduler job)."""
    return {pid: watch(pid, asof) for pid in ("china", "hk")}
