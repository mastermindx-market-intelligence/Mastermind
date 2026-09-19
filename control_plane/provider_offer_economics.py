"""Time/context-qualified quotes using the existing model-economics calculator.

This is a pure consumer of reviewed, owner-supplied offer facts, NOT an approval
issuer or a second catalog. It reads/writes no state, chooses no worker/account,
and never infers subscription quota, model quality, consent or runtime authority.
Effective timestamps and integer context thresholds must be resolved by the
existing offer owner; this module does not guess them from promotional prose.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from control_plane.provider_model_economics import (
    ApiRateCard, ModelEconomicsError, ProviderModelCatalog, ProviderModelRecord,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WEEK = 7 * 24 * 60


@dataclass(frozen=True)
class TimeBoundRate:
    card: ApiRateCard
    effective_from: str
    effective_until: str
    # Half-open minute-of-week intervals in UTC, Monday 00:00 = 0.
    # An all-week rate is explicitly ((0, 10080),); no implicit fallback rate.
    weekly_minutes: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ReviewedApiOffer:
    model_key: str
    provider: str
    provider_model: str
    surface: str
    offer_digest: str
    valid_until: str
    rates: tuple[TimeBoundRate, ...]


@dataclass(frozen=True)
class TemporalQuote:
    model_key: str
    provider_model: str
    surface: str
    offer_digest: str
    request_digest: str
    rate_id: str
    context_tokens: int
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    estimated_usage_usd: Decimal
    quoted_at: str
    valid_until: str
    quote_digest: str
    # Token-valued consumption is not a cash authorization or quota reservation.
    scope: str = "estimate_only_not_capacity_or_execution_authority"


def _at(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ModelEconomicsError("invalid offer timestamp")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ModelEconomicsError("invalid offer timestamp") from None
    if at.tzinfo is None:
        raise ModelEconomicsError("offer timestamp must have a timezone")
    return at.astimezone(timezone.utc)


def _iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def _id(value: str, *, model: bool = False) -> str:
    pattern = _MODEL if model else _ID
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ModelEconomicsError("invalid offer identity")
    return value


def _digest(value: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ModelEconomicsError("invalid offer or request digest")
    return value


def _windows(value: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    if type(value) is not tuple or not 1 <= len(value) <= 64:
        raise ModelEconomicsError("invalid weekly rate windows")
    previous_end = -1
    for pair in value:
        if (type(pair) is not tuple or len(pair) != 2
                or any(type(x) is not int for x in pair)
                or not 0 <= pair[0] < pair[1] <= _WEEK
                or pair[0] < previous_end):
            raise ModelEconomicsError("invalid weekly rate windows")
        previous_end = pair[1]
    return value


def _card(card: ApiRateCard, surface: str) -> None:
    if not isinstance(card, ApiRateCard):
        raise ModelEconomicsError("invalid rate card")
    _id(card.rate_id)
    if card.surface != surface:
        raise ModelEconomicsError("rate surface mismatch")
    lo, hi = card.min_context_tokens, card.max_context_tokens
    if type(lo) is not int or lo < 0 or (hi is not None and (type(hi) is not int or hi < lo)):
        raise ModelEconomicsError("invalid context range")
    for price, nullable in ((card.input_per_million, False),
                            (card.output_per_million, False),
                            (card.cached_input_per_million, True),
                            (card.cache_write_per_million, True)):
        if nullable and price is None:
            continue
        if (not isinstance(price, Decimal) or not price.is_finite() or price < 0
                or price > Decimal("100000000") or price.as_tuple().exponent < -9):
            raise ModelEconomicsError("invalid rate price")


def _validated(offer: ReviewedApiOffer):
    if not isinstance(offer, ReviewedApiOffer):
        raise ModelEconomicsError("invalid reviewed offer")
    for value in (offer.model_key, offer.provider, offer.surface):
        _id(value)
    _id(offer.provider_model, model=True)
    _digest(offer.offer_digest)
    lease_end = _at(offer.valid_until)
    if type(offer.rates) is not tuple or not 1 <= len(offer.rates) <= 64:
        raise ModelEconomicsError("invalid offer rates")
    parsed = []
    names = set()
    for rate in offer.rates:
        if not isinstance(rate, TimeBoundRate):
            raise ModelEconomicsError("invalid timed rate")
        _card(rate.card, offer.surface)
        if rate.card.rate_id in names:
            raise ModelEconomicsError("duplicate rate id")
        names.add(rate.card.rate_id)
        start, end = _at(rate.effective_from), _at(rate.effective_until)
        if start >= end:
            raise ModelEconomicsError("empty effective rate interval")
        windows = _windows(rate.weekly_minutes)
        parsed.append((rate, start, end, windows))
    # Refuse a latent ambiguous schedule before it reaches a later request.
    for i, (left, ls, le, lw) in enumerate(parsed):
        for right, rs, re_, rw in parsed[i + 1:]:
            if max(ls, rs) >= min(le, re_):
                continue
            a, b = left.card, right.card
            overlap = ((a.max_context_tokens is None or b.min_context_tokens <= a.max_context_tokens)
                       and (b.max_context_tokens is None or a.min_context_tokens <= b.max_context_tokens))
            if overlap and any(max(x, p) < min(y, q) for x, y in lw for p, q in rw):
                raise ModelEconomicsError("overlapping time/context rate variants")
    return lease_end, parsed


def quote_temporal_offer(
    offer: ReviewedApiOffer, *, expected_offer_digest: str,
    expected_model_key: str, expected_surface: str, request_digest: str,
    now: str, context_tokens: int, input_tokens: int,
    cached_input_tokens: int = 0, cache_write_tokens: int = 0,
    output_tokens: int = 0,
) -> TemporalQuote:
    """Quote exactly one rate variant; bounds are inclusive start/exclusive end.

    Input/cached-input/cache-write token amounts are DISJOINT categories. Output
    includes billable reasoning as defined by the upstream accounting normalizer.
    Quote inputs are estimates supplied by that owner, not tokenizer claims here.
    A digest match is integrity only, not proof the caller has been authorized.
    """
    lease_end, rows = _validated(offer)
    if (offer.offer_digest != _digest(expected_offer_digest)
            or offer.model_key != _id(expected_model_key)
            or offer.surface != _id(expected_surface)):
        raise ModelEconomicsError("reviewed offer binding changed")
    _digest(request_digest)
    at = _at(now)
    if at >= lease_end:
        raise ModelEconomicsError("offer review expired")
    amounts = (context_tokens, input_tokens, cached_input_tokens, cache_write_tokens, output_tokens)
    if any(type(x) is not int or not 0 <= x <= 1000000000 for x in amounts):
        raise ModelEconomicsError("invalid token estimate")
    if input_tokens + cached_input_tokens + cache_write_tokens > context_tokens:
        raise ModelEconomicsError("disjoint input estimates exceed context")
    minute = at.weekday() * 1440 + at.hour * 60 + at.minute
    week_start = (at - timedelta(days=at.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    matches = [(rate, end, finish) for rate, start, end, windows in rows
               if start <= at < end and rate.card.accepts(context_tokens)
               for begin, finish in windows if begin <= minute < finish]
    if len(matches) != 1:
        raise ModelEconomicsError("no unique applicable rate variant")
    rate, effective_end, week_end_minute = matches[0]
    valid_until = min(lease_end, effective_end, week_start + timedelta(minutes=week_end_minute))
    # Reuse the exact existing calculator through its typed, in-memory input.
    # This ephemeral one-record value is NOT a published registry or approval.
    record = ProviderModelRecord(offer.model_key, offer.provider, offer.provider_model,
                                 None, None, frozenset(), (), (rate.card,), ())
    calculator = ProviderModelCatalog("offer-quote-input", at.date().isoformat(),
                                     {offer.model_key: record})
    dollars = calculator.estimate_api_cash_usd(
        offer.model_key, surface=offer.surface, context_tokens=context_tokens,
        input_tokens=input_tokens, cached_input_tokens=cached_input_tokens,
        cache_write_tokens=cache_write_tokens, output_tokens=output_tokens,
    )
    fields = dict(model_key=offer.model_key, provider_model=offer.provider_model,
                  surface=offer.surface, offer_digest=offer.offer_digest,
                  request_digest=request_digest, rate_id=rate.card.rate_id,
                  context_tokens=context_tokens, input_tokens=input_tokens,
                  cached_input_tokens=cached_input_tokens, cache_write_tokens=cache_write_tokens,
                  output_tokens=output_tokens, estimated_usage_usd=str(dollars),
                  quoted_at=_iso(at), valid_until=_iso(valid_until))
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    fields["estimated_usage_usd"] = dollars
    return TemporalQuote(**fields, quote_digest=digest)


def require_current_quote(quote: TemporalQuote, *, now: str, request_digest: str,
                          offer_digest: str, model_key: str, surface: str) -> None:
    """Reject reuse after an epoch/window boundary; no automatic execution/retry."""
    if not isinstance(quote, TemporalQuote):
        raise ModelEconomicsError("invalid temporal quote")
    if (quote.request_digest != _digest(request_digest)
            or quote.offer_digest != _digest(offer_digest)
            or quote.model_key != _id(model_key) or quote.surface != _id(surface)):
        raise ModelEconomicsError("quote binding changed")
    fields = asdict(quote)
    digest = fields.pop("quote_digest")
    scope = fields.pop("scope")
    fields["estimated_usage_usd"] = str(quote.estimated_usage_usd)
    actual = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != actual or scope != "estimate_only_not_capacity_or_execution_authority":
        raise ModelEconomicsError("quote integrity changed")
    at = _at(now)
    if not _at(quote.quoted_at) <= at < _at(quote.valid_until):
        raise ModelEconomicsError("quote expired or future-dated")
