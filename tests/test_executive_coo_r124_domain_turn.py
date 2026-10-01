"""Source-only typed proof of the dedicated R124 ``run_domain_consumption_turn``.

The orchestrator method must reuse the genuine R119/R121/R123 current-domain
fixture helpers and the real Runtime + ``ExecutiveOperatorHarnessPort`` so the
new method is exercised through the exact current FINAL-only
``reserve_domain_consumption_turn`` reservation.  Source-only typed fixtures
are not native actor acceptance.  All snapshots are taken on the real
Executive Event/SQLite store before any side effect.
"""
from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import replace
from typing import Any

import pytest

from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_runtime import (
    AttemptLease,
    AttemptStatus,
    StateConflict,
)
from control_plane.operator_harness_contract import CandidateResult, EventCursor, LaunchDecision, NormalizedEvent, OperationReceiptKind, TurnStartObservation, operation_receipt_command_id
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown,
    OperatorHarnessOrchestrationError,
    OperatorHarnessOrchestrator,
    OperatorLaunchRefused,
    OperatorOperationApplied,
    OperatorSessionReceipt,
)
from tests.test_executive_coo_r119_later_turn import (
    _begin_turn_intents,
    _charge_events,
    _charge_rows,
    _domain_attempt,
    _happy_args,
    _inventory,
    _seeded_domain,
)


CONSUMPTION_NATIVE_TURN_PREFIX = "native-consumption"


class TypedHermeticConsumptionAdapter:
    """Hermetic later-turn transport; it cannot start a new session or process."""

    interface_version = "mastermind.operator_harness/v1"

    def __init__(self, profile=None):
        self.begin_turn_calls = []
        self.read_events_calls = []
        self.collect_candidate_calls = []
        self.forbidden_calls = []

    def begin_turn(self, *, operation_id, turn, generation, launch):
        self.begin_turn_calls.append(
            {
                "operation_id": operation_id,
                "turn": turn,
                "generation": generation,
                "launch": launch,
            }
        )
        return TurnStartObservation(
            provider_native_turn_id=f"{CONSUMPTION_NATIVE_TURN_PREFIX}-{turn.turn_id}",
            acknowledged=True,
        )

    def read_events(self, cursor, *, timeout_seconds=30.0):
        self.read_events_calls.append(cursor)
        assert timeout_seconds > 0
        assert cursor.turn_id
        event = NormalizedEvent(
            attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id,
            turn_id=cursor.turn_id,
            kind="turn.completed",
            payload_redacted={"status": "complete"},
        )
        next_cursor = EventCursor(
            attempt_id=cursor.attempt_id,
            session_epoch_id=cursor.session_epoch_id,
            process_generation_id=cursor.process_generation_id,
            local_sequence=cursor.local_sequence + 1,
            turn_id=cursor.turn_id,
        )
        return (event,), next_cursor

    def collect_candidate_result(self, turn):
        self.collect_candidate_calls.append(turn)
        return CandidateResult(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            artifact_digest="a" * 64,
            summary="consumption candidate only",
        )


def _wrap_start_attempt_to_capture_receipt(monkeypatch):
    """Wrap ``OperatorHarnessOrchestrator.start_attempt`` to capture receipts.

    Returns ``(receipts, adapters)`` keyed by ``attempt_id``.  Calls the
    genuine original method so the captured receipt reflects the real
    Executive-allocated epoch/generation/observed ALLOW launch through the
    real Supervisor and the source-only typed hermetic adapter the original
    orchestrator built.  Caller MUST NOT mutate the receipt or attempt to
    swap the captured adapter for a foreign one.
    """

    original = OperatorHarnessOrchestrator.start_attempt
    receipts: dict[str, OperatorSessionReceipt] = {}
    adapters: dict[str, Any] = {}

    def capturing(self, *, attempt_id, requested, operation_id):
        receipt = original(self, attempt_id=attempt_id, requested=requested, operation_id=operation_id)
        receipts[attempt_id] = receipt
        adapters[attempt_id] = self.adapter
        return receipt

    monkeypatch.setattr(OperatorHarnessOrchestrator, "start_attempt", capturing)
    return receipts, adapters


def _build_orchestrator_with_consumption_adapter(
    runtime, lease, adapter
) -> OperatorHarnessOrchestrator:
    """Build a fresh orchestrator for the consumption path.

    Uses the genuine ``ExecutiveOperatorHarnessPort`` so all Runtime calls
    are the real ones; the adapter is the source-only typed hermetic
    consumption adapter created by this test.
    """

    port = ExecutiveOperatorHarnessPort(runtime, lease)
    return OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.observed_attestation(generation),
    )


