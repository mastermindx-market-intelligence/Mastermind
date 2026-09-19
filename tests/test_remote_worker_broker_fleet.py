from __future__ import annotations

import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path

from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_worker_broker import (
    BrokerStateError,
    RemoteWorkerBrokerEndpoint,
    RemoteWorkerBrokerFleet,
    WorkerBrokerClient,
    WorkerBrokerError,
)
from control_plane.worker_adapter import WorkerExecutionAdapter
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRunStatus,
)


def _binary() -> BinaryAttestation:
    return BinaryAttestation(
        path="/usr/local/bin/codex",
        real_path="/usr/local/bin/codex",
        version="0.147.0",
        sha256="a" * 64,
        team_identifier="2DC432GLL2",
        size=1,
        device=1,
        inode=2,
        mode=0o755,
        uid=0,
        gid=0,
        mtime_ns=1,
    )


def _ref(run_id: str, pid: int) -> WorkerProcessRef:
    return WorkerProcessRef(
        run_id=run_id,
        pid=pid,
        pgid=pid,
        process_start_identity=f"start-{pid}",
        boot_session_id="boot-1",
        launch_nonce=f"nonce-{pid}",
        provider_session_id=None,
        stdout_path=f"/tmp/{run_id}.out",
        stderr_path=f"/tmp/{run_id}.err",
        result_path=f"/tmp/{run_id}.json",
        started_at="2026-09-13T00:00:00+00:00",
        binary=_binary(),
        base_sha="b" * 40,
        effective_uid=451,
        effective_gid=451,
        real_uid=451,
        real_gid=451,
    )


def _spec(run_id: str, worker_id: str) -> WorkerLaunchSpec:
    return WorkerLaunchSpec(
        run_id=run_id,
        job_id=f"job-{run_id}",
        worker_id=worker_id,
        workspace_path=Path("/tmp/workspace"),
        run_dir=Path(f"/tmp/run-{run_id}"),
        prompt="bounded job",
        result_schema_path=Path(f"/tmp/run-{run_id}/schema.json"),
    )


class _FakeAdapter:
    def __init__(self, name: str, pid: int, *, fail_start: bool = False) -> None:
        self.name = name
        self.pid = pid
        self.fail_start = fail_start
        self.calls: list[tuple] = []
        self.start_specs: list[WorkerLaunchSpec] = []
        self.validation_specs: list[WorkerLaunchSpec] = []
        self.inspector = object()

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        self.start_specs.append(spec)
        self.calls.append(("start", spec.run_id, spec.worker_id))
        if self.fail_start:
            raise RuntimeError("ambiguous fixture start")
        return _ref(spec.run_id, self.pid)

    def launch_attestation(self, ref: WorkerProcessRef):
        self.calls.append(("attestation", ref.run_id))
        return {"worker": self.name, "run_id": ref.run_id}

    def uid_sweep_receipt(self, ref: WorkerProcessRef):
        self.calls.append(("sweep", ref.run_id))
        return {"worker": self.name, "run_id": ref.run_id}

    async def cleanup_unbound_run(self, run_id: str):
        self.calls.append(("cleanup", run_id))
        return {"worker": self.name, "run_id": run_id}

    async def status(self, ref: WorkerProcessRef):
        self.calls.append(("status", ref.run_id))
        return WorkerRunStatus.RUNNING

    async def collect_result(self, ref: WorkerProcessRef):
        self.calls.append(("collect", ref.run_id))
        return (self.name, "collect", ref.run_id)

    async def cancel(self, ref: WorkerProcessRef, reason: str):
        self.calls.append(("cancel", ref.run_id, reason))
        return (self.name, "cancel", ref.run_id)

    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv,
        *,
        timeout_seconds: float = 300.0,
    ):
        self.validation_specs.append(spec)
        self.calls.append(("validate", spec.run_id, tuple(argv), timeout_seconds))
        return (self.name, "validate", spec.run_id)


class _FakeController:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple] = []

    def uid_sweep_receipt(self, attempt):
        self.calls.append(("sweep", attempt.attempt_id))
        return {"worker": self.name, "run_id": attempt.attempt_id}

    def presence(self, attempt):
        self.calls.append(("presence", attempt.attempt_id))
        return (self.name, "presence")

    def absence_verified(self, attempt):
        self.calls.append(("absence", attempt.attempt_id))
        return True

    def terminate(self, attempt):
        self.calls.append(("terminate", attempt.attempt_id))


