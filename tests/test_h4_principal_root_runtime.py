from __future__ import annotations

import dataclasses
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import ceo_intent, ceo_request
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
    orchestration_digest,
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


def host_binding() -> dict[str, object]:
    return {
        "eligible_quota_classes": ["codex-h4-work"],
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "base_sha": "a" * 40,
        "routing_policy_version": "h4-routing-v1",
        "execution_profile_id": "sealed.worker.write.no-extensions.v1",
        "execution_profile_digest": "3" * 64,
        "capability_policy_version": "h4-capability-v1",
        "capability_policy_digest": "4" * 64,
        "operator_eligible_quota_classes": ["codex-h4-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-5.6-sol",
        "operator_effort": "xhigh",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "h4-routing-v1",
        "operator_execution_profile_id": "operator.appserver.readonly.docs-mcp.native-helper.v1",
        "operator_execution_profile_digest": "5" * 64,
        "operator_capability_policy_version": "h4-capability-v1",
        "operator_capability_policy_digest": "4" * 64,
        "operator_harness_binary_digest": "6" * 64,
        "operator_harness_version": "h4-harness-v1",
        "operator_harness_armed": True,
        "host_execution_binding_version": "mastermind.host_execution_binding/v3",
        "work_placement_union": [
            {
                "provider_realm": "codex",
                "quota_class": "codex-h4-work",
            },
            {
                "provider_realm": "claude-compatible-subscription",
                "quota_class": "claude-h4-evidence",
            },
        ],
    }


def dialogue_source() -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": WORK_REF,
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "7" * 40,
            "path": "docs/commissions/claude-capability-hardening-h4.md",
            "content_sha256": "8" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }


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


def test_host_bound_principal_root_persists_trusted_workspace_binding_and_dialogue(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    source = bundle()
    workspace_root = tmp_path / "workspaces"
    binding = host_binding()
    dialogue = dialogue_source()

    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
        workspace_root=workspace_root,
        execution_binding=binding,
        dialogue_source=dialogue,
        require_dialogue_source=True,
    )

    assert root.branch == ceo_request.derive_branch(source["intent_id"])
    assert root.worktree == ceo_request.derive_worktree(
        str(workspace_root),
        source["intent_id"],
    )
    assert root.constraints["base_sha"] == "a" * 40
    assert root.constraints["provider"] == "codex"
    assert root.constraints["operator_harness_armed"] is True
    assert root.constraints["work_placement_union"] == [
        {"provider_realm": "claude-compatible-subscription", "quota_class": "claude-h4-evidence"},
        {"provider_realm": "codex", "quota_class": "codex-h4-work"},
    ]

    event = runtime.events.get_event_by_command_id(
        ceo_intent.command_id_for(source["intent_id"])
    )
    assert event is not None
    assert event.payload["provenance"]["dialogue_source"] == dialogue
    assert len(event.payload["provenance"]["dialogue_source_digest"]) == 64

    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "PLANNER_CREATED"
    planner = runtime.jobs.get_job(outcome.selected_job_id)
    assert planner is not None
    assert planner.worktree == root.worktree
    assert planner.branch == root.branch
    assert planner.constraints["provider"] == binding["operator_provider"]
    assert planner.constraints["model"] == binding["operator_model"]
    assert (
        planner.constraints["execution_profile_id"]
        == binding["operator_execution_profile_id"]
    )

    fabric = read_fabric_view_v2_from_runtime(
        runtime,
        root.job_id,
        armed={},
        runtime_identity={"db_present": True},
    )
    assert fabric["root"]["job_id"] == root.job_id
    assert [row["job_id"] for row in fabric["children"]] == [planner.job_id]
    assert fabric["unjoined_job_count"] == 0
    assert fabric["runtime"]["acquisition"]["provenance"]["state"] == "COMPLETE"


