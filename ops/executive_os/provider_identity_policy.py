"""Closed, secret-free Codex provider identity policy.

The company workspace and dedicated Personal Pro workers are different trust
realms.  Keeping the policy in one pure module prevents the live identity
probe and the readiness-receipt consumer from accepting different identities.
"""
from __future__ import annotations

from typing import Any


COMPANY_WORKSPACE_BINDING_CLASS = "company-workspace-admin-attested"
PERSONAL_PRO_WORKER_BINDING_CLASS = "personal-pro-dedicated-worker-attested"

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
    "COMPANY_WORKSPACE_BINDING_CLASS",
    "EXPECTED_AUTH_MODE",
    "PERSONAL_PRO_PLAN_TYPES",
    "PERSONAL_PRO_WORKER_BINDING_CLASS",
    "WORKSPACE_BINDING_CLASSES",
    "evaluate_identity_policy",
]
