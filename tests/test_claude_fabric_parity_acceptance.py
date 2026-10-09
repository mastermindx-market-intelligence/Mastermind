"""Static corpus/source contracts, not provider execution or live COO qualification."""
import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "research/fixtures/claude_fabric_parity_acceptance_2026-09-15.json"
PLAN = ROOT / "docs/superpowers/plans/2026-09-15-claude-fabric-parity-and-portable-orchestration.md"
CASE_IDS = tuple(
    f"{prefix}{i:02d}"
    for prefix, count in (("Q", 15), ("E", 11), ("O", 10))
    for i in range(1, count + 1)
)


def corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def normalized(text):
    """Ignore Markdown emphasis/line wrapping, but preserve normative wording."""
    return " ".join(re.sub(r"[*`]", "", text).split())


def test_corpus_is_proposed_data_not_runtime_or_observed_proof():
    data = corpus()
    assert set(data) == {
        "schema", "status", "is_runtime_configuration", "is_live_usage",
        "parent_program", "purpose", "cases",
    }
    assert data["schema"] == "mastermind.claude_fabric_acceptance_cases.v1"
    assert data["status"] == "SPEC_ONLY"
    assert data["is_runtime_configuration"] is False
    assert data["is_live_usage"] is False
    assert data["parent_program"] == "WS:EXECUTIVE-CAPACITY-FABRIC"
    assert isinstance(data["purpose"], str) and len(data["purpose"]) >= 40
    assert isinstance(data["cases"], list)


def test_corpus_has_exact_ordered_unique_case_set():
    ids = tuple(row["case_id"] for row in corpus()["cases"])
    assert ids == CASE_IDS
    assert len(ids) == len(set(ids)) == 36


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_each_case_has_owner_setup_and_discriminating_pass_condition(case_id):
    matches = [row for row in corpus()["cases"] if row["case_id"] == case_id]
    assert len(matches) == 1, f"missing/duplicate case {case_id}"
    row = matches[0]
    assert set(row) == {"case_id", "owner", "setup", "pass_condition"}
    for key, lower in (("owner", 5), ("setup", 40), ("pass_condition", 40)):
        assert isinstance(row[key], str) and lower <= len(row[key]) <= 2500
        assert not re.search(r"\b(?:TBD|TODO|FIXME)\b", row[key])


def test_quota_example_expected_numbers_follow_its_own_inputs():
    row = next(row for row in corpus()["cases"] if row["case_id"] == "Q02")
    inputs = re.fullmatch(
        r"Synthetic total=(\d+), Fable cap=(\d+), Fable used=(\d+), "
        r"other used=(\d+); other constraints nonbinding\.", row["setup"]
    )
    outputs = re.fullmatch(
        r"Shared remaining=(\d+) and Fable remaining=(\d+); "
        r"constraints intersect, they are not summed\.", row["pass_condition"]
    )
    assert inputs and outputs, "quota example must have explicit inputs/expectations"
    total, cap, fable, other = map(int, inputs.groups())
    shared_left, family_left = map(int, outputs.groups())
    assert (total, cap, fable, other) == (100, 50, 20, 15)
    assert shared_left == total - fable - other == 65
    assert family_left == min(shared_left, cap - fable) == 30


@pytest.mark.parametrize("case_id,required", [
    ("Q13", "shared-window telemetry alone MUST NOT establish Fable capacity"),
    ("Q14", "host replicas MUST share the same provider-domain resource identity"),
    ("Q15", "MUST preserve strict dominance and the frozen lexicographic ordering"),
    ("E09", "MUST reject caller-selected, stale or wrong-realm generation"),
    ("E10", "MUST refuse unattended execution without an exact current usage-policy receipt"),
    ("E11", "MUST NOT treat a third-party Claude-compatible profile as native Anthropic capacity"),
])
def test_new_falsifiers_preserve_normative_expected_outcomes(case_id, required):
    rows = {row["case_id"]: row for row in corpus()["cases"]}
    assert case_id in rows
    assert required in normalized(rows[case_id]["pass_condition"])


@pytest.mark.parametrize("clause", [
    "Ranking MUST preserve strict Pareto dominance before the documented lexicographic ordering",
    "A scalar MAY operate only inside one already-frozen lexicographic stage or as a display aid",
    "Static provider preference MUST be a deterministic tie-break only",
    "Usage debit is not usage-policy permission",
    "Native Anthropic Fable/Opus MUST use the existing PF1 claude-code boundary",
    "#581 MUST NOT be represented as the native Anthropic subscription worker",
    "Native subscription authentication MUST remain with the dedicated worker principal",
    "Headless claude -p and equivalent noninteractive SDK execution MUST be classified as unattended",
    "An interactive canary MUST NOT flip unattended or autonomous policy flags",
    "usage_policy_mode and provider_policy_receipt_ref",
    "The v1 realm and Capacity evidence seams are fixture-only/hermetic",
    "Wave C MUST NOT promote #581's hermetic v1 facts to production",
    "Family-B B0 review/acceptance is a predecessor, not permission to START B1+",
    "Owner-issued current realm generation MUST be exact-realm scoped",
    "Shared-window telemetry alone MUST NOT establish Fable capacity",
    "Do not spawn a Claude process per status refresh",
    "Host replicas MUST NOT multiply one provider entitlement",
    "No new host telemetry collector is authorized by this plan",
    "Wave B live before/after proof depends on Wave C admission",
    "A non-author lane MUST execute independent acceptance",
    "tests/test_claude_fabric_parity_acceptance.py",
])
def test_plan_preserves_reviewed_source_boundaries(clause):
    text = PLAN.read_text(encoding="utf-8")
    if clause == "usage_policy_mode and provider_policy_receipt_ref":
        # Wave-level references must not mask a missing launch-receipt binding.
        text = text.split("## 4. Environment parity", 1)[1].split("## 5.", 1)[0]
    assert clause in normalized(text)


def test_current_owner_heads_and_proposed_family_b_are_distinguished():
    text = PLAN.read_text(encoding="utf-8")
    for ref in (
        "bf06ef8f2453b7592c4312d65f770292446ea141",
        "7f68d90d3c5453dc7b2f6adb8fcca379fbd06a0b",
        "30f8a4c1188f19f99622da5503a70b643c1ef167",
        "d5ac0d61f1a95b9d21441a6dc3b1905bde6b7c6d",
        "PROPOSED / B0 REVIEW-GATED / NOT_ENROLLED",
    ):
        assert ref in text
    assert "Historical superseded inspection heads" in text


def test_every_case_has_an_explicit_wave_mapping():
    text = PLAN.read_text(encoding="utf-8")
    for mapping in (
        "A: E01–E08", "B: Q01–Q15", "C: E09–E11, O04–O07",
        "D: O01–O08, O10", "E: Q14, E05, E07–E08, O09–O10",
    ):
        assert mapping in text
    assert "36 source-only acceptance scenarios" in text


def test_validation_is_source_only_and_has_no_execution_imports_or_calls():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imports <= {"ast", "json", "re", "pathlib", "pytest"}
    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not called & {"exec", "eval", "system", "Popen", "run", "run_one", "query", "connect", "write_text", "write_bytes", "unlink"}
