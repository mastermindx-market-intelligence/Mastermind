from __future__ import annotations

import ast
import copy
import hashlib
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
_PLAN = (
    _ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-chairman-cognition-source-composer-a2.md"
)
_MASTERMIND_SHA = "a" * 40
_MACRO_SHA = "b" * 40
_STRATEGIC_BLOB_SHA = "c" * 40
_AGENTOS_RECORDS_DIGEST = "sha256:" + "d" * 64
_CHAIRMAN_REF = "CHAIRMAN_DIRECTIVE:2026-08-30"
_GITHUB_REF = "GITHUB:A1"


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _payload_digest(value) -> str:
    return "sha256:" + _digest(value)


def _classification_payload(option: dict) -> dict:
    return {
        "option_id": option["option_id"],
        "action": option["action"],
        "scope_refs": sorted(option["scope_refs"]),
        "repositories": sorted(option["repositories"]),
        "paths": sorted(option["paths"]),
        "creates_duplicate_control_plane": option[
            "creates_duplicate_control_plane"
        ],
        "change_classes": sorted(option["change_classes"]),
        "affected_departments": sorted(option["affected_departments"]),
    }


def _envelope_payload(envelope: dict) -> dict:
    return {
        "schema": envelope["schema"],
        "envelope_id": envelope["envelope_id"],
        "authority_source_refs": sorted(envelope["authority_source_refs"]),
        "mode": envelope["mode"],
        "allowed_actions": sorted(envelope["allowed_actions"]),
        "allowed_reversibility": sorted(envelope["allowed_reversibility"]),
        "allowed_repositories": sorted(envelope["allowed_repositories"]),
        "allowed_path_prefixes": {
            repository: sorted(envelope["allowed_path_prefixes"][repository])
            for repository in sorted(envelope["allowed_path_prefixes"])
        },
        "allowed_scope_prefixes": sorted(envelope["allowed_scope_prefixes"]),
        "allowed_carrier_prefixes": sorted(envelope["allowed_carrier_prefixes"]),
        "max_budget_units": envelope["max_budget_units"],
        "max_active_children": envelope["max_active_children"],
        "require_exact_carrier": envelope["require_exact_carrier"],
        "expires_at": envelope["expires_at"],
    }


def _append_binding(receipt: dict, label: str, digest: str) -> None:
    prefix = f"{label}:"
    fields = [
        field
        for field in receipt["revision"].split(";")
        if not field.startswith(prefix)
    ]
    fields.append(f"{label}:{digest}")
    receipt["revision"] = ";".join(fields)


def _bind_bundle(bundle: dict) -> dict:
    receipts = {
        bundle["chairman_directive"]["source_ref"]: bundle["chairman_directive"]
    }
    receipts.update(
        {
            item["source_ref"]: item
            for item in bundle["additional_source_receipts"]
        }
    )
    envelope = bundle["delegation_envelope"]
    envelope_digest = _digest(_envelope_payload(envelope))
    for ref in envelope["authority_source_refs"]:
        if ref in receipts:
            _append_binding(receipts[ref], "envelope-sha256", envelope_digest)
    for option in bundle["options"]:
        ref = option["classification_source_ref"]
        if ref in receipts:
            token = f"classification-sha256:{_digest(_classification_payload(option))}"
            fields = receipts[ref]["revision"].split(";")
            if token not in fields:
                receipts[ref]["revision"] = ";".join([*fields, token])
    return bundle


