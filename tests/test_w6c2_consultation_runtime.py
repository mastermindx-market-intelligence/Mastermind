from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    build_consultation,
    validate_consultation,
)
from control_plane.consultation_runtime import (
    ConsultationConflict,
    ConsultationRuntime,
    _consultation_intent_payload,
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
from control_plane.wake_ledger import LedgerPhase, attempt_record
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    ConsultationWakeExtension,
)


QUESTION = (
    "From the exact accepted source revision, what is the closed Company MCP "
    "consultation input schema and which caller-supplied fields must be refused?"
)


@dataclass
class _ManualClock:
    value: str

    def __call__(self) -> str:
        return self.value


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


def _consultations(
    runtime: Runtime,
    repository_root: Path,
    *,
    clock: _ManualClock | None = None,
) -> ConsultationRuntime:
    return ConsultationRuntime(
        runtime,
        repository_root=repository_root,
        _clock=clock or _ManualClock("2026-09-14T00:00:00Z"),
    )


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


def _wake_records(runtime: Runtime, extension):
    return WakeLedgerRepository(runtime).list_records(
        extension.obligation().obligation_id
    )


def _credited_path(runtime: Runtime, consultations: ConsultationRuntime, frame: dict):
    from control_plane.wake_ledger import (
        AckMode,
        TrustedAckContext,
        ack_record,
        acknowledge,
    )

    extension, attempt = _persisted_wake_attempt(
        runtime, consultations, frame
    )
    obligation = extension.obligation()
    delivered = attempt_record(attempt, LedgerPhase.DELIVERED)
    ack = acknowledge(
        obligation,
        trusted=TrustedAckContext(
            ack_mode=AckMode.REASONING_SESSION,
            target_seat=obligation.declared_target_seat,
            session_alias=attempt.session_alias,
            reasoning_surface=attempt.reasoning_surface,
            binding_id=attempt.binding_id,
            binding_generation=attempt.binding_generation,
            acknowledged_at="2026-09-14T00:03:00Z",
        ),
        claimed_obligation_ids=(obligation.obligation_id,),
        delivered_command_id=delivered.command_id,
    )
    WakeLedgerRepository(runtime).append_records_atomic(
        [
            (delivered, obligation),
            (ack_record(obligation, ack), obligation),
        ]
    )
    return extension, attempt


def test_runtime_binding_id_grammar_accepts_exact_runtime_ids(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
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
    assert intent.event.payload["consultation_schema"] == CONSULTATION_SCHEMA
    assert len(frame["recipient_binding"]["binding_id"]) == 45


def test_r1_repair_discriminators(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )

    blank = copy.deepcopy(frame)
    blank["fingerprint"] = ""
    with pytest.raises(StateConflict, match="nonblank fingerprint"):
        consultations.intent(
            blank,
            requester_attempt_id=workers[0][1],
            carrier_ref="dialogue://fixture/consultation",
            observed_at="2026-09-14T00:01:00Z",
            repository_root=semantic_bundle[1],
        )
    assert len(list(runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=blank["consultation_id"]
    ))) == 1

    extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)
    assert consultations.resolve_restart(frame) == "RECONCILIATION_REQUIRED"
    assert not hasattr(consultations, "dispatch_attempt")
    assert not hasattr(consultations, "native_accepted")

    answer = _answer_frame(frame, "r1", semantic_bundle[0])
    with pytest.raises(StateConflict):
        consultations.answer_available(answer, observed_at="2026-09-14T00:05:00Z")


