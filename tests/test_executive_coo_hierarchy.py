"""Hierarchy regressions: original-root budget and legacy policy replay."""
import pytest
import copy
import sqlite3
from jsonschema import Draft202012Validator
from control_plane.executive_orchestration_result import (
    _validate_plan, _role_body_schema, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    OrchestrationResultError,
)

from control_plane.executive_coo_policy import (
    CooCyclePolicy, CooCyclePolicyError, EXPECTED_POLICY_SHA256,
    HIERARCHY_POLICY_SHA256,
)


def leaf(review=False):
    return {"review_required": review, "delegation": None}


def coordinator(count, depth=3):
    return {"review_required": False,
            "delegation": {"descendant_limit": count, "max_depth": depth}}


def reserve(steps, *, depth=0, limit=16, maximum=3):
    return CooCyclePolicy.load(version=2).reserved_hierarchy_children(
        tuple(steps), coordinator_depth=depth, descendant_limit=limit,
        max_depth=maximum,
    )


def test_legacy_policy_and_hash_remain_exact():
    old = CooCyclePolicy.load()
    assert old.schema_version == 1 and old.max_depth == 1
    assert old.policy_sha256 == EXPECTED_POLICY_SHA256
    assert CooCyclePolicy.for_digest(old.policy_sha256).to_dict() == old.to_dict()
    new = CooCyclePolicy.load(version=2)
    assert new.policy_sha256 == HIERARCHY_POLICY_SHA256 != old.policy_sha256
    assert new.max_depth == 3 and new.max_children_total == 16
    assert CooCyclePolicy.for_digest(new.policy_sha256).schema_version == 2


def test_four_levels_share_one_original_allowance():
    assert reserve([coordinator(14)]) == 16
    assert reserve([coordinator(12)], depth=1, limit=14) == 14
    assert reserve([leaf()]*11, depth=2, limit=12) == 12
    # Eleven depth-3 leaves + root planner + two coordinators + their planners.
    assert 11 + 1 + 2 + 2 == 16


def test_sibling_coordinators_cannot_each_claim_the_root_budget():
    with pytest.raises(CooCyclePolicyError, match="inherited allowance"):
        reserve([coordinator(14), coordinator(14)])


def test_nested_coordinator_cannot_replenish_budget():
    with pytest.raises(CooCyclePolicyError, match="widens"):
        reserve([coordinator(16)], depth=1, limit=14)


def test_fourth_child_generation_is_refused():
    with pytest.raises(CooCyclePolicyError, match="widens"):
        reserve([coordinator(2)], depth=2, limit=4)
    with pytest.raises(CooCyclePolicyError, match="original grant"):
        reserve([leaf()], depth=3)


def test_existing_review_repair_capacity_is_reserved():
    assert reserve([leaf(True)]) == 10
    with pytest.raises(CooCyclePolicyError, match="inherited allowance"):
        reserve([leaf(True), leaf(True)])


@pytest.mark.parametrize("field,value", [("descendant_limit", True), ("max_depth", True),
                                         ("descendant_limit", -1), ("max_depth", 4)])
def test_invalid_or_widened_grants_are_rejected(field, value):
    step = coordinator(8)
    step["delegation"][field] = value
    with pytest.raises(CooCyclePolicyError):
        reserve([step])


def test_legacy_policy_never_implicitly_admits_nested_work():
    with pytest.raises(CooCyclePolicyError, match="policy v2"):
        CooCyclePolicy.load().reserved_hierarchy_children(
            (coordinator(8),), coordinator_depth=0, descendant_limit=16, max_depth=3)


def test_unknown_admitted_hash_does_not_fall_back_to_new_policy():
    with pytest.raises(CooCyclePolicyError, match="unrecognized"):
        CooCyclePolicy.for_digest("f"*64)


def plan(count=1):
    steps = [{"ordinal": i, "step_id": f"STEP-{i}", "objective": "Bounded work",
              "business_impact": "routine", "review_required": False,
              "requested_authorities": ["READ"], "allowed_write_paths": [],
              "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
              "prerequisite_step_ids": [], "delegation": None}
             for i in range(count)]
    return {"schema_version": PLAN_SCHEMA_V5, "root_job_id": "JOB-001",
            "coordinator_job_id": "JOB-003", "plan_attempt_id": "ATT-001", "steps": steps}