def _brief(*, degraded=None, warnings=None, readiness_degraded=None):
    return {
        "schema": "ceo_brief.v1",
        "generated_at": "2026-08-30T16:00:00Z",
        "since": "2026-08-29T16:00:00Z",
        "since_label": "the last 24h",
        "counts": {
            "total": 1,
            "active": 1,
            "awaiting_ci": 0,
            "blocked": 0,
            "done_in_window": 0,
        },
        "inputs": {
            "active_builds_age_hours": 1.0,
            "worktrees": 1,
            "degraded": list(degraded or []),
        },
        "needs_ceo": [],
        "blocked": [],
        "finished": [],
        "running": {
            "active": 1,
            "awaiting_ci": 0,
            "awaiting_review": 0,
            "blocked": 0,
            "proposed": 0,
            "open_prs": 0,
            "stale_claims": 0,
            "claims_without_worktree": 0,
        },
        "readiness": {
            "schema": "agentos.readiness.v1",
            "records": [
                {
                    "workstream": "CHAIRMAN-CONTROL-ROOM",
                    "wave": None,
                    "state": "in_progress",
                    "reason_code": "status_in_progress",
                    "reason": "Authored workstream status is active.",
                    "depends_on": [],
                    "unmet_dependencies": [],
                    "source": "agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md",
                }
            ],
            "degraded": list(readiness_degraded or []),
        },
        "warnings": list(warnings or []),
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
                "marketing_org_expansion_before_distribution_proof": "prohibited",
                "new_feature_expansion": "constrained",
                "unbounded_autonomous_strategic_modification": "prohibited",
            },
        },
        "brief": resolved_brief,
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "Consult the canonical Improvement Agenda.",
    }


def _mastermind_attestation(boot: dict, *, state="CURRENT") -> dict:
    return {
        "revision": _MASTERMIND_SHA,
        "state": state,
        "load_bearing": True,
        "observed_at": "2026-08-30T16:00:00Z",
        "source_blob_sha": _STRATEGIC_BLOB_SHA,
        "payload_digest": _payload_digest(boot["strategic_state"]),
    }


def _agentos_attestation(boot: dict, *, state="CURRENT") -> dict:
    return {
        "revision": _MACRO_SHA,
        "state": state,
        "load_bearing": True,
        "observed_at": "2026-08-30T16:00:00Z",
        "source_records_digest": _AGENTOS_RECORDS_DIGEST,
        "payload_digest": _payload_digest(boot["brief"]),
    }


