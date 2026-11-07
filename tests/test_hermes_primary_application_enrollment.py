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
from test_go_native_stage import builds, native_stage, g, installer, loaded_entry, native_module_namespace
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import service_owner, prepare, selected_purpose, unchanged_ingress
from test_go_service_startup import environment, boot


@pytest.fixture(autouse=True)
def isolated_native_service_imports(native_stage):
    manifest = json.loads((native_stage / "native-manifest.json").read_bytes())
    with native_module_namespace(manifest, clean_yaml=True):
        yield


def test_service_enrollment_keeps_foreign_module_refusal(service_owner, monkeypatch):
    from types import ModuleType
    case = service_owner
    foreign = ModuleType("a04_terminal_reconcile")
    foreign.__file__ = str(case.root / "foreign-a04.py")
    monkeypatch.setitem(sys.modules, "a04_terminal_reconcile", foreign)
    with pytest.raises(ValueError, match="native Go module conflict: a04_terminal_reconcile"):
        prepare(case)
    assert not any(path.exists() for path in (case.intent, case.binding, case.service_receipt))


PROFILES = {
    "hermes-secretary": "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN",
    "hermes-meta-ceo": "HERMES_META_FABRIC_APPLICATION_TOKEN",
}


def routed_role(case, profile):
    select_role(case, profile)
    case.specification["scope"]["route_scope"] = {
        "schema": "mastermind.application_route_scope.v1", "pools": ["go"]}
    first = case.specification.pop("grant")
    second = copy.deepcopy(first)
    second.update(grant_id=first["grant_id"] + "-second", models=["fixture-second-model"])
    case.specification["grants"] = [first, second]


@pytest.mark.parametrize("profile", PROFILES)
def test_routed_role_uses_original_grants_and_one_physical_owner(service_owner, profile):
    case = service_owner
    routed_role(case, profile)
    accounts_before = json.loads(case.accounts.read_bytes())
    plan = prepare(case)
    assert plan["grant_sha256"] == g.digest(g.canonical(case.specification["grants"]))
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    accounts_after = json.loads(case.accounts.read_bytes())
    assert accounts_after == {**accounts_before, "application_grants": case.specification["grants"]}
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        (binding,), _, account_profile = entry.load_completed_application_startup(startup, profile)
        assert binding.route_scope == startup.handler.ApplicationRouteScope(case.specification["scope"]["route_scope"])
        assert binding.credential_ref == PROFILES[profile] and not binding.admin_pool_view
        assert account_profile == case.profile
    installed = accounts_after["application_grants"]
    assert installed == case.specification["grants"]
    assert len({tuple(row["accounts"]) for row in installed}) == 1


@pytest.mark.parametrize("mutation", ["mixed", "empty", "scope", "foreign_pool", "role", "overlap", "null_scope"])
def test_routed_role_refuses_foreign_authority_before_original_intent(service_owner, mutation):
    case = service_owner
    routed_role(case, "hermes-secretary")
    if mutation == "mixed": case.specification["grant"] = case.specification["grants"][0]
    elif mutation == "empty": case.specification["grants"] = []
    elif mutation == "scope": case.specification["scope"]["route_scope"]["pools"] = ["go", "go"]
    elif mutation == "foreign_pool": case.specification["grants"][0]["pool"] = "bailian"
    elif mutation == "role": case.specification["grants"][0]["principal_id"] = "hermes-meta-ceo"
    elif mutation == "overlap": case.specification["grants"][1] = copy.deepcopy(case.specification["grants"][0])
    else: case.specification["scope"]["route_scope"] = None
    with pytest.raises(ValueError): prepare(case)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()


def test_routed_grant_change_cannot_reuse_original_plan(service_owner, monkeypatch):
    case = service_owner
    routed_role(case, "hermes-secretary")
    prepare(case)
    spec = case.service_bundle / "specification.json"
    changed = json.loads(spec.read_bytes())
    changed["grants"][0]["models"].append("uncommitted-model")
    spec.write_bytes(g.canonical(changed) + b"\n")
    monkeypatch.setattr(installer.secrets, "token_urlsafe", lambda *args: pytest.fail("replacement credential"))
    with pytest.raises(ValueError): installer.apply_go_service_enrollment(case.service_bundle)
    assert not case.intent.exists() and not case.binding.exists()


def select_role(case, profile):
    case.specification = copy.deepcopy(case.specification)
    selected_purpose(case)
    case.specification["schema"] = installer.SERVICE_ROLE_SPEC_SCHEMA
    case.specification["operation_id"] = "fixture-enroll-" + profile
    attended = profile == "hermes-attended"
    credential_ref = "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN" if attended else PROFILES[profile]
    workload = "hermes_attended" if attended else "site_interactive"
    case.specification["scope"].update(service_profile=profile, principal_id=profile,
        capability_lane=profile, credential_ref=credential_ref,
        workload=workload, workload_profile=workload)
    case.specification["grant"].update(grant_id="fixture-" + profile, principal_id=profile,
        credential_ref=credential_ref, admission_root="service:" + profile,
        workloads=[workload])
    case.service_bundle = case.root / ("review-" + profile)
    case.binding = case.ext / "go_shim" / ("application-service-" + profile + ".json")
    case.intent = case.store / "bootstrap" / (".go-service-enrollment-" + profile + "-v9.json")
    case.service_receipt = case.store / "bootstrap" / ("go-service-enrollment-" + profile + "-v9.json")