@pytest.mark.parametrize(
    "fault",
    ["workspace", "relative_workspace", "binding", "dialogue", "base"],
)
def test_host_bound_principal_root_refuses_partial_or_drifted_host_inputs(tmp_path, fault):
    runtime = Runtime.at(tmp_path / "runtime")
    source = bundle()
    workspace_root = tmp_path / "workspaces"
    binding = host_binding()
    dialogue = dialogue_source()
    kwargs = {
        "workspace_root": workspace_root,
        "execution_binding": binding,
        "dialogue_source": dialogue,
        "require_dialogue_source": True,
    }
    if fault == "workspace":
        kwargs["workspace_root"] = None
    elif fault == "relative_workspace":
        kwargs["workspace_root"] = Path("relative-workspaces")
    elif fault == "binding":
        kwargs["execution_binding"] = None
    elif fault == "dialogue":
        kwargs["dialogue_source"] = None
    else:
        changed = dict(binding)
        changed["base_sha"] = "f" * 40
        kwargs["execution_binding"] = changed

    with pytest.raises(StateConflict):
        runtime.jobs.create_principal_orchestration_root(
            source,
            principal_admission_guard=lambda _value: None,
            **kwargs,
        )
    assert runtime.jobs.list_jobs() == []


def test_host_binding_cannot_change_principal_operation_identity(tmp_path):
    source = bundle()
    first = Runtime.at(tmp_path / "first").jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
        workspace_root=tmp_path / "workspaces-a",
        execution_binding=host_binding(),
        dialogue_source=dialogue_source(),
        require_dialogue_source=True,
    )
    changed = host_binding()
    changed["provider"] = "other-provider"
    changed["work_placement_union"] = [
        {"provider_realm": "other-provider", "quota_class": "codex-h4-work"}
    ]
    second = Runtime.at(tmp_path / "second").jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
        workspace_root=tmp_path / "workspaces-b",
        execution_binding=changed,
        dialogue_source=dialogue_source(),
        require_dialogue_source=True,
    )

    assert first.orchestration_provenance["source_id"] == second.orchestration_provenance["source_id"]
    assert first.orchestration_provenance["source_digest"] == second.orchestration_provenance["source_digest"]
    first_event = Runtime.at(tmp_path / "first").events.get_event_by_command_id(
        ceo_intent.command_id_for(source["intent_id"])
    )
    second_event = Runtime.at(tmp_path / "second").events.get_event_by_command_id(
        ceo_intent.command_id_for(source["intent_id"])
    )
    assert first_event is not None and second_event is not None
    assert first_event.command_id == second_event.command_id


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


