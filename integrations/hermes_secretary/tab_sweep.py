"""Tab-sweep plan from routine 6. No AppleScript or window manager is invoked."""

from __future__ import annotations

_CLOSE_OTHER = frozenset({"KRIS KE", "Y7"})


def plan_tabs(profile: dict) -> dict:
    name = profile["name"]
    if profile.get("debugging_banner"):
        return {
            "profile": name,
            "action": "skip",
            "reason": "debugging_banner",
            "keep": [],
            "close": [],
            "method": None,
        }
    tabs = profile["tabs"]
    keep: set[int] = set()
    chatgpt = [tab for tab in tabs if "chatgpt.com" in tab["url"]]
    if chatgpt:
        keep.add(chatgpt[0]["index"])
    for tab in tabs:
        url = tab["url"].lower()
        title = str(tab.get("title", "")).lower()
        if "tencent" in url or "tencent" in title:
            keep.add(tab["index"])
        if any(token in url for token in ("/login", "signin", "sign-in", "mid-login")) or "sign in" in title:
            keep.add(tab["index"])
    close = [tab["index"] for tab in tabs if tab["index"] not in keep]
    method = "close_other_tabs" if name in _CLOSE_OTHER else "sweeptabs.scpt"
    return {
        "profile": name,
        "action": "sweep",
        "reason": None,
        "keep": sorted(keep),
        "close": close,
        "method": method,
    }
