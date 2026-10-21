"""GLT T15 same-information baselines, paired population and train-only transforms.

Every baseline implements the existing ``ResponseCurveEstimator`` Protocol
(``model_version`` + ``fit(observations, *, condition_keys)``) so it is scored by
``run_walk_forward_curves`` and ``score_incremental_predictions`` on the SAME
``WalkForwardPlan`` as the candidate: identical eligible observations by
construction (C27).  A baseline's information set is its declared
``condition_keys``; ``fit`` refuses any other keys, so a comparator can never be
handed information it did not declare.

Conditioning values are origin-known covariates the harness writes into
``ForwardReturnObservation.conditions`` (known_at <= first_detected).  This
module reads no prices, no files and no outcomes beyond the rows it is given; it
never records a look and never touches the ``ForwardLedger`` custodian.

Card mapping (T14 card ``baselines``; SCIENCE_PROTOCOL section 6 rungs):

* ``PooledMeanBaseline``      -- unconditional training mean (B1 rung, event rows).
* ``PersistenceBaseline``     -- persistence / no-change (component-outlook rung).
* ``AnnouncedOnlyBaseline``   -- announced-path only; abstains when the card
  registers no announced-path series (never a stand-in).
* ``ComponentBaseline``       -- the composite's components as direct inputs
  (card B4 information set).
* ``DirectFundingBaseline``   -- dollar and real yield directly; the C26 comparator.
* ``PriceMomentumBaseline``   -- target return / volatility / trend context (B3).
* ``NoGapBaseline``           -- zero-increment comparator (T18 consumes it later).

The card's B3/B4/B5 are OLS forms.  A row-level regression cannot be scored by
the existing cell-keyed runner without editing ``validation.py``, so T15 fits
them as partition means over origin-known sign/bucket keys; the deviation is
declared in the T15/T16 evidence note.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

import numpy as np

from brain.liquidity_lab.contracts import HORIZONS_BDAYS, ContractError
from brain.liquidity_lab.estimator import (
    ForwardReturnObservation,
    ResponseCurveCell,
    ResponseCurveEstimator,
    _sample_values,
    condition_bucket,
)
from brain.liquidity_lab.preregistration import canonical_json, card_hash
from brain.liquidity_lab.validation import (
    StatisticalDependencyUnavailable,
    WalkForwardPlan,
    WalkForwardPrediction,
    WalkForwardSplit,
    run_walk_forward_curves,
    score_incremental_predictions,
)

DEFAULT_LTIFO_PATH = "research/liquidity_transmission/glt_ltifo_sensitivity.v1.json"
LTIFO_VERSION = "glt_ltifo_sensitivity.v1"
OPEN_RIGHTS = frozenset({"OPEN", "LICENSED"})

#: Origin-known 4-week-change sign key for each card direct input (card B4 sources).
DIRECT_INPUT_KEYS: Mapping[str, str] = {
    "fed_total_assets": "fed_total_assets.d4w_sign",
    "ecb_total_assets": "ecb_total_assets.d4w_sign",
    "boj_total_assets": "boj_total_assets.d4w_sign",
    "dtwexbgs": "dtwexbgs.d4w_sign",
    "dfii10": "dfii10.d4w_sign",
}
COMPONENT_SOURCES = (
    "fed_total_assets",
    "ecb_total_assets",
    "boj_total_assets",
    "dtwexbgs",
    "dfii10",
)
#: Funding inputs of the composite present in the card's B4 (HY OAS is UNPROVEN
#: and outside B4, so it never enters a v1 comparator).
DIRECT_FUNDING_SOURCES = ("dtwexbgs", "dfii10")

TARGET_RET20_SIGN = "target.ret20_sign"
TARGET_VOL60 = "target.vol60"
TARGET_VOL60_TERCILE = "target.vol60_tercile"
TARGET_ABOVE_MA200 = "target.above_ma200"
PRICE_CONTEXT_KEYS = (TARGET_RET20_SIGN, TARGET_VOL60_TERCILE, TARGET_ABOVE_MA200)

ANNOUNCED_SOURCE_MARKERS = ("announced", "forward_guidance", "path_announcement")
ANNOUNCED_ABSTENTION = (
    "no announced-path series is registered in the preregistration card "
    "(sources[] carries no announced/forward-guidance path); the announced-only "
    "rung abstains and no stand-in series is substituted"
)

PredictionKey = tuple[str, str, int]


class PopulationMismatch(ContractError):
    """Candidate and comparator predictions are not on identical keys (C27)."""

    def __init__(self, asymmetric: Mapping[str, Mapping[str, tuple[PredictionKey, ...]]]):
        self.asymmetric = {
            name: {side: tuple(keys) for side, keys in sides.items()}
            for name, sides in asymmetric.items()
        }
        parts = []
        for name, sides in self.asymmetric.items():
            for side, keys in sides.items():
                if keys:
                    parts.append(f"{name}.{side}={list(keys)}")
        super().__init__("paired population mismatch: " + "; ".join(parts))


class LeakedFitError(ContractError):
    """A train-only transform was fitted with a row outside its fold's training set (C17)."""


