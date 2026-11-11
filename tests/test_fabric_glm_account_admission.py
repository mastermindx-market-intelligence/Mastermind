"""Run the frozen GLM account-admission archive through normal repository CI."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "fabric_glm_account_admission_20261014"
)
SUITE = PACKAGE / "test_account_quota.py"
FROZEN_SOURCE_SHA256 = {
    "quota_remote.py": "a1dab11da10264836e6271955b375b8e6508c23f23d0444c99d96464deb70f2b",
    "lease_broker.py": "d59fed1160403d93c2c46a34b39e0ff87d587f3bc207f74aec3749f658ba20ec",
    "test_account_quota.py": "e3c4deb7d2ec4c2e4178f42e3e676b354cb53fb8149b944481fb702609f094b4",
    "baseline.quota_remote.py": "80ce4151a5d3f05528bc3c5e9af214d510ad9d9f17803c62f01a4c2d818ec5ff",
    "baseline.lease_broker.py": "a72bc031ddb81e559e0cf48fcbf824a959edfcf445c1d3d2d89348c3c66c6f0c",
}
EXPECTED_BASELINE_FAILURES = {
    "test_real_broker_candidate_filter",
    "test_real_broker_acquires_spare_with_original_root",
    "test_explicit_empty_account_cannot_reach_spare",
}


def _run_archive(tmp_path: Path, *, baseline: bool):
    label = "baseline" if baseline else "candidate"
    report = tmp_path / f"{label}.xml"
    env = dict(os.environ)
    for key in ("BROKER_SOURCE", "PYTEST_ADDOPTS", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if baseline:
        env["BROKER_SOURCE"] = "baseline.lease_broker.py"
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
            "-p", "no:cacheprovider", "--confcutdir", str(PACKAGE),
            "--basetemp", str(tmp_path / label),
            "--junitxml", str(report), str(SUITE),
        ],
        cwd=PACKAGE,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    output = result.stdout + result.stderr
    assert report.is_file(), output
    cases = ET.parse(report).getroot().findall(".//testcase")
    assert len(cases) == 24, output
    assert not any(case.find("error") is not None for case in cases), output
    assert not any(case.find("skipped") is not None for case in cases), output
    return result.returncode, cases, output


def test_frozen_glm_account_admission_candidate_and_old_broker_control(tmp_path):
    for filename, expected in FROZEN_SOURCE_SHA256.items():
        assert hashlib.sha256((PACKAGE / filename).read_bytes()).hexdigest() == expected

    candidate_rc, candidate_cases, candidate_output = _run_archive(
        tmp_path, baseline=False
    )
    assert candidate_rc == 0, candidate_output
    assert not any(
        case.find("failure") is not None for case in candidate_cases
    ), candidate_output

    baseline_rc, baseline_cases, baseline_output = _run_archive(
        tmp_path, baseline=True
    )
    assert baseline_rc == 1, baseline_output
    failures = [
        case.attrib["name"]
        for case in baseline_cases
        if case.find("failure") is not None
    ]
    assert len(failures) == 3, baseline_output
    assert set(failures) == EXPECTED_BASELINE_FAILURES, baseline_output
