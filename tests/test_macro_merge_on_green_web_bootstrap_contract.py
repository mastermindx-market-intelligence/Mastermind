"""Source-only regression for Web CEO Macro merge-on-green release instructions.

The Project code fence is the deployable instruction payload. These checks do
not claim that it is installed in the active ChatGPT Project, that a native
review exists, or that any PR has been merged.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "docs/sol_skills/BOOTSTRAP_KERNEL.md"
DELIVERY = ROOT / "docs/DELIVERY_WORKFLOW.md"


def _approved_project_block(text: str) -> str:
    return text.split("## Approved Project instruction text", 1)[1].split(
        "```text\n", 1
    )[1].split("\n```", 1)[0]



def _contains_macro_release_instruction(text: str) -> bool:
    # Accepted Macro opt-in still lives in DELIVERY_WORKFLOW; the compact
    # one-pass rule routes there and must never bulk-arm other PRs.
    return all(
        snippet in _approved_project_block(text)
        for snippet in (
            "9A. TASK FIRST:",
            "docs/DELIVERY_WORKFLOW.md",
            "actual repo controls/opt-ins govern",
            "Never bulk-arm/clear other holds",
        )
    )


def test_actual_web_project_block_exposes_release_pointer_within_budget():
    kernel = KERNEL.read_text(encoding="utf-8")
    block = _approved_project_block(kernel)
    assert _contains_macro_release_instruction(kernel)
    assert block.startswith("MASTERMIND SOL BOOTSTRAP")
    assert len(block) <= 8000
    assert len(block.encode("utf-8")) <= 8000
    for anchor in (
        "6A. No named reviewer seat absent binding rule",
        "33. MORE_WORK_EXISTS is incomplete",
        "39. Persist rulings/results to canonical owners",
        "40. Grok Secretary",
        "5A. CHATGPT WEB REVIEW WAIVER",
    ):
        assert anchor in block, f"incumbent release safety lost: {anchor}"
    assert DELIVERY.is_file()


def test_outside_fence_release_note_does_not_count_as_installed_instruction():
    kernel = KERNEL.read_text(encoding="utf-8")
    assert _contains_macro_release_instruction(kernel)
    marker = "9A. TASK FIRST:"
    moved = kernel.replace(marker, "", 1) + "\n" + marker
    assert moved != kernel, "actual projected release pointer must exist"
    assert not _contains_macro_release_instruction(moved)
    assert marker in moved
    assert "Cross-session PR release and auto-merge discoverability" in moved

def test_release_procedure_requires_review_holds_ci_and_real_sweeper_readback():
    delivery = DELIVERY.read_text(encoding="utf-8")
    section = delivery.split(
        "## Macro release: `merge-on-green` is opt-in, not native auto-merge",
        1,
    )[1].split("## Review-readiness liveness", 1)[0]
    for token in (
        "macro/main",
        "can_arm_merge_on_green",
        "HOLD-RELEASED",
        "APPROVED",
        "Fabric",
        "Once the required checks, applicable review and holds are satisfied",
        "gh pr edit <number> --repo mastermindx-market-intelligence/macro --add-label merge-on-green",
        "failure-marker pass",
        "global CI workload cap",
        "native `gh pr merge --auto`",
        "PROVEN_LIVE",
    ):
        assert token in section, f"Macro release gate lost: {token}"
    assert section.index("Apply only the review actually required") < section.index(
        "Once the required checks, applicable review and holds are satisfied"
    ), "release opt-in must follow applicable qualification and hold checks"


def test_account_entrypoint_routes_macros_and_other_repos_differently():
    source = (ROOT / "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md").read_text(
        encoding="utf-8"
    )
    section = source.split(
        "## Cross-repository PR auto-merge discipline", 1
    )[1].split("## Preserve real controls and prove the result", 1)[0]
    for token in (
        "docs/DELIVERY_WORKFLOW.md",
        "merge-on-green",
        "binding CI",
        "assigned session",
        "recorded holds",
        "main",
        "master",
        "Project setting",
    ):
        assert token in section



def _macro_release_commands(section: str) -> list[str]:
    """Only operative PR/sweeper commands, not the explicitly forbidden --auto."""
    import re

    return re.findall(
        r"`(gh (?:pr (?:edit|view)|run (?:list|view)) [^`]+)`",
        section,
    )


def _assert_explicit_macro_repo_binding(section: str) -> None:
    commands = _macro_release_commands(section)
    assert len(commands) == 4, "every listed operative command must be checked"
    for command in commands:
        words = command.split()
        assert words.count("--repo") == 1, (
            f"no implicit repository or duplicate repository selection: {command}"
        )
        assert words[words.index("--repo") + 1] == (
            "mastermindx-market-intelligence/macro"
        ), f"command would target wrong GitHub repository: {command}"


def test_cross_repository_macro_gh_commands_are_explicitly_bound():
    section = DELIVERY.read_text(encoding="utf-8").split(
        "## Macro release: `merge-on-green` is opt-in, not native auto-merge", 1
    )[1].split("## Review-readiness liveness", 1)[0]
    _assert_explicit_macro_repo_binding(section)

    import pytest

    for defective in (
        section.replace(
            "gh pr edit <number> --repo mastermindx-market-intelligence/macro",
            "gh pr edit <number>",
        ),
        section.replace(
            "gh run view <run-id> --repo mastermindx-market-intelligence/macro",
            "gh run view <run-id> --repo mastermindx-market-intelligence/Mastermind",
        ),
        section.replace(
            "gh pr view <number> --repo mastermindx-market-intelligence/macro",
            "gh pr view <number> --repo mastermindx-market-intelligence/Mastermind",
        ),
    ):
        assert defective != section, "negative mutation must change a command"
        with pytest.raises(AssertionError):
            _assert_explicit_macro_repo_binding(defective)



def _assert_proportionate_automatic_release(delivery: str) -> None:
    ordinary = delivery.split("## One qualification, normal protected release", 1)[1]
    for token in (
        "Ordinary reversible FAST/STANDARD",
        "No independent technical review, formal approval, separate release operator",
        "**one** distinct native/Fabric technical review",
        "CEO-Web all-tier self-review waiver remains",
        "only when an actual repository rule or specific binding hold requires it",
        "No additional non-author arming ceremony",
        "Until a prospective controller",
        "preserve its actual enforced behavior",
        "Missing or unreadable enforcement data must fail closed",
        "Never use REST/admin bypass",
    ):
        assert token in ordinary, token
    for obsolete in (
        "current interim non-author release fence",
        "eligible independent release/arming actor must verify",
        "Verify **one genuinely independent formal GitHub APPROVED review**",
    ):
        assert obsolete not in delivery


def test_ordinary_release_removes_internal_arming_gate_preserves_real_controls():
    import pytest

    delivery = DELIVERY.read_text(encoding="utf-8")
    _assert_proportionate_automatic_release(delivery)
    # Losing a real enforcement fence is a regression even when routine review
    # counts remain zero. Reject that mutation, not merely a renamed heading.
    for removed in (
        "preserve its actual enforced behavior",
        "Missing or unreadable enforcement data must fail closed",
        "Never use REST/admin bypass",
    ):
        damaged = delivery.replace(removed, "", 1)
        assert damaged != delivery
        with pytest.raises(AssertionError):
            _assert_proportionate_automatic_release(damaged)
