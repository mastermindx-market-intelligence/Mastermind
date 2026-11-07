"""Exact incident policy, authenticated issuance and one-use qualification.

The production policy binds the separately authorized exact incident without
claiming an ordinary cause. Positive issuer/consumer tests use private fixture
policies and real machinery; no fixture is production permission or readiness.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import provider_readiness as r
from ops.executive_os import provider_recovery as rec
from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    PrivilegedActionError,
    build_argv,
    canonical_request_bytes,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    EffectUnknownError,
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
    PrivilegedBrokerError,
)
from scripts import mmx_admin
from tests.test_provider_readiness_terminal_adverse import (
    canary, iso, state, write_json,
)


ISSUER_REQUEST_ID = "req-incident-issuer-1"
ISSUER_REQUEST_SHA256 = "d" * 64
SUCCESSOR_REQUEST_ID = "req-incident-successor-1"
ORIGINAL_REQUEST_ID = "req-incident-predecessor"
ORIGINAL_REQUEST_SHA256 = "b" * 64


def receipt_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def custody_root(tmp_path):
    """Build the fixed custody chain shape under a private temporary root."""
    root = tmp_path / "var" / "db" / "mastermind-executive" / "provider-recovery"
    state_root = root / "current-pin"
    state_root.mkdir(parents=True)
    for path in (
        tmp_path / "var",
        tmp_path / "var" / "db",
        tmp_path / "var" / "db" / "mastermind-executive",
        root,
        state_root,
    ):
        os.chmod(path, 0o700)
    return state_root


def _test_storage_contract(*, workspace_binding_class=None, worker_gid=r.WORKER_GID):
    return os.getuid(), os.getgid(), 0o400


@pytest.fixture
def recovery(state, custody_root, monkeypatch):
    """A retained terminal-adverse predecessor with full incident fixtures.

    Only host-path ownership, OS principal observation and the readiness
    storage contract are substituted.  All bytes, digests, custody metadata,
    duplicate-key rejection, exclusive custody writes, broker terminal
    lifecycle, typed admission and one-use allocation run unchanged.
    """
    s = state
    monkeypatch.setattr(r, "RECEIPT_PATH", s.receipt)
    monkeypatch.setattr(r, "AUTH_PATH", s.tmp / "provider-home")
    monkeypatch.setattr(r, "CODEX_BINARY", s.tmp / "codex-0.159.2")
    monkeypatch.setattr(rec, "RECOVERY_STATE_ROOT", custody_root)
    monkeypatch.setattr(rec, "RECOVERY_GRANT_PATH", custody_root / "grant.json")
    monkeypatch.setattr(rec, "RECOVERY_ALLOCATION_PATH", custody_root / "allocation.json")
    monkeypatch.setattr(rec, "RECOVERY_INCIDENT_GRANT_PATH", custody_root / "incident-grant.json")
    monkeypatch.setattr(
        rec, "RECOVERY_INCIDENT_COMMITMENT_PATH", custody_root / "incident-commitment.json"
    )
    monkeypatch.setattr(rec, "CUSTODY_UID", os.getuid())
    monkeypatch.setattr(rec, "CUSTODY_GID", os.getgid())
    monkeypatch.setattr(rec._readiness, "RECEIPT_PATH", s.receipt)
    monkeypatch.setattr(rec._readiness, "AUTH_PATH", s.tmp / "provider-home")
    monkeypatch.setattr(rec._readiness, "CODEX_BINARY", s.tmp / "codex-0.159.2")
    monkeypatch.setattr(rec._readiness, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(rec._readiness, "_assert_no_macos_acl", lambda path: None)
    monkeypatch.setattr(r, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(r, "_assert_no_macos_acl", lambda path: None)
    monkeypatch.setattr(r, "receipt_storage_contract", _test_storage_contract)
    monkeypatch.setattr(rec._readiness, "receipt_storage_contract", _test_storage_contract)

    # Re-bind the installed-source identity to the substituted review path so
    # the grant, the predecessor receipt and the observation all name the
    # exact same pinned source.
    s.current = {**s.current, "path": os.fspath(r.CODEX_BINARY)}
    s.identity = {**s.identity, "codex_binary": dict(s.current)}
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **k: dict(s.auth))
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(s.current))

    document = incident_adverse_document(s)
    write_json(s.receipt, document)
    os.chmod(s.receipt, 0o400)
    s.document = document
    s.digest = receipt_digest(s.receipt)
    s.executive_source = {"release_sha": "a" * 40, "manifest_sha256": "b" * 64}
    monkeypatch.setattr(rec, "current_executive_source", lambda: dict(s.executive_source))
    terminal_root = s.tmp / "broker" / "receipts"
    for directory in (terminal_root, terminal_root / "inflight", terminal_root / "reconciled"):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(broker_module, "_RECEIPT_ROOT", terminal_root)
    monkeypatch.setattr(
        broker_module, "_assert_root_owned_nonwritable", lambda path, directory: path.lstat()
    )
    when = datetime.fromisoformat(s.document["observed_at"].replace("Z", "+00:00"))
    s.terminal = {
        "schema": broker_module.RECEIPT_SCHEMA,
        "request_id": ORIGINAL_REQUEST_ID, "request_sha256": ORIGINAL_REQUEST_SHA256,
        "action": "executive.worker_auth.verify_ready",
        "effect_class": broker_module.ACTION_EFFECT_CLASS[
            "executive.worker_auth.verify_ready"],
        "started_at": iso(when - timedelta(seconds=10)),
        "finished_at": iso(when + timedelta(seconds=10)),
        "release_sha": "c" * 40, "broker_version": "test",
        "exit_code": 65, "outcome": "FAILED",
        "stdout_bytes": 0, "stdout_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_excerpt": "",
        "stderr_bytes": 0, "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stderr_excerpt": "",
    }
    s.terminal_path = terminal_root / (ORIGINAL_REQUEST_ID + ".json")
    write_json(s.terminal_path, s.terminal)
    os.chmod(s.terminal_path, 0o600)
    s.designated = designated_evidence(s)
    s.observation_path = s.tmp / "observation.json"
    return s


def incident_adverse_document(s):
    """One closed terminal adverse receipt produced by the pinned current pin."""
    failed = {**canary(False)}
    failed.update(codex_version=s.current["version"], codex_sha256=s.current["sha256"])
    document = r.compose_receipt(
        identity=s.identity, canary=failed, auth_identity=s.auth,
        binary_identity=s.current, expected_kind="device-auth",
        workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS,
        credential_expires_at=s.deadline, canary_command_status=1,
    )
    past = datetime.now(UTC) - timedelta(days=1)
    document.update(
        observed_at=iso(past),
        credential_expires_at=iso(past + timedelta(hours=12)),
        readiness_expires_at=iso(past + timedelta(hours=12)),
    )
    document["provider_identity"]["observed_at"] = iso(past)
    document["inference_canary"]["observed_at"] = iso(past)
    return document


def designated_evidence(s):
    """Derive one coherent test-only designation from the retained fixtures."""
    return {
        "original_request_id": ORIGINAL_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_release_sha": s.terminal["release_sha"],
        "original_terminal_sha256": receipt_digest(s.terminal_path),
        "original_terminal_bytes": s.terminal_path.stat().st_size,
        "original_broker_exit_code": 65,
        "readiness_receipt_sha256": s.digest,
        "readiness_receipt_bytes": s.receipt.stat().st_size,
        "canary_id": s.document["inference_canary"]["canary_id"],
        "canary_exit_code": 1,
    }


def fixture_authorization_fields():
    # Synthetic fixtures are private in-process test injection, not a human
    # answer or a production activation input.
    return dict(policy_id="test-due10-policy", question_sha256="1" * 64,
                answer_sha256="2" * 64, provenance_sha256="3" * 64)


def incident_policy(s):
    return rec.IncidentPolicy(**fixture_authorization_fields(), **designated_evidence(s))


def incident_request_raw(request_id=ISSUER_REQUEST_ID,
                         successor=SUCCESSOR_REQUEST_ID):
    return {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "action": rec.INCIDENT_ISSUER_ACTION,
        "args": {"successor_request_id": successor},
    }


def make_broker(s):
    evidence = {
        "readiness_receipt_sha256": s.digest,
        "readiness_document": s.document,
        "readiness_transaction_lock_present": False,
        "verify_ready_processes": [],
        "current_auth_identity": dict(s.auth),
        "current_binary_identity": dict(s.current),
    }
    return PrivilegedActionBroker(
        PrivilegedBrokerConfig(
            release_root=s.tmp / s.executive_source["release_sha"],
            receipt_root=broker_module._RECEIPT_ROOT,
            allowed_peer_uids=(501,), timeout_seconds=30, broker_version="test",
        ),
        executor=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("incident issuance must never spawn a child")),
        require_root=False,
        trust_validator=lambda config: None,
        reconciliation_observer=lambda: dict(evidence),
    )


def issue_incident(s, monkeypatch, *, policy=None):
    """Run the real internal issuer under a test-only designation."""
    monkeypatch.setattr(
        rec, "PRODUCTION_INCIDENT_POLICY",
        incident_policy(s) if policy is None else policy,
    )
    broker = make_broker(s)
    receipt = broker.handle(incident_request_raw(), peer_uid=501)
    return broker, receipt


def incident_grant_document(s, **changes):
    grant = {
        "schema_version": rec.INCIDENT_GRANT_SCHEMA,
        "authority_reference": rec.INCIDENT_AUTHORITY_REFERENCE,
        "incident_class": "due10_incident",
        "historical_cause": rec.INCIDENT_HISTORICAL_CAUSE,
        "causal_link": rec.INCIDENT_CAUSAL_LINK,
        "raw_provider_messages_retained": False,
        "authorization": incident_policy(s).authorization_binding(),
        "evidence": dict(s.designated),
        "installed_source": {
            "path": os.fspath(r.CODEX_BINARY),
            "version": r.CODEX_VERSION,
            "sha256": r.CODEX_SHA256,
            "team_identifier": r.CODEX_TEAM_ID,
        },
        "executive_source": dict(s.executive_source),
        "worker": {
            "worker_user": rec.get_slot("codex-01").worker_user,
            "worker_uid": r.WORKER_UID,
            "worker_gid": r.WORKER_GID,
            "provider_home": os.fspath(r.AUTH_PATH.parent),
            "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
            "expected_credential_kind": "device-auth",
        },
        "credential_lstat": dict(s.auth),
        "model": r.PRODUCTION_MODEL,
        "issuer_request_id": ISSUER_REQUEST_ID,
        "issuer_request_sha256": ISSUER_REQUEST_SHA256,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "budget": 1,
        "granted_at": iso(datetime.now(UTC) - timedelta(minutes=5)),
        "expires_at": iso(datetime.now(UTC) + timedelta(minutes=40)),
    }
    grant.update(changes)
    return grant


def rewrite_custody(path: Path, value) -> None:
    """Replace a custody file's bytes in tests (the issuer can never do this)."""
    previous = path.stat().st_mode
    os.chmod(path, 0o600)
    path.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.chmod(path, previous & 0o777)


