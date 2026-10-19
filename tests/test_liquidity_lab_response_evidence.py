"""GLT T16 section 5 read projection: exact fields, receipts, null cells, path claims.

Named cases:
* section 5 -- ``test_projection_fields_equal_section5_exactly``
* no causal estimand -- ``test_t16_emits_no_causal_estimand``
* null -- ``test_null_cell_carries_no_effect_estimate``
* pointwise -- ``test_pointwise_projection_cannot_claim_a_path``
* hygiene -- ``test_t16_modules_import_no_network_macro_engine_or_ledger``
"""

from __future__ import annotations

import ast
import math
from dataclasses import fields, replace
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pytest

from brain.liquidity_lab.contracts import TARGET_BY_ID, ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation, ResponseCurveCell
from brain.liquidity_lab.path_inference import block_bootstrap_path
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.response_evidence import (
    SECTION5_FIELDS,
    IdentificationReceiptMissing,
    ResponseEvidenceProjection,
    coverage_record,
    project_cell,
)
from brain.liquidity_lab.response_path import ResponsePathSpec

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json"
RELATION = "glt_rel_monetary_impulse_to_broad_targets.v1"
GRID = (5, 20, 60)
T16_MODULES = ("response_path.py", "path_inference.py", "response_evidence.py")

# CONTRACTS section 5, transcribed literally (never derived from the code under test).
LITERAL_SECTION5 = (
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


@pytest.fixture(scope="module")
def spec():
    return ResponsePathSpec.from_card(load_card(CARD_PATH))


def _cell(**over):
    base = ResponseCurveCell(
        target_id="spy",
        shock_family="glt_composite",
        condition_bucket="all",
        horizon_bdays=20,
        sample_n=30,
        effective_n=14,
        raw_mean=0.0041,
        shrunk_mean=0.0036,
        interval_low=-0.0010,
        interval_high=0.0082,
        prior_mean=0.0020,
        prior_effective_n=40,
        evidence_state="estimated",
    )
    return replace(base, **over)


def _bands():
    rng = np.random.default_rng(11)
    rows = []
    for i in range(24):
        detected = np.busday_offset("2008-01-07", 70 * i, roll="forward").astype(date)
        anchor = np.busday_offset(detected.isoformat(), 1, roll="forward").astype(date)
        for h in GRID:
            rows.append(
                ForwardReturnObservation(
                    shock_id=f"liq_{i:03d}",
                    first_detected=datetime.combine(detected, time(21, 0)),
                    target_id="spy",
                    asset_class=TARGET_BY_ID["spy"].asset_class,
                    hierarchy_parent=TARGET_BY_ID["spy"].hierarchy_parent,
                    shock_family="glt_composite",
                    shock_type="composite_z",
                    horizon_bdays=h,
                    anchor_session=anchor,
                    exit_session=np.busday_offset(anchor.isoformat(), h, roll="forward").astype(date),
                    forward_return=0.003 * math.sqrt(h / 20) + float(rng.normal(0, 0.006)),
                    conditions={},
                )
            )
    return block_bootstrap_path(rows, horizons=GRID, purge_sessions=60, n_draws=400)


def _project(spec, cell, **over):
    kwargs = dict(
        spec=spec,
        shock_definition="evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66",
        target_calendar="XNYS",
        return_basis="total_return_fixture",
        currency="USD",
        train_cutoff=date(2017, 12, 29),
        coverage=coverage_record(59, 60),
        model_version="glt_t14_m1.v1",
    )
    kwargs.update(over)
    return project_cell(cell, **kwargs)


def test_projection_fields_equal_section5_exactly(spec):
    assert SECTION5_FIELDS == LITERAL_SECTION5
    assert tuple(f.name for f in fields(ResponseEvidenceProjection)) == LITERAL_SECTION5
    record = _project(spec, _cell()).as_record()
    assert tuple(record) == LITERAL_SECTION5
    assert "path_claim_allowed" not in record  # a property, never a sixth-of-section field


def test_projection_reads_relation_protocol_and_tier_from_the_cards(spec):
    out = _project(spec, _cell())
    assert out.relation_id == RELATION
    assert out.protocol == "walk_forward_one_plan_purge60@da060bf4"
    assert out.estimand_kind == "predictive_response"
    assert out.identification_status == "NOT_IDENTIFIED" == spec.treatment_identification_status
    assert spec.identification_status == "association_only"  # interpretation, carried in the assumptions
    assert out.evidence_tier == "research_measurement_only"
    assert out.identification_assumptions[0].startswith("none: association only")


def test_t16_emits_no_causal_estimand(spec):
    with pytest.raises(IdentificationReceiptMissing, match="T17 owns the identification receipt"):
        _project(spec, _cell(), estimand_kind="causal_response")
    with pytest.raises(TypeError):  # no receipt parameter exists in T16
        _project(spec, _cell(), identification_receipt={"receipt_id": "r1", "relation_id": RELATION})
    record = _project(spec, _cell()).as_record()
    for label in ("causal (model-labelled)", "identified_by_receipt:r1", "NOT_IDENTIFIED"):
        with pytest.raises(IdentificationReceiptMissing, match="a causal label creates none"):
            ResponseEvidenceProjection(**{**record, "estimand_kind": "causal_response", "identification_status": label})
    for status in ("association_only", "identified_by_receipt:r1"):
        with pytest.raises(ContractError, match="NOT_IDENTIFIED"):
            ResponseEvidenceProjection(**{**record, "identification_status": status})
    with pytest.raises(ContractError, match="T17 work"):
        _project(replace(spec, treatment_identification_status="IDENTIFIED"), _cell())


@pytest.mark.parametrize(
    "over",
    [
        {"effective_n": 4},
        {"shrunk_mean": None, "interval_low": None, "interval_high": None},
        {"evidence_state": "insufficient"},
    ],
)
def test_null_cell_carries_no_effect_estimate(spec, over):
    out = _project(spec, _cell(**over), band=_bands().simultaneous, increment={"p_value": 0.01})
    assert out.effect_estimate is None
    assert out.uncertainty_kind == "none"
    assert out.interval_or_band["lower"] is None and out.interval_or_band["upper"] is None
    assert "min_effective_n=10" in out.abstention_reason
    assert out.path_claim_allowed is False
    with pytest.raises(ContractError, match="abstention_reason"):
        ResponseEvidenceProjection(**{**out.as_record(), "abstention_reason": None})


def test_a_band_with_too_few_purged_episodes_nulls_the_cell(spec):
    band = replace(_bands().simultaneous, n_episodes_effective=8)
    out = _project(spec, _cell(effective_n=14), band=band)
    assert out.effect_estimate is None and out.uncertainty_kind == "none"
    assert out.independent_episode_count == 8
    assert "independent_episode_count=8" in out.abstention_reason
    assert "min_effective_n=10" in out.abstention_reason


def test_pointwise_projection_cannot_claim_a_path(spec):
    boot = _bands()
    bare = _project(spec, _cell())
    pointwise = _project(spec, _cell(), band=boot.pointwise)
    simultaneous = _project(spec, _cell(), band=boot.simultaneous)
    assert bare.uncertainty_kind == "pointwise" and bare.path_claim_allowed is False
    assert pointwise.uncertainty_kind == "pointwise" and pointwise.path_claim_allowed is False
    assert simultaneous.uncertainty_kind == "simultaneous" and simultaneous.path_claim_allowed is True
    assert pointwise.interval_or_band["path_horizons"] == GRID
    assert simultaneous.independent_episode_count == boot.simultaneous.n_episodes_effective == 24
    with pytest.raises(ContractError, match="must equal uncertainty_kind"):
        ResponseEvidenceProjection(**{**pointwise.as_record(), "uncertainty_kind": "simultaneous"})


def test_borrowed_and_target_support_stay_separately_visible(spec):
    out = _project(spec, _cell(effective_n=12, prior_effective_n=40))
    assert (out.target_support, out.borrowed_support) == (12, 40)
    assert out.interval_or_band["target_support_effective_n"] == 12
    assert out.interval_or_band["borrowed_prior_effective_n"] == 40
    null = _project(spec, _cell(effective_n=3, prior_effective_n=55))
    assert (null.target_support, null.borrowed_support) == (3, 55)


def test_insufficient_coverage_reports_no_p_value(spec):
    increment = {"comparator": "direct_funding", "status": "admissible_for_review", "p_value": 0.01, "secret": 1}
    thin = _project(spec, _cell(), coverage=coverage_record(7, 10), increment=increment)
    assert thin.coverage["sufficient"] is False
    assert thin.baseline_comparison["status"] == "insufficient_coverage"
    assert thin.baseline_comparison["p_value"] is None
    full = _project(spec, _cell(), coverage=coverage_record(59, 60), increment=increment)
    assert full.baseline_comparison == {
        "comparator": "direct_funding",
        "status": "admissible_for_review",
        "p_value": 0.01,
    }
    assert _project(spec, _cell()).baseline_comparison["status"] == "not_scored"
    with pytest.raises(ContractError):
        coverage_record(11, 10)


def test_off_grid_cells_and_bands_are_refused(spec):
    with pytest.raises(ContractError, match="not on the card grid"):
        _project(spec, _cell(horizon_bdays=10))


# ------------------------------------------------------------------ hygiene
_FORBIDDEN_ROOTS = ("requests", "yfinance", "urllib", "macro", "engine", "httpx", "aiohttp")


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("module", T16_MODULES)
def test_t16_modules_import_no_network_macro_engine_or_ledger(module):
    names = _imports(REPO / "brain" / "liquidity_lab" / module)
    assert names
    for name in names:
        assert name.split(".")[0] not in _FORBIDDEN_ROOTS, (module, name)
        assert "ledger" not in name.split("."), (module, name)
        assert "adapter" not in name.split("."), (module, name)
