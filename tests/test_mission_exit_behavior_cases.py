"""Existing-OHF scenario inputs only; not served-model behavioral proof."""
import json
from pathlib import Path

import pytest

CASES = Path(__file__).resolve().parents[1] / "research/fixtures/mission_exit_behavior_cases_20261101.json"


def test_stalled_session_behavior_packets_match_incumbent_ohf_contract():
    try:
        from scripts.ohf.fresh_sol_eval import ScenarioPacket
    except ModuleNotFoundError as exc:
        if exc.name != "scripts.ohf.fresh_sol_eval":
            raise
        pytest.skip("isolated export does not include incumbent OHF runner")
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    assert [x["scenario_id"] for x in rows] == [f"SXA{i:02d}" for i in range(1, 6)]
    for row in rows:
        assert set(row) == {"scenario_id", "prompt", "pass_requires"}
        packet = ScenarioPacket(**row)
        assert 40 <= len(packet.prompt) <= 2500
        assert 40 <= len(packet.pass_requires) <= 2500
        assert "PASS:" in packet.pass_requires and "FAIL:" in packet.pass_requires