def _endpoint(worker_id: str, uid: int) -> RemoteWorkerBrokerEndpoint:
    return RemoteWorkerBrokerEndpoint(
        worker_id=worker_id,
        client=WorkerBrokerClient(Path(f"/tmp/{worker_id}.sock")),
        worker_user=f"_mastermind_{worker_id.replace('-', '_')}",
        worker_uid=uid,
        worker_gid=uid,
        secret_canary_verdict={"passed": True, "worker_id": worker_id},
    )


class RemoteWorkerBrokerFleetTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adapters = {
            "codex-01": _FakeAdapter("codex", 101),
            "alibaba-token-01": _FakeAdapter("alibaba", 202),
        }
        self.controllers = {
            "codex-01": _FakeController("codex"),
            "alibaba-token-01": _FakeController("alibaba"),
        }

    def _fleet(self) -> RemoteWorkerBrokerFleet:
        return RemoteWorkerBrokerFleet(
            (_endpoint("codex-01", 451), _endpoint("alibaba-token-01", 458)),
            adapter_factory=lambda row: self.adapters[row.worker_id],
            controller_factory=lambda row: self.controllers[row.worker_id],
        )

    def test_fleet_satisfies_common_adapter_and_supervisor_composition(self) -> None:
        fleet = self._fleet()
        self.assertIsInstance(fleet, WorkerExecutionAdapter)
        self.assertEqual(fleet.adapter_id, "remote-worker-broker-fleet")
        with self.assertRaises(AttributeError):
            fleet.adapter_id = "codex-cli"  # type: ignore[misc]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            supervisor = ExecutiveSupervisor(
                Runtime.at(root / "runtime"),
                fleet,
                runs_root=root / "runs",
                process_controller=fleet,
                worker_user="fixture-worker",
            )
            self.assertIs(supervisor.adapter, fleet)
            self.assertIs(supervisor.process_controller, fleet)
            self.assertIs(supervisor.inspector, fleet.inspector)

    async def test_claimed_worker_routes_all_run_operations_to_one_carrier(self) -> None:
        fleet = self._fleet()
        spec = _spec("run-1", "alibaba-token-01")
        ref = await fleet.start(spec)
        self.assertEqual(ref.pid, 202)
        bound = self.adapters["alibaba-token-01"].start_specs[0]
        self.assertEqual(bound.worker_user, "_mastermind_alibaba_token_01")
        self.assertEqual(bound.expected_worker_uid, 458)
        self.assertEqual(bound.expected_worker_gid, 458)
        self.assertEqual(dict(bound.secret_canary_verdict)["worker_id"], "alibaba-token-01")
        self.assertEqual(spec.worker_user, "mastermind-worker")
        self.assertIsNone(spec.expected_worker_uid)
        self.assertIsNone(spec.expected_worker_gid)
        self.assertEqual(await fleet.status(ref), WorkerRunStatus.RUNNING)
        self.assertEqual(await fleet.collect_result(ref), ("alibaba", "collect", "run-1"))
        self.assertEqual(
            await fleet.run_validation_argv(spec, ("/usr/bin/true",)),
            ("alibaba", "validate", "run-1"),
        )
        self.assertEqual(
            self.adapters["alibaba-token-01"].validation_specs,
            [bound],
        )
        self.assertEqual(
            await fleet.cancel(ref, "fixture"),
            ("alibaba", "cancel", "run-1"),
        )
        self.assertFalse(self.adapters["codex-01"].calls)

    async def test_missing_claimed_worker_refuses_without_fallback(self) -> None:
        fleet = self._fleet()
        with self.assertRaisesRegex(BrokerStateError, "no configured broker endpoint"):
            await fleet.start(_spec("run-missing", "glm-01"))
        self.assertFalse(self.adapters["codex-01"].calls)
        self.assertFalse(self.adapters["alibaba-token-01"].calls)

    async def test_ambiguous_start_stays_bound_to_same_carrier_for_cleanup(self) -> None:
        self.adapters["alibaba-token-01"].fail_start = True
        fleet = self._fleet()
        with self.assertRaisesRegex(RuntimeError, "ambiguous fixture start"):
            await fleet.start(_spec("run-ambiguous", "alibaba-token-01"))
        receipt = await fleet.cleanup_unbound_run("run-ambiguous")
        self.assertEqual(receipt["worker"], "alibaba")
        self.assertIn(("cleanup", "run-ambiguous"), self.adapters["alibaba-token-01"].calls)
        self.assertFalse(self.adapters["codex-01"].calls)

    async def test_run_id_cannot_rebind_after_start(self) -> None:
        fleet = self._fleet()
        await fleet.start(_spec("run-fixed", "alibaba-token-01"))
        with self.assertRaisesRegex(BrokerStateError, "already bound"):
            await fleet.start(_spec("run-fixed", "codex-01"))
        self.assertFalse(self.adapters["codex-01"].calls)

    async def test_validation_refuses_launch_spec_drift(self) -> None:
        fleet = self._fleet()
        spec = _spec("run-drift", "alibaba-token-01")
        await fleet.start(spec)
        changed = replace(spec, prompt="changed after start")
        with self.assertRaisesRegex(BrokerStateError, "differs from the spec bound"):
            await fleet.run_validation_argv(changed, ("/usr/bin/true",))
        self.assertFalse(self.adapters["alibaba-token-01"].validation_specs)

    def test_endpoint_refuses_invalid_principal_identity(self) -> None:
        with self.assertRaisesRegex(WorkerBrokerError, "invalid worker_uid"):
            RemoteWorkerBrokerEndpoint(
                worker_id="alibaba-token-01",
                client=WorkerBrokerClient(Path("/tmp/alibaba.sock")),
                worker_user="_mastermind_alibaba_01",
                worker_uid=0,
                worker_gid=458,
            )

    def test_endpoint_canary_binding_is_immutable_after_construction(self) -> None:
        source = {
            "passed": True,
            "worker_id": "alibaba-token-01",
            "evidence": {"digest": "original", "chain": ["first"]},
        }
        endpoint = RemoteWorkerBrokerEndpoint(
            worker_id="alibaba-token-01",
            client=WorkerBrokerClient(Path("/tmp/alibaba-token-01.sock")),
            worker_user="_mastermind_alibaba_token_01",
            worker_uid=458,
            worker_gid=458,
            secret_canary_verdict=source,
        )

        source["evidence"]["digest"] = "mutated"
        source["evidence"]["chain"].append("mutated")
        evidence = endpoint.secret_canary_verdict["evidence"]
        self.assertEqual(evidence["digest"], "original")
        self.assertEqual(evidence["chain"], ("first",))
        with self.assertRaises(TypeError):
            endpoint.secret_canary_verdict["passed"] = False  # type: ignore[index]
        with self.assertRaises(TypeError):
            evidence["digest"] = "changed"  # type: ignore[index]
        with self.assertRaises(TypeError):
            evidence["chain"][0] = "changed"  # type: ignore[index]

        spec = _spec("run-canary-snapshot", "alibaba-token-01")
        bound = endpoint.bind_launch_spec(spec)
        self.assertEqual(bound.secret_canary_verdict["evidence"]["digest"], "original")
        self.assertEqual(bound.secret_canary_verdict["evidence"]["chain"], ("first",))
        self.assertEqual(dict(spec.secret_canary_verdict), {})
        self.assertEqual(spec.worker_user, "mastermind-worker")
        self.assertIsNone(spec.expected_worker_uid)
        self.assertIsNone(spec.expected_worker_gid)

    async def test_fresh_fleet_restart_uses_only_persisted_worker_carrier(self) -> None:
        self.adapters["alibaba-token-01"].fail_start = True
        first = self._fleet()
        with self.assertRaisesRegex(RuntimeError, "ambiguous fixture start"):
            await first.start(_spec("run-restart", "alibaba-token-01"))

        # Lose every process-local run binding. Restart reconciliation must use
        # only the durable Attempt.worker_id and the fixed endpoint catalog.
        self.adapters = {
            "codex-01": _FakeAdapter("codex", 303),
            "alibaba-token-01": _FakeAdapter("alibaba", 404),
        }
        self.controllers = {
            "codex-01": _FakeController("codex"),
            "alibaba-token-01": _FakeController("alibaba"),
        }
        fresh = self._fleet()
        attempt = types.SimpleNamespace(
            worker_id="alibaba-token-01", attempt_id="run-restart"
        )
        self.assertEqual(fresh.presence(attempt), ("alibaba", "presence"))
        self.assertTrue(fresh.absence_verified(attempt))
        fresh.terminate(attempt)
        self.assertFalse(self.controllers["codex-01"].calls)
        self.assertEqual(
            [call[0] for call in self.controllers["alibaba-token-01"].calls],
            ["presence", "absence", "terminate"],
        )

    def test_restart_controller_uses_persisted_worker_id(self) -> None:
        fleet = self._fleet()
        attempt = types.SimpleNamespace(
            worker_id="alibaba-token-01", attempt_id="attempt-1"
        )
        self.assertEqual(fleet.presence(attempt), ("alibaba", "presence"))
        self.assertTrue(fleet.absence_verified(attempt))
        fleet.terminate(attempt)
        self.assertEqual(
            [call[0] for call in self.controllers["alibaba-token-01"].calls],
            ["presence", "absence", "terminate"],
        )
        self.assertFalse(self.controllers["codex-01"].calls)
