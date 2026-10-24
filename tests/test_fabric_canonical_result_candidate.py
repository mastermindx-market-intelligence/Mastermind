"""Exercise the source-only Macro canonical stdout candidate in canonical CI.

This builds no worker, provides no credentials, dispatches nothing, and never
edits the installed M2 controller. It checks the exact published preimages,
applies the reviewed patch in pytest's disposable directory, and runs the
candidate's complete adversarial regression cases.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/native_fabric/quota_continuity/source"
CANDIDATE = ROOT / "integrations/session_bridge/canonical_macro_result_20261020"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, *, cwd, timeout=120, env=None):
    return subprocess.run(
        argv, cwd=cwd, text=True, capture_output=True,
        timeout=timeout, env=env,
    )


def test_canonical_stdout_patch_exact_source_and_regressions(tmp_path):
    manifest = json.loads((CANDIDATE / "SOURCE_MANIFEST.json").read_text())
    assert manifest["schema"] == "mastermind.fabric.canonical_result_candidate.v2"
    assert manifest["status"] == "SOURCE_ONLY_NOT_INSTALLED"
    expected = manifest["changes"]
    assert set(expected) == {"remote_sub.sh", "remote_sub_helpers.py"}

    # Use the repository's existing reviewed, nonsecret native source closure.
    # Never import or copy a developer's live credentials, results, or ledger.
    work = tmp_path / "ext"
    tests = work / "tests"
    tests.mkdir(parents=True)
    for source in SOURCE.iterdir():
        if source.is_symlink() or not source.is_file():
            continue
        if source.suffix in {".py", ".sh"}:
            shutil.copy2(source, work / source.name)

    for name, fingerprints in expected.items():
        assert digest(work / name) == fingerprints["source_sha256"]
        assert digest(SOURCE / name) == fingerprints["source_sha256"]
        blob = run(["git", "hash-object", str(work / name)], cwd=work)
        assert blob.returncode == 0, blob.stderr
        assert blob.stdout.strip() == fingerprints["source_git_blob_sha"]

    patch = CANDIDATE / "canonical-result-binding.patch"
    check = run(["git", "apply", "--check", str(patch)], cwd=work)
    assert check.returncode == 0, check.stderr
    applied = run(["git", "apply", str(patch)], cwd=work)
    assert applied.returncode == 0, applied.stderr
    for name, fingerprints in expected.items():
        assert digest(work / name) == fingerprints["candidate_sha256"]

    lint = run(["bash", "-n", str(work / "remote_sub.sh")], cwd=work)
    assert lint.returncode == 0, lint.stderr
    (tests / "test_macro_result_canonical.py").write_bytes(
        (CANDIDATE / "test_macro_result_canonical.py").read_bytes()
    )
    assert digest(tests / "test_macro_result_canonical.py") == manifest["source_test_sha256"]

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    result = run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_macro_result_canonical.py"],
        cwd=work, timeout=120, env=env,
    )
    assert result.returncode == 0, result.stdout[-2500:] + result.stderr[-2500:]
    assert "22 passed" in result.stdout, result.stdout[-1000:]
