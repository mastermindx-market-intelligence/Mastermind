from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_deployment as deployment
from integrations.chairman_surfaces import web_sol_protocol as wsp
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
        package_version=wsp.WEB_SOL_PACKAGE_VERSION,
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
    original_atomic = applier._atomic_rename_at
    install_target_names = {artifact.destination.name for artifact in bundle.artifacts}
    apply_calls = 0

    def fail_before_second_install(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *,
        exchange: bool,
    ) -> None:
        nonlocal apply_calls
        if (
            target_name in install_target_names
            and source_name.endswith(".tmp")
            and not source_name.endswith(".rollback.tmp")
        ):
            apply_calls += 1
            if apply_calls == 2:
                raise OSError("injected-before-second-install")
        original_atomic(
            parent_descriptor,
            source_name,
            target_name,
            exchange=exchange,
        )

    monkeypatch.setattr(applier, "_atomic_rename_at", fail_before_second_install)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="APPLY_ABORTED_ROLLED_BACK",
    ):
        applier.apply_deployment(prepared)

    assert apply_calls == 2
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
    original_fsync = applier.os.fsync
    original_atomic = applier._atomic_rename_at
    fsync_calls: list[Path] = []
    replace_targets: list[str] = []
    injected = False

    def record_install(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *,
        exchange: bool,
    ) -> None:
        replace_targets.append(target_name)
        original_atomic(
            parent_descriptor,
            source_name,
            target_name,
            exchange=exchange,
        )

    def fail_first_post_replace_fsync(descriptor: int) -> None:
        nonlocal injected
        info = applier.os.fstat(descriptor)
        parent = first.destination.parent
        if parent.exists():
            parent_info = parent.stat()
            if (info.st_dev, info.st_ino) == (parent_info.st_dev, parent_info.st_ino):
                fsync_calls.append(parent)
                if first.destination.exists() and not injected:
                    injected = True
                    raise OSError("injected-directory-fsync-failure")
        original_fsync(descriptor)

    monkeypatch.setattr(applier, "_atomic_rename_at", record_install)
    monkeypatch.setattr(applier.os, "fsync", fail_first_post_replace_fsync)

    applied = applier.apply_deployment(prepared)

    assert injected is True
    assert replace_targets.count(first.destination.name) == 1
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


