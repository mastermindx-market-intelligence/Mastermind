"""GLT broad target card V1 (task T12): the outcome ruler, frozen before any outcome is read.

The card sits ADDITIVELY beside the precommitted research registry in
``brain.liquidity_lab.contracts``: it copies identity fields from ``TARGET_BY_ID`` and never
rewrites, reorders or mutates ``TARGETS``, ``TARGET_BY_ID``, ``HORIZONS_BDAYS`` or
``TargetSpec``.  For every eligible target it declares the return basis an outcome must be
measured in, the session calendar that counts horizons, the anchor price, the maturity rule
and the quote currency -- acceptance C21 (each target uses its actual return basis and its
own session/maturity rule).  The BTC and single-name motivating examples stay archived and
excluded -- acceptance C22.

What this module is NOT:

* It reads no prices and no wall clock.  Every date it uses is supplied by the caller;
  session membership comes from the existing calendar owner,
  ``portfolio.market_calendar.is_trading_day``, imported lazily inside the helpers.
* It changes no estimator behaviour.  ``build_forward_return_panel`` still anchors on the
  first SUPPLIED close after first detection and counts supplied closes; the card's
  declared-calendar maturity rule is a stated difference that task T13 reconciles.
* It is not validated (``validated`` is always ``False``).  Its horizons are PLANNING
  roles drawn from ``HORIZONS_BDAYS``; the primary horizon stays ``None`` until task T14.
* It does not pre-empt CONTRACTS section 5 (the later additive read projection): it is a
  declaration consumed by future outcome code, not a read surface.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping

from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    TARGET_BY_ID,
    TARGETS,
    ContractError,
    canonical_hash,
)

CARD_VERSION = "glt_broad_target_card.v1"
# v1 is frozen. The freeze date and the canonical content hash are part of the
# version: a different date, or any registry edit that changes a card field, must
# mint a new card version instead of silently yielding a different "v1".
V1_FROZEN_AT = date(2026, 10, 13)
BROAD_TARGET_CARD_V1_SHA256 = "f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537"
RETURN_BASES = ("price", "total_return", "excess_vs_benchmark")
DEFAULT_RETURN_BASIS = "total_return"
QUOTE_CURRENCY = "USD"
SESSION_CALENDAR = "us_equity_sessions"
CALENDAR_OWNER = "portfolio.market_calendar.is_trading_day"
CALENDAR_COVERAGE = (date(2025, 1, 1), date(2027, 12, 31))
ANCHOR_PRICE = "official_close"
ANCHOR_RULE = (
    "the anchor is the official close of the first declared-calendar session strictly "
    "after the first-detection calendar date"
)
MATURITY_RULE = (
    "an outcome at horizon h is mature only when the official close of the h-th "
    "declared-calendar session after the anchor session is available as of the evaluation "
    "clock; a missing close keeps the outcome immature and never shifts the horizon to a "
    "later session"
)
PLANNING_HORIZONS = (5, 20, 60)
FX_NOTE = (
    "every entry is a US-listed USD-quoted fund; local-currency returns and FX returns are "
    "SEPARATE outcomes that this card does not define"
)
UNDERLYING_HOLIDAY_NOTE = (
    "the underlying market's holidays are NOT US sessions; this entry is measured on US "
    "equity sessions only, so an underlying-market holiday that is a US session still "
    "counts as a session and a US holiday never does"
)

_EQUITY_RATIONALE = (
    "total return: dividends are part of holder return and ex-dividend price drops are not "
    "economic moves"
)
_NON_US_EQUITY_RATIONALE = (
    _EQUITY_RATIONALE + "; measured in USD as listed; no FX or local-currency translation"
)
# Crypto is deliberately UNRULED: an eligible entry whose asset class is missing here makes
# the build fail closed rather than inherit a default basis.
BASIS_RULINGS: Mapping[str, str] = MappingProxyType({
    "us_equity": _EQUITY_RATIONALE,
    "dm_equity": _NON_US_EQUITY_RATIONALE,
    "em_equity": _NON_US_EQUITY_RATIONALE,
    "china_equity": _NON_US_EQUITY_RATIONALE,
    "rates": (
        "total return: bond funds pay monthly distributions; a yield change in basis points "
        "is not a fund return and is refused as a basis"
    ),
    "credit": (
        "total return: high-yield and investment-grade funds pay monthly distributions that "
        "are most of their return"
    ),
    "commodity": (
        "total return: equals price for non-distributing commodity trusts and captures the "
        "distributions of funds that pay them"
    ),
})
EXCLUDED = (
    ("btc", "crypto motivating example: archived motivation per SCIENCE_PROTOCOL section 9 / "
            "acceptance C22; no new crypto programme"),
    ("baba", "single-name motivating example: archived per SCIENCE_PROTOCOL section 9 / "
             "acceptance C22; excluded by role (single_name) and by name"),
)

_ELIGIBLE_ROLE = "macro_proxy"
_NON_US_EQUITY = frozenset({"dm_equity", "em_equity", "china_equity"})


def _require_date(value: Any, name: str) -> date:
    # datetime subclasses date; a timestamp is never accepted where a calendar date is owed.
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ContractError(f"{name} must be a calendar date, not a datetime or other value")
    return value


@dataclass(frozen=True)
class TargetCardEntry:
    """One eligible target's frozen outcome ruler."""

    target_id: str
    symbol: str
    asset_class: str
    region: str
    benchmark: str | None
    return_basis: str
    allowed_bases: tuple[str, ...]
    basis_rationale: str
    quote_currency: str
    session_calendar: str
    anchor_price: str
    underlying_holiday_note: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_bases, tuple) or not set(self.allowed_bases) <= set(RETURN_BASES):
            raise ContractError("allowed_bases must be a tuple drawn from RETURN_BASES")
        if self.return_basis not in self.allowed_bases:
            raise ContractError("return_basis must be one of the entry's allowed bases")
        if ("excess_vs_benchmark" in self.allowed_bases) != (self.benchmark is not None):
            raise ContractError("excess_vs_benchmark is allowed exactly when a benchmark exists")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "region": self.region,
            "benchmark": self.benchmark,
            "return_basis": self.return_basis,
            "allowed_bases": list(self.allowed_bases),
            "basis_rationale": self.basis_rationale,
            "quote_currency": self.quote_currency,
            "session_calendar": self.session_calendar,
            "anchor_price": self.anchor_price,
            "underlying_holiday_note": self.underlying_holiday_note,
        }


