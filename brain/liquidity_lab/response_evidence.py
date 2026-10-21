"""GLT T16: the CONTRACTS section 5 additive response-evidence read projection.

``ResponseCurveCell`` is NOT replaced.  ``ResponseEvidenceProjection`` is an
additive, read-only view built from an existing cell, an optional ``PathBand``
and an optional incremental-score result, with EXACTLY the section 5 fields in
the section 5 order (``SECTION5_FIELDS``).  Rules enforced here:

* T16 emits NO causal estimand.  The only estimand kind is
  ``predictive_response`` and ``identification_status`` is the card's
  treatment status ``NOT_IDENTIFIED``.  A causal label is refused outright
  and no identification receipt is accepted: T17 owns the receipt.
* ``uncertainty_kind="pointwise"`` carries ``interval_or_band["kind"] ==
  "pointwise"`` and ``path_claim_allowed`` is False: a pointwise band is never
  drawn as a simultaneous path band nor used to assert a response time.
  ``path_claim_allowed`` is a property, so the field tuple stays exact.
* Borrowed prior support and target support stay separately visible.
* Null/inadequate cells carry NO ``effect_estimate``, no interval and an
  ``abstention_reason``.  The floor is the card's ``min_effective_n`` applied to
  the most conservative independent count reported (the band's purged
  ``n_episodes_effective`` when a band is supplied, else the cell's own).

Nothing here reads a price, writes a ledger or serves a reader.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from typing import Any, Mapping, Sequence

from brain.liquidity_lab.baselines import card_hash_prefix
from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.estimator import ResponseCurveCell
from brain.liquidity_lab.path_inference import PathBand
from brain.liquidity_lab.response_path import ResponsePathSpec

SECTION5_FIELDS = (
    "relation_id",
    "target_id",
    "shock_definition",
    "estimand_kind",
    "horizon",
    "target_calendar",
    "return_basis",
    "currency",
    "conditioning_information",
    "model_version",
    "protocol",
    "train_cutoff",
    "coverage",
    "independent_episode_count",
    "effect_estimate",
    "uncertainty_kind",
    "interval_or_band",
    "identification_assumptions",
    "identification_status",
    "baseline_comparison",
    "evidence_tier",
    "abstention_reason",
)
ESTIMAND_KINDS = ("predictive_response",)  # T16 emits no causal estimand (T17 owns identification)
T16_IDENTIFICATION_STATUS = "NOT_IDENTIFIED"
CAUSAL_REFUSAL = (
    "a causal estimand is not emitted by T16: T17 owns the identification receipt and none exists; "
    "a causal label creates none"
)
UNCERTAINTY_KINDS = ("pointwise", "simultaneous", "none")
# glt_estimand_card.v1: evidence_tier research_measurement_only.
DEFAULT_EVIDENCE_TIER = "research_measurement_only"
DEFAULT_IDENTIFICATION_ASSUMPTIONS = (
    "none: association only; glt_estimand_card.v1 identification_status association_only, "
    "treatment identification_status NOT_IDENTIFIED; no identification receipt exists (T17)",
)
COVERAGE_FLOOR = 0.80  # card coverage_denominator: below 0.80 the comparison is insufficient


class IdentificationReceiptMissing(ContractError):
    """A causal estimand was requested; T16 emits none (T17 owns the identification receipt)."""


@dataclass(frozen=True)
class ResponseEvidenceProjection:
    relation_id: str
    target_id: str
    shock_definition: str
    estimand_kind: str
    horizon: int
    target_calendar: str
    return_basis: str
    currency: str
    conditioning_information: Mapping[str, Any]
    model_version: str
    protocol: str
    train_cutoff: date
    coverage: Mapping[str, Any]
    independent_episode_count: int
    effect_estimate: float | None
    uncertainty_kind: str
    interval_or_band: Mapping[str, Any]
    identification_assumptions: tuple[str, ...]
    identification_status: str
    baseline_comparison: Mapping[str, Any]
    evidence_tier: str
    abstention_reason: str | None

    def __post_init__(self) -> None:
        if "causal" in self.estimand_kind:
            raise IdentificationReceiptMissing(CAUSAL_REFUSAL)
        if self.estimand_kind not in ESTIMAND_KINDS:
            raise ContractError(f"unknown estimand_kind {self.estimand_kind!r}")
        if self.identification_status != T16_IDENTIFICATION_STATUS:
            raise ContractError(
                f"a T16 projection carries identification_status {T16_IDENTIFICATION_STATUS}; "
                f"got {self.identification_status!r}"
            )
        if self.uncertainty_kind not in UNCERTAINTY_KINDS:
            raise ContractError(f"unknown uncertainty_kind {self.uncertainty_kind!r}")
        band_kind = self.interval_or_band.get("kind")
        if self.uncertainty_kind != "none" and band_kind != self.uncertainty_kind:
            raise ContractError("interval_or_band kind must equal uncertainty_kind")
        if self.effect_estimate is None:
            if not self.abstention_reason:
                raise ContractError("a null cell must state its abstention_reason")
            if self.uncertainty_kind != "none" or self.interval_or_band.get("lower") is not None:
                raise ContractError("a null cell carries no interval, band or mean")
        elif self.abstention_reason is not None:
            raise ContractError("an estimated cell carries no abstention_reason")

    @property
    def path_claim_allowed(self) -> bool:
        """Only a simultaneous band on an estimated cell may support a path claim (C29)."""

        return (
            self.effect_estimate is not None
            and self.uncertainty_kind == "simultaneous"
            and self.interval_or_band.get("kind") == "simultaneous"
        )

    @property
    def target_support(self) -> int:
        return int(self.interval_or_band.get("target_support_effective_n", 0))

    @property
    def borrowed_support(self) -> int:
        return int(self.interval_or_band.get("borrowed_prior_effective_n", 0))

    def as_record(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in SECTION5_FIELDS}


assert tuple(f.name for f in fields(ResponseEvidenceProjection)) == SECTION5_FIELDS


def coverage_record(paired: int, denominator: int, *, floor: float = COVERAGE_FLOOR) -> dict[str, Any]:
    """The card's coverage = paired / denominator; below the floor the comparison is insufficient."""

    if denominator <= 0 or paired < 0 or paired > denominator:
        raise ContractError("coverage needs 0 <= paired <= denominator and denominator > 0")
    ratio = paired / denominator
    return {
        "paired": int(paired),
        "denominator": int(denominator),
        "ratio": ratio,
        "floor": floor,
        "sufficient": ratio >= floor,
    }