def test_partial_temporary_write_is_cleaned_and_aborted_safely(
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
    original_write = applier.os.write
    calls = 0

    def partial_then_fail(descriptor: int, payload: object) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_write(descriptor, payload[: max(1, len(payload) // 2)])
        raise OSError("injected-partial-write")

    monkeypatch.setattr(applier.os, "write", partial_then_fail)

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


def test_prepared_plan_mutation_is_refused_before_filesystem_effect(
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
    prepared.plan = dataclasses.replace(
        prepared.plan,
        bundle_digest="b" * 64,
    )

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREPARED_INTEGRITY_MISMATCH",
    ):
        applier.apply_deployment(prepared)

    assert list(install_root.rglob("*")) == []


def test_target_symlink_is_refused_during_prepare(tmp_path: Path) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    target.destination.symlink_to(outside)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="TARGET_SYMLINK_REFUSED",
    ):
        applier.prepare_deployment(
            bundle,
            deployment.plan_deployment(bundle, {}),
            install_root=install_root,
            expected_uid=install_root.stat().st_uid,
            expected_gid=install_root.stat().st_gid,
            operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
        )

    assert outside.read_bytes() == b"outside"


def test_file_changed_after_prepare_is_refused_before_replace(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    target.destination.write_bytes(b"approved-preimage")
    target.destination.chmod(0o600)
    current = {str(target.destination): b"approved-preimage"}
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, current),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    target.destination.write_bytes(b"external-change")

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREIMAGE_CONFLICT",
    ):
        applier.apply_deployment(prepared)

    assert target.destination.read_bytes() == b"external-change"



def test_target_changed_after_temporary_write_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[1]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    prior = b"approved-preimage-before-temporary"
    target.destination.write_bytes(prior)
    target.destination.chmod(target.mode)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {str(target.destination): prior}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    original_write = applier._write_exact_temporary_at
    foreign = b"concurrent-owner-change-after-temporary"
    injected = False

    def write_then_change_target(*args, **kwargs) -> None:
        nonlocal injected
        original_write(*args, **kwargs)
        parent_descriptor, temporary_name = args[:2]
        if injected or temporary_name != applier._temporary_path(target, prepared).name:
            return
        injected = True
        flags = applier.os.O_WRONLY | applier.os.O_TRUNC
        if hasattr(applier.os, "O_NOFOLLOW"):
            flags |= applier.os.O_NOFOLLOW
        descriptor = applier.os.open(
            target.destination.name,
            flags,
            dir_fd=parent_descriptor,
        )
        try:
            applier.os.write(descriptor, foreign)
            applier.os.fsync(descriptor)
        finally:
            applier.os.close(descriptor)

    monkeypatch.setattr(
        applier,
        "_write_exact_temporary_at",
        write_then_change_target,
    )

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREIMAGE_CONFLICT",
    ):
        applier.apply_deployment(prepared)

    assert injected is True
    assert target.destination.read_bytes() == foreign
    assert prepared._state == "CONFLICT"
    assert all(
        not artifact.destination.exists()
        for artifact in bundle.artifacts
        if artifact.destination != target.destination
    )


def test_target_changed_after_final_preimage_check_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[1]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    prior = b"approved-preimage-before-final-check"
    target.destination.write_bytes(prior)
    target.destination.chmod(target.mode)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {str(target.destination): prior}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    original_matches = applier._named_preimage_matches
    temporary_name = applier._temporary_path(target, prepared).name
    foreign = b"concurrent-owner-change-after-final-check"
    injected = False

    def match_then_change_target(
        parent_descriptor: int,
        name: str,
        row: applier.ArtifactPreimage,
        current: applier.PreparedDeployment,
    ) -> bool:
        nonlocal injected
        matched = original_matches(parent_descriptor, name, row, current)
        if injected or not matched or name != target.destination.name:
            return matched
        try:
            applier.os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            return matched
        injected = True
        flags = applier.os.O_WRONLY | applier.os.O_TRUNC
        if hasattr(applier.os, "O_NOFOLLOW"):
            flags |= applier.os.O_NOFOLLOW
        descriptor = applier.os.open(name, flags, dir_fd=parent_descriptor)
        try:
            view = memoryview(foreign)
            offset = 0
            while offset < len(view):
                written = applier.os.write(descriptor, view[offset:])
                assert written > 0
                offset += written
            applier.os.fsync(descriptor)
        finally:
            applier.os.close(descriptor)
        return matched

    monkeypatch.setattr(
        applier,
        "_named_preimage_matches",
        match_then_change_target,
    )

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREIMAGE_CONFLICT",
    ):
        applier.apply_deployment(prepared)

    assert injected is True
    assert target.destination.read_bytes() == foreign
    assert prepared._state == "CONFLICT"
    assert all(
        not artifact.destination.exists()
        for artifact in bundle.artifacts
        if artifact.destination != target.destination
    )


def test_temporary_replaced_at_cleanup_boundary_is_not_unlinked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifact = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    artifact.destination.parent.mkdir(parents=True, mode=0o700)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    temporary_name = applier._temporary_path(artifact, prepared).name
    parent_descriptor = applier._open_verified_directory(
        artifact.destination.parent,
        prepared,
    )
    foreign = b"concurrent-foreign-temporary-substitution"
    original_atomic = applier._atomic_rename_at
    injected = False

    try:
        applier._write_exact_temporary_at(
            parent_descriptor,
            temporary_name,
            artifact.content,
            artifact.mode,
            prepared,
        )

        def replace_then_rename(
            descriptor: int,
            source_name: str,
            target_name: str,
            *,
            exchange: bool,
        ) -> None:
            nonlocal injected
            if not injected and source_name == temporary_name and not exchange:
                injected = True
                applier.os.unlink(source_name, dir_fd=descriptor)
                flags = applier.os.O_WRONLY | applier.os.O_CREAT | applier.os.O_EXCL
                if hasattr(applier.os, "O_NOFOLLOW"):
                    flags |= applier.os.O_NOFOLLOW
                foreign_descriptor = applier.os.open(
                    source_name,
                    flags,
                    artifact.mode,
                    dir_fd=descriptor,
                )
                try:
                    applier.os.write(foreign_descriptor, foreign)
                    applier.os.fsync(foreign_descriptor)
                finally:
                    applier.os.close(foreign_descriptor)
            original_atomic(
                descriptor,
                source_name,
                target_name,
                exchange=exchange,
            )

        monkeypatch.setattr(applier, "_atomic_rename_at", replace_then_rename)

        with pytest.raises(
            applier.WebSolDeploymentApplyError,
            match="APPLY_EFFECT_UNKNOWN",
        ):
            applier._cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                artifact.content,
                artifact.mode,
                prepared,
            )

        assert injected is True
        assert (artifact.destination.parent / temporary_name).read_bytes() == foreign
    finally:
        applier.os.close(parent_descriptor)


