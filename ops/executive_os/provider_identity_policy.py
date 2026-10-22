"""Closed, secret-free Codex provider identity policy.

The company workspace and dedicated Personal Pro workers are different trust
realms.  Keeping the policy in one pure module prevents the live identity
probe and the readiness-receipt consumer from accepting different identities.
"""
from __future__ import annotations

from typing import Any


COMPANY_WORKSPACE_BINDING_CLASS = "company-workspace-admin-attested"
PERSONAL_PRO_WORKER_BINDING_CLASS = "personal-pro-dedicated-worker-attested"

# One reviewed recovery preimage. This digest grants neither auth continuity
# nor a retry; it closes the explicit current-credential qualification route.
COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256 = (
    "654abd66f6baef1b610a6c03fafe85f76fd81ed646266d3ff90db3c6e85e2a7d"
)

# Separate native incident: controller41117 stopped with exit65 at
# 2026-10-20T08:04:27.668781Z before reservation or inference. The retained
# evidence does not establish the writer or continuity of credential contents.
# These constants close eligibility; they are not approval for a live attempt.
NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256 = (
    "2bca56bcf84b1c5332879eaa22f23f521b37cea30c01dfe5936c3923c3f651cf"
)
NATIVE_PROBE_DRIFT_EVIDENCE_SHA256 = (
    "ffa2dec44d1d81569be113ebcd4b199464ba8e50e100b894196c32e82fa50d42"
)
# A pre-reservation probe refusal leaves the PASS preimage unchanged. The
# broker's durable request identity, not the preimage alone, fences that probe.
NATIVE_PROBE_DRIFT_REQUEST_ID = "mmos-native-probe-drift-2bca-20261022-v1"

EXPECTED_AUTH_MODE = {
    "service-account": "agentIdentity",
    "personal-access-token": "personalAccessToken",
    "device-auth": "chatgpt",
}

COMPANY_PLAN_TYPES = frozenset(
    {
        "team",
        "self_serve_business_prolite",
        "self_serve_business_usage_based",
        "business",
        "ent26",
        "enterprise_cbp_automation",
        "enterprise_cbp_usage_based",
        "enterprise",
        "edu",
    }
)
PERSONAL_PRO_PLAN_TYPES = frozenset({"pro"})
WORKSPACE_BINDING_CLASSES = frozenset(
    {COMPANY_WORKSPACE_BINDING_CLASS, PERSONAL_PRO_WORKER_BINDING_CLASS}
)


def evaluate_identity_policy(
    *,
    expected_kind: str,
    auth_mode: str | None,
    account_type: str,
    plan_type: str,
    requires_openai_auth: Any,
    workspace_binding_class: str,
) -> str | None:
    """Return one bounded refusal code or ``None`` for a passing identity."""

    if expected_kind not in EXPECTED_AUTH_MODE:
        return "credential_kind_unknown"
    if auth_mode not in EXPECTED_AUTH_MODE.values():
        return "auth_mode_missing_or_unknown"
    if auth_mode != EXPECTED_AUTH_MODE[expected_kind]:
        return "auth_mode_policy_mismatch"
    if account_type != "chatgpt":
        return "account_type_not_chatgpt"
    if requires_openai_auth is not True:
        return "openai_auth_requirement_malformed"

    if workspace_binding_class == COMPANY_WORKSPACE_BINDING_CLASS:
        if plan_type not in COMPANY_PLAN_TYPES:
            return "company_plan_required"
        return None

    if workspace_binding_class == PERSONAL_PRO_WORKER_BINDING_CLASS:
        if expected_kind != "device-auth":
            return "personal_pro_device_auth_required"
        if plan_type not in PERSONAL_PRO_PLAN_TYPES:
            return "personal_pro_plan_required"
        return None

    return "workspace_binding_class_unknown"


__all__ = [
    "COMPANY_PLAN_TYPES",
    "COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256",
    "NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256",
    "NATIVE_PROBE_DRIFT_EVIDENCE_SHA256",
    "NATIVE_PROBE_DRIFT_REQUEST_ID",
    "COMPANY_WORKSPACE_BINDING_CLASS",
    "EXPECTED_AUTH_MODE",
    "PERSONAL_PRO_PLAN_TYPES",
    "PERSONAL_PRO_WORKER_BINDING_CLASS",
    "WORKSPACE_BINDING_CLASSES",
    "evaluate_identity_policy",
]
