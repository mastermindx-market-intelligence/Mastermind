"""Numeric-only projection of Codex thread/tokenUsage/updated observations.

Consumer: the existing Codex adapter's generation/turn-scoped event normalizer.
This module owns no process, state store, compaction, routing or retry authority.
It does not claim integration/installation into an adapter merely by existing.

Wire references: OpenAI Codex App Server documentation and
openai/codex: app-server-protocol/schema/json/v2/ThreadTokenUsageUpdatedNotification.json.
`last` is request-local; `total` is cumulative spend, not context occupancy.
A caller must revalidate the current generation/turn and remeasure after any
compaction, reroute or later context mutation before using the numbers to plan.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SCHEMA = "mastermind.codex_context_observation/v1"
_INT64_MAX = (1 << 63) - 1
_LAST_FIELDS = (
    "inputTokens", "outputTokens", "totalTokens", "cachedInputTokens",
    "reasoningOutputTokens",
)


def _binding(value: str) -> None:
    if (not isinstance(value, str) or not value or len(value) > 256
            or value.strip() != value or any(ord(char) < 32 for char in value)):
        raise ValueError("an exact known native thread/turn binding is required")


def _count(value: Any, *, positive: bool = False) -> bool:
    return type(value) is int and (1 if positive else 0) <= value <= _INT64_MAX


def _observation(state: str, *, window: int | None = None,
                 tokens: int | None = None) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA,
        "state": state,
        "authority_effect": "NONE",
        "source_method": "thread/tokenUsage/updated",
        "basis": "LAST_REQUEST_NOT_CUMULATIVE",
        "context_window_tokens": window,
        "last_request_tokens": tokens,
        # Last request usage is not attested current thread/context occupancy.
        # Do not silently supply it as context_plan.used_tokens.
        "context_occupancy_tokens": None,
        "usable_as_context_plan_used_tokens": False,
        "auto_compaction_threshold_tokens": None,
        "remeasure_after_context_change": True,
    }


def project_codex_context_usage(
    params: object, *, expected_thread_id: str, expected_turn_id: str,
) -> dict[str, Any] | None:
    """Project a matching native event, or ignore foreign/unbound observations.

    Matching but malformed counts produce UNKNOWN, never zero or invented space.
    Only protocol int64 fields are inspected. Extra provider data is not copied.
    Thread identity comparison is a scope guard, not authentication or admission.
    Cached input/reasoning counts are components of the reported request usage;
    they are deliberately not added again to `last.totalTokens`.
    """
    _binding(expected_thread_id)
    _binding(expected_turn_id)
    if not isinstance(params, Mapping):
        return None
    if (type(params.get("threadId")) is not str
            or type(params.get("turnId")) is not str
            or params["threadId"] != expected_thread_id
            or params["turnId"] != expected_turn_id):
        return None
    usage = params.get("tokenUsage")
    last = usage.get("last") if isinstance(usage, Mapping) else None
    if not isinstance(last, Mapping) or any(not _count(last.get(key)) for key in _LAST_FIELDS):
        return _observation("UNKNOWN")
    if "cacheWriteInputTokens" in last and not _count(last["cacheWriteInputTokens"]):
        return _observation("UNKNOWN")
    if last["totalTokens"] < max(last["inputTokens"], last["outputTokens"]):
        return _observation("UNKNOWN")
    window = usage.get("modelContextWindow")
    if window is None:
        return _observation("WINDOW_UNKNOWN", tokens=last["totalTokens"])
    if not _count(window, positive=True):
        return _observation("UNKNOWN")
    return _observation("OBSERVED", window=window, tokens=last["totalTokens"])


def project_codex_compaction_notification(
    params: object, *, expected_thread_id: str, expected_turn_id: str,
) -> dict[str, Any] | None:
    """Observe one exact native completion notice; never attest saved state.

    The provider's asynchronous notification cannot substitute for the
    Executive generation-bound checkpoint INTENT/APPLIED transaction or an
    updated context measurement. It authorizes no replay or provider switch.
    """
    _binding(expected_thread_id)
    _binding(expected_turn_id)
    if (not isinstance(params, Mapping)
            or type(params.get("threadId")) is not str
            or type(params.get("turnId")) is not str
            or params["threadId"] != expected_thread_id
            or params["turnId"] != expected_turn_id):
        return None
    return {
        "schema_version": "mastermind.codex_compaction_observation/v1",
        "source_method": "thread/compacted",
        "state": "NATIVE_COMPACTION_NOTIFIED",
        "authority_effect": "NONE",
        "checkpoint_committed": False,
        "requires_remeasurement": True,
        "auto_resume_permitted": False,
        "retry_authorized": False,
    }