def test_quarantine_replaced_after_validation_is_not_unlinked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifact = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    artifact.destination.parent.mkdir(parents=True, mode=0o700)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    temporary_name = applier._temporary_path(artifact, prepared).name
    quarantine_name = applier._cleanup_quarantine_name(temporary_name, prepared)
    parent_descriptor = applier._open_verified_directory(
        artifact.destination.parent,
        prepared,
    )
    foreign_name = "foreign-cleanup-owner-file"
    foreign = b"foreign-bytes-substituted-after-validation"
    original_matches = applier._named_file_matches
    injected = False

    try:
        applier._write_exact_temporary_at(
            parent_descriptor,
            temporary_name,
            artifact.content,
            artifact.mode,
            prepared,
        )
        foreign_descriptor = applier.os.open(
            foreign_name,
            applier.os.O_WRONLY | applier.os.O_CREAT | applier.os.O_EXCL,
            artifact.mode,
            dir_fd=parent_descriptor,
        )
        try:
            applier.os.write(foreign_descriptor, foreign)
            applier.os.fsync(foreign_descriptor)
        finally:
            applier.os.close(foreign_descriptor)

        def validate_then_replace(
            descriptor: int,
            name: str,
            content: bytes,
            mode: int,
            current: applier.PreparedDeployment,
        ) -> bool:
            nonlocal injected
            matched = original_matches(descriptor, name, content, mode, current)
            if matched and name == quarantine_name and not injected:
                injected = True
                applier.os.rename(
                    foreign_name,
                    quarantine_name,
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                )
            return matched

        monkeypatch.setattr(applier, "_named_file_matches", validate_then_replace)

        with pytest.raises(
            applier.WebSolDeploymentApplyError,
            match="APPLY_EFFECT_UNKNOWN",
        ):
            applier._cleanup_exact_temporary_at(
                parent_descriptor,
                temporary_name,
                artifact.content,
                artifact.mode,
                prepared,
            )

        assert injected is True
        assert (artifact.destination.parent / temporary_name).read_bytes() == foreign
    finally:
        applier.os.close(parent_descriptor)


def test_cleanup_quarantine_blocks_false_clean_reconciliation(
    tmp_path: Path,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifact = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    artifact.destination.parent.mkdir(parents=True, mode=0o700)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    temporary_name = applier._temporary_path(artifact, prepared).name
    quarantine_name = applier._cleanup_quarantine_name(
        temporary_name,
        prepared,
    )
    quarantine = artifact.destination.parent / quarantine_name
    quarantine.write_bytes(artifact.content)
    quarantine.chmod(artifact.mode)

    assert applier._transaction_temporaries_absent(prepared) is False


def test_apply_and_rollback_are_single_consumption_boundaries(
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
    applied = applier.apply_deployment(prepared)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="TRANSACTION_CONSUMED",
    ):
        applier.apply_deployment(prepared)

    applier.rollback_deployment(applied)
    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="TRANSACTION_CONSUMED",
    ):
        applier.rollback_deployment(applied)


def test_effect_unknown_rollback_reconciliation_rearms_exact_postimage(
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
    applied = applier.apply_deployment(prepared)
    applied._state = "EFFECT_UNKNOWN"
    prepared._state = "EFFECT_UNKNOWN"

    assert applier.reconcile_applied_rollback(applied) is None
    assert applied._state == "APPLIED"
    assert prepared._state == "APPLIED"
    assert applier.rollback_deployment(applied)["status"] == "ROLLBACK_VERIFIED"


def test_irreconcilable_post_replace_state_is_effect_unknown(
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
    original_atomic = applier._atomic_rename_at
    injected = False

    def install_then_corrupt(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *,
        exchange: bool,
    ) -> None:
        nonlocal injected
        original_atomic(
            parent_descriptor,
            source_name,
            target_name,
            exchange=exchange,
        )
        if not injected:
            injected = True
            descriptor = applier.os.open(
                target_name,
                applier.os.O_WRONLY | applier.os.O_TRUNC,
                dir_fd=parent_descriptor,
            )
            try:
                applier.os.write(descriptor, b"irreconcilable-postimage")
                applier.os.fsync(descriptor)
            finally:
                applier.os.close(descriptor)
            raise OSError("lost-response-with-foreign-postimage")

    monkeypatch.setattr(applier, "_atomic_rename_at", install_then_corrupt)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="APPLY_EFFECT_UNKNOWN",
    ):
        applier.apply_deployment(prepared)

    assert first.destination.read_bytes() == b"irreconcilable-postimage"
    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="TRANSACTION_CONSUMED",
    ):
        applier.apply_deployment(prepared)


