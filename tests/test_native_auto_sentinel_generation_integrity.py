"""Offline source qualification only; no providers or native selection."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def contract(tmp_path, monkeypatch):
    candidate = _load("ops/native_fabric/verify_native_auto_sentinel_20261024.py", "sentinel_candidate")
    owner = _load("ops/native_fabric/quota_continuity/rollout/native_generation.py", "generation_owner")
    files = {"pool": "a" * 64, "ext/fabric_task.py": "b" * 64, "ext/remote_sub.sh": "c" * 64}
    files.update({f"ext/member_{n}.py": "d" * 64 for n in range(92)})
    meta = owner.descriptor(files, tmp_path / "stable" / "ext")
    digest = owner.digest(owner.canonical(meta))
    meta["digest"] = digest
    monkeypatch.setattr(candidate, "GENERATION", digest)
    return candidate, owner, meta

def test_real_owner_descriptor_is_the_single_generation_digest_contract(contract):
    candidate, owner, meta = contract
    assert candidate.verified_generation_manifest(owner.canonical(meta)) == meta["files"]

@pytest.mark.parametrize("mutation", [
    "changed-member-updated-claim", "missing-member", "extra-member", "absolute-member",
    "parent-member", "malformed-hash", "changed-stable-ext", "changed-binding",
    "changed-entrypoint", "declared-digest", "extra-metadata", "relative-stable-ext",
    "parent-stable-ext", "wrong-shape",
])
def test_changed_generation_refuses_before_source_execution(contract, mutation):
    candidate, owner, original = contract
    meta = copy.deepcopy(original)
    if mutation == "changed-member-updated-claim":
        meta["files"]["ext/remote_sub.sh"] = "e" * 64
    elif mutation == "missing-member":
        meta["files"].pop("ext/member_0.py")
    elif mutation == "extra-member":
        meta["files"]["ext/extra.py"] = "a" * 64
    elif mutation in {"absolute-member", "parent-member"}:
        value = meta["files"].pop("ext/member_0.py")
        meta["files"]["/tmp/elsewhere.py" if mutation == "absolute-member" else "../elsewhere.py"] = value
    elif mutation == "malformed-hash":
        meta["files"]["ext/member_0.py"] = True
    elif mutation == "changed-stable-ext":
        meta["stable_ext"] += "-other"
    elif mutation == "changed-binding":
        meta["links"]["ext/state"] += "-other"
    elif mutation == "changed-entrypoint":
        meta["entrypoints"]["task"] = "ext/other.py"
    elif mutation == "declared-digest":
        meta["digest"] = "e" * 64
    elif mutation == "extra-metadata":
        meta["unexpected"] = True
    elif mutation == "relative-stable-ext":
        meta["stable_ext"] = "relative/ext"
    elif mutation == "parent-stable-ext":
        meta["stable_ext"] += "/../ext"
    else:
        meta = []
    with pytest.raises(ValueError):
        candidate.verified_generation_manifest(owner.canonical(meta))

def test_duplicate_manifest_key_is_not_last_value_wins(contract):
    candidate, owner, meta = contract
    raw = owner.canonical(meta)
    duplicate = b'{"digest":"ignored",' + raw[1:]
    with pytest.raises(ValueError, match="duplicate"):
        candidate.verified_generation_manifest(duplicate)

def test_invalid_closure_stops_before_member_reads_patch_or_test_import(contract, tmp_path, monkeypatch):
    candidate, owner, meta = contract
    root = tmp_path / "native-code-releases" / candidate.GENERATION
    root.mkdir(parents=True)
    meta["files"]["ext/remote_sub.sh"] = "e" * 64
    manifest = root / "RELEASE.json"
    manifest.write_bytes(owner.canonical(meta))
    manifest.chmod(0o444)
    def forbidden(*args, **kwargs):
        pytest.fail("unverified closure reached source/patch/test execution")
    monkeypatch.setattr(candidate, "checked_file", forbidden)
    monkeypatch.setattr(candidate, "exec_checked", forbidden)
    with pytest.raises(ValueError, match="generation"):
        candidate.qualify(root)
