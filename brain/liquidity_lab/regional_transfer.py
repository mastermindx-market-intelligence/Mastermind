"""T19 regional transfer challenge (research substrate, measurement only).

A region's response is never assumed from the US or from a pooled global fit.
Each region has a frozen :class:`TransferCard` in
``research/liquidity_transmission/glt_transfer_cards.v1.json``. The card names:

* the region's T10 measurement status;
* its local currency, and its local and listing calendars;
* the FX fixing policy (``known_at_only``);
* the context owner of its policy reaction;
* its hierarchy members, taken from the broad target card registry;
* the leave-country-out and leave-era-out holdout plan.

The card was frozen before any fit.

* :func:`decompose_returns` splits a USD log return into a local-currency return
  and an FX translation return on one calendar. It uses only fixings known at
  the cutoff:

  - a fixing dated or known after ``known_at`` raises :class:`FutureFixingError`;
  - a mixed-calendar join raises :class:`CalendarMismatchError` (there is no
    forward-fill).
* :func:`qualify_transfer` compares the pooled (borrowed) cells with the
  region's own local cells. It returns one of four statuses:

  - ``supported_local`` only when the local predictions beat the pooled
    predictions on BOTH frozen paired holdouts, under the window guard;
  - ``pooled_only_borrowed`` otherwise when a pooled member cell exists. The
    borrowed prior's effective n is reported separately and never summed into
    ``local_effective_n``;
  - ``abstain`` outside the registered hierarchy, below the local floor, or
    with a missing holdout;
  - ``missing_input`` when T10 did not measure the region, or its local series
    or calendar is absent. A missing input never falls back to USD returns or
    to a US cell.

Targets the registry excludes raise :class:`ExcludedRoleError`, through the
registry's own ``BroadTargetCard.entry`` check. Uncertainty here is pointwise;
significance belongs to T20. Nothing here sizes, ranks or recommends a position.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from brain.liquidity_lab.baselines import PairedPopulation, mean_squared_error
from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    ContractError,
    _finite,
    _utc_timestamp,
    canonical_hash,
)
from brain.liquidity_lab.estimator import ResponseCurveCell
from brain.liquidity_lab.target_card import (
    BROAD_TARGET_CARD_V1,
    BROAD_TARGET_CARD_V1_SHA256,
    TargetCardEntry,
)
from brain.liquidity_lab.validation import WalkForwardPrediction
from brain.liquidity_lab.window_guard import WindowGuard

CARDS_SCHEMA = "glt_transfer_cards.v1"
RESULT_SCHEMA = "glt_transfer_result.v1"
CARDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "liquidity_transmission"
    / "glt_transfer_cards.v1.json"
)
MEASUREMENT_STATUSES = ("measured", "assumption_only_context", "missing_input")
STATUSES = ("supported_local", "pooled_only_borrowed", "abstain", "missing_input")
HOLDOUT_KINDS = ("leave_country_out", "leave_era_out")
FX_FIXING_POLICY = "known_at_only"
UNCERTAINTY_KIND = "pointwise"
COPIED_US_REASON = "copied_us_probability_refused"
UNASSIGNED_OWNER = "missing_owner:unassigned"
US_REGION = "us"
USD = "USD"
_IDENTITY_TOLERANCE = 1e-12


# ------------------------------------------------------------------ refusals
class RegionalTransferError(ContractError):
    """Base class for the T19 refusals."""


class FutureFixingError(RegionalTransferError):
    """An FX fixing dated or known after the cutoff was supplied."""


class CalendarMismatchError(RegionalTransferError):
    """Two series on different calendars, or different session sets, were joined."""


class ExcludedRoleError(RegionalTransferError):
    """The broad target card registry excludes (or does not register) this target."""


def _registry_entry(target_id: Any) -> TargetCardEntry:
    """Reuse the registry's own role check; never a second exclusion list."""

    try:
        return BROAD_TARGET_CARD_V1.entry(str(target_id))
    except ContractError as exc:
        raise ExcludedRoleError(str(exc)) from exc


def _registry_members(registry_region: str) -> tuple[str, ...]:
    return tuple(
        target_id
        for target_id in BROAD_TARGET_CARD_V1.target_ids()
        if BROAD_TARGET_CARD_V1.entry(target_id).region == registry_region
    )


def _date(name: str, value: Any) -> date:
    if isinstance(value, datetime):
        raise ContractError(f"{name} must be a session date, not a timestamp")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO date") from exc


def _text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ContractError(f"{name} is empty")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ------------------------------------------------------------ holdout plan
@dataclass(frozen=True, slots=True)
class Era:
    era_id: str
    start: date
    end: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "era_id", _text("era_id", self.era_id))
        object.__setattr__(self, "start", _date("era start", self.start))
        object.__setattr__(self, "end", _date("era end", self.end))
        if self.end < self.start:
            raise ContractError(f"era {self.era_id} ends before it starts")

    def contains(self, session: date) -> bool:
        return self.start <= session <= self.end

    def to_dict(self) -> dict[str, str]:
        return {"end": self.end.isoformat(), "era_id": self.era_id, "start": self.start.isoformat()}


