"""Create or verify the root-owned exact-SHA Executive release manifest."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import errno
import importlib.abc
import importlib.util
import re
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_RELEASE_ROOT = Path(__file__).parents[2]


def has_macos_acl(*args: Any, **kwargs: Any) -> bool:
    # Legacy create/verify keep their existing helper and path behavior. The
    # isolated Hermes entry must execute no repository import before custody.
    root = _RELEASE_ROOT.resolve()
    if os.fspath(root) not in sys.path:
        sys.path.insert(0, os.fspath(root))
    from control_plane.fs_security import has_macos_acl as observe
    return observe(*args, **kwargs)


SCHEMA_VERSION = "mastermind.executive_release_manifest/v1"
MANIFEST_NAME = ".executive-release-manifest.json"


class ReleaseManifestError(RuntimeError):
    pass


def _has_acl(path: Path, info: os.stat_result) -> bool:
    try:
        return has_macos_acl(
            path,
            expected_identity=info,
            allow_symlink=stat.S_ISLNK(info.st_mode),
        )
    except RuntimeError:
        raise ReleaseManifestError(f"cannot inspect release ACL: {path.name}")


def _validate_owned_info(info: os.stat_result, *, label: str) -> None:
    if info.st_uid != 0 or info.st_gid != 0:
        raise ReleaseManifestError(f"release object is not root:wheel: {label}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError(f"release object is writable by group or other: {label}")


def _release_root(path: Path) -> Path:
    lexical = Path(path)
    info = lexical.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ReleaseManifestError("release root must be a direct real directory")
    _validate_owned_info(info, label=".")
    if stat.S_IMODE(info.st_mode) & 0o055 != 0o055:
        raise ReleaseManifestError("release root must be traversable by both service UIDs")
    if _has_acl(lexical, info):
        raise ReleaseManifestError("release root has a filesystem ACL")
    return lexical.resolve(strict=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entries(root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        names.sort()
        filenames.sort()
        for name in [*names, *filenames]:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative == MANIFEST_NAME:
                continue
            info = path.lstat()
            _validate_owned_info(info, label=relative)
            if _has_acl(path, info):
                raise ReleaseManifestError(f"release object has a filesystem ACL: {relative}")
            common = {
                "path": relative,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if os.path.isabs(target):
                    raise ReleaseManifestError(f"absolute release symlink is forbidden: {relative}")
                resolved = (path.parent / target).resolve(strict=False)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ReleaseManifestError(
                        f"release symlink escapes the release root: {relative}"
                    ) from exc
                result.append({**common, "type": "symlink", "target": target})
            elif stat.S_ISDIR(info.st_mode):
                result.append({**common, "type": "directory"})
            elif stat.S_ISREG(info.st_mode):
                result.append(
                    {
                        **common,
                        "type": "file",
                        "size": info.st_size,
                        "sha256": _sha256_file(path),
                    }
                )
            else:
                raise ReleaseManifestError(f"unsupported release object: {relative}")
    return result


def _document(root: Path, commit_sha: str, tree_sha: str) -> dict[str, Any]:
    if len(commit_sha) != 40 or len(tree_sha) != 40:
        raise ReleaseManifestError("release commit and tree identities must be exact SHA-1 values")
    return {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "entries": _entries(root),
    }


def create(root: Path, commit_sha: str, tree_sha: str) -> Path:
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    if manifest.exists() or manifest.is_symlink():
        raise ReleaseManifestError("release manifest already exists")
    value = _document(root, commit_sha, tree_sha)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{MANIFEST_NAME}.", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o444)
        if os.geteuid() == 0:
            os.chown(temporary, 0, 0)
        temporary.replace(manifest)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def verify(root: Path, commit_sha: str, tree_sha: str) -> dict[str, Any]:
    root = _release_root(root)
    manifest = root / MANIFEST_NAME
    info = manifest.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseManifestError("release manifest is not a regular file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ReleaseManifestError("release manifest is writable by group or other")
    _validate_owned_info(info, label=MANIFEST_NAME)
    if _has_acl(manifest, info):
        raise ReleaseManifestError("release manifest has a filesystem ACL")
    try:
        persisted = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("release manifest is invalid") from exc
    observed = _document(root, commit_sha, tree_sha)
    if persisted != observed:
        raise ReleaseManifestError("installed release differs from its exact-SHA manifest")
    return persisted



# The Linux runtime consumer shares the existing manifest and release owner.
# This is source custody, not independent interpreter/installed-unit attestation.
_LINUX_RELEASES = Path("/opt/mastermind-executive/releases")
_FIRST_PARTY = ("common", "control_plane", "integrations", "ops", "scripts")
_YAML_ROOT = "ops/native_fabric/quota_continuity/candidate"
_MAX_SOURCE = 4 * 1024 * 1024


def _held_identity(info: os.stat_result, directory: bool) -> tuple:
    fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")
    if not directory:
        fields += ("st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    return tuple(getattr(info, key) for key in fields)


def _linux_source_acl(descriptor: int, directory: bool) -> None:
    """Any ACL attribute or any observation error except ENODATA refuses."""
    names = ("system.posix_acl_access", "system.posix_acl_default") if directory else ("system.posix_acl_access",)
    for name in names:
        try:
            os.getxattr(descriptor, name)
        except OSError as exc:
            if exc.errno == errno.ENODATA:
                continue
            raise ReleaseManifestError("release source ACL is unqualified") from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise ReleaseManifestError("descriptor ACL observation is unavailable") from exc
        raise ReleaseManifestError("release source has an ACL")


def _closed_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReleaseManifestError("release manifest has a duplicate key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ReleaseManifestError("release manifest is invalid") from exc


class _HeldReleaseSources:
    """Physical Linux descriptors and manifest-matched immutable source bytes."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.stack = ExitStack()
        self.held: dict[Path, tuple] = {}
        self.sources: dict[str, bytes] = {}
        self.total = 0
        self.closed = False
        try:
            if (not sys.platform.startswith("linux") or self.root.parent != _LINUX_RELEASES
                    or re.fullmatch(r"[0-9a-f]{40}", self.root.name) is None):
                raise ReleaseManifestError("fixed Linux release root is required")
            self.hold(self.root, directory=True)
            raw = self.read(self.root / MANIFEST_NAME, _MAX_SOURCE)
            document = _closed_json(raw)
            if (type(document) is not dict
                    or set(document) != {"schema_version", "commit_sha", "tree_sha", "entries"}
                    or document["schema_version"] != SCHEMA_VERSION
                    or document["commit_sha"] != self.root.name
                    or type(document["tree_sha"]) is not str
                    or re.fullmatch(r"[0-9a-f]{40}", document["tree_sha"]) is None
                    or type(document["entries"]) is not list
                    or not 1 <= len(document["entries"]) <= 16384):
                raise ReleaseManifestError("release manifest identity is invalid")
            self.entries: dict[str, dict] = {}
            common = {"path", "type", "mode", "uid", "gid"}
            for entry in document["entries"]:
                name = entry.get("path") if type(entry) is dict else None
                if (type(name) is not str or not name or len(name) > 4096 or "\\" in name
                        or name.startswith("/") or any(p in ("", ".", "..") for p in name.split("/"))
                        or name in self.entries):
                    raise ReleaseManifestError("release manifest path is invalid")
                kind = entry.get("type")
                extra = ({"file": {"size", "sha256"}, "directory": set(), "symlink": {"target"}}.get(kind)
                         if type(kind) is str else None)
                if (extra is None or set(entry) != common | extra
                        or type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o7777
                        or type(entry["uid"]) is not int or entry["uid"] != 0
                        or type(entry["gid"]) is not int or entry["gid"] != 0):
                    raise ReleaseManifestError("release manifest entry is invalid")
                if kind == "file" and (
                    type(entry["size"]) is not int or entry["size"] < 0
                    or type(entry["sha256"]) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
                ):
                    raise ReleaseManifestError("release manifest file is invalid")
                if kind == "symlink" and (type(entry["target"]) is not str or not entry["target"]):
                    raise ReleaseManifestError("release manifest link is invalid")
                self.entries[name] = entry
            self.check()
        except BaseException:
            self.close()
            raise

    def hold(self, path: Path, *, directory: bool = False) -> int:
        if self.closed:
            raise ReleaseManifestError("release source context is closed")
        path = Path(path)
        if not path.is_absolute() or any(p in (".", "..") for p in path.parts):
            raise ReleaseManifestError("release source path is invalid")
        if path in self.held:
            record = self.held[path]
            if record[4] != directory:
                raise ReleaseManifestError("release source type changed")
            return record[0]
        if len(self.held) >= 1024:
            raise ReleaseManifestError("release source descriptor limit exceeded")
        if path == Path("/"):
            parent, name = None, "/"
        else:
            parent, name = self.hold(path.parent, directory=True), path.name
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        try:
            fd = os.open(name, flags, dir_fd=parent)
        except OSError as exc:
            raise ReleaseManifestError("release source open refused") from exc
        self.stack.callback(os.close, fd)
        info = os.fstat(fd)
        if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
                or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
                or (not directory and info.st_nlink != 1)):
            raise ReleaseManifestError("release source ownership or mode is invalid")
        _linux_source_acl(fd, directory)
        self.held[path] = (fd, _held_identity(info, directory), parent, name, directory)
        self.check()
        return fd

    def read(self, path: Path, maximum: int) -> bytes:
        fd = self.hold(path)
        info = os.fstat(fd)
        if not 0 <= info.st_size <= maximum:
            raise ReleaseManifestError("release source size exceeds limit")
        raw = os.pread(fd, info.st_size + 1, 0)
        if len(raw) != info.st_size:
            raise ReleaseManifestError("release source read is incomplete")
        self.check()
        return raw

    def source(self, relative: str) -> bytes:
        entry = self.entries.get(relative)
        if type(entry) is not dict or entry.get("type") != "file":
            raise ReleaseManifestError("release source is not listed")
        if relative not in self.sources:
            raw = self.read(self.root / relative, _MAX_SOURCE)
            info = os.fstat(self.held[self.root / relative][0])
            if (stat.S_IMODE(info.st_mode) != entry["mode"]
                    or len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]):
                raise ReleaseManifestError("release source differs from manifest")
            self.total += len(raw)
            if self.total > 32 * 1024 * 1024:
                raise ReleaseManifestError("release source byte limit exceeded")
            self.sources[relative] = raw
        self.check()
        return self.sources[relative]

    def directory(self, relative: str) -> None:
        entry = self.entries.get(relative)
        if type(entry) is not dict or entry.get("type") != "directory":
            raise ReleaseManifestError("release package is not listed")
        fd = self.hold(self.root / relative, directory=True)
        if stat.S_IMODE(os.fstat(fd).st_mode) != entry["mode"]:
            raise ReleaseManifestError("release package differs from manifest")

    def check(self) -> None:
        if self.closed:
            raise ReleaseManifestError("release source context is closed")
        for fd, identity, parent, name, directory in self.held.values():
            try:
                if (_held_identity(os.fstat(fd), directory) != identity
                        or _held_identity(os.stat(name, dir_fd=parent, follow_symlinks=False), directory) != identity):
                    raise ReleaseManifestError("held release source changed")
                _linux_source_acl(fd, directory)
            except OSError as exc:
                raise ReleaseManifestError("held release source is unavailable") from exc

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.stack.close()


