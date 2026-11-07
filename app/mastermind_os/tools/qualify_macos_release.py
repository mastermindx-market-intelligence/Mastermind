#!/usr/bin/env python3
"""Read-only qualification of an existing signed/notarized Mastermind OS .app.

This produces artifact evidence, never release authority, updater admission or an
installation. Apple tools only verify; this tool cannot sign, submit or staple.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class QualificationError(Exception):
    """A bounded failure code, without raw tool output or credentials."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise QualificationError(code)


def _command(args: list[str], code: str) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30,
                                check=False, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        raise QualificationError(code) from None
    _require(result.returncode == 0, code)
    return result.stdout + "\n" + result.stderr


def _field(text: str, key: str) -> str:
    values = [line[len(key) + 1:] for line in text.splitlines() if line.startswith(key + "=")]
    _require(len(values) == 1, "SIGNATURE_METADATA_INVALID")
    return values[0]


def _bundle_digest(app: Path) -> str:
    """Hash names, modes, bytes and contained link targets; never follow links."""
    digest = hashlib.sha256(b"mastermind.os_app_tree.v1\0")
    def failed_walk(error):
        raise error

    digest.update(str(stat.S_IMODE(app.stat().st_mode)).encode() + b"\0")
    for directory, dirs, files, fd in os.fwalk(app, follow_symlinks=False, onerror=failed_walk):
        dirs.sort()
        files.sort()
        for name in sorted(dirs + files):
            path = Path(directory) / name
            before = os.stat(name, dir_fd=fd, follow_symlinks=False)
            mode = stat.S_IMODE(before.st_mode)
            entry = {"path": path.relative_to(app).as_posix(), "mode": mode}
            if stat.S_ISLNK(before.st_mode):
                target = os.readlink(name, dir_fd=fd)
                _require(not Path(target).is_absolute(), "EXTERNAL_SYMLINK")
                _require(path.resolve(strict=True).is_relative_to(app), "EXTERNAL_SYMLINK")
                entry.update(kind="symlink", target=target)
            elif stat.S_ISDIR(before.st_mode):
                entry.update(kind="directory")
            elif stat.S_ISREG(before.st_mode):
                file_hash = hashlib.sha256()
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(file_fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    _require(stat.S_ISREG(opened.st_mode) and
                             (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                             "BUNDLE_CHANGED")
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        file_hash.update(block)
                    after = os.fstat(stream.fileno())
                    _require((opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) ==
                             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "BUNDLE_CHANGED")
                entry.update(kind="file", sha256=file_hash.hexdigest())
            else:
                raise QualificationError("UNSUPPORTED_BUNDLE_ENTRY")
            digest.update(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    return digest.hexdigest()


def _info(app: Path) -> dict:
    """Read the small sealed plist without following substituted parent links."""
    root_fd = os.open(app, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        contents_fd = os.open("Contents", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            info_fd = os.open("Info.plist", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=contents_fd)
            with os.fdopen(info_fd, "rb") as stream:
                _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "INVALID_INFO_PLIST")
                raw = stream.read(1024 * 1024 + 1)
                _require(len(raw) <= 1024 * 1024, "INVALID_INFO_PLIST")
        finally:
            os.close(contents_fd)
    finally:
        os.close(root_fd)
    try:
        info = plistlib.loads(raw)
    except (ValueError, plistlib.InvalidFileException):
        raise QualificationError("INVALID_INFO_PLIST") from None
    _require(isinstance(info, dict), "INVALID_INFO_PLIST")
    return info


def qualify(app: Path, *, source_revision: str, build_identity: str,
            version: str, team_id: str) -> dict:
    _require(sys.platform == "darwin", "MACOS_REQUIRED")
    _require(bool(re.fullmatch(r"[0-9a-f]{40}", source_revision)), "INVALID_SOURCE_REVISION")
    _require(bool(re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", build_identity)), "INVALID_BUILD_IDENTITY")
    _require(bool(re.fullmatch(r"[A-Z0-9]{10}", team_id)), "INVALID_TEAM_ID")
    _require(bool(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version)),
             "INVALID_VERSION")
    _require(not app.is_symlink() and app.is_dir() and app.suffix == ".app", "INVALID_APP_PATH")
    app = app.resolve(strict=True)
    before = _bundle_digest(app)
    try:
        info = _info(app)
    except OSError:
        raise QualificationError("INVALID_INFO_PLIST") from None
    _require(info.get("CFBundleIdentifier") == "com.mastermind.os", "BUNDLE_ID_MISMATCH")
    _require(info.get("CFBundleShortVersionString") == version, "VERSION_MISMATCH")
    executable = info.get("CFBundleExecutable")
    _require(isinstance(executable, str) and bool(re.fullmatch(r"[A-Za-z0-9._-]+", executable))
             and executable not in {".", ".."}, "INVALID_EXECUTABLE")
    binary = app / "Contents/MacOS" / executable
    _require(binary.is_file() and not binary.is_symlink() and os.access(binary, os.X_OK),
             "INVALID_EXECUTABLE")

    _command(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
             "SIGNATURE_VERIFICATION_FAILED")
    signature = _command(["/usr/bin/codesign", "--display", "--verbose=4", str(app)],
                         "SIGNATURE_INSPECTION_FAILED")
    _require(_field(signature, "Identifier") == "com.mastermind.os", "SIGNATURE_ID_MISMATCH")
    _require(_field(signature, "TeamIdentifier") == team_id, "SIGNATURE_TEAM_MISMATCH")
    _require("Signature=adhoc" not in signature and
             any(line.startswith("Authority=Developer ID Application:") for line in signature.splitlines()),
             "DEVELOPER_ID_REQUIRED")
    flags = re.findall(r"^CodeDirectory .*? flags=0x([0-9a-fA-F]+)\(", signature, re.MULTILINE)
    _require(len(flags) == 1 and bool(int(flags[0], 16) & 0x10000), "HARDENED_RUNTIME_REQUIRED")
    _require(info.get("MMSourceRevision") == source_revision, "SOURCE_REVISION_MISMATCH")
    _require(info.get("MMBuildIdentity") == build_identity, "BUILD_IDENTITY_MISMATCH")
    _command(["/usr/bin/xcrun", "stapler", "validate", "-v", str(app)], "STAPLED_TICKET_REQUIRED")
    assessment = _command(["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", str(app)],
                          "GATEKEEPER_REJECTED")
    _require(_field(assessment, "source") == "Notarized Developer ID", "NOTARIZATION_REQUIRED")
    after = _bundle_digest(app)
    _require(before == after, "BUNDLE_CHANGED")
    return {
        "schema": "mastermind.os_macos_release_qualification.v1",
        "qualification": "SIGNED_NOTARIZED_APP_VERIFIED",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": source_revision,
        "build_identity": build_identity,
        "version": version,
        "bundle_identifier": "com.mastermind.os",
        "team_id": team_id,
        "bundle_sha256": after,
        "bundle_digest_schema": "mastermind.os_app_tree.v1",
        "release_authorized": False,
        "updater_qualified": False,
        "installed_journey_qualified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--build-identity", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        _require(not args.out.resolve().is_relative_to(args.app.resolve()), "RECEIPT_MUST_BE_OUTSIDE_APP")
        _require(not args.out.exists() and not args.out.is_symlink(), "RECEIPT_ALREADY_EXISTS")
        result = qualify(args.app, source_revision=args.source_revision, build_identity=args.build_identity,
                         version=args.version, team_id=args.team_id)
        with args.out.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    except QualificationError as exc:
        print(json.dumps({"qualification": "REFUSED", "code": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"qualification": "REFUSED", "code": "QUALIFICATION_IO_FAILED"}), file=sys.stderr)
        return 1
    print(json.dumps({"qualification": result["qualification"], "receipt": str(args.out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
