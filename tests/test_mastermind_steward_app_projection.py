from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone

import pytest

from integrations.mastermind_secretary_mcp.adapter import SecretaryGroundingGateway
from integrations.mastermind_secretary_mcp.schemas import TOOL_REQUIRED_PREDICATES
from integrations.mastermind_steward_app.projection import (
    ControlRoomStewardReadPort,
    ProjectionError,
    responsibility_ref_for,
)


NOW = datetime(2026, 9, 1, 12, 5, 0, tzinfo=timezone.utc)


def _snapshot(*, generated_at: str = "2026-09-01T12:04:00Z") -> dict:
    return {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": generated_at,
        "sources": {
            "agent_os_state_generated_at": "2026-09-01T12:03:00Z",
            "runtime_db_present": True,
            "bindings_path_present": True,
        },
        "degraded": [],
        "attention": {
            "chairman": [],
            "ceo": [
                {
                    "attention_id": "ATTENTION-RAW-001",
                    "kind": "decision",
                    "target": "ceo",
                    "source": "agent_os",
                    "job_id": None,
                    "workstream": "WS:ALPHA",
                    "status": None,
                    "reason": "Ship or hold the Alpha One rollout?",
                    "evidence": [],
                    "existing_next_actions": [],
                }
            ],
            "coo": [],
        },
        "work": [
            {
                "work_ref": "WS:ALPHA",
                "agent_os": {
                    "title": "Alpha program",
                    "program": "Alpha One",
                    "next_action": "Get the CEO ruling on ship vs hold",
                    "status": "in_progress",
                    "state": "in_progress",
                    "reason_code": "workstream_active",
                    "reason": "Authored workstream status is active.",
                    "depends_on": [],
                    "unmet_dependencies": [],
                },
                "executive": {
                    "jobs": [
                        {
                            "job_id": "JOB-RAW-001",
                            "status": "queued",
                            "workstream": "WS:ALPHA",
                        }
                    ],
                    "joined_by": "ceo_intent_provenance",
                },
                "github": {"prs": []},
                "attention_ids": ["ATTENTION-RAW-001"],
                "bindings": [
                    {
                        "binding_id": "11111111-1111-4111-8111-111111111111",
                        "work_ref": "WS:ALPHA",
                        "role": "ceo",
                        "provider": "chatgpt",
                        "seat_ref": "SEAT-RAW-001",
                        "locator_kind": "chat",
                        "observed_at": "2026-09-01T12:03:30Z",
                        "last_verified_at": "2026-09-01T12:04:30Z",
                    }
                ],
                "disagreements": [],
            }
        ],
        "unjoined_open_prs": [],
        "unbound_surfaces": [],
        "binding_conflicts": [],
    }


def _port(snapshot: dict, calls: list[int] | None = None):
    def provider():
        if calls is not None:
            calls.append(1)
        return snapshot

    return ControlRoomStewardReadPort(
        provider,
        clock=lambda: NOW,
        stale_after_seconds=900,
    )


def test_public_responsibility_ref_uses_frozen_domain_and_is_opaque():
    first = responsibility_ref_for("WS:ALPHA")
    second = responsibility_ref_for("WS:ALPHA")
    expected = "responsibility:" + hashlib.sha256(
        b"mastermind-steward-responsibility-v1\x00" + b"WS:ALPHA"
    ).hexdigest()
    assert first == second == expected
    assert "ALPHA" not in first
    assert len(first) == len("responsibility:") + 64


def test_list_responsibilities_projects_closed_facts_and_calls_source_once():
    calls: list[int] = []
    result = asyncio.run(_port(_snapshot(), calls).list_responsibilities())
    assert len(calls) == 1
    assert result.state == "FACTS"
    assert result.reason_codes == ()
    assert [fact.predicate for fact in result.facts] == [
        "responsibility.identity",
        "responsibility.title",
        "responsibility.next_action",
        "responsibility.state",
    ]
    assert [fact.value for fact in result.facts] == [
        "WS:ALPHA",
        "Alpha program",
        "Get the CEO ruling on ship vs hold",
        "ACTIVE",
    ]
    assert result.facts[0].sources[0].source_ref == "WS:ALPHA"