def test_complete_census1_bundle_applies_reads_back_and_rolls_back(
    tmp_path: Path,
) -> None:
    bundle_seed, _unused_root = _bundle(tmp_path)
    binding_row = _binding()
    install_root = tmp_path / "census-install"
    install_root.mkdir(mode=0o700)
    release = deployment.WebSolRelease(
        package_version=wsp.WEB_SOL_PACKAGE_VERSION,
        source_commit="c" * 40,
        repository_root=tmp_path / "repo",
        python_executable=Path(sys.executable),
        install_root=install_root,
    )
    source_root = (
        Path(__file__).resolve().parents[1]
        / "integrations"
        / "chairman_surfaces"
        / "web_sol_extension"
    )
    names = (
        "manifest.json",
        "background.js",
        "content.js",
        "continuation_core.js",
        "census.html",
        "census.css",
        "census_core.js",
        "census.js",
    )
    source_files = {name: (source_root / name).read_bytes() for name in names}
    expected = {
        name: applier.hashlib.sha256(payload).hexdigest()
        for name, payload in source_files.items()
    }
    bundle = deployment.render_census_extension_bundle(
        binding_row,
        release,
        source_files=source_files,
        expected_source_digests=expected,
    )
    assert len(bundle_seed.artifacts) == 3
    assert len(bundle.artifacts) == 11
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )

    applied = applier.apply_deployment(prepared)

    assert applied.public_receipt["target_count"] == 11
    assert applier.verify_applied_deployment(applied)["target_count"] == 11
    assert applier.rollback_deployment(applied)["removed_count"] == 11
    assert list(install_root.rglob("*")) == []


def test_parent_symlink_swap_at_replace_never_writes_outside_install_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    attack_temp = outside / applier._temporary_path(first, prepared).name
    displaced = tmp_path / "displaced-parent"
    original_atomic = applier._atomic_rename_at
    injected = False

    def swap_parent_then_install(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *,
        exchange: bool,
    ) -> None:
        nonlocal injected
        if not injected and target_name == first.destination.name:
            injected = True
            parent = first.destination.parent
            parent.rename(displaced)
            parent.symlink_to(outside, target_is_directory=True)
            assert source_name == attack_temp.name
            attack_temp.write_bytes(first.content)
            attack_temp.chmod(first.mode)
        original_atomic(
            parent_descriptor,
            source_name,
            target_name,
            exchange=exchange,
        )

    monkeypatch.setattr(applier, "_atomic_rename_at", swap_parent_then_install)

    with pytest.raises(applier.WebSolDeploymentApplyError):
        applier.apply_deployment(prepared)

    assert injected is True
    assert not (outside / first.destination.name).exists()
    assert attack_temp.read_bytes() == first.content



def test_rollback_present_exchange_cleanup_uses_rollback_effect_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifact = sorted(bundle.artifacts, key=lambda row: str(row.destination))[1]
    artifact.destination.parent.mkdir(parents=True, mode=0o700)
    prior = b"exact-prior-for-rollback-cleanup-code"
    artifact.destination.write_bytes(prior)
    artifact.destination.chmod(0o640)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {str(artifact.destination): prior}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    applier.apply_deployment(prepared)
    row = next(item for item in prepared.preimages if item.path == artifact.destination)
    assert row.prior_bytes is not None and row.prior_mode is not None
    rollback_name = (
        f".{artifact.destination.name}.mmx-"
        f"{prepared.prepared_digest[:16]}.rollback.tmp"
    )
    parent_descriptor = applier._open_verified_directory(
        artifact.destination.parent,
        prepared,
    )
    original_unlink = applier.os.unlink
    injected = False

    try:
        applier._write_exact_temporary_at(
            parent_descriptor,
            rollback_name,
            row.prior_bytes,
            row.prior_mode,
            prepared,
        )

        def fail_quarantine_unlink(name, *args, **kwargs):
            nonlocal injected
            if str(name).startswith(".mmx-clean-"):
                injected = True
                raise OSError("injected rollback cleanup failure")
            return original_unlink(name, *args, **kwargs)

        monkeypatch.setattr(applier.os, "unlink", fail_quarantine_unlink)

        with pytest.raises(
            applier.WebSolDeploymentApplyError,
            match="ROLLBACK_EFFECT_UNKNOWN",
        ):
            applier._rollback_present_target_at(
                parent_descriptor,
                rollback_name,
                artifact.destination.name,
                row,
                artifact,
                prepared,
            )

        assert injected is True
        assert artifact.destination.read_bytes() == prior
    finally:
        applier.os.close(parent_descriptor)

