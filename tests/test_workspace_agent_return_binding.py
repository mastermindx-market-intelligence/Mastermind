"""Contracts for stateless Workspace Agent current-binding resolution."""
from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER,
    DialogueCandidateReference,
)
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.session_targets import RuntimeBinding
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
    require_company_dialogue_binding,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    build_parent_v2,
)
from integrations.slack_agent_dialogue.engine_v2 import DiscoveredDialogueParent
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveObservationClientError,
    ResolvedDialogueObservation,
)
from integrations.workspace_agent_return import (
    WorkspaceCandidateReturnGateway,
    WorkspaceReturnTicketCodec,
)
from integrations.workspace_agent_return_binding import (
    MAX_DISCOVERED_PARENTS,
    WorkspaceCurrentBindingError,
    WorkspaceOperationBindingResolver,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "integrations/workspace_agent_return_binding.py"
THREAD_TS = "1788000000.123456"
OPERATION = "exec-job-200"
SESSION = "asd-session-exec-job-200"
ATTEMPT = "ATT-0123456789abcdef0123456789abcdef"
PROFILE = "operator.appserver.readonly.company-dialogue.v1"
PROFILE_DIGEST = "a" * 64
POLICY_DIGEST = "b" * 64
TICKET_KEY = b"k" * 32
NOW = 1790000000000


def _parent(*, operation_key: str = OPERATION) -> dict:
    return build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:WORKSPACE-AGENT-PROGRAM",
            "commission_ref": {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "c" * 40,
                "path": "research/workspace-agent-canary.md",
                "content_sha256": "d" * 64,
            },
            "session_ref": SESSION,
            "operation_key": operation_key,
            "watch_mode": None,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": "2026-09-20T00:00:00Z",
        }
    )


def _runtime_binding() -> RuntimeBinding:
    return RuntimeBinding(
        session_alias="EXECUTIVE-COO-A",
        binding_id="bind-workspace-return-0001",
        binding_generation=3,
        native_handle=None,
        account_label=None,
        reasoning_surface="codex",
    )


def _current(parent: dict | None = None) -> CurrentWorkerDialogueSnapshot:
    exact_parent = parent or _parent()
    return CurrentWorkerDialogueSnapshot(
        root_job_id="JOB-100",
        job_id="JOB-200",
        attempt_id=ATTEMPT,
        worker_id="codex-worker-01",
        attempt_status=AttemptStatus.RUNNING,
        worker_status=WorkerStatus.BUSY,
        execution_profile_id=PROFILE,
        execution_profile_digest=PROFILE_DIGEST,
        capability_policy_digest=POLICY_DIGEST,
        runtime_binding=_runtime_binding(),
        parent_fingerprint=exact_parent["fingerprint"],
        company_dialogue_server_identity=SERVER_IDENTITY,
        company_dialogue_server_version=SERVER_VERSION,
        company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
        company_dialogue_attested=True,
    )


def _actor() -> WorkerDialogueCaller:
    return WorkerDialogueCaller(
        attempt_id=ATTEMPT,
        worker_id="codex-worker-01",
        execution_profile_id=PROFILE,
        execution_profile_digest=PROFILE_DIGEST,
        capability_policy_digest=POLICY_DIGEST,
        runtime_binding=_runtime_binding(),
    )


def _identity(operation_key: str = OPERATION) -> ExecutiveDelegationIdentity:
    return ExecutiveDelegationIdentity(
        job_id="JOB-200",
        root_job_id="JOB-100",
        operation_key=operation_key,
        session_ref=SESSION,
    )


