"""Worker-aware Active-Session Dialogue V2 contract."""
from __future__ import annotations

from typing import Any, Mapping

from integrations.slack_agent_dialogue.contract import semantic_fingerprint

MESSAGE_SCHEMA_V2 = "mastermind.agent_dialogue.v2"
MESSAGE_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_V2"
PARENT_SCHEMA_V2 = "mastermind.agent_dialogue_parent.v2"
PARENT_DISCRIMINATOR_V2 = "MMX/AGENT_DIALOGUE_PARENT_V2"
TURN_WATCH_MODE_V1 = "turn_watch_v1"


def build_parent_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build one V2 parent with deterministic semantic identity."""

    raw = dict(value)
    raw["fingerprint"] = semantic_fingerprint(raw)
    return raw
