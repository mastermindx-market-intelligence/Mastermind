"""Public Git preimages for offline source composition; no installed-state proof."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
EXACT = {"ext/" + name + ".py" for name in (
    "artifact_delivery", "fabric_operator_contract", "fabric_operator_owner",
    "provider_outcome", "run_observation_delivery")}
PREIMAGES_SHA256 = "9afb3cb62eb1bce33a9a5db12c2ce8edbac50e53d01658fce27f4ea4af51c8f2"


def materialize_predecessor(base, fixture):
    raw = (ROOT / "tests/fixtures/current116-memory-preimages.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PREIMAGES_SHA256
    retained = json.loads(raw)
    assert retained["source_commit"] == "2541a68e9240ca3fb5c1fda7b68e1df8984c973b"
    assert set(retained["sources"]) == EXACT
    for relative, spec in fixture["sources"].items():
        if relative in EXACT:
            saved = retained["sources"][relative]
            assert saved["source"] == spec["source"]
            assert saved["sha256"] == fixture["files"][relative]
            data = zlib.decompress(base64.b64decode(saved["zlib_base64"], validate=True))
            assert len(data) == saved["bytes"]
        else:
            data = ((ROOT / spec["source"]).read_bytes() if "source" in spec else
                    zlib.decompress(base64.b64decode(spec["zlib_base64"], validate=True)))
        assert hashlib.sha256(data).hexdigest() == fixture["files"][relative]
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
