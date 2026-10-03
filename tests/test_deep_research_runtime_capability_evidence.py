from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

from control_plane import chairman_control_room
from integrations.mastermind_steward_app.runtime_capability_evidence import (
    RuntimeCapabilityProjectionError,
    project_runtime_capability_evidence,
)
from integrations.studio_direct_mcp.read_evidence import (
    OBSERVATION_SCHEMA,
    ObservationQuality,
    StudioDirectEvidenceError,
    parse_studio_direct_read_observation,
    project_studio_direct_read_capabilities,
)


OBSERVED = "2026-10-03T07:07:22.197Z"
GENERATION = "74cffcb7-f835-4ac5-b56c-d9bf55019ab3"


def _raw(**overrides):
    value = {
        "schema": OBSERVATION_SCHEMA,
        "observed_at": OBSERVED,
        "gateway_generation": GENERATION,
        "gateway_version": "0.1.7",
        "backend_version": "0.2.50",
        "quality": "COMPLETE",
        "gateway_reachable": True,
        "file_read_exposed": True,
        "file_read_proven": True,
        "terminal_read_probe_exposed": True,
        "terminal_read_probe_proven": True,
    }
    value.update(overrides)
    return value


def _control_room(generated_at: str = "2026-10-03T07:07:22Z"):
    return chairman_control_room.compose_control_room(
        inbox=None,
        boot_packet=None,
        active_builds=None,
        bindings=None,
        generated_at=generated_at,
    )


def _state(status):
    return {
        "control_room": _control_room(),
        "runtime_capability_status": status.to_dict(),
    }


def _by_name(status):
    return {item.name: item for item in status.capabilities}


def test_producer_projects_live_gateway_file_and_terminal_probe_through_cap1():
    receipt = parse_studio_direct_read_observation(_raw())
    status = project_studio_direct_read_capabilities(receipt)
    rows = _by_name(status)

    assert status.schema == "mastermind.sol_capability_status.v1"
    assert status.capability_generation == f"studio-direct-{GENERATION}"
    assert status.observed_at == "2026-10-03T07:07:22.197000Z"
    assert set(rows) == {
        "studio_direct_reachability",
        "studio_direct_file_read",
        "studio_direct_terminal_read_probe",
    }
    for row in rows.values():
        assert row.app_id == "studio-direct"
        assert row.app_generation == GENERATION
        assert row.privilege_class.value == "R0_OBSERVE"
        assert row.proof_state.value == "PROVEN_LIVE"
        assert row.availability.value == "AVAILABLE"
        assert row.read_serviceable is True
        assert row.write_serviceable is False
        assert row.last_proven_at == "2026-10-03T07:07:22.197000Z"
        assert row.canonical_owner == "studio-direct"
        assert row.source_refs == ("studio-direct:read-evidence",)


def test_exposed_but_unproven_read_stays_distinct_from_proven_live():
    receipt = parse_studio_direct_read_observation(
        _raw(file_read_proven=False)
    )
    row = _by_name(project_studio_direct_read_capabilities(receipt))[
        "studio_direct_file_read"
    ]

    assert row.availability.value == "AVAILABLE"
    assert row.proof_state.value == "BUILT_NOT_PROVEN"
    assert row.read_serviceable is True
    assert row.last_proven_at is None
    assert "LIVE_PROOF_MISSING" in row.issues


def test_unavailable_and_unknown_are_not_promoted_to_false_green():
    receipt = parse_studio_direct_read_observation(
        _raw(
            quality="UNAVAILABLE",
            gateway_reachable=False,
            file_read_exposed=None,
            file_read_proven=False,
            terminal_read_probe_exposed=None,
            terminal_read_probe_proven=False,
        )
    )
    rows = _by_name(project_studio_direct_read_capabilities(receipt))

    assert rows["studio_direct_reachability"].availability.value == "UNAVAILABLE"
    assert rows["studio_direct_reachability"].proof_state.value == "DARK_OR_DISCONNECTED"
    assert rows["studio_direct_file_read"].availability.value == "UNKNOWN"
    assert rows["studio_direct_terminal_read_probe"].availability.value == "UNKNOWN"
    assert "SOURCE_UNAVAILABLE" in rows["studio_direct_file_read"].issues


