"""Hermes v9 enrollment borrows the original completed retained-Go ingress.

Every owner is disposable. The original installer creates and prunes its own
bootstrap history; the retained transition and service publication run for
real. No provider request, live enrollment or runtime selection is performed.
"""
import json
from pathlib import Path
from unittest import mock

import pytest

from test_hermes_primary_application_enrollment import PROFILES, routed_role, select_role
from test_go_native_stage import builds, native_stage, g, installer, loaded_entry
from test_go_native_install import retained_go_owner, assert_retained_history
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import (
    service_owner as incumbent_service_fixture,
    reseal_modified_entry_for_disposable_fixtures,
    prepare,
)
from test_go_service_startup import environment, boot


@pytest.fixture
def retained_service_owner(retained_go_owner):
    case = retained_go_owner
    case.retained_receipt = installer.apply_retained_go(case.retained_bundle)
    assert case.retained_receipt["schema"] == installer.GO_RETAINED_SCHEMA
    case.go_bundle, case.go_plan = case.retained_bundle, case.retained_plan

    def already_completed(bundle):
        # Reuse only the incumbent fixture's synthetic account/role data setup.
        # Its initial apply_go call must inspect the retained transition that
        # already completed above. No production reader or transition is mocked
        # during any enrollment, startup, refusal or recovery assertion below.
        assert Path(bundle) == case.retained_bundle
        plan, selected, _, _ = installer._completed_go_for_service(bundle)
        assert plan == case.retained_plan
        assert selected == case.retained_receipt["selection"]
        return case.retained_receipt

    with mock.patch.object(installer, "apply_go", side_effect=already_completed) as inspected:
        assert incumbent_service_fixture.__wrapped__(case) is case
        assert inspected.call_count == 1
    intent_name, suffix, _, _, _, _ = installer._transition_records(case.retained_plan)
    case.retained_intent_path = case.store / "bootstrap" / intent_name
    case.retained_receipt_path = case.store / "bootstrap" / (case.retained_plan["digest"] + suffix)
    case.retained_artifacts = {
        path: (path.read_bytes(), path.stat().st_ino)
        for path in (case.retained_bundle / "PLAN.json", case.retained_intent_path,
                     case.retained_receipt_path)
    }
    return case


def unchanged_retained_ingress(case):
    assert_retained_history(case)
    assert (case.store / "CURRENT.json").read_bytes() == case.current_before
    assert {name: Path(row["target"]).read_bytes()
            for name, row in case.retained_plan["entries"].items()} == case.bridge_before
    assert {path: (path.read_bytes(), path.stat().st_ino)
            for path in case.retained_artifacts} == case.retained_artifacts


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("routed", [False, True])
def test_retained_ingress_enrolls_one_role_and_starts_the_original_broker(
        retained_service_owner, monkeypatch, profile, routed):
    case = retained_service_owner
    (routed_role if routed else select_role)(case, profile)
    before = json.loads(case.accounts.read_bytes())
    plan = prepare(case)
    assert plan["schema"] == "native-go-service-enrollment.v9"
    assert plan["ingress_digest"] == case.retained_plan["digest"]
    assert plan["go_ingress_bundle"] == str(case.retained_bundle)
    assert plan["source_generation"] == case.retained_plan["target_generation"]
    assert plan["installer_sha256"] == g.digest(Path(installer.__file__).read_bytes())
    expected_grants = (case.specification["grants"] if routed
                       else [case.specification["grant"]])
    original_secret = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as minted, \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("enrollment selected")):
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed replay wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert minted.call_count == 1
    assert receipt["schema"] == "native-go-service-enrollment-completed.v9"
    assert json.loads(case.accounts.read_bytes()) == {**before, "application_grants": expected_grants}
    assert {tuple(grant["accounts"]) for grant in expected_grants} == {("account-a",)}
    private = json.loads(case.binding.read_bytes())
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
        assert binding.credential == private["credential"] and not binding.admin_pool_view
        if routed:
            assert binding.route_scope == startup.handler.ApplicationRouteScope(
                case.specification["scope"]["route_scope"])
        assert entry.load_completed_application_startup(startup, profile)[2] == case.profile
    unchanged_retained_ingress(case)


