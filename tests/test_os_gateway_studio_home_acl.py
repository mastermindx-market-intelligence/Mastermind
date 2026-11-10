"""Focused adversarial tests for the home-directory ACL exception.

These tests are fully offline: they build temp-owned fixture trees, never
touch the live host home, private config, credentials, services, or installed
state, and never read another uid's bytes. Mechanical fixtures are disclosed:

1. ``reader.FIXED_OBSERVED_UID`` is monkeypatched to the current process uid
   so temp-owned fixtures qualify; the shipped constant remains 501.
2. ``reader.pwd`` is replaced with a fake account database so the sole
   pwd-qualified exception home is the disposable fixture directory. The real
   host home directory is never read or modified.
3. ``reader.has_macos_acl`` and ``reader.has_macos_everyone_deny_delete_only_acl``
   are monkeypatched at the reader boundary for reader-wiring tests, and
   ``fs_security._bind_acl_classifier_functions`` is replaced with a pure
   Python fake libc for classifier-logic tests. These mocks exercise the
   production predicates only; they are disclosure, never native proof. The
   Darwin-only classes at the bottom run the real libc, real ``chmod +a``
   ACLs, and the real classifier on disposable directories owned by this
   test process; off Darwin they skip and claim nothing.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid as uuid_module
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane import fs_security
from control_plane.fs_security import (
    FilesystemSecurityError,
    has_macos_everyone_deny_delete_only_acl,
)
from ops.executive_os import os_gateway_studio_reader as reader

CURRENT_UID = os.getuid()
CURRENT_GID = os.getgid()
FOREIGN_UID = 4242
FOREIGN_GID = CURRENT_GID + 1 if CURRENT_GID != 4242 else 4243
INSTANCE = "mastermind-os-publication"
PLIST_NAME = f"com.mastermind.studio-direct-private.{INSTANCE}.plist"
IS_DARWIN = sys.platform == "darwin"


# ---------------------------------------------------------------------------
# Pure-Python fake libc ACL family for classifier-logic tests
# ---------------------------------------------------------------------------


def _fake_encode_acl(entries: list[dict]) -> bytes:
    """A deterministic external encoding in the spirit of acl_copy_ext."""

    out = bytearray()
    out += len(entries).to_bytes(4, "big")
    out += (0).to_bytes(4, "big")  # ACL-level flags
    for entry in entries:
        out += int(entry["tag"]).to_bytes(4, "big")
        out += int(entry["flags"]).to_bytes(4, "big")
        out += int(entry["perms"]).to_bytes(8, "big")
        out += entry["uuid"]
    return bytes(out)


def cleanup_owned_fixture(name):
    # Only fresh directories created by this test; never live Home or state.
    root = Path(name)
    if IS_DARWIN:
        for item in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True) + [root]:
            if not item.is_symlink():
                subprocess.run(["/bin/chmod", "-N", str(item)], capture_output=True, check=True)
    shutil.rmtree(root)


class FakeAclLib:
    """Fake libc ACL family with the same call shapes and errno behavior."""

    def __init__(
        self,
        observed_entries: list[dict] | None,
        *,
        get_fd_errno: int | None = None,
        failures: dict[str, object] | None = None,
        uuid_bytes: bytes | None = None,
        free_result: int = 0,
        ext_short: bool = False,
        acl_size_value: int | None = None,
    ) -> None:
        self._next = 1
        self.objects: dict[int, object] = {}
        self.observed_entries = observed_entries
        self.get_fd_errno = get_fd_errno
        self.failures = dict(failures or {})
        self.uuid_bytes = uuid_bytes or uuid_module.uuid5(
            uuid_module.NAMESPACE_DNS, "everyone-fake"
        ).bytes
        self.free_result = free_result
        self.ext_short = ext_short
        self.acl_size_value = acl_size_value
        self.freed: list[tuple[int, str]] = []
        self.built_entries: list[dict] = []

    def _handle(self, obj: object) -> int:
        handle = self._next
        self._next += 1
        self.objects[handle] = obj
        return handle

    @staticmethod
    def _h(handle: object) -> int:
        """Normalize a handle that may arrive as a c_void_p instance."""

        value = getattr(handle, "value", handle)
        if not isinstance(value, int):
            raise TypeError("fake ACL family received a non-integer handle")
        return value

    # -- family ------------------------------------------------------------
    def acl_get_fd(self, fd: int) -> int:
        if self.observed_entries is None:
            ctypes.set_errno(
                errno.ENOENT if self.get_fd_errno is None else self.get_fd_errno
            )
            return 0
        ctypes.set_errno(0)
        # A None uuid means "the everyone qualifier this fake libc maps to".
        entries = [
            dict(entry, uuid=self.uuid_bytes if entry["uuid"] is None else entry["uuid"])
            for entry in self.observed_entries
        ]
        return self._handle(entries)

    def acl_free(self, handle: int) -> int:
        obj = self.objects.pop(self._h(handle), None)
        kind = "entry" if isinstance(obj, dict) and "acl" in obj else "acl"
        self.freed.append((handle, kind))
        return self.free_result

    def acl_init(self, count: int) -> int:
        if self.failures.get("acl_init"):
            return 0
        return self._handle({"entries": []})

    def acl_create_entry(self, acl_handle: int, ref: object) -> int:
        if self.failures.get("acl_create_entry"):
            return -1
        acl_value = ctypes.cast(acl_handle, ctypes.POINTER(ctypes.c_void_p)).contents.value
        acl = self.objects[self._h(acl_value)]
        entry = {"acl": acl, "tag": 0, "flags": 0, "perms": 0, "uuid": b"\0" * 16}
        entry_handle = self._handle(entry)
        # The entry lives inside its acl_t; later set_* calls mutate this
        # same dict, so the acl's external encoding tracks them.
        acl["entries"].append(entry)
        ctypes.cast(ref, ctypes.POINTER(ctypes.c_void_p)).contents.value = entry_handle
        return 0

    def _entry(self, entry_handle: int) -> dict:
        entry = self.objects[self._h(entry_handle)]
        assert isinstance(entry, dict) and "acl" in entry
        return entry

    def acl_set_tag_type(self, entry_handle: int, tag: int) -> int:
        if self.failures.get("acl_set_tag_type"):
            return -1
        self._entry(entry_handle)["tag"] = tag
        return 0

    def acl_set_qualifier(self, entry_handle: int, qualifier: object) -> int:
        if self.failures.get("acl_set_qualifier"):
            return -1
        raw = ctypes.cast(qualifier, ctypes.POINTER(ctypes.c_char * 16)).contents
        self._entry(entry_handle)["uuid"] = bytes(raw)
        return 0

    def acl_set_permset_mask_np(self, entry_handle: int, mask: int) -> int:
        if self.failures.get("acl_set_permset_mask_np"):
            return -1
        self._entry(entry_handle)["perms"] = mask
        return 0

    def acl_size(self, handle: int) -> int:
        if self.acl_size_value is not None:
            return self.acl_size_value
        obj = self.objects[self._h(handle)]
        entries = obj if isinstance(obj, list) else obj["entries"]  # type: ignore[index]
        return len(_fake_encode_acl(entries))

    def acl_copy_ext_native(self, buffer: object, acl_handle: int, size: int) -> int:
        obj = self.objects[self._h(acl_handle)]
        entries = obj if isinstance(obj, list) else obj["entries"]  # type: ignore[index]
        data = _fake_encode_acl(entries)
        if self.ext_short or size < len(data):
            ctypes.set_errno(errno.ENOMEM)
            return -1
        ctypes.memmove(buffer, data, len(data))
        return len(data)

    def mbr_gid_to_uuid(self, gid: int, out: object) -> int:
        ctypes.memmove(out, self.uuid_bytes, 16)
        return -1 if self.failures.get("mbr_gid_to_uuid") else 0


def _deny_everyone_delete(flags: int = 0, uuid: bytes | None = None) -> dict:
    return {
        "tag": 2,
        "flags": flags,
        "perms": 16,
        "uuid": uuid,
    }


class ClassifierMockedLibcTests(unittest.TestCase):
    """Classifier logic against a fake libc; this is not native proof."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="acl-classifier-", dir=REPO_ROOT)
        self.addCleanup(cleanup_owned_fixture, self._tmp)
        self.dir_path = Path(self._tmp) / "home"
        self.dir_path.mkdir()
        self.fd = os.open(self.dir_path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.fd)
        self.identity = os.fstat(self.fd)

    def classify(self, lib: FakeAclLib, *, fd: int | None = None, identity=None) -> object:
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(
            fs_security, "_bind_acl_classifier_functions", return_value=lib
        ), mock.patch.object(
            fs_security.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=99, gr_name="everyone")
        ):
            return has_macos_everyone_deny_delete_only_acl(
                descriptor=self.fd if fd is None else fd,
                expected_identity=self.identity if identity is None else identity,
            )

    def test_sdk_pointer_and_membership_status_signatures(self):
        names = fs_security._AclClassifierBindings._fields
        library = SimpleNamespace(**{name: mock.Mock() for name in names})
        with mock.patch.object(ctypes, "CDLL", return_value=library):
            bound = fs_security._bind_acl_classifier_functions()
        self.assertEqual(bound.acl_create_entry.argtypes, [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)])
        self.assertEqual(bound.mbr_gid_to_uuid.restype, ctypes.c_int)
        self.assertEqual(bound.mbr_gid_to_uuid.argtypes, [ctypes.c_uint32, ctypes.POINTER(ctypes.c_ubyte)])
        self.assertEqual(bound.acl_set_tag_type.argtypes, [ctypes.c_void_p, ctypes.c_int])

    def test_exact_single_deny_delete_entry_is_true(self) -> None:
        lib = FakeAclLib([_deny_everyone_delete()])
        self.assertTrue(self.classify(lib))
        # Both the observed and the expected acl_t were released; the entry
        # handle is owned by its acl_t and is never freed separately.
        self.assertEqual(
            sorted(kind for _, kind in lib.freed), ["acl", "acl"]
        )

    def test_expected_entry_shape_built_through_api(self) -> None:
        lib = FakeAclLib([_deny_everyone_delete()])
        captured: dict = {}

        original_create = lib.acl_create_entry

        def create(acl_handle: int, ref: object) -> int:
            captured["acl"] = lib.objects[ctypes.cast(acl_handle, ctypes.POINTER(ctypes.c_void_p)).contents.value]
            return original_create(acl_handle, ref)

        lib.acl_create_entry = create  # type: ignore[method-assign]
        self.assertTrue(self.classify(lib))
        entries = captured["acl"]["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tag"], 2)
        self.assertEqual(entries[0]["perms"], 16)
        self.assertEqual(entries[0]["flags"], 0)
        self.assertEqual(entries[0]["uuid"], lib.uuid_bytes)

    def test_membership_failure_even_with_populated_buffer_refuses(self):
        lib = FakeAclLib([_deny_everyone_delete()], failures={"mbr_gid_to_uuid": True})
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)
        self.assertEqual(len(lib.freed), 2)

    def test_both_acl_handles_are_freed_when_first_free_fails(self):
        lib = FakeAclLib([_deny_everyone_delete()], free_result=-1)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)
        self.assertEqual(len(lib.freed), 2)

    def test_missing_acl_returns_false(self) -> None:
        lib = FakeAclLib(None)
        self.assertIs(self.classify(lib), False)

    def test_null_acl_with_kernel_error_refuses(self) -> None:
        lib = FakeAclLib(None, get_fd_errno=errno.EPERM)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)

    def test_allow_entry_instead_of_deny_is_false(self) -> None:
        entry = _deny_everyone_delete()
        entry["tag"] = 1
        self.assertIs(self.classify(FakeAclLib([entry])), False)

    def test_extra_rights_are_false(self) -> None:
        entry = _deny_everyone_delete()
        entry["perms"] = 16 | 1  # delete + read_data
        self.assertIs(self.classify(FakeAclLib([entry])), False)

    def test_inherited_flag_is_false(self) -> None:
        entry = _deny_everyone_delete(flags=0x10)
        self.assertIs(self.classify(FakeAclLib([entry])), False)

    def test_unknown_flag_is_false(self) -> None:
        entry = _deny_everyone_delete(flags=1 << 12)
        self.assertIs(self.classify(FakeAclLib([entry])), False)

    def test_other_principal_is_false(self) -> None:
        entry = _deny_everyone_delete(uuid=b"\xbb" * 16)
        self.assertIs(self.classify(FakeAclLib([entry])), False)

    def test_extra_entry_is_false(self) -> None:
        entries = [_deny_everyone_delete(), _deny_everyone_delete()]
        self.assertIs(self.classify(FakeAclLib(entries)), False)

    def test_empty_observed_acl_is_false(self) -> None:
        self.assertIs(self.classify(FakeAclLib([])), False)

    def test_constructor_failures_refuse(self) -> None:
        for failure in (
            "acl_init",
            "acl_create_entry",
            "acl_set_tag_type",
            "acl_set_qualifier",
            "acl_set_permset_mask_np",
        ):
            with self.subTest(failure=failure):
                lib = FakeAclLib([_deny_everyone_delete()], failures={failure: True})
                with self.assertRaises(FilesystemSecurityError):
                    self.classify(lib)

    def test_unbounded_or_short_external_refusals(self) -> None:
        lib = FakeAclLib([_deny_everyone_delete()], acl_size_value=0)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)
        lib = FakeAclLib([_deny_everyone_delete()], acl_size_value=1 << 20)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)
        lib = FakeAclLib([_deny_everyone_delete()], ext_short=True)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)

    def test_failed_acl_free_refuses(self) -> None:
        lib = FakeAclLib([_deny_everyone_delete()], free_result=-1)
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib)

    def test_identity_drift_refuses(self) -> None:
        other = Path(self._tmp) / "other"
        other.mkdir()
        fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        lib = FakeAclLib([_deny_everyone_delete()])
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib, fd=fd, identity=self.identity)

    def test_non_directory_identity_refuses(self) -> None:
        file_path = Path(self._tmp) / "file"
        file_path.write_bytes(b"x")
        fd = os.open(file_path, os.O_RDONLY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        lib = FakeAclLib([_deny_everyone_delete()])
        with self.assertRaises(FilesystemSecurityError):
            self.classify(lib, fd=fd, identity=os.fstat(fd))

    def test_identity_change_around_read_refuses(self) -> None:
        real_fstat = os.fstat
        calls = {"n": 0}

        def changing_fstat(fd: int) -> os.stat_result:
            calls["n"] += 1
            info = real_fstat(fd)
            if calls["n"] == 1:
                return info
            fields = {
                "st_atime_ns": info.st_atime_ns,
                "st_mtime_ns": info.st_mtime_ns + 1,
                "st_ctime_ns": info.st_ctime_ns,
            }
            return os.stat_result(tuple(info), fields)

        lib = FakeAclLib([_deny_everyone_delete()])
        with mock.patch.object(os, "fstat", changing_fstat):
            with self.assertRaises(FilesystemSecurityError):
                self.classify(lib)
        self.assertGreaterEqual(calls["n"], 2)

    def test_classifier_never_opens_a_path(self) -> None:
        def no_open(*args, **kwargs):  # pragma: no cover - guard
            raise AssertionError("classifier opened a path")

        lib = FakeAclLib([_deny_everyone_delete()])
        with mock.patch.object(os, "open", no_open):
            self.assertTrue(self.classify(lib))

    def test_malformed_descriptor_refuses_before_any_platform_or_open(self) -> None:
        for bad in (True, None, "3", 3.0, -1):
            with self.subTest(descriptor=bad):
                with self.assertRaises(FilesystemSecurityError):
                    has_macos_everyone_deny_delete_only_acl(
                        descriptor=bad, expected_identity=self.identity
                    )

    def test_malformed_identity_refuses_before_any_platform_or_open(self) -> None:
        for bad in (None, "stat", (1, 2), SimpleNamespace(st_mode=0)):
            with self.subTest(identity=bad):
                with self.assertRaises(FilesystemSecurityError):
                    has_macos_everyone_deny_delete_only_acl(
                        descriptor=self.fd, expected_identity=bad
                    )

    def test_off_darwin_refuses_instead_of_passing(self) -> None:
        if IS_DARWIN:
            self.skipTest("only meaningful off Darwin")
        with self.assertRaises(FilesystemSecurityError):
            has_macos_everyone_deny_delete_only_acl(
                descriptor=self.fd, expected_identity=self.identity
            )

    def test_unavailable_native_api_refuses(self) -> None:
        if IS_DARWIN:
            self.skipTest("native libc always present on Darwin")
        with mock.patch.object(sys, "platform", "darwin"):
            with self.assertRaises(FilesystemSecurityError):
                has_macos_everyone_deny_delete_only_acl(
                    descriptor=self.fd, expected_identity=self.identity
                )

    def test_everyone_group_failures_refuse(self) -> None:
        lib = FakeAclLib([_deny_everyone_delete()])
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(
            fs_security, "_bind_acl_classifier_functions", return_value=lib
        ), mock.patch.object(
            fs_security.grp,
            "getgrnam",
            side_effect=KeyError("everyone"),
        ):
            with self.assertRaises(FilesystemSecurityError):
                has_macos_everyone_deny_delete_only_acl(
                    descriptor=self.fd, expected_identity=self.identity
                )
        lib = FakeAclLib([_deny_everyone_delete()], uuid_bytes=bytes(16))
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(
            fs_security, "_bind_acl_classifier_functions", return_value=lib
        ), mock.patch.object(
            fs_security.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=99, gr_name="everyone")
        ):
            with self.assertRaises(FilesystemSecurityError):
                has_macos_everyone_deny_delete_only_acl(
                    descriptor=self.fd, expected_identity=self.identity
                )


