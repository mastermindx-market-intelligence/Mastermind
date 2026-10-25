#!/usr/bin/env python3
"""Verify a bounded AUTO-sentinel native release candidate without installing it.

Requires the exact sealed generation-22 input, checks all 95 original source
members, applies the reviewed one-file patch in scratch, and runs synthetic
strict-pin/preview tests. No provider, lease, host install or release selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

GENERATION = "ac9acf0daf5a438934f3862afa02039734aa100812d4e040eda5966388817c3b"
INPUT_SHA256 = "4a37990f0a132bf96f8fbd658452b29472716ba4b544ca73272a2c542c5eee43"
OUTPUT_SHA256 = "7700a7975f3585dc985fb37a949448449373ec825d9223648a126bf238a77c2d"
PATCH_SHA256 = "e6ab0c6237648eeb639ef7ac4f10fd67c194aa77589f38f76af7918971521ff8"
FIXTURE_SHA256 = "7153b9293999b6cf641a49764fad1f155fb8b9885f3873e2814a410b48ba293f"
REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / "ops/native_fabric/patches/native_generation_auto_sentinel_20261024.patch"
FIXTURE = REPO / "ops/native_fabric/qualification/native_auto_sentinel_fixture.py"
PREVIEW_FIXTURE = REPO / "ops/native_fabric/qualification/native_manual_preview_fixture.py"
MAX_FILE_BYTES = 2 * 1024 * 1024


def checked_file(path: Path, sha: str, sealed: bool = False) -> bytes:
    first = path.lstat()
    if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= MAX_FILE_BYTES:
        raise ValueError("invalid bounded regular source: " + path.name)
    if sealed and first.st_mode & 0o222:
        raise ValueError("sealed source writable: " + path.name)
    value = path.read_bytes()
    final = path.lstat()
    if (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns, first.st_ctime_ns) != (
        final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns
    ):
        raise ValueError("source changed during read: " + path.name)
    if hashlib.sha256(value).hexdigest() != sha:
        raise ValueError("source SHA256 mismatch: " + path.name)
    return value


def exec_checked(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=55)
    if p.returncode:
        raise ValueError(
            "source-only test failed: " + " ".join(argv[:3])
            + " rc=" + str(p.returncode) + " " + p.stderr[-480:].replace("\n", " ")
        )
    return p.stdout + "\n" + p.stderr


def qualify(generation: Path) -> dict[str, object]:
    generation = generation.absolute()
    if generation.name != GENERATION or generation.parent.name != "native-code-releases":
        raise ValueError("wrong exact baseline generation")
    if generation.is_symlink() or not generation.is_dir():
        raise ValueError("invalid sealed generation directory")
    manifest_path = generation / "RELEASE.json"
    manifest_stat = manifest_path.lstat()
    if not stat.S_ISREG(manifest_stat.st_mode) or manifest_stat.st_mode & 0o222:
        raise ValueError("manifest not sealed")
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files")
    if (manifest.get("schema") != "native-code-generation.v1"
        or manifest.get("digest") != GENERATION
        or not isinstance(files, dict) or len(files) != 95):
        raise ValueError("generation manifest differs from expected exact 95-file source")
    for name, sha in files.items():
        if not isinstance(name, str) or not isinstance(sha, str) or ".." in Path(name).parts:
            raise ValueError("invalid native manifest member")
        checked_file(generation / name, sha, sealed=True)
    if files.get("ext/fabric_task.py") != INPUT_SHA256:
        raise ValueError("native task input drift")
    raw_patch = checked_file(PATCH, PATCH_SHA256)
    fixture = checked_file(FIXTURE, FIXTURE_SHA256)
    if "diff --git a/ext/fabric_task.py b/ext/fabric_task.py" not in raw_patch.decode():
        raise ValueError("native patch unexpected path")
    with tempfile.TemporaryDirectory(prefix="mmx-native-auto-sentinel-source-only-") as location:
        stage = Path(location)
        (stage / "ext").mkdir()
        (stage / "ext/fabric_task.py").write_bytes(
            checked_file(generation / "ext/fabric_task.py", INPUT_SHA256, sealed=True)
        )
        p = stage / "source.patch"
        p.write_bytes(raw_patch)
        counts = [line for line in exec_checked(["git", "apply", "--numstat", str(p)], cwd=stage).splitlines() if line.strip()]
        if len(counts) != 1 or counts[0].split("\t")[-1] != "ext/fabric_task.py":
            raise ValueError("unexpected native patch scope")
        exec_checked(["git", "apply", "--check", str(p)], cwd=stage)
        exec_checked(["git", "apply", str(p)], cwd=stage)
        checked_file(stage / "ext/fabric_task.py", OUTPUT_SHA256)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env["PYTHONPATH"] = os.pathsep.join((str(stage / "ext"), str(generation / "ext")))
        env["MMX_NATIVE_AUTO_SENTINEL_CANDIDATE"] = str(stage)
        env["MMX_NATIVE_AUTO_SENTINEL_BASELINE"] = str(generation)
        env["MMX_NATIVE_PREVIEW_CANDIDATE"] = str(stage)
        test_file = stage / "native_auto_sentinel_fixture.py"
        test_file.write_bytes(fixture)
        result = exec_checked([sys.executable, str(test_file)], cwd=stage, env=env)
        if "Ran 8 tests" not in result or not re.search(r"\nOK\s*$", result):
            raise ValueError("AUTO candidate test count/receipt mismatch")
        preview = exec_checked([sys.executable, str(PREVIEW_FIXTURE)], cwd=stage, env=env)
        if "Ran 12 tests" not in preview or not re.search(r"\nOK\s*$", preview):
            raise ValueError("original strict native preview regression incomplete")
        checked_file(generation / "ext/fabric_task.py", INPUT_SHA256, sealed=True)
    selected = False
    try:
        row = json.loads((generation.parent / "CURRENT.json").read_text())
        selected = row.get("generation") == GENERATION
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {
        "schema": "mastermind.native_auto_sentinel_source_qualification.v1",
        "state": "SOURCE_ONLY_TESTED",
        "generation": GENERATION,
        "source_members_verified": len(files),
        "source_sha256": INPUT_SHA256,
        "candidate_sha256": OUTPUT_SHA256,
        "patch_sha256": PATCH_SHA256,
        "fixture_sha256": FIXTURE_SHA256,
        "tests_passed": 20,
        "original_generation_unchanged": True,
        "current_selected_at_end": selected,
        "live_install_performed": False,
        "provider_call_performed": False,
        "worker_start_proven": False,
        "independent_review_required": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generation", required=True, type=Path)
    ns = ap.parse_args()
    try:
        print(json.dumps(qualify(ns.generation), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("NATIVE_AUTO_SENTINEL_QUALIFICATION_REFUSED: " + str(exc), file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
