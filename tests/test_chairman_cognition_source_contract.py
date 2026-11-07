from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
import yaml

from control_plane.chairman_cognition import (
    ENVELOPE_SCHEMA,
    INPUT_SCHEMA,
    ChairmanCognitionError,
    evaluate_document,
)
from scripts import chairman_cognition as cli

_ROOT = Path(__file__).resolve().parents[1]
_LAW = _ROOT / "docs" / "EXECUTIVE_CHAIRMAN_COGNITION_LAW.md"
_SPEC = (
    _ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-chairman-cognition-loop-design.md"
)
_PLAN = (
    _ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-chairman-cognition-loop-accelerated-program.md"
)
_MODULE = _ROOT / "control_plane" / "chairman_cognition.py"
_CLI = _ROOT / "scripts" / "chairman_cognition.py"
_STATE = _ROOT / "config" / "strategic_state.yml"

_CURRENT_CONSTRAINTS = {
    "autonomous_production_deploy": "prohibited",
    "autonomous_live_capital_execution": "prohibited",
    "duplicate_control_planes": "prohibited",
    "marketing_org_expansion_before_distribution_proof": "prohibited",
    "new_feature_expansion": "constrained",
    "unbounded_autonomous_strategic_modification": "prohibited",
}


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


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


def _set_binding(receipt: dict, label: str, digest: str) -> None:
    prefix = f"{label}:"
    fields = [
        field for field in receipt["revision"].split(";") if not field.startswith(prefix)
    ]
    receipt["revision"] = ";".join([*fields, f"{label}:{digest}"])


def _set_binding_tokens(receipt: dict, label: str, tokens: set[str]) -> None:
    prefix = f"{label}:"
    fields = [
        field for field in receipt["revision"].split(";") if not field.startswith(prefix)
    ]
    receipt["revision"] = ";".join([*fields, *sorted(tokens)])


def _bind_document(document: dict) -> dict:
    receipts = {item["source_ref"]: item for item in document["source_receipts"]}
    strategy_ref = document["strategic_constraints_source_ref"]
    _set_binding(
        receipts[strategy_ref],
        "constraints-sha256",
        _digest(document["strategic_constraints"]),
    )
    envelope = document["delegation_envelope"]
    if envelope is not None:
        envelope_digest = _digest(_envelope_payload(envelope))
        for ref in envelope["authority_source_refs"]:
            if ref in receipts:
                _set_binding(receipts[ref], "envelope-sha256", envelope_digest)
    bindings: dict[str, set[str]] = {}
    for option in document["options"]:
        ref = option["classification_source_ref"]
        bindings.setdefault(ref, set()).add(
            f"classification-sha256:{_digest(_classification_payload(option))}"
        )
    for ref, tokens in bindings.items():
        _set_binding_tokens(receipts[ref], "classification-sha256", tokens)
    return document


def _text(path: Path) -> str:
    assert path.is_file(), f"missing Chairman Cognition source: {path}"
    return path.read_text(encoding="utf-8")