def test_r1_v1_contract_fixture_accepts_original_answer_shape(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    raw = copy.deepcopy(frame)
    raw.update(
        {
            "message_key": "asd-consultation-original-answer",
            "purpose": "ANSWER",
            "question": None,
            "answer": {
                "text": json.dumps(semantic_bundle[0], sort_keys=True),
                "evidence_refs": frame["evidence_refs"],
            },
            "fingerprint": "",
        }
    )
    raw["correlation"]["request_message_key"] = raw["message_key"]
    item = validate_consultation(build_consultation(raw))
    assert item["schema"] == CONSULTATION_SCHEMA
    assert "question_message_key" not in item
    assert item["correlation"]["request_message_key"] == item["message_key"]


def test_r1_wake_projection_and_exact_answer_transaction(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _extension, _attempt = _credited_path(runtime, consultations, frame)

    answer = _answer_frame(frame, "exact", semantic_bundle[0])
    available = consultations.answer_available(
        answer, observed_at="2026-09-14T00:04:00Z"
    )
    assert available.event.payload["historical"] is False

    foreign = _answer_frame(frame, "foreign", semantic_bundle[0])
    foreign["requester_actor_ref"]["worker_id"] = "foreign-requester"
    foreign["fingerprint"] = ""
    foreign = build_consultation(foreign)
    with pytest.raises(StateConflict):
        consultations.consumed_by_requester(
            foreign,
            requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-14T00:05:00Z",
        )

    consumed = consultations.consumed_by_requester(
        answer,
        requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
        observed_at="2026-09-14T00:06:00Z",
    )
    assert consumed.event.payload["answer_fingerprint"] == answer["fingerprint"]








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


def _distinct_question_frame(frame: dict, suffix: str) -> dict:
    digest = hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:32]
    changed = copy.deepcopy(frame)
    changed["message_key"] = f"asd-consultation-{digest}"
    changed["consultation_id"] = f"consult-{digest}"
    changed["recipient_peer_ref"] = f"peer-{digest}"
    changed["correlation"]["request_message_key"] = changed["message_key"]
    changed["correlation"]["consultation_id"] = changed["consultation_id"]
    changed["fingerprint"] = ""
    return build_consultation(changed)


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
    raw["schema"] = CONSULTATION_V2_SCHEMA
    raw["question_message_key"] = frame["message_key"]
    raw["fingerprint"] = ""
    return build_consultation(raw)


def test_stale_recipient_binding_is_refused_before_receipt(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
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
    consultations = _consultations(runtime, tmp_path)
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
            session_alias="CONSULTATION-RECIPIENT",
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
        session_alias="CONSULTATION-RECIPIENT",
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











def _setup_canonical_intent(
    tmp_path: Path, *, clock: _ManualClock | None = None
):
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path, clock=clock)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    return runtime, consultations, workers, frame, semantic_bundle


def _append_delivered_only(runtime: Runtime, extension, attempt):
    obligation = extension.obligation()
    delivered = attempt_record(attempt, LedgerPhase.DELIVERED)
    WakeLedgerRepository(runtime).append_records_atomic([(delivered, obligation)])
    return obligation, delivered


def _append_target_ack(runtime: Runtime, obligation, attempt, delivered) -> None:
    from control_plane.wake_ledger import (
        AckMode,
        TrustedAckContext,
        ack_record,
        acknowledge,
    )

    ack = acknowledge(
        obligation,
        trusted=TrustedAckContext(
            ack_mode=AckMode.REASONING_SESSION,
            target_seat=obligation.declared_target_seat,
            session_alias=attempt.session_alias,
            reasoning_surface=attempt.reasoning_surface,
            binding_id=attempt.binding_id,
            binding_generation=attempt.binding_generation,
            acknowledged_at="2026-09-14T00:03:00Z",
        ),
        claimed_obligation_ids=(obligation.obligation_id,),
        delivered_command_id=delivered.command_id,
    )
    WakeLedgerRepository(runtime).append_records_atomic(
        [(ack_record(obligation, ack), obligation)]
    )


def test_canonical_wake_state_projection_and_ack_gate(tmp_path: Path) -> None:
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path)
    )

    assert consultations.resolve_restart(frame) == "NOT_SEEN"
    projection = consultation_projection(runtime)
    assert len(projection) == 1
    assert projection[0]["current_wake_state"] == "NOT_SEEN"
    assert projection[0]["wake_state"] == consultations.resolve_restart(frame)
    assert projection[0]["blocker"] == "NOT_SEEN"

    extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)
    assert consultations.resolve_restart(frame) == "RECONCILIATION_REQUIRED"
    projection = consultation_projection(runtime)[0]
    assert projection["wake_state"] == "RECONCILIATION_REQUIRED"
    assert projection["blocker"] == "RECONCILIATION_REQUIRED"

    obligation, delivered = _append_delivered_only(runtime, extension, attempt)
    assert consultations.resolve_restart(frame) == "DELIVERED_UNACKNOWLEDGED"
    projection = consultation_projection(runtime)[0]
    assert projection["wake_state"] == "DELIVERED_UNACKNOWLEDGED"
    assert projection["blocker"] == "DELIVERED_UNACKNOWLEDGED"
    answer = _answer_frame(frame, "ack-gate", semantic_bundle[0])
    with pytest.raises(StateConflict, match="TARGET_ACKNOWLEDGED"):
        consultations.answer_available(answer, observed_at="2026-09-14T00:02:00Z")

    _append_target_ack(runtime, obligation, attempt, delivered)
    assert consultations.resolve_restart(frame) == "TARGET_ACKNOWLEDGED"
    projection = consultation_projection(runtime)[0]
    assert projection["wake_state"] == "TARGET_ACKNOWLEDGED"
    assert projection["blocker"] is None
    assert set(projection) == {
        "consultation_id",
        "sender_digest",
        "recipient_digest",
        "question_digest",
        "evidence_revision_digest",
        "current_wake_state",
        "wake_state",
        "deadline",
        "blocker",
    }

    available = consultations.answer_available(
        answer, observed_at="2026-09-14T00:04:00Z"
    )
    consumed = consultations.consumed_by_requester(
        answer,
        requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
        observed_at="2026-09-14T00:05:00Z",
    )
    assert available.event.payload["historical"] is False
    assert consumed.event.payload["answer_fingerprint"] == answer["fingerprint"]


