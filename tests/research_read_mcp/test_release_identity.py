"""Installed byte proof is separate from source/runtime/client acceptance."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from integrations.research_read_mcp import release_identity as identity
from integrations.research_read_mcp.runtime import RuntimeRefused


def fixture(tmp_path):
    root = tmp_path.resolve()
    release = root / ("a" * 40)
    (release / "engine").mkdir(parents=True)
    code = release / "engine/source.py"
    code.write_bytes(b"fixture1")
    code.chmod(0o644)
    manifest = {
        "schema": "mastermind.research_read_stage.v1", "state": "INERT_CANDIDATE",
        "mastermind_commit": "b" * 40, "mastermind_tree": "c" * 40,
        "macro_commit": "a" * 40, "macro_tree": "d" * 40,
        "dependency_lock_sha256": "e" * 64, "macro_import_closure": "OWNER_QUALIFICATION_REQUIRED",
        "files": [], "members": {"mastermind": [], "macro": [{
            "path": "engine/source.py", "bytes": 8,
            "sha256": hashlib.sha256(b"fixture1").hexdigest(),
        }]},
    }
    path = root / "manifest.json"
    raw = (json.dumps(manifest, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    kwargs = {"path": str(release), "commit": "a" * 40, "tree": "d" * 40,
              "project": "macro", "manifest_path": str(path),
              "expected_manifest_sha256": hashlib.sha256(raw).hexdigest(),
              "manifest_owner_uid": os.geteuid(), "release_owner_uid": os.geteuid()}
    return kwargs, manifest, code


def resign(kwargs, document):
    raw = json.dumps(document).encode()
    Path(kwargs["manifest_path"]).write_bytes(raw)
    kwargs["expected_manifest_sha256"] = hashlib.sha256(raw).hexdigest()


def test_verified_bytes_never_claim_dependency_or_runtime_acceptance(tmp_path):
    kwargs, _manifest, _code = fixture(tmp_path)
    receipt = identity.verify_archive_release(**kwargs)
    assert receipt["state"] == "ARCHIVE_BYTES_VERIFIED"
    assert receipt["member_count"] == 1 and receipt["bytes"] == 8
    assert receipt["dependency_closure"] == "OWNER_QUALIFICATION_REQUIRED"


def test_expected_manifest_digest_is_independent_of_mutable_manifest(tmp_path):
    kwargs, manifest, code = fixture(tmp_path)
    code.write_bytes(b"fixture2")
    manifest["members"]["macro"][0]["sha256"] = hashlib.sha256(b"fixture2").hexdigest()
    Path(kwargs["manifest_path"]).write_text(json.dumps(manifest))
    with pytest.raises(RuntimeRefused):
        identity.verify_archive_release(**kwargs)


@pytest.mark.parametrize("change", ["same_size", "missing", "extra", "extra_directory", "symlink",
                                    "writable", "env", "owner"])
def test_filesystem_changes_refuse(tmp_path, change):
    kwargs, _manifest, code = fixture(tmp_path)
    if change == "same_size":
        code.write_bytes(b"fixture2")
    elif change == "missing":
        code.unlink()
    elif change == "extra":
        (code.parent / "extra.py").write_text("fixture")
    elif change == "extra_directory":
        (code.parent / "extra").mkdir()
    elif change == "symlink":
        target = code.with_name("target")
        code.rename(target)
        code.symlink_to(target)
    elif change == "writable":
        code.chmod(0o666)
    elif change == "env":
        (code.parent / ".env.production").write_text("synthetic")
    elif change == "owner":
        kwargs["release_owner_uid"] += 1
    with pytest.raises(RuntimeRefused):
        identity.verify_archive_release(**kwargs)


@pytest.mark.parametrize("change", ["duplicate", "traversal", "nonfinite", "unknown", "bound", "wrong_tree"])
def test_closed_manifest_and_identity_refuse(tmp_path, change):
    kwargs, manifest, _code = fixture(tmp_path)
    row = manifest["members"]["macro"][0]
    if change == "duplicate":
        manifest["members"]["macro"].append(dict(row))
    elif change == "traversal":
        row["path"] = "../source.py"
    elif change == "nonfinite":
        row["bytes"] = float("nan")
    elif change == "unknown":
        row["object_key"] = "synthetic-forbidden-key"
    elif change == "bound":
        row["bytes"] = 64 * 1024 * 1024 + 1
    elif change == "wrong_tree":
        manifest["macro_tree"] = "f" * 40
    resign(kwargs, manifest)
    with pytest.raises(RuntimeRefused):
        identity.verify_archive_release(**kwargs)


def test_earlier_file_change_during_later_capture_is_detected(tmp_path, monkeypatch):
    kwargs, manifest, code = fixture(tmp_path)
    other = code.with_name("tail.py")
    other.write_bytes(b"fixture-tail")
    other.chmod(0o644)
    manifest["members"]["macro"].append({"path": "engine/tail.py", "bytes": 12,
                                         "sha256": hashlib.sha256(b"fixture-tail").hexdigest()})
    resign(kwargs, manifest)
    original = identity._file_digest

    def change_earlier(path, size, uid):
        if path.name == "tail.py":
            code.write_bytes(b"fixture2")
        return original(path, size, uid)

    monkeypatch.setattr(identity, "_file_digest", change_earlier)
    with pytest.raises(RuntimeRefused):
        identity.verify_archive_release(**kwargs)
