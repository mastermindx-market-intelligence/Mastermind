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
    # The compact Project carries enforceable review safety; the optional
    # detail guide remains discoverable from protected source, not a forced hop.
    for required in (
        "5A. CHATGPT WEB REVIEW WAIVER, all tiers:",
        "Real non-author APPROVED only where required",
        "Native review != GitHub APPROVED",
        "No extra review/handoff ceremony",
    ):
        assert required in block, required
    assert GUIDE in kernel
    assert "docs/SESSION_LOCAL_REVIEW_POLICY.md" in kernel
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
    guard = "5A. CHATGPT WEB REVIEW WAIVER, all tiers:"
    assert guard in _project_instructions(kernel)
    # Moving an actual waiver marker outside the installed fence cannot
    # count as a Project instruction, even if it remains in Markdown.
    moved = kernel.replace(guard, "", 1) + "\n" + guard
    assert moved != kernel
    assert guard not in _project_instructions(moved)
    assert guard in moved
    assert GUIDE in moved

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


def test_session_local_review_all_tiers_preserves_actual_native_gates():
    policy = _read("docs/SESSION_LOCAL_REVIEW_POLICY.md")
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")
    for required in (
        "Attended CEO Web FAST / STANDARD / CRITICAL",
        "Zero blanket independent technical reviewers",
        "Native/automatic CRITICAL requires one distinct read-only technical reviewer",
        "signed AUTOMATIC GitHub/Executive",
        "native GitHub/CODEOWNERS",
        "SELF_REVIEWED",
        "EFFECT_UNKNOWN",
        "original",
        "protected-accepted and actually loaded",
        "FAST0/0, STANDARD0/0 and CRITICAL1/0",
        "Review-host enrollment",
        "OFF unless separately authorized and enabled",
        "Explicit review requests, native rules, CODEOWNERS",
        "recorded holds and release controls remain binding",
        "Repository source is not proof of installed instructions",
        "a second prompt in the builder's own context is SELF_REVIEWED",
        "On `EFFECT_UNKNOWN`",
    ):
        assert required in policy, f"missing all-tier attended waiver or gate: {required}"
    assert "Before #2018 is protected" not in policy
    assert "CRITICAL's two technical perspectives must show" not in policy
    assert "docs/SESSION_LOCAL_REVIEW_POLICY.md" in claude
    assert GUIDE in claude, "optional lawful external review remains discoverable"
    assert "No review-host enrollment" in agents
    assert "native GitHub/CODEOWNERS protections" in agents
    assert "Ordinary reversible FAST/STANDARD changes" in claude
    assert "proves neither instruction installation nor changed machine enforcement" in claude
    guide = _read(GUIDE)
    assert "## First gate: which review obligation actually applies?" in guide
    assert "Ordinary reversible FAST/STANDARD" in guide
    assert "These reviewer START/commission canaries apply only" in guide
    assert "no unwanted Fabric/Dot review operation" in guide
    assert "Source text does not prove" in guide and "installation" in guide



def test_project_installed_fence_separates_native_review_from_formal_approval():
    block = _project_instructions(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))
    for guard in (
        "Native review != GitHub APPROVED",
        "Real non-author APPROVED only where required",
        "Tool-specific technical errors require diagnosis; reconcile unknown modifying effects",
        "No extra review/handoff ceremony",
        "No impersonation/duplicate/uncertain review",
        "GitHub/CODEOWNERS/security/release holds bind",
    ):
        assert guard in block, f"uninstalled outside-fence safeguard: {guard}"
    assert len(block.encode("utf-8")) <= 8000


def test_project_kernel_explicit_all_tier_web_waiver_and_handoff_exemption():
    block = _project_instructions(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))
    assert "5A. CHATGPT WEB REVIEW WAIVER, all tiers:" in block
    for guard in (
        "no blanket independent technical/source review",
        "Self-check diff, focused tests, required CI/proof",
        "GitHub/CODEOWNERS/security/release holds bind",
        "never self-approve/self-merge/falsify/bypass",
        "No independent review solely for handoff",
        "HANDOFF_SOURCE_LINK_V1",
        "9A. TASK FIRST",
    ):
        assert guard in block, f"required actual Project-fence clause missing: {guard}"
    numbered = [line.split(".", 1)[0] for line in block.splitlines() if line[:1].isdigit()]
    assert set(map(str, range(1, 41))).issubset(numbered)
    assert {"5A", "6A", "9A"}.issubset(numbered)
    assert len(block.encode("utf-8")) <= 8000

def test_session_finishes_original_pr_not_draft_or_ci_handoff():
    policy = _read("docs/SESSION_LOCAL_REVIEW_POLICY.md")
    agents = _read("AGENTS.md")
    for required in (
        "Finish-to-release ownership",
        "A draft, comment, reviewer request, CI observation, checkpoint",
        "existing",
        "Normal automated release",
    ):
        assert required.lower() in policy.lower()
    assert "Finish the actual PR, not its draft" in agents
    assert "do not" in policy.lower() and "EFFECT_UNKNOWN" in policy