def test_failed_and_source_resolved_wake_states_never_credit_answer(tmp_path: Path) -> None:
    failed_root = tmp_path / "failed"
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(failed_root)
    )
    extension, attempt = _persisted_wake_attempt(runtime, consultations, frame)
    WakeLedgerRepository(runtime).append_records_atomic(
        [(attempt_record(attempt, LedgerPhase.FAILED), extension.obligation())]
    )
    assert consultations.resolve_restart(frame) == "ATTEMPTED"
    projection = consultation_projection(runtime)[0]
    assert projection["wake_state"] == "ATTEMPTED"
    assert projection["blocker"] == "ATTEMPTED"
    with pytest.raises(StateConflict, match="TARGET_ACKNOWLEDGED"):
        consultations.answer_available(
            _answer_frame(frame, "failed", semantic_bundle[0]),
            observed_at="2026-09-14T00:04:00Z",
        )

    resolved_root = tmp_path / "resolved"
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(resolved_root)
    )
    extension, attempt = _credited_path(runtime, consultations, frame)
    from control_plane.wake_ledger import (
        SourceReadHealth,
        expected_resolution_code,
        resolve_source,
        resolved_record,
    )

    obligation = extension.obligation()
    resolution = resolve_source(
        obligation,
        code=expected_resolution_code(obligation),
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        snapshot_digest="a" * 16,
        resolved_at="2026-09-14T00:04:00Z",
    )
    WakeLedgerRepository(runtime).append_records_atomic(
        [(resolved_record(obligation, resolution), obligation)]
    )
    assert consultations.resolve_restart(frame) == "SOURCE_RESOLVED"
    with pytest.raises(StateConflict, match="TARGET_ACKNOWLEDGED"):
        consultations.answer_available(
            _answer_frame(frame, "resolved", semantic_bundle[0]),
            observed_at="2026-09-14T00:05:00Z",
        )


def test_wake_route_and_current_binding_are_exact_authority(tmp_path: Path) -> None:
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path / "forged")
    )
    from control_plane.wake_ledger import requested_record

    extension, attempt = _wake_route(runtime, frame)
    forged = replace(attempt, binding_generation=attempt.binding_generation + 1)
    obligation = extension.obligation()
    WakeLedgerRepository(runtime).append_records_atomic(
        [
            (requested_record(obligation), obligation),
            (attempt_record(forged, LedgerPhase.DELIVERY_ATTEMPT), None),
        ]
    )
    with pytest.raises(StateConflict, match="current RuntimeBinding"):
        consultations.resolve_restart(frame)
    assert {event.event_type for event in consultations.events(frame)} == {"INTENT"}

    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path / "stale")
    )
    _credited_path(runtime, consultations, frame)
    _release_recipient_writer(runtime)
    answer = _answer_frame(frame, "stale", semantic_bundle[0])
    with pytest.raises(StateConflict, match="current|actionable|binding|writer"):
        consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    assert "ANSWER_AVAILABLE" not in {
        event.event_type for event in consultations.events(frame)
    }


def test_answer_identity_replay_conflict_and_exact_consumption(tmp_path: Path) -> None:
    drift_cases = (
        "requester_actor_ref",
        "recipient_actor_ref",
        "recipient_peer_ref",
        "recipient_binding",
        "correlation",
        "artifact_revisions",
    )
    for index, field in enumerate(drift_cases, start=1):
        root = tmp_path / f"drift-{field}"
        runtime, consultations, _workers_value, frame, semantic_bundle = (
            _setup_canonical_intent(root)
        )
        _credited_path(runtime, consultations, frame)
        answer = _answer_frame(frame, f"d{index}", semantic_bundle[0])
        changed = copy.deepcopy(answer)
        if field in {"requester_actor_ref", "recipient_actor_ref"}:
            changed[field]["worker_id"] = f"foreign-{field}"
        elif field == "recipient_peer_ref":
            changed[field] = "peer-foreign-answer-0001"
        elif field == "recipient_binding":
            changed[field]["binding_generation"] += 1
        elif field == "correlation":
            changed[field]["parent_fingerprint"] = "d" * 64
        else:
            changed[field][0]["content_sha256"] = "e" * 64
        changed["fingerprint"] = ""
        changed = build_consultation(changed)
        with pytest.raises(StateConflict):
            consultations.answer_available(
                changed, observed_at="2026-09-14T00:04:00Z"
            )
        assert "ANSWER_AVAILABLE" not in {
            event.event_type for event in consultations.events(frame)
        }

    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path / "reservation")
    )
    _credited_path(runtime, consultations, frame)
    answer_a = _answer_frame(frame, "a", semantic_bundle[0])
    first = consultations.answer_available(
        answer_a, observed_at="2026-09-14T00:04:00Z"
    )
    replay = consultations.answer_available(
        answer_a, observed_at="2026-09-14T00:09:00Z"
    )
    assert replay.inserted is False
    assert replay.event.created_at == first.event.created_at
    assert replay.event.payload["observed_at"] == first.event.payload["observed_at"]

    changed_a = copy.deepcopy(answer_a)
    changed_semantic = json.loads(changed_a["answer"]["text"])
    changed_semantic["variant"] = "changed"
    changed_a["answer"]["text"] = json.dumps(
        changed_semantic, sort_keys=True, separators=(",", ":")
    )
    changed_a["fingerprint"] = ""
    changed_a = build_consultation(changed_a)
    with pytest.raises(ConsultationConflict, match="CONFLICT|conflict"):
        consultations.answer_available(
            changed_a, observed_at="2026-09-14T00:05:00Z"
        )

    answer_b = _answer_frame(frame, "b", semantic_bundle[0])
    refused = consultations.answer_available(
        answer_b, observed_at="2026-09-14T00:06:00Z"
    )
    assert refused.event.event_type == "ANSWER_REFUSED"
    with pytest.raises(StateConflict, match="exact reserved answer"):
        consultations.consumed_by_requester(
            answer_b,
            requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-14T00:07:00Z",
        )

    consumed = consultations.consumed_by_requester(
        answer_a,
        requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
        observed_at="2026-09-14T00:07:00Z",
    )
    replay_consumed = consultations.consumed_by_requester(
        answer_a,
        requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
        observed_at="2026-09-14T00:08:00Z",
    )
    assert replay_consumed.inserted is False
    assert replay_consumed.event.created_at == consumed.event.created_at


