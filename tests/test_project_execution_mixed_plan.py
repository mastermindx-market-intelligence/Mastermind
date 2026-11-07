"""Inert mixed v5 planning on actual Runtime admission, seals and Capacity.

Temporary registered workers and catalogue profiles are test DATA only. No
provider, paid lease, attended source, installed config or process is started.
"""
import json
from types import SimpleNamespace

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.foreground_operation import ForegroundOperationRefusal
from control_plane import executive_runtime as er
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement, placement_member
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_supervisor import ExecutiveSupervisor, _planner_routing_options
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from tests.test_executive_os_phase1fc import _v2_intent, _v3_execution_binding, _complete_ohf_role
from tests.test_executive_coo_hierarchy_cycle import finish_result
from tests.test_fabric_attended_routing import router, member as attended_member
from tests.test_executive_paid_runtime import _capacity_join_wire


@pytest.fixture
def mixed(tmp_path, monkeypatch, router):
    runtime = er.Runtime.at(tmp_path / "runtime")
    workspace = tmp_path / "workspace"; workspace.mkdir()
    native = router.resolve_model_alias("coo.sealed")
    paid = router.resolve_model_alias("glm.paid.sealed-input")
    members = [
        {"provider_realm": native.provider_alias, "quota_class": "native-code"},
        placement_member(router, PaidWorkPlacement(paid.model_alias, "paid-read")),
        attended_member(router),
    ]
    monkeypatch.setattr(ExecutionCapabilityRegistry, "load", classmethod(lambda cls, *args, **kwargs: router.capability_registry))
    identity_keys = ("execution_profile_id", "execution_profile_digest", "capability_policy_version", "capability_policy_digest")
    def identity(alias):
        return {key: getattr(alias, key) for key in identity_keys}
    for worker_id, member, alias in [
        ("native-worker", members[0], native), ("paid-worker", members[1], paid),
        ("attended-worker", members[2], router.model_aliases["minimax.attended"]),
    ]:
        route_key = next((key for key in ("paid_execution_route", "attended_route") if key in member), None)
        metadata = {**identity(alias), "adapter_id": alias.adapter_id, "model_alias": alias.model_alias,
            "routing_policy_version": router.policy_version}
        if route_key:
            metadata[route_key] = member[route_key]
        if route_key == "paid_execution_route":
            metadata["capacity_join"] = _capacity_join_wire("9" * 64)
        caps = ["read", "research", "code", "tests"] if worker_id == "native-worker" else ["read", "research"]
        runtime.workers.register_worker(worker_id, provider=alias.provider_alias,
            account_label=worker_id + "-inert", worker_type=alias.adapter_id, capabilities=caps,
            quota_classes={member["quota_class"]: {"provider": alias.provider_alias, "capabilities": caps,
                "model": alias.model, "effort": alias.effort, "cost_class": "small", "metadata": metadata}})
    binding = {**_v3_execution_binding(), **identity(native), "provider": native.provider_alias,
        "model": native.model, "effort": native.effort, "cost_class": "default",
        "routing_policy_version": router.policy_version, "eligible_quota_classes": ["native-code"],
        "work_placement_union": members}
    # This host fixture explicitly admits the ordinary shared workspace shape.
    # It does not remove readonly/v1 from a live binding or redefine that policy.
    assert er.CHILD_WORKSPACE_POLICY_KEY not in binding
    commands = [["python3", "-m", "pytest", "tests/test_example.py"]]
    intent = _v2_intent(business_impact="routine", execution_contract={
        "requested_authorities": ["READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"],
        "worktree": str(workspace), "allowed_write_paths": ["control_plane/example.py"],
        "validation_commands": commands, "attempt_limit": 2})
    root = runtime.jobs.get_job(submit_intent(runtime, intent, execution_binding=binding,
        workspace_root=tmp_path)["job_id"])
    planner = runtime.jobs.create_cycle_planner(root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="native-worker", quota_class="native-code")
    assert isinstance(dispatch, er.OrchestrationDispatchOutcome)
    return SimpleNamespace(runtime=runtime, root=root, planner=planner, dispatch=dispatch,
        members=members, router=router, commands=commands, tmp_path=tmp_path)