@pytest.mark.parametrize("profile", [*PROFILES, "hermes-attended"])
def test_role_uses_original_enrollment_once_and_actual_startup(service_owner, monkeypatch, profile):
    case = service_owner
    select_role(case, profile)
    accounts_before = json.loads(case.accounts.read_bytes())
    plan = prepare(case)
    original_secret = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as generated:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert generated.call_count == 1
    assert plan["schema"] == "native-go-service-enrollment.v9"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v9"
    private = json.loads(case.binding.read_bytes())
    assert private["schema"] == "mastermind.native_go_application_service.v9"
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
        assert binding.principal_id == profile
        assert binding.credential_ref == case.specification["scope"]["credential_ref"]
        assert binding.workload == ("hermes_attended" if profile == "hermes-attended" else "site_interactive")
        assert binding.admin_pool_view is False
        if profile == "hermes-attended":
            candidate = ROOT / "ops/native_fabric/quota_continuity/candidate/native_go_entry.py"
            assert case.published.meta["files"][g.GO_ENTRY] == g.digest(candidate.read_bytes())
            assert Path(entry.__file__).resolve() == (case.published.release / g.GO_ENTRY).resolve()
            assert private["scope"]["workload_profile"] == "hermes_attended"
            assert private["scope"]["capability_lane"] == "hermes-attended"
            assert binding.credential_ref == "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN"
    accounts_after = json.loads(case.accounts.read_bytes())
    assert accounts_after == {**accounts_before, "application_grants": [case.specification["grant"]]}
    unchanged_ingress(case)


@pytest.mark.parametrize("field,value", [
    ("workload", "site_interactive"),
    ("workload_profile", "site_interactive"),
    ("credential_ref", "HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN"),
])
def test_attended_scope_refuses_borrowed_role_before_original_intent(service_owner, field, value):
    case = service_owner
    select_role(case, "hermes-attended")
    accounts_before = case.accounts.read_bytes()
    case.specification["scope"][field] = value
    # Keep the grant internally consistent so refusal proves the closed role
    # mapping, rather than only the generic scope/grant consistency check.
    if field == "workload":
        case.specification["grant"]["workloads"] = [value]
    elif field == "credential_ref":
        case.specification["grant"]["credential_ref"] = value
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("credential generated")):
        with pytest.raises(ValueError):
            prepare(case)
    assert case.accounts.read_bytes() == accounts_before
    assert not any(path.exists() for path in
                   (case.intent, case.binding, case.service_receipt, case.service_bundle))
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
        bindings, host, account_profile = entry.load_all_completed_application_startup(startup)
        legacy = entry.load_completed_application_startup(startup)
        assert len(legacy[0]) == 1 and legacy[0][0].principal_id == "macro-admin"
        assert [b.principal_id for b in bindings] == ["macro-admin", *PROFILES]
        assert len({b.credential for b in bindings}) == 3
        assert len({b.credential_ref for b in bindings}) == 3
        assert host == "fixture-native" and account_profile == case.profile
    grants = json.loads(case.accounts.read_bytes())["application_grants"]
    assert [g["principal_id"] for g in grants] == ["macro-admin", *PROFILES]
    assert all(g["accounts"] == ["account-a"] and g["models"] == ["fixture-model"] for g in grants)
    unchanged_ingress(case)


def test_completed_family_and_hermes_share_owners_without_changing_family_recovery(service_owner):
    from test_go_service_family_composition import family_specification, prepare_family
    case = service_owner
    family_specification(case)
    prepare_family(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    retained = {p: (p.read_bytes(), p.stat().st_ino)
                for p in (case.binding, case.intent, case.service_receipt)}
    for profile in PROFILES:
        select_role(case, profile)
        prepare(case)
        installer.apply_go_service_enrollment(case.service_bundle)
    assert {p: (p.read_bytes(), p.stat().st_ino) for p in retained} == retained
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        family = entry.load_completed_application_startup(startup)
        combined = entry.load_all_completed_application_startup(startup)
        assert len(family[0]) == 5 and len(combined[0]) == 7
        assert combined[0][:5] == family[0] and combined[1:] == family[1:]
    unchanged_ingress(case)


def test_family_upgrade_after_role_enrollment_uses_legacy_predecessor_only(service_owner):
    from test_go_service_family_composition import family_specification, prepare_family
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    previous = json.loads(case.binding.read_bytes())
    legacy = {name: getattr(case, name) for name in
              ("specification", "binding", "intent", "service_receipt")}
    select_role(case, "hermes-secretary")
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    retained = {p: (p.read_bytes(), p.stat().st_ino)
                for p in (case.binding, case.intent, case.service_receipt)}
    for name, value in legacy.items():
        setattr(case, name, value)
    case.service_bundle = case.root / "family-after-hermes"
    family_specification(case, previous)
    prepare_family(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    assert {p: (p.read_bytes(), p.stat().st_ino) for p in retained} == retained
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        assert len(entry.load_completed_application_startup(startup)[0]) == 5
        assert len(entry.load_all_completed_application_startup(startup)[0]) == 6
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


@pytest.mark.parametrize("schema", ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8"])
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
            entry.load_all_completed_application_startup(startup)


@pytest.mark.parametrize("collision", ["principal_id", "credential_ref", "credential", "host", "profile"])
def test_combination_refuses_cross_service_identity_or_owner_conflicts(service_owner, collision):
    case = service_owner
    select_role(case, "hermes-secretary")
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        original = entry.load_all_completed_application_startup(startup)
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
        with mock.patch.object(entry, "load_completed_application_startup", side_effect=read):
            with pytest.raises(ValueError):
                entry.load_all_completed_application_startup(startup)
