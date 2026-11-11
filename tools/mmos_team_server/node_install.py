#!/usr/bin/env python3
"""Install the pinned official Node.js archive and inspect the packed runtime.

Downloaded executables are never run during verification or extraction. The
archive is first copied into a private staging directory; that one private
copy is hashed, member-checked and extracted from a single open file, so the
bytes that reach the destination are exactly the bytes that were verified.
The install receipt travels inside the staged tree, and one atomic rename
publishes tree and receipt together. The caller must create the private
server root; this tool never chmods a pre-existing root into private.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
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
BASE_ENV = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}


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
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


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


def validated_root(root, create=False):
    """F4/F8: reject a symlinked root before any realpath, then require the
    resolved root to stay private, owned, and outside the Chairman's ~/.t3.
    A missing root may be created 0700; an existing loose root is refused,
    never silently tightened (that tightening is the operator's act)."""
    root = os.path.abspath(os.path.expanduser(root))
    if create and not os.path.lexists(root):
        os.makedirs(root, mode=0o700)
    private_dir(root, create=False)
    root = os.path.realpath(root)
    private_dir(root)
    real_t3 = os.path.realpath(os.path.expanduser("~/.t3"))
    if root == real_t3 or root.startswith(real_t3 + os.sep):
        raise InstallError("the Chairman's ~/.t3 is out of scope")
    return root


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
    prefix = f"node-v{VERSION}-darwin-arm64"
    destination = os.path.join(runtime_dir, prefix)
    if any(os.path.basename(p).startswith(".node-install-")
           for p in os.listdir(staging_parent)):
        raise InstallError("half-finished staging installation found; inspect it before retrying")
    receipt = {
        "schemaVersion": 1,
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
    payload = json.dumps(receipt, indent=2) + "\n"
    # A destination whose in-tree receipt already matches this exact payload is
    # an interrupted-after-publish install: repair the two activation markers,
    # never re-extract over it. Anything else refuses.
    if os.path.lexists(destination):
        if os.path.islink(destination):
            raise InstallError(f"symlinked destination refused: {destination}")
        in_tree = os.path.join(destination, "INSTALL_RECEIPT.json")
        try:
            regular_file(in_tree)
            with open(in_tree, encoding="utf-8") as stream:
                if stream.read() != payload:
                    raise InstallError
        except (InstallError, OSError):
            raise InstallError(
                "destination already exists without this exact receipt; "
                "inspect and move it away before retrying")
        idempotent_receipt(os.path.join(runtime_dir, "install-receipt.json"), payload)
        idempotent_receipt(os.path.join(config_dir, "node-runtime.json"), payload)
        print(f"NODE_INSTALLED version=v{VERSION} node={receipt['nodePath']} "
              f"sha256={OFFICIAL_SHA256} (activation repaired)")
        return receipt
    stage = tempfile.mkdtemp(prefix=".node-install-", dir=staging_parent)
    try:
        # F5: copy the archive into private staging, then hash, member-check
        # and extract that one copy from one open file. The bytes extracted
        # are bound to the bytes verified.
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
                # 'data' is a second, independent safety filter; it also
                # blocks archive-driven ownership changes.
                tf.extractall(stage, members=members, filter="data")
        os.unlink(private_copy)
        extracted = os.path.join(stage, prefix)
        executable = os.path.join(extracted, "bin", "node")
        info = os.lstat(executable)
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o100:
            raise InstallError("extracted Node executable is missing")
        # F1: the receipt travels inside the staged tree; one atomic rename
        # publishes tree and receipt together. No bytes are published without
        # their receipt, and no receipt is written after publication.
        private_write(os.path.join(extracted, "INSTALL_RECEIPT.json"), payload)
        os.rename(extracted, destination)
        # Activation markers live outside the tree and are repairable on a
        # retry via the matching-receipt branch above.
        idempotent_receipt(os.path.join(runtime_dir, "install-receipt.json"), payload)
        idempotent_receipt(os.path.join(config_dir, "node-runtime.json"), payload)
        print(f"NODE_INSTALLED version=v{VERSION} node={receipt['nodePath']} "
              f"sha256={OFFICIAL_SHA256}")
        return receipt
    finally:
        if os.path.isdir(stage) and not os.path.islink(stage):
            shutil.rmtree(stage)


def load_receipt(path):
    with open(regular_file(path), encoding="utf-8") as stream:
        receipt = json.load(stream)
    if receipt.get("schemaVersion") != 1:
        raise InstallError("unsupported runtime receipt schema")
    return receipt


def runtime_paths(root):
    root = validated_root(root)
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
    return node_path, server_bin


def resolve_command(root, command):
    node, server = runtime_paths(root)
    return node if command == "node" else server


def http_status(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=4) as response:
            return str(response.status)
    except Exception:
        return "unanswered"


def doctor(root, label):
    """Only metadata: no access token, environment, cookies or log contents."""
    root = validated_root(root)
    try:
        probe = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                               capture_output=True, text=True, timeout=10)
        loaded = probe.returncode == 0
        match = re.search(r"^\s*pid = ([0-9]+)", probe.stdout, re.MULTILINE) if loaded else None
        port = "unknown"
        try:
            with open(os.path.join(root, "run", "port"), encoding="ascii") as stream:
                candidate = stream.read().strip()
            if candidate.isdigit() and 1 <= int(candidate) <= 65535:
                port = candidate
        except OSError:
            pass
        answering = port if port != "unknown" and http_status(port) == "200" else "unanswered"
        node, server = runtime_paths(root)
        version = subprocess.run([node, "--version"], cwd="/tmp", capture_output=True,
                                 text=True, timeout=10, env=BASE_ENV)
        if version.returncode or version.stdout.strip() != "v" + VERSION:
            raise InstallError("installed Node version does not match its receipt")
        migration = "not initialized"
        db = os.path.join(root, "home", "userdata", "statev2.sqlite")
        if os.path.isfile(db):
            import sqlite3
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
                ("nodeVersion", "v" + VERSION), ("buildPath", server),
                ("migrationHead", migration), ("serverLogBytes", size),
                ("serverLogCapBytes", cap), ("pairingFileAgeSeconds", age)]
        for key, value in rows:
            print(f"{key}={value}")
        return 0 if loaded and answering == port else 1
    except (InstallError, OSError, ValueError) as exc:
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
        else:
            p.add_argument("--command", choices=("node", "serve"), default="serve")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install_node(args.root, args.archive, args.checksum, args.version)
        elif args.command == "doctor":
            return doctor(args.root, args.label)
        else:
            # F8: resolve applies the same root validation as install/doctor.
            print(resolve_command(validated_root(args.root), args.command))
    except (InstallError, OSError, ValueError) as exc:
        print(f"team_runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
