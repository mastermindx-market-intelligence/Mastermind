"""Retained predecessor ingress reaches the existing finite service owner."""
import json
from pathlib import Path
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, g, installer, loaded_entry
from test_go_native_install import retained_go_owner, assert_retained_history
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import (
    prepare, service_owner_from_completed_go,
    reseal_modified_entry_for_disposable_fixtures,
)
from test_go_service_startup import environment, boot
from test_hermes_primary_application_enrollment import select_role, routed_role


@pytest.fixture
def retained_service_owner(retained_go_owner):
    case = retained_go_owner
    case.go_bundle = case.retained_bundle
    case.go_plan = case.retained_plan
    case.go_receipt = installer.apply_retained_go(case.go_bundle)
    return service_owner_from_completed_go(case)


def retained_ingress_unchanged(case):
    assert_retained_history(case)
    assert (case.store / "CURRENT.json").read_bytes() == case.current_before
    assert {name: Path(row["target"]).read_bytes()
            for name, row in case.go_plan["entries"].items()} == case.bridge_before
    assert json.loads((case.go_bundle / "PLAN.json").read_bytes()) == case.retained_plan


@pytest.mark.parametrize("profile", [None, "hermes-secretary", "hermes-meta-ceo"])
def test_retained_origin_enrolls_once_and_reaches_original_startup(
        retained_service_owner, monkeypatch, profile):
    case = retained_service_owner
    if profile:
        select_role(case, profile)
    # Inspection may consume only the completed original ingress. It cannot
    # create, replay or reconcile that transition on the enrollment's behalf.
    monkeypatch.setattr(installer, "_apply_ingress_transition",
                        lambda *a, **k: pytest.fail("inspection invoked ingress transition"))
    original_credential = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_credential) as minted:
        plan = prepare(case)
        assert case.go_plan["schema"] == installer.GO_RETAINED_SCHEMA
        assert plan["go_ingress_bundle"] == str(case.go_bundle)
        assert plan["ingress_digest"] == case.go_plan["digest"]
        assert plan["selection"] == case.go_receipt["selection"]
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed enrollment wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert minted.call_count == 1
    private = json.loads(case.binding.read_bytes())
    assert private["credential"] not in json.dumps([plan, receipt])
    assert private["scope"] == plan["scope"] == receipt["scope"]
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
        assert binding.principal_id == case.specification["scope"]["principal_id"]
        assert binding.credential_ref == case.specification["scope"]["credential_ref"]
    retained_ingress_unchanged(case)


@pytest.mark.parametrize("profile", ["hermes-secretary", "hermes-meta-ceo"])
def test_retained_origin_routed_roles_keep_one_physical_account_owner(retained_service_owner, profile):
    case = retained_service_owner
    routed_role(case, profile)
    before = json.loads(case.accounts.read_bytes())
    plan = prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    assert plan["grant_sha256"] == g.digest(g.canonical(case.specification["grants"]))
    assert json.loads(case.accounts.read_bytes()) == {
        **before, "application_grants": case.specification["grants"]}
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        (binding,), _, account_profile = entry.load_completed_application_startup(startup, profile)
        assert binding.route_scope == startup.handler.ApplicationRouteScope(case.specification["scope"]["route_scope"])
        assert account_profile == case.profile
    retained_ingress_unchanged(case)


@pytest.mark.parametrize("mutation", [
    "unknown-schema", "intact-schema-relabel", "changed-origin", "missing-receipt", "changed-receipt",
    "missing-intent", "different-selection", "changed-live-bridge", "changed-payload",
])
def test_retained_origin_enrollment_refuses_incomplete_or_foreign_ingress(
        retained_service_owner, monkeypatch, mutation):
    case = retained_service_owner
    go_plan = case.go_bundle / "PLAN.json"
    go_receipt = case.store / "bootstrap" / (case.go_plan["digest"] + ".go.json")
    go_intent = case.store / "bootstrap/.go-application-ingress-v1.json"
    if mutation in ("unknown-schema", "intact-schema-relabel", "changed-origin"):
        changed = json.loads(go_plan.read_bytes())
        if mutation == "intact-schema-relabel":
            changed["schema"] = installer.GO_SCHEMA
        else:
            changed["schema" if mutation == "unknown-schema" else "predecessor_origin"] = "foreign"
        go_plan.write_bytes(g.canonical(changed) + b"\n")
    elif mutation == "missing-receipt":
        go_receipt.unlink()
    elif mutation == "changed-receipt":
        changed = json.loads(go_receipt.read_bytes())
        changed["plan_digest"] = "f" * 64
        go_receipt.write_bytes(g.canonical(changed) + b"\n")
    elif mutation == "missing-intent":
        go_intent.unlink()
    elif mutation == "different-selection":
        changed = g.current(case.store)
        changed["sequence"] += 1
        (case.store / "CURRENT.json").write_bytes(g.canonical(changed) + b"\n")
    elif mutation == "changed-live-bridge":
        path = Path(case.go_plan["entries"]["go"]["target"])
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
    else:
        path = case.go_bundle / "pool.bridge"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
    before_accounts = case.accounts.read_bytes()
    before_selection = (case.store / "CURRENT.json").read_bytes()
    monkeypatch.setattr(installer.secrets, "token_urlsafe",
                        lambda *a, **k: pytest.fail("unqualified enrollment minted a credential"))
    with pytest.raises((ValueError, OSError)):
        prepare(case)
    assert case.accounts.read_bytes() == before_accounts
    assert (case.store / "CURRENT.json").read_bytes() == before_selection
    assert not case.service_bundle.exists()
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()
