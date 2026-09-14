from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from common.agent_dialogue_consultation_contract import (
    RECEIPT_KEYS,
    build_consultation,
    validate_consultation,
)
from control_plane.consultation_runtime import (
    ConsultationConflict,
    ConsultationRuntime,
    consultation_projection,
)
from control_plane.executive_runtime import Runtime, StateConflict


QUESTION = (
    "From the exact accepted source revision, what is the closed Company MCP "
    "consultation input schema and which caller-supplied fields must be refused?"
)


def _actor(job: str, attempt: str, worker: str) -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": job,
        "attempt_id": attempt,
        "worker_id": worker,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _binding(attempt_epoch: str, generation: int = 1) -> dict[str, object]:
    return {
        "binding_id": "bind-" + hashlib.sha256(attempt_epoch.encode()).hexdigest()[:40],
        "binding_generation": generation,
        "reasoning_surface": "codex",
    }


def _fixture_repo(root: Path) -> tuple[Path, dict[str, str], dict[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "fixture-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    source = (
        "CONSULTATION_KEYS = frozenset({'question', 'answer'})\n"
        "FORBIDDEN_FIELDS = frozenset({'provider', 'account', 'host', 'session_id'})\n"
    )
    path = repo / "consultation_schema.py"
    path.write_text(source, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    revision = {
        "repository": "fixture/consultation",
        "path": "consultation_schema.py",
        "commit": commit,
        "content_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }
    return repo, revision, {
        "fields": ["answer", "question"],
        "refused": ["account", "host", "provider", "session_id"],
    }


def _bound_worker(
    runtime: Runtime,
    *,
    worker_id: str,
    thread_id: str,
    root_job_id: str | None = None,
) -> tuple[str, str, dict[str, object]]:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@example.invalid",
        worker_type="codex-app-server",
        capabilities=["code"],
        quota_classes={
            "codex-consultation": {
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "small",
                "capabilities": ["code"],
            }
        },
    )
    job = runtime.jobs.create_job(
        "Managed consultation fixture",
        parent_job_id=root_job_id,
        constraints={
            "provider": "codex",
            "eligible_quota_classes": ["codex-consultation"],
            "required_capabilities": ["code"],
        },
    )
    lease = runtime.attempts.claim_job(
        job.job_id, worker_id=worker_id, quota_class="codex-consultation"
    )
    assert lease is not None
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE attempts SET status='RUNNING',provider_session_id=?
            WHERE attempt_id=?
            """,
            (thread_id, lease.attempt.attempt_id),
        )
    epoch_id = f"ohf-epoch-{worker_id}"
    generation_id = f"ohf-generation-{worker_id}"
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            INSERT INTO harness_session_epochs(
              session_epoch_id,attempt_id,worker_id,epoch_number,state,
              provider_session_id,created_at_ms
            ) VALUES (?,?,?,1,'CURRENT',?,?)
            """,
            (epoch_id, lease.attempt.attempt_id, worker_id, thread_id, 1),
        )
        connection.execute(
            """
            INSERT INTO process_generations(
              process_generation_id,session_epoch_id,worker_id,generation_number,
                  executive_writer_held,provider_writer_state,provider_session_id,
                  started_at_ms,created_at_ms
                ) VALUES (?,?,?,?,1,'HELD',?,1,1)
            """,
            (generation_id, epoch_id, worker_id, 1, thread_id),
        )
    binding = _binding(f"{lease.attempt.attempt_id}:{epoch_id}")
    return job.job_id, lease.attempt.attempt_id, binding


def _workers(
    runtime: Runtime,
) -> tuple[
    tuple[str, str, dict[str, object]],
    tuple[str, str, dict[str, object]],
    str,
]:
    root = runtime.jobs.create_job("Managed consultation program")
    requester = _bound_worker(
        runtime,
        worker_id="requester",
        thread_id="thread-requester",
        root_job_id=root.job_id,
    )
    recipient = _bound_worker(
        runtime,
        worker_id="recipient",
        thread_id="thread-recipient",
        root_job_id=root.job_id,
    )
    return requester, recipient, root.job_id


def _frame(
    tmp_path: Path,
    *,
    requester: tuple[str, str, str, dict[str, object]],
    recipient: tuple[str, str, str, dict[str, object]],
    question: str = QUESTION,
) -> tuple[dict, dict]:
    repo, revision, semantic = _fixture_repo(tmp_path / "fixture-repo-root")
    raw = {
        "schema": "mastermind.agent_dialogue_consultation.v1",
        "message_key": "asd-consultation-0000000000000001",
        "consultation_id": "consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        "purpose": "QUESTION",
        "requester_actor_ref": _actor(requester[0], requester[1], requester[2]),
        "recipient_actor_ref": _actor(recipient[0], recipient[1], recipient[2]),
        "recipient_peer_ref": "peer-7bdf4a6f9a664bbcf1a93d67a41ba51d",
        "recipient_binding": recipient[3],
        "correlation": {
            "parent_fingerprint": "a" * 64,
            "request_message_key": "asd-consultation-0000000000000001",
            "consultation_id": "consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
            "requester_actor_digest": _digest(requester[2] + requester[1]),
            "recipient_actor_digest": _digest(recipient[2] + recipient[1]),
        },
        "question": question,
        "answer": None,
        "evidence_refs": [
            "https://github.com/mastermindx-market-intelligence/Mastermind/pull/611"
        ],
        "artifact_revisions": [revision],
        "valid_until": "2026-09-15T00:00:00Z",
        "deadline_ms": 60000,
        "response_budget": {
            "max_answers": 1,
            "max_evidence_reads": 4,
            "max_forward_hops": 0,
            "max_payload_bytes": 32768,
        },
        "supersedes_message_key": None,
        "question_message_key": "asd-consultation-0000000000000001",
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw), (semantic, repo)


def test_runtime_binding_id_grammar_accepts_exact_runtime_ids(tmp_path: Path) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, _binding_value), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), root = _workers(runtime)
    frame, _semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", _binding("ignored")),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    fixture_repo = _semantic_bundle[1]

    intent = consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )

    assert intent.event.event_type == "INTENT"
    assert intent.event.payload["recipient_binding"] == recipient_binding
    assert len(frame["recipient_binding"]["binding_id"]) == 45


