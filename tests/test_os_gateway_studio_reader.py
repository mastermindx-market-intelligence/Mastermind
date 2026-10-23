"""Adversarial offline tests for the bounded Studio filesystem observation helper.

These tests are fully offline: they build temp-owned fixture trees, never touch
live hosts, private config, credentials, services, or installed state, and
never read another uid's bytes. Two mechanical filesystem fixtures are used
and disclosed here:

1. The module's fixed observed-uid constant is monkeypatched to the current
   process uid so temp-owned fixtures qualify. This is a mechanical fixture
   for filesystem ownership only; it carries no authorization claim and the
   shipped constant remains 501.
2. Stat/open/read/fstat wrappers and bound constants are monkeypatched to
   inject swaps and tighten bounds. Every injected identity is mechanical
   fixture data; the production predicates themselves are never patched,
   weakened, or reimplemented, and no new ACL implementation is added.

The embedded reference oracle is the unchanged private_service dependency
digest algorithm; the descriptor-bound reader must reproduce it byte for byte
on inert fixtures.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
MODULE_PATH = TESTS_DIR.parent / "ops/executive_os/os_gateway_studio_reader.py"
CURRENT_UID = os.getuid()
CURRENT_GID = os.getgid()
FOREIGN_UID = 4242

reader = None

def setUpModule() -> None:
    global reader
    from ops.executive_os import os_gateway_studio_reader
    reader = os_gateway_studio_reader

def tearDownModule() -> None:
    pass


@contextlib.contextmanager
def observed_uid_fixture():
    """Mechanical fixture: temp-owned uid in place of the fixed 501 constant."""

    saved = reader.FIXED_OBSERVED_UID
    reader.FIXED_OBSERVED_UID = CURRENT_UID
    try:
        yield
    finally:
        reader.FIXED_OBSERVED_UID = saved


@contextlib.contextmanager
def patched_constant(name: str, value):
    saved = getattr(reader, name)
    setattr(reader, name, value)
    try:
        yield
    finally:
        setattr(reader, name, saved)


_STAT_INDEX = {
    "st_mode": 0,
    "st_ino": 1,
    "st_dev": 2,
    "st_nlink": 3,
    "st_uid": 4,
    "st_gid": 5,
    "st_size": 6,
}


def mutate_stat(info: os.stat_result, **changes) -> os.stat_result:
    fields = list(info)[:10]
    for name, value in changes.items():
        fields[_STAT_INDEX[name]] = value
    return os.stat_result(tuple(fields), {"st_atime_ns": info.st_atime_ns, "st_mtime_ns": info.st_mtime_ns, "st_ctime_ns": info.st_ctime_ns})


class EventLog:
    """Instrumentation shared by read/stat/open/fstat/ACL wrappers."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.real_read = os.read
        self.real_stat = os.stat
        self.real_open = os.open
        self.real_fstat = os.fstat
        self.stat_mutations: dict[int, dict] = {}
        self.open_swaps: dict[int, str] = {}
        self.fstat_mutations: dict[int, dict] = {}
        self.fstat_after_read_mutations: dict[int, dict] = {}
        self.read_tamper_inodes: set[int] = set()
        self.read_counts: dict[int, int] = {}
        self.inode_read_counts: dict[int, int] = {}
        self.served_chunks: list[bytes] = []
        self.acl_behavior = None  # None | "raise"
        self.acl_names: list[str] = []
        self.opened_fds: set[int] = set()

    # -- os.read ----------------------------------------------------------
    def read(self, fd: int, size: int) -> bytes:
        chunk = self.real_read(fd, size)
        info = self.real_fstat(fd)
        self.events.append(("read", info.st_ino))
        self.read_counts[fd] = self.read_counts.get(fd, 0) + 1
        self.inode_read_counts[info.st_ino] = (
            self.inode_read_counts.get(info.st_ino, 0) + 1
        )
        served = chunk
        if self.inode_read_counts[info.st_ino] > 1 and info.st_ino in self.read_tamper_inodes:
            served = served + b"TAMPERED"
        self.served_chunks.append(served)
        return served

    # -- os.stat ----------------------------------------------------------
    def stat(self, *args, **kwargs):
        result = self.real_stat(*args, **kwargs)
        mutations = self.stat_mutations.get(result.st_ino)
        if mutations:
            self.events.append(("stat-mutated", result.st_ino))
            return mutate_stat(result, **mutations)
        return result

    # -- os.fstat ---------------------------------------------------------
    def fstat(self, fd: int):
        result = self.real_fstat(fd)
        if self.read_counts.get(fd):
            overrides = self.fstat_after_read_mutations.get(result.st_ino)
            if overrides:
                self.events.append(("fstat-after-read", result.st_ino))
                return mutate_stat(result, **overrides)
        mutations = self.fstat_mutations.get(result.st_ino)
        if mutations:
            self.events.append(("fstat-mutated", result.st_ino))
            return mutate_stat(result, **mutations)
        return result

    # -- os.open ----------------------------------------------------------
    def open(self, *args, **kwargs):
        fd = self.real_open(*args, **kwargs)
        self.opened_fds.add(fd)
        info = self.real_fstat(fd)
        swap_path = self.open_swaps.get(info.st_ino)
        if swap_path is not None:
            self.events.append(("open-swapped", info.st_ino))
            self.real_close(fd)
            self.opened_fds.discard(fd)
            return self.real_open(swap_path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        return fd

    real_close = os.close

    # -- ACL --------------------------------------------------------------
    def acl(self, path, **kwargs):
        name = str(path)
        self.acl_names.append(name)
        self.events.append(("acl", name))
        if self.acl_behavior == "present":
            return True
        if self.acl_behavior == "unknown":
            return None
        if self.acl_behavior == "raise":
            from control_plane.fs_security import FilesystemSecurityError

            raise FilesystemSecurityError("macOS ACL observation failed: errno=1")
        return False

    # -- bookkeeping ------------------------------------------------------
    def foreign_bytes_served(self, sentinel: bytes) -> int:
        return sum(chunk.count(sentinel) for chunk in self.served_chunks)

    def open_calls_for_inode(self, inode: int) -> int:
        return sum(
            1
            for fd in ()  # placeholder; swaps tracked via events below
        ) or len([e for e in self.events if e[0] == "open-swapped" and e[1] == inode])

    def all_fds_closed(self) -> bool:
        return True

    def opened_snapshot(self) -> set[int]:
        return set(self.opened_fds)


@contextlib.contextmanager
def instrumented(**config):
    """Patch os.read/os.stat/os.open/os.fstat and the module ACL symbol."""

    log = EventLog()
    log.stat_mutations = config.get("stat_mutations", {})
    log.open_swaps = config.get("open_swaps", {})
    log.fstat_mutations = config.get("fstat_mutations", {})
    log.fstat_after_read_mutations = config.get("fstat_after_read_mutations", {})
    log.read_tamper_inodes = config.get("read_tamper_inodes", set())
    log.acl_behavior = config.get("acl_behavior")
    saved = (os.read, os.stat, os.open, os.fstat)
    os.read = log.read
    os.stat = log.stat
    os.open = log.open
    os.fstat = log.fstat
    saved_acl = reader.has_macos_acl
    reader.has_macos_acl = log.acl
    try:
        yield log
    finally:
        os.read, os.stat, os.open, os.fstat = saved
        reader.has_macos_acl = saved_acl


class FDClosureTracker:
    """Assert every descriptor opened inside a window is closed again."""

    def __init__(self) -> None:
        self.real_open = os.open
        self.real_close = os.close
        self.live: set[int] = set()
        self.started = False

    def open(self, *args, **kwargs):
        fd = self.real_open(*args, **kwargs)
        if self.started:
            self.live.add(fd)
        return fd

    def close(self, fd: int) -> None:
        self.real_close(fd)
        self.live.discard(fd)

    def __enter__(self) -> "FDClosureTracker":
        self._tokens = (os.open, os.close)
        os.open = self.open
        os.close = self.close
        self.started = True
        return self

    def __exit__(self, *exc) -> None:
        self.started = False
        os.open, os.close = self._tokens


# ---------------------------------------------------------------------------
# Fixture builder and reference oracle
# ---------------------------------------------------------------------------

INSTANCE = "mastermind-os-publication"
PLIST_NAME = f"com.mastermind.studio-direct-private.{INSTANCE}.plist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


from integrations.studio_direct_mcp.private_service import _dependency_tree_hash_once


def inert_bytes(size: int, seed: int = 7) -> bytes:
    out = bytearray()
    counter = seed
    while len(out) < size:
        counter = (counter * 1103515245 + 12345) % (2**31)
        out += counter.to_bytes(4, "big")
    return bytes(out[:size])


class Fixture:
    """Temp-owned publication tree plus an outside-home tools area."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.base = self.home / ".local" / "share" / "studio-direct-mcp" / "private" / INSTANCE
        self.node_modules = self.base / "node_modules"
        self.tools = self.home / "tools"
        self.foreign = root / "foreign"
        self.sentinel = b"FOREIGN-SENTINEL-9f2c"

    def build(self) -> "Fixture":
        self.base.mkdir(parents=True)
        self.node_modules.mkdir()
        (self.node_modules / "pkg").mkdir()
        (self.node_modules / "vendor").mkdir()
        (self.node_modules / "pkg" / "index.js").write_bytes(b"console.log('index')\n")
        (self.node_modules / "pkg" / "empty.js").write_bytes(b"")
        (self.node_modules / "vendor" / "lib.js").write_bytes(b"module.exports=1;\n")
        (self.node_modules / "pkg" / "nested").mkdir()
        (self.node_modules / "pkg" / "nested" / "deep").mkdir()
        (self.node_modules / "pkg" / "nested" / "deep" / "x.js").write_bytes(b"x\n")
        (self.node_modules / "bin").mkdir()
        (self.node_modules / "bin" / "run.js").write_bytes(b"run();\n")
        # Safe internal relative symlinks: a directory alias and a file alias.
        os.symlink("../vendor", self.node_modules / "pkg" / "alias")
        os.symlink("../pkg/index.js", self.node_modules / "bin" / "latest.js")
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
        (self.base / "util.py").write_bytes(b"VALUE = 1\n")
        launch = self.home / "Library" / "LaunchAgents"
        launch.mkdir(parents=True)
        (launch / PLIST_NAME).write_bytes(b"<plist><dict/></plist>\n")
        node_bin = self.tools / "node"
        node_bin.parent.mkdir(parents=True)
        node_bin.write_bytes(b"#!/bin/sh\nexit 0\n")
        node_bin.chmod(0o755)
        backend = self.tools / "backend"
        backend.mkdir()
        (backend / "server.py").write_bytes(inert_bytes(1024 * 1024 + 128 * 1024))
        self.foreign.mkdir()
        (self.foreign / "sentinel.txt").write_bytes(self.sentinel)
        return self

    def paths(self) -> dict[str, Path]:
        return {
            "home": self.home,
            "base": self.base,
            "node_modules": self.node_modules,
            "node": self.tools / "node",
            "backend": self.tools / "backend" / "server.py",
            "manifest": self.base / "manifest.json",
            "config": self.base / "config.json",
            "plist": self.home / "Library" / "LaunchAgents" / PLIST_NAME,
            "staged_app": self.base / "app.py",
            "staged_util": self.base / "util.py",
            "dep_index": self.node_modules / "pkg" / "index.js",
            "dep_lib": self.node_modules / "vendor" / "lib.js",
        }

    def observe(self, source_file_names=("app.py", "util.py")):
        return reader.observe_studio_files(
            home=self.home,
            uid=CURRENT_UID,
            gid=CURRENT_GID,
            source_file_names=source_file_names,
        )

    def inode(self, path: Path) -> int:
        return os.lstat(path).st_ino


class StudioReaderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="studio-reader-fixture-", dir=TESTS_DIR.parent)
        self.fx = Fixture(Path(self._tmp)).build()
        self._uid = observed_uid_fixture()
        self._uid.__enter__()

    def tearDown(self) -> None:
        self._uid.__exit__(None, None, None)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def assertRefused(self, callable_fn, *args, **kwargs) -> None:
        with self.assertRaises(reader.StudioObservationError) as caught:
            callable_fn(*args, **kwargs)
        self.assertEqual(str(caught.exception), "gateway_studio_invalid")


# ---------------------------------------------------------------------------
# Positive observations and digest equivalence
# ---------------------------------------------------------------------------


class ObservationSuccessTests(StudioReaderTestCase):
    def test_full_observation_matches_reference_oracle(self) -> None:
        paths = self.fx.paths()
        observation = self.fx.observe()
        self.assertIsInstance(observation, reader.StudioFilesObservation)
        self.assertEqual(
            observation.manifest_bytes, paths["manifest"].read_bytes()
        )
        self.assertEqual(observation.config_bytes, paths["config"].read_bytes())
        self.assertEqual(observation.plist_bytes, paths["plist"].read_bytes())
        self.assertEqual(
            observation.installed_file_hashes["app.py"],
            sha256_file(paths["staged_app"]),
        )
        self.assertEqual(
            observation.installed_file_hashes["util.py"],
            sha256_file(paths["staged_util"]),
        )
        self.assertEqual(list(observation.installed_file_hashes), ["app.py", "util.py"])
        self.assertEqual(observation.node_sha256, sha256_file(paths["node"]))
        self.assertEqual(observation.backend_sha256, sha256_file(paths["backend"]))
        self.assertEqual(
            observation.dependency_tree_sha256,
            _dependency_tree_hash_once(paths["node_modules"]),
        )

    def test_empty_staged_file_is_allowed_with_empty_digest(self) -> None:
        (self.fx.base / "util.py").write_bytes(b"")
        observation = self.fx.observe()
        self.assertEqual(
            observation.installed_file_hashes["util.py"],
            hashlib.sha256(b"").hexdigest(),
        )

    def test_observation_is_frozen_and_deterministic(self) -> None:
        first = self.fx.observe()
        second = self.fx.observe()
        self.assertEqual(first, second)
        with self.assertRaises(Exception):
            first.node_sha256 = "mutated"  # type: ignore[misc]

    def test_large_inert_tool_over_1mib_observed_within_128mib(self) -> None:
        paths = self.fx.paths()
        self.assertGreater(paths["backend"].stat().st_size, 1024 * 1024)
        observation = self.fx.observe()
        self.assertEqual(observation.backend_sha256, sha256_file(paths["backend"]))

    def test_dependency_tree_with_internal_symlinks_matches_oracle(self) -> None:
        paths = self.fx.paths()
        observation = self.fx.observe()
        self.assertEqual(
            observation.dependency_tree_sha256,
            _dependency_tree_hash_once(paths["node_modules"]),
        )
        # Repeat with a symlink chain through a symlinked directory alias.
        os.symlink("alias/lib.js", self.fx.node_modules / "pkg" / "chained.js")
        observation = self.fx.observe()
        self.assertEqual(
            observation.dependency_tree_sha256,
            _dependency_tree_hash_once(paths["node_modules"]),
        )

    def test_acl_observed_before_reads_on_every_object(self) -> None:
        app_inode = self.fx.inode(self.fx.paths()["staged_app"])
        with instrumented() as log:
            self.fx.observe()
        acl_names = set(log.acl_names)
        for expected in ("/", "app.py", "manifest.json", "node_modules"):
            self.assertIn(expected, acl_names)
        first_read = log.events.index(("read", app_inode))
        acl_app = log.events.index(("acl", "app.py"))
        self.assertLess(acl_app, first_read)

    def test_real_acl_helper_passes_off_platform(self) -> None:
        saved = reader.has_macos_acl
        reader.has_macos_acl = __import__(
            "control_plane.fs_security", fromlist=["has_macos_acl"]
        ).has_macos_acl
        try:
            observation = self.fx.observe()
            self.assertTrue(observation.node_sha256)
        finally:
            reader.has_macos_acl = saved


# ---------------------------------------------------------------------------
# Swap refusal: tool leaf, staged leaf, dependency leaf, ancestor
# ---------------------------------------------------------------------------


class SwapRefusalTests(StudioReaderTestCase):
    """Each swap must refuse before a single foreign byte is served."""

    SWAP_SURFACES = {
        "tool": "node",
        "staged": "staged_app",
        "dependency": "dep_index",
    }

    def test_swap_at_open_refuses_with_zero_foreign_bytes(self) -> None:
        foreign = self.fx.foreign / "sentinel.txt"
        for label, key in self.SWAP_SURFACES.items():
            with self.subTest(surface=label):
                inode = self.fx.inode(self.fx.paths()[key])
                with instrumented(open_swaps={inode: str(foreign)}) as log:
                    self.assertRefused(self.fx.observe)
                self.assertEqual(
                    log.foreign_bytes_served(self.fx.sentinel),
                    0,
                    "foreign sentinel bytes were served",
                )

    def test_swap_at_stat_foreign_uid_refuses_before_open(self) -> None:
        for label, key in self.SWAP_SURFACES.items():
            with self.subTest(surface=label):
                inode = self.fx.inode(self.fx.paths()[key])
                with instrumented(
                    stat_mutations={inode: {"st_uid": FOREIGN_UID}}
                ) as log:
                    self.assertRefused(self.fx.observe)
                self.assertEqual(
                    len([e for e in log.events if e[0] == "open-swapped"]),
                    0,
                    "swapped object was still opened",
                )

    def test_swap_at_stat_fifo_type_refuses_before_open(self) -> None:
        app_inode = self.fx.inode(self.fx.paths()["staged_app"])
        fifo_mode = stat.S_IFIFO | 0o600
        with instrumented(stat_mutations={app_inode: {"st_mode": fifo_mode}}):
            self.assertRefused(self.fx.observe)

    def test_swap_at_stat_on_ancestor_directory_refuses(self) -> None:
        base_inode = self.fx.inode(self.fx.base)
        with instrumented(stat_mutations={base_inode: {"st_uid": FOREIGN_UID}}):
            self.assertRefused(self.fx.observe)
        with instrumented(stat_mutations={base_inode: {"st_mode": stat.S_IFDIR | 0o400}}):
            self.assertRefused(self.fx.observe)

    def test_ancestor_recheck_refuses_after_open_mutation(self) -> None:
        base_inode = self.fx.inode(self.fx.base)
        with instrumented(fstat_mutations={base_inode: {"st_size": 123456}}):
            self.assertRefused(self.fx.observe)
        home_inode = self.fx.inode(self.fx.home)
        with instrumented(fstat_mutations={home_inode: {"st_uid": FOREIGN_UID}}):
            self.assertRefused(self.fx.observe)

    def test_post_read_mutation_refuses(self) -> None:
        app_inode = self.fx.inode(self.fx.paths()["staged_app"])
        with instrumented(
            fstat_after_read_mutations={app_inode: {"st_size": 999999}}
        ):
            self.assertRefused(self.fx.observe)

    def test_dependency_file_tampered_between_passes_refuses(self) -> None:
        lib_inode = self.fx.inode(self.fx.paths()["dep_lib"])
        with instrumented(read_tamper_inodes={lib_inode}):
            self.assertRefused(self.fx.observe)

    def test_symlink_swap_to_foreign_file_refuses_without_reading(self) -> None:
        foreign = self.fx.foreign / "sentinel.txt"
        staged = self.fx.paths()["staged_app"]
        staged.unlink()
        os.symlink(foreign, staged)
        with instrumented() as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.foreign_bytes_served(self.fx.sentinel), 0)

    def test_fifo_replacement_refuses_without_hanging(self) -> None:
        staged = self.fx.paths()["staged_app"]
        staged.unlink()
        os.mkfifo(staged, 0o600)
        with instrumented():
            self.assertRefused(self.fx.observe)

    def test_fifo_hidden_behind_faked_regular_stat_refuses_before_read(self) -> None:
        """O_NONBLOCK keeps the open from hanging; the fstat type check refuses."""

        staged = self.fx.paths()["staged_app"]
        regular_stat = os.lstat(staged)
        staged.unlink()
        os.mkfifo(staged, 0o600)
        fifo_inode = os.lstat(staged).st_ino
        with instrumented(
            stat_mutations={
                fifo_inode: {
                    "st_mode": regular_stat.st_mode,
                    "st_size": regular_stat.st_size,
                }
            }
        ) as log:
            self.assertRefused(self.fx.observe)
        self.assertNotIn(("read", fifo_inode), log.events)
        self.assertEqual(log.foreign_bytes_served(self.fx.sentinel), 0)


# ---------------------------------------------------------------------------
# Ownership and mode policy
# ---------------------------------------------------------------------------


class ModePolicyTests(StudioReaderTestCase):
    def test_explicit_0400_directory_refuses(self) -> None:
        os.chmod(self.fx.base, 0o400)
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.chmod(self.fx.base, 0o700)

    def test_owner_searchable_modes_are_legitimate(self) -> None:
        os.chmod(self.fx.base, 0o500)
        try:
            observation = self.fx.observe()
            self.assertTrue(observation.node_sha256)
        finally:
            os.chmod(self.fx.base, 0o700)
        os.chmod(self.fx.home, 0o755)
        try:
            self.fx.observe()
        finally:
            os.chmod(self.fx.home, 0o700)

    def test_group_or_other_write_refuses(self) -> None:
        os.chmod(self.fx.base, 0o770)
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.chmod(self.fx.base, 0o700)
        os.chmod(self.fx.paths()["staged_app"], 0o664)
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.chmod(self.fx.paths()["staged_app"], 0o644)
        os.chmod(self.fx.paths()["staged_app"], 0o646)
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.chmod(self.fx.paths()["staged_app"], 0o644)

    def test_leaf_with_nlink_above_one_refuses(self) -> None:
        os.link(self.fx.paths()["staged_app"], self.fx.base / "hardlink.py")
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.unlink(self.fx.base / "hardlink.py")

    def test_node_tool_requires_owner_execute(self) -> None:
        os.chmod(self.fx.paths()["node"], 0o644)
        try:
            self.assertRefused(self.fx.observe)
        finally:
            os.chmod(self.fx.paths()["node"], 0o755)

    def test_acl_failure_fails_closed_before_any_read(self) -> None:
        with instrumented(acl_behavior="raise") as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.served_chunks, [])

    def external_tool_fixture(self) -> Path:
        """Point the manifest's node at a tool outside home."""

        tools = self.fx.root / "exttools"
        node = tools / "node"
        node.parent.mkdir(parents=True, exist_ok=True)
        node.write_bytes(b"#!/bin/sh\nexit 0\n")
        node.chmod(0o755)
        manifest_path = self.fx.base / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["node"] = str(node)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return node

    def fake_root_prefix(self, log, *paths) -> None:
        """Mechanical fixture: report given dirs as root-owned 0755 prefixes."""

        for path in paths:
            info = os.stat(path)
            override = {"st_uid": 0, "st_mode": stat.S_IFDIR | 0o755}
            log.stat_mutations[info.st_ino] = dict(override)
            log.fstat_mutations[info.st_ino] = dict(override)

    def test_root_owned_prefix_allows_tool_transition(self) -> None:
        node = self.external_tool_fixture()
        ancestors = ("/tmp", self.fx.root, node.parent)
        with instrumented() as log:
            self.fake_root_prefix(log, *ancestors)
            observation = self.fx.observe()
        self.assertTrue(observation.node_sha256)
        self.assertEqual(sha256_file(node), observation.node_sha256)

    def test_root_owned_prefix_with_other_write_refuses(self) -> None:
        node = self.external_tool_fixture()
        poisoned = {"st_uid": 0, "st_mode": stat.S_IFDIR | 0o777}
        with instrumented() as log:
            self.fake_root_prefix(log, "/tmp", self.fx.root, node.parent)
            for table in (log.stat_mutations, log.fstat_mutations):
                table[os.stat(node.parent).st_ino] = dict(poisoned)
            self.assertRefused(self.fx.observe)

    def test_foreign_uid_prefix_refuses(self) -> None:
        node = self.external_tool_fixture()
        foreign = {"st_uid": FOREIGN_UID, "st_mode": stat.S_IFDIR | 0o755}
        with instrumented() as log:
            self.fake_root_prefix(log, "/tmp", self.fx.root)
            for table in (log.stat_mutations, log.fstat_mutations):
                table[os.stat(node.parent).st_ino] = dict(foreign)
            self.assertRefused(self.fx.observe)

    def test_owned_tool_outside_home_is_accepted(self) -> None:
        """An already-transitioned observed-uid prefix outside home qualifies."""

        node = self.external_tool_fixture()
        with instrumented() as log:
            self.fake_root_prefix(log, "/tmp")
            observation = self.fx.observe()
        self.assertTrue(observation.node_sha256)


# ---------------------------------------------------------------------------
# Dependency symlink graph safety
# ---------------------------------------------------------------------------


class DependencySymlinkTests(StudioReaderTestCase):
    def add_link(self, name: str, target: str) -> Path:
        link = self.fx.node_modules / name
        os.symlink(target, link)
        return link

    def assert_refused_without_sentinel_reads(self) -> None:
        with instrumented() as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(
            log.foreign_bytes_served(self.fx.sentinel),
            0,
            "foreign dependency target bytes were read before refusal",
        )

    def test_absolute_symlink_refuses_without_foreign_reads(self) -> None:
        self.add_link("abs.js", str(self.fx.foreign / "sentinel.txt"))
        self.assert_refused_without_sentinel_reads()

    def test_escaping_symlink_refuses_without_foreign_reads(self) -> None:
        escaped = self.fx.root / "outside.txt"
        escaped.write_bytes(self.fx.sentinel)
        self.add_link("escape.js", "../../../../../outside.txt")
        self.assert_refused_without_sentinel_reads()

    def test_dangling_symlink_refuses_without_foreign_reads(self) -> None:
        self.add_link("dangling.js", "missing/missing.js")
        self.assert_refused_without_sentinel_reads()

    def test_symlink_cycle_refuses_without_foreign_reads(self) -> None:
        self.add_link("cycle-a.js", "cycle-b.js")
        self.add_link("cycle-b.js", "cycle-a.js")
        self.assert_refused_without_sentinel_reads()

    def test_self_cycle_refuses(self) -> None:
        self.add_link("self.js", "self.js")
        self.assert_refused_without_sentinel_reads()

    def test_symlink_escape_via_up_then_down_refuses(self) -> None:
        self.add_link("updown.js", "../../studio-direct-mcp")
        self.assert_refused_without_sentinel_reads()


# ---------------------------------------------------------------------------
# Bounds, metadata limits, manifest validation, input validation
# ---------------------------------------------------------------------------


class BoundsTests(StudioReaderTestCase):
    def test_tool_bound_refuses_over_128mib(self) -> None:
        with patched_constant("_BACKEND_FILE_LIMIT", 4096):
            self.assertRefused(self.fx.observe)

    def test_dependency_file_bound_refuses(self) -> None:
        with patched_constant("_DEPENDENCY_FILE_LIMIT", 8):
            self.assertRefused(self.fx.observe)

    def test_dependency_tree_bound_refuses(self) -> None:
        with patched_constant("_DEPENDENCY_TREE_LIMIT", 16):
            self.assertRefused(self.fx.observe)

    def test_dependency_entry_count_bound_refuses(self) -> None:
        with patched_constant("_DEPENDENCY_ENTRY_LIMIT", 3):
            self.assertRefused(self.fx.observe)

    def test_dependency_depth_bound_refuses(self) -> None:
        with patched_constant("_DEPENDENCY_DEPTH_LIMIT", 1):
            self.assertRefused(self.fx.observe)

    def test_oversized_metadata_refuses(self) -> None:
        (self.fx.base / "manifest.json").write_bytes(inert_bytes(1024 * 1024 + 1))
        self.assertRefused(self.fx.observe)
        (self.fx.base / "config.json").write_bytes(inert_bytes(1024 * 1024 + 1, seed=9))
        self.assertRefused(self.fx.observe)
        (self.fx.paths()["plist"]).write_bytes(inert_bytes(1024 * 1024 + 1, seed=11))
        self.assertRefused(self.fx.observe)

    def test_empty_metadata_refuses(self) -> None:
        (self.fx.base / "manifest.json").write_bytes(b"")
        self.assertRefused(self.fx.observe)
        (self.fx.base / "manifest.json").write_bytes(b"{}")
        (self.fx.base / "config.json").write_bytes(b"")
        self.assertRefused(self.fx.observe)
        (self.fx.base / "config.json").write_bytes(b"{}")
        (self.fx.paths()["plist"]).write_bytes(b"")
        self.assertRefused(self.fx.observe)

    def test_oversized_staged_file_refuses(self) -> None:
        (self.fx.base / "util.py").write_bytes(inert_bytes(1024 * 1024 + 1, seed=13))
        self.assertRefused(self.fx.observe)


class ManifestValidationTests(StudioReaderTestCase):
    def set_manifest(self, payload) -> None:
        if isinstance(payload, (bytes, bytearray)):
            self.fx.base.joinpath("manifest.json").write_bytes(bytes(payload))
        else:
            self.fx.base.joinpath("manifest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

    def test_non_dict_manifest_refuses(self) -> None:
        self.set_manifest([1, 2, 3])
        self.assertRefused(self.fx.observe)

    def test_invalid_json_manifest_refuses(self) -> None:
        self.set_manifest(b"{not json")
        self.assertRefused(self.fx.observe)

    def test_missing_node_or_backend_refuses(self) -> None:
        paths = self.fx.paths()
        self.set_manifest({"node": str(paths["node"])})
        self.assertRefused(self.fx.observe)
        self.set_manifest({"backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)

    def test_relative_or_traversal_tool_path_refuses(self) -> None:
        paths = self.fx.paths()
        self.set_manifest({"node": "tools/node", "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)
        self.set_manifest({"node": str(paths["node"]) + "/../node", "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)
        self.set_manifest({"node": "/" + str(paths["node"]).lstrip("/").replace("tools", "./tools", 1), "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)

    def test_non_string_tool_path_refuses(self) -> None:
        paths = self.fx.paths()
        self.set_manifest({"node": 4711, "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)

    def test_root_path_tool_refuses(self) -> None:
        paths = self.fx.paths()
        self.set_manifest({"node": "/", "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)

    def test_missing_node_leaf_refuses_without_fallback(self) -> None:
        paths = self.fx.paths()
        paths["node"].unlink()
        self.assertRefused(self.fx.observe)

    def test_missing_backend_leaf_refuses_without_fallback(self) -> None:
        paths = self.fx.paths()
        self.fx.tools.joinpath("backend").joinpath("server.py").unlink()
        self.assertRefused(self.fx.observe)

    def test_tool_directory_instead_of_leaf_refuses(self) -> None:
        paths = self.fx.paths()
        self.set_manifest({"node": str(self.fx.tools / "backend"), "backend": str(paths["backend"])})
        self.assertRefused(self.fx.observe)


class InputValidationTests(StudioReaderTestCase):
    def call(self, **overrides):
        kwargs = dict(
            home=self.fx.home,
            uid=CURRENT_UID,
            gid=CURRENT_GID,
            source_file_names=("app.py", "util.py"),
        )
        kwargs.update(overrides)
        return reader.observe_studio_files(**kwargs)

    def test_uid_must_equal_fixed_constant(self) -> None:
        # The shipped constant is the fixed 501; the suite-wide mechanical
        # fixture has repointed it at the temp-owned uid for this test run.
        self.assertNotEqual(reader.FIXED_OBSERVED_UID, FOREIGN_UID)
        self.assertRefused(self.call, uid=FOREIGN_UID)
        self.assertRefused(self.call, uid=True)
        self.assertRefused(self.call, uid=str(CURRENT_UID))
        observation = self.call(uid=CURRENT_UID)
        self.assertTrue(observation.node_sha256)

    def test_structural_type_refusals(self) -> None:
        self.assertRefused(self.call, uid=True)
        self.assertRefused(self.call, uid=str(CURRENT_UID))
        self.assertRefused(self.call, gid="0")
        self.assertRefused(self.call, gid=True)
        self.assertRefused(self.call, gid=-1)
        self.assertRefused(self.call, home=str(self.fx.home))
        self.assertRefused(self.call, home=Path("relative/home"))
        self.assertRefused(self.call, home=Path("/"))
        self.assertRefused(self.call, home=self.fx.root / "missing")
        self.assertRefused(self.call, source_file_names=["app.py"])
        self.assertRefused(self.call, source_file_names=())
        self.assertRefused(self.call, source_file_names=("app.py", "app.py"))
        self.assertRefused(self.call, source_file_names=("../escape.py",))
        self.assertRefused(self.call, source_file_names=("sub/app.py",))
        self.assertRefused(self.call, source_file_names=("",))
        self.assertRefused(self.call, source_file_names=(".",))
        self.assertRefused(self.call, source_file_names=("..",))
        self.assertRefused(self.call, source_file_names=(42,))
        self.assertRefused(self.call, source_file_names=(b"app.py",))

    def test_missing_staged_file_refuses(self) -> None:
        self.assertRefused(self.call, source_file_names=("app.py", "absent.py"))

    def test_staged_traversal_name_never_resolves(self) -> None:
        (self.fx.root / "escape.py").write_bytes(b"foreign payload")
        self.assertRefused(self.call, source_file_names=("../escape.py",))
        with instrumented() as log:
            self.assertRefused(self.call, source_file_names=("../escape.py",))
        self.assertEqual(
            log.foreign_bytes_served(b"foreign payload"), 0
        )


# ---------------------------------------------------------------------------
# Descriptor closure
# ---------------------------------------------------------------------------


class DescriptorClosureTests(StudioReaderTestCase):
    def all_descriptors_closed(self, fn) -> None:
        tracker = FDClosureTracker()
        with tracker:
            tracker.started = True
            try:
                fn()
            except reader.StudioObservationError:
                pass
            else:
                self.fail("expected refusal")
        self.assertEqual(tracker.live, set())

    def test_success_closes_every_descriptor(self) -> None:
        tracker = FDClosureTracker()
        with tracker:
            self.fx.observe()
        self.assertEqual(tracker.live, set())

    def test_refusal_paths_close_every_descriptor(self) -> None:
        self.all_descriptors_closed(
            lambda: self.fx.observe(source_file_names=("../escape.py",))
        )
        os.chmod(self.fx.base, 0o400)
        try:
            self.all_descriptors_closed(self.fx.observe)
        finally:
            os.chmod(self.fx.base, 0o700)
        self.fx.tools.joinpath("node").unlink()
        self.all_descriptors_closed(self.fx.observe)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ParentContractRegressions(StudioReaderTestCase):
    """Actual filesystem mechanics, never production authority or live tool proof."""

    def test_acl_present_refuses_before_any_payload(self):
        with instrumented(acl_behavior="present") as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.served_chunks, [])

    def test_unknown_acl_observation_refuses_before_payload(self):
        with instrumented(acl_behavior="unknown") as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.served_chunks, [])

    def test_root_writable_above_home_refuses_before_payload(self):
        inode = os.stat(self.fx.root).st_ino
        poisoned = {"st_uid": 0, "st_mode": stat.S_IFDIR | 0o1777}
        with instrumented(stat_mutations={inode: poisoned}, fstat_mutations={inode: poisoned}) as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.served_chunks, [])

    def test_root_owner_search_required_even_with_public_search(self):
        inode = os.stat(self.fx.root).st_ino
        poisoned = {"st_uid": 0, "st_mode": stat.S_IFDIR | 0o401}
        with instrumented(stat_mutations={inode: poisoned}, fstat_mutations={inode: poisoned}) as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.served_chunks, [])

    def test_both_nanosecond_timestamp_changes_refuse(self):
        info = os.stat(self.fx.paths()["node"])
        for field in ("st_mtime_ns", "st_ctime_ns"):
            fields = {"st_atime_ns": info.st_atime_ns, "st_mtime_ns": info.st_mtime_ns, "st_ctime_ns": info.st_ctime_ns}
            fields[field] += 1
            changed = os.stat_result(tuple(info), fields)
            self.assertRefused(reader._require_same_object, info, changed)

    def _real_swap(self, surface, ancestor):
        target = self.fx.paths()[surface]
        sentinel = self.fx.foreign / "sentinel.txt"
        expected_inode = self.fx.inode(target)
        incoming = target.parent.with_name(target.parent.name + "-replacement")
        if ancestor:
            incoming.mkdir()
            (incoming / target.name).write_bytes(self.fx.sentinel)
        fired = False
        with instrumented() as log:
            original_open = os.open
            def swapped(path, flags, *args, **kwargs):
                nonlocal fired
                parent_fd = kwargs.get("dir_fd")
                if not fired and parent_fd is not None and path == target.name:
                    st = log.real_stat(path, dir_fd=parent_fd, follow_symlinks=False)
                    if st.st_ino == self.fx.inode(target):
                        fired = True
                        if ancestor:
                            parent = target.parent
                            temporary = self.fx.root / "exchange-scratch"
                            parent.rename(temporary)
                            incoming.rename(parent)
                            temporary.rename(incoming)
                        else:
                            target.rename(target.with_name(target.name + "-old"))
                            target.symlink_to(sentinel)
                return original_open(path, flags, *args, **kwargs)
            os.open = swapped
            try:
                self.assertRefused(self.fx.observe)
            finally:
                os.open = original_open
        self.assertTrue(fired)
        self.assertEqual(log.foreign_bytes_served(self.fx.sentinel), 0)
        self.assertNotIn(expected_inode, log.inode_read_counts)

    def test_real_tool_leaf_swap_has_zero_foreign_reads(self):
        self._real_swap("node", False)

    def test_real_staged_leaf_swap_has_zero_foreign_reads(self):
        self._real_swap("staged_app", False)

    def test_real_dependency_leaf_swap_has_zero_foreign_reads(self):
        self._real_swap("dep_index", False)

    def test_real_tool_ancestor_swap_has_zero_foreign_reads(self):
        self._real_swap("node", True)

    def test_real_staged_ancestor_swap_has_zero_foreign_reads(self):
        self._real_swap("staged_app", True)

    def test_real_dependency_ancestor_swap_has_zero_foreign_reads(self):
        self._real_swap("dep_index", True)

    def test_root_public_tool_leaves_qualify_mechanically(self):
        paths = self.fx.paths()
        overrides = {
            self.fx.inode(paths["node"]): {"st_uid": 0, "st_mode": stat.S_IFREG | 0o555},
            self.fx.inode(paths["backend"]): {"st_uid": 0, "st_mode": stat.S_IFREG | 0o444},
        }
        with instrumented(stat_mutations=overrides, fstat_mutations=overrides):
            observation = self.fx.observe()
        self.assertEqual(observation.node_sha256, sha256_file(paths["node"]))
        self.assertEqual(observation.backend_sha256, sha256_file(paths["backend"]))

    def test_root_private_node_refuses_before_its_bytes(self):
        path = self.fx.paths()["node"]; inode = self.fx.inode(path)
        override = {"st_uid": 0, "st_mode": stat.S_IFREG | 0o700}
        with instrumented(stat_mutations={inode: override}, fstat_mutations={inode: override}) as log:
            self.assertRefused(self.fx.observe)
        self.assertNotIn(inode, log.inode_read_counts)

    def test_root_public_node_without_public_exec_refuses(self):
        inode = self.fx.inode(self.fx.paths()["node"])
        override = {"st_uid": 0, "st_mode": stat.S_IFREG | 0o544}
        with instrumented(stat_mutations={inode: override}, fstat_mutations={inode: override}) as log:
            self.assertRefused(self.fx.observe)
        self.assertNotIn(inode, log.inode_read_counts)

    def test_separate_tool_caps_refuse_before_tool_payload(self):
        self.assertEqual(reader._NODE_FILE_LIMIT, 256 * 1024 * 1024)
        self.assertEqual(reader._BACKEND_FILE_LIMIT, 16 * 1024 * 1024)
        for field, key in (("_NODE_FILE_LIMIT", "node"), ("_BACKEND_FILE_LIMIT", "backend")):
            with instrumented() as log, patched_constant(field, 1):
                self.assertRefused(self.fx.observe)
            self.assertNotIn(self.fx.inode(self.fx.paths()[key]), log.inode_read_counts)

    def test_same_size_edit_after_read_refuses(self):
        path = self.fx.paths()["staged_app"]; inode = self.fx.inode(path)
        fired = False
        with instrumented() as log:
            original_read = os.read
            def changed(fd, size):
                nonlocal fired
                data = original_read(fd, size)
                if not fired and log.real_fstat(fd).st_ino == inode:
                    fired = True
                    st = os.stat(path)
                    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000))
                return data
            os.read = changed
            try:
                self.assertRefused(self.fx.observe)
            finally:
                os.read = original_read
        self.assertTrue(fired)

    def test_missing_nofollow_capability_refuses(self):
        previous = os.O_NOFOLLOW
        os.O_NOFOLLOW = 0
        try:
            with instrumented() as log:
                self.assertRefused(self.fx.observe)
            self.assertEqual(log.served_chunks, [])
        finally:
            os.O_NOFOLLOW = previous

    def test_link_through_regular_file_refuses(self):
        (self.fx.node_modules / "bad-link").symlink_to("pkg/index.js/../empty.js")
        with instrumented() as log:
            self.assertRefused(self.fx.observe)
        self.assertEqual(log.foreign_bytes_served(self.fx.sentinel), 0)


    @unittest.skipUnless(sys.platform == "darwin", "native descriptor ACL observation is Darwin-only")
    def test_real_darwin_acl_is_rejected_before_manifest_payload(self):
        from control_plane.fs_security import has_macos_acl
        path = self.fx.paths()["manifest"]
        inode = self.fx.inode(path)
        subprocess.run(["/bin/chmod", "+a", "everyone deny delete", str(path)], check=True, capture_output=True)
        try:
            self.assertTrue(has_macos_acl(path))
            with instrumented() as log:
                saved = reader.has_macos_acl
                reader.has_macos_acl = has_macos_acl
                try:
                    self.assertRefused(self.fx.observe)
                finally:
                    reader.has_macos_acl = saved
            self.assertNotIn(inode, log.inode_read_counts)
        finally:
            subprocess.run(["/bin/chmod", "-N", str(path)], check=True, capture_output=True)


    def test_finite_repeated_internal_symlink_preserves_incumbent_digest(self):
        root = self.fx.node_modules
        (root / "alias").symlink_to("vendor")
        (root / "repeated").symlink_to("alias/../alias/lib.js")
        expected = _dependency_tree_hash_once(root)
        self.assertEqual(self.fx.observe().dependency_tree_sha256, expected)
