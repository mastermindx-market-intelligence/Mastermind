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
        "Submit, observe, or cancel one bounded Mastermind child through "
        "Executive admission on an existing Fabric/Cursor carrier. Model calls "
        "cannot submit independent-review verdicts or consume a parent's result; "
        "those require a separate trusted owner. Built-in delegate_task remains "
        "disabled. UNKNOWN is not retried and refusals are not rehomed."
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
    # Client schema is advisory; enforce this fence in the handler as well.
    # A model can invent a reviewer_id, not a legitimate non-author receipt.
    if arguments.get("action") in {"review", "consume"}:
        return _dump({
            "state": "REFUSED",
            "reason": "REVIEW_AND_CONSUME_OWNER_ONLY",
            "live_submit": False,
        })
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
    else:
        body = owner.cancel(key)
    return _dump(body)


def _dump(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
