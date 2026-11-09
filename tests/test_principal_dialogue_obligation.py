"""Exact, read-only Wake anchors; no live principal, provider or Relay effect."""
from __future__ import annotations

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.executive_runtime import Runtime
from control_plane.principal_dialogue_obligation import (
    PrincipalDialogueObligationUnavailable, read_principal_dialogue_obligation,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    AckMode, SourceReadHealth, TrustedAckContext, acknowledge, ack_record,
    expected_resolution_code, requested_record, resolve_source, resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository


def carrier(runtime, *, key="asd-decision-001", seat="coo", work="WS:R2-TEST"):
    root = runtime.jobs.create_job("synthetic root")
    child = runtime.jobs.create_job("synthetic child", parent_job_id=root.job_id)
    worker = "worker-" + child.job_id.lower()
    runtime.workers.register_worker(worker, provider="codex", account_label=worker,
                                    worker_type="fixture", capabilities=["research"])
    lease = runtime.attempts.claim_job(child.job_id, worker_id=worker)
    assert lease is not None
    candidate = {"mode": "ACTIVE_CURRENT_WORKER", "root_job_id": root.job_id,
                 "job_id": child.job_id, "attempt_id": lease.attempt.attempt_id,
                 "worker_id": worker, "evidence_digest": "b" * 64}
    operation = "exec-" + child.job_id.lower()
    observed = DialogueSourceObservation("T0BRD2AQXQV", "C0BSBM78V1N",
                                        "1788000000.123456", key, "c" * 64)
    attention = attention_source_ref(parent_fingerprint="a" * 64,
                                     message_key=key, target_seat=seat)
    logical = correlated_source_ref(attention_source_ref=attention,
                                    parent_fingerprint="a" * 64,
                                    operation_key=operation, candidate=candidate)
    obligation = mint_obligation(wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention", source_ref=logical,
        declared_target_seat=seat, job_id=child.job_id,
        attempt_id=lease.attempt.attempt_id, root_job_id=root.job_id,
        source_workstream=work, emitted_at="2026-10-14T00:00:00Z")
    physical = PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=obligation.obligation_id, observation=observed,
        parent_fingerprint="a" * 64, operation_key=operation,
        target_seat=seat, candidate=candidate)
    WakeLedgerRepository(runtime).append_record(
        requested_record(obligation, physical_source=physical), obligation=obligation)
    return obligation, physical


def read(runtime, obligation, **overrides):
    args = {"obligation_id": obligation.obligation_id,
            "expected_work_ref": obligation.source_workstream,
            "expected_root_job_id": obligation.root_job_id}
    args.update(overrides)
    return read_principal_dialogue_obligation(runtime, **args)


def test_exact_obligation_selects_its_original_anchor_and_never_writes(tmp_path):
    runtime = Runtime.at(tmp_path)
    first, original = carrier(runtime)
    carrier(runtime, key="asd-decision-002")
    before = runtime.events.list_events()
    result = read(runtime, first)
    assert result.obligation == first
    assert result.physical_source == original
    assert result.physical_source.predecessor_message_key == "asd-decision-001"
    assert result.observed_event_ids
    assert runtime.events.list_events() == before


@pytest.mark.parametrize("change", [
    {"expected_work_ref": "WS:OTHER"}, {"expected_root_job_id": "JOB-999"},
    {"obligation_id": "wake-" + "0" * 32}, {"obligation_id": "../private"},
    {"expected_work_ref": None}, {"expected_root_job_id": None},
])
def test_foreign_missing_or_malformed_selector_has_one_closed_response(tmp_path, change):
    runtime = Runtime.at(tmp_path)
    obligation, _ = carrier(runtime)
    with pytest.raises(PrincipalDialogueObligationUnavailable) as error:
        read(runtime, obligation, **change)
    assert str(error.value) == "PRINCIPAL_DIALOGUE_OBLIGATION_UNAVAILABLE"


def test_other_seat_is_not_a_coo_carrier(tmp_path):
    runtime = Runtime.at(tmp_path)
    obligation, _ = carrier(runtime, seat="ceo")
    with pytest.raises(PrincipalDialogueObligationUnavailable):
        read(runtime, obligation)


def test_attention_ack_is_not_source_resolution_but_resolved_source_is_closed(tmp_path):
    runtime = Runtime.at(tmp_path)
    obligation, physical = carrier(runtime)
    repository = WakeLedgerRepository(runtime)
    ack = acknowledge(obligation, trusted=TrustedAckContext(
        ack_mode=AckMode.HUMAN_OPERATOR, target_seat="coo",
        session_alias="SYNTHETIC-OPERATOR", reasoning_surface="human",
        acknowledged_at="2026-10-14T00:00:01Z",
        operator_authority_receipt="OP-WAKE-RECONCILE-TEST"),
        claimed_obligation_ids=(obligation.obligation_id,))
    repository.append_record(ack_record(obligation, ack))
    assert read(runtime, obligation).physical_source == physical
    resolution = resolve_source(obligation, code=expected_resolution_code(obligation),
        health=SourceReadHealth.HEALTHY, source_present=False,
        snapshot_digest="d" * 64, resolved_at="2026-10-14T00:00:02Z")
    repository.append_record(resolved_record(obligation, resolution))
    with pytest.raises(PrincipalDialogueObligationUnavailable):
        read(runtime, obligation)


def test_missing_well_formed_obligation_has_no_fallback(tmp_path):
    runtime = Runtime.at(tmp_path)
    obligation, _ = carrier(runtime)
    missing = obligation.obligation_id[:-8] + "0" * 8
    assert missing != obligation.obligation_id
    with pytest.raises(PrincipalDialogueObligationUnavailable):
        read(runtime, obligation, obligation_id=missing)


def test_owner_failure_does_not_leak_details(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path)
    obligation, _ = carrier(runtime)
    def denied(*args, **kwargs):
        raise PermissionError("PRIVATE_CANARY /private/credentials")
    monkeypatch.setattr(WakeLedgerRepository, "list_records", denied)
    with pytest.raises(PrincipalDialogueObligationUnavailable) as error:
        read(runtime, obligation)
    assert "PRIVATE_CANARY" not in str(error.value)
    assert error.value.__cause__ is None