def typed(value):
    return _validate_plan(value, outer={"run_id":"ATT-001", "expected_root_job_id":"JOB-001"})


def test_v5_schema_and_typed_wire_preserve_actual_parent_and_optional_model():
    value = plan()
    value["steps"][0]["delegation"] = {"descendant_limit": 8, "max_depth": 3}
    value["steps"][0]["placement"] = {"provider_realm":"codex", "quota_class":"default",
                                      "model":"gpt-6-astra"}
    Draft202012Validator(_role_body_schema("plan")).validate(value)
    assert typed(value) == value


def test_v5_wire_capacity_does_not_enlarge_v4():
    value = plan(16)
    Draft202012Validator(_role_body_schema("plan")).validate(value)
    assert typed(value) == value
    # Wire permits 16 steps; reservation also charges the planner and refuses.
    with pytest.raises(CooCyclePolicyError, match="inherited allowance"):
        reserve(value["steps"])
    legacy = copy.deepcopy(value)
    legacy["schema_version"] = PLAN_SCHEMA_V4
    del legacy["coordinator_job_id"]
    for step in legacy["steps"]: del step["delegation"]
    assert list(Draft202012Validator(_role_body_schema("plan")).iter_errors(legacy))
    with pytest.raises(OrchestrationResultError): typed(legacy)


@pytest.mark.parametrize("change", ["missing_parent", "missing_delegation", "extra_grant",
                                    "review_coordinator", "bool_depth", "too_deep"])
def test_v5_json_and_typed_validation_reject_same_malformed_grants(change):
    value = plan()
    step = value["steps"][0]
    step["delegation"] = {"descendant_limit": 8, "max_depth": 3}
    if change == "missing_parent": del value["coordinator_job_id"]
    if change == "missing_delegation": del step["delegation"]
    if change == "extra_grant": step["delegation"]["new_root"] = True
    if change == "review_coordinator": step["review_required"] = True
    if change == "bool_depth": step["delegation"]["max_depth"] = True
    if change == "too_deep": step["delegation"]["max_depth"] = 4
    assert list(Draft202012Validator(_role_body_schema("plan")).iter_errors(value))
    with pytest.raises(OrchestrationResultError): typed(value)


def test_completed_immediate_child_cannot_hide_live_grandchild():
    # Exercise the real runtime query on a minimal synthetic jobs table. The
    # fixture deliberately represents a previously incorrectly settled parent.
    from control_plane.executive_runtime import _living_child_rows, _assert_parent_aggregation_allowed, StateConflict
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY,parent_job_id TEXT,status TEXT,created_at_ms INTEGER,review_required INTEGER)")
    conn.executemany("INSERT INTO jobs VALUES(?,?,?,?,?)", [
        ("ROOT", None, "QUEUED", 0, 0),
        ("COORD-A", "ROOT", "COMPLETED", 1, 0),
        ("COORD-SOL", "COORD-A", "COMPLETED", 2, 0),
        ("LEAF", "COORD-SOL", "RUNNING", 3, 0),
        ("OTHER-ROOT", None, "RUNNING", 4, 0),
    ])
    assert [r["job_id"] for r in _living_child_rows(conn, "ROOT")] == ["LEAF"]
    assert [r["job_id"] for r in _living_child_rows(conn, "COORD-A")] == ["LEAF"]
    with pytest.raises(StateConflict, match="LEAF"):
        _assert_parent_aggregation_allowed(conn, parent_job_id="ROOT")
    conn.execute("UPDATE jobs SET status='COMPLETED' WHERE job_id='LEAF'")
    assert _living_child_rows(conn, "ROOT") == []
    _assert_parent_aggregation_allowed(conn, parent_job_id="ROOT")
    conn.close()


def tree_rows():
    return [dict(job_id=job, parent_job_id=parent, root_job_id="ROOT", depth=depth,
                 orchestration_role=role, status="QUEUED", cancel_requested_at_ms=None,
                 current_attempt_id=None, attempt_count=0)
            for job, parent, depth, role in [("ROOT", None, 0, "aggregation"),
                ("ASTRA", "ROOT", 1, "aggregation"), ("SOL", "ASTRA", 2, "aggregation"),
                ("LEAF", "SOL", 3, "work")]]


