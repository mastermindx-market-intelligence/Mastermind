"""V6 to V7 is one token-preserving, explicit-scope enrollment transaction."""
import copy
import json
import os
import time
from pathlib import Path
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, loaded_entry, installer, ROOT, g
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner, historical
from test_go_service_enrollment import service_owner, unchanged_ingress
from test_go_service_family_composition import (
    NAMES, family_specification, prepare_family, completed_predecessor)
from test_go_service_startup import environment, inspect, boot


def complete_v6(case):
    family_specification(case)
    prepare_family(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    previous = json.loads(case.binding.read_bytes())
    case.previous_bundle = case.service_bundle
    case.service_bundle = case.root / "service-routed-review"
    return previous


def routed_specification(case, previous, *, additions=False):
    specification = {"schema": installer.SERVICE_ROUTED_SPEC_SCHEMA,
                     "operation_id": "fixture-routed-five"}
    for name, scope in zip(NAMES, previous["scopes"]):
        scope = copy.deepcopy(scope)
        scope["route_scope"] = {"schema": "mastermind.application_route_scope.v1",
                                "pools": ["codex-native", "go"]}
        grants = []
        if additions:
            grant = copy.deepcopy(case.family[name]["grant"])
            grant.update(grant_id="new-routed-" + name, models=["additional-fixture-model"])
            grants.append(grant)
        specification[name] = {"scope": scope, "new_grants": grants}
    case.routed = specification
    return specification


def prepare_routed(case):
    return installer.prepare_go_service_enrollment(case.go_bundle, case.routed, case.service_bundle)


def targets(case):
    return {path: path.read_bytes() if path.exists() else None
            for path in (case.binding, case.intent, case.service_receipt, case.accounts)}


def test_scope_only_transition_preserves_five_credentials_and_exact_accounts(service_owner, monkeypatch):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous)
    before = case.accounts.read_bytes()
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("routed minted")):
        plan = prepare_routed(case)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "prepared"
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    document = json.loads(case.binding.read_bytes())
    assert document["schema"] == "mastermind.native_go_application_service.v7"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v7"
    assert plan["predecessor_schema"] == previous["schema"]
    assert len(plan["predecessor_credential_sha256s"]) == 5
    assert document["credentials"] == previous["credentials"]
    assert case.accounts.read_bytes() == before
    assert all(secret not in json.dumps(plan) + json.dumps(receipt) for secret in previous["credentials"])
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        services, host, profile = entry.load_completed_application_startup(startup)
        assert len(services) == 5 and [s.credential for s in services] == previous["credentials"]
        assert all(s.route_scope.document == case.routed[name]["scope"]["route_scope"]
                   for name, s in zip(NAMES, services))
        with mock.patch.object(startup.handler, "main", return_value=71) as main:
            assert boot(entry, case) == 71
            assert main.call_args.kwargs["application_services"] == services
    unchanged_ingress(case)


def test_explicit_additions_preserve_disabled_expired_narrowed_and_removed_rows(service_owner):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous, additions=True)
    accounts = json.loads(case.accounts.read_bytes())
    grants = accounts["application_grants"]
    grants[0]["enabled"] = False
    grants[1]["expires_at"] = time.time() - 20
    grants[2]["models"] = ["narrowed-original-model"]
    removed = grants.pop(3)
    case.accounts.write_text(json.dumps(accounts))
    retained = copy.deepcopy(grants)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("routed minted")):
        prepare_routed(case)
        installer.apply_go_service_enrollment(case.service_bundle)
    current = json.loads(case.accounts.read_bytes())
    expected = retained + [case.routed[name]["new_grants"][0] for name in NAMES]
    assert current["application_grants"] == expected
    assert removed not in current["application_grants"]
    assert current["operator_note"] == accounts["operator_note"]
    assert json.loads(case.binding.read_bytes())["credentials"] == previous["credentials"]


@pytest.mark.parametrize("schema", [None, "v1", "v5"])
def test_routed_requires_completed_five_identity_predecessor(service_owner, schema):
    case = service_owner
    previous = completed_predecessor(case, schema)
    family_specification(case, previous)
    scopes = [case.family[name]["scope"] for name in NAMES]
    routed_specification(case, {"scopes": scopes})
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("legacy minted")), \
            pytest.raises(ValueError, match="completed v6 predecessor"):
        prepare_routed(case)
    assert targets(case) == before


@pytest.mark.parametrize("fault", ["missing-role", "extra-role", "missing-new-grants", "implicit-grant",
    "missing-scope", "unknown-pool", "alias-pool", "duplicate-pool", "scope-secret",
    "identity", "account-owner", "admin-metadata", "changed-purpose", "wrong-reference"])
