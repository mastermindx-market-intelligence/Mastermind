"""brain/neural_web_context.py — single reader for the Neural Web → Mastermind bridge (W-NW.1).

Reads ONLY vendor/macro/site/neuralwebdata/mastermind_context.json.  Fail-soft everywhere:
absent / malformed / stale / wrong-schema → stable empty context object, never raises.
Never imports Macro engine modules.

PUBLIC API
----------
* context()            — full artifact cached by source identity; {} when absent/stale/invalid.
* candidate(ticker)    — per-ticker advisory context dict; {} when not present.
* market_plane()       — compact dict for the neural_web market_view plane.
* seat_prompt_block(tickers, max_chars=1200) — compact text for prompt injection (NO cortex prose).
* audit_row()          — {status, asof, age_days, n_candidates, gap_notes_count}.
* nw_prompts_enabled() — reads MASTERMIND_NW_CONTEXT; default OFF (text-only prompt injection).
* nw_decision_mode()   — reads MASTERMIND_NW_DECISION; default 'off' (typed decision ladder).
* decision_signals(ticker) — THE typed decision-policy chokepoint; default-OFF inert no-op.
* _reset_context_cache() — explicit cache reset for tests.

FLAGS (independent):
  MASTERMIND_NW_CONTEXT  — default OFF; owns TEXT-ONLY prompt/plane injection.
  MASTERMIND_NW_DECISION — default 'off'; owns the typed decision ladder
                           (off|shadow|candidacy|shrink|vote) — see nw_decision_mode().
Reader + audit rows are flag-independent; prompt injection and decision signals are gated.

STALENESS: as_of age > 4 calendar days → treat as absent-stale.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
# Follow intake._read convention: _V = repo_root / "vendor" / "macro"
_V = _ROOT / "vendor" / "macro"
_ARTIFACT_PATH = _V / "site" / "neuralwebdata" / "mastermind_context.json"

_EXPECTED_SCHEMA = "neural_web_mastermind_context.v1"
_STALE_DAYS = 4   # calendar days

# --------------------------------------------------------------------------- #
# typed decision-policy priors (A5) — ALL UNVERIFIED, tunable module constants
# --------------------------------------------------------------------------- #
# Candidacy scores by NW bottom_state. Unverified priors: leader-anticipation is
# coin-flip per the China-basket program; these are conservative starter weights,
# never authority to size. Only ever *add* a candidate for the gate to filter.
NW_CANDIDACY_SCORES: dict[str, float] = {
    "WATCH": 0.35,          # eyes-only prior — turn not yet confirmed
    "BOTTOMING": 0.50,      # turn in progress
    "CONFIRMED": 0.50,      # confirmed turn — still a starter-grade prior
}
# graph_conflicts count at/above which a NEW entry is shrunk (subtract-only). Unverified.
NW_CONFLICTS_MIN: int = 2
# entry-size multiplier applied when the conflict floor is breached (subtract-only). Unverified.
NW_ENTRY_SHRINK: float = 0.7
# market-plane contradiction_count at/above which the tape is "conflicted", so a
# name with zero graph_conflicts reads as a clean/safe-haven tell. Unverified.
NW_CONTRADICTIONS_MIN: int = 3

# Monotone decision-mode ladder (see nw_decision_mode()). Ordinal only — the values
# are used solely for threshold (>=) comparisons via _mode_ge().
_DECISION_MODE_ORDER: dict[str, int] = {
    "off": 0,
    "shadow": 1,
    "candidacy": 2,
    "shrink": 3,
    "vote": 4,
}
# W8 (2026-07-19, operator-ordered): default 'shrink' — candidacy sourcing (NW may ADD candidates
# for the gate to filter) + subtract-only entry shrink on graph-conflict density. 'vote' stays
# opt-in. Opt out with MASTERMIND_NW_DECISION=off.
_DECISION_MODE_DEFAULT = "shrink"

# --------------------------------------------------------------------------- #
# process-level cache — reset via _reset_context_cache() for tests
# --------------------------------------------------------------------------- #
_CACHE: dict[str, Any] | None = None   # None = not yet loaded; {} = empty/absent
_CACHE_LOADED: bool = False
_CACHE_SIGNATURE: tuple[int, int, int, int] | None = None
_CACHE_LOCK = RLock()


def _reset_context_cache() -> None:
    """Invalidate the per-process cache.  Tests MUST call this around fixtures."""
    global _CACHE, _CACHE_LOADED, _CACHE_SIGNATURE
    with _CACHE_LOCK:
        _CACHE = None
        _CACHE_LOADED = False
        _CACHE_SIGNATURE = None


# --------------------------------------------------------------------------- #
# flag
# --------------------------------------------------------------------------- #

def nw_prompts_enabled() -> bool:
    """Return True iff MASTERMIND_NW_CONTEXT is set to '1' (default OFF).

    NOTE: this flag owns TEXT-ONLY prompt injection (seat_prompt_block / pm_conviction
    section) and is fully independent of MASTERMIND_NW_DECISION (see nw_decision_mode),
    which owns the typed decision-signal chokepoint.
    """
    # W8 (2026-07-19): default flipped ON — the W-NW.1 arming condition (≥5 consecutive builds with
    # nw_context status=present) matured on schedule (come-back date 2026-07-19) and the operator
    # ordered the NW connection as part of the Flagship v2 program. Text-only prompt injection;
    # opt out with MASTERMIND_NW_CONTEXT=0.
    return os.environ.get("MASTERMIND_NW_CONTEXT", "1").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# typed decision-policy chokepoint (A5)
# --------------------------------------------------------------------------- #

def nw_decision_mode() -> str:
    """Return the NW decision mode from MASTERMIND_NW_DECISION (default 'off').

    The five-mode monotone ladder — each mode is a strict superset of the prior's
    authority (use _mode_ge for threshold checks):

        off        nothing; decision_signals() is a byte-identical no-op (inert).
        shadow     compute + log only; signals are still inert to downstream sizing.
        candidacy  NW MAY add candidates (a candidacy prior for the gate to filter).
        shrink     NW may ALSO subtract entry size on graph-conflict density.
        vote       NW may ALSO cast a graded lens vote.

    This flag is SEPARATE from MASTERMIND_NW_CONTEXT, which stays owning text-only
    prompt injection. Unrecognized / empty values fail-soft to 'off'.
    """
    try:
        raw = os.environ.get("MASTERMIND_NW_DECISION")
        if raw is None:
            return _DECISION_MODE_DEFAULT          # ABSENT → the W8 default ('shrink')
        raw = raw.strip().lower()
        # PRESENT but empty/unrecognized → 'off' (inert), NOT the default: a garbled value must
        # never ESCALATE authority (fail-soft means unknown input is inert, W8 default included).
        return raw if raw in _DECISION_MODE_ORDER else "off"
    except Exception:  # noqa: BLE001 — fail-soft: never raise
        return "off"


def _mode_ge(mode: str, threshold: str) -> bool:
    """True iff `mode` is at or above `threshold` on the decision ladder.

    Unrecognized modes/thresholds resolve to 'off' (rank 0), so unknown input is inert.
    """
    m = _DECISION_MODE_ORDER.get(mode, 0)
    t = _DECISION_MODE_ORDER.get(threshold, 0)
    return m >= t


def _inert_signals(mode: str) -> dict[str, Any]:
    """The byte-identical no-op signal dict: everything None/inert."""
    return {
        "candidacy": None,
        "entry_shrink": None,
        "clean_in_conflicted": False,
        "inert": True,
        "mode": mode,
    }


def decision_signals(ticker: str) -> dict[str, Any]:
    """Return TYPED decision signals for `ticker`, gated by nw_decision_mode().

    THE single place that converts raw NW candidate/market fields into decision
    signals, so no downstream consumer reads raw NW fields ad hoc. Fail-soft: any
    absent/stale/malformed context, or an fdr-uncleared name, degrades to the inert
    default (a byte-identical no-op for every caller).

    Return shape::

        {
          "candidacy": {"state": <bottom_state>, "score": <float>, "lean": +1} | None,
          "entry_shrink": 0.7 | None,
          "clean_in_conflicted": <bool>,
          "inert": <bool>,
          "mode": <mode string>,
        }

    Derivation (all fail-soft; absent data → None, never a fabricated signal):
      * off              → fully inert (candidacy/entry_shrink None, clean_in_conflicted False).
      * fdr not cleared  → per-name inert (display-armed-only names never originate a signal).
      * candidacy (mode>=candidacy) → bottom_state WATCH→0.35, BOTTOMING/CONFIRMED→0.50,
                                      lean=+1; any other state → candidacy None.
      * entry_shrink (mode>=shrink) → graph_conflicts>=NW_CONFLICTS_MIN AND fdr ok → NW_ENTRY_SHRINK;
                                      missing/insufficient conflicts → None (never shrink on absence).
      * clean_in_conflicted (mode>=candidacy) → conflicts==0 AND market contradiction_count
                                      >=NW_CONTRADICTIONS_MIN (the safe-haven tell).
    """
    mode = nw_decision_mode()
    try:
        # mode off — byte-identical no-op regardless of row content.
        if not _mode_ge(mode, "shadow"):
            return _inert_signals(mode)

        c = context()
        row = candidate(ticker, ctx=c)
        # per-name inert: absent row, or a name not cleared by the FDR batch.
        kernel = row.get("kernel") if isinstance(row, dict) else None
        reliability_fresh = not lobe_freshness("reliability", c).get("stale", True)
        fdr_ok = (
            reliability_fresh
            and isinstance(kernel, dict)
            and kernel.get("fdr_cleared") is True
        )
        if not row or not fdr_ok:
            return _inert_signals(mode)

        signals = _inert_signals(mode)
        # From here on the name is fdr-cleared and present → not per-name inert,
        # though individual signals may still be None until their mode arms.
        signals["inert"] = False

        # --- graph_conflicts (shared leg for shrink + clean_in_conflicted) --- #
        contradictions_fresh = not lobe_freshness("contradictions", c).get("stale", True)
        conflicts_raw = row.get("graph_conflicts") if contradictions_fresh else None
        conflicts = len(conflicts_raw) if isinstance(conflicts_raw, list) else None

        # --- candidacy (mode >= candidacy) --- #
        if _mode_ge(mode, "candidacy"):
            bottom_fresh = not lobe_freshness("bottom_sensors", c).get("stale", True)
            bottom = (row.get("bottom") or {}) if bottom_fresh else {}
            state = None
            if isinstance(bottom, dict):
                state = bottom.get("bottom_state") or bottom.get("state")
            score = NW_CANDIDACY_SCORES.get(state) if isinstance(state, str) else None
            if score is not None:
                signals["candidacy"] = {"state": state, "score": score, "lean": +1}

            # --- clean_in_conflicted (available at candidacy+) --- #
            try:
                contradictions = int((market_plane(ctx=c) or {}).get("contradiction_count") or 0)
            except Exception:  # noqa: BLE001
                contradictions = 0
            signals["clean_in_conflicted"] = (
                conflicts == 0
                and contradictions_fresh
                and not (market_plane(ctx=c) or {}).get("stale", True)
                and contradictions >= NW_CONTRADICTIONS_MIN
            )

        # --- entry_shrink (mode >= shrink; subtract-only, never on absence) --- #
        if _mode_ge(mode, "shrink"):
            if conflicts is not None and conflicts >= NW_CONFLICTS_MIN:
                signals["entry_shrink"] = NW_ENTRY_SHRINK

        return signals
    except Exception as e:  # noqa: BLE001 — fail-soft: never raise into a decision
        log.debug("neural_web_context: decision_signals failed (%s)", e)
        return _inert_signals(mode)


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #

def _age_days(asof_str: str | None) -> int | None:
    """Calendar days since asof_str (YYYY-MM-DD).  None if unparseable."""
    if not asof_str:
        return None
    try:
        asof_date = date.fromisoformat(str(asof_str)[:10])
        return (date.today() - asof_date).days
    except Exception:  # noqa: BLE001
        return None


def lobe_freshness(name: str, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an honest freshness record for one Neural Web lobe.

    Explicit producer freshness wins.  When the producer did not publish a freshness entry,
    derive age from the lobe's own ``as_of``/``asof``.  A missing or unparseable lobe timestamp
    is stale (fail-closed); top-level freshness never launders a stale sub-lobe.
    """
    try:
        c = ctx if isinstance(ctx, dict) else context()
        if not c:
            return {
                "asof": None,
                "age_days": None,
                "stale": True,
                "source": "absent",
            }
        freshness = c.get("freshness") or {}
        explicit = freshness.get(name) if isinstance(freshness, dict) else None
        if isinstance(explicit, dict):
            asof = explicit.get("as_of") or explicit.get("asof")
            age = _age_days(asof)
            explicit_stale = explicit.get("stale")
            stale = bool(explicit_stale) if explicit_stale is not None else (
                age is None or age < 0 or age > _STALE_DAYS
            )
            # An explicit "fresh" flag cannot override an unparseable/missing timestamp.
            if age is None or age < 0:
                stale = True
            return {
                "asof": asof,
                "age_days": age,
                "stale": bool(stale),
                "source": "producer",
            }

        lobes = c.get("lobes") or {}
        lobe = lobes.get(name) if isinstance(lobes, dict) else None
        asof = (
            lobe.get("as_of") or lobe.get("asof")
            if isinstance(lobe, dict)
            else None
        )
        age = _age_days(asof)
        return {
            "asof": asof,
            "age_days": age,
            "stale": age is None or age < 0 or age > _STALE_DAYS,
            "source": "derived",
        }
    except Exception:  # noqa: BLE001 — fail-closed
        return {
            "asof": None,
            "age_days": None,
            "stale": True,
            "source": "error",
        }
