"""Anthropic-wire guards owned by the existing Experiential gateway.

Reuse the sealed native policy's JSON and refusal primitives without changing
its historical source identity. This module owns no admission state or retry.
"""
from __future__ import annotations

import hashlib
import json
import re

from control_plane.experiential_plan_policy import (
    PlanRequestRefused,
    ROUTING_OVERRIDES,
    _closed_object,
    _invalid_constant,
)

ANTHROPIC_ENDPOINTS = frozenset({"messages", "messages/count_tokens"})
_ANTHROPIC_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def parse_anthropic_models(raw: str) -> tuple[str, ...]:
    """Parse EXPLABS_ANTHROPIC_MODELS into exact admitted slugs.

    The operator-deployed list is the whole funding boundary for the
    Anthropic-wire surface: no expansion, aliasing or suffix matching.
    """
    if type(raw) is not str:
        raise ValueError("EXPLABS_ANTHROPIC_MODELS must be a string")
    models = []
    for item in raw.split(","):
        slug = item.strip()
        if not slug:
            continue
        if not _ANTHROPIC_SLUG_RE.match(slug):
            raise ValueError(f"invalid Anthropic model slug: {slug!r}")
        if slug in models:
            raise ValueError(f"duplicate Anthropic model slug: {slug!r}")
        models.append(slug)
    return tuple(models)


def anthropic_policy_digest(models) -> str:
    """Bind an Anthropic-wire caller to the exact deployed admitted catalogue."""
    if not isinstance(models, (tuple, list, frozenset)) or not all(
        isinstance(m, str) and m for m in models
    ) or len(set(models)) != len(models):
        raise ValueError("admitted Anthropic models must be unique nonempty strings")
    spec = {"version": 1, "surface": "anthropic_messages",
            "gateway_policy": "single_attempt_no_fallback",
            "admitted_models": sorted(models)}
    return hashlib.sha256(json.dumps(spec, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def validate_anthropic_plan_request(models, endpoint: str, body: bytes) -> str:
    """Validate an Anthropic Messages-wire target before RPM/slot reservation.

    Admission is membership in the operator-deployed catalogue only. A body
    field can never widen it, and there is no fallback to another model.
    """
    if endpoint not in ANTHROPIC_ENDPOINTS:
        raise ValueError("not an Anthropic-wire endpoint")
    if not isinstance(models, (tuple, list, frozenset)) or not models:
        raise PlanRequestRefused("PLAN_ANTHROPIC_NOT_ENABLED")
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
    if model not in set(models):
        raise PlanRequestRefused("PLAN_MODEL_NOT_ADMITTED")
    return "anthropic"
