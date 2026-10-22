"""GLT T16: response path over the card's horizon grid, under ONE plan and ONE budget.

Measurement only.  Everything this module evaluates is declared by the frozen
T14 preregistration card (``glt_preregistration_card.v1.json``):

* ``ResponsePathSpec.from_card`` reads the horizon grid, primary horizon,
  response-time functional (the v1 card declares none), model families, tuning
  budget, block definition and purge length.  Nothing is read from data.
* ``PooledChallenger`` / ``LocalProjectionChallenger`` /
  ``StateConditionedChallenger`` implement the existing
  ``ResponseCurveEstimator`` protocol, so they run through the same
  ``run_walk_forward_curves`` machinery as the incumbent.
* ``fit_response_path`` runs every estimator on ONE walk-forward plan, purged at
  the longest path horizon, and registers every (family x hyperparameter x
  horizon) trial with ONE ``SearchBudget`` that refuses trial n+1 of the card's
  ``family.n_trials_total``.
* ``response_time_functional`` never returns a single session: it returns an
  interval between grid horizons, a supported region, or ``unavailable``.  A
  pointwise band never licenses it (C29).
* ``delay_cost_sensitivity`` describes the response remaining after acting k
  sessions late.  It is a description, not a recommendation.

No local projection here supplies exogeneity (S31); every path is association
evidence under the card's ``identification_status``.  ``validated`` stays False.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from brain.liquidity_lab.baselines import (
    QuantileBucketTransform,
    _card_mapping,
    _verified_card_hash,
    card_hash_prefix,
    run_fold_transformed,
)
from brain.liquidity_lab.contracts import HORIZONS_BDAYS, ContractError
from brain.liquidity_lab.estimator import (
    ForwardReturnObservation,
    HierarchicalMeanCurveEstimator,
    ResponseCurveCell,
    condition_bucket,
)
from brain.liquidity_lab.validation import (
    WalkForwardPlan,
    WalkForwardPrediction,
    WalkForwardSplit,
)
from brain.liquidity_lab.window_guard import ReservedWindowTouched

FUNCTIONAL_KINDS = ("peak", "time_to_fraction", "threshold_crossing")
SHOCK_SIZE_KEY = "shock_size_z"
SHOCK_SIZE_BUCKET_KEY = "shock_size_tercile"
NO_FUNCTIONAL_REASON = (
    "the frozen card declares no response-time functional (horizons carry "
    "unit/candidates/primary/sensitivity only); no response time is estimated"
)
DELAY_COST_NOTE = (
    "description of response remaining after acting k sessions after detection; "
    "linear between grid horizons with R(0)=0; not a recommendation"
)


class SearchBudgetExceeded(ContractError):
    """A trial beyond the card's ``family.n_trials_total`` was requested."""


# ------------------------------------------------------------------------- spec
def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _condition_keys_from_card(value: Any) -> tuple[str, ...]:
    """The card writes ``"none: ..."`` for the empty tuple; a list is taken literally."""

    if value is None:
        return ()
    if isinstance(value, str):
        if value.strip().lower().startswith("none"):
            return ()
        raise ContractError(f"unparseable card condition_keys: {value!r}")
    return tuple(str(key) for key in value)


