"""Finite enrollment through the actual completed C lineage and A parser."""
import copy
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import time
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, ROOT, g, installer, loaded_entry
from test_go_native_install import go_owner, assert_history, retained_go_owner, assert_retained_history
from test_native_launcher_successor_transition import source_owners, owner


@pytest.fixture(scope="module", autouse=True)
def reseal_modified_entry_for_disposable_fixtures():
    """Reseal the entry in disposable fixtures without replacing source verification."""
    import native_generation as generation
    import sys as fixture_sys
    from test_go_native_stage import builder, ROOT
    import test_native_launcher_upgrade as fixture_upgrade
    fixture_path = str(ROOT / "tests")
    if fixture_path in sys.path:
        sys.path.remove(fixture_path)
    import test_native_launcher_upgrade as fixture_upgrade
    import test_native_launcher_successor_transition as package_transition
    package_transition.historical = fixture_upgrade
    fixture_sys.modules["test_native_launcher_successor_transition"] = package_transition
    if "test_go_native_install" in fixture_sys.modules:
        fixture_sys.modules["test_go_native_install"].history = package_transition

    original = builder.stage_external_go_component
    def reseal(root, output, ext, staged_manifest=None):
        result = original(root, output, ext, staged_manifest=staged_manifest)
        if staged_manifest is None or not (output / "native-source-inventory.json").exists():
            return result
        path = output / "native-code-stage" / generation.GO_ENTRY
        raw = (ROOT / "candidate/native_go_entry.py").read_bytes()
        path.write_bytes(raw)
        digest = generation.digest(raw)
        output.joinpath("native-manifest.json").write_text(json.dumps(
            dict(staged_manifest, **{generation.GO_ENTRY: digest}), sort_keys=True, indent=2) + "\n")
        if staged_manifest is not None:
            staged_manifest[generation.GO_ENTRY] = digest
        inventory_path = output / "native-source-inventory.json"
        if not inventory_path.exists():
            return result
        inventory = json.loads(inventory_path.read_bytes())
        inventory["files"][generation.GO_ENTRY].update(sha256=digest, bytes=len(raw))
        inventory_path.write_text(json.dumps(inventory, sort_keys=True, indent=2) + "\n")
        return result
    with mock.patch.object(builder, "stage_external_go_component", side_effect=reseal):
        yield



@pytest.fixture
def service_owner(go_owner):
    case = go_owner
    installer.apply_go(case.go_bundle)
    return service_owner_from_completed_go(case)


