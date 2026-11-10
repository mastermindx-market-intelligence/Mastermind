"""Expose the real Grok billing regression suite to canonical hosted pytest CI."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
BILLING = ROOT / "ops/native_fabric/grok47/quota_billing"
PRESERVED = (
    "source/quota_remote.py",
    "candidate/quota_remote.py",
    "rollout/native-preimages.json",
    "rollout/native-manifest.json",
    "rollout/native-source-inventory.json",
)


def test_grok_billing_suite_runs_and_preserves_native_inputs() -> None:
    suite = BILLING / "test_grok_acp_billing.py"
    assert suite.is_file(), "required Grok billing suite is missing"
    before = {relative: (NATIVE / relative).read_bytes() for relative in PRESERVED}
    source_sha = hashlib.sha256(before["source/quota_remote.py"]).hexdigest()
    candidate = before["candidate/quota_remote.py"]
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    preimages = json.loads(before["rollout/native-preimages.json"])
    manifest = json.loads(before["rollout/native-manifest.json"])
    entry = json.loads(before["rollout/native-source-inventory.json"])["files"][
        "ext/quota_remote.py"
    ]
    assert preimages["files"]["quota_remote.py"] == source_sha
    assert manifest["ext/quota_remote.py"] == candidate_sha
    assert entry["source"] == "candidate/quota_remote.py"
    assert entry["sha256"] == candidate_sha
    assert entry["bytes"] == len(candidate)
    assert entry["installed_preimage_sha256"] == source_sha

    try:
        run = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", "test_grok_acp_billing"],
            cwd=BILLING,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    finally:
        for relative, original in before.items():
            assert (NATIVE / relative).read_bytes() == original, (
                f"frozen native input changed during billing tests: {relative}"
            )

    report = run.stdout + run.stderr
    assert run.returncode == 0, "Grok billing suite failed: " + report[-3000:]
    # unittest can exit zero after discovering no cases. Use its final count.
    counts = re.findall(r"(?m)^Ran (\d+) tests?\b", report)
    assert counts and int(counts[-1]) >= 7, (
        "Grok billing suite discovered too few cases: " + report[-1000:]
    )
    assert not re.search(r"\bskipped=[1-9]\d*\b", report), (
        "skipped billing cases are not execution proof: " + report[-1000:]
    )