def read_custody(path: Path):
    return json.loads(path.read_bytes().decode())


def write_observation(s, **changes):
    observation = {
        "schema_version": rec.OBSERVATION_SCHEMA,
        "observation_only": True,
        "readiness_issued": False,
        "observation_status": "observed",
        "refusal": None,
        "observed_at": r.now_iso(),
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "slot_id": "codex-01",
        "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
        "expected_credential_kind": "device-auth",
        "configured_model": r.PRODUCTION_MODEL,
        "codex_binary": dict(s.current),
        "executive_source": dict(s.executive_source),
        "credential_lstat": dict(s.auth),
        "provider_identity": dict(s.identity),
        "ordinary_usage_allowed": True,
        "model_catalog": {"listed_in_returned_page": True, "complete": True},
    }
    observation.update(changes)
    write_json(s.observation_path, observation)
    return observation


def reserve_incident(s):
    """Drive the internal reservation with NO producer qualification at all."""
    args = argparse.Namespace(
        receipt=s.receipt,
        auth=s.tmp / "provider-home",
        binary=s.tmp / "codex-0.159.2",
        identity_json=None,
        expected_kind="device-auth",
        workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS,
        credential_expires_at=iso(datetime.now(UTC) + timedelta(minutes=55)),
        worker_uid=r.WORKER_UID,
        worker_gid=r.WORKER_GID,
        recover_current_pin_grant_sha256=s.incident_grant_digest,
        successor_request_id=SUCCESSOR_REQUEST_ID,
        recovery_observation_json=s.observation_path,
        refresh_expired=False,
    )
    return r._reserve_current_pin_recovery(
        args,
        auth_identity=r.current_auth_identity(
            s.tmp / "provider-home", worker_uid=r.WORKER_UID, worker_gid=r.WORKER_GID,
        ),
        binary_identity=r.current_binary_identity(s.tmp / "codex-0.159.2"),
    )


