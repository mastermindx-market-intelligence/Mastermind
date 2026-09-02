"""RED-first tests for CAP-S1's attempt-local Skill projection.

Covers ``scripts/ohf/capability_skill_projection.py`` per:

- ``docs/superpowers/specs/2026-09-01-sol-capability-fabric-cap-s1-protocol-attestation-
  amendment.md`` §4 (exact source-root modes);
- ``docs/superpowers/specs/2026-09-01-sol-capability-fabric-cap-s1-vertical-amendment.md``
  §6.2 (Codex-only laboratory projection).

The canary runner's own tests (``scripts/ohf/cap_s1_mastermind_operator_canary.py``) are
appended to this module by a later commission; this section is scoped strictly to the
attempt-local projection primitive.
"""
from __future__ import annotations

import dataclasses
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    CapabilityPackageGeneration,
    VerifiedCapabilityPackage,
    build_capability_package_generation,
    verify_capability_package_source,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_INSTALLED_RELEASE,
    ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
    SkillProjectionCleanupReceipt,
    SkillProjectionError,
    SkillProjectionReceipt,
    _extract_safe_tar,
    cleanup_skill_projection,
    create_ephemeral_archive_origin,
    stage_skill_projection,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"
PACKAGE_ROOT = REPO_ROOT / "plugins" / "mastermind-operator"

EXPECTED_PACKAGE_SOURCE_DIGEST = "16a19d7399b8ff737b59c959cffbc9bedabee7a5fe0d6f05ced8172fd9870852"
EXPECTED_PACKAGE_GENERATION_DIGEST = "37836a5986c916a58217b95d1976220eae8827e4e588a50677011c2543e43b97"
REAL_SOURCE_COMMIT = "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"

OPERATION_ID = "mastermind-cap-s1-complete-vertical-20260901-sol-001"


def _load_real_generation() -> CapabilityPackageGeneration:
    raw_document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw_package = raw_document["capability_packages"]["mastermind-operator.p1"]
    return build_capability_package_generation(capability_id="mastermind-operator.p1", raw=raw_package)


def _resolve_repo_git_dir() -> Path:
    git_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-dir"], cwd=REPO_ROOT, text=True
    ).strip()
    git_dir_path = Path(git_dir)
    if not git_dir_path.is_absolute():
        git_dir_path = (REPO_ROOT / git_dir_path).resolve()
    return git_dir_path


# ---------------------------------------------------------------------------
# Fixture sanity: the frozen digests this whole module pins against
# ---------------------------------------------------------------------------


def test_fixture_generation_matches_frozen_digests():
    generation = _load_real_generation()
    assert generation.package_source_digest == EXPECTED_PACKAGE_SOURCE_DIGEST
    assert generation.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert len(generation.files) == 7
    assert generation.source_commit == REAL_SOURCE_COMMIT


# ---------------------------------------------------------------------------
# Happy path: INSTALLED_RELEASE-style origin (the repo root itself)
# ---------------------------------------------------------------------------


def test_stage_skill_projection_happy_path_installed_release(tmp_path):
    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=REPO_ROOT,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="happy-path-0001",
    )

    assert isinstance(receipt, SkillProjectionReceipt)
    assert receipt.origin_mode == ORIGIN_INSTALLED_RELEASE
    assert receipt.package_source_digest == EXPECTED_PACKAGE_SOURCE_DIGEST
    assert receipt.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert receipt.package_capability_id == "mastermind-operator.p1"
    assert receipt.package_generation == generation.generation
    assert receipt.repository == generation.repository
    assert receipt.source_commit == generation.source_commit
    assert receipt.source_tree_sha == generation.source_tree_sha
    assert len(receipt.file_rows) == 7
    assert {row[0] for row in receipt.file_rows} == {f.relative_path for f in generation.files}
    assert all(row[3] is False for row in receipt.file_rows)  # every real row is non-executable
    assert receipt.skills_root.endswith("/plugins/mastermind-operator/skills")
    assert receipt.projection_root.startswith(str(attempt_root))
    assert receipt.owning_operation_id == OPERATION_ID
    assert receipt.owning_process_generation == "happy-path-0001"
    assert receipt.cleanup_state == "LIVE"
    assert receipt.read_only_applied is True

    # Byte-identical re-verification through the real package verifier,
    # independent of stage_skill_projection's own internal call.
    reverified = verify_capability_package_source(receipt.projection_root, generation)
    assert isinstance(reverified, VerifiedCapabilityPackage)
    assert reverified.package_content_digest == generation.package_content_digest
    assert reverified.package_source_digest == EXPECTED_PACKAGE_SOURCE_DIGEST
    assert reverified.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert reverified.skill_content_digests == receipt.skill_content_digests

    # The projection tree is read-only: writing into it must fail.
    entrypoint = Path(receipt.projection_root) / "plugins/mastermind-operator/skills/escalate-decision/SKILL.md"
    assert entrypoint.is_file()
    with pytest.raises(OSError):
        entrypoint.write_bytes(b"tampered")

    cleanup = cleanup_skill_projection(receipt)
    assert isinstance(cleanup, SkillProjectionCleanupReceipt)
    assert cleanup.removed is True
    assert cleanup.verified_absent is True
    assert not Path(receipt.projection_root).exists()


