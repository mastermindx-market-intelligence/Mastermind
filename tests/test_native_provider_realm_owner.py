"""Native owner joins, revocation, and filesystem boundary regression tests."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

from control_plane import codex_provider_realm as realm
from ops.executive_os import provider_worker_slots as slots


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    """Virtual root custody only; real config/binary bytes and mutation races."""
    home = tmp_path / "provider-home"
    home.mkdir(mode=0o700)
    (home / ".claude").mkdir(mode=0o700)
    binary = tmp_path / "claude"
    binary.write_bytes(b"native-binary-v1")
    binary.chmod(0o555)
    config_path = tmp_path / "worker.json"
    slot = dataclasses.replace(slots.get_slot("claude8-native-01"), provider_home=home)
    monkeypatch.setattr(slots, "get_slot", lambda identifier: slot if identifier == slot.slot_id else
                        (_ for _ in ()).throw(slots.SlotCatalogError("unknown_slot")))
    config = {
        "worker_uid": 459, "worker_gid": 459, "worker_user": slot.worker_user,
        "provider_home": str(home), "claude_binary": str(binary),
        "allowed_supplementary_gids": [],
        "native_realm_enrollment": {
            "schema_version": realm.NATIVE_REALM_ENROLLMENT_SCHEMA,
            "slot_id": slot.slot_id, "host_ref": "host-" + "a" * 64,
            "os_principal_ref": "principal-" + "b" * 64,
            "config_custody_ref": "custody-" + "c" * 64,
            "generation": 1, "enrollment_state": "enrolled",
            "provider_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        },
    }
    original_open = realm._native_open
    @contextmanager
    def virtual_root_open(path, *, directory=False, private_uid=None):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if directory:
            info = types.SimpleNamespace(st_uid=459, st_gid=459, st_mode=info.st_mode)
        try:
            yield descriptor, info
        finally:
            os.close(descriptor)
    monkeypatch.setattr(realm, "_native_open", virtual_root_open)
    for name in ("getuid", "geteuid", "getgid", "getegid"):
        monkeypatch.setattr(realm.os, name, lambda: 459)
    monkeypatch.setattr(realm.os, "getgroups", lambda: [459])
    principal = types.SimpleNamespace(pw_name=slot.worker_user, pw_gid=459, pw_dir=str(home))
    monkeypatch.setattr(realm.pwd, "getpwuid", lambda _: principal)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    def load():
        raw = json.dumps(config).encode()
        config_path.write_bytes(raw)
        return realm.load_native_realm_owner(config_path, expected_config_sha256=hashlib.sha256(raw).hexdigest())
    return types.SimpleNamespace(config=config, path=config_path, load=load,
                                 binary=binary, home=home, principal=principal,
                                 original_open=original_open)


def test_real_process_join_returns_only_secret_free_identity(enrolled):
    owner = enrolled.load()
    observation = owner.observe()
    assert observation.generation == 1
    assert observation.slot_id == "claude8-native-01"
    assert owner.require_current_identity(observation.host_ref, observation.os_principal_ref) is None
    rendered = json.dumps(dataclasses.asdict(observation))
    assert str(enrolled.home) not in rendered
    assert "credentials" not in rendered
    assert "WORKER_BROKER" not in rendered


@pytest.mark.parametrize("field,value", [
    ("schema_version", "unknown"), ("slot_id", "claude8-native-02"),
    ("host_ref", "host-localhostname"), ("os_principal_ref", "principal-459"),
    ("config_custody_ref", "/private/credentials"),
    ("generation", True), ("generation", 0), ("generation", 2**63),
    ("enrollment_state", "unenrolled"), ("provider_binary_sha256", "bad"),
])
def test_unowned_or_revoked_enrollment_refuses(enrolled, field, value):
    enrolled.config["native_realm_enrollment"][field] = value
    with pytest.raises(realm.ProviderRealmError, match="NATIVE_REALM_IDENTITY_UNAVAILABLE"):
        enrolled.load()


@pytest.mark.parametrize("field,value", [
    ("worker_uid", True), ("worker_uid", 501), ("worker_gid", 501),
    ("worker_user", "chriswong"), ("provider_home", "/Users/chriswong"),
])
def test_slot_config_cannot_select_another_principal(enrolled, field, value):
    enrolled.config[field] = value
    with pytest.raises(realm.ProviderRealmError):
        enrolled.load()


def test_unknown_enrollment_fields_refuse(enrolled):
    enrolled.config["native_realm_enrollment"]["caller_ready"] = True
    with pytest.raises(realm.ProviderRealmError):
        enrolled.load()


@pytest.mark.parametrize("name", ["getuid", "geteuid", "getgid", "getegid"])
def test_actual_process_identity_must_match(enrolled, monkeypatch, name):
    owner = enrolled.load()
    monkeypatch.setattr(realm.os, name, lambda: 501)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_unadmitted_supplementary_group_refuses(enrolled, monkeypatch):
    owner = enrolled.load()
    monkeypatch.setattr(realm.os, "getgroups", lambda: [459, 80])
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


@pytest.mark.parametrize("field,value", [("pw_name", "other"), ("pw_dir", "/Users/other"), ("pw_gid", 80)])
def test_current_directory_service_join_must_match(enrolled, field, value):
    owner = enrolled.load()
    setattr(enrolled.principal, field, value)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


@pytest.mark.parametrize("variable", ["HOME", "CLAUDE_CONFIG_DIR"])
def test_environment_cannot_select_shared_account(enrolled, monkeypatch, variable):
    owner = enrolled.load()
    monkeypatch.setenv(variable, "/Users/shared")
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_named_identity_cannot_be_substituted(enrolled):
    owner = enrolled.load()
    with pytest.raises(realm.ProviderRealmError):
        owner.require_current_identity("host-" + "d" * 64, "principal-" + "b" * 64)


def test_revocation_invalidates_already_loaded_callback(enrolled):
    owner = enrolled.load()
    enrolled.config["native_realm_enrollment"]["enrollment_state"] = "unenrolled"
    enrolled.path.write_text(json.dumps(enrolled.config))
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_binary_replacement_invalidates_owner(enrolled):
    owner = enrolled.load()
    enrolled.binary.unlink()
    enrolled.binary.write_bytes(b"native-binary-v2")
    enrolled.binary.chmod(0o555)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_private_config_permissions_are_checked(enrolled):
    owner = enrolled.load()
    (enrolled.home / ".claude").chmod(0o755)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe()


def test_no_credentials_are_opened(enrolled, monkeypatch):
    owner = enrolled.load()
    original = os.open
    def observed(path, *args, **kwargs):
        assert ".credentials.json" not in str(path)
        assert "auth.json" not in str(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", observed)
    owner.observe()


def test_duplicate_json_is_not_enrollment(enrolled):
    raw = b'{"native_realm_enrollment":{},"native_realm_enrollment":{}}'
    enrolled.path.write_bytes(raw)
    with pytest.raises(realm.ProviderRealmError):
        realm.load_native_realm_owner(enrolled.path, expected_config_sha256=hashlib.sha256(raw).hexdigest())


def test_direct_constructor_cannot_mint_owner(enrolled):
    with pytest.raises(realm.ProviderRealmError):
        realm.NativeRealmIdentityOwner(enrolled.path, "0" * 64, object()).observe()


def test_unprivileged_filesystem_is_not_root_enrollment(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")
    with pytest.raises(realm.ProviderRealmError):
        with realm._native_open(path):
            pytest.fail("untrusted ancestor accepted")


def test_lexical_path_refuses_parent_traversal():
    with pytest.raises(realm.ProviderRealmError):
        realm._native_path("/Library/../Users/other")


def test_native_slot_does_not_widen_legacy_codex_install_inventory():
    assert len(slots.all_slots()) == 4
    assert len(slots.native_slots()) == 5
    native = slots.get_slot("claude8-native-01")
    assert native.worker_uid == native.worker_gid == 459
    assert native.auth_path.name == ".credentials.json"
    assert native.provider_family == "anthropic"


def test_root_walk_does_not_require_listing_permission(tmp_path, monkeypatch):
    """Exercise the real walker and FD ACL join, with virtual root metadata."""
    import stat
    actual_open, actual_fstat, actual_stat = os.open, os.fstat, os.stat
    path = tmp_path / "config.json"
    path.write_bytes(b"{}")
    seen = []
    def metadata(info):
        # Tests do not acquire root. Model the production root0711 ancestors,
        # retaining inode/time identity so replacement detection stays real.
        return types.SimpleNamespace(
            st_dev=info.st_dev, st_ino=info.st_ino,
            st_mode=(stat.S_IFDIR | 0o711) if stat.S_ISDIR(info.st_mode) else info.st_mode,
            st_uid=0, st_gid=0, st_nlink=info.st_nlink, st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns, st_ctime_ns=info.st_ctime_ns,
        )
    def opened(name, flags, *args, **kwargs):
        if flags & os.O_DIRECTORY:
            search_flag = 0x40000000 if realm.sys.platform == "darwin" else os.O_PATH
            assert flags & search_flag
        assert flags & os.O_NOFOLLOW
        seen.append(name)
        return actual_open(name, flags, *args, **kwargs)
    def acl(path, *, expected_identity, descriptor):
        assert actual_fstat(descriptor).st_ino == expected_identity.st_ino
        return False
    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "fstat", lambda fd: metadata(actual_fstat(fd)))
    monkeypatch.setattr(os, "stat", lambda *args, **kwargs: metadata(actual_stat(*args, **kwargs)))
    monkeypatch.setattr(realm, "has_macos_acl", acl)
    # Canonical tmp paths avoid macOS's OS-owned /var alias in this boundary test.
    with realm._native_open(path.resolve()) as (descriptor, _):
        assert os.read(descriptor, 2) == b"{}"
    assert path.name in seen
