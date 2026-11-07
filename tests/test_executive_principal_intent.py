"""Hermetic COO admission through the existing sink; no live service or OAuth."""
from __future__ import annotations
import copy
import dataclasses
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from control_plane import ceo_intent as sink
from control_plane.coo_principal_envelope import PrincipalAdmissionContext, derive_principal_envelope
from control_plane.executive_runtime import Runtime, JobStatus


def context(**changes):
    value = PrincipalAdmissionContext("WS:EXECUTIVE-CAPACITY-FABRIC", "1" * 64,
                                     "authority:coo-test", "2" * 64)
    return dataclasses.replace(value, **changes)


def bundle(root, *, ctx=None, **changes):
    request = dict(operation_key="coo-sink-proof", objective="Inspect the assigned mission.",
                   department="executive-infrastructure", priority=7,
                   execution_profile="research_only", workstream=context().work_ref)
    request.update(changes)
    return derive_principal_envelope(request, context=ctx or context(),
        workspace_root=str(root / "workspaces"),
        grounding={"mastermind_sha": "a" * 40, "macro_sha": "b" * 40})


def allow(_envelope):
    return None


def submit(runtime, root, value=None, *, ctx=None, guard=allow):
    value = value or bundle(root, ctx=ctx)
    return sink.submit_intent(runtime, value["envelope"],
        workspace_root=root / "workspaces", principal_context=ctx or context(),
        principal_request_ref=value["request_ref"], principal_admission_guard=guard)


def test_real_sink_admits_one_role_correct_job_and_persists_receipt(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    receipt = submit(runtime, tmp_path)
    assert receipt["schema"] == "mastermind.executive_principal_intent_receipt.v1"
    assert receipt["request_ref"] == bundle(tmp_path)["request_ref"]
    assert receipt["status"] == "QUEUED" and receipt["dispatched"] is False
    assert receipt["principal"]["seat"] == "coo"
    assert receipt["principal"]["principal_binding_digest"] == "1" * 64
    jobs = runtime.jobs.list_jobs()
    assert len(jobs) == 1 and jobs[0].status is JobStatus.QUEUED
    assert jobs[0].owner_seat == jobs[0].escalation_target == "coo"
    assert jobs[0].requested_authorities == ["READ", "RESEARCH"]
    assert jobs[0].attempt_count == 0
    reopened = Runtime.at(tmp_path / "runtime")
    assert sink.resolve_intent(reopened, receipt["intent_id"]) == receipt


@pytest.mark.parametrize("guard", [None, False, lambda _: True])
def test_missing_or_non_none_guard_cannot_create_job(tmp_path, guard):
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError, match="principal admission"):
        submit(runtime, tmp_path, guard=guard)
    assert runtime.jobs.list_jobs() == []


def test_durable_replay_precedes_dynamic_guard_and_semantic_conflicts(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    first = submit(runtime, tmp_path)
    def no_longer_current(_):
        raise AssertionError("dynamic state changed after admission")
    second = submit(runtime, tmp_path, guard=no_longer_current)
    assert second == dict(first, duplicate=True)
    with pytest.raises(sink.CeoIntentConflict):
        submit(runtime, tmp_path, bundle(tmp_path, objective="Different objective"),
               guard=no_longer_current)
    assert len(runtime.jobs.list_jobs()) == 1


def test_guard_is_detached_and_errors_are_redacted(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    def corrupt_copy(value):
        value["actor"] = "ceo-sol"
        value["execution_contract"]["requested_authorities"] = ["MERGE"]
    result = submit(runtime, tmp_path, guard=corrupt_copy)
    assert result["principal"]["seat"] == "coo"
    assert result["authority"]["requested"] == ["READ", "RESEARCH"]
    def denied(_):
        raise ValueError("private owner data must never escape")
    with pytest.raises(sink.CeoIntentError, match="principal admission refused") as exc:
        submit(runtime, tmp_path, bundle(tmp_path, operation_key="new-coo-effect"), guard=denied)
    assert "private owner" not in str(exc.value)
    assert len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize("field,value", [
    ("actor", "ceo-sol"), ("seat", "ceo"), ("seat", "chairman"),
    ("principal_binding_digest", "bad"), ("authority_generation_digest", "bad"),
    ("mission_authority_ref", ""), ("workstream", "WS:OTHER"),
    ("intent_id", "coo-not-a-digest"), ("client_ref", "secret-client"),
])
def test_changed_or_privileged_envelope_identity_refuses(tmp_path, field, value):
    runtime = Runtime.at(tmp_path / "runtime")
    candidate = bundle(tmp_path)
    candidate["envelope"][field] = value
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, candidate)
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("field,value", [
    ("attempt_limit", 3), ("attempt_limit", True), ("authority_level", "A7"),
    ("requested_authorities", ["READ", "MERGE"]),
    ("requested_authorities", ["READ"]), ("constraints", {}),
    ("branch", "codex/another-operation"), ("worktree", "/tmp/another-operation"),
    ("allowed_write_paths", ["control_plane/example.py"]),
    ("validation_commands", [["git", "diff", "--check"]]),
])
def test_principal_cannot_expand_or_redirect_worker_profile(tmp_path, field, value):
    runtime = Runtime.at(tmp_path / "runtime")
    candidate = bundle(tmp_path)
    candidate["envelope"]["execution_contract"][field] = value
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, candidate)
    assert runtime.jobs.list_jobs() == []