def test_attention_runtime_blocker_and_surface_projection():
    port = _port(_snapshot())
    ref = responsibility_ref_for("WS:ALPHA")

    responsibility = asyncio.run(port.get_responsibility(ref))
    responsibility_values = {
        fact.predicate: fact.value for fact in responsibility.facts
    }
    assert responsibility.state == "DEGRADED"
    assert responsibility.reason_codes == ("NO_SOURCE",)
    assert responsibility_values == {
        "responsibility.identity": "WS:ALPHA",
        "responsibility.title": "Alpha program",
        "responsibility.next_action": "Get the CEO ruling on ship vs hold",
        "responsibility.state": "ACTIVE",
    }
    assert "responsibility.objective" not in responsibility_values

    attention = asyncio.run(port.get_attention())
    attention_values = {fact.predicate: fact.value for fact in attention.facts}
    assert attention.state == "DEGRADED"
    assert attention.reason_codes == ("NO_SOURCE",)
    assert attention_values == {
        "attention.ref": "EXEC:" + hashlib.sha256(
            b"mastermind.steward.source.v1\0attention\0ATTENTION-RAW-001"
        ).hexdigest(),
        "attention.target_seat": "CEO",
        "attention.kind": "decision",
        "attention.reason": "Ship or hold the Alpha One rollout?",
        "attention.state": "SOL_REQUIRED",
    }
    assert "attention.requested_action" not in attention_values

    runtime = asyncio.run(port.get_current_runtime(ref))
    values = {fact.predicate: fact.value for fact in runtime.facts}
    assert runtime.state == "DEGRADED"
    assert runtime.reason_codes == ("EFFECT_UNKNOWN", "RUNTIME_UNKNOWN")
    assert values["runtime.state"] == "IDLE"
    assert values["runtime.effect_state"] == "EFFECT_UNKNOWN"
    assert isinstance(values["runtime.age_seconds"], int)
    assert "runtime.continuity" not in values
    assert "runtime.continuation" not in values

    blocker = asyncio.run(port.explain_blocker(ref))
    values = {fact.predicate: fact.value for fact in blocker.facts}
    assert values == {
        "blocker.present": False,
        "blocker.kind": "NONE",
        "blocker.explanation": "Authored workstream status is active.",
    }

    surface = asyncio.run(port.resolve_surface(ref))
    values = {fact.predicate: fact.value for fact in surface.facts}
    assert surface.state == "DEGRADED"
    assert surface.reason_codes == ("SURFACE_UNKNOWN",)
    assert values["surface.locator_kind"] == "chat"
    assert values["surface.review_state"] == "UNKNOWN"
    assert values["surface.health"] == "UNKNOWN"
    assert "surface.ref" not in values
    assert "surface.repair_required" not in values
    assert {fact.sources[0].owner for fact in surface.facts} == {
        "surface_bindings"
    }
    assert all(
        fact.sources[0].source_ref.startswith("surface-binding:")
        for fact in surface.facts
    )


def test_raw_operational_identifiers_never_cross_projection_boundary():
    port = _port(_snapshot())
    ref = responsibility_ref_for("WS:ALPHA")
    results = [
        asyncio.run(port.list_responsibilities()),
        asyncio.run(port.get_responsibility(ref)),
        asyncio.run(port.get_attention()),
        asyncio.run(port.get_current_runtime(ref)),
        asyncio.run(port.explain_blocker(ref)),
        asyncio.run(port.resolve_surface(ref)),
    ]
    wire = json.dumps(
        [
            {
                "state": result.state,
                "reasons": result.reason_codes,
                "facts": [
                    {
                        "subject": fact.subject_ref,
                        "predicate": fact.predicate,
                        "value": fact.value,
                        "freshness": fact.freshness,
                        "sources": [
                            {
                                "owner": source.owner,
                                "source_ref": source.source_ref,
                                "observed_at": source.observed_at,
                            }
                            for source in fact.sources
                        ],
                    }
                    for fact in result.facts
                ],
            }
            for result in results
        ],
        sort_keys=True,
    )
    for raw in (
        "JOB-RAW-001",
        "ATTENTION-RAW-001",
        "11111111-1111-4111-8111-111111111111",
        "SEAT-RAW-001",
    ):
        assert raw not in wire


