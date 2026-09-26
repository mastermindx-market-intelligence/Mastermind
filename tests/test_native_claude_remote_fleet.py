"""Provider-free native Claude composition through the existing remote fleet.

The fake transport never opens a socket, starts a provider, or reads credentials.
It supplies broker wire receipts so the production fleet and adapter facades are
exercised rather than replaced with fake adapters.
"""
from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from control_plane.executive_worker_broker import (
    BrokerProtocolError,
    BrokerStateError,
    RemoteWorkerBrokerEndpoint,
    RemoteWorkerBrokerFleet,
    WorkerBrokerError,
)
from control_plane.worker_adapter import adapter_descriptor
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    WorkerLaunchSpec,
    WorkerProcessRef,
)


class _BrokerWire:
    def __init__(self, adapter_id: str, *, lose_response: bool = False) -> None:
        self.adapter_id = adapter_id
        self.lose_response = lose_response
        self.calls: list[tuple[str, dict]] = []

    async def request(self, operation: str, payload: dict) -> dict:
        self.calls.append((operation, payload))
        if self.lose_response:
            raise ConnectionError("fixture lost response after submission")
        if operation != "start":
            raise AssertionError(f"unexpected fixture operation: {operation}")
        spec = payload["launch_spec"]
        run_id = spec["run_id"]
        binary_name = "claude" if self.adapter_id == "claude-code" else "codex"
        binary = BinaryAttestation(
            path=f"/fixtures/{binary_name}",
            real_path=f"/fixtures/{binary_name}",
            version="1.0.0",
            sha256="a" * 64,
            team_identifier=None,
            size=1,
            device=1,
            inode=2,
            mode=0o755,
            uid=0,
            gid=0,
            mtime_ns=1,
        )
        ref = WorkerProcessRef(
            run_id=run_id,
            pid=43210,
            pgid=43210,
            process_start_identity="fixture-start",
            boot_session_id="fixture-boot",
            launch_nonce=f"fixture-{run_id}",
            provider_session_id=None,
            stdout_path=f"/fixtures/{run_id}.out",
            stderr_path=f"/fixtures/{run_id}.err",
            result_path=f"/fixtures/{run_id}.json",
            started_at=datetime.now(timezone.utc).isoformat(),
            binary=binary,
            base_sha="b" * 40,
            effective_uid=451,
            effective_gid=451,
            real_uid=451,
            real_gid=451,
        )
        return {
            "adapter_id": self.adapter_id,
            "process_ref": dataclasses.asdict(ref),
            "launch_attestation": {"run_id": run_id},
            "startup_sweep": {
                "schema_version": "mastermind.executive_uid_sweep/v2",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "reason": "startup",
                "worker_uid": 451,
                "broker_pid": 43209,
                "residual_pids_before": [],
                "residual_pids_after": [],
                "signal_name": "SIGKILL",
                "signal_sent": False,
                "quiescent_observations": 2,
                "ambient_pids": [],
                "ambient_identities": [],
                "ambient_attribution": "absent",
                "passed": True,
                "found_residuals": False,
            },
        }


def _endpoint(worker_id: str, client: _BrokerWire, **kwargs) -> RemoteWorkerBrokerEndpoint:
    return RemoteWorkerBrokerEndpoint(
        worker_id=worker_id,
        client=client,
        worker_user=f"_fixture_{worker_id}",
        worker_uid=451,
        worker_gid=451,
        **kwargs,
    )


def _spec(run_id: str, worker_id: str) -> WorkerLaunchSpec:
    return WorkerLaunchSpec(
        run_id=run_id,
        job_id=f"job-{run_id}",
        worker_id=worker_id,
        workspace_path=Path("/fixtures/workspace"),
        run_dir=Path(f"/fixtures/run-{run_id}"),
        prompt="provider-free transport test",
        result_schema_path=Path(f"/fixtures/run-{run_id}/schema.json"),
    )


class NativeClaudeRemoteFleetTest(unittest.IsolatedAsyncioTestCase):
    def test_legacy_endpoint_retains_codex_default_without_transport(self) -> None:
        client = _BrokerWire("codex-cli")
        endpoint = _endpoint("legacy", client)
        self.assertEqual(getattr(endpoint, "adapter_id", None), "codex-cli")
        self.assertEqual(client.calls, [])

    def test_endpoint_identity_is_frozen(self) -> None:
        endpoint = _endpoint("native", _BrokerWire("claude-code"), adapter_id="claude-code")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            endpoint.adapter_id = "codex-cli"

    def test_unreviewed_or_noncanonical_adapter_is_refused_before_transport(self) -> None:
        for invalid in (None, True, "", "claude", "Claude-Code", " claude-code", "claude-code ",
                        "claude-compatible-subscription", "acp", "unknown", []):
            with self.subTest(adapter_id=invalid):
                client = _BrokerWire("claude-code")
                with self.assertRaises(WorkerBrokerError):
                    _endpoint("native", client, adapter_id=invalid)
                self.assertEqual(client.calls, [])

    async def test_default_factory_launches_claude_and_codex_on_exact_endpoints(self) -> None:
        native = _BrokerWire("claude-code")
        codex = _BrokerWire("codex-cli")
        fleet = RemoteWorkerBrokerFleet([
            _endpoint("native", native, adapter_id="claude-code"),
            _endpoint("codex", codex),
        ])
        self.assertEqual(native.calls, [])
        self.assertEqual(codex.calls, [])
        native_ref = await fleet.start(_spec("native-run", "native"))
        codex_ref = await fleet.start(_spec("codex-run", "codex"))
        self.assertEqual(native_ref.binary.path, "/fixtures/claude")
        self.assertEqual(codex_ref.binary.path, "/fixtures/codex")
        self.assertEqual(native_ref.run_id, "native-run")
        self.assertEqual(codex_ref.run_id, "codex-run")
        self.assertEqual(len(native.calls), 1)
        self.assertEqual(len(codex.calls), 1)
        self.assertEqual(native.calls[0][1]["launch_spec"]["worker_id"], "native")
        self.assertEqual(codex.calls[0][1]["launch_spec"]["worker_id"], "codex")
        self.assertNotIn("adapter_id", native.calls[0][1])

    async def test_claude_endpoint_refuses_codex_response_without_fallback(self) -> None:
        wrong = _BrokerWire("codex-cli")
        other = _BrokerWire("codex-cli")
        fleet = RemoteWorkerBrokerFleet([
            _endpoint("native", wrong, adapter_id="claude-code"),
            _endpoint("other", other),
        ])
        with self.assertRaises(BrokerProtocolError):
            await fleet.start(_spec("bound-run", "native"))
        with self.assertRaises(BrokerStateError):
            await fleet.start(_spec("bound-run", "other"))
        self.assertEqual(len(wrong.calls), 1)
        self.assertEqual(other.calls, [])

    async def test_lost_native_response_keeps_same_worker_binding(self) -> None:
        native = _BrokerWire("claude-code", lose_response=True)
        other = _BrokerWire("codex-cli")
        fleet = RemoteWorkerBrokerFleet([
            _endpoint("native", native, adapter_id="claude-code"),
            _endpoint("other", other),
        ])
        with self.assertRaises(ConnectionError):
            await fleet.start(_spec("uncertain-run", "native"))
        with self.assertRaises(BrokerStateError):
            await fleet.start(_spec("uncertain-run", "other"))
        self.assertEqual(len(native.calls), 1)
        self.assertEqual(other.calls, [])

    def test_transport_composition_does_not_enable_native_admission(self) -> None:
        self.assertFalse(adapter_descriptor("claude-code").implemented)


if __name__ == "__main__":
    unittest.main()
