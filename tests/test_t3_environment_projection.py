"""T3 environment projection: unknown-safe capabilities, freshness, registry."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from control_plane.t3_environment_projection import (
    CAPABILITY_KEYS,
    CAPABILITY_READY,
    CAPABILITY_UNKNOWN,
    OBSERVATION_SCHEMA,
    PROJECTION_SCHEMA,
    REQUIRED_CAPABILITIES,
    T3EnvironmentObservation,
    T3EnvironmentProjection,
    T3ProjectionError,
    project,
    project_registry,
    to_session_targets,
)
from integrations.session_bridge.schemas import validate_target_ref

HOST_ID = "m2-studio"
ENVIRONMENT_ID = "t3-m2-studio-01"
OBSERVED_AT = "2026-11-08T14:09:03Z"
CLOCK = datetime(2026, 11, 8, 14, 9, 10, tzinfo=timezone.utc)


def host_snapshot(**overrides):
    snapshot = {
        "schema": "mastermind.host_readiness_snapshot/v1",
        "host_id": HOST_ID,
        "role": "coordinator",
        "reachable": True,
        "collected_at": "2026-11-08T14:09:06Z",
        "observed_at_utc": OBSERVED_AT,
        "cores": 24,
        "ram_gib": 192.0,
        "disk_free_gib": {
            "root": 271.65,
            "runtime_dir": 271.65,
            "runtime_dir_path": "$HOME/.hermes (on /System/Volumes/Data)",
        },
        "load_1m": 58.58,
        "uptime_s": 1162959,
        "os": "Darwin",
        "python": "3.12.10",
        "runtimes_present": {
            "hermes": "/Users/chriswong/.hermes/hermes-agent/.hermes/bin/hermes",
            "opencode": "/opt/homebrew/bin/opencode",
            "deepseek": None,
        },
        "thermal": "unknown",
        "proposed_worker_slots": 12,
        "eligible_slots": 0,
        "proposed_thresholds": {"heartbeat_s": 15},
        "unreachable_error": None,
    }
    snapshot.update(overrides)
    return snapshot


def observation(**overrides):
    facts = {
        "environment_id": ENVIRONMENT_ID,
        "server_endpoint": "127.0.0.1:43110",
        "service_state": "running",
        "service_persistence": "lingering",
        "auth_state": "paired",
        "version": "1.4.2",
        "provider_instance_ids": ["provider-instance-1"],
        "reachable": True,
        "observed_at_utc": OBSERVED_AT,
        "source": "wb:t3-environment-census",
    }
    facts.update(overrides)
    return facts


def ready_host(**overrides):
    """A host whose thermal state is actually observed (not the unknown default)."""
    return host_snapshot(thermal="nominal", **overrides)


def test_all_ready_fresh_reachable_projects_ready_and_eligible():
    projection = project(ready_host(), observation(), CLOCK)
    assert isinstance(projection, T3EnvironmentProjection)
    assert set(REQUIRED_CAPABILITIES) <= set(projection.capabilities)
    assert set(projection.capabilities) == set(CAPABILITY_KEYS)
    assert all(state == CAPABILITY_READY for state in projection.capabilities.values())
    assert projection.host_id == HOST_ID
    assert projection.host_reachable is True
    assert projection.launch_eligible is True


def test_missing_observation_facts_are_unknown_never_ready():
    # Only the three identity facts; every other fact is unobserved.
    projection = project(
        ready_host(),
        {
            "environment_id": ENVIRONMENT_ID,
            "observed_at_utc": OBSERVED_AT,
            "source": "wb:t3-environment-census",
        },
        CLOCK,
    )
    for key in (
        "t3_server_reachable",
        "auth",
        "service_persistence",
        "provider_sessions",
    ):
        assert projection.capabilities[key] == CAPABILITY_UNKNOWN
    # An unreachable/unobserved environment never becomes launch eligible.
    assert projection.launch_eligible is False


def test_thermal_unknown_propagates_and_blocks_eligibility():
    projection = project(host_snapshot(thermal="unknown"), observation(), CLOCK)
    assert projection.capabilities["host_thermal"] == CAPABILITY_UNKNOWN
    for key in (
        "host_reachable",
        "t3_server_reachable",
        "auth",
        "service_persistence",
        "provider_sessions",
        "workspace_scratch",
    ):
        assert projection.capabilities[key] == CAPABILITY_READY
    assert projection.launch_eligible is False


def test_missing_thermal_field_is_unknown_not_ready():
    snapshot = host_snapshot()
    snapshot.pop("thermal")
    projection = project(snapshot, observation(), CLOCK)
    assert projection.capabilities["host_thermal"] == CAPABILITY_UNKNOWN
    assert projection.launch_eligible is False


def test_stale_host_snapshot_is_not_launch_eligible():
    projection = project(
        ready_host(), observation(), CLOCK + timedelta(seconds=120)
    )
    # Capabilities still describe the last observation...
    assert all(state == CAPABILITY_READY for state in projection.capabilities.values())
    # ...but neither instant is fresh, so eligibility is refused.
    assert projection.launch_eligible is False


def test_stale_observation_is_not_launch_eligible():
    projection = project(
        ready_host(), observation(observed_at_utc="2026-11-08T14:00:00Z"), CLOCK
    )
    assert projection.launch_eligible is False


def test_future_dated_host_snapshot_is_not_fresh():
    projection = project(
        ready_host(observed_at_utc="2026-11-08T14:10:00Z"),
        observation(observed_at_utc="2026-11-08T14:10:00Z"),
        CLOCK,
    )
    assert projection.launch_eligible is False


def test_freshness_window_is_injectable():
    later = CLOCK + timedelta(seconds=60)
    assert project(ready_host(), observation(), later).launch_eligible is False
    assert (
        project(ready_host(), observation(), later, freshness_window_s=120).launch_eligible
        is True
    )


def test_unreachable_host_degrades_and_never_claims_scratch():
    projection = project(
        ready_host(reachable=False, unreachable_error="ssh timeout"),
        observation(),
        CLOCK,
    )
    assert projection.capabilities["host_reachable"] == "degraded"
    # Last-known free space is not evidence for a host we cannot see now.
    assert projection.capabilities["workspace_scratch"] == CAPABILITY_UNKNOWN
    assert projection.host_reachable is False
    assert projection.launch_eligible is False


def test_stopped_service_degrades_provider_sessions():
    projection = project(
        ready_host(), observation(service_state="stopped"), CLOCK
    )
    assert projection.capabilities["provider_sessions"] == "degraded"
    assert projection.launch_eligible is False


def test_unobserved_provider_listing_is_unknown_not_empty():
    seen = project(
        ready_host(), observation(provider_instance_ids=None), CLOCK
    )
    empty = project(ready_host(), observation(provider_instance_ids=[]), CLOCK)
    assert seen.capabilities["provider_sessions"] == CAPABILITY_UNKNOWN
    # An observed empty listing is real evidence of degradation.
    assert empty.capabilities["provider_sessions"] == "degraded"


def test_unpaired_and_login_bound_states_degrade():
    projection = project(
        ready_host(),
        observation(auth_state="unpaired", service_persistence="login_bound"),
        CLOCK,
    )
    assert projection.capabilities["auth"] == "degraded"
    assert projection.capabilities["service_persistence"] == "degraded"
    assert projection.launch_eligible is False


def test_observation_round_trips_through_its_schema_const():
    facts = T3EnvironmentObservation.from_dict(observation())
    payload = facts.to_dict()
    assert payload["schema"] == OBSERVATION_SCHEMA
    assert T3EnvironmentObservation.from_dict(payload) == facts
    # Missing optional facts default to unknown/None, never to a guess.
    minimal = T3EnvironmentObservation.from_dict(
        {
            "environment_id": ENVIRONMENT_ID,
            "observed_at_utc": OBSERVED_AT,
            "source": "wb:t3-environment-census",
        }
    )
    assert minimal.service_state == CAPABILITY_UNKNOWN
    assert minimal.auth_state == CAPABILITY_UNKNOWN
    assert minimal.provider_instance_ids is None
    assert minimal.reachable is None


def test_projection_round_trips_through_its_schema_const():
    projection = project(ready_host(), observation(), CLOCK)
    payload = projection.to_dict()
    assert payload["schema"] == PROJECTION_SCHEMA
    assert payload["launch_eligible"] is True
    assert T3EnvironmentProjection.from_dict(payload) == projection


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda facts: {**facts, "unexpected": 1}, "OBSERVATION_FIELDS_INVALID"),
        (lambda facts: {**facts, "service_state": "running "}, "SERVICE_STATE_INVALID"),
        (lambda facts: {**facts, "auth_state": "maybe"}, "AUTH_STATE_INVALID"),
        (
            lambda facts: {**facts, "service_persistence": "always"},
            "SERVICE_PERSISTENCE_INVALID",
        ),
        (lambda facts: {**facts, "server_endpoint": "127.0.0.1"}, "SERVER_ENDPOINT_INVALID"),
        (lambda facts: {**facts, "server_endpoint": "127.0.0.1:99999"}, "SERVER_ENDPOINT_INVALID"),
        (lambda facts: {**facts, "reachable": "yes"}, "REACHABLE_INVALID"),
        (lambda facts: {**facts, "observed_at_utc": "2026-11-08 14:09:03"}, "OBSERVED_AT_INVALID"),
        (lambda facts: {**facts, "provider_instance_ids": ["a", "a"]}, "PROVIDER_INSTANCE_IDS_INVALID"),
        (lambda facts: {**facts, "environment_id": ""}, "ENVIRONMENT_ID_INVALID"),
        (lambda facts: {**facts, "source": "  "}, "OBSERVATION_SOURCE_INVALID"),
    ],
)
def test_observation_refuses_malformed_facts(mutate, code):
    with pytest.raises(T3ProjectionError) as exc:
        T3EnvironmentObservation.from_dict(mutate(observation()))
    assert exc.value.code == code


def test_observation_refuses_reachability_without_an_endpoint():
    with pytest.raises(T3ProjectionError) as exc:
        T3EnvironmentObservation.from_dict(
            observation(server_endpoint=None)
        )
    assert exc.value.code == "SERVER_ENDPOINT_REQUIRED"


def test_projection_refuses_forged_eligibility():
    payload = project(host_snapshot(thermal="unknown"), observation(), CLOCK).to_dict()
    payload["launch_eligible"] = True
    with pytest.raises(T3ProjectionError) as exc:
        T3EnvironmentProjection.from_dict(payload)
    assert exc.value.code == "LAUNCH_ELIGIBLE_INCONSISTENT"


def test_projection_refuses_missing_required_capability():
    payload = project(ready_host(), observation(), CLOCK).to_dict()
    payload["capabilities"].pop("workspace_scratch")
    with pytest.raises(T3ProjectionError) as exc:
        T3EnvironmentProjection.from_dict(payload)
    assert exc.value.code == "CAPABILITIES_MISSING"


def test_projection_refuses_ungraded_capability_value():
    payload = project(ready_host(), observation(), CLOCK).to_dict()
    payload["capabilities"]["host_thermal"] = "probably-fine"
    with pytest.raises(T3ProjectionError) as exc:
        T3EnvironmentProjection.from_dict(payload)
    assert exc.value.code == "CAPABILITY_STATE_INVALID"


def test_project_refuses_wrong_host_schema_and_missing_host_id():
    with pytest.raises(T3ProjectionError) as exc:
        project(host_snapshot(schema="mastermind.other/v1"), observation(), CLOCK)
    assert exc.value.code == "HOST_SNAPSHOT_SCHEMA_INVALID"
    snapshot = host_snapshot()
    snapshot.pop("host_id")
    with pytest.raises(T3ProjectionError) as exc:
        project(snapshot, observation(), CLOCK)
    assert exc.value.code == "HOST_ID_INVALID"


def test_to_session_targets_is_a_closed_t3_target_entry():
    projection = project(ready_host(), observation(), CLOCK)
    target = to_session_targets(projection)
    assert target["kind"] == "t3"
    assert target["target_ref"] == f"t3:{ENVIRONMENT_ID}"
    # The projection's ref must satisfy the Session Bridge target-ref grammar.
    assert validate_target_ref(target["target_ref"]) == target["target_ref"]
    assert target["host_id"] == HOST_ID
    assert target["environment_id"] == ENVIRONMENT_ID
    assert target["launch_eligible"] is True
    assert set(target["capabilities"]) == set(CAPABILITY_KEYS)
    assert target["label"] == f"{ENVIRONMENT_ID} on {HOST_ID}"
    assert set(target) == {
        "kind",
        "target_ref",
        "label",
        "host_id",
        "environment_id",
        "capabilities",
        "launch_eligible",
    }


def _write(directory, name, payload):
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_registry_projects_fixture_hosts_and_skips_bad_snapshots(tmp_path):
    _write(tmp_path, "m2-studio.json", ready_host())
    _write(tmp_path, "ubuntu0.json", host_snapshot(host_id="ubuntu0", thermal="nominal"))
    _write(tmp_path, "ubuntu1.json", host_snapshot(host_id="ubuntu1"))  # no observation
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    observations = {
        HOST_ID: observation(),
        "ubuntu0": observation(
            environment_id="t3-ubuntu0-01",
            server_endpoint="10.0.0.7:43110",
            service_state="stopped",
        ),
    }
    projections, notes = project_registry(tmp_path, observations, CLOCK)
    by_host = {projection.host_id: projection for projection in projections}
    assert set(by_host) == {HOST_ID, "ubuntu0"}
    assert by_host[HOST_ID].launch_eligible is True
    assert by_host["ubuntu0"].launch_eligible is False
    assert by_host["ubuntu0"].environment_id == "t3-ubuntu0-01"
    rendered = "\n".join(notes)
    assert "broken.json: unreadable" in rendered
    assert "ubuntu1: no t3 observation supplied" in rendered
    assert isinstance(notes, tuple) and isinstance(projections, tuple)


def test_registry_reports_a_missing_directory_without_raising(tmp_path):
    projections, notes = project_registry(tmp_path / "absent", {}, CLOCK)
    assert projections == ()
    assert len(notes) == 1 and notes[0].startswith("hosts_dir unavailable:")


def test_registry_falls_back_to_the_filename_when_host_id_absent(tmp_path):
    snapshot = ready_host()
    snapshot.pop("host_id")
    _write(tmp_path, f"{HOST_ID}.json", snapshot)
    projections, notes = project_registry(tmp_path, {HOST_ID: observation()}, CLOCK)
    assert [projection.host_id for projection in projections] == [HOST_ID]
    assert f"{HOST_ID}.json: host_id from filename" in notes


def test_registry_skips_a_snapshot_that_breaks_the_closed_contract(tmp_path):
    _write(tmp_path, f"{HOST_ID}.json", ready_host(reachable="true"))
    projections, notes = project_registry(tmp_path, {HOST_ID: observation()}, CLOCK)
    assert projections == ()
    assert f"{HOST_ID}: HOST_REACHABLE_INVALID" in notes


REAL_HOSTS_DIR = Path("/Users/chriswong/.hermes/profiles/engineering/mmos/hosts")


def test_registry_projects_the_real_host_snapshots_when_present():
    """Optional: the live fleet directory is not part of the hermetic contract."""
    if not REAL_HOSTS_DIR.is_dir():
        pytest.skip("no live hosts directory in this environment")
    names = sorted(path.stem for path in REAL_HOSTS_DIR.glob("*.json"))
    observations = {
        name: observation(
            environment_id=f"t3-{name}",
            server_endpoint="127.0.0.1:43110",
        )
        for name in names
    }
    projections, _ = project_registry(REAL_HOSTS_DIR, observations, CLOCK)
    assert [projection.host_id for projection in projections] == names
    for projection in projections:
        # Live snapshots declare thermal unknown, so nothing may be eligible.
        assert projection.capabilities["host_thermal"] == CAPABILITY_UNKNOWN
        assert projection.launch_eligible is False
        assert isinstance(projection.capabilities, Mapping)
