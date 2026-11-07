"""Commission, placement, BLOCKED, and owed-return detection.

Dedup key is ``channel:ts``. Only this agent's own bot user id is a self
loop. Grok Secretary is a peer: its posts are read, and its assignments and
receipts become decisions. Other seats stay quiet.
"""

from __future__ import annotations

import re
from typing import Iterable

from constants import SHADOW_SCHEMA
from roster import Roster, agent_dispatch_id, channel_names, returns_channel_id
from wake_bridge import annotate

_TS = re.compile(r"^[1-9][0-9]{9,15}\.[0-9]{6}$")
_USER = re.compile(r"^U[A-Z0-9]{6,32}$")
_CHANNEL = re.compile(r"^[CG][A-Z0-9]{8,31}$")
_TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,80}")
_OP = re.compile(
    r"(?i)\b(?:operation[_\s-]?id|op)\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9._:-]{0,80})"
)
_LIMITS = re.compile(r"(?i)\blimits?\s*[:=]\s*([^\n]+)")
_ACK = re.compile(r"(?i)\bACK\b")
_RECEIPT = re.compile(r"(?i)\b(?:ACK|RECEIPT|PICKUP|RESULT)\b")
_SECRET = re.compile(
    r"(xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9]|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:api[_-]?key|password|token)\s*[:=]\s*\S+)"
)
_STATUS = re.compile(r"(?i)status-only|status_only|watcher update")
_EXTRA_TOKENS = (
    "DECISION_REQUEST",
    "HOLD-FOR-SOL",
    "WATCH_UNAVAILABLE",
    "OPEN COMMISSION",
    "DIRECT_TARGETED",
    "DIRECT TARGET",
)


def contains_secret(text: str) -> bool:
    return _SECRET.search(text) is not None


def addressed_to_secretary(text: str, addressed_user_id: str) -> bool:
    if addressed_user_id and f"<@{addressed_user_id}>" in text:
        return True
    if re.search(r"(?i)\bto:\s*grok secretary\b", text):
        return True
    if re.search(r"(?i)\bdirect[_\s]targeted\b", text):
        return True
    if re.search(r"(?i)\bdirect target\b", text):
        return True
    if re.search(r"(?i)\bmeta-ceo assignments?\b", text):
        return True
    return False


def needs_placement(text: str) -> bool:
    return any(
        re.search(pattern, text) is not None
        for pattern in (
            r"(?i)\bWAITING_CAPACITY\b",
            r"(?i)\bneeds_placement\b",
            r"(?i)\bPENDING_PICKUP\b",
        )
    )


def real_blocked(text: str) -> bool:
    for match in re.finditer(r"(?<![A-Za-z])BLOCKED(?![A-Za-z])", text, flags=re.IGNORECASE):
        prefix = text[max(0, match.start() - 4) : match.start()]
        if prefix.lower().endswith("not ") or prefix.lower().endswith("un"):
            continue
        return True
    return False


def status_only(text: str) -> bool:
    if _STATUS.search(text) is None:
        return False
    if real_blocked(text):
        return False
    upper = text.upper()
    return not any(token.upper() in upper for token in _EXTRA_TOKENS)


def blocked_actionable(text: str) -> bool:
    if status_only(text):
        return False
    if real_blocked(text):
        return True
    upper = text.upper()
    return any(token.upper() in upper for token in _EXTRA_TOKENS)


def open_tasks(ledger: Iterable[dict]) -> list[dict]:
    found = []
    for entry in ledger:
        if not isinstance(entry, dict) or entry.get("state") != "open":
            continue
        task = entry.get("task")
        if isinstance(task, str) and _TASK.fullmatch(task):
            found.append(entry)
    return found


def tasks_mentioned(text: str, ledger: Iterable[dict]) -> list[str]:
    hits = []
    for entry in open_tasks(ledger):
        task = entry["task"]
        if re.search(rf"(?i)(?<![A-Za-z0-9]){re.escape(task)}(?![A-Za-z0-9])", text):
            hits.append(task)
    return hits


def _require_message(message: dict) -> None:
    if _CHANNEL.fullmatch(str(message.get("channel", ""))) is None:
        raise ValueError("message channel is malformed")
    if _TS.fullmatch(str(message.get("ts", ""))) is None:
        raise ValueError("message ts is malformed")
    if _USER.fullmatch(str(message.get("user", ""))) is None:
        raise ValueError("message user is malformed")
    if not isinstance(message.get("text"), str):
        raise ValueError("message text is missing")
    thread_ts = message.get("thread_ts")
    if thread_ts is not None and _TS.fullmatch(str(thread_ts)) is None:
        raise ValueError("message thread_ts is malformed")


