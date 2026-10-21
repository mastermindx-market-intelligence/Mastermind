"""Pure producer-core tests for CF2F worker-capacity observations."""
from __future__ import annotations

import hashlib
import json

import pytest

from control_plane import executive_capacity_observation as consumer

HOST = "host-" + "a" * 64
CAPABILITY = "codex_account_2"
OBSERVED = "2026-09-17T05:10:00Z"


def source_config(**changes):
    value = {
        "schema_version": "mastermind.executive_worker_capacity_source_config/v1",
        "host_ref": HOST,
        "capacity_capability_id": CAPABILITY,
        "broker_release_identity_digest": "1" * 64,
        "broker_operation_identity_digest": "2" * 64,
        "broker_generation": 7,
        "executive_peer_policy_digest": "3" * 64,
        "worker_realm_metadata_policy_digest": "4" * 64,
        "provider_binary_identity_digest": "5" * 64,
    }
    value.update(changes)
    return value


def readiness(**changes):
    value = {
        "realm_metadata_valid": True,
        "credential_present": True,
        "credential_metadata_valid": True,
        "provider_binary_attested": True,
        "broker_generation_ready": True,
    }
    value.update(changes)
    return value


def test_builds_exact_consumer_validated_observation():
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(source_config())
    facts = producer.validate_worker_capacity_readiness(readiness())
    observed = producer.build_worker_capacity_observation(
        source_config=config,
        readiness=facts,
        observed_at=OBSERVED,
    )

    assert isinstance(observed, consumer.WorkerCapacityObservation)
    assert observed.host_ref == HOST
    assert observed.capacity_capability_id == CAPABILITY
    assert observed.expires_at == "2026-09-17T05:10:15Z"
    expected_config_digest = hashlib.sha256(
        json.dumps(
            source_config(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert observed.source_config_digest == expected_config_digest
    rendered = consumer.canonical_worker_capacity_observation_json(observed)
    assert not rendered.endswith(b"\n")
    assert json.loads(rendered) == observed.to_dict()


def test_source_config_is_frozen_defensive_and_canonical():
    import dataclasses
    from control_plane import executive_capacity_observation_producer as producer

    raw = source_config()
    config = producer.validate_worker_capacity_source_config(raw)
    raw["host_ref"] = "host-" + "b" * 64
    assert config.host_ref == HOST
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.host_ref = raw["host_ref"]
    wire = config.to_dict()
    wire["capacity_capability_id"] = "tampered"
    assert config.to_dict() == source_config()
    rendered = producer.canonical_worker_capacity_source_config_json(config)
    assert not rendered.endswith(b"\n")
    assert json.loads(rendered) == source_config()
    forbidden = (b"path", b"uid", b"username", b"email", b"account_label", b"secret")
    assert all(token not in rendered.lower() for token in forbidden)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "other"),
        ("host_ref", "macbook"),
        ("host_ref", True),
        ("capacity_capability_id", "a/b"),
        ("capacity_capability_id", "x" * 129),
        ("broker_release_identity_digest", "A" * 64),
        ("broker_operation_identity_digest", "g" * 64),
        ("broker_generation", True),
        ("broker_generation", -1),
        ("broker_generation", 1 << 63),
        ("executive_peer_policy_digest", None),
        ("worker_realm_metadata_policy_digest", "4" * 63),
        ("provider_binary_identity_digest", "5" * 65),
    ],
)
def test_invalid_source_config_refuses_as_config_drift(field, value):
    from control_plane import executive_capacity_observation_producer as producer

    with pytest.raises(consumer.CapacityObservationError) as error:
        producer.validate_worker_capacity_source_config(source_config(**{field: value}))
    assert error.value.code == "CAPACITY_OBSERVE_CONFIG_DRIFT"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        {**source_config(), "provider_home": "/secret"},
    ],
)
def test_source_config_shape_is_closed(raw):
    from control_plane import executive_capacity_observation_producer as producer

    with pytest.raises(consumer.CapacityObservationError, match="CAPACITY_OBSERVE_CONFIG_DRIFT"):
        producer.validate_worker_capacity_source_config(raw)


def test_each_source_identity_field_changes_the_config_digest():
    from control_plane import executive_capacity_observation_producer as producer

    baseline = producer.validate_worker_capacity_source_config(source_config())
    baseline_digest = producer.worker_capacity_source_config_digest(baseline)
    changes = {
        "host_ref": "host-" + "b" * 64,
        "capacity_capability_id": "codex_account_3",
        "broker_release_identity_digest": "a" * 64,
        "broker_operation_identity_digest": "b" * 64,
        "broker_generation": 8,
        "executive_peer_policy_digest": "c" * 64,
        "worker_realm_metadata_policy_digest": "d" * 64,
        "provider_binary_identity_digest": "e" * 64,
    }
    for field, changed in changes.items():
        config = producer.validate_worker_capacity_source_config(
            source_config(**{field: changed})
        )
        assert producer.worker_capacity_source_config_digest(config) != baseline_digest