def test_consultation_runtime_restart_effect_unknown_and_late_answer(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, _requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), root = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", _requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    fixture_repo = semantic_bundle[1]
    original = consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )
    duplicate = consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:01:00Z",
        repository_root=fixture_repo,
    )
    assert duplicate.inserted is False
    assert duplicate.event.created_at == original.event.created_at

    changed = copy.deepcopy(frame)
    changed["question"] = QUESTION + " changed"
    changed["fingerprint"] = ""
    changed = build_consultation(changed)
    with pytest.raises(ConsultationConflict, match="CONFLICT"):
        consultations.intent(
            changed,
            requester_attempt_id=requester_attempt,
            carrier_ref="dialogue://fixture/consultation",
            observed_at="2026-09-14T00:02:00Z",
            repository_root=fixture_repo,
        )

    dispatch = consultations.dispatch_attempt(
        frame,
        wake_obligation_id="WAKE-" + "1" * 32,
        wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
        observed_at="2026-09-14T00:03:00Z",
    )
    assert dispatch.event.event_type == "DISPATCH_ATTEMPT"
    reopened = ConsultationRuntime(Runtime.at(tmp_path), repository_root=tmp_path)
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        reopened.dispatch_attempt(
            frame,
            wake_obligation_id="WAKE-" + "1" * 32,
            wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
            observed_at="2026-09-14T00:04:00Z",
        )
    unknown = reopened.resolve_restart(frame)
    assert unknown == "EFFECT_UNKNOWN"

    native = reopened.native_accepted(
        frame,
        native_thread_id="thread-recipient",
        native_turn_id="turn-recipient",
        observed_at="2026-09-14T00:05:00Z",
    )
    assert native.event.event_type == "NATIVE_ACCEPTED"
    assert native.event.payload["evidence"]["accepted"] is True
    consumed = reopened.consumed_by_recipient(
        frame,
        native_thread_id="thread-recipient",
        native_turn_id="turn-recipient",
        observed_at="2026-09-14T00:06:00Z",
    )
    assert consumed.event.event_type == "CONSUMED_BY_RECIPIENT"

    semantic, fixture_repo = semantic_bundle
    answer_one = _answer_frame(frame, "v1", semantic)
    answer_two = _answer_frame(frame, "v2", semantic)
    late_semantic = copy.deepcopy(semantic)
    late_semantic["refused"] = late_semantic["refused"] + ["runtime_binding"]
    late = _answer_frame(frame, "late", late_semantic)
    first_available = reopened.answer_available(
        answer_one, observed_at="2026-09-14T00:07:00Z", historical=False
    )
    request_one = reopened.consumed_by_requester(
        answer_one, observed_at="2026-09-14T00:08:00Z"
    )
    available_commands = {
        event.command_id
        for event in reopened.events(frame)
        if event.event_type == "ANSWER_AVAILABLE"
    }
    assert len(available_commands) == 1
    assert available_commands == {
        f"consult:{frame['consultation_id']}:ANSWER_AVAILABLE:{answer_one['message_key']}"
    }
    assert first_available.event.event_type == "ANSWER_AVAILABLE"
    assert request_one.event.event_type == "CONSUMED_BY_REQUESTER"
    second_available = reopened.answer_available(
        answer_two, observed_at="2026-09-14T00:09:00Z"
    )
    late_receipt = reopened.answer_available(
        answer_two, observed_at="2026-09-14T00:10:00Z"
    )
    expected_budget_command = (
        f"consult:{frame['consultation_id']}:"
        f"BUDGET_EXHAUSTED:{answer_two['message_key']}"
    )
    assert expected_budget_command in {
        event.command_id for event in reopened.events(frame)
    }
    with pytest.raises(StateConflict, match="answer budget exhausted"):
        reopened.consumed_by_requester(
            answer_two, observed_at="2026-09-14T00:10:00Z"
        )
    forged_answer = _answer_frame(frame, "forged", semantic)
    forged_answer["requester_actor_ref"] = _actor(
        root, "ROOT", "root-worker"
    )
    forged_answer["correlation"]["requester_actor_digest"] = _digest(
        "root-worker" + "ROOT"
    )
    forged_answer["fingerprint"] = ""
    forged_answer = build_consultation(forged_answer)
    assert second_available.event.event_type == "BUDGET_EXHAUSTED"
    assert second_available.inserted is True
    assert second_available.event.command_id == (
        f"consult:{frame['consultation_id']}:"
        f"BUDGET_EXHAUSTED:{answer_two['message_key']}"
    )
    with pytest.raises(StateConflict, match="answer requester actor drifted"):
        reopened.consumed_by_requester(
            forged_answer, observed_at="2026-09-14T00:10:30Z"
        )
    assert late_receipt.event.event_type == "BUDGET_EXHAUSTED"
    assert late_receipt.inserted is False
    assert late_receipt.event.payload["historical"] is True
    assert late_receipt.event.payload["conflict"] == "BUDGET_EXHAUSTED"
    assert late_receipt.event.payload["refused_message_key"] == answer_two["message_key"]
    assert late_receipt.event.payload["answer_fingerprint"] == answer_two["fingerprint"]

    projection = consultation_projection(runtime)
    assert len(projection) == 1
    assert projection[0]["question_digest"] == _digest(frame["question"])
    assert projection[0]["receipt_stage"] == "CONSUMED_BY_REQUESTER"
    assert projection[0]["blocker"] is None
    assert [event.event_type for event in reopened.events(frame)] == [
        "INTENT",
        "DISPATCH_ATTEMPT",
        "EFFECT_UNKNOWN",
        "NATIVE_ACCEPTED",
        "CONSUMED_BY_RECIPIENT",
        "ANSWER_AVAILABLE",
        "CONSUMED_BY_REQUESTER",
        "BUDGET_EXHAUSTED",
    ]


