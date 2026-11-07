"""GLT T16: episode-block path inference (C28/C29).

Rows are never events.  The card's block rule is "one shock episode is one
block; every row an episode generates (horizon, target) shares that block".
``episode_blocks`` builds those blocks with the existing honest-N helper
``effective_episode_dates`` at the card's purge length, and shocks whose
windows overlap a retained episode travel WITH that episode's block (they are
never counted as independent confirmation, and never silently dropped).

``block_bootstrap_path`` resamples whole blocks and returns two DIFFERENT
objects (C29):

* a pointwise band (per-horizon studentised quantile), which may describe a
  single horizon but never certifies a path claim, and
* a simultaneous sup-t band over the whole horizon grid, whose critical value is
  the quantile of the per-draw maximum of the studentised deviations.

Every draw used is defined at every horizon, so the sup-t critical value is
never below a pointwise one and the simultaneous band contains the pointwise
band at every horizon by construction.

``episode_influence`` reports leave-one-episode-out and leave-one-era-out
deltas, the largest single-episode share and the era concentration.
``path_multiplicity`` / ``incremental_skill`` reuse the existing
``apply_bh_fdr`` / ``score_incremental_predictions`` boundaries by reference; a
missing canonical judge is an abstention carrying the exact
``StatisticalDependencyUnavailable`` text, never a fabricated p-value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from brain.liquidity_lab.baselines import score_paired
from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation
from brain.liquidity_lab.validation import (
    StatisticalDependencyUnavailable,
    WalkForwardPrediction,
    apply_bh_fdr,
    effective_episode_dates,
)

BAND_KINDS = ("pointwise", "simultaneous")
BOOTSTRAP_METHOD = "episode_block_bootstrap_studentised"


class InadequateBlocks(ContractError):
    """Too few independent episode blocks to state an uncertainty band."""


# ----------------------------------------------------------------------- blocks
@dataclass(frozen=True, slots=True)
class EpisodeBlock:
    block_id: str
    anchor: date
    shock_ids: tuple[str, ...]
    n_rows: int


@dataclass(frozen=True)
class EpisodeBlocks:
    blocks: tuple[EpisodeBlock, ...]
    n_rows: int
    n_shocks: int
    purge_sessions: int

    @property
    def n_episodes_effective(self) -> int:
        return len(self.blocks)

    def block_of(self) -> dict[str, str]:
        return {shock: block.block_id for block in self.blocks for shock in block.shock_ids}


def episode_blocks(
    observations: Sequence[ForwardReturnObservation], *, purge_sessions: int
) -> EpisodeBlocks:
    """One block per retained episode; overlapping shocks join the episode they overlap."""

    if purge_sessions < 1:
        raise ContractError("purge_sessions must be positive")
    anchors: dict[str, date] = {}
    counts: dict[str, int] = {}
    for row in observations:
        current = anchors.get(row.shock_id)
        if current is None or row.anchor_session < current:
            anchors[row.shock_id] = row.anchor_session
        counts[row.shock_id] = counts.get(row.shock_id, 0) + 1
    if not anchors:
        return EpisodeBlocks(blocks=(), n_rows=0, n_shocks=0, purge_sessions=purge_sessions)
    kept = effective_episode_dates(anchors.values(), horizon_bdays=purge_sessions)
    members: dict[date, list[str]] = {day: [] for day in kept}
    for shock_id, anchor in anchors.items():
        owner = max(day for day in kept if day <= anchor)
        members[owner].append(shock_id)
    blocks = tuple(
        EpisodeBlock(
            block_id=f"episode:{day.isoformat()}",
            anchor=day,
            shock_ids=tuple(sorted(members[day])),
            n_rows=sum(counts[s] for s in members[day]),
        )
        for day in kept
    )
    return EpisodeBlocks(
        blocks=blocks,
        n_rows=sum(counts.values()),
        n_shocks=len(anchors),
        purge_sessions=purge_sessions,
    )


def _filtered(observations, *, target_id, shock_family):
    return [
        row
        for row in observations
        if (target_id is None or row.target_id == target_id)
        and (shock_family is None or row.shock_family == shock_family)
    ]


def _block_matrix(
    observations: Sequence[ForwardReturnObservation],
    blocks: EpisodeBlocks,
    horizons: Sequence[int],
) -> np.ndarray:
    """V[b, h]: mean over the block's shocks of each shock's mean row at h (NaN if none)."""

    per_shock: dict[tuple[str, int], list[float]] = {}
    for row in observations:
        per_shock.setdefault((row.shock_id, row.horizon_bdays), []).append(float(row.forward_return))
    matrix = np.full((len(blocks.blocks), len(horizons)), np.nan)
    for b, block in enumerate(blocks.blocks):
        for j, horizon in enumerate(horizons):
            means = [
                float(np.mean(per_shock[(shock, horizon)]))
                for shock in block.shock_ids
                if (shock, horizon) in per_shock
            ]
            if means:
                matrix[b, j] = float(np.mean(means))
    return matrix


# ------------------------------------------------------------------------ bands
@dataclass(frozen=True)
class PathBand:
    kind: str
    horizons: tuple[int, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    level: float
    n_blocks: int
    n_episodes_effective: int
    n_rows: int
    n_draws: int
    method: str
    critical_values: tuple[float, ...]
    n_blocks_by_horizon: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in BAND_KINDS:
            raise ContractError(f"unknown band kind {self.kind!r}")
        if not (len(self.horizons) == len(self.lower) == len(self.upper)):
            raise ContractError("band arrays must align with its horizons")
        if not 0 < self.level < 1:
            raise ContractError("band level must be in (0, 1)")

    @property
    def certifies_path(self) -> bool:
        """Only a simultaneous band may support a statement about the whole path (C29)."""

        return self.kind == "simultaneous"


@dataclass(frozen=True)
class BootstrapPath:
    horizons: tuple[int, ...]
    point: tuple[float, ...]
    pointwise: PathBand
    simultaneous: PathBand
    blocks: EpisodeBlocks


def block_bootstrap_path(
    observations: Sequence[ForwardReturnObservation],
    *,
    horizons: Sequence[int],
    purge_sessions: int,
    target_id: str | None = None,
    shock_family: str | None = None,
    n_draws: int = 2000,
    level: float = 0.90,
    seed: int = 0,
    min_blocks: int = 2,
) -> BootstrapPath:
    """Resample whole episode blocks; return the pointwise AND the sup-t band."""

    if n_draws < 100:
        raise ContractError("n_draws must be at least 100")
    if not 0 < level < 1:
        raise ContractError("level must be in (0, 1)")
    horizons = tuple(int(h) for h in horizons)
    rows = _filtered(observations, target_id=target_id, shock_family=shock_family)
    rows = [r for r in rows if r.horizon_bdays in horizons]
    blocks = episode_blocks(rows, purge_sessions=purge_sessions)
    matrix = _block_matrix(rows, blocks, horizons)
    support = tuple(int(np.sum(~np.isnan(matrix[:, j]))) for j in range(len(horizons)))
    thin = [h for h, n in zip(horizons, support) if n < min_blocks]
    if thin:
        raise InadequateBlocks(
            f"horizons {thin} have fewer than {min_blocks} independent episode blocks "
            f"(n_episodes_effective={blocks.n_episodes_effective}, n_rows={blocks.n_rows})"
        )
    point = np.nanmean(matrix, axis=0)
    n_blocks = matrix.shape[0]
    rng = np.random.default_rng(seed)
    index = rng.integers(0, n_blocks, size=(n_draws, n_blocks))
    sample = matrix[index]  # (draws, blocks, horizons)
    present = ~np.isnan(sample)
    totals = np.where(present, sample, 0.0).sum(axis=1)
    counts = present.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = totals / counts
    complete = ~np.isnan(draws).any(axis=1)
    draws = draws[complete]
    if draws.shape[0] < n_draws // 2:
        raise InadequateBlocks("fewer than half the bootstrap draws define every horizon")
    sd = draws.std(axis=0, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t_stats = np.where(sd > 0, np.abs(draws - point) / np.where(sd > 0, sd, 1.0), 0.0)
    pointwise_q = np.quantile(t_stats, level, axis=0)
    sup_c = float(np.quantile(t_stats.max(axis=1), level))
    common = dict(
        horizons=horizons,
        level=float(level),
        n_blocks=int(n_blocks),
        n_episodes_effective=blocks.n_episodes_effective,
        n_rows=blocks.n_rows,
        n_draws=int(draws.shape[0]),
        method=BOOTSTRAP_METHOD,
        n_blocks_by_horizon=support,
    )
    pointwise = PathBand(
        kind="pointwise",
        lower=tuple(float(v) for v in point - pointwise_q * sd),
        upper=tuple(float(v) for v in point + pointwise_q * sd),
        critical_values=tuple(float(v) for v in pointwise_q),
        **common,
    )
    simultaneous = PathBand(
        kind="simultaneous",
        lower=tuple(float(v) for v in point - sup_c * sd),
        upper=tuple(float(v) for v in point + sup_c * sd),
        critical_values=(sup_c,) * len(horizons),
        **common,
    )
    return BootstrapPath(
        horizons=horizons,
        point=tuple(float(v) for v in point),
        pointwise=pointwise,
        simultaneous=simultaneous,
        blocks=blocks,
    )


# -------------------------------------------------------------------- influence
@dataclass(frozen=True)
class EpisodeInfluence:
    horizons: tuple[int, ...]
    primary_horizon: int
    full_path: tuple[float, ...]
    loeo: Mapping[str, tuple[float, ...]]
    most_influential_block: str
    most_influential_shocks: tuple[str, ...]
    max_episode_share: tuple[float | None, ...]
    loera: Mapping[str, tuple[float, ...]]
    most_influential_era: str
    era_concentration: float | None
    n_episodes_effective: int


def _calendar_year(block: EpisodeBlock) -> str:
    return str(block.anchor.year)


def episode_influence(
    observations: Sequence[ForwardReturnObservation],
    *,
    horizons: Sequence[int],
    purge_sessions: int,
    primary_horizon: int,
    era_of: Callable[[EpisodeBlock], str] | None = None,
    target_id: str | None = None,
    shock_family: str | None = None,
) -> EpisodeInfluence:
    """Leave-one-episode-out and leave-one-era-out deltas on the block-mean path."""

    horizons = tuple(int(h) for h in horizons)
    if primary_horizon not in horizons:
        raise ContractError("primary horizon is not on the path grid")
    era_of = era_of or _calendar_year
    rows = _filtered(observations, target_id=target_id, shock_family=shock_family)
    rows = [r for r in rows if r.horizon_bdays in horizons]
    blocks = episode_blocks(rows, purge_sessions=purge_sessions)
    if blocks.n_episodes_effective < 2:
        raise InadequateBlocks("influence needs at least two independent episode blocks")
    matrix = _block_matrix(rows, blocks, horizons)
    full = np.nanmean(matrix, axis=0)
    p = horizons.index(primary_horizon)

    def _without(mask: np.ndarray) -> np.ndarray:
        kept = matrix[~mask]
        with np.errstate(invalid="ignore"):
            return np.array(
                [np.nanmean(col) if np.any(~np.isnan(col)) else np.nan for col in kept.T]
            )

    loeo: dict[str, tuple[float, ...]] = {}
    for b, block in enumerate(blocks.blocks):
        mask = np.zeros(len(blocks.blocks), dtype=bool)
        mask[b] = True
        loeo[block.block_id] = tuple(float(v) for v in _without(mask) - full)
    ranked = sorted(
        loeo,
        key=lambda k: (-(abs(loeo[k][p]) if np.isfinite(loeo[k][p]) else -1.0), k),
    )
    top = ranked[0]
    shares: list[float | None] = []
    for j in range(len(horizons)):
        col = np.abs(matrix[:, j][~np.isnan(matrix[:, j])])
        shares.append(float(col.max() / col.sum()) if col.size and col.sum() > 0 else None)
    eras = [era_of(block) for block in blocks.blocks]
    loera: dict[str, tuple[float, ...]] = {}
    for era in sorted(set(eras)):
        mask = np.array([e == era for e in eras])
        loera[era] = tuple(float(v) for v in _without(mask) - full)
    top_era = sorted(
        loera,
        key=lambda k: (-(abs(loera[k][p]) if np.isfinite(loera[k][p]) else -1.0), k),
    )[0]
    primary_col = matrix[:, p]
    weights = np.abs(np.nan_to_num(primary_col, nan=0.0))
    if weights.sum() > 0:
        by_era: dict[str, float] = {}
        for era, weight in zip(eras, weights):
            by_era[era] = by_era.get(era, 0.0) + float(weight)
        concentration: float | None = max(by_era.values()) / float(weights.sum())
    else:
        concentration = None
    top_block = next(b for b in blocks.blocks if b.block_id == top)
    return EpisodeInfluence(
        horizons=horizons,
        primary_horizon=primary_horizon,
        full_path=tuple(float(v) for v in full),
        loeo=loeo,
        most_influential_block=top,
        most_influential_shocks=top_block.shock_ids,
        max_episode_share=tuple(shares),
        loera=loera,
        most_influential_era=top_era,
        era_concentration=concentration,
        n_episodes_effective=blocks.n_episodes_effective,
    )


# ------------------------------------------------- multiplicity and skill (reuse)
def _abstention(exc: StatisticalDependencyUnavailable) -> str:
    return f"StatisticalDependencyUnavailable: {exc}"


def path_multiplicity(
    p_values: Mapping[str, float],
    *,
    alpha: float,
    fdr_fn: Callable[..., Mapping[str, Mapping[str, object]]] | None = None,
) -> dict[str, Any]:
    """BH-FDR over the path's tests through the existing ``apply_bh_fdr`` boundary."""

    try:
        adjusted = apply_bh_fdr(p_values, alpha=alpha, fdr_fn=fdr_fn)
    except StatisticalDependencyUnavailable as exc:
        return {"status": "abstained", "abstention_reason": _abstention(exc), "adjusted": None}
    return {"status": "adjusted", "abstention_reason": None, "adjusted": adjusted}


def incremental_skill(
    candidate: Sequence[WalkForwardPrediction],
    comparator: Sequence[WalkForwardPrediction],
    *,
    mean_test_fn: Callable[..., Mapping[str, object]] | None = None,
) -> dict[str, Any]:
    """Paired incremental score via ``score_paired``; SDU becomes an abstention, never a p."""

    try:
        scored = dict(score_paired(candidate, comparator, mean_test_fn=mean_test_fn))
    except StatisticalDependencyUnavailable as exc:
        return {
            "status": "abstained",
            "p_value": None,
            "mean_squared_error_improvement": None,
            "abstention_reason": _abstention(exc),
        }
    scored.setdefault("abstention_reason", None)
    return scored