# ---------------------------------------------------------------------------
# Reader fixtures
# ---------------------------------------------------------------------------


class PwdFixture:
    """Fake account database whose record can drift between calls."""

    def __init__(self, *records: object) -> None:
        self._records = list(records)
        self.calls: list[int] = []

    def getpwuid(self, uid: int):
        self.calls.append(uid)
        if not self._records:
            raise KeyError(uid)
        record = self._records.pop(0) if len(self._records) > 1 else self._records[0]
        if record is None:
            raise KeyError(uid)
        return record


def pwd_record(home: str, uid: int, gid: int):
    return SimpleNamespace(pw_dir=home, pw_uid=uid, pw_gid=gid, pw_name="fixture")


def acl_presence_for(inodes: set[int]):
    """has_macos_acl double: ACL present exactly on the given inodes."""

    def _acl(path, **kwargs):
        descriptor = kwargs.get("descriptor")
        if descriptor is not None:
            return os.fstat(descriptor).st_ino in inodes
        return os.lstat(path).st_ino in inodes

    return _acl


def permissive_classifier(calls: list[int]):
    """Classifier double that approves every descriptor it is asked about."""

    def _classifier(*, descriptor: int, expected_identity) -> bool:
        calls.append(os.fstat(descriptor).st_ino)
        return True

    return _classifier


