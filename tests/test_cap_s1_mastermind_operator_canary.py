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
import errno
import gc
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import threading
from pathlib import Path

import pytest

import scripts.ohf.capability_skill_projection as capability_skill_projection
from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    CapabilityPackageGeneration,
    VerifiedCapabilityPackage,
    build_capability_package_generation,
    verify_capability_package_source,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE,
    ORIGIN_AUTHENTICATION_INSTALLED_RELEASE,
    ORIGIN_INSTALLED_RELEASE,
    ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
    EphemeralGitOriginReceipt,
    SkillProjectionCleanupReceipt,
    SkillProjectionError,
    SkillProjectionReceipt,
    _extract_safe_tar,
    cleanup_skill_projection,
    create_ephemeral_archive_origin,
    stage_skill_projection,
    validate_skill_projection_receipt,
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


def _real_package_tree_sha() -> str:
    git_dir = _resolve_repo_git_dir()
    return subprocess.check_output(
        ["git", f"--git-dir={git_dir}", "rev-parse", f"{REAL_SOURCE_COMMIT}:plugins/mastermind-operator"],
        text=True,
    ).strip()


def _build_installed_release_origin(
    root_dir: Path, generation: CapabilityPackageGeneration, *, basename: "str | None" = None
) -> Path:
    """Build a small, real (non-symlink) INSTALLED_RELEASE-shaped origin by
    copying the real, already-reviewed package tree under a directory named
    after the generation's ``source_commit`` -- the Executive installer's
    ``releases/<sha>`` layout ``stage_skill_projection`` now authenticates
    against (Sol wave-3 review finding M6). ``basename`` overrides the
    directory name for the negative authentication tests.
    """
    name = generation.source_commit if basename is None else basename
    release_root = root_dir / name
    package_dest = release_root / generation.package_root
    package_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE_ROOT, package_dest)
    return release_root


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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
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

    # --- Sol wave-3 M6 hardening: the extended receipt shape -------------
    assert receipt.schema_version == "mastermind.skill_projection_receipt/v1"
    assert receipt.origin_authentication == ORIGIN_AUTHENTICATION_INSTALLED_RELEASE
    assert tuple(sorted(receipt.origin_rows)) == tuple(sorted(receipt.projection_rows))
    assert len(receipt.origin_rows) == 7
    assert receipt.origin_resolved_root == os.path.realpath(str(origin_root))
    assert receipt.projection_resolved_root == os.path.realpath(receipt.projection_root)
    assert receipt.attempt_root == str(attempt_root)
    assert receipt.attempt_root_identity == (os.lstat(str(attempt_root)).st_dev, os.lstat(str(attempt_root)).st_ino)
    assert receipt.created_at_monotonic_ns > 0
    # A happy-path receipt is, by construction, its own valid witness.
    validate_skill_projection_receipt(receipt)

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
    assert cleanup.schema_version == "mastermind.skill_projection_cleanup/v1"
    assert not Path(receipt.projection_root).exists()


# ---------------------------------------------------------------------------
# INSTALLED_RELEASE authentication (Sol wave-3 review finding M6)
# ---------------------------------------------------------------------------


def test_stage_installed_release_rejects_unauthenticated_basename(tmp_path):
    """A byte-identical origin under a basename that is NOT the exact
    generation ``source_commit`` no longer authenticates as
    ``INSTALLED_RELEASE`` -- a plain checkout root must refuse, not just a
    hostile one."""
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(
        tmp_path / "origin", generation, basename="not-the-source-commit"
    )
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    with pytest.raises(SkillProjectionError, match="installed_release_root_unauthenticated"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="unauthenticated-basename-0001",
        )
    # Nothing should have been staged.
    assert list(attempt_root.iterdir()) == []


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

    origin_receipt = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
        expected_package_tree_sha=generation.source_tree_sha,
    )
    assert isinstance(origin_receipt, EphemeralGitOriginReceipt)
    assert origin_receipt.schema_version == "mastermind.ephemeral_git_origin/v1"
    assert origin_receipt.source_commit == REAL_SOURCE_COMMIT
    assert origin_receipt.source_tree_sha == generation.source_tree_sha
    assert origin_receipt.member_count == 7
    origin_root = Path(origin_receipt.origin_root)

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
        origin_receipt=origin_receipt,
    )
    assert receipt.origin_mode == ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE
    assert receipt.origin_authentication == ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE
    assert receipt.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert len(receipt.file_rows) == 7
    validate_skill_projection_receipt(receipt)

    cleanup = cleanup_skill_projection(receipt)
    assert cleanup.removed is True
    assert cleanup.verified_absent is True


# ---------------------------------------------------------------------------
# Ephemeral origin receipt (Sol wave-3 review finding M6)
# ---------------------------------------------------------------------------


def test_create_ephemeral_archive_origin_expected_package_tree_sha_mismatch_refuses(tmp_path):
    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()

    with pytest.raises(SkillProjectionError, match="package_tree_sha_mismatch"):
        create_ephemeral_archive_origin(
            repository_git_dir=git_dir,
            source_commit=REAL_SOURCE_COMMIT,
            package_root=generation.package_root,
            scratch_root=scratch_root,
            expected_package_tree_sha="f" * 40,
        )


def test_create_ephemeral_archive_origin_rolls_back_on_unexpected_archive_error(
    tmp_path, monkeypatch
):
    """Ownership starts at the exclusive origin-root mkdir, not at receipt return."""

    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()

    def _unexpected_archive_error(*_args, **_kwargs):
        raise RuntimeError("synthetic unexpected archive failure")

    monkeypatch.setattr(
        capability_skill_projection, "_run_git_archive", _unexpected_archive_error
    )

    with pytest.raises(SkillProjectionError, match="origin_root: creation_failed"):
        create_ephemeral_archive_origin(
            repository_git_dir=git_dir,
            source_commit=REAL_SOURCE_COMMIT,
            package_root=generation.package_root,
            scratch_root=scratch_root,
            expected_package_tree_sha=generation.source_tree_sha,
        )

    assert list(scratch_root.iterdir()) == []


def test_create_ephemeral_archive_origin_bounded_write_survives_short_writes(
    tmp_path, monkeypatch
):
    """Archive extraction must complete, reread and hash every intended post-image."""

    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    real_os_write = os.write

    def _short_os_write(fd, data):
        return real_os_write(fd, bytes(data)[:5])

    monkeypatch.setattr(capability_skill_projection.os, "write", _short_os_write)
    receipt = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
        expected_package_tree_sha=generation.source_tree_sha,
    )

    verified = verify_capability_package_source(receipt.origin_root, generation)
    assert verified.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert receipt.inventory_digest
    shutil.rmtree(receipt.origin_root)


def test_stage_ephemeral_rederives_git_origin_provenance_at_consumption(
    tmp_path, monkeypatch
):
    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()
    origin_receipt = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
        expected_package_tree_sha=generation.source_tree_sha,
    )
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    real_git_rev = capability_skill_projection._git_rev_or_none

    def _drifted_git_rev(repository_git_dir, *args):
        if args and args[0] == "rev-parse" and ":" in args[-1]:
            return "f" * 40
        return real_git_rev(repository_git_dir, *args)

    monkeypatch.setattr(capability_skill_projection, "_git_rev_or_none", _drifted_git_rev)
    with pytest.raises(SkillProjectionError, match="git_provenance_mismatch"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
            origin_root=Path(origin_receipt.origin_root),
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="rederived-origin-0001",
            origin_receipt=origin_receipt,
        )
    assert list(attempt_root.iterdir()) == []
    shutil.rmtree(origin_receipt.origin_root)


def test_stage_ephemeral_without_origin_receipt_refuses(tmp_path):
    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()

    origin_receipt = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
    )
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    with pytest.raises(SkillProjectionError, match="ephemeral_origin_receipt_required"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
            origin_root=Path(origin_receipt.origin_root),
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="no-receipt-0001",
        )
    assert list(attempt_root.iterdir()) == []


def test_stage_ephemeral_with_doctored_origin_receipt_refuses(tmp_path):
    git_dir = _resolve_repo_git_dir()
    generation = _load_real_generation()
    scratch_root = tmp_path / "scratch"
    scratch_root.mkdir()

    origin_receipt = create_ephemeral_archive_origin(
        repository_git_dir=git_dir,
        source_commit=REAL_SOURCE_COMMIT,
        package_root=generation.package_root,
        scratch_root=scratch_root,
    )
    doctored = dataclasses.replace(origin_receipt, source_commit="f" * 40)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    with pytest.raises(SkillProjectionError, match="ephemeral_origin_receipt_commit_mismatch"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
            origin_root=Path(origin_receipt.origin_root),
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="doctored-receipt-0001",
            origin_receipt=doctored,
        )
    assert list(attempt_root.iterdir()) == []


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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SkillProjectionError, match="attempt_root_unavailable"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    with pytest.raises(SkillProjectionError, match="attempt_root_symlink_refused"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
            attempt_root=link_dir,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="symlink-root-0001",
        )


def test_stage_rejects_preexisting_projection_directory(tmp_path):
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    gen_token = "exclusivity-0001"
    (attempt_root / f"skill-projection-{gen_token}").mkdir()

    with pytest.raises(SkillProjectionError, match="projection_root_exists"):
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
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


def test_cleanup_refuses_doctored_attempt_root_identity_and_deletes_nothing(tmp_path):
    """Sol wave-3 review finding M6: cleanup authorization must bind the
    EXACT attempt-root parent identity, not merely the projection root's own
    basename and inode. A receipt whose ``attempt_root_identity`` no longer
    matches the real parent directory's identity refuses -- even though the
    projection root's own name and identity are perfectly correct -- and the
    real tree must survive untouched."""
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="parent-binding-0001",
    )

    other_dir = tmp_path / "some-other-directory"
    other_dir.mkdir()
    other_identity = (os.lstat(str(other_dir)).st_dev, os.lstat(str(other_dir)).st_ino)
    assert other_identity != receipt.attempt_root_identity

    doctored = dataclasses.replace(receipt, attempt_root_identity=other_identity)
    with pytest.raises(SkillProjectionError, match="projection_root_parent_identity_mismatch"):
        cleanup_skill_projection(doctored)

    # Nothing was deleted: the real projection tree survives.
    assert Path(receipt.projection_root).exists()
    reverified = verify_capability_package_source(receipt.projection_root, generation)
    assert reverified.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST

    # Clean up for real so the test leaves nothing behind.
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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    hostile_path = tmp_path / "\U0001F525do-not-echo-this-secret\U0001F525"
    with pytest.raises(SkillProjectionError) as exc_info:
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
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
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
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


def test_cleanup_non_enoent_precheck_error_never_proves_absence(
    tmp_path, monkeypatch
):
    receipt = _staged_happy_receipt(tmp_path)
    projection_root = receipt.projection_root
    real_lstat = os.lstat

    def _permission_refusal(path, *args, **kwargs):
        if str(path) == projection_root:
            raise PermissionError(errno.EACCES, "synthetic access refusal")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(capability_skill_projection.os, "lstat", _permission_refusal)
    with pytest.raises(SkillProjectionError, match="projection_root_unavailable"):
        cleanup_skill_projection(receipt)
    assert Path(projection_root).exists()
    monkeypatch.setattr(capability_skill_projection.os, "lstat", real_lstat)
    cleanup_skill_projection(receipt)


def test_cleanup_non_enoent_postcheck_error_never_proves_absence(
    tmp_path, monkeypatch
):
    receipt = _staged_happy_receipt(tmp_path)
    projection_root = receipt.projection_root
    real_lstat = os.lstat
    calls = {"projection": 0}

    def _post_remove_io_error(path, *args, **kwargs):
        if str(path) == projection_root:
            calls["projection"] += 1
            if calls["projection"] == 2:
                raise OSError(errno.EIO, "synthetic post-remove I/O error")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(capability_skill_projection.os, "lstat", _post_remove_io_error)
    cleanup = cleanup_skill_projection(receipt)
    assert cleanup.removed is False
    assert cleanup.verified_absent is False


# ---------------------------------------------------------------------------
# validate_skill_projection_receipt: self-validation boundary
# (Sol wave-3 review finding M6)
# ---------------------------------------------------------------------------


def _staged_happy_receipt(tmp_path) -> SkillProjectionReceipt:
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()
    return stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="validate-witness-0001",
    )


