"""Guard the signed GLM v1/v2 source inventory against stale release digests.

Read-only, deterministic: never loads a provider, service, key or live broker.
The inventory is a source identity record, not authorization to install it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GLM = ROOT / "ops/native_fabric/paid_canonical_glm"
INVENTORY = GLM / "external-preimages.json"
FILES = frozenset({"glm_lease_capability.py", "glm_lease_gateway.py", "glm_shim.py"})
SIGNED_UPGRADE_SHA = {
    "glm_lease_capability.py": "3e4e2ad4dbdfd2ead14ef764adb0e134d6d73e907ef0edebe1d692d1b155a48c",
    "glm_lease_gateway.py": "3ab7ae015d8093f81ab41d8ae73dd849572c8718530750d70ffe551aa719e258",
}
OLD_FLAT_PREIMAGES = {
    "glm_lease_capability.py": "e80070971fdce507c5314e05b5be67abd0f9cd4603ae6a6b1072e666f3e0a5b7",
    "glm_lease_gateway.py": "7fd2b64925cb7d7ea83dd37e3802ddab9d004e775bb4ed04e5da04a51dc5ed00",
}


def _unique_pairs(pairs):
    value = {}
    for name, data in pairs:
        if name in value:
            raise ValueError("duplicate inventory key")
        value[name] = data
    return value


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(base: Path, inventory: Path):
    document = json.loads(inventory.read_bytes(), object_pairs_hook=_unique_pairs)
    assert set(document) == {"external_owner", "files", "installed", "schema", "source_only"}
    assert document["schema"] == "mastermind.paid_glm_external_preimages/v1"
    assert document["installed"] is False and document["source_only"] is True
    assert set(document["files"]) == FILES
    for name, digests in document["files"].items():
        assert set(digests) == {"candidate_sha256", "preimage_sha256"}
        assert len(digests["candidate_sha256"]) == 64
        assert len(digests["preimage_sha256"]) == 64
        assert _sha256(base / "candidate" / name) == digests["candidate_sha256"], name
        assert _sha256(base / "source" / name) == digests["preimage_sha256"], name
    for name, wanted in SIGNED_UPGRADE_SHA.items():
        assert document["files"][name]["candidate_sha256"] == wanted
        assert document["files"][name]["preimage_sha256"] == OLD_FLAT_PREIMAGES[name]
    assert _sha256(base / "candidate" / "glm_shim.py") != _sha256(base / "source" / "glm_shim.py")


def test_signed_glm_source_inventory_is_current_and_historical_preimages_immutable():
    _verify(GLM, INVENTORY)


def test_source_inventory_catches_stale_candidate_digest(tmp_path):
    source = json.loads(INVENTORY.read_text())
    source["files"]["glm_lease_capability.py"]["candidate_sha256"] = (
        source["files"]["glm_lease_capability.py"]["preimage_sha256"]
    )
    bad = tmp_path / "stale.json"
    bad.write_text(json.dumps(source))
    with pytest.raises(AssertionError):
        _verify(GLM, bad)


def test_source_inventory_catches_candidate_byte_drift_without_touching_live_files(tmp_path):
    base = tmp_path / "glm"
    for stage in ("candidate", "source"):
        (base / stage).mkdir(parents=True)
        for name in FILES:
            (base / stage / name).write_bytes((GLM / stage / name).read_bytes())
    (base / "candidate" / "glm_lease_gateway.py").write_bytes(
        (base / "candidate" / "glm_lease_gateway.py").read_bytes() + b"\n# drift"
    )
    with pytest.raises(AssertionError):
        _verify(base, INVENTORY)


def test_source_inventory_refuses_duplicate_keys(tmp_path):
    bad = tmp_path / "duplicate.json"
    bad.write_bytes(INVENTORY.read_bytes().replace(
        b'"source_only": true', b'"source_only": true, "source_only": true'
    ))
    with pytest.raises(ValueError, match="duplicate inventory key"):
        _verify(GLM, bad)