def test_concurrent_answers_reserve_exactly_one_current_answer(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    import threading

    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path)
    )
    _credited_path(runtime, consultations, frame)
    answers = (
        _answer_frame(frame, "race-a", semantic_bundle[0]),
        _answer_frame(frame, "race-b", semantic_bundle[0]),
    )
    barrier = threading.Barrier(2)

    def reserve(answer):
        local = _consultations(_runtime_at(tmp_path), tmp_path)
        barrier.wait()
        return local.answer_available(answer, observed_at="2026-09-14T00:04:00Z")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(reserve, answers))
    assert sorted(result.event.event_type for result in results) == [
        "ANSWER_AVAILABLE",
        "ANSWER_REFUSED",
    ]
    current = [
        event
        for event in consultations.events(frame)
        if event.event_type == "ANSWER_AVAILABLE"
        and event.payload.get("historical") is False
    ]
    assert len(current) == 1


def test_deadline_and_correction_history_never_receive_current_credit(tmp_path: Path) -> None:
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(
            tmp_path / "late",
            clock=_ManualClock("2026-09-16T00:00:00Z"),
        )
    )
    _credited_path(runtime, consultations, frame)
    late = _answer_frame(frame, "late", semantic_bundle[0])
    result = consultations.answer_available(
        late, observed_at="2026-09-16T00:00:00Z"
    )
    assert result.event.payload["historical"] is True
    with pytest.raises(StateConflict, match="expired|historical"):
        consultations.consumed_by_requester(
            late,
            requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-16T00:01:00Z",
        )

    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path / "correction")
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "original", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")

    correction = copy.deepcopy(answer)
    correction["message_key"] = "asd-consultation-correction-0001"
    correction["purpose"] = "CORRECTION"
    correction["supersedes_message_key"] = answer["message_key"]
    corrected_semantic = json.loads(correction["answer"]["text"])
    corrected_semantic["revision"] = 1
    correction["answer"]["text"] = json.dumps(
        corrected_semantic, sort_keys=True, separators=(",", ":")
    )
    correction["fingerprint"] = ""
    correction = build_consultation(correction)
    corrected = consultations.answer_available(
        correction, observed_at="2026-09-14T00:05:00Z"
    )
    assert corrected.event.payload["historical"] is True
    with pytest.raises(ConsultationConflict, match="historical"):
        consultations.consumed_by_requester(
            correction,
            requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-14T00:06:00Z",
        )

    second = copy.deepcopy(correction)
    second["message_key"] = "asd-consultation-correction-0002"
    second_semantic = json.loads(second["answer"]["text"])
    second_semantic["revision"] = 2
    second["answer"]["text"] = json.dumps(
        second_semantic, sort_keys=True, separators=(",", ":")
    )
    second["fingerprint"] = ""
    second = build_consultation(second)
    with pytest.raises(StateConflict, match="deterministic"):
        consultations.answer_available(
            second, observed_at="2026-09-14T00:07:00Z"
        )


def test_alternate_consultation_provider_ingress_is_absent() -> None:
    import control_plane.remote_codex_operator_adapter as remote_adapter
    from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION
    from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION

    assert not hasattr(remote_adapter, "CodexConsultationIngress")
    assert not hasattr(remote_adapter, "ConsultationIngressRefused")
    assert not hasattr(remote_adapter, "ConsultationIngressUnavailable")
    assert CODEX_WAKE_INSTRUCTION == ATTENTION_TURN_INSTRUCTION


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