@dataclass(frozen=True)
class BroadTargetCard:
    """The frozen broad target card; never validated, never a trading universe."""

    card_version: str
    frozen_at: date
    entries: tuple[TargetCardEntry, ...]
    excluded: tuple[tuple[str, str], ...]
    horizon_roles: Mapping[str, Any] = field(hash=False)
    session_calendar: str
    calendar_owner: str
    calendar_coverage: tuple[date, date]
    anchor_price: str
    anchor_rule: str
    maturity_rule: str
    fx_note: str
    basis_rulings: Mapping[str, str] = field(hash=False)
    validated: bool = False

    def __post_init__(self) -> None:
        _require_date(self.frozen_at, "frozen_at")
        if self.validated is not False:
            raise ContractError("the broad target card is never validated (T14 owns that)")
        for name in ("entries", "excluded", "calendar_coverage"):
            if not isinstance(getattr(self, name), tuple):
                raise ContractError(f"{name} must be a tuple")
        for name in ("horizon_roles", "basis_rulings"):
            if not isinstance(getattr(self, name), MappingProxyType):
                raise ContractError(f"{name} must be read-only")

    def target_ids(self) -> tuple[str, ...]:
        return tuple(entry.target_id for entry in self.entries)

    def entry(self, target_id: str) -> TargetCardEntry:
        for excluded_id, reason in self.excluded:
            if target_id == excluded_id:
                raise ContractError(f"{target_id!r} is excluded from {self.card_version}: {reason}")
        for entry in self.entries:
            if entry.target_id == target_id:
                return entry
        raise ContractError(
            f"{target_id!r} is not a {self.card_version} entry "
            f"(unknown id, or a role other than {_ELIGIBLE_ROLE})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_version": self.card_version,
            "frozen_at": self.frozen_at.isoformat(),
            "validated": self.validated,
            "horizon_roles": {
                "planning_candidates": list(self.horizon_roles["planning_candidates"]),
                "primary": self.horizon_roles["primary"],
            },
            "session_calendar": self.session_calendar,
            "calendar_owner": self.calendar_owner,
            "calendar_coverage": [day.isoformat() for day in self.calendar_coverage],
            "anchor_price": self.anchor_price,
            "anchor_rule": self.anchor_rule,
            "maturity_rule": self.maturity_rule,
            "fx_note": self.fx_note,
            "basis_rulings": {key: self.basis_rulings[key] for key in self.basis_rulings},
            "entries": [entry.to_dict() for entry in self.entries],
            "excluded": [[target_id, reason] for target_id, reason in self.excluded],
        }