def _settle_reviewed_domain_with_real_supervisor(
    tmp_path, monkeypatch, receipts, adapters
) -> tuple:
    """Run the real Supervisor through the genuine seeded domain fixture.

    The wrapped ``start_attempt`` captures the genuine receipt (and the
    Supervisor's adapter) for the domain Attempt.  Returns
    ``(runtime, root, domain, domain_attempt_id, session_receipt, supervisor_adapter)``.
    """

    runtime, root, domain, domain_attempt_id = _seeded_domain(
        tmp_path, monkeypatch, genuine_enabled=True,
    )
    assert domain_attempt_id in receipts, (
        "real Supervisor did not yield a captured receipt for the domain Attempt"
    )
    return runtime, root, domain, domain_attempt_id, receipts[domain_attempt_id], adapters[domain_attempt_id]


def _fresh_orchestrator_for_domain_attempt(
    runtime, domain_attempt_id, adapter
) -> tuple[OperatorHarnessOrchestrator, AttemptLease]:
    attempt = runtime.attempts.get_attempt(domain_attempt_id)
    assert attempt is not None
    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT fence_generation, lease_token FROM attempts WHERE attempt_id=?",
            (domain_attempt_id,),
        ).fetchone()
    lease = AttemptLease(attempt, str(row["lease_token"]))
    orchestrator = _build_orchestrator_with_consumption_adapter(runtime, lease, adapter)
    return orchestrator, lease


