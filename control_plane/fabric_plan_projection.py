"""Pure projection of one Runtime-admitted execution plan into the closed view.

Consumes the Runtime-owned ``BoundedAdmittedPlanSnapshot`` (detached canonical
admission plus its typed sealed plan) together with the finalized
``RuntimeReadObservationReceipt`` and returns exactly the closed
``mastermind.admitted_execution_plan_view.v1`` body, never the whole Workspace
response.  This leaf performs no I/O or SQL, re-runs no admission, capacity,
grant or child-creation validator, recomputes no digest, and exposes no raw
event, reservation-row, provider/session, write-path or result-envelope
material.  Display objectives stay under the incumbent Mission text owner
(``mission_workspace._safe_text``): one redacted, altered, oversized or
rejected objective withholds the whole plan.  A refused projection returns no
partial proof, digest or count, and the reduced view never claims to hash to
``plan_digest``; that digest identifies the canonical full typed plan.
"""

from __future__ import annotations

import re
from typing import Any, NoReturn

from control_plane.executive_runtime import (
    BoundedAdmittedPlanSnapshot,
    BoundedRoleResultRootMetadata,
    RuntimeReadObservationReceipt,
)
from control_plane.mission_workspace import _safe_text

__all__ = ["FabricPlanProjectionError", "PLAN_VIEW_SCHEMA", "project_admitted_plan"]

PLAN_VIEW_SCHEMA = "mastermind.admitted_execution_plan_view.v1"
_ADMISSION_STATE = "ADMITTED"

_COO_PLAN_ADMISSION_SCHEMA_V1 = "mastermind.coo_plan_admission/v1"
_COO_PLAN_ADMISSION_SCHEMA_V2 = "mastermind.coo_plan_admission/v2"
_EXECUTION_PLAN_SCHEMA_V1 = "mastermind.execution_plan/v1"
_EXECUTION_PLAN_SCHEMA_V2 = "mastermind.execution_plan/v2"
_EXECUTION_PLAN_SCHEMA_V3 = "mastermind.execution_plan/v3"
_EXECUTION_PLAN_SCHEMA_V4 = "mastermind.execution_plan/v4"
_ADMISSION_SCHEMAS = (_COO_PLAN_ADMISSION_SCHEMA_V1, _COO_PLAN_ADMISSION_SCHEMA_V2)
_EXECUTION_PLAN_SCHEMAS = (
    _EXECUTION_PLAN_SCHEMA_V1,
    _EXECUTION_PLAN_SCHEMA_V2,
    _EXECUTION_PLAN_SCHEMA_V3,
    _EXECUTION_PLAN_SCHEMA_V4,
)
# Canonical pairing: dependency-carrying plans v3/v4 ride admission v2, while
# v1/v2 plans ride admission v1 and project empty dependency lists.
_DEPENDENCY_PLAN_SCHEMAS = frozenset(
    {_EXECUTION_PLAN_SCHEMA_V3, _EXECUTION_PLAN_SCHEMA_V4}
)

_MAX_PLAN_STEPS = 8
_MAX_OBJECTIVE_TEXT = 4096

# Defensive shapes for exactly the fields this view displays.  The canonical
# validators remain the only admission revalidators; nothing here re-derives
# reservation arithmetic, grants, capacity or child creation.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_IDENTITY_RE = re.compile(r"^[0-9a-f]{32}$")
_BUSINESS_IMPACTS = frozenset({"routine", "material", "critical"})
_REDACTED_TEXT = "agent_os_detail_redacted"

_ERROR_MESSAGES: dict[str, str] = {
    "SOURCE_CHANGED": "admitted plan source changed",
    "SOURCE_UNAVAILABLE": "admitted plan source unavailable",
    "CONTENT_WITHHELD": "admitted plan content withheld",
    "CONTENT_OVER_BUDGET": "admitted plan content exceeds the display budget",
}


class FabricPlanProjectionError(Exception):
    """Typed closed refusal with one fixed code and one fixed safe message."""

    def __init__(self, code: str) -> None:
        message = _ERROR_MESSAGES.get(code)
        if message is None:
            raise ValueError("projection refusal code is outside the closed set")
        self.code = code
        self.message = message
        super().__init__(message)


def _refuse(code: str) -> NoReturn:
    raise FabricPlanProjectionError(code)


def _identifier(value: object) -> str | None:
    return value if type(value) is str and _IDENTIFIER_RE.fullmatch(value) else None


def _digest(value: object) -> str | None:
    return value if type(value) is str and _DIGEST_RE.fullmatch(value) else None