class _ReleaseSourceFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, owner: _HeldReleaseSources):
        self.owner = owner
        self.owned: dict[str, Any] = {}
        self.baseline = tuple(sys.meta_path)
        self.paths = tuple(sys.path)
        self.predecessor = None

    def check(self):
        prefix = [] if self.predecessor is None else [self.predecessor]
        if list(sys.meta_path) != prefix + [self] + list(self.baseline):
            raise ReleaseManifestError("release import finder order changed")
        if tuple(sys.path) != self.paths:
            raise ReleaseManifestError("release import path changed")
        observed = {name: module for name, module in tuple(sys.modules.items())
                    if any(name == root or name.startswith(root + ".") for root in _FIRST_PARTY)}
        if set(observed) != set(self.owned) or any(observed[name] is not module for name, module in self.owned.items()):
            raise ReleaseManifestError("release module ownership changed")
        self.owner.check()

    def find_spec(self, fullname, path=None, target=None):
        if not any(fullname == root or fullname.startswith(root + ".") for root in _FIRST_PARTY):
            return None
        self.check()
        relative = fullname.replace(".", "/")
        init, module = relative + "/__init__.py", relative + ".py"
        if init in self.owner.entries:
            origin, package = init, True
        elif module in self.owner.entries:
            origin, package = module, False
        else:
            self.owner.directory(relative)
            origin, package = relative, True
        if package:
            self.owner.directory(relative)
        spec = importlib.util.spec_from_loader(fullname, self, origin=str(self.owner.root / origin), is_package=package)
        if package:
            spec.submodule_search_locations = []
        spec.has_location = True
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        self.owned[module.__name__] = module
        self.check()
        relative = Path(module.__spec__.origin).relative_to(self.owner.root).as_posix()
        if self.owner.entries[relative]["type"] == "directory":
            self.owner.directory(relative)
            module.__file__ = None
        else:
            raw = self.owner.source(relative)
            module.__file__ = str(self.owner.root / relative)
            self.owner.check()
            exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
        self.check()


