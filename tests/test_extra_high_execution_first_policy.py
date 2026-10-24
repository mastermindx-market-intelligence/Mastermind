"""Static regression contract for execution-first Extra High sessions.

These tests validate source policy and adversarial scenario coverage. They do
not prove that a served model loaded the policy or performed live actions.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs" / "sol_skills"
PAPER = ROOT / "skills" / "paper-design-workflow" / "SKILL.md"
CORPUS = ROOT / "research" / "fixtures" / "extra_high_execution_first_2026-10-11.json"


def _words(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def test_delivery_assignments_require_real_action_before_recommendation_only_exit():
    active = _words(SKILLS / "ACTIVE_EXECUTION.md")
    for clause in (
        "Extra High execution-first rule for assigned delivery",
        "**perform the next safe, authorized action**",
        "does not silently convert an end-to-end assignment into an assessment",
        "Do not perform a dummy mutation merely to satisfy this rule",
        "Ordinary reversible choices within the assigned scope",
        "not a fresh Chairman approval ceremony",
        "If yes, execute it in the current healthy turn",
    ):
        assert clause in active


def test_method_unavailability_does_not_swallow_alternative_execution_lanes():
    active = _words(SKILLS / "ACTIVE_EXECUTION.md")
    paper = _words(PAPER)
    for clause in (
        "explicitly required invariant",
        "identity-preserving cross-file page move",
        "already-copied destination",
        "Preserve originals until destination quality and references are proven",
        "An explicit permission/safety refusal is not a fallback invitation",
        "EFFECT_UNKNOWN edit stays on its original carrier",
    ):
        assert clause in active
    for clause in (
        "Non-destructive cross-file cleanup",
        "not automatically a requirement to preserve their internal page/artboard/node identities",
        "copy or reconstruct into the verified destination, compare and repair",
        "An unsupported cross-file move is a blocker for that method",
        "do not invent calls, switch carriers after a denial",
        "Do not require another human design-signoff",
    ):
        assert clause in paper


def test_checkpoints_are_sparse_recovery_saves_not_turn_boundaries():
    reliability = _words(SKILLS / "SESSION_RELIABILITY.md")
    for clause in (
        "Extra High checkpoint economy",
        "A checkpoint is a **recovery save, not a deliverable or approval request**",
        "Tool-call counts, elapsed time, a completed assessment",
        "do not independently trigger a checkpoint or justify ending the turn",
        "Reuse a verified commit, PR, artifact or existing-owner checkpoint",
        "start the next safe ready in-scope phase immediately",
        "never prioritize turn length over effect safety",
    ):
        assert clause in reliability


def test_adversarial_extra_high_scenarios_cover_delivery_and_safety():
    scenarios = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert [row["scenario_id"] for row in scenarios] == [
        "EHX01", "EHX02", "EHX03", "EHX04",
        "EHX05", "EHX06", "EHX07", "EHX08",
    ]
    for row in scenarios:
        assert set(row) == {"scenario_id", "prompt", "pass_requires"}
        assert 70 <= len(row["prompt"]) <= 1500
        assert 80 <= len(row["pass_requires"]) <= 1500
        assert row["pass_requires"].startswith("PASS:")
        assert "FAIL:" in row["pass_requires"]
    corpus = " ".join(row["prompt"] + " " + row["pass_requires"] for row in scenarios)
    for phrase in (
        "identity-preserving cross-file move",
        "signoff",
        "checkpoint",
        "permission",
        "EFFECT_UNKNOWN",
        "research-only",
    ):
        assert phrase in corpus