def incident_state(s):
    """Consume a completed issuance into a ready-to-reserve state."""
    s.incident_grant_digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    write_observation(s)
    return s


def nothing_created(s):
    return (
        not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
        and not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
        and not rec.RECOVERY_ALLOCATION_PATH.exists()
        and list(s.tmp.rglob("*.superseded-*")) == []
    )


# ---------------------------------------------------------------------------
# Source-bound production policy, explicit dormancy, ordinary unchanged.
# ---------------------------------------------------------------------------


def test_production_incident_policy_binds_exact_human_answer_and_designated_evidence():
    policy = rec.PRODUCTION_INCIDENT_POLICY
    assert isinstance(policy, rec.IncidentPolicy)
    assert policy.authorization_binding() == {
        "schema_version": rec.INCIDENT_POLICY_SCHEMA,
        "policy_id": "due10-dual-unknown-one-attempt-20261013",
        "question_sha256": "660ddac062ace661a01984e4abddc0d36145c17226c352134ca4883eb7f82b0b",
        "answer_sha256": "590b9e4398dbd11400728d7c566e29bc4afd6c574a39a464f6581eae60b75028",
        "provenance_sha256": "b55221d99bbd31a90d68b9ea9c59a43d3b3191595a8fe2ce99dfdef2e7bcd2de",
    }
    assert policy.designated_evidence() == rec.INCIDENT_DESIGNATED_EVIDENCE
    assert rec.INCIDENT_HISTORICAL_CAUSE == "UNKNOWN"
    assert rec.INCIDENT_CAUSAL_LINK == "NOT_ESTABLISHED"
    assert not rec.PRODUCER_QUALIFICATION.terminal_events
    assert rec.INCIDENT_DESIGNATED_EVIDENCE == {
        "original_request_id": "codex01-current-v5-company-01a1230a-20261011-10",
        "original_request_sha256":
            "612e85ce922cc9f97f2399d2a1d99e0250795026d86b3101ce32303df48e7863",
        "original_release_sha": "a858ac249296ffaa7bf523863dea5917bbbc1f24",
        "original_terminal_sha256":
            "1ed264ba7e356cd5f673056a8275aca5492016e9e5fb0f4b2f02f6768bcbdde3",
        "original_terminal_bytes": 785,
        "original_broker_exit_code": 65,
        "readiness_receipt_sha256":
            "05d9505d022dd82deca57b093759c6d44b4d2a1ddb09afd613b12b18a4b12b1a",
        "readiness_receipt_bytes": 3457,
        "canary_id": "canary-127d79f1f6bb",
        "canary_exit_code": 1,
    }


