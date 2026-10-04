"""Host-owned execution binding for the VPS inference service principal.

This module owns no lifecycle, queue, retry, credential, workspace creation, or
provider process. It derives a closed placement contract from the existing
Model Router and the host's reviewed workspace/base/capacity inputs. Executive
Runtime, Capacity, ExecutiveSupervisor, and executive_workspace remain owners.
"""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from control_plane import ceo_request
from control_plane.model_router import ModelRouter, RoutingPolicyError, WorkRequest

SCHEMA = "mastermind.executive_service_inference_binding.v1"
_MAX_QUOTA_CLASSES = 16
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class InferenceExecutionBindingError(ValueError):
    """The trusted host inference execution binding is unavailable."""


def _quota_classes(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise InferenceExecutionBindingError("eligible quota classes must be a sequence")
    result: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            raise InferenceExecutionBindingError("eligible quota class must be a string")
        value = raw.strip()
        if _ID_RE.fullmatch(value) is None:
            raise InferenceExecutionBindingError("eligible quota class is invalid")
        if value not in result:
            result.append(value)
    if not result or len(result) > _MAX_QUOTA_CLASSES:
        raise InferenceExecutionBindingError("eligible quota classes are empty or exceed the bound")
    return tuple(sorted(result))


def _base_sha(value: str) -> str:
    if not isinstance(value, str):
        raise InferenceExecutionBindingError("base_sha must be a string")
    base = value.strip().lower()
    if _SHA_RE.fullmatch(base) is None:
        raise InferenceExecutionBindingError("base_sha must be exact 40-hex")
    return base


def _intent(value: str) -> str:
    if not isinstance(value, str):
        raise InferenceExecutionBindingError("intent_id must be a string")
    intent = value.strip()
    if _ID_RE.fullmatch(intent) is None:
        raise InferenceExecutionBindingError("intent_id is invalid")
    return intent


def build_execution_binding(
    *,
    intent_id: str,
    workspace_root: str | Path,
    base_sha: str,
    eligible_quota_classes: Sequence[str],
    router: ModelRouter | None = None,
) -> dict:
    """Derive one read-only research placement contract from existing owners."""

    identity = _intent(intent_id)
    root = Path(workspace_root).expanduser().resolve(strict=False)
    if not root.is_absolute():
        raise InferenceExecutionBindingError("workspace_root must be absolute")
    base = _base_sha(base_sha)
    quotas = _quota_classes(eligible_quota_classes)
    try:
        active_router = router or ModelRouter.load()
        decision = active_router.route(
            WorkRequest(
                "research",
                risk="routine",
                ambiguity="low",
                required_capabilities=("research",),
            )
        )
        constraints = decision.job_constraints()
    except RoutingPolicyError as exc:
        raise InferenceExecutionBindingError("research routing policy is unavailable") from exc
    constraints = dict(constraints)
    constraints["base_sha"] = base
    constraints["eligible_quota_classes"] = list(quotas)
    return {
        "schema": SCHEMA,
        "intent_id": identity,
        "branch": ceo_request.derive_branch(identity),
        "worktree": ceo_request.derive_worktree(str(root), identity),
        "constraints": constraints,
    }


def validate_execution_binding(
    value: Mapping,
    *,
    intent_id: str,
    workspace_root: str | Path,
    router: ModelRouter | None = None,
) -> dict:
    """Require exact current-policy binding; never accept caller-selected route fields."""

    if not isinstance(value, Mapping) or set(value) != {
        "schema", "intent_id", "branch", "worktree", "constraints"
    }:
        raise InferenceExecutionBindingError("service execution binding shape is invalid")
    constraints = value.get("constraints")
    if not isinstance(constraints, Mapping):
        raise InferenceExecutionBindingError("service execution constraints are invalid")
    base = constraints.get("base_sha")
    quotas = constraints.get("eligible_quota_classes")
    expected = build_execution_binding(
        intent_id=intent_id,
        workspace_root=workspace_root,
        base_sha=base,
        eligible_quota_classes=quotas,
        router=router,
    )
    if dict(value) != expected:
        raise InferenceExecutionBindingError("service execution binding differs from current host policy")
    return copy.deepcopy(expected)


__all__ = [
    "SCHEMA",
    "InferenceExecutionBindingError",
    "build_execution_binding",
    "validate_execution_binding",
]
