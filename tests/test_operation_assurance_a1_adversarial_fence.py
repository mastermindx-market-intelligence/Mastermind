"""tests.test_operation_assurance_a1_adversarial_fence — remaining required falsifiers.

Rounds out the mutation/falsifier corpus required by
docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md
Section 10 and docs/superpowers/plans/2026-08-30-operation-assurance-core.md
Section 18 Task 8 that are not already pinned by the per-layer test files:
internal checker exception handling (never a healthy default, never a
partial report), no-side-effect coverage across all three pure modules,
execution-order (never sorted) traces, canonical shortest-prefix tie-break,
and the structural impossibility of ``REPORT_ONLY_PROCEED``.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

import control_plane.operation_assurance_checker as checker_mod
from control_plane.operation_assurance_checker import CheckerInternalError, run_checker
from control_plane.operation_assurance_model import parse_model_text
from control_plane.operation_assurance_report import ADMISSION_RECOMMENDATIONS
from tests.operation_assurance_fixture_lib import clone, dumps, effect, guard, minimal_model, transition

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "operation_assurance.py"
GENERATED_AT = "2026-08-30T12:00:00Z"

_FORBIDDEN_IMPORTS = {"socket", "subprocess", "sqlite3", "urllib", "requests", "http.client"}


def _forbidden_imports_in(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names & _FORBIDDEN_IMPORTS


@pytest.mark.parametrize(
    "relpath",
    [
        "control_plane/operation_assurance_model.py",
        "control_plane/operation_assurance_report.py",
        "control_plane/operation_assurance_checker.py",
    ],
)
def test_pure_modules_import_no_forbidden_io(relpath: str) -> None:
    assert not _forbidden_imports_in(ROOT / relpath), relpath


def test_pure_modules_have_no_filesystem_write_calls() -> None:
    for relpath in (
        "control_plane/operation_assurance_model.py",
        "control_plane/operation_assurance_report.py",
        "control_plane/operation_assurance_checker.py",
    ):
        src = (ROOT / relpath).read_text()
        assert "open(" not in src, relpath
        assert ".write(" not in src, relpath


def test_import_of_core_modules_has_zero_side_effect() -> None:
    # A bare (re-)import must not touch the network, filesystem, or a clock.
    # Reloading in-process would rebind class identities (e.g.
    # CheckerInternalError) out from under every other test's `import`
    # statement in this session, so the reload happens in an isolated
    # subprocess instead of via importlib.reload() here.
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import control_plane.operation_assurance_model\n"
            "import control_plane.operation_assurance_report\n"
            "import control_plane.operation_assurance_checker\n",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""


# ---------------------------------------------------------------------------
# Internal checker exception: never proof, never a healthy default
# ---------------------------------------------------------------------------


def test_internal_exception_never_becomes_proof(monkeypatch) -> None:
    def _boom(model):
        raise RuntimeError("simulated internal fault")

    monkeypatch.setattr(checker_mod, "explore", _boom)
    model = parse_model_text(dumps(minimal_model()))
    with pytest.raises(CheckerInternalError):
        run_checker(model, generated_at=GENERATED_AT)


def test_internal_exception_via_cli_exits_three_with_bounded_stderr(tmp_path, monkeypatch) -> None:
    model_path = tmp_path / "model.json"
    model_path.write_text(dumps(minimal_model()))
    # sabotage the checker module at import time via a tiny wrapper script so
    # the fault happens inside the real subprocess, proving the CLI's own
    # exception boundary (not just the library function).
    saboteur = tmp_path / "run_cli_with_fault.py"
    saboteur.write_text(
        "import sys, pathlib\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import control_plane.operation_assurance_checker as c\n"
        "def _boom(model):\n"
        "    raise RuntimeError('simulated internal fault')\n"
        "c.explore = _boom\n"
        f"sys.argv = ['operation-assurance', {str(model_path)!r}]\n"
        f"spec = __import__('importlib.util', fromlist=['spec_from_file_location']).spec_from_file_location('cli_main', {str(CLI)!r})\n"
        "mod = __import__('importlib.util', fromlist=['module_from_spec']).module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "sys.exit(mod.main(['" + str(model_path) + "']))\n"
    )
    proc = subprocess.run([sys.executable, str(saboteur)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 3
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    assert proc.stderr.strip() != ""


# ---------------------------------------------------------------------------
# REPORT_ONLY_PROCEED is structurally impossible
# ---------------------------------------------------------------------------


def test_report_only_proceed_is_not_in_the_closed_a1_recommendation_set() -> None:
    assert "REPORT_ONLY_PROCEED" not in ADMISSION_RECOMMENDATIONS


@pytest.mark.parametrize(
    "model_mutator",
    [
        lambda d: d,  # safe
        lambda d: {**d, "transitions": d["transitions"] + [transition("reopen", [guard("phase", "EQ", "DONE")], [effect("phase", "START")])]},  # unsafe
    ],
)
def test_admission_recommendation_never_proceed(model_mutator) -> None:
    d = model_mutator(clone(minimal_model()))
    model = parse_model_text(dumps(d))
    report = run_checker(model, generated_at=GENERATED_AT)
    assert report.admission_recommendation != "REPORT_ONLY_PROCEED"
    assert report.admission_recommendation in ADMISSION_RECOMMENDATIONS


# ---------------------------------------------------------------------------
# Trace order is execution order, never re-sorted
# ---------------------------------------------------------------------------


def test_shortest_prefix_preserves_execution_order_not_alphabetical() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "MID", "BAD"]
    d["transitions"] = [
        transition("zzz_step_one", [guard("phase", "EQ", "START")], [effect("phase", "MID")], required_reachable=True),
        transition("aaa_step_two", [guard("phase", "EQ", "MID")], [effect("phase", "BAD")], required_reachable=True),
    ]
    from tests.operation_assurance_fixture_lib import state_forbidden

    d["safety_properties"] = [state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")])]
    model = parse_model_text(dumps(d))
    report = run_checker(model, generated_at=GENERATED_AT)
    cx = [c for c in report.counterexamples if c.property_id == "NO_BAD"][0]
    # execution order is zzz_step_one THEN aaa_step_two; alphabetical order
    # would be the reverse.
    assert cx.shortest_prefix == ("zzz_step_one", "aaa_step_two")
    assert cx.shortest_prefix != tuple(sorted(cx.shortest_prefix))


# ---------------------------------------------------------------------------
# Canonical shortest-prefix tie-break: two equally-short violating paths
# ---------------------------------------------------------------------------


def test_canonical_tie_break_picks_lexically_smallest_transition_sequence() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "BAD"]
    d["transitions"] = [
        transition("via_b_path", [guard("phase", "EQ", "START")], [effect("phase", "BAD")]),
        transition("via_a_path", [guard("phase", "EQ", "START")], [effect("phase", "BAD")]),
    ]
    from tests.operation_assurance_fixture_lib import state_forbidden

    d["safety_properties"] = [state_forbidden("NO_BAD", [guard("phase", "EQ", "BAD")])]
    model = parse_model_text(dumps(d))
    report = run_checker(model, generated_at=GENERATED_AT)
    cx = [c for c in report.counterexamples if c.property_id == "NO_BAD"][0]
    # both transitions reach the violating state in exactly one step; the
    # canonical (lexically smallest) choice must win, not discovery order.
    assert cx.shortest_prefix == ("via_a_path",)


# ---------------------------------------------------------------------------
# Bounded result via the real CLI (exit 0, never proof)
# ---------------------------------------------------------------------------


def test_bounded_model_via_cli_exits_zero_and_is_never_proof(tmp_path) -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "MID", "DONE"]
    d["transitions"] = [
        transition("advance", [guard("phase", "EQ", "START")], [effect("phase", "MID")], required_reachable=True),
        transition("finish", [guard("phase", "EQ", "MID")], [effect("phase", "DONE")], required_reachable=True),
    ]
    d["exploration_limits"] = {"max_states": 2, "max_depth": 1000}
    model_path = tmp_path / "bounded.json"
    model_path.write_text(dumps(d))
    proc = subprocess.run(
        [sys.executable, str(CLI), str(model_path)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["model_analysis_verdict"] != "PROVEN_WITHIN_FINITE_MODEL"
    assert report["exploration_receipt"]["base_graph_complete"] is False
    assert report["exploration_receipt"]["state_limit_reached"] is True
    # at least one analysis product names the exact limit reason
    assert any(p["limit_reason"] == "STATE_LIMIT_REACHED" for p in report["exploration_receipt"]["analysis_products"])
