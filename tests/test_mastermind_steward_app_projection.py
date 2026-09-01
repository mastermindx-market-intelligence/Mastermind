from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

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
                }
            ],
            "coo": [],
        },
        "work": [
            {
                "work_ref": "WS:ALPHA",
                "agent_os": {
                    "title": "Alpha program",
                    "status": "in_progress",
                    "state": "in_progress",
                    "reason_code": "workstream_active",
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
                        "binding_id": "BINDING-RAW-001",
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


def test_public_responsibility_ref_is_stable_and_opaque():
    first = responsibility_ref_for("WS:ALPHA")
    second = responsibility_ref_for("WS:ALPHA")
    assert first == second
    assert first.startswith("responsibility:")
    assert "ALPHA" not in first
    assert len(first) == len("responsibility:") + 64


def test_list_responsibilities_projects_closed_facts_and_calls_source_once():
    calls: list[int] = []
    result = asyncio.run(_port(_snapshot(), calls).list_responsibilities())
    assert len(calls) == 1
    assert result.state == "FACTS"
    assert result.reason_codes == ()
    assert [fact.predicate for fact in result.facts] == [
        "responsibility.state",
    ]
    assert result.facts[0].value == "ACTIVE"
    assert result.facts[0].sources[0].source_ref == "WS:ALPHA"


def test_attention_runtime_blocker_and_surface_projection():
    port = _port(_snapshot())
    ref = responsibility_ref_for("WS:ALPHA")

    attention = asyncio.run(port.get_attention())
    assert attention.state == "FACTS"
    assert attention.facts[0].value == "SOL_REQUIRED"

    runtime = asyncio.run(port.get_current_runtime(ref))
    values = {fact.predicate: fact.value for fact in runtime.facts}
    assert values["runtime.state"] == "IDLE"
    assert values["runtime.continuity"] == "BOUND"
    assert isinstance(values["runtime.age_seconds"], int)

    blocker = asyncio.run(port.explain_blocker(ref))
    values = {fact.predicate: fact.value for fact in blocker.facts}
    assert values == {"blocker.present": False, "blocker.kind": "NONE"}

    surface = asyncio.run(port.resolve_surface(ref))
    values = {fact.predicate: fact.value for fact in surface.facts}
    assert values["surface.health"] == "UNKNOWN"
    assert values["surface.repair_required"] is False


def test_raw_operational_identifiers_never_cross_projection_boundary():
    port = _port(_snapshot())
    ref = responsibility_ref_for("WS:ALPHA")
    results = [
        asyncio.run(port.list_responsibilities()),
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
        "BINDING-RAW-001",
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


def test_duplicate_work_identity_is_refused_not_last_wins():
    snapshot = _snapshot()
    snapshot["work"].append(dict(snapshot["work"][0]))
    with pytest.raises(ProjectionError, match="AMBIGUOUS_JOIN"):
        asyncio.run(_port(snapshot).list_responsibilities())


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
    assert result.state == "DEGRADED"
    assert "STEWARD_DEGRADED" in result.reason_codes


def test_multiple_jobs_with_same_runtime_state_do_not_become_ambiguous():
    snapshot = _snapshot()
    snapshot["work"][0]["executive"]["jobs"].append(
        {"job_id": "JOB-RAW-002", "status": "queued", "workstream": "WS:ALPHA"}
    )
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).get_current_runtime(ref))
    values = {fact.predicate: fact.value for fact in result.facts}
    assert values["runtime.state"] == "IDLE"
    assert "AMBIGUOUS_JOIN" not in result.reason_codes


def test_unrelated_global_degradation_does_not_fabricate_a_blocker():
    snapshot = _snapshot()
    snapshot["degraded"] = ["active_builds: unavailable"]
    ref = responsibility_ref_for("WS:ALPHA")
    result = asyncio.run(_port(snapshot).explain_blocker(ref))
    values = {fact.predicate: fact.value for fact in result.facts}
    assert values == {"blocker.present": False, "blocker.kind": "NONE"}
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
    assert "STEWARD_DEGRADED" in result.reason_codes
