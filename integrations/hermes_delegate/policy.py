"""Hermes delegation fence for the WP4 bridge.

The built-in ``delegation`` toolset and ``delegate_task`` stay disabled.
Exactly one replacement tool is described. This policy does not enroll that
tool into a live Hermes profile and does not grant Executive authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "mastermind.hermes_delegate.tool_policy/v1"
HERMES_PIN = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
BUILTIN_DELEGATION_TOOLSET = "delegation"
BUILTIN_DELEGATION_TOOL = "delegate_task"
TOOL_NAME = "mmx_delegate"
TOOLSET_NAME = "mmx_delegate"

# Same set as integrations/hermes_qualification/preflight.py REQUIRED_DISABLED
# at the pinned Hermes inspection. The unit test fails if the two drift.
REQUIRED_DISABLED_TOOLSETS = frozenset({
    "web", "browser", "terminal", "file", "code_execution", "vision",
    "video", "image_gen", "video_gen", "x_search", "tts", "stt",
    "skills", "todo", "kanban", "memory", "context_engine", "session_search",
    "connections", "delegation", "cronjob", "yuanbao", "computer_use",
    "a2a",
})


class PolicyError(ValueError):
    """The checked-in fence would enable a second delegation path."""


def validate_policy(policy: Mapping[str, Any]) -> None:
    if not isinstance(policy, Mapping):
        raise PolicyError("policy must be an object")
    if policy.get("schema") != SCHEMA:
        raise PolicyError("policy schema is not the WP4 fence")
    if policy.get("hermes_pin") != HERMES_PIN:
        raise PolicyError("policy is not bound to the inspected Hermes pin")
    if policy.get("built_in_delegation_toolset") != BUILTIN_DELEGATION_TOOLSET:
        raise PolicyError("built-in delegation toolset name drifted")
    if policy.get("built_in_delegation_tool") != BUILTIN_DELEGATION_TOOL:
        raise PolicyError("built-in delegate_task name drifted")
    if policy.get("live_submit") is not False:
        raise PolicyError("live submit is not authorized by this policy")
    disabled = policy.get("disabled_toolsets")
    if not isinstance(disabled, list) or BUILTIN_DELEGATION_TOOLSET not in disabled:
        raise PolicyError("BUILTIN_DELEGATION_ENABLED")
    if frozenset(disabled) != REQUIRED_DISABLED_TOOLSETS:
        raise PolicyError("DELEGATION_POLICY_INVALID")
    enabled_tools = policy.get("enabled_tools")
    enabled_toolsets = policy.get("enabled_toolsets")
    if enabled_tools != [TOOL_NAME] or enabled_toolsets != [TOOLSET_NAME]:
        raise PolicyError("MULTIPLE_DELEGATION_TOOLS")
    if BUILTIN_DELEGATION_TOOL in enabled_tools or BUILTIN_DELEGATION_TOOLSET in enabled_toolsets:
        raise PolicyError("BUILTIN_DELEGATION_ENABLED")
    if frozenset(enabled_toolsets) & REQUIRED_DISABLED_TOOLSETS:
        raise PolicyError("BUILTIN_DELEGATION_ENABLED")


def load_policy(path: Path | None = None) -> dict[str, Any]:
    file = path or Path(__file__).with_name("tool_policy.json")
    policy = json.loads(file.read_text(encoding="utf-8"))
    validate_policy(policy)
    return policy


def refusal_for_policy(policy: Mapping[str, Any]) -> str | None:
    """Return a stable refusal code, or None when the fence holds."""
    try:
        validate_policy(policy)
    except PolicyError as exc:
        text = str(exc)
        if text in {"BUILTIN_DELEGATION_ENABLED", "MULTIPLE_DELEGATION_TOOLS"}:
            return text
        return "DELEGATION_POLICY_INVALID"
    return None
