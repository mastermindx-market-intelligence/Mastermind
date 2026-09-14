from __future__ import annotations

import copy
import hashlib
import json
import os
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
from control_plane.dialogue_source_resolution import ConsultationSourceIdentity
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessIdentityObservation,
    RequestedExecutionProfile,
    WorkspaceIdentity,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    ConsultationWakeExtension,
)


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


def _runtime_at(root: Path) -> Runtime:
    return Runtime.at(root, lease_seconds=3600)


def _binding(attempt_epoch: str, generation: int = 1) -> dict[str, object]:
    return {
        "binding_id": "bind-" + hashlib.sha256(attempt_epoch.encode()).hexdigest()[:40],
        "binding_generation": generation,
        "reasoning_surface": "codex",
    }


def _profile(lease) -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id=str(lease.attempt.worker_id),
        provider="openai-codex",
        requested_model="fixture-model",
        harness_kind="fixture",
        harness_binary_digest="a" * 64,
        harness_version="1",
        workspace=WorkspaceIdentity(
            "/tmp/consultation-runtime", "b" * 40, 1, 2, os.getuid(), os.getgid()
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=str(lease.attempt.authority_policy_hash),
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
    )


def _attestation(profile: RequestedExecutionProfile):
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
        auth=AuthRealmFact(worker_id=profile.worker_id, provider=profile.provider),
        workspace=profile.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN,
    )




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