def test_validate_skill_projection_receipt_accepts_the_happy_receipt(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    validate_skill_projection_receipt(receipt)  # must not raise
    cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_wrong_type():
    with pytest.raises(SkillProjectionError, match="invalid_receipt_type"):
        validate_skill_projection_receipt(object())


def test_validate_skill_projection_receipt_rejects_bad_schema_version(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        doctored = dataclasses.replace(receipt, schema_version="not-a-real-schema-version")
        with pytest.raises(SkillProjectionError, match="invalid_schema_version"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_origin_projection_rows_mismatch(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        tampered_rows = tuple(receipt.projection_rows[:-1])  # drop one row
        doctored = dataclasses.replace(receipt, projection_rows=tampered_rows)
        with pytest.raises(SkillProjectionError, match="origin_projection_rows_mismatch"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_non_hex64_digest(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        doctored = dataclasses.replace(receipt, package_content_digest="not-hex-at-all")
        with pytest.raises(SkillProjectionError, match="invalid_digest"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_non_hex64_row_digest(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        bad_row = (receipt.origin_rows[0][0], "not-a-real-sha256", receipt.origin_rows[0][2], receipt.origin_rows[0][3])
        doctored = dataclasses.replace(receipt, origin_rows=(bad_row, *receipt.origin_rows[1:]))
        with pytest.raises(SkillProjectionError, match="invalid_row_digest"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_bad_authentication_token(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        doctored = dataclasses.replace(receipt, origin_authentication="not-a-real-authentication-token")
        with pytest.raises(SkillProjectionError, match="unsupported_value"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_doctored_attempt_root_identity_shape(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        doctored = dataclasses.replace(receipt, attempt_root_identity=("not", "a", "tuple-of-two-ints"))
        with pytest.raises(SkillProjectionError, match="invalid_identity_shape"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


def test_validate_skill_projection_receipt_rejects_non_positive_monotonic_ns(tmp_path):
    receipt = _staged_happy_receipt(tmp_path)
    try:
        doctored = dataclasses.replace(receipt, created_at_monotonic_ns=0)
        with pytest.raises(SkillProjectionError, match="invalid_value"):
            validate_skill_projection_receipt(doctored)
    finally:
        cleanup_skill_projection(receipt)


# ---------------------------------------------------------------------------
# Rollback on partial staging (Sol wave-3 review finding M6)
# ---------------------------------------------------------------------------


def test_stage_skill_projection_rolls_back_orphan_tree_on_mid_staging_failure(tmp_path, monkeypatch):
    """A failure injected AFTER the exclusive projection-root mkdir (here: a
    seam failure partway through copying the declared files) must leave NO
    projection root behind, and the re-raised error must carry the bounded
    ``rollback_complete`` outcome token -- never a leaked path."""
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    real_write_exclusive_file = capability_skill_projection._write_exclusive_file
    call_count = {"n": 0}

    def _flaky_write_exclusive_file(parent_fd, name, data, executable):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OSError("synthetic mid-staging failure (no path here)")
        return real_write_exclusive_file(parent_fd, name, data, executable)

    monkeypatch.setattr(capability_skill_projection, "_write_exclusive_file", _flaky_write_exclusive_file)

    with pytest.raises(SkillProjectionError) as exc_info:
        stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_INSTALLED_RELEASE,
            origin_root=origin_root,
            attempt_root=attempt_root,
            owning_operation_id=OPERATION_ID,
            owning_process_generation="rollback-0001",
        )

    assert call_count["n"] == 3  # the seam actually fired mid-copy, not before or never
    assert "rollback_complete" in str(exc_info.value)
    assert list(attempt_root.iterdir()) == []  # no orphan projection root


# ---------------------------------------------------------------------------
# Bounded write loop (Sol wave-3 review finding M6)
# ---------------------------------------------------------------------------


def test_stage_skill_projection_bounded_write_loop_survives_short_writes(tmp_path, monkeypatch):
    """``os.write`` returning far fewer bytes than requested must not
    truncate a staged file -- the bounded write loop must keep writing
    until every declared byte has landed."""
    generation = _load_real_generation()
    origin_root = _build_installed_release_origin(tmp_path / "origin", generation)
    attempt_root = tmp_path / "attempt"
    attempt_root.mkdir()

    real_os_write = os.write

    def _short_os_write(fd, data):
        return real_os_write(fd, bytes(data)[:7])

    monkeypatch.setattr(capability_skill_projection.os, "write", _short_os_write)

    receipt = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
        attempt_root=attempt_root,
        owning_operation_id=OPERATION_ID,
        owning_process_generation="short-write-0001",
    )

    reverified = verify_capability_package_source(receipt.projection_root, generation)
    assert reverified.package_generation_digest == EXPECTED_PACKAGE_GENERATION_DIGEST
    assert len(receipt.projection_rows) == 7

    cleanup_skill_projection(receipt)


# ===========================================================================
# CAP-S1 phase 11: the canary runner itself
# ===========================================================================
#
# Covers ``scripts/ohf/cap_s1_mastermind_operator_canary.py`` per:
#
# - the protocol-attestation amendment §2 (schema source precedence), §5
#   (fresh-process causal isolation), §9 (exact real-model journey and
#   evidence receipt), §11 (failure vocabulary);
# - the vertical amendment §9 (real canary journey and evidence).
#
# Every test here drives ``backend="fake"``: a REAL ``python -m
# scripts.ohf.fake_app_server`` subprocess (the same fake-App-Server harness
# pattern ``tests/test_codex_operator_adapter.py`` uses for its own
# skill-canary tests), wrapped by a small scripted client that can
# substitute individual ``skills/list``/``turn/start`` responses. The
# real Codex binary is never referenced, imported, or invoked anywhere in
# this section -- schema generation is driven entirely through an injected
# ``run_command`` fake, never the real ``subprocess.run`` default, and every
# ``client_factory`` below asserts its own argv never names a "codex"
# executable.

import shutil
import subprocess as _subprocess
import sys as _sys

from control_plane.codex_operator_adapter import CodexProtocolAttestationReceipt
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.operator_harness_contract import LaunchDecision
from scripts.ohf.cap_s1_mastermind_operator_canary import (
    PROFILE_ID as _CANARY_PROFILE_ID,
    CANARY_EVIDENCE_SCHEMA_VERSION,
    RESULT_CONTRACT_MARKER,
    RESULT_CONTRACT_SCHEMA,
    RESULT_RELEASE_STATE,
    CanaryCleanupRecord,
    CanaryEvidence,
    CanaryStop,
    CAP_S1_OBSERVER_MUTANT_TRANSFORMS,
    CAP_S1_OBSERVER_TEST_MODULES,
    CAP_S1_GITLEAKS_ARCHIVE_BYTES,
    CAP_S1_GITLEAKS_ARCHIVE_MEMBERS,
    CAP_S1_GITLEAKS_ARCHIVE_SHA256,
    CAP_S1_GITLEAKS_ARCHIVE_URL,
    CAP_S1_GITLEAKS_RULE_COUNT,
    CAP_S1_GITLEAKS_RULE_SHA256,
    CAP_S1_GITLEAKS_SOURCE_COMMIT,
    CAP_S1_GITLEAKS_VERSION,
    CAP_S1_SECRET_CONTROL_RECIPES,
    CapS1Result,
    CapS1ResultError,
    FAKE_HARNESS_VERSION,
    FROZEN_STOP_CODES,
    _SCHEMA_FIXTURE_BINARY_SOURCE,
    _RESULT_ALL_CLEANUP_KINDS,
    _build_cap_s1_result_from_fixture,
    _assemble_cap_s1_secret_controls,
    _CapS1SecretSourceEntry,
    _CapS1SourceCopyEntry,
    _CapS1OwnedProcessCleanupObservation,
    _CapS1OwnedRootIdentity,
    _CapS1GitHubObservations,
    _canonical_digest,
    _capture_cap_s1_interpreter_identity,
    _consume_cap_s1_fake_canary_for_fixture,
    _extract_cap_s1_gitleaks_binary,
    _finalize_cap_s1_observer_cleanup,
    _download_cap_s1_pinned_bytes,
    _github_api_json as _real_github_api_json,
    _load_cap_s1_producer_evidence,
    _parse_cap_s1_gitleaks_coverage,
    _parse_cap_s1_gitleaks_report,
    _parse_cap_s1_junit,
    _parse_cap_s1_mutation_junit,
    _observe_cap_s1_codeql,
    _observe_cap_s1_diff,
    _observe_cap_s1_mutations,
    _register_cap_s1_canary_evidence,
    _revalidate_cap_s1_observer_source,
    _register_cap_s1_owned_root,
    _run_cap_s1_observer_bytes,
    _run_cap_s1_observer_process,
    _run_cap_s1_python_observer_process,
    _run_cap_s1_source_observer,
    _revalidate_cap_s1_interpreter_identity,
    _strict_json_loads,
    _stage_cap_s1_secret_source,
    _verify_cap_s1_secret_manifest,
    _validate_cap_s1_result_against_producer,
    attest_protocol_schema,
    build_cap_s1_result as _public_build_cap_s1_result,
    build_synthetic_workspace,
    cap_s1_observer_registry,
    main as canary_main,
    run_canary,
)
from scripts.ohf.laboratory import AppServerClient, default_user_codex_home


def build_cap_s1_result(**kwargs):
    """Fixture-only compatibility wrapper for the structural contract tests."""

    return _build_cap_s1_result_from_fixture(**kwargs)


def validate_cap_s1_result(result, *, producer_evidence_path):
    """Validate against a fixture artifact without entering the full observer."""

    return _validate_cap_s1_result_against_producer(
        result,
        producer_evidence=_load_cap_s1_producer_evidence(producer_evidence_path),
    )


def _load_canary_profile():
    registry = ExecutionCapabilityRegistry.load(FIXTURE_PATH, source_root=REPO_ROOT)
    return registry.resolve(_CANARY_PROFILE_ID)

_SKILL_INPUT_WITH_PATH = {
    "type": "object",
    "properties": {
        "type": {"enum": ["skill"], "type": "string"},
        "name": {"type": "string"},
        "path": {"type": "string"},
    },
    "required": ["name", "path", "type"],
    "title": "SkillUserInput",
}

_SKILL_INPUT_WITHOUT_PATH = {
    "type": "object",
    "properties": {
        "type": {"enum": ["skill"], "type": "string"},
        "name": {"type": "string"},
    },
    "required": ["name", "type"],
    "title": "SkillUserInput",
}


def _turn_start_schema(skill_input: dict, *, unrelated_skill_fragment: bool = False) -> dict:
    """Hand-built shape of generated ``v2/TurnStartParams.json``.

    The expected path is deliberately literal: the production resolver must
    enter at ``properties.input.items``, follow the local ``UserInput`` ref,
    and select the one Skill union member.  An unrelated Skill-shaped object
    may coexist in the same document without becoming request authority.
    """

    definitions = {
        "UserInput": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "type": {"enum": ["text"], "type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["text", "type"],
                    "title": "TextUserInput",
                },
                skill_input,
            ]
        }
    }
    if unrelated_skill_fragment:
        definitions["DeprecatedSkillResponse"] = _SKILL_INPUT_WITH_PATH
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": definitions,
        "properties": {
            "input": {
                "items": {"$ref": "#/definitions/UserInput"},
                "type": "array",
            },
            "threadId": {"type": "string"},
        },
        "required": ["input", "threadId"],
        "title": "TurnStartParams",
        "type": "object",
    }


_SCHEMA_WITH_SKILL_PATH = _turn_start_schema(_SKILL_INPUT_WITH_PATH)
_SCHEMA_WITHOUT_SKILL_PATH = _turn_start_schema(_SKILL_INPUT_WITHOUT_PATH)
_SCHEMA_WITHOUT_SKILL_PATH_PLUS_UNRELATED_FRAGMENT = _turn_start_schema(
    _SKILL_INPUT_WITHOUT_PATH,
    unrelated_skill_fragment=True,
)

_HAPPY_REPLIES = [
    "PICKUP-ACK received for cap-s1-synthetic-op.",
    "PROGRESS: bounded synthetic steps underway.",
    "DECISION-REQUEST: need Sol ruling on branch alpha.",
    "RESULT: synthetic operation finished; awaiting review.",
]


def _asserts_never_the_real_codex_binary(argv) -> None:
    """Refuse any argv naming a "codex" executable (basename match, never a
    generic path-prefix match -- the interpreter running the fake backend
    can legitimately live under a package-manager prefix that a naive
    substring check would misclassify as a real binary path)."""

    assert not any(Path(str(part)).name == "codex" for part in argv), (
        "real Codex binary must never be invoked"
    )


def _fake_schema_run_command(schema_doc, *, extra_schema_docs=None):
    """Write ``schema_doc`` to whichever ``--out`` directory is requested.

    The written payload embeds ``out_dir.name`` ("stable" or "experimental",
    per ``attest_protocol_schema``'s own two fixed subdirectory names) so the
    stable and experimental inventory digests this fixture produces are
    genuinely distinct -- matching what a real ``--experimental`` schema
    dump would look like -- while staying a pure, deterministic function of
    ``(schema_doc, variant)`` so
    ``test_attest_protocol_schema_with_skill_path_supports_true_and_is_
    deterministic`` still sees identical digests across two independent
    runs of the same schema_doc.
    """

    def run_command(argv, **kwargs):
        _asserts_never_the_real_codex_binary(argv)
        # ``run_command`` is now the single injectable seam for BOTH schema
        # generation AND the synthetic workspace's real git init/commit
        # (Sol wave-3 review finding B2) -- a real ``git`` invocation is
        # passed straight through to the real ``subprocess.run`` (the
        # workspace itself is a real temp directory; there is nothing to
        # fake here), while a schema-generation call (identified by its own
        # ``--out`` flag) is answered with this fixture's deterministic
        # payload, never actually invoking the fixture "binary".
        if argv and argv[0] == "git":
            return _subprocess.run(argv, **kwargs)
        out_dir = Path(argv[argv.index("--out") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        turn_start_path = out_dir / "v2" / "TurnStartParams.json"
        turn_start_path.parent.mkdir(parents=True, exist_ok=True)
        turn_start_path.write_text(json.dumps(schema_doc), encoding="utf-8")
        (out_dir / "inventory-variant.json").write_text(
            json.dumps({"variant": out_dir.name}), encoding="utf-8"
        )
        for relative_path, document in (extra_schema_docs or {}).items():
            destination = out_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(document), encoding="utf-8")
        return _subprocess.CompletedProcess(argv, 0)

    return run_command


def _failing_schema_run_command(argv, **_kwargs):
    return _subprocess.CompletedProcess(argv, 1, stdout="", stderr="synthetic failure")


_CREATED_CANARY_CLIENTS: list = []


class _ScriptedCanaryClient:
    """Wraps a real fake-App-Server ``AppServerClient``.

    Records every RPC call and can substitute scripted sequential
    ``skills/list`` responses (mirroring
    ``tests/test_codex_operator_adapter.py::_RecordingSkillsClient``), a
    scripted per-turn model reply keyed by call order, a synthetic
    transport failure on a chosen ``turn/start`` call -- used only to prove
    the runner's ``EFFECT_UNKNOWN`` no-retry law -- and a synthetic
    ``skills/changed`` notification injected right after a chosen
    ``turn/start`` call accepts, appended directly onto the wrapped real
    client's own ``notifications`` queue (the same list
    ``drain_notifications``/``wait_notification`` read) so it is ingested
    exactly like a real out-of-band notification during that turn's own
    event collection -- used to prove ``SKILLS_CHANGED_DURING_CANARY``.
    Every other RPC always reaches the real fake App Server subprocess.
    """

    def __init__(
        self,
        inner,
        *,
        skills_list_script=None,
        replies=None,
        fail_turn_start_at=None,
        config_read_mutator=None,
        inject_skills_changed_after_turn_starts=None,
        force_post_clear_nonempty=False,
    ) -> None:
        self._inner = inner
        self._skills_list_script = list(skills_list_script or [])
        self._replies = list(replies or [])
        self._native_turn_replies: dict[str, str] = {}
        self._fail_turn_start_at = fail_turn_start_at
        self._turn_start_calls = 0
        self._config_read_mutator = config_read_mutator
        self._inject_skills_changed_after_turn_starts = inject_skills_changed_after_turn_starts
        # CAP-S1 item 9 "post-turn drift refusal" falsifier: the ONE
        # skills/list read immediately after the runner's own final
        # ``extraRoots/set []`` clear is forced non-empty, simulating a
        # provider whose skill surface silently failed to actually clear.
        # The adapter's OWN internal causal sequence already issues one
        # earlier ``extraRoots/set []`` as its baseline probe (before ever
        # adding the canary's roots) -- only the SECOND empty-clear call is
        # the runner's own final teardown step, so only that one is armed.
        self._force_post_clear_nonempty = force_post_clear_nonempty
        self._empty_extra_roots_set_calls = 0
        self._extra_roots_just_cleared = False
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def request(self, method, params=None, *, timeout: float = 15.0):
        self.calls.append((method, dict(params or {})))
        if method == "skills/extraRoots/set" and self._force_post_clear_nonempty:
            if isinstance(params, dict) and params.get("extraRoots") == []:
                self._empty_extra_roots_set_calls += 1
                if self._empty_extra_roots_set_calls == 2:
                    self._extra_roots_just_cleared = True
        if method == "skills/list" and self._extra_roots_just_cleared:
            self._extra_roots_just_cleared = False
            cwd = ""
            if isinstance(params, dict):
                cwds = params.get("cwds")
                if isinstance(cwds, list) and cwds:
                    cwd = str(cwds[0])
            return _strict_skills_list_result(
                cwd, [_skill_row("rogue-post-clear-skill", path=f"{cwd}/rogue-post-clear-skill/SKILL.md")]
            )
        if method == "skills/list" and self._skills_list_script:
            return self._skills_list_script.pop(0)
        if method == "turn/start":
            self._turn_start_calls += 1
            if self._fail_turn_start_at == self._turn_start_calls:
                raise ConnectionError("synthetic transport failure")
        result = self._inner.request(method, params, timeout=timeout)
        if (
            method == "turn/start"
            and self._inject_skills_changed_after_turn_starts == self._turn_start_calls
        ):
            self._inner.notifications.append({"method": "skills/changed", "params": {}})
        if method == "config/read" and self._config_read_mutator is not None:
            result = self._config_read_mutator(result)
        if method == "turn/start" and self._replies:
            turn_obj = result.get("turn") if isinstance(result.get("turn"), dict) else {}
            native_turn_id = str(turn_obj.get("id") or "")
            if native_turn_id:
                self._native_turn_replies[native_turn_id] = self._replies.pop(0)
        elif method == "thread/turns/list" and isinstance(result.get("data"), list):
            patched = []
            for row in result["data"]:
                native_id = str(row.get("id") or "")
                if native_id in self._native_turn_replies:
                    reply = self._native_turn_replies[native_id]
                    row = dict(row)
                    row["text"] = reply
                    row["items"] = [
                        {
                            "type": "agentMessage",
                            "text": reply,
                            "content": [{"type": "text", "text": reply}],
                        }
                    ]
                patched.append(row)
            result = dict(result)
            result["data"] = patched
        return result


def _canary_client_factory(
    *,
    skills_list_script=None,
    replies=None,
    fail_turn_start_at=None,
    on_create=None,
    config_read_mutator=None,
    inject_skills_changed_after_turn_starts=None,
    force_post_clear_nonempty=False,
):
    def factory(argv, env, cwd):
        _asserts_never_the_real_codex_binary(argv)
        if on_create is not None:
            on_create()
        inner = AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)
        client = _ScriptedCanaryClient(
            inner,
            skills_list_script=skills_list_script,
            replies=replies,
            fail_turn_start_at=fail_turn_start_at,
            config_read_mutator=config_read_mutator,
            inject_skills_changed_after_turn_starts=inject_skills_changed_after_turn_starts,
            force_post_clear_nonempty=force_post_clear_nonempty,
        )
        _CREATED_CANARY_CLIENTS.append(client)
        return client

    return factory


def _strip_bundled_from_config_read(result):
    """Simulate an App Server that never echoes ``skills.bundled`` back.

    Deep-copies the scripted fake server's real ``config/read`` reply and
    removes the ``skills`` key the runner's ``OHF_FAKE_BUNDLED_DISABLED=1``
    wiring added -- this is the config-digest attestation gate's falsifier:
    the profile's ``expected_config_digest`` requires
    ``skills.bundled.enabled=false``, so a real config/read that omits it
    must produce ``REFUSE_CONFIG_DRIFT``, never a silent ALLOW.
    """

    copied = json.loads(json.dumps(result))
    config = copied.get("config")
    if isinstance(config, dict):
        config.pop("skills", None)
    return copied


@pytest.fixture(autouse=True)
def _close_created_canary_clients(monkeypatch, tmp_path):
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    global _CAP_S1_PRODUCER_EVIDENCE_DIR, _CAP_S1_PRODUCER_EVIDENCE_COUNTER
    _CAP_S1_PRODUCER_EVIDENCE_DIR = tmp_path
    _CAP_S1_PRODUCER_EVIDENCE_COUNTER = 0

    def _fake_github_api_json(endpoint: str):
        if endpoint == "repos/mastermindx-market-intelligence/Mastermind/actions/runs/33741521536":
            return {
                "id": 33741521536,
                "status": "completed",
                "conclusion": "success",
                "head_sha": "a" * 40,
            }
        if endpoint.startswith(
            "repos/mastermindx-market-intelligence/Mastermind/actions/runs/33741521536/jobs?"
        ):
            return {
                "total_count": 1,
                "jobs": [
                    {
                        "id": 100000000001,
                        "name": "test",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
            }
        if endpoint == "repos/mastermindx-market-intelligence/Mastermind/pulls/350":
            return {
                "user": {"login": "chriswong6031-creator", "id": 101},
                "head": {"sha": "a" * 40},
            }
        if endpoint == (
            "repos/mastermindx-market-intelligence/Mastermind/pulls/350/reviews/5104652791"
        ):
            return {
                "id": 5104652791,
                "state": "APPROVED",
                "commit_id": "a" * 40,
                "user": {"login": "mastermindx-3", "id": 303},
            }
        raise AssertionError(f"unexpected fake GitHub endpoint: {endpoint}")

    monkeypatch.setattr(canary_module, "_github_api_json", _fake_github_api_json, raising=False)
    _CREATED_CANARY_CLIENTS.clear()
    yield
    for client in _CREATED_CANARY_CLIENTS:
        try:
            client.close()
        except Exception:
            pass
    _CREATED_CANARY_CLIENTS.clear()
    _CAP_S1_PRODUCER_EVIDENCE_DIR = None


def _cleanup_map(record) -> dict:
    """``CanaryCleanupRecord.artifacts`` (Sol wave-3 review finding B4) as a
    ``{kind: (removed, verified_absent)}`` mapping -- the same shape the
    tests below used to read off the old mutable dict, minus the renamed
    keys."""

    return {kind: (removed, verified_absent) for kind, removed, verified_absent in record.artifacts}


def _strict_skills_list_result(cwd: str, rows: list) -> dict:
    return {"data": [{"cwd": cwd, "skills": rows, "errors": []}]}


def _skill_row(name: str, *, path: "str | None" = None, enabled: bool = True) -> dict:
    row: dict[str, object] = {"name": name, "enabled": enabled}
    if path is not None:
        row["path"] = path
    return row


# ---------------------------------------------------------------------------
# attest_protocol_schema
# ---------------------------------------------------------------------------


def _write_launchable_single_binary(path: Path) -> None:
    """A REAL, launchable copy of the committed single-binary fixture
    (CAP-S1 Sol review item 1): unlike the old plain-bytes stub, the
    receipt's own ``probe_user_agent`` now comes from a genuine
    ``initialize`` RPC against this exact file, so ``attest_protocol_schema``
    callers need a binary that can actually be launched as an App Server."""

    path.write_text(_SCHEMA_FIXTURE_BINARY_SOURCE, encoding="utf-8")
    path.chmod(0o755)


def _probe_env(probe_root: Path) -> dict:
    codex_home = probe_root / "codex-home"
    codex_home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(codex_home),
        "CODEX_HOME": str(codex_home),
        "PYTHONPATH": str(REPO_ROOT),
        "OHF_FAKE_STATE": str(probe_root / "fake-state.json"),
        "OHF_FAKE_MODEL": "gpt-5.6-sol",
        "OHF_FAKE_MCP_GONE": "1",
        "LC_ALL": "C",
    }


def test_attest_protocol_schema_with_skill_path_supports_true_and_is_deterministic(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-a"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-a"
    _write_launchable_single_binary(binary)
    probe_root = tmp_path / "probe-a"
    probe_root.mkdir()
    env = _probe_env(probe_root)

    first = attest_protocol_schema(
        binary_path=binary,
        scratch_root=scratch,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        probe_env=env,
        probe_cwd=probe_root,
    )
    assert isinstance(first, CodexProtocolAttestationReceipt)
    assert first.supports_skill_input_path is True
    assert first.binary_digest
    assert first.probe_user_agent == FAKE_HARNESS_VERSION
    assert first.binary_version == FAKE_HARNESS_VERSION
    assert first.receipt_digest

    scratch_2 = tmp_path / "scratch-a-2"
    scratch_2.mkdir()
    second = attest_protocol_schema(
        binary_path=binary,
        scratch_root=scratch_2,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        probe_env=env,
        probe_cwd=probe_root,
    )
    assert second.stable_inventory_digest == first.stable_inventory_digest
    assert second.experimental_inventory_digest == first.experimental_inventory_digest
    assert second.binary_digest == first.binary_digest
    assert second.receipt_digest == first.receipt_digest


def test_attest_protocol_schema_missing_path_evidence_supports_false(tmp_path) -> None:
    scratch = tmp_path / "scratch-b"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-b"
    _write_launchable_single_binary(binary)
    probe_root = tmp_path / "probe-b"
    probe_root.mkdir()

    attestation = attest_protocol_schema(
        binary_path=binary,
        scratch_root=scratch,
        run_command=_fake_schema_run_command(_SCHEMA_WITHOUT_SKILL_PATH),
        probe_env=_probe_env(probe_root),
        probe_cwd=probe_root,
    )
    assert attestation.supports_skill_input_path is False
    assert attestation.skill_input_schema_evidence == ""


def test_attest_protocol_schema_ignores_unrelated_skill_shaped_fragment(tmp_path) -> None:
    """A path on a deprecated/response-like definition is not evidence that
    the real ``turn/start`` request input accepts a Skill path."""

    scratch = tmp_path / "scratch-unrelated-skill-fragment"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-unrelated-skill-fragment"
    _write_launchable_single_binary(binary)
    probe_root = tmp_path / "probe-unrelated-skill-fragment"
    probe_root.mkdir()

    attestation = attest_protocol_schema(
        binary_path=binary,
        scratch_root=scratch,
        run_command=_fake_schema_run_command(
            _SCHEMA_WITHOUT_SKILL_PATH_PLUS_UNRELATED_FRAGMENT
        ),
        probe_env=_probe_env(probe_root),
        probe_cwd=probe_root,
    )

    assert attestation.supports_skill_input_path is False
    assert attestation.skill_input_schema_evidence == ""


def test_attest_protocol_schema_refuses_ambiguous_turn_start_documents(tmp_path) -> None:
    """Two generated candidates for the request schema fail closed instead
    of letting arbitrary inventory order choose one."""

    scratch = tmp_path / "scratch-ambiguous-turn-start"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-ambiguous-turn-start"
    _write_launchable_single_binary(binary)
    probe_root = tmp_path / "probe-ambiguous-turn-start"
    probe_root.mkdir()

    attestation = attest_protocol_schema(
        binary_path=binary,
        scratch_root=scratch,
        run_command=_fake_schema_run_command(
            _SCHEMA_WITH_SKILL_PATH,
            extra_schema_docs={"legacy/TurnStartParams.json": _SCHEMA_WITH_SKILL_PATH},
        ),
        probe_env=_probe_env(probe_root),
        probe_cwd=probe_root,
    )

    assert attestation.supports_skill_input_path is False
    assert attestation.skill_input_schema_evidence == ""


def test_canary_stop_only_accepts_a_frozen_code() -> None:
    for code in FROZEN_STOP_CODES:
        stop = CanaryStop(code, "detail")
        assert stop.code == code
    with pytest.raises(ValueError):
        CanaryStop("NOT_A_FROZEN_CODE")


def test_attest_protocol_schema_failing_command_stops_unattested(tmp_path) -> None:
    scratch = tmp_path / "scratch-c"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-c"
    binary.write_bytes(b"fixture codex binary bytes")

    with pytest.raises(CanaryStop) as excinfo:
        attest_protocol_schema(
            binary_path=binary, scratch_root=scratch, run_command=_failing_schema_run_command
        )
    assert excinfo.value.code == "SKILL_PROTOCOL_SCHEMA_UNATTESTED"


def test_attest_protocol_schema_unlaunchable_binary_stops_unattested(tmp_path) -> None:
    """The schema-generation half can succeed via an injected ``run_command``
    fake while the binary itself is not genuinely launchable -- the REAL
    initialize probe (CAP-S1 Sol review item 1) must still refuse, never
    fabricate a ``probe_user_agent``."""

    scratch = tmp_path / "scratch-unlaunchable"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-unlaunchable"
    binary.write_bytes(b"not an executable")
    probe_root = tmp_path / "probe-unlaunchable"
    probe_root.mkdir()

    with pytest.raises(CanaryStop) as excinfo:
        attest_protocol_schema(
            binary_path=binary,
            scratch_root=scratch,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
            probe_env=_probe_env(probe_root),
            probe_cwd=probe_root,
        )
    assert excinfo.value.code == "SKILL_PROTOCOL_SCHEMA_UNATTESTED"
    # Sol wave-3 review finding B4 self-cleanup still applies to the new
    # probe failure path: the sealed schema dir never survives the stop.
    assert not (scratch / "schema-attestation").exists()


def test_attest_protocol_schema_unexpected_error_rolls_back_sealed_root(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-schema-unexpected"
    scratch.mkdir()
    binary = tmp_path / "fixture-binary-schema-unexpected"
    binary.write_bytes(b"fixture")

    def _unexpected(*_args, **_kwargs):
        raise RuntimeError("synthetic unexpected schema seam")

    with pytest.raises(RuntimeError, match="synthetic unexpected schema seam"):
        attest_protocol_schema(
            binary_path=binary,
            scratch_root=scratch,
            run_command=_unexpected,
        )
    assert not (scratch / "schema-attestation").exists()


# ---------------------------------------------------------------------------
# build_synthetic_workspace
# ---------------------------------------------------------------------------


def test_build_synthetic_workspace_is_fresh_and_contains_only_readme(tmp_path) -> None:
    scratch = tmp_path / "scratch-ws"
    workspace, base_sha, read_only_applied = build_synthetic_workspace(
        scratch, operation_id="test-op-ws"
    )
    assert workspace.is_dir()
    entries = {entry.name for entry in workspace.iterdir()}
    # A real, sealed git repo now lives alongside the README (Sol wave-3
    # review finding B2) -- ``.git`` is not one of the forbidden ambient
    # surface names below.
    assert entries == {"README.md", ".git"}
    assert "CAP-S1 synthetic canary workspace" in (workspace / "README.md").read_text(
        encoding="utf-8"
    )
    for name in (".agents", ".codex", "plugins", "marketplace", "skills"):
        assert not (workspace / name).exists()
    assert re.fullmatch(r"[0-9a-f]{40}", base_sha)
    assert isinstance(read_only_applied, bool)


def test_build_synthetic_workspace_refuses_a_preexisting_directory(tmp_path) -> None:
    scratch = tmp_path / "scratch-ws-2"
    build_synthetic_workspace(scratch, operation_id="test-op-ws-2")
    with pytest.raises(FileExistsError):
        build_synthetic_workspace(scratch, operation_id="test-op-ws-2")


def test_build_synthetic_workspace_unexpected_error_rolls_back_workspace(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-ws-unexpected"
    scratch.mkdir()

    def _unexpected(*_args, **_kwargs):
        raise RuntimeError("synthetic unexpected workspace seam")

    with pytest.raises(RuntimeError, match="synthetic unexpected workspace seam"):
        build_synthetic_workspace(
            scratch,
            operation_id="test-op-ws-unexpected",
            run_command=_unexpected,
        )
    assert not (scratch / "synthetic-workspace").exists()


# ---------------------------------------------------------------------------
# run_canary: full fake journey happy path
# ---------------------------------------------------------------------------


def test_run_canary_fake_backend_happy_path_four_turn_journey(tmp_path) -> None:
    scratch = tmp_path / "scratch-happy"
    scratch.mkdir()
    factory = _canary_client_factory(replies=list(_HAPPY_REPLIES))

    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-canary-happy",
        protected_join="c" * 40,
        client_factory=factory,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )

    assert isinstance(evidence, CanaryEvidence)
    assert evidence.launch_decision == "ALLOW"
    # Config-digest attestation gate (protocol amendment §5): the happy
    # path now runs with ``expected_config_digest`` armed end to end --
    # the observed attestation's digest must equal the profile's own
    # expectation, not merely be non-None.
    profile = _load_canary_profile()
    assert evidence.app_server_config_digest == profile.expected_config_digest
    assert evidence.turn_marker_results == (
        ("receive-commission", True),
        ("return-progress", True),
        ("escalate-decision", True),
        ("finish-operation", True),
    )
    assert evidence.observed_enabled_names == (
        "escalate-decision",
        "finish-operation",
        "receive-commission",
        "return-progress",
    )
    assert evidence.baseline_enabled_names == evidence.observed_enabled_names
    assert evidence.after_add_enabled_names == evidence.observed_enabled_names
    assert evidence.after_clear_enabled_names == ()
    assert evidence.schema_version == "mastermind.cap_s1_canary_evidence/v1"
    assert evidence.protected_join == "c" * 40
    assert evidence.origin_mode == ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE
    assert evidence.origin_authentication == ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE
    assert evidence.skills_root
    assert evidence.binary_digest
    assert evidence.binary_version == f"{FAKE_HARNESS_VERSION} (mastermind-ohf/p1b)"
    assert evidence.protocol_receipt_digest
    cleanup_map = _cleanup_map(evidence.cleanup)
    assert set(cleanup_map) == {
        "schema",
        "workspace",
        "origin",
        "projection",
        "attempt",
        "thread",
        "process",
    }
    for kind in ("schema", "workspace", "origin", "projection", "attempt", "thread"):
        assert cleanup_map[kind] == (True, True), (kind, cleanup_map[kind])
    assert evidence.served_model
    assert evidence.terminal_process_state
    assert evidence.package_source_digest
    assert evidence.package_generation_digest
    assert len(evidence.skill_grant_digests) == 4
    assert len(evidence.skill_closure_digests) == 4
    assert evidence.extra_roots_set_outcomes == ("cleared",)

    # The whole receipt must be JSON-serializable (it is printed verbatim by
    # the CLI).
    json.dumps(dataclasses.asdict(evidence))

    # Cleanup actually happened on disk.
    assert not Path(evidence.workspace_root).exists()


# ---------------------------------------------------------------------------
# config-digest attestation gate (protocol amendment §5)
# ---------------------------------------------------------------------------


def test_probe_env_is_immune_to_inherited_terminal_identity(tmp_path, monkeypatch):
    """Second live EFFECT_UNKNOWN (PR #350): the probe env was a SUPERSET of
    the adapter launch env, and the real binary embeds env-derived terminal
    identity into its userAgent -- so the probe sealed a version the
    sanitized launch could never observe. The probe env is now built from
    empty, byte-equal to CodexOperatorAdapter._env. This regression taints
    the inherited environment with a userAgent-affecting variable (echoed
    by the fake under OHF_FAKE_UA_SUFFIX) and proves the journey still
    completes: pre-fix, the tainted var reached ONLY the probe and the
    launch refused on version inequality."""
    monkeypatch.setenv("OHF_FAKE_UA_SUFFIX", "tainted-terminal-identity")
    scratch = tmp_path / "scratch-env-immunity"
    scratch.mkdir()
    factory = _canary_client_factory(replies=list(_HAPPY_REPLIES))
    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-canary-env-immunity",
        protected_join="c" * 40,
        client_factory=factory,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )
    assert evidence.launch_decision == "ALLOW"
    assert "tainted-terminal-identity" not in evidence.binary_version


def test_probe_client_identity_mismatch_reproduces_the_live_version_refusal(tmp_path, monkeypatch):
    """The live canary refused EFFECT_UNKNOWN because the attestation probe
    identified as a different client than the launch, and the real App
    Server's userAgent incorporates the caller's clientInfo (PR #350
    reconciliation). With the clientInfo-echoing fake this defect class is
    now fake-detectable: a mismatched probe identity must reproduce the
    exact version-equality refusal, while the unified one-truth identity
    passes (every other green fake-journey test in this file)."""
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(
        canary_module,
        "_PROBE_CLIENT_INFO",
        {"name": "cap-s1-canary-probe", "title": "Mismatched Probe", "version": "p1b"},
    )
    scratch = tmp_path / "scratch-probe-mismatch"
    scratch.mkdir()
    factory = _canary_client_factory(replies=list(_HAPPY_REPLIES))
    with pytest.raises(CanaryStop) as exc:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-probe-mismatch",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert exc.value.code == "EFFECT_UNKNOWN"
    assert "version" in exc.value.detail


def test_run_canary_fake_backend_bundled_omission_refuses_config_drift(tmp_path) -> None:
    """The re-armed gate's runner-level falsifier.

    Everything else about the journey is identical to the happy path: the
    fake App Server still echoes ``skills.bundled.enabled=false`` from its
    own state (``OHF_FAKE_BUNDLED_DISABLED=1``, wired unconditionally by
    ``run_canary`` for this V4 skill-grant profile), but the scripted
    client strips the ``skills`` key back out of the raw ``config/read``
    reply before the adapter ever sees it -- simulating a real App Server
    that never echoes the override. ``expected_config_digest`` is now
    always sealed onto this profile's requested profile, so the observed
    digest mismatch must REFUSE_CONFIG_DRIFT rather than silently ALLOW,
    and the four-turn journey must never run.
    """

    scratch = tmp_path / "scratch-bundled-omit"
    scratch.mkdir()
    factory = _canary_client_factory(
        replies=list(_HAPPY_REPLIES),
        config_read_mutator=_strip_bundled_from_config_read,
    )

    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-canary-bundled-omit",
        protected_join="c" * 40,
        client_factory=factory,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )

    assert evidence.launch_decision == LaunchDecision.REFUSE_CONFIG_DRIFT.value
    assert evidence.launch_decision != LaunchDecision.ALLOW.value
    profile = _load_canary_profile()
    assert evidence.app_server_config_digest != profile.expected_config_digest
    # The turn loop is gated on ALLOW; a refused launch must never run it.
    assert evidence.turn_marker_results == ()

    # Consistent with the runner's existing decision handling (``main``'s
    # ``launch_ok`` gate): a non-ALLOW decision maps to a nonzero exit.
    markers_ok = all(ok for _name, ok in evidence.turn_marker_results)
    cleanup_ok = evidence.cleanup.all_removed
    launch_ok = evidence.launch_decision == LaunchDecision.ALLOW.value
    exit_code = 0 if (markers_ok and cleanup_ok and launch_ok) else 1
    assert exit_code == 1


# ---------------------------------------------------------------------------
# marker detection
# ---------------------------------------------------------------------------


def test_run_canary_records_a_false_marker_without_raising(tmp_path) -> None:
    scratch = tmp_path / "scratch-marker"
    scratch.mkdir()
    non_compliant_replies = [
        _HAPPY_REPLIES[0],
        "PROGRESS COMPLETE synthetic operation is already done.",  # forbidden COMPLETE
        _HAPPY_REPLIES[2],
        _HAPPY_REPLIES[3],
    ]
    factory = _canary_client_factory(replies=non_compliant_replies)

    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-canary-marker",
        protected_join="c" * 40,
        client_factory=factory,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )

    assert evidence.turn_marker_results == (
        ("receive-commission", True),
        ("return-progress", False),
        ("escalate-decision", True),
        ("finish-operation", True),
    )
    # main()'s exit-code behavior on a false marker is covered by
    # test_cli_main_exits_nonzero_when_a_marker_is_false_or_cleanup_failed
    # below; this test scopes strictly to run_canary's own non-raising
    # recording law.


# ---------------------------------------------------------------------------
# ambient skill surface
# ---------------------------------------------------------------------------


def test_run_canary_ambient_skill_surface_stops(tmp_path) -> None:
    scratch = tmp_path / "scratch-ambient"
    scratch.mkdir()
    workspace_cwd = str((scratch / "synthetic-workspace").resolve())
    script = [
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(
            workspace_cwd,
            [_skill_row("rogue-skill", path="/fake-ambient-skills/rogue-skill/SKILL.md")],
        ),
    ]
    factory = _canary_client_factory(skills_list_script=script)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-ambient",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "AMBIENT_SKILL_SURFACE_NOT_EMPTY"


# ---------------------------------------------------------------------------
# CAP-S1 gap fill: dedicated stop-code coverage for the three
# ``_mapped_stop_for_adapter_error`` mappings that (before this commission)
# had no test of their own -- only AMBIENT_SKILL_SURFACE_NOT_EMPTY did.
# ---------------------------------------------------------------------------


def _expected_skills_root(scratch: Path, operation_id: str) -> str:
    """The exact ``skills_root`` ``stage_skill_projection`` will compute.

    Deterministic from ``scratch_root``, ``operation_id``, and the real
    reviewed package's own ``package_root`` -- reproduced here independently
    (not imported from the staging module) so a scripted ``skills/list``
    response can name syntactically-correct per-skill paths before the
    projection is ever staged.
    """

    generation = _load_real_generation()
    process_generation_id = f"{operation_id}-gen1"
    return str(
        scratch
        / "cap-s1-attempt-root"
        / f"skill-projection-{process_generation_id}"
        / generation.package_root
        / "skills"
    )


def _required_runtime_names() -> tuple[str, ...]:
    return tuple(sorted(grant.runtime_name for grant in _load_real_generation().skills))


def test_run_canary_extra_enabled_skill_after_root_add_is_causality_failed(tmp_path) -> None:
    """An extra, correctly-pathed skill row after the root add refuses.

    ``_skill_rows_to_observed`` compares the enabled name *set* (and count)
    against the profile's required runtime names -- a fifth, unrequested but
    otherwise well-formed row makes the sets unequal and must map to
    ``SKILL_SET_CAUSALITY_FAILED``, never silently accepted as "close
    enough".
    """

    scratch = tmp_path / "scratch-causality-extra"
    scratch.mkdir()
    workspace_cwd = str((scratch / "synthetic-workspace").resolve())
    operation_id = "cap-s1-canary-causality-extra"
    skills_root = _expected_skills_root(scratch, operation_id)
    required_names = _required_runtime_names()
    assert len(required_names) == 4

    after_add_rows = [
        _skill_row(name, path=f"{skills_root}/{name}/SKILL.md") for name in required_names
    ] + [_skill_row("rogue-extra-skill", path=f"{skills_root}/rogue-extra-skill/SKILL.md")]
    # Three scripted `skills/list` responses, in real call order:
    #   1. the generic ambient probe `_initialize_and_attest` issues before
    #      the CAP-S1 skill-canary sequence even begins (lenient parser,
    #      unrelated to the canary binding -- must stay empty or it trips
    #      AMBIENT_SKILL_SURFACE_NOT_EMPTY instead of the causality check
    #      this test targets);
    #   2. the causal sequence's own baseline (post `extraRoots/set []`),
    #      which must also be empty for the same reason;
    #   3. the causal sequence's post-root-add read -- this is the one
    #      carrying the extra unrequested row.
    script = [
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(workspace_cwd, after_add_rows),
    ]
    factory = _canary_client_factory(skills_list_script=script)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id=operation_id,
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "SKILL_SET_CAUSALITY_FAILED"

    # No retry: skills/list is read exactly three times (generic ambient
    # probe + causal-sequence baseline + post-root-add) and the runner never
    # starts a turn once the causal sequence refuses.
    assert len(_CREATED_CANARY_CLIENTS) == 1
    client = _CREATED_CANARY_CLIENTS[0]
    skills_list_calls = [call for call in client.calls if call[0] == "skills/list"]
    assert len(skills_list_calls) == 3
    turn_start_calls = [call for call in client.calls if call[0] == "turn/start"]
    assert len(turn_start_calls) == 0


def test_run_canary_pathless_request_with_unrelated_skill_fragment_refuses_before_thread_start(
    tmp_path,
) -> None:
    """Pathless post-add rows with an unsupportive schema refuse.

    When the App Server's ``skills/list`` rows carry no ``path`` field at
    all (mode B), the runner can only trust runtime-name identity if the
    attested protocol schema itself declares a ``path`` on the Skill turn
    input.  The real request union here omits it while a deprecated schema
    fragment does carry a Skill-shaped path, so
    ``binding.schema_supports_skill_input_path`` is False and this must map
    to ``SKILL_PATH_ATTESTATION_UNAVAILABLE`` rather than silently trusting
    the name-only rows.
    """

    scratch = tmp_path / "scratch-attestation-unavailable"
    scratch.mkdir()
    workspace_cwd = str((scratch / "synthetic-workspace").resolve())
    operation_id = "cap-s1-canary-attestation-unavailable"
    required_names = _required_runtime_names()

    after_add_rows = [_skill_row(name) for name in required_names]  # no `path` key at all
    # Same three-slot ordering as the causality test above: generic ambient
    # probe, causal-sequence baseline (both empty), then the pathless
    # post-root-add rows this test targets.
    script = [
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(workspace_cwd, after_add_rows),
    ]
    factory = _canary_client_factory(skills_list_script=script)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id=operation_id,
            protected_join="c" * 40,
            client_factory=factory,
            # The schema fixture WITHOUT the skill input path -- the fake
            # binary is never invoked; this is just the JSON doc the
            # injected run_command writes out for attest_protocol_schema.
            run_command=_fake_schema_run_command(
                _SCHEMA_WITHOUT_SKILL_PATH_PLUS_UNRELATED_FRAGMENT
            ),
        )
    assert (
        excinfo.value.code == "SKILL_PATH_ATTESTATION_UNAVAILABLE"
    ), "CAP_A_UNRELATED_SKILL_ACCEPTED"

    assert len(_CREATED_CANARY_CLIENTS) == 1
    client = _CREATED_CANARY_CLIENTS[0]
    skills_list_calls = [call for call in client.calls if call[0] == "skills/list"]
    assert len(skills_list_calls) == 3
    turn_start_calls = [call for call in client.calls if call[0] == "turn/start"]
    assert len(turn_start_calls) == 0
    thread_start_calls = [call for call in client.calls if call[0] == "thread/start"]
    assert len(thread_start_calls) == 0


def test_run_canary_skills_changed_notification_stops_before_the_next_turn(tmp_path) -> None:
    """A ``skills/changed`` notification during turn 1 stops turn 2.

    The launch causal sequence, real skill projection, and turn 1 itself
    all proceed exactly as the happy path -- no ``skills_list_script``
    override is used, so the real fake App Server discovers the real
    staged skills on disk, matching the happy-path test's approach. A
    synthetic ``skills/changed`` notification is appended directly to the
    real client's own notification queue right after turn 1's ``turn/start``
    accepts (mirroring the fake App Server's own
    ``OHF_FAKE_SKILLS_CHANGED`` behavior, which notifies right after
    ``skills/extraRoots/set`` -- here scripted at the RPC layer instead,
    since ``run_canary`` does not expose that env switch to callers). Turn
    1's own event collection ingests the notification and sets
    ``state.skills_changed``; the pre-turn revalidation before turn 2 must
    see it and refuse before ever calling ``turn/start`` a second time.
    """

    scratch = tmp_path / "scratch-skills-changed"
    scratch.mkdir()
    factory = _canary_client_factory(
        replies=list(_HAPPY_REPLIES),
        inject_skills_changed_after_turn_starts=1,
    )

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-skills-changed",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "SKILLS_CHANGED_DURING_CANARY"

    # No retry: turn 1 was allowed to start exactly once, and the refusal
    # before turn 2 must never re-attempt a second turn/start call.
    assert len(_CREATED_CANARY_CLIENTS) == 1
    client = _CREATED_CANARY_CLIENTS[0]
    turn_start_calls = [call for call in client.calls if call[0] == "turn/start"]
    assert len(turn_start_calls) == 1


# ---------------------------------------------------------------------------
# residual refusal rows (CAP-S1 Sol review item 3)
# ---------------------------------------------------------------------------


def test_run_canary_empty_candidate_identity_refuses_before_provider_start(
    tmp_path, monkeypatch
) -> None:
    """An empty/whitespace candidate identity -- a doctored generation whose
    ``source_commit``/``source_tree_sha`` a real reviewed source can never
    actually produce (``build_capability_package_generation`` itself already
    refuses those at the field-format level; this proves the runner's OWN
    independent check closes the gap even if that upstream guarantee ever
    weakened) -- refuses as a TYPED, deterministic ``CanaryStop`` before any
    provider process starts (CAP-S1 Sol review item 3).
    """

    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    real_generation = _load_real_generation()
    doctored_generation = dataclasses.replace(
        real_generation, source_commit="", source_tree_sha=""
    )
    monkeypatch.setattr(
        canary_module, "build_capability_package_generation", lambda **_kwargs: doctored_generation
    )

    scratch = tmp_path / "scratch-empty-candidate"
    scratch.mkdir()
    factory = _canary_client_factory()

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-empty-candidate",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert not (
        scratch / "cap-s1-attempt-root"
    ).exists(), "CAP_C_FIRST_EFFECT_CLEANUP_BYPASSED"
    assert len(_CREATED_CANARY_CLIENTS) == 0


def test_run_canary_workspace_git_commit_failure_is_provider_realm_unavailable(
    tmp_path,
) -> None:
    """A workspace whose git commit could not be created is a bounded
    ``PROVIDER_REALM_UNAVAILABLE`` refusal, and cleanup still runs for every
    resource already registered by the time the failure occurs (CAP-S1 Sol
    review item 3)."""

    scratch = tmp_path / "scratch-ws-commit-fail"
    scratch.mkdir()
    schema_run_command = _fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH)

    def failing_workspace_run_command(argv, **kwargs):
        if argv and argv[0] == "git" and "commit" in argv:
            return _subprocess.CompletedProcess(
                argv, 1, stdout="", stderr="synthetic commit failure"
            )
        if argv and argv[0] == "git":
            return _subprocess.run(argv, **kwargs)
        return schema_run_command(argv, **kwargs)

    factory = _canary_client_factory()

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-ws-commit-fail",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=failing_workspace_run_command,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert not (scratch / "cap-s1-attempt-root").exists()
    # No provider process was ever started.
    assert len(_CREATED_CANARY_CLIENTS) == 0
    # The schema-attestation cleanup action, registered BEFORE the
    # workspace-build step that failed, still ran via the outer ledger; the
    # partially-built workspace tore itself down via its own internal
    # CanaryStop handler.
    assert not (scratch / "schema-attestation").exists()
    assert not (scratch / "synthetic-workspace").exists()


# ---------------------------------------------------------------------------
# live-backend realm validation
# ---------------------------------------------------------------------------


def test_run_canary_live_backend_refuses_missing_codex_home_without_running_command(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-live-1"
    scratch.mkdir()

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("run_command must never be invoked for an unavailable realm")

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="live",
            binary_path=Path("/nonexistent/synthetic-codex-binary"),
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-live-realm",
            protected_join="c" * 40,
            client_factory=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("client_factory must never be invoked")
            ),
            run_command=_must_not_run,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert not (scratch / "cap-s1-attempt-root").exists()


def test_run_canary_live_backend_refuses_default_codex_home_without_running_command(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-live-2"
    scratch.mkdir()

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("run_command must never be invoked for an unavailable realm")

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="live",
            binary_path=Path("/nonexistent/synthetic-codex-binary"),
            codex_home=default_user_codex_home(),
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-live-realm-2",
            protected_join="c" * 40,
            client_factory=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("client_factory must never be invoked")
            ),
            run_command=_must_not_run,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert not (scratch / "cap-s1-attempt-root").exists()


def test_run_canary_live_home_validation_never_echoes_hostile_path(tmp_path) -> None:
    scratch = tmp_path / "scratch-live-hostile-home"
    scratch.mkdir()
    hostile_home = tmp_path / "secret-token-do-not-echo"

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="live",
            binary_path=Path("/nonexistent/synthetic-codex-binary"),
            codex_home=hostile_home,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-live-hostile-home",
            protected_join="c" * 40,
            client_factory=lambda *_a, **_k: None,
        )
    message = str(excinfo.value)
    assert str(hostile_home) not in message
    assert "secret-token-do-not-echo" not in message
    assert not (scratch / "cap-s1-attempt-root").exists()


# ---------------------------------------------------------------------------
# EFFECT_UNKNOWN, no retry
# ---------------------------------------------------------------------------


def test_run_canary_transport_failure_mid_turn_is_effect_unknown_with_no_retry(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-effect-unknown"
    scratch.mkdir()
    factory = _canary_client_factory(fail_turn_start_at=1)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-effect-unknown",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "EFFECT_UNKNOWN"

    assert len(_CREATED_CANARY_CLIENTS) == 1
    client = _CREATED_CANARY_CLIENTS[0]
    turn_start_calls = [call for call in client.calls if call[0] == "turn/start"]
    assert len(turn_start_calls) == 1


# ---------------------------------------------------------------------------
# Failure-bounded cleanup (Sol wave-3 review finding B4): EVERYTHING created
# after scratch setup -- schema dir, synthetic workspace, archive origin,
# projection -- is torn down on EVERY exit path, never just the happy one.
# ---------------------------------------------------------------------------


def _assert_scratch_has_no_leaked_resources(scratch: Path) -> None:
    assert not (scratch / "synthetic-workspace").exists()
    for entry in scratch.iterdir():
        assert not entry.name.startswith("schema-attestation-"), entry
        assert not entry.name.startswith("ephemeral-archive-"), entry
    assert not (scratch / "cap-s1-attempt-root").exists()


def test_canary_cleanup_record_requires_exact_closed_zero_survivor_inventory() -> None:
    exact = CanaryCleanupRecord(
        artifacts=tuple(
            (kind, True, True)
            for kind in (
                "process",
                "thread",
                "projection",
                "origin",
                "attempt",
                "workspace",
                "schema",
            )
        )
    )
    assert exact.all_removed is True
    assert CanaryCleanupRecord(artifacts=exact.artifacts[:-1]).all_removed is False
    assert CanaryCleanupRecord(
        artifacts=exact.artifacts + (("schema", True, True),)
    ).all_removed is False
    assert CanaryCleanupRecord(
        artifacts=exact.artifacts[:-1] + (("unknown", True, True),)
    ).all_removed is False


def test_run_canary_unexpected_origin_error_removes_owned_attempt_root(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    scratch = tmp_path / "scratch-unexpected-origin"
    scratch.mkdir()

    def _unexpected_origin(**_kwargs):
        raise RuntimeError("synthetic unexpected origin failure")

    monkeypatch.setattr(
        canary_module, "create_ephemeral_archive_origin", _unexpected_origin
    )
    with pytest.raises(RuntimeError, match="synthetic unexpected origin failure"):
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-unexpected-origin",
            protected_join="c" * 40,
            client_factory=_canary_client_factory(),
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert not (scratch / "cap-s1-attempt-root").exists()
    _assert_scratch_has_no_leaked_resources(scratch)


def test_run_canary_schema_attestation_failure_leaves_scratch_clean(tmp_path) -> None:
    scratch = tmp_path / "scratch-cleanup-boundary-schema"
    scratch.mkdir()
    factory = _canary_client_factory()

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-cleanup-boundary-schema",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_failing_schema_run_command,
        )
    assert excinfo.value.code == "SKILL_PROTOCOL_SCHEMA_UNATTESTED"
    _assert_scratch_has_no_leaked_resources(scratch)


def test_run_canary_ambient_refusal_at_launch_leaves_scratch_clean(tmp_path) -> None:
    scratch = tmp_path / "scratch-cleanup-boundary-ambient"
    scratch.mkdir()
    workspace_cwd = str((scratch / "synthetic-workspace").resolve())
    script = [
        _strict_skills_list_result(workspace_cwd, []),
        _strict_skills_list_result(
            workspace_cwd,
            [_skill_row("rogue-skill", path="/fake-ambient-skills/rogue-skill/SKILL.md")],
        ),
    ]
    factory = _canary_client_factory(skills_list_script=script)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-cleanup-boundary-ambient",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "AMBIENT_SKILL_SURFACE_NOT_EMPTY"
    # The adapter's own ``_start_process`` already closed the client
    # internally on this exact failure boundary (before our own "process"
    # cleanup action would ever be registered) -- the process is still dead.
    assert _CREATED_CANARY_CLIENTS[0].alive() is False
    _assert_scratch_has_no_leaked_resources(scratch)


def test_run_canary_mid_turn_effect_unknown_tears_down_process_exactly_once_and_cleans_scratch(
    tmp_path, monkeypatch
) -> None:
    scratch = tmp_path / "scratch-cleanup-boundary-effect-unknown"
    scratch.mkdir()
    call_count = {"n": 0}
    real_graceful_close = AppServerClient.graceful_close

    def _counting_graceful_close(self, *, wait: float = 5.0):
        call_count["n"] += 1
        return real_graceful_close(self, wait=wait)

    monkeypatch.setattr(AppServerClient, "graceful_close", _counting_graceful_close)

    factory = _canary_client_factory(fail_turn_start_at=1)

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-cleanup-boundary-effect-unknown",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "EFFECT_UNKNOWN"
    # Attempted exactly once, never retried -- the process stop surface is
    # invoked by the finally-block cleanup ledger regardless of the
    # mid-turn transport failure's own uncertainty.
    assert call_count["n"] == 1
    assert _CREATED_CANARY_CLIENTS[0].alive() is False
    _assert_scratch_has_no_leaked_resources(scratch)


def test_run_canary_marker_noncompliant_journey_still_cleans_up_everything(tmp_path) -> None:
    """A non-raising, marker-noncompliant journey (a false marker recorded,
    never an exception) is not exempt from the SAME cleanup discipline as
    every raising failure boundary above."""

    scratch = tmp_path / "scratch-cleanup-boundary-marker"
    scratch.mkdir()
    non_compliant_replies = [
        _HAPPY_REPLIES[0],
        "PROGRESS COMPLETE synthetic operation is already done.",  # forbidden COMPLETE
        _HAPPY_REPLIES[2],
        _HAPPY_REPLIES[3],
    ]
    factory = _canary_client_factory(replies=non_compliant_replies)

    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-canary-cleanup-boundary-marker",
        protected_join="c" * 40,
        client_factory=factory,
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )
    assert evidence.turn_marker_results[1] == ("return-progress", False)
    assert evidence.cleanup.all_removed is True
    _assert_scratch_has_no_leaked_resources(scratch)


def test_run_canary_post_clear_drift_refusal_still_cleans_up_everything(tmp_path) -> None:
    """"Post-turn drift refusal": the provider's skill surface fails to
    actually clear after the runner's own ``extraRoots/set []`` -- the
    causal-sequence law this maps to (``SKILL_SET_CAUSALITY_FAILED``) must
    still leave scratch fully torn down, exactly like every earlier
    boundary."""

    scratch = tmp_path / "scratch-cleanup-boundary-post-clear"
    scratch.mkdir()
    factory = _canary_client_factory(
        replies=list(_HAPPY_REPLIES), force_post_clear_nonempty=True
    )

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-cleanup-boundary-post-clear",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "SKILL_SET_CAUSALITY_FAILED"
    assert "post-clear" in str(excinfo.value)
    assert _CREATED_CANARY_CLIENTS[0].alive() is False
    _assert_scratch_has_no_leaked_resources(scratch)


# ---------------------------------------------------------------------------
# cleanup honesty
# ---------------------------------------------------------------------------


def test_run_canary_reports_cleanup_failure_honestly(tmp_path, monkeypatch) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses permission checks; cannot force an undeletable directory")

    scratch = tmp_path / "scratch-cleanup-honesty"
    scratch.mkdir()
    attempt_root = scratch / "cap-s1-attempt-root"

    def _lock_attempt_root() -> None:
        # Staging (stage_skill_projection) has already completed by the time
        # the client is constructed -- client_factory is invoked from
        # start_session, well after the projection is staged -- so locking
        # here cannot prevent staging, only the later cleanup rmdir.
        os.chmod(attempt_root, 0o555)

    factory = _canary_client_factory(replies=list(_HAPPY_REPLIES), on_create=_lock_attempt_root)

    try:
        evidence = run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-cleanup-honesty",
            protected_join="c" * 40,
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    finally:
        if attempt_root.exists():
            os.chmod(attempt_root, 0o700)

    cleanup_map = _cleanup_map(evidence.cleanup)
    assert cleanup_map["projection"] == (False, False)
    assert cleanup_map["schema"] == (True, True)
    assert cleanup_map["workspace"] == (True, True)
    assert cleanup_map["origin"] == (True, True)
    assert cleanup_map["attempt"] == (True, True)
    assert cleanup_map["thread"] == (True, True)
    assert evidence.cleanup.all_removed is False

    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(canary_module, "run_canary", lambda **_kwargs: evidence)
    exit_code = canary_module.main(
        [
            "--backend",
            "fake",
            "--scratch",
            str(tmp_path / "cli-scratch-cleanup-honesty"),
            "--operation-id",
            "cap-s1-canary-cleanup-honesty-cli",
            "--protected-join",
            "c" * 40,
        ]
    )
    assert exit_code != 0

    shutil.rmtree(attempt_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_main_prints_evidence_json_and_exits_zero_on_a_clean_journey(
    tmp_path, monkeypatch, capsys
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    clean_evidence = CanaryEvidence(
        candidate_commit="a" * 40,
        candidate_tree="b" * 40,
        canary_operation_id="cap-s1-cli-smoke",
        provider_attempt_id="cap-s1-cli-smoke-attempt",
        protected_join="c" * 40,
        workspace_root=str(tmp_path / "workspace"),
        process_generation="cap-s1-cli-smoke-gen1",
        v4_policy_digest="c" * 64,
        package_source_digest="d" * 64,
        package_generation_digest="e" * 64,
        skill_grant_digests=(("cap.a", "f" * 64),),
        skill_closure_digests=(("cap.a", "0" * 64),),
        projection_receipt_digest="1" * 64,
        binary_digest="4" * 64,
        binary_version=FAKE_HARNESS_VERSION,
        origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
        origin_authentication=ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE,
        skills_root="/fixture/skills",
        app_server_config_digest="2" * 64,
        extra_roots_set_outcomes=("cleared",),
        skills_list_raw_shape_digest="3" * 64,
        baseline_enabled_names=("receive-commission",),
        after_add_enabled_names=("receive-commission",),
        observed_enabled_names=("receive-commission",),
        after_clear_enabled_names=(),
        protocol_receipt_digest="5" * 64,
        launch_decision="ALLOW",
        turn_marker_results=(
            ("receive-commission", True),
            ("return-progress", True),
            ("escalate-decision", True),
            ("finish-operation", True),
        ),
        served_model="gpt-5.6-sol",
        terminal_process_state="PROVEN_DEAD",
        artifact_inventory=("workspace:README.md",),
        cleanup=CanaryCleanupRecord(
            artifacts=(
                ("schema", True, True),
                ("workspace", True, True),
                ("attempt", True, True),
                ("origin", True, True),
                ("projection", True, True),
                ("thread", True, True),
                ("process", True, True),
            )
        ),
    )
    monkeypatch.setattr(canary_module, "run_canary", lambda **_kwargs: clean_evidence)

    exit_code = canary_module.main(
        [
            "--backend",
            "fake",
            "--scratch",
            str(tmp_path / "cli-scratch"),
            "--operation-id",
            "cap-s1-cli-smoke",
            "--protected-join",
            "c" * 40,
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    printed = json.loads(captured.out)
    assert printed["launch_decision"] == "ALLOW"
    assert printed["canary_operation_id"] == "cap-s1-cli-smoke"


def test_cli_main_exits_nonzero_when_a_marker_is_false_or_cleanup_failed(
    tmp_path, monkeypatch, capsys
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    dirty_evidence = CanaryEvidence(
        candidate_commit="a" * 40,
        candidate_tree="b" * 40,
        canary_operation_id="cap-s1-cli-smoke-2",
        provider_attempt_id="cap-s1-cli-smoke-2-attempt",
        protected_join="c" * 40,
        workspace_root=str(tmp_path / "workspace2"),
        process_generation="cap-s1-cli-smoke-2-gen1",
        v4_policy_digest="c" * 64,
        package_source_digest="d" * 64,
        package_generation_digest="e" * 64,
        skill_grant_digests=(("cap.a", "f" * 64),),
        skill_closure_digests=(("cap.a", "0" * 64),),
        projection_receipt_digest="1" * 64,
        binary_digest="4" * 64,
        binary_version=FAKE_HARNESS_VERSION,
        origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
        origin_authentication=ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE,
        skills_root="/fixture/skills",
        app_server_config_digest="2" * 64,
        extra_roots_set_outcomes=("cleared",),
        skills_list_raw_shape_digest="3" * 64,
        baseline_enabled_names=("receive-commission",),
        after_add_enabled_names=("receive-commission",),
        observed_enabled_names=("receive-commission",),
        after_clear_enabled_names=(),
        protocol_receipt_digest="5" * 64,
        launch_decision="ALLOW",
        turn_marker_results=(
            ("receive-commission", True),
            ("return-progress", False),
            ("escalate-decision", True),
            ("finish-operation", True),
        ),
        served_model="gpt-5.6-sol",
        terminal_process_state="PROVEN_DEAD",
        artifact_inventory=(),
        cleanup=CanaryCleanupRecord(
            artifacts=(
                ("schema", True, True),
                ("workspace", True, True),
                ("attempt", True, True),
                ("origin", True, True),
                ("projection", True, True),
                ("thread", True, True),
                ("process", True, True),
            )
        ),
    )
    monkeypatch.setattr(canary_module, "run_canary", lambda **_kwargs: dirty_evidence)

    exit_code = canary_module.main(
        [
            "--backend",
            "fake",
            "--scratch",
            str(tmp_path / "cli-scratch-2"),
            "--operation-id",
            "cap-s1-cli-smoke-2",
            "--protected-join",
            "c" * 40,
        ]
    )
    assert exit_code != 0


def test_cli_main_prints_stop_code_and_exits_nonzero_on_canary_stop(
    tmp_path, monkeypatch, capsys
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    def _raise_stop(**_kwargs):
        raise CanaryStop("AMBIENT_SKILL_SURFACE_NOT_EMPTY", "synthetic")

    monkeypatch.setattr(canary_module, "run_canary", _raise_stop)

    exit_code = canary_module.main(
        [
            "--backend",
            "fake",
            "--scratch",
            str(tmp_path / "cli-scratch-3"),
            "--operation-id",
            "cap-s1-cli-smoke-3",
            "--protected-join",
            "c" * 40,
        ]
    )
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "AMBIENT_SKILL_SURFACE_NOT_EMPTY" in captured.out


# ---------------------------------------------------------------------------
# Closed evidence contract (Sol wave-3 review finding B5)
# ---------------------------------------------------------------------------


def test_canary_evidence_schema_pins_version_and_full_field_set() -> None:
    fields = dataclasses.fields(CanaryEvidence)
    assert fields[0].name == "schema_version"
    assert fields[0].default == "mastermind.cap_s1_canary_evidence/v1"
    field_names = {f.name for f in fields}
    assert field_names == {
        "schema_version",
        "candidate_commit",
        "candidate_tree",
        "canary_operation_id",
        "provider_attempt_id",
        "protected_join",
        "workspace_root",
        "process_generation",
        "v4_policy_digest",
        "package_source_digest",
        "package_generation_digest",
        "skill_grant_digests",
        "skill_closure_digests",
        "projection_receipt_digest",
        "binary_digest",
        "binary_version",
        "origin_mode",
        "origin_authentication",
        "skills_root",
        "app_server_config_digest",
        "extra_roots_set_outcomes",
        "skills_list_raw_shape_digest",
        "baseline_enabled_names",
        "after_add_enabled_names",
        "observed_enabled_names",
        "after_clear_enabled_names",
        "protocol_receipt_digest",
        "launch_decision",
        "turn_marker_results",
        "served_model",
        "terminal_process_state",
        "artifact_inventory",
        "cleanup",
    }


def test_canary_cleanup_record_schema_and_fields() -> None:
    fields = dataclasses.fields(CanaryCleanupRecord)
    field_names = {f.name for f in fields}
    assert field_names == {"schema_version", "artifacts"}
    assert CanaryCleanupRecord().schema_version == "mastermind.cap_s1_canary_cleanup/v1"
    assert CanaryCleanupRecord().artifacts == ()
    assert CanaryCleanupRecord().all_removed is False
    assert CanaryCleanupRecord(artifacts=(("schema", True, False),)).all_removed is False


def test_turn_markers_use_a_closed_standalone_word_grammar() -> None:
    from scripts.ohf.cap_s1_mastermind_operator_canary import _turn_markers_satisfied

    # A bare substring occurrence inside a longer word must never satisfy a
    # required token.
    assert (
        _turn_markers_satisfied("finish-operation", "Still RESULTING, nothing else final.")
        is False
    )
    # ... but the standalone token itself still satisfies it.
    assert _turn_markers_satisfied("finish-operation", "RESULT: final output recorded.") is True
    # A bare substring occurrence inside a longer word must never trip a
    # forbidden token either.
    assert (
        _turn_markers_satisfied("return-progress", "PROGRESS: task is COMPLETED already.")
        is True
    )
    # ... but the standalone forbidden token still refuses it.
    assert (
        _turn_markers_satisfied("return-progress", "PROGRESS: task is COMPLETE now.") is False
    )


# ---------------------------------------------------------------------------
# CAP-S1 addendum: executable CLI backends (5087373998)
# ---------------------------------------------------------------------------


def test_cli_main_fake_backend_completes_the_real_four_turn_journey_as_a_subprocess(
    tmp_path,
) -> None:
    """Neither committed CLI backend ran end to end before this commission
    (addendum finding 2): the fake fixture schema "binary" was print-only
    and wrote no files, so ``--backend fake`` always stopped at
    ``SKILL_PROTOCOL_SCHEMA_UNATTESTED`` the moment ``main`` was actually
    invoked as a real subprocess (never overriding ``run_command``). This
    drives the REAL ``python -m scripts.ohf.cap_s1_mastermind_operator_canary``
    entry point end to end -- real schema-fixture generation, a real
    ephemeral git archive origin, a real synthetic-workspace git commit, and
    a real ``python -m scripts.ohf.fake_app_server`` subprocess -- and
    parses its printed JSON evidence.
    """

    scratch = tmp_path / "cli-e2e-scratch"
    result = _subprocess.run(
        [
            _sys.executable,
            "-m",
            "scripts.ohf.cap_s1_mastermind_operator_canary",
            "--backend",
            "fake",
            "--scratch",
            str(scratch),
            "--operation-id",
            "cap-s1-cli-e2e-fake",
            "--protected-join",
            "c" * 40,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "mastermind.cap_s1_canary_evidence/v1"
    assert payload["protected_join"] == "c" * 40
    assert payload["launch_decision"] == "ALLOW"
    assert [ok for _name, ok in payload["turn_marker_results"]] == [True, True, True, True]
    artifacts = payload["cleanup"]["artifacts"]
    assert {row[0] for row in artifacts} == {
        "schema",
        "workspace",
        "origin",
        "projection",
        "attempt",
        "thread",
        "process",
    }
    assert all(row[1] and row[2] for row in artifacts)


def test_cli_main_requires_protected_join_before_creating_scratch(tmp_path) -> None:
    scratch = tmp_path / "cli-missing-protected-join"
    result = _subprocess.run(
        [
            _sys.executable,
            "-m",
            "scripts.ohf.cap_s1_mastermind_operator_canary",
            "--backend",
            "fake",
            "--scratch",
            str(scratch),
            "--operation-id",
            "cap-s1-cli-missing-protected-join",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert not scratch.exists()


@pytest.mark.parametrize(
    "protected_join",
    ("", "c" * 39, "g" * 40, "C" * 40),
)
def test_run_canary_refuses_unattested_protected_join_before_first_effect(
    tmp_path, protected_join
) -> None:
    scratch = tmp_path / "invalid-protected-join"

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-invalid-protected-join",
            protected_join=protected_join,
            client_factory=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("client factory must not run")
            ),
            run_command=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("schema command must not run")
            ),
        )

    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert excinfo.value.detail == "protected source join is not attested"
    assert not scratch.exists()


def test_cli_main_live_backend_seam_probe_reaches_client_construction_and_refuses(
    tmp_path,
) -> None:
    """Addendum finding 3: the live CLI backend's client-factory wiring is
    proven end to end -- reaching real ``CodexOperatorAdapter`` client
    construction with the exact real schema/workspace/origin/projection
    machinery -- via an explicit ``CAP_S1_LIVE_CLIENT_FACTORY`` override
    pointed at ``_seam_probe_client_factory``, a non-network double that
    records construction was reached then raises a deterministic refusal.
    No provider or network effect occurs anywhere in this test.
    """

    fixture_binary = tmp_path / "fixture-live-binary"
    fixture_binary.write_text(_SCHEMA_FIXTURE_BINARY_SOURCE, encoding="utf-8")
    fixture_binary.chmod(0o755)

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    codex_home.chmod(0o700)
    auth_path = codex_home / "auth.json"
    auth_path.write_text("fixture credential bytes", encoding="utf-8")
    auth_path.chmod(0o600)

    scratch = tmp_path / "scratch-live-seam"
    record_path = tmp_path / "seam-probe-record.json"

    env = dict(os.environ)
    env["CAP_S1_LIVE_CLIENT_FACTORY"] = (
        "scripts.ohf.cap_s1_mastermind_operator_canary:_seam_probe_client_factory"
    )
    env["OHF_SEAM_PROBE_RECORD_PATH"] = str(record_path)

    result = _subprocess.run(
        [
            _sys.executable,
            "-m",
            "scripts.ohf.cap_s1_mastermind_operator_canary",
            "--backend",
            "live",
            "--binary-path",
            str(fixture_binary),
            "--codex-home",
            str(codex_home),
            "--scratch",
            str(scratch),
            "--operation-id",
            "cap-s1-cli-e2e-live-seam",
            "--protected-join",
            "c" * 40,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "CANARY_STOP:" in result.stdout
    assert record_path.is_file(), result.stdout + result.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    # CAP-S1 Sol review item 2 residual: the seam probe must construct the
    # REAL AppServerClient class -- not a callback-only substitute -- and
    # genuinely spawn a process through it.
    assert record["constructed"] == "AppServerClient", record
    assert record["argv"], record
    assert Path(record["argv"][0]) == fixture_binary.resolve()
    assert record["argv0"] == str(fixture_binary.resolve())
    assert record["cwd"]
    assert record["pid"]


# ---------------------------------------------------------------------------
# No real binary anywhere in this module
# ---------------------------------------------------------------------------


def test_this_test_module_never_references_the_real_codex_binary_as_an_executable_target() -> None:
    """Defense in depth: this file never spells out a real installed Codex
    binary path anywhere -- every live-backend test above targets a
    ``/nonexistent/synthetic-codex-binary`` path so ``PROVIDER_REALM_
    UNAVAILABLE`` is proven without naming a real one -- and every
    ``client_factory``/``run_command`` fake used in this module (exercised
    by every other test above) launches only ``sys.executable -m
    scripts.ohf.fake_app_server`` or writes bounded fixture bytes, guarded
    at call time by ``_asserts_never_the_real_codex_binary``.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    # A literal, real installed Codex path would end with the two path
    # segments checked below; this file's only other "codex" mentions are
    # module/symbol names or the synthetic nonexistent-binary fixture path.
    forbidden_suffix = "/".join(("bin", "codex"))
    assert forbidden_suffix not in source
    assert "/nonexistent/synthetic-codex-binary" in source
    assert "scripts.ohf.fake_app_server" in source
    assert _sys.executable  # sanity: fake backend always launches this interpreter


# ---------------------------------------------------------------------------
# Closed CAP-S1 result contract (CAP-S1 Sol review item 5)
# ---------------------------------------------------------------------------


_CAP_S1_PRODUCER_EVIDENCE_DIR: Path | None = None
_CAP_S1_PRODUCER_EVIDENCE_COUNTER = 0


def _happy_cap_s1_result_kwargs() -> dict:
    global _CAP_S1_PRODUCER_EVIDENCE_COUNTER
    exact_head = "a" * 40
    exact_tree = "b" * 40
    protected_join = "c" * 40
    attempt_id = "cap-s1-provider-attempt-001"
    bound = {
        "exact_head": exact_head,
        "exact_tree": exact_tree,
        "protected_join": protected_join,
        "provider_attempt_id": attempt_id,
    }
    local_scopes = tuple(sorted(CAP_S1_OBSERVER_TEST_MODULES))
    local_manifest = tuple(
        (
            scope,
            1,
            2 if index == len(local_scopes) - 1 else 0,
            0,
            0,
        )
        for index, scope in enumerate(local_scopes)
    )
    raw = dict(
        operation="mastermind-cap-s1-complete-vertical-20260901-sol-001",
        receiver="fable-cap-s1",
        carrier="C0BSBM78V1N/1788258398.440699",
        exact_head=exact_head,
        exact_tree=exact_tree,
        current_protected_join=protected_join,
        release_state=RESULT_RELEASE_STATE,
        changed_path_census=(
            "control_plane/chairman_control_room_remote.py",
            "control_plane/codex_operator_adapter.py",
            "control_plane/executive_agent_capabilities.py",
            "control_plane/executive_capability_packages.py",
            "control_plane/operator_harness_contract.py",
            "docs/superpowers/plans/2026-09-01-sol-capability-fabric-cap-s1.md",
            "ops/control_room_remote/install.sh",
            "scripts/ohf/cap_s1_mastermind_operator_canary.py",
            "scripts/ohf/capability_skill_projection.py",
            "scripts/ohf/fake_app_server.py",
            "scripts/ohf/fake_codex_binary.py",
            "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
            "scripts/ohf/protocol.py",
            "tests/test_cap_s1_mastermind_operator_canary.py",
            "tests/test_codex_operator_adapter.py",
            "tests/test_control_room_remote_install.py",
            "tests/test_executive_agent_capabilities.py",
            "tests/test_executive_agent_capabilities_v4.py",
            "tests/test_executive_capability_packages.py",
            "tests/test_ohf_p1a_operator_harness_contract.py",
            "tests/test_ohf_protocol_fidelity.py",
        ),
        package_identities={
            "exact_head": exact_head,
            "exact_tree": exact_tree,
            "package_content_digest": "1" * 64,
            "package_source_digest": "2" * 64,
            "package_generation_digest": "3" * 64,
            "closures": {
                "skill.a": "4" * 64,
                "skill.b": "5" * 64,
                "skill.c": "c" * 64,
                "skill.d": "d" * 64,
            },
        },
        canary_evidence=None,
        provider_attempt={
            "state": "HOLD",
            "attempt_id": attempt_id,
            "attempt_operation": "historical-cap-s1-provider-attempt",
            "candidate_head": "d" * 40,
            "candidate_tree": "e" * 40,
            "disposition": "CONSUMED_NOT_ACCEPTED_NO_REPLAY_NO_FAILOVER",
            "hold_code": "GATES_NOT_GREEN",
        },
        local_proof={
            **bound,
            "suite_count": len(local_manifest),
            "total": len(local_manifest) + 2,
            "passed": len(local_manifest),
            "skipped": 2,
            "failed": 0,
            "cancelled": 0,
            "suite_manifest": local_manifest,
            "evidence_digest": "6" * 64,
        },
        hosted_proof={
            **bound,
            "run_id": "33741521536",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "jobs_total": 1,
            "jobs_passed": 1,
            "jobs_failed": 0,
            "jobs_cancelled": 0,
            "job_manifest": (
                ("100000000001", "test", "COMPLETED", "SUCCESS"),
            ),
            "evidence_digest": "7" * 64,
        },
        security_proof={
            **bound,
            "status": "CLEAN",
            "tool_count": 3,
            "findings": 0,
            "failures": 0,
            "cancelled": 0,
            "tool_manifest": tuple(
                (name, "PASSED", 0, _canonical_digest({"tool": name}))
                for name in ("codeql", "diff", "secret-scan")
            ),
            "evidence_digest": "8" * 64,
        },
        mutation_proof={
            **bound,
            "status": "PASSED",
            "total": 12,
            "killed": 12,
            "survived": 0,
            "skipped": 0,
            "errors": 0,
            "cancelled": 0,
            "mutation_manifest": tuple(
                (
                    f"mutation-{index:02d}",
                    "KILLED",
                    _canonical_digest({"mutation": index, "outcome": "KILLED"}),
                )
                for index in range(12)
            ),
            "evidence_digest": "9" * 64,
        },
        cleanup_proof={
            **bound,
            "status": "CLEAN",
            "all_removed": True,
            "resources_total": len(_RESULT_ALL_CLEANUP_KINDS),
            "failures": 0,
            "residue_count": 0,
            "resource_kinds": _RESULT_ALL_CLEANUP_KINDS,
            "resource_manifest": tuple(
                (kind, _canonical_digest({"owned_resource": kind}), True, True)
                for kind in _RESULT_ALL_CLEANUP_KINDS
            ),
            "evidence_digest": "a" * 64,
        },
        review_state={
            **bound,
            "author": "chriswong6031-creator",
            "author_id": 101,
            "reviewer": "mastermindx-3",
            "reviewer_id": 303,
            "review_id": "5104652791",
            "state": "APPROVED",
            "review_commit": exact_head,
            "evidence_digest": "b" * 64,
        },
        held_non_goals=(
            "NO_CAP_PROMOTE1",
            "NO_DEFAULT_V4_PROMOTION",
            "NO_MAT_S1_RUNTIMEBINDING_WAKE",
            "NO_READY_OR_MERGE",
            "PRODUCTION_UNARMED",
        ),
    )
    receipt_types = {
        "local_proof": "CapS1LocalProofReceipt",
        "hosted_proof": "CapS1HostedProofReceipt",
        "security_proof": "CapS1SecurityProofReceipt",
        "mutation_proof": "CapS1MutationProofReceipt",
        "cleanup_proof": "CapS1CleanupProofReceipt",
        "review_state": "CapS1ReviewReceipt",
    }
    for field_name, receipt_type in receipt_types.items():
        observation = dict(raw[field_name])
        observation.pop("evidence_digest")
        raw[field_name]["evidence_digest"] = _canonical_digest(
            {"receipt_type": receipt_type, "observation": observation}
        )
    assert _CAP_S1_PRODUCER_EVIDENCE_DIR is not None
    producer_payload = {
        "schema_version": "mastermind.cap_s1_producer_evidence/v1",
        "exact_head": exact_head,
        "exact_tree": exact_tree,
        "protected_join": protected_join,
        "provider_attempt_id": attempt_id,
        "local_suites": [
            {
                "suite_id": suite_id,
                "passed": passed,
                "skipped": skipped,
                "failed": failed,
                "cancelled": cancelled,
            }
            for suite_id, passed, skipped, failed, cancelled in raw["local_proof"][
                "suite_manifest"
            ]
        ],
        "security_tools": [
            {
                "tool_id": tool_id,
                "status": status,
                "findings": findings,
                "evidence": {"tool": tool_id},
            }
            for tool_id, status, findings, _digest in raw["security_proof"][
                "tool_manifest"
            ]
        ],
        "mutations": [
            {
                "mutation_id": mutation_id,
                "state": state,
                "evidence": {
                    "mutation": int(mutation_id.removeprefix("mutation-")),
                    "outcome": state,
                },
            }
            for mutation_id, state, _digest in raw["mutation_proof"][
                "mutation_manifest"
            ]
        ],
        "cleanup_resources": [
            {
                "kind": kind,
                "identity": {"owned_resource": kind},
                "removed": removed,
                "verified_absent": verified_absent,
            }
            for kind, _digest, removed, verified_absent in raw["cleanup_proof"][
                "resource_manifest"
            ]
        ],
    }
    producer_path = (
        _CAP_S1_PRODUCER_EVIDENCE_DIR
        / f"cap-s1-producer-{_CAP_S1_PRODUCER_EVIDENCE_COUNTER}.json"
    )
    _CAP_S1_PRODUCER_EVIDENCE_COUNTER += 1
    producer_path.write_text(
        json.dumps(producer_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    producer_path.chmod(0o444)
    raw["producer_evidence_path"] = producer_path
    return raw


def _refresh_result_receipt_digest(raw: dict, field_name: str, receipt_type: str) -> None:
    observation = dict(raw[field_name])
    observation.pop("evidence_digest")
    raw[field_name]["evidence_digest"] = _canonical_digest(
        {"receipt_type": receipt_type, "observation": observation}
    )


def test_build_cap_s1_result_happy_path_round_trips_through_json() -> None:
    raw = _happy_cap_s1_result_kwargs()
    result = build_cap_s1_result(**raw)
    assert result.schema_version == RESULT_CONTRACT_SCHEMA
    assert result.marker == RESULT_CONTRACT_MARKER
    validate_cap_s1_result(
        result, producer_evidence_path=raw["producer_evidence_path"]
    )  # never raises on an already-built result with the same producer artifact
    payload = dataclasses.asdict(result)
    reloaded = json.loads(json.dumps(payload))
    assert reloaded["schema_version"] == RESULT_CONTRACT_SCHEMA
    assert reloaded["marker"] == RESULT_CONTRACT_MARKER


def test_cap_s1_result_schema_and_marker_are_exact() -> None:
    kwargs = _happy_cap_s1_result_kwargs()
    result = build_cap_s1_result(**kwargs)
    with pytest.raises(CapS1ResultError, match="schema_mismatch"):
        validate_cap_s1_result(
            dataclasses.replace(result, schema_version="wrong/v1"),
            producer_evidence_path=kwargs["producer_evidence_path"],
        )
    with pytest.raises(CapS1ResultError, match="marker_mismatch"):
        validate_cap_s1_result(
            dataclasses.replace(result, marker="wrong-marker"),
            producer_evidence_path=kwargs["producer_evidence_path"],
        )


def test_cap_s1_result_hex_fields_are_fullmatched() -> None:
    for field_name in ("exact_head", "exact_tree", "current_protected_join"):
        kwargs = _happy_cap_s1_result_kwargs()
        kwargs[field_name] = "not-40-hex"
        with pytest.raises(CapS1ResultError, match=f"{field_name}_invalid"):
            build_cap_s1_result(**kwargs)
        kwargs2 = _happy_cap_s1_result_kwargs()
        kwargs2[field_name] = "a" * 41  # one char too many
        with pytest.raises(CapS1ResultError, match=f"{field_name}_invalid"):
            build_cap_s1_result(**kwargs2)


def test_cap_s1_result_changed_path_census_must_be_nonempty_sorted_and_unique() -> None:
    empty = _happy_cap_s1_result_kwargs()
    empty["changed_path_census"] = ()
    with pytest.raises(CapS1ResultError, match="changed_path_census_empty"):
        build_cap_s1_result(**empty)

    unsorted = _happy_cap_s1_result_kwargs()
    unsorted["changed_path_census"] = ("z.py", "a.py")
    with pytest.raises(CapS1ResultError, match="changed_path_census_unsorted"):
        build_cap_s1_result(**unsorted)

    duplicated = _happy_cap_s1_result_kwargs()
    duplicated["changed_path_census"] = ("a.py", "a.py")
    with pytest.raises(CapS1ResultError, match="changed_path_census_duplicate"):
        build_cap_s1_result(**duplicated)


def test_cap_s1_result_package_identities_must_be_nonempty_and_all_hex64() -> None:
    empty = _happy_cap_s1_result_kwargs()
    empty["package_identities"] = {}
    with pytest.raises(CapS1ResultError, match="package_identities_invalid"):
        build_cap_s1_result(**empty)

    bad_leaf = _happy_cap_s1_result_kwargs()
    bad_leaf["package_identities"]["package_content_digest"] = "not-a-digest"
    with pytest.raises(CapS1ResultError, match="package_identities_digest_invalid"):
        build_cap_s1_result(**bad_leaf)

    nested_bad_leaf = _happy_cap_s1_result_kwargs()
    nested_bad_leaf["package_identities"]["closures"]["skill.a"] = "short"
    with pytest.raises(CapS1ResultError, match="package_identities_digest_invalid"):
        build_cap_s1_result(**nested_bad_leaf)

    raw = _happy_cap_s1_result_kwargs()
    typed = build_cap_s1_result(**raw)
    wrong_closure_count = dataclasses.replace(
        typed,
        package_identities=dataclasses.replace(
            typed.package_identities,
            closures=typed.package_identities.closures[:-1],
        ),
    )
    with pytest.raises(CapS1ResultError, match="package_identities_invalid"):
        validate_cap_s1_result(
            wrong_closure_count,
            producer_evidence_path=raw["producer_evidence_path"],
        )


def test_cap_s1_result_provider_attempt_state_is_closed() -> None:
    bad_state = _happy_cap_s1_result_kwargs()
    bad_state["provider_attempt"] = {"state": "RUNNING"}
    with pytest.raises(CapS1ResultError, match="provider_attempt_state_invalid"):
        build_cap_s1_result(**bad_state)


def test_cap_s1_result_hold_requires_frozen_hold_code_detail_and_empty_evidence() -> None:
    hold_kwargs = _happy_cap_s1_result_kwargs()
    build_cap_s1_result(**hold_kwargs)  # a well-formed HOLD constructs cleanly

    unknown_code = dict(hold_kwargs)
    unknown_code["provider_attempt"] = dict(hold_kwargs["provider_attempt"])
    unknown_code["provider_attempt"]["hold_code"] = "NOT_A_FROZEN_CODE"
    with pytest.raises(CapS1ResultError, match="provider_attempt_hold_code_invalid"):
        build_cap_s1_result(**unknown_code)

    wrong_disposition = dict(hold_kwargs)
    wrong_disposition["provider_attempt"] = dict(hold_kwargs["provider_attempt"])
    wrong_disposition["provider_attempt"]["disposition"] = "ACCEPTED"
    with pytest.raises(CapS1ResultError, match="provider_attempt_disposition_invalid"):
        build_cap_s1_result(**wrong_disposition)

    evidence_on_hold = dict(hold_kwargs)
    evidence_on_hold["canary_evidence"] = {"schema_version": CANARY_EVIDENCE_SCHEMA_VERSION}
    with pytest.raises(CapS1ResultError, match="canary_evidence_must_be_empty_on_hold"):
        build_cap_s1_result(**evidence_on_hold)


def test_cap_s1_result_completed_requires_nonempty_matching_canary_evidence() -> None:
    empty_evidence = _happy_cap_s1_result_kwargs()
    empty_evidence["provider_attempt"] = {
        key: value
        for key, value in empty_evidence["provider_attempt"].items()
        if key != "hold_code"
    }
    empty_evidence["provider_attempt"].update(state="COMPLETED", disposition="ACCEPTED")
    with pytest.raises(CapS1ResultError, match="canary_evidence_required_on_completed"):
        build_cap_s1_result(**empty_evidence)

    schema_token_only = dict(empty_evidence)
    schema_token_only["canary_evidence"] = {"schema_version": CANARY_EVIDENCE_SCHEMA_VERSION}
    with pytest.raises(CapS1ResultError, match="canary_evidence_type_invalid"):
        build_cap_s1_result(**schema_token_only)


def _completed_canary_evidence(
    *, head: str, tree: str, attempt_id: str, protected_join: str
) -> CanaryEvidence:
    skill_rows = (
        ("escalate-decision", "1" * 64),
        ("finish-operation", "2" * 64),
        ("receive-commission", "3" * 64),
        ("return-progress", "4" * 64),
    )
    return CanaryEvidence(
        candidate_commit=head,
        candidate_tree=tree,
        canary_operation_id="cap-s1-completed-canary",
        provider_attempt_id=attempt_id,
        protected_join=protected_join,
        workspace_root="/tmp/cap-s1-workspace",
        process_generation="cap-s1-generation-1",
        v4_policy_digest="5" * 64,
        package_source_digest="6" * 64,
        package_generation_digest="7" * 64,
        skill_grant_digests=skill_rows,
        skill_closure_digests=skill_rows,
        projection_receipt_digest="8" * 64,
        binary_digest="9" * 64,
        binary_version="codex-fixture",
        origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
        origin_authentication=ORIGIN_AUTHENTICATION_EPHEMERAL_GIT_ARCHIVE,
        skills_root="/tmp/cap-s1-skills",
        app_server_config_digest="a" * 64,
        extra_roots_set_outcomes=("cleared",),
        skills_list_raw_shape_digest="b" * 64,
        baseline_enabled_names=tuple(name for name, _digest in skill_rows),
        after_add_enabled_names=tuple(name for name, _digest in skill_rows),
        observed_enabled_names=tuple(name for name, _digest in skill_rows),
        after_clear_enabled_names=(),
        protocol_receipt_digest="c" * 64,
        launch_decision="ALLOW",
        turn_marker_results=(
            ("receive-commission", True),
            ("return-progress", True),
            ("escalate-decision", True),
            ("finish-operation", True),
        ),
        served_model="gpt-5.6-sol",
        terminal_process_state="PROVEN_DEAD",
        artifact_inventory=("workspace:README.md",),
        cleanup=CanaryCleanupRecord(
            artifacts=(
                ("process", True, True),
                ("thread", True, True),
                ("projection", True, True),
                ("origin", True, True),
                ("attempt", True, True),
                ("workspace", True, True),
                ("schema", True, True),
            )
        ),
    )


def test_cap_s1_result_completed_accepts_only_fully_bound_typed_canary_evidence() -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["provider_attempt"] = {
        key: value for key, value in raw["provider_attempt"].items() if key != "hold_code"
    }
    raw["provider_attempt"].update(
        state="COMPLETED",
        disposition="ACCEPTED",
        candidate_head=raw["exact_head"],
        candidate_tree=raw["exact_tree"],
    )
    raw["canary_evidence"] = _completed_canary_evidence(
        head=raw["exact_head"],
        tree=raw["exact_tree"],
        attempt_id=raw["provider_attempt"]["attempt_id"],
        protected_join=raw["current_protected_join"],
    )
    build_cap_s1_result(**raw)

    extra_marker = dict(raw)
    extra_marker["canary_evidence"] = dataclasses.replace(
        raw["canary_evidence"],
        turn_marker_results=raw["canary_evidence"].turn_marker_results
        + (("unexpected", False),),
    )
    with pytest.raises(CapS1ResultError, match="markers_invalid"):
        build_cap_s1_result(**extra_marker)

    wrong_attempt = dict(raw)
    wrong_attempt["canary_evidence"] = dataclasses.replace(
        raw["canary_evidence"], provider_attempt_id="different-attempt"
    )
    with pytest.raises(CapS1ResultError, match="binding_mismatch"):
        build_cap_s1_result(**wrong_attempt)

    wrong_protected_join = dict(raw)
    wrong_protected_join["canary_evidence"] = dataclasses.replace(
        raw["canary_evidence"], protected_join="f" * 40
    )
    with pytest.raises(CapS1ResultError, match="binding_mismatch"):
        build_cap_s1_result(**wrong_protected_join)

    hostile_inventory = dict(raw)
    hostile_inventory["canary_evidence"] = dataclasses.replace(
        raw["canary_evidence"],
        artifact_inventory=("workspace:/Users/alice/auth-token-secret",),
    )
    with pytest.raises(CapS1ResultError, match="canary_evidence_invalid") as excinfo:
        build_cap_s1_result(**hostile_inventory)
    assert "/Users/alice" not in str(excinfo.value)
    assert "auth-token-secret" not in str(excinfo.value)

    for credential_oriented_name in (
        "workspace:auth.json",
        "workspace:credentials.json",
        "schema:oauth_credentials.json",
    ):
        hostile_inventory = dict(raw)
        hostile_inventory["canary_evidence"] = dataclasses.replace(
            raw["canary_evidence"],
            artifact_inventory=(credential_oriented_name,),
        )
        with pytest.raises(CapS1ResultError, match="canary_evidence_invalid") as excinfo:
            build_cap_s1_result(**hostile_inventory)
        assert credential_oriented_name not in str(excinfo.value)


def test_cap_s1_result_local_and_hosted_proof_shapes_are_enforced() -> None:
    empty_local = _happy_cap_s1_result_kwargs()
    empty_local["local_proof"] = {}
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        build_cap_s1_result(**empty_local)

    malformed_local = _happy_cap_s1_result_kwargs()
    malformed_local["local_proof"]["passed"] = "12"
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        build_cap_s1_result(**malformed_local)

    empty_hosted = _happy_cap_s1_result_kwargs()
    empty_hosted["hosted_proof"] = {}
    with pytest.raises(CapS1ResultError, match="hosted_proof_invalid"):
        build_cap_s1_result(**empty_hosted)

    missing_run_id = _happy_cap_s1_result_kwargs()
    missing_run_id["hosted_proof"]["run_id"] = ""
    with pytest.raises(CapS1ResultError, match="hosted_proof_invalid"):
        build_cap_s1_result(**missing_run_id)

    missing_conclusion = _happy_cap_s1_result_kwargs()
    missing_conclusion["hosted_proof"]["conclusion"] = ""
    with pytest.raises(CapS1ResultError, match="hosted_proof_invalid"):
        build_cap_s1_result(**missing_conclusion)


@pytest.mark.parametrize(
    ("mutate", "case_name"),
    [
        (lambda raw: raw["local_proof"].update(passed=-1), "negative-count"),
        (lambda raw: raw["local_proof"].update(passed=True), "boolean-count"),
        (lambda raw: raw["hosted_proof"].update(conclusion="FAILURE"), "failed-hosted"),
        (lambda raw: raw["hosted_proof"].update(status="IN_PROGRESS"), "nonterminal-hosted"),
        (lambda raw: raw.update(security_proof={}), "empty-security"),
        (lambda raw: raw.update(mutation_proof={}), "empty-mutation"),
        (lambda raw: raw.update(cleanup_proof={}), "empty-cleanup"),
        (lambda raw: raw.update(review_state={}), "empty-review"),
        (
            lambda raw: raw.update(
                canary_evidence={"schema_version": CANARY_EVIDENCE_SCHEMA_VERSION}
            ),
            "schema-token-only-canary",
        ),
        (lambda raw: raw["hosted_proof"].update(unexpected="accepted"), "unknown-key"),
        (
            lambda raw: raw["security_proof"].update(
                evidence="/Users/alice/.codex/auth.json?token=secret"
            ),
            "secret-path-material",
        ),
        (lambda raw: raw["hosted_proof"].update(exact_head="f" * 40), "head-mismatch"),
        (lambda raw: raw["hosted_proof"].update(exact_tree="f" * 40), "tree-mismatch"),
        (
            lambda raw: raw["mutation_proof"].update(
                provider_attempt_id="different-attempt"
            ),
            "provider-attempt-mismatch",
        ),
        (
            lambda raw: raw["review_state"].update(
                reviewer=raw["review_state"]["author"]
            ),
            "self-review",
        ),
        (
            lambda raw: raw["review_state"].update(state="CHANGES_REQUESTED"),
            "changes-requested-review",
        ),
        (
            lambda raw: raw["cleanup_proof"].update(residue_count=1),
            "residue",
        ),
        (
            lambda raw: raw["cleanup_proof"].update(
                resource_kinds=[
                    "attempt",
                    "origin",
                    "process",
                    "projection",
                    "schema",
                    "workspace",
                ]
            ),
            "missing-thread-cleanup-proof",
        ),
    ],
)
def test_cap_s1_result_hostile_nested_receipts_refuse(mutate, case_name) -> None:
    raw = _happy_cap_s1_result_kwargs()
    mutate(raw)
    with pytest.raises(CapS1ResultError) as excinfo:
        build_cap_s1_result(**raw)
    assert "/Users/alice" not in str(excinfo.value), case_name
    assert "token=secret" not in str(excinfo.value), case_name


def test_cap_s1_result_direct_mapping_subreceipts_are_not_proof() -> None:
    raw = _happy_cap_s1_result_kwargs()
    typed = build_cap_s1_result(**raw)
    result = dataclasses.replace(
        typed,
        local_proof=dataclasses.asdict(typed.local_proof),
    )
    with pytest.raises(CapS1ResultError, match="subreceipt_type_invalid"):
        validate_cap_s1_result(
            result, producer_evidence_path=raw["producer_evidence_path"]
        )


def test_cap_s1_result_release_ceiling_and_exact_path_census_are_closed() -> None:
    wrong_release = _happy_cap_s1_result_kwargs()
    wrong_release["release_state"] = "READY"
    with pytest.raises(CapS1ResultError, match="release_state_invalid"):
        build_cap_s1_result(**wrong_release)

    wrong_paths = _happy_cap_s1_result_kwargs()
    wrong_paths["changed_path_census"] = wrong_paths["changed_path_census"][:-1]
    with pytest.raises(CapS1ResultError, match="changed_path_census_mismatch"):
        build_cap_s1_result(**wrong_paths)


def test_cap_s1_result_held_non_goals_must_be_nonempty() -> None:
    empty_held = _happy_cap_s1_result_kwargs()
    empty_held["held_non_goals"] = ()
    with pytest.raises(CapS1ResultError, match="held_non_goals_empty"):
        build_cap_s1_result(**empty_held)


# ---------------------------------------------------------------------------
# REQUEST_CHANGES 5112126365: trust-boundary regressions (RED first)
# ---------------------------------------------------------------------------


def test_run_canary_refuses_foreign_attempt_root_without_touching_it_or_starting_provider(
    tmp_path,
) -> None:
    scratch = tmp_path / "scratch-foreign-attempt-root"
    foreign_root = scratch / "cap-s1-attempt-root"
    foreign_root.mkdir(parents=True)
    sentinel = foreign_root / "foreign.txt"
    sentinel.write_bytes(b"foreign bytes must survive exactly\n")

    with pytest.raises(CanaryStop) as excinfo:
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-canary-foreign-attempt-root",
            protected_join="c" * 40,
            client_factory=_canary_client_factory(),
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )

    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
    assert sentinel.read_bytes() == b"foreign bytes must survive exactly\n"
    assert sorted(path.name for path in foreign_root.iterdir()) == ["foreign.txt"]
    assert _CREATED_CANARY_CLIENTS == []
    assert not (scratch / "codex-home").exists()
    assert not (scratch / "fake-state.json").exists()
    assert not (scratch / "synthetic-workspace").exists()
    assert not any(path.name.startswith("schema-attestation") for path in scratch.iterdir())
    assert not any(path.name.startswith("ephemeral-archive-") for path in scratch.iterdir())


@pytest.mark.parametrize(
    ("field_name", "hostile_value"),
    [
        ("operation", "x" * (1024 * 1024)),
        ("receiver", "receiver\nSTART provider-handle: native-task"),
        ("carrier", "/Users/alice/.codex/auth.json?token=secret"),
        ("carrier", "C0BSBM78V1N/1788258398.440699\x00native-task"),
    ],
)
def test_cap_s1_result_top_level_identities_use_bounded_closed_grammars(
    field_name, hostile_value
) -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw[field_name] = hostile_value
    with pytest.raises(CapS1ResultError, match=f"{field_name}_invalid") as excinfo:
        build_cap_s1_result(**raw)
    assert hostile_value not in str(excinfo.value)


def test_cap_s1_result_refuses_mixed_case_self_review_identity() -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["review_state"].update(
        author="chriswong6031-creator",
        reviewer="CHRISWONG6031-CREATOR",
    )
    with pytest.raises(CapS1ResultError, match="review_state_invalid"):
        build_cap_s1_result(**raw)


@pytest.mark.parametrize(
    ("receipt_name", "field_name", "hostile_value"),
    [
        ("local_proof", "passed", 999_999),
        ("hosted_proof", "jobs_passed", 999),
        ("security_proof", "tool_count", 999),
        ("mutation_proof", "killed", 999_999),
    ],
)
def test_cap_s1_result_refuses_unbounded_caller_authored_positive_counts(
    receipt_name, field_name, hostile_value
) -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw[receipt_name][field_name] = hostile_value
    with pytest.raises(CapS1ResultError):
        build_cap_s1_result(**raw)


def test_cap_s1_result_refuses_caller_selected_digest_after_summary_mutation() -> None:
    raw = _happy_cap_s1_result_kwargs()
    original_digest = raw["security_proof"]["evidence_digest"]
    raw["security_proof"]["tool_count"] = 4
    raw["security_proof"]["tool_manifest"] = (
        *raw["security_proof"]["tool_manifest"],
        ("typing", "PASSED", 0, _canonical_digest({"tool": "typing"})),
    )
    raw["security_proof"]["evidence_digest"] = original_digest
    with pytest.raises(CapS1ResultError, match="evidence_digest_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_result_rederives_local_same_unit_totals_from_suite_manifest() -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["local_proof"]["total"] += 1
    _refresh_result_receipt_digest(raw, "local_proof", "CapS1LocalProofReceipt")
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_result_refetches_complete_hosted_job_inventory() -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["hosted_proof"].update(
        jobs_total=2,
        jobs_passed=2,
        job_manifest=(
            ("100000000001", "test", "COMPLETED", "SUCCESS"),
            ("100000000002", "invented", "COMPLETED", "SUCCESS"),
        ),
    )
    _refresh_result_receipt_digest(raw, "hosted_proof", "CapS1HostedProofReceipt")
    with pytest.raises(CapS1ResultError, match="hosted_proof_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_result_rederives_cleanup_summary_from_owned_resource_manifest() -> None:
    raw = _happy_cap_s1_result_kwargs()
    rows = list(raw["cleanup_proof"]["resource_manifest"])
    kind, identity, _removed, _absent = rows[0]
    rows[0] = (kind, identity, False, False)
    raw["cleanup_proof"]["resource_manifest"] = tuple(rows)
    _refresh_result_receipt_digest(raw, "cleanup_proof", "CapS1CleanupProofReceipt")
    with pytest.raises(CapS1ResultError, match="cleanup_proof_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_result_refetches_review_and_requires_stable_non_author_ids() -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["review_state"].update(reviewer="invented-reviewer", reviewer_id=404)
    _refresh_result_receipt_digest(raw, "review_state", "CapS1ReviewReceipt")
    with pytest.raises(CapS1ResultError, match="review_state_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_source_owned_validation_consumes_precleanup_github_observations(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    raw = _happy_cap_s1_result_kwargs()
    result = build_cap_s1_result(**raw)
    observations = _CapS1GitHubObservations(
        hosted_run={
            "id": int(result.hosted_proof.run_id),
            "status": "completed",
            "conclusion": "success",
            "head_sha": result.exact_head,
        },
        hosted_rows=result.hosted_proof.job_manifest,
        pull={
            "user": {
                "login": result.review_state.author,
                "id": result.review_state.author_id,
            },
            "head": {"sha": result.exact_head},
        },
        review={
            "id": int(result.review_state.review_id),
            "state": result.review_state.state,
            "commit_id": result.review_state.review_commit,
            "user": {
                "login": result.review_state.reviewer,
                "id": result.review_state.reviewer_id,
            },
        },
    )
    monkeypatch.setattr(
        canary_module,
        "_rederive_hosted_job_manifest",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("post-cleanup hosted read")),
    )
    monkeypatch.setattr(
        canary_module,
        "_rederive_github_review",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("post-cleanup review read")),
    )
    _validate_cap_s1_result_against_producer(
        result,
        producer_evidence=_load_cap_s1_producer_evidence(
            raw["producer_evidence_path"]
        ),
        github_observations=observations,
    )


# ---------------------------------------------------------------------------
# REQUEST_CHANGES 5112468319: producer-authentic evidence (RED first)
# ---------------------------------------------------------------------------


def test_run_canary_missing_fake_client_factory_has_no_owned_residue(tmp_path) -> None:
    scratch = tmp_path / "missing-fake-client-factory"
    with pytest.raises(ValueError, match="explicit client_factory"):
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-missing-fake-client",
            protected_join="c" * 40,
            client_factory=None,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert not (scratch / "cap-s1-attempt-root").exists()


def test_run_canary_fake_auth_setup_failure_cleans_first_owned_effect(
    tmp_path, monkeypatch
) -> None:
    scratch = tmp_path / "fake-auth-setup-failure"
    real_write_text = Path.write_text

    def _fail_auth_write(self, *args, **kwargs):
        if self.name == "auth.json":
            raise OSError("synthetic auth write failure")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_auth_write)
    with pytest.raises(OSError, match="synthetic auth write failure"):
        run_canary(
            backend="fake",
            binary_path=None,
            codex_home=None,
            repo_root=REPO_ROOT,
            scratch_root=scratch,
            operation_id="cap-s1-fake-auth-failure",
            protected_join="c" * 40,
            client_factory=_canary_client_factory(),
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert not (
        scratch / "cap-s1-attempt-root"
    ).exists(), "CAP_C_FIRST_EFFECT_CLEANUP_BYPASSED"


@pytest.mark.parametrize(
    "receipt_name",
    ("local_proof", "security_proof", "mutation_proof", "cleanup_proof"),
)
def test_cap_s1_result_refuses_invented_self_consistent_proof_family(
    receipt_name,
) -> None:
    raw = _happy_cap_s1_result_kwargs()
    if receipt_name == "local_proof":
        raw[receipt_name].update(
            suite_count=1,
            total=1,
            passed=1,
            skipped=0,
            failed=0,
            cancelled=0,
            suite_manifest=(("invented-suite", 1, 0, 0, 0),),
        )
        receipt_type = "CapS1LocalProofReceipt"
    elif receipt_name == "security_proof":
        raw[receipt_name].update(
            status="CLEAN",
            tool_count=1,
            findings=0,
            failures=0,
            cancelled=0,
            tool_manifest=(("invented-tool", "PASSED", 0, "f" * 64),),
        )
        receipt_type = "CapS1SecurityProofReceipt"
    elif receipt_name == "mutation_proof":
        raw[receipt_name].update(
            status="PASSED",
            total=1,
            killed=1,
            survived=0,
            skipped=0,
            errors=0,
            cancelled=0,
            mutation_manifest=(("invented-mutation", "KILLED", "f" * 64),),
        )
        receipt_type = "CapS1MutationProofReceipt"
    else:
        raw[receipt_name]["resource_manifest"] = tuple(
            (kind, "f" * 64, True, True)
            for kind in raw[receipt_name]["resource_kinds"]
        )
        receipt_type = "CapS1CleanupProofReceipt"
    _refresh_result_receipt_digest(raw, receipt_name, receipt_type)
    with pytest.raises(CapS1ResultError, match=f"{receipt_name}_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_result_refuses_wholly_forged_producer_family() -> None:
    """CAP_B discriminator: matching forged families never become evidence."""

    forged = _happy_cap_s1_result_kwargs()
    with pytest.raises(CapS1ResultError) as excinfo:
        _public_build_cap_s1_result(**forged)
    assert str(excinfo.value) == (
        "cap_s1_result_caller_proof_authority_forbidden"
    ), "CAP_B_FORGED_PRODUCER_ACCEPTED"


def test_cap_s1_result_public_boundary_refuses_direct_proof_objects() -> None:
    forged = _happy_cap_s1_result_kwargs()
    typed = build_cap_s1_result(**forged)
    with pytest.raises(
        CapS1ResultError,
        match="caller_proof_authority_forbidden",
    ):
        _public_build_cap_s1_result(local_proof=typed.local_proof)


def test_cap_s1_result_historical_attempt_without_cleanup_stays_unavailable() -> None:
    with pytest.raises(CapS1ResultError, match="cleanup_evidence_unavailable"):
        _public_build_cap_s1_result(
            operation="cap-s1-abc-final-source-repair-20260904-sol-001",
            receiver="codex-cap-s1",
            carrier="C0BSBM78V1N/1788511189.200899",
            canary_evidence=None,
            hosted_run_id="1",
            review_id="1",
        )


def test_cap_s1_result_caller_constructed_canary_object_is_not_producer_proof() -> None:
    forged = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="forged-attempt",
        protected_join="c" * 40,
    )
    with pytest.raises(CapS1ResultError, match="canary_evidence_source_invalid"):
        _public_build_cap_s1_result(
            operation="cap-s1-abc-final-source-repair-20260904-sol-001",
            receiver="codex-cap-s1",
            carrier="C0BSBM78V1N/1788511189.200899",
            canary_evidence=forged,
            hosted_run_id="1",
            review_id="1",
        )


def test_cap_s1_result_actual_fake_canary_refuses_before_source_observer(
    tmp_path, monkeypatch
) -> None:
    """A real fake-realm return is fixture evidence, never provider proof."""

    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    scratch = tmp_path / "fake-canary-source-boundary"
    scratch.mkdir()
    evidence = run_canary(
        backend="fake",
        binary_path=None,
        codex_home=None,
        repo_root=REPO_ROOT,
        scratch_root=scratch,
        operation_id="cap-s1-fake-not-provider-proof",
        protected_join="c" * 40,
        client_factory=_canary_client_factory(replies=list(_HAPPY_REPLIES)),
        run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
    )
    observer_called = False

    def _observer_must_not_run(**_kwargs):
        nonlocal observer_called
        observer_called = True
        raise AssertionError("source observer reached for fake canary")

    monkeypatch.setattr(canary_module, "_run_cap_s1_source_observer", _observer_must_not_run)
    with pytest.raises(CapS1ResultError, match="canary_provenance_invalid"):
        _public_build_cap_s1_result(
            operation="cap-s1-abc-final-source-repair-20260904-sol-001",
            receiver="codex-cap-s1",
            carrier="C0BSBM78V1N/1788511189.200899",
            canary_evidence=evidence,
            hosted_run_id="1",
            review_id="1",
        )
    assert not observer_called


def test_cap_s1_canary_seal_requires_exact_object_and_is_at_most_once(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(canary_module, "_CANARY_SOURCE_EVIDENCE_SEALS", {})
    evidence = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="fixture-seal-attempt",
        protected_join="c" * 40,
    )
    replacement = dataclasses.replace(evidence)
    _register_cap_s1_canary_evidence(
        evidence,
        backend="fake",
        client_factory=object(),
    )

    with pytest.raises(CapS1ResultError, match="canary_evidence_source_invalid"):
        _consume_cap_s1_fake_canary_for_fixture(replacement)
    assert _consume_cap_s1_fake_canary_for_fixture(evidence) == (
        "FIXTURE_ONLY/NOT_PROVIDER_PROOF"
    )
    with pytest.raises(CapS1ResultError, match="canary_evidence_source_invalid"):
        _consume_cap_s1_fake_canary_for_fixture(evidence)


def test_cap_s1_canary_seal_expires_weak_entries_and_bounds_live_entries(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    seals = {}
    monkeypatch.setattr(canary_module, "_CANARY_SOURCE_EVIDENCE_SEALS", seals)
    monkeypatch.setattr(canary_module, "_CANARY_SOURCE_EVIDENCE_SEAL_LIMIT", 1)
    first = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="fixture-seal-first",
        protected_join="c" * 40,
    )
    _register_cap_s1_canary_evidence(first, backend="fake", client_factory=object())
    assert len(seals) == 1
    del first
    gc.collect()
    assert seals == {}

    live = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="fixture-seal-live",
        protected_join="c" * 40,
    )
    other = dataclasses.replace(live, provider_attempt_id="fixture-seal-other")
    _register_cap_s1_canary_evidence(live, backend="fake", client_factory=object())
    with pytest.raises(CanaryStop, match="seal capacity unavailable"):
        _register_cap_s1_canary_evidence(other, backend="fake", client_factory=object())


def test_cap_s1_canary_seal_records_failed_observer_and_never_retries(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(canary_module, "_CANARY_SOURCE_EVIDENCE_SEALS", {})
    monkeypatch.setattr(
        canary_module,
        "_cap_s1_canary_provenance",
        lambda **_kwargs: "LIVE_DEFAULT_APP_SERVER",
    )
    evidence = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="fixture-seal-observer-failure",
        protected_join="c" * 40,
    )
    replacement = dataclasses.replace(evidence)
    _register_cap_s1_canary_evidence(
        evidence,
        backend="live",
        client_factory=object(),
    )
    calls = 0
    request = dict(
        operation="cap-s1-abc-final-source-repair-20260904-sol-001",
        receiver="codex-cap-s1",
        carrier="C0BSBM78V1N/1788511189.200899",
        canary_evidence=evidence,
        hosted_run_id="1",
        review_id="1",
    )

    def _failed_observer(**_kwargs):
        nonlocal calls
        calls += 1
        with pytest.raises(CapS1ResultError, match="canary_evidence_in_progress"):
            _public_build_cap_s1_result(**request)
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")

    monkeypatch.setattr(canary_module, "_run_cap_s1_source_observer", _failed_observer)
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        _public_build_cap_s1_result(**request)
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        _public_build_cap_s1_result(**request)
    with pytest.raises(CapS1ResultError, match="canary_evidence_source_invalid"):
        _public_build_cap_s1_result(**{**request, "canary_evidence": replacement})
    assert calls == 1


def test_cap_s1_canary_seal_refuses_concurrent_second_claim(monkeypatch) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(canary_module, "_CANARY_SOURCE_EVIDENCE_SEALS", {})
    monkeypatch.setattr(
        canary_module,
        "_cap_s1_canary_provenance",
        lambda **_kwargs: "LIVE_DEFAULT_APP_SERVER",
    )
    evidence = _completed_canary_evidence(
        head="a" * 40,
        tree="b" * 40,
        attempt_id="fixture-seal-concurrent",
        protected_join="c" * 40,
    )
    _register_cap_s1_canary_evidence(
        evidence,
        backend="live",
        client_factory=object(),
    )
    entered = threading.Event()
    release = threading.Event()
    first_errors = []
    calls = 0
    request = dict(
        operation="cap-s1-abc-final-source-repair-20260904-sol-001",
        receiver="codex-cap-s1",
        carrier="C0BSBM78V1N/1788511189.200899",
        canary_evidence=evidence,
        hosted_run_id="1",
        review_id="1",
    )

    def _blocking_observer(**_kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=5)
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")

    def _first_claim():
        try:
            _public_build_cap_s1_result(**request)
        except CapS1ResultError as exc:
            first_errors.append(str(exc))

    monkeypatch.setattr(canary_module, "_run_cap_s1_source_observer", _blocking_observer)
    worker = threading.Thread(target=_first_claim)
    worker.start()
    assert entered.wait(timeout=5)
    with pytest.raises(CapS1ResultError, match="canary_evidence_in_progress"):
        _public_build_cap_s1_result(**request)
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert first_errors == ["cap_s1_result_security_proof_invalid"]
    assert calls == 1


def test_cap_s1_diff_observer_executes_exact_registry_and_consumes_status(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    calls = []

    def _completed(
        argv, *, cwd, timeout, owned_state_path=None, cleanup_observations=None
    ):
        calls.append((tuple(argv), cwd, timeout, owned_state_path))
        return _subprocess.CompletedProcess(
            args=list(argv), returncode=len(calls) - 1, stdout="", stderr=""
        )

    monkeypatch.setattr(canary_module, "_run_cap_s1_observer_process", _completed)
    passed = _observe_cap_s1_diff(exact_head="a" * 40, protected_join="b" * 40)
    failed = _observe_cap_s1_diff(exact_head="a" * 40, protected_join="b" * 40)

    expected_argv = tuple(cap_s1_observer_registry()["diff_argv"])
    assert calls[0][0][:6] == expected_argv[:6]
    assert calls[0][0][6] == f"{'b' * 40}...{'a' * 40}"
    assert calls[0][0][7:] == expected_argv[7:]
    assert passed[0:3] == ("diff-check", "PASSED", 0)
    assert failed[0:3] == ("diff-check", "FAILED", 1)
    assert passed[3] != failed[3]


def test_cap_s1_supply_rejects_unapproved_redirect_even_when_bytes_match(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    payload = b"equal-hash-payload"

    class _Response:
        status = 302
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://unapproved.example.invalid/asset"

        def read(self, _size=-1):
            value, self._payload = getattr(self, "_payload", payload), b""
            return value

    class _Opener:
        def open(self, _request, timeout):
            assert timeout == 60
            return _Response()

    monkeypatch.setattr(canary_module.urllib.request, "build_opener", lambda *_args: _Opener())
    with pytest.raises(CapS1ResultError, match="secret_supply_unavailable"):
        _download_cap_s1_pinned_bytes(
            url=CAP_S1_GITLEAKS_ARCHIVE_URL,
            expected_size=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )


class _CapS1SupplyFixtureResponse:
    def __init__(self, *, status, url, payload=b"", location=None):
        self.status = status
        self._url = url
        self._payload = payload
        self.closed = False
        self.headers = {}
        if status == 200:
            self.headers["Content-Length"] = str(len(payload))
        if location is not None:
            self.headers["Location"] = location

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if size < 0:
            size = len(self._payload)
        chunk, self._payload = self._payload[:size], self._payload[size:]
        return chunk

    def close(self):
        self.closed = True


def test_cap_s1_supply_accepts_direct_200_and_exact_single_hop(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    payload = b"finite-route-fixture"
    digest = hashlib.sha256(payload).hexdigest()
    direct = _CapS1SupplyFixtureResponse(
        status=200,
        url=canary_module.CAP_S1_GITLEAKS_RULE_URL,
        payload=payload,
    )
    archive_initial, archive_base, _asset_id = (
        canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[0]
    )
    opaque_destination = f"{archive_base}?opaque=fixture-value"
    first = _CapS1SupplyFixtureResponse(
        status=302,
        url=archive_initial,
        location=opaque_destination,
    )
    second = _CapS1SupplyFixtureResponse(
        status=200,
        url=opaque_destination,
        payload=payload,
    )
    responses = [direct, first, second]
    requests = []

    class _Opener:
        def open(self, request, timeout):
            requests.append((request.full_url, dict(request.header_items()), timeout))
            return responses.pop(0)

    monkeypatch.setattr(
        canary_module.urllib.request,
        "build_opener",
        lambda *handlers: _Opener(),
    )
    assert _download_cap_s1_pinned_bytes(
        url=canary_module.CAP_S1_GITLEAKS_RULE_URL,
        expected_size=len(payload),
        expected_sha256=digest,
    ) == payload
    assert _download_cap_s1_pinned_bytes(
        url=archive_initial,
        expected_size=len(payload),
        expected_sha256=digest,
    ) == payload
    assert [row[0] for row in requests] == [
        canary_module.CAP_S1_GITLEAKS_RULE_URL,
        archive_initial,
        opaque_destination,
    ]
    assert all(row[1] == {"User-agent": "cap-s1-source-observer/1"} for row in requests)
    assert all(row[2] == 60 for row in requests)
    assert all(response.closed for response in (direct, first, second))


@pytest.mark.parametrize(
    "location",
    (
        "relative/path?opaque=x",
        "http://release-assets.githubusercontent.com/wrong?opaque=x",
        "https://user@release-assets.githubusercontent.com/wrong?opaque=x",
        "https://release-assets.githubusercontent.com:443/wrong?opaque=x",
        "https://RELEASE-ASSETS.GITHUBUSERCONTENT.COM/wrong?opaque=x",
        "https://release-assets.githubusercontent.com/wrong%2Fpath?opaque=x",
        "https://release-assets.githubusercontent.com/wrong?opaque=x#fragment",
        "https://release-assets.githubusercontent.com/wrong\\path?opaque=x",
        "https://release-assets.githubusercontent.com/wrong path?opaque=x",
    ),
)
def test_cap_s1_supply_rejects_noncanonical_redirect_locations(
    monkeypatch, location
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    initial, _base, _asset_id = canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[0]
    response = _CapS1SupplyFixtureResponse(
        status=302,
        url=initial,
        location=location,
    )

    class _Opener:
        def open(self, _request, _timeout=None, **_kwargs):
            return response

    monkeypatch.setattr(
        canary_module.urllib.request,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    with pytest.raises(CapS1ResultError, match="secret_supply_unavailable"):
        _download_cap_s1_pinned_bytes(
            url=initial,
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )
    assert response.closed


def test_cap_s1_supply_refuses_redirect_chain_without_retry(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    initial, base, _asset_id = canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[0]
    destination = f"{base}?opaque=x"
    responses = [
        _CapS1SupplyFixtureResponse(status=302, url=initial, location=destination),
        _CapS1SupplyFixtureResponse(status=302, url=destination, location=destination),
    ]
    calls = 0

    class _Opener:
        def open(self, _request, timeout):
            nonlocal calls
            calls += 1
            assert timeout == 60
            return responses.pop(0)

    monkeypatch.setattr(
        canary_module.urllib.request,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    with pytest.raises(CapS1ResultError, match="secret_supply_unavailable"):
        _download_cap_s1_pinned_bytes(
            url=initial,
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )
    assert calls == 2


@pytest.mark.parametrize("location_kind", ("cross-asset", "oversized", "control"))
def test_cap_s1_supply_refuses_cross_asset_and_unbounded_location(
    monkeypatch, location_kind
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    initial, base, _asset_id = canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[0]
    if location_kind == "cross-asset":
        wrong_base = canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[1][1]
        location = f"{wrong_base}?opaque=private-cross-asset"
    elif location_kind == "oversized":
        location = f"{base}?opaque={'x' * 8192}"
    else:
        location = f"{base}?opaque=private\ncontrol"
    response = _CapS1SupplyFixtureResponse(
        status=302,
        url=initial,
        location=location,
    )

    class _Opener:
        def open(self, _request, timeout):
            assert timeout == 60
            return response

    monkeypatch.setattr(
        canary_module.urllib.request,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    with pytest.raises(CapS1ResultError) as excinfo:
        _download_cap_s1_pinned_bytes(
            url=initial,
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )
    assert str(excinfo.value) == "cap_s1_result_secret_supply_unavailable"
    assert "private" not in str(excinfo.value)
    assert response.closed


@pytest.mark.parametrize("hostile", ("changed-final-url", "different-hash"))
def test_cap_s1_supply_refuses_changed_final_identity_or_digest(
    monkeypatch, hostile
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    payload = b"fixed-payload"
    initial, base, _asset_id = canary_module.CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES[0]
    destination = f"{base}?opaque=private-final-token"
    first = _CapS1SupplyFixtureResponse(
        status=302,
        url=initial,
        location=destination,
    )
    second = _CapS1SupplyFixtureResponse(
        status=200,
        url=destination + ("-changed" if hostile == "changed-final-url" else ""),
        payload=payload,
    )
    responses = [first, second]

    class _Opener:
        def open(self, _request, timeout):
            assert timeout == 60
            return responses.pop(0)

    monkeypatch.setattr(
        canary_module.urllib.request,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    expected_digest = hashlib.sha256(
        b"different" if hostile == "different-hash" else payload
    ).hexdigest()
    with pytest.raises(CapS1ResultError) as excinfo:
        _download_cap_s1_pinned_bytes(
            url=initial,
            expected_size=len(payload),
            expected_sha256=expected_digest,
        )
    assert str(excinfo.value) in {
        "cap_s1_result_secret_supply_unavailable",
        "cap_s1_result_secret_supply_invalid",
    }
    assert "private-final-token" not in str(excinfo.value)
    assert first.closed and second.closed


def test_cap_s1_source_observer_registry_is_exact_and_secret_scan_stays_held() -> None:
    registry = cap_s1_observer_registry()
    assert registry["schema_version"] == "mastermind.cap_s1_source_observer_registry/v1"
    assert registry["python_argv"][:6] == (
        "<bound-lexical-python-entrypoint>",
        "-I",
        "-B",
        "-c",
        "<fixed-source-owned-pytest-bootstrap>",
        "<private-exact-provenance-binding>",
    )
    assert registry["python_argv"][6:9] == (
        "-q",
        "--junitxml",
        "<owned-output>",
    )
    assert len(registry["python_argv"][9:]) == 17
    assert registry["python_provenance_exit"] not in {0, 1}
    assert registry["python_bootstrap_sha256"] == hashlib.sha256(
        registry["python_bootstrap_source"].encode("utf-8")
    ).hexdigest()
    assert len(registry["diff_argv"][8:]) == 21
    assert tuple(mutation_id for mutation_id, _node in registry["mutants"]) == (
        "CAP_A_UNRELATED_SKILL_ACCEPTED",
        "CAP_B_FORGED_PRODUCER_ACCEPTED",
        "CAP_C_FIRST_EFFECT_CLEANUP_BYPASSED",
    )
    owned_git = registry["owned_git"]
    assert owned_git["object_count"] == 131
    assert owned_git["historical_tree_closure"] == {
        "commit": "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab",
        "root_tree": "b5a042c3b0a1a54d74855be5dcd132bef3a7a2ce",
        "path_count": 124,
        "unique_object_count": 121,
        "total_raw_bytes": 77_050,
        "maximum_raw_bytes": 21_231,
        "path_manifest_digest": (
            "5a6c36388af247b001fad02cabd21fd8e4e9d8e97d54adaf3ef785aacca4d92f"
        ),
        "object_manifest_digest": (
            "039b886b8975708e35347716afb50a105b4ae89d83af54300cb37ac25e188666"
        ),
        "tracked_attribute_blobs": (),
        "package_blob_count": 7,
    }
    assert "archive-fixed-historical-package" in owned_git["commands"]
    assert "ls-tree-full-historical-leaf-metadata-no-attributes" in owned_git[
        "commands"
    ]
    assert registry["secret_scan"].endswith("EVIDENCE_UNAVAILABLE_HOLD")


def test_cap_s1_strict_json_parser_refuses_duplicate_keys_at_every_depth() -> None:
    for payload in (
        '{"exact_head":"a","exact_head":"b"}',
        '{"outer":{"state":"clean","state":"forged"}}',
        '{"rows":[{"id":1,"id":2}]}',
    ):
        with pytest.raises(CapS1ResultError, match="duplicate_boundary") as excinfo:
            _strict_json_loads(payload, error="cap_s1_result_duplicate_boundary")
        assert "forged" not in str(excinfo.value)


def test_cap_s1_github_json_boundary_refuses_duplicate_keys(monkeypatch) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    cleanup = []

    def _duplicate_response(argv, **kwargs):
        assert tuple(argv) == (
            "gh",
            "api",
            "repos/mastermindx-market-intelligence/Mastermind/fixed",
        )
        assert kwargs["cleanup_observations"] is cleanup
        assert kwargs["github_environment"] is True
        return _subprocess.CompletedProcess(
            args=["gh", "api", "fixed"],
            returncode=0,
            stdout='{"head_sha":"a","head_sha":"b"}',
            stderr="",
        )

    monkeypatch.setattr(
        canary_module,
        "_run_cap_s1_observer_process",
        _duplicate_response,
    )
    with pytest.raises(CapS1ResultError, match="github_evidence_unavailable") as excinfo:
        _real_github_api_json(
            "repos/mastermindx-market-intelligence/Mastermind/fixed",
            cleanup_observations=cleanup,
        )
    assert "head_sha" not in str(excinfo.value)


def _install_cap_s1_codeql_fixture(monkeypatch, *, flaw=None):
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    exact_head = "a" * 40
    categories = ("actions", "javascript-typescript", "python")
    check_rows = []
    details = {}
    runs = {}
    for index, category in enumerate(categories, start=1):
        check_id = 1000 + index
        run_id = str(9000 + index)
        name = f"Analyze ({category})"
        row = {
            "id": check_id,
            "name": name,
            "head_sha": exact_head,
            "app": {"id": 15368, "slug": "github-actions"},
        }
        check_rows.append(row)
        details[check_id] = {
            **row,
            "status": "completed",
            "conclusion": "success",
            "details_url": (
                "https://github.com/mastermindx-market-intelligence/Mastermind/"
                f"actions/runs/{run_id}/job/{check_id}"
            ),
        }
        runs[run_id] = {
            "id": int(run_id),
            "head_sha": exact_head,
            "status": "completed",
            "conclusion": "success",
        }
    analyses = [
        {
            "id": 2000 + index,
            "commit_sha": exact_head,
            "ref": "refs/pull/350/head",
            "analysis_key": "dynamic/github-code-scanning/codeql:analyze",
            "category": f"/language:{category}",
            "tool": {"name": "CodeQL"},
            "results_count": 0,
            "rules_count": 10 + index,
            "error": "",
            "warning": "",
        }
        for index, category in enumerate(categories, start=1)
    ]
    if flaw == "same-sha-non-codeql":
        analyses[0]["tool"] = {"name": "Other"}
    elif flaw == "missing-category":
        analyses.pop()
    elif flaw == "missing-check":
        check_rows.pop()
    elif flaw == "nonzero-results":
        analyses[0]["results_count"] = 1
    elif flaw == "analysis-error":
        analyses[0]["error"] = "analysis failed"
    elif flaw == "analysis-warning":
        analyses[0]["warning"] = "analysis incomplete"
    elif flaw == "wrong-ref":
        analyses[0]["ref"] = "refs/heads/fable/cap-s1-complete-vertical-20260901"
    elif flaw == "duplicate-rerun":
        analyses.append(dict(analyses[0], id=2999))

    pull_reads = 0

    def _json(endpoint):
        nonlocal pull_reads
        if endpoint.endswith("/pulls/350"):
            pull_reads += 1
            head = exact_head
            if flaw == "moved-pr" and pull_reads == 2:
                head = "b" * 40
            return {
                "number": 350,
                "head": {
                    "sha": head,
                    "ref": "fable/cap-s1-complete-vertical-20260901",
                },
            }
        if endpoint.endswith("/git/ref/pull/350/head"):
            return {
                "ref": "refs/pull/350/head",
                "object": {"type": "commit", "sha": exact_head},
            }
        if "/commits/" in endpoint and "/check-runs?" in endpoint:
            return {"total_count": len(check_rows), "check_runs": check_rows}
        match = re.search(r"/check-runs/([0-9]+)$", endpoint)
        if match:
            return details[int(match.group(1))]
        match = re.search(r"/actions/runs/([0-9]+)$", endpoint)
        if match:
            return runs[match.group(1)]
        raise AssertionError(endpoint)

    def _list(endpoint):
        if "/code-scanning/analyses?" in endpoint:
            assert "ref=refs%2Fpull%2F350%2Fhead" in endpoint
            return analyses
        if "/code-scanning/alerts?" in endpoint:
            assert "?pr=350&state=open&" in endpoint
            return []
        raise AssertionError(endpoint)

    monkeypatch.setattr(canary_module, "_github_api_json", _json)
    monkeypatch.setattr(canary_module, "_github_api_list", _list)
    return exact_head


def test_cap_s1_codeql_binds_exact_pr_checks_analyses_and_alerts(monkeypatch) -> None:
    exact_head = _install_cap_s1_codeql_fixture(monkeypatch)
    rows = _observe_cap_s1_codeql(exact_head=exact_head)
    assert tuple(row[:3] for row in rows) == (
        ("codeql-checks", "PASSED", 0),
        ("code-scanning-alerts", "PASSED", 0),
    )


@pytest.mark.parametrize(
    "flaw",
    (
        "same-sha-non-codeql",
        "missing-category",
        "missing-check",
        "nonzero-results",
        "analysis-error",
        "analysis-warning",
        "moved-pr",
        "wrong-ref",
        "duplicate-rerun",
    ),
)
def test_cap_s1_codeql_refuses_incomplete_or_moved_evidence(
    monkeypatch, flaw
) -> None:
    exact_head = _install_cap_s1_codeql_fixture(monkeypatch, flaw=flaw)
    with pytest.raises(CapS1ResultError, match="security_proof_(?:invalid|unavailable)"):
        _observe_cap_s1_codeql(exact_head=exact_head)


def test_cap_s1_codeql_refuses_full_page_pagination_exhaustion(monkeypatch) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    exact_head = _install_cap_s1_codeql_fixture(monkeypatch)
    original_list = canary_module._github_api_list

    def _full_analysis_pages(endpoint):
        if "/code-scanning/analyses?" in endpoint:
            return [{"page-not-terminal": True} for _index in range(100)]
        return original_list(endpoint)

    monkeypatch.setattr(canary_module, "_github_api_list", _full_analysis_pages)
    with pytest.raises(CapS1ResultError, match="security_proof_unavailable"):
        _observe_cap_s1_codeql(exact_head=exact_head)


def test_cap_s1_mutant_transforms_are_unique_and_nodes_are_fixed() -> None:
    source = (REPO_ROOT / "scripts/ohf/cap_s1_mastermind_operator_canary.py").read_text(
        encoding="utf-8"
    )
    test_source = Path(__file__).read_text(encoding="utf-8")
    assert len(CAP_S1_OBSERVER_MUTANT_TRANSFORMS) == 3
    for mutation_id, relative_path, preimage, postimage in CAP_S1_OBSERVER_MUTANT_TRANSFORMS:
        assert relative_path == "scripts/ohf/cap_s1_mastermind_operator_canary.py"
        assert source.count(preimage) == 1, mutation_id
        assert postimage not in source, mutation_id
    for _mutation_id, node in cap_s1_observer_registry()["mutants"]:
        module, separator, test_name = node.partition("::")
        assert separator == "::"
        assert module == "tests/test_cap_s1_mastermind_operator_canary.py"
        assert f"def {test_name}" in test_source


def _write_cap_s1_mutation_junit(
    path: Path,
    *,
    name: str = "test_bound",
    outcome: str = "PASSED",
    detail: str = "",
) -> None:
    child = ""
    if outcome == "FAILURE":
        child = (
            f'<failure type="AssertionError" message="{detail}">'
            f"{detail}</failure>"
        )
    elif outcome == "ERROR":
        child = f'<error type="RuntimeError" message="{detail}">{detail}</error>'
    elif outcome == "SKIPPED":
        child = '<skipped type="pytest.skip" message="fixture skip" />'
    path.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase classname="test_cap_s1_mastermind_operator_canary" name="{name}">'
        f"{child}</testcase></testsuite>",
        encoding="utf-8",
    )
    path.chmod(0o444)


def _install_cap_s1_mutation_unit_seams(
    canary_module,
    monkeypatch,
    *,
    source_root: Path,
    target: Path,
) -> None:
    """Keep narrow mutation-outcome tests independent of Git/provenance fixtures."""

    payload = target.read_bytes()
    git_blob = hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload
    ).hexdigest()
    manifest = (
        canary_module._CapS1SourceCopyEntry(
            path=target.relative_to(source_root).as_posix(),
            mode="100644",
            blob=git_blob,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )
    monkeypatch.setattr(
        canary_module,
        "_owned_cap_s1_source_copy",
        lambda **_kwargs: (source_root, manifest),
    )
    monkeypatch.setattr(
        canary_module,
        "_cap_s1_owned_git_package_expectation",
        lambda _source_root: ("b" * 40, "c" * 40, tuple(f"f{i}" for i in range(7))),
    )
    fake_git = canary_module._CapS1OwnedGitContext(
        git_dir=source_root / ".git",
        device=1,
        inode=1,
        exact_head="a" * 40,
        exact_tree="d" * 40,
        historical_commit="b" * 40,
        historical_package_tree="c" * 40,
        historical_tree_path_manifest=(),
        historical_tree_path_manifest_digest="4" * 64,
        historical_tree_object_manifest=(),
        historical_tree_object_manifest_digest="5" * 64,
        object_manifest=(),
        object_manifest_digest="e" * 64,
        filesystem_manifest=(),
        filesystem_manifest_digest="3" * 64,
        archive_digest="f" * 64,
        archive_diagnostic="",
        archive_diagnostic_digest=hashlib.sha256(b"").hexdigest(),
        archive_file_manifest=(),
        archive_file_manifest_digest="6" * 64,
        command_registry=(),
    )
    monkeypatch.setattr(
        canary_module,
        "_install_cap_s1_owned_git_context",
        lambda **_kwargs: fake_git,
    )
    monkeypatch.setattr(
        canary_module,
        "_verify_cap_s1_owned_git_context",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        canary_module,
        "_remove_cap_s1_owned_git_context",
        lambda *_args, **_kwargs: None,
    )
    binding = canary_module._CapS1PytestBinding(
        payload_json="{}",
        bootstrap_sha256=hashlib.sha256(
            canary_module._CAP_S1_PYTEST_BOOTSTRAP.encode("utf-8")
        ).hexdigest(),
        source_rows=(),
        pytest_origin_sha256="1" * 64,
        evidence_digest="2" * 64,
    )
    monkeypatch.setattr(
        canary_module,
        "_build_cap_s1_pytest_binding",
        lambda **_kwargs: binding,
    )


def test_cap_s1_mutation_junit_distinguishes_error_skip_and_wrong_node(
    tmp_path,
) -> None:
    node = "tests/test_cap_s1_mastermind_operator_canary.py::test_bound"
    for outcome in ("ERROR", "SKIPPED", "FAILURE", "PASSED"):
        junit = tmp_path / f"{outcome}.xml"
        _write_cap_s1_mutation_junit(
            junit,
            outcome=outcome,
            detail="AssertionError: FIXED_MUTANT" if outcome == "FAILURE" else "setup",
        )
        assert _parse_cap_s1_mutation_junit(
            junit,
            expected_node=node,
        ).outcome == outcome
    wrong = tmp_path / "wrong.xml"
    _write_cap_s1_mutation_junit(wrong, name="test_unrelated")
    with pytest.raises(CapS1ResultError, match="mutation_proof_invalid"):
        _parse_cap_s1_mutation_junit(wrong, expected_node=node)


@pytest.mark.parametrize(
    ("mutant_outcome", "expected_error"),
    (
        ("UNRELATED", "mutation_proof_invalid"),
        ("ERROR", "mutation_proof_invalid"),
        ("EXCEPTION", "mutation_proof_invalid"),
        ("PROVENANCE", "import_origin_invalid"),
    ),
)
def test_cap_s1_mutation_refuses_hostile_result_and_restores_source(
    tmp_path, monkeypatch, mutant_outcome, expected_error
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source_root = tmp_path / "source"
    target = source_root / "scripts/ohf/fixture.py"
    target.parent.mkdir(parents=True)
    original = b"return False\n"
    target.write_bytes(original)
    node = "tests/test_cap_s1_mastermind_operator_canary.py::test_bound"
    monkeypatch.setattr(
        canary_module,
        "CAP_S1_OBSERVER_MUTANTS",
        (("FIXED_MUTANT", node),),
    )
    monkeypatch.setattr(
        canary_module,
        "CAP_S1_OBSERVER_MUTANT_ASSERTIONS",
        (("FIXED_MUTANT", node, "FIXED_MUTANT"),),
    )
    monkeypatch.setattr(
        canary_module,
        "CAP_S1_OBSERVER_MUTANT_TRANSFORMS",
        (("FIXED_MUTANT", "scripts/ohf/fixture.py", "return False\n", "return True\n"),),
    )
    _install_cap_s1_mutation_unit_seams(
        canary_module,
        monkeypatch,
        source_root=source_root,
        target=target,
    )
    calls = 0

    def _run(argv, **_kwargs):
        nonlocal calls
        calls += 1
        junit = Path(argv[argv.index("--junitxml") + 1])
        if calls == 2 and mutant_outcome == "EXCEPTION":
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
        if calls == 2 and mutant_outcome == "PROVENANCE":
            return _subprocess.CompletedProcess(
                argv,
                canary_module._CAP_S1_PYTEST_PROVENANCE_EXIT,
                "",
                "",
            )
        if calls == 2 and mutant_outcome == "ERROR":
            _write_cap_s1_mutation_junit(junit, outcome="ERROR", detail="setup error")
            return _subprocess.CompletedProcess(argv, 1, "", "")
        if calls == 2:
            _write_cap_s1_mutation_junit(
                junit,
                outcome="FAILURE",
                detail="AssertionError: UNRELATED_ASSERTION",
            )
            return _subprocess.CompletedProcess(argv, 1, "", "")
        _write_cap_s1_mutation_junit(junit)
        return _subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(canary_module, "_run_cap_s1_observer_process", _run)
    with pytest.raises(CapS1ResultError, match=expected_error):
        _observe_cap_s1_mutations(exact_head="a" * 40, scratch_root=tmp_path)
    assert target.read_bytes() == original
    assert calls == 3


def test_cap_s1_mutation_refuses_skipped_control_before_mutation(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source_root = tmp_path / "source"
    target = source_root / "scripts/ohf/fixture.py"
    target.parent.mkdir(parents=True)
    target.write_text("return False\n", encoding="utf-8")
    node = "tests/test_cap_s1_mastermind_operator_canary.py::test_bound"
    monkeypatch.setattr(canary_module, "CAP_S1_OBSERVER_MUTANTS", (("MUTANT", node),))
    monkeypatch.setattr(
        canary_module,
        "CAP_S1_OBSERVER_MUTANT_ASSERTIONS",
        (("MUTANT", node, "MUTANT"),),
    )
    monkeypatch.setattr(
        canary_module,
        "CAP_S1_OBSERVER_MUTANT_TRANSFORMS",
        (("MUTANT", "scripts/ohf/fixture.py", "return False\n", "return True\n"),),
    )
    _install_cap_s1_mutation_unit_seams(
        canary_module,
        monkeypatch,
        source_root=source_root,
        target=target,
    )

    def _skipped(argv, **_kwargs):
        junit = Path(argv[argv.index("--junitxml") + 1])
        _write_cap_s1_mutation_junit(junit, outcome="SKIPPED")
        return _subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(canary_module, "_run_cap_s1_observer_process", _skipped)
    with pytest.raises(CapS1ResultError, match="mutation_proof_invalid"):
        _observe_cap_s1_mutations(exact_head="a" * 40, scratch_root=tmp_path)
    assert target.read_text(encoding="utf-8") == "return False\n"


@pytest.mark.parametrize("replacement", ("directory", "symlink"))
def test_cap_s1_observer_temp_root_refuses_replacement_before_ownership_change(
    tmp_path, monkeypatch, replacement
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    output_root = tmp_path / "observer-output"
    output_root.mkdir(mode=0o700)
    expected = output_root.lstat()
    original = tmp_path / "original-output"
    output_root.rename(original)
    if replacement == "directory":
        output_root.mkdir(mode=0o700)
    else:
        output_root.symlink_to(original, target_is_directory=True)

    descriptor_mutations = []
    monkeypatch.setattr(
        canary_module.os,
        "fchown",
        lambda *args: descriptor_mutations.append(args),
    )
    monkeypatch.setattr(
        canary_module.os,
        "chown",
        lambda *_args, **_kwargs: pytest.fail(
            "pathname ownership mutation is forbidden"
        ),
    )

    with pytest.raises(CapS1ResultError, match="source_observation_unavailable"):
        canary_module._bind_cap_s1_observer_temp_root(
            output_root,
            expected=expected,
            error="cap_s1_result_source_observation_unavailable",
        )
    assert descriptor_mutations == []


def test_cap_s1_observer_temp_root_normalizes_only_verified_descriptor(
    monkeypatch,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    def _state(gid):
        return os.stat_result(
            (stat.S_IFDIR | 0o700, 101, 202, 2, 501, gid, 0, 0, 0, 0)
        )

    expected = _state(20)
    normalized = _state(453)
    fstats = iter((expected, normalized))
    calls = []

    class _BoundPath:
        def __fspath__(self):
            return "/owned/observer-output"

        def lstat(self):
            calls.append(("lstat",))
            return normalized

    monkeypatch.setattr(canary_module.os, "getuid", lambda: 501)
    monkeypatch.setattr(canary_module.os, "getgid", lambda: 453)
    monkeypatch.setattr(
        canary_module.os,
        "open",
        lambda path, flags: calls.append(("open", os.fspath(path), flags)) or 91,
    )
    monkeypatch.setattr(canary_module.os, "fstat", lambda fd: next(fstats))
    monkeypatch.setattr(
        canary_module.os,
        "fchown",
        lambda fd, uid, gid: calls.append(("fchown", fd, uid, gid)),
    )
    monkeypatch.setattr(
        canary_module.os,
        "close",
        lambda fd: calls.append(("close", fd)),
    )
    monkeypatch.setattr(
        canary_module.os,
        "chown",
        lambda *_args, **_kwargs: pytest.fail(
            "pathname ownership mutation is forbidden"
        ),
    )

    observed = canary_module._bind_cap_s1_observer_temp_root(
        _BoundPath(),
        expected=expected,
        error="cap_s1_result_source_observation_unavailable",
    )

    assert observed == normalized
    assert calls[0][0:2] == ("open", "/owned/observer-output")
    assert calls[0][2] & os.O_DIRECTORY
    assert calls[0][2] & os.O_NOFOLLOW
    assert ("fchown", 91, 501, 453) in calls
    assert calls[-2:] == [("close", 91), ("lstat",)]


def test_cap_s1_owned_tree_cleanup_does_not_chmod_symlink_target(tmp_path) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    external_target = tmp_path / "external-executable"
    external_target.write_bytes(b"external executable bytes")
    external_target.chmod(0o755)
    owned_root = tmp_path / "owned-output"
    owned_root.mkdir(mode=0o700)
    (owned_root / "python-link").symlink_to(external_target)
    owned_root.chmod(0o500)

    assert canary_module._remove_tree(owned_root) is True
    assert not owned_root.exists()
    assert external_target.read_bytes() == b"external executable bytes"
    assert stat.S_IMODE(external_target.lstat().st_mode) == 0o755


def test_cap_s1_source_archive_omits_tracked_symlink_from_regular_blob_copy(
    tmp_path,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    archive = tmp_path / "source.tar"
    payload = b"verified regular source\n"
    with tarfile.open(archive, mode="w") as bundle:
        directory = tarfile.TarInfo("package")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        bundle.addfile(directory)
        regular = tarfile.TarInfo("package/module.py")
        regular.mode = 0o644
        regular.size = len(payload)
        bundle.addfile(regular, io.BytesIO(payload))
        symlink_parent = tarfile.TarInfo("vendor")
        symlink_parent.type = tarfile.DIRTYPE
        symlink_parent.mode = 0o755
        bundle.addfile(symlink_parent)
        tracked_link = tarfile.TarInfo("vendor/macro")
        tracked_link.type = tarfile.SYMTYPE
        tracked_link.linkname = "macro_src"
        bundle.addfile(tracked_link)

    destination = tmp_path / "source"
    destination.mkdir(mode=0o700)
    canary_module._extract_cap_s1_source_archive(archive, destination)

    assert (destination / "package/module.py").read_bytes() == payload
    assert not (destination / "vendor").exists()
    assert not (destination / "vendor/macro").exists()
    assert not (destination / "vendor/macro").is_symlink()


def _cap_s1_copy_bootstrap_source(destination: Path) -> tuple[_CapS1SourceCopyEntry, ...]:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    for top_level in ("scripts", "control_plane"):
        shutil.copytree(
            REPO_ROOT / top_level,
            destination / top_level,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    rows = []
    for _module, relative in canary_module._CAP_S1_PYTEST_SOURCE_MODULES:
        payload = (destination / relative).read_bytes()
        rows.append(
            _CapS1SourceCopyEntry(
                path=relative,
                mode="100644",
                blob=hashlib.sha1(
                    f"blob {len(payload)}\0".encode("ascii") + payload
                ).hexdigest(),
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    return tuple(rows)


def test_cap_s1_actual_pytest_bootstrap_binds_owned_source_and_ignores_ambient(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source = tmp_path / "owned-source"
    source.mkdir()
    manifest = _cap_s1_copy_bootstrap_source(source)
    poison = tmp_path / "ambient-editable"
    (poison / "scripts/ohf").mkdir(parents=True)
    (poison / "scripts/__init__.py").write_text("", encoding="utf-8")
    (poison / "scripts/ohf/__init__.py").write_text("", encoding="utf-8")
    (poison / "scripts/ohf/cap_s1_mastermind_operator_canary.py").write_text(
        "raise RuntimeError('ambient editable source imported')\n", encoding="utf-8"
    )
    monkeypatch.setenv("PYTHONPATH", str(poison))
    probe = tmp_path / "test_bootstrap_probe.py"
    probe.write_text("def test_bootstrap_probe():\n    assert True\n", encoding="utf-8")
    junit = tmp_path / "bootstrap.xml"
    interpreter = _capture_cap_s1_interpreter_identity()
    binding = canary_module._build_cap_s1_pytest_binding(
        source_root=source,
        source_manifest=manifest,
        interpreter=interpreter,
    )
    completed = _run_cap_s1_python_observer_process(
        interpreter,
        canary_module._cap_s1_pytest_argv(
            binding,
            ("-q", "--junitxml", str(junit), str(probe)),
        ),
        cwd=source,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert junit.exists()
    assert binding.bootstrap_sha256 == hashlib.sha256(
        canary_module._CAP_S1_PYTEST_BOOTSTRAP.encode("utf-8")
    ).hexdigest()


def test_cap_s1_actual_pytest_bootstrap_refuses_digest_drift_with_non_test_exit(
    tmp_path,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source = tmp_path / "owned-source"
    source.mkdir()
    manifest = _cap_s1_copy_bootstrap_source(source)
    interpreter = _capture_cap_s1_interpreter_identity()
    binding = canary_module._build_cap_s1_pytest_binding(
        source_root=source,
        source_manifest=manifest,
        interpreter=interpreter,
    )
    canary_path = source / "scripts/ohf/cap_s1_mastermind_operator_canary.py"
    original = canary_path.read_bytes()
    canary_path.write_bytes(original + b"\n# drift\n")
    probe = tmp_path / "test_bootstrap_probe.py"
    probe.write_text("def test_bootstrap_probe():\n    assert True\n", encoding="utf-8")
    junit = tmp_path / "bootstrap.xml"
    completed = _run_cap_s1_python_observer_process(
        interpreter,
        canary_module._cap_s1_pytest_argv(
            binding,
            ("-q", "--junitxml", str(junit), str(probe)),
        ),
        cwd=source,
        timeout=120,
    )
    assert completed.returncode == canary_module._CAP_S1_PYTEST_PROVENANCE_EXIT
    assert completed.returncode not in {0, 1}
    assert not junit.exists()
    canary_path.write_bytes(original)
    restored = _run_cap_s1_python_observer_process(
        interpreter,
        canary_module._cap_s1_pytest_argv(
            binding,
            ("-q", "--junitxml", str(junit), str(probe)),
        ),
        cwd=source,
        timeout=120,
    )
    assert restored.returncode == 0, restored.stderr


def _build_cap_s1_historical_git_repository(
    tmp_path: Path,
) -> tuple[Path, str, str, str, tuple[str, ...]]:
    repository = tmp_path / "historical-repository"
    repository.mkdir()
    _cap_s1_test_git(repository, "init", "--quiet")
    package_files = (
        ".codex-plugin/plugin.json",
        "references/app-bindings.template.json",
        "references/dialogue-boundary.md",
        "skills/escalate-decision/SKILL.md",
        "skills/finish-operation/SKILL.md",
        "skills/receive-commission/SKILL.md",
        "skills/return-progress/SKILL.md",
    )
    for relative in package_files:
        path = repository / "plugins/mastermind-operator" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"historical:{relative}\n", encoding="utf-8")
    for relative in (".agents/marker/metadata.txt", ".agents/repeated/metadata.txt"):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unrelated historical marker\n", encoding="utf-8")
    _cap_s1_test_git(repository, "add", "--all")
    _cap_s1_test_git(repository, "commit", "--quiet", "-m", "historical package")
    historical = _cap_s1_test_git(repository, "rev-parse", "HEAD")
    package_tree = _cap_s1_test_git(
        repository, "rev-parse", f"{historical}:plugins/mastermind-operator"
    )
    candidate_file = repository / "candidate.txt"
    candidate_file.write_text("current candidate\n", encoding="utf-8")
    _cap_s1_test_git(repository, "add", "candidate.txt")
    _cap_s1_test_git(repository, "commit", "--quiet", "-m", "candidate")
    candidate = _cap_s1_test_git(repository, "rev-parse", "HEAD")
    return repository, candidate, historical, package_tree, package_files


def test_cap_s1_owned_git_context_is_finite_detached_and_removable(tmp_path) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, candidate, historical, package_tree, package_files = (
        _build_cap_s1_historical_git_repository(tmp_path)
    )
    source = tmp_path / "owned-source"
    source.mkdir()
    cleanup = []
    context = canary_module._install_cap_s1_owned_git_context(
        source_repository_root=repository,
        source_root=source,
        exact_head=candidate,
        historical_commit=historical,
        expected_package_tree=package_tree,
        expected_package_files=package_files,
        cleanup_observations=cleanup,
    )
    assert len(context.object_manifest) == 22
    assert sum(row[1] == "commit" for row in context.object_manifest) == 2
    assert sum(row[1] == "tree" for row in context.object_manifest) == 13
    assert sum(row[1] == "blob" for row in context.object_manifest) == 7
    marker_tree = _cap_s1_test_git(
        repository, "rev-parse", f"{historical}:.agents/marker"
    )
    repeated_tree = _cap_s1_test_git(
        repository, "rev-parse", f"{historical}:.agents/repeated"
    )
    marker_blob = _cap_s1_test_git(
        repository, "rev-parse", f"{historical}:.agents/marker/metadata.txt"
    )
    assert marker_tree == repeated_tree
    assert marker_tree in {row[0] for row in context.object_manifest}
    assert marker_blob not in {row[0] for row in context.object_manifest}
    expected_archive_diagnostic = (
        f"error: invalid object 100644 {marker_blob} for "
        "'.agents/marker/metadata.txt'\n"
    )
    assert context.archive_diagnostic == expected_archive_diagnostic
    assert context.archive_diagnostic_digest == hashlib.sha256(
        expected_archive_diagnostic.encode("utf-8")
    ).hexdigest()
    path_rows = {
        (path, object_id)
        for path, object_id, _size in context.historical_tree_path_manifest
    }
    assert (".agents/marker", marker_tree) in path_rows
    assert (".agents/repeated", marker_tree) in path_rows
    expected_archive = []
    for relative in package_files:
        path = repository / "plugins/mastermind-operator" / relative
        payload = path.read_bytes()
        expected_archive.append(
            (
                f"plugins/mastermind-operator/{relative}",
                len(payload),
                hashlib.sha256(payload).hexdigest(),
            )
        )
    assert context.archive_file_manifest == tuple(sorted(expected_archive))
    assert len(context.filesystem_manifest) == 5
    assert {row[0] for row in context.filesystem_manifest} == {
        "HEAD",
        "config",
        *(
            path.relative_to(source / ".git").as_posix()
            for path in (source / ".git/objects/pack").iterdir()
        ),
    }
    assert _cap_s1_test_git(source, "rev-parse", "HEAD") == candidate
    assert _cap_s1_test_git(
        source, "rev-parse", f"{historical}:plugins/mastermind-operator"
    ) == package_tree
    assert _cap_s1_test_git(source, "for-each-ref") == ""
    assert not (source / ".git/hooks").exists()
    assert not (source / ".git/objects/info/alternates").exists()
    assert "fetch" not in " ".join(context.command_registry)
    canary_module._verify_cap_s1_owned_git_context(context)
    canary_module._remove_cap_s1_owned_git_context(
        context,
        cleanup_observations=cleanup,
    )
    assert not (source / ".git").exists()
    assert cleanup and all(row.removed and row.verified_absent for row in cleanup)


def test_cap_s1_owned_git_context_refuses_missing_packed_object(tmp_path) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, candidate, historical, package_tree, package_files = (
        _build_cap_s1_historical_git_repository(tmp_path)
    )
    source = tmp_path / "owned-source"
    source.mkdir()
    context = canary_module._install_cap_s1_owned_git_context(
        source_repository_root=repository,
        source_root=source,
        exact_head=candidate,
        historical_commit=historical,
        expected_package_tree=package_tree,
        expected_package_files=package_files,
    )
    pack = next((source / ".git/objects/pack").glob("*.pack"))
    pack.parent.chmod(0o700)
    pack.chmod(0o600)
    pack.unlink()
    with pytest.raises(CapS1ResultError, match="owned_git_invalid"):
        canary_module._verify_cap_s1_owned_git_context(context)
    canary_module._remove_cap_s1_owned_git_context(context)


def test_cap_s1_owned_git_context_refuses_missing_historical_sibling_tree(
    tmp_path,
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, candidate, historical, package_tree, package_files = (
        _build_cap_s1_historical_git_repository(tmp_path)
    )
    marker_tree = _cap_s1_test_git(
        repository, "rev-parse", f"{historical}:.agents/marker"
    )
    loose_tree = repository / ".git/objects" / marker_tree[:2] / marker_tree[2:]
    assert loose_tree.is_file()
    loose_tree.unlink()
    source = tmp_path / "owned-source"
    source.mkdir()
    with pytest.raises(CapS1ResultError, match="owned_git_invalid"):
        canary_module._install_cap_s1_owned_git_context(
            source_repository_root=repository,
            source_root=source,
            exact_head=candidate,
            historical_commit=historical,
            expected_package_tree=package_tree,
            expected_package_files=package_files,
        )
    assert not (source / ".git").exists()


def test_cap_s1_owned_git_context_refuses_credential_config_drift(tmp_path) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, candidate, historical, package_tree, package_files = (
        _build_cap_s1_historical_git_repository(tmp_path)
    )
    source = tmp_path / "owned-source"
    source.mkdir()
    context = canary_module._install_cap_s1_owned_git_context(
        source_repository_root=repository,
        source_root=source,
        exact_head=candidate,
        historical_commit=historical,
        expected_package_tree=package_tree,
        expected_package_files=package_files,
    )
    config = source / ".git/config"
    config.chmod(0o600)
    with config.open("a", encoding="ascii") as handle:
        handle.write("\n[credential]\n\thelper = hostile\n")
    config.chmod(0o400)
    with pytest.raises(CapS1ResultError, match="owned_git_invalid"):
        canary_module._verify_cap_s1_owned_git_context(context)
    canary_module._remove_cap_s1_owned_git_context(context)


def test_cap_s1_observer_process_and_junit_parser_short_fixture_seam(tmp_path) -> None:
    cleanup = []
    completed = _run_cap_s1_observer_process(
        (
            _sys.executable,
            "-I",
            "-c",
            "import os,pathlib,stat; "
            "assert 'PYTHONPATH' not in os.environ; "
            "assert '/usr/sbin' in os.environ['PATH'].split(os.pathsep); "
            "temp_root=pathlib.Path(os.environ['TMPDIR']); "
            "temp_state=temp_root.lstat(); "
            "assert stat.S_ISDIR(temp_state.st_mode); "
            "assert not stat.S_ISLNK(temp_state.st_mode); "
            "assert stat.S_IMODE(temp_state.st_mode)==0o700; "
            "assert temp_state.st_uid==os.getuid(); "
            "assert temp_state.st_gid==os.getgid(); "
            "print('fixture-ok')",
        ),
        cwd=tmp_path,
        timeout=30,
        cleanup_observations=cleanup,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "fixture-ok"
    assert len(cleanup) == 2
    assert all(row.removed and row.verified_absent for row in cleanup)
    assert len({row.identity_digest for row in cleanup}) == 2

    junit = tmp_path / "fixture.xml"
    junit.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="test_fixture_scope.Example" name="test_ok" />'
        "</testsuite>",
        encoding="utf-8",
    )
    junit.chmod(0o444)
    assert _parse_cap_s1_junit(
        junit,
        expected_scope=("tests/test_fixture_scope.py",),
    ) == (("tests/test_fixture_scope.py", 1, 0, 0, 0),)


def test_cap_s1_observer_environment_is_closed_across_all_process_call_sites(
    tmp_path, monkeypatch
) -> None:
    poisoned_tmp = tmp_path / "ambient-poison"
    poisoned_tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(poisoned_tmp))
    monkeypatch.setenv("PYTHONPATH", "/ambient/python/path")
    child = (
        "import os,pathlib,stat; "
        "assert 'PYTHONPATH' not in os.environ; "
        f"assert os.environ['TMPDIR']!={str(poisoned_tmp)!r}; "
        "assert '/usr/sbin' in os.environ['PATH'].split(os.pathsep); "
        "root=pathlib.Path(os.environ['TMPDIR']); state=root.lstat(); "
        "assert stat.S_ISDIR(state.st_mode) and not stat.S_ISLNK(state.st_mode); "
        "assert stat.S_IMODE(state.st_mode)==0o700; "
        "assert state.st_uid==os.getuid() and state.st_gid==os.getgid(); "
        "print('closed-environment-ok')"
    )

    for github_environment in (False, True):
        cleanup = []
        completed = _run_cap_s1_observer_process(
            (_sys.executable, "-I", "-c", child),
            cwd=tmp_path,
            timeout=30,
            cleanup_observations=cleanup,
            github_environment=github_environment,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "closed-environment-ok"
        assert len(cleanup) == 2
        assert all(row.removed and row.verified_absent for row in cleanup)

    byte_cleanup = []
    completed_bytes = _run_cap_s1_observer_bytes(
        (_sys.executable, "-I", "-c", child),
        cwd=tmp_path,
        timeout=30,
        maximum_stream_bytes=4096,
        cleanup_observations=byte_cleanup,
    )
    assert completed_bytes.returncode == 0, completed_bytes.stderr
    assert completed_bytes.stdout.strip() == b"closed-environment-ok"
    assert len(byte_cleanup) == 2
    assert all(row.removed and row.verified_absent for row in byte_cleanup)
    assert cap_s1_observer_registry()["environment_keys"] == (
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_NO_LAZY_FETCH",
        "GIT_OPTIONAL_LOCKS",
        "GIT_TERMINAL_PROMPT",
        "LANG",
        "LC_ALL",
        "OHF_FAKE_STATE",
        "PATH",
        "PYTEST_ADDOPTS",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "TMPDIR",
    )


def test_cap_s1_actual_junit_parser_rows_are_accepted_by_result_consumer(
    tmp_path,
) -> None:
    cases = []
    sorted_scopes = tuple(sorted(CAP_S1_OBSERVER_TEST_MODULES))
    for index, scope in enumerate(sorted_scopes):
        module = Path(scope).stem
        cases.append(
            f'<testcase classname="{module}.Fixture" name="test_pass_{index}" />'
        )
        if index == len(sorted_scopes) - 1:
            cases.extend(
                f'<testcase classname="{module}.Fixture" name="test_skip_{offset}">'
                '<skipped message="fixed skip" /></testcase>'
                for offset in range(2)
            )
    junit = tmp_path / "actual-scopes.xml"
    junit.write_text(
        '<testsuite tests="19" failures="0" errors="0" skipped="2">'
        + "".join(cases)
        + "</testsuite>",
        encoding="utf-8",
    )
    junit.chmod(0o444)
    parsed = _parse_cap_s1_junit(
        junit,
        expected_scope=CAP_S1_OBSERVER_TEST_MODULES,
    )
    raw = _happy_cap_s1_result_kwargs()
    assert parsed == raw["local_proof"]["suite_manifest"]
    assert build_cap_s1_result(**raw).local_proof.suite_manifest == parsed


@pytest.mark.parametrize(
    "hostile",
    ("traversal", "absolute", "unknown", "duplicate", "missing", "extra"),
)
def test_cap_s1_result_refuses_nonexact_local_scope_inventory(hostile) -> None:
    raw = _happy_cap_s1_result_kwargs()
    rows = list(raw["local_proof"]["suite_manifest"])
    if hostile == "traversal":
        rows[0] = ("../tests/test_escape.py", *rows[0][1:])
    elif hostile == "absolute":
        rows[0] = ("/tests/test_escape.py", *rows[0][1:])
    elif hostile == "unknown":
        rows[0] = ("tests/test_unknown.py", *rows[0][1:])
    elif hostile == "duplicate":
        rows[0] = (rows[1][0], *rows[0][1:])
    elif hostile == "missing":
        rows.pop()
    else:
        rows.append(("tests/test_extra.py", 1, 0, 0, 0))
    rows = sorted(rows)
    raw["local_proof"].update(
        suite_manifest=tuple(rows),
        suite_count=len(rows),
        passed=sum(row[1] for row in rows),
        skipped=sum(row[2] for row in rows),
        failed=sum(row[3] for row in rows),
        cancelled=sum(row[4] for row in rows),
        total=sum(sum(row[1:]) for row in rows),
    )
    _refresh_result_receipt_digest(raw, "local_proof", "CapS1LocalProofReceipt")
    with pytest.raises(CapS1ResultError, match="local_proof_invalid"):
        build_cap_s1_result(**raw)


def test_cap_s1_observer_process_timeout_kills_owned_descendant(tmp_path) -> None:
    marker = tmp_path / "descendant.pid"
    child_script = "import time; time.sleep(30)"
    parent_script = (
        "import pathlib,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-I','-c',{child_script!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(marker)!r}).write_text(str(p.pid),encoding='ascii'); "
        "time.sleep(30)"
    )
    with pytest.raises(CapS1ResultError, match="source_observation_unavailable"):
        _run_cap_s1_observer_process(
            (_sys.executable, "-I", "-c", parent_script),
            cwd=tmp_path,
            timeout=0.5,
        )
    descendant_pid = int(marker.read_text(encoding="ascii"))
    try:
        os.kill(descendant_pid, 0)
    except ProcessLookupError:
        survived = False
    else:
        survived = True
        os.kill(descendant_pid, 9)  # cleanup only our test-owned process on RED
    assert not survived


def test_cap_s1_observer_process_enforces_prebound_output_limit(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    monkeypatch.setattr(canary_module, "_CAP_S1_OBSERVER_MAX_OUTPUT_BYTES", 1024)
    with pytest.raises(CapS1ResultError, match="source_observation_unavailable"):
        _run_cap_s1_observer_process(
            (_sys.executable, "-I", "-c", "import os; os.write(1,b'x'*4096)"),
            cwd=tmp_path,
            timeout=30,
        )


def test_cap_s1_observer_process_preserves_replaced_output_root(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    output_root = tmp_path / "observer-process-output"
    original_root = tmp_path / "original-observer-process-output"
    sentinel = output_root / "foreign-sentinel"

    def _owned_process(_argv, *, stdout_path, **_kwargs):
        stdout_path.parent.rename(original_root)
        output_root.mkdir()
        sentinel.write_text("preserve replacement\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        canary_module.tempfile,
        "mkdtemp",
        lambda *_args, **_kwargs: str(
            output_root.mkdir(mode=0o700) or output_root
        ),
    )
    monkeypatch.setattr(canary_module, "_run_cap_s1_owned_process", _owned_process)
    with pytest.raises(CapS1ResultError, match="source_observation_unavailable"):
        _run_cap_s1_observer_process(("fixed",), cwd=tmp_path, timeout=30)
    assert sentinel.read_text(encoding="utf-8") == "preserve replacement\n"


def test_cap_s1_observer_bytes_preserves_replaced_output_root(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    output_root = tmp_path / "observer-bytes-output"
    original_root = tmp_path / "original-observer-bytes-output"
    sentinel = output_root / "foreign-sentinel"

    def _owned_process(_argv, *, stdout_path, **_kwargs):
        stdout_path.parent.rename(original_root)
        output_root.mkdir()
        sentinel.write_text("preserve byte replacement\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(
        canary_module.tempfile,
        "mkdtemp",
        lambda *_args, **_kwargs: str(
            output_root.mkdir(mode=0o700) or output_root
        ),
    )
    monkeypatch.setattr(canary_module, "_run_cap_s1_owned_process", _owned_process)
    with pytest.raises(CapS1ResultError, match="source_copy_invalid"):
        _run_cap_s1_observer_bytes(
            ("fixed",),
            cwd=tmp_path,
            timeout=30,
            maximum_stream_bytes=1024,
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve byte replacement\n"


def test_cap_s1_python_observer_uses_lexical_entrypoint_isolation_and_no_pycache(
    tmp_path,
) -> None:
    module = tmp_path / "cap_s1_import_probe.py"
    module.write_text("VALUE = 'owned-source'\n", encoding="utf-8")
    identity = _capture_cap_s1_interpreter_identity()
    completed = _run_cap_s1_python_observer_process(
        identity,
        (
            "-c",
            "import json,os,pathlib,sys; "
            "sys.path.insert(0, os.getcwd()); "
            "import cap_s1_import_probe as probe; "
            "print(json.dumps({'value':probe.VALUE,'isolated':sys.flags.isolated,"
            "'dont_write_bytecode':sys.dont_write_bytecode,"
            "'pythonhashseed':os.environ.get('PYTHONHASHSEED')}))",
        ),
        cwd=tmp_path,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    assert completed.args[:3] == [identity.entrypoint_path, "-I", "-B"]
    assert payload == {
        "value": "owned-source",
        "isolated": 1,
        "dont_write_bytecode": True,
        "pythonhashseed": None,
    }
    assert not (tmp_path / "__pycache__").exists()


_CAP_S1_FAKE_CHILD_FIXTURE_PATHS = (
    "scripts/__init__.py",
    "scripts/ohf/__init__.py",
    "scripts/ohf/fake_app_server.py",
    "scripts/ohf/fake_codex_binary.py",
    "scripts/ohf/fixtures/__init__.py",
    "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
    "plugins/mastermind-operator/.codex-plugin/plugin.json",
    "plugins/mastermind-operator/references/app-bindings.template.json",
    "plugins/mastermind-operator/references/dialogue-boundary.md",
    "plugins/mastermind-operator/skills/escalate-decision/SKILL.md",
    "plugins/mastermind-operator/skills/finish-operation/SKILL.md",
    "plugins/mastermind-operator/skills/receive-commission/SKILL.md",
    "plugins/mastermind-operator/skills/return-progress/SKILL.md",
)


def _cap_s1_verify_selected_fake_child_fixture(
    source_root: Path,
    manifest: tuple[_CapS1SourceCopyEntry, ...],
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    assert tuple(entry.path for entry in manifest) == _CAP_S1_FAKE_CHILD_FIXTURE_PATHS
    canary_module._verify_cap_s1_owned_source_manifest(
        source_root=source_root,
        manifest=manifest,
    )
    for entry in manifest:
        candidate = source_root / entry.path
        state = candidate.lstat()
        expected_mode = 0o755 if entry.mode == "100755" else 0o644
        assert stat.S_ISREG(state.st_mode)
        assert not candidate.is_symlink()
        assert stat.S_IMODE(state.st_mode) == expected_mode
        assert state.st_size == entry.size
        assert hashlib.sha256(candidate.read_bytes()).hexdigest() == entry.sha256


def _cap_s1_copy_selected_fake_child_fixture(
    source_root: Path,
) -> tuple[_CapS1SourceCopyEntry, ...]:
    rows = []
    total_bytes = 0
    for relative in _CAP_S1_FAKE_CHILD_FIXTURE_PATHS:
        origin = REPO_ROOT / relative
        before = origin.lstat()
        mode = stat.S_IMODE(before.st_mode)
        assert stat.S_ISREG(before.st_mode)
        assert not origin.is_symlink()
        assert mode in {0o644, 0o755}
        assert 0 < before.st_size <= 1024 * 1024
        payload = origin.read_bytes()
        after = origin.lstat()
        assert (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        assert len(payload) == before.st_size
        total_bytes += len(payload)
        assert total_bytes <= 2 * 1024 * 1024
        destination = source_root / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_bytes(payload)
        destination.chmod(mode)
        git_blob = hashlib.sha1()
        git_blob.update(f"blob {len(payload)}\0".encode("ascii"))
        git_blob.update(payload)
        rows.append(
            _CapS1SourceCopyEntry(
                path=relative,
                mode="100755" if mode == 0o755 else "100644",
                blob=git_blob.hexdigest(),
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    manifest = tuple(rows)
    _cap_s1_verify_selected_fake_child_fixture(source_root, manifest)
    return manifest


def test_cap_s1_fake_child_bytecode_binding_prevents_owned_source_residue(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    exact_head = _cap_s1_test_git(REPO_ROOT, "rev-parse", "HEAD")
    exact_tree = _cap_s1_test_git(REPO_ROOT, "rev-parse", "HEAD^{tree}")
    original_configure = canary_module._configure_canary_backend
    original_resolve_repo_git_dir = canary_module._resolve_repo_git_dir

    def run_actual_fake_process(label: str, *, omit_binding: bool) -> None:
        outer = tmp_path / label
        outer.mkdir(mode=0o700)
        outer_state = outer.lstat()
        owned_roots = [
            _register_cap_s1_owned_root(outer, kind="observer-scratch")
        ]
        process_cleanup = []
        copy_root = outer / "source-copy"
        copy_root.mkdir(mode=0o700)
        owned_roots.append(
            _register_cap_s1_owned_root(copy_root, kind="observer-source")
        )
        source_root = copy_root / "verified-source"
        source_root.mkdir(mode=0o700)
        owned_roots.append(
            _register_cap_s1_owned_root(source_root, kind="observer-source")
        )
        source_manifest = _cap_s1_copy_selected_fake_child_fixture(source_root)
        existing_git_dir = original_resolve_repo_git_dir(REPO_ROOT)
        historical_commit, historical_tree, _historical_files = (
            canary_module._cap_s1_owned_git_package_expectation(source_root)
        )
        assert _cap_s1_test_git(REPO_ROOT, "rev-parse", "HEAD^{commit}") == exact_head
        assert _cap_s1_test_git(REPO_ROOT, "rev-parse", "HEAD^{tree}") == exact_tree
        assert (
            _cap_s1_test_git(
                REPO_ROOT,
                "rev-parse",
                f"{historical_commit}:plugins/mastermind-operator",
            )
            == historical_tree
        )

        def resolve_existing_git_dir(repo_root: Path) -> Path:
            if Path(repo_root) == source_root:
                return existing_git_dir
            return original_resolve_repo_git_dir(repo_root)

        monkeypatch.setattr(
            canary_module,
            "_resolve_repo_git_dir",
            resolve_existing_git_dir,
        )
        canary_scratch = outer / "canary-scratch"
        canary_scratch.mkdir(mode=0o700)
        owned_roots.append(
            _register_cap_s1_owned_root(canary_scratch, kind="observer-scratch")
        )

        if omit_binding:
            def configure_without_bytecode_binding(**kwargs):
                configured = original_configure(**kwargs)
                extra_env = dict(configured.extra_env)
                extra_env.pop("PYTHONDONTWRITEBYTECODE", None)
                return dataclasses.replace(configured, extra_env=extra_env)

            monkeypatch.setattr(
                canary_module,
                "_configure_canary_backend",
                configure_without_bytecode_binding,
            )
        else:
            monkeypatch.setattr(
                canary_module,
                "_configure_canary_backend",
                original_configure,
            )

        try:
            evidence = canary_module.run_canary(
                backend="fake",
                binary_path=source_root / "scripts/ohf/fake_codex_binary.py",
                codex_home=None,
                repo_root=source_root,
                scratch_root=canary_scratch,
                operation_id=f"cap-s1-fake-child-bytecode-{label}",
                protected_join="c" * 40,
                client_factory=canary_module._default_fake_client_factory,
            )
            assert evidence.launch_decision == LaunchDecision.ALLOW.value
            assert len(evidence.cleanup.artifacts) == 7
            assert all(removed and absent for _kind, removed, absent in evidence.cleanup.artifacts)
            cache_directories = tuple(
                sorted(
                    path.relative_to(source_root).as_posix()
                    for path in source_root.rglob("__pycache__")
                    if path.is_dir()
                )
            )
            if omit_binding:
                assert "scripts/__pycache__" in cache_directories
                with pytest.raises(CapS1ResultError, match="source_copy_invalid"):
                    canary_module._verify_cap_s1_owned_source_manifest(
                        source_root=source_root,
                        manifest=source_manifest,
                    )
            else:
                assert cache_directories == ()
                _cap_s1_verify_selected_fake_child_fixture(
                    source_root,
                    source_manifest,
                )
        finally:
            cleanup_rows = _finalize_cap_s1_observer_cleanup(
                scratch_path=outer,
                scratch_device=outer_state.st_dev,
                scratch_inode=outer_state.st_ino,
                owned_roots=owned_roots,
                process_cleanup=process_cleanup,
                require_complete=False,
            )
            assert cleanup_rows
            assert all(removed and absent for _kind, _digest, removed, absent in cleanup_rows)
            assert process_cleanup == []
            assert not outer.exists()

    run_actual_fake_process("binding-omitted", omit_binding=True)
    run_actual_fake_process("binding-fixed", omit_binding=False)


def test_cap_s1_interpreter_identity_binds_entrypoint_target_and_venv_config(
    tmp_path,
) -> None:
    venv = tmp_path / "venv"
    entrypoint = venv / "bin/python"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.symlink_to(Path(_sys.executable).resolve())
    config = venv / "pyvenv.cfg"
    config.write_text("home = /owned/base\n", encoding="utf-8")
    identity = _capture_cap_s1_interpreter_identity(
        entrypoint=str(entrypoint),
        prefix=str(venv),
        base_prefix="/owned/base",
    )
    assert identity.entrypoint_path == str(entrypoint.absolute())
    assert identity.resolved_target_path == str(Path(_sys.executable).resolve())
    assert identity.venv_config_path == str(config)
    _revalidate_cap_s1_interpreter_identity(identity)

    config.write_text("home = /replaced/base\n", encoding="utf-8")
    with pytest.raises(CapS1ResultError, match="interpreter_identity_changed"):
        _revalidate_cap_s1_interpreter_identity(identity)


def _build_cap_s1_cleanup_fixture(
    root: Path,
) -> tuple[_CapS1OwnedRootIdentity, ...]:
    owned_roots = [_register_cap_s1_owned_root(root, kind="observer-scratch")]
    for relative, kind in (
        ("mutant-0", "observer-mutants"),
        ("mutant-1", "observer-mutants"),
        ("mutant-2", "observer-mutants"),
        ("output", "observer-output"),
        ("source-copy", "observer-source"),
        ("source-copy/verified-source", "observer-source"),
        ("secret-scan", "observer-scratch"),
        ("secret-scan/supply", "secret-supply"),
        ("secret-scan/source", "secret-source"),
        ("secret-scan/controls", "secret-controls"),
        ("secret-scan/source-run", "secret-output"),
    ):
        directory = root / relative
        directory.mkdir()
        owned_roots.append(_register_cap_s1_owned_root(directory, kind=kind))
        (directory / "owned.fixture").write_bytes(relative.encode("utf-8"))
    return tuple(owned_roots)


def test_cap_s1_observer_cleanup_returns_actual_fixed_resource_observations(
    tmp_path,
) -> None:
    scratch = tmp_path / "observer-scratch"
    scratch.mkdir()
    owned_roots = _build_cap_s1_cleanup_fixture(scratch)
    identity = scratch.stat()
    process_cleanup = (
        _CapS1OwnedProcessCleanupObservation(
            identity_digest="a" * 64,
            removed=True,
            verified_absent=True,
        ),
    )
    rows = _finalize_cap_s1_observer_cleanup(
        scratch_path=scratch,
        scratch_device=identity.st_dev,
        scratch_inode=identity.st_ino,
        process_cleanup=process_cleanup,
        owned_roots=owned_roots,
    )
    assert tuple(row[0] for row in rows) == (
        "observer-mutants",
        "observer-output",
        "observer-processes",
        "observer-scratch",
        "observer-source",
        "secret-controls",
        "secret-output",
        "secret-source",
        "secret-supply",
    )
    assert all(row[2:] == (True, True) for row in rows)
    assert not scratch.exists()


def test_cap_s1_observer_cleanup_failure_refuses_without_false_receipt(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    scratch = tmp_path / "observer-scratch"
    scratch.mkdir()
    owned_roots = _build_cap_s1_cleanup_fixture(scratch)
    identity = scratch.stat()
    monkeypatch.setattr(
        canary_module,
        "_cleanup_owned_dir_action",
        lambda *_args, **_kwargs: (False, False),
    )
    with pytest.raises(CapS1ResultError, match="source_observer_cleanup_failed"):
        _finalize_cap_s1_observer_cleanup(
            scratch_path=scratch,
            scratch_device=identity.st_dev,
            scratch_inode=identity.st_ino,
            owned_roots=owned_roots,
            process_cleanup=(
                _CapS1OwnedProcessCleanupObservation(
                    identity_digest="a" * 64,
                    removed=True,
                    verified_absent=True,
                ),
            ),
        )
    assert scratch.exists()


def test_cap_s1_observer_cleanup_refuses_untracked_owned_resource(
    tmp_path,
) -> None:
    scratch = tmp_path / "observer-scratch"
    scratch.mkdir()
    owned_roots = _build_cap_s1_cleanup_fixture(scratch)
    (scratch / "unexpected-resource").mkdir()
    identity = scratch.stat()
    with pytest.raises(CapS1ResultError, match="source_observer_cleanup_failed"):
        _finalize_cap_s1_observer_cleanup(
            scratch_path=scratch,
            scratch_device=identity.st_dev,
            scratch_inode=identity.st_ino,
            owned_roots=owned_roots,
            process_cleanup=(
                _CapS1OwnedProcessCleanupObservation(
                    identity_digest="a" * 64,
                    removed=True,
                    verified_absent=True,
                ),
            ),
        )


def test_cap_s1_observer_cleanup_preserves_replaced_supply_identity(
    tmp_path,
) -> None:
    scratch = tmp_path / "observer-scratch"
    scratch.mkdir()
    owned_roots = _build_cap_s1_cleanup_fixture(scratch)
    identity = scratch.stat()
    supply = scratch / "secret-scan/supply"
    owned_supply = tmp_path / "original-owned-supply"
    supply.rename(owned_supply)
    supply.mkdir()
    sentinel = supply / "foreign-sentinel"
    sentinel.write_text("preserve replacement\n", encoding="utf-8")
    with pytest.raises(CapS1ResultError, match="source_observer_cleanup_failed"):
        _finalize_cap_s1_observer_cleanup(
            scratch_path=scratch,
            scratch_device=identity.st_dev,
            scratch_inode=identity.st_ino,
            owned_roots=owned_roots,
            process_cleanup=(
                _CapS1OwnedProcessCleanupObservation(
                    identity_digest="a" * 64,
                    removed=True,
                    verified_absent=True,
                ),
            ),
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve replacement\n"
    assert scratch.exists()


def test_cap_s1_observer_early_failure_cleanup_preserves_replaced_identity(
    tmp_path,
) -> None:
    scratch = tmp_path / "observer-scratch"
    scratch.mkdir()
    scratch_identity = scratch.stat()
    owned_roots = [_register_cap_s1_owned_root(scratch, kind="observer-scratch")]
    secret_root = scratch / "secret-scan"
    secret_root.mkdir()
    owned_roots.append(_register_cap_s1_owned_root(secret_root, kind="observer-scratch"))
    supply = secret_root / "supply"
    supply.mkdir()
    owned_roots.append(_register_cap_s1_owned_root(supply, kind="secret-supply"))
    supply.rename(tmp_path / "original-owned-supply")
    supply.mkdir()
    sentinel = supply / "foreign-sentinel"
    sentinel.write_text("preserve after early failure\n", encoding="utf-8")
    with pytest.raises(CapS1ResultError, match="source_observer_cleanup_failed"):
        _finalize_cap_s1_observer_cleanup(
            scratch_path=scratch,
            scratch_device=scratch_identity.st_dev,
            scratch_inode=scratch_identity.st_ino,
            owned_roots=tuple(owned_roots),
            process_cleanup=(),
            require_complete=False,
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve after early failure\n"


def test_cap_s1_source_observer_early_failure_preserves_replaced_identity(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    scratch = tmp_path / "source-observer"
    source_identity = ("a" * 40, "b" * 40, "c" * 40)
    evidence = _completed_canary_evidence(
        head=source_identity[0],
        tree=source_identity[1],
        attempt_id="source-observer-early-failure",
        protected_join=source_identity[2],
    )
    monkeypatch.setattr(
        canary_module,
        "_capture_cap_s1_source_identity",
        lambda **_kwargs: source_identity,
    )
    monkeypatch.setattr(
        canary_module,
        "_capture_cap_s1_interpreter_identity",
        lambda: object(),
    )
    monkeypatch.setattr(
        canary_module.tempfile,
        "mkdtemp",
        lambda *_args, **_kwargs: str(scratch.mkdir() or scratch),
    )

    def _fail_after_replacement(*, scratch_root, owned_roots, **_kwargs):
        secret_root = scratch_root / "secret-scan"
        secret_root.mkdir()
        owned_roots.append(
            _register_cap_s1_owned_root(secret_root, kind="observer-scratch")
        )
        supply = secret_root / "supply"
        supply.mkdir()
        owned_roots.append(
            _register_cap_s1_owned_root(supply, kind="secret-supply")
        )
        supply.rename(tmp_path / "original-source-observer-supply")
        supply.mkdir()
        (supply / "foreign-sentinel").write_text(
            "preserve source observer replacement\n",
            encoding="utf-8",
        )
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")

    monkeypatch.setattr(
        canary_module,
        "_owned_cap_s1_source_copy",
        _fail_after_replacement,
    )
    with pytest.raises(CapS1ResultError, match="source_observer_cleanup_failed"):
        _run_cap_s1_source_observer(
            canary=evidence,
            canary_provenance="LIVE_DEFAULT_APP_SERVER",
            hosted_run_id="1",
            review_id="1",
        )
    assert (scratch / "secret-scan/supply/foreign-sentinel").read_text(
        encoding="utf-8"
    ) == "preserve source observer replacement\n"


def _cap_s1_source_manifest_fixture(source_root: Path) -> tuple[_CapS1SourceCopyEntry, ...]:
    payload = b"verified source bytes\n"
    path = source_root / "package/module.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    git_blob = hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload
    ).hexdigest()
    return (
        _CapS1SourceCopyEntry(
            path="package/module.py",
            mode="100644",
            blob=git_blob,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )


def test_cap_s1_post_observation_revalidation_accepts_stable_exact_source(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest = _cap_s1_source_manifest_fixture(source_root)
    before = ("a" * 40, "b" * 40, "c" * 40)
    monkeypatch.setattr(
        canary_module,
        "_capture_cap_s1_source_identity",
        lambda **_kwargs: before,
    )
    _revalidate_cap_s1_observer_source(
        before=before,
        source_root=source_root,
        source_manifest=manifest,
    )


@pytest.mark.parametrize("changed_index", (0, 1, 2))
def test_cap_s1_post_observation_revalidation_refuses_identity_drift(
    tmp_path, monkeypatch, changed_index
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest = _cap_s1_source_manifest_fixture(source_root)
    before = ("a" * 40, "b" * 40, "c" * 40)
    changed = list(before)
    changed[changed_index] = "d" * 40
    monkeypatch.setattr(
        canary_module,
        "_capture_cap_s1_source_identity",
        lambda **_kwargs: tuple(changed),
    )
    with pytest.raises(CapS1ResultError, match="source_identity_changed"):
        _revalidate_cap_s1_observer_source(
            before=before,
            source_root=source_root,
            source_manifest=manifest,
        )


@pytest.mark.parametrize("drift", ("bytes", "extra-file", "extra-directory"))
def test_cap_s1_post_observation_revalidation_refuses_owned_source_drift(
    tmp_path, monkeypatch, drift
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    source_root = tmp_path / "source"
    source_root.mkdir()
    manifest = _cap_s1_source_manifest_fixture(source_root)
    before = ("a" * 40, "b" * 40, "c" * 40)
    monkeypatch.setattr(
        canary_module,
        "_capture_cap_s1_source_identity",
        lambda **_kwargs: before,
    )
    if drift == "bytes":
        (source_root / "package/module.py").write_bytes(b"changed source bytes\n")
    elif drift == "extra-file":
        (source_root / "package/extra.py").write_text("extra\n", encoding="utf-8")
    else:
        (source_root / "package/extra").mkdir()
    with pytest.raises(CapS1ResultError, match="source_copy_invalid"):
        _revalidate_cap_s1_observer_source(
            before=before,
            source_root=source_root,
            source_manifest=manifest,
        )


def test_cap_s1_secret_scan_policy_registry_is_exact_and_unobserved() -> None:
    registry = cap_s1_observer_registry()
    supply = registry["secret_supply"]
    assert supply["version"] == CAP_S1_GITLEAKS_VERSION == "8.30.1"
    assert supply["source_commit"] == CAP_S1_GITLEAKS_SOURCE_COMMIT
    assert supply["archive"][1:] == (
        CAP_S1_GITLEAKS_ARCHIVE_BYTES,
        CAP_S1_GITLEAKS_ARCHIVE_SHA256,
    )
    assert supply["rule"][2:] == (
        CAP_S1_GITLEAKS_RULE_SHA256,
        CAP_S1_GITLEAKS_RULE_COUNT,
    )
    assert supply["archive_members"] == CAP_S1_GITLEAKS_ARCHIVE_MEMBERS
    assert supply["binary_sha256"] == "UNOBSERVED"
    assert supply["binary_version"] == "UNOBSERVED"
    assert registry["secret_argv"][0] == "<verified-owned-gitleaks>"
    assert "--ignore-gitleaks-allow" in registry["secret_argv"]
    assert "--exit-code" in registry["secret_argv"]
    assert "--no-color" in registry["secret_argv"]
    assert registry["secret_environment_keys"] == (
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "TMPDIR",
    )


def test_cap_s1_gitleaks_runtime_argv_disables_color_exactly_once(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    binary = tmp_path / "gitleaks"
    rule = tmp_path / "gitleaks.toml"
    target = tmp_path / "source"
    invocation = tmp_path / "invocation"
    binary.write_bytes(b"fixture")
    rule.write_bytes(b"fixture")
    target.mkdir()
    observed = []

    def _capture(argv, **kwargs):
        observed.append(tuple(argv))
        (invocation / "report.json").write_bytes(b"[]")
        kwargs["stdout_path"].write_bytes(b"")
        kwargs["stderr_path"].write_bytes(b"")
        return 0

    monkeypatch.setattr(canary_module, "_run_cap_s1_secret_process", _capture)
    canary_module._run_cap_s1_gitleaks_dir(
        binary_path=binary,
        rule_path=rule,
        target_root=target,
        invocation_root=invocation,
    )
    assert len(observed) == 1
    assert observed[0].count("--no-color") == 1
    expected = list(cap_s1_observer_registry()["secret_argv"])
    substitutions = {
        "<verified-owned-gitleaks>": str(binary),
        "<verified-owned-21-path-tree>": str(target),
        "<verified-pinned-rule-file>": str(rule),
        "<owned-private-report>": str(invocation / "report.json"),
        "<owned-empty-ignore-file>": str(invocation / "empty-ignore"),
    }
    assert observed[0] == tuple(substitutions.get(value, value) for value in expected)


def test_cap_s1_secret_control_recipes_assemble_only_in_owned_scratch(tmp_path) -> None:
    owner = tmp_path / "control-owner"
    owner.mkdir()
    rows = _assemble_cap_s1_secret_controls(owned_root=owner)
    assert tuple(rule_id for rule_id, _path, _count, _digest in rows) == (
        "private-key",
        "slack-bot-token",
        "stripe-access-token",
    )
    committed = (
        (REPO_ROOT / "scripts/ohf/cap_s1_mastermind_operator_canary.py").read_bytes()
        + Path(__file__).read_bytes()
    )
    for (rule_id, recipe, expected_count, expected_digest), row in zip(
        CAP_S1_SECRET_CONTROL_RECIPES,
        rows,
    ):
        observed_rule, path, observed_count, observed_digest = row
        payload = b"".join(segment * repeats for segment, repeats in recipe)
        assert observed_rule == rule_id
        assert observed_count == expected_count == 1
        assert observed_digest == expected_digest
        assert path.read_bytes() == payload
        assert payload not in committed
        assert path.is_relative_to(owner)


def _secret_test_archive(members) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for name, kind, payload in members:
            member = tarfile.TarInfo(name)
            member.mode = 0o755 if name == "gitleaks" else 0o644
            if kind == "file":
                member.size = len(payload)
                bundle.addfile(member, io.BytesIO(payload))
            elif kind == "symlink":
                member.type = tarfile.SYMTYPE
                member.linkname = "gitleaks"
                bundle.addfile(member)
            elif kind == "hardlink":
                member.type = tarfile.LNKTYPE
                member.linkname = "gitleaks"
                bundle.addfile(member)
            else:
                raise AssertionError(kind)
    return output.getvalue()


def test_cap_s1_secret_archive_member_policy_rejects_hostile_members(tmp_path) -> None:
    canonical = _secret_test_archive(
        (
            ("LICENSE", "file", b"fixture-license"),
            ("README.md", "file", b"fixture-readme"),
            ("gitleaks", "file", b"fixture-binary"),
        )
    )
    destination = tmp_path / "gitleaks"
    digest = _extract_cap_s1_gitleaks_binary(canonical, destination=destination)
    assert digest == hashlib.sha256(b"fixture-binary").hexdigest()
    assert destination.read_bytes() == b"fixture-binary"

    hostile_member_sets = (
        (
            ("LICENSE", "file", b"x"),
            ("README.md", "file", b"x"),
            ("gitleaks", "file", b"x"),
            ("gitleaks", "file", b"replacement"),
        ),
        (("LICENSE", "file", b"x"), ("README.md", "file", b"x"), ("../gitleaks", "file", b"x")),
        (("LICENSE", "file", b"x"), ("README.md", "file", b"x"), ("gitleaks", "symlink", b"")),
        (("LICENSE", "file", b"x"), ("README.md", "file", b"x"), ("gitleaks", "hardlink", b"")),
        (("LICENSE", "file", b"x"), ("README.md", "file", b"x"), ("gitleaks", "file", b"x"), ("extra", "file", b"x")),
    )
    for index, members in enumerate(hostile_member_sets):
        with pytest.raises(CapS1ResultError, match="secret_supply_invalid"):
            _extract_cap_s1_gitleaks_binary(
                _secret_test_archive(members),
                destination=tmp_path / f"hostile-{index}",
            )


def _redacted_secret_finding(rule_id: str, *, line: int = 1) -> dict:
    return {
        "RuleID": rule_id,
        "Description": "synthetic detector control",
        "StartLine": line,
        "EndLine": line,
        "StartColumn": 1,
        "EndColumn": 8,
        "Match": "REDACTED",
        "Secret": "REDACTED",
        "File": f"{rule_id}.txt",
        "SymlinkFile": "",
        "Commit": "",
        "Entropy": 0.0,
        "Author": "",
        "Email": "",
        "Date": "",
        "Message": "",
        "Tags": [],
        "Fingerprint": "",
    }


def test_cap_s1_secret_report_parser_requires_complete_clean_evidence(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    first = source / "a.py"
    second = source / "b.py"
    first.write_text("alpha\n", encoding="utf-8")
    second.write_text("beta\n", encoding="utf-8")
    manifest = (
        _CapS1SecretSourceEntry(
            index=1, path="a.py", mode="100644", blob="0" * 40,
            size=first.stat().st_size, sha256=hashlib.sha256(first.read_bytes()).hexdigest(),
        ),
        _CapS1SecretSourceEntry(
            index=2, path="b.py", mode="100644", blob="0" * 40,
            size=second.stat().st_size, sha256=hashlib.sha256(second.read_bytes()).hexdigest(),
        ),
    )
    total = sum(entry.size for entry in manifest)
    log = (
        f'TRC scanning path path="{first}"\n'
        f'TRC scanning path path="{second}"\n'
        f'INF scanned ~{total} bytes ({total} bytes) in 1ms\n'
        "INF no leaks found\n"
    ).encode()
    assert _parse_cap_s1_gitleaks_report(b"[]") == ()
    assert _parse_cap_s1_gitleaks_coverage(
        log,
        source_root=source,
        manifest=manifest,
        expected_bytes=total,
    )
    colored_log = (
        log.replace(b"TRC ", b"\x1b[90mTRC\x1b[0m ")
        .replace(b'path="', b'path=\x1b[0m"')
    )
    with pytest.raises(CapS1ResultError, match="secret_scan_incomplete"):
        _parse_cap_s1_gitleaks_coverage(
            colored_log,
            source_root=source,
            manifest=manifest,
            expected_bytes=total,
        )
    with pytest.raises(CapS1ResultError, match="secret_scan_incomplete"):
        _parse_cap_s1_gitleaks_coverage(
            log.replace(b"no leaks found", b"partial scan completed"),
            source_root=source,
            manifest=manifest,
            expected_bytes=total,
        )
    with pytest.raises(CapS1ResultError, match="secret_scan_incomplete"):
        _parse_cap_s1_gitleaks_coverage(
            log.replace(b"no leaks found", b"partial\x1b[0m scan completed"),
            source_root=source,
            manifest=manifest,
            expected_bytes=total,
        )
    with pytest.raises(CapS1ResultError, match="secret_scan_incomplete"):
        _parse_cap_s1_gitleaks_coverage(
            log.replace(b"TRC ", b"\x1b]unsupported-controlTRC "),
            source_root=source,
            manifest=manifest,
            expected_bytes=total,
        )
    with pytest.raises(CapS1ResultError, match="secret_scan_incomplete"):
        _parse_cap_s1_gitleaks_coverage(
            log.replace(str(second).encode(), str(first).encode()),
            source_root=source,
            manifest=manifest,
            expected_bytes=total,
        )


def test_cap_s1_secret_report_parser_preserves_findings_and_rejects_forgery() -> None:
    findings = [
        _redacted_secret_finding("private-key"),
        _redacted_secret_finding("slack-bot-token"),
        _redacted_secret_finding("stripe-access-token"),
    ]
    assert _parse_cap_s1_gitleaks_report(
        json.dumps(findings, separators=(",", ":")).encode(),
        allowed_rule_ids={"private-key", "slack-bot-token", "stripe-access-token"},
    ) == (
        ("private-key", 1),
        ("slack-bot-token", 1),
        ("stripe-access-token", 1),
    )
    unredacted = dict(findings[0])
    unredacted["Secret"] = "not-redacted"
    with pytest.raises(CapS1ResultError, match="secret_report_unredacted"):
        _parse_cap_s1_gitleaks_report(json.dumps([unredacted]).encode())
    with pytest.raises(CapS1ResultError, match="secret_report_invalid"):
        _parse_cap_s1_gitleaks_report(
            b'[{"RuleID":"private-key","RuleID":"stripe-access-token"}]'
        )
    forged = _redacted_secret_finding("private-key")
    forged["caller_clean"] = True
    with pytest.raises(CapS1ResultError, match="secret_report_invalid"):
        _parse_cap_s1_gitleaks_report(json.dumps([forged]).encode())


def test_cap_s1_secret_source_stage_is_immutable_complete_and_bounded(tmp_path) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, protected, head = _build_cap_s1_secret_stage_repository(tmp_path)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(canary_module, "REPO_ROOT", repository)
    owner = tmp_path / "source-owner"
    owner.mkdir()
    try:
        source, manifest, total = _stage_cap_s1_secret_source(
            exact_head=head,
            protected_join=protected,
            owned_root=owner,
        )
        assert len(manifest) == 21
        assert tuple(entry.path for entry in manifest) == tuple(
            sorted(entry.path for entry in manifest)
        )
        assert total == sum(entry.size for entry in manifest)
        assert 0 < total <= 10 * 1024 * 1024
        _verify_cap_s1_secret_manifest(source_root=source, manifest=manifest)
        first = source / manifest[0].path
        first.chmod(0o600)
        first.write_bytes(first.read_bytes() + b"changed")
        with pytest.raises(CapS1ResultError, match="secret_source_changed"):
            _verify_cap_s1_secret_manifest(source_root=source, manifest=manifest)
    finally:
        monkeypatch.undo()


def _cap_s1_test_git(repository: Path, *args: str) -> str:
    environment = {
        "PATH": os.environ["PATH"],
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "CAP-S1 fixture",
        "GIT_AUTHOR_EMAIL": "cap-s1-fixture@example.invalid",
        "GIT_COMMITTER_NAME": "CAP-S1 fixture",
        "GIT_COMMITTER_EMAIL": "cap-s1-fixture@example.invalid",
    }
    return _subprocess.check_output(
        ["git", *args], cwd=repository, env=environment, text=True
    ).strip()


def _build_cap_s1_secret_stage_repository(
    tmp_path: Path,
    *,
    extra_candidate_path: str | None = None,
    omit_candidate_path: str | None = None,
) -> tuple[Path, str, str]:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository = tmp_path / "stage-repository"
    repository.mkdir()
    _cap_s1_test_git(repository, "init", "--quiet")
    for relative in canary_module.RESULT_CHANGED_PATHS:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"protected:{relative}\n", encoding="utf-8")
        if relative in {
            "ops/control_room_remote/install.sh",
            "scripts/ohf/fake_codex_binary.py",
        }:
            path.chmod(0o755)
    _cap_s1_test_git(repository, "add", "--", *canary_module.RESULT_CHANGED_PATHS)
    _cap_s1_test_git(repository, "commit", "--quiet", "-m", "protected fixture")
    protected = _cap_s1_test_git(repository, "rev-parse", "HEAD")
    for relative in canary_module.RESULT_CHANGED_PATHS:
        path = repository / relative
        path.write_text(f"candidate:{relative}\n", encoding="utf-8")
    if omit_candidate_path is not None:
        (repository / omit_candidate_path).unlink()
    if extra_candidate_path is not None:
        extra = repository / extra_candidate_path
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("unexpected candidate path\n", encoding="utf-8")
    _cap_s1_test_git(repository, "add", "--all")
    _cap_s1_test_git(repository, "commit", "--quiet", "-m", "candidate fixture")
    return repository, protected, _cap_s1_test_git(repository, "rev-parse", "HEAD")


def test_cap_s1_secret_source_stage_refuses_real_22nd_path(tmp_path, monkeypatch) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    repository, protected, head = _build_cap_s1_secret_stage_repository(
        tmp_path, extra_candidate_path="unexpected/22nd-path.txt"
    )
    monkeypatch.setattr(canary_module, "REPO_ROOT", repository)
    owner = tmp_path / "source-owner"
    owner.mkdir()
    with pytest.raises(CapS1ResultError, match="secret_source_path_boundary"):
        _stage_cap_s1_secret_source(
            exact_head=head,
            protected_join=protected,
            owned_root=owner,
        )


def test_cap_s1_secret_source_stage_refuses_missing_candidate_blob(
    tmp_path, monkeypatch
) -> None:
    import scripts.ohf.cap_s1_mastermind_operator_canary as canary_module

    missing = canary_module.RESULT_CHANGED_PATHS[-1]
    repository, protected, head = _build_cap_s1_secret_stage_repository(
        tmp_path, omit_candidate_path=missing
    )
    monkeypatch.setattr(canary_module, "REPO_ROOT", repository)
    owner = tmp_path / "source-owner"
    owner.mkdir()
    with pytest.raises(CapS1ResultError, match="secret_source_unsupported"):
        _stage_cap_s1_secret_source(
            exact_head=head,
            protected_join=protected,
            owned_root=owner,
        )


def test_cap_s1_result_reopens_only_read_only_regular_producer_evidence() -> None:
    writable = _happy_cap_s1_result_kwargs()
    writable["producer_evidence_path"].chmod(0o644)
    with pytest.raises(CapS1ResultError, match="producer_evidence_invalid"):
        build_cap_s1_result(**writable)

    linked = _happy_cap_s1_result_kwargs()
    target = linked["producer_evidence_path"]
    link = target.with_name(f"{target.stem}-link.json")
    link.symlink_to(target)
    linked["producer_evidence_path"] = link
    with pytest.raises(CapS1ResultError, match="producer_evidence_invalid"):
        build_cap_s1_result(**linked)


def test_cap_s1_result_refuses_rebound_producer_evidence() -> None:
    raw = _happy_cap_s1_result_kwargs()
    producer_path = raw["producer_evidence_path"]
    producer_path.chmod(0o644)
    payload = json.loads(producer_path.read_text(encoding="utf-8"))
    payload["exact_head"] = "f" * 40
    producer_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    producer_path.chmod(0o444)
    with pytest.raises(CapS1ResultError, match="producer_evidence_invalid"):
        build_cap_s1_result(**raw)


@pytest.mark.parametrize(
    "host_path",
    (
        "/Users/alice/private-workspace",
        "/home/alice/private-workspace",
        "/private/tmp/private-workspace",
        "/var/tmp/private-workspace",
        "/tmp/private-workspace",
        "~/private-workspace",
        "/tmp/credentials/auth.json?token=secret",
        "https://provider.invalid/native-task?token=secret",
    ),
)
def test_completed_cap_s1_result_projects_attempt_local_paths_to_safe_identities(
    host_path,
) -> None:
    raw = _happy_cap_s1_result_kwargs()
    raw["provider_attempt"] = {
        key: value for key, value in raw["provider_attempt"].items() if key != "hold_code"
    }
    raw["provider_attempt"].update(
        state="COMPLETED",
        disposition="ACCEPTED",
        candidate_head=raw["exact_head"],
        candidate_tree=raw["exact_tree"],
    )
    raw["canary_evidence"] = dataclasses.replace(
        _completed_canary_evidence(
            head=raw["exact_head"],
            tree=raw["exact_tree"],
            attempt_id=raw["provider_attempt"]["attempt_id"],
            protected_join=raw["current_protected_join"],
        ),
        workspace_root=host_path,
        skills_root=host_path,
    )
    result = build_cap_s1_result(**raw)
    public_json = json.dumps(dataclasses.asdict(result), sort_keys=True)
    assert host_path not in public_json
    assert "workspace_root" not in public_json
    assert "skills_root" not in public_json
    assert "producer_evidence_path" not in public_json
    assert result.canary_evidence.workspace_identity_digest == _canonical_digest(
        {
            "identity_type": "cap-s1-synthetic-workspace/v1",
            "candidate_commit": raw["exact_head"],
            "candidate_tree": raw["exact_tree"],
            "canary_operation_id": "cap-s1-completed-canary",
            "provider_attempt_id": raw["provider_attempt"]["attempt_id"],
        }
    )
