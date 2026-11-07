"""Classify a chat observation into one symptom. First match wins."""

from __future__ import annotations

SYMPTOMS = (
    "inactive_tab",
    "crashed",
    "page_unresponsive",
    "free_plan",
    "out_of_credits",
    "hit_limit",
    "could_not_load",
    "maximum_length",
    "connection_interrupted",
    "thinking_failed",
    "error_in_message_stream",
    "message_delivery_timed_out",
    "permission_card",
    "running",
    "idle",
)


def _blob(obs: dict) -> str:
    parts = [
        obs.get("window_title") or "",
        obs.get("page_title") or "",
        obs.get("title") or "",
        obs.get("tail") or "",
        obs.get("plan_badge") or "",
        obs.get("account_badge") or "",
        " ".join(obs.get("flags") or []),
    ]
    return "\n".join(str(p) for p in parts)


def classify(obs: dict) -> str:
    text = _blob(obs)
    low = text.casefold()
    flags = {str(f).upper() for f in (obs.get("flags") or [])}
    title = f"{obs.get('window_title') or ''} {obs.get('page_title') or ''}"
    if "inactive tab" in title.casefold():
        return "inactive_tab"
    if "crashed" in title.casefold():
        return "crashed"
    if "page unresponsive" in low:
        return "page_unresponsive"
    badge = str(obs.get("plan_badge") or "")
    account = str(obs.get("account_badge") or "")
    if badge.casefold() == "free" or account.casefold().endswith(" free") or " free" in f" {account.casefold()} ":
        return "free_plan"
    if "out of credits" in low or "turn on auto-reload" in low or "auto-reload" in low:
        return "out_of_credits"
    if "you've hit your limit" in low or "you have hit your limit" in low:
        return "hit_limit"
    if "could not load" in low or "cannot load this conversation" in low:
        return "could_not_load"
    if "MAXLEN" in flags or "maximum length for this conversation" in low:
        return "maximum_length"
    if "CARD" in flags or obs.get("card_tool") or obs.get("permission_card"):
        return "permission_card"
    if "connection interrupted" in low:
        return "connection_interrupted"
    if "thinking failed" in low:
        return "thinking_failed"
    if "error in message stream" in low or "streaming failed" in low:
        return "error_in_message_stream"
    if "message delivery timed out" in low:
        return "message_delivery_timed_out"
    button = str(obs.get("button") or "")
    if button == "Stop" or button.casefold().startswith("stop"):
        return "running"
    return "idle"