def _complete_planner(
    runtime: Runtime,
    dispatch,
    sealed,
    epoch,
    generation,
    process,
    role_result: dict,
) -> None:
    from control_plane.executive_orchestration_result import (
        RESULT_SCHEMA,
        RawRoleResultObservation,
        canonical_bytes as result_canonical_bytes,
        canonical_digest as result_digest,
    )
    from control_plane.operator_harness_contract import (
        CandidateResult,
        EventCursor,
        ProcessLiveness,
        ProviderWriterState,
        ReconcileObservation,
        TurnStartObservation,
    )

    attempt = dispatch.attempt
    job = runtime.jobs.get_job(attempt.job_id)
    assert job is not None and job.orchestration_role == "plan"
    harness = runtime.operator_harness
    turn_operation = OperationId(f"ohf-op:w6c2-{attempt.attempt_id}-turn")
    turn = harness.reserve_turn(
        epoch=epoch,
        generation=generation,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    native_turn = f"native-{attempt.attempt_id}"
    harness.acknowledge_turn(
        turn=turn,
        operation_id=turn_operation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
        observation=TurnStartObservation(native_turn, True),
    )
    artifact_digest = hashlib.sha256(
        f"w6c2-{attempt.attempt_id}".encode()
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
        "worker_id": attempt.worker_id,
        "role": job.orchestration_role,
        "status": "COMPLETED",
        "role_result": role_result,
        "summary": "typed fixture result",
        "current_state": "complete",
        "next_actions": [],
        "errors": [],
        "validations": [],
    }
    canonical = result_canonical_bytes(envelope).decode()
    observation = RawRoleResultObservation(
        attempt_id=attempt.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        turn_id=turn.turn_id,
        provider_session_id="thread-planner",
        provider_native_turn_id=native_turn,
        provider_turn_artifact_digest=artifact_digest,
        canonical_result_json=canonical,
        canonical_result_digest=hashlib.sha256(canonical.encode()).hexdigest(),
        canonical_result_byte_length=len(canonical.encode()),
    )
    harness.seal_orchestration_role_result(
        turn=turn,
        observation=observation,
        fence_generation=sealed.fence_generation,
        lease_token=dispatch.lease_token,
    )
    harness.record_graceful_stop(
        generation=generation,
        observation=ReconcileObservation(
            process_liveness=ProcessLiveness.PROVEN_DEAD,
            observed_process=process,
            provider_session_reachable=True,
            provider_writer_state=ProviderWriterState.RELEASED,
            observed_provider_session_id="thread-planner",
        ),
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


def _strict_v2_workers(
    runtime: Runtime,
) -> tuple[
    tuple[str, str, str, dict[str, object]],
    tuple[str, str, str, dict[str, object]],
    str,
]:
    from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
    from control_plane.executive_orchestration_principal import (
        OperatorPrincipalObservation,
    )
    from control_plane.executive_orchestration_result import (
        RESULT_SCHEMA,
        RawRoleResultObservation,
        canonical_bytes as result_canonical_bytes,
        canonical_digest as result_digest,
    )
    from control_plane.operator_harness_contract import (
        CandidateResult,
        EventCursor,
        ProcessLiveness,
        ProviderWriterState,
        ReconcileObservation,
        TurnStartObservation,
    )

    for worker_id in ("consultation-requester", "consultation-recipient"):
        runtime.workers.register_worker(
            worker_id,
            provider="openai-codex",
            account_label=f"{worker_id}@example.invalid",
            worker_type="fixture",
            capabilities=["read"],
            quota_classes={
                "default": {
                    "provider": "openai-codex",
                    "capabilities": ["read"],
                    "cost_class": "small",
                }
            },
        )

    receipt = submit_intent(
        runtime,
        {
            "schema": INTENT_SCHEMA_V2,
            "intent_id": "CEO-W6-C2-CONSULTATION-001",
            "actor": "ceo-sol",
            "objective": "Support two exact current consultation writers.",
            "department": "executive-infrastructure",
            "priority": 9,
            "grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
            "execution_contract": {
                "requested_authorities": ["READ"],
                "attempt_limit": 2,
            },
            "intent_kind": "executive_coo_cycle",
            "business_impact": "routine",
        },
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )

    def dispatch(job, sequence, worker_id):
        outcome = runtime.attempts.dispatch_cycle_job(
            job.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:{sequence}"
            ),
            worker_id=worker_id,
        )
        assert outcome is not None and outcome.lease_token is not None
        return outcome

    def admitted(dispatch_outcome, provider_session):
        attempt = dispatch_outcome.attempt
        job = runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        profile = _profile(dispatch_outcome)
        harness = runtime.operator_harness
        sealed = harness.seal_operator_harness_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=dispatch_outcome.lease_token,
            requested=profile,
        )
        operation = OperationId(f"ohf-op:w6c2-{attempt.attempt_id}-start")
        epoch, generation = harness.reserve_start(
            sealed.attempt_id,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch_outcome.lease_token,
            operation_id=operation,
        )
        process = ProcessIdentityObservation(
            3101,
            3101,
            f"start-{attempt.attempt_id}",
            f"boot-{attempt.attempt_id}",
        )
        harness.bind_start_result(
            epoch=epoch,
            generation=generation,
            operation_id=operation,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch_outcome.lease_token,
            provider_session_id=provider_session,
            process=process,
        )
        principal = OperatorPrincipalObservation(
            attempt_id=attempt.attempt_id,
            worker_id=attempt.worker_id,
            process_generation_id=generation.process_generation_id,
            provider_session_id=provider_session,
            process_identity={
                "pid": process.pid,
                "pgid": process.pgid,
                "process_start_identity": process.process_start_identity,
                "boot_id": process.boot_id,
            },
            os_principal_name=f"fixture-{attempt.attempt_id}",
            os_principal_uid=os.getuid(),
            provider_home_identity={
                "path": f"/tmp/w6c2-{attempt.attempt_id}",
                "device": 1,
                "inode": 2,
                "uid": os.getuid(),
                "gid": os.getgid(),
                "mode": 0o700,
            },
            observed_at_ms=runtime.store.now_ms(),
        )
        harness.seal_attestation(
            generation=generation,
            fence_generation=sealed.fence_generation,
            lease_token=dispatch_outcome.lease_token,
            requested=profile,
            attestation=_attestation(profile),
            principal_observation=principal,
        )
        return attempt, job, sealed, epoch, generation, process

    def admit(dispatch_outcome, provider_session):
        attempt, job, sealed, epoch, generation, process = admitted(
            dispatch_outcome, provider_session
        )
        return attempt, job, sealed, epoch, generation, process

    planner_dispatch = dispatch(
        planner, 1, "consultation-requester"
    )
    plan_body = {
        "schema_version": "mastermind.execution_plan/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "steps": [
            {
                "ordinal": index,
                "step_id": f"consultation-{index}",
                "objective": f"Hold current consultation writer {index}.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
            }
            for index in range(2)
        ],
    }
    (
        _planner_attempt,
        _planner_job,
        planner_sealed,
        planner_epoch,
        planner_generation,
        planner_process,
    ) = admit(planner_dispatch, "thread-planner")
    _complete_planner(
        runtime,
        planner_dispatch,
        planner_sealed,
        planner_epoch,
        planner_generation,
        planner_process,
        plan_body,
    )
    works = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{planner_dispatch.attempt.attempt_id}"
        ),
    )
    assert len(works) == 2
    result = []
    for index, work in enumerate(works):
        work_dispatch = dispatch(
            work,
            1,
            "consultation-requester" if index == 0 else "consultation-recipient",
        )
        admit(work_dispatch, f"thread-recipient-{index}")
        with runtime.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT e.session_epoch_id,g.generation_number
                FROM harness_session_epochs e
                JOIN process_generations g
                  ON g.session_epoch_id=e.session_epoch_id
                WHERE e.attempt_id=?
                ORDER BY e.created_at_ms,g.generation_number DESC
                LIMIT 1
                """,
                (work_dispatch.attempt.attempt_id,),
            ).fetchone()
        assert row is not None
        result.append(
            (
                work.job_id,
                work_dispatch.attempt.attempt_id,
                work_dispatch.attempt.worker_id,
                _binding(
                    f"{work_dispatch.attempt.attempt_id}:{row['session_epoch_id']}",
                    row["generation_number"],
                ),
            )
        )
    requester_job, requester_attempt, requester_worker, requester_binding = result[0]
    recipient_job, recipient_attempt, recipient_worker, recipient_binding = result[1]
    return (
        (requester_job, requester_attempt, requester_worker, requester_binding),
        (recipient_job, recipient_attempt, recipient_worker, recipient_binding),
        root.job_id,
    )

def _workers(
    runtime: Runtime,
) -> tuple[
    tuple[str, str, str, dict[str, object]],
    tuple[str, str, str, dict[str, object]],
    str,
]:
    return _strict_v2_workers(runtime)

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
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw), (semantic, repo)


def _persisted_wake_attempt(
    runtime: Runtime,
    consultations: ConsultationRuntime,
    frame: dict,
):
    from control_plane.wake_ledger import LedgerPhase, attempt_record, requested_record
    from control_plane.wake_persist import WakeLedgerRepository

    extension, attempt = _wake_route(runtime, frame)
    WakeLedgerRepository(runtime).append_records_atomic(
        [
            (requested_record(extension.obligation()), extension.obligation()),
            (attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), None),
        ]
    )
    return extension, attempt


def test_runtime_binding_id_grammar_accepts_exact_runtime_ids(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _binding_value),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, _semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _binding("ignored")),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
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
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
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

    _extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    dispatch = consultations.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:03:00Z"
    )
    assert dispatch.event.event_type == "DISPATCH_ATTEMPT"
    reopened = ConsultationRuntime(_runtime_at(tmp_path), repository_root=tmp_path)
    unknown = reopened.resolve_restart(frame)
    assert unknown == "EFFECT_UNKNOWN"
    # The first persisted Wake attempt remains unsettled until exact evidence.

    native = reopened.native_accepted(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        wake_attempt_command_id=attempt.attempt_command_id,
        observed_at="2026-09-14T00:05:00Z",
    )
    assert native.event.event_type == "NATIVE_ACCEPTED"
    assert native.event.payload["evidence"]["accepted"] is True
    consumed = reopened.consumed_by_recipient(
        frame,
        native_thread_id="thread-recipient-1",
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
    expected_refused_command = (
        f"consult:{frame['consultation_id']}:"
        f"ANSWER_REFUSED:{answer_two['message_key']}"
    )
    assert expected_refused_command in {
        event.command_id for event in reopened.events(frame)
    }
    with pytest.raises(StateConflict, match="reserved answer"):
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
    assert second_available.event.event_type == "ANSWER_REFUSED"
    assert second_available.inserted is True
    assert second_available.event.command_id == (
        f"consult:{frame['consultation_id']}:"
        f"ANSWER_REFUSED:{answer_two['message_key']}"
    )
    with pytest.raises(StateConflict, match="answer requester actor drifted"):
        reopened.consumed_by_requester(
            forged_answer, observed_at="2026-09-14T00:10:30Z"
        )
    assert late_receipt.event.event_type == "ANSWER_REFUSED"
    assert late_receipt.inserted is False
    assert late_receipt.event.payload["historical"] is True
    assert late_receipt.event.payload["conflict"] == "ANSWER_ALREADY_RESERVED"
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
        "NATIVE_ACCEPTED",
        "CONSUMED_BY_RECIPIENT",
        "ANSWER_AVAILABLE",
        "CONSUMED_BY_REQUESTER",
        "ANSWER_REFUSED",
    ]


def test_b1_intent_only_restart_is_not_dispatched_and_may_redispatch(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    reopened = ConsultationRuntime(_runtime_at(tmp_path), repository_root=tmp_path)

    assert reopened.resolve_restart(frame) == "NOT_DISPATCHED"
    _extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    dispatch = reopened.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:01:00Z"
    )

    assert dispatch.inserted is True
    assert dispatch.event.event_type == "DISPATCH_ATTEMPT"
    assert reopened.resolve_restart(frame) == "EFFECT_UNKNOWN"


def test_b2_native_acceptance_requires_dispatch_attempt(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)

    with pytest.raises(StateConflict, match="DISPATCH_ATTEMPT"):
        consultations.native_accepted(
            frame,
            native_thread_id="thread-recipient-1",
            native_turn_id="turn-recipient",
            wake_attempt_command_id=attempt.attempt_command_id,
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
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    fixture_repo = semantic_bundle[1]
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )
    _extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
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
                wake_attempt=attempt,
                observed_at="2026-09-14T00:01:00Z",
            )

    _release_recipient_writer(runtime)
    with pytest.raises(StateConflict, match="current Runtime binding|current actionable OHF writer"):
        consultations.dispatch_attempt(
            frame,
            wake_attempt=attempt,
            observed_at="2026-09-14T00:02:00Z",
        )

    assert consultations.events(frame) == [
        event for event in consultations.events(frame) if event.event_type == "INTENT"
    ]


def test_b4_recipient_consumption_refuses_changed_stale_frame_and_current_binding(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    fixture_repo = semantic_bundle[1]
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=fixture_repo,
    )
    _extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    consultations.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:01:00Z"
    )
    consultations.native_accepted(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        wake_attempt_command_id=attempt.attempt_command_id,
        observed_at="2026-09-14T00:02:00Z",
    )
    stale = copy.deepcopy(recipient_binding)
    stale["binding_generation"] = 2
    changed = _drifted_frame(frame, field="recipient_binding", value=stale)

    with pytest.raises(StateConflict, match="frame identity drifted"):
        consultations.consumed_by_recipient(
            changed,
            native_thread_id="thread-recipient-1",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:03:00Z",
        )

    _release_recipient_writer(runtime)
    with pytest.raises(StateConflict, match="current Runtime binding|current actionable OHF writer"):
        consultations.consumed_by_recipient(
            frame,
            native_thread_id="thread-recipient-1",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:04:00Z",
        )

    assert "CONSUMED_BY_RECIPIENT" not in {
        event.event_type for event in consultations.events(frame)
    }


def _release_recipient_writer(runtime: Runtime) -> None:
    with runtime.store.transaction() as connection:
        row = connection.execute(
            "SELECT g.process_generation_id FROM process_generations g "
            "JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id "
            "WHERE e.attempt_id=(SELECT attempt_id FROM attempts WHERE worker_id=?) "
            "ORDER BY g.generation_number DESC LIMIT 1",
            ("consultation-recipient",),
        ).fetchone()
        assert row is not None
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0 "
            "WHERE process_generation_id=?",
            (row["process_generation_id"],),
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
    raw["schema"] = "mastermind.agent_dialogue_consultation.v2"
    raw["question_message_key"] = frame["message_key"]
    raw["fingerprint"] = ""
    return build_consultation(raw)


def test_stale_recipient_binding_is_refused_before_receipt(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    stale = copy.deepcopy(recipient_binding)
    stale["binding_generation"] = 2
    frame, _semantic = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, stale),
    )
    fixture_repo = _semantic[1]
    with pytest.raises(StateConflict, match="current Runtime binding|current actionable OHF writer"):
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

    runtime = _runtime_at(tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        root,
    ) = _workers(runtime)
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
    from control_plane.session_targets import RuntimeBinding, SessionTarget
    from control_plane.wake_ledger import requested_record
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        ConsultationWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (_requester_job, _requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, _semantic = _frame(
        tmp_path,
        requester=(_requester_job, _requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    extension, _attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    repository = WakeLedgerRepository(runtime)
    persisted = repository.get_by_command_id(extension.obligation().obligation_id)
    assert persisted is not None
    target = SessionTarget(
        session_alias="CONSULTATION-RECIPIENT",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=True,
    )
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
    from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION

    assert ingress.adapter.calls[0]["instruction"] == ATTENTION_TURN_INSTRUCTION
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


def _wake_route(runtime: Runtime, frame: dict | None = None):
    from control_plane.session_targets import RuntimeBinding
    from control_plane.wake_ledger import make_delivery_attempt

    question = frame
    assert question is not None
    identity = ConsultationSourceIdentity.create(
        consultation_id=question["consultation_id"],
        message_key=question["message_key"],
        semantic_fingerprint=question["fingerprint"],
        root_job_id=_root_job_id(runtime, question),
        requester_job_id=question["requester_actor_ref"]["job_id"],
        requester_attempt_id=question["requester_actor_ref"]["attempt_id"],
        recipient_job_id=question["recipient_actor_ref"]["job_id"],
        recipient_attempt_id=question["recipient_actor_ref"]["attempt_id"],
        binding_id=str(question["recipient_binding"]["binding_id"]),
        binding_generation=int(question["recipient_binding"]["binding_generation"]),
    )
    extension = ConsultationWakeExtension(
        repository=WakeLedgerRepository(runtime),
        requester_job_id=identity.requester_job_id,
        requester_attempt_id=identity.requester_attempt_id,
        root_job_id=identity.root_job_id,
        recipient_job_id=identity.recipient_job_id,
        recipient_attempt_id=identity.recipient_attempt_id,
        consultation_id=identity.consultation_id,
        message_key=identity.message_key,
        semantic_fingerprint=identity.semantic_fingerprint,
        current_binding=RuntimeBinding(
            session_alias="WORKER-RECIPIENT",
            binding_id=str(question["recipient_binding"]["binding_id"]),
            binding_generation=int(question["recipient_binding"]["binding_generation"]),
            native_handle="thread-recipient-1",
            reasoning_surface="codex",
        ),
    )
    obligation = extension.obligation()
    return extension, make_delivery_attempt(
        obligation,
        _wake_route_for(obligation, extension),
        attempt_n=1,
    )


def _root_job_id(runtime: Runtime, frame: dict) -> str:
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT j.root_job_id FROM attempts a JOIN jobs j ON j.job_id=a.job_id "
            "WHERE a.attempt_id=?",
            (frame["recipient_actor_ref"]["attempt_id"],),
        ).fetchone()
    assert row is not None
    return row["root_job_id"]


def _wake_route_for(obligation, extension):
    from control_plane.session_targets import SessionTarget, route_obligation

    target = SessionTarget(
        session_alias="WORKER-RECIPIENT",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=True,
    )
    return route_obligation(
        obligation,
        _single_target_registry(target, obligation),
        binding=extension.current_binding,
    )


def _single_target_registry(target, obligation):
    from control_plane.session_targets import SessionTargetRegistry

    return SessionTargetRegistry(
        schema="mastermind.wake_session_targets.v2",
        lifecycle_authority="executive_os",
        production_armed=False,
        policy_version="fixture-v1",
        default_alias_by_seat={"coo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={obligation.root_job_id: {"coo": target.session_alias}},
        targets={target.session_alias: target},
    )


def test_dispatch_and_late_reconciliation_derive_from_exact_wake_attempt(tmp_path):
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )

    from control_plane.wake_ledger import attempt_record, requested_record, LedgerPhase
    from control_plane.wake_persist import WakeLedgerRepository

    extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    repository = WakeLedgerRepository(runtime)

    dispatch = consultations.dispatch_attempt(
        frame,
        wake_attempt=attempt,
        observed_at="2026-09-14T00:01:00Z",
    )
    assert dispatch.event.payload["wake_attempt_command_id"] == attempt.attempt_command_id
    reopened = ConsultationRuntime(_runtime_at(tmp_path), repository_root=tmp_path)
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        reopened.dispatch_attempt(
            frame,
            wake_attempt=attempt,
            observed_at="2026-09-14T00:02:00Z",
        )

    native = reopened.native_accepted(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        wake_attempt_command_id=attempt.attempt_command_id,
        observed_at="2026-09-14T00:03:00Z",
    )
    assert native.inserted is True
    assert reopened.resolve_restart(frame) == "RESOLVED"
    assert sum(
        event.record.phase.value == "DELIVERY_ATTEMPT"
        for event in repository.list_records(extension.obligation().obligation_id)
    ) == 1


def test_answer_identity_expiry_correction_replay_and_atomic_credit(tmp_path):
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    consultations.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:01:00Z"
    )
    consultations.native_accepted(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        wake_attempt_command_id=attempt.attempt_command_id,
        observed_at="2026-09-14T00:02:00Z",
    )
    consultations.consumed_by_recipient(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        observed_at="2026-09-14T00:03:00Z",
    )
    answer = _answer_frame(frame, "v1", semantic_bundle[0])
    foreign = _answer_frame(frame, "foreign", semantic_bundle[0])
    foreign["recipient_actor_ref"]["worker_id"] = "foreign-recipient"
    foreign["fingerprint"] = ""
    foreign = build_consultation(foreign)
    with pytest.raises(StateConflict, match="answer recipient actor drifted"):
        consultations.answer_available(foreign, observed_at="2026-09-14T00:04:00Z")

    available = consultations.answer_available(
        answer, observed_at="2026-09-14T00:04:00Z"
    )
    assert available.event.payload["historical"] is False
    with pytest.raises(StateConflict, match="expired"):
        consultations.consumed_by_requester(
            answer, observed_at="2026-09-16T00:00:01Z"
        )
    late = consultations.answer_available(
        answer, observed_at="2026-09-16T00:00:01Z"
    )
    assert late.inserted is False
    assert late.event.created_at == available.event.created_at

    replay = consultations.answer_available(
        answer, observed_at="2026-09-14T00:05:00Z"
    )
    assert replay.inserted is False
    assert replay.event.created_at == available.event.created_at

    second = _answer_frame(frame, "v2", {**semantic_bundle[0], "second": True})
    refused = consultations.answer_available(
        second, observed_at="2026-09-14T00:06:00Z"
    )
    assert refused.event.event_type == "ANSWER_REFUSED"
    assert refused.event.payload["historical"] is True
    with pytest.raises(StateConflict, match="reserved answer"):
        consultations.consumed_by_requester(
            second, observed_at="2026-09-14T00:06:30Z"
        )

    correction = _answer_frame(frame, "correction", semantic_bundle[0])
    correction["purpose"] = "CORRECTION"
    correction["supersedes_message_key"] = answer["message_key"]
    correction["fingerprint"] = ""
    correction = build_consultation(correction)
    corrected = consultations.answer_available(
        correction, observed_at="2026-09-14T00:07:00Z", historical=True
    )
    assert corrected.event.event_type == "ANSWER_AVAILABLE"
    assert corrected.event.payload["historical"] is True
    assert corrected.event.payload["supersedes_message_key"] == answer["message_key"]
    with pytest.raises(StateConflict, match="historical"):
        consultations.consumed_by_requester(
            correction, observed_at="2026-09-14T00:07:30Z"
        )


def test_correction_requires_its_exact_answer_predecessor(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)
    consultations.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:01:00Z"
    )
    consultations.native_accepted(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        wake_attempt_command_id=attempt.attempt_command_id,
        observed_at="2026-09-14T00:02:00Z",
    )
    consultations.consumed_by_recipient(
        frame,
        native_thread_id="thread-recipient-1",
        native_turn_id="turn-recipient",
        observed_at="2026-09-14T00:03:00Z",
    )
    answer = _answer_frame(frame, "v1", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")

    forged = _answer_frame(frame, "forged", semantic_bundle[0])
    forged["purpose"] = "CORRECTION"
    forged["supersedes_message_key"] = "asd-consultation-foreign-0001"
    forged["fingerprint"] = ""
    forged = build_consultation(forged)
    with pytest.raises(StateConflict, match="exact predecessor"):
        consultations.answer_available(forged, observed_at="2026-09-14T00:05:00Z")
    assert forged["message_key"] not in {
        event.payload.get("message_key", event.payload.get("refused_message_key"))
        for event in consultations.events(frame)
    }

    replacement = _answer_frame(frame, "replacement", semantic_bundle[0])
    replacement["purpose"] = "CORRECTION"
    replacement["supersedes_message_key"] = answer["message_key"]
    replacement["fingerprint"] = ""
    replacement = build_consultation(replacement)
    historical = consultations.answer_available(
        replacement, observed_at="2026-09-14T00:06:00Z", historical=True
    )
    assert historical.event.payload["historical"] is True

    competing = _answer_frame(frame, "competing", semantic_bundle[0])
    competing["purpose"] = "CORRECTION"
    competing["supersedes_message_key"] = answer["message_key"]
    competing["fingerprint"] = ""
    competing = build_consultation(competing)
    with pytest.raises(StateConflict, match="chain is not deterministic"):
        consultations.answer_available(
            competing, observed_at="2026-09-14T00:07:00Z", historical=True
        )


def test_native_acceptance_requires_the_exact_wake_attempt(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = ConsultationRuntime(runtime, repository_root=tmp_path)
    (
        (requester_job, requester_attempt, _requester_worker, _requester_binding),
        (recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
        _root,
    ) = _workers(runtime)
    frame, _semantic_bundle = _frame(
        tmp_path,
        requester=(requester_job, requester_attempt, _requester_worker, _requester_binding),
        recipient=(recipient_job, recipient_attempt, _recipient_worker, recipient_binding),
    )
    consultations.intent(
        frame,
        requester_attempt_id=requester_attempt,
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=_semantic_bundle[1],
    )
    _extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)
    dispatch = consultations.dispatch_attempt(
        frame, wake_attempt=attempt, observed_at="2026-09-14T00:01:00Z"
    )
    assert dispatch.event.payload["wake_attempt_command_id"] == attempt.attempt_command_id

    with pytest.raises(StateConflict, match="Wake attempt"):
        consultations.native_accepted(
            frame,
            native_thread_id="thread-recipient-1",
            native_turn_id="turn-recipient",
            observed_at="2026-09-14T00:02:00Z",
            wake_attempt_command_id="wake:foreign",
        )

def test_consultation_fits_pr600_policy_arithmetic(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    _requester, _recipient, root = _workers(runtime)
    children = [
        job
        for job in runtime.jobs.list_jobs()
        if job.parent_job_id == root
        and job.orchestration_role == "work"
    ]
    assert len(children) == 2
    assert all(job.depth == 1 for job in children)
    assert len(children) <= 16