def card_hash_prefix(card_hash_value: str) -> str:
    if not isinstance(card_hash_value, str) or len(card_hash_value) < 8:
        raise ContractError("a full card hash is required for a baseline model_version")
    return card_hash_value[:8]


def _version(slug: str, card_hash_value: str, suffix: str = "") -> str:
    return f"glt_t15_{slug}.v1{suffix}@{card_hash_prefix(card_hash_value)}"


def _card_mapping(card: Any) -> Mapping[str, Any]:
    payload = getattr(card, "payload", None)
    if payload is not None:
        return payload
    if isinstance(card, Mapping):
        return card
    raise TypeError("expected a PreregistrationCard or a card mapping")


def _verified_card_hash(card: Any) -> str:
    mapping = _card_mapping(card)
    computed = card_hash(mapping)
    if mapping.get("card_hash") != computed:
        raise ContractError("card_hash does not recompute; refusing to build baselines")
    return computed


def _card_min_effective_n(card: Any) -> int:
    models = _card_mapping(card).get("models") or []
    for model in models:
        value = (model.get("hyperparameters") or {}).get("min_effective_n")
        if isinstance(value, int):
            return value
    raise ContractError("card declares no min_effective_n")


# --------------------------------------------------------------------------- cells
class _CellBaseline:
    """Shared cell machinery: one cell per (target, family, bucket) x every horizon."""

    slug = "baseline"
    rung = ""
    card_baseline = ""
    transform_factories: tuple[Callable[[WalkForwardSplit], "TrainOnlyTransform"], ...] = ()

    def __init__(
        self,
        *,
        card_hash: str,
        condition_keys: Sequence[str] = (),
        min_effective_n: int = 2,
        version_suffix: str = "",
    ) -> None:
        if min_effective_n < 1:
            raise ContractError("min_effective_n must be positive")
        self.card_hash = card_hash
        self.condition_keys: tuple[str, ...] = tuple(condition_keys)
        self.min_effective_n = int(min_effective_n)
        self.model_version = _version(self.slug, card_hash, version_suffix)

    @property
    def information_set(self) -> tuple[str, ...]:
        return self.condition_keys

    def _check_keys(self, condition_keys: Sequence[str]) -> None:
        if tuple(condition_keys) != self.condition_keys:
            raise ContractError(
                f"{type(self).__name__} declares condition_keys {self.condition_keys}; "
                f"refusing undeclared information {tuple(condition_keys)}"
            )

    def _estimate(
        self, rows: Sequence[ForwardReturnObservation]
    ) -> tuple[float | None, int, float | None, float | None, str]:
        raise NotImplementedError

    def fit(
        self,
        observations: Sequence[ForwardReturnObservation],
        *,
        condition_keys: Sequence[str] = (),
    ) -> list[ResponseCurveCell]:
        self._check_keys(condition_keys)
        groups: dict[tuple[str, str, str, int], list[ForwardReturnObservation]] = {}
        axes: set[tuple[str, str, str]] = set()
        for row in observations:
            if row.horizon_bdays not in HORIZONS_BDAYS:
                raise ContractError("observation horizon is not precommitted")
            key = (
                row.target_id,
                row.shock_family,
                condition_bucket(row, self.condition_keys),
                row.horizon_bdays,
            )
            groups.setdefault(key, []).append(row)
            axes.add(key[:3])
        cells: list[ResponseCurveCell] = []
        for target_id, shock_family, bucket in sorted(axes):
            for horizon in HORIZONS_BDAYS:
                rows = groups.get((target_id, shock_family, bucket, horizon), [])
                estimate, effective_n, low, high, state = self._estimate(rows)
                cells.append(
                    ResponseCurveCell(
                        target_id=target_id,
                        shock_family=shock_family,
                        condition_bucket=bucket,
                        horizon_bdays=horizon,
                        sample_n=len(rows),
                        effective_n=effective_n,
                        raw_mean=estimate,
                        shrunk_mean=estimate,
                        interval_low=low,
                        interval_high=high,
                        prior_mean=None,
                        prior_effective_n=0,
                        evidence_state=state,
                    )
                )
        return cells


