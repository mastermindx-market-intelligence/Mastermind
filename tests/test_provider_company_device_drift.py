"""One explicit company credential observation, never ordinary renewal relaxation."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_provider_readiness_terminal_adverse import state, canary, iso, write_json
from tests.test_provider_device_revalidation import passing
from tests import test_provider_readiness_terminal_adverse as prior
from ops.executive_os import provider_readiness as r
from control_plane import executive_privileged_action as action
from control_plane.executive_privileged_broker import PrivilegedBrokerError, ReconciledNotAppliedError
from scripts import mmx_admin

FLAG = "--requalify-company-device-drift-sha256"
KEY = "requalify_company_device_drift_sha256"


@pytest.fixture
def drift(passing, monkeypatch):
    s = passing
    # Substitute only external OS observations and the fixed incident's digest.
    # Actual receipt bytes, archive, lstat, fsync and CAS remain exercised.
    monkeypatch.setattr(r, "COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256", s.digest, raising=False)
    monkeypatch.setattr(action, "COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256", s.digest, raising=False)
    monkeypatch.setattr(r, "RECEIPT_PATH", s.receipt)
    monkeypatch.setattr(r, "AUTH_PATH", s.tmp / "auth.json")
    s.auth.update(size=138, mtime_ns=10, ctime_ns=11)
    # The broker observer reads the actual old bytes, not the fixture builder's
    # in-memory mappings (which can share the original auth object).
    s.document = json.loads(s.receipt.read_bytes())
    s.identity = {**s.identity, "credential_lstat": dict(s.auth)}
    write_json(s.identity_path, s.identity)
    return s


def cli(s, command, *, digest=None, **changes):
    args = [command, "--receipt", str(s.receipt), "--auth", str(r.AUTH_PATH),
            "--expected-kind", changes.get("kind", "device-auth"),
            "--workspace-binding-class", changes.get("binding", r.COMPANY_WORKSPACE_BINDING_CLASS),
            "--credential-expires-at", changes.get("deadline", s.deadline), FLAG, digest or s.digest]
    if command == "reserve":
        args += ["--identity-json", str(s.identity_path)]
    return r.main(args)


def request(s, **changes):
    raw = prior.request(s)
    raw["request_id"] = "req-company-device-drift"
    del raw["args"]["requalify_terminal_adverse_sha256"]
    raw["args"][KEY] = s.digest
    raw["args"].update(changes)
    return raw


def test_explicit_check_accepts_only_metadata_drift_without_writing(drift):
    s = drift
    before = s.receipt.read_bytes()
    assert cli(s, "reuse") == 7
    assert s.receipt.read_bytes() == before
    assert not list(s.tmp.glob("*.superseded-*"))


def test_ordinary_renewal_still_rejects_current_metadata_drift(drift):
    from tests.test_provider_device_revalidation import cli as renew
    assert renew(drift, "reuse") == 2
    assert renew(drift, "reuse", explicit=False) == 2
    assert not list(drift.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("field", ["device", "inode", "uid", "gid", "mode", "nlink"])
def test_replaced_or_unsafe_credential_cannot_use_incident_transition(drift, field):
    drift.auth[field] += 1
    assert cli(drift, "reuse") == 2
    assert not list(drift.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("change", ["no_drift", "binary", "not_expired", "reserved", "wrong_kind", "wrong_binding"])
def test_ineligible_predecessors_do_not_reserve(drift, monkeypatch, change):
    s = drift
    if change == "no_drift": s.auth.update(s.document["credential_lstat"])
    elif change == "binary": s.current["inode"] += 1
    else:
        d = copy.deepcopy(s.document)
        if change == "not_expired":
            d["credential_expires_at"] = d["readiness_expires_at"] = iso(datetime.now(UTC) + timedelta(hours=1))
        elif change == "reserved": d.update(passed=False, refusal="canary_reserved", inference_canary=None)
        elif change == "wrong_kind": d["expected_credential_kind"] = "service-account"
        else: d["workspace_binding_class"] = r.PERSONAL_PRO_WORKER_BINDING_CLASS
        write_json(s.receipt, d)
        s.digest = hashlib.sha256(s.receipt.read_bytes()).hexdigest()
        monkeypatch.setattr(r, "COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256", s.digest)
    before = s.receipt.read_bytes()
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == before
    assert not list(s.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("minutes", [0, 30, 61, 120])
def test_drift_qualification_horizon_is_bounded(drift, minutes):
    assert cli(drift, "reserve", deadline=iso(datetime.now(UTC) + timedelta(minutes=minutes))) == 2
    assert not list(drift.tmp.glob("*.superseded-*"))


def test_wrong_preimage_never_changes_live_receipt(drift):
    before = drift.receipt.read_bytes()
    assert cli(drift, "reserve", digest="a" * 64) == 2
    assert drift.receipt.read_bytes() == before
    assert not list(drift.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("flag,path", [("--receipt", "/other/readiness.json"),
                                     ("--auth", "/other/auth.json"),
                                     ("--binary", "/other/codex")])
def test_low_level_path_overrides_cannot_qualify_another_realm(drift, flag, path):
    before = drift.receipt.read_bytes()
    argv = ["reuse", "--receipt", str(drift.receipt), "--auth", str(r.AUTH_PATH),
            "--expected-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", drift.deadline, FLAG, drift.digest, flag, path]
    assert r.main(argv) == 2
    assert drift.receipt.read_bytes() == before


def test_finalization_metadata_drift_burns_reservation_instead_of_retry(drift):
    s = drift
    assert cli(s, "reserve") == 0
    cp = s.tmp / "canary.json"
    write_json(cp, canary(True))
    s.auth["mtime_ns"] += 1
    assert r.main(["finalize", "--receipt", str(s.receipt), "--auth", str(r.AUTH_PATH),
        "--post-identity-json", str(s.identity_path), "--post-identity-command-status", "0",
        "--canary-json", str(cp), "--canary-command-status", "0", "--expected-kind", "device-auth",
        "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline]) == 2
    final = s.receipt.read_bytes()
    assert json.loads(final)["passed"] is False
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == final


@pytest.mark.parametrize("change", ["failed", "refusal", "stale", "plan", "credential", "binary"])
def test_fresh_company_identity_must_pass_before_reservation(drift, change):
    s = drift
    d = copy.deepcopy(s.identity)
    if change == "failed": d.update(passed=False, refusal="company_plan_required")
    elif change == "refusal": d["refusal"] = "company_plan_required"
    elif change == "stale": d["observed_at"] = iso(datetime.now(UTC) - timedelta(minutes=10))
    elif change == "plan": d["plan_type"] = "pro"
    elif change == "credential": d["credential_lstat"]["mtime_ns"] += 1
    else: d["codex_binary"]["inode"] += 1
    write_json(s.identity_path, d)
    before = s.receipt.read_bytes()
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == before
    assert not list(s.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("passed", [True, False])
def test_one_reservation_preserves_old_pass_and_never_authorizes_second_canary(drift, passed):
    s = drift
    before = s.receipt.read_bytes()
    assert cli(s, "reserve") == 0
    reserved = s.receipt.read_bytes()
    assert json.loads(reserved)["refusal"] == "canary_reserved"
    archive, = s.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == before
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == reserved
    cp = s.tmp / "canary.json"
    write_json(cp, canary(passed))
    assert r.main(["finalize", "--receipt", str(s.receipt), "--auth", str(r.AUTH_PATH),
                   "--post-identity-json", str(s.identity_path), "--post-identity-command-status", "0",
                   "--canary-json", str(cp), "--canary-command-status", "0" if passed else "1",
                   "--expected-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
                   "--credential-expires-at", s.deadline]) == (0 if passed else 2)
    final = s.receipt.read_bytes()
    assert json.loads(final)["passed"] is passed
    assert json.loads(final)["credential_lstat"] == s.auth
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == final
    assert archive.read_bytes() == before


def test_receipt_race_after_archive_preserves_newer_state(drift, monkeypatch):
    s = drift
    real = r._persist_superseded_receipt
    changed = {**s.document, "passed": False, "refusal": "canary_reserved"}
    def race(*args, **kwargs):
        real(*args, **kwargs)
        write_json(s.receipt, changed)
    monkeypatch.setattr(r, "_persist_superseded_receipt", race)
    assert cli(s, "reserve") == 2
    assert json.loads(s.receipt.read_bytes()) == changed


@pytest.mark.parametrize("change", ["credential", "binary"])
def test_current_identity_race_during_archive_never_reserves(drift, monkeypatch, change):
    s = drift
    before = s.receipt.read_bytes()
    real = r._persist_superseded_receipt
    def race(*args, **kwargs):
        real(*args, **kwargs)
        if change == "credential": s.auth["mtime_ns"] += 1
        else: s.current["inode"] += 1
    monkeypatch.setattr(r, "_persist_superseded_receipt", race)
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == before


def test_closed_client_preserves_explicit_digest_and_broker_executes_once(drift, monkeypatch):
    s = drift
    raw = mmx_admin.build_request(["executive.worker_auth.verify_ready", "--request-id", "req-company-device-drift",
        "--expected-credential-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline, FLAG, s.digest])
    assert raw == request(s)
    assert action.build_argv(action.validate_request(raw), s.tmp)[-2:] == (FLAG, s.digest)
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request(["status", "--request-id", "req-company-device-drift", FLAG, s.digest])
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: raw)
    broker, _, _, calls = prior.broker_fixture(s, write_marker=False)
    assert broker.handle(raw, peer_uid=501) == broker.handle(raw, peer_uid=501)
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [
    {"slot_id": "codex-pro-01"}, {"expected_credential_kind": "service-account"},
    {KEY: "a" * 64}, {"renew_device_revalidation_sha256": "a" * 64},
    {"workspace_binding_class": "personal-pro-dedicated-worker-attested"},
])
def test_closed_request_refuses_other_incidents_or_realms(drift, changes):
    with pytest.raises(action.PrivilegedActionError):
        action.validate_request(request(drift, **changes))


@pytest.mark.parametrize("extras,status", [
    (["--slot-id", "codex-pro-01"], 65), (["--worker-uid", "454"], 64),
    (["--provider-home", "/other/provider-home"], 64),
    (["--renew-device-revalidation-sha256", "a" * 64], 64),
])
def test_provisioner_rejects_slot_and_policy_overrides_before_host_effect(extras, status):
    command = ["/bin/bash", str(Path(__file__).resolve().parents[1] / "ops/executive_os/provision-worker-auth.sh"),
               "--verify-ready", "--expected-credential-kind", "device-auth",
               "--workspace-binding-class", "company-workspace-admin-attested",
               "--credential-expires-at", "2026-10-11T12:00:00Z", FLAG,
               "654abd66f6baef1b610a6c03fafe85f76fd81ed646266d3ff90db3c6e85e2a7d", *extras]
    completed = subprocess.run(command, capture_output=True, check=False, timeout=10)
    assert completed.returncode == status
    assert b"run as root" not in completed.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="Valid parse must stop at unprivileged root requirement.")
def test_provisioner_accepts_closed_option_then_stops_at_root_boundary():
    command = ["/bin/bash", str(Path(__file__).resolve().parents[1] / "ops/executive_os/provision-worker-auth.sh"),
               "--verify-ready", "--expected-credential-kind", "device-auth",
               "--workspace-binding-class", "company-workspace-admin-attested",
               "--credential-expires-at", "2026-10-11T12:00:00Z", FLAG,
               "654abd66f6baef1b610a6c03fafe85f76fd81ed646266d3ff90db3c6e85e2a7d"]
    completed = subprocess.run(command, capture_output=True, check=False, timeout=10)
    assert completed.returncode == 77
    assert b"root" in completed.stderr


def test_unknown_current_operation_reconciles_same_marker_without_replaying(drift, monkeypatch):
    s = drift
    target = request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: target)
    broker, raw, marker, calls = prior.broker_fixture(s)
    record, replayed = broker.reconcile_not_applied(raw, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert broker.inflight_path(target["request_id"]).read_bytes() == marker
    with pytest.raises(ReconciledNotAppliedError): broker.handle(target, peer_uid=501)
    assert calls == []


def test_new_transition_does_not_reconcile_old_renewal_with_metadata_drift(drift, monkeypatch):
    from tests.test_provider_device_revalidation import request as renewal_request
    s = drift
    old_target = renewal_request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: old_target)
    broker, raw, marker, calls = prior.broker_fixture(s)
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(raw, peer_uid=501)
    assert broker.inflight_path(old_target["request_id"]).read_bytes() == marker
    assert calls == []


@pytest.mark.parametrize("change", ["lock", "process", "digest", "credential", "binary"])
def test_reconciliation_never_closes_uncertain_or_moved_input(drift, monkeypatch, change):
    s = drift
    target = request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: target)
    changes = {}
    if change == "lock": changes["readiness_transaction_lock_present"] = True
    elif change == "process": changes["verify_ready_processes"] = ["123 helper"]
    elif change == "digest": changes["readiness_receipt_sha256"] = "a" * 64
    elif change == "credential": changes["current_auth_identity"] = {**s.auth, "inode": 999}
    else: changes["current_binary_identity"] = s.old
    broker, raw, marker, calls = prior.broker_fixture(s, changes)
    with pytest.raises(PrivilegedBrokerError): broker.reconcile_not_applied(raw, peer_uid=501)
    assert broker.inflight_path(target["request_id"]).read_bytes() == marker
    assert calls == []