# The Risk Envelope is a native descriptive projection, never another decision
# plane. These fields keep source clocks and overlap disclosures together.
_RISK_SCHEMA = "mastermind.risk_envelope/v1"
_RISK_TIMEZONE = ZoneInfo("America/New_York")
_RISK_FIELDS = (
    "schema", "definition_id", "market", "revision", "bundle_id", "source_session",
    "as_of", "observed_at", "produced_at", "stale_after", "measured_state",
    "hazard_summary", "policy_summary", "data_state", "authority", "coverage",
    "freshness", "coherence", "rotation_context", "confluence", "market_transition",
)
_RISK_AUTHORITY_FLAGS = (
    "envelope_may_rank", "envelope_may_gate",
    "envelope_may_size", "envelope_may_execute",
)
_ROTATION_LABELS = {
    "DEFENSIVE_RELATIVE_STRENGTH": "Defensive relative strength",
    "BROADENING": "Broader-market proxies gaining relative strength",
    "MIXED_ROTATION": "Defensive groups and broader-market proxies gaining relative strength",
    "NO_EARLY_SHIFT": "No early relative shift observed",
}


def _risk_date(value: Any) -> date | None:
    try:
        parsed = date.fromisoformat(value) if isinstance(value, str) else None
        return parsed if parsed and parsed.isoformat() == value else None
    except ValueError:
        return None


