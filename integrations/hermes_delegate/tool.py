"""The one Hermes delegation tool: ``mmx_delegate``.

Pinned Hermes ``tools/registry.py`` registers each tool with a name, toolset,
JSON-schema object, and handler. This descriptor uses toolset ``mmx_delegate``.
It is not a member of the built-in ``delegation`` toolset and it does not
register ``delegate_task``.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.policy import TOOL_NAME, TOOLSET_NAME
from integrations.hermes_delegate.schema import ACTIONS


TOOL_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Submit one bounded Mastermind child through Executive OS admission to "
        "Subagent Fabric or a Cursor cloud agent, then track, independently review, "
        "and consume its result once. Does not spawn a Hermes subagent. Built-in "
        "delegate_task stays disabled. UNKNOWN is not retried. A refusal is not rehomed."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": sorted(ACTIONS)},
            "idempotency_key": {"type": "string"},
            "replay_of": {"type": "string"},
            "parent_id": {"type": "string"},
            "root_id": {"type": "string"},
            "child_kind": {
                "type": "string",
                "enum": ["implementation", "watcher", "computer_use"],
            },
            "carrier": {"type": "string", "enum": ["fabric", "cursor_cloud"]},
            "task_class": {"type": "string"},
            "task_complexity": {"type": "string"},
            "objective": {"type": "string"},
            "acceptance": {"type": "string"},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "reviewer_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["accept", "reject"]},
            "result_sha256": {"type": "string"},
            "handoff_model": {"type": "string"},
            "workstream": {"type": "string"},
            "session": {"type": "string"},
        },
        "required": ["action", "idempotency_key"],
    },
}

TOOL_REGISTRATION = {
    "name": TOOL_NAME,
    "toolset": TOOLSET_NAME,
    "schema": TOOL_SCHEMA,
    "emoji": "mmx",
}


def registered_tools(policy: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
    """Return the only delegation registration this package exposes."""
    del policy
    if TOOL_REGISTRATION["name"] != TOOL_NAME or TOOL_REGISTRATION["toolset"] == "delegation":
        return ()
    return (TOOL_REGISTRATION,)


def dispatch(arguments: Mapping[str, Any] | Any, bridge: Bridge | None = None) -> str:
    """Hermes-style handler. Returns one JSON object and does not raise for a bad call."""
    owner = bridge if bridge is not None else Bridge()
    if not isinstance(arguments, Mapping):
        return _dump({"state": "REFUSED", "reason": "ARGUMENTS_NOT_OBJECT", "live_submit": False})
    unknown = set(arguments) - set(TOOL_SCHEMA["parameters"]["properties"])
    if unknown:
        return _dump({"state": "REFUSED", "reason": "UNKNOWN_FIELD", "live_submit": False})
    action = arguments.get("action")
    key = arguments.get("idempotency_key")
    if action not in ACTIONS:
        return _dump({"state": "REFUSED", "reason": "UNKNOWN_ACTION", "live_submit": False})
    if not isinstance(key, str):
        return _dump({"state": "REFUSED", "reason": "IDEMPOTENCY_KEY_INVALID", "live_submit": False})
    if action == "submit":
        body = owner.submit(arguments)
    elif action == "status":
        body = owner.status(key)
    elif action == "cancel":
        body = owner.cancel(key)
    elif action == "review":
        body = owner.review(
            key,
            reviewer_id=str(arguments.get("reviewer_id") or ""),
            verdict=str(arguments.get("verdict") or ""),
            result_sha256=str(arguments.get("result_sha256") or ""),
        )
    else:
        body = owner.consume(
            key,
            parent_id=str(arguments.get("parent_id") or ""),
            handoff_model=arguments.get("handoff_model") if isinstance(arguments.get("handoff_model"), str) else None,
            workstream=arguments.get("workstream") if isinstance(arguments.get("workstream"), str) else None,
            session=arguments.get("session") if isinstance(arguments.get("session"), str) else None,
        )
    return _dump(body)


def _dump(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
