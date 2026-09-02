"""Static contract pins for carrier and Skillpack grounding.

RED-first companion to test_sol_commission_grounding.py. The candidate procedure
must describe the same grounding invariants that the deterministic linter enforces.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "sol_skills" / "CONTINUATION_DELTA_CONTRACT.md"


def test_contract_names_carrier_head_mismatch_hard_finding():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "CARRIER_HEAD_MISMATCH" in text


def test_contract_requires_exact_skillpack_commit_identity():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "skillpack_sha" in text
    assert "exact 40-hex" in text and "Skillpack" in text
