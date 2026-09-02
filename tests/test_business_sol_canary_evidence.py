"""RED-first contract tests for the deterministic Business Sol H1 validator."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json

import pytest


MODULE = "integrations.business_sol_canary.evidence"
EVALUATED_AT = "2026-09-02T04:00:00Z"
P1_COMMIT = "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"
TOOLS = [
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
]
ADVERSE_STATES = [
    "NORMAL",
    "STALE",
    "DEGRADED",
    "PARTIAL_CLOSEOUT",
    "EFFECT_UNKNOWN",
    "NO_ACTION",
]


def _module():
    try:
        spec = importlib.util.find_spec(MODULE)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "Business Sol H1 validator is not implemented"
    return importlib.import_module(MODULE)


def _source(owner: str, ref: str, observed_at: str = "2026-09-02T03:58:00Z"):
    return {
        "owner": owner,
        "ref": ref,
        "observed_at": observed_at,
        "freshness": "FRESH",
    }


def _state_rows(prefix: str):
    return [
        {
            "state": state,
            "evidence_digest": hashlib.sha256(
                f"{prefix}:{state}".encode("utf-8")
            ).hexdigest(),
            "structured_text_equivalent": True,
        }
        for state in ADVERSE_STATES
    ]


def valid_receipt() -> dict:
    return {
        "schema": "mastermind.business_sol_one_cockpit_receipt.v1",
        "receipt_id": "receipt:business-canary-001",
        "generation": 1,
        "observed_at": "2026-09-02T03:59:50Z",
        "source_refs": [
            _source("github", f"commit:{P1_COMMIT}"),
            _source("business_workspace", "workspace-readback:canary-001"),
            _source("chatgpt", "app-readback:canary-001"),
            _source("executive_os", "executive-job:JOB-001"),
            _source("control_room", "control-room:canary-001"),
        ],
        "selected_cockpit_ref": "cockpit:business-canary",
        "control_cockpit_refs": [
            "cockpit:pro-control-1",
            "cockpit:pro-control-2",
        ],
        "cockpit_selection": {
            "method": "EXPLICIT_CANARY_ASSIGNMENT",
            "assignment_ref": "selection:chairman-canary-001",
            "account_or_title_heuristic_used": False,
            "recency_heuristic_used": False,
        },
        "personal_workspace": {
            "separately_selectable": True,
            "merged_into_business": False,
            "transition": ["PERSONAL", "BUSINESS", "PERSONAL"],
            "readback_state": "PERSONAL",
        },
        "package": {
            "protected_commit": P1_COMMIT,
            "inventory_digest": "3847c8ac04fbd6354a4a352c8eb7bb1fd98c92e24f2c1e3e13c2051f891834df",
            "plugins": ["mastermind-operator", "mastermind-sol"],
        },
        "generations": {
            "steward_source_commit": "2" * 40,
            "executive_source_commit": "3" * 40,
            "control_room_source_commit": "4" * 40,
            "h1_source_commit": "5" * 40,
            "steward_app_generation": "6" * 64,
            "executive_app_generation": "7" * 64,
        },
        "steward": {
            "tools": list(TOOLS),
            "initial_read": {
                "observed_at": "2026-09-02T03:55:00Z",
                "authenticated": True,
                "fresh": True,
                "result_digest": "8" * 64,
            },
            "initial_access_expires_at": "2026-09-02T03:56:00Z",
            "refresh_read": {
                "observed_at": "2026-09-02T03:57:00Z",
                "authenticated": True,
                "fresh": True,
                "after_expiry": True,
                "refresh_succeeded": True,
                "result_digest": "9" * 64,
            },
            "refresh_material_in_mastermind_custody": False,
        },
        "control_room": {
            "structured_read": True,
            "text_fallback": True,
            "desktop_states": _state_rows("desktop"),
            "mobile_states": _state_rows("mobile"),
        },
        "executive_admission": {
            "operation_key": "business-exec-canary-001",
            "intent_id": "mcp-9de04c7dfe8a908026cd5c47cf730a1b",
            "job_id": "JOB-001",
            "submission_calls": 1,
            "duplicate_submission_created_job": False,
            "changed_payload_conflict_observed": True,
            "status": "QUEUED",
            "dispatched": False,
            "attempts": 0,
            "latest_attempt": None,
            "attempt_limit": 1,
            "authorities": ["READ", "RESEARCH"],
            "write_paths": [],
            "validation_commands": [],
            "worker": None,
            "wake_effect": False,
            "runtime_binding_effect": False,
            "slack_effect": False,
            "linear_effect": False,
            "agent_os_effect": False,
            "status_readback": {
                "intent_id": "mcp-9de04c7dfe8a908026cd5c47cf730a1b",
                "job_id": "JOB-001",
                "status": "QUEUED",
                "dispatched": False,
                "attempts": 0,
                "latest_attempt": None,
            },
        },
        "rollback": {
            "observed_at": "2026-09-02T03:59:00Z",
            "performed": True,
            "workspace_state": "PERSONAL",
            "plugin_absent": True,
            "steward_app_absent": True,
            "executive_app_absent": True,
        },
        "zero_unintended_effects": True,
    }


def test_complete_receipt_passes_without_granting_production_acceptance():
    module = _module()
    result = module.validate_one_cockpit_receipt(
        valid_receipt(), evaluated_at=EVALUATED_AT
    )
    assert result["schema"] == "mastermind.business_sol_h1_validation.v1"
    assert result["verdict"] == "PASS"
    assert result["issues"] == []
    assert result["production_acceptance_granted"] is False
    assert result["capability_state"] == "CANARY_EVIDENCE_COMPLETE"
    assert len(result["input_digest"]) == 64
    assert result["validated_generations"]["h1_source_commit"] == "5" * 40


def test_order_insensitive_collections_are_canonicalized_before_digesting():
    module = _module()
    first = valid_receipt()
    second = copy.deepcopy(first)
    second["source_refs"].reverse()
    second["control_cockpit_refs"].reverse()
    second["package"]["plugins"].reverse()
    second["steward"]["tools"].reverse()
    second["control_room"]["desktop_states"].reverse()
    second["control_room"]["mobile_states"].reverse()
    second["executive_admission"]["authorities"].reverse()

    result_a = module.validate_one_cockpit_receipt(first, evaluated_at=EVALUATED_AT)
    result_b = module.validate_one_cockpit_receipt(second, evaluated_at=EVALUATED_AT)
    assert result_a == result_b


@pytest.mark.parametrize(
    ("mutator", "verdict", "issue"),
    [
        (lambda row: row.update(selected_cockpit_ref="cockpit:pro-control-1"), "FAIL", "COCKPIT_NOT_DISTINCT"),
        (lambda row: row["control_cockpit_refs"].__setitem__(1, "cockpit:pro-control-1"), "FAIL", "COCKPIT_NOT_DISTINCT"),
        (lambda row: row["cockpit_selection"].update(method="RECENCY_HEURISTIC"), "FAIL", "COCKPIT_SELECTION_HEURISTIC"),
        (lambda row: row["cockpit_selection"].update(account_or_title_heuristic_used=True), "FAIL", "COCKPIT_SELECTION_HEURISTIC"),
        (lambda row: row["cockpit_selection"].update(recency_heuristic_used=True), "FAIL", "COCKPIT_SELECTION_HEURISTIC"),
        (lambda row: row["personal_workspace"].update(merged_into_business=True), "FAIL", "PERSONAL_WORKSPACE_MERGED"),
        (lambda row: row["personal_workspace"].update(transition=["PERSONAL", "BUSINESS"]), "FAIL", "REVERSIBILITY_NOT_PROVEN"),
        (lambda row: row["package"].update(protected_commit="0" * 40), "FAIL", "PACKAGE_COMMIT_MISMATCH"),
        (lambda row: row["package"].update(inventory_digest="0" * 64), "FAIL", "PACKAGE_INVENTORY_MISMATCH"),
        (lambda row: row["package"]["plugins"].append("unexpected-plugin"), "FAIL", "PACKAGE_INVENTORY_MISMATCH"),
        (lambda row: row["steward"].pop("refresh_read"), "UNKNOWN", "MISSING_REFRESH_READ"),
        (lambda row: row["control_room"].update(text_fallback=False), "FAIL", "CONTROL_ROOM_FALLBACK_MISSING"),
        (lambda row: row["control_room"]["desktop_states"].pop(), "FAIL", "CONTROL_ROOM_STATE_MATRIX_INCOMPLETE"),
        (lambda row: row["control_room"]["mobile_states"][1].update(evidence_digest=row["control_room"]["mobile_states"][0]["evidence_digest"]), "FAIL", "CONTROL_ROOM_EVIDENCE_REUSED"),
        (lambda row: row["executive_admission"].update(submission_calls=True), "FAIL", "EXECUTIVE_SUBMISSION_COUNT_MISMATCH"),
        (lambda row: row["executive_admission"].update(attempts=False), "FAIL", "EXECUTIVE_ATTEMPT_OCCURRED"),
        (lambda row: row["executive_admission"].update(attempt_limit=True), "FAIL", "EXECUTIVE_ATTEMPT_LIMIT_MISMATCH"),
        (lambda row: row["executive_admission"].update(dispatched=True), "FAIL", "EXECUTIVE_DISPATCH_OCCURRED"),
        (lambda row: row["executive_admission"].update(attempts=1), "FAIL", "EXECUTIVE_ATTEMPT_OCCURRED"),
        (lambda row: row["executive_admission"].update(authorities=["READ"]), "FAIL", "EXECUTIVE_AUTHORITY_MISMATCH"),
        (lambda row: row["executive_admission"]["write_paths"].append("control_plane"), "FAIL", "EXECUTIVE_WRITE_SCOPE_PRESENT"),
        (lambda row: row["executive_admission"]["status_readback"].update(job_id="JOB-002"), "FAIL", "EXECUTIVE_READBACK_MISMATCH"),
        (lambda row: row["rollback"].update(performed=False), "FAIL", "ROLLBACK_NOT_PROVEN"),
        (lambda row: row.update(zero_unintended_effects=False), "FAIL", "UNINTENDED_EFFECT_OBSERVED"),
    ],
)
def test_false_green_mutations_cannot_pass(mutator, verdict, issue):
    module = _module()
    receipt = valid_receipt()
    mutator(receipt)
    result = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert result["verdict"] == verdict
    assert issue in result["issues"]
    assert result["production_acceptance_granted"] is False


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "chairman@example.com",
        "/Users/operator/private/profile.json",
        "provider_session:opaque-123",
        "C0123456789/1788320000.123456",
        "https://chatgpt.com/private/conversation",
    ],
)
def test_secret_or_private_locator_values_are_refused(unsafe_value):
    module = _module()
    receipt = valid_receipt()
    receipt["receipt_id"] = unsafe_value
    result = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert result["verdict"] == "REFUSED"
    assert "UNSAFE_VALUE" in result["issues"]
    assert unsafe_value not in json.dumps(result)


@pytest.mark.parametrize(
    ("path", "value", "issue"),
    [
        (("observed_at",), "2026-02-30T03:59:50Z", "TIMESTAMP_INVALID"),
        (("observed_at",), "2026-09-02T04:10:00Z", "EVIDENCE_FROM_FUTURE"),
        (("observed_at",), "2026-09-02T01:00:00Z", "EVIDENCE_STALE"),
        (("steward", "refresh_read", "observed_at"), "2026-09-02T03:55:30Z", "REFRESH_NOT_AFTER_EXPIRY"),
        (("rollback", "observed_at"), "2026-09-02T03:54:00Z", "EVENT_ORDER_INVALID"),
    ],
)
def test_time_contract_fails_closed(path, value, issue):
    module = _module()
    receipt = valid_receipt()
    target = receipt
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = value
    result = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert result["verdict"] in {"FAIL", "REFUSED"}
    assert issue in result["issues"]



def test_source_owner_ref_mismatch_and_post_receipt_evidence_fail():
    module = _module()

    mismatched = valid_receipt()
    mismatched["source_refs"][0]["ref"] = "control-room:not-github"
    mismatch_result = module.validate_one_cockpit_receipt(
        mismatched, evaluated_at=EVALUATED_AT
    )
    assert mismatch_result["verdict"] == "FAIL"
    assert "SOURCE_OWNER_REF_MISMATCH" in mismatch_result["issues"]

    late = valid_receipt()
    late["source_refs"][0]["observed_at"] = "2026-09-02T03:59:55Z"
    late_result = module.validate_one_cockpit_receipt(
        late, evaluated_at=EVALUATED_AT
    )
    assert late_result["verdict"] == "FAIL"
    assert "SOURCE_AFTER_RECEIPT" in late_result["issues"]


def test_correction_requires_exact_append_only_lineage():
    module = _module()
    receipt = valid_receipt()
    receipt["generation"] = 2
    receipt["supersedes_digest"] = "a" * 64
    accepted = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert accepted["verdict"] == "PASS"
    assert accepted["supersedes_digest"] == "a" * 64

    receipt["supersedes_digest"] = "not-a-digest"
    refused = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert refused["verdict"] == "REFUSED"
    assert "CORRECTION_LINEAGE_INVALID" in refused["issues"]


def test_fixture_only_executive_canary_is_truthfully_incomplete():
    module = _module()
    receipt = {
        "schema": "mastermind.business_sol_one_cockpit_receipt.v1",
        "receipt_id": "receipt:fixture-only",
        "generation": 1,
        "observed_at": "2026-09-02T03:59:50Z",
        "executive_admission": valid_receipt()["executive_admission"],
    }
    result = module.validate_one_cockpit_receipt(receipt, evaluated_at=EVALUATED_AT)
    assert result["verdict"] == "UNKNOWN"
    assert "RECEIPT_INCOMPLETE" in result["issues"]


def test_receipt_digest_rejects_non_string_mapping_keys():
    module = _module()
    receipt = valid_receipt()
    receipt[1] = "not-json"
    result = module.validate_one_cockpit_receipt(
        receipt, evaluated_at=EVALUATED_AT
    )
    assert result["verdict"] == "REFUSED"
    assert result["input_digest"] is None
    assert "INVALID_JSON" in result["issues"]


def test_canonical_json_rejects_non_json_state():
    module = _module()
    with pytest.raises(module.ReceiptContractError, match="INVALID_JSON"):
        module.canonical_json({"unordered": {"a", "b"}})
