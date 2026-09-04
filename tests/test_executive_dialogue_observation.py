from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)

from control_plane import executive_dialogue_observation as observation_mod
from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER,
    RECONCILE_WAKE,
    SUBMIT_WAKE,
    WAKE_REQUEST_SCHEMA,
    WAKE_RESPONSE_SCHEMA,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    ActiveObservationFacts,
    CanonicalTerminalWakeCandidate,
    DialogueObservationFacts,
    DialogueObservationProtocolError,
    PublicRuntimeBindingFacts,
    TerminalObservationFacts,
    TerminalProjectionReceiptFacts,
    parse_observation_request,
    parse_wake_request,
    reduce_dialogue_observation,
    read_canonical_terminal_wake,
    wake_response_bytes,
)
from control_plane.session_targets import WakeRoute
from control_plane.executive_runtime import Runtime
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    LedgerPhase,
    WAKE_AGGREGATE_TYPE,
    attempt_record,
    event_payload_for,
    make_delivery_attempt,
    requested_record,
)
from tests.test_company_dialogue_runtime_binding import parent as valid_parent
from tests.test_slack_agent_dialogue_executive_terminal_return_projector import (
    _candidate as terminal_candidate,
)


def _request(parent: dict | None = None) -> bytes:
    return json.dumps(
        {
            "schema": REQUEST_SCHEMA,
            "request_id": "observation-request-001",
            "parent": parent or valid_parent(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _wake_pair() -> tuple[object, WakeRoute]:
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "a" * 64,
        declared_target_seat="ceo",
        job_id="JOB-101",
        attempt_id="ATT-" + "2" * 32,
        root_job_id="JOB-100",
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    route = WakeRoute(
        obligation_id=obligation.obligation_id,
        session_alias="EXECUTIVE-CEO-A",
        target_seat="ceo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        binding_id="bind-dialogue-wake-0001",
        binding_generation=7,
        route_digest="1" * 16,
        destination_digest="2" * 16,
        policy_digest="3" * 16,
        root_job_id="JOB-100",
        workstream=None,
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        requires_runtime_binding=True,
        binding_ready=True,
        human_required=False,
        policy_version="wake-policy-v1",
        interface_version="codex-app-server-wake/v1",
    )
    return obligation, route


def _candidate_reference(parent: dict | None = None) -> dict[str, str]:
    dialogue_parent = parent or valid_parent()
    response = reduce_dialogue_observation(
        parent=dialogue_parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(active=(_active(dialogue_parent),)),
    )
    observation = response["observation"]
    return {
        "mode": response["mode"],
        "root_job_id": observation["root_job_id"],
        "job_id": observation["job_id"],
        "attempt_id": observation["attempt_id"],
        "worker_id": observation["worker_id"],
        "evidence_digest": observation["evidence_digest"],
    }


def _wake_request(operation: str = RECONCILE_WAKE) -> bytes:
    obligation, route = _wake_pair()
    return json.dumps(
        {
            "schema": WAKE_REQUEST_SCHEMA,
            "operation": operation,
            "parent": valid_parent(),
            "thread_ts": "1788000000.123456",
            "candidate": _candidate_reference(),
            "obligation": obligation.to_dict(),
            "route": route.to_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _active(parent: dict | None = None) -> ActiveObservationFacts:
    dialogue_parent = parent or valid_parent()
    return ActiveObservationFacts(
        root_job_id="JOB-100",
        job_id="JOB-101",
        attempt_id="ATT-" + "2" * 32,
        worker_id="worker-01",
        attempt_status="RUNNING",
        worker_status="BUSY",
        execution_profile_id="profile-readonly",
        execution_profile_digest="1" * 64,
        capability_policy_digest="2" * 64,
        runtime_binding=PublicRuntimeBindingFacts(
            session_alias="MM-COO-SEAT",
            binding_id="bind-observation-0001",
            binding_generation=7,
            reasoning_surface="codex",
        ),
        parent_fingerprint=dialogue_parent["fingerprint"],
        company_dialogue_server_identity=SERVER_IDENTITY,
        company_dialogue_server_version=SERVER_VERSION,
        company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
        company_dialogue_attested=True,
        target_bindings={
            "coo": PublicRuntimeBindingFacts(
                session_alias="MM-COO-SEAT",
                binding_id="bind-observation-0001",
                binding_generation=7,
                reasoning_surface="codex",
            ),
            "ceo": PublicRuntimeBindingFacts(
                session_alias="EXECUTIVE-CEO-A",
                binding_id="bind-dialogue-wake-0001",
                binding_generation=7,
                reasoning_surface="codex",
            ),
        },
    )


def _terminal(parent: dict | None = None) -> TerminalObservationFacts:
    dialogue_parent = parent or valid_parent()
    candidate = terminal_candidate()
    candidate = dataclasses.replace(
        candidate,
        attempt_id="ATT-" + "b" * 32,
        operation_key=dialogue_parent["operation_key"],
        session_ref=dialogue_parent["session_ref"],
        dialogue_source=dataclasses.replace(
            candidate.dialogue_source,
            work_ref=dialogue_parent["work_ref"],
            commission_ref=dialogue_parent["commission_ref"],
            watch_mode=dialogue_parent["watch_mode"],
        ),
    )
    receipt = TerminalProjectionReceiptFacts(
        action="POSTED",
        message_key=candidate.message_key,
        fingerprint="4" * 64,
        message_ts="1787961600.000002",
        duplicate_timestamps=(),
        thread_ts="1787961600.000001",
        parent_author_user_id="U0RELAY001",
        parent_fingerprint=dialogue_parent["fingerprint"],
    )
    return TerminalObservationFacts(
        candidate=candidate,
        projection_receipt=receipt,
        projection_effect="APPLIED",
        binding_revalidated=True,
        target_bindings=_active(dialogue_parent).target_bindings,
    )


def test_strict_request_reuses_canonical_v2_parent_parser() -> None:
    parsed = parse_observation_request(_request())
    assert parsed.parent == valid_parent()
    assert parsed.request_id == "observation-request-001"

    duplicate = _request().decode("utf-8").replace(
        '"schema":"mastermind.executive_dialogue_observation_request.v1"',
        '"schema":"mastermind.executive_dialogue_observation_request.v1",'
        '"schema":"mastermind.executive_dialogue_observation_request.v1"',
        1,
    )
    hostile = (
        duplicate.encode("utf-8"),
        b'{"schema":NaN}',
        _request()[:-1] + b',"root_job_id":"JOB-999"}',
        _request() + b"\n{}",
        b"\xff",
    )
    for payload in hostile:
        with pytest.raises(DialogueObservationProtocolError) as exc:
            parse_observation_request(payload)
        assert exc.value.code == "REQUEST_REFUSED"
        assert "JOB-999" not in str(exc.value)

    for forbidden_key, forbidden_value in (
        ("operation", "RESOLVE_PARENT"),
        ("thread_ts", "1787961600.000001"),
    ):
        legacy = json.loads(_request())
        legacy[forbidden_key] = forbidden_value
        with pytest.raises(DialogueObservationProtocolError, match="REQUEST_REFUSED"):
            parse_observation_request(json.dumps(legacy).encode("utf-8"))


@pytest.mark.parametrize("operation", [RECONCILE_WAKE, SUBMIT_WAKE])
def test_wake_request_is_closed_non_authoritative_and_parent_bound(
    operation: str,
) -> None:
    obligation, route = _wake_pair()
    parsed = parse_wake_request(_wake_request(operation))

    assert parsed.operation == operation
    assert parsed.parent == valid_parent()
    assert parsed.thread_ts == "1788000000.123456"
    assert parsed.candidate.to_dict() == _candidate_reference()
    assert parsed.obligation == obligation
    assert parsed.proposed_route == route

    hostile = json.loads(_wake_request(operation))
    hostile["route"]["native_handle"] = "provider-private"
    with pytest.raises(DialogueObservationProtocolError, match="REQUEST_REFUSED"):
        parse_wake_request(json.dumps(hostile).encode("utf-8"))

    hostile = json.loads(_wake_request(operation))
    hostile["obligation"]["declared_target_seat"] = "coo"
    with pytest.raises(DialogueObservationProtocolError, match="REQUEST_REFUSED"):
        parse_wake_request(json.dumps(hostile).encode("utf-8"))

    hostile = json.loads(_wake_request(operation))
    hostile["operation"] = "WAKE_SUBMIT"
    with pytest.raises(DialogueObservationProtocolError, match="REQUEST_REFUSED"):
        parse_wake_request(json.dumps(hostile).encode("utf-8"))


@pytest.mark.parametrize("state", ["MISSING", "RECORDED", "EFFECT_UNKNOWN"])
def test_wake_response_has_only_closed_reconciliation_states(state: str) -> None:
    raw = wake_response_bytes(state=state, reason="FIXED_REASON")
    assert json.loads(raw) == {
        "schema": WAKE_RESPONSE_SCHEMA,
        "state": state,
        "reason": "FIXED_REASON",
    }
    with pytest.raises(DialogueObservationProtocolError):
        wake_response_bytes(state="SUBMITTED", reason="FIXED_REASON")


def test_active_reducer_exposes_only_public_current_worker_facts() -> None:
    parent = valid_parent()
    response = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(active=(_active(parent),)),
    )
    assert response["schema"] == RESPONSE_SCHEMA
    assert response["state"] == "RESOLVED"
    assert response["mode"] == ACTIVE_CURRENT_WORKER
    assert response["observation"]["runtime_binding"] == {
        "session_alias": "MM-COO-SEAT",
        "binding_id": "bind-observation-0001",
        "binding_generation": 7,
        "reasoning_surface": "codex",
    }
    assert response["target_bindings"] == {
        "coo": {
            "session_alias": "MM-COO-SEAT",
            "binding_id": "bind-observation-0001",
            "binding_generation": 7,
            "reasoning_surface": "codex",
        },
        "ceo": {
            "session_alias": "EXECUTIVE-CEO-A",
            "binding_id": "bind-dialogue-wake-0001",
            "binding_generation": 7,
            "reasoning_surface": "codex",
        },
    }
    encoded = json.dumps(response, sort_keys=True)
    for forbidden in (
        "native_handle",
        "account_label",
        "provider_home",
        "credential_home",
        "token",
        "local_path",
    ):
        assert forbidden not in encoded
    assert response["action_authoritative"] is False
    assert response["provider_action_authorized"] is False
    assert response["wake_write_authorized"] is False
    assert response["lifecycle_write_authorized"] is False


@pytest.mark.parametrize(
    ("change", "state", "reason"),
    [
        ({"attempt_status": "COMPLETED"}, "UNAVAILABLE", "CURRENT_ATTEMPT_INACTIVE"),
        ({"worker_status": "AVAILABLE"}, "UNAVAILABLE", "CURRENT_WORKER_INACTIVE"),
        ({"company_dialogue_attested": False}, "HELD", "CAPABILITY_NOT_ATTESTED"),
        ({"parent_fingerprint": "f" * 64}, "HELD", "DIALOGUE_PARENT_STALE"),
    ],
)
def test_active_reducer_fails_closed_without_leaking_fact_payload(
    change: dict[str, object], state: str, reason: str
) -> None:
    response = reduce_dialogue_observation(
        parent=valid_parent(),
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(active=(dataclasses.replace(_active(), **change),)),
    )
    assert response == {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}


def test_terminal_requires_one_applied_revalidated_receipt() -> None:
    parent = valid_parent()
    resolved = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(terminal=(_terminal(parent),)),
    )
    assert resolved["state"] == "RESOLVED"
    assert resolved["mode"] == "TERMINAL_RESULT"
    assert resolved["observation"]["projection_effect"] == "APPLIED"
    assert set(resolved["observation"]["candidate"]) == {
        "root_job_id",
        "job_id",
        "attempt_id",
        "worker_id",
        "runtime_status",
        "result_status",
        "result_envelope_digest",
        "terminal_evidence_digest",
        "artifact_receipt_digest",
        "validation_receipt_digest",
        "effective_grant_digest",
        "terminal_at",
        "projection_command_digest",
    }
    assert set(resolved["observation"]["projection_receipt"]) == {
        "action",
        "message_fingerprint",
        "receipt_digest",
    }

    for change, state, reason in (
        ({"projection_effect": "EFFECT_UNKNOWN"}, "UNKNOWN", "R2_EFFECT_UNKNOWN"),
        ({"projection_effect": "ATTEMPTED"}, "HELD", "R2_RECEIPT_MISSING"),
        ({"projection_effect": "PROVEN_NO_EFFECT"}, "HELD", "R2_RECEIPT_MISSING"),
        ({"binding_revalidated": False}, "HELD", "R2_BINDING_UNAVAILABLE"),
    ):
        response = reduce_dialogue_observation(
            parent=parent,
            thread_ts="1787961600.000001",
            facts=DialogueObservationFacts(
                terminal=(dataclasses.replace(_terminal(parent), **change),)
            ),
        )
        assert response == {"schema": RESPONSE_SCHEMA, "state": state, "reason": reason}

    @dataclasses.dataclass(frozen=True)
    class LookalikeReceipt:
        parent_fingerprint: str

    wrong_shape = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(
            terminal=(
                dataclasses.replace(
                    _terminal(parent),
                    projection_receipt=LookalikeReceipt(parent["fingerprint"]),
                ),
            )
        ),
    )
    assert wrong_shape == {
        "schema": RESPONSE_SCHEMA,
        "state": "HELD",
        "reason": "TERMINAL_FACTS_INVALID",
    }


@pytest.mark.parametrize(
    "hostile_summary",
    (
        "xoxb-0123456789abcdef-secret",
        "/Users/private/.config/provider/token",
        "first line\nsecond line\x00",
        "<@U0BRETDUAS2|Chris> private Slack text",
        "Traceback (most recent call last): private chain-of-thought",
    ),
)
def test_terminal_wire_omits_hostile_summary_and_full_receipt(
    hostile_summary: str,
) -> None:
    parent = valid_parent()
    terminal = _terminal(parent)
    facts = dataclasses.replace(
        terminal,
        candidate=dataclasses.replace(terminal.candidate, summary=hostile_summary),
    )

    response = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(terminal=(facts,)),
    )

    assert response["state"] == "RESOLVED"
    encoded = json.dumps(response, sort_keys=True)
    assert hostile_summary not in encoded
    for forbidden_key in (
        "summary",
        "dialogue_source",
        "message_key",
        "message_ts",
        "thread_ts",
        "parent_author_user_id",
        "parent_fingerprint",
    ):
        assert f'"{forbidden_key}"' not in encoded


def test_terminal_wire_refuses_malicious_receipt_value_without_reflection() -> None:
    parent = valid_parent()
    terminal = _terminal(parent)
    malicious_value = "xoxb-0123456789abcdef-secret"

    response = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(
            terminal=(
                dataclasses.replace(
                    terminal,
                    projection_receipt=dataclasses.replace(
                        terminal.projection_receipt,
                        message_ts=malicious_value,
                    ),
                ),
            )
        ),
    )

    assert response == {
        "schema": RESPONSE_SCHEMA,
        "state": "HELD",
        "reason": "TERMINAL_FACTS_INVALID",
    }
    assert malicious_value not in json.dumps(response)