def service_owner_from_completed_go(case):
    """Configure the same physical service owner after an actual Go transition."""
    go = case.ext / "go_shim"
    go.chmod(0o700)
    for relative in ("glm_shim", "state", "broker"):
        (case.ext / relative).mkdir(mode=0o700)
    (case.ext / "glm_shim/glm_shim.py").write_bytes(
        (ROOT.parent / "paid_canonical_glm/source/glm_shim.py").read_bytes())
    case.profile = case.root / "service-profile/accounts.json"
    case.profile.parent.mkdir(mode=0o700)
    case.profile.write_text(json.dumps({"account-a": {"api_key": "fixture-provider-only"}}))
    case.profile.chmod(0o600)
    (go / ".token").write_text("fixture-controller-only-0123456789abcdef")
    (go / ".token").chmod(0o600)
    (go / "go_prices.json").write_text(json.dumps({"models": {"fixture-model": {"rows": [
        {"monthly_usd": "20", "in": "1", "out": "1", "cached_read": "0", "cache_write": "0"}]}}, "unpriced": []}))
    (go / "model_tiers.json").write_text(json.dumps({"models": {"fixture-model": {"weight": 1}}}))
    (go / "wire_matrix.json").write_text("{}")
    (case.ext / "state/go_wire_compat.json").write_text("{}")
    (case.ext / "hosts.json").write_text("{}")
    sqlite3.connect(case.ext / "broker/leases.sqlite").close()
    (case.ext / "broker/leases.lock").touch(mode=0o600)
    case.accounts = case.ext.parent / "orch/fabric/accounts.yaml"
    case.accounts.parent.mkdir(parents=True)
    case.document = {"schema": "mastermind.provider_accounts.v1", "providers": {"go": {
        "enabled": True, "accounts": [{"name": "account-a", "per_account_cap": 2},
                                      {"name": "account-b", "per_account_cap": 1}]}},
        "operator_note": {"retain": [1, "unchanged", False]}}
    case.accounts.write_text(json.dumps(case.document))
    (case.accounts.parent / "status.json").write_text("{}")
    case.specification = {"schema": installer.SERVICE_SPEC_SCHEMA,
        "operation_id": "fixture-admin-enrollment", "scope": {
            "principal_id": "macro-admin", "caller_host": "fixture-vps", "native_host": "fixture-native",
            "workload": "admin-site-interactive", "credential_ref": "MACRO_FABRIC_APPLICATION_TOKEN",
            "capability_lane": "admin-orchestrator", "workload_profile": "site_interactive",
            "account_profile": str(case.profile)},
        "grant": {"grant_id": "fixture-admin", "purpose": "APPLICATION", "enabled": True,
            "principal_id": "macro-admin", "credential_ref": "MACRO_FABRIC_APPLICATION_TOKEN",
            "admission_root": "service:macro-admin", "caller_hosts": ["fixture-vps"],
            "workloads": ["admin-site-interactive"], "pool": "go", "accounts": ["account-a"],
            "models": ["fixture-model"], "route": "/v1/chat/completions", "stream": False,
            "expires_at": time.time() + 900, "max_turn_seconds": 90, "max_steps": 3,
            "qualification_ref": "fixture:source-only", "application_permission_ref": "fixture:ordinary-inference"}}
    case.service_bundle = case.root / "service-review"
    case.binding = go / "application-service.json"
    case.intent = case.store / "bootstrap/.go-service-enrollment-v1.json"
    case.service_receipt = case.store / "bootstrap/go-service-enrollment-v1.json"
    _, metadata = g.verify(case.store, case.go_target.name)
    case.published = SimpleNamespace(root=case.root, ext=case.ext, release=case.go_target,
        store=case.store, meta=metadata, profile=case.profile, manifest=metadata["files"])
    case.current_before = (case.store / "CURRENT.json").read_bytes()
    case.bridge_before = {name: Path(row["target"]).read_bytes() for name, row in case.go_plan["entries"].items()}
    return case