def test_principal_root_two_lane_reviewed_cycle_reaches_canonical_completion(tmp_path):
    from tests import test_executive_os_phase1fc as phase

    runtime = Runtime.at(tmp_path)
    phase._register(runtime, "worker-a")
    phase._register(runtime, "worker-b")
    source = bundle(
        operation_key="h4-two-lane-cycle",
        objective="Coordinate two path-disjoint governed read outcomes.",
    )
    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )
    dispatches = []

    def accepted_dispatch(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        if job.orchestration_role in {"plan", "aggregation"}:
            worker = "worker-a"
        elif job.orchestration_role == "review":
            worker = "worker-b"
        elif job.plan_step_id == "step-primary":
            worker = "worker-a"
        else:
            worker = "worker-b"
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker,
        )
        assert outcome is not None
        dispatches.append(outcome)
        return outcome

    cycle = CooCycle(runtime, dispatcher=accepted_dispatch)
    assert cycle.run_once(root.job_id).action == "PLANNER_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    planner = dispatches[-1]

    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-primary",
                "objective": "Produce the primary bounded read outcome.",
                "business_impact": "routine",
                "review_required": True,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            },
            {
                "ordinal": 1,
                "step_id": "step-evidence",
                "objective": "Produce a path-disjoint evidence-only outcome.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            },
        ],
    }
    phase._complete_ohf_role(runtime, planner, plan_body, identity_seed=9101)

    admitted = cycle.run_once(root.job_id)
    assert admitted.action == "PLAN_ADMITTED"
    work_ids = list(admitted.receipt["work_job_ids"])
    assert len(work_ids) == 2
    work_by_step = {}
    for work_id in work_ids:
        job = runtime.jobs.get_job(work_id)
        assert job is not None
        worker = "worker-a" if job.plan_step_id == "step-primary" else "worker-b"
        outcome = runtime.attempts.dispatch_cycle_job(
            work_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{work_id}:attempt:1",
            worker_id=worker,
        )
        assert outcome is not None
        work_by_step[str(job.plan_step_id)] = outcome
    assert {item.attempt.worker_id for item in work_by_step.values()} == {
        "worker-a",
        "worker-b",
    }

    plan_digest = phase.result_digest(plan_body)
    seals = {}
    for step_id, work in work_by_step.items():
        body = {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": planner.attempt.attempt_id,
            "plan_digest": plan_digest,
            "plan_step_id": step_id,
            "repair_round": 0,
            "artifacts": [],
            "evidence_digests": [],
        }
        seals[step_id] = phase._complete_ohf_role(
            runtime,
            work,
            body,
            identity_seed=9102 if step_id == "step-primary" else 9103,
        )[0]

    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    primary = work_by_step["step-primary"]
    review_body = phase._review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=primary.attempt.job_id,
        target_attempt_id=primary.attempt.attempt_id,
        target_result_digest=seals["step-primary"]["role_result_digest"],
        repair_round=0,
        verdict="approve",
        plan_step_id="step-primary",
    )
    phase._complete_ohf_role(runtime, review, review_body, identity_seed=9104)
    assert review.attempt.worker_id != primary.attempt.worker_id

    handoff_outcome = cycle.run_once(root.job_id)
    assert handoff_outcome.action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert len(handoff["revisions"]) == 2
    by_step = {item["plan_step_id"]: item for item in handoff["revisions"]}
    assert by_step["step-primary"]["qualifying_review_result_digest"] is not None
    assert by_step["step-evidence"]["qualifying_review_result_digest"] is None

    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation = dispatches[-1]
    aggregation_body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        "handoff_digest": handoff["handoff_digest"],
        "policy_sha": handoff["policy_sha"],
        "plan_attempt_id": handoff["plan_attempt_id"],
        "plan_digest": handoff["plan_digest"],
        "revisions": [
            {
                key: item[key]
                for key in (
                    "ordinal",
                    "plan_step_id",
                    "current_job_id",
                    "current_attempt_id",
                    "current_result_digest",
                    "repair_round",
                    "review_required",
                    "qualifying_review_job_id",
                    "qualifying_review_attempt_id",
                    "qualifying_review_result_digest",
                )
            }
            for item in handoff["revisions"]
        ],
        "aggregate_summary": "Two path-disjoint principal outcomes are accepted.",
        "evidence_digests": [],
    }
    phase._complete_ohf_role(runtime, aggregation, aggregation_body, identity_seed=9105)

    completed = runtime.jobs.get_job(root.job_id)
    assert completed is not None
    assert completed.status.value == "COMPLETED"
    assert cycle.run_once(root.job_id).action == "NO_ACTION"

    fabric = read_fabric_view_v2_from_runtime(
        runtime,
        root.job_id,
        armed={},
        runtime_identity={"db_present": True},
    )
    assert fabric["unjoined_job_count"] == 0, fabric
    assert fabric["root"] is not None, fabric["degraded"]
    assert fabric["root"]["status"] == "COMPLETED"

    from control_plane.coo_principal_orchestration_status import (
        resolve_principal_orchestration,
    )

    reconciled = resolve_principal_orchestration(
        runtime,
        request_ref=source["request_ref"],
        work_ref=WORK_REF,
    )
    assert reconciled["job_id"] == root.job_id
    assert reconciled["job_status"] == "COMPLETED"


def _fabric_child(
    *,
    role: str,
    job_id: str,
    root_id: str,
    source_id: str,
    source_digest: str,
    plan_step_id: str,
    reviews_job_id: str | None = None,
    supersedes_job_id: str | None = None,
    repair_round: int = 0,
):
    provenance = {
        "schema_version": "mastermind.executive_orchestration_provenance/v1",
        "creator": "coo_cycle",
        "source_id": source_id,
        "source_digest": source_digest,
        "command_id": f"coo-cycle:{root_id}:fixture:{job_id}",
        "job_id": job_id,
        "parent_job_id": root_id,
        "root_job_id": root_id,
        "role": role,
    }
    return SimpleNamespace(
        job_id=job_id,
        parent_job_id=root_id,
        root_job_id=root_id,
        depth=1,
        orchestration_role=role,
        orchestration_provenance=provenance,
        orchestration_provenance_digest=orchestration_digest(provenance),
        plan_attempt_id="ATT-001",
        plan_digest="a" * 64,
        plan_step_id=plan_step_id,
        repair_round=repair_round,
        supersedes_job_id=supersedes_job_id,
        reviews_job_id=reviews_job_id,
    )


