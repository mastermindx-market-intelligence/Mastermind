"""Remote selected-host commission verification for the read-only planner.

These tests prove the production remote commission route of
:func:`control_plane.executive_supervisor.verify_commission_for_job` with a
real private Runtime (durable Job/Attempt/worker assignment, immutable root
dialogue source) and a mock canonical byte reader in place of the exact
bounded GitHub reader.

No test here performs provider, host, Git-transport, credential or network
effects: the remote workspace is removed before verification so any local
stat/resolve/Git read would fail loudly, ``_commission_git_probe`` is patched
to raise on every remote-route test, and the only network-touching code under
test is the production reader's pre-network destination guards exercised with
a fully faked opener.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.ceo_intent import INTENT_SCHEMA_V2, submit_intent
from control_plane.executive_runtime import (
    AttemptStatus,
    OrchestrationDispatchOutcome,
    Runtime,
)
from control_plane import executive_supervisor as executive_supervisor_mod
from control_plane.executive_supervisor import (
    SupervisorError,
    VerifiedCommission,
    verify_commission_for_job,
)
from control_plane.model_router import ModelRouter
from control_plane.operator_harness_contract import WorkspaceIdentity

_COMMISSION = b"# Remote operator commission\n\nUse this exact immutable brief.\n"
_CANONICAL_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_COMMISSION_PATH = "research/operator-commission.md"


class _Clock:
    def __init__(self) -> None:
        self.value = 1_900_000_000_000

    def __call__(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds * 1000


class _IdentitySubclass(WorkspaceIdentity):
    """Same fields, wrong exact type: a subclass is not admission."""


def _seed_remote_operator_planner(
    tmp_path: Path,
    *,
    content: bytes = _COMMISSION,
    repository: str = _CANONICAL_REPOSITORY,
    ref_commit: str | None = None,
    ref_path: str = _COMMISSION_PATH,
    digest: str | None = None,
    dispatch: bool = True,
    dialogue: bool = True,
) -> SimpleNamespace:
    """Seed one real commission-bound operator planner, exactly as armed."""

    clock = _Clock()
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "g2-planner"
    workspace.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "codex/g2-planner"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "fixture@mastermind.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Mastermind Fixture"],
        cwd=workspace,
        check=True,
    )
    (workspace / "README.md").write_text("G2 fixture\n", encoding="utf-8")
    commission_path = workspace / "research" / "operator-commission.md"
    commission_path.parent.mkdir(parents=True)
    commission_path.write_bytes(content)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    runtime = Runtime.at(tmp_path / "runtime", clock=clock, lease_seconds=30)
    router = ModelRouter.load()
    sealed = router.model_aliases["coo.sealed"]
    operator = router.model_aliases["coo.operator.readonly"]
    binding = {
        "eligible_quota_classes": ["codex-coo", "codex-coo-default"],
        "provider": sealed.provider_alias,
        "model": sealed.model,
        "effort": sealed.effort,
        "cost_class": sealed.cost_class,
        "base_sha": base_sha,
        "routing_policy_version": router.policy_version,
        "execution_profile_id": sealed.execution_profile_id,
        "execution_profile_digest": sealed.execution_profile_digest,
        "capability_policy_version": sealed.capability_policy_version,
        "capability_policy_digest": sealed.capability_policy_digest,
        "operator_eligible_quota_classes": ["codex-coo-operator"],
        "operator_provider": operator.provider_alias,
        "operator_model": operator.model,
        "operator_effort": operator.effort,
        "operator_cost_class": operator.cost_class,
        "operator_routing_policy_version": router.policy_version,
        "operator_execution_profile_id": operator.execution_profile_id,
        "operator_execution_profile_digest": operator.execution_profile_digest,
        "operator_capability_policy_version": operator.capability_policy_version,
        "operator_capability_policy_digest": operator.capability_policy_digest,
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "0.147.0",
        "operator_harness_armed": True,
    }
    runtime.workers.register_worker(
        "worker-a",
        provider=operator.provider_alias,
        account_label="worker-a@company",
        worker_type="fixture",
        capabilities=list(operator.capabilities),
        quota_classes={
            "codex-coo-operator": {
                "provider": operator.provider_alias,
                "model": operator.model,
                "effort": operator.effort,
                "cost_class": operator.cost_class,
                "capabilities": list(operator.capabilities),
                "metadata": {
                    "routing_policy_version": router.policy_version,
                    "execution_profile_id": operator.execution_profile_id,
                    "execution_profile_digest": operator.execution_profile_digest,
                    "capability_policy_version": operator.capability_policy_version,
                    "capability_policy_digest": operator.capability_policy_digest,
                    "harness_binary_digest": "a" * 64,
                    "harness_version": "0.147.0",
                },
            }
        },
    )
    intent = {
        "schema": INTENT_SCHEMA_V2,
        "intent_id": "CEO-REMOTE-COMMISSION-001",
        "actor": "ceo-sol",
        "objective": "Produce one bounded read-only execution plan remotely.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {"mastermind_sha": base_sha, "macro_sha": "b" * 40},
        "execution_contract": {
            "requested_authorities": ["READ"],
            "branch": "codex/g2-planner",
            "worktree": str(workspace),
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "routine",
    }
    dialogue_kwargs = {}
    if dialogue:
        intent["workstream"] = "WS:REMOTE-COMMISSION"
        dialogue_kwargs = {
            "dialogue_source": {
                "schema_version": "mastermind.executive_dialogue_source/v1",
                "work_ref": "WS:REMOTE-COMMISSION",
                "commission_ref": {
                    "repository": repository,
                    "commit": ref_commit or base_sha,
                    "path": ref_path,
                    "content_sha256": digest or hashlib.sha256(content).hexdigest(),
                },
                "watch_mode": None,
            },
            "require_dialogue_source": True,
        }
    receipt = submit_intent(
        runtime,
        intent,
        workspace_root=workspace_root,
        execution_binding=binding,
        **dialogue_kwargs,
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatch_outcome = None
    if dispatch:
        dispatch_outcome = runtime.attempts.dispatch_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
            worker_id="worker-a",
        )
        assert isinstance(dispatch_outcome, OrchestrationDispatchOutcome)
        assert dispatch_outcome.lease_token is not None
    return SimpleNamespace(
        clock=clock,
        runtime=runtime,
        root=root,
        planner=planner,
        dispatch=dispatch_outcome,
        workspace=workspace,
        base_sha=base_sha,
        content=content,
    )


def _qualified_identity(seeded: SimpleNamespace) -> WorkspaceIdentity:
    """Build the identity exactly as the selected host observed it."""

    info = Path(str(seeded.planner.worktree)).lstat()
    return WorkspaceIdentity(
        workspace_path=str(seeded.planner.worktree),
        base_sha=str(seeded.planner.constraints["base_sha"]),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        uid=int(info.st_uid),
        gid=int(info.st_gid),
    )


def _detach_remote_workspace(seeded: SimpleNamespace) -> None:
    """Remove the local copy: the real workspace lives on the selected host."""

    shutil.rmtree(seeded.workspace)
    assert not Path(str(seeded.planner.worktree)).exists()


def _forbid_local_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("remote commission verification must not run local Git")

    monkeypatch.setattr(
        executive_supervisor_mod, "_commission_git_probe", forbidden
    )


def _install_reader(
    monkeypatch: pytest.MonkeyPatch,
    *,
    content: bytes | None = None,
    error: Exception | None = None,
    mutate=None,
) -> list[dict[str, str]]:
    """Install the mock canonical byte reader and return its call record."""

    calls: list[dict[str, str]] = []

    def reader(*, repository: str, commit: str, path: str) -> bytes:
        calls.append(
            {"repository": repository, "commit": commit, "path": path}
        )
        if mutate is not None:
            mutate()
        if error is not None:
            raise error
        if content is not None:
            return content
        raise AssertionError("mock canonical byte reader had no scripted outcome")

    monkeypatch.setattr(
        executive_supervisor_mod, "_fetch_remote_commission", reader
    )
    return calls


_IDENTITY_CASES = {
    "subclass": "not exact WorkspaceIdentity",
    "namespace": "not exact WorkspaceIdentity",
    "wrong_path": "differs from the durable Job assignment",
    "wrong_base": "differs from the durable Job assignment",
    "inode_zero": "physical identity is not qualified",
    "bool_device": "physical identity is not qualified",
    "string_uid": "physical identity is not qualified",
    "negative_gid": "physical identity is not qualified",
}


def _mutated_identity(identity: WorkspaceIdentity, case: str):
    if case == "subclass":
        return _IdentitySubclass(
            workspace_path=identity.workspace_path,
            base_sha=identity.base_sha,
            device=identity.device,
            inode=identity.inode,
            uid=identity.uid,
            gid=identity.gid,
        )
    if case == "namespace":
        return SimpleNamespace(
            workspace_path=identity.workspace_path,
            base_sha=identity.base_sha,
            device=identity.device,
            inode=identity.inode,
            uid=identity.uid,
            gid=identity.gid,
        )
    if case == "wrong_path":
        return dataclasses.replace(
            identity, workspace_path=identity.workspace_path + "-other"
        )
    if case == "wrong_base":
        return dataclasses.replace(identity, base_sha="a" * 40)
    if case == "inode_zero":
        return dataclasses.replace(identity, inode=0)
    if case == "bool_device":
        return dataclasses.replace(identity, device=True)
    if case == "string_uid":
        return dataclasses.replace(identity, uid=str(identity.uid))
    if case == "negative_gid":
        return dataclasses.replace(identity, gid=-1)
    raise AssertionError(f"unknown identity case {case}")


def _corrupt_private_row(seeded: SimpleNamespace, sql: str, params: tuple) -> None:
    connection = sqlite3.connect(seeded.runtime.store.path)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def _strip_durable_base_sha(seeded: SimpleNamespace) -> None:
    connection = sqlite3.connect(seeded.runtime.store.path)
    try:
        row = connection.execute(
            "SELECT constraints_json FROM jobs WHERE job_id=?",
            (seeded.planner.job_id,),
        ).fetchone()
        assert row is not None
        constraints = json.loads(str(row[0]))
        constraints.pop("base_sha", None)
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (
                json.dumps(constraints, sort_keys=True, separators=(",", ":")),
                seeded.planner.job_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _rewrite_root_dialogue_source_commit(
    seeded: SimpleNamespace, commit: str
) -> None:
    """Corrupt the immutable root event consistently, digest included."""

    with seeded.runtime.store.read() as connection:
        row = connection.execute(
            """SELECT event_id,payload_json FROM events
               WHERE event_type='JOB_CREATED' AND job_id=?""",
            (seeded.root.job_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    stored = payload["provenance"]["dialogue_source"]
    stored["commission_ref"]["commit"] = commit
    payload["provenance"]["dialogue_source_digest"] = hashlib.sha256(
        json.dumps(
            stored,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    connection = sqlite3.connect(seeded.runtime.store.path)
    try:
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_id=?",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                int(row["event_id"]),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_remote_operator_planner_commission_verifies_exact_bytes_without_local_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, ref_commit="f" * 40)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    verified = verify_commission_for_job(
        seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
    )

    assert isinstance(verified, VerifiedCommission)
    assert verified.ref_dict() == {
        "repository": _CANONICAL_REPOSITORY,
        "commit": "f" * 40,
        "path": _COMMISSION_PATH,
        "content_sha256": hashlib.sha256(_COMMISSION).hexdigest(),
    }
    assert verified.content == _COMMISSION
    assert calls == [
        {
            "repository": _CANONICAL_REPOSITORY,
            "commit": "f" * 40,
            "path": _COMMISSION_PATH,
        }
    ]
    attempt = seeded.runtime.attempts.get_attempt(
        seeded.dispatch.attempt.attempt_id
    )
    assert attempt is not None and attempt.status is AttemptStatus.CLAIMED


@pytest.mark.parametrize("case", sorted(_IDENTITY_CASES))
def test_remote_commission_refuses_malformed_workspace_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dispatch=False)
    broken = _mutated_identity(_qualified_identity(seeded), case)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(SupervisorError, match=_IDENTITY_CASES[case]):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=broken
        )

    assert calls == []


def test_remote_commission_refuses_descriptor_only_job_without_current_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dispatch=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(
        SupervisorError, match="remote commission Job has no current Attempt"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_refuses_durable_current_attempt_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    _corrupt_private_row(
        seeded,
        "UPDATE jobs SET status='QUEUED', current_attempt_id=NULL,"
        " assigned_worker_id=NULL, assigned_quota_class=NULL WHERE job_id=?",
        (seeded.planner.job_id,),
    )

    with pytest.raises(
        SupervisorError, match="remote commission Job has no current Attempt"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [("worktree", None), ("worktree", "relative/nope"), ("base", "nothex"), ("base", "a" * 39)],
)
def test_remote_commission_refuses_snapshot_without_exact_worktree_or_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dispatch=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    if field == "worktree":
        snapshot = dataclasses.replace(seeded.planner, worktree=value)
        message = "remote commission Job has no exact assigned workspace"
    else:
        snapshot = dataclasses.replace(
            seeded.planner,
            constraints={**seeded.planner.constraints, "base_sha": value},
        )
        message = "remote commission Job has no exact base identity"

    with pytest.raises(SupervisorError, match=message):
        verify_commission_for_job(
            seeded.runtime, snapshot, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_refuses_durable_worktree_and_base_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durable drift against the caller's snapshot refuses before any fetch."""

    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    _corrupt_private_row(
        seeded,
        "UPDATE jobs SET worktree=NULL WHERE job_id=?",
        (seeded.planner.job_id,),
    )

    with pytest.raises(
        SupervisorError,
        match="remote commission durable assignment differs from the commission Job",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []
    _install_reader(monkeypatch, content=seeded.content)
    _corrupt_private_row(
        seeded,
        "UPDATE jobs SET worktree=? WHERE job_id=?",
        (str(seeded.planner.worktree), seeded.planner.job_id),
    )
    _strip_durable_base_sha(seeded)

    with pytest.raises(
        SupervisorError,
        match="remote commission durable assignment differs from the commission Job",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_refuses_durable_worker_rebind_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    _corrupt_private_row(
        seeded,
        "UPDATE attempts SET worker_id='worker-b' WHERE attempt_id=?",
        (seeded.dispatch.attempt.attempt_id,),
    )

    with pytest.raises(
        SupervisorError,
        match="remote commission durable assignment differs from the commission Job",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_refuses_non_planner_role_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dispatch=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(
        SupervisorError, match="accepts only the non-direct planner role"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.root, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_direct_native_job_refuses_remote_workspace_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    direct_job = dataclasses.replace(
        seeded.planner,
        constraints={
            **seeded.planner.constraints,
            "direct_native_policy": "mastermind.direct_native_readonly/v1",
        },
    )

    assert executive_supervisor_mod._is_direct_native_job(direct_job) is True
    with pytest.raises(
        SupervisorError,
        match="direct native commission refuses a remote workspace identity",
    ):
        verify_commission_for_job(
            seeded.runtime, direct_job, None, owner_workspace_identity=identity
        )

    assert calls == []


@pytest.mark.parametrize("mode", ["existing", "foreign", "removed"])
def test_remote_commission_refuses_simultaneous_local_and_remote_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    if mode == "removed":
        workspace = Path(str(seeded.planner.worktree))
        shutil.rmtree(seeded.workspace)
    elif mode == "foreign":
        foreign = tmp_path / "foreign" / "planner"
        foreign.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(foreign)], check=True)
        workspace = foreign
    else:
        workspace = Path(str(seeded.planner.worktree))
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(
        SupervisorError,
        match="refuses simultaneous local and remote workspace identity",
    ):
        verify_commission_for_job(
            seeded.runtime,
            seeded.planner,
            workspace,
            owner_workspace_identity=identity,
        )

    assert calls == [], "a local refusal must never be replaced by the remote route"


def _corrupt_root_dialogue_source(seeded: SimpleNamespace, corruption: str) -> None:
    """Private corruption fixture; no malformed source becomes legacy absence."""

    with seeded.runtime.store.read() as connection:
        row = connection.execute(
            """SELECT event_id,payload_json FROM events
               WHERE event_type='JOB_CREATED' AND job_id=?""",
            (seeded.root.job_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    assert isinstance(payload["provenance"].get("dialogue_source"), dict)
    if corruption == "orphan_digest":
        del payload["provenance"]["dialogue_source"]
    elif corruption == "source_without_digest":
        del payload["provenance"]["dialogue_source_digest"]
    elif corruption == "malformed_source":
        payload["provenance"]["dialogue_source"] = {"schema_version": "invalid"}
    else:
        raise AssertionError("unknown private corruption case")
    connection = sqlite3.connect(seeded.runtime.store.path)
    try:
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_id=?",
            (
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                int(row["event_id"]),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_source_free_remote_planner_passes_without_commission_after_qualification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy source-free provenance passes the remote route with no commission.

    Neither the optional dialogue source nor its digest exists in the
    immutable root creation Event, so no commission was ever admitted: the
    route returns ``None`` after qualifying the exact remote identity and
    durable assignment.  It performs no canonical fetch and no local Git read
    or stat of the removed workspace, and the original local route keeps its
    legacy ``None``.
    """
    seeded = _seed_remote_operator_planner(tmp_path, dialogue=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    assert verify_commission_for_job(seeded.runtime, seeded.planner, None) is None
    assert (
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )
        is None
    )

    assert calls == []


@pytest.mark.parametrize("case", ["wrong_path", "wrong_base", "inode_zero", "negative_gid"])
def test_source_free_remote_planner_refuses_unqualified_remote_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dialogue=False)
    broken = _mutated_identity(_qualified_identity(seeded), case)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(SupervisorError, match=_IDENTITY_CASES[case]):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=broken
        )

    assert calls == []


def test_source_free_remote_planner_refuses_without_current_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dispatch=False, dialogue=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(
        SupervisorError, match="remote commission Job has no current Attempt"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_source_free_remote_planner_refuses_durable_worker_rebind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, dialogue=False)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    _corrupt_private_row(
        seeded,
        "UPDATE attempts SET worker_id='worker-b' WHERE attempt_id=?",
        (seeded.dispatch.attempt.attempt_id,),
    )

    with pytest.raises(
        SupervisorError,
        match="remote commission durable assignment differs from the commission Job",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


@pytest.mark.parametrize("corruption", ["orphan_digest", "source_without_digest", "malformed_source"])
def test_corrupt_source_never_recategorizes_source_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corruption: str
) -> None:
    """Orphaned, partial and malformed commissioned provenance all refuse."""

    seeded = _seed_remote_operator_planner(tmp_path)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)
    _corrupt_root_dialogue_source(seeded, corruption)

    with pytest.raises(
        SupervisorError, match="immutable commission source is invalid"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_refuses_non_canonical_repository_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(
        tmp_path, repository="mastermindx-market-intelligence/Other"
    )
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=seeded.content)

    with pytest.raises(
        SupervisorError, match="outside the canonical Executive repository"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert calls == []


def test_remote_commission_unavailable_bytes_stay_refusal_without_local_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, ref_commit="f" * 40)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(
        monkeypatch,
        error=SupervisorError("immutable commission remote evidence is unavailable"),
    )

    with pytest.raises(
        SupervisorError, match="immutable commission remote evidence is unavailable"
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert len(calls) == 1


_BYTE_CASES = {
    "changed": (
        _COMMISSION,
        b"# Replacement different commission bytes\n",
        "commission content digest differs from immutable source",
    ),
    "empty": (_COMMISSION, b"", "empty or exceeds the 512 KiB ceiling"),
    "oversized": (
        _COMMISSION,
        b"x" * ((1 << 19) + 1),
        "empty or exceeds the 512 KiB ceiling",
    ),
    "bad_utf8": (
        b"\xff\xfe\x81invalid",
        b"\xff\xfe\x81invalid",
        "commission content must be UTF-8 text",
    ),
    "nul": (
        b"invalid\x00commission",
        b"invalid\x00commission",
        "commission content contains a NUL byte",
    ),
}


@pytest.mark.parametrize("case", sorted(_BYTE_CASES))
def test_remote_commission_invalid_bytes_stay_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    seeded_content, served, message = _BYTE_CASES[case]
    seeded = _seed_remote_operator_planner(tmp_path, content=seeded_content)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(monkeypatch, content=served)

    with pytest.raises(SupervisorError, match=message):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert len(calls) == 1


def test_remote_commission_assignment_rebind_during_fetch_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, ref_commit="f" * 40)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)

    def rebind() -> None:
        # A real durable rebinding of the claimed assignment while the fetch
        # is in flight; corruption fixtures may mutate private records.
        _corrupt_private_row(
            seeded,
            "UPDATE attempts SET lease_owner='remote-rebind',"
            " fence_generation=fence_generation+1 WHERE attempt_id=?",
            (seeded.dispatch.attempt.attempt_id,),
        )

    calls = _install_reader(monkeypatch, content=seeded.content, mutate=rebind)

    with pytest.raises(
        SupervisorError,
        match="remote commission durable assignment moved during verification",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert len(calls) == 1


def test_remote_commission_source_drift_during_fetch_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path, ref_commit="f" * 40)
    identity = _qualified_identity(seeded)
    _detach_remote_workspace(seeded)
    _forbid_local_git(monkeypatch)
    calls = _install_reader(
        monkeypatch,
        content=seeded.content,
        mutate=lambda: _rewrite_root_dialogue_source_commit(seeded, "e" * 40),
    )

    with pytest.raises(
        SupervisorError,
        match="immutable commission source drifted during remote verification",
    ):
        verify_commission_for_job(
            seeded.runtime, seeded.planner, None, owner_workspace_identity=identity
        )

    assert len(calls) == 1


def test_local_route_still_verifies_from_local_git_without_remote_parameter(
    tmp_path: Path,
) -> None:
    seeded = _seed_remote_operator_planner(tmp_path)

    verified = verify_commission_for_job(
        seeded.runtime,
        seeded.planner,
        Path(str(seeded.planner.worktree)).resolve(strict=True),
    )

    assert verified is not None
    assert verified.content == seeded.content
    assert verified.commit == seeded.base_sha
    assert verified.content_sha256 == hashlib.sha256(seeded.content).hexdigest()


def test_production_remote_reader_refuses_non_canonical_repository_without_network() -> None:
    with pytest.raises(
        SupervisorError, match="outside the canonical Executive repository"
    ):
        executive_supervisor_mod._fetch_remote_commission(
            repository="other/origin",
            commit="a" * 40,
            path=_COMMISSION_PATH,
        )


def test_production_remote_reader_rejects_off_origin_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"# exact remote commission\n"
    commit = "a" * 40
    canonical_url = (
        "https://raw.githubusercontent.com/"
        f"{_CANONICAL_REPOSITORY}/{commit}/"
        f"{urllib.parse.quote(_COMMISSION_PATH, safe='/')}"
    )

    class Response:
        headers = {"Content-Length": str(len(content))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://raw.githubusercontent.com/other/origin/served.md"

        def read(self, limit):
            raise AssertionError("off-origin response must never be read")

    class Opener:
        def open(self, request, *, timeout):
            assert request.full_url == canonical_url
            return Response()

    monkeypatch.setattr(
        executive_supervisor_mod.urllib.request,
        "build_opener",
        lambda *handlers: Opener(),
    )

    with pytest.raises(
        SupervisorError, match="escaped the canonical GitHub raw destination"
    ):
        executive_supervisor_mod._fetch_remote_commission(
            repository=_CANONICAL_REPOSITORY,
            commit=commit,
            path=_COMMISSION_PATH,
        )


def test_production_remote_reader_refuses_redirect_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit = "a" * 40
    canonical_url = (
        "https://raw.githubusercontent.com/"
        f"{_CANONICAL_REPOSITORY}/{commit}/"
        f"{urllib.parse.quote(_COMMISSION_PATH, safe='/')}"
    )

    class Opener:
        def open(self, request, *, timeout):
            raise urllib.error.HTTPError(canonical_url, 302, "Found", {}, None)

    monkeypatch.setattr(
        executive_supervisor_mod.urllib.request,
        "build_opener",
        lambda *handlers: Opener(),
    )

    with pytest.raises(SupervisorError, match="redirect is forbidden"):
        executive_supervisor_mod._fetch_remote_commission(
            repository=_CANONICAL_REPOSITORY,
            commit=commit,
            path=_COMMISSION_PATH,
        )