class _MeanCellBaseline(_CellBaseline):
    """Unshrunk partition mean with the incumbent's honest effective N."""

    def _estimate(self, rows):
        values, effective_n = _sample_values(rows)
        if effective_n < self.min_effective_n:
            return None, effective_n, None, None, "insufficient"
        mean = float(values.mean())
        if len(values) >= 2:
            se = float(values.std(ddof=1) / math.sqrt(len(values)))
            return mean, effective_n, mean - 1.96 * se, mean + 1.96 * se, "discovered"
        return mean, effective_n, None, None, "discovered"


class PooledMeanBaseline(_MeanCellBaseline):
    """Unconditional training mean: no keys, no hierarchy, no shrinkage."""

    slug = "pooled_mean"
    rung = "unconditional"
    card_baseline = "B1 (event-row form; B1 proper uses all-session bars) / B6 lower-complexity"

    def __init__(self, *, card_hash: str, min_effective_n: int = 2) -> None:
        super().__init__(card_hash=card_hash, condition_keys=(), min_effective_n=min_effective_n)


class PersistenceBaseline(_CellBaseline):
    """No-change: the last non-overlapping training episode's realized cell response."""

    slug = "persistence"
    rung = "persistence_no_change"
    card_baseline = "protocol section 6 component outlook: persistence/no-change"

    def __init__(self, *, card_hash: str) -> None:
        super().__init__(card_hash=card_hash, condition_keys=(), min_effective_n=1)

    def _estimate(self, rows):
        values, effective_n = _sample_values(rows)
        if effective_n < 1:
            return None, 0, None, None, "insufficient"
        # One episode supports a persistence forecast; it never claims more N.
        return float(values[-1]), 1, None, None, "comparator"


class NoGapBaseline(_CellBaseline):
    """Zero-increment comparator: predicts 0.0 wherever a training cell exists."""

    slug = "no_gap"
    rung = "no_gap_zero_increment"
    card_baseline = "protocol section 6 remaining repricing: no-gap/zero-increment"

    def __init__(self, *, card_hash: str) -> None:
        super().__init__(card_hash=card_hash, condition_keys=(), min_effective_n=1)

    def _estimate(self, rows):
        _, effective_n = _sample_values(rows)
        if effective_n < 1:
            return None, 0, None, None, "insufficient"
        return 0.0, effective_n, None, None, "comparator"


