#!/usr/bin/env python3
"""Read-only SOURCE preflight for the held BytePlus personal coding-tool lane.

Run from the repository root using:
    python -m scripts.byteplus_coding_plan_preflight

It calls existing catalog/Model Router/activation-blocker owners. Never reads
secrets, CLI sessions, host process state or provider quota; never dispatches.
A report is not a live Capacity fact or an admission receipt.
"""
from __future__ import annotations

import json

from control_plane.claude_subscription_worker import _usage_policy_satisfied
from control_plane.model_router import ModelRouter
from control_plane.subscription_catalog import compose_catalog_digest
from control_plane.subscription_harness_bindings import (
    autonomous_activation_blockers, canary_blockers, get_binding,
)
from control_plane.subscription_provider_profiles import get_profile
from control_plane.worker_adapter import adapter_descriptor

_PROFILE = "byteplus-coding-plan-personal"
_BINDING = "byteplus-coding-plan-personal.claude-code-anthropic"
_ALIAS = "byteplus.attended"


def source_preflight() -> dict[str, object]:
    profile = get_profile(_PROFILE)
    binding = get_binding(_BINDING)
    descriptor = adapter_descriptor(binding.adapter_id)
    router = ModelRouter.load()
    provider = router.providers["byteplus"]
    alias = router.model_aliases[_ALIAS]
    in_automatic_tiers = any(
        _ALIAS in tier.model_aliases
        for work_routes in router.routes.values()
        for risk in ("routine", "elevated")
        for tier in work_routes[risk]
    )
    if (
        not profile.supported_tool_only
        or profile.autonomous_allowed
        or binding.autonomous_allowed
        or provider.enabled
        or provider.autonomous_allowed
        or alias.worker_eligible
        or in_automatic_tiers
    ):
        raise RuntimeError("BytePlus personal policy unexpectedly armed")
    if binding.implementation_state != "SPEC_ONLY":
        raise RuntimeError("BytePlus canary implementation state unexpectedly changed")
    if binding.profile_id != profile.profile_id or binding.provider != profile.provider:
        raise RuntimeError("BytePlus profile/binding identity drift")
    if binding.effective_base_url != "https://ark.ap-southeast.bytepluses.com/api/coding":
        raise RuntimeError("BytePlus Coding Plan endpoint drift")
    statically_allowed = _usage_policy_satisfied(profile, "interactive_canary")
    if not statically_allowed or _usage_policy_satisfied(profile, "executive_worker"):
        raise RuntimeError("BytePlus supported-tool policy drift")
    canary = canary_blockers(
        binding,
        adapter_implemented=descriptor.implemented,
        provider_realm_enrolled=False,  # not checked; never presume enrollment
        capacity_known=False,  # rounded account usage is not capacity
        usage_policy_satisfied=statically_allowed,
    )
    autonomous = autonomous_activation_blockers(
        binding,
        adapter_implemented=descriptor.implemented,
        provider_realm_enrolled=False,
        capacity_known=False,
        real_canary_passed=False,
        usage_policy_satisfied=False,  # real user/harness use not attested
    )
    return {
        "schema": "mastermind.byteplus_coding_plan_source_preflight/v1",
        "evidence_scope": "SOURCE_ONLY",
        "live_provider_calls": False,
        "credential_read": False,
        "account_tier_observed": False,
        "real_canary_observed": False,
        "quota_debit_observed": False,
        "provider_realm_receipt_observed": False,
        "capacity_owner_fact_observed": False,
        "binding_id": binding.binding_id,
        "profile_id": profile.profile_id,
        "source_catalog_digest": compose_catalog_digest(),
        "endpoint": binding.effective_base_url,
        "models_by_source_role": {key: profile.models[key] for key in sorted(binding.model_classes)},
        "individual_supported_tool_mode_statically_allowed": statically_allowed,
        "canary_preparation_only": True,
        "canary_start_authorized": False,
        "canary_source_blockers": list(canary),
        "autonomous_start_authorized": False,
        "production_source_blockers": list(autonomous),
        "actual_concurrent_worker_limit": None,
        "estimated_startable_jobs": None,
        "additional_owner_proofs_required": [
            "qualified_supported_tool_binary_and_isolation",
            "attended_subscriber_session_and_actual_model_response",
            "current_provider_account_and_seat_use_rights",
            "provider_issued_realm_enrollment",
            "capacity_owner_fact_and_actual_quota_units",
            "provider_quota_debit_and_served_model",
            "accepted_release_and_production_path",
        ],
    }


def main() -> None:
    # This is a local, non-privileged SOURCE diagnostic; no activate command.
    print(json.dumps(source_preflight(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