@dataclass(frozen=True, slots=True)
class HoldoutPlan:
    """The frozen holdout plan of one card. Its hash binds every scored holdout."""

    eval_horizon_bdays: int
    local_floor_effective_n: int
    margin: float
    leave_country_out: tuple[str, ...]
    leave_era_out: tuple[Era, ...]

    def __post_init__(self) -> None:
        horizon = int(self.eval_horizon_bdays)
        if horizon not in HORIZONS_BDAYS:
            raise ContractError(f"eval_horizon_bdays {horizon} is not a preregistered horizon")
        floor = int(self.local_floor_effective_n)
        if floor < 1:
            raise ContractError("local_floor_effective_n must be positive")
        margin = _finite("margin", self.margin)
        if not 0.0 < margin <= 1.0:
            raise ContractError("margin must lie in (0, 1]: local must not lose to pooled")
        countries = tuple(str(t) for t in self.leave_country_out)
        if len(set(countries)) != len(countries):
            raise ContractError("leave_country_out repeats a member")
        eras = tuple(e if isinstance(e, Era) else Era(**dict(e)) for e in self.leave_era_out)
        if not eras:
            raise ContractError("leave_era_out names no era")
        for earlier, later in zip(eras, eras[1:]):
            if later.start <= earlier.end:
                raise ContractError("leave_era_out eras must be ordered and disjoint")
        object.__setattr__(self, "eval_horizon_bdays", horizon)
        object.__setattr__(self, "local_floor_effective_n", floor)
        object.__setattr__(self, "margin", margin)
        object.__setattr__(self, "leave_country_out", countries)
        object.__setattr__(self, "leave_era_out", eras)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HoldoutPlan":
        return cls(
            eval_horizon_bdays=payload["eval_horizon_bdays"],
            local_floor_effective_n=payload["local_floor_effective_n"],
            margin=payload["margin"],
            leave_country_out=tuple(payload["leave_country_out"]),
            leave_era_out=tuple(Era(**dict(era)) for era in payload["leave_era_out"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_horizon_bdays": self.eval_horizon_bdays,
            "leave_country_out": list(self.leave_country_out),
            "leave_era_out": [era.to_dict() for era in self.leave_era_out],
            "local_floor_effective_n": self.local_floor_effective_n,
            "margin": self.margin,
        }

    @property
    def plan_hash(self) -> str:
        return canonical_hash(self.to_dict())

    def era_of(self, session: date) -> Era | None:
        for era in self.leave_era_out:
            if era.contains(session):
                return era
        return None


# ------------------------------------------------------------ transfer card
@dataclass(frozen=True)
class TransferCard:
    """One region's frozen transfer card. It holds no fitted number."""

    region_id: str
    measurement_status: str
    t10_row: str
    local_currency: str
    local_calendar_ref: str | None
    listing_calendar_ref: str | None
    fx_fixing_policy: str
    fx_translation_series: str | None
    fx_rights_status: str
    policy_reaction_owner: str | None
    registry_region: str | None
    hierarchy_members: tuple[str, ...]
    local_return_series: str | None
    missing_owners: tuple[str, ...]
    holdout_plan: HoldoutPlan
    card_hash: str
    preregistration_card_hash: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "region_id", _text("region_id", self.region_id))
        if self.measurement_status not in MEASUREMENT_STATUSES:
            raise ContractError(
                f"measurement_status {self.measurement_status!r} not in {MEASUREMENT_STATUSES}"
            )
        if self.fx_fixing_policy != FX_FIXING_POLICY:
            raise ContractError(f"fx_fixing_policy must be {FX_FIXING_POLICY!r}")
        currency = _text("local_currency", self.local_currency)
        if len(currency) != 3 or not currency.isalpha() or not currency.isupper():
            raise ContractError(f"local_currency {currency!r} is not an ISO code")
        for name in (
            "local_calendar_ref",
            "listing_calendar_ref",
            "fx_translation_series",
            "policy_reaction_owner",
            "registry_region",
            "local_return_series",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name)))
        if not isinstance(self.holdout_plan, HoldoutPlan):
            raise ContractError("holdout_plan must be a HoldoutPlan")
        members = tuple(str(t) for t in self.hierarchy_members)
        if len(set(members)) != len(members):
            raise ContractError(f"{self.region_id}: hierarchy_members repeats a target")
        for target_id in members:
            _registry_entry(target_id)
        if self.registry_region is None:
            if members:
                raise ContractError(
                    f"{self.region_id}: hierarchy members come from a registry region; none is named"
                )
        elif set(members) != set(_registry_members(self.registry_region)):
            raise ContractError(
                f"{self.region_id}: hierarchy_members must equal the registry targets of "
                f"region {self.registry_region!r}"
            )
        if set(self.holdout_plan.leave_country_out) != set(members):
            raise ContractError(f"{self.region_id}: leave_country_out must hold out every member")
        object.__setattr__(self, "hierarchy_members", members)
        object.__setattr__(self, "missing_owners", tuple(str(o) for o in self.missing_owners))
        computed = canonical_hash(self.to_dict(include_hash=False))
        if self.card_hash != computed:
            raise ContractError(
                f"transfer card {self.region_id} card_hash mismatch: {self.card_hash!r} != {computed}"
            )

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any], *, preregistration_card_hash: str | None = None
    ) -> "TransferCard":
        return cls(
            region_id=payload["region_id"],
            measurement_status=payload["measurement_status"],
            t10_row=payload["t10_row"],
            local_currency=payload["local_currency"],
            local_calendar_ref=payload["local_calendar_ref"],
            listing_calendar_ref=payload["listing_calendar_ref"],
            fx_fixing_policy=payload["fx_fixing_policy"],
            fx_translation_series=payload["fx_translation_series"],
            fx_rights_status=payload["fx_rights_status"],
            policy_reaction_owner=payload["policy_reaction_owner"],
            registry_region=payload["registry_region"],
            hierarchy_members=tuple(payload["hierarchy_members"]),
            local_return_series=payload["local_return_series"],
            missing_owners=tuple(payload["missing_owners"]),
            holdout_plan=HoldoutPlan.from_dict(payload["holdout_plan"]),
            card_hash=payload["card_hash"],
            preregistration_card_hash=preregistration_card_hash,
        )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "region_id": self.region_id,
            "measurement_status": self.measurement_status,
            "t10_row": self.t10_row,
            "local_currency": self.local_currency,
            "local_calendar_ref": self.local_calendar_ref,
            "listing_calendar_ref": self.listing_calendar_ref,
            "fx_fixing_policy": self.fx_fixing_policy,
            "fx_translation_series": self.fx_translation_series,
            "fx_rights_status": self.fx_rights_status,
            "policy_reaction_owner": self.policy_reaction_owner,
            "registry_region": self.registry_region,
            "hierarchy_members": list(self.hierarchy_members),
            "local_return_series": self.local_return_series,
            "missing_owners": list(self.missing_owners),
            "holdout_plan": self.holdout_plan.to_dict(),
        }
        if include_hash:
            payload["card_hash"] = self.card_hash
        return payload


