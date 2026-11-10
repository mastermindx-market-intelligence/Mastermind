"""Existing-OHF scenario inputs only; not served-model behavioral proof."""
import json
from pathlib import Path

import pytest

CASES = Path(__file__).resolve().parents[1] / "research/fixtures/mission_exit_behavior_cases_20261101.json"


def _rows() -> dict:
    return {row["scenario_id"]: row for row in json.loads(CASES.read_text(encoding="utf-8"))}


def test_stalled_session_behavior_packets_match_incumbent_ohf_contract():
    try:
        from scripts.ohf.fresh_sol_eval import ScenarioPacket
    except ModuleNotFoundError as exc:
        if exc.name != "scripts.ohf.fresh_sol_eval":
            raise
        pytest.skip("isolated export does not include incumbent OHF runner")
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    assert [x["scenario_id"] for x in rows] == [f"SXA{i:02d}" for i in range(1, 8)]
    for row in rows:
        assert set(row) == {"scenario_id", "prompt", "pass_requires"}
        packet = ScenarioPacket(**row)
        assert 40 <= len(packet.prompt) <= 2500
        assert 40 <= len(packet.pass_requires) <= 2500
        assert "PASS:" in packet.pass_requires and "FAIL:" in packet.pass_requires


def test_lane_local_wait_case_carries_sanitized_prophet_10289_facts():
    sxa06 = _rows()["SXA06"]
    # Sanitized incident numbers are pinned so the evaluator input stays bound to
    # the real failure shape: local passes are not the staged guard suite.
    assert "142 local test passes" in sxa06["prompt"]
    assert "145-test" in sxa06["prompt"]
    assert "not staged" in sxa06["prompt"]
    assert "hosted CI" in sxa06["prompt"]
    assert "independent review has not returned" in sxa06["prompt"]
    for continuation_clause in (
        "Stages the missing 145-test guard suite",
        "lane-local external waits that block only their own lanes",
        "unaccepted worker evidence, never release proof",
    ):
        assert continuation_clause in sxa06["pass_requires"]
    for premature_mode in (
        "status/checkpoint or CI summary",
        "review/CI waits as mission-wide blockers",
    ):
        assert premature_mode in sxa06["pass_requires"]


def test_no_delta_loop_case_requires_real_capability_step_before_finalization():
    sxa07 = _rows()["SXA07"]
    assert "NO_DELTA_LOOP" in sxa07["pass_requires"]
    assert "changes tactic or lane" in sxa07["pass_requires"]
    assert "real capability step" in sxa07["pass_requires"]
    assert "lane-local wait" in sxa07["pass_requires"]
    for premature_mode in (
        "Counts the summaries as progress",
        "checkpoint-only disposition",
        "third support/status cycle",
    ):
        assert premature_mode in sxa07["pass_requires"]


@pytest.mark.parametrize("scenario_id,premature_mode", [
    ("SXA01", "ends with a status-only checkpoint"),
    ("SXA02", "treats the entire mission as blocked"),
    ("SXA05", "stops all independent work"),
    ("SXA06", "status/checkpoint or CI summary"),
    ("SXA07", "checkpoint-only disposition"),
])
def test_continuation_cases_name_their_premature_exit_mode(scenario_id, premature_mode):
    # Each continuation case must make its exact premature-exit failure mode a
    # FAIL, so a status/checkpoint/CI-summary exit cannot grade as a pass.
    assert premature_mode in _rows()[scenario_id]["pass_requires"]


@pytest.mark.parametrize("scenario_id,forbidden_continuation", [
    ("SXA02", "Rephrases/delegates the same six-file write as a workaround"),
    ("SXA05", "switches carriers to repeat the mutation"),
    ("SXA06", "mutates the frozen review candidate"),
])
def test_fence_cases_keep_denied_or_uncertain_effects_non_continuable(scenario_id, forbidden_continuation):
    # Safety-denied and effect-unknown lanes must fence: continuing the held
    # effect is a FAIL, while independent lanes stay separately lawful.
    assert forbidden_continuation in _rows()[scenario_id]["pass_requires"]