def test_trusted_clock_prevents_caller_backdating_current_credit(tmp_path: Path) -> None:
    clock = _ManualClock("2026-09-14T00:00:00Z")
    runtime = _runtime_at(tmp_path / "availability")
    consultations = ConsultationRuntime(
        runtime, repository_root=tmp_path / "availability", _clock=clock
    )
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path / "availability", requester=workers[0], recipient=workers[1]
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "trusted-clock-late", semantic_bundle[0])

    clock.value = "2026-09-16T00:00:00Z"
    available = consultations.answer_available(
        answer, observed_at="2026-09-14T00:04:00Z"
    )
    assert available.event.payload["historical"] is True
    assert available.event.payload["observed_at"] == clock.value
    with pytest.raises(StateConflict, match="expired"):
        consultations.consumed_by_requester(
            answer,
            requester_attempt_id=frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-14T00:05:00Z",
        )

    consume_clock = _ManualClock("2026-09-14T00:00:00Z")
    consume_runtime = _runtime_at(tmp_path / "consumption")
    consume_consultations = ConsultationRuntime(
        consume_runtime, repository_root=tmp_path / "consumption", _clock=consume_clock
    )
    consume_workers = _workers(consume_runtime)
    consume_frame, consume_semantic = _frame(
        tmp_path / "consumption",
        requester=consume_workers[0],
        recipient=consume_workers[1],
    )
    consume_consultations.intent(
        consume_frame,
        requester_attempt_id=consume_workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=consume_semantic[1],
    )
    _credited_path(consume_runtime, consume_consultations, consume_frame)
    current_answer = _answer_frame(
        consume_frame, "trusted-clock-consume", consume_semantic[0]
    )
    consume_consultations.answer_available(
        current_answer, observed_at="2026-09-14T00:04:00Z"
    )
    consume_clock.value = "2026-09-16T00:00:00Z"
    with pytest.raises(StateConflict, match="expired"):
        consume_consultations.consumed_by_requester(
            current_answer,
            requester_attempt_id=consume_frame["requester_actor_ref"]["attempt_id"],
            observed_at="2026-09-14T00:05:00Z",
        )

def test_trusted_clock_regression_cannot_reopen_expired_credit(tmp_path: Path) -> None:
    clock = _ManualClock("2026-09-14T00:00:00Z")
    runtime, consultations, _workers_value, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path, clock=clock)
    )
    _credited_path(runtime, consultations, frame)

    clock.value = "2026-09-16T00:00:00Z"
    historical = consultations.answer_available(
        _answer_frame(frame, "historical-before-regression", semantic_bundle[0]),
        observed_at="2026-09-14T00:04:00Z",
    )
    assert historical.event.payload["historical"] is True

    clock.value = "2026-09-14T00:10:00Z"
    with pytest.raises(StateConflict, match="clock regressed"):
        consultations.answer_available(
            _answer_frame(frame, "must-not-reopen", semantic_bundle[0]),
            observed_at="2026-09-14T00:05:00Z",
        )


def test_malformed_trusted_clock_fails_before_durable_receipt(tmp_path: Path) -> None:
    for index, malformed in enumerate(("::Z", "9999-99-99T99:99:99Z")):
        root = tmp_path / f"malformed-{index}"
        clock = _ManualClock(malformed)
        runtime = _runtime_at(root)
        consultations = _consultations(runtime, root, clock=clock)
        workers = _workers(runtime)
        frame, semantic_bundle = _frame(
            root, requester=workers[0], recipient=workers[1]
        )
        with pytest.raises(StateConflict, match="UTC timestamp"):
            consultations.intent(
                frame,
                requester_attempt_id=workers[0][1],
                carrier_ref="dialogue://fixture/consultation",
                observed_at="2026-09-14T00:00:00Z",
                repository_root=semantic_bundle[1],
            )
        assert runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=frame["consultation_id"]
        ) == []


