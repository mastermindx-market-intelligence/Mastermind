"""Hermetic W6-B native one-child Executive round trip."""
from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.codex_worker import BinaryAttestation, CodexWorkerAdapter
from control_plane.worker_adapter import construct_reviewed_adapter
from control_plane.executive_agent_capabilities import (
    app_server_security_config_digest,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import (
    RESULT_SCHEMA,
    canonical_bytes as result_canonical_bytes,
)
from control_plane.executive_runtime import (
    HOST_EXECUTION_BINDING_V3,
    HOST_EXECUTION_BINDING_VERSION_KEY,
    AttemptStatus,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
)
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.operator_harness_contract import runtime_binding_id_for
from control_plane.executive_worker_broker import (
    BrokerPolicy,
    ExecutiveWorkerBroker,
    PeerCredentials,
    RemoteCodexWorkerAdapter,
    UIDSweepReceipt,
    UID_SWEEP_SCHEMA_VERSION,
    WorkerBrokerClient,
)
from control_plane.model_router import ModelRouter
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from scripts.ohf.laboratory import AppServerClient, PrivateRawTurnPage


REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_HARNESS_VERSION = "ohf-fake-app-server/p0b"
SEALED_HARNESS_VERSION = "ohf.fake.app.server.p0b"
_FAKE_MCP_PROJECTION = {
    "agents": {
        "default_subagent_model": "gpt-5.6-sol",
        "default_subagent_reasoning_effort": "xhigh",
        "enabled": True,
        "interrupt_message": None,
        "job_max_runtime_seconds": 60,
        "max_concurrent_threads_per_session": 1,
        "max_depth": 1,
    },
    "features": {
        "apps": False,
        "auth_elicitation": False,
        "enable_mcp_apps": False,
        "mcp_2026_07_28": False,
        "multi_agent": False,
        "multi_agent_v2": {
            "enabled": True,
            "hide_spawn_agent_metadata": True,
            "max_concurrent_threads_per_session": 2,
            "non_code_mode_only": False,
        },
        "plugins": False,
        "remote_plugin": False,
        "tool_call_mcp_elicitation": False,
    },
    "mcp_servers": {
        "openaiDeveloperDocs": {
            "url": "https://developers.openai.com/mcp",
            "required": True,
            "enabled": True,
            "enabled_tools": ["fetch_openai_doc", "search_openai_docs"],
            "default_tools_approval_mode": "approve",
        }
    },
    "plugins": {},
    "skills": {"config": None},
}


class _PassingSweeper:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sweep(self, reason: str) -> UIDSweepReceipt:
        self.calls.append(reason)
        return UIDSweepReceipt(
            schema_version=UID_SWEEP_SCHEMA_VERSION,
            observed_at="2026-09-13T00:00:00+00:00",
            reason=reason,
            worker_uid=os.geteuid(),
            broker_pid=os.getpid(),
            residual_pids_before=(),
            residual_pids_after=(),
            signal_name="SIGKILL",
            signal_sent=False,
            quiescent_observations=2,
        )


def _reviewed_codex_adapter(root: Path) -> CodexWorkerAdapter:
    """Construct the reviewed sealed adapter the broker now binds at init."""

    root.mkdir(parents=True, exist_ok=True)
    (root / "codex-home").mkdir(mode=0o700, exist_ok=True)
    binary = root / "reviewed-codex"
    if not binary.exists():
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o700)
    info = binary.lstat()
    attestation = BinaryAttestation(
        path=str(binary),
        real_path=str(binary.resolve()),
        version="test-0",
        sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )
    return construct_reviewed_adapter(  # type: ignore[return-value]
        "codex-cli",
        binary,
        codex_home=root / "codex-home",
        binary_attestation=attestation,
        allowed_versions=frozenset({"test-0"}),
        required_team_identifier=None,
    )


@dataclass
class _NativeFixture:
    runtime: Runtime
    runtime_path: Path
    root_id: str
    broker: ExecutiveWorkerBroker
    peer: PeerCredentials
    sweeper: _PassingSweeper
    socket_path: Path
    provider_home: Path
    workspace_root: Path
    base_sha: str


