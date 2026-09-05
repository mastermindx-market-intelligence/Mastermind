from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from brain.liquidity_lab.contracts import SourceStateRef, build_shock_record
from brain.liquidity_lab.estimator import ForwardReturnObservation, HierarchicalMeanCurveEstimator
from brain.liquidity_lab.validation import (
    PromotionPolicy,
    RelationEvidence,
    RelationState,
    WalkForwardSpec,
    WalkForwardPrediction,
    apply_bh_fdr,
    build_walk_forward_plan,
    effective_episode_dates,
    lifecycle_step,
    run_walk_forward_curves,
    score_incremental_predictions,
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
            }
        )
    )


def test_effective_n_is_non_overlapping_episode_dates():
    dates = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 12)]
    assert effective_episode_dates(dates, horizon_bdays=5) == (
        date(2026, 1, 2),
        date(2026, 1, 12),
    )


def test_walk_forward_plan_purges_outcomes_and_keeps_holdout_untouched():
    shocks = [
        _shock("2026-01-02"),
        _shock("2026-01-12"),
        _shock("2026-01-22"),
        _shock("2026-02-03"),
        _shock("2026-02-13"),
        _shock("2026-03-02"),
    ]
    plan = build_walk_forward_plan(
        shocks,
        horizon_bdays=5,
        spec=WalkForwardSpec(
            holdout_start=date(2026, 3, 1),
            min_train_episodes=2,
            validation_episodes=1,
            step_episodes=1,
        ),
    )
    assert plan.splits
    assert all(
        held not in split.train_shock_ids + split.validation_shock_ids
        for held in plan.untouched_holdout_shock_ids
        for split in plan.splits
    )
    assert plan.untouched_holdout_shock_ids == (shocks[-1].shock_id,)
    assert all(split.train_end < split.validation_start for split in plan.splits)


def _observation(shock, value: float) -> ForwardReturnObservation:
    anchor = shock.first_detected.date()
    return ForwardReturnObservation(
        shock_id=shock.shock_id,
        first_detected=shock.first_detected,
        target_id="baba",
        asset_class="china_equity",
        hierarchy_parent="china_internet",
        shock_family=shock.shock_family,
        shock_type=shock.shock_type,
        horizon_bdays=1,
        anchor_session=anchor,
        exit_session=date.fromordinal(anchor.toordinal() + 1),
        forward_return=value,
        conditions={},
    )


def test_walk_forward_runner_fits_train_only_and_never_scores_holdout():
    shocks = [_shock("2026-01-02"), _shock("2026-01-12"), _shock("2026-01-22"), _shock("2026-03-02")]
    observations = [
        _observation(shocks[0], 0.10),
        _observation(shocks[1], 0.10),
        _observation(shocks[2], 0.20),
        _observation(shocks[3], 9.99),  # untouched holdout sentinel
    ]
    plan = build_walk_forward_plan(
        shocks,
        horizon_bdays=1,
        spec=WalkForwardSpec(
            holdout_start=date(2026, 3, 1),
            min_train_episodes=2,
            validation_episodes=1,
            step_episodes=1,
        ),
    )
    predictions = run_walk_forward_curves(
        observations,
        plan=plan,
        estimator=HierarchicalMeanCurveEstimator(
            model_version="curve_1", prior_strength=0, min_effective_n=2
        ),
        relation_id="glt_to_baba",
    )
    assert len(predictions) == 1
    assert predictions[0].shock_id == shocks[2].shock_id
    assert predictions[0].predicted_return == 0.10
    assert predictions[0].realized_return == 0.20
    assert shocks[3].shock_id not in {row.shock_id for row in predictions}


def test_incremental_score_is_paired_episode_honest_input_to_fdr():
    candidate = [
        WalkForwardPrediction(
            split_index=index,
            relation_id="candidate",
            model_version="curve_1",
            shock_id=f"shock_{index}",
            target_id="baba",
            horizon_bdays=1,
            anchor_session=date(2026, 1, 2 + index * 10),
            exit_session=date(2026, 1, 3 + index * 10),
            predicted_return=0.15,
            realized_return=0.20,
            effective_n_at_fit=10,
        )
        for index in range(2)
    ]
    baseline = [
        WalkForwardPrediction(
            split_index=row.split_index,
            relation_id="baseline",
            model_version="baseline_1",
            shock_id=row.shock_id,
            target_id=row.target_id,
            horizon_bdays=row.horizon_bdays,
            anchor_session=row.anchor_session,
            exit_session=row.exit_session,
            predicted_return=0.0,
            realized_return=row.realized_return,
            effective_n_at_fit=10,
        )
        for row in candidate
    ]

    def frozen_hac(values):
        assert len(values) == 2
        return {"mean": float(values.mean()), "p": 0.04}

    score = score_incremental_predictions(candidate, baseline, mean_test_fn=frozen_hac)
    assert score["status"] == "scoring"
    assert score["effective_n"] == 2
    assert score["mean_squared_error_improvement"] > 0
    assert score["p_value"] == 0.04


def test_fdr_bridge_uses_injected_canonical_judge_shape():
    def frozen_judge(p_values, *, alpha):
        return {
            key: {"p": value, "reject": value <= alpha / len(p_values)}
            for key, value in p_values.items()
        }

    result = apply_bh_fdr(
        {"btc_to_china": 0.01, "qqq_to_china": 0.20},
        alpha=0.10,
        fdr_fn=frozen_judge,
    )
    assert result["btc_to_china"]["reject"] is True
    assert result["qqq_to_china"]["reject"] is False


def test_lifecycle_cannot_promote_without_sol_owned_policy():
    evidence = RelationEvidence(
        effective_n=30,
        fdr_reject=True,
        incremental_metric=0.10,
        sign_stability=0.90,
        max_episode_share=0.10,
        forward_windows=12,
        forward_predictions_started=True,
    )
    assert lifecycle_step(RelationState.DISCOVERED, evidence, policy=None) == RelationState.DISCOVERED
    policy = PromotionPolicy(
        min_effective_n_advisory=12,
        min_effective_n_validated=24,
        min_incremental_metric=0.02,
        min_sign_stability=0.70,
        max_episode_share=0.25,
        min_forward_windows_validated=8,
        demote_sign_stability=0.45,
    )
    assert lifecycle_step(RelationState.DISCOVERED, evidence, policy=policy) == RelationState.SHADOW
    assert lifecycle_step(RelationState.SHADOW, evidence, policy=policy) == RelationState.ADVISORY
    assert lifecycle_step(RelationState.ADVISORY, evidence, policy=policy) == RelationState.VALIDATED


def test_btc_china_protocol_refuses_to_invent_chronology():
    path = Path("research/liquidity_transmission/btc_china_protocol.v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["historical_episode_fixture"]["episodes"] == []
    assert payload["historical_episode_fixture"]["status"] == "chronology_not_frozen"
    assert payload["holdout"]["start"] is None
    assert payload["horizons_bdays"] == [1, 5, 10, 20, 40, 60, 90, 120]
