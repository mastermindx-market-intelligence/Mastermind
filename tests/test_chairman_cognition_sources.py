from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.chairman_cognition import ENVELOPE_SCHEMA, ChairmanCognitionError
from control_plane.chairman_cognition_sources import (
    AGENT_OS_SOURCE_REF,
    COMPOSITION_SCHEMA,
    SOURCE_BUNDLE_SCHEMA,
    STRATEGIC_SOURCE_REF,
    ChairmanCognitionSourceError,
    compose_input,
    evaluate_bundle,
)

_ROOT = Path(__file__).resolve().parents[1]


def _brief(*, degraded=None, warnings=None):
    return {
        "schema": "ceo_brief.v1",
        "generated_at": "2026-08-30T16:00:00Z",
        "inputs": {"degraded": list(degraded or [])},
        "warnings": list(warnings or []),
        "needs_ceo": [],
        "blocked": [],
        "running": {"active": 1},
    }


def _boot_packet(*, mastermind_sha="a" * 40, macro_sha="b" * 40, brief="DEFAULT"):
    resolved_brief = _brief() if brief == "DEFAULT" else brief
    return {
        "schema": "mastermind.ceo_boot_packet.v1",
        "generated_at": "2026-08-30T16:00:00Z",
        "mastermind": {
            "root": "/repo/Mastermind",
            "sha": mastermind_sha,
            "branch": "master",
        },
        "macro": {
            "root": "/repo/Macro Dashboard",
            "sha": macro_sha,
            "resolved_via": "sibling",
            "candidates_tried": [],
        },
        "strategic_state": {
            "schema": "mastermind.strategic_state.v1",
            "company_phase": "PRE_REVENUE_MVP_CONVERGENCE",
            "north_star": ["build a continuously improving AI-led organization"],
            "p0": [],
            "constraints": {
                "autonomous_production_deploy": "prohibited",
                "autonomous_live_capital_execution": "prohibited",
                "duplicate_control_planes": "prohibited",
                "unbounded_autonomous_strategic_modification": "prohibited",
            },
        },
        "brief": resolved_brief,
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "Consult the canonical Improvement Agenda.",
    }


def _option(*, source_refs=None):
    return {
        "option_id": "OPT-COMPOSE",
        "title": "Continue one bounded Chairman cognition vertical",
        "action": "SOURCE_BRANCH_WRITE",
        "reversibility": "REVERSIBLE",
        "source_refs": source_refs
        or [
            "CHAIRMAN_DIRECTIVE:2026-08-30",
            STRATEGIC_SOURCE_REF,
            AGENT_OS_SOURCE_REF,
            "GITHUB:PR-284",
        ],
        "scope_refs": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "effect_state": "NONE",
        "operation_key": "chairman-cognition-compose-test-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:ccl-a2",
        "expected_head_sha": None,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition_sources.py"],
        "budget_units": 1,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop at one exact reviewable branch head.",
        "rollback_plan": "Abandon the unmerged branch.",
        "falsifier": "Any invented CURRENT source is failure.",
        "benefits": {
            "strategic_leverage": 80,
            "dependency_unlock": 75,
            "learning_value": 80,
            "chairman_load_reduction": 70,
            "user_or_machine_value": 70,
        },
        "costs": {
            "time_to_evidence": 20,
            "execution_cost": 15,
            "coordination_risk": 20,
            "irreversibility_risk": 5,
            "scarce_cognition_cost": 20,
        },
    }


def _envelope():
    return {
        "schema": ENVELOPE_SCHEMA,
        "envelope_id": "ENV-COMPOSE-001",
        "authority_source_refs": ["CHAIRMAN_DIRECTIVE:2026-08-30"],
        "mode": "SUPERVISED_LIVE_CANARY",
        "allowed_actions": ["SOURCE_BRANCH_WRITE"],
        "allowed_reversibility": ["REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": ["control_plane"]
        },
        "allowed_scope_prefixes": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "allowed_carrier_prefixes": ["github:Mastermind:branch:"],
        "max_budget_units": 5,
        "max_active_children": 2,
        "require_exact_carrier": True,
        "expires_at": "2026-09-30T00:00:00Z",
    }


def _github_receipt():
    return {
        "source_ref": "GITHUB:PR-284",
        "owner": "GITHUB",
        "revision": "1927f82f8a30893b379a2a2e2b5b10abd625fccb",
        "state": "CURRENT",
        "load_bearing": True,
        "observed_at": "2026-08-30T16:00:00Z",
    }


def _bundle(*, boot=None, option=None, additions=None):
    return {
        "schema": SOURCE_BUNDLE_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "chairman_directive": {
            "source_ref": "CHAIRMAN_DIRECTIVE:2026-08-30",
            "revision": "conversation:pro-mode-go",
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": "2026-08-30T16:00:00Z",
        },
        "boot_packet": _boot_packet() if boot is None else boot,
        "additional_source_receipts": (
            [_github_receipt()] if additions is None else additions
        ),
        "delegation_envelope": _envelope(),
        "options": [_option() if option is None else option],
    }