def test_unknown_public_ref_is_explicit():
    result = asyncio.run(
        _port(_snapshot()).get_responsibility("responsibility:" + "f" * 64)
    )
    assert result.state == "UNKNOWN"
    assert result.reason_codes == ("RESPONSIBILITY_UNKNOWN",)
    assert result.facts == ()


def test_stale_and_future_observations_degrade_instead_of_looking_fresh():
    stale = _snapshot(generated_at="2026-09-01T10:00:00Z")
    stale["sources"]["agent_os_state_generated_at"] = "2026-09-01T10:00:00Z"
    stale["work"][0]["bindings"][0]["last_verified_at"] = "2026-09-01T10:00:00Z"
    result = asyncio.run(_port(stale).list_responsibilities())
    assert result.state == "DEGRADED"
    assert "STALE_SOURCE" in result.reason_codes

    future = _snapshot(generated_at="2026-09-01T13:00:00Z")
    future["sources"]["agent_os_state_generated_at"] = "2026-09-01T13:00:00Z"
    result = asyncio.run(_port(future).list_responsibilities())
    assert result.state == "DEGRADED"
    assert "STALE_SOURCE" in result.reason_codes

    slight_future = _snapshot(generated_at="2026-09-01T12:05:01Z")
    slight_future["sources"][
        "agent_os_state_generated_at"
    ] = "2026-09-01T12:05:01Z"
    result = asyncio.run(_port(slight_future).list_responsibilities())
    assert result.state == "DEGRADED"
    assert "STALE_SOURCE" in result.reason_codes
    assert {fact.freshness for fact in result.facts} == {"UNKNOWN"}


def test_subsecond_future_observation_never_truncates_to_fresh():
    snapshot = _snapshot(generated_at="2026-09-01T12:05:01Z")
    snapshot["sources"]["agent_os_state_generated_at"] = "2026-09-01T12:05:01Z"
    port = ControlRoomStewardReadPort(
        lambda: snapshot,
        clock=lambda: datetime(
            2026,
            9,
            1,
            12,
            5,
            0,
            900_000,
            tzinfo=timezone.utc,
        ),
        stale_after_seconds=900,
    )

    result = asyncio.run(port.list_responsibilities())

    assert result.state == "DEGRADED"
    assert "STALE_SOURCE" in result.reason_codes
    assert {fact.freshness for fact in result.facts} == {"UNKNOWN"}


def test_duplicate_work_identity_is_refused_not_last_wins():
    snapshot = _snapshot()
    snapshot["work"].append(dict(snapshot["work"][0]))
    with pytest.raises(ProjectionError, match="AMBIGUOUS_JOIN"):
        asyncio.run(_port(snapshot).list_responsibilities())


def test_foreign_control_room_schema_is_unavailable_and_never_parsed():
    snapshot = _snapshot()
    snapshot["schema"] = "foreign.control_room.v9"
    snapshot["work"][0]["agent_os"]["title"] = "must-not-cross"
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            "list_responsibilities",
            {},
        )
    )

    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == {
        "code": "STEWARD_UNAVAILABLE",
        "message": "STEWARD_UNAVAILABLE",
    }
    assert "must-not-cross" not in json.dumps(result, sort_keys=True)


@pytest.mark.parametrize(
    "tool_name",
    ["get_attention", "get_current_runtime", "resolve_surface"],
)
def test_cross_card_source_rows_are_ambiguous_and_never_projected(tool_name: str):
    snapshot = _snapshot()
    if tool_name == "get_attention":
        snapshot["attention"]["ceo"][0]["workstream"] = "WS:BETA"
        snapshot["attention"]["ceo"][0]["reason"] = "must-not-cross"
        arguments = {}
    elif tool_name == "get_current_runtime":
        snapshot["work"][0]["executive"]["jobs"][0]["workstream"] = "WS:BETA"
        arguments = {"responsibility_ref": responsibility_ref_for("WS:ALPHA")}
    else:
        snapshot["work"][0]["bindings"][0]["work_ref"] = "WS:BETA"
        snapshot["work"][0]["bindings"][0]["locator_kind"] = "must-not-cross"
        arguments = {"responsibility_ref": responsibility_ref_for("WS:ALPHA")}

    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(tool_name, arguments)
    )

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "AMBIGUOUS_JOIN" in result["data"]["reason_codes"]
    assert "must-not-cross" not in json.dumps(result, sort_keys=True)


