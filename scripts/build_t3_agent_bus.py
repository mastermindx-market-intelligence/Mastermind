#!/usr/bin/env python3
"""Reproduce the exact-base T3 affected-source overlay; never install or run T3.

Input is the reviewed `git archive` of only the manifest's base paths, not a live
worktree. Output must not exist. No credentials, network, provider process,
package install, repository initialization, hooks or live profile are involved.
An interrupted build may leave its own incomplete output; never reuse that path.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
from typing import Any

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_PATCH_BYTES = 2 * 1024 * 1024
MAX_FILES = 64
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


def _read(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("A bounded regular input file is required")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if not 0 < len(raw) <= limit:
            raise ValueError("Input changed beyond its bounded contract")
        return raw
    finally:
        os.close(fd)


def _path(value: Any) -> str:
    if (type(value) is not str or not value or len(value) > 512
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value or PurePosixPath(value).is_absolute()
            or str(PurePosixPath(value)) != value
            or any(p in {".", "..", ".git", "node_modules"} for p in PurePosixPath(value).parts)):
        raise ValueError("Unsafe source path")
    return value


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def qualify_package(package: Path) -> tuple[dict, bytes]:
    """Capture and qualify the reviewed bytes once; callers cannot swap a patch later."""
    manifest = json.loads(_read(package / "manifest.json", 131072), object_pairs_hook=_unique)
    patch = _read(package / "native.patch", MAX_PATCH_BYTES)
    license_bytes = _read(package / "UPSTREAM_LICENSE", 16384)
    if (type(manifest) is not dict or manifest.get("schema") != "mastermind.t3-agent-bus-native-overlay.v1"
            or manifest.get("upstream_repository") != "pingdotgg/t3code"
            or type(manifest.get("upstream_revision")) is not str
            or not _REVISION.fullmatch(manifest["upstream_revision"])
            or manifest.get("patch_sha256") != _hash(patch)
            or manifest.get("license_sha256") != _hash(license_bytes)
            or not _SHA.fullmatch(str(manifest.get("base_archive_sha256")))):
        raise ValueError("Native package provenance does not match its captured bytes")
    rows = manifest.get("files")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILES:
        raise ValueError("Bounded native source manifest required")
    paths = set()
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "before_sha256", "after_sha256"}:
            raise ValueError("Invalid native source manifest row")
        path = _path(row["path"])
        if path in paths or not _SHA.fullmatch(str(row["after_sha256"])):
            raise ValueError("Duplicate or unqualified source postimage")
        if row["before_sha256"] is not None and not _SHA.fullmatch(str(row["before_sha256"])):
            raise ValueError("Invalid source preimage")
        paths.add(path)
    expected_base = sorted([row["path"] for row in rows if row["before_sha256"] is not None] + ["LICENSE"])
    if manifest.get("base_archive_paths") != expected_base or len(set(expected_base)) != len(expected_base):
        raise ValueError("Exact upstream base paths are required")
    # No rename, copy, binary, submodule, mode-change or path escape is accepted.
    headers = []
    for line in patch.decode("utf-8").splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" ")
            if len(parts) != 4 or not parts[2].startswith("a/") or not parts[3].startswith("b/"):
                raise ValueError("Invalid native patch target")
            a, b = _path(parts[2][2:]), _path(parts[3][2:])
            if a != b or a not in paths:
                raise ValueError("Native patch escaped the source manifest")
            headers.append(a)
        elif line.startswith(("rename ", "copy ", "GIT binary", "Binary files", "old mode", "new mode", "deleted file")):
            raise ValueError("Unsupported native patch operation")
        elif line.startswith("new file mode") and line != "new file mode 100644":
            raise ValueError("Unexpected new source file mode")
        elif line.startswith(("--- ", "+++ ")):
            target = line[4:]
            if target != "/dev/null" and (target[:2] not in {"a/", "b/"} or _path(target[2:]) not in paths):
                raise ValueError("Unqualified native patch file header")
    if sorted(headers) != sorted(paths):
        raise ValueError("Native patch targets differ from the source manifest")
    return manifest, patch


def materialize_source(*, package: Path, archive: Path, output: Path) -> dict:
    """Create one exclusive source overlay. This never mutates an existing target."""
    manifest, patch = qualify_package(package)
    raw_archive = _read(archive, MAX_ARCHIVE_BYTES)
    if _hash(raw_archive) != manifest["base_archive_sha256"]:
        raise ValueError("Archive is not the exact reviewed native base")
    contents: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:") as source:
        members = source.getmembers()
        if len(members) > MAX_FILES * 16:
            raise ValueError("Too many native base archive entries")
        for member in members:
            path = _path(member.name.rstrip("/") if member.isdir() else member.name)
            if member.isdir():
                continue
            if not member.isfile() or path not in manifest["base_archive_paths"] or path in contents:
                raise ValueError("Native base archive contains an unexpected file or link")
            stream = source.extractfile(member)
            if stream is None or member.size > MAX_ARCHIVE_BYTES:
                raise ValueError("Native base archive member is not bounded")
            contents[path] = stream.read(MAX_ARCHIVE_BYTES + 1)
    if sorted(contents) != manifest["base_archive_paths"]:
        raise ValueError("Native base archive is incomplete")
    for row in manifest["files"]:
        raw = contents.get(row["path"])
        if (None if raw is None else _hash(raw)) != row["before_sha256"]:
            raise ValueError("Native source preimage differs from its reviewed revision")
    if _hash(contents["LICENSE"]) != manifest["license_sha256"]:
        raise ValueError("Upstream license is not the reviewed original")
    if not output.is_absolute() or output.parent.resolve() != output.parent or not output.parent.is_dir():
        raise ValueError("An absolute output with an existing non-aliased parent is required")
    output.mkdir(mode=0o700)  # Exclusive; existing files, directories and symlinks all refuse.
    for name, raw in contents.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CEILING_DIRECTORIES"] = str(output.parent)
    # Apply only the captured, qualified patch. No nested repository or hook owner.
    for check in (True, False):
        subprocess.run(["git", "-C", str(output), "apply", *( ["--check"] if check else []), "-"],
                       input=patch, capture_output=True, check=True, timeout=30, env=env)
    for row in manifest["files"]:
        if _hash(_read(output / row["path"], MAX_PATCH_BYTES * 8)) != row["after_sha256"]:
            raise ValueError("Native source postimage failed verification")
    receipt = {"schema": "mastermind.t3-agent-bus-source-build.v1", "upstream_revision": manifest["upstream_revision"],
               "patch_sha256": manifest["patch_sha256"], "base_archive_sha256": manifest["base_archive_sha256"],
               "files": {row["path"]: row["after_sha256"] for row in manifest["files"]},
               "output_kind": "affected-source-files-only", "installed": False, "runtime_effects": "none"}
    with (output / "source-build.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    package = Path(__file__).resolve().parents[1] / "integrations/t3_agent_bus"
    try:
        print(json.dumps(materialize_source(package=package, archive=args.archive, output=args.output), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, tarfile.TarError, subprocess.SubprocessError):
        print(json.dumps({"error": "SOURCE_BUILD_NOT_QUALIFIED", "installed": False,
                          "recovery": "Inspect any original partial output; do not overwrite or reuse it."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