def _risk_timestamp(value: Any) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        return stamp.astimezone(timezone.utc) if stamp and stamp.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _risk_envelope_context(
    raw: Any, asof: Any, *, now: datetime | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    # Optional context failures must never erase independent legacy market data
    # or change typed decision eligibility.
    try:
        return _qualify_risk_envelope_context(raw, asof, now=now)
    except Exception as exc:  # noqa: BLE001 — isolate this optional projection
        log.debug("neural_web_context: invalid optional risk context (%s)", type(exc).__name__)
        return None, {"qualified": False, "reasons": ["invalid_envelope"], "context_exclusions": {}}


def _qualify_risk_envelope_context(
    raw: Any, asof: Any, *, now: datetime | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Qualify the inner source on EVERY call, including a cached outer bridge.

    A fresh wrapper cannot refresh an old observation. Optional off-session
    context does not invalidate independently qualified measured/hazard data.
    No scores, votes, posture, caps or confidence are derived here.
    """
    status: dict[str, Any] = {"qualified": False, "reasons": [], "context_exclusions": {}}
    if not isinstance(raw, dict) or not raw:
        status["reasons"] = ["missing_envelope"]
        return None, status
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    session = raw.get("source_session")
    session_date = _risk_date(session)
    status["source_session"] = session if session_date else None
    for key in ("observed_at", "produced_at", "stale_after"):
        status[key] = raw.get(key) if _risk_timestamp(raw.get(key)) else None
    if raw.get("schema") != _RISK_SCHEMA:
        reasons.append("invalid_schema")
    if not session_date or not 0 <= (now.astimezone(_RISK_TIMEZONE).date() - session_date).days <= _STALE_DAYS:
        reasons.append("invalid_future_or_expired_session")
    if not _risk_date(asof) or session != asof or raw.get("as_of") != session:
        reasons.append("source_session_mismatch")
    if raw.get("revision") not in ("settled", "corrected", "live_provisional"):
        reasons.append("invalid_revision")
    if raw.get("data_state") not in ("FRESH", "PARTIAL", "DEGRADED"):
        reasons.append("unusable_data_state")
    if not isinstance(raw.get("bundle_id"), str) or not raw["bundle_id"]:
        reasons.append("missing_bundle_id")
    for key in ("measured_state", "hazard_summary", "policy_summary"):
        if not isinstance(raw.get(key), dict):
            reasons.append("invalid_" + key)
    authority = raw.get("authority")
    if (not isinstance(authority, dict)
            or any(authority.get(key) is not False for key in _RISK_AUTHORITY_FLAGS)
            or authority.get("policy_actions_require_individual_authority") is not True):
        reasons.append("unqualified_authority")
    for key in ("hazard_summary", "policy_summary"):
        block = raw.get(key)
        if isinstance(block, dict) and block.get("display_only") is not True:
            reasons.append("invalid_" + key + "_authority")
    observed, produced = (_risk_timestamp(raw.get(key)) for key in ("observed_at", "produced_at"))
    for key, stamp in (("observed_at", observed), ("produced_at", produced)):
        if stamp is None:
            reasons.append("missing_or_invalid_" + key)
        elif stamp > now:
            reasons.append("future_" + key)
    if observed and produced and observed > produced:
        reasons.append("incoherent_publication_clocks")
    if observed and session_date and observed.astimezone(_RISK_TIMEZONE).date() < session_date:
        reasons.append("observation_before_source_session")
    expires = _risk_timestamp(raw.get("stale_after"))
    if raw.get("stale_after") is not None and (expires is None or expires <= now or (produced and expires < produced)):
        reasons.append("invalid_or_expired_envelope")
    if raw.get("revision") == "live_provisional" and expires is None:
        reasons.append("missing_live_expiry")
    measured = raw.get("measured_state") or {}
    if isinstance(measured, dict) and measured.get("usable") is True:
        if measured.get("as_of") != session:
            reasons.append("measured_session_mismatch")
        if measured.get("verdict") not in ("RISK_ON", "MIXED", "RISK_OFF"):
            reasons.append("invalid_measured_verdict")
    freshness = raw.get("freshness") or {}
    if not isinstance(freshness, dict):
        reasons.append("invalid_freshness")
    else:
        if freshness.get("source_session") not in (None, session):
            reasons.append("freshness_session_mismatch")
        if freshness.get("stale") is True:
            reasons.append("owner_stale")
    if raw.get("stale") is True:
        reasons.append("owner_stale")
    confluence = raw.get("confluence")
    if isinstance(confluence, dict) and any(confluence.get(key) is not False for key in (
        "statistical_independence_established", "changes_hazard_stage", "changes_policy",
    )):
        reasons.append("invalid_confluence_authority")

    # Whitelist and detach: neither raw Cortex/provenance prose nor mutations of a
    # caller's returned view can enter/change the canonical process cache.
    envelope = {key: raw[key] for key in _RISK_FIELDS if key in raw}
    try:
        encoded = json.dumps(envelope, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 32768:
            reasons.append("context_size_limit")
        envelope = json.loads(encoded)
    except (ValueError, TypeError):
        reasons.append("invalid_json_values")
    if reasons:
        status["reasons"] = sorted(set(reasons))
        return None, status

    excluded: dict[str, str] = status["context_exclusions"]
    for key in ("rotation_context", "confluence", "market_transition"):
        value = envelope.get(key)
        if value is not None and (not isinstance(value, dict) or value.get("display_only") is not True):
            excluded[key] = "invalid_descriptive_context"
            envelope[key] = None
    rotation = envelope.get("rotation_context")
    if isinstance(rotation, dict) and rotation.get("usable") is True:
        early = rotation.get("early_context")
        if (rotation.get("as_of") != session or not isinstance(early, dict)
                or early.get("as_of") != session or early.get("display_only") is not True
                or early.get("prior_loser_constituent_claim") is not False
                or not isinstance(rotation.get("state"), str)
                or rotation.get("state") not in _ROTATION_LABELS
                or early.get("state") != rotation.get("state")):
            excluded["rotation_context"] = "rotation_source_session_mismatch"
            envelope["rotation_context"] = None
    confluence = envelope.get("confluence")
    if isinstance(confluence, dict):
        rotation = envelope.get("rotation_context")
        expected_rotation = rotation.get("state") if isinstance(rotation, dict) and rotation.get("usable") is True else None
        expected_backdrop = measured.get("verdict") if measured.get("usable") is True else None
        if confluence.get("rotation_state") != expected_rotation or confluence.get("measured_backdrop") != expected_backdrop:
            excluded["confluence"] = "source_context_unavailable_or_mismatched"
            envelope["confluence"] = None
        elif ((confluence.get("lineage_status") != "COMPLETE" or confluence.get("unknown_lineage_sources"))
                and confluence.get("nonredundant_component_count") is not None):
            excluded["confluence"] = "incomplete_lineage_count"
            envelope["confluence"] = None
    transition = envelope.get("market_transition")
    if isinstance(transition, dict):
        records = [transition.get(key) for key in ("latest_recorded", "previous_recorded", "current_snapshot")]
        for key in ("latest_comparison", "latest_recorded_change"):
            comparison = transition.get(key)
            if isinstance(comparison, dict):
                records.extend((comparison.get("before"), comparison.get("after")))
        invalid_records = False
        for record in records:
            if record is None:
                continue
            if not isinstance(record, dict):
                invalid_records = True
                break
            dates = [_risk_date(record[key]) for key in ("asof", "as_of", "source_session", "session_date")
                     if record.get(key) is not None]
            clocks = [_risk_timestamp(record[key]) for key in (
                "logged_at", "observed_at", "produced_at", "available_at",
                "generated_at", "generated_utc", "updated_at", "timestamp", "ts",
            ) if record.get(key) is not None]
            # Every recognized present alias must agree with the source session
            # and precede this envelope publication. Missing clocks stay unknown.
            if (not dates or any(stamp is None or stamp > session_date for stamp in dates)
                    or len(set(dates)) != 1
                    or any(stamp is None or stamp > produced for stamp in clocks)):
                invalid_records = True
                break
        if (transition.get("source_session") != session
                or transition.get("basis") != "market_state_forward_log_first_writer"
                or invalid_records):
            excluded["market_transition"] = "invalid_transition_source_or_record"
            envelope["market_transition"] = None
    # freshness.all_on_session includes optional sources and is disclosure only.
    status["qualified"] = True
    return envelope, status


def _risk_token(value: Any) -> str:
    """Closed scalar copy for prompts; no arbitrary owner prose."""
    return value if isinstance(value, str) and 0 < len(value) <= 64 and all(
        ch.isupper() or ch.isdigit() or ch == "_" for ch in value
    ) else "unavailable"


def _risk_prompt_lines(envelope: dict[str, Any] | None, status: dict[str, Any]) -> list[str]:
    if envelope is None:
        return ["Risk/rotation context unavailable: " + ",".join(status.get("reasons") or ["unknown"])]
    measured = envelope.get("measured_state") or {}
    hazard = envelope.get("hazard_summary") or {}
    policy = envelope.get("policy_summary") or {}
    state = _risk_token(measured.get("verdict")) if measured.get("usable") is True else "unavailable"
    lines = [
        "Risk context is descriptive: no extra evidence vote or sizing authority; overlap is not independent confirmation.",
        f"Backdrop: {state} asof={envelope.get('source_session')}; hazard={_risk_token(hazard.get('stage'))}; native policy={_risk_token(policy.get('posture'))}; data={_risk_token(envelope.get('data_state'))}.",
    ]
    rotation = envelope.get("rotation_context") or {}
    rotation_label = _ROTATION_LABELS.get(rotation.get("state"), "unavailable") if rotation.get("usable") is True and isinstance(rotation.get("state"), str) else "unavailable"
    lines.append(f"Early rotation: {rotation_label}; asof={rotation.get('as_of') if _risk_date(rotation.get('as_of')) else 'unknown'}. Relative prices do not establish fund flows.")
    confluence = envelope.get("confluence") or {}
    # Never present an incomplete dependency inventory as an independent vote count.
    lineage = _risk_token(confluence.get("lineage_status"))
    lines.append(f"Confluence lineage={lineage}; statistical independence is not established.")
    transition = envelope.get("market_transition") or {}
    change = transition.get("latest_recorded_change")
    if isinstance(change, dict) and change.get("verdict_changed") is True:
        before, after = change.get("before") or {}, change.get("after") or {}
        if isinstance(before, dict) and isinstance(after, dict) and _risk_date(before.get("asof")) and _risk_date(after.get("asof")):
            lines.append(f"Last recorded change: {_risk_token(before.get('verdict'))} {before['asof']} -> {_risk_token(after.get('verdict'))} {after['asof']} (first-writer record; cause not inferred).")
        else:
            lines.append("Recorded market transition unavailable.")
    else:
        lines.append("Recorded market transition unavailable." if not transition else "No recorded verdict change supplied.")
    return lines


def _load_raw() -> dict[str, Any] | None:
    """Read and JSON-parse the artifact.  Returns None on any IO/parse error."""
    try:
        if not _ARTIFACT_PATH.exists():
            return None
        return json.loads(_ARTIFACT_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("neural_web_context: read failed (%s)", e)
        return None


def _validate(raw: Any) -> tuple[bool, str]:
    """Return (valid, reason).  valid=True only when schema+is_context_only+as_of+freshness pass."""
    if not isinstance(raw, dict):
        return False, "not a dict"
    if raw.get("schema") != _EXPECTED_SCHEMA:
        return False, f"wrong schema {raw.get('schema')!r}"
    if not raw.get("is_context_only"):
        return False, "is_context_only not True"
    asof = raw.get("as_of")
    if not asof:
        return False, "as_of absent"
    age = _age_days(asof)
    if age is None:
        return False, f"as_of unparseable: {asof!r}"
    if age < 0:
        return False, f"future-dated: as_of={asof} age={age}d"
    if age > _STALE_DAYS:
        return False, f"stale: as_of={asof} age={age}d > {_STALE_DAYS}d"
    return True, "ok"


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #

def _artifact_identity() -> tuple[int, int, int, int] | None:
    """File metadata invalidates cached bytes; it never establishes market freshness."""
    try:
        info = _ARTIFACT_PATH.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    except OSError:
        return None


def context() -> dict[str, Any]:
    """Read the existing source cache with a coherent identity/value pair."""
    with _CACHE_LOCK:
        return _context_locked()


def _context_locked() -> dict[str, Any]:
    """Return cached source bytes while source identity and source age remain valid.

    Atomic replacement is visible to long-running consumers without a restart.
    Missing/malformed/stale data remains empty; mtime never supplies evidence age.
    """
    global _CACHE, _CACHE_LOADED, _CACHE_SIGNATURE
    identity = _artifact_identity()
    if _CACHE_LOADED and identity == _CACHE_SIGNATURE:
        if _CACHE and not _validate(_CACHE)[0]:
            _CACHE = {}
        return _CACHE or {}
    _CACHE_LOADED = True
    _CACHE_SIGNATURE = identity
    try:
        raw = _load_raw()
        if _artifact_identity() != identity:
            # The source changed during the read. Abstain for this call and let
            # the next caller read one coherent replacement; never retry writes.
            _reset_context_cache()
            return {}
        if raw is None:
            _CACHE = {}
            return {}
        valid, reason = _validate(raw)
        if not valid:
            log.debug("neural_web_context: invalid artifact (%s)", reason)
            _CACHE = {}
            return {}
        _CACHE = raw
        return _CACHE
    except Exception as e:  # noqa: BLE001 — fail-soft: never raise into a build
        log.warning("neural_web_context: unexpected error loading context (%s)", e)
        _CACHE = {}
        return {}


def candidate(ticker: str, *, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return advisory context; optional ctx binds reads to an already captured source."""
    try:
        c = context() if ctx is None else ctx
        if not c:
            return {}
        cc = c.get("candidate_context")
        if not isinstance(cc, dict):
            return {}
        row = cc.get(str(ticker).upper())
        return row if isinstance(row, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def market_plane(*, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a compact dict for the neural_web market_view plane.

    Shape: {verdict, regime, vol, breadth, liquidity, contradiction_count, asof, stale,
            risk_envelope, risk_envelope_status}. Risk context is descriptive only.
    Returns an empty-stale dict if context is absent/stale.

    ``liquidity`` is distilled fail-soft from the market lobe's liquidity_plumbing block:
    {state, netliq_bn, tga_bn, tga_impulse} — every field None (tga_impulse None, not {})
    when the plumbing block is absent, so the shape is stable for pass-through consumers.
    Optional ctx keeps a decision on the same already captured source generation.
    """
    try:
        c = context() if ctx is None else ctx
        if not c:
            return {"stale": True, "asof": None}
        lobes = c.get("lobes") or {}
        market = lobes.get("market") or {}
        contradictions_lobe = lobes.get("contradictions") or {}
        market_health = lobe_freshness("market", c)
        asof = market_health.get("asof") or c.get("as_of")
        stale = bool(market_health.get("stale", True))
        if stale:
            return {
                "stale": True,
                "asof": asof,
                "lobe_freshness": market_health,
            }

        risk_envelope, risk_status = _risk_envelope_context(
            market.get("risk_envelope"), market_health.get("asof"),
        )
        verdict_raw = market.get("verdict") or {}
        regime_raw = market.get("regime") or {}
        vol_raw = market.get("vol") or {}
        breadth_raw = market.get("breadth") or {}
        contr_summary = (contradictions_lobe.get("summary") or
                         market.get("contradictions") or {})

        # count contradiction records
        contr_count = 0
        try:
            recs = contradictions_lobe.get("records") or []
            contr_count = len(recs) if isinstance(recs, list) else 0
        except Exception:  # noqa: BLE001
            pass

        # W-TSY.1 — Treasury/TGA liquidity distillation (additive; stable shape).
        # Every access .get-chained with isinstance guards; an absent/malformed
        # liquidity_plumbing block degrades to all-None fields, never raises.
        _plumb = market.get("liquidity_plumbing")
        _plumb = _plumb if isinstance(_plumb, dict) else {}
        _headline = _plumb.get("headline")
        _headline = _headline if isinstance(_headline, dict) else {}
        _quantity = _plumb.get("quantity")
        _quantity = _quantity if isinstance(_quantity, dict) else {}
        _treasury = _plumb.get("treasury")
        _treasury = _treasury if isinstance(_treasury, dict) else {}
        _impulse = _treasury.get("tga_impulse")
        liquidity = {
            "state": _headline.get("state"),
            "netliq_bn": _quantity.get("netliq_bn"),
            "tga_bn": _treasury.get("tga_bn"),
            "tga_impulse": ({
                "direction": _impulse.get("direction"),
                "magnitude_bn": _impulse.get("magnitude_bn"),
                "quarter_end_adjacent": _impulse.get("quarter_end_adjacent"),
            } if isinstance(_impulse, dict) else None),
        }

        return {
            "verdict": verdict_raw,
            "regime": {
                "quad": regime_raw.get("quad"),
                "quad_name": regime_raw.get("quad_name"),
                "confidence": regime_raw.get("confidence"),
                "cycle_tag": regime_raw.get("cycle_tag"),
                "transition_state": regime_raw.get("transition_state"),
                "flip_margin": regime_raw.get("flip_margin"),
                "liquidity_overlay": regime_raw.get("liquidity_overlay"),
            },
            "vol": vol_raw,
            "breadth": breadth_raw,
            "liquidity": liquidity,
            "contradiction_count": contr_count,
            "contradiction_summary": contr_summary,
            "risk_envelope": risk_envelope,
            "risk_envelope_status": risk_status,
            "asof": asof,
            "stale": stale,
            "lobe_freshness": market_health,
        }
    except Exception:  # noqa: BLE001
        return {"stale": True, "asof": None}


def seat_prompt_block(tickers: list[str], max_chars: int = 1200) -> str:
    """Return compact text lines suitable for prompt injection (bounded to max_chars).

    STRUCTURAL EXCLUSION: cortex memo text is NEVER included — this function reads
    only candidate_context rows, market-level regime/vol/breadth, and qualified
    native descriptive risk fields. Risk context supplies no additional evidence vote.
    It never touches lobes['cortex'] or any memo field.

    Returns empty string when context is absent/stale or flag is OFF.
    """
    try:
        c = context()
        if not c:
            return ""
        asof = c.get("as_of")
        market_health = lobe_freshness("market", c)
        if market_health.get("stale", True):
            return ""

        lobes = c.get("lobes") or {}
        market = lobes.get("market") or {}
        regime_raw = market.get("regime") or {}
        vol_raw = market.get("vol") or {}
        breadth_raw = market.get("breadth") or {}
        verdict_raw = market.get("verdict") or {}
        candidate_ctx = c.get("candidate_context") or {}

        lines: list[str] = []
        lines.append(f"NW asof={asof}")
        risk_envelope, risk_status = _risk_envelope_context(
            market.get("risk_envelope"), market_health.get("asof"),
        )
        lines.extend(_risk_prompt_lines(risk_envelope, risk_status))
        source_lobes = ("market", "reliability", "contradictions",
                        "bottom_sensors", "options_entry")
        stale_lobes = [name for name in source_lobes
                       if lobe_freshness(name, c).get("stale", True)]
        if stale_lobes:
            lines.append("NW stale lobes excluded: " + ",".join(stale_lobes))

        # market-level context
        quad_name = regime_raw.get("quad_name") or ""
        conf = regime_raw.get("confidence")
        cycle_tag = regime_raw.get("cycle_tag") or ""
        trans = regime_raw.get("transition_state") or ""
        liq = regime_raw.get("liquidity_overlay") or ""
        if quad_name or conf is not None:
            lines.append(
                f"Regime: {quad_name} conf={conf} cycle={cycle_tag} "
                f"transition={trans} liquidity={liq}"
            )

        verdict_en = verdict_raw.get("label_en") or verdict_raw.get("verdict") or ""
        if verdict_en:
            lines.append(f"NW verdict: {verdict_en}")

        breadth_label = breadth_raw.get("label_en") or breadth_raw.get("label") or ""
        vol_label = vol_raw.get("label_en") or vol_raw.get("label") or ""
        if breadth_label or vol_label:
            lines.append(f"Breadth: {breadth_label}  Vol: {vol_label}")

        # per-candidate rows — ONLY for tickers in the provided set, NO cortex
        norm_tickers = {t.upper() for t in tickers if t}
        cand_lines: list[str] = []
        for tkr, row in (candidate_ctx.items() if isinstance(candidate_ctx, dict) else []):
            if tkr.upper() not in norm_tickers:
                continue
            if not isinstance(row, dict):
                continue
            parts: list[str] = [tkr]
            bottom = (
                row.get("bottom") or {}
                if not lobe_freshness("bottom_sensors", c).get("stale", True)
                else {}
            )
            if bottom:
                bst = bottom.get("bottom_state") or bottom.get("state") or ""
                if bst:
                    parts.append(f"bottom={bst}")
            opts = (
                row.get("options") or {}
                if not lobe_freshness("options_entry", c).get("stale", True)
                else {}
            )
            if opts:
                gate_status = opts.get("gate_status") or opts.get("status") or ""
                if gate_status:
                    parts.append(f"options={gate_status}")
            conflicts = (
                row.get("graph_conflicts") or []
                if not lobe_freshness("contradictions", c).get("stale", True)
                else []
            )
            if conflicts and isinstance(conflicts, list):
                parts.append(f"conflicts={len(conflicts)}")
            kernel = (
                row.get("kernel") or {}
                if not lobe_freshness("reliability", c).get("stale", True)
                else {}
            )
            if isinstance(kernel, dict) and kernel.get("fdr_cleared") is False:
                parts.append("kernel=display_armed_only")
            cand_lines.append(" ".join(parts))

        if cand_lines:
            lines.append("Candidates: " + "; ".join(cand_lines[:20]))

        result = "\n".join(lines)
        # hard bound — structural, not filtering
        if len(result) > max_chars:
            result = result[:max_chars]
        return result
    except Exception:  # noqa: BLE001 — fail-soft
        return ""


def audit_row() -> dict[str, Any]:
    """Return {status, asof, age_days, n_candidates, gap_notes_count} for runlog.

    status: 'present' | 'absent' | 'stale'
    This function is flag-independent — always runs to feed the perception runlog.
    """
    try:
        raw = _load_raw()
        if raw is None:
            return {"status": "absent", "asof": None, "age_days": None,
                    "n_candidates": 0, "gap_notes_count": 0}
        asof = raw.get("as_of")
        age = _age_days(asof)

        # check schema first
        if raw.get("schema") != _EXPECTED_SCHEMA or not raw.get("is_context_only") or not asof:
            return {"status": "absent", "asof": asof, "age_days": age,
                    "n_candidates": 0, "gap_notes_count": 0}

        if age is None or age < 0 or age > _STALE_DAYS:
            return {"status": "stale", "asof": asof, "age_days": age,
                    "n_candidates": 0, "gap_notes_count": 0}

        cc = raw.get("candidate_context") or {}
        n_cands = len(cc) if isinstance(cc, dict) else 0
        gap_notes = raw.get("gap_notes") or []
        n_gaps = len(gap_notes) if isinstance(gap_notes, list) else 0
        lobes = raw.get("lobes") or {}
        lobe_names = list(lobes) if isinstance(lobes, dict) else []
        lobe_health = {name: lobe_freshness(name, raw) for name in lobe_names}

        return {
            "status": "present",
            "asof": asof,
            "age_days": age,
            "n_candidates": n_cands,
            "gap_notes_count": n_gaps,
            "market_lobe_stale": lobe_health.get("market", {}).get("stale", True),
            "fresh_lobes": sum(1 for row in lobe_health.values()
                               if not row.get("stale", True)),
            "stale_lobes": sum(1 for row in lobe_health.values()
                               if row.get("stale", True)),
        }
    except Exception:  # noqa: BLE001
        return {"status": "absent", "asof": None, "age_days": None,
                "n_candidates": 0, "gap_notes_count": 0}
