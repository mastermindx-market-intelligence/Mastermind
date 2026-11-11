"""Real temporary Runtime pause/resume chain; no installed or provider effects."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

import pytest
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane import workstream_resumption_contract as law
from test_workstream_admission_runtime import WORK, OTHER, project, pause, mutable_rows, event_count


def kwargs(receipt,command="resume-original",actor="resumer"):
    return dict(command_id=command,actor=actor,expected_pause_event_id=receipt["event_id"],
                expected_pause_receipt_digest=law.pause_receipt_digest(receipt))

def resume(runtime,receipt,**overrides):
    return runtime.jobs.resume_workstream_admission(WORK,**{**kwargs(receipt),**overrides})


def test_resume_opens_only_new_admission_and_preserves_historical_pause(tmp_path):
    runtime=Runtime.at(tmp_path);queued=project(runtime)
    runtime.workers.register_worker("worker-01",provider="codex",account_label="test",worker_type="test")
    stopped=pause(runtime);before=mutable_rows(runtime)
    returned=resume(runtime,stopped)
    assert returned["state"]=="RESUMED" and returned["pause_event_id"]==stopped["event_id"]
    assert mutable_rows(runtime)==before
    assert runtime.jobs.read_workstream_admission_suspension(WORK) is None
    assert runtime.jobs.read_workstream_admission_transition(WORK)==returned
    assert runtime.jobs.read_workstream_admission_pause_command(WORK,command_id="pause-project",actor="test-operator")==stopped
    assert runtime.jobs.read_workstream_admission_resume_command(WORK,command_id="resume-original",actor="resumer")==returned
    assert runtime.attempts.claim_job(queued.job_id) is not None
    project(runtime,command="new-root-after-resume")


def test_same_resume_command_reconciles_read_only_even_after_later_pause(tmp_path,monkeypatch):
    runtime=Runtime.at(tmp_path);first=pause(runtime);returned=resume(runtime,first)
    later=pause(runtime,command="later-pause");count=event_count(runtime)
    def forbidden(): raise AssertionError("original reconciliation attempted a writer")
    monkeypatch.setattr(runtime.store,"transaction",forbidden)
    assert resume(runtime,first)==returned
    assert runtime.jobs.read_workstream_admission_suspension(WORK)==later
    assert event_count(runtime)==count

@pytest.mark.parametrize("change",["old_pause","wrong_digest","wrong_id","foreign_work","same_command_changed_token","same_command_changed_actor","pause_command_collision"])
def test_resume_requires_exact_current_pause_and_original_request_identity(tmp_path,change):
    runtime=Runtime.at(tmp_path);first=pause(runtime)
    args=kwargs(first);selected=WORK
    if change=="old_pause":pause(runtime,command="newer-pause")
    elif change=="wrong_digest":args["expected_pause_receipt_digest"]="f"*64
    elif change=="wrong_id":args["expected_pause_event_id"]=first["event_id"]+10
    elif change=="foreign_work":selected=OTHER
    elif change in {"same_command_changed_token","same_command_changed_actor"}:
        resume(runtime,first);later=pause(runtime,command="another-pause")
        if change=="same_command_changed_token":args=kwargs(later)
        else:args["actor"]="other-resumer"
    elif change=="pause_command_collision":args["command_id"]="pause-project"
    before=mutable_rows(runtime);count=event_count(runtime)
    with pytest.raises(StateConflict):runtime.jobs.resume_workstream_admission(selected,**args)
    assert mutable_rows(runtime)==before and event_count(runtime)==count

@pytest.mark.parametrize("change",["never_paused","already_resumed","unknown_latest"])
def test_absent_open_or_unknown_gate_cannot_be_resumed_again(tmp_path,change):
    runtime=Runtime.at(tmp_path)
    if change=="never_paused":
        args=dict(command_id="resume-original",actor="resumer",expected_pause_event_id=1,expected_pause_receipt_digest="a"*64)
    else:
        first=pause(runtime);args=kwargs(first,command="new-resume-command")
        if change=="already_resumed":resume(runtime,first)
        else:
            with runtime.store.transaction() as connection:
                runtime.store.append_event(connection,aggregate_type="workstream",aggregate_id=WORK,event_type="UNKNOWN",command_id="unknown")
    count=event_count(runtime)
    with pytest.raises(StateConflict):runtime.jobs.resume_workstream_admission(WORK,**args)
    assert event_count(runtime)==count


def test_permission_loss_in_commit_rolls_back_resume_and_leaves_pause_current(tmp_path):
    runtime=Runtime.at(tmp_path);first=pause(runtime);calls=[]
    def guard():
        calls.append(True)
        if len(calls)==3:raise StateConflict("permission changed")
    with pytest.raises(StateConflict,match="permission changed"):resume(runtime,first,_commit_guard=guard)
    assert event_count(runtime)==1 and runtime.jobs.read_workstream_admission_suspension(WORK)==first
    assert runtime.jobs.read_workstream_admission_resume_command(WORK,command_id="resume-original",actor="resumer") is None


def test_unknown_original_resume_status_is_observation_only(tmp_path,monkeypatch):
    runtime=Runtime.at(tmp_path);first=pause(runtime);before=event_count(runtime)
    def forbidden():raise AssertionError("status read attempted mutation")
    monkeypatch.setattr(runtime.store,"transaction",forbidden)
    assert runtime.jobs.read_workstream_admission_resume_command(WORK,command_id="not-observed",actor="resumer") is None
    assert runtime.jobs.read_workstream_admission_suspension(WORK)==first and event_count(runtime)==before


def test_current_gate_rejects_resume_fork_instead_of_trusting_old_pause_token(tmp_path):
    runtime=Runtime.at(tmp_path);first=pause(runtime);pause(runtime,command="newer-pause")
    request=law.make_resume_request(WORK,**kwargs(first))
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection,aggregate_type="workstream",aggregate_id=WORK,
            event_type="WORKSTREAM_ADMISSION_RESUMED",command_id="resume-original",actor="resumer",payload=law.make_resume_payload(request))
    with pytest.raises(StateConflict):runtime.jobs.read_workstream_admission_transition(WORK)
    with pytest.raises(StateConflict):project(runtime,command="must-remain-held")


def test_two_equal_resume_requests_commit_one_event(tmp_path):
    runtime=Runtime.at(tmp_path);first=pause(runtime);ready=threading.Barrier(2)
    def action():ready.wait(5);return resume(runtime,first)
    with ThreadPoolExecutor(2) as pool:
        one=pool.submit(action);two=pool.submit(action)
        assert one.result(5)==two.result(5)
    assert event_count(runtime)==2

@pytest.mark.parametrize("first_operation",["resume","pause"])
def test_pause_resume_race_is_ordered_by_original_writer_transaction(tmp_path,monkeypatch,first_operation):
    runtime=Runtime.at(tmp_path);first=pause(runtime);before=mutable_rows(runtime)
    entered=threading.Event();release=threading.Event();other=threading.Event();original=runtime.store.transaction
    @contextmanager
    def ordered():
        if threading.current_thread().name.startswith("second"):other.set()
        with original() as connection:
            if threading.current_thread().name.startswith("first"):entered.set();assert release.wait(5)
            yield connection
    monkeypatch.setattr(runtime.store,"transaction",ordered)
    def one():return resume(runtime,first) if first_operation=="resume" else pause(runtime,command="concurrent-pause")
    def two():
        if first_operation=="resume":return pause(runtime,command="concurrent-pause")
        with pytest.raises(StateConflict,match="STALE_PAUSE"):resume(runtime,first)
    with ThreadPoolExecutor(1,thread_name_prefix="first") as a,ThreadPoolExecutor(1,thread_name_prefix="second") as b:
        left=a.submit(one);assert entered.wait(5)
        right=b.submit(two);assert other.wait(5);release.set();left.result(5);right.result(5)
    assert runtime.jobs.read_workstream_admission_suspension(WORK)["command_id"]=="concurrent-pause"
    assert mutable_rows(runtime)==before
