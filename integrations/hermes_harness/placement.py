"""Turn a shadow placement decision into one inert ``mmx_delegate`` submit.

The default admission port refuses. This module does not bind Executive OS,
start Fabric, or post to Slack.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.tool import dispatch

PARENT_ID = "hermes-secretary"
ROOT_ID = "hermes-root-mmsecretary"
PLACEMENT_DECISION = "PLACE_ON_TITLED_WORKER"


def placement_key(decision: Mapping[str, Any]) -> str:
    channel = str(decision["channel"]).lower()
    stamp = str(decision["ts"]).replace(".", "-")
    return f"place-{channel}-{stamp}"


def place_decision(decision: Mapping[str, Any], bridge: Bridge) -> dict[str, Any]:
    ask = decision.get("ask")
    objective = " ".join(str(ask or "Place this note on the existing titled worker.").split())
    payload = {
        "action": "submit",
        "idempotency_key": placement_key(decision),
        "parent_id": PARENT_ID,
        "root_id": ROOT_ID,
        "child_kind": "implementation",
        "carrier": "fabric",
        "task_class": "mechanical",
        "task_complexity": "C1_ROUTINE_BOUNDED",
        "objective": objective[:500],
        "acceptance": "The placement is recorded locally. No Slack post and no live admission.",
        "constraints": ["shadow_jsonl_only", "no_slack_post"],
    }
    view = json.loads(dispatch(payload, bridge))
    return {
        "tool": "mmx_delegate",
        "state": view.get("state"),
        "reason": view.get("reason"),
        "live_submit": view.get("live_submit") is True,
        "idempotency_key": view.get("idempotency_key") or payload["idempotency_key"],
        "admitted": view.get("state") == "ADMITTED",
    }