def _python_digest() -> str:
    return hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()


def _planner_result(root_id: str, attempt_id: str) -> dict:
    return {
        "schema_version": RESULT_SCHEMA,
        "job_id": root_id,
        "run_id": attempt_id,
        "worker_id": "worker-a",
        "role": "plan",
        "status": "COMPLETED",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": root_id,
            "plan_attempt_id": attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "step-1",
                    "objective": "Return one sealed reviewed result.",
                    "business_impact": "routine",
                    "review_required": True,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
        "summary": "One typed W6-B plan",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }


def _canonical_result(value: dict) -> str:
    return result_canonical_bytes(value).decode("utf-8")


def _make_git_workspace(root: Path, name: str, branch: str) -> tuple[Path, str]:
    workspace = root / name
    workspace.mkdir(parents=True)
    commands = (
        ("git", "init", "-q", "-b", branch),
        ("git", "config", "user.email", "w6b-fixture@mastermind.invalid"),
        ("git", "config", "user.name", "W6B Fixture"),
    )
    for command in commands:
        subprocess.run(command, cwd=workspace, check=True)
    (workspace / "README.md").write_text("W6B hermetic fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return workspace, head


def _build_broker(
    workspace_root: Path,
    provider_home: Path,
) -> tuple[ExecutiveWorkerBroker, _PassingSweeper, Path]:
    python = Path(sys.executable).resolve()
    fake_state = provider_home / "fake-app-server-state.json"
    router = ModelRouter.load()
    operator = router.model_aliases["coo.operator.readonly"]
    capability_profile = ExecutionCapabilityRegistry.load().resolve(
        operator.execution_profile_id
    )
    expected_config_digest = app_server_security_config_digest(_FAKE_MCP_PROJECTION)
    assert expected_config_digest == capability_profile.expected_config_digest

    def operator_factory(_workspace, turn_loader, requested):
        del turn_loader
        return CodexOperatorAdapter(
            binary_path=python,
            codex_home=provider_home,
            workspace_root=Path(requested.workspace.workspace_path),
            worker_id="worker-a",
            app_server_argv=(str(python), "-m", "scripts.ohf.fake_app_server"),
            expected_harness_version=requested.harness_version,
            expected_config_digest=expected_config_digest,
            native_helper_grant=capability_profile.native_helper,
            network_policy="disabled",
            turn_input_loader=lambda turn: "unused",
            base_sha_resolver=lambda _path: requested.workspace.base_sha,
            extra_env={
                "PYTHONPATH": str(REPO_ROOT),
                "OHF_FAKE_STATE": str(fake_state),
                "OHF_FAKE_WORKSPACE": str(Path(requested.workspace.workspace_path)),
                "OHF_FAKE_SKILL_ROOT": str(
                    Path(requested.workspace.workspace_path) / ".agents" / "skills"
                ),
                "OHF_FAKE_MODEL": "gpt-5.6-sol",
                "OHF_FAKE_NATIVE_HELPER": "1",
                "OHF_FAKE_TURN_REPLY": os.environ.get("OHF_FAKE_TURN_REPLY", ""),
            },
        )

    policy = BrokerPolicy(
        control_uid=os.geteuid() + 1000 if os.geteuid() != 0 else 501,
        worker_uid=os.geteuid(),
        worker_gid=os.getegid(),
        worker_user="fixture-worker",
        worker_id="worker-a",
        workspace_root=workspace_root,
        run_root=workspace_root.parent / "runs",
        provider_home=provider_home,
        allowed_supplementary_gids=frozenset(set(os.getgroups()) - {os.getegid()}),
    )
    sweeper = _PassingSweeper()
    broker = ExecutiveWorkerBroker(
        _reviewed_codex_adapter(provider_home.parent / "reviewed-codex-adapter"),
        policy,
        sweeper,
        operator_adapter_factory=operator_factory,
        operator_harness_armed=True,
        autonomy_guard=lambda: None,
        autonomy_canary_factory=lambda value: dict(value),
    )
    broker.peer_resolver = lambda _socket: PeerCredentials(
        policy.control_uid, policy.worker_gid, os.getpid()
    )
    socket_path = (
        Path(tempfile.gettempdir())
        / f"mm-w6b-{os.getpid()}-{os.urandom(4).hex()}.sock"
    )
    return broker, sweeper, socket_path


def _native_fixture(tmp_path: Path) -> _NativeFixture:
    workspace_root = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace_root, run_root, provider_home):
        path.mkdir(parents=True, mode=0o700)
    workspace, base_sha = _make_git_workspace(
        workspace_root, "w6b-root", "codex/w6b-fixture"
    )
    (provider_home / "auth.json").write_text(
        "fixture marker, not a credential\n", encoding="utf-8"
    )
    (provider_home / "auth.json").chmod(0o600)
    router = ModelRouter.load()
    operator = router.model_aliases["coo.operator.readonly"]
    broker, sweeper, socket_path = _build_broker(workspace_root, provider_home)
    runtime_path = tmp_path / "runtime"
    runtime = Runtime.at(runtime_path)
    binding = {
        "eligible_quota_classes": ["codex-coo-default"],
        "provider": operator.provider_alias,
        "model": operator.model,
        "effort": operator.effort,
        "cost_class": operator.cost_class,
        "base_sha": base_sha,
        "routing_policy_version": router.policy_version,
        "execution_profile_id": operator.execution_profile_id,
        "execution_profile_digest": operator.execution_profile_digest,
        "capability_policy_version": operator.capability_policy_version,
        "capability_policy_digest": operator.capability_policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": operator.provider_alias,
        "operator_model": operator.model,
        "operator_effort": operator.effort,
        "operator_cost_class": operator.cost_class,
        "operator_routing_policy_version": router.policy_version,
        "operator_execution_profile_id": operator.execution_profile_id,
        "operator_execution_profile_digest": operator.execution_profile_digest,
        "operator_capability_policy_version": operator.capability_policy_version,
        "operator_capability_policy_digest": operator.capability_policy_digest,
        "operator_harness_binary_digest": _python_digest(),
        "operator_harness_version": SEALED_HARNESS_VERSION,
        "operator_harness_armed": True,
        HOST_EXECUTION_BINDING_VERSION_KEY: HOST_EXECUTION_BINDING_V3,
        "work_placement_union": [
            {
                "provider_realm": "codex",
                "quota_class": "codex-coo-default",
            }
        ],
    }
    runtime.workers.register_worker(
        "worker-a",
        provider=operator.provider_alias,
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=list(operator.capabilities),
        quota_classes={
            "codex-coo-default": {
                "provider": operator.provider_alias,
                "model": operator.model,
                "effort": operator.effort,
                "cost_class": operator.cost_class,
                "capabilities": list(operator.capabilities),
                "metadata": {
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": operator.execution_profile_id,
                    "execution_profile_digest": operator.execution_profile_digest,
                    "capability_policy_version": operator.capability_policy_version,
                    "capability_policy_digest": operator.capability_policy_digest,
                },
            },
            "codex-coo-operator": {
                "provider": operator.provider_alias,
                "model": operator.model,
                "effort": operator.effort,
                "cost_class": operator.cost_class,
                "capabilities": list(operator.capabilities),
                "metadata": {
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": operator.execution_profile_id,
                    "execution_profile_digest": operator.execution_profile_digest,
                    "capability_policy_version": operator.capability_policy_version,
                    "capability_policy_digest": operator.capability_policy_digest,
                    "harness_binary_digest": binding["operator_harness_binary_digest"],
                    "harness_version": SEALED_HARNESS_VERSION,
                },
            },
        },
    )
    runtime.workers.register_worker(
        "worker-b",
        provider=operator.provider_alias,
        account_label="worker-b@company",
        worker_type="fixture-review",
        capabilities=list(operator.capabilities),
        quota_classes={
            "codex-coo-default": {
                "provider": operator.provider_alias,
                "model": operator.model,
                "effort": operator.effort,
                "cost_class": operator.cost_class,
                "capabilities": list(operator.capabilities),
                "metadata": {
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": operator.execution_profile_id,
                    "execution_profile_digest": operator.execution_profile_digest,
                    "capability_policy_version": operator.capability_policy_version,
                    "capability_policy_digest": operator.capability_policy_digest,
                },
            }
        },
    )
    intent = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-W6B-HERMETIC-001",
        "actor": "ceo-sol",
        "objective": "Prove one native planner round trip.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": base_sha, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "branch": "codex/w6b-fixture",
            "worktree": str(workspace),
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "routine",
    }
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace_root,
        execution_binding=binding,
    )
    return _NativeFixture(
        runtime=runtime,
        runtime_path=runtime_path,
        root_id=str(receipt["job_id"]),
        broker=broker,
        peer=broker.peer_resolver(object()),
        sweeper=sweeper,
        socket_path=socket_path,
        provider_home=provider_home,
        workspace_root=workspace_root,
        base_sha=base_sha,
    )