@dataclass(frozen=True, slots=True)
class ResponsePathSpec:
    """Everything the path evaluation may use, read ONLY from the frozen card."""

    card_hash: str
    relation_id: str
    horizon_unit: str
    horizon_grid: tuple[int, ...]
    primary_horizon: int
    sensitivity_horizons: tuple[int, ...]
    functional_kind: str | None
    model_families: tuple[str, ...]
    model_version: str
    prior_strength_grid: tuple[int, ...]
    tuning_budget: int
    min_effective_n: int
    condition_keys: tuple[str, ...]
    n_trials_total: int
    blocks: str
    dependence_rule: str
    purge_sessions: int
    reserved_start: date
    identification_status: str
    treatment_identification_status: str = "NOT_IDENTIFIED"

    @classmethod
    def from_card(cls, card: Any) -> "ResponsePathSpec":
        digest = _verified_card_hash(card)
        mapping = _card_mapping(card)
        horizons = mapping["horizons"]
        grid = tuple(int(h) for h in horizons["candidates"])
        primary = int(horizons["primary"])
        if primary not in grid:
            raise ContractError("card primary horizon is not on its candidate grid")
        if any(h not in HORIZONS_BDAYS for h in grid):
            raise ContractError("card horizon grid leaves the precommitted horizons")
        models = mapping.get("models") or []
        if not models:
            raise ContractError("card declares no model")
        hyper = models[0].get("hyperparameters") or {}
        windows = mapping["windows"]
        purge = int(windows["purge_sessions"])
        if purge < max(grid):
            raise ContractError("card purge is shorter than its longest horizon")
        functional = horizons.get("functional") or horizons.get("response_time_functional")
        if functional is not None and functional not in FUNCTIONAL_KINDS:
            raise ContractError(f"unknown card functional {functional!r}")
        power = mapping.get("power") or {}
        estimand_ref = mapping.get("estimand_card_ref") or {}
        return cls(
            card_hash=digest,
            relation_id=str(estimand_ref.get("relation_id") or mapping.get("task_id")),
            horizon_unit=str(horizons.get("unit")),
            horizon_grid=tuple(sorted(grid)),
            primary_horizon=primary,
            sensitivity_horizons=tuple(int(h) for h in horizons.get("sensitivity") or ()),
            functional_kind=functional,
            model_families=tuple(str(m["family"]) for m in models),
            model_version=str(hyper["model_version"]),
            prior_strength_grid=tuple(int(p) for p in hyper["prior_strength_grid"]),
            tuning_budget=int(models[0]["tuning_budget"]),
            min_effective_n=int(hyper["min_effective_n"]),
            condition_keys=_condition_keys_from_card(hyper.get("condition_keys")),
            n_trials_total=int(mapping["family"]["n_trials_total"]),
            blocks=str(power.get("blocks")),
            dependence_rule=str(power.get("dependence_rule")),
            purge_sessions=purge,
            reserved_start=_parse_date(windows["reserved_start"]),
            identification_status=str(estimand_ref.get("identification_status") or "association_only"),
            treatment_identification_status=str(
                estimand_ref.get("treatment_identification_status") or "NOT_IDENTIFIED"
            ),
        )

    def incumbent_configs(self) -> tuple[HierarchicalMeanCurveEstimator, ...]:
        """The card's M1 configurations: one per ``prior_strength_grid`` entry."""

        if len(self.prior_strength_grid) > self.tuning_budget:
            raise ContractError("card prior grid exceeds its tuning budget")
        configs = []
        for strength in self.prior_strength_grid:
            estimator = HierarchicalMeanCurveEstimator(
                model_version=f"{self.model_version}+prior{strength}@{card_hash_prefix(self.card_hash)}",
                prior_strength=strength,
                min_effective_n=self.min_effective_n,
            )
            estimator.search_family = self.model_families[0]  # type: ignore[attr-defined]
            estimator.hyperparameter = f"prior_strength={strength}"  # type: ignore[attr-defined]
            estimator.condition_keys = self.condition_keys  # type: ignore[attr-defined]
            configs.append(estimator)
        return tuple(configs)


# ---------------------------------------------------------------------- budget
@dataclass
class SearchBudget:
    """ONE fixed search budget: (family x hyperparameter x horizon) trials."""

    card_hash: str
    n_trials_total: int
    trials: list[tuple[str, str, int]] = field(default_factory=list)

    def register(self, family: str, hyperparameter: str, horizon: int) -> int:
        key = (str(family), str(hyperparameter), int(horizon))
        if key in self.trials:
            return len(self.trials)
        if len(self.trials) >= self.n_trials_total:
            raise SearchBudgetExceeded(
                f"trial {len(self.trials) + 1} {key} refused: card family.n_trials_total="
                f"{self.n_trials_total} is spent (card_hash {card_hash_prefix(self.card_hash)})"
            )
        self.trials.append(key)
        return len(self.trials)

    @property
    def remaining(self) -> int:
        return self.n_trials_total - len(self.trials)


def search_budget_guard(spec: ResponsePathSpec) -> SearchBudget:
    """The ONE budget for a path evaluation: the card's ``family.n_trials_total``."""

    return SearchBudget(card_hash=spec.card_hash, n_trials_total=spec.n_trials_total)


def trial_identity(estimator: Any) -> tuple[str, str]:
    family = getattr(estimator, "search_family", None) or type(estimator).__name__
    hyper = getattr(estimator, "hyperparameter", None) or estimator.model_version
    return str(family), str(hyper)


