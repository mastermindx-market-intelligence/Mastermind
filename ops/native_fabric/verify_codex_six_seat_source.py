#!/usr/bin/env python3
"""Verify an inert Codex six-seat alias source patch in a disposable directory.

This is not an installer, credential reader, lease selector or account linker.
The live source tree is read only. Nothing is written to any CODEX_HOME.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
FILES = ("codex_pool_policy.py", "codex_native_profile.py",
         "tests/test_codex_pool_policy.py", "tests/test_codex_native_profile.py")
NAME = "codex_six_seat_alias_20261018"
PATCH = HERE / "patches" / (NAME + ".patch")
EXTRA_TEST = HERE / "patches" / (NAME + ".tests.py.txt")
BUSINESS_TEST = HERE / "patches" / (NAME + ".business_tests.py.txt")
MANIFEST = HERE / "patches" / (NAME + ".manifest.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(source: Path) -> None:
    metadata = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (metadata.get("schema") != "mastermind.native_codex_six_seat_source/v1"
            or metadata.get("status") != "source_candidate_not_installed"
            or metadata.get("admission_granted") is not False):
        raise ValueError("source_manifest_invalid")
    if sha(PATCH.read_bytes()) != metadata["patch_sha256"]:
        raise ValueError("source_patch_digest_changed")
    if sha(EXTRA_TEST.read_bytes()) != metadata["additional_tests_sha256"]:
        raise ValueError("source_tests_digest_changed")
    if sha(BUSINESS_TEST.read_bytes()) != metadata["business_tests_sha256"]:
        raise ValueError("business_tests_digest_changed")
    observed = {}
    for name in FILES:
        path = source / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError("source_file_not_regular_" + name)
        data = path.read_bytes()
        observed[name] = sha(data)
        if name in metadata["preimages_sha256"] and observed[name] != metadata["preimages_sha256"][name]:
            raise ValueError("source_preimage_drift_" + name)

    with tempfile.TemporaryDirectory(prefix="mmx-codex-six-alias-") as folder:
        work = Path(folder)
        (work / "tests").mkdir()
        for name in FILES:
            shutil.copy2(source / name, work / name)
        shutil.copy2(EXTRA_TEST, work / "tests/test_codex_six_seat_alias.py")
        shutil.copy2(BUSINESS_TEST, work / "tests/test_codex_business_quota_scope.py")

        for argv in (
            ["git", "apply", "--unidiff-zero", "--check", str(PATCH)],
            ["git", "apply", "--unidiff-zero", str(PATCH)],
        ):
            result = subprocess.run(argv, cwd=work, check=False,
                                    capture_output=True, timeout=12)
            if result.returncode != 0:
                raise ValueError("source_patch_did_not_apply")
        for name, expected in metadata["postimages_sha256"].items():
            if sha((work / name).read_bytes()) != expected:
                raise ValueError("source_postimage_drift_" + name)

        env = {k:v for k,v in os.environ.items()
               if not (k.startswith(("OPENAI_", "CODEX_", "ANTHROPIC_API_KEY"))
                       or k in ("PYTHONPATH", "HTTP_PROXY", "HTTPS_PROXY"))}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        test_argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                     "--basetemp", str(work / "pytest-private"),
                     "tests/test_codex_pool_policy.py",
                     "tests/test_codex_native_profile.py",
                     "tests/test_codex_six_seat_alias.py",
                     "tests/test_codex_business_quota_scope.py"]
        result = subprocess.run(test_argv, cwd=work, env=env, text=True,
                                capture_output=True, check=False, timeout=40)
        if result.returncode:
            raise ValueError("source_tests_failed")
        print("SOURCE_PATCH_VERIFIED=true")
        print("POSTIMAGE_HASHES_MATCH=true")
        print("OFFLINE_PYTEST=" + result.stdout.strip().splitlines()[-1])
        print("CREDENTIAL_OR_PROVIDER_ACCESS=false")
        print("ADMISSION_GRANTED=false")
    for name in FILES:
        if sha((source / name).read_bytes()) != observed[name]:
            raise ValueError("original_source_mutated_" + name)
    print("ORIGINAL_SOURCE_UNCHANGED=true")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        verify(args.source_root.resolve(strict=True))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("SOURCE_VERIFICATION_REFUSED=" + str(exc).splitlines()[0][:130])
        raise SystemExit(2)