def _option(*, source_refs=None, **changes):
    refs = list(
        source_refs
        or [
            _CHAIRMAN_REF,
            STRATEGIC_SOURCE_REF,
            AGENT_OS_SOURCE_REF,
            _GITHUB_REF,
        ]
    )
    if _CHAIRMAN_REF not in refs:
        refs.insert(0, _CHAIRMAN_REF)
    option = {
        "option_id": "OPT-COMPOSE",
        "title": "Continue one bounded Chairman cognition vertical",
        "action": "SOURCE_BRANCH_WRITE",
        "reversibility": "REVERSIBLE",
        "source_refs": refs,
        "scope_refs": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "effect_state": "NONE",
        "operation_key": "chairman-cognition-compose-test-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:ccl-a2",
        "expected_head_sha": "a" * 40,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition_sources.py"],
        "budget_units": 1,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop at one exact reviewable branch head.",
        "rollback_plan": "Abandon the unmerged branch.",
        "falsifier": "Any invented CURRENT source is failure.",
        "classification_source_ref": _CHAIRMAN_REF,
        "change_classes": ["EXISTING_CAPABILITY_COMPLETION"],
        "affected_departments": ["executive"],
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
    option.update(changes)
    return option


def _envelope():
    return {
        "schema": ENVELOPE_SCHEMA,
        "envelope_id": "ENV-COMPOSE-001",
        "authority_source_refs": [_CHAIRMAN_REF],
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
        "source_ref": _GITHUB_REF,
        "owner": "GITHUB",
        "revision": "00ea4ac337af99e9d5a13be0e4b36ab861f4c336",
        "state": "CURRENT",
        "load_bearing": True,
        "observed_at": "2026-08-30T16:00:00Z",
    }


def _bundle(*, boot=None, option=None, additions=None):
    resolved_boot = _boot_packet() if boot is None else boot
    bundle = {
        "schema": SOURCE_BUNDLE_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "chairman_directive": {
            "source_ref": _CHAIRMAN_REF,
            "revision": "conversation:pro-mode-go",
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": "2026-08-30T16:00:00Z",
        },
        "mastermind_revision_attestation": _mastermind_attestation(resolved_boot),
        "agentos_revision_attestation": _agentos_attestation(resolved_boot),
        "boot_packet": resolved_boot,
        "additional_source_receipts": (
            [_github_receipt()] if additions is None else additions
        ),
        "delegation_envelope": _envelope(),
        "options": [_option() if option is None else option],
    }
    return _bind_bundle(bundle)


def _receipt(document, source_ref):
    return next(
        item
        for item in document["source_receipts"]
        if item["source_ref"] == source_ref
    )


def _duplicate_payload(secret: str, *, nested: bool) -> str:
    valid = json.dumps(_bundle(), separators=(",", ":"))
    if nested:
        target = '"option_id":"OPT-COMPOSE"'
        replacement = f'"option_id":"{secret}","option_id":"OPT-COMPOSE"'
        assert target in valid
        return valid.replace(target, replacement, 1)
    return f'{{"schema":"{secret}",' + valid[1:]


def _assert_agentos_state(bundle: dict, expected: str) -> dict:
    result = evaluate_bundle(bundle)
    summary = next(
        item
        for item in result["source_summary"]
        if item["source_ref"] == AGENT_OS_SOURCE_REF
    )
    assert summary["state"] == expected
    assert result["packet"]["adjudications"][0]["reason"] == "SOURCE_NOT_CURRENT"
    return summary


def test_composes_owner_attributed_input_and_evaluates_unique_option():
    composed = compose_input(_bundle())
    assert [item["source_ref"] for item in composed["source_receipts"]] == [
        _CHAIRMAN_REF,
        MASTERMIND_REVISION_SOURCE_REF,
        STRATEGIC_SOURCE_REF,
        AGENT_OS_REVISION_SOURCE_REF,
        AGENT_OS_SOURCE_REF,
        _GITHUB_REF,
    ]
    strategic = _receipt(composed, STRATEGIC_SOURCE_REF)
    agentos = _receipt(composed, AGENT_OS_SOURCE_REF)
    assert strategic["state"] == "CURRENT"
    assert agentos["state"] == "CURRENT"
    assert "constraints-sha256:" in strategic["revision"]
    assert f"blob:{_STRATEGIC_BLOB_SHA}" in strategic["revision"]
    assert "records-sha256:" + "d" * 64 in agentos["revision"]

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
        bundle = _bundle()
        bundle["boot_packet"] = boot
        with pytest.raises(ChairmanCognitionSourceError, match="strategic state"):
            compose_input(bundle)


def test_each_load_bearing_strategic_constraint_is_required_by_composer():
    constraints = tuple(_boot_packet()["strategic_state"]["constraints"])
    assert constraints == (
        "autonomous_production_deploy",
        "autonomous_live_capital_execution",
        "duplicate_control_planes",
        "marketing_org_expansion_before_distribution_proof",
        "new_feature_expansion",
        "unbounded_autonomous_strategic_modification",
    )
    for constraint in constraints:
        bundle = _bundle()
        del bundle["boot_packet"]["strategic_state"]["constraints"][constraint]
        with pytest.raises(
            ChairmanCognitionSourceError,
            match="load-bearing strategic constraint missing",
        ):
            compose_input(bundle)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda bundle: bundle["boot_packet"]["strategic_state"].update(
            {"company_phase": "MUTATED_WITHOUT_ATTESTATION"}
        ),
        lambda bundle: bundle["mastermind_revision_attestation"].update(
            {"payload_digest": "UNRESOLVED"}
        ),
        lambda bundle: bundle["mastermind_revision_attestation"].update(
            {"source_blob_sha": "UNRESOLVED"}
        ),
    ],
)
def test_strategic_payload_or_identity_cannot_be_laundered_current(mutation):
    bundle = _bundle()
    mutation(bundle)
    with pytest.raises(
        ChairmanCognitionError,
        match="strategic constraints source must be CURRENT",
    ):
        compose_input(bundle)


def test_unresolved_or_noncanonical_mastermind_checkout_is_not_current():
    for sha, branch in ((None, "master"), (_MASTERMIND_SHA, "feature/unaccepted")):
        boot = _boot_packet(mastermind_sha=sha)
        boot["mastermind"]["branch"] = branch
        bundle = _bundle(boot=boot)
        with pytest.raises(
            ChairmanCognitionError,
            match="strategic constraints source must be CURRENT",
        ):
            compose_input(bundle)


