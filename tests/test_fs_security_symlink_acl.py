"""Manifest-only symlink ACL observation contract for ``control_plane.fs_security``.

The Executive installer exports the tracked ``vendor/macro -> macro_src`` symlink
(git mode 120000) into every release tree, so the release manifest must be able to
observe a symlink's *own* ACL without following it. That permission is a narrow,
explicit opt-in on the shared API; every ordinary caller keeps failing closed.
"""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
import sys

import pytest

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
from control_plane import fs_security
from ops.executive_os import release_manifest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS ACL observation is Darwin-only"
)


def _live_link(tmp_path):
    """Create ``link -> target`` with a real (non-dangling) target file."""

    target = tmp_path / "target.txt"
    target.write_text("payload\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target.name)
    return link, target


def _identity(path):
    info = os.lstat(path)
    return info.st_dev, info.st_ino


def _add_link_acl(link):
    """Set a real ACL on the symlink itself (``chmod -h``); never follows the link."""

    name = pwd.getpwuid(os.getuid()).pw_name
    return subprocess.run(
        ["/bin/chmod", "-h", "+a", f"{name} allow read", os.fspath(link)],
        capture_output=True,
        text=True,
    )


def test_default_path_only_observation_still_refuses_symlinks(tmp_path):
    """Contract 1: ordinary callers keep failing closed on a live and a dangling link."""

    link, _ = _live_link(tmp_path)
    with pytest.raises(FilesystemSecurityError) as live:
        has_macos_acl(link)
    assert "macOS ACL open failed" in str(live.value)

    dangling = tmp_path / "dangling"
    dangling.symlink_to("missing-target")
    assert not os.path.exists(dangling)
    with pytest.raises(FilesystemSecurityError) as dead:
        has_macos_acl(dangling)
    assert "macOS ACL open failed" in str(dead.value)

    # A caller that hands over a symlink lstat but does NOT opt in is still refused.
    with pytest.raises(FilesystemSecurityError) as informed:
        has_macos_acl(link, expected_identity=os.lstat(link))
    assert "macOS ACL open failed" in str(informed.value)


def test_opt_in_observes_live_and_dangling_links_without_following(tmp_path):
    """Contract 3: opt-in + symlink lstat observes the link itself, never the target."""

    link, target = _live_link(tmp_path)
    assert has_macos_acl(link, expected_identity=os.lstat(link), allow_symlink=True) is False

    dangling = tmp_path / "dangling"
    dangling.symlink_to("missing-target")
    assert not os.path.exists(dangling)
    assert (
        has_macos_acl(dangling, expected_identity=os.lstat(dangling), allow_symlink=True) is False
    )


def test_opt_in_does_not_follow_to_an_acl_bearing_target(tmp_path):
    """No-follow proof: the target's ACL is not the link's ACL."""

    link, target = _live_link(tmp_path)
    name = pwd.getpwuid(os.getuid()).pw_name
    applied = subprocess.run(
        ["/bin/chmod", "+a", f"{name} allow read", os.fspath(target)],
        capture_output=True,
        text=True,
    )
    if applied.returncode != 0:
        pytest.skip(f"chmod +a on a regular file is unavailable: {applied.stderr.strip()}")

    assert has_macos_acl(target, expected_identity=os.lstat(target)) is True
    assert has_macos_acl(link, expected_identity=os.lstat(link), allow_symlink=True) is False


def test_retargeted_link_refuses_on_identity_change(tmp_path):
    """Contract 3: a link swapped between lstat and open refuses as identity change."""

    link, target = _live_link(tmp_path)
    before = os.lstat(link)
    link.unlink()
    link.symlink_to(f"{target.name}-other")
    after = os.lstat(link)
    assert (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino), "inode was reused"

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(link, expected_identity=before, allow_symlink=True)
    assert "identity changed" in str(excinfo.value)


def test_link_replaced_by_regular_file_refuses(tmp_path):
    """Contract 3: a link replaced by a regular file is refused, not silently accepted."""

    link, _ = _live_link(tmp_path)
    before = os.lstat(link)
    link.unlink()
    link.write_text("now a regular file\n", encoding="utf-8")
    after = os.lstat(link)
    assert (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino) or not stat.S_ISLNK(
        after.st_mode
    )

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(link, expected_identity=before, allow_symlink=True)
    message = str(excinfo.value)
    assert "identity changed" in message or "not a symlink" in message


def test_opt_in_without_expected_identity_refuses(tmp_path):
    """Contract 3: opt-in never establishes a fresh lstat baseline of its own."""

    link, _ = _live_link(tmp_path)
    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(link, allow_symlink=True)
    assert "requires the caller's pre-open lstat" in str(excinfo.value)

    regular = tmp_path / "regular.txt"
    regular.write_text("payload\n", encoding="utf-8")
    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(regular, allow_symlink=True)
    assert "requires the caller's pre-open lstat" in str(excinfo.value)


def test_opt_in_with_non_link_identity_refuses(tmp_path):
    """Contract 3: a non-symlink identity is refused, not routed to the ordinary path."""

    regular = tmp_path / "regular.txt"
    regular.write_text("payload\n", encoding="utf-8")
    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(regular, expected_identity=os.lstat(regular), allow_symlink=True)
    assert "requires a symlink pre-open identity" in str(excinfo.value)

    directory = tmp_path / "subdir"
    directory.mkdir()
    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl(directory, expected_identity=os.lstat(directory), allow_symlink=True)
    assert "requires a symlink pre-open identity" in str(excinfo.value)


def test_missing_native_o_symlink_refuses_without_any_open(tmp_path, monkeypatch):
    """Contract 4: no native O_SYMLINK -> typed refusal before opening anything."""

    link, _ = _live_link(tmp_path)
    before = os.lstat(link)
    real_open = os.open
    opened = []

    def recording_open(path, flags, *args, **kwargs):
        opened.append((os.fspath(path), flags))
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.delattr(os, "O_SYMLINK", raising=True)
        assert not hasattr(os, "O_SYMLINK")
        patch.setattr(fs_security.os, "open", recording_open)
        with pytest.raises(FilesystemSecurityError) as excinfo:
            has_macos_acl(link, expected_identity=before, allow_symlink=True)

    assert "O_SYMLINK" in str(excinfo.value)
    assert opened == [], "a missing O_SYMLINK must refuse before any fallback open"


def test_real_symlink_acl_is_observed(tmp_path):
    """Contract 4: an ACL set on the link itself is observed (``chmod -h``), not the target's."""

    target = tmp_path / "target-dir"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target.name)
    assert has_macos_acl(target, expected_identity=os.lstat(target)) is False

    applied = _add_link_acl(link)
    if applied.returncode != 0:
        pytest.skip(f"chmod -h +a on a symlink is unavailable: {applied.stderr.strip()}")

    before = os.lstat(link)
    assert has_macos_acl(link, expected_identity=before, allow_symlink=True) is True
    assert _identity(link) == (before.st_dev, before.st_ino)
    assert has_macos_acl(target, expected_identity=os.lstat(target)) is False

    # The ACL is on the link, so the default path-only call keeps refusing the link.
    with pytest.raises(FilesystemSecurityError):
        has_macos_acl(link)


