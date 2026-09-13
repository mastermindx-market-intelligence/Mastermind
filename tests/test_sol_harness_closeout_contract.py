"""Static skill-contract tests; not proof of model behavior or runtime enforcement.

The production text changes these tests detect are missing exact-child cleanup,
missing aggregate-watcher protection, unbound evidence acceptance, and unconditional
production-proof requirements in records-only closeout. No provider is invoked.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("review-worker-return", "close-out-program")


def text(skill: str) -> str:
    return (ROOT / "plugins/mastermind-sol/skills" / skill / "SKILL.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_current_source_gate_survives(skill: str) -> None:
    source = text(skill)
    assert "Read protected Mastermind `master`" in source
    assert "same exact commit" in source
    assert "modifying workflow is unavailable" in source
    assert "../../references/authority-boundaries.md" in source


@pytest.mark.parametrize("skill", SKILLS)
def test_terminal_cleanup_names_exact_child_source(skill: str) -> None:
    assert "exact child operation + carrier source" in text(skill)


@pytest.mark.parametrize("skill", SKILLS)
def test_terminal_cleanup_preserves_shared_resource(skill: str) -> None:
    assert "keep the aggregate resource active" in text(skill)


@pytest.mark.parametrize("skill", SKILLS)
def test_failed_cleanup_does_not_reopen_child(skill: str) -> None:
    source = text(skill)
    assert "WATCH_STOP_FAILED" in source
    assert "keep the child terminal" in source


@pytest.mark.parametrize("skill", SKILLS)
def test_terminal_stop_is_not_a_successor_assignment(skill: str) -> None:
    assert "does not authorize a new child" in text(skill)


def test_review_requires_artifact_bound_evidence_not_success_prose() -> None:
    source = text("review-worker-return")
    assert "exact reviewed artifact" in source
    assert "A `PASS` word, status label, or model summary is not independent proof" in source
    assert "Missing or contradictory evidence is not acceptance" in source


def test_review_refreshes_carrier_after_evidence_before_adjudication() -> None:
    source = text("review-worker-return")
    assert "after the latest evidence-producing action" in source
    assert "Watcher silence does not satisfy this read" in source


def test_review_preserves_effect_reconciliation_and_owned_independent_work() -> None:
    source = text("review-worker-return")
    assert "do not retry an `EFFECT_UNKNOWN` action" in source
    assert "Separately authorized, path-disjoint work may continue" in source


def test_review_does_not_repeat_valid_immutable_review_without_material_change() -> None:
    assert "reuse eligible immutable review evidence" in text("review-worker-return")


def test_closeout_production_proof_is_conditional_on_the_commission() -> None:
    source = text("close-out-program")
    assert "production proof required by the commission is missing" in source
    assert "A records-only closeout may finish" in source
    assert "BUILT_NOT_PROVEN" in source
    assert "or production proof is missing" not in source
    assert ", production proof is missing," not in source


@pytest.mark.parametrize("skill", SKILLS)
def test_obsolete_whole_watcher_shutdown_wording_is_removed(skill: str) -> None:
    source = text(skill)
    assert "require reciprocal watcher shutdown" not in source
    assert "Disarm or truthfully report failure to disarm temporary reciprocal watchers" not in source


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_remains_small_and_has_no_live_program_state(skill: str) -> None:
    source = text(skill)
    assert len(source.encode("utf-8")) < 6500
    assert source.startswith(f"---\nname: {skill}\n")
    for forbidden in ("5560737246", "C0BSBM78V1N", "01a06f73", "4fe4d6bc"):
        assert forbidden not in source


@pytest.mark.parametrize("skill", SKILLS)
def test_cleanup_is_conditional_on_a_terminal_stop(skill: str) -> None:
    source = text(skill)
    assert "After terminal STOP, where a continuation source exists" in source


@pytest.mark.parametrize("skill", SKILLS)
def test_cleanup_does_not_grant_control_of_another_session(skill: str) -> None:
    source = text(skill)
    assert "remove only this side's exact child operation + carrier source" in source
    assert "Require the counterpart to remove its own exact source" in source
    assert "Do not directly mutate another session's continuation resource" in source


OPERATOR_FILES = (
    "plugins/mastermind-operator/skills/finish-operation/SKILL.md",
    "plugins/mastermind-operator/references/dialogue-boundary.md",
)


def operator_text(relative: str = OPERATOR_FILES[0]) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_operator_keeps_bound_identity_and_existing_tool_contract() -> None:
    source = operator_text()
    assert "one already-bound operation and dialogue" in source
    assert "never choose actor, Job, Attempt, Worker, provider, account, host, channel, or thread" in source
    assert "../../references/dialogue-boundary.md" in source
    assert "RESULT is not acceptance or STOP" in source
    assert "never self-merge" in source


@pytest.mark.parametrize("relative", OPERATOR_FILES)
def test_operator_terminal_cleanup_preserves_other_sources(relative: str) -> None:
    source = operator_text(relative)
    assert "exact child operation + carrier source" in source
    assert "keep the aggregate resource active" in source
    assert "WATCH_STOP_FAILED" in source
    assert "keep the child terminal" in source


@pytest.mark.parametrize("relative", OPERATOR_FILES)
def test_operator_dialogue_wait_does_not_change_runtime_lifecycle(relative: str) -> None:
    source = operator_text(relative)
    assert "A pending Sol dialogue does not reopen or change Executive Job or Attempt state" in source
    assert "The child remains nonterminal until an explicit Sol terminal edge exists" not in source


def test_operator_does_not_invent_a_terminal_receipt_tool() -> None:
    source = operator_text()
    assert "only when the current contract and exposed tools support it" in source
    assert "do not invent a message type or reuse an unrelated tool" in source


def test_operator_reference_closes_only_terminal_child_source() -> None:
    source = operator_text(OPERATOR_FILES[1])
    assert "After terminal STOP" in source
    assert "does not authorize a successor child" in source
    assert "→ reciprocal watcher shutdown" not in source
