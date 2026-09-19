"""Canonical remote-broker restart survivability discriminators."""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import threading
from pathlib import Path

import pytest

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ReconcileStatus,
    RESULT_SCHEMA_VERSION,
)
from control_plane.executive_worker_broker import (
    RemoteBrokerError,
    RemoteCodexWorkerAdapter,
    RemoteWorkerProcessController,
    WorkerBrokerClient,
)
from test_executive_worker_broker import FakeAdapter, _fixture, _socket_path


class RestartCompletionAdapter(FakeAdapter):
    """Worker-local fixture that records exact provider-side invocations."""

    def __init__(self, provider_home: Path) -> None:
        super().__init__()
        self.provider_home = provider_home
        self.start_calls = 0
        self.collect_calls = 0
        self.block_validation = False
        self.validation_entered = asyncio.Event()
        self.validation_release = asyncio.Event()

    async def start(self, spec):
        self.start_calls += 1
        return await super().start(spec)

    def launch_attestation(self, ref):
        assert self.spec is not None
        return {
            "schema_version": "mastermind.executive_launch_attestation/v1",
            "created_at": ref.started_at,
            "executable_path": ref.binary.real_path,
            "binary": dataclasses.asdict(ref.binary),
            "rendered_argv": [ref.binary.real_path, "exec", "--json", "-"],
            "environment_keys": ["CODEX_HOME", "HOME", "PATH"],
            "permission_profile_sha256": "c" * 64,
            "prompt_sha256": hashlib.sha256(
                self.spec.prompt.encode("utf-8")
            ).hexdigest(),
            "expected_base_sha": self.spec.expected_base_sha,
            "observed_base_sha": ref.base_sha,
            "workspace_identity": {"path": str(self.spec.workspace_path)},
            "worker_identity": {
                "requested_user": self.spec.worker_user,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
            },
            "provider_home_identity": {"path": str(self.provider_home)},
            "secret_canary_verdict": {
                "schema_version": "mastermind.executive_secret_canary/v1",
                "passed": True,
            },
            "launch_nonce": ref.launch_nonce,
            "process_identity": {
                "pid": ref.pid,
                "pgid": ref.pgid,
                "session_id": ref.session_id,
                "start_identity": ref.process_start_identity,
                "boot_id": ref.boot_session_id,
                "effective_uid": ref.effective_uid,
                "effective_gid": ref.effective_gid,
                "real_uid": ref.real_uid,
                "real_gid": ref.real_gid,
            },
        }

    def _collection(self):
        receipt = super()._collection()
        assert self.spec is not None
        output = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "job_id": self.spec.job_id,
            "run_id": self.spec.run_id,
            "worker_id": self.spec.worker_id,
            "status": "COMPLETED",
            "summary": "original broker-owned execution completed",
            "completed_steps": [
                "survived control supervisor restart",
                "returned one durable result",
            ],
            "current_state": "done",
            "artifacts": [],
            "next_actions": [],
            "errors": [],
            "validations": [],
        }
        result = dataclasses.replace(
            receipt.result,
            structured_output=output,
            git_manifest={
                "base_sha": self.spec.expected_base_sha,
                "head_sha": self.spec.expected_base_sha,
                "status_sha256": hashlib.sha256(b"").hexdigest(),
                "changed_paths": [],
            },
        )
        return dataclasses.replace(receipt, result=result)

    async def collect_result(self, ref):
        self.collect_calls += 1
        return await super().collect_result(ref)

    async def run_validation_argv(
        self, spec, argv, *, timeout_seconds=300.0
    ):
        if self.block_validation:
            self.validation_entered.set()
            await self.validation_release.wait()
        return await super().run_validation_argv(
            spec,
            argv,
            timeout_seconds=timeout_seconds,
        )


def _canary() -> dict:
    return {
        "schema_version": "mastermind.executive_secret_canary/v1",
        "passed": True,
        "checks": {
            "control_service_environment": "DENIED",
            "administrative_checkout": "DENIED",
            "executive_database": "DENIED",
            "other_worker_home": "DENIED",
            "forbidden_production_path": "DENIED",
        },
        "receipt_sha256": "a" * 64,
        "control_environment_probe_sha256": "b" * 64,
        "observed_at": "2026-09-19T00:00:00Z",
        "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
    }