def test_b1_intent_only_restart_is_not_dispatched_and_may_redispatch(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, _requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), _root = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", _requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    reopened = ConsultationRuntime(Runtime.at(tmp_path), repository_root=tmp_path)

    assert reopened.resolve_restart(frame) == "NOT_DISPATCHED"
    dispatch = reopened.dispatch_attempt(
        frame,
        wake_obligation_id="WAKE-" + "1" * 32,
        wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
        observed_at="2026-09-14T00:01:00Z",
    )

    assert dispatch.inserted is True
    assert dispatch.event.event_type == "DISPATCH_ATTEMPT"
    assert reopened.resolve_restart(frame) == "EFFECT_UNKNOWN"


def test_b2_native_acceptance_requires_dispatch_attempt(tmp_path: Path) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, _requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), _root = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", _requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )

    with pytest.raises(StateConflict, match="DISPATCH_ATTEMPT"):
        consultations.native_accepted(
            frame,
            native_thread_id="thread-recipient",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:01:00Z",
        )

    assert [event.event_type for event in consultations.events(frame)] == ["INTENT"]


def _drifted_frame(
    frame: dict,
    *,
    field: str,
    value: object,
) -> dict:
    changed = copy.deepcopy(frame)
    changed[field] = value
    changed["fingerprint"] = ""
    return build_consultation(changed)


