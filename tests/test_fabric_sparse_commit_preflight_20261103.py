"""Prevent unqualified local pins from reaching the sparse workspace helper.

Real temporary Git objects exercise missing, blob, tree and annotated-tag pins.
Fault injection covers observer uncertainty and the remaining preflight race.
No provider, live host, real lease or production workspace is used.
"""
from __future__ import annotations

import pytest

import test_fabric_native_security_composition_20261018 as composition
import test_fabric_clean_linked_donor_20261017 as donor_contract

applied = composition.applied
module = composition.module
repository = composition.repository


def assert_no_helper_effect(f):
    assert f.calls == []
    assert not (f.home / "lanes/wt" / f.key).exists()
    assert not (f.here / "lanes" / (f.key + ".workspace-mint.process.jsonl")).exists()
    assert (f.original / "preserve.txt").read_text() == "ORIGINAL UNCOMMITTED WORK\n"


def test_missing_local_pin_refuses_before_workspace_helper(repository, monkeypatch):
    f = repository
    before = donor_contract._git(f.original, "worktree", "list", "--porcelain")
    monkeypatch.setenv("FABRIC_NEW_MACRO_COMMIT", "0" * 40)
    with pytest.raises(f.module["SparseWorkspaceRefused"],
                       match="PINNED_COMMIT_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown
    assert_no_helper_effect(f)
    assert donor_contract._git(f.original, "worktree", "list", "--porcelain") == before


@pytest.mark.parametrize("kind", ["blob", "tree", "tag"])
def test_noncommit_object_refuses_before_workspace_helper(repository, monkeypatch, kind):
    f = repository
    if kind == "blob":
        pin = donor_contract._git(f.original, "rev-parse", f.head + ":preserve.txt")
    elif kind == "tree":
        pin = donor_contract._git(f.original, "rev-parse", f.head + "^{tree}")
    else:
        donor_contract._git(f.original, "tag", "-a", "pin-fixture", "-m",
                            "inert annotated tag", f.head)
        pin = donor_contract._git(f.original, "rev-parse", "refs/tags/pin-fixture")
    assert donor_contract._git(f.original, "cat-file", "-t", pin) == kind
    monkeypatch.setenv("FABRIC_NEW_MACRO_COMMIT", pin)
    with pytest.raises(f.module["SparseWorkspaceRefused"],
                       match="PINNED_COMMIT_UNQUALIFIED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown
    assert_no_helper_effect(f)


@pytest.mark.parametrize("reason", [
    "FABRIC_SPARSE_GIT_CLEANUP_UNKNOWN",
    "FABRIC_SPARSE_GIT_OBSERVATION_UNQUALIFIED",
])
def test_uncertain_observer_is_preserved_without_starting_helper(repository, monkeypatch, reason):
    f = repository
    original = f.module["_sparse_git"]
    failure = f.module["SparseWorkspaceRefused"](reason, effect_unknown=True)

    def observe(root, common, *args, **kwargs):
        if args == ("cat-file", "-t", f.head):
            assert root == f.alternate
            assert common == f.original / ".git"
            raise failure
        return original(root, common, *args, **kwargs)

    monkeypatch.setitem(f.module, "_sparse_git", observe)
    with pytest.raises(f.module["SparseWorkspaceRefused"]) as raised:
        f.invoke()
    assert raised.value is failure
    assert raised.value.effect_unknown
    assert_no_helper_effect(f)


def test_unexpected_observer_failure_is_not_reclassified(repository, monkeypatch):
    f = repository
    original = f.module["_sparse_git"]
    failure = RuntimeError("inert unexpected observer failure")

    def observe(root, common, *args, **kwargs):
        if args == ("cat-file", "-t", f.head):
            raise failure
        return original(root, common, *args, **kwargs)

    monkeypatch.setitem(f.module, "_sparse_git", observe)
    with pytest.raises(RuntimeError) as raised:
        f.invoke()
    assert raised.value is failure
    assert_no_helper_effect(f)


def test_helper_drift_during_pin_observation_still_refuses(repository, monkeypatch):
    f = repository
    original = f.module["_sparse_git"]

    def observe(root, common, *args, **kwargs):
        result = original(root, common, *args, **kwargs)
        if args == ("cat-file", "-t", f.head):
            assert result == b"commit\n"
            (f.alternate / "scripts/worktree_sparse.py").write_text(
                "# inert concurrent helper drift\n")
        return result

    monkeypatch.setitem(f.module, "_sparse_git", observe)
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="HELPER_CHANGED") as raised:
        f.invoke()
    assert not raised.value.effect_unknown
    assert_no_helper_effect(f)


def test_helper_failure_after_qualified_pin_stays_effect_unknown(repository):
    f = repository
    f.result.returncode = 1
    with pytest.raises(f.module["SparseWorkspaceRefused"], match="MINT_UNVERIFIED") as raised:
        f.invoke()
    assert raised.value.effect_unknown
    assert len(f.calls) == 1
    assert (f.home / "lanes/wt" / f.key).is_dir()
    assert f.calls[0][0][-1] == f.head


@pytest.mark.parametrize("dirty_kind", ["modified_tracked", "untracked"])
def test_advice_suppression_does_not_admit_dirty_excluded_content(repository, dirty_kind):
    f = repository
    excluded = f.alternate / "site"
    excluded.mkdir()
    filename = "keep.txt" if dirty_kind == "modified_tracked" else "new-untracked.fixture"
    (excluded / filename).write_text("UNCOMMITTED FIXTURE CONTENT\n")
    with pytest.raises(f.module["SparseWorkspaceRefused"]):
        f.invoke()
    assert_no_helper_effect(f)


def test_clean_materialized_tracked_content_is_preserved(repository):
    f = repository
    excluded = f.alternate / "site"
    excluded.mkdir()
    path = excluded / "keep.txt"
    path.write_text("tracked fixture\n")
    target = f.invoke()
    assert target == str(f.home / "lanes/wt" / f.key)
    assert len(f.calls) == 1
    assert path.read_text() == "tracked fixture\n"
    assert (f.original / "preserve.txt").read_text() == "ORIGINAL UNCOMMITTED WORK\n"