@dataclass(frozen=True)
class TransferCards:
    definition_hash: str
    preregistration_card_hash: str
    target_card_sha256: str
    cards: tuple[TransferCard, ...]

    def __getitem__(self, region_id: str) -> TransferCard:
        for card in self.cards:
            if card.region_id == region_id:
                return card
        raise ContractError(
            f"no transfer card for region {region_id!r}; a region without a card is missing_input"
        )

    def region_ids(self) -> tuple[str, ...]:
        return tuple(card.region_id for card in self.cards)


def load_transfer_cards(path: Path | str = CARDS_PATH) -> TransferCards:
    """Load the frozen cards. Verify the definition hash, each card hash and the registry identity."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != CARDS_SCHEMA:
        raise ContractError(f"expected schema {CARDS_SCHEMA}")
    recorded = document.get("definition_hash")
    computed = canonical_hash({k: v for k, v in document.items() if k != "definition_hash"})
    if recorded != computed:
        raise ContractError(f"transfer cards definition_hash mismatch: {recorded!r} != {computed}")
    if document.get("validated") is not False:
        raise ContractError("the transfer cards are research cards and never validated here")
    target_card = document.get("target_card") or {}
    if target_card.get("sha256") != BROAD_TARGET_CARD_V1_SHA256:
        raise ContractError("the transfer cards were frozen against another broad target card")
    prereg = _text("preregistration_card_hash", document.get("preregistration_card_hash"))
    cards = tuple(
        TransferCard.from_dict(card, preregistration_card_hash=prereg) for card in document["cards"]
    )
    region_ids = [card.region_id for card in cards]
    if len(set(region_ids)) != len(region_ids):
        raise ContractError("a region carries more than one transfer card")
    return TransferCards(
        definition_hash=computed,
        preregistration_card_hash=prereg,
        target_card_sha256=str(target_card["sha256"]),
        cards=cards,
    )


# --------------------------------------------------- local / FX decomposition
@dataclass(frozen=True, slots=True)
class LocalPriceSeries:
    series_id: str
    currency: str
    calendar_ref: str
    sessions: tuple[date, ...]
    prices: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "series_id", _text("series_id", self.series_id))
        object.__setattr__(self, "currency", _text("currency", self.currency))
        object.__setattr__(self, "calendar_ref", _text("calendar_ref", self.calendar_ref))
        sessions = tuple(_date("session", s) for s in self.sessions)
        prices = tuple(_finite("price", p) for p in self.prices)
        if len(sessions) != len(prices) or len(sessions) < 2:
            raise ContractError("a local price series needs two or more aligned sessions")
        if any(later <= earlier for earlier, later in zip(sessions, sessions[1:])):
            raise ContractError("local sessions must be strictly increasing")
        if any(p <= 0.0 for p in prices):
            raise ContractError("local prices must be positive")
        object.__setattr__(self, "sessions", sessions)
        object.__setattr__(self, "prices", prices)


@dataclass(frozen=True, slots=True)
class FxFixing:
    fixing_date: date
    usd_per_local: float
    known_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "fixing_date", _date("fixing_date", self.fixing_date))
        rate = _finite("usd_per_local", self.usd_per_local)
        if rate <= 0.0:
            raise ContractError("usd_per_local must be positive")
        object.__setattr__(self, "usd_per_local", rate)
        known_at = _utc_timestamp("fixing known_at", self.known_at)
        if known_at.date() < self.fixing_date:
            raise ContractError("a fixing cannot be known before its fixing date")
        object.__setattr__(self, "known_at", known_at)


@dataclass(frozen=True, slots=True)
class FxFixingSeries:
    pair: str
    currency: str
    calendar_ref: str
    fixings: tuple[FxFixing, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", _text("pair", self.pair))
        object.__setattr__(self, "currency", _text("currency", self.currency))
        object.__setattr__(self, "calendar_ref", _text("calendar_ref", self.calendar_ref))
        fixings = tuple(self.fixings)
        if not fixings or not all(isinstance(f, FxFixing) for f in fixings):
            raise ContractError("an FX fixing series needs FxFixing rows")
        dates = [f.fixing_date for f in fixings]
        if any(later <= earlier for earlier, later in zip(dates, dates[1:])):
            raise ContractError("fixing dates must be strictly increasing")
        object.__setattr__(self, "fixings", fixings)


@dataclass(frozen=True, slots=True)
class ReturnDecomposition:
    series_id: str
    currency: str
    calendar_ref: str
    start_session: date
    end_session: date
    local_ccy_return: float
    fx_return: float
    usd_return: float
    fixing_known_at: datetime | None
    known_at: datetime

    def __post_init__(self) -> None:
        for name in ("local_ccy_return", "fx_return", "usd_return"):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if abs(self.usd_return - (self.local_ccy_return + self.fx_return)) > _IDENTITY_TOLERANCE:
            raise ContractError("usd_return must equal local_ccy_return + fx_return (log returns)")
        if self.fixing_known_at is not None and self.fixing_known_at > self.known_at:
            raise FutureFixingError("a fixing used in the decomposition was known after known_at")


def decompose_returns(
    local_px: LocalPriceSeries,
    fx_fixings: FxFixingSeries | None,
    *,
    known_at: datetime | str,
) -> ReturnDecomposition:
    """Split the USD log return of ``local_px`` over its sessions into local and FX legs.

    Only fixings known at ``known_at`` may be supplied. The fixing dates must be
    exactly the local sessions on the same calendar; nothing is forward-filled.
    A USD-quoted series has no FX leg. A non-USD series without fixings is refused
    and never treated as USD.
    """

    if not isinstance(local_px, LocalPriceSeries):
        raise ContractError("local_px must be a LocalPriceSeries")
    cutoff = _utc_timestamp("known_at", known_at)
    late = [s for s in local_px.sessions if s > cutoff.date()]
    if late:
        raise RegionalTransferError(
            f"local session {late[0].isoformat()} is after known_at {cutoff.isoformat()}"
        )
    start, end = local_px.sessions[0], local_px.sessions[-1]
    local_return = math.log(local_px.prices[-1] / local_px.prices[0])
    if fx_fixings is None:
        if local_px.currency != USD:
            raise ContractError(
                f"{local_px.series_id} is quoted in {local_px.currency}; FX fixings are required "
                "and there is no USD fallback"
            )
        fx_return, fixing_known_at = 0.0, None
    else:
        if not isinstance(fx_fixings, FxFixingSeries):
            raise ContractError("fx_fixings must be an FxFixingSeries")
        if local_px.currency == USD:
            raise ContractError("a USD-quoted series has no FX leg to translate")
        if fx_fixings.currency != local_px.currency:
            raise ContractError(
                f"fixing currency {fx_fixings.currency} != local currency {local_px.currency}"
            )
        future = [
            f for f in fx_fixings.fixings if f.known_at > cutoff or f.fixing_date > cutoff.date()
        ]
        if future:
            raise FutureFixingError(
                f"{fx_fixings.pair} fixing {future[0].fixing_date.isoformat()} known at "
                f"{future[0].known_at.isoformat()} is after known_at {cutoff.isoformat()}"
            )
        if fx_fixings.calendar_ref != local_px.calendar_ref:
            raise CalendarMismatchError(
                f"local calendar {local_px.calendar_ref!r} != fixing calendar {fx_fixings.calendar_ref!r}"
            )
        by_date = {f.fixing_date: f for f in fx_fixings.fixings}
        if set(by_date) != set(local_px.sessions):
            missing = sorted(set(local_px.sessions) - set(by_date))
            extra = sorted(set(by_date) - set(local_px.sessions))
            raise CalendarMismatchError(
                f"fixing dates differ from local sessions (missing {len(missing)}, extra {len(extra)}); "
                "no forward-fill"
            )
        first, last = by_date[start], by_date[end]
        fx_return = math.log(last.usd_per_local / first.usd_per_local)
        fixing_known_at = max(first.known_at, last.known_at)
    return ReturnDecomposition(
        series_id=local_px.series_id,
        currency=local_px.currency,
        calendar_ref=local_px.calendar_ref,
        start_session=start,
        end_session=end,
        local_ccy_return=local_return,
        fx_return=fx_return,
        usd_return=local_return + fx_return,
        fixing_known_at=fixing_known_at,
        known_at=cutoff,
    )


# ----------------------------------------------------------- transfer inputs
@dataclass(frozen=True, slots=True)
class LocalCells:
    """The region's own cells, fitted in its local currency on its local calendar."""

    region_id: str
    currency: str
    calendar_ref: str
    cells: tuple[ResponseCurveCell, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "region_id", _text("region_id", self.region_id))
        object.__setattr__(self, "currency", _text("currency", self.currency))
        object.__setattr__(self, "calendar_ref", _text("calendar_ref", self.calendar_ref))
        cells = tuple(self.cells)
        if not all(isinstance(c, ResponseCurveCell) for c in cells):
            raise ContractError("local cells must be ResponseCurveCell rows")
        object.__setattr__(self, "cells", cells)