def test_link_swap_and_restore_during_open_never_reports_acl_free(tmp_path, monkeypatch):
    """Contract 3: a link swapped for an ACL-free decoy around the open is never ACL-free."""

    link, _ = _live_link(tmp_path)
    applied = _add_link_acl(link)
    if applied.returncode != 0:
        pytest.skip(f"chmod -h +a on a symlink is unavailable: {applied.stderr.strip()}")

    before = os.lstat(link)
    assert has_macos_acl(link, expected_identity=before, allow_symlink=True) is True

    decoy = tmp_path / "acl-free-decoy"
    decoy.symlink_to("target.txt")
    held = tmp_path / "held-original"
    real_open = os.open
    target_name = os.fspath(link)
    swaps = []

    def swapping_open(path, flags, *args, **kwargs):
        if os.fspath(path) != target_name:
            return real_open(path, flags, *args, **kwargs)
        os.rename(link, held)
        os.rename(decoy, link)
        swaps.append(os.lstat(link).st_ino)
        try:
            descriptor = real_open(path, flags, *args, **kwargs)
        finally:
            os.rename(link, decoy)
            os.rename(held, link)
        return descriptor

    answer = None
    with monkeypatch.context() as patch:
        patch.setattr(fs_security.os, "open", swapping_open)
        try:
            answer = has_macos_acl(link, expected_identity=before, allow_symlink=True)
        except FilesystemSecurityError as exc:
            assert "identity changed" in str(exc) or "not a symlink" in str(exc)

    assert swaps and swaps[0] != before.st_ino, "the injected swap never ran"
    assert answer is None or answer is True, "an ACL-bearing original link was reported ACL-free"
    assert _identity(link) == (before.st_dev, before.st_ino), "the original link was not restored"
    assert has_macos_acl(link, expected_identity=os.lstat(link), allow_symlink=True) is True