def set_specification(case, *, successor=False):
    admin = copy.deepcopy(case.specification)
    text = copy.deepcopy(case.specification)
    admin["schema"] = installer.SERVICE_ADMIN_SPEC_SCHEMA
    admin["scope"]["admin_pool_view"] = True
    admin["scope"]["selection_purpose"] = {
        "purpose_id": "fixture-admin-text", "source_ref": "fixture:qualified-purpose",
        "task": {"task_class": "mechanical", "route_key": "fixture-admin-text",
                 "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
    admin["scope"].update(principal_id="macro-admin", caller_host="fixture-vps",
        workload="admin-site-interactive", capability_lane="admin-orchestrator",
        workload_profile="site_interactive", credential_ref="MACRO_FABRIC_APPLICATION_TOKEN")
    admin["grant"].update(grant_id="fixture-admin", principal_id="macro-admin",
        credential_ref="MACRO_FABRIC_APPLICATION_TOKEN", caller_hosts=["fixture-vps"],
        workloads=["admin-site-interactive"], models=["fixture-model"])
    purpose = {"purpose_id": "fixture-text-batch", "source_ref": "fixture:qualified-text",
        "task": {"task_class": "mechanical", "route_key": "fixture-text-batch",
                 "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
    text["schema"] = installer.SERVICE_SELECTED_SPEC_SCHEMA
    text["scope"].update(principal_id="mastermind-text", caller_host="m2studio",
        workload="mastermind-site-batch", capability_lane="mastermind-text",
        workload_profile="site_batch", credential_ref="MASTERMIND_FABRIC_APPLICATION_TOKEN",
        selection_purpose=purpose)
    text["grant"].update(grant_id="fixture-text", principal_id="mastermind-text",
        credential_ref="MASTERMIND_FABRIC_APPLICATION_TOKEN", caller_hosts=["m2studio"],
        workloads=["mastermind-site-batch"], models=["fixture-model"])
    case.service_set = {"schema": installer.SERVICE_SET_SPEC_SCHEMA,
        "operation_id": "fixture-service-set", "admin": admin, "text": text}
    case.admin_credential = None
    case.admin_grant = copy.deepcopy(admin["grant"])
    return case.service_set


def prepare_set(case):
    plan = installer.prepare_go_service_enrollment(case.go_bundle, case.service_set, case.service_bundle)
    private = case.service_bundle / installer._SERVICE_PRIVATE
    case.admin_credential = (json.loads(private.read_bytes())["credentials"][0]
                             if private.exists() else None)
    return plan


def prepare(case):
    case.service_plan = installer.prepare_go_service_enrollment(case.go_bundle, case.specification, case.service_bundle)
    return case.service_plan

def selected_purpose(case):
    """Explicit fixture qualification; workload names supply no task class."""
    purpose = {"purpose_id": "fixture-admin-text", "source_ref": "fixture:qualified-purpose",
        "task": {"task_class": "mechanical", "route_key": "fixture-admin-text",
                 "task_complexity": "C1_ROUTINE_BOUNDED", "needs": []}}
    case.specification["schema"] = installer.SERVICE_SELECTED_SPEC_SCHEMA
    case.specification["scope"]["selection_purpose"] = copy.deepcopy(purpose)
    return purpose


@pytest.mark.parametrize("allowed", [True, False])
def test_admin_v4_permission_is_committed_by_existing_owner(service_owner, allowed):
    case = service_owner
    purpose = selected_purpose(case)
    case.specification["schema"] = installer.SERVICE_ADMIN_SPEC_SCHEMA
    case.specification["scope"]["admin_pool_view"] = allowed
    plan = prepare(case)
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    assert plan["schema"] == "native-go-service-enrollment.v4"
    assert receipt["schema"] == "native-go-service-enrollment-completed.v4"
    document = json.loads(case.binding.read_bytes())
    assert document["schema"] == "mastermind.native_go_application_service.v4"
    assert document["scope"] == plan["scope"] == receipt["scope"]
    assert document["scope"]["admin_pool_view"] is allowed
    assert document["scope"]["selection_purpose"] == purpose
    with loaded_entry(case.published) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        bindings, _, _ = entry.load_completed_application_startup(startup)
        assert bindings[0].admin_pool_view is allowed
    # Changing only the private permission cannot survive the original receipt.
    document["scope"]["admin_pool_view"] = not allowed
    case.binding.write_text(json.dumps(document))
    with loaded_entry(case.published) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        with pytest.raises(ValueError):
            entry.load_completed_application_startup(startup)
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ["v1", "v3", "nonbool", "missing", "no-purpose"])
def test_admin_permission_cannot_be_inferred_or_smuggled_into_old_schema(service_owner, fault):
    case = service_owner
    selected_purpose(case)
    case.specification["schema"] = installer.SERVICE_ADMIN_SPEC_SCHEMA
    case.specification["scope"]["admin_pool_view"] = True
    if fault == "v1":
        case.specification["schema"] = installer.SERVICE_SPEC_SCHEMA
        del case.specification["scope"]["selection_purpose"]
    elif fault == "v3":
        case.specification["schema"] = installer.SERVICE_SELECTED_SPEC_SCHEMA
    elif fault == "nonbool":
        case.specification["scope"]["admin_pool_view"] = 1
    elif fault == "missing":
        del case.specification["scope"]["admin_pool_view"]
    else:
        del case.specification["scope"]["selection_purpose"]
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.service_bundle.exists() and not case.intent.exists() and not case.binding.exists()


def test_selected_purpose_uses_existing_plan_private_binding_and_completion_receipt(service_owner):
    case = service_owner
    purpose = selected_purpose(case)
    plan = prepare(case)
    assert plan["schema"] == "native-go-service-enrollment.v3"
    assert plan["scope"]["selection_purpose"] == purpose
    # Mutation of a caller's input after prepare cannot alter its sealed plan.
    case.specification["scope"]["selection_purpose"]["task"]["needs"].append("vision")
    original = installer.secrets.token_urlsafe
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original) as secret:
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        assert secret.call_count == 1
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
        assert secret.call_count == 1
    binding = json.loads(case.binding.read_bytes())
    assert binding["schema"] == "mastermind.native_go_application_service.v3"
    assert binding["scope"]["selection_purpose"] == purpose
    assert receipt["schema"] == "native-go-service-enrollment-completed.v3"
    assert receipt["scope"] == binding["scope"] == plan["scope"]
    assert receipt["binding_sha256"] == g.digest(case.binding.read_bytes())
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ["missing", "requested-model", "unknown", "workload-alias",
    "malformed-needs", "legacy-v1"])
def test_selected_purpose_is_closed_and_never_inserted_into_legacy_scope(service_owner, fault):
    case = service_owner
    selected_purpose(case)
    purpose = case.specification["scope"]["selection_purpose"]
    if fault == "missing":
        del case.specification["scope"]["selection_purpose"]
    elif fault == "requested-model":
        purpose["task"]["requested_model"] = "different-model"
    elif fault == "unknown":
        purpose["task"]["caller_permission"] = True
    elif fault == "workload-alias":
        del purpose["task"]["task_class"]
    elif fault == "malformed-needs":
        purpose["task"]["needs"] = {"tools": True}
    elif fault == "legacy-v1":
        case.specification["schema"] = installer.SERVICE_SPEC_SCHEMA
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.intent.exists() and not case.binding.exists() and not case.service_receipt.exists()
    assert not case.service_bundle.exists()
    unchanged_ingress(case)


def unchanged_ingress(case):
    if case.go_plan["schema"] == installer.GO_RETAINED_SCHEMA:
        assert_retained_history(case)
    else:
        assert_history(case)
    assert (case.store / "CURRENT.json").read_bytes() == case.current_before
    assert {name: Path(row["target"]).read_bytes() for name, row in case.go_plan["entries"].items()} == case.bridge_before


def test_prepare_uses_actual_parser_without_broker_database_credentials_or_mutation(service_owner):
    case = service_owner
    original = case.accounts.read_bytes()
    with mock.patch.object(sqlite3, "connect", side_effect=AssertionError("prepare opened SQLite")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("prepare minted credential")):
        plan = prepare(case)
        assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "prepared"
    assert case.accounts.read_bytes() == original
    assert not case.binding.exists() and not case.intent.exists() and not case.service_receipt.exists()
    assert {p.name for p in case.service_bundle.iterdir()} == installer._SERVICE_PREPARED_FILES
    after = json.loads((case.service_bundle / "accounts.after.yaml").read_bytes())
    assert after == dict(case.document, application_grants=[case.specification["grant"]])
    assert plan["scope"]["caller_host"] != plan["scope"]["native_host"]
    assert "credential" not in plan and "api_key" not in json.dumps(plan)
    unchanged_ingress(case)


def test_enrollment_commits_one_private_binding_and_one_scoped_grant(service_owner, capsys):
    case = service_owner
    plan = prepare(case)
    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=installer.secrets.token_urlsafe) as minted, \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("enrollment changed CURRENT")):
        receipt = installer.apply_go_service_enrollment(case.service_bundle)
        assert minted.call_count == 1
    assert case.binding.stat().st_mode & 0o777 == 0o600
    binding_raw = case.binding.read_bytes()
    secret = json.loads(binding_raw)["credential"]
    assert receipt["binding_sha256"] == g.digest(binding_raw)
    assert json.loads(case.accounts.read_bytes()) == dict(case.document, application_grants=[case.specification["grant"]])
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed enrollment wrote again")), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("completed enrollment minted")):
        assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
        assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        services, host, profile = entry.load_completed_application_startup(startup)
        assert services[0].credential == secret and secret not in repr(services)
        assert host == "fixture-native" and services[0].host == "fixture-vps" and profile == case.profile
    assert secret not in json.dumps(plan) and secret not in json.dumps(receipt)
    assert secret not in capsys.readouterr().out
    unchanged_ingress(case)