@dataclass(frozen=True, slots=True)
class HoldoutScores:
    pooled: tuple[WalkForwardPrediction, ...]
    local: tuple[WalkForwardPrediction, ...]

    def __post_init__(self) -> None:
        for name in ("pooled", "local"):
            rows = tuple(getattr(self, name))
            if not all(isinstance(r, WalkForwardPrediction) for r in rows):
                raise ContractError(f"{name} holdout rows must be WalkForwardPrediction")
            object.__setattr__(self, name, rows)


@dataclass(frozen=True, slots=True)
class TransferHoldouts:
    plan_hash: str
    leave_country_out: HoldoutScores | None = None
    leave_era_out: HoldoutScores | None = None


# ---------------------------------------------------------------- results
CellKey = tuple[str, str, str, int]


@dataclass(frozen=True, slots=True)
class PairedCellRow:
    target_id: str
    shock_family: str
    condition_bucket: str
    horizon_bdays: int
    pooled_mean: float | None
    local_mean: float | None
    pooled_effective_n: int
    local_effective_n: int


@dataclass(frozen=True, slots=True)
class PairedComparison:
    """Pooled and local member cells on the same keys; unpaired keys stay listed."""

    rows: tuple[PairedCellRow, ...]
    pooled_only_keys: tuple[CellKey, ...]
    local_only_keys: tuple[CellKey, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [
                {
                    "target_id": r.target_id,
                    "shock_family": r.shock_family,
                    "condition_bucket": r.condition_bucket,
                    "horizon_bdays": r.horizon_bdays,
                    "pooled_mean": r.pooled_mean,
                    "local_mean": r.local_mean,
                    "pooled_effective_n": r.pooled_effective_n,
                    "local_effective_n": r.local_effective_n,
                }
                for r in self.rows
            ],
            "pooled_only_keys": [list(k) for k in self.pooled_only_keys],
            "local_only_keys": [list(k) for k in self.local_only_keys],
        }


