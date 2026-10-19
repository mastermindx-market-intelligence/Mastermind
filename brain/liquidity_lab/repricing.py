"""T18 remaining-repricing projection (research substrate, measurement only).

An issued forward forecast fixes a reference path ``m0`` (the T16 response path
of the forecast's own model version) and an exit ``H``.  At an elapsed cutoff
``u`` this module reports two quantities with separate support:

* ``reference_path_discrepancy`` ``d(u) = m0(u) - a(u)``: a diagnostic about the
  path already travelled ("observed divergence from the reference path");
* ``remaining_response_estimate`` ``g(u, H) = E[log(P_H / P_u) | I_u]``: set only
  from a :class:`RemainderQualification` issued by :func:`qualify_remainder`,
  i.e. a remainder model that beat no-gap, direct-state and original-fixed
  comparators on paired out-of-sample remaining-interval loss.

``g`` is never ``m0(H) - a(u)``: :func:`project` takes no remainder argument and
:class:`RepricingProjection` refuses a remainder that does not come from a
passing, sealed qualification.  ``percent_complete`` is withheld by the ex-ante
rules in ``research/liquidity_transmission/glt_repricing_rules.v1.json``.  The
original forecast row and its exit ``H`` are immutable; an update is one
appended ledger row with its own ``known_at``.  Nothing here sizes, ranks or
recommends a position.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from brain.liquidity_lab.baselines import PairedPopulation, card_hash_prefix, mean_squared_error
from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    ContractError,
    ForwardForecast,
    _finite,
    _iso_utc,
    _snapshot_hash,
    _utc_timestamp,
    canonical_hash,
)
from brain.liquidity_lab.ledger import ForwardLedger, ShockRegistry, _now_iso
from brain.liquidity_lab.response_path import ResponsePath
from brain.liquidity_lab.target_card import BROAD_TARGET_CARD_V1
from brain.liquidity_lab.validation import WalkForwardPrediction
from brain.liquidity_lab.window_guard import WindowGuard

RULES_SCHEMA = "glt_repricing_rules.v1"
RULES_PATH = (
    Path(__file__).resolve().parents[2]
    / "research"
    / "liquidity_transmission"
    / "glt_repricing_rules.v1.json"
)
UPDATE_KIND = "forecast_repricing_update"
DISCREPANCY_LABEL = "observed divergence from the reference path"
THESIS_STATUSES = ("active", "eliminated", "expired")
REMAINING_REASONS = (
    "no_qualified_remainder",
    "no_incremental_support",
    "invalidated_by_new_information",
    "expired",
)
PERCENT_WITHHELD_REASONS = (
    "denominator_near_zero",
    "sign_uncertain",
    "not_economically_meaningful",
    "expired",
    "no_qualified_remainder",
)
_PATH_TOLERANCE = 1e-12


# --------------------------------------------------------------------- errors
class RepricingError(ContractError):
    """Base refusal for the T18 projection."""


class ExitElapsedError(RepricingError):
    """The elapsed cutoff has reached or passed the original exit H."""


class CutoffBeforeIssuanceError(RepricingError):
    """The elapsed cutoff precedes the forecast's issuance."""


class FuturePathPointError(RepricingError):
    """An observed path point lies after the elapsed cutoff."""


class MixedBasisError(RepricingError):
    """The observed path and the forecast use different return bases or currencies."""


class ModelSourceMismatchError(RepricingError):
    """The path, the observation or the qualification is bound to another model or source."""


class OriginalOverwrittenError(RepricingError):
    """The original ledger row no longer hashes to what the forecast object carries."""


class HorizonExtensionError(RepricingError):
    """An exit other than the ledger's original H was supplied."""


# ---------------------------------------------------------------------- rules
@dataclass(frozen=True, slots=True)
class RepricingRules:
    definition_hash: str
    preregistration_card_hash: str
    comparators: tuple[str, ...]
    margin: float
    min_paired_keys: int
    fold: str
    denominator_near_zero_abs: float
    not_economically_meaningful_abs: float
    reason_precedence: tuple[str, ...]
    discrepancy_label: str
    forbidden_terms: tuple[str, ...]


