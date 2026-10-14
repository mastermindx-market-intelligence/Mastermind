from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from brain.liquidity_lab.contracts import ContractError, SourceStateRef, build_shock_record
from brain.liquidity_lab.estimator import (
    ForwardReturnObservation,
    HierarchicalMeanCurveEstimator,
    build_forward_return_panel,
)


def _shock(day: str):
    return build_shock_record(
        SourceStateRef.from_mapping(
            {
                "observed_at": f"{day}T12:00:00Z",
                "known_at": f"{day}T13:00:00Z",
                "source_snapshot_hash": "a" * 64,
                "model_version": "glt_state_1",
                "data_version": "pit_1",
                "state_family": "orthogonalised_impulse",
                "shock_type": "monetary_easing",
                "direction": 1,
                "magnitude_z": 1.4,
                "breadth": 0.7,
                "quality": "benign",
                "confidence": 0.8,
                "coverage": 0.8,
                "freshness": "fresh",
                "conditions": {"dxy": "falling"},
            }
        )
    )


def test_forward_returns_anchor_strictly_after_detection_and_respect_asof():
    shock = _shock("2026-01-02")
    prices = {
        "baba": pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
        )
    }
    unresolved = build_forward_return_panel(
        [shock], prices, as_of=date(2026, 1, 5), horizons=[1]
    )
    assert unresolved == []

    resolved = build_forward_return_panel(
        [shock], prices, as_of=date(2026, 1, 6), horizons=[1]
    )
    assert len(resolved) == 1
    assert resolved[0].anchor_session == date(2026, 1, 5)
    assert resolved[0].exit_session == date(2026, 1, 6)
    assert round(resolved[0].forward_return, 8) == 0.1


def test_forward_panel_fails_closed_on_ambiguous_duplicate_session_closes():
    shock = _shock("2026-01-02")
    ambiguous = pd.Series(
        [100.0, 101.0, 102.0],
        index=pd.to_datetime(
            ["2026-01-05T14:00:00Z", "2026-01-05T21:00:00Z", "2026-01-06T21:00:00Z"]
        ),
    )
    with pytest.raises(ContractError, match="one close per business session"):
        build_forward_return_panel(
            [shock], {"baba": ambiguous}, as_of=date(2026, 1, 6), horizons=[1]
        )


def _obs(target: str, day: int, value: float, *, horizon: int = 1) -> ForwardReturnObservation:
    target_parent = "china_internet"
    return ForwardReturnObservation(
        shock_id=f"liq_2026-01-{day:02d}_orthogonalised_impulse_pos_{day:012d}",
        first_detected=datetime(2026, 1, day, 13, tzinfo=timezone.utc),
        target_id=target,
        asset_class="china_equity",
        hierarchy_parent=target_parent,
        shock_family="orthogonalised_impulse",
        shock_type="monetary_easing",
        horizon_bdays=horizon,
        anchor_session=date(2026, 1, day),
        exit_session=date(2026, 1, min(day + horizon, 28)),
        forward_return=value,
        conditions={"dxy": "falling"},
    )


def test_hierarchical_curve_shrinks_to_peer_prior_and_hides_thin_cells():
    observations = [
        _obs("baba", 2, 0.10),
        _obs("baba", 6, 0.10),
        _obs("kweb", 2, 0.00),
        _obs("kweb", 6, 0.00),
        _obs("baba", 2, 0.20, horizon=5),
        _obs("baba", 6, 0.20, horizon=5),  # overlapping 5d windows -> effective_n=1
    ]
    estimator = HierarchicalMeanCurveEstimator(
        model_version="curve_1", prior_strength=2, min_effective_n=2
    )
    cells = estimator.fit(observations, condition_keys=["dxy"])
    baba_1d = next(
        cell for cell in cells if cell.target_id == "baba" and cell.horizon_bdays == 1
    )
    assert baba_1d.effective_n == 2
    assert baba_1d.raw_mean == 0.10
    assert baba_1d.prior_mean == 0.0
    assert baba_1d.shrunk_mean == 0.05
    assert baba_1d.evidence_state == "discovered"

    baba_5d = next(
        cell for cell in cells if cell.target_id == "baba" and cell.horizon_bdays == 5
    )
    assert baba_5d.effective_n == 1
    assert baba_5d.shrunk_mean is None
    assert baba_5d.evidence_state == "insufficient"