def test_run_domain_consumption_turn_records_final_row_event_intent_and_candidate(
    tmp_path, monkeypatch,
):
    """Happy path: identical FINAL row/Event/INTENT/dispatch/APPLIED/candidate."""
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    assert session.launch.decision is LaunchDecision.ALLOW
    identity_before = tuple(_domain_attempt(runtime, domain_attempt_id))
    before_charge_events = len(_charge_events(runtime, domain.job_id))
    before_charge_rows = len(_charge_rows(runtime, root.job_id))
    before_intents = len(_begin_turn_intents(runtime, domain_attempt_id))
    before_inventory = _inventory(runtime)
    with runtime.store.read() as connection:
        sealed_before = connection.execute(
            "SELECT event_id FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'"
        ).fetchall()

    receipt = orchestrator.run_domain_consumption_turn(
        session,
        operation_id=operation_id,
        expected_consumption_projection_digest=digest,
        timeout_seconds=12.0,
    )

    # Adapter reached the typed consumption surface exactly once.
    assert len(adapter.begin_turn_calls) == 1
    assert adapter.begin_turn_calls[0]["turn"].turn_id == receipt.turn.turn_id
    assert adapter.begin_turn_calls[0]["generation"] == session.generation
    assert len(adapter.read_events_calls) == 1
    assert adapter.read_events_calls[0].turn_id == receipt.turn.turn_id
    assert len(adapter.collect_candidate_calls) == 1
    assert adapter.collect_candidate_calls[0].turn_id == receipt.turn.turn_id
    assert adapter.forbidden_calls == []

    # Receipt identity and candidate integrity.
    assert receipt.attempt_id == domain_attempt_id
    assert receipt.turn.session_epoch_id == generation.session_epoch_id
    assert receipt.turn.process_generation_id == generation.process_generation_id
    assert receipt.start.acknowledged is True
    assert receipt.start.provider_native_turn_id.startswith(CONSUMPTION_NATIVE_TURN_PREFIX)
    assert receipt.candidate.complete_job_permitted is False
    assert receipt.candidate.artifact_digest == "a" * 64
    assert len(receipt.events) == 1
    assert receipt.events[0].turn_id == receipt.turn.turn_id
    assert receipt.cursor.turn_id == receipt.turn.turn_id
    assert receipt.cursor.local_sequence == 1

    # Identity is conserved on the same domain Job/Attempt/epoch/generation/session.
    assert tuple(_domain_attempt(runtime, domain_attempt_id)) == identity_before

    # Inventory effects: exactly one new FINAL row, charge Event, and INTENT.
    charge_events = _charge_events(runtime, domain.job_id)
    charge_rows = _charge_rows(runtime, root.job_id)
    intents = _begin_turn_intents(runtime, domain_attempt_id)
    assert len(charge_events) == before_charge_events + 1
    assert len(charge_rows) == before_charge_rows + 1
    assert len(intents) == before_intents + 1

    final_row = charge_rows[-1]
    charge_payload = json.loads(charge_events[-1]["payload_json"])
    intent_payload = json.loads(intents[-1]["payload_json"])
    assert final_row["effect_class"] == "FINAL"
    assert final_row["turn_id"] == receipt.turn.turn_id
    assert final_row["operation_id"] == operation_id.command_id
    assert final_row["job_id"] == domain.job_id
    assert final_row["attempt_id"] == domain_attempt_id
    assert charge_payload["consumption_projection_digest"] == digest
    assert charge_payload["effect_class"] == "FINAL"
    assert charge_payload["turn_id"] == receipt.turn.turn_id
    assert intent_payload["operation_kind"] == "begin_turn"
    assert intent_payload["turn_id"] == receipt.turn.turn_id
    assert intent_payload["attempt_id"] == domain_attempt_id
    assert intents[-1]["command_id"] == operation_id.command_id

    # Exactly one APPLIED receipt pairs the consumption INTENT.
    applied = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation_id, OperationReceiptKind.APPLIED),
    )
    assert applied is not None
    applied_payload = applied.payload
    assert applied_payload["turn_id"] == receipt.turn.turn_id
    assert applied_payload["provider_native_turn_id"] == receipt.start.provider_native_turn_id
    assert applied_payload["acknowledged"] is True

    # Exactly one OHF_CANDIDATE_RESULT_RECORDED event for this turn.
    candidate_event = runtime.events.get_event_by_command_id(
        f"ohf-candidate:{receipt.turn.turn_id}"
    )
    assert candidate_event is not None
    candidate_payload = candidate_event.payload
    assert candidate_payload["turn"]["turn_id"] == receipt.turn.turn_id
    assert candidate_payload["candidate"]["complete_job_permitted"] is False
    assert candidate_payload["candidate"]["artifact_digest"] == "a" * 64

    # Plan seal preserved: nonterminal domain Attempt still CHECKPOINTED.
    attempt_after = runtime.attempts.get_attempt(domain_attempt_id)
    assert attempt_after is not None and attempt_after.status is AttemptStatus.CHECKPOINTED
    domain_after = runtime.jobs.get_job(domain.job_id)
    assert domain_after is not None
    assert domain_after.current_attempt_id == domain_attempt_id

    # Original plan seal remains immutable; no second role seal is produced.
    with runtime.store.read() as connection:
        sealed = connection.execute(
            "SELECT event_id FROM events WHERE event_type=?",
            ("ORCHESTRATION_ROLE_RESULT_SEALED",),
        ).fetchall()
    assert sealed == sealed_before

    # Full durable inventory differs only by the FINAL row / event / intent.
    after_inventory = _inventory(runtime)
    added = sorted(set(after_inventory) - set(before_inventory))
    removed = sorted(set(before_inventory) - set(after_inventory))
    assert added == []
    assert removed == []
    for table in after_inventory:
        before_lines = before_inventory.get(table, [])
        after_lines = after_inventory[table]
        new_lines = [line for line in after_lines if line not in before_lines]
        if table == "coo_provider_charges":
            assert len(new_lines) == 1
            assert json.loads(new_lines[0])["effect_class"] == "FINAL"
        elif table == "events":
            final_events = [
                json.loads(line) for line in new_lines
                if json.loads(line)["event_type"] == "COO_DOMAIN_CONSUMPTION_CHARGED"
            ]
            intent_events = [
                json.loads(line) for line in new_lines
                if json.loads(line)["event_type"] == "OPERATOR_OPERATION_INTENT"
                and json.loads(line).get("command_id") == operation_id.command_id
            ]
            applied_events = [
                json.loads(line) for line in new_lines
                if json.loads(line)["event_type"] == "OPERATOR_OPERATION_APPLIED"
            ]
            candidate_events = [
                json.loads(line) for line in new_lines
                if json.loads(line)["event_type"] == "OHF_CANDIDATE_RESULT_RECORDED"
            ]
            assert len(final_events) == 1
            assert len(intent_events) == 1
            assert len(applied_events) == 1
            assert len(candidate_events) == 1


def test_run_domain_consumption_turn_uses_dedicated_bridge_and_not_generic_turn(
    tmp_path, monkeypatch,
):
    """The dedicated method must call ``begin_operator_domain_consumption_turn``."""

    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )

    begin_generic = runtime.operator_harness.reserve_turn
    begin_domain = runtime.operator_harness.reserve_domain_consumption_turn
    generic_calls: list[dict] = []
    domain_calls: list[dict] = []

    def observed_generic(**kwargs):
        generic_calls.append(kwargs)
        return begin_generic(**kwargs)

    def observed_domain(**kwargs):
        domain_calls.append(kwargs)
        return begin_domain(**kwargs)

    monkeypatch.setattr(runtime.operator_harness, "reserve_turn", observed_generic)
    monkeypatch.setattr(runtime.operator_harness, "reserve_domain_consumption_turn", observed_domain)

    receipt = orchestrator.run_domain_consumption_turn(
        session,
        operation_id=operation_id,
        expected_consumption_projection_digest=digest,
    )

    assert generic_calls == []
    assert len(domain_calls) == 1
    kwargs = domain_calls[0]
    assert kwargs["generation"] == session.generation
    assert kwargs["operation_id"] == operation_id
    assert kwargs["fence_generation"] == fence
    assert kwargs["lease_token"] == token
    assert kwargs["expected_consumption_projection_digest"] == digest
    assert receipt.turn.turn_id.startswith("ohf-coo-consumption-turn-")


