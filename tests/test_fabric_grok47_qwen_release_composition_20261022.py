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
    assert len(manifest) == len(inventory["files"]) == 95
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
    assert len(hashes) == 95
    for path, digest_value in hashes.items():
        assert digest((stage / "native-code-stage" / path).read_bytes()) == digest_value


def test_published_bundle_keeps_protected_worker_ceiling_and_operator_scope(tmp_path):
    """Test what the native stage actually publishes, never just candidate files."""
    root = tmp_path / "published-stage"
    p = subprocess.run([sys.executable,
        str(NATIVE / "rollout/build_review_stage.py"), "--output", str(root)],
        text=True, capture_output=True, timeout=25)
    assert p.returncode == 0, p.stderr
    ext = root / "native-code-stage/ext"
    manifest = json.loads((root / "native-manifest.json").read_text())
    files = ("sub.sh", "remote_sub_helpers.py", "fabric_operator_client.py")
    for name in files:
        assert digest((ext / name).read_bytes()) == manifest["ext/" + name]
    sub = (ext / "sub.sh").read_text()
    assert "POOL_REQUEST_MAX_TURNS" in sub
    assert "LOCAL_GROK_MODEL_REFUSED unsupported_model" in sub
    assert "LOCAL_CURSOR_MODEL_REFUSED unsupported_model" in sub
    body = sub.split('CLAUDE_WORKER_MAX_TURNS=120\n', 1)[1]
    body = body.split('\n}\n', 1)[0] + '\n}\n'
    bash = ('CLAUDE_WORKER_MAX_TURNS=120\n' + body
            + '\n_claude_worker_profile glm glm-5.3 || exit $?\n'
            + 'printf "%s\n" "$CLAUDE_WORKER_MAX_TURNS"\n')
    env = {"PATH": "/usr/bin:/bin", "POOL_TASK_COMPLEXITY": "C0_MECHANICAL",
           "POOL_MAX_TURNS": "40", "POOL_REQUEST_MAX_TURNS": "7"}
    call = subprocess.run(["bash", "-c", bash], env=env,
                          text=True, capture_output=True, timeout=5)
    assert call.returncode == 0, call.stderr
    assert call.stdout.strip() == "7"
    forwarded = subprocess.run([sys.executable, str(ext / "remote_sub_helpers.py"),
                                "routing-env"], env=env, text=True,
                               capture_output=True, timeout=5)
    assert forwarded.returncode == 0, forwarded.stderr
    assert "POOL_REQUEST_MAX_TURNS=7" in forwarded.stdout
    helper = (ext / "remote_sub_helpers.py").read_text()
    assert "mastermind.grok_usage.v2" in helper
    assert "requested_cli_only" in helper
    operator = (ext / "fabric_operator_client.py").read_text()
    assert "('grok', 'grok-4.7')" in operator
    assert "Submit fabric_child_request ONCE" in operator
    assert "Never resubmit an uncertain/dispatched request" in operator
    assert "unexpired grant" in operator


def test_published_paid_model_and_grok_controls_composed(tmp_path):
    """New protected canonical paid GLM additions must survive Grok overlay."""
    stage = tmp_path / "composed-stage"
    result = subprocess.run([sys.executable,
        str(NATIVE / "rollout/build_review_stage.py"), "--output", str(stage)],
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((stage / "native-manifest.json").read_text())
    inventory = json.loads((stage / "native-source-inventory.json").read_text())
    assert len(manifest) == len(inventory["files"]) == 95
    assert "qualified_pure_yaml" in inventory
    ext = stage / "native-code-stage/ext"
    for name in ("remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py"):
        data = (ext / name).read_bytes()
        assert digest(data) == manifest["ext/" + name]
        assert inventory["files"]["ext/" + name]["source"] == "../grok47/overlay/" + name
    transport = (ext / "remote_sub.sh").read_text()
    assert "FABRIC_CANONICAL_PAID_MODE" in transport
    assert "CANONICAL_PAID_STATE_REFUSED" in transport
    assert "LOCAL_GROK_MODEL_REFUSED" in (ext / "sub.sh").read_text()
    executor = (ext / "remote_sub_exec.py").read_text()
    assert "_canonical_model_command" in executor
    assert "CANONICAL_PAID_RESULT_RETENTION_UNCONFIRMED" in executor
    assert "grok" in executor.lower()
    helper = (ext / "remote_sub_helpers.py").read_text()
    assert "POOL_REQUEST_MAX_TURNS" in helper
    assert "from paid_incumbent_state import policy_source, read_policy" in helper
    assert "mastermind.grok_usage.v2" in helper


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

def test_approved_grok_bytes_stay_pinned_after_concurrent_source_change(tmp_path, monkeypatch):
    """The accepted bytes are staged once, even if their source changes."""
    clone_root = tmp_path / "ops/native_fabric"
    candidate_native = clone_root / "quota_continuity"
    shutil.copytree(NATIVE / "candidate", candidate_native / "candidate")
    shutil.copytree(NATIVE / "source", candidate_native / "source")
    shutil.copytree(NATIVE / "rollout", candidate_native / "rollout")
    shutil.copytree(GROK, clone_root / "grok47/overlay")
    # Current protected native builder reads the exact locked PyYAML
    # provenance from the repository root, not from its rollout subdirectory.
    pure_yaml = json.loads((NATIVE / "candidate/paid_pyyaml_provenance.json").read_text())
    lock = pure_yaml["lock_path"]
    lock_source = REPO / lock
    raw = lock_source.read_bytes()
    assert digest(raw) == pure_yaml["lock_sha256"]
    lock_target = tmp_path / lock
    lock_target.parent.mkdir(parents=True, exist_ok=True)
    lock_target.write_bytes(raw)
    changed = clone_root / "grok47/overlay/artifact_delivery.py"
    spec = importlib.util.spec_from_file_location(
        "raced_qwen_grok_builder", candidate_native / "rollout/build_review_stage.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    original = Path.read_bytes
    seen = {"changed": False}

    def read_then_mutate(path):
        raw = original(path)
        if path == changed and not seen["changed"]:
            seen["changed"] = True
            changed.write_bytes(raw + b"\n# source modified after first read\n")
        return raw

    stage = tmp_path / "stage"
    monkeypatch.setattr(Path, "read_bytes", read_then_mutate)
    monkeypatch.setattr(sys, "argv", ["build_review_stage.py", "--output", str(stage)])
    builder.main()
    assert seen["changed"]
    manifest = json.loads((stage / "native-manifest.json").read_text())
    pin = read_builder().GROK47_MERGED_SOURCE_DIGESTS["artifact_delivery.py"]
    assert manifest["ext/artifact_delivery.py"] == pin
    assert digest((stage / "native-code-stage/ext/artifact_delivery.py").read_bytes()) == pin
    assert digest(changed.read_bytes()) != pin
