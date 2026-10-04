"""Source-evidence proofs for the AttentionCompanyReadProjection wire extension."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.operator_harness_contract import (
    AttentionCompanyReadProjection,
    AttentionTurnObservation,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError,
    attention_turn_observation,
    to_wire,
)

CONSULT = "consult-" + "a" * 32
SHA = "b" * 64
IDS = dict(
    process_generation_id="gen-a",
    provider_session_id="thread-a",
    provider_native_turn_id="turn-a",
    nudge_id="NUDGE-a",
)


def _projection(**overrides: object) -> AttentionCompanyReadProjection:
    fields: dict[str, object] = dict(
        target_attempt_id="ATT-a",
        binding_id="bind-a",
        binding_generation=1,
        consultation_ref=CONSULT,
        result_sha256=SHA,
        native_item_sha256=SHA,
        answer_attestation_sha256=SHA,
        **IDS,
    )
    fields.update(overrides)
    return AttentionCompanyReadProjection(**fields)


def _observation(**overrides: object) -> AttentionTurnObservation:
    fields: dict[str, object] = dict(accepted=True, delivered=True, **IDS)
    fields.update(overrides)
    return AttentionTurnObservation(**fields)


def test_nested_projection_round_trips_closed_frozen_and_hidden() -> None:
    observation = _observation(company_read_projection=_projection())
    wire = to_wire(observation)
    assert set(wire["company_read_projection"]) == {
        f.name for f in dataclasses.fields(AttentionCompanyReadProjection)}
    assert attention_turn_observation(wire) == observation
    with pytest.raises(dataclasses.FrozenInstanceError):
        observation.company_read_projection.result_sha256 = "c" * 64
    field = next(f for f in dataclasses.fields(AttentionTurnObservation)
                 if f.name == "company_read_projection")
    assert field.repr is False and CONSULT not in repr(observation)


@pytest.mark.parametrize("field,value", [
    ("result_sha256", "A" * 64), ("native_item_sha256", "b" * 63),
    ("consultation_ref", "consult-" + "g" * 32), ("binding_id", "binding-a"),
    ("binding_generation", 0), ("binding_generation", True),
    ("target_attempt_id", " ATT-a")])
def test_projection_rejects_malformed_fields(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _projection(**{field: value})


@pytest.mark.parametrize("field", ["process_generation_id", "provider_session_id",
                                   "provider_native_turn_id", "nudge_id"])
def test_projection_must_match_observation_identity(field: str) -> None:
    with pytest.raises(ValueError):
        _observation(company_read_projection=_projection(**{field: "other-id"}))


def test_projection_requires_typed_exact_delivery() -> None:
    with pytest.raises(ValueError):
        _observation(delivered=False, company_read_projection=_projection())
    with pytest.raises(ValueError):
        _observation(company_read_projection=CONSULT)


@pytest.mark.parametrize("mutation", ["unknown", "missing", "untyped"])
def test_wire_rejects_nested_projection_drift(mutation: str) -> None:
    wire = to_wire(_observation(company_read_projection=_projection()))
    nested = wire["company_read_projection"]
    match = "fields drifted"
    if mutation == "unknown":
        nested["raw_text"] = "must not cross"
    elif mutation == "missing":
        nested.pop("result_sha256")
    else:
        wire["company_read_projection"] = [nested]
        match = "object"
    with pytest.raises(OperatorHarnessWireError, match=match):
        attention_turn_observation(wire)
