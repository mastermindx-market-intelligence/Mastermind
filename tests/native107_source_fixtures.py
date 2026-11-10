"""Frozen accepted 107-member advice epoch, separate from current APPLICATION.

The manifest and inventory are exact protected e2569dc8 artifacts. Current
builder compatibility is exercised against them; no historical implementation
is substituted for the current builder.
"""
import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCE_COMMIT = "e2569dc878c7fd1c946fe8552adc0fc47cb8df83"
MANIFEST_SHA256 = "470305e48c164563b53626967c178d8c3c5cdaff5a58308aea0a9d838eef3e6d"
INVENTORY_SHA256 = "9c817e6406dd831542a14e591cf4cfa12cd1d6c54c4e8f496844c81415d20d84"

def historical_manifest_and_inventory():
    manifest_raw = (FIXTURES / "native-advice107-e256-manifest.json").read_bytes()
    inventory_raw = (FIXTURES / "native-advice107-e256-inventory.json").read_bytes()
    assert hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256
    assert hashlib.sha256(inventory_raw).hexdigest() == INVENTORY_SHA256
    manifest = json.loads(manifest_raw)
    inventory = json.loads(inventory_raw)
    assert set(manifest) == set(inventory["files"])
    assert len(manifest) == inventory["native_code_files"] == 107
    for name, digest in manifest.items():
        row = inventory["files"][name]
        assert row["sha256"] == digest
        assert type(row["bytes"]) is int and row["bytes"] > 0
    return manifest, inventory