# ---------------------------------------------------------------------------
# Ephemeral archive path
# ---------------------------------------------------------------------------


def test_ephemeral_archive_origin_and_projection_end_to_end(tmp_path):
    git_dir = _resolve_repo_git_dir()
    exists = (
        subprocess.run(
            ["git", f"--git-dir={git_dir}", "cat-file", "-e", REAL_SOURCE_COMMIT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )
    assert exists, (
        f"local object store lacks commit {REAL_SOURCE_COMMIT}; the ephemeral-archive mode "
        "cannot be proven without it (this is a hard failure, not a silent skip)"
    )

    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()

    origin_root = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
    )
    assert isinstance(origin_root, Path)

    verified = verify_capability_package_source(origin_root, generation)
    assert verified.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST

    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
        origin_root=origin_root,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="ephemeral-0001",
    )
    assert receipt.origin_mode == ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE
    assert receipt.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert len(receipt.file_rows) == 7

    cleanup = cleanup_skill_projection(receipt)
    assert cleanup.removed is True
    assert cleanup.verified_absent is True


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_stage_rejects_unsupported_origin_mode(tmp_path):
    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    with pytest.raises(SkillProjectionError):
        stage_skill_projection(
            generation=generation,
            origin_mode="NOT_A_REAL_MODE",
            origin_root=REPO_ROOT,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="bad-mode-0001",
        )


def test_stage_rejects_missing_attempt_root(tmp_path):
    generation = _load_real_generation()
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SkillProjectionError):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=REPO_ROOT,
            attempt_root=missing,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="missing-root-0001",
        )


def test_stage_rejects_symlinked_attempt_root(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = tmp_path / "link"
    os.symlink(real_dir, link_dir)

    generation = _load_real_generation()
    with pytest.raises(SkillProjectionError):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=REPO_ROOT,
            attempt_root=link_dir,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="symlink-root-0001",
        )


def test_stage_rejects_preexisting_projection_directory(tmp_path):
    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    gen_token = "exclusivity-0001"
    (attempt_root / f"skill-projection-{gen_token}").mkdir()

    with pytest.raises(SkillProjectionError):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=REPO_ROOT,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation=gen_token,
        )


def test_stage_rejects_tampered_origin_byte(tmp_path):
    import shutil

    generation = _load_real_generation()

    tampered_root = tmp_path / "tampered-origin"
    tampered_root.mkdir()
    shutil.copytree(PACKAGE_ROOT, tampered_root / "plugins" / "mastermind-operator")
    target = tampered_root / "plugins" / "mastermind-operator" / "skills" / "escalate-decision" / "SKILL.md"
    data = bytearray(target.read_bytes())
    data[0] ^= 0xFF
    target.write_bytes(bytes(data))

    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    # A tampered origin byte is refused by the package verifier itself, and
    # that refusal must propagate unwrapped -- stage_skill_projection never
    # masks a real CapabilityPackageError as its own SkillProjectionError.
    with pytest.raises(CapabilityPackageError):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=tampered_root,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="tamper-0001",
        )
    # Nothing should have been staged.
    assert list(attempt_root.iterdir()) == []


