#!/usr/bin/env python3
"""pick.py — pool router for agent-pools machine-wide pickup.

Given --task-class and optional --prefer / --pool, applies hard filters then
the R15/R17–R27 routing law in orch/fabric/pools.yaml. Prints ONE line:

  POOL=<name> KEY=<bailian_key_name or -> MODEL=<default> REASON=<...> [ESCALATE_TO=<tier>]
  NONE reason=...

Never prints key values. Reads config only at runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import model_tier
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
POOLS_YAML = os.path.join(HERE, "..", "orch", "fabric", "pools.yaml")
if os.path.lexists(os.path.join(HERE, "pools.yaml")):
    from fabric_policy_snapshot import verified_snapshot_path
    POOLS_YAML = str(verified_snapshot_path(HERE))
LEDGER_PATH = os.path.join(HERE, "..", "orch", "fabric", "ledger.jsonl")
SLOT_ROOT = os.path.join(HERE, "slots")
GROK_EXHAUSTED = os.path.join(HERE, "GROK_EXHAUSTED")
BAILIAN_KEYS = os.path.join(HERE, "bailian_keys.py")
BAILIAN_USAGE = os.path.join(HERE, "bailian_usage.json")

# Task-class to pool-fit mapping (from POOL_LIMITS.md / ROUTING_SURVEY.md)
TASK_CLASS_FIT = {
    "high_level":  ["cursor", "claude"],
    "fix_build":   ["minimax", "grok"],
    "review":      ["bailian"],
    "census":      ["bailian"],
    "audit":       ["bailian"],
    "orchestration": ["claude"],
    "domain_orchestration": ["glm", "grok"],
    "mechanical":  ["bailian", "minimax"],
    "unknown":     ["bailian", "minimax", "grok"],
}

# Base scores per pool per task class
BASE_SCORES = {
    "minimax":   {"fix_build": 80, "default": 40},
    "bailian":   {"review": 75, "census": 75, "audit": 75,
                  "fix_build": 60, "mechanical": 60, "default": 50},
    "grok":      {"fix_build": 90, "high_level": 50, "default": 50},
    "cursor":    {"high_level": 25, "default": 10},
    "claude":    {"orchestration": 100, "high_level": 60, "default": 0},
}

OFFPEAK_WEIGHT = 25
BURNDOWN_WEIGHT = 20
HIGH_TIER_WEIGHT = 15
LEAST_BUSY_WEIGHT = 10

SHANGHAI_TZ = "Asia/Shanghai"

POOL_ALIASES = {
    "qwen": "bailian",
    "claude-fable": "claude",
    "fable": "claude",
    "claude-opus": "claude",
}

EXECUTE_CLASSES_DEFAULT = frozenset({
    "execute", "fix_build", "mechanical", "review", "census", "audit",
    "verify", "heal", "build", "fix",
})
OPERATOR_CLASSES_DEFAULT = frozenset({
    "architecture", "integration", "design", "decompose", "adjudicate", "high_level",
    "domain_orchestration",
})
SEAT_CLASSES_DEFAULT = frozenset({"ruling", "orchestration"})
FORBIDDEN_MINIMAX_DEFAULT = frozenset({
    "architecture", "integration", "design", "ruling", "decompose", "adjudicate",
})
EXECUTE_ORDER_DEFAULT = ["minimax", "glm-flash", "bailian", "grok", "cursor"]
JUDGMENT_ORDER_DEFAULT = ["glm-5.3", "grok", "cursor", "fable"]  # R31a
ESCALATION_LADDER_DEFAULT = [
    "minimax", "glm-flash", "glm-5.3", "bailian-max", "cursor", "fable",
]
SEAT_POOLS = frozenset({"claude", "claude-fable", "fable"})

# R24 — GLM roles are per MODEL, not per pool: glm-5.3-flash serves the
# executor/labor classes, glm-5.3 the review/operator classes (pools.yaml
# pools.glm.models is the source of truth; glm_keys.model() the fallback).
GLM_FLASH_CLASSES = frozenset({
    "execute", "fix_build", "mechanical", "census", "audit", "verify",
})
GLM_FULL_CLASSES = frozenset({
    "review", "high_level", "decompose", "adjudicate", "repair",
    "architecture", "integration", "design", "operator", "reviewer",
    "domain_orchestration",
})
# Routing/ladder tokens → concrete pool ("glm-flash" = pool glm + glm-5.3-flash,
# "glm-5.3" = pool glm + glm-5.3, "bailian-max" = pool bailian + qwen3.8-max).
ROUTING_TOKEN_POOLS = {
    "glm-flash": "glm",
    "glm-5.3": "glm",
    "bailian-max": "bailian",
}

_POOLS_DOC: Optional[Dict[str, Any]] = None


def _now_sh() -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(SHANGHAI_TZ))


def _is_offpeak() -> bool:
    """True between 22:00 and 08:00 Asia/Shanghai."""
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        return bailian_keys.is_offpeak()
    except Exception:
        dt = _now_sh()
        h, m = dt.hour, dt.minute
        mins = h * 60 + m
        start = 22 * 60   # 22:00
        end   = 8 * 60    # 08:00
        if start < end:
            return False  # degenerate
        return mins >= start or mins < end


def _minutes_to_reset(pool: str) -> float:
    """Hours until next weekly reset for minimax/grok (float)."""
    if pool == "minimax":
        pair = _minimax_burn_down_window()
        # Neutral score horizon when no observation exists, never a reset claim.
        return 168.0 if pair is None else pair[0]
    if pool == "grok":
        pair = _grok_burn_down_window()
        return 168.0 if pair is None else pair[0]
    if pool == "glm":
        # R31 round 2: hours and remaining MUST come from one account's one window.
        # glm_burn()["weekly_reset"] is NOT usable here -- glm_burn rolls only the
        # 5h boundary forward (one `while now_ts >= five_reset` loop, none for
        # weekly) and otherwise copies glm_window_state.json verbatim, so after a
        # weekly boundary that field goes PAST and `max(0.0, secs)` would report
        # hours=0.0 -> inside any threshold -> promotion. Read the paired
        # per-account provider window instead.
        pair = _glm_burn_down_window()
        return 168.0 if pair is None else max(0.0, pair[0])
    return 168.0  # default 1 week


def _hours_to_reset(pool: str) -> float:
    """Alias with the truthful name; `_minutes_to_reset` has always returned hours."""
    return _minutes_to_reset(pool)


REVIEW_CLASSES_R33 = frozenset({"review", "audit", "verify"})


def _weekly_remaining_pct(pool: str) -> Optional[float]:
    """Remaining % of the pool's weekly quota window, provider-authoritative when a
    reader exists (R31). None = unknown (no reader / read failed)."""
    if pool == "glm":
        # Same pair as _minutes_to_reset, so the two halves of the R31 test can
        # never describe different windows. NOT glm_burn()["pct_week"]: that is
        # glm_quota_decision's single "best" account (5h pct first), whose own
        # weekly reset can be days from the pool clock -- on 2026-09-20
        # chairman-max reset 21:16Z with 0% left while chairman-max-3 held 66%
        # until 09-23. And NOT `credits_by_account`, which is a LOCAL
        # reconstruction the provider read never overwrites: it showed one account
        # "65% free" while a real lane took 429 [1310] Weekly Limit Exhausted.
        pair = _glm_burn_down_window()
        return None if pair is None else pair[1]
    if pool == "minimax":
        pair = _minimax_burn_down_window()
        return None if pair is None else pair[1]
    if pool == "grok":
        pair = _grok_burn_down_window()
        return None if pair is None else pair[1]
    return None


def _grok_burn_down_window(doc=None, now=None):
    """One dated operator-supplied provider screenshot, never a guessed week."""
    import math
    source = load_pools() if doc is None else doc
    cfg = (((source.get("pools") or {}).get("grok") or {}).get("windows") or {}).get("weekly") or {}
    if cfg.get("source") != "chairman_provider_screenshot":
        return None
    remaining = cfg.get("remaining_pct")
    if type(remaining) not in (int, float) or not math.isfinite(remaining) or not 0 <= remaining <= 100:
        return None
    try:
        observed = datetime.fromisoformat(cfg["observed_at"].replace("Z", "+00:00"))
        reset = datetime.fromisoformat(cfg["reset_at"].replace("Z", "+00:00"))
        now = now or datetime.now(timezone.utc)
        if observed.utcoffset() is None or reset.utcoffset() is None:
            return None
        age = (now - observed).total_seconds()
        hours = (reset - now).total_seconds() / 3600
        if not 0 <= age <= 21600 or not 0 < hours <= 6:
            return None
        return hours, float(remaining)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None


def _grok_priority_active(doc=None, task_class=None):
    source = load_pools() if doc is None else doc
    cfg = _routing(source).get("grok_expiring_priority") or {}
    pair = _grok_burn_down_window(source)
    if cfg.get("enabled") is not True or pair is None or pair[1] < 15 or _grok_exhausted():
        return False
    allowed = {"execute", "fix_build", "mechanical", "review", "audit", "census", "verify",
               "build", "fix", "heal", "extract", "tests-only-repair", "integration", "design",
               "high_level", "repair", "domain_orchestration"}
    return task_class in allowed


def _minimax_burn_down_window(doc: Optional[Dict[str, Any]] = None
                              ) -> Optional[Tuple[float, float]]:
    """Use one fresh provider row for both MiniMax reset and remaining quota."""
    import math
    try:
        import quota_remote
        states = quota_remote.read_provider("minimax")
        freshness = float(quota_remote.FRESH_S)
    except Exception:
        return None
    if not math.isfinite(freshness) or freshness <= 0:
        return None
    now = datetime.now(timezone.utc)
    windows = []
    for state in states or []:
        if (getattr(state, "provider", None) != "minimax"
                or getattr(state, "source", None) != "PROVIDER_AUTHORITATIVE"
                or getattr(state, "window", None) not in ("weekly", "week", "7d")):
            continue
        remaining = getattr(state, "remaining_pct", None)
        if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
            continue
        if not 0 <= remaining <= 100 or not math.isfinite(remaining):
            continue
        try:
            observed = datetime.fromisoformat(state.observed_at.replace("Z", "+00:00"))
            reset = datetime.fromisoformat(state.reset_at.replace("Z", "+00:00"))
            if observed.utcoffset() is None or reset.utcoffset() is None:
                continue
            age = (now - observed).total_seconds()
            hours = (reset - now).total_seconds() / 3600.0
        except (AttributeError, TypeError, ValueError, OverflowError):
            continue
        if not 0 <= age <= freshness or hours <= 0:
            continue
        windows.append((hours, float(remaining)))
    if not windows:
        return None
    floor = _burn_down_cfg(doc)["min_remaining_pct"]
    eligible = [window for window in windows if window[1] >= floor]
    return min(eligible or windows, key=lambda window: window[0])


def _glm_account_weekly_windows() -> Optional[List[Tuple[float, float]]]:
    """[(hours until THAT account's weekly reset, THAT account's remaining %)].

    Read from one provider row per account (`quota_remote.glm_accounts_state()`,
    cached, FRESH_S=600, ~5 ms) so hours and remaining are paired by construction.
    An account whose reset is already in the PAST is DROPPED, not scored as
    hours=0 -- a past stamp is a stale reading, not an imminent boundary.
    None = no authoritative per-account reading at all -> callers refuse.
    """
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import quota_remote
        rows = quota_remote.glm_accounts_state()
    except Exception:
        return None
    now = datetime.now(timezone.utc)
    out: List[Tuple[float, float]] = []
    for row in rows or []:
        if str((row or {}).get("source") or "") != "PROVIDER_AUTHORITATIVE":
            continue
        for st in (row or {}).get("states") or []:
            if str(getattr(st, "window", "") or "").lower() not in ("weekly", "week", "7d"):
                continue
            rem = getattr(st, "remaining_pct", None)
            reset = getattr(st, "reset_at", None)
            if rem is None or not reset:
                continue
            try:
                when = datetime.fromisoformat(str(reset).strip().replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                hours = (when - now).total_seconds() / 3600.0
                rem_f = max(0.0, min(100.0, float(rem)))
            except (TypeError, ValueError):
                continue
            if hours <= 0:
                continue
            out.append((hours, rem_f))
    return out or None


def _glm_burn_down_window(doc: Optional[Dict[str, Any]] = None
                          ) -> Optional[Tuple[float, float]]:
    """The one (hours, remaining %) pair R31 judges glm on: among accounts still
    holding >= min_remaining_pct, the one resetting SOONEST -- the capacity most at
    risk of forfeiture. When none qualify, report the soonest window anyway so the
    pair stays truthful and the remaining test fails on its own merits."""
    wins = _glm_account_weekly_windows()
    if not wins:
        return None
    floor = _burn_down_cfg(doc)["min_remaining_pct"]
    eligible = [w for w in wins if w[1] >= floor]
    return min(eligible or wins, key=lambda w: w[0])


# R31 pools whose weekly window may earn a burn-down promotion.
_BURN_DOWN_POOLS_R31 = ("minimax", "grok", "glm")
# Every promotion requires a dated paired quota window; Grok uses the explicit
# operator-supplied screenshot until its observed reset and never guesses a week.
_BURN_DOWN_NEEDS_AUTHORITATIVE_R31 = frozenset({"glm", "minimax", "grok"})


def _burn_down_remaining_pct_r31(pool: str) -> Optional[float]:
    """Remaining % for the R31 burn-down term, with ONE definition of what an
    unknown means. None = refuse to guess (fail closed, never urgent)."""
    rem = _weekly_remaining_pct(pool)
    if rem is not None:
        try:
            return max(0.0, min(100.0, float(rem)))
        except (TypeError, ValueError):
            return None
    if pool in _BURN_DOWN_NEEDS_AUTHORITATIVE_R31:
        return None
    return None  # unknown is not evidence of available quota


def _burn_down_cfg(doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = _routing(doc).get("burn_down") or {}
    return {
        "hours_before_reset": float(cfg.get("hours_before_reset", 36) or 36),
        "min_remaining_pct": float(cfg.get("min_remaining_pct", 15) or 15),
        "promote": bool(cfg.get("promote", True)),
    }


def burn_down_urgent(pool: str, doc: Optional[Dict[str, Any]] = None) -> bool:
    """R31 use-it-or-lose-it: weekly-window pool resetting within
    hours_before_reset with >= min_remaining_pct unspent.

    MiniMax and GLM require fresh paired provider observations. Grok accepts the
    dated operator-supplied provider screenshot. Unknown quota is never urgent."""
    p = canonical_pool(pool) or pool
    if p not in _BURN_DOWN_POOLS_R31:
        p = pool_family(p) or p
    if p not in _BURN_DOWN_POOLS_R31:
        return False
    cfg = _burn_down_cfg(doc)
    if not cfg["promote"]:
        return False
    if p == "grok" and _grok_exhausted():
        return False
    if p in {"glm", "minimax", "grok"}:
        # Bind the pair ONCE per verdict. Sampling it twice -- _hours_to_reset()
        # and then _weekly_remaining_pct(), each calling _glm_burn_down_window()
        # on its own -- leaves a TOCTOU against a concurrent cache writer that
        # can recombine tonight's clock with a FAR window's remaining, which is
        # round-1 MAJOR 2's exact symptom (Grok round 2, MINOR 1).
        pair = (_minimax_burn_down_window(doc) if p == "minimax"
                else _grok_burn_down_window(doc) if p == "grok"
                else _glm_burn_down_window(doc))
        if pair is None:
            return False
        hours, rem = pair
        return (hours <= cfg["hours_before_reset"]
                and rem >= cfg["min_remaining_pct"])
    if _hours_to_reset(p) > cfg["hours_before_reset"]:
        return False
    rem = _burn_down_remaining_pct_r31(p)
    if rem is None:
        return False
    return rem >= cfg["min_remaining_pct"]


def _promote_urgent(tokens: List[str], doc: Optional[Dict[str, Any]] = None,
                    allowed_pools: Optional[frozenset] = None) -> List[str]:
    """Stable partition: urgent pools first, everything else in original order.
    allowed_pools restricts which pools may be promoted (role law, R17)."""
    urgent, rest = [], []
    for tok in tokens:
        p = ROUTING_TOKEN_POOLS.get(tok, tok)
        if (allowed_pools is None or p in allowed_pools) and burn_down_urgent(p, doc):
            urgent.append(tok)
        else:
            rest.append(tok)
    return urgent + rest


def pool_capability(pool: str, cap: str, model: Optional[str] = None,
                    doc: Optional[Dict[str, Any]] = None) -> Optional[bool]:
    """R32: True/False when declared, None when not verified.
    Model-level `model_capabilities` overrides pool-level `capabilities`."""
    spec = ((doc or load_pools()).get("pools") or {}).get(
        canonical_pool(pool) or pool) or {}
    value: Any = None
    if model:
        mc = (spec.get("model_capabilities") or {}).get(model) or {}
        if isinstance(mc, dict) and cap in mc:
            value = mc.get(cap)
    if value is None:
        pc = spec.get("capabilities") or {}
        if isinstance(pc, dict) and cap in pc:
            value = pc.get(cap)
    if value is True or value is False:
        return value
    return None


def _needs_ok(pool: str, needs: Optional[List[str]], task_class: str,
              doc: Optional[Dict[str, Any]] = None,
              model: Optional[str] = None) -> Tuple[bool, str]:
    """R32 capability filter. glm answers with its vision-capable model."""
    for cap in needs or []:
        selected_model = model
        if (canonical_pool(pool) or pool) == "glm" and selected_model is None:
            selected_model = _glm_models(doc).get("executor") if cap == "vision" else None
        ok = pool_capability(pool, cap, model=selected_model, doc=doc)
        if ok is not True:
            why = "capability_unknown" if ok is None else "capability_absent"
            return False, f"{pool} lacks {cap} ({why}, R32)"
    return True, "ok"


# R24 directional review bans: (reviewer_pool, subject_pool) pairs that are
# forbidden in one direction only. The reverse direction stays lawful.
_DIRECTIONAL_REVIEW_BANS = (("minimax", "glm"),)

# Pool FAMILIES (2026-09-20 round 2, after independent Grok review MAJOR 1).
#
# The round-1 R24 ban compared `canonical_pool()` forms. canonical_pool folds only
# true aliases (qwen -> bailian, case), so `pick review --subject-pool glm-flash
# --pool minimax` answered `REASON=ok` -- the ban bypassed by the very spelling R24
# names. The reviewer proposed `ROUTING_TOKEN_POOLS.get(...)`; measured, that table
# holds only glm-flash, glm-5.3 and bailian-max, so it closes 2 of 6 bypasses and
# leaves glm-5.3-flash, glm-codex, remote-glm and remote-glm-codex open -- which are
# exactly the strings the ledger's task_class already uses. So: canonical alias ->
# routing token -> family fold, in that order.
_POOL_FAMILIES = ("minimax", "glm", "bailian", "grok", "cursor", "go", "claude")
# The incumbent Go remote capability is deliberately short-lived: child <=240s,
# capability <=300s. Do not weaken that security boundary merely to make long
# workers fit it. Classified long work must stay on long-runtime-capable pools.
_GO_SHORT_CAPABILITY_BLOCKED_COMPLEXITIES = frozenset({
    "C2_COMPLEX_BOUNDED",
    "C3_FRONTIER_JUDGMENT",
})


def pool_family(name: Optional[str]) -> str:
    """Fold an engine/model/host spelling down to its pool family.

    glm-flash / glm-5.3-flash / glm-codex / remote-glm-codex -> glm,
    minimax-codex / remote-minimax -> minimax, qwen -> bailian, go-codex -> go.
    An unknown name returns its canonical form UNCHANGED, never guessed into a
    family, so a pool nobody has declared cannot be swallowed by an existing ban.
    """
    raw = (canonical_pool(name) or name or "").strip().lower()
    if not raw:
        return ""
    raw = ROUTING_TOKEN_POOLS.get(raw, raw)
    stem = raw[len("remote-"):] if raw.startswith("remote-") else raw
    if stem == "cursor-grok-4.6-high":
        return "grok"
    for fam in _POOL_FAMILIES:
        if stem == fam or stem.startswith(fam + "-"):
            return fam
    return raw


def _subject_ok(pool: str, task_class: str, subject_pool: Optional[str],
                doc: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """R33 reviewer-not-author for review/audit/verify picks."""
    # MiniMax is an executor-only lane; generic review without an actual
    # subject/provider identity cannot establish reviewer independence.
    # Keep the existing R24-approved explicit cross-provider review paths.
    if (task_class.lower() == "review"
            and pool_family(pool) == "minimax"
            and not subject_pool
            and _routing(doc).get("minimax_review_subject_required", True) is True):
        return False, "minimax review requires subject_pool (R20/R23/R33)"
    if not subject_pool:
        return True, "ok"
    if not bool(_routing(doc).get("reviewer_not_author", True)):
        return True, "ok"
    if task_class.lower() not in REVIEW_CLASSES_R33:
        return True, "ok"
    rev = pool_family(pool)
    subj = pool_family(subject_pool)
    if rev == subj:
        return False, f"{pool} authored the subject; reviewer must differ (R33/R20)"
    # R24 is DIRECTIONAL and not covered by the symmetric R33 rule above:
    # "GLM-flash may review MiniMax output (different provider); MiniMax never
    # reviews GLM."  Before 2026-09-20 `pick review --subject-pool glm` returned
    # minimax, i.e. the tool permitted exactly what the ruling forbids, and even
    # `--pool minimax` answered REASON=ok.  Encoded here so the caller does not
    # have to remember it -- the same rationale R33 itself gives.
    for reviewer, subject in _DIRECTIONAL_REVIEW_BANS:
        if rev == reviewer and subj == subject:
            return False, f"{pool} never reviews {subject_pool} (R24)"
    return True, "ok"


def _grok_exhausted() -> bool:
    return os.path.exists(GROK_EXHAUSTED)


def _bailian_keys_usable() -> List[str]:
    """Return list of usable Bailian key names (not in cooldown, not at cap)."""
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        return bailian_keys.usable_names()
    except Exception:
        return []


def _bailian_total_cap() -> int:
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        return int(bailian_keys.total_cap())
    except Exception:
        return 8


def _bailian_active_count() -> int:
    """Total active bailian slots across all keys."""
    total = 0
    for name in _bailian_keys_usable():
        try:
            sys.path.insert(0, HERE)
            import bailian_keys
            total += bailian_keys.active_count(name)
        except Exception:
            pass
    return total


def _slot_concurrent(pool: str) -> int:
    """Count active slots for pool from slot.py state."""
    if pool == "bailian":
        return _bailian_active_count()
    d = os.path.join(SLOT_ROOT, pool)
    if not os.path.isdir(d):
        return 0
    alive = 0
    for fn in os.listdir(d):
        if not fn.endswith(".lock"):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as fh:
                pid_str = fh.read().strip().split()[0]
                pid = int(pid_str)
            if pid > 0:
                try:
                    os.kill(pid, 0)
                    alive += 1
                except OSError:
                    pass
        except Exception:
            pass
    return alive


def _pool_cap(pool: str, task_class: Optional[str] = None) -> int:
    CAPS = {"minimax": 7, "go": 9}
    if pool in {"grok", "cursor"}:
        # Read-only advisory cap from the existing broker, not a second quota.
        # The broker remains the sole authoritative lease grantor at START.
        try:
            from lease_broker import default_broker
            return max(0, int(default_broker().pool_cap(pool)))
        except Exception:
            return 0
    if pool == "bailian":
        return _bailian_total_cap()
    if pool in {"codex-native", "claude-native"}:
        try:
            from lease_broker import default_broker
            br = default_broker()
            if br.provider(pool).get("enabled") is not True:
                return 0
            snap = br.snapshot()["pools"][pool]
            return max(0, int(snap["cap"]))
        except Exception:
            return 0
    if pool == "glm":
        if not _glm_enabled():
            return 0
        # A model-specific routing hint is not a separate slot pool.
        # The canonical lease broker knows the current shared account budget.
        try:
            from lease_broker import default_broker
            return max(0, int(default_broker().pool_cap("glm")))
        except Exception:
            return 0
    return CAPS.get(pool, 1)


def _glm_broker_model_remaining(model: str) -> Optional[int]:
    """Read current broker room for one concrete GLM model.

    This is advisory pre-selection only. The broker remains the sole grantor and
    rechecks atomically at START. None means the read failed, never invented room.
    """
    model_name = str(model or "").strip().lower()
    if not model_name:
        return None
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        from lease_broker import default_broker
        br = default_broker()
        snap = br.snapshot()
        pool = (snap.get("pools") or {}).get("glm") or {}
        leases = [
            row for row in (snap.get("leases") or [])
            if str(row.get("pool") or "").strip().lower() == "glm"
        ]
        specs = {
            str(acct.get("name") or ""): acct
            for acct in (br.provider("glm").get("accounts") or [])
            if isinstance(acct, dict)
        }
        remaining = 0
        for acct in pool.get("accounts") or []:
            name = str(acct.get("name") or "")
            eff = acct.get("effective_cap")
            held = acct.get("held")
            if (
                not name
                or acct.get("parked") is True
                or isinstance(eff, bool)
                or not isinstance(eff, (int, float))
                or isinstance(held, bool)
                or not isinstance(held, (int, float))
            ):
                continue
            generic_room = max(0, int(eff) - int(held))
            spec = specs.get(name)
            if spec is None:
                continue
            model_cap = br.account_model_cap("glm", spec, model_name)
            if model_cap is None:
                remaining += generic_room
                continue
            held_model = 0
            for row in leases:
                if str(row.get("account") or "") != name:
                    continue
                held_name = str(row.get("model") or "").strip().lower()
                if held_name == model_name or (
                    model_name == "glm-5.3" and held_name == ""
                ):
                    held_model += 1
            remaining += min(
                generic_room,
                max(0, int(model_cap) - held_model),
            )
        return max(0, int(remaining))
    except Exception:
        return None


def _glm_enabled() -> bool:
    """Dynamic GLM enable: pools.yaml true OR (auto + glm_keys.enabled())."""
    spec = (load_pools().get("pools") or {}).get("glm") or {}
    cfg_enabled = spec.get("enabled")
    if cfg_enabled is True:
        return True
    if cfg_enabled == "auto":
        try:
            sys.path.insert(0, HERE)
            import glm_keys  # type: ignore
            return bool(glm_keys.enabled())
        except Exception:
            return False
    return False


def _glm_model() -> str:
    """Return glm_keys.model() when enabled, else the placeholder."""
    if not _glm_enabled():
        return "glm-placeholder"
    try:
        sys.path.insert(0, HERE)
        import glm_keys  # type: ignore
        if glm_keys.enabled():
            return str(glm_keys.model())
    except Exception:
        pass
    return "glm-placeholder"


# ── R24/R24a/R27: per-model GLM routing ──────────────────────────────────────

def _glm_now() -> datetime:
    """Clock for the R27 windows (UTC); tests monkeypatch this."""
    return datetime.now(timezone.utc)


def _parse_hhmm(value: Any) -> int:
    h, _, m = str(value).partition(":")
    return int(h) * 60 + int(m or 0)


def _window_days_allowed(days: Any) -> Optional[set]:
    """Parse 'Mon-Fri' / 'Mon,Wed' into a set of day names; None = any day."""
    day_names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    if not days:
        return None
    allowed: set = set()
    for part in str(days).replace(" ", "").split(","):
        if "-" in part:
            a, _, b = part.partition("-")
            if a in day_names and b in day_names:
                i, j = day_names.index(a), day_names.index(b)
                allowed.update(day_names[i:j + 1] if i <= j else day_names)
        elif part in day_names:
            allowed.add(part)
    return allowed or None


def _in_daily_window(win: Any, now: Optional[datetime] = None) -> bool:
    """True when `now` (UTC, default _glm_now()) is inside {tz, days, start, end}."""
    if not isinstance(win, dict) or not win.get("start") or not win.get("end"):
        return False
    if ZoneInfo is None:
        return False
    try:
        tz = ZoneInfo(str(win.get("tz") or "UTC"))
    except Exception:
        return False
    dt = now or _glm_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)
    allowed = _window_days_allowed(win.get("days"))
    if allowed:
        day_names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        if day_names[local.weekday()] not in allowed:
            return False
    try:
        start = _parse_hhmm(win.get("start"))
        end = _parse_hhmm(win.get("end"))
    except Exception:
        return False
    mins = local.hour * 60 + local.minute
    if start <= end:
        return start <= mins < end
    return mins >= start or mins < end  # window wraps midnight


def _parse_promo_time(value: Any) -> Optional[datetime]:
    """Parse an offset-aware ISO campaign timestamp; malformed policy fails closed."""
    if not value:
        return None
    try:
        text = str(value).strip()
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _glm_credit_promo_policy(
    doc: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Validate the temporary economics policy. Invalid configuration fails closed."""
    promo = _routing(doc).get("glm_credit_promo")
    if not isinstance(promo, dict):
        return None
    start = _parse_promo_time(promo.get("starts_at"))
    end = _parse_promo_time(promo.get("ends_at"))
    raw_models = promo.get("models")
    raw_balance_pools = promo.get("balance_pools")
    if (
        start is None or end is None or end <= start
        or not isinstance(raw_models, list)
        or not isinstance(raw_balance_pools, list)
    ):
        return None
    model_names = [
        str(model).strip() for model in raw_models
        if isinstance(model, str) and str(model).strip()
    ]
    balance_names = [
        str(pool).strip() for pool in raw_balance_pools
        if isinstance(pool, str) and str(pool).strip()
    ]
    if len(model_names) != len(raw_models) or len(balance_names) != len(raw_balance_pools):
        return None
    models = frozenset(model_names)
    configured_models = frozenset(_glm_models(doc).values())
    allowed_balance = frozenset({"minimax", "bailian", "go", "grok", "cursor"})
    balance_families = [pool_family(name) for name in balance_names]
    if (
        not models.issubset(configured_models)
        or any(family not in allowed_balance for family in balance_families)
    ):
        return None
    balance_pools = frozenset(balance_families)
    raw_multiplier = promo.get("credit_multiplier")
    raw_target = promo.get("target_share")
    raw_floor = promo.get("min_non_glm_share", 0.25)
    raw_lookback = promo.get("lookback_launches", 12)
    if (
        isinstance(raw_multiplier, bool)
        or not isinstance(raw_multiplier, (int, float))
        or isinstance(raw_target, bool)
        or not isinstance(raw_target, (int, float))
        or isinstance(raw_floor, bool)
        or not isinstance(raw_floor, (int, float))
        or type(raw_lookback) is not int
    ):
        return None
    multiplier = float(raw_multiplier)
    target = float(raw_target)
    non_glm_floor = float(raw_floor)
    lookback = raw_lookback
    if (
        not models
        or not balance_pools
        or not math.isfinite(multiplier)
        or not 0.0 < multiplier < 1.0
        or not math.isfinite(target)
        or not math.isfinite(non_glm_floor)
        or not 0.0 < target < 1.0
        or not 0.0 <= non_glm_floor < 1.0
        or lookback < 1
    ):
        return None
    lookback = min(100, lookback)
    effective_target = min(target, 1.0 - non_glm_floor)
    if effective_target <= 0.0:
        return None
    return {
        "start": start,
        "end": end,
        "models": models,
        "balance_pools": balance_pools,
        "credit_multiplier": multiplier,
        "target_share": effective_target,
        "min_non_glm_share": non_glm_floor,
        "lookback_launches": lookback,
    }