def test_restart_projection_survive_released_writer_and_isolate_bad_rows(
    tmp_path: Path,
) -> None:
    runtime, consultations, workers, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path)
    )
    second = _distinct_question_frame(frame, "second-projection-row")
    consultations.intent(
        second,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation-second",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    _release_recipient_writer(runtime)

    assert consultations.resolve_restart(frame) == "TARGET_ACKNOWLEDGED"
    rows = {row["consultation_id"]: row for row in consultation_projection(runtime)}
    assert rows[frame["consultation_id"]]["wake_state"] == "TARGET_ACKNOWLEDGED"
    assert rows[frame["consultation_id"]]["blocker"] is None
    assert rows[second["consultation_id"]]["wake_state"] == "NOT_SEEN"
    with pytest.raises(StateConflict, match="current|actionable|binding|writer"):
        consultations.answer_available(
            _answer_frame(frame, "released-writer", semantic_bundle[0]),
            observed_at="2026-09-14T00:04:00Z",
        )

    isolated_root = tmp_path / "isolated-bad-row"
    isolated_runtime, isolated_consultations, isolated_workers, good, isolated_semantic = (
        _setup_canonical_intent(isolated_root)
    )
    bad = _distinct_question_frame(good, "bad-projection-row")
    isolated_consultations.intent(
        bad,
        requester_attempt_id=isolated_workers[0][1],
        carrier_ref="dialogue://fixture/consultation-bad",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=isolated_semantic[1],
    )
    from control_plane.wake_ledger import requested_record

    extension, attempt = _wake_route(isolated_runtime, bad)
    forged = replace(attempt, binding_generation=attempt.binding_generation + 1)
    obligation = extension.obligation()
    WakeLedgerRepository(isolated_runtime).append_records_atomic(
        [
            (requested_record(obligation), obligation),
            (attempt_record(forged, LedgerPhase.DELIVERY_ATTEMPT), None),
        ]
    )
    isolated_rows = {
        row["consultation_id"]: row
        for row in consultation_projection(isolated_runtime)
    }
    assert isolated_rows[good["consultation_id"]]["wake_state"] == "NOT_SEEN"
    assert isolated_rows[bad["consultation_id"]]["wake_state"] == (
        "RECONCILIATION_REQUIRED"
    )
    assert isolated_rows[bad["consultation_id"]]["blocker"] == (
        "WAKE_STATE_UNAVAILABLE"
    )


def test_requester_consumption_requires_exact_calling_attempt(tmp_path: Path) -> None:
    runtime, consultations, workers, frame, semantic_bundle = (
        _setup_canonical_intent(tmp_path)
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "authenticated-consumption", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")

    with pytest.raises(StateConflict, match="requester actor"):
        consultations.consumed_by_requester(
            answer,
            requester_attempt_id=workers[1][1],
            observed_at="2026-09-14T00:05:00Z",
        )
    consumed = consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )
    assert consumed.event.payload["requester_actor_ref"]["attempt_id"] == workers[0][1]


def test_intent_payload_requires_explicit_trusted_time_keyword() -> None:
    parameters = inspect.signature(_consultation_intent_payload).parameters

    assert "trusted_observed_at" in parameters
    assert "observed_at" not in parameters


def test_v3_intent_payload_is_exact_while_runtime_admission_stays_dark(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    grok = copy.deepcopy(frame)
    grok["schema"] = GROK_CONSULTATION_SCHEMA
    grok["recipient_binding"]["reasoning_surface"] = "grok-bot"
    grok["fingerprint"] = ""
    grok = build_consultation(grok)

    payload = _consultation_intent_payload(
        grok,
        requester_binding=workers[0][3],
        carrier_ref="dialogue://fixture/grok-identity",
        trusted_observed_at="2026-09-14T00:00:00Z",
    )
    assert payload["consultation_schema"] == GROK_CONSULTATION_SCHEMA
    assert payload["semantic_fingerprint"] == grok["fingerprint"]
    assert payload["recipient_binding"]["reasoning_surface"] == "grok-bot"

    with pytest.raises(StateConflict, match="current Runtime binding"):
        consultations.intent(
            grok,
            requester_attempt_id=workers[0][1],
            carrier_ref="dialogue://fixture/grok-identity",
            observed_at="2026-09-14T00:00:00Z",
            repository_root=semantic_bundle[1],
        )
    assert runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=grok["consultation_id"]
    ) == []


def test_requester_answer_attention_projects_exact_runtime_binding_without_writes(
    tmp_path: Path,
) -> None:
    from control_plane.wake_events import SourceKind, WakeKind

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "requester-attention", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    before = tuple(
        runtime.events.list_events(
            aggregate_type="consultation",
            aggregate_id=frame["consultation_id"],
        )
    )

    projected = consultations.requester_answer_attention(
        answer,
        requester_attempt_id=workers[0][1],
    )

    after = tuple(
        runtime.events.list_events(
            aggregate_type="consultation",
            aggregate_id=frame["consultation_id"],
        )
    )
    assert after == before
    assert projected.identity.consultation_id == frame["consultation_id"]
    assert projected.identity.answer_message_key == answer["message_key"]
    assert projected.identity.answer_fingerprint == answer["fingerprint"]
    assert projected.identity.requester_job_id == workers[0][0]
    assert projected.identity.requester_attempt_id == workers[0][1]
    assert projected.identity.requester_binding_id == workers[0][3]["binding_id"]
    assert projected.identity.requester_binding_generation == workers[0][3][
        "binding_generation"
    ]
    assert projected.identity.requester_reasoning_surface == "codex"
    assert projected.target.session_alias == "CONSULTATION-REQUESTER"
    assert projected.target.target_seat == "coo"
    assert projected.target.reasoning_surface == "codex"
    assert projected.target.wake_transport == "codex-app-server"
    assert projected.binding.binding_id == workers[0][3]["binding_id"]
    assert projected.binding.binding_generation == workers[0][3][
        "binding_generation"
    ]
    assert projected.obligation.wake_kind is WakeKind.CONSULTATION_ANSWER_AVAILABLE
    assert (
        projected.obligation.source_kind
        is SourceKind.CONSULTATION_ANSWER_ATTENTION
    )
    assert projected.obligation.job_id == workers[0][0]
    assert projected.obligation.attempt_id == workers[0][1]
    assert not WakeLedgerRepository(runtime).list_records(
        projected.obligation.obligation_id
    )


def test_requester_answer_attention_refuses_noncurrent_requester_binding(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "stale-requester", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE process_generations SET executive_writer_held=0 "
            "WHERE process_generation_id=("
            "SELECT g.process_generation_id FROM process_generations g "
            "JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id "
            "WHERE e.attempt_id=? ORDER BY g.generation_number DESC LIMIT 1)",
            (workers[0][1],),
        )

    with pytest.raises(StateConflict, match="current actionable OHF writer"):
        consultations.requester_answer_attention(
            answer,
            requester_attempt_id=workers[0][1],
        )


def test_requester_answer_attention_refuses_historical_answer(
    tmp_path: Path,
) -> None:
    clock = _ManualClock("2026-09-14T00:00:00Z")
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path, clock=clock)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    clock.value = "2026-09-16T00:00:00Z"
    answer = _answer_frame(frame, "historical-attention", semantic_bundle[0])
    available = consultations.answer_available(
        answer, observed_at="2026-09-16T00:00:00Z"
    )
    assert available.event.payload["historical"] is True

    with pytest.raises(ConsultationConflict, match="historical answer"):
        consultations.requester_answer_attention(
            answer,
            requester_attempt_id=workers[0][1],
        )
    with pytest.raises(ConsultationConflict, match="historical answer"):
        consultations.requester_answer_attention_replay(
            answer,
            requester_attempt_id=workers[0][1],
        )