def test_ancestor_cancellation_blocks_creation_at_third_level():
    from control_plane.executive_coo_hierarchy import validate_tree, assert_admission_open, HierarchyError
    rows = tree_rows()
    rows[0]["cancel_requested_at_ms"] = 123
    with pytest.raises(HierarchyError, match="ancestor closed"):
        assert_admission_open(validate_tree(rows, "ROOT"), "SOL")


@pytest.mark.parametrize("change", ["cross_root", "cycle", "orphan", "leaf_parent", "depth"])
def test_tree_rejects_invalid_ancestry(change):
    from control_plane.executive_coo_hierarchy import validate_tree, HierarchyError
    rows = tree_rows()
    if change == "cross_root": rows[-1]["root_job_id"] = "OTHER"
    if change == "cycle": rows[1]["parent_job_id"] = "SOL"
    if change == "orphan": rows[-1]["parent_job_id"] = "MISSING"
    if change == "leaf_parent": rows[2]["orchestration_role"] = "work"
    if change == "depth": rows[-1]["depth"] = 4
    with pytest.raises(HierarchyError): validate_tree(rows, "ROOT")


def test_terminal_descendants_stay_charged_to_ancestors():
    from control_plane.executive_coo_hierarchy import (
        validate_tree, assert_creation_capacity, root_grant, inherited_grant, HierarchyError,
    )
    rows = tree_rows()
    rows[-1]["status"] = "COMPLETED"
    rows.append({**rows[-1], "job_id":"LEAF-2"})
    root = root_grant()
    astra = inherited_grant(0, root, {"descendant_limit": 4, "max_depth":3})
    sol = inherited_grant(1, astra, {"descendant_limit": 2, "max_depth":3})
    with pytest.raises(HierarchyError, match="descendant allowance"):
        assert_creation_capacity(validate_tree(rows, "ROOT"), "SOL", {"ROOT":root,"ASTRA":astra,"SOL":sol})


def test_pre_reserved_independent_sibling_does_not_inherit_unrelated_execution_state():
    from control_plane.executive_coo_hierarchy import validate_tree, assert_admission_open
    rows = tree_rows()
    # A running leaf under SOL blocks ancestor completion, not creation in an
    # independent, already reserved root branch while its ancestors remain open.
    rows[-1]["status"] = "RUNNING"
    rows.append({**rows[1], "job_id":"INDEPENDENT"})
    assert_admission_open(validate_tree(rows, "ROOT"), "INDEPENDENT")

# Full existing Runtime/OHF transitions; inert identities, no provider/network.
from test_executive_os_phase1fc import _v2_intent, _register, _complete_ohf_role
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import Runtime, OrchestrationDispatchOutcome, StateConflict


def hierarchy_runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime)
    receipt = submit_intent(runtime, _v2_intent(business_impact='routine'))
    return runtime, runtime.jobs.get_job(receipt['job_id'])


def finish_plan(runtime, parent, *, delegation=None, count=1, adjust=None):
    planner = runtime.jobs.create_cycle_planner(parent.job_id,
        command_id=f'coo-cycle:{parent.job_id}:create-planner:0')
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f'coo-cycle:{parent.job_id}:dispatch:{planner.job_id}:attempt:1', worker_id='worker-1')
    assert isinstance(dispatch, OrchestrationDispatchOutcome)
    body=plan(count)
    body.update(root_job_id=parent.root_job_id, coordinator_job_id=parent.job_id,
                plan_attempt_id=dispatch.attempt.attempt_id)
    for step in body['steps']:
        step['delegation']=delegation
    if adjust is not None:
        adjust(body)
    _complete_ohf_role(runtime,dispatch,body,identity_seed=1000+int(planner.job_id.split('-')[1]))
    return planner, body


def admit(runtime, parent, **kwargs):
    planner, body=finish_plan(runtime,parent,**kwargs)
    command=f'coo-cycle:{parent.job_id}:admit-plan:{body["plan_attempt_id"]}'
    children=runtime.jobs.admit_cycle_plan(parent.job_id,command_id=command)
    assert [j.job_id for j in runtime.jobs.admit_cycle_plan(parent.job_id,command_id=command)] == [j.job_id for j in children]
    return children