def test_stale_local_master_and_noncurrent_attestation_fail_root_closed():
    bundle = _bundle()
    bundle["boot_packet"]["mastermind"]["sha"] = "e" * 40
    with pytest.raises(ChairmanCognitionError, match="must be CURRENT"):
        compose_input(bundle)

    for state in ("STALE", "UNKNOWN", "CONFLICT"):
        bundle = _bundle()
        bundle["mastermind_revision_attestation"]["state"] = state
        with pytest.raises(ChairmanCognitionError, match="must be CURRENT"):
            compose_input(bundle)


def test_agentos_payload_mutation_with_unchanged_revision_is_conflict():
    bundle = _bundle()
    bundle["boot_packet"]["brief"]["counts"]["total"] += 1
    summary = _assert_agentos_state(bundle, "CONFLICT")
    assert "payload-sha256:" in summary["revision"]


def test_agentos_unresolved_owner_identity_is_unknown():
    for field in ("payload_digest", "source_records_digest"):
        bundle = _bundle()
        bundle["agentos_revision_attestation"][field] = "UNRESOLVED"
        _assert_agentos_state(bundle, "UNKNOWN")


def test_missing_degraded_or_malformed_agentos_is_unknown_not_current():
    cases = [
        None,
        _brief(degraded=["worktree census unavailable"]),
        _brief(readiness_degraded=["ambiguous workstream source"]),
        {**_brief(), "schema": "future.brief.v2"},
    ]
    for brief in cases:
        boot = _boot_packet(brief=brief)
        bundle = _bundle(boot=boot)
        if isinstance(brief, dict):
            bundle["agentos_revision_attestation"]["payload_digest"] = _payload_digest(
                brief
            )
        else:
            bundle["agentos_revision_attestation"]["payload_digest"] = "UNRESOLVED"
        _assert_agentos_state(bundle, "UNKNOWN")


def test_partial_or_malformed_ceo_brief_cannot_be_laundered_current():
    partial = {
        "schema": "ceo_brief.v1",
        "inputs": {"degraded": []},
        "warnings": [],
    }
    malformed_readiness = _brief()
    malformed_readiness["readiness"]["records"] = [{"state": "ready"}]
    boolean_count = _brief()
    boolean_count["counts"]["total"] = True

    for brief in (partial, malformed_readiness, boolean_count):
        boot = _boot_packet(brief=brief)
        bundle = _bundle(boot=boot)
        _assert_agentos_state(bundle, "UNKNOWN")


def test_macro_revision_mismatch_is_conflict_not_current():
    bundle = _bundle()
    bundle["boot_packet"]["macro"]["sha"] = "f" * 40
    summary = _assert_agentos_state(bundle, "CONFLICT")
    assert "git:" + _MACRO_SHA in summary["revision"]


def test_modifying_options_must_cite_both_canonical_owner_roots():
    for omitted in (STRATEGIC_SOURCE_REF, AGENT_OS_SOURCE_REF):
        refs = [
            _CHAIRMAN_REF,
            STRATEGIC_SOURCE_REF,
            AGENT_OS_SOURCE_REF,
            _GITHUB_REF,
        ]
        refs.remove(omitted)
        bundle = _bundle(option=_option(source_refs=refs))
        with pytest.raises(
            ChairmanCognitionSourceError,
            match="must cite Strategic State and Agent OS",
        ):
            compose_input(bundle)


def test_read_only_option_does_not_require_agentos_citation():
    option = _option(
        action="READ_ONLY_AUDIT",
        reversibility="READ_ONLY",
        source_refs=[_CHAIRMAN_REF, _GITHUB_REF],
        operation_key=None,
        carrier_state="NOT_APPLICABLE",
        carrier_ref=None,
        expected_head_sha=None,
        active_children_after=0,
        stop_condition=None,
        rollback_plan=None,
        falsifier=None,
    )
    bundle = _bundle(option=option)
    result = evaluate_bundle(bundle)
    assert result["packet"]["adjudications"][0]["disposition"] == (
        "READ_ONLY_ELIGIBLE"
    )


