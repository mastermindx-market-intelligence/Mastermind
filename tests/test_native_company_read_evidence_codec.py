"""Pure codec tests for control_plane.wake_ledger.NativeCompanyReadEvidence."""
import dataclasses, pytest
from control_plane.wake_ledger import NativeCompanyReadEvidence, WakeLedgerError

def _d(**overrides):
    base = {
        "target_attempt_id": "ATT-" + "a" * 32,
        "process_generation_id": "gen-a",
        "binding_id": "bind-abcdefgh",
        "nudge_id": "NUDGE-" + "b" * 32,
        "binding_generation": 1,
        "consultation_ref": "consult-" + "c" * 32,
        "provider_session_sha256": "1" * 64,
        "provider_native_turn_sha256": "2" * 64,
        "result_sha256": "3" * 64,
        "native_item_sha256": "4" * 64,
        "answer_attestation_sha256": "5" * 64,
    }
    base.update(overrides)
    return base

DIGESTS = ("provider_session_sha256", "provider_native_turn_sha256", "result_sha256", "native_item_sha256", "answer_attestation_sha256")

def test_roundtrip_and_eleven_fields():
    evidence = NativeCompanyReadEvidence(**_d())
    payload = evidence.to_dict()
    assert isinstance(payload, dict) and len(payload) == 11
    assert set(payload) == set(_d())
    assert NativeCompanyReadEvidence.from_dict(payload) == evidence

def test_immutable_and_error_is_value_error():
    assert issubclass(WakeLedgerError, ValueError)
    evidence = NativeCompanyReadEvidence(**_d())
    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.binding_generation = 2

@pytest.mark.parametrize("field", DIGESTS)
@pytest.mark.parametrize("bad", ["", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "0" * 63 + "Z"])
def test_malformed_digest_rejected(field, bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(**{field: bad}))

@pytest.mark.parametrize("field", sorted(_d()))
def test_missing_field_rejected(field):
    payload = _d()
    del payload[field]
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(payload)

@pytest.mark.parametrize("field", ["extra", "provider_session_id", "provider_native_turn_id"])
def test_unknown_and_raw_alias_fields_rejected(field):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(**{field: "x"}))

@pytest.mark.parametrize("alias,canonical", [("provider_session_id", "provider_session_sha256"), ("provider_native_turn_id", "provider_native_turn_sha256")])
def test_raw_alias_cannot_replace_canonical(alias, canonical):
    payload = _d()
    payload[alias] = payload.pop(canonical)
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(payload)

@pytest.mark.parametrize("bad", [None, [], (), "x", 7, 3.5, b"x"])
def test_non_mapping_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(bad)

@pytest.mark.parametrize("bad", ["ATT-" + "a" * 31, "ATT-" + "a" * 33, "ATT-" + "A" * 32, "att-" + "a" * 32, "ATT-" + "g" * 32, "ATT"])
def test_malformed_target_attempt_id_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(target_attempt_id=bad))

@pytest.mark.parametrize("bad", ["", ".gen", "gen a", "gen/a", "g" * 129, 5])
def test_malformed_process_generation_id_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(process_generation_id=bad))

@pytest.mark.parametrize("bad", [True, False, 0, -1, "1", 1.0, 1.5, None])
def test_malformed_binding_generation_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(binding_generation=bad))

@pytest.mark.parametrize("bad", ["NUDGE-" + "b" * 31, "NUDGE-" + "b" * 33, "NUDGE-" + "B" * 32, "nudge-" + "b" * 32, "NUDGE-" + "z" * 32, "NUDGE"])
def test_malformed_nudge_id_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(nudge_id=bad))

@pytest.mark.parametrize("bad", ["", "bind-a", "BIND-abcdefgh", "bind-ABCDEFGH", "bind-" + "a" * 65, 5])
def test_malformed_binding_id_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(binding_id=bad))

@pytest.mark.parametrize("bad", ["consult-" + "c" * 31, "consult-" + "c" * 33, "consult-" + "C" * 32, "consults-" + "c" * 32, "consult-", "consult-" + "z" * 32])
def test_malformed_consultation_ref_rejected(bad):
    with pytest.raises(ValueError):
        NativeCompanyReadEvidence.from_dict(_d(consultation_ref=bad))
