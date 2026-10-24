#!/usr/bin/env python3
"""Exact-source, no-install verification for the current native Fabric manual preview.

Never calls request, launch, lease, publisher, CURRENT selection, provider or service.
The sealed generation, three source hashes, patch and fixture must agree before replay.
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

GENERATION = "6957399841a2913d5a32deedd633e4c4b5124c3199d0e804fc8a6abe69e8ef51"
INPUT = {
    "ext/fabric_task.py": "3ceba9777a475fb1cfc568f13035b4c23ae15c7bd54316c4cb006335557a545b",
    "pool": "4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059",
    "ext/pick.py": "a3c3a9822779e244f4140dc1223c4a2617243ed35c12c0358527d637fc1fc1ee",
}
OUTPUT = {
    "ext/fabric_task.py": "4a37990f0a132bf96f8fbd658452b29472716ba4b544ca73272a2c542c5eee43",
    "pool": "12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679",
    "ext/pick.py": "9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174",
}
PATCH_SHA256 = "b678fa16bc04a075cc87272a30f7ca4a11a9e60391e99c0b44fa46df032376ca"
FIXTURE_SHA256 = "dd2bf01f597b6749d08ebc30092aa59ef9318a8de837c2eaec8504d9e1204f30"
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
    patch_source = file_bytes(PATCH, PATCH_SHA256)
    fixture_source = file_bytes(FIXTURE, FIXTURE_SHA256)
    with tempfile.TemporaryDirectory(prefix="mmx-native-manual-preview-source-only-") as location:
        stage = Path(location)
        for name, content in source.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        staged_fixture = stage / "native_manual_preview_fixture.py"
        staged_fixture.write_bytes(fixture_source)
        staged_patch = stage / "native_manual_preview.patch"
        staged_patch.write_bytes(patch_source)
        numstat = run(["git", "apply", "--numstat", str(staged_patch)], stage).stdout.splitlines()
        changed = [line.split("\t", 2) for line in numstat]
        if len(changed) != len(INPUT) or any(len(fields) != 3 for fields in changed) or {fields[2] for fields in changed} != set(INPUT):
            raise ValueError("native patch changed-path scope drift")
        run(["git", "apply", "--check", str(staged_patch)], stage)
        run(["git", "apply", str(staged_patch)], stage)
        for name, sha in OUTPUT.items():
            file_bytes(stage / name, sha)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(stage / "ext") + os.pathsep + str(generation / "ext")
        env["MMX_NATIVE_PREVIEW_CANDIDATE"] = str(stage)
        result = run([sys.executable, str(staged_fixture)], stage, env)
        test_summary = re.search(r"Ran (\d+) tests", result.stderr)
        if not test_summary or int(test_summary.group(1)) != 12 or "\nOK\n" not in result.stderr:
            raise ValueError("native test receipt does not prove the expected twelve cases")
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
        "patch_sha256": PATCH_SHA256, "fixture_sha256": FIXTURE_SHA256,
        "tests_passed": 12,
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
