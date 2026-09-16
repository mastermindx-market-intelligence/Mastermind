from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_deployment_apply as applier


def _binding() -> dict:
    return sb.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "multilogin",
            "folder_id": "11111111-1111-4111-8111-111111111111",
            "profile_id": "22222222-2222-4222-8222-222222222222",
            "url": "https://chatgpt.com/c/apply-test",
        },
        observed_at="2026-09-16T00:00:00Z",
        seat_ref="chatgpt1",
        binding_id="33333333-3333-4333-8333-333333333333",
    )


def _bundle(tmp_path: Path) -> tuple[deployment.DeploymentBundle, Path]:
    install_root = tmp_path / "install"
    install_root.mkdir(mode=0o700)
    release = deployment.WebSolRelease(
        package_version="0.2.0",
        source_commit="a" * 40,
        repository_root=tmp_path / "repo",
        python_executable=Path(sys.executable),
        install_root=install_root,
    )
    return deployment.render_bundle(_binding(), release), install_root


def test_prepare_deployment_captures_absent_preimages_without_public_paths(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    plan = deployment.plan_deployment(bundle, {})

    prepared = applier.prepare_deployment(
        bundle,
        plan,
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )

    receipt = prepared.public_receipt
    assert receipt == {
        "schema": applier.PREPARED_RECEIPT_SCHEMA,
        "status": "PREPARED",
        "operation_key": "web-sol-install1-transactional-applier-source-20260916-sol-001",
        "bundle_digest": bundle.bundle_digest,
        "prepared_digest": prepared.prepared_digest,
        "target_count": 3,
        "create_count": 3,
        "update_count": 0,
        "unchanged_count": 0,
        "production_acceptance_granted": False,
    }
    serialized = json.dumps(receipt, sort_keys=True)
    assert str(install_root) not in serialized
    assert all(row.prior_state == "ABSENT" for row in prepared.preimages)


def test_apply_and_rollback_new_bundle_restores_exact_empty_preimage(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    plan = deployment.plan_deployment(bundle, {})
    prepared = applier.prepare_deployment(
        bundle,
        plan,
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )

    applied = applier.apply_deployment(prepared)

    assert applied.public_receipt == {
        "schema": applier.APPLY_RECEIPT_SCHEMA,
        "status": "APPLIED_VERIFIED",
        "operation_key": prepared.operation_key,
        "bundle_digest": bundle.bundle_digest,
        "prepared_digest": prepared.prepared_digest,
        "target_count": 3,
        "changed_count": 3,
        "unchanged_count": 0,
        "reconciled_count": 0,
        "production_acceptance_granted": False,
    }
    for artifact in bundle.artifacts:
        assert artifact.destination.read_bytes() == artifact.content
        assert artifact.destination.stat().st_mode & 0o777 == artifact.mode

    verify = applier.verify_applied_deployment(applied)
    assert verify["status"] == "READBACK_VERIFIED"
    assert verify["target_count"] == 3

    rollback = applier.rollback_deployment(applied)
    assert rollback == {
        "schema": applier.ROLLBACK_RECEIPT_SCHEMA,
        "status": "ROLLBACK_VERIFIED",
        "operation_key": prepared.operation_key,
        "bundle_digest": bundle.bundle_digest,
        "prepared_digest": prepared.prepared_digest,
        "restored_count": 0,
        "removed_count": 3,
        "production_acceptance_granted": False,
    }
    assert list(install_root.rglob("*")) == []


def test_partial_apply_failure_rolls_back_and_consumes_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    plan = deployment.plan_deployment(bundle, {})
    prepared = applier.prepare_deployment(
        bundle,
        plan,
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    original_replace = applier.os.replace
    calls = 0

    def fail_before_second_replace(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected-before-second-replace")
        original_replace(source, target)

    monkeypatch.setattr(applier.os, "replace", fail_before_second_replace)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="APPLY_ABORTED_ROLLED_BACK",
    ):
        applier.apply_deployment(prepared)

    assert calls == 2
    assert list(install_root.rglob("*")) == []
    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="TRANSACTION_CONSUMED",
    ):
        applier.apply_deployment(prepared)


def test_post_replace_fsync_failure_reconciles_without_replacing_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    first = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    original_fsync_directory = applier._fsync_directory
    original_replace = applier.os.replace
    fsync_calls: list[Path] = []
    replace_targets: list[Path] = []
    injected = False

    def record_replace(source: object, target: object) -> None:
        replace_targets.append(Path(target))
        original_replace(source, target)

    def fail_first_post_replace_fsync(path: Path) -> None:
        nonlocal injected
        fsync_calls.append(path)
        if path == first.destination.parent and first.destination.exists() and not injected:
            injected = True
            raise OSError("injected-directory-fsync-failure")
        original_fsync_directory(path)

    monkeypatch.setattr(applier.os, "replace", record_replace)
    monkeypatch.setattr(applier, "_fsync_directory", fail_first_post_replace_fsync)

    applied = applier.apply_deployment(prepared)

    assert injected is True
    assert replace_targets.count(first.destination) == 1
    assert fsync_calls.count(first.destination.parent) == 2
    assert applied.public_receipt["reconciled_count"] == 1
    applier.rollback_deployment(applied)


def test_mixed_plan_preserves_unchanged_inode_and_restores_prior_mode(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifacts = sorted(bundle.artifacts, key=lambda row: str(row.destination))
    unchanged, updated, created = artifacts
    for artifact in (unchanged, updated):
        artifact.destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    unchanged.destination.write_bytes(unchanged.content)
    unchanged.destination.chmod(unchanged.mode)
    updated.destination.write_bytes(b"exact-prior-update-bytes")
    updated.destination.chmod(0o640)
    unchanged_inode = unchanged.destination.stat().st_ino
    current = {
        str(unchanged.destination): unchanged.content,
        str(updated.destination): b"exact-prior-update-bytes",
    }
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, current),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )

    applied = applier.apply_deployment(prepared)

    assert applied.public_receipt["changed_count"] == 2
    assert applied.public_receipt["unchanged_count"] == 1
    assert unchanged.destination.stat().st_ino == unchanged_inode
    assert updated.destination.read_bytes() == updated.content
    assert updated.destination.stat().st_mode & 0o777 == updated.mode
    assert created.destination.read_bytes() == created.content

    receipt = applier.rollback_deployment(applied)

    assert receipt["restored_count"] == 1
    assert receipt["removed_count"] == 1
    assert unchanged.destination.stat().st_ino == unchanged_inode
    assert unchanged.destination.read_bytes() == unchanged.content
    assert updated.destination.read_bytes() == b"exact-prior-update-bytes"
    assert updated.destination.stat().st_mode & 0o777 == 0o640
    assert not created.destination.exists()


def test_directory_created_after_prepare_is_preimage_conflict(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    first_parent = sorted(
        {artifact.destination.parent for artifact in bundle.artifacts},
        key=str,
    )[0]
    first_parent.mkdir(parents=True, mode=0o700)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREIMAGE_CONFLICT",
    ):
        applier.apply_deployment(prepared)

    assert not any(artifact.destination.exists() for artifact in bundle.artifacts)
