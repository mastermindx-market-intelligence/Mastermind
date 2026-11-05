from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from brain.liquidity_lab.contracts import (
    HORIZONS_BDAYS,
    TARGETS,
    ContractError,
    ForwardForecast,
    SourceStateRef,
    build_shock_record,
)


def _source(**overrides) -> SourceStateRef:
    payload = {
        "observed_at": "2026-08-20T13:30:00Z",
        "known_at": "2026-08-20T14:00:00Z",
        "source_snapshot_hash": "a" * 64,
        "model_version": "glt_state_1",
        "data_version": "pit_1",
        "state_family": "orthogonalised_impulse",
        "shock_type": "monetary_easing",
        "direction": 1,
        "magnitude_z": 1.4,
        "breadth": 0.67,
        "quality": "benign",
        "confidence": 0.8,
        "coverage": 0.75,
        "freshness": "fresh",
        "conditions": {"dxy": "falling", "credit": "stable"},
        "regional_gates": {"china_gate": "unknown"},
        "component_snapshot": {"fed": {"contribution": 0.4}},
    }
    payload.update(overrides)
    return SourceStateRef.from_mapping(payload)


def test_target_and_horizon_registries_are_precommitted_and_unique():
    assert HORIZONS_BDAYS == (1, 5, 10, 20, 40, 60, 90, 120)
    ids = [target.target_id for target in TARGETS]
    assert len(ids) == len(set(ids))
    assert all(target.benchmark is None or target.benchmark in ids for target in TARGETS)
    assert {"btc", "spy", "qqq", "smh", "tlt", "hyg", "gld", "eem", "fxi", "mchi", "kweb", "baba"} <= set(ids)
    assert next(target for target in TARGETS if target.target_id == "baba").role == "single_name"


def test_source_reference_keeps_observed_and_first_known_clocks_separate():
    source = _source()
    assert source.observed_at < source.known_at
    assert source.producer_schema == "global_liquidity_transmission.v1"
    assert source.conditions["dxy"] == "falling"

    with pytest.raises(ContractError, match="known_at may not precede observed_at"):
        _source(known_at="2026-08-20T12:00:00Z")
    with pytest.raises(ContractError, match="include a timezone"):
        _source(known_at="2026-08-20T14:00:00")
    with pytest.raises(ContractError, match="source_snapshot_hash"):
        _source(source_snapshot_hash="not-a-content-hash")


def test_shock_identity_is_keep_first_identity_not_revised_magnitude():
    original = build_shock_record(_source())
    revised = build_shock_record(
        _source(source_snapshot_hash="b" * 64, magnitude_z=2.1, breadth=0.9)
    )
    assert original.shock_id == revised.shock_id
    assert original.magnitude_z == 1.4
    assert revised.magnitude_z == 2.1
    assert original.source_snapshot_hash != revised.source_snapshot_hash


def test_forecast_contract_is_shadow_only_and_insufficient_means_no_estimate():
    base = ForwardForecast(
        shock_id=build_shock_record(_source()).shock_id,
        target_id="baba",
        horizon_bdays=60,
        model_version="curve_1",
        predicted_at=datetime(2026, 8, 20, 15, tzinfo=timezone.utc),
        relation_id="btc_china_delay",
        relation_state="shadow",
        expected_return=0.08,
        interval_low=-0.02,
        interval_high=0.18,
        probability_positive=0.65,
        effective_n=12,
        forecast_state="estimated",
    )
    assert base.forecast_key.endswith(":baba:60:curve_1")
    with pytest.raises(ContractError, match="non-authoritative"):
        replace(base, relation_state="advisory")
    with pytest.raises(ContractError, match="must not fabricate"):
        replace(base, forecast_state="insufficient")
