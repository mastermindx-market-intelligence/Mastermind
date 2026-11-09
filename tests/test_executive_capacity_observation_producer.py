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


# ---------------------------------------------------------------------------
# MMOS V1 WO-09 — QuotaEconomicsPreviewProducer (real runtime producer).
# Synthetic rows below are explicitly non-executable test inputs; the
# production path takes only explicit paths and a sealed factory config.
# ---------------------------------------------------------------------------

QUOTA_OBSERVED = "2026-09-17T05:10:00Z"
QUOTA_RESOURCE_FIELDS = frozenset(
    {
        "pool_ref",
        "shared_quota_resource_ref",
        "provider_ref",
        "auth_route_ref",
        "registry_revision",
        "source_owner_ref",
        "observation_id",
        "observed_at",
        "expires_at",
        "readiness_state",
        "configured_concurrency_cap",
        "active_slots",
        "reserved_slots",
        "remaining_quota",
        "reset_at",
        "quota_knowledge",
        "cooldown_until",
        "admission_eligibility",
        "reason_codes",
    }
)


def quota_projection():
    """Minimal real-shape WO-03 projection (no secret material)."""
    return {
        "schema": "mastermind.owner_ext_registry_projection/v1",
        "produced_at": "2026-09-16T14:18:20+00:00",
        "registry_revision": "14259ca4-test-revision",
        "registry_revision_basis": "sha256(pools.yaml bytes || accounts.yaml bytes)",
        "source_owner_ref": {"owner_ext_root": {"path": "/tmp/owner/ext"}},
        "pools": [
            {
                "id": "bailian",
                "enabled": True,
                "access_route": "codex exec via ext/qwen_exec.sh",
                "configured_ceilings": {"concurrent": 21, "per_key": 7},
                "models": {"default": None, "worker_models": ["qwen3.8-flash"]},
                "inline_key_entries": [
                    {
                        "name": "Ryan",
                        "pct_7d": 98.56,
                        "resets_at": "2026-09-16T03:58Z",
                        "parked": True,
                    },
                    {
                        "name": "Chris",
                        "pct_7d": 1.19,
                        "resets_at": "2026-09-16T19:16Z",
                        "parked": False,
                    },
                ],
            },
            {
                "id": "minimax",
                "enabled": True,
                "access_route": "claude -p with MiniMax base URL via ext/sub.sh",
                "configured_ceilings": {"concurrent": 7},
                "models": {"default": "MiniMax-M3"},
                "windows": {"hourly": {"anchor": "5h", "reset_approx": "rolling 5h"}},
            },
            {
                "id": "grok",
                "enabled": True,
                "access_route": "grok -p",
                "configured_ceilings": {"concurrent": 17},
                "models": {"default": None},
                "windows": {
                    "weekly": {
                        "anchor": "weekly",
                        "source": "chairman_provider_screenshot",
                        "observed_at": "2026-09-16T01:37:00Z",
                        "reset_at": "2026-09-16T05:54:00Z",
                        "remaining_pct": 53,
                    }
                },
            },
        ],
        "shared_quota_resources": [
            {
                "provider": "bailian",
                "account_name": "Ryan",
                "enabled_flag": True,
                "per_account_cap": 7,
                "windows": [],
                "parked_until": "2026-09-16T03:58Z",
                "has_credential_ref": True,
                "pool_aliases": ["qwen"],
            },
            {
                "provider": "bailian",
                "account_name": "Chris",
                "enabled_flag": True,
                "per_account_cap": 7,
                "windows": [],
                "parked_until": None,
                "has_credential_ref": True,
                "pool_aliases": ["qwen"],
            },
            {
                "provider": "minimax",
                "account_name": "default",
                "enabled_flag": True,
                "per_account_cap": 7,
                "windows": [{"kind": "5h", "length_hours": 5}],
                "parked_until": None,
                "has_credential_ref": True,
            },
            {
                "provider": "grok",
                "account_name": "default",
                "enabled_flag": True,
                "per_account_cap": None,
                "windows": [{"kind": "weekly", "reset_approx": "Sun 00:00Z"}],
                "parked_until": None,
                "has_credential_ref": True,
            },
            {
                "provider": "bailian",
                "account_name": "Ryan",
                "kind": "inline_key_bucket",
                "pct_7d": 98.56,
            },
            {
                "provider": "bailian",
                "account_name": "Chris",
                "kind": "inline_key_bucket",
                "pct_7d": 1.19,
            },
        ],
        "routing_policy": {"priority_order": ["minimax", "bailian", "grok"]},
    }


