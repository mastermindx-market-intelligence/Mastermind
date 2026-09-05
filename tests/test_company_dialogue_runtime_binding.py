from __future__ import annotations

import ast
import copy
import dataclasses
import inspect
from pathlib import Path
from types import MappingProxyType

import pytest

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_runtime import AttemptStatus, WorkerStatus
from control_plane.session_targets import RuntimeBinding
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    PARENT_SCHEMA_V2,
    TURN_WATCH_MODE_V1,
    build_parent_v2,
)

from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    BINDING_SCHEMA,
    BindingReason,
    BindingState,
    CompanyDialogueBindingError,
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
    require_company_dialogue_binding,
    resolve_company_dialogue_binding,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_TS = "1788000000.123456"
PROFILE_ID = "operator.appserver.readonly.company-dialogue.v1"
PROFILE_DIGEST = "a" * 64
POLICY_DIGEST = "b" * 64
PARENT_CREATED = "2026-08-31T22:00:00Z"
ATTEMPT_ID = "ATT-0123456789abcdef0123456789abcdef"
ROLLED_ATTEMPT_ID = "ATT-fedcba9876543210fedcba9876543210"


def identity() -> ExecutiveDelegationIdentity:
    return ExecutiveDelegationIdentity(
        job_id="JOB-200",
        root_job_id="JOB-100",
        operation_key="exec-job-200",
        session_ref="asd-session-exec-job-200",
    )


def commission() -> dict[str, str]:
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "c" * 40,
        "path": "research/operator-commission.md",
        "content_sha256": "d" * 64,
    }


def parent(*, operation_key: str | None = None, session_ref: str | None = None, created_at: str = PARENT_CREATED) -> dict:
    projected = identity()
    return build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": session_ref or projected.session_ref,
            "operation_key": operation_key or projected.operation_key,
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": created_at,
        }
    )


def runtime_binding(*, generation: int = 3, binding_id: str = "bind-worker-runtime-0001") -> RuntimeBinding:
    return RuntimeBinding(
        session_alias="EXECUTIVE-COO-A",
        binding_id=binding_id,
        binding_generation=generation,
        native_handle="provider-session-private-1",
        account_label="provider-realm-private-1",
        reasoning_surface="codex",
    )


def snapshot(
    *,
    attempt_id: str = ATTEMPT_ID,
    worker_id: str = "codex-worker-01",
    attempt_status: AttemptStatus = AttemptStatus.RUNNING,
    worker_status: WorkerStatus = WorkerStatus.BUSY,
    runtime: RuntimeBinding | None = None,
    parent_fingerprint: str | None = None,
    attested: bool = True,
    server_identity: str = SERVER_IDENTITY,
    server_version: str = SERVER_VERSION,
    tool_digest: str = TOOL_SCHEMA_DIGEST,
) -> CurrentWorkerDialogueSnapshot:
    exact_parent = parent()
    return CurrentWorkerDialogueSnapshot(
        root_job_id="JOB-100",
        job_id="JOB-200",
        attempt_id=attempt_id,
        worker_id=worker_id,
        attempt_status=attempt_status,
        worker_status=worker_status,
        execution_profile_id=PROFILE_ID,
        execution_profile_digest=PROFILE_DIGEST,
        capability_policy_digest=POLICY_DIGEST,
        runtime_binding=runtime or runtime_binding(),
        parent_fingerprint=parent_fingerprint or exact_parent["fingerprint"],
        company_dialogue_server_identity=server_identity,
        company_dialogue_server_version=server_version,
        company_dialogue_tool_schema_digest=tool_digest,
        company_dialogue_attested=attested,
    )


def caller(
    *,
    attempt_id: str = ATTEMPT_ID,
    worker_id: str = "codex-worker-01",
    runtime: RuntimeBinding | None = None,
    profile_id: str = PROFILE_ID,
    profile_digest: str = PROFILE_DIGEST,
    policy_digest: str = POLICY_DIGEST,
) -> WorkerDialogueCaller:
    return WorkerDialogueCaller(
        attempt_id=attempt_id,
        worker_id=worker_id,
        execution_profile_id=profile_id,
        execution_profile_digest=profile_digest,
        capability_policy_digest=policy_digest,
        runtime_binding=runtime or runtime_binding(),
    )


