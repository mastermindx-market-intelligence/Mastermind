"""Qualify the existing core patch against live files without modifying them.

This adds host preimage/rollback proof to the already-qualified ABI fixture.
It does not install source, reload Hermes, admit work, or contact a provider.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone

CORE = frozenset((
    "gateway/run.py", "gateway/run_turn_prepare.py",
    "gateway/run_turn_runner.py", "gateway/session_authority.py",
    "gateway/session_provider_context.py", "hermes_cli/cli_agent_setup_mixin.py",
    "hermes_cli/plugins.py", "hermes_cli/runtime_provider.py",
    "hermes_cli/runtime_provider_host.py", "providers/base.py",
    "hermes_cli/inventory.py", "pm/workspace.py",
    "tests/pm/test_buildable_multi_home.py",
    "ui-tui/src/components/modelPicker.tsx",
    "ui-tui/src/__tests__/modelPickerHostBound.test.tsx",
    "hermes_cli/config.py", "hermes_cli/config_backend.py",
    "hermes_cli/env_loader.py", "hermes_cli/managed_scope.py",
    "tests/hermes_cli/test_config_observational.py",
))
FIXTURE = "integrations/hermes_application_fabric/hermes_core/hermes-2bd378ed-host-bound"
IDENTITY = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(root: Path, *args: str) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
               GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                             "-C", str(root), *args],
                            stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=20, env=env, check=False)
    if result.returncode:
        raise RuntimeError("LOCAL_GIT_CHECK_FAILED: " + args[0])
    return result.stdout


def read_native(root: Path, relative: str) -> tuple[bytes | None, dict | None]:
    path = root / relative
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise RuntimeError("UNSAFE_RELATIVE_PATH")
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise RuntimeError("NATIVE_SYMLINK_REFUSED: " + relative)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None, None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 8 * 1024 * 1024:
            raise RuntimeError("NATIVE_FILE_INVALID: " + relative)
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(fd)
        named = path.lstat()
        if len(raw) != before.st_size or any(
            getattr(before, k) != getattr(item, k)
            for item in (after, named) for k in IDENTITY
        ):
            raise RuntimeError("NATIVE_FILE_CHANGED: " + relative)
        return bytes(raw), {k: getattr(before, k) for k in IDENTITY}
    finally:
        os.close(fd)


def changed_paths(root: Path) -> list[str]:
    raw = git(root, "diff", "--name-only", "-z", "HEAD", "--")
    return sorted(p.decode("utf-8") for p in raw.split(b"\0") if p)


def qualify(native: Path, repository: Path, candidate: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise RuntimeError("EXACT_SOURCE_COMMIT_REQUIRED")
    native = native.resolve(strict=True)
    repository = repository.resolve(strict=True)
    manifest_raw = git(repository, "show", candidate + ":" + FIXTURE + ".json")
    patch = git(repository, "show", candidate + ":" + FIXTURE + ".patch")
    manifest = json.loads(manifest_raw)
    if (manifest.get("schema") != "mastermind.hermes_gateway_patch_fixture.v1"
            or set(manifest.get("preimages", {})) != CORE
            or set(manifest.get("core_files", {})) != CORE
            or digest(patch) != manifest.get("patch_sha256")):
        raise RuntimeError("SOURCE_FIXTURE_INVALID")
    head = git(native, "rev-parse", "HEAD").decode().strip()
    if head != manifest["hermes"]:
        raise RuntimeError("NATIVE_HEAD_CHANGED")
    dirty = changed_paths(native)
    if set(dirty) & CORE:
        raise RuntimeError("LIVE_WRITER_OVERLAPS_CORE")
    observed = {}
    originals = {}
    for relative in sorted(CORE | set(dirty)):
        raw, identity = read_native(native, relative)
        originals[relative] = raw
        observed[relative] = {
            "sha256": None if raw is None else digest(raw),
            "identity": identity,
        }
    for relative, expected in manifest["preimages"].items():
        if observed[relative]["sha256"] != expected:
            raise RuntimeError("NATIVE_PREIMAGE_MISMATCH: " + relative)

    # Apply and reverse only in this temporary directory, outside the live tree.
    with tempfile.TemporaryDirectory(prefix="hermes-h4-native-preimages-") as name:
        fixture = Path(name)
        for relative, raw in originals.items():
            if raw is not None:
                path = fixture / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        patch_path = fixture / "qualified.patch"
        patch_path.write_bytes(patch)
        git(fixture, "apply", "--check", str(patch_path))
        git(fixture, "apply", str(patch_path))
        postimages = {}
        for relative, expected in manifest["core_files"].items():
            raw, _ = read_native(fixture, relative)
            if raw is None or digest(raw) != expected:
                raise RuntimeError("PATCH_POSTIMAGE_MISMATCH: " + relative)
            if relative.endswith(".py"):
                ast.parse(raw, filename=relative)
            # TSX syntax is qualified by the native Ink suite; this gate
            # verifies its exact preimage, postimage and reversible patch.
            postimages[relative] = digest(raw)
        for relative in dirty:
            raw, _ = read_native(fixture, relative)
            if raw != originals[relative]:
                raise RuntimeError("PATCH_CHANGED_UNRELATED_FILE")
        git(fixture, "apply", "--reverse", "--check", str(patch_path))
        git(fixture, "apply", "--reverse", str(patch_path))
        for relative, expected in originals.items():
            raw, _ = read_native(fixture, relative)
            if raw != expected:
                raise RuntimeError("ROLLBACK_PREIMAGE_MISMATCH: " + relative)

    if git(native, "rev-parse", "HEAD").decode().strip() != head or changed_paths(native) != dirty:
        raise RuntimeError("LIVE_SOURCE_CHANGED_DURING_QUALIFICATION")
    for relative, initial in observed.items():
        raw, identity = read_native(native, relative)
        if {"sha256": None if raw is None else digest(raw), "identity": identity} != initial:
            raise RuntimeError("LIVE_FILE_CHANGED_DURING_QUALIFICATION: " + relative)
    if (git(repository, "show", candidate + ":" + FIXTURE + ".json") != manifest_raw
            or git(repository, "show", candidate + ":" + FIXTURE + ".patch") != patch):
        raise RuntimeError("SOURCE_FIXTURE_CHANGED")
    return {
        "schema": "mastermind.hermes_h4_live_preimage_qualification.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": candidate, "native_head": head,
        "manifest_sha256": digest(manifest_raw), "patch_sha256": digest(patch),
        "native_files": observed, "core_postimages": postimages,
        "preserved_tracked_edits": dirty,
        "patch_apply_check": True, "exact_postimages": True,
        "syntax_checked_files": sum(path.endswith(".py") for path in postimages),
        "non_python_postimages_verified": sorted(path for path in postimages if not path.endswith(".py")),
        "reverse_patch_restores_preimages": True,
        "live_source_unchanged": True, "installed": False,
        "runtime_reload": False, "provider_request": False,
        "worker_dispatch": False, "live_acceptance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", required=True, type=Path)
    parser.add_argument("--source-repo", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.native_root.resolve(strict=True)):
        raise RuntimeError("RECEIPT_MUST_BE_OUTSIDE_LIVE_NATIVE_ROOT")
    receipt = qualify(args.native_root, args.source_repo, args.candidate)
    receipt["qualifier_source_sha256"] = digest(Path(__file__).read_bytes())
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"state": "QUALIFIED_PREIMAGES_NOT_INSTALLED",
                      "receipt": str(args.output), "sha256": digest(raw),
                      "core_files": len(CORE),
                      "preserved_tracked_edits": receipt["preserved_tracked_edits"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
