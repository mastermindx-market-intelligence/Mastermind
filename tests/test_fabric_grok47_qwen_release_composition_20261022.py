"""Native seq16 Grok 4.7 + Qwen 429 repair source composition.

The accepted Grok 4.7 overlay is canonical in merged Mastermind PR #1691.
This verifies that adding Qwen selection fixes does not silently revert it.
No live generation, provider, account, bridge, lease or runner is touched.

2026-10-22 release-composition extension: the builder first checks all nine
exact protected overlay bases, then substitutes exactly the three
previously-reviewed candidate-forward bytes. This file adds the closed
three-name forward-map set check, absolute SHA-256 pinning for the four
protected Qwen files, symlinked-candidate and tampered-accepted-base
negatives (typed mismatch, no completed manifest). Existing guarded runtime
suites qualify freshness and caller UTC behavior separately. Every negative
fixture is cloned under tmp_path; repository state is only ever read.
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
FORWARD_NAMES = ("pick.py", "remote_sub.sh", "remote_sub_helpers.py")
BASE_ONLY_OVERLAY_NAMES = (
    "artifact_delivery.py", "fabric_operator_client.py",
    "fabric_operator_contract.py", "native_remote.py", "remote_sub_exec.py",
    "sub.sh",
)
PROTECTED_QWEN_SOURCE_DIGESTS = {
    "bailian_keys.py":
        "a6a775dd3204c4e508dedf9a892d80d3dd42069e88c1e9462c049e9cedbee085",
    "glm_host_account_probe.py":
        "2dbbdf5c7585b45c34269d8d19a8eb68c3919423b91164a024d8a558b42d3325",
    "glm_host_account_source.py":
        "34501b394c24fffd13374894c2c375d2b123c28580ed02335c5e7e19a29d83ab",
    "lease_broker.py":
        "a2847a29abe590cb168c2cd8ae34e0b1c3222b6e92ab4c00f252a342d56e6406",
}


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
    assert len(manifest) == len(inventory["files"]) == 97
    for name in NAMES:
        path = GROK / name
        assert path.is_file() and not path.is_symlink()
        expected = builder.GROK47_MERGED_SOURCE_DIGESTS[name]
        assert digest(path.read_bytes()) == expected
        forward = builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS.get(name)
        if forward is not None:
            assert digest((NATIVE / "candidate" / name).read_bytes()) == forward
        published = forward or expected
        source = "candidate/" + name if forward else "../grok47/overlay/" + name
        assert manifest["ext/" + name] == published
        assert inventory["files"]["ext/" + name]["sha256"] == published
        assert inventory["files"]["ext/" + name]["source"] == source
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
    assert len(hashes) == 97
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
    assert len(manifest) == len(inventory["files"]) == 97
    assert "qualified_pure_yaml" in inventory
    ext = stage / "native-code-stage/ext"
    for name in ("remote_sub.sh", "remote_sub_exec.py", "remote_sub_helpers.py"):
        data = (ext / name).read_bytes()
        assert digest(data) == manifest["ext/" + name]
        source = ("candidate/" if name in read_builder().GROK47_CANDIDATE_COMPOSITION_DIGESTS
                  else "../grok47/overlay/") + name
        assert inventory["files"]["ext/" + name]["source"] == source
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


@pytest.mark.parametrize("name", ("pick.py", "remote_sub.sh", "remote_sub_helpers.py"))
@pytest.mark.parametrize("damage", ("changed", "missing", "symlink"))
def test_builder_refuses_unqualified_forward_composition(tmp_path, name, damage):
    clone_root = tmp_path / "ops/native_fabric"
    candidate_native = clone_root / "quota_continuity"
    for directory in ("candidate", "source", "rollout"):
        shutil.copytree(NATIVE / directory, candidate_native / directory,
                        ignore=shutil.ignore_patterns("native-code-stage", "__pycache__"))
    shutil.copytree(GROK, clone_root / "grok47/overlay")
    changed = candidate_native / "candidate" / name
    if damage == "changed":
        changed.write_bytes(changed.read_bytes() + b"\n# unreviewed forward bytes\n")
    elif damage == "symlink":
        # Even a symlink whose target carries the exact reviewed bytes is
        # refused: the builder requires a regular candidate file.
        reviewed = tmp_path / "reviewed-forward-bytes"
        reviewed.write_bytes(changed.read_bytes())
        changed.unlink()
        changed.symlink_to(reviewed)
    else:
        changed.unlink()
    stage = tmp_path / "stage"
    proc = subprocess.run([sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
                           "--output", str(stage)], capture_output=True, text=True, timeout=25)
    assert proc.returncode != 0
    assert "accepted Grok forward composition mismatch: " + name in proc.stderr
    assert not (stage / "native-manifest.json").exists()
    assert not (stage / "native-source-inventory.json").exists()


def _clone_composition_fixture(tmp_path):
    """Clone the reviewed builder inputs under tmp_path; never touch real state."""
    clone_root = tmp_path / "ops/native_fabric"
    candidate_native = clone_root / "quota_continuity"
    for directory in ("candidate", "source", "rollout"):
        shutil.copytree(NATIVE / directory, candidate_native / directory,
                        ignore=shutil.ignore_patterns("native-code-stage", "__pycache__"))
    shutil.copytree(GROK, clone_root / "grok47/overlay")
    return clone_root, candidate_native


@pytest.mark.parametrize("name", ("artifact_delivery.py", "pick.py"))
def test_builder_refuses_tampered_overlay_base_despite_valid_forward(tmp_path, name):
    """A valid forward candidate never excuses a changed accepted overlay base."""
    clone_root, candidate_native = _clone_composition_fixture(tmp_path)
    builder = read_builder()
    for forward in FORWARD_NAMES:
        assert (digest((candidate_native / "candidate" / forward).read_bytes())
                == builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS[forward])
    changed = clone_root / "grok47/overlay" / name
    changed.write_bytes(changed.read_bytes() + b"\n# tampered accepted overlay base\n")
    stage = tmp_path / "stage"
    proc = subprocess.run(
        [sys.executable, str(candidate_native / "rollout/build_review_stage.py"),
         "--output", str(stage)],
        capture_output=True, text=True, timeout=25,
    )
    assert proc.returncode != 0
    assert "accepted Grok 4.7 source digest mismatch: " + name in proc.stderr
    assert not (stage / "native-manifest.json").exists()
    assert not (stage / "native-source-inventory.json").exists()


def test_forward_map_is_the_closed_reviewed_three_name_set():
    """The forward substitution is exactly three reviewed names over nine bases."""
    builder = read_builder()
    forward = builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS
    merged = builder.GROK47_MERGED_SOURCE_DIGESTS
    assert len(merged) == 9 and set(merged) == set(NAMES)
    assert set(forward) == set(FORWARD_NAMES) and len(forward) == 3
    assert set(forward) < set(merged)
    assert set(merged) - set(forward) == set(BASE_ONLY_OVERLAY_NAMES)
    for name, value in sorted(forward.items()):
        assert len(value) == 64
        assert all(ch in "0123456789abcdef" for ch in value)
        assert value != merged[name]
        candidate = NATIVE / "candidate" / name
        assert candidate.is_file() and not candidate.is_symlink()
        assert digest(candidate.read_bytes()) == value


def test_protected_qwen_files_stay_byte_exact():
    """The four protected Qwen files are pinned to absolute source digests."""
    builder = read_builder()
    assert set(PROTECTED_QWEN_SOURCE_DIGESTS) == set(QWEN)
    assert len(set(PROTECTED_QWEN_SOURCE_DIGESTS.values())) == 4
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(NAMES)
    assert not set(PROTECTED_QWEN_SOURCE_DIGESTS) & set(builder.GROK47_CANDIDATE_COMPOSITION_DIGESTS)
    manifest = json.loads((NATIVE / "rollout/native-manifest.json").read_text())
    inventory = json.loads((NATIVE / "rollout/native-source-inventory.json").read_text())
    for name, expected in sorted(PROTECTED_QWEN_SOURCE_DIGESTS.items()):
        assert name in builder.BASE_FILES
        candidate = NATIVE / "candidate" / name
        assert candidate.is_file() and not candidate.is_symlink()
        assert digest(candidate.read_bytes()) == expected
        assert manifest["ext/" + name] == expected
        row = inventory["files"]["ext/" + name]
        assert row["sha256"] == expected
        assert row["source"] == "candidate/" + name
        assert row["installed_preimage_sha256"]


# Runtime freshness and caller UTC behavior are qualified by the existing
# guarded eligibility/outcome/not-before suites. Exact source digests above
# bind those checked functions; string or identifier ordering is not gate proof.