def glm_credit_promo_active(doc: Optional[Dict[str, Any]] = None) -> bool:
    """True only while a fully valid temporary GLM economics policy is active."""
    policy = _glm_credit_promo_policy(doc)
    if policy is None:
        return False
    now = _glm_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return policy["start"] <= now < policy["end"]


def glm_credit_promo_model_eligible(
    model: Optional[str], doc: Optional[Dict[str, Any]] = None,
) -> bool:
    """A pool is promo-preferred only when its concrete selected model is covered."""
    policy = _glm_credit_promo_policy(doc)
    if policy is None or not glm_credit_promo_active(doc):
        return False
    return bool(model) and str(model) in policy["models"]


def glm_peak_active(
    doc: Optional[Dict[str, Any]] = None, model: Optional[str] = None,
) -> bool:
    """Normal peak pricing, suppressed only for models covered by the all-day promo."""
    if model is not None and glm_credit_promo_model_eligible(model, doc):
        return False
    if model is None and glm_credit_promo_active(doc):
        configured = frozenset(_glm_models(doc).values())
        policy = _glm_credit_promo_policy(doc)
        if configured and policy is not None and configured.issubset(policy["models"]):
            return False
    return _in_daily_window(_routing(doc).get("glm_peak_window"))


def glm_flash_campaign_active(doc: Optional[Dict[str, Any]] = None) -> bool:
    """Flash-only nightly doubled-quota campaign with an absolute expiry."""
    win = _routing(doc).get("glm_flash_campaign")
    if not isinstance(win, dict) or not _in_daily_window(win):
        return False
    end = _parse_promo_time(win.get("ends_at"))
    if end is not None:
        now = _glm_now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now < end
    # Backward-compatible support for the older date-only policy shape.
    until = win.get("until")
    if not until:
        return True
    dt = _glm_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        tz = (ZoneInfo(str(win.get("tz") or "UTC"))
              if ZoneInfo is not None else timezone.utc)
    except Exception:
        tz = timezone.utc
    return dt.astimezone(tz).date().isoformat() < str(until)


