"""Symlink ACL observation contract for ``control_plane.fs_security``.

The Executive installer exports the tracked ``vendor/macro -> macro_src`` symlink
(git mode 120000) into every release tree, so the release manifest must be able to
observe a symlink's *own* ACL without following it. That permission is a narrow,
explicit opt-in on the shared API; every ordinary caller keeps failing closed.

The suite has two layers, so the contract is exercised on Linux hosted CI as well
as on Darwin:

* **Semantic** cases run on every platform. They patch ``sys.platform`` to
  ``"darwin"`` (the module attribute ``fs_security`` reads at call time), set
  ``os.O_SYMLINK`` as each case needs it, and replace ``os.open``/``os.lstat``/
  ``os.fstat``/``os.close`` plus the descriptor-bound ACL reader
  (``control_plane.fs_security._acl_get_fd``) with command-aware fakes, so the
  decision logic, the exact open flags, and descriptor ownership are observable
  without a Darwin kernel.
* **Real-filesystem** cases use a real ``O_SYMLINK`` open, ``/bin/chmod -h +a``
  link ACLs, and the real manifest walker. They are Darwin-only and each case
  carries its own skip marker.
"""

from __future__ import annotations

import ctypes
import errno
import os
import pwd
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

from control_plane import fs_security
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
from ops.executive_os import release_manifest

# Darwin's O_SYMLINK; semantic cases install it explicitly so the assertions do
# not depend on the host's headers, and so Linux CI can run them.
O_SYMLINK = 0x200000

# Descriptor the fakes hand back for observer-owned opens.
FAKE_DESCRIPTOR = 4242


def _stat_result(kind, *, dev=11, ino=22, mode=0o755, uid=0, gid=0, size=0):
    """Build a real ``os.stat_result`` with the requested file type and identity."""

    return os.stat_result((kind | mode, ino, dev, 1, uid, gid, size, 0, 0, 0))


def _darwin(monkeypatch):
    """Make ``fs_security`` read ``sys.platform == "darwin"`` for this call."""

    monkeypatch.setattr(sys, "platform", "darwin")


class _Observation:
    """Command-aware stand-in for the Darwin open/lstat/fstat/close/ACL path.

    Every fake delegates to the real function for paths and descriptors this
    observation does not own, so pytest's own file handling is untouched.
    """

    def __init__(
        self,
        *,
        target,
        observed,
        acl_present=False,
        acl_errno=None,
        open_error=None,
        nofollow_eloop=False,
        fstat_error=None,
        caller_descriptor=None,
    ):
        self.target = os.fspath(target)
        self.observed = observed
        self.acl_present = acl_present
        self.acl_errno = acl_errno
        self.open_error = open_error
        self.nofollow_eloop = nofollow_eloop
        self.fstat_error = fstat_error
        self.caller_descriptor = caller_descriptor
        self.opens = []
        self.lstats = []
        self.fstats = []
        self.closed = []
        self.caller_closes = []
        self.acl_reads = []
        self._real = (os.open, os.lstat, os.fstat, os.close)

    def install(self, monkeypatch):
        real_open, real_lstat, real_fstat, real_close = self._real

        def fake_open(path, flags, *args, **kwargs):
            name = os.fspath(path)
            self.opens.append((name, flags))
            if name != self.target:
                return real_open(name, flags, *args, **kwargs)
            if self.open_error is not None:
                raise self.open_error
            if self.nofollow_eloop and flags & getattr(os, "O_NOFOLLOW", 0):
                raise OSError(errno.ELOOP, "Too many levels of symbolic links", name)
            return FAKE_DESCRIPTOR

        def fake_lstat(path, *args, **kwargs):
            name = os.fspath(path)
            if name != self.target:
                return real_lstat(name, *args, **kwargs)
            self.lstats.append(name)
            return self.observed

        def fake_fstat(descriptor):
            owned = descriptor == FAKE_DESCRIPTOR
            caller = self.caller_descriptor is not None and descriptor == self.caller_descriptor
            if owned or caller:
                self.fstats.append(descriptor)
                if self.fstat_error is not None:
                    raise self.fstat_error
                return self.observed
            return real_fstat(descriptor)

        def fake_close(descriptor):
            if descriptor == FAKE_DESCRIPTOR:
                self.closed.append(descriptor)
                return None
            if self.caller_descriptor is not None and descriptor == self.caller_descriptor:
                self.caller_closes.append(descriptor)
                return None
            return real_close(descriptor)

        def fake_acl_get_fd(descriptor):
            self.acl_reads.append(descriptor)
            if self.acl_errno is not None:
                ctypes.set_errno(self.acl_errno)
                return None
            if self.acl_present:
                ctypes.set_errno(0)
                return 1
            ctypes.set_errno(errno.ENOENT)
            return None

        def fake_acl_get_entry(acl, entry_id, entry):
            ctypes.set_errno(0)
            entry._obj.value = 1
            return 0

        def fake_acl_free(acl):
            return 0

        monkeypatch.setattr(fs_security.os, "open", fake_open)
        monkeypatch.setattr(fs_security.os, "lstat", fake_lstat)
        monkeypatch.setattr(fs_security.os, "fstat", fake_fstat)
        monkeypatch.setattr(fs_security.os, "close", fake_close)
        monkeypatch.setattr(fs_security, "_acl_get_fd", fake_acl_get_fd)
        if self.acl_present:
            monkeypatch.setattr(fs_security, "_acl_get_entry", fake_acl_get_entry)
            monkeypatch.setattr(fs_security, "_acl_free", fake_acl_free)
        return self

    @property
    def flags(self):
        assert len(self.opens) == 1, f"expected one observer open, saw {self.opens!r}"
        return self.opens[0][1]