def load_rules(path: Path | str = RULES_PATH) -> RepricingRules:
    """Load the frozen withholding rules and verify their ``definition_hash``."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != RULES_SCHEMA:
        raise ContractError(f"expected schema {RULES_SCHEMA}")
    recorded = document.get("definition_hash")
    computed = canonical_hash({k: v for k, v in document.items() if k != "definition_hash"})
    if recorded != computed:
        raise ContractError(f"repricing rules definition_hash mismatch: {recorded!r} != {computed}")
    if document.get("validated") is not False:
        raise ContractError("the repricing rules are research rules and never validated here")
    qualification = document["qualification"]
    withholding = document["percent_withholding"]
    language = document["language"]
    precedence = tuple(withholding["reason_precedence"])
    if set(precedence) != set(PERCENT_WITHHELD_REASONS):
        raise ContractError("reason_precedence must name every withheld reason exactly once")
    if language["discrepancy_label"] != DISCREPANCY_LABEL:
        raise ContractError("the discrepancy label is fixed by the science protocol")
    return RepricingRules(
        definition_hash=computed,
        preregistration_card_hash=str(document["preregistration_card_hash"]),
        comparators=tuple(qualification["comparators"]),
        margin=_finite("margin", qualification["margin"]),
        min_paired_keys=int(qualification["min_paired_keys"]),
        fold=str(qualification["fold"]),
        denominator_near_zero_abs=_finite(
            "denominator_near_zero_abs", withholding["denominator_near_zero_abs"]
        ),
        not_economically_meaningful_abs=_finite(
            "not_economically_meaningful_abs", withholding["not_economically_meaningful_abs"]
        ),
        reason_precedence=precedence,
        discrepancy_label=str(language["discrepancy_label"]),
        forbidden_terms=tuple(language["forbidden_terms"]),
    )


def ledger_model_version(path_model_version: str) -> str:
    """Map a T16 path model_version onto the contracts identifier grammar."""

    text = str(path_model_version or "").strip().lower().replace("+", ".").replace("@", ":")
    if not text:
        raise ContractError("path model_version is empty")
    return text


# ---------------------------------------------------------- original forecast
@dataclass(frozen=True, slots=True)
class OriginalForecast:
    """An issued ledger forecast plus the facts the ledger row binds to it."""

    forecast: ForwardForecast
    payload_hash: str
    registered_at: str
    graded: bool
    return_basis: str
    currency: str
    source_snapshot_hash: str | None = None

    @property
    def forecast_id(self) -> str:
        return self.forecast.forecast_key

    @property
    def original_exit(self) -> int:
        return self.forecast.horizon_bdays


def _forecast_from_payload(payload: Mapping[str, Any]) -> ForwardForecast:
    fields = {
        name: payload[name]
        for name in (
            "shock_id",
            "target_id",
            "horizon_bdays",
            "model_version",
            "predicted_at",
            "relation_id",
            "relation_state",
            "expected_return",
            "interval_low",
            "interval_high",
            "probability_positive",
            "effective_n",
            "forecast_state",
        )
    }
    return ForwardForecast(**fields)


def load_original_forecast(
    ledger: ForwardLedger,
    forecast_id: str,
    *,
    registry: ShockRegistry | None = None,
) -> OriginalForecast:
    """Read one issued forecast without writing; refuse a rewritten or ambiguous row."""

    rows = ledger.rows()
    matches = [
        row for row in rows if row.get("kind") == "forecast" and row.get("forecast_key") == forecast_id
    ]
    if not matches:
        raise ContractError(f"unknown forecast_key: {forecast_id}")
    first = matches[0]
    payload = first.get("payload")
    if not isinstance(payload, Mapping):
        raise OriginalOverwrittenError(f"{forecast_id}: forecast row carries no payload")
    if any(row.get("payload") != payload for row in matches[1:]):
        raise OriginalOverwrittenError(f"{forecast_id}: more than one distinct forecast row")
    if canonical_hash(payload) != first.get("payload_hash"):
        raise OriginalOverwrittenError(f"{forecast_id}: payload no longer hashes to payload_hash")
    forecast = _forecast_from_payload(payload)
    if forecast.to_dict() != dict(payload):
        raise OriginalOverwrittenError(f"{forecast_id}: payload does not round-trip through ForwardForecast")
    graded = any(
        row.get("kind") == "forecast_grade" and row.get("forecast_key") == forecast_id for row in rows
    )
    entry = BROAD_TARGET_CARD_V1.entry(forecast.target_id)
    source_hash: str | None = None
    if registry is not None:
        shocks = [shock for shock in registry.shocks() if shock.get("shock_id") == forecast.shock_id]
        if len(shocks) != 1:
            raise ModelSourceMismatchError(
                f"{forecast_id}: the shock registry holds {len(shocks)} rows for {forecast.shock_id}"
            )
        source_hash = _snapshot_hash(shocks[0].get("source_snapshot_hash"))
    return OriginalForecast(
        forecast=forecast,
        payload_hash=str(first["payload_hash"]),
        registered_at=str(first.get("registered_at")),
        graded=graded,
        return_basis=entry.return_basis,
        currency=entry.quote_currency,
        source_snapshot_hash=source_hash,
    )


# ------------------------------------------------------------- observed path
@dataclass(frozen=True, slots=True)
class PathPoint:
    session: date
    elapsed_sessions: int
    cumulative_log_return: float
    known_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.session, date) or isinstance(self.session, datetime):
            raise ContractError("path point session must be a date")
        if int(self.elapsed_sessions) < 0:
            raise ContractError("elapsed_sessions may not be negative")
        object.__setattr__(self, "elapsed_sessions", int(self.elapsed_sessions))
        object.__setattr__(
            self, "cumulative_log_return", _finite("cumulative_log_return", self.cumulative_log_return)
        )
        object.__setattr__(self, "known_at", _utc_timestamp("known_at", self.known_at))


@dataclass(frozen=True, slots=True)
class ObservedPath:
    """The travelled cumulative log return of one forecast's target to the cutoff."""

    forecast_key: str
    target_id: str
    return_basis: str
    currency: str
    model_version: str
    elapsed_cutoff: datetime
    elapsed_sessions: int
    points: tuple[PathPoint, ...]
    source_snapshot_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "elapsed_cutoff", _utc_timestamp("elapsed_cutoff", self.elapsed_cutoff))
        if int(self.elapsed_sessions) < 1:
            raise ContractError("elapsed_sessions must be at least one session")
        object.__setattr__(self, "elapsed_sessions", int(self.elapsed_sessions))
        points = tuple(self.points)
        if not points:
            raise ContractError("an observed path needs at least one point")
        ordered = sorted(points, key=lambda point: point.elapsed_sessions)
        for left, right in zip(ordered, ordered[1:]):
            if right.elapsed_sessions == left.elapsed_sessions or right.session <= left.session:
                raise ContractError("observed path points must be strictly increasing")
        object.__setattr__(self, "points", tuple(ordered))
        if self.source_snapshot_hash is not None:
            object.__setattr__(self, "source_snapshot_hash", _snapshot_hash(self.source_snapshot_hash))