def test_consumption_turn_uses_same_session_generation_and_writer(
    tmp_path, monkeypatch,
):
    """The adapter sees the exact captured session's epoch/generation/launch."""

    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    assert session.launch.decision is LaunchDecision.ALLOW

    orchestrator.run_domain_consumption_turn(
        session,
        operation_id=operation_id,
        expected_consumption_projection_digest=digest,
    )

    assert len(adapter.begin_turn_calls) == 1
    call = adapter.begin_turn_calls[0]
    assert call["generation"] == session.generation
    assert call["generation"].process_generation_id == generation.process_generation_id
    assert call["generation"].session_epoch_id == generation.session_epoch_id
    assert call["launch"].decision is LaunchDecision.ALLOW


def test_stale_digest_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, _digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    bogus_digest = "0" * 64
    with pytest.raises(StateConflict, match="projection digest"):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=bogus_digest,
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_malformed_digest_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, _digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(OperatorHarnessOrchestrationError, match="64-char hex"):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest="not-a-projection-digest",
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_stale_lease_token_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    # Rebuild the orchestrator with a foreign lease_token; it must refuse
    # before any adapter mutation.
    attempt = runtime.attempts.get_attempt(domain_attempt_id)
    foreign_lease = AttemptLease(attempt, "definitely-not-the-real-lease-token")
    port = ExecutiveOperatorHarnessPort(runtime, foreign_lease)
    foreign_orchestrator = OperatorHarnessOrchestrator(
        port,
        adapter,
        attestation_reader=lambda item, generation: item.observed_attestation(generation),
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="lease token"):
        foreign_orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_foreign_attempt_id_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    # An adversarial caller-known foreign Attempt is refused before reservation.
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    foreign_session = replace(session, attempt_id=domain_attempt_id + "-foreign")
    before = _inventory(runtime)
    with pytest.raises(OperatorHarnessOrchestrationError, match="identity mismatch"):
        orchestrator.run_domain_consumption_turn(
            foreign_session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


@pytest.mark.parametrize("bad_timeout", [-1.0, 0.0, 301.0, math.nan, math.inf])
def test_invalid_timeout_refuses_before_any_mutation(tmp_path, monkeypatch, bad_timeout):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(OperatorHarnessOrchestrationError, match="turn timeout"):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
            timeout_seconds=bad_timeout,
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_non_allow_launch_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    # Fabricate a refused launch by re-using the LaunchComparison shape with
    # REFUSED; the orchestrator refuses before reserving the FINAL turn.
    refused_launch = dataclasses.replace(session.launch, decision=LaunchDecision.REFUSE_SERVED_MODEL_UNKNOWN)
    refused_session = dataclasses.replace(session, launch=refused_launch)
    before = _inventory(runtime)
    with pytest.raises(OperatorLaunchRefused, match="observed launch comparison"):
        orchestrator.run_domain_consumption_turn(
            refused_session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_fresh_orchestrator_replay_is_blocked_by_durable_state(
    tmp_path, monkeypatch,
):
    """A second orchestrator bound to the same lease cannot replay after APPLIED."""

    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, domain_attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter_one = TypedHermeticConsumptionAdapter(profile=None)
    orchestrator_one, lease_one = _fresh_orchestrator_for_domain_attempt(
        runtime, domain_attempt_id, adapter_one,
    )
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    receipt_one = orchestrator_one.run_domain_consumption_turn(
        session,
        operation_id=operation_id,
        expected_consumption_projection_digest=digest,
    )
    assert receipt_one.turn.turn_id.startswith("ohf-coo-consumption-turn-")

    # Fresh orchestrator, same lease; durable APPLIED prevents second
    # provider/credit dispatch on this same operation.
    adapter_two = TypedHermeticConsumptionAdapter(profile=None)
    port_two = ExecutiveOperatorHarnessPort(runtime, lease_one)
    orchestrator_two = OperatorHarnessOrchestrator(
        port_two,
        adapter_two,
        attestation_reader=lambda item, generation: item.observed_attestation(generation),
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        orchestrator_two.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before
    assert adapter_two.begin_turn_calls == []


def test_unacknowledged_native_turn_is_recorded_unknown_without_retries(
    tmp_path, monkeypatch,
):
    """An adapter that does not acknowledge begin_turn must not cause a replay."""

    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, domain_attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter = TypedHermeticConsumptionAdapter(profile=None)

    def unack_begin_turn(*, turn, **kwargs):
        adapter.begin_turn_calls.append(turn)
        return TurnStartObservation(
            provider_native_turn_id=f"{CONSUMPTION_NATIVE_TURN_PREFIX}-{turn.turn_id}",
            acknowledged=False,
        )

    adapter.begin_turn = unack_begin_turn  # type: ignore[assignment]
    orchestrator, _ = _fresh_orchestrator_for_domain_attempt(
        runtime, domain_attempt_id, adapter,
    )
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(OperatorEffectUnknown, match="did not acknowledge"):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    # EFFECT_UNKNOWN recorded on the operation; inventory advanced only
    # along the durable UNKNOWN path.  No second provider/credit dispatch.
    with runtime.store.read() as connection:
        events = list(
            connection.execute(
                "SELECT * FROM events WHERE command_id LIKE ?",
                (operation_id.command_id + "%",),
            )
        )
    effect_unknown = [
        event for event in events if event["event_type"] == "OPERATOR_OPERATION_EFFECT_UNKNOWN"
    ]
    assert len(effect_unknown) >= 1
    unknown_payload = json.loads(effect_unknown[-1]["payload_json"])
    assert unknown_payload["phase"] == "begin_turn_ack"
    # No APPLIED nor OHF_CANDIDATE_RESULT_RECORDED for this operation.
    assert not [
        event for event in events if event["event_type"] == "OPERATOR_OPERATION_APPLIED"
    ]
    # Subsequent attempts to retry with the same adapter must also fail.
    with pytest.raises(OperatorEffectUnknown):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert adapter.forbidden_calls == []
    # Adapter was reached exactly once for the unacknowledged begin_turn.
    assert len(adapter.begin_turn_calls) == 1
    # A committed provider call consumed exactly one FINAL credit; UNKNOWN
    # preserves that effect and never grants a retry or new credit.
    after = _inventory(runtime)
    final_rows = [
        json.loads(line) for line in after["coo_provider_charges"]
        if json.loads(line)["effect_class"] == "FINAL"
    ]
    assert len(final_rows) == len(before["coo_provider_charges"]) + 1


def test_foreign_candidate_preserves_applied_without_retries(
    tmp_path, monkeypatch,
):
    """An acknowledged turn cannot promote an out-of-scope candidate or replay."""

    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, domain_attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter = TypedHermeticConsumptionAdapter(profile=None)

    orchestrator, _ = _fresh_orchestrator_for_domain_attempt(
        runtime, domain_attempt_id, adapter,
    )
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    # The wrong native id is still acknowledged, so the orchestrator applies
    # APPLIED and proceeds to the candidate collection.  To simulate a
    # *foreign* native candidate that refuses recognition, the
    # ``collect_candidate_result`` returns a CandidateResult with a wrong
    # attempt_id (out of turn scope), which makes ``finish_operator_candidate``
    # raise ``StateConflict`` and the effect-unknown handler records UNKNOWN.
    def foreign_candidate(turn):
        adapter.collect_candidate_calls.append(turn)
        return CandidateResult(
            attempt_id=turn.attempt_id + "-foreign",
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            artifact_digest="b" * 64,
            summary="foreign candidate",
        )

    adapter.collect_candidate_result = foreign_candidate  # type: ignore[assignment]
    with pytest.raises(OperatorOperationApplied, match="durably applied") as error:
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert "outside the turn scope" in str(error.value.__cause__)
    applied = runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation_id, OperationReceiptKind.APPLIED))
    assert applied is not None
    assert runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation_id, OperationReceiptKind.EFFECT_UNKNOWN)) is None
    assert runtime.events.get_event_by_command_id(
        f"ohf-candidate:{adapter.collect_candidate_calls[0].turn_id}") is None
    assert adapter.forbidden_calls == []
    # Adapter was reached exactly once for begin_turn and once for the
    # candidate collection; subsequent attempts must not retry.
    assert len(adapter.begin_turn_calls) == 1
    assert len(adapter.collect_candidate_calls) == 1
    with pytest.raises(OperatorOperationApplied):
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )


def test_complete_job_permitted_in_candidate_is_refused(tmp_path, monkeypatch):
    """A candidate that tries to claim Executive completion must be refused."""

    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, domain_attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter = TypedHermeticConsumptionAdapter(profile=None)

    def complete_job_candidate(turn):
        adapter.collect_candidate_calls.append(turn)
        # Bypass the CandidateResult invariant by constructing via __new__.
        candidate = CandidateResult.__new__(CandidateResult)
        object.__setattr__(candidate, "attempt_id", turn.attempt_id)
        object.__setattr__(candidate, "session_epoch_id", turn.session_epoch_id)
        object.__setattr__(candidate, "process_generation_id", turn.process_generation_id)
        object.__setattr__(candidate, "artifact_digest", "c" * 64)
        object.__setattr__(candidate, "summary", "complete")
        object.__setattr__(candidate, "complete_job_permitted", True)
        return candidate

    adapter.collect_candidate_result = complete_job_candidate  # type: ignore[assignment]
    orchestrator, _ = _fresh_orchestrator_for_domain_attempt(
        runtime, domain_attempt_id, adapter,
    )
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(OperatorOperationApplied, match="durably applied") as error:
        orchestrator.run_domain_consumption_turn(
            session,
            operation_id=operation_id,
            expected_consumption_projection_digest=digest,
        )
    assert "Executive completion" in str(error.value.__cause__)
    assert len(adapter.begin_turn_calls) == 1
    assert len(adapter.collect_candidate_calls) == 1
    assert len(_charge_rows(runtime, root.job_id)) == len(before["coo_provider_charges"]) + 1
    assert runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation_id, OperationReceiptKind.EFFECT_UNKNOWN)
    ) is None
    assert runtime.events.get_event_by_command_id(
        f"ohf-candidate:{adapter.collect_candidate_calls[0].turn_id}"
    ) is None


