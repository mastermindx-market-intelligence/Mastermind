"""Full Control start over TLS/Unix; provider observations are synthetic fixtures.

Regression witnesses: losing Control's workspace-source wiring breaks the
remote-only start; accepting a changed second binding violates pre-RPC refusal.
This proves source composition, never installed identities or two-host readiness.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane import executive_worker_broker as broker
from control_plane import remote_attempt_transport as remote
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisorError
from control_plane.executive_runtime import AttemptStatus, JobStatus, WorkerStatus
from control_plane.operator_harness_contract import WorkspaceIdentity
from control_plane.operator_harness_wire import (
    event_cursor, process_generation_ref, requested_execution_profile, to_wire, turn_ref,
)
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import BrokerTransportBinding
from scripts import executive_os_phase1c as cli
from test_ceo_submit_armed_composition import _raw, _write
from test_executive_operator_supervisor import (
    _ActiveAdapter, _PromptSource, _seed_dispatchable_operator_planner,
)
from test_remote_attempt_transport import HOST_A, _join
from tests import test_remote_worker_gateway as gateway_tests


pytestmark = [pytest.mark.anyio, pytest.mark.skipif(
    not gateway_tests._openssl_available(), reason="openssl unavailable")]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def journey(tmp_path, monkeypatch, request):
    runtime, root, planner = _seed_dispatchable_operator_planner(tmp_path / "job")
    quota = runtime.workers.get_quota_class("worker-a", "codex-coo-operator")
    assert quota is not None
    runtime.workers.register_worker(
        "worker-b", provider=quota.provider, account_label="synthetic-selected-worker",
        worker_type="fixture", capabilities=quota.capabilities,
        quota_classes={quota.quota_class: {
            "provider": quota.provider, "model": quota.model, "effort": quota.effort,
            "cost_class": quota.cost_class, "capabilities": quota.capabilities,
            "metadata": {**quota.metadata, "capacity_join": _join()},
        }},
    )
    runtime.workers.set_worker_status("worker-a", WorkerStatus.OFFLINE)
    workspace = Path(planner.worktree)
    info = workspace.stat()
    physical = WorkspaceIdentity(str(workspace), planner.constraints["base_sha"],
        info.st_dev, info.st_ino, info.st_uid, info.st_gid)
    # Move only this fixture directory; the canonical assigned path is now absent.
    workspace.rename(workspace.with_name("synthetic-worker-materialization"))
    assert not workspace.exists()
    monkeypatch.setattr(gateway_tests, "HOST_REF", HOST_A)
    operations = {"ohf-validate", "ohf-start", "ohf-begin-turn",
                  "ohf-collect-turn", "ohf-stop"}
    gateway = await gateway_tests._gateway_fixture(
        tmp_path, allowed_operations=operations, allowed_worker_ids={"worker-b"})
    calls, broker_errors, primary_calls, observations, rpc_attempts = [], [], [], [], []
    handlers = []
    prompts = {}
    provider = _ActiveAdapter(runtime, lambda turn: prompts[turn.turn_id],
                              cancel_during_collect=False)

    async def reply(reader, writer):
        handlers.append(asyncio.current_task())
        message = None
        try:
            message = json.loads(await reader.readline())
            calls.append(message)  # Record every attempt before fixture validation.
            payload, operation = message["payload"], message["operation"]
            if operation == "ohf-validate":
                profile = requested_execution_profile(payload["requested"])
                result = {"validation": to_wire(provider.validate_requested_profile(profile))}
            elif operation == "ohf-start":
                profile = requested_execution_profile(payload["requested"])
                assert profile == provider.profile
                generation = process_generation_ref(payload["generation"])
                result = {
                    "observation": to_wire(provider.start_session()),
                    "attestation": to_wire(provider.observed_attestation(generation)),
                    "process_credentials": to_wire(provider.observe_process_credentials(generation)),
                    "provider_home": to_wire(provider.observe_provider_home_identity(generation)),
                }
            elif operation == "ohf-begin-turn":
                turn = turn_ref(payload["turn"])
                prompts[turn.turn_id] = payload["prompt"]
                result = {"observation": to_wire(provider.begin_turn(turn=turn))}
            elif operation == "ohf-collect-turn":
                turn = turn_ref(payload["turn"])
                events, cursor = provider.read_events(event_cursor(payload["cursor"]),
                    timeout_seconds=payload["timeout_seconds"])
                result = {
                    "events": to_wire(events), "cursor": to_wire(cursor),
                    "candidate": to_wire(provider.collect_candidate_result(turn)),
                    "raw_role_result": to_wire(provider.observe_raw_role_result(turn)),
                }
            elif operation == "ohf-stop":
                result = {"observation": to_wire(provider.graceful_stop(
                    process_generation_ref(payload["generation"]))), "artifact_receipt": None}
            else:
                raise AssertionError(f"unexpected provider fixture operation: {operation}")
            response = dict(schema_version=broker.BROKER_RESPONSE_SCHEMA_VERSION,
                request_id=message["request_id"], operation=operation, ok=True, result=result)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
        except Exception as exc:
            broker_errors.append((message, repr(exc)))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as exc:
                broker_errors.append((message, repr(exc)))

    def forbidden_primary(*args, **kwargs):
        primary_calls.append((args, kwargs))
        raise AssertionError("selected remote claim reached the primary worker client")

    try:
        gateway.unix_server.close()
        await gateway.unix_server.wait_closed()
        gateway.broker_socket.unlink(missing_ok=True)
        gateway.unix_server = await asyncio.start_unix_server(
            reply, path=str(gateway.broker_socket))
        transport = BrokerTransportBinding(endpoint=("localhost", gateway.endpoint[1]),
            ca_path=gateway.config.ca_path, client_cert_path=gateway.control_cert,
            client_key_path=gateway.control_key,
            expected_server_fingerprint=gateway_tests._cert_sha256(gateway.config.certificate_path))
        from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
        policy = ExecutionCapabilityRegistry.load().resolve(planner.constraints["execution_profile_id"])
        host = remote.RemoteOperatorHostBinding(
            host_ref=HOST_A, worker_id="worker-b", transport=transport,
            worker_source_config_digest="c" * 64, provider="openai-codex",
            harness_kind="codex-app-server",
            harness_binary_digest=planner.constraints["harness_binary_digest"],
            harness_version=planner.constraints["harness_version"],
            expected_config_digest=policy.expected_config_digest,
            workspace=physical, capabilities=codex_remote_capabilities())
        drift = getattr(request, "param", None)

        def source(host_ref, worker_id):
            observations.append((host_ref, worker_id))
            assert (host_ref, worker_id) == (HOST_A, "worker-b")
            if len(observations) == 2 and drift == "inode":
                return dataclasses.replace(host, workspace=dataclasses.replace(
                    physical, inode=physical.inode + 1))
            if len(observations) == 2 and drift == "worker_source_config_digest":
                return dataclasses.replace(host, worker_source_config_digest="f" * 64)
            return host

        # Keep the actual Control service/factory. Only host socket activation is inert.
        monkeypatch.setattr(cli, "activate_launchd_socket", lambda name: None)
        primary_socket = tmp_path / "worker.sock"
        real_request = broker.WorkerBrokerClient.request

        async def request(client, *args, **kwargs):
            if client.socket_path == primary_socket:
                return forbidden_primary(*args, **kwargs)
            return await real_request(client, *args, **kwargs)

        real_remote_request = RemoteWorkerBrokerClient.request_sync

        def remote_request(client, operation, payload, **kwargs):
            rpc_attempts.append((dict(client.identity), operation))
            return real_remote_request(client, operation, payload, **kwargs)

        monkeypatch.setattr(broker.WorkerBrokerClient, "request", request)
        monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", remote_request)
        service = cli._service_from_config(cli.load_control_config(_write(tmp_path, _raw(tmp_path))),
            remote_operator_binding_source=source)
        supervisor = service._operator_supervisor_factory(runtime, _PromptSource())
        assert service.config.worker_id != "worker-b"
        yield dict(runtime=runtime, root=root, planner=planner, supervisor=supervisor,
            physical=physical, calls=calls, observations=observations, provider=provider,
            rpc_attempts=rpc_attempts)
    finally:
        await gateway_tests._close_gateway(gateway)
        handler_results = await asyncio.gather(*handlers, return_exceptions=True)
        assert not any(isinstance(result, BaseException) for result in handler_results)
        assert primary_calls == []
        assert broker_errors == []


def _dispatch_command(case):
    return f"coo-cycle:{case['root'].job_id}:dispatch:{case['planner'].job_id}:attempt:1"


async def test_full_control_start_remote_only_workspace_reaches_runtime_terminal(journey):
    case = journey
    outcome = await case["supervisor"].start_cycle_job(
        case["planner"].job_id, command_id=_dispatch_command(case))
    runtime, attempt = case["runtime"], outcome.attempt
    assert outcome.outcome == "TERMINAL" and attempt.status is AttemptStatus.COMPLETED
    assert runtime.jobs.get_job(attempt.job_id).status is JobStatus.COMPLETED
    assert attempt.worker_id == "worker-b"
    assert requested_execution_profile(attempt.requested_execution_profile).workspace == case["physical"]
    assert case["observations"] == [(HOST_A, "worker-b")] * 2
    calls = case["calls"]
    assert [call["operation"] for call in calls] == [
        "ohf-validate", "ohf-start", "ohf-begin-turn", "ohf-collect-turn", "ohf-stop"]
    assert [operation for identity, operation in case["rpc_attempts"]] == [
        call["operation"] for call in calls]
    assert all(identity["worker_id"] == "worker-b" and identity["attempt_id"] == attempt.attempt_id
               and identity["job_id"] == attempt.job_id for identity, _ in case["rpc_attempts"])
    assert calls[0]["payload"]["requested"] == attempt.requested_execution_profile
    assert calls[1]["payload"]["requested"] == attempt.requested_execution_profile
    assert case["provider"].begin_turn_calls == case["provider"].stop_calls == 1
    seal = runtime.events.get_event_by_command_id(f"orchestration-result-seal:{attempt.attempt_id}")
    assert seal.event_type == "ORCHESTRATION_ROLE_RESULT_SEALED"
    assert seal.worker_id == "worker-b" and seal.job_id == attempt.job_id
    terminal = attempt.result
    assert terminal["schema_version"] == "mastermind.orchestration_terminal_receipt/v1"
    assert terminal["attempt_id"] == attempt.attempt_id and terminal["job_id"] == attempt.job_id
    assert terminal["result_envelope"] == seal.payload["result_envelope"]
    assert terminal["result_envelope_digest"] == seal.payload["result_envelope_digest"]
    with runtime.store.read() as connection:
        epochs = connection.execute("SELECT state FROM harness_session_epochs WHERE attempt_id=?",
                                    (attempt.attempt_id,)).fetchall()
        writers = connection.execute("SELECT g.executive_writer_held FROM process_generations g "
                                     "JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id "
                                     "WHERE e.attempt_id=?",
                                     (attempt.attempt_id,)).fetchall()
        completed = connection.execute("SELECT worker_id FROM events WHERE attempt_id=? AND event_type='JOB_COMPLETED'",
                                       (attempt.attempt_id,)).fetchall()
    assert [row[0] for row in epochs] == ["ABANDONED"]
    assert [row[0] for row in writers] == [0]
    assert [row[0] for row in completed] == ["worker-b"]
    # Replay the same dispatch command consumes the terminal receipt without another RPC.
    replay = await case["supervisor"].start_cycle_job(
        case["planner"].job_id, command_id=_dispatch_command(case))
    assert replay.attempt == attempt and replay.outcome == "TERMINAL"
    assert len(calls) == len(case["rpc_attempts"]) == 5 and len(case["observations"]) == 2


@pytest.mark.parametrize("journey", ["inode", "worker_source_config_digest"], indirect=True)
async def test_full_control_start_binding_drift_refuses_before_broker_rpc(journey):
    case = journey
    with pytest.raises(ExecutiveOperatorSupervisorError, match="claimed operator construction refused"):
        await case["supervisor"].start_cycle_job(
            case["planner"].job_id, command_id=_dispatch_command(case))
    assert case["observations"] == [(HOST_A, "worker-b")] * 2
    assert case["calls"] == [] and case["provider"].begin_turn_calls == 0
    assert case["rpc_attempts"] == []
    runtime = case["runtime"]
    attempts = runtime.attempts.list_attempts()
    assert len(attempts) == 1 and attempts[0].worker_id == "worker-b"
    assert attempts[0].status is AttemptStatus.CLAIMED
    assert attempts[0].requested_execution_profile is None
    assert attempts[0].result is None
    assert runtime.events.get_event_by_command_id(
        f"orchestration-result-seal:{attempts[0].attempt_id}") is None
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0