def test_retained_enrollment_never_relabels_or_replays_the_original_ingress(retained_service_owner):
    case = retained_service_owner
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("inspection wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("inspection selected")):
        assert installer._completed_go_for_service(case.retained_bundle)[0] == case.retained_plan
        assert installer.reconcile_retained_go(case.retained_bundle) == case.retained_receipt
        for action in (installer.read_go, installer.apply_go, installer.reconcile_go):
            with pytest.raises(ValueError):
                action(case.retained_bundle)
        # The historical status reader still authenticates the OLD bridges.
        # It must not pretend that the newly selected Go bridges are the old pin.
        with pytest.raises(ValueError):
            installer.read_retained_successor_after_bootstrap_prune(case.successor)
    unchanged_retained_ingress(case)


@pytest.mark.parametrize("fault", ["missing-intent", "missing-receipt", "foreign-receipt",
    "selection", "bridge", "launcher", "restored-bootstrap", "unknown-schema", "ordinary-schema"])
def test_unproven_retained_ingress_refuses_before_role_intent_or_credential(retained_service_owner, fault):
    case = retained_service_owner
    select_role(case, "hermes-secretary")
    accounts_before = case.accounts.read_bytes()
    if fault == "missing-intent":
        case.retained_intent_path.unlink()
    elif fault == "missing-receipt":
        case.retained_receipt_path.unlink()
    elif fault == "foreign-receipt":
        changed = json.loads(case.retained_receipt_path.read_bytes())
        changed["plan_digest"] = "0" * 64
        case.retained_receipt_path.write_bytes(g.canonical(changed) + b"\n")
    elif fault == "selection":
        selected = g.current(case.store)
        g.select(case.store, selected["generation"], selected["generation"])
    elif fault == "bridge":
        Path(case.retained_plan["entries"]["go"]["target"]).write_bytes(b"foreign bridge\n")
    elif fault == "launcher":
        (case.store / "launchers" / (case.retained_plan["to_launcher"] + ".py")).unlink()
    elif fault == "restored-bootstrap":
        case.original.mkdir()
    else:
        path = case.retained_bundle / "PLAN.json"
        changed = json.loads(path.read_bytes())
        changed["schema"] = installer.GO_SCHEMA if fault == "ordinary-schema" else "unknown-ingress.v1"
        path.write_bytes(g.canonical(changed) + b"\n")
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("unproven ingress minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("unproven ingress wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("unproven ingress selected")):
        with pytest.raises((ValueError, OSError)):
            prepare(case)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_bundle.exists()
    assert case.accounts.read_bytes() == accounts_before


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("boundary", ["binding-ack", "missing-receipt"])
def test_retained_role_recovery_uses_the_original_token_and_published_inode(
        retained_service_owner, profile, boundary):
    case = retained_service_owner
    select_role(case, profile)
    prepare(case)
    original_replace = installer.os.replace
    original_write = g.atomic_bytes
    original_secret = installer.secrets.token_urlsafe
    interrupted = []

    def replace(source, target):
        original_replace(source, target)
        if boundary == "binding-ack" and Path(target) == case.binding and not interrupted:
            interrupted.append(True)
            raise OSError("fixture original binding acknowledgement lost")

    def write(path, raw, mode):
        if boundary == "missing-receipt" and Path(path) == case.service_receipt and not interrupted:
            interrupted.append(True)
            raise OSError("fixture original receipt absent")
        return original_write(path, raw, mode)

    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as minted:
        with mock.patch.object(installer.os, "replace", side_effect=replace), \
                mock.patch.object(g, "atomic_bytes", side_effect=write), \
                pytest.raises(OSError, match="fixture original"):
            installer.apply_go_service_enrollment(case.service_bundle)
    assert interrupted == [True] and minted.call_count == 1
    original_binding = (case.binding.read_bytes(), case.binding.stat().st_ino)
    assert not case.service_receipt.exists()

    def receipt_only(path, raw, mode):
        assert Path(path) == case.service_receipt, "reconciliation rewrote a settled target"
        return original_write(path, raw, mode)

    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("recovery minted")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("recovery selected")):
        if boundary == "binding-ack":
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("partial inspection wrote")):
                assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "partial"
            receipt = installer.apply_go_service_enrollment(case.service_bundle)
        else:
            with mock.patch.object(g, "atomic_bytes", side_effect=receipt_only):
                receipt = installer.reconcile_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed recovery wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert (case.binding.read_bytes(), case.binding.stat().st_ino) == original_binding
    assert json.loads(case.accounts.read_bytes())["application_grants"] == [case.specification["grant"]]
    unchanged_retained_ingress(case)
