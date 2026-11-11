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
# Measured 2026-11-11 on this M2 Studio over the real 199 MB / ~4.7k-entry
# pinned Node tree: full schema-2 digest 1.22 s cold, 0.33-0.38 s warm. That
# is fast enough to recompute at EVERY server start, so resolve (the runner's
# pre-execve gate) verifies the tree by default; doctor verifies too.
VERIFY_TREE_AT_RESOLVE = True


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


def tree_sha256(directory):
    """Deterministic digest of a published tree, excluding its own receipt
    (which embeds this digest and so cannot cover itself). Schema 2: every
    entry contributes — directories (including empty ones) contribute
    path+mode; symlinked directories and file symlinks contribute
    path+target; regular files contribute path+mode+size+bytes. Any entry
    that is not a regular file, a directory or a symlink (a FIFO, socket or
    device) is refused WITHOUT being opened, so a planted FIFO cannot hang
    the digest. Used to verify, on a retry and in doctor, that an existing
    destination is still the tree this exact archive produced."""
    digest = hashlib.sha256()

    def feed(relative, kind, extra):
        digest.update(relative.encode("utf-8") + b"\0" + kind.encode("ascii") +
                      extra.encode("utf-8") + b"\0")

    for current, dirnames, filenames in os.walk(directory):
        dirnames.sort()
        for name in dirnames:
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, directory)
            if os.path.islink(absolute):
                # os.walk does not descend into symlinked directories
                # (followlinks=False), but they still must contribute.
                feed(relative, "l", os.readlink(absolute))
            else:
                info = os.lstat(absolute)
                feed(relative, "d", oct(stat.S_IMODE(info.st_mode) & 0o7777))
        for name in sorted(filenames):
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, directory)
            if relative == "INSTALL_RECEIPT.json":
                continue
            info = os.lstat(absolute)
            if stat.S_ISLNK(info.st_mode):
                feed(relative, "l", os.readlink(absolute))
            elif not stat.S_ISREG(info.st_mode):
                # FIFO, socket, device: refused before any open() can block.
                raise InstallError(f"non-regular tree entry refused: {relative}")
            else:
                feed(relative, "f", f"{stat.S_IMODE(info.st_mode) & 0o7777:o}:{info.st_size}")
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
    for temp in (os.path.join(runtime_dir, "install-receipt.json.tmp"),
                 os.path.join(config_dir, "node-runtime.json.tmp"),
                 os.path.join(config_dir, "python3-path.tmp")):
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


def runtime_paths(root, verify_tree=True):
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
        if tree_sha256(install_dir) != recorded:
            raise InstallError(
                "pinned Node tree no longer matches its receipt (treeSha256 "
                "mismatch); reinstall the runtime")
    return node_path, server_bin


def resolve_command(root, command, verify_tree=None):
    if verify_tree is None:
        verify_tree = VERIFY_TREE_AT_RESOLVE
    node, server = runtime_paths(root, verify_tree=verify_tree)
    return node if command == "node" else server


def http_status(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=4) as response:
            return str(response.status)
    except Exception:
        return "unanswered"


def doctor(root, label, verify_tree=True):
    """Only metadata: no access token, environment, cookies or log contents.
    F23: the pinned-Node tree digest is recomputed against the receipt
    (measured ~0.3-1.2 s on the real tree); --no-verify-tree skips it."""
    root = validated_root(root)
    try:
        try:
            probe = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                                   capture_output=True, text=True, timeout=10)
            loaded = probe.returncode == 0
        except subprocess.TimeoutExpired:
            raise InstallError(f"launchctl print timed out for label {label}")
        match = re.search(r"^\s*pid = ([0-9]+)", probe.stdout, re.MULTILINE) if loaded else None
        port = "unknown"
        try:
            with open(os.path.join(root, "run", "port"), encoding="ascii") as stream:
                candidate = stream.read().strip()
            if re.fullmatch(r"[1-9][0-9]{0,4}", candidate) and 1024 <= int(candidate) <= 65535:
                port = candidate
        except OSError:
            pass
        answering = port if port != "unknown" and http_status(port) == "200" else "unanswered"
        node, server = runtime_paths(root, verify_tree=verify_tree)
        # Never execute the installed binary: attesting provenance is doctor's
        # job, and running the bytes under inspection would let a tampered tree
        # execute attacker code (attack finding 6). The version below is
        # receipt-attested (and the receipt's tree was digest-verified at
        # install); the runbook has the operator run `<node> --version` once
        # by hand when they want a live check.
        node_version = "v" + VERSION
        node_exec_check = "skipped-receipt-attested"
        tree_line = "treeVerified=" + ("yes" if verify_tree else "not-checked")
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
        rows = [("label", label), ("loaded", "yes" if loaded else "no"),
                ("pid", match.group(1) if match else "none"), ("port", port),
                ("answeringPort", answering), ("nodePath", node),
                ("nodeVersion", node_version), ("nodeExecCheck", node_exec_check),
                ("buildPath", server), ("treeVerified", tree_line.split("=")[1]),
                ("migrationHead", migration), ("serverLogBytes", size),
                ("serverLogCapBytes", cap), ("pairingFileAgeSeconds", age)]
        for key, value in rows:
            print(f"{key}={value}")
        # Attack finding 6: exit 1 without a doctor_error= line sent an
        # operator grepping for the documented token to an empty result on
        # the commonest failure (server down). The two down states name
        # themselves and their recovery.
        if not loaded:
            print("doctor_error=label not loaded — recovery: runbook step 6 "
                  "(team_server.sh install --replace), then re-run doctor")
            return 1
        if answering != port:
            print(f"doctor_error=port {port} not answering — recovery: runbook "
                  f"step 6 (team_server.sh install --replace), then re-run doctor")
            return 1
        return 0
    except (InstallError, OSError, ValueError, EOFError, tarfile.TarError,
            sqlite3.Error, subprocess.SubprocessError) as exc:
        print(f"doctor_error={str(exc)[:180]}")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "doctor", "resolve"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True)
        if name == "install":
            p.add_argument("--archive", required=True)
            p.add_argument("--checksum", required=True)
            p.add_argument("--version", default=VERSION)
        elif name == "doctor":
            p.add_argument("--label", required=True)
            p.add_argument("--verify-tree", action=argparse.BooleanOptionalAction,
                           default=True,
                           help="recompute the full pinned-Node tree digest "
                                "against the receipt (default: yes)")
        else:
            p.add_argument("--command", choices=("node", "serve"), default="serve")
            p.add_argument("--verify-tree", action=argparse.BooleanOptionalAction,
                           default=None,
                           help="override whether resolve recomputes the tree digest")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install_node(args.root, args.archive, args.checksum, args.version)
        elif args.command == "doctor":
            return doctor(args.root, args.label, verify_tree=args.verify_tree)
        else:
            # F8: resolve applies the same root validation as install/doctor.
            print(resolve_command(validated_root(args.root), args.command,
                                  verify_tree=args.verify_tree))
    except (InstallError, OSError, ValueError, EOFError, tarfile.TarError) as exc:
        print(f"team_runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
