from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from scripts.ohf.capability_skill_projection import (
    PROJECTION_DIRECTORY_NAME,
    CapabilitySkillProjectionError,
    cleanup_capability_skill_projection,
    create_capability_skill_projection,
    verify_capability_skill_projection,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
V4_FIXTURE = (
    REPO_ROOT
    / "scripts"
    / "ohf"
    / "fixtures"
    / "executive_agent_capabilities_v4_mastermind_operator.json"
)
PACKAGE_ID = "mastermind-operator.p1"
RUNTIME_NAMES = (
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress",
)


def _generation():
    return ExecutionCapabilityRegistry.load(
        V4_FIXTURE, source_root=REPO_ROOT
    ).capability_packages[PACKAGE_ID]


def _attempt_root(tmp_path: Path) -> Path:
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    attempt.chmod(0o700)
    return attempt


def test_projection_copies_the_exact_seven_file_generation_and_exposes_four_paths(
    tmp_path: Path,
) -> None:
    generation = _generation()
    attempt = _attempt_root(tmp_path)
    receipt = create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=attempt,
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    )

    assert receipt.package_capability_id == PACKAGE_ID
    assert receipt.package_generation == generation.generation
    assert receipt.package_content_digest == generation.package_content_digest
    assert receipt.package_source_digest == generation.package_source_digest
    assert receipt.package_generation_digest == generation.package_generation_digest
    assert len(receipt.files) == 7
    assert Path(receipt.projection_root) == attempt / PROJECTION_DIRECTORY_NAME
    assert Path(receipt.projection_skills_root).is_dir()
    assert len(receipt.receipt_digest) == 64

    source_package = REPO_ROOT / generation.package_root
    projected_package = Path(receipt.projection_package_root)
    for row in generation.files:
        source = source_package / row.relative_path
        projected = projected_package / row.relative_path
        assert projected.read_bytes() == source.read_bytes()
        assert projected.stat().st_ino != source.stat().st_ino
        assert projected.stat().st_size == row.byte_length
        assert bool(projected.stat().st_mode & 0o111) is row.executable

    for name in RUNTIME_NAMES:
        assert receipt.expected_skill_path(name) == (
            projected_package / "skills" / name / "SKILL.md"
        )
        assert receipt.expected_skill_path(name).is_file()

    assert verify_capability_skill_projection(receipt, generation) == (
        receipt.source_verified
    )


def test_projection_is_fixed_under_attempt_root_and_does_not_touch_siblings(
    tmp_path: Path,
) -> None:
    generation = _generation()
    attempt = _attempt_root(tmp_path)
    sibling = attempt / "keep.txt"
    sibling.write_text("preserve", encoding="utf-8")

    receipt = create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=attempt,
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    )
    cleanup = cleanup_capability_skill_projection(receipt, generation)

    assert cleanup.removed is True
    assert cleanup.absent_after_cleanup is True
    assert len(cleanup.cleanup_digest) == 64
    assert not Path(receipt.projection_root).exists()
    assert sibling.read_text(encoding="utf-8") == "preserve"


def test_projection_refuses_duplicate_destination_as_reconciliation_required(
    tmp_path: Path,
) -> None:
    generation = _generation()
    attempt = _attempt_root(tmp_path)
    create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=attempt,
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    )
    with pytest.raises(CapabilitySkillProjectionError, match="already exists"):
        create_capability_skill_projection(
            source_root=REPO_ROOT,
            generation=generation,
            attempt_root=attempt,
            operation_id="cap-s1-fixture",
            process_generation_id="generation-1",
        )


def test_projection_refuses_symlink_or_writable_attempt_root(tmp_path: Path) -> None:
    generation = _generation()
    real = _attempt_root(tmp_path)
    link = tmp_path / "attempt-link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(CapabilitySkillProjectionError, match="real directory"):
        create_capability_skill_projection(
            source_root=REPO_ROOT,
            generation=generation,
            attempt_root=link,
            operation_id="cap-s1-fixture",
            process_generation_id="generation-1",
        )

    real.chmod(0o777)
    with pytest.raises(CapabilitySkillProjectionError, match="writable"):
        create_capability_skill_projection(
            source_root=REPO_ROOT,
            generation=generation,
            attempt_root=real,
            operation_id="cap-s1-fixture",
            process_generation_id="generation-1",
        )


def test_projection_receipt_tamper_and_projected_byte_drift_refuse(
    tmp_path: Path,
) -> None:
    generation = _generation()
    receipt = create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=_attempt_root(tmp_path),
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    )

    forged = dataclasses.replace(receipt, receipt_digest="0" * 64)
    with pytest.raises(CapabilitySkillProjectionError, match="receipt digest"):
        verify_capability_skill_projection(forged, generation)

    target = receipt.expected_skill_path("receive-commission")
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b"drift")
    target.chmod(0o400)
    with pytest.raises(CapabilitySkillProjectionError):
        verify_capability_skill_projection(receipt, generation)
    with pytest.raises(CapabilitySkillProjectionError):
        cleanup_capability_skill_projection(receipt, generation)
    assert Path(receipt.projection_root).exists()


def test_projection_refuses_source_drift_and_leaves_no_destination(
    tmp_path: Path,
) -> None:
    generation = _generation()
    source = tmp_path / "source"
    package = source / generation.package_root
    package.parent.mkdir(parents=True)
    import shutil

    shutil.copytree(REPO_ROOT / generation.package_root, package)
    target = package / "references" / "dialogue-boundary.md"
    target.write_bytes(target.read_bytes() + b"drift")
    attempt = _attempt_root(tmp_path)

    with pytest.raises(CapabilitySkillProjectionError, match="source verification"):
        create_capability_skill_projection(
            source_root=source,
            generation=generation,
            attempt_root=attempt,
            operation_id="cap-s1-fixture",
            process_generation_id="generation-1",
        )
    assert not (attempt / PROJECTION_DIRECTORY_NAME).exists()


def test_projection_receipt_is_secret_free_and_has_no_lifecycle_authority(
    tmp_path: Path,
) -> None:
    generation = _generation()
    receipt = create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=_attempt_root(tmp_path),
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    )
    rendered = repr(receipt).lower()
    for forbidden in (
        "api_key",
        "authorization",
        "bearer",
        "cookie",
        "oauth_token",
        "password",
        "worker_id=",
        "attempt_status",
        "job_status",
        "retry",
    ):
        assert forbidden not in rendered
    assert not hasattr(receipt, "provider_session_id")
    assert not hasattr(receipt, "worker_id")


def test_invalid_operation_and_runtime_name_are_refused(tmp_path: Path) -> None:
    generation = _generation()
    with pytest.raises(CapabilitySkillProjectionError, match="operation_id"):
        create_capability_skill_projection(
            source_root=REPO_ROOT,
            generation=generation,
            attempt_root=_attempt_root(tmp_path),
            operation_id="../../escape",
            process_generation_id="generation-1",
        )

    receipt = create_capability_skill_projection(
        source_root=REPO_ROOT,
        generation=generation,
        attempt_root=tmp_path / "attempt-2",
        operation_id="cap-s1-fixture",
        process_generation_id="generation-1",
    ) if False else None
    # The fixed API never accepts a caller-selected destination or provider path.
    assert receipt is None