def test_extract_safe_tar_rejects_parent_traversal(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        payload = b"evil"
        info = tarfile.TarInfo(name="plugins/mastermind-operator/../../../evil.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(SkillProjectionError):
        _extract_safe_tar(buf.getvalue(), dest, "plugins/mastermind-operator")
    # Nothing should have been extracted.
    assert list(dest.iterdir()) == []


def test_extract_safe_tar_rejects_symlink_member(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(name="plugins/mastermind-operator/skills/escalate-decision/SKILL.md")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(SkillProjectionError):
        _extract_safe_tar(buf.getvalue(), dest, "plugins/mastermind-operator")


def test_extract_safe_tar_rejects_absolute_member(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        payload = b"evil"
        info = tarfile.TarInfo(name="/etc/evil.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(SkillProjectionError):
        _extract_safe_tar(buf.getvalue(), dest, "plugins/mastermind-operator")


def test_create_ephemeral_archive_origin_rejects_bad_source_commit(tmp_path):
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    with pytest.raises(SkillProjectionError):
        create_ephemeral_archive_origin(
            repository_git_dir=_resolve_repo_git_dir(),
            source_commit="not-a-commit",
            package_root="plugins/mastermind-operator",
            scratch_root=scratch_root,
        )


def test_create_ephemeral_archive_origin_rejects_missing_git_dir(tmp_path):
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    with pytest.raises(SkillProjectionError):
        create_ephemeral_archive_origin(
            repository_git_dir=tmp_path / "no-such-git-dir",
            source_commit=REAL_SOURCE_COMMIT,
            package_root="plugins/mastermind-operator",
            scratch_root=scratch_root,
        )


def test_create_ephemeral_archive_origin_rejects_unknown_commit(tmp_path):
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    with pytest.raises(SkillProjectionError):
        create_ephemeral_archive_origin(
            repository_git_dir=_resolve_repo_git_dir(),
            source_commit="f" * 40,
            package_root="plugins/mastermind-operator",
            scratch_root=scratch_root,
        )


def test_cleanup_refuses_doctored_projection_root_and_leaves_it_untouched(tmp_path):
    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=REPO_ROOT,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="containment-0001",
    )

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    marker = outside_dir / "still-here.txt"
    marker.write_text("do not delete", encoding="utf-8")

    doctored = dataclasses.replace(receipt, projection_root=str(outside_dir))
    with pytest.raises(SkillProjectionError):
        cleanup_skill_projection(doctored)
    assert marker.exists()
    assert marker.read_text(encoding="utf-8") == "do not delete"

    # A same-named-but-wrong-identity doctoring is refused too, even though
    # it passes the basename check.
    lookalike = tmp_path / f"skill-projection-{receipt.owning_process_generation}-lookalike"
    lookalike.mkdir()
    renamed_lookalike = tmp_path / f"skill-projection-{receipt.owning_process_generation}"
    # Only construct the collision if it does not already exist as the real
    # projection root (it does not -- the real one lives under attempt_root).
    assert not renamed_lookalike.exists()
    lookalike.rename(renamed_lookalike)
    lookalike_marker = renamed_lookalike / "also-here.txt"
    lookalike_marker.write_text("do not delete either", encoding="utf-8")

    doctored_lookalike = dataclasses.replace(receipt, projection_root=str(renamed_lookalike))
    with pytest.raises(SkillProjectionError):
        cleanup_skill_projection(doctored_lookalike)
    assert lookalike_marker.exists()

    # Clean up the real projection so the test leaves nothing behind.
    real_cleanup = cleanup_skill_projection(receipt)
    assert real_cleanup.removed is True
    assert real_cleanup.verified_absent is True


def test_error_messages_never_echo_hostile_origin_mode(tmp_path):
    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    hostile_mode = "/etc/passwd-should-not-leak-into-any-message"
    with pytest.raises(SkillProjectionError) as exc_info:
        stage_skill_projection(
            generation=generation,
            origin_mode=hostile_mode,
            origin_root=REPO_ROOT,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="no-echo-mode-0001",
        )
    assert hostile_mode not in str(exc_info.value)


def test_error_messages_never_echo_hostile_paths(tmp_path):
    generation = _load_real_generation()
    hostile_path = tmp_path / "\U0001F525do-not-echo-this-secret\U0001F525"
    with pytest.raises(SkillProjectionError) as exc_info:
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=REPO_ROOT,
            attempt_root=hostile_path,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="no-echo-path-0001",
        )
    message = str(exc_info.value)
    assert str(hostile_path) not in message
    assert "\U0001F525" not in message


def test_cleanup_reports_failure_honestly_when_parent_undeletable(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission checks; cannot force an undeletable directory")

    generation = _load_real_generation()
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=REPO_ROOT,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="undeletable-0001",
    )

    os.chmod(attempt_root, 0o555)
    try:
        cleanup = cleanup_skill_projection(receipt)
        assert cleanup.removed is False
        assert Path(receipt.projection_root).exists()
    finally:
        os.chmod(attempt_root, 0o700)
        final_cleanup = cleanup_skill_projection(receipt)
        assert final_cleanup.removed is True
        assert final_cleanup.verified_absent is True
