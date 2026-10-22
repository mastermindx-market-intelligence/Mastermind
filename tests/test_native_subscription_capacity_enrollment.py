"""Root-source/realm composition, with only OS ownership boundaries virtualized."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import types

import pytest

from control_plane import codex_provider_realm as realm
from ops.executive_os import capacity_source_contract as source
from tests.test_subscription_realm_owner import enrolled
from tests.test_attended_worker_definition import inputs


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def bound(enrolled, monkeypatch, tmp_path):
    f = enrolled
    f.config.update(worker_id="minimax-finite-01", worker_user="_mastermind_minimax",
        worker_uid=470, worker_gid=470, control_gid=450,
        harness_binding_id="minimax-token-plan.claude-code-anthropic",
        subscription_realm_enrollment={"generation": 2, "binding_id": "minimax-token-plan.claude-code-anthropic"})
    # Existing fixture owns actual private credential and config read checks.
    # Virtualize only dedicated UID/GID and the attested executable boundary.
    from contextlib import contextmanager
    original_open = realm._native_open
    @contextmanager
    def root_open(path, **kw):
        try:
            with original_open(path, **kw) as (fd, info):
                if kw.get("directory"):
                    info = types.SimpleNamespace(st_uid=470, st_gid=470, st_mode=info.st_mode)
                yield fd, info
        except OSError:
            raise realm.ProviderRealmError("NATIVE_REALM_IDENTITY_UNAVAILABLE") from None
    monkeypatch.setattr(realm, "_native_open", root_open)
    for name in ("getuid", "geteuid", "getgid", "getegid"):
        monkeypatch.setattr(realm.os, name, lambda: 470)
    monkeypatch.setattr(realm.os, "getgroups", lambda: [470])
    monkeypatch.setattr(realm.pwd, "getpwuid", lambda _: types.SimpleNamespace(
        pw_name="_mastermind_minimax", pw_gid=470, pw_dir=str(f.home)))
    monkeypatch.setattr(realm, "_observe_attended_claude_binary", lambda config, gid: None)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(source, "SYSTEM_ROOT", tmp_path / "system")
    row = {"schema": "mastermind.provider_native_capability_registration/v1",
        "capacity_capability_id": "cap.fixture", "capability_generation": 3,
        "provider": "minimax", "billing_mode": "subscription", "credential_kind": "api_key",
        "execution_surface": "native_cli", "registration_state": "registered", "material_source_digest": "a"*64}
    row["registration_receipt_digest"] = sha(encode(row))
    document = {"repository_commit": "b"*40, "previous_repository_commit": "c"*40,
                "material_source_digest": "a"*64, "registrations": [row]}
    export = source.SYSTEM_ROOT / "config/capacity-source-components-native-v2" / (("b"*40) + ".json")
    export.parent.mkdir(parents=True)
    f.config["capacity_capability_id"] = "cap.fixture"
    f.config["native_capacity_enrollment"] = {
        "schema_version": "mastermind.native_subscription_capacity_enrollment/v1",
        "host_ref": "host-"+"1"*64, "os_principal_ref": "principal-"+"2"*64,
        "config_custody_ref": "custody-"+"3"*64, "enrollment_state": "enrolled",
        "registration_source": {"release_commit": "b"*40, "previous_release_commit": "c"*40,
                                "material_source_digest": "a"*64, "export_sha256": ""}}
    def publish():
        export.write_bytes(encode(document))
        f.config["native_capacity_enrollment"]["registration_source"]["export_sha256"] = sha(export.read_bytes())
        return f.load()
    return types.SimpleNamespace(f=f, document=document, row=row, export=export, publish=publish)


def test_actual_realm_and_source_owners_compose_closed_enrollment(bound, monkeypatch):
    owner = bound.publish()
    import os
    read = os.read
    credential_inode = bound.f.credential.stat().st_ino
    def no_secret(fd, count):
        assert os.fstat(fd).st_ino != credential_inode
        return read(fd, count)
    monkeypatch.setattr(realm.os, "read", no_secret)
    receipt = owner.observe_capacity_enrollment()
    assert receipt["schema"] == "mastermind.provider_realm_enrollment/v2"
    assert receipt["capability_generation"] == 3 and receipt["realm_generation"] == 2
    assert receipt["auth_family"] == "minimax_subscription_api_key"
    assert receipt["provider_family"] == "minimax"
    assert receipt["registration_receipt_digest"] == bound.row["registration_receipt_digest"]
    unsigned = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    assert receipt["receipt_digest"] == sha(encode(unsigned))
    assert str(bound.f.home) not in json.dumps(receipt)
    assert "available" not in receipt and "capacity_generation" not in receipt


@pytest.mark.parametrize("edge", ["empty", "revoked", "wrong-id", "generation-bool", "digest",
    "duplicate", "extra-field", "wrong-source", "wrong-provider-type", "missing-export"])
def test_unqualified_registration_never_enrolls(bound, edge):
    if edge == "empty": bound.document["registrations"] = []
    if edge == "revoked": bound.row["registration_state"] = "revoked"
    if edge == "wrong-id": bound.f.config["capacity_capability_id"] = "other"
    if edge == "generation-bool": bound.row["capability_generation"] = True
    if edge == "digest": bound.row["registration_receipt_digest"] = "0"*64
    if edge == "duplicate": bound.document["registrations"].append(copy.deepcopy(bound.row))
    if edge == "extra-field": bound.row["secret"] = "never-project"
    if edge == "wrong-source": bound.document["repository_commit"] = "d"*40
    if edge == "wrong-provider-type": bound.row["provider"] = {}
    if edge != "digest":
        bound.row["registration_receipt_digest"] = sha(encode({k: v for k, v in bound.row.items()
                                                             if k != "registration_receipt_digest"}))
    owner = bound.publish()
    if edge == "missing-export": bound.export.unlink()
    with pytest.raises((source.CapacitySourceContractError, realm.ProviderRealmError)):
        owner.observe_capacity_enrollment()


@pytest.mark.parametrize("field,value", [("host_ref", "local-unbound"), ("os_principal_ref", "path/to/user"),
    ("config_custody_ref", "secret-ref"), ("enrollment_state", "unenrolled")])
def test_foreign_or_unenrolled_realm_refuses(bound, field, value):
    bound.f.config["native_capacity_enrollment"][field] = value
    with pytest.raises(realm.ProviderRealmError):
        bound.publish().observe_capacity_enrollment()


def test_public_hash_cannot_replace_root_export_custody(bound, monkeypatch):
    owner = bound.publish()
    monkeypatch.setattr(realm, "_native_open", bound.f.original_open)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe_capacity_enrollment()


def test_fake_owner_refused():
    with pytest.raises(source.CapacitySourceContractError, match="OWNER_REQUIRED"):
        source.acquire_native_registration(types.SimpleNamespace())


def test_export_changed_after_first_read_refuses(bound, monkeypatch):
    owner = bound.publish()
    read = realm._native_read_config
    seen = []
    def changed(path, digest):
        value = read(path, digest)
        if path == bound.export:
            seen.append(1)
            if len(seen) == 1:
                bound.export.write_text("{}")
        return value
    monkeypatch.setattr(realm, "_native_read_config", changed)
    with pytest.raises(realm.ProviderRealmError): owner.observe_capacity_enrollment()


def test_root_config_revocation_invalidates_collected_owner(bound):
    owner = bound.publish()
    bound.f.path.write_text("{}")
    with pytest.raises(realm.ProviderRealmError): owner.observe_capacity_enrollment()


def test_macro_checkout_location_is_never_used_as_projection_fallback(bound):
    owner = bound.publish()
    raw = bound.export.read_bytes()
    old = source.SYSTEM_ROOT / 'capacity-sources/macro' / ('b'*40) / 'native-registrations.json'
    old.parent.mkdir(parents=True)
    bound.export.rename(old)
    with pytest.raises(realm.ProviderRealmError):
        owner.observe_capacity_enrollment()
    assert old.read_bytes() == raw and not bound.export.exists()


def test_stanza_parser_detaches_source_and_rejects_overrides(bound):
    stanza = bound.f.config['native_capacity_enrollment']
    bound.publish()
    result = source.validate_native_subscription_capacity_enrollment(stanza)
    assert result == stanza and result is not stanza
    assert result['registration_source'] is not stanza['registration_source']
    for field, value in [('path', '/tmp/override'), ('capacity_generation', 999), ('realm_generation', 999)]:
        with pytest.raises(source.CapacitySourceContractError):
            source.validate_native_subscription_capacity_enrollment({**stanza, field: value})


def test_actual_finite_renderer_carries_stanza_into_strict_reader(inputs, tmp_path):
    from ops.executive_os.attended_worker_definition import build_finite_worker_artifacts
    from scripts.executive_os_phase1c_worker import _load_config
    stanza = {'schema_version': 'mastermind.native_subscription_capacity_enrollment/v1',
        'host_ref': 'host-'+'a'*64, 'os_principal_ref': 'principal-'+'b'*64,
        'config_custody_ref': 'custody-'+'c'*64, 'enrollment_state': 'enrolled',
        'registration_source': {'release_commit': 'd'*40, 'previous_release_commit': 'e'*40,
            'material_source_digest': 'f'*64, 'export_sha256': '1'*64}}
    artifacts = build_finite_worker_artifacts(**{**inputs, 'host_ref': stanza['host_ref'],
        'capacity_capability_id': 'cap.fixture', 'native_capacity_enrollment': stanza})
    path = tmp_path/'worker.json'
    path.write_bytes(artifacts['worker.json']); path.chmod(0o600)
    parsed = _load_config(path, require_root_owner=False)
    assert parsed['native_capacity_enrollment'] == stanza
    assert parsed['operator_harness_armed'] is False
    old = build_finite_worker_artifacts(**inputs)
    assert 'native_capacity_enrollment' not in json.loads(old['worker.json'])
    with pytest.raises(ValueError):
        build_finite_worker_artifacts(**{**inputs, 'capacity_capability_id': 'cap.fixture',
            'native_capacity_enrollment': {**stanza, 'host_ref': 'host-'+'2'*64}})