def test_attention_bucket_target_disagreement_never_selects_a_winner():
    snapshot = _snapshot()
    snapshot["attention"]["ceo"][0]["target"] = "coo"
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call("get_attention", {})
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "AMBIGUOUS_JOIN" in result["data"]["reason_codes"]


@pytest.mark.parametrize("source", ["runtime", "unknown"])
def test_bare_attention_workstream_is_only_valid_for_agent_os_source(
    source: str,
):
    snapshot = _snapshot()
    snapshot["attention"]["ceo"][0]["source"] = source
    snapshot["attention"]["ceo"][0]["workstream"] = "ALPHA"
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call("get_attention", {})
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "AMBIGUOUS_JOIN" in result["data"]["reason_codes"]


def test_unrecognized_responsibility_state_does_not_fabricate_no_blocker():
    snapshot = _snapshot()
    snapshot["work"][0]["agent_os"]["state"] = "mystery"
    snapshot["work"][0]["agent_os"]["status"] = "mystery"
    snapshot["work"][0]["agent_os"]["reason"] = "State is not recognized."
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            "explain_blocker",
            {"responsibility_ref": ref},
        )
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "DEGRADED"
    assert "STEWARD_DEGRADED" in result["data"]["reason_codes"]
    facts = {
        fact["predicate"]: fact["value"]
        for fact in result["data"]["subjects"][0]["facts"]
    }
    assert facts == {"blocker.explanation": "State is not recognized."}


def test_conflicting_agent_states_do_not_fabricate_blocker_absence():
    snapshot = _snapshot()
    snapshot["work"][0]["agent_os"]["state"] = "in_progress"
    snapshot["work"][0]["agent_os"]["status"] = "blocked"
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).explain_blocker(ref))
    values = {fact.predicate: fact.value for fact in result.facts}

    assert result.state == "DEGRADED"
    assert "AMBIGUOUS_JOIN" in result.reason_codes
    assert "blocker.present" not in values
    assert "blocker.kind" not in values
    assert values["blocker.explanation"] == "Authored workstream status is active."


@pytest.mark.parametrize("source_state", ["ready", "proposed"])
def test_known_nonblocking_agent_states_are_explicit(source_state: str):
    snapshot = _snapshot()
    snapshot["work"][0]["agent_os"]["state"] = source_state
    snapshot["work"][0]["agent_os"]["status"] = source_state
    port = _port(snapshot)
    ref = responsibility_ref_for("WS:ALPHA")

    listed = asyncio.run(port.list_responsibilities())
    list_values = {fact.predicate: fact.value for fact in listed.facts}
    assert list_values["responsibility.state"] == "WAITING"

    blocker = asyncio.run(port.explain_blocker(ref))
    blocker_values = {fact.predicate: fact.value for fact in blocker.facts}
    assert blocker_values["blocker.present"] is False
    assert blocker_values["blocker.kind"] == "NONE"


def test_runtime_job_without_status_never_becomes_idle():
    snapshot = _snapshot()
    snapshot["work"][0]["executive"]["jobs"][0]["status"] = None
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).get_current_runtime(ref))
    values = {fact.predicate: fact.value for fact in result.facts}

    assert result.state == "UNKNOWN"
    assert "RUNTIME_UNKNOWN" in result.reason_codes
    assert values == {}


@pytest.mark.parametrize("joined_by", [None, "title_match"])
def test_runtime_job_requires_exact_control_room_join_provenance(
    joined_by: str | None,
):
    snapshot = _snapshot()
    snapshot["work"][0]["executive"]["joined_by"] = joined_by
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            "get_current_runtime",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        )
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "AMBIGUOUS_JOIN" in result["data"]["reason_codes"]
    assert "RUNTIME_UNKNOWN" in result["data"]["reason_codes"]