def _runtime_and_job(tmp_path: Path, broker):
    runtime_root = tmp_path / "runtime-state"
    runtime = Runtime.at(runtime_root, lease_seconds=30)
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="dedicated-worker-account",
        worker_type="codex-cli",
        capabilities=["tests"],
        quota_classes={
            "codex-native": {
                "capabilities": ["tests"],
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "standard",
            }
        },
    )
    workspace = broker.policy.workspace_root / "restart-job"
    workspace.mkdir(mode=0o700)
    job = runtime.jobs.create_job(
        "Prove one broker-owned worker survives an Executive restart",
        worktree=str(workspace.resolve()),
        requested_authorities=["READ", "RUN_TESTS"],
        allowed_write_paths=[],
        validation_commands=[["/usr/bin/true"]],
        constraints={
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "effort": "xhigh",
            "cost_class": "standard",
            "base_sha": "b" * 40,
            "eligible_quota_classes": ["codex-native"],
            "required_capabilities": ["tests"],
        },
        attempt_limit=1,
    )
    return runtime_root, runtime, job


def _supervisor_for(
    owned_runtime: Runtime,
    broker,
    client: WorkerBrokerClient,
    tmp_path: Path,
    *,
    instance_id: str,
) -> ExecutiveSupervisor:
    def validations(spec):
        persisted = owned_runtime.jobs.get_job(spec.job_id)
        assert persisted is not None
        return tuple(tuple(command) for command in persisted.validation_commands)

    remote = RemoteCodexWorkerAdapter(
        client,
        validation_commands_for_spec=validations,
    )
    return ExecutiveSupervisor(
        owned_runtime,
        remote,
        runs_root=broker.policy.run_root,
        isolation_roots=(
            broker.policy.workspace_root,
            broker.policy.run_root,
        ),
        receipts_root=tmp_path / "receipts",
        worker_user=broker.policy.worker_user,
        worker_uid=broker.policy.worker_uid,
        worker_gid=broker.policy.worker_gid,
        shared_run_gid=broker.policy.worker_gid,
        secret_canary_verdict=_canary(),
        require_complete_launch_attestation=True,
        heartbeat_interval_seconds=0.01,
        process_controller=RemoteWorkerProcessController(client),
        instance_id=instance_id,
    )


async def _serve_fixture(tmp_path: Path):
    broker, _fixture_adapter, sweeper, peer, _fixture_spec = _fixture(tmp_path)
    adapter = RestartCompletionAdapter(broker.policy.provider_home)
    broker.adapter = adapter
    broker.startup_sweep = sweeper.sweep("broker_startup")
    broker.last_sweep = broker.startup_sweep
    socket_path = _socket_path()
    server = await asyncio.start_unix_server(
        broker.handle_connection,
        path=str(socket_path),
        limit=1024 * 1024,
    )
    broker.peer_resolver = lambda _socket: peer
    client = WorkerBrokerClient(socket_path, timeout_seconds=10.0)
    return broker, adapter, server, socket_path, client


async def _close_fixture(broker, adapter, server, socket_path: Path) -> None:
    adapter.finished.set()
    await broker.shutdown()
    server.close()
    await server.wait_closed()
    socket_path.unlink(missing_ok=True)