def test_present_target_changed_after_rollback_temporary_write_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[1]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    prior = b"exact-prior-before-rollback-race"
    target.destination.write_bytes(prior)
    target.destination.chmod(0o640)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {str(target.destination): prior}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    applied = applier.apply_deployment(prepared)
    original_write = applier._write_exact_temporary_at
    rollback_name = (
        f".{target.destination.name}.mmx-"
        f"{prepared.prepared_digest[:16]}.rollback.tmp"
    )
    foreign = b"concurrent-owner-change-during-rollback"
    injected = False

    def write_then_change_target(*args, **kwargs) -> None:
        nonlocal injected
        original_write(*args, **kwargs)
        parent_descriptor, temporary_name = args[:2]
        if injected or temporary_name != rollback_name:
            return
        injected = True
        flags = applier.os.O_WRONLY | applier.os.O_TRUNC
        if hasattr(applier.os, "O_NOFOLLOW"):
            flags |= applier.os.O_NOFOLLOW
        descriptor = applier.os.open(
            target.destination.name,
            flags,
            dir_fd=parent_descriptor,
        )
        try:
            view = memoryview(foreign)
            offset = 0
            while offset < len(view):
                written = applier.os.write(descriptor, view[offset:])
                assert written > 0
                offset += written
            applier.os.fsync(descriptor)
        finally:
            applier.os.close(descriptor)

    monkeypatch.setattr(
        applier,
        "_write_exact_temporary_at",
        write_then_change_target,
    )

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="ROLLBACK_EFFECT_UNKNOWN",
    ):
        applier.rollback_deployment(applied)

    assert injected is True
    assert target.destination.read_bytes() == foreign
    assert applied._state == "EFFECT_UNKNOWN"
    assert prepared._state == "EFFECT_UNKNOWN"


def test_absent_target_changed_after_rollback_check_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    applied = applier.apply_deployment(prepared)
    target = prepared.preimages[-1].path
    original_matches = applier._named_file_matches
    foreign = b"concurrent-owner-change-before-rollback-delete"
    target_match_calls = 0
    injected = False

    def match_then_change_target(
        parent_descriptor: int,
        name: str,
        content: bytes,
        mode: int,
        current: applier.PreparedDeployment,
    ) -> bool:
        nonlocal target_match_calls, injected
        matched = original_matches(
            parent_descriptor,
            name,
            content,
            mode,
            current,
        )
        if name != target.name or not matched:
            return matched
        target_match_calls += 1
        if target_match_calls != 2:
            return matched
        injected = True
        flags = applier.os.O_WRONLY | applier.os.O_TRUNC
        if hasattr(applier.os, "O_NOFOLLOW"):
            flags |= applier.os.O_NOFOLLOW
        descriptor = applier.os.open(name, flags, dir_fd=parent_descriptor)
        try:
            view = memoryview(foreign)
            offset = 0
            while offset < len(view):
                written = applier.os.write(descriptor, view[offset:])
                assert written > 0
                offset += written
            applier.os.fsync(descriptor)
        finally:
            applier.os.close(descriptor)
        return matched

    monkeypatch.setattr(
        applier,
        "_named_file_matches",
        match_then_change_target,
    )

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="ROLLBACK_EFFECT_UNKNOWN",
    ):
        applier.rollback_deployment(applied)

    assert injected is True
    assert target.read_bytes() == foreign
    assert applied._state == "EFFECT_UNKNOWN"
    assert prepared._state == "EFFECT_UNKNOWN"