def _travelled(observed: ObservedPath) -> PathPoint:
    """Return the point at the cutoff; refuse any point beyond it."""

    cutoff_day = observed.elapsed_cutoff.date()
    late = [
        point
        for point in observed.points
        if point.elapsed_sessions > observed.elapsed_sessions
        or point.known_at > observed.elapsed_cutoff
        or point.session > cutoff_day
    ]
    if late:
        raise FuturePathPointError(
            f"{len(late)} observed point(s) lie after the elapsed cutoff "
            f"{_iso_utc(observed.elapsed_cutoff)} (u={observed.elapsed_sessions})"
        )
    at_cutoff = [point for point in observed.points if point.elapsed_sessions == observed.elapsed_sessions]
    if not at_cutoff:
        raise ContractError(f"no observed point at the cutoff session u={observed.elapsed_sessions}")
    return at_cutoff[0]


def reference_value(path: ResponsePath, elapsed_sessions: int) -> float:
    """``m0(h)``: linear in sessions between grid horizons with ``m0(0) = 0``."""

    h = int(elapsed_sessions)
    if h < 0:
        raise ContractError("a reference read needs a non-negative session count")
    if h == 0:
        return 0.0
    grid = sorted(zip(path.horizons, path.points))
    if not grid or h > grid[-1][0]:
        raise ContractError(f"reference read at {h} lies beyond the path grid")
    lower_h, lower_v = 0, 0.0
    for grid_h, grid_v in grid:
        if grid_h >= h:
            if grid_v is None or lower_v is None:
                raise ContractError(f"reference read at {h} crosses a missing grid cell")
            if grid_h == h:
                return float(grid_v)
            weight = (h - lower_h) / (grid_h - lower_h)
            return float(lower_v + weight * (grid_v - lower_v))
        lower_h, lower_v = grid_h, grid_v
    raise ContractError(f"reference read at {h} lies beyond the path grid")


def reference_path_discrepancy(path: ResponsePath, observed: ObservedPath) -> float:
    """``d(u) = m0(u) - a(u)``: observed divergence from the reference path (diagnostic)."""

    point = _travelled(observed)
    return reference_value(path, observed.elapsed_sessions) - point.cumulative_log_return


# -------------------------------------------------------- remainder evidence
@dataclass(frozen=True, slots=True)
class RemainingInterval:
    """One historical remaining interval ``(u, H]`` with its realised remainder."""

    shock_id: str
    target_id: str
    horizon_bdays: int
    elapsed_sessions: int
    anchor_session: date
    exit_session: date
    travelled_return: float
    realized_remaining: float
    split_index: int

    def __post_init__(self) -> None:
        if self.horizon_bdays not in HORIZONS_BDAYS:
            raise ContractError("horizon_bdays is not precommitted")
        if not 1 <= int(self.elapsed_sessions) < int(self.horizon_bdays):
            raise ContractError("a remaining interval needs 1 <= u < H")
        if self.exit_session <= self.anchor_session:
            raise ContractError("a remaining interval exits after its anchor")
        object.__setattr__(self, "travelled_return", _finite("travelled_return", self.travelled_return))
        object.__setattr__(
            self, "realized_remaining", _finite("realized_remaining", self.realized_remaining)
        )