def _sample(value: object) -> int | None:
    """One nonnegative integer progress sample; booleans are never integers."""

    return value if type(value) is int and value >= 0 else None


def _validate_observation(
    snapshot: BoundedAdmittedPlanSnapshot, receipt: RuntimeReadObservationReceipt
) -> None:
    """Apply the finalized-receipt law and the self-root identity joins."""

    if not isinstance(receipt, RuntimeReadObservationReceipt):
        _refuse("SOURCE_UNAVAILABLE")
    if receipt.schema != "mastermind.runtime_read_observation.v1":
        _refuse("SOURCE_UNAVAILABLE")
    state = receipt.state
    if state == "CONFLICT":
        _refuse("SOURCE_CHANGED")
    if state != "SAME":
        _refuse("SOURCE_UNAVAILABLE")
    identity = receipt.source_identity
    if type(identity) is not str or _REQUEST_IDENTITY_RE.fullmatch(identity) is None:
        _refuse("SOURCE_UNAVAILABLE")
    before, after = _sample(receipt.before), _sample(receipt.after)
    if before is None or after is None or before != after:
        _refuse("SOURCE_UNAVAILABLE")
    if not isinstance(snapshot, BoundedAdmittedPlanSnapshot):
        _refuse("SOURCE_UNAVAILABLE")
    if snapshot.observation_source_identity != identity:
        _refuse("SOURCE_UNAVAILABLE")
    metadata = snapshot.root_metadata
    if not isinstance(metadata, BoundedRoleResultRootMetadata):
        _refuse("SOURCE_UNAVAILABLE")
    root_job_id = _identifier(snapshot.root_job_id)
    if (
        root_job_id is None
        or metadata.root_job_id != root_job_id
        or metadata.job_id != root_job_id
        or metadata.orchestration_role != "aggregation"
    ):
        _refuse("SOURCE_UNAVAILABLE")
    if metadata.work_ref is not None and (
        type(metadata.work_ref) is not str or not metadata.work_ref
    ):
        _refuse("SOURCE_UNAVAILABLE")


def _validated_headers(
    admission: dict[str, Any], plan: dict[str, Any], root_job_id: str
) -> tuple[str, str, str, str, str, str]:
    """Join and return the closed identity header, paired schema versions first."""

    admission_schema = admission.get("schema_version")
    plan_schema = plan.get("schema_version")
    if (
        type(admission_schema) is not str
        or type(plan_schema) is not str
        or admission_schema not in _ADMISSION_SCHEMAS
        or plan_schema not in _EXECUTION_PLAN_SCHEMAS
    ):
        _refuse("SOURCE_UNAVAILABLE")
    expected_admission_schema = (
        _COO_PLAN_ADMISSION_SCHEMA_V2
        if plan_schema in _DEPENDENCY_PLAN_SCHEMAS
        else _COO_PLAN_ADMISSION_SCHEMA_V1
    )
    if admission_schema != expected_admission_schema:
        _refuse("SOURCE_UNAVAILABLE")
    if (
        _identifier(admission.get("root_job_id")) != root_job_id
        or _identifier(plan.get("root_job_id")) != root_job_id
    ):
        _refuse("SOURCE_UNAVAILABLE")
    plan_attempt_id = _identifier(plan.get("plan_attempt_id"))
    if (
        plan_attempt_id is None
        or _identifier(admission.get("plan_attempt_id")) != plan_attempt_id
    ):
        _refuse("SOURCE_UNAVAILABLE")
    policy_sha = _digest(admission.get("policy_sha"))
    plan_digest = _digest(admission.get("plan_digest"))
    reservation_digest = _digest(admission.get("reservation_digest"))
    if policy_sha is None or plan_digest is None or reservation_digest is None:
        _refuse("SOURCE_UNAVAILABLE")
    return (
        plan_schema,
        admission_schema,
        plan_attempt_id,
        policy_sha,
        plan_digest,
        reservation_digest,
    )


def _dependencies(step: dict[str, Any], earlier_step_ids: set[str]) -> list[str]:
    """Project the validated dependency list; duplicate/forward/unknown refuse."""

    raw = step.get("prerequisite_step_ids")
    if not isinstance(raw, list):
        _refuse("SOURCE_UNAVAILABLE")
    dependencies: list[str] = []
    for item in raw:
        dependency = _identifier(item)
        if dependency is None or dependency not in earlier_step_ids:
            _refuse("SOURCE_UNAVAILABLE")
        if dependency in dependencies:
            _refuse("SOURCE_UNAVAILABLE")
        dependencies.append(dependency)
    return dependencies