def _requester_answer_projection(
    runtime: Runtime,
    consultations: ConsultationRuntime,
    tmp_path: Path,
):
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "extension", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    return consultations.requester_answer_attention(
        answer,
        requester_attempt_id=workers[0][1],
    )


def test_requester_answer_wake_extension_preserves_projection_emitted_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import control_plane.wake_events as wake_events
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    projection = _requester_answer_projection(runtime, consultations, tmp_path)
    repository = WakeLedgerRepository(runtime)
    frozen_emitted_at = projection.obligation.emitted_at

    monkeypatch.setattr(
        wake_events,
        "utc_now_iso",
        lambda now=None: "2099-12-31T23:59:59Z",
    )

    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )

    assert extension.obligation().emitted_at == frozen_emitted_at


def test_requester_answer_wake_extension_binds_exact_projection_and_request(
    tmp_path: Path,
) -> None:
    from control_plane.wake_ledger import requested_record
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    projection = _requester_answer_projection(
        runtime, consultations, tmp_path
    )
    repository = WakeLedgerRepository(runtime)
    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )

    assert extension.obligation() == projection.obligation
    repository.append_record(
        requested_record(extension.obligation()),
        obligation=extension.obligation(),
    )
    assert extension.current_binding_matches()
    records = repository.list_records(extension.obligation().obligation_id)
    assert len(records) == 1
    assert records[0].event.payload["source_ref"] == (
        projection.obligation.source_ref
    )


def test_requester_answer_wake_extension_refuses_binding_or_route_drift(
    tmp_path: Path,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    projection = _requester_answer_projection(
        runtime, consultations, tmp_path
    )
    repository = WakeLedgerRepository(runtime)

    with pytest.raises(StateConflict, match="binding identity"):
        RequesterAnswerWakeExtension(
            repository=repository,
            projection=replace(
                projection,
                binding=replace(
                    projection.binding,
                    binding_generation=projection.binding.binding_generation + 1,
                ),
            ),
        )
    with pytest.raises(StateConflict, match="target route"):
        RequesterAnswerWakeExtension(
            repository=repository,
            projection=replace(
                projection,
                target=replace(
                    projection.target,
                    session_alias="CONSULTATION-RECIPIENT",
                ),
            ),
        )


def test_intent_freezes_original_requester_binding(tmp_path: Path) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )

    intent = consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )

    assert intent.event.payload["schema_version"] == (
        "mastermind.consultation_intent/v2"
    )
    assert intent.event.payload["requester_binding"] == workers[0][3]


def test_requester_answer_attention_refuses_generation_change_after_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "rotated-requester", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    original = Runtime.current_harness_binding_source

    def rotated(self, attempt_id, *, connection=None):
        facts = original(self, attempt_id, connection=connection)
        return replace(
            facts,
            generation_number=facts.generation_number + 1,
        )

    monkeypatch.setattr(Runtime, "current_harness_binding_source", rotated)

    with pytest.raises(StateConflict, match="original requester binding is stale"):
        consultations.requester_answer_attention(
            answer,
            requester_attempt_id=workers[0][1],
        )
    with pytest.raises(StateConflict, match="original requester binding is stale"):
        consultations.requester_answer_attention_replay(
            answer,
            requester_attempt_id=workers[0][1],
        )


def test_requester_answer_attention_refuses_already_consumed_answer(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "already-consumed", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )

    with pytest.raises(ConsultationConflict, match="already consumed"):
        consultations.requester_answer_attention(
            answer,
            requester_attempt_id=workers[0][1],
        )