def test_routed_closed_grammar_and_retained_identity_refuse_without_effect(service_owner, fault):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous)
    spec = case.routed
    if fault == "missing-role":
        del spec["ask"]
    elif fault == "extra-role":
        spec["terminal"] = copy.deepcopy(spec["ask"])
    elif fault == "missing-new-grants":
        del spec["chat"]["new_grants"]
    elif fault == "implicit-grant":
        spec["chat"]["grant"] = copy.deepcopy(case.family["chat"]["grant"])
    elif fault == "missing-scope":
        del spec["chat"]["scope"]["route_scope"]
    elif fault in {"unknown-pool", "alias-pool", "duplicate-pool"}:
        spec["chat"]["scope"]["route_scope"]["pools"] = (
            ["unknown"] if fault == "unknown-pool" else ["codex"] if fault == "alias-pool" else ["go", "go"])
    elif fault == "scope-secret":
        spec["chat"]["scope"]["route_scope"]["account"] = "invented"
    elif fault == "identity":
        spec["chat"]["scope"]["principal_id"] = "replacement-chat"
    elif fault == "account-owner":
        for name in NAMES:
            spec[name]["scope"]["account_profile"] = "/tmp/different-account-owner"
    elif fault == "admin-metadata":
        spec["admin"]["scope"]["admin_pool_view"] = not spec["admin"]["scope"].get("admin_pool_view", False)
    elif fault == "changed-purpose":
        spec["text"]["scope"]["selection_purpose"]["source_ref"] = "fixture:changed-existing-purpose"
    else:
        spec["chat"]["scope"]["credential_ref"] = spec["admin"]["scope"]["credential_ref"]
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid minted")), \
            pytest.raises(ValueError):
        prepare_routed(case)
    assert targets(case) == before


@pytest.mark.parametrize("fault", ["existing-disabled", "existing-expired", "duplicate-id",
    "mutual-overlap", "outside-scope", "wrong-principal", "unknown-field", "expired"])
def test_new_grants_are_explicit_nonoverlapping_current_authority(service_owner, fault):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous, additions=True)
    grant = case.routed["admin"]["new_grants"][0]
    if fault in {"existing-disabled", "existing-expired"}:
        accounts = json.loads(case.accounts.read_bytes())
        accounts["application_grants"][0]["enabled"] = False
        if fault == "existing-expired":
            accounts["application_grants"][0]["expires_at"] = time.time() - 20
        case.accounts.write_text(json.dumps(accounts))
        grant["models"] = case.family["admin"]["grant"]["models"]
    elif fault == "duplicate-id":
        grant["grant_id"] = case.family["admin"]["grant"]["grant_id"]
    elif fault == "mutual-overlap":
        copy_grant = dict(grant, grant_id="second-explicit")
        case.routed["admin"]["new_grants"].append(copy_grant)
    elif fault == "outside-scope":
        grant["pool"] = "bailian"
    elif fault == "wrong-principal":
        grant["principal_id"] = "wrong-service"
    elif fault == "unknown-field":
        grant["token"] = "not-grant-authority"
    else:
        grant["expires_at"] = time.time() - 1
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("invalid minted")), \
            pytest.raises(ValueError):
        prepare_routed(case)
    assert targets(case) == before


def test_absent_purpose_can_only_be_added_explicitly(service_owner):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous)
    assert "selection_purpose" not in previous["scopes"][2]
    purpose = copy.deepcopy(case.routed["text"]["scope"]["selection_purpose"])
    purpose.update(purpose_id="explicit-chat-purpose", source_ref="fixture:explicit-chat-contract")
    case.routed["chat"]["scope"]["selection_purpose"] = purpose
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("purpose minted")):
        prepare_routed(case)
        installer.apply_go_service_enrollment(case.service_bundle)
    current = json.loads(case.binding.read_bytes())
    assert current["scopes"][2]["selection_purpose"] == purpose
    assert current["credentials"] == previous["credentials"]


