from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-09-02-w3c-dialogue-observation-authority-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-02-w3c-dialogue-observation-authority.md"
ENROLLMENT = ROOT / "ops/executive_os/a2_agent_relay_enrollment.py"
RELAY_RUNTIME = ROOT / "integrations/slack_agent_dialogue/runtime.py"
START = "<!-- W3C-P0-CONTRACT:START -->"
END = "<!-- W3C-P0-CONTRACT:END -->"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contract() -> dict[str, Any]:
    text = _read(SPEC)
    assert text.count(START) == 1
    assert text.count(END) == 1
    body = text.split(START, 1)[1].split(END, 1)[0].strip()
    assert body.startswith("```json\n") and body.endswith("\n```")
    value = json.loads(body[len("```json\n") : -len("\n```")])
    assert isinstance(value, dict)
    return value


def _validate(document: dict[str, Any]) -> None:
    assert document["schema"] == "mastermind.w3c_dialogue_observation_authority.v1"
    assert document["operation"] == "w3c-p0-dialogue-observation-authority-20260902-sol-001"

    current = document["current_state"]
    assert current == {
        "capability": "SPEC_ONLY",
        "authorized_modes": [],
        "production_armed": False,
        "provider_effect": False,
        "runtime_effect": False,
    }

    modes = document["modes"]
    assert set(modes) == {"ACTIVE_CURRENT_WORKER", "TERMINAL_RESULT"}
    active = modes["ACTIVE_CURRENT_WORKER"]
    terminal = modes["TERMINAL_RESULT"]
    assert active["status"] == "HELD_PREDECESSOR_UNPROTECTED"
    assert active["authority_owner"] == "EXECUTIVE_RUNTIME_PLUS_PROTECTED_R2_DIALOGUE_BINDING"
    assert {
        "EXACT_PARENT_BINDING_RECEIPT",
        "CURRENT_ACTIVE_ATTEMPT",
        "CURRENT_BUSY_WORKER",
        "CURRENT_RUNTIME_BINDING",
        "EFFECTIVE_GRANT_AND_PROFILE_ATTESTATION",
    } <= set(active["required_facts"])
    assert {
        "WORKER_DIALOGUE_CALLER_REPLAY",
        "SLACK_AUTHOR_ID",
        "CALLER_SUPPLIED_JOB_ATTEMPT_WORKER",
    } <= set(active["forbidden_substitutes"])

    assert terminal["status"] == "HELD_R2_TERMINAL_PROJECTION_UNPROTECTED"
    assert terminal["authority_owner"] == "EXISTING_ORION_R2_TERMINAL_DIALOGUE_PROJECTION_RECEIPT"
    assert terminal["accepted_projection_effects"] == ["APPLIED"]
    assert {
        "RET1_TERMINAL_CANDIDATE",
        "R2_MESSAGE_IDENTITY",
        "R2_PROJECTION_EFFECT_KNOWN",
    } <= set(terminal["required_facts"])
    assert {
        "SLACK_RESULT_TEXT_ALONE",
        "EFFECT_UNKNOWN_PROJECTION",
        "PARALLEL_RET2_PROJECTION_CARRIER",
    } <= set(terminal["forbidden_substitutes"])

    request = document["request_contract"]
    assert request["schema"] == "mastermind.executive_dialogue_observation_request.v1"
    assert request["operation"] == "resolve_dialogue_observation"
    assert request["parent_is_untrusted_lookup_input"] is True
    assert request["exact_keys"] == ["schema", "request_id", "parent"]
    assert request["parent_required_identity"] == [
        "schema",
        "work_ref",
        "commission_ref",
        "session_ref",
        "operation_key",
        "watch_mode",
        "allowed_sol_user_ids",
        "created_at",
        "fingerprint",
    ]
    for forbidden in (
        "root_job_id",
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
    assert response["schema"] == "mastermind.executive_dialogue_observation_response.v1"
    assert set(response["states"]) == {"RESOLVED", "UNAVAILABLE", "UNKNOWN", "CONFLICT", "HELD"}
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
        "private_transcript",
        "local_path",
    ):
        assert secret in response["forbidden_response_fields"]
    assert set(response["always_false_authority_flags"]) == {
        "action_authoritative",
        "provider_action_authorized",
        "wake_write_authorized",
        "lifecycle_write_authorized",
    }

    assert document["mode_non_interchangeability"] == {
        "active_must_require_worker_busy": True,
        "terminal_must_not_require_worker_busy": True,
        "active_receipt_cannot_authorize_terminal": True,
        "terminal_receipt_cannot_authorize_active": True,
        "effect_unknown_terminal_is": "UNKNOWN",
    }

    transport = document["transport"]
    assert transport["owner_process"] == "EXISTING_EXECUTIVE_SERVICE"
    assert transport["owner_user"] == "_mastermind_exec"
    assert transport["owner_uid"] == 450
    assert transport["peer_user"] == "_mastermind_agent_relay"
    assert transport["allowed_peer_uid"] == 457
    assert transport["host_identity_source"] == [
        "ops/executive_os/a2_agent_relay_enrollment.py::EXEC_UID=450",
        "ops/executive_os/a2_agent_relay_enrollment.py::RELAY_UID=457",
        "ops/executive_os/a2_agent_relay_enrollment.py::_RELAY_GROUP_MEMBERS includes _mastermind_exec",
    ]
    assert transport["listener_kind"] == "DEDICATED_READ_ONLY_AF_UNIX"
    assert transport["socket_parent"] == "/var/run/mastermind-dialogue-observation"
    assert transport["listener_socket"] == (
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
    )
    assert transport["socket_parent_owner_uid"] == 450
    assert transport["socket_parent_group_gid"] == 457
    assert transport["socket_parent_mode"] == "0710"
    assert transport["socket_owner_uid"] == 450
    assert transport["socket_group_gid"] == 457
    assert transport["socket_mode"] == "0660"
    assert transport["peer_credentials_required"] is True
    assert transport["parent_symlink_forbidden"] is True
    assert transport["socket_symlink_forbidden"] is True
    assert transport["replacement_requires_owned_stale_inode"] is True
    assert transport["socket_cleanup_requires_identity_match"] is True
    assert transport["general_control_parent_reuse"] is False
    assert transport["allowed_operations"] == ["resolve_dialogue_observation"]
    assert transport["max_requests_per_connection"] == 1
    assert transport["general_control_socket_reuse"] is False
    assert transport["ceo_ingress_socket_reuse"] is False
    assert transport["direct_database_access_from_relay"] is False
    assert transport["request_is_enumeration_capable"] is False
    assert transport["unbound_response_is_uniform"] is True
    assert transport["default_enabled"] is False
    assert transport["enabled_bind_failure"] == "CAPABILITY_NOT_READY"
    assert transport["permission_or_inode_conflict"] == "CAPABILITY_NOT_READY"
    assert transport["bounded_request_bytes"] == 65536
    assert transport["bounded_response_bytes"] == 65536
    for key in ("runtime_writes", "agent_os_writes", "slack_writes", "wake_writes"):
        assert transport[key] is False

    discovery = document["relay_discovery"]
    assert discovery == {
        "source": "BOUNDED_VALIDATED_V2_PARENT_HISTORY",
        "persistent_cursor": False,
        "parent_limit_required": True,
        "parent_deduplication_key": "PARENT_FINGERPRINT",
        "executive_request_per_parent": True,
        "unknown_parent_is_candidate": False,
        "conflicting_parent_is_candidate": False,
    }

    collection = document["candidate_collection"]
    assert collection["interface"] == "ASYNC_BOUNDED_IMMUTABLE_TUPLE"
    assert collection["synchronous_iterable_callback_allowed"] is False
    assert collection["worker_thread_allowed"] is False
    assert collection["timeout_required"] is True
    assert collection["maximum_cardinality_required"] is True
    assert collection["maximum_inflight_collections"] == 1
    assert collection["unresolved_collection_behavior"] == (
        "NO_NEW_COLLECTION_ZERO_PROVIDER_EFFECT"
    )
    assert collection["per_candidate_fault_isolation"] is True
    assert collection["af_unix_service_must_remain_available"] is True

    waiter = document["active_waiter"]
    assert waiter["owner"] == "EXISTING_AGENT_RELAY_PROCESS"
    assert waiter["storage"] == "EPHEMERAL_MEMORY_ONLY"
    assert waiter["register_at"] == "WAIT_FOR_REPLY_BEFORE_FIRST_POLL"
    assert waiter["remove_at"] == "WAIT_FOR_REPLY_FINALLY"
    assert waiter["key_fields"] == [
        "parent_fingerprint",
        "operation_key",
        "session_ref",
        "target_seat",
    ]
    assert waiter["maximum_active_registration_per_key"] == 1
    assert waiter["duplicate_registration"] == "CONFLICT_ZERO_EFFECT"
    assert waiter["registration_identity"] == "OPAQUE_PROCESS_LOCAL_TOKEN"
    assert waiter["remove_requires"] == "KEY_PLUS_EXACT_REGISTRATION_TOKEN"
    assert waiter["stale_cleanup"] == "INERT"
    assert waiter["lookup_rule"] == "ACTIVE_ONLY_FOR_CURRENT_EXACT_REGISTRATION"
    assert waiter["source_ref_is_key"] is False
    assert waiter["provider_attention_inflight_is_equivalent"] is False
    assert waiter["missing_or_failed_lookup"] == "FAIL_CLOSED_BEFORE_WAKE_PERSISTENCE"
    assert waiter["restart_behavior"] == (
        "REGISTRY_EMPTY_AND_WAKE_IDEMPOTENCY_REMAINS_AUTHORITY"
    )

    failures = document["failure_states"]
    assert failures["R2_EFFECT_UNKNOWN"] == "UNKNOWN_ZERO_EFFECT"
    assert failures["LISTENER_PERMISSION_CONFLICT"] == "CAPABILITY_NOT_READY_ZERO_EFFECT"
    assert failures["LISTENER_INODE_CONFLICT"] == "CAPABILITY_NOT_READY_ZERO_EFFECT"
    assert failures["PEER_UID_REFUSED"] == "REFUSE_ZERO_EFFECT"
    assert failures["COLLECTION_TIMEOUT"] == "UNKNOWN_ZERO_EFFECT"
    assert failures["WAITER_LOOKUP_UNAVAILABLE"] == "HELD_ZERO_EFFECT"
    assert failures["WAITER_REGISTRATION_CONFLICT"] == "CONFLICT_ZERO_EFFECT"

    assert {
        "NO_NEW_JOB_ATTEMPT_WORKER_EVENT_LIFECYCLE",
        "NO_SECOND_RUNTIME_BINDING_OWNER",
        "NO_SECOND_AGENT_RELAY_SERVICE",
        "NO_SECOND_WAKE_LEDGER",
        "NO_CURSOR_OR_INBOX_DATABASE",
        "NO_GENERIC_EXECUTIVE_READ_GATEWAY",
        "NO_PROVIDER_PROCESS_MANAGER",
        "NO_RETRY_OR_FAILOVER_PLANE",
        "NO_SECOND_TERMINAL_PROJECTION_OPERATION",
    } <= set(document["no_rebuild"])

    predecessors = document["implementation_predecessors"]
    assert predecessors["ACTIVE_CURRENT_WORKER"] == [
        "R2_DIALOGUE_BINDING_AND_RUNTIME_RESOLVER_PROTECTED"
    ]
    assert predecessors["TERMINAL_RESULT"] == [
        "RET1_PROTECTED",
        "ORION_R2_TERMINAL_PROJECTION_PROTECTED",
    ]
    assert predecessors["RELAY_CONSUMER"] == [
        "EXECUTIVE_OBSERVATION_LISTENER_PROTECTED",
        "ACTIVE_WAITER_REGISTRY_PROTECTED",
    ]