def build_broad_target_card(*, frozen_at: date) -> BroadTargetCard:
    """Build the v1 card from the registry; the caller supplies the freeze date, which v1 pins."""
    _require_date(frozen_at, "frozen_at")
    if frozen_at != V1_FROZEN_AT:
        raise ContractError(
            f"{CARD_VERSION} is frozen at {V1_FROZEN_AT.isoformat()}; "
            "a different freeze date needs a new card version"
        )
    if not set(PLANNING_HORIZONS) <= set(HORIZONS_BDAYS):
        raise ContractError("planning horizons must be registered HORIZONS_BDAYS")
    excluded_ids = {target_id for target_id, _ in EXCLUDED}
    entries = []
    for target in TARGETS:
        if target.role != _ELIGIBLE_ROLE or target.target_id in excluded_ids:
            continue
        spec = TARGET_BY_ID.get(target.target_id)
        if spec is None or spec != target:
            raise ContractError(f"registry disagreement for {target.target_id!r}")
        rationale = BASIS_RULINGS.get(spec.asset_class)
        if rationale is None:
            raise ContractError(
                f"asset class {spec.asset_class!r} of {spec.target_id!r} has no return-basis "
                "ruling; the card fails closed"
            )
        allowed = ("price", "total_return")
        if spec.benchmark is not None:
            allowed += ("excess_vs_benchmark",)
        entries.append(TargetCardEntry(
            target_id=spec.target_id,
            symbol=spec.symbol,
            asset_class=spec.asset_class,
            region=spec.region,
            benchmark=spec.benchmark,
            return_basis=DEFAULT_RETURN_BASIS,
            allowed_bases=allowed,
            basis_rationale=rationale,
            quote_currency=QUOTE_CURRENCY,
            session_calendar=SESSION_CALENDAR,
            anchor_price=ANCHOR_PRICE,
            underlying_holiday_note=(
                UNDERLYING_HOLIDAY_NOTE if spec.asset_class in _NON_US_EQUITY else None
            ),
        ))
    card_ids = {entry.target_id for entry in entries}
    for entry in entries:
        if entry.benchmark is not None and entry.benchmark not in card_ids:
            raise ContractError(
                f"benchmark {entry.benchmark!r} of {entry.target_id!r} is not itself a card entry"
            )
    card = BroadTargetCard(
        card_version=CARD_VERSION,
        frozen_at=frozen_at,
        entries=tuple(entries),
        excluded=tuple((target_id, reason) for target_id, reason in EXCLUDED),
        horizon_roles=MappingProxyType({"planning_candidates": PLANNING_HORIZONS, "primary": None}),
        session_calendar=SESSION_CALENDAR,
        calendar_owner=CALENDAR_OWNER,
        calendar_coverage=CALENDAR_COVERAGE,
        anchor_price=ANCHOR_PRICE,
        anchor_rule=ANCHOR_RULE,
        maturity_rule=MATURITY_RULE,
        fx_note=FX_NOTE,
        basis_rulings=BASIS_RULINGS,
    )
    if canonical_hash(card.to_dict()) != BROAD_TARGET_CARD_V1_SHA256:
        raise ContractError(
            f"{CARD_VERSION} content hash drifted from BROAD_TARGET_CARD_V1_SHA256; "
            "a registry change needs a new card version"
        )
    return card