def test_requester_answer_attention_refuses_unreserved_answer_identity(
    tmp_path: Path,
) -> None:
    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    admitted = _answer_frame(frame, "admitted-answer", semantic_bundle[0])
    consultations.answer_available(
        admitted, observed_at="2026-09-14T00:04:00Z"
    )
    foreign = _answer_frame(frame, "foreign-answer", semantic_bundle[0])

    with pytest.raises(StateConflict, match="one exact admitted answer"):
        consultations.requester_answer_attention(
            foreign,
            requester_attempt_id=workers[0][1],
        )


def test_requester_answer_first_wake_request_refuses_consumed_projection(
    tmp_path: Path,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "consumed-before-first-request", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    projection = consultations.requester_answer_attention(
        answer,
        requester_attempt_id=workers[0][1],
    )
    consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )
    repository = WakeLedgerRepository(runtime)
    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )

    with pytest.raises(ConsultationConflict, match="already consumed"):
        extension.persist_requested_if_current(consultations)
    assert not repository.list_records(projection.obligation.obligation_id)


def test_requester_answer_first_wake_request_refuses_post_projection_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    projection = _requester_answer_projection(runtime, consultations, tmp_path)
    repository = WakeLedgerRepository(runtime)
    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )
    original = Runtime.current_harness_binding_source

    def rotated(self, attempt_id, *, connection=None):
        facts = original(self, attempt_id, connection=connection)
        return replace(
            facts,
            generation_number=facts.generation_number + 1,
        )

    monkeypatch.setattr(Runtime, "current_harness_binding_source", rotated)

    with pytest.raises(StateConflict, match="original requester binding is stale"):
        extension.persist_requested_if_current(consultations)
    assert not repository.list_records(projection.obligation.obligation_id)


def test_requester_answer_first_wake_request_stays_sticky_after_consumption(
    tmp_path: Path,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "request-before-consumption", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    projection = consultations.requester_answer_attention(
        answer,
        requester_attempt_id=workers[0][1],
    )
    repository = WakeLedgerRepository(runtime)
    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )

    first = extension.persist_requested_if_current(consultations)
    assert first.inserted is True
    consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )
    replay = extension.persist_requested_if_current(consultations)

    assert replay.inserted is False
    assert replay.event.event_id == first.event.event_id
    records = repository.list_records(projection.obligation.obligation_id)
    assert len(records) == 1


def test_requester_answer_replay_reconstructs_sticky_request_after_consumption(
    tmp_path: Path,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "sticky-fresh-replay", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    projection = consultations.requester_answer_attention(
        answer,
        requester_attempt_id=workers[0][1],
    )
    repository = WakeLedgerRepository(runtime)
    first_extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=projection,
    )
    first = first_extension.persist_requested_if_current(consultations)
    assert first.inserted is True
    consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )

    replay_projection = consultations.requester_answer_attention_replay(
        answer,
        requester_attempt_id=workers[0][1],
    )
    assert replay_projection.identity == projection.identity
    assert replay_projection.target == projection.target
    assert replay_projection.binding == projection.binding
    assert (
        replay_projection.obligation.obligation_id
        == projection.obligation.obligation_id
    )
    assert (
        replay_projection.obligation.source_ref
        == projection.obligation.source_ref
    )
    replay_extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=replay_projection,
    )
    replay = replay_extension.persist_requested_if_current(consultations)

    assert replay.inserted is False
    assert replay.event.event_id == first.event.event_id
    assert len(repository.list_records(projection.obligation.obligation_id)) == 1


def test_requester_answer_replay_cannot_originate_after_prior_consumption(
    tmp_path: Path,
) -> None:
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        RequesterAnswerWakeExtension,
    )

    runtime = _runtime_at(tmp_path)
    consultations = _consultations(runtime, tmp_path)
    workers = _workers(runtime)
    frame, semantic_bundle = _frame(
        tmp_path,
        requester=workers[0],
        recipient=workers[1],
    )
    consultations.intent(
        frame,
        requester_attempt_id=workers[0][1],
        carrier_ref="dialogue://fixture/consultation",
        observed_at="2026-09-14T00:00:00Z",
        repository_root=semantic_bundle[1],
    )
    _credited_path(runtime, consultations, frame)
    answer = _answer_frame(frame, "no-late-origination", semantic_bundle[0])
    consultations.answer_available(answer, observed_at="2026-09-14T00:04:00Z")
    consultations.consumed_by_requester(
        answer,
        requester_attempt_id=workers[0][1],
        observed_at="2026-09-14T00:05:00Z",
    )

    replay_projection = consultations.requester_answer_attention_replay(
        answer,
        requester_attempt_id=workers[0][1],
    )
    repository = WakeLedgerRepository(runtime)
    extension = RequesterAnswerWakeExtension(
        repository=repository,
        projection=replay_projection,
    )

    with pytest.raises(ConsultationConflict, match="already consumed"):
        extension.persist_requested_if_current(consultations)
    assert not repository.list_records(replay_projection.obligation.obligation_id)
