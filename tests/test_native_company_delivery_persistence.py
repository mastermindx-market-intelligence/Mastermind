"""Real Runtime ledger restart and privacy checks; no live provider is contacted."""
from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.operator_harness_contract import AttentionCompanyReadProjection
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import route_obligation
from control_plane.wake_dispatcher import (
    PersistedNudgeState, TransportOutcome, TransportReceipt, WakeTransportCompletion,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    LedgerPhase, WakeLedgerError, attempt_record, wake_record_from_event,
)
from control_plane.wake_persist import WakeLedgerRepository
from tests.test_executive_wake_persisted_dispatch import (
    _POLICY, _codex_registry, _dispatch_persisted, _seed_requested,
)
from tests.test_wake_ack_ingress import _admitted_runtime


class _CompanyDispatcher:
    transport_id = "codex-app-server"

    def __init__(self, sealed, generation, *, overrides=None, late=False):
        self.sealed, self.generation = sealed, generation
        self.overrides = overrides or {}
        self.late = late
        self.calls = self.reconcile_calls = 0

    def completion(self, wake):
        company = AttentionCompanyReadProjection(**({
            "target_attempt_id": self.sealed.attempt_id,
            "process_generation_id": self.generation.process_generation_id,
            "binding_id": wake.binding_id,
            "binding_generation": wake.binding_generation,
            "provider_session_id": wake.native_handle,
            "provider_native_turn_id": "native-company-turn-private",
            "nudge_id": wake.nudge_id,
            "consultation_ref": "consult-" + "a" * 32,
            "result_sha256": "1" * 64,
            "native_item_sha256": "2" * 64,
            "answer_attestation_sha256": "3" * 64,
        } | self.overrides))
        return WakeTransportCompletion(
            receipt=TransportReceipt(
                outcome=TransportOutcome.DELIVERED, reason_code="delivered",
                created_at="2026-10-04T00:00:00Z",
                details=(("nudge_id", wake.nudge_id),),
            ),
            company_read_projection=company,
        )

    async def nudge(self, wake):
        self.calls += 1
        if self.late:
            return TransportReceipt(
                outcome=TransportOutcome.ACCEPTED, reason_code="accepted",
                created_at="2026-10-04T00:00:00Z",
                details=(("nudge_id", wake.nudge_id),),
            )
        return self.completion(wake)

    async def reconcile(self, wake):
        self.reconcile_calls += 1
        return self.completion(wake)


def _fixture(tmp_path, *, overrides=None, late=False, count=1):
    runtime, sealed, generation = _admitted_runtime(tmp_path)
    repo = WakeLedgerRepository(runtime)
    registry = _codex_registry("PROPHET-COO-A")
    binding = project_runtime_binding(
        runtime, sealed.attempt_id, registry.targets["PROPHET-COO-A"],
    )
    attempt = runtime.attempts.get_attempt(sealed.attempt_id)
    pairs = []
    for ordinal in range(count):
        obligation = mint_obligation(
            wake_kind="job_failed", source_kind="executive_inbox_attention",
            source_ref=f"eia-{ordinal:012x}", declared_target_seat="coo",
            root_job_id="JOB-001", job_id=attempt.job_id, attempt_id=sealed.attempt_id,
        )
        pairs.append((obligation, route_obligation(obligation, registry, binding=binding)))
    _seed_requested(repo, *pairs)
    dispatcher = _CompanyDispatcher(sealed, generation, overrides=overrides, late=late)
    return repo, pairs, binding, dispatcher


def _dispatch(repo, pairs, binding, dispatcher):
    return _dispatch_persisted(
        repo, pairs, binding=binding, dispatcher=dispatcher, retry_policy=_POLICY,
    )