def step(index, member, *, authorities=None, paths=None, validations=None, depends=False, delegation=None):
    return {"ordinal": index, "step_id": f"STEP-{index}", "objective": "Complete the bounded mixed-pool step",
        "business_impact": "routine", "review_required": False,
        "requested_authorities": authorities or ["READ"], "allowed_write_paths": paths or [],
        "validation_ids": validations or [], "attempt_limit": 1, "cost_class": "small",
        "placement": {key: member[key] for key in ("provider_realm", "quota_class")},
        "prerequisite_step_ids": ["STEP-0"] if depends else [], "delegation": delegation}


def seal(e, steps):
    body = {"schema_version": "mastermind.execution_plan/v5", "root_job_id": e.root.job_id,
        "coordinator_job_id": e.root.job_id, "plan_attempt_id": e.dispatch.attempt.attempt_id, "steps": steps}
    _complete_ohf_role(e.runtime, e.dispatch, body, identity_seed=48001)
    return f"coo-cycle:{e.root.job_id}:admit-plan:{e.dispatch.attempt.attempt_id}"


@pytest.mark.parametrize("pool,fault", [
    (1, "write"), (1, "tests"), (1, "paths"), (1, "coordinator"),
    (2, "write"), (2, "tests"), (2, "paths"), (2, "research"),
])
@pytest.mark.parametrize("deferred", [False, True])
def test_incompatible_step_is_refused_before_any_v5_reservation_or_child(mixed, pool, fault, deferred):
    e = mixed
    kwargs = {"depends": deferred}
    if fault == "write": kwargs["authorities"] = ["READ", "WRITE_BRANCH"]; kwargs["paths"] = ["control_plane/example.py"]
    if fault == "tests":
        kwargs["authorities"] = ["READ", "RUN_TESTS"]
        kwargs["validations"] = [canonical_digest(command) for command in e.commands]
    if fault == "paths": kwargs["paths"] = ["control_plane/example.py"]
    if fault == "research": kwargs["authorities"] = ["READ", "RESEARCH"]
    if fault == "coordinator": kwargs["delegation"] = {"descendant_limit": 4, "max_depth": 2}
    command = seal(e, [step(0, e.members[0]), step(1, e.members[pool], **kwargs)])
    with pytest.raises(er.StateConflict, match="paid placement|attended placement"):
        e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert {job.job_id for job in e.runtime.jobs.list_jobs()} == {e.root.job_id, e.planner.job_id}
    assert len(e.runtime.attempts.list_attempts()) == 1
    assert e.runtime.store.find_event_by_command_id(command) is None


def test_native_code_and_deferred_paid_analysis_materialize_with_distinct_profile_owners(mixed):
    e = mixed
    command = seal(e, [
        step(0, e.members[0], authorities=["READ", "WRITE_BRANCH"], paths=["control_plane/example.py"]),
        step(1, e.members[1], authorities=["READ", "RESEARCH"], depends=True),
    ])
    (code,) = e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert code.constraints["execution_profile_id"] == e.root.constraints["execution_profile_id"]
    assert code.requested_authorities == ["READ", "WRITE_BRANCH"]
    assert code.allowed_write_paths == e.root.allowed_write_paths
    claimed = e.runtime.attempts.dispatch_cycle_job(code.job_id,
        command_id=f"coo-cycle:{e.root.job_id}:dispatch:{code.job_id}:attempt:1", worker_id="native-worker")
    assert isinstance(claimed, er.OrchestrationDispatchOutcome)
    class NativeAdapter:
        adapter_id = "codex-cli"
    class PaidAdapter:
        adapter_id = "canonical-paid-fabric"
    native = ExecutiveSupervisor(e.runtime, NativeAdapter(), runs_root=e.tmp_path / "runs",
        inspector=object(), process_controller=object(), instance_id="inert-mixed-v5")
    paid = ExecutiveSupervisor(e.runtime, PaidAdapter(), runs_root=e.tmp_path / "paid-runs",
        inspector=object(), process_controller=object(), instance_id=native.instance_id, project_input_owner=native)
    owners = MixedExecutionOwnerSupervisor(native, {"native-worker": native, "paid-worker": paid})
    assert owners._select(claimed.attempt) is native
    finish_result(e.runtime, claimed)
    manifest = e.runtime.jobs.project_cycle_work_dependency_manifest(e.root.job_id, "STEP-1")
    deferred = e.runtime.jobs.create_cycle_work(e.root.job_id, "STEP-1", dependency_manifest=manifest,
        command_id=f"coo-cycle:{e.root.job_id}:create-work:STEP-1:{manifest['dependency_manifest_digest']}")
    assert deferred.constraints["execution_profile_id"] == "fabric.paid.glm.sealed-input.v1"
    assert deferred.requested_authorities == ["READ", "RESEARCH"]
    assert deferred.allowed_write_paths == deferred.validation_commands == []
    paid_claim = e.runtime.attempts.dispatch_cycle_job(deferred.job_id,
        command_id=f"coo-cycle:{e.root.job_id}:dispatch:{deferred.job_id}:attempt:1", worker_id="paid-worker")
    assert isinstance(paid_claim, er.OrchestrationDispatchOutcome)
    assert owners._select(paid_claim.attempt) is paid
    assert owners._foreground(deferred.job_id) is None
    assert len(e.runtime.attempts.list_attempts()) == 3


