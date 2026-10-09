"""Exact-source adapter tests; mutated payloads below are synthetic, not history."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.eventization import EventizationPolicy, eventize

FIXTURE = Path(__file__).parent / "fixtures/liquidity_lab/glt_producer_20260904.json"
CUTOFF = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)


def sample():
    return json.loads(FIXTURE.read_text())


def adapt(payload, *, as_of=CUTOFF):
    spec = importlib.util.find_spec("brain.liquidity_lab.adapter")
    assert spec is not None, "The canonical raw-producer adapter is not implemented"
    return importlib.import_module("brain.liquidity_lab.adapter").adapt_producer_state(payload, as_of=as_of)


def set_path(payload, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        payload = payload[part]
    payload[parts[-1]] = value


def test_exact_producer_sample_copies_without_reinterpreting():
    p = sample()
    before = deepcopy(p)
    ref = adapt(p)
    e = p["state"]["event_reference"]
    assert ref is not None
    assert ref.observed_at.isoformat() == "2026-08-28T00:00:00+00:00"
    assert ref.known_at.isoformat() == "2026-09-04T11:03:41.497178+00:00"
    for key in ("source_snapshot_hash", "model_version", "data_version", "direction",
                "magnitude_z", "breadth", "quality", "confidence", "coverage", "freshness"):
        assert getattr(ref, key) == e[key]
    assert ref.magnitude_z != e["magnitude"]
    assert e["direction_label"] == "flat" and ref.direction == 1
    assert p["quality"]["status"] == "degraded" and ref.freshness == "fresh"
    assert ref.conditions == e["conditions"]
    assert ref.component_snapshot == e["component_snapshot"]
    assert p == before
    # Test-only policy: not a registered production threshold or empirical finding.
    policy = EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5)
    assert eventize([ref], policy) == []


def test_input_mutation_cannot_rewrite_adapted_receipts():
    p = sample()
    ref = adapt(p)
    p["state"]["event_reference"]["component_snapshot"]["monetary"]["fed"]["receipt"]["available_date"] = "2099-01-01"
    assert ref.component_snapshot["monetary"]["fed"]["receipt"]["available_date"] == "2026-08-27"


@pytest.mark.parametrize("path,value", [
    ("meta.schema", "unrelated.v1"),
    ("meta.authority", "trade"),
    ("meta.contract_scope", "forecast"),
    ("meta.source_snapshot_hash", "a" * 64),
    ("meta.model_version", "changed.v2"),
    ("meta.data_version", "changed.v2"),
    ("state.event_reference.magnitude_z_unit", "weekly_change_in_expanding_z_score"),
    ("state.event_reference.magnitude_z_field", "state.monetary_impulse"),
    ("state.event_reference.magnitude_unit", "percent"),
    ("state.event_reference.magnitude_field", "state.monetary_stance"),
    ("state.event_reference.magnitude_z", 12.5),
    ("state.event_reference.direction_label", "easing"),
    ("state.event_reference.quality", "expanding"),
    ("state.event_reference.direction", True),
    ("state.event_reference.direction", -1),
    ("state.event_reference.coverage", True),
    ("state.event_reference.confidence", "0.833333"),
    ("state.event_reference.regional_gates", {"china": "allow"}),
    ("state.event_reference.clocks.adapter_observed_at_field", "monetary_release_at"),
    ("state.event_reference.clocks.first_known_at", "2026-08-27T00:00:00Z"),
])
def test_malformed_or_inconsistent_contract_refuses(path, value):
    p = sample()
    set_path(p, path, value)
    with pytest.raises(ContractError):
        adapt(p)


def test_backdated_clock_refuses_even_when_aliases_agree():
    p = sample()
    for c in (p["freshness"]["clocks"], p["state"]["event_reference"]["clocks"]):
        c["evidence_available_at"] = c["release_at"] = "2026-08-27T00:00:00Z"
        c["evidence_available_at_contributions"]["usd_funding"] = "2026-08-27T00:00:00Z"
    with pytest.raises(ContractError, match="availability|available|evidence"):
        adapt(p)


def test_later_embedded_quality_clock_cannot_be_hidden():
    p = sample()
    p["quality"]["us_liquidity_quality"] = {"asof": "2026-08-31", "quality": "easing"}
    with pytest.raises(ContractError, match="quality|availability|available|evidence"):
        adapt(p)


@pytest.mark.parametrize("cutoff", [datetime(2026, 9, 4), datetime(2026, 8, 29, tzinfo=timezone.utc)])
def test_cutoff_is_explicit_aware_and_after_actual_first_known(cutoff):
    with pytest.raises(ContractError):
        adapt(sample(), as_of=cutoff)


@pytest.mark.parametrize("value", [True, "1.5", float("nan"), float("inf")])
def test_matching_bad_numbers_are_not_validated_by_equality(value):
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = value
    with pytest.raises(ContractError):
        adapt(p)


def test_valid_warmup_null_does_not_become_zero():
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = None
    assert adapt(p) is None


def test_zero_raw_direction_is_a_non_event_without_inventing_sign():
    p = sample()
    p["state"]["monetary_impulse"] = p["state"]["event_reference"]["magnitude"] = 0.0
    p["state"]["event_reference"]["direction"] = None
    assert adapt(p) is None


def test_standardized_deviation_need_not_have_raw_direction_sign():
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = -2.5
    ref = adapt(p)
    assert ref.magnitude_z == -2.5 and ref.direction == 1


def test_null_still_requires_honest_evidence_clock():
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = None
    p["state"]["event_reference"]["clocks"]["first_known_at"] = "2026-08-01T00:00:00Z"
    with pytest.raises(ContractError):
        adapt(p)


@pytest.mark.parametrize("freshness", ["degraded", "stale", "unknown"])
def test_unavailable_event_reference_is_not_upgraded(freshness):
    p = sample()
    p["state"]["event_reference"]["freshness"] = freshness
    p["freshness"]["status"] = freshness
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = 3.0
    ref = adapt(p)
    assert ref.freshness == freshness
    assert eventize([ref], EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5)) == []


def test_synthetic_material_point_uses_existing_event_and_identity():
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = 3.0
    ref = adapt(p)
    events = eventize([ref, ref], EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5))
    assert len(events) == 1
    assert events[0].first_detected == ref.known_at
    assert events[0].source_observed_at == ref.observed_at
    assert events[0].source_snapshot_hash == ref.source_snapshot_hash


def test_missing_contract_object_raises_typed_refusal():
    with pytest.raises(ContractError):
        adapt({})


@pytest.mark.parametrize("path,value", [
    ("state.event_reference.conditions.usd_funding_impulse", 99.0),
    ("state.event_reference.conditions.us_liquidity_quality", "easing"),
    ("state.event_reference.breadth", 0.75),
    ("quality.confidence.kind", "predictive_probability"),
    ("state.event_reference.freshness", "unchecked"),
])
def test_copied_context_must_match_its_declared_semantics(path, value):
    p = sample()
    set_path(p, path, value)
    with pytest.raises(ContractError):
        adapt(p)


def test_conditions_do_not_accept_new_unregistered_features():
    p = sample()
    p["state"]["event_reference"]["conditions"]["future_return"] = 0.5
    with pytest.raises(ContractError):
        adapt(p)


def test_null_event_still_validates_context_structure():
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = None
    p["state"]["event_reference"]["conditions"] = []
    with pytest.raises(ContractError):
        adapt(p)


def test_erased_component_inventory_is_not_full_coverage():
    p = sample()
    p["freshness"]["component_snapshot"]["monetary"] = {}
    p["state"]["event_reference"]["component_snapshot"]["monetary"] = {}
    p["freshness"]["components"]["monetary"] = {}
    with pytest.raises(ContractError):
        adapt(p)


def test_flat_receipt_copy_must_match_event_snapshot():
    p = sample()
    p["freshness"]["components"]["monetary"]["fed"]["available_date"] = "2099-01-01"
    with pytest.raises(ContractError):
        adapt(p)


def test_copied_unknown_component_family_cannot_hide_future_evidence():
    p = sample()
    for snapshots in (p["freshness"]["component_snapshot"],
                      p["state"]["event_reference"]["component_snapshot"]):
        snapshots["future"] = {"unregistered": {"receipt": {"available_date": "2099-01-01"}}}
    with pytest.raises(ContractError):
        adapt(p)


def test_economic_reference_cannot_postdate_its_availability():
    p = sample()
    p["freshness"]["components"]["monetary"]["fed"]["reference_date"] = "2099-01-01"
    for snapshots in (p["freshness"]["component_snapshot"],
                      p["state"]["event_reference"]["component_snapshot"]):
        snapshots["monetary"]["fed"]["receipt"]["reference_date"] = "2099-01-01"
    with pytest.raises(ContractError):
        adapt(p)


def test_present_us_quality_label_is_copied_not_reclassified():
    p = sample()
    p["quality"]["us_liquidity_quality"] = {"asof": "2026-08-27", "label": "benign"}
    p["state"]["event_reference"]["conditions"]["us_liquidity_quality"] = "benign"
    for clocks in (p["freshness"]["clocks"], p["state"]["event_reference"]["clocks"]):
        clocks["evidence_available_at_contributions"]["us_liquidity_quality"] = "2026-08-27T00:00:00Z"
    ref = adapt(p)
    assert ref.conditions["us_liquidity_quality"] == "benign"
    assert ref.quality == "mixed"


def test_additive_top_level_metadata_does_not_break_adapter():
    p = sample()
    p["meta"]["human_note"] = "additional non-consumed annotation"
    assert adapt(p).source_snapshot_hash == sample()["meta"]["source_snapshot_hash"]


@pytest.mark.parametrize("value", [[], {}, None, True])
def test_malformed_freshness_is_typed_refusal_even_for_warmup(value):
    p = sample()
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = None
    p["state"]["event_reference"]["freshness"] = p["freshness"]["status"] = value
    with pytest.raises(ContractError):
        adapt(p)


@pytest.mark.parametrize("block,key", [
    ("state", "usd_funding_impulse"), ("state", "liquidity_breadth"),
    ("quality", "us_liquidity_quality"),
])
def test_required_null_source_field_is_not_silently_defaulted(block, key):
    p = sample()
    if key == "usd_funding_impulse":
        p["state"]["event_reference"]["conditions"][key] = None
    elif key == "liquidity_breadth":
        p["state"]["event_reference"]["breadth"] = None
    del p[block][key]
    with pytest.raises(ContractError):
        adapt(p)


def test_real_sample_does_not_publish_a_synthetic_shock(tmp_path):
    from brain.liquidity_lab.ledger import ShockRegistry
    path = tmp_path / "shocks.jsonl"
    registry = ShockRegistry(path)
    # This is deliberately only a test policy, not empirical threshold selection.
    for event in eventize([adapt(sample())], EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5)):
        registry.record(event)
    assert registry.shocks() == []
    assert not path.exists()


def test_synthetic_adapter_event_registry_retry_and_correction(tmp_path):
    from brain.liquidity_lab.ledger import ShockRegistry
    p = sample()
    synthetic_hash = "c" * 64
    for block in (p["meta"], p["state"]["event_reference"]):
        block["source_snapshot_hash"] = synthetic_hash
        block["data_version"] = "glt_data:" + synthetic_hash[:16]
    p["state"]["monetary_impulse_z"] = p["state"]["event_reference"]["magnitude_z"] = 3.0
    event, = eventize([adapt(p)], EventizationPolicy(2.0, 0.5, 0.8, 0.5, 10, 5))
    registry = ShockRegistry(tmp_path / "synthetic_shocks.jsonl")
    assert registry.record(event) == "created"
    assert registry.record(event) == "duplicate"
    assert registry.amend(
        event.shock_id, amended_at=CUTOFF,
        reason="synthetic correction test; not a historical observation",
        replacement_fields={"magnitude_z": 4.0}, source_snapshot_hash="d" * 64,
    ) == "created"
    reopened = ShockRegistry(tmp_path / "synthetic_shocks.jsonl")
    assert len(reopened.shocks()) == 1
    assert reopened.shocks()[0]["magnitude_z"] == 3.0
    assert reopened.shocks()[0]["source_snapshot_hash"] == synthetic_hash
    assert reopened.amendments(event.shock_id)[0]["replacement_fields"] == {"magnitude_z": 4.0}
