"""OS credential isolation for the two existing Hermes service roles.

This module never creates accounts, changes permissions, reads a credential,
installs a service, or treats an account name as numeric-identity proof.
"""
from __future__ import annotations

import grp
import os
from pathlib import Path
import pwd
import stat

from .errors import RuntimeRefusal
from .profile import RuntimeProfile

ROLE_ACCOUNTS = {"mmsecretary": "mmsecretary", "mmmeta": "mmmeta"}


def assert_service_account_names(role: str, user: str, group: str) -> None:
    """Rendering is pure; actual NSS/UID checks happen inside the service."""
    expected = ROLE_ACCOUNTS.get(role)
    if expected is None or user != expected or group != expected:
        raise RuntimeRefusal("ROOT_UNIT_ROLE_ACCOUNT_REQUIRED")


def _identity(role: str) -> tuple[int, int]:
    try:
        account = pwd.getpwnam(ROLE_ACCOUNTS[role])
        group = grp.getgrnam(ROLE_ACCOUNTS[role])
    except (KeyError, OSError):
        raise RuntimeRefusal("ROLE_OS_ACCOUNT_UNAVAILABLE") from None
    if (account.pw_name != role or group.gr_name != role
            or type(account.pw_uid) is not int or account.pw_uid <= 0
            or type(group.gr_gid) is not int or group.gr_gid <= 0
            or account.pw_gid != group.gr_gid):
        raise RuntimeRefusal("ROLE_OS_ACCOUNT_UNQUALIFIED")
    return account.pw_uid, group.gr_gid


def _private_directory(path: Path, uid: int, gid: int) -> None:
    """Require a real role-owned 0700 directory; do not repair it implicitly."""
    try:
        info = path.lstat()
        real = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RuntimeRefusal("ROLE_PRIVATE_DIRECTORY_UNAVAILABLE") from None
    if (not path.is_absolute() or path != real
            or not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != uid or info.st_gid != gid):
        raise RuntimeRefusal("ROLE_PRIVATE_DIRECTORY_UNQUALIFIED")
    # A parent writable by an unrelated user could rename/swap the private
    # directory. Root and this role alone may control the path to it.
    for parent in path.parents:
        try:
            item = parent.lstat()
        except OSError:
            raise RuntimeRefusal("ROLE_PRIVATE_ANCESTOR_UNAVAILABLE") from None
        if (not stat.S_ISDIR(item.st_mode) or item.st_uid not in (0, uid)
                or stat.S_IMODE(item.st_mode) & 0o022):
            raise RuntimeRefusal("ROLE_PRIVATE_ANCESTOR_UNQUALIFIED")


def assert_role_credential_isolation(profile: RuntimeProfile) -> None:
    """Before key access, prove distinct numeric identities and private paths.

    Two differently named accounts with the same UID/GID still fail. Real and
    effective IDs must agree, and extra supplementary groups are not accepted.
    No production secret bytes are inspected to establish these properties.
    """
    if type(profile) is not RuntimeProfile or profile.role not in ROLE_ACCOUNTS:
        raise RuntimeRefusal("ROLE_OS_ACCOUNT_UNQUALIFIED")
    peer = "mmmeta" if profile.role == "mmsecretary" else "mmsecretary"
    uid, gid = _identity(profile.role)
    other_uid, other_gid = _identity(peer)
    if uid == other_uid or gid == other_gid:
        raise RuntimeRefusal("ROLE_OS_IDENTITY_COLLISION")
    if (os.getuid() != uid or os.geteuid() != uid
            or os.getgid() != gid or os.getegid() != gid
            or not set(os.getgroups()) <= {gid}):
        raise RuntimeRefusal("ROLE_OS_PROCESS_IDENTITY_MISMATCH")
    _private_directory(profile.state_dir, uid, gid)
    _private_directory(profile.secrets_file.parent, uid, gid)
    try:
        secret = profile.secrets_file.lstat()
    except OSError:
        raise RuntimeRefusal("ROLE_PRIVATE_SECRET_UNAVAILABLE") from None
    if (not stat.S_ISREG(secret.st_mode) or secret.st_nlink != 1
            or stat.S_IMODE(secret.st_mode) != 0o600
            or secret.st_uid != uid or secret.st_gid != gid):
        raise RuntimeRefusal("ROLE_PRIVATE_SECRET_UNQUALIFIED")
