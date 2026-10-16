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


def selected_owner_value(tmp_path, *, valid_until=None):
    return {"schema": identity.SELECTED_ARCHIVE_OWNER_SCHEMA,
            "manifest_path": str(tmp_path.resolve() / "manifest.json"),
            "manifest_sha256": "e" * 64,
            "selected_read": {
                "expected_producer_commit": "b" * 40,
                "max_age_seconds": 3600, "max_reuse_seconds": 300,
                "corpus_byte_budget": 32 * 1024 * 1024,
                "image_admission_bytes": 256 * 1024 * 1024,
                "refresh_interval_seconds": 30,
                "writer_protocol_qualified": True,
                "valid_until": (int(identity._wall_now()) + 3600
                                if valid_until is None else valid_until)}}


def selected_owner_config(tmp_path, top=None, read=None, raw=None, valid_until=None):
    path = tmp_path.resolve() / "archive-owner.json"
    value = selected_owner_value(tmp_path, valid_until=valid_until)
    if top:
        value.update(top)
    if read:
        value["selected_read"].update(read)
    path.write_text(json.dumps(value) if raw is None else raw)
    path.chmod(0o600)
    return path


def test_v1_owner_binding_keeps_selected_options_none(tmp_path, monkeypatch):
    from tests.research_read_mcp.test_runtime import parsed
    monkeypatch.setattr(identity, "verify_archive_release", lambda *a, **k: None)
    bound = identity.load_archive_verifier(str(owner_config(tmp_path)), parsed(),
                                           owner_uid=os.geteuid())
    # v1 behavior is exact: no selected options can arrive through the old schema.
    assert bound.selected_options is None


def test_v2_owner_admits_exact_options_with_live_fresh_reread_policy(tmp_path, monkeypatch):
    import sys
    from tests.research_read_mcp.test_runtime import parsed
    from integrations.research_read_mcp.selected_factory import SelectedReadOptions
    deployment = parsed()
    path = selected_owner_config(tmp_path)
    # Binding and policy use must never import the server/listener or audit sink.
    monkeypatch.setitem(sys.modules, "integrations.research_read_mcp.app", None)
    monkeypatch.setitem(sys.modules, "integrations.business_mcp_auth.audit", None)
    monkeypatch.setattr(identity, "verify_archive_release", lambda *a, **k: None)
    bound = identity.load_archive_verifier(str(path), deployment, owner_uid=os.geteuid())
    options = bound.selected_options
    assert type(options) is SelectedReadOptions
    # The producer commit is a writer declaration, independent of the reader release.
    assert options.expected_producer_commit == "b" * 40
    assert options.expected_producer_commit != deployment.mastermind_commit
    assert options.max_age_seconds == 3600 and options.max_reuse_seconds == 300
    assert options.corpus_byte_budget == 32 * 1024 * 1024
    assert options.image_admission_bytes == 256 * 1024 * 1024
    assert options.refresh_interval_seconds == 30
    assert bound(deployment.mastermind_release, deployment.mastermind_commit,
                 deployment.mastermind_tree) is None
    original = identity.read_secure_json
    reads = []
    def counting(read_path, **kwargs):
        reads.append(read_path)
        return original(read_path, **kwargs)
    monkeypatch.setattr(identity, "read_secure_json", counting)
    assert options.writer_policy() is True
    assert options.writer_policy() is True
    # Each use freshly and securely rereads the SAME owner file bytes.
    assert reads == [str(path), str(path)]


@pytest.mark.parametrize("change", ["duplicate", "extra", "extra_read", "missing_read",
                                    "missing_field", "bool_int", "wrong_policy", "bool_expiry",
                                    "malformed_producer", "past_expiry", "float_expiry",
                                    "nonfinite", "bad_bounds_age", "bad_bounds_zero",
                                    "bad_bounds_refresh", "v1_with_read", "unknown_schema", "millisecond_expiry", "excessive_expiry"])