def test_source_merge_without_expected_head_remains_refused_by_a1():
    option = _option(action="SOURCE_MERGE", expected_head_sha=None)
    result = evaluate_bundle(_bundle(option=option))
    adjudication = result["packet"]["adjudications"][0]
    assert adjudication["disposition"] == "REFUSED"
    assert adjudication["reason"] == "EXPECTED_HEAD_REQUIRED"


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


def test_attestations_are_closed_load_bearing_and_content_typed():
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

    bundle = _bundle()
    bundle["mastermind_revision_attestation"]["source_blob_sha"] = "not-a-blob"
    with pytest.raises(ChairmanCognitionSourceError, match="Git blob SHA"):
        compose_input(bundle)

    bundle = _bundle()
    bundle["agentos_revision_attestation"]["source_records_digest"] = (
        "sha256:UPPERCASE"
    )
    with pytest.raises(ChairmanCognitionSourceError, match="64 lowercase hex"):
        compose_input(bundle)


def test_future_dated_owner_receipt_and_attestation_are_rejected_by_a1():
    future = _github_receipt()
    future["observed_at"] = "2026-08-30T16:00:01Z"
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        compose_input(_bundle(additions=[future]))

    bundle = _bundle()
    bundle["mastermind_revision_attestation"]["observed_at"] = (
        "2026-08-30T16:00:01Z"
    )
    with pytest.raises(ChairmanCognitionError, match="postdate"):
        compose_input(bundle)


def test_bound_envelope_mutation_is_rejected_before_acceptance():
    bundle = _bundle()
    bundle["delegation_envelope"]["max_budget_units"] += 1
    with pytest.raises(ChairmanCognitionError, match="not content-bound"):
        compose_input(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("option_id", "OPT-OTHER"),
        ("action", "SOURCE_MERGE"),
        ("scope_refs", ["WS:CHAIRMAN-CONTROL-ROOM:OTHER"]),
        ("repositories", ["mastermindx-market-intelligence/macro"]),
        ("paths", ["control_plane/other.py"]),
        ("creates_duplicate_control_plane", True),
    ],
)
def test_bound_classification_cannot_move_to_another_option_subject(field, value):
    bundle = _bundle()
    bundle["options"][0][field] = value
    with pytest.raises(ChairmanCognitionError, match="not content-bound"):
        compose_input(bundle)


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
    assert json.loads(proc.stderr)["error"] == "INVALID_SOURCE_BUNDLE"
    assert "do-not-leak" not in proc.stderr
    assert proc.stdout == ""


@pytest.mark.parametrize("use_stdin,nested", [(False, False), (True, True)])
def test_cli_rejects_duplicate_keys_in_otherwise_valid_bundle(
    tmp_path: Path,
    use_stdin: bool,
    nested: bool,
) -> None:
    secret = "duplicate-source-secret-must-not-leak"
    payload = _duplicate_payload(secret, nested=nested)
    assert evaluate_bundle(json.loads(payload))["packet"]["recommended_option_id"]

    if use_stdin:
        input_path = "-"
        stdin_payload = payload
    else:
        path = tmp_path / "duplicate-valid.json"
        path.write_text(payload, encoding="utf-8")
        input_path = str(path)
        stdin_payload = None

    proc = subprocess.run(
        [
            sys.executable,
            str(_ROOT / "scripts" / "chairman_cognition_compose.py"),
            input_path,
        ],
        cwd=_ROOT,
        text=True,
        input=stdin_payload,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert json.loads(proc.stderr) == {
        "error": "INVALID_SOURCE_BUNDLE",
        "schema": "mastermind.chairman_cognition_source_error.v1",
    }
    assert secret not in proc.stderr


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


def test_plan_freezes_content_identity_and_no_rebuild_law():
    plan = _PLAN.read_text(encoding="utf-8")
    for marker in (
        "source_blob_sha",
        "source_records_digest",
        "payload_digest",
        "mutated local payload",
        "must cite both",
        "trusted source adapter",
        "model-authored or arbitrary local JSON",
        "execution_authority_granted=false",
        "no second Agent OS parser",
    ):
        assert marker in plan


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
