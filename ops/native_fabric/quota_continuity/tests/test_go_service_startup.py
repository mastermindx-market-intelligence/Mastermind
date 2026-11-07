"""Completed enrollment reaches the exact B/A startup without a new auth owner."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest import mock

import pytest

from test_go_native_stage import builds, native_stage, ROOT, g, installer, loaded_entry
from test_go_native_install import go_owner
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import service_owner, prepare, unchanged_ingress, selected_purpose


def environment(monkeypatch, case):
    for key in list(os.environ):
        if key.startswith(("GO_", "POOL_")) or key == "REMOTE_SUB_HERE":
            monkeypatch.delenv(key)
    monkeypatch.setenv("GO_ACCOUNTS_PATH", str(case.profile))
    monkeypatch.setenv("GO_STATE_DIR", str(case.ext / "go_shim"))


def inspect(entry, case):
    return entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)


def boot(entry, case):
    return entry.main(verified_root=case.published.release, verified_metadata=case.published.meta)

def test_selected_completed_enrollment_reaches_actual_main_without_current_selection_reads(service_owner, monkeypatch):
    case = service_owner
    purpose = selected_purpose(case)
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        def original_main(*, application_broker, application_services, application_selection_profile):
            assert type(application_broker) is startup.broker_module.Broker
            assert Path(application_broker.db_path) == case.ext / "broker/leases.sqlite"
            assert application_services[0].selection_purpose.document == purpose
            view = application_services[0].selection_purpose.document
            view["task"]["needs"].append("vision")
            assert application_services[0].selection_purpose.document == purpose
            profile = application_selection_profile.document
            assert profile["source_generation"] == startup.generation
            assert profile["ingress_digest"] == case.published.meta["files"]["ext/go_application_handler.py"]
            assert profile["pool"] == "go" and profile["protocol"] == "chat"
            return 43
        with mock.patch.object(startup.handler, "main", side_effect=original_main) as main, \
             mock.patch.object(sys.modules["pick"], "read_application_policy", side_effect=AssertionError("startup policy")), \
             mock.patch.object(sys.modules["pool_ledger"], "read_recent", side_effect=AssertionError("startup quality")):
            assert boot(entry, case) == 43
            assert boot(entry, case) == 43
            assert main.call_count == 2
    unchanged_ingress(case)


def test_selected_completed_purpose_cannot_be_overridden_in_explicit_startup(service_owner, monkeypatch):
    case = service_owner
    purpose = selected_purpose(case)
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        completed = entry.load_completed_application_startup(startup)
        service = completed[0][0]
        purpose["purpose_id"] = "different-purpose"
        changed = startup.handler.ApplicationServiceBinding(service.principal_id, service.host,
            service.workload, service.credential_ref, service.credential,
            selection_purpose=startup.handler.ApplicationSelectionPurpose(purpose))
        with mock.patch.object(startup.handler, "main", side_effect=AssertionError("override started service")), pytest.raises(ValueError):
            entry.main(verified_root=case.published.release, verified_metadata=case.published.meta,
                application_services=(changed,), application_host=completed[1], application_account_path=completed[2])


def test_selected_quality_owner_rejects_an_undeclared_parent_symlink_alias(service_owner, monkeypatch):
    case = service_owner
    selected_purpose(case)
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    alias = case.root / "unqualified-quality-alias"
    alias.symlink_to(case.accounts.parent, target_is_directory=True)
    monkeypatch.setenv("POOL_LEDGER_PATH", str(alias / "ledger.jsonl"))
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        with mock.patch.object(startup.handler, "main", side_effect=AssertionError("alias started service")), \
             mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("alias constructed owner")), \
             pytest.raises(ValueError, match="selection owner mapping"):
            boot(entry, case)


def test_actual_inspection_never_reads_enrolled_credential_or_constructs_broker(service_owner):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        original = entry._regular
        def no_private(path, **kwargs):
            assert Path(path).name not in {"application-service.json", "go-service-enrollment-v1.json",
                                           ".go-service-enrollment-v1.json"}
            return original(path, **kwargs)
        with mock.patch.object(entry, "_regular", side_effect=no_private), \
                mock.patch.object(sqlite3, "connect", side_effect=AssertionError("inspection opened database")):
            startup = inspect(entry, case)
            assert startup.policy_snapshot.__file__ == str(case.published.release / "ext/fabric_policy_snapshot.py")
    unchanged_ingress(case)


def test_actual_main_loads_completed_service_into_same_B_and_original_A_database(service_owner, monkeypatch):
    case = service_owner
    prepare(case)
    receipt = installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    db_identity = (case.ext / "broker/leases.sqlite").stat().st_ino
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        def original_main(*, application_broker, application_services):
            assert type(application_broker) is startup.broker_module.Broker
            assert application_broker.this_host == "fixture-native"
            assert Path(application_broker.db_path) == case.ext / "broker/leases.sqlite"
            assert Path(application_broker.lock_path) == case.ext / "broker/leases.lock"
            assert len(application_services) == 1
            service = application_services[0]
            assert service.principal_id == "macro-admin" and service.host == "fixture-vps"
            assert service.workload == "admin-site-interactive"
            assert service.credential_ref == "MACRO_FABRIC_APPLICATION_TOKEN"
            assert g.digest(case.binding.read_bytes()) == receipt["binding_sha256"]
            return 37
        with mock.patch.object(startup.handler, "main", side_effect=original_main) as main, \
                mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("startup minted credential")):
            assert boot(entry, case) == 37
            assert boot(entry, case) == 37
            assert main.call_count == 2
    assert (case.ext / "broker/leases.sqlite").stat().st_ino == db_identity
    unchanged_ingress(case)


@pytest.mark.parametrize("fault", ["intent-only", "missing-binding", "missing-receipt", "binding-mode",
    "binding-hardlink", "binding-symlink", "receipt-duplicate", "scope", "foreign-intent"])
def test_partial_or_corrupt_enrollment_never_falls_back_to_another_startup(service_owner, monkeypatch, fault):
    case = service_owner
    prepare(case)
    if fault == "intent-only":
        original = g.atomic_bytes
        def stop(path, raw, mode):
            original(path, raw, mode)
            if Path(path) == case.intent:
                raise OSError("fixture after intent")
        with mock.patch.object(g, "atomic_bytes", side_effect=stop), pytest.raises(OSError):
            installer.apply_go_service_enrollment(case.service_bundle)
    else:
        installer.apply_go_service_enrollment(case.service_bundle)
        if fault == "missing-binding":
            case.binding.unlink()
        elif fault == "missing-receipt":
            case.service_receipt.unlink()
        elif fault == "binding-mode":
            case.binding.chmod(0o644)
        elif fault == "binding-hardlink":
            os.link(case.binding, case.root / "other-binding")
        elif fault == "binding-symlink":
            other = case.root / "other-binding"
            case.binding.rename(other)
            case.binding.symlink_to(other)
        elif fault == "receipt-duplicate":
            raw = case.service_receipt.read_bytes()
            case.service_receipt.write_bytes(raw[:-2] + b',"schema":"foreign"}\n')
        elif fault == "scope":
            value = json.loads(case.binding.read_bytes())
            value["scope"]["caller_host"] = "other-vps"
            g.atomic_bytes(case.binding, g.canonical(value) + b"\n", 0o600)
        else:
            value = json.loads(case.intent.read_bytes())
            value["plan_digest"] = "0" * 64
            case.intent.write_bytes(g.canonical(value) + b"\n")
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("bad startup constructed broker")), \
                mock.patch.object(startup.handler, "main", side_effect=AssertionError("bad startup started legacy")), \
                pytest.raises((ValueError, OSError)):
            boot(entry, case)


@pytest.mark.parametrize("changed", ["expired", "disabled", "malformed", "unrelated"])
def test_stable_service_auth_survives_accounts_changes_and_A_recovers_original_effect(service_owner, monkeypatch, changed):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        stable = entry.load_completed_application_startup(startup)
        clock = [case.specification["grant"]["expires_at"] - 899]
        def broker():
            return startup.broker_module.Broker(db_path=str(startup.paths["db_path"]),
                lock_path=str(startup.paths["lock_path"]), accounts_path=str(case.accounts),
                status_json=str(startup.paths["status_json"]), hosts_path=str(startup.paths["hosts_path"]),
                this_host="fixture-native", now_fn=lambda: clock[0], check_pid=False, external_gates=False)
        args = dict(principal_id="macro-admin", caller_host="fixture-vps", workload="admin-site-interactive",
                    turn_id="original-turn", pool="go", model="fixture-model",
                    expected_credential_ref="MACRO_FABRIC_APPLICATION_TOKEN")
        with startup.yaml_runtime.held_yaml(startup.yaml_archive, startup.yaml_provenance, startup.yaml_check):
            first = broker()
            admitted = first.begin_application_turn(**args)
            assert admitted["ok"] and admitted["disposition"] == "admitted"
            request = first.prepare_application_request(principal_id="macro-admin", turn_id="original-turn",
                request_id="original-step", request_digest="a" * 64)
            assert request["dispatch_permitted"]
            document = json.loads(case.accounts.read_bytes())
            if changed == "expired":
                document["application_grants"][0]["expires_at"] = clock[0] - 1
            elif changed == "disabled":
                document["application_grants"][0]["enabled"] = False
            elif changed == "unrelated":
                document["operator_note"] = {"legitimate_change": True}
            case.accounts.write_text("not a valid accounts mapping" if changed == "malformed" else json.dumps(document))
            assert entry.load_completed_application_startup(startup) == stable
            restarted = broker()
            recovered = restarted.recover_application_request(principal_id="macro-admin", turn_id="original-turn",
                request_id="original-step", request_digest="a" * 64)
            assert recovered["dispatch_id"] == request["dispatch_id"]
            assert recovered["dispatch_permitted"] is False
            assert recovered["disposition"] == "pending"
            if changed != "unrelated":
                with pytest.raises(startup.broker_module.ApplicationAdmissionError):
                    restarted.begin_application_turn(**dict(args, turn_id="new-turn"))
            else:
                assert restarted.begin_application_turn(**dict(args, turn_id="new-turn"))["ok"]
        with mock.patch.object(startup.handler, "main", return_value=41) as main:
            assert boot(entry, case) == 41
            assert main.call_args.kwargs["application_services"] == stable[0]


def test_startup_does_not_depend_on_retained_preparation_directory(service_owner, monkeypatch):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    # The native finite transaction retains its private bundle for reconciliation,
    # but service startup authenticates only its fixed original-owner artifacts.
    case.service_bundle.rename(case.root / "retained-review-moved")
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        with mock.patch.object(startup.handler, "main", return_value=43):
            assert boot(entry, case) == 43


def test_enrolled_binding_cannot_be_overridden_by_explicit_startup_or_environment(service_owner, monkeypatch):
    case = service_owner
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    environment(monkeypatch, case)
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = inspect(entry, case)
        stable = entry.load_completed_application_startup(startup)
        with mock.patch.object(startup.broker_module, "Broker", side_effect=AssertionError("override constructed broker")):
            with pytest.raises(ValueError, match="conflicts"):
                entry.main(verified_root=case.published.release, verified_metadata=case.published.meta,
                    application_services=stable[0], application_host="other-native", application_account_path=case.profile)
            monkeypatch.setenv("GO_ACCOUNTS_PATH", str(case.root / "other-profile/accounts.json"))
            with pytest.raises(ValueError, match="conflicts"):
                boot(entry, case)
