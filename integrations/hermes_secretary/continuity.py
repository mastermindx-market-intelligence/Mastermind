"""Codex continuity audit decisions from routine 7. The drift script is not run."""

from __future__ import annotations

from datetime import datetime


_STAMP = "%Y-%m-%dT%H:%M"
_DRIFT_MINUTES = 240


def continuity_action(state: str, *, last_prompt_at: str | None, now: str) -> str:
    if state == "FRESH":
        return "none"
    if state == "STALE":
        return "nudge_refresh"
    if state == "DRIFTING":
        if last_prompt_at is None:
            return "continuity_prompt"
        start = datetime.strptime(last_prompt_at, _STAMP)
        end = datetime.strptime(now, _STAMP)
        elapsed = int((end - start).total_seconds() // 60)
        if elapsed >= _DRIFT_MINUTES:
            return "continuity_prompt"
        return "hold"
    if state == "LOST":
        return "restore_relaunch"
    raise ValueError(f"unknown continuity state {state}")