def refusing_classifier(calls: list[int]):
    def _classifier(*, descriptor: int, expected_identity):
        calls.append(os.fstat(descriptor).st_ino)
        return False

    return _classifier


def failing_classifier(calls: list[int]):
    def _classifier(*, descriptor: int, expected_identity):
        calls.append(os.fstat(descriptor).st_ino)
        raise FilesystemSecurityError("macOS ACL observation failed: errno=1")

    return _classifier


@contextlib.contextmanager
def counted_reads(counts: dict):
    real_read = os.read
    real_fstat = os.fstat

    def read(fd: int, size: int) -> bytes:
        data = real_read(fd, size)
        inode = real_fstat(fd).st_ino
        counts[inode] = counts.get(inode, 0) + 1
        return data

    os.read = read
    try:
        yield
    finally:
        os.read = real_read


_STAT_INDEX = {
    "st_mode": 0,
    "st_ino": 1,
    "st_dev": 2,
    "st_nlink": 3,
    "st_uid": 4,
    "st_gid": 5,
    "st_size": 6,
}


def _mutate_stat(info: os.stat_result, **changes) -> os.stat_result:
    fields = list(info)[:10]
    for name, value in changes.items():
        fields[_STAT_INDEX[name]] = value
    return os.stat_result(
        tuple(fields),
        {
            "st_atime_ns": info.st_atime_ns,
            "st_mtime_ns": info.st_mtime_ns,
            "st_ctime_ns": info.st_ctime_ns,
        },
    )