def test_none_policy_issuance_refuses_before_any_state_exists(recovery, monkeypatch):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", None)
    s = recovery
    broker = make_broker(s)
    with pytest.raises(PrivilegedBrokerError, match="dormant"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert nothing_created(s)
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()
    assert not broker.receipt_path(ISSUER_REQUEST_ID).exists()


@pytest.mark.parametrize("section,field", [
    ("authorization", key) for key in ("policy_id", "question_sha256", "answer_sha256", "provenance_sha256")
] + [("evidence", key) for key in rec.INCIDENT_DESIGNATED_EVIDENCE])
def test_live_production_policy_rejects_each_changed_binding_before_state(recovery, section, field):
    policy = rec.PRODUCTION_INCIDENT_POLICY
    assert isinstance(policy, rec.IncidentPolicy)
    grant = {"authorization": policy.authorization_binding(), "evidence": policy.designated_evidence()}
    rec.require_current_incident_policy(grant)
    assert nothing_created(recovery)
    old = grant[section][field]
    grant[section][field] = old + 1 if type(old) is int else old + "-changed"
    with pytest.raises(rec.RecoveryError, match="incident_policy_binding_mismatch"):
        rec.require_current_incident_policy(grant)
    assert nothing_created(recovery)


def test_incident_policy_shape_is_closed():
    with pytest.raises(rec.RecoveryError, match="incident_policy_malformed"):
        rec.validate_incident_policy(None)
    with pytest.raises(rec.RecoveryError, match="incident_policy_malformed"):
        rec.validate_incident_policy({"original_request_id": "x"})
    base = {
        "original_request_id": ORIGINAL_REQUEST_ID,
        "original_request_sha256": "b" * 64,
        "original_release_sha": "c" * 40,
        "original_terminal_sha256": "a" * 64,
        "original_terminal_bytes": 10,
        "original_broker_exit_code": 65,
        "readiness_receipt_sha256": "e" * 64,
        "readiness_receipt_bytes": 20,
        "canary_id": "canary-123456789abc",
        "canary_exit_code": 1,
    }
    assert rec.validate_incident_policy(rec.IncidentPolicy(**fixture_authorization_fields(), **base)) == base
    for change in (
        {"canary_exit_code": 0},
        {"original_broker_exit_code": 0},
        {"original_terminal_sha256": "z" * 64},
        {"original_release_sha": "nope"},
        {"canary_id": "not-a-canary"},
        {"original_request_id": "../escape"},
        {"original_terminal_bytes": 0},
    ):
        with pytest.raises(rec.RecoveryError, match="incident_policy_malformed"):
            rec.validate_incident_policy(rec.IncidentPolicy(**fixture_authorization_fields(), **{**base, **change}))


def test_ordinary_producer_table_and_cause_admission_are_unchanged(recovery):
    s = recovery
    assert rec.PRODUCER_QUALIFICATION.producers == ()
    assert rec.PRODUCER_QUALIFICATION.vocabularies == {}
    cause = {
        "schema_version": rec.RECOVERY_EVIDENCE_SCHEMA,
        "authority_reference": rec.RECOVERY_AUTHORITY_REFERENCE,
        "producer": {
            "producer_id": "codex.exec.jsonl/0.159.2",
            "failure_class": rec.ORDINARY_FAILURE_CLASS,
            "codex_version": r.CODEX_VERSION,
            "codex_sha256": r.CODEX_SHA256,
            "event_schema": "codex.exec.jsonl.thread_event",
            "event_types_seen": ["turn.failed"],
            "events_total": 3,
            "truncated": False,
            "conflicting_events": [],
            "malformed_events": 0,
            "denial_refusal": None,
            "structured_error_code": None,
            "raw_message_digest": None,
        },
        "original_request_id": ORIGINAL_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_terminal_sha256": "a" * 64,
        "original_release_sha": "c" * 40,
        "original_receipt_sha256": s.digest,
        "original_result_completed": True,
        "original_canary_exit_code": 1,
        "original_broker_exit_code": 65,
        "original_timed_out": False,
        "original_signalled": False,
        "original_cancelled": False,
        "original_unknown_effect": False,
        "original_reserved": False,
        "original_denied": False,
        "observed_at": s.document["observed_at"],
    }
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(cause)


def test_incident_grant_schema_never_passes_the_ordinary_v1_reader(recovery, monkeypatch):
    """An unknown incident mislabelled as ordinary cannot enter admission."""
    s = recovery
    grant = incident_grant_document(s)
    payload = (json.dumps(grant, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (rec.RECOVERY_GRANT_PATH).write_bytes(payload)
    os.chmod(rec.RECOVERY_GRANT_PATH, 0o400)
    digest = receipt_digest(rec.RECOVERY_GRANT_PATH)
    with pytest.raises(rec.RecoveryError):
        rec.read_grant(expected_digest=digest)
    with pytest.raises(rec.RecoveryError):  # custody schema failure never falls through
        rec.read_grant_for_admission(expected_digest=digest)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_incident_history_fields_are_truthful_and_closed(recovery):
    s = recovery
    grant = incident_grant_document(s)
    validated = rec._validate_incident_grant_document(grant)
    assert validated["historical_cause"] == "UNKNOWN"
    assert validated["causal_link"] == "NOT_ESTABLISHED"
    assert validated["raw_provider_messages_retained"] is False
    assert "cause_evidence" not in validated
    with pytest.raises(rec.RecoveryError, match="incident_history_mislabelled"):
        rec._validate_incident_grant_document(
            incident_grant_document(s, causal_link="ESTABLISHED"))
    with pytest.raises(rec.RecoveryError, match="incident_history_mislabelled"):
        rec._validate_incident_grant_document(
            incident_grant_document(s, historical_cause="ordinary_provider_turn_failed"))
    with pytest.raises(rec.RecoveryError, match="incident_history_mislabelled"):
        rec._validate_incident_grant_document(
            incident_grant_document(s, raw_provider_messages_retained=True))
    with pytest.raises(rec.RecoveryError, match="recovery_grant_fields_malformed"):
        rec._validate_incident_grant_document(
            incident_grant_document(s, denial_evidence_retained=True))
    with pytest.raises(rec.RecoveryError, match="recovery_grant_fields_malformed"):
        rec._validate_incident_grant_document(
            incident_grant_document(s, cause_evidence={}))


# ---------------------------------------------------------------------------
# Typed action catalog and client surface.
# ---------------------------------------------------------------------------


def test_action_catalog_accepts_only_the_successor_argument():
    request = validate_request(incident_request_raw())
    assert request.effect_class == "CREDENTIAL_ADMIN_INCIDENT_ISSUANCE"
    assert request.args_dict() == {"successor_request_id": SUCCESSOR_REQUEST_ID}
    assert request.request_id == ISSUER_REQUEST_ID
    with pytest.raises(PrivilegedActionError, match="without an argv"):
        build_argv(request, Path("/tmp"))


@pytest.mark.parametrize("args", [
    {},
    {"successor_request_id": SUCCESSOR_REQUEST_ID, "credential_expires_at": "2026-12-31T00:00:00Z"},
    {"successor_request_id": SUCCESSOR_REQUEST_ID, "expected_credential_kind": "device-auth",
     "workspace_binding_class": "company-workspace-admin-attested",
     "credential_expires_at": "2026-12-31T00:00:00Z"},
    {"successor_request_id": SUCCESSOR_REQUEST_ID, "budget": "1"},
    {"successor_request_id": SUCCESSOR_REQUEST_ID, "slot_id": "codex-01"},
    {"successor_request_id": ""},
    {"successor_request_id": "../escape"},
])
def test_incident_action_rejects_caller_override_arguments(args):
    raw = incident_request_raw()
    raw["args"] = args
    with pytest.raises(PrivilegedActionError):
        validate_request(raw)


def test_incident_action_rejects_self_designation_and_other_actions():
    raw = incident_request_raw(successor=ISSUER_REQUEST_ID)
    with pytest.raises(PrivilegedActionError, match="successor"):
        validate_request(raw)
    for action in ("executive.worker_auth.verify_only",
                   "executive.worker_auth.recover_transaction",
                   "executive.services.start"):
        raw = incident_request_raw()
        raw["action"] = action
        with pytest.raises(PrivilegedActionError):
            validate_request(raw)


def test_canonical_request_bytes_bind_the_exact_incident_issuer_identity():
    left = validate_request(incident_request_raw())
    right = validate_request({
        "args": {"successor_request_id": SUCCESSOR_REQUEST_ID},
        "action": rec.INCIDENT_ISSUER_ACTION,
        "request_id": ISSUER_REQUEST_ID,
        "schema": REQUEST_SCHEMA,
    })
    assert canonical_request_bytes(left) == canonical_request_bytes(right)
    changed = validate_request(incident_request_raw(successor="req-incident-successor-2"))
    assert canonical_request_bytes(left) != canonical_request_bytes(changed)


def test_mmx_admin_requires_explicit_issuer_and_rejects_overrides(recovery):
    s = recovery
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    with pytest.raises(SystemExit):
        mmx_admin.build_request([rec.INCIDENT_ISSUER_ACTION,
                                 "--successor-request-id", SUCCESSOR_REQUEST_ID])
    with pytest.raises(SystemExit):
        mmx_admin.build_request([rec.INCIDENT_ISSUER_ACTION, "--request-id", ISSUER_REQUEST_ID])
    with pytest.raises(SystemExit):
        mmx_admin.build_request([
            rec.INCIDENT_ISSUER_ACTION, "--request-id", ISSUER_REQUEST_ID,
            "--successor-request-id", SUCCESSOR_REQUEST_ID,
            "--credential-expires-at", expiry])
    with pytest.raises(SystemExit):
        mmx_admin.build_request([
            rec.INCIDENT_ISSUER_ACTION, "--request-id", ISSUER_REQUEST_ID,
            "--successor-request-id", SUCCESSOR_REQUEST_ID,
            "--recover-current-pin-grant-sha256", "a" * 64])
    request = mmx_admin.build_request([
        rec.INCIDENT_ISSUER_ACTION, "--request-id", ISSUER_REQUEST_ID,
        "--successor-request-id", SUCCESSOR_REQUEST_ID])
    assert request == validate_request(incident_request_raw()).to_dict()
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request([
            "status", "--request-id", "req-status",
            "--successor-request-id", SUCCESSOR_REQUEST_ID])


# ---------------------------------------------------------------------------
# Positive test-only issuance: grant, commitment, terminal join, no respawn.
# ---------------------------------------------------------------------------


def test_incident_issuance_binds_grant_commitment_and_terminal_bytes(recovery, monkeypatch):
    s = recovery
    broker, receipt = issue_incident(s, monkeypatch)
    assert receipt["outcome"] == "SUCCEEDED" and receipt["exit_code"] == 0
    assert receipt["action"] == rec.INCIDENT_ISSUER_ACTION
    grant_path = rec.RECOVERY_INCIDENT_GRANT_PATH
    commitment_path = rec.RECOVERY_INCIDENT_COMMITMENT_PATH
    assert grant_path.exists() and commitment_path.exists()
    assert stat.S_IMODE(grant_path.stat().st_mode) == 0o400
    assert stat.S_IMODE(commitment_path.stat().st_mode) == 0o400
    assert grant_path.stat().st_nlink == 1
    commitment_bytes = commitment_path.read_bytes()
    grant_bytes = grant_path.read_bytes()
    commitment = read_custody(commitment_path)
    assert commitment["grant_sha256"] == receipt_digest(grant_path)
    assert commitment["successor_request_id"] == SUCCESSOR_REQUEST_ID
    assert commitment["issuer_request_id"] == ISSUER_REQUEST_ID
    assert receipt["stdout_sha256"] == hashlib.sha256(commitment_bytes).hexdigest()
    assert receipt["stdout_bytes"] == len(commitment_bytes)
    # No circular digest: the grant precedes and excludes every future
    # commitment/terminal digest field by construction.
    grant = json.loads(grant_bytes)
    assert frozenset(grant).isdisjoint(
        {"grant_sha256", "commitment_sha256", "stdout_sha256", "terminal_sha256"})
    issuer_digest = hashlib.sha256(
        canonical_request_bytes(validate_request(incident_request_raw()))
    ).hexdigest()
    assert grant["issuer_request_sha256"] == issuer_digest
    assert grant["executive_source"] == s.executive_source
    assert grant["evidence"] == s.designated
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()
    stored = json.loads(broker.receipt_path(ISSUER_REQUEST_ID).read_text())
    assert stored == receipt


def test_incident_issuance_replays_from_the_terminal_without_a_second_write(recovery, monkeypatch):
    s = recovery
    broker, receipt = issue_incident(s, monkeypatch)
    grant_before = rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes()
    stat_before = broker.receipt_path(ISSUER_REQUEST_ID).stat()
    receipt2 = broker.handle(incident_request_raw(), peer_uid=501)
    assert receipt2 == receipt
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes() == grant_before
    stat_after = broker.receipt_path(ISSUER_REQUEST_ID).stat()
    assert (stat_before.st_mtime_ns, stat_before.st_size, stat_before.st_ino) == (
        stat_after.st_mtime_ns, stat_after.st_size, stat_after.st_ino)


def test_incident_issuance_derives_current_source_not_the_historical_release(
    recovery, monkeypatch
):
    """The historical release can never satisfy the issuer (red on old source)."""
    s = recovery
    evidence = {
        "readiness_receipt_sha256": s.digest,
        "readiness_document": s.document,
        "readiness_transaction_lock_present": False,
        "verify_ready_processes": [],
        "current_auth_identity": dict(s.auth),
        "current_binary_identity": dict(s.current),
    }
    broker = PrivilegedActionBroker(
        PrivilegedBrokerConfig(
            # A release root that disagrees with the sealed loaded source.
            release_root=s.tmp / ("e" * 40),
            receipt_root=broker_module._RECEIPT_ROOT,
            allowed_peer_uids=(501,), timeout_seconds=30, broker_version="test",
        ),
        executor=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("incident issuance must never spawn a child")),
        require_root=False, trust_validator=lambda config: None,
        reconciliation_observer=lambda: evidence,
    )
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(s))
    with pytest.raises(PrivilegedBrokerError, match="running release"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert nothing_created(s)
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()


@pytest.mark.parametrize("change", [
    "wrong_predecessor_digest", "lock_present", "process_active", "binary_drift",
])
def test_incident_issuance_prerequisites_are_closed(recovery, monkeypatch, change):
    s = recovery
    evidence = {
        "readiness_receipt_sha256": s.digest,
        "readiness_document": s.document,
        "readiness_transaction_lock_present": False,
        "verify_ready_processes": [],
        "current_auth_identity": dict(s.auth),
        "current_binary_identity": dict(s.current),
    }
    if change == "wrong_predecessor_digest":
        evidence["readiness_receipt_sha256"] = "f" * 64
    elif change == "lock_present":
        evidence["readiness_transaction_lock_present"] = True
    elif change == "process_active":
        evidence["verify_ready_processes"] = ["bash provision-worker-auth.sh --verify-ready"]
    elif change == "binary_drift":
        evidence["current_binary_identity"] = {**s.current, "inode": 999}
    broker = PrivilegedActionBroker(
        PrivilegedBrokerConfig(
            release_root=s.tmp / s.executive_source["release_sha"],
            receipt_root=broker_module._RECEIPT_ROOT,
            allowed_peer_uids=(501,), timeout_seconds=30, broker_version="test",
        ),
        require_root=False, trust_validator=lambda config: None,
        reconciliation_observer=lambda: evidence,
    )
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(s))
    with pytest.raises(PrivilegedBrokerError):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert nothing_created(s)


@pytest.mark.parametrize("change", [
    "preimage", "canary_exit", "canary_id", "timeout", "passing", "denial_term",
])
def test_incident_issuance_refuses_contradicted_designated_evidence(
    recovery, monkeypatch, change
):
    s = recovery
    document = copy.deepcopy(s.document)
    if change == "preimage":
        # The retained predecessor bytes no longer match the designation.
        document["refusal"] = "provider_stream_error"
    elif change == "canary_exit":
        document["inference_canary"]["exit_code"] = 2
    elif change == "canary_id":
        document["inference_canary"]["canary_id"] = "canary-ffffffffffff"
    elif change == "timeout":
        document["inference_canary"]["timed_out"] = True
    elif change == "passing":
        document["inference_canary"]["passed"] = True
        document["inference_canary"]["refusal"] = None
    elif change == "denial_term":
        document["inference_canary"]["provider_error_terms"] = ["denied"]
    # The frozen pre-mutation designation stays fixed; the observer hands the
    # broker the mutated retained document so the specific evidence validator
    # is what refuses.
    monkeypatch.setattr(
        rec, "PRODUCTION_INCIDENT_POLICY", rec.IncidentPolicy(**fixture_authorization_fields(), **s.designated)
    )
    s.document = document
    broker = make_broker(s)
    with pytest.raises(PrivilegedBrokerError):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert nothing_created(s)


def test_partial_issuance_stays_the_same_operation_and_cannot_be_replaced(
    recovery, monkeypatch
):
    s = recovery
    broker, _receipt = issue_incident(s, monkeypatch)
    commitment_path = rec.RECOVERY_INCIDENT_COMMITMENT_PATH
    commitment_path.chmod(0o600)
    commitment_path.unlink()
    # Simulate a crash between the grant write and the terminal: the issuer
    # terminal and its replay evidence are gone.
    broker.receipt_path(ISSUER_REQUEST_ID).unlink()
    # Without either lifecycle record this is an orphaned grant, not a
    # resumable operation. Refuse before creating another marker or grant.
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(s))
    with pytest.raises(PrivilegedBrokerError, match="recovery_custody_slot_occupied"):
        broker.handle(incident_request_raw(), peer_uid=501)
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not commitment_path.exists()
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()


