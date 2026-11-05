"""Hard rules for the ChatGPT session watcher.

Deterministic policy. A model may draft a sentence; it cannot widen these rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

PRO_COOLOFF = timedelta(minutes=30)
MAX_PRO_PER_MULTILOGIN = 5
TARGET_ACTIVE_MIN = 7
TARGET_ACTIVE_MAX = 11
LIMIT_RETRY_AFTER = timedelta(hours=1)

# GitHub writes are Allow once, and only after See details matches the tool.
# Merge, approve, label, enqueue, Ready, credits and auto-reload are refused.
GITHUB_WRITE_MARKERS = (
    "commit",
    "push",
    "create tree",
    "update file",
    "delete file",
    "create pull",
    "pull request",
    "issue comment",
    "upload",
    "write file",
    "github",
)
DENY_TOOL_MARKERS = (
    "merge",
    "approve",
    "label",
    "enqueue",
    "ready for review",
    "mark ready",
    "auto-reload",
    "auto reload",
    "add credit",
    "buy credit",
    "turn on auto-reload",
)
CARD_CHOICES = ("allow_once", "allow_conversation", "always_allow", "deny", "see_details")

HOLD_STATUSES = frozenset({"HOLD", "leave_alone", "personal"})
ARCHIVED_STATUSES = frozenset({"archived", "superseded"})
CHRIS_OWN_STATUSES = frozenset({"chris_own"})

_SECRET = re.compile(
    r"(?i)(sk-[A-Za-z0-9_\-]{12,}|api[_-]?key\s*[:=]\s*\S+|bearer\s+[A-Za-z0-9._\-]{12,})"
)
_MARATHON = re.compile(
    r"(?i)\b(marathon|don'?t stop|do not stop|scarce turns?|turns are scarce|60-100)\b"
)
_FORBIDDEN_REPLY = re.compile(
    r"(?i)\b(merge|approve|enqueue|self-review|self review|mark it ready|ready for review|label this)\b"
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class PolicyRefusal(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Account:
    profile: str
    account: str
    surface: str  # multilogin | chrome
    tier: str  # personal_pro | business
    tokens: frozenset

    def matches(self, badge: str) -> bool:
        if not badge or not badge.strip():
            return True
        return _norm(badge) in self.tokens


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def _acc(profile: str, account: str, surface: str, tier: str, extra: Iterable[str] = ()) -> Account:
    tokens = {_norm(profile), _norm(account), *(_norm(x) for x in extra)}
    return Account(profile, account, surface, tier, frozenset(tokens))


ACCOUNTS: tuple[Account, ...] = (
    _acc("ModernLuxe", "ChatGPT1", "multilogin", "personal_pro", ("ChatGPT 1",)),
    _acc("KRIS KE", "ChatGPT2", "multilogin", "personal_pro", ("ChatGPT 2", "Kris Ke")),
    _acc("Y7", "ChatGPT3", "multilogin", "personal_pro", ("ChatGPT 3",)),
    _acc("FashionBird", "ChatGPT4", "multilogin", "personal_pro", ("Fashionbird", "ChatGPT 4")),
    _acc("Chris-Dot", "Chris business", "chrome", "business", ("chrome:Chris", "Chris-Dot")),
    _acc("Ryan-Dot", "Ryan business", "chrome", "business", ("chrome:Ryan", "Ryan-Dot")),
)

_BY_TOKEN: dict[str, Account] = {}
for _account in ACCOUNTS:
    for _token in _account.tokens:
        _BY_TOKEN.setdefault(_token, _account)

PROFILE_ALIASES = {
    "fashionbird": "FashionBird",
    "chatgpt4": "FashionBird",
    "chatgpt2": "KRIS KE",
    "chatgpt3": "Y7",
    "chatgpt1": "ModernLuxe",
    "chrome:chris": "Chris-Dot",
    "chrome:ryan": "Ryan-Dot",
    "chris business": "Chris-Dot",
    "ryan business": "Ryan-Dot",
    "kris ke": "KRIS KE",
    "y7 elevate retail": "Y7",
}


def canonical_profile(name: str) -> str | None:
    if not name:
        return None
    key = _norm(name)
    if key in PROFILE_ALIASES:
        return PROFILE_ALIASES[key]
    for account in ACCOUNTS:
        if key == _norm(account.profile) or key == _norm(account.account):
            return account.profile
    return None


def account_for(profile: str) -> Account | None:
    canon = canonical_profile(profile) or profile
    for account in ACCOUNTS:
        if account.profile == canon:
            return account
    return None


def other_account(badge: str, expected: Account) -> Account | None:
    """An in-scope account that is not the window's account, if the badge names one."""
    if not badge or expected.matches(badge):
        return None
    found = _BY_TOKEN.get(_norm(badge))
    if found is None or found.profile == expected.profile:
        return None
    return found


def redact(text: str) -> str:
    if not text:
        return ""
    return _SECRET.sub("[redacted]", text)