def _comparison(increment: Mapping[str, Any] | None, coverage: Mapping[str, Any]) -> dict[str, Any]:
    if increment is None:
        return {"status": "not_scored", "p_value": None, "abstention_reason": "no comparator scored"}
    if not coverage.get("sufficient", False):
        return {
            "status": "insufficient_coverage",
            "p_value": None,
            "abstention_reason": f"coverage {coverage.get('ratio')} below floor {coverage.get('floor')}",
        }
    keep = (
        "comparator",
        "status",
        "p_value",
        "mean_squared_error_improvement",
        "effective_n",
        "n_paired_rows",
        "paired_keys",
        "reason",
        "abstention_reason",
    )
    return {key: increment.get(key) for key in keep if key in increment}


def project_cell(
    cell: ResponseCurveCell,
    *,
    spec: ResponsePathSpec,
    shock_definition: str,
    target_calendar: str,
    return_basis: str,
    currency: str,
    train_cutoff: date,
    coverage: Mapping[str, Any],
    model_version: str,
    band: PathBand | None = None,
    increment: Mapping[str, Any] | None = None,
    estimand_kind: str = "predictive_response",
    identification_assumptions: Sequence[str] = DEFAULT_IDENTIFICATION_ASSUMPTIONS,
    evidence_tier: str = DEFAULT_EVIDENCE_TIER,
    partition: str = "all",
) -> ResponseEvidenceProjection:
    """Project one existing cell (plus an optional band) onto the section 5 fields."""

    if "causal" in estimand_kind:
        raise IdentificationReceiptMissing(CAUSAL_REFUSAL)
    if estimand_kind not in ESTIMAND_KINDS:
        raise ContractError(f"unknown estimand_kind {estimand_kind!r}")
    status = spec.treatment_identification_status
    if status != T16_IDENTIFICATION_STATUS:
        raise ContractError(
            f"card treatment identification_status {status!r} is not {T16_IDENTIFICATION_STATUS}; "
            "a change of identification status is T17 work"
        )
    if cell.horizon_bdays not in spec.horizon_grid:
        raise ContractError("cell horizon is not on the card grid")
    support = {
        "target_support_effective_n": int(cell.effective_n),
        "borrowed_prior_effective_n": int(cell.prior_effective_n),
    }
    conditioning = {
        "condition_bucket": cell.condition_bucket,
        "declared_condition_keys": spec.condition_keys,
        "partition": partition,
        "shock_family": cell.shock_family,
    }
    # The binding independent count is the most conservative one reported: the
    # band's purged episode count when a band is supplied, else the cell's own.
    independent = int(cell.effective_n) if band is None else min(int(cell.effective_n), band.n_episodes_effective)
    null = (
        cell.shrunk_mean is None
        or cell.evidence_state == "insufficient"
        or independent < spec.min_effective_n
    )
    common = dict(
        relation_id=spec.relation_id,
        target_id=cell.target_id,
        shock_definition=shock_definition,
        estimand_kind=estimand_kind,
        horizon=int(cell.horizon_bdays),
        target_calendar=target_calendar,
        return_basis=return_basis,
        currency=currency,
        conditioning_information=conditioning,
        model_version=model_version,
        protocol=f"walk_forward_one_plan_purge{spec.purge_sessions}@{card_hash_prefix(spec.card_hash)}",
        train_cutoff=train_cutoff,
        coverage=dict(coverage),
        identification_assumptions=tuple(identification_assumptions),
        identification_status=status,
        baseline_comparison=_comparison(increment, coverage),
        evidence_tier=evidence_tier,
    )
    if null:
        return ResponseEvidenceProjection(
            **common,
            independent_episode_count=independent,
            effect_estimate=None,
            uncertainty_kind="none",
            interval_or_band={"kind": None, "lower": None, "upper": None, **support},
            abstention_reason=(
                f"inadequate independent support: independent_episode_count={independent} "
                f"(cell effective_n={cell.effective_n}) against the card floor "
                f"min_effective_n={spec.min_effective_n} (evidence_state={cell.evidence_state})"
            ),
        )
    if band is not None:
        if cell.horizon_bdays not in band.horizons:
            raise ContractError("band does not cover the cell horizon")
        j = band.horizons.index(cell.horizon_bdays)
        interval = {
            "kind": band.kind,
            "level": band.level,
            "lower": band.lower[j],
            "upper": band.upper[j],
            "path_horizons": band.horizons,
            "method": band.method,
            "n_blocks": band.n_blocks,
            "n_rows": band.n_rows,
            **support,
        }
        episodes = band.n_episodes_effective
        kind = band.kind
    else:
        interval = {
            "kind": "pointwise",
            "level": None,
            "lower": cell.interval_low,
            "upper": cell.interval_high,
            "path_horizons": (cell.horizon_bdays,),
            "method": "response_curve_cell_interval",
            **support,
        }
        episodes = int(cell.effective_n)
        kind = "pointwise"
    return ResponseEvidenceProjection(
        **common,
        independent_episode_count=int(episodes),
        effect_estimate=float(cell.shrunk_mean),
        uncertainty_kind=kind,
        interval_or_band=interval,
        abstention_reason=None,
    )
