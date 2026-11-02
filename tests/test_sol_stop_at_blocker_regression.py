"""Source and future served-behavior regression for the Terminal-style stop-at-blocker failure.

These are source-contract tests. Passing them is not proof that a fresh model
actually follows the instructions; the six scenarios are separate evaluation inputs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "docs/sol_skills/ACTIVE_EXECUTION.md"
CASES = ROOT / "research/fixtures/sol_stop_at_blocker_20261024.json"


def _policy_clause() -> str:
    text = ACTIVE.read_text(encoding="utf-8")
    return text.split("**Stop-at-blocker falsifier.**", 1)[1].split(
        "## Step 1 — Freeze the active-turn frame", 1
    )[0]


def _has_protective_contract(text: str) -> bool:
    return all(
        clause in text
        for clause in (
            "next\nconcrete executable action",
            "does not exhaust the\ncommission",
            "pre-effect *technical* refusal",
            "same original operation",
            "relevant recovery evidence",
            "genuinely independent authorized",
            "explicit permission/safety denial",
            "uncertain effect remains frozen",
            "Do not route around",
            "Step 6 negative-capability evidence",
            "each useful lane",
            "not another form",
        )
    )


def test_stop_falsifier_is_early_in_the_execution_contract():
    text = ACTIVE.read_text(encoding="utf-8")
    assert text.count("**Stop-at-blocker falsifier.**") == 1
    assert text.index("**Stop-at-blocker falsifier.**") < text.index("## Step 1 —")
    assert _has_protective_contract(_policy_clause())


@pytest.mark.parametrize(
    "deleted",
    [
        "pre-effect *technical* refusal",
        "explicit permission/safety denial",
        "uncertain effect remains frozen",
        "Do not route around",
        "Step 6 negative-capability evidence",
        "genuinely independent authorized",
    ],
)
def test_removing_a_critical_effect_or_forward_execution_guard_fails(deleted: str):
    original = _policy_clause()
    assert deleted in original
    assert not _has_protective_contract(original.replace(deleted, "", 1))


def test_terminal_stop_fixture_is_an_unserved_behavior_test_input():
    raw = json.loads(CASES.read_text(encoding="utf-8"))
    assert raw["schema"] == "mastermind.sol_stop_at_blocker_behavior_cases.v1"
    assert raw["served_evidence"] == "NOT_RUN"
    scenarios = raw["cases"]
    assert len(scenarios) == 6
    assert len({case["id"] for case in scenarios}) == 6
    for case in scenarios:
        assert len(case["input"]) >= 70
        assert case["next_action"] and case["next_action"] != "write a report"
        assert case["stop_classification"] in {
            "MORE_WORK_EXISTS",
            "ALL_SCOPED_LANES_BLOCKED",
        }
        assert case["forbidden_claims"]
    by_id = {case["id"]: case for case in scenarios}
    for name in (
        "technical_pre_effect_release_refusal",
        "explicit_source_permission_denial",
        "effect_unknown_one_lane",
        "ci_review_pending",
        "review_request_unconsumed",
    ):
        assert by_id[name]["stop_classification"] == "MORE_WORK_EXISTS"
    assert by_id["all_lanes_proven_blocked"]["stop_classification"] == (
        "ALL_SCOPED_LANES_BLOCKED"
    )