@pytest.mark.parametrize("boundary", ["intent", "private", "private-progress", "binding-prepare",
    "binding", "binding-progress", "accounts-prepare", "accounts", "accounts-progress", "receipt"])
def test_interrupted_original_enrollment_never_mints_or_publishes_twice(service_owner, boundary):
    case = service_owner
    plan = prepare(case)
    targets = {"intent": case.intent, "private": case.service_bundle / installer._SERVICE_PRIVATE,
        "binding": case.binding, "accounts": case.accounts, "receipt": case.service_receipt,
        "private-progress": case.store / "bootstrap" / (plan["digest"] + ".service-private.json"),
        "binding-prepare": case.store / "bootstrap" / (plan["digest"] + ".service-binding-prepared.json"),
        "accounts-prepare": case.store / "bootstrap" / (plan["digest"] + ".service-accounts-prepared.json"),
        "binding-progress": case.store / "bootstrap" / (plan["digest"] + ".service-binding.json"),
        "accounts-progress": case.store / "bootstrap" / (plan["digest"] + ".service-accounts.json")}
    original = g.atomic_bytes
    original_replace = os.replace
    hit = []
    def interrupted(path, raw, mode):
        original(path, raw, mode)
        if Path(path) == targets[boundary] and not hit:
            hit.append(True)
            raise OSError("fixture original write lost acknowledgement")
    def rename_interrupted(source, target):
        original_replace(source, target)
        if boundary in {"binding", "accounts"} and Path(target) == targets[boundary] and not hit:
            hit.append(True)
            raise OSError("fixture original rename lost acknowledgement")
    with mock.patch.object(g, "atomic_bytes", side_effect=interrupted), \
            mock.patch.object(os, "replace", side_effect=rename_interrupted), pytest.raises(OSError, match="fixture"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert hit
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("regenerated original credential")):
        if boundary in {"intent", "private"}:
            for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
                with pytest.raises(ValueError, match="regeneration refused|adoption refused"):
                    action(case.service_bundle)
            assert not case.binding.exists()
            return
        if boundary in {"private-progress", "binding-prepare", "binding", "binding-progress", "accounts-prepare"}:
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("partial reconcile wrote")):
                result = installer.reconcile_go_service_enrollment(case.service_bundle)
                assert result["disposition"] == ("staged" if boundary in {"private-progress", "binding-prepare"} else "partial")
            installer.apply_go_service_enrollment(case.service_bundle)
        else:
            def receipts_only(path, raw, mode):
                assert Path(path).parent == case.store / "bootstrap", "reconcile rewrote a target"
                original(path, raw, mode)
            with mock.patch.object(g, "atomic_bytes", side_effect=receipts_only):
                installer.reconcile_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed original wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle)["plan_digest"] == plan["digest"]
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ["accounts-bytes", "accounts-inode", "profile-mode", "lock-inode", "go-mode", "source-selection"])
def test_stale_preimage_and_owner_custody_refuse_before_intent(service_owner, fault):
    case = service_owner
    prepare(case)
    if fault == "accounts-bytes":
        case.accounts.write_bytes(case.accounts.read_bytes() + b"\n")
    elif fault == "accounts-inode":
        g.atomic_bytes(case.accounts, case.accounts.read_bytes(), 0o644)
    elif fault == "profile-mode":
        case.profile.chmod(0o644)
    elif fault == "lock-inode":
        g.atomic_bytes(case.ext / "broker/leases.lock", b"", 0o600)
    elif fault == "go-mode":
        (case.ext / "go_shim").chmod(0o755)
    else:
        current = g.current(case.store)
        g.select(case.store, current["generation"], current["generation"])
    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("bad custody minted")), \
            mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("bad custody wrote")), \
            pytest.raises(ValueError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert not case.intent.exists() and not case.binding.exists()


def test_same_physical_broker_lock_excludes_enrollment_without_creating_another_lock(service_owner):
    case = service_owner
    prepare(case)
    lock = case.ext / "broker/leases.lock"
    identity = lock.stat().st_ino
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("locked operation minted")), \
                mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("locked operation wrote")), \
                pytest.raises(ValueError, match="lock is busy"):
            installer.apply_go_service_enrollment(case.service_bundle)
    finally:
        os.close(fd)
    assert lock.stat().st_ino == identity and not case.intent.exists()
    installer.apply_go_service_enrollment(case.service_bundle)


