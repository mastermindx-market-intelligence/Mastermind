"""Explicit operational-deadline renewal preserves evidence and requires new proof."""
from __future__ import annotations
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from tests import test_provider_readiness_terminal_adverse as prior
from tests.test_provider_readiness_terminal_adverse import state, canary, iso, write_json
from ops.executive_os import provider_readiness as r
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA, STATUS_REQUEST_SCHEMA, PrivilegedActionError,
    build_argv, canonical_request_bytes, validate_request,
)
from control_plane.executive_privileged_broker import (
    PrivilegedBrokerError, ReconciledNotAppliedError,
)
from scripts import mmx_admin


@pytest.fixture
def passing(state):
    s = state
    d = r.compose_receipt(
        identity=s.identity, canary=canary(True), auth_identity=s.auth,
        binary_identity=s.current, expected_kind="device-auth",
        workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS,
        credential_expires_at=s.deadline, canary_command_status=0,
    )
    observed = iso(datetime.now(UTC) - timedelta(minutes=56))
    deadline = iso(datetime.now(UTC) - timedelta(minutes=1))
    d.update(observed_at=observed, credential_expires_at=deadline,
             readiness_expires_at=deadline)
    d["provider_identity"]["observed_at"] = observed
    d["inference_canary"]["observed_at"] = observed
    s.document = d
    write_json(s.receipt, d)
    s.digest = hashlib.sha256(s.receipt.read_bytes()).hexdigest()
    return s


