"""OHF/App Server conformance for a bounded Codex-Sol technical continuation.

The provider/harness may return technical prose, including a proposal outside the
Executive grant.  That output remains candidate evidence only: it cannot complete
the Executive Job, widen its authority, or become source law by being emitted by
Codex/App Server.
"""
from __future__ import annotations

import dataclasses

from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    AuthRealmFact,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProfileValidation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    WorkspaceIdentity,
)
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator


_CEO_PROVENANCE = {"schema": "mastermind.ceo_intent.v1", "actor": "sol"}
_WIDENING_PROPOSAL = (
    "Create a second durable lifecycle plane, set owner_seat=ceo from model identity, "
    "and grant DEPLOY even though the Executive Job permits READ only."
)


def _requested(*, worker_id: str, authority_policy_hash: str) -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id=worker_id,
        provider="codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="codex/1",
        workspace=WorkspaceIdentity("/work", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="restricted",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash=authority_policy_hash,
    )


def _observed(requested: RequestedExecutionProfile) -> ObservedHarnessAttestation:
    return ObservedHarnessAttestation(
        served_model=requested.requested_model,
        harness_version=requested.harness_version,
        harness_binary_digest=requested.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=requested.sandbox_policy,
        approval_state=requested.approval_policy,
        network_state=requested.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(
            worker_id=requested.worker_id,
            provider=requested.provider,
            attestation_status=ACCOUNT_REALM_STATUS,
        ),
        workspace=requested.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


class _RuntimePort:
    """Production-inert RuntimePort fixture: records candidate evidence, never Job authority."""

    def __init__(self, *, attempt_id: str, worker_id: str) -> None:
        self.attempt_id = attempt_id
        self.worker_id = worker_id
        self.epoch = SessionEpochRef("epoch-codex-sol", attempt_id, worker_id, 1)
        self.generation = ProcessGenerationRef("gen-codex-sol", self.epoch.session_epoch_id, 1, worker_id)
        self.candidates: list[CandidateResult] = []
        self.calls: list[str] = []

    def seal_operator_attempt(self, attempt_id, requested):
        assert attempt_id == self.attempt_id
        self.calls.append("seal")

    def extend_operator_lease(self, attempt_id, minimum_seconds):
        assert attempt_id == self.attempt_id

    def begin_operator_session(self, attempt_id, operation_id):
        assert attempt_id == self.attempt_id
        self.calls.append("start_intent")
        return self.epoch, self.generation

    def commit_operator_provider_dispatch(self, attempt_id, operation_id, operation_kind):
        assert attempt_id == self.attempt_id
        return True

    def bind_operator_session(self, attempt_id, operation_id, observation):
        assert attempt_id == self.attempt_id
        self.calls.append("start_bind")

    def seal_operator_attestation(self, attempt_id, generation, observed, launch, *args):
        assert attempt_id == self.attempt_id
        self.calls.append("attest")

    def begin_operator_turn(self, attempt_id, generation, operation_id):
        assert attempt_id == self.attempt_id
        self.calls.append("turn_intent")
        return TurnRef("turn-codex-sol", self.epoch.session_epoch_id, generation.process_generation_id, attempt_id)

    def apply_operator_turn(self, attempt_id, operation_id, observation):
        assert attempt_id == self.attempt_id
        self.calls.append("turn_bind")

    def record_operator_effect_unknown(self, attempt_id, operation_id, phase, detail):
        raise AssertionError(f"unexpected effect-unknown at {phase}: {detail}")

    def finish_operator_candidate(self, attempt_id, turn, candidate, events, cursor):
        assert attempt_id == self.attempt_id
        self.calls.append("candidate")
        self.candidates.append(candidate)


class _CodexAdapter:
    interface_version = "mastermind.operator_harness/v1"

    def __init__(self, requested: RequestedExecutionProfile) -> None:
        self.requested = requested
        self.attestation = _observed(requested)

    def validate_requested_profile(self, requested):
        return ProfileValidation(requested, True)

    def start_session(self, **kwargs):
        return SessionStartObservation(
            "codex-session-technical",
            ProcessIdentityObservation(10, 10, "start", "boot"),
        )

    def begin_turn(self, **kwargs):
        return TurnStartObservation("codex-native-turn", True)

    def read_events(self, cursor, *, timeout_seconds=30.0):
        event = NormalizedEvent(
            cursor.attempt_id,
            cursor.session_epoch_id,
            cursor.process_generation_id,
            cursor.turn_id,
            "turn/completed",
        )
        return (event,), dataclasses.replace(cursor, local_sequence=cursor.local_sequence + 1)

    def collect_candidate_result(self, turn):
        return CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "d" * 64,
            _WIDENING_PROPOSAL,
        )


def test_codex_ohf_widening_proposal_remains_candidate_and_ceo_job_grant_is_unchanged(tmp_path):
    executive = Runtime.at(tmp_path)
    executive.workers.register_worker(
        "codex-sol-01",
        provider="codex",
        account_label="codex-sol-capacity",
        worker_type="fixture",
        capabilities=["code"],
        quota_classes={"codex-native": ["code"]},
    )
    job = executive.jobs.create_job(
        "Bounded CEO technical continuation through Codex App Server",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=_CEO_PROVENANCE,
        requested_authorities=["READ"],
        constraints={
            "required_capabilities": ["code"],
            "eligible_quota_classes": ["codex-native"],
        },
    )
    authority_before = (
        job.job_id,
        job.owner_seat,
        job.escalation_target,
        tuple(job.requested_authorities),
        job.authority_policy_hash,
    )
    executive.jobs.assign_job(job.job_id, "codex-sol-01", quota_class="codex-native")
    running = executive.jobs.get_job(job.job_id)
    assert running is not None and running.current_attempt_id is not None

    requested = _requested(
        worker_id="codex-sol-01",
        authority_policy_hash=running.authority_policy_hash,
    )
    port = _RuntimePort(attempt_id=running.current_attempt_id, worker_id="codex-sol-01")
    adapter = _CodexAdapter(requested)
    orchestrator = OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.attestation,
    )

    session = orchestrator.start_attempt(
        attempt_id=running.current_attempt_id,
        requested=requested,
        operation_id=OperationId("ohf-op:codex-sol-start"),
    )
    receipt = orchestrator.run_turn(
        session,
        operation_id=OperationId("ohf-op:codex-sol-turn"),
    )

    assert receipt.candidate.complete_job_permitted is False
    assert _WIDENING_PROPOSAL in receipt.candidate.summary
    assert port.candidates == [receipt.candidate]
    assert port.calls[-3:] == ["turn_intent", "turn_bind", "candidate"]
    assert not hasattr(port, "complete_job")

    candidate_fields = {field.name for field in dataclasses.fields(CandidateResult)}
    assert candidate_fields.isdisjoint(
        {
            "owner_seat",
            "escalation_target",
            "requested_authorities",
            "effective_grant",
            "deploy_authority",
            "source_law",
        }
    )

    after = Runtime.at(tmp_path).jobs.get_job(job.job_id)
    assert after is not None
    assert (
        after.job_id,
        after.owner_seat,
        after.escalation_target,
        tuple(after.requested_authorities),
        after.authority_policy_hash,
    ) == authority_before
    assert after.current_attempt_id == running.current_attempt_id
    assert "DEPLOY" not in after.requested_authorities
