"""Original Runtime creator evidence; no installed/native policy admission."""
import copy
from pathlib import Path

import pytest

from control_plane import executive_runtime as rt
from control_plane.ceo_intent import submit_intent
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError, ExecutionCapabilityRegistry, DSH_NATIVE_CONVERSATION_PROFILE_ID as PROFILE,
)
from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT as CONTRACT, ROLE_RESULT_CONTRACT
from control_plane.model_router import ModelRouter
from test_interactive_tx5_runtime import _intent
from test_planner_producer_binding import _created, _replace_created

CANDIDATE = Path(__file__).resolve().parents[1]/"config/executive_dsh_native_conversation_capabilities.json"


def _root(tmp_path, *, armed=True, selected=None, native_registry=None, worktree=None):
    runtime = rt.Runtime.at(tmp_path/"runtime", clock=lambda: 1_800_000_000_000, lease_seconds=3600)
    registry = native_registry or ExecutionCapabilityRegistry.load(CANDIDATE)
    candidate = registry.profiles[PROFILE]  # Declaration only; resolve remains refused.
    router = ModelRouter.load()
    sealed = router.model_aliases["coo.sealed"]
    binding = {
        "eligible_quota_classes": ["default"], "provider": sealed.provider_alias,
        "model": sealed.model, "effort": sealed.effort, "cost_class": sealed.cost_class,
        "base_sha": "a"*40, "routing_policy_version": router.policy_version,
        "execution_profile_id": sealed.execution_profile_id,
        "execution_profile_digest": sealed.execution_profile_digest,
        "capability_policy_version": sealed.capability_policy_version,
        "capability_policy_digest": sealed.capability_policy_digest,
        "operator_eligible_quota_classes": ["dsh-native"],
        "operator_provider": "acp", "operator_model": "deepseek-chat", "operator_effort": "default",
        "operator_cost_class": "small", "operator_routing_policy_version": "dsh-native-test-only",
        "operator_execution_profile_id": PROFILE,
        "operator_execution_profile_digest": candidate.profile_digest,
        "operator_capability_policy_version": registry.policy_version,
        "operator_capability_policy_digest": registry.policy_digest,
        "operator_harness_binary_digest": "c"*64, "operator_harness_version": "native-test-only",
        "operator_harness_armed": armed,
    }
    intent = _intent("CEO-DSH-BINDING")
    extra = {}
    if worktree is not None:
        intent["execution_contract"]["worktree"] = str(worktree)
        extra["workspace_root"] = tmp_path
    if selected is not None:
        intent["frontier_model_alias"] = selected["model_alias"]
        extra["frontier_selection"] = selected
    receipt = submit_intent(runtime, intent, execution_binding=binding, **extra)
    return runtime, runtime.jobs.get_job(receipt["job_id"])


def _kwargs(runtime, root):
    constraints = runtime.jobs._operator_child_constraints(root)
    constraints["operator_result_contract"] = CONTRACT
    return dict(
        objective=f"Continue the native DeepSeek conversation for {root.job_id}: {root.objective}",
        department=root.department, priority=root.priority, authority_level=root.authority_level,
        branch=root.branch, worktree=root.worktree, constraints=constraints,
        attempt_limit=root.attempt_limit, requested_authorities=["READ"],
        allowed_write_paths=[], validation_commands=[],
        command_id=f"coo-cycle:{root.job_id}:create-interactive:0",
        parent_job_id=root.job_id, owner_seat="coo", escalation_target="coo",
        business_impact=root.business_impact, review_required=False, orchestration_role="plan",
        orchestration_provenance={
            "schema_version": "mastermind.executive_orchestration_provenance_source/v1",
            "creator": "coo_cycle", "source_id": root.job_id,
            "source_digest": root.orchestration_provenance_digest,
        },
        _coo_cycle_planner_capability=rt._COO_CYCLE_PLANNER_CREATION_CAPABILITY,
    )


def _stored(tmp_path):
    runtime, root = _root(tmp_path)
    # Exercise the private owner's storage sink, not profile resolution or dispatch.
    job = runtime.jobs.create_job(**_kwargs(runtime, root))
    assert runtime.attempts.list_attempts() == []
    return runtime, root, job


def test_original_creator_stores_exact_binding_and_reconciles_replay(tmp_path):
    runtime, root, job = _stored(tmp_path)
    binding = runtime.jobs.get_native_conversation_binding(job.job_id)
    assert binding["result_contract"] == CONTRACT
    assert binding["execution_binding_digest"] == rt.orchestration_digest(job.constraints)
    assert runtime.jobs.operator_result_contract(job.job_id) == CONTRACT
    assert runtime.jobs.get_planner_producer_binding(job.job_id) is None
    assert runtime.jobs.assert_native_conversation_execution(job.job_id) == binding
    assert runtime.jobs.create_job(**_kwargs(runtime, root)).job_id == job.job_id
    assert _created(runtime, job)["operator_result_binding"] == binding
    assert len(runtime.jobs.list_jobs()) == 2
    assert runtime.attempts.list_attempts() == []
    reopened = rt.Runtime.at(tmp_path/"runtime")
    assert reopened.jobs.get_native_conversation_binding(job.job_id) == binding


