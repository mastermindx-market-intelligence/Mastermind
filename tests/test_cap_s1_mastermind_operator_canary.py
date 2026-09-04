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
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
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
    CapS1Result,
    CapS1ResultError,
    FAKE_HARNESS_VERSION,
    FROZEN_STOP_CODES,
    _SCHEMA_FIXTURE_BINARY_SOURCE,
    attest_protocol_schema,
    build_cap_s1_result,
    build_synthetic_workspace,
    main as canary_main,
    run_canary,
    validate_cap_s1_result,
)
from scripts.ohf.laboratory import AppServerClient, default_user_codex_home


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
def _close_created_canary_clients():
    _CREATED_CANARY_CLIENTS.clear()
    yield
    for client in _CREATED_CANARY_CLIENTS:
        try:
            client.close()
        except Exception:
            pass
    _CREATED_CANARY_CLIENTS.clear()


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
            client_factory=factory,
            # The schema fixture WITHOUT the skill input path -- the fake
            # binary is never invoked; this is just the JSON doc the
            # injected run_command writes out for attest_protocol_schema.
            run_command=_fake_schema_run_command(
                _SCHEMA_WITHOUT_SKILL_PATH_PLUS_UNRELATED_FRAGMENT
            ),
        )
    assert excinfo.value.code == "SKILL_PATH_ATTESTATION_UNAVAILABLE"

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
            client_factory=factory,
            run_command=_fake_schema_run_command(_SCHEMA_WITH_SKILL_PATH),
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
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
            client_factory=factory,
            run_command=failing_workspace_run_command,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"
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
            client_factory=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("client_factory must never be invoked")
            ),
            run_command=_must_not_run,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"


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
            client_factory=lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("client_factory must never be invoked")
            ),
            run_command=_must_not_run,
        )
    assert excinfo.value.code == "PROVIDER_REALM_UNAVAILABLE"


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
            client_factory=lambda *_a, **_k: None,
        )
    message = str(excinfo.value)
    assert str(hostile_home) not in message
    assert "secret-token-do-not-echo" not in message


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
        ["--backend", "fake", "--scratch", str(tmp_path / "cli-scratch"), "--operation-id", "cap-s1-cli-smoke"]
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
        ["--backend", "fake", "--scratch", str(tmp_path / "cli-scratch-2"), "--operation-id", "cap-s1-cli-smoke-2"]
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
        ["--backend", "fake", "--scratch", str(tmp_path / "cli-scratch-3"), "--operation-id", "cap-s1-cli-smoke-3"]
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
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "mastermind.cap_s1_canary_evidence/v1"
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


def _happy_cap_s1_result_kwargs() -> dict:
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
    return dict(
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
            "suite_count": 4,
            "passed": 357,
            "skipped": 2,
            "evidence_digest": "6" * 64,
        },
        hosted_proof={
            **bound,
            "run_id": "33741521536",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "jobs_passed": 5,
            "evidence_digest": "7" * 64,
        },
        security_proof={
            **bound,
            "status": "CLEAN",
            "tool_count": 3,
            "findings": 0,
            "evidence_digest": "8" * 64,
        },
        mutation_proof={
            **bound,
            "status": "PASSED",
            "killed": 12,
            "survived": 0,
            "evidence_digest": "9" * 64,
        },
        cleanup_proof={
            **bound,
            "status": "CLEAN",
            "all_removed": True,
            "residue_count": 0,
            "resource_kinds": [
                "attempt",
                "origin",
                "process",
                "projection",
                "schema",
                "thread",
                "workspace",
            ],
            "evidence_digest": "a" * 64,
        },
        review_state={
            **bound,
            "author": "chriswong6031-creator",
            "reviewer": "mastermindx-3",
            "review_id": "5104652791",
            "state": "APPROVED",
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


def test_build_cap_s1_result_happy_path_round_trips_through_json() -> None:
    result = build_cap_s1_result(**_happy_cap_s1_result_kwargs())
    assert result.schema_version == RESULT_CONTRACT_SCHEMA
    assert result.marker == RESULT_CONTRACT_MARKER
    validate_cap_s1_result(result)  # never raises on an already-built result
    payload = dataclasses.asdict(result)
    reloaded = json.loads(json.dumps(payload))
    assert reloaded["schema_version"] == RESULT_CONTRACT_SCHEMA
    assert reloaded["marker"] == RESULT_CONTRACT_MARKER


def test_cap_s1_result_schema_and_marker_are_exact() -> None:
    kwargs = _happy_cap_s1_result_kwargs()
    with pytest.raises(CapS1ResultError, match="schema_mismatch"):
        validate_cap_s1_result(CapS1Result(schema_version="wrong/v1", marker=RESULT_CONTRACT_MARKER, **kwargs))
    with pytest.raises(CapS1ResultError, match="marker_mismatch"):
        validate_cap_s1_result(
            CapS1Result(schema_version=RESULT_CONTRACT_SCHEMA, marker="wrong-marker", **kwargs)
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

    typed = build_cap_s1_result(**_happy_cap_s1_result_kwargs())
    wrong_closure_count = dataclasses.replace(
        typed,
        package_identities=dataclasses.replace(
            typed.package_identities,
            closures=typed.package_identities.closures[:-1],
        ),
    )
    with pytest.raises(CapS1ResultError, match="package_identities_invalid"):
        validate_cap_s1_result(wrong_closure_count)


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
    result = CapS1Result(
        schema_version=RESULT_CONTRACT_SCHEMA,
        marker=RESULT_CONTRACT_MARKER,
        **raw,
    )
    with pytest.raises(CapS1ResultError, match="subreceipt_type_invalid"):
        validate_cap_s1_result(result)


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