# ---------------------------------------------------------------------------
# Typed common admission and the consumer join (no producer qualification).
# ---------------------------------------------------------------------------


def test_incident_consumer_completes_without_any_producer_qualification(
    recovery, monkeypatch
):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    # qualification is deliberately never injected: incident admission is the
    # exact validator plus the issuer terminal join, never evaluate_cause.
    reserve_incident(s)
    allocation = rec.read_allocation()
    assert allocation["allocation_class"] == "due10_incident"
    assert allocation["consumed"] is True and allocation["budget"] == 1
    assert allocation["grant_sha256"] == s.incident_grant_digest
    assert allocation["successor_request_id"] == SUCCESSOR_REQUEST_ID
    assert allocation["predecessor_receipt_sha256"] == s.digest
    assert allocation["issuer_request_id"] == ISSUER_REQUEST_ID
    assert json.loads(s.receipt.read_bytes())["refusal"] == "canary_reserved"
    archive, = s.tmp.rglob("*.superseded-*")
    assert archive.stat().st_mode & 0o777 == 0o400


def test_incident_consumer_finalizes_ready_and_never_reallocates(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    # Finalization must retain the exact reserved expiry, even across a second
    # boundary. Recomputing now + 55 minutes fabricates a different credential.
    reserved_expiry = json.loads(s.receipt.read_bytes())["credential_expires_at"]
    canary_path = s.tmp / "canary.json"
    write_json(canary_path, canary(True))
    post = s.tmp / "post-identity.json"
    write_json(post, s.identity)
    assert r.main([
        "finalize", "--receipt", str(s.receipt), "--post-identity-json", str(post),
        "--post-identity-command-status", "0", "--canary-json", str(canary_path),
        "--canary-command-status", "0", "--expected-kind", "device-auth",
        "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", reserved_expiry,
    ]) == 0
    assert json.loads(s.receipt.read_bytes())["passed"] is True
    assert rec.read_allocation()["consumed"] is True
    # The consumed slot blocks every further claim, including the same one.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH,
            grant=read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH),
            grant_sha256=s.incident_grant_digest,
            predecessor_receipt_sha256=s.digest,
        )
    with pytest.raises(r.ReadinessError):
        reserve_incident(s)


