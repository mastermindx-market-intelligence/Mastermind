#!/usr/bin/env python3
"""Install the pinned official Node.js archive and inspect the packed runtime.

Downloaded executables are never run during extraction or activation. The
archive digest, extraction paths, file ownership and staging layout are checked
before any archive content is made active. The caller must create the private
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
import urllib.request

VERSION = "24.22.2"
ARCHIVE = f"node-v{VERSION}-darwin-arm64.tar.gz"
OFFICIAL_SHA256 = "aa9549349e47dffaa42dcf95d6e06ade8c4bdafc980979883b88767670df385a"
NODE_REQUIREMENT = "^22.16 || ^23.11 || >=24.10"
BUILD_REQUIREMENT = "^22.18.0 || ^24.11.0 || >=26.0.0"


class InstallError(Exception):
    """The tested, operator-actionable refusal."""


def _inside(path, root):
    return os.path.relpath(path, root) == "." or not os.path.relpath(
        path, root).startswith(".." + os.sep) and os.path.relpath(
            path, root) != ".."


def private_dir(path, create=False):
    """Check a directory itself, without following a directory symlink."""
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
    if info.st_mode & 0o077:
        raise InstallError(f"directory must be mode 0700: {path}")
    return os.path.realpath(path)


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
                if not re.fullmatch("[0-9a-f]{64}", digest):
                    raise InstallError("invalid checksum file")
                found.append(digest)
    if len(found) != 1:
        raise InstallError("checksum file lacks one exact archive entry")
    if found[0] != OFFICIAL_SHA256:
        raise InstallError("checksum record does not match the pinned official Node release")
    return found[0]


def checked_members(tf, prefix):
    """Validate tar metadata from the exact opened file later extracted."""
    if tf is None:
        raise InstallError("an opened tar archive is required")
    members = []
    bytes_total = 0
    for member in tf:
            name = member.name.removesuffix("/")
            parts = name.split("/")
            if (not name or name.startswith(("/", "\\")) or parts[0] != prefix or
                    any(p in ("", ".", "..") for p in parts)):
                raise InstallError(f"unsafe archive member: {name!r}")
        if member.isreg():
                bytes_total += member.size
            elif not member.isdir() and not member.issym():
                raise InstallError("special and hardlink archive members refused")
            if member.mode & 0o7000:
                raise InstallError("privileged archive mode refused")
                # The official archive has npm, npx and corepack relative links.
            # Constrain their resolved target to the archive's own top-level.
            target = os.path.normpath(os.path.join(
                os.path.dirname(name), member.linkname))
            if (not member.linkname or os.path.isabs(member.linkname) or
                    not _inside(target, prefix)):
                raise InstallError("escaping archive link refused")
                # Constrain their resolved target to the archive's own top-level.
                target = os.path.normpath(os.path.join(
                    os.path.dirname(name), member.linkname))
                if (not member.linkname or os.path.isabs(member.linkname) or
                        not _inside(target, prefix)):
                    raise InstallError("escaping archive link refused")
            members.append(member)
            if len(members) > 30000 or bytes_total > 2 * 1024 ** 3:
                raise InstallError("archive member/byte budget exceeded")
    if not members:
        raise InstallError("empty archive")
    return members, prefix


def new_private_file(path, payload):
    if os.path.lexists(path) or os.path.lexists(path + ".tmp"):
        raise InstallError(f"install receipt conflict: {path}")
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
        os.replace(path + ".tmp", path)
    finally:
        if os.path.lexists(path + ".tmp"):
            os.unlink(path + ".tmp")


def install_node(root, archive, checksum, version=VERSION):
    if version != VERSION:
        raise InstallError(f"Node version must be exactly {VERSION}")
    root = private_dir(os.path.abspath(os.path.expanduser(root)))
    real_t3 = os.path.realpath(os.path.expanduser("~/.t3"))
    if _inside(root, real_t3):
        raise InstallError("the Chairman's ~/.t3 is out of scope")
    archive = os.path.abspath(os.path.expanduser(archive))
    checksum = os.path.abspath(os.path.expanduser(checksum))
    if os.path.basename(archive) != ARCHIVE:
        raise InstallError(f"archive must be named {ARCHIVE}")
    expected = official_digest(checksum, ARCHIVE)
    actual = sha256(archive)
    if actual != expected:
        raise InstallError("tampered archive: SHA-256 mismatch")
    runtime = private_dir(os.path.join(root, "runtime"), create=True)
    staging = private_dir(os.path.join(runtime, "staging"), create=True)
    config = private_dir(os.path.join(root, "config"), create=True)
    prefix = f"node-v{VERSION}-darwin-arm64"
    destination = os.path.join(runtime, prefix)
    if os.path.lexists(destination):
        raise InstallError("destination already exists; refusing to overwrite a partial installation")
    if os.listdir(staging):
        raise InstallError("half-finished staging installation found; inspect and move it away first")
    members, prefix = checked_members(archive)
    stage = tempfile.mkdtemp(prefix=".node-install-", dir=staging)
    extracted = os.path.join(stage, prefix)
    try:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(stage, members=members, filter="data")
        executable = os.path.join(extracted, "bin", "node")
        info = os.lstat(executable)
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o100:
            raise InstallError("extracted Node executable is missing")
        receipt = {
            "schemaVersion": 1,
            "kind": "official-nodejs-install",
            "version": "v" + VERSION,
            "architecture": "arm64",
            "platform": "darwin",
            "nodePath": os.path.join(destination, "bin", "node"),
            "installDir": destination,
            "archiveSha256": actual,
            "checksumRecord": f"https://nodejs.org/dist/v{VERSION}/SHASUMS256.txt",
            "archiveUrl": f"https://nodejs.org/dist/v{VERSION}/{ARCHIVE}",
            "supportedBy": {"server": NODE_REQUIREMENT, "vitePlus": BUILD_REQUIREMENT},
            "sourceBuiltWith": "Homebrew Node v26.5.0; pinned runtime is separate",
        }
        payload = json.dumps(receipt, indent=2) + "\n"
        new_private_file(os.path.join(extracted, "INSTALL_RECEIPT.json"), payload)
        # Publish all bytes and the in-tree receipt in a single rename.
        os.rename(extracted, destination)
        new_private_file(os.path.join(runtime, "install-receipt.json"), payload)
        # Until this config is durable, the runner never considers it installed.
        new_private_file(os.path.join(config, "node-runtime.json"), payload)
        print(f"NODE_INSTALLED version=v{VERSION} node={receipt['nodePath']} sha256={actual}")
        return receipt
    finally:
        shutil.rmtree(stage)


def load_receipt(path):
    with open(regular_file(path), encoding="utf-8") as stream:
        receipt = json.load(stream)
    if receipt.get("schemaVersion") != 1:
        raise InstallError("unsupported runtime receipt")
    return receipt


def runtime_paths(root):
    root = os.path.realpath(root)
    node = load_receipt(os.path.join(root, "config", "node-runtime.json"))
    server = load_receipt(os.path.join(root, "config", "server-runtime.json"))
    if (node.get("version") != "v" + VERSION or
            node.get("archiveSha256") != OFFICIAL_SHA256):
        raise InstallError("unrecognized or incomplete Node install receipt")
    executable = node.get("nodePath", "")
    if (os.path.dirname(executable) != os.path.join(node.get("installDir", ""), "bin") or
            not _inside(executable, root) or os.path.islink(executable) or
            not os.path.isfile(executable) or not os.access(executable, os.X_OK)):
        raise InstallError("Node path is missing, unsafe, or outside the server root")
    built = server.get("buildDir", "")
    entry = server.get("serverBin", "")
    if (entry != os.path.join(built, "bin.mjs") or
            os.path.basename(built) != "dist" or not _inside(built, root) or
            os.path.islink(built)):
        raise InstallError("server runtime receipt does not name a safe local dist")
    for name in ("bin.mjs", "claude-history-worker.mjs", "client/index.html",
                 "node_modules/playwright-core/package.json",
                 "node_modules/node-pty/package.json"):
        if not os.path.isfile(os.path.join(built, name)):
            raise InstallError(f"packed runtime is missing {name}; incomplete build refused")
    return executable, entry


def doctor(root, label):
    """Only metadata: no access token, environment, cookies or log contents."""
    root = os.path.abspath(os.path.expanduser(root))
    private_dir(root)
    root = os.path.realpath(root)
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
        answering = "unanswered"
        if port != "unknown":
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=4) as response:
                    if response.status == 200:
                        answering = port
            except Exception:
                pass
        node, built = runtime_paths(root)
        version = subprocess.run([node, "--version"], cwd="/tmp", capture_output=True,
                                 text=True, timeout=10,
                                 env={"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"]})
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
            pass
        access = os.path.join(root, "run", "access.txt")
        age = "missing"
        if os.path.isfile(access):
            info = os.stat(access)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise InstallError("pairing file must be owned by this user and mode 0600")
            age = max(0, int(time.time() - info.st_mtime))
        rows = [("label", label), ("loaded", "yes" if loaded else "no"),
                ("pid", match.group(1) if match else "none"), ("port", port),
                ("answeringPort", answering), ("nodePath", node), ("nodeVersion", "v" + VERSION),
                ("buildPath", built), ("migrationHead", migration), ("serverLogBytes", size),
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
            print(runtime_paths(os.path.realpath(args.root))[
                0 if args.command == "node" else 1])
    except (InstallError, OSError, ValueError) as exc:
        print(f"team_runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
