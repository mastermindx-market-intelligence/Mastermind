"""Pure displays of existing admitted-policy and host-status owner results.

The caller acquires the selected admitted plan and actual policy under the
existing root/catalogue/policy bracket, and authorizes before and after that
work. This module neither loads policy files nor samples the host. A policy
digest identifies source rules; it does not grant their full ceiling to a Job.
Host status is separately scoped and cannot establish project pause or ongoing
supervision. No collector, Runtime or transport is constructed here.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import UTC, datetime

from common.executive_workspace_contract import (
    PLAN_BODY_SCHEMA, bounded_canonical, canonical,
    validate_available_plan_observation, v3_selection,
)
from common.workspace_autonomy_read_contract import BODY_SCHEMA, MAX_RESPONSE_BYTES
from control_plane.executive_coo_policy import CooCyclePolicy

_HASH = re.compile(r"[0-9a-f]{64}")
_SHA = re.compile(r"[0-9a-f]{40}")
_PLAN_FIELDS = {"schema", "plan_schema_version", "admission_schema_version",
                "root_job_id", "plan_attempt_id", "policy_sha", "plan_digest",
                "reservation_digest", "admission_state", "steps"}
_LIMIT_FIELDS = {"schema_version", "max_fan_out_per_parent", "max_depth",
                 "max_repair_rounds", "max_review_attempts_per_job",
                 "max_children_total", "max_attempts_per_orchestration_job",
                 "review_job_attempt_limit", "allowed_child_cost_classes"}


def _refuse():
    raise ValueError("AUTONOMY_SOURCE_INVALID")


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def compose_autonomy_policy_read(plan_body, policy):
    """Project one already-qualified admitted root, retaining its source receipt.

    The original plan reader owns admission and physical-read/source closure.
    This adds no currentness inference and no independent policy selection.
    """
    if (type(plan_body) is not dict
            or set(plan_body) != {"schema", "selection", "availability", "reason_codes",
                                  "source_observation", "plan"}
            or plan_body["schema"] != PLAN_BODY_SCHEMA
            or plan_body["availability"] != "AVAILABLE" or plan_body["reason_codes"] != []
            or type(policy) is not CooCyclePolicy):
        _refuse()
    try:
        selected = v3_selection(plan_body["selection"])
        validate_available_plan_observation(plan_body["source_observation"], selected)
    except (TypeError, ValueError):
        _refuse()
    plan = plan_body["plan"]
    if (type(plan) is not dict or set(plan) != _PLAN_FIELDS
            or plan["schema"] != "mastermind.admitted_execution_plan_view.v1"
            or plan["root_job_id"] != selected["root_job_id"]
            or plan["admission_state"] != "ADMITTED"
            or not all(_hash(plan[key]) for key in ("policy_sha", "plan_digest", "reservation_digest"))
            or not _hash(policy.policy_sha256)
            or plan["policy_sha"] != policy.policy_sha256
            or not _hash(policy.source_sha256)
            or type(plan["plan_schema_version"]) is not str
            or plan["plan_schema_version"] not in {
                "mastermind.execution_plan/v1", "mastermind.execution_plan/v2",
                "mastermind.execution_plan/v3", "mastermind.execution_plan/v4",
                "mastermind.execution_plan/v5"}
            or type(plan["admission_schema_version"]) is not str
            or plan["admission_schema_version"] != (
                "mastermind.coo_plan_admission/v3"
                if plan["plan_schema_version"] == "mastermind.execution_plan/v5"
                else "mastermind.coo_plan_admission/v2" if plan["plan_schema_version"] in {
                    "mastermind.execution_plan/v3", "mastermind.execution_plan/v4"}
                else "mastermind.coo_plan_admission/v1")
            or policy.schema_version != (
                2 if plan["plan_schema_version"] == "mastermind.execution_plan/v5" else 1)
            or type(plan["plan_attempt_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", plan["plan_attempt_id"]) is None
            or type(plan["steps"]) is not list
            or len(plan["steps"]) > (
                16 if plan["plan_schema_version"] == "mastermind.execution_plan/v5" else 8)):
        _refuse()
    limits = policy.to_dict()
    if (type(limits) is not dict or set(limits) != _LIMIT_FIELDS
            or limits["schema_version"] not in (1, 2)
            or any(type(limits[k]) is not int or limits[k] < 0
                   for k in _LIMIT_FIELDS - {"allowed_child_cost_classes"})
            or type(limits["allowed_child_cost_classes"]) is not list
            or not 1 <= len(limits["allowed_child_cost_classes"]) <= 16
            or any(type(x) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", x) is None
                   for x in limits["allowed_child_cost_classes"])
            or len(set(limits["allowed_child_cost_classes"])) != len(limits["allowed_child_cost_classes"])
            or hashlib.sha256(canonical(limits)).hexdigest() != policy.policy_sha256):
        _refuse()
    out = {"schema": BODY_SCHEMA, "selection": dict(selected), "availability": "AVAILABLE",
           "reason_codes": [], "source_observation": copy.deepcopy(plan_body["source_observation"]),
           "policy": {"scope": "ADMITTED_ROOT", "policy_sha": policy.policy_sha256,
                      "source_sha256": policy.source_sha256, "plan_digest": plan["plan_digest"],
                      "reservation_digest": plan["reservation_digest"],
                      "limits": copy.deepcopy(limits)}}
    try:
        bounded_canonical(out, limit=MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError):
        _refuse()
    return out


def project_host_autonomy_status(snapshot, *, expected_sha, observed_at):
    """Display an existing status snapshot; never invoke its host collector.

    The host read remains a separately installed/granted capability. Supplying
    this pure projector cannot perform or unlock a held host action.
    """
    from control_plane.executive_autonomy import StatusEvidence
    from ops.executive_os.autonomy_control import StatusSnapshot, status_document
    if (type(snapshot) is not StatusSnapshot or type(snapshot.evidence) is not StatusEvidence
            or type(expected_sha) is not str or _SHA.fullmatch(expected_sha) is None
            or type(snapshot.expected_sha) is not str
            or snapshot.expected_sha != expected_sha
            or type(observed_at) is not datetime or observed_at.utcoffset() is None):
        _refuse()
    evidence = snapshot.evidence
    if (any(type(getattr(evidence, key)) is not bool for key in (
            "transaction_present", "control_armed", "worker_armed", "receipt_matches",
            "config_drift", "identity_reconciled"))
            or (snapshot.installed_sha is not None and (
                type(snapshot.installed_sha) is not str or _SHA.fullmatch(snapshot.installed_sha) is None))
            or any(x is not None and not _hash(x) for x in (
                snapshot.control_config_sha256, snapshot.worker_config_sha256))
            or (evidence.receipt_state is not None and (type(evidence.receipt_state) is not str
                or re.fullmatch(r"[A-Z][A-Z_]{0,63}", evidence.receipt_state) is None))
            or type(evidence.service_state) is not str
            or re.fullmatch(r"[A-Z][A-Z_]{0,63}", evidence.service_state) is None
            or (snapshot.refusal_code is not None and (type(snapshot.refusal_code) is not str
                or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", snapshot.refusal_code) is None))
            or (evidence.readiness_expires_at is not None and (
                type(evidence.readiness_expires_at) is not datetime
                or evidence.readiness_expires_at.utcoffset() is None))):
        _refuse()
    result = {"scope": "HOST", "observed_at": observed_at.astimezone(UTC).isoformat(),
              "status": status_document(snapshot, now=observed_at)}
    bounded_canonical(result, limit=MAX_RESPONSE_BYTES - 1)
    return result