def quota_broker(path, *, held=(), released=(), waiters=(), cooldowns=()):
    """Broker sqlite fixture with the deployed table columns."""
    import sqlite3

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE leases (id TEXT PRIMARY KEY, orchestrator_id TEXT, pool TEXT,
            account TEXT, task_class TEXT, host TEXT, pid INTEGER, granted_at REAL,
            ttl INTEGER, last_heartbeat REAL, state TEXT, renewable INTEGER,
            model TEXT, quota_outcome_sha256 TEXT, quota_scope TEXT, purpose TEXT);
        CREATE TABLE waiters (id INTEGER PRIMARY KEY, orchestrator_id TEXT,
            pool TEXT, account TEXT, task_class TEXT, host TEXT, enqueued_at REAL,
            priority INTEGER, need TEXT, last_heartbeat REAL);
        CREATE TABLE quota_cooldowns (scope TEXT, observed_at REAL, until_ts REAL,
            failures INTEGER, kind TEXT, source_run TEXT, reset_source TEXT,
            mode TEXT, soft_cap INTEGER);
        """
    )
    for index, (scope, state) in enumerate(held + released):
        connection.execute(
            "INSERT INTO leases (id, state, quota_scope) VALUES (?, ?, ?)",
            (f"L{index}", state, scope),
        )
    for index, (pool, account) in enumerate(waiters):
        connection.execute(
            "INSERT INTO waiters (id, pool, account) VALUES (?, ?, ?)",
            (index, pool, account),
        )
    for scope, observed_at, until_ts in cooldowns:
        connection.execute(
            "INSERT INTO quota_cooldowns (scope, observed_at, until_ts, failures,"
            " kind, mode) VALUES (?, ?, ?, 20, 'unknown', 'SOFT')",
            (scope, observed_at, until_ts),
        )
    connection.commit()
    connection.close()
    return path


def quota_preview(tmp_path, **broker_kwargs):
    """Produce one preview from synthetic inputs through the real producer."""
    from datetime import datetime, timezone

    from control_plane import executive_capacity_observation_producer as factory
    from control_plane import quota_economics_preview_producer as quota

    projection_path = tmp_path / "owner_ext_projection.json"
    projection_path.write_text(json.dumps(quota_projection()))
    broker_path = quota_broker(tmp_path / "leases.sqlite", **broker_kwargs)
    config = factory.validate_worker_capacity_source_config(source_config())
    return (
        quota.produce_quota_economics_preview(
            source_config=config,
            projection_path=projection_path,
            broker_db_path=broker_path,
            observed_at=QUOTA_OBSERVED,
        ),
        config,
        datetime.strptime(QUOTA_OBSERVED, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ),
    )


def test_quota_preview_envelope_and_resources_round_trip_through_consumer(tmp_path):
    from control_plane import capacity_economics_projection as consumer
    from control_plane import quota_economics_preview_producer as quota

    preview, _, observed = quota_preview(tmp_path)
    document = preview.to_dict()

    assert document["schema"] == consumer.QUOTA_PREVIEW_SCHEMA
    assert document["authority"] == "NONE_PREVIEW_ONLY"
    assert document["binding_verification"] == "NOT_PERFORMED"
    assert document["live_admission"] is False
    assert document["claim_time_revalidation_required"] is True
    assert document["production_armed"] is False
    assert document["status"] == quota.PREVIEW_STATUS_READY
    assert document["as_of"] == QUOTA_OBSERVED
    assert document["expires_at"] == "2026-09-17T05:25:00Z"
    assert document["selected_tier"] == quota.SELECTED_TIER_LABEL
    assert document["suggested_option"] == "bailian:Chris"

    refs = [row["shared_quota_resource_ref"] for row in document["resources"]]
    assert refs == [
        "bailian:Chris",
        "bailian:Ryan",
        "grok:default",
        "minimax:default",
    ]
    for row in document["resources"]:
        assert QUOTA_RESOURCE_FIELDS <= set(row)
        assert row["registry_revision"] == "14259ca4-test-revision"
        assert row["source_owner_ref"] == "owner_ext"
        assert row["observed_at"] == QUOTA_OBSERVED
        assert row["expires_at"] == "2026-09-17T05:25:00Z"

    # The real consumer at capacity_economics_projection.py:19 accepts it.
    freshness = consumer.QuotaPreviewFreshness(
        observed_at=observed,
        verified_at=observed.replace(second=5),
        max_age_seconds=900,
    )
    preference = consumer.project_quota_preference(
        [{"tier_id": "first_lawful_suitability_tier",
          "model_aliases": ["qwen3.8-flash"]}],
        document,
        owner_freshness=freshness,
    )
    assert preference.provider == "bailian"
    assert preference.model_alias == "qwen3.8-flash"
    assert preference.option_id == "bailian:Chris"
    assert preference.estimated_startable_jobs == 7
    assert preference.selection_is_commitment is False
    assert preference.claim_time_revalidation_required is True


def test_one_shared_bucket_stays_one_resource_across_credentials(tmp_path):
    from control_plane import quota_economics_preview_producer as quota

    preview, _, _ = quota_preview(tmp_path)
    document = preview.to_dict()
    # 6 projection rows (4 canonical + 2 inline key buckets) merge into 4
    # resources: the inline 7-day buckets join their canonical keys.
    rows = {
        row["shared_quota_resource_ref"]: row for row in document["resources"]
    }
    assert len(rows) == 4
    ryan = rows["bailian:Ryan"]
    assert ryan["remaining_quota"] == 1.44
    assert ryan["quota_knowledge"] == "observed"
    assert ryan["reset_at"] == "2026-09-16T03:58:00Z"
    assert ryan["readiness_state"] == "parked"
    assert "owner_parked_verdict" in ryan["reason_codes"]
    assert ryan["admission_eligibility"] is False
    chris = rows["bailian:Chris"]
    assert chris["remaining_quota"] == 98.81
    assert chris["quota_knowledge"] == "observed"
    assert chris["readiness_state"] == "ready"
    assert chris["admission_eligibility"] is True
    assert "eligible_in_preview" in chris["reason_codes"]
    grok = rows["grok:default"]
    assert grok["remaining_quota"] == 53
    assert grok["quota_observed_at"] == "2026-09-16T01:37:00Z"
    assert grok["reset_at"] == "2026-09-16T05:54:00Z"
    assert grok["configured_concurrency_cap"] == 17
    assert grok["configured_cap_basis"] == "pools_yaml_concurrent"
    assert grok["admission_eligibility"] is True
    # Only bailian:Chris yields an option: Ryan is parked, grok lists no
    # model alias, and minimax's quota is unknown.
    assert [option["option_id"] for option in document["options"]] == ["bailian:Chris"]


def test_unexposed_provider_quota_stays_null_unknown_and_ineligible(tmp_path):
    preview, _, _ = quota_preview(tmp_path)
    document = preview.to_dict()
    minimax = next(
        row
        for row in document["resources"]
        if row["shared_quota_resource_ref"] == "minimax:default"
    )
    # Nothing is invented for a provider that exposes no usage observation.
    assert minimax["remaining_quota"] is None
    assert minimax["remaining_quota_basis"] is None
    assert minimax["reset_at"] is None
    assert minimax["quota_knowledge"] == "unknown"
    assert minimax["quota_observed_at"] is None
    assert minimax["cooldown_until"] is None
    assert minimax["admission_eligibility"] is False
    assert "quota_unknown_no_bounded_unknown_mode_authorized" in minimax["reason_codes"]
    # Configuration stays labeled configuration, never observed quota.
    assert minimax["configured_concurrency_cap"] == 7
    assert minimax["configured_cap_basis"] == "accounts_yaml_per_account_cap"
    assert document["knowledge_summary"]["observed_vs_unknown"] == "3 observed / 1 unknown"


def test_broker_active_reserved_and_cooldown_counters_map_to_resources(tmp_path):
    from datetime import datetime, timezone

    until = datetime(2026, 9, 17, 6, 0, tzinfo=timezone.utc).timestamp()
    preview, _, _ = quota_preview(
        tmp_path,
        held=(("bailian:Chris", "held"), ("bailian:Chris", "rented")),
        released=(("bailian:Chris", "released"),),
        waiters=(("bailian", "Chris"),),
        cooldowns=(("bailian-adaptive429:Ryan", until - 120, until),),
    )
    document = preview.to_dict()
    rows = {
        row["shared_quota_resource_ref"]: row for row in document["resources"]
    }
    chris = rows["bailian:Chris"]
    assert chris["active_slots"] == 2  # released leases never count as active
    assert chris["reserved_slots"] == 1
    option = next(
        option
        for option in document["options"]
        if option["option_id"] == "bailian:Chris"
    )
    assert option["estimated_startable_jobs"] == 4  # cap 7 - 2 active - 1 reserved
    assert option["suggested_parallelism"] == 4
    ryan = rows["bailian:Ryan"]
    assert ryan["cooldown_until"] == "2026-09-17T06:00:00Z"
    assert ryan["cooldown_source"] == "lease_broker_quota_cooldown"
    assert "cooldown_active" in ryan["reason_codes"]
    assert ryan["admission_eligibility"] is False


def test_quota_preview_inputs_refuse_fail_closed(tmp_path):
    from control_plane import executive_capacity_observation_producer as factory
    from control_plane import quota_economics_preview_producer as quota

    config = factory.validate_worker_capacity_source_config(source_config())
    broker_path = quota_broker(tmp_path / "leases.sqlite")
    bad_projection = tmp_path / "bad.json"
    bad_projection.write_text(json.dumps({"schema": "other/v9"}))
    with pytest.raises(quota.QuotaEconomicsPreviewError) as error:
        quota.produce_quota_economics_preview(
            source_config=config,
            projection_path=bad_projection,
            broker_db_path=broker_path,
            observed_at=QUOTA_OBSERVED,
        )
    assert error.value.code == "QUOTA_PREVIEW_PROJECTION_INVALID"

    missing = tmp_path / "missing" / "leases.sqlite"
    good_projection = tmp_path / "good.json"
    good_projection.write_text(json.dumps(quota_projection()))
    with pytest.raises(quota.QuotaEconomicsPreviewError) as error:
        quota.produce_quota_economics_preview(
            source_config=config,
            projection_path=good_projection,
            broker_db_path=missing,
            observed_at=QUOTA_OBSERVED,
        )
    assert error.value.code == "QUOTA_PREVIEW_BROKER_UNAVAILABLE"
    assert not missing.exists()  # a missing broker is never created


def test_quota_preview_requires_the_sealed_trusted_factory_boundary(tmp_path):
    import inspect

    from control_plane import executive_capacity_observation_producer as factory
    from control_plane import quota_economics_preview_producer as quota

    projection_path = tmp_path / "owner_ext_projection.json"
    projection_path.write_text(json.dumps(quota_projection()))
    broker_path = quota_broker(tmp_path / "leases.sqlite")
    with pytest.raises(TypeError):
        quota.produce_quota_economics_preview(
            source_config=source_config(),  # raw dict, not factory-sealed
            projection_path=projection_path,
            broker_db_path=broker_path,
            observed_at=QUOTA_OBSERVED,
        )
    with pytest.raises(factory.CapacityObservationError):
        # The re-exported sealed dataclass still refuses direct construction.
        factory.WorkerCapacitySourceConfig(**source_config())
    # Only explicit arguments; no pytest-only or environment switches exist.
    signature = inspect.signature(quota.produce_quota_economics_preview)
    assert set(signature.parameters) == {
        "source_config",
        "projection_path",
        "broker_db_path",
        "observed_at",
        "quota_observations_path",
    }
    source = inspect.getsource(quota)
    # No environment reads or test hooks exist on the production path.
    assert "import os" not in source
    assert "getenv" not in source
    assert "monkeypatch" not in source

