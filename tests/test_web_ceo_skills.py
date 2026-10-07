"""Static package contracts, not evidence of native ChatGPT behavior."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import validate_mastermind_plugins as validator

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "mastermind-web-ceo": ("user outcome", "smallest", "ACTIVE_EXECUTION.md", "WEB_CEO_DELEGATION.md", "no authority"),
    "mastermind-principal-architect": ("invariants", "alternatives", "migration", "falsifier", "no authority"),
    "mastermind-product-designer": ("persona", "loading", "keyboard", "screenshot", "no authority"),
    "mastermind-deep-research": ("primary sources", "counterevidence", "falsifier", "out-of-sample", "SOURCE_ADMISSION_INCOMPLETE", "SOURCE_INCOMPLETE", "mastermindx-market-intelligence/Mastermind", "SOURCE_PROVEN", "no authority"),
    "mastermind-recovery": ("EFFECT_UNKNOWN", "RECONCILE_STATE.md", "safety or permission denial", "SESSION_RELIABILITY.md", "no authority"),
}


def _text(name: str) -> str:
    path = ROOT / "plugins/mastermind-sol/skills" / name / "SKILL.md"
    assert path.is_file(), f"Missing skill: {name}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SKILLS)
def test_role_skill_is_enrolled_in_existing_sol_package(name: str) -> None:
    assert name in validator.SOL_SKILLS
    _text(name)


@pytest.mark.parametrize("name", SKILLS)
def test_role_skill_has_bounded_native_metadata_and_concrete_method(name: str) -> None:
    text = _text(name)
    match = validator.FRONTMATTER_RE.match(text)
    assert match is not None
    assert match.group("name") == name
    assert match.group("description").startswith("Use when ")
    assert len(match.group("description")) <= 350
    assert len(text.split()) <= 650, "Move optional detail out of the loaded skill"
    assert "## Do not use" in text
    assert "## Evidence and output" in text
    for phrase in SKILLS[name]:
        assert phrase.casefold() in text.casefold(), (name, phrase)


@pytest.mark.parametrize("name", SKILLS)
def test_role_skill_preserves_source_and_authority_owners(name: str) -> None:
    text = _text(name)
    for marker in validator.SOL_GATE_MARKERS:
        assert marker in text
    assert "../../references/authority-boundaries.md" in text
    assert "before interpreting any app, record, or action as authority" in text
    assert "verified pin" in text
    assert "bootstrap-mastermind" in text
    assert "GitHub" in text


@pytest.mark.parametrize("name", SKILLS)
def test_existing_validator_rejects_missing_role_source_gate(tmp_path: Path, name: str) -> None:
    text = _text(name)
    path = tmp_path / "SKILL.md"
    path.write_text(text.replace("same exact commit", "mixed revisions"), encoding="utf-8")
    errors: list[dict[str, str]] = []
    validator._validate_skill(tmp_path, path, "mastermind-sol", name, errors)
    assert "CURRENT_SOURCE_GATE_MISSING" in {item["code"] for item in errors}


@pytest.mark.parametrize("name", SKILLS)
def test_existing_validator_rejects_missing_role_authority_reference(tmp_path: Path, name: str) -> None:
    text = _text(name)
    path = tmp_path / "SKILL.md"
    path.write_text(text.replace("../../references/authority-boundaries.md", "missing-reference.md"), encoding="utf-8")
    errors: list[dict[str, str]] = []
    validator._validate_skill(tmp_path, path, "mastermind-sol", name, errors)
    assert "PACKAGE_REFERENCE_MISSING" in {item["code"] for item in errors}


def test_native_evaluation_cases_are_specifications_not_fabricated_results() -> None:
    path = ROOT / "tests/fixtures/web_ceo_skill_cases.json"
    assert path.is_file(), "Missing native behavior evaluation corpus"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["kind"] == "evaluation_specification_not_results"
    assert data["native_runs_observed"] == 0
    assert data["required_surfaces"] == ["ChatGPT Web Pro", "ChatGPT Web Extra High"]
    cases = data["cases"]
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    covered: set[str] = set()
    for case in cases:
        assert set(case) == {"id", "prompt", "expected_skills", "must_observe", "must_not_observe"}
        assert case["prompt"] and case["must_observe"] and case["must_not_observe"]
        assert set(case["expected_skills"]) <= set(SKILLS)
        covered.update(case["expected_skills"])
    assert covered == set(SKILLS)
    assert sum(not case["expected_skills"] for case in cases) >= 3


def test_new_roles_add_no_plugin_identity_tools_hooks_or_runtime_store() -> None:
    assert set(validator.EXPECTED_SKILLS) == {
        "mastermind-sol", "mastermind-operator", "mastermind-cortex", "mastermind-navigator"
    }
    assert validator.MANIFESTS["mastermind-sol"]["interface"]["capabilities"] == ["Read"]
    for name in SKILLS:
        directory = ROOT / "plugins/mastermind-sol/skills" / name
        assert directory.is_dir(), f"Missing skill: {name}"
        assert sorted(p.name for p in directory.iterdir()) == ["SKILL.md"]


@pytest.mark.parametrize("name", SKILLS)
def test_pin_reuse_is_limited_to_the_current_turn(name: str) -> None:
    text = _text(name)
    assert "already loaded in the current turn" in text
    assert "new-turn recovery must re-establish current source" in text


DEEP_RESEARCH_ADMISSION_CASE_IDS = {
    "research-admission-github-missing",
    "research-admission-github-wrong-repo",
    "research-admission-steward-missing",
    "research-admission-public-web-no-internal",
    "research-admission-historical-github-only",
    "research-admission-external-only",
    "research-admission-steward-degraded",
    "research-admission-owner-conflict",
    "research-admission-short-prompt",
    "research-admission-postrun-source-omission",
}


def test_deep_research_source_admission_contract_is_fail_closed_and_owner_preserving() -> None:
    text = _text("mastermind-deep-research")
    for marker in (
        "SOURCE_REQUIRED",
        "SOURCE_AVAILABLE",
        "SOURCE_PROVEN",
        "SOURCE_MISSING",
        "SOURCE_DEGRADED",
        "SOURCE_ADMISSION_INCOMPLETE",
        "SOURCE_INCOMPLETE",
        "mastermindx-market-intelligence/Mastermind",
        "Mastermind Steward",
        "public web",
        "post-run",
    ):
        assert marker.casefold() in text.casefold(), marker
    assert "historical" in text.casefold()
    assert "wrong repo" in text.casefold() or "wrong repository" in text.casefold()
    assert "does not authorize" in text.casefold() or "cannot authorize" in text.casefold()
    assert "actually used" in text.casefold()
    assert "`source_available` requires" in text.casefold()
    assert "exact-source" in text.casefold()


def test_deep_research_fixture_covers_source_admission_discriminators() -> None:
    data = json.loads((ROOT / "tests/fixtures/web_ceo_skill_cases.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in data["cases"]}
    assert DEEP_RESEARCH_ADMISSION_CASE_IDS <= set(cases)
    for case_id in DEEP_RESEARCH_ADMISSION_CASE_IDS:
        case = cases[case_id]
        assert case["expected_skills"] == ["mastermind-deep-research"]
        assert case["must_observe"] and case["must_not_observe"]