# ------------------------------------------------------------------ challengers
class PooledChallenger(HierarchicalMeanCurveEstimator):
    """No shrinkage and no conditioning: the target's own episode mean per horizon."""

    search_family = "pooled_no_shrinkage"

    def __init__(self, *, card_hash: str, min_effective_n: int) -> None:
        super().__init__(
            model_version=f"glt_t16_pooled.v1@{card_hash_prefix(card_hash)}",
            prior_strength=0,
            min_effective_n=min_effective_n,
        )
        self.card_hash = card_hash
        self.condition_keys: tuple[str, ...] = ()
        self.hyperparameter = "prior_strength=0"

    def fit(self, observations, *, condition_keys=()):
        if tuple(condition_keys):
            raise ContractError("PooledChallenger takes no conditioning information")
        return super().fit(observations, condition_keys=())


class StateConditionedChallenger(HierarchicalMeanCurveEstimator):
    """The incumbent with the card's own ``condition_keys`` (empty on the v1 card)."""

    search_family = "state_conditioned_hierarchical"

    def __init__(self, spec: ResponsePathSpec, *, prior_strength: int) -> None:
        if prior_strength not in spec.prior_strength_grid:
            raise ContractError("prior_strength is not on the card grid")
        super().__init__(
            model_version=(
                f"glt_t16_state_conditioned.v1+prior{prior_strength}@{card_hash_prefix(spec.card_hash)}"
            ),
            prior_strength=prior_strength,
            min_effective_n=spec.min_effective_n,
        )
        self.card_hash = spec.card_hash
        self.condition_keys = spec.condition_keys
        self.hyperparameter = (
            f"prior_strength={prior_strength}|keys={','.join(spec.condition_keys) or 'none'}"
        )

    def fit(self, observations, *, condition_keys=()):
        if tuple(condition_keys) != self.condition_keys:
            raise ContractError("StateConditionedChallenger uses exactly the card's condition_keys")
        return super().fit(observations, condition_keys=self.condition_keys)