class HomeAclFixture:
    """One temp-owned publication tree; builds like the original suite's."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.base = self.home / ".local" / "share" / "studio-direct-mcp" / "private" / INSTANCE
        self.node_modules = self.base / "node_modules"
        self.tools = self.home / "tools"

    def build(self) -> "HomeAclFixture":
        self.base.mkdir(parents=True)
        self.node_modules.mkdir()
        (self.node_modules / "pkg").mkdir()
        (self.node_modules / "pkg" / "index.js").write_bytes(b"console.log('index')\n")
        (self.node_modules / "vendor").mkdir()
        (self.node_modules / "vendor" / "lib.js").write_bytes(b"module.exports=1;\n")
        (self.base / "manifest.json").write_bytes(
            json.dumps(
                {
                    "node": str(self.tools / "node"),
                    "backend": str(self.tools / "backend" / "server.py"),
                    "release": "inert-fixture",
                }
            ).encode("utf-8")
        )
        (self.base / "config.json").write_bytes(b'{"mode":"inert"}\n')
        (self.base / "app.py").write_bytes(b"print('staged app')\n")
        launch = self.home / "Library" / "LaunchAgents"
        launch.mkdir(parents=True)
        (launch / PLIST_NAME).write_bytes(b"<plist><dict/></plist>\n")
        node = self.tools / "node"
        node.parent.mkdir(parents=True)
        node.write_bytes(b"#!/bin/sh\nexit 0\n")
        node.chmod(0o755)
        backend_dir = self.tools / "backend"
        backend_dir.mkdir()
        (backend_dir / "server.py").write_bytes(b"print('backend')\n")
        return self

    def inode(self, path: Path) -> int:
        return os.lstat(path).st_ino

    def observe(self, home=None, uid=CURRENT_UID, gid=CURRENT_GID):
        return reader.observe_studio_files(
            home=self.home if home is None else home,
            uid=uid,
            gid=gid,
            source_file_names=("app.py",),
        )


@contextlib.contextmanager
def reader_overrides(
    *,
    pwd_fixture: PwdFixture | None = None,
    acl_presence=None,
    classifier=None,
):
    saved = (
        reader.FIXED_OBSERVED_UID,
        reader.pwd,
        reader.has_macos_acl,
        reader.has_macos_everyone_deny_delete_only_acl,
        reader._PrefixMutationGuard,
    )
    if not IS_DARWIN:
        # Only the mechanical fixture supplies a non-native queue seam;
        # native classifier/event integration continues to use real Darwin.
        from test_os_gateway_studio_prefix_identity import MechanicalPrefixGuard
        reader._PrefixMutationGuard = MechanicalPrefixGuard
    reader.FIXED_OBSERVED_UID = CURRENT_UID
    if pwd_fixture is not None:
        reader.pwd = pwd_fixture
    if acl_presence is not None:
        reader.has_macos_acl = acl_presence
    if classifier is not None:
        reader.has_macos_everyone_deny_delete_only_acl = classifier
    try:
        yield
    finally:
        (
            reader.FIXED_OBSERVED_UID,
            reader.pwd,
            reader.has_macos_acl,
            reader.has_macos_everyone_deny_delete_only_acl,
            reader._PrefixMutationGuard,
        ) = saved


class HomeAclReaderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="acl-reader-", dir=REPO_ROOT)
        self.addCleanup(cleanup_owned_fixture, self._tmp)
        self.fx = HomeAclFixture(Path(self._tmp) / "fx").build()

    def assertRefused(self, fn, *args, **kwargs) -> None:
        with self.assertRaises(reader.StudioObservationError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(str(caught.exception), "gateway_studio_invalid")


# ---------------------------------------------------------------------------
# Reader: the single exception is wired only through the qualified home
# ---------------------------------------------------------------------------


class ReaderExceptionWiringTests(HomeAclReaderTestCase):
    def test_no_acl_behavior_preserved_without_any_fixture(self) -> None:
        """Real helpers, no pwd fixture: the original no-ACL rules hold."""

        with reader_overrides():
            observation = self.fx.observe()
        self.assertTrue(observation.node_sha256)
        self.assertEqual(
            observation.installed_file_hashes["app.py"],
            hashlib.sha256(b"print('staged app')\n").hexdigest(),
        )

    def test_qualified_home_with_exact_acl_is_observed(self) -> None:
        calls: list[int] = []
        home_ino = self.fx.inode(self.fx.home)
        pwd_fixture = PwdFixture(
            pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
        )
        with reader_overrides(
            pwd_fixture=pwd_fixture,
            acl_presence=acl_presence_for({home_ino}),
            classifier=permissive_classifier(calls),
        ):
            observation = self.fx.observe()
        self.assertTrue(observation.node_sha256)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {home_ino})
        # The pwd binding was resolved at entry, at every application, and
        # at the final check.
        self.assertGreaterEqual(len(pwd_fixture.calls), 3)

    def test_unknown_acl_presence_cannot_use_permissive_classifier(self):
        calls = []
        home_ino = self.fx.inode(self.fx.home)
        def presence(path, *, descriptor, expected_identity):
            return None if os.fstat(descriptor).st_ino == home_ino else False
        with reader_overrides(pwd_fixture=PwdFixture(pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)), acl_presence=presence, classifier=permissive_classifier(calls)):
            self.assertRefused(self.fx.observe)
        self.assertEqual(calls, [])

    def test_permissive_classifier_still_refuses_acl_outside_fixed_directories(self) -> None:
        """Only the walk's component gate admits the exception, not the flag."""

        for label, target in (
            ("metadata-subdir", self.fx.home / ".local"),
            ("library-child", self.fx.home / "Library" / "LaunchAgents"),
            ("dependency-dir", self.fx.node_modules),
            ("home-ancestor", self.fx.root),
        ):
            with self.subTest(target=label):
                calls: list[int] = []
                with reader_overrides(
                    pwd_fixture=PwdFixture(
                        pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
                    ),
                    acl_presence=acl_presence_for({self.fx.inode(target)}),
                    classifier=permissive_classifier(calls),
                ), counted_reads({}):
                    self.assertRefused(self.fx.observe)
                self.assertEqual(calls, [])

    def test_acl_at_manifest_refuses_and_is_never_read(self) -> None:
        manifest_ino = self.fx.inode(self.fx.base / "manifest.json")
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
            ),
            acl_presence=acl_presence_for({manifest_ino}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertNotIn(manifest_ino, counts)

    def test_acl_at_tool_leaf_refuses_before_its_bytes(self) -> None:
        node_ino = self.fx.inode(self.fx.tools / "node")
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
            ),
            acl_presence=acl_presence_for({node_ino}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertNotIn(node_ino, counts)

    def test_acl_at_dependency_leaf_refuses(self) -> None:
        dep_ino = self.fx.inode(self.fx.node_modules / "pkg" / "index.js")
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
            ),
            acl_presence=acl_presence_for({dep_ino}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertNotIn(dep_ino, counts)

    def test_acl_at_other_home_refuses(self) -> None:
        other = HomeAclFixture(Path(self._tmp) / "other").build()
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID)
            ),
            acl_presence=acl_presence_for({self.fx.inode(other.home)}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe, home=other.home)
        self.assertNotIn(self.fx.inode(other.home), counts)
        manifest_ino = other.inode(other.base / "manifest.json")
        self.assertNotIn(manifest_ino, counts)


