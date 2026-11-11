"""Exact current native source fixture; no runtime owners or live effects.

The committed 107-file records remain immutable historical inputs. This shared
test fixture derives only the three independently pinned GLM core successors.
"""
import hashlib
import json
from pathlib import Path

BASELINE_MANIFEST_SHA = "22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada"
BASELINE_INVENTORY_SHA = "aa4ca6b0f27e411870f9bad325aca295da1bf3fbf6c536d213d002f675eb2b68"
REVIEWED_CORE = {
    "go_lease_capability.py": (
        "d8562f38a397900bd851ddbe8bb27f511fcefc2bcd2af6ae1eea5d55d15c5940",
        "c4b7ec997cb73a5fbbcd40868de9f9825e18770a82ba4202b8a6de27c9dbcc86"),
    "go_lease_gateway.py": (
        "adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949",
        "4e34f9aa2810a9d897d2b2b3135f91f6f4759e7c08c0575e50cdbab7996e8193"),
    "lease_broker.py": (
        "0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807",
        "b9b13f9a276c3ce814a43e91591588d0e2be9b59066125d7393343241f707004"),
}
APPLICATION_MEMBERS = frozenset({
    "ext/quota_circuit.py", "ext/lease_broker.py",
    "ext/go_lease_capability.py", "ext/go_lease_gateway.py",
})


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(record):
    return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()


def expected_current_source_closure(native):
    native = Path(native)
    baseline_raw = (native / "rollout/native-manifest.json").read_bytes()
    baseline_inventory_raw = (native / "rollout/native-source-inventory.json").read_bytes()
    if (digest(baseline_raw) != BASELINE_MANIFEST_SHA
            or digest(baseline_inventory_raw) != BASELINE_INVENTORY_SHA):
        raise AssertionError("immutable native source baseline differs")
    manifest = json.loads(baseline_raw)
    inventory = json.loads(baseline_inventory_raw)
    for filename, (preimage, candidate) in REVIEWED_CORE.items():
        member = "ext/" + filename
        path = native / "candidate" / filename
        if not path.is_file() or path.is_symlink():
            raise AssertionError("reviewed core source is not regular: " + member)
        data = path.read_bytes()
        row = inventory["files"][member]
        if (manifest[member] != preimage
                or row["sha256"] != preimage or digest(data) != candidate):
            raise AssertionError("reviewed core successor differs: " + member)
        manifest[member] = candidate
        row.update(bytes=len(data), sha256=candidate, composition={
            "schema": "mastermind.glm-native-core-source.v1",
            "preimage_sha256": preimage, "candidate_sha256": candidate})
    return manifest, inventory


def verify_current_stage(output, native, expected_members):
    output, native = Path(output), Path(native)
    manifest_raw = (output / "native-manifest.json").read_bytes()
    inventory_raw = (output / "native-source-inventory.json").read_bytes()
    manifest, inventory = json.loads(manifest_raw), json.loads(inventory_raw)
    expected_manifest, expected_inventory = expected_current_source_closure(native)
    if (manifest_raw != canonical(expected_manifest)
            or inventory_raw != canonical(expected_inventory)
            or len(manifest) != 107
            or set(manifest) != set(expected_members)
            or set(inventory["files"]) != set(manifest)
            or inventory["native_code_files"] != len(manifest)):
        raise AssertionError("current application source closure differs")
    for name, wanted in manifest.items():
        data = (output / "native-code-stage" / name).read_bytes()
        row = inventory["files"][name]
        source = (native / row["source"]).read_bytes()
        if (digest(data) != wanted or row["sha256"] != wanted
                or row["bytes"] != len(data) or source != data):
            raise AssertionError("current captured source differs: " + name)
        if name in APPLICATION_MEMBERS:
            candidate = "candidate/" + name.split("/")[1]
            if row["source"] != candidate or (native / candidate).read_bytes() != data:
                raise AssertionError("current application candidate differs: " + name)
    return manifest


