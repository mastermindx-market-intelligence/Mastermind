"""Exact frozen-record to authenticated GLM core release derivation.

Disposable source qualification only; no installed release, service or provider
is exercised. Expected records are independently pinned here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
RECORD_NAMES = ("native-manifest.json", "native-source-inventory.json")
RECORD_DIGESTS = {
    "native-manifest.json": "22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada",
    "native-source-inventory.json": "aa4ca6b0f27e411870f9bad325aca295da1bf3fbf6c536d213d002f675eb2b68",
}
CORE_SUCCESSORS = {
    "go_lease_capability.py": (
        "d8562f38a397900bd851ddbe8bb27f511fcefc2bcd2af6ae1eea5d55d15c5940", 24577,
        "c4b7ec997cb73a5fbbcd40868de9f9825e18770a82ba4202b8a6de27c9dbcc86", 25031),
    "go_lease_gateway.py": (
        "adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949", 45716,
        "4e34f9aa2810a9d897d2b2b3135f91f6f4759e7c08c0575e50cdbab7996e8193", 47610),
    "lease_broker.py": (
        "0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807", 211236,
        "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004", 217721),
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def original_records(native=NATIVE):
    return {name: (native / "rollout" / name).read_bytes() for name in RECORD_NAMES}


def expected_core_release_records(native, records):
    assert set(records) == set(RECORD_NAMES)
    for name, raw in records.items():
        assert hashlib.sha256(raw).hexdigest() == RECORD_DIGESTS[name]
    manifest = json.loads(records["native-manifest.json"])
    inventory = json.loads(records["native-source-inventory.json"])
    assert len(manifest) == len(inventory["files"]) == inventory["native_code_files"] == 107
    assert set(manifest) == set(inventory["files"])
    before_manifest = dict(manifest)
    before_files = dict(inventory["files"])
    for name, (old, old_size, new, new_size) in CORE_SUCCESSORS.items():
        relative = "ext/" + name
        historical = (native / "rollout/preimages/glm_application_core_5c3d" / name).read_bytes()
        candidate = (native / "candidate" / name).read_bytes()
        assert (hashlib.sha256(historical).hexdigest(), len(historical)) == (old, old_size)
        assert (hashlib.sha256(candidate).hexdigest(), len(candidate)) == (new, new_size)
        row = inventory["files"][relative]
        assert set(row) == {"source", "bytes", "sha256", "installed_preimage_sha256"}
        assert (manifest[relative], row["sha256"], row["bytes"], row["source"]) == (
            old, old, old_size, "candidate/" + name)
        manifest[relative] = new
        inventory["files"][relative] = dict(
            row, sha256=new, bytes=new_size,
            composition={"schema": "mastermind.glm-native-core-source.v1",
                         "preimage_sha256": old, "candidate_sha256": new})
    changed = {"ext/" + name for name in CORE_SUCCESSORS}
    assert {name for name in manifest if manifest[name] != before_manifest[name]} == changed
    assert {name for name in inventory["files"] if inventory["files"][name] != before_files[name]} == changed
    return {"native-manifest.json": encoded(manifest),
            "native-source-inventory.json": encoded(inventory)}


@pytest.fixture(scope="module")
def verify():
    owner = runpy.run_path(str(NATIVE / "rollout/build_review_stage.py"),
                           run_name="h4_release_record_owner")
    return owner["verify_glm_core_release_records"]


def test_exact_successor_is_verified_without_processes_or_record_writes(verify, monkeypatch):
    before = original_records()
    after = expected_core_release_records(NATIVE, before)

    def forbidden(*args, **kwargs):
        raise AssertionError("record verification must remain read-only and process-free")

    with monkeypatch.context() as context:
        context.setattr(subprocess, "Popen", forbidden)
        context.setattr(Path, "write_bytes", forbidden)
        context.setattr(Path, "write_text", forbidden)
        verify(NATIVE, before, after)
    assert original_records() == before


@pytest.mark.parametrize("drift", [
    "unrelated_manifest", "unrelated_inventory", "inventory_header",
    "partial_successor", "composition", "extra_row", "output_encoding",
])
def test_unrelated_partial_or_noncanonical_outputs_are_refused(verify, drift):
    before = original_records()
    after = expected_core_release_records(NATIVE, before)
    manifest = json.loads(after["native-manifest.json"])
    inventory = json.loads(after["native-source-inventory.json"])
    if drift == "unrelated_manifest":
        manifest["ext/pick.py"] = "0" * 64
    elif drift == "unrelated_inventory":
        inventory["files"]["ext/pick.py"]["bytes"] += 1
    elif drift == "inventory_header":
        inventory["stable_ext"] += "/foreign"
    elif drift == "partial_successor":
        manifest["ext/go_lease_gateway.py"] = CORE_SUCCESSORS["go_lease_gateway.py"][0]
    elif drift == "composition":
        inventory["files"]["ext/lease_broker.py"]["composition"]["candidate_sha256"] = "0" * 64
    elif drift == "extra_row":
        manifest["ext/foreign.py"] = "0" * 64
        inventory["files"]["ext/foreign.py"] = dict(inventory["files"]["ext/pick.py"])
    after = {"native-manifest.json": encoded(manifest),
             "native-source-inventory.json": encoded(inventory)}
    if drift == "output_encoding":
        after["native-manifest.json"] += b"\n"
    with pytest.raises(ValueError):
        verify(NATIVE, before, after)


@pytest.mark.parametrize("drift", ["encoding", "duplicate_key", "core_hash", "row_source", "prior_composition"])
def test_foreign_or_ambiguous_predecessor_records_are_refused(verify, drift):
    before = original_records()
    after = expected_core_release_records(NATIVE, before)
    manifest = json.loads(before["native-manifest.json"])
    inventory = json.loads(before["native-source-inventory.json"])
    if drift == "encoding":
        before["native-manifest.json"] += b"\n"
    elif drift == "duplicate_key":
        name = "ext/pick.py"
        duplicate = json.dumps(name) + ": " + json.dumps(manifest[name]) + ","
        before["native-manifest.json"] = ("{" + duplicate + before["native-manifest.json"].decode()[1:]).encode()
    elif drift == "core_hash":
        manifest["ext/lease_broker.py"] = "0" * 64
        before["native-manifest.json"] = encoded(manifest)
    elif drift == "row_source":
        inventory["files"]["ext/lease_broker.py"]["source"] = "source/lease_broker.py"
        before["native-source-inventory.json"] = encoded(inventory)
    elif drift == "prior_composition":
        inventory["files"]["ext/lease_broker.py"]["composition"] = {}
        before["native-source-inventory.json"] = encoded(inventory)
    with pytest.raises(ValueError):
        verify(NATIVE, before, after)


@pytest.mark.parametrize("source", ["candidate", "rollout/preimages/glm_application_core_5c3d"])
def test_changed_authenticating_source_is_refused(verify, tmp_path, source):
    before = original_records()
    after = expected_core_release_records(NATIVE, before)
    for directory in ("candidate", "rollout/preimages/glm_application_core_5c3d"):
        for name in CORE_SUCCESSORS:
            target = tmp_path / directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(NATIVE / directory / name, target)
    changed = tmp_path / source / "lease_broker.py"
    changed.write_bytes(changed.read_bytes() + b"\n# foreign source\n")
    with pytest.raises(ValueError):
        verify(tmp_path, before, after)
