"""Native seq16 Grok 4.7 + Qwen 429 repair source composition.

The accepted Grok 4.7 overlay is canonical in merged Mastermind PR #1691.
This verifies that adding Qwen selection fixes does not silently revert it.
No live generation, provider, account, bridge, lease or runner is touched.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
NATIVE = REPO / "ops/native_fabric/quota_continuity"
GROK = REPO / "ops/native_fabric/grok47/overlay"
NAMES = (
    "artifact_delivery.py", "fabric_operator_client.py",
    "fabric_operator_contract.py", "native_remote.py", "pick.py",
    "remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py", "sub.sh",
)
QWEN = ("bailian_keys.py", "lease_broker.py",
        "glm_host_account_probe.py", "glm_host_account_source.py")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_builder():
    file = NATIVE / "rollout/build_review_stage.py"
    spec = importlib.util.spec_from_file_location("qwen_grok_stage_builder", file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_grok47_merged_source_digest_is_pinned():
    builder = read_builder()
    assert set(builder.GROK47_MERGED_SOURCE_DIGESTS) == set(NAMES)
    inventory = json.loads((NATIVE / "rollout/native-source-inventory.json").read_text())
    manifest = json.loads((NATIVE / "rollout/native-manifest.json").read_text())
    assert len(manifest) == len(inventory["files"]) == 85
    for name in NAMES:
        path = GROK / name
        assert path.is_file() and not path.is_symlink()
        expected = builder.GROK47_MERGED_SOURCE_DIGESTS[name]
        assert digest(path.read_bytes()) == expected
        assert manifest["ext/" + name] == expected
        assert inventory["files"]["ext/" + name]["sha256"] == expected
        assert inventory["files"]["ext/" + name]["source"] == "../grok47/overlay/" + name
    for name in QWEN:
        blob = (NATIVE / "candidate" / name).read_bytes()
        assert manifest["ext/" + name] == digest(blob)
        assert inventory["files"]["ext/" + name]["source"] == "candidate/" + name


def test_rebuild_staged_manifest_is_exact(tmp_path):
    stage = tmp_path / "stage"
    result = subprocess.run(
        [sys.executable, str(NATIVE / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        text=True, capture_output=True, timeout=25,
    )
    assert result.returncode == 0, result.stderr
    for name in ("native-manifest.json", "native-source-inventory.json"):
        assert (stage / name).read_bytes() == (NATIVE / "rollout" / name).read_bytes()
    hashes = json.loads((stage / "native-manifest.json").read_text())
    assert len(hashes) == 85
    for path, digest_value in hashes.items():
        assert digest((stage / "native-code-stage" / path).read_bytes()) == digest_value


def test_builder_rejects_changed_accepted_grok_source(tmp_path):
    clone_root = tmp_path / "ops/native_fabric"
    candidate_native = clone_root / "quota_continuity"
    shutil.copytree(NATIVE / "candidate", candidate_native / "candidate")
    shutil.copytree(NATIVE / "source", candidate_native / "source")
    shutil.copytree(NATIVE / "rollout", candidate_native / "rollout")
    shutil.copytree(GROK, clone_root / "grok47/overlay")
    changed = clone_root / "grok47/overlay/remote_sub_exec.py"
    changed.write_bytes(changed.read_bytes() + b"\n# deliberate tamper\n")
    stage = tmp_path / "stage"
    proc = subprocess.run(
        [sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        capture_output=True, text=True, timeout=25,
    )
    assert proc.returncode != 0
    assert "accepted Grok 4.7 source digest mismatch: remote_sub_exec.py" in proc.stderr
    assert not (stage / "native-manifest.json").exists()
