"""Request policy for the existing Experiential gateway.

This is a stateless guard, not a scheduler or a second budget ledger. The
provider owns daily included-allowance enforcement. A promotional :free grant
is not a paid-plan entitlement. The provider
owns its prepaid wallet and subscription allowance. Configured plan entitlements
are distinct from authenticated observations of current remaining funds.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time

PLAN_MODES = frozenset({"legacy", "free_only", "free_and_uncensored"})
FREE_CHAT_MODELS = (
    "deepseek-v4.1-flash",
    "deepseek-v4.1-flash-1017",
    "gpt-6-luna",
    "clef",
    "clef-flash",
)
FREE_NATIVE_MODELS = {
    "jev-latest": "systemone",
    "gpt-6-luna-decisions": "decisions",
}
PAID_UNCENSORED_MODELS = (
    "deepseek-v4.1-flash-uncensored",
    "glm-5.3-flash-uncensored",
)
# Preference is for a NEW admitted selection only. This is never a retry ladder.
CHAT_ENDPOINTS = frozenset({"chat/completions", "responses"})
ROUTING_OVERRIDES = frozenset({
    "models", "fallbacks", "fallback", "provider", "providers", "route",
    "route_id", "routing", "routing_pool", "routing_pool_id", "api_key",
    "base_url", "extra_body", "extra_headers", "extra_query",
})


def plan_policy_digest(mode: str) -> str:
    """Bind an admitted Attempt to the exact deployed request policy."""
    if type(mode) is not str or mode not in PLAN_MODES:
        raise ValueError("unsupported Experiential plan policy")
    spec = {"version": 3, "included_funding": "max_plan_provider_stop_required", "mode": mode, "gateway_policy": "single_attempt_no_fallback", "free_chat": FREE_CHAT_MODELS,
            "free_native": FREE_NATIVE_MODELS, "paid": PAID_UNCENSORED_MODELS,
            "overrides": sorted(ROUTING_OVERRIDES)}
    return hashlib.sha256(json.dumps(spec, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


class PlanRequestRefused(ValueError):
    """Stable, nonsecret reason, suitable for the existing gateway refusal."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _closed_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PlanRequestRefused("PLAN_DUPLICATE_JSON_FIELD")
        value[key] = item
    return value


def _invalid_constant(_value):
    raise PlanRequestRefused("PLAN_INVALID_JSON")


def validate_plan_request(mode: str, endpoint: str, body: bytes) -> str | None:
    """Validate exact wire target before RPM/slot reservation; never rewrite.

    Legacy mode preserves existing callers. Neither a body field nor a client
    header can select the deployment policy or enable paid inference.
    """
    if mode not in PLAN_MODES:
        raise ValueError("unsupported Experiential plan policy")
    if mode == "legacy":
        return None
    try:
        payload = json.loads(
            body, object_pairs_hook=_closed_object, parse_constant=_invalid_constant
        )
    except PlanRequestRefused:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanRequestRefused("PLAN_INVALID_JSON") from exc
    if type(payload) is not dict:
        raise PlanRequestRefused("PLAN_JSON_OBJECT_REQUIRED")
    if ROUTING_OVERRIDES.intersection(payload):
        raise PlanRequestRefused("PLAN_ROUTING_OVERRIDE_REFUSED")
    gateway = payload.get("gateway")
    if gateway is not None:
        safe = {"routing": {"allow_fallbacks": False},
                "retry": {"max_attempts_per_route": 1, "max_total_attempts": 1,
                          "backoff": {"type": "none"}}}
        if type(gateway) is not dict or gateway != safe:
            raise PlanRequestRefused("PLAN_ROUTING_OVERRIDE_REFUSED")
    model = payload.get("model")
    if type(model) is not str or not model:
        raise PlanRequestRefused("PLAN_EXACT_MODEL_REQUIRED")
    if model in FREE_CHAT_MODELS:
        if endpoint not in CHAT_ENDPOINTS:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "free"
    if model in FREE_NATIVE_MODELS:
        if endpoint != FREE_NATIVE_MODELS[model]:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "free"
    if model in PAID_UNCENSORED_MODELS:
        if mode != "free_and_uncensored":
            raise PlanRequestRefused("PLAN_PAID_LANE_DISABLED")
        if endpoint not in CHAT_ENDPOINTS:
            raise PlanRequestRefused("PLAN_MODEL_PROTOCOL_MISMATCH")
        return "paid_uncensored"
    # Promotional :free grants are not enrolled by a Max-plan declaration.
    # glm-5.3-uncensored is the old full model, not the selected Flash model.
    raise PlanRequestRefused("PLAN_MODEL_NOT_ALLOWED")