def _plan_reply(runtime: Runtime, root_id: str, attempt_id: str) -> str:
    value = _planner_result(root_id, attempt_id)
    value["job_id"] = runtime.attempts.get_attempt(attempt_id).job_id
    return _canonical_result(value)


def _with_fake_reply(
    monkeypatch,
    reply: str,
    requests: list[str] | None = None,
) -> None:
    monkeypatch.setenv("OHF_FAKE_TURN_REPLY", reply)
    from control_plane import codex_operator_adapter

    monkeypatch.setattr(
        codex_operator_adapter,
        "_observed_network_state",
        lambda _config: "disabled",
    )
    original_request = AppServerClient.request

    def sealed_harness_version_request(
        client, method: str, params=None, *args, **kwargs
    ):
        if requests is not None:
            requests.append(method)
        result = original_request(client, method, params, *args, **kwargs)
        if method == "initialize" and isinstance(result, dict):
            if result.get("userAgent") == FAKE_HARNESS_VERSION:
                result["userAgent"] = SEALED_HARNESS_VERSION
        elif method == "config/read" and isinstance(result, dict):
            config = result.get("config")
            if isinstance(config, dict):
                config["mcp_servers"] = _FAKE_MCP_PROJECTION["mcp_servers"]
                config["skills"] = _FAKE_MCP_PROJECTION["skills"]
        elif method == "mcpServerStatus/list" and isinstance(result, dict):
            rows = result.get("data")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("name") == "ohf_probe":
                        row["name"] = "openaiDeveloperDocs"
                        row["serverInfo"] = {
                            "name": "openai-docs-mcp",
                            "version": "1.0.0",
                        }
                        row["tools"] = {
                            "fetch_openai_doc": {
                                "name": "fetch_openai_doc",
                                "annotations": {
                                    "destructiveHint": False,
                                    "readOnlyHint": True,
                                },
                                "inputSchema": {
                                    "$schema": (
                                        "http://json-schema.org/draft-07/schema#"
                                    ),
                                    "properties": {
                                        "anchor": {"type": "string"},
                                        "url": {"minLength": 1, "type": "string"},
                                    },
                                    "required": ["url"],
                                    "type": "object",
                                },
                            },
                            "search_openai_docs": {
                                "name": "search_openai_docs",
                                "annotations": {
                                    "destructiveHint": False,
                                    "readOnlyHint": True,
                                },
                                "inputSchema": {
                                    "$schema": (
                                        "http://json-schema.org/draft-07/schema#"
                                    ),
                                    "properties": {
                                        "cursor": {"type": "string"},
                                        "limit": {
                                            "maximum": 50,
                                            "minimum": 1,
                                            "type": "integer",
                                        },
                                        "query": {
                                            "minLength": 1,
                                            "type": "string",
                                        },
                                    },
                                    "required": ["query"],
                                    "type": "object",
                                },
                            },
                        }
        return result

    monkeypatch.setattr(
        AppServerClient,
        "request",
        sealed_harness_version_request,
    )

    def sealed_request_raw_turn_page(client, **kwargs):
        result = client.request(
            "thread/turns/list",
            {"threadId": kwargs["thread_id"]},
        )
        rows = result.get("data")
        matches = [
            row
            for row in rows or []
            if isinstance(row, dict) and row.get("id") == kwargs["native_turn_id"]
        ]
        assert len(matches) == 1
        result = {
            "data": matches,
            "nextCursor": result.get("nextCursor"),
        }
        return PrivateRawTurnPage(result, 4096)

    monkeypatch.setattr(
        AppServerClient,
        "request_raw_turn_page",
        sealed_request_raw_turn_page,
    )


