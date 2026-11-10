"""Read-only ``route_preview`` tool for the existing Executive MCP host.

One preview authority for the shared routing law (MMOS V1 WO-07, Rev 4 §S3.B):
the tool composes the shared ``ChildRoutingPolicy`` classification (WO-02),
``ModelRouter.explain_route`` suitability (source-only), and host-configured
owner observations (WO-04 snapshots, WO-03 registry projection, WO-09 quota
preview) **when present** into one ``RoutePreview.v1`` record.

The record's ``authority`` is the fixed constant ``NONE_SOURCE_PREVIEW_ONLY``
and ``production_armed`` is False by construction. This module never
reserves, claims, admits, launches or spends; placement stays with the
existing claim authority, and observation paths are host composition inputs,
never caller-supplied MCP arguments.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from control_plane.child_execution_contracts import (
    CANONICAL_ROUTE_OPTIONS,
    ChildRoutingPolicy,
    PREVIEW_AUTHORITY,
    ROUTE_PREVIEW_SCHEMA,
    RoutePreview,
    canonical_task_complexity,
    witness_disposition_of,
)
from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ModelRouter,
    RoutingPolicyError,
    WorkRequest,
)
from integrations.executive_mcp.schemas import GatewayError, ToolSpec

ROUTE_PREVIEW_TOOL_NAME = "route_preview"

#: Mirrors ``control_plane.model_router`` worker/lead task kinds, risks and
#: ambiguities. tests/test_adaptive_agent_economics.py pins the equality so
#: drift on either side fails a test instead of refusing at runtime.
TOOL_TASK_KINDS = frozenset({
    "implementation", "mechanical", "tests", "research", "review",
    "planning", "judgment", "escalation",
})
TOOL_RISKS = ("routine", "elevated", "critical")
TOOL_AMBIGUITIES = ("low", "medium", "high")

#: Shared routing-law option name -> the ModelRouter task kind whose route
#: table the suitability explanation reads. Decision is classification, not
#: placement: this mapping only picks the source route table to explain.
ROUTE_OPTION_TASK_KINDS = {
    "mechanical": "mechanical",
    "routine": "implementation",
    "hard": "implementation",
    "frontier": "judgment",
    "review": "review",
}

_MAX_TEXT = 4000
_MAX_CAPABILITIES = 8
_MAX_HOST_SNAPSHOTS = 8
_MAX_OBSERVATION_BYTES = 262144
_OBSERVATION_TTL = timedelta(minutes=15)
_HOST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

#: WO-04 snapshot schema and the WO-09 producer's consumer schema. The WO-03
#: sanitized registry projection schema is matched literally (the producer
#: lives out-of-repo by design).
HOST_SNAPSHOT_SCHEMA = "mastermind.host_readiness_snapshot/v1"
REGISTRY_PROJECTION_SCHEMA = "mastermind.owner_ext_registry_projection/v1"

ROUTE_PREVIEW_TOOL_SPEC = ToolSpec(
    ROUTE_PREVIEW_TOOL_NAME,
    "Preview the shared routing law's classification and the source-suitable "
    "model tiers for one child task. The answer is always "
    "NONE_SOURCE_PREVIEW_ONLY: it never reserves, claims, admits, launches or "
    "spends, and placement stays with the existing claim authority.",
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["route_option", "goal"],
        "properties": {
            "route_option": {
                "type": "string",
                "enum": sorted(CANONICAL_ROUTE_OPTIONS),
                "description": "Shared routing-law lane (mechanical..review).",
            },
            "goal": {"type": "string", "minLength": 1, "maxLength": _MAX_TEXT},
            "context": {"type": "string", "maxLength": _MAX_TEXT},
            "task_kind": {"type": "string", "enum": sorted(TOOL_TASK_KINDS)},
            "risk": {"type": "string", "enum": list(TOOL_RISKS)},
            "ambiguity": {"type": "string", "enum": list(TOOL_AMBIGUITIES)},
            "required_capabilities": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 64},
                "maxItems": _MAX_CAPABILITIES,
            },
        },
    },
    "One RoutePreview.v1 record with explicit capacity knowledge and rank basis.",
    True,
)


@dataclass(frozen=True)
class RoutePreviewSource:
    """Host-composed read-only observation inputs for one preview composition.

    Paths point at owner-produced artifacts (WO-04 host snapshots, the WO-03
    sanitized registry projection, the WO-09 quota preview). They are set by
    the host builder, never by an MCP caller; every read is bounded and a
    missing, oversized or invalid artifact simply contributes nothing, so the
    tool degrades to ``capacity_knowledge=unknown`` /
    ``rank_basis=suitability_only`` rather than guessing.
    """

    host_snapshot_paths: tuple[str, ...] = ()
    registry_projection_path: str | None = None
    quota_preview_path: str | None = None
    policy_path: str | None = None

    def __post_init__(self) -> None:
        if type(self.host_snapshot_paths) is not tuple or any(
                type(item) is not str for item in self.host_snapshot_paths):
            raise ValueError("host_snapshot_paths must be a tuple of strings")
        if len(self.host_snapshot_paths) > _MAX_HOST_SNAPSHOTS:
            raise ValueError(f"at most {_MAX_HOST_SNAPSHOTS} host snapshots")
        for name in (self.registry_projection_path, self.quota_preview_path,
                     self.policy_path):
            if name is not None and (type(name) is not str or not name):
                raise ValueError("observation paths must be non-empty strings or None")


def _bounded_text(value: Any, field: str, *, limit: int = _MAX_TEXT) -> str:
    if type(value) is not str:
        raise GatewayError("invalid_input", f"{field} must be a string")
    if not value.strip():
        raise GatewayError("invalid_input", f"{field} must be non-empty")
    if len(value) > limit:
        raise GatewayError("invalid_input", f"{field} exceeds {limit} characters")
    return value


def _bounded_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise GatewayError("invalid_input", f"{field} must be a string")
    if len(value) > _MAX_TEXT:
        raise GatewayError("invalid_input", f"{field} exceeds {_MAX_TEXT} characters")
    return value


def validate_route_preview_tool_arguments(name: str, arguments: Any) -> dict[str, Any]:
    """Closed server-side validation for the one read-only preview tool."""
    if name != ROUTE_PREVIEW_TOOL_NAME:
        raise GatewayError("not_found", f"unknown tool {name!r}")
    if not isinstance(arguments, dict):
        raise GatewayError("invalid_input", "arguments must be an object")
    unknown = set(arguments) - set(ROUTE_PREVIEW_TOOL_SPEC.input_schema["properties"])
    if unknown:
        raise GatewayError("invalid_input", f"unknown arguments {sorted(unknown)}")
    option = arguments.get("route_option")
    if type(option) is not str or option not in CANONICAL_ROUTE_OPTIONS:
        raise GatewayError("invalid_input", "route_option must be a configured lane")
    task_kind = arguments.get("task_kind")
    if task_kind is not None and (type(task_kind) is not str
                                  or task_kind not in TOOL_TASK_KINDS):
        raise GatewayError("invalid_input", "task_kind must be a supported task kind")
    risk = arguments.get("risk")
    if risk is not None and (type(risk) is not str or risk not in TOOL_RISKS):
        raise GatewayError("invalid_input", "risk must be one of routine/elevated/critical")
    ambiguity = arguments.get("ambiguity")
    if ambiguity is not None and (type(ambiguity) is not str
                                  or ambiguity not in TOOL_AMBIGUITIES):
        raise GatewayError("invalid_input", "ambiguity must be one of low/medium/high")
    capabilities = arguments.get("required_capabilities")
    if capabilities is not None:
        if (type(capabilities) is not list
                or len(capabilities) > _MAX_CAPABILITIES
                or any(type(item) is not str or not item.strip() or len(item) > 64
                       for item in capabilities)):
            raise GatewayError(
                "invalid_input",
                f"required_capabilities must be at most {_MAX_CAPABILITIES} short strings")
    return {
        "route_option": option,
        "goal": _bounded_text(arguments.get("goal"), "goal"),
        "context": _bounded_optional_text(arguments.get("context"), "context") or "",
        "task_kind": task_kind,
        "risk": risk,
        "ambiguity": ambiguity,
        "required_capabilities": capabilities,
    }


def _read_bounded_json(path: str | None) -> dict[str, Any] | None:
    """One bounded JSON-object read; anything else contributes nothing."""
    if not path:
        return None
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if len(raw) > _MAX_OBSERVATION_BYTES:
        return None
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    return document if type(document) is dict else None


def _parse_timestamp(value: Any) -> datetime | None:
    if type(value) is not str or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _observations(source: RoutePreviewSource | None) -> dict[str, Any]:
    """Fold configured owner observations into the preview's honesty fields."""
    refs: list[str] = []
    stamps: list[datetime] = []
    observed_hosts = False
    configured_only = False
    quota_observed = False
    registry_revision = ""
    if source is not None:
        for path in source.host_snapshot_paths:
            snapshot = _read_bounded_json(path)
            if snapshot is None or snapshot.get("schema") != HOST_SNAPSHOT_SCHEMA:
                continue
            host_id = snapshot.get("host_id")
            collected = _parse_timestamp(snapshot.get("collected_at"))
            if type(host_id) is not str or _HOST_ID_RE.fullmatch(host_id) is None:
                continue
            refs.append(f"wo04:{host_id}")
            if collected is not None:
                stamps.append(collected)
            observed_hosts = True
        projection = _read_bounded_json(source.registry_projection_path)
        if projection is not None and projection.get("schema") == REGISTRY_PROJECTION_SCHEMA:
            # Schema match is the configured-ceilings floor; the revision is
            # pinned only when the producer shipped an unsanitized token (the
            # distributed WO-03 artifact redacts it).
            revision = projection.get("registry_revision")
            if type(revision) is str and _REVISION_RE.fullmatch(revision) is not None:
                registry_revision = revision
                refs.append(f"wo03:{revision[:16]}")
            else:
                refs.append("wo03:sanitized")
            configured_only = True
            produced = _parse_timestamp(projection.get("produced_at"))
            if produced is not None:
                stamps.append(produced)
        quota = _read_bounded_json(source.quota_preview_path)
        if quota is not None and quota.get("schema") == "mastermind.quota_economics_preview/v1":
            refs.append("wo09:" + sha256(
                json.dumps(quota, sort_keys=True).encode("utf-8")).hexdigest()[:16])
            quota_observed = True
            for field in ("observed_at", "generated_at", "produced_at"):
                stamp = _parse_timestamp(quota.get(field))
                if stamp is not None:
                    stamps.append(stamp)
                    break
    if quota_observed:
        capacity_knowledge, rank_basis = "observed", "observed_headroom"
    elif observed_hosts:
        capacity_knowledge, rank_basis = "observed", "suitability_only"
    elif configured_only:
        capacity_knowledge, rank_basis = "configured_only", "suitability_only"
    else:
        capacity_knowledge, rank_basis = "unknown", "suitability_only"
    observed_at = expires_at = ""
    if stamps:
        latest = max(stamps)
        observed_at = latest.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        expires_at = (latest + _OBSERVATION_TTL).astimezone(timezone.utc) \
            .isoformat().replace("+00:00", "Z")
    return {
        "capacity_knowledge": capacity_knowledge,
        "rank_basis": rank_basis,
        "observation_refs": tuple(refs[:_MAX_HOST_SNAPSHOTS + 2]),
        "observed_at": observed_at,
        "expires_at": expires_at,
        "registry_revision": registry_revision,
    }


