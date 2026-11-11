"""Immutable logical CEO selection; no provider/session/worker activation.

The requested alias is caller intent. This closed record is trusted host
resolution, retained only in the original root's immutable creation event.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

SCHEMA = "mastermind.frontier_selection.v1"
ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_KEYS = frozenset({
    "schema", "routing_policy_version", "model_alias", "provider_alias",
    "adapter_id", "execution_profile_id", "execution_profile_digest",
    "capability_policy_version", "capability_policy_digest", "model",
    "effort", "cost_class", "capabilities", "worker_eligible",
})
PROVENANCE_KEYS = frozenset({
    "frontier_model_alias", "frontier_selection", "frontier_selection_digest",
})


class FrontierSelectionError(ValueError):
    """A logical selection is absent, malformed, or inconsistent."""


def validate_alias(value: Any) -> str:
    if not isinstance(value, str) or ALIAS_RE.fullmatch(value) is None:
        raise FrontierSelectionError("frontier_model_alias must be an exact lowercase alias")
    return value


def validate_selection(value: Any, *, requested_alias: str) -> dict[str, Any]:
    alias = validate_alias(requested_alias)
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise FrontierSelectionError("frontier selection has an invalid closed shape")
    if value["schema"] != SCHEMA or value["worker_eligible"] is not False:
        raise FrontierSelectionError("frontier selection must identify a logical non-worker lead")
    result: dict[str, Any] = {}
    for key in _KEYS - {"capabilities", "worker_eligible"}:
        item = value[key]
        limit = 256 if key == "model" else 128
        if (not isinstance(item, str) or not item or len(item) > limit
                or item != item.strip() or any(ord(c) < 32 or ord(c) == 127 for c in item)):
            raise FrontierSelectionError("frontier selection contains invalid identity text")
        result[key] = item
    for key in ("model_alias", "provider_alias", "adapter_id"):
        validate_alias(result[key])
    if result["model_alias"] != alias:
        raise FrontierSelectionError("frontier selection does not match the requested alias")
    for key in ("execution_profile_digest", "capability_policy_digest"):
        if _DIGEST_RE.fullmatch(result[key]) is None:
            raise FrontierSelectionError("frontier selection contains an invalid identity digest")
    capabilities = value["capabilities"]
    if (not isinstance(capabilities, list) or not 3 <= len(capabilities) <= 64
            or any(not isinstance(item, str) or ALIAS_RE.fullmatch(item) is None
                   for item in capabilities)
            or capabilities != sorted(set(capabilities))
            or not {"planning", "judgment", "escalation"}.issubset(capabilities)):
        raise FrontierSelectionError("frontier selection has invalid lead capabilities")
    result["capabilities"] = list(capabilities)
    result["worker_eligible"] = False
    return result


def selection_digest(value: Mapping[str, Any]) -> str:
    normalized = validate_selection(value, requested_alias=value.get("model_alias"))
    return hashlib.sha256(json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def resolve_selection(router: Any, requested_alias: str) -> dict[str, Any]:
    """Resolve from an operation-local host router; never load or call a provider."""
    alias = validate_alias(requested_alias)
    profile = router.resolve_frontier_model_alias(alias)
    record = dataclasses.asdict(profile)
    record["capabilities"] = sorted(record["capabilities"])
    record.update(schema=SCHEMA, routing_policy_version=router.policy_version)
    return validate_selection(record, requested_alias=alias)


def selection_provenance(requested_alias: Any, value: Any) -> dict[str, Any]:
    if requested_alias is None and value is None:
        return {}
    record = validate_selection(value, requested_alias=validate_alias(requested_alias))
    return {
        "frontier_model_alias": requested_alias,
        "frontier_selection": record,
        "frontier_selection_digest": selection_digest(record),
    }


def selection_from_provenance(provenance: Mapping[str, Any]) -> dict[str, Any] | None:
    present = PROVENANCE_KEYS.intersection(provenance)
    if not present:
        return None
    if present != PROVENANCE_KEYS or provenance.get("schema") != "mastermind.ceo_intent.v2":
        raise FrontierSelectionError("frontier selection provenance is incomplete or foreign")
    record = validate_selection(
        provenance["frontier_selection"],
        requested_alias=provenance["frontier_model_alias"],
    )
    if (record != provenance["frontier_selection"]
            or provenance["frontier_selection_digest"] != selection_digest(record)):
        raise FrontierSelectionError("frontier selection provenance digest differs")
    return record