# ---------------------------------------------------------------------------
# Reader: the pwd qualification itself
# ---------------------------------------------------------------------------


class ReaderPwdQualificationTests(HomeAclReaderTestCase):
    home_ino_property = None

    def qualified(self):
        return PwdFixture(pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID))

    def test_gid_mismatch_leaves_no_exception(self) -> None:
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, FOREIGN_GID)
            ),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})

    def test_uid_record_mismatch_leaves_no_exception(self) -> None:
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), FOREIGN_UID, CURRENT_GID)
            ),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})

    def test_missing_pwd_record_leaves_no_exception(self) -> None:
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})

    def test_malformed_pwd_home_leaves_no_exception(self) -> None:
        for label, raw in (
            ("relative", "relative/home"),
            ("non-normalized", str(self.fx.home) + "/."),
            ("empty", ""),
            ("not-a-string", 4711),
        ):
            with self.subTest(pwd_home=label):
                counts: dict = {}
                with reader_overrides(
                    pwd_fixture=PwdFixture(
                        pwd_record(raw, CURRENT_UID, CURRENT_GID)
                    ),
                    acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
                    classifier=permissive_classifier([]),
                ), counted_reads(counts):
                    self.assertRefused(self.fx.observe)
                self.assertEqual(counts, {})

    def test_pwd_drift_at_application_refuses(self) -> None:
        drift_home = self.fx.root / "drift-home"
        drift_home.mkdir()
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=PwdFixture(
                pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID),
                pwd_record(str(drift_home), CURRENT_UID, CURRENT_GID),
            ),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=permissive_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})

    def test_classifier_false_on_home_acl_refuses(self) -> None:
        counts: dict = {}
        calls: list[int] = []
        with reader_overrides(
            pwd_fixture=self.qualified(),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=refusing_classifier(calls),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})
        self.assertEqual(set(calls), {self.fx.inode(self.fx.home)})

    def test_classifier_error_on_home_acl_refuses(self) -> None:
        counts: dict = {}
        with reader_overrides(
            pwd_fixture=self.qualified(),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=failing_classifier([]),
        ), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertEqual(counts, {})

    def test_input_uid_and_gid_gates_unchanged(self) -> None:
        with reader_overrides(
            pwd_fixture=self.qualified(),
            acl_presence=acl_presence_for({self.fx.inode(self.fx.home)}),
            classifier=permissive_classifier([]),
        ):
            self.assertRefused(self.fx.observe, uid=FOREIGN_UID)
            self.assertRefused(self.fx.observe, gid=-1)
            self.assertRefused(self.fx.observe, uid=True)


