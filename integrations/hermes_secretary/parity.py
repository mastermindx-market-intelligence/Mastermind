"""Compare a shadow JSONL with Grok Secretary's actual posts over a window.

The checker does not call Slack. A caller that wants posts from Slack must
already have used the read-only client and filtered them to the secretary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParityReport:
    matched: tuple[str, ...]
    shadow_only: tuple[str, ...]
    secretary_only: tuple[str, ...]
    mismatched_kind: tuple[str, ...]
    withheld: tuple[str, ...]


def _ts(value: str) -> float:
    return float(value)


def _in_window(ts: str, start_ts: str, end_ts: str) -> bool:
    return _ts(start_ts) <= _ts(ts) < _ts(end_ts)


def _root(record: dict) -> str:
    return str(record.get("thread_ts") or record["ts"])


def _marker_ok(kind: str, text: str) -> bool:
    if kind == "ACTION_NEEDED_RETURN":
        return "ACTION NEEDED RETURN" in text
    if kind == "HAND_TO_COORDINATOR":
        return re.search(r"\b(ACK|RESULT)\b", text) is not None
    if kind == "PLACE_ON_TITLED_WORKER":
        return re.search(r"\b(ACK|RESULT|PLACED)\b", text) is not None
    if kind == "BLOCKED_WAKE":
        return re.search(r"\b(ACK|RESULT)\b", text) is not None or "BLOCKED" in text
    return False


def _related(decision: dict, posts: list[dict]) -> list[dict]:
    root = _root(decision)
    found = []
    for post in posts:
        if post.get("channel") != decision["channel"]:
            continue
        post_root = _root(post)
        if post_root == root or post.get("thread_ts") == decision["ts"] or post_root == decision["ts"]:
            found.append(post)
    return found


def compare(
    *,
    decisions: list[dict],
    posts: list[dict],
    start_ts: str,
    end_ts: str,
) -> ParityReport:
    window_decisions = [item for item in decisions if _in_window(item["ts"], start_ts, end_ts)]
    window_posts = [item for item in posts if _in_window(item["ts"], start_ts, end_ts)]
    consumed: set[int] = set()
    matched: list[str] = []
    shadow_only: list[str] = []
    mismatched: list[str] = []
    withheld: list[str] = []

    for decision in window_decisions:
        related = []
        for index, post in enumerate(window_posts):
            if index in consumed:
                continue
            if post in _related(decision, [post]):
                related.append((index, post))
        key = decision["dedup_key"]
        if decision["decision"] == "REFUSE_SECRET":
            if related:
                mismatched.append(key)
                consumed.update(index for index, _post in related)
            else:
                withheld.append(key)
            continue
        good = [(index, post) for index, post in related if _marker_ok(decision["decision"], post.get("text", ""))]
        if good:
            matched.append(key)
            consumed.add(good[0][0])
        elif related:
            mismatched.append(key)
            consumed.update(index for index, _post in related)
        else:
            shadow_only.append(key)

    secretary_only = [
        f"{post['channel']}:{post['ts']}"
        for index, post in enumerate(window_posts)
        if index not in consumed
    ]
    return ParityReport(
        matched=tuple(matched),
        shadow_only=tuple(shadow_only),
        secretary_only=tuple(secretary_only),
        mismatched_kind=tuple(mismatched),
        withheld=tuple(withheld),
    )


def load_decisions(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def secretary_posts_from_readonly(client: object, *, channels: tuple[str, ...], secretary_user_id: str) -> list[dict]:
    """Filter already-authorized history down to the secretary's posts.

    The import is local so a parity-only caller does not need the Slack types
    until it opts into a read. Write methods are rejected first.
    """

    from slack_readonly import ReadOnlySlackClient, assert_read_only_client
    from shadow import collect_messages

    assert_read_only_client(client)
    if not isinstance(client, ReadOnlySlackClient):
        raise TypeError("secretary post read requires ReadOnlySlackClient")
    posts = []
    for message in collect_messages(client, channels):
        if message.get("user") == secretary_user_id:
            posts.append(message)
    return posts
