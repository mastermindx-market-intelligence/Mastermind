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


def test_protected_index_routes_review_at_same_pinned_source():
    # Existing Shared Project instructions already bootstrap the protected
    # index; a conditional review entry is discoverable without re-installing
    # the complete Project instruction block first.
    index = _read("docs/sol_skills/INDEX.md")
    assert "`" + GUIDE + "`" in index
    section = index.split("### `" + GUIDE + "`", 1)[1].split("\n### ", 1)[0]
    assert "same" in section.lower() and "protected Mastermind commit" in section
    assert "independent PR/source review" in section
    assert "not" in section.lower() and "runtime" in section
    assert "does not install" in section


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


def test_native_and_web_fabric_skill_sources_discover_the_shared_review_guide():
    """Source packaging is a prerequisite, not installed/fresh-load proof."""
    for p in (
        "skills/mastermind-fabric-delegate/SKILL.md",
        "skills/mastermind-claude-fabric-delegation/SKILL.md",
        "integrations/studio_direct_mcp/fabric_plugin_source/skills/use-subagent-fabric/SKILL.md",
    ):
        skill = _read(p)
        assert GUIDE in skill, f"{p}: the review procedure would be undiscoverable"
        assert "not" in skill.lower() and "GitHub" in skill
        assert "Slack Dot" in skill


def test_source_only_prevents_false_installed_and_live_claims():
    guide = _read(GUIDE)
    assert "not a deployed service" in guide
    assert "not a live" in guide or "no ability to enroll" in guide
    assert "NOT_PROVEN" in guide
    assert "fresh" in guide.lower()


def test_session_local_review_does_not_preempt_unmerged_standard_policy():
    policy = _read("docs/SESSION_LOCAL_REVIEW_POLICY.md")
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")
    for required in (
        "Before #2018 is protected",
        "one independent technical assessment and real non-author formal approval",
        "SELF_REVIEWED",
        "a second prompt in the builder's own context is SELF_REVIEWED",
        "On `EFFECT_UNKNOWN`",
        "original",
    ):
        assert required in policy, f"local-first cannot silently waive prior source: {required}"
    assert "Only after #2018's risk-tier source is protected" in agents
    assert "STANDARD's zero-extra-review rule is conditional" in claude
    assert "docs/SESSION_LOCAL_REVIEW_POLICY.md" in claude
    assert GUIDE in claude, "external avenue remains discoverable when genuinely needed"


def test_project_installed_fence_separates_native_review_from_formal_approval():
    block = _project_instructions(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))
    for guard in (
        "Native read-only child may review here",
        "child != GitHub APPROVED",
        "No denied/EFFECT_UNKNOWN review reroute",
        "Independent non-author review only when required",
        "No impersonation, self-review, duplicate or denial evasion",
        "Review: load " + GUIDE + " at pin.",
        "docs/SESSION_LOCAL_REVIEW_POLICY.md",
    ):
        assert guard in block, f"uninstalled outside-fence safeguard: {guard}"
    assert len(block.encode("utf-8")) <= 8000


def test_session_finishes_original_pr_not_draft_or_ci_handoff():
    policy = _read("docs/SESSION_LOCAL_REVIEW_POLICY.md")
    agents = _read("AGENTS.md")
    for required in (
        "Finish-to-release ownership",
        "A draft, comment, reviewer request, CI observation, checkpoint",
        "existing",
        "no self-merge",
    ):
        assert required.lower() in policy.lower()
    assert "Finish the actual PR, not its draft" in agents
    assert "do not" in policy.lower() and "EFFECT_UNKNOWN" in policy