# ---------------------------------------------------------------------------
# Native Darwin: real libc, real chmod ACLs, own disposable dirs only
# ---------------------------------------------------------------------------


@unittest.skipUnless(IS_DARWIN, "native libc ACL classification is Darwin-only")
class NativeClassifierDarwinTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="acl-native-", dir=REPO_ROOT)
        self.addCleanup(cleanup_owned_fixture, self._tmp)

    def _dir(self, name: str) -> Path:
        path = Path(self._tmp) / name
        path.mkdir()
        return path

    def _open(self, path: Path) -> tuple[int, os.stat_result]:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        return fd, os.fstat(fd)

    def _chmod_acl(self, path: Path, entry: str) -> None:
        subprocess.run(
            ["/bin/chmod", "+a", entry, str(path)], check=True, capture_output=True
        )

    def test_exact_acl_classifies_true(self) -> None:
        path = self._dir("home")
        self._chmod_acl(path, "everyone deny delete")
        fd, info = self._open(path)
        self.assertTrue(has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info))

    def test_no_acl_classifies_false(self) -> None:
        path = self._dir("plain")
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_acl_removed_classifies_false(self) -> None:
        path = self._dir("removed")
        self._chmod_acl(path, "everyone deny delete")
        subprocess.run(["/bin/chmod", "-N", str(path)], check=True, capture_output=True)
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_extra_entry_classifies_false(self) -> None:
        path = self._dir("extra")
        self._chmod_acl(path, "everyone deny delete")
        self._chmod_acl(path, "everyone allow read")
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_allow_instead_of_deny_classifies_false(self) -> None:
        path = self._dir("allow")
        self._chmod_acl(path, "everyone allow delete")
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_extra_right_classifies_false(self) -> None:
        path = self._dir("rights")
        self._chmod_acl(path, "everyone deny delete,writeattr")
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_other_principal_classifies_false(self) -> None:
        path = self._dir("principal")
        self._chmod_acl(path, "group:wheel deny delete")
        fd, info = self._open(path)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_inherited_entry_classifies_false(self) -> None:
        parent = self._dir("parent")
        self._chmod_acl(parent, "everyone deny delete,file_inherit,directory_inherit")
        child = parent / "child"
        child.mkdir()
        fd, info = self._open(child)
        self.assertIs(
            has_macos_everyone_deny_delete_only_acl(descriptor=fd, expected_identity=info),
            False,
        )

    def test_regular_file_identity_refuses(self) -> None:
        path = self._dir("file-holder") / "file"
        path.write_bytes(b"x")
        self._chmod_acl(path, "everyone deny delete")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        self.addCleanup(os.close, fd)
        with self.assertRaises(FilesystemSecurityError):
            has_macos_everyone_deny_delete_only_acl(
                descriptor=fd, expected_identity=os.fstat(fd)
            )

    def test_identity_drift_refuses(self) -> None:
        a = self._dir("drift-a")
        b = self._dir("drift-b")
        self._chmod_acl(a, "everyone deny delete")
        fd_a, _ = self._open(a)
        _fd_b, info_b = self._open(b)
        with self.assertRaises(FilesystemSecurityError):
            has_macos_everyone_deny_delete_only_acl(descriptor=fd_a, expected_identity=info_b)

    def test_everyone_group_resolves_through_real_grparent(self) -> None:
        import grp as grp_module

        record = grp_module.getgrnam("everyone")
        self.assertTrue(isinstance(record.gr_gid, int))


