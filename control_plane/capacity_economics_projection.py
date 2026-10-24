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
from collections.abc import Mapping, Sequence
from typing import Any

QUOTA_PREVIEW_SCHEMA = "mastermind.quota_economics_preview/v1"
PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class CapacityEconomicsProjectionError(ValueError):
    """The router/quota preview composition is invalid or non-actionable."""


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
    if provider != "byteplus-modelark" or not model_alias.startswith("byteplus-modelark."):
        return False

    from control_plane.codex_provider_realm import (
        BYTEPLUS_MODELARK_COMMERCIAL,
        REVIEWED_CODEX_PROVIDER_REALMS,
    )
    from control_plane.model_router import ModelRouter

    if (
        type(reviewed_router) is not ModelRouter
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
    )
