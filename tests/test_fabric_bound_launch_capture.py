"""Replay the pinned capture patch in an isolated inert test process."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def test_pinned_capture_patch_and_owned_child_negatives(tmp_path):
    bundle = Path(__file__).resolve().parents[1] / "integrations/session_bridge/bound_launch_capture"
    manifest = json.loads((bundle / "CAPTURE_SOURCE.json").read_text())
    base = (bundle / "fixtures/lane_runtime.base.py").read_bytes()
    patch = (bundle / "lane_runtime.py.patch").read_bytes()
    assert hashlib.sha256(base).hexdigest() == manifest["base_sha256"]
    assert hashlib.sha256(patch).hexdigest() == manifest["patch_sha256"]
    (tmp_path / "lane_runtime.py").write_bytes(base)
    result = subprocess.run(
        ["patch", "--batch", "-p1", "-i", str(bundle / "lane_runtime.py.patch")],
        cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert hashlib.sha256((tmp_path / "lane_runtime.py").read_bytes()).hexdigest() == manifest["candidate_sha256"]
    for path in (bundle / "tests").glob("test_*.py"):
        shutil.copyfile(path, tmp_path / path.name)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "test_launch_receipt.py",
         "test_launch_identity.py", "test_launch_receipt_binding.py"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "76 passed" in result.stdout, result.stdout