def test_ambiguous_observation_preserves_known_ping_and_unknown_subcapabilities():
    receipt = parse_studio_direct_read_observation(
        _raw(
            quality="AMBIGUOUS",
            file_read_exposed=None,
            file_read_proven=False,
            terminal_read_probe_exposed=None,
            terminal_read_probe_proven=False,
        )
    )
    rows = _by_name(project_studio_direct_read_capabilities(receipt))

    assert rows["studio_direct_reachability"].proof_state.value == "PROVEN_LIVE"
    assert rows["studio_direct_file_read"].availability.value == "UNKNOWN"
    assert rows["studio_direct_terminal_read_probe"].availability.value == "UNKNOWN"
    assert "OBSERVATION_AMBIGUOUS" in rows["studio_direct_file_read"].issues


@pytest.mark.parametrize(
    "overrides",
    [
        {"file_read_exposed": False, "file_read_proven": True},
        {
            "gateway_reachable": False,
            "terminal_read_probe_exposed": True,
            "terminal_read_probe_proven": True,
        },
    ],
)
def test_contradictory_observer_claims_are_refused_before_projection(overrides):
    with pytest.raises(StudioDirectEvidenceError):
        parse_studio_direct_read_observation(_raw(**overrides))


@pytest.mark.parametrize("field", ["path", "command", "session_id", "profile_path", "credential"])
def test_receipt_refuses_private_or_execution_fields_entirely(field):
    raw = _raw()
    raw[field] = "must-never-enter-the-receipt"
    with pytest.raises(StudioDirectEvidenceError):
        parse_studio_direct_read_observation(raw)


def test_receipt_refuses_secret_shaped_generation():
    with pytest.raises(StudioDirectEvidenceError):
        parse_studio_direct_read_observation(
            _raw(gateway_generation="github_pat_not-a-generation")
        )


def test_synthetic_producer_control_room_steward_journey_is_fresh_and_source_attributed():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(_raw())
    )
    projection = project_runtime_capability_evidence(
        _state(status),
        now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
    )

    assert projection.schema == "mastermind.steward_runtime_capability_evidence.v1"
    assert projection.control_room_schema == "mastermind.chairman_control_room.v1"
    assert projection.capability_generation == f"studio-direct-{GENERATION}"
    assert projection.observed_at == "2026-10-03T07:07:22.197000Z"
    assert projection.freshness == "FRESH"
    assert projection.issues == ()
    assert len(projection.records) == 3

    records = {record.capability_id: record for record in projection.records}
    file_record = records["studio_direct_file_read"]
    assert file_record.canonical_owner == "studio-direct"
    assert file_record.source_refs == ("studio-direct:read-evidence",)
    assert file_record.app_generation == GENERATION
    assert file_record.proof_state == "PROVEN_LIVE"
    assert file_record.availability == "AVAILABLE"
    assert file_record.read_serviceable is True
    assert file_record.write_serviceable is False
    assert file_record.freshness == "FRESH"

    public = json.dumps(projection.to_dict(), sort_keys=True).lower()
    for forbidden in (
        "/users/",
        "/private/",
        "command",
        "session_id",
        "profile_path",
        "credential",
        "bearer",
        "github_pat_",
    ):
        assert forbidden not in public


def test_stale_capability_epoch_stays_visible_but_stale():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(_raw())
    )
    projection = project_runtime_capability_evidence(
        _state(status),
        now=datetime(2026, 10, 3, 7, 30, 0, tzinfo=timezone.utc),
    )

    assert projection.freshness == "STALE"
    assert "STALE_SOURCE" in projection.issues
    assert {record.freshness for record in projection.records} == {"STALE"}