class LocalProjectionChallenger:
    """Per-horizon least squares of the episode response on the DECLARED shock size.

    One regression per (target, shock family, horizon) over thinned episodes
    (``y_e = a + b * size_e``), evaluated at each size bucket's mean training
    size.  Buckets are fitted per fold on train rows only
    (``QuantileBucketTransform``).  The cell's ``effective_n`` is the bucket's
    own episode support; the support borrowed from the other buckets through the
    linear form is reported separately as ``prior_effective_n``.  A regression
    on shock size does not supply exogeneity (S31).
    """

    search_family = "binned_local_projection"
    identification = "none: a regression on declared shock size does not supply exogeneity (S31)"

    def __init__(
        self,
        *,
        card_hash: str,
        min_effective_n: int,
        size_key: str = SHOCK_SIZE_KEY,
        bucket_key: str = SHOCK_SIZE_BUCKET_KEY,
    ) -> None:
        if min_effective_n < 2:
            raise ContractError("min_effective_n must be at least 2")
        self.card_hash = card_hash
        self.min_effective_n = int(min_effective_n)
        self.size_key = size_key
        self.bucket_key = bucket_key
        self.condition_keys: tuple[str, ...] = (bucket_key,)
        self.model_version = f"glt_t16_local_projection.v1@{card_hash_prefix(card_hash)}"
        self.hyperparameter = f"size={size_key}|bucket={bucket_key}"
        self.transform_factories: tuple[Callable[[WalkForwardSplit], Any], ...] = (
            lambda split: QuantileBucketTransform(split, source_key=size_key, output_key=bucket_key),
        )

    def _episodes(self, rows: Sequence[ForwardReturnObservation]) -> list[tuple[float, float, str]]:
        """Thinned (size, response, bucket) per episode under the incumbent's honest-N rule."""

        by_shock: dict[str, list[ForwardReturnObservation]] = {}
        for row in rows:
            by_shock.setdefault(row.shock_id, []).append(row)
        unique = []
        for group in by_shock.values():
            size = group[0].conditions.get(self.size_key)
            if not isinstance(size, (int, float)) or not np.isfinite(float(size)):
                raise ContractError(
                    f"declared shock size {self.size_key!r} missing on {group[0].shock_id}"
                )
            unique.append(
                (
                    min(r.anchor_session for r in group),
                    max(r.exit_session for r in group),
                    float(size),
                    float(np.mean([r.forward_return for r in group])),
                    condition_bucket(group[0], self.condition_keys),
                )
            )
        kept = []
        last_exit = None
        for anchor, exit_, size, response, bucket in sorted(unique):
            if last_exit is None or anchor >= last_exit:
                kept.append((size, response, bucket))
                last_exit = exit_
        return kept

    def fit(self, observations, *, condition_keys=()):
        if tuple(condition_keys) != self.condition_keys:
            raise ContractError(
                f"LocalProjectionChallenger declares {self.condition_keys}; "
                f"refusing undeclared information {tuple(condition_keys)}"
            )
        groups: dict[tuple[str, str, int], list[ForwardReturnObservation]] = {}
        axes: set[tuple[str, str, str]] = set()
        for row in observations:
            if row.horizon_bdays not in HORIZONS_BDAYS:
                raise ContractError("observation horizon is not precommitted")
            groups.setdefault((row.target_id, row.shock_family, row.horizon_bdays), []).append(row)
            axes.add((row.target_id, row.shock_family, condition_bucket(row, self.condition_keys)))
        cells: list[ResponseCurveCell] = []
        for target_id, shock_family, bucket in sorted(axes):
            for horizon in HORIZONS_BDAYS:
                episodes = self._episodes(groups.get((target_id, shock_family, horizon), []))
                cells.append(self._cell(target_id, shock_family, bucket, horizon, episodes))
        return cells

    def _cell(self, target_id, shock_family, bucket, horizon, episodes) -> ResponseCurveCell:
        own = [e for e in episodes if e[2] == bucket]
        usable = [e for e in episodes if not e[2].endswith("=unknown")]
        n_own, n_all = len(own), len(usable)
        common = dict(
            target_id=target_id,
            shock_family=shock_family,
            condition_bucket=bucket,
            horizon_bdays=horizon,
            sample_n=n_own,
            effective_n=n_own,
            prior_mean=None,
            prior_effective_n=max(n_all - n_own, 0),
        )
        sizes = np.asarray([e[0] for e in usable], dtype=float)
        if (
            bucket.endswith("=unknown")
            or n_own < self.min_effective_n
            or n_all < 3
            or float(np.ptp(sizes)) == 0.0
        ):
            return ResponseCurveCell(
                **common,
                raw_mean=None,
                shrunk_mean=None,
                interval_low=None,
                interval_high=None,
                evidence_state="insufficient",
            )
        responses = np.asarray([e[1] for e in usable], dtype=float)
        x_bar = float(sizes.mean())
        sxx = float(((sizes - x_bar) ** 2).sum())
        slope = float(((sizes - x_bar) * (responses - responses.mean())).sum() / sxx)
        intercept = float(responses.mean() - slope * x_bar)
        resid = responses - (intercept + slope * sizes)
        s2 = float((resid**2).sum() / (n_all - 2))
        representative = float(np.mean([e[0] for e in own]))
        estimate = intercept + slope * representative
        se = float(np.sqrt(s2 * (1.0 / n_all + (representative - x_bar) ** 2 / sxx)))
        return ResponseCurveCell(
            **common,
            raw_mean=float(np.mean([e[1] for e in own])),
            shrunk_mean=float(estimate),
            interval_low=float(estimate - 1.96 * se),
            interval_high=float(estimate + 1.96 * se),
            evidence_state="discovered",
        )


# ------------------------------------------------------------------------- path
@dataclass(frozen=True, slots=True)
class ResponsePath:
    """One estimator's in-sample cells across the card grid for one curve axis."""

    model_version: str
    family: str
    partition: str
    target_id: str
    shock_family: str
    condition_bucket: str
    horizons: tuple[int, ...]
    cells: tuple[ResponseCurveCell | None, ...]

    @property
    def points(self) -> tuple[float | None, ...]:
        return tuple(None if c is None else c.shrunk_mean for c in self.cells)

    @property
    def effective_n(self) -> tuple[int, ...]:
        return tuple(0 if c is None else c.effective_n for c in self.cells)

    @property
    def prior_effective_n(self) -> tuple[int, ...]:
        return tuple(0 if c is None else c.prior_effective_n for c in self.cells)