@pytest.mark.parametrize("missing_field", ["job_id", "binding_id"])
def test_missing_runtime_or_surface_row_identity_never_mints_a_receipt(
    missing_field: str,
):
    snapshot = _snapshot()
    ref = responsibility_ref_for("WS:ALPHA")
    if missing_field == "job_id":
        snapshot["work"][0]["executive"]["jobs"][0]["job_id"] = None
        tool_name = "get_current_runtime"
        expected_reason = "RUNTIME_UNKNOWN"
    else:
        snapshot["work"][0]["bindings"][0]["binding_id"] = None
        tool_name = "resolve_surface"
        expected_reason = "SURFACE_UNKNOWN"

    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            tool_name,
            {"responsibility_ref": ref},
        )
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert expected_reason in result["data"]["reason_codes"]


def test_missing_agent_observation_time_never_falls_back_to_fresh():
    snapshot = _snapshot()
    snapshot["sources"]["agent_os_state_generated_at"] = None
    result = asyncio.run(_port(snapshot).list_responsibilities())

    assert result.state == "DEGRADED"
    assert "STALE_SOURCE" in result.reason_codes
    assert {fact.freshness for fact in result.facts} == {"UNKNOWN"}
    assert {fact.sources[0].observed_at for fact in result.facts} == {None}


def test_malformed_work_row_degrades_the_valid_remainder():
    snapshot = _snapshot()
    snapshot["work"].append("malformed-row")
    result = asyncio.run(_port(snapshot).list_responsibilities())

    assert result.state == "DEGRADED"
    assert "STEWARD_DEGRADED" in result.reason_codes
    assert {fact.subject_ref for fact in result.facts} == {
        responsibility_ref_for("WS:ALPHA")
    }


def test_unrepresentable_runtime_and_surface_ages_are_omitted_not_clamped():
    snapshot = _snapshot(generated_at="2024-01-01T00:00:00Z")
    snapshot["work"][0]["bindings"][0]["observed_at"] = "2024-01-01T00:00:00Z"
    snapshot["work"][0]["bindings"][0]["last_verified_at"] = "2024-01-01T00:00:00Z"
    port = _port(snapshot)
    ref = responsibility_ref_for("WS:ALPHA")

    runtime = asyncio.run(port.get_current_runtime(ref))
    runtime_values = {fact.predicate: fact.value for fact in runtime.facts}
    assert "runtime.age_seconds" not in runtime_values
    assert "STALE_SOURCE" in runtime.reason_codes

    surface = asyncio.run(port.resolve_surface(ref))
    surface_values = {fact.predicate: fact.value for fact in surface.facts}
    assert "surface.observation_age_seconds" not in surface_values
    assert "STALE_SOURCE" in surface.reason_codes


@pytest.mark.parametrize(
    "malformed_source",
    [
        "attention_ids",
        "attention_rows",
        "runtime_jobs",
        "surface_bindings",
        "surface_conflicts",
        "blocker_dependencies",
        "blocker_disagreements",
    ],
)
def test_malformed_nested_candidates_never_create_a_unique_winner(
    malformed_source: str,
):
    snapshot = _snapshot()
    ref = responsibility_ref_for("WS:ALPHA")
    if malformed_source == "attention_ids":
        snapshot["work"][0]["attention_ids"].append(7)
        tool_name, arguments = "get_attention", {}
    elif malformed_source == "attention_rows":
        snapshot["attention"]["ceo"].append("malformed-row")
        tool_name, arguments = "get_attention", {}
    elif malformed_source == "runtime_jobs":
        snapshot["work"][0]["executive"]["jobs"].append("malformed-row")
        tool_name = "get_current_runtime"
        arguments = {"responsibility_ref": ref}
    elif malformed_source == "surface_bindings":
        snapshot["work"][0]["bindings"].append("malformed-row")
        tool_name = "resolve_surface"
        arguments = {"responsibility_ref": ref}
    elif malformed_source == "surface_conflicts":
        snapshot["binding_conflicts"].append("malformed-row")
        tool_name = "resolve_surface"
        arguments = {"responsibility_ref": ref}
    elif malformed_source == "blocker_dependencies":
        snapshot["work"][0]["agent_os"]["unmet_dependencies"] = "malformed"
        tool_name = "explain_blocker"
        arguments = {"responsibility_ref": ref}
    else:
        snapshot["work"][0]["disagreements"] = "malformed"
        tool_name = "explain_blocker"
        arguments = {"responsibility_ref": ref}

    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(tool_name, arguments)
    )

    assert result["ok"] is True
    assert result["data"]["state"] in {"UNKNOWN", "DEGRADED"}
    assert "STEWARD_DEGRADED" in result["data"]["reason_codes"]
    facts = [
        fact
        for subject in result["data"]["subjects"]
        for fact in subject["facts"]
    ]
    if tool_name == "explain_blocker":
        assert {fact["predicate"] for fact in facts} <= {"blocker.explanation"}
    else:
        assert facts == []


