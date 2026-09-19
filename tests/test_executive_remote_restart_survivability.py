"""Canonical remote-broker restart survivability discriminator for Executive OS."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from pathlib import Path

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ReconcileStatus,
    RESULT_SCHEMA_VERSION,
)
from control_plane.executive_worker_broker import (
    RemoteCodexWorkerAdapter,
    RemoteWorkerProcessController,
    WorkerBrokerClient,
)
from test_executive_worker_broker import FakeAdapter, _fixture, _socket_path


def test_remote_supervisor_restart_terminalizes_same_broker_owned_attempt(
    tmp_path: Path,
) -> None:
    """Canonical Phase 1C restart keeps one provider execution and Attempt."""

    class RestartCompletionAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.start_calls = 0
            self.collect_calls = 0

        async def start(self, spec):
            self.start_calls += 1
            return await super().start(spec)

        def launch_attestation(self, ref):
            value = dict(super().launch_attestation(ref))
            identity = dict(value["process_identity"])
            identity.update(
                {
                    "start_identity": ref.process_start_identity,
                    "boot_id": ref.boot_session_id,
                    "real_uid": ref.real_uid,
                    "real_gid": ref.real_gid,
                }
            )
            value["process_identity"] = identity
            return value

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

    async def scenario() -> None:
        broker, _fixture_adapter, sweeper, peer, _fixture_spec = _fixture(
            tmp_path
        )
        adapter = RestartCompletionAdapter()
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
        canary = {
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

        def supervisor_for(
            owned_runtime: Runtime,
            *,
            instance_id: str,
        ) -> ExecutiveSupervisor:
            def validations(spec):
                persisted = owned_runtime.jobs.get_job(spec.job_id)
                assert persisted is not None
                return tuple(
                    tuple(command)
                    for command in persisted.validation_commands
                )

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
                secret_canary_verdict=canary,
                require_complete_launch_attestation=True,
                heartbeat_interval_seconds=0.01,
                process_controller=RemoteWorkerProcessController(client),
                instance_id=instance_id,
            )

        try:
            first = supervisor_for(runtime, instance_id="before-restart")
            active = await first.start_job(job.job_id)
            attempt_id = active.lease.attempt.attempt_id
            original_fence = active.lease.attempt.fence_generation
            assert adapter.start_calls == 1
            assert adapter.collect_calls == 0

            # Model only the Executive/control-process death. The worker broker
            # remains the original child parent and retains truthful exit status.
            del active
            del first

            reopened = Runtime.at(runtime_root, lease_seconds=30)
            restarted = supervisor_for(
                reopened,
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
            adapter.finished.set()
            await broker.shutdown()
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())
