from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane.chairman_cognition import ENVELOPE_SCHEMA, ChairmanCognitionError
from control_plane.chairman_cognition_sources import (
    AGENT_OS_REVISION_SOURCE_REF,
    AGENT_OS_SOURCE_REF,
    COMPOSITION_SCHEMA,
    MASTERMIND_REVISION_SOURCE_REF,
    SOURCE_BUNDLE_SCHEMA,
    STRATEGIC_SOURCE_REF,
    ChairmanCognitionSourceError,
    compose_input,
    evaluate_bundle,
)

_ROOT = Path(__file__).resolve().parents[1]
_MASTERMIND_SHA = "a" * 40
_MACRO_SHA = "b" * 40


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


def _boot_packet(
    *, mastermind_sha=_MASTERMIND_SHA, macro_sha=_MACRO_SHA, brief="DEFAULT"
):
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


def _revision_attestation(revision, *, state="CURRENT"):
    return {
        "revision": revision,
        "state": state,
        "load_bearing": True,
        "observed_at": "2026-08-30T16:00:00Z",
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
        "mastermind_revision_attestation": _revision_attestation(
            _MASTERMIND_SHA
        ),
        "agentos_revision_attestation": _revision_attestation(_MACRO_SHA),
        "boot_packet": _boot_packet() if boot is None else boot,
        "additional_source_receipts": (
            [_github_receipt()] if additions is None else additions
        ),
        "delegation_envelope": _envelope(),
        "options": [_option() if option is None else option],
    }


def _receipt(document, source_ref):
    return next(
        item
        for item in document["source_receipts"]
        if item["source_ref"] == source_ref
    )


def test_composes_owner_attributed_input_and_evaluates_unique_option():
    composed = compose_input(_bundle())
    assert [item["source_ref"] for item in composed["source_receipts"]] == [
        "CHAIRMAN_DIRECTIVE:2026-08-30",
        MASTERMIND_REVISION_SOURCE_REF,
        STRATEGIC_SOURCE_REF,
        AGENT_OS_REVISION_SOURCE_REF,
        AGENT_OS_SOURCE_REF,
        "GITHUB:PR-284",
    ]
    assert _receipt(composed, STRATEGIC_SOURCE_REF)["state"] == "CURRENT"
    assert _receipt(composed, AGENT_OS_SOURCE_REF)["state"] == "CURRENT"
    assert (
        composed["strategic_constraints"]["duplicate_control_planes"]
        == "prohibited"
    )

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


def test_unresolved_mastermind_revision_is_unknown_not_current():
    boot = _boot_packet(mastermind_sha=None)
    option = _option(source_refs=[STRATEGIC_SOURCE_REF])
    result = evaluate_bundle(_bundle(boot=boot, option=option))
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == STRATEGIC_SOURCE_REF
    )
    assert summary["state"] == "UNKNOWN"
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_stale_local_master_cannot_be_laundered_as_current():
    boot = _boot_packet(mastermind_sha="c" * 40)
    option = _option(source_refs=[STRATEGIC_SOURCE_REF])
    result = evaluate_bundle(_bundle(boot=boot, option=option))
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == STRATEGIC_SOURCE_REF
    )
    assert summary["state"] == "CONFLICT"
    assert "canonical:" + _MASTERMIND_SHA in summary["revision"]
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_noncanonical_mastermind_checkout_is_unknown_even_when_sha_matches():
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
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_stale_or_unknown_mastermind_attestation_propagates():
    for state in ("STALE", "UNKNOWN", "CONFLICT"):
        bundle = _bundle(option=_option(source_refs=[STRATEGIC_SOURCE_REF]))
        bundle["mastermind_revision_attestation"]["state"] = state
        result = evaluate_bundle(bundle)
        summary = next(
            item
            for item in result["source_summary"]
            if item["source_ref"] == STRATEGIC_SOURCE_REF
        )
        assert summary["state"] == state
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


