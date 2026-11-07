"""Current catalog readers through the actual immutable-release staging body.

Disposable filesystem only. This uses working source so it also detects an
uncommitted source/manifest mismatch; the adjacent archive suite separately
qualifies the final committed Git tree.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from tests.test_paid_release_archive_composition import _materialize


ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path("ops/native_fabric/quota_continuity")
PREIMAGE = "85d40296487f1f040ef3597b8110966e36a9b6ebee781e05a5e6172b8610d78e"
CURRENT_MANIFEST = "28e4c5049a99f28cbb43459ad07e9b2b5bad8a28a3ff0228c15a84360fc16d1f"


def test_current_installer_materializes_the_exact_new_catalog_readers(tmp_path):
    release = tmp_path / "release"
    shutil.copytree(ROOT / "ops/native_fabric", release / "ops/native_fabric",
                    ignore=shutil.ignore_patterns("native-code-stage", "__pycache__"))
    installer = release / "ops/executive_os/install.sh"
    installer.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "ops/executive_os/install.sh", installer)
    provenance = json.loads((ROOT / NATIVE / "candidate/paid_pyyaml_provenance.json").read_bytes())
    lock = Path(provenance["lock_path"])
    (release / lock).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / lock, release / lock)

    rollout = release / NATIVE / "rollout"
    before = {name: (rollout / name).read_bytes()
              for name in ("native-manifest.json", "native-source-inventory.json", "native-preimages.json")}
    assert hashlib.sha256(before["native-manifest.json"]).hexdigest() == CURRENT_MANIFEST
    assert hashlib.sha256((release / NATIVE / "source/pool_ledger.py").read_bytes()).hexdigest() == PREIMAGE
    result = _materialize(release)
    assert result.returncode == 0, result.stderr
    for name, raw in before.items():
        assert (rollout / name).read_bytes() == raw
    manifest = json.loads(before["native-manifest.json"])
    inventory = json.loads(before["native-source-inventory.json"])
    assert len(manifest) == len(inventory["files"]) == 107
    for name, digest in manifest.items():
        path = rollout / "native-code-stage" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_mode & 0o777 == 0o644
    for name in ("fabric_task.py", "pool_ledger.py"):
        staged = (rollout / "native-code-stage/ext" / name).read_bytes()
        assert staged == (release / NATIVE / "candidate" / name).read_bytes()
        assert inventory["files"]["ext/" + name]["source"] == "candidate/" + name
    assert inventory["files"]["ext/pool_ledger.py"]["installed_preimage_sha256"] == PREIMAGE

    # The existing installed owner requires these exact staged members and
    # compares them with the final root release seal, not the historical B11
    # launcher-transition manifest. Keep that actual source contract visible.
    source = (ROOT / "control_plane/paid_fabric_backend.py").read_text()
    assert "native-code-stage/ext" in source
    assert "'fabric_task.py','pool_ledger.py'" in source
    assert "SUCCESSOR_MANIFEST" not in source
