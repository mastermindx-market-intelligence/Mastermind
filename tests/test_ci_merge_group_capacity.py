"""Merge-queue capacity policy: only required-check workflows run in queue groups.

GitHub's merge queue waits only for the branch's required status checks; for
Mastermind that is the CI workflow's ``test`` job (ruleset "Mastermind Default
Branch Merge Queue"). Every other workflow with a ``merge_group`` trigger runs
once per *built* queue group -- including groups that are later rebuilt or
discarded -- yet its result cannot hold or eject a merge. ``merge_group`` also
ignores path filters, so such a workflow runs for every group regardless of
what changed.

Measured 2026-11-09T13Z..2026-11-10T13Z: the three non-required merge_group
workflows (Hermes enrollment, Hermes inference, Mastermind OS) used ~21k run
wall-minutes, more than the required CI itself (~12k), and ~85% of it was for
groups that never landed. A non-required workflow proves landed changes with a
path-filtered ``push`` run on master instead.

To make a workflow required, add its check to the ruleset first, then add the
workflow here together with its ``merge_group`` trigger.
"""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Workflows whose jobs back a required status check of the master ruleset.
REQUIRED_CHECK_WORKFLOWS = frozenset({"ci.yml"})

# Former merge_group workflows: each keeps post-merge proof on master.
POST_MERGE_PROOF_WORKFLOWS = (
    "hermes-application-enrollment.yml",
    "hermes-application-inference.yml",
    "mastermind-os.yml",
)


def _load(path):
    # BaseLoader preserves GitHub's YAML 1.2 `on` key as a string.
    return yaml.load(path.read_text(), Loader=yaml.BaseLoader)


def _triggers(path):
    on = _load(path)["on"]
    if isinstance(on, str):
        return {on}
    return set(on)


def _workflow_files():
    return sorted(p for p in WORKFLOWS.iterdir() if p.suffix in {".yml", ".yaml"})


def test_only_required_check_workflows_run_in_merge_groups():
    offenders = sorted(
        path.name
        for path in _workflow_files()
        if "merge_group" in _triggers(path) and path.name not in REQUIRED_CHECK_WORKFLOWS
    )
    assert not offenders, (
        "non-required workflows must not run in merge-queue groups (they spend "
        f"runners on every built group without gating the merge): {offenders}"
    )


def test_required_check_workflows_still_run_in_merge_groups():
    for name in REQUIRED_CHECK_WORKFLOWS:
        on = _load(WORKFLOWS / name)["on"]
        assert "merge_group" in on, name
        assert on["merge_group"]["types"] == ["checks_requested"], name


def test_former_merge_group_workflows_keep_path_filtered_post_merge_proof():
    for name in POST_MERGE_PROOF_WORKFLOWS:
        on = _load(WORKFLOWS / name)["on"]
        assert "merge_group" not in on, name
        assert on["push"]["branches"] == ["master"], name
        assert on["push"]["paths"], name
        assert on["pull_request"]["paths"], name


def test_enrollment_post_merge_paths_mirror_its_pull_request_paths():
    on = _load(WORKFLOWS / "hermes-application-enrollment.yml")["on"]
    assert on["push"]["paths"] == on["pull_request"]["paths"]
