"""Read-only catalog helpers shared by provider realm and canary admission."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from control_plane.subscription_harness_bindings import HarnessBindingError


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def compose_catalog_digest(
    *,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> str:
    from control_plane.subscription_harness_bindings import (
        load_bindings,
        validate_bindings,
    )
    from control_plane.subscription_provider_profiles import (
        load_profiles,
        validate_profiles,
    )

    profiles = (
        validate_profiles(profiles_document)
        if profiles_document is not None
        else load_profiles()
    )
    bindings = (
        validate_bindings(bindings_document, profiles_document=profiles)
        if bindings_document is not None
        else load_bindings(profiles_document=profiles)
    )
    return hashlib.sha256(
        _canonical_json({"bindings": bindings, "profiles": profiles}).encode("utf-8")
    ).hexdigest()


def get_binding(
    binding_id: str,
    *,
    document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> Any:
    from control_plane.subscription_harness_bindings import (
        load_bindings,
        validate_bindings,
    )
    from control_plane.subscription_provider_profiles import (
        load_profiles,
        validate_profiles,
    )

    if not isinstance(binding_id, str) or not binding_id:
        raise HarnessBindingError("binding_id is required")
    profiles = (
        validate_profiles(profiles_document)
        if profiles_document is not None
        else load_profiles()
    )
    bindings = (
        validate_bindings(document, profiles_document=profiles)
        if document is not None
        else load_bindings(profiles_document=profiles)
    )
    binding = bindings.get("bindings", {}).get(binding_id)
    if binding is None:
        raise HarnessBindingError(f"unknown harness binding {binding_id!r}")
    if binding.get("binding_id", binding_id) != binding_id:
        raise HarnessBindingError(f"binding {binding_id!r} does not match its catalog key")
    from control_plane.subscription_harness_bindings import get_binding as binding_lookup

    return binding_lookup(
        binding_id,
        document={**document, "bindings": {binding_id: binding}}
        if document is not None
        else None,
        profiles_document=profiles,
    )


def project_byteplus_plan_readback(
    holdings: Mapping[str, Any],
    usage: Mapping[str, Any],
    *,
    subscription_ref: str | None = None,
    verified_at_unix: int | None = None,
) -> dict[str, Any]:
    """Reduce official BytePlus management readbacks to a NON-authoritative fact.

    Caller must obtain vendor records through its *existing* authenticated
    credential owner and separately attest freshness/account binding. This
    function accesses no credentials, files, clocks, providers or leases.
    Whole-number percentages never imply a free-request count, worker slots
    or permission for an unattended Coding Plan inference backend.
    """
    from datetime import datetime
    import re

    def refuse(message: str) -> None:
        raise HarnessBindingError("BytePlus readback invalid: " + message)

    if not isinstance(holdings, Mapping) or not isinstance(usage, Mapping):
        refuse("plan and usage documents must be mappings")
    plans = holdings.get("plans")
    items = usage.get("items")
    if not isinstance(plans, list) or not isinstance(items, list):
        refuse("plan and usage arrays required")
    candidates = [
        row for row in plans if isinstance(row, Mapping)
        and row.get("key") == "coding-plan" and row.get("scope") == "personal"
    ]
    measurements = [
        row for row in items if isinstance(row, Mapping)
        and row.get("product") == "coding-plan" and row.get("edition") == "personal"
    ]
    if len(candidates) != 1 or len(measurements) != 1:
        refuse("exactly one personal Coding Plan required")
    plan, measurement = candidates[0], measurements[0]
    if plan.get("name") != "Coding Plan" or plan.get("tier") != "pro" or plan.get("status") != "Running":
        refuse("personal Pro subscription not reported Running")
    if measurement.get("subscribed") is not True:
        refuse("measurement must report active subscription")
    # BytePlus Ark CLI v1.0.42 reports updated_at on the *matched usage item*,
    # not at the root. Keep the earlier root-only shape for existing callers
    # without accepting contradictory measurements from one readback.
    item_has_timestamp = "updated_at" in measurement
    root_has_timestamp = "updated_at" in usage
    item_timestamp = measurement.get("updated_at")
    root_timestamp = usage.get("updated_at")
    if item_has_timestamp and (type(item_timestamp) is not int or item_timestamp <= 0):
        refuse("provider measurement timestamp required")
    if root_has_timestamp and (type(root_timestamp) is not int or root_timestamp <= 0):
        refuse("provider measurement timestamp required")
    if item_has_timestamp and root_has_timestamp and item_timestamp != root_timestamp:
        refuse("conflicting provider measurement timestamps")
    timestamp = item_timestamp if item_has_timestamp else root_timestamp
    if type(timestamp) is not int or timestamp <= 0:
        refuse("provider measurement timestamp required")
    periods = measurement.get("periods")
    if not isinstance(periods, list) or len(periods) != 3:
        refuse("exactly three quota windows required")
    seen = {}
    for row in periods:
        if not isinstance(row, Mapping):
            refuse("quota window must be a mapping")
        label = row.get("label")
        percent = row.get("percent")
        if type(label) is not str or label not in ("session", "weekly", "monthly") or label in seen:
            refuse("unexpected or duplicated quota window")
        if type(percent) is not int or not 0 <= percent <= 100:
            refuse("quota percent must be a bounded whole number")
        reset_at = row.get("reset_at")
        if label == "session":
            if reset_at is not None:
                refuse("unreviewed session reset")
        else:
            if not isinstance(reset_at, str) or len(reset_at) > 64:
                refuse("weekly/monthly offset timestamp required")
            try:
                dt = datetime.fromisoformat(reset_at)
                if dt.tzinfo is None or dt.utcoffset() is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError, OverflowError):
                refuse("invalid reset timestamp")
        seen[label] = {"used_percent_rounded": percent, "reset_at": reset_at}
    if set(seen) != {"session", "weekly", "monthly"}:
        refuse("missing quota window")
    # Stable opaque subscription identity comes from the existing account
    # owner, NEVER from a credential hash: rotating/adding keys creates no quota.
    if subscription_ref is not None and (
        type(subscription_ref) is not str
        or re.fullmatch(r"subscription-[0-9a-f]{64}", subscription_ref) is None
    ):
        refuse("opaque owner subscription reference required")
    if verified_at_unix is not None and (
        type(verified_at_unix) is not int or verified_at_unix <= 0
    ):
        refuse("verification timestamp must be a positive integer")
    exhausted = [key for key, row in seen.items() if row["used_percent_rounded"] == 100]
    # All three restrictions apply to the SAME subscription. Do not sum their
    # remaining percentages, derive request counts or reset at guessed UTC dates.
    constraints = "UNKNOWN"
    reasons = []
    if subscription_ref is None:
        reasons.append("subscription_identity_not_bound")
    if verified_at_unix is None:
        reasons.append("freshness_not_evaluated")
    elif not 0 <= verified_at_unix - timestamp <= 300:
        reasons.append("measurement_stale_or_future")
    else:
        for key in ("weekly", "monthly"):
            reset = datetime.fromisoformat(seen[key]["reset_at"]).timestamp()
            if reset <= verified_at_unix:
                reasons.append(key + "_reset_requires_new_readback")
    if not reasons:
        constraints = "EXHAUSTED" if exhausted else "NOT_EXHAUSTED_ROUNDED"
    # Whitelist only non-identifying control-plane fields. Never copy the
    # viewer/user/account/project profile returned by the authenticated CLI.
    return {
        "schema": "mastermind.byteplus_personal_plan_readback_projection/v1",
        "provider": "byteplus",
        "product": "coding_plan_personal",
        "tier_reported": "pro",
        "status_reported": "Running",
        "usage_observed_at_unix": timestamp,
        "windows": {key: seen[key] for key in ("session", "weekly", "monthly")},
        "subscription_ref": subscription_ref,
        "quota_constraint_state": constraints,
        "quota_constraint_reasons": reasons,
        "exhausted_windows": exhausted,
        "minimum_remaining_percent_rounded": min(
            100 - row["used_percent_rounded"] for row in seen.values()
        ),
        "quota_scope": "ONE_SUBSCRIPTION_ALL_MODELS_AND_KEYS",
        "independent_concurrency_observed": False,
        "account_identity_attested": False,
        "provider_origin_attested": False,
        "measurement_freshness_attested": False,
        "actual_request_counts_available": False,
        "actual_concurrency_limit_available": False,
        "estimated_startable_jobs": None,
        "suggested_parallelism": None,
        "live_admission": False,
        "autonomous_allowed": False,
        "usage_scope": "APPROVED_INDIVIDUAL_CODING_TOOL_ONLY",
    }


__all__ = [
    "HarnessBindingError",
    "compose_catalog_digest",
    "get_binding",
    "project_byteplus_plan_readback",
]
