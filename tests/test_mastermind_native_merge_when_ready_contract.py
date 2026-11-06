"""Regression contract for Mastermind native merge-when-ready instructions.

These source checks do not arm, enqueue or merge a live PR. Required CI,
GitHub native rules and release holds remain independent production gates.
"""
from __future__ import annotations

from pathlib import Path
import re
import shlex

import pytest


DELIVERY = Path(__file__).resolve().parents[1] / "docs/DELIVERY_WORKFLOW.md"
MACRO_HEADER = "## Macro release: `merge-on-green` is opt-in, not native auto-merge"
START = "6. **Enroll a qualified Ready PR in native Merge when ready without waiting for pending CI.**"
END = "7. Deploy only when the assigned change requires runtime rollout"


def _sections(source: str) -> tuple[str, str]:
    mastermind, marker, macro = source.partition(MACRO_HEADER)
    assert marker, "Macro controller exception must remain explicit"
    before, marker, release = mastermind.partition(START)
    assert marker, "Mastermind early auto-merge enrollment is missing"
    release, marker, after = release.partition(END)
    assert marker, "Native release step must precede actual deployment"
    assert before and after
    return release, macro


def _assert_release_contract(release: str) -> None:
    source = " ".join(release.split())
    assert "The assigned session owns this routine release request" in source
    for required in (
        "do not introduce a second non-author arming ceremony",
        "re-read the exact GitHub repository",
        "protected `master` base",
        "full current 40-hex head SHA",
        "actual native/CODEOWNERS reviews",
        "explicit HOLD/STOP/security restrictions",
        "source-writer and effect custody",
        "current trusted required-check conclusions",
        "armed while required hosted CI is pending",
        "a Draft, incomplete source, known failing check",
        "conflict, missing/ambiguous enforcement evidence or binding hold",
        "autoMergeRequest",
        "mergeQueueEntry",
        "REST `auto_merge=null` alone does not prove a PR is unqueued",
        "preserve that existing effect rather than submitting another",
        "An ambiguous reply requires reading the **same** PR/queue",
        "A changed head requires fresh source, hold, review and CI qualification",
        "Only GitHub's enforced PR-head checks and native `merge_group`",
        "Read the actual merged PR and commit before claiming release",
        "Branch cleanup remains queue/repository-owned after merge; the native CLI"
        " does not support `--delete-branch` during queue enrollment",
    ):
        assert required in source, required

    fenced = re.search(r"```bash\s*\n\s*(gh pr merge [\s\S]+?)\n\s*```", release)
    assert fenced is not None, "Expected one explicit native command"
    command = re.sub(r"\\\s*\n\s*", " ", fenced.group(1))
    assert shlex.split(command) == [
        "gh", "pr", "merge", "<PR>",
        "--repo", "mastermindx-market-intelligence/Mastermind",
        "--auto", "--squash",
        "--match-head-commit", "<CURRENT_40_HEX_HEAD>",
    ], "Wrong repository, missing --auto/head lease or unsafe native release flags"


def test_qualified_mastermind_ready_pr_enrolls_before_ci_concludes() -> None:
    release, macro = _sections(DELIVERY.read_text(encoding="utf-8"))
    _assert_release_contract(release)
    assert "**Never use GitHub's native `gh pr merge --auto`" in macro
    assert "macro/.github/workflows/merge-on-green.yml" in macro


@pytest.mark.parametrize("required", [
    "do not introduce a second non-author arming ceremony",
    "full current 40-hex head SHA",
    "actual native/CODEOWNERS reviews",
    "explicit HOLD/STOP/security restrictions",
    "source-writer and effect custody",
    "armed while required hosted CI is pending",
    "a Draft, incomplete source, known failing check",
    "autoMergeRequest",
    "mergeQueueEntry",
    "REST `auto_merge=null` alone does not prove a PR is unqueued",
    "An ambiguous reply requires reading the **same** PR/queue",
    "A changed head requires fresh source, hold, review and CI qualification",
    "Read the actual merged PR and commit before claiming release",
])
def test_removing_a_binding_native_release_gate_fails_closed(required: str) -> None:
    release, _ = _sections(DELIVERY.read_text(encoding="utf-8"))
    _assert_release_contract(release)
    assert required in " ".join(release.split())
    # Match original whitespace/newline wrapping; a literal replacement would
    # silently miss long phrases and falsely report a negative regression.
    pattern = r"\s+".join(map(re.escape, required.split()))
    damaged, count = re.subn(pattern, "", release, count=1)
    assert count == 1, required
    with pytest.raises(AssertionError):
        _assert_release_contract(damaged)


@pytest.mark.parametrize("removed", [
    "--auto", "--squash", "--match-head-commit",
    "mastermindx-market-intelligence/Mastermind",
    "<CURRENT_40_HEX_HEAD>",
])
def test_native_command_mutation_is_rejected(removed: str) -> None:
    release, _ = _sections(DELIVERY.read_text(encoding="utf-8"))
    _assert_release_contract(release)
    before, separator, fenced_and_after = release.partition("```bash")
    assert separator and removed in fenced_and_after
    # Mutate the actual command, not a preceding narrative repository mention.
    damaged = before + separator + fenced_and_after.replace(removed, "", 1)
    with pytest.raises(AssertionError):
        _assert_release_contract(damaged)


@pytest.mark.parametrize("unsupported", ["--delete-branch", "--admin"])
def test_unsupported_native_queue_flag_is_rejected(unsupported: str) -> None:
    release, _ = _sections(DELIVERY.read_text(encoding="utf-8"))
    _assert_release_contract(release)
    before, opening, fenced_and_after = release.partition("```bash")
    assert opening
    command, closing, after = fenced_and_after.partition("```")
    assert closing and command.count("--auto --squash") == 1
    damaged_command = command.replace("--auto --squash", "--auto --squash " + unsupported, 1)
    assert damaged_command != command
    damaged = before + opening + damaged_command + closing + after
    with pytest.raises(AssertionError):
        _assert_release_contract(damaged)
