"""Pin and qualify the signed Peekaboo CLI beside the installed Mac GUI bridge.

This is an offline fleet-install *payload*, not a daemon, Runtime capability,
or TCC/credential installer. The existing enrolled host owner invokes it only
after selecting the physical Mac. No unsigned Homebrew replacement or privilege
escalation. A successful read-only preflight does not authorize a worker action.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile

VERSION = "4.9.2"
ARCHIVE_SHA256 = "d0679fdccab7295261add8be4880a7ba0f87a8e6e1aa0fec1d21c6c98c79f448"
TEAM_ID = "FWJYW4S8P8"
CLI_ID = "boo.peekaboo.peekaboo"
APP_ID = "boo.peekaboo.mac"
ROOT_NAME = "peekaboo-macos-arm64"
MEMBER_NAMES = frozenset({
    ROOT_NAME, ROOT_NAME + "/peekaboo", ROOT_NAME + "/LICENSE",
    ROOT_NAME + "/libswiftCompatibilitySpan.dylib",
    ROOT_NAME + "/README.md", ROOT_NAME + "/VERSION",
})
MAX_ARCHIVE = 40 * 1024 * 1024
MAX_UNPACKED = 70 * 1024 * 1024
SCHEMA = "mastermind.native_signed_helper_qualification.v1"


class QualificationRefused(RuntimeError):
    pass


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            value.update(chunk)
    return value.hexdigest()


def checked_dir(path: Path) -> Path:
    if path.is_symlink():
        raise QualificationRefused("UNSAFE_INSTALL_DIRECTORY")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise QualificationRefused("UNSAFE_INSTALL_DIRECTORY")
    return path


def inspect_archive(archive: Path) -> list[tarfile.TarInfo]:
    info = archive.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARCHIVE
            or info.st_size <= 0 or info.st_nlink != 1
            or digest_file(archive) != ARCHIVE_SHA256):
        raise QualificationRefused("SIGNED_HELPER_ARCHIVE_DIGEST_REFUSED")
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if ({m.name.rstrip("/") for m in members} != MEMBER_NAMES
                or len(members) != len(MEMBER_NAMES)
                or sum(m.size for m in members) > MAX_UNPACKED):
            raise QualificationRefused("SIGNED_HELPER_ARCHIVE_LAYOUT_REFUSED")
        for member in members:
            normalized = member.name.rstrip("/")
            if normalized == ROOT_NAME:
                if not member.isdir():
                    raise QualificationRefused("SIGNED_HELPER_ARCHIVE_LAYOUT_REFUSED")
            elif (not member.isfile() or member.size < 0
                  or member.size > MAX_UNPACKED or member.linkname):
                raise QualificationRefused("SIGNED_HELPER_ARCHIVE_LAYOUT_REFUSED")
    return members


def extract_verified(archive: Path, destination: Path) -> None:
    inspect_archive(archive)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            name = member.name.rstrip("/")
            if name == ROOT_NAME:
                continue
            target = destination / name[len(ROOT_NAME) + 1:]
            if target.parent != destination or target.exists() or target.is_symlink():
                raise QualificationRefused("SIGNED_HELPER_ARCHIVE_LAYOUT_REFUSED")
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise QualificationRefused("SIGNED_HELPER_ARCHIVE_LAYOUT_REFUSED")
            # Private regular-file creation, never follow archive symlinks.
            with target.open("xb") as output:
                shutil.copyfileobj(extracted, output, length=65536)
            target.chmod(0o500 if target.name == "peekaboo" else 0o400)


def command(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise QualificationRefused("SIGNED_HELPER_COMMAND_UNAVAILABLE") from error


def signature(path: Path, *, expected_id: str) -> dict:
    check = command(["/usr/bin/codesign", "--verify", "--strict", str(path)])
    if check.returncode:
        raise QualificationRefused("SIGNED_HELPER_SIGNATURE_INVALID")
    details = command(["/usr/bin/codesign", "-dv", "--verbose=2", str(path)])
    text = details.stderr + "\n" + details.stdout
    if (f"Identifier={expected_id}" not in text
            or f"TeamIdentifier={TEAM_ID}" not in text):
        raise QualificationRefused("SIGNED_HELPER_SIGNER_MISMATCH")
    return {"bundle_id": expected_id, "team_id": TEAM_ID, "verified": True}


def verify_cli(binary: Path) -> dict:
    info = binary.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022):
        raise QualificationRefused("SIGNED_HELPER_BINARY_UNSAFE")
    signer = signature(binary, expected_id=CLI_ID)
    version = command([str(binary), "--version"], timeout=8)
    if version.returncode or not version.stdout.startswith("Peekaboo " + VERSION + " "):
        raise QualificationRefused("SIGNED_HELPER_VERSION_MISMATCH")
    return {"version": VERSION, "binary_sha256": digest_file(binary),
            "signing": signer}


def verify_app(app: Path) -> dict:
    info = app.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise QualificationRefused("SIGNED_GUI_APP_MISSING")
    properties = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    if properties.get("CFBundleShortVersionString") != VERSION:
        raise QualificationRefused("SIGNED_GUI_APP_VERSION_MISMATCH")
    return {"version": VERSION, "signing": signature(app, expected_id=APP_ID)}


def verify_bridge(binary: Path, bridge: Path) -> dict:
    info = bridge.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise QualificationRefused("SIGNED_GUI_BRIDGE_NOT_OWNED")
    reply = command([str(binary), "permissions", "status", "--json",
                     "--bridge-socket", str(bridge)], timeout=30)
    if reply.returncode:
        raise QualificationRefused("SIGNED_GUI_BRIDGE_PERMISSION_READ_FAILED")
    try:
        record = json.loads(reply.stdout)
        data = record["data"]
        if record["success"] is not True or data["source"] != "bridge":
            raise ValueError("wrong source")
        flags = {item["name"]: item["isGranted"]
                 for item in data["permissions"]}
        if not {"Screen Recording", "Accessibility", "Event Synthesizing"} <= set(flags):
            raise ValueError("missing permission row")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise QualificationRefused("SIGNED_GUI_BRIDGE_RESULT_UNQUALIFIED") from error
    return {"owner_uid": info.st_uid, "source": "bridge", "permissions": flags,
            "observation_ready": all(flags.get(k) is True for k in (
                "Screen Recording", "Accessibility", "Event Synthesizing"))}


def install_archive(archive: Path, destination: Path, parent: Path) -> None:
    inspect_archive(archive)
    lock_path = parent / "install.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise QualificationRefused("SIGNED_HELPER_INSTALL_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise QualificationRefused("SIGNED_HELPER_INSTALL_BUSY") from error
        if destination.exists():
            verify_cli(destination / "peekaboo")
            return
        scratch = Path(tempfile.mkdtemp(prefix=".verify-", dir=parent))
        try:
            extract_verified(archive, scratch)
            verify_cli(scratch / "peekaboo")
            os.rename(scratch, destination)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--archive")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("native GUI helper qualification is macOS-only")
    if args.install != bool(args.archive):
        parser.error("--install requires exactly one pinned --archive")
    home = Path.home()
    parent = home / "Library/Application Support/Mastermind/native-helper"
    destination = parent / ("peekaboo-" + VERSION)
    report = {"schema": SCHEMA, "version": VERSION, "status": "NOT_QUALIFIED",
              "host_ref": hashlib.sha256(socket.gethostname().encode()).hexdigest(),
              "uid": os.getuid(), "worker_admission_proven": False,
              "production_grant_enabled": False}
    try:
        if args.install:
            checked_dir(parent)
            install_archive(Path(args.archive).resolve(strict=True), destination, parent)
        if not destination.is_dir():
            raise QualificationRefused("SIGNED_HELPER_NOT_INSTALLED")
        cli = verify_cli(destination / "peekaboo")
        app = verify_app(Path("/Applications/Peekaboo.app"))
        bridge = verify_bridge(destination / "peekaboo",
                               home / "Library/Application Support/Peekaboo/bridge.sock")
        report.update({"cli": cli, "gui": app, "bridge": bridge,
                       "status": "OBSERVATION_READY" if bridge["observation_ready"]
                       else "GUI_PERMISSION_UNAVAILABLE"})
    except (QualificationRefused, OSError, ValueError) as error:
        report["reason"] = str(error)[:128] if isinstance(error, QualificationRefused) else "HOST_PRECONDITION_FAILED"
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "OBSERVATION_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
