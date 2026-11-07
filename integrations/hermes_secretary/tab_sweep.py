"""Tab-sweep plan from routine 6. No AppleScript or window manager is invoked."""

from __future__ import annotations

from urllib.parse import urlsplit

_CLOSE_OTHER = frozenset({"KRIS KE", "Y7"})


def _is_chatgpt_url(value: object) -> bool:
    """Select the real supported origin, never a hostname in path/query/userinfo."""
    if not isinstance(value, str) or any(ord(ch) <= 32 or ord(ch) == 127 for ch in value):
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme in {"http", "https"}
                and parsed.hostname == "chatgpt.com"
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 80 if parsed.scheme == "http" else 443))
    except (TypeError, ValueError):
        return False


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
    chatgpt = [tab for tab in tabs if _is_chatgpt_url(tab["url"])]
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