@dataclass(frozen=True)
class ResponsePathResult:
    card_hash: str
    relation_id: str
    horizons: tuple[int, ...]
    primary_horizon: int
    plan_purge_horizon: int
    paths: tuple[ResponsePath, ...]
    predictions: Mapping[str, Mapping[int, tuple[WalkForwardPrediction, ...]]]
    trials: tuple[tuple[str, str, int], ...]
    trials_remaining: int

    def path(
        self,
        model_version: str,
        *,
        target_id: str,
        partition: str = "all",
        bucket: str = "all",
        shock_family: str | None = None,
    ) -> ResponsePath:
        for path in self.paths:
            if (path.model_version, path.target_id, path.partition, path.condition_bucket) == (
                model_version,
                target_id,
                partition,
                bucket,
            ) and (shock_family is None or path.shock_family == shock_family):
                return path
        raise KeyError((model_version, target_id, partition, bucket))

    def oos_mse(self, model_version: str, horizon: int) -> float | None:
        rows = self.predictions.get(model_version, {}).get(horizon, ())
        if not rows:
            return None
        return float(np.mean([(r.realized_return - r.predicted_return) ** 2 for r in rows]))


def _plan_at(plan: WalkForwardPlan, horizon: int) -> WalkForwardPlan:
    return replace(
        plan,
        horizon_bdays=horizon,
        splits=tuple(replace(split, horizon_bdays=horizon) for split in plan.splits),
    )


def _in_sample_rows(
    estimator: Any, rows: Sequence[ForwardReturnObservation]
) -> list[ForwardReturnObservation]:
    factories = getattr(estimator, "transform_factories", ())
    if not factories or not rows:
        return list(rows)
    shock_ids = tuple(sorted({r.shock_id for r in rows}))
    last = max(r.first_detected.date() for r in rows)
    pseudo = WalkForwardSplit(
        train_shock_ids=shock_ids,
        validation_shock_ids=(),
        train_end=last,
        validation_start=last,
        validation_end=last,
        horizon_bdays=max(r.horizon_bdays for r in rows),
    )
    out = list(rows)
    for factory in factories:
        transform = factory(pseudo).fit(out)
        out = [transform.apply(r) for r in out]
    return out


def fit_response_path(
    observations: Sequence[ForwardReturnObservation],
    *,
    spec: ResponsePathSpec,
    plan: WalkForwardPlan,
    estimators: Sequence[Any],
    budget: SearchBudget | None = None,
    directions: Mapping[str, int] | None = None,
) -> ResponsePathResult:
    """Run every estimator on ONE plan across the card grid under ONE budget.

    ``plan`` must be purged at least at the longest grid horizon; its splits are
    re-used unchanged at every horizon, so every horizon is scored on the same
    origins.  ``directions`` applies the card's M1 direction partition to every
    estimator alike.  Rows reaching ``reserved_start`` are refused outright.
    Paths are in-sample descriptions of the supplied (window-admitted) rows;
    skill comes only from the walk-forward predictions.
    """

    if budget is None:
        budget = search_budget_guard(spec)
    if budget.card_hash != spec.card_hash:
        raise ContractError("search budget belongs to a different card")
    if plan.horizon_bdays < max(spec.horizon_grid):
        raise ContractError(
            f"the ONE plan is purged at h={plan.horizon_bdays}; "
            f"the path needs purge >= {max(spec.horizon_grid)}"
        )
    touching = [
        r.shock_id
        for r in observations
        if r.exit_session >= spec.reserved_start or r.anchor_session >= spec.reserved_start
    ]
    if touching:
        raise ReservedWindowTouched(
            f"{len(touching)} row(s) reach reserved_start {spec.reserved_start.isoformat()}"
        )
    versions = [e.model_version for e in estimators]
    if len(set(versions)) != len(versions):
        raise ContractError("estimators must carry distinct model_version strings")
    partitions: dict[str, list[ForwardReturnObservation]] = {}
    for row in observations:
        if row.horizon_bdays not in spec.horizon_grid:
            continue
        if directions is None:
            label = "all"
        else:
            if row.shock_id not in directions:
                raise ContractError(f"no declared direction for shock {row.shock_id}")
            direction = int(directions[row.shock_id])
            if direction not in (-1, 1):
                raise ContractError("direction must be -1 or 1")
            label = f"direction={direction:+d}"
        partitions.setdefault(label, []).append(row)

    predictions: dict[str, dict[int, tuple[WalkForwardPrediction, ...]]] = {}
    paths: list[ResponsePath] = []
    for estimator in estimators:
        family, hyper = trial_identity(estimator)
        keys = tuple(getattr(estimator, "condition_keys", ()))
        factories = tuple(getattr(estimator, "transform_factories", ()))
        per_h: dict[int, tuple[WalkForwardPrediction, ...]] = {}
        for horizon in spec.horizon_grid:
            budget.register(family, hyper, horizon)
            plan_h = _plan_at(plan, horizon)
            rows: list[WalkForwardPrediction] = []
            for label in sorted(partitions):
                rows.extend(
                    run_fold_transformed(
                        partitions[label],
                        plan=plan_h,
                        estimator=estimator,
                        relation_id=spec.relation_id,
                        condition_keys=keys,
                        transform_factories=factories,
                    )
                )
            per_h[horizon] = tuple(
                sorted(rows, key=lambda p: (p.split_index, p.anchor_session, p.shock_id, p.target_id))
            )
        predictions[estimator.model_version] = per_h
        for label in sorted(partitions):
            cells = estimator.fit(_in_sample_rows(estimator, partitions[label]), condition_keys=keys)
            index = {
                (c.target_id, c.shock_family, c.condition_bucket, c.horizon_bdays): c for c in cells
            }
            for axis in sorted({k[:3] for k in index}):
                paths.append(
                    ResponsePath(
                        model_version=estimator.model_version,
                        family=family,
                        partition=label,
                        target_id=axis[0],
                        shock_family=axis[1],
                        condition_bucket=axis[2],
                        horizons=spec.horizon_grid,
                        cells=tuple(index.get((*axis, h)) for h in spec.horizon_grid),
                    )
                )
    return ResponsePathResult(
        card_hash=spec.card_hash,
        relation_id=spec.relation_id,
        horizons=spec.horizon_grid,
        primary_horizon=spec.primary_horizon,
        plan_purge_horizon=plan.horizon_bdays,
        paths=tuple(paths),
        predictions=predictions,
        trials=tuple(budget.trials),
        trials_remaining=budget.remaining,
    )


