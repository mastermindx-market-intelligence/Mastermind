#!/usr/bin/env python3
"""Exact-source, no-install verification for the current native Fabric manual preview.

Never calls request, launch, lease, publisher, CURRENT selection, provider or service.
The sealed input generation and two source hashes must agree before patch replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

GENERATION = "0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f"
INPUT = {
    "ext/fabric_task.py": "2294bbcf537ebc7fb91ab03a71f7de85b4c1c8f697932c9e3c8865983dc2633d",
    "pool": "4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059",
    "ext/pick.py": "74bd656884739d61e7a1892735fdcf7844e030fa55b2dc51ecaad1b4c8560286",
}
OUTPUT = {
    "ext/fabric_task.py": "b5ca574e05245637eb008a7c248fbdd77e808ee458472f621e935f7fc0c6e892",
    "pool": "12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679",
    "ext/pick.py": "f785916dc3a7c876af93beefa02bbb663f81124583f8a691d02b13642f203589",
}
PATCH_SHA256 = "53e9c28f43939994f43d6a11018dc0b28cb9eab4d610197cd03c80f94bbeb077"
REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / "ops/native_fabric/patches/native_generation_manual_preview_20261022.patch"
FIXTURE = REPO / "ops/native_fabric/qualification/native_manual_preview_fixture.py"
MAX_BYTES = 196608


def file_bytes(path: Path, expected: str, *, sealed: bool = False) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES or before.st_size < 1:
        raise ValueError(f"not a bounded regular source: {path.name}")
    if sealed and before.st_mode & 0o222:
        raise ValueError(f"sealed source is writable: {path.name}")
    value = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise ValueError("source changed during read")
    if hashlib.sha256(value).hexdigest() != expected:
        raise ValueError(f"source hash drift: {path.name}")
    return value


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=55)
    if completed.returncode != 0:
        raise ValueError(
            "isolated step failed: " + " ".join(command[:3]) + " stderr="
            + completed.stderr[-550:].replace("\n", " ")
        )
    return completed


def qualify(generation: Path) -> dict[str, object]:
    generation = generation.absolute()
    if generation.name != GENERATION or not generation.parent.name == "native-code-releases":
        raise ValueError("not the exact pinned sealed generation")
    if generation.is_symlink() or not generation.is_dir():
        raise ValueError("invalid generation source")
    source = {name: file_bytes(generation / name, sha, sealed=True) for name, sha in INPUT.items()}
    file_bytes(PATCH, PATCH_SHA256)
    if not FIXTURE.is_file() or FIXTURE.is_symlink():
        raise ValueError("missing pinned fixture")
    with tempfile.TemporaryDirectory(prefix="mmx-native-manual-preview-source-only-") as location:
        stage = Path(location)
        for name, content in source.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        run(["git", "apply", "--check", str(PATCH)], stage)
        run(["git", "apply", str(PATCH)], stage)
        for name, sha in OUTPUT.items():
            file_bytes(stage / name, sha)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(stage / "ext") + os.pathsep + str(generation / "ext")
        env["MMX_NATIVE_PREVIEW_CANDIDATE"] = str(stage)
        result = run([sys.executable, str(FIXTURE)], stage, env)
        test_summary = re.search(r"Ran (\d+) tests", result.stderr)
        if not test_summary or int(test_summary.group(1)) != 10 or "\nOK\n" not in result.stderr:
            raise ValueError("native test receipt does not prove the expected ten cases")
        for name, sha in INPUT.items():
            file_bytes(generation / name, sha, sealed=True)
    selected = False
    try:
        current = generation.parent / "CURRENT.json"
        row = json.loads(current.read_text())
        selected = row.get("generation") == GENERATION
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {
        "schema": "mastermind.native_manual_preview_source_qualification.v1",
        "state": "SOURCE_ONLY_TESTED", "generation": GENERATION,
        "current_selected_at_end": selected, "source_count": len(INPUT),
        "patch_sha256": PATCH_SHA256, "tests_passed": 10,
        "sealed_generation_unchanged": True,
        "live_install_performed": False, "provider_call_performed": False,
        "worker_start_proven": False, "review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(qualify(args.generation), sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print("NATIVE_MANUAL_PREVIEW_QUALIFICATION_REFUSED: " + str(exc), file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
