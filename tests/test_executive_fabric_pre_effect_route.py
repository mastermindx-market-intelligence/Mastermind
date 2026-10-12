"""In-process review regressions; never dispatches hosts or providers."""
import asyncio

import pytest

from control_plane.executive_fabric_bridge_broker import BridgeProtocolError
from control_plane.executive_worker_broker import BrokerProtocolError, PeerCredentials
from test_executive_fabric_adapter import _fixture, physical
from test_executive_fabric_bridge_broker import Backend, broker, envelope


class RoutedBackend(Backend):
    """Existing test owner with an explicit actual route and observable effects."""

    def __init__(self, route):
        super().__init__()
        self.route = route
        self.effects = []

    async def start_owned(self, payload, *, authority):
        authority.require(payload)
        if payload["physical_binding_sha256"] != self.route:
            raise BridgeProtocolError("EFFECT_UNKNOWN", "actual fixture route moved")
        return await self.execute("start", payload)

    async def execute(self, operation, payload):
        if operation in {"start", "cancel", "validate"}:
            self.effects.append(operation)
        result = await super().execute(operation, payload)
        result["physical_binding_sha256"] = self.route
        if operation == "start":
            result["process_ref"]["run_id"] = payload["launch_spec"]["run_id"]
        return result


class InProcessClient:
    """Exercise the actual broker and facade across a pure authenticated seam."""

    def __init__(self):
        self.service = None

    async def request(self, operation, payload, **_options):
        response = await self.service.execute(envelope(operation, payload),
                                               peer=PeerCredentials(uid=450, gid=450))
        return response["result"]


def composed(tmp_path, monkeypatch, route):
    client = InProcessClient()
    runtime, _job, lease, adapter, spec, payload = _fixture(tmp_path, monkeypatch, client)
    payload["validation_commands"] = [["/usr/bin/true"]]
    backend = RoutedBackend(route)
    client.service = broker(tmp_path, monkeypatch, backend)
    return runtime, lease, adapter, spec, backend


def test_wrong_preflight_route_is_refused_before_start_effect(tmp_path, monkeypatch):
    runtime, lease, adapter, spec, backend = composed(tmp_path, monkeypatch, "8" * 64)
    assert backend.route != physical().digest
    with pytest.raises((BrokerProtocolError, BridgeProtocolError)):
        asyncio.run(adapter.start(spec, lease=lease))
    # A final facade rejection cannot undo a provider launch on another route.
    assert backend.effects == []
    assert [operation for operation, _payload in backend.calls] == ["status"]
    assert runtime.attempts.get_attempt(spec.run_id).pid is None


@pytest.mark.parametrize("operation", ["cancel", "validate"])
def test_moved_route_is_refused_before_mutating_original_run(tmp_path, monkeypatch, operation):
    runtime, lease, adapter, spec, backend = composed(tmp_path, monkeypatch, physical().digest)
    ref = asyncio.run(adapter.start(spec, lease=lease))
    runtime.attempts.record_process(spec.run_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id=ref.provider_session_id)
    runtime.attempts.mark_running(spec.run_id, fence_generation=lease.attempt.fence_generation,
                                 lease_token=lease.lease_token)
    backend.effects.clear()
    backend.calls.clear()
    backend.route = "8" * 64
    with pytest.raises((BrokerProtocolError, BridgeProtocolError)):
        if operation == "cancel":
            asyncio.run(adapter.cancel(ref, "inert cancellation request"))
        else:
            asyncio.run(adapter.run_validation_argv(spec, ("/usr/bin/true",), timeout_seconds=1))
    assert backend.effects == []
    assert [kind for kind, _payload in backend.calls] == ["status"]