def _display_objective(value: object) -> str:
    """Display one objective only when the incumbent owner returns it unchanged."""

    if type(value) is not str or not value:
        _refuse("CONTENT_WITHHELD")
    if len(value) > _MAX_OBJECTIVE_TEXT:
        _refuse("CONTENT_OVER_BUDGET")
    projected = _safe_text(value)
    if projected is None or projected == _REDACTED_TEXT or projected != value:
        _refuse("CONTENT_WITHHELD")
    return projected


def _projected_steps(
    plan_schema: str, admission: dict[str, Any], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Project the ordered steps, reserving effective review from the admission."""

    plan_steps = plan.get("steps")
    reserved_steps = admission.get("steps")
    if not isinstance(plan_steps, list) or not plan_steps or len(plan_steps) > _MAX_PLAN_STEPS:
        _refuse("SOURCE_UNAVAILABLE")
    if not isinstance(reserved_steps, list) or len(reserved_steps) != len(plan_steps):
        _refuse("SOURCE_UNAVAILABLE")
    carries_dependencies = plan_schema in _DEPENDENCY_PLAN_SCHEMAS
    steps: list[dict[str, Any]] = []
    earlier_step_ids: set[str] = set()
    for ordinal, (step, reserved) in enumerate(zip(plan_steps, reserved_steps)):
        if not isinstance(step, dict) or not isinstance(reserved, dict):
            _refuse("SOURCE_UNAVAILABLE")
        if type(step.get("ordinal")) is not int or step["ordinal"] != ordinal:
            _refuse("SOURCE_UNAVAILABLE")
        if type(reserved.get("ordinal")) is not int or reserved["ordinal"] != ordinal:
            _refuse("SOURCE_UNAVAILABLE")
        step_id = _identifier(step.get("step_id"))
        if step_id is None or step_id in earlier_step_ids:
            _refuse("SOURCE_UNAVAILABLE")
        if reserved.get("plan_step_id") != step_id:
            _refuse("SOURCE_UNAVAILABLE")
        # Effective review_required is the revalidated reservation's value; it
        # may strengthen the planner's request and is never weakened here.
        review_required = reserved.get("review_required")
        if type(review_required) is not bool:
            _refuse("SOURCE_UNAVAILABLE")
        if type(step.get("review_required")) is not bool:
            _refuse("SOURCE_UNAVAILABLE")
        if step["review_required"] and not review_required:
            _refuse("SOURCE_UNAVAILABLE")
        business_impact = step.get("business_impact")
        if type(business_impact) is not str or business_impact not in _BUSINESS_IMPACTS:
            _refuse("SOURCE_UNAVAILABLE")
        dependencies = _dependencies(step, earlier_step_ids) if carries_dependencies else []
        if carries_dependencies and reserved.get("prerequisite_step_ids") != dependencies:
            _refuse("SOURCE_UNAVAILABLE")
        steps.append(
            {
                "ordinal": ordinal,
                "step_id": step_id,
                "objective": _display_objective(step.get("objective")),
                "business_impact": business_impact,
                "review_required": review_required,
                "prerequisite_step_ids": dependencies,
            }
        )
        earlier_step_ids.add(step_id)
    return steps


def project_admitted_plan(
    snapshot: BoundedAdmittedPlanSnapshot, receipt: RuntimeReadObservationReceipt
) -> dict[str, Any]:
    """Project one finalized same-observation plan read into the closed view."""

    _validate_observation(snapshot, receipt)
    admission = snapshot.admission
    plan = snapshot.plan
    if not isinstance(admission, dict) or not isinstance(plan, dict):
        _refuse("SOURCE_UNAVAILABLE")
    (
        plan_schema,
        admission_schema,
        plan_attempt_id,
        policy_sha,
        plan_digest,
        reservation_digest,
    ) = _validated_headers(admission, plan, snapshot.root_job_id)
    return {
        "schema": PLAN_VIEW_SCHEMA,
        "plan_schema_version": plan_schema,
        "admission_schema_version": admission_schema,
        "root_job_id": snapshot.root_job_id,
        "plan_attempt_id": plan_attempt_id,
        "policy_sha": policy_sha,
        "plan_digest": plan_digest,
        "reservation_digest": reservation_digest,
        "admission_state": _ADMISSION_STATE,
        "steps": _projected_steps(plan_schema, admission, plan),
    }