@pytest.mark.parametrize("late", [False, True])
def test_company_evidence_survives_restart_without_provider_resubmission(tmp_path, late):
    repo, pairs, binding, dispatcher = _fixture(tmp_path, late=late)
    result = _dispatch(repo, pairs, binding, dispatcher)
    if late:
        assert result.state is PersistedNudgeState.ACCEPTED
        assert result.native_company_read is None
        repo = WakeLedgerRepository(Runtime.at(tmp_path))
        result = _dispatch(repo, pairs, binding, dispatcher)
    evidence = result.native_company_read
    assert result.state is PersistedNudgeState.DELIVERED
    assert evidence is not None
    assert evidence.provider_session_sha256 == hashlib.sha256(
        binding.native_handle.encode()).hexdigest()
    assert evidence.provider_native_turn_sha256 == hashlib.sha256(
        b"native-company-turn-private").hexdigest()
    assert (evidence.result_sha256, evidence.native_item_sha256,
            evidence.answer_attestation_sha256) == ("1" * 64, "2" * 64, "3" * 64)
    rows = repo.list_records(pairs[0][0].obligation_id)
    delivered = [row for row in rows if row.record.phase is LedgerPhase.DELIVERED]
    assert len(delivered) == 1
    assert delivered[0].event.attempt_id == evidence.target_attempt_id
    assert delivered[0].event.payload["native_company_read"] == evidence.to_dict()
    assert LedgerPhase.TARGET_ACKNOWLEDGED not in [row.record.phase for row in rows]
    serialized = json.dumps([row.event.payload for row in rows])
    assert binding.native_handle not in serialized
    assert "native-company-turn-private" not in serialized
    repo = WakeLedgerRepository(Runtime.at(tmp_path))
    replay = _dispatch(repo, pairs, binding, dispatcher)
    assert replay.native_company_read == evidence
    assert len(repo.list_records(pairs[0][0].obligation_id)) == len(rows)
    assert dispatcher.calls == 1
    assert dispatcher.reconcile_calls == int(late)


@pytest.mark.parametrize("overrides", [
    {"target_attempt_id": "ATT-" + "f" * 32},
    {"binding_id": "bind-foreign"},
    {"binding_generation": 900},
    {"provider_session_id": "foreign-provider"},
    {"nudge_id": "NUDGE-" + "f" * 32},
])
def test_foreign_optional_evidence_preserves_delivery(tmp_path, overrides):
    repo, pairs, binding, dispatcher = _fixture(tmp_path, overrides=overrides)
    result = _dispatch(repo, pairs, binding, dispatcher)
    assert result.state is PersistedNudgeState.DELIVERED
    assert result.native_company_read is None
    assert dispatcher.calls == 1


def test_coalesced_delivery_does_not_guess_company_owner(tmp_path):
    repo, pairs, binding, dispatcher = _fixture(tmp_path, count=2)
    result = _dispatch(repo, pairs, binding, dispatcher)
    assert result.state is PersistedNudgeState.DELIVERED
    assert result.native_company_read is None
    assert all(repo.list_records(pair[0].obligation_id)[-1].record.native_company_read is None
               for pair in pairs)


def test_exact_native_proof_replay_is_idempotent_and_hash_drift_conflicts(tmp_path):
    repo, pairs, binding, dispatcher = _fixture(tmp_path)
    result = _dispatch(repo, pairs, binding, dispatcher)
    attempt = result.nudge_attempt.attempts[0]
    evidence = result.native_company_read
    record = attempt_record(attempt, LedgerPhase.DELIVERED, native_company_read=evidence)
    assert repo.append_record(record, obligation=pairs[0][0]).inserted is False
    changed = dataclasses.replace(
        record, native_company_read=dataclasses.replace(evidence, result_sha256="9" * 64),
    )
    with pytest.raises(StateConflict, match="payload disagrees"):
        repo.append_record(changed, obligation=pairs[0][0])


@pytest.mark.parametrize("phase", [p for p in LedgerPhase if p is not LedgerPhase.DELIVERED])
def test_native_evidence_is_delivered_only(tmp_path, phase):
    repo, pairs, binding, dispatcher = _fixture(tmp_path)
    result = _dispatch(repo, pairs, binding, dispatcher)
    with pytest.raises(WakeLedgerError):
        attempt_record(
            result.nudge_attempt.attempts[0], phase,
            native_company_read=result.native_company_read,
        )


@pytest.mark.parametrize("mutation", ["outer_attempt", "raw_alias", "unknown", "null_proof"])
def test_durable_decoder_refuses_foreign_correlation_or_open_shapes(tmp_path, mutation):
    repo, pairs, binding, dispatcher = _fixture(tmp_path)
    _dispatch(repo, pairs, binding, dispatcher)
    event = repo.list_records(pairs[0][0].obligation_id)[-1].event
    if mutation == "outer_attempt":
        event = dataclasses.replace(event, attempt_id="ATT-" + "f" * 32)
    else:
        payload = dict(event.payload)
        if mutation == "raw_alias":
            payload["provider_session_id"] = "private-provider"
        elif mutation == "unknown":
            payload["ignored_provider_address"] = "private-provider"
        else:
            payload["native_company_read"] = None
        event = dataclasses.replace(event, payload=payload)
    with pytest.raises(WakeLedgerError):
        wake_record_from_event(event)
