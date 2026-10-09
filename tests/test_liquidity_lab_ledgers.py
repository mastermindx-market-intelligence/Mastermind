from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from brain.liquidity_lab.contracts import (
    ContractError,
    ForecastGrade,
    ForwardForecast,
    SourceStateRef,
    build_shock_record,
)
from brain.liquidity_lab.ledger import (
    ForwardLedger,
    KeepFirstConflict,
    LedgerCorruptionError,
    ShockRegistry,
)


def _shock():
    return build_shock_record(
        SourceStateRef.from_mapping(
            {
                "observed_at": "2026-08-20T12:00:00Z",
                "known_at": "2026-08-20T13:00:00Z",
                "source_snapshot_hash": "a" * 64,
                "model_version": "glt_state_1",
                "data_version": "pit_1",
                "state_family": "monetary_impulse",
                "shock_type": "monetary_easing",
                "direction": 1,
                "magnitude_z": 1.4,
                "breadth": 0.7,
                "quality": "benign",
                "confidence": 0.8,
                "coverage": 0.8,
                "freshness": "fresh",
            }
        )
    )


def _forecast(shock_id: str) -> ForwardForecast:
    return ForwardForecast(
        shock_id=shock_id,
        target_id="baba",
        horizon_bdays=60,
        model_version="curve_1",
        predicted_at=datetime(2026, 8, 20, 14, tzinfo=timezone.utc),
        relation_id="btc_china_delay",
        relation_state="shadow",
        expected_return=0.08,
        interval_low=-0.02,
        interval_high=0.18,
        probability_positive=0.65,
        effective_n=12,
        forecast_state="estimated",
    )


def test_shock_registry_keep_first_and_append_only_amendment(tmp_path):
    registry = ShockRegistry(tmp_path / "shocks.jsonl")
    shock = _shock()
    assert registry.record(shock) == "created"
    assert registry.record(shock) == "duplicate"
    with pytest.raises(KeepFirstConflict, match="shock_id collision"):
        registry.record(replace(shock, magnitude_z=2.4))

    assert registry.amend(
        shock.shock_id,
        amended_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        reason="upstream vintage revision",
        replacement_fields={"magnitude_z": 1.6},
        source_snapshot_hash="b" * 64,
    ) == "created"
    assert registry.shocks()[0]["magnitude_z"] == 1.4
    assert registry.amendments(shock.shock_id)[0]["replacement_fields"] == {
        "magnitude_z": 1.6
    }
    with pytest.raises(ContractError, match="may not precede first_detected"):
        registry.amend(
            shock.shock_id,
            amended_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            reason="impossible early correction",
            replacement_fields={"magnitude_z": 1.1},
            source_snapshot_hash="d" * 64,
        )


def test_forward_ledger_keep_first_forecast_and_grade(tmp_path):
    ledger = ForwardLedger(tmp_path / "forecasts.jsonl")
    forecast = _forecast(_shock().shock_id)
    assert ledger.record(forecast) == "created"
    assert ledger.record(forecast) == "duplicate"
    with pytest.raises(KeepFirstConflict, match="forecast_key collision"):
        ledger.record(replace(forecast, expected_return=0.09))

    grade = ForecastGrade(
        forecast_key=forecast.forecast_key,
        resolved_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
        realized_return=0.05,
        outcome_source_hash="c" * 64,
    )
    assert ledger.grade(grade) == "created"
    assert ledger.grade(grade) == "duplicate"
    with pytest.raises(KeepFirstConflict, match="forecast grade collision"):
        ledger.grade(replace(grade, realized_return=-0.02))
    assert len(ledger.forecasts()) == 1
    assert len(ledger.grades()) == 1
    with pytest.raises(ContractError, match="may not precede predicted_at"):
        ledger.grade(
            ForecastGrade(
                forecast_key=forecast.forecast_key,
                resolved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
                realized_return=0.01,
                outcome_source_hash="e" * 64,
            )
        )


def test_ledgers_fail_closed_on_corrupt_existing_history(tmp_path):
    path = tmp_path / "shocks.jsonl"
    path.write_text('{"kind":"shock"}\nnot-json\n', encoding="utf-8")
    registry = ShockRegistry(path)
    with pytest.raises(LedgerCorruptionError, match="line 2"):
        registry.record(_shock())
