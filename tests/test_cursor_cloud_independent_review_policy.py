"""Source-law regression for the manual Cursor Cloud GitHub review route.

No network, provider commissions, lifecycle writes, or actual GitHub reviews.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = (ROOT / "docs/sol_skills/REVIEW_RETURN.md").read_text()
WORKER = (ROOT / "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md").read_text()
SKILL = (ROOT / "plugins/mastermind-sol/skills/review-pull-request/SKILL.md").read_text()
RUNBOOK = (ROOT / "docs/CURSOR_CLOUD_INDEPENDENT_REVIEW.md").read_text()


def test_github_cursor_path_is_manual_not_executive_alias():
    assert "GitHub-native Cursor Cloud" in REVIEW
    assert "valid" in SKILL.lower()
    assert "attended external review surface" in WORKER
    assert "Executive OS model/provider alias" in REVIEW
    assert "Executive OS provider" in RUNBOOK


def test_denial_and_original_effect_are_preserved():
    for source in (REVIEW, RUNBOOK):
        assert "permission" in source
        assert "EFFECT_UNKNOWN" in source or "unknown effect" in source
        assert "retry_allowed=false" in source or "prohibited" in source
        assert "do not" in source.lower()


def test_technical_source_review_does_not_imply_nonauthor_github_approval():
    for source in (REVIEW, RUNBOOK):
        assert "NON_AUTHOR_APPROVAL_NOT_PROVEN" in source
        assert "GitHub" in source
    assert "actual distinct GitHub" in SKILL


def test_ack_is_not_terminal_review_or_fabric_lifecycle():
    assert "Taking a look!" in REVIEW
    assert "launch acknowledgement" in RUNBOOK
    assert "terminal" in REVIEW
    assert "Fabric" in RUNBOOK and "Slack" in RUNBOOK


def test_packet_freezes_original_pr_and_prohibits_source_effects():
    assert "@cursor INDEPENDENT READ-ONLY SECURITY REVIEW" in RUNBOOK
    assert "<full-40-char-SHA>" in RUNBOOK
    assert "THIS ORIGINAL PR" in RUNBOOK
    assert "DO NOT edit, commit or push source" in RUNBOOK


def test_historical_pr1515_is_not_promoted_to_approved():
    assert "6389262119" in RUNBOOK
    assert "6389332447" in RUNBOOK
    assert "bc-03e22133-a364-4ec8-98c4-3db18becba0c" in RUNBOOK
    assert "NON_AUTHOR_APPROVAL_NOT_PROVEN" in RUNBOOK