def _panel_row(row: RemainingInterval, *, model_version: str, predicted: float) -> WalkForwardPrediction:
    return WalkForwardPrediction(
        split_index=row.split_index,
        relation_id="glt_t18_remainder",
        model_version=model_version,
        shock_id=row.shock_id,
        target_id=row.target_id,
        horizon_bdays=row.horizon_bdays,
        anchor_session=row.anchor_session,
        exit_session=row.exit_session,
        predicted_return=float(predicted),
        realized_return=row.realized_remaining,
        effective_n_at_fit=0,
    )


class NoGapComparator:
    """``g = 0`` for every remaining interval."""

    name = "no_gap"
    model_version = "glt_t18_no_gap.v1"

    def predictions(self, panel: Sequence[RemainingInterval]) -> tuple[WalkForwardPrediction, ...]:
        return tuple(_panel_row(row, model_version=self.model_version, predicted=0.0) for row in panel)


class OriginalFixedResponse:
    """``g = m0(H) - m0(u)`` read from the T16 reference path of the row's target."""

    name = "original_fixed"

    def __init__(self, paths: Mapping[str, ResponsePath]) -> None:
        if not paths:
            raise ContractError("original_fixed needs a reference path per target")
        versions = {path.model_version for path in paths.values()}
        if len(versions) != 1:
            raise ContractError("original_fixed paths must share one model_version")
        for target_id, path in paths.items():
            if path.target_id != target_id:
                raise ContractError(f"original_fixed path for {target_id} is bound to {path.target_id}")
        self.paths = dict(paths)
        self.model_version = f"glt_t18_original_fixed.v1/{next(iter(versions))}"

    def predictions(self, panel: Sequence[RemainingInterval]) -> tuple[WalkForwardPrediction, ...]:
        rows = []
        for row in panel:
            path = self.paths.get(row.target_id)
            if path is None:
                raise ContractError(f"original_fixed has no reference path for {row.target_id}")
            predicted = reference_value(path, row.horizon_bdays) - reference_value(path, row.elapsed_sessions)
            rows.append(_panel_row(row, model_version=self.model_version, predicted=predicted))
        return tuple(rows)


class DirectStateBaseline:
    """The T15 direct-observable rung refit at ``u`` on remaining-interval outcomes."""

    name = "direct_state"
    _PREFIXES = ("glt_t15_component.v1", "glt_t15_direct_funding.v1")

    def __init__(
        self,
        model_version: str,
        predictions: Sequence[WalkForwardPrediction],
        *,
        card_hash: str,
    ) -> None:
        suffix = f"@{card_hash_prefix(card_hash)}"
        if not (str(model_version).startswith(self._PREFIXES) and str(model_version).endswith(suffix)):
            raise ContractError(
                f"direct_state must be a T15 direct-observable rung at {suffix}; got {model_version!r}"
            )
        if any(row.model_version != model_version for row in predictions):
            raise ContractError("direct_state rows carry another model_version")
        self.model_version = str(model_version)
        self.card_hash = card_hash
        self._rows = tuple(predictions)

    def predictions(self, panel: Sequence[RemainingInterval]) -> tuple[WalkForwardPrediction, ...]:
        wanted = {(row.shock_id, row.target_id, row.horizon_bdays) for row in panel}
        return tuple(
            row for row in self._rows if (row.shock_id, row.target_id, row.horizon_bdays) in wanted
        )


@dataclass(frozen=True, slots=True)
class RemainderCandidate:
    """A remainder model: walk-forward remaining-interval rows plus its live estimate."""

    model_version: str
    predictions: tuple[WalkForwardPrediction, ...]
    live_forecast_key: str
    live_elapsed_sessions: int
    live_horizon_bdays: int
    live_estimate: float
    live_interval_low: float
    live_interval_high: float
    live_known_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "predictions", tuple(self.predictions))
        if any(row.model_version != self.model_version for row in self.predictions):
            raise ContractError("candidate rows carry another model_version")
        for name in ("live_estimate", "live_interval_low", "live_interval_high"):
            object.__setattr__(self, name, _finite(name, getattr(self, name)))
        if not self.live_interval_low <= self.live_estimate <= self.live_interval_high:
            raise ContractError("the live remaining interval must contain the live estimate")
        object.__setattr__(self, "live_known_at", _utc_timestamp("live_known_at", self.live_known_at))


# A passing qualification carries an HMAC over its own fields under a key that
# exists only inside this process, so it can be issued by qualify_remainder()
# and cannot be forged by construction or by dataclasses.replace().
_SEAL_KEY = secrets.token_bytes(32)
_SEALED_FIELDS = (
    "passed",
    "model_version",
    "horizon_bdays",
    "elapsed_sessions",
    "live_forecast_key",
    "n_paired_keys",
    "paired_keys_hash",
    "candidate_mse",
    "comparator_mse",
    "margin",
    "rules_hash",
    "live_estimate",
    "live_interval_low",
    "live_interval_high",
    "live_known_at",
)