def test_public_creator_cannot_execute_disabled_or_missing_native_profile(tmp_path, monkeypatch):
    runtime, root = _root(tmp_path)
    missing = ExecutionCapabilityRegistry.load()
    del missing.profiles[PROFILE]
    for registry in (missing, ExecutionCapabilityRegistry.load(CANDIDATE)):
        with monkeypatch.context() as m:
            m.setattr(ExecutionCapabilityRegistry, "load", classmethod(lambda cls: registry))
            with pytest.raises(CapabilityPolicyError):
                runtime.jobs.create_interactive_operator(
                    root.job_id, command_id=f"coo-cycle:{root.job_id}:create-interactive:0")
        assert len(runtime.jobs.list_jobs()) == 1
        assert runtime.attempts.list_attempts() == []


@pytest.mark.parametrize("change", [
    {"_coo_cycle_planner_capability": None},
    {"command_id": "coo-cycle:JOB-001:create-planner:0"},
    {"orchestration_role": "work"}, {"parent_job_id": None},
    {"_planner_plan_schema_version": "mastermind.execution_plan/v3"},
])
def test_native_selector_is_reserved_before_insertion(tmp_path, change):
    runtime, root = _root(tmp_path)
    kwargs = _kwargs(runtime, root)
    kwargs.update(change)
    with pytest.raises(rt.StateConflict, match="native result selection"):
        runtime.jobs.create_job(**kwargs)
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize("key,value", [
    ("operator_result_contract", ROLE_RESULT_CONTRACT), ("operator_result_contract", None),
    ("execution_profile_id", "operator.appserver.interactive.v1"),
    ("provider", "codex"), ("model", "borrowed-model"), ("harness_binary_digest", "f"*64),
])
def test_mutable_job_constraints_cannot_replace_original_contract(tmp_path, key, value):
    runtime, root, job = _stored(tmp_path)
    constraints = copy.deepcopy(job.constraints)
    if value is None:
        del constraints[key]
    else:
        constraints[key] = value
    with runtime.store.transaction() as connection:
        connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                           (rt._json_dumps(constraints), job.job_id))
    with pytest.raises(rt.StateConflict):
        runtime.jobs.get_native_conversation_binding(job.job_id)
    with pytest.raises(rt.StateConflict):
        runtime.jobs.operator_result_contract(job.job_id)


@pytest.mark.parametrize("mutation", [
    "missing_binding", "missing_digest", "extra_field", "wrong_digest", "mixed_planner",
    "wrong_root", "wrong_command",
])
def test_original_creation_binding_refuses_drift(tmp_path, mutation):
    runtime, root, job = _stored(tmp_path)
    payload = _created(runtime, job)
    binding = payload["operator_result_binding"]
    if mutation == "missing_binding":
        del payload["operator_result_binding"]
    elif mutation == "missing_digest":
        del payload["operator_result_binding_digest"]
    elif mutation == "extra_field":
        binding["authority"] = True
    elif mutation == "wrong_digest":
        payload["operator_result_binding_digest"] = "f"*64
    elif mutation == "mixed_planner":
        payload["planner_producer_binding"] = {}
    elif mutation == "wrong_root":
        binding["root_job_id"] = "JOB-999"
    elif mutation == "wrong_command":
        binding["command_id"] = "coo-cycle:JOB-001:create-planner:0"
    _replace_created(runtime, job, payload)
    with pytest.raises(rt.StateConflict):
        runtime.jobs.get_native_conversation_binding(job.job_id)
    with pytest.raises(rt.StateConflict):
        runtime.jobs.create_job(**_kwargs(runtime, root))


def test_native_declaration_without_armed_tuple_never_uses_fallback(tmp_path):
    runtime, root = _root(tmp_path, armed=False)
    with pytest.raises(rt.StateConflict, match="complete armed"):
        runtime.jobs._operator_child_constraints(root)


def test_native_fresh_execution_matches_root_even_without_ceo_selection(tmp_path):
    runtime, root, job = _stored(tmp_path)
    changed = dict(root.constraints, operator_model="changed-model")
    with runtime.store.transaction() as connection:
        connection.execute("UPDATE jobs SET constraints_json=? WHERE job_id=?",
                           (rt._json_dumps(changed), root.job_id))
    assert runtime.jobs.get_native_conversation_binding(job.job_id) is not None
    with pytest.raises(rt.StateConflict, match="differs from its admitted root"):
        runtime.jobs.assert_native_conversation_execution(job.job_id)


def test_native_selection_cannot_relabel_another_ceo_model(tmp_path):
    from control_plane.frontier_selection import resolve_selection
    selected = resolve_selection(ModelRouter.load(), "frontier.orchestrator")
    runtime, root = _root(tmp_path, selected=selected)
    with pytest.raises(rt.StateConflict, match="selected CEO differs"):
        runtime.jobs.create_job(**_kwargs(runtime, root))
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize("profile_id", [PROFILE.upper(), f"  {PROFILE}  "])
def test_normalization_cannot_bypass_native_creator_reservation(tmp_path, profile_id):
    runtime, root = _root(tmp_path)
    constraints = runtime.jobs._operator_child_constraints(root)
    constraints["execution_profile_id"] = profile_id
    assert "operator_result_contract" not in constraints
    with pytest.raises(rt.StateConflict, match="native result selection"):
        runtime.jobs.create_job("Ordinary caller cannot select native authority",
                                constraints=constraints, requested_authorities=["READ"])
    assert len(runtime.jobs.list_jobs()) == 1
    assert runtime.attempts.list_attempts() == []