def test_default_path_only_symlink_identity_refuses_without_following(monkeypatch):
    """Contract 1 (semantic): a path-only caller keeps O_NOFOLLOW and no opt-in."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(
        target="link", observed=link_info, nofollow_eloop=True
    ).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link")

    assert "macOS ACL open failed" in str(excinfo.value)
    flags = observation.flags
    assert flags == (
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    ), "the default branch flag word must be exactly O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK"
    assert observation.lstats == ["link"]
    assert observation.fstats == [], "an ELOOP open must not be observed further"


def test_default_branch_keeps_o_nofollow_for_an_informed_symlink_caller(monkeypatch):
    """Contract 1 (semantic): a symlink lstat without the opt-in is still refused."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info)

    assert "not a file or directory" in str(excinfo.value)
    flags = observation.flags
    assert flags & os.O_NOFOLLOW
    assert not flags & O_SYMLINK
    assert observation.closed == [FAKE_DESCRIPTOR], "the owned descriptor closes on refusal"


def test_default_descriptor_handoff_is_unchanged(monkeypatch):
    """Contract 1 (semantic): a non-opt-in descriptor handoff keeps its old behavior."""

    _darwin(monkeypatch)
    info = _stat_result(stat.S_IFREG)
    observation = _Observation(
        target="file", observed=info, caller_descriptor=77
    ).install(monkeypatch)

    assert has_macos_acl("file", expected_identity=info, descriptor=77) is False

    assert observation.opens == [], "a caller-supplied descriptor must not be re-opened"
    assert observation.fstats == [77]
    assert observation.closed == []
    assert observation.caller_closes == [], "the caller still owns its descriptor"