# ------------------------------------------------------------------- functional
@dataclass(frozen=True, slots=True)
class ResponseTimeFunctional:
    """A response time as an interval (lo, hi] in sessions, a region, or unavailable."""

    kind: str | None
    status: str  # "interval" | "supported_region" | "unavailable"
    lower_session_exclusive: int | None
    upper_session_inclusive: int | None
    candidate_horizons: tuple[int, ...]
    band_kind: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.status not in ("interval", "supported_region", "unavailable"):
            raise ContractError(f"unknown functional status {self.status!r}")
        if self.status == "interval":
            lo, hi = self.lower_session_exclusive, self.upper_session_inclusive
            if lo is None or hi is None or hi - lo < 2:
                raise ContractError("a response-time functional never resolves to a single session")


def _unavailable(kind: str | None, reason: str, band_kind: str | None = None) -> ResponseTimeFunctional:
    return ResponseTimeFunctional(kind, "unavailable", None, None, (), band_kind, reason)


def _previous_grid(horizons: Sequence[int], horizon: int) -> int:
    earlier = [h for h in horizons if h < horizon]
    return max(earlier) if earlier else 0


def response_time_functional(
    path: Any,
    kind: str | None,
    *,
    band: Any = None,
    fraction: float | None = None,
    threshold: float | None = None,
) -> ResponseTimeFunctional:
    """Locate a response time WITHOUT ever naming one session.

    ``path`` exposes ``horizons`` and ``points``; ``band`` must be a
    simultaneous ``PathBand`` (a pointwise band cannot certify a path
    functional, C29).  ``kind=None`` (the v1 card) is ``unavailable``.
    """

    if kind is None:
        return _unavailable(None, NO_FUNCTIONAL_REASON)
    if kind not in FUNCTIONAL_KINDS:
        raise ContractError(f"unknown functional kind {kind!r}")
    if band is None:
        return _unavailable(kind, "no path band: a point path cannot locate a response time")
    if band.kind != "simultaneous":
        return _unavailable(kind, "a pointwise band cannot certify a path functional (C29)", band.kind)
    horizons = tuple(path.horizons)
    points = tuple(path.points)
    if tuple(band.horizons) != horizons:
        raise ContractError("band and path horizons differ")
    if any(p is None for p in points) or any(v is None for v in (*band.lower, *band.upper)):
        return _unavailable(kind, "an inadequate horizon on the path", band.kind)
    lower = np.asarray(band.lower, dtype=float)
    upper = np.asarray(band.upper, dtype=float)
    if not ((lower > 0) | (upper < 0)).any():
        return _unavailable(kind, "flat path: no horizon's simultaneous band excludes zero", band.kind)
    pts = np.asarray(points, dtype=float)
    sign = 1.0 if pts[int(np.argmax(np.abs(pts)))] >= 0 else -1.0
    lo_s, hi_s = (lower, upper) if sign > 0 else (-upper, -lower)
    if kind == "peak":
        floor = float(lo_s.max())
        candidates = tuple(h for h, top in zip(horizons, hi_s) if top >= floor)
        lo = _previous_grid(horizons, min(candidates))
        nxt = [h for h in horizons if h > max(candidates)]
        if len(candidates) == 1 and nxt:
            return ResponseTimeFunctional(
                kind, "interval", lo, nxt[0], candidates, band.kind,
                "peak bracketed by its neighbouring grid horizons",
            )
        return ResponseTimeFunctional(
            kind, "supported_region", lo, nxt[0] if nxt else None, candidates, band.kind,
            "horizons whose band cannot be excluded as the peak",
        )
    if kind == "time_to_fraction":
        if fraction is None or not 0 < fraction <= 1:
            raise ContractError("time_to_fraction needs 0 < fraction <= 1")
        level = float(fraction) * float((sign * pts).max())
    else:
        if threshold is None:
            raise ContractError("threshold_crossing needs a threshold")
        level = float(sign * threshold)
    possible = [h for h, top in zip(horizons, hi_s) if top >= level]
    sure = [h for h, bottom in zip(horizons, lo_s) if bottom >= level]
    if not possible:
        return _unavailable(kind, "the band never reaches the level on the grid", band.kind)
    lo = _previous_grid(horizons, possible[0])
    if not sure:
        return ResponseTimeFunctional(
            kind, "supported_region", lo, None, tuple(possible), band.kind,
            "level possibly reached; never certainly reached on the grid (right-censored)",
        )
    hi = sure[0]
    candidates = tuple(h for h in horizons if lo < h <= hi)
    if hi - lo < 2:
        return ResponseTimeFunctional(
            kind, "supported_region", lo, hi, candidates, band.kind,
            "grid too fine to report an interval wider than one session",
        )
    return ResponseTimeFunctional(
        kind, "interval", lo, hi, candidates, band.kind,
        "first crossing lies after the previous grid horizon and by the first certain one",
    )


