"""Static guards for a compact, current-procedure-bound bootstrap handoff.

These tests check explicit instruction clauses, not model compliance, runtime
permissions, autonomous continuation or Fable parity. The existing package
validator remains the structural authority; no additional runtime is created.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/mastermind-sol/skills/bootstrap-mastermind/SKILL.md"
HEADING = "## Active-duty handoff after recovery"
BASELINE_BLOB = "38ee459dbb6c01f7b56176b558cb2c9936694e4e"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _active_section(text: str) -> str:
    if HEADING not in text:
        return ""
    tail = text.split(HEADING + "\n", 1)[1]
    return tail.split("\n## ", 1)[0].strip()


CLAUSES = (
    ("procedure_not_new_authority", ("selected current procedure", "not a scheduler", "creates no authority")),
    ("answer_vs_change", ("answer-shaped", "change-shaped", "diagnosis alone")),
    ("discriminating_next_action", ("question whose answer changes", "cheapest falsifier", "another broad audit")),
    ("readiness_per_action", ("actual tool schema", "installed or enabled", "does not prove", "required app confirmation")),
    ("same_parent_owns_return", ("action-authoritative parent", "exact artifact", "fresh carrier", "same-carrier decision")),
    ("no_informal_takeover", ("shared account", "does not identify", "no replacement worker")),
    ("bounded_delegation", ("least-scarce capable", "measurable result", "existing placement", "local tool call")),
    ("independent_progress", ("already-authorized independent work", "blocked branch", "irreversible", "within existing scope")),
    ("evidence_reuse", ("existing immutable evidence", "material source or dependency change", "do not repeat")),
    ("uncertain_effects", ("update the diagnosis", "EFFECT_UNKNOWN", "original operation and carrier", "no blind retry or failover")),
    ("obligation_not_tail", ("unanswered decision", "routine progress", "existing dialogue contract", "not interchangeable")),
    ("truthful_turn_boundary", ("continuation packet", "remaining obligations", "not start a future turn", "registration receipt", "unavailable")),
    ("existing_continuation_and_succession", ("Reuse a verified existing continuation binding", "instead of stacking registrations", "Conversation replacement preserves unresolved effects and remaining budget", "existing succession and fencing")),
)


@pytest.mark.parametrize("name,phrases", CLAUSES, ids=[item[0] for item in CLAUSES])
def test_active_duty_clause_is_explicit(name: str, phrases: tuple[str, ...]) -> None:
    section = re.sub(r"\s+", " ", _active_section(_text()))
    missing = [phrase for phrase in phrases if phrase not in section]
    assert not missing, f"{name}: explicit clauses missing: {missing}"


def test_original_bootstrap_is_preserved_byte_for_byte() -> None:
    text = _text()
    if HEADING in text:
        start = text.index(HEADING)
        end = text.index("## Output", start)
        text = text[:start] + text[end:]
    payload = text.encode("utf-8")
    oid = hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
    assert oid == BASELINE_BLOB


def test_handoff_is_after_current_source_gate_and_before_output() -> None:
    text = _text()
    assert text.index("## Mandatory current-source gate") < text.index("## Procedure") < text.index("## Output")
    if HEADING in text:
        assert text.index("## Procedure") < text.index(HEADING) < text.index("## Output")


def test_handoff_is_compact_not_an_extra_manual() -> None:
    assert len(_active_section(_text()).split()) <= 700


def test_existing_dynamic_authority_gate_is_retained() -> None:
    text = _text()
    for clause in (
        "../../references/authority-boundaries.md",
        "Read protected Mastermind `master`",
        "docs/sol_skills/INDEX.md",
        "same exact commit",
        "modifying workflow is unavailable",
    ):
        assert clause in text


def test_bootstrap_has_no_new_runtime_or_provider_entrypoint() -> None:
    text = _text()
    assert text.startswith("---\nname: bootstrap-mastermind\ndescription: Use when ")
    assert not re.search(r"https?://|\b(?:JOB|ATTEMPT|WORKER)-\d|\bMAS-\d|\bC[A-Z0-9]{8,}\b|\b\d{10}\.\d{6}\b", text)
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text)
