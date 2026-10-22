from __future__ import annotations

import inspect
import json
import random
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import brain.liquidity_lab.ledger as ledger_module
from brain.liquidity_lab.contracts import ContractError, SourceStateRef
from brain.liquidity_lab.eventization import (
    EVENTIZATION_DEFINITION_VERSION,
    SHOCK_CLASSES,
    TRUSTED_FRESHNESS,
    EventizationPolicy,
    ShockLabel,
    event_definition,
    event_definition_id,
    eventize,
    label_shock,
)
from brain.liquidity_lab.ledger import KeepFirstConflict, ShockRegistry


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


# --- T11: event-definition identity, amendment-only corrections, shock-class label ---
# All observations below are synthetic; thresholds are test-only (the T11 docket lists them).
BASE = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0)


def test_event_definition_id_is_stable_and_versioned():
    first = event_definition_id(BASE)
    assert first == event_definition_id(EventizationPolicy(1.0, 0.4, 0.7, 0.7, 10, 0))
    assert first.startswith("evdef_")
    definition = event_definition(BASE)
    assert definition["definition_version"] == EVENTIZATION_DEFINITION_VERSION
    assert definition["trusted_freshness"] == ["fresh"] == sorted(TRUSTED_FRESHNESS)
    # Every policy threshold is part of the hashed definition.
    assert {field.name for field in fields(EventizationPolicy)} <= set(definition)


@pytest.mark.parametrize("field,value", [
    ("material_abs_z", 1.1), ("reset_abs_z", 0.3), ("min_coverage", 0.6),
    ("min_confidence", 0.6), ("max_observation_gap_bdays", 9), ("refractory_bdays", 1),
])
def test_event_definition_id_changes_with_every_threshold(field, value):
    assert event_definition_id(replace(BASE, **{field: value})) != event_definition_id(BASE)


def test_event_definition_id_normalises_numeric_types():
    assert event_definition_id(EventizationPolicy(1, 0, 1, 1, 10, 0)) == event_definition_id(
        EventizationPolicy(1.0, 0.0, 1.0, 1.0, 10, 0)
    )


@pytest.mark.parametrize("field,value", [
    ("material_abs_z", True), ("min_coverage", True), ("min_confidence", False),
    ("max_observation_gap_bdays", True), ("refractory_bdays", False),
    ("max_observation_gap_bdays", 10.5), ("refractory_bdays", 2.5), ("refractory_bdays", 2.0),
])
def test_event_definition_refuses_bool_and_non_integer_bday_counts(field, value):
    # refractory_bdays=2.5 and =2 behave differently in eventize; int() would give them one id.
    policy = replace(BASE, **{field: value})
    with pytest.raises(ContractError):
        event_definition_id(policy)


def test_event_definition_id_reads_no_outcome_data():
    assert list(inspect.signature(event_definition_id).parameters) == ["policy"]
    assert list(inspect.signature(event_definition).parameters) == ["policy"]
    before = event_definition_id(BASE)
    eventize([_point("2026-01-02", 1.2), _point("2026-01-05", 1.8)], BASE)
    middle = event_definition_id(BASE)
    eventize([_point("2026-01-02", -1.4, direction=-1)], BASE)
    assert before == middle == event_definition_id(BASE)


@pytest.mark.parametrize("field,value", [
    ("data_version", "pit_2"), ("model_version", "glt_state_2"), ("source_snapshot_hash", "c" * 64),
])
def test_changed_versions_of_a_recorded_observation_are_amendments_not_new_episodes(
    tmp_path, field, value
):
    original = eventize([_point("2026-01-02", 1.2)], BASE)[0]
    variant = eventize([replace(_point("2026-01-02", 1.2), **{field: value})], BASE)[0]
    registry = ShockRegistry(tmp_path / "shocks.jsonl")
    assert registry.record(original) == "created"
    with pytest.raises(KeepFirstConflict):
        registry.record(variant)
    assert registry.amend(
        original.shock_id,
        amended_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        reason=f"{field} correction",
        replacement_fields={field: value},
        source_snapshot_hash="d" * 64,
    ) == "created"
    assert len(registry.shocks()) == 1
    assert registry.shocks()[0] == original.to_dict()
    assert len(registry.amendments(original.shock_id)) == 1


def test_later_known_revision_of_same_observation_is_an_amendment(tmp_path):
    original = eventize([_point("2026-01-02", 1.2)], BASE)[0]
    revised_point = replace(
        _point("2026-01-02", 1.2),
        known_at=datetime(2026, 1, 5, 13, tzinfo=timezone.utc),
        data_version="pit_2",
    )
    revision = eventize([revised_point], BASE)[0]
    assert revision.shock_id != original.shock_id
    assert revision.source_observed_at == original.source_observed_at
    registry = ShockRegistry(tmp_path / "shocks.jsonl")
    assert registry.record(original) == "created"
    with pytest.raises(KeepFirstConflict, match="corrections use ShockRegistry.amend"):
        registry.record(revision)
    assert len(registry.shocks()) == 1


def test_sign_flipped_revision_of_same_observation_is_an_amendment(tmp_path):
    original = eventize([_point("2026-01-02", 1.2)], BASE)[0]
    flipped = eventize([_point("2026-01-02", -1.3, direction=-1)], BASE)[0]
    assert flipped.shock_id != original.shock_id
    registry = ShockRegistry(tmp_path / "shocks.jsonl")
    assert registry.record(original) == "created"
    with pytest.raises(KeepFirstConflict, match="corrections use ShockRegistry.amend"):
        registry.record(flipped)
    assert len(registry.shocks()) == 1