def _seal_digest(values: Mapping[str, Any]) -> str:
    material = {}
    for name in _SEALED_FIELDS:
        value = values.get(name)
        if isinstance(value, datetime):
            value = _iso_utc(value)
        elif name == "comparator_mse" and value is not None:
            value = [list(pair) for pair in value]
        material[name] = value
    message = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(_SEAL_KEY, message, hashlib.sha256).hexdigest()


def _sealed(qualification: "RemainderQualification") -> bool:
    expected = _seal_digest({name: getattr(qualification, name) for name in _SEALED_FIELDS})
    return isinstance(qualification._seal, str) and hmac.compare_digest(qualification._seal, expected)


@dataclass(frozen=True, slots=True)
class RemainderQualification:
    """Outcome of :func:`qualify_remainder`; a passing one is issued only there."""

    passed: bool
    reason: str | None
    detail: str
    model_version: str
    horizon_bdays: int
    elapsed_sessions: int
    live_forecast_key: str
    n_paired_keys: int
    paired_keys_hash: str | None
    candidate_mse: float | None
    comparator_mse: tuple[tuple[str, float | None], ...]
    margin: float
    rules_hash: str
    guard_receipt: Mapping[str, Any] = field(compare=False)
    live_estimate: float | None = None
    live_interval_low: float | None = None
    live_interval_high: float | None = None
    live_known_at: datetime | None = None
    _seal: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.passed:
            if not _sealed(self):
                raise ContractError("a passing RemainderQualification is issued only by qualify_remainder")
            if self.reason is not None or self.live_estimate is None:
                raise ContractError("a passing qualification carries a live estimate and no reason")
        else:
            if self.reason != "no_incremental_support":
                raise ContractError("a failed qualification carries reason no_incremental_support")
            if self.live_estimate is not None:
                raise ContractError("a failed qualification may not carry a live estimate")


def qualify_remainder(
    candidate: RemainderCandidate,
    comparators: Sequence[Any],
    panel: Sequence[RemainingInterval],
    guard: WindowGuard,
    *,
    rules: RepricingRules | None = None,
) -> RemainderQualification:
    """Qualify a remainder model on paired out-of-sample remaining-interval loss.

    Every member is admitted through ``guard`` on the rules' fold, then
    :meth:`PairedPopulation.require` refuses asymmetric keys.  The candidate
    passes only when its MSE is within ``margin`` of EVERY comparator.
    """

    rules = rules or load_rules()
    if guard.card_hash != rules.preregistration_card_hash:
        raise ContractError("the window guard is built from another preregistration card")
    names = [getattr(comparator, "name", None) for comparator in comparators]
    if sorted(names) != sorted(rules.comparators) or len(set(names)) != len(names):
        raise ContractError(f"comparators must be exactly {rules.comparators}; got {names}")
    panel = tuple(panel)
    horizons = {row.horizon_bdays for row in panel}
    elapsed = {row.elapsed_sessions for row in panel}
    if horizons != {candidate.live_horizon_bdays} or elapsed != {candidate.live_elapsed_sessions}:
        raise HorizonExtensionError(
            "the remaining-interval panel must share the live forecast's H and u"
        )
    admitted_panel = guard.admit(panel, fold=rules.fold)
    members: dict[str, Sequence[WalkForwardPrediction]] = {
        "candidate": guard.admit(candidate.predictions, fold=rules.fold)
    }
    for comparator in sorted(comparators, key=lambda item: rules.comparators.index(item.name)):
        rows = comparator.predictions(admitted_panel)
        members[comparator.name] = guard.admit(rows, fold=rules.fold)
    # The candidate is the reference member: every comparator is built from the
    # admitted panel, so require() also binds the candidate's realized values to
    # the panel's realized remaining-interval returns.
    population = PairedPopulation.require(members)
    n_paired = len(population.keys)
    candidate_mse = mean_squared_error(members["candidate"])
    comparator_mse = tuple((name, mean_squared_error(members[name])) for name in rules.comparators)
    base = dict(
        model_version=candidate.model_version,
        horizon_bdays=candidate.live_horizon_bdays,
        elapsed_sessions=candidate.live_elapsed_sessions,
        live_forecast_key=candidate.live_forecast_key,
        n_paired_keys=n_paired,
        paired_keys_hash=canonical_hash({"keys": [list(key) for key in population.keys]}),
        candidate_mse=candidate_mse,
        comparator_mse=comparator_mse,
        margin=rules.margin,
        rules_hash=rules.definition_hash,
        guard_receipt=guard.receipt(),
    )
    if n_paired < rules.min_paired_keys:
        return RemainderQualification(
            passed=False,
            reason="no_incremental_support",
            detail=f"paired keys {n_paired} < min_paired_keys {rules.min_paired_keys}",
            **base,
        )
    losers = [
        name
        for name, mse in comparator_mse
        if candidate_mse is None or mse is None or candidate_mse > rules.margin * mse
    ]
    if losers:
        return RemainderQualification(
            passed=False,
            reason="no_incremental_support",
            detail=f"candidate is not within margin {rules.margin} of: {', '.join(losers)}",
            **base,
        )
    sealed = dict(
        base,
        passed=True,
        live_estimate=candidate.live_estimate,
        live_interval_low=candidate.live_interval_low,
        live_interval_high=candidate.live_interval_high,
        live_known_at=candidate.live_known_at,
    )
    return RemainderQualification(
        reason=None,
        detail=f"candidate beat {', '.join(rules.comparators)} on {n_paired} paired keys",
        _seal=_seal_digest(sealed),
        **sealed,
    )