@contextmanager
def _held_release_imports(owner: _HeldReleaseSources):
    if any(name == root or name.startswith(root + ".") for name in sys.modules for root in _FIRST_PARTY):
        raise ReleaseManifestError("ambient first-party imports are refused")
    finder = _ReleaseSourceFinder(owner)
    sys.meta_path.insert(0, finder)
    try:
        yield finder
        owner.check()
    finally:
        drift = tuple(sys.path) != finder.paths or any(
            (name == root or name.startswith(root + ".")) and name not in finder.owned
            for name in sys.modules for root in _FIRST_PARTY)
        for name, module in reversed(list(finder.owned.items())):
            if sys.modules.get(name) is module:
                del sys.modules[name]
            else:
                drift = True
        indices = [i for i, item in enumerate(sys.meta_path) if item is finder]
        if list(sys.meta_path) != [finder] + list(finder.baseline):
            drift = True
        for index in reversed(indices):
            del sys.meta_path[index]
        if drift:
            raise ReleaseManifestError("held release import ownership changed")


def _hermes_runtime(argv: list[str]) -> int:
    if (not argv or argv[0] not in {"supervise", "canary", "isolation-probe"}
            or sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12)
            or not sys.platform.startswith("linux") or not sys.flags.isolated
            or not sys.flags.no_site or not sys.flags.no_user_site
            or not sys.flags.dont_write_bytecode or not sys.flags.safe_path):
        raise ReleaseManifestError("Hermes requires the fixed isolated Linux recipe")
    entry = Path(__file__)
    root = entry.parents[2]
    if (not entry.is_absolute() or root.parent != _LINUX_RELEASES
            or entry != root / "ops/executive_os/release_manifest.py"):
        raise ReleaseManifestError("Hermes entry is outside the fixed release")
    owner = _HeldReleaseSources(root)
    try:
        owner.source("ops/executive_os/release_manifest.py")
        label = os.environ.get("MM_HERMES_IMPLEMENTATION_SHA")
        if label is not None and label != root.name:
            raise ReleaseManifestError("Hermes implementation label differs from release")
        with _held_release_imports(owner) as finder:
            yaml_owner = importlib.import_module(_YAML_ROOT.replace("/", ".") + ".paid_yaml_runtime")
            with yaml_owner.held_yaml(
                owner.source(_YAML_ROOT + "/paid_pyyaml_6_0_3.zip"),
                owner.source(_YAML_ROOT + "/paid_pyyaml_provenance.json"),
                owner.check,
            ) as yaml:
                finder.predecessor = yaml.__loader__
                finder.check()
                if argv[0] == "isolation-probe":
                    from integrations.hermes_runtime.isolation_probe import main as entry_main
                    entry_args = argv[1:]
                else:
                    from integrations.hermes_runtime.cli import main as entry_main
                    entry_args = argv
                finder.check()
                result = entry_main(entry_args)
                finder.check()
                return result
    finally:
        owner.close()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "hermes-runtime":
        try:
            return _hermes_runtime(sys.argv[2:])
        except (ReleaseManifestError, OSError, ValueError, ImportError, SyntaxError):
            print("HERMES_RELEASE_SOURCE_UNQUALIFIED", file=sys.stderr)
            return 78  # Existing Hermes CONFIG_EXIT; no unqualified import to read it.
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--tree-sha", required=True)
    args = parser.parse_args()
    if args.command == "create":
        create(args.root, args.commit_sha, args.tree_sha)
    else:
        verify(args.root, args.commit_sha, args.tree_sha)
    print(json.dumps({"ok": True, "commit_sha": args.commit_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