def resolve(*, current: CurrentWorkerDialogueSnapshot | None = None, actor: WorkerDialogueCaller | None = None, dialogue_parent: dict | None = None, thread_ts: str = THREAD_TS):
    return resolve_company_dialogue_binding(
        delegation_identity=identity(),
        dialogue_parent=dialogue_parent or parent(),
        thread_ts=thread_ts,
        current=current if current is not None else snapshot(),
        actor=actor if actor is not None else caller(),
    )


def test_exact_current_worker_receives_same_parent_context_and_current_attempt_actor() -> None:
    result = resolve()

    assert result.schema == BINDING_SCHEMA
    assert result.state is BindingState.RESOLVED
    assert result.reason is BindingReason.EXACT_CURRENT_WORKER
    assert result.binding is not None
    assert result.binding.work_ref == "WS:CHAIRMAN-CONTROL-ROOM"
    assert result.binding.commission_ref == commission()
    assert result.binding.session_ref == identity().session_ref
    assert result.binding.operation_key == identity().operation_key
    assert result.binding.watch_mode == TURN_WATCH_MODE_V1
    assert result.binding.thread_ts == THREAD_TS
    assert result.binding.actor_ref == {
        "kind": "worker_attempt",
        "job_id": "JOB-200",
        "attempt_id": ATTEMPT_ID,
        "worker_id": "codex-worker-01",
    }
    assert result.binding.applies_to == {
        "kind": "executive_attempt",
        "job_id": "JOB-200",
        "attempt_id": ATTEMPT_ID,
        "worker_id": "codex-worker-01",
    }
    assert result.binding.allowed_message_types == (
        "ACK",
        "BLOCKED",
        "DECISION_REQUEST",
        "PROGRESS",
        "RESULT",
    )
    assert result.binding.reply_to_message_key is None
    assert len(result.evidence_digest) == 64


def test_actual_runtime_minted_job_and_attempt_ids_resolve_public_binding() -> None:
    runtime_identity = ExecutiveDelegationIdentity(
        job_id="JOB-002",
        root_job_id="JOB-001",
        operation_key="exec-job-002",
        session_ref="asd-session-exec-job-002",
    )
    runtime_parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": runtime_identity.session_ref,
            "operation_key": runtime_identity.operation_key,
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": PARENT_CREATED,
        }
    )
    runtime_attempt = ATTEMPT_ID
    current = dataclasses.replace(
        snapshot(parent_fingerprint=runtime_parent["fingerprint"]),
        root_job_id=runtime_identity.root_job_id,
        job_id=runtime_identity.job_id,
        attempt_id=runtime_attempt,
    )
    actor = dataclasses.replace(caller(), attempt_id=runtime_attempt)

    result = resolve_company_dialogue_binding(
        delegation_identity=runtime_identity,
        dialogue_parent=runtime_parent,
        thread_ts=THREAD_TS,
        current=current,
        actor=actor,
    )

    assert result.state is BindingState.RESOLVED
    assert result.reason is BindingReason.EXACT_CURRENT_WORKER
    assert result.binding is not None
    assert result.binding.actor_ref == {
        "kind": "worker_attempt",
        "job_id": "JOB-002",
        "attempt_id": runtime_attempt,
        "worker_id": "codex-worker-01",
    }


