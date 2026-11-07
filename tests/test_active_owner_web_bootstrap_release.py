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
    # Protected #1999 added this real source-law rule on master after the
    # original candidate. A passing standalone 8k check is insufficient:
    # the integrated Project fence must still fit after the accepted rule.
    block = _project_block()
    macro_rule = "9A. Macro `merge-on-green`: docs/DELIVERY_WORKFLOW.md. Never bulk-arm."
    assert macro_rule in block, "retain accepted #1999 Macro rule"
    assert len(block.encode("utf-8")) <= 8000
    assert "Native child != GitHub APPROVED." in block
    assert "denied/EFFECT_UNKNOWN reroute." in block


def test_live_account_owner_and_exact_safety_fences_are_in_installed_fence():
    block = _project_block()
    for phrase in (
        "Archived",
        "Current assigned receiver owns recovery",
        "Archived chats/PR authors aren't live owners",
        "Handoffs name an executable successor action",
        "Native CRITICAL tier: one distinct review",
        "never native Sol labor",
        "First explicit safety/permission denial",
        "EFFECT_UNKNOWN",
        "Never self-approve/bypass protection",
    ):
        assert phrase in block


def test_formal_review_eligibility_and_handoff_remain_inside_fence():
    block = _project_block()
    for phrase in (
        "6A. No named-seat lock absent binding rule",
        "independent of PR authors/committers/coauthors",
        "No impersonation, self-approval, duplicate or denied/EFFECT_UNKNOWN reroute",
        "HANDOFF_SOURCE_LINK_V1",
        "Delivery != PICKUP_ACK/START",
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
