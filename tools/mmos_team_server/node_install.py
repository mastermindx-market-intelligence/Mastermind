#!/usr/bin/env python3
"""Verify and install one official Node archive for an isolated team server.

No interpreter from the extracted archive is used during verification. The
archive and SHASUMS256 record are opened as relative files, never passed to a
shell. Activation is an atomic rename inside a private, current-user-owned
server root; a missing/partial installation is never repaired by overwriting
an existing destination.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time

VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
ALLOWED_LINKS = {
    "npm": "../lib/node_modules/npm/bin/npm-cli.js",
    "npx": "../lib/node_modules/npm/bin/npx-cli.js",
    "corepack": "../lib/node_modules/corepack/dist/corepack.js",
}
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
    "HOME": os.path.expanduser("~"),
}


class InstallError(Exception):
    pass


def private_dir(path, create=False):
    """A real directory, not a symlink, private and owned by this user."""
    if os.path.lexists(path) and os.path.islink(path):
        raise InstallError(f"symlinked directory refused: {path}")
    if create:
        os.makedirs(path, mode=0o700, exist_ok=True)
        if os.stat(path).st_uid == os.getuid():
            os.chmod(path, 0o700)
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise InstallError(f"missing directory: {path}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise InstallError(f"not a directory: {path}")
    if info.st_uid != os.getuid():
        raise InstallError(f"directory belongs to another user: {path}")
    if stat.S_IMODE(info.st_mode) & 0o077:
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
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise InstallError(f"file must not be writable by group or other: {path}")
    return path


def sha256(path):
    digest = hashlib.sha256()
    with open(regular_file(path), "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_official_digest(checksum_path, archive_name):
    """Accept only one well-formed GNU-format entry for this exact archive."""
    matches = []
    with open(regular_file(checksum_path), encoding="utf-8") as stream:
        for line in stream:
            line = line.rstrip("\n")
            parts = line.split("  ")
            if len(parts) == 2 and parts[1] == archive_name:
                if not HEX64_RE.fullmatch(parts[0]):
                    raise InstallError("invalid checksum digest for archive")
                matches.append(parts[0])
    if len(matches) != 1:
        raise InstallError("checksum file must contain exactly one entry for archive")
    return matches[0]


def checked_members(archive, version, platform="darwin", arch="arm64"):
    """Bound extraction and allow only Node's own regular files and links.

    Node's official npm/npx/corepack entries are legitimate relative links;
    every target is checked, rather than rejecting the official release.
    """
    prefix = f"node-v{version}-{platform}-{arch}"
    members = []
    total_bytes = 0
    with tarfile.open(regular_file(archive), "r:gz") as bundle:
        for member in bundle:
            name = member.name.removesuffix("/")
            parts = name.split("/")
            if (not name or name.startswith(("/" , "\\")) or
                    parts[0] != prefix or any(p in ("", ".", "..") for p in parts)):
                raise InstallError(f"unsafe archive member: {name[:100]!r}")
            if member.isdir() or member.isreg():
                if member.mode & 0o7000:
                    raise InstallError("privileged archive mode refused")
                if member.isreg():
                    total_bytes += member.size
            elif member.issym():
                # Ensure every symlink has a relative target which stays below
                # the archive's top-level directory after lexical resolution.
                target = member.linkname
                if (os.path.isabs(target) or target.startswith("\\") or
                        not target or "\x00" in target):
                    raise InstallError(f"unsafe archive link: {name!r}")
                destination = os.path.normpath(os.path.join(
                    os.path.dirname(name), target))
                if destination != prefix and not destination.startswith(prefix + "/"):
                    raise InstallError(f"escaping archive link: {name!r}")
                if parts == [prefix, "bin", parts[-1]] and parts[-1] in ALLOWED_LINKS:
                    if target != ALLOWED_LINKS[parts[-1]]:
                        raise InstallError("unexpected npm-family link target")
            else:
                raise InstallError("hardlinks, devices and special archive members refused")
            members.append(member)
            if len(members) > 30000 or total_bytes > 2 * 1024**3:
                raise InstallError("archive member count or byte budget exceeded")
    if not members:
        raise InstallError("empty archive")
    return members, prefix


def private_write(path, payload, mode=0o600):
    temp = path + ".tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(fd)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)
    os.replace(temp, path)


def atomic_receipt(path, payload):
    # Only replace an equal, current-user-owned receipt on an idempotent rerun.
    if os.path.lexists(path):
        if os.path.islink(path):
            raise InstallError(f"symlinked receipt refused: {path}")
        regular_file(path)
        try:
            if open(path, encoding="utf-8").read() == payload:
                return
        except OSError as exc:
            raise InstallError(f"cannot read receipt: {path}") from exc
        raise InstallError(f"conflicting existing receipt: {path}")
    private_write(path, payload)


def install_node(root, archive, checksum, version):
    if not VERSION_RE.fullmatch(version):
        raise InstallError("an exact Node version is required")
    root = os.path.realpath(os.path.expanduser(root))
    private_dir(root)
    private_t3 = os.path.realpath(os.path.expanduser("~/.t3"))
    if root == private_t3 or root.startswith(private_t3 + os.sep):
        raise InstallError("the Chairman's ~/.t3 is out of scope")
    base = private_dir(os.path.join(root, "runtime"), create=True)
    staging_parent = private_dir(os.path.join(base, "staging"), create=True)
    archive = regular_file(os.path.abspath(os.path.expanduser(archive)))
    checksum = regular_file(os.path.abspath(os.path.expanduser(checksum)))
    archive_name = f"node-v{version}-darwin-arm64.tar.gz"
    if os.path.basename(archive) != archive_name:
        raise InstallError(f"archive filename must be {archive_name}")
    expected = load_official_digest(checksum, archive_name)
    actual = sha256(archive)
    if actual != expected:
        raise InstallError("archive checksum does not match the official record")
    destination = os.path.join(base, f"node-v{version}-darwin-arm64")
    receipt_path = os.path.join(base, "install-receipt.json")
    config_dir = private_dir(os.path.join(root, "config"), create=True)
    if os.path.lexists(destination) or os.path.lexists(receipt_path):
        raise InstallError("destination or receipt already exists; refusing to overwrite an installation")
    if any(os.path.basename(p).startswith(".node-install-")
           for p in os.listdir(staging_parent)):
        raise InstallError("half-finished staging installation found; inspect it before retrying")
    members, prefix = checked_members(archive, version)
    stage = tempfile.mkdtemp(prefix=".node-install-", dir=staging_parent)
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            # 'data' applies a separate safety filter after the explicit member
            # checks above. It also prevents archive UID/GID ownership changes.
            bundle.extractall(stage, members=members, filter="data")
        node = os.path.join(stage, prefix, "bin", "node")
        info = os.lstat(node)
        if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o100:
            raise InstallError("extracted Node executable is missing")
        if os.stat(stage).st_uid != os.getuid():
            raise InstallError("extracted staging ownership changed")
        if any(os.path.basename(p).startswith(".node-install-")
               for p in os.listdir(base)):
            raise InstallError("unexpected staged path")
        os.rename(os.path.join(stage, prefix), destination)
        receipt = {
            "schemaVersion": 1,
            "kind": "official-nodejs-install",
            "version": f"v{version}",
            "architecture": "arm64",
            "platform": "darwin",
            "nodePath": os.path.join(destination, "bin", "node"),
            "installDir": destination,
            "archiveSha256": actual,
            "officialChecksumRecord": {
                "name": archive_name,
                "source": "https://nodejs.org/dist/v%s/SHASUMS256.txt" % version,
                "sha256": expected,
            },
            "archiveSource": {
                "name": archive_name,
                "url": "https://nodejs.org/dist/v%s/%s" % (version, archive_name),
            },
            "supportedBy": {
                "server": "^22.16 || ^23.11 || >=24.10",
                "vitePlus": "^22.18.0 || ^24.11.0 || >=26.0.0",
            },
            "verification": "exact SHA-256 match, safe archive traversal, no overwrite",
        }
        payload = json.dumps(receipt, indent=2) + "\n"
        atomic_receipt(os.path.join(destination, "INSTALL_RECEIPT.json"), payload)
        atomic_receipt(receipt_path, payload)
        private_write(os.path.join(config_dir, "node-runtime.json"), payload)
        print("NODE_INSTALLED version=v%s node=%s sha256=%s" %
              (version, receipt["nodePath"], actual))
        return receipt
    except Exception:
        # Preserve the partial destination and receipts for diagnosis; never
        # delete or overwrite evidence of an interrupted installation.
        raise
    finally:
        if os.path.isdir(stage) and not os.path.islink(stage):
            shutil.rmtree(stage)


def require_exact_one(value):
    if not isinstance(value, str) or not value:
        raise InstallError("missing runtime path")


def load_receipt(path):
    if not os.path.lexists(path):
        raise InstallError("runtime has not been installed")
    regular_file(path)
    with open(path, encoding="utf-8") as stream:
        receipt = json.load(stream)
    if receipt.get("schemaVersion") != 1:
        raise InstallError("unsupported runtime receipt")
    return receipt


def runtime_paths(root):
    node_receipt = load_receipt(os.path.join(root, "config", "node-runtime.json"))
    server_receipt = load_receipt(os.path.join(root, "config", "server-runtime.json"))
    for key in ("nodePath", "installDir"):
        require_exact_one(node_receipt.get(key))
    require_exact_one(server_receipt.get("serverBin"))
    for key in ("nodePath", "installDir"):
        path = node_receipt[key]
        rel = os.path.relpath(os.path.abspath(path), root)
        if rel.startswith(".." + os.sep) or os.path.isabs(rel) or os.path.islink(path):
            raise InstallError(f"receipt path escapes server root or is a symlink: {key}")
    if (not os.path.isfile(node_receipt["nodePath"]) or
            not os.access(node_receipt["nodePath"], os.X_OK)):
        raise InstallError("Node receipt does not point to an executable")
    build = os.path.dirname(server_receipt["serverBin"])
    if (os.path.basename(build) != "dist" or
            os.path.relpath(build, root).startswith(".." + os.sep)):
        raise InstallError("server receipt must name a built dist directory under root")
    for relative in ("bin.mjs", "claude-history-worker.mjs", "client/index.html",
                     "node_modules/playwright-core/package.json",
                     "node_modules/node-pty/package.json"):
        if not os.path.isfile(os.path.join(build, relative)):
            raise InstallError(f"packed runtime is missing {relative}")
    return node_receipt["nodePath"], server_receipt["serverBin"]


def resolve_command(root, command):
    # Used by the runner in a deliberately sparse launchd environment.
    node, server = runtime_paths(root)
    if command == "node":
        return node
    return server


def http_status(port):
    import urllib.request
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=4) as response:
            return str(response.status)
    except Exception:
        return "unanswered"


def doctor(root, label):
    """Print the server's health metadata, never any credential contents."""
    root = os.path.realpath(os.path.expanduser(root))
    private_dir(root)
    try:
        details = {}
        probe = __import__("subprocess").run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True, text=True, timeout=10)
        loaded = probe.returncode == 0
        pid = "none"
        if loaded:
            match = re.search(r"^\s*pid = ([0-9]+)", probe.stdout, re.MULTILINE)
            if match:
                pid = match.group(1)
        port = "unknown"
        try:
            with open(os.path.join(root, "run", "port"), encoding="ascii") as stream:
                port = stream.read().strip()
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                port = "invalid"
        except OSError:
            pass
        details.update(label=label, loaded="yes" if loaded else "no", pid=pid,
                       port=port, answeringPort=port if http_status(port) == "200"
                       else "unanswered")
        node, server = runtime_paths(root)
        probe = __import__("subprocess").run([node, "--version"],
                                              capture_output=True, text=True, timeout=10,
                                              cwd="/tmp", env=BASE_ENV)
        if probe.returncode != 0 or not VERSION_RE.fullmatch(probe.stdout.strip().lstrip("v")):
            raise InstallError("installed Node failed its version check")
        details.update(nodePath=node, nodeVersion=probe.stdout.strip(), buildPath=server)
        database = os.path.join(root, "home", "userdata", "statev2.sqlite")
        migration = "not initialized"
        if os.path.isfile(database):
            import sqlite3
            conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                migration = conn.execute(
                    "SELECT COALESCE(MAX(migration_id), 'none') "
                    "FROM effect_sql_migrations").fetchone()[0]
            finally:
                conn.close()
        details["migrationHead"] = migration
        log = os.path.join(root, "run", "server.log")
        size = os.stat(log).st_size if os.path.isfile(log) else 0
        cap = 52428800
        try:
            cap = int(open(os.path.join(root, "config", "log-cap")).read().strip())
            if cap < 0:
                raise ValueError
        except (OSError, ValueError):
            cap = 52428800
        details["serverLogBytes"] = size
        details["serverLogCapBytes"] = cap
        access = os.path.join(root, "run", "access.txt")
        if os.path.isfile(access):
            details["pairingFileAgeSeconds"] = max(
                0, int(time.time() - os.stat(access).st_mtime))
            info = os.stat(access)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise InstallError("pairing file must be current-user-owned mode 0600")
        else:
            details["pairingFileAgeSeconds"] = "missing"
        for key in ("label", "loaded", "pid", "port", "answeringPort", "nodePath",
                    "nodeVersion", "buildPath", "migrationHead", "serverLogBytes",
                    "serverLogCapBytes", "pairingFileAgeSeconds"):
            print(f"{key}={details[key]}")
        return 0 if loaded and details["answeringPort"] == port else 1
    except (InstallError, OSError, ValueError) as exc:
        print(f"doctor_error={str(exc)[:180]}")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    install = subs.add_parser("install")
    install.add_argument("--root", required=True)
    install.add_argument("--archive", required=True)
    install.add_argument("--checksum", required=True)
    install.add_argument("--version", required=True)
    serve = subs.add_parser("resolve")
    serve.add_argument("--root", required=True)
    serve.add_argument("--command", choices=("serve", "node"), default="serve")
    probe = subs.add_parser("doctor")
    probe.add_argument("--root", required=True)
    probe.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install_node(args.root, args.archive, args.checksum, args.version)
        elif args.command == "resolve":
            print(resolve_command(os.path.realpath(args.root), args.command))
        elif args.command == "doctor":
            return doctor(args.root, args.label)
    except InstallError as exc:
        print(f"team_runtime: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
