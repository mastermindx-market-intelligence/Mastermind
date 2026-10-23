#!/usr/bin/env python3
"""Fail-closed provider-free DSH AgentLoop -> ACP WorkerResult qualification.

This is an explicit acceptance command, not a CI assertion that an optional
external supply exists. No installation, routing, provider request or Job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from xml.etree import ElementTree

EXPECTED_DONOR = "4878cdabd87d4041bdaff61d04c966883b9fd07a"
EXPECTED_PROFILE_SOURCE = "4159c403cf63bac8bd18138fa232911589afe06f"
EXPECTED_PROFILE_SHA = "c77814901495ebb3131d28b4968bd3f1cce3f39233e1c0cb580de5a7b9f9106c"
EXPECTED_R4_SHA = "243ec445db513db3bb9ff0cad05bc70550df972a785b8af1546d89c055cadc1f"
EXPECTED_TESTS = 11
SOURCE_FILES = frozenset({
    "governed_acp_fixture.mjs", "scoped_profile.mjs",
    "scoped_profile.test.mjs", "build_governed_fixture.cjs",
})
REPO = Path(__file__).resolve().parents[1]
TEST = REPO / "tests/harness_convergence/test_dsh_acp_governed_worker.py"
SOURCES = REPO / "experiments/harness_convergence/dsh_worker"


class QualificationRefused(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_file(root: Path, relative: str, expected: str) -> None:
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise QualificationRefused("INVALID_MANIFEST", "invalid file/hash types")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or ".." in parts.parts or "\\" in relative:
        raise QualificationRefused("INVALID_MANIFEST", "unsafe relative manifest path")
    dest = (root / relative).resolve(strict=True)
    if not dest.is_relative_to(root) or not dest.is_file():
        raise QualificationRefused("INVALID_MANIFEST", "file escapes supplied root")
    if digest(dest) != expected:
        raise QualificationRefused("PIN_MISMATCH", "supplied file digest mismatch: " + relative)


def verify_supply(root: Path) -> dict:
    if not root.is_dir():
        raise QualificationRefused("MISSING_SUPPLY", "governed DSH external supply is absent")
    manifest_path = root / "supply-manifest.json"
    if not manifest_path.is_file():
        raise QualificationRefused("MISSING_SUPPLY", "external supply has no manifest")
    try:
        data = json.loads(manifest_path.read_text())
    except (ValueError, OSError) as exc:
        raise QualificationRefused("INVALID_MANIFEST", "supply manifest unreadable") from exc
    if not isinstance(data, dict):
        raise QualificationRefused("INVALID_MANIFEST", "manifest must be an object")
    frozen = {
        "donor": EXPECTED_DONOR,
        "profile_head": EXPECTED_PROFILE_SOURCE,
        "r4_patch": EXPECTED_R4_SHA,
        "profile_artifact": EXPECTED_PROFILE_SHA,
    }
    if any(data.get(k) != v for k, v in frozen.items()):
        raise QualificationRefused("PIN_MISMATCH", "donor/profile/patch pin mismatch")
    if set(data.get("fixture_sources", {})) != SOURCE_FILES:
        raise QualificationRefused("INVALID_MANIFEST", "fixture source set mismatch")
    for field, directory in (
        ("files", root), ("fixture_input", root / "fixture-input"),
        ("fixture_sources", SOURCES),
    ):
        entries = data.get(field)
        if not isinstance(entries, dict) or not entries:
            raise QualificationRefused("INVALID_MANIFEST", "missing " + field)
        for relative, expected in entries.items():
            pinned_file(directory, relative, expected)
    pinned_file(root, "profile1060.mjs", EXPECTED_PROFILE_SHA)
    pinned_file(root, "governed-acp-mount.patch", EXPECTED_R4_SHA)
    node_value, node_sha = data.get("node"), data.get("node_sha256")
    if not isinstance(node_value, str) or not os.path.isabs(node_value) or not isinstance(node_sha, str):
        raise QualificationRefused("INVALID_MANIFEST", "missing exact Node binary pin")
    node = Path(node_value).resolve(strict=True)
    if not node.is_file() or digest(node) != node_sha:
        raise QualificationRefused("PIN_MISMATCH", "Node executable digest mismatch")
    return data


def junit_counts(file: Path) -> dict[str, int]:
    if not file.is_file():
        return {"tests": 0, "failures": 0, "errors": 1, "skipped": 0}
    root = ElementTree.parse(file).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites:
        raise QualificationRefused("INVALID_RESULT", "JUnit report has no test suite")
    return {key: sum(int(s.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def qualify(args: argparse.Namespace) -> int:
    evidence = Path(args.evidence_dir).resolve()
    if evidence.is_relative_to(REPO):
        raise QualificationRefused("INVALID_EVIDENCE", "evidence cannot be written into source checkout")
    if evidence.exists():
        raise QualificationRefused("EXISTING_EVIDENCE", "do not overwrite a prior qualification receipt")
    evidence.mkdir(mode=0o700, parents=True)
    (evidence / "home").mkdir(mode=0o700)
    result = {
        "schema": "mastermind.dsh_governed_worker_qualification.v1",
        "source_root": str(REPO),
        "source_test": str(TEST.relative_to(REPO)),
        "qualifier_sha256": digest(Path(__file__).resolve()),
        "source_test_sha256": digest(TEST),
        "provider_calls": 0, "installed": False, "route_armed": False,
        "status": "NOT_RUN",
    }
    try:
        supply = Path(args.supply).resolve()
        manifest = verify_supply(supply)
        result["supply_manifest_sha256"] = digest(supply / "supply-manifest.json")
        result["profile_artifact_sha256"] = manifest["profile_artifact"]
        result["donor"] = manifest["donor"]
        environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(evidence / "home"),
            "PYTHONPATH": str(REPO),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "MMX_DSH_GOVERNED_ACP_SUPPLY": str(supply),
        }
        cmd = [
            sys.executable, "-m", "pytest", "--noconftest", "-p", "no:cacheprovider",
            "-o", "addopts=", "-q", "--basetemp", str(evidence / "pytest-tmp"),
            "--junitxml", str(evidence / "tests.xml"), str(TEST),
        ]
        try:
            completed = subprocess.run(cmd, cwd=REPO, env=environment,
                                       text=True, capture_output=True, timeout=360,
                                       check=False)
        except subprocess.TimeoutExpired:
            raise QualificationRefused("TEST_TIMEOUT", "real AgentLoop fixture timed out") from None
        (evidence / "pytest-output.txt").write_text(completed.stdout + "\n" + completed.stderr)
        result["pytest_exit_code"] = completed.returncode
        counts = junit_counts(evidence / "tests.xml")
        result["junit"] = counts
        result["junit_sha256"] = digest(evidence / "tests.xml") if (evidence / "tests.xml").is_file() else None
        result["pytest_output_sha256"] = digest(evidence / "pytest-output.txt")
        if completed.returncode or counts != {
            "tests": EXPECTED_TESTS, "failures": 0, "errors": 0, "skipped": 0,
        }:
            raise QualificationRefused("NOT_QUALIFIED", "real fixture did not pass every expected case")
        result["status"] = "REAL_PROVIDER_FREE_WORKERRESULT_PASS"
    except QualificationRefused as exc:
        result["status"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError) as exc:
        result["status"] = "INPUT_UNAVAILABLE"
        result["reason"] = type(exc).__name__
    (evidence / "qualification.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "provider_calls", "installed")},
                     sort_keys=True))
    return 0 if result["status"] == "REAL_PROVIDER_FREE_WORKERRESULT_PASS" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supply", required=True, help="absolute pinned external supply root")
    parser.add_argument("--evidence-dir", required=True, help="new external receipt directory")
    try:
        return qualify(parser.parse_args())
    except QualificationRefused as exc:
        print(json.dumps({"status": exc.status, "reason": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
