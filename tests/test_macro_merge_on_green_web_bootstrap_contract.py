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
    return all(
        snippet in _approved_project_block(text)
        for snippet in (
            "9A. Macro `merge-on-green`:",
            "docs/DELIVERY_WORKFLOW.md",
            "Never bulk-arm.",
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
        "6A. Named reviewer login",
        "33. MORE_WORK_EXISTS means the mission is incomplete",
        "39. Persist results/rulings/continuations",
        "40. Grok Secretary",
        "Review: load docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md at pin.",
    ):
        assert anchor in block, f"incumbent #1987 instruction lost: {anchor}"
    assert DELIVERY.is_file()


def test_outside_fence_release_note_does_not_count_as_installed_instruction():
    kernel = KERNEL.read_text(encoding="utf-8")
    assert _contains_macro_release_instruction(kernel)
    moved = kernel.replace(
        "9A. Macro `merge-on-green`: docs/DELIVERY_WORKFLOW.md. Never bulk-arm.",
        "",
    )
    assert moved != kernel, "the exact projected rule must exist in the source"
    assert not _contains_macro_release_instruction(moved)
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
        "Only when release is **actually authorized**",
        "gh pr edit <number> --repo mastermindx-market-intelligence/macro --add-label merge-on-green",
        "failure-marker pass",
        "global CI workload cap",
        "native `gh pr merge --auto`",
        "PROVEN_LIVE",
    ):
        assert token in section, f"Macro release gate lost: {token}"
    assert section.index("Verify **one genuinely independent formal GitHub APPROVED review**") < section.index(
        "Only when release is **actually authorized**"
    ), "release opt-in must come after non-author and hold checks"


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
        "independent non-author arming/release decision",
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



def _assert_review_once_automatic_release_transition(delivery: str, account: str) -> None:
    section = delivery.split(
        "### Review once, release automatically — only after machine enforcement", 1
    )[1].split("`merge-blocked` is a refusal/diagnostic", 1)[0]
    for token in (
        "one independent source review",
        "not yet live authority",
        "absent, stale, revoked, self-authored and unreadable reviews",
        "CHANGES_REQUESTED",
        "installed, independently qualified and read back",
        "without an additional non-author release operator",
        "admin bypass",
    ):
        assert token in section, f"automatic release safety contract lost: {token}"
    interim = delivery.split(
        "3. Verify **one genuinely independent formal GitHub APPROVED review**", 1
    )[1].split("5. Reconcile the **existing controller**", 1)[0]
    assert "**current interim non-author release fence**" in interim
    assert "Macro's sweeper does not yet read native PR" in interim
    assert "eligible independent release/arming actor must verify" in interim
    assert "Macro\'s existing sweeper does not check formal" in section
    assert "retain the current" in account
    assert "independent non-author arming/release decision" in account
    assert "review once and let existing automation perform" in account


def test_review_once_auto_release_preserves_interim_and_machine_enforcement():
    delivery = DELIVERY.read_text(encoding="utf-8")
    account = (ROOT / "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md").read_text(
        encoding="utf-8"
    )
    _assert_review_once_automatic_release_transition(delivery, account)

    import pytest

    for removed in (
        "**current interim non-author release fence**",
        "Macro's sweeper does not yet read native PR",
        "eligible independent release/arming actor must verify",
        "installed, independently qualified and read back",
        "absent, stale, revoked, self-authored and unreadable reviews",
    ):
        damaged = delivery.replace(removed, "UNVERIFIED", 1)
        assert damaged != delivery
        with pytest.raises(AssertionError):
            _assert_review_once_automatic_release_transition(damaged, account)
    damaged_account = account.replace(
        "independent non-author arming/release decision",
        "self-release approved", 1
    )
    assert damaged_account != account
    with pytest.raises(AssertionError):
        _assert_review_once_automatic_release_transition(delivery, damaged_account)
