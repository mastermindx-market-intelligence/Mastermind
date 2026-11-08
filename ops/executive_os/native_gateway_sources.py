"""Native dependency qualification subordinate to the Executive release owner.

The release manifest selects the frozen inventory and optional named source
derivation. The existing root recipe materializes those artifacts. This module
admits no work, loads no native package, and never adopts live candidate hashes
as its expected identities. Bounded descriptors verify the complete trees.
"""
from __future__ import annotations

import hashlib
import json
import os
import ctypes
import errno
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile

SCHEMA = "mastermind.hermes_native_dependencies/v1"
MAX_INVENTORY_BYTES = 8 * 1024 * 1024
MAX_MEMBERS = 32768
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")


class NativeSourceRefusal(ValueError):
    pass


def _refuse():
    raise NativeSourceRefusal("native dependency custody refused")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _refuse()
        result[key] = value
    return result


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _relative(value):
    if (type(value) is not str or not 1 <= len(value) <= 4096
            or value.startswith("/") or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in {"", ".", ".."} for p in value.split("/"))
            or PurePosixPath(value).as_posix() != value):
        _refuse()
    return value


def _qualified(fd, acl_check, *, directory, expected=None):
    info = os.fstat(fd)
    if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022
            or info.st_mode & 0o7000 or (not directory and info.st_nlink != 1)
            or (stat.S_IMODE(info.st_mode) & (0o005 if directory else 0o004))
               != (0o005 if directory else 0o004)):
        _refuse()
    acl_check(fd, directory)
    if expected is not None and stat.S_IMODE(info.st_mode) != expected["mode"]:
        _refuse()
    return info


class NativeSourceClosure:
    """One verified closure inside one existing held release context.

    Only root-owned, single-link regular files and root-owned directories
    are accepted. The role cannot change them. Checks compare every saved
    inode/ctime and complete directory membership; hashing streams once,
    without using the first-party source cache or retaining one fd per file.
    """

    def __init__(self, owner, recipe, acl_check):
        self.owner = owner
        self.recipe = recipe
        self.acl_check = acl_check
        self.roots = tuple(Path(p) for p in recipe["import_roots"])
        self.closed = False
        self.snapshots = {}
        self.directories = {}
        self.expected = {}
        self.root_fds = {}
        self.total = 0
        inventory = recipe["dependency_inventory"]
        raw = owner.read(Path(inventory["path"]), MAX_INVENTORY_BYTES)
        if (len(raw) != inventory["size"]
                or hashlib.sha256(raw).hexdigest() != inventory["sha256"]):
            _refuse()
        try:
            document = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError, RecursionError):
            _refuse()
        if (type(document) is not dict or set(document) != {"schema", "roots"}
                or document["schema"] != SCHEMA or type(document["roots"]) is not list
                or len(document["roots"]) != len(self.roots)):
            _refuse()
        count = 0
        for root, row in zip(self.roots, document["roots"]):
            if (type(row) is not dict or set(row) != {"path", "entries"}
                    or row["path"] != str(root) or type(row["entries"]) is not list):
                _refuse()
            entries = {}
            for entry in row["entries"]:
                if type(entry) is not dict:
                    _refuse()
                relative = _relative(entry.get("path"))
                kind = entry.get("type")
                extra = {"size", "sha256"} if kind == "file" else set()
                if (kind not in {"file", "directory"}
                        or set(entry) != {"path", "type", "mode"} | extra
                        or relative in entries or type(entry["mode"]) is not int
                        or not 0 <= entry["mode"] <= 0o777 or entry["mode"] & 0o022):
                    _refuse()
                if kind == "file" and (
                    type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_FILE_BYTES
                    or type(entry["sha256"]) is not str or not _SHA.fullmatch(entry["sha256"])
                ):
                    _refuse()
                entries[relative] = entry
                count += 1
                if count > MAX_MEMBERS:
                    _refuse()
            if not entries:
                _refuse()
            for relative in entries:
                parent = PurePosixPath(relative).parent.as_posix()
                if parent != "." and (parent not in entries or entries[parent]["type"] != "directory"):
                    _refuse()
            self.expected[root] = entries
            self.root_fds[root] = owner.hold(root, directory=True)
            found = set()
            self._walk(root, self.root_fds[root], "", first=True, found=found)
            if found != set(entries):
                _refuse()
        owner.check()

    def _qualified(self, fd, *, directory, expected=None):
        return _qualified(fd, self.acl_check, directory=directory, expected=expected)

    def _walk(self, root, fd, relative, *, first, found):
        before = self._qualified(fd, directory=True,
                                 expected=self.expected[root].get(relative))
        key = (root, relative)
        names = tuple(sorted(os.listdir(fd)))
        if first:
            self.directories[key] = (names, _identity(before))
        elif self.directories.get(key) != (names, _identity(before)):
            _refuse()
        for name in names:
            child = f"{relative}/{name}" if relative else name
            entry = self.expected[root].get(child)
            if entry is None:
                _refuse()
            found.add(child)
            directory = entry["type"] == "directory"
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child_fd = os.open(name, flags, dir_fd=fd)
            try:
                info = self._qualified(child_fd, directory=directory, expected=entry)
                if directory:
                    self._walk(root, child_fd, child, first=first, found=found)
                else:
                    child_key = (root, child)
                    if info.st_size != entry["size"]:
                        _refuse()
                    if first:
                        self.total += info.st_size
                        if self.total > MAX_TOTAL_BYTES:
                            _refuse()
                        digest = hashlib.sha256()
                        size = 0
                        while True:
                            data = os.read(child_fd, 65536)
                            if not data:
                                break
                            size += len(data)
                            if size > entry["size"]:
                                _refuse()
                            digest.update(data)
                        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                            _refuse()
                        self.snapshots[child_key] = _identity(info)
                    elif self.snapshots.get(child_key) != _identity(info):
                        _refuse()
                if (_identity(os.fstat(child_fd)) != _identity(info)
                        or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info)):
                    _refuse()
            finally:
                os.close(child_fd)
        if _identity(os.fstat(fd)) != _identity(before):
            _refuse()

    def check(self):
        if self.closed:
            _refuse()
        for root, fd in self.root_fds.items():
            found = set()
            self._walk(root, fd, "", first=False, found=found)
            if found != set(self.expected[root]):
                _refuse()

    def close(self):
        self.closed = True


