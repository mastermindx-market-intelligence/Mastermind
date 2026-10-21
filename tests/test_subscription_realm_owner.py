"""Worker-local subscription identity, private metadata and revocation."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import types

import pytest

from control_plane import codex_provider_realm as realm
from control_plane import codex_worker
from ops.executive_os import provider_worker_slots as slots


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    uid, gid = os.getuid(), os.getgid()
    root = tmp_path / "workers"
    home = root / "minimax-01" / "provider-home"
    home.mkdir(parents=True, mode=0o700)
    credential = home / realm.PROVIDER_CREDENTIAL_FILENAME
    credential.write_bytes(b"opaque-test-value")
    credential.chmod(0o600)
    binary, receipt = tmp_path / "codex", tmp_path / "receipt.json"
    binary.write_bytes(b"binary")
    binary.chmod(0o555)
    receipt.write_bytes(b"receipt")
    config_path = tmp_path / "worker.json"
    config = {
        "schema_version": "mastermind.executive_worker_broker_config/v5",
        "worker_id": "minimax-01", "worker_uid": 460, "worker_gid": 460,
        "control_uid": 450, "worker_user": "_mastermind_minimax_01",
        "provider_home": str(home), "harness_binding_id": "minimax-token-plan.codex-responses",
        "operator_harness_armed": False, "allowed_supplementary_gids": [],
        "subscription_realm_enrollment": {"generation": 2, "binding_id": "minimax-token-plan.codex-responses"},
        "codex_binary": str(binary), "codex_attestation_receipt": str(receipt),
        "allowed_codex_versions": ["0.154.0"], "required_team_identifier": "2DC432GLL2",
    }
    original_open = realm._native_open
    @contextmanager
    def virtual_root_open(path, *, directory=False, private_uid=None):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if directory:
            info = types.SimpleNamespace(st_uid=460, st_gid=460, st_mode=info.st_mode)
        try:
            yield descriptor, info
        finally:
            os.close(descriptor)
    monkeypatch.setattr(realm, "_native_open", virtual_root_open)
    private_open = realm._open_regular_credential
    monkeypatch.setattr(realm, "_open_regular_credential", lambda path, before, **_: private_open(path, before, expected_uid=uid, expected_gid=gid))
    monkeypatch.setattr(realm, "_has_macos_acl", lambda *a, **kw: False)
    monkeypatch.setattr(slots, "RUNTIME_WORKER_ROOT", root)
    for key in ("getuid", "geteuid", "getgid", "getegid"):
        monkeypatch.setattr(realm.os, key, lambda: 460)
    monkeypatch.setattr(realm.os, "getgroups", lambda: [460])
    monkeypatch.setattr(realm.pwd, "getpwuid", lambda _: types.SimpleNamespace(pw_name=config["worker_user"], pw_gid=460, pw_dir=str(home)))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(codex_worker, "load_codex_attestation_receipt", lambda *a, **kw: types.SimpleNamespace(version="0.154.0", team_identifier="2DC432GLL2"))
    def load():
        raw = json.dumps(config).encode()
        config_path.write_bytes(raw)
        return realm.load_subscription_realm_owner(config_path, expected_config_sha256=hashlib.sha256(raw).hexdigest())
    return types.SimpleNamespace(home=home, credential=credential, config=config, path=config_path,
                                 load=load, original_open=original_open)


def test_worker_observes_metadata_without_reading_secret(enrolled, monkeypatch):
    read = os.read
    inode = enrolled.credential.stat().st_ino
    def guarded_read(fd, count):
        assert os.fstat(fd).st_ino != inode, "owner must not read credential bytes"
        return read(fd, count)
    monkeypatch.setattr(realm.os, "read", guarded_read)
    owner = enrolled.load()
    value = owner.observe()
    assert value["worker_id"] == "minimax-01"
    assert value["realm_generation"] == 2
    assert value["control_uid"] == 450
    assert "opaque-test-value" not in json.dumps(value)
    assert str(enrolled.home) not in json.dumps(value)


def test_root_config_revocation_refuses_old_owner(enrolled):
    owner = enrolled.load()
    enrolled.path.write_text("{}")
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


@pytest.mark.parametrize("change", ["missing", "public", "symlink", "empty"])
def test_bad_credential_metadata_refuses(enrolled, change):
    owner = enrolled.load()
    if change == "missing":
        enrolled.credential.unlink()
    elif change == "public":
        enrolled.credential.chmod(0o644)
    elif change == "empty":
        enrolled.credential.write_bytes(b"")
    else:
        enrolled.credential.unlink()
        enrolled.credential.symlink_to(enrolled.path)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


@pytest.mark.parametrize("field,value", [
    ("worker_uid", 450), ("operator_harness_armed", True),
    ("harness_binding_id", "other"), ("required_team_identifier", "OTHER"),
    ("subscription_realm_enrollment", {"generation": True, "binding_id": "minimax-token-plan.codex-responses"}),
])
def test_wrong_root_identity_or_generation_refuses(enrolled, field, value):
    enrolled.config[field] = value
    with pytest.raises(realm.ProviderRealmError):
        enrolled.load()


def test_wrong_process_home_or_groups_refuses(enrolled, monkeypatch):
    owner = enrolled.load()
    monkeypatch.setenv("CODEX_HOME", str(enrolled.home.parent))
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()
    monkeypatch.setenv("CODEX_HOME", str(enrolled.home))
    monkeypatch.setattr(realm.os, "getgroups", lambda: [460, 20])
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_real_filesystem_refuses_user_owned_config(enrolled, monkeypatch):
    enrolled.load()
    monkeypatch.setattr(realm, "_native_open", enrolled.original_open)
    with pytest.raises(realm.ProviderRealmError):
        realm.load_subscription_realm_owner(enrolled.path, expected_config_sha256=hashlib.sha256(enrolled.path.read_bytes()).hexdigest())
