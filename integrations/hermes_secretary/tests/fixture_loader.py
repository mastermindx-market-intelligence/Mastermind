"""Load the checked-in Slack fixture into a read-only client."""

from __future__ import annotations

import json
from pathlib import Path

from slack_readonly import ReadOnlySlackClient

FIXTURE = Path(__file__).with_name("fixtures") / "ping_scan.json"


def load_fixture(path: Path | None = None) -> tuple[ReadOnlySlackClient, list[dict]]:
    raw = json.loads((path or FIXTURE).read_text(encoding="utf-8"))
    replies = {}
    for key, rows in raw["replies"].items():
        channel, ts = key.split("|", 1)
        replies[(channel, ts)] = rows
    client = ReadOnlySlackClient(raw["history"], replies)
    return client, raw["ledger"]