def test_remote_supervisor_restart_terminalizes_same_broker_owned_attempt(
    tmp_path: Path,
) -> None:
    """A live broker-owned execution survives one control-supervisor restart."""

    async def scenario() -> None:
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 0

            # Only the Executive/control process dies. The persistent broker
            # remains the worker's parent and retains truthful exit status.
            del active
            del first

            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.LIVE_RECOVERED
            ]
            repeated = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in repeated] == [
                ReconcileStatus.ALREADY_RECOVERED
            ]

            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1
            assert recovered[0].lease.attempt.attempt_id == attempt_id
            assert restarted.take_recovered_runs() == ()
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 0

            adapter.finished.set()
            terminal = await restarted.finish_job(recovered[0])

            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert terminal.attempt.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
            assert broker._active_run_id is None
            assert Path(terminal.collection_receipt_path).is_file()
            assert Path(terminal.validation_receipt_path or "").is_file()
            assert Path(
                terminal.assignment_seal_receipt_path or ""
            ).is_file()
        finally:
            await _close_fixture(broker, adapter, server, socket_path)

    asyncio.run(scenario())


def test_restart_replays_broker_completed_collection_and_validation_once(
    tmp_path: Path,
) -> None:
    """Crash after broker effects reuses receipts rather than repeating effects."""

    async def scenario() -> None:
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-post-effect-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            adapter.finished.set()
            collected = await first.adapter.collect_result(active.process_ref)
            validation = await first.adapter.run_validation_argv(
                active.launch_spec,
                ["/usr/bin/true"],
            )
            assert collected.result.exit_code == 0
            assert validation.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            with pytest.raises(
                RemoteBrokerError,
                match="validation replay timeout differs",
            ):
                await first.adapter.run_validation_argv(
                    active.launch_spec,
                    ["/usr/bin/true"],
                    timeout_seconds=301.0,
                )
            assert adapter.validation_calls == [("/usr/bin/true",)]
            persisted = runtime.attempts.get_attempt(attempt_id)
            assert persisted is not None
            assert persisted.status is AttemptStatus.CHECKPOINTED
            assert persisted.exit_code is None

            # The worker-side effects are complete, but the controller has not
            # persisted collection, validation or a terminal Runtime mutation.
            del active
            del first

            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-post-effect-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.TERMINAL_RECOVERED
            ]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1

            terminal = await restarted.finish_job(recovered[0])

            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert terminal.attempt.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
        finally:
            await _close_fixture(broker, adapter, server, socket_path)

    asyncio.run(scenario())


def test_restart_joins_inflight_broker_collection_without_second_effect(
    tmp_path: Path,
) -> None:
    """A lost collect caller does not cause a second provider collection."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unhandled: list[dict] = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(
            lambda _loop, context: unhandled.append(dict(context))
        )
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        pending: asyncio.Task | None = None
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-inflight-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            pending = asyncio.create_task(
                first.adapter.collect_result(active.process_ref)
            )
            await adapter.collect_started.wait()
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending

            # The provider-side collect is still owned by the persistent broker;
            # only the control-side caller disappeared.
            del active
            del first
            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-inflight-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.LIVE_RECOVERED
            ]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1

            finisher = asyncio.create_task(
                restarted.finish_job(recovered[0])
            )
            await asyncio.sleep(0.05)
            adapter.finished.set()
            terminal = await finisher

            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
        finally:
            adapter.finished.set()
            if pending is not None and not pending.done():
                pending.cancel()
            await asyncio.sleep(0)
            await _close_fixture(broker, adapter, server, socket_path)
            await asyncio.sleep(0.05)
            loop.set_exception_handler(prior_handler)
        assert unhandled == []

    asyncio.run(scenario())


def test_restart_joins_inflight_validation_without_second_effect(
    tmp_path: Path,
) -> None:
    """A lost validation caller rejoins the exact broker-owned validation."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unhandled: list[dict] = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(
            lambda _loop, context: unhandled.append(dict(context))
        )
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        pending: asyncio.Task | None = None
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-validation-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            adapter.finished.set()
            collected = await first.adapter.collect_result(active.process_ref)
            assert collected.result.exit_code == 0
            adapter.block_validation = True
            pending = asyncio.create_task(
                first.adapter.run_validation_argv(
                    active.launch_spec,
                    ["/usr/bin/true"],
                )
            )
            await adapter.validation_entered.wait()
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending

            del active
            del first
            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-validation-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.TERMINAL_RECOVERED
            ]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1

            finisher = asyncio.create_task(
                restarted.finish_job(recovered[0])
            )
            await asyncio.sleep(0.05)
            adapter.validation_release.set()
            terminal = await finisher

            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert terminal.attempt.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
        finally:
            adapter.finished.set()
            adapter.validation_release.set()
            if pending is not None and not pending.done():
                pending.cancel()
            await asyncio.sleep(0)
            await _close_fixture(broker, adapter, server, socket_path)
            await asyncio.sleep(0.05)
            loop.set_exception_handler(prior_handler)
        assert unhandled == []

    asyncio.run(scenario())