@pytest.mark.parametrize(
    "conflict",
    [
        {},
        {"work_ref": "WS:ALPHA", "role": "ceo", "binding_ids": []},
        {
            "work_ref": "WS:ALPHA",
            "role": "ceo",
            "binding_ids": [7],
        },
    ],
)
def test_malformed_binding_conflict_mapping_never_allows_surface_facts(
    conflict: dict,
):
    snapshot = _snapshot()
    snapshot["binding_conflicts"] = [conflict]
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            "resolve_surface",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        )
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "STEWARD_DEGRADED" in result["data"]["reason_codes"]
    assert "SURFACE_UNKNOWN" in result["data"]["reason_codes"]


def test_cross_work_binding_id_conflict_never_allows_surface_facts():
    snapshot = _snapshot()
    snapshot["binding_conflicts"] = [
        {
            "work_ref": "WS:BETA",
            "role": "ceo",
            "binding_ids": ["11111111-1111-4111-8111-111111111111"],
        }
    ]
    result = asyncio.run(
        SecretaryGroundingGateway(_port(snapshot)).call(
            "resolve_surface",
            {"responsibility_ref": responsibility_ref_for("WS:ALPHA")},
        )
    )

    assert result["ok"] is True
    assert result["data"]["state"] == "UNKNOWN"
    assert result["data"]["subjects"] == []
    assert "AMBIGUOUS_JOIN" in result["data"]["reason_codes"]
    assert "SURFACE_UNKNOWN" in result["data"]["reason_codes"]


def test_malformed_global_degraded_container_cannot_report_facts_state():
    snapshot = _snapshot()
    snapshot["degraded"] = "malformed"

    result = asyncio.run(_port(snapshot).list_responsibilities())

    assert result.state == "DEGRADED"
    assert "STEWARD_DEGRADED" in result.reason_codes


def test_list_is_bounded_and_reports_degradation():
    snapshot = _snapshot()
    base = snapshot["work"][0]
    snapshot["work"] = []
    for index in range(80):
        row = json.loads(json.dumps(base))
        row["work_ref"] = f"WS:ITEM-{index:02d}"
        row["attention_ids"] = []
        snapshot["work"].append(row)
    result = asyncio.run(_port(snapshot).list_responsibilities())
    assert len(result.facts) == 64
    assert len({fact.subject_ref for fact in result.facts}) == 16
    by_subject: dict[str, set[str]] = {}
    for fact in result.facts:
        by_subject.setdefault(fact.subject_ref, set()).add(fact.predicate)
    assert all(
        predicates == set(TOOL_REQUIRED_PREDICATES["list_responsibilities"])
        for predicates in by_subject.values()
    )
    assert result.state == "DEGRADED"
    assert "STEWARD_DEGRADED" in result.reason_codes


def test_multiple_current_jobs_are_ambiguous_even_when_status_matches():
    snapshot = _snapshot()
    snapshot["work"][0]["executive"]["jobs"].append(
        {"job_id": "JOB-RAW-002", "status": "queued", "workstream": "WS:ALPHA"}
    )
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).get_current_runtime(ref))
    values = {fact.predicate: fact.value for fact in result.facts}
    assert values == {}
    assert result.state == "UNKNOWN"
    assert "AMBIGUOUS_JOIN" in result.reason_codes