def _bind_supervisors(
    runtime: Runtime, socket_path: Path
) -> tuple[ExecutiveOperatorSupervisor, ExecutiveSupervisor]:
    """Real production owners used by ExecutiveService._dispatch_cycle_job_exact."""

    client = WorkerBrokerClient(socket_path, timeout_seconds=15.0)
    sealed = ExecutiveSupervisor(
        runtime,
        RemoteCodexWorkerAdapter(client),
        instance_id="executive-supervisor",
    )
    operator = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=lambda loader: RemoteCodexOperatorAdapter(
            client, turn_input_loader=loader
        ),
        prompt_source=sealed,
        instance_id="executive-coo-operator",
    )
    return operator, sealed


async def _start_via_production_route(
    operator: ExecutiveOperatorSupervisor,
    sealed: ExecutiveSupervisor,
    runtime: Runtime,
    job_id: str,
    command_id: str,
) -> OrchestrationDispatchOutcome:
    """Mirror control_plane/executive_service.py:_dispatch_cycle_job_exact routing."""

    job = runtime.jobs.get_job(job_id)
    if job is None:
        raise StateConflict(f"job {job_id!r} does not exist")
    supervisor: ExecutiveOperatorSupervisor | ExecutiveSupervisor = (
        operator if job.orchestration_role == "plan" else sealed
    )
    started = await supervisor.start_cycle_job(job_id, command_id=command_id)
    if isinstance(started, OrchestrationDispatchOutcome):
        return started
    raise SupervisorError("sealed start_cycle_job returned an ActiveRun without a cycle outcome")


