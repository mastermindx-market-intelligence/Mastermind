#!/usr/bin/env python3
"""Source-only replay of the M2 Codex Switcher OAuth member-identity patch.

No credentials, installed app, session, or running Switcher process is touched.
The original source checkout is read only; patch application is disposable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
STEM = "codex_switcher_business_member_guard_20261019"
PATCH = HERE / "patches" / (STEM + ".patch")
MANIFEST = HERE / "patches" / (STEM + ".manifest.json")
PATHS = frozenset(("src-tauri/src/auth/storage.rs", "src-tauri/src/types.rs"))
HASH = re.compile(r"^[a-f0-9]{64}$")
SHA = re.compile(r"^[a-f0-9]{40}$")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bundle(manifest_path: Path = MANIFEST, patch_path: Path = PATCH) -> dict:
    document = json.loads(manifest_path.read_text())
    required = {
        "schema", "status", "source_base_git_sha", "source_candidate_git_sha",
        "modified_paths", "preimages_sha256", "postimages_sha256", "patch_sha256",
        "rust_unit_tests_passed", "rust_unit_tests_failed",
        "rust_unit_tests_ignored", "source_repo_has_remote",
        "installed_app_modified", "production_credentials_modified",
        "model_turns",
    }
    if type(document) is not dict or set(document) != required:
        raise ValueError("BUNDLE_SCHEMA_REFUSED")
    if (document["schema"] != "mastermind.switcher_member_token_guard_source/v1"
        or document["status"] != "candidate_not_installed"
        or any(document[name] is not False for name in (
            "source_repo_has_remote", "installed_app_modified",
            "production_credentials_modified"))
        or document["model_turns"] != 0
        or document["rust_unit_tests_failed"] != 0
        or type(document["modified_paths"]) is not list
        or set(document["modified_paths"]) != PATHS
        or len(document["modified_paths"]) != len(PATHS)
        or not all(type(document[name]) is str and SHA.fullmatch(document[name])
                   for name in ("source_base_git_sha", "source_candidate_git_sha"))
        or type(document["rust_unit_tests_passed"]) is not int
        or document["rust_unit_tests_passed"] < 1
        or type(document["rust_unit_tests_ignored"]) is not int
        or type(document["patch_sha256"]) is not str
        or HASH.fullmatch(document["patch_sha256"]) is None):
        raise ValueError("BUNDLE_FIELDS_REFUSED")
    for key in ("preimages_sha256", "postimages_sha256"):
        value = document[key]
        if (type(value) is not dict or set(value) != PATHS
                or any(type(h) is not str or HASH.fullmatch(h) is None
                       for h in value.values())):
            raise ValueError("BUNDLE_SOURCE_DIGESTS_REFUSED")
    patch = patch_path.read_bytes()
    if digest(patch) != document["patch_sha256"] or not 1 <= len(patch) <= 120000:
        raise ValueError("BUNDLE_PATCH_CHANGED")
    changes = re.findall(rb"(?m)^diff --git a/([^ \n]+) b/([^ \n]+)$", patch)
    if len(changes) != len(PATHS) or {
        left.decode() for left, right in changes if left == right
    } != PATHS:
        raise ValueError("BUNDLE_PATCH_SCOPE_CHANGED")
    if any(left != right for left, right in changes):
        raise ValueError("BUNDLE_PATCH_SCOPE_CHANGED")
    for fragment in (b"auth.json", b"accounts.json", b"node_modules/",
                     b"Cargo.lock", b".env"):
        if any(fragment in path for path, _ in changes):
            raise ValueError("BUNDLE_PATCH_FORBIDDEN_TARGET")
    return document


def verify_original(source_root: Path) -> dict:
    manifest = read_bundle()
    original = source_root.resolve(strict=True)
    if not original.is_dir():
        raise ValueError("ORIGINAL_SOURCE_ROOT_INVALID")
    snapshots: dict[str, tuple[Path, bytes, tuple[int, int, int, int]]] = {}
    for relative in manifest["modified_paths"]:
        target = original / relative
        info = target.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_nlink != 1):
            raise ValueError("ORIGINAL_SOURCE_PATH_UNSAFE")
        data = target.read_bytes()
        if digest(data) != manifest["preimages_sha256"][relative]:
            raise ValueError("ORIGINAL_SOURCE_PREIMAGE_DRIFT")
        snapshots[relative] = (
            target, data, (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
        )
    with tempfile.TemporaryDirectory(prefix="mmx-switcher-member-replay-") as root:
        scratch = Path(root)
        for relative, (_, original_data, _) in snapshots.items():
            candidate = scratch / relative
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(original_data)
        for args in (
            ["git", "apply", "--unidiff-zero", "--check", str(PATCH)],
            ["git", "apply", "--unidiff-zero", str(PATCH)],
        ):
            result = subprocess.run(args, cwd=scratch, capture_output=True,
                                    text=True, check=False, timeout=30)
            if result.returncode != 0:
                raise ValueError("SOURCE_PATCH_REPLAY_REFUSED")
        for relative in snapshots:
            if digest((scratch / relative).read_bytes()) != manifest["postimages_sha256"][relative]:
                raise ValueError("SOURCE_PATCH_POSTIMAGE_MISMATCH")
    for relative, (target, data, metadata) in snapshots.items():
        after = target.lstat()
        if ((after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size) != metadata
                or digest(target.read_bytes()) != digest(data)):
            raise ValueError("ORIGINAL_SOURCE_CHANGED_DURING_REPLAY")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.source_root:
            verify_original(arguments.source_root)
        else:
            read_bundle()
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        print("SOURCE_REPLAY_REFUSED=" + str(exc).splitlines()[0][:110])
        return 2
    print("BUNDLE_DIGEST_VERIFIED=true")
    if arguments.source_root:
        print("EXACT_PREIMAGE_AND_POSTIMAGE_REPLAY=true")
        print("ORIGINAL_SOURCE_UNCHANGED=true")
    else:
        print("ORIGINAL_SOURCE_REPLAY=NOT_RUN")
    print("INSTALLED_APP_MODIFIED=false")
    print("PRODUCTION_TOKEN_FILES_MODIFIED=false")
    print("LIVE_WORKER_STARTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
