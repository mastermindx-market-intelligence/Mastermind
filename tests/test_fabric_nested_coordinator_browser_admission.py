"""Nested original-root V5 Job → existing Browser snapshot-only admission boundary.

Runs actual SQLite CooCycle/Attempt code plus the incumbent private worker
Browser tunnel. Provider/process attestation and BrowserRef are *fixtures*;
there is no real browser, Chrome consent, plugin installation or authority.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from control_plane.executive_runtime import AttemptLease, StateConflict
from tests import test_worker_browser_admission as browser_owner
from test_executive_coo_hierarchy_cycle import (
    finish_result, harness, plan_result,
)


def _nested_leaf(tmp_path):
    runtime, root, cycle, dispatches = harness(tmp_path)
    for _ in range(90):
        result = cycle.run_once(root.job_id)
        assert result.action not in {"BLOCKED", "RECONCILIATION_REQUIRED"}, result
        if result.action != "DISPATCHED":
            continue
        attempt = dispatches[-1]
        job = runtime.jobs.get_job(attempt.attempt.job_id)
        assert job is not None and job.root_job_id == root.job_id
        if job.depth == 3 and job.orchestration_role == "work":
            assert attempt.lease_token is not None
            return runtime, root, job, AttemptLease(
                attempt=attempt.attempt, lease_token=attempt.lease_token,
            )
        if job.orchestration_role == "plan":
            parent = runtime.jobs.get_job(job.parent_job_id)
            assert parent is not None
            delegation = (
                {"descendant_limit": 14 - 2 * parent.depth, "max_depth": 3}
                if parent.depth < 2 else None
            )
            plan_result(runtime, attempt, parent, delegation=delegation,
                        count=2 if parent.depth == 2 else 1)
        else:
            finish_result(runtime, attempt)
    raise AssertionError("never admitted the original-root depth-3 leaf")


def test_depth_three_browser_attempt_refuses_without_typed_principal(tmp_path, monkeypatch):
    """A nested Runtime Attempt is necessary, never sufficient Browser authority.

    The existing direct-leaf owner fixture omits the TX-4 typed principal
    observation because its standalone Job has no orchestration role. Reusing
    it with a *real* depth-three original-root CooCycle Job must instead refuse
    at the existing Runtime admission boundary, before Browser tool creation.
    A production principal cannot be fabricated by a Skill prompt/test caller.
    """
    runtime, original, leaf, lease = _nested_leaf(tmp_path / "nested")
    assert leaf.depth == 3 and leaf.root_job_id == original.job_id
    assert leaf.parent_job_id != original.job_id
    assert leaf.requested_authorities == ["READ"]
    assert leaf.allowed_write_paths == []
    assert lease.attempt.job_id == leaf.job_id

    old_grant = browser_owner._grant
    monkeypatch.setattr(
        browser_owner, "_grant",
        lambda configuration: old_grant(configuration, ("browser_snapshot",)),
    )
    monkeypatch.setattr(browser_owner, "_lease", lambda _: (runtime, lease))
    browser_root = tmp_path / "browser"
    browser_root.mkdir(mode=0o700)

    # The original standalone fixture gives the worker an observed fake
    # App Server attestation but lacks the trusted principal/placement/tx3
    # source required by TX-4 for nested orchestration roles. The Runtime
    # correctly refuses an ALLOW transition, rather than letting any Browser
    # resource be created from an opaque worker-provided reference.
    with pytest.raises(
        StateConflict, match="TX-4 ALLOW requires typed principal observation"
    ):
        browser_owner._setup(browser_root)

    assert runtime.jobs.get_job(leaf.job_id).root_job_id == original.job_id
    assert runtime.jobs.get_job(leaf.job_id).parent_job_id == leaf.parent_job_id
    artifact_dirs = list(browser_root.rglob("artifact-browser"))
    assert len(artifact_dirs) == 1
    assert not list(artifact_dirs[0].iterdir())