@pytest.mark.parametrize("fault", ["duplicate-grant", "overlapping-grant", "unknown-account", "caller", "workload", "credential-ref", "extra-grant-field"])
def test_actual_A_parser_and_explicit_mapping_reject_widening(service_owner, fault):
    case = service_owner
    if fault in {"duplicate-grant", "overlapping-grant"}:
        existing = copy.deepcopy(case.specification["grant"])
        if fault == "overlapping-grant":
            existing["grant_id"] = "other-grant"
        case.document["application_grants"] = [existing]
        case.accounts.write_text(json.dumps(case.document))
    elif fault == "unknown-account":
        case.specification["grant"]["accounts"] = ["not-an-account"]
    elif fault == "caller":
        case.specification["grant"]["caller_hosts"] = ["other-caller"]
    elif fault == "workload":
        case.specification["scope"]["workload"] = "unrelated-workload"
    elif fault == "credential-ref":
        case.specification["scope"]["credential_ref"] = "GO_CONTROLLER_TOKEN"
    else:
        case.specification["grant"]["extra"] = True
    with pytest.raises(ValueError):
        prepare(case)
    assert not case.binding.exists() and not case.intent.exists()


@pytest.mark.parametrize("target", ["binding", "accounts"])
def test_settled_identical_bytes_on_a_different_inode_are_not_original_publication(service_owner, target):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    path = getattr(case, target)
    g.atomic_bytes(path, path.read_bytes(), path.stat().st_mode & 0o777)
    for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("foreign inode repaired")), pytest.raises(ValueError):
            action(case.service_bundle)


