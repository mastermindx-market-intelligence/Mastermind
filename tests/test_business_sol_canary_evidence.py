"""RED-first hostile-case tests for the H1 one-cockpit receipt validator.

``integrations/business_sol_canary/evidence.py`` is a pure, dependency-free
(stdlib only) validator for the frozen contract
``mastermind.business_sol_one_cockpit_receipt.v1``. It performs no
Business/Executive/OAuth/RuntimeBinding/Slack/Linear/Agent-OS/deployment
action of any kind, and it never reads the process clock, environment,
filesystem (beyond its own source), network, or a random source — every
notion of "now" comes from the caller-supplied ``evaluated_at``.

Every hostile case below was written to fail against an incomplete/absent
implementation (RED) and is expected to pass once the corresponding
enforcement rule exists in ``evidence.py`` (GREEN). See
``test_business_sol_canary_evidence_mutation.py`` for the paired mutation
kill matrix that proves each rule is actually load-bearing.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import re
from pathlib import Path
from typing import Any

import pytest

from integrations.business_sol_canary import evidence as ev

EVALUATED_AT = "2026-09-02T00:05:00Z"

# ---------------------------------------------------------------------------
# Golden packet — a fully compliant instance of the frozen input contract.
# ---------------------------------------------------------------------------

_INVENTORY = [
    {"name": "executive_mcp", "kind": "app"},
    {"name": "control_room_widget", "kind": "plugin"},
    {"name": "steward_tools", "kind": "tool"},
]
_INVENTORY_DIGEST = hashlib.sha256(
    ev.canonical_json(sorted(_INVENTORY, key=lambda entry: (entry["name"], entry["kind"])))
).hexdigest()


def _control_room_state(observed_at: str) -> dict[str, Any]:
    return {
        "observed_at": observed_at,
        "structured_present": True,
        "text_fallback_present": True,
        "ui_only": False,
    }


def golden_packet() -> dict[str, Any]:
    """A deep-copyable, fully compliant packet. Callers mutate a copy."""

    return {
        "schema_id": ev.INPUT_SCHEMA_ID,
        "receipt_id": "receipt-0001",
        "generation_id": "gen-0001",
        "observed_at": "2026-09-02T00:00:00Z",
        "is_correction": False,
        "correction": None,
        "source_refs": [
            {"ref_id": "src-s1", "owner": "s1"},
            {"ref_id": "src-exec", "owner": "executive_app"},
            {"ref_id": "src-cr", "owner": "control_room"},
            {"ref_id": "src-h1", "owner": "h1"},
        ],
        "cockpit_selection": {
            "selected_ref": "cockpit-opaque-A",
            "control_refs": ["cockpit-opaque-B", "cockpit-opaque-C"],
            "selection_basis": "opaque",
        },
        "personal_cockpit": {
            "separately_selectable": True,
            "merged_into_business": False,
        },
        "business_membership_transition": {
            "initial_state": "personal",
            "initial_observed_at": "2026-09-01T23:00:00Z",
            "transitioned_state": "business",
            "transitioned_observed_at": "2026-09-01T23:05:00Z",
            "reverted_state": "personal",
            "reverted_observed_at": "2026-09-01T23:10:00Z",
            "readback_state": "personal",
            "readback_observed_at": "2026-09-01T23:11:00Z",
        },
        "protected_baseline": {
            "p1_commit": ev.EXPECTED_P1_COMMIT,
            "package_inventory": copy.deepcopy(_INVENTORY),
            "package_inventory_digest": _INVENTORY_DIGEST,
            "expected_package_inventory": copy.deepcopy(_INVENTORY),
            "expected_package_inventory_digest": _INVENTORY_DIGEST,
        },
        "generation_identities": {
            "s1": {"expected_id": "s1-gen-1", "observed_id": "s1-gen-1", "source_ref_id": "src-s1"},
            "executive_app": {
                "expected_id": "exec-gen-1",
                "observed_id": "exec-gen-1",
                "source_ref_id": "src-exec",
            },
            "control_room": {
                "expected_id": "cr-gen-1",
                "observed_id": "cr-gen-1",
                "source_ref_id": "src-cr",
            },
            "h1": {"expected_id": "h1-gen-1", "observed_id": "h1-gen-1", "source_ref_id": "src-h1"},
        },
        "steward_census": {
            "tool_names": ["t1", "t2", "t3", "t4", "t5", "t6"],
            "initial_read": {
                "observed_at": "2026-09-01T22:00:00Z",
                "authenticated": True,
                "token_material_present": False,
            },
            "post_expiry_read": {
                "observed_at": "2026-09-01T22:30:00Z",
                "authenticated": True,
                "expired_token_used": True,
                "refresh_material_present": False,
            },
        },
        "control_room_evidence": {
            "desktop": {
                state: _control_room_state("2026-09-01T23:20:00Z")
                for state in ev._ALLOWED_CONTROL_ROOM_STATES
            },
            "mobile": {
                state: _control_room_state("2026-09-01T23:21:00Z")
                for state in ev._ALLOWED_CONTROL_ROOM_STATES
            },
        },
        "executive_admission": {
            "operation_key": "op-0001",
            "intent_id": "intent-0001",
            "job_id": "job-0001",
            "status": "QUEUED",
            "dispatched": False,
            "attempts": 0,
            "latest_attempt": None,
            "attempt_limit": 1,
            "authorities": ["READ", "RESEARCH"],
            "write_paths": [],
            "validation_commands": [],
            "worker_effects": [],
            "wake_effect": False,
            "runtime_binding_effect": False,
            "slack_effect": False,
            "linear_effect": False,
            "agent_os_effect": False,
            "submission_count": 1,
            "conflict_on_changed_payload": {"detected": False, "reported": False},
            "status_readback": {"job_id": "job-0001", "status": "QUEUED"},
        },
        "rollback": {
            "performed": True,
            "post_rollback_workspace_state": "clean",
            "post_rollback_plugin_state": "uninstalled",
            "post_rollback_app_state": "disconnected",
            "readback_confirmed": True,
        },
        "evidence_source_provenance": "live_receipt",
    }


def _issue_codes(result: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def _validate(packet: dict[str, Any]) -> dict[str, Any]:
    return ev.validate_receipt(packet, evaluated_at=EVALUATED_AT)


# ---------------------------------------------------------------------------
# Baseline: the golden packet is a clean PASS.
# ---------------------------------------------------------------------------


def test_golden_packet_passes_with_no_issues() -> None:
    result = _validate(golden_packet())
    assert result["verdict"] == "PASS"
    assert result["issues"] == []
    assert result["schema_id"] == ev.OUTPUT_SCHEMA_ID
    assert result["production_acceptance_granted"] is False


def test_output_schema_shape() -> None:
    result = _validate(golden_packet())
    assert set(result) == {
        "schema_id",
        "verdict",
        "issues",
        "canonical_input_digest",
        "validated_identities",
        "capability_state_projection",
        "production_acceptance_granted",
    }
    assert result["verdict"] in ev.VERDICTS
    assert re.fullmatch(r"[0-9a-f]{64}", result["canonical_input_digest"])


# ---------------------------------------------------------------------------
# Determinism / canonicalization / permutation independence
# ---------------------------------------------------------------------------


def test_canonical_digest_is_pure_and_repeatable() -> None:
    packet = golden_packet()
    first = ev.canonical_input_digest(packet)
    second = ev.canonical_input_digest(copy.deepcopy(packet))
    assert first == second


def test_validation_is_order_independent_for_object_keys() -> None:
    packet = golden_packet()
    reordered = dict(reversed(list(packet.items())))
    a = _validate(packet)
    b = _validate(reordered)
    assert a["verdict"] == b["verdict"] == "PASS"
    assert a["canonical_input_digest"] == b["canonical_input_digest"]


def test_validation_is_order_independent_for_set_like_arrays() -> None:
    packet = golden_packet()
    permuted = golden_packet()
    permuted["cockpit_selection"]["control_refs"] = list(
        reversed(permuted["cockpit_selection"]["control_refs"])
    )
    permuted["source_refs"] = list(reversed(permuted["source_refs"]))
    permuted["steward_census"]["tool_names"] = list(reversed(permuted["steward_census"]["tool_names"]))
    permuted["executive_admission"]["authorities"] = list(
        reversed(permuted["executive_admission"]["authorities"])
    )
    permuted["protected_baseline"]["package_inventory"] = list(
        reversed(permuted["protected_baseline"]["package_inventory"])
    )
    permuted["protected_baseline"]["expected_package_inventory"] = list(
        reversed(permuted["protected_baseline"]["expected_package_inventory"])
    )

    a = _validate(packet)
    b = _validate(permuted)
    assert a["verdict"] == b["verdict"] == "PASS"
    assert a["canonical_input_digest"] == b["canonical_input_digest"]


def test_a_real_duplicate_survives_set_normalization() -> None:
    """Permutation tolerance must not blind duplicate detection."""

    packet = golden_packet()
    packet["cockpit_selection"]["control_refs"] = ["same-ref", "same-ref"]
    result = _validate(packet)
    assert "COCKPIT_CONTROLS_DUPLICATED" in _issue_codes(result)


# ---------------------------------------------------------------------------
# Mandatory hostile cases
# ---------------------------------------------------------------------------


def test_selected_cockpit_duplicated_among_controls() -> None:
    packet = golden_packet()
    packet["cockpit_selection"]["selected_ref"] = packet["cockpit_selection"]["control_refs"][0]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "COCKPIT_SELECTED_IN_CONTROLS" in _issue_codes(result)


def test_control_cockpits_duplicated() -> None:
    packet = golden_packet()
    packet["cockpit_selection"]["control_refs"] = ["dup-ref", "dup-ref"]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "COCKPIT_CONTROLS_DUPLICATED" in _issue_codes(result)


@pytest.mark.parametrize("basis", ["account", "title", "recency"])
def test_cockpit_selection_basis_must_be_opaque(basis: str) -> None:
    packet = golden_packet()
    packet["cockpit_selection"]["selection_basis"] = basis
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "COCKPIT_SELECTION_BASIS_INVALID" in _issue_codes(result)


def test_personal_merged_into_business_is_forbidden() -> None:
    packet = golden_packet()
    packet["personal_cockpit"]["merged_into_business"] = True
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "PERSONAL_MERGED_INTO_BUSINESS" in _issue_codes(result)


def test_personal_not_separately_selectable_is_forbidden() -> None:
    packet = golden_packet()
    packet["personal_cockpit"]["separately_selectable"] = False
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "PERSONAL_NOT_SEPARATELY_SELECTABLE" in _issue_codes(result)


def test_missing_personal_business_personal_reversibility() -> None:
    packet = golden_packet()
    packet["business_membership_transition"]["reverted_state"] = "business"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "PERSONAL_REVERSIBILITY_INCOMPLETE" in _issue_codes(result)


def test_membership_transition_must_actually_change_state() -> None:
    packet = golden_packet()
    packet["business_membership_transition"]["transitioned_state"] = "personal"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "MEMBERSHIP_TRANSITION_NOT_APPLIED" in _issue_codes(result)


def test_wrong_p1_commit() -> None:
    packet = golden_packet()
    packet["protected_baseline"]["p1_commit"] = "0" * 40
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "P1_COMMIT_MISMATCH" in _issue_codes(result)


def test_package_inventory_drift() -> None:
    packet = golden_packet()
    packet["protected_baseline"]["expected_package_inventory_digest"] = "0" * 64
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "PACKAGE_INVENTORY_DRIFT" in _issue_codes(result)


def test_extra_app_or_plugin_present() -> None:
    packet = golden_packet()
    entries = packet["protected_baseline"]["package_inventory"] + [
        {"name": "rogue_plugin", "kind": "plugin"}
    ]
    packet["protected_baseline"]["package_inventory"] = entries
    packet["protected_baseline"]["package_inventory_digest"] = hashlib.sha256(
        ev.canonical_json(sorted(entries, key=lambda entry: (entry["name"], entry["kind"])))
    ).hexdigest()
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXTRA_COMPONENT_PRESENT" in _issue_codes(result)


def test_schema_mismatch() -> None:
    packet = golden_packet()
    packet["schema_id"] = "mastermind.some_other_receipt.v1"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "SCHEMA_IDENTITY_MISMATCH" in _issue_codes(result)


@pytest.mark.parametrize("component", list(ev._ALLOWED_GENERATION_COMPONENTS))
def test_generation_identity_mismatch_per_component(component: str) -> None:
    packet = golden_packet()
    packet["generation_identities"][component]["observed_id"] = "drifted-generation-id"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "GENERATION_IDENTITY_MISMATCH" in _issue_codes(result)


def test_only_one_steward_read() -> None:
    packet = golden_packet()
    packet["steward_census"]["post_expiry_read"] = None
    result = _validate(packet)
    assert result["verdict"] == "UNKNOWN"
    assert "STEWARD_POST_EXPIRY_READ_MISSING" in _issue_codes(result)


def test_post_expiry_read_not_after_expiry() -> None:
    packet = golden_packet()
    packet["steward_census"]["post_expiry_read"]["expired_token_used"] = False
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "STEWARD_POST_EXPIRY_NOT_AFTER_EXPIRY" in _issue_codes(result)


def test_post_expiry_read_must_be_strictly_after_initial_read() -> None:
    packet = golden_packet()
    packet["steward_census"]["post_expiry_read"]["observed_at"] = "2026-09-01T21:00:00Z"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_ORDER_INVERSION" in _issue_codes(result)


def test_refresh_material_leakage_is_refused() -> None:
    packet = golden_packet()
    packet["steward_census"]["post_expiry_read"]["refresh_material_present"] = True
    result = _validate(packet)
    assert result["verdict"] == "REFUSED"
    assert "SECRET_REFRESH_MATERIAL" in _issue_codes(result)


def test_initial_read_token_material_flag_is_refused() -> None:
    packet = golden_packet()
    packet["steward_census"]["initial_read"]["token_material_present"] = True
    result = _validate(packet)
    assert result["verdict"] == "REFUSED"
    assert "SECRET_TOKEN_MATERIAL" in _issue_codes(result)


@pytest.mark.parametrize("surface", ["desktop", "mobile"])
@pytest.mark.parametrize("state", list(ev._ALLOWED_CONTROL_ROOM_STATES))
def test_missing_adverse_control_room_state(surface: str, state: str) -> None:
    packet = golden_packet()
    del packet["control_room_evidence"][surface][state]
    result = _validate(packet)
    assert result["verdict"] == "UNKNOWN"
    assert "CONTROL_ROOM_STATE_MISSING" in _issue_codes(result)


def test_ui_only_control_room_evidence_without_fallback() -> None:
    packet = golden_packet()
    state = packet["control_room_evidence"]["desktop"]["normal"]
    state["ui_only"] = True
    state["structured_present"] = False
    state["text_fallback_present"] = False
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "CONTROL_ROOM_EVIDENCE_UI_ONLY" in _issue_codes(result)


def test_executive_status_not_queued() -> None:
    packet = golden_packet()
    packet["executive_admission"]["status"] = "RUNNING"
    packet["executive_admission"]["status_readback"]["status"] = "RUNNING"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_STATUS_NOT_QUEUED" in _issue_codes(result)


def test_executive_dispatched_true() -> None:
    packet = golden_packet()
    packet["executive_admission"]["dispatched"] = True
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_DISPATCHED_TRUE" in _issue_codes(result)


def test_executive_attempt_or_worker_effect_present() -> None:
    packet = golden_packet()
    packet["executive_admission"]["worker_effects"] = ["worker-claimed-job-0001"]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_WORKER_EFFECT_PRESENT" in _issue_codes(result)


def test_executive_attempts_nonzero() -> None:
    packet = golden_packet()
    packet["executive_admission"]["attempts"] = 1
    packet["executive_admission"]["latest_attempt"] = {"worker": "w1"}
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_ATTEMPTS_NONZERO" in _issue_codes(result)


def test_latest_attempt_present_despite_zero_attempts() -> None:
    packet = golden_packet()
    packet["executive_admission"]["latest_attempt"] = {"worker": "w1"}
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_WORKER_EFFECT_PRESENT" in _issue_codes(result)


@pytest.mark.parametrize(
    "authorities",
    [["READ"], ["READ", "RESEARCH", "WRITE_BRANCH"], ["RUN_TESTS"], []],
)
def test_executive_authorities_must_be_exactly_read_and_research(authorities: list[str]) -> None:
    packet = golden_packet()
    packet["executive_admission"]["authorities"] = authorities
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_AUTHORITIES_INVALID" in _issue_codes(result)


def test_executive_write_path_present() -> None:
    packet = golden_packet()
    packet["executive_admission"]["write_paths"] = ["app/some_module.py"]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_WRITE_PATH_PRESENT" in _issue_codes(result)


def test_executive_validation_command_present() -> None:
    packet = golden_packet()
    packet["executive_admission"]["validation_commands"] = ["pytest -q"]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_VALIDATION_COMMAND_PRESENT" in _issue_codes(result)


def test_executive_duplicate_submission() -> None:
    packet = golden_packet()
    packet["executive_admission"]["submission_count"] = 2
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_DUPLICATE_SUBMISSION" in _issue_codes(result)


def test_executive_changed_payload_conflict_omitted() -> None:
    packet = golden_packet()
    packet["executive_admission"]["conflict_on_changed_payload"] = {
        "detected": True,
        "reported": False,
    }
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_CONFLICT_OMITTED" in _issue_codes(result)


def test_executive_status_readback_mismatch() -> None:
    packet = golden_packet()
    packet["executive_admission"]["status_readback"]["status"] = "RUNNING"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "EXECUTIVE_STATUS_READBACK_MISMATCH" in _issue_codes(result)


@pytest.mark.parametrize(
    "field",
    ["wake_effect", "runtime_binding_effect", "slack_effect", "linear_effect", "agent_os_effect"],
)
def test_executive_side_effects_forbidden(field: str) -> None:
    packet = golden_packet()
    packet["executive_admission"][field] = True
    result = _validate(packet)
    assert result["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "provenance", ["ci_green", "merge_event", "slack_delivery", "queued_fixture_job", "prose_claim"]
)
def test_evidence_source_substitution_is_refused(provenance: str) -> None:
    packet = golden_packet()
    packet["evidence_source_provenance"] = provenance
    result = _validate(packet)
    assert result["verdict"] == "REFUSED"
    assert "EVIDENCE_SOURCE_NOT_LIVE_RECEIPT" in _issue_codes(result)


def test_missing_rollback_section() -> None:
    packet = golden_packet()
    del packet["rollback"]
    result = _validate(packet)
    assert result["verdict"] == "UNKNOWN"
    assert "ROLLBACK_MISSING" in _issue_codes(result)


def test_rollback_not_performed() -> None:
    packet = golden_packet()
    packet["rollback"]["performed"] = False
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "ROLLBACK_NOT_PERFORMED" in _issue_codes(result)


def test_rollback_readback_missing() -> None:
    packet = golden_packet()
    packet["rollback"]["readback_confirmed"] = False
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "ROLLBACK_READBACK_MISSING" in _issue_codes(result)


def test_stale_timestamp() -> None:
    packet = golden_packet()
    packet["observed_at"] = "2026-08-01T00:00:00Z"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_STALE" in _issue_codes(result)


def test_future_timestamp_beyond_skew() -> None:
    packet = golden_packet()
    packet["observed_at"] = "2026-09-05T00:00:00Z"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_FUTURE" in _issue_codes(result)


@pytest.mark.parametrize(
    "malformed",
    [
        "2026-02-30T00:00:00Z",  # impossible calendar date
        "2026-09-02T00:00:00+05:00",  # not UTC
        "not-a-timestamp",
        "2026-09-02 00:00:00",  # missing offset entirely
    ],
)
def test_impossible_or_non_utc_timestamps(malformed: str) -> None:
    packet = golden_packet()
    packet["observed_at"] = malformed
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_MALFORMED" in _issue_codes(result)


def test_contradictory_clock_sub_evidence_after_receipt_assembly() -> None:
    packet = golden_packet()
    packet["steward_census"]["initial_read"]["observed_at"] = "2026-09-03T00:00:00Z"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_CONTRADICTORY_CLOCK" in _issue_codes(result)


def test_event_order_inversion_in_membership_transition() -> None:
    packet = golden_packet()
    packet["business_membership_transition"]["transitioned_observed_at"] = "2026-09-01T22:00:00Z"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_ORDER_INVERSION" in _issue_codes(result)


def test_source_owner_mismatch() -> None:
    packet = golden_packet()
    packet["source_refs"][0] = {"ref_id": "src-s1", "owner": "control_room"}
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "SOURCE_OWNER_MISMATCH" in _issue_codes(result)


def test_dangling_source_ref() -> None:
    packet = golden_packet()
    packet["generation_identities"]["s1"]["source_ref_id"] = "no-such-ref"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "DANGLING_SOURCE_REF" in _issue_codes(result)


def test_duplicate_field_identity_in_source_refs() -> None:
    packet = golden_packet()
    packet["source_refs"].append({"ref_id": "src-s1", "owner": "executive_app"})
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "DUPLICATE_FIELD_IDENTITY" in _issue_codes(result)


def test_duplicate_field_identity_in_executive_admission() -> None:
    packet = golden_packet()
    packet["executive_admission"]["intent_id"] = packet["executive_admission"]["operation_key"]
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "DUPLICATE_FIELD_IDENTITY" in _issue_codes(result)


# ---------------------------------------------------------------------------
# Secret / private-locator / error leakage screening (REFUSED, never echoed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda p: p["source_refs"][0].__setitem__("ref_id", "user@example.com"), "SECRET_EMAIL_ADDRESS"),
        (
            lambda p: p["source_refs"][0].__setitem__(
                "ref_id", "bearer sk-ant-abcdefghijklmnopqrstuvwx"
            ),
            "SECRET_TOKEN_MATERIAL",
        ),
        (
            lambda p: p.__setitem__(
                "generation_id", "sess_abcdefghijklmnop"
            ),
            "SECRET_SESSION_IDENTIFIER",
        ),
        (
            lambda p: p.__setitem__("receipt_id", "/Users/operator/secret/receipt.json"),
            "SECRET_LOCAL_PATH",
        ),
        (
            lambda p: p.__setitem__("generation_id", "chrome profile 3"),
            "SECRET_BROWSER_PROFILE",
        ),
        (
            lambda p: p.__setitem__("receipt_id", "C0123456789"),
            "SECRET_SLACK_COORDINATE",
        ),
        (
            lambda p: p.__setitem__(
                "receipt_id", "I hereby authorize this Business membership change"
            ),
            "SECRET_MODEL_AUTHORITY_CLAIM",
        ),
        (
            lambda p: p.__setitem__(
                "receipt_id", "Traceback (most recent call last): boom"
            ),
            "SECRET_ERROR_LEAKAGE",
        ),
        (
            lambda p: p.__setitem__("receipt_id", "4111 1111 1111 1111"),
            "SECRET_ACCOUNT_NUMBER",
        ),
    ],
)
def test_secret_and_private_locator_screening_is_refused(mutate, code: str) -> None:
    packet = golden_packet()
    mutate(packet)
    result = _validate(packet)
    assert result["verdict"] == "REFUSED"
    assert code in _issue_codes(result)
    # The offending value itself must never be echoed back in an issue.
    for issue in result["issues"]:
        assert "sk-ant-" not in issue["detail"]
        assert "user@example.com" not in issue["detail"]
        assert "4111 1111 1111 1111" not in issue["detail"]


# ---------------------------------------------------------------------------
# Correction lineage
# ---------------------------------------------------------------------------


def test_correction_packet_without_lineage_fails() -> None:
    packet = golden_packet()
    packet["is_correction"] = True
    packet["correction"] = None
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "CORRECTION_LINEAGE_MISSING" in _issue_codes(result)


def test_correction_lineage_must_be_a_sha256_digest() -> None:
    packet = golden_packet()
    packet["is_correction"] = True
    packet["correction"] = {"supersedes_digest": "not-a-digest"}
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "CORRECTION_LINEAGE_INVALID" in _issue_codes(result)


def test_unexpected_correction_lineage_when_not_a_correction() -> None:
    packet = golden_packet()
    packet["correction"] = {"supersedes_digest": "a" * 64}
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "CORRECTION_LINEAGE_UNEXPECTED" in _issue_codes(result)


def test_valid_correction_lineage_passes() -> None:
    packet = golden_packet()
    packet["is_correction"] = True
    packet["correction"] = {"supersedes_digest": "a" * 64}
    result = _validate(packet)
    assert result["verdict"] == "PASS"


def test_correction_never_borrows_fields_from_a_superseded_packet() -> None:
    """A correction validates from scratch — dropping a required field must
    still fail even though the packet claims to correct a (hypothetical)
    prior, complete packet."""

    packet = golden_packet()
    packet["is_correction"] = True
    packet["correction"] = {"supersedes_digest": "a" * 64}
    del packet["rollback"]
    result = _validate(packet)
    assert result["verdict"] == "UNKNOWN"
    assert "ROLLBACK_MISSING" in _issue_codes(result)


# ---------------------------------------------------------------------------
# Closed contract / structural discipline
# ---------------------------------------------------------------------------


def test_unrecognized_top_level_field_is_rejected() -> None:
    packet = golden_packet()
    packet["unexpected_field"] = "not part of the contract"
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "UNRECOGNIZED_FIELD" in _issue_codes(result)


def test_unrecognized_nested_field_is_rejected() -> None:
    packet = golden_packet()
    packet["executive_admission"]["unexpected_nested_field"] = True
    result = _validate(packet)
    assert result["verdict"] == "FAIL"
    assert "UNRECOGNIZED_FIELD" in _issue_codes(result)


def test_missing_required_section_is_unknown_not_pass() -> None:
    packet = golden_packet()
    del packet["executive_admission"]
    result = _validate(packet)
    assert result["verdict"] == "UNKNOWN"
    assert result["verdict"] != "PASS"


def test_non_mapping_input_is_refused() -> None:
    result = ev.validate_receipt(["not", "a", "mapping"], evaluated_at=EVALUATED_AT)
    assert result["verdict"] == "REFUSED"
    assert "INPUT_NOT_MAPPING" in _issue_codes(result)


def test_verdict_precedence_refused_over_fail() -> None:
    packet = golden_packet()
    packet["executive_admission"]["dispatched"] = True  # FAIL
    packet["receipt_id"] = "user@example.com"  # REFUSED
    result = _validate(packet)
    assert result["verdict"] == "REFUSED"
    codes = _issue_codes(result)
    assert "EXECUTIVE_DISPATCHED_TRUE" in codes
    assert "SECRET_EMAIL_ADDRESS" in codes


def test_issues_are_completely_sorted() -> None:
    packet = golden_packet()
    packet["executive_admission"]["dispatched"] = True
    packet["executive_admission"]["attempts"] = 1
    packet["executive_admission"]["latest_attempt"] = {"worker": "w1"}
    result = _validate(packet)
    pairs = [(issue["severity"], issue["code"], issue["path"]) for issue in result["issues"]]
    assert pairs == sorted(pairs)


# ---------------------------------------------------------------------------
# Purity guard: no now()/random/network/fs-discovery/env in the module.
#
# This walks the actual AST (not raw text) so prose in docstrings/comments
# describing what the module does NOT do (e.g. "never calls datetime.now()")
# can never masquerade as, or be mistaken for, a violation.
# ---------------------------------------------------------------------------

_ALLOWED_IMPORT_MODULES = frozenset(
    {
        "__future__",
        "dataclasses",
        "hashlib",
        "json",
        "re",
        "collections.abc",
        "datetime",
        "typing",
    }
)

_FORBIDDEN_CALL_NAMES = frozenset({"open", "eval", "exec", "input", "compile"})
_FORBIDDEN_ATTRIBUTE_CALLS = frozenset(
    {
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("date", "today"),
        ("time", "time"),
        ("os", "getenv"),
        ("random", "random"),
        ("random", "choice"),
        ("random", "randint"),
        ("uuid", "uuid4"),
    }
)
_FORBIDDEN_MODULE_ROOTS = frozenset(
    {"os", "sys", "random", "time", "socket", "subprocess", "requests", "urllib", "uuid", "shutil", "glob"}
)


def _source_ast() -> ast.Module:
    source = Path(ev.__file__).read_text(encoding="utf-8")
    return ast.parse(source, filename=ev.__file__)


def test_evidence_module_only_imports_the_allowed_stdlib_surface() -> None:
    tree = _source_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _FORBIDDEN_MODULE_ROOTS, f"forbidden import: {alias.name}"
                assert alias.name in _ALLOWED_IMPORT_MODULES, f"unexpected import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            assert root not in _FORBIDDEN_MODULE_ROOTS, f"forbidden import: {module}"
            assert module in _ALLOWED_IMPORT_MODULES, f"unexpected import: {module}"


def test_evidence_module_never_calls_a_current_clock_random_or_io_primitive() -> None:
    tree = _source_ast()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            assert func.id not in _FORBIDDEN_CALL_NAMES, f"forbidden call: {func.id}("
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            pair = (func.value.id, func.attr)
            assert pair not in _FORBIDDEN_ATTRIBUTE_CALLS, f"forbidden call: {pair[0]}.{pair[1]}("


def test_evidence_module_never_reads_os_environ() -> None:
    tree = _source_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                raise AssertionError("forbidden environment read: os.environ")


def test_validate_receipt_never_mutates_its_input() -> None:
    packet = golden_packet()
    before = copy.deepcopy(packet)
    ev.validate_receipt(packet, evaluated_at=EVALUATED_AT)
    assert packet == before


# ---------------------------------------------------------------------------
# Step 6 — a SANITIZED shape of the Executive MCP #64 canary receipt as a
# deliberately INCOMPLETE / non-production packet. #64 is SAMPLE evidence
# only (authority precedence #5) and never live-production proof; this
# fixture is a synthetic reconstruction of that receipt's *shape*, not a
# verbatim reproduction, and it must not, on its own, yield a full PASS.
# ---------------------------------------------------------------------------


def sanitized_incomplete_exec_mcp_64_sample() -> dict[str, Any]:
    packet = golden_packet()
    # A #64-shaped sample only ever demonstrated ONE Steward read and never
    # captured the post-expiry/refresh read this contract requires.
    packet["steward_census"]["post_expiry_read"] = None
    # It also never captured the adverse Control Room states — only the
    # normal desktop path was screenshotted.
    packet["control_room_evidence"]["desktop"] = {
        "normal": _control_room_state("2026-09-01T23:20:00Z")
    }
    del packet["control_room_evidence"]["mobile"]
    # And it never demonstrated the rollback + post-rollback readback.
    del packet["rollback"]
    return packet


def test_sanitized_exec_mcp_64_sample_does_not_pass_on_its_own() -> None:
    result = _validate(sanitized_incomplete_exec_mcp_64_sample())
    assert result["verdict"] in {"UNKNOWN", "FAIL"}
    assert result["verdict"] != "PASS"
    codes = _issue_codes(result)
    assert "STEWARD_POST_EXPIRY_READ_MISSING" in codes
    assert "CONTROL_ROOM_STATE_MISSING" in codes
    assert "ROLLBACK_MISSING" in codes
    assert result["production_acceptance_granted"] is False
