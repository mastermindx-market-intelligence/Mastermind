"""Source-only contract checks for cross-session independent review routing.

These tests cannot prove installation, a live Dot pickup, Fabric START, or a formal
GitHub review. They protect the discoverable bootstrap/guide projection and its
negative capability boundaries without creating a second reviewer service.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _project_instructions(source: str) -> str:
    return source.split("## Approved Project instruction text", 1)[1].split(
        "```text\n", 1
    )[1].split("\n```", 1)[0]


def test_web_project_instruction_block_loads_review_guide_within_budget():
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    block = _project_instructions(kernel)
    assert block.startswith("MASTERMIND SOL BOOTSTRAP")
    assert "protected master docs/sol_skills/INDEX.md" in block
    assert GUIDE in block, "outside-fence Markdown is not installed Project text"
    assert "Review: load " + GUIDE in block
    assert "at pin" in block
    assert "Fabric block" in block
    assert "never native Sol labor" in block
    assert len(block) <= 8000
    assert len(block.encode("utf-8")) <= 8000
    assert (ROOT / GUIDE).is_file()


def test_outside_fence_only_pointer_fails_project_consumer():
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    block = _project_instructions(kernel)
    assert GUIDE in block
    # Simulate accidentally moving the only review pointer to supporting
    # Markdown outside the actual Project instruction code fence.
    moved = kernel.replace("Review: load " + GUIDE + " at pin.", "")
    assert GUIDE not in _project_instructions(moved)
    assert GUIDE in moved, "supporting Markdown should still contain the guide"
    assert GUIDE not in _project_instructions(moved), (
        "a guide mentioned elsewhere in the file must not pass installation"
    )


def test_existing_session_bootstraps_and_review_skill_link_to_one_guide():
    expected = {
        "AGENTS.md": GUIDE,
        "CLAUDE.md": GUIDE,
        "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md": "SESSION_INDEPENDENT_REVIEW_ROUTING.md",
        "plugins/mastermind-sol/skills/review-pull-request/SKILL.md": GUIDE,
    }
    for p, link in expected.items():
        assert link in _read(p), f"{p} must discover canonical review guide"
    assert "independent review" in _read(
        "plugins/mastermind-sol/skills/review-pull-request/SKILL.md"
    ).lower()


def test_review_guide_preserves_identity_and_no_denial_failover():
    guide = _read(GUIDE)
    for token in (
        "fabric_capabilities",
        "fabric_request",
        "root_id",
        "parent_id",
        "EFFECT_UNKNOWN",
        "retry_allowed=false",
        "C0CAUK8P8S3",
        "PICKUP_ACK",
        "START",
        "FORMAL_APPROVAL_NOT_PROVEN",
        "formal",
        "GitHub",
        "REVIEW_RETURN.md",
        "GITHUB_REVIEW_INGRESS.md",
    ):
        assert token in guide, f"missing review guard or evidence owner: {token}"
    assert "no new" in guide.lower() or "not a new" in guide.lower()
    assert "not a submitted" not in guide.lower() or "GitHub" in guide
    assert "cannot substitute" in guide, (
        "a manual Dot technical review cannot prove required Fabric START"
    )


def test_source_only_prevents_false_installed_and_live_claims():
    guide = _read(GUIDE)
    assert "not a deployed service" in guide
    assert "not a live" in guide or "no ability to enroll" in guide
    assert "NOT_PROVEN" in guide
    assert "fresh" in guide.lower()
