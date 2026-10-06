from __future__ import annotations

import ast
import asyncio
import dataclasses
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCommitIntent,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
    PRINCIPAL_RUNTIME_EVENT_TYPE,
    PrincipalCommitObservationState,
    PrincipalDialogueRuntimeCommitOwner,
    PrincipalRuntimeFenceError,
)
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2


ROOT = Path(__file__).resolve().parents[1]
THREAD_TS = "1788000000.123456"
MESSAGE_KEY = "asd-principal-" + "a" * 32
REPLY_KEY = "asd-result-12345678"
WORK_REF = "WS:CLAUDE-CAPABILITY-HARDENING"
SESSION_REF = "asd-session-claudeprincipal0001"
OPERATION_KEY = "claude-capability-hardening-h6-b2"
D0 = "0" * 64
D1 = "1" * 64
D2 = "2" * 64


def commission() -> dict[str, str]:
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "a" * 40,
        "path": "docs/claude-capability-hardening.md",
        "content_sha256": "b" * 64,
    }


def runtime_child(tmp_path: Path):
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker(
        "worker-h6-b2",
        provider="fixture",
        account_label="fixture",
        worker_type="fixture",
        quota_classes={"default": []},
    )
    root = runtime.jobs.create_job(
        "H6 root",
        requested_authorities=["READ"],
    )
    child = runtime.jobs.create_job(
        "H6 live child",
        parent_job_id=root.job_id,
        requested_authorities=["READ"],
    )
    lease = runtime.attempts.claim_job(
        child.job_id,
        worker_id="worker-h6-b2",
        quota_class="default",
    )
    assert lease is not None
    current = runtime.jobs.get_job(child.job_id)
    assert current is not None
    return runtime, root, current, lease.attempt


def binding(root, child, attempt, **changes) -> DialogueBinding:
    values = {
        "actor_ref": {
            "kind": "executive_principal",
            "seat": "coo",
            "reasoning_surface": "claude-agent-sdk",
            "principal_binding_digest": D0,
            "mission_authority_ref": "authority:claude-coo-current",
            "authority_generation_digest": D1,
            "capability_profile_digest": D2,
            "root_job_id": root.job_id,
        },
        "work_ref": WORK_REF,
        "commission_ref": commission(),
        "session_ref": SESSION_REF,
        "operation_key": OPERATION_KEY,
        "watch_mode": "turn_watch_v1",
        "applies_to": {
            "kind": "executive_attempt",
            "job_id": child.job_id,
            "attempt_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
        },
        "thread_ts": THREAD_TS,
        "allowed_message_types": ("RULING", "CONTINUE", "STOP"),
        "reply_to_message_key": REPLY_KEY,
    }
    values.update(changes)
    return DialogueBinding(**values)


def principal_message(bound: DialogueBinding, **body_changes) -> dict:
    body = {
        "instruction": "Continue the next bounded phase.",
        "stop_condition": "Return one canonical result.",
        "scope_change": False,
    }
    body.update(body_changes)
    return build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": MESSAGE_KEY,
            "message_type": "CONTINUE",
            "work_ref": bound.work_ref,
            "commission_ref": bound.commission_ref,
            "session_ref": bound.session_ref,
            "actor_ref": bound.actor_ref,
            "reply_to_message_key": bound.reply_to_message_key,
            "applies_to": bound.applies_to,
            "summary": "COO continuation returned.",
            "body": body,
            "evidence_refs": [],
            "requires_response": False,
            "created_at": "2026-10-05T06:00:00Z",
        }
    )


def intent(bound: DialogueBinding, message: dict) -> PrincipalCommitIntent:
    actor = bound.actor_ref
    applies = bound.applies_to
    return PrincipalCommitIntent(
        schema="mastermind.company_dialogue_principal_commit_intent.v1",
        work_ref=bound.work_ref,
        session_ref=bound.session_ref,
        operation_key=bound.operation_key,
        thread_ts=bound.thread_ts,
        reply_to_message_key=str(bound.reply_to_message_key),
        message_key=message["message_key"],
        message_fingerprint=message["fingerprint"],
        message_type=message["message_type"],
        principal_binding_digest=actor["principal_binding_digest"],
        authority_generation_digest=actor["authority_generation_digest"],
        capability_profile_digest=actor["capability_profile_digest"],
        child_job_id=applies["job_id"],
        child_attempt_id=applies["attempt_id"],
        child_worker_id=applies["worker_id"],
    )


class Resolver:
    def __init__(self, value: DialogueBinding):
        self.value = value
        self.calls = 0

    def resolve(self) -> DialogueBinding:
        self.calls += 1
        return self.value


class ReadService:
    def __init__(self, messages: list[dict] | None = None, *, error: bool = False):
        self.messages = list(messages or [])
        self.error = error
        self.calls: list[dict] = []

    async def __call__(self, path: Path, request: dict, **kwargs):
        self.calls.append(request)
        assert kwargs == {}
        if self.error:
            raise RuntimeError("synthetic read failure")
        assert request["operation"] == "read_thread"
        return {
            "ok": True,
            "result": {
                "thread_ts": request["args"]["thread_ts"],
                "historical_messages": [],
                "messages": [
                    {"message": item}
                    for item in self.messages
                ],
                "mutated_count": 0,
            },
        }


def owner(runtime, resolver, service=None):
    return PrincipalDialogueRuntimeCommitOwner(
        runtime,
        resolver,
        socket_path=Path("/private/tmp/mastermind-agent-dialogue.sock"),
        service_call=service or ReadService(),
    )


def run(value):
    return asyncio.run(value)