def test_terminal_wire_refuses_oversized_multibyte_summary_without_reflection() -> None:
    parent = valid_parent()
    terminal = _terminal(parent)
    hostile_summary = "\N{SNOWMAN}" * 4096

    response = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(
            terminal=(
                dataclasses.replace(
                    terminal,
                    candidate=dataclasses.replace(
                        terminal.candidate,
                        summary=hostile_summary,
                    ),
                ),
            )
        ),
    )

    assert response == {
        "schema": RESPONSE_SCHEMA,
        "state": "HELD",
        "reason": "TERMINAL_FACTS_INVALID",
    }
    assert hostile_summary not in json.dumps(response)


def test_mode_cardinality_is_closed_and_non_interchangeable() -> None:
    parent = valid_parent()
    for facts, reason in (
        (DialogueObservationFacts(active=(_active(), _active())), "MULTIPLE_ACTIVE_BINDINGS"),
        (
            DialogueObservationFacts(terminal=(_terminal(), _terminal())),
            "MULTIPLE_TERMINAL_BINDINGS",
        ),
    ):
        response = reduce_dialogue_observation(
            parent=parent,
            thread_ts="1787961600.000001",
            facts=facts,
        )
        assert response == {
            "schema": RESPONSE_SCHEMA,
            "state": "CONFLICT",
            "reason": reason,
        }

    active_precedence = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(
            active=(_active(),),
            terminal=(_terminal(), _terminal()),
        ),
    )
    assert active_precedence["state"] == "RESOLVED"
    assert active_precedence["mode"] == ACTIVE_CURRENT_WORKER

    assert reduce_dialogue_observation(
        parent=parent,
        thread_ts="1787961600.000001",
        facts=DialogueObservationFacts(complete=False),
    ) == {
        "schema": RESPONSE_SCHEMA,
        "state": "UNKNOWN",
        "reason": "OBSERVATION_SCAN_INCOMPLETE",
    }