def test_normative_contract_is_closed_and_currently_authorizes_nothing() -> None:
    _validate(_contract())


def test_host_identity_and_reverse_socket_direction_match_protected_source() -> None:
    enrollment = _read(ENROLLMENT)
    relay_runtime = _read(RELAY_RUNTIME)
    for required in (
        'RELAY_USER = "_mastermind_agent_relay"',
        "RELAY_UID = 457",
        "RELAY_GID = 457",
        'EXEC_USER = "_mastermind_exec"',
        "EXEC_UID = 450",
        "EXEC_GID = 450",
        "ALLOWED_PEER_UIDS = (EXEC_UID,)",
        "_RELAY_GROUP_MEMBERS = (EXEC_USER,)",
    ):
        assert required in enrollment
    assert "EXECUTIVE_CLIENT_UID = 450" in relay_runtime
    assert "allowed_peer_uids != (EXECUTIVE_CLIENT_UID,)" in relay_runtime
    transport = _contract()["transport"]
    assert transport["allowed_peer_uid"] == 457
    assert transport["owner_uid"] == 450
    assert transport["listener_socket"] != (
        "/var/run/mastermind-agent-relay/agent-relay.sock"
    )


def test_plan_freezes_owner_host_sequence_and_real_canary_boundary() -> None:
    text = _read(PLAN).lower()
    for required in (
        "gate a - r2 active binding source",
        "gate b - ret1 and existing orion r2 terminal projection",
        "gate c - dedicated listener and host reachability",
        "gate d - relay hot waiter",
        "parent/final symlinks",
        "foreign or ambiguous inode",
        "wave p1 - executive active observation",
        "wave p2 - relay waiter and async discovery",
        "opaque process-local registration token",
        "compare-and-delete",
        "stale cleanup",
        "cannot clear a newer waiter",
        "existing orion r2 - terminal result projection",
        "wave p3 - terminal observation extension",
        "wave p4 - one-target canary",
        "no new lifecycle",
    ):
        assert required in text
    assert "separate fresh operation" not in text


