"""Hermes roles compose through the original finite APPLICATION publisher.

Disposable owners only. The incumbent fixture guards network/process/private
owner access and exercises the actual sealed source, installer and startup.
"""
import copy
import json
from pathlib import Path
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/native_fabric/quota_continuity/tests"))
from test_go_native_stage import builds, native_stage, g, installer, loaded_entry
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import service_owner, prepare, selected_purpose, unchanged_ingress
from test_go_service_startup import environment, boot


PROFILES = {
    "hermes-secretary": "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN",
    "hermes-meta-ceo": "HERMES_META_FABRIC_APPLICATION_TOKEN",
}


def select_role(case, profile):
    case.specification = copy.deepcopy(case.specification)
    selected_purpose(case)
    case.specification["schema"] = installer.SERVICE_ROLE_SPEC_SCHEMA
    case.specification["operation_id"] = "fixture-enroll-" + profile
    case.specification["scope"].update(service_profile=profile, principal_id=profile,
        capability_lane=profile, credential_ref=PROFILES[profile], workload="site_interactive")
    case.specification["grant"].update(grant_id="fixture-" + profile, principal_id=profile,
        credential_ref=PROFILES[profile], admission_root="service:" + profile,
        workloads=["site_interactive"])
    case.service_bundle = case.root / ("review-" + profile)
    case.binding = case.ext / "go_shim" / ("application-service-" + profile + ".json")
    case.intent = case.store / "bootstrap" / (".go-service-enrollment-" + profile + "-v5.json")
    case.service_receipt = case.store / "bootstrap" / ("go-service-enrollment-" + profile + "-v5.json")


@pytest.mark.parametrize("profile", PROFILES)
def test_role_uses_original_enrollment_once_and_actual_startup(service_owner, monkeypatch, profile):
    case = service_owner
    select_role(case, profile)
    plan = prepare(case)
    original_secret = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as generated:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert generated.call_count == 1
    assert plan["schema"] == "native-go-service-enrollment.v5"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v5"
    private = json.loads(case.binding.read_bytes())
    assert private["schema"] == "mastermind.native_go_application_service.v5"
    assert private["scope"] == plan["scope"] == receipt["scope"]
    assert private["credential"] not in json.dumps([plan, receipt])
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        captured = {}
        def original_main(**kwargs):
            captured.update(kwargs)
            assert type(kwargs["application_broker"]) is startup.broker_module.Broker
            assert Path(kwargs["application_broker"].db_path) == case.ext / "broker/leases.sqlite"
            return 73
        with mock.patch.object(startup.handler, "main", side_effect=original_main):
            assert boot(entry, case) == 73
        binding, = captured["application_services"]
        assert binding.principal_id == profile and binding.credential_ref == PROFILES[profile]
        assert binding.admin_pool_view is False
    unchanged_ingress(case)


def test_legacy_and_both_roles_preserve_original_artifacts_and_physical_owner(service_owner):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    retained = {p: (p.read_bytes(), p.stat().st_ino) for p in (case.binding, case.intent, case.service_receipt)}
    for profile in PROFILES:
        select_role(case, profile)
        prepare(case)
        installer.apply_go_service_enrollment(case.service_bundle)
    assert {p: (p.read_bytes(), p.stat().st_ino) for p in retained} == retained
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        bindings, host, account_profile = entry.load_completed_application_startup(startup)
        assert [b.principal_id for b in bindings] == ["macro-admin", *PROFILES]
        assert len({b.credential for b in bindings}) == 3
        assert len({b.credential_ref for b in bindings}) == 3
        assert host == "fixture-native" and account_profile == case.profile
    grants = json.loads(case.accounts.read_bytes())["application_grants"]
    assert [g["principal_id"] for g in grants] == ["macro-admin", *PROFILES]
    assert all(g["accounts"] == ["account-a"] and g["models"] == ["fixture-model"] for g in grants)
    unchanged_ingress(case)


@pytest.mark.parametrize("field,value", [
    ("service_profile", "../macro"), ("service_profile", "hermes-meta-ceo"),
    ("principal_id", "macro-admin"), ("capability_lane", "hermes-meta-ceo"),
    ("credential_ref", "MACRO_FABRIC_APPLICATION_TOKEN"),
    ("credential_ref", "HERMES_META_FABRIC_APPLICATION_TOKEN"),
    ("workload", "admin-site-interactive"), ("admin_pool_view", True),
    ("binding_path", "/tmp/unowned-binding"),
])
def test_role_substitution_refuses_before_intent_and_credential(service_owner, field, value):
    case = service_owner
    select_role(case, "hermes-secretary")
    case.specification["scope"][field] = value
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("credential read")):
        with pytest.raises(ValueError):
            prepare(case)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_bundle.exists()


@pytest.mark.parametrize("schema", ["v1", "v2", "v3", "v4"])
def test_role_fields_do_not_relax_historical_schemas(service_owner, schema):
    case = service_owner
    select_role(case, "hermes-secretary")
    case.specification["schema"] = "native-go-service-enrollment-specification." + schema
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.intent.exists()


def test_lost_binding_rename_ack_recovers_original_credential_and_inode(service_owner):
    case = service_owner
    select_role(case, "hermes-secretary")
    prepare(case)
    original_replace, original_secret = installer.os.replace, installer.secrets.token_urlsafe
    renamed = []
    def replace(source, target):
        original_replace(source, target)
        if Path(target) == case.binding and not renamed:
            renamed.append(case.binding.stat().st_ino)
            raise OSError("fixture lost original rename acknowledgement")
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as generated:
        with mock.patch.object(installer.os, "replace", side_effect=replace):
            with pytest.raises(OSError, match="original rename"):
                installer.apply_go_service_enrollment(case.service_bundle)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "partial"
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert generated.call_count == 1 and case.binding.stat().st_ino == renamed[0]
    assert receipt == installer.reconcile_go_service_enrollment(case.service_bundle)


def test_partial_role_never_disappears_behind_completed_legacy(service_owner):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    select_role(case, "hermes-secretary")
    case.intent.write_text("{}")
    case.intent.chmod(0o600)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        with pytest.raises(ValueError, match="incomplete"):
            entry.load_completed_application_startup(startup)


@pytest.mark.parametrize("collision", ["principal_id", "credential_ref", "credential", "host", "profile"])
def test_combination_refuses_cross_service_identity_or_owner_conflicts(service_owner, collision):
    case = service_owner
    select_role(case, "hermes-secretary")
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        original = entry.load_completed_application_startup(startup)
        from dataclasses import replace
        changes = dict(principal_id="other-principal", credential_ref="OTHER_INTERNAL_TOKEN",
                       credential="fixture-distinct-service-credential-0123456789")
        if collision in changes:
            changes[collision] = getattr(original[0][0], collision)
        duplicate = ((replace(original[0][0], **changes),),
                     "another-native-host" if collision == "host" else original[1],
                     Path("/another/accounts.json") if collision == "profile" else original[2])
        def read(_, profile=None):
            return original if profile is None else duplicate if profile == "hermes-secretary" else ((), None, None)
        with mock.patch.object(entry, "_load_completed_application_startup", side_effect=read):
            with pytest.raises(ValueError):
                entry.load_completed_application_startup(startup)