def _changed_frame(frame: dict, field: str, value: object) -> dict:
    changed = copy.deepcopy(frame)
    changed[field] = value
    changed["fingerprint"] = ""
    return build_consultation(changed)


def test_b3_dispatch_refuses_changed_stale_frame_and_current_binding(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), _root = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    fixture_repo = semantic_bundle[1]
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )
    stale = copy.deepcopy(recipient_binding)
    stale["binding_generation"] = 2
    changed_requester_actor = copy.deepcopy(frame["requester_actor_ref"])
    changed_requester_actor["worker_id"] = "changed-requester"
    changed_recipient_actor = copy.deepcopy(frame["recipient_actor_ref"])
    changed_recipient_actor["worker_id"] = "changed-recipient"
    changed_revision = copy.deepcopy(frame["artifact_revisions"])
    changed_revision[0]["content_sha256"] = "b" * 64
    drifted_frames = {
        "semantic": _changed_frame(frame, "question", QUESTION + " changed"),
        "requester_actor_ref": _changed_frame(
            frame, "requester_actor_ref", changed_requester_actor
        ),
        "recipient_actor_ref": _changed_frame(
            frame, "recipient_actor_ref", changed_recipient_actor
        ),
        "artifact_revision_digest": _changed_frame(
            frame, "artifact_revisions", changed_revision
        ),
        "recipient_binding": _changed_frame(frame, "recipient_binding", stale),
    }

    for changed in drifted_frames.values():
        with pytest.raises(StateConflict, match="frame identity drifted"):
            consultations.dispatch_attempt(
                changed,
                wake_obligation_id="WAKE-" + "1" * 32,
                wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
                observed_at="2026-09-14T00:01:00Z",
            )

    _release_recipient_writer(runtime)
    with pytest.raises(StateConflict, match="current Runtime binding"):
        consultations.dispatch_attempt(
            frame,
            wake_obligation_id="WAKE-" + "1" * 32,
            wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
            observed_at="2026-09-14T00:02:00Z",
        )

    assert consultations.events(frame) == [
        event for event in consultations.events(frame) if event.event_type == "INTENT"
    ]


def test_b4_recipient_consumption_refuses_changed_stale_frame_and_current_binding(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), _root = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", recipient_binding),
    )
    fixture_repo = semantic_bundle[1]
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )
    consultations.dispatch_attempt(
        frame,
        wake_obligation_id="WAKE-" + "1" * 32,
        wake_attempt_command_id="WAKE-" + "1" * 32 + ":delivery:1",
        observed_at="2026-09-14T00:01:00Z",
    )
    consultations.native_accepted(
        frame,
        native_thread_id="thread-recipient",
        native_turn_id="turn-recipient",
        observed_at="2026-09-14T00:02:00Z",
    )
    stale = copy.deepcopy(recipient_binding)
    stale["binding_generation"] = 2
    changed = _drifted_frame(frame, field="recipient_binding", value=stale)

    with pytest.raises(StateConflict, match="frame identity drifted"):
        consultations.consumed_by_recipient(
            changed,
            native_thread_id="thread-recipient",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:03:00Z",
        )

    _release_recipient_writer(runtime)
    with pytest.raises(StateConflict, match="current Runtime binding"):
        consultations.consumed_by_recipient(
            frame,
            native_thread_id="thread-recipient",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:04:00Z",
        )

    assert "CONSUMED_BY_RECIPIENT" not in {
        event.event_type for event in consultations.events(frame)
    }