@dataclass(frozen=True, slots=True)
class HoldoutResult:
    kind: str
    held_out: tuple[str, ...]
    n_paired_keys: int
    local_mse: float | None
    pooled_mse: float | None
    margin: float
    floor: int
    local_beats_pooled: bool
    per_group: tuple[tuple[str, int], ...]
    refused_by_guard: int
    reason: str | None

    def __post_init__(self) -> None:
        if self.kind not in HOLDOUT_KINDS:
            raise ContractError(f"unknown holdout kind {self.kind!r}")
        if self.local_beats_pooled:
            if self.local_mse is None or self.pooled_mse is None:
                raise ContractError("a winning holdout needs both paired losses")
            if self.n_paired_keys < self.floor:
                raise ContractError("a winning holdout needs at least the floor of paired keys")
            if self.local_mse > self.margin * self.pooled_mse:
                raise ContractError("local_beats_pooled contradicts the paired losses")
            if self.reason is not None:
                raise ContractError("a winning holdout carries no refusal reason")
        elif not self.reason:
            raise ContractError("a holdout that local does not win names its reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "held_out": list(self.held_out),
            "n_paired_keys": self.n_paired_keys,
            "local_mse": self.local_mse,
            "pooled_mse": self.pooled_mse,
            "margin": self.margin,
            "floor": self.floor,
            "local_beats_pooled": self.local_beats_pooled,
            "per_group": [list(g) for g in self.per_group],
            "refused_by_guard": self.refused_by_guard,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TransferResult:
    region_id: str
    status: str
    card_hash: str
    plan_hash: str
    pooled_vs_local: PairedComparison | None
    leave_country_out: HoldoutResult | None
    leave_era_out: HoldoutResult | None
    coverage: float | None
    local_effective_n: int | None
    borrowed_prior_effective_n: int | None
    uncertainty_kind: str = UNCERTAINTY_KIND
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ContractError(f"status {self.status!r} not in {STATUSES}")
        if self.uncertainty_kind != UNCERTAINTY_KIND:
            raise ContractError("T19 uncertainty is pointwise; significance belongs to T20")
        reasons = tuple(str(r) for r in self.reasons)
        if any(not r for r in reasons):
            raise ContractError("an empty reason is not a reason")
        object.__setattr__(self, "reasons", reasons)
        if self.status != "supported_local" and not reasons:
            raise ContractError(f"a {self.status} result names its reasons")
        if self.status == "missing_input":
            carried = [
                name
                for name in (
                    "pooled_vs_local",
                    "leave_country_out",
                    "leave_era_out",
                    "coverage",
                    "local_effective_n",
                    "borrowed_prior_effective_n",
                )
                if getattr(self, name) is not None
            ]
            if carried:
                raise ContractError(f"a missing_input region carries no number: {carried}")
        if self.status == "supported_local":
            if reasons:
                raise ContractError("supported_local carries no refusal reason")
            for holdout in (self.leave_country_out, self.leave_era_out):
                if holdout is None or not holdout.local_beats_pooled:
                    raise ContractError("supported_local needs local to win BOTH frozen holdouts")
            if self.local_effective_n is None:
                raise ContractError("supported_local reports its local effective n")
        if self.status == "pooled_only_borrowed":
            if self.pooled_vs_local is None or self.borrowed_prior_effective_n is None:
                raise ContractError(
                    "pooled_only_borrowed shows the pooled cells and the borrowed prior separately"
                )
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ContractError("coverage is a fraction of the region's members")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "evidence_tier": "research",
            "validated": False,
            "region_id": self.region_id,
            "status": self.status,
            "card_hash": self.card_hash,
            "plan_hash": self.plan_hash,
            "uncertainty_kind": self.uncertainty_kind,
            "reasons": list(self.reasons),
            "coverage": self.coverage,
            "local_effective_n": self.local_effective_n,
            "borrowed_prior_effective_n": self.borrowed_prior_effective_n,
            "pooled_vs_local": None if self.pooled_vs_local is None else self.pooled_vs_local.to_dict(),
            "leave_country_out": None
            if self.leave_country_out is None
            else self.leave_country_out.to_dict(),
            "leave_era_out": None if self.leave_era_out is None else self.leave_era_out.to_dict(),
        }


