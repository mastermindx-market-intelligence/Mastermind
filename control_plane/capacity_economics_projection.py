"""Pure bridge from Model Router suitability to Provider Control quota economics.

This module deliberately does not calculate provider quota, mutate routing policy,
select a worker, or claim Executive capacity. It consumes the preview-only output
owned by Shared AI Provider Control and projects one economic preference only when
that preview stays inside the FIRST lawful Model Router suitability tier.

The output remains advisory and requires claim-time revalidation by the existing
Capacity Fabric / Executive claim owner.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from typing import Any

QUOTA_PREVIEW_SCHEMA = "mastermind.quota_economics_preview/v1"
PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v1"

# Commercial API model IDs, not Personal Coding Plan names. These are
# catalog candidates until exact ProviderRealm, ModelRouter and Capacity
# owners independently qualify the live adapter/credential/model.
BYTEPLUS_COMMERCIAL_FLASH_MODELS = {
    "byteplus-modelark.glm-5.3-flash": "glm-5-3-flash-260828",
    "byteplus-modelark.deepseek-v4.1-flash": "deepseek-v4-1-flash-261017",
}
BYTEPLUS_COMMERCIAL_MODEL_PINS = {
    **BYTEPLUS_COMMERCIAL_FLASH_MODELS,
    "byteplus-modelark.commercial-coding": "dola-seed-2-1-turbo-260628",
}
_ZAI_FLASH_MODELS = frozenset({"glm-5.3-flash", "glm-5-3-flash-260828"})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class CapacityEconomicsProjectionError(ValueError):
    """The router/quota preview composition is invalid or non-actionable."""


@dataclasses.dataclass(frozen=True, slots=True)
class QuotaPreviewFreshness:
    """Owner-supplied advisory timestamps; never a signed quota/Worker grant.

    observed_at: independent Provider Control observation time, not a value
    copied from the untrusted preview. verified_at: the owner's current time
    at evaluation. Neither value is sampled implicitly in this projection.
    """
    observed_at: datetime
    verified_at: datetime
    max_age_seconds: int


def _source_freshness_ok(as_of: str, freshness: Any) -> bool:
    if type(freshness) is not QuotaPreviewFreshness:
        return False
    age_limit = freshness.max_age_seconds
    if type(age_limit) is not int or not 1 <= age_limit <= 900:
        return False
    stamps = (freshness.observed_at, freshness.verified_at)
    if any(type(stamp) is not datetime or stamp.tzinfo is None
           or stamp.utcoffset() is None for stamp in stamps):
        return False
    try:
        preview_time = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return False
    if preview_time.tzinfo is None or preview_time.utcoffset() is None:
        return False
    observed = freshness.observed_at.astimezone(timezone.utc)
    verified = freshness.verified_at.astimezone(timezone.utc)
    preview = preview_time.astimezone(timezone.utc)
    observed_lag = (observed - preview).total_seconds()
    verified_lag = (verified - observed).total_seconds()
    end_to_end_age = (verified - preview).total_seconds()
    return (
        0 <= observed_lag
        and 0 <= verified_lag
        and 0 <= end_to_end_age <= age_limit
    )


def _token(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise CapacityEconomicsProjectionError(f"{field} must be a bounded identifier")
    return value


def _mentions_byteplus(value: str) -> bool:
    """Conservatively refuse BytePlus-looking identities in untrusted previews.

    Provider Control's preview is not an authoritative binding. Identifiers
    can add prefixes, suffixes, or ASCII separators; none may convert a
    personal Coding Plan into an autonomous worker. A separately licensed
    commercial route needs its own reviewed owner, not a preview rename.
    """
    compact = re.sub(r"[-._:]", "", value.casefold())
    return "byteplus" in compact


def _canonical_model_router_matches(candidate: Any) -> bool:
    """Reject caller-mutated router objects that are not the installed policy.

    A canonical source reload is a necessary source-integrity preflight,
    **not** the issuer/Worker/Capacity owner attestation. Until those owners
    issue independent receipts, live START remains held by codex_worker.
    """
    from control_plane.model_router import ModelRouter
    if type(candidate) is not ModelRouter:
        return False
    try:
        installed = ModelRouter.load()
    except (OSError, ValueError):
        return False
    return (
        candidate.source_path == installed.source_path
        and candidate.policy_version == installed.policy_version
        and candidate.providers == installed.providers
        and candidate.model_aliases == installed.model_aliases
        and candidate.routes == installed.routes
        and candidate.capability_registry.policy_version
            == installed.capability_registry.policy_version
        and candidate.capability_registry.policy_digest
            == installed.capability_registry.policy_digest
        and candidate.capability_registry.source_path
            == installed.capability_registry.source_path
    )


def _commercial_byteplus_reviewed(
    provider: str,
    model_alias: str,
    first_tier_id: str,
    first_tier_aliases: tuple[str, ...],
    reviewed_router: Any,
) -> bool:
    """Accept only an already reviewed commercial route, never preview rights.

    The issuer credential, balance, model activation, host and claim-time
    Capacity must still be independently proven by their incumbent owners.
    No file, provider, broker or network read occurs in this projection.
    """
    if provider != "byteplus-modelark":
        return False
    # No arbitrary BytePlus-looking preview may expand the commercial scope.
    if model_alias not in BYTEPLUS_COMMERCIAL_MODEL_PINS:
        return False

    from control_plane.codex_provider_realm import (
        BYTEPLUS_MODELARK_COMMERCIAL,
        REVIEWED_CODEX_PROVIDER_REALMS,
    )
    from control_plane.model_router import ModelRouter

    if (
        not _canonical_model_router_matches(reviewed_router)
        or REVIEWED_CODEX_PROVIDER_REALMS.get(
            BYTEPLUS_MODELARK_COMMERCIAL.realm_id
        ) is not BYTEPLUS_MODELARK_COMMERCIAL
    ):
        return False
    registered_provider = reviewed_router.providers.get(provider)
    registered_model = reviewed_router.model_aliases.get(model_alias)
    if (
        registered_provider is None
        or registered_provider.adapter_id != "codex-cli"
        or registered_provider.enabled is not True
        or registered_provider.autonomous_allowed is not True
        or registered_model is None
        or registered_model.provider_alias != provider
        or registered_model.adapter_id != "codex-cli"
        or registered_model.worker_eligible is not True
        or registered_model.model != BYTEPLUS_COMMERCIAL_MODEL_PINS[model_alias]
    ):
        return False
    # Caller-supplied first-tier text is not routing authority. Require an
    # actual first tier of the reviewed ModelRouter with the same identity.
    return any(
        risk in route
        and bool(route[risk])
        and route[risk][0].tier_id == first_tier_id
        and tuple(route[risk][0].model_aliases) == first_tier_aliases
        for route in reviewed_router.routes.values()
        for risk in ("routine", "elevated")
    )


def _prefer_commercial_flash_over_zai_flash(
    selected: Mapping[str, Any],
    options: Sequence[Mapping[str, Any]],
    *,
    first_tier_id: str,
    first_tier_aliases: tuple[str, ...],
    reviewed_router: Any,
    source_freshness_ok: bool,
) -> Mapping[str, Any]:
    """Project scarcity priority inside the first *already lawful* tier.

    When the preview otherwise favors Z.AI GLM Flash, commercial ModelArk
    Flash is preferred if the same tier has a reviewed, *eligible* BytePlus
    account-backed option with positive observed-preview headroom. This
    spares Z.AI headroom for full GLM 5.3. Never use this rule to displace
    a full-model job, switch suitability tiers, claim capacity or infer that
    a credential/worker has been activated.
    """
    from control_plane.model_router import ModelRouter

    if not source_freshness_ok or type(reviewed_router) is not ModelRouter:
        return selected
    if selected.get("provider") != "glm":
        return selected
    zai_alias = selected.get("model_alias")
    if type(zai_alias) is not str or _ID_RE.fullmatch(zai_alias) is None:
        return selected
    # A malformed original recommendation must not be "repaired" by
    # preferentially selecting an alternative from untrusted preview bytes.
    starting = selected.get("estimated_startable_jobs")
    concurrency = selected.get("suggested_parallelism")
    pressure = selected.get("expiry_pressure_jobs_per_hour")
    if (
        type(starting) is not int
        or type(concurrency) is not int
        or not (0 < concurrency <= starting)
        or (pressure is not None and (
            type(pressure) is not str or not 0 < len(pressure) <= 64
        ))
    ):
        return selected
    zai_model = reviewed_router.model_aliases.get(zai_alias)
    if (
        zai_model is None
        or zai_model.provider_alias != "glm"
        or zai_model.model not in _ZAI_FLASH_MODELS
        or zai_alias not in first_tier_aliases
    ):
        return selected
    candidates = []
    for option in options:
        if not isinstance(option, Mapping):
            continue
        alias = option.get("model_alias")
        if type(alias) is not str or alias not in BYTEPLUS_COMMERCIAL_FLASH_MODELS:
            continue
        if option.get("provider") != "byteplus-modelark":
            continue
        if alias not in first_tier_aliases:
            continue
        if option.get("eligible_in_preview") is not True:
            continue
        estimated = option.get("estimated_startable_jobs")
        parallelism = option.get("suggested_parallelism")
        if (type(estimated) is not int or type(parallelism) is not int
                or not (0 < parallelism <= estimated)):
            continue
        option_id = option.get("option_id")
        if (not isinstance(option_id, str)
                or _ID_RE.fullmatch(option_id) is None):
            continue
        if sum(
            isinstance(row, Mapping) and row.get("option_id") == option_id
            for row in options
        ) != 1:
            continue
        if not _commercial_byteplus_reviewed(
            "byteplus-modelark", alias, first_tier_id,
            first_tier_aliases, reviewed_router,
        ):
            continue
        # Tie-breaking is deterministic, not a provider-cost or quota claim.
        # Prefer more usable preview slots; both Flash models are viable
        # alternatives, with the GLM identity stable on exact ties.
        candidates.append((
            -parallelism, -estimated,
            list(BYTEPLUS_COMMERCIAL_FLASH_MODELS).index(alias),
            option_id, option,
        ))
    if not candidates:
        return selected
    candidates.sort(key=lambda item: item[:4])
    return candidates[0][-1]


def _validate_tiers(value: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise CapacityEconomicsProjectionError("suitability_tiers must be a non-empty sequence")
    if len(value) > 16:
        raise CapacityEconomicsProjectionError("suitability_tiers exceeds 16 tiers")
    tiers: list[tuple[str, tuple[str, ...]]] = []
    tier_ids: set[str] = set()
    aliases_seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != {"tier_id", "model_aliases"}:
            raise CapacityEconomicsProjectionError(
                f"suitability_tiers[{index}] must contain only tier_id and model_aliases"
            )
        tier_id = _token(raw["tier_id"], field=f"suitability_tiers[{index}].tier_id")
        if tier_id in tier_ids:
            raise CapacityEconomicsProjectionError("duplicate suitability tier_id")
        tier_ids.add(tier_id)
        raw_aliases = raw["model_aliases"]
        if (
            not isinstance(raw_aliases, Sequence)
            or isinstance(raw_aliases, (str, bytes))
            or not raw_aliases
            or len(raw_aliases) > 32
        ):
            raise CapacityEconomicsProjectionError(
                f"suitability_tiers[{index}].model_aliases must be a non-empty bounded sequence"
            )
        aliases: list[str] = []
        for alias_index, raw_alias in enumerate(raw_aliases):
            alias = _token(
                raw_alias,
                field=f"suitability_tiers[{index}].model_aliases[{alias_index}]",
            )
            if alias in aliases_seen:
                raise CapacityEconomicsProjectionError(
                    "a model alias may appear in only one suitability tier"
                )
            aliases_seen.add(alias)
            aliases.append(alias)
        tiers.append((tier_id, tuple(aliases)))
    return tuple(tiers)


@dataclasses.dataclass(frozen=True, slots=True)
class EconomicRoutePreference:
    preview_as_of: str
    selected_tier: str
    option_id: str
    provider: str
    model_alias: str
    estimated_startable_jobs: int
    suggested_parallelism: int
    expiry_pressure_jobs_per_hour: str | None
    original_suggested_option_id: str = ""
    preference_substituted: bool = False
    selection_is_commitment: bool = False
    claim_time_revalidation_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECTION_SCHEMA,
            "preview_as_of": self.preview_as_of,
            "selected_tier": self.selected_tier,
            "option_id": self.option_id,
            "provider": self.provider,
            "model_alias": self.model_alias,
            "estimated_startable_jobs": self.estimated_startable_jobs,
            "suggested_parallelism": self.suggested_parallelism,
            "expiry_pressure_jobs_per_hour": self.expiry_pressure_jobs_per_hour,
            "original_suggested_option_id": self.original_suggested_option_id,
            "preference_substituted": self.preference_substituted,
            "selection_is_commitment": self.selection_is_commitment,
            "claim_time_revalidation_required": self.claim_time_revalidation_required,
        }


def _nonnegative_int(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise CapacityEconomicsProjectionError(f"{field} must be a non-negative integer")
    return value


def project_quota_preference(
    suitability_tiers: Sequence[Mapping[str, Any]],
    quota_preview: Mapping[str, Any],
    *,
    reviewed_router: Any = None,
    owner_freshness: QuotaPreviewFreshness | None = None,
) -> EconomicRoutePreference:
    """Project one provider/model economic preference without changing authority.

    Provider Control may compare quota/cash/expiry economics only inside the first
    lawful Model Router tier. Any preview that names a later tier, claims live
    admission, omits revalidation, or selects an ineligible/ambiguous option is
    refused. The returned object is still not a worker selection or capacity hold.
    """
    tiers = _validate_tiers(suitability_tiers)
    if not isinstance(quota_preview, Mapping):
        raise CapacityEconomicsProjectionError("quota_preview must be an object")

    if quota_preview.get("schema") != QUOTA_PREVIEW_SCHEMA:
        raise CapacityEconomicsProjectionError("unsupported quota preview schema")
    if quota_preview.get("authority") != "NONE_PREVIEW_ONLY":
        raise CapacityEconomicsProjectionError("quota preview authority must remain NONE_PREVIEW_ONLY")
    if quota_preview.get("binding_verification") != "NOT_PERFORMED":
        raise CapacityEconomicsProjectionError("quota preview binding verification must remain NOT_PERFORMED")
    if quota_preview.get("live_admission") is not False:
        raise CapacityEconomicsProjectionError("quota preview must not claim live admission")
    if quota_preview.get("claim_time_revalidation_required") is not True:
        raise CapacityEconomicsProjectionError("claim-time revalidation must be required")
    if quota_preview.get("status") != "PREVIEW_READY":
        raise CapacityEconomicsProjectionError("quota preview is not ready")

    first_tier_id, first_tier_aliases = tiers[0]
    selected_tier = _token(quota_preview.get("selected_tier"), field="selected_tier")
    if selected_tier != first_tier_id:
        raise CapacityEconomicsProjectionError(
            "quota economics may not promote or select outside the first lawful suitability tier"
        )
    suggested_option = _token(quota_preview.get("suggested_option"), field="suggested_option")
    as_of = quota_preview.get("as_of")
    if not isinstance(as_of, str) or not as_of or len(as_of) > 64:
        raise CapacityEconomicsProjectionError("as_of must be a bounded timestamp string")

    options = quota_preview.get("options")
    if not isinstance(options, Sequence) or isinstance(options, (str, bytes)):
        raise CapacityEconomicsProjectionError("quota preview options must be a sequence")
    matches = [row for row in options if isinstance(row, Mapping) and row.get("option_id") == suggested_option]
    if len(matches) != 1:
        raise CapacityEconomicsProjectionError("suggested option must resolve to exactly one preview option")
    row = matches[0]
    if row.get("eligible_in_preview") is not True:
        raise CapacityEconomicsProjectionError("suggested option is not eligible in preview")

    # No new quota/selection owner: this advisory projection consumes the
    # incumbent Provider Control preview and cannot promote a held alias.
    row = _prefer_commercial_flash_over_zai_flash(
        row, options, first_tier_id=first_tier_id,
        first_tier_aliases=first_tier_aliases,
        reviewed_router=reviewed_router,
        source_freshness_ok=_source_freshness_ok(as_of, owner_freshness),
    )
    model_alias = _token(row.get("model_alias"), field="option.model_alias")
    if model_alias not in first_tier_aliases:
        raise CapacityEconomicsProjectionError(
            "suggested model alias is outside the first lawful suitability tier"
        )
    provider = _token(row.get("provider"), field="option.provider")
    # BytePlus Personal Coding Plan quota is valid only inside vendor-supported
    # coding tools for its individual subscriber. A provider-economics PREVIEW
    # does not attest that execution surface, consent or a plan-funded worker.
    # Never turn a forged positive Capacity estimate into an autonomous worker.
    # Neither the exact personal alias nor a near-miss label supplied by the
    # untrusted preview can assert license/Capacity facts. A commercial
    # BytePlus grant requires an explicit independently reviewed owner path.
    if _mentions_byteplus(provider) or _mentions_byteplus(model_alias):
        if not _commercial_byteplus_reviewed(
            provider, model_alias, first_tier_id, first_tier_aliases,
            reviewed_router,
        ):
            raise CapacityEconomicsProjectionError(
                "personal BytePlus Coding Plan or unreviewed commercial route "
                "cannot enter autonomous Capacity preference"
            )
    option_id = _token(row.get("option_id"), field="option.option_id")
    estimated = _nonnegative_int(
        row.get("estimated_startable_jobs"), field="option.estimated_startable_jobs"
    )
    parallelism = _nonnegative_int(
        row.get("suggested_parallelism"), field="option.suggested_parallelism"
    )
    if parallelism > estimated:
        raise CapacityEconomicsProjectionError(
            "suggested_parallelism cannot exceed estimated_startable_jobs"
        )
    if estimated == 0 or parallelism == 0:
        raise CapacityEconomicsProjectionError(
            "suggested option must have positive actionable capacity"
        )
    pressure = row.get("expiry_pressure_jobs_per_hour")
    if pressure is not None and (not isinstance(pressure, str) or not pressure or len(pressure) > 64):
        raise CapacityEconomicsProjectionError(
            "expiry_pressure_jobs_per_hour must be null or a bounded decimal string"
        )

    return EconomicRoutePreference(
        preview_as_of=as_of,
        selected_tier=selected_tier,
        option_id=option_id,
        provider=provider,
        model_alias=model_alias,
        estimated_startable_jobs=estimated,
        suggested_parallelism=parallelism,
        expiry_pressure_jobs_per_hour=pressure,
        original_suggested_option_id=suggested_option,
        preference_substituted=(option_id != suggested_option),
    )
