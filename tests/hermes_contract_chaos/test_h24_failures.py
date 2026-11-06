"""Faults at original-effect, source, capacity, clock and publication seams."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import hashlib
import json
import os
import sqlite3

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_retry_safety import (
    RetrySafety, RetrySafetyDecision, RetrySafetyEvidence, classify_retry_safety,
)
from integrations.hermes_models.client import HermesModelClient, HttpResponse
from integrations.hermes_models.contract import PROVIDERS
from integrations.hermes_models.tests.support import env_for, ok_body, request
from integrations.session_bridge.schemas import BridgeError

from .fixtures import (
    FaultScript, ManualClock, Schedule, SECRET_SENTINEL, counts, event_digest,
    native_case, publication_case, selected_case,
)


def test_lost_modifying_return_is_unknown_and_original_is_reconciled(tmp_path, monkeypatch, chaos_seed):
    async def exercise():
        async with selected_case(tmp_path) as (service, supervisor, work, command, composition, received, finish):
            original = service.dispatch_selected_child
            submitted = []

            async def lose_return(**kwargs):
                result = await original(**kwargs)
                submitted.append(result["attempt_id"])
                raise ConnectionError(SECRET_SENTINEL)

            monkeypatch.setattr(service, "dispatch_selected_child", lose_return)
            before = counts(service.runtime)
            lost = await composition.submit_async(command)
            assert lost["state"] == "EFFECT_UNKNOWN" and lost["live_submit"] is None
            assert lost["command_id"] == command and lost["job_id"] == work.job_id
            assert SECRET_SENTINEL not in json.dumps(lost)
            for _ in Schedule(chaos_seed).order(range(4)):
                recovered = await composition.submit_async(command)
                assert recovered["state"] == "ACTIVE"
                assert recovered["attempt_id"] == submitted[0]
            assert len(submitted) == 1
            assert counts(service.runtime)[:2] == (before[0], before[1] + 1)
            finish.set()
    asyncio.run(exercise())


def test_unknown_native_return_retains_journal_without_job_or_attempt(native_case, chaos_seed):
    from tests.test_hermes_session_runtime import arguments, original_events

    async def exercise():
        s = native_case
        args = await arguments(s)
        before = counts(s.runtime)
        s.state.lose_submit = s.state.read_unavailable = True
        lost = await s.owner.send_hermes(s.principal, args)
        assert lost["commit_started"] is True and lost["native_status"] is None
        assert lost["answer"] is lost["admission"] is None
        assert s.state.writes == 1 and len(original_events(s, args)) == 2
        for _ in Schedule(chaos_seed).order(range(4)):
            same = await s.owner.send_hermes(s.principal, args)
            assert same["read_ref"] == lost["read_ref"] and same["answer"] is None
        assert s.state.writes == 1 and counts(s.runtime)[:2] == before[:2]
        s.state.read_unavailable = False
        reconciled = await s.owner.read_hermes(s.principal, lost["read_ref"])
        assert reconciled["native_status"] == "OBSERVED"
        assert reconciled["answer"] == "Actual original answer: 日本語 ✓"
        assert len(original_events(s, args)) == 2 and s.state.writes == 1
    asyncio.run(exercise())


def _runtime_job(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker("h24-worker", provider="codex", account_label="inert",
                                    worker_type="codex", quota_classes=["default"])
    job = runtime.jobs.create_job("H24 inert claim", command_id="h24:original-job")
    return runtime, job


@pytest.mark.parametrize("when", ["before_claim", "after_claim"])
def test_worker_stop_never_creates_a_replacement_attempt(tmp_path, when):
    runtime, job = _runtime_job(tmp_path)
    before = counts(runtime)
    lease = runtime.broker.claim(job.job_id) if when == "after_claim" else None
    runtime.workers.set_worker_status("h24-worker", "OFFLINE")
    if lease:
        with pytest.raises(StateConflict, match="not QUEUED"):
            runtime.broker.claim(job.job_id)
    else:
        assert runtime.broker.claim(job.job_id) is None
    current = runtime.jobs.get_job(job.job_id)
    assert current.attempt_count == int(when == "after_claim")
    assert counts(runtime)[:2] == (before[0], before[1] + int(when == "after_claim"))
    if lease is not None:
        assert current.current_attempt_id == lease.attempt.attempt_id
        assert current.status.value == "RUNNING"  # STOP availability is not completion proof.
        assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value == "CLAIMED"


@pytest.mark.parametrize("lost_return", [False, True])
def test_typed_stop_after_claim_has_one_original_effect(tmp_path, monkeypatch, lost_return):
    from control_plane.operator_harness_contract import (
        OperationId, OperationReceiptKind, ProcessLiveness, ProviderWriterState,
        operation_receipt_command_id,
    )
    from control_plane.operator_harness_orchestrator import OperatorEffectUnknown
    from tests.test_ohf_p1b_runtime_orchestrator import (
        FakeAdapter, _orchestrator, _profile, _runtime_lease,
    )

    runtime, job, lease = _runtime_lease(tmp_path)
    profile = _profile(lease)
    adapter = FakeAdapter(profile)
    _, orchestrator = _orchestrator(runtime, lease, adapter)
    session = orchestrator.start_attempt(attempt_id=lease.attempt.attempt_id,
        requested=profile, operation_id=OperationId("ohf-op:h24-start"))
    before = counts(runtime)[:2]
    operation = OperationId("ohf-op:h24-stop")
    original = adapter.graceful_stop

    def stop(generation, *, operation_id):
        observed = original(generation, operation_id=operation_id)
        if lost_return:
            raise ConnectionError(SECRET_SENTINEL)
        return observed

    monkeypatch.setattr(adapter, "graceful_stop", stop)
    if lost_return:
        with pytest.raises(OperatorEffectUnknown):
            orchestrator.graceful_stop(session, operation_id=operation)
    else:
        observed = orchestrator.graceful_stop(session, operation_id=operation)
        assert observed.process_liveness is ProcessLiveness.PROVEN_DEAD
        assert observed.provider_writer_state is ProviderWriterState.RELEASED
    frozen = counts(runtime), event_digest(runtime)
    # A fresh orchestrator has no local replay cache: the durable owner must
    # also refuse reissuing the exact modifying STOP operation.
    _, resumed = _orchestrator(runtime, lease, adapter)
    for owner in (orchestrator, resumed):
        with pytest.raises((OperatorEffectUnknown, StateConflict)):
            owner.graceful_stop(session, operation_id=operation)
    assert (counts(runtime), event_digest(runtime)) == frozen
    assert adapter.calls.count("start_session") == adapter.calls.count("graceful_stop") == 1
    assert counts(runtime)[:2] == before
    assert runtime.jobs.get_job(job.job_id).current_attempt_id == lease.attempt.attempt_id
    receipt = runtime.events.get_event_by_command_id(operation_receipt_command_id(
        operation, OperationReceiptKind.EFFECT_UNKNOWN if lost_return else OperationReceiptKind.APPLIED))
    assert receipt is not None and SECRET_SENTINEL not in json.dumps(receipt.payload)
    with runtime.store.read() as connection:
        generation = connection.execute(
            "SELECT ended_at_ms,executive_writer_held FROM process_generations WHERE process_generation_id=?",
            (session.generation.process_generation_id,),
        ).fetchone()
    assert generation[1] == int(lost_return)
    assert (generation[0] is None) is lost_return


@pytest.mark.parametrize("when", ["before_claim", "after_claim"])
def test_cancellation_before_or_after_claim_never_reclaims(tmp_path, when):
    runtime, job = _runtime_job(tmp_path)
    before = counts(runtime)
    lease = runtime.broker.claim(job.job_id) if when == "after_claim" else None
    exact = {} if lease is None else dict(expected_attempt_id=lease.attempt.attempt_id,
                                          expected_fence_generation=lease.attempt.fence_generation)
    cancelled = runtime.jobs.cancel_job(job.job_id, **exact)
    frozen = counts(runtime), event_digest(runtime)
    for _ in range(4):
        if lease:
            assert runtime.jobs.cancel_job(job.job_id, **exact).status == cancelled.status
        else:
            with pytest.raises(StateConflict, match="cannot cancel from CANCELLED"):
                runtime.jobs.cancel_job(job.job_id)
        with pytest.raises(StateConflict, match="not QUEUED"):
            runtime.broker.claim(job.job_id)
    assert (counts(runtime), event_digest(runtime)) == frozen
    assert cancelled.status.value == ("CANCEL_REQUESTED" if lease else "CANCELLED")
    assert counts(runtime)[:2] == (before[0], before[1] + int(lease is not None))
    if lease:
        assert cancelled.current_attempt_id == lease.attempt.attempt_id


def test_quota_exhaustion_after_candidate_projection_refuses_claim(tmp_path):
    runtime, job = _runtime_job(tmp_path)
    candidate = runtime.broker.select_worker(job)
    assert candidate.worker_id == "h24-worker"
    before = counts(runtime)
    runtime.workers.set_worker_status(candidate.worker_id, "RATE_LIMITED", quota_class="default")
    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.claim(job.job_id, worker_id=candidate.worker_id, quota_class="default") is None
    assert counts(runtime)[:2] == before[:2]
    assert runtime.jobs.get_job(job.job_id).current_attempt_id is None


@pytest.mark.parametrize("mutation", ["replacement", "aba"])
def test_original_source_identity_survives_no_byte_equivalent_replacement(native_case, mutation):
    from control_plane.executive_fabric_composition import FabricCompositionError
    from tests.test_hermes_session_runtime import arguments
    s = native_case
    args = asyncio.run(arguments(s))
    source = s.source
    original = source.path.read_bytes()
    before = counts(s.runtime)
    # Keep the original inode alive so allocation/reuse is not a timing oracle.
    with source.path.open("rb") as held:
        identity = os.fstat(held.fileno()).st_ino
        if mutation == "aba":
            intermediate = source.path.with_name("h24-intermediate")
            intermediate.write_bytes(original + b" ")
            intermediate.chmod(0o600)
            os.replace(intermediate, source.path)
        replacement = source.path.with_name("h24-replacement")
        replacement.write_bytes(original)
        replacement.chmod(0o600)
        os.replace(replacement, source.path)
        assert source.path.read_bytes() == original
        assert source.expected_sha256 == hashlib.sha256(original).hexdigest()
        assert source.path.stat().st_ino != identity
        with pytest.raises(FabricCompositionError):
            source.require_current()
        # Exercise the real public consumer too: an equivalent-byte file may
        # not cause a fresh native submission under the old source identity.
        with pytest.raises(BridgeError):
            asyncio.run(s.owner.send_hermes(s.principal, args))
    assert counts(s.runtime) == before and s.state.writes == 0


def test_owner_lost_during_original_capture_withholds_answer(native_case):
    from tests.test_hermes_session_runtime import arguments

    async def exercise():
        s = native_case
        args = await arguments(s)
        sent = await s.owner.send_hermes(s.principal, args)
        before = counts(s.runtime), event_digest(s.runtime)
        # The bound owner's guard disappears after bytes are captured but
        # before the public result is returned. This simulates owner loss;
        # it does not kill a host process or assert physical death.
        s.state.after_read = lambda: setattr(s.state, "read_allowed", False)
        with pytest.raises(BridgeError):
            await s.owner.read_hermes(s.principal, sent["read_ref"])
        assert (counts(s.runtime), event_digest(s.runtime)) == before
        assert s.state.writes == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["before_insert", "after_insert"])
@pytest.mark.parametrize("fault", ["authority_lost", "connection_lost"])
def test_capture_owner_or_connection_loss_rolls_back_claim_facts(tmp_path, monkeypatch, phase, fault):
    async def exercise():
        async with selected_case(tmp_path) as (service, supervisor, work, command, composition, received, finish):
            runtime = service.runtime
            before = counts(runtime), event_digest(runtime)
            original = runtime.attempts._claim_job_in_transaction
            inserted = []

            def lose_boundary():
                if fault == "authority_lost":
                    service._selected_child_fixture[1]["missions"][0]["enabled"] = False
                else:
                    raise sqlite3.OperationalError("injected H24 connection loss")

            def capture(*args, **kwargs):
                if phase == "before_insert":
                    lose_boundary()
                result = original(*args, **kwargs)
                inserted.append(result.attempt.attempt_id)
                if phase == "after_insert":
                    lose_boundary()
                return result

            monkeypatch.setattr(runtime.attempts, "_claim_job_in_transaction", capture)
            result = await composition.submit_async(command)
            assert result["state"] == "REFUSED" and result["live_submit"] is False
            assert result["command_id"] == command and result["attempt_id"] is None
            assert (counts(runtime), event_digest(runtime)) == before
            assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            assert all(runtime.attempts.get_attempt(attempt) is None for attempt in inserted)
            if phase == "after_insert":
                assert len(inserted) == 1  # A real inserted claim was rolled back.
            assert not service._dispatch_tasks and received == []
    asyncio.run(exercise())


def test_failed_dispatch_teardown_always_clears_global_composition(tmp_path):
    from integrations.hermes_delegate.executive import selected_child_composition

    async def fail():
        raise RuntimeError("injected H24 cleanup failure")

    async def exercise():
        with pytest.raises(RuntimeError, match="injected H24 cleanup failure"):
            async with selected_case(tmp_path) as values:
                service = values[0]
                service._dispatch_tasks["h24-failed-teardown"] = asyncio.create_task(fail())
        assert selected_child_composition() is None
    asyncio.run(exercise())


@pytest.mark.parametrize("effect", ["read_only", "side_effecting"])
@pytest.mark.parametrize("fault", ["disconnect", "503", "429", "401"])
def test_model_fault_fallback_is_readonly_and_secrets_stay_private(tmp_path, caplog, effect, fault):
    first = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
    second = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
    clock = ManualClock()
    response = OSError(SECRET_SENTINEL) if fault == "disconnect" else HttpResponse(
        int(fault), {"Retry-After": "999999"}, {"error": {"message": SECRET_SENTINEL}})

    def fail():
        clock.rewind_wall(3600)
        if isinstance(response, BaseException):
            raise response
        return response

    transport = FaultScript(fail, ok_body(second.served_model), clock=clock)
    meter = tmp_path / "meter.jsonl"
    client = HermesModelClient(transport=transport, meter_path=meter,
        environ=env_for(first.provider_id, second.provider_id, secret=SECRET_SENTINEL),
        monotonic=clock.monotonic, now=clock.now)
    result = client.complete(request("secretary", None, effect=effect, turn=f"h24-{effect}-{fault}"))
    allowed = effect == "read_only" and fault in {"disconnect", "503"}
    assert len(transport.calls) == len(result.attempts) == (2 if allowed else 1)
    assert len(transport.steps) == (0 if allowed else 1)
    assert result.ok is allowed
    assert not result.replayed and not result.capacity_claimed and not result.executive_admission
    if fault == "429":
        assert result.backoff_seconds == 900
    public = json.dumps(asdict(result)) + meter.read_text() + caplog.text
    assert SECRET_SENTINEL not in public
    assert all(row["wall_time_ms"] == pytest.approx(25, abs=0.1)
               for row in map(json.loads, meter.read_text().splitlines()))


@pytest.mark.parametrize("mutate", ["unknown", "live_writer", "stale_attempt", "modifying"])
def test_retry_classifier_never_turns_ambiguous_quota_into_replay(mutate):
    evidence = RetrySafetyEvidence(
        retry_safety=RetrySafety.SAFE_NON_MODIFYING_QUOTA_ROLLOVER,
        terminal_status="RATE_LIMITED", job_id="JOB-1", attempt_id="ATT-1", attempt_job_id="JOB-1",
        current_attempt_id="ATT-1", provenance_digest="a" * 64,
        retry_lineage_available=True, effect_unknown=False, writer_or_provider_generation_live=False,
        candidate_present=False, result_present=False, seal_present=False, effective_grant_non_modifying=True)
    assert classify_retry_safety(evidence) is RetrySafetyDecision.SAFE_REQUEUE
    changes = {"unknown": dict(effect_unknown=True), "live_writer": dict(writer_or_provider_generation_live=True),
               "stale_attempt": dict(current_attempt_id="ATT-2"), "modifying": dict(effective_grant_non_modifying=False)}
    unsafe = replace(evidence, **changes[mutate])
    assert classify_retry_safety(unsafe) is RetrySafetyDecision.NEEDS_RECONCILIATION
    assert unsafe.evidence_digest != evidence.evidence_digest


@pytest.mark.parametrize("phase", ["write_publication_receipt", "prove_control_config_bound"])
def test_interrupted_publish_recovers_same_transaction_and_exact_preimages(publication_case, monkeypatch, phase):
    from ops.executive_os import autonomy_control as owner
    from ops.executive_os import dialogue_wake_canary_control as canary
    from tests.test_dialogue_wake_canary_control import configure
    from tests.test_native_dialogue_publication import native_case as prepare, publish
    from tests.test_executive_autonomy_control import SHA

    s = publication_case
    proposal, control, worker = prepare(s, monkeypatch)
    original = getattr(s.host, phase)
    observed = []

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        observed.append(s.host._manifest()["transaction_id"])
        raise owner.TransactionEffectUnknown()

    monkeypatch.setattr(s.host, phase, interrupt)
    with pytest.raises(owner.TransactionEffectUnknown):
        publish(s, proposal)
    manifest = s.host._manifest()
    assert observed == [manifest["transaction_id"]]
    assert manifest["operation"] == "DIALOGUE_WAKE_CANARY_PUBLISH"
    assert owner.CONTROL_CONFIG.read_bytes() == control and owner.WORKER_CONFIG.read_bytes() == worker
    s.host._release_transaction_owner()  # Lose only the disposable fixture's lock.
    recovery = configure(canary.ProductionDialogueCanaryHost(), monkeypatch)
    monkeypatch.setattr(recovery, "reconcile_control_service", lambda *args: pytest.fail("recovery restarted a service"))
    assert recovery.recover_publication(SHA) == manifest["transaction_id"]
    assert owner.CONTROL_CONFIG.read_bytes() == control and owner.WORKER_CONFIG.read_bytes() == worker
    assert not s.marker.exists() and not canary.RECEIPT_PATH.exists()


def test_terminal_return_is_immutable_under_duplicate_and_late_callbacks(tmp_path):
    async def exercise():
        async with selected_case(tmp_path) as (service, supervisor, work, command, composition, received, finish):
            active = await composition.submit_async(command)
            finish.set()
            await asyncio.wait_for(asyncio.gather(*tuple(service._dispatch_tasks.values())), 5)
            terminal = await composition.status_async(command)
            before = counts(service.runtime), event_digest(service.runtime)
            assert terminal["state"] == "COMPLETED"
            assert len(received) == 1
            # Repeat the incumbent callback entry, including a foreign late
            # Attempt; no replacement callback tracker is introduced.
            await asyncio.gather(*(
                service._project_terminal_return(work.job_id, expected_attempt_id=attempt)
                for attempt in (active["attempt_id"], active["attempt_id"], "ATT-foreign")))
            after = await composition.submit_async(command)
            assert after == terminal
            assert len(received) == 1
            assert (counts(service.runtime), event_digest(service.runtime)) == before
            assert not service._terminal_return_flights and not service._dispatch_tasks
    asyncio.run(exercise())


def test_selected_child_bound_refuses_oversized_projection_before_claim(tmp_path):
    async def exercise():
        async with selected_case(tmp_path) as (service, supervisor, work, command, composition, received, finish):
            before = counts(service.runtime), event_digest(service.runtime)
            oversized = replace(composition, children=composition.children * 65)
            result = await oversized.submit_async(command)
            assert result["state"] == "REFUSED"
            assert result["reason"] == "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND"
            assert (counts(service.runtime), event_digest(service.runtime)) == before
            assert service._dispatch_tasks == {} and received == []
    asyncio.run(exercise())


def test_runner_cannot_reuse_old_success_after_invocation_loss(tmp_path, monkeypatch, capsys):
    from . import run_lane

    report = tmp_path / "run.json"
    report.write_text('{"exit_code":0,"pytest_summary":{"tests":999}}')
    report.with_suffix(".junit.xml").write_text(
        '<testsuites><testsuite tests="999" failures="0" errors="0" skipped="0"/></testsuites>')

    def fail_to_start(*args, **kwargs):
        raise OSError(SECRET_SENTINEL)

    monkeypatch.setattr(run_lane.sys, "argv", ["h24-lane", "--report", str(report)])
    monkeypatch.setattr(run_lane.subprocess, "run", fail_to_start)
    assert run_lane.main() == 127
    receipt = json.loads(report.read_text())
    assert receipt["exit_code"] == 127 and receipt["pytest_summary"] == {}
    assert receipt["invocation_error"] == "OSError"
    assert not report.with_suffix(".junit.xml").exists()
    assert SECRET_SENTINEL not in report.read_text() + capsys.readouterr().out