def test_parent_symlink_swap_at_rollback_never_deletes_outside_install_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    applied = applier.apply_deployment(prepared)
    target = prepared.preimages[-1].path
    outside = tmp_path / "outside-rollback"
    outside.mkdir(mode=0o700)
    sentinel = outside / target.name
    sentinel.write_bytes(b"outside-rollback-sentinel")
    displaced = tmp_path / "displaced-rollback-parent"
    original_atomic = applier._atomic_rename_at
    injected = False

    def swap_parent_then_remove(
        parent_descriptor: int,
        source_name: str,
        target_name: str,
        *,
        exchange: bool,
    ) -> None:
        nonlocal injected
        if not injected and source_name == target.name:
            injected = True
            target.parent.rename(displaced)
            target.parent.symlink_to(outside, target_is_directory=True)
        original_atomic(
            parent_descriptor,
            source_name,
            target_name,
            exchange=exchange,
        )

    monkeypatch.setattr(applier, "_atomic_rename_at", swap_parent_then_remove)

    with pytest.raises(applier.WebSolDeploymentApplyError):
        applier.rollback_deployment(applied)

    assert injected is True
    assert sentinel.read_bytes() == b"outside-rollback-sentinel"


def test_install_root_symlink_swap_at_directory_create_never_creates_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    first_directory = min(
        (row.path for row in prepared.directory_preimages if row.prior_state == "ABSENT"),
        key=lambda item: (len(item.parts), str(item)),
    )
    outside = tmp_path / "outside-directory-create"
    outside.mkdir(mode=0o700)
    displaced = tmp_path / "displaced-install-root"
    original_mkdir = applier.os.mkdir
    injected = False

    def swap_root_then_mkdir(path_value, mode=0o777, *args, **kwargs):
        nonlocal injected
        if not injected and Path(path_value).name == first_directory.name:
            injected = True
            install_root.rename(displaced)
            install_root.symlink_to(outside, target_is_directory=True)
        return original_mkdir(path_value, mode, *args, **kwargs)

    monkeypatch.setattr(applier.os, "mkdir", swap_root_then_mkdir)

    with pytest.raises(applier.WebSolDeploymentApplyError):
        applier.apply_deployment(prepared)

    assert injected is True
    assert not (outside / first_directory.name).exists()


def test_parent_symlink_swap_at_directory_removal_never_removes_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    applied = applier.apply_deployment(prepared)
    target = sorted(
        applied.created_directories,
        key=lambda item: (len(item.parts), str(item)),
        reverse=True,
    )[0]
    outside = tmp_path / "outside-directory-removal"
    outside.mkdir(mode=0o700)
    outside_target = outside / target.name
    outside_target.mkdir(mode=0o700)
    displaced = tmp_path / "displaced-directory-parent"
    original_rmdir = applier.os.rmdir
    injected = False

    def swap_parent_then_rmdir(path_value, *args, **kwargs):
        nonlocal injected
        if not injected and Path(path_value).name == target.name:
            injected = True
            target.parent.rename(displaced)
            target.parent.symlink_to(outside, target_is_directory=True)
        return original_rmdir(path_value, *args, **kwargs)

    monkeypatch.setattr(applier.os, "rmdir", swap_parent_then_rmdir)

    with pytest.raises(applier.WebSolDeploymentApplyError):
        applier.rollback_deployment(applied)

    assert injected is True
    assert outside_target.is_dir()


def test_lost_response_after_first_directory_create_is_effect_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    original_mkdir = applier.os.mkdir
    calls = 0

    def create_then_lose_response(path_value, mode=0o777, *args, **kwargs):
        nonlocal calls
        calls += 1
        original_mkdir(path_value, mode, *args, **kwargs)
        if calls == 1:
            raise OSError("lost-directory-create-response")

    monkeypatch.setattr(applier.os, "mkdir", create_then_lose_response)

    first_directory = min(
        (row.path for row in prepared.directory_preimages if row.prior_state == "ABSENT"),
        key=lambda item: (len(item.parts), str(item)),
    )
    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="APPLY_EFFECT_UNKNOWN",
    ):
        applier.apply_deployment(prepared)

    assert calls == 1
    assert first_directory.is_dir()
    assert prepared._state == "EFFECT_UNKNOWN"