def finish_leaf(runtime,job):
    dispatch=runtime.attempts.dispatch_cycle_job(job.job_id,
        command_id=f'coo-cycle:{job.parent_job_id}:dispatch:{job.job_id}:attempt:1',worker_id='worker-1')
    assert isinstance(dispatch,OrchestrationDispatchOutcome)
    body={'schema_version':'mastermind.work_result/v1','root_job_id':job.root_job_id,
          'plan_attempt_id':job.plan_attempt_id,'plan_digest':job.plan_digest,
          'plan_step_id':job.plan_step_id,'repair_round':job.repair_round,
          'artifacts':[], 'evidence_digests':[]}
    return _complete_ohf_role(runtime,dispatch,body,identity_seed=2000+int(job.job_id.split('-')[1]))


def finish_coordinator(runtime,job):
    handoff=runtime.jobs.create_cycle_handoff(job.job_id,
        command_id=f'coo-cycle:{job.job_id}:aggregation-handoff:1')
    assert handoff['root_job_id']==job.root_job_id
    assert handoff['coordinator_job_id']==job.job_id
    keys={'ordinal','plan_step_id','current_job_id','current_attempt_id','current_result_digest',
          'repair_round','review_required','qualifying_review_job_id','qualifying_review_attempt_id',
          'qualifying_review_result_digest'}
    body={'schema_version':handoff['aggregate_result_schema'], 'coordinator_job_id':job.job_id,
          **{k:handoff[k] for k in ('root_job_id','handoff_digest','policy_sha','plan_attempt_id','plan_digest')},
          'revisions':[{k:v for k,v in r.items() if k in keys} for r in handoff['revisions']],
          'aggregate_summary':'All scoped outcomes accepted', 'evidence_digests':[]}
    dispatch=runtime.attempts.dispatch_cycle_job(job.job_id,
        command_id=f'coo-cycle:{job.job_id}:dispatch:{job.job_id}:attempt:1',worker_id='worker-1')
    assert isinstance(dispatch,OrchestrationDispatchOutcome)
    return _complete_ohf_role(runtime,dispatch,body,identity_seed=3000+int(job.job_id.split('-')[1]))


def test_runtime_four_levels_original_root_and_shared_slots(tmp_path):
    runtime,root=hierarchy_runtime(tmp_path)
    coordinator1,=admit(runtime,root,delegation={'descendant_limit':14,'max_depth':3})
    coordinator2,=admit(runtime,coordinator1,delegation={'descendant_limit':12,'max_depth':3})
    leaves=admit(runtime,coordinator2,count=11)
    jobs=runtime.jobs.list_jobs()
    assert len(jobs)==17
    assert {j.root_job_id for j in jobs}=={root.job_id}
    assert len(leaves)==11 and all(j.depth==3 for j in leaves)
    assert coordinator1.depth==1 and coordinator2.depth==2
    assert coordinator1.parent_job_id==root.job_id
    assert coordinator2.parent_job_id==coordinator1.job_id
    assert all(j.parent_job_id==coordinator2.job_id for j in leaves)
    with pytest.raises(StateConflict,match='living'):
        runtime.jobs.create_cycle_handoff(root.job_id,
            command_id=f'coo-cycle:{root.job_id}:aggregation-handoff:1')

    for job in leaves:
        finish_leaf(runtime,job)
    finish_coordinator(runtime,coordinator2)
    finish_coordinator(runtime,coordinator1)
    finish_coordinator(runtime,root)
    assert all(j.status.value=='COMPLETED' for j in runtime.jobs.list_jobs())
    restarted=Runtime.at(tmp_path)
    assert len(restarted.jobs.list_jobs())==17
    assert restarted.jobs.get_job(root.job_id).status.value=='COMPLETED'
    for job in (root, coordinator1, leaves[0]):
        current=restarted.jobs.get_job(job.job_id)
        completion=restarted.validated_role_completion(current.job_id,expected_attempt_id=current.current_attempt_id)
        with restarted.observe_bounded_read() as observation:
            selected=observation.read_role_result_bounded(root.job_id,current.job_id,
                expected_attempt_id=current.current_attempt_id,
                expected_result_envelope_digest=completion.result_digest)
        assert selected.root_job_id==root.job_id
        assert selected.completion==completion