def test_terminal_owned_legacy_attempt_without_binding_is_quarantined(
    tmp_path: Path,
) -> None:
    """Terminal broker ownership alone cannot invent an adoption contract."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unhandled: list[dict] = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(
            lambda _loop, context: unhandled.append(dict(context))
        )
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        pending: asyncio.Task | None = None
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-legacy-terminal-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            adapter.finished.set()
            collected = await first.adapter.collect_result(active.process_ref)
            assert collected.result.exit_code == 0
            adapter.block_validation = True
            pending = asyncio.create_task(
                first.adapter.run_validation_argv(
                    active.launch_spec,
                    ["/usr/bin/true"],
                )
            )
            await adapter.validation_entered.wait()
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending

            # Simulate a pre-recovery-contract persisted Attempt without
            # changing its exact process identity or the broker-owned effect.
            with runtime.store.transaction() as connection:
                row = connection.execute(
                    "SELECT launch_metadata_json FROM attempts "
                    "WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                assert row is not None
                metadata = json.loads(row[0])
                assert metadata.pop("worker_recovery_binding", None) is not None
                connection.execute(
                    "UPDATE attempts SET launch_metadata_json=? "
                    "WHERE attempt_id=?",
                    (
                        json.dumps(
                            metadata,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        attempt_id,
                    ),
                )

            del active
            del first
            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-legacy-terminal-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )

            assert [item.status for item in outcomes] == [
                ReconcileStatus.LIVE_QUARANTINED
            ]
            assert outcomes[0].process_was_live is False
            assert "no durable recovery binding" in (outcomes[0].error or "")
            assert restarted.take_recovered_runs() == ()
            persisted = reopened.attempts.get_attempt(attempt_id)
            assert persisted is not None
            assert persisted.status is AttemptStatus.CHECKPOINTED
            assert persisted.fence_generation == original_fence
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == []
        finally:
            adapter.finished.set()
            adapter.validation_release.set()
            if pending is not None and not pending.done():
                pending.cancel()
            await asyncio.sleep(0)
            await _close_fixture(broker, adapter, server, socket_path)
            await asyncio.sleep(0.05)
            loop.set_exception_handler(prior_handler)
        assert unhandled == []

    asyncio.run(scenario())


def test_restart_joins_collection_after_receipt_before_terminal_sweep(
    tmp_path: Path,
) -> None:
    """A terminal receipt with an in-flight sweep remains exactly owned."""

    class BlockingTerminalSweep:
        def __init__(self, delegate) -> None:
            self.delegate = delegate
            self.entered = threading.Event()
            self.release = threading.Event()

        def sweep(self, reason: str):
            if reason == "run_terminal":
                self.entered.set()
                if not self.release.wait(timeout=10):
                    raise RuntimeError("terminal sweep test gate timed out")
            return self.delegate.sweep(reason)

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unhandled: list[dict] = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(
            lambda _loop, context: unhandled.append(dict(context))
        )
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        blocker = BlockingTerminalSweep(broker.sweeper)
        broker.sweeper = blocker
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        pending: asyncio.Task | None = None
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-collection-sweep-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            adapter.finished.set()
            pending = asyncio.create_task(
                first.adapter.collect_result(active.process_ref)
            )
            entered = await asyncio.to_thread(blocker.entered.wait, 5)
            assert entered is True
            assert adapter.collect_calls == 1
            assert broker._runs[attempt_id].collected_receipt is not None
            assert broker._runs[attempt_id].collection_task is not None
            assert not broker._runs[attempt_id].collection_task.done()
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending

            del active
            del first
            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-collection-sweep-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.TERMINAL_RECOVERED
            ]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1

            finisher = asyncio.create_task(
                restarted.finish_job(recovered[0])
            )
            await asyncio.sleep(0.05)
            blocker.release.set()
            terminal = await finisher

            assert terminal.job.status is JobStatus.COMPLETED
            assert terminal.attempt.status is AttemptStatus.COMPLETED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert terminal.attempt.exit_code == 0
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
        finally:
            adapter.finished.set()
            blocker.release.set()
            if pending is not None and not pending.done():
                pending.cancel()
            await asyncio.sleep(0)
            await _close_fixture(broker, adapter, server, socket_path)
            await asyncio.sleep(0.05)
            loop.set_exception_handler(prior_handler)
        assert unhandled == []

    asyncio.run(scenario())


def test_cancelled_restart_waits_for_inflight_validation_owner(
    tmp_path: Path,
) -> None:
    """Cancellation cannot release capacity while exact validation is still owned."""

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unhandled: list[dict] = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(
            lambda _loop, context: unhandled.append(dict(context))
        )
        broker, adapter, server, socket_path, client = await _serve_fixture(
            tmp_path
        )
        runtime_root, runtime, job = _runtime_and_job(tmp_path, broker)
        pending: asyncio.Task | None = None
        finisher: asyncio.Task | None = None
        try:
            first = _supervisor_for(
                runtime,
                broker,
                client,
                tmp_path,
                instance_id="before-cancelled-validation-restart",
            )
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation

            adapter.finished.set()
            collected = await first.adapter.collect_result(active.process_ref)
            assert collected.result.exit_code == 0
            adapter.block_validation = True
            pending = asyncio.create_task(
                first.adapter.run_validation_argv(
                    active.launch_spec,
                    ["/usr/bin/true"],
                )
            )
            await adapter.validation_entered.wait()
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
            runtime.jobs.cancel_job(job.job_id)

            del active
            del first
            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = _supervisor_for(
                reopened,
                broker,
                client,
                tmp_path,
                instance_id="after-cancelled-validation-restart",
            )
            outcomes = await asyncio.to_thread(
                restarted.reconcile_restart,
                requeue_lost=False,
            )
            assert [item.status for item in outcomes] == [
                ReconcileStatus.TERMINAL_RECOVERED
            ]
            recovered = restarted.take_recovered_runs()
            assert len(recovered) == 1

            finisher = asyncio.create_task(
                restarted.finish_job(recovered[0])
            )
            await asyncio.sleep(0.05)
            assert not finisher.done(), (
                "replacement supervisor released the cancelled Attempt while "
                "the broker still owned its validation"
            )
            status = await client.request("status", {"run_id": attempt_id})
            assert status["run"]["validation_busy"] is True

            adapter.validation_release.set()
            terminal = await finisher

            assert terminal.job.status is JobStatus.CANCELLED
            assert terminal.attempt.status is AttemptStatus.CANCELLED
            assert terminal.attempt.attempt_id == attempt_id
            assert terminal.attempt.fence_generation == original_fence + 1
            assert terminal.validation_receipt_path is None
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 1
            assert adapter.validation_calls == [("/usr/bin/true",)]
            status = await client.request("status", {"run_id": attempt_id})
            assert status["run"]["validation_busy"] is False
            assert status["validation_busy"] is False
            assert [
                item.attempt_id
                for item in reopened.attempts.list_attempts(job.job_id)
            ] == [attempt_id]
        finally:
            adapter.finished.set()
            adapter.validation_release.set()
            if pending is not None and not pending.done():
                pending.cancel()
            if finisher is not None and not finisher.done():
                finisher.cancel()
                await asyncio.gather(finisher, return_exceptions=True)
            await asyncio.sleep(0)
            await _close_fixture(broker, adapter, server, socket_path)
            await asyncio.sleep(0.05)
            loop.set_exception_handler(prior_handler)
        assert unhandled == []

    asyncio.run(scenario())