def test_prepare_parent_swap_never_reads_outside_install_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    target.destination.parent.chmod(0o700)
    prior = b"admitted-prior-bytes"
    target.destination.write_bytes(prior)
    target.destination.chmod(target.mode)
    current = {str(target.destination): prior}
    plan = deployment.plan_deployment(bundle, current)

    outside = tmp_path / "outside-prepare"
    outside.mkdir(mode=0o700)
    outside_secret = b"outside-secret-must-not-be-read"
    (outside / target.destination.name).write_bytes(outside_secret)
    displaced = tmp_path / "displaced-prepare-parent"
    original_lstat = Path.lstat
    original_read_bytes = Path.read_bytes
    injected = False
    outside_read = False

    def swap_parent_after_target_lstat(self: Path):
        nonlocal injected
        info = original_lstat(self)
        if self == target.destination and not injected:
            injected = True
            target.destination.parent.rename(displaced)
            target.destination.parent.symlink_to(outside, target_is_directory=True)
        return info

    def track_path_read(self: Path) -> bytes:
        nonlocal outside_read
        if self == target.destination and injected:
            outside_read = True
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "lstat", swap_parent_after_target_lstat)
    monkeypatch.setattr(Path, "read_bytes", track_path_read)

    prepared = None
    try:
        prepared = applier.prepare_deployment(
            bundle,
            plan,
            install_root=install_root,
            expected_uid=install_root.stat().st_uid,
            expected_gid=install_root.stat().st_gid,
            operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
        )
    except applier.WebSolDeploymentApplyError as exc:
        assert exc.code in {
            "PREIMAGE_CONFLICT",
            "DIRECTORY_PREIMAGE_CONFLICT",
            "TARGET_READ_FAILED",
        }

    assert outside_read is False
    if prepared is not None:
        captured = next(row for row in prepared.preimages if row.path == target.destination)
        assert captured.prior_bytes == prior
    assert (outside / target.destination.name).read_bytes() == outside_secret



def test_apply_preimage_parent_swap_never_reads_outside_install_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    target = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    target.destination.parent.mkdir(parents=True, mode=0o700)
    target.destination.parent.chmod(0o700)
    prior = b"admitted-prior-before-apply"
    target.destination.write_bytes(prior)
    target.destination.chmod(target.mode)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {str(target.destination): prior}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )

    outside = tmp_path / "outside-apply-preimage"
    outside.mkdir(mode=0o700)
    outside_secret = b"outside-apply-secret-must-not-be-read"
    (outside / target.destination.name).write_bytes(outside_secret)
    displaced = tmp_path / "displaced-apply-preimage-parent"
    original_lstat = Path.lstat
    original_read_bytes = Path.read_bytes
    injected = False
    outside_read = False

    def swap_parent_after_target_lstat(self: Path):
        nonlocal injected
        info = original_lstat(self)
        if self == target.destination and not injected:
            injected = True
            target.destination.parent.rename(displaced)
            target.destination.parent.symlink_to(outside, target_is_directory=True)
        return info

    def track_path_read(self: Path) -> bytes:
        nonlocal outside_read
        if self == target.destination and injected:
            outside_read = True
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "lstat", swap_parent_after_target_lstat)
    monkeypatch.setattr(Path, "read_bytes", track_path_read)

    applied = None
    try:
        applied = applier.apply_deployment(prepared)
    except applier.WebSolDeploymentApplyError as exc:
        assert exc.code in {
            "PREIMAGE_CONFLICT",
            "APPLY_ABORTED_ROLLED_BACK",
            "APPLY_EFFECT_UNKNOWN",
        }

    assert outside_read is False
    assert (outside / target.destination.name).read_bytes() == outside_secret
    if applied is not None:
        applier.rollback_deployment(applied)



def test_prepare_refuses_unbounded_preimage_bytes_before_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifacts = sorted(bundle.artifacts, key=lambda row: str(row.destination))[:2]
    current: dict[str, bytes] = {}
    for index, artifact in enumerate(artifacts):
        artifact.destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        artifact.destination.parent.chmod(0o700)
        prior = bytes([65 + index]) * 12
        artifact.destination.write_bytes(prior)
        artifact.destination.chmod(artifact.mode)
        current[str(artifact.destination)] = prior

    monkeypatch.setattr(applier, "MAX_PREIMAGE_BYTES", 16, raising=False)
    monkeypatch.setattr(applier, "MAX_TOTAL_PREIMAGE_BYTES", 20, raising=False)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="PREIMAGE_TOO_LARGE",
    ):
        applier.prepare_deployment(
            bundle,
            deployment.plan_deployment(bundle, current),
            install_root=install_root,
            expected_uid=install_root.stat().st_uid,
            expected_gid=install_root.stat().st_gid,
            operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
        )

    for index, artifact in enumerate(artifacts):
        assert artifact.destination.read_bytes() == bytes([65 + index]) * 12