ANTHROPIC_ENDPOINTS = frozenset({"messages", "messages/count_tokens"})
_ANTHROPIC_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def parse_anthropic_models(raw: str) -> tuple[str, ...]:
    """Parse EXPLABS_ANTHROPIC_MODELS into exact admitted slugs.

    The operator-deployed list is the whole funding boundary for the
    Anthropic-wire surface: no expansion, aliasing or suffix matching.
    """
    if type(raw) is not str:
        raise ValueError("EXPLABS_ANTHROPIC_MODELS must be a string")
    models = []
    for item in raw.split(","):
        slug = item.strip()
        if not slug:
            continue
        if not _ANTHROPIC_SLUG_RE.match(slug):
            raise ValueError(f"invalid Anthropic model slug: {slug!r}")
        if slug in models:
            raise ValueError(f"duplicate Anthropic model slug: {slug!r}")
        models.append(slug)
    return tuple(models)


def anthropic_policy_digest(models) -> str:
    """Bind an Anthropic-wire caller to the exact deployed admitted catalogue."""
    if not isinstance(models, (tuple, list, frozenset)) or not all(
        isinstance(m, str) and m for m in models
    ) or len(set(models)) != len(models):
        raise ValueError("admitted Anthropic models must be unique nonempty strings")
    spec = {"version": 1, "surface": "anthropic_messages",
            "gateway_policy": "single_attempt_no_fallback",
            "admitted_models": sorted(models)}
    return hashlib.sha256(json.dumps(spec, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def validate_anthropic_plan_request(models, endpoint: str, body: bytes) -> str:
    """Validate an Anthropic Messages-wire target before RPM/slot reservation.

    Admission is membership in the operator-deployed catalogue only. A body
    field can never widen it, and there is no fallback to another model.
    """
    if endpoint not in ANTHROPIC_ENDPOINTS:
        raise ValueError("not an Anthropic-wire endpoint")
    if not isinstance(models, (tuple, list, frozenset)) or not models:
        raise PlanRequestRefused("PLAN_ANTHROPIC_NOT_ENABLED")
    try:
        payload = json.loads(
            body, object_pairs_hook=_closed_object, parse_constant=_invalid_constant
        )
    except PlanRequestRefused:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlanRequestRefused("PLAN_INVALID_JSON") from exc
    if type(payload) is not dict:
        raise PlanRequestRefused("PLAN_JSON_OBJECT_REQUIRED")
    if ROUTING_OVERRIDES.intersection(payload):
        raise PlanRequestRefused("PLAN_ROUTING_OVERRIDE_REFUSED")
    model = payload.get("model")
    if type(model) is not str or not model:
        raise PlanRequestRefused("PLAN_EXACT_MODEL_REQUIRED")
    if model not in set(models):
        raise PlanRequestRefused("PLAN_MODEL_NOT_ADMITTED")
    return "anthropic"


def require_included_funding(observation, *, organization_sha256, now=None):
    """Require account-specific provider enforcement, never a local opt-in.

    The documented public account API currently reports wallet/catalog data,
    not Max entitlement or the effective continuation setting. Its production
    reader therefore supplies no included-funding evidence and fails closed.
    A future provider-account reader must bind all of these facts; neither
    request JSON, environment flags nor declared allowances can satisfy them.
    This is a pure admission predicate, not a balance counter or setting writer.
    """
    current = time.time() if now is None else now
    if type(observation) is not dict:
        raise PlanRequestRefused("PLAN_INCLUDED_FUNDING_UNVERIFIED")
    expected = {
        "schema": "mastermind.experiential_included_funding/v1",
        "source": "authenticated_provider_account",
        "organization_sha256": organization_sha256,
        "plan_tier": "max",
        "plan_active": True,
        "daily_credits": 7000,
        "continue_on_credits": False,
        "provider_enforces_included_stop": True,
        "paid_uncensored_remains_available": True,
    }
    for key, wanted in expected.items():
        value = observation.get(key)
        if type(value) is not type(wanted) or value != wanted:
            raise PlanRequestRefused("PLAN_INCLUDED_FUNDING_UNVERIFIED")
    seen = observation.get("observed_at_unix")
    if (type(seen) not in (int, float) or not math.isfinite(seen)
            or type(current) not in (int, float) or not math.isfinite(current)
            or not 0 <= current - seen <= MAX_OBSERVATION_AGE_SECONDS):
        raise PlanRequestRefused("PLAN_INCLUDED_FUNDING_STALE")
    included = observation.get("included_models")
    if (type(included) is not list or any(type(v) is not str for v in included)
            or len(included) != len(set(included))
            or set(included) != set(FREE_CHAT_MODELS) | set(FREE_NATIVE_MODELS)):
        raise PlanRequestRefused("PLAN_INCLUDED_MODELS_UNVERIFIED")
    return {"funding_contract": "max_included", "paid_overflow": False,
            "observed_at_unix": seen}


PLAN_ACCOUNT_SCHEMA = "mastermind.experiential_plan_account/v1"
PLAN_OBSERVATION_SCHEMA = "mastermind.experiential_plan_observation/v1"
PLAN_CHAT_MODELS = frozenset(FREE_CHAT_MODELS + PAID_UNCENSORED_MODELS)
PLAN_MODELS = PLAN_CHAT_MODELS | frozenset(FREE_NATIVE_MODELS)
PLAN_ACCOUNT_PREFIX = "experiential-plan-"
PLAN_FREE_CREDITS_PER_DAY = 7000
PLAN_PAID_ALLOWANCE_USD_PER_MONTH = 200
MAX_OBSERVATION_AGE_SECONDS = 60


def route_policy_generation(base_url: str, path: str, mode: str) -> str:
    """Shared pure identity; no endpoint, credential or admission discovery."""
    digest = plan_policy_digest(mode)
    target = str(base_url).rstrip("/") + "\n" + path
    if mode != "legacy":
        target += "\n" + digest
    return hashlib.sha256(target.encode("utf-8")).hexdigest()


def plan_model_endpoint(model: str) -> str:
    """One exact model determines its wire protocol; callers cannot override it."""
    if model in FREE_NATIVE_MODELS:
        return FREE_NATIVE_MODELS[model]
    if model in PLAN_CHAT_MODELS:
        return "chat/completions"
    raise PlanRequestRefused("PLAN_MODEL_NOT_ALLOWED")


def select_plan_model(lane: str, available_models, requested_model=None) -> str:
    """Resolve one NEW selection. An existing Attempt must keep its exact pin.

    Availability is read from the host-owned authenticated catalog. There is no
    retry/fallback invocation here and no selection after a possible send.
    """
    if lane not in {"free", "paid_uncensored"}:
        raise PlanRequestRefused("PLAN_LANE_INVALID")
    if not isinstance(available_models, (list, tuple, set, frozenset)) or any(
        type(value) is not str for value in available_models
    ):
        raise PlanRequestRefused("PLAN_MODEL_AVAILABILITY_UNKNOWN")
    order = FREE_CHAT_MODELS if lane == "free" else PAID_UNCENSORED_MODELS
    available = frozenset(available_models)
    if requested_model is not None:
        eligible = set(order) | (set(FREE_NATIVE_MODELS) if lane == "free" else set())
        if requested_model not in eligible or requested_model not in available:
            raise PlanRequestRefused("PLAN_SELECTED_MODEL_UNAVAILABLE")
        return requested_model
    for model in order:
        if model in available:
            return model
    raise PlanRequestRefused("PLAN_NO_ELIGIBLE_MODEL")


def admit_plan_account(*, model, account, registration, observation, now=None):
    """Recheck fresh owner observations, without mirroring provider balances.

    This function is called by the incumbent pin admission, not by a second
    scheduler. The trusted host context supplies registration and authenticated
    gateway readback. A configured allowance is never returned as remaining.
    """
    if type(registration) is not dict or registration.get("schema") != PLAN_ACCOUNT_SCHEMA:
        raise PlanRequestRefused("PLAN_ACCOUNT_NOT_ENROLLED")
    org = registration.get("organization_sha256")
    if type(org) is not str or re.fullmatch(r"[0-9a-f]{64}", org) is None:
        raise PlanRequestRefused("PLAN_ORGANIZATION_IDENTITY_INVALID")
    expected_account = PLAN_ACCOUNT_PREFIX + org
    if account != expected_account or registration.get("account") != expected_account:
        raise PlanRequestRefused("PLAN_ACCOUNT_IDENTITY_MISMATCH")
    mode = registration.get("plan_policy")
    if mode not in {"free_only", "free_and_uncensored"}:
        raise PlanRequestRefused("PLAN_POLICY_NOT_ENROLLED")
    endpoint = plan_model_endpoint(model)
    lane = validate_plan_request(mode, endpoint, json.dumps({"model": model}).encode())
    if registration.get("policy_digest") != plan_policy_digest(mode):
        raise PlanRequestRefused("PLAN_POLICY_GENERATION_MISMATCH")
    if (registration.get("free_credits_per_day") != PLAN_FREE_CREDITS_PER_DAY
            or registration.get("paid_allowance_usd_per_month") != PLAN_PAID_ALLOWANCE_USD_PER_MONTH
            or registration.get("entitlement_source") != "chairman_declared_plan"
            or registration.get("funding") != "provider_prepaid_wallet"):
        raise PlanRequestRefused("PLAN_ENTITLEMENT_MISMATCH")
    if type(observation) is not dict or observation.get("schema") != PLAN_OBSERVATION_SCHEMA:
        raise PlanRequestRefused("PLAN_ACCOUNT_OBSERVATION_REQUIRED")
    if (observation.get("account") != expected_account
            or observation.get("organization_sha256") != org
            or observation.get("source") != "authenticated_gateway_metadata"
            or observation.get("policy_digest") != plan_policy_digest(mode)):
        raise PlanRequestRefused("PLAN_ACCOUNT_OBSERVATION_MISMATCH")
    observed = observation.get("observed_at_unix")
    current = time.time() if now is None else now
    if (type(observed) not in (int, float) or not math.isfinite(observed)
            or type(current) not in (int, float) or not math.isfinite(current)
            or not 0 <= current - observed <= MAX_OBSERVATION_AGE_SECONDS):
        raise PlanRequestRefused("PLAN_ACCOUNT_OBSERVATION_STALE")
    select_plan_model(lane, observation.get("available_models"), model)
    funding = {}
    if lane == "free":
        funding = require_included_funding(observation.get("included_funding"),
                                            organization_sha256=org, now=current)
    balance = observation.get("wallet_balance_usd")
    if type(balance) not in (int, float) or not math.isfinite(balance):
        raise PlanRequestRefused("PLAN_WALLET_OBSERVATION_INVALID")
    if lane == "paid_uncensored" and balance <= 0:
        raise PlanRequestRefused("PLAN_PREPAID_WALLET_EXHAUSTED")
    return {**funding, "account": expected_account, "plan_lane": lane, "endpoint": endpoint,
            "plan_policy": mode, "policy_digest": plan_policy_digest(mode),
            "quota_owner": "provider", "free_credits_remaining": None,
            "monthly_allowance_remaining_usd": None,
            "wallet_balance_usd_observed": balance,
            "observed_at_unix": observed}


def registered_plan_account(row, provider):
    """Pure Broker enrollment predicate; live admission still rechecks metadata."""
    if type(row) is not dict or type(provider) is not dict:
        return False
    registration = row.get("plan")
    if type(registration) is not dict or registration.get("schema") != PLAN_ACCOUNT_SCHEMA:
        return False
    org, mode = registration.get("organization_sha256"), registration.get("plan_policy")
    if type(org) is not str or re.fullmatch(r"[0-9a-f]{64}", org) is None:
        return False
    if mode not in {"free_only", "free_and_uncensored"}:
        return False
    account = PLAN_ACCOUNT_PREFIX + org
    return (provider.get("enabled") is True and row.get("enabled") is True
            and row.get("name") == registration.get("account") == account
            and provider.get("plan_gateway", {}).get("account") == account
            and registration.get("policy_digest") == plan_policy_digest(mode)
            and registration.get("free_credits_per_day") == PLAN_FREE_CREDITS_PER_DAY
            and registration.get("paid_allowance_usd_per_month") == PLAN_PAID_ALLOWANCE_USD_PER_MONTH
            and registration.get("entitlement_source") == "chairman_declared_plan"
            and registration.get("funding") == "provider_prepaid_wallet"
            and len(provider.get("accounts", [])) == 1)
