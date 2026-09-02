from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-09-02-w3c-dialogue-observation-authority-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-02-w3c-dialogue-observation-authority.md"
START = "<!-- W3C-P0-CONTRACT:START -->"
END = "<!-- W3C-P0-CONTRACT:END -->"


def _contract() -> dict[str, object]:
    text = SPEC.read_text(encoding="utf-8")
    assert text.count(START) == 1
    assert text.count(END) == 1
    body = text.split(START, 1)[1].split(END, 1)[0].strip()
    assert body.startswith("```json\n") and body.endswith("\n```")
    return json.loads(body[len("```json\n") : -len("\n```")])


def _validate(document: dict[str, object]) -> None:
    assert document["schema"] == "mastermind.w3c_dialogue_observation_authority.v1"
    assert document["operation"] == "w3c-p0-dialogue-observation-authority-20260902-sol-001"

    current = document["current_state"]
    assert isinstance(current, dict)
    assert current["capability"] == "SPEC_ONLY"
    assert current["authorized_modes"] == []
    assert current["production_armed"] is False
    assert current["provider_effect"] is False
    assert current["runtime_effect"] is False

    modes = document["modes"]
    assert isinstance(modes, dict)
    assert set(modes) == {"ACTIVE_CURRENT_WORKER", "TERMINAL_RESULT"}
    active = modes["ACTIVE_CURRENT_WORKER"]
    terminal = modes["TERMINAL_RESULT"]
    assert active["status"] == "HELD_PREDECESSOR_UNPROTECTED"
    assert terminal["status"] == "HELD_RET2_NOT_BUILT"
    assert "EXACT_PARENT_BINDING_RECEIPT" in active["required_facts"]
    assert "CURRENT_BUSY_WORKER" in active["required_facts"]
    assert "CURRENT_RUNTIME_BINDING" in active["required_facts"]
    assert "WORKER_DIALOGUE_CALLER_REPLAY" in active["forbidden_substitutes"]
    assert "RET2_PROJECTION_EFFECT_KNOWN" in terminal["required_facts"]
    assert terminal["accepted_projection_effects"] == ["APPLIED", "RECOVERED"]
    assert "SLACK_RESULT_TEXT_ALONE" in terminal["forbidden_substitutes"]
    assert "EFFECT_UNKNOWN_PROJECTION" in terminal["forbidden_substitutes"]

    request = document["request_contract"]
    assert request["operation"] == "resolve_dialogue_observation"
    assert request["parent_is_untrusted_lookup_input"] is True
    assert set(request["exact_keys"]) == {"schema", "request_id", "parent"}
    assert set(request["parent_required_identity"]) == {
        "schema",
        "work_ref",
        "commission_ref",
        "session_ref",
        "operation_key",
        "watch_mode",
        "allowed_sol_user_ids",
        "created_at",
        "fingerprint",
    }
    for forbidden in (
        "job_id",
        "attempt_id",
        "worker_id",
        "runtime_binding",
        "native_handle",
        "target_seat",
        "mode",
    ):
        assert forbidden in request["caller_forbidden_fields"]

    response = document["response_contract"]
    assert set(response["resolved_modes"]) == {"ACTIVE_CURRENT_WORKER", "TERMINAL_RESULT"}
    assert response["public_runtime_binding_fields"] == [
        "session_alias",
        "binding_id",
        "binding_generation",
        "reasoning_surface",
    ]
    for secret in (
        "native_handle",
        "account_label",
        "token",
        "secret",
        "raw_message_body",
        "local_path",
    ):
        assert secret in response["forbidden_response_fields"]
    assert set(response["always_false_authority_flags"]) == {
        "action_authoritative",
        "provider_action_authorized",
        "wake_write_authorized",
        "lifecycle_write_authorized",
    }

    split = document["mode_non_interchangeability"]
    assert split == {
        "active_must_require_worker_busy": True,
        "terminal_must_not_require_worker_busy": True,
        "active_receipt_cannot_authorize_terminal": True,
        "terminal_receipt_cannot_authorize_active": True,
        "effect_unknown_terminal_is": "UNKNOWN",
    }

    transport = document["transport"]
    assert transport["owner_process"] == "EXISTING_EXECUTIVE_SERVICE"
    assert transport["listener_kind"] == "DEDICATED_READ_ONLY_AF_UNIX"
    assert transport["allowed_peer_uid"] == 457
    assert transport["allowed_operations"] == ["resolve_dialogue_observation"]
    assert transport["general_control_socket_reuse"] is False
    assert transport["ceo_ingress_socket_reuse"] is False
    assert transport["direct_database_access_from_relay"] is False
    assert transport["request_is_enumeration_capable"] is False
    for key in ("runtime_writes", "agent_os_writes", "slack_writes", "wake_writes"):
        assert transport[key] is False
    assert transport["default_enabled"] is False

    discovery = document["relay_discovery"]
    assert discovery["source"] == "BOUNDED_VALIDATED_V2_PARENT_HISTORY"
    assert discovery["persistent_cursor"] is False
    assert discovery["parent_limit_required"] is True
    assert discovery["parent_deduplication_key"] == "PARENT_FINGERPRINT"
    assert discovery["unknown_parent_is_candidate"] is False
    assert discovery["conflicting_parent_is_candidate"] is False

    collection = document["candidate_collection"]
    assert collection["interface"] == "ASYNC_BOUNDED_IMMUTABLE_TUPLE"
    assert collection["synchronous_iterable_callback_allowed"] is False
    assert collection["worker_thread_allowed"] is False
    assert collection["timeout_required"] is True
    assert collection["maximum_cardinality_required"] is True
    assert collection["maximum_inflight_collections"] == 1
    assert collection["per_candidate_fault_isolation"] is True
    assert collection["af_unix_service_must_remain_available"] is True

    waiter = document["active_waiter"]
    assert waiter["owner"] == "EXISTING_AGENT_RELAY_PROCESS"
    assert waiter["storage"] == "EPHEMERAL_MEMORY_ONLY"
    assert waiter["register_at"] == "WAIT_FOR_REPLY_BEFORE_FIRST_POLL"
    assert waiter["remove_at"] == "WAIT_FOR_REPLY_FINALLY"
    assert set(waiter["key_fields"]) == {
        "parent_fingerprint",
        "operation_key",
        "session_ref",
        "target_seat",
    }
    assert waiter["source_ref_is_key"] is False
    assert waiter["provider_attention_inflight_is_equivalent"] is False
    assert waiter["missing_or_failed_lookup"] == "FAIL_CLOSED_BEFORE_WAKE_PERSISTENCE"

    failures = document["failure_states"]
    assert failures["RET2_EFFECT_UNKNOWN"] == "UNKNOWN_ZERO_EFFECT"
    assert failures["COLLECTION_TIMEOUT"] == "UNKNOWN_ZERO_EFFECT"
    assert failures["WAITER_LOOKUP_UNAVAILABLE"] == "HELD_ZERO_EFFECT"

    no_rebuild = set(document["no_rebuild"])
    assert {
        "NO_NEW_JOB_ATTEMPT_WORKER_EVENT_LIFECYCLE",
        "NO_SECOND_RUNTIME_BINDING_OWNER",
        "NO_SECOND_AGENT_RELAY_SERVICE",
        "NO_SECOND_WAKE_LEDGER",
        "NO_CURSOR_OR_INBOX_DATABASE",
        "NO_GENERIC_EXECUTIVE_READ_GATEWAY",
        "NO_PROVIDER_PROCESS_MANAGER",
        "NO_RETRY_OR_FAILOVER_PLANE",
    } <= no_rebuild

    predecessors = document["implementation_predecessors"]
    assert predecessors["ACTIVE_CURRENT_WORKER"] == [
        "R2_DIALOGUE_BINDING_AND_RUNTIME_RESOLVER_PROTECTED"
    ]
    assert predecessors["TERMINAL_RESULT"] == [
        "RET1_PROTECTED",
        "RET2_TERMINAL_PROJECTION_PROTECTED",
    ]