def test_cleanup_quarantine_name_uses_private_nonce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    values = iter((b"A" * 16, b"B" * 16))
    monkeypatch.setattr(applier.os, "urandom", lambda size: next(values))
    kwargs = {
        "install_root": install_root,
        "expected_uid": install_root.stat().st_uid,
        "expected_gid": install_root.stat().st_gid,
        "operation_key": "web-sol-install1-transactional-applier-source-20260916-sol-001",
    }

    first = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        **kwargs,
    )
    second = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        **kwargs,
    )

    assert applier._cleanup_quarantine_name("fixed.tmp", first) != (
        applier._cleanup_quarantine_name("fixed.tmp", second)
    )
    assert "cleanup_nonce" not in first.public_receipt


def test_cleanup_quarantine_name_rejects_nul(
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

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="APPLY_EFFECT_UNKNOWN",
    ):
        applier._cleanup_quarantine_name("bad\x00name", prepared)


def test_partial_temporary_identity_swap_is_not_unlinked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, install_root = _bundle(tmp_path)
    artifact = sorted(bundle.artifacts, key=lambda row: str(row.destination))[0]
    artifact.destination.parent.mkdir(parents=True, mode=0o700)
    prepared = applier.prepare_deployment(
        bundle,
        deployment.plan_deployment(bundle, {}),
        install_root=install_root,
        expected_uid=install_root.stat().st_uid,
        expected_gid=install_root.stat().st_gid,
        operation_key="web-sol-install1-transactional-applier-source-20260916-sol-001",
    )
    parent_descriptor = applier._open_verified_directory(
        artifact.destination.parent,
        prepared,
    )
    temporary_name = "partial-owned.tmp"
    foreign_name = "partial-foreign.tmp"
    foreign = b"foreign-partial-temporary"
    original_stat = applier.os.stat
    injected = False

    try:
        descriptor = applier.os.open(
            temporary_name,
            applier.os.O_WRONLY | applier.os.O_CREAT | applier.os.O_EXCL,
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            applier.os.write(descriptor, b"owned-partial-temporary")
            applier.os.fsync(descriptor)
            created = applier.os.fstat(descriptor)
        finally:
            applier.os.close(descriptor)
        foreign_descriptor = applier.os.open(
            foreign_name,
            applier.os.O_WRONLY | applier.os.O_CREAT | applier.os.O_EXCL,
            0o600,
            dir_fd=parent_descriptor,
        )
        try:
            applier.os.write(foreign_descriptor, foreign)
            applier.os.fsync(foreign_descriptor)
        finally:
            applier.os.close(foreign_descriptor)

        def stat_then_swap(name, *args, **kwargs):
            nonlocal injected
            observed = original_stat(name, *args, **kwargs)
            if (
                not injected
                and name == temporary_name
                and kwargs.get("dir_fd") == parent_descriptor
            ):
                injected = True
                applier.os.rename(
                    foreign_name,
                    temporary_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
            return observed

        monkeypatch.setattr(applier.os, "stat", stat_then_swap)

        with pytest.raises(
            applier.WebSolDeploymentApplyError,
            match="APPLY_EFFECT_UNKNOWN",
        ):
            applier._remove_owned_partial_temporary_at(
                parent_descriptor,
                temporary_name,
                created_dev=created.st_dev,
                created_ino=created.st_ino,
                prepared=prepared,
            )

        assert injected is True
        assert (artifact.destination.parent / temporary_name).read_bytes() == foreign
    finally:
        applier.os.close(parent_descriptor)


def test_created_directory_identity_swap_is_not_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    created: list[Path] = []
    applier._create_parent_directories(prepared, created)
    directory = max(created, key=lambda path: len(path.parts))
    foreign = directory.with_name(f"{directory.name}-foreign")
    displaced = directory.with_name(f"{directory.name}-displaced")
    foreign.mkdir(mode=0o700)
    original_listdir = applier.os.listdir
    injected = False

    def list_then_swap(descriptor: int) -> list[str]:
        nonlocal injected
        entries = original_listdir(descriptor)
        if not injected:
            injected = True
            directory.rename(displaced)
            foreign.rename(directory)
        return entries

    monkeypatch.setattr(applier.os, "listdir", list_then_swap)

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="ROLLBACK_EFFECT_UNKNOWN",
    ):
        applier._remove_created_directory(directory, prepared)

    assert injected is True
    assert directory.is_dir()
    assert displaced.is_dir()


def test_atomic_rename_unavailable_refuses_before_target_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(applier.sys, "platform", "unsupported-platform")

    with pytest.raises(
        applier.WebSolDeploymentApplyError,
        match="ATOMIC_RENAME_UNAVAILABLE",
    ):
        applier.apply_deployment(prepared)

    assert prepared._state == "PREPARED"
    assert list(install_root.rglob("*")) == []