def redact_obj(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    return value


def is_flovia(entry: dict | None, obs: dict | None = None) -> bool:
    blob = " ".join(
        str((entry or {}).get(k) or "")
        for k in ("title", "project", "kind", "notes", "status")
    )
    blob += " " + " ".join(
        str((obs or {}).get(k) or "") for k in ("title", "project", "kind", "tail")
    )
    if "flovia" in blob.casefold():
        return True
    status = str((entry or {}).get("status") or "").casefold()
    return status == "personal" or str((entry or {}).get("kind") or "").casefold() == "personal"


def is_chris_own(entry: dict | None) -> bool:
    if not entry:
        return False
    status = str(entry.get("status") or "")
    kind = str(entry.get("kind") or "")
    return status in CHRIS_OWN_STATUSES or kind == "chris_own" or bool(entry.get("chris_own"))


def is_held(entry: dict | None) -> str | None:
    if not entry:
        return None
    if entry.get("do_not_steer") is True:
        return "do_not_steer"
    status = str(entry.get("status") or "")
    if status in HOLD_STATUSES or status == "HOLD":
        return "do_not_steer"
    return None


def is_github_write(tool: str) -> bool:
    name = _norm(tool)
    if not name:
        return False
    if any(marker in name for marker in DENY_TOOL_MARKERS):
        return False
    return any(marker in name for marker in GITHUB_WRITE_MARKERS)


def is_denied_tool(tool: str) -> bool:
    name = _norm(tool)
    return any(marker in name for marker in DENY_TOOL_MARKERS)


def details_match(tool: str, details: str | None) -> bool:
    if not tool or not details:
        return False
    return _norm(tool) in _norm(details) or _norm(details) in _norm(tool)


def card_choice(obs: dict) -> tuple[str, str]:
    """Return (choice, reason). Never Escape. Escape denies a card."""
    tool = str(obs.get("card_tool") or "")
    if is_denied_tool(tool):
        return "deny", "denied_tool"
    if is_github_write(tool):
        details = obs.get("see_details")
        if not details:
            return "see_details", "github_write_needs_details"
        if not details_match(tool, str(details)):
            return "hold", "see_details_mismatch"
        return "allow_once", "github_write_allow_once"
    choices = [_norm(c) for c in (obs.get("card_choices") or [])]
    if not choices or any("this conversation" in c for c in choices):
        return "allow_conversation", "allow_for_conversation"
    if any(c == "always allow" or c.startswith("always allow") for c in choices):
        return "always_allow", "always_allow_accepted"
    if any("allow once" in c or c == "allow" for c in choices):
        return "allow_once", "allow_once_fallback"
    return "hold", "no_safe_card_choice"


def sentence_count(text: str) -> int:
    parts = [p for p in _SENTENCE_SPLIT.split((text or "").strip()) if p.strip()]
    return len(parts)


def reply_ok(text: str) -> bool:
    body = (text or "").strip()
    if not body or sentence_count(body) < 1 or sentence_count(body) > 3:
        return False
    if len(body) > 500:
        return False
    if _MARATHON.search(body) or _FORBIDDEN_REPLY.search(body):
        return False
    if body != redact(body):
        return False
    return True


def parse_stamp(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace(" ", "T", 1)
    # Drop a trailing zone-less note such as " (observed...)".
    text = text.split(" (", 1)[0].strip()
    # 2026-11-04T17:50:00-0700 -> -07:00
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PT)
    return parsed


def stamp_sort_key(value: str | None) -> str:
    parsed = parse_stamp(value)
    if parsed is None:
        return ""
    return parsed.astimezone(PT).strftime("%Y-%m-%dT%H:%M")


def cooloff_active(entry: dict | None, now: datetime, mode: str) -> bool:
    if (mode or "") != "Pro":
        return False
    last = parse_stamp((entry or {}).get("last_nudge_pt"))
    if last is None or now.tzinfo is None:
        return False
    return now - last < PRO_COOLOFF


def next_numbered_title(title: str) -> str:
    text = (title or "Recovered session").strip()
    match = re.search(r"^(.*?)(?:\s+(\d+))?$", text)
    stem = (match.group(1) or text).strip()
    if match and match.group(2):
        return f"{stem} {int(match.group(2)) + 1}"
    return f"{stem} 2"


def human_is_active(idle_seconds: float, seconds_since_own_input: float | None) -> bool:
    """True when a person, not our own last synthetic input, is using the Mac.

    Idle time shorter than the time since our own input means someone else
    reset the HID counter. Our own input does not count as the user.
    """
    if seconds_since_own_input is None:
        return idle_seconds < 4
    if idle_seconds + 1 >= seconds_since_own_input:
        return False
    return idle_seconds < 4


def assert_safe_argv(argv: list[str]) -> None:
    """Refuse process listings that print full command lines (they can carry a key)."""
    if any(part in {"-f", "-a", "-af", "-fa"} for part in argv) and "pgrep" in argv:
        raise PolicyRefusal("process_listing_leaks_secrets")
    if "ps" in argv and any(part in {"aux", "-f", "-a", "-af", "-fa", "command="} for part in argv):
        raise PolicyRefusal("process_listing_leaks_secrets")
    if any("command=" in part for part in argv):
        raise PolicyRefusal("process_listing_leaks_secrets")
    for part in argv:
        if "chatgpt.com/c/" in part or part.startswith("http://") or part.startswith("https://"):
            raise PolicyRefusal("no_chat_url_navigation")
        if "keystroke" in part or part in {"type", "typist"}:
            raise PolicyRefusal("paste_never_type")
