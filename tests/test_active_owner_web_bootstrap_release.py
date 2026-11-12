"""Contract tests for source-pinned Web Project owner-takeover rollout.

Source publication, live Project installation and real agent behavior are separate.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md"
ACCOUNT = ROOT / "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md"


def _project_block() -> str:
    source = KERNEL.read_text(encoding="utf-8")
    return source.split("## Approved Project instruction text", 1)[1].split(
        "```text\n", 1
    )[1].split("\n```", 1)[0]


def test_project_block_fits_both_real_limits_and_has_exact_unique_rules():
    block = _project_block()
    assert len(block) <= 8000
    assert len(block.encode("utf-8")) <= 8000
    for number in ("5.", "6A.", "13.", "39.", "40."):
        assert sum(line.startswith(number + " ") for line in block.splitlines()) == 1



def test_accepted_macro_merge_rule_can_fit_when_composed_with_this_kernel():
    # The accepted Macro opt-in remains governed by the release workflow;
    # the compact Project must retain the pointer and never bulk-arm PRs.
    block = _project_block()
    for guard in (
        "9A. TASK FIRST:",
        "docs/DELIVERY_WORKFLOW.md",
        "Never bulk-arm/clear other holds",
        "Native review != GitHub APPROVED",
        "Tool-specific technical errors require diagnosis; reconcile unknown modifying effects",
    ):
        assert guard in block, f"accepted release guard missing: {guard}"
    assert len(block.encode("utf-8")) <= 8000


def test_live_account_owner_and_exact_safety_fences_are_in_installed_fence():
    block = _project_block()
    for phrase in (
        "Assigned session owns recovery",
        "not old chats/authors/roles",
        "No dead-chat handback",
        "HANDOFF_SOURCE_LINK_V1",
        "Native CRITICAL keeps actual distinct review",
        "no blanket independent technical/source review",
        "Restrict only proven denied effects",
        "EFFECT_UNKNOWN",
        "never self-approve/self-merge/falsify/bypass",
    ):
        assert phrase in block


def test_formal_review_eligibility_and_handoff_remain_inside_fence():
    block = _project_block()
    for phrase in (
        "6A. No named reviewer seat absent binding rule",
        "Verify login, authors/coauthors, head and prior reviews",
        "No impersonation/duplicate/uncertain review",
        "HANDOFF_SOURCE_LINK_V1",
        "Delivery != pickup/START",
        "<@U0BTCHX8HMF>",
        "Never DM.",
    ):
        assert phrase in block

def test_project_installation_needs_editor_readback_and_behavioral_canary():
    instructions = ACCOUNT.read_text(encoding="utf-8")
    for phrase in (
        "each **distinct** authorized Mastermind Project",
        "preserving newer valid Project-specific rules",
        "8,000-character and UTF-8 byte budgets",
        "fresh-chat action scenarios per intended member account",
        "UNKNOWN/BLOCKED gap",
        "not proof of ChatGPT settings installation",
    ):
        assert phrase in instructions


def test_native_guidance_uses_one_genuine_non_author_review_owner():
    for name in ("AGENTS.md", "CLAUDE.md"):
        entry = (ROOT / name).read_text(encoding="utf-8")
        assert "reviewer login is a **placement preference, not an owner wait**" in entry
        assert "same reasoning session between two GitHub accounts" in entry
        assert "No impersonation, false independent-review claim" in entry
    review = (ROOT / "docs/sol_skills/REVIEW_RETURN.md").read_text(encoding="utf-8")
    for phrase in (
        "not an exclusive owner/approver",
        "A different connector login in the **same underlying reasoning session**",
        "full current head SHA",
        "one native submitted GitHub review",
        "review ID",
        "`commit_id`",
        "not a formal",
    ):
        assert phrase in review


def test_native_installer_retires_our_takeover_block_preserving_old_m2():
    installer = (ROOT / "scripts/project_execution_brief.py").read_text(encoding="utf-8")
    assert "'mastermind-active-owner-takeover-20261102'" in installer
    assert "'mastermind-leadership-continuity-20261024'" in installer
    assert "retire this exact superseded blanket review/release sentence" in installer
    account = ACCOUNT.read_text(encoding="utf-8")
    for term in (
        "scripts/project_execution_brief.py",
        "Preview before applying",
        "no conflicting writer",
        "backup and post-write readback",
        "preferred placement, not a permanent owner",
        "different reasoning reviewer",
    ):
        assert term in account