def test_dedicated_path_does_not_seal_role_result_or_complete(
    tmp_path, monkeypatch,
):
    """Sanity: no ORCHESTRATION_ROLE_RESULT_SEALED nor Job completion."""

    runtime, root, domain, domain_attempt_id, session, adapter, orchestrator, lease, _, _ = _real_consumption_context(tmp_path, monkeypatch)
    generation, operation_id, _, _, digest = _happy_args(
        runtime, root.job_id, domain_attempt_id,
    )
    with runtime.store.read() as connection:
        sealed_before = list(connection.execute(
            "SELECT event_id FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'"
        ))
    receipt = orchestrator.run_domain_consumption_turn(
        session,
        operation_id=operation_id,
        expected_consumption_projection_digest=digest,
    )
    with runtime.store.read() as connection:
        sealed = list(
            connection.execute(
                "SELECT event_id FROM events WHERE event_type=?",
                ("ORCHESTRATION_ROLE_RESULT_SEALED",),
            )
        )
    assert sealed == sealed_before
    attempt = runtime.attempts.get_attempt(domain_attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.CHECKPOINTED
    domain_after = runtime.jobs.get_job(domain.job_id)
    assert domain_after is not None and domain_after.current_attempt_id == domain_attempt_id


def test_missing_native_ack_is_unknown_and_fresh_replay_cannot_dispatch(tmp_path, monkeypatch):
    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter = TypedHermeticConsumptionAdapter(profile=None)
    def missing_native(*, turn, **kwargs):
        adapter.begin_turn_calls.append(turn)
        return TurnStartObservation(acknowledged=True, provider_native_turn_id=None)
    adapter.begin_turn = missing_native
    orchestrator, lease = _fresh_orchestrator_for_domain_attempt(runtime, attempt_id, adapter)
    _, operation, _, _, digest = _happy_args(runtime, root.job_id, attempt_id)
    with pytest.raises(OperatorEffectUnknown, match="could not be bound") as error:
        orchestrator.run_domain_consumption_turn(session, operation_id=operation,
            expected_consumption_projection_digest=digest)
    assert "acknowledged native turn" in str(error.value.__cause__)
    assert len(adapter.begin_turn_calls) == 1
    assert adapter.collect_candidate_calls == []
    assert len(_charge_rows(runtime, root.job_id)) == 1
    assert runtime.events.get_event_by_command_id(
        operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)
    ) is None
    snapshot = _inventory(runtime)
    successor = TypedHermeticConsumptionAdapter(profile=None)
    fresh = _build_orchestrator_with_consumption_adapter(runtime, lease, successor)
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        fresh.run_domain_consumption_turn(session, operation_id=operation,
            expected_consumption_projection_digest=digest)
    assert _inventory(runtime) == snapshot
    assert successor.begin_turn_calls == []


def _real_consumption_context(tmp_path, monkeypatch):
    receipts, adapters = _wrap_start_attempt_to_capture_receipt(monkeypatch)
    runtime, root, domain, attempt_id, session, _ = _settle_reviewed_domain_with_real_supervisor(
        tmp_path, monkeypatch, receipts, adapters,
    )
    adapter = TypedHermeticConsumptionAdapter(profile=None)
    orchestrator, lease = _fresh_orchestrator_for_domain_attempt(runtime, attempt_id, adapter)
    _, op, _, _, digest = _happy_args(runtime, root.job_id, attempt_id)
    return runtime, root, domain, attempt_id, session, adapter, orchestrator, lease, op, digest


