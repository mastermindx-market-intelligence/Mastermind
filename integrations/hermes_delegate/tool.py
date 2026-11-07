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
from integrations.hermes_delegate.schema import (
    ACTIONS,
    SELECTED_CHILD_ACTIONS,
    SubmissionError,
    parse_selected_child,
)


_BRIDGE_ARGUMENTS: dict[str, Any] = {
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
}

# The selected-child branch is closed: the action and the exact canonical
# command reference the host projected. No request key, Job, plan, carrier,
# objective, acceptance, reviewer, or cancel argument exists on this branch.
_SELECTED_CHILD_ARGUMENTS: dict[str, Any] = {
    "action": {"type": "string", "enum": sorted(SELECTED_CHILD_ACTIONS)},
    "command": {"type": "string"},
}


TOOL_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Submit, observe, or cancel one bounded Mastermind child through "
        "Executive admission on an existing Fabric/Cursor carrier. Model calls "
        "cannot submit independent-review verdicts or consume a parent's result; "
        "those require a separate trusted owner. Built-in delegate_task remains "
        "disabled. UNKNOWN is not retried and refusals are not rehomed. "
        "A selected_child action submits or observes exactly the Executive "
        "child the authenticated host already froze, under its canonical "
        "command reference."
    ),
    "parameters": {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "idempotency_key"],
                "properties": _BRIDGE_ARGUMENTS,
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "command"],
                "properties": _SELECTED_CHILD_ARGUMENTS,
            },
        ],
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
    if not isinstance(arguments, Mapping):
        return _dump({"state": "REFUSED", "reason": "ARGUMENTS_NOT_OBJECT", "live_submit": False})
    action = arguments.get("action")
    # Client schema is advisory; enforce this fence in the handler as well.
    # A model can invent a reviewer_id, not a legitimate non-author receipt.
    # The action is compared as text so an unhashable model value cannot
    # escape the handler.
    if isinstance(action, str) and action in {"review", "consume"}:
        return _dump({
            "state": "REFUSED",
            "reason": "REVIEW_AND_CONSUME_OWNER_ONLY",
            "live_submit": False,
        })
    if isinstance(action, str) and action in SELECTED_CHILD_ACTIONS:
        return _dump(_dispatch_selected_child(arguments))
    owner = bridge if bridge is not None else Bridge()
    unknown = set(arguments) - set(_BRIDGE_ARGUMENTS)
    if unknown:
        return _dump({"state": "REFUSED", "reason": "UNKNOWN_FIELD", "live_submit": False})
    key = arguments.get("idempotency_key")
    if not isinstance(action, str) or action not in ACTIONS:
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


def _dispatch_selected_child(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Route the closed selected-child branch to the installed composition.

    The default process has no composition, so the branch refuses instead of
    constructing a live bridge. The composition is the trusted host's
    explicit binding; the model never chooses the child.
    """

    from integrations.hermes_delegate.executive import (
        selected_child_composition,
    )

    try:
        request = parse_selected_child(arguments)
    except SubmissionError as exc:
        return _refused(exc.reason)
    composition = selected_child_composition()
    if composition is None:
        return _refused("EXECUTIVE_SELECTED_CHILD_NOT_BOUND")
    if request["action"] == "selected_child_submit":
        return composition.submit(request["command"])
    return composition.status(request["command"])


def _refused(reason: str) -> dict[str, Any]:
    return {
        "schema": "mastermind.hermes_delegate.selected_child/v1",
        "state": "REFUSED",
        "reason": reason,
        "command_id": None,
        "job_id": None,
        "attempt_id": None,
        "attempt_status": None,
        "job_status": None,
        "live_submit": False,
    }


def _dump(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