def test_bounded_code_profile_keeps_runtime_policy_and_zero_attempts(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    candidate = bundle(tmp_path, execution_profile="bounded_code_change",
        allowed_write_paths=["control_plane/example.py"],
        validation={"pytest_targets": ["tests/test_example.py"], "git_diff_check": True})
    receipt = submit(runtime, tmp_path, candidate)
    job = runtime.jobs.get_job(receipt["job_id"])
    assert job.requested_authorities == ["READ", "RUN_TESTS", "WRITE_BRANCH"]
    assert job.allowed_write_paths == ["control_plane/example.py"]
    assert job.attempt_count == 0 and receipt["dispatched"] is False


def test_concurrent_submission_uses_existing_event_uniqueness(tmp_path):
    runtimes = [Runtime.at(tmp_path / "runtime") for _ in range(2)]
    barrier = threading.Barrier(2)
    def worker(index):
        runtime = runtimes[index]
        create = runtime.jobs.create_job
        def synchronized_create(*args, **kwargs):
            # Synchronize creators before either holds the SQLite writer lock.
            barrier.wait(timeout=10)
            return create(*args, **kwargs)
        runtime.jobs.create_job = synchronized_create
        return submit(runtime, tmp_path)
    with ThreadPoolExecutor(2) as workers:
        receipts = list(workers.map(worker, range(2)))
    assert len({r["job_id"] for r in receipts}) == 1
    assert sorted(r["duplicate"] for r in receipts) == [False, True]
    assert len(Runtime.at(tmp_path / "runtime").jobs.list_jobs()) == 1


def test_changed_binding_conflicts_under_the_same_logical_operation(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    first = submit(runtime, tmp_path)
    changed = context(principal_binding_digest="3" * 64)
    with pytest.raises(sink.CeoIntentConflict):
        submit(runtime, tmp_path, bundle(tmp_path, ctx=changed), ctx=changed)
    assert sink.resolve_intent(runtime, first["intent_id"]) == first


def test_existing_unwired_sink_call_cannot_admit_a_principal(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError, match="principal admission"):
        sink.submit_intent(runtime, bundle(tmp_path)["envelope"],
                           workspace_root=tmp_path / "workspaces")
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("field,value", [
    ("seat", "ceo"), ("actor", "ceo-sol"),
    ("request_ref", "req-coo-" + "9" * 32),
    ("principal_binding_digest", None), ("client_ref", "unexpected"),
])
def test_durable_identity_drift_is_not_a_successful_read(tmp_path, field, value):
    runtime = Runtime.at(tmp_path / "runtime")
    accepted = submit(runtime, tmp_path)
    event = copy.deepcopy(runtime.store.find_event_by_command_id(
        sink.command_id_for(accepted["intent_id"])))
    event["payload"]["provenance"][field] = value
    with pytest.raises(sink.CeoIntentError):
        sink._receipt_from_event(runtime, event, intent_id=accepted["intent_id"],
                                 fingerprint=None)


def test_request_ref_must_be_the_exact_intent_preimage(tmp_path):
    candidate = bundle(tmp_path)
    candidate["request_ref"] = "req-coo-" + "9" * 32
    with pytest.raises(sink.CeoIntentError, match="request identity"):
        submit(Runtime.at(tmp_path / "runtime"), tmp_path, candidate)


def test_post_commit_response_loss_is_reconciled_without_resubmission(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    create = runtime.jobs.create_job
    def lose_response(*args, **kwargs):
        create(*args, **kwargs)
        raise RuntimeError("simulated response loss after commit")
    monkeypatch.setattr(runtime.jobs, "create_job", lose_response)
    with pytest.raises(RuntimeError, match="response loss"):
        submit(runtime, tmp_path)
    reader = Runtime.at(tmp_path / "runtime")
    result = sink.resolve_intent(reader, bundle(tmp_path)["intent_id"])
    assert result["accepted"] is True and result["dispatched"] is False
    assert len(reader.jobs.list_jobs()) == 1


def test_principal_guard_cannot_be_carried_inside_model_authored_envelope(tmp_path):
    candidate = bundle(tmp_path)
    candidate["envelope"]["principal_admission_guard"] = "allow"
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, candidate)
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("bad_context", [None, {}, dataclasses.asdict(context()),
    context(principal_binding_digest="5" * 64)])
def test_only_matching_typed_host_context_is_accepted(tmp_path, bad_context):
    runtime = Runtime.at(tmp_path / "runtime")
    candidate = bundle(tmp_path)
    with pytest.raises(sink.CeoIntentError):
        sink.submit_intent(runtime, candidate["envelope"],
            workspace_root=tmp_path / "workspaces", principal_context=bad_context,
            principal_request_ref=candidate["request_ref"], principal_admission_guard=allow)
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("returned", [True, False, 0, "", {}, []])
def test_guard_must_return_none_not_a_truthy_or_falsy_grant(tmp_path, returned):
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError, match="principal admission refused"):
        submit(runtime, tmp_path, guard=lambda _: returned)
    assert runtime.jobs.list_jobs() == []


def test_principal_guard_runs_after_sqlite_lock_wait_and_leaves_no_effect(tmp_path):
    from contextlib import contextmanager
    holder = Runtime.at(tmp_path / "runtime")
    writer = Runtime.at(tmp_path / "runtime")
    entered = threading.Event()
    current = [True]
    outcome = []
    original = writer.store.transaction
    @contextmanager
    def waiting_transaction():
        entered.set()
        with original() as connection:
            yield connection
    writer.store.transaction = waiting_transaction
    def guard(_):
        if not current[0]:
            raise ValueError("private role was relieved")
    def contender():
        try:
            submit(writer, tmp_path, guard=guard)
        except sink.CeoIntentError:
            outcome.append("refused")
        else:
            outcome.append("accepted")
    with holder.store.transaction():
        thread = threading.Thread(target=contender)
        thread.start()
        assert entered.wait(10)
        assert thread.is_alive()
        current[0] = False
    thread.join(10)
    assert not thread.is_alive()
    assert outcome == ["refused"]
    assert writer.jobs.list_jobs() == []
    assert writer.events.list_events() == []
    with pytest.raises(sink.CeoIntentError):
        sink.resolve_intent(writer, bundle(tmp_path)["intent_id"])


def test_principal_relief_during_insert_rolls_back_job_and_receipt(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    current = [True]
    create = runtime.jobs._create_job_in_transaction
    def insert_then_relieve(*args, **kwargs):
        job = create(*args, **kwargs)
        current[0] = False
        return job
    runtime.jobs._create_job_in_transaction = insert_then_relieve
    def guard(_):
        if not current[0]:
            raise ValueError("private owner diagnostic")
    with pytest.raises(sink.CeoIntentError) as error:
        submit(runtime, tmp_path, guard=guard)
    assert "private owner diagnostic" not in str(error.value)
    assert runtime.jobs.list_jobs() == []
    assert runtime.events.list_events() == []
    with pytest.raises(sink.CeoIntentError):
        sink.resolve_intent(runtime, bundle(tmp_path)["intent_id"])


def test_accepted_command_arriving_during_wait_precedes_revoked_guard(tmp_path):
    from contextlib import contextmanager
    probe = Runtime.at(tmp_path / "probe")
    captured = []
    create = probe.jobs._create_job_in_transaction
    def capture(connection, *, spec):
        captured.append(spec)
        return create(connection, spec=spec)
    probe.jobs._create_job_in_transaction = capture
    submit(probe, tmp_path)
    holder = Runtime.at(tmp_path / "runtime")
    writer = Runtime.at(tmp_path / "runtime")
    entered = threading.Event()
    current = [True]
    results = []
    original = writer.store.transaction
    @contextmanager
    def waiting_transaction():
        entered.set()
        with original() as connection:
            yield connection
    writer.store.transaction = waiting_transaction
    def guard(_):
        if not current[0]:
            raise ValueError("role relieved after original admission")
    def contender():
        try:
            results.append(submit(writer, tmp_path, guard=guard))
        except Exception as error:
            results.append(error)
    with holder.store.transaction() as connection:
        thread = threading.Thread(target=contender)
        thread.start()
        assert entered.wait(10)
        accepted = holder.jobs._create_job_in_transaction(connection, spec=captured[0])
        current[0] = False
    thread.join(10)
    assert not thread.is_alive()
    assert len(results) == 1 and isinstance(results[0], dict)
    assert results[0]["duplicate"] is True and results[0]["job_id"] == accepted.job_id
    assert len(writer.jobs.list_jobs()) == len(writer.events.list_events()) == 1


@pytest.mark.parametrize("async_function", [True, False])
def test_async_principal_guard_refuses_without_leaking_coroutine(tmp_path, async_function):
    import warnings
    coroutines = []
    async def asynchronous(_):
        return None
    def returning_coroutine(value):
        result = asynchronous(value)
        coroutines.append(result)
        return result
    runtime = Runtime.at(tmp_path / "runtime")
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(sink.CeoIntentError):
            submit(runtime, tmp_path, guard=asynchronous if async_function else returning_coroutine)
    assert all(item.cr_frame is None for item in coroutines)
    assert runtime.jobs.list_jobs() == runtime.events.list_events() == []


def test_public_intent_cannot_supply_internal_creation_guard(tmp_path):
    candidate = bundle(tmp_path)
    candidate["envelope"]["_principal_commit_guard"] = "caller-forged-ceo-role"
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, candidate)
    assert runtime.jobs.list_jobs() == runtime.events.list_events() == []
