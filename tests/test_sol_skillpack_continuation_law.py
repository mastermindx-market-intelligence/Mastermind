"""Procedure-presence regression for the Continuation Delta Skillpack revision.

Pins the acceptance criteria of the 2026-08-24 Chairman-approved design spec
(as corrected by the Sol C1–C6/C2' ruling): the Continuation Delta Law exists
at the right numbering in both constitutional surfaces, every amended skill
carries its required section, all Skillpack files share one compatible
metadata set, and the heavy contract exists with its full finding vocabulary.

These assertions are text-presence pins, not semantics: the behavioral half is
owned by Skillpack pressure testing, and the deterministic half by
tests/test_sol_commission_lint.py.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs" / "sol_skills"

SKILL_FILES = [
    "INDEX.md",
    "BOOTSTRAP_KERNEL.md",
    "COLD_START.md",
    "REVIEW_RETURN.md",
    "COMMISSION_WAVE.md",
    "CLOSEOUT.md",
    "RECONCILE_STATE.md",
    "CONTINUATION_DELTA_CONTRACT.md",
]

HARD_FINDING_NAMES = [
    "MALFORMED_MANIFEST",
    "HANDOFF_REPLAY_COLLISION",
    "SUPERSEDED_WORK_REOPENED",
    "REJECTED_WORK_REOPENED",
    "OBLIGATION_STATE_COLLISION",
    "EXECUTION_SURFACE_COLLISION",
    "DNR_STATE_COLLISION",
    "UNJUSTIFIED_REVALIDATION",
    "UNBOUND_CONTINUATION",
    "CARRIER_HEAD_MISMATCH",
    "UNDECLARED_EXECUTION",
    "EXECUTION_DISPOSITION_ILLEGAL",
    "HELD_DISPOSITION_ILLEGAL",
    "DARK_OPEN_WORK",
    "NOTHING_TO_COMMISSION",
    "DNR_REOPEN_WITHOUT_REFUTATION",
    "DNR_COVERAGE_MISSING",
    "ORGANIZATIONAL_STATE_NOT_RECONCILED",
]

WARNING_FINDING_NAMES = [
    "POSSIBLE_STALE_ORG_STATE",
    "DNR_COVERAGE_UNPROVEN",
    "NEW_WAVE_WITH_EXISTING_CARRIER",
]


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path.name} has no frontmatter"
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def _read(name: str) -> str:
    return (SKILLS / name).read_text(encoding="utf-8")


def test_all_skillpack_files_exist():
    for name in SKILL_FILES:
        assert (SKILLS / name).is_file(), f"missing {name}"


def test_skillpack_metadata_is_one_compatible_release():
    versions, majors = set(), set()
    for name in SKILL_FILES:
        meta = _frontmatter(SKILLS / name)
        assert meta.get("schema") == "mastermind.sol_skillpack.v1", name
        versions.add(meta.get("skillpack_version"))
        majors.add(meta.get("minimum_bootstrap_major"))
    assert len(versions) == 1, f"skillpack files disagree on version: {versions}"
    assert majors == {"1"}, f"bootstrap major must stay 1: {majors}"
    (only,) = versions
    parts = tuple(int(x) for x in only.split("."))
    assert parts >= (1, 1, 0), f"Continuation Delta revision requires >= 1.1.0, got {only}"
    assert parts[0] == 1, "major bump not authorized by this revision"


def test_index_hard_law_21_is_continuation_delta():
    # 1.0.1 already occupies hard laws 13-20 (reciprocal dialogue / routing /
    # placement). Continuation Delta appends as 21 after those protected laws.
    text = _read("INDEX.md")
    m = re.search(r"^21\.\s+(.{0,120})", text, re.MULTILINE)
    assert m, "INDEX.md has no hard law 21"
    assert "Continuation Delta" in m.group(1)
    assert "NOTHING_TO_COMMISSION" in text
    assert "Revalidation is not redo" in text
    assert "CONTINUATION_DELTA_CONTRACT" in text, "contract not registered in skill selection"


def test_bootstrap_kernel_law_21_is_continuation_delta():
    # Same numbering collision as INDEX: 1.0.1 took kernel 14-20.
    text = _read("BOOTSTRAP_KERNEL.md")
    m = re.search(r"^21\.\s+(.*)$", text, re.MULTILINE)
    assert m, "BOOTSTRAP_KERNEL.md has no kernel law 21"
    law = m.group(1)
    assert "delta" in law.lower() and "receipt-invalidating" in law


def test_cold_start_detects_durable_state_lag():
    text = _read("COLD_START.md")
    assert "DURABLE_STATE_STALE" in text
    assert "Durable-state freshness" in text


def test_review_return_forces_obligation_disposition():
    text = _read("REVIEW_RETURN.md")
    assert "NEXT_WORKSET" in text
    for word in ("DONE", "OPEN", "BLOCKED", "SUPERSEDED", "REJECTED", "REVALIDATE_REQUIRED"):
        assert word in text, f"REVIEW_RETURN.md missing disposition {word}"


def test_commission_wave_has_subtraction_gate_and_modes():
    text = _read("COMMISSION_WAVE.md")
    assert "Completion Subtraction Gate" in text
    assert "CONTINUATION_DELTA" in text and "NEW_WAVE" in text
    assert "sol_commission_lint" in text


def test_closeout_produces_structured_do_not_repeat_state():
    text = _read("CLOSEOUT.md")
    for key in (
        "COMPLETED_DO_NOT_REPEAT",
        "OPEN_WORKSET",
        "REVALIDATE_REQUIRED",
        "BLOCKED_OR_HELD",
        "SUPERSEDED_OR_REJECTED",
        "EXACT_NEXT_ACTION",
    ):
        assert key in text, f"CLOSEOUT.md missing {key}"
    assert "CLOSEOUT_INCOMPLETE" in text


def test_reconcile_state_has_instruction_census():
    text = _read("RECONCILE_STATE.md")
    assert re.search(r"instruction census", text, re.IGNORECASE)
    assert "Repeated context is verbosity; repeated executable effect is replay." in text


def test_contract_carries_full_finding_vocabulary_and_limits():
    text = _read("CONTINUATION_DELTA_CONTRACT.md")
    for name in HARD_FINDING_NAMES + WARNING_FINDING_NAMES:
        assert name in text, f"contract missing finding {name}"
    # C4: exact blob-proof grammar.
    assert "blob:<40-hex>" in text
    # C4: ID laundering named as a deterministic blind spot.
    assert re.search(r"renam\w+", text, re.IGNORECASE) and "blind spot" in text.lower()
    # C5: enforcement honesty.
    assert "technically advisory" in text
    # Over-hardening guard (Case K).
    assert "Repeated context is verbosity" in text