BROAD_TARGET_CARD_V1 = build_broad_target_card(frozen_at=V1_FROZEN_AT)


def validate_return_basis(
    target_id: str, basis: str, *, card: BroadTargetCard = BROAD_TARGET_CARD_V1
) -> str:
    """Return ``basis`` when the entry allows it; refuse every substitute by name."""
    entry = card.entry(target_id)
    if isinstance(basis, str) and basis in entry.allowed_bases:
        return basis
    lowered = basis.lower() if isinstance(basis, str) else ""
    if lowered == "yield_change_bp":
        raise ContractError(
            f"{target_id}: a yield change in basis points is not a fund return; "
            f"use one of {entry.allowed_bases}"
        )
    if any(token in lowered for token in ("fx", "inver", "local_currency")):
        raise ContractError(
            f"{target_id}: an FX quote or inversion is not a return basis for this card; "
            f"{FX_NOTE}"
        )
    if basis == "excess_vs_benchmark":
        raise ContractError(f"{target_id}: no declared benchmark, so excess_vs_benchmark is refused")
    raise ContractError(f"{target_id}: unknown return basis {basis!r}; closed vocabulary {RETURN_BASES}")


def is_target_session(d: date) -> bool:
    """True when ``d`` is a declared-calendar (US equity) session inside the owner's coverage."""
    _require_date(d, "session date")
    low, high = CALENDAR_COVERAGE
    if not low <= d <= high:
        raise ContractError(
            f"{d.isoformat()} is outside declared calendar coverage "
            f"{low.isoformat()}..{high.isoformat()}"
        )
    from portfolio.market_calendar import is_trading_day

    return bool(is_trading_day(d))


def anchor_session(first_detected: date) -> date:
    """The first declared-calendar session strictly after the first-detection date."""
    day = _require_date(first_detected, "first_detected") + timedelta(days=1)
    while not is_target_session(day):
        day += timedelta(days=1)
    return day


def nth_session_after(anchor: date, h: int) -> date:
    """The h-th declared-calendar session after an anchor session (coverage errors propagate)."""
    if isinstance(h, bool) or not isinstance(h, int) or h not in HORIZONS_BDAYS:
        raise ContractError(f"horizon {h!r} is not a registered HORIZONS_BDAYS value")
    if not is_target_session(_require_date(anchor, "anchor")):
        raise ContractError(f"anchor {anchor.isoformat()} is not a declared-calendar session")
    day, counted = anchor, 0
    while counted < h:
        day += timedelta(days=1)
        if is_target_session(day):
            counted += 1
    return day


def outcome_is_mature(
    *, anchor: date, horizon_bdays: int, available_close_dates: Collection[date]
) -> bool:
    """True iff the exit session's close is available; a missing exit close never shifts."""
    available = set()
    for value in available_close_dates:
        available.add(_require_date(value, "available close date"))
    return nth_session_after(anchor, horizon_bdays) in available


__all__ = [
    "ANCHOR_PRICE",
    "ANCHOR_RULE",
    "BASIS_RULINGS",
    "BROAD_TARGET_CARD_V1",
    "BROAD_TARGET_CARD_V1_SHA256",
    "CALENDAR_COVERAGE",
    "CALENDAR_OWNER",
    "CARD_VERSION",
    "DEFAULT_RETURN_BASIS",
    "EXCLUDED",
    "FX_NOTE",
    "MATURITY_RULE",
    "PLANNING_HORIZONS",
    "QUOTE_CURRENCY",
    "RETURN_BASES",
    "SESSION_CALENDAR",
    "UNDERLYING_HOLIDAY_NOTE",
    "V1_FROZEN_AT",
    "BroadTargetCard",
    "TargetCardEntry",
    "anchor_session",
    "build_broad_target_card",
    "is_target_session",
    "nth_session_after",
    "outcome_is_mature",
    "validate_return_basis",
]
