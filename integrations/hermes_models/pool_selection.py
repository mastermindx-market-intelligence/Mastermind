"""Pure H24-05 pre-claim projection; never a router, quota store or executor.

The authenticated caller supplies detached facts from the incumbent owners and
independently current source pins. Stamps are provenance, NOT authentication.
Only the first lawful Router tier and the existing Capacity owner's order are
projected. Before any effect, the executing owner must revalidate and atomically
reserve through the incumbent. Parallel readers acquire nothing.

Inputs intentionally have no credentials, URLs, callbacks, arbitrary metadata,
provider error text or mutable collections. Public results hash opaque owner
identifiers rather than echoing them. Monetary values are exact Decimals and all
times are explicit UTC epoch seconds; this module reads neither clocks nor I/O.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from decimal import Context, Decimal, localcontext
from enum import Enum
import hashlib
import json
import re

from integrations.hermes_models.contract import MODELARK_CONTRACT, PROVIDERS, ROLES


SCHEMA = "mastermind.hermes_model_pool_projection/v1"
SURFACE = "hermes.chat_completions"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_INT = 10**15
_MAX_TIME = 253402300799


class PoolSelectionError(ValueError):
    """Malformed inputs; messages never contain submitted values."""


class Owner(str, Enum):
    ROUTER = "model_router"
    ECONOMICS = "provider_model_economics"
    PROVIDER = "shared_ai_provider_control"
    CAPACITY = "capacity_fabric"
    EXECUTIVE = "executive_os"


class Health(str, Enum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    RATE_LIMITED = "RATE_LIMITED"


class Auth(str, Enum):
    READY = "READY"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


class Effect(str, Enum):
    PRE_SEND = "PRE_SEND"
    READ_ONLY_NO_EFFECT = "READ_ONLY_NO_EFFECT"
    UNKNOWN = "EFFECT_UNKNOWN"
    OBSERVED = "EFFECT_OBSERVED"


class Failure(str, Enum):
    NONE = "NONE"
    OUTAGE = "OUTAGE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_DENIED = "AUTH_DENIED"
    MODEL_MISMATCH = "MODEL_MISMATCH"


class Unit(str, Enum):
    REQUESTS = "requests"
    TOKENS = "tokens"
    CREDITS = "credits"
    USD = "usd"


# repr=False prevents even a malformed input's opaque labels appearing in repr.
@dataclass(frozen=True, slots=True, repr=False)
class SourcePin:
    owner: Owner
    issuer_id: str
    source_id: str
    revision: str


@dataclass(frozen=True, slots=True, repr=False)
class Stamp:
    pin: SourcePin
    observed_at: int
    expires_at: int


@dataclass(frozen=True, slots=True, repr=False)
class Binding:
    """Opaque enrolled pool binding; no credential material or resolution."""

    issuer_id: str
    realm_id: str
    pool_id: str
    generation: str


@dataclass(frozen=True, slots=True, repr=False)
class Demand:
    request_id: str
    job_id: str
    role: str
    input_tokens: int  # Upper bound per request, including tools/history.
    output_tokens: int  # Upper bound per request.
    max_requests: int
    required_capabilities: tuple[str, ...]
    cash_ceiling_usd: Decimal
    effect: str  # Existing Hermes vocabulary: read_only | side_effecting.


@dataclass(frozen=True, slots=True, repr=False)
class Suitability:
    stamp: Stamp
    demand_digest: str
    first_tier_id: str
    model_aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class Capability:
    stamp: Stamp
    model_alias: str
    provider_id: str
    served_model: str
    surface: str
    context_window_tokens: int | None
    max_output_tokens: int | None
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class Candidate:
    candidate_id: str
    model_alias: str
    provider_id: str
    served_model: str
    surface: str
    binding: Binding
    host_id: str
    lane_id: str
    worker_id: str
    source_digest: str
    execution_profile_digest: str
    capability_policy_digest: str
    available: bool
    readiness: Health
    source_qualified: bool
    policy_qualified: bool
    owner_rank: int


@dataclass(frozen=True, slots=True, repr=False)
class Capacity:
    stamp: Stamp
    demand_digest: str
    suitability_source: SourcePin
    first_tier_id: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RealmHealth:
    issuer_id: str
    realm_id: str
    auth: Auth  # A 401/403 is DENIED across every pool/model in this realm.


@dataclass(frozen=True, slots=True, repr=False)
class PoolHealth:
    binding: Binding
    health: Health


@dataclass(frozen=True, slots=True, repr=False)
class ModelHealth:
    binding: Binding
    served_model: str
    health: Health
    cooldown_until: int | None  # Owner-observed 429; no locally invented TTL.


@dataclass(frozen=True, slots=True, repr=False)
class Window:
    """One native depletion resource, shared or model-specific, never a wallet."""

    resource_id: str
    binding: Binding
    served_model: str | None  # None means shared across models in this pool.
    unit: Unit
    starts_at: int
    resets_at: int
    limit: Decimal
    used: Decimal
    reserved: Decimal  # All competing incumbent reservations, not just this job.


@dataclass(frozen=True, slots=True, repr=False)
class ModelQuota:
    binding: Binding
    served_model: str
    required_resources: tuple[str, ...]  # Owner's complete applicable horizon set.
    complete: bool


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFacts:
    stamp: Stamp
    realms: tuple[RealmHealth, ...]
    pools: tuple[PoolHealth, ...]
    models: tuple[ModelHealth, ...]
    quotas: tuple[ModelQuota, ...]
    windows: tuple[Window, ...]


@dataclass(frozen=True, slots=True, repr=False)
class Debit:
    resource_id: str
    unit: Unit
    upper_bound: Decimal


@dataclass(frozen=True, slots=True, repr=False)
class Quote:
    """Owner-computed worst-case cash/native debit for the EXACT bounded demand.

    This projection does not calculate prices, estimate credit multipliers or
    assume cache discounts. The source owner must include every billable item.
    """

    stamp: Stamp
    quote_id: str
    rate_card_source: SourcePin
    binding: Binding
    model_alias: str
    provider_id: str
    served_model: str
    surface: str
    demand_digest: str
    context_min: int
    context_max: int | None
    currency: str
    cash_upper_bound: Decimal
    debits: tuple[Debit, ...]


@dataclass(frozen=True, slots=True, repr=False)
class Budget:
    stamp: Stamp
    budget_id: str
    job_id: str
    demand_digest: str
    request_limit: int
    requests_used: int
    requests_reserved: int
    token_limit: int
    tokens_used: int
    tokens_reserved: int
    cash_limit: Decimal
    cash_used: Decimal
    cash_reserved: Decimal


@dataclass(frozen=True, slots=True, repr=False)
class EffectEvidence:
    stamp: Stamp
    demand_digest: str
    state: Effect
    failure: Failure
    attempted_provider_id: str | None
    served_model: str | None
    response_status: int | None
    no_effect_receipt: str | None


@dataclass(frozen=True, slots=True, repr=False)
class PoolFacts:
    suitability: Suitability
    capacity: Capacity
    provider: ProviderFacts
    capabilities: tuple[Capability, ...]
    quotes: tuple[Quote, ...]
    budget: Budget
    effect: EffectEvidence


@dataclass(frozen=True, slots=True)
class SourceReference:
    owner: str
    issuer_ref: str
    source_ref: str
    revision: str
    observed_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class DebitProjection:
    resource_ref: str
    unit: str
    upper_bound: str
    remaining_before: str
    remaining_after: str
    resets_at: int


@dataclass(frozen=True, slots=True)
class QuoteProjection:
    quote_ref: str
    source: SourceReference
    rate_card_revision: str
    rate_card_source: SourceReference
    currency: str
    cash_upper_bound: str
    debits: tuple[DebitProjection, ...]


@dataclass(frozen=True, slots=True)
class Selection:
    candidate_ref: str
    provider_id: str
    served_model: str
    model_alias_ref: str
    binding_ref: str
    placement_ref: str
    owner_rank: int
    expires_at: int
    quote: QuoteProjection
    sources: tuple[SourceReference, ...]


@dataclass(frozen=True, slots=True)
class Exclusion:
    candidate_ref: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    status: str
    demand_digest: str
    snapshot_digest: str
    selected: Selection | None
    alternatives: tuple[Selection, ...]
    exclusions: tuple[Exclusion, ...]
    reasons: tuple[str, ...]
    trace: tuple[str, ...]
    sources: tuple[SourceReference, ...]
    expires_at: int | None

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            **asdict(self),
            "authority": "NONE_PREVIEW_ONLY",
            "binding_verification": "NOT_PERFORMED",
            "selection_is_commitment": False,
            "capacity_claimed": False,
            "live_admission": False,
            "provider_connected": False,
            "claim_time_revalidation_required": True,
            "incumbent_reservation_required": True,
        }


def _invalid() -> None:
    raise PoolSelectionError("invalid H24 model-pool input")


def _type(value, kind) -> None:
    if type(value) is not kind:
        _invalid()


def _id(value) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        _invalid()


def _digest(value) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _invalid()


def _int(value, *, minimum=0, maximum=_MAX_INT) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        _invalid()


def _money(value) -> None:
    if (type(value) is not Decimal or not value.is_finite() or value < 0
            or value > Decimal(_MAX_INT) or not -9 <= value.as_tuple().exponent <= 15):
        _invalid()


def _tuple(value, kind, *, nonempty=False, maximum=128) -> None:
    if type(value) is not tuple or len(value) > maximum or (nonempty and not value):
        _invalid()
    for item in value:
        _type(item, kind)


def _ids(value, *, nonempty=False) -> None:
    _tuple(value, str, nonempty=nonempty)
    for item in value:
        _id(item)
    _unique(value)


def _unique(values) -> None:
    values = tuple(values)
    if len(set(values)) != len(values):
        _invalid()


def _pin(pin: SourcePin) -> None:
    _type(pin, SourcePin)
    _type(pin.owner, Owner)
    _id(pin.issuer_id)
    _id(pin.source_id)
    _digest(pin.revision)


def _stamp(stamp: Stamp) -> None:
    _type(stamp, Stamp)
    _pin(stamp.pin)
    _int(stamp.observed_at, maximum=_MAX_TIME)
    _int(stamp.expires_at, minimum=1, maximum=_MAX_TIME)
    if stamp.observed_at >= stamp.expires_at:
        _invalid()


def _binding(binding: Binding) -> None:
    _type(binding, Binding)
    for name in ("issuer_id", "realm_id", "pool_id"):
        _id(getattr(binding, name))
    _digest(binding.generation)


def _canonical(value):
    if isinstance(value, Enum):
        return value.value
    if type(value) is Decimal:
        # normalize() uses ambient Decimal precision; fixed-point text does not.
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if is_dataclass(value):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if type(value) is tuple:
        return [_canonical(item) for item in value]
    return value


def _hash(value) -> str:
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_demand(demand: Demand) -> None:
    _type(demand, Demand)
    for value in (demand.request_id, demand.job_id, demand.role):
        _id(value)
    if (demand.role not in ROLES or type(demand.effect) is not str
            or demand.effect not in {"read_only", "side_effecting"}):
        _invalid()
    _int(demand.input_tokens)
    _int(demand.output_tokens, minimum=1)
    _int(demand.max_requests, minimum=1)
    _ids(demand.required_capabilities)
    _money(demand.cash_ceiling_usd)


def demand_digest(demand: Demand) -> str:
    """Bind an owner quote, budget and decision to exact maximum demand."""
    _validate_demand(demand)
    return _hash(demand)


def candidate_ref(candidate: Candidate) -> str:
    """Opaque join key; the executing owner retains the original candidate."""
    _validate_candidate(candidate)
    return _hash(candidate)


def _validate_candidate(candidate: Candidate) -> None:
    _type(candidate, Candidate)
    for name in ("candidate_id", "model_alias", "provider_id", "served_model", "surface",
                 "host_id", "lane_id", "worker_id"):
        _id(getattr(candidate, name))
    _binding(candidate.binding)
    for name in ("source_digest", "execution_profile_digest", "capability_policy_digest"):
        _digest(getattr(candidate, name))
    for name in ("available", "source_qualified", "policy_qualified"):
        _type(getattr(candidate, name), bool)
    _type(candidate.readiness, Health)
    _int(candidate.owner_rank)


def _validate(facts: PoolFacts, pins: tuple[SourcePin, ...], now: int) -> None:
    _type(facts, PoolFacts)
    _int(now, maximum=_MAX_TIME)
    _tuple(pins, SourcePin, nonempty=True)
    for pin in pins:
        _pin(pin)
    _unique((pin.owner, pin.source_id) for pin in pins)
    for name, kind in (("suitability", Suitability), ("capacity", Capacity),
                       ("provider", ProviderFacts), ("budget", Budget), ("effect", EffectEvidence)):
        value = getattr(facts, name)
        _type(value, kind)
        _stamp(value.stamp)
        if name != "provider":
            _digest(value.demand_digest)
    route, capacity, provider, budget, effect = (
        facts.suitability, facts.capacity, facts.provider, facts.budget, facts.effect)
    _id(route.first_tier_id)
    _ids(route.model_aliases, nonempty=True)
    _id(capacity.first_tier_id)
    _pin(capacity.suitability_source)
    _tuple(capacity.candidates, Candidate)
    for candidate in capacity.candidates:
        _validate_candidate(candidate)
    _unique(c.candidate_id for c in capacity.candidates)
    _unique(c.owner_rank for c in capacity.candidates)
    _tuple(facts.capabilities, Capability)
    for cap in facts.capabilities:
        _stamp(cap.stamp)
        for name in ("model_alias", "provider_id", "served_model", "surface"):
            _id(getattr(cap, name))
        for number in (cap.context_window_tokens, cap.max_output_tokens):
            if number is not None:
                _int(number, minimum=1)
        _ids(cap.capabilities)
    _unique((c.model_alias, c.surface) for c in facts.capabilities)
    _tuple(provider.realms, RealmHealth)
    for realm in provider.realms:
        _id(realm.issuer_id)
        _id(realm.realm_id)
        _type(realm.auth, Auth)
    _unique((r.issuer_id, r.realm_id) for r in provider.realms)
    _tuple(provider.pools, PoolHealth)
    for pool in provider.pools:
        _binding(pool.binding)
        _type(pool.health, Health)
    _unique(p.binding for p in provider.pools)
    _tuple(provider.models, ModelHealth)
    for model in provider.models:
        _binding(model.binding)
        _id(model.served_model)
        _type(model.health, Health)
        if model.cooldown_until is not None:
            _int(model.cooldown_until, maximum=_MAX_TIME)
    _unique((m.binding, m.served_model) for m in provider.models)
    _tuple(provider.quotas, ModelQuota)
    for quota in provider.quotas:
        _binding(quota.binding)
        _id(quota.served_model)
        _ids(quota.required_resources, nonempty=True)
        _type(quota.complete, bool)
    _unique((q.binding, q.served_model) for q in provider.quotas)
    _tuple(provider.windows, Window)
    for window in provider.windows:
        _id(window.resource_id)
        _binding(window.binding)
        if window.served_model is not None:
            _id(window.served_model)
        _type(window.unit, Unit)
        _int(window.starts_at, maximum=_MAX_TIME)
        _int(window.resets_at, minimum=1, maximum=_MAX_TIME)
        if window.starts_at >= window.resets_at:
            _invalid()
        for amount in (window.limit, window.used, window.reserved):
            _money(amount)
        if window.unit in {Unit.REQUESTS, Unit.TOKENS} and any(
                v != v.to_integral_value() for v in (window.limit, window.used, window.reserved)):
            _invalid()
    # A shared resource is declared once, never copied into per-model wallets.
    _unique(w.resource_id for w in provider.windows)
    _tuple(facts.quotes, Quote)
    for quote in facts.quotes:
        _stamp(quote.stamp)
        _binding(quote.binding)
        for name in ("quote_id", "model_alias", "provider_id", "served_model", "surface"):
            _id(getattr(quote, name))
        _pin(quote.rate_card_source)
        _digest(quote.demand_digest)
        _int(quote.context_min)
        if quote.context_max is not None:
            _int(quote.context_max, minimum=quote.context_min)
        if type(quote.currency) is not str or quote.currency != "USD":
            _invalid()
        _money(quote.cash_upper_bound)
        _tuple(quote.debits, Debit, nonempty=True)
        for debit in quote.debits:
            _id(debit.resource_id)
            _type(debit.unit, Unit)
            _money(debit.upper_bound)
        _unique(d.resource_id for d in quote.debits)
    _unique((q.binding, q.model_alias, q.surface) for q in facts.quotes)
    for name in ("budget_id", "job_id"):
        _id(getattr(budget, name))
    for name in ("request_limit", "requests_used", "requests_reserved",
                 "token_limit", "tokens_used", "tokens_reserved"):
        _int(getattr(budget, name))
    for value in (budget.cash_limit, budget.cash_used, budget.cash_reserved):
        _money(value)
    _type(effect.state, Effect)
    _type(effect.failure, Failure)
    for value in (effect.attempted_provider_id, effect.served_model):
        if value is not None:
            _id(value)
    if effect.response_status is not None:
        _int(effect.response_status, minimum=100, maximum=599)
    if effect.no_effect_receipt is not None:
        _digest(effect.no_effect_receipt)


def _source(stamp: Stamp) -> SourceReference:
    return SourceReference(stamp.pin.owner.value, _hash(stamp.pin.issuer_id),
                           _hash(stamp.pin.source_id), stamp.pin.revision,
                           stamp.observed_at, stamp.expires_at)


def _source_reasons(stamp: Stamp, owner: Owner, pins: tuple[SourcePin, ...], now: int) -> tuple[str, ...]:
    if stamp.pin.owner is not owner:
        return ("WRONG_SOURCE_OWNER",)
    matches = [p for p in pins if p.owner is owner and p.source_id == stamp.pin.source_id]
    if not matches:
        return ("CURRENT_SOURCE_MISSING",)
    if matches[0].issuer_id != stamp.pin.issuer_id:
        return ("SOURCE_ISSUER_MISMATCH",)
    if matches[0].revision != stamp.pin.revision:
        return ("SOURCE_MOVED",)
    if not stamp.observed_at <= now < stamp.expires_at:
        return ("SOURCE_STALE_OR_FUTURE",)
    return ()


def _effect_reasons(demand: Demand, effect: EffectEvidence) -> tuple[str, ...]:
    if effect.state in {Effect.UNKNOWN, Effect.OBSERVED}:
        return ("PRIOR_EFFECT_FORBIDS_SELECTION",)
    if effect.failure is Failure.MODEL_MISMATCH:
        return ("SERVED_MODEL_MISMATCH",)
    if effect.failure is Failure.AUTH_DENIED or effect.response_status in {401, 403}:
        return ("AUTH_DENIAL_NOT_FAILOVER",)
    if effect.state is Effect.PRE_SEND:
        if (effect.failure is not Failure.NONE or effect.attempted_provider_id is not None
                or effect.response_status is not None or effect.served_model is not None
                or effect.no_effect_receipt is not None):
            return ("INCOHERENT_PRE_SEND_EVIDENCE",)
        return ()
    if demand.effect != "read_only" or effect.no_effect_receipt is None:
        return ("READ_ONLY_NO_EFFECT_PROOF_REQUIRED",)
    spec = PROVIDERS.get(effect.attempted_provider_id)
    if spec is None or effect.attempted_provider_id not in ROLES[demand.role].provider_ids:
        return ("ATTEMPT_IDENTITY_MISMATCH",)
    if ((effect.served_model is not None and effect.served_model != spec.served_model)
            or (effect.response_status is not None and 200 <= effect.response_status < 300
                and effect.served_model is None)):
        return ("SERVED_MODEL_MISMATCH",)
    if effect.failure not in {Failure.OUTAGE, Failure.RATE_LIMITED}:
        return ("FAILURE_NOT_FALLBACK_ELIGIBLE",)
    if effect.failure is Failure.RATE_LIMITED and effect.response_status != 429:
        return ("FAILURE_EVIDENCE_MISMATCH",)
    if effect.failure is Failure.OUTAGE and effect.response_status is not None and effect.response_status < 500:
        return ("FAILURE_EVIDENCE_MISMATCH",)
    return ()


def _qualified_candidate(demand: Demand, facts: PoolFacts, c: Candidate,
                         pins: tuple[SourcePin, ...], now: int,
                         common_sources: tuple[SourceReference, ...]) -> tuple[Selection | None, tuple[str, ...]]:
    reasons: list[str] = []
    spec = PROVIDERS.get(c.provider_id)
    if spec is None or c.provider_id not in ROLES[demand.role].provider_ids:
        return None, ("ROLE_PROVIDER_NOT_ALLOWED",)
    if not spec.enabled_in_profile:
        return None, ("PROFILE_PROVIDER_DISABLED",)
    if c.served_model != spec.served_model:
        reasons.append("MODEL_CONTRACT_MISMATCH")
    if c.surface != SURFACE:
        reasons.append("WRONG_SERVING_SURFACE")
    if c.model_alias not in facts.suitability.model_aliases:
        reasons.append("OUTSIDE_FIRST_SUITABILITY_TIER")
    if c.provider_id.startswith("byteplus-modelark.") and (
            c.model_alias != spec.router_alias or c.binding.realm_id != MODELARK_CONTRACT["realm_id"]):
        reasons.append("MODELARK_COMMERCIAL_BINDING_REQUIRED")
    if not c.source_qualified:
        reasons.append("CAPACITY_SOURCE_UNQUALIFIED")
    if not c.policy_qualified:
        reasons.append("OWNER_POLICY_NOT_QUALIFIED")
    if not c.available or c.readiness is not Health.READY:
        reasons.append("CAPACITY_NOT_READY")
    if facts.effect.state is not Effect.PRE_SEND and c.provider_id == facts.effect.attempted_provider_id:
        reasons.append("ATTEMPTED_MODEL_NOT_A_FALLBACK")

    cap = next((item for item in facts.capabilities
                if item.model_alias == c.model_alias and item.surface == c.surface), None)
    if cap is None:
        reasons.append("CAPABILITY_FACT_MISSING")
    else:
        reasons.extend(_source_reasons(cap.stamp, Owner.ECONOMICS, pins, now))
        if (cap.provider_id, cap.served_model) != (c.provider_id, c.served_model):
            reasons.append("CAPABILITY_IDENTITY_MISMATCH")
        if cap.context_window_tokens is None or cap.max_output_tokens is None:
            reasons.append("EFFECTIVE_LIMITS_UNKNOWN")
        elif (demand.input_tokens + demand.output_tokens > cap.context_window_tokens
              or demand.output_tokens > cap.max_output_tokens):
            reasons.append("MODEL_CONTEXT_OR_OUTPUT_EXCEEDED")
        if not set(demand.required_capabilities).issubset(cap.capabilities):
            reasons.append("REQUIRED_CAPABILITY_MISSING")

    provider = facts.provider
    realm = next((r for r in provider.realms
                  if (r.issuer_id, r.realm_id) == (c.binding.issuer_id, c.binding.realm_id)), None)
    if realm is None or realm.auth is Auth.UNKNOWN:
        reasons.append("REALM_AUTH_UNKNOWN")
    elif realm.auth is Auth.DENIED:
        reasons.append("REALM_AUTH_DENIED")
    pool = next((p for p in provider.pools if p.binding == c.binding), None)
    if pool is None or pool.health is not Health.READY:
        reasons.append("POOL_NOT_HEALTHY")
    model = next((m for m in provider.models
                  if (m.binding, m.served_model) == (c.binding, c.served_model)), None)
    if model is None:
        reasons.append("MODEL_HEALTH_UNKNOWN")
    elif model.cooldown_until is not None and now < model.cooldown_until:
        reasons.append("MODEL_COOLDOWN")
    elif model.cooldown_until is not None and provider.stamp.observed_at < model.cooldown_until:
        reasons.append("MODEL_HEALTH_REQUIRES_REFRESH")
    elif model.health is not Health.READY:
        # Expired cooldown is not a fresh positive health observation.
        reasons.append("MODEL_NOT_HEALTHY")

    quota = next((q for q in provider.quotas
                  if (q.binding, q.served_model) == (c.binding, c.served_model)), None)
    quote = next((q for q in facts.quotes
                  if (q.binding, q.model_alias, q.surface) == (c.binding, c.model_alias, c.surface)), None)
    debits: list[DebitProjection] = []
    expiry = min(s.expires_at for s in common_sources)
    if quota is None or not quota.complete:
        reasons.append("QUOTA_INCOMPLETE")
    elif set(quota.required_resources) != {
            w.resource_id for w in provider.windows
            if w.binding == c.binding and w.served_model in {None, c.served_model}}:
        reasons.append("QUOTA_APPLICABLE_SET_MISMATCH")
    if quote is None:
        reasons.append("EXACT_QUOTE_MISSING")
    else:
        reasons.extend(_source_reasons(quote.stamp, Owner.ECONOMICS, pins, now))
        rate_stamp = Stamp(quote.rate_card_source, quote.stamp.observed_at, quote.stamp.expires_at)
        reasons.extend(_source_reasons(rate_stamp, Owner.ECONOMICS, pins, now))
        if (quote.provider_id, quote.served_model, quote.demand_digest) != (
                c.provider_id, c.served_model, demand_digest(demand)):
            reasons.append("QUOTE_IDENTITY_OR_DEMAND_MISMATCH")
        if not (quote.context_min <= demand.input_tokens and (
                quote.context_max is None or demand.input_tokens <= quote.context_max)):
            reasons.append("QUOTE_CONTEXT_BAND_MISMATCH")
        if quote.cash_upper_bound > demand.cash_ceiling_usd:
            reasons.append("REQUEST_CASH_CEILING")
        budget = facts.budget
        if budget.cash_used + budget.cash_reserved + quote.cash_upper_bound > budget.cash_limit:
            reasons.append("JOB_CASH_BUDGET_EXHAUSTED")
        if quota is not None:
            if {d.resource_id for d in quote.debits} != set(quota.required_resources):
                reasons.append("QUOTA_DEBIT_SET_MISMATCH")
            for debit in quote.debits:
                window = next((w for w in provider.windows if w.resource_id == debit.resource_id), None)
                if window is None:
                    reasons.append("QUOTA_HORIZON_MISSING")
                    continue
                if window.binding != c.binding or window.served_model not in {None, c.served_model}:
                    reasons.append("QUOTA_BINDING_MISMATCH")
                    continue
                if not window.starts_at <= provider.stamp.observed_at <= now < window.resets_at:
                    reasons.append("QUOTA_HORIZON_STALE_OR_FUTURE")
                    continue
                if debit.unit is not window.unit:
                    reasons.append("QUOTA_DEBIT_UNIT_MISMATCH")
                if ((window.unit is Unit.REQUESTS and debit.upper_bound < demand.max_requests)
                        or (window.unit is Unit.TOKENS and debit.upper_bound < (
                            demand.max_requests * (demand.input_tokens + demand.output_tokens)))
                        or (window.unit is Unit.USD and debit.upper_bound < quote.cash_upper_bound)):
                    reasons.append("QUOTA_DEBIT_UNDERSTATED")
                if window.unit in {Unit.REQUESTS, Unit.TOKENS} and debit.upper_bound != debit.upper_bound.to_integral_value():
                    reasons.append("QUOTA_DEBIT_UNIT_MISMATCH")
                remaining = window.limit - window.used - window.reserved
                if debit.upper_bound > remaining:
                    reasons.append("QUOTA_HARD_CAP_EXCEEDED")
                expiry = min(expiry, window.resets_at)
                debits.append(DebitProjection(_hash(window.resource_id), window.unit.value,
                                              str(debit.upper_bound), str(remaining),
                                              str(remaining - debit.upper_bound), window.resets_at))
    if reasons:
        return None, tuple(dict.fromkeys(reasons))
    assert cap is not None and quote is not None
    expiry = min(expiry, cap.stamp.expires_at, quote.stamp.expires_at)
    sources = common_sources + (_source(cap.stamp), _source(quote.stamp), _source(rate_stamp))
    selection = Selection(candidate_ref(c), c.provider_id, c.served_model,
                          _hash(c.model_alias), _hash(c.binding),
                          _hash((c.host_id, c.lane_id, c.worker_id, c.source_digest,
                                 c.execution_profile_digest, c.capability_policy_digest)),
                          c.owner_rank, expiry,
                          QuoteProjection(_hash(quote.quote_id), _source(quote.stamp),
                                          quote.rate_card_source.revision, _source(rate_stamp),
                                          "USD", str(quote.cash_upper_bound),
                                          tuple(debits)), sources)
    return selection, ()


def _project_validated(demand: Demand, facts: PoolFacts,
                       current_sources: tuple[SourcePin, ...], now: int, digest: str) -> Decision:
    sources = tuple(_source(f.stamp) for f in (
        facts.suitability, facts.capacity, facts.provider, facts.budget, facts.effect))
    snapshot = _hash((demand, facts, current_sources, now))
    reasons: list[str] = []
    for fact, owner in ((facts.suitability, Owner.ROUTER), (facts.capacity, Owner.CAPACITY),
                        (facts.provider, Owner.PROVIDER), (facts.budget, Owner.EXECUTIVE),
                        (facts.effect, Owner.EXECUTIVE)):
        reasons.extend(_source_reasons(fact.stamp, owner, current_sources, now))
    if any(f.demand_digest != digest for f in (
            facts.suitability, facts.capacity, facts.budget, facts.effect)):
        reasons.append("DEMAND_BINDING_MISMATCH")
    if facts.capacity.suitability_source != facts.suitability.stamp.pin:
        reasons.append("CAPACITY_ROUTER_SOURCE_MISMATCH")
    if facts.capacity.first_tier_id != facts.suitability.first_tier_id:
        reasons.append("CAPACITY_FIRST_TIER_MISMATCH")
    if facts.budget.job_id != demand.job_id:
        reasons.append("JOB_BUDGET_IDENTITY_MISMATCH")
    reasons.extend(_effect_reasons(demand, facts.effect))
    budget = facts.budget
    if budget.requests_used + budget.requests_reserved + demand.max_requests > budget.request_limit:
        reasons.append("JOB_REQUEST_BUDGET_EXHAUSTED")
    if budget.tokens_used + budget.tokens_reserved + demand.max_requests * (
            demand.input_tokens + demand.output_tokens) > budget.token_limit:
        reasons.append("JOB_TOKEN_BUDGET_EXHAUSTED")
    trace = ("OWNER_ORIGIN_MUST_BE_AUTHENTICATED_EXTERNALLY",
             "FIRST_ROUTER_TIER_ONLY", "CAPACITY_OWNER_ORDER_PRESERVED",
             "COMPLETE_NATIVE_HORIZONS_AND_COMPETING_RESERVATIONS_REQUIRED",
             "NO_PROVIDER_CALL_OR_RESERVATION", "REVALIDATE_AND_RESERVE_AT_INCUMBENT")
    if reasons:
        return Decision("BLOCKED", digest, snapshot, None, (), (),
                        tuple(dict.fromkeys(reasons)), trace, sources, None)

    qualified: list[Selection] = []
    exclusions: list[Exclusion] = []
    # No locally computed score, preference ladder, allocation or new policy.
    for candidate in sorted(facts.capacity.candidates, key=lambda item: item.owner_rank):
        selection, rejected = _qualified_candidate(demand, facts, candidate, current_sources, now, sources)
        if selection is None:
            exclusions.append(Exclusion(candidate_ref(candidate), rejected))
        else:
            qualified.append(selection)
    if not qualified:
        return Decision("BLOCKED", digest, snapshot, None, (), tuple(exclusions),
                        ("NO_QUALIFIED_CANDIDATE",), trace, sources, None)
    selected, *alternatives = qualified
    fallback = "PRE_SEND_PROJECTION" if facts.effect.state is Effect.PRE_SEND else "READ_ONLY_NO_EFFECT_FALLBACK"
    return Decision("PROJECTED", digest, snapshot, selected, tuple(alternatives), tuple(exclusions),
                    (fallback, "OWNER_RANK_FIRST_QUALIFIED"), trace, sources,
                    min(item.expires_at for item in qualified))


def project_model_pool(demand: Demand, facts: PoolFacts, *,
                       current_sources: tuple[SourcePin, ...], now: int) -> Decision:
    """Return an expiring non-authoritative recommendation, without any effects.

    ``current_sources`` must be a separate current owner read, not copied from
    the submitted stamps. Origin authentication and atomic reservation are the
    executing owner's duties. No H24-02 import or live owner read occurs here.
    """
    digest = demand_digest(demand)
    _validate(facts, current_sources, now)
    # Caller/thread Decimal settings must not round a cap into an acceptance.
    # Validated magnitudes need fewer than 40 significant digits; 80 is exact.
    with localcontext(Context(prec=80)):
        return _project_validated(demand, facts, current_sources, now, digest)