def _session_epoch_id(runtime: Runtime, attempt_id: str) -> str:
    with runtime.store.read() as connection:
        rows = connection.execute(
            "SELECT session_epoch_id FROM harness_session_epochs WHERE attempt_id=?",
            (attempt_id,),
        ).fetchall()
    if rows:
        return str(rows[0]["session_epoch_id"])
    return f"sealed-worker:{attempt_id}"


def _assert_hop_identity(
    runtime: Runtime,
    *,
    command_id: str,
    attempt_id: str,
    job_id: str | None = None,
) -> str:
    assert command_id
    assert attempt_id
    event = runtime.events.get_event_by_command_id(command_id)
    assert event is not None
    assert event.attempt_id == attempt_id
    if job_id is not None:
        assert event.job_id == job_id
    binding_id = runtime_binding_id_for(attempt_id, _session_epoch_id(runtime, attempt_id))
    assert binding_id.startswith("bind-")
    assert len(binding_id) == 45
    return binding_id


def test_w6b_native_round_trip_and_crash_after_dispatch_replay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    banned = (
        "dispatch_existing_attempt",
        "crash_after_dispatch",
        "_complete_ohf_role",
    )
    for name in banned:
        assert f"def {name}(" not in source

    fixture = _native_fixture(tmp_path)
    runtime_path = fixture.runtime_path
    broker_accepts: list[str] = []
    app_server_requests: list[str] = []
    sealed_starts: list[tuple[str, str]] = []

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        live_runtime = fixture.runtime
        live_broker = fixture.broker
        root_id = fixture.root_id
        workspace_root = fixture.workspace_root
        provider_home = fixture.provider_home
        socket_path = fixture.socket_path
        created = CooCycle(live_runtime).run_once(root_id)
        assert created.action == "PLANNER_CREATED"
        planner_id = str(created.selected_job_id)
        planner_create_command = f"coo-cycle:{root_id}:create-planner:0"
        assert created.command_id == planner_create_command

        first_operator, first_sealed = _bind_supervisors(
            live_runtime, socket_path
        )

        def raise_after_claim(self, job, lease):
            del self, job, lease
            raise RuntimeError("simulated crash after dispatch")

        first_operator._run_claimed = raise_after_claim.__get__(
            first_operator, type(first_operator)
        )

        def first_dispatch(job_id: str, command_id: str):
            return asyncio.run_coroutine_threadsafe(
                _start_via_production_route(
                    first_operator,
                    first_sealed,
                    live_runtime,
                    job_id,
                    command_id,
                ),
                loop,
            ).result(timeout=30)

        with pytest.raises(RuntimeError, match="simulated crash after dispatch"):
            await asyncio.to_thread(
                CooCycle(live_runtime, dispatcher=first_dispatch).run_once,
                root_id,
            )
        planner = live_runtime.jobs.get_job(planner_id)
        assert planner is not None
        assert planner.attempt_count == 1
        crash_attempt_id = str(planner.current_attempt_id)
        planner_command = (
            f"coo-cycle:{root_id}:dispatch:{planner_id}:attempt:1"
        )
        assert live_runtime.events.get_event_by_command_id(planner_command)
        assert len(live_runtime.attempts.list_attempts(planner_id)) == 1
        assert broker_accepts == []

        fixture.runtime = None  # type: ignore[assignment]
        fixture.broker = None  # type: ignore[assignment]
        del first_dispatch, first_operator, first_sealed, live_runtime, live_broker
        gc.collect()

        runtime = Runtime.at(runtime_path)
        broker, _sweeper, _ignored_socket = _build_broker(workspace_root, provider_home)
        broker_accepts.clear()

        async def counting_handle(reader, writer):
            broker_accepts.append("accept")
            return await broker.handle_connection(reader, writer)

        server = await asyncio.start_unix_server(
            counting_handle,
            path=str(socket_path),
            limit=4 * 1024 * 1024,
        )
        try:
            _with_fake_reply(
                monkeypatch,
                _plan_reply(runtime, root_id, crash_attempt_id),
                requests=app_server_requests,
            )
            operator, sealed = _bind_supervisors(runtime, socket_path)
            original_sealed_start = sealed.start_cycle_job

            async def counting_sealed_start(job_id: str, *, command_id: str):
                sealed_starts.append((job_id, command_id))
                return await original_sealed_start(job_id, command_id=command_id)

            sealed.start_cycle_job = counting_sealed_start  # type: ignore[method-assign]

            def dispatch(job_id: str, command_id: str):
                return asyncio.run_coroutine_threadsafe(
                    _start_via_production_route(
                        operator, sealed, runtime, job_id, command_id
                    ),
                    loop,
                ).result(timeout=30)

            replay = await asyncio.to_thread(
                CooCycle(runtime, dispatcher=dispatch).run_once,
                root_id,
            )
            assert replay.action == "DISPATCHED"
            assert replay.command_id == planner_command
            assert replay.receipt["attempt"]["attempt_id"] == crash_attempt_id
            assert runtime.jobs.get_job(planner_id).attempt_count == 1
            assert len(runtime.attempts.list_attempts(planner_id)) == 1
            assert broker_accepts, "planner hop must accept on the Worker Broker socket"
            assert "initialize" in app_server_requests
            assert app_server_requests.count("initialize") == 1
            planner_binding = _assert_hop_identity(
                runtime,
                command_id=planner_command,
                attempt_id=crash_attempt_id,
                job_id=planner_id,
            )
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

        planner = runtime.jobs.get_job(planner_id)
        assert planner is not None and planner.status is JobStatus.COMPLETED
        attempt = runtime.attempts.get_attempt(crash_attempt_id)
        assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
        seal = runtime.events.get_event_by_command_id(
            f"orchestration-result-seal:{crash_attempt_id}"
        )
        assert seal is not None
        materialization = runtime.events.get_event_by_command_id(
            f"ohf-op:start:{crash_attempt_id}"
        )
        assert materialization is not None
        assert materialization.attempt_id == crash_attempt_id
        envelope = seal.payload["result_envelope"]
        assert envelope["run_id"] == crash_attempt_id
        assert envelope["job_id"] == planner_id
        assert envelope["role_result"]["root_job_id"] == root_id
        assert planner_binding == runtime_binding_id_for(
            crash_attempt_id, _session_epoch_id(runtime, crash_attempt_id)
        )

        admitted = CooCycle(runtime).run_once(root_id)
        assert admitted.action == "PLAN_ADMITTED"
        work_id = admitted.receipt["work_job_ids"][0]
        work_command = f"coo-cycle:{root_id}:dispatch:{work_id}:attempt:1"

        with pytest.raises(
            StateConflict, match="App Server supervisor accepts only planner Jobs"
        ):
            await operator.start_cycle_job(work_id, command_id=work_command)

        with pytest.raises(SupervisorError, match="unimplemented surface"):
            await asyncio.to_thread(
                CooCycle(runtime, dispatcher=dispatch).run_once,
                root_id,
            )
        work = runtime.jobs.get_job(work_id)
        assert work is not None
        assert work.attempt_count == 1
        work_attempt_id = str(work.current_attempt_id)
        assert sealed_starts == [(work_id, work_command)]
        work_binding = _assert_hop_identity(
            runtime,
            command_id=work_command,
            attempt_id=work_attempt_id,
            job_id=work_id,
        )
        assert work_binding == runtime_binding_id_for(
            work_attempt_id, f"sealed-worker:{work_attempt_id}"
        )
        # FINDING: work launch cannot complete hermetically. The sealed
        # supervisor claims via start_cycle_job then refuses the operator/MCP
        # profile at control_plane/executive_supervisor.py:1020-1022. The
        # operator supervisor refuses non-plan work at
        # control_plane/executive_operator_supervisor.py:808-809. Completing
        # work/review/root would require a second fake (sealed Codex process).
        # Review / aggregation / next-child therefore do not run.
        review_jobs = [
            job
            for job in runtime.jobs.list_jobs()
            if job.orchestration_role == "review"
        ]
        assert review_jobs == []
        aggregation_command = f"coo-cycle:{root_id}:aggregation-handoff:1"
        assert aggregation_command == f"coo-cycle:{root_id}:aggregation-handoff:1"
        assert runtime.events.get_event_by_command_id(aggregation_command) is None
        next_child_command = f"coo-cycle:{root_id}:dispatch:{root_id}:attempt:1"
        assert runtime.events.get_event_by_command_id(next_child_command) is None
        assert app_server_requests.count("initialize") == 1

    asyncio.run(scenario())


