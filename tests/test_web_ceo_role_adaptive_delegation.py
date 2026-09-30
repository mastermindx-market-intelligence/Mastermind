"""Static policy/corpus contracts only: not model behavior or live delegation proof."""
import ast
import json
from pathlib import Path

import pytest
from scripts.ohf.fresh_sol_eval import ScenarioPacket

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "research/fixtures/web_ceo_role_adaptive_delegation_2026-09-14.json"
SKILL = ROOT / "docs/sol_skills/WEB_CEO_DELEGATION.md"
INDEX = ROOT / "docs/sol_skills/INDEX.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-14-web-ceo-role-adaptive-delegation.md"
SPEC = ROOT / "docs/superpowers/specs/2026-09-14-web-ceo-role-adaptive-delegation.md"
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


def test_corpus_covers_evaluator_exposure_and_fail_closed_pro_admission():
    rows = {row["scenario_id"]: row for row in json.loads(CORPUS.read_text(encoding="utf-8"))}
    assert "evaluation-bundle exposure" in rows["WCD10"]["pass_requires"]
    assert "PRO_MODE_TASK_CLASS" in rows["WCD13"]["pass_requires"]
    assert "PRO_MODE_REFUSED / USE_NON_PRO_MODE" in rows["WCD13"]["pass_requires"]


@pytest.mark.parametrize("clause", [
    "CONCENTRATED_JUDGMENT", "SUSTAINED_ORCHESTRATION", "role preferences",
    "not duration guarantees", "Do not force an Astra-to-Sol handoff",
    "LOWER_TOTAL_OVERHEAD", "PRINCIPAL_JUDGMENT", "UNIQUE_APPROVED_ACCESS",
    "CRITICAL_PATH_SHORTCUT", "NO_ELIGIBLE_PRE_EFFECT_WORKER",
    "EFFECT_UNKNOWN", "not live admission", "ACTIVE_EXECUTION",
    "enrolled in the same pinned INDEX",
    "PRO_MODE_TASK_CLASS", "PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    "Model Router fixes the first lawful suitability tier",
    "fresh-Sol evaluation bundle", "evaluation exposure, not production enrollment",
    "Enrolled companion procedure", "not a served-model or Web Pro attestation",
])
def test_enrolled_instruction_preserves_required_boundaries(clause):
    assert SKILL.is_file(), "enrolled role-adaptive instruction is not supplied"
    assert clause in SKILL.read_text(encoding="utf-8")


@pytest.mark.parametrize("artifact", [SKILL, PLAN, SPEC])
def test_artifacts_disclose_bundle_exposure_without_claiming_runtime_authority(artifact):
    text = artifact.read_text(encoding="utf-8")
    assert "fresh-Sol evaluation bundle" in text
    assert "evaluation exposure, not production enrollment" in text


def test_spec_treats_workstation_connector_exposure_as_session_scoped():
    text = SPEC.read_text(encoding="utf-8")
    assert "Workstation connector exposure is session-scoped" in text
    assert "Studio Direct or Remote Desktop Commander" in text
    assert "absence from one effective schema" in text
    assert "This continuation exposes Studio Direct" not in text


def test_minimax_evidence_and_holds_are_route_scoped():
    plan = PLAN.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    assert "MiniMax evidence and holds are route-scoped" in spec
    assert "truthful kit-path evidence" in plan
    assert "exact model/harness/realm/host route" in plan
    assert "The existing MiniMax incident hold must remain deny-only" not in spec
    assert "MiniMax remains held unless" not in plan


def test_index_enrolls_web_ceo_delegation_as_same_pin_companion_without_new_finalizer():
    raw_index = INDEX.read_text(encoding="utf-8")
    index = " ".join(raw_index.split())
    active = "### `ACTIVE_EXECUTION.md`"
    companion = "### `WEB_CEO_DELEGATION.md`"
    review = "### `REVIEW_RETURN.md`"
    assert raw_index.count(companion) == 1
    assert raw_index.index(active) < raw_index.index(companion) < raw_index.index(review)
    assert "same pinned Skillpack revision" in index
    assert "ACTIVE_EXECUTION remains the sole active-turn, no-delta and finalization owner" in index
    assert "does not select a provider, account, credential, host, model setting, or reasoning mode" in index


def test_enrolled_companion_is_truthful_and_preserves_existing_authority_boundaries():
    raw_skill = SKILL.read_text(encoding="utf-8")
    skill = " ".join(raw_skill.split())
    plan = PLAN.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    rows = {
        row["scenario_id"]: row
        for row in json.loads(CORPUS.read_text(encoding="utf-8"))
    }

    assert "Enrolled companion procedure" in skill
    assert "Candidate procedure: not enrolled" not in raw_skill
    assert "Before that enrollment, this candidate has no procedural authority" not in raw_skill
    assert "ACTIVE_EXECUTION as the sole active-turn, no-delta and finalization owner" in skill
    for clause in ("direct-spawn", "raw-socket", "alternate-queue"):
        assert clause in skill
    assert "raw-socket/provider-spawn bypass" in rows["WCD08"]["pass_requires"]
    for task_class in (
        "LONG_HORIZON_FRONTIER_REASONING",
        "CROSS_SYSTEM_ARCHITECTURE",
        "HARD_DEBUGGING",
        "ADVERSARIAL_JUDGMENT",
    ):
        assert task_class in skill
    assert "`SUSTAINED_ORCHESTRATION` is a work profile, not a `PRO_MODE_TASK_CLASS`" in skill
    assert "44 tests" in plan
    for artifact in (plan, spec):
        assert "Original design basis" in artifact
        assert "current protected integration base" in artifact
    assert "source basis `bffe2ca" not in plan
    assert "Basis: Mastermind `bffe2ca" not in spec
    assert "CRITICAL_PATH_INTERVENTION" not in skill
    assert "NO_ELIGIBLE_WORKER" not in skill
    assert "once #591 is accepted" not in skill
    assert "PROCEDURE ENROLLMENT CANDIDATE / SOURCE-ONLY / PRODUCTION INERT" in spec
    assert "accepted enrollment in the same pinned INDEX" not in spec
    assert "first enrollment of WEB_CEO_DELEGATION must join" not in spec
    assert "once #591 is accepted" not in spec
    assert "The original #632 source package changed none of those active files or live settings" in spec
    assert "This enrollment slice changes only the same-pinned INDEX/companion records and static contract" in spec


def test_plan_records_only_the_index_enrollment_slice_and_keeps_downstream_proof_open():
    plan = PLAN.read_text(encoding="utf-8")
    assert "web-ceo-delegation-enrollment-20260915-sol-001" in plan
    assert "- [x] Re-pin protected INDEX" in plan
    assert "- [ ] Extend the existing external-delegation AGENTS/brief composition" in plan
    assert "- [ ] Prove a fresh consumer loaded the exact enrolled instruction bytes" in plan
    assert "source-only procedural enrollment" in plan
    assert "does not prove Web adoption, Executive admission, worker execution, or parent consumption" in plan


def test_static_packet_checks_do_not_launch_or_grade_models():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert not called.intersection({"run_one", "check_corpus", "submit_ceo_intent"})
