"""Original T3 factory -> retained native observation and recovery evidence.

The MCP fixture is the native wire boundary. Runtime, claim, port, adapter,
provider-only projection and original recovery code are real. The fixture
records an existing execution through the raw adapter; it grants no native
scope capability. Governed launch and terminal acceptance remain fenced.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_supervisor import SupervisorError
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from control_plane.t3_execution_adapter import (
    SQLiteT3AdapterStateStore, T3ExecutionAdapterError, t3_expected_launch_thread_id,
)
from control_plane.t3_native_composition import (
    T3NativeCollectionReceipt, T3NativeCompositionError,
    compose_t3_native_adapter, compose_t3_native_supervisor_owners,
    qualify_native_collection,
)
from control_plane.worker_execution_contract import WorkerRunStatus
from tests.test_executive_claim_job_placement_authority import (
    QUOTA, REVISION, Clock, _observations, _request,
)
from tests.test_t3_native_composition import (
    _T3_WORKER_ID, _claim_t3_route, _primary_owner, _session_token,
    _record_original_native_attempt,
)
from tests.test_t3_execution_adapter import FakeInspector


class NativeWire:
    """Exact native thread/run/item owner, with a server-owned chunk cursor."""

    def __init__(self):
        self.calls = []
        self.thread = None
        self.run = "native-original-run"
        self.output = None
        self.text = None
        self.waits = 0
        self.running_waits = 1
        self.status = "completed"
        self.page_mutation = None
        self.chunk_mutation = None
        self.wait_mutation = None
        self.project = "native-project"

    def call_tool(self, tool, arguments):
        self.calls.append((tool, dict(arguments)))
        if tool == "t3_thread_launch":
            assert self.thread is None, "no second native submission"
            self.thread = t3_expected_launch_thread_id(
                "client:sess-supervisor", arguments["clientRequestId"])
            message = arguments["message"]
            packet = json.loads(message[message.index("{"):])
            schema = packet["result_schema"]["properties"]
            self.output = {
                "schema_version": schema["schema_version"]["const"],
                "job_id": schema["job_id"]["const"],
                "run_id": schema["run_id"]["const"],
                "worker_id": schema["worker_id"]["const"],
                "status": "COMPLETED", "summary": "Original native result " + "x" * 4600,
                "completed_steps": ["Read the admitted evidence"],
                "current_state": "Complete", "artifacts": [],
                "next_actions": [], "errors": [], "validations": [],
            }
            self.text = json.dumps(self.output, ensure_ascii=False)
            return {"threadId": self.thread, "runId": self.run,
                    "projectId": self.project, "status": "running"}
        assert arguments["threadId"] == self.thread
        if tool == "t3_thread_wait":
            assert arguments["runId"] == self.run
            assert arguments["untilDelegatedWorkSettled"] is False
            assert 1 <= arguments["timeoutMs"] <= 30_000
            self.waits += 1
            status = "running" if self.waits <= self.running_waits else self.status
            value = {"threadId": self.thread, "runId": self.run,
                     "status": status, "timedOut": status == "running"}
            if self.wait_mutation:
                self.wait_mutation(value)
            return value
        if tool == "t3_thread_read":
            chunk = "itemId" in arguments
            if chunk:
                assert arguments["itemId"] == "original-final"
                assert arguments["textOffset"] == 2111
            item = {
                "position": 7, "itemId": "original-final", "runId": self.run,
                "sourceThreadId": self.thread, "type": "assistant_message",
                "updatedAt": "2026-11-09T12:00:00Z",
                "text": self.text[2111:] if chunk else self.text[:2111],
                "textTruncated": not chunk,
                "nextTextOffset": None if chunk else 2111,
            }
            value = {
                "thread": {"threadId": self.thread, "projectId": self.project},
                "recentRuns": [{"runId": self.run, "status": self.status}],
                "items": [item], "hasMore": False, "nextPosition": 7,
            }
            mutation = self.chunk_mutation if chunk else self.page_mutation
            if mutation:
                mutation(value)
            return value
        if tool == "t3_thread_interrupt":
            assert arguments["runId"] == self.run
            self.status = "interrupted"
            return {"threadId": self.thread, "runId": self.run,
                    "status": "interrupt_requested"}
        raise AssertionError(tool)


def _case(tmp_path, *, scope=None, project=True):
    runtime = Runtime.at(tmp_path, clock=Clock(), lease_seconds=60)
    runtime.workers.register_worker(
        _T3_WORKER_ID, provider="t3", account_label="mcp-session",
        worker_type="t3-native", capabilities=["code"],
        quota_classes={"default": {"capabilities": ["code"],
                                   "metadata": {"adapter_id": "t3-native"}}},
        metadata={"host_id": "ubuntu0"})
    workspace = tmp_path / "workspaces" / "original-checkout"
    workspace.mkdir(mode=0o700, parents=True)
    placement = {
        "child_execution_request": _request("native-terminal-child").to_dict(),
        "effective_complexity": "C1_ROUTINE_BOUNDED", "registry_revision": REVISION,
        "route": {"provider_ref": "t3", "pool_ref": "glm", "adapter_id": "t3-native"},
        "shared_quota_resource_refs": [QUOTA], "root_concurrency_limit": 32,
    }
    values = {"worktree": str(workspace.resolve()),
              "requested_authorities": ["READ", "RESEARCH"],
              "constraints": {"child_placement": placement}, "attempt_limit": 3}
    values.update(scope or {})
    job = runtime.jobs.create_job("Return an exact bounded native answer", **values)
    primary = _primary_owner(runtime, tmp_path)
    token = tmp_path / "t3-token"
    token.write_text(_session_token("sess-supervisor"), encoding="utf-8")
    wire = NativeWire()
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), token_file=token,
        transport_factory=lambda _url, _token: wire,
        launch_arguments={"projectId": wire.project} if project else None,
        state_store=SQLiteT3AdapterStateStore(tmp_path / "native.sqlite3"), environ={})
    owners = compose_t3_native_supervisor_owners(
        primary, composition, runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"))
    mixed = MixedExecutionOwnerSupervisor(primary, {"primary": primary, **owners})
    lease = _claim_t3_route(runtime, job.job_id, _observations())
    return runtime, job, workspace, wire, composition, mixed, lease


async def _original_attempt(case):
    _runtime, job, _workspace, _wire, _composition, mixed, lease = case
    return await _record_original_native_attempt(mixed, job.job_id, lease)


def test_factory_retains_full_original_native_observation_without_acceptance(tmp_path):
    case = _case(tmp_path)
    runtime, job, workspace, wire, composition, mixed, lease = case
    async def run():
        active = await _original_attempt(case)
        owner = mixed._select(lease.attempt)
        receipt = await owner.adapter.collect_result(active.process_ref)
        assert qualify_native_collection(owner, active, receipt) == receipt.native_terminal
        return receipt, owner._persist_collection(active, receipt)

    receipt, collection_path = asyncio.run(run())
    attempt = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    assert attempt.status is AttemptStatus.RUNNING
    assert attempt.pid is attempt.pgid is attempt.exit_code is None
    assert len(receipt.result.structured_output["summary"]) > 4000
    assert wire.waits == 0
    launch = [args for tool, args in wire.calls if tool == "t3_thread_launch"]
    assert len(launch) == 1
    assert launch[0]["workspaceStrategy"] == {
        "type": "existing_worktree", "worktreePath": str(workspace.resolve())}
    assert launch[0]["projectId"] == wire.project
    assert len([1 for tool, args in wire.calls if tool == "t3_thread_read" and "itemId" in args]) == 1
    ledger = composition.adapter.result_ledger_entry(lease.attempt.attempt_id)
    assert ledger.result_ref.endswith("/run/native-original-run/item/original-final")
    assert receipt.native_terminal.result_ref == ledger.result_ref
    assert receipt.result_sha256 == hashlib.sha256(ledger.result_ref.encode()).hexdigest()
    retained = json.loads(Path(collection_path).read_text())
    assert retained["result"]["structured_output"] == wire.output
    assert retained["native_text"] == wire.text
    assert retained["native_terminal"]["native_run_id"] == wire.run
    assert not mixed._select(lease.attempt)._terminal_assignment_receipt_path(
        lease.attempt.attempt_id).exists()


@pytest.mark.parametrize("corrupt", ["source", "run", "project", "revision", "partial", "oversize", "json", "duplicate", "artifacts", "validations"])
def test_native_observation_refuses_unqualified_original_answer(tmp_path, corrupt):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, composition, mixed, lease = case

    async def run():
        active = await _original_attempt(case)
        if corrupt == "source":
            wire.page_mutation = lambda v: v["items"][0].update(sourceThreadId="foreign")
        elif corrupt == "run":
            wire.chunk_mutation = lambda v: v["items"][0].update(runId="later-run")
        elif corrupt == "project":
            wire.chunk_mutation = lambda v: v["thread"].update(projectId="foreign")
        elif corrupt == "revision":
            wire.chunk_mutation = lambda v: v["items"][0].update(updatedAt="changed")
        elif corrupt == "partial":
            wire.chunk_mutation = lambda v: v["items"][0].update(textTruncated=True, nextTextOffset=None)
        elif corrupt == "oversize":
            wire.text = "x" * 32_769
        elif corrupt == "json":
            wire.text = "A native answer without the admitted result envelope"
        elif corrupt == "duplicate":
            wire.text = wire.text[:-1] + ',"status":"COMPLETED"}'
        elif corrupt == "artifacts":
            wire.output["artifacts"] = [{"path": "unattested.txt"}]
            wire.text = json.dumps(wire.output)
        elif corrupt == "validations":
            wire.output["validations"] = [{"argv": ["true"], "exit_code": 0}]
            wire.text = json.dumps(wire.output)
        with pytest.raises((T3ExecutionAdapterError, T3NativeCompositionError)):
            await mixed._select(lease.attempt).adapter.collect_result(active.process_ref)

    asyncio.run(run())
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).exit_code is None
    assert len([1 for tool, _args in wire.calls if tool == "t3_thread_launch"]) == 1


@pytest.mark.parametrize("scope", [
    {"allowed_write_paths": ["result.txt"],
     "requested_authorities": ["READ", "RESEARCH", "WRITE_BRANCH"]},
    {"validation_commands": [["/usr/bin/true"]],
     "requested_authorities": ["READ", "RESEARCH", "RUN_TESTS"]},
])
def test_native_observation_does_not_invent_workspace_or_validation_proofs(tmp_path, scope):
    case = _case(tmp_path, scope=scope)
    runtime, job, _workspace, wire, _composition, mixed, lease = case

    async def run():
        active = await _original_attempt(case)
        with pytest.raises(T3NativeCompositionError, match="evidence is unavailable"):
            await mixed._select(lease.attempt).adapter.collect_result(active.process_ref)

    asyncio.run(run())
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.RUNNING
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).exit_code is None


def test_native_launch_does_not_fall_back_to_project_root(tmp_path):
    case = _case(tmp_path, project=False)
    with pytest.raises((T3ExecutionAdapterError, SupervisorError)):
        asyncio.run(_original_attempt(case))
    assert case[3].calls == []


def test_wait_refuses_later_native_run(tmp_path):
    case = _case(tmp_path)
    wire, mixed = case[3], case[5]

    async def run():
        active = await _original_attempt(case)
        wire.wait_mutation = lambda v: v.update(runId="replacement")
        with pytest.raises(T3ExecutionAdapterError):
            await mixed._select(case[6].attempt).adapter.wait_status(
                active.process_ref, timeout_ms=1000)

    asyncio.run(run())
    assert all(tool != "t3_thread_read" for tool, _ in wire.calls)


def test_native_terminal_rejects_forged_or_untyped_collection(tmp_path):
    case = _case(tmp_path)
    wire, mixed = case[3], case[5]

    async def run():
        active = await _original_attempt(case)
        owner = mixed._select(case[6].attempt)
        receipt = await owner.adapter.collect_result(active.process_ref)
        assert type(receipt) is T3NativeCollectionReceipt
        forged = dataclasses.replace(receipt, native_terminal=dataclasses.replace(
            receipt.native_terminal, native_run_id="foreign"))
        with pytest.raises(T3NativeCompositionError, match="differs"):
            qualify_native_collection(owner, active, forged)
        from control_plane.worker_execution_contract import CollectionReceipt
        untyped = CollectionReceipt(
            process_ref=receipt.process_ref, result=receipt.result,
            stdout_sha256=receipt.stdout_sha256, stderr_sha256=receipt.stderr_sha256,
            result_sha256=receipt.result_sha256)
        with pytest.raises(T3NativeCompositionError, match="typed evidence"):
            qualify_native_collection(owner, active, untyped)

    asyncio.run(run())


def test_native_cold_restart_observes_original_but_cannot_accept_it(tmp_path):
    case = _case(tmp_path)
    original = asyncio.run(_original_attempt(case))
    wire = case[3]
    runtime = Runtime.at(tmp_path, clock=Clock(), lease_seconds=60)
    primary = _primary_owner(runtime, tmp_path)
    composition = compose_t3_native_adapter(
        runtime, inspector=FakeInspector(), token_file=tmp_path / "t3-token",
        transport_factory=lambda _url, _token: wire,
        launch_arguments={"projectId": wire.project},
        state_store=SQLiteT3AdapterStateStore(tmp_path / "native.sqlite3"), environ={})
    owners = compose_t3_native_supervisor_owners(
        primary, composition, runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"))
    mixed = MixedExecutionOwnerSupervisor(primary, {"primary": primary, **owners})
    receipts = mixed.reconcile_restart()
    assert [r.status.value for r in receipts] == ["TERMINAL_RECOVERED"]
    recovered, = mixed.take_recovered_runs()
    assert recovered.process_ref == original.process_ref
    owner = mixed._select(recovered.lease.attempt)
    observed = asyncio.run(owner.adapter.collect_result(recovered.process_ref))
    assert observed.native_terminal.native_run_id == wire.run
    assert observed.native_text == wire.text
    before = list(wire.calls)
    before_status = runtime.jobs.get_job(case[1].job_id).status
    assert before_status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
    with pytest.raises(T3NativeCompositionError, match="scope.*quiescence"):
        asyncio.run(mixed.finish_job(recovered))
    assert wire.calls == before
    assert runtime.jobs.get_job(case[1].job_id).status is before_status
    assert runtime.attempts.get_attempt(case[6].attempt.attempt_id).exit_code is None
    assert len([1 for tool, _ in wire.calls if tool == "t3_thread_launch"]) == 1


def test_native_cancel_observes_exact_run_without_claiming_executive_quiescence(tmp_path):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, _composition, mixed, lease = case

    async def run():
        active = await _original_attempt(case)
        runtime.jobs.cancel_job(job.job_id,
            expected_attempt_id=lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation)
        owner = mixed._select(lease.attempt)
        await owner.adapter.cancel(active.process_ref, "original durable cancellation")
        assert await owner.adapter.wait_status(active.process_ref, timeout_ms=1000) is WorkerRunStatus.CANCELLING
        assert await owner.adapter.wait_status(active.process_ref, timeout_ms=1000) is WorkerRunStatus.CANCELLED
        return await owner.adapter.collect_result(active.process_ref)

    observed = asyncio.run(run())
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.CANCEL_REQUESTED
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).exit_code is None
    assert observed.native_terminal.native_status == "interrupted"
    assert case[4].adapter.cancel_report(lease.attempt.attempt_id).settled is True
    assert len([1 for tool, _ in wire.calls if tool == "t3_thread_interrupt"]) == 1


def test_native_observation_settles_original_unknown_cancel_without_resending(tmp_path):
    case = _case(tmp_path)
    runtime, job, _workspace, wire, _composition, mixed, lease = case

    async def run():
        active = await _original_attempt(case)
        runtime.jobs.cancel_job(job.job_id,
            expected_attempt_id=lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation)
        owner = mixed._select(lease.attempt)
        original = wire.call_tool

        def lost_reply(tool, arguments):
            result = original(tool, arguments)
            if tool == "t3_thread_interrupt":
                raise OSError("lost interrupt reply after original effect")
            return result

        port = case[4].adapter._port
        port._call_tool = lost_reply
        with pytest.raises(T3ExecutionAdapterError, match="outcome unknown"):
            await owner.adapter.cancel(active.process_ref, "original durable cancellation")
        port._call_tool = original
        assert await owner.adapter.wait_status(active.process_ref, timeout_ms=1000) is WorkerRunStatus.CANCELLING
        assert await owner.adapter.wait_status(active.process_ref, timeout_ms=1000) is WorkerRunStatus.CANCELLED
        return await owner.adapter.collect_result(active.process_ref)

    observed = asyncio.run(run())
    assert observed.native_terminal.native_status == "interrupted"
    assert runtime.jobs.get_job(job.job_id).status is JobStatus.CANCEL_REQUESTED
    assert case[4].adapter.cancel_report(lease.attempt.attempt_id).settled is True
    assert len([1 for tool, _ in wire.calls if tool == "t3_thread_interrupt"]) == 1