@pytest.mark.parametrize(
    ("job_id", "root_job_id", "attempt_id"),
    [
        ("JOB-02", "JOB-001", ATTEMPT_ID),
        ("JOB-002", "JOB-01", ATTEMPT_ID),
        ("JOB-002", "JOB-001", "ATT-0123456789abcdef0123456789abcdeg"),
        ("JOB-002", "JOB-001", "ATT-0123456789ABCDEF0123456789ABCDEF"),
    ],
)
def test_malformed_runtime_ids_remain_closed(
    job_id: str,
    root_job_id: str,
    attempt_id: str,
) -> None:
    runtime_identity = dataclasses.replace(
        ExecutiveDelegationIdentity(
            job_id="JOB-002",
            root_job_id="JOB-001",
            operation_key="exec-job-002",
            session_ref="asd-session-exec-job-002",
        ),
        job_id=job_id,
        root_job_id=root_job_id,
    )
    runtime_parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:CHAIRMAN-CONTROL-ROOM",
            "commission_ref": commission(),
            "session_ref": runtime_identity.session_ref,
            "operation_key": runtime_identity.operation_key,
            "watch_mode": TURN_WATCH_MODE_V1,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": PARENT_CREATED,
        }
    )
    current = dataclasses.replace(
        snapshot(parent_fingerprint=runtime_parent["fingerprint"]),
        job_id=job_id,
        root_job_id=root_job_id,
        attempt_id=attempt_id,
    )
    actor = dataclasses.replace(caller(), attempt_id=attempt_id)

    result = resolve_company_dialogue_binding(
        delegation_identity=runtime_identity,
        dialogue_parent=runtime_parent,
        thread_ts=THREAD_TS,
        current=current,
        actor=actor,
    )

    assert result.state is BindingState.REFUSED
    assert result.reason is BindingReason.CURRENT_JOB_MISMATCH
    assert result.binding is None


def test_same_parent_survives_attempt_rollover_but_stale_previous_attempt_cannot_post() -> None:
    p = parent()
    current = snapshot(attempt_id=ROLLED_ATTEMPT_ID, worker_id="codex-worker-02")
    current_actor = caller(attempt_id=ROLLED_ATTEMPT_ID, worker_id="codex-worker-02")

    accepted = resolve(current=current, actor=current_actor, dialogue_parent=p)
    assert accepted.state is BindingState.RESOLVED
    assert accepted.binding is not None
    assert accepted.binding.session_ref == p["session_ref"]
    assert accepted.binding.operation_key == p["operation_key"]
    assert accepted.binding.commission_ref == p["commission_ref"]
    assert accepted.binding.actor_ref["attempt_id"] == ROLLED_ATTEMPT_ID
    assert accepted.binding.actor_ref["worker_id"] == "codex-worker-02"

    stale = resolve(current=current, actor=caller(), dialogue_parent=p)
    assert stale.state is BindingState.REFUSED
    assert stale.reason is BindingReason.ACTOR_ATTEMPT_MISMATCH
    assert stale.binding is None


@pytest.mark.parametrize(
    ("actor", "reason"),
    [
        (caller(worker_id="other-worker"), BindingReason.ACTOR_WORKER_MISMATCH),
        (caller(profile_id="operator.other.v1"), BindingReason.ACTOR_PROFILE_MISMATCH),
        (caller(profile_digest="e" * 64), BindingReason.ACTOR_PROFILE_MISMATCH),
        (caller(policy_digest="f" * 64), BindingReason.ACTOR_PROFILE_MISMATCH),
        (
            caller(runtime=runtime_binding(generation=4)),
            BindingReason.ACTOR_RUNTIME_BINDING_MISMATCH,
        ),
        (
            caller(runtime=runtime_binding(binding_id="bind-worker-runtime-0002")),
            BindingReason.ACTOR_RUNTIME_BINDING_MISMATCH,
        ),
    ],
)
def test_actor_cannot_impersonate_current_runtime(actor: WorkerDialogueCaller, reason: BindingReason) -> None:
    result = resolve(actor=actor)
    assert result.state is BindingState.REFUSED
    assert result.reason is reason
    assert result.binding is None


@pytest.mark.parametrize(
    "status",
    [
        AttemptStatus.CANCEL_REQUESTED,
        AttemptStatus.RATE_LIMITED,
        AttemptStatus.FAILED,
        AttemptStatus.LOST,
        AttemptStatus.COMPLETED,
        AttemptStatus.CANCELLED,
    ],
)
def test_inactive_attempt_cannot_receive_dialogue_binding(status: AttemptStatus) -> None:
    result = resolve(current=snapshot(attempt_status=status))
    assert result.state is BindingState.REFUSED
    assert result.reason is BindingReason.CURRENT_ATTEMPT_INACTIVE
    assert result.binding is None


