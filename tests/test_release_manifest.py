"""Regression coverage for the exact-SHA Executive release manifest.

The release tree tracks ``vendor/macro`` as a symbolic link. Routing that entry
into the descriptor-based ACL observer -- which opens with ``O_NOFOLLOW`` and so
can never open a link at all -- made the manifest unbuildable for any release
containing one. ``install.sh`` reached that failure only after it had already
disabled and booted out the running control plane, so a deterministic,
source-derived defect presented as an outage.

These tests pin three things: the walk handles a symbolic link, it still refuses
an ACL on one (macOS lets ``chmod -h`` attach an ACL to the link itself, so
skipping links would have been a real hole), and file/directory behavior is
unchanged.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import fs_security
from control_plane.fs_security import FilesystemSecurityError
from ops.executive_os import release_manifest
from ops.executive_os.release_manifest import ReleaseManifestError


COMMIT_SHA = "a" * 40
TREE_SHA = "b" * 40
REPO_ROOT = Path(__file__).resolve().parents[1]

requires_darwin = pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS ACL observation is Darwin-only"
)


def _set_acl(path: Path, *, link: bool = False) -> None:
    """Attach a real ACL, or skip if this filesystem cannot carry one."""
    user = subprocess.run(
        ["/usr/bin/id", "-un"], capture_output=True, text=True, check=True
    ).stdout.strip()
    arguments = ["/bin/chmod"]
    if link:
        arguments.append("-h")
    arguments += ["+a", f"user:{user} allow read", str(path)]
    result = subprocess.run(arguments, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"cannot set a filesystem ACL here: {result.stderr.strip()}")


@pytest.fixture
def unowned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the walk as the invoking user.

    Every release object must be root:wheel, which no unprivileged test process
    can create. That policy is exercised directly by ``TestOwnershipPolicy``;
    these tests target the walk, which is otherwise unreachable without root.
    """
    monkeypatch.setattr(
        release_manifest, "_validate_owned_info", lambda info, *, label: None
    )


