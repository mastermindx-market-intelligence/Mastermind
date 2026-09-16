from __future__ import annotations

from dataclasses import replace

import pytest

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


# An unavailable observation is not evidence that a previous episode ended.
# All observations below are synthetic; thresholds are test-only.
@pytest.mark.parametrize("changes", [
    {"freshness": "stale"}, {"freshness": "unknown"},
    {"freshness": "degraded"}, {"coverage": 0.1}, {"confidence": 0.1},
])
def test_untrusted_low_reading_cannot_reset_and_remint_episode(changes):
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0)
    points = [
        _point("2026-01-02", 1.2),
        replace(_point("2026-01-05", 0.1), **changes),
        _point("2026-01-06", 1.3),
    ]
    events = eventize(points, policy)
    assert [e.first_detected.date().isoformat() for e in events] == ["2026-01-02"]


def test_trusted_low_reading_still_resets_episode():
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0)
    events = eventize([_point("2026-01-02", 1.2), _point("2026-01-05", 0.1),
                      _point("2026-01-06", 1.3)], policy)
    assert len(events) == 2


@pytest.mark.parametrize("changes", [
    {"freshness": "stale"}, {"coverage": 0.1}, {"confidence": 0.1},
])
def test_untrusted_readings_cannot_bridge_valid_observation_gap(changes):
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 2, 0)
    points = [_point("2026-01-02", 1.2)]
    for day in ("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"):
        points.append(replace(_point(day, 1.3), **changes))
    points.append(_point("2026-01-09", 1.4))
    events = eventize(points, policy)
    assert [e.first_detected.date().isoformat() for e in events] == [
        "2026-01-02", "2026-01-09",
    ]


@pytest.mark.parametrize("changes", [
    {"magnitude_z": 1.8}, {"direction": -1, "magnitude_z": -1.4},
    {"coverage": 0.1}, {"freshness": "stale"},
    {"model_version": "glt_state_2"}, {"source_snapshot_hash": "c" * 64},
])
def test_conflicting_same_clock_observations_are_not_order_selected(changes):
    from brain.liquidity_lab.contracts import ContractError
    point = _point("2026-01-02", 1.2)
    conflict = replace(point, **changes)
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0)
    for inputs in ([point, conflict], [conflict, point]):
        with pytest.raises(ContractError, match="conflicting.*observation"):
            eventize(inputs, policy)


def test_exact_duplicate_observations_preserve_replay_result():
    point = _point("2026-01-02", 1.2)
    followup = _point("2026-01-05", 1.6)
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0)
    expected = [e.to_dict() for e in eventize([point, followup], policy)]
    assert [e.to_dict() for e in eventize([followup, point, point], policy)] == expected
