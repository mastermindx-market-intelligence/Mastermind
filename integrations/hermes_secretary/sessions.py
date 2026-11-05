"""ChatGPT browser-session decisions from routine 4. No browser is driven."""

from __future__ import annotations

from datetime import datetime


_STAMP = "%Y-%m-%dT%H:%M"


def _minutes(earlier: str, later: str) -> int:
    start = datetime.strptime(earlier, _STAMP)
    end = datetime.strptime(later, _STAMP)
    return int((end - start).total_seconds() // 60)


def decide_session(entry: dict, *, now: str) -> dict:
    status = entry["status"]
    base = {
        "id": entry["id"],
        "retry": False,
        "handoff": None,
        "refusal_text": entry.get("refusal_text"),
    }
    if status == "chris_own":
        return {**base, "action": "exclude_chris_own"}
    if status == "do_not_steer":
        return {**base, "action": "exclude_do_not_steer"}
    if status == "refusal" or entry.get("refusal_text"):
        handoff = None if entry.get("handed_off") else "ACTION_NEEDED_RETURN"
        return {**base, "action": "hold_refusal", "handoff": handoff, "retry": False}
    if status == "running":
        return {**base, "action": "leave_running"}
    if entry.get("waiting_on") in {"ci", "review"}:
        return {**base, "action": "leave_waiting"}
    if status == "finished":
        return {**base, "action": "extract_finished", "handoff": "ACTION_NEEDED_RETURN", "state": "returned_pending"}
    if status == "stalled":
        last = entry.get("last_recovery_at")
        if last is None or _minutes(last, now) >= 30:
            return {**base, "action": "recover_once"}
        return {**base, "action": "hold_stall_cooldown"}
    if status == "aging":
        tier = entry["tier"]
        age = float(entry["age_hours"])
        past = (tier == "extra_high" and age >= 2) or (tier == "pro" and age >= 6)
        if past:
            return {**base, "action": "age_out", "handoff": "ACTION_NEEDED_RETURN", "state": "stalled_pending"}
        return {**base, "action": "leave_aging"}
    return {**base, "action": "leave"}


def service_sessions(entries: list[dict], *, now: str, limit: int = 6) -> list[dict]:
    """Service the oldest-checked entries, six per run, registry order only."""

    ordered = sorted(entries, key=lambda item: item["checked_at"])[:limit]
    return [decide_session(item, now=now) for item in ordered]