@pytest.mark.parametrize(
    "field,code",
    [
        ("realm_metadata_valid", "CAPACITY_OBSERVE_REALM_INVALID"),
        ("credential_present", "CAPACITY_OBSERVE_CREDENTIAL_ABSENT"),
        (
            "credential_metadata_valid",
            "CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID",
        ),
        ("provider_binary_attested", "CAPACITY_OBSERVE_BINARY_UNATTESTED"),
        ("broker_generation_ready", "CAPACITY_OBSERVE_GENERATION_UNREADY"),
    ],
)
def test_false_readiness_never_emits_an_observation(field, code):
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(source_config())
    facts = producer.validate_worker_capacity_readiness(readiness(**{field: False}))
    with pytest.raises(consumer.CapacityObservationError) as error:
        producer.build_worker_capacity_observation(
            source_config=config,
            readiness=facts,
            observed_at=OBSERVED,
        )
    assert error.value.code == code


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {**readiness(), "extra": True},
        readiness(credential_present=1),
        readiness(provider_binary_attested="true"),
    ],
)
def test_readiness_shape_and_booleans_are_strict(raw):
    from control_plane import executive_capacity_observation_producer as producer

    with pytest.raises(consumer.CapacityObservationError) as error:
        producer.validate_worker_capacity_readiness(raw)
    assert error.value.code == "CAPACITY_OBSERVE_SCHEMA_INVALID"


def test_builder_requires_validated_sealed_inputs():
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(source_config())
    facts = producer.validate_worker_capacity_readiness(readiness())
    with pytest.raises(TypeError):
        producer.build_worker_capacity_observation(
            source_config=source_config(), readiness=facts, observed_at=OBSERVED
        )
    with pytest.raises(TypeError):
        producer.build_worker_capacity_observation(
            source_config=config, readiness=readiness(), observed_at=OBSERVED
        )
    with pytest.raises(consumer.CapacityObservationError):
        producer.WorkerCapacitySourceConfig(**source_config())
    with pytest.raises(consumer.CapacityObservationError):
        producer.WorkerCapacityReadiness(**readiness())


@pytest.mark.parametrize(
    "observed_at",
    [
        "not-a-time",
        "2026-09-17T05:10:00.000Z",
        "2026-09-17T05:10:00+00:00",
        "2026-02-30T05:10:00Z",
        "9999-12-31T23:59:59Z",
    ],
)
def test_invalid_or_overflowing_observed_time_refuses(observed_at):
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(source_config())
    facts = producer.validate_worker_capacity_readiness(readiness())
    with pytest.raises(consumer.CapacityObservationError) as error:
        producer.build_worker_capacity_observation(
            source_config=config,
            readiness=facts,
            observed_at=observed_at,
        )
    assert error.value.code == "CAPACITY_OBSERVE_SCHEMA_INVALID"


def test_local_unbound_remains_only_a_constructible_historical_canary_identity():
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(
        source_config(host_ref="local-unbound")
    )
    facts = producer.validate_worker_capacity_readiness(readiness())
    observed = producer.build_worker_capacity_observation(
        source_config=config,
        readiness=facts,
        observed_at=OBSERVED,
    )
    assert observed.host_ref == "local-unbound"
    # Remote eligibility remains PR #713's separate fail-closed responsibility.


def test_observation_digest_and_source_digest_change_with_their_owned_inputs():
    from control_plane import executive_capacity_observation_producer as producer

    config = producer.validate_worker_capacity_source_config(source_config())
    facts = producer.validate_worker_capacity_readiness(readiness())
    first = producer.build_worker_capacity_observation(
        source_config=config, readiness=facts, observed_at=OBSERVED
    )
    second = producer.build_worker_capacity_observation(
        source_config=config,
        readiness=facts,
        observed_at="2026-09-17T05:10:01Z",
    )
    changed_config = producer.validate_worker_capacity_source_config(
        source_config(broker_generation=8)
    )
    third = producer.build_worker_capacity_observation(
        source_config=changed_config, readiness=facts, observed_at=OBSERVED
    )
    assert first.observation_digest != second.observation_digest
    assert first.source_config_digest == second.source_config_digest
    assert first.source_config_digest != third.source_config_digest
    assert first.observation_digest != third.observation_digest