def cli(s, command, *, explicit=True, digest=None, deadline=None):
    argv = [command, "--receipt", str(s.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", deadline or s.deadline]
    if command == "reserve":
        argv += ["--identity-json", str(s.identity_path)]
    if explicit:
        argv += ["--renew-device-revalidation-sha256", digest or s.digest]
    return r.main(argv)


def request(s, **changes):
    raw = prior.request(s)
    raw["request_id"] = "req-device-revalidation"
    del raw["args"]["requalify_terminal_adverse_sha256"]
    raw["args"]["renew_device_revalidation_sha256"] = s.digest
    raw["args"].update(changes)
    return raw


def test_expired_pass_cannot_extend_itself_and_explicit_check_is_readonly(passing):
    s = passing
    raw = s.receipt.read_bytes()
    assert cli(s, "reuse", explicit=False) == 2
    assert cli(s, "reserve", explicit=False) == 2
    assert cli(s, "reuse") == 6
    assert s.receipt.read_bytes() == raw
    assert not list(s.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("minutes", [0, 29, 61, 120])
def test_new_deadline_is_bounded(passing, minutes):
    assert cli(passing, "reserve", deadline=iso(datetime.now(UTC) + timedelta(minutes=minutes))) == 2
    assert not list(passing.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("change", [
    "not_due", "adverse", "reserved", "unknown", "kind", "binding", "credential",
    "device", "binary", "canary", "identity_binding", "refusal", "extra",
])
def test_bad_predecessor_refuses_without_archiving(passing, change):
    s = passing
    d = copy.deepcopy(s.document)
    if change == "not_due":
        d["credential_expires_at"] = d["readiness_expires_at"] = iso(datetime.now(UTC) + timedelta(hours=1))
    elif change == "adverse": d.update(passed=False, refusal="provider_turn_failed")
    elif change == "reserved": d.update(passed=False, refusal="canary_reserved", inference_canary=None)
    elif change == "unknown": d["inference_canary"] = None
    elif change == "kind": d["expected_credential_kind"] = "service-account"
    elif change == "binding": d["workspace_binding_class"] = "personal-pro-worker-admin-attested"
    elif change == "credential": d["credential_lstat"]["inode"] += 1
    elif change == "device": d["credential_lstat"]["device"] += 1
    elif change == "binary": d["codex_binary"]["inode"] += 1
    elif change == "canary": d["inference_canary"]["passed"] = False
    elif change == "identity_binding": d["provider_identity"]["workspace_binding_class"] = "personal-pro-worker-admin-attested"
    elif change == "refusal": d["provider_identity"]["refusal"] = "not_ready"
    else: d["permit_renewal"] = True
    write_json(s.receipt, d)
    raw = s.receipt.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert cli(s, "reuse", digest=digest) == 2
    assert cli(s, "reserve", digest=digest) == 2
    assert s.receipt.read_bytes() == raw
    assert not list(s.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("change", ["stale", "plan", "credential"])
def test_fresh_provider_identity_required_before_reservation(passing, change):
    s = passing
    identity = copy.deepcopy(s.identity)
    if change == "stale": identity["observed_at"] = iso(datetime.now(UTC) - timedelta(minutes=10))
    elif change == "plan": identity["plan_type"] = "enterprise"
    else: identity["credential_lstat"]["inode"] += 1
    write_json(s.identity_path, identity)
    assert cli(s, "reserve") == 2
    assert not list(s.tmp.glob("*.superseded-*"))


@pytest.mark.parametrize("passed", [True, False])
def test_one_reservation_and_finalization_preserve_old_pass(passing, passed):
    s = passing
    original = s.receipt.read_bytes()
    assert cli(s, "reserve") == 0
    reserved = s.receipt.read_bytes()
    archive, = s.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == original
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == reserved
    cp = s.tmp / "canary.json"
    write_json(cp, canary(passed))
    result = r.main([
        "finalize", "--receipt", str(s.receipt), "--post-identity-json", str(s.identity_path),
        "--post-identity-command-status", "0", "--canary-json", str(cp),
        "--canary-command-status", "0" if passed else "1",
        "--expected-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline,
    ])
    assert result == (0 if passed else 2)
    final = s.receipt.read_bytes()
    assert json.loads(final)["passed"] is passed
    assert json.loads(final)["credential_expires_at"] == s.deadline
    assert cli(s, "reserve", digest=hashlib.sha256(final).hexdigest()) == 2
    assert archive.read_bytes() == original


def test_digest_and_archive_race_preserve_newer_state(passing, monkeypatch):
    s = passing
    original = s.receipt.read_bytes()
    assert cli(s, "reserve", digest="a" * 64) == 2
    assert s.receipt.read_bytes() == original
    real = r._persist_superseded_receipt
    changed = {**s.document, "refusal": "canary_reserved", "passed": False}
    def race(*args, **kwargs):
        real(*args, **kwargs)
        write_json(s.receipt, changed)
    monkeypatch.setattr(r, "_persist_superseded_receipt", race)
    assert cli(s, "reserve") == 2
    assert json.loads(s.receipt.read_bytes()) == changed


def test_archive_crash_is_recoverable_without_erasing_evidence(passing, monkeypatch):
    s = passing
    old = s.receipt.read_bytes()
    real = r.os.replace
    def fail(src, dst):
        if Path(dst) == s.receipt: raise OSError("injected pre-replace failure")
        return real(src, dst)
    monkeypatch.setattr(r.os, "replace", fail)
    assert cli(s, "reserve") == 2
    archive, = s.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == s.receipt.read_bytes() == old
    monkeypatch.setattr(r.os, "replace", real)
    assert cli(s, "reserve") == 0


def test_typed_client_and_broker_preserve_exact_new_grant(passing, monkeypatch):
    s = passing
    raw = mmx_admin.build_request([
        "executive.worker_auth.verify_ready", "--request-id", "req-device-revalidation",
        "--expected-credential-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline, "--renew-device-revalidation-sha256", s.digest,
    ])
    assert raw == request(s)
    assert build_argv(validate_request(raw), s.tmp)[-2:] == ("--renew-device-revalidation-sha256", s.digest)
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request(["status", "--request-id", "req-status", "--renew-device-revalidation-sha256", s.digest])
    original_request = request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: original_request)
    broker, _, _, calls = prior.broker_fixture(s, write_marker=False)
    assert broker.handle(raw, peer_uid=501) == broker.handle(raw, peer_uid=501)
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [
    {"expected_credential_kind": "service-account"},
    {"slot_id": "codex-pro-01"},
    {"renew_device_revalidation_sha256": "A" * 64},
    {"requalify_terminal_adverse_sha256": "a" * 64},
])
def test_closed_request_refuses_ambiguous_or_noncompany_renewal(passing, changes):
    with pytest.raises(PrivilegedActionError):
        validate_request(request(passing, **changes))


def test_unknown_broker_effect_reconciles_exact_predecessor_without_replay(passing, monkeypatch):
    s = passing
    target = request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: target)
    broker, raw, marker, calls = prior.broker_fixture(s)
    record, replayed = broker.reconcile_not_applied(raw, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert broker.reconcile_not_applied(raw, peer_uid=501) == (record, True)
    with pytest.raises(ReconciledNotAppliedError):
        broker.handle(target, peer_uid=501)
    assert calls == []
    assert broker.inflight_path(target["request_id"]).read_bytes() == marker


@pytest.mark.parametrize("change", ["lock", "process", "digest", "auth", "binary"])
def test_reconciliation_refuses_effect_uncertainty(passing, monkeypatch, change):
    s = passing
    target = request(s)
    monkeypatch.setattr(prior, "request", lambda *_a, **_k: target)
    evidence = {}
    if change == "lock": evidence["readiness_transaction_lock_present"] = True
    elif change == "process": evidence["verify_ready_processes"] = ["123 helper"]
    elif change == "digest": evidence["readiness_receipt_sha256"] = "b" * 64
    elif change == "auth": evidence["current_auth_identity"] = {**s.auth, "inode": 333}
    else: evidence["current_binary_identity"] = s.old
    broker, raw, marker, calls = prior.broker_fixture(s, evidence)
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(raw, peer_uid=501)
    assert calls == []
    assert broker.inflight_path(target["request_id"]).read_bytes() == marker
