from __future__ import annotations

from pathlib import Path


def test_ghp1_candidate_receipt_preserves_completion_honesty() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root
        / "docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1-candidate-receipt.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "DRAFT_HOLD",
        "PRODUCTION_INERT",
        "No hosted check",
        "GHP2 owner app         = NOT_BUILT",
        "GHP3 deployment        = NOT_BUILT",
        "GHP4 live canary       = NOT_BUILT",
        "GitHub owns the exact changed-path census",
        "No downstream child inherits START",
    ):
        assert marker in text