@pytest.fixture
def release(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    root.mkdir()
    ops = root / "ops"
    ops.mkdir()
    (ops / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    vendor = root / "vendor"
    vendor.mkdir()
    source = vendor / "macro_src"
    source.mkdir()
    (source / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
    # The tracked symlink the manifest walk could not get past.
    (vendor / "macro").symlink_to("macro_src")
    for path in (root, ops, vendor, source):
        os.chmod(path, 0o755)
    for path in (ops / "install.sh", source / "engine.py"):
        os.chmod(path, 0o644)
    return root


class TestSymlinkEntries:
    def test_create_walks_past_a_tracked_symlink(
        self, release: Path, unowned: None
    ) -> None:
        """The regression: this raised 'cannot inspect release ACL: macro'."""
        manifest = release_manifest.create(release, COMMIT_SHA, TREE_SHA)

        document = json.loads(manifest.read_text(encoding="utf-8"))
        entries = {entry["path"]: entry for entry in document["entries"]}
        assert entries["vendor/macro"]["type"] == "symlink"
        assert entries["vendor/macro"]["target"] == "macro_src"
        assert entries["vendor/macro_src"]["type"] == "directory"
        assert entries["vendor/macro_src/engine.py"]["type"] == "file"
        assert document["commit_sha"] == COMMIT_SHA

    def test_verify_round_trips_a_tracked_symlink(
        self, release: Path, unowned: None
    ) -> None:
        release_manifest.create(release, COMMIT_SHA, TREE_SHA)

        assert release_manifest.verify(release, COMMIT_SHA, TREE_SHA)["commit_sha"] == COMMIT_SHA

    def test_verify_detects_a_retargeted_symlink(
        self, release: Path, unowned: None
    ) -> None:
        release_manifest.create(release, COMMIT_SHA, TREE_SHA)
        (release / "vendor" / "decoy").mkdir()
        os.chmod(release / "vendor" / "decoy", 0o755)
        (release / "vendor" / "macro").unlink()
        (release / "vendor" / "macro").symlink_to("decoy")

        with pytest.raises(ReleaseManifestError, match="differs from its exact-SHA manifest"):
            release_manifest.verify(release, COMMIT_SHA, TREE_SHA)

    def test_absolute_symlink_is_rejected(self, release: Path, unowned: None) -> None:
        (release / "vendor" / "escape").symlink_to("/etc")

        with pytest.raises(ReleaseManifestError, match="absolute release symlink is forbidden"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)

    def test_escaping_symlink_is_rejected(self, release: Path, unowned: None) -> None:
        (release / "vendor" / "escape").symlink_to("../../outside")

        with pytest.raises(ReleaseManifestError, match="escapes the release root"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)

    def test_unsupported_object_is_rejected(self, release: Path, unowned: None) -> None:
        os.mkfifo(release / "channel")

        with pytest.raises(ReleaseManifestError, match="unsupported release object"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)


@requires_darwin
class TestAclRefusal:
    def test_symlink_carrying_an_acl_is_rejected(
        self, release: Path, unowned: None
    ) -> None:
        """macOS lets an ACL sit on the link itself; skipping links would hide it."""
        _set_acl(release / "vendor" / "macro", link=True)

        with pytest.raises(ReleaseManifestError, match="release symlink has a filesystem ACL"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)

    def test_regular_file_carrying_an_acl_is_still_rejected(
        self, release: Path, unowned: None
    ) -> None:
        _set_acl(release / "ops" / "install.sh")

        with pytest.raises(ReleaseManifestError, match="release object has a filesystem ACL"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)

    def test_directory_carrying_an_acl_is_still_rejected(
        self, release: Path, unowned: None
    ) -> None:
        _set_acl(release / "vendor" / "macro_src")

        with pytest.raises(ReleaseManifestError, match="release object has a filesystem ACL"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)


class TestOwnershipPolicy:
    @pytest.mark.skipif(
        getattr(os, "geteuid", lambda: 1000)() == 0,
        reason="a root test process creates root-owned objects, inverting the premise",
    )
    def test_non_root_release_object_is_still_rejected(self, release: Path) -> None:
        """No ``unowned`` fixture: the real root:wheel policy must still bite."""
        with pytest.raises(ReleaseManifestError, match="is not root:wheel"):
            release_manifest.create(release, COMMIT_SHA, TREE_SHA)


@requires_darwin
class TestLinkAclObserver:
    def test_descriptor_observer_still_fails_closed_on_a_symlink(
        self, release: Path
    ) -> None:
        """Why the link observer exists: O_NOFOLLOW cannot open a link."""
        with pytest.raises(FilesystemSecurityError, match="macOS ACL open failed"):
            fs_security.has_macos_acl(release / "vendor" / "macro")

    def test_link_observer_reports_absence_then_presence(self, release: Path) -> None:
        link = release / "vendor" / "macro"
        assert fs_security.has_macos_link_acl(link) is False

        _set_acl(link, link=True)

        assert fs_security.has_macos_link_acl(link) is True

    def test_link_observer_refuses_a_regular_file(self, release: Path) -> None:
        with pytest.raises(FilesystemSecurityError, match="is not a symbolic link"):
            fs_security.has_macos_link_acl(release / "ops" / "install.sh")

    def test_link_observer_fails_closed_on_a_missing_path(self, release: Path) -> None:
        with pytest.raises(FilesystemSecurityError, match="observation target is unavailable"):
            fs_security.has_macos_link_acl(release / "vendor" / "absent")


class TestInstallerMutationBoundary:
    """The ordering invariant that turns this class of defect back into an abort.

    ``install.sh`` disables and boots out the control plane as its first
    mutation. Any check derived purely from the source commit must therefore run
    before that point, or a deterministic failure strands the host with every
    Executive daemon stopped -- which is exactly what happened on 2026-09-17.
    """

    @staticmethod
    def _installer_lines() -> list[str]:
        return (REPO_ROOT / "ops" / "executive_os" / "install.sh").read_text(
            encoding="utf-8"
        ).splitlines()

    @staticmethod
    def _first_line_matching(lines: list[str], pattern: str) -> int:
        for number, line in enumerate(lines, start=1):
            if re.search(pattern, line):
                return number
        raise AssertionError(f"install.sh no longer contains {pattern!r}")

    def test_release_manifest_runs_before_any_launchctl_call(self) -> None:
        lines = self._installer_lines()
        manifest = self._first_line_matching(lines, r"release_manifest\.py")
        launchctl = self._first_line_matching(lines, r"launchctl ")

        assert manifest < launchctl, (
            f"install.sh reaches launchctl at line {launchctl} before the release "
            f"manifest at line {manifest}; a manifest failure would again leave the "
            "control plane disabled"
        )

    def test_manifest_is_created_before_the_release_is_published(self) -> None:
        lines = self._installer_lines()
        create = self._first_line_matching(lines, r'release_manifest\.py" create')
        publish = self._first_line_matching(lines, r'mv "\$STAGING" "\$RELEASE_ROOT"')

        assert create < publish, (
            "install.sh publishes the release before writing its manifest; a failure "
            "in between leaves a manifest-less release that fails the verify branch "
            "of every later install"
        )

    def test_staging_is_discarded_on_an_early_failure(self) -> None:
        lines = self._installer_lines()
        trap = self._first_line_matching(lines, r"trap discard_release_staging EXIT")
        staging = self._first_line_matching(lines, r'STAGING="\$\(/usr/bin/mktemp')

        assert trap < staging, "staging is created before its cleanup trap is armed"