def _valid_document() -> dict:
    document = {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "source_receipts": [
            {
                "source_ref": "SRC-STRATEGY",
                "owner": "STRATEGIC_STATE",
                "revision": "strategy-current",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
            {
                "source_ref": "SRC-CHAIRMAN",
                "owner": "CHAIRMAN_DIRECTIVE",
                "revision": "conversation:2026-08-30",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
        ],
        "strategic_constraints_source_ref": "SRC-STRATEGY",
        "strategic_constraints": copy.deepcopy(_CURRENT_CONSTRAINTS),
        "delegation_envelope": None,
        "options": [
            {
                "option_id": "OPT-DUPLICATE",
                "title": "Hold while validating input integrity",
                "action": "PORTFOLIO_HOLD",
                "reversibility": "READ_ONLY",
                "source_refs": ["SRC-CHAIRMAN"],
                "scope_refs": [],
                "effect_state": "NONE",
                "operation_key": None,
                "carrier_state": "NOT_APPLICABLE",
                "carrier_ref": None,
                "expected_head_sha": None,
                "repositories": [],
                "paths": [],
                "budget_units": 0,
                "active_children_after": 0,
                "creates_duplicate_control_plane": False,
                "stop_condition": None,
                "rollback_plan": None,
                "falsifier": None,
                "classification_source_ref": "SRC-CHAIRMAN",
                "change_classes": ["RESEARCH"],
                "affected_departments": ["executive"],
                "benefits": {
                    "strategic_leverage": 50,
                    "dependency_unlock": 50,
                    "learning_value": 50,
                    "chairman_load_reduction": 50,
                    "user_or_machine_value": 50,
                },
                "costs": {
                    "time_to_evidence": 20,
                    "execution_cost": 20,
                    "coordination_risk": 20,
                    "irreversibility_risk": 20,
                    "scarce_cognition_cost": 20,
                },
            }
        ],
    }
    return _bind_document(document)


def _duplicate_payload(secret: str, *, nested: bool) -> str:
    valid = json.dumps(_valid_document(), separators=(",", ":"))
    if nested:
        target = '"option_id":"OPT-DUPLICATE"'
        replacement = f'"option_id":"{secret}","option_id":"OPT-DUPLICATE"'
        assert target in valid
        return valid.replace(target, replacement, 1)
    return f'{{"schema":"{secret}",' + valid[1:]


def test_source_law_freezes_one_office_two_modes_and_no_duplicate_owner():
    law = _text(_LAW)
    for marker in (
        "SOL:META-CEO:MASTERMIND",
        "CHAIRMAN_COGNITION",
        "CEO_EXECUTION",
        "does **not** create a second `META_CHAIRMAN`",
        "execution_authority_granted=false",
        "SUPERVISED_LIVE_CANARY",
        "PORTFOLIO_HOLD",
        "PROGRAM_START",
        "PROGRAM_RETIRE",
        "EFFECT_UNKNOWN_RECONCILE_FIRST",
        "EFFECT_ALREADY_APPLIED",
        "NEW_CHILD_CARRIER_REQUIRED",
        "DUPLICATE_CONTROL_PLANE_REFUSED",
        "strategic_constraints_source_ref",
        "classification_source_ref",
        "constraints-sha256",
        "classification-sha256",
        "envelope-sha256",
        "constraint_results",
        "blocking_constraint",
    ):
        assert marker in law


def test_architecture_preserves_canonical_owners_and_accelerated_live_canary():
    spec = _text(_SPEC)
    for marker in (
        "Executive OS",
        "Agent OS",
        "GitHub",
        "Linear",
        "RuntimeBinding",
        "Wake",
        "Capacity",
        "Executive Steward",
        "Executive Attention Frontier",
        "Runtime Observability",
        "Operation Assurance",
        "no mandatory multi-week shadow",
        "one supervised live reversible canary",
        "canonical affected-scope references",
        "allowed exact-carrier prefixes",
        "known-applied effect",
        "explicit `NEW_CHILD` carrier state",
        "No `chairman_brain.db`",
        "NEW_FEATURE",
        "ORGANIZATIONAL_EXPANSION",
        "future constraint",
        "content-bound",
        "classification source",
        "envelope-sha256",
    ):
        assert marker in spec


def test_program_has_real_vertical_and_completion_not_docs():
    plan = _text(_PLAN)
    for marker in (
        "control_plane/chairman_cognition.py",
        "scripts/chairman_cognition.py",
        "tests/test_chairman_cognition.py",
        "tests/test_chairman_cognition_hardening.py",
        "CCL-A2",
        "CCL-A3",
        "CCL-A4",
        "CCL-A5",
        "CCL-A6",
        "One closed canary",
        "zero routine",
        "R2",
        "all six current constraints",
        "constraint map",
        "classification",
        "envelope-sha256",
    ):
        assert marker in plan


def test_strategic_state_records_current_chairman_cognition_objective():
    state = yaml.safe_load(_text(_STATE))
    assert str(state["meta"]["as_of"]) == "2026-08-30"
    objectives = {item["id"]: item for item in state["p0"]}
    objective = objectives["CHAIRMAN_COGNITION_AUTONOMY"]
    assert objective["department"] == "executive"
    assert objective["status"] == "active"
    assert "Chairman-engineering" in objective["objective"]
    assert "first_chairman_cognition_supervised_live_cycle" in state["review_triggers"]
    assert state["constraints"] == _CURRENT_CONSTRAINTS
    assert sum(float(v) for v in state["resource_policy"].values()) == 1.0


def test_pure_core_imports_no_runtime_io_network_or_connector_owner():
    tree = ast.parse(_text(_MODULE))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    forbidden_fragments = (
        "sqlite",
        "subprocess",
        "socket",
        "urllib",
        "httpx",
        "requests",
        "worker_runtime",
        "executive_runtime",
        "executive_service",
        "capacity",
        "runtime_binding",
        "session_targets",
        "slack",
        "linear",
        "github",
        "agentos",
        "mcp",
    )
    offenders = sorted(
        module
        for module in imported
        if any(fragment in module.lower() for fragment in forbidden_fragments)
    )
    assert not offenders, offenders


def test_cli_is_a_bounded_json_projection_not_an_actuator():
    tree = ast.parse(_text(_CLI))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "write_text" not in calls
    assert "unlink" not in calls
    assert "replace" not in calls
    assert "system" not in calls


@pytest.mark.parametrize(
    "use_stdin,nested",
    [(False, False), (True, True)],
)
def test_cli_rejects_duplicate_keys_that_would_otherwise_form_valid_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_stdin: bool,
    nested: bool,
) -> None:
    secret = "duplicate-secret-must-not-leak"
    payload = _duplicate_payload(secret, nested=nested)

    permissive_document = json.loads(payload)
    assert evaluate_document(permissive_document)["recommended_option_id"] == "OPT-DUPLICATE"

    if use_stdin:
        monkeypatch.setattr(cli.sys, "stdin", io.StringIO(payload))
        path = "-"
    else:
        input_path = tmp_path / "duplicate-valid.json"
        input_path.write_text(payload, encoding="utf-8")
        path = str(input_path)

    assert cli.main([path]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error == {
        "error": "INVALID_INPUT",
        "schema": "mastermind.chairman_cognition_error.v1",
    }
    assert secret not in captured.err


def _r2_envelope(*, mode: str = "SUPERVISED_LIVE_CANARY") -> dict:
    return {
        "schema": ENVELOPE_SCHEMA,
        "envelope_id": "ENV-R2-001",
        "authority_source_refs": ["SRC-CHAIRMAN"],
        "mode": mode,
        "allowed_actions": [
            "SOURCE_BRANCH_WRITE",
            "PRODUCTION_DEPLOY",
            "LIVE_CAPITAL_EXECUTION",
            "ORGANIZATIONAL_RESTRUCTURE",
            "REVERSIBLE_RUNTIME_CANARY",
        ],
        "allowed_reversibility": ["REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": ["control_plane"]
        },
        "allowed_scope_prefixes": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "allowed_carrier_prefixes": ["github:Mastermind:", "agentos:"],
        "max_budget_units": 10,
        "max_active_children": 2,
        "require_exact_carrier": True,
        "expires_at": "2026-09-30T00:00:00Z",
    }


def _r2_option(**changes) -> dict:
    option = {
        "option_id": "OPT-R2",
        "title": "Complete one existing Chairman cognition capability",
        "action": "SOURCE_BRANCH_WRITE",
        "reversibility": "REVERSIBLE",
        "source_refs": ["SRC-CHAIRMAN", "SRC-GITHUB"],
        "scope_refs": ["WS:CHAIRMAN-CONTROL-ROOM"],
        "effect_state": "NONE",
        "operation_key": "chairman-cognition-r2-test-001",
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": "github:Mastermind:branch:ccl-r2",
        "expected_head_sha": "a" * 40,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["control_plane/chairman_cognition.py"],
        "budget_units": 1,
        "active_children_after": 1,
        "creates_duplicate_control_plane": False,
        "stop_condition": "Stop after one exact reviewed head.",
        "rollback_plan": "Abandon the unmerged branch.",
        "falsifier": "Any ignored current constraint is failure.",
        "classification_source_ref": "SRC-GITHUB",
        "change_classes": ["EXISTING_CAPABILITY_COMPLETION"],
        "affected_departments": ["executive"],
        "benefits": {
            "strategic_leverage": 70,
            "dependency_unlock": 70,
            "learning_value": 70,
            "chairman_load_reduction": 70,
            "user_or_machine_value": 70,
        },
        "costs": {
            "time_to_evidence": 20,
            "execution_cost": 20,
            "coordination_risk": 20,
            "irreversibility_risk": 5,
            "scarce_cognition_cost": 20,
        },
    }
    option.update(changes)
    return option


def _r2_document(option: dict | None = None, *, envelope: dict | None = None) -> dict:
    document = {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-08-30T16:00:00Z",
        "source_receipts": [
            {
                "source_ref": "SRC-STRATEGY",
                "owner": "STRATEGIC_STATE",
                "revision": "strategy-current",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
            {
                "source_ref": "SRC-CHAIRMAN",
                "owner": "CHAIRMAN_DIRECTIVE",
                "revision": "conversation:2026-08-30",
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
            {
                "source_ref": "SRC-GITHUB",
                "owner": "GITHUB",
                "revision": "a" * 40,
                "state": "CURRENT",
                "load_bearing": True,
                "observed_at": "2026-08-30T16:00:00Z",
            },
        ],
        "strategic_constraints_source_ref": "SRC-STRATEGY",
        "strategic_constraints": copy.deepcopy(_CURRENT_CONSTRAINTS),
        "delegation_envelope": _r2_envelope() if envelope is None else envelope,
        "options": [option or _r2_option()],
    }
    return _bind_document(document)


def _r2_result(document: dict) -> dict:
    return evaluate_document(document)["adjudications"][0]


def test_r2_emits_complete_sorted_constraint_results_and_exact_blocker() -> None:
    packet = evaluate_document(_r2_document())
    item = packet["adjudications"][0]
    ids = [result["constraint_id"] for result in item["constraint_results"]]
    assert ids == sorted(_CURRENT_CONSTRAINTS)
    assert item["blocking_constraint"] is None
    assert item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


@pytest.mark.parametrize("constraint_id", sorted(_CURRENT_CONSTRAINTS))
def test_r2_each_current_constraint_is_required(constraint_id: str) -> None:
    document = _r2_document()
    del document["strategic_constraints"][constraint_id]
    with pytest.raises(ChairmanCognitionError, match="missing load-bearing strategic constraint"):
        evaluate_document(document)


def test_r2_new_feature_requires_chairman() -> None:
    item = _r2_result(
        _r2_document(_r2_option(change_classes=["NEW_FEATURE"]))
    )
    assert item["disposition"] == "CHAIRMAN_REQUIRED"
    assert item["blocking_constraint"] == "new_feature_expansion"


def test_r2_unknown_class_fails_closed_against_prohibited_expansion() -> None:
    item = _r2_result(
        _r2_document(_r2_option(change_classes=["UNKNOWN"]))
    )
    assert item["disposition"] == "REFUSED"
    assert item["blocking_constraint"] == (
        "marketing_org_expansion_before_distribution_proof"
    )


def test_r2_marketing_expansion_and_missing_department_are_refused() -> None:
    marketing = _r2_option(
        action="ORGANIZATIONAL_RESTRUCTURE",
        carrier_ref="agentos:WS:CHAIRMAN-CONTROL-ROOM",
        repositories=[],
        paths=[],
        expected_head_sha=None,
        change_classes=["ORGANIZATIONAL_EXPANSION"],
        affected_departments=["marketing"],
    )
    item = _r2_result(_r2_document(marketing))
    assert item["disposition"] == "REFUSED"
    assert item["blocking_constraint"] == (
        "marketing_org_expansion_before_distribution_proof"
    )

    missing_department = copy.deepcopy(marketing)
    missing_department["affected_departments"] = []
    with pytest.raises(ChairmanCognitionError, match="affected department"):
        evaluate_document(_r2_document(missing_department))


def test_r2_safe_completion_and_runtime_canary_do_not_trigger_expansion_rules() -> None:
    completion = _r2_result(_r2_document())
    assert completion["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"

    runtime = _r2_option(
        action="REVERSIBLE_RUNTIME_CANARY",
        repositories=[],
        paths=[],
        expected_head_sha=None,
        change_classes=["RUNTIME_CANARY"],
    )
    item = _r2_result(_r2_document(runtime))
    by_id = {result["constraint_id"]: result for result in item["constraint_results"]}
    assert by_id["new_feature_expansion"]["applicability"] == "DOES_NOT_APPLY"
    assert by_id["marketing_org_expansion_before_distribution_proof"][
        "applicability"
    ] == "DOES_NOT_APPLY"
    assert item["disposition"] == "ELIGIBLE_WITHIN_DELEGATION"


def test_r2_future_unknown_selector_never_silently_disappears() -> None:
    for level, disposition in (
        ("prohibited", "REFUSED"),
        ("constrained", "CHAIRMAN_REQUIRED"),
        ("permitted", "ELIGIBLE_WITHIN_DELEGATION"),
    ):
        document = _r2_document()
        document["strategic_constraints"]["future_constraint"] = level
        _bind_document(document)
        item = _r2_result(document)
        result = next(
            row
            for row in item["constraint_results"]
            if row["constraint_id"] == "future_constraint"
        )
        assert result["applicability"] == "UNKNOWN"
        assert item["disposition"] == disposition


def test_r2_strategy_source_is_exact_current_load_bearing_owner() -> None:
    for mutation in (
        {"owner": "GITHUB"},
        {"state": "STALE"},
        {"load_bearing": False},
    ):
        document = _r2_document()
        strategy = document["source_receipts"][0]
        strategy.update(mutation)
        with pytest.raises(ChairmanCognitionError):
            evaluate_document(document)


def test_r2_constraint_map_is_content_bound_to_strategy_receipt() -> None:
    document = _r2_document()
    document["strategic_constraints"]["new_feature_expansion"] = "permitted"
    with pytest.raises(ChairmanCognitionError, match="not content-bound"):
        evaluate_document(document)


def test_r2_requires_exactly_one_load_bearing_strategy_source() -> None:
    document = _r2_document()
    document["source_receipts"].append(
        {
            "source_ref": "SRC-STRATEGY-OTHER",
            "owner": "STRATEGIC_STATE",
            "revision": document["source_receipts"][0]["revision"],
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": "2026-08-30T16:00:00Z",
        }
    )
    with pytest.raises(ChairmanCognitionError, match="exactly one"):
        evaluate_document(document)


def test_r2_classification_is_content_bound_and_owner_limited() -> None:
    document = _r2_document()
    document["options"][0]["change_classes"] = ["NEW_FEATURE"]
    with pytest.raises(ChairmanCognitionError, match="not content-bound"):
        evaluate_document(document)

    document = _r2_document()
    document["source_receipts"][2]["owner"] = "SLACK"
    with pytest.raises(ChairmanCognitionError, match="owner is not allowed"):
        evaluate_document(document)


def test_r2_non_load_bearing_context_cannot_establish_or_cure_current() -> None:
    document = _r2_document()
    github = document["source_receipts"][2]
    github["load_bearing"] = False
    document["options"][0]["source_refs"] = ["SRC-GITHUB"]
    with pytest.raises(ChairmanCognitionError, match="load-bearing"):
        evaluate_document(document)

    document = _r2_document()
    document["source_receipts"][2]["state"] = "STALE"
    document["source_receipts"].append(
        {
            "source_ref": "SRC-LINEAR",
            "owner": "LINEAR",
            "revision": "projection-current",
            "state": "CURRENT",
            "load_bearing": False,
            "observed_at": "2026-08-30T16:00:00Z",
        }
    )
    document["options"][0]["source_refs"].append("SRC-LINEAR")
    item = _r2_result(document)
    assert item["source_state"] == "STALE"
    assert item["disposition"] == "REFUSED"


def test_r2_classification_cannot_bypass_constitutional_constraints() -> None:
    cases = (
        ("PRODUCTION_DEPLOY", {}, "autonomous_production_deploy"),
        ("LIVE_CAPITAL_EXECUTION", {}, "autonomous_live_capital_execution"),
        (
            "ORGANIZATIONAL_RESTRUCTURE",
            {"creates_duplicate_control_plane": True},
            "duplicate_control_planes",
        ),
    )
    for action, extra, blocker in cases:
        option = _r2_option(
            action=action,
            change_classes=["MAINTENANCE_REPAIR"],
            **extra,
        )
        if action == "ORGANIZATIONAL_RESTRUCTURE":
            option.update(
                carrier_ref="agentos:WS:CHAIRMAN-CONTROL-ROOM",
                repositories=[],
                paths=[],
                expected_head_sha=None,
            )
        item = _r2_result(_r2_document(option))
        assert item["disposition"] == "REFUSED"
        assert item["blocking_constraint"] == blocker


def test_r2_source_branch_write_requires_expected_head() -> None:
    item = _r2_result(_r2_document(_r2_option(expected_head_sha=None)))
    assert item["disposition"] == "REFUSED"
    assert item["reason"] == "EXPECTED_HEAD_REQUIRED"


def test_r2_constraint_output_and_digest_are_permutation_stable() -> None:
    first = evaluate_document(_r2_document())
    document = _r2_document()
    document["strategic_constraints"] = dict(
        reversed(list(document["strategic_constraints"].items()))
    )
    second = evaluate_document(document)
    assert first == second


@pytest.mark.parametrize(
    "mutation",
    [
        "envelope_id",
        "mode",
        "allowed_actions",
        "allowed_reversibility",
        "allowed_repositories",
        "allowed_path_prefixes",
        "allowed_scope_prefixes",
        "allowed_carrier_prefixes",
        "max_budget_units",
        "max_active_children",
        "expires_at",
    ],
)
def test_r3_every_authority_bearing_envelope_field_is_content_bound(
    mutation: str,
) -> None:
    document = _r2_document()
    envelope = document["delegation_envelope"]
    if mutation == "envelope_id":
        envelope[mutation] = "ENV-R3-MUTATED"
    elif mutation == "mode":
        envelope[mutation] = "BOUNDED_AUTONOMOUS"
    elif mutation == "allowed_actions":
        envelope[mutation].append("PROGRAM_PAUSE")
    elif mutation == "allowed_reversibility":
        envelope[mutation].append("COSTLY_REVERSIBLE")
    elif mutation == "allowed_repositories":
        envelope[mutation].append("mastermindx-market-intelligence/macro")
    elif mutation == "allowed_path_prefixes":
        envelope[mutation]["mastermindx-market-intelligence/Mastermind"].append(
            "docs"
        )
    elif mutation == "allowed_scope_prefixes":
        envelope[mutation].append("WS:OTHER")
    elif mutation == "allowed_carrier_prefixes":
        envelope[mutation].append("slack:")
    elif mutation == "max_budget_units":
        envelope[mutation] = 11
    elif mutation == "max_active_children":
        envelope[mutation] = 3
    elif mutation == "expires_at":
        envelope[mutation] = "2026-09-29T00:00:00Z"
    else:  # pragma: no cover - closed parameter set
        raise AssertionError(mutation)

    with pytest.raises(ChairmanCognitionError, match="delegation envelope is not content-bound"):
        evaluate_document(document)


def test_r3_authority_source_set_is_part_of_envelope_binding() -> None:
    document = _r2_document()
    document["source_receipts"].append(
        {
            "source_ref": "SRC-CHAIRMAN-2",
            "owner": "CHAIRMAN_DIRECTIVE",
            "revision": "conversation:2026-08-30:second",
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": "2026-08-30T16:00:00Z",
        }
    )
    document["delegation_envelope"]["authority_source_refs"].append(
        "SRC-CHAIRMAN-2"
    )
    with pytest.raises(ChairmanCognitionError, match="delegation envelope is not content-bound"):
        evaluate_document(document)


def test_r3_at_least_one_cited_chairman_receipt_must_bind_the_envelope() -> None:
    document = _r2_document()
    chairman = document["source_receipts"][1]
    chairman["revision"] = ";".join(
        field
        for field in chairman["revision"].split(";")
        if not field.startswith("envelope-sha256:")
    )
    with pytest.raises(ChairmanCognitionError, match="delegation envelope is not content-bound"):
        evaluate_document(document)


def test_r3_one_of_multiple_cited_chairman_receipts_may_carry_the_binding() -> None:
    document = _r2_document()
    document["source_receipts"].append(
        {
            "source_ref": "SRC-CHAIRMAN-2",
            "owner": "CHAIRMAN_DIRECTIVE",
            "revision": "conversation:2026-08-30:second",
            "state": "CURRENT",
            "load_bearing": True,
            "observed_at": "2026-08-30T16:00:00Z",
        }
    )
    document["delegation_envelope"]["authority_source_refs"].append(
        "SRC-CHAIRMAN-2"
    )
    _bind_document(document)
    second = document["source_receipts"][-1]
    second["revision"] = ";".join(
        field
        for field in second["revision"].split(";")
        if not field.startswith("envelope-sha256:")
    )
    packet = evaluate_document(document)
    assert packet["delegation_envelope"]["state"] == "ACCEPTED"


def test_r3_envelope_digest_is_semantic_permutation_stable() -> None:
    envelope = _r2_envelope()
    envelope["allowed_repositories"].append("mastermindx-market-intelligence/macro")
    envelope["allowed_path_prefixes"]["mastermindx-market-intelligence/macro"] = [
        "agentos",
        "src",
    ]
    envelope["allowed_actions"].append("PROGRAM_PAUSE")
    envelope["allowed_scope_prefixes"].append("WS:SECOND")
    envelope["allowed_carrier_prefixes"].append("executive:")

    first = evaluate_document(_r2_document(envelope=copy.deepcopy(envelope)))
    second_document = _r2_document(envelope=copy.deepcopy(envelope))
    second_envelope = second_document["delegation_envelope"]
    for field in (
        "authority_source_refs",
        "allowed_actions",
        "allowed_reversibility",
        "allowed_repositories",
        "allowed_scope_prefixes",
        "allowed_carrier_prefixes",
    ):
        second_envelope[field] = list(reversed(second_envelope[field]))
    second_envelope["allowed_path_prefixes"] = {
        repository: list(reversed(prefixes))
        for repository, prefixes in reversed(
            list(second_envelope["allowed_path_prefixes"].items())
        )
    }
    second = evaluate_document(second_document)
    assert first["delegation_envelope"]["digest"] == second["delegation_envelope"][
        "digest"
    ]
    assert first["delegation_envelope"]["digest"].startswith("sha256:")
