"""Additive, configuration-bound fourth Codex Personal Pro realm.

Source-only: no OS principal provisioning, no provider credential, no launchd,
no socket, no account quota, no Executive/Fabric claim, no model turn.
"""
from copy import deepcopy
from pathlib import Path

import pytest
from ops.executive_os.provider_worker_slots import (
    SlotCatalogError, all_slots, get_slot, native_slot_from_config,
)
from ops.executive_os.provider_identity_policy import (
    PERSONAL_PRO_WORKER_BINDING_CLASS,
)


def candidate():
    return {
        "native_provider": "codex",
        "worker_uid": 470, "worker_gid": 470,
        "control_uid": 450,
        "worker_user": "_mastermind_codex_04",
        "provider_home": "/var/db/mastermind-executive/workers/codex-pro-04/provider-home",
        "native_realm_enrollment": {"slot_id": "codex-pro-04"},
    }


def test_c4_config_bound_source_candidate_uses_incumbent_native_realm_owner():
    slot=native_slot_from_config(candidate())
    assert slot.slot_id=="codex-pro-04"
    assert slot.oauth_seat_ref=="chatgpt4"
    assert slot.workspace_binding_class==PERSONAL_PRO_WORKER_BINDING_CLASS
    assert slot.allowed_credential_kinds==("device-auth",)
    assert slot.provider_family=="openai"
    assert slot.worker_uid==470 and slot.worker_gid==470
    assert slot.worker_user==slot.worker_group=="_mastermind_codex_04"
    assert str(slot.provider_home)==candidate()["provider_home"]
    assert slot.readiness_receipt==Path(
        "/Library/Application Support/MastermindExecutive/config/provider-readiness-codex-pro-04-v2.json")
    assert slot.auth_path==slot.provider_home/"auth.json"
    # Static H0 three-personal source and normal get_slot remain unchanged.
    assert len(all_slots())==4
    with pytest.raises(SlotCatalogError,match="unknown_slot"):
        get_slot("codex-pro-04")


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(native_provider="openai"),
    lambda c: c.update(native_provider="claude"),
    lambda c: c["native_realm_enrollment"].update(slot_id="codex-pro-05"),
    lambda c: c["native_realm_enrollment"].update(slot_id="codex-business-02"),
    lambda c: c.update(worker_user="_mastermind_codex_01"),
    lambda c: c.update(worker_user="root"),
    lambda c: c.update(worker_uid=454,worker_gid=454),
    lambda c: c.update(worker_uid=451,worker_gid=451),
    lambda c: c.update(worker_uid=450,worker_gid=450),
    lambda c: c.update(worker_gid=471),
    lambda c: c.update(worker_uid=False),
    lambda c: c.update(worker_gid="470"),
    lambda c: c.update(control_uid=451),
    lambda c: c.update(provider_home="/Users/m2/.mastermind/fabric-codex-homes/C4"),
    lambda c: c.pop("native_realm_enrollment"),
])
def test_unreviewed_codex_pro04_config_refuses_without_fallback(mutate):
    config=candidate()
    mutate(config)
    with pytest.raises(SlotCatalogError):
        native_slot_from_config(config)


def test_existing_claude_and_company_slot_catalog_not_widened():
    rows=all_slots()
    assert tuple(r.slot_id for r in rows)==(
        "codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03")
    assert all(row.worker_uid not in {470} for row in rows)
    # The actual UID is read from a trusted host config, NEVER defaulted by source.
    without_uid=candidate()
    without_uid.pop("worker_uid")
    with pytest.raises(SlotCatalogError):
        native_slot_from_config(without_uid)


def test_c4_config_record_does_not_impersonate_ready_worker_or_authorize_login():
    row=native_slot_from_config(candidate())
    rendered=row.public_descriptor()
    assert "@" not in str(rendered) and "account_id" not in str(rendered)
    assert "provider_home" not in rendered
    assert not hasattr(row,"quota") and not hasattr(row,"lease")
    assert not hasattr(row,"admission_granted")


def enrolled_candidate():
    from control_plane.codex_provider_realm import NATIVE_REALM_ENROLLMENT_SCHEMA
    row=candidate()
    row["native_realm_enrollment"].update({
        "schema_version":NATIVE_REALM_ENROLLMENT_SCHEMA,
        "host_ref":"host-"+"a"*64,
        "os_principal_ref":"principal-"+"b"*64,
        "config_custody_ref":"custody-"+"c"*64,
        "generation":1,"enrollment_state":"enrolled",
        "provider_binary_sha256":"d"*64,
    })
    return row


def test_existing_native_realm_identity_owner_resolves_only_explicit_fourth_codex_slot(monkeypatch):
    from control_plane import codex_provider_realm as realm
    # Keep source-only test structural: path/UID/owner custody checks are
    # independently enforced in NativeRealmIdentityOwner.observe.
    monkeypatch.setattr(realm,"_native_canonical_home",lambda path:Path(path))
    config=enrolled_candidate()
    enrollment,slot=realm._native_enrollment(config)
    assert enrollment["enrollment_state"]=="enrolled"
    assert slot.slot_id=="codex-pro-04"
    assert slot.oauth_seat_ref=="chatgpt4"
    assert slot.workspace_binding_class==PERSONAL_PRO_WORKER_BINDING_CLASS
    assert len(all_slots())==4


@pytest.mark.parametrize("bad", [
    "unenrolled","wrong_binary","wrong_home","wrong_user","missing_custody",
])
def test_native_codex_fourth_slot_enrollment_refuses_drift(monkeypatch,bad):
    from control_plane import codex_provider_realm as realm
    monkeypatch.setattr(realm,"_native_canonical_home",lambda path:Path(path))
    config=enrolled_candidate()
    if bad=="unenrolled":config["native_realm_enrollment"]["enrollment_state"]="unenrolled"
    elif bad=="wrong_binary":config["native_realm_enrollment"]["provider_binary_sha256"]="invalid"
    elif bad=="wrong_home":config["provider_home"]="/var/db/mastermind-executive/workers/codex-pro-03/provider-home"
    elif bad=="wrong_user":config["worker_user"]="_mastermind_codex_01"
    elif bad=="missing_custody":config["native_realm_enrollment"].pop("config_custody_ref")
    with pytest.raises(realm.ProviderRealmError,match="NATIVE_REALM_IDENTITY_UNAVAILABLE"):
        realm._native_enrollment(config)