@pytest.mark.parametrize(
    "status",
    [
        WorkerStatus.AVAILABLE,
        WorkerStatus.DRAINING,
        WorkerStatus.RATE_LIMITED,
        WorkerStatus.OFFLINE,
        WorkerStatus.ERROR,
    ],
)
def test_non_busy_worker_cannot_receive_dialogue_binding(status: WorkerStatus) -> None:
    result = resolve(current=snapshot(worker_status=status))
    assert result.state is BindingState.REFUSED
    assert result.reason is BindingReason.CURRENT_WORKER_INACTIVE
    assert result.binding is None


def test_unknown_current_runtime_is_typed_unknown_not_fallback() -> None:
    result = resolve_company_dialogue_binding(
        delegation_identity=identity(),
        dialogue_parent=parent(),
        thread_ts=THREAD_TS,
        current=None,
        actor=caller(),
    )
    assert result.state is BindingState.UNKNOWN
    assert result.reason is BindingReason.CURRENT_RUNTIME_UNAVAILABLE
    assert result.binding is None


@pytest.mark.parametrize(
    "mutation",
    ["operation", "session", "parent_fingerprint", "job", "root"],
)
def test_dialogue_and_executive_identity_must_join_exactly(mutation: str) -> None:
    p = parent()
    current = snapshot()
    projected = identity()
    if mutation == "operation":
        p = parent(operation_key="exec-job-201")
    elif mutation == "session":
        p = parent(session_ref="asd-session-exec-job-201")
    elif mutation == "parent_fingerprint":
        current = dataclasses.replace(current, parent_fingerprint="f" * 64)
    elif mutation == "job":
        projected = dataclasses.replace(projected, job_id="JOB-201")
    else:
        projected = dataclasses.replace(projected, root_job_id="JOB-101")

    result = resolve_company_dialogue_binding(
        delegation_identity=projected,
        dialogue_parent=p,
        thread_ts=THREAD_TS,
        current=current,
        actor=caller(),
    )
    assert result.state is BindingState.REFUSED
    assert result.reason in {
        BindingReason.DIALOGUE_IDENTITY_MISMATCH,
        BindingReason.DIALOGUE_PARENT_STALE,
        BindingReason.CURRENT_JOB_MISMATCH,
    }
    assert result.binding is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"company_dialogue_attested": False}, BindingReason.CAPABILITY_NOT_ATTESTED),
        (
            {"company_dialogue_server_identity": "other-server"},
            BindingReason.CAPABILITY_NOT_ATTESTED,
        ),
        (
            {"company_dialogue_server_version": "2.0.0"},
            BindingReason.CAPABILITY_NOT_ATTESTED,
        ),
        (
            {"company_dialogue_tool_schema_digest": "f" * 64},
            BindingReason.CAPABILITY_NOT_ATTESTED,
        ),
    ],
)
def test_exact_company_dialogue_capability_must_be_attested(changes: dict, reason: BindingReason) -> None:
    result = resolve(current=dataclasses.replace(snapshot(), **changes))
    assert result.state is BindingState.REFUSED
    assert result.reason is reason
    assert result.binding is None


@pytest.mark.parametrize("thread_ts", ["", "1788000000", "abc.123456", "1788000000.1", "1788000000.1234567"])
def test_thread_identity_is_trusted_but_still_closed(thread_ts: str) -> None:
    result = resolve(thread_ts=thread_ts)
    assert result.state is BindingState.REFUSED
    assert result.reason is BindingReason.THREAD_INVALID
    assert result.binding is None


def test_malformed_parent_is_refused_without_exception_leakage() -> None:
    malformed = copy.deepcopy(parent())
    malformed["commission_ref"]["content_sha256"] = "not-a-digest"
    result = resolve(dialogue_parent=malformed)
    assert result.state is BindingState.REFUSED
    assert result.reason is BindingReason.DIALOGUE_PARENT_INVALID
    assert result.binding is None


def test_require_re_resolves_and_raises_fixed_typed_error() -> None:
    with pytest.raises(CompanyDialogueBindingError) as caught:
        require_company_dialogue_binding(
            delegation_identity=identity(),
            dialogue_parent=parent(),
            thread_ts=THREAD_TS,
            current=snapshot(attempt_id=ROLLED_ATTEMPT_ID),
            actor=caller(),
        )
    assert str(caught.value) == "company dialogue binding refused: REFUSED/ACTOR_ATTEMPT_MISMATCH"
    assert caught.value.resolution.reason is BindingReason.ACTOR_ATTEMPT_MISMATCH


