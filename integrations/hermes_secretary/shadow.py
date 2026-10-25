"""Slack shadow runner. Reads history and replies. Writes a local JSONL. Posts nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from detect import scan
from roster import (
    Roster,
    agent_dispatch_id,
    default_roster,
    original_room_ids,
    returns_channel_id,
    watched_channel_ids,
)
from slack_readonly import ReadOnlySlackClient, assert_read_only_client


def collect_messages(client: ReadOnlySlackClient, channels: Iterable[str]) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(channel: str, raw: dict) -> dict | None:
        if not isinstance(raw, dict):
            return None
        key = (channel, str(raw.get("ts")))
        if key in seen:
            return None
        seen.add(key)
        item = dict(raw)
        item["channel"] = channel
        found.append(item)
        return item

    for channel in channels:
        roots: list[str] = []
        for raw in client.conversations_history(channel=channel):
            item = add(channel, raw)
            if item is None:
                continue
            thread_ts = item.get("thread_ts")
            if thread_ts in (None, "", item["ts"]):
                roots.append(item["ts"])
        for root in roots:
            for raw in client.conversations_replies(channel=channel, ts=root):
                add(channel, raw)
    return found


def collect_thread(client: ReadOnlySlackClient, *, channel: str, thread_ts: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for raw in client.conversations_replies(channel=channel, ts=thread_ts):
        if not isinstance(raw, dict) or raw.get("ts") in seen:
            continue
        seen.add(raw["ts"])
        item = dict(raw)
        item["channel"] = channel
        found.append(item)
    return found


def _keys_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        keys.add(json.loads(line)["dedup_key"])
    return keys


def _append(path: Path, decisions: list[dict]) -> None:
    if not decisions:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for decision in decisions:
            if decision.get("would_post") is not False:
                raise RuntimeError("SHADOW_NO_POST")
            handle.write(json.dumps(decision, sort_keys=True, ensure_ascii=True) + "\n")


def run_shadow(
    client: ReadOnlySlackClient,
    *,
    mode: str,
    ledger: list[dict],
    output_path: Path,
    roster: Roster | None = None,
    thread_ts: str | None = None,
    channel: str | None = None,
) -> list[dict]:
    """Run one shadow pass.

    ``mode`` is ``ping_scan``, ``overnight_sweep``, or ``blocked_trigger``.
    The client is rejected unless it is a read-only Slack surface.
    """

    assert_read_only_client(client)
    roster = roster or default_roster()
    if mode == "ping_scan":
        watched = watched_channel_ids()
        messages = collect_messages(client, watched)
        returns = returns_channel_id()
        channels = tuple(item for item in watched if item != returns)
        include_returns = True
    elif mode == "overnight_sweep":
        messages = collect_messages(client, original_room_ids())
        channels = original_room_ids()
        include_returns = False
    elif mode == "blocked_trigger":
        dispatch = agent_dispatch_id()
        if channel != dispatch or not thread_ts:
            raise ValueError("blocked trigger requires the agent-dispatch thread")
        messages = collect_thread(client, channel=channel, thread_ts=thread_ts)
        channels = (dispatch,)
        include_returns = False
    else:
        raise ValueError(f"unknown shadow mode {mode}")

    seen = _keys_in(output_path)
    decisions = scan(
        messages,
        channels=channels,
        include_returns=include_returns,
        ledger=ledger,
        roster=roster,
        seen=seen,
    )
    for decision in decisions:
        decision["mode"] = mode
        decision["would_post"] = False
    _append(output_path, decisions)
    return decisions