def test_first_commit_fence_uses_existing_runtime_event_store_and_replay_refuses(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    subject = owner(runtime, Resolver(bound))

    receipt = subject.before_commit(request)
    assert receipt.intent_sha256 == request.digest()
    assert receipt.durable_ref.startswith("runtime-event:")

    events = runtime.events.list_events(
        aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
        aggregate_id=MESSAGE_KEY,
    )
    assert len(events) == 1
    assert events[0].event_type == PRINCIPAL_RUNTIME_EVENT_TYPE
    assert events[0].job_id == child.job_id
    assert events[0].attempt_id == attempt.attempt_id
    assert events[0].worker_id == attempt.worker_id

    with pytest.raises(
        PrincipalRuntimeFenceError,
        match="COMMIT may already have occurred",
    ):
        subject.before_commit(request)

    assert len(
        runtime.events.list_events(
            aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
            aggregate_id=MESSAGE_KEY,
        )
    ) == 1


def test_binding_drift_refuses_before_runtime_event(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    resolver = Resolver(
        dataclasses.replace(
            bound,
            actor_ref={
                **dict(bound.actor_ref),
                "authority_generation_digest": "f" * 64,
            },
        )
    )

    with pytest.raises(PrincipalRuntimeFenceError, match="binding changed"):
        owner(runtime, resolver).before_commit(request)

    assert runtime.events.list_events(
        aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
        aggregate_id=MESSAGE_KEY,
    ) == []


def test_expired_attempt_refuses_inside_runtime_write_transaction(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE attempts SET lease_expires_at_ms=0 WHERE attempt_id=?",
            (attempt.attempt_id,),
        )

    with pytest.raises(PrincipalRuntimeFenceError, match="no longer exact/current"):
        owner(runtime, Resolver(bound)).before_commit(request)

    assert runtime.events.list_events(
        aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
        aggregate_id=MESSAGE_KEY,
    ) == []


def test_changed_semantics_under_same_message_key_cannot_replace_fence(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    first_message = principal_message(bound)
    first = intent(bound, first_message)
    subject = owner(runtime, Resolver(bound))
    subject.before_commit(first)

    changed_message = principal_message(
        bound,
        instruction="Changed instruction.",
    )
    changed = intent(bound, changed_message)
    assert changed.message_key == first.message_key
    assert changed.message_fingerprint != first.message_fingerprint

    with pytest.raises(PrincipalRuntimeFenceError, match="identity conflicts"):
        subject.before_commit(changed)

    assert len(
        runtime.events.list_events(
            aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
            aggregate_id=MESSAGE_KEY,
        )
    ) == 1


def test_reconcile_without_fence_is_not_applied_and_performs_no_carrier_read(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    service = ReadService()
    subject = owner(runtime, Resolver(bound), service)

    result = run(subject.reconcile(MESSAGE_KEY))
    assert result.state is PrincipalCommitObservationState.NOT_APPLIED
    assert result.event_id is None
    assert result.durable_ref is None
    assert service.calls == []


def test_reconcile_fenced_edge_without_message_is_sticky_effect_unknown(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    service = ReadService()
    subject = owner(runtime, Resolver(bound), service)
    subject.before_commit(request)

    first = run(subject.reconcile(MESSAGE_KEY))
    second = run(subject.reconcile(MESSAGE_KEY))
    assert first.state is PrincipalCommitObservationState.EFFECT_UNKNOWN
    assert second.state is PrincipalCommitObservationState.EFFECT_UNKNOWN
    assert first.message_fingerprint == request.message_fingerprint
    assert first.durable_ref == second.durable_ref
    assert len(service.calls) == 2

    with pytest.raises(PrincipalRuntimeFenceError):
        subject.before_commit(request)


def test_reconcile_exact_carrier_message_is_applied(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    service = ReadService([message])
    subject = owner(runtime, Resolver(bound), service)
    receipt = subject.before_commit(request)

    result = run(subject.reconcile(MESSAGE_KEY))
    assert result.state is PrincipalCommitObservationState.APPLIED
    assert result.message_fingerprint == message["fingerprint"]
    assert result.durable_ref == receipt.durable_ref
    assert result.event_id is not None
    assert len(result.canonical_digest) == 64


def test_reconcile_conflicting_same_key_message_is_conflict(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    conflict = principal_message(bound, instruction="Different committed semantics.")
    service = ReadService([conflict])
    subject = owner(runtime, Resolver(bound), service)
    subject.before_commit(request)

    result = run(subject.reconcile(MESSAGE_KEY))
    assert result.state is PrincipalCommitObservationState.CONFLICT


def test_reconcile_carrier_failure_preserves_effect_unknown(tmp_path):
    runtime, root, child, attempt = runtime_child(tmp_path)
    bound = binding(root, child, attempt)
    message = principal_message(bound)
    request = intent(bound, message)
    service = ReadService(error=True)
    subject = owner(runtime, Resolver(bound), service)
    subject.before_commit(request)

    result = run(subject.reconcile(MESSAGE_KEY))
    assert result.state is PrincipalCommitObservationState.EFFECT_UNKNOWN


def test_runtime_fence_owner_adds_no_table_listener_or_retry_plane() -> None:
    path = (
        ROOT
        / "integrations"
        / "mastermind_company_principal_runtime_fence.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
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
        {"sqlite3", "subprocess", "requests", "httpx", "slack_sdk", "mcp"}
    )
    for forbidden in (
        "CREATE TABLE",
        "CREATE INDEX",
        "retry(",
        "failover(",
        "wake(",
        "register_worker(",
        "create_job(",
        "claim_job(",
    ):
        assert forbidden not in source


def test_runtime_fence_test_is_in_existing_ci_gate() -> None:
    from scripts.ci_pytest import resolve_gate

    gate = resolve_gate(ROOT)
    assert "tests/test_company_dialogue_principal_runtime_fence.py" in gate["included"]