def _reserve_context(runtime, orchestrator, session, operation, digest):
    return orchestrator.runtime.begin_operator_domain_consumption_turn(
        session.attempt_id, session.generation, operation,
        expected_consumption_projection_digest=digest,
    )


def _append_negative_event(runtime, source, *, command, payload=None, event_type=None):
    """Adversarial evidence only; positive setup used public actors, never SQL."""
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection,
            aggregate_type=source.aggregate_type, aggregate_id=source.aggregate_id,
            event_type=event_type or source.event_type, actor=source.actor,
            job_id=source.job_id, attempt_id=source.attempt_id,
            worker_id=source.worker_id, quota_class=source.quota_class,
            command_id=command, payload=source.payload if payload is None else payload,
        )


def test_reserved_but_uncommitted_final_cannot_acknowledge(tmp_path, monkeypatch):
    runtime, _, _, attempt, session, _, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    turn = _reserve_context(runtime, o, session, op, digest)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="committed later dispatch"):
        o.runtime.apply_operator_turn(attempt, op, TurnStartObservation("native-later", True))
    assert _inventory(runtime) == before
    assert turn.attempt_id == attempt


def test_committed_final_without_applied_cannot_record_candidate(tmp_path, monkeypatch):
    runtime, _, _, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    turn = _reserve_context(runtime, o, session, op, digest)
    assert o.runtime.commit_operator_provider_dispatch(attempt, op, "begin_turn") is True
    cursor = EventCursor(attempt, turn.session_epoch_id, turn.process_generation_id, turn_id=turn.turn_id)
    events, cursor = adapter.read_events(cursor)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="matching TX-5 APPLIED"):
        o.runtime.finish_operator_candidate(attempt, turn, adapter.collect_candidate_result(turn), events, cursor)
    assert _inventory(runtime) == before


@pytest.mark.parametrize("phase", ["ack", "candidate"])
@pytest.mark.parametrize("forgery", ["dispatch_alias", "intent_alias", "unknown_alias", "final_orphan"])
def test_affiliated_provenance_conflicts_refuse_without_effects(tmp_path, monkeypatch, phase, forgery):
    runtime, root, domain, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    turn = _reserve_context(runtime, o, session, op, digest)
    assert o.runtime.commit_operator_provider_dispatch(attempt, op, "begin_turn") is True
    observation = TurnStartObservation("native-later", True)
    if phase == "candidate":
        o.runtime.apply_operator_turn(attempt, op, observation)
    intent = runtime.events.get_event_by_command_id(op.command_id)
    dispatch = runtime.events.get_event_by_command_id(op.command_id + ":dispatch")
    if forgery == "dispatch_alias":
        _append_negative_event(runtime, dispatch, command=op.command_id + ":dispatch-alias")
    elif forgery == "intent_alias":
        _append_negative_event(runtime, intent, command=op.command_id + ":intent-alias")
    elif forgery == "unknown_alias":
        _append_negative_event(runtime, intent, command=op.command_id + ":unknown-alias",
            event_type=OperationReceiptKind.EFFECT_UNKNOWN.value,
            payload={"schema_version": "mastermind.operator_harness_effect_unknown/v1", "phase": "begin_turn", "detail": "unknown"})
    else:
        source = next(event for event in runtime.events.list_events(job_id=domain.job_id)
            if event.event_type == "COO_DOMAIN_CONSUMPTION_CHARGED")
        _append_negative_event(runtime, source, command=op.command_id + ":orphan-charge")
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        if phase == "ack":
            o.runtime.apply_operator_turn(attempt, op, observation)
        else:
            cursor = EventCursor(attempt, turn.session_epoch_id, turn.process_generation_id, turn_id=turn.turn_id)
            events, cursor = adapter.read_events(cursor)
            o.runtime.finish_operator_candidate(attempt, turn, adapter.collect_candidate_result(turn), events, cursor)
    assert _inventory(runtime) == before


def test_duplicate_later_applied_cannot_record_candidate(tmp_path, monkeypatch):
    runtime, _, _, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    turn = _reserve_context(runtime, o, session, op, digest)
    assert o.runtime.commit_operator_provider_dispatch(attempt, op, "begin_turn") is True
    o.runtime.apply_operator_turn(attempt, op, TurnStartObservation("native-later", True))
    applied = runtime.events.get_event_by_command_id(operation_receipt_command_id(op, OperationReceiptKind.APPLIED))
    _append_negative_event(runtime, applied, command=op.command_id + ":applied-alias")
    before = _inventory(runtime)
    cursor = EventCursor(attempt, turn.session_epoch_id, turn.process_generation_id, turn_id=turn.turn_id)
    events, cursor = adapter.read_events(cursor)
    with pytest.raises(StateConflict, match="later APPLIED is not unique"):
        o.runtime.finish_operator_candidate(attempt, turn, adapter.collect_candidate_result(turn), events, cursor)
    assert _inventory(runtime) == before


