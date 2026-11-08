"""Reconstruct the sealed sequence-37 test parent, never the latest output."""
from __future__ import annotations
import base64
import hashlib
import json
import shutil
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "ops/native_fabric/provider_plans"
PARENT_PROFILE = ROOT / "tests/fixtures/provider-plan-sequence37-profile.json"


def materialize_fixed_parent(target):
    metadata = json.loads((HERE / "router_admission.json").read_text())
    raw_profile = PARENT_PROFILE.read_bytes()
    assert hashlib.sha256(raw_profile).hexdigest() == metadata["parent_profile_sha256"]
    profile = json.loads(raw_profile)
    fixture = json.loads((ROOT / "tests/fixtures/provider-plan-auto-predecessor.json").read_text())
    assert fixture["schema"] == "mastermind.provider_plan_test_predecessor.v1"
    assert fixture["generation"] == "9c557397a9fbbcb88fa300b20063d6982c82fe5e768da951c74fa14a298d27b4"
    assert fixture["files"] == profile["files"]
    assert len(fixture["files"]) == 116
    target.mkdir()
    for relative, spec in fixture["sources"].items():
        raw = ((ROOT / spec["source"]).read_bytes() if "source" in spec else
               zlib.decompress(base64.b64decode(spec["zlib_base64"], validate=True)))
        assert hashlib.sha256(raw).hexdigest() == fixture["files"][relative]
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    # Test-only descriptors, with all payloads verified; no installed state read.
    (target / "RELEASE.json").write_text(json.dumps({
        "digest": fixture["generation"], "files": fixture["files"]}))
    (target / "FILES.json").write_text(json.dumps(fixture["files"]))
    return target


def materialize_fixed_sequence38(target, previous):
    """Join only the five recorded overlays to the sealed sequence-37 input."""
    profile = json.loads((HERE / "remote_placement/profile.json").read_text())
    historical_sources = {
        "ext/experiential_bridge.py":
            "ops/native_fabric/experiential_native_bridge/experiential_bridge.py",
        "ext/experiential_host_context.py":
            "ops/native_fabric/experiential53/experiential_host_context.py",
        "ext/experiential_plan_policy.py":
            "control_plane/experiential_plan_policy.py",
        "ext/experiential_transport.py":
            "ops/native_fabric/experiential53/experiential_transport.py",
        "ext/native_plan_worker.py":
            "ops/native_fabric/quota_continuity/candidate/native_plan_worker.py",
    }
    previous_files = json.loads((previous / "RELEASE.json").read_text())["files"]
    assert {
        name for name, expected in profile["base_files"].items()
        if previous_files[name] != expected
    } == set(historical_sources)
    assert all(hashlib.sha256((previous / name).read_bytes()).hexdigest() == expected
               for name, expected in previous_files.items())
    shutil.copytree(previous, target)
    for name, source in historical_sources.items():
        payload = (ROOT / source).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == profile["base_files"][name]
        (target / name).write_bytes(payload)
    files = {
        name: hashlib.sha256((target / name).read_bytes()).hexdigest()
        for name in profile["base_files"]
    }
    assert files == profile["base_files"] and len(files) == 116
    (target / "FILES.json").write_text(json.dumps(files))
    # Inert descriptor over independently hash-qualified public source bytes.
    (target / "RELEASE.json").write_text(json.dumps({
        "digest": profile["base_selection"]["generation"], "files": files}))
    return target
