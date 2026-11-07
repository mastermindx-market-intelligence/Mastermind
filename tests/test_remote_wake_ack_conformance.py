"""Provider-free remote Wake/ACK conformance over the real mTLS/Unix chain.

This is synthetic-principal protocol evidence, NOT OS isolation or live-fleet
proof. The existing test-only peer_resolver seam supplies a distinct control UID;
BrokerPolicy and the real Unix handler/authorization remain enabled. Only native
provider I/O is deterministic. Unix/TLS-unavailable runners must report NOT_RUN,
not skip this campaign and call it accepted. No production process is launched.
"""
from __future__ import annotations

import pytest

from control_plane.wake_ledger import LedgerPhase


import asyncio
import copy
import dataclasses
import hashlib
import os
import ssl
import threading
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from control_plane import codex_operator_adapter, executive_worker_broker, wake_dispatcher
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_worker_broker import BrokerPolicy, PeerCredentials
from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION
from control_plane.operator_harness_wire import to_wire
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import BrokerTransportBinding, TransportEffect, TransportError
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import (
    SCHEMA as TARGET_SCHEMA,
    SessionTargetRegistry,
    route_obligation,
)
from control_plane.wake_ack_ingress import WakeAckClaim, acknowledge_consumed_wakes
from control_plane.wake_dispatcher import (
    WakeDispatchError,
    WakeNudge,
    dispatch_persisted_nudge,
    normalize_transport_completion,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    SourceReadHealth,
    WakeLedgerError,
    WakeRetryPolicy,
    expected_resolution_code,
    requested_record,
    resolve_source,
    resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_reconcile import collect_source_snapshot, reconcile_wakes
from integrations.executive_wake.codex_app_server import CodexAppServerWakeDispatcher
from integrations.executive_wake.codex_app_server_rpc import CodexCurrentWriterWakeClient
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import (
    REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA,
    RemoteWorkerGatewayConfig,
)
from scripts.ohf.laboratory import JsonRpcError
from tests.test_executive_wake_ack_end_to_end import _source_attempt
from tests.test_executive_worker_broker import _reviewed_codex_adapter
from tests.test_remote_worker_transport import _certificate_fixture
from tests.test_runtime_binding_projection import (
    _admitted_runtime,
    _attestation,
    _resume_admitted_runtime,
    _target,
)


_POLICY = WakeRetryPolicy(
    max_delivery_attempts=1,
    retry_cooldown_s=1,
    accepted_ttl_s=60,
    target_unavailable_backoff_s=1,
    reenable_on_binding_rotation=False,
    armed=True,
)
_OPERATIONS = frozenset({"ohf-deliver-attention", "ohf-reconcile"})
_HOST_REF = hashlib.sha256(b"remote-wake-synthetic-host").hexdigest()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class ProviderFixture:
    """Native I/O only: terminal text is parsed by the actual owned adapter."""

    native_handle: str
    obligation_id: str
    before_submission: Any
    mode: str = "valid"
    turn_id: str = "turn-remote-wake-1"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    submitted: threading.Event = field(default_factory=threading.Event)
    completion_available: threading.Event = field(default_factory=threading.Event)
    completion_reads: int = 0
    timeout_reads: int = 0

    def __post_init__(self) -> None:
        self.completion_available.set()

    @property
    def write_count(self) -> int:
        return sum(method == "turn/start" for method, _ in self.calls)

    def alive(self) -> bool:
        return True

    def request(self, method: str, params: Mapping[str, Any] | None = None, *, timeout: float = 60.0) -> dict[str, Any]:
        value = dict(params or {})
        self.calls.append((method, copy.deepcopy(value)))
        if method == "thread/read":
            assert value == {"threadId": self.native_handle}
            return {"thread": {"id": self.native_handle}}
        assert method == "turn/start", f"unexpected provider method: {method}"
        self.before_submission()
        assert value["threadId"] == self.native_handle
        self.submitted.set()
        return {"turn": {"id": self.turn_id}}

    def terminal(self) -> dict[str, Any]:
        marker = f"MASTERMIND_WAKE_ACK {self.obligation_id}"
        texts = {
            "valid": f"Canonical attention source consumed.\n{marker}",
            "echoed": f"Example instruction: {marker}",
            "forged": "MASTERMIND_WAKE_ACK WAKE-" + "f" * 32,
            "duplicate": f"{marker}\n{marker}",
            "malformed": "MASTERMIND_WAKE_ACK WAKE-malformed",
            "conflicting": marker,
        }
        item = {"type": "agentMessage", "phase": "final_answer", "text": texts[self.mode]}
        if self.mode == "conflicting":
            item["content"] = [{"type": "output_text", "text": "conflicting answer"}]
        return {
            "method": "turn/completed",
            "params": {
                "threadId": self.native_handle,
                "turn": {"id": self.turn_id, "status": "completed", "items": [item]},
            },
        }

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        assert method == "turn/completed"
        if not self.completion_available.is_set():
            self.timeout_reads += 1
            raise JsonRpcError(f"timeout waiting for notification {method}")
        assert self.submitted.is_set(), "completion cannot precede provider submission"
        self.completion_available.clear()
        self.completion_reads += 1
        return self.terminal()

    def drain_notifications(self) -> list[dict[str, Any]]:
        return []


class _NoProcessSweeper:
    def sweep(self, reason):
        pytest.fail(f"provider-free conformance must not sweep OS processes: {reason}")


class _RecordingClient(RemoteWorkerBrokerClient):
    """Transparent observation, with no substituted transport results."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests = []
        self.errors = []

    async def request(self, operation, payload, *, timeout_seconds=None):
        self.requests.append((operation, copy.deepcopy(dict(payload))))
        try:
            return await super().request(operation, payload, timeout_seconds=timeout_seconds)
        except TransportError as exc:
            self.errors.append(exc)
            raise


@dataclass
class RemoteWakeChain:
    admitted: tuple
    target: Any
    registry: SessionTargetRegistry
    binding: Any
    obligation: Any
    route: Any
    repo: WakeLedgerRepository
    provider: ProviderFixture
    owned_adapter: Any
    broker: executive_worker_broker.ExecutiveWorkerBroker
    peer_calls: list
    identity: dict[str, str]
    gateway_calls: list = field(default_factory=list)
    ack_projections: list = field(default_factory=list)
    handlers: set = field(default_factory=set)
    writers: set = field(default_factory=set)
    client: Any = None
    dispatcher: Any = None
    gateway: Any = None
    server: Any = None
    unix_server: Any = None
    config: Any = None
    transport_binding: Any = None

    @property
    def runtime(self):
        return self.repo.runtime

    @property
    def generation(self):
        return self.admitted[4]

    def records(self):
        return tuple(row.record for row in self.repo.list_records(self.obligation.obligation_id))

    def phases(self):
        return [record.phase for record in self.records()]

    def assert_before_submission(self):
        assert self.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]

    async def dispatch(self, *, binding=None, route=None):
        return await dispatch_persisted_nudge(
            self.repo,
            [(self.obligation, route or self.route)],
            dispatcher=self.dispatcher,
            binding=binding or self.binding,
            retry_policy=_POLICY,
            target_registry=self.registry,
        )

    def source_resolution(self):
        snapshot = collect_source_snapshot(self.runtime, include_boot_packet=False)
        assert snapshot.inbox_runtime_health is SourceReadHealth.HEALTHY
        assert self.obligation.obligation_id not in {item.obligation_id for item in snapshot.observed}
        return resolved_record(
            self.obligation,
            resolve_source(
                self.obligation,
                code=expected_resolution_code(self.obligation),
                health=snapshot.inbox_runtime_health,
                source_present=False,
                snapshot_digest=snapshot.digest,
            ),
        )

    def assert_resolution_refused(self):
        with pytest.raises((WakeLedgerError, StateConflict), match="TARGET_ACKNOWLEDGED"):
            self.repo.append_record(self.source_resolution(), obligation=self.obligation)

    def resolve_source(self):
        result = reconcile_wakes(self.runtime, include_boot_packet=False)
        assert result.snapshot.inbox_runtime_health is SourceReadHealth.HEALTHY
        assert self.obligation.obligation_id in result.resolved
        assert result.transport_invocations == result.delivery_attempts == 0

    def assert_no_ack(self):
        assert LedgerPhase.TARGET_ACKNOWLEDGED not in self.phases()
        assert LedgerPhase.SOURCE_RESOLVED not in self.phases()
        assert self.ack_projections == []
        self.assert_resolution_refused()

    def assert_duplicate_ack_is_idempotent(self):
        assert len(self.ack_projections) == 1
        trusted = self.ack_projections[0]
        before = self.records()
        replay = acknowledge_consumed_wakes(
            self.runtime, self.registry,
            claim=WakeAckClaim(trusted.obligation_ids), trusted=trusted,
        )
        assert len(replay) == 1 and replay[0].inserted is False
        assert self.records() == before

    def assert_exact_submission(self, result):
        assert self.provider.write_count == 1
        method, payload = next(call for call in self.provider.calls if call[0] == "turn/start")
        assert method == "turn/start"
        assert payload["threadId"] == self.binding.native_handle
        assert payload["clientUserMessageId"] == result.nudge_id
        text = payload["input"][0]["text"]
        assert text.startswith(ATTENTION_TURN_INSTRUCTION)
        for opaque in (self.obligation.obligation_id, *tuple(item.attempt_command_id for item in result.nudge_attempt.attempts)):
            assert f"- {opaque}" in text
        assert self.gateway_calls[0][0] == "ohf-deliver-attention"
        assert self.gateway_calls[0][1]["generation"] == to_wire(self.generation)
        assert self.peer_calls
        if self.ack_projections:
            trusted = self.ack_projections[0]
            assert trusted.target_attempt_id == self.admitted[2].attempt_id
            assert trusted.process_generation_id == self.generation.process_generation_id
            assert trusted.binding_id == self.binding.binding_id
            assert trusted.binding_generation == self.binding.binding_generation
            assert trusted.provider_session_id == self.binding.native_handle
            assert trusted.provider_native_turn_id == self.provider.turn_id
            assert trusted.nudge_id == result.nudge_id
            assert trusted.obligation_ids == (self.obligation.obligation_id,)

    def wake_for(self, result):
        return WakeNudge(
            session_alias=self.binding.session_alias,
            reasoning_surface="codex", wake_transport="codex-app-server",
            binding_id=self.binding.binding_id,
            binding_generation=self.binding.binding_generation,
            native_handle=self.binding.native_handle,
            account_label=self.binding.account_label,
            destination_digest=self.route.destination_digest,
            obligation_ids=(self.obligation.obligation_id,),
            attempt_command_ids=tuple(item.attempt_command_id for item in result.nudge_attempt.attempts),
            nudge_id=result.nudge_id,
        )

    def bind_client(self, transport_binding=None):
        self.client = _RecordingClient(
            transport_binding or self.transport_binding,
            self.identity,
            allowed_operations=_OPERATIONS,
            bound_payload_identity={
                "session_epoch_id": self.generation.session_epoch_id,
                "process_generation_id": self.generation.process_generation_id,
            },
        )
        remote = RemoteCodexOperatorAdapter(self.client, turn_input_loader=lambda _: pytest.fail("unexpected ordinary turn"))
        self.dispatcher = CodexAppServerWakeDispatcher(CodexCurrentWriterWakeClient(
            operator_adapter=remote, generation=self.generation,
            attempt_id=self.admitted[2].attempt_id, runtime_binding=self.binding,
            completion_timeout_seconds=0.1,
        ))

    async def track(self, handler, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        self.writers.add(writer)
        try:
            await handler(reader, writer)
        finally:
            self.handlers.discard(task)
            self.writers.discard(writer)

    async def start_gateway(self):
        self.gateway = RemoteWorkerGateway(self.config)
        original_call = self.gateway.broker_call

        async def observe_call(operation, payload):
            self.gateway_calls.append((operation, copy.deepcopy(dict(payload))))
            return await original_call(operation, payload)

        self.gateway.broker_call = observe_call
        original_handler = self.gateway._handle_connection
        self.gateway._handle_connection = lambda r, w: self.track(original_handler, r, w)
        self.server = await self.gateway.start_server()
        endpoint = self.server.sockets[0].getsockname()[:2]
        self.transport_binding = dataclasses.replace(self.transport_binding, endpoint=endpoint)
        self.bind_client()

    async def close(self):
        servers = tuple(server for server in (self.server, self.unix_server) if server is not None)
        try:
            for server in servers:
                server.close()
            for writer in tuple(self.writers):
                writer.close()
            tasks = tuple(self.handlers)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for server in servers:
                await server.wait_closed()
            assert not self.handlers
            assert all(method in {"thread/read", "turn/start"} for method, _ in self.provider.calls), self.provider.calls
        finally:
            if self.config is not None:
                self.config.broker_socket_path.unlink(missing_ok=True)


def _build_core(tmp_path: Path) -> RemoteWakeChain:
    admitted = _admitted_runtime(tmp_path / "runtime")
    runtime, _dispatch, sealed, epoch, generation, process, profile = admitted
    source_attempt, source_job, source_root = _source_attempt(runtime)
    assert source_attempt != sealed.attempt_id
    target = dataclasses.replace(_target(), wake_transport="codex-app-server", allowed_transports=("codex-app-server",), target_enabled=True)
    registry = SessionTargetRegistry(
        schema=TARGET_SCHEMA, lifecycle_authority="executive_os", production_armed=True,
        policy_version="remote-wake-conformance", default_alias_by_seat={"coo": target.session_alias},
        workstream_alias_by_seat={}, root_job_bindings={source_root: {"coo": target.session_alias}},
        targets={target.session_alias: target},
    )
    binding = project_runtime_binding(runtime, sealed.attempt_id, target)
    obligation = mint_obligation(
        wake_kind="job_failed", source_kind="executive_inbox_attention", source_ref="eia-00000000cafe",
        declared_target_seat="coo", job_id=source_job, attempt_id=source_attempt, root_job_id=source_root,
    )
    repo = WakeLedgerRepository(runtime)
    repo.append_record(requested_record(obligation), obligation=obligation)
    provider = ProviderFixture(str(binding.native_handle), obligation.obligation_id, lambda: None)
    # Seed the already-owned generation, as in test_codex_app_server_wake_rpc.
    # No start/resume, configuration guard changes, or production credentials.
    adapter = object.__new__(codex_operator_adapter.CodexOperatorAdapter)
    adapter.worker_id = generation.worker_id
    adapter.workspace_root = tmp_path
    adapter.process_identity_observer = lambda _pid: process
    adapter._active_workers = {generation.worker_id: generation.process_generation_id}
    adapter._generations = {generation.process_generation_id: codex_operator_adapter._GenerationState(
        epoch=epoch, generation=generation, requested=profile, client=provider,
        provider_session_id=str(binding.native_handle), provider_session_tree_id=str(binding.native_handle),
        process=process, attestation=_attestation(profile),
    )}
    roots = [tmp_path / name for name in ("workspaces", "runs", "provider-home")]
    for root in roots:
        root.mkdir(mode=0o700)
    policy = BrokerPolicy(
        control_uid=os.getuid() + 1000, worker_uid=os.getuid(), worker_gid=os.getgid(),
        worker_user="synthetic-worker", worker_id=generation.worker_id,
        workspace_root=roots[0], run_root=roots[1], provider_home=roots[2],
        allowed_supplementary_gids=frozenset(set(os.getgroups()) - {os.getgid()}),
    )
    peer_calls = []

    def synthetic_peer(sock):
        peer_calls.append(sock.family)
        return PeerCredentials(uid=policy.control_uid, gid=policy.worker_gid, pid=100)

    broker = executive_worker_broker.ExecutiveWorkerBroker(
        _reviewed_codex_adapter(tmp_path / "reviewed-flat-adapter"), policy,
        _NoProcessSweeper(), peer_resolver=synthetic_peer,
    )
    broker._operator_run = executive_worker_broker._BrokerOperatorRun(
        adapter=adapter, requested=profile, epoch=epoch, generation=generation,
        provider_session_id=str(binding.native_handle),
    )
    chain = RemoteWakeChain(
        admitted, target, registry, binding, obligation,
        route_obligation(obligation, registry, binding=binding), repo,
        provider, adapter, broker, peer_calls,
        {"host_ref": _HOST_REF, "job_id": sealed.job_id, "attempt_id": sealed.attempt_id,
         "worker_id": generation.worker_id, "operation_id": "OP-remote-wake-conformance"},
    )
    provider.before_submission = chain.assert_before_submission
    return chain


def _fingerprint(path):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(path.read_text())).hexdigest()


@pytest.fixture
async def remote_wake_chain(tmp_path: Path, monkeypatch) -> AsyncIterator[RemoteWakeChain]:
    chain = _build_core(tmp_path)
    original_ack = wake_dispatcher.acknowledge_consumed_wakes

    def observe_ack(*args, **kwargs):
        assert chain.phases()[-1] is LedgerPhase.DELIVERED
        result = original_ack(*args, **kwargs)
        chain.ack_projections.append(kwargs["trusted"])
        return result

    monkeypatch.setattr(wake_dispatcher, "acknowledge_consumed_wakes", observe_ack)
    try:
        ca_key, ca, _ = _certificate_fixture(tmp_path, name="ca", common_name="Wake test CA", san="DNS:ca.invalid", ca=True)
        server_key, server_cert, _ = _certificate_fixture(tmp_path, name="server", common_name="localhost", san="IP:127.0.0.1,DNS:localhost", issuer_key=ca_key, issuer_cert=ca)
        control_key, control_cert, _ = _certificate_fixture(tmp_path, name="control", common_name="control", san="DNS:control.invalid", issuer_key=ca_key, issuer_cert=ca)
        # Short path fits Darwin's AF_UNIX length bound; always removed in finally.
        sock = Path("/tmp") / f"wake-{uuid.uuid4().hex[:16]}.sock"
        chain.config = RemoteWorkerGatewayConfig(
            schema=REMOTE_WORKER_GATEWAY_CONFIG_SCHEMA, host_ref=_HOST_REF,
            listen_host="127.0.0.1", listen_port=0,
            certificate_path=server_cert, key_path=server_key, ca_path=ca,
            expected_control_fingerprint=_fingerprint(control_cert), broker_socket_path=sock,
            allowed_worker_ids={chain.generation.worker_id}, allowed_operations=_OPERATIONS,
            request_timeout_seconds=2.0,
        )
        chain.transport_binding = BrokerTransportBinding(
            endpoint=("127.0.0.1", 1), ca_path=ca, client_cert_path=control_cert,
            client_key_path=control_key, expected_server_fingerprint=_fingerprint(server_cert), timeout_seconds=2.0,
        )
        chain.unix_server = await asyncio.start_unix_server(
            lambda r, w: chain.track(chain.broker.handle_connection, r, w), path=str(sock),
        )
        await chain.start_gateway()
        yield chain
    finally:
        await chain.close()


@pytest.mark.anyio
async def test_remote_success_orders_delivery_ack_and_resolution(remote_wake_chain):
    chain = remote_wake_chain
    chain.assert_resolution_refused()
    result = await chain.dispatch()
    assert result.state.value == "DELIVERED"
    assert chain.provider.write_count == 1
    assert chain.phases() == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
        LedgerPhase.TARGET_ACKNOWLEDGED,
    ]
    chain.assert_exact_submission(result)
    chain.assert_duplicate_ack_is_idempotent()
    chain.resolve_source()
    assert chain.phases()[-2:] == [
        LedgerPhase.TARGET_ACKNOWLEDGED,
        LedgerPhase.SOURCE_RESOLVED,
    ]


@pytest.mark.anyio
async def test_remote_pre_submit_disconnect(remote_wake_chain):
    chain = remote_wake_chain
    chain.server.close()
    await chain.server.wait_closed()
    result = await chain.dispatch()
    assert result.state.value == "RECONCILIATION_REQUIRED"
    assert len(chain.client.requests) == 1
    assert chain.client.errors[-1].classification is TransportEffect.NO_EFFECT
    assert chain.gateway_calls == [] and chain.peer_calls == []
    assert chain.provider.write_count == 0
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    before = chain.records()
    replay = await chain.dispatch()
    assert replay.nudge_id == result.nudge_id
    assert replay.state.value == "RECONCILIATION_REQUIRED"
    assert chain.records() == before and len(chain.client.requests) == 1
    chain.assert_no_ack()


@pytest.mark.anyio
async def test_remote_accepted_response_loss(remote_wake_chain, monkeypatch):
    chain = remote_wake_chain
    chain.provider.completion_available.clear()
    lost_responses = []

    async def lose_response(writer, response):
        # The actual broker/native operation completed before this network fault.
        assert chain.provider.submitted.is_set()
        assert chain.provider.write_count == 1
        assert response["broker_response"]["observation"]["accepted"] is True
        assert response["broker_response"]["observation"]["delivered"] is False
        lost_responses.append(response["request_sha256"])
        writer.close()
        await writer.wait_closed()

    original_response = chain.gateway._write_response
    monkeypatch.setattr(chain.gateway, "_write_response", lose_response)
    result = await chain.dispatch()
    assert lost_responses and chain.provider.timeout_reads == 1
    assert result.state.value == "RECONCILIATION_REQUIRED"
    assert chain.client.errors[-1].classification is TransportEffect.EFFECT_UNKNOWN
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    replay = await chain.dispatch()
    assert replay.nudge_id == result.nudge_id and len(chain.client.requests) == 1
    chain.assert_no_ack()

    # Unfinished-attempt persistence stays fenced. Existing exact readback is
    # observable separately; this test never manufactures ACCEPTED or ACK rows.
    monkeypatch.setattr(chain.gateway, "_write_response", original_response)
    chain.provider.completion_available.set()
    completion = await chain.dispatcher.reconcile(chain.wake_for(result))
    receipt, projection = normalize_transport_completion(completion)
    assert receipt.outcome.value == "DELIVERED"
    assert projection is not None and projection.nudge_id == result.nudge_id
    assert projection.process_generation_id == chain.generation.process_generation_id
    assert chain.provider.completion_reads == 1 and chain.provider.write_count == 1
    assert [operation for operation, _ in chain.gateway_calls] == ["ohf-deliver-attention", "ohf-reconcile"]
    assert (await chain.dispatch()).state.value == "RECONCILIATION_REQUIRED"
    chain.assert_no_ack()


@pytest.mark.anyio
async def test_remote_late_completion(remote_wake_chain):
    chain = remote_wake_chain
    chain.provider.completion_available.clear()
    result = await chain.dispatch()
    assert result.state.value == "ACCEPTED"
    assert chain.provider.timeout_reads == 1
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED]
    chain.assert_no_ack()
    chain.provider.completion_available.set()
    late = await chain.dispatch()
    assert late.state.value == "DELIVERED" and late.nudge_id == result.nudge_id
    assert chain.provider.write_count == 1 and chain.provider.completion_reads == 1
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED, LedgerPhase.DELIVERED, LedgerPhase.TARGET_ACKNOWLEDGED]
    assert [operation for operation, _ in chain.gateway_calls] == ["ohf-deliver-attention", "ohf-reconcile"]
    chain.assert_exact_submission(late)
    before = chain.records()
    assert (await chain.dispatch()).nudge_id == result.nudge_id
    assert chain.records() == before and chain.provider.write_count == 1


@pytest.mark.anyio
async def test_remote_gateway_restart(remote_wake_chain):
    chain = remote_wake_chain
    chain.provider.completion_available.clear()
    first = await chain.dispatch()
    assert first.state.value == "ACCEPTED" and chain.provider.write_count == 1
    old_gateway, old_client = chain.gateway, chain.client
    chain.server.close()
    await chain.server.wait_closed()
    chain.repo = WakeLedgerRepository(Runtime.at(chain.runtime.store.root))
    assert chain.phases()[-1] is LedgerPhase.ACCEPTED
    await chain.start_gateway()
    assert chain.gateway is not old_gateway and chain.client is not old_client
    chain.provider.completion_available.set()
    recovered = await chain.dispatch()
    assert recovered.state.value == "DELIVERED" and recovered.nudge_id == first.nudge_id
    assert [op for op, _ in chain.client.requests] == ["ohf-reconcile"]
    assert chain.provider.write_count == 1
    assert chain.phases().count(LedgerPhase.TARGET_ACKNOWLEDGED) == 1
    chain.assert_exact_submission(recovered)


@pytest.mark.anyio
@pytest.mark.parametrize("dimension", ["host", "worker", "attempt", "epoch", "generation", "session"])
async def test_remote_wrong_identity(remote_wake_chain, dimension):
    chain = remote_wake_chain
    state = chain.broker._operator_run
    if dimension == "host":
        chain.client.identity["host_ref"] = "b" * 64
    elif dimension == "worker":
        chain.client.identity["worker_id"] = "worker-other"
    elif dimension == "attempt":
        chain.client.identity["attempt_id"] = "ATT-" + "9" * 32
    elif dimension == "epoch":
        state.generation = dataclasses.replace(state.generation, session_epoch_id="epoch-other")
    elif dimension == "generation":
        state.generation = dataclasses.replace(state.generation, process_generation_id="generation-other")
    else:
        state.provider_session_id = "PROVIDER-SESSION-OTHER"
    result = await chain.dispatch()
    assert result.state.value == "RECONCILIATION_REQUIRED"
    assert len(chain.client.requests) == 1 and len(chain.client.errors) == 1
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    before = chain.records()
    assert chain.provider.calls == []
    if dimension in {"host", "worker", "attempt"}:
        assert chain.gateway_calls == [] and chain.peer_calls == []
        assert chain.client.errors[-1].classification is TransportEffect.NO_EFFECT
    else:
        assert len(chain.gateway_calls) == 1 and len(chain.peer_calls) == 1
        assert chain.client.errors[-1].classification is TransportEffect.EFFECT_UNKNOWN
    assert (await chain.dispatch()).nudge_id == result.nudge_id
    assert len(chain.client.requests) == 1 and chain.provider.write_count == 0
    assert chain.records() == before
    chain.assert_no_ack()


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["wrong_pin", "untrusted_client", "missing_client"])
async def test_remote_tls_refusal(remote_wake_chain, monkeypatch, tmp_path, fault):
    chain = remote_wake_chain
    if fault == "wrong_pin":
        chain.bind_client(dataclasses.replace(chain.transport_binding, expected_server_fingerprint="0" * 64))
    elif fault == "untrusted_client":
        key, cert, _ = _certificate_fixture(tmp_path, name="untrusted-client", common_name="untrusted", san="DNS:untrusted.invalid", ca=True)
        chain.bind_client(dataclasses.replace(chain.transport_binding, client_cert_path=cert, client_key_path=key))
    else:
        # Binding cannot represent an absent cert. Restrict this injection to the
        # test client's TLS connection, preserving actual TLS and pin checks.
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(chain.config.ca_path))
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3

        async def no_client_certificate():
            return await asyncio.open_connection(*chain.transport_binding.endpoint, ssl=context, server_hostname="127.0.0.1")

        monkeypatch.setattr(chain.client, "_open_connection", no_client_certificate)
    result = await chain.dispatch()
    assert result.state.value == "RECONCILIATION_REQUIRED"
    assert len(chain.client.requests) == 1 and len(chain.client.errors) == 1
    if fault == "wrong_pin":
        assert chain.client.errors[-1].code == "server_identity_mismatch"
        assert chain.client.errors[-1].classification is TransportEffect.NO_EFFECT
    assert chain.gateway_calls == [] and chain.peer_calls == []
    assert chain.provider.write_count == 0
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    before = chain.records()
    assert (await chain.dispatch()).nudge_id == result.nudge_id
    assert chain.records() == before and len(chain.client.requests) == 1
    chain.assert_no_ack()


@pytest.mark.anyio
async def test_remote_unix_peer_refusal(remote_wake_chain):
    chain = remote_wake_chain
    refused_peers = []

    def wrong_peer(sock):
        refused_peers.append(sock.family)
        return PeerCredentials(uid=chain.broker.policy.worker_uid, gid=chain.broker.policy.worker_gid, pid=100)

    chain.broker.peer_resolver = wrong_peer
    result = await chain.dispatch()
    assert result.state.value == "RECONCILIATION_REQUIRED"
    assert len(chain.gateway_calls) == 1 and len(refused_peers) == 1
    assert chain.client.errors[-1].classification is TransportEffect.EFFECT_UNKNOWN
    assert chain.provider.write_count == 0
    assert chain.phases() == [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    before = chain.records()
    assert (await chain.dispatch()).nudge_id == result.nudge_id
    assert chain.records() == before and len(chain.client.requests) == 1
    chain.assert_no_ack()


@pytest.mark.anyio
async def test_remote_duplicate_request(remote_wake_chain):
    chain = remote_wake_chain
    first = await chain.dispatch()
    assert first.state.value == "DELIVERED"
    before = chain.records()
    second = await chain.dispatch()
    assert second.nudge_id == first.nudge_id and second.state.value == "DELIVERED"
    assert chain.records() == before
    assert chain.provider.write_count == 1 and len(chain.client.requests) == 1
    chain.assert_duplicate_ack_is_idempotent()


@pytest.mark.anyio
async def test_remote_duplicate_request_changed_payload(remote_wake_chain):
    chain = remote_wake_chain
    chain.provider.completion_available.clear()
    first = await chain.dispatch()
    assert first.state.value == "ACCEPTED"
    before = chain.records()
    # Same persisted obligation/nudge, but a different identity-bearing body.
    operation, payload = copy.deepcopy(chain.client.requests[0])
    payload["provider_session_id"] = "PROVIDER-SESSION-OTHER"
    with pytest.raises(TransportError):
        await chain.client.request(operation, payload)
    assert chain.client.errors[-1].classification is TransportEffect.EFFECT_UNKNOWN
    assert len(chain.gateway_calls) == 2 and len(chain.peer_calls) == 2
    assert chain.records() == before and chain.provider.write_count == 1
    assert chain.owned_adapter._generations[chain.generation.process_generation_id].attention_inflight
    chain.assert_no_ack()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["echoed", "forged", "duplicate", "malformed", "conflicting"])
async def test_remote_invalid_terminal_ack(remote_wake_chain, mode):
    chain = remote_wake_chain
    chain.provider.mode = mode
    result = await chain.dispatch()
    # A syntactically valid wrong obligation reaches the exact-session mapper,
    # which must preserve uncertainty rather than ACK the claimed obligation.
    assert result.state.value == ("RECONCILIATION_REQUIRED" if mode == "forged" else "DELIVERED")
    assert chain.provider.completion_reads == 1 and chain.provider.write_count == 1
    expected_phases = [LedgerPhase.WAKE_REQUESTED, LedgerPhase.DELIVERY_ATTEMPT]
    if mode != "forged":
        expected_phases.append(LedgerPhase.DELIVERED)
    assert chain.phases() == expected_phases
    assert len(chain.gateway_calls) == 1 and len(chain.peer_calls) == 1
    before = chain.records()
    replay = await chain.dispatch()
    assert replay.nudge_id == result.nudge_id and chain.records() == before
    assert chain.provider.write_count == 1 and len(chain.client.requests) == 1
    chain.assert_no_ack()


@pytest.mark.anyio
async def test_remote_binding_rotation(remote_wake_chain):
    chain = remote_wake_chain
    chain.provider.completion_available.clear()
    first = await chain.dispatch()
    assert first.state.value == "ACCEPTED" and chain.provider.write_count == 1
    before = chain.records()
    _resume_admitted_runtime(chain.admitted)
    rotated = project_runtime_binding(chain.runtime, chain.admitted[2].attempt_id, chain.target)
    assert rotated.binding_generation == chain.binding.binding_generation + 1
    rotated_route = route_obligation(chain.obligation, chain.registry, binding=rotated)
    with pytest.raises(WakeDispatchError, match="does not match"):
        await chain.dispatch(binding=rotated, route=rotated_route)
    assert chain.records() == before
    assert len(chain.client.requests) == 1 and chain.provider.write_count == 1
    chain.assert_no_ack()
