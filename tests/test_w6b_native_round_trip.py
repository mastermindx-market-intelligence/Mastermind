"""Hermetic W6-B native one-child Executive round trip."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.codex_worker import BinaryAttestation
from control_plane.executive_agent_capabilities import (
    app_server_security_config_digest,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import (
    parse_and_validate_envelope,
    RawRoleResultObservation,
    RESULT_SCHEMA,
    canonical_bytes as result_canonical_bytes,
    canonical_digest as result_digest,
)
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    TurnStartObservation,
    WorkspaceIdentity,
)
from control_plane.executive_worker_broker import (
    BrokerPolicy,
    ExecutiveWorkerBroker,
    PeerCredentials,
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


class _SealedWorker:
    def __init__(self) -> None:
        self.binary = BinaryAttestation(
            path="/fixture/codex",
            real_path="/fixture/codex",
            version="0.147.0",
            sha256="a" * 64,
            team_identifier="2DC432GLL2",
            size=1,
            device=1,
            inode=1,
            mode=0o555,
            uid=0,
            gid=0,
            mtime_ns=1,
        )


@dataclass
class _NativeFixture:
    runtime: Runtime
    root_id: str
    broker: ExecutiveWorkerBroker
    peer: PeerCredentials
    sweeper: _PassingSweeper
    socket_path: Path
    provider_home: Path
    base_sha: str


def _python_digest() -> str:
    return hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()


def _orchestration_profile(
    fixture: _NativeFixture,
    dispatch: OrchestrationDispatchOutcome,
) -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id=str(dispatch.attempt.worker_id),
        provider="codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity(
            workspace_path="/tmp/work",
            base_sha="b" * 40,
            device=1,
            inode=2,
            uid=os.getuid(),
            gid=os.getgid(),
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(dispatch.attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _orchestration_attestation(
    profile: RequestedExecutionProfile,
) -> ObservedHarnessAttestation:
    return ObservedHarnessAttestation(
        served_model=profile.requested_model,
        harness_version=profile.harness_version,
        harness_binary_digest=profile.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=profile.sandbox_policy,
        approval_state=profile.approval_policy,
        network_state=profile.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(
            worker_id=profile.worker_id, provider=profile.provider
        ),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )


def _complete_ohf_role(
    fixture: _NativeFixture,
    dispatch: OrchestrationDispatchOutcome,
    role_result: dict,
    *,
    identity_seed: int,
) -> tuple[dict, dict]:
    assert dispatch.lease_token is not None
    runtime = fixture.runtime
    harness = runtime.operator_harness
    attempt = dispatch.attempt
    job = runtime.jobs.get_job(attempt.job_id)
    assert job is not None and job.orchestration_role
    profile = _orchestration_profile(fixture, dispatch)
    sealed = harness.seal_operator_harness_attempt(
        attempt.attempt_id,
        fence_generation=attempt.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
    )
    start = OperationId(f"ohf-op:complete-{identity_seed}-start")
    epoch, generation = harness.reserve_start(
        sealed.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        operation_id=start,
    )
    process = ProcessIdentityObservation(
        identity_seed, identity_seed, f"start-{identity_seed}", "boot-test"
    )
    provider_session = f"SESSION-{identity_seed}"
    harness.bind_start_result(
        epoch=epoch,
        generation=generation,
        operation_id=start,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        provider_session_id=provider_session,
        process=process,
    )
    principal = OperatorPrincipalObservation(
        attempt_id=sealed.attempt_id,
        worker_id=str(sealed.worker_id),
        process_generation_id=generation.process_generation_id,
        provider_session_id=provider_session,
        process_identity={
            "pid": process.pid,
            "pgid": process.pgid,
            "process_start_identity": process.process_start_identity,
            "boot_id": process.boot_id,
        },
        os_principal_name=f"fixture-principal-{identity_seed}",
        os_principal_uid=identity_seed,
        provider_home_identity={
            "path": f"/tmp/phase1fc-codex-home-{identity_seed}",
            "device": identity_seed,
            "inode": identity_seed + 1,
            "uid": identity_seed,
            "gid": identity_seed,
            "mode": 0o700,
        },
        observed_at_ms=runtime.store.now_ms(),
    )
    harness.seal_attestation(
        generation=generation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        requested=profile,
        attestation=_orchestration_attestation(profile),
        principal_observation=principal,
    )
    turn_operation = OperationId(f"ohf-op:complete-{identity_seed}-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    native_turn = f"NATIVE-{identity_seed}"
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation(native_turn, True),
    )
    artifact_digest = hashlib.sha256(
        f"artifact-{identity_seed}".encode()
    ).hexdigest()
    harness.record_candidate_evidence(
        turn=turn,
        candidate=CandidateResult(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            artifact_digest,
            "typed fixture candidate",
        ),
        events=(),
        cursor=EventCursor(
            attempt.attempt_id,
            epoch.session_epoch_id,
            generation.process_generation_id,
            turn_id=turn.turn_id,
        ),
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "job_id": job.job_id,
        "run_id": attempt.attempt_id,
        "worker_id": str(attempt.worker_id),
        "role": job.orchestration_role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": "bounded typed fixture result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    canonical = result_canonical_bytes(envelope).decode("utf-8")
    parse_and_validate_envelope(
        canonical,
        expected_job_id=job.job_id,
        expected_run_id=attempt.attempt_id,
        expected_worker_id=str(attempt.worker_id),
        expected_role=job.orchestration_role,
        expected_root_job_id=str(job.root_job_id),
    )
    observation = RawRoleResultObservation(
        attempt_id=attempt.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id=provider_session,
        provider_native_turn_id=native_turn,
        provider_turn_artifact_digest=artifact_digest,
        canonical_result_json=canonical,
        canonical_result_digest=hashlib.sha256(
            canonical.encode()
        ).hexdigest(),
        canonical_result_byte_length=len(canonical.encode()),
    )
    seal = harness.seal_orchestration_role_result(
        turn=turn,
        observation=observation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    death = ReconcileObservation(
        process_liveness=ProcessLiveness.PROVEN_DEAD,
        observed_process=process,
        provider_session_reachable=True,
        provider_writer_state=ProviderWriterState.RELEASED,
        observed_provider_session_id=provider_session,
    )
    harness.record_graceful_stop(
        generation=generation,
        observation=death,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.abandon_epoch(
        epoch=epoch,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    terminal = {
        "schema_version": "mastermind.orchestration_terminal_receipt/v1",
        "status": "COMPLETED",
        "job_id": job.job_id,
        "attempt_id": attempt.attempt_id,
        "orchestration_role": job.orchestration_role,
        "execution_mode": "OPERATOR_HARNESS",
        "result_seal_command_id": f"orchestration-result-seal:{attempt.attempt_id}",
        "result_evidence": None,
        "result_envelope": envelope,
        "result_envelope_digest": result_digest(envelope),
        "artifact_receipt_digest": result_digest([]),
        "validation_receipt_digest": result_digest([]),
        "effective_grant_digest": attempt.effective_grant_digest,
    }
    terminal["terminal_evidence_digest"] = result_digest(terminal)
    runtime.attempts.complete_attempt(
        attempt.attempt_id,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        payload=terminal,
    )
    return seal, terminal


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


def _native_fixture(tmp_path: Path) -> _NativeFixture:
    workspace_root = tmp_path / "workspaces"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace_root, run_root, provider_home):
        path.mkdir(parents=True, mode=0o700)
    workspace, base_sha = _make_git_workspace(
        workspace_root, "w6b-root", "codex/w6b-fixture"
    )
    python = Path(sys.executable).resolve()
    fake_state = provider_home / "fake-app-server-state.json"
    (provider_home / "auth.json").write_text(
        "fixture marker, not a credential\n", encoding="utf-8"
    )
    (provider_home / "auth.json").chmod(0o600)
    router = ModelRouter.load()
    operator = router.model_aliases["coo.operator.readonly"]
    capability_profile = ExecutionCapabilityRegistry.load().resolve(
        operator.execution_profile_id
    )
    fake_mcp_projection = _FAKE_MCP_PROJECTION
    expected_config_digest = app_server_security_config_digest(fake_mcp_projection)
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
        run_root=run_root,
        provider_home=provider_home,
        allowed_supplementary_gids=frozenset(set(os.getgroups()) - {os.getegid()}),
    )
    sweeper = _PassingSweeper()
    broker = ExecutiveWorkerBroker(
        _SealedWorker(),
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

    runtime = Runtime.at(tmp_path / "runtime")
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
        root_id=str(receipt["job_id"]),
        broker=broker,
        peer=broker.peer_resolver(object()),
        sweeper=sweeper,
        socket_path=socket_path,
        provider_home=provider_home,
        base_sha=base_sha,
    )


def _plan_reply(fixture: _NativeFixture, attempt_id: str) -> str:
    value = _planner_result(fixture.root_id, attempt_id)
    value["job_id"] = fixture.runtime.attempts.get_attempt(attempt_id).job_id
    return _canonical_result(value)


def _with_fake_reply(fixture: _NativeFixture, monkeypatch, reply: str) -> None:
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


class _PromptSource:
    def _prompt(self, *_args):
        return "Return one sealed reviewed W6-B plan."


async def _dispatch_plan(
    fixture: _NativeFixture,
    server: asyncio.AbstractServer,
    *,
    worker_id: str | None = None,
) -> OrchestrationDispatchOutcome:
    client = WorkerBrokerClient(fixture.socket_path, timeout_seconds=15.0)
    supervisor = ExecutiveOperatorSupervisor(
        fixture.runtime,
        adapter_factory=lambda loader: RemoteCodexOperatorAdapter(
            client, turn_input_loader=loader
        ),
        prompt_source=_PromptSource(),
        instance_id="executive-coo-operator",
    )
    planner = fixture.runtime.jobs.get_job(fixture.root_id)
    assert planner is not None
    children = [
        job
        for job in fixture.runtime.jobs.list_jobs()
        if job.parent_job_id == fixture.root_id
    ]
    assert len(children) == 1
    planner = children[0]
    return await supervisor.start_cycle_job(
        planner.job_id,
        command_id=(
            f"coo-cycle:{fixture.root_id}:dispatch:{planner.job_id}:attempt:1"
        ),
    ) if worker_id is None else await supervisor.start_cycle_job(
        planner.job_id,
        command_id=(
            f"coo-cycle:{fixture.root_id}:dispatch:{planner.job_id}:attempt:1"
        ),
        worker_id=worker_id,
    )


def test_w6b_native_round_trip_and_crash_after_dispatch_replay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _native_fixture(tmp_path)
    dispatches: list[OrchestrationDispatchOutcome] = []

    def crash_after_dispatch(job_id: str, command_id: str):
        job = fixture.runtime.jobs.get_job(job_id)
        assert job is not None
        worker_id = (
            "worker-b"
            if job.orchestration_role == "review"
            else None
            if job.orchestration_role == "plan"
            else "worker-a"
        )
        quota_class = (
            None
            if job.orchestration_role == "plan"
            else "codex-coo-default"
        )
        outcome = fixture.runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker_id,
            quota_class=quota_class,
            lease_owner="executive-coo-operator",
        )
        assert outcome is not None
        dispatches.append(outcome)
        raise RuntimeError("simulated crash after dispatch")

    def dispatch_existing_attempt(job_id: str, command_id: str):
        job = fixture.runtime.jobs.get_job(job_id)
        assert job is not None
        worker_id = (
            "worker-b"
            if job.orchestration_role == "review"
            else None
            if job.orchestration_role == "plan"
            else "worker-a"
        )
        quota_class = (
            None
            if job.orchestration_role == "plan"
            else "codex-coo-default"
        )
        outcome = fixture.runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker_id,
            quota_class=quota_class,
            lease_owner="executive-coo-operator",
        )
        assert outcome is not None
        dispatches.append(outcome)
        return outcome

    async def scenario() -> None:
        cycle = CooCycle(fixture.runtime)
        created = cycle.run_once(fixture.root_id)
        assert created.action == "PLANNER_CREATED"
        planner_id = str(created.selected_job_id)
        assert created.command_id == f"coo-cycle:{fixture.root_id}:create-planner:0"

        crashing_cycle = CooCycle(
            fixture.runtime,
            dispatcher=crash_after_dispatch,
        )
        with pytest.raises(RuntimeError, match="simulated crash after dispatch"):
            crashing_cycle.run_once(fixture.root_id)
        planner = fixture.runtime.jobs.get_job(planner_id)
        assert planner is not None
        assert planner.attempt_count == 1
        crash_attempt_id = planner.current_attempt_id
        assert crash_attempt_id
        assert len(fixture.runtime.attempts.list_attempts(planner_id)) == 1

        replay = CooCycle(
            fixture.runtime,
            dispatcher=dispatch_existing_attempt,
        ).run_once(fixture.root_id)
        assert replay.action == "DISPATCHED"
        assert replay.command_id == (
            f"coo-cycle:{fixture.root_id}:dispatch:{planner_id}:attempt:1"
        )
        assert replay.receipt["attempt"]["attempt_id"] == crash_attempt_id
        assert fixture.runtime.jobs.get_job(planner_id).attempt_count == 1
        assert len(fixture.runtime.attempts.list_attempts(planner_id)) == 1

        # Return the same durable Attempt through the checked-in fake App Server.
        server = await asyncio.start_unix_server(
            fixture.broker.handle_connection,
            path=str(fixture.socket_path),
            limit=4 * 1024 * 1024,
        )
        try:
            _with_fake_reply(
                fixture,
                monkeypatch,
                _plan_reply(fixture, crash_attempt_id),
            )
            native = await asyncio.to_thread(
                lambda: asyncio.run(_dispatch_plan(fixture, server))
            )
        finally:
            server.close()
            await server.wait_closed()
            fixture.socket_path.unlink(missing_ok=True)

        assert native.outcome == "TERMINAL"
        assert native.attempt.attempt_id == crash_attempt_id
        assert native.command_id == replay.command_id
        planner = fixture.runtime.jobs.get_job(planner_id)
        assert planner is not None and planner.status is JobStatus.COMPLETED
        attempt = fixture.runtime.attempts.get_attempt(crash_attempt_id)
        assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
        seal = fixture.runtime.events.get_event_by_command_id(
            f"orchestration-result-seal:{crash_attempt_id}"
        )
        assert seal is not None
        materialization = fixture.runtime.events.get_event_by_command_id(
            f"ohf-op:start:{crash_attempt_id}"
        )
        assert materialization is not None
        assert materialization.attempt_id == crash_attempt_id
        binding = seal.payload["result_envelope"]
        assert binding["run_id"] == crash_attempt_id
        assert binding["job_id"] == planner_id
        assert binding["role_result"]["root_job_id"] == fixture.root_id

        admitted = CooCycle(fixture.runtime).run_once(fixture.root_id)
        assert admitted.action == "PLAN_ADMITTED"
        work_id = admitted.receipt["work_job_ids"][0]
        work_dispatched = CooCycle(
            fixture.runtime,
            dispatcher=dispatch_existing_attempt,
        ).run_once(fixture.root_id)
        assert work_dispatched.action == "DISPATCHED"
        assert work_dispatched.selected_job_id == work_id
        work_attempt_id = work_dispatched.receipt["attempt"]["attempt_id"]
        work_dispatch = dispatches[-1]
        assert work_attempt_id == work_dispatch.attempt.attempt_id
        plan_digest = result_digest(_planner_result(fixture.root_id, crash_attempt_id)["role_result"])
        work_body = {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": fixture.root_id,
            "plan_attempt_id": crash_attempt_id,
            "plan_digest": plan_digest,
            "plan_step_id": "step-1",
            "repair_round": 0,
            "artifacts": [],
            "evidence_digests": [],
        }
        work_seal, _ = _complete_ohf_role(
            fixture,
            work_dispatch,
            work_body,
            identity_seed=3102,
        )

        review_created = CooCycle(fixture.runtime).run_once(fixture.root_id)
        assert review_created.action == "REVIEW_CREATED"
        assert review_created.selected_job_id is not None
        review_id = str(review_created.selected_job_id)
        assert review_created.command_id == (
            f"coo-cycle:{fixture.root_id}:create-review:{work_id}:1"
        )
        review_dispatched = CooCycle(
            fixture.runtime,
            dispatcher=dispatch_existing_attempt,
        ).run_once(fixture.root_id)
        assert review_dispatched.action == "DISPATCHED"
        assert review_dispatched.selected_job_id == review_id
        review_dispatch = dispatches[-1]
        assert review_dispatch.attempt.attempt_id == (
            review_dispatched.receipt["attempt"]["attempt_id"]
        )
        review_body = {
            "schema_version": "mastermind.review_result/v1",
            "root_job_id": fixture.root_id,
            "plan_attempt_id": crash_attempt_id,
            "plan_digest": plan_digest,
            "plan_step_id": "step-1",
            "reviewed_job_id": work_id,
            "reviewed_attempt_id": work_dispatch.attempt.attempt_id,
            "reviewed_result_digest": work_seal["role_result_digest"],
            "repair_round": 0,
            "verdict": "approve",
            "evidence_digests": [],
            "findings": [],
        }
        _complete_ohf_role(
            fixture,
            review_dispatch,
            review_body,
            identity_seed=3103,
        )
        handoff = CooCycle(fixture.runtime).run_once(fixture.root_id)
        assert handoff.action == "HANDOFF_CREATED"
        next_child = CooCycle(
            fixture.runtime,
            dispatcher=dispatch_existing_attempt,
        ).run_once(fixture.root_id)
        assert next_child.action == "DISPATCHED"
        assert next_child.selected_job_id == fixture.root_id
        assert next_child.command_id == (
            f"coo-cycle:{fixture.root_id}:dispatch:{fixture.root_id}:attempt:1"
        )

        # Exact durable command/attempt identity across the native hop.
        claim = fixture.runtime.events.get_event_by_command_id(replay.command_id)
        assert claim is not None and claim.attempt_id == crash_attempt_id
        assert seal.attempt_id == crash_attempt_id
        assert materialization.attempt_id == crash_attempt_id
        assert fixture.runtime.jobs.get_job(work_id) is not None
        assert fixture.runtime.jobs.get_job(review_id) is not None

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
