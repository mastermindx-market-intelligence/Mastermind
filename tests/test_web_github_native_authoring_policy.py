"""Instruction-level regression for GitHub-native source authoring parity.

This validates source documents, not connector installation or protected release.
GitHub credentials, actual writer custody, CI, branch rules and PR effects are
still enforced by their respective owners.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_native_authoring_is_explicit_and_distinct_from_host_workspace() -> None:
    workflow = _read("docs/DELIVERY_WORKFLOW.md")
    assert "### GitHub-native authoring (no host worktree required)" in workflow
    assert "### Host-local worktree authoring" in workflow
    for required in (
        "without** `mmx-workspace`",
        "compare-and-swap",
        "current file blob SHA",
        "without a local runner",
        "GitHub-native authors without a local test runner may publish",
        "An ambiguous mutation response requires original-branch",
        "an explicit safety/permission denial is final",
        "No local `git push` or launcher receipt is",
        "Only if this operation acquired a host-local",
    ):
        assert required.lower() in workflow.lower(), required


def test_release_controls_still_bind_both_routes() -> None:
    # Markdown may wrap a guard between words; verify semantic text without
    # weakening any of the actual release-control keywords or commands.
    workflow = " ".join(_read("docs/DELIVERY_WORKFLOW.md").split())
    for required in (
        "Never force-update a shared ref",
        "write directly to `master`",
        "actual release hold or formal approval",
        "full current 40-hex head SHA",
        "mergeQueueEntry",
        "--match-head-commit",
        "Only GitHub's enforced PR-head checks",
        "NEVER use GitHub's native",
    ):
        assert required.lower() in workflow.lower(), required


def test_all_principal_entrypoints_advertise_the_same_route() -> None:
    for path, markers in {
        "AGENTS.md": ("GitHub-native authoring is allowed without a host worktree", "Host-local authoring keeps host-local safeguards"),
        "CLAUDE.md": ("Source-authoring surfaces are alternatives", "host-selected workspace launcher"),
        "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md": ("First-class GitHub-native source authoring", "protected GitHub review/CI/merge queue"),
        "docs/sol_skills/BOOTSTRAP_KERNEL.md": ("6B. GITHUB-NATIVE AUTHORING:", "No denied-effect/EFFECT_UNKNOWN carrier swap"),
    }.items():
        source = _read(path)
        for marker in markers:
            assert marker in source, (path, marker)


def test_web_project_instruction_text_fits_8000_characters() -> None:
    source = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    _, marker, fenced = source.partition("```text\n")
    assert marker
    payload, closing, _ = fenced.partition("```")
    assert closing and payload.startswith("MASTERMIND SOL BOOTSTRAP")
    assert len(payload) <= 8000

def test_mastermind_merge_queue_auto_arm_omits_unsupported_branch_deletion() -> None:
    """A real queue rejected --delete-branch before creating an arm request."""
    workflow = _read("docs/DELIVERY_WORKFLOW.md")
    _, marker, release = workflow.partition(
        "this head-leased request against the exact qualified candidate:"
    )
    assert marker
    _, fenced, command = release.partition("```bash\n")
    assert fenced
    command, ending, _ = command.partition("```")
    assert ending
    assert "gh pr merge <PR>" in command
    assert "--auto --squash" in command
    assert "--match-head-commit <CURRENT_40_HEX_HEAD>" in command
    assert "--delete-branch" not in command
    assert "GitHub CLI refuses `--delete-branch`" in release