@pytest.mark.parametrize("boundary", ["private", "private-progress", "intent", "binding", "accounts", "receipt"])
def test_original_four_target_interruption_never_mints_or_adopts(service_owner, boundary):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous, additions=True)
    plan = prepare_routed(case)
    paths = {"intent": case.intent, "binding": case.binding, "accounts": case.accounts,
             "receipt": case.service_receipt}
    named = dict(paths, private=case.service_bundle / installer._SERVICE_PRIVATE)
    named["private-progress"] = case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
    original = targets(case)
    original_write, original_replace = g.atomic_bytes, os.replace
    hit = []
    def written(path, raw, mode):
        original_write(path, raw, mode)
        if Path(path) == named[boundary] and boundary not in paths and not hit:
            hit.append(boundary)
            raise OSError("fixture routed ACK lost")
    def renamed(source, target):
        original_replace(source, target)
        if boundary in paths and Path(target) == named[boundary] and not hit:
            hit.append(boundary)
            raise OSError("fixture routed ACK lost")
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("routed minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=written), \
            mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError, match="routed ACK"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit == [boundary]
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("routed reminted")):
        if boundary == "private":
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("uncommitted adopted")), \
                        pytest.raises(ValueError, match="adoption refused"):
                    action(case.service_bundle)
            assert targets(case) == original
            return
        result = installer.reconcile_go_service_enrollment(case.service_bundle)
        receipt = installer.apply_go_service_enrollment(case.service_bundle) if "disposition" in result else result
        assert json.loads(case.binding.read_bytes())["credentials"] == previous["credentials"]
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("target", ["binding", "intent", "receipt", "predecessor", "accounts"])
def test_prepared_transition_keeps_all_predecessor_and_accounts_cas(service_owner, target):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous, additions=True)
    prepare_routed(case)
    path = {"binding": case.binding, "intent": case.intent, "receipt": case.service_receipt,
            "predecessor": case.service_bundle / installer._SERVICE_PREDECESSOR,
            "accounts": case.accounts}[target]
    g.atomic_bytes(path, path.read_bytes(), 0o600)
    before = targets(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("replacement minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("replacement wrote")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert targets(case) == before


@pytest.mark.parametrize("committed", [False, True])
def test_expiry_only_blocks_before_original_intent(service_owner, committed):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous, additions=True)
    prepare_routed(case)
    if committed:
        original = os.replace
        def renamed(source, target):
            original(source, target)
            if Path(target) == case.intent:
                raise OSError("fixture committed intent ACK lost")
        with mock.patch.object(os, "replace", side_effect=renamed), pytest.raises(OSError):
            installer.apply_go_service_enrollment(case.service_bundle)
    future = max(case.routed[name]["new_grants"][0]["expires_at"] for name in NAMES) + 1
    with mock.patch.object(installer.time, "time", return_value=future), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("elapsed minted")):
        if committed:
            receipt = installer.apply_go_service_enrollment(case.service_bundle)
            assert receipt["schema"] == "native-go-service-enrollment-completed.v7"
        else:
            with pytest.raises(ValueError, match="expired before"):
                installer.apply_go_service_enrollment(case.service_bundle)
    assert json.loads(case.binding.read_bytes())["credentials"] == previous["credentials"]

@pytest.mark.parametrize("foreign", [False, True])
def test_scope_only_accounts_ack_loss_keeps_exact_original_custody(service_owner, foreign):
    case = service_owner
    previous = complete_v6(case)
    before = case.accounts.read_bytes()
    routed_specification(case, previous, additions=False)
    prepare_routed(case)
    original = os.replace
    hit = []
    def renamed(source, target):
        original(source, target)
        if Path(target) == case.accounts and not hit:
            hit.append(True)
            raise OSError("fixture scope-only accounts ACK lost")
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("scope-only minted")), \
            mock.patch.object(os, "replace", side_effect=renamed), \
            pytest.raises(OSError, match="scope-only accounts ACK"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit == [True] and case.accounts.read_bytes() == before
    if foreign:
        g.atomic_bytes(case.accounts, before, 0o600)
        held = targets(case)
        for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("foreign accounts adopted")), \
                    mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("foreign minted")), \
                    pytest.raises(ValueError):
                action(case.service_bundle)
        assert targets(case) == held
    else:
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("scope-only reminted")):
            result = installer.reconcile_go_service_enrollment(case.service_bundle)
            receipt = installer.apply_go_service_enrollment(case.service_bundle) if "disposition" in result else result
            assert receipt["schema"] == "native-go-service-enrollment-completed.v7"
            assert json.loads(case.binding.read_bytes())["credentials"] == previous["credentials"]
            assert case.accounts.read_bytes() == before
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("scope-only replay wrote")):
                assert installer.apply_go_service_enrollment(case.service_bundle) == receipt


@pytest.mark.parametrize("index", range(5))
def test_every_retained_credential_hash_is_checked_before_any_write(service_owner, index):
    case = service_owner
    previous = complete_v6(case)
    routed_specification(case, previous)
    plan = prepare_routed(case)
    plan["predecessor_credential_sha256s"][index] = "a" * 64
    plan["digest"] = g.digest(g.canonical({key: value for key, value in plan.items() if key != "digest"}))
    (case.service_bundle / "PLAN.json").write_bytes(g.canonical(plan) + b"\n")
    before = targets(case)
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("forged hash wrote")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("forged hash minted")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert targets(case) == before