def test_runtime_age_is_attributed_to_the_controlling_executive_observation():
    snapshot = _snapshot(generated_at="2026-09-01T12:00:00Z")
    snapshot["work"][0]["bindings"][0]["last_verified_at"] = "2026-09-01T12:04:30Z"
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).get_current_runtime(ref))
    age_fact = next(
        fact for fact in result.facts if fact.predicate == "runtime.age_seconds"
    )
    assert age_fact.value == 300
    assert len(age_fact.sources) == 1
    assert age_fact.sources[0].owner == "executive_os"
    assert age_fact.sources[0].observed_at == "2026-09-01T12:00:00Z"


def test_unrelated_global_degradation_does_not_fabricate_a_blocker():
    snapshot = _snapshot()
    snapshot["degraded"] = ["active_builds: unavailable"]
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).explain_blocker(ref))
    values = {fact.predicate: fact.value for fact in result.facts}
    assert values == {
        "blocker.present": False,
        "blocker.kind": "NONE",
        "blocker.explanation": "Authored workstream status is active.",
    }
    assert result.state == "DEGRADED"
    assert "STEWARD_DEGRADED" in result.reason_codes


def test_attention_and_active_work_are_selected_before_completed_work():
    snapshot = _snapshot()
    base = snapshot["work"][0]
    snapshot["work"] = []
    for index in range(80):
        row = json.loads(json.dumps(base))
        row["work_ref"] = f"WS:DONE-{index:02d}"
        row["agent_os"]["state"] = "done"
        row["agent_os"]["status"] = "done"
        row["attention_ids"] = []
        snapshot["work"].append(row)
    active = json.loads(json.dumps(base))
    active["work_ref"] = "WS:URGENT"
    snapshot["work"].append(active)
    result = asyncio.run(_port(snapshot).list_responsibilities())
    refs = {fact.subject_ref for fact in result.facts}
    assert responsibility_ref_for("WS:URGENT") in refs
    assert len(result.facts) == 64
    assert len(refs) == 16
    assert "STEWARD_DEGRADED" in result.reason_codes


def _tool_cases() -> list[tuple[str, dict[str, str]]]:
    ref = responsibility_ref_for("WS:ALPHA")
    return [
        ("list_responsibilities", {}),
        ("get_responsibility", {"responsibility_ref": ref}),
        ("get_attention", {}),
        ("get_current_runtime", {"responsibility_ref": ref}),
        ("explain_blocker", {"responsibility_ref": ref}),
        ("resolve_surface", {"responsibility_ref": ref}),
    ]


@pytest.mark.parametrize(("tool_name", "arguments"), _tool_cases())
def test_real_control_room_port_crosses_protected_gateway_for_each_nonempty_tool(
    tool_name: str,
    arguments: dict[str, str],
):
    calls: list[int] = []
    result = asyncio.run(
        SecretaryGroundingGateway(_port(_snapshot(), calls)).call(
            tool_name,
            arguments,
        )
    )

    assert calls == [1]
    assert set(result) == {
        "schema",
        "tool",
        "ok",
        "server_version",
        "data",
        "error",
    }
    assert result["schema"] == "mastermind.secretary_grounding_mcp_result.v2"
    assert result["server_version"] == "2.0.0"
    assert result["tool"] == tool_name
    assert result["ok"] is True
    assert result["error"] is None
    assert isinstance(result["data"], dict)
    assert set(result["data"]) == {"state", "subjects", "reason_codes"}
    assert len(result["data"]["subjects"]) == 1
    subject = result["data"]["subjects"][0]
    assert subject["subject_ref"] == responsibility_ref_for("WS:ALPHA")
    assert subject["facts"]
    for fact in subject["facts"]:
        assert set(fact) == {"predicate", "value", "freshness", "sources"}
        assert fact["sources"]
        assert all(
            set(source) == {"owner", "source_ref", "observed_at"}
            for source in fact["sources"]
        )

    wire = json.dumps(result, sort_keys=True)
    for raw in (
        "JOB-RAW-001",
        "ATTENTION-RAW-001",
        "11111111-1111-4111-8111-111111111111",
        "SEAT-RAW-001",
    ):
        assert raw not in wire
