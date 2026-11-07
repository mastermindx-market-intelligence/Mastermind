#!/usr/bin/env python3
"""Canonical task-class to model-tier mapping for KIT_TIER_B1."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

TIERS = ("adjudicate", "orchestrate", "frontier-labor", "leaf-labor")
FRONTIER_MODEL = "glm-5.3"
LEAF_MODEL = "glm-5.3-flash"
TIER_MODEL = {
    "frontier-labor": FRONTIER_MODEL,
    "leaf-labor": LEAF_MODEL,
    "orchestrate": None,
    "adjudicate": None,
}
TIER_POOL = {
    "frontier-labor": "glm",
    "leaf-labor": "glm",
    "orchestrate": "claude",
    "adjudicate": "claude",
}
DEFAULT_TIER = "leaf-labor"

CLASS_TIER = {
    "review": "frontier-labor",
    "reviewer": "frontier-labor",
    "adversarial-review": "frontier-labor",
    "architecture": "frontier-labor",
    "integration": "frontier-labor",
    "design": "frontier-labor",
    "decompose": "frontier-labor",
    "adjudicate": "frontier-labor",
    "repair": "frontier-labor",
    "high_level": "frontier-labor",
    "operator": "frontier-labor",
    # Bounded selection class; never a grant of recursive authority.
    "domain_orchestration": "frontier-labor",
    "audit": "leaf-labor",
    "hard-debug": "frontier-labor",
    "debug": "frontier-labor",
    "escalation": "frontier-labor",
    "build": "leaf-labor",
    "build-bounded": "leaf-labor",
    "execute": "leaf-labor",
    "executor": "leaf-labor",
    "fix_build": "leaf-labor",
    "fix": "leaf-labor",
    "heal": "leaf-labor",
    "mechanical": "leaf-labor",
    "tests-only-repair": "leaf-labor",
    "fixtures": "leaf-labor",
    "transcription": "leaf-labor",
    "probe": "leaf-labor",
    "probe-matrix": "leaf-labor",
    "census": "leaf-labor",
    "scout": "leaf-labor",
    "pong": "leaf-labor",
    "doc-draft": "leaf-labor",
    "drafting": "leaf-labor",
    "screenshot-verify": "leaf-labor",
    "ui-verify": "leaf-labor",
    "verify": "leaf-labor",
    "extract": "leaf-labor",
    "orchestration": "orchestrate",
    "shepherd": "orchestrate",
    "packet-authoring": "orchestrate",
    "first-pass-adjudication": "orchestrate",
    "ruling": "adjudicate",
    "carrier-post": "adjudicate",
    "release-act": "adjudicate",
    "final-adjudication": "adjudicate",
}

PICK_DIVERGENCE = frozenset()
FLASH_WINDOW_START_TIME = datetime(2026, 9, 3, 15, 0, 0, tzinfo=timezone.utc)
FLASH_WINDOW_END_TIME = datetime(2026, 10, 8, 1, 0, 0, tzinfo=timezone.utc)
FLASH_WINDOW_NIGHTLY_START = 15 * 60 * 60
FLASH_WINDOW_NIGHTLY_END = 1 * 60 * 60
FLASH_WINDOW_WIDENED_CLASSES = frozenset({
    "repair", "debug", "integration", "decompose",
})
FLASH_WINDOW_HELD_CLASSES = frozenset({
    "review", "reviewer", "adversarial-review", "architecture", "design",
    "adjudicate", "high_level", "operator", "hard-debug", "escalation",
})


def _normalize(task_class: str | None) -> str:
    return str(task_class or "").strip().lower()


def flash_window_active(now: datetime) -> bool:
    """Return whether the frozen UTC flash-widening window is active."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("flash window now must be timezone-aware")
    current = now.astimezone(timezone.utc)
    if not FLASH_WINDOW_START_TIME <= current < FLASH_WINDOW_END_TIME:
        return False
    seconds = (
        current.hour * 60 * 60 + current.minute * 60 + current.second
    )
    return seconds >= FLASH_WINDOW_NIGHTLY_START or seconds < FLASH_WINDOW_NIGHTLY_END


def resolve(task_class: str | None, now: datetime | None = None) -> dict:
    """Resolve a task class deterministically using the tier law."""
    normalized = _normalize(task_class)
    tier = CLASS_TIER.get(normalized, DEFAULT_TIER)
    known = normalized in CLASS_TIER
    reason = "classified" if known else "unknown-class-flash-first"
    base_tier = tier
    effective_now = now
    if (
        now is not None
        and base_tier == "frontier-labor"
        and normalized in FLASH_WINDOW_WIDENED_CLASSES
        and flash_window_active(effective_now)
    ):
        tier = "leaf-labor"
        reason = "flash-window-widened"
    return {
        "task_class": normalized,
        "tier": tier,
        "model": TIER_MODEL[tier],
        "pool": TIER_POOL[tier],
        "known": known,
        "base_tier": base_tier,
        "reason": reason,
    }


def escalate(
    task_class: str | None, receipt: str, now: datetime | None = None
) -> dict:
    """Escalate one tier after a required failure receipt."""
    cleaned_receipt = str(receipt or "").strip()
    if not cleaned_receipt:
        raise ValueError("escalation requires a failure receipt")
    current = resolve(task_class, now=now)["tier"]
    if current == "leaf-labor":
        tier = "frontier-labor"
    elif current == "frontier-labor":
        tier = "orchestrate"
    else:
        tier = "adjudicate"
    return {
        "task_class": _normalize(task_class),
        "from_tier": current,
        "tier": tier,
        "model": TIER_MODEL[tier],
        "pool": TIER_POOL[tier],
        "receipt": cleaned_receipt,
        "terminal": tier in ("orchestrate", "adjudicate"),
    }


def _parse_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--at requires an offset or Z")
    return parsed


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: model_tier.py <task_class> [--json] [--now | --at <ISO>]", file=sys.stderr)
        return 2
    has_now = "--now" in argv[1:]
    has_at = "--at" in argv[1:]
    if has_now and has_at:
        print("--now and --at are mutually exclusive", file=sys.stderr)
        return 2
    now = None
    try:
        if has_at:
            at_index = argv.index("--at") + 1
            at_value = argv[at_index] if at_index < len(argv) else ""
            now = _parse_at(at_value)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if has_now:
        now = datetime.now(timezone.utc)
    as_json = "--json" in argv[1:]
    task_class = argv[0]
    result = resolve(task_class, now=now)
    if as_json:
        print(json.dumps(result, separators=(",", ":")))
    else:
        print(result["model"] or result["tier"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