class AnnouncedOnlyBaseline(_CellBaseline):
    """Announced-path-only rung.  Abstains when the card registers no announced series."""

    slug = "announced_only"
    rung = "announced_only"
    card_baseline = "protocol section 6 component outlook: announced-only"
    abstention_reason = ANNOUNCED_ABSTENTION

    def __init__(self, *, card_hash: str, announced_source_ids: Sequence[str] = ()) -> None:
        if announced_source_ids:
            raise ContractError(
                "an announced-path series is registered but T15 implements no announced-path "
                "estimator; register and implement it separately -- never a stand-in"
            )
        super().__init__(card_hash=card_hash, condition_keys=(), min_effective_n=1)

    @classmethod
    def from_card(cls, card: Any) -> "AnnouncedOnlyBaseline":
        hash_value = _verified_card_hash(card)
        announced = [
            str(source.get("source_id"))
            for source in _card_mapping(card).get("sources") or []
            if any(
                marker in json.dumps(source, sort_keys=True).lower()
                for marker in ANNOUNCED_SOURCE_MARKERS
            )
        ]
        return cls(card_hash=hash_value, announced_source_ids=announced)

    def _estimate(self, rows):
        return None, 0, None, None, "unavailable"


class _DirectInputBaseline(_MeanCellBaseline):
    default_sources: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        card_hash: str,
        sources: Sequence[str] | None = None,
        exclude_sources: Iterable[str] = (),
        min_effective_n: int = 2,
    ) -> None:
        chosen = tuple(self.default_sources if sources is None else sources)
        unknown = [source for source in chosen if source not in DIRECT_INPUT_KEYS]
        if unknown:
            raise ContractError(f"no registered direct-input key for {unknown}")
        excluded = frozenset(exclude_sources)
        self.sources = tuple(source for source in chosen if source not in excluded)
        self.excluded_sources = tuple(sorted(excluded & set(chosen)))
        suffix = f"+ltifo-{'-'.join(self.excluded_sources)}" if self.excluded_sources else ""
        super().__init__(
            card_hash=card_hash,
            condition_keys=tuple(DIRECT_INPUT_KEYS[source] for source in self.sources),
            min_effective_n=min_effective_n,
            version_suffix=suffix,
        )

    @classmethod
    def from_card(
        cls,
        card: Any,
        *,
        ltifo_def: Mapping[str, Any] | None = None,
        target_id: str | None = None,
        min_effective_n: int | None = None,
    ):
        hash_value = _verified_card_hash(card)
        mapping = _card_mapping(card)
        rights = {
            str(source.get("source_id")): source.get("rights_state")
            for source in mapping.get("sources") or []
        }
        b4_inputs: set[str] = set()
        for baseline in mapping.get("baselines") or []:
            if baseline.get("baseline_id") == "B4":
                b4_inputs = set(baseline.get("inputs") or [])
        sources = [
            source
            for source in cls.default_sources
            if source in b4_inputs and rights.get(source) in OPEN_RIGHTS
        ]
        exclude: frozenset[str] = frozenset()
        if ltifo_def is not None:
            if target_id is None:
                raise ContractError("an LTIFO mask needs the target_id")
            exclude = ltifo_family_mask(card, ltifo_def, target_id)
        return cls(
            card_hash=hash_value,
            sources=sources,
            exclude_sources=exclude,
            min_effective_n=_card_min_effective_n(card) if min_effective_n is None else min_effective_n,
        )


class ComponentBaseline(_DirectInputBaseline):
    """The composite's components as separate direct inputs (card B4 information set)."""

    slug = "component"
    rung = "direct_component"
    card_baseline = "B4"
    default_sources = COMPONENT_SOURCES


class DirectFundingBaseline(_DirectInputBaseline):
    """Dollar and real yield as direct inputs: the C26 mechanical-overlap comparator."""

    slug = "direct_funding"
    rung = "direct_funding"
    card_baseline = "B4 funding legs (dollar, real yield); HY OAS excluded (UNPROVEN, not in B4)"
    default_sources = DIRECT_FUNDING_SOURCES


# ------------------------------------------------------------------ transforms
class TrainOnlyTransform(Protocol):
    """A fitted transform bound to ONE walk-forward split; fit sees train rows only."""

    split: WalkForwardSplit

    def fit(self, train_observations: Sequence[ForwardReturnObservation]) -> "TrainOnlyTransform": ...

    def apply(self, row: ForwardReturnObservation) -> ForwardReturnObservation: ...