def test_path_swap_held_through_acl_read_never_reports_acl_free(tmp_path, monkeypatch):
    """Contract 4: the ACL read is descriptor-bound; a pathname re-read would see the decoy.

    The swap is injected *after* the real open and held until the descriptor is closed,
    so a pathname-based ``acl_get_link_np`` bracket would observe the ACL-free decoy
    while the descriptor still refers to the ACL-bearing original link.
    """

    link, _ = _live_link(tmp_path)
    applied = _add_link_acl(link)
    if applied.returncode != 0:
        pytest.skip(f"chmod -h +a on a symlink is unavailable: {applied.stderr.strip()}")

    before = os.lstat(link)
    decoy = tmp_path / "acl-free-decoy"
    decoy.symlink_to("target.txt")
    held = tmp_path / "held-original"
    real_open = os.open
    real_close = os.close
    target_name = os.fspath(link)
    swaps = []
    swapped_descriptors = set()

    def swapping_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == target_name:
            os.rename(link, held)
            os.rename(decoy, link)
            swaps.append(os.lstat(link).st_ino)
            swapped_descriptors.add(descriptor)
        return descriptor

    def restoring_close(descriptor):
        if descriptor in swapped_descriptors:
            swapped_descriptors.discard(descriptor)
            os.rename(link, decoy)
            os.rename(held, link)
        return real_close(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(fs_security.os, "open", swapping_open)
        patch.setattr(fs_security.os, "close", restoring_close)
        answer = has_macos_acl(link, expected_identity=before, allow_symlink=True)

    assert swaps and swaps[0] != before.st_ino, "the injected swap never ran"
    assert answer is True, "the descriptor-bound ACL read must observe the opened link"
    assert _identity(link) == (before.st_dev, before.st_ino), "the original link was not restored"
    assert has_macos_acl(link, expected_identity=os.lstat(link), allow_symlink=True) is True


def _production_shaped_root(tmp_path, links):
    root = tmp_path / "release"
    (root / "macro_src").mkdir(parents=True)
    (root / "macro_src" / "engine.py").write_text("payload\n", encoding="utf-8")
    (root / "vendor").mkdir()
    for name, target in links.items():
        (root / "vendor" / name).symlink_to(target)
    return root


def test_entries_records_relative_symlink_entries(tmp_path, monkeypatch):
    """Contract 4: the manifest opts in and records symlink entries instead of failing."""

    monkeypatch.setattr(
        release_manifest, "_validate_owned_info", lambda info, *, label: None
    )
    root = _production_shaped_root(
        tmp_path, {"macro": "macro_src", "dead": "missing_target"}
    )

    by_path = {entry["path"]: entry for entry in release_manifest._entries(root)}

    live = by_path["vendor/macro"]
    assert {key: live[key] for key in ("path", "type", "target")} == {
        "path": "vendor/macro",
        "type": "symlink",
        "target": "macro_src",
    }
    dangling = by_path["vendor/dead"]
    assert {key: dangling[key] for key in ("path", "type", "target")} == {
        "path": "vendor/dead",
        "type": "symlink",
        "target": "missing_target",
    }
    assert by_path["macro_src"]["type"] == "directory"
    assert by_path["macro_src/engine.py"]["type"] == "file"


def test_entries_still_refuses_absolute_targets(tmp_path, monkeypatch):
    """Contract 4: opting in does not relax the pre-existing absolute-target refusal."""

    monkeypatch.setattr(
        release_manifest, "_validate_owned_info", lambda info, *, label: None
    )
    root = _production_shaped_root(tmp_path, {"abs": "/etc/hosts"})

    with pytest.raises(release_manifest.ReleaseManifestError) as excinfo:
        release_manifest._entries(root)
    assert "absolute release symlink is forbidden" in str(excinfo.value)


def test_cross_caller_path_only_observation_still_refuses_symlinks(tmp_path):
    """Contract 1: the existing receipt caller's path-only behavior is unchanged."""

    from control_plane.executive_autonomy import AutonomyRefusal, _macos_acl, load_receipt_file

    link, target = _live_link(tmp_path)
    target.write_text(
        '{"schema_version": "mastermind.executive_autonomy_state/v1"}\n', encoding="utf-8"
    )

    with pytest.raises(AutonomyRefusal) as direct:
        _macos_acl(link)
    assert str(direct.value) == "receipt_acl_unsafe"

    with pytest.raises(AutonomyRefusal) as loaded:
        load_receipt_file(link)
    assert str(loaded.value) == "receipt_unavailable"
