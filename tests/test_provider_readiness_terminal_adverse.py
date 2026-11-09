"""Explicit old-generation qualification: one reservation, durable adverse evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import provider_readiness as r
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA, STATUS_REQUEST_SCHEMA, PrivilegedActionError,
    build_argv, canonical_request_bytes, validate_request,
)
from control_plane.executive_privileged_broker import (
    PrivilegedActionBroker, PrivilegedBrokerConfig, PrivilegedBrokerError,
    ReconciledNotAppliedError, RECONCILE_REQUEST_SCHEMA,
)
from scripts import mmx_admin


def iso(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def canary(passed=False):
    return {
        "schema_version": r.CANARY_SCHEMA, "canary_id": "canary-123456789abc",
        "observed_at": r.now_iso(), "codex_version": r.CODEX_VERSION,
        "codex_sha256": r.CODEX_SHA256, "codex_team_identifier": r.CODEX_TEAM_ID,
        "model": r.PRODUCTION_MODEL, "exit_code": 0 if passed else 1,
        "timed_out": False, "terminal_event_class": "turn_completed" if passed else "provider_turn_failed",
        "result_valid": passed, "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64,
        "provider_error_message_count": 0, "provider_error_message_sha256": None,
        "provider_error_terms": [], "workspace_capability_outcome": "inert_untrusted_workspace",
        "workspace_selection_mechanism": "none", "forced_chatgpt_workspace_id_applied": False,
        "passed": passed, "refusal": None if passed else "provider_turn_failed",
    }


def write_json(path, value):
    if path.exists():
        path.chmod(0o600)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    path.chmod(0o400)


@pytest.fixture
def state(tmp_path, monkeypatch):
    os.chown(tmp_path, -1, os.getgid())  # macOS inherits the parent directory group.
    auth = dict(device=1, inode=2, uid=451, gid=451, mode=0o600,
                size=123, mtime_ns=4, ctime_ns=5, nlink=1)
    current = {**auth, "uid": 0, "gid": 0, "mode": 0o555,
               "path": str(r.CODEX_BINARY), "version": r.CODEX_VERSION,
               "sha256": r.CODEX_SHA256, "team_identifier": r.CODEX_TEAM_ID}
    old = {**current, "path": str(r.CODEX_BINARY.with_name("codex-0.147.0")),
           "version": r.REQUALIFICATION_PREDECESSOR_VERSION,
           "sha256": r.REQUALIFICATION_PREDECESSOR_SHA256}
    identity = {
        "schema_version": r.IDENTITY_SCHEMA, "passed": True, "refusal": None,
        "expected_credential_kind": "device-auth", "auth_mode": "chatgpt",
        "account_type": "chatgpt", "plan_type": "self_serve_business_prolite",
        "requires_openai_auth": True, "workspace_binding_class": r.WORKSPACE_BINDING_CLASS,
        "observed_at": r.now_iso(), "codex_binary": current, "credential_lstat": auth,
        "forced_chatgpt_workspace_id_applied": False,
    }
    deadline = iso(datetime.now(UTC) + timedelta(minutes=55))
    document = r.compose_receipt(
        identity=identity, canary=canary(), auth_identity=auth, binary_identity=current,
        expected_kind="device-auth", workspace_binding_class=r.WORKSPACE_BINDING_CLASS,
        credential_expires_at=deadline, canary_command_status=1,
    )
    past = datetime.now(UTC) - timedelta(days=1)
    document.update(codex_binary=old, observed_at=iso(past),
                    credential_expires_at=iso(past + timedelta(hours=12)),
                    readiness_expires_at=iso(past + timedelta(hours=12)))
    document["provider_identity"] = {**identity, "codex_binary": old, "observed_at": iso(past)}
    document["inference_canary"].update(codex_version=old["version"], codex_sha256=old["sha256"],
                                        observed_at=iso(past))
    receipt = tmp_path / "readiness.json"
    identity_path = tmp_path / "identity.json"
    write_json(receipt, document)
    write_json(identity_path, identity)
    # Only OS principal/ACL and installed-binary observation are substituted.
    # Real file bytes, chmod, lstat, fsync, archive and atomic CAS run unchanged.
    monkeypatch.setattr(r, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(r, "_assert_no_macos_acl", lambda path: None)
    monkeypatch.setattr(r, "receipt_storage_contract", lambda **kw: (os.getuid(), os.getgid(), 0o400))
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **k: dict(auth))
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(current))
    monkeypatch.setattr(r, "_attested_predecessor_identity", lambda: dict(old))
    result = SimpleNamespace(auth=auth, current=current, old=old, identity=identity, document=document,
                             receipt=receipt, identity_path=identity_path, deadline=deadline, tmp=tmp_path)
    result.digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return result


def cli(s, command, *, explicit=True, **kwargs):
    args = [command, "--receipt", str(s.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", kwargs.get("deadline", s.deadline)]
    if command == "reserve":
        args += ["--identity-json", str(s.identity_path)]
    if explicit:
        args += ["--requalify-terminal-adverse-sha256", kwargs.get("digest", s.digest)]
    return r.main(args)


def test_default_stays_closed_and_explicit_path_is_read_only_until_reservation(state):
    original = state.receipt.read_bytes()
    assert cli(state, "reuse", explicit=False) == 2
    assert cli(state, "reserve", explicit=False) == 2
    assert cli(state, "reuse") == 5
    assert state.receipt.read_bytes() == original
    assert list(state.tmp.glob("*.superseded-*")) == []


@pytest.mark.parametrize("change", [
    "passing", "reserved", "absent_canary", "timeout", "signal", "bool_exit",
    "finalization_failure", "unknown_terminal", "canary_refusal", "credential",
    "old_binary", "identity_binary", "identity_credential", "canary_binary",
    "kind", "binding", "extra_field", "future_observation", "component_time",
])
def test_invalid_predecessors_never_reserve_or_archive(state, change):
    d = copy.deepcopy(state.document)
    if change == "passing": d.update(passed=True, refusal=None)
    elif change == "reserved": d.update(refusal="canary_reserved", inference_canary=None)
    elif change == "absent_canary": d["inference_canary"] = None
    elif change == "timeout": d["inference_canary"]["timed_out"] = True
    elif change == "signal": d["inference_canary"]["exit_code"] = -15
    elif change == "bool_exit": d["inference_canary"]["exit_code"] = True
    elif change == "finalization_failure": d["refusal"] = "post_identity_command_failed"
    elif change == "unknown_terminal": d["inference_canary"]["terminal_event_class"] = "unknown"
    elif change == "canary_refusal": d["inference_canary"]["refusal"] = "other"
    elif change == "credential": d["credential_lstat"]["inode"] = 999
    elif change == "old_binary": d["codex_binary"] = state.current
    elif change == "identity_binary": d["provider_identity"]["codex_binary"] = state.current
    elif change == "identity_credential": d["provider_identity"]["credential_lstat"]["inode"] = 999
    elif change == "canary_binary": d["inference_canary"]["codex_sha256"] = r.CODEX_SHA256
    elif change == "kind": d["expected_credential_kind"] = "service-account"
    elif change == "binding": d["workspace_binding_class"] = "personal-pro-worker-admin-attested"
    elif change == "extra_field": d["retry_allowed"] = True
    elif change == "future_observation": d["observed_at"] = iso(datetime.now(UTC) + timedelta(days=1))
    elif change == "component_time": d["inference_canary"]["observed_at"] = r.now_iso()
    write_json(state.receipt, d)
    original = state.receipt.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert state.receipt.read_bytes() == original
    assert list(state.tmp.glob("*.superseded-*")) == []


@pytest.mark.parametrize("digest", ["", "a" * 63, "A" * 64, "z" * 64, "a" * 64])
def test_digest_fence_refuses_without_effect(state, digest):
    original = state.receipt.read_bytes()
    assert cli(state, "reserve", digest=digest) == 2
    assert state.receipt.read_bytes() == original
    assert list(state.tmp.glob("*.superseded-*")) == []


@pytest.mark.parametrize("minutes", [0, 29, 61, 120])
def test_requalification_horizon_is_thirty_to_sixty_minutes(state, minutes):
    assert cli(state, "reserve", deadline=iso(datetime.now(UTC) + timedelta(minutes=minutes))) == 2
    assert list(state.tmp.glob("*.superseded-*")) == []


def test_missing_or_unsafe_old_attestation_refuses(state, monkeypatch):
    def refuse():
        raise r.ReadinessError("requalification_predecessor_attestation_invalid")
    monkeypatch.setattr(r, "_attested_predecessor_identity", refuse)
    assert cli(state, "reserve") == 2
    assert list(state.tmp.glob("*.superseded-*")) == []


@pytest.mark.parametrize("change", ["old_current", "unreviewed_current", "stale_identity", "identity_plan"])
def test_current_generation_and_fresh_identity_are_required(state, monkeypatch, change):
    if change in ("old_current", "unreviewed_current"):
        binary = state.old if change == "old_current" else {**state.current, "sha256": "a" * 64}
        monkeypatch.setattr(r, "current_binary_identity", lambda *a: binary)
    else:
        value = copy.deepcopy(state.identity)
        if change == "stale_identity":
            value["observed_at"] = iso(datetime.now(UTC) - timedelta(minutes=10))
        else:
            value["plan_type"] = "enterprise"
        write_json(state.identity_path, value)
    original = state.receipt.read_bytes()
    assert cli(state, "reserve") == 2
    assert state.receipt.read_bytes() == original
    assert list(state.tmp.glob("*.superseded-*")) == []


@pytest.mark.parametrize("passed", [True, False])
def test_one_reservation_then_final_result_retains_old_bytes_and_burns_generation(state, passed):
    old_bytes = state.receipt.read_bytes()
    assert cli(state, "reserve") == 0
    reserved = state.receipt.read_bytes()
    assert json.loads(reserved)["refusal"] == "canary_reserved"
    archive, = state.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == old_bytes
    assert archive.stat().st_mode & 0o777 == 0o400
    assert cli(state, "reserve") == 2
    assert state.receipt.read_bytes() == reserved
    canary_path = state.tmp / "canary.json"
    write_json(canary_path, canary(passed))
    args = ["finalize", "--receipt", str(state.receipt),
            "--post-identity-json", str(state.identity_path), "--post-identity-command-status", "0",
            "--canary-json", str(canary_path), "--canary-command-status", "0" if passed else "1",
            "--expected-kind", "device-auth", "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", state.deadline]
    assert r.main(args) == (0 if passed else 2)
    final = state.receipt.read_bytes()
    assert json.loads(final)["passed"] is passed
    assert cli(state, "reserve", digest=hashlib.sha256(final).hexdigest()) == 2
    assert state.receipt.read_bytes() == final
    assert archive.read_bytes() == old_bytes


def test_crash_after_archive_before_replace_is_safe_and_recoverable(state, monkeypatch):
    original = state.receipt.read_bytes()
    real_replace = r.os.replace
    def crash(src, dst):
        if Path(dst) == state.receipt:
            raise OSError("simulated power loss before CAS")
        return real_replace(src, dst)
    monkeypatch.setattr(r.os, "replace", crash)
    assert cli(state, "reserve") == 2
    archive, = state.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == state.receipt.read_bytes() == original
    monkeypatch.setattr(r.os, "replace", real_replace)
    assert cli(state, "reserve") == 0
    assert archive.read_bytes() == original


@pytest.mark.parametrize("conflict", ["bytes", "symlink", "mode"])
def test_archive_conflict_preserves_live_evidence(state, conflict):
    original = state.receipt.read_bytes()
    archive = r._superseded_sibling_path(state.receipt, original)
    if conflict == "symlink":
        archive.symlink_to(state.receipt)
    else:
        archive.write_bytes(b"partial" if conflict == "bytes" else original)
        archive.chmod(0o600 if conflict == "mode" else 0o400)
    assert cli(state, "reserve") == 2
    assert state.receipt.read_bytes() == original


def test_receipt_changed_after_archive_is_not_overwritten(state, monkeypatch):
    real_archive = r._persist_superseded_receipt
    changed = {**state.document, "refusal": "canary_reserved"}
    def race(*args, **kwargs):
        real_archive(*args, **kwargs)
        write_json(state.receipt, changed)
    monkeypatch.setattr(r, "_persist_superseded_receipt", race)
    assert cli(state, "reserve") == 2
    assert json.loads(state.receipt.read_bytes()) == changed


def request(s, **changes):
    value = {
        "schema": REQUEST_SCHEMA, "request_id": "req-terminal-requalification",
        "action": "executive.worker_auth.verify_ready",
        "args": {"expected_credential_kind": "device-auth",
                 "workspace_binding_class": r.WORKSPACE_BINDING_CLASS,
                 "credential_expires_at": s.deadline,
                 "requalify_terminal_adverse_sha256": s.digest},
    }
    value["args"].update(changes)
    return value


def test_typed_action_and_client_preserve_exact_preimage_digest(state):
    values = ["executive.worker_auth.verify_ready", "--request-id", "req-terminal-requalification",
              "--expected-credential-kind", "device-auth",
              "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
              "--credential-expires-at", state.deadline,
              "--requalify-terminal-adverse-sha256", state.digest]
    raw = mmx_admin.build_request(values)
    assert raw == request(state)
    argv = build_argv(validate_request(raw), state.tmp)
    assert argv[-2:] == ("--requalify-terminal-adverse-sha256", state.digest)
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request(["status", "--request-id", "req-status",
                                       "--requalify-terminal-adverse-sha256", state.digest])


@pytest.mark.parametrize("changes", [
    {"expected_credential_kind": "service-account"},
    {"expected_credential_kind": "personal-access-token"},
    {"slot_id": "codex-01"}, {"slot_id": "codex-pro-01"},
    {"requalify_terminal_adverse_sha256": ""},
    {"requalify_terminal_adverse_sha256": "A" * 64},
    {"requalify_terminal_adverse_sha256": "a" * 63},
    {"requalify_terminal_adverse_sha256": "a" * 65},
])
def test_closed_typed_arguments(state, changes):
    with pytest.raises(PrivilegedActionError):
        validate_request(request(state, **changes))


@pytest.mark.parametrize("action", ["executive.worker_auth.verify_only",
                                  "executive.worker_auth.recover_transaction",
                                  "executive.services.start"])
def test_other_actions_cannot_requalify(state, action):
    raw = request(state)
    raw["action"] = action
    with pytest.raises(PrivilegedActionError):
        validate_request(raw)


def broker_fixture(s, evidence_changes=None, *, write_marker=True):
    release = s.tmp / ("a" * 40)
    release.mkdir()
    evidence = {
        "readiness_receipt_sha256": s.digest, "readiness_document": s.document,
        "current_auth_identity": s.auth, "current_binary_identity": s.current,
        "readiness_transaction_lock_present": False, "verify_ready_processes": [],
    }
    evidence.update(evidence_changes or {})
    calls = []
    broker = PrivilegedActionBroker(
        PrivilegedBrokerConfig(release_root=release, receipt_root=s.tmp / "receipts",
                               allowed_peer_uids=(501,), timeout_seconds=30, broker_version="test"),
        executor=lambda *a, **k: calls.append(a) or subprocess.CompletedProcess([], 0, b"", b""),
        require_root=False, trust_validator=lambda c: None,
        reconciliation_observer=lambda: evidence,
    )
    target = validate_request(request(s))
    target_digest = hashlib.sha256(canonical_request_bytes(target)).hexdigest()
    marker = {
        "schema": "mastermind.executive_privileged_action_inflight.v1",
        "request_id": target.request_id, "request_sha256": target_digest,
        "action": target.action, "effect_class": target.effect_class,
        "started_at": iso(datetime.now(UTC) - timedelta(minutes=1)),
        "release_sha": "a" * 40,
    }
    raw = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    marker_path = broker.inflight_path(target.request_id)
    if write_marker:
        marker_path.write_bytes(raw)
        marker_path.chmod(0o600)
    reconciliation = {
        "schema": RECONCILE_REQUEST_SCHEMA, "target_request_id": target.request_id,
        "target_request_sha256": target_digest, "target_marker_sha256": hashlib.sha256(raw).hexdigest(),
        "target_release_sha": "a" * 40, "readiness_receipt_sha256": s.digest,
        "expected_credential_kind": "device-auth", "workspace_binding_class": r.WORKSPACE_BINDING_CLASS,
        "credential_expires_at": s.deadline,
    }
    return broker, reconciliation, raw, calls


def test_requal_not_applied_reconciliation_is_durable_and_never_replays_effect(state):
    broker, reconciliation, marker, calls = broker_fixture(state)
    record, replayed = broker.reconcile_not_applied(reconciliation, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert broker.reconcile_not_applied(reconciliation, peer_uid=501) == (record, True)
    status = broker.query_status({"schema": STATUS_REQUEST_SCHEMA,
                                 "request_id": reconciliation["target_request_id"]}, peer_uid=501)
    assert status["status"] == "RECONCILED_NOT_APPLIED"
    with pytest.raises(ReconciledNotAppliedError):
        broker.handle(request(state), peer_uid=501)
    assert calls == []
    assert broker.inflight_path(reconciliation["target_request_id"]).read_bytes() == marker


@pytest.mark.parametrize("change", ["digest", "lock", "process", "auth", "binary", "reserved", "timeout", "passing"])
def test_reconciliation_refuses_uncertain_or_changed_effects(state, change):
    evidence = {}
    if change == "digest": evidence["readiness_receipt_sha256"] = "d" * 64
    elif change == "lock": evidence["readiness_transaction_lock_present"] = True
    elif change == "process": evidence["verify_ready_processes"] = ["123 provision-worker-auth.sh"]
    elif change == "auth": evidence["current_auth_identity"] = {**state.auth, "inode": 999}
    elif change == "binary": evidence["current_binary_identity"] = state.old
    else:
        d = copy.deepcopy(state.document)
        if change == "reserved": d.update(refusal="canary_reserved", inference_canary=None)
        elif change == "timeout": d["inference_canary"]["timed_out"] = True
        elif change == "passing": d.update(passed=True, refusal=None)
        evidence["readiness_document"] = d
    broker, reconciliation, marker, calls = broker_fixture(state, evidence)
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(reconciliation, peer_uid=501)
    assert not broker.reconciliation_path(reconciliation["target_request_id"]).exists()
    assert broker.inflight_path(reconciliation["target_request_id"]).read_bytes() == marker
    assert calls == []


def test_broker_executes_exact_requalification_once_and_rejects_invalid_before_spawn(state):
    broker, _, _, calls = broker_fixture(state, write_marker=False)
    with pytest.raises(PrivilegedActionError):
        broker.handle(request(state, expected_credential_kind="service-account"), peer_uid=501)
    assert calls == []
    first = broker.handle(request(state), peer_uid=501)
    second = broker.handle(request(state), peer_uid=501)
    assert first == second
    assert first["outcome"] == "SUCCEEDED"
    assert len(calls) == 1
    assert tuple(calls[0][0])[-2:] == ("--requalify-terminal-adverse-sha256", state.digest)


def test_reconciliation_status_rejects_record_changed_to_legacy_target_digest(state):
    broker, reconciliation, marker, calls = broker_fixture(state)
    record, _ = broker.reconcile_not_applied(reconciliation, peer_uid=501)
    legacy = request(state)
    del legacy["args"]["requalify_terminal_adverse_sha256"]
    record["target_request_sha256"] = hashlib.sha256(
        canonical_request_bytes(validate_request(legacy))
    ).hexdigest()
    record_path = broker.reconciliation_path(reconciliation["target_request_id"])
    record_path.chmod(0o600)
    record_path.write_text(json.dumps(record) + "\n")
    record_path.chmod(0o400)
    with pytest.raises(PrivilegedBrokerError):
        broker.query_status({"schema": STATUS_REQUEST_SCHEMA,
                             "request_id": reconciliation["target_request_id"]}, peer_uid=501)
    assert broker.inflight_path(reconciliation["target_request_id"]).read_bytes() == marker
    assert calls == []


def paired_state(s):
    # Preserve history while changing all current observations as one cohort.
    s.document = copy.deepcopy(s.document)
    s.auth["device"] = 2
    s.old["device"] = 2
    s.current["device"] = 2
    s.identity = {**s.identity, "credential_lstat": dict(s.auth), "codex_binary": dict(s.current)}
    write_json(s.identity_path, s.identity)


def test_explicit_paired_device_change_preserves_history_and_reserves_current_identity(state):
    original = state.receipt.read_bytes()
    paired_state(state)
    assert cli(state, "reuse", explicit=False) == 2
    assert cli(state, "reuse") == 5
    assert cli(state, "reserve") == 0
    reserved = json.loads(state.receipt.read_bytes())
    assert reserved["credential_lstat"] == state.auth
    assert reserved["provider_identity"]["credential_lstat"] == state.auth
    archive, = state.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == original
    assert cli(state, "reserve") == 2


@pytest.mark.parametrize("change", ["only_auth", "split_successor", "split_predecessor",
                                  "inode", "mtime", "ctime", "size", "mode",
                                  "old_split", "bool_device", "missing_device", "no_renumber"])
def test_paired_device_exception_refuses_partial_or_nondevice_drift(state, change):
    paired_state(state)
    if change == "only_auth": state.old["device"] = state.current["device"] = 1
    elif change == "split_successor": state.current["device"] = 3
    elif change == "split_predecessor": state.old["device"] = 3
    elif change in ("inode", "mtime", "ctime", "size", "mode"):
        key = {"mtime": "mtime_ns", "ctime": "ctime_ns"}.get(change, change)
        state.auth[key] += 1
    elif change == "no_renumber":
        state.auth["device"] = state.old["device"] = state.current["device"] = 1
        state.auth["inode"] += 1
    else:
        doc = copy.deepcopy(state.document)
        if change == "old_split": doc["credential_lstat"]["device"] = 9
        elif change == "bool_device": doc["credential_lstat"]["device"] = True
        elif change == "missing_device": del doc["credential_lstat"]["device"]
        write_json(state.receipt, doc)
    original = state.receipt.read_bytes()
    assert cli(state, "reserve", digest=hashlib.sha256(original).hexdigest()) == 2
    assert state.receipt.read_bytes() == original
    assert list(state.tmp.glob("*.superseded-*")) == []


def test_paired_exception_is_shared_by_only_explicit_broker_reconciliation(state):
    paired_state(state)
    broker, reconciliation, _, calls = broker_fixture(state)
    record, _ = broker.reconcile_not_applied(reconciliation, peer_uid=501)
    assert record["classification"] == "NOT_APPLIED" and calls == []


def test_normal_passing_validation_keeps_full_device_identity(state):
    passed = r.compose_receipt(
        identity=state.identity, canary=canary(True), auth_identity=state.auth,
        binary_identity=state.current, expected_kind="device-auth",
        workspace_binding_class=r.WORKSPACE_BINDING_CLASS, credential_expires_at=state.deadline,
    )
    paired_state(state)
    with pytest.raises(r.ReadinessError, match="readiness_credential_stale"):
        r.validate_receipt_document(passed, auth_identity=state.auth, binary_identity=state.current)
