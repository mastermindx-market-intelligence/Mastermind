from __future__ import annotations

from brain.liquidity_lab.contracts import SourceStateRef
from brain.liquidity_lab.eventization import EventizationPolicy, eventize


def _point(day: str, magnitude: float, *, direction: int = 1, freshness: str = "fresh") -> SourceStateRef:
    return SourceStateRef.from_mapping(
        {
            "observed_at": f"{day}T12:00:00Z",
            "known_at": f"{day}T13:00:00Z",
            "source_snapshot_hash": ("a" if direction > 0 else "b") * 64,
            "model_version": "glt_state_1",
            "data_version": "pit_1",
            "state_family": "orthogonalised_impulse",
            "shock_type": "monetary_easing" if direction > 0 else "monetary_tightening",
            "direction": direction,
            "magnitude_z": magnitude,
            "breadth": 0.7,
            "quality": "benign" if direction > 0 else "restrictive",
            "confidence": 0.8,
            "coverage": 0.8,
            "freshness": freshness,
        }
    )


def test_eventization_keeps_first_and_refuses_stale_or_rapid_remints():
    policy = EventizationPolicy(
        material_abs_z=1.0,
        reset_abs_z=0.4,
        min_coverage=0.7,
        min_confidence=0.7,
        max_observation_gap_bdays=3,
        refractory_bdays=5,
    )
    shocks = eventize(
        [
            _point("2026-01-02", 1.2),       # first positive episode
            _point("2026-01-05", 1.8),       # continuation cannot rewrite it
            _point("2026-01-06", 2.0, freshness="stale"),
            _point("2026-01-07", 0.2),       # explicit reset
            _point("2026-01-08", 1.3),       # inside refractory window: suppressed
            _point("2026-01-12", 1.4),       # same active suppressed episode: no remint
            _point("2026-01-13", -1.5, direction=-1),  # sign flip is a distinct episode
        ],
        policy,
    )
    assert len(shocks) == 2
    assert shocks[0].first_detected.isoformat().startswith("2026-01-02T13:00:00")
    assert shocks[0].magnitude_z == 1.2
    assert shocks[1].direction == -1
    assert all(shock.freshness == "fresh" for shock in shocks)


def test_long_gap_closes_episode_and_allows_new_first_detection():
    policy = EventizationPolicy(
        material_abs_z=1.0,
        reset_abs_z=0.4,
        min_coverage=0.5,
        min_confidence=0.5,
        max_observation_gap_bdays=2,
        refractory_bdays=2,
    )
    shocks = eventize([_point("2026-01-02", 1.2), _point("2026-01-12", 1.3)], policy)
    assert [shock.first_detected.date().isoformat() for shock in shocks] == [
        "2026-01-02",
        "2026-01-12",
    ]
