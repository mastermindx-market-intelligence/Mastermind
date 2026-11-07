"""Request policy for the existing Experiential gateway.

This is a stateless guard, not a scheduler or a second budget ledger. The
provider's :free contract owns daily free-allowance enforcement. Paid monthly
limits still require the incumbent budget owner/provider budget before enabling
free_and_uncensored on a credential-owning gateway.
"""
from __future__ import annotations

import hashlib
import json

PLAN_MODES = frozenset({"legacy", "free_only", "free_and_uncensored"})
FREE_CHAT_MODELS = (
    "deepseek-v4.1-flash:free",
    "deepseek-v4.1-flash-1017:free",
    "gpt-6-luna:free",
    "clef:free",
    "clef-flash:free",
)
FREE_NATIVE_MODELS = {
    "jev-latest:free": "systemone",
    "gpt-6-luna-decisions:free": "decisions",
}
PAID_UNCENSORED_MODELS = (
    "deepseek-v4.1-flash-uncensored",
    "glm-5.3-flash-uncensored",
)
# Preference is for a NEW admitted selection only. This is never a retry ladder.
CHAT_ENDPOINTS = frozenset({"chat/completions", "responses"})
ROUTING_OVERRIDES = frozenset({
    "models", "fallbacks", "fallback", "provider", "providers", "route",
    "route_id", "routing", "routing_pool", "routing_pool_id", "api_key",
    "base_url", "extra_body", "extra_headers", "extra_query",
})


def plan_policy_digest(mode: str) -> str:
    """Bind an admitted Attempt to the exact deployed request policy."""
    if type(mode) is not str or mode not in PLAN_MODES:
        raise ValueError("unsupported Experiential plan policy")
    spec = {"version": 1, "mode": mode, "free_chat": FREE_CHAT_MODELS,
            "free_native": FREE_NATIVE_MODELS, "paid": PAID_UNCENSORED_MODELS,
            "overrides": sorted(ROUTING_OVERRIDES)}
    return hashlib.sha256(json.dumps(spec, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


class PlanRequestRefused(ValueError):
    """Stable, nonsecret reason, suitable for the existing gateway refusal."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _closed_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PlanRequestRefused("PLAN_DUPLICATE_JSON_FIELD")
        value[key] = item
    return value


def _invalid_constant(_value):
    raise PlanRequestRefused("PLAN_INVALID_JSON")


def validate_plan_request(mode: str, endpoint: str, body: bytes) -> str | None:
    """Validate exact wire target before RPM/slot reservation; never rewrite.

    Legacy mode preserves existing callers. Neither a body field nor a client
    header can select the deployment policy or enable paid inference.
    """
    if mode not in PLAN_MODES:
        raise ValueError("unsupported Experiential plan policy")
    if mode == "legacy":
        return None
    try:
        payload = json.loads(
            body, object_pairs_hook=_closed_object, parse_constant=_invalid_constant
        )
    except PlanRequestRefused:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanRequestRefused("PLAN_INVALID_JSON") from exc
    if type(payload) is not dict:
        raise PlanRequestRefused("PLAN_JSON_OBJECT_REQUIRED")
    if ROUTING_OVERRIDES.intersection(payload):
        raise PlanRequestRefused("PLAN_ROUTING_OVERRIDE_REFUSED")
    model = payload.get("model")
    if type(model) is not str or not model:
        raise PlanRequestRefused("PLAN_EXACT_MODEL_REQUIRED")
    if model in FREE_CHAT_MODELS:
        if endpoint not in CHAT_ENDPOINTS:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "free"
    if model in FREE_NATIVE_MODELS:
        if endpoint != FREE_NATIVE_MODELS[model]:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "free"
    if model in PAID_UNCENSORED_MODELS:
        if mode != "free_and_uncensored":
            raise PlanRequestRefused("PLAN_PAID_LANE_DISABLED")
        if endpoint not in CHAT_ENDPOINTS:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "paid_uncensored"
    # In particular, a plain promotional slug may spill to wallet charges;
    # glm-5.3-uncensored is the old full model, not the selected Flash model.
    raise PlanRequestRefused("PLAN_MODEL_NOT_ALLOWED")
