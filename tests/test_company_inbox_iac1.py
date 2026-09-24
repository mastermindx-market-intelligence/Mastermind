"""IAC-1 Company Inbox journey tests.

These tests run the real ``RuntimeConsultationDispatcher`` through the real
``CompanyConsultationGateway`` over a hermetic Executive Runtime. The shape
of the journey is fixed in ``control_plane/consultation_runtime`` and the
tool surface is frozen in ``integrations/mastermind_company_mcp``.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    build_consultation,
)
from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.company_inbox_projection import (
    COMPANY_INBOX_SCHEMA,
    company_inbox_row,
    project_company_inbox,
)
from control_plane.consultation_runtime import ConsultationRuntime
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    AuthRealmRequirement,
    CapabilityManifest,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    RequestedExecutionProfile,
    WorkspaceIdentity,
)
from control_plane.wake_ledger import LedgerPhase, attempt_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
    CompanyConsultationGateway,
)
from integrations.company_consultation_dispatch import (
    AnswerFrameCarrier,
    CallerIdentity,
    InMemoryAnswerFrameCarrier,
    RecipientBinding,
    RuntimeConsultationDispatcher,
)


PEER_REF = "peer-7bdf4a6f9a664bbcf1a93d67a41ba51d"


def _actor(job: str, attempt: str, worker: str) -> dict[str, str]:
    return {
        "kind": "worker_attempt",
        "job_id": job,
        "attempt_id": attempt,
        "worker_id": worker,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _ManualClock:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


def _runtime_at(root: Path) -> Runtime:
    return Runtime.at(root, lease_seconds=3600)


def _consultations(runtime: Runtime, repository_root: Path) -> ConsultationRuntime:
    return ConsultationRuntime(
        runtime,
        repository_root=repository_root,
        _clock=_ManualClock("2026-09-14T00:00:00Z"),
    )


def _binding(attempt_epoch: str, generation: int = 1) -> dict[str, object]:
    return {
        "binding_id": "bind-" + hashlib.sha256(attempt_epoch.encode()).hexdigest()[:40],
        "binding_generation": generation,
        "reasoning_surface": "codex",
    }


def _profile(lease):
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


def _attestation(profile):
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


def _fixture_repo(root: Path) -> tuple[Path, dict[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "fixture-repo"
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Fixture"], cwd=repo, check=True
    )
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
    return repo, revision


def _profile_per_attempt(runtime: Runtime, dispatch_outcome, provider_session):
    attempt = dispatch_outcome.attempt
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
    from control_plane.operator_harness_contract import ProcessIdentityObservation

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
    from control_plane.executive_orchestration_principal import (
        OperatorPrincipalObservation,
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
    return sealed, epoch, generation, process


def _complete_planner(runtime, dispatch, plan_body, sealed, epoch, generation, process):
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
    assert job is not None
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
        "role_result": plan_body,
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


def _workers(
    runtime: Runtime,
) -> tuple[
    tuple[str, str, str, dict[str, object]],
    tuple[str, str, str, dict[str, object]],
    tuple[str, str, str, dict[str, object]],
    str,
]:
    for worker_id in (
        "consultation-requester",
        "consultation-recipient",
    ):
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
            "objective": "Support three exact current consultation writers.",
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
    planner_dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="consultation-requester",
    )
    assert planner_dispatch is not None and planner_dispatch.lease_token is not None

    sealed_p, epoch_p, generation_p, process_p = _profile_per_attempt(
        runtime, planner_dispatch, "thread-planner"
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
    _complete_planner(
        runtime,
        planner_dispatch,
        plan_body,
        sealed_p,
        epoch_p,
        generation_p,
        process_p,
    )
    works = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{planner_dispatch.attempt.attempt_id}"
        ),
    )
    assert len(works) == 2
    labels = [
        "consultation-requester",
        "consultation-recipient",
    ]
    result = []
    for index, work in enumerate(works):
        work_dispatch = runtime.attempts.dispatch_cycle_job(
            work.job_id,
            command_id=(
                f"coo-cycle:{root.job_id}:dispatch:{work.job_id}:attempt:1"
            ),
            worker_id=labels[index],
        )
        assert work_dispatch is not None and work_dispatch.lease_token is not None
        _profile_per_attempt(runtime, work_dispatch, f"thread-recipient-{index}")
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
    third_pair = _register_third_worker(runtime)
    return tuple(result) + (third_pair, root.job_id)


def _register_third_worker(runtime: Runtime):
    """Register a third non-party worker without going through the plan."""
    runtime.workers.register_worker(
        "consultation-third",
        provider="openai-codex",
        account_label="consultation-third@example.invalid",
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
    return (
        "JOB-THIRD",
        "ATT-THIRD",
        "consultation-third",
        _binding("rotated-third-binding", 1),
    )


def _recipient_resolver(recipient: tuple) -> Any:
    recipient_job, recipient_attempt, recipient_worker, recipient_binding = recipient

    def _resolve(peer_ref: str) -> RecipientBinding:
        return RecipientBinding(
            actor_ref={
                "kind": "worker_attempt",
                "job_id": recipient_job,
                "attempt_id": recipient_attempt,
                "worker_id": recipient_worker,
            },
            recipient_binding=dict(recipient_binding),
        )

    return _resolve


def _make_dispatcher(
    runtime: Runtime,
    repository_root: Path,
    *,
    requester: tuple,
    recipient: tuple,
    clock_value: str = "2026-09-14T00:00:00Z",
    answer_frames: AnswerFrameCarrier | None = None,
) -> RuntimeConsultationDispatcher:
    caller = CallerIdentity(
        worker_id=requester[2],
        attempt_id=requester[1],
        reasoning_surface="codex",
        binding=requester[3],
        job_id=requester[0],
    )
    return RuntimeConsultationDispatcher(
        runtime=runtime,
        repository_root=repository_root,
        caller=caller,
        recipients=_recipient_resolver(recipient),
        answer_frames=answer_frames or InMemoryAnswerFrameCarrier(),
        _clock=_ManualClock(clock_value),
    )


class _ConsultationPeerLike:
    def __init__(self, peer_ref: str, display_name: str, schema: str, binding: dict) -> None:
        self.peer_ref = peer_ref
        self.display_name = display_name
        self._consultation_schema = schema
        self._public_projection = {"peer_ref": peer_ref, "display_name": display_name}
        self.binding = binding

    @property
    def consultation_schema(self) -> str:
        return self._consultation_schema

    def public_projection(self) -> dict:
        return dict(self._public_projection)


class _GatewayResolver:
    """Resolve peers through the frozen ``CompanyConsultationGateway``.

    The gateway still needs a real resolver so it can format the
    ``company.consult`` dispatch request. It only reads
    ``peer.public_projection()`` and ``peer.consultation_schema``; the
    actual recipient resolution is performed by the dispatcher's
    injected recipient resolver.
    """

    def __init__(self, peer_ref: str, binding: dict) -> None:
        self.peers = [
            _ConsultationPeerLike(
                peer_ref=peer_ref,
                display_name="Peer B",
                schema=CONSULTATION_SCHEMA,
                binding=binding,
            )
        ]

    def resolve(self, alias: str, *, program_ref: str):
        for peer in self.peers:
            if peer.peer_ref.lower() == alias.strip().lower():
                return peer
        from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
            ConsultationPeerRefused,
        )

        raise ConsultationPeerRefused("UNAVAILABLE")


def _gateway_with_dispatcher(
    dispatcher: RuntimeConsultationDispatcher,
    *,
    peer_ref: str = PEER_REF,
    recipient_binding: dict | None = None,
):
    binding = recipient_binding or {}
    return CompanyConsultationGateway(
        peer_resolver=_GatewayResolver(peer_ref, binding),
        dispatcher=dispatcher,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-14T00:00:00Z",
    )


def _run(coroutine):
    return asyncio.run(coroutine)


def _evidence_for(runtime, consultation_id):
    events = runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    )
    by_type: dict[str, list[int]] = {}
    for event in events:
        by_type.setdefault(event.event_type, []).append(event.event_id)
    return by_type


def _credit_wake_path(runtime, consultation_id):
    """Append WAKE_REQUESTED/DELIVERY_ATTEMPT/DELIVERED/ACK records so the
    obligation reaches TARGET_ACKNOWLEDGED — mirrors the runtime
    test helper but reuses the persisted INTENT to derive the frame.
    """
    from control_plane.session_targets import RuntimeBinding
    from control_plane.dialogue_source_resolution import (
        ConsultationSourceIdentity,
    )
    from control_plane.session_targets import (
        SessionTarget,
        route_obligation,
        SessionTargetRegistry,
    )
    from control_plane.wake_ledger import (
        AckMode,
        TrustedAckContext,
        ack_record,
        acknowledge,
        make_delivery_attempt,
        requested_record,
    )
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        ConsultationWakeExtension,
    )

    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT * FROM events WHERE aggregate_type='consultation' "
            "AND aggregate_id=? AND event_type='INTENT' "
            "ORDER BY event_id LIMIT 1",
            (consultation_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("intent event missing")
    payload = json.loads(row["payload_json"])
    with runtime.store.read() as connection:
        attempt_row = connection.execute(
            "SELECT j.root_job_id FROM attempts a JOIN jobs j ON j.job_id=a.job_id "
            "WHERE a.attempt_id=?",
            (payload["recipient_actor_ref"]["attempt_id"],),
        ).fetchone()
    root_job_id = attempt_row["root_job_id"]
    identity = ConsultationSourceIdentity.create(
        consultation_id=payload["consultation_id"],
        message_key=payload["message_key"],
        semantic_fingerprint=payload["semantic_fingerprint"],
        root_job_id=root_job_id,
        requester_job_id=payload["requester_actor_ref"]["job_id"],
        requester_attempt_id=payload["requester_actor_ref"]["attempt_id"],
        recipient_job_id=payload["recipient_actor_ref"]["job_id"],
        recipient_attempt_id=payload["recipient_actor_ref"]["attempt_id"],
        binding_id=str(payload["recipient_binding"]["binding_id"]),
        binding_generation=int(payload["recipient_binding"]["binding_generation"]),
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
            binding_id=str(payload["recipient_binding"]["binding_id"]),
            binding_generation=int(payload["recipient_binding"]["binding_generation"]),
            native_handle="thread-recipient-1",
            reasoning_surface="codex",
        ),
    )
    obligation = extension.obligation()
    target = SessionTarget(
        session_alias="CONSULTATION-RECIPIENT",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=True,
    )
    route = route_obligation(
        obligation,
        SessionTargetRegistry(
            schema="mastermind.wake_session_targets.v2",
            lifecycle_authority="executive_os",
            production_armed=False,
            policy_version="fixture-v1",
            default_alias_by_seat={"coo": target.session_alias},
            workstream_alias_by_seat={},
            root_job_bindings={obligation.root_job_id: {"coo": target.session_alias}},
            targets={target.session_alias: target},
        ),
        binding=extension.current_binding,
    )
    attempt = make_delivery_attempt(obligation, route, attempt_n=1)
    WakeLedgerRepository(runtime).append_records_atomic(
        [
            (requested_record(extension.obligation()), extension.obligation()),
            (attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), None),
        ]
    )
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


# ---------------------------------------------------------------------------
# Journey tests
# ---------------------------------------------------------------------------


def test_a_b_a_journey_with_full_credit_and_consumption(tmp_path: Path) -> None:
    """Case (a) A→B→A journey: INTENT, wake, ANSWER, CONSUMED, no duplicates."""
    runtime = _runtime_at(tmp_path / "journey")
    consultations = _consultations(runtime, tmp_path / "journey")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-journey")
    shared_carrier = InMemoryAnswerFrameCarrier()

    a_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=requester,
        recipient=recipient,
        answer_frames=shared_carrier,
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)
    b_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=recipient,
        recipient=requester,
        answer_frames=shared_carrier,
    )
    b_gateway = _gateway_with_dispatcher(b_dispatcher)

    # A.consult
    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    assert consult_envelope["ok"] is True
    consultation_id = consult_envelope["data"]["consultation_ref"]
    assert consultation_id.startswith("consult-")

    # Credit the wake so the obligation is TARGET_ACKNOWLEDGED.
    _credit_wake_path(runtime, consultation_id)

    # Both inboxes see QUESTION_DELIVERED with owed_turn=RECIPIENT
    a_inbox = project_company_inbox(
        runtime, actor_worker_id=requester[2], now="2026-09-14T00:00:30Z"
    )
    a_row = a_inbox["items"][0]
    assert a_row["state"] == "QUESTION_DELIVERED"
    assert a_row["owed_turn"] == "RECIPIENT"
    assert a_row["role"] == "REQUESTER"
    assert a_row["schema"] == COMPANY_INBOX_SCHEMA

    b_inbox = project_company_inbox(
        runtime, actor_worker_id=recipient[2], now="2026-09-14T00:00:30Z"
    )
    b_row = b_inbox["items"][0]
    assert b_row["role"] == "RECIPIENT"
    assert b_row["state"] == "QUESTION_DELIVERED"
    assert b_row["owed_turn"] == "RECIPIENT"

    # B.reply
    reply_envelope = _run(
        b_gateway.call(
            "company.reply",
            {
                "consultation_ref": consultation_id,
                "answer": "answer text",
                "evidence_refs": [],
            },
        )
    )
    assert reply_envelope["ok"] is True
    assert reply_envelope["data"]["state"] == "ANSWER_AVAILABLE"

    # A.inbox now sees ANSWER_AVAILABLE, owed_turn=REQUESTER.
    a_inbox = project_company_inbox(
        runtime, actor_worker_id=requester[2], now="2026-09-14T00:01:00Z"
    )
    assert a_inbox["items"][0]["state"] == "ANSWER_AVAILABLE"
    assert a_inbox["items"][0]["owed_turn"] == "REQUESTER"

    # A.read — first read CONSUMED + CONSUMED_BY_REQUESTER
    a_read_envelope = _run(
        a_gateway.call(
            "company.consultation", {"consultation_ref": consultation_id}
        )
    )
    assert a_read_envelope["ok"] is True
    assert a_read_envelope["data"]["state"] == "CONSUMED"

    evidence = _evidence_for(runtime, consultation_id)
    assert len(evidence.get("CONSUMED_BY_REQUESTER", [])) == 1
    assert len(evidence.get("INTENT", [])) == 1
    assert len(evidence.get("ANSWER_AVAILABLE", [])) == 1

    # A.read — second read still CONSUMED, no new CONSUMED event
    a_read_envelope_2 = _run(
        a_gateway.call(
            "company.consultation", {"consultation_ref": consultation_id}
        )
    )
    assert a_read_envelope_2["data"]["state"] == "CONSUMED"
    evidence_2 = _evidence_for(runtime, consultation_id)
    assert len(evidence_2.get("CONSUMED_BY_REQUESTER", [])) == 1

    # JOURNEY_EVIDENCE
    intent_event_id_value = evidence["INTENT"][0]
    answer_event_id_value = evidence["ANSWER_AVAILABLE"][0]
    consumed_event_id_value = evidence["CONSUMED_BY_REQUESTER"][0]
    obligation_id = a_inbox["items"][0]["obligation_id"]

    print(
        "JOURNEY_EVIDENCE: "
        f"consultation_id={consultation_id} "
        f"obligation_id={obligation_id} "
        f"INTENT={intent_event_id_value} "
        f"ANSWER_AVAILABLE={answer_event_id_value} "
        f"CONSUMED_BY_REQUESTER={consumed_event_id_value}"
    )


def test_b_reply_before_credited_path_wakes_typed_refusal(tmp_path: Path) -> None:
    """Case (b): reply BEFORE wake credit → typed WAKE_NOT_ACKNOWLEDGED."""
    runtime = _runtime_at(tmp_path / "before-credit")
    consultations = _consultations(runtime, tmp_path / "before-credit")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-before-credit")

    a_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=requester,
        recipient=recipient,
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)
    b_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=recipient,
        recipient=requester,
    )
    b_gateway = _gateway_with_dispatcher(b_dispatcher)

    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    consultation_id = consult_envelope["data"]["consultation_ref"]

    reply_envelope = _run(
        b_gateway.call(
            "company.reply",
            {
                "consultation_ref": consultation_id,
                "answer": "answer text",
                "evidence_refs": [],
            },
        )
    )
    assert reply_envelope["ok"] is True
    assert reply_envelope["data"]["code"] == "WAKE_NOT_ACKNOWLEDGED"

    events = runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    )
    assert "ANSWER_AVAILABLE" not in {event.event_type for event in events}


def test_duplicate_consult_returns_already_intended_with_one_event(
    tmp_path: Path,
) -> None:
    """Case (c): duplicate consult → ALREADY_INTENDED + one INTENT."""
    runtime = _runtime_at(tmp_path / "duplicate")
    consultations = _consultations(runtime, tmp_path / "duplicate")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-duplicate")

    a_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=requester,
        recipient=recipient,
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)

    first = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    assert first["ok"] is True

    second = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    assert second["ok"] is True
    consultation_id = first["data"]["consultation_ref"]
    assert consultation_id == second["data"]["consultation_ref"]
    assert second["data"]["state"] == "ALREADY_INTENDED"

    events = runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    )
    assert sum(1 for event in events if event.event_type == "INTENT") == 1


def test_non_party_worker_c_reads_returns_not_a_party(tmp_path: Path) -> None:
    """Case (d): non-party worker C reads → NOT_A_PARTY, empty inbox."""
    runtime = _runtime_at(tmp_path / "non-party")
    consultations = _consultations(runtime, tmp_path / "non-party")
    requester, recipient, third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-non-party")

    a_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=requester,
        recipient=recipient,
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)

    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    consultation_id = consult_envelope["data"]["consultation_ref"]

    c_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=third,
        recipient=third,
    )
    c_gateway = _gateway_with_dispatcher(c_dispatcher)
    c_read = _run(
        c_gateway.call(
            "company.consultation", {"consultation_ref": consultation_id}
        )
    )
    assert c_read["ok"] is True
    assert c_read["data"]["blocker"] == "NOT_A_PARTY"

    c_inbox = project_company_inbox(
        runtime, actor_worker_id=third[2], now="2026-09-14T00:01:00Z"
    )
    assert c_inbox["items"] == []


def test_session_rotation_observes_existing_runtime_rule(tmp_path: Path) -> None:
    """Case (e): rotated requester attempt — record existing runtime rule.

    Drives ``ConsultationRuntime.consumed_by_requester`` directly with the
    rotated attempt so the dispatcher-level short-circuit (it bails on
    the attempt mismatch before reaching the runtime rule) cannot mask
    the canonical runtime check at
    ``control_plane/consultation_runtime.py:684``.
    """
    runtime = _runtime_at(tmp_path / "rotation")
    consultations = _consultations(runtime, tmp_path / "rotation")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-rotation")

    a_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=requester,
        recipient=recipient,
        answer_frames=InMemoryAnswerFrameCarrier(),
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)
    shared_carrier = a_dispatcher.answer_frames
    b_dispatcher = _make_dispatcher(
        runtime,
        fixture_repo,
        requester=recipient,
        recipient=requester,
        answer_frames=shared_carrier,
    )
    b_gateway = _gateway_with_dispatcher(b_dispatcher)

    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    consultation_id = consult_envelope["data"]["consultation_ref"]
    _credit_wake_path(runtime, consultation_id)

    # B.reply first (legitimate recipient)
    reply_envelope = _run(
        b_gateway.call(
            "company.reply",
            {
                "consultation_ref": consultation_id,
                "answer": "answer text",
                "evidence_refs": [],
            },
        )
    )
    assert reply_envelope["ok"] is True

    # Consume the exact admitted ANSWER frame the recipient dispatcher put on
    # the shared carrier (only after the runtime admitted ANSWER_AVAILABLE),
    # so the rotated caller presents the frame the runtime already holds.
    answer_frame = shared_carrier.get(consultation_id)
    assert answer_frame is not None

    # Build a rotated attempt for the requester: same worker, new attempt, new binding.
    rotated_attempt = (
        "ATT-ROTATED-" + hashlib.sha256(b"rotated-attempt").hexdigest()[:16]
    )

    # Call ``consumed_by_requester`` directly with the rotated attempt; the
    # runtime at ``control_plane/consultation_runtime.py:684`` requires the
    # exact attempt_id recorded on the INTENT and raises StateConflict.
    with pytest.raises(StateConflict) as excinfo:
        consultations.consumed_by_requester(
            answer_frame,
            requester_attempt_id=rotated_attempt,
            observed_at="2026-09-14T00:01:00Z",
        )
    assert "requester actor is not the Runtime Attempt" in str(excinfo.value)

    # Dispatcher-level typed refusal still applies — keeps the rotation
    # path fully exercised without depending on the substring.
    rotated_caller = CallerIdentity(
        worker_id=requester[2],
        attempt_id=rotated_attempt,
        reasoning_surface="codex",
        binding=_binding(f"rotated-{rotated_attempt}", 1),
    )
    rotated_dispatcher = RuntimeConsultationDispatcher(
        runtime=runtime,
        repository_root=tmp_path / "rotation",
        caller=rotated_caller,
        recipients=_recipient_resolver(recipient),
        answer_frames=shared_carrier,
        _clock=_ManualClock("2026-09-14T00:01:00Z"),
    )
    rotated_gateway = _gateway_with_dispatcher(rotated_dispatcher)
    rotated_read = _run(
        rotated_gateway.call(
            "company.consultation", {"consultation_ref": consultation_id}
        )
    )
    # The rotated dispatcher bails on the attempt mismatch with zero effect.
    assert rotated_read["ok"] is True
    row = rotated_read["data"]
    assert row.get("state") in {"ANSWER_AVAILABLE", "CONSUMED"}
    assert row.get("blocker") == "ANSWER_FRAME_UNAVAILABLE"
    events = runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    )
    assert sum(
        1 for event in events if event.event_type == "CONSUMED_BY_REQUESTER"
    ) == 0

    print(
        "RUNTIME_RULES_OBSERVED: rotated_attempt consumption refused at "
        "control_plane/consultation_runtime.py:684 "
        "(requester actor attempt_id mismatch); "
        f"raised={type(excinfo.value).__name__}"
    )


def test_corrupt_wake_ledger_path_surfaces_reconciliation_required(
    tmp_path: Path,
) -> None:
    """Case (f): corrupt the wake ledger lineage → RECONCILIATION_REQUIRED.

    Appends a canonical WAKE_REQUESTED plus a binding-mismatched
    DELIVERY_ATTEMPT via WakeLedgerRepository so the canonical wake
    evidence no longer validates against the current RuntimeBinding. The
    runtime then refuses to evaluate the obligation and the projection
    must surface RECONCILIATION_REQUIRED + WAKE_STATE_UNAVAILABLE
    (no disjunctive asserts).
    """
    runtime = _runtime_at(tmp_path / "corrupt")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-corrupt")

    a_dispatcher = _make_dispatcher(
        runtime, fixture_repo, requester=requester, recipient=recipient
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)

    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": "Frozen question?",
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    consultation_id = consult_envelope["data"]["consultation_ref"]

    from control_plane.dialogue_source_resolution import (
        ConsultationSourceIdentity,
    )
    from control_plane.session_targets import (
        RuntimeBinding,
        SessionTarget,
        SessionTargetRegistry,
        route_obligation,
    )
    from control_plane.wake_ledger import (
        LedgerPhase,
        attempt_record,
        make_delivery_attempt,
        requested_record,
    )
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        ConsultationWakeExtension,
    )

    intent_payload = next(
        event.payload
        for event in runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=consultation_id
        )
        if event.event_type == "INTENT"
    )
    with runtime.store.read() as connection:
        root_row = connection.execute(
            "SELECT j.root_job_id FROM attempts a JOIN jobs j ON j.job_id=a.job_id "
            "WHERE a.attempt_id=?",
            (intent_payload["recipient_actor_ref"]["attempt_id"],),
        ).fetchone()
    identity = ConsultationSourceIdentity.create(
        consultation_id=intent_payload["consultation_id"],
        message_key=intent_payload["message_key"],
        semantic_fingerprint=intent_payload["semantic_fingerprint"],
        root_job_id=root_row["root_job_id"],
        requester_job_id=intent_payload["requester_actor_ref"]["job_id"],
        requester_attempt_id=intent_payload["requester_actor_ref"]["attempt_id"],
        recipient_job_id=intent_payload["recipient_actor_ref"]["job_id"],
        recipient_attempt_id=intent_payload["recipient_actor_ref"]["attempt_id"],
        binding_id=str(intent_payload["recipient_binding"]["binding_id"]),
        binding_generation=int(intent_payload["recipient_binding"]["binding_generation"]),
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
            binding_id=str(intent_payload["recipient_binding"]["binding_id"]),
            binding_generation=int(intent_payload["recipient_binding"]["binding_generation"]),
            native_handle="thread-recipient-1",
            reasoning_surface="codex",
        ),
    )
    obligation = extension.obligation()
    target = SessionTarget(
        session_alias="CONSULTATION-RECIPIENT",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=True,
    )
    mismatched_binding_obj = RuntimeBinding(
        session_alias="CONSULTATION-RECIPIENT",
        binding_id="bind-mismatched-corrupt",
        binding_generation=99,
        native_handle="thread-mismatched",
        reasoning_surface="codex",
    )
    route = route_obligation(
        obligation,
        SessionTargetRegistry(
            schema="mastermind.wake_session_targets.v2",
            lifecycle_authority="executive_os",
            production_armed=False,
            policy_version="fixture-v1",
            default_alias_by_seat={"coo": target.session_alias},
            workstream_alias_by_seat={},
            root_job_bindings={obligation.root_job_id: {"coo": target.session_alias}},
            targets={target.session_alias: target},
        ),
        binding=mismatched_binding_obj,
    )
    WakeLedgerRepository(runtime).append_records_atomic(
        [
            (requested_record(obligation), None),
            (
                attempt_record(
                    make_delivery_attempt(obligation, route, attempt_n=1),
                    LedgerPhase.DELIVERY_ATTEMPT,
                ),
                None,
            ),
        ]
    )

    row = company_inbox_row(
        runtime, consultation_id, requester[2], "2026-09-14T00:01:00Z"
    )
    assert row["state"] == "RECONCILIATION_REQUIRED"
    assert row["blocker"] == "WAKE_STATE_UNAVAILABLE"


def test_inbox_rows_carry_only_digests_never_text(tmp_path: Path) -> None:
    """Case (g): inbox rows contain no question/answer TEXT — digests only."""
    runtime = _runtime_at(tmp_path / "privacy")
    requester, recipient, _third, _root = _workers(runtime)
    fixture_repo, fixture_revision = _fixture_repo(tmp_path / "fixture-repo-privacy")
    body_text = "SECRET-QUESTION-TEXT-MUST-NOT-LEAK"

    a_dispatcher = _make_dispatcher(
        runtime, fixture_repo, requester=requester, recipient=recipient
    )
    a_gateway = _gateway_with_dispatcher(a_dispatcher)

    consult_envelope = _run(
        a_gateway.call(
            "company.consult",
            {
                "to": PEER_REF,
                "question": body_text,
                "evidence_refs": [],
                "artifact_revisions": [fixture_revision],
            },
        )
    )
    consultation_id = consult_envelope["data"]["consultation_ref"]

    inbox = project_company_inbox(
        runtime, actor_worker_id=requester[2], now="2026-09-14T00:01:00Z"
    )
    raw = json.dumps(inbox, sort_keys=True)
    assert body_text not in raw
    assert recipient[2] not in raw  # no clear worker_id in inbox
    assert recipient[1] not in raw  # no clear attempt_id

    row = company_inbox_row(
        runtime, consultation_id, recipient[2], "2026-09-14T00:01:00Z"
    )
    raw_row = json.dumps(row, sort_keys=True)
    assert body_text not in raw_row
    assert requester[2] not in raw_row
    assert recipient[2] not in raw_row


def test_frozen_company_consultation_mcp_tests_stay_green() -> None:
    """Case (h): the frozen-surface tool-schema digest is unchanged."""
    from tests.test_company_consultation_mcp import (
        COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST as EXECUTIVE_COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
    )

    assert (
        COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST
        == EXECUTIVE_COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST
    )