def _terminal_wake_candidate(parent: dict) -> CanonicalTerminalWakeCandidate:
    terminal = _terminal(parent).candidate
    return CanonicalTerminalWakeCandidate(
        root_job_id=terminal.root_job_id,
        job_id=terminal.job_id,
        attempt_id=terminal.attempt_id,
        worker_id=terminal.worker_id,
    )


def _persist_dialogue_wake(
    runtime: Runtime,
    *,
    candidate: CanonicalTerminalWakeCandidate,
    seed: str,
):
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + seed * 64,
        declared_target_seat="ceo",
        job_id=candidate.job_id,
        attempt_id=candidate.attempt_id,
        root_job_id=candidate.root_job_id,
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    record = requested_record(obligation)
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        runtime.store.append_event(
            connection,
            aggregate_type=WAKE_AGGREGATE_TYPE,
            aggregate_id=obligation.obligation_id,
            event_type=record.phase.value,
            actor="fixture",
            job_id=obligation.job_id,
            attempt_id=obligation.attempt_id,
            payload=event_payload_for(record),
            command_id=record.command_id,
        )
        connection.commit()
    finally:
        connection.close()
    return obligation


def test_runtime_canonical_terminal_wake_facade_owns_one_fixed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing the fixed public Runtime owner must break the direct facade."""

    reader = getattr(observation_mod, "read_runtime_canonical_terminal_wake", None)
    facts_owner = getattr(observation_mod, "runtime_canonical_terminal_facts", None)
    assert callable(reader), "standalone Runtime reader is not exposed"
    assert callable(facts_owner), "canonical Runtime facts owner is not exposed"

    runtime = Runtime.at(tmp_path / "standalone-runtime-read")
    parent = valid_parent()
    terminal = _terminal(parent)
    candidate = _terminal_wake_candidate(parent)
    _persist_dialogue_wake(runtime, candidate=candidate, seed="e")
    original_read = runtime.store.read
    read_calls = 0
    owner_connections: list[object] = []

    def counted_read():
        nonlocal read_calls
        read_calls += 1
        return original_read()

    def observed_owner(runtime_arg, candidate_arg, connection_arg):
        assert runtime_arg is runtime
        assert candidate_arg == candidate
        owner_connections.append(connection_arg)
        return DialogueObservationFacts(terminal=(terminal,))

    monkeypatch.setattr(runtime.store, "read", counted_read)
    monkeypatch.setattr(
        observation_mod,
        "runtime_canonical_terminal_facts",
        observed_owner,
    )

    with original_read() as connection:
        event_count_before = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )
        supplied = reader(
            runtime=runtime,
            source_root_job_id=candidate.root_job_id,
            candidate=candidate,
            connection=connection,
        )
        assert read_calls == 0
        assert owner_connections == [connection]

    owned = reader(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
    )
    assert read_calls == 1
    assert len(owner_connections) == 2
    with original_read() as connection:
        event_count_after = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )

    assert supplied.to_dict() == owned.to_dict()
    assert owned.state == "RESOLVED"
    assert event_count_after == event_count_before


def test_canonical_terminal_wake_read_is_exact_public_and_unambiguous(
    tmp_path: Path,
) -> None:
    runtime = Runtime.at(tmp_path / "canonical-read")
    parent = valid_parent()
    terminal = _terminal(parent)
    candidate = _terminal_wake_candidate(parent)
    obligation = _persist_dialogue_wake(
        runtime,
        candidate=candidate,
        seed="a",
    )
    facts_provider = lambda _runtime, _candidate, _connection: DialogueObservationFacts(
        terminal=(terminal,)
    )

    result = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=facts_provider,
    )
    with runtime.store.read() as connection:
        event_count_before = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )
        caller_snapshot_result = read_canonical_terminal_wake(
            runtime=runtime,
            source_root_job_id=candidate.root_job_id,
            candidate=candidate,
            facts_provider=facts_provider,
            connection=connection,
        )
    replay = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=facts_provider,
    )
    with runtime.store.read() as connection:
        event_count_after = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )

    assert result.state == "RESOLVED"
    assert result.reason == "CANONICAL_TERMINAL_WAKE_RESOLVED"
    assert result.terminal_state == "APPLIED"
    assert result.wake_state == "PENDING_RETRYABLE"
    assert result.terminal_applied is True
    assert result.wake is not None
    assert result.wake.obligation_id == obligation.obligation_id
    assert result.wake.status == "PENDING_RETRYABLE"
    assert result.source_receipt is not None
    assert result.terminal is not None
    assert result.terminal.source_owner == "executive_terminal_return"
    assert result.wake.source_owner == "wake_ledger"
    assert result.source_receipt.freshness == "SOURCE_EVIDENCE_TIME"
    assert caller_snapshot_result.to_dict() == result.to_dict()
    assert replay.to_dict() == result.to_dict()
    assert event_count_after == event_count_before
    assert result.source_receipt.terminal_source_owner == (
        "executive_terminal_return"
    )
    assert result.source_receipt.wake_source_owner == "wake_ledger"
    assert result.action_authoritative is False
    assert result.provider_action_authorized is False
    assert result.wake_write_authorized is False
    assert result.lifecycle_write_authorized is False
    encoded = json.dumps(result.to_dict(), sort_keys=True)
    for forbidden in (
        "native_handle",
        "provider_session",
        "account_label",
        "payload_json",
        "slack_text",
        "credential",
        "thread_ts",
        "message_ts",
        "message_key",
        "parent_author_user_id",
        obligation.source_ref,
    ):
        assert forbidden not in encoded

    historical_sibling = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "f" * 64,
        declared_target_seat="ceo",
        job_id="JOB-999",
        attempt_id="ATT-" + "9" * 32,
        root_job_id=candidate.root_job_id,
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    foreign_record = requested_record(historical_sibling)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type=WAKE_AGGREGATE_TYPE,
            aggregate_id=historical_sibling.obligation_id,
            event_type=foreign_record.phase.value,
            actor="fixture",
            job_id=None,
            attempt_id=None,
            payload=event_payload_for(foreign_record),
            command_id=foreign_record.command_id,
        )
    still_exact = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=facts_provider,
    )
    assert still_exact.state == "RESOLVED"
    assert still_exact.wake is not None
    assert still_exact.wake.obligation_id == obligation.obligation_id

    wrong = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=dataclasses.replace(candidate, worker_id="wrong-worker"),
        facts_provider=facts_provider,
    )
    assert wrong.state == "ABSENT"
    assert wrong.reason == "CANDIDATE_NOT_CANONICAL"
    assert wrong.terminal_state == "MISSING"
    assert wrong.terminal_applied is False
    assert wrong.wake is None

    _persist_dialogue_wake(
        runtime,
        candidate=candidate,
        seed="b",
    )
    ambiguous = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=facts_provider,
    )
    assert ambiguous.state == "AMBIGUOUS"
    assert ambiguous.reason == "MULTIPLE_WAKE_OBLIGATIONS"
    assert ambiguous.terminal_state == "APPLIED"
    assert ambiguous.wake_state == "AMBIGUOUS"
    assert ambiguous.terminal_applied is True
    assert ambiguous.wake is None


def test_canonical_terminal_wake_read_refuses_incomplete_malformed_and_over_budget(
    tmp_path: Path,
) -> None:
    parent = valid_parent()
    terminal = _terminal(parent)
    candidate = _terminal_wake_candidate(parent)

    incomplete_runtime = Runtime.at(tmp_path / "incomplete")
    with incomplete_runtime.store.transaction() as connection:
        incomplete_runtime.store.append_event(
            connection,
            aggregate_type="terminal_return_projection",
            aggregate_id=candidate.attempt_id,
            event_type="EXECUTIVE_TERMINAL_RETURN_APPLIED",
            actor="fixture",
            job_id=None,
            attempt_id=None,
            payload={"projection_effect": "APPLIED"},
            command_id="fixture:standalone-applied",
        )
    incomplete = read_canonical_terminal_wake(
        runtime=incomplete_runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=lambda _runtime, _candidate, _connection: DialogueObservationFacts(),
    )
    assert incomplete.state == "ABSENT"
    assert incomplete.reason == "CANONICAL_TERMINAL_ABSENT"
    assert incomplete.terminal_state == "MISSING"

    effect_unknown = read_canonical_terminal_wake(
        runtime=incomplete_runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=lambda _runtime, _candidate, _connection: DialogueObservationFacts(
            terminal=(dataclasses.replace(terminal, projection_effect="EFFECT_UNKNOWN"),)
        ),
    )
    assert effect_unknown.state == "EFFECT_UNKNOWN"
    assert effect_unknown.reason == "CANONICAL_TERMINAL_EFFECT_UNKNOWN"
    assert effect_unknown.terminal_state == "EFFECT_UNKNOWN"
    assert effect_unknown.terminal_applied is False

    drifted_terminal = dataclasses.replace(
        terminal,
        projection_receipt=dataclasses.replace(
            terminal.projection_receipt,
            message_key="terminal-return:drifted",
        ),
    )
    receipt_drift = read_canonical_terminal_wake(
        runtime=incomplete_runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=lambda _runtime, _candidate, _connection: DialogueObservationFacts(
            terminal=(drifted_terminal,)
        ),
    )
    assert receipt_drift.state == "UNAVAILABLE"
    assert receipt_drift.reason == "CANONICAL_TERMINAL_UNAVAILABLE"

    malformed_runtime = Runtime.at(tmp_path / "malformed")
    malformed_obligation = _persist_dialogue_wake(
        malformed_runtime,
        candidate=candidate,
        seed="c",
    )
    malformed_route = dataclasses.replace(
        _wake_pair()[1],
        obligation_id=malformed_obligation.obligation_id,
        root_job_id=candidate.root_job_id,
    )
    delivered_without_attempt = attempt_record(
        make_delivery_attempt(
            malformed_obligation,
            malformed_route,
            attempt_n=1,
        ),
        LedgerPhase.DELIVERED,
    )
    with malformed_runtime.store.transaction() as connection:
        malformed_runtime.store.append_event(
            connection,
            aggregate_type=WAKE_AGGREGATE_TYPE,
            aggregate_id=malformed_obligation.obligation_id,
            event_type=delivered_without_attempt.phase.value,
            actor="fixture",
            job_id=None,
            attempt_id=None,
            payload=event_payload_for(delivered_without_attempt),
            command_id=delivered_without_attempt.command_id,
        )
    malformed = read_canonical_terminal_wake(
        runtime=malformed_runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=lambda _runtime, _candidate, _connection: DialogueObservationFacts(
            terminal=(terminal,)
        ),
    )
    assert malformed.state == "CONFLICT"
    assert malformed.reason == "WAKE_HISTORY_INVALID"
    assert malformed.wake_state == "CONFLICT"

    budget_runtime = Runtime.at(tmp_path / "budget")
    budget_obligation = _persist_dialogue_wake(
        budget_runtime,
        candidate=candidate,
        seed="d",
    )
    with budget_runtime.store.transaction() as connection:
        for ordinal in range(64):
            budget_runtime.store.append_event(
                connection,
                aggregate_type=WAKE_AGGREGATE_TYPE,
                aggregate_id=budget_obligation.obligation_id,
                event_type="NOISE",
                actor="fixture",
                job_id=None,
                attempt_id=None,
                payload={"ordinal": ordinal},
                command_id=f"fixture:wake-noise:{ordinal}",
            )
    over_budget = read_canonical_terminal_wake(
        runtime=budget_runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=candidate,
        facts_provider=lambda _runtime, _candidate, _connection: DialogueObservationFacts(
            terminal=(terminal,)
        ),
    )
    assert over_budget.state == "UNAVAILABLE"
    assert over_budget.reason == "WAKE_EVENT_BUDGET_EXCEEDED"
    assert over_budget.wake_state == "OVERFLOW"