def test_selected_owner_closed_schema_and_values_refuse(tmp_path, change):
    from tests.research_read_mcp.test_runtime import parsed
    deployment = parsed()
    top, read, valid_until = None, None, None
    if change == "duplicate":
        raw = json.dumps(selected_owner_value(tmp_path)).replace(
            '"max_age_seconds": 3600', '"max_age_seconds": 3600, "max_age_seconds": 3600', 1)
        path = selected_owner_config(tmp_path, raw=raw)
    elif change == "extra":
        top = {"issuer": "https://extra.invalid/"}
    elif change == "extra_read":
        read = {"selection_scope": "synthetic-forbidden"}
    elif change == "missing_read":
        top, read = {"selected_read": None}, "drop"
        value = selected_owner_value(tmp_path)
        del value["selected_read"]
        path = selected_owner_config(tmp_path, raw=json.dumps(value))
    elif change == "missing_field":
        value = selected_owner_value(tmp_path)
        del value["selected_read"]["image_admission_bytes"]
        path = selected_owner_config(tmp_path, raw=json.dumps(value))
    elif change == "bool_int":
        read = {"writer_protocol_qualified": 1}
    elif change == "wrong_policy":
        read = {"writer_protocol_qualified": False}
    elif change == "bool_expiry":
        read = {"valid_until": True}
    elif change == "malformed_producer":
        read = {"expected_producer_commit": "B" * 40}
    elif change == "past_expiry":
        valid_until = int(identity._wall_now()) - 1
    elif change == "millisecond_expiry":
        valid_until = int(identity._wall_now()) * 1000
    elif change == "excessive_expiry":
        valid_until = 2 ** 62
    elif change == "float_expiry":
        valid_until = float(int(identity._wall_now())) + 3600.0
    elif change == "nonfinite":
        path = selected_owner_config(
            tmp_path, raw=json.dumps(selected_owner_value(tmp_path)).replace(
                '"valid_until": ', '"valid_until": Infinity,"x": ', 1))
    elif change == "bad_bounds_age":
        read = {"max_age_seconds": 3601}
    elif change == "bad_bounds_zero":
        read = {"corpus_byte_budget": 0}
    elif change == "bad_bounds_refresh":
        read = {"refresh_interval_seconds": 301}
    elif change == "v1_with_read":
        top = {"schema": identity.ARCHIVE_OWNER_SCHEMA}
    elif change == "unknown_schema":
        top = {"schema": "mastermind.research_read_archive_owner.v3"}
    if change not in ("duplicate", "missing_read", "missing_field", "nonfinite"):
        path = selected_owner_config(tmp_path, top=top, read=read, valid_until=valid_until)
    with pytest.raises(RuntimeRefused):
        identity.load_archive_verifier(str(path), deployment, owner_uid=os.geteuid())


def test_selected_owner_binding_refuses_past_valid_until(tmp_path, monkeypatch):
    from tests.research_read_mcp.test_runtime import parsed
    path = selected_owner_config(tmp_path)
    monkeypatch.setattr(identity, "_wall_now",
                        lambda: selected_owner_value(tmp_path)["selected_read"]["valid_until"])
    with pytest.raises(RuntimeRefused):
        identity.load_archive_verifier(str(path), parsed(), owner_uid=os.geteuid())


@pytest.mark.parametrize("change", ["deleted", "insecure", "mutated", "reformatted", "expiry_boundary", "expired", "restored"])
def test_owner_file_lifecycle_denies_writer_policy(tmp_path, monkeypatch, change):
    from tests.research_read_mcp.test_runtime import parsed
    path = selected_owner_config(tmp_path)
    monkeypatch.setattr(identity, "verify_archive_release", lambda *a, **k: None)
    options = identity.load_archive_verifier(str(path), parsed(),
                                             owner_uid=os.geteuid()).selected_options
    policy = options.writer_policy
    assert policy() is True
    if change == "deleted":
        path.unlink()
    elif change == "insecure":
        path.chmod(0o644)
    elif change == "mutated":
        selected_owner_config(tmp_path, read={"max_age_seconds": 1800})
    elif change == "reformatted":
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
    elif change == "expiry_boundary":
        expiry = json.loads(path.read_text())["selected_read"]["valid_until"]
        monkeypatch.setattr(identity, "_wall_now", lambda: expiry)
    elif change == "expired":
        monkeypatch.setattr(identity, "_wall_now", lambda: 2 ** 40)
    elif change == "restored":
        admitted = path.read_bytes()
        path.unlink()
        assert policy() is False
        path.write_bytes(admitted)
        path.chmod(0o600)
    if change != "restored":
        assert policy() is False
    # Observed withdrawal is final for this process, even for identical bytes.
    assert policy() is False


@pytest.mark.parametrize("seconds, admitted", [(86400, True), (86401, False)])
def test_selected_owner_expiry_horizon(tmp_path, monkeypatch, seconds, admitted):
    from tests.research_read_mcp.test_runtime import parsed
    monkeypatch.setattr(identity, "_wall_now", lambda: 2_000_000_000)
    path = selected_owner_config(tmp_path, valid_until=2_000_000_000 + seconds)
    if admitted:
        assert identity.load_archive_verifier(str(path), parsed(), owner_uid=os.geteuid()).selected_options.writer_policy()
    else:
        with pytest.raises(RuntimeRefused):
            identity.load_archive_verifier(str(path), parsed(), owner_uid=os.geteuid())
