from __future__ import annotations

import ast
from pathlib import Path

import control_plane.executive_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "control_plane" / "executive_runtime.py"


def _root(creator: str = "ceo_intent", *, schema: str | None = None):
    return {
        "schema_version": schema or runtime._ORCHESTRATION_PROVENANCE_SCHEMA,
        "creator": creator,
        "source_id": "operation-key",
        "source_digest": "a" * 64,
        "command_id": "ceo-intent:operation-key",
        "job_id": "JOB-001",
        "parent_job_id": None,
        "root_job_id": "JOB-001",
        "role": "aggregation",
    }


def test_root_source_discriminator_is_closed_and_ceo_only_today() -> None:
    assert runtime._ORCHESTRATION_ROOT_CREATORS == frozenset({"ceo_intent"})
    root_source = {
        "schema_version": runtime._ORCHESTRATION_PROVENANCE_SOURCE_SCHEMA,
        "creator": "ceo_intent",
        "source_id": "operation-key",
        "source_digest": "a" * 64,
    }
    child_source = dict(root_source, creator="coo_cycle")
    assert runtime._orchestration_source_creator(
        root_source, role="aggregation"
    ) == "ceo_intent"
    assert runtime._orchestration_source_creator(
        child_source, role="work"
    ) == "coo_cycle"
    assert runtime._orchestration_source_creator(
        child_source, role="aggregation"
    ) is None
    assert runtime._orchestration_source_creator(
        root_source, role="work"
    ) is None
    assert runtime._orchestration_root_creator(_root()) == "ceo_intent"
    assert runtime._accepted_orchestration_root_provenance(_root()) is True
    assert runtime._ceo_intent_root_provenance(_root()) is True

    for creator in ("coo_cycle", "principal_orchestration", "", "ceo-intent"):
        assert runtime._orchestration_root_creator(_root(creator)) is None
        assert runtime._accepted_orchestration_root_provenance(_root(creator)) is False
        assert runtime._ceo_intent_root_provenance(_root(creator)) is False

    wrong = _root(schema="mastermind.executive_orchestration_provenance/v2")
    assert runtime._orchestration_root_creator(wrong) is None
    assert runtime._accepted_orchestration_root_provenance(wrong) is False
    assert runtime._accepted_orchestration_root_provenance(None) is False


def _functions_containing_literal(tree: ast.AST, literal: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(
            isinstance(child, ast.Constant) and child.value == literal
            for child in ast.walk(node)
        ):
            found.add(node.name)
    return found


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, name
    return matches[0]


def _called_names(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            result.add(child.func.id)
    return result


def test_generic_runtime_lifecycle_uses_one_root_source_discriminator() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    generic = {
        "_validate_exact_worker_target_selection",
        "_decode_orchestration_job_fields",
        "_assert_orchestration_lineage_for_create",
        "_assert_orchestration_dispatch_eligible",
        "_assert_orchestration_requeue_eligible",
        "create_cycle_planner",
        "create_interactive_operator",
        "admit_cycle_plan",
        "create_cycle_handoff",
    }
    for name in generic:
        calls = _called_names(_function(tree, name))
        assert "_accepted_orchestration_root_provenance" in calls, name

    # CEO identity stays explicit only where the existing path is actually
    # CEO-specific. New H4 principal-root work must extend the central root
    # discriminator rather than sprinkling "or principal" across generic paths.
    allowed_ceo_specific = {
        "_ceo_intent_root_provenance",
        "_finite_root_admission",
        "_finite_bound_effect",
        "create_v2_orchestration_root",
        "arm_finite_cycle",
        "_validated_capacity_source_root",
        "_remember",
    }
    assert _functions_containing_literal(tree, "ceo_intent") == allowed_ceo_specific


def test_source_and_stored_provenance_schema_names_are_centralized() -> None:
    assert runtime._ORCHESTRATION_PROVENANCE_SCHEMA == (
        "mastermind.executive_orchestration_provenance/v1"
    )
    assert runtime._ORCHESTRATION_PROVENANCE_SOURCE_SCHEMA == (
        "mastermind.executive_orchestration_provenance_source/v1"
    )