def test_opt_in_without_expected_identity_refuses_before_open(monkeypatch):
    """Contract 3 (semantic): the opt-in never establishes a fresh lstat baseline."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", allow_symlink=True)

    assert "requires the caller's pre-open lstat" in str(excinfo.value)
    assert observation.opens == [] and observation.fstats == [] and observation.lstats == []


@pytest.mark.parametrize(
    "identity",
    [
        object(),
        types.SimpleNamespace(st_mode=stat.S_IFLNK),
        (stat.S_IFLNK, 22, 11),
    ],
    ids=["object-without-attributes", "namespace-without-identity", "plain-tuple"],
)
def test_opt_in_with_non_stat_result_identity_refuses_before_open(monkeypatch, identity):
    """Reviewer LOW (semantic): a malformed pre-open identity is a typed refusal.

    The opt-in requires the caller's real ``os.stat_result``. An object without
    ``st_mode``, one that reports ``S_IFLNK`` without ``st_dev``/``st_ino``, and a
    plain tuple must all raise ``FilesystemSecurityError`` before any open rather
    than leaking an ``AttributeError`` from the S_ISLNK check or the post-open
    identity comparison. This is platform-independent and never skips.
    """

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    observation = _Observation(
        target="link", observed=_stat_result(stat.S_IFLNK)
    ).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=identity, allow_symlink=True)

    assert "requires an os.stat_result pre-open identity" in str(excinfo.value)
    assert observation.opens == [], "a malformed identity must refuse before any open"
    assert observation.fstats == [] and observation.acl_reads == []


@pytest.mark.parametrize(
    "kind", [stat.S_IFREG, stat.S_IFDIR], ids=["regular-file", "directory"]
)
def test_opt_in_with_non_link_identity_refuses_before_open(monkeypatch, kind):
    """Contract 3 (semantic): a non-symlink identity is refused, never re-routed."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    info = _stat_result(kind)
    observation = _Observation(target="object", observed=info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("object", expected_identity=info, allow_symlink=True)

    assert "requires a symlink pre-open identity" in str(excinfo.value)
    assert observation.opens == [] and observation.fstats == [] and observation.acl_reads == []


def test_symlink_opt_in_refuses_a_caller_supplied_descriptor(monkeypatch):
    """P1 (semantic): the symlink observation must own its O_SYMLINK descriptor."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(
        target="link", observed=link_info, caller_descriptor=77
    ).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info, descriptor=77, allow_symlink=True)

    assert "must own its descriptor" in str(excinfo.value)
    assert observation.opens == [], "the opt-in must not open when a descriptor is supplied"
    assert observation.fstats == [], "the caller's descriptor must not be observed"
    assert observation.closed == [] and observation.caller_closes == []


def test_opt_in_missing_o_symlink_refuses_before_any_open(monkeypatch):
    """P2 (semantic): no native O_SYMLINK attribute -> typed refusal, no open."""

    _darwin(monkeypatch)
    monkeypatch.delattr(os, "O_SYMLINK", raising=False)
    assert not hasattr(os, "O_SYMLINK")
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info, allow_symlink=True)

    assert "O_SYMLINK is not native" in str(excinfo.value)
    assert observation.opens == [] and observation.fstats == [] and observation.acl_reads == []


def test_opt_in_zero_o_symlink_refuses_before_any_open(monkeypatch):
    """P2 (semantic): a zero O_SYMLINK is not a usable flag and must refuse."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", 0, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info, allow_symlink=True)

    assert "O_SYMLINK is not a nonzero integer" in str(excinfo.value)
    assert observation.opens == [], "a zero O_SYMLINK must refuse before any open"
    assert observation.fstats == [] and observation.acl_reads == []


@pytest.mark.parametrize("flag", [True, "0x200000"], ids=["bool", "string"])
def test_opt_in_non_integer_o_symlink_refuses_before_any_open(monkeypatch, flag):
    """P2 (semantic): bool/str O_SYMLINK values are not native ints and must refuse."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", flag, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info, allow_symlink=True)

    assert "O_SYMLINK is not native" in str(excinfo.value)
    assert observation.opens == [], "a non-int O_SYMLINK must refuse before any open"
    assert observation.fstats == [] and observation.acl_reads == []


def test_opt_in_input_validation_is_platform_independent(monkeypatch):
    """Reviewer MEDIUM: opt-in input validation refuses before the Darwin gate.

    ``has_macos_acl`` stays a Darwin ACL *observer*, so a well-formed opt-in off
    Darwin still returns ``False`` without opening anything (no open, no ACL
    concept there) -- that keeps the Linux release-manifest path working. The
    input contract itself is unconditional: a missing identity, a non-symlink
    identity, or a caller-supplied descriptor is refused on every platform
    instead of silently answering ACL-free.
    """

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delattr(os, "O_SYMLINK", raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", allow_symlink=True)
    assert "requires the caller's pre-open lstat" in str(excinfo.value)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("object", expected_identity=_stat_result(stat.S_IFREG), allow_symlink=True)
    assert "requires a symlink pre-open identity" in str(excinfo.value)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=link_info, descriptor=77, allow_symlink=True)
    assert "must own its descriptor" in str(excinfo.value)

    assert has_macos_acl("link", expected_identity=link_info, allow_symlink=True) is False
    assert has_macos_acl("link") is False
    assert observation.opens == []
    assert observation.lstats == []
    assert observation.fstats == []


def test_symlink_branch_flags_include_o_symlink_and_exclude_o_nofollow(monkeypatch):
    """Contract 4 (semantic): the opt-in flag word is exactly the no-follow-escape set.

    Reviewer GAP: equality (not membership) so an extra flag bit cannot hide.
    """

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(target="link", observed=link_info).install(monkeypatch)

    assert has_macos_acl("link", expected_identity=link_info, allow_symlink=True) is False

    flags = observation.flags
    assert flags == (
        os.O_RDONLY
        | O_SYMLINK
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    ), "the opt-in flag word must be exactly O_RDONLY|O_SYMLINK|O_CLOEXEC|O_NONBLOCK"
    assert observation.acl_reads == [FAKE_DESCRIPTOR]
    assert observation.closed == [FAKE_DESCRIPTOR]


def test_symlink_branch_reports_a_present_acl_on_the_opened_link(monkeypatch):
    """Contract 4 (semantic): the ACL decision comes from the descriptor-bound reader."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    observation = _Observation(
        target="link", observed=link_info, acl_present=True
    ).install(monkeypatch)

    assert has_macos_acl("link", expected_identity=link_info, allow_symlink=True) is True

    assert observation.acl_reads == [FAKE_DESCRIPTOR]
    assert observation.closed == [FAKE_DESCRIPTOR]


