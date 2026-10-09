"""Synthetic boundary regression for reviewed existing membership-reader excerpts.

No data download, market-store access, cohort admission, trading or source mutation.
The captured functions are research fixtures, never an alternate production reader.
Full original modules are not imported: one initializes a separate TrialLedger.
"""
from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from types import FunctionType
from typing import Any

import pandas as pd

NATIVE_EXCERPT = '''def members_asof(mem: pd.DataFrame, t: pd.Timestamp) -> set:
    """PIT membership as-of t - excerpt's docstring normalized for this fixture."""
    t = pd.Timestamp(t)
    active = mem[(mem["start_date"] <= t) & (mem["end_date"].isna() | (mem["end_date"] > t))]
    return set(active["ticker"].unique())
'''
LEGACY_EXCERPT = '''def _eligible(membership: pd.DataFrame, d: pd.Timestamp) -> set:
    mask = (membership["start_date"] <= d) & (
        membership["end_date"].isna() | (membership["end_date"] >= d))
    return set(membership.loc[mask, "ticker"])
'''
PROVENANCE = {
    "native": {"repository": "mastermindx-market-intelligence/Mastermind",
               "commit": "a29161fa0a44cca9927afe042b5f7ea25aae1736",
               "path": "loop/single_name_panel.py", "function": "members_asof",
               "full_file_git_blob": "9967191353f96dd8feebf6f16941e47f2a69ed15"},
    "legacy": {"repository": "mastermindx-market-intelligence/macro",
               "commit": "5600bb63b27978031769eb428911fe9b46572a92",
               "path": "scripts/s13_reversal_phase0.py", "function": "_eligible",
               "full_file_git_blob": "dadcb0043ba5ed380f4984ea4e2bf360a1ebd72f"},
    "upstream": {"repository": "fja05680/sp500",
                 "commit": "a2430f2af0c79ddf0748e91de11bdeb1616ab5a7",
                 "path": "PIT to Ticker Delta.ipynb", "code_cell_execution_count": 3,
                 "full_file_git_blob": "50304417f01ec3f711445c4f32ef1a53291c9598"},
}


def executable_ast(source: str, name: str) -> ast.Module:
    """Select one function, strip only its docstring, and reject ambiguous input."""
    tree = ast.parse(source)
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise ValueError("exactly one named function required")
    function = found[0]
    if function.decorator_list or function.args.defaults or function.args.kw_defaults:
        raise ValueError("fixture may not execute decorators or defaults")
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)
            and isinstance(function.body[0].value.value, str)):
        function.body = function.body[1:]
    return ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))


def ast_digest(source: str, name: str) -> str:
    dump = ast.dump(executable_ast(source, name), include_attributes=False)
    return hashlib.sha256(dump.encode()).hexdigest()


def fixture_readers() -> tuple[FunctionType, FunctionType]:
    output = []
    for text, name in ((NATIVE_EXCERPT, "members_asof"), (LEGACY_EXCERPT, "_eligible")):
        namespace = {"pd": pd, "set": set}
        exec(compile(executable_ast(text, name), "<reviewed-research-fixture>", "exec"), namespace)
        output.append(namespace[name])
    return tuple(output)


def sample_membership() -> pd.DataFrame:
    # In the upstream converter, end_date is the first snapshot where absent.
    frame = pd.DataFrame([
        {"ticker": "SYNTHETIC_A", "start_date": "2020-01-02", "end_date": "2020-01-06"},
        {"ticker": "SYNTHETIC_A", "start_date": "2020-01-09", "end_date": None},
        {"ticker": "SYNTHETIC_B", "start_date": "2020-01-02", "end_date": None},
    ])
    for column in ("start_date", "end_date"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def report() -> dict[str, Any]:
    correct, legacy = fixture_readers()
    frame = sample_membership()
    expected = {
        "2020-01-01": set(),
        "2020-01-02": {"SYNTHETIC_A", "SYNTHETIC_B"},
        "2020-01-05": {"SYNTHETIC_A", "SYNTHETIC_B"},
        "2020-01-06": {"SYNTHETIC_B"},
        "2020-01-07": {"SYNTHETIC_B"},
        "2020-01-09": {"SYNTHETIC_A", "SYNTHETIC_B"},
        "2020-01-10": {"SYNTHETIC_A", "SYNTHETIC_B"},
    }
    cases = []
    for when, want in expected.items():
        actual, old = correct(frame, pd.Timestamp(when)), legacy(frame, pd.Timestamp(when))
        cases.append({"date": when, "expected": sorted(want), "native": sorted(actual),
                      "legacy": sorted(old), "native_pass": actual == want,
                      "legacy_pass": old == want})
    return {
        "schema": "market_experience.membership_boundary_regression.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "SYNTHETIC_REVIEWED_FUNCTION_EXCERPTS_NOT_CORPUS_COMPARISON",
        "full_original_modules_executed": False,
        "native_docstring_normalized": True,
        "native_executable_ast_sha256": ast_digest(NATIVE_EXCERPT, "members_asof"),
        "legacy_executable_ast_sha256": ast_digest(LEGACY_EXCERPT, "_eligible"),
        "provenance": PROVENANCE, "cases": cases,
        "native_pass_count": sum(c["native_pass"] for c in cases),
        "legacy_failure_count": sum(not c["legacy_pass"] for c in cases),
        "source_comparison_completed": False, "stock_pilot_admitted": False,
        "production_data_admitted": 0, "model_calls": 0, "provider_spend_usd": 0,
        "limitations": ["No real membership corpus comparison", "No historical identity join",
                        "No rights admission", "No forecast or production-impact measurement"],
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