def test_incident_admission_refuses_without_the_complete_issuance_join(
    recovery, monkeypatch
):
    s = recovery
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(s))
    # Manual grant and commitment bytes with no issuer terminal at all.
    grant = incident_grant_document(s)
    payload = (json.dumps(grant, sort_keys=True, separators=(",", ":")) + "\n").encode()
    grant_path = rec.RECOVERY_INCIDENT_GRANT_PATH
    commitment_path = rec.RECOVERY_INCIDENT_COMMITMENT_PATH
    grant_path.write_bytes(payload)
    os.chmod(grant_path, 0o400)
    commitment = {
        "schema_version": rec.INCIDENT_COMMITMENT_SCHEMA,
        "authorization": incident_policy(s).authorization_binding(),
        "incident_class": "due10_incident",
        "grant_sha256": hashlib.sha256(payload).hexdigest(),
        "issuer_request_id": ISSUER_REQUEST_ID,
        "issuer_request_sha256": ISSUER_REQUEST_SHA256,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "created_at": iso(datetime.now(UTC)),
    }
    commitment_path.write_bytes(
        (json.dumps(commitment, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.chmod(commitment_path, 0o400)
    incident_state(s)
    with pytest.raises(r.ReadinessError, match="incident_issuance_unverified"):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


@pytest.mark.parametrize("change", ["commitment_bytes", "wrong_successor",
                                    "issuer_inflight", "terminal_failed"])
def test_incident_admission_join_is_exact(recovery, monkeypatch, change):
    s = recovery
    broker, _receipt = issue_incident(s, monkeypatch)
    if change == "commitment_bytes":
        commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
        commitment["created_at"] = iso(datetime.now(UTC) + timedelta(seconds=1))
        rewrite_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH, commitment)
    elif change == "wrong_successor":
        commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
        commitment["successor_request_id"] = "req-someone-else"
        rewrite_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH, commitment)
    elif change == "issuer_inflight":
        marker = {
            "schema": "mastermind.executive_privileged_action_inflight.v1",
            "request_id": ISSUER_REQUEST_ID,
            "request_sha256": ISSUER_REQUEST_SHA256,
            "action": rec.INCIDENT_ISSUER_ACTION,
            "effect_class": "CREDENTIAL_ADMIN_INCIDENT_ISSUANCE",
            "started_at": iso(datetime.now(UTC)),
            "release_sha": s.executive_source["release_sha"],
        }
        path = broker.inflight_path(ISSUER_REQUEST_ID)
        path.write_bytes((json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.chmod(path, 0o600)
    elif change == "terminal_failed":
        receipt = json.loads(broker.receipt_path(ISSUER_REQUEST_ID).read_text())
        receipt["exit_code"] = 65
        receipt["outcome"] = "FAILED"
        path = broker.receipt_path(ISSUER_REQUEST_ID)
        path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
        os.chmod(path, 0o600)
    incident_state(s)
    with pytest.raises(r.ReadinessError):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_incident_consumer_refuses_evidenced_denial_and_old_source(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    # Retained denial vocabulary excludes admission outright.
    document = copy.deepcopy(s.document)
    document["inference_canary"]["provider_error_terms"] = ["permission"]
    s.receipt.chmod(0o600)
    write_json(s.receipt, document)
    os.chmod(s.receipt, 0o400)
    with pytest.raises(r.ReadinessError, match="incident_denial_evidenced"):
        reserve_incident(s)
    # Restore the designated predecessor and bind the grant to the historical
    # release instead of the current sealed source: red on old source.
    s.receipt.chmod(0o600)
    write_json(s.receipt, s.document)
    os.chmod(s.receipt, 0o400)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    grant["executive_source"] = {"release_sha": "c" * 40, "manifest_sha256": "b" * 64}
    rewrite_custody(rec.RECOVERY_INCIDENT_GRANT_PATH, grant)
    s.incident_grant_digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(r.ReadinessError):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_expired_incident_grant_blocks_admission_but_stays_readable(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    grant["granted_at"] = iso(datetime.now(UTC) - timedelta(minutes=90))
    grant["expires_at"] = iso(datetime.now(UTC) - timedelta(minutes=31))
    rewrite_custody(rec.RECOVERY_INCIDENT_GRANT_PATH, grant)
    s.incident_grant_digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    write_observation(s)
    with pytest.raises(r.ReadinessError, match="recovery_grant_expired"):
        reserve_incident(s)
    historical = rec._read_incident_historical_grant(expected_digest=s.incident_grant_digest)
    assert historical["successor_request_id"] == SUCCESSOR_REQUEST_ID
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


@pytest.mark.parametrize("change", ["symlink", "wrong_mode", "commitment_mode"])
def test_incident_custody_is_stable_root_only(recovery, monkeypatch, change):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    if change == "symlink":
        real = s.tmp / "grant-real.json"
        real.write_bytes(rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes())
        rec.RECOVERY_INCIDENT_GRANT_PATH.chmod(0o600)
        rec.RECOVERY_INCIDENT_GRANT_PATH.unlink()
        rec.RECOVERY_INCIDENT_GRANT_PATH.symlink_to(real)
    elif change == "wrong_mode":
        rec.RECOVERY_INCIDENT_GRANT_PATH.chmod(0o640)
    elif change == "commitment_mode":
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH.chmod(0o644)
    if change != "commitment_mode":
        with pytest.raises(rec.RecoveryError):
            rec.read_incident_grant(
                expected_digest=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))
    with pytest.raises(r.ReadinessError):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_one_allocation_slot_is_shared_by_both_policy_classes(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    record = rec.read_allocation()
    assert record["allocation_class"] == "due10_incident"
    # An ordinary grant can never allocate beside or after the incident claim.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_scope_conflict"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH,
            grant={"schema_version": rec.RECOVERY_GRANT_SCHEMA,
                   "cause_evidence": {"original_request_id": "req-other",
                                      "original_request_sha256": "9" * 64},
                   "executive_source": dict(s.executive_source),
                   "successor_request_id": "req-other",
                   "credential_lstat": dict(s.auth)},
            grant_sha256="a" * 64,
            predecessor_receipt_sha256="e" * 64,
        )
    # A different predecessor under the incident class is a conflict, not a key.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_scope_conflict"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH,
            grant=read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH),
            grant_sha256=s.incident_grant_digest,
            predecessor_receipt_sha256="e" * 64,
        )


def test_incident_allocation_record_is_truthful_at_the_fixed_path(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    record = rec.read_allocation()
    assert record["schema_version"] == rec.INCIDENT_ALLOCATION_SCHEMA
    assert record["consumed"] is True
    path = rec.RECOVERY_ALLOCATION_PATH
    assert stat.S_IMODE(path.stat().st_mode) == 0o400
    tampered = read_custody(path)
    tampered["consumed"] = False
    rewrite_custody(path, tampered)
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_not_consumed"):
        rec.read_allocation()


def test_parent_fixed_terminal_digest_matches_retained_contract():
    assert rec.INCIDENT_DESIGNATED_EVIDENCE["original_terminal_sha256"] == (
        "1ed264ba7e356cd5f673056a8275aca5492016e9e5fb0f4b2f02f6768bcbdde3"
    )


def test_parent_incident_never_borrows_ordinary_authorization(recovery, monkeypatch):
    issue_incident(recovery, monkeypatch)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    assert grant["authority_reference"] != rec.RECOVERY_AUTHORITY_REFERENCE


def test_parent_consumer_requires_current_incident_policy(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", None)
    with pytest.raises(r.ReadinessError, match="incident_policy_dormant"):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()
    assert receipt_digest(s.receipt) == s.digest


def test_parent_allocation_binds_actual_commitment_bytes(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    record = rec.read_allocation()
    assert record["commitment_sha256"] == receipt_digest(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)


@pytest.mark.parametrize("change", ["bytes", "mode", "inflight", "reconciled"])
def test_parent_consumer_rechecks_designated_terminal(recovery, monkeypatch, change):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    if change == "bytes":
        s.terminal_path.write_bytes(s.terminal_path.read_bytes() + b" ")
    elif change == "mode":
        s.terminal_path.chmod(0o644)
    else:
        (broker_module._RECEIPT_ROOT / change / (ORIGINAL_REQUEST_ID + ".json")).write_text("{}")
    with pytest.raises(r.ReadinessError):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()
    assert receipt_digest(s.receipt) == s.digest


@pytest.mark.parametrize("write_number", [1, 2])
def test_parent_partial_custody_write_is_effect_unknown(recovery, monkeypatch, write_number):
    s = recovery
    writer = rec.write_custody_document
    calls = []
    def fail_after_write(path, payload):
        result = writer(path, payload)
        calls.append(path)
        if len(calls) == write_number:
            raise rec.RecoveryError("recovery_allocation_unwritable")
        return result
    monkeypatch.setattr(rec, "write_custody_document", fail_after_write)
    with pytest.raises(EffectUnknownError):
        issue_incident(s, monkeypatch)
    assert make_broker(s).inflight_path(ISSUER_REQUEST_ID).exists()
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not make_broker(s).receipt_path(ISSUER_REQUEST_ID).exists()


def successor_reconciliation(s, broker):
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    target = validate_request({
        "schema": REQUEST_SCHEMA, "request_id": SUCCESSOR_REQUEST_ID,
        "action": "executive.worker_auth.verify_ready",
        "args": {"expected_credential_kind": "device-auth",
                 "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
                 "credential_expires_at": expiry,
                 "recover_current_pin_grant_sha256": s.incident_grant_digest,
                 "successor_request_id": SUCCESSOR_REQUEST_ID},
    })
    digest = hashlib.sha256(canonical_request_bytes(target)).hexdigest()
    broker._write_inflight(target, digest, iso(datetime.now(UTC) - timedelta(minutes=1)))
    return {
        "schema": broker_module.RECONCILE_REQUEST_SCHEMA,
        "target_request_id": target.request_id, "target_request_sha256": digest,
        "target_marker_sha256": receipt_digest(broker.inflight_path(target.request_id)),
        "target_release_sha": s.executive_source["release_sha"],
        "readiness_receipt_sha256": s.digest, "expected_credential_kind": "device-auth",
        "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
        "credential_expires_at": expiry,
    }


@pytest.mark.parametrize("allocated", [False, True])
def test_parent_incident_historical_broker_reconciliation(recovery, monkeypatch, allocated):
    s = recovery
    broker, _ = issue_incident(s, monkeypatch)
    incident_state(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    if allocated:
        rec.claim_or_refuse_allocation(rec.RECOVERY_ALLOCATION_PATH, grant=grant,
            grant_sha256=s.incident_grant_digest, predecessor_receipt_sha256=s.digest)
    raw = successor_reconciliation(s, broker)
    # Historical status must not need a live grant window or current policy.
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", None)
    monkeypatch.setattr(rec, "read_incident_grant", lambda **kw: (_ for _ in ()).throw(
        rec.RecoveryError("recovery_grant_expired")))
    record, replayed = broker.reconcile_not_applied(raw, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert broker.reconcile_not_applied(raw, peer_uid=501) == (record, True)
    assert rec.RECOVERY_ALLOCATION_PATH.exists() == allocated
    if allocated:
        assert rec.read_allocation()["consumed"] is True


@pytest.mark.parametrize("field", ["policy_id", "question_sha256", "answer_sha256", "provenance_sha256"])
def test_parent_consumer_rejects_changed_policy_binding(recovery, monkeypatch, field):
    import dataclasses
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    policy = rec.PRODUCTION_INCIDENT_POLICY
    replacement = "another-incident-policy" if field == "policy_id" else "9" * 64
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", dataclasses.replace(policy, **{field: replacement}))
    with pytest.raises(r.ReadinessError, match="incident_policy_binding_mismatch"):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


@pytest.mark.parametrize("field", ["policy_id", "commitment_sha256", "issuer_request_sha256", "grant_sha256"])
def test_parent_allocation_rejects_drift_from_issued_binding(recovery, monkeypatch, field):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    allocation = read_custody(rec.RECOVERY_ALLOCATION_PATH)
    allocation[field] = "other-policy" if field == "policy_id" else "9" * 64
    rewrite_custody(rec.RECOVERY_ALLOCATION_PATH, allocation)
    with pytest.raises(rec.RecoveryError):
        rec.read_allocation()


def test_parent_actual_expiry_retains_historical_reconciliation(recovery, monkeypatch):
    s = recovery
    broker, _ = issue_incident(s, monkeypatch)
    incident_state(s)
    raw = successor_reconciliation(s, broker)
    future = datetime.now(UTC) + timedelta(hours=2)
    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future
    monkeypatch.setattr(rec, "datetime", FutureDatetime)
    with pytest.raises(rec.RecoveryError, match="recovery_grant_expired"):
        rec.read_incident_grant(expected_digest=s.incident_grant_digest)
    record, replayed = broker.reconcile_not_applied(raw, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_parent_commitment_binds_distinct_policy_and_rejects_mutation(recovery, monkeypatch):
    s = recovery
    issue_incident(s, monkeypatch)
    incident_state(s)
    commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    assert commitment["authorization"] == grant["authorization"] == incident_policy(s).authorization_binding()
    commitment["authorization"]["answer_sha256"] = "9" * 64
    rewrite_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH, commitment)
    with pytest.raises(r.ReadinessError, match="incident_commitment_mismatch"):
        reserve_incident(s)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_parent_consumed_budget_precludes_new_issuer(recovery, monkeypatch):
    s = recovery
    broker, _ = issue_incident(s, monkeypatch)
    incident_state(s)
    reserve_incident(s)
    before = rec.RECOVERY_ALLOCATION_PATH.read_bytes()
    with pytest.raises(PrivilegedBrokerError, match="already consumed"):
        broker.handle(incident_request_raw(request_id="new-issuer", successor="new-successor"), peer_uid=501)
    assert rec.RECOVERY_ALLOCATION_PATH.read_bytes() == before
    assert not broker.inflight_path("new-issuer").exists()


def test_parent_incident_issuer_checks_actual_peer_before_policy(recovery, monkeypatch):
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(recovery))
    with pytest.raises(broker_module.PeerAuthorizationError):
        make_broker(recovery).handle(incident_request_raw(), peer_uid=999)
    assert nothing_created(recovery)


def test_parent_incident_reconciliation_refuses_wrong_target_digest(recovery, monkeypatch):
    s = recovery
    broker, _ = issue_incident(s, monkeypatch)
    incident_state(s)
    raw = successor_reconciliation(s, broker)
    raw["target_request_sha256"] = "9" * 64
    with pytest.raises(broker_module.RequestIdConflictError):
        broker.reconcile_not_applied(raw, peer_uid=501)
    assert broker.inflight_path(SUCCESSOR_REQUEST_ID).exists()