def test_changed_private_payload_between_targets_stops_before_grant(service_owner):
    case = service_owner
    prepare(case)
    before = case.accounts.read_bytes()
    original = os.replace
    def altered(source, target):
        original(source, target)
        if Path(target) == case.binding:
            private = case.service_bundle / installer._SERVICE_PRIVATE
            value = json.loads(private.read_bytes())
            value["credential"] = "fixture-other-credential-0123456789"
            g.atomic_bytes(private, g.canonical(value) + b"\n", 0o600)
    with mock.patch.object(os, "replace", side_effect=altered), pytest.raises(ValueError, match="custody changed"):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert case.accounts.read_bytes() == before and not case.service_receipt.exists()


@pytest.mark.parametrize("replace_inode", [False, True])
def test_staged_private_credential_cannot_change_across_restart(service_owner, replace_inode):
    case = service_owner
    plan = prepare(case)
    committed = case.store / "bootstrap" / (plan["digest"] + ".service-private.json")
    original = g.atomic_bytes
    def interrupted(path, raw, mode):
        original(path, raw, mode)
        if Path(path) == committed:
            raise OSError("fixture after private commitment")
    with mock.patch.object(g, "atomic_bytes", side_effect=interrupted), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    private = case.service_bundle / installer._SERVICE_PRIVATE
    value = json.loads(private.read_bytes())
    value["credential"] = "fixture-substituted-valid-credential-0123456789"
    raw = g.canonical(value) + b"\n"
    if replace_inode:
        original(private, raw, 0o600)
    else:
        private.write_bytes(raw)
    for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("substituted credential wrote")), \
                pytest.raises(ValueError, match="commitment differs"):
            action(case.service_bundle)
    assert not case.binding.exists() and not case.service_receipt.exists()