def test_w6b_checked_in_routes_do_not_dispatch_inert_cycle(tmp_path: Path) -> None:
    fixture = _native_fixture(tmp_path)
    routes = json.loads(
        (REPO_ROOT / "config" / "executive_worker_routes.json").read_text(
            encoding="utf-8"
        )
    )
    assert routes["production_armed"] is False
    created = CooCycle(fixture.runtime).run_once(fixture.root_id)
    assert created.action == "PLANNER_CREATED"
    blocked = CooCycle(fixture.runtime).run_once(fixture.root_id)
    assert blocked.action == "BLOCKED"
    assert blocked.receipt["reason"] == "exact_dispatch_unavailable"
    planner = fixture.runtime.jobs.get_job(str(created.selected_job_id))
    assert planner is not None
    assert planner.status is JobStatus.QUEUED
    assert fixture.runtime.attempts.list_attempts(planner.job_id) == []


def test_w6b_t2v2_crash_replay_preserves_per_work_step_placement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _native_fixture(tmp_path)
    runtime_path = fixture.runtime_path
    runtime = fixture.runtime
    root_id = fixture.root_id
    app_server_requests: list[str] = []

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        root = runtime.jobs.get_job(root_id)
        assert root is not None
        admitted_union = [
            {"provider_realm": "codex", "quota_class": "codex-coo-default"}
        ]
        assert root.constraints["work_placement_union"] == admitted_union
        created = CooCycle(runtime).run_once(root_id)
        assert created.action == "PLANNER_CREATED"
        planner_id = str(created.selected_job_id)
        operator, _sealed = _bind_supervisors(runtime, fixture.socket_path)

        def crash_run_claimed(self, _job, _lease):
            raise RuntimeError("simulated v2 planner crash")

        operator._run_claimed = crash_run_claimed.__get__(
            operator, type(operator)
        )

        def crashing_dispatch(job_id: str, command_id: str):
            return asyncio.run_coroutine_threadsafe(
                operator.start_cycle_job(job_id, command_id=command_id),
                loop,
            ).result(timeout=30)

        with pytest.raises(RuntimeError, match="simulated v2 planner crash"):
            await asyncio.to_thread(
                CooCycle(runtime, dispatcher=crashing_dispatch).run_once,
                root_id,
            )
        planner = runtime.jobs.get_job(planner_id)
        assert planner is not None and planner.attempt_count == 1
        attempt_id = str(planner.current_attempt_id)
        command_id = (
            f"coo-cycle:{root_id}:dispatch:{planner_id}:attempt:1"
        )

        fixture.runtime = None
        fixture.broker = None
        import gc

        gc.collect()
        replay_runtime = Runtime.at(runtime_path)
        replay_root = replay_runtime.jobs.get_job(root_id)
        assert replay_root is not None
        assert replay_root.constraints["work_placement_union"] == admitted_union
        plan = {
            "schema_version": "mastermind.execution_plan/v2",
            "root_job_id": root_id,
            "plan_attempt_id": attempt_id,
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "step-0",
                    "objective": "One replayed exact placement.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                    "placement": {
                        "provider_realm": "codex",
                        "quota_class": "codex-coo-default",
                    },
                },
                {
                    "ordinal": 1,
                    "step_id": "step-1",
                    "objective": "One replayed inherited placement.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                    "placement": {
                        "provider_realm": "codex",
                        "quota_class": "codex-coo-default",
                    },
                },
            ],
        }
        reply = _planner_result(root_id, attempt_id)
        reply["job_id"] = replay_runtime.attempts.get_attempt(attempt_id).job_id
        reply["role_result"] = plan
        _with_fake_reply(
            monkeypatch,
            _canonical_result(reply),
            requests=app_server_requests,
        )
        broker, _sweeper, socket_path = _build_broker(
            fixture.workspace_root,
            fixture.provider_home,
        )
        server = await asyncio.start_unix_server(
            broker.handle_connection,
            path=str(socket_path),
            limit=4 * 1024 * 1024,
        )
        try:
            replay_operator, _replay_sealed = _bind_supervisors(
                replay_runtime, socket_path
            )

            def dispatch(job_id: str, dispatch_command: str):
                return asyncio.run_coroutine_threadsafe(
                    replay_operator.start_cycle_job(
                        job_id, command_id=dispatch_command
                    ),
                    loop,
                ).result(timeout=30)

            outcome = await asyncio.to_thread(
                CooCycle(replay_runtime, dispatcher=dispatch).run_once,
                root_id,
            )
            assert outcome.action == "DISPATCHED"
            assert outcome.receipt["attempt"]["attempt_id"] == attempt_id
            admitted = CooCycle(replay_runtime).run_once(root_id)
            assert admitted.action == "PLAN_ADMITTED"
            work_ids = list(admitted.receipt["work_job_ids"])
            work = [replay_runtime.jobs.get_job(value) for value in work_ids]
            assert all(job is not None for job in work)
            assert [
                job.constraints["eligible_quota_classes"] for job in work if job
            ] == [["codex-coo-default"], ["codex-coo-default"]]
            replay_admission = replay_runtime.jobs.admit_cycle_plan(
                root_id,
                command_id=(
                    f"coo-cycle:{root_id}:admit-plan:{attempt_id}"
                ),
            )
            assert [job.job_id for job in replay_admission] == work_ids
            assert [
                replay_runtime.jobs.get_job(value)
                for value in work_ids
            ] == work
        finally:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)

    asyncio.run(scenario())
