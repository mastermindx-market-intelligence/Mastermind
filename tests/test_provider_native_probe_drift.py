"""Hermetic boundary and transaction tests for the native 2bca incident.

Temporary receipt storage uses the test user's ownership. These tests exercise
real lstat, archival, CAS and broker replay, not production root custody.
No credential contents, provider process or network endpoint are accessed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA, PrivilegedActionError, build_argv, canonical_request_bytes,
    validate_request,
)
from ops.executive_os import provider_identity_policy as policy
from ops.executive_os import provider_identity_probe as probe
from ops.executive_os import provider_readiness as readiness
from ops.executive_os import provider_recovery
from scripts import mmx_admin


T = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
FLAG = "--requalify-native-probe-drift-sha256"
KEY = "requalify_native_probe_drift_sha256"


def stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@pytest.fixture
def case(monkeypatch):
    class Clock(datetime):
        current = T - timedelta(hours=2)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(readiness, "datetime", Clock)
    auth = dict(device=1, inode=2, uid=451, gid=451, mode=0o600,
                size=123, mtime_ns=4, ctime_ns=5, nlink=1)
    binary = {**auth, "uid": 0, "gid": 0, "mode": 0o555,
              "path": str(readiness.CODEX_BINARY), "version": readiness.CODEX_VERSION,
              "sha256": readiness.CODEX_SHA256, "team_identifier": readiness.CODEX_TEAM_ID}

    def identity(metadata, when):
        return {
            **probe.evaluate_identity(
                account_read={"account": {"type": "chatgpt", "planType": "enterprise_cbp_automation"},
                              "requiresOpenaiAuth": True},
                auth_mode="chatgpt", expected_kind="device-auth",
                workspace_binding_class=policy.COMPANY_WORKSPACE_BINDING_CLASS,
            ),
            "observed_at": stamp(when), "codex_binary": copy.deepcopy(binary),
            "credential_lstat": dict(metadata), "forced_chatgpt_workspace_id_applied": False,
        }

    canary = {
        "schema_version": readiness.CANARY_SCHEMA, "canary_id": "canary-123456789abc",
        "observed_at": stamp(Clock.current), "codex_version": readiness.CODEX_VERSION,
        "codex_sha256": readiness.CODEX_SHA256, "codex_team_identifier": readiness.CODEX_TEAM_ID,
        "model": "gpt-5.6-sol", "exit_code": 0, "timed_out": False,
        "terminal_event_class": "turn_completed", "result_valid": True,
        "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64,
        "provider_error_message_count": 0, "provider_error_message_sha256": None,
        "provider_error_terms": [], "workspace_capability_outcome": "inert_untrusted_workspace",
        "workspace_selection_mechanism": "none", "forced_chatgpt_workspace_id_applied": False,
        "passed": True, "refusal": None,
    }
    old = readiness.compose_receipt(
        identity=identity(auth, Clock.current), canary=canary,
        auth_identity=auth, binary_identity=binary, expected_kind="device-auth",
        workspace_binding_class=policy.COMPANY_WORKSPACE_BINDING_CLASS,
        credential_expires_at=stamp(T - timedelta(hours=1)),
    )
    Clock.current = T
    current = {**auth, "mtime_ns": 40, "ctime_ns": 50}
    return {"clock": Clock, "old": old, "auth": current, "binary": binary,
            "fresh": identity(current, T), "deadline": stamp(T + timedelta(minutes=45))}


def kwargs(case):
    return dict(auth_identity=case["auth"], binary_identity=case["binary"],
                expected_kind="device-auth", workspace_binding_class=policy.COMPANY_WORKSPACE_BINDING_CLASS)


def test_exact_native_policy_is_separate_from_legacy():
    assert policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256 == "2bca56bcf84b1c5332879eaa22f23f521b37cea30c01dfe5936c3923c3f651cf"
    assert policy.NATIVE_PROBE_DRIFT_EVIDENCE_SHA256 == "ffa2dec44d1d81569be113ebcd4b199464ba8e50e100b894196c32e82fa50d42"
    assert policy.COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256 == "654abd66f6baef1b610a6c03fafe85f76fd81ed646266d3ff90db3c6e85e2a7d"


@pytest.mark.parametrize("minutes,allowed", [(30, False), (31, True), (45, True), (60, True), (61, False)])
def test_timestamp_drift_and_bounded_new_deadline(case, minutes, allowed):
    def classify():
        readiness.classify_native_probe_drift_requalification(
            case["old"], **kwargs(case), new_credential_expires_at=stamp(T + timedelta(minutes=minutes)))
    if allowed:
        classify()
    else:
        with pytest.raises(readiness.ReadinessError, match="deadline_out_of_bounds"):
            classify()


@pytest.mark.parametrize("field,value", [("size", 124), ("device", 3), ("inode", 3), ("uid", 452),
    ("gid", 452), ("mode", 0o640), ("nlink", 2)])
def test_non_timestamp_drift_refuses(case, field, value):
    case["auth"][field] = value
    with pytest.raises(readiness.ReadinessError):
        readiness.validate_native_probe_drift_predecessor_document(case["old"], **kwargs(case))


@pytest.mark.parametrize("defect", ["unchanged", "adverse", "binary", "unexpired", "wrong_realm"])
def test_other_predecessor_classes_refuse(case, defect):
    values = kwargs(case)
    if defect == "unchanged":
        values["auth_identity"] = case["old"]["credential_lstat"]
    elif defect == "adverse":
        case["old"].update(passed=False, refusal="canary_reserved")
    elif defect == "binary":
        case["binary"]["sha256"] = "0" * 64
    elif defect == "unexpired":
        case["old"]["credential_expires_at"] = stamp(T + timedelta(minutes=45))
    else:
        values["workspace_binding_class"] = policy.PERSONAL_PRO_WORKER_BINDING_CLASS
    with pytest.raises(readiness.ReadinessError):
        readiness.validate_native_probe_drift_predecessor_document(case["old"], **values)


@pytest.fixture
def stored(case, tmp_path, monkeypatch):
    receipt = tmp_path / "readiness.json"
    auth = tmp_path / "opaque-auth.json"
    identity_path = tmp_path / "identity.json"
    raw = (json.dumps(case["old"], sort_keys=True, indent=2) + "\n").encode()
    receipt.write_bytes(raw)
    receipt.chmod(0o600)
    storage_gid = receipt.stat().st_gid  # macOS directories can inherit another group.
    identity_path.write_text(json.dumps(case["fresh"]))
    digest = hashlib.sha256(raw).hexdigest()
    # Test-only substitution permits real temp-file CAS; production pins are
    # asserted separately and no arbitrary preimage enters the public route.
    monkeypatch.setattr(readiness, "NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256", digest)
    monkeypatch.setattr(readiness, "RECEIPT_PATH", receipt)
    monkeypatch.setattr(readiness, "AUTH_PATH", auth)
    monkeypatch.setattr(readiness, "receipt_storage_contract", lambda **kw: (os.getuid(), storage_gid, 0o600))
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(readiness, "current_auth_identity", lambda *a, **kw: dict(case["auth"]))
    monkeypatch.setattr(readiness, "current_binary_identity", lambda *a, **kw: dict(case["binary"]))
    args = ["--receipt", str(receipt), "--auth", str(auth), "--binary", str(readiness.CODEX_BINARY),
            "--expected-kind", "device-auth", "--workspace-binding-class", policy.COMPANY_WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", case["deadline"], FLAG, digest]
    return {"receipt": receipt, "raw": raw, "digest": digest, "identity": identity_path,
            "reuse": ["reuse", *args], "reserve": ["reserve", *args, "--identity-json", str(identity_path)]}


def test_reservation_preserves_preimage_and_cannot_spend_again(stored, case):
    assert readiness.main(stored["reuse"]) == 10
    assert readiness.main(stored["reserve"]) == 0
    reservation = json.loads(stored["receipt"].read_bytes())
    assert reservation["refusal"] == "canary_reserved" and reservation["passed"] is False
    assert reservation["credential_lstat"] == case["auth"]
    assert reservation["credential_expires_at"] == case["deadline"]
    archives = list(stored["receipt"].parent.glob("readiness.json.superseded-*.json"))
    assert len(archives) == 1 and archives[0].read_bytes() == stored["raw"]
    assert archives[0].stat().st_mode & 0o777 == 0o600
    reserved_bytes = stored["receipt"].read_bytes()
    assert readiness.main(stored["reserve"]) == 2
    assert stored["receipt"].read_bytes() == reserved_bytes
    assert archives[0].read_bytes() == stored["raw"]


@pytest.mark.parametrize("defect", ["refused", "stale", "credential", "binary", "policy"])
def test_fresh_probe_defects_preserve_predecessor(stored, case, defect, capsys):
    fresh = case["fresh"]
    if defect == "refused":
        fresh["refusal"] = "credential_identity_changed_during_probe"
    elif defect == "stale":
        fresh["observed_at"] = stamp(T - timedelta(hours=1))
    elif defect == "credential":
        fresh["credential_lstat"]["mtime_ns"] += 1
    elif defect == "binary":
        fresh["codex_binary"]["sha256"] = "0" * 64
    else:
        fresh["plan_type"] = "pro"
    stored["identity"].write_text(json.dumps(fresh))
    assert readiness.main(stored["reserve"]) == 2
    expected = {"refused": "drift_requalification_fresh_identity_refused",
                "stale": "requalification_fresh_identity_required",
                "credential": "requalification_provider_identity_changed",
                "binary": "identity_binary_mismatch",
                "policy": "identity_company_plan_required"}
    assert expected[defect] in capsys.readouterr().err
    assert stored["receipt"].read_bytes() == stored["raw"]
    assert list(stored["receipt"].parent.glob("*.superseded-*.json")) == []


@pytest.mark.parametrize("race", ["credential", "receipt"])
def test_archive_cas_race_never_overwrites_intervening_state(stored, case, monkeypatch, race):
    persist = readiness._persist_superseded_receipt
    intervening = stored["raw"] + b" "

    def race_after_archive(*args, **kw):
        persist(*args, **kw)
        if race == "credential":
            case["auth"]["mtime_ns"] += 1
        else:
            stored["receipt"].write_bytes(intervening)

    monkeypatch.setattr(readiness, "_persist_superseded_receipt", race_after_archive)
    assert readiness.main(stored["reserve"]) == 2
    assert stored["receipt"].read_bytes() == (intervening if race == "receipt" else stored["raw"])
    archives = list(stored["receipt"].parent.glob("*.superseded-*.json"))
    assert len(archives) == 1 and archives[0].read_bytes() == stored["raw"]


def request(deadline=None):
    return {"schema": REQUEST_SCHEMA, "request_id": policy.NATIVE_PROBE_DRIFT_REQUEST_ID,
            "action": "executive.worker_auth.verify_ready", "args": {
                "expected_credential_kind": "device-auth",
                "workspace_binding_class": policy.COMPANY_WORKSPACE_BINDING_CLASS,
                "credential_expires_at": deadline or stamp(T + timedelta(minutes=45)),
                KEY: policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256}}


def test_cli_and_broker_contract_require_explicit_canonical_request():
    raw = request()
    argv = [raw["action"], "--expected-credential-kind", "device-auth", "--workspace-binding-class",
            policy.COMPANY_WORKSPACE_BINDING_CLASS, "--credential-expires-at", raw["args"]["credential_expires_at"],
            FLAG, policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256]
    with pytest.raises(SystemExit):
        mmx_admin.build_request(argv)
    assert mmx_admin.build_request([*argv, "--request-id", raw["request_id"]]) == raw
    with pytest.raises(PrivilegedActionError):
        mmx_admin.build_request([*argv, "--request-id", "different-request"])
    assert FLAG in build_argv(validate_request(raw), Path("/reviewed/release"))
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request(["status", "--request-id", raw["request_id"], FLAG, raw["args"][KEY]])


@pytest.mark.parametrize("defect", ["preimage", "id", "kind", "slot", "mixed"])
def test_wire_cannot_widen_native_route(defect):
    raw = request()
    if defect == "preimage":
        raw["args"][KEY] = policy.COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256
    elif defect == "id":
        raw["request_id"] = "replacement-incident"
    elif defect == "kind":
        raw["args"]["expected_credential_kind"] = "service-account"
    elif defect == "slot":
        raw["args"]["slot_id"] = "codex-01"
    else:
        raw["args"]["renew_device_revalidation_sha256"] = raw["args"][KEY]
    with pytest.raises(PrivilegedActionError):
        validate_request(raw)


@pytest.fixture
def broker_case(tmp_path, monkeypatch):
    release = tmp_path / ("a" * 40)
    release.mkdir()
    calls = []
    source_calls = []

    def source():
        source_calls.append(True)
        return {"release_sha": release.name, "manifest_sha256": "b" * 64}

    monkeypatch.setattr(provider_recovery, "current_executive_source", source)
    monkeypatch.setattr(provider_recovery, "historical_recovery_grants", lambda: [])

    def make(executor=None, observer=None):
        def execute(argv, **kw):
            calls.append(tuple(argv))
            return subprocess.CompletedProcess(argv, 65, b"", b"credential_identity_changed_during_probe")
        return broker_module.PrivilegedActionBroker(
            broker_module.PrivilegedBrokerConfig(release_root=release, receipt_root=tmp_path / "receipts",
                allowed_peer_uids=(501,), timeout_seconds=30, broker_version="test"),
            executor=executor or execute, require_root=False, trust_validator=lambda config: None,
            reconciliation_observer=observer,
        )
    return make, calls, source_calls


def test_failed_probe_terminal_replay_never_rechecks_source_or_spawns(broker_case, monkeypatch):
    make, calls, source_calls = broker_case
    broker = make()
    raw = request()
    first = broker.handle(raw, peer_uid=501)
    assert first["exit_code"] == 65 and first["outcome"] == "FAILED"
    # Historical terminal is readable even if current source can no longer qualify.
    monkeypatch.setattr(provider_recovery, "current_executive_source", lambda: pytest.fail("replayed live guard"))
    assert broker.handle(raw, peer_uid=501) == first
    assert len(calls) == len(source_calls) == 1
    with pytest.raises(broker_module.RequestIdConflictError):
        broker.handle(request(stamp(T + timedelta(minutes=50))), peer_uid=501)
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["mismatch", "unsealed"])
def test_unqualified_source_never_starts_probe_or_writes_marker(broker_case, monkeypatch, kind):
    make, calls, _ = broker_case
    broker = make()

    def source():
        if kind == "unsealed":
            raise provider_recovery.RecoveryError("recovery_executive_source_unverified")
        return {"release_sha": "f" * 40, "manifest_sha256": "b" * 64}

    monkeypatch.setattr(provider_recovery, "current_executive_source", source)
    with pytest.raises(broker_module.BrokerTrustError):
        broker.handle(request(), peer_uid=501)
    assert calls == [] and not broker.inflight_path(policy.NATIVE_PROBE_DRIFT_REQUEST_ID).exists()


def test_uncertain_probe_preserves_marker_without_another_attempt(broker_case):
    make, calls, source_calls = broker_case

    def uncertain(argv, **kw):
        calls.append(tuple(argv))
        raise OSError("unknown post-admission failure")

    broker = make(executor=uncertain)
    for _ in range(2):
        with pytest.raises(broker_module.EffectUnknownError):
            broker.handle(request(), peer_uid=501)
    assert len(calls) == len(source_calls) == 1
    assert broker.inflight_path(policy.NATIVE_PROBE_DRIFT_REQUEST_ID).exists()
    assert not broker.receipt_path(policy.NATIVE_PROBE_DRIFT_REQUEST_ID).exists()


def test_expired_request_reconstruction_preserves_exact_hash(broker_case, case):
    make, _, _ = broker_case
    broker = make()
    raw = request(stamp(T - timedelta(hours=1)))
    validated = validate_request(raw)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    wire = {"schema": broker_module.RECONCILE_REQUEST_SCHEMA, "target_request_id": raw["request_id"],
            "target_request_sha256": digest, "target_marker_sha256": "d" * 64,
            "target_release_sha": broker.config.release_root.name,
            "readiness_receipt_sha256": policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256,
            **{key: value for key, value in raw["args"].items() if key != KEY}}
    reconstructed = broker_module.validate_reconcile_not_applied_request(wire)
    assert reconstructed.requalify_native_probe_drift_sha256 == policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256
    assert reconstructed.to_dict() == wire
    # Historical evidence is valid independently of the now-expired new deadline.
    readiness.validate_native_probe_drift_predecessor_document(case["old"], **kwargs(case))
    with pytest.raises(readiness.ReadinessError, match="deadline_out_of_bounds"):
        readiness.classify_native_probe_drift_requalification(
            case["old"], **kwargs(case), new_credential_expires_at=raw["args"]["credential_expires_at"])
    wire["target_request_sha256"] = "e" * 64
    with pytest.raises(broker_module.RequestIdConflictError):
        broker_module.validate_reconcile_not_applied_request(wire)


@pytest.mark.parametrize("hold", [None, "lock", "process", "preimage"])
def test_expired_native_reconciliation_is_durable_and_never_reopens_execution(broker_case, case, hold):
    make, calls, source_calls = broker_case
    evidence = {"readiness_receipt_sha256": policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256,
                "readiness_document": case["old"], "readiness_transaction_lock_present": False,
                "verify_ready_processes": [], "current_auth_identity": case["auth"],
                "current_binary_identity": case["binary"]}
    broker = make(observer=lambda: evidence)
    raw = request(stamp(T - timedelta(hours=1)))
    validated = validate_request(raw)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    broker._write_inflight(validated, digest, stamp(T - timedelta(minutes=90)))
    marker_path = broker.inflight_path(raw["request_id"])
    marker_raw = marker_path.read_bytes()
    wire = {"schema": broker_module.RECONCILE_REQUEST_SCHEMA, "target_request_id": raw["request_id"],
            "target_request_sha256": digest, "target_marker_sha256": hashlib.sha256(marker_raw).hexdigest(),
            "target_release_sha": broker.config.release_root.name,
            "readiness_receipt_sha256": policy.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256,
            **{key: value for key, value in raw["args"].items() if key != KEY}}
    if hold == "lock":
        evidence["readiness_transaction_lock_present"] = True
    elif hold == "process":
        evidence["verify_ready_processes"] = ["retained-verify-ready-process"]
    elif hold == "preimage":
        evidence["readiness_receipt_sha256"] = "c" * 64
    if hold:
        with pytest.raises(broker_module.BrokerTrustError):
            broker.reconcile_not_applied(wire, peer_uid=501)
        assert not broker.reconciliation_path(raw["request_id"]).exists()
    else:
        record, replayed = broker.reconcile_not_applied(wire, peer_uid=501)
        assert replayed is False and record["classification"] == "NOT_APPLIED"
        assert record["target_request_sha256"] == digest
        assert json.loads(broker.reconciliation_path(raw["request_id"]).read_bytes()) == record
        assert broker.reconcile_not_applied(wire, peer_uid=501) == (record, True)
        with pytest.raises(broker_module.ReconciledNotAppliedError):
            broker.handle(raw, peer_uid=501)
    assert marker_path.read_bytes() == marker_raw
    assert calls == [] and source_calls == []