def test_symlink_opt_in_identity_drift_refuses_and_closes(monkeypatch):
    """Contract 3 (semantic): an fstat identity change refuses and closes the descriptor."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    before = _stat_result(stat.S_IFLNK, ino=22)
    observed = _stat_result(stat.S_IFLNK, ino=23)
    observation = _Observation(target="link", observed=observed).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=before, allow_symlink=True)

    assert "identity changed" in str(excinfo.value)
    assert observation.acl_reads == [], "the ACL must not be read after an identity change"
    assert observation.closed == [FAKE_DESCRIPTOR]


def test_symlink_opt_in_type_drift_refuses_and_closes(monkeypatch):
    """Contract 3 (semantic): an fstat type change refuses and closes the descriptor."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    before = _stat_result(stat.S_IFLNK, dev=11, ino=22)
    observed = _stat_result(stat.S_IFREG, dev=11, ino=22)
    observation = _Observation(target="link", observed=observed).install(monkeypatch)

    with pytest.raises(FilesystemSecurityError) as excinfo:
        has_macos_acl("link", expected_identity=before, allow_symlink=True)

    assert "not a symlink" in str(excinfo.value)
    assert observation.acl_reads == []
    assert observation.closed == [FAKE_DESCRIPTOR]


def test_descriptor_is_closed_on_every_raise_after_open(monkeypatch):
    """Contract 4 (semantic): each post-open refusal still closes the owned descriptor."""

    _darwin(monkeypatch)
    monkeypatch.setattr(os, "O_SYMLINK", O_SYMLINK, raising=False)
    link_info = _stat_result(stat.S_IFLNK)
    cases = [
        ("fstat failure", {"fstat_error": OSError(errno.EIO, "boom")}, "object is unavailable"),
        ("identity drift", {"observed": _stat_result(stat.S_IFLNK, ino=99)}, "identity changed"),
        ("type drift", {"observed": _stat_result(stat.S_IFREG)}, "not a symlink"),
        ("acl failure", {"acl_errno": errno.EIO}, "observation failed"),
    ]

    for label, options, expected in cases:
        with monkeypatch.context() as patch:
            kwargs = {"target": "link", "observed": link_info}
            kwargs.update(options)
            observation = _Observation(**kwargs).install(patch)
            with pytest.raises(FilesystemSecurityError) as excinfo:
                has_macos_acl("link", expected_identity=link_info, allow_symlink=True)
            assert expected in str(excinfo.value), label
            assert observation.closed == [FAKE_DESCRIPTOR], f"{label} leaked its descriptor"