def test_binding_maps_are_deeply_read_only_and_resolution_leaks_no_native_identity() -> None:
    result = resolve()
    assert result.binding is not None
    assert isinstance(result.binding.actor_ref, MappingProxyType)
    assert isinstance(result.binding.commission_ref, MappingProxyType)
    assert isinstance(result.binding.applies_to, MappingProxyType)
    with pytest.raises(TypeError):
        result.binding.actor_ref["worker_id"] = "forged"  # type: ignore[index]
    rendered = repr(result)
    assert "provider-session-private-1" not in rendered
    assert "provider-realm-private-1" not in rendered


def test_evidence_digest_excludes_clock_and_private_runtime_labels_but_binds_generation() -> None:
    first = resolve(dialogue_parent=parent(created_at="2026-08-31T22:00:00Z"))
    second = resolve(dialogue_parent=parent(created_at="2026-08-31T22:00:01Z"))
    assert first.evidence_digest == second.evidence_digest

    moved_runtime = runtime_binding(generation=4)
    moved = resolve(
        current=snapshot(runtime=moved_runtime),
        actor=caller(runtime=moved_runtime),
    )
    assert moved.evidence_digest != first.evidence_digest


def test_caller_identity_has_no_thread_target_or_authority_fields() -> None:
    assert set(WorkerDialogueCaller.__dataclass_fields__) == {
        "attempt_id",
        "worker_id",
        "execution_profile_id",
        "execution_profile_digest",
        "capability_policy_digest",
        "runtime_binding",
    }
    signature = inspect.signature(resolve_company_dialogue_binding)
    assert "channel" not in signature.parameters
    assert "provider" not in signature.parameters
    assert "account" not in signature.parameters
    assert "authority" not in signature.parameters


def test_module_is_pure_storeless_and_has_no_transport_or_lifecycle_mutation() -> None:
    path = ROOT / "integrations" / "slack_agent_dialogue" / "company_dialogue_runtime_binding.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports.isdisjoint(
        {"sqlite3", "socket", "subprocess", "requests", "httpx", "mcp", "slack_sdk"}
    )
    source = path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_job(",
        "claim_job(",
        "requeue_job(",
        "send_message(",
        "call_service(",
        "retry",
        "failover",
        "open(",
        "write_text(",
        "write_bytes(",
    ):
        assert forbidden not in source


def test_resolver_stays_owned_by_agent_dialogue_and_reuses_shared_id_contracts() -> None:
    assert not (ROOT / "control_plane" / "company_dialogue_runtime_binding.py").exists()
    path = ROOT / "integrations" / "slack_agent_dialogue" / "company_dialogue_runtime_binding.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wake_event_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "control_plane.wake_events"
        for alias in node.names
    }
    assert wake_event_names == {"ATTEMPT_ID_RE", "JOB_ID_RE"}

    allowed_integration_imports = {
        "dialogue_source_resolution.py": {
            (
                "integrations.slack_agent_dialogue.turn_watcher",
                "_canonical_identity",
            ),
        },
        "executive_dialogue_observation.py": {
            (
                "integrations.slack_agent_dialogue.contract_v2",
                "validate_message_v2",
            ),
        },
        "executive_service.py": {
            ("integrations.slack_agent_dialogue.turn_watcher", "TurnAction"),
            ("integrations.slack_agent_dialogue.turn_watcher", "TurnRoutingFacts"),
            ("integrations.slack_agent_dialogue.turn_watcher", "classify_turn"),
        },
    }
    for control_path in sorted((ROOT / "control_plane").glob("*.py")):
        control_tree = ast.parse(control_path.read_text(encoding="utf-8"))
        observed = {
            (node.module, alias.name)
            for node in ast.walk(control_tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("integrations.")
            for alias in node.names
        }
        direct = {
            alias.name
            for node in ast.walk(control_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name.startswith("integrations.")
        }
        assert direct == set(), control_path
        assert observed == allowed_integration_imports.get(control_path.name, set()), (
            control_path,
            observed,
        )
