"""Static policy/corpus contracts only: not model behavior or live delegation proof."""
import json
from pathlib import Path

import pytest
from scripts.ohf.fresh_sol_eval import ScenarioPacket

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "research/fixtures/web_ceo_role_adaptive_delegation_2026-09-14.json"
SKILL = ROOT / "docs/sol_skills/WEB_CEO_DELEGATION.md"
CASE_IDS = tuple(f"WCD{i:02d}" for i in range(1, 15))


@pytest.mark.parametrize("scenario_id", CASE_IDS)
def test_scenarios_materialize_the_existing_packet_contract(scenario_id):
    assert CORPUS.is_file(), "role-adaptive scenario corpus is not supplied"
    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    matches = [row for row in rows if row["scenario_id"] == scenario_id]
    assert len(matches) == 1
    row = matches[0]
    assert set(row) == {"scenario_id", "prompt", "pass_requires"}
    packet = ScenarioPacket(**row)
    assert packet.scenario_id == scenario_id
    for value in (packet.prompt, packet.pass_requires):
        assert isinstance(value, str) and 40 <= len(value) <= 2500
    assert "PASS:" in packet.pass_requires and "FAIL:" in packet.pass_requires


def test_corpus_has_unique_closed_case_set():
    assert CORPUS.is_file(), "role-adaptive scenario corpus is not supplied"
    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert tuple(row["scenario_id"] for row in rows) == CASE_IDS


@pytest.mark.parametrize("clause", [
    "CONCENTRATED_JUDGMENT", "SUSTAINED_ORCHESTRATION", "role preferences",
    "not duration guarantees", "Do not force an Astra-to-Sol handoff",
    "LOWER_TOTAL_OVERHEAD", "PRINCIPAL_JUDGMENT", "UNIQUE_APPROVED_ACCESS",
    "CRITICAL_PATH_INTERVENTION", "NO_ELIGIBLE_WORKER",
    "EFFECT_UNKNOWN", "Capacity", "ACTIVE_EXECUTION",
    "not enrolled", "not a served-model or Web Pro attestation",
])
def test_candidate_instruction_preserves_required_boundaries(clause):
    assert SKILL.is_file(), "role-adaptive instruction candidate is not supplied"
    assert clause in SKILL.read_text(encoding="utf-8")


def test_static_packet_checks_do_not_launch_or_grade_models():
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not called.intersection({"run_one", "check_corpus", "submit_ceo_intent"})