def _manifest_tree(tmp_path):
    root = tmp_path / "release"
    (root / "macro_src").mkdir(parents=True)
    (root / "macro_src" / "engine.py").write_text("payload\n", encoding="utf-8")
    (root / "vendor").mkdir()
    (root / "vendor" / "macro").symlink_to("macro_src")
    (root / "vendor" / "note.txt").write_text("note\n", encoding="utf-8")
    return root


def _recording_manifest(monkeypatch, root):
    """Record which identity the manifest validated and what it handed to the observer."""

    validated = []
    observed = []

    def record_validate(info, *, label):
        validated.append((label, info))

    def record_observe(path, *, expected_identity=None, descriptor=None, allow_symlink=False):
        observed.append(
            {
                "path": Path(path).relative_to(root).as_posix(),
                "identity": expected_identity,
                "descriptor": descriptor,
                "allow_symlink": allow_symlink,
            }
        )
        return False

    monkeypatch.setattr(release_manifest, "_validate_owned_info", record_validate)
    monkeypatch.setattr(release_manifest, "has_macos_acl", record_observe)
    return validated, observed


def test_entries_passes_the_exact_validated_identity_for_every_entry(tmp_path, monkeypatch):
    """Contract 5 (semantic): the manifest hands over the very lstat it validated."""

    root = _manifest_tree(tmp_path)
    validated, observed = _recording_manifest(monkeypatch, root)

    entries = {entry["path"]: entry for entry in release_manifest._entries(root)}
    by_label = dict(validated)
    by_path = {item["path"]: item for item in observed}

    assert entries["vendor/macro"]["type"] == "symlink"
    assert entries["vendor/note.txt"]["type"] == "file"

    link_call = by_path["vendor/macro"]
    assert link_call["identity"] is by_label["vendor/macro"], "the validated lstat must be reused"
    assert link_call["allow_symlink"] is True
    assert link_call["allow_symlink"] == stat.S_ISLNK(link_call["identity"].st_mode)
    assert link_call["descriptor"] is None

    file_call = by_path["vendor/note.txt"]
    assert file_call["identity"] is by_label["vendor/note.txt"]
    assert file_call["allow_symlink"] is False
    assert stat.S_ISLNK(file_call["identity"].st_mode) is False

    assert set(by_path) == set(by_label)
    assert all(item["identity"] is not None for item in observed)
    assert all(item["descriptor"] is None for item in observed)
    assert all(
        item["allow_symlink"] == stat.S_ISLNK(item["identity"].st_mode) for item in observed
    )


def test_release_root_and_verify_pass_non_link_identities(tmp_path, monkeypatch):
    """Contract 5 (semantic): the root and manifest call sites never opt in."""

    root = _manifest_tree(tmp_path)
    root.chmod(0o755)
    (root / release_manifest.MANIFEST_NAME).write_text("{}\n", encoding="utf-8")
    validated, observed = _recording_manifest(monkeypatch, root)

    assert release_manifest._release_root(root) == root.resolve()
    root_call = {item["path"]: item for item in observed}["."]
    assert root_call["allow_symlink"] is False
    assert root_call["identity"] is dict(validated)["."]
    assert not stat.S_ISLNK(root_call["identity"].st_mode)

    with pytest.raises(release_manifest.ReleaseManifestError):
        release_manifest.verify(root, "a" * 40, "b" * 40)

    manifest_call = {item["path"]: item for item in observed}[release_manifest.MANIFEST_NAME]
    assert manifest_call["allow_symlink"] is False
    assert manifest_call["identity"] is dict(validated)[release_manifest.MANIFEST_NAME]
    assert not stat.S_ISLNK(manifest_call["identity"].st_mode)


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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
def test_entries_still_refuses_absolute_targets(tmp_path, monkeypatch):
    """Contract 4: opting in does not relax the pre-existing absolute-target refusal."""

    monkeypatch.setattr(
        release_manifest, "_validate_owned_info", lambda info, *, label: None
    )
    root = _production_shaped_root(tmp_path, {"abs": "/etc/hosts"})

    with pytest.raises(release_manifest.ReleaseManifestError) as excinfo:
        release_manifest._entries(root)
    assert "absolute release symlink is forbidden" in str(excinfo.value)


@pytest.mark.skipif(
    sys.platform != "darwin", reason="real O_SYMLINK ACL observation is Darwin-only"
)
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