@unittest.skipUnless(IS_DARWIN, "native reader ACL observation is Darwin-only")
class NativeReaderDarwinTests(HomeAclReaderTestCase):
    """Real ACLs on own dirs; the pwd record stays a disclosed fixture."""

    def test_native_home_acl_observes_end_to_end(self) -> None:
        home_ino = self.fx.inode(self.fx.home)
        subprocess.run(
            ["/bin/chmod", "+a", "everyone deny delete", str(self.fx.home)],
            check=True,
            capture_output=True,
        )
        self.addCleanup(
            subprocess.run,
            ["/bin/chmod", "-N", str(self.fx.home)],
            capture_output=True,
        )
        pwd_fixture = PwdFixture(pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID))
        with reader_overrides(pwd_fixture=pwd_fixture):
            observation = self.fx.observe()
        self.assertTrue(observation.node_sha256)

    def test_native_acl_on_manifest_refuses_before_payload(self) -> None:
        manifest = self.fx.base / "manifest.json"
        subprocess.run(
            ["/bin/chmod", "+a", "everyone deny delete", str(manifest)],
            check=True,
            capture_output=True,
        )
        self.addCleanup(
            subprocess.run,
            ["/bin/chmod", "-N", str(manifest)],
            capture_output=True,
        )
        pwd_fixture = PwdFixture(pwd_record(str(self.fx.home), CURRENT_UID, CURRENT_GID))
        counts: dict = {}
        with reader_overrides(pwd_fixture=pwd_fixture), counted_reads(counts):
            self.assertRefused(self.fx.observe)
        self.assertNotIn(self.fx.inode(manifest), counts)

    def test_native_inherited_acl_on_subdir_refuses(self) -> None:
        home = self.fx.home
        subprocess.run(
            ["/bin/chmod", "+a", "everyone deny delete,file_inherit,directory_inherit", str(home)],
            check=True,
            capture_output=True,
        )
        self.addCleanup(
            subprocess.run,
            ["/bin/chmod", "-N", str(home)],
            capture_output=True,
        )
        child = home / "Library" / "LaunchAgents" / "inherited-dir"
        child.mkdir()
        pwd_fixture = PwdFixture(pwd_record(str(home), CURRENT_UID, CURRENT_GID))
        with reader_overrides(pwd_fixture=pwd_fixture):
            self.assertRefused(self.fx.observe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