def _thread_root(message: dict) -> str:
    return str(message.get("thread_ts") or message["ts"])


def _is_ack(message: dict, self_user_id: str | None) -> bool:
    if self_user_id is None:
        return False
    return message.get("user") == self_user_id and _ACK.search(message.get("text", "")) is not None


def _acked(message: dict, messages: list[dict], self_user_id: str | None) -> bool:
    root = _thread_root(message)
    for other in messages:
        if other.get("channel") != message["channel"] or not _is_ack(other, self_user_id):
            continue
        if _thread_root(other) != root:
            continue
        if other["ts"] > message["ts"]:
            return True
    return False


def _ask(text: str) -> str:
    cleaned = re.sub(r"<@[A-Z0-9]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:400]


def _operation_id(text: str) -> str | None:
    match = _OP.search(text)
    if match is None:
        return None
    return match.group(1)


def _limits(text: str) -> str | None:
    match = _LIMITS.search(text)
    if match is None:
        return None
    return match.group(1).strip()[:300]


def classify(
    message: dict,
    *,
    messages: list[dict],
    ledger: Iterable[dict],
    roster: Roster,
    include_returns: bool,
) -> dict | None:
    """Return one decision dict, or None when the scan stays quiet."""

    _require_message(message)
    role = roster.role(message["user"])
    if role in {"self", "other_seat"}:
        return None
    text = message["text"]
    channel = message["channel"]
    if contains_secret(text):
        decision = _base(message, roster, "REFUSE_SECRET")
        decision["signals"] = ["secret"]
        return annotate(decision, message)

    signals: list[str] = []
    if addressed_to_secretary(text, roster.grok_secretary_user_id) or (
        roster.self_user_id is not None and f"<@{roster.self_user_id}>" in text
    ):
        signals.append("commission")
    if role == "peer" and _RECEIPT.search(text):
        signals.append("receipt")
    if needs_placement(text):
        signals.append("placement")
    if channel == agent_dispatch_id() and blocked_actionable(text):
        signals.append("blocked")
    tasks = tasks_mentioned(text, ledger) if include_returns and channel == returns_channel_id() else []
    if tasks:
        signals.append("return")
    if not signals:
        return None
    if _acked(message, messages, roster.self_user_id) and "return" not in signals:
        return None

    if "return" in signals:
        kind = "ACTION_NEEDED_RETURN"
    elif "receipt" in signals and role == "peer":
        kind = "PEER_RECEIPT"
    elif "commission" in signals:
        kind = "HAND_TO_COORDINATOR"
    elif "placement" in signals:
        kind = "PLACE_ON_TITLED_WORKER"
    else:
        kind = "BLOCKED_WAKE"
    decision = _base(message, roster, kind)
    decision["signals"] = signals
    if kind != "REFUSE_SECRET":
        decision["ask"] = _ask(text)
        decision["limits"] = _limits(text)
        decision["operation_id"] = _operation_id(text)
        decision["tasks"] = tasks
    return annotate(decision, message)


def _base(message: dict, roster: Roster, kind: str) -> dict:
    return {
        "schema": SHADOW_SCHEMA,
        "decision": kind,
        "channel": message["channel"],
        "channel_name": channel_names().get(message["channel"]),
        "ts": message["ts"],
        "thread_ts": message.get("thread_ts"),
        "author": roster.author_name(message["user"]),
        "operation_id": None,
        "ask": None,
        "limits": None,
        "tasks": [],
        "signals": [],
        "would_post": False,
    }


def scan(
    messages: list[dict],
    *,
    channels: Iterable[str],
    include_returns: bool,
    ledger: Iterable[dict],
    roster: Roster,
    seen: set[str],
) -> list[dict]:
    allowed = set(channels)
    if include_returns:
        allowed.add(returns_channel_id())
    ordered = sorted(messages, key=lambda item: (item["channel"], item["ts"]))
    decisions = []
    for message in ordered:
        if message["channel"] not in allowed:
            continue
        decision = classify(
            message,
            messages=ordered,
            ledger=ledger,
            roster=roster,
            include_returns=include_returns,
        )
        if decision is None:
            continue
        key = f"{decision['channel']}:{decision['ts']}"
        if key in seen:
            continue
        seen.add(key)
        decision["dedup_key"] = key
        decision["would_post"] = False
        decisions.append(decision)
    return decisions