def _glm_models(doc: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """pools.yaml pools.glm.models — {operator, reviewer, executor} → model."""
    spec = ((doc or load_pools()).get("pools") or {}).get("glm") or {}
    raw = spec.get("models")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


def _glm_per_model_caps(doc: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """pools.yaml pools.glm.per_model_caps (R24a hints; adaptive 429 governs)."""
    spec = ((doc or load_pools()).get("pools") or {}).get("glm") or {}
    raw = spec.get("per_model_caps")
    if not isinstance(raw, dict):
        return {}
    caps: Dict[str, int] = {}
    for k, v in raw.items():
        try:
            caps[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return caps


def _glm_model_for_class(task_class: Optional[str],
                         doc: Optional[Dict[str, Any]] = None,
                         now: Optional[datetime] = None) -> str:
    """R24 model-by-class: flash for executor classes, glm-5.3 for
    review/operator classes; other classes fall back to glm_keys.model()."""
    tc = (task_class or "").lower().strip()
    if not tc:
        return _glm_model()
    models = _glm_models(doc)
    if not models:
        return _glm_model()
    if (now is not None
            and model_tier.flash_window_active(now)
            and ((task_class or "").lower().strip()
                 in model_tier.FLASH_WINDOW_WIDENED_CLASSES)):
        return models.get("executor") or _glm_model()
    if (now is not None
            and ((task_class or "").lower().strip()
                 in model_tier.FLASH_WINDOW_HELD_CLASSES)):
        return models.get("reviewer") or models.get("operator") or _glm_model()
    if tc in GLM_FULL_CLASSES:
        return models.get("reviewer") or models.get("operator") or _glm_model()
    if tc in GLM_FLASH_CLASSES or model_tier.CLASS_TIER.get(tc) == "leaf-labor":
        return models.get("executor") or _glm_model()
    return _glm_model()


def _glm_labor_class(task_class: Optional[str],
                     doc: Optional[Dict[str, Any]] = None) -> bool:
    """Execute classes minus review/operator classes (R27 demotion scope)."""
    tc = (task_class or "").lower().strip()
    return tc in execute_classes(doc) and tc not in GLM_FULL_CLASSES


def _glm_pick_model(task_class: Optional[str],
                    doc: Optional[Dict[str, Any]] = None,
                    now: Optional[datetime] = None) -> Tuple[str, bool]:
    """Resolve (model, demoted). R27: inside the peak window glm-5.3 is demoted
    to flash for execute classes only; flash and review/operator picks stay."""
    model = _glm_model_for_class(task_class, doc, now)
    if not glm_peak_active(doc, model=model) or not _glm_labor_class(task_class, doc):
        return model, False
    flash = _glm_models(doc).get("executor")
    if flash and model != flash:
        return flash, True
    return model, False


def _parked_bailian_keys() -> set:
    """Keys parked due to high usage."""
    parked = set()
    try:
        with open(BAILIAN_USAGE, encoding="utf-8") as fh:
            data = json.load(fh)
        for name, info in data.get("keys", {}).items():
            if info.get("parked"):
                parked.add(name)
    except Exception:
        pass
    return parked


def _score_pool(pool: str, task_class: str, prefer: Optional[str]) -> float:
    """Compute POOL_LIMITS.md score for a pool given task class."""
    tc = task_class.lower()
    fit_pools = TASK_CLASS_FIT.get(tc, TASK_CLASS_FIT["unknown"])
    if pool not in fit_pools:
        return -999.0

    base = BASE_SCORES.get(pool, {}).get(tc) or BASE_SCORES.get(pool, {}).get("default", 0)

    cap = _pool_cap(pool, task_class)
    concurrent = _slot_concurrent(pool)
    if cap == 0:
        return -999.0
    least_busy = LEAST_BUSY_WEIGHT * (1 - concurrent / cap)

    score = base + least_busy

    # Off-peak amplifier for bailian
    if pool == "bailian" and _is_offpeak():
        score += OFFPEAK_WEIGHT

    # Burn-down urgency for minimax/grok (R31: elapsed-week x unspent-quota)
    if pool in _BURN_DOWN_POOLS_R31:
        if pool in {"minimax", "grok"}:
            pair = _minimax_burn_down_window() if pool == "minimax" else _grok_burn_down_window()
            hrs_to_reset, rem = (168.0, None) if pair is None else pair
        else:
            hrs_to_reset = _hours_to_reset(pool)
            rem = _burn_down_remaining_pct_r31(pool)
        elapsed_frac = max(0.0, 1 - hrs_to_reset / 168)
        remaining_frac = 0.0 if rem is None else max(0.0, min(1.0, rem / 100.0))
        score += BURNDOWN_WEIGHT * elapsed_frac * remaining_frac

    # High-tier grok bonus
    if pool == "grok" and tc == "fix_build":
        score += HIGH_TIER_WEIGHT

    # Prefer override
    if prefer and prefer == pool:
        score += 5

    # Penalise parked bailian keys heavily
    if pool == "bailian":
        parked = _parked_bailian_keys()
        usable = [n for n in _bailian_keys_usable() if n not in parked]
        if not usable:
            return -999.0

    return score


def _bailian_key_name() -> str:
    """Pick the least-loaded usable bailian key name (no value printed)."""
    parked = _parked_bailian_keys()
    try:
        sys.path.insert(0, HERE)
        import bailian_keys
        for name in bailian_keys.usable_names():
            if name in parked:
                continue
            return name
    except Exception:
        pass
    return "-"


def _default_model(pool: str, task_class: Optional[str] = None) -> str:
    if pool == "glm":
        if (task_class or "").strip():
            return _glm_model_for_class(task_class)
        return _glm_model()
    MODELS = {
        "grok":    "grok-4.6",
        "cursor":  "composer-2.5",
        "codex-native": "gpt-6.1-sol",
        "claude-native": "opus",
        "ocfree": "mimo-v2.5-free",
        "bailian": "qwen3.8-flash",
        "minimax": "MiniMax-M3",
        "claude":  "claude-opus-5",
    }
    return MODELS.get(pool, "")


# ── R15 / R17–R23 routing law (from pools.yaml) ───────────────────────────────

def load_pools(path: Optional[str] = None) -> Dict[str, Any]:
    """Load orch/fabric/pools.yaml. Cached. Empty dict if unreadable."""
    global _POOLS_DOC
    if path is None and _POOLS_DOC is not None:
        return _POOLS_DOC
    target = path or POOLS_YAML
    try:
        import yaml  # type: ignore
        with open(target, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except Exception:
        doc = {}
    if path is None:
        _POOLS_DOC = doc
    return doc


def reset_pools_cache() -> None:
    global _POOLS_DOC
    _POOLS_DOC = None


def canonical_pool(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.strip().lower()
    return POOL_ALIASES.get(n, n)


def _routing(doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return (doc or load_pools()).get("routing") or {}


def execute_classes(doc: Optional[Dict[str, Any]] = None) -> frozenset:
    listed = _routing(doc).get("execute_classes")
    return frozenset(listed) if listed else EXECUTE_CLASSES_DEFAULT


def operator_classes(doc: Optional[Dict[str, Any]] = None) -> frozenset:
    listed = _routing(doc).get("operator_classes")
    return frozenset(listed) if listed else OPERATOR_CLASSES_DEFAULT


def seat_classes(doc: Optional[Dict[str, Any]] = None) -> frozenset:
    listed = _routing(doc).get("seat_classes")
    return frozenset(listed) if listed else SEAT_CLASSES_DEFAULT


def is_execute_class(task_class: str, doc: Optional[Dict[str, Any]] = None) -> bool:
    return task_class.lower() in execute_classes(doc)


def is_seat_pool(pool: Optional[str]) -> bool:
    return canonical_pool(pool) in SEAT_POOLS or (pool or "") in SEAT_POOLS


def execute_order(doc: Optional[Dict[str, Any]] = None) -> List[str]:
    listed = _routing(doc).get("execute_order")
    return list(listed) if listed else list(EXECUTE_ORDER_DEFAULT)


def escalation_ladder(doc: Optional[Dict[str, Any]] = None) -> List[str]:
    listed = _routing(doc).get("escalation_ladder")
    return list(listed) if listed else list(ESCALATION_LADDER_DEFAULT)


def judgment_order(doc: Optional[Dict[str, Any]] = None) -> List[str]:
    listed = _routing(doc).get("judgment_order")
    return list(listed) if listed else list(JUDGMENT_ORDER_DEFAULT)


JUDGMENT_CLASSES_R28 = frozenset({
    "operator", "reviewer", "adjudicate", "decompose", "audit", "repair",
    "domain_orchestration",
})
LABOR_CLASSES_R30 = frozenset({
    "executor", "census", "extract", "mechanical",
})


def is_judgment_class(task_class: str,
                      doc: Optional[Dict[str, Any]] = None) -> bool:
    return task_class.lower() in frozenset(JUDGMENT_CLASSES_R28)


def acceptance_floor(doc: Optional[Dict[str, Any]] = None) -> Tuple[float, int, str]:
    """Return (threshold, window, label). Default 0.6 over last 20."""
    raw = _routing(doc).get("acceptance_floor", "0.6 over last 20")
    label = str(raw)
    m = re.search(r"([0-9.]+)\s*over\s*last\s*(\d+)", label, re.I)
    if m:
        return float(m.group(1)), int(m.group(2)), label
    return 0.6, 20, label


def minimax_forbidden(doc: Optional[Dict[str, Any]] = None) -> frozenset:
    pools = (doc or load_pools()).get("pools") or {}
    elig = (pools.get("minimax") or {}).get("eligibility") or {}
    listed = elig.get("forbidden_classes")
    return frozenset(listed) if listed else FORBIDDEN_MINIMAX_DEFAULT


def roles_of(pool: str, doc: Optional[Dict[str, Any]] = None) -> List[str]:
    p = canonical_pool(pool) or pool
    spec = ((doc or load_pools()).get("pools") or {}).get(p) or {}
    role = spec.get("role", [])
    if isinstance(role, str):
        return [role]
    return list(role or [])


def pool_task_classes(pool: str, doc: Optional[Dict[str, Any]] = None) -> List[str]:
    p = canonical_pool(pool) or pool
    spec = ((doc or load_pools()).get("pools") or {}).get(p) or {}
    return list(spec.get("task_classes") or [])


def next_escalate(pool: str, doc: Optional[Dict[str, Any]] = None,
                  model: Optional[str] = None,
                  task_class: Optional[str] = None) -> str:
    """R21/R25: next tier on the escalation ladder for this pick.
    Ladder tokens 'glm-flash' / 'glm-5.3' are printed verbatim (pool glm).
    W4-K2 R24: when the picked pool+model equals the ladder's next token
    (e.g. glm pool with glm-5.3 escalating to glm-5.3), skip to the next
    DISTINCT ladder token — never escalate to itself."""
    ladder = escalation_ladder(doc)
    p = canonical_pool(pool) or (pool or "")
    index_of = {
        "minimax": 0,
        "ocfree": -1,      # escalate to first rung (normally minimax)
        "go": -1,          # paid cheap worker retries start at the labor rung
        "glm": 1,          # glm-flash rung (pool glm + glm-5.3-flash)
        "glm-flash": 1,
        "glm-5.3": 2,
        "bailian": 3,
        "qwen": 3,
        "bailian-max": 3,
        "grok": 4,
        "cursor": 4,
        "claude": 5,
        "fable": 5,
        "claude-fable": 5,
    }.get(p)
    if task_class is not None:
        # A CLI hint must preserve the assignment's class. It is still advisory:
        # callers must run a fresh pick for host, quota and acceptance admission.
        start = index_of + 1 if index_of is not None else len(ladder)
        picked_token = _escalate_picked_token(p, model)
        for token in ladder[start:]:
            candidate = canonical_pool(ROUTING_TOKEN_POOLS.get(token, token))
            if token != picked_token and policy_allows(candidate, task_class, doc)[0]:
                return token
        return ""
    if index_of is None:
        return ladder[-1] if ladder else "fable"
    nxt = index_of + 1
    if nxt >= len(ladder):
        return ladder[-1]
    # W4-K2 R24: never return a ladder token that names the picked pool+model.
    # For pool=glm the ladder token names the model (glm-flash / glm-5.3);
    # for other pools the ladder token names the pool. If the next token
    # would resolve to the same (pool, model) we picked, skip it.
    picked_token = _escalate_picked_token(p, model)
    while nxt < len(ladder) and ladder[nxt] == picked_token:
        nxt += 1
    if nxt >= len(ladder):
        return ladder[-1]
    return ladder[nxt]


def _escalate_picked_token(pool: str, model: Optional[str]) -> str:
    """The ladder token that names the picked (pool, model), used to detect
    a self-escalation. Returns '' when the pick has no ladder token (so the
    next rung is always returned as-is)."""
    if not pool:
        return ""
    if pool == "glm":
        if model in ("glm-5.3", "glm-5.3-flash", "glm-flash"):
            return str(model)
        return ""
    return pool


def _cursor_grok_quota_affinity(model: Optional[str], task_class: str,
                                doc: Optional[Dict[str, Any]] = None) -> bool:
    return (model == "cursor-grok-4.6-high" and _grok_exhausted()
            and policy_allows("grok", task_class, doc)[0])


def policy_allows(pool: str, task_class: str,
                  doc: Optional[Dict[str, Any]] = None,
                  model: Optional[str] = None) -> Tuple[bool, str]:
    """Enforce role/class (R20/R23). One-line reason on refuse."""
    tc = task_class.lower()
    p = canonical_pool(pool) or pool
    # Chairman's quota-only exception follows this exact Grok model's class
    # capability. Composer and ordinary Cursor routes retain R30 unchanged.
    if p == "cursor" and _cursor_grok_quota_affinity(model, tc, doc):
        p = "grok"
    # Hard boundary independent of optional YAML parsing: top-level orchestration
    # remains seat-only, while bounded domain orchestration is restricted to the
    # qualified frontier coordinator families. This does not grant recursive spawn
    # authority; child admission remains an Executive/root-budget concern.
    if tc == "orchestration" and not is_seat_pool(p):
        return False, "orchestration is seat-only; use domain_orchestration for bounded subsystem coordination"
    if tc == "domain_orchestration":
        if p not in {"glm", "grok"}:
            return False, f"{p} is not a domain coordinator pool"
        source = doc or load_pools()
        spec = ((source.get("pools") or {}).get(p) or {}) if isinstance(source, dict) else {}
        allowed_domain = list(spec.get("task_classes") or []) if isinstance(spec, dict) else []
        if tc not in allowed_domain:
            return False, f"{p} domain coordinator policy unavailable or unqualified"
    if p == "cursor" and (is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30):
        return False, "cursor never for labor (R30)"
    if p == "minimax" and tc in minimax_forbidden(doc):
        return False, (
            f"minimax refused for {tc}: labor tier, never judgment (R20)"
        )
    if is_seat_pool(p) and is_execute_class(tc, doc):
        return False, (
            "execute-class refused for pool=claude "
            "(R17/R23: Claude never for mechanical)"
        )
    allowed = pool_task_classes(p, doc)
    if p == "grok" and _grok_priority_active(doc, tc):
        return True, "grok_expiring_priority_class"
    if allowed and tc not in allowed:
        return False, f"{p} role does not allow class={tc} (R23)"
    return True, "ok"


def _ledger_records() -> List[dict]:
    """Best-effort read of ledger.jsonl. Tests monkeypatch this."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import pool_ledger
        return pool_ledger.read_recent(limit=10_000)
    except Exception:
        records = []
        if not os.path.exists(LEDGER_PATH):
            return records
        try:
            with open(LEDGER_PATH, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return records


def _routing_cohort(
    task_class: Optional[str], doc: Optional[Dict[str, Any]] = None,
) -> str:
    """Map a task class to the selector branch whose mix should be balanced."""
    tc = str(task_class or "").strip().lower()
    if not tc:
        return ""
    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:
        return "labor"
    if is_judgment_class(tc, doc):
        return "judgment"
    return ""


def _glm_credit_promo_share(doc: Optional[Dict[str, Any]] = None,
                            task_class: Optional[str] = None
                            ) -> Tuple[int, int, float, float]:
    """Recent realized GLM share for this routing cohort during the promo only.

    The existing launch ledger remains the sole observation source. Outcome rows
    are excluded, duplicate run IDs count once, malformed/future timestamps are
    ignored, and pre-promo history cannot influence the temporary controller.
    """
    policy = _glm_credit_promo_policy(doc)
    cohort = _routing_cohort(task_class, doc)
    if policy is None or not cohort:
        return 0, 0, 0.0, 0.0

    now = _glm_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start_ts = policy["start"].timestamp()
    now_ts = now.timestamp()
    rows: List[Tuple[float, int, dict]] = []
    seen_run_ids: set = set()

    for index, rec in enumerate(_ledger_records()):
        if rec.get("kind") == "outcome":
            continue
        pool = str(rec.get("pool") or "").strip().lower()
        if not pool or pool in {"-", "claude"}:
            continue
        family = pool_family(pool)
        if family == "glm":
            if str(rec.get("model") or "") not in policy["models"]:
                continue
        elif family not in policy["balance_pools"]:
            continue
        cls = str(rec.get("job_class") or rec.get("task_class") or "").strip().lower()
        if _routing_cohort(cls, doc) != cohort:
            continue
        try:
            raw_ts = rec.get("ts")
            if type(raw_ts) is bool:
                continue
            ts = float(raw_ts)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(ts) or ts < start_ts or ts > now_ts:
            continue
        run_id = str(rec.get("run_id") or "").strip()
        if run_id:
            if run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
        rows.append((ts, index, rec))

    rows.sort(key=lambda item: (item[0], item[1]))
    sample = [item[2] for item in rows[-policy["lookback_launches"]:]]
    total = len(sample)
    glm_count = sum(
        1 for rec in sample
        if pool_family(str(rec.get("pool") or "")) == "glm"
        and str(rec.get("model") or "") in policy["models"]
    )
    share = (glm_count / float(total)) if total else 0.0
    return glm_count, total, share, float(policy["target_share"])


def _promo_target_count(total: int, target_share: float) -> int:
    """Nearest discrete GLM count for an observed window; avoids 8/12 -> 9/12 overshoot."""
    if total <= 0:
        return 0
    return max(0, min(total, int(math.floor(target_share * total + 0.5))))


def _promo_balance_glm(tokens: List[str], doc: Optional[Dict[str, Any]] = None,
                       task_class: Optional[str] = None,
                       needs: Optional[List[str]] = None) -> List[str]:
    """Bias toward covered GLM below target; restore a non-GLM lead at/above it."""
    original = list(tokens)
    if not glm_credit_promo_active(doc):
        return original
    model, _suffix = _selection_model("glm", str(task_class or ""), doc, needs)
    if not glm_credit_promo_model_eligible(model, doc):
        return original

    policy = _glm_credit_promo_policy(doc)
    if policy is None:
        return original
    _glm_n, total, share, target = _glm_credit_promo_share(doc, task_class)
    glm_tokens, balance_tokens, fallback_tokens = [], [], []
    for token in original:
        family = pool_family(ROUTING_TOKEN_POOLS.get(token, token))
        if family == "glm":
            glm_tokens.append(token)
        elif family in policy["balance_pools"]:
            balance_tokens.append(token)
        else:
            fallback_tokens.append(token)
    if not glm_tokens or not balance_tokens:
        return original
    desired_glm = _promo_target_count(total, target)
    if total == 0 or _glm_n < desired_glm:
        return glm_tokens + balance_tokens + fallback_tokens
    # At/above the nearest discrete target, use ordinary worker pools to preserve
    # diversity, but keep
    # GLM ahead of scarce native/seat fallbacks that are not diversity targets.
    return balance_tokens + glm_tokens + fallback_tokens


def _glm_burn_snapshot() -> Optional[Dict[str, Any]]:
    """Best-effort R29 meter snapshot; never lets meter I/O break routing."""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import pool_ledger
        return pool_ledger.glm_burn()
    except Exception:
        return None


def _glm_meter_state() -> str:
    burn = _glm_burn_snapshot()
    if burn:
        return str((burn or {}).get("state") or "")
    try:
        import quota_remote
        remote_states = quota_remote.read_provider("glm")
        fresh_remote = any(
            state.source == "PROVIDER_AUTHORITATIVE"
            and quota_remote._age_seconds(state, quota_remote._utc_now().timestamp()) <= quota_remote.FRESH_S
            for state in remote_states
        )
        if fresh_remote:
            decision = quota_remote.glm_quota_decision(read_remote=False)
            return str(decision.get("state") or "")
        raise RuntimeError("no fresh authoritative quota")
    except Exception:
        pass
    burn = _glm_burn_snapshot()
    return str((burn or {}).get("state") or "")


def floor_demotes(pool: str, task_class: str,
                  records: Optional[List[dict]] = None,
                  doc: Optional[Dict[str, Any]] = None,
                  needs: Optional[List[str]] = None,
                  model: Optional[str] = None) -> bool:
    """R22: compare adjudicated quality for the concrete selected model/class.

    Transport failures and absent reviews remain visible in reliability stats,
    but are not evidence of a model quality failure. Unknown historical model
    identity cannot be imputed to the current candidate.
    """
    threshold, window, _label = acceptance_floor(doc)
    recs = records if records is not None else _ledger_records()
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import pool_ledger
        jobs = pool_ledger.outcome_jobs(recs, pool=pool, task_class=task_class)
        resolved_model, _ = _selection_model(
            pool, task_class, doc, needs, model=model
        )
        jobs = [j for j in jobs
                if resolved_model
                and str(j.get("model") or "").casefold() == resolved_model.casefold()
                and (j.get("accepted_by") in pool_ledger.ACCEPTED_BY_OK
                     or j.get("review_rejected") is True
                     or j.get("scope_violation") is True)]
        return pool_ledger.below_acceptance_floor(
            jobs, threshold=threshold, window=window
        )
    except Exception:
        return False


def _selection_model(pool: str, task_class: str,
                     doc: Optional[Dict[str, Any]] = None,
                     needs: Optional[List[str]] = None,
                     model: Optional[str] = None) -> Tuple[str, str]:
    """Resolve once for both quality assessment and emitted selection."""
    suffix = ""
    if pool == "glm":
        resolved_model = str(model or "").strip()
        if not resolved_model:
            resolved_model, demoted = _glm_pick_model(task_class, doc)
        else:
            demoted = False
            model = resolved_model
        if demoted:
            suffix += "+glm_peak_demoted"
        if needs and "vision" in needs and not model:
            flash = _glm_models(doc).get("executor")
            if flash:
                resolved_model = flash
            suffix += "+needs_vision"
        if (glm_flash_campaign_active(doc)
                and resolved_model == _glm_models(doc).get("executor")):
            suffix += "+glm_flash_campaign"
        if glm_credit_promo_model_eligible(resolved_model, doc):
            suffix += "+glm_credit_promo"
        return resolved_model, suffix
    spec = ((doc or load_pools()).get("pools") or {}).get(pool) or {}
    model = (model if pool == "cursor" and model == "cursor-grok-4.6-high" else None) or spec.get("default_model") or _default_model(pool, task_class)
    if pool == "bailian" and task_class.lower() == "review":
        model = spec.get("review_model") or "qwen3.8-max"
    return model, suffix


def _emit(pool: str, reason: str, task_class: str,
          doc: Optional[Dict[str, Any]] = None,
          needs: Optional[List[str]] = None,
          model: Optional[str] = None,
          host_modes: Optional[Dict[str, str]] = None,
          task_complexity: str = "", escalation_reason: str = "") -> str:
    resolved_model, suffix = _selection_model(
        pool, task_class, doc, needs, model=model
    )
    # Reuse the incumbent launch decision for this exact emitted model/mode.
    # Selection is still advisory: the transport rechecks before any effect.
    mode = (host_modes or {}).get(pool) or _HOST_POOL_MODES.get(pool, (pool,))[0]
    guard = launch_policy(mode, task_class, resolved_model, doc=doc,
                          task_complexity=task_complexity,
                          escalation_reason=escalation_reason)
    if not guard.get("allowed"):
        return "NONE reason=" + str(guard.get("reason") or "launch_policy_refused")
    key = _bailian_key_name() if pool == "bailian" else "-"
    reason += suffix
    line = f"POOL={pool} KEY={key} MODEL={resolved_model} REASON={reason}"
    if is_execute_class(task_class, doc):
        escalate = next_escalate(
            pool, doc, model=resolved_model, task_class=task_class
        )
        if escalate:
            line += f" ESCALATE_TO={escalate}"
    return line


def _explain_pick(task_class: str, line: str,
                  doc: Optional[Dict[str, Any]] = None) -> List[str]:
    """Stable reason chain for the R28–R30 class orders."""
    tc = task_class.lower()
    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:
        steps = [
            "1 labor_order=minimax",
            "2 labor_order=glm-5.3-flash",
            "3 labor_order=bailian (window must be open)",
            "4 cursor-never-for-labor",
        ]
    elif is_judgment_class(tc, doc):
        steps = [
            "1 judgment_order=glm-5.3",
            "2 judgment_order=grok (R31a; promoted first when burn-down urgent)",
            "3 judgment_order=cursor (fallback, monthly, no window)",
            "4 judgment_order=fable-placeholder",
        ]
    else:
        steps = [
            "1 unknown class scored by pool eligibility",
            "2 grok unavailable until its 402 marker clears",
        ]
    if _grok_priority_active(doc, tc):
        steps.insert(0, "grok_expiring_priority=first while dated window is live; Ubuntu0..3 only; ordinary gates apply")
    meter = _glm_meter_state()
    if meter:
        steps.append(f"glm_meter_state={meter}")
    if glm_credit_promo_active(doc):
        glm_n, total, share, target = _glm_credit_promo_share(doc, task_class)
        policy = _glm_credit_promo_policy(doc) or {}
        steps.append(
            f"glm_credit_promo=active cohort={_routing_cohort(task_class, doc) or 'none'} "
            f"recent_glm={glm_n}/{total} share={share:.3f} target={target:.3f} "
            f"non_glm_floor={float(policy.get('min_non_glm_share', 0.0)):.3f}"
        )
        promo_model, _promo_suffix = _selection_model("glm", task_class, doc)
        if (
            glm_credit_promo_model_eligible(promo_model, doc)
            and policy_allows("glm", task_class, doc)[0]
            and is_execute_class(task_class, doc)
            and floor_demotes("glm", task_class, doc=doc)
        ):
            _threshold, _window, floor_label = acceptance_floor(doc)
            steps.append(
                f"glm_promo_candidate=blocked_quality model={promo_model} "
                f"acceptance_floor={floor_label}"
            )
    if glm_peak_active(doc):
        steps.append("glm_peak=active")
    if glm_flash_campaign_active(doc):
        steps.append("glm_flash_campaign=active")
    return steps


def hard_filter(pool: str, task_class: str,
                doc: Optional[Dict[str, Any]] = None,
                needs: Optional[List[str]] = None,
                model: Optional[str] = None) -> Tuple[bool, str]:
    """Apply hard filters. Returns (pass, reason).

    GLM selection also observes current broker model room. This is advisory:
    the broker remains the only atomic grantor and rechecks at START.
    """
    try:
        from lease_broker import default_broker
        import quota_circuit
        if quota_circuit.pool_blocked(default_broker(), pool):
            return False, "provider quota cooldown"
    except Exception:
        return False, "provider quota state unavailable"
    if pool in {"codex-native", "claude-native"}:
        try:
            from lease_broker import default_broker
            br = default_broker()
            if br.provider(pool).get("enabled") is not True:
                return False, "native subscription enrollment pending"
            snap = br.snapshot()["pools"][pool]
            if snap["remaining"] < 1:
                return False, "native subscription at shared cap"
        except Exception:
            return False, "native subscription unavailable"
    if pool == "glm":
        if not _glm_enabled():
            return False, "glm disabled (no key)"
        resolved_model, _suffix = _selection_model(
            "glm", task_class, doc, needs, model=model
        )
        remaining = _glm_broker_model_remaining(resolved_model)
        if remaining is not None and remaining < 1:
            return False, f"glm model at broker cap ({resolved_model})"

    if pool == "grok":
        if _grok_exhausted():
            return False, "grok exhausted (GROK_EXHAUSTED marker)"
        cap = _pool_cap(pool)
        if _slot_concurrent(pool) >= cap:
            return False, f"grok at cap {cap}"

    if pool == "cursor":
        if ((is_execute_class(task_class)
                or task_class.lower() in LABOR_CLASSES_R30)
                and not _cursor_grok_quota_affinity(model, task_class, doc)):
            return False, "cursor never for labor (R30)"
        cap = _pool_cap(pool)
        if _slot_concurrent(pool) >= cap:
            return False, f"cursor at cap {cap}"
        # grok_before_cursor: if grok not exhausted and fits, prefer it
        tc = task_class.lower()
        if tc in ("fix_build", "high_level"):
            if not _grok_exhausted() and _slot_concurrent("grok") < _pool_cap("grok"):
                return False, "grok_before_cursor policy"

    if pool == "bailian":
        parked = _parked_bailian_keys()
        usable = [n for n in _bailian_keys_usable() if n not in parked]
        if not usable:
            return False, "all bailian keys parked or at cap"
        cap = _pool_cap("bailian")
        if _slot_concurrent("bailian") >= cap:
            return False, f"bailian at cap {cap}"

    if pool in {"minimax", "go"}:
        cap = _pool_cap(pool)
        if _slot_concurrent(pool) >= cap:
            return False, f"{pool} at cap {cap}"

    return True, "ok"


# Existing remote adapters only; eligibility comes from the shared placement view.
_HOST_POOL_MODES = {
    "go": ("go-codex",), "bailian": ("qwen",), "minimax": ("minimax",),
    "glm": ("glm-codex", "glm"), "cursor": ("cursor",), "grok": ("grok",),
    "codex-native": ("codex-native",), "claude-native": ("claude-native",),
    "ocfree": ("oc-free",),
}


class _HostRoutes(dict):
    """Selection-local diagnostic data; never admission or cached capacity."""
    blockers: tuple[str, ...] = ()


def _eligible_host_routes(host: str, route_key: Optional[str] = None,
                          required_modes: Optional[List[str]] = None,
                          required_platforms: Optional[List[str]] = None,
                          glm_model: Optional[str] = None,
                          qwen_model: Optional[str] = None) -> Dict[str, Tuple[str, str]]:
    # Lazy imports keep unconstrained picks and launch-policy independent of hosts.
    import host_pick
    import placement_view
    from functools import lru_cache

    registry = host_pick.load_registry()
    if not host or (host != "auto" and host not in registry):
        raise ValueError("unknown or empty host")
    now = datetime.now(timezone.utc)
    reader = lru_cache(maxsize=None)(placement_view._default_read_bytes)
    routes = _HostRoutes()
    blocked: dict[str, set[str]] = {}
    excluded = set() if host == "auto" else set(registry) - {host}
    if required_platforms is not None:
        excluded |= {name for name, entry in registry.items()
                     if not isinstance(entry, dict) or entry.get("platform") not in required_platforms}
    for pool, adapters in _HOST_POOL_MODES.items():
        # Chairman placement instruction: Grok workers run only on the four
        # Ubuntu hosts. This restricts selection; all ordinary host gates remain.
        pool_excluded = excluded | (set(registry) - {"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3"}
                                    if pool == "grok" else set())
        for mode in adapters:
            if required_modes is not None and mode not in required_modes:
                continue
            mode_excluded = set(pool_excluded)
            if mode in ("glm", "qwen"):
                provider = "glm" if mode == "glm" else "bailian"
                selected_model = glm_model if mode == "glm" else qwen_model
                # Room is advisory; the broker rechecks this same join at acquire.
                from lease_broker import default_broker
                from glm_host_account_source import filter_observed_accounts
                br = default_broker()
                conn = br._conn()
                try:
                    candidates = []
                    for account in br.grantable_accounts(provider):
                        name = account["name"]
                        cap = br.account_model_cap(provider, account, selected_model or "")
                        if (br._account_held(conn, provider, name) < int(account["_eff_cap"])
                                and (cap is None or br._account_model_held(conn, provider, name, selected_model or "") < cap)):
                            candidates.append(account)
                    for name in registry:
                        ready, _ = filter_observed_accounts(candidates, host=name, model=selected_model,
                            now=now.timestamp(), hosts_path=br.hosts_path,
                            state_dir=host_pick.HOSTS_STATE_DIR, mode=mode)
                        if not ready:
                            mode_excluded.add(name)
                finally:
                    conn.close()
            view = placement_view.build_placement_view(
                registry, host_pick.HOSTS_STATE_DIR, mode, now=now,
                excluded=mode_excluded, plan_path=None, state_reader=reader,
                **({"selection_key": route_key} if host == "auto" and route_key is not None else {}),
            )
            chosen = view.get("host_choice")
            for row in view.get("host_eligibility", {}).get("hosts", []):
                gates = row.get("gates", [])
                # Retired/excluded hosts and unsupported modes are not useful
                # explanations for this request. Preserve every gate decision.
                structural = {"roles", "mode", "excluded"}
                if any(g.get("result") != "PASS" for g in gates
                       if g.get("gate") in structural):
                    continue
                name = row.get("host", "")
                if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
                    continue
                reasons = {("reconciliation-hold" if g.get("gate") == "lane-ceiling"
                            and g.get("detail") == "reconciliation_hold" else g.get("gate", ""))
                           for g in gates if g.get("result") == "FAIL"}
                blocked.setdefault(name, set()).update(
                    reason for reason in reasons if isinstance(reason, str)
                    and re.fullmatch(r"[a-z-]{1,48}", reason))
            if chosen in registry and chosen not in mode_excluded and (host == "auto" or chosen == host):
                routes[pool] = (chosen, mode)
                break
    routes.blockers = tuple(name + ":" + "+".join(sorted(reasons))
                            for name, reasons in sorted(blocked.items()) if reasons)[:16]
    return routes


def format_pick(task_class: str, prefer: Optional[str] = None,
                host: Optional[str] = None, pool: Optional[str] = None,
                needs: Optional[List[str]] = None,
                subject_pool: Optional[str] = None,
                task_complexity: str = "",
                escalation_reason: str = "",
                requested_model: Optional[str] = None,
                route_key: Optional[str] = None,
                required_modes: Optional[List[str]] = None,
                required_platforms: Optional[List[str]] = None) -> str:
    """Select a new request, preserving Grok model affinity on quota exhaustion."""
    if os.environ.get("POOL_OPERATOR_CHILD_BUDGET", "0") != "0":
        # Same model is not the same harness capability. The existing operator
        # grant admits child-launch only on these modes; this can only narrow.
        if required_modes is None:
            required_modes = ["glm", "grok"]
        else:
            known_modes = {mode for modes in _HOST_POOL_MODES.values() for mode in modes}
            # Invalid caller input must keep the existing rejection, never be
            # normalized into validity by this capability intersection.
            if (type(required_modes) is list and 0 < len(required_modes) <= len(known_modes)
                    and all(type(mode) is str and mode in known_modes for mode in required_modes)):
                required_modes = sorted(set(required_modes) & {"glm", "grok"})
    common = dict(prefer=prefer, host=host, needs=needs, subject_pool=subject_pool,
                  task_complexity=task_complexity, escalation_reason=escalation_reason,
                  route_key=route_key, required_modes=required_modes,
                  required_platforms=required_platforms)
    affinity = (requested_model == "grok-4.6" and canonical_pool(pool) in (None, "grok")) or (
        canonical_pool(pool) == "grok" and requested_model is None)
    if not affinity:
        return _format_pick_host(task_class, pool=pool, requested_model=requested_model, **common)
    primary = _format_pick_host(task_class, pool="grok", **common)
    if primary.startswith("POOL=") or not _grok_exhausted():
        return primary
    same = _format_pick_host(task_class, pool="cursor", requested_model="cursor-grok-4.6-high", **common)
    if same.startswith("POOL="):
        return same + " AFFINITY=grok-4.6 QUOTA_FAILOVER=grok-weekly-to-cursor-monthly MODEL_CHANGED=false"
    other = _format_pick_host(task_class, **common)
    if other.startswith("POOL="):
        return other + " AFFINITY=grok-4.6 QUOTA_FAILOVER=grok-exhausted MODEL_CHANGED=true"
    return other


def _format_pick_host(task_class: str, prefer: Optional[str] = None,
                host: Optional[str] = None, pool: Optional[str] = None,
                needs: Optional[List[str]] = None,
                subject_pool: Optional[str] = None,
                task_complexity: str = "",
                escalation_reason: str = "",
                requested_model: Optional[str] = None,
                route_key: Optional[str] = None,
                required_modes: Optional[List[str]] = None,
                required_platforms: Optional[List[str]] = None) -> str:
    """Read-only selection; host name or auto also requires placement eligibility."""
    if required_modes is not None:
        known_modes = {mode for adapters in _HOST_POOL_MODES.values() for mode in adapters}
        if (type(required_modes) is not list or not required_modes
                or len(required_modes) > len(known_modes)
                or any(type(mode) is not str or mode not in known_modes for mode in required_modes)):
            return "NONE reason=invalid required_modes"
        if not host:
            return "NONE reason=required_modes requires host selection"
    if required_platforms is not None:
        if (not host or type(required_platforms) is not list or not required_platforms
                or len(required_platforms) > 2
                or any(type(value) is not str or value not in {"linux", "darwin"} for value in required_platforms)):
            return "NONE reason=invalid required_platforms or host"
    modes = None
    glm_candidate_model = None
    qwen_candidate_model = None
    if host is not None:
        try:
            glm_candidate_model = _selection_model("glm", task_class, load_pools(), needs,
                model=requested_model if requested_model != "cursor-grok-4.6-high" else None)[0]
            qwen_candidate_model = _selection_model("bailian", task_class, load_pools(), needs)[0]
            routes = _eligible_host_routes(
                host, glm_model=glm_candidate_model,
                qwen_model=qwen_candidate_model,
                **({"route_key": route_key} if route_key is not None else {}),
                **({"required_modes": required_modes} if required_modes is not None else {}),
                **({"required_platforms": required_platforms} if required_platforms is not None else {}),
            )
            modes = {pool: route[1] for pool, route in routes.items()}
        except Exception as exc:
            return f"NONE reason=host prerequisite unavailable ({type(exc).__name__})"
        if not modes:
            blockers = getattr(routes, "blockers", ())
            detail = (" blockers=" + ",".join(blockers)) if blockers else ""
            if required_modes is not None:
                return "NONE reason=no eligible remote mode satisfying required_modes" + detail
            return "NONE reason=no eligible remote mode on requested host" + detail
    line = _format_pick(
        task_class, prefer=prefer, pool=pool, needs=needs,
        subject_pool=subject_pool, host_modes=modes,
        task_complexity=task_complexity,
        escalation_reason=escalation_reason, requested_model=requested_model, route_key=route_key,
    )
    if modes is not None and line.startswith("POOL="):
        selected = line.split(" ", 1)[0].removeprefix("POOL=")
        # Defend against a future selection path forgetting the host filter.
        if selected not in modes:
            return "NONE reason=selected pool has no eligible mode on requested host"
        chosen_host, chosen_mode = routes[selected]
        if chosen_mode in ("glm", "qwen"):
            emitted = re.search(r"(?:^| )MODEL=([^ ]+)", line)
            expected = glm_candidate_model if chosen_mode == "glm" else qwen_candidate_model
            if emitted is None or emitted.group(1) != expected:
                return f"NONE reason={chosen_mode} model changed after host account observation"
        if required_modes is not None and chosen_mode not in required_modes:
            return "NONE reason=selected mode does not satisfy required_modes"
        line += f" HOST={chosen_host} MODE={chosen_mode}"
    return line


def _format_pick(task_class: str, prefer: Optional[str] = None,
                 host_modes: Optional[Dict[str, str]] = None, pool: Optional[str] = None,
                 needs: Optional[List[str]] = None,
                 subject_pool: Optional[str] = None,
                 task_complexity: str = "",
                 escalation_reason: str = "",
                 requested_model: Optional[str] = None,
                 route_key: Optional[str] = None) -> str:
    """Return the one-line pick (or NONE). Does not print."""
    tc = (task_class or "unknown").lower().strip()
    doc = load_pools()
    complexity = str(task_complexity or "").strip().upper()
    explicit_model = str(requested_model or "").strip().casefold()
    forced = canonical_pool(pool)
    if complexity and complexity not in TASK_COMPLEXITY_CLASSES:
        return f"NONE reason=unknown_task_complexity ({complexity})"
    # Complexity alone is classification, never permission to upgrade. Only
    # the existing full-GLM C2 build escalation is admitted by this narrow API.
    native_alias = explicit_model == "cursor-grok-4.6-high"
    if native_alias:
        if forced != "cursor":
            return "NONE reason=exact native alias requires cursor pool"
        if not _cursor_grok_quota_affinity(explicit_model, tc, doc):
            return "NONE reason=Cursor Grok alias requires exhausted weekly Grok and eligible Grok task"
        ok, reason = _subject_ok("grok", tc, subject_pool, doc)
        if not ok:
            return f"NONE reason={reason}"
        if is_execute_class(tc, doc) and floor_demotes(
                "grok", tc, doc=doc, needs=needs, model="grok-4.6"):
            return "NONE reason=Grok model quality floor remains binding across products (R22)"
        # This exact high-effort alias was observed in the authenticated Cursor
        # catalog. Capability/host, economic, quality and independence gates
        # below are still required; catalog presence is not worker admission.
    if explicit_model and not native_alias:
        models = {str(value).casefold() for value in _glm_models(doc).values()}
        full = (_glm_models(doc).get("reviewer") or _glm_models(doc).get("operator") or "").casefold()
        if explicit_model not in models:
            return f"NONE reason=unknown requested_model ({explicit_model})"
        effective_pool = ROUTING_TOKEN_POOLS.get(forced, forced)
        if forced and effective_pool != "glm":
            return f"NONE reason=requested_model contradicts pool={pool!r}"
        if tc != "build" or complexity != "C2_COMPLEX_BOUNDED" or explicit_model != full:
            return "NONE reason=requested model/complexity escalation not admitted"
        guard = launch_policy(
            "glm", tc, explicit_model, escalation_reason=escalation_reason,
            doc=doc, task_complexity=complexity,
        )
        if not guard.get("allowed"):
            return f"NONE reason={guard.get('reason') or 'launch_policy_refused'}"
        if glm_peak_active(doc, model=explicit_model) and _glm_labor_class(tc, doc):
            return "NONE reason=explicit model held by GLM peak labor policy"
        forced = "glm"
    if forced:
        forced = ROUTING_TOKEN_POOLS.get(forced, forced)
        if forced not in (doc.get("pools") or {}):
            return f"NONE reason=unknown forced pool={pool!r}"
    prefer_c = canonical_pool(prefer)
    needs = [n.lower().strip() for n in (needs or []) if n and n.strip()]

    if forced:
        if forced == "go" and complexity in _GO_SHORT_CAPABILITY_BLOCKED_COMPLEXITIES:
            return "NONE reason=go_short_capability_only_for_c0_c1"
        if host_modes is not None and forced not in host_modes:
            return f"NONE reason=pool {forced} has no eligible mode on requested host"
        selected_model = (explicit_model or None) if forced == "glm" or native_alias else None
        ok, reason = policy_allows(forced, tc, doc, model=selected_model)
        if not ok:
            return f"NONE reason={reason}"
        ok, reason = _needs_ok(forced, needs, tc, doc, model=selected_model)
        if not ok:
            return f"NONE reason={reason}"
        ok, reason = _subject_ok(forced, tc, subject_pool, doc)
        if not ok:
            return f"NONE reason={reason}"
        if is_execute_class(tc, doc) and floor_demotes(
                forced, tc, doc=doc, needs=needs, model=selected_model):
            _thr, _win, label = acceptance_floor(doc)
            return (
                f"NONE reason={forced} demoted: first_pass_acceptance "
                f"below {label} (R22)"
            )
        ok, reason = hard_filter(forced, tc, doc, needs, model=selected_model)
        if not ok:
            return f"NONE reason={reason}"
        return _emit(
            forced, reason, tc, doc, needs=needs, model=selected_model,
            host_modes=host_modes, task_complexity=complexity, escalation_reason=escalation_reason
        )

    if is_execute_class(tc, doc) or tc in LABOR_CLASSES_R30:
        return _pick_execute(tc, prefer_c, doc, needs=needs, subject_pool=subject_pool, host_modes=host_modes,
                             task_complexity=complexity, escalation_reason=escalation_reason,
                             route_key=route_key)
    if is_judgment_class(tc, doc):
        return _pick_scored(tc, prefer_c, doc, needs=needs, subject_pool=subject_pool, host_modes=host_modes,
                             task_complexity=complexity, escalation_reason=escalation_reason)

    if tc in seat_classes(doc) and tc not in operator_classes(doc):
        return (
            "NONE reason="
            f"{tc} is seat-only (claude-fable Agent tool; R23)"
        )

    return _pick_scored(tc, prefer_c, doc, needs=needs, subject_pool=subject_pool, host_modes=host_modes,
                             task_complexity=complexity, escalation_reason=escalation_reason)



def _minimax_weekly_catchup(doc: Dict[str, Any], task_class: str,
                            task_complexity: str = "", needs: Optional[List[str]] = None,
                            subject_pool: Optional[str] = None,
                            escalation_reason: str = "",
                            routine_bailian: bool = False,
                            prefer: Optional[str] = None) -> bool:
    """Bias simple, underused MiniMax labor; do not override imminent GLM resets.

    This changes ranking only, not provider admission, quality demotion, slots,
    launch permissions or task identity. A stale/unknown provider quota is inert.
    """
    cfg = _routing(doc).get("minimax_weekly_catchup")
    if not isinstance(cfg, dict) or cfg.get("enabled") is not True:
        return False
    allowed = cfg.get("task_classes")
    if (type(allowed) is not list or task_class not in ("mechanical", "census", "extract")
            or task_class not in allowed):
        return False
    if (task_complexity not in ("", "C0_MECHANICAL", "C1_ROUTINE_BOUNDED")
            or needs or subject_pool or escalation_reason or routine_bailian
            or (prefer and prefer != "minimax")):
        return False
    thresholds = [cfg.get("lag_pct_points"), cfg.get("min_remaining_pct"),
                  cfg.get("protect_glm_hours")]
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in thresholds):
        return False
    lag_floor, min_remaining, protect_glm = map(float, thresholds)
    if (not 0 <= lag_floor <= 100 or not 0 <= min_remaining <= 100
            or not 0 <= protect_glm <= 36):
        return False
    pair = _minimax_burn_down_window(doc)
    if pair is None:
        return False
    hours, remaining = pair
    if not 0 < hours <= 168 or not min_remaining <= remaining <= 100:
        return False
    elapsed_pct = 100 * (168.0 - hours) / 168.0
    actual_used_pct = 100.0 - remaining
    if elapsed_pct - actual_used_pct < lag_floor:
        return False
    glm_pair = _glm_burn_down_window(doc)
    if (glm_pair is not None and 0 < glm_pair[0] <= protect_glm
            and glm_pair[1] >= _burn_down_cfg(doc)["min_remaining_pct"]):
        return False
    return True


def _bailian_routine_sample(tc: str, doc: Dict[str, Any], route_key: Optional[str],
                            prefer: Optional[str], needs: Optional[List[str]],
                            subject_pool: Optional[str], task_complexity: str,
                            escalation_reason: str) -> bool:
    """Bounded Qwen exploration for small independent tasks, never extra admission.

    The caller's immutable run identity is hashed, not a per-process counter,
    so concurrent calls do not create a routing state owner or inconsistent
    retries. Every existing quality, capability, provider, and lease gate still
    runs after this advisory ranking. Unknown identity/policy fails closed.
    """
    config = _routing(doc).get("bailian_routine_sampling")
    if type(config) is not dict or config.get("enabled") is not True:
        return False
    classes = config.get("task_classes")
    percent = config.get("percent")
    if (type(classes) is not list or len(classes) > 5
            or any(type(t) is not str for t in classes)
            or type(percent) is not int or not 0 <= percent <= 40):
        return False
    if tc not in classes or tc not in {"mechanical", "census", "extract"}:
        return False
    if (prefer not in (None, "", "bailian") or needs or subject_pool
            or escalation_reason or task_complexity not in
            ("", "C0_MECHANICAL", "C1_ROUTINE_BOUNDED")):
        return False
    if type(route_key) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", route_key):
        return False
    # R31's provider-authoritative near-reset capacity stays ahead of exploratory
    # routing; an absent/stale provider observation never proves urgency.
    if burn_down_urgent("minimax", doc):
        return False
    # Separate independent task identities rather than sending every picker
    # invocation to a preferred provider when the ledger stays unchanged.
    value = int.from_bytes(hashlib.sha256(
        b"mastermind-bailian-routine-v1\0" + route_key.encode("ascii")
    ).digest()[:8], "big") % 10000
    return value < percent * 100


def _cursor_grok_after_quota(tc, *, needs=None, subject_pool=None, host_modes=None,
                             task_complexity="", escalation_reason=""):
    """At a Grok candidate's existing position, try its other paid product.

    The forced route rechecks capability, account capacity, both quality floors,
    reviewer provenance and economics. This is selection before any worker effect.
    """
    if not _grok_exhausted():
        return "NONE reason=weekly Grok not exhausted"
    same = _format_pick(tc, pool="cursor", requested_model="cursor-grok-4.6-high",
        needs=needs, subject_pool=subject_pool, host_modes=host_modes,
        task_complexity=task_complexity, escalation_reason=escalation_reason)
    if same.startswith("POOL="):
        return same + " AFFINITY=grok-4.6 QUOTA_FAILOVER=grok-weekly-to-cursor-monthly MODEL_CHANGED=false"
    return same


EXECUTOR_PROMOTABLE_R31 = frozenset({"minimax", "glm", "bailian"})


def _pick_execute(tc: str, prefer: Optional[str],
                  doc: Dict[str, Any], needs: Optional[List[str]] = None,
                  subject_pool: Optional[str] = None,
                  host_modes: Optional[Dict[str, str]] = None,
                  task_complexity: str = "", escalation_reason: str = "",
                  route_key: Optional[str] = None) -> str:
    """R17/R25 MiniMax-first walk with R22 demotion; R31 promotes urgent
    executor-tier pools only (grok/cursor never ahead of labor pools, R17/R30).
    Tokens resolve to pools: glm-flash → glm (+glm-5.3-flash), bailian-max → bailian."""
    # Temporary economics policy balances the base lawful order first.
    # Canonical burn-down urgency is then applied on top, so the promo can never
    # demote an already-urgent existing quota window.
    order = _promo_balance_glm(execute_order(doc), doc, tc, needs=needs)
    routine_bailian = _bailian_routine_sample(
        tc, doc, route_key, prefer, needs, subject_pool,
        task_complexity, escalation_reason)
    if routine_bailian:
        order = ["bailian"] + [tok for tok in order
                              if ROUTING_TOKEN_POOLS.get(tok, tok) != "bailian"]
    order = _promote_urgent(order, doc, EXECUTOR_PROMOTABLE_R31)
    mini_catchup = _minimax_weekly_catchup(
        doc, tc, task_complexity=task_complexity, needs=needs,
        subject_pool=subject_pool, escalation_reason=escalation_reason,
        routine_bailian=routine_bailian, prefer=prefer,
    )
    if mini_catchup:
        order = ["minimax"] + [tok for tok in order
                               if ROUTING_TOKEN_POOLS.get(tok, tok) != "minimax"]
    if tc in REVIEW_CLASSES_R33 and burn_down_urgent("grok", doc) \
            and policy_allows("grok", tc, doc)[0]:
        # R31: a burn-down-urgent reviewer frontier takes review/audit/verify
        # classes ahead of the executor-tier reviewers (never labor classes).
        order = ["grok"] + [t for t in order if t != "grok"]
    if _grok_priority_active(doc, tc):
        order = ["grok"] + [token for token in order if token != "grok"]
    for token in order:
        p = ROUTING_TOKEN_POOLS.get(token, token)
        if p == "grok":
            same = _cursor_grok_after_quota(tc, needs=needs, subject_pool=subject_pool,
                host_modes=host_modes, task_complexity=task_complexity,
                escalation_reason=escalation_reason)
            if same.startswith("POOL="):
                return same
        if host_modes is not None and p not in host_modes:
            continue
        ok, reason = policy_allows(p, tc, doc)
        if not ok:
            continue
        ok, reason = _needs_ok(p, needs, tc, doc)
        if not ok:
            continue
        ok, reason = _subject_ok(p, tc, subject_pool, doc)
        if not ok:
            continue
        if p == "glm":
            state = _glm_meter_state()
            if state == "PARKED":
                continue
            if state == "SPILL":
                continue
        if floor_demotes(p, tc, doc=doc, needs=needs):
            continue
        ok, reason = hard_filter(p, tc, doc, needs)
        if not ok:
            continue
        why = "minimax_first" if p == "minimax" else f"execute_order_{p}"
        if p == "minimax" and mini_catchup:
            why += "+minimax_weekly_catchup"
        if p == "bailian" and routine_bailian:
            why += "+bounded_routine_sampling"
        if burn_down_urgent(p, doc):
            why = f"{why}+burn_down_urgent"
        if p == "grok" and _grok_priority_active(doc, tc):
            why += "+grok_expiring_priority"
        if prefer == p:
            why = f"{why}+prefer"
        line = _emit(p, why, tc, doc, needs=needs, host_modes=host_modes,
                     task_complexity=task_complexity, escalation_reason=escalation_reason)
        if line.startswith("POOL="):
            return line

    usable = _bailian_keys_usable()
    if (usable and (host_modes is None or "bailian" in host_modes)
            and policy_allows("bailian", tc, doc)[0]
            and _needs_ok("bailian", needs, tc, doc)[0]
            and _subject_ok("bailian", tc, subject_pool, doc)[0]
            and not floor_demotes("bailian", tc, doc=doc, needs=needs)
            and hard_filter("bailian", tc, doc, needs)[0]):
        return _emit("bailian", "fallback_last_resort", tc, doc, needs=needs,
                         host_modes=host_modes, task_complexity=task_complexity, escalation_reason=escalation_reason)
    return "NONE reason=no_pool_available"


def _pick_scored(tc: str, prefer: Optional[str],
                  doc: Dict[str, Any], needs: Optional[List[str]] = None,
                  subject_pool: Optional[str] = None,
                  host_modes: Optional[Dict[str, str]] = None,
                  task_complexity: str = "", escalation_reason: str = "") -> str:
    """R28 judgment classes (R31 promotes urgent operator pools); unknown
    classes retain the scored path."""
    candidates: List[Tuple[float, str, str]] = []
    quota_lines = {}

    if is_judgment_class(tc, doc):
        order = _promo_balance_glm(judgment_order(doc), doc, tc, needs=needs)
        order = _promote_urgent(order, doc)
        if _grok_priority_active(doc, tc):
            order = ["grok"] + [token for token in order if token != "grok"]
        for token in order:
            p = ROUTING_TOKEN_POOLS.get(token, token)
            if p == "grok":
                same = _cursor_grok_after_quota(tc, needs=needs, subject_pool=subject_pool,
                    host_modes=host_modes, task_complexity=task_complexity,
                    escalation_reason=escalation_reason)
                if same.startswith("POOL="):
                    return same
            if host_modes is not None and p not in host_modes:
                continue
            ok, reason = policy_allows(p, tc, doc)
            if not ok:
                continue
            ok, reason = _needs_ok(p, needs, tc, doc)
            if not ok:
                continue
            ok, reason = _subject_ok(p, tc, subject_pool, doc)
            if not ok:
                continue
            ok, reason = hard_filter(p, tc, doc, needs)
            if not ok:
                continue
            if p == "glm":
                state = _glm_meter_state()
                if state == "PARKED":
                    continue
                if state == "SPILL":
                    continue
            why = f"judgment_order_{p}"
            if burn_down_urgent(p, doc):
                why = f"{why}+burn_down_urgent"
            if prefer == p:
                why = f"{why}+prefer"
            line = _emit(p, why, tc, doc, needs=needs, host_modes=host_modes,
                         task_complexity=task_complexity, escalation_reason=escalation_reason)
            if line.startswith("POOL="):
                return line
        return "NONE reason=no_operator_available"

    for pool in ("grok", "cursor", "bailian", "minimax"):
        if pool == "grok":
            same = _cursor_grok_after_quota(tc, needs=needs, subject_pool=subject_pool,
                host_modes=host_modes, task_complexity=task_complexity,
                escalation_reason=escalation_reason)
            if same.startswith("POOL="):
                score = _score_pool("grok", tc, prefer)
                if score >= -900:
                    quota_lines["grok"] = same
                    candidates.append((score, "grok", "quota_same_model"))
                continue
        if host_modes is not None and pool not in host_modes:
            continue
        ok, reason = policy_allows(pool, tc, doc)
        if not ok:
            continue
        ok, reason = _needs_ok(pool, needs, tc, doc)
        if not ok:
            continue
        ok, reason = _subject_ok(pool, tc, subject_pool, doc)
        if not ok:
            continue
        ok, reason = hard_filter(pool, tc, doc, needs)
        if not ok:
            continue
        if pool == "grok" and _grok_priority_active(doc, tc):
            if floor_demotes(pool, tc, doc=doc, needs=needs):
                continue
            line = _emit(pool, "grok_expiring_priority", tc, doc, needs=needs, host_modes=host_modes,
                         task_complexity=task_complexity, escalation_reason=escalation_reason)
            if line.startswith("POOL="):
                return line
        score = _score_pool(pool, tc, prefer)
        if score < -900:
            continue
        candidates.append((score, pool, reason))

    if not candidates:
        if tc in operator_classes(doc) or tc in seat_classes(doc):
            return "NONE reason=no_operator_available"
        usable = _bailian_keys_usable()
        if (usable and (host_modes is None or "bailian" in host_modes)
                and policy_allows("bailian", tc, doc)[0]
                and _needs_ok("bailian", needs, tc, doc)[0]
                and _subject_ok("bailian", tc, subject_pool, doc)[0]
                and hard_filter("bailian", tc, doc, needs)[0]):
            return _emit("bailian", "fallback_last_resort", tc, doc, needs=needs,
                         host_modes=host_modes, task_complexity=task_complexity, escalation_reason=escalation_reason)
        return "NONE reason=no_pool_available"

    candidates.sort(key=lambda x: (-x[0], x[1]))
    for _best_score, best_pool, best_reason in candidates:
        if best_pool in quota_lines:
            return quota_lines[best_pool]
        if burn_down_urgent(best_pool, doc):
            best_reason = f"{best_reason}+burn_down_urgent"
        line = _emit(best_pool, best_reason, tc, doc, needs=needs, host_modes=host_modes,
                     task_complexity=task_complexity, escalation_reason=escalation_reason)
        if line.startswith("POOL="):
            return line
    return "NONE reason=no_pool_available"


TASK_COMPLEXITY_CLASSES = frozenset({
    "C0_MECHANICAL",
    "C1_ROUTINE_BOUNDED",
    "C2_COMPLEX_BOUNDED",
    "C3_FRONTIER_JUDGMENT",
})
BOUNDED_TASK_COMPLEXITIES = frozenset({
    "C0_MECHANICAL",
    "C1_ROUTINE_BOUNDED",
    "C2_COMPLEX_BOUNDED",
})


def _economic_witness(value: str) -> str:
    reason = str(value or "").strip()
    if len(reason) < 12 or reason.lower() in {"yes", "ok", "none"}:
        return ""
    return reason


def launch_policy(mode: str, task_class: str, model: str,
                  escalation_reason: str = "", doc: Optional[Dict[str, Any]] = None,
                  task_complexity: str = "") -> Dict[str, Any]:
    """Return the additive economic decision for a prospective launch.

    This does not replace or grant any role, admission, lease, or availability
    decision: it filters expensive or unclassified models on leaf work.
    """
    normalized_mode = str(mode or "").strip().lower()
    normalized_task = str(task_class or "").strip().lower()
    normalized_complexity = str(task_complexity or "").strip().upper()
    requested_model = str(model or "")
    result = {
        "allowed": True,
        "reason": "outside_economic_guard_scope",
        "task_class": normalized_task,
        "requested_model": requested_model,
        "tier": "",
    }
    if normalized_complexity:
        result["task_complexity"] = normalized_complexity
    if normalized_mode not in {"grok", "cursor", "glm", "glm-codex",
                               "go", "go-codex", "qwen", "bailian", "codex-native", "claude-native", "oc-free"}:
        return result
    if normalized_complexity and normalized_complexity not in TASK_COMPLEXITY_CLASSES:
        result.update(allowed=False, reason="unknown_task_complexity", tier="unknown")
        return result

    policy_doc = load_pools() if doc is None else doc
    executor = str((policy_doc.get("pools") or {}).get(
        "glm", {}).get("models", {}).get("executor", ""))
    normalized_model = requested_model.strip().lower()
    if normalized_mode == "cursor" and normalized_model == "cursor-grok-4.6-high":
        if not _cursor_grok_quota_affinity(normalized_model, normalized_task, policy_doc):
            result.update(allowed=False, reason="cursor_grok_quota_affinity_unproven")
            return result
    # Live OpenCode Go worker rs_ubuntu3_go_minimax27_20261008a settled
    # HTTP 400 ModelProtocolUnsupported. Keep this exact model fail-closed
    # in the existing economic admission path for every task tier.
    if normalized_mode in {"go", "go-codex"} and normalized_model == "minimax-m2.7":
        result.update(allowed=False, reason="model_protocol_unsupported",
                      tier=model_tier.CLASS_TIER.get(normalized_task, "unknown"))
        return result
    # Go's current remote bearer capability is intentionally short-lived
    # (worker <=240s, capability <=300s). Preserve that security boundary:
    # classified long work must use a long-runtime-capable pool rather than
    # weakening Go capability lifetime or timing out after useful labor.
    if (
        normalized_mode in {"go", "go-codex"}
        and normalized_complexity in _GO_SHORT_CAPABILITY_BLOCKED_COMPLEXITIES
    ):
        result.update(
            allowed=False,
            reason="go_short_capability_only_for_c0_c1",
            tier=model_tier.CLASS_TIER.get(normalized_task, "leaf-labor"),
        )
        return result

    # Mixed catalogs are not uniformly cheap. Classify the selected model,
    # never the provider name; this does not grant capability or admission.
    mixed_pool = {"go": "go", "go-codex": "go",
                  "qwen": "bailian", "bailian": "bailian"}.get(normalized_mode)
    if mixed_pool:
        tier = model_tier.CLASS_TIER.get(normalized_task)
        if tier is None:
            result.update(allowed=False, reason="unknown_task_class", tier="unknown")
            return result
        models = ((policy_doc.get("pools") or {}).get(mixed_pool) or {}).get(
            "worker_models", [])
        if isinstance(models, list) and normalized_model and normalized_model in {
                m.strip().lower() for m in models if isinstance(m, str) and m.strip()}:
            result.update(reason="registered_cheap_worker_model", tier=tier)
            return result

    if normalized_mode == "oc-free":
        models = {"mimo-v2.5-free", "mimo-v2.6-flash-free", "ling-3.0-flash-fin-free"}
        result.update(allowed=normalized_model in models, reason="registered_free_model" if normalized_model in models else "unregistered_free_model")
        return result

    is_glm_mode = normalized_mode in {"glm", "glm-codex"}
    if is_glm_mode and not normalized_model:
        if normalized_complexity in BOUNDED_TASK_COMPLEXITIES:
            resolved_model = executor
        elif normalized_complexity == "C3_FRONTIER_JUDGMENT":
            resolved_model = model_tier.FRONTIER_MODEL
        else:
            resolved = model_tier.resolve(normalized_task)
            resolved_model = str(resolved.get("model") or "").strip()
            if not resolved_model:
                result.update(
                    allowed=False,
                    reason="task_class_has_no_glm_model",
                    requested_model="",
                    tier=str(resolved.get("tier") or ""),
                )
                return result
        requested_model = resolved_model
        normalized_model = resolved_model.lower()
        result["requested_model"] = requested_model
    is_cheap_glm = (
        is_glm_mode and requested_model
        and normalized_model == executor.strip().lower()
    )
    if is_cheap_glm:
        cheap = {
            "allowed": True,
            "reason": "cheap_glm_executor",
            "task_class": normalized_task,
            "requested_model": requested_model,
            "tier": "leaf-labor",
        }
        if normalized_complexity:
            cheap["task_complexity"] = normalized_complexity
        return cheap

    witness = _economic_witness(escalation_reason)
    if is_glm_mode and normalized_complexity in BOUNDED_TASK_COMPLEXITIES:
        result["tier"] = model_tier.CLASS_TIER.get(normalized_task, "leaf-labor")
        if not witness:
            result.update(
                allowed=False,
                reason="bounded_complexity_requires_escalation",
            )
            return result
        result["reason"] = "bounded_complexity_escalation_recorded"
        return result
    if is_glm_mode and normalized_complexity == "C3_FRONTIER_JUDGMENT":
        result["tier"] = model_tier.CLASS_TIER.get(
            normalized_task, "frontier-labor"
        )
        if not witness:
            result.update(allowed=False, reason="frontier_witness_required")
            return result
        result["reason"] = "frontier_witness_recorded"
        return result

    if (normalized_mode == "grok" and normalized_model == "grok-4.6"
            and model_tier.CLASS_TIER.get(normalized_task) == "leaf-labor"
            and _grok_priority_active(policy_doc, normalized_task)):
        result.update(reason="grok_expiring_quota_authorization", tier="leaf-labor")
        return result
    tier = model_tier.CLASS_TIER.get(normalized_task)
    if tier is None:
        result.update(allowed=False, reason="unknown_task_class", tier="unknown")
        return result
    result["tier"] = tier
    if tier != "leaf-labor":
        result["reason"] = "economic_guard_permitted_class"
        return result
    reason = str(escalation_reason or "").strip()
    if len(reason) < 12 or reason.lower() in {"yes", "ok", "none"}:
        result.update(allowed=False, reason="leaf_labor_requires_escalation")
        return result
    result["reason"] = "leaf_labor_escalation_recorded"
    return result


def pick(task_class: str, prefer: Optional[str] = None,
         host: Optional[str] = None, pool: Optional[str] = None,
         explain: bool = False, needs: Optional[List[str]] = None,
         subject_pool: Optional[str] = None,
         task_complexity: str = "",
         escalation_reason: str = "",
         requested_model: Optional[str] = None,
         route_key: Optional[str] = None) -> None:
    """Print one pool line or NONE, optionally followed by the reason chain."""
    doc = load_pools()
    line = format_pick(
        task_class, prefer=prefer, host=host, pool=pool, needs=needs,
        subject_pool=subject_pool, task_complexity=task_complexity,
        escalation_reason=escalation_reason, requested_model=requested_model,
        route_key=route_key,
    )
    print(line)
    if explain:
        print("REASON_CHAIN")
        for reason in _explain_pick(task_class, line, doc):
            print(f"- {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="pool router")
    parser.add_argument("task_class_pos", nargs="*", default=None,
                        help="task-class (positional): high_level|fix_build|review|execute|…")
    parser.add_argument("--task-class", dest="task_class_flag", default=None,
                        help="high_level|fix_build|review|census|audit|orchestration|domain_orchestration|mechanical|unknown|execute|architecture|…")
    parser.add_argument("--prefer", default=None,
                        help="prefer this pool (soft nudge)")
    parser.add_argument("--pool", default=None,
                        help="request this pool (refused if ineligible)")
    parser.add_argument("--host", default=None,
                        help="qualified host name, or auto to select a provider and eligible host; advisory only")
    parser.add_argument("--explain", action="store_true",
                        help="print the routing reason chain after the pick")
    parser.add_argument("--needs", action="append", default=[],
                        help="R32 required capability (repeatable), e.g. --needs vision")
    parser.add_argument("--subject-pool", default=None,
                        help="R33: pool that produced the subject of a review/audit/verify pick")
    parser.add_argument("--task-complexity", default="")
    parser.add_argument("--escalation-reason", default="")
    parser.add_argument("--requested-model", default=None)
    parser.add_argument("--route-key", default=None, help="stable task run id for bounded routine sampling")
    if len(sys.argv) > 1 and sys.argv[1] == "launch-policy":
        launch_parser = argparse.ArgumentParser(prog="pick.py launch-policy")
        launch_parser.add_argument("--mode", required=True)
        launch_parser.add_argument("--class", dest="task_class", required=True)
        launch_parser.add_argument("--model", default="")
        launch_parser.add_argument("--task-complexity", default="")
        launch_parser.add_argument("--escalation-reason", default="")
        return _run_launch_policy_cli(launch_parser.parse_args(sys.argv[2:]))

    args = parser.parse_args()

    positional_words = args.task_class_pos or []
    if positional_words and positional_words[0].lower() == "pick":
        positional_words = positional_words[1:]
    positional = " ".join(positional_words)
    task_class = args.task_class_flag or positional
    if not task_class:
        parser.error("the following arguments are required: task-class (positional or --task-class)")
    pick(
        task_class, prefer=args.prefer, host=args.host, pool=args.pool,
        explain=args.explain, needs=args.needs, subject_pool=args.subject_pool,
        task_complexity=args.task_complexity,
        escalation_reason=args.escalation_reason,
        requested_model=args.requested_model,
        route_key=args.route_key,
    )
    return 0


def _run_launch_policy_cli(args: argparse.Namespace) -> int:
    decision = launch_policy(
        args.mode, args.task_class, args.model,
        escalation_reason=args.escalation_reason,
        task_complexity=args.task_complexity,
    )
    print(json.dumps(decision, separators=(",", ":"), sort_keys=True))
    return 0 if decision["allowed"] else 78


if __name__ == "__main__":
    sys.exit(main())
