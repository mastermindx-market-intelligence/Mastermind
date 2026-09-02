"""Mutation controls for the Business Sol H1 evidence validator."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util

import pytest


MODULE = "integrations.business_sol_canary.evidence"
EVALUATED_AT = "2026-09-02T04:00:00Z"
P1_COMMIT = "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"
TOOLS = (
    "list_responsibilities",
    "get_responsibility",
    "get_attention",
    "get_current_runtime",
    "explain_blocker",
    "resolve_surface",
)
STATES = (
    "NORMAL",
    "STALE",
    "DEGRADED",
    "PARTIAL_CLOSEOUT",
    "EFFECT_UNKNOWN",
    "NO_ACTION",
)


def _module():
    try:
        spec = importlib.util.find_spec(MODULE)
    except ModuleNotFoundError:
        spec = None
    assert spec is not None, "Business Sol H1 validator is not implemented"
    return importlib.import_module(MODULE)


def _receipt() -> dict:
    source = lambda owner, ref: {
        "owner": owner,
        "ref": ref,
        "observed_at": "2026-09-02T03:58:00Z",
        "freshness": "FRESH",
    }
    read = lambda when, digest: {
        "observed_at": when,
        "authenticated": True,
        "fresh": True,
        "result_digest": digest,
    }
    state_rows = lambda prefix: [
        {
            "state": state,
            "evidence_digest": hashlib.sha256(
                f"{prefix}:{state}".encode("utf-8")
            ).hexdigest(),
            "structured_text_equivalent": True,
        }
        for state in STATES
    ]
    return {
        "schema": "mastermind.business_sol_one_cockpit_receipt.v1",
        "receipt_id": "receipt:mutation-base",
        "generation": 1,
        "observed_at": "2026-09-02T03:59:50Z",
        "source_refs": [
            source("github", f"commit:{P1_COMMIT}"),
            source("business_workspace", "workspace-readback:canary-001"),
            source("chatgpt", "app-readback:canary-001"),
            source("executive_os", "executive-job:JOB-001"),
            source("control_room", "control-room:canary-001"),
        ],
        "selected_cockpit_ref": "cockpit:business-canary",
        "control_cockpit_refs": ["cockpit:control-a", "cockpit:control-b"],
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
            "initial_read": read("2026-09-02T03:55:00Z", "8" * 64),
            "initial_access_expires_at": "2026-09-02T03:56:00Z",
            "refresh_read": {
                **read("2026-09-02T03:57:00Z", "9" * 64),
                "after_expiry": True,
                "refresh_succeeded": True,
            },
            "refresh_material_in_mastermind_custody": False,
        },
        "control_room": {
            "structured_read": True,
            "text_fallback": True,
            "desktop_states": state_rows("desktop"),
            "mobile_states": state_rows("mobile"),
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


@pytest.mark.parametrize(
    ("path", "mutant", "issue"),
    [
        (("executive_admission", "submission_calls"), 0, "EXECUTIVE_SUBMISSION_COUNT_MISMATCH"),
        (("executive_admission", "duplicate_submission_created_job"), True, "EXECUTIVE_DUPLICATE_JOB"),
        (("executive_admission", "changed_payload_conflict_observed"), False, "EXECUTIVE_CONFLICT_NOT_PROVEN"),
        (("executive_admission", "latest_attempt"), "ATT-1", "EXECUTIVE_ATTEMPT_OCCURRED"),
        (("executive_admission", "worker"), "worker-1", "EXECUTIVE_WORKER_PRESENT"),
        (("executive_admission", "wake_effect"), True, "EXECUTIVE_SIDE_EFFECT_PRESENT"),
        (("executive_admission", "runtime_binding_effect"), True, "EXECUTIVE_SIDE_EFFECT_PRESENT"),
        (("executive_admission", "slack_effect"), True, "EXECUTIVE_SIDE_EFFECT_PRESENT"),
        (("executive_admission", "linear_effect"), True, "EXECUTIVE_SIDE_EFFECT_PRESENT"),
        (("executive_admission", "agent_os_effect"), True, "EXECUTIVE_SIDE_EFFECT_PRESENT"),
        (("steward", "refresh_material_in_mastermind_custody"), True, "REFRESH_MATERIAL_CUSTODY"),
        (("rollback", "plugin_absent"), False, "ROLLBACK_READBACK_MISMATCH"),
        (("rollback", "steward_app_absent"), False, "ROLLBACK_READBACK_MISMATCH"),
        (("rollback", "executive_app_absent"), False, "ROLLBACK_READBACK_MISMATCH"),
    ],
)
def test_killed_false_green_mutations(path, mutant, issue):
    module = _module()
    receipt = _receipt()
    target = receipt
    for name in path[:-1]:
        target = target[name]
    target[path[-1]] = mutant

    result = module.validate_one_cockpit_receipt(
        receipt, evaluated_at=EVALUATED_AT
    )

    assert result["verdict"] != "PASS"
    assert issue in result["issues"]


def test_issue_order_and_digest_are_permutation_stable_under_multiple_failures():
    module = _module()
    first = _receipt()
    first["personal_workspace"]["merged_into_business"] = True
    first["executive_admission"]["dispatched"] = True
    first["rollback"]["performed"] = False

    second = copy.deepcopy(first)
    second["source_refs"].reverse()
    second["control_room"]["desktop_states"].reverse()
    second["executive_admission"]["authorities"].reverse()

    result_a = module.validate_one_cockpit_receipt(first, evaluated_at=EVALUATED_AT)
    result_b = module.validate_one_cockpit_receipt(second, evaluated_at=EVALUATED_AT)

    assert result_a == result_b
    assert result_a["issues"] == sorted(result_a["issues"])
    assert result_a["verdict"] == "FAIL"
