"""Codex account switch order from routine 5. No menu bar is read."""

from __future__ import annotations

SWITCH_ORDER = (
    "ChatGPT1",
    "ChatGPT2",
    "ChatGPT2 Business",
    "ChrisWong6031",
    "ChatGPT3",
)
RELOGIN = frozenset({"ChatGPT2", "ChatGPT2 Business", "ChrisWong6031"})
FORBIDDEN = frozenset({"ChatGPT4"})


def _usable(account: dict) -> bool:
    name = account.get("name")
    if name in FORBIDDEN or name not in SWITCH_ORDER:
        return False
    if str(account.get("status")) == "401":
        return False
    return float(account["remaining_pct"]) > 5


def choose_account(accounts: list[dict], *, active: str) -> dict:
    by_name = {item["name"]: item for item in accounts}
    current = by_name.get(active)
    if current is not None and _usable(current):
        return {"action": "hold", "message_chris": False, "target": active, "relogin": False}
    for name in SWITCH_ORDER:
        candidate = by_name.get(name)
        if candidate is not None and _usable(candidate):
            return {
                "action": "switch",
                "message_chris": True,
                "target": name,
                "relogin": name in RELOGIN,
            }
    return {"action": "all_empty", "message_chris": True, "target": None, "relogin": False}


def relaunch_wake_plan(chats: list[dict]) -> list[dict]:
    """After a Codex relaunch, record who would be nudged. Do not send."""

    plan = []
    for chat in chats:
        if chat.get("status") in {"chris_own", "do_not_steer"}:
            plan.append({**chat, "action": "exclude"})
            continue
        if chat.get("tier") == "pro" and chat.get("state") == "running":
            plan.append({**chat, "action": "leave_running_pro"})
            continue
        if chat.get("pinned") or chat.get("parked"):
            plan.append({**chat, "action": "would_paste_nudge"})
            continue
        plan.append({**chat, "action": "leave"})
    return plan
