"""One paused secretary routine tick over a recorded Slack fixture.

The tick writes would-decisions JSONL. Placement rows carry an ``mmx_delegate``
result. ``would_post`` stays false. The Slack client is the read-only fixture
client; this module never constructs a network transport.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_harness.placement import PLACEMENT_DECISION, place_decision

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "hermes_secretary"
    / "tests"
    / "fixtures"
    / "ping_scan.json"
)


def _secretary():
    root = Path(__file__).resolve().parents[1] / "hermes_secretary"
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    import roster
    import shadow
    import slack_readonly
    return roster, shadow, slack_readonly


def load_fixture(path: Path | None = None):
    roster, _shadow, slack_readonly = _secretary()
    raw = json.loads((path or FIXTURE).read_text(encoding="utf-8"))
    replies: dict[tuple[str, str], list] = {}
    for key, rows in raw.get("replies", {}).items():
        channel, stamp = key.split("|", 1)
        replies[(channel, stamp)] = rows
    client = slack_readonly.ReadOnlySlackClient(raw["history"], replies)
    return client, list(raw.get("ledger") or []), roster.default_roster()


def routine_tick(
    *,
    mode: str = "ping_scan",
    fixture: Path | None = None,
    output: Path,
    bridge: Bridge | None = None,
    roster: Any = None,
    channel: str | None = None,
    thread_ts: str | None = None,
) -> dict[str, Any]:
    _roster_mod, shadow, _slack = _secretary()
    client, ledger, _configured = load_fixture(fixture)
    owner = bridge if bridge is not None else Bridge()
    active = roster if roster is not None else _secretary()[0].default_roster(environ=os.environ)
    prior = output.read_text(encoding="utf-8") if output.exists() else ""
    decisions = shadow.run_shadow(
        client,
        mode=mode,
        ledger=ledger,
        output_path=output,
        roster=active,
        channel=channel,
        thread_ts=thread_ts,
    )
    admitted = 0
    for decision in decisions:
        if decision.get("decision") == PLACEMENT_DECISION:
            delegation = place_decision(decision, owner)
            if delegation["admitted"]:
                admitted += 1
        else:
            delegation = None
        decision["delegation"] = delegation
        decision["would_post"] = False
    _rewrite(output, decisions, prior=prior)
    methods = sorted({call[0] for call in getattr(client, "calls", [])})
    return {
        "decisions": decisions,
        "admitted": admitted,
        "slack_methods": methods,
        "output": str(output),
        "count": len(decisions),
    }


def _rewrite(path: Path, decisions: list[dict], *, prior: str = "") -> None:
    """Replace this tick's raw append with enriched rows. Keep earlier rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for decision in decisions:
        if decision.get("would_post") is not False:
            raise RuntimeError("SHADOW_NO_POST")
        if decision.get("delegation", {}).get("live_submit") if isinstance(decision.get("delegation"), dict) else False:
            raise RuntimeError("SHADOW_NO_LIVE_SUBMIT")
        lines.append(json.dumps(decision, sort_keys=True, ensure_ascii=True))
    body = prior
    if body and not body.endswith("\n"):
        body += "\n"
    path.write_text(body + "".join(line + "\n" for line in lines), encoding="utf-8")