def check_train_only(
    split: WalkForwardSplit, observations: Sequence[ForwardReturnObservation]
) -> None:
    """Raise ``LeakedFitError`` for any row outside the fold's purged training set.

    The fold boundary is the plan's own: a row is eligible only when its shock is
    in ``split.train_shock_ids`` and it was detected on or before
    ``split.train_end``.  (``anchor_session`` is strictly after detection, so the
    last purged training shock's anchor may fall after ``train_end`` legitimately.)
    """

    train_ids = set(split.train_shock_ids)
    leaked = sorted(
        {
            row.shock_id
            for row in observations
            if row.shock_id not in train_ids or row.first_detected.date() > split.train_end
        }
    )
    if leaked:
        raise LeakedFitError(
            f"transform fit received {len(leaked)} non-training shock(s) for the fold ending "
            f"{split.train_end.isoformat()}: {leaked[:5]}"
        )


class QuantileBucketTransform:
    """Bucket a continuous origin covariate by cut points fitted on the fold's train rows."""

    def __init__(
        self,
        split: WalkForwardSplit,
        *,
        source_key: str = TARGET_VOL60,
        output_key: str = TARGET_VOL60_TERCILE,
        n_buckets: int = 3,
    ) -> None:
        if n_buckets < 2:
            raise ContractError("n_buckets must be at least 2")
        self.split = split
        self.source_key = source_key
        self.output_key = output_key
        self.n_buckets = int(n_buckets)
        self.cut_points: tuple[float, ...] | None = None
        self.fitted_on: tuple[str, ...] = ()

    def fit(self, train_observations):
        check_train_only(self.split, train_observations)
        per_shock: dict[str, float] = {}
        for row in train_observations:
            value = row.conditions.get(self.source_key)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                per_shock.setdefault(row.shock_id, float(value))
        if len(per_shock) < self.n_buckets:
            raise ContractError("too few training shocks to fit the bucket cut points")
        quantiles = np.linspace(0, 1, self.n_buckets + 1)[1:-1]
        self.cut_points = tuple(float(q) for q in np.quantile(list(per_shock.values()), quantiles))
        self.fitted_on = tuple(sorted(per_shock))
        return self

    def apply(self, row):
        if self.cut_points is None:
            raise ContractError("apply() before fit()")
        value = row.conditions.get(self.source_key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            bucket = f"q{int(np.searchsorted(self.cut_points, float(value), side='right')) + 1}"
        else:
            bucket = "unknown"
        conditions = dict(row.conditions)
        conditions[self.output_key] = bucket
        return replace(row, conditions=conditions)


class PriceMomentumBaseline(_MeanCellBaseline):
    """Target context: trailing 20-session return sign, 60-session vol tercile, 200-session trend."""

    slug = "price_momentum"
    rung = "context"
    card_baseline = "B3"
    transform_factories = (lambda split: QuantileBucketTransform(split),)

    def __init__(self, *, card_hash: str, min_effective_n: int = 2) -> None:
        super().__init__(
            card_hash=card_hash, condition_keys=PRICE_CONTEXT_KEYS, min_effective_n=min_effective_n
        )


# --------------------------------------------------------------------- runners
def run_fold_transformed(
    observations: Sequence[ForwardReturnObservation],
    *,
    plan: WalkForwardPlan,
    estimator: ResponseCurveEstimator,
    relation_id: str,
    condition_keys: Sequence[str] = (),
    transform_factories: Sequence[Callable[[WalkForwardSplit], TrainOnlyTransform]] = (),
) -> list[WalkForwardPrediction]:
    """``run_walk_forward_curves`` with per-fold transforms fitted on that fold's train rows."""

    if not transform_factories:
        return run_walk_forward_curves(
            observations,
            plan=plan,
            estimator=estimator,
            relation_id=relation_id,
            condition_keys=condition_keys,
        )
    rows_by_shock: dict[str, list[ForwardReturnObservation]] = {}
    for row in observations:
        rows_by_shock.setdefault(row.shock_id, []).append(row)
    predictions: list[WalkForwardPrediction] = []
    for split_index, split in enumerate(plan.splits):
        train_rows = [
            row
            for shock_id in split.train_shock_ids
            for row in rows_by_shock.get(shock_id, [])
            if row.horizon_bdays == plan.horizon_bdays
        ]
        transforms = [factory(split).fit(train_rows) for factory in transform_factories]
        fold_rows = []
        for shock_id in (*split.train_shock_ids, *split.validation_shock_ids):
            for row in rows_by_shock.get(shock_id, []):
                for transform in transforms:
                    row = transform.apply(row)
                fold_rows.append(row)
        fold_plan = WalkForwardPlan(
            splits=(split,),
            untouched_holdout_shock_ids=plan.untouched_holdout_shock_ids,
            holdout_start=plan.holdout_start,
            horizon_bdays=plan.horizon_bdays,
        )
        for prediction in run_walk_forward_curves(
            fold_rows,
            plan=fold_plan,
            estimator=estimator,
            relation_id=relation_id,
            condition_keys=condition_keys,
        ):
            predictions.append(replace(prediction, split_index=split_index))
    return predictions


def run_baseline(
    observations: Sequence[ForwardReturnObservation],
    *,
    plan: WalkForwardPlan,
    baseline: Any,
    relation_id: str,
) -> list[WalkForwardPrediction]:
    """Score one baseline on the shared plan with ITS declared information set."""

    return run_fold_transformed(
        observations,
        plan=plan,
        estimator=baseline,
        relation_id=relation_id,
        condition_keys=baseline.condition_keys,
        transform_factories=getattr(baseline, "transform_factories", ()),
    )


def run_direction_partitioned(
    observations: Sequence[ForwardReturnObservation],
    *,
    directions: Mapping[str, int],
    plan: WalkForwardPlan,
    estimator: ResponseCurveEstimator,
    relation_id: str,
    condition_keys: Sequence[str] = (),
) -> list[WalkForwardPrediction]:
    """Card M1 harness: partition episodes by ShockRecord.direction; estimator unchanged."""

    partitions: dict[int, list[ForwardReturnObservation]] = {}
    for row in observations:
        if row.shock_id not in directions:
            raise ContractError(f"no declared direction for shock {row.shock_id}")
        direction = int(directions[row.shock_id])
        if direction not in (-1, 1):
            raise ContractError("direction must be -1 or 1")
        partitions.setdefault(direction, []).append(row)
    predictions: list[WalkForwardPrediction] = []
    for direction in sorted(partitions):
        predictions.extend(
            run_walk_forward_curves(
                partitions[direction],
                plan=plan,
                estimator=estimator,
                relation_id=relation_id,
                condition_keys=condition_keys,
            )
        )
    return sorted(
        predictions,
        key=lambda p: (p.split_index, p.anchor_session, p.shock_id, p.target_id, p.horizon_bdays),
    )


# ------------------------------------------------------------ paired population
def _prediction_key(row: WalkForwardPrediction) -> PredictionKey:
    return row.shock_id, row.target_id, row.horizon_bdays


def _keyed(name: str, rows: Sequence[WalkForwardPrediction]) -> dict[PredictionKey, WalkForwardPrediction]:
    keyed: dict[PredictionKey, WalkForwardPrediction] = {}
    for row in rows:
        key = _prediction_key(row)
        if key in keyed:
            raise ContractError(f"{name} carries a duplicate prediction key {key}")
        keyed[key] = row
    return keyed


@dataclass(frozen=True)
class PairedPopulation:
    """Identical (shock_id, target_id, horizon_bdays) keys across every member (C27)."""

    members: tuple[str, ...]
    keys: tuple[PredictionKey, ...]
    per_fold: Mapping[int, int]

    @classmethod
    def require(cls, predictions: Mapping[str, Sequence[WalkForwardPrediction]]) -> "PairedPopulation":
        if len(predictions) < 2:
            raise ContractError("a paired population needs a candidate and at least one comparator")
        names = tuple(predictions)
        keyed = {name: _keyed(name, rows) for name, rows in predictions.items()}
        reference_name = names[0]
        reference = keyed[reference_name]
        asymmetric: dict[str, dict[str, tuple[PredictionKey, ...]]] = {}
        for name in names[1:]:
            other = keyed[name]
            only_reference = tuple(sorted(set(reference) - set(other)))
            only_other = tuple(sorted(set(other) - set(reference)))
            if only_reference or only_other:
                asymmetric[name] = {
                    f"missing_vs_{reference_name}": only_reference,
                    f"extra_vs_{reference_name}": only_other,
                }
                continue
            for key, row in other.items():
                base = reference[key]
                if row.split_index != base.split_index:
                    raise ContractError(f"{name} scores {key} in a different fold")
                if not math.isclose(row.realized_return, base.realized_return, rel_tol=0, abs_tol=1e-12):
                    raise ContractError(f"{name} disagrees on the realized return of {key}")
        if asymmetric:
            raise PopulationMismatch(asymmetric)
        per_fold: dict[int, int] = {}
        for row in reference.values():
            per_fold[row.split_index] = per_fold.get(row.split_index, 0) + 1
        return cls(members=names, keys=tuple(sorted(reference)), per_fold=dict(sorted(per_fold.items())))


def restrict_to_common(
    predictions: Mapping[str, Sequence[WalkForwardPrediction]],
) -> tuple[dict[str, list[WalkForwardPrediction]], dict[str, int]]:
    """Explicitly restrict every member to the common key set; report what each lost.

    This is the card's paired population (origins where every member predicts).
    The drop counts are returned so coverage is quoted, never silently narrowed.
    """

    keyed = {name: _keyed(name, rows) for name, rows in predictions.items()}
    common = set.intersection(*(set(rows) for rows in keyed.values())) if keyed else set()
    restricted = {
        name: [rows[key] for key in sorted(common)] for name, rows in keyed.items()
    }
    dropped = {name: len(rows) - len(common) for name, rows in keyed.items()}
    return restricted, dropped


def score_paired(
    candidate: Sequence[WalkForwardPrediction],
    comparator: Sequence[WalkForwardPrediction],
    *,
    mean_test_fn: Callable[..., Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Refuse unequal populations, then score with the existing incremental scorer."""

    population = PairedPopulation.require({"candidate": candidate, "comparator": comparator})
    result = score_incremental_predictions(candidate, comparator, mean_test_fn=mean_test_fn)
    result["paired_keys"] = len(population.keys)
    result["per_fold"] = dict(population.per_fold)
    return result


def mean_squared_error(rows: Sequence[WalkForwardPrediction]) -> float | None:
    if not rows:
        return None
    return float(np.mean([(row.realized_return - row.predicted_return) ** 2 for row in rows]))


def novelty_disposition(
    candidate: Sequence[WalkForwardPrediction],
    direct_funding: Sequence[WalkForwardPrediction],
    *,
    alpha: float,
    mean_test_fn: Callable[..., Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """C26: the candidate's novelty claim is withheld unless it beats ``direct_funding``.

    Scored on the identical paired population.  A missing canonical HAC
    dependency is an abstention carrying the exact error text, never a p-value.
    """

    population = PairedPopulation.require({"candidate": candidate, "direct_funding": direct_funding})
    out: dict[str, object] = {
        "comparator": "direct_funding",
        "paired_keys": len(population.keys),
        "per_fold": dict(population.per_fold),
        "candidate_mse": mean_squared_error(candidate),
        "direct_funding_mse": mean_squared_error(direct_funding),
        "alpha": alpha,
    }
    try:
        scored = score_incremental_predictions(candidate, direct_funding, mean_test_fn=mean_test_fn)
    except StatisticalDependencyUnavailable as exc:
        out.update(
            status="novelty_withheld",
            p_value=None,
            mean_squared_error_improvement=None,
            reason=f"StatisticalDependencyUnavailable: {exc}",
        )
        return out
    p_value = scored.get("p_value")
    improvement = scored.get("mean_squared_error_improvement")
    out.update(
        p_value=p_value,
        mean_squared_error_improvement=improvement,
        effective_n=scored.get("effective_n"),
        n_paired_rows=scored.get("n_paired_rows"),
    )
    if improvement is not None and improvement > 0 and p_value is not None and p_value < alpha:
        out.update(status="novelty_admissible_for_review", reason="beats direct_funding on the paired population")
    else:
        out.update(status="novelty_withheld", reason="no gain over direct_funding on the paired population")
    return out


# ------------------------------------------------------------------------ LTIFO
def ltifo_definition_hash(definition: Mapping[str, Any]) -> str:
    body = {k: v for k, v in definition.items() if k != "definition_hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def load_ltifo_definition(path: str | Path = DEFAULT_LTIFO_PATH) -> dict[str, Any]:
    definition = json.loads(Path(path).read_text(encoding="utf-8"))
    if definition.get("definition_version") != LTIFO_VERSION:
        raise ContractError("unexpected LTIFO definition_version")
    if definition.get("definition_hash") != ltifo_definition_hash(definition):
        raise ContractError("LTIFO definition_hash does not recompute")
    return definition


def ltifo_family_mask(card: Any, ltifo_def: Mapping[str, Any], target_id: str) -> frozenset[str]:
    """Source ids of every information family containing ``target_id`` (sensitivity only)."""

    hash_value = _verified_card_hash(card)
    if (ltifo_def.get("card_ref") or {}).get("card_hash") != hash_value:
        raise ContractError("LTIFO definition is registered against a different card")
    if ltifo_def.get("definition_hash") != ltifo_definition_hash(ltifo_def):
        raise ContractError("LTIFO definition_hash does not recompute")
    families = {
        str(family["family_id"]): tuple(family.get("members") or ())
        for family in ltifo_def.get("families") or []
    }
    target_map = ltifo_def.get("target_family_map") or {}
    member_of = [family_id for family_id, members in families.items() if target_id in members]
    if target_id not in target_map and not member_of:
        raise ContractError(f"target {target_id} is not covered by the LTIFO definition")
    selected = set(target_map.get(target_id, ())) | set(member_of)
    unknown = selected - set(families)
    if unknown:
        raise ContractError(f"LTIFO target map names unknown families {sorted(unknown)}")
    return frozenset(member for family_id in selected for member in families[family_id])


# ----------------------------------------------------------------- ladder table
BASELINE_LADDER: tuple[Mapping[str, str], ...] = (
    {
        "rung": "unconditional",
        "class": "PooledMeanBaseline",
        "information_set": "() -- training event-row mean",
        "card": "B1 / B6",
        "protocol_6": "asset response: unconditional mean",
    },
    {
        "rung": "context",
        "class": "PriceMomentumBaseline",
        "information_set": ", ".join(PRICE_CONTEXT_KEYS),
        "card": "B3",
        "protocol_6": "asset response: return/vol/trend context",
    },
    {
        "rung": "direct_component",
        "class": "ComponentBaseline",
        "information_set": ", ".join(DIRECT_INPUT_KEYS[s] for s in COMPONENT_SOURCES),
        "card": "B4",
        "protocol_6": "asset response: direct observable macro inputs",
    },
    {
        "rung": "direct_funding",
        "class": "DirectFundingBaseline",
        "information_set": ", ".join(DIRECT_INPUT_KEYS[s] for s in DIRECT_FUNDING_SOURCES),
        "card": "B4 funding legs",
        "protocol_6": "funding composite contains dollar/real yield/HY: direct-component comparator",
    },
    {
        "rung": "persistence_no_change",
        "class": "PersistenceBaseline",
        "information_set": "() -- last training episode",
        "card": "-",
        "protocol_6": "component outlook: persistence/no-change",
    },
    {
        "rung": "announced_only",
        "class": "AnnouncedOnlyBaseline",
        "information_set": "unavailable: no announced-path series in the card",
        "card": "-",
        "protocol_6": "component outlook: announced-only",
    },
    {
        "rung": "no_gap_zero_increment",
        "class": "NoGapBaseline",
        "information_set": "() -- predicts 0",
        "card": "-",
        "protocol_6": "remaining repricing: no-gap/zero-increment",
    },
)
