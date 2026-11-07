"""Read-only comparison of two *same-seat* native Codex quota observations.

This is an evidence projector, not a Capacity candidate, quota ledger, worker
registration, account picker, provider probe, redemption or reset predictor.
Use only sanitized results from the existing admitted native account observer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

SCHEMA = "mastermind.codex_quota_comparison.v1"
_WINDOW_NAMES = ("primary", "secondary")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_LIMIT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_WINDOW_STATES = frozenset({"UNKNOWN", "MISSING", "NOT_APPLICABLE", "INVALID_OR_STALE", "OBSERVED"})
_MAX_GAP_SECONDS = 6 * 60 * 60
_CLOCK_TOLERANCE_SECONDS = 60
_HEADROOM_GAIN_POINTS = 10.0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        num = float(value)
    except (OverflowError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _validated_sample(raw: object) -> dict[str, Any] | None:
    """Validate native-result shape; provenance stays with the existing owner."""
    if (not isinstance(raw, Mapping) or raw.get("state") != "NATIVE_READS_COMPLETED"
            or raw.get("api_fallback") is not False):
        return None
    stop = raw.get("stop")
    identity = raw.get("home_identity")
    account = raw.get("account")
    if not isinstance(stop, Mapping) or stop.get("private_group_empty") is not True:
        return None
    if not isinstance(identity, Mapping) or not isinstance(account, Mapping):
        return None
    account_hash = identity.get("account_id_sha256")
    if not isinstance(account_hash, str) or _HASH.fullmatch(account_hash) is None:
        return None
    if account.get("auth_state") != "MANAGED_CHATGPT_OBSERVED":
        return None
    limit_id = account.get("limit_id")
    if not isinstance(limit_id, str) or _LIMIT_ID.fullmatch(limit_id) is None:
        return None
    plan_type = account.get("plan_type")
    if not isinstance(plan_type, str) or _LIMIT_ID.fullmatch(plan_type) is None:
        return None
    # Business users can share a workspace account ID but have separate
    # included seat allowances. Never compare one member's quota to another.
    user_hash = identity.get("user_id_sha256")
    if user_hash is not None and (
        not isinstance(user_hash, str) or _HASH.fullmatch(user_hash) is None
    ):
        return None
    if "business" in plan_type.lower() and user_hash is None:
        return None
    observed_at = _number(account.get("observed_at_unix"))
    if observed_at is None or observed_at <= 0:
        return None
    windows = account.get("windows")
    states = account.get("window_states")
    if not isinstance(windows, Mapping) or not isinstance(states, Mapping):
        return None
    # Unmodeled quota windows could hold the binding constraint. Never
    # classify a refresh while silently discarding a provider-added window.
    if any(name not in _WINDOW_NAMES for name in windows) or any(
        name not in _WINDOW_NAMES for name in states
    ):
        return None
    checked: dict[str, dict[str, float | int]] = {}
    checked_states: dict[str, str] = {}
    for name in _WINDOW_NAMES:
        state = states.get(name)
        if not isinstance(state, str) or state not in _WINDOW_STATES:
            return None
        checked_states[name] = state
        if state != "OBSERVED":
            if name in windows:
                return None
            continue
        window = windows.get(name)
        if not isinstance(window, Mapping):
            return None
        used = _number(window.get("used_percent"))
        remaining = _number(window.get("remaining_percent"))
        reset_at = window.get("resets_at")
        minutes = window.get("window_minutes")
        if (used is None or remaining is None or not 0 <= used <= 100
                or not 0 <= remaining <= 100 or abs(100 - used - remaining) > 0.001
                or type(reset_at) is not int or reset_at <= observed_at
                or type(minutes) is not int or minutes <= 0):
            return None
        checked[name] = {"used_percent": used, "remaining_percent": remaining,
                         "resets_at": reset_at, "window_minutes": minutes}
    return {"account_hash": account_hash, "user_hash": user_hash,
            "observed_at": observed_at, "limit_id": limit_id,
            "plan_type": plan_type,
            "windows": checked, "window_states": checked_states}


def compare_native_codex_quota(before: object, after: object) -> dict[str, Any]:
    """Compare two observations without combining accounts or authorizing work.

    An early timer move with materially recovered headroom is *candidate*
    evidence of refresh; the cause (promotion, explicit reset, server correction,
    first-request anchoring, etc.) is deliberately unclassified. A changed
    window constraint requires rebaseline; any timer movement updates the
    schedule without proving a promotion. NO_MATERIAL_CHANGE refers only to
    reset anomalies: consumers must still ingest every fresh quota balance.
    """
    result: dict[str, Any] = {
        "schema": SCHEMA, "state": "UNKNOWN", "reason": "UNVERIFIED_OBSERVATIONS",
        "observed_windows": [], "schedule_changed": False,
        "constraint_shape_changed": False,
        "early_refresh_candidate": False, "provider_cause": "UNATTRIBUTED",
        "provenance_verified": False,
        "admission_granted": False, "account_switch_authorized": False,
        "reset_redemption_authorized": False, "schedule_prediction_authorized": False,
    }
    old, new = _validated_sample(before), _validated_sample(after)
    if old is None or new is None:
        return result
    if (old["account_hash"] != new["account_hash"]
            or old["user_hash"] != new["user_hash"]
            or old["limit_id"] != new["limit_id"]):
        result["reason"] = "SUBJECT_OR_LIMIT_MISMATCH"
        return result
    if old["plan_type"] != new["plan_type"]:
        result["reason"] = "ENTITLEMENT_CHANGED"
        return result
    gap = new["observed_at"] - old["observed_at"]
    if gap <= 0:
        result["reason"] = "NONMONOTONIC_OBSERVATION"
        return result
    if gap > _MAX_GAP_SECONDS:
        result["reason"] = "GAP_TOO_LONG_TO_INFER_RESET"
        return result

    old_shape = tuple((name, old["window_states"][name],
                       old["windows"].get(name, {}).get("window_minutes"))
                      for name in _WINDOW_NAMES)
    new_shape = tuple((name, new["window_states"][name],
                       new["windows"].get(name, {}).get("window_minutes"))
                      for name in _WINDOW_NAMES)
    if old_shape != new_shape:
        result["constraint_shape_changed"] = True
        result["reason"] = "WINDOW_CONSTRAINTS_CHANGED"
        return result

    for name in _WINDOW_NAMES:
        previous, current = old["windows"].get(name), new["windows"].get(name)
        if not previous or not current or previous["window_minutes"] != current["window_minutes"]:
            continue
        moved = current["resets_at"] - previous["resets_at"]
        headroom_gained = current["remaining_percent"] - previous["remaining_percent"]
        timer_changed = moved != 0
        if not timer_changed:
            classification = ("HEADROOM_GAIN_WITHOUT_TIMER_PROOF"
                              if headroom_gained >= _HEADROOM_GAIN_POINTS else "NO_TIMER_CHANGE")
        elif abs(moved) <= _CLOCK_TOLERANCE_SECONDS:
            classification = "TIMER_ADJUSTED_WITHIN_TOLERANCE"
        elif new["observed_at"] >= previous["resets_at"]:
            classification = "PRIOR_WINDOW_DUE"
        elif moved > 0 and headroom_gained >= _HEADROOM_GAIN_POINTS:
            classification = "EARLY_REFRESH_CANDIDATE"
        else:
            classification = "TIMER_CHANGED_CAUSE_UNKNOWN"
        result["observed_windows"].append({
            "window": name, "timer_moved_seconds": moved,
            "headroom_delta_points": round(headroom_gained, 3),
            "classification": classification,
        })
        result["schedule_changed"] = result["schedule_changed"] or timer_changed
        result["early_refresh_candidate"] = (
            result["early_refresh_candidate"] or classification == "EARLY_REFRESH_CANDIDATE"
        )

    if not result["observed_windows"]:
        result["reason"] = "NO_COMPARABLE_WINDOWS"
        return result
    result["state"] = ("CHANGE_OBSERVED" if result["schedule_changed"]
                       or any(row["classification"] == "HEADROOM_GAIN_WITHOUT_TIMER_PROOF"
                              for row in result["observed_windows"]) else "NO_MATERIAL_CHANGE")
    result["reason"] = "SAME_SEAT_NATIVE_WINDOW_COMPARISON"
    return result
