"""Bounded provider rejection classification; admission/health stay with the router.

An HTTP server error is not proof that inference was never accepted. Classification
keeps replay permission, accounting certainty and future-route health separate.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re


@dataclass(frozen=True)
class ProviderFailure:
    category: str
    code: str
    rejected: bool = False
    retryable: bool = False
    owner_hold: bool = False
    scope: str = "route"


_POLICY = frozenset({
    "refusal", "org_under_review", "organization_under_review", "model_not_granted",
    "model_location_not_supported", "permission_denied", "access_denied",
    "content_policy_violation", "safety_refusal", "account_suspended", "account_banned",
    "plan_model_not_allowed", "plan_included_funding_unverified",
})
_EXHAUSTED = frozenset({
    "insufficient_quota", "accountquotaexceeded", "account_quota_exceeded",
    "credits_exhausted", "insufficient_credit", "insufficient_credits", "insufficient_balance",
    "subscription_exhausted", "plan_quota_exceeded", "usage_limit_reached",
    "billing_hard_limit_reached", "budget_exceeded", "monthly_quota_exceeded",
    "weekly_quota_exceeded", "credit_balance_too_low",
})
_ADMISSION = frozenset({
    "rate_limit_exceeded", "admission_capacity_exceeded", "overloaded_error",
    "capacity_exceeded", "too_many_requests", "resource_exhausted",
})


def classify(status: int, body: bytes) -> ProviderFailure:
    """Only stable error identifiers are returned; never retain provider prose."""
    codes = []
    try:
        value = json.loads(body[:4096])
        stack = [value]
        for _ in range(16):
            if not stack:
                break
            row = stack.pop()
            if not isinstance(row, dict):
                continue
            for key in ("code", "type", "Code", "Type"):
                token = row.get(key)
                if isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", token):
                    codes.append(token.lower())
            stack.extend(row.get(k) for k in ("error", "Error", "detail") if isinstance(row.get(k), dict))
    except (ValueError, UnicodeError):
        pass
    code = next((c for c in codes if c in _POLICY), None)
    if code or status in (401, 403):
        scope = ("request" if code in ("refusal", "content_policy_violation", "safety_refusal") else
                 "model" if code in ("model_not_granted", "model_location_not_supported", "plan_model_not_allowed") else "route")
        return ProviderFailure("permission", code or "http_" + str(status), True, False,
                               scope != "request", scope)
    code = next((c for c in codes if c in _EXHAUSTED), None)
    if code or status == 402:
        return ProviderFailure("quota_exhausted", code or "payment_required", True, True, True)
    code = next((c for c in codes if c in _ADMISSION), None)
    if status == 429 or (status in (503, 529) and code):
        return ProviderFailure("temporary_capacity", code or "rate_limit", True, True)
    if status >= 500:
        # Including nested-provider all_routes_failed and generic gateway errors.
        return ProviderFailure("execution_unknown", codes[0] if codes else "http_" + str(status))
    return ProviderFailure("invalid_request", codes[0] if codes else "http_" + str(status), True)