def test_native_tests_and_exact_attended_read_remain_valid_without_promoting_attended_lifetime(mixed):
    e = mixed
    command = seal(e, [
        step(0, e.members[0], authorities=["READ", "RUN_TESTS"],
            validations=[canonical_digest(command) for command in e.commands]),
        step(1, e.members[2]),
    ])
    code, attended = e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert code.validation_commands == e.commands
    assert attended.requested_authorities == ["READ"] and attended.allowed_write_paths == attended.validation_commands == []
    class Adapter:
        adapter_id = "codex-cli"
    primary = ExecutiveSupervisor(e.runtime, Adapter(), inspector=object(), process_controller=object())
    owners = MixedExecutionOwnerSupervisor(primary, {"native-worker": primary})
    with pytest.raises(ForegroundOperationRefusal):
        owners._foreground(attended.job_id)
    assert attended.current_attempt_id is None


def test_current_member_read_research_cannot_widen_its_parent(mixed):
    e = mixed
    with e.runtime.store.transaction() as connection:
        connection.execute("UPDATE jobs SET requested_authorities_json=? WHERE job_id=?", ('["READ"]', e.root.job_id))
    command = seal(e, [step(0, e.members[1], authorities=["READ", "RESEARCH"], depends=False)])
    with pytest.raises(er.StateConflict, match="shrink"):
        e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert e.runtime.store.find_event_by_command_id(command) is None


def test_planner_options_report_actual_pool_ceiling_and_continuation_without_identity(mixed):
    e = mixed
    pools = {item["quota_class"]: item for item in _planner_routing_options(e.runtime, e.planner)["pools"]}
    native, paid, attended = (pools[name] for name in ("native-code", "paid-read", "minimax-read"))
    assert native["supported_authorities"] == ["READ", "RESEARCH", "RUN_TESTS", "WRITE_BRANCH"]
    assert native["allows_write_paths"] and native["allows_validation_commands"] and native["allows_coordinator"]
    assert paid["supported_authorities"] == ["READ", "RESEARCH"]
    assert not any(paid[key] for key in ("allows_write_paths", "allows_validation_commands", "allows_coordinator"))
    assert paid["input_constraint"] == "SEALED_SUPPLIED_TEXT_ONLY"
    assert paid["continuation_constraint"] == "ROOT_CONTINUATION_MODE"
    assert attended["supported_authorities"] == ["READ"] and attended["allows_coordinator"]
    assert not attended["allows_write_paths"] and not attended["allows_validation_commands"]
    assert attended["continuation_constraint"] == "ORIGINAL_REQUEST_ONLY"
    encoded = json.dumps(pools)
    assert all(word not in encoded for word in ("native-worker", "paid-worker", "attended-worker", "account_label", "host_ref"))


def test_readonly_workspace_policy_and_profile_drift_are_not_advertised_as_code_capacity(mixed):
    e = mixed
    with e.runtime.store.transaction() as connection:
        constraints = {**e.root.constraints, er.CHILD_WORKSPACE_POLICY_KEY: er.CHILD_WORKSPACE_POLICY}
        connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?", (json.dumps(constraints, sort_keys=True, separators=(",", ":")), e.root.job_id))
        row = connection.execute("SELECT metadata_json FROM worker_quota_classes WHERE worker_id='paid-worker'").fetchone()
        metadata = json.loads(row[0]); metadata["execution_profile_digest"] = "0" * 64
        connection.execute("UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id='paid-worker'", (json.dumps(metadata),))
    pools = {item["quota_class"]: item for item in _planner_routing_options(e.runtime, e.planner)["pools"]}
    assert pools["native-code"]["supported_authorities"] == ["READ", "RESEARCH"]
    assert not pools["native-code"]["allows_write_paths"] and not pools["native-code"]["allows_validation_commands"]
    assert not pools["paid-read"]["constraints_available"] and pools["paid-read"]["supported_authorities"] == []
    command = seal(e, [step(0, e.members[0]), step(1, e.members[0],
        authorities=["READ", "WRITE_BRANCH"], paths=["control_plane/example.py"], depends=True)])
    with pytest.raises(er.StateConflict, match="isolated analysis"):
        e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert e.runtime.store.find_event_by_command_id(command) is None