def _release_recipient_writer(runtime: Runtime) -> None:
    with runtime.store.transaction() as connection:
        connection.execute(
            """
            UPDATE process_generations SET executive_writer_held=0
            WHERE process_generation_id='ohf-generation-recipient'
            """
        )


def _answer_frame(frame: dict, suffix: str, semantic: dict) -> dict:
    raw = copy.deepcopy(frame)
    raw["message_key"] = f"asd-consultation-answer-{suffix}"
    raw["purpose"] = "ANSWER"
    raw["question"] = None
    raw["answer"] = {
        "text": json.dumps(semantic, sort_keys=True, separators=(",", ":")),
        "evidence_refs": frame["evidence_refs"],
    }
    raw["correlation"]["request_message_key"] = "asd-consultation-0000000000000001"
    raw["question_message_key"] = frame["message_key"]
    raw["fingerprint"] = ""
    return build_consultation(raw)


def test_stale_recipient_binding_is_refused_before_receipt(tmp_path: Path) -> None:
    runtime = Runtime.at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (requester_job, requester_attempt, _requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), _root = _workers(runtime)
    stale = copy.deepcopy(recipient_binding)
    stale["binding_generation"] = 2
    frame, _semantic = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, "requester", _requester_binding),
        recipient=(recipient_job, recipient_attempt, "recipient", stale),
    )
    fixture_repo = _semantic[1]
    with pytest.raises(StateConflict, match="current Runtime binding"):
        consultations.intent(
            frame,
            requester_attempt_id=requester_attempt,
            carrier_ref="dialogue://fixture/consultation",
            observed_at="2026-09-14T00:00:00Z",
            repository_root=fixture_repo,
        )
    assert validate_consultation(frame)["fingerprint"]


def test_consultation_wake_source_and_peer_binding_extension(tmp_path: Path) -> None:
    from control_plane.dialogue_source_resolution import (
        ConsultationSourceIdentity,
        peer_attention_source_ref,
    )

    runtime = Runtime.at(tmp_path)
    (requester_job, requester_attempt, _requester_binding), (
        recipient_job,
        recipient_attempt,
        recipient_binding,
    ), root = _workers(runtime)
    identity = ConsultationSourceIdentity.create(
        consultation_id="consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        message_key="asd-consultation-0000000000000001",
        semantic_fingerprint="a" * 64,
        root_job_id=root,
        requester_job_id=requester_job,
        requester_attempt_id=requester_attempt,
        recipient_job_id=recipient_job,
        recipient_attempt_id=recipient_attempt,
        binding_id=str(recipient_binding["binding_id"]),
        binding_generation=int(recipient_binding["binding_generation"]),
    )
    assert peer_attention_source_ref(identity).startswith(
        "agent_dialogue_attention:"
    )