def test_fabric_work_join_refuses_foreign_plan_source_digest():
    from control_plane import fabric_job_view as fabric

    root = SimpleNamespace(job_id="JOB-001", orchestration_provenance_digest="b" * 64)
    valid = _fabric_child(
        role="work",
        job_id="JOB-002",
        root_id=root.job_id,
        source_id=root.job_id,
        source_digest="a" * 64,
        plan_step_id="step-a",
    )
    joined, warning = fabric._bounded_cycle_child(
        valid,
        root=root,
        root_validated=True,
        jobs_by_id={root.job_id: root, valid.job_id: valid},
    )
    assert joined is valid and warning is None

    hostile_cycle = dict(valid.orchestration_provenance)
    hostile_cycle["source_digest"] = "f" * 64
    hostile = SimpleNamespace(
        **{
            **valid.__dict__,
            "orchestration_provenance": hostile_cycle,
            "orchestration_provenance_digest": orchestration_digest(hostile_cycle),
        }
    )
    joined, warning = fabric._bounded_cycle_child(
        hostile,
        root=root,
        root_validated=True,
        jobs_by_id={root.job_id: root, hostile.job_id: hostile},
    )
    assert joined is None
    assert warning == "durable work provenance source invalid"


def test_fabric_review_join_requires_exact_reviewed_target():
    from control_plane import fabric_job_view as fabric

    root = SimpleNamespace(job_id="JOB-001", orchestration_provenance_digest="b" * 64)
    work = _fabric_child(
        role="work",
        job_id="JOB-002",
        root_id=root.job_id,
        source_id=root.job_id,
        source_digest="a" * 64,
        plan_step_id="step-a",
    )
    review = _fabric_child(
        role="review",
        job_id="JOB-003",
        root_id=root.job_id,
        source_id=work.job_id,
        source_digest="c" * 64,
        plan_step_id="step-a",
        reviews_job_id=work.job_id,
    )
    jobs = {root.job_id: root, work.job_id: work, review.job_id: review}
    joined, warning = fabric._bounded_cycle_child(
        review,
        root=root,
        root_validated=True,
        jobs_by_id=jobs,
    )
    assert joined is review and warning is None

    wrong = SimpleNamespace(**{**review.__dict__, "reviews_job_id": "JOB-999"})
    joined, warning = fabric._bounded_cycle_child(
        wrong,
        root=root,
        root_validated=True,
        jobs_by_id={**jobs, wrong.job_id: wrong},
    )
    assert joined is None
    assert warning == "durable review provenance source invalid"


def test_fabric_repair_join_requires_rejecting_review_of_superseded_revision():
    from control_plane import fabric_job_view as fabric

    root = SimpleNamespace(job_id="JOB-001", orchestration_provenance_digest="b" * 64)
    work = _fabric_child(
        role="work",
        job_id="JOB-002",
        root_id=root.job_id,
        source_id=root.job_id,
        source_digest="a" * 64,
        plan_step_id="step-a",
    )
    review = _fabric_child(
        role="review",
        job_id="JOB-003",
        root_id=root.job_id,
        source_id=work.job_id,
        source_digest="c" * 64,
        plan_step_id="step-a",
        reviews_job_id=work.job_id,
    )
    repair = _fabric_child(
        role="repair",
        job_id="JOB-004",
        root_id=root.job_id,
        source_id=review.job_id,
        source_digest="d" * 64,
        plan_step_id="step-a",
        supersedes_job_id=work.job_id,
        repair_round=1,
    )
    jobs = {
        root.job_id: root,
        work.job_id: work,
        review.job_id: review,
        repair.job_id: repair,
    }
    joined, warning = fabric._bounded_cycle_child(
        repair,
        root=root,
        root_validated=True,
        jobs_by_id=jobs,
    )
    assert joined is repair and warning is None

    unrelated_review = SimpleNamespace(**{**review.__dict__, "reviews_job_id": "JOB-999"})
    broken_jobs = {**jobs, review.job_id: unrelated_review}
    joined, warning = fabric._bounded_cycle_child(
        repair,
        root=root,
        root_validated=True,
        jobs_by_id=broken_jobs,
    )
    assert joined is None
    assert warning == "durable repair provenance source invalid"


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