# ----------------------------------------------------------------- projection
@dataclass(frozen=True, slots=True)
class RepricingProjection:
    """Discrepancy and remainder as separate fields; the original exit is immutable."""

    forecast_id: str
    issued_at: datetime
    original_exit: int
    elapsed_cutoff: datetime
    elapsed_sessions: int
    target_id: str
    return_basis: str
    currency: str
    original_model_version: str
    remainder_model_version: str | None
    original_payload_hash: str
    rules_hash: str
    reference_path_discrepancy: float
    discrepancy_label: str
    travelled_return: float
    remaining_response_estimate: float | None
    remaining_interval: tuple[float, float] | None
    remaining_interval_kind: str | None
    remaining_reason: str | None
    percent_complete: float | None
    percent_withheld_reason: str | None
    thesis_status: str
    invalidating_information: tuple[str, ...]
    known_at: datetime
    qualification: RemainderQualification | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.thesis_status not in THESIS_STATUSES:
            raise ContractError("thesis_status is not in the closed vocabulary")
        if self.original_exit not in HORIZONS_BDAYS:
            raise ContractError("original_exit is not precommitted")
        if self.discrepancy_label != DISCREPANCY_LABEL:
            raise ContractError("the discrepancy label is fixed")
        _finite("reference_path_discrepancy", self.reference_path_discrepancy)
        object.__setattr__(self, "invalidating_information", tuple(self.invalidating_information))
        if self.remaining_response_estimate is not None:
            qual = self.qualification
            if (
                qual is None
                or not qual.passed
                or not _sealed(qual)
                or qual.live_estimate != self.remaining_response_estimate
                or qual.horizon_bdays != self.original_exit
                or qual.elapsed_sessions != self.elapsed_sessions
                or qual.live_forecast_key != self.forecast_id
            ):
                raise ContractError(
                    "a remaining estimate needs a passing qualification for this forecast, H and u"
                )
            if self.remaining_reason is not None or self.thesis_status != "active":
                raise ContractError("a supported remainder belongs to an active thesis without a reason")
            if self.remaining_interval is None or self.remaining_interval_kind != "pointwise":
                raise ContractError("a supported remainder carries its pointwise interval")
        else:
            if self.remaining_reason not in REMAINING_REASONS:
                raise ContractError("a withheld remainder needs a closed reason")
            if self.remaining_interval is not None:
                raise ContractError("a withheld remainder carries no interval")
        if self.percent_complete is not None:
            if self.remaining_response_estimate is None or self.percent_withheld_reason is not None:
                raise ContractError("percent_complete needs a supported remainder and no withheld reason")
        elif self.percent_withheld_reason not in PERCENT_WITHHELD_REASONS:
            raise ContractError("a withheld percent needs a closed reason")
        if self.thesis_status == "eliminated" and (
            not self.invalidating_information
            or self.remaining_reason != "invalidated_by_new_information"
        ):
            raise ContractError("an eliminated thesis names its invalidating information")
        if self.thesis_status == "expired" and self.remaining_reason != "expired":
            raise ContractError("an expired thesis withholds the remainder as expired")

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": "glt_repricing_projection.v1",
            "forecast_id": self.forecast_id,
            "issued_at": _iso_utc(self.issued_at),
            "original_exit": self.original_exit,
            "elapsed_cutoff": _iso_utc(self.elapsed_cutoff),
            "elapsed_sessions": self.elapsed_sessions,
            "target_id": self.target_id,
            "return_basis": self.return_basis,
            "currency": self.currency,
            "original_model_version": self.original_model_version,
            "remainder_model_version": self.remainder_model_version,
            "original_payload_hash": self.original_payload_hash,
            "rules_hash": self.rules_hash,
            "reference_path_discrepancy": self.reference_path_discrepancy,
            "discrepancy_label": self.discrepancy_label,
            "travelled_return": self.travelled_return,
            "remaining_response_estimate": self.remaining_response_estimate,
            "remaining_interval": None
            if self.remaining_interval is None
            else list(self.remaining_interval),
            "remaining_interval_kind": self.remaining_interval_kind,
            "remaining_reason": self.remaining_reason,
            "percent_complete": self.percent_complete,
            "percent_withheld_reason": self.percent_withheld_reason,
            "thesis_status": self.thesis_status,
            "invalidating_information": list(self.invalidating_information),
            "known_at": _iso_utc(self.known_at),
            "qualification_paired_keys_hash": None
            if self.qualification is None
            else self.qualification.paired_keys_hash,
        }


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _percent(
    travelled: float,
    remaining: float,
    interval: tuple[float, float],
    reference_exit: float,
    rules: RepricingRules,
) -> tuple[float | None, str | None]:
    total = travelled + remaining
    reasons: list[str] = []
    if abs(reference_exit) < rules.denominator_near_zero_abs or abs(total) < rules.denominator_near_zero_abs:
        reasons.append("denominator_near_zero")
    if (
        interval[0] <= 0.0 <= interval[1]
        or _sign(reference_exit) != _sign(remaining)
        or _sign(total) != _sign(reference_exit)
    ):
        reasons.append("sign_uncertain")
    ratio = None if "denominator_near_zero" in reasons else travelled / total
    if abs(remaining) < rules.not_economically_meaningful_abs or (ratio is not None and ratio < 0):
        reasons.append("not_economically_meaningful")
    if reasons:
        first = min(reasons, key=rules.reason_precedence.index)
        return None, first
    return ratio, None