def compose(arguments: dict[str, Any], *, source: RoutePreviewSource | None = None) -> dict[str, Any]:
    """Compose one ``RoutePreview.v1`` record from the shared law + source."""
    normalized = validate_route_preview_tool_arguments(ROUTE_PREVIEW_TOOL_NAME, arguments)
    policy = ChildRoutingPolicy()
    decision = policy.evaluate(normalized["route_option"], normalized["goal"],
                               normalized["context"])
    if not decision.resolved or not decision.task_complexity:
        raise GatewayError("invalid_input",
                           "the shared routing law refused the requested lane")
    requested_complexity = canonical_task_complexity(
        CANONICAL_ROUTE_OPTIONS[normalized["route_option"]]["task_complexity"])
    request = WorkRequest(
        normalized["task_kind"] or ROUTE_OPTION_TASK_KINDS[normalized["route_option"]],
        risk=normalized["risk"] or "routine",
        ambiguity=normalized["ambiguity"] or "low",
        required_capabilities=tuple(normalized["required_capabilities"] or ()),
    )
    try:
        router = ModelRouter.load(source.policy_path if source else None)
        explanation = router.explain_route(request)
    except RoutingPolicyError as exc:
        raise GatewayError("invalid_input", str(exc)) from None
    observations = _observations(source)
    decision_rows = explanation["decision"]
    preview = RoutePreview(
        preview_id=f"preview-{uuid4().hex}",
        requested_complexity=requested_complexity,
        effective_complexity=decision.task_complexity,
        witness_disposition=witness_disposition_of(decision),
        request_digest=sha256(
            json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest(),
        policy_revision=decision.policy_revision,
        registry_revision=observations["registry_revision"],
        suitability_tiers=tuple(
            tier["tier_id"] for tier in decision_rows["suitability_tiers"]),
        candidate_reason_codes=tuple(decision_rows["reason_codes"]),
        observation_refs=observations["observation_refs"],
        observed_at=observations["observed_at"],
        expires_at=observations["expires_at"],
        capacity_knowledge=observations["capacity_knowledge"],
        rank_basis=observations["rank_basis"],
    )
    return preview.to_dict()