@pytest.mark.parametrize("nested", [False,True])
def test_oversubscribed_plan_rolls_back_all_members(tmp_path,nested):
    runtime,root=hierarchy_runtime(tmp_path)
    target=root
    if nested:
        target,=admit(runtime,root,delegation={'descendant_limit':4,'max_depth':3})
    planner,body=finish_plan(runtime,target,count=4 if nested else 2,
                            delegation=None if nested else {'descendant_limit':14,'max_depth':3})
    before=[j.job_id for j in runtime.jobs.list_jobs()]
    with pytest.raises(StateConflict,match='capacity'):
        runtime.jobs.admit_cycle_plan(target.job_id,
          command_id=f'coo-cycle:{target.job_id}:admit-plan:{body["plan_attempt_id"]}')
    assert [j.job_id for j in runtime.jobs.list_jobs()]==before
    assert not any(e.event_type=='COO_PLAN_ADMITTED' for e in runtime.events.list_events(job_id=target.job_id))


@pytest.mark.parametrize("after_plan", [False, True])
def test_ancestor_cancellation_prevents_nested_creation(tmp_path,after_plan):
    runtime,root=hierarchy_runtime(tmp_path)
    child,=admit(runtime,root,delegation={'descendant_limit':8,'max_depth':3})
    if after_plan:
        planner,body=finish_plan(runtime,child)
    runtime.jobs.cancel_job(root.job_id)
    before=len(runtime.jobs.list_jobs())
    with pytest.raises(StateConflict,match='ancestor'):
        if after_plan:
            runtime.jobs.admit_cycle_plan(child.job_id,
               command_id=f'coo-cycle:{child.job_id}:admit-plan:{body["plan_attempt_id"]}')
        else:
            runtime.jobs.create_cycle_planner(child.job_id,
               command_id=f'coo-cycle:{child.job_id}:create-planner:0')
    assert len(runtime.jobs.list_jobs())==before


def test_nested_unknown_return_reconciles_same_attempt_before_aggregate(tmp_path):
    runtime,root=hierarchy_runtime(tmp_path)
    child,=admit(runtime,root,delegation={'descendant_limit':8,'max_depth':3})
    work,=admit(runtime,child)
    dispatch=runtime.attempts.dispatch_cycle_job(work.job_id,
        command_id=f'coo-cycle:{child.job_id}:dispatch:{work.job_id}:attempt:1',worker_id='worker-1')
    marker=runtime.jobs.record_cycle_dispatch_effect_unknown(child.job_id,
        selected_job_id=work.job_id,dispatch_command_id=dispatch.command_id)
    assert marker['root_job_id']==root.job_id and marker['coordinator_job_id']==child.job_id
    body={'schema_version':'mastermind.work_result/v1','root_job_id':root.job_id,
          'plan_attempt_id':work.plan_attempt_id,'plan_digest':work.plan_digest,
          'plan_step_id':work.plan_step_id,'repair_round':0,'artifacts':[],'evidence_digests':[]}
    _complete_ohf_role(runtime,dispatch,body,identity_seed=4000)
    with pytest.raises(StateConflict,match='unresolved descendant'):
        runtime.jobs.create_cycle_handoff(child.job_id,
            command_id=f'coo-cycle:{child.job_id}:aggregation-handoff:1')
    receipt=runtime.attempts.terminal_cycle_dispatch_outcome(work.job_id,command_id=dispatch.command_id)
    resolution=runtime.jobs.reconcile_cycle_dispatch_effect(child.job_id,
        selected_job_id=work.job_id,dispatch_command_id=dispatch.command_id,receipt=receipt)
    assert resolution['root_job_id']==root.job_id and resolution['coordinator_job_id']==child.job_id
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(child.job_id) is None
    assert runtime.jobs.get_job(work.job_id).attempt_count==1
    finish_coordinator(runtime,child)
    finish_coordinator(runtime,root)