# ------------------------------------------------------------------ delay cost
@dataclass(frozen=True)
class DelayCostTable:
    horizons: tuple[int, ...]
    delays_sessions: tuple[int, ...]
    rows: tuple[Mapping[str, Any], ...]
    note: str = DELAY_COST_NOTE


def _interpolate(horizons: Sequence[int], points: Sequence[float], k: int) -> float:
    xs = np.asarray((0, *horizons), dtype=float)
    ys = np.asarray((0.0, *points), dtype=float)
    if k > xs[-1]:
        raise ContractError("delay beyond the longest grid horizon")
    return float(np.interp(float(k), xs, ys))


def delay_cost_sensitivity(path: Any, delays_sessions: Sequence[int]) -> DelayCostTable:
    """Response remaining at each grid horizon H after acting k sessions late.

    ``remaining(k, H) = R(H) - R(k)``; ``R(k)`` is linear between grid horizons
    with ``R(0) = 0`` (detection).  Rows with ``k >= H`` are omitted.
    """

    horizons = tuple(path.horizons)
    points = tuple(path.points)
    if any(p is None for p in points):
        raise ContractError("delay cost needs an estimate at every grid horizon")
    delays = tuple(sorted({int(k) for k in delays_sessions}))
    if not delays or delays[0] < 0:
        raise ContractError("delays must be non-negative sessions")
    rows = []
    for k in delays:
        forgone = _interpolate(horizons, points, k)
        for horizon, value in zip(horizons, points):
            if k >= horizon:
                continue
            remaining = float(value) - forgone
            rows.append(
                {
                    "delay_sessions": k,
                    "horizon": horizon,
                    "response_at_horizon": float(value),
                    "response_forgone": forgone,
                    "response_remaining": remaining,
                    "share_remaining": (remaining / float(value)) if float(value) != 0 else None,
                }
            )
    return DelayCostTable(horizons=horizons, delays_sessions=delays, rows=tuple(rows))
