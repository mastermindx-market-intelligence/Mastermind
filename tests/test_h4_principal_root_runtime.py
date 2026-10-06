from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane import ceo_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.coo_principal_envelope import (
    PrincipalAdmissionContext,
    derive_principal_orchestration_envelope,
    principal_orchestration_bundle_digest,
)
from control_plane.fabric_job_view import read_fabric_view_v2_from_runtime
from control_plane.executive_runtime import (
    PRINCIPAL_ORCHESTRATION_ROOT_CREATOR,
    Runtime,
    StateConflict,
    _ceo_intent_root_provenance,
)


ROOT = Path(__file__).resolve().parents[1]
WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"


def bundle(**request_changes):
    request = {
        "operation_key": "claude-governed-orchestration",
        "objective": "Coordinate one governed Executive orchestration episode.",
        "department": "executive-infrastructure",
        "priority": 7,
        "workstream": WORK_REF,
        "business_impact": "routine",
    }
    request.update(request_changes)
    return derive_principal_orchestration_envelope(
        request,
        context=PrincipalAdmissionContext(
            work_ref=WORK_REF,
            principal_binding_digest="1" * 64,
            mission_authority_ref="authority:coo-principal-v2",
            authority_generation_digest="2" * 64,
        ),
        grounding={
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
    )


def test_guarded_principal_bundle_creates_one_read_only_v1_root_and_planner(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    seen = []

    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda value: seen.append(value),
    )

    assert seen == [source]
    assert root.orchestration_role == "aggregation"
    assert root.parent_job_id is None
    assert root.root_job_id == root.job_id
    assert root.owner_seat == "coo"
    assert root.escalation_target == "coo"
    assert root.requested_authorities == ["READ"]
    assert root.allowed_write_paths == []
    assert root.validation_commands == []
    assert root.branch is None
    assert root.worktree is None
    assert root.constraints == {"eligible_quota_classes": ["default"]}
    assert "provider" not in root.constraints
    assert "model" not in root.constraints
    assert "host" not in root.constraints
    assert root.attempt_limit == CooCyclePolicy.load().max_attempts_per_orchestration_job
    assert root.business_impact == "routine"
    assert root.orchestration_provenance["creator"] == PRINCIPAL_ORCHESTRATION_ROOT_CREATOR
    assert root.orchestration_provenance["source_id"] == source["intent_id"]
    assert root.orchestration_provenance["source_digest"] == (
        principal_orchestration_bundle_digest(source)
    )
    assert _ceo_intent_root_provenance(root.orchestration_provenance) is False

    created = [
        event
        for event in runtime.events.list_events(job_id=root.job_id)
        if event.event_type == "JOB_CREATED"
    ]
    assert len(created) == 1
    assert created[0].command_id == ceo_intent.command_id_for(source["intent_id"])
    provenance = created[0].payload["provenance"]
    assert provenance["request_ref"] == source["request_ref"]
    assert provenance["action_kind"] == "governed_orchestration"
    assert provenance["bundle_digest"] == principal_orchestration_bundle_digest(source)
    assert provenance["authority_generation_digest"] == "2" * 64

    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    assert planner.parent_job_id == root.job_id
    assert planner.root_job_id == root.job_id
    assert planner.orchestration_role == "plan"
    assert planner.orchestration_provenance["creator"] == "coo_cycle"


def test_principal_root_is_accepted_by_existing_coo_cycle(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )

    outcome = CooCycle(runtime).run_once(root.job_id)

    assert outcome.action == "PLANNER_CREATED"
    assert outcome.selected_job_id is not None
    planner = runtime.jobs.get_job(outcome.selected_job_id)
    assert planner is not None
    assert planner.parent_job_id == root.job_id
    assert planner.root_job_id == root.job_id
    assert planner.orchestration_role == "plan"


def test_principal_root_and_planner_join_existing_fabric_view(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "PLANNER_CREATED"

    document = read_fabric_view_v2_from_runtime(
        runtime,
        root.job_id,
        armed={},
        runtime_identity={"db_present": True},
    )

    assert document["root"]["job_id"] == root.job_id
    assert document["root"]["orchestration_role"] == "aggregation"
    assert [row["job_id"] for row in document["children"]] == [outcome.selected_job_id]
    assert document["unjoined_job_count"] == 0
    assert document["runtime"]["acquisition"]["provenance"]["state"] == "COMPLETE"


def test_same_principal_operation_refuses_second_root_and_requires_reconciliation(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )
    calls = []

    with pytest.raises(StateConflict, match="already has durable state"):
        runtime.jobs.create_principal_orchestration_root(
            source,
            principal_admission_guard=lambda value: calls.append(value),
        )

    assert calls == []
    roots = [
        job
        for job in runtime.jobs.list_jobs()
        if job.orchestration_role == "aggregation"
    ]
    assert len(roots) == 1


def test_cross_kind_same_logical_operation_cannot_create_a_second_root(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    command_id = ceo_intent.command_id_for(source["intent_id"])
    bounded = runtime.jobs.create_job(
        "Existing bounded COO operation.",
        command_id=command_id,
        requested_authorities=["READ"],
        attempt_limit=1,
    )
    calls = []

    with pytest.raises(StateConflict, match="already has durable state"):
        runtime.jobs.create_principal_orchestration_root(
            source,
            principal_admission_guard=lambda value: calls.append(value),
        )

    assert calls == []
    assert runtime.jobs.list_jobs() == [bounded]


@pytest.mark.parametrize("fault", ["bundle", "guard", "missing_guard"])
def test_invalid_or_unadmitted_principal_root_has_zero_runtime_effect(tmp_path, fault):
    runtime = Runtime.at(tmp_path)
    source = bundle()

    if fault == "bundle":
        changed = dict(source)
        changed["envelope"] = dict(changed["envelope"])
        changed["envelope"]["authority_generation_digest"] = "f" * 64
        guard = lambda _value: None
        with pytest.raises(StateConflict, match="bundle is invalid"):
            runtime.jobs.create_principal_orchestration_root(
                changed,
                principal_admission_guard=guard,
            )
    elif fault == "guard":
        def refused(_value):
            raise ValueError("current mission moved")
        with pytest.raises(StateConflict, match="admission is not current"):
            runtime.jobs.create_principal_orchestration_root(
                source,
                principal_admission_guard=refused,
            )
    else:
        with pytest.raises(StateConflict, match="current admission guard"):
            runtime.jobs.create_principal_orchestration_root(
                source,
                principal_admission_guard=None,  # type: ignore[arg-type]
            )

    assert runtime.jobs.list_jobs() == []
    assert runtime.events.list_events() == []


def test_semantic_change_same_operation_is_still_one_command_namespace(tmp_path):
    runtime = Runtime.at(tmp_path)
    first = bundle()
    changed = bundle(
        objective="Changed orchestration semantics under the same operation.",
        business_impact="material",
    )
    assert first["request_ref"] == changed["request_ref"]
    assert first["intent_id"] == changed["intent_id"]
    assert first["request_fingerprint"] != changed["request_fingerprint"]

    runtime.jobs.create_principal_orchestration_root(
        first,
        principal_admission_guard=lambda _value: None,
    )
    with pytest.raises(StateConflict, match="already has durable state"):
        runtime.jobs.create_principal_orchestration_root(
            changed,
            principal_admission_guard=lambda _value: None,
        )
    assert len(runtime.jobs.list_jobs()) == 1


def test_principal_root_constructor_has_no_production_caller_yet():
    needle = ".create_principal_orchestration_root("
    offenders = []
    for base in (ROOT / "control_plane", ROOT / "integrations", ROOT / "ops"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".mjs", ".js", ".ts"}:
                continue
            if path == ROOT / "control_plane" / "executive_runtime.py":
                continue
            if needle in path.read_text(encoding="utf-8", errors="strict"):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
