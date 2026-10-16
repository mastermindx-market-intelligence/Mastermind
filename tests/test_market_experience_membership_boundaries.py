from pathlib import Path
import os

import pandas as pd
import pytest

from research.market_experience_membership_boundaries import (
    NATIVE_EXCERPT, LEGACY_EXCERPT, executable_ast, ast_digest,
    fixture_readers, sample_membership, report,
)


@pytest.mark.parametrize("when,expected", [
    ("2020-01-01", set()),
    ("2020-01-02", {"SYNTHETIC_A", "SYNTHETIC_B"}),
    ("2020-01-05", {"SYNTHETIC_A", "SYNTHETIC_B"}),
    ("2020-01-06", {"SYNTHETIC_B"}),
    ("2020-01-07", {"SYNTHETIC_B"}),
    ("2020-01-09", {"SYNTHETIC_A", "SYNTHETIC_B"}),
    ("2020-01-10", {"SYNTHETIC_A", "SYNTHETIC_B"}),
])
def test_native_boundary_fixture(when, expected):
    current, _ = fixture_readers()
    assert current(sample_membership(), pd.Timestamp(when)) == expected


def test_legacy_removal_day_disagreement_is_not_hidden():
    current, legacy = fixture_readers()
    when = pd.Timestamp("2020-01-06")
    frame = sample_membership()
    assert legacy(frame, when) - current(frame, when) == {"SYNTHETIC_A"}


def test_duplicate_rows_do_not_duplicate_members():
    current, _ = fixture_readers()
    frame = sample_membership()
    assert current(pd.concat([frame, frame]), "2020-01-02") == current(frame, "2020-01-02")


def test_method_does_not_claim_a_cohort_or_full_module_run():
    result = report()
    assert result["native_pass_count"] == 7
    assert result["legacy_failure_count"] == 1
    assert result["stock_pilot_admitted"] is False
    assert result["source_comparison_completed"] is False
    assert result["full_original_modules_executed"] is False
    assert result["production_data_admitted"] == result["model_calls"] == 0


def test_docstrings_do_not_change_executable_identity():
    changed = NATIVE_EXCERPT.replace("excerpt's docstring normalized for this fixture.", "other text")
    assert ast_digest(changed, "members_asof") == ast_digest(NATIVE_EXCERPT, "members_asof")
    assert ast_digest(NATIVE_EXCERPT, "members_asof") != ast_digest(LEGACY_EXCERPT, "_eligible")


@pytest.mark.parametrize("source", [
    "def other():\n    return set()\n",
    "def x():\n    pass\ndef x():\n    pass\n",
    "@unknown\ndef x():\n    pass\n",
    "def x(arg=unknown()):\n    pass\n",
])
def test_ambiguous_or_effectful_definition_rejected(source):
    with pytest.raises(ValueError):
        executable_ast(source, "x")


def test_repo_reader_semantics_match_when_full_repo_present():
    """CI checks the real file. Container excerpt-only run reports this as skipped."""
    path = Path(__file__).resolve().parents[1] / "loop" / "single_name_panel.py"
    if not path.exists() and os.environ.get("MMX_MEMBERSHIP_EXCERPT_ONLY_TESTS") == "1":
        pytest.skip("explicit excerpt-only run; repository-native AST comparison not executed")
    assert path.is_file(), "native reader missing from repository; no silent fixture fallback"
    assert ast_digest(path.read_text(), "members_asof") == ast_digest(NATIVE_EXCERPT, "members_asof")