# ----------------------------------------------------------- qualification
def _cell_key(cell: ResponseCurveCell) -> CellKey:
    return (str(cell.target_id), str(cell.shock_family), str(cell.condition_bucket), int(cell.horizon_bdays))


def _keyed_cells(name: str, cells: Sequence[ResponseCurveCell]) -> dict[CellKey, ResponseCurveCell]:
    keyed: dict[CellKey, ResponseCurveCell] = {}
    for cell in cells:
        key = _cell_key(cell)
        if key in keyed:
            raise ContractError(f"{name} cells repeat key {key}")
        keyed[key] = cell
    return keyed


def _pair_cells(
    pooled: Sequence[ResponseCurveCell], local: Sequence[ResponseCurveCell]
) -> PairedComparison:
    pooled_keyed = _keyed_cells("pooled", pooled)
    local_keyed = _keyed_cells("local", local)
    shared = sorted(set(pooled_keyed) & set(local_keyed))
    rows = tuple(
        PairedCellRow(
            target_id=key[0],
            shock_family=key[1],
            condition_bucket=key[2],
            horizon_bdays=key[3],
            pooled_mean=pooled_keyed[key].shrunk_mean,
            local_mean=local_keyed[key].shrunk_mean,
            pooled_effective_n=int(pooled_keyed[key].effective_n),
            local_effective_n=int(local_keyed[key].effective_n),
        )
        for key in shared
    )
    return PairedComparison(
        rows=rows,
        pooled_only_keys=tuple(sorted(set(pooled_keyed) - set(local_keyed))),
        local_only_keys=tuple(sorted(set(local_keyed) - set(pooled_keyed))),
    )