def test_persisted_wake_carrier_holds_exact_peer_binding_and_refuses_stale_generation(
    tmp_path: Path,
) -> None:
    from control_plane.session_targets import RuntimeBinding
    from control_plane.wake_ledger import requested_record
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        ConsultationWakeExtension,
    )

    runtime = Runtime.at(tmp_path)
    root = runtime.jobs.create_job("Managed consultation program")
    _job, recipient_attempt, recipient_binding = _bound_worker(
        runtime,
        worker_id="recipient",
        thread_id="thread-recipient",
        root_job_id=root.job_id,
    )
    repository = WakeLedgerRepository(runtime)
    _requester_job, requester_attempt, _requester_binding = _bound_worker(
        runtime,
        worker_id="requester",
        thread_id="thread-requester",
        root_job_id=root.job_id,
    )
    extension = ConsultationWakeExtension(
        repository=repository,
        requester_job_id=_requester_job,
        requester_attempt_id=requester_attempt,
        root_job_id=root.job_id,
        recipient_job_id=_job,
        recipient_attempt_id=recipient_attempt,
        consultation_id="consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        message_key="asd-consultation-0000000000000001",
        semantic_fingerprint="a" * 64,
        current_binding=RuntimeBinding(
            session_alias="WORKER-RECIPIENT",
            binding_id=str(recipient_binding["binding_id"]),
            binding_generation=1,
            native_handle="thread-recipient",
            reasoning_surface="codex",
        ),
    )
    obligation = extension.obligation()
    repository.append_record(requested_record(obligation), obligation=obligation)
    assert extension.current_binding_matches()
    stale = ConsultationWakeExtension(
        repository=repository,
        requester_job_id=extension.requester_job_id,
        requester_attempt_id=extension.requester_attempt_id,
        root_job_id=extension.root_job_id,
        recipient_job_id=extension.recipient_job_id,
        recipient_attempt_id=extension.recipient_attempt_id,
        consultation_id=extension.consultation_id,
        message_key=extension.message_key,
        semantic_fingerprint=extension.semantic_fingerprint,
        current_binding=replace(
            extension.current_binding, binding_generation=2
        ),
    )
    with pytest.raises(StateConflict, match="stale generation"):
        stale.current_binding_matches()


def test_remote_codex_consultation_ingress_idle_active_and_unqualified_claude() -> None:

    from control_plane.operator_harness_contract import (
        AttentionTurnObservation,
        ProcessGenerationRef,
    )
    from control_plane.remote_codex_operator_adapter import (
        CodexConsultationIngress,
        ConsultationIngressRefused,
        ConsultationIngressUnavailable,
    )

    generation = ProcessGenerationRef(
        "generation-recipient",
        "ohf-epoch-recipient",
        1,
        "recipient",
    )

    @dataclass
    class FakeAdapter:
        active: bool = False
        fail: bool = False
        calls: list[dict] = field(default_factory=list)

        def deliver_attention(self, **kwargs):
            self.calls.append(kwargs)
            if self.fail:
                raise RuntimeError("provider call began")
            return AttentionTurnObservation(
                process_generation_id=generation.process_generation_id,
                provider_session_id="thread-recipient",
                nudge_id=kwargs["nudge_id"],
                provider_native_turn_id="turn-recipient",
                accepted=True,
                delivered=True,
            )

    ingress = CodexConsultationIngress(
        adapter=FakeAdapter(),
        generation=generation,
        attempt_id="ATT-" + "2" * 32,
        binding_id="bind-" + "2" * 40,
        binding_generation=1,
        provider_session_id="thread-recipient",
        surface="codex",
    )
    accepted = ingress.deliver(
        consultation_ref="consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        message_key="asd-consultation-0000000000000001",
        semantic_fingerprint="a" * 64,
        wake_obligation_id="WAKE-" + "1" * 32,
    )
    assert accepted["native_thread_id"] == "thread-recipient"
    assert accepted["native_turn_id"] == "turn-recipient"
    assert accepted["accepted"] is True
    assert ingress.adapter.calls[0]["instruction"].startswith(
        "Company consultation reference only"
    )
    ingress.adapter.calls.clear()

    active = ingress.with_active_turn(True)
    assert len(active.adapter.calls) == 0
    with pytest.raises(ConsultationIngressRefused, match="active consultation"):
        active.deliver(
            consultation_ref="consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
            message_key="asd-consultation-0000000000000001",
            semantic_fingerprint="a" * 64,
            wake_obligation_id="WAKE-" + "1" * 32,
        )

    with pytest.raises(ConsultationIngressUnavailable, match="UNQUALIFIED"):
        CodexConsultationIngress(
            adapter=FakeAdapter(),
            generation=generation,
            attempt_id="ATT-" + "2" * 32,
            binding_id="bind-" + "2" * 40,
            binding_generation=1,
            provider_session_id="thread-recipient",
            surface="claude",
        )


def test_consultation_fits_pr600_policy_arithmetic(tmp_path: Path) -> None:
    runtime = Runtime.at(tmp_path)
    _requester, _recipient, root = _workers(runtime)
    children = [job for job in runtime.jobs.list_jobs() if job.parent_job_id == root]
    assert len(children) == 2
    assert all(job.depth == 1 for job in children)
    assert len(children) <= 16
