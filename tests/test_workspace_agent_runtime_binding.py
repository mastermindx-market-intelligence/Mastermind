"""Hermetic current-target contracts for Workspace Agent candidate return."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    PhysicalDialogueSourceIdentity,
    attention_source_ref,
    correlated_source_ref,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    JobStatus,
    WorkerStatus,
)
from control_plane.wake_events import mint_obligation_id
from integrations.slack_agent_dialogue.contract import FABLE_MESSAGE_TYPES
from integrations.workspace_agent_return import WorkspaceReturnError, binding_digest
from integrations.workspace_agent_runtime_binding import (
    ExecutiveWorkspaceReturnBindingResolver,
    WorkspaceReturnPhysicalSource,
    WorkspaceReturnTargetEpoch,
)


OPERATION = "exec-job-101"
ROOT_JOB = "JOB-100"
JOB = "JOB-101"
ATTEMPT = "ATT-" + "2" * 32
WORKER = "worker-01"
THREAD = "1788000000.123456"
PARENT = "a" * 64


def target(**changes) -> WorkspaceReturnTargetEpoch:
    value = WorkspaceReturnTargetEpoch(
        root_job_id=ROOT_JOB,
        job_id=JOB,
        attempt_id=ATTEMPT,
        worker_id=WORKER,
        job_status=JobStatus.RUNNING,
        attempt_status=AttemptStatus.RUNNING,
        fence_generation=4,
        worker_status=WorkerStatus.BUSY,
    )
    return dataclasses.replace(value, **changes)


def source(*, work_ref="WS:WORKSPACE-AGENT-PROGRAM") -> ExecutiveDialogueSource:
    return ExecutiveDialogueSource(
        schema_version="mastermind.executive_dialogue_source/v1",
        work_ref=work_ref,
        commission_ref={
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "research/WORKSPACE_AGENT_SUPERVISION_INTEGRATION_2026-09-13.md",
            "content_sha256": "2" * 64,
        },
        watch_mode="turn_watch_v1",
    )


def physical(
    *,
    worker_id=WORKER,
    attempt_id=ATTEMPT,
    root_job_id=ROOT_JOB,
    job_id=JOB,
    operation_key=OPERATION,
    source_workstream="WS:WORKSPACE-AGENT-PROGRAM",
) -> WorkspaceReturnPhysicalSource:
    candidate = {
        "mode": "ACTIVE_CURRENT_WORKER",
        "root_job_id": root_job_id,
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
        "evidence_digest": "b" * 64,
    }
    observation = DialogueSourceObservation(
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BSBM78V1N",
        thread_ts=THREAD,
        predecessor_message_key="asd-progress-001",
        predecessor_message_fingerprint="c" * 64,
    )
    attention = attention_source_ref(
        parent_fingerprint=PARENT,
        message_key=observation.predecessor_message_key,
        target_seat="coo",
    )
    logical = correlated_source_ref(
        attention_source_ref=attention,
        parent_fingerprint=PARENT,
        operation_key=operation_key,
        candidate=candidate,
    )
    identity = PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical,
        obligation_id=mint_obligation_id(
            source_kind="agent_dialogue_attention",
            source_ref=logical,
            wake_kind="dialogue_turn_pending",
        ),
        observation=observation,
        parent_fingerprint=PARENT,
        operation_key=operation_key,
        target_seat="coo",
        candidate=candidate,
    )
    return WorkspaceReturnPhysicalSource(
        identity=identity,
        source_workstream=source_workstream,
    )


class TargetSequence:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = []

    def __call__(self, operation_key):
        self.calls.append(operation_key)
        if not self.values:
            raise AssertionError("unexpected target read")
        return self.values.pop(0)


def resolver(
    *,
    targets=None,
    source_value=None,
    physical_value=None,
):
    target_reader = targets or TargetSequence(target(), target())
    source_value = source_value or source()
    physical_value = physical_value or physical()
    return (
        ExecutiveWorkspaceReturnBindingResolver(
            object(),
            target_reader=target_reader,
            dialogue_source_reader=lambda root_job_id: source_value,
            physical_source_reader=lambda operation_key, job_id, attempt_id: physical_value,
        ),
        target_reader,
    )


def test_exact_current_target_reconstructs_company_dialogue_binding() -> None:
    instance, targets = resolver()
    binding = instance.resolve(OPERATION)

    assert targets.calls == [OPERATION, OPERATION]
    assert binding.operation_key == OPERATION
    assert binding.session_ref == "asd-session-exec-job-101"
    assert binding.work_ref == "WS:WORKSPACE-AGENT-PROGRAM"
    assert binding.thread_ts == THREAD
    assert binding.actor_ref == {
        "kind": "worker_attempt",
        "job_id": JOB,
        "attempt_id": ATTEMPT,
        "worker_id": WORKER,
    }
    assert binding.applies_to == {
        "kind": "executive_attempt",
        "job_id": JOB,
        "attempt_id": ATTEMPT,
        "worker_id": WORKER,
    }
    assert binding.allowed_message_types == tuple(sorted(FABLE_MESSAGE_TYPES))
    assert binding.reply_to_message_key is None
    second_instance, _ = resolver()
    assert binding_digest(binding) == binding_digest(second_instance.resolve(OPERATION))


def test_target_rollover_between_source_reads_refuses() -> None:
    changed = target(
        attempt_id="ATT-" + "3" * 32,
        worker_id="worker-02",
        fence_generation=5,
    )
    instance, targets = resolver(targets=TargetSequence(target(), changed))

    with pytest.raises(WorkspaceReturnError, match="BINDING_UNAVAILABLE"):
        instance.resolve(OPERATION)
    assert targets.calls == [OPERATION, OPERATION]


@pytest.mark.parametrize(
    "physical_value",
    [
        physical(worker_id="worker-02"),
        physical(attempt_id="ATT-" + "3" * 32),
        physical(root_job_id="JOB-999"),
        physical(job_id="JOB-999", operation_key="exec-job-999"),
    ],
)
def test_physical_source_must_match_exact_current_executive_target(
    physical_value: WorkspaceReturnPhysicalSource,
) -> None:
    instance, _ = resolver(physical_value=physical_value)
    with pytest.raises(WorkspaceReturnError, match="BINDING_UNAVAILABLE"):
        instance.resolve(OPERATION)


def test_physical_source_must_match_immutable_root_workstream() -> None:
    instance, _ = resolver(
        physical_value=physical(source_workstream="WS:OTHER-PROGRAM"),
    )
    with pytest.raises(WorkspaceReturnError, match="BINDING_UNAVAILABLE"):
        instance.resolve(OPERATION)


@pytest.mark.parametrize(
    "operation_key",
    [
        "job-101",
        "exec-job-x",
        "exec-job-10",
        "exec-job-101-extra",
        "EXEC-JOB-101",
        "",
    ],
)
def test_only_host_derived_executive_operation_keys_reach_target_reader(
    operation_key: str,
) -> None:
    targets = TargetSequence(target(), target())
    instance, _ = resolver(targets=targets)
    with pytest.raises(WorkspaceReturnError, match="BINDING_UNAVAILABLE"):
        instance.resolve(operation_key)
    assert targets.calls == []


def test_reader_failures_are_closed_and_do_not_leak_dependency_text() -> None:
    def fail_source(_root_job_id):
        raise RuntimeError("xoxb-SYNTHETIC-PRIVATE")

    instance = ExecutiveWorkspaceReturnBindingResolver(
        object(),
        target_reader=TargetSequence(target(), target()),
        dialogue_source_reader=fail_source,
        physical_source_reader=lambda operation_key, job_id, attempt_id: physical(),
    )
    with pytest.raises(WorkspaceReturnError) as exc:
        instance.resolve(OPERATION)
    assert str(exc.value) == "BINDING_UNAVAILABLE"
    assert "SYNTHETIC" not in repr(exc.value)


def test_runtime_binding_adapter_adds_no_workspace_state_or_mutator() -> None:
    text = (
        Path(__file__).resolve().parent.parent
        / "integrations"
        / "workspace_agent_runtime_binding.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "sqlite3",
        "CREATE TABLE",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        ".transaction(",
        "asyncio.Queue",
        "queue.Queue",
        "CredentialStore",
    ):
        assert forbidden not in text
    assert "runtime.store.read()" in text
    assert "wake_record_from_event" in text
    assert "_dialogue_source_from_root_creation" in text