def _missing_input_reasons(card: TransferCard, local_cells: LocalCells | None) -> tuple[str, ...]:
    reasons: list[str] = []
    if card.measurement_status != "measured":
        reasons.append(f"t10_status:{card.measurement_status}")
    if card.local_return_series is None:
        reasons.append("local_return_series_absent")
    if card.local_calendar_ref is None:
        reasons.append("local_calendar_absent")
    if reasons:
        owners = [f"missing_owner:{owner}" for owner in card.missing_owners]
        reasons.extend(owners or [UNASSIGNED_OWNER])
    elif local_cells is None:
        reasons.append("local_cells_not_supplied")
    return tuple(reasons)


def _copied_us(card: TransferCard, local_cells: LocalCells | None) -> bool:
    if local_cells is None or card.region_id == US_REGION:
        return False
    if card.local_currency != USD and local_cells.currency == USD:
        return True
    return any(_registry_entry(c.target_id).region == US_REGION for c in local_cells.cells)


def _score_holdout(
    kind: str,
    scores: HoldoutScores,
    card: TransferCard,
    guard: WindowGuard,
) -> HoldoutResult:
    plan = card.holdout_plan
    before = guard.refused_count
    pooled = list(guard.admit(scores.pooled, fold="dev"))
    local = list(guard.admit(scores.local, fold="dev"))
    refused = guard.refused_count - before
    groups: dict[str, int] = {}
    for row in local + pooled:
        if int(row.horizon_bdays) != plan.eval_horizon_bdays:
            raise ContractError(
                f"{kind} row {row.shock_id}/{row.target_id} is not at the card's "
                f"eval horizon {plan.eval_horizon_bdays}"
            )
        if kind == "leave_country_out":
            if row.target_id not in plan.leave_country_out:
                raise ContractError(f"{kind} row target {row.target_id} is not a held-out member")
        elif plan.era_of(row.anchor_session) is None:
            raise ContractError(
                f"{kind} row {row.shock_id}/{row.target_id} is anchored outside every frozen era"
            )
    for row in local:
        group = row.target_id if kind == "leave_country_out" else plan.era_of(row.anchor_session).era_id
        groups[group] = groups.get(group, 0) + 1
    held_out = (
        plan.leave_country_out
        if kind == "leave_country_out"
        else tuple(era.era_id for era in plan.leave_era_out)
    )
    if not pooled and not local:
        n_keys, local_mse, pooled_mse = 0, None, None
    else:
        population = PairedPopulation.require({"local": local, "pooled": pooled})
        n_keys = len(population.keys)
        local_mse = mean_squared_error(local)
        pooled_mse = mean_squared_error(pooled)
    if n_keys < plan.local_floor_effective_n:
        beats, reason = False, f"too_few_paired_keys:{kind}:{n_keys}<{plan.local_floor_effective_n}"
    elif local_mse <= plan.margin * pooled_mse:
        beats, reason = True, None
    else:
        beats, reason = False, f"local_did_not_beat_pooled:{kind}"
    return HoldoutResult(
        kind=kind,
        held_out=held_out,
        n_paired_keys=n_keys,
        local_mse=local_mse,
        pooled_mse=pooled_mse,
        margin=plan.margin,
        floor=plan.local_floor_effective_n,
        local_beats_pooled=beats,
        per_group=tuple(sorted(groups.items())),
        refused_by_guard=refused,
        reason=reason,
    )