def _readable_path(owner, path, acl_check, *, directory):
    fd = owner.hold(path, directory=directory)
    _qualified(fd, acl_check, directory=directory)
    for parent in path.parents:
        info = os.fstat(owner.hold(parent, directory=True))
        # Native roles are neither root nor members of root's group.
        if not stat.S_IMODE(info.st_mode) & 0o001:
            _refuse()
    return fd


def candidate_inventory(owner, roots, acl_check):
    """Deterministic candidate DATA; never supplies its own expected digest."""
    rows, count, total = [], 0, 0

    def walk(fd, prefix, entries):
        nonlocal count, total
        before = _qualified(fd, acl_check, directory=True)
        names = tuple(sorted(os.listdir(fd)))
        for name in names:
            relative = _relative(f"{prefix}/{name}" if prefix else name)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(info.st_mode)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            member = os.open(name, flags, dir_fd=fd)
            try:
                opened = _qualified(member, acl_check, directory=directory)
                if _identity(opened) != _identity(info):
                    _refuse()
                count += 1
                if count > MAX_MEMBERS:
                    _refuse()
                entry = {"path": relative, "type": "directory" if directory else "file",
                         "mode": stat.S_IMODE(info.st_mode)}
                if directory:
                    walk(member, relative, entries)
                else:
                    if not 0 <= info.st_size <= MAX_FILE_BYTES:
                        _refuse()
                    total += info.st_size
                    if total > MAX_TOTAL_BYTES:
                        _refuse()
                    digest, size = hashlib.sha256(), 0
                    while True:
                        block = os.read(member, 65536)
                        if not block:
                            break
                        size += len(block)
                        if size > info.st_size:
                            _refuse()
                        digest.update(block)
                    if size != info.st_size:
                        _refuse()
                    entry.update(size=size, sha256=digest.hexdigest())
                entries.append(entry)
                if (_identity(os.fstat(member)) != _identity(info)
                        or _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info)):
                    _refuse()
            finally:
                os.close(member)
        if _identity(os.fstat(fd)) != _identity(before) or tuple(sorted(os.listdir(fd))) != names:
            _refuse()

    for value in roots:
        root = Path(value)
        entries = []
        walk(_readable_path(owner, root, acl_check, directory=True), "", entries)
        if not entries:
            _refuse()
        rows.append({"path": str(root), "entries": sorted(entries, key=lambda row: row["path"])})
    raw = (json.dumps({"schema": SCHEMA, "roots": rows}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    if len(raw) > MAX_INVENTORY_BYTES:
        _refuse()
    owner.check()
    return raw


def prepare_inventory(owner, recipe, acl_check):
    """Publish/adopt exact frozen bytes, then qualify them through the owner.

    Invoked by the existing root enrollment transaction after immutable source
    publication and before any unit/config selection. No live tree is repaired;
    no expected digest is inferred. A missing artifact is materialized only
    if its complete candidate bytes match the independently frozen commitment.
    """
    if os.getuid() != 0 or os.geteuid() != 0:
        _refuse()
    inventory = recipe["dependency_inventory"]
    path = Path(inventory["path"])
    if path == owner.root or owner.root in path.parents:
        _refuse()
    parent = _readable_path(owner, path.parent, acl_check, directory=True)
    try:
        os.stat(path.name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        raw = candidate_inventory(owner, recipe["import_roots"], acl_check)
        if len(raw) != inventory["size"] or hashlib.sha256(raw).hexdigest() != inventory["sha256"]:
            _refuse()
        fd, name = tempfile.mkstemp(prefix=".hermes-native-inventory-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                os.fchmod(stream.fileno(), 0o444)
                os.fchown(stream.fileno(), 0, 0)
                stream.flush()
                os.fsync(stream.fileno())
            owner.check()
            try:
                # Atomic no-replace publication. An existing name is adopted
                # only by the exact-byte/identity verifier below.
                os.link(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
            except FileExistsError:
                pass
            temporary.unlink()
            os.fsync(parent)
        finally:
            temporary.unlink(missing_ok=True)
    _readable_path(owner, path, acl_check, directory=False)
    closure = NativeSourceClosure(owner, recipe, acl_check)
    try:
        closure.check()
        owner.check()
    finally:
        closure.close()


# Closed source transformations, subordinate to the existing frozen recipe
# and inventory. They cannot be combined or supplied as arbitrary patch lists.
# These are source identities, never runtime access grants.
DERIVATION_KIND = "computer_env_guard"
DERIVATION_BASE = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
DERIVATION_PATCH = "d17af87e60a1f92a52ef446ad393ce2841c876a28e2ae0580bc7e6db09d6721f"
DERIVATION_POSTIMAGES = {
    "tools/computer_use/permissions.py": "c1b1f7b1de10fc14ff2892ec8b0dd7ca2c1976ef76a0d6884e93577caeea8d0d",
    "tools/computer_use/cua_backend.py": "b106ce6b1086a932648c141a517821fd503a54b75d52e7cf5b127c94df1de78f",
}
_GUARD_PACKAGE = "integrations/hermes_qualification/computer_env_guard"
PRIVACY_DERIVATION_KIND = "diagnostic_privacy"
PRIVACY_DERIVATION_PATCH = "ded504ad2d660f14c89527ec74593fcc459485666fbb0994bb92f7b02c878bce"
PRIVACY_DERIVATION_POSTIMAGES = {
    "agent/agent_init.py": "eea2233a2b6cd536fca891dc3436a8dd55c1e69f0ad54a5aa6cf8fa58a3c7e08",
    "agent/memory_caller_scope.py": "e8924a95d756f0235071a0276763bffdaa7fdf5cef68eda589f7f46939a872a6",
}
PRIVACY_LICENSE_SHA256 = "821556e6336796450ab852d375117b48a4887e71d255794fd6318d99982a5ab6"
_PRIVACY_PACKAGE = "integrations/hermes_qualification/diagnostic_privacy"
WORKSPACE_OAUTH_DERIVATION_KIND = "workspace_oauth_privacy"
WORKSPACE_OAUTH_DERIVATION_PATCH = "1d1df9a1fde6654d1690715e52ed10524c6b1b4d9af24b406243324d212146ce"
WORKSPACE_OAUTH_DERIVATION_POSTIMAGES = {
    "agent/agent_init.py": "eea2233a2b6cd536fca891dc3436a8dd55c1e69f0ad54a5aa6cf8fa58a3c7e08",
    "agent/memory_caller_scope.py": "e8924a95d756f0235071a0276763bffdaa7fdf5cef68eda589f7f46939a872a6",
    "agent/redact.py": "d52ac54e1107b404c0882432a2e06b114d298f4ccd33ec16deffc0544074d935",
    "hermes_cli/mcp_config.py": "0970c0cd3ed94a3a3986a5364c697b6b64006844b383707ea12998bd0084e70c",
    "tools/mcp_oauth_manager.py": "b1b611725cb1f873c2b9c715eab8591ea56d8ca0c61cd832224f5ed0a21624ae",
    "tools/mcp_oauth_provider.py": "f79aa231c90de8e483a4cb02c4c51d1cc9ba4a8838872e718b92784fcb3181b8",
    "tools/mcp_tool_errors.py": "e71abeb9e97b0d1e97c976c709dd2fa2ccb71822626184e976dad0838d9c3c28",
    "tools/mcp_tool_server_run.py": "89a93742b9344fa351f6b3a931a3daf5787f2d7abba6ec52695a6c52c2e37b5e",
    "tools/mcp_tool_transport.py": "51443ff396278a8c1088b5141146f3ba53cec340b90ac04a1263c18e3ecbb8ec",
}
_WORKSPACE_OAUTH_PACKAGE = "integrations/hermes_qualification/workspace_oauth_privacy"

# Explicit cumulative source selection. Historical derivation meanings and
# postimages remain unchanged; no arbitrary patch stack is admitted.
EVAL_INPUTS_DERIVATION_KIND = "native_eval_inputs"
EVAL_INPUTS_DERIVATION_PATCH = "123bd25188aa844afceeb0a97f1e023797740116e89bf886b2b8686efd04012d"
EVAL_INPUTS_DERIVATION_POSTIMAGES = {**WORKSPACE_OAUTH_DERIVATION_POSTIMAGES,
    "hermes_state_common.py": "bc77e0f3b74596030016ff72bc6c8eff959507e9cc414dfc102c8e8140a972e8",
    "hermes_state_runtime.py": "5b30be6913da982c7cb50dd3ad8c37700229288eab0eb101dce1843b27777340",
    "hermes_state_schema.py": "08abad090492db461eca6205f2791e47fa0b6238065c1c4f284420420ca45b37",
    "gateway/session_authority.py": "2cf93a511edd77943440eb63c23d45e8e11adb12e31a7d979a38d4cb56ff4bf1",
    "gateway/session_managed_worker.py": "3d61709dc368addcb21b871fb4b34aac1994b9f52ee85b17b692ad4bf6ffb30a",
    "gateway/session_runtime_workers.py": "dc5924b1180b9660342eef0f74a317cb32a8e0327531f706f794d3bfd2a74d0e",
    "hermes_state_mutation_retirement.py": "12c890e1a2ae4a3b89b01de58c3f5330b87431f48f7672c04cd3b68c7e8e677c"}
_EVAL_INPUTS_PACKAGE = "integrations/hermes_qualification/native_eval_inputs"


def _derivation_policy(kind):
    if kind == DERIVATION_KIND:
        return DERIVATION_PATCH, DERIVATION_POSTIMAGES, _GUARD_PACKAGE
    if kind == PRIVACY_DERIVATION_KIND:
        return PRIVACY_DERIVATION_PATCH, PRIVACY_DERIVATION_POSTIMAGES, _PRIVACY_PACKAGE
    if kind == WORKSPACE_OAUTH_DERIVATION_KIND:
        return WORKSPACE_OAUTH_DERIVATION_PATCH, WORKSPACE_OAUTH_DERIVATION_POSTIMAGES, _WORKSPACE_OAUTH_PACKAGE
    if kind == EVAL_INPUTS_DERIVATION_KIND:
        return EVAL_INPUTS_DERIVATION_PATCH, EVAL_INPUTS_DERIVATION_POSTIMAGES, _EVAL_INPUTS_PACKAGE
    _refuse()


def _derivation(recipe):
    value = recipe.get("vendor_derivation")
    if (type(value) is not dict
            or set(value) != {"kind", "base_sha", "patch_sha256", "source_root"}
            or type(value["kind"]) is not str or value["base_sha"] != DERIVATION_BASE):
        _refuse()
    patch, _, _ = _derivation_policy(value["kind"])
    if value["patch_sha256"] != patch:
        _refuse()
    source, destination = Path(value["source_root"]), Path(recipe["vendor_root"])
    if (not source.is_absolute() or not destination.is_absolute()
            or source == destination or source in destination.parents
            or destination in source.parents):
        _refuse()
    return source, destination


def _git(root, *arguments):
    # No global changes, replacement objects, lazy network fetch, index refresh,
    # or caller-supplied Git environment. No shell or content filters are used.
    environment = {"PATH": os.defpath, "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0",
                   "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
                   "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                   "GIT_CONFIG_VALUE_0": str(root)}
    try:
        result = subprocess.run(["git", "-C", str(root), *arguments], env=environment,
                                capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        _refuse()
    if result.returncode:
        _refuse()
    return result.stdout


def _base_members(root, postimages):
    if (_git(root, "rev-parse", "--verify", "HEAD").strip() != DERIVATION_BASE.encode()
            or _git(root, "rev-parse", "--show-object-format").strip() != b"sha1"):
        _refuse()
    result = {}
    listing = _git(root, "ls-tree", "-r", "-z", "--full-tree", DERIVATION_BASE)
    for record in listing.split(b"\0"):
        if not record:
            continue
        try:
            header, name = record.split(b"\t", 1)
            mode, kind, digest = header.decode("ascii").split()
            relative = _relative(name.decode("utf-8", "strict"))
        except (ValueError, UnicodeError):
            _refuse()
        if (kind != "blob" or mode not in {"100644", "100755"}
                or re.fullmatch(r"[0-9a-f]{40}", digest) is None
                or relative == ".git" or relative.startswith(".git/")
                or relative in result or len(result) >= MAX_MEMBERS):
            _refuse()
        result[relative] = (mode == "100755", digest)
    if not result or not set(postimages) <= result.keys():
        _refuse()
    return result


def _member_fd(root_fd, relative, acl_check):
    """Open through no-follow directory descriptors, retaining no file cache."""
    parent = os.dup(root_fd)
    try:
        pieces = _relative(relative).split("/")
        for name in pieces[:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=parent)
            try:
                _qualified(child, acl_check, directory=True)
            except BaseException:
                os.close(child)
                raise
            os.close(parent)
            parent = child
        fd = os.open(pieces[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent)
        try:
            _qualified(fd, acl_check, directory=False)
        except BaseException:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(parent)


def _member_hash(root_fd, entry, acl_check, *, git_blob=False):
    fd = _member_fd(root_fd, entry["path"], acl_check)
    try:
        before = _qualified(fd, acl_check, directory=False, expected=entry)
        if before.st_size != entry["size"]:
            _refuse()
        digest = hashlib.sha1() if git_blob else hashlib.sha256()
        if git_blob:
            digest.update(b"blob %d\0" % before.st_size)
        total = 0
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            total += len(block)
            if total > before.st_size:
                _refuse()
            digest.update(block)
        if total != before.st_size or _identity(os.fstat(fd)) != _identity(before):
            _refuse()
        return digest.hexdigest()
    finally:
        os.close(fd)


def _checkout_snapshot(owner, root, acl_check, *, patched, postimages):
    # Complete actual membership is examined, including ignored/untracked files
    # and Git metadata; index flags cannot conceal changes in tracked bytes.
    snapshot = json.loads(candidate_inventory(owner, [str(root)], acl_check))["roots"][0]
    entries = {row["path"]: row for row in snapshot["entries"]}
    if (entries.get(".git", {}).get("type") != "directory"
            or entries.get(".git/HEAD", {}).get("type") != "file"
            or any(name in entries for name in (".git/commondir", ".git/gitdir",
                       ".git/objects/info/alternates", ".git/objects/info/http-alternates"))):
        _refuse()
    members = _base_members(root, postimages)
    files = {name for name, row in entries.items()
             if row["type"] == "file" and not name.startswith(".git/")}
    directories = set()
    for name in members:
        directories.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    if (files != set(members)
            or {name for name, row in entries.items() if row["type"] == "directory"
                and name != ".git" and not name.startswith(".git/")} != directories):
        _refuse()
    root_fd = _readable_path(owner, root, acl_check, directory=True)
    for name, (executable, blob) in members.items():
        row = entries[name]
        if bool(row["mode"] & 0o111) != executable:
            _refuse()
        if patched and name in postimages:
            if row["sha256"] != postimages[name]:
                _refuse()
        elif _member_hash(root_fd, row, acl_check, git_blob=True) != blob:
            _refuse()
    owner.check()
    return snapshot


def _guard(owner, kind):
    patch, postimages, relative = _derivation_policy(kind)
    if kind == DERIVATION_KIND:
        from integrations.hermes_qualification.computer_env_guard import qualify
    elif kind == PRIVACY_DERIVATION_KIND:
        from integrations.hermes_qualification.diagnostic_privacy import qualify
    elif kind == WORKSPACE_OAUTH_DERIVATION_KIND:
        from integrations.hermes_qualification.workspace_oauth_privacy import qualify
    elif kind == EVAL_INPUTS_DERIVATION_KIND:
        from integrations.hermes_qualification.native_eval_inputs import qualify
    else:
        _refuse()
    package = owner.root / relative
    if Path(qualify.ROOT) != package:
        _refuse()
    # The existing held first-party importer owns executable source; its fixed
    # data files are held too. No path, patch, or postimage is discovered online.
    for name in ("manifest.json", "guard.patch", "UPSTREAM_LICENSE"):
        if owner.source(f"{relative}/{name}") != (package / name).read_bytes():
            _refuse()
    policy = qualify.manifest()
    if (policy["patch_sha256"] != patch
            or {name: row["after_sha256"] for name, row in policy["files"].items()}
               != postimages):
        _refuse()
    if (kind in {PRIVACY_DERIVATION_KIND, WORKSPACE_OAUTH_DERIVATION_KIND, EVAL_INPUTS_DERIVATION_KIND} and hashlib.sha256(
            owner.source(f"{relative}/UPSTREAM_LICENSE")).hexdigest() != PRIVACY_LICENSE_SHA256):
        _refuse()
    owner.check()
    return qualify


def verify_vendor_derivation(owner, recipe, acl_check):
    """Verify the named repair, separate from the base HEAD and frozen closure."""
    _, destination = _derivation(recipe)
    kind = recipe["vendor_derivation"]["kind"]
    patch, postimages, package = _derivation_policy(kind)
    _guard(owner, kind)
    snapshot = _checkout_snapshot(owner, destination, acl_check, patched=True, postimages=postimages)
    _expected_derived_inventory(owner, recipe, snapshot, {}, acl_check)
    return {"kind": kind, "base_sha": DERIVATION_BASE,
            "patch_sha256": patch, "postimages": dict(postimages),
            "license_sha256": hashlib.sha256(
                owner.source(f"{package}/UPSTREAM_LICENSE")).hexdigest(),
            "vendor_root": str(destination)}


def _expected_derived_inventory(owner, recipe, snapshot, patched, acl_check):
    row = json.loads(json.dumps(snapshot))
    row["path"] = recipe["vendor_root"]
    for entry in row["entries"]:
        if entry["path"] in patched:
            raw = patched[entry["path"]]
            entry.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    others = recipe["import_roots"][1:]
    rows = [row] + (json.loads(candidate_inventory(owner, others, acl_check))["roots"] if others else [])
    raw = (json.dumps({"schema": SCHEMA, "roots": rows}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    expected = recipe["dependency_inventory"]
    if len(raw) != expected["size"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
        _refuse()


def _copy_derivation(root_fd, staging, snapshot, patched, acl_check, *, postimages):
    # Copy Git metadata too: native version_info must still identify the base
    # commit. The inventory binds those bytes; no clone, hooks or Git writes run.
    for entry in sorted(snapshot["entries"], key=lambda row: (row["path"].count("/"), row["path"])):
        target = staging / entry["path"]
        if entry["type"] == "directory":
            target.mkdir(mode=0o700)
            target.chmod(entry["mode"])
            os.chown(target, 0, 0)
            continue
        output = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        source = None
        try:
            digest, count = hashlib.sha256(), 0
            replacement = patched.get(entry["path"])
            if replacement is None:
                source = _member_fd(root_fd, entry["path"], acl_check)
                before = _qualified(source, acl_check, directory=False, expected=entry)
                if before.st_size != entry["size"]:
                    _refuse()
            while True:
                block = replacement if replacement is not None else os.read(source, 65536)
                if not block:
                    break
                count += len(block)
                if count > MAX_FILE_BYTES:
                    _refuse()
                digest.update(block)
                view = memoryview(block)
                while view:
                    size = os.write(output, view)
                    if size <= 0:
                        _refuse()
                    view = view[size:]
                if replacement is not None:
                    break
            expected_size = len(replacement) if replacement is not None else entry["size"]
            expected_hash = postimages.get(entry["path"], entry["sha256"])
            if count != expected_size or digest.hexdigest() != expected_hash:
                _refuse()
            if source is not None and _identity(os.fstat(source)) != _identity(before):
                _refuse()
            os.fchmod(output, entry["mode"])
            os.fchown(output, 0, 0)
            os.fsync(output)
        finally:
            if source is not None:
                os.close(source)
            os.close(output)


def _publish_derivation(parent_fd, temporary, destination):
    """OS no-replace rename, as used by existing Executive artifact owners."""
    try:
        library = ctypes.CDLL(None, use_errno=True)
        name, flags = ("renameatx_np", 4) if sys.platform == "darwin" else ("renameat2", 1)
        rename = getattr(library, name)
    except (AttributeError, OSError):
        _refuse()
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    ctypes.set_errno(0)
    if rename(parent_fd, os.fsencode(temporary), parent_fd, os.fsencode(destination), flags):
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            return False
        raise OSError(code, "native derivation publication refused")
    os.fsync(parent_fd)
    return True


def _sync_derivation(staging, snapshot):
    directories = [staging / row["path"] for row in snapshot["entries"]
                   if row["type"] == "directory"]
    for path in sorted(directories, key=lambda p: len(p.parts), reverse=True) + [staging]:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def prepare_vendor_derivation(owner, recipe, acl_check):
    """Materialize/adopt only the named unselected repair in the root recipe.

    No live artifact is edited. A failure after publication retains the original
    destination for reconciliation. Frozen inventory expectations are input.
    """
    if os.getuid() != 0 or os.geteuid() != 0:
        _refuse()
    source, destination = _derivation(recipe)
    kind = recipe["vendor_derivation"]["kind"]
    _, postimages, _ = _derivation_policy(kind)
    if any(root == owner.root or root in owner.root.parents or owner.root in root.parents
           for root in (source, destination)):
        _refuse()
    parent = _readable_path(owner, destination.parent, acl_check, directory=True)
    if os.path.lexists(destination):
        return verify_vendor_derivation(owner, recipe, acl_check)
    guard = _guard(owner, kind)
    snapshot = _checkout_snapshot(owner, source, acl_check, patched=False, postimages=postimages)
    source_fd = _readable_path(owner, source, acl_check, directory=True)
    sources = {}
    for name in postimages:
        fd = _member_fd(source_fd, name, acl_check)
        try:
            sources[name] = os.read(fd, guard.MAX_SOURCE_BYTES + 1)
        finally:
            os.close(fd)
    patched = guard.prepare_sources(sources)
    _expected_derived_inventory(owner, recipe, snapshot, patched, acl_check)
    staging = Path(tempfile.mkdtemp(prefix=".hermes-derivation-", dir=destination.parent))
    try:
        _copy_derivation(source_fd, staging, snapshot, patched, acl_check, postimages=postimages)
        os.chmod(staging, 0o755)
        os.chown(staging, 0, 0)
        _sync_derivation(staging, snapshot)
        # Owner snapshots must exclude this private staging path: its name will
        # move. The final published namespace is verified through the owner.
        owner.check()
        _publish_derivation(parent, staging.name, destination.name)
        return verify_vendor_derivation(owner, recipe, acl_check)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