def project(
    original: OriginalForecast,
    observed: ObservedPath,
    qualification: RemainderQualification | None,
    *,
    as_of: datetime,
    reference_path: ResponsePath,
    invalidating_information: Sequence[str] = (),
    original_exit: int | None = None,
    rules: RepricingRules | None = None,
) -> RepricingProjection:
    """Project the remaining repricing of one issued forecast at its elapsed cutoff.

    There is deliberately no remainder argument: ``g(u, H)`` comes only from a
    passing ``qualification``; ``m0(H) - a(u)`` is never a remainder.
    """

    rules = rules or load_rules()
    forecast = original.forecast
    if canonical_hash(forecast.to_dict()) != original.payload_hash:
        raise OriginalOverwrittenError(
            f"{original.forecast_id}: the forecast object no longer hashes to the ledger row"
        )
    exit_h = forecast.horizon_bdays
    if original_exit is not None and int(original_exit) != exit_h:
        raise HorizonExtensionError(f"original exit is {exit_h}; {original_exit} is not that exit")
    if qualification is not None and qualification.horizon_bdays != exit_h:
        raise HorizonExtensionError(
            f"qualification is for H={qualification.horizon_bdays}; the original exit is {exit_h}"
        )
    if observed.return_basis != original.return_basis or observed.currency != original.currency:
        raise MixedBasisError(
            f"observed {observed.return_basis}/{observed.currency} vs forecast "
            f"{original.return_basis}/{original.currency}"
        )
    if (
        observed.forecast_key != forecast.forecast_key
        or observed.target_id != forecast.target_id
        or observed.model_version != forecast.model_version
        or reference_path.target_id != forecast.target_id
        or ledger_model_version(reference_path.model_version) != forecast.model_version
    ):
        raise ModelSourceMismatchError("the path or the observation is bound to another forecast or model")
    if (observed.source_snapshot_hash is None) != (original.source_snapshot_hash is None) or (
        observed.source_snapshot_hash != original.source_snapshot_hash
    ):
        raise ModelSourceMismatchError("the observation is bound to another source snapshot")
    if forecast.expected_return is None:
        raise ContractError("an insufficient forecast has no reference path to reprice")
    reference_exit = reference_value(reference_path, exit_h)
    if abs(reference_exit - forecast.expected_return) > _PATH_TOLERANCE:
        raise ModelSourceMismatchError("m0(H) from the path is not the forecast's expected_return")
    if observed.elapsed_cutoff < forecast.predicted_at:
        raise CutoffBeforeIssuanceError("the elapsed cutoff precedes the forecast's issuance")
    known_at = _utc_timestamp("as_of", as_of)
    if known_at < observed.elapsed_cutoff:
        raise ContractError("as_of may not precede the elapsed cutoff")
    u = observed.elapsed_sessions
    if not original.graded and u >= exit_h:
        raise ExitElapsedError(f"u={u} has reached the original exit H={exit_h}")
    point = _travelled(observed)
    discrepancy = reference_value(reference_path, u) - point.cumulative_log_return
    invalidating = tuple(str(item) for item in invalidating_information if str(item).strip())
    common = dict(
        forecast_id=forecast.forecast_key,
        issued_at=forecast.predicted_at,
        original_exit=exit_h,
        elapsed_cutoff=observed.elapsed_cutoff,
        elapsed_sessions=u,
        target_id=forecast.target_id,
        return_basis=original.return_basis,
        currency=original.currency,
        original_model_version=forecast.model_version,
        original_payload_hash=original.payload_hash,
        rules_hash=rules.definition_hash,
        reference_path_discrepancy=discrepancy,
        discrepancy_label=DISCREPANCY_LABEL,
        travelled_return=point.cumulative_log_return,
        invalidating_information=invalidating,
        known_at=known_at,
    )
    withheld = dict(remaining_response_estimate=None, remaining_interval=None, remaining_interval_kind=None)
    if original.graded:
        return RepricingProjection(
            remainder_model_version=None,
            remaining_reason="expired",
            percent_complete=None,
            percent_withheld_reason="expired",
            thesis_status="expired",
            **withheld,
            **common,
        )
    if invalidating:
        return RepricingProjection(
            remainder_model_version=None,
            remaining_reason="invalidated_by_new_information",
            percent_complete=None,
            percent_withheld_reason="no_qualified_remainder",
            thesis_status="eliminated",
            **withheld,
            **common,
        )
    if qualification is None or not qualification.passed:
        return RepricingProjection(
            remainder_model_version=None,
            remaining_reason="no_qualified_remainder" if qualification is None else "no_incremental_support",
            percent_complete=None,
            percent_withheld_reason="no_qualified_remainder",
            thesis_status="active",
            qualification=qualification,
            **withheld,
            **common,
        )
    if (
        qualification.live_forecast_key != forecast.forecast_key
        or qualification.elapsed_sessions != u
        or qualification.rules_hash != rules.definition_hash
        or qualification.live_known_at is None
        or qualification.live_known_at > known_at
    ):
        raise ModelSourceMismatchError("the qualification is bound to another forecast, cutoff or rule set")
    interval = (float(qualification.live_interval_low), float(qualification.live_interval_high))
    remaining = float(qualification.live_estimate)
    percent, reason = _percent(point.cumulative_log_return, remaining, interval, reference_exit, rules)
    return RepricingProjection(
        remainder_model_version=qualification.model_version,
        remaining_response_estimate=remaining,
        remaining_interval=interval,
        remaining_interval_kind="pointwise",
        remaining_reason=None,
        percent_complete=percent,
        percent_withheld_reason=reason,
        thesis_status="active",
        qualification=qualification,
        **common,
    )