def test_normative_contract_is_closed_and_currently_authorizes_nothing() -> None:
    _validate(_contract())


def test_plan_freezes_owner_sequence_and_real_canary_boundary() -> None:
    text = PLAN.read_text(encoding="utf-8")
    for required in (
        "Gate A - R2 active binding source",
        "Gate B - RET1 and RET2",
        "Gate C - dedicated listener",
        "Gate D - Relay hot waiter",
        "Wave P1 - Executive active observation",
        "Wave P2 - Relay waiter and async discovery",
        "Wave RET2 - terminal RESULT projection",
        "Wave P3 - terminal observation extension",
        "Wave P4 - one-target canary",
        "No new lifecycle",
    ):
        assert required.lower() in text.lower()
    assert "opening the Executive SQLite database" not in text
    assert "No Ready" not in text


def test_false_support_mutations_are_detected() -> None:
    base = _contract()
    mutations = []

    authorized = copy.deepcopy(base)
    authorized["current_state"]["authorized_modes"] = ["ACTIVE_CURRENT_WORKER"]
    mutations.append(authorized)

    broad_socket = copy.deepcopy(base)
    broad_socket["transport"]["general_control_socket_reuse"] = True
    mutations.append(broad_socket)

    broad_peer = copy.deepcopy(base)
    broad_peer["transport"]["allowed_peer_uid"] = 501
    mutations.append(broad_peer)

    sync_source = copy.deepcopy(base)
    sync_source["candidate_collection"]["synchronous_iterable_callback_allowed"] = True
    mutations.append(sync_source)

    thread_source = copy.deepcopy(base)
    thread_source["candidate_collection"]["worker_thread_allowed"] = True
    mutations.append(thread_source)

    fake_waiter = copy.deepcopy(base)
    fake_waiter["active_waiter"]["provider_attention_inflight_is_equivalent"] = True
    mutations.append(fake_waiter)

    source_ref_waiter = copy.deepcopy(base)
    source_ref_waiter["active_waiter"]["source_ref_is_key"] = True
    mutations.append(source_ref_waiter)

    terminal_slack = copy.deepcopy(base)
    terminal_slack["modes"]["TERMINAL_RESULT"]["forbidden_substitutes"].remove(
        "SLACK_RESULT_TEXT_ALONE"
    )
    mutations.append(terminal_slack)

    effect_unknown = copy.deepcopy(base)
    effect_unknown["mode_non_interchangeability"]["effect_unknown_terminal_is"] = "RESOLVED"
    mutations.append(effect_unknown)

    for mutated in mutations:
        try:
            _validate(mutated)
        except AssertionError:
            continue
        raise AssertionError("false-support mutation survived source-law validation")