def test_macro_revision_mismatch_is_conflict_not_current():
    boot = _boot_packet(macro_sha="d" * 40)
    option = _option(source_refs=[AGENT_OS_SOURCE_REF])
    result = evaluate_bundle(_bundle(boot=boot, option=option, additions=[]))
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == AGENT_OS_SOURCE_REF
    )
    assert summary["state"] == "CONFLICT"
    assert "canonical:" + _MACRO_SHA in summary["revision"]
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"


def test_reserved_source_owner_and_duplicate_ref_fail_closed():
    injected = _github_receipt()
    injected["owner"] = "AGENT_OS"
    with pytest.raises(
        ChairmanCognitionSourceError, match="reserved canonical source"
    ):
        compose_input(_bundle(additions=[injected]))

    duplicate = _github_receipt()
    duplicate["source_ref"] = STRATEGIC_SOURCE_REF
    with pytest.raises(ChairmanCognitionSourceError, match="duplicate source_ref"):
        compose_input(_bundle(additions=[duplicate]))


def test_revision_attestations_are_closed_load_bearing_full_shas():
    for field in (
        "mastermind_revision_attestation",
        "agentos_revision_attestation",
    ):
        bundle = _bundle()
        bundle[field]["load_bearing"] = False
        with pytest.raises(ChairmanCognitionSourceError, match="load-bearing"):
            compose_input(bundle)

        bundle = _bundle()
        bundle[field]["revision"] = "short"
        with pytest.raises(ChairmanCognitionSourceError, match="full commit SHA"):
            compose_input(bundle)

        bundle = _bundle()
        bundle[field]["extra"] = True
        with pytest.raises(ChairmanCognitionSourceError, match="unknown fields"):
            compose_input(bundle)


def test_future_dated_owner_receipt_is_rejected_by_a1():
    future = _github_receipt()
    future["observed_at"] = "2026-08-30T16:00:01Z"
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        compose_input(_bundle(additions=[future]))


def test_cli_valid_and_opaque_invalid_journeys(tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_bundle()), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "chairman_cognition_compose.py"),
            str(valid),
        ],
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
        [
            sys.executable,
            str(_ROOT / "scripts" / "chairman_cognition_compose.py"),
            str(invalid),
        ],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "INVALID_SOURCE_BUNDLE" in proc.stderr
    assert "do-not-leak" not in proc.stderr
    assert proc.stdout == ""


def test_derived_source_observation_uses_latest_load_bearing_input():
    bundle = _bundle()
    bundle["as_of"] = "2026-08-30T16:00:02Z"
    bundle["mastermind_revision_attestation"]["observed_at"] = (
        "2026-08-30T16:00:02Z"
    )
    bundle["agentos_revision_attestation"]["observed_at"] = (
        "2026-08-30T16:00:01Z"
    )
    composed = compose_input(bundle)
    assert _receipt(composed, STRATEGIC_SOURCE_REF)["observed_at"] == (
        "2026-08-30T16:00:02Z"
    )
    assert _receipt(composed, AGENT_OS_SOURCE_REF)["observed_at"] == (
        "2026-08-30T16:00:01Z"
    )


def test_future_dated_revision_attestation_is_rejected_by_a1():
    bundle = _bundle()
    bundle["mastermind_revision_attestation"]["observed_at"] = (
        "2026-08-30T16:00:01Z"
    )
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        compose_input(bundle)


def test_composer_imports_no_io_runtime_or_connector_owner():
    source = (
        _ROOT / "control_plane" / "chairman_cognition_sources.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    forbidden = (
        "pathlib",
        "sqlite",
        "subprocess",
        "socket",
        "urllib",
        "httpx",
        "requests",
        "worker_runtime",
        "executive_runtime",
        "capacity",
        "runtime_binding",
        "slack",
        "linear",
        "github",
        "agentos",
        "mcp",
    )
    offenders = sorted(
        name
        for name in imported
        if any(fragment in name.lower() for fragment in forbidden)
    )
    assert not offenders, offenders
