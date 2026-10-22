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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import islice
from typing import Any

QUOTA_PREVIEW_SCHEMA = "mastermind.quota_economics_preview/v1"
PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
# An input-size bound, not a provider or fleet concurrency limit.
_MAX_PREVIEW_OPTIONS = 512
_PRESSURE_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


class CapacityEconomicsProjectionError(ValueError):
    """The router/quota preview composition is invalid or non-actionable."""


def _token(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise CapacityEconomicsProjectionError(f"{field} must be a bounded identifier")
    return value


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
    options = tuple(islice(options, _MAX_PREVIEW_OPTIONS + 1))
    if len(options) > _MAX_PREVIEW_OPTIONS:
        raise CapacityEconomicsProjectionError("quota preview options must be bounded")
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
    if pressure is not None:
        if (
            not isinstance(pressure, str)
            or len(pressure) > 64
            or _PRESSURE_RE.fullmatch(pressure) is None
        ):
            raise CapacityEconomicsProjectionError("expiry pressure must be a bounded decimal string")
        try:
            numeric_pressure = Decimal(pressure)
        except InvalidOperation as exc:
            raise CapacityEconomicsProjectionError("expiry pressure must be a finite decimal") from exc
        if not numeric_pressure.is_finite() or numeric_pressure < 0:
            raise CapacityEconomicsProjectionError("expiry pressure must be a non-negative finite decimal")

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


OWNER_ENVELOPE_SCHEMA = "mastermind.capacity_owner_envelope/v1"
BOUNDED_PROJECTION_SCHEMA = "mastermind.capacity_economics_projection/v2"
_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_CONCURRENCY_SCOPES = frozenset({"provider", "account", "model", "host", "root", "operation", "review"})
_ENVELOPE_FIELDS = frozenset({
    "schema", "observation_ref", "observed_at", "valid_until", "option_id",
    "provider", "model_alias", "root_operation_ref", "operation_ref",
    "quota_domain_ref", "workload_ref", "host_ref", "review_pool_ref", "constraints",
})
_BOUND_FIELDS = frozenset({"kind", "scope", "scope_ref", "remaining", "evidence_ref"})


def _reference_tuple(value: Any, *, field: str, minimum: int, maximum: int) -> tuple[str, ...]:
    if type(value) is not tuple or not minimum <= len(value) <= maximum:
        raise CapacityEconomicsProjectionError(f"{field} must be a bounded immutable tuple")
    result = tuple(_token(item, field=field) for item in value)
    if len(set(result)) != len(result):
        raise CapacityEconomicsProjectionError(f"{field} contains duplicate references")
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityProjectionScope:
    """Existing owner references, supplied independently of the candidate envelope.

    This value neither authenticates a caller nor creates identities or grants.
    The caller must obtain the complete ancestor and quota-window sets from their
    canonical owners, and the workload reference must identify the same job-cost
    cohort used to normalize native quota units into remaining starts.
    """

    root_operation_ref: str
    operation_ref: str
    quota_domain_ref: str
    workload_ref: str
    host_ref: str
    review_pool_ref: str
    quota_window_refs: tuple[str, ...]
    ancestor_operation_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("root_operation_ref", "operation_ref", "quota_domain_ref", "workload_ref", "host_ref", "review_pool_ref"):
            _token(getattr(self, field), field=field)
        _reference_tuple(self.quota_window_refs, field="quota_window_refs", minimum=1, maximum=32)
        _reference_tuple(self.ancestor_operation_refs, field="ancestor_operation_refs", minimum=0, maximum=16)
        if {self.operation_ref, self.root_operation_ref}.intersection(self.ancestor_operation_refs):
            raise CapacityEconomicsProjectionError("ancestors must exclude the operation and root")
        if self.operation_ref == self.root_operation_ref and self.ancestor_operation_refs:
            raise CapacityEconomicsProjectionError("a root projection cannot name intermediate ancestors")


def _timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64 or _TIMESTAMP_RE.fullmatch(value) is None:
        raise CapacityEconomicsProjectionError(f"{field} must be a timezone-aware timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapacityEconomicsProjectionError(f"{field} is not a valid timestamp") from exc


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityBoundedPreference:
    """An immutable, non-reserving preview; NEVER a dispatch capability."""

    preference: EconomicRoutePreference
    scope: CapacityProjectionScope
    observation_ref: str
    observed_at: str
    valid_until: str
    status: str
    estimated_startable_jobs: int | None
    suggested_parallelism: int
    limiting_constraints: tuple[str, ...]
    unknown_constraints: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = self.preference.to_dict()
        result.update({
            "schema": BOUNDED_PROJECTION_SCHEMA,
            "status": self.status,
            "authority": "NONE_PREVIEW_ONLY",
            "binding_verification": "NOT_PERFORMED",
            "live_admission": False,
            "selection_is_commitment": False,
            "claim_time_revalidation_required": True,
            "unbounded_preview_startable_jobs": self.preference.estimated_startable_jobs,
            "unbounded_preview_parallelism": self.preference.suggested_parallelism,
            "estimated_startable_jobs": self.estimated_startable_jobs,
            "suggested_parallelism": self.suggested_parallelism,
            "capacity_scope": dataclasses.asdict(self.scope),
            "capacity_observation_ref": self.observation_ref,
            "capacity_observed_at": self.observed_at,
            "capacity_valid_until": self.valid_until,
            "limiting_constraints": list(self.limiting_constraints),
            "unknown_constraints": list(self.unknown_constraints),
        })
        return result


def _owner_bounds(
    raw: Any, *, scope: CapacityProjectionScope, preference: EconomicRoutePreference,
) -> tuple[tuple[str, str, int | None], ...]:
    # Closed JSON-shaped inputs avoid unbounded lazy iterators at this boundary.
    if type(raw) not in (list, tuple) or not 1 <= len(raw) <= 80:
        raise CapacityEconomicsProjectionError("constraints must be a non-empty bounded list")
    bounds: list[tuple[str, str, int | None]] = []
    seen: set[tuple[str, str, str]] = set()
    pairs: set[tuple[str, str]] = set()
    windows: set[str] = set()
    ancestors: dict[str, set[str]] = {"concurrency": set(), "starts": set()}
    bound_refs = {
        "provider": preference.provider,
        "account": scope.quota_domain_ref,
        "model": preference.model_alias,
        "host": scope.host_ref,
        "review": scope.review_pool_ref,
        "root": scope.root_operation_ref,
        "operation": scope.operation_ref,
    }
    for item in raw:
        if type(item) is not dict or set(item) != _BOUND_FIELDS:
            raise CapacityEconomicsProjectionError("constraint has missing or unsupported fields")
        kind = _token(item["kind"], field="constraint.kind")
        category = _token(item["scope"], field="constraint.scope")
        ref = _token(item["scope_ref"], field="constraint.scope_ref")
        _token(item["evidence_ref"], field="constraint.evidence_ref")
        pair = (kind, category)
        allowed = (
            kind == "concurrency" and category in _CONCURRENCY_SCOPES | {"ancestor"}
        ) or (kind == "starts" and category in {"root", "operation", "ancestor", "quota_window"})
        if not allowed:
            raise CapacityEconomicsProjectionError("unsupported constraint kind/scope")
        key = (kind, category, ref)
        if key in seen or (pair in pairs and category not in {"ancestor", "quota_window"}):
            raise CapacityEconomicsProjectionError("duplicate constraint")
        seen.add(key)
        pairs.add(pair)
        if category in bound_refs and ref != bound_refs[category]:
            raise CapacityEconomicsProjectionError("constraint scope binding mismatch")
        if category == "quota_window":
            windows.add(ref)
        if category == "ancestor":
            ancestors[kind].add(ref)
        remaining = item["remaining"]
        if remaining is not None:
            _nonnegative_int(remaining, field="constraint.remaining")
        bounds.append((kind, ":".join(key), remaining))
    required = {("concurrency", item) for item in _CONCURRENCY_SCOPES}
    required.update({("starts", "root"), ("starts", "operation")})
    if not required.issubset(pairs):
        raise CapacityEconomicsProjectionError("missing required capacity dimension")
    if windows != set(scope.quota_window_refs):
        raise CapacityEconomicsProjectionError("quota window set must match the owner scope exactly")
    if any(refs != set(scope.ancestor_operation_refs) for refs in ancestors.values()):
        raise CapacityEconomicsProjectionError("ancestor set must match the owner scope exactly")
    return tuple(sorted(bounds, key=lambda row: row[1]))


def project_capacity_bounded_preference(
    suitability_tiers: Sequence[Mapping[str, Any]],
    quota_preview: Mapping[str, Any],
    capacity_envelope: Mapping[str, Any],
    *,
    scope: CapacityProjectionScope,
    now: datetime,
    max_age_seconds: int,
) -> CapacityBoundedPreference:
    """Intersect an economic hint with fresh, complete owner-produced ceilings.

    All `remaining` values are JOB-EQUIVALENT HEADROOM, already normalized for
    `workload_ref` by the appropriate owner after active/uncertain holds and
    review, repair and return obligations. This function never reads credentials,
    computes token costs, predicts resets, acquires a lease or mutates a queue.

    Concurrency ceilings and cumulative start budgets are different dimensions.
    No sum across accounts, aliases, models, windows or ancestors is performed.
    Unknown required evidence blocks a new positive projection; a zero ceiling
    blocks a positive wave. Neither result selects a weaker suitability tier.

    `now` and the observation-age policy are supplied by the existing caller;
    there is no new clock, watcher, reservation or autonomous dispatch owner.
    """
    if not isinstance(scope, CapacityProjectionScope):
        raise CapacityEconomicsProjectionError("scope must be CapacityProjectionScope")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise CapacityEconomicsProjectionError("now must be a timezone-aware datetime")
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise CapacityEconomicsProjectionError("max_age_seconds must be a positive integer")
    if type(capacity_envelope) is not dict or set(capacity_envelope) != _ENVELOPE_FIELDS:
        raise CapacityEconomicsProjectionError("capacity envelope has missing or unsupported fields")
    if capacity_envelope["schema"] != OWNER_ENVELOPE_SCHEMA:
        raise CapacityEconomicsProjectionError("unsupported owner capacity envelope schema")
    preference = project_quota_preference(suitability_tiers, quota_preview)
    expected = {
        "option_id": preference.option_id,
        "provider": preference.provider,
        "model_alias": preference.model_alias,
        "root_operation_ref": scope.root_operation_ref,
        "operation_ref": scope.operation_ref,
        "quota_domain_ref": scope.quota_domain_ref,
        "workload_ref": scope.workload_ref,
        "host_ref": scope.host_ref,
        "review_pool_ref": scope.review_pool_ref,
    }
    if any(capacity_envelope[key] != value for key, value in expected.items()):
        raise CapacityEconomicsProjectionError("capacity envelope scope binding mismatch")
    observation_ref = _token(capacity_envelope["observation_ref"], field="observation_ref")
    observed = _timestamp(capacity_envelope["observed_at"], field="observed_at")
    valid_until = _timestamp(capacity_envelope["valid_until"], field="valid_until")
    preview_at = _timestamp(preference.preview_as_of, field="preview.as_of")
    for field, timestamp in (("observed_at", observed), ("preview.as_of", preview_at)):
        age = (now - timestamp).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise CapacityEconomicsProjectionError(f"{field} is future-dated or stale")
    if valid_until <= observed or now >= valid_until:
        raise CapacityEconomicsProjectionError("capacity envelope has expired or invalid validity")
    bounds = _owner_bounds(capacity_envelope["constraints"], scope=scope, preference=preference)
    unknown = tuple(label for _, label, remaining in bounds if remaining is None)
    limiting: tuple[str, ...] = ()
    starts: int | None = None
    parallelism = 0
    status = "WAIT_EVIDENCE"
    if not unknown:
        # Unknowns have been excluded; only validated non-negative integers remain.
        start_values = [value for kind, _, value in bounds if kind == "starts" and value is not None]
        concurrency_values = [value for kind, _, value in bounds if kind == "concurrency" and value is not None]
        starts = min(preference.estimated_startable_jobs, *start_values)
        parallelism = min(preference.suggested_parallelism, starts, *concurrency_values)
        limiting = tuple(label for kind, label, value in bounds if (
            (kind == "starts" and value == starts)
            or (kind == "concurrency" and value == parallelism)
        ))
        status = "PREVIEW_READY" if parallelism > 0 else "WAIT_CAPACITY"
    return CapacityBoundedPreference(
        preference=preference,
        scope=scope,
        observation_ref=observation_ref,
        observed_at=capacity_envelope["observed_at"],
        valid_until=capacity_envelope["valid_until"],
        status=status,
        estimated_startable_jobs=starts,
        suggested_parallelism=parallelism,
        limiting_constraints=limiting,
        unknown_constraints=unknown,
    )