def test_material_coordinator_passes_review_requirement_to_nested_leaf(tmp_path):
    runtime,root=hierarchy_runtime(tmp_path)
    child,=admit(runtime,root,delegation={'descendant_limit':14,'max_depth':3},
        adjust=lambda body:body['steps'][0].update(business_impact='material'))
    assert child.business_impact=='material' and not child.review_required
    work,=admit(runtime,child)
    assert work.review_required
    finish_leaf(runtime,work)
    with pytest.raises(StateConflict,match='qualifying independent approval'):
        finish_coordinator(runtime,child)


@pytest.mark.parametrize('nested',[False, True])
def test_block_cannot_replace_the_coordinator_policy_pin(tmp_path,nested):
    runtime,root=hierarchy_runtime(tmp_path)
    target=root
    wrong=HIERARCHY_POLICY_SHA256
    if nested:
        target,=admit(runtime,root,delegation={'descendant_limit':8,'max_depth':3})
        wrong=EXPECTED_POLICY_SHA256
    before=len(runtime.events.list_events(job_id=target.job_id))
    with pytest.raises(StateConflict,match='policy digest'):
        runtime.jobs.block_cycle(target.job_id,selected_job_id=target.job_id,
            reason='state_conflict',command_id=f'coo-cycle:{target.job_id}:block:state_conflict:{target.job_id}',
            policy_sha=wrong)
    assert len(runtime.events.list_events(job_id=target.job_id))==before


def test_nested_planner_projection_names_local_grant_and_v5(tmp_path):
    from control_plane.executive_supervisor import _planner_routing_options
    runtime,root=hierarchy_runtime(tmp_path)
    child,=admit(runtime,root,delegation={'descendant_limit':8,'max_depth':3})
    planner=runtime.jobs.create_cycle_planner(child.job_id,
        command_id=f'coo-cycle:{child.job_id}:create-planner:0')
    options=_planner_routing_options(runtime,planner)
    assert options['manual_override_plan_schema']=='mastermind.execution_plan/v5'
    assert options['hierarchy']['root_job_id']==root.job_id
    assert options['hierarchy']['coordinator_job_id']==child.job_id
    assert options['hierarchy']['grant']['descendant_limit']==8


def test_finite_halt_replays_original_nested_dispatch_scope(tmp_path,monkeypatch):
    from control_plane.executive_coo_cycle import CooCycle
    runtime,root=hierarchy_runtime(tmp_path)
    child,=admit(runtime,root,delegation={'descendant_limit':8,'max_depth':3})
    work,=admit(runtime,child)
    command=f'coo-cycle:{child.job_id}:dispatch:{work.job_id}:attempt:1'
    dispatch=runtime.attempts.dispatch_cycle_job(work.job_id,command_id=command,worker_id='worker-1')
    seen=[]
    def replay(job_id,cmd):
        seen.append((job_id,cmd))
        return dispatch
    cycle=CooCycle(runtime,dispatcher=replay)
    monkeypatch.setattr(cycle,'_finite_incumbent_allowed',lambda *args:(True,None))
    result=cycle._finite_halt_outcome(root.job_id,object(),HIERARCHY_POLICY_SHA256)
    assert result.action=='DISPATCHED' and seen==[(work.job_id,command)]
    assert runtime.jobs.get_job(work.job_id).attempt_count==1


def test_finite_halt_root_aggregation_replay_keeps_original_root(tmp_path,monkeypatch):
    from control_plane.executive_coo_cycle import CooCycle
    runtime,root=hierarchy_runtime(tmp_path)
    work,=admit(runtime,root)
    finish_leaf(runtime,work)
    runtime.jobs.create_cycle_handoff(root.job_id,command_id=f'coo-cycle:{root.job_id}:aggregation-handoff:1')
    command=f'coo-cycle:{root.job_id}:dispatch:{root.job_id}:attempt:1'
    dispatch=runtime.attempts.dispatch_cycle_job(root.job_id,command_id=command,worker_id='worker-1')
    seen=[]
    cycle=CooCycle(runtime,dispatcher=lambda job,cmd:seen.append((job,cmd)) or dispatch)
    monkeypatch.setattr(cycle,'_finite_incumbent_allowed',lambda *args:(True,None))
    result=cycle._finite_halt_outcome(root.job_id,object(),HIERARCHY_POLICY_SHA256)
    assert result.action=='DISPATCHED' and seen==[(root.job_id,command)]
