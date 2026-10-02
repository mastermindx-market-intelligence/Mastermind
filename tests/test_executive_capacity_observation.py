"""Pure consumer tests for the frozen CF2F worker-capacity observation wire."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from datetime import datetime, timezone

import pytest

HOST = "host-" + "a" * 64
CAPABILITY = "codex_account_2"
CONFIG_DIGEST = "c" * 64
OBSERVED = "2026-09-16T20:00:00Z"
EXPIRES = "2026-09-16T20:00:15Z"


@pytest.fixture
def api():
    try:
        return importlib.import_module("control_plane.executive_capacity_observation")
    except ModuleNotFoundError:
        pytest.fail("worker-capacity observation consumer is not implemented")


def _ms(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1_000)


def _digest(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observation(**changes):
    supplied_digest = changes.pop("observation_digest", None)
    payload = {
        "schema_version": "mastermind.executive_worker_capacity_observation/v1",
        "host_ref": HOST,
        "capacity_capability_id": CAPABILITY,
        "realm_metadata_valid": True,
        "credential_present": True,
        "credential_metadata_valid": True,
        "provider_binary_attested": True,
        "broker_generation_ready": True,
        "source_config_digest": CONFIG_DIGEST,
        "observed_at": OBSERVED,
        "expires_at": EXPIRES,
    }
    payload.update(changes)
    return {**payload, "observation_digest": supplied_digest or _digest(payload)}


_DEFAULT_VALUE = object()
_DEFAULT_TIME = object()


def validate(api, value=_DEFAULT_VALUE, *, now_ms=_DEFAULT_TIME, **expected):
    return api.validate_worker_capacity_observation(
        observation() if value is _DEFAULT_VALUE else value,
        expected_host_ref=expected.get("host_ref", HOST),
        expected_capacity_capability_id=expected.get("capability_id", CAPABILITY),
        expected_source_config_digest=expected.get("source_config_digest", CONFIG_DIGEST),
        trusted_current_ms=(
            _ms("2026-09-16T20:00:07Z") if now_ms is _DEFAULT_TIME else now_ms
        ),
    )


def test_valid_observation_is_frozen_defensive_and_canonical(api):
    raw = observation()
    fact = validate(api, raw)
    raw["host_ref"] = "host-" + "b" * 64
    assert fact.host_ref == HOST
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.host_ref = raw["host_ref"]
    wire = fact.to_dict()
    wire["capacity_capability_id"] = "tampered"
    assert fact.to_dict() == observation()
    rendered = api.canonical_worker_capacity_observation_json(fact)
    assert not rendered.endswith(b"\n")
    assert json.loads(rendered) == observation()


def test_digest_binds_every_non_digest_field(api):
    raw = observation()
    raw["broker_generation_ready"] = False
    with pytest.raises(api.CapacityObservationError, match="CAPACITY_OBSERVE_DIGEST_INVALID"):
        validate(api, raw)


@pytest.mark.parametrize("field,code", [
    ("realm_metadata_valid", "CAPACITY_OBSERVE_REALM_INVALID"),
    ("credential_present", "CAPACITY_OBSERVE_CREDENTIAL_ABSENT"),
    ("credential_metadata_valid", "CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID"),
    ("provider_binary_attested", "CAPACITY_OBSERVE_BINARY_UNATTESTED"),
    ("broker_generation_ready", "CAPACITY_OBSERVE_GENERATION_UNREADY"),
])
def test_false_readiness_fact_maps_to_closed_refusal(api, field, code):
    with pytest.raises(api.CapacityObservationError) as error:
        validate(api, observation(**{field: False}))
    assert error.value.code == code


@pytest.mark.parametrize("field,value", [
    ("realm_metadata_valid", 1),
    ("credential_present", None),
    ("provider_binary_attested", "true"),
    ("source_config_digest", "C" * 64),
    ("observation_digest", "g" * 64),
])
def test_malformed_boolean_or_digest_refuses(api, field, value):
    raw = observation()
    raw[field] = value
    with pytest.raises(api.CapacityObservationError):
        validate(api, raw)


@pytest.mark.parametrize("expected", [
    {"host_ref": "host-" + "b" * 64},
    {"capability_id": "codex_account_3"},
    {"source_config_digest": "d" * 64},
])
def test_expected_identity_drift_refuses(api, expected):
    with pytest.raises(api.CapacityObservationError) as error:
        validate(api, **expected)
    assert error.value.code == "CAPACITY_OBSERVE_CONFIG_DRIFT"


@pytest.mark.parametrize("now_ms", [
    _ms("2026-09-16T19:59:58Z"),
    _ms("2026-09-16T20:00:17Z"),
])
def test_clock_skew_boundaries_are_accepted(api, now_ms):
    assert validate(api, now_ms=now_ms).host_ref == HOST


@pytest.mark.parametrize("now_ms,code", [
    (_ms("2026-09-16T19:59:57Z") + 999, "CAPACITY_OBSERVE_FUTURE"),
    (_ms("2026-09-16T20:00:17Z") + 1, "CAPACITY_OBSERVE_STALE"),
])
def test_outside_clock_window_refuses(api, now_ms, code):
    with pytest.raises(api.CapacityObservationError) as error:
        validate(api, now_ms=now_ms)
    assert error.value.code == code


@pytest.mark.parametrize("changes", [
    {"expires_at": "2026-09-16T20:00:14Z"},
    {"expires_at": "2026-09-16T20:00:16Z"},
    {"observed_at": "2026-09-16T20:00:00.000Z"},
    {"observed_at": "2026-09-16T20:00:00+00:00"},
    {"expires_at": "not-a-time"},
])
def test_lifetime_or_timestamp_drift_refuses(api, changes):
    with pytest.raises(api.CapacityObservationError) as error:
        validate(api, observation(**changes))
    assert error.value.code == "CAPACITY_OBSERVE_SCHEMA_INVALID"


def test_trusted_time_is_explicit_and_strict(api):
    for value in (None, True, -1, 1.5, "2026-09-16T20:00:07Z"):
        with pytest.raises(api.CapacityObservationError, match="CAPACITY_OBSERVE_SCHEMA_INVALID"):
            validate(api, now_ms=value)


@pytest.mark.parametrize("raw", [
    None,
    [],
    {},
    {**observation(), "provider_home": "/secret"},
])
def test_observation_shape_is_closed(api, raw):
    with pytest.raises(api.CapacityObservationError) as error:
        validate(api, raw)
    assert error.value.code == "CAPACITY_OBSERVE_SCHEMA_INVALID"


@pytest.mark.parametrize("changes", [
    {"schema_version": "other"},
    {"host_ref": "macbook"},
    {"host_ref": True},
    {"capacity_capability_id": "a/b"},
    {"capacity_capability_id": "x" * 129},
])
def test_invalid_schema_or_identity_refuses(api, changes):
    with pytest.raises(api.CapacityObservationError):
        validate(api, observation(**changes))


def test_canonical_wire_is_bounded_and_contains_no_unowned_fields(api):
    fact = validate(api)
    rendered = api.canonical_worker_capacity_observation_json(fact)
    assert len(rendered) <= 4_096
    forbidden = (b"auth", b"path", b"uid", b"email", b"account_label", b"provider_session")
    assert all(item not in rendered.lower() for item in forbidden)


def test_canonical_renderer_rejects_unvalidated_mapping(api):
    with pytest.raises(TypeError):
        api.canonical_worker_capacity_observation_json(observation())