def test_materialization_rechecks_a_deferred_plan_retained_before_the_route_guard(mixed, monkeypatch):
    e = mixed
    command = seal(e, [step(0, e.members[0]), step(1, e.members[1], depends=True,
        authorities=["READ", "WRITE_BRANCH"], paths=["control_plane/example.py"])])
    # Reproduce the former admission behavior only while retaining the sealed
    # plan. The current materializer must independently reject that old step.
    with monkeypatch.context() as prior:
        prior.setattr(er, "_assert_cycle_placement_compatible", lambda *args, **kwargs: None)
        (first,) = e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    claimed = e.runtime.attempts.dispatch_cycle_job(first.job_id,
        command_id=f"coo-cycle:{e.root.job_id}:dispatch:{first.job_id}:attempt:1", worker_id="native-worker")
    finish_result(e.runtime, claimed)
    manifest = e.runtime.jobs.project_cycle_work_dependency_manifest(e.root.job_id, "STEP-1")
    with pytest.raises(er.StateConflict, match="paid placement"):
        e.runtime.jobs.create_cycle_work(e.root.job_id, "STEP-1", dependency_manifest=manifest,
            command_id=f"coo-cycle:{e.root.job_id}:create-work:STEP-1:{manifest['dependency_manifest_digest']}")
    assert len(e.runtime.jobs.list_jobs()) == 3
    assert e.runtime.store.find_event_by_command_id(command) is not None


def test_unadmitted_deferred_pool_refuses_before_reservation(mixed):
    e = mixed
    unknown = {"provider_realm": "glm", "quota_class": "unadmitted-paid-pool"}
    command = seal(e, [step(0, e.members[0]), step(1, unknown, depends=True)])
    with pytest.raises(er.StateConflict, match="host work-placement union"):
        e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert e.runtime.store.find_event_by_command_id(command) is None
    assert len(e.runtime.jobs.list_jobs()) == 2


def test_planner_never_advertises_capabilities_from_incompatible_adapter_metadata(mixed):
    e = mixed
    with e.runtime.store.transaction() as connection:
        row = connection.execute("SELECT metadata_json FROM worker_quota_classes WHERE worker_id='paid-worker'").fetchone()
        metadata = json.loads(row[0]); metadata["adapter_id"] = "codex-cli"
        connection.execute("UPDATE worker_quota_classes SET metadata_json=? WHERE worker_id='paid-worker'", (json.dumps(metadata),))
    pools = {item["quota_class"]: item for item in _planner_routing_options(e.runtime, e.planner)["pools"]}
    assert pools["paid-read"]["registered_capacity_count"] == 1
    assert pools["paid-read"]["constraints_available"] is False
    assert pools["paid-read"]["supported_authorities"] == []


def test_worker_provider_remains_immutable_before_pool_projection(mixed):
    e = mixed
    with pytest.raises(er.StateConflict, match="worker provider/account identity is immutable"):
        with e.runtime.store.transaction() as connection:
            connection.execute("UPDATE workers SET provider='codex' WHERE worker_id='paid-worker'")
    pools = {item["quota_class"]: item for item in _planner_routing_options(e.runtime, e.planner)["pools"]}
    assert pools["paid-read"]["supported_authorities"] == ["READ", "RESEARCH"]
    assert e.runtime.workers.get_worker("paid-worker").provider == "glm"


def test_existing_attended_readonly_coordinator_semantics_remain_admissible(mixed):
    e = mixed
    command = seal(e, [step(0, e.members[2], delegation={"descendant_limit": 4, "max_depth": 2})])
    (coordinator,) = e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    assert coordinator.orchestration_role == "aggregation"
    assert coordinator.constraints["execution_profile_id"] == "fabric.attended.claude.bounded.v1"
    assert coordinator.requested_authorities == ["READ"] and coordinator.validation_commands == []