def test_durable_ack_and_candidate_evidence_replay_is_idempotent(tmp_path, monkeypatch):
    runtime, _, _, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    receipt = o.run_domain_consumption_turn(session, operation_id=op, expected_consumption_projection_digest=digest)
    before = _inventory(runtime)
    o.runtime.apply_operator_turn(attempt, op, receipt.start)
    o.runtime.finish_operator_candidate(attempt, receipt.turn, receipt.candidate, receipt.events, receipt.cursor)
    assert _inventory(runtime) == before
    assert len(adapter.begin_turn_calls) == 1


@pytest.mark.parametrize("foreign_field", ["attempt_id", "session_epoch_id", "process_generation_id"])
def test_caller_known_foreign_cursor_refuses_before_reservation(tmp_path, monkeypatch, foreign_field):
    runtime, _, _, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    cursor = EventCursor(attempt, session.epoch.session_epoch_id, session.generation.process_generation_id)
    cursor = dataclasses.replace(cursor, **{foreign_field: "foreign"})
    before = _inventory(runtime)
    with pytest.raises(OperatorHarnessOrchestrationError, match="identity mismatch"):
        o.run_domain_consumption_turn(session, operation_id=op, expected_consumption_projection_digest=digest, cursor=cursor)
    assert _inventory(runtime) == before
    assert adapter.begin_turn_calls == []


def test_fresh_orchestrator_cannot_dispatch_an_already_committed_turn(tmp_path, monkeypatch):
    runtime, root, _, attempt, session, adapter, o, lease, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    _reserve_context(runtime, o, session, op, digest)
    assert o.runtime.commit_operator_provider_dispatch(attempt, op, "begin_turn") is True
    fresh = _build_orchestrator_with_consumption_adapter(runtime, lease, adapter)
    with pytest.raises(OperatorEffectUnknown, match="previously committed"):
        fresh.run_domain_consumption_turn(session, operation_id=op, expected_consumption_projection_digest=digest)
    assert adapter.begin_turn_calls == []
    assert len(_charge_rows(runtime, root.job_id)) == 1
    unknown = runtime.events.get_event_by_command_id(operation_receipt_command_id(op, OperationReceiptKind.EFFECT_UNKNOWN))
    assert unknown is not None
    before = _inventory(runtime)
    fresh_again = _build_orchestrator_with_consumption_adapter(runtime, lease, adapter)
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        fresh_again.run_domain_consumption_turn(session, operation_id=op, expected_consumption_projection_digest=digest)
    assert _inventory(runtime) == before


def test_generation_cursor_is_bound_before_dispatch_with_offsets_preserved(tmp_path, monkeypatch):
    runtime, root, _, attempt, session, adapter, o, _, op, digest = _real_consumption_context(tmp_path, monkeypatch)
    cursor = EventCursor(attempt, session.epoch.session_epoch_id,
        session.generation.process_generation_id, local_sequence=23,
        provider_replay_cursor="provider-offset-23")
    assert cursor.turn_id is None
    original_dispatch = o.runtime.commit_operator_provider_dispatch
    def dispatch(*args, **kwargs):
        # No provider read/call occurred before the durable boundary.
        assert adapter.begin_turn_calls == [] and adapter.read_events_calls == []
        return original_dispatch(*args, **kwargs)
    monkeypatch.setattr(o.runtime, "commit_operator_provider_dispatch", dispatch)
    receipt = o.run_domain_consumption_turn(session, operation_id=op,
        expected_consumption_projection_digest=digest, cursor=cursor)
    read_cursor = adapter.read_events_calls[0]
    assert read_cursor.turn_id == receipt.turn.turn_id
    assert read_cursor.local_sequence == 23
    assert read_cursor.provider_replay_cursor == "provider-offset-23"
    assert receipt.cursor.turn_id == receipt.turn.turn_id
    assert receipt.cursor.local_sequence == 24
    assert cursor.turn_id is None and cursor.local_sequence == 23
    assert len(adapter.begin_turn_calls) == 1
    assert len(_charge_rows(runtime, root.job_id)) == 1
    candidate = runtime.events.get_event_by_command_id(f"ohf-candidate:{receipt.turn.turn_id}")
    assert candidate is not None
    assert candidate.payload["cursor"]["turn_id"] == receipt.turn.turn_id
    assert candidate.payload["cursor"]["local_sequence"] == 24