# --------------------------------------------------------------- ledger append
def append_projection(ledger: ForwardLedger, projection: RepricingProjection) -> str:
    """Append ONE ``forecast_repricing_update`` row; the original row is never rewritten.

    ``ForwardLedger`` has no public forecast amendment method, so the row is
    appended under the ledger's own exclusive lock and fsync'd append.
    """

    payload = projection.to_payload()
    payload_hash = canonical_hash(payload)
    update_id = "rpu_" + payload_hash[:20]
    with ledger._locked() as (handle, rows):
        originals = [
            row
            for row in rows
            if row.get("kind") == "forecast" and row.get("forecast_key") == projection.forecast_id
        ]
        if not originals:
            raise ContractError(f"cannot reprice unknown forecast_key: {projection.forecast_id}")
        original = originals[0]
        if (
            canonical_hash(original.get("payload") or {}) != original.get("payload_hash")
            or original.get("payload_hash") != projection.original_payload_hash
        ):
            raise OriginalOverwrittenError(f"{projection.forecast_id}: the original row has changed")
        predicted_at = _utc_timestamp("predicted_at", (original.get("payload") or {}).get("predicted_at"))
        if projection.known_at < predicted_at:
            raise ContractError("a repricing update may not be known before the forecast was issued")
        if any(row.get("kind") == UPDATE_KIND and row.get("update_id") == update_id for row in rows):
            return "duplicate"
        ledger._append(
            handle,
            {
                "kind": UPDATE_KIND,
                "forecast_key": projection.forecast_id,
                "update_id": update_id,
                "registered_at": _now_iso(),
                "known_at": _iso_utc(projection.known_at),
                "payload_hash": payload_hash,
                "payload": payload,
            },
        )
    return "created"


def repricing_updates(ledger: ForwardLedger, forecast_id: str | None = None) -> list[dict[str, Any]]:
    rows = [row for row in ledger.rows() if row.get("kind") == UPDATE_KIND]
    if forecast_id is not None:
        rows = [row for row in rows if row.get("forecast_key") == forecast_id]
    return [row["payload"] for row in rows]


__all__ = [
    "CutoffBeforeIssuanceError",
    "DISCREPANCY_LABEL",
    "DirectStateBaseline",
    "ExitElapsedError",
    "FuturePathPointError",
    "HorizonExtensionError",
    "MixedBasisError",
    "ModelSourceMismatchError",
    "NoGapComparator",
    "ObservedPath",
    "OriginalFixedResponse",
    "OriginalForecast",
    "OriginalOverwrittenError",
    "PathPoint",
    "RemainderCandidate",
    "RemainderQualification",
    "RemainingInterval",
    "RepricingError",
    "RepricingProjection",
    "RepricingRules",
    "append_projection",
    "ledger_model_version",
    "load_original_forecast",
    "load_rules",
    "project",
    "qualify_remainder",
    "reference_path_discrepancy",
    "reference_value",
    "repricing_updates",
]
