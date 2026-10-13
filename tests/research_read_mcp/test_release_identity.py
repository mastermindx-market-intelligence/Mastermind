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


def owner_config(tmp_path, **changes):
    path = tmp_path.resolve() / "archive-owner.json"
    value = {"schema": identity.ARCHIVE_OWNER_SCHEMA,
             "manifest_path": str(tmp_path.resolve() / "manifest.json"),
             "manifest_sha256": "e" * 64}
    value.update(changes)
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def test_secure_owner_binding_callback_retains_receipt_and_reverifies(tmp_path, monkeypatch):
    from tests.research_read_mcp.test_runtime import parsed
    deployment = parsed()
    path = owner_config(tmp_path)
    calls = []
    def verifier(*args, **kwargs):
        calls.append((args, kwargs))
        return {"project": kwargs["project"], "state": "ARCHIVE_BYTES_VERIFIED"}
    monkeypatch.setattr(identity, "verify_archive_release", verifier)
    bound = identity.load_archive_verifier(str(path), deployment, owner_uid=os.geteuid())
    args = (deployment.mastermind_release, deployment.mastermind_commit, deployment.mastermind_tree)
    assert bound(*args) is None
    assert bound(*args) is None
    assert len(calls) == 2 and len(bound.receipts) == 1
    assert calls[0][1] == {"project": "mastermind", "manifest_path": str(tmp_path.resolve() / "manifest.json"),
                           "expected_manifest_sha256": "e" * 64,
                           "manifest_owner_uid": os.geteuid(), "release_owner_uid": 0}
    bound.receipts[0]["state"] = "mutable-copy"
    assert bound.receipts[0]["state"] == "ARCHIVE_BYTES_VERIFIED"
    with pytest.raises(RuntimeRefused):
        bound(args[0], args[1], "f" * 40)
    assert len(calls) == 2
    def changed(*args, **kwargs):
        raise RuntimeRefused("ARCHIVE_IDENTITY_REFUSED")
    monkeypatch.setattr(identity, "verify_archive_release", changed)
    with pytest.raises(RuntimeRefused):
        bound(*args)


@pytest.mark.parametrize("change", ["mode", "symlink", "owner", "digest", "relative", "extra", "deployment"])
def test_owner_binding_refuses_untrusted_configuration(tmp_path, change):
    from tests.research_read_mcp.test_runtime import parsed
    from dataclasses import replace
    path = owner_config(tmp_path)
    owner = os.geteuid()
    deployment = parsed()
    if change == "mode":
        path.chmod(0o644)
    elif change == "symlink":
        actual = path.with_name("actual.json")
        path.rename(actual)
        path.symlink_to(actual)
    elif change == "owner":
        owner += 1
    elif change == "digest":
        path = owner_config(tmp_path, manifest_sha256="not-a-pin")
    elif change == "relative":
        path = owner_config(tmp_path, manifest_path="manifest.json")
    elif change == "extra":
        path = owner_config(tmp_path, issuer="https://extra.invalid/")
    elif change == "deployment":
        deployment = replace(deployment, macro_release="/tmp/arbitrary")
    with pytest.raises(RuntimeRefused):
        identity.load_archive_verifier(str(path), deployment, owner_uid=owner)