def _receipt(document, source_ref):
    return next(
        item for item in document["source_receipts"] if item["source_ref"] == source_ref
    )


def test_composes_owner_attributed_input_and_evaluates_unique_option():
    composed = compose_input(_bundle())
    assert [item["source_ref"] for item in composed["source_receipts"]] == [
        "CHAIRMAN_DIRECTIVE:2026-08-30",
        STRATEGIC_SOURCE_REF,
        AGENT_OS_SOURCE_REF,
        "GITHUB:PR-284",
    ]
    assert _receipt(composed, STRATEGIC_SOURCE_REF)["state"] == "CURRENT"
    assert _receipt(composed, AGENT_OS_SOURCE_REF)["state"] == "CURRENT"
    assert composed["strategic_constraints"]["duplicate_control_planes"] == "prohibited"

    result = evaluate_bundle(_bundle())
    assert result["schema"] == COMPOSITION_SCHEMA
    assert result["packet"]["recommended_option_id"] == "OPT-COMPOSE"
    assert result["execution_authority_granted"] is False
    assert result["packet"]["execution_authority_granted"] is False


def test_composition_is_deterministic_and_does_not_mutate_owner_documents():
    bundle = _bundle()
    original = copy.deepcopy(bundle)
    assert evaluate_bundle(bundle) == evaluate_bundle(copy.deepcopy(bundle))
    assert bundle == original


def test_missing_or_invalid_strategic_state_fails_closed():
    for strategic in (None, {"schema": "wrong"}):
        boot = _boot_packet()
        boot["strategic_state"] = strategic
        with pytest.raises(ChairmanCognitionSourceError, match="strategic state"):
            compose_input(_bundle(boot=boot))


def test_unresolved_or_noncanonical_mastermind_revision_is_unknown_not_current():
    boot = _boot_packet(mastermind_sha=None)
    option = _option(source_refs=[STRATEGIC_SOURCE_REF])
    composed = compose_input(_bundle(boot=boot, option=option))
    assert _receipt(composed, STRATEGIC_SOURCE_REF)["state"] == "UNKNOWN"
    result = evaluate_bundle(_bundle(boot=boot, option=option))
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_missing_or_degraded_agentos_is_unknown_not_fabricated_current():
    cases = [
        None,
        _brief(degraded=["worktree census unavailable"]),
        _brief(warnings=["source mismatch"]),
        {**_brief(), "schema": "future.brief.v2"},
    ]
    for brief in cases:
        boot = _boot_packet(brief=brief)
        option = _option(source_refs=[AGENT_OS_SOURCE_REF])
        result = evaluate_bundle(_bundle(boot=boot, option=option, additions=[]))
        summary = next(
            item
            for item in result["source_summary"]
            if item["source_ref"] == AGENT_OS_SOURCE_REF
        )
        assert summary["state"] == "UNKNOWN"
        assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_reserved_source_owner_and_duplicate_ref_fail_closed():
    injected = _github_receipt()
    injected["owner"] = "AGENT_OS"
    with pytest.raises(ChairmanCognitionSourceError, match="reserved canonical source"):
        compose_input(_bundle(additions=[injected]))

    duplicate = _github_receipt()
    duplicate["source_ref"] = STRATEGIC_SOURCE_REF
    with pytest.raises(ChairmanCognitionSourceError, match="duplicate source_ref"):
        compose_input(_bundle(additions=[duplicate]))


def test_future_dated_owner_receipt_is_rejected_by_a1():
    future = _github_receipt()
    future["observed_at"] = "2026-08-30T16:00:01Z"
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        compose_input(_bundle(additions=[future]))


def test_non_master_strategic_checkout_is_unknown_even_with_full_sha():
    boot = _boot_packet()
    boot["mastermind"]["branch"] = "feature/unaccepted-strategy"
    option = _option(source_refs=[STRATEGIC_SOURCE_REF])
    result = evaluate_bundle(_bundle(boot=boot, option=option))
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == STRATEGIC_SOURCE_REF
    )
    assert summary["state"] == "UNKNOWN"
    assert summary["revision"].startswith("sha256:")
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_cli_valid_and_opaque_invalid_journeys(tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_bundle()), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "chairman_cognition_compose.py"), str(valid)],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["schema"] == COMPOSITION_SCHEMA

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret":"do-not-leak"}', encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "chairman_cognition_compose.py"), str(invalid)],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "INVALID_SOURCE_BUNDLE" in proc.stderr
    assert "do-not-leak" not in proc.stderr
    assert proc.stdout == ""
