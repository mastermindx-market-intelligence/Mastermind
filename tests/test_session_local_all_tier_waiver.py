"""Source-only guard for the Chairman's attended CEO Web review waiver.

This does not claim a protected merge, live Project setting, native skill install,
a real reviewer child, or a signed GitHub/Executive machine admission.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/SESSION_LOCAL_REVIEW_POLICY.md"


def policy() -> str:
    return POLICY.read_text(encoding="utf-8")


def test_attended_web_waiver_is_all_three_tiers_without_host_dependency():
    s = policy()
    required = (
        "Attended CEO Web FAST / STANDARD / CRITICAL",
        "Zero blanket independent technical reviewers",
        "zero additional formal non-author approvals",
        "Do not wait for #2018 or a signed host deployment",
        "CRITICAL classification by itself does **not** require",
        "SELF_REVIEWED",
        "proportionate security and real-path proof",
    )
    for anchor in required:
        assert anchor in s, anchor
    for obsolete in (
        "FAST / ordinary STANDARD only AFTER",
        "Before #2018 is protected",
        "CRITICAL's two technical perspectives must show two distinct child",
        "a CRITICAL source subagent runs and returns locally",
    ):
        assert obsolete not in s, obsolete


def test_machine_review_and_actual_native_release_stay_distinct():
    s = policy()
    for anchor in (
        "signed AUTOMATIC GitHub/Executive",
        "default OFF",
        "separate",
        "native GitHub/CODEOWNERS",
        "mandatory hosted CI",
        "no-self-approval/merge",
        "HOLD",
        "original",
        "explicit permission denial",
        "separate START",
        "Actual GitHub native requirements reject author self-approval",
    ):
        assert anchor in s, anchor


def test_optional_review_availability_is_not_a_default_delegation():
    s = policy()
    table = s.split("## Session-local review avenues", 1)[1].split(
        "## Receipt, adversarial protocol and limits", 1
    )[0]
    assert "FAST, STANDARD and CRITICAL" in table
    for surface in (
        "ChatGPT Web, ordinary session",
        "ChatGPT Web, Pro session",
        "Codex native",
        "Claude native",
        "Subagent Fabric",
    ):
        assert surface in table
    assert "when distinct scrutiny is genuinely owed" in table
    assert "when a separate technical review is actually required" in s.lower()
    assert "a CRITICAL label alone creates no such child requirement" in table


def test_source_candidate_cannot_pretend_to_be_installed():
    s = policy()
    assert "SOURCE CANDIDATE" in s
    assert "until its own protected merge" in s
    assert "does not install ChatGPT Project settings" in s
    assert "Distinguish source, installed instructions" in s
    assert "No self-merge" in s
