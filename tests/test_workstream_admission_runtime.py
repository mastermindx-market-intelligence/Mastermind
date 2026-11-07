"""Temporary real SQLite transactions only; no host, provider or live Runtime."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import dataclasses
import threading

import pytest
from control_plane import executive_runtime as owner
from control_plane.executive_runtime import Runtime, StateConflict

WORK = "WS:PAUSE-ONE"
OTHER = "WS:PAUSE-TWO"

def project(runtime, work=WORK, *, parent=None, command="create-project", provenance=None):
    return runtime.jobs.create_job("A scoped test job", command_id=command,
        parent_job_id=parent, provenance=provenance if provenance is not None else {"workstream": work})

def pause(runtime, command="pause-project", actor="test-operator"):
    return runtime.jobs.pause_workstream_admission(WORK, command_id=command, actor=actor)

def mutable_rows(runtime):
    with runtime.store.read() as connection:
        return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("jobs", "attempts", "workers", "worker_quota_classes")}

def event_count(runtime):
    with runtime.store.read() as connection:
        return connection.execute("SELECT count(*) FROM events").fetchone()[0]

def test_pause_is_a_committed_receipt_and_identical_command_reconciles_without_writes(tmp_path):
    runtime=Runtime.at(tmp_path)
    assert runtime.jobs.read_workstream_admission_suspension(WORK) is None
    count=event_count(runtime)
    receipt=pause(runtime)
    assert receipt["state"] == "PAUSED" and receipt["work_ref"] == WORK
    assert receipt["command_id"] == "pause-project"
    assert runtime.jobs.read_workstream_admission_suspension(WORK) == receipt
    assert event_count(runtime) == count+1
    assert pause(runtime) == receipt
    assert event_count(runtime) == count+1
    assert set(receipt) == {"schema", "state", "work_ref", "event_id", "command_id", "request_digest", "committed_at_ms"}

@pytest.mark.parametrize("mutation", ["actor", "foreign_work", "foreign_command_family"])
def test_same_command_cannot_change_request_or_relabel_another_event(tmp_path, mutation):
    runtime=Runtime.at(tmp_path)
    if mutation=="foreign_command_family":
        project(runtime, command="pause-project")
    else:
        pause(runtime)
    count=event_count(runtime)
    with pytest.raises(StateConflict):
        if mutation=="foreign_work": runtime.jobs.pause_workstream_admission(OTHER, command_id="pause-project", actor="test-operator")
        elif mutation=="actor": pause(runtime, actor="other-operator")
        else: pause(runtime)
    assert event_count(runtime)==count

@pytest.mark.parametrize("work", ["WS:PAUSE-ONE\n", "WS:lower", "WS:X", "WS:../private", None])
def test_bad_scope_cannot_persist_pause(tmp_path, work):
    runtime=Runtime.at(tmp_path)
    with pytest.raises(StateConflict): runtime.jobs.pause_workstream_admission(work, command_id="pause-one", actor="test")
    assert event_count(runtime)==0

def test_pause_blocks_future_roots_and_root_derived_children_but_preserves_other_and_unscoped_work(tmp_path):
    runtime=Runtime.at(tmp_path)
    root=project(runtime)
    pause(runtime)
    before=mutable_rows(runtime); count=event_count(runtime)
    with pytest.raises(StateConflict, match="WORKSTREAM_ADMISSION_SUSPENDED"):
        project(runtime, command="new-root")
    with pytest.raises(StateConflict, match="WORKSTREAM_ADMISSION_SUSPENDED"):
        project(runtime, parent=root.job_id, command="new-child", provenance={"workstream":OTHER})
    assert mutable_rows(runtime)==before and event_count(runtime)==count
    other=project(runtime, OTHER, command="other-root")
    project(runtime, OTHER, parent=other.job_id, command="other-child",provenance={"workstream":WORK})
    runtime.jobs.create_job("Legacy unscoped work", command_id="legacy-root")

def test_cycle_child_insert_uses_same_gate_before_any_effect(tmp_path):
    runtime=Runtime.at(tmp_path); root=project(runtime); pause(runtime)
    before=mutable_rows(runtime); count=event_count(runtime)
    with runtime.store.transaction() as connection:
        row=connection.execute("SELECT * FROM jobs WHERE job_id=?",(root.job_id,)).fetchone()
        with pytest.raises(StateConflict, match="WORKSTREAM_ADMISSION_SUSPENDED"):
            owner._insert_cycle_child(connection,runtime.store,root_row=row,role="work",objective="new child",
                requested_authorities=["READ"],allowed_write_paths=[],validation_commands=[],cost_class="small",
                attempt_limit=1,review_required=False,command_id="cycle-child",plan_attempt_id="ATT-test",
                plan_digest="a"*64,plan_step_id="STEP-1",repair_round=0)
    assert mutable_rows(runtime)==before and event_count(runtime)==count

@pytest.mark.parametrize("queued_child",[False,True])
def test_queued_work_cannot_acquire_new_attempt_but_claimed_lease_can_still_start(tmp_path,queued_child):
    runtime=Runtime.at(tmp_path)
    runtime.workers.register_worker("worker-01",provider="codex",account_label="test",worker_type="test")
    runtime.workers.register_worker("worker-02",provider="codex",account_label="test2",worker_type="test")
    claimed=project(runtime,command="claimed-root")
    lease=runtime.attempts.claim_job(claimed.job_id); assert lease is not None
    queued=project(runtime,command="queued-root",parent=claimed.job_id if queued_child else None)
    before=mutable_rows(runtime); pause(runtime)
    assert mutable_rows(runtime)==before
    assert runtime.attempts.claim_job(queued.job_id,worker_id="worker-02") is None
    assert mutable_rows(runtime)==before
    runtime.attempts.record_process(lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token, provider_session_id="fixture-session")
    runtime.attempts.mark_running(lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token)
    current=runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert current is not None and current.status.value=="RUNNING"

def test_pause_append_failure_rolls_back_receipt_and_gate(tmp_path,monkeypatch):
    runtime=Runtime.at(tmp_path); original=runtime.store.append_event
    def failed(connection,**kwargs):
        original(connection,**kwargs)
        if kwargs["event_type"]=="WORKSTREAM_ADMISSION_SUSPENDED": raise RuntimeError("test rollback")
    monkeypatch.setattr(runtime.store,"append_event",failed)
    with pytest.raises(RuntimeError,match="test rollback"): pause(runtime)
    assert runtime.jobs.read_workstream_admission_suspension(WORK) is None
    assert event_count(runtime)==0
    project(runtime)

def test_unknown_latest_workstream_event_is_not_silently_overwritten_or_admitted(tmp_path):
    runtime=Runtime.at(tmp_path)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection,aggregate_type="workstream",aggregate_id=WORK,event_type="UNKNOWN_STATE",command_id="unknown")
    count=event_count(runtime)
    with pytest.raises(StateConflict,match="WORKSTREAM_SUSPENSION_SOURCE_INVALID"): pause(runtime)
    with pytest.raises(StateConflict,match="WORKSTREAM_SUSPENSION_SOURCE_INVALID"): project(runtime)
    assert event_count(runtime)==count

@pytest.mark.parametrize("provenance", [{"workstream":WORK+"\n"},{"dialogue_source":{"work_ref":WORK}},{"workstream":WORK,"dialogue_source":{"work_ref":OTHER}}])
def test_missing_or_conflicting_required_binding_is_not_unscoped_legacy(tmp_path,provenance):
    runtime=Runtime.at(tmp_path)
    with pytest.raises(StateConflict,match="WORKSTREAM_ADMISSION_SOURCE"):
        project(runtime,provenance=provenance)
    assert event_count(runtime)==0

def test_private_carrier_capability_cannot_bypass_project_gate_or_relabel_closed_provenance(tmp_path,monkeypatch):
    runtime=Runtime.at(tmp_path); captured=[]
    original=runtime.jobs._create_job_in_transaction
    class Capture(Exception): pass
    def capture(connection,*,spec,**kwargs): captured.append(spec); raise Capture()
    monkeypatch.setattr(runtime.jobs,"_create_job_in_transaction",capture)
    with pytest.raises(Capture): project(runtime)
    spec=captured[0]; pause(runtime)
    with runtime.store.transaction() as connection:
        with pytest.raises(StateConflict,match="private C2"):
            original(connection,spec=spec,_c2_capability=object())
        forged=dataclasses.replace(spec,event_provenance={"schema_version":"mastermind.sol_session_carrier/v1","workstream":WORK})
        with pytest.raises(StateConflict,match="private C2"):
            original(connection,spec=forged,_c2_capability=owner._CAPACITY_C2_R1A_CAPABILITY)
    assert runtime.jobs.list_jobs()==[]

@pytest.mark.parametrize("first", ["pause", "root", "claim"])
def test_pause_and_new_admission_or_claim_linearize_under_same_writer_lock(tmp_path,monkeypatch,first):
    runtime=Runtime.at(tmp_path)
    runtime.workers.register_worker("worker-01",provider="codex",account_label="test",worker_type="test")
    queued=project(runtime,command="queued")
    entered=threading.Event(); release=threading.Event(); second_started=threading.Event()
    original=runtime.store.transaction
    @contextmanager
    def ordered():
        if threading.current_thread().name.startswith("second"):
            second_started.set()
        with original() as connection:
            if threading.current_thread().name.startswith("first"):
                entered.set(); assert release.wait(5)
            yield connection
    monkeypatch.setattr(runtime.store,"transaction",ordered)
    def first_action():
        if first=="pause": return pause(runtime)
        if first=="root": return project(runtime,command="ordered-root")
        return runtime.attempts.claim_job(queued.job_id)
    def second_action():
        if first=="pause":
            with pytest.raises(StateConflict,match="WORKSTREAM_ADMISSION_SUSPENDED"):
                project(runtime,command="ordered-root")
            return runtime.attempts.claim_job(queued.job_id)
        return pause(runtime)
    with ThreadPoolExecutor(1,thread_name_prefix="first") as a, ThreadPoolExecutor(1,thread_name_prefix="second") as b:
        one=a.submit(first_action); assert entered.wait(5)
        two=b.submit(second_action); assert second_started.wait(5)
        release.set(); result=one.result(5); latter=two.result(5)
    if first=="pause": assert result["state"]=="PAUSED" and latter is None
    elif first=="root": assert result.job_id != queued.job_id and latter["state"]=="PAUSED"
    else:
        assert result is not None and latter["state"]=="PAUSED"
        assert runtime.attempts.get_attempt(result.attempt.attempt_id)==result.attempt

def test_real_completed_plan_cannot_insert_children_or_admission_receipt_after_pause(tmp_path,monkeypatch):
    import test_executive_os_phase1fc as phase
    runtime=Runtime.at(tmp_path); phase._register_placement_union(runtime)
    original_intent=phase._v2_intent
    monkeypatch.setattr(phase,"_v2_intent",lambda **kwargs: original_intent(**{**kwargs,"workstream":WORK}))
    original_admit=runtime.jobs.admit_cycle_plan
    class Observed(Exception): pass
    def paused_admit(*args,**kwargs):
        pause(runtime); before=mutable_rows(runtime); count=event_count(runtime)
        with pytest.raises(StateConflict,match="WORKSTREAM_ADMISSION_SUSPENDED"):
            original_admit(*args,**kwargs)
        assert mutable_rows(runtime)==before and event_count(runtime)==count
        raise Observed()
    monkeypatch.setattr(runtime.jobs,"admit_cycle_plan",paused_admit)
    with pytest.raises(Observed): phase._admit_v2_plan(runtime,placements=[
        {"provider_realm":"codex","quota_class":"codex-hf1q-step"},
        {"provider_realm":"claude-compatible-subscription","quota_class":"claude-hf1q-step"}])

def test_actual_unknown_harness_effect_and_existing_writer_facts_survive_pause(tmp_path,monkeypatch):
    import test_ohf_p1b_runtime as harness_fixture
    from control_plane.operator_harness_contract import OperationId,OperationReceiptKind,operation_receipt_command_id
    def scoped_lease(path):
        runtime=Runtime.at(path)
        runtime.workers.register_worker("worker-01",provider="codex",account_label="test",worker_type="test")
        job=project(runtime); lease=runtime.attempts.claim_job(job.job_id); assert lease is not None
        return runtime,lease
    monkeypatch.setattr(harness_fixture,"_lease",scoped_lease)
    runtime,lease,epoch,generation=harness_fixture._started(tmp_path)
    operation=OperationId("ohf-op:unknown-checkpoint")
    runtime.operator_harness.reserve_checkpoint_operation(generation=generation,operation_id=operation,
        fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
    assert runtime.operator_harness.record_effect_unknown(attempt_id=lease.attempt.attempt_id,operation_id=operation,
        fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,phase="checkpoint",detail="inert fixture unknown")
    command=operation_receipt_command_id(operation,OperationReceiptKind.EFFECT_UNKNOWN)
    unknown=runtime.store.get_event_by_command_id(command); assert unknown is not None
    before=mutable_rows(runtime)
    with runtime.store.read() as connection:
        epochs=[tuple(row) for row in connection.execute("SELECT * FROM harness_session_epochs ORDER BY 1")]
        generations=[tuple(row) for row in connection.execute("SELECT * FROM process_generations ORDER BY 1")]
    pause(runtime)
    assert runtime.store.get_event_by_command_id(command)==unknown
    assert mutable_rows(runtime)==before
    with runtime.store.read() as connection:
        assert [tuple(row) for row in connection.execute("SELECT * FROM harness_session_epochs ORDER BY 1")]==epochs
        assert [tuple(row) for row in connection.execute("SELECT * FROM process_generations ORDER BY 1")]==generations

def test_original_pause_reconciliation_never_opens_a_writer(tmp_path,monkeypatch):
 runtime=Runtime.at(tmp_path); receipt=pause(runtime)
 def forbidden(): raise AssertionError("reconciliation tried to mutate")
 monkeypatch.setattr(runtime.store,"transaction",forbidden)
 assert pause(runtime)==receipt

def test_simultaneous_identical_pause_commands_commit_exactly_one_event(tmp_path):
 runtime=Runtime.at(tmp_path); ready=threading.Barrier(2)
 def command(): ready.wait(5); return pause(runtime)
 with ThreadPoolExecutor(2) as pool:
  first=pool.submit(command);second=pool.submit(command)
  assert first.result(5)==second.result(5)
 assert event_count(runtime)==1

def test_changed_host_guard_rolls_back_and_never_publishes_committed_pause(tmp_path):
 runtime=Runtime.at(tmp_path); calls=[]
 def guard():
  calls.append(True)
  if len(calls)==3: raise StateConflict("source permission changed")
 with pytest.raises(StateConflict,match="source permission changed"):
  runtime.jobs.pause_workstream_admission(WORK,command_id="guarded-pause",actor="test",_commit_guard=guard)
 assert event_count(runtime)==0
 assert runtime.jobs.read_workstream_admission_suspension(WORK) is None
 project(runtime)

def test_original_command_read_rechecks_host_guard_without_changing_receipt(tmp_path):
 runtime=Runtime.at(tmp_path); receipt=pause(runtime); calls=[]
 def guard(): calls.append(True)
 assert runtime.jobs.pause_workstream_admission(WORK,command_id="pause-project",actor="test-operator",_commit_guard=guard)==receipt
 assert len(calls)==2 and event_count(runtime)==1

def test_read_only_runtime_can_reconcile_original_pause_but_cannot_issue_a_new_one(tmp_path):
    runtime=Runtime.at(tmp_path); receipt=pause(runtime)
    observed=Runtime.at(tmp_path,create=False)
    assert pause(observed)==receipt
    with pytest.raises(StateConflict,match="read-only store"):
        observed.jobs.pause_workstream_admission(OTHER,command_id="new-read-only-command",actor="test")
    assert event_count(runtime)==1

def test_original_command_status_is_read_only_and_absence_never_issues_pause(tmp_path,monkeypatch):
 runtime=Runtime.at(tmp_path);receipt=pause(runtime)
 def forbidden(): raise AssertionError("status read attempted mutation")
 monkeypatch.setattr(runtime.store,"transaction",forbidden)
 assert runtime.jobs.read_workstream_admission_pause_command(WORK,command_id="pause-project",actor="test-operator")==receipt
 assert runtime.jobs.read_workstream_admission_pause_command(WORK,command_id="not-observed",actor="test-operator") is None
 with pytest.raises(StateConflict):
  runtime.jobs.read_workstream_admission_pause_command(OTHER,command_id="pause-project",actor="test-operator")
 with pytest.raises(StateConflict):
  runtime.jobs.read_workstream_admission_pause_command(WORK,command_id="pause-project",actor="other-operator")
 assert event_count(runtime)==1

def test_scope_guard_reads_actual_root_creation_not_child_tag_or_mutable_constraints(tmp_path):
 runtime=Runtime.at(tmp_path);root=project(runtime)
 child=project(runtime,parent=root.job_id,command="scoped-child",provenance={"workstream":OTHER})
 assert runtime.jobs.admission_workstream_for_root(root.job_id)==WORK
 with pytest.raises(StateConflict,match="ROOT_INVALID"):
  runtime.jobs.admission_workstream_for_root(child.job_id)
 legacy=runtime.jobs.create_job("unscoped legacy",command_id="unscoped")
 assert runtime.jobs.admission_workstream_for_root(legacy.job_id) is None
 with pytest.raises(StateConflict): runtime.jobs.admission_workstream_for_root(root.job_id+"\n")