def qualify_transfer(
    card: TransferCard,
    pooled_cells: Sequence[ResponseCurveCell],
    local_cells: LocalCells | None,
    *,
    holdouts: TransferHoldouts | None,
    guard: WindowGuard,
) -> TransferResult:
    """Decide whether the pooled relationship transfers to ``card``'s region.

    The function is pure in its inputs. Only ``guard`` records its own refusals.
    One region's inputs therefore cannot change another region's result.
    """

    if not isinstance(card, TransferCard):
        raise ContractError("card must be a TransferCard")
    if not isinstance(guard, WindowGuard):
        raise ContractError("guard must be a WindowGuard")
    if card.preregistration_card_hash is None:
        raise ContractError("the transfer card was not loaded against a preregistration card")
    if guard.card_hash != card.preregistration_card_hash:
        raise ContractError("the window guard belongs to another preregistration card")
    pooled = tuple(pooled_cells or ())
    if not all(isinstance(c, ResponseCurveCell) for c in pooled):
        raise ContractError("pooled cells must be ResponseCurveCell rows")
    for cell in pooled:
        _registry_entry(cell.target_id)
    if local_cells is not None:
        if not isinstance(local_cells, LocalCells):
            raise ContractError("local_cells must be LocalCells")
        if local_cells.region_id != card.region_id:
            raise ContractError(
                f"local cells of {local_cells.region_id!r} cannot qualify {card.region_id!r}"
            )
        for cell in local_cells.cells:
            _registry_entry(cell.target_id)
    if holdouts is not None:
        if not isinstance(holdouts, TransferHoldouts):
            raise ContractError("holdouts must be TransferHoldouts")
        for scores in (holdouts.leave_country_out, holdouts.leave_era_out):
            if scores is not None:
                if not isinstance(scores, HoldoutScores):
                    raise ContractError("holdout scores must be HoldoutScores")
                for row in scores.pooled + scores.local:
                    _registry_entry(row.target_id)

    plan = card.holdout_plan
    copied = (COPIED_US_REASON,) if _copied_us(card, local_cells) else ()

    def result(status: str, reasons: Sequence[str], **numbers: Any) -> TransferResult:
        fields = {
            "pooled_vs_local": None,
            "leave_country_out": None,
            "leave_era_out": None,
            "coverage": None,
            "local_effective_n": None,
            "borrowed_prior_effective_n": None,
        }
        fields.update(numbers)
        return TransferResult(
            region_id=card.region_id,
            status=status,
            card_hash=card.card_hash,
            plan_hash=plan.plan_hash,
            reasons=tuple(reasons) + tuple(r for r in copied if r not in reasons),
            **fields,
        )

    missing = _missing_input_reasons(card, local_cells)
    if missing:
        return result("missing_input", missing)
    if local_cells is None:  # unreachable: _missing_input_reasons names it
        raise ContractError("local cells are required past the missing-input gate")
    if local_cells.currency != card.local_currency:
        return result(
            "abstain", (f"local_currency_mismatch:{local_cells.currency}!={card.local_currency}",)
        )
    if local_cells.calendar_ref != card.local_calendar_ref:
        raise CalendarMismatchError(
            f"local cells on {local_cells.calendar_ref!r} cannot join the card calendar "
            f"{card.local_calendar_ref!r}"
        )
    members = card.hierarchy_members
    if not members:
        return result("abstain", ("no_registered_hierarchy",))
    outside = sorted({c.target_id for c in local_cells.cells if c.target_id not in members})
    if outside:
        return result("abstain", tuple(f"outside_hierarchy:{t}" for t in outside))

    horizon = plan.eval_horizon_bdays
    member_pooled = tuple(c for c in pooled if c.target_id in members)
    usable_pooled = [
        c for c in member_pooled if c.horizon_bdays == horizon and c.shrunk_mean is not None
    ]
    local_at_h = [c for c in local_cells.cells if c.horizon_bdays == horizon]
    local_n = max((int(c.effective_n) for c in local_at_h), default=0)
    borrowed_n = max((int(c.prior_effective_n) for c in usable_pooled), default=None)
    covered = {c.target_id for c in local_at_h if c.shrunk_mean is not None}
    numbers: dict[str, Any] = {
        "pooled_vs_local": _pair_cells(member_pooled, local_cells.cells),
        "coverage": len(covered) / len(members),
        "local_effective_n": local_n,
        "borrowed_prior_effective_n": borrowed_n,
    }
    if local_n < plan.local_floor_effective_n:
        return result(
            "abstain", (f"local_effective_n_below_floor:{local_n}<{plan.local_floor_effective_n}",), **numbers
        )
    if holdouts is None:
        return result("abstain", tuple(f"missing_holdout:{kind}" for kind in HOLDOUT_KINDS), **numbers)
    absent = [kind for kind in HOLDOUT_KINDS if getattr(holdouts, kind) is None]
    if absent:
        return result("abstain", tuple(f"missing_holdout:{kind}" for kind in absent), **numbers)
    if holdouts.plan_hash != plan.plan_hash:
        return result("abstain", ("holdout_plan_hash_mismatch",), **numbers)

    scored = {
        kind: _score_holdout(kind, getattr(holdouts, kind), card, guard) for kind in HOLDOUT_KINDS
    }
    numbers.update(scored)
    if all(h.local_beats_pooled for h in scored.values()):
        return result("supported_local", (), **numbers)
    reasons = tuple(h.reason for h in scored.values() if h.reason)
    if usable_pooled:
        return result("pooled_only_borrowed", reasons, **numbers)
    return result("abstain", reasons + ("no_pooled_cell",), **numbers)


__all__ = [
    "CARDS_PATH",
    "COPIED_US_REASON",
    "CalendarMismatchError",
    "Era",
    "ExcludedRoleError",
    "FutureFixingError",
    "FxFixing",
    "FxFixingSeries",
    "HoldoutPlan",
    "HoldoutResult",
    "HoldoutScores",
    "LocalCells",
    "LocalPriceSeries",
    "PairedCellRow",
    "PairedComparison",
    "RegionalTransferError",
    "ReturnDecomposition",
    "STATUSES",
    "TransferCard",
    "TransferCards",
    "TransferHoldouts",
    "TransferResult",
    "decompose_returns",
    "load_transfer_cards",
    "qualify_transfer",
]