def _observation(parent: dict | None = None) -> ResolvedDialogueObservation:
    exact_parent = parent or _parent()
    current = _current(exact_parent)
    actor = _actor()
    return ResolvedDialogueObservation(
        state="RESOLVED",
        mode=ACTIVE_CURRENT_WORKER,
        dialogue_parent=copy.deepcopy(exact_parent),
        thread_ts=THREAD_TS,
        delegation_identity=_identity(str(exact_parent["operation_key"])),
        candidate=DialogueCandidateReference(
            mode=ACTIVE_CURRENT_WORKER,
            root_job_id=current.root_job_id,
            job_id=current.job_id,
            attempt_id=current.attempt_id,
            worker_id=current.worker_id,
            evidence_digest="e" * 64,
        ),
        target_bindings={"coo": None, "ceo": None},
        current_worker=current,
        actor=actor,
    )


class Discovery:
    def __init__(self, values=(), *, error: Exception | None = None):
        self.values = tuple(values)
        self.error = error
        self.calls: list[int] = []

    async def discover_validated_parents(self, *, maximum: int):
        self.calls.append(maximum)
        if self.error is not None:
            raise self.error
        return self.values


class Observation:
    def __init__(self, value=None, *, error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls: list[tuple[dict, str]] = []

    async def resolve(self, *, parent, thread_ts):
        self.calls.append((copy.deepcopy(dict(parent)), thread_ts))
        if self.error is not None:
            raise self.error
        return self.value


def _resolver(*, discovered=None, observed=None):
    parent = _parent()
    discovery = Discovery(
        discovered
        if discovered is not None
        else (DiscoveredDialogueParent(thread_ts=THREAD_TS, parent=parent),)
    )
    observation = Observation(observed if observed is not None else _observation(parent))
    return (
        WorkspaceOperationBindingResolver(
            parent_discovery=discovery,
            executive_observation=observation,
        ),
        discovery,
        observation,
    )


@pytest.mark.asyncio
async def test_exact_single_parent_reuses_existing_current_binding_owner():
    resolver, discovery, observation = _resolver()
    binding = await resolver.resolve(OPERATION)

    assert discovery.calls == [MAX_DISCOVERED_PARENTS]
    assert observation.calls == [(_parent(), THREAD_TS)]
    assert binding.operation_key == OPERATION
    assert binding.session_ref == SESSION
    assert binding.thread_ts == THREAD_TS
    assert binding.actor_ref == {
        "kind": "worker_attempt",
        "job_id": "JOB-200",
        "attempt_id": ATTEMPT,
        "worker_id": "codex-worker-01",
    }
    assert binding.applies_to == {
        "kind": "executive_attempt",
        "job_id": "JOB-200",
        "attempt_id": ATTEMPT,
        "worker_id": "codex-worker-01",
    }


@pytest.mark.asyncio
async def test_no_match_or_duplicate_match_refuses_before_executive_observation():
    other = _parent(operation_key="exec-job-201")
    exact = _parent()
    for discovered in (
        (DiscoveredDialogueParent(thread_ts=THREAD_TS, parent=other),),
        (
            DiscoveredDialogueParent(thread_ts=THREAD_TS, parent=exact),
            DiscoveredDialogueParent(
                thread_ts="1788000001.123456",
                parent=copy.deepcopy(exact),
            ),
        ),
    ):
        resolver, _, observation = _resolver(discovered=discovered)
        with pytest.raises(WorkspaceCurrentBindingError, match="BINDING_UNAVAILABLE"):
            await resolver.resolve(OPERATION)
        assert observation.calls == []


@pytest.mark.asyncio
async def test_discovery_and_observation_fail_closed_without_provider_text():
    for resolver in (
        WorkspaceOperationBindingResolver(
            parent_discovery=Discovery(error=RuntimeError("SECRET_DISCOVERY")),
            executive_observation=Observation(),
        ),
        WorkspaceOperationBindingResolver(
            parent_discovery=Discovery(
                (
                    DiscoveredDialogueParent(
                        thread_ts=THREAD_TS,
                        parent=_parent(),
                    ),
                )
            ),
            executive_observation=Observation(
                error=ExecutiveObservationClientError("TRANSPORT_UNAVAILABLE")
            ),
        ),
    ):
        with pytest.raises(WorkspaceCurrentBindingError) as caught:
            await resolver.resolve(OPERATION)
        assert str(caught.value) == "BINDING_UNAVAILABLE"
        assert "SECRET" not in repr(caught.value)


@pytest.mark.asyncio
async def test_terminal_or_mismatched_observation_is_not_a_return_target():
    exact = _observation()
    bad_values = (
        None,
        copy.deepcopy(exact),
    )
    object.__setattr__(bad_values[1], "mode", "TERMINAL_RESULT")
    for value in bad_values:
        resolver, _, _ = _resolver(observed=value)
        with pytest.raises(WorkspaceCurrentBindingError, match="BINDING_UNAVAILABLE"):
            await resolver.resolve(OPERATION)


@pytest.mark.asyncio
async def test_current_worker_drift_is_revalidated_by_existing_binding_owner():
    parent = _parent()
    observation = _observation(parent)
    drifted = copy.deepcopy(observation.current_worker)
    assert drifted is not None
    drifted = type(drifted)(
        **{
            **drifted.__dict__,
            "company_dialogue_attested": False,
        }
    )
    object.__setattr__(observation, "current_worker", drifted)
    resolver, _, _ = _resolver(observed=observation)

    with pytest.raises(WorkspaceCurrentBindingError, match="BINDING_UNAVAILABLE"):
        await resolver.resolve(OPERATION)


class RecordingService:
    def __init__(self):
        self.calls = []

    async def __call__(self, socket_path, request):
        self.calls.append((socket_path, copy.deepcopy(request)))
        message = request["args"]["message"]
        return {
            "ok": True,
            "result": {
                "action": "POSTED",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "message_ts": "1790000000.111111",
                "duplicate_timestamps": [],
                "thread_ts": request["args"]["thread_ts"],
                "parent_author_user_id": "U0RELAY001",
                "parent_fingerprint": _parent()["fingerprint"],
            },
        }


@pytest.mark.asyncio
async def test_candidate_gateway_accepts_async_current_binding_resolver_once(tmp_path):
    resolver, discovery, observation = _resolver()
    binding = await resolver.resolve(OPERATION)
    codec = WorkspaceReturnTicketCodec(TICKET_KEY)
    return_ref = codec.mint(
        binding=binding,
        ticket_id="wr-current-binding-001",
        issued_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    service = RecordingService()
    gateway = WorkspaceCandidateReturnGateway(
        codec=codec,
        binding_resolver=resolver,
        socket_path=tmp_path / "dialogue.sock",
        clock_ms=lambda: NOW + 1,
        utc_now=lambda: "2026-09-20T00:00:01Z",
        service_call=service,
    )

    before_discovery = len(discovery.calls)
    before_observation = len(observation.calls)
    result = await gateway.call(
        {
            "return_ref": return_ref,
            "status": "PASS",
            "result": "Bounded candidate from the Workspace supervisor.",
        }
    )

    assert result["ok"] is True
    assert result["state"] == "CANDIDATE_RECORDED"
    assert result["accepted"] is False
    assert result["wake_acknowledged"] is False
    assert len(discovery.calls) == before_discovery + 1
    assert len(observation.calls) == before_observation + 1
    assert len(service.calls) == 1
    _, request = service.calls[0]
    assert request["args"]["thread_ts"] == THREAD_TS
    assert request["args"]["message"]["applies_to"]["attempt_id"] == ATTEMPT


def test_resolver_source_has_no_new_state_or_effect_plane():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden = {
        "sqlite3",
        "subprocess",
        "keyring",
        "control_plane.executive_runtime",
        "control_plane.wake_dispatcher",
        "control_plane.wake_transport",
    }
    assert not (imports & forbidden)
    source = MODULE.read_text(encoding="utf-8")
    for forbidden_text in (
        "CREATE TABLE",
        "INSERT INTO",
        "UPDATE ",
        "requests.",
        "httpx.",
        "post_message",
        "send_message",
        "trigger_once",
    ):
        assert forbidden_text not in source