@pytest.mark.parametrize("field,value", [
    ("freshness", "stale"), ("freshness", "degraded"), ("freshness", "unknown"),
    ("coverage", 0.5), ("confidence", 0.5),
])
def test_low_quality_gap_cannot_remint_inside_the_episode(tmp_path, field, value):
    points = [
        _point("2026-01-02", 1.2),
        replace(_point("2026-01-05", 0.1), **{field: value}),
        replace(_point("2026-01-06", -1.6, direction=-1), **{field: value}),
        _point("2026-01-07", 1.5),
    ]
    shocks = eventize(points, BASE)
    assert [shock.first_detected.date().isoformat() for shock in shocks] == ["2026-01-02"]
    registry = ShockRegistry(tmp_path / "shocks.jsonl")
    assert [registry.record(shock) for shock in shocks] == ["created"]
    assert len(registry.shocks()) == 1


def test_low_quality_points_do_not_bridge_a_real_gap():
    policy = EventizationPolicy(1.0, 0.4, 0.7, 0.7, 2, 0)
    shocks = eventize(
        [
            _point("2026-01-02", 1.2),
            _point("2026-01-05", 1.4, freshness="stale"),
            _point("2026-01-06", 1.4, freshness="stale"),
            _point("2026-01-12", 1.5),
        ],
        policy,
    )
    assert [shock.first_detected.date().isoformat() for shock in shocks] == [
        "2026-01-02",
        "2026-01-12",
    ]


def _replay_points():
    return [
        _point("2026-01-02", 1.2),
        _point("2026-01-05", 1.8),
        _point("2026-01-06", 0.2),
        _point("2026-01-07", 1.3),
        _point("2026-01-08", -1.5, direction=-1),
        _point("2026-01-09", -1.7, direction=-1),
        _point("2026-01-12", 1.1),
    ]


def test_replay_through_eventize_and_registry_is_byte_identical(tmp_path, monkeypatch):
    points = _replay_points()
    first = json.dumps([shock.to_dict() for shock in eventize(points, BASE)], sort_keys=True)
    second = json.dumps([shock.to_dict() for shock in eventize(points, BASE)], sort_keys=True)
    shuffled = json.dumps(
        [shock.to_dict() for shock in eventize(random.Random(7).sample(points, len(points)), BASE)],
        sort_keys=True,
    )
    assert first == second == shuffled
    shocks = eventize(points, BASE)
    assert len(shocks) == 4
    monkeypatch.setattr(ledger_module, "_now_iso", lambda: "2026-10-13T00:00:00+00:00")
    path_a, path_b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    registry_a, registry_b = ShockRegistry(path_a), ShockRegistry(path_b)
    assert [registry_a.record(shock) for shock in shocks] == ["created"] * len(shocks)
    assert [registry_b.record(shock) for shock in shocks] == ["created"] * len(shocks)
    assert path_a.read_bytes() == path_b.read_bytes()
    assert registry_a.rows() == registry_b.rows()
    before = path_a.read_bytes()
    assert [registry_a.record(shock) for shock in eventize(points, BASE)] == ["duplicate"] * len(shocks)
    assert path_a.read_bytes() == before


def test_eventized_shock_label_defaults_to_not_identified():
    shocks = eventize(_replay_points(), BASE)
    assert shocks
    for shock in shocks:
        label = label_shock(shock)
        assert isinstance(label, ShockLabel)
        assert label.shock_id == shock.shock_id
        assert label.shock_class == "observed_state_change"
        assert label.identification_status == "NOT_IDENTIFIED"
        assert label.identification_receipt is None
        assert set(label.to_dict()) == {
            "shock_id", "shock_class", "identification_status", "identification_receipt",
        }
        # The label is never written into the immutable shock record.
        assert "shock_class" not in shock.to_dict()
        assert "identification_status" not in shock.to_dict()


def test_identified_intervention_requires_an_explicit_receipt():
    shock = eventize([_point("2026-01-02", 1.2)], BASE)[0]
    receipt = {"receipt_id": "r1", "method": "high_frequency_surprise"}
    with pytest.raises(ContractError):
        label_shock(shock, shock_class="identified_intervention")
    with pytest.raises(ContractError):
        label_shock(shock, shock_class="identified_intervention", identification_receipt=receipt)
    with pytest.raises(ContractError):
        label_shock(
            shock,
            shock_class="identified_intervention",
            identification_receipt={**receipt, "weak_instrument": True},
        )
    with pytest.raises(ContractError):
        label_shock(
            shock,
            shock_class="identified_intervention",
            identification_receipt={"receipt_id": "r1", "weak_instrument": False},
        )
    identified = label_shock(
        shock,
        shock_class="identified_intervention",
        identification_receipt={**receipt, "weak_instrument": False},
    )
    assert identified.identification_status == "IDENTIFIED"
    assert identified.identification_receipt["receipt_id"] == "r1"
    with pytest.raises(ContractError):
        label_shock(
            shock,
            shock_class="forecast_innovation",
            identification_receipt={**receipt, "weak_instrument": False},
        )
    with pytest.raises(ContractError):
        label_shock(shock, shock_class="exogenous_shock")
    assert SHOCK_CLASSES == (
        "observed_state_change",
        "forecast_innovation",
        "policy_announcement_surprise",
        "identified_intervention",
    )


def test_no_other_code_path_names_identified_intervention():
    root = Path(__file__).resolve().parents[1]
    hits = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "brain").rglob("*.py")
        if path.is_file()
        and "identified_intervention" in path.read_text(encoding="utf-8", errors="ignore")
    )
    assert hits == ["brain/liquidity_lab/eventization.py"]
