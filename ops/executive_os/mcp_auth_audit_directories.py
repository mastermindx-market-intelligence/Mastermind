"""Fixed MCP policy audit leaves, owned by the normal gateway transaction.

No sink is opened and no log is read, created, replaced or locked. The caller
retains the closed before/after observations in its existing transaction marker.
Existing directories are verified and left untouched; only positively absent
required leaves may be created. There is no CLI or independently replayable
operation here.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys

from control_plane.fs_security import has_macos_acl

ROOT = Path("/var/log/mastermind-executive/mcp-auth")
CONFIG_ROOT = "/var/log/mastermind-executive/mcp-auth"
SCHEMA = "mastermind.mcp_auth_audit_directories.v1"
UID = GID = 458
MODE = 0o700
NAMES = frozenset({"read", "submit", "workspace", "content", "steward", "coo"})


class AuditDirectoryError(ValueError):
    pass


def _require(value):
    if not value:
        raise AuditDirectoryError("MCP audit directory custody refused")


def _effective_uid():
    return os.geteuid()


def _identity(info):
    return [info.st_dev, info.st_ino]


def _custody(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def required_names(raw: bytes) -> tuple[str, ...]:
    """Reuse the installed policy readers; paths/identities are not inputs."""
    from ops.executive_os import executive_mcp_entry as entry
    from ops.executive_os.os_gateway_publication import _strict_json
    from integrations.mastermind_executive_app.gateway import load_app_policies

    document = _strict_json(raw, "MCP_AUDIT_CONFIG_MALFORMED")
    _require(document.get("audit_root") == CONFIG_ROOT
             and type(document.get("service_uid")) is int
             and document["service_uid"] == UID)
    policies = load_app_policies(document["policies"])
    optional = entry.optional_policies(document)
    entries = [("read", policies.read), ("submit", policies.submit), *sorted(optional.items())]
    names = tuple(sorted(name for name, _ in entries))
    _require(set(names) <= NAMES and len(set(names)) == len(entries)
             and len({policy.policy_id for _, policy in entries}) == len(entries))
    return names


def validate_observation(value, *, complete: bool = False):
    _require(type(value) is dict and set(value) == {"schema", "root_identity", "leaves"}
             and value["schema"] == SCHEMA)
    def identity(item):
        return (type(item) is list and len(item) == 2
                and all(type(n) is int and n >= 0 for n in item) and item[1] > 0)
    _require(identity(value["root_identity"]))
    leaves = value["leaves"]
    _require(type(leaves) is dict and {"read", "submit"} <= set(leaves) <= NAMES
             and all(identity(item) or item is None and not complete for item in leaves.values()))
    return value


def validate_transition(before, after):
    validate_observation(before)
    validate_observation(after, complete=True)
    _require(before["root_identity"] == after["root_identity"]
             and set(before["leaves"]) == set(after["leaves"])
             and all(prior is None or after["leaves"][name] == prior
                     for name, prior in before["leaves"].items()))


def _directory(fd, *, uid, gid, mode):
    info = os.fstat(fd)
    _require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid and info.st_gid == gid
             and stat.S_IMODE(info.st_mode) == mode and info.st_nlink >= 1
             and not has_macos_acl(".", expected_identity=info, descriptor=fd))
    return info


def _ancestry():
    """Only the incumbent root-owned macOS /var alias may be followed."""
    observed = []
    for path in reversed((ROOT, *ROOT.parents)):
        info = path.lstat()
        if path == Path("/var") and sys.platform == "darwin":
            _require(stat.S_ISLNK(info.st_mode) and info.st_uid == info.st_gid == 0
                     and os.readlink(path) in ("private/var", "/private/var"))
            observed.append((str(path), _custody(info), os.readlink(path)))
            # The physical alias target must have the same root custody.
            for physical in (Path("/private"), Path("/private/var")):
                current = physical.lstat()
                _require(stat.S_ISDIR(current.st_mode) and current.st_uid == current.st_gid == 0
                         and not current.st_mode & 0o022 and not has_macos_acl(physical))
                observed.append((str(physical), _custody(current), None))
            continue
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
                 and not info.st_mode & 0o022 and not has_macos_acl(path))
        observed.append((str(path), _custody(info), None))
    return tuple(observed)


@contextmanager
def _parent():
    _require(_effective_uid() == 0)
    before = _ancestry()
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        held = _directory(fd, uid=0, gid=0, mode=0o755)
        _require(_custody(held) == _custody(ROOT.lstat()) and _ancestry() == before)
        yield fd, held
        _require(_custody(_directory(fd, uid=0, gid=0, mode=0o755)) == _custody(held)
                 and _custody(ROOT.lstat()) == _custody(held) and _ancestry() == before)
    finally:
        os.close(fd)


def _leaves(fd, names):
    result = {}
    for name in sorted(names):
        try:
            named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            result[name] = None
            continue
        leaf = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = _directory(leaf, uid=UID, gid=GID, mode=MODE)
            _require(_custody(info) == _custody(named)
                     and _custody(os.stat(name, dir_fd=fd, follow_symlinks=False)) == _custody(info))
            result[name] = _identity(info)
        finally:
            os.close(leaf)
    return result


def observe(names):
    _require(type(names) is tuple and tuple(sorted(set(names))) == names
             and {"read", "submit"} <= set(names) <= NAMES)
    with _parent() as (fd, info):
        value = {"schema": SCHEMA, "root_identity": _identity(info), "leaves": _leaves(fd, names)}
    return validate_observation(value)


def establish(before):
    """Apply only the caller's retained absence, with a held root descriptor."""
    validate_observation(before)
    names = tuple(sorted(before["leaves"]))
    with _parent() as (fd, info):
        _require(_identity(info) == before["root_identity"]
                 and _leaves(fd, names) == before["leaves"])
        for name in names:
            if before["leaves"][name] is not None:
                continue
            _require(_custody(ROOT.lstat()) == _custody(info))
            os.mkdir(name, MODE, dir_fd=fd)
            created = os.stat(name, dir_fd=fd, follow_symlinks=False)
            leaf = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                held = os.fstat(leaf)
                _require(stat.S_ISDIR(held.st_mode) and _custody(held) == _custody(created))
                os.fchown(leaf, UID, GID)
                os.fchmod(leaf, MODE)
                final = _directory(leaf, uid=UID, gid=GID, mode=MODE)
                _require(_identity(final) == _identity(created)
                         and _custody(os.stat(name, dir_fd=fd, follow_symlinks=False)) == _custody(final))
                os.fsync(leaf)
            finally:
                os.close(leaf)
            os.fsync(fd)
        after = {"schema": SCHEMA, "root_identity": _identity(info), "leaves": _leaves(fd, names)}
        validate_transition(before, after)
    return after


def verify(after):
    validate_observation(after, complete=True)
    _require(observe(tuple(sorted(after["leaves"]))) == after)