@pytest.mark.parametrize("target", ["binding", "accounts"])
def test_lost_ack_identical_postimage_replacement_cannot_be_adopted(service_owner, target):
    case = service_owner
    plan = prepare(case)
    path = getattr(case, target)
    original = os.replace
    def interrupted(source, destination):
        original(source, destination)
        if Path(destination) == path:
            raise OSError("fixture after original target rename")
    with mock.patch.object(os, "replace", side_effect=interrupted), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    assert not (case.store / "bootstrap" / (plan["digest"] + ".service-" + target + ".json")).exists()
    g.atomic_bytes(path, path.read_bytes(), path.stat().st_mode & 0o777)
    for action in (installer.apply_go_service_enrollment, installer.reconcile_go_service_enrollment):
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("foreign lost-ack inode repaired")), \
                pytest.raises(ValueError, match="original prepared inode"):
            action(case.service_bundle)


@pytest.mark.parametrize("target", ["binding", "accounts"])
def test_recovered_rename_is_durable_and_revalidated_before_receipt(service_owner, target):
    case = service_owner
    plan = prepare(case)
    path = getattr(case, target)
    progress = case.store / "bootstrap" / (plan["digest"] + ".service-" + target + ".json")
    original_replace = os.replace

    def interrupted(source, destination):
        original_replace(source, destination)
        if Path(destination) == path:
            raise OSError("fixture after original target rename")

    with mock.patch.object(os, "replace", side_effect=interrupted), pytest.raises(OSError):
        installer.apply_go_service_enrollment(case.service_bundle)
    before = (path.read_bytes(), path.stat().st_ino)
    original_sync = g.fsync_directory
    action = (installer.apply_go_service_enrollment if target == "binding"
              else installer.reconcile_go_service_enrollment)

    def failed_sync(directory):
        if Path(directory) == path.parent:
            raise OSError("fixture recovered target fsync failed")
        return original_sync(directory)

    with mock.patch.object(g, "fsync_directory", side_effect=failed_sync), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("new credential")), \
            pytest.raises(OSError, match="recovered target fsync failed"):
        action(case.service_bundle)
    assert not progress.exists() and not case.service_receipt.exists()
    assert (path.read_bytes(), path.stat().st_ino) == before
    events = []
    original_target, original_record = installer._service_target, installer._record_once

    def synced(directory):
        result = original_sync(directory)
        if Path(directory) == path.parent:
            events.append("sync")
        return result

    def checked(*args):
        result = original_target(*args)
        if Path(args[1]) == path:
            events.append("identity")
        return result

    def recorded(destination, value):
        if Path(destination) == progress:
            assert events[-2:] == ["sync", "identity"]
            events.append("progress")
        return original_record(destination, value)

    def no_replacement(source, destination):
        assert Path(destination) != path, "recovered original target was rewritten"
        return original_replace(source, destination)

    with mock.patch.object(g, "fsync_directory", side_effect=synced), \
            mock.patch.object(installer, "_service_target", side_effect=checked), \
            mock.patch.object(installer, "_record_once", side_effect=recorded), \
            mock.patch.object(os, "replace", side_effect=no_replacement), \
            mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("new credential")):
        action(case.service_bundle)
    assert "progress" in events and case.service_receipt.exists()
    assert (path.read_bytes(), path.stat().st_ino) == before


@pytest.fixture
def retained_service_owner(retained_go_owner):
    # Reuse the actual existing service fixture, choosing the genuine retained
    # transition instead of the intact transition at its installer call.
    case = retained_go_owner
    case.go_bundle = case.retained_bundle
    case.go_plan = case.retained_plan
    with mock.patch.object(installer, "apply_go", side_effect=installer.apply_retained_go) as applied:
        result = service_owner.__wrapped__(case)
        assert applied.call_count == 1
    return result


def test_retained_go_enrolls_and_reconciles_through_actual_service_owner(retained_service_owner, capsys):
    case = retained_service_owner
    assert installer._completed_go_for_service(case.go_bundle)[0]["schema"] == installer.GO_RETAINED_SCHEMA
    test_enrollment_commits_one_private_binding_and_one_scoped_grant(case, capsys)
    assert_retained_history(case)
