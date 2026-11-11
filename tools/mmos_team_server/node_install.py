#!/usr/bin/env python3
"""Install the pinned official Node.js archive and inspect the packed runtime.

Downloaded executables are never run during verification or extraction. The
archive is first copied into a private staging directory; that one private
copy is hashed, member-checked and extracted from a single open file, so the
bytes that reach the destination are exactly the bytes that were verified.
The install receipt travels inside the staged tree, and one atomic rename
publishes tree and receipt together. The caller must create the private
server root; this tool never chmods a pre-existing root into private.

Failure-path contract (lane TSHc): every refusal prints one line —
`team_runtime: …` for install/resolve, `doctor_error=…` for doctor — never a
traceback; a refusal publishes nothing (every outside receipt that could
conflict is checked before the publishing rename); a killed install leaves
only staging debris and a stale temp, both of which the next run removes
under an exclusive install lock before doing any work.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

VERSION = "24.22.2"
ARCHIVE = f"node-v{VERSION}-darwin-arm64.tar.gz"
OFFICIAL_SHA256 = "aa9549349e47dffaa42dcf95d6e06ade8c4bdafc980979883b88767670df385a"
NODE_REQUIREMENT = "^22.16 || ^23.11 || >=24.10"
BUILD_REQUIREMENT = "^22.18.0 || ^24.11.0 || >=26.0.0"
MEMBER_BUDGET = 30000
BYTE_BUDGET = 2 * 1024 ** 3
HEX64 = re.compile(r"[0-9a-f]{64}")
# Receipt schema 2: the tree digest now covers every entry (type, mode bits,
# link targets, empty and symlinked directories) instead of regular files
# only. Receipts written by schema-1 code must be reinstalled, never blessed.
SCHEMA_VERSION = 2
# The official archive ships exactly these relative links in bin/.
ALLOWED_LINKS = {
    "npm": "../lib/node_modules/npm/bin/npm-cli.js",
    "npx": "../lib/node_modules/npm/bin/npx-cli.js",
    "corepack": "../lib/node_modules/corepack/dist/corepack.js",
}
REQUIRED_DIST_FILES = (
    "bin.mjs",
    "claude-history-worker.mjs",
    "client/index.html",
    "node_modules/playwright-core/package.json",
    "node_modules/node-pty/package.json",
)
INSTALL_DIR_NAME = f"node-v{VERSION}-darwin-arm64"
# Panel R3: the server release folder is a single safe-named component under
# <root>/runtime/ (pack_server.mjs enforces the same shape on --release-ID).
RELEASE_ID_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,60}")
DIGESTS_NAME = "file-digests.json"
# Written into dist AFTER hashing (pack_server.mjs:265), so it is the one file
# the digest list deliberately does not record.
PACK_EXCLUDED = {"BUILD_RECEIPT.json"}
# Resolve (the runner's pre-execve gate) verifies BOTH trees by default; so
# does doctor. The pinned Node tree's full schema-2 digest measured 1.22 s
# cold on an idle M2 Studio — but ~2 minutes under launchd's background I/O
# band at load 25-107 (the 22-minute switch outage: two resolves per boot,
# 199 MB each, re-hashed from scratch every time). Both trees therefore
# verify through stat-tripwire caches (verify-stat-cache.json for the server
# tree, node-tree-stat-cache.json for the Node tree; see round 3 A1): an
# all-match cached verify equals the recorded digest, any mismatch falls
# back to the full re-hash. `doctor --full` forces the full re-hash past
# both caches. The receipts, not the caches, remain the anchors.
VERIFY_TREE_AT_RESOLVE = True
# Round 3 / FU4: every MMOS_*/TEAM_SERVER_* environment seam in this tool
# is TEST-ONLY and gated behind MMOS_TEST_SEAMS=1. Outside the test harness
# a hostile shell cannot steer lsof/ps/launchctl, the LaunchAgents location
# or the verify valve by environment. PYTHON3_BIN (team_server.sh) is
# deliberately NOT gated: it is an operator knob, validated absolute and
# executable.
TEST_SEAM_FLAG = "MMOS_TEST_SEAMS"
TEST_SEAM_VARS = ("MMOS_LSOF_BIN", "MMOS_PS_BIN", "MMOS_LAUNCHCTL_BIN",
                  "TEAM_SERVER_LAUNCHAGENTS_DIR", "MMOS_VERIFY_DELAY_SECONDS")


class InstallError(Exception):
    """The tested, operator-actionable refusal."""


def lexically_inside(name, prefix):
    return name == prefix or name.startswith(prefix + "/")


def realpath_inside(path, root):
    """F7: containment compares realpaths, not spellings."""
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    return real == real_root or real.startswith(real_root + os.sep)


def private_dir(path, create=False):
    """A real directory, not a symlink, private and owned by this user.

    With create=True an owned directory that is too loose (a legacy root's
    0755 config/ or runtime/) is tightened to 0700 rather than refused — the
    tool already owns it. The server ROOT itself is never chmod'd by this
    tool; callers pass create=False for it, so an over-loose root refuses.
    """
    if os.path.islink(path):
        raise InstallError(f"symlinked directory refused: {path}")
    if create:
        os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise InstallError(f"missing directory: {path}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise InstallError(f"not a directory: {path}")
    if info.st_uid != os.getuid():
        raise InstallError(f"directory belongs to another user: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        if create:
            os.chmod(path, 0o700)
        else:
            raise InstallError(f"directory must be mode 0700: {path}")
    return path


def regular_file(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise InstallError(f"missing file: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise InstallError(f"not a regular file: {path}")
    if info.st_uid != os.getuid():
        raise InstallError(f"file belongs to another user: {path}")
    return path


def sha256(path):
    digest = hashlib.sha256()
    with open(regular_file(path), "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_digest(checksum, archive_name):
    """Read only GNU two-space SHASUMS256 entries, exactly one for this file."""
    found = []
    with open(regular_file(checksum), encoding="utf-8") as stream:
        for line in stream:
            digest, separator, name = line.rstrip("\n").partition("  ")
            if separator and name == archive_name:
                if not HEX64.fullmatch(digest):
                    raise InstallError("invalid checksum file")
                found.append(digest)
    if len(found) != 1:
        raise InstallError("checksum file lacks one exact archive entry")
    if found[0] != OFFICIAL_SHA256:
        raise InstallError("checksum record does not match the pinned official Node release")
    return found[0]


def checked_members(tf, prefix):
    """Validate tar metadata from the exact open file later extracted.

    Every refusal below has a test; none of them trusts the archive's own
    spelling of a path beyond the pinned top-level directory.
    """
    if tf is None:
        raise InstallError("an opened tar archive is required")
    members = []
    bytes_total = 0
    for member in tf:
        name = member.name.removesuffix("/")
        parts = name.split("/")
        if (not name or name.startswith(("/", "\\")) or parts[0] != prefix or
                any(p in ("", ".", "..") for p in parts)):
            raise InstallError(f"unsafe archive member: {name[:120]!r}")
        if member.isreg():
            bytes_total += member.size
            if bytes_total > BYTE_BUDGET:
                raise InstallError("archive member/byte budget exceeded")
        elif member.isdir():
            pass
        elif member.issym():
            target = member.linkname
            if not target or os.path.isabs(target) or target.startswith("\\"):
                raise InstallError(f"unsafe archive link: {name!r}")
            resolved = os.path.normpath(os.path.join(os.path.dirname(name), target))
            if not lexically_inside(resolved, prefix):
                raise InstallError(f"escaping archive link refused: {name!r}")
            # Only the three known npm-family links may appear in bin/.
            if len(parts) == 3 and parts[:2] == [prefix, "bin"]:
                if parts[2] not in ALLOWED_LINKS:
                    raise InstallError(f"unexpected archive link in bin/: {name!r}")
                if target != ALLOWED_LINKS[parts[2]]:
                    raise InstallError(f"archive link target mismatch: {name!r}")
        else:
            # Hardlinks, fifo/char/block devices and anything else special.
            raise InstallError("hardlink, device or special archive member refused")
        if member.mode & 0o7000:
            raise InstallError("privileged archive mode refused")
        members.append(member)
        if len(members) > MEMBER_BUDGET:
            raise InstallError("archive member/byte budget exceeded")
    if not members:
        raise InstallError("empty archive")
    return members, prefix


def fsync_dir(path):
    """F22: make a completed rename durable. Best effort on filesystems that
    refuse directory fsync; a refusal to fsync must not fail the install."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def private_write(path, payload, mode=0o600):
    """F3: write to a private temp, fsync, atomically replace; clean the temp
    only when the replace did not happen. The temp is never unlinked before
    the replace."""
    temp = path + ".tmp"
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), mode)
    except FileExistsError as exc:
        raise InstallError(f"write conflict, try after removing: {temp}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fsync_dir(os.path.dirname(path) or ".")
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def ensure_receipt_writable(path, payload):
    """F4: refuse BEFORE publication when an existing outside receipt
    conflicts with the payload this install is about to publish. An equal
    receipt is fine (retry repair); anything else — foreign, older schema,
    unreadable, a symlink — refuses with the recovery move spelled out, and
    the caller has not published anything yet."""
    if not os.path.lexists(path):
        return
    if os.path.islink(path):
        raise InstallError(f"symlinked receipt refused: {path} — move it away and re-run install")
    regular_file(path)
    try:
        with open(path, encoding="utf-8") as stream:
            existing = stream.read()
    except OSError as exc:
        raise InstallError(
            f"cannot read existing receipt: {path} — inspect it, move it away "
            f"(mv {path} {path}.conflict) and re-run install") from exc
    if existing != payload:
        raise InstallError(
            f"conflicting existing receipt: {path} — inspect it and move it away "
            f"(mv {path} {path}.conflict), then re-run install")


def idempotent_receipt(path, payload):
    """Publish a receipt unless an equal one is already there (retry repair);
    refuse on any conflicting content, never overwrite it."""
    if os.path.lexists(path):
        if os.path.islink(path):
            raise InstallError(f"symlinked receipt refused: {path}")
        regular_file(path)
        try:
            with open(path, encoding="utf-8") as stream:
                if stream.read() == payload:
                    return
        except OSError as exc:
            raise InstallError(f"cannot read receipt: {path}") from exc
        raise InstallError(f"conflicting existing receipt: {path}")
    private_write(path, payload)


def tree_sha256(directory, status_file=None, note_stage=None, note_every=500,
                entries_out=None):
    """Deterministic digest of a published tree, excluding its own receipt
    (which embeds this digest and so cannot cover itself). Schema 2: every
    entry contributes — directories (including empty ones) contribute
    path+mode; symlinked directories and file symlinks contribute
    path+target; regular files contribute path+mode+size+bytes. Any entry
    that is not a regular file, a directory or a symlink (a FIFO, socket or
    device) is refused WITHOUT being opened, so a planted FIFO cannot hang
    the digest. Used to verify, on a retry and in doctor, that an existing
    destination is still the tree this exact archive produced.

    Micro-fix HIGH-2: with status_file AND note_stage the walk appends a
    boot.status heartbeat every `note_every` entries — a 199 MB tree hash
    otherwise writes one note and then goes silent long enough for
    wait_ours's 30 s freshness rule to read a working boot as dead.

    Micro-fix HIGH-3: with entries_out the walk ALSO records each entry's
    stat triple (the _node_tree_entries schema) in the SAME per-entry visit
    that feeds the digest, so a caller can cache exactly what it hashed —
    never a stat snapshot of a later, different tree."""
    digest = hashlib.sha256()
    seen = 0

    def feed(relative, kind, extra):
        nonlocal seen
        digest.update(relative.encode("utf-8") + b"\0" + kind.encode("ascii") +
                      extra.encode("utf-8") + b"\0")
        seen += 1
        if status_file and note_stage and seen % note_every == 0:
            _status_note(status_file, note_stage)

    def remember(relative, kind, extra, info, size):
        if entries_out is not None:
            entries_out[relative] = [kind, extra, size, info.st_mtime_ns,
                                     info.st_ctime_ns]

    for current, dirnames, filenames in os.walk(directory):
        dirnames.sort()
        for name in dirnames:
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, directory)
            info = os.lstat(absolute)
            if stat.S_ISLNK(info.st_mode):
                # os.walk does not descend into symlinked directories
                # (followlinks=False), but they still must contribute.
                feed(relative, "l", os.readlink(absolute))
                remember(relative, "l", os.readlink(absolute), info, 0)
            else:
                feed(relative, "d", oct(stat.S_IMODE(info.st_mode) & 0o7777))
                remember(relative, "d",
                         f"{stat.S_IMODE(info.st_mode) & 0o7777:o}", info, 0)
        for name in sorted(filenames):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, directory)
            if relative == "INSTALL_RECEIPT.json":
                continue
            info = os.lstat(absolute)
            if stat.S_ISLNK(info.st_mode):
                feed(relative, "l", os.readlink(absolute))
                remember(relative, "l", os.readlink(absolute), info, 0)
            elif not stat.S_ISREG(info.st_mode):
                # FIFO, socket, device: refused before any open() can block.
                raise InstallError(f"non-regular tree entry refused: {relative}")
            else:
                feed(relative, "f", f"{stat.S_IMODE(info.st_mode) & 0o7777:o}:{info.st_size}")
                remember(relative, "f",
                         f"{stat.S_IMODE(info.st_mode) & 0o7777:o}",
                         info, info.st_size)
                with open(absolute, "rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
    return digest.hexdigest()


def validated_root(root, create=False):
    """F4/F8: reject a symlinked root before any realpath, then require the
    resolved root to stay private, owned, and outside the Chairman's ~/.t3.
    A missing root may be created 0700; an existing loose root is refused,
    never silently tightened (that tightening is the operator's act).
    The ~/.t3 scope is checked on the LEXICAL realpath (resolving only the
    existing prefix) BEFORE anything is created, so a refused root never
    leaves a freshly-created ~/.t3/<name> directory behind (attack finding 4)."""
    root = os.path.abspath(os.path.expanduser(root))
    real_t3 = os.path.realpath(os.path.expanduser("~/.t3"))
    probe = os.path.realpath(root)  # non-strict: resolves the existing prefix
    if probe == real_t3 or probe.startswith(real_t3 + os.sep):
        raise InstallError("the Chairman's ~/.t3 is out of scope")
    if create and not os.path.lexists(root):
        os.makedirs(root, mode=0o700)
    private_dir(root, create=False)
    root = os.path.realpath(root)
    private_dir(root)
    if root == real_t3 or root.startswith(real_t3 + os.sep):
        raise InstallError("the Chairman's ~/.t3 is out of scope")
    return root


def verified_extract(archive, expected, stage, prefix):
    """F5: copy the archive into private staging, then hash, member-check and
    extract that one copy from a single open file. The bytes extracted are
    bound to the bytes verified. Used by both the fresh install and the
    retry-repair branch (which must prove the published tree is what this
    exact official archive produces — attack finding 5)."""
    private_copy = os.path.join(stage, ARCHIVE)
    shutil.copyfile(archive, private_copy)
    os.chmod(private_copy, 0o600)
    regular_file(private_copy)
    with open(private_copy, "rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        if digest.hexdigest() != expected:
            raise InstallError("tampered archive: SHA-256 mismatch")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:gz") as tf:
            members, _ = checked_members(tf, prefix)
            # 'data' is a second, independent safety filter; it also blocks
            # archive-driven ownership changes.
            tf.extractall(stage, members=members, filter="data")
    os.unlink(private_copy)


def trusted_interpreter(path, root):
    """Item 13: the interpreter recorded for later runs must be an absolute
    path to a regular executable file owned by root or the current user, and
    must not live inside the server root (nothing inside the root is pinned
    by an outside authority). The caller records the RESOLVED realpath, so
    nothing is re-resolved — and thus interceptable — at run time."""
    if not path or not os.path.isabs(path):
        raise InstallError(f"interpreter must be an absolute path: {path!r}")
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise InstallError(f"interpreter not found: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise InstallError(f"interpreter is not a regular file: {path}")
    if info.st_uid not in (0, os.getuid()):
        raise InstallError(f"interpreter belongs to another user: {path}")
    if realpath_inside(path, root):
        raise InstallError(f"interpreter must not live inside the server root: {path}")
    if not os.access(path, os.X_OK):
        raise InstallError(f"interpreter is not executable: {path}")
    return path


def _require_teammate_safe_dir(folder, what, strict_leaf=True):
    """Item F: every component from / down to `folder` must be a place a
    teammate (another local user) cannot plant or swap a binary in.

    The folder itself (strict_leaf=True, the recorded folder and the
    resolution-target folder) must have NO group/other write at all. For the
    ANCESTORS above it, group/other write is refused unless the sticky bit
    is set — a sticky 1777 directory (/tmp, /var/tmp) is the OS's own
    mitigation: anyone may create entries there, but only their owner may
    rename or remove them, so this user's subtree under it cannot have its
    entries swapped by anyone else. The owner of every component must be
    root or the current user (root is the OS, not a teammate — /usr, /opt
    and friends are root-owned by design)."""
    folder = os.path.realpath(folder).rstrip("/") or "/"
    components = [] if folder == "/" else folder.strip("/").split("/")
    current = ""
    for index, part in enumerate(components):
        current += "/" + part
        leaf = index == len(components) - 1
        try:
            info = os.stat(current)
        except OSError as exc:
            raise InstallError(f"{what} not found: {current}") from exc
        if info.st_uid not in (0, os.getuid()):
            raise InstallError(
                f"{what} is owned by another user (a teammate could control "
                f"it): {current}")
        if info.st_mode & 0o022 and (leaf and strict_leaf
                                     or not info.st_mode & stat.S_ISVTX):
            raise InstallError(
                f"{what} is writable by group or others: {current} "
                f"({stat.filemode(info.st_mode)}) — a teammate could plant "
                f"or swap a provider binary there")


def validated_provider_cli(cli, root=None):
    """Item F: validate the provider CLI binary and return the folder install
    records as config/provider-cli-dir.

    The record is the folder the binary is NAMEABLE in (its dirname, fully
    resolved), because the server's PATH must resolve `claude` by name. The
    binary's RESOLUTION target tree gets the same teammate-safety walk: the
    stock Claude install is a symlink (`~/.local/bin/claude` ->
    `~/.local/share/claude/versions/<v>`), and the folder that names the
    binary is only as trustworthy as the tree the symlink resolves into.
    python3-path precedent: the folder must not live inside the server root
    (nothing inside the root is pinned by an outside authority, and uninstall
    would delete it)."""
    path = os.path.expanduser(str(cli))
    if not path or not os.path.isabs(path):
        raise InstallError(f"provider CLI must be an absolute path: {cli!r}")
    # MF-MED-REQ-1(b): the record is the FOLDER and the server PATH-resolves
    # `claude` BY NAME inside it. Any other basename validates a file the
    # server never executes while the <folder>/claude it does execute goes
    # unchecked. Fail closed on the name.
    if os.path.basename(path) != "claude":
        raise InstallError(
            f"provider CLI must be named 'claude' (the server PATH-resolves "
            f"`claude` by name in the recorded folder; a differently named "
            f"file is never the executed one): {path}")
    try:
        info = os.stat(path)
    except OSError as exc:
        raise InstallError(f"provider CLI not found: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise InstallError(f"provider CLI is not a regular file: {path}")
    if not os.access(path, os.X_OK):
        raise InstallError(f"provider CLI is not executable: {path}")
    # F-HIGH-1 (micro-fix round): the executed FILE itself, not only its
    # folders. The folder walks stop a teammate PLANTING or SWAPPING a
    # binary; they do not stop an in-place rewrite — open(O_TRUNC) needs the
    # file's own write bits, no directory write at all. Both the named path
    # and its resolution target must be owned by root or this user (the
    # trusted_interpreter rule) and carry no group/other write bits.
    # MF-MED-REQ-1(a): the file the server will actually execute is
    # <realpath of the recorded folder>/claude and its resolution target —
    # when the naming folder is a symlink chain those can differ from what
    # this argument named, so they get the same check, and a missing one is
    # a clean refusal: never record a folder whose `claude` is not there.
    folder = os.path.dirname(path)
    executed = os.path.join(os.path.realpath(folder), "claude")
    for what, target in (("provider CLI", path),
                         ("provider CLI resolution target",
                          os.path.realpath(path)),
                         ("provider CLI the server executes", executed),
                         ("provider CLI the server executes, resolved",
                          os.path.realpath(executed))):
        try:
            finfo = os.stat(target)
        except OSError as exc:
            raise InstallError(f"{what} not found: {target}") from exc
        if finfo.st_uid not in (0, os.getuid()):
            raise InstallError(
                f"{what} belongs to another user (a teammate could rewrite "
                f"its executed bytes in place): {target}")
        if finfo.st_mode & 0o022:
            raise InstallError(
                f"{what} is writable by group or others (any local user "
                f"could rewrite the executed bytes in place — no directory "
                f"write needed): {target} ({stat.filemode(finfo.st_mode)})")
    _require_teammate_safe_dir(folder, "provider CLI folder")
    _require_teammate_safe_dir(os.path.dirname(os.path.realpath(path)),
                               "provider CLI resolution target")
    # F-MED-A (micro-fix round): containment covers the naming folder AND
    # the resolution-target folder — a safe outside folder symlinking a
    # binary that actually lives inside the root would otherwise pass, and
    # uninstall would delete the executed binary.
    if root and (realpath_inside(folder, root) or
                 realpath_inside(os.path.dirname(os.path.realpath(path)),
                                 root)):
        raise InstallError(
            f"provider CLI must not live inside the server root: {folder}")
    return os.path.realpath(folder)


def record_provider_cli(root, cli):
    """Item F: validate the provider CLI and record its folder the way
    trusted_interpreter is recorded (config/, 0600, one atomic write)."""
    root = validated_root(root)
    folder = validated_provider_cli(cli, root=root)
    config_dir = private_dir(os.path.join(root, "config"), create=True)
    # F-MED-B (micro-fix round): a killed earlier run can leave this
    # writer's temp behind and O_EXCL then refuses every retry — clean_dead_
    # leftovers removes it on the node_install install path, but this
    # subcommand also runs alone. A symlink is refused, never followed.
    temp = os.path.join(config_dir, "provider-cli-dir.tmp")
    if os.path.lexists(temp):
        if os.path.islink(temp) or not os.path.isfile(temp):
            raise InstallError(f"symlinked or non-regular temp refused: {temp}")
        os.unlink(temp)
    private_write(os.path.join(config_dir, "provider-cli-dir"), folder + "\n")
    return folder


def install_lock(runtime_dir):
    """F5/F6: one installer at a time per root. The lock is an flock on a
    private file inside runtime/; a second installer refuses in one line.
    The fd is returned and must be closed by the caller to release."""
    lock_path = os.path.join(runtime_dir, "install.lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise InstallError(
            "another install is already running for this root; let it finish "
            "before retrying")
    return fd


def clean_dead_leftovers(root, runtime_dir, staging_parent, config_dir):
    """F5/F6: called with the install lock held, so any leftover that carries
    this installer's own names is debris from a killed run, not live work.
    Remove staging directories and receipt temps so the retry the runbook
    prescribes actually succeeds."""
    for name in os.listdir(staging_parent):
        if name.startswith(".node-install-"):
            target = os.path.join(staging_parent, name)
            if os.path.islink(target) or not os.path.isdir(target):
                # Attack finding 10: name the removal — a one-line refusal
                # with no next action is not a recovery.
                raise InstallError(
                    f"unexpected staging leftover (not a directory): {target} "
                    f"— inspect it, remove it by hand (rm -rf {target}), "
                    f"then re-run install")
            shutil.rmtree(target)
    # Attack finding 2: python3-path.tmp is this installer's temp too; a kill
    # during private_write left it behind and O_EXCL refused every later run.
    # provider-cli-dir.tmp (F-MED-B, micro-fix round): same failure class —
    # a leftover wedged every later install at record-provider.
    for temp in (os.path.join(runtime_dir, "install-receipt.json.tmp"),
                 os.path.join(config_dir, "node-runtime.json.tmp"),
                 os.path.join(config_dir, "python3-path.tmp"),
                 os.path.join(config_dir, "provider-cli-dir.tmp")):
        if os.path.lexists(temp):
            if os.path.islink(temp):
                raise InstallError(f"symlinked temp refused: {temp}")
            os.unlink(temp)


def install_node(root, archive, checksum, version=VERSION):
    if version != VERSION:
        raise InstallError(f"Node version must be exactly {VERSION}")
    root = validated_root(root, create=True)
    archive = os.path.abspath(os.path.expanduser(archive))
    checksum = os.path.abspath(os.path.expanduser(checksum))
    if os.path.basename(archive) != ARCHIVE:
        raise InstallError(f"archive must be named {ARCHIVE}")
    regular_file(archive)  # regular, current-user-owned input before any copy
    expected = official_digest(checksum, ARCHIVE)
    runtime_dir = private_dir(os.path.join(root, "runtime"), create=True)
    staging_parent = private_dir(os.path.join(runtime_dir, "staging"), create=True)
    config_dir = private_dir(os.path.join(root, "config"), create=True)
    destination = os.path.join(runtime_dir, INSTALL_DIR_NAME)
    lock_fd = install_lock(runtime_dir)
    try:
        clean_dead_leftovers(root, runtime_dir, staging_parent, config_dir)
        receipt = {
            "schemaVersion": SCHEMA_VERSION,
            "kind": "official-nodejs-install",
            "version": "v" + VERSION,
            "architecture": "arm64",
            "platform": "darwin",
            "nodePath": os.path.join(destination, "bin", "node"),
            "installDir": destination,
            "archiveSha256": OFFICIAL_SHA256,
            "checksumRecord": f"https://nodejs.org/dist/v{VERSION}/SHASUMS256.txt",
            "archiveUrl": f"https://nodejs.org/dist/v{VERSION}/{ARCHIVE}",
            "supportedBy": {"server": NODE_REQUIREMENT, "vitePlus": BUILD_REQUIREMENT},
            "verification": "one private copy hashed, member-checked and extracted "
                            "from a single open file; receipt published by one rename",
        }
        if os.path.lexists(destination):
            return _repair_activation(root, archive, expected, destination,
                                      runtime_dir, config_dir, staging_parent,
                                      receipt)
        return _fresh_install(archive, expected, destination, runtime_dir,
                              config_dir, staging_parent, receipt)
    finally:
        os.close(lock_fd)


def _repair_activation(root, archive, expected, destination, runtime_dir,
                       config_dir, staging_parent, receipt):
    """A destination with this exact in-tree receipt is an interrupted-after-
    publish install: the receipt's fields AND its treeSha256 are verified
    against the tree actually on disk before any marker is repaired — a
    planted receipt over a tampered tree must refuse, not be blessed with
    the official sha attestation (attack finding 5)."""
    if os.path.islink(destination):
        raise InstallError(f"symlinked destination refused: {destination}")
    in_tree = os.path.join(destination, "INSTALL_RECEIPT.json")
    content = None
    try:
        regular_file(in_tree)
        with open(in_tree, encoding="utf-8") as stream:
            content = stream.read()
        existing = json.loads(content)
    except (InstallError, OSError, ValueError):
        raise InstallError(
            "destination already exists without this exact receipt; "
            "inspect and move it away before retrying")
    expected_fields = {
        "schemaVersion": SCHEMA_VERSION, "kind": "official-nodejs-install",
        "version": "v" + VERSION, "architecture": "arm64", "platform": "darwin",
        "nodePath": os.path.join(destination, "bin", "node"),
        "installDir": destination, "archiveSha256": OFFICIAL_SHA256,
    }
    recorded = existing.get("treeSha256")
    if any(existing.get(k) != v for k, v in expected_fields.items()) or \
            not isinstance(recorded, str) or not HEX64.fullmatch(recorded):
        raise InstallError(
            "destination already exists without this exact receipt; "
            "inspect and move it away before retrying")
    if tree_sha256(destination) != recorded:
        raise InstallError(
            "destination tree no longer matches its receipt (treeSha256 "
            "mismatch); inspect and move it away before retrying")
    # F4: refuse on a conflicting OUTSIDE receipt before any work, so this
    # branch never repairs half way and never has to publish anything.
    ensure_receipt_writable(os.path.join(runtime_dir, "install-receipt.json"), content)
    ensure_receipt_writable(os.path.join(config_dir, "node-runtime.json"), content)
    # A forged receipt whose digest was recomputed over a tampered tree
    # still refuses here: the official archive is re-verified end-to-end
    # and the published tree must be byte-identical to a fresh extraction
    # of it (attack finding 5).
    stage = tempfile.mkdtemp(prefix=".node-install-", dir=staging_parent)
    try:
        verified_extract(archive, expected, stage, INSTALL_DIR_NAME)
        if tree_sha256(os.path.join(stage, INSTALL_DIR_NAME)) != recorded:
            raise InstallError(
                "destination does not match a fresh extraction of the "
                "official archive; inspect and move it away before retrying")
    finally:
        if os.path.isdir(stage) and not os.path.islink(stage):
            shutil.rmtree(stage)
    payload = content  # the verified in-tree bytes are the canonical payload
    idempotent_receipt(os.path.join(runtime_dir, "install-receipt.json"), payload)
    idempotent_receipt(os.path.join(config_dir, "node-runtime.json"), payload)
    # Attack finding 1: an interrupted-after-publish install can be missing
    # config/python3-path (the sole fresh-install writer never ran). The
    # repair must complete the WHOLE activation — re-record the validated
    # interpreter this run is executing under — or a later runner start
    # wedges on exit 78 while this command reports success. The same branch
    # also heals an interpreter that disappeared after it was recorded
    # (Homebrew removed it): the recorded path is replaced by the one this
    # verified run actually uses.
    interpreter = trusted_interpreter(os.path.realpath(sys.executable),
                                      destination_root(destination))
    private_write(os.path.join(config_dir, "python3-path"), interpreter + "\n")
    print(f"NODE_INSTALLED version=v{VERSION} node={receipt['nodePath']} "
          f"sha256={OFFICIAL_SHA256} (activation repaired; tree verified)")
    return existing


def _fresh_install(archive, expected, destination, runtime_dir,
                   config_dir, staging_parent, receipt):
    stage = tempfile.mkdtemp(prefix=".node-install-", dir=staging_parent)
    try:
        verified_extract(archive, expected, stage, INSTALL_DIR_NAME)
        extracted = os.path.join(stage, INSTALL_DIR_NAME)
        executable = os.path.join(extracted, "bin", "node")
        info = os.lstat(executable)
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o100:
            raise InstallError("extracted Node executable is missing")
        # The receipt binds the exact tree it travels in: its digest is
        # computed over the staged tree (self-excluded) and verified whenever
        # this destination is later "repaired" (attack finding 5).
        receipt["treeSha256"] = tree_sha256(extracted)
        payload = json.dumps(receipt, indent=2) + "\n"
        # The receipt travels inside the staged tree; one atomic rename
        # publishes tree and receipt together. No bytes are published without
        # their receipt, and no receipt is written after publication.
        private_write(os.path.join(extracted, "INSTALL_RECEIPT.json"), payload)
        # F4: everything that can refuse AFTER the rename is checked BEFORE
        # it — a conflicting outside receipt must leave nothing published.
        ensure_receipt_writable(os.path.join(runtime_dir, "install-receipt.json"), payload)
        ensure_receipt_writable(os.path.join(config_dir, "node-runtime.json"), payload)
        os.rename(extracted, destination)
        fsync_dir(runtime_dir)  # F22: the tree rename is the publish
        # Attack finding 3 (honest state): every REFUSAL fires above, before
        # the rename. An OS error below it (unwritable config/, full disk) can
        # leave the tree published with markers missing — that is not a
        # refusal, and the retry completes the whole activation via the
        # matching-receipt repair branch above (receipts AND interpreter).
        idempotent_receipt(os.path.join(runtime_dir, "install-receipt.json"), payload)
        idempotent_receipt(os.path.join(config_dir, "node-runtime.json"), payload)
        interpreter = trusted_interpreter(os.path.realpath(sys.executable),
                                          destination_root(destination))
        private_write(os.path.join(config_dir, "python3-path"),
                      interpreter + "\n")
        print(f"NODE_INSTALLED version=v{VERSION} node={receipt['nodePath']} "
              f"sha256={OFFICIAL_SHA256}")
        return receipt
    finally:
        if os.path.isdir(stage) and not os.path.islink(stage):
            shutil.rmtree(stage)


def destination_root(destination):
    """The server root that contains this install destination."""
    return os.path.dirname(os.path.dirname(destination))


def load_receipt(path):
    with open(regular_file(path), encoding="utf-8") as stream:
        receipt = json.load(stream)
    if receipt.get("schemaVersion") != SCHEMA_VERSION:
        raise InstallError(
            f"runtime receipt schema {receipt.get('schemaVersion')!r} is not "
            f"supported (this build requires {SCHEMA_VERSION}); move "
            f"{os.path.basename(path)} aside and reinstall with "
            f"'node_install.py install'")
    return receipt


def _load_stat_cache(path):
    """Best-effort load of the (size, mtime_ns, ctime_ns) skip-cache."""
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    clean = {}
    for rel, triple in data.items():
        if (isinstance(rel, str) and isinstance(triple, list) and len(triple) == 3
                and all(isinstance(v, int) and not isinstance(v, bool)
                        for v in triple)):
            clean[rel] = triple
    return clean


def _save_stat_cache(path, fresh):
    """Best-effort persist; a read-only release dir only costs re-hashing."""
    if not fresh:
        return
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(fresh, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _status_note(status_file, stage):
    """Round 3 B: append `stage=<name> <epoch>` to the boot status file so a
    slow start is observable (an empty server.log never again means
    "working"). Credential-free; best-effort — a read-only run dir must not
    turn observability into a refusal."""
    if not status_file:
        return
    try:
        with open(status_file, "a", encoding="utf-8") as stream:
            stream.write(f"stage={stage} {int(time.time())}\n")
    except OSError:
        pass


def _load_node_cache(path):
    """Best-effort load of the Node tree's entry cache. Schema:
    {"__treeSha256__": <hex>, rel: [kind, extra, size, mtime_ns, ctime_ns]}
    with kind in {d,f,l} and mtime_ns/ctime_ns ints (extra is the octal mode
    string, or the link target for symlinks)."""
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    clean = {}
    for rel, entry in data.items():
        if rel == "__treeSha256__":
            if isinstance(entry, str) and HEX64.fullmatch(entry):
                clean[rel] = entry
            continue
        if (isinstance(rel, str) and isinstance(entry, list) and len(entry) == 5
                and entry[0] in ("d", "f", "l")
                and isinstance(entry[1], str)
                and all(isinstance(v, int) and not isinstance(v, bool)
                        for v in entry[2:])):
            clean[rel] = entry
    return clean


def _verify_valve(stage, status_file, root=None):
    """TEST-ONLY: hold a verify stage open (with a fresh status note) so
    tests can exercise a slow boot deterministically. Two channels, because
    launchd starts the runner with NO environment (env -i at bootstrap keeps
    the installer's env out of the job):
      * MMOS_VERIFY_DELAY_SECONDS in the environment — the in-process/
        CLI-test channel, refused unless MMOS_TEST_SEAMS=1 like every other
        env seam;
      * <root>/config/verify-delay — the RUNNER channel (the same
        root-config-file pattern as TEAM_SERVER_LOG_CAP's config/log-cap).
        The file lives inside the 0700 root, so only the root's owner can
        plant it; an absent, unreadable or non-numeric file delays nothing.
    """
    seconds = None
    delay = os.environ.get("MMOS_VERIFY_DELAY_SECONDS")
    if delay:
        if not _test_seams_on():
            raise InstallError(
                f"MMOS_VERIFY_DELAY_SECONDS is set but {TEST_SEAM_FLAG} is not 1; "
                f"test-only environment seams are refused outside the test harness")
        try:
            seconds = float(delay)
        except ValueError:
            raise InstallError("MMOS_VERIFY_DELAY_SECONDS must be a number") from None
    elif root:
        try:
            with open(os.path.join(validated_root(root), "config",
                                   "verify-delay"), encoding="ascii") as fh:
                delay = fh.readline().strip()
        except (OSError, UnicodeError):
            delay = ""
        if delay.isdigit():
            seconds = float(delay)
    if seconds is not None and 0 <= seconds <= 600:
        # Micro-fix HIGH-2: note AFTER the hold, never before — a note written
        # before sleeping is exactly the stale-note starvation a long silent
        # walk produced. Freshness during real work comes from the walk
        # heartbeats (every 500 entries), not from this valve.
        time.sleep(seconds)
        _status_note(status_file, stage)


def _node_tree_entries(install_dir, status_file=None, note_every=500):
    """Enumerate the Node tree exactly as tree_sha256 does (sorted os.walk,
    INSTALL_RECEIPT.json excluded, non-regular entries refused), returning
    {rel: [kind, extra, size, mtime_ns, ctime_ns]} for files AND directories
    (a changed mode/owner/mtime on a directory is part of the digest too).
    Micro-fix HIGH-2: with status_file the walk appends a boot.status
    heartbeat every `note_every` entries, so a long stat walk stays fresh."""
    entries = {}
    seen = 0
    for current, dirnames, filenames in os.walk(install_dir):
        dirnames.sort()
        for name in dirnames + sorted(filenames):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, install_dir)
            if relative == "INSTALL_RECEIPT.json":
                continue
            seen += 1
            if status_file and seen % note_every == 0:
                _status_note(status_file, "verify-node")
            info = os.lstat(absolute)
            if stat.S_ISLNK(info.st_mode):
                entries[relative] = ["l", os.readlink(absolute), 0,
                                     info.st_mtime_ns, info.st_ctime_ns]
            elif stat.S_ISDIR(info.st_mode):
                entries[relative] = ["d", f"{stat.S_IMODE(info.st_mode) & 0o7777:o}",
                                     0, info.st_mtime_ns, info.st_ctime_ns]
            elif not stat.S_ISREG(info.st_mode):
                raise InstallError(f"non-regular tree entry refused: {relative}")
            else:
                entries[relative] = ["f", f"{stat.S_IMODE(info.st_mode) & 0o7777:o}",
                                     info.st_size, info.st_mtime_ns,
                                     info.st_ctime_ns]
    return entries


def _verify_node_tree(install_dir, recorded, status_file=None, force_full=False,
                      root=None):
    """Round 3 A1: verify the pinned Node tree against the receipt's
    treeSha256 through a stat-tripwire cache.

    Why: the runner resolves twice per boot and each resolve re-hashed the
    whole 199 MB tree from scratch; under launchd's background I/O band at
    load 25-107 that alone held the boot in state U for minutes (the
    22-minute switch outage). The cache lives at
    <root>/runtime/node-tree-stat-cache.json — beside install_dir, never
    inside it, because the digest covers every install_dir entry except the
    receipt itself. Semantics match the server tree's verify-stat-cache: all
    (kind, extra, size, mtime_ns, ctime_ns) triples present and equal plus a
    matching cached digest == verified; any difference (a same-size in-place
    edit included — ctime is kernel-set) falls back to the full tree_sha256,
    which refuses on mismatch and rewrites the cache on success. The receipt,
    not the cache, is the anchor: a deleted cache can only make the next
    verify SLOW (full re-hash) — but a FORGED cache (triples plus the
    recorded digest, written by the root's own user) is accepted without any
    re-hash. The cache therefore changes nothing about the tamper model: a
    same-user writer of the root could edit the tree and the receipts alike,
    exactly as before the cache existed (MED d2-2 — the server tree's
    verify-stat-cache concedes the same). force_full (doctor --full) skips
    the cache read entirely and re-hashes."""
    cache_path = os.path.join(os.path.dirname(os.path.abspath(install_dir)),
                              "node-tree-stat-cache.json")
    _verify_valve("verify-node", status_file, root=root)
    cached = _load_node_cache(cache_path) if not force_full else {}
    if isinstance(cached.get("__treeSha256__"), str) and HEX64.fullmatch(
            cached.get("__treeSha256__", "")):
        _status_note(status_file, "verify-node")   # stat walk begins (warm)
        try:
            entries = _node_tree_entries(install_dir, status_file=status_file)
        except (InstallError, OSError):
            entries = None  # a non-regular entry: let the full digest refuse it
        if (entries is not None and len(entries) + 1 == len(cached)
                and cached.get("__treeSha256__") == recorded
                and all(cached.get(rel) == triple
                        for rel, triple in entries.items())):
            _status_note(status_file, "verify-node")
            return  # every triple matches: the tree is what we digest-recorded
    _status_note(status_file, "verify-node")   # full digest begins (cold)
    # Micro-fix HIGH-3: ONE walk — the triples are captured in the same
    # per-entry visit that feeds the digest, so the cache can only bless
    # what was actually hashed. The old second walk sampled the tree AFTER
    # the hash; a file changed in that gap left a cache whose triples
    # blessed the mutated file while the digest field still named the
    # pre-change tree, and every later boot rode it without re-hashing.
    fresh = {}
    digest = tree_sha256(install_dir, status_file=status_file,
                         note_stage="verify-node", entries_out=fresh)
    if digest != recorded:
        raise InstallError(
            "pinned Node tree no longer matches its receipt (treeSha256 "
            "mismatch); reinstall the runtime")
    _save_stat_cache(cache_path, {"__treeSha256__": digest, **fresh})


def verify_packed_server(build_dir, force_full=False, status_file=None, root=None):
    """Panel R1: verify the packed server tree against its recorded digests.

    file-digests.json (written by pack_server.mjs beside dist/) is the
    authority: every recorded file must exist as a regular non-link file with
    the recorded size and sha256, and every file in the tree except
    BUILD_RECEIPT.json (written after hashing) must be recorded — verifying
    only the recorded set would bless a planted payload. Returns the number
    of verified files. Raises InstallError naming the server tree and the
    offending file, so the refusal is operator-readable wherever it surfaces
    (resolve, doctor, or the runner's boot gate).

    Boot-time cost: a real packed tree is ~4500 files / 344 MB and a full
    re-hash measures ~15 s per pass (the runner resolves twice per boot, and
    resolve ran again at install and doctor), so every boot paying three
    full digests was both slow and the reason a first install could outrun
    its own wait window. After a file's content digest matches the record
    once, its (size, mtime_ns, ctime_ns) triple is remembered beside the
    record in verify-stat-cache.json; a later verify that sees the identical
    triple skips re-hashing that file. Any rewrite, truncate, chmod or
    replace changes at least one of mtime_ns/ctime_ns — ctime is set by the
    kernel and cannot be restored without root — so a changed file falls
    back to a full digest and fails. The record, not the cache, stays the
    anchor: cache entries exist only for paths the record names, and the
    record's own tamper model (same-user writer of the root) is unchanged.
    """
    release_dir = os.path.dirname(build_dir)
    digests_path = os.path.join(release_dir, DIGESTS_NAME)
    try:
        with open(regular_file(digests_path), encoding="utf-8") as stream:
            recorded = json.load(stream)
    except InstallError:
        raise
    except FileNotFoundError as exc:
        raise InstallError(
            f"server tree cannot be verified: {DIGESTS_NAME} is missing next "
            f"to {build_dir}; repack, or roll back per the runbook") from exc
    except (OSError, ValueError) as exc:
        raise InstallError(f"cannot read {digests_path}: {exc}") from exc
    if not isinstance(recorded, list) or not recorded:
        raise InstallError(f"{digests_path} is not a non-empty digest list")

    def refuse(detail):
        raise InstallError(
            f"server tree no longer matches {DIGESTS_NAME} ({detail}); repack, "
            f"or roll back per the runbook")

    cache = {} if force_full else _load_stat_cache(
        os.path.join(release_dir, "verify-stat-cache.json"))
    _verify_valve("verify-server", status_file, root=root)
    verified = {}
    for index, entry in enumerate(recorded):
        if status_file and index % 500 == 0:
            _status_note(status_file, "verify-server")
        if not isinstance(entry, dict):
            refuse(f"{digests_path} has a malformed entry")
        rel, size, sha = entry.get("path"), entry.get("bytes"), entry.get("sha256")
        if (not isinstance(rel, str) or not rel or rel.startswith("/") or
                rel == "." or "\\" in rel or
                any(part in ("", ".", "..") for part in rel.split("/")) or
                not isinstance(size, int) or isinstance(size, bool) or size < 0 or
                not isinstance(sha, str) or not HEX64.fullmatch(sha)):
            refuse(f"{digests_path} has a malformed entry: {entry!r}")
        if rel in verified or rel in PACK_EXCLUDED:
            refuse(f"{digests_path} records {rel} twice or records an excluded file")
        target = os.path.join(build_dir, *rel.split("/"))
        if os.path.islink(target) or not os.path.isfile(target):
            refuse(f"{rel} is missing (or not a regular file)")
        info = os.stat(target)
        triple = [info.st_size, info.st_mtime_ns, info.st_ctime_ns]
        if cache.get(rel) == triple:
            verified[rel] = triple
            continue
        if info.st_size != size:
            refuse(f"{rel} is {info.st_size} bytes, recorded {size}")
        with open(target, "rb") as stream:
            if hashlib.sha256(stream.read()).hexdigest() != sha:
                refuse(f"{rel} content digest mismatch")
        verified[rel] = triple
    # Everything on disk must be recorded: an unlisted file is a plant.
    for current, dirnames, filenames in os.walk(build_dir):
        dirnames.sort()
        for name in dirnames:
            if os.path.islink(os.path.join(current, name)):
                refuse(f"{os.path.relpath(os.path.join(current, name), build_dir)} "
                       f"is a symlink")
        for name in sorted(filenames):
            absolute = os.path.join(current, name)
            rel = os.path.relpath(absolute, build_dir)
            if os.path.islink(absolute):
                refuse(f"{rel} is a symlink")
            if rel not in verified and rel not in PACK_EXCLUDED:
                refuse(f"unrecorded file in the server tree: {rel}")
    if verified != cache:
        _save_stat_cache(os.path.join(release_dir, "verify-stat-cache.json"),
                         verified)
    return len(verified)


def runtime_paths(root, verify_tree=True, status_file=None):
    """Resolve the pinned node and packed server entrypoint.

    Item 12: installDir is not taken from the receipt's word — it must be
    exactly <root>/runtime/node-v<VERSION>-darwin-arm64 as computed from the
    pinned constants, the in-tree INSTALL_RECEIPT.json must exist and agree
    with the config receipt on treeSha256, and nodePath must be that exact
    folder's bin/node as a regular non-link file. A writer of the one config
    file can therefore no longer point the runner at an arbitrary in-root
    executable. (A writer who can replace the runner script itself is outside
    what any receipt check can stop; the defence there is the 0700 root.)
    verify_tree=True (the default) additionally recomputes the full tree
    digest before the caller may exec anything from it.
    """
    root = validated_root(root)
    expected_install_dir = os.path.join(root, "runtime", INSTALL_DIR_NAME)
    node = load_receipt(os.path.join(root, "config", "node-runtime.json"))
    server = load_receipt(os.path.join(root, "config", "server-runtime.json"))
    if (node.get("version") != "v" + VERSION or
            node.get("archiveSha256") != OFFICIAL_SHA256):
        raise InstallError("unrecognized or incomplete Node install receipt")
    install_dir = node.get("installDir") or ""
    node_path = node.get("nodePath") or ""
    build_dir = server.get("buildDir") or ""
    server_bin = server.get("serverBin") or ""
    if not (install_dir and node_path and build_dir and server_bin):
        raise InstallError("runtime receipt is missing a required path")
    if os.path.realpath(install_dir) != os.path.realpath(expected_install_dir):
        raise InstallError(
            f"installDir must be the pinned {expected_install_dir}, not: {install_dir}")
    if node_path != os.path.join(install_dir, "bin", "node"):
        raise InstallError("nodePath must be installDir/bin/node")
    in_tree_path = os.path.join(install_dir, "INSTALL_RECEIPT.json")
    if os.path.islink(in_tree_path) or not os.path.isfile(in_tree_path):
        raise InstallError(f"missing in-tree install receipt: {in_tree_path}")
    try:
        with open(in_tree_path, encoding="utf-8") as stream:
            in_tree = json.load(stream)
    except (OSError, ValueError) as exc:
        raise InstallError(f"cannot read in-tree install receipt: {in_tree_path}") from exc
    if in_tree.get("treeSha256") != node.get("treeSha256"):
        raise InstallError("config receipt and in-tree receipt disagree on treeSha256")
    # F7: cross-check nodePath against installDir, serverBin against buildDir.
    if os.path.realpath(node_path) != os.path.realpath(
            os.path.join(install_dir, "bin", "node")):
        raise InstallError("nodePath does not resolve to installDir/bin/node")
    if os.path.basename(os.path.normpath(build_dir)) != "dist":
        raise InstallError("server runtime receipt does not name a dist directory")
    # Panel R3: Item 12's guarantee held for Node only — buildDir was
    # free-form, so a writer of config/server-runtime.json alone pointed
    # serverBin at any in-root */dist. The release folder must be exactly
    # <root>/runtime/<safe-release-ID> (computed on realpath, so a symlinked
    # path inside the root cannot launder an outsider either).
    real_build = os.path.realpath(build_dir)
    release_dir = os.path.dirname(real_build)
    runtime_dir = os.path.realpath(os.path.join(root, "runtime"))
    if (os.path.dirname(release_dir) != runtime_dir or
            not RELEASE_ID_RE.fullmatch(os.path.basename(release_dir))):
        raise InstallError(
            f"buildDir must be <root>/runtime/<release-ID>/dist "
            f"(pack_server.mjs layout), not: {build_dir}")
    if os.path.realpath(server_bin) != os.path.realpath(
            os.path.join(build_dir, "bin.mjs")):
        raise InstallError("serverBin does not resolve to buildDir/bin.mjs")
    # F7: realpath containment against the validated root, plus no symlink at
    # any of the four receipt-named paths.
    for label, path in (("nodePath", node_path), ("installDir", install_dir),
                        ("buildDir", build_dir), ("serverBin", server_bin)):
        if os.path.islink(path):
            raise InstallError(f"{label} must not be a symlink: {path}")
        if not realpath_inside(path, root):
            raise InstallError(f"{label} escapes the server root: {path}")
    if not os.path.isfile(node_path) or not os.access(node_path, os.X_OK):
        raise InstallError("pinned Node executable is missing or not executable")
    # F6: refuse now, not at launchd start time.
    if not os.path.isfile(server_bin):
        raise InstallError(f"packed server entrypoint is missing: {server_bin}")
    for name in REQUIRED_DIST_FILES:
        if not os.path.isfile(os.path.join(build_dir, name)):
            raise InstallError(f"packed runtime is missing {name}")
    if verify_tree:
        recorded = node.get("treeSha256")
        if not isinstance(recorded, str) or not HEX64.fullmatch(recorded):
            raise InstallError("config receipt lacks a valid treeSha256")
        # Round 3 A1: the Node tree verifies through its stat-tripwire cache
        # (full digest on any mismatch); verify_tree == "full" forces the
        # full digest past the cache (doctor --full).
        _verify_node_tree(install_dir, recorded, status_file=status_file,
                          force_full=(verify_tree == "full"), root=root)
        # Panel R1: the packed SERVER tree — the code that actually executes
        # on every boot — is verified against file-digests.json too, not just
        # the Node tree that launches it.
        verify_packed_server(build_dir, force_full=(verify_tree == "full"),
                             status_file=status_file, root=root)
    return node_path, server_bin


def resolve_command(root, command, verify_tree=None, status_file=None):
    if verify_tree is None:
        verify_tree = VERIFY_TREE_AT_RESOLVE
    node, server = runtime_paths(root, verify_tree=verify_tree,
                                 status_file=status_file)
    return node if command == "node" else server


def http_status(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=4) as response:
            return str(response.status)
    except Exception:
        return "unanswered"


# Panel R8: absolute paths for the system tools attribution relies on — a
# PATH-injected fake lsof/ps/launchctl must not be able to fake "ours" or
# "loaded". The MMOS_*_BIN seams exist for the test harness's fake launchd,
# and only there: _gated_seam refuses any of them set outside
# MMOS_TEST_SEAMS=1 (round 3 / FU4).
def _test_seams_on():
    return os.environ.get(TEST_SEAM_FLAG) == "1"


def _gated_seam(name, default):
    if name not in TEST_SEAM_VARS:
        return default
    value = os.environ.get(name)
    if value is None:
        return default
    if not _test_seams_on():
        raise InstallError(
            f"{name} is set but {TEST_SEAM_FLAG} is not 1; test-only "
            f"environment seams are refused outside the test harness")
    return value


def _lsof_bin():
    return _gated_seam("MMOS_LSOF_BIN", "/usr/sbin/lsof")


def _ps_bin():
    return _gated_seam("MMOS_PS_BIN", "/bin/ps")


def _launchctl_bin():
    return _gated_seam("MMOS_LAUNCHCTL_BIN", "/bin/launchctl")


def _listener_pids(port):
    """Pids with a LISTEN socket on port (panel R4)."""
    try:
        probe = subprocess.run([_lsof_bin(), "-tP", f"-iTCP:{port}",
                                "-sTCP:LISTEN"], capture_output=True,
                               text=True, timeout=10)
    except subprocess.SubprocessError:
        return []
    return [int(p) for p in (probe.stdout or "").split() if p.isdigit()]


def _parent_of(pid):
    try:
        probe = subprocess.run([_ps_bin(), "-o", "ppid=", "-p", str(pid)],
                               capture_output=True, text=True, timeout=10)
    except subprocess.SubprocessError:
        return None
    parent = (probe.stdout or "").strip()
    return int(parent) if parent.isdigit() else None


def _pid_descendant_of(child, ancestor, hops=20):
    """True when child's parent chain (bounded) includes ancestor."""
    current, seen = child, 0
    while current and current > 1 and seen < hops:
        if current == ancestor:
            return True
        current = _parent_of(current)
        seen += 1
    return False


def answering_process(port, job_pid):
    """Panel R4: attribute an answering port to this label's job.

    'ours' only when some listener pid is the job pid or one of its
    descendants; a listener that is provably someone else's is 'foreign'.
    Round 3 C: a lookup that identifies NO listener at all (lsof empty, slow
    or failed under load) is UNKNOWN — never 'foreign': on the real switch
    the first doctor called our own listener foreign because lsof returned
    nothing at load ~100. One retry covers the slow case; a persistent empty
    lookup says unknown and names the independent job-specific probe."""
    try:
        job_pid = int(job_pid)
    except (TypeError, ValueError):
        job_pid = None
    listeners = _listener_pids(port)
    if not listeners:
        time.sleep(0.5)  # lsof can be merely slow under load; retry once
        listeners = _listener_pids(port)
    if not listeners:
        return (f"unknown(no listener identified by lsof; job pid "
                f"{job_pid or 'none'} — retry doctor, or probe: lsof -a -p "
                f"{job_pid or '<job pid>'} -tP -iTCP:{port} -sTCP:LISTEN -n)")
    if job_pid and any(p == job_pid or _pid_descendant_of(p, job_pid)
                       for p in listeners):
        return "ours"
    return f"foreign(pid {listeners[0]}, job pid {job_pid or 'none'})"


def doctor(root, label, verify_tree=True, port=None):
    """Only metadata: no access token, environment, cookies or log contents.
    F23/panel R1: both trees are verified against their receipts — the
    pinned Node tree (treeSha256, through node-tree-stat-cache.json) and the
    packed server tree (file-digests.json, through verify-stat-cache.json);
    treeVerified names which. --full forces both full re-hashes past the
    caches (the caches are a same-user-writable performance artifact; the
    receipts remain the anchors). --no-verify-tree skips both. --port N
    probes N when run/port is missing or unreadable. A rollback root (no
    server receipt) is reported as such, not refused."""
    root = validated_root(root)
    try:
        try:
            probe = subprocess.run([_launchctl_bin(), "print",
                                    f"gui/{os.getuid()}/{label}"],
                                   capture_output=True, text=True, timeout=10)
            loaded = probe.returncode == 0
        except subprocess.TimeoutExpired:
            raise InstallError(f"launchctl print timed out for label {label}")
        match = re.search(r"^\s*pid = ([0-9]+)", probe.stdout, re.MULTILINE) if loaded else None
        # Panel atk-7: which plist is the job actually loaded from? A squatted
        # /tmp plist under the same label serves instead of this root's job.
        plist_match = re.search(r"^\s*path = (\S+)", probe.stdout or "",
                                re.MULTILINE) if loaded else None
        job_plist = plist_match.group(1) if plist_match else "unknown"
        # FU2: honor TEAM_SERVER_LAUNCHAGENTS_DIR only as a gated test seam;
        # _gated_seam refuses it when MMOS_TEST_SEAMS is not 1.
        expected_plist = os.path.join(
            _gated_seam("TEAM_SERVER_LAUNCHAGENTS_DIR",
                        os.path.expanduser("~/Library/LaunchAgents")),
            f"{label}.plist")
        port_unknown_hint = ""
        port = str(port) if port else "unknown"
        if not port.isdigit() or not 1024 <= int(port) <= 65535:
            port = "unknown"
        if port == "unknown":
            try:
                with open(os.path.join(root, "run", "port"), encoding="ascii") as stream:
                    candidate = stream.read().strip()
                if re.fullmatch(r"[1-9][0-9]{0,4}", candidate) and 1024 <= int(candidate) <= 65535:
                    port = candidate
            except OSError:
                pass
        if port == "unknown":
            port_unknown_hint = (" (run/port unreadable; pass --port <port> "
                                 "and re-run doctor to probe a port)")
        answering = port if port != "unknown" and http_status(port) == "200" else "unanswered"
        # Panel R4: loaded + HTTP-200 is not health. Attribute the responder:
        # 'ours' only when the listener pid is the job's pid or a descendant.
        if answering != "unanswered":
            attributed = answering_process(port, match.group(1) if match else None)
        else:
            attributed = "none"
        # LOW-13: a printed recovery must be runnable as written, so it
        # carries the root/label/port doctor was invoked against (port only
        # when a port is actually known — else the error names --port), not
        # just the subcommand.
        port_arg = f" --port {port}" if port != "unknown" else ""
        base_install = (f"team_server.sh install --replace --root {root}"
                        f" --label {label}{port_arg}{port_unknown_hint}")
        server_receipt = os.path.join(root, "config", "server-runtime.json")
        if os.path.isfile(server_receipt):
            # Panel R1/LOW-13: packed mode verifies BOTH trees and says
            # exactly what was verified; rollback mode (receipts moved aside
            # per the runbook's 'Going back') reports the operator-named
            # binary instead of dying on the missing receipt — and its
            # recovery line names the command that works on such a root.
            node, server = runtime_paths(root, verify_tree=verify_tree)
            node_row, node_version = node, "v" + VERSION
            build_row = server
            if verify_tree:
                server_files = verify_packed_server(
                    os.path.dirname(server),
                    force_full=(verify_tree == "full"))
                tree_row = "node+server"
                node_exec_check = "skipped-receipt-attested"
            else:
                server_files, tree_row = "not-checked", "not-checked"
                node_exec_check = "not-checked"
            recovery_install = base_install
        else:
            legacy_conf = os.path.join(root, "config", "server-bin")
            try:
                with open(regular_file(legacy_conf), encoding="utf-8") as stream:
                    legacy_bin = stream.read().strip().splitlines()[0]
            except (OSError, ValueError, IndexError) as exc:
                # FU7: name the recovery, not a bare I/O error — the runbook's
                # 'Going back' step 3 is what records a server binary here.
                # (Recovery wording leads: doctor_error lines truncate at
                # 180 chars and the long path in {exc} would eat it.)
                raise InstallError(
                    f"recovery: runbook 'Going back' step 3 names a server "
                    f"binary; rollback root's config/server-bin is unreadable: "
                    f"{exc}") from exc
            if (not legacy_bin or not legacy_bin.startswith("/") or
                    os.path.islink(legacy_bin) or not os.path.isfile(legacy_bin)):
                raise InstallError(
                    f"rollback {legacy_conf} does not name an absolute regular "
                    f"file: {legacy_bin!r}")
            node_row = node_version = node_exec_check = "none(rollback)"
            build_row = legacy_bin
            tree_row, server_files = "none(rollback)", 0
            recovery_install = f"{base_install} --server-bin {legacy_bin}"
        # Never execute the installed binary: attesting provenance is doctor's
        # job, and running the bytes under inspection would let a tampered tree
        # execute attacker code (attack finding 6). The version below is
        # receipt-attested (and the receipt's tree was digest-verified at
        # install); the runbook has the operator run `<node> --version` once
        # by hand when they want a live check.
        migration = "not initialized"
        db = os.path.join(root, "home", "userdata", "statev2.sqlite")
        if os.path.isfile(db):
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                migration = conn.execute("SELECT COALESCE(MAX(migration_id), 'none') "
                                         "FROM effect_sql_migrations").fetchone()[0]
        log = os.path.join(root, "run", "server.log")
        size = os.stat(log).st_size if os.path.isfile(log) else 0
        cap = 52428800
        try:
            cap = int(open(os.path.join(root, "config", "log-cap")).read().strip())
            if not 0 <= cap <= 1024 ** 4:
                raise ValueError
        except (OSError, ValueError):
            cap = 52428800
        access = os.path.join(root, "run", "access.txt")
        age = "missing"
        if os.path.isfile(access):
            info = os.stat(access)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise InstallError("pairing file must be owned by this user and mode 0600")
            age = max(0, int(time.time() - info.st_mtime))
        # Item F: the recorded provider CLI folder. Doctor reports the RECORD
        # (never resolves `claude` in its own shell — that is not the server's
        # PATH); a pre-item-F root shows the re-run-install recovery inline.
        provider_row = "missing (pre-item-F root; re-run install to record it)"
        try:
            with open(os.path.join(root, "config", "provider-cli-dir"),
                      encoding="utf-8") as stream:
                recorded_folder = stream.read().strip().splitlines()[0]
            if recorded_folder.startswith("/") and os.path.isdir(recorded_folder):
                provider_row = recorded_folder
        except (OSError, ValueError, IndexError):
            pass
        rows = [("label", label), ("loaded", "yes" if loaded else "no"),
                ("pid", match.group(1) if match else "none"), ("port", port),
                ("answeringPort", answering), ("answeringProcess", attributed),
                ("jobPlist", job_plist),
                ("nodePath", node_row),
                ("nodeVersion", node_version), ("nodeExecCheck", node_exec_check),
                ("buildPath", build_row), ("treeVerified", tree_row),
                ("serverTreeFiles", server_files),
                ("providerCliFolder", provider_row),
                ("migrationHead", migration), ("serverLogBytes", size),
                ("serverLogCapBytes", cap), ("pairingFileAgeSeconds", age)]
        for key, value in rows:
            print(f"{key}={value}")
        # Attack finding 6: exit 1 without a doctor_error= line sent an
        # operator grepping for the documented token to an empty result on
        # the commonest failure (server down). The two down states name
        # themselves and their recovery.
        if not loaded:
            # LOW-13: the printed recovery must be runnable as written — on a
            # rollback root that means naming config/server-bin's binary.
            print(f"doctor_error=label not loaded — recovery: runbook step 6 "
                  f"({recovery_install}), then re-run doctor")
            return 1
        # Panel atk-7: a job loaded from a foreign plist is a squatted label —
        # even a healthy-looking pid is not this root's server.
        if job_plist != "unknown" and os.path.realpath(job_plist) != os.path.realpath(
                expected_plist):
            print(f"doctor_error=job runs from a foreign plist: {job_plist} "
                  f"(expected {expected_plist}) — a squatted label; recovery: "
                  f"launchctl bootout gui/{os.getuid()}/{label}, remove the "
                  f"foreign plist, re-run runbook step 6")
            return 1
        # Panel R4: an answered port served by a foreign process is not
        # health — the job is crash-looping (or dead) beside an impostor.
        if attributed.startswith("foreign"):
            print(f"doctor_error=port {port} answered by a foreign process "
                  f"({attributed}) — this label's job is not serving; find it: "
                  f"lsof -nP -iTCP:{port} -sTCP:LISTEN")
            return 1
        # Round 3 C: attribution that could not identify ANY listener is
        # unknown, not healthy and not foreign — say so and let the retry (the
        # lookup already retried once) decide.
        if attributed.startswith("unknown"):
            print(f"doctor_error=port {port} answering but attribution "
                  f"UNKNOWN ({attributed}) — re-run doctor once lsof answers; "
                  f"health is unverified until attribution says ours")
            return 1
        if answering != port:
            print(f"doctor_error=port {port} not answering — recovery: runbook "
                  f"step 6 ({recovery_install}), then re-run doctor")
            return 1
        return 0
    except (InstallError, OSError, ValueError, EOFError, tarfile.TarError,
            sqlite3.Error, subprocess.SubprocessError) as exc:
        print(f"doctor_error={str(exc)[:180]}")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "doctor", "resolve", "provider-folder", "record-provider"):
        p = sub.add_parser(name)
        if name in ("provider-folder", "record-provider"):
            # Item F: validate (and optionally record) the provider CLI whose
            # folder install pins as config/provider-cli-dir.
            p.add_argument("--root", required=True)
            p.add_argument("--cli", required=True)
        else:
            p.add_argument("--root", required=True)
        if name == "install":
            p.add_argument("--archive", required=True)
            p.add_argument("--checksum", required=True)
            p.add_argument("--version", default=VERSION)
        elif name in ("doctor",):
            p.add_argument("--label", required=True)
            p.add_argument("--verify-tree", action=argparse.BooleanOptionalAction,
                           default=True,
                           help="verify both trees against their receipts "
                                "(default: yes; cached stat triples where valid)")
            p.add_argument("--full", action="store_true",
                           help="force the FULL digest of both trees, past the "
                                "stat caches (FU3: the caches are a "
                                "same-user-writable performance artifact)")
            p.add_argument("--port", default=None,
                           help="probe this port when run/port is missing or "
                                "unreadable (FU7)")
        elif name == "resolve":
            p.add_argument("--command", choices=("node", "serve"), default="serve")
            p.add_argument("--verify-tree", action=argparse.BooleanOptionalAction,
                           default=None,
                           help="override whether resolve recomputes the tree digest")
            p.add_argument("--status-file", default=None,
                           help="append stage= lines while verifying (round 3 B: "
                                "a slow boot must be observable)")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install_node(args.root, args.archive, args.checksum, args.version)
        elif args.command == "doctor":
            return doctor(args.root, args.label,
                          verify_tree=("full" if args.full else args.verify_tree),
                          port=args.port)
        elif args.command == "provider-folder":
            # Item F: validate only; print the folder install would record.
            print(validated_provider_cli(args.cli, root=validated_root(args.root)))
        elif args.command == "record-provider":
            # Item F: validate and record (config/provider-cli-dir, 0600).
            print(record_provider_cli(args.root, args.cli))
        else:
            # F8: resolve applies the same root validation as install/doctor.
            print(resolve_command(validated_root(args.root), args.command,
                                  verify_tree=args.verify_tree,
                                  status_file=args.status_file))
    except (InstallError, OSError, ValueError, EOFError, tarfile.TarError) as exc:
        print(f"team_runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