def test_missing_capability_source_is_explicit_unknown_not_empty_success():
    projection = project_runtime_capability_evidence(
        {"control_room": _control_room()},
        now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
    )

    assert projection.freshness == "UNKNOWN"
    assert projection.records == ()
    assert projection.issues == ("RUNTIME_CAPABILITY_SOURCE_MISSING",)


def test_unavailable_capability_source_survives_steward_projection():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(
            _raw(
                quality="UNAVAILABLE",
                gateway_reachable=False,
                file_read_exposed=None,
                file_read_proven=False,
                terminal_read_probe_exposed=None,
                terminal_read_probe_proven=False,
            )
        )
    )
    projection = project_runtime_capability_evidence(
        _state(status),
        now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
    )
    records = {record.capability_id: record for record in projection.records}

    assert records["studio_direct_reachability"].availability == "UNAVAILABLE"
    assert records["studio_direct_file_read"].availability == "UNKNOWN"
    assert records["studio_direct_terminal_read_probe"].availability == "UNKNOWN"


def test_malformed_or_duplicate_runtime_capability_status_is_refused():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(_raw())
    ).to_dict()

    malformed = _state(
        project_studio_direct_read_capabilities(
            parse_studio_direct_read_observation(_raw())
        )
    )
    malformed["runtime_capability_status"] = copy.deepcopy(status)
    malformed["runtime_capability_status"]["capabilities"][0]["canonical_owner"] = "wrong-owner"
    with pytest.raises(RuntimeCapabilityProjectionError):
        project_runtime_capability_evidence(
            malformed,
            now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
        )

    duplicate = _state(
        project_studio_direct_read_capabilities(
            parse_studio_direct_read_observation(_raw())
        )
    )
    duplicate["runtime_capability_status"] = copy.deepcopy(status)
    duplicate["runtime_capability_status"]["capabilities"].append(
        copy.deepcopy(duplicate["runtime_capability_status"]["capabilities"][0])
    )
    with pytest.raises(RuntimeCapabilityProjectionError):
        project_runtime_capability_evidence(
            duplicate,
            now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
        )


def test_control_room_schema_mismatch_is_refused():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(_raw())
    )
    state = _state(status)
    state["control_room"] = dict(state["control_room"])
    state["control_room"]["schema"] = "not-control-room"

    with pytest.raises(RuntimeCapabilityProjectionError):
        project_runtime_capability_evidence(
            state,
            now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
        )


def test_partial_observation_stays_partial_or_unknown_per_subcapability():
    receipt = parse_studio_direct_read_observation(
        _raw(
            quality="PARTIAL",
            file_read_proven=False,
            terminal_read_probe_exposed=None,
            terminal_read_probe_proven=False,
        )
    )
    rows = _by_name(project_studio_direct_read_capabilities(receipt))

    assert rows["studio_direct_reachability"].proof_state.value == "PROVEN_LIVE"
    assert "OBSERVATION_PARTIAL" in rows["studio_direct_reachability"].issues
    assert rows["studio_direct_file_read"].proof_state.value == "BUILT_NOT_PROVEN"
    assert rows["studio_direct_terminal_read_probe"].availability.value == "UNKNOWN"
    assert "OBSERVATION_PARTIAL" in rows["studio_direct_terminal_read_probe"].issues


def test_control_room_and_capability_epochs_must_be_composed_close_together():
    status = project_studio_direct_read_capabilities(
        parse_studio_direct_read_observation(_raw())
    )
    state = {
        "control_room": _control_room("2026-10-03T06:00:00Z"),
        "runtime_capability_status": status.to_dict(),
    }
    projection = project_runtime_capability_evidence(
        state,
        now=datetime(2026, 10, 3, 7, 10, 0, tzinfo=timezone.utc),
    )

    assert projection.freshness == "UNKNOWN"
    assert "CONTROL_ROOM_EPOCH_MISMATCH" in projection.issues
    assert {record.freshness for record in projection.records} == {"UNKNOWN"}