def test_false_support_mutations_are_detected() -> None:
    base = _contract()
    mutations: list[dict[str, Any]] = []

    def changed(path: tuple[str, ...], value: Any) -> dict[str, Any]:
        item = copy.deepcopy(base)
        cursor: Any = item
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        return item

    mutations.extend(
        [
            changed(("current_state", "authorized_modes"), ["ACTIVE_CURRENT_WORKER"]),
            changed(("transport", "general_control_socket_reuse"), True),
            changed(("transport", "general_control_parent_reuse"), True),
            changed(("transport", "allowed_peer_uid"), 450),
            changed(("transport", "owner_uid"), 501),
            changed(("transport", "socket_parent_mode"), "0777"),
            changed(("transport", "socket_mode"), "0666"),
            changed(("transport", "peer_credentials_required"), False),
            changed(("transport", "parent_symlink_forbidden"), False),
            changed(("transport", "replacement_requires_owned_stale_inode"), False),
            changed(("transport", "max_requests_per_connection"), 2),
            changed(("transport", "unbound_response_is_uniform"), False),
            changed(("candidate_collection", "synchronous_iterable_callback_allowed"), True),
            changed(("candidate_collection", "worker_thread_allowed"), True),
            changed(("active_waiter", "maximum_active_registration_per_key"), 2),
            changed(("active_waiter", "duplicate_registration"), "OVERWRITE"),
            changed(("active_waiter", "registration_identity"), "KEY_ONLY"),
            changed(("active_waiter", "remove_requires"), "KEY_ONLY"),
            changed(("active_waiter", "stale_cleanup"), "DELETE_CURRENT"),
            changed(("active_waiter", "lookup_rule"), "KEY_PRESENT"),
            changed(("active_waiter", "provider_attention_inflight_is_equivalent"), True),
            changed(("active_waiter", "source_ref_is_key"), True),
            changed(("failure_states", "WAITER_REGISTRATION_CONFLICT"), "OVERWRITE_ALLOWED"),
            changed(("mode_non_interchangeability", "effect_unknown_terminal_is"), "RESOLVED"),
        ]
    )

    terminal_slack = copy.deepcopy(base)
    terminal_slack["modes"]["TERMINAL_RESULT"]["forbidden_substitutes"].remove(
        "SLACK_RESULT_TEXT_ALONE"
    )
    mutations.append(terminal_slack)

    invented_recovered = copy.deepcopy(base)
    invented_recovered["modes"]["TERMINAL_RESULT"]["accepted_projection_effects"] = [
        "APPLIED",
        "RECOVERED",
    ]
    mutations.append(invented_recovered)

    parallel_projection = copy.deepcopy(base)
    parallel_projection["no_rebuild"].remove("NO_SECOND_TERMINAL_PROJECTION_OPERATION")
    mutations.append(parallel_projection)

    survivors = []
    for index, mutated in enumerate(mutations):
        try:
            _validate(mutated)
        except AssertionError:
            continue
        survivors.append(index)
    assert survivors == [], survivors
