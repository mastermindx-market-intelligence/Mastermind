#!/usr/bin/env python3
"""Read-only exact-source preflight for Mastermind Fabric selector patches.

No live code mutation, no auth/credential access, no service restart, no provider
calls, no lease operations. Replay is performed ONLY inside a private tempdir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any


class PreflightRefusal(ValueError):
    pass


def _source_file(path: Path, limit: int = 1_048_576) -> bytes:
    """Nofollow single-inode bounded local read; no caller path is written."""
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise PreflightRefusal("SOURCE_NOT_BOUNDED_REGULAR:" + path.name)
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            info.st_dev, info.st_ino, info.st_size
        ) or not stat.S_ISREG(opened.st_mode):
            raise PreflightRefusal("SOURCE_CHANGED_ON_READ:" + path.name)
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise PreflightRefusal("SOURCE_TOO_LARGE:" + path.name)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns) != (
            opened.st_dev, opened.st_ino, opened.st_size,
            opened.st_mtime_ns, opened.st_ctime_ns
        ) or len(data) != opened.st_size:
            raise PreflightRefusal("SOURCE_CHANGED_ON_READ:" + path.name)
        return data
    finally:
        os.close(descriptor)


def _relative(value: Any, required_prefix: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PreflightRefusal("INVALID_BUNDLE_PATH")
    raw = PurePosixPath(value)
    if (raw.is_absolute() or ".." in raw.parts
        or any(not re.fullmatch(r"[a-zA-Z0-9_.-]+", part) for part in raw.parts)):
        raise PreflightRefusal("INVALID_BUNDLE_PATH")
    if not value.startswith(required_prefix):
        raise PreflightRefusal("BUNDLE_PATH_OUT_OF_SCOPE")
    return Path(*raw.parts)


def _hash(text: Any) -> str:
    if not isinstance(text, str) or not re.fullmatch(r"[0-9a-f]{64}", text):
        raise PreflightRefusal("INVALID_DIGEST")
    return text


def _manifest(path: Path) -> dict[str, Any]:
    raw = _source_file(path, limit=65536)
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise PreflightRefusal("INVALID_MANIFEST_JSON") from exc
    if (not isinstance(doc, dict) or
        doc.get("schema") != "mastermind.fabric_selector_source_bundle.v1" or
        doc.get("mode") != "SOURCE_ONLY_PREFLIGHT" or
        doc.get("live_install_supported") is not False):
        raise PreflightRefusal("INVALID_MANIFEST_SCHEMA")
    sources = doc.get("sources")
    patches = doc.get("patches")
    if not isinstance(sources, list) or len(sources) != 6 or not isinstance(patches, list) or len(patches) != 7:
        raise PreflightRefusal("BUNDLE_COMPLETENESS_REFUSED")
    return doc


def verify(ext_root: Path, bundle_root: Path, manifest: Path,
           pool_wrapper: Path) -> dict[str, Any]:
    doc = _manifest(manifest)
    by_path: dict[str, bytes] = {}
    for item in doc["sources"]:
        if not isinstance(item, dict):
            raise PreflightRefusal("INVALID_SOURCE_ENTRY")
        requested = item.get("path")
        if requested == "bin/pool":
            rel = Path("bin/pool")
            installed = pool_wrapper
        else:
            rel = _relative(requested, "ext/")
            installed = ext_root / rel.relative_to("ext")
        if str(rel) in by_path:
            raise PreflightRefusal("DUPLICATE_SOURCE")
        expected = _hash(item.get("sha256"))
        # The caller provides explicit installed paths; never write there.
        raw = _source_file(installed)
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise PreflightRefusal("SOURCE_DRIFT:" + str(rel))
        by_path[str(rel)] = raw
        _hash(item.get("patched_sha256"))
    patches: list[Path] = []
    for item in doc["patches"]:
        if not isinstance(item, dict):
            raise PreflightRefusal("INVALID_PATCH_ENTRY")
        rel = _relative(item.get("path"), "ops/native_fabric/patches/")
        patch = bundle_root / rel
        raw = _source_file(patch, limit=262144)
        if hashlib.sha256(raw).hexdigest() != _hash(item.get("sha256")):
            raise PreflightRefusal("PATCH_DRIFT:" + str(rel))
        patches.append(patch)

    # This is only a hermetic *replay* of source patches; no install branch.
    with tempfile.TemporaryDirectory(prefix="mmx-fabric-selector-preflight-") as work:
        temp = Path(work)
        for relative, raw in by_path.items():
            file = temp / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        for patch in patches:
            for check in (True, False):
                action = ["git", "apply"]
                if check:
                    action.append("--check")
                action.append(str(patch))
                try:
                    result = subprocess.run(
                        action, cwd=temp, capture_output=True, text=True,
                        timeout=15, check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise PreflightRefusal("PATCH_REPLAY_UNAVAILABLE") from exc
                if result.returncode:
                    raise PreflightRefusal(
                        "PATCH_REPLAY_REFUSED:" + patch.name + (":CHECK" if check else ":APPLY")
                    )
        actual_paths = {
            str(file.relative_to(temp)) for file in temp.rglob("*") if file.is_file()
        }
        if actual_paths != set(by_path):
            raise PreflightRefusal("PATCH_TOUCHED_UNLISTED_FILE")
        verified: dict[str, str] = {}
        for item in doc["sources"]:
            relative = item["path"]
            actual = hashlib.sha256(_source_file(temp / relative)).hexdigest()
            expected = item["patched_sha256"]
            if actual != expected:
                raise PreflightRefusal("PATCH_RESULT_DRIFT:" + relative)
            verified[relative] = actual

    # A concurrent source edit after the input snapshot is not installation
    # authority. Preserve source-collision evidence and return a refusal.
    for relative, original in by_path.items():
        installed = (pool_wrapper if relative == "bin/pool"
                     else ext_root / Path(relative).relative_to("ext"))
        if hashlib.sha256(_source_file(installed)).digest() != hashlib.sha256(original).digest():
            raise PreflightRefusal("SOURCE_MOVED_DURING_PREFLIGHT:" + relative)

    return {
        "schema": "mastermind.fabric_selector_preflight_result.v1",
        "result": "QUALIFIED_SOURCE_ONLY",
        "patches_verified": len(patches),
        "sources_verified": len(verified),
        "targets": verified,
        "live_source_modified": False,
        "account_or_lease_modified": False,
        "production_installed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ext-root", required=True, type=Path)
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--pool-wrapper", required=True, type=Path)
    args = parser.parse_args()
    try:
        outcome = verify(args.ext_root, args.bundle_root,
                         args.manifest, args.pool_wrapper)
        print(json.dumps(outcome, separators=(",", ":"), sort_keys=True))
        return 0
    except (PreflightRefusal, OSError, ValueError) as exc:
        print(json.dumps({
            "schema": "mastermind.fabric_selector_preflight_result.v1",
            "result": "REFUSED",
            "reason": str(exc)[:200],
            "live_source_modified": False,
            "production_installed": False,
        }, separators=(",", ":"), sort_keys=True))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
