"""Bounded current-pin recovery: production admission stays closed.

The pinned production ``codex`` 0.159.2 exec producer cannot establish ordinary
cause, so every production submission must refuse with
``recovery_failure_cause_unproven`` before any claim, archive, reservation or
inference.  The qualified path below exercises the claim, archive, CAS, one-use
and finalization machinery against an explicit test-only source-review table;
it is reachable only by calling the internal function with that table and is
never reachable from argv, config, environment, or any receipt field.
"""
from __future__ import annotations

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
from tests.test_provider_readiness_terminal_adverse import (
    canary, iso, state, write_json,
)


SUCCESSOR_REQUEST_ID = "req-current-pin-successor"
ORIGINAL_REQUEST_ID = "req-current-pin-predecessor"
ORIGINAL_REQUEST_SHA256 = "c" * 64
TEST_QUALIFICATION = rec.ProducerQualification(
    producers=("codex.exec.jsonl/reviewed-test-producer",),
    vocabularies={
        "codex.exec.jsonl/reviewed-test-producer": (
            "item.completed", "turn.failed", "turn.started",
        ),
    },
    terminal_events={"codex.exec.jsonl/reviewed-test-producer": "turn.failed"},
    source_review_reference="offline test table; not an installed source",
    evidence_verifier=lambda cause: (cause["original_request_id"] == ORIGINAL_REQUEST_ID
        and len(cause["original_terminal_sha256"]) == 64
        and len(cause["original_receipt_sha256"]) == 64),
)


def receipt_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def custody_root(tmp_path):
    """Build the fixed custody chain shape under a private temporary root."""
    root = tmp_path / "var" / "db" / "mastermind-executive" / "provider-recovery"
    state_root = root / "current-pin"
    state_root.mkdir(parents=True)
    # The custody walk covers the whole fixed chain below /var/db.
    for path in (
        tmp_path / "var",
        tmp_path / "var" / "db",
        tmp_path / "var" / "db" / "mastermind-executive",
        root,
        state_root,
    ):
        os.chmod(path, 0o700)
    return state_root


@pytest.fixture
def recovery(state, custody_root, monkeypatch):
    """A current-pin adverse predecessor with a structurally valid grant.

    Only host-path ownership and OS principal observation are substituted.  All
    bytes, digests, custody metadata, duplicate-key rejection, exclusive claim,
    archive and atomic CAS run unchanged.
    """
    s = state
    monkeypatch.setattr(r, "RECEIPT_PATH", s.receipt)
    monkeypatch.setattr(r, "AUTH_PATH", s.tmp / "provider-home")
    monkeypatch.setattr(r, "CODEX_BINARY", s.tmp / "codex-0.159.2")
    monkeypatch.setattr(rec, "RECOVERY_STATE_ROOT", custody_root)
    monkeypatch.setattr(rec, "RECOVERY_GRANT_PATH", custody_root / "grant.json")
    monkeypatch.setattr(rec, "RECOVERY_ALLOCATION_PATH", custody_root / "allocation.json")
    monkeypatch.setattr(rec, "CUSTODY_UID", os.getuid())
    monkeypatch.setattr(rec, "CUSTODY_GID", os.getgid())
    monkeypatch.setattr(rec._readiness, "RECEIPT_PATH", s.receipt)
    monkeypatch.setattr(rec._readiness, "AUTH_PATH", s.tmp / "provider-home")
    monkeypatch.setattr(rec._readiness, "CODEX_BINARY", s.tmp / "codex-0.159.2")
    monkeypatch.setattr(rec._readiness, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(rec._readiness, "_assert_no_macos_acl", lambda path: None)

    # Re-bind the installed-source identity to the substituted review path so
    # the grant, the predecessor receipt and the live observation all name the
    # exact same source.
    s.current = {**s.current, "path": os.fspath(r.CODEX_BINARY)}
    s.identity = {**s.identity, "codex_binary": dict(s.current)}
    monkeypatch.setattr(r, "current_auth_identity",
                        lambda *a, **k: dict(s.auth))
    monkeypatch.setattr(r, "current_binary_identity",
                        lambda *a, **k: dict(s.current))

    document = current_pin_adverse_document(s)
    write_json(s.receipt, document)
    s.document = document
    s.digest = receipt_digest(s.receipt)
    s.executive_source = {"release_sha": "a" * 40, "manifest_sha256": "b" * 64}
    monkeypatch.setattr(rec, "current_executive_source", lambda: dict(s.executive_source))
    from control_plane import executive_privileged_broker as broker_module
    terminal_root = s.tmp / "broker" / "receipts"
    for directory in (terminal_root, terminal_root / "inflight", terminal_root / "reconciled"):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(broker_module, "_RECEIPT_ROOT", terminal_root)
    # The fixture user stands in for root custody; stable bytes and all document
    # joins use the production readers. Separate tests exercise bad file modes.
    monkeypatch.setattr(broker_module, "_assert_root_owned_nonwritable",
                        lambda path, directory: path.lstat())
    when = datetime.fromisoformat(s.document["observed_at"].replace("Z", "+00:00"))
    s.terminal = {
        "schema": broker_module.RECEIPT_SCHEMA,
        "request_id": ORIGINAL_REQUEST_ID, "request_sha256": ORIGINAL_REQUEST_SHA256,
        "action": "executive.worker_auth.verify_ready",
        "effect_class": broker_module.ACTION_EFFECT_CLASS["executive.worker_auth.verify_ready"],
        "started_at": iso(when - timedelta(seconds=10)),
        "finished_at": iso(when + timedelta(seconds=10)),
        "release_sha": "c" * 40, "broker_version": "test",
        "exit_code": 65, "outcome": "FAILED",
        "stdout_bytes": 0, "stdout_sha256": hashlib.sha256(b"").hexdigest(), "stdout_excerpt": "",
        "stderr_bytes": 0, "stderr_sha256": hashlib.sha256(b"").hexdigest(), "stderr_excerpt": "",
    }
    s.terminal_path = terminal_root / (ORIGINAL_REQUEST_ID + ".json")
    write_json(s.terminal_path, s.terminal)
    s.terminal_path.chmod(0o600)
    s.cause = cause_document(s, s.digest)
    s.grant = grant_document(s, s.cause)
    s.grant_path = custody_root / "grant.json"
    write_json(s.grant_path, s.grant)
    s.grant_digest = receipt_digest(s.grant_path)
    s.qualification = TEST_QUALIFICATION
    return s


def current_pin_adverse_document(s):
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


def producer_document(**changes):
    producer = {
        "producer_id": "codex.exec.jsonl/0.159.2",
        "failure_class": "ordinary_provider_turn_failed",
        "codex_version": r.CODEX_VERSION,
        "codex_sha256": r.CODEX_SHA256,
        "event_schema": "codex.exec.jsonl.thread_event",
        "event_types_seen": ["item.completed", "turn.failed"],
        "events_total": 7,
        "truncated": False,
        "conflicting_events": [],
        "malformed_events": 0,
        "denial_refusal": None,
        "structured_error_code": None,
        "raw_message_digest": None,
    }
    producer.update(changes)
    return producer


def cause_document(s, predecessor_digest, *, producer=None):
    return {
        "schema_version": rec.RECOVERY_EVIDENCE_SCHEMA,
        "authority_reference": rec.RECOVERY_AUTHORITY_REFERENCE,
        "producer": producer or producer_document(),
        "original_request_id": ORIGINAL_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_terminal_sha256": receipt_digest(s.terminal_path),
        "original_release_sha": s.terminal["release_sha"],
        "original_receipt_sha256": predecessor_digest,
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


def grant_document(s, cause, **changes):
    grant = {
        "schema_version": rec.RECOVERY_GRANT_SCHEMA,
        "authority_reference": rec.RECOVERY_AUTHORITY_REFERENCE,
        "executive_source": dict(s.executive_source),
        "installed_source": {
            "path": os.fspath(r.CODEX_BINARY),
            "version": r.CODEX_VERSION,
            "sha256": r.CODEX_SHA256,
            "team_identifier": r.CODEX_TEAM_ID,
        },
        "worker": {
            "worker_user": "_mastermind_worker",
            "worker_uid": r.WORKER_UID,
            "worker_gid": r.WORKER_GID,
            "provider_home": os.fspath(r.AUTH_PATH.parent),
            "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
            "expected_credential_kind": "device-auth",
        },
        "credential_lstat": dict(s.auth),
        "model": r.PRODUCTION_MODEL,
        "cause_evidence": cause,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "budget": 1,
        "granted_at": iso(datetime.now(UTC) - timedelta(minutes=5)),
        "expires_at": iso(datetime.now(UTC) + timedelta(minutes=40)),
    }
    grant.update(changes)
    return grant


def cli(s, command, *, grant=None, request_id=SUCCESSOR_REQUEST_ID, **kwargs):
    args = [command, "--receipt", str(s.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
            "--credential-expires-at",
            kwargs.get("deadline", iso(datetime.now(UTC) + timedelta(minutes=55)))]
    if command == "reuse":
        args += ["--recover-current-pin-grant-sha256",
                 kwargs.get("grant", grant or s.grant_digest),
                 "--successor-request-id", request_id]
        return r.main(args)
    args += ["--recover-current-pin-grant-sha256", kwargs.get("grant", grant or s.grant_digest),
             "--successor-request-id", request_id,
             "--recovery-observation-json", kwargs.get("observation", str(s.observation_path))]
    return r.main(args)


def write_post_identity(s):
    path = s.tmp / "post-identity.json"
    write_json(path, s.identity)
    return path


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


def allocation_absent(s):
    return not (rec.RECOVERY_ALLOCATION_PATH).exists()


def no_evidence_written(s):
    """Nothing may be claimed or archived, so nothing can be reserved either."""
    return allocation_absent(s) and list(s.tmp.glob("*.superseded-*")) == []


# ---------------------------------------------------------------------------
# Production admission is closed: every unqualified cause refuses first.
# ---------------------------------------------------------------------------


@pytest.fixture
def closed_state(recovery):
    s = recovery
    s.observation_path = s.tmp / "observation.json"
    s.receipt_bytes = s.receipt.read_bytes()
    write_observation(s)
    return s


def test_production_cause_is_unproven_for_every_source_shape(closed_state):
    """The pinned producer is unqualified, so admission is closed."""
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(closed_state.cause)
    assert rec.PRODUCER_QUALIFICATION.producers == ()
    assert rec.PRODUCER_QUALIFICATION.vocabularies == {}


def test_empty_producer_table_cannot_be_extended_by_any_submission(closed_state):
    producer = producer_document(
        producer_id="codex.exec.jsonl/reviewed-test-producer",
        event_types_seen=["turn.failed"],
    )
    cause = cause_document(closed_state, closed_state.digest, producer=producer)
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(cause)
    assert rec.PRODUCER_QUALIFICATION.producers == ()
    assert rec.PRODUCER_QUALIFICATION.vocabularies == {}


@pytest.mark.parametrize("words", [
    ["provider_turn_failed"],
    ["rate", "limit"],
    ["capacity", "model"],
    ["overloaded", "usage"],
    ["error", "unknown"],
])
def test_legacy_and_capacity_text_is_diagnostic_only(closed_state, words):
    """Message vocabulary never promotes an unqualified producer to cause."""
    cause = cause_document(
        closed_state, closed_state.digest,
        producer=producer_document(event_types_seen=["turn.failed"], events_total=3,
                                   structured_error_code=" ".join(words)),
    )
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(cause)
    assert cause["producer"]["structured_error_code"] == " ".join(words)
    assert no_evidence_written(closed_state)


def test_caller_asserted_ordinary_class_is_not_cause(closed_state):
    cause = cause_document(
        closed_state, closed_state.digest,
        producer=producer_document(failure_class=rec.ORDINARY_FAILURE_CLASS),
    )
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(cause)
    assert no_evidence_written(closed_state)


@pytest.mark.parametrize("field", [
    "original_result_completed", "original_timed_out", "original_signalled",
    "original_cancelled", "original_unknown_effect", "original_reserved",
    "original_denied",
])
def test_unclosed_or_reserved_effect_attestations_are_refused(closed_state, field):
    value = copy.deepcopy(closed_state.cause)
    value[field] = False if field == "original_result_completed" else True
    with pytest.raises(rec.RecoveryError, match="recovery_cause_outcome_malformed"):
        rec.validate_cause_document(value)
    write_json(closed_state.grant_path, grant_document(closed_state, value))
    closed_state.grant_digest = receipt_digest(closed_state.grant_path)
    assert cli(closed_state, "reuse") == 2
    assert cli(closed_state, "reserve") == 2
    assert no_evidence_written(closed_state)


def test_denial_evidence_is_excluded_before_qualification(closed_state):
    cause = copy.deepcopy(closed_state.cause)
    cause["producer"] = producer_document(denial_refusal="provider_entitlement_denied")
    with pytest.raises(rec.RecoveryError, match="recovery_cause_denial_excluded"):
        rec.evaluate_cause(cause)


def test_declared_denial_attestation_is_structurally_refused(closed_state):
    cause = copy.deepcopy(closed_state.cause)
    cause["original_denied"] = True
    with pytest.raises(rec.RecoveryError, match="recovery_cause_outcome_malformed"):
        rec.evaluate_cause(cause)


@pytest.mark.parametrize("failure_class", [
    "unknown", "uncertain", "provider_rate_limited", "cancelled",
])
def test_uncertain_failure_class_is_refused(closed_state, failure_class):
    cause = copy.deepcopy(closed_state.cause)
    cause["producer"] = producer_document(failure_class=failure_class)
    with pytest.raises(rec.RecoveryError, match="recovery_cause_class_uncertain"):
        rec.evaluate_cause(cause)


@pytest.mark.parametrize("change", [
    "truncated", "conflicting", "malformed", "structured_code", "raw_digest",
    "terminal_absent", "event_unreviewed",
])
def test_incomplete_event_coverage_never_qualifies(closed_state, change):
    producer = producer_document(
        producer_id="codex.exec.jsonl/reviewed-test-producer",
        event_types_seen=["turn.failed"],
    )
    if change == "truncated":
        producer["truncated"] = True
    elif change == "conflicting":
        producer["conflicting_events"] = ["turn.started"]
    elif change == "malformed":
        producer["malformed_events"] = 1
    elif change == "structured_code":
        producer["structured_error_code"] = "rate_limited"
    elif change == "raw_digest":
        producer["raw_message_digest"] = "d" * 64
    elif change == "terminal_absent":
        producer["event_types_seen"] = ["item.completed"]
    elif change == "event_unreviewed":
        producer["event_types_seen"] = ["turn.failed", "unreviewed.event"]
    cause = cause_document(closed_state, closed_state.digest, producer=producer)
    if change == "event_unreviewed":
        with pytest.raises(rec.RecoveryError, match="recovery_cause_event_unreviewed"):
            rec.evaluate_cause(cause, qualification=TEST_QUALIFICATION)
    elif change == "terminal_absent":
        with pytest.raises(rec.RecoveryError, match="recovery_cause_terminal_event_absent"):
            rec.evaluate_cause(cause, qualification=TEST_QUALIFICATION)
    else:
        with pytest.raises(rec.RecoveryError, match="recovery_cause_coverage_incomplete"):
            rec.evaluate_cause(cause, qualification=TEST_QUALIFICATION)


@pytest.mark.parametrize("change", [
    "extra_field", "missing_field", "bad_schema", "bad_authority", "bad_request_id",
    "bad_digest", "exit_zero", "exit_bool", "bad_timestamp", "producer_extra",
])
def test_malformed_cause_documents_are_refused(closed_state, change):
    value = copy.deepcopy(closed_state.cause)
    if change == "extra_field":
        value["ordinary"] = True
    elif change == "missing_field":
        del value["original_canary_exit_code"]
    elif change == "bad_schema":
        value["schema_version"] = "mastermind.executive_provider_recovery_cause/v2"
    elif change == "bad_authority":
        value["authority_reference"] = "self-declared"
    elif change == "bad_request_id":
        value["original_request_id"] = ""
    elif change == "bad_digest":
        value["original_receipt_sha256"] = "z" * 64
    elif change == "exit_zero":
        value["original_canary_exit_code"] = 0
    elif change == "exit_bool":
        value["original_canary_exit_code"] = True
    elif change == "bad_timestamp":
        value["observed_at"] = "not-a-time"
    elif change == "producer_extra":
        value["producer"]["raw"] = "message"
    with pytest.raises(rec.RecoveryError):
        rec.evaluate_cause(value)


# ---------------------------------------------------------------------------
# Grant custody.
# ---------------------------------------------------------------------------


def test_grant_digest_alone_is_never_authority(recovery):
    """A matching digest with drifted custody bytes refuses."""
    s = recovery
    grant = copy.deepcopy(s.grant)
    grant["budget"] = 2
    write_json(s.grant_path, grant)
    s.grant_digest = receipt_digest(s.grant_path)
    assert cli(s, "reuse") == 2
    assert allocation_absent(s)


def test_grant_requires_exact_authority_reference(recovery):
    s = recovery
    grant = copy.deepcopy(s.grant)
    grant["authority_reference"] = "diagnostic-percentage-90"
    write_json(s.grant_path, grant)
    assert cli(s, "reuse", grant=receipt_digest(s.grant_path)) == 2
    assert allocation_absent(s)


@pytest.mark.parametrize("change", [
    "symlink", "hardlink", "duplicate_keys", "oversize", "truncated", "not_json",
    "wrong_mode", "world_readable",
])
def test_grant_custody_refuses_unsafe_files(recovery, change):
    s = recovery
    path = s.grant_path
    if change == "symlink":
        real = s.tmp / "grant-real.json"
        real.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(real)
    elif change == "hardlink":
        link = s.tmp / "grant-hardlink.json"
        os.link(path, link)
        path.unlink()
        os.link(link, path)
    elif change == "duplicate_keys":
        payload = json.dumps(s.grant, sort_keys=True, indent=2)
        duplicated = payload[:-2] + ',\n  "budget": 1\n}\n'
        path.unlink()
        path.write_text(duplicated)
        path.chmod(0o400)
    elif change == "oversize":
        path.chmod(0o600)
        path.write_bytes(b"x" * (17 * 1024))
        path.chmod(0o400)
    elif change == "truncated":
        raw = path.read_bytes()
        path.chmod(0o600)
        path.write_bytes(raw[:40])
        path.chmod(0o400)
    elif change == "not_json":
        path.chmod(0o600)
        path.write_bytes(b"not json")
        path.chmod(0o400)
    elif change in ("wrong_mode", "world_readable"):
        path.chmod(0o600 if change == "wrong_mode" else 0o644)
    digest = receipt_digest(path)
    assert cli(s, "reuse", grant=digest) == 2
    assert allocation_absent(s)


@pytest.mark.parametrize("change", [
    "source_path", "source_sha", "worker_user", "worker_uid", "worker_binding", "worker_kind",
    "provider_home", "credential_inode", "credential_mode", "model", "budget",
    "successor", "window_short", "window_long", "expired", "cause_mismatch",
    "schema", "extra_field",
])
def test_grant_bindings_and_bounds_are_closed(recovery, change):
    s = recovery
    grant = copy.deepcopy(s.grant)
    if change == "source_path":
        grant["installed_source"]["path"] = "/opt/homebrew/bin/codex"
    elif change == "source_sha":
        grant["installed_source"]["sha256"] = "a" * 64
    elif change == "worker_user":
        grant["worker"]["worker_user"] = "_another_worker"
    elif change == "worker_uid":
        grant["worker"]["worker_uid"] = 452
    elif change == "worker_binding":
        grant["worker"]["workspace_binding_class"] = "personal-pro-dedicated-worker-attested"
    elif change == "worker_kind":
        grant["worker"]["expected_credential_kind"] = "personal-access-token"
    elif change == "provider_home":
        grant["worker"]["provider_home"] = "/tmp/provider-home"
    elif change == "credential_inode":
        grant["credential_lstat"]["inode"] = 999
    elif change == "credential_mode":
        grant["credential_lstat"]["mode"] = 0o640
    elif change == "model":
        grant["model"] = "gpt-5.6-mini"
    elif change == "budget":
        grant["budget"] = 2
    elif change == "successor":
        grant["successor_request_id"] = "req-someone-else"
    elif change == "window_short":
        grant["granted_at"] = iso(datetime.now(UTC))
        grant["expires_at"] = iso(datetime.now(UTC) + timedelta(minutes=29))
    elif change == "window_long":
        grant["granted_at"] = iso(datetime.now(UTC) - timedelta(minutes=1))
        grant["expires_at"] = iso(datetime.now(UTC) + timedelta(minutes=61))
    elif change == "expired":
        grant["granted_at"] = iso(datetime.now(UTC) - timedelta(minutes=90))
        grant["expires_at"] = iso(datetime.now(UTC) - timedelta(minutes=31))
    elif change == "cause_mismatch":
        cause = copy.deepcopy(grant["cause_evidence"])
        cause["original_canary_exit_code"] = 0
        grant["cause_evidence"] = cause
    elif change == "schema":
        grant["schema_version"] = "mastermind.executive_provider_recovery_grant/v2"
    elif change == "extra_field":
        grant["ordinary"] = True
    write_json(s.grant_path, grant)
    digest = receipt_digest(s.grant_path)
    if change == "worker_user":
        with pytest.raises(rec.RecoveryError, match="recovery_grant_worker_mismatch"):
            rec.read_grant(expected_digest=digest)
    if change in {"expired", "window_short", "window_long"}:
        code = "recovery_grant_expired" if change == "expired" else "recovery_grant_window_invalid"
        with pytest.raises(rec.RecoveryError, match=code):
            rec.read_grant(expected_digest=digest)
    assert cli(s, "reuse", grant=digest) == 2
    assert allocation_absent(s)


def test_designated_successor_request_is_enforced(recovery):
    s = recovery
    assert cli(s, "reuse", request_id="req-someone-else") == 2
    assert cli(s, "reuse", request_id="") == 2
    assert cli(s, "reuse", request_id="req/current/pin") == 2
    assert allocation_absent(s)
    assert s.receipt.read_bytes() == json.dumps(s.document, sort_keys=True, indent=2).encode() + b"\n"


# ---------------------------------------------------------------------------
# Production entry point: the new option refuses before any write.
# ---------------------------------------------------------------------------


def test_production_entry_point_refuses_before_claim_archive_or_reserve(closed_state):
    s = closed_state
    original = s.receipt.read_bytes()
    assert cli(s, "reuse") == 2
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == original
    assert no_evidence_written(s)


def test_production_entry_point_requires_the_exact_company_preimage(closed_state):
    s = closed_state
    assert cli(s, "reuse", grant="a" * 64) == 2
    assert cli(s, "reuse", grant="A" * 64) == 2
    assert cli(s, "reuse", grant="a" * 63) == 2
    assert cli(s, "reserve", grant="a" * 64) == 2
    assert no_evidence_written(s)


def test_changed_predecessor_preimage_refuses(closed_state):
    s = closed_state
    changed = copy.deepcopy(s.document)
    changed["refusal"] = "provider_stream_error"
    write_json(s.receipt, changed)
    digest = receipt_digest(s.receipt)
    write_json(s.grant_path, grant_document(s, cause_document(s, digest)))
    s.grant_digest = receipt_digest(s.grant_path)
    assert cli(s, "reuse") == 2
    assert no_evidence_written(s)


@pytest.mark.parametrize("change", [
    "passing", "reserved", "unknown_class", "timeout", "exit_zero", "bool_exit",
    "canary_binary", "credential", "source", "identity_refusal", "kind", "binding",
])
def test_non_terminal_predecessors_never_recover(closed_state, change):
    s = closed_state
    d = copy.deepcopy(s.document)
    if change == "passing":
        d.update(passed=True, refusal=None)
    elif change == "reserved":
        d.update(refusal="canary_reserved")
        d["inference_canary"] = None
    elif change == "unknown_class":
        d["inference_canary"]["terminal_event_class"] = "unknown"
    elif change == "timeout":
        d["inference_canary"]["timed_out"] = True
    elif change == "exit_zero":
        d["inference_canary"]["exit_code"] = 0
    elif change == "bool_exit":
        d["inference_canary"]["exit_code"] = True
    elif change == "canary_binary":
        d["inference_canary"]["codex_sha256"] = "a" * 64
    elif change == "credential":
        d["credential_lstat"]["inode"] = 999
    elif change == "source":
        d["codex_binary"]["sha256"] = "a" * 64
    elif change == "identity_refusal":
        d["provider_identity"]["refusal"] = "company_plan_required"
    elif change == "kind":
        d["expected_credential_kind"] = "service-account"
    elif change == "binding":
        d["workspace_binding_class"] = "personal-pro-dedicated-worker-attested"
    write_json(s.receipt, d)
    digest = receipt_digest(s.receipt)
    write_json(s.grant_path, grant_document(s, cause_document(s, digest)))
    s.grant_digest = receipt_digest(s.grant_path)
    assert cli(s, "reuse") == 2
    assert cli(s, "reserve") == 2
    assert no_evidence_written(s)


def test_current_source_drift_or_auth_drift_refuses_before_observation(closed_state, monkeypatch):
    s = closed_state
    drifted = {**s.current, "inode": s.current["inode"] + 1}
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(drifted))
    assert cli(s, "reuse") == 2
    drifted_auth = {**s.auth, "inode": s.auth["inode"] + 1}
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(s.current))
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **k: dict(drifted_auth))
    assert cli(s, "reuse") == 2
    assert no_evidence_written(s)


@pytest.mark.parametrize("minutes", [0, 29, 61, 120])
def test_recovery_deadline_window_is_thirty_to_sixty_minutes(closed_state, minutes):
    deadline = iso(datetime.now(UTC) + timedelta(minutes=minutes))
    assert cli(closed_state, "reuse", deadline=deadline) == 2
    assert cli(closed_state, "reserve", deadline=deadline) == 2
    assert no_evidence_written(closed_state)


@pytest.mark.parametrize("change", [
    "wrong_request", "stale", "source", "credential", "ordinary_false",
    "catalog_incomplete", "catalog_missing_model", "refused", "not_diagnostic",
    "readiness_issued", "identity_refused", "extra_field",
])
def test_observation_is_transaction_bound_and_closed(qualified_state, monkeypatch, change):
    s = qualified_state
    if change == "wrong_request":
        write_observation(s, successor_request_id="req-someone-else")
    elif change == "stale":
        write_observation(s, observed_at=iso(datetime.now(UTC) - timedelta(minutes=10)))
    elif change == "source":
        write_observation(s, codex_binary={**s.current, "inode": 999})
    elif change == "credential":
        write_observation(s, credential_lstat={**s.auth, "inode": 999})
    elif change == "ordinary_false":
        write_observation(s, ordinary_usage_allowed=False)
    elif change == "catalog_incomplete":
        write_observation(s, model_catalog={"listed_in_returned_page": True, "complete": False})
    elif change == "catalog_missing_model":
        write_observation(s, model_catalog={"listed_in_returned_page": False, "complete": True})
    elif change == "refused":
        write_observation(s, observation_status="refused", refusal="provider_auth_failed",
                          ordinary_usage_allowed=None)
    elif change == "not_diagnostic":
        write_observation(s, observation_only=False)
    elif change == "readiness_issued":
        write_observation(s, readiness_issued=True)
    elif change == "identity_refused":
        identity = copy.deepcopy(s.identity)
        identity.update(passed=False, refusal="company_plan_required")
        write_observation(s, provider_identity=identity)
    elif change == "extra_field":
        observation = write_observation(s)
        observation["readiness_issued_receipt"] = True
        write_json(s.observation_path, observation)
    codes = {
        "wrong_request": "recovery_observation_request_mismatch",
        "stale": "recovery_observation_stale",
        "source": "recovery_observation_source_mismatch",
        "credential": "recovery_observation_credential_mismatch",
        "ordinary_false": "recovery_ordinary_usage_not_permitted",
        "catalog_incomplete": "recovery_model_catalog_incomplete",
        "catalog_missing_model": "recovery_model_catalog_incomplete",
        "refused": "recovery_observation_refused",
        "not_diagnostic": "recovery_observation_schema_malformed",
        "readiness_issued": "recovery_observation_schema_malformed",
        "identity_refused": "identity_not_passing",
        "extra_field": "recovery_observation_fields_malformed",
    }
    with pytest.raises(r.ReadinessError, match=codes[change]):
        reserve_qualified(s, monkeypatch)
    assert no_evidence_written(s)


def test_recovery_route_rejects_identity_override_and_missing_observation(closed_state):
    s = closed_state
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    shared = ["--receipt", str(s.receipt), "--expected-kind", "device-auth",
              "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
              "--credential-expires-at", expiry,
              "--recover-current-pin-grant-sha256", s.grant_digest,
              "--successor-request-id", SUCCESSOR_REQUEST_ID]
    # A caller-supplied identity file is an identity override channel: the
    # recovery route takes only the transaction-bound observation.
    override = r.main(["reserve", *shared, "--identity-json", str(s.identity_path),
                       "--recovery-observation-json", str(s.observation_path)])
    assert override == 2
    missing = r.main(["reserve", *shared, "--identity-json", str(s.identity_path)])
    assert missing == 2
    absent = r.main(["reserve", *shared])
    assert absent == 2
    assert no_evidence_written(s)
    assert s.receipt.read_bytes() == s.receipt_bytes


def test_no_new_option_is_accepted_on_any_other_route(recovery):
    s = recovery
    argv = ["--receipt", str(s.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", iso(datetime.now(UTC) + timedelta(minutes=55))]
    with pytest.raises(SystemExit):
        r.main(["validate", *argv, "--recover-current-pin-grant-sha256", "a" * 64])
    with pytest.raises(SystemExit):
        r.main(["reuse", *argv, "--requalify-terminal-adverse-sha256", s.digest,
                "--recover-current-pin-grant-sha256", "a" * 64])
    # The historical routes stay reachable and never gain the recovery option;
    # this current-pin predecessor is simply not their reviewed predecessor.
    assert r.main(["reuse", *argv, "--requalify-terminal-adverse-sha256", s.digest]) != 8
    assert r.main(["reuse", *argv, "--renew-device-revalidation-sha256", s.digest]) != 8
    assert allocation_absent(s)
    assert list(s.tmp.glob("*.superseded-*")) == []


def test_typed_catalog_binds_the_designated_request_and_no_other_route(recovery):
    from control_plane.executive_privileged_action import (
        PrivilegedActionError, REQUEST_SCHEMA, build_argv, canonical_request_bytes,
        validate_request,
    )
    from scripts import mmx_admin

    s = recovery
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    values = ["executive.worker_auth.verify_ready", "--request-id", SUCCESSOR_REQUEST_ID,
              "--expected-credential-kind", "device-auth",
              "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
              "--credential-expires-at", expiry,
              "--recover-current-pin-grant-sha256", s.grant_digest,
              "--successor-request-id", SUCCESSOR_REQUEST_ID]
    raw = mmx_admin.build_request(values)
    request = validate_request(raw)
    assert request.args_dict()["successor_request_id"] == request.request_id
    argv = build_argv(request, s.tmp)
    assert argv[-4:] == ("--recover-current-pin-grant-sha256", s.grant_digest,
                         "--successor-request-id", SUCCESSOR_REQUEST_ID)
    canonical = hashlib.sha256(canonical_request_bytes(request)).hexdigest()
    assert len(canonical) == 64
    # A designated successor that is not this request is refused at the client.
    with pytest.raises(PrivilegedActionError):
        mmx_admin.build_request(
            ["executive.worker_auth.verify_ready", "--request-id", "req-successor-1",
             "--expected-credential-kind", "device-auth",
             "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
             "--credential-expires-at", expiry,
             "--recover-current-pin-grant-sha256", s.grant_digest,
             "--successor-request-id", SUCCESSOR_REQUEST_ID])
    for changes in (
        {"recover_current_pin_grant_sha256": s.grant_digest},
        {"successor_request_id": SUCCESSOR_REQUEST_ID},
        {"recover_current_pin_grant_sha256": "A" * 64,
         "successor_request_id": SUCCESSOR_REQUEST_ID},
        {"recover_current_pin_grant_sha256": s.grant_digest,
         "successor_request_id": SUCCESSOR_REQUEST_ID,
         "requalify_terminal_adverse_sha256": "b" * 64},
    ):
        args = {"expected_credential_kind": "device-auth",
                "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
                "credential_expires_at": expiry}
        args.update(changes)
        with pytest.raises(PrivilegedActionError):
            validate_request({"schema": REQUEST_SCHEMA, "request_id": SUCCESSOR_REQUEST_ID,
                              "action": "executive.worker_auth.verify_ready", "args": args})
    with pytest.raises(SystemExit):
        mmx_admin.build_status_request(["status", "--request-id", "req-status",
                                        "--recover-current-pin-grant-sha256", s.grant_digest])
    for action in ("executive.worker_auth.verify_only",
                   "executive.worker_auth.recover_transaction",
                   "executive.services.start"):
        raw = mmx_admin.build_request(values)
        raw["action"] = action
        with pytest.raises(PrivilegedActionError):
            validate_request(raw)


# ---------------------------------------------------------------------------
# Qualified (test-only) path: one-use claim, CAS, finalization.
# ---------------------------------------------------------------------------


def reserve_qualified(s, monkeypatch, *, deadline=None, patch_context=True):
    """Drive the internal recovery reservation with the test-only table."""
    if patch_context:
        original_context = r._current_pin_recovery_context

        def context_with_test_table(args, **kwargs):
            kwargs.pop("qualification", None)
            return original_context(args, qualification=s.qualification, **kwargs)

        monkeypatch.setattr(r, "_current_pin_recovery_context", context_with_test_table)
    args = argparse_namespace(s, deadline=deadline)
    return r._reserve_current_pin_recovery(
        args,
        auth_identity=r.current_auth_identity(
            s.tmp / "provider-home", worker_uid=r.WORKER_UID, worker_gid=r.WORKER_GID,
        ),
        binary_identity=r.current_binary_identity(s.tmp / "codex-0.159.2"),
    )


def argparse_namespace(s, *, deadline=None):
    import argparse

    return argparse.Namespace(
        receipt=s.receipt,
        auth=s.tmp / "provider-home",
        binary=s.tmp / "codex-0.159.2",
        identity_json=None,
        expected_kind="device-auth",
        workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS,
        credential_expires_at=deadline or iso(datetime.now(UTC) + timedelta(minutes=55)),
        worker_uid=r.WORKER_UID,
        worker_gid=r.WORKER_GID,
        recover_current_pin_grant_sha256=s.grant_digest,
        successor_request_id=SUCCESSOR_REQUEST_ID,
        recovery_observation_json=s.observation_path,
        refresh_expired=False,
    )


@pytest.fixture
def qualified_state(closed_state):
    s = closed_state
    s.cause = cause_document(
        s, s.digest,
        producer=producer_document(
            producer_id="codex.exec.jsonl/reviewed-test-producer",
            event_types_seen=["item.completed", "turn.failed"],
            events_total=9,
        ),
    )
    s.grant_document_for_qualified = grant_document(s, s.cause)
    write_json(s.grant_path, s.grant_document_for_qualified)
    s.grant_digest = receipt_digest(s.grant_path)
    return s


def test_qualified_grant_still_requires_explicit_test_table(qualified_state):
    """Production qualification stays closed even for a fully bound grant."""
    with pytest.raises(rec.RecoveryError, match="recovery_failure_cause_unproven"):
        rec.evaluate_cause(qualified_state.cause)
    observed = rec.evaluate_cause(qualified_state.cause, qualification=TEST_QUALIFICATION)
    assert observed["producer"]["producer_id"] == "codex.exec.jsonl/reviewed-test-producer"


def test_qualified_claim_is_exclusive_and_consumes_before_reservation(
    qualified_state, monkeypatch
):
    s = qualified_state
    write_observation(s)
    original = s.receipt.read_bytes()
    reserve_qualified(s, monkeypatch)
    allocation = rec.read_allocation()
    assert allocation is not None
    assert allocation["consumed"] is True
    assert allocation["budget"] == 1
    assert allocation["predecessor_receipt_sha256"] == s.digest
    assert allocation["successor_request_id"] == SUCCESSOR_REQUEST_ID
    assert allocation["grant_sha256"] == s.grant_digest
    assert json.loads(s.receipt.read_bytes())["refusal"] == "canary_reserved"
    archive, = s.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == original
    assert archive.stat().st_mode & 0o777 == 0o400


def test_qualified_regrant_and_new_key_cannot_allocate_twice(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    reserve_qualified(s, monkeypatch)
    reserved_bytes = s.receipt.read_bytes()
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=s.grant_document_for_qualified,
            grant_sha256=s.grant_digest,
            predecessor_receipt_sha256=s.digest,
        )
    # A different predecessor digest is a scope conflict, never a second key.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_scope_conflict"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=s.grant_document_for_qualified,
            grant_sha256=s.grant_digest,
            predecessor_receipt_sha256="e" * 64,
        )
    # And a reservation re-run cannot reinstall over the final receipt either.
    assert cli(s, "reserve") == 2
    assert s.receipt.read_bytes() == reserved_bytes


def test_qualified_chained_adverse_cannot_recover_again(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    reserve_qualified(s, monkeypatch)
    canary_path = s.tmp / "canary.json"
    write_json(canary_path, canary(False))
    assert r.main([
        "finalize", "--receipt", str(s.receipt), "--post-identity-json", str(write_post_identity(s)),
        "--post-identity-command-status", "0", "--canary-json", str(canary_path),
        "--canary-command-status", "1", "--expected-kind", "device-auth",
        "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", iso(datetime.now(UTC) + timedelta(minutes=55)),
    ]) == 2
    final = s.receipt.read_bytes()
    assert json.loads(final)["passed"] is False
    # The new adverse receipt is not the retained predecessor, and the single
    # allocation is still keyed to the original one.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_scope_conflict"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=s.grant_document_for_qualified,
            grant_sha256=s.grant_digest,
            predecessor_receipt_sha256=receipt_digest(s.receipt),
        )
    assert cli(s, "reuse") == 2
    assert rec.read_allocation()["consumed"] is True


def test_qualified_success_finalization_and_no_second_allocation(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    # Reserve and finalize one immutable expiry; independently sampling the
    # second-granularity clock can otherwise cross a second boundary.
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    reserve_qualified(s, monkeypatch, deadline=expiry)
    canary_path = s.tmp / "canary.json"
    write_json(canary_path, canary(True))
    assert r.main([
        "finalize", "--receipt", str(s.receipt), "--post-identity-json", str(write_post_identity(s)),
        "--post-identity-command-status", "0", "--canary-json", str(canary_path),
        "--canary-command-status", "0", "--expected-kind", "device-auth",
        "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", expiry,
    ]) == 0
    final = json.loads(s.receipt.read_bytes())
    assert final["passed"] is True
    assert rec.read_allocation()["consumed"] is True
    assert cli(s, "reuse") == 2


def test_qualified_lost_response_stays_unknown_and_consumes_budget(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    reserve_qualified(s, monkeypatch)
    # An unknown post-call effect cannot be promoted into a passing receipt.
    assert r.main([
        "finalize", "--receipt", str(s.receipt), "--post-identity-json", str(write_post_identity(s)),
        "--post-identity-command-status", "75", "--canary-json", str(s.tmp / "absent.json"),
        "--canary-command-status", "75", "--expected-kind", "device-auth",
        "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", iso(datetime.now(UTC) + timedelta(minutes=55)),
    ]) == 2
    final = json.loads(s.receipt.read_bytes())
    assert final["passed"] is False and final["inference_canary"] is None
    assert rec.read_allocation()["consumed"] is True
    assert cli(s, "reuse") == 2


def test_qualified_claim_without_refund_survives_a_crash(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    original = s.receipt.read_bytes()
    real_replace = os.replace

    def crash(src, dst):
        if Path(dst) == s.receipt:
            raise OSError("simulated power loss before CAS")
        return real_replace(src, dst)

    monkeypatch.setattr(r.os, "replace", crash)
    with pytest.raises(OSError):
        reserve_qualified(s, monkeypatch)
    assert rec.read_allocation()["consumed"] is True
    assert s.receipt.read_bytes() == original
    archive, = s.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == original
    # Retrying cannot refund or re-allocate: the same key is already consumed.
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=s.grant_document_for_qualified,
            grant_sha256=s.grant_digest, predecessor_receipt_sha256=s.digest,
        )


def test_qualified_expired_grant_refuses_before_claim(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    grant = copy.deepcopy(s.grant_document_for_qualified)
    grant["granted_at"] = iso(datetime.now(UTC) - timedelta(minutes=90))
    grant["expires_at"] = iso(datetime.now(UTC) - timedelta(minutes=31))
    write_json(s.grant_path, grant)
    s.grant_digest = receipt_digest(s.grant_path)
    with pytest.raises(r.ReadinessError, match="recovery_grant_expired"):
        reserve_qualified(s, monkeypatch)
    assert allocation_absent(s)
    assert list(s.tmp.glob("*.superseded-*")) == []


def test_qualified_source_or_auth_drift_refuses_before_claim(qualified_state, monkeypatch):
    s = qualified_state
    write_observation(s)
    monkeypatch.setattr(
        r, "current_binary_identity",
        lambda *a, **k: {**s.current, "inode": s.current["inode"] + 1},
    )
    with pytest.raises(r.ReadinessError):
        reserve_qualified(s, monkeypatch)
    assert allocation_absent(s)
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(s.current))
    monkeypatch.setattr(
        r, "current_auth_identity",
        lambda *a, **k: {**s.auth, "inode": s.auth["inode"] + 1},
    )
    with pytest.raises(r.ReadinessError):
        reserve_qualified(s, monkeypatch)
    assert allocation_absent(s)


def test_allocation_custody_refuses_tampered_records(qualified_state):
    s = qualified_state
    path = rec.RECOVERY_ALLOCATION_PATH
    path.write_text("{}\n")
    path.chmod(0o400)
    with pytest.raises(rec.RecoveryError):
        rec.read_allocation()
    path.unlink()
    record = {
        "schema_version": rec.RECOVERY_ALLOCATION_SCHEMA,
        "allocation_class": "current_pin_recovery",
        "authority_reference": rec.RECOVERY_AUTHORITY_REFERENCE,
        "predecessor_receipt_sha256": "f" * 64,
        "predecessor_request_id": ORIGINAL_REQUEST_ID,
        "predecessor_request_sha256": ORIGINAL_REQUEST_SHA256,
        "grant_sha256": "f" * 64,
        "executive_source": dict(s.executive_source),
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "worker_uid": r.WORKER_UID,
        "worker_gid": r.WORKER_GID,
        "provider_home": os.fspath(r.AUTH_PATH.parent),
        "codex_version": r.CODEX_VERSION,
        "codex_sha256": r.CODEX_SHA256,
        "credential_lstat": dict(s.auth),
        "budget": 1,
        "consumed": False,
        "claimed_at": r.now_iso(),
    }
    path.write_text(json.dumps(record, sort_keys=True) + "\n")
    path.chmod(0o400)
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_not_consumed"):
        rec.read_allocation()


def test_broker_reconciliation_binds_grant_successor_and_allocation(qualified_state, monkeypatch):
    from control_plane.executive_privileged_action import (
        REQUEST_SCHEMA, canonical_request_bytes, validate_request,
    )
    from control_plane.executive_privileged_broker import (
        RECONCILE_REQUEST_SCHEMA, PrivilegedActionBroker, PrivilegedBrokerConfig,
        PrivilegedBrokerError,
    )
    import subprocess

    s = qualified_state
    write_observation(s)
    expiry = iso(datetime.now(UTC) + timedelta(minutes=55))
    target = validate_request({
        "schema": REQUEST_SCHEMA, "request_id": SUCCESSOR_REQUEST_ID,
        "action": "executive.worker_auth.verify_ready",
        "args": {"expected_credential_kind": "device-auth",
                 "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
                 "credential_expires_at": expiry,
                 "recover_current_pin_grant_sha256": s.grant_digest,
                 "successor_request_id": SUCCESSOR_REQUEST_ID},
    })
    target_digest = hashlib.sha256(canonical_request_bytes(target)).hexdigest()
    marker = {
        "schema": "mastermind.executive_privileged_action_inflight.v1",
        "request_id": target.request_id, "request_sha256": target_digest,
        "action": target.action, "effect_class": target.effect_class,
        "started_at": iso(datetime.now(UTC) - timedelta(minutes=1)),
        "release_sha": "a" * 40,
    }
    raw = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    broker = PrivilegedActionBroker(
        PrivilegedBrokerConfig(release_root=s.tmp / ("a" * 40),
                               receipt_root=s.tmp / "receipts",
                               allowed_peer_uids=(501,), timeout_seconds=30,
                               broker_version="test"),
        executor=lambda *a, **k: subprocess.CompletedProcess([], 0, b"", b""),
        require_root=False, trust_validator=lambda c: None,
        reconciliation_observer=lambda: {
            "readiness_receipt_sha256": s.digest,
            "readiness_document": s.document,
            "current_auth_identity": s.auth,
            "current_binary_identity": s.current,
            "readiness_transaction_lock_present": False,
            "verify_ready_processes": [],
        },
    )
    broker.inflight_path(target.request_id).write_bytes(raw)
    broker.inflight_path(target.request_id).chmod(0o600)
    reconcile = {
        "schema": RECONCILE_REQUEST_SCHEMA,
        "target_request_id": target.request_id,
        "target_request_sha256": target_digest,
        "target_marker_sha256": hashlib.sha256(raw).hexdigest(),
        "target_release_sha": "a" * 40,
        "readiness_receipt_sha256": s.digest,
        "expected_credential_kind": "device-auth",
        "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
        "credential_expires_at": expiry,
    }
    record, replayed = broker.reconcile_not_applied(reconcile, peer_uid=501)
    assert not replayed and record["classification"] == "NOT_APPLIED"
    assert broker.reconcile_not_applied(reconcile, peer_uid=501) == (record, True)
    # No reservation may be installed by a reconciled request.
    with pytest.raises(PrivilegedBrokerError):
        broker.handle(json.loads(json.dumps(target.to_dict())), peer_uid=501)
    assert allocation_absent(s)
    # Once the budget is claimed, reconciliation still proves not-applied while
    # the allocation stays bound to this exact request and predecessor.
    s.receipt.chmod(0o400)
    rec.claim_or_refuse_allocation(
        rec.RECOVERY_ALLOCATION_PATH, grant=s.grant_document_for_qualified,
        grant_sha256=s.grant_digest, predecessor_receipt_sha256=s.digest,
    )
    record2, replayed2 = broker.reconcile_not_applied(reconcile, peer_uid=501)
    assert replayed2 is True
    assert rec.read_allocation()["consumed"] is True
    # A foreign successor binding is refused outright.
    tampered = dict(reconcile, target_request_id="req-someone-else")
    with pytest.raises(PrivilegedBrokerError):
        broker.reconcile_not_applied(tampered, peer_uid=501)


@pytest.mark.parametrize("unsafe_mode", [0o600, 0o644, 0o666])
def test_root_adjudication_grant_custody_rejects_mode_before_cause(recovery, unsafe_mode):
    """A producer refusal must not hide acceptance of mutable grant custody."""
    recovery.grant_path.chmod(unsafe_mode)
    with pytest.raises(rec.RecoveryError, match="recovery_custody_metadata_unsafe"):
        rec.read_grant(expected_digest=receipt_digest(recovery.grant_path))


def test_root_adjudication_grant_not_yet_issued_cannot_be_admitted(recovery):
    now = datetime.now(UTC)
    grant = {**recovery.grant, "granted_at": iso(now + timedelta(minutes=10)),
             "expires_at": iso(now + timedelta(minutes=55))}
    with pytest.raises(rec.RecoveryError, match="recovery_grant_window_invalid"):
        rec.validate_grant_document(grant, now=now)


def test_root_adjudication_consumed_budget_requires_integer_one(qualified_state):
    s = qualified_state
    record = rec.claim_or_refuse_allocation(rec.RECOVERY_ALLOCATION_PATH,
        grant=s.grant_document_for_qualified, grant_sha256=s.grant_digest,
        predecessor_receipt_sha256=s.digest)
    record["budget"] = True
    write_json(rec.RECOVERY_ALLOCATION_PATH, record)
    with pytest.raises(rec.RecoveryError, match="recovery_allocation_not_consumed"):
        rec.read_allocation()


@pytest.mark.parametrize("edge", ["missing", "digest", "mode", "inflight", "reconciled", "action", "release", "clock"])
def test_root_original_terminal_join_is_real_and_closed(recovery, edge):
    s = recovery
    assert rec.validate_original_terminal(s.cause)["exit_code"] == 65
    cause = dict(s.cause)
    if edge == "missing":
        s.terminal_path.unlink()
    elif edge == "digest":
        cause["original_terminal_sha256"] = "d" * 64
    elif edge == "mode":
        s.terminal_path.chmod(0o666)
    elif edge in {"inflight", "reconciled"}:
        (s.terminal_path.parent / edge / s.terminal_path.name).write_text("{}")
    elif edge == "action":
        record = dict(s.terminal, action="executive.worker_auth.verify_only")
        write_json(s.terminal_path, record)
        s.terminal_path.chmod(0o600)
        cause["original_terminal_sha256"] = receipt_digest(s.terminal_path)
    elif edge == "release":
        cause["original_release_sha"] = "d" * 40
    else:
        cause["observed_at"] = iso(datetime.now(UTC))
    with pytest.raises(rec.RecoveryError):
        rec.validate_original_terminal(cause)
    assert allocation_absent(s)


def test_root_qualified_vocabulary_without_evidence_link_never_admits(qualified_state):
    import dataclasses
    qualification = dataclasses.replace(TEST_QUALIFICATION, evidence_verifier=None)
    with pytest.raises(rec.RecoveryError, match="recovery_failure_link_unproven"):
        rec.evaluate_cause(qualified_state.cause, qualification=qualification)
    for result in (False, None, 1, "true"):
        qualification = dataclasses.replace(TEST_QUALIFICATION,
            evidence_verifier=lambda cause, result=result: result)
        with pytest.raises(rec.RecoveryError, match="recovery_failure_link_unproven"):
            rec.evaluate_cause(qualified_state.cause, qualification=qualification)


def test_root_qualified_source_must_match_loaded_executive_release(qualified_state, monkeypatch):
    s = qualified_state
    grant = dict(s.grant_document_for_qualified,
                 executive_source={"release_sha": "d" * 40, "manifest_sha256": "e" * 64})
    write_json(s.grant_path, grant)
    s.grant_digest = receipt_digest(s.grant_path)
    write_observation(s)
    with pytest.raises(r.ReadinessError, match="recovery_executive_source_mismatch"):
        reserve_qualified(s, monkeypatch)
    assert allocation_absent(s)


def test_root_executive_source_uses_existing_manifest_and_actual_file_bytes(tmp_path, monkeypatch):
    from ops.executive_os import release_manifest
    from control_plane import executive_privileged_broker as broker
    prefix = tmp_path / "releases"
    root = prefix / ("a" * 40)
    script = root / "ops" / "executive_os" / "provider_recovery.py"
    script.parent.mkdir(parents=True)
    script.write_text("fixture source\n")
    monkeypatch.setattr(broker, "_RELEASE_PREFIX", prefix)
    monkeypatch.setattr(rec, "__file__", str(script))
    # Substitute only OS ownership/ACL; original manifest creation, complete
    # entry hashing and verification are exercised over actual temp files.
    monkeypatch.setattr(release_manifest, "_validate_owned_info", lambda *a, **k: None)
    monkeypatch.setattr(release_manifest, "_has_acl", lambda *a: False)
    manifest = release_manifest.create(root, root.name, "b" * 40)
    assert rec.current_executive_source() == {
        "release_sha": root.name, "manifest_sha256": receipt_digest(manifest)}
    script.write_text("changed source\n")
    with pytest.raises(rec.RecoveryError, match="recovery_executive_source_unverified"):
        rec.current_executive_source()


from tests.test_provider_model_capacity_diagnostic import live as capacity_live


def test_root_recovery_observation_keeps_exact_source_and_nullable_permission(capacity_live, monkeypatch):
    from ops.executive_os import provider_identity_probe as probe
    live = capacity_live
    source = {"release_sha": "a" * 40, "manifest_sha256": "b" * 64}
    monkeypatch.setattr(rec, "current_executive_source", lambda: dict(source))
    observation, identity = probe.live_probe(**live.kwargs, recovery_request_id=SUCCESSOR_REQUEST_ID)
    observation["capacity"]["ordinary_usage_allowed"] = None
    value = probe.recovery_observation_document(SUCCESSOR_REQUEST_ID, "codex-01", observation, identity)
    assert value["executive_source"] == source
    assert value["ordinary_usage_allowed"] is None
    assert "executive_source" not in value["provider_identity"]
    assert live.closed == 1


def test_root_recovery_observation_source_drift_refuses(capacity_live, monkeypatch):
    from ops.executive_os import provider_identity_probe as probe
    live = capacity_live
    sources = iter([{"release_sha": "a" * 40, "manifest_sha256": "b" * 64},
                    {"release_sha": "a" * 40, "manifest_sha256": "c" * 64}])
    monkeypatch.setattr(rec, "current_executive_source", lambda: next(sources))
    with pytest.raises(probe.IdentityProbeError, match="recovery_observation_source_mismatch"):
        probe.live_probe(**live.kwargs, recovery_request_id=SUCCESSOR_REQUEST_ID)
    assert live.closed == 1


@pytest.mark.parametrize("failure", ["source", "terminal", "allocation"])
@pytest.mark.parametrize("error_type", [rec.RecoveryError, r.ReadinessError, OSError])
def test_review_reconciliation_reader_errors_become_bounded_refusal(qualified_state, monkeypatch, failure, error_type):
    from control_plane import executive_privileged_broker as b
    def broken(*args, **kwargs):
        raise error_type("private_fixture_failure")
    name = {"source": "current_executive_source", "terminal": "validate_original_terminal",
            "allocation": "read_allocation"}[failure]
    monkeypatch.setattr(rec, name, broken)
    with pytest.raises(b.BrokerTrustError):
        test_broker_reconciliation_binds_grant_successor_and_allocation(qualified_state, monkeypatch)


def test_review_allocation_exact_mode_is_independent_of_umask(qualified_state):
    s = qualified_state
    prior = os.umask(0o777)
    try:
        rec.claim_or_refuse_allocation(rec.RECOVERY_ALLOCATION_PATH,
            grant=s.grant_document_for_qualified, grant_sha256=s.grant_digest,
            predecessor_receipt_sha256=s.digest)
    finally:
        os.umask(prior)
    assert stat.S_IMODE(rec.RECOVERY_ALLOCATION_PATH.stat().st_mode) == 0o400
    assert rec.read_allocation()["consumed"] is True


def test_review_successor_flag_cannot_be_ignored_on_reuse(recovery, capsys):
    s = recovery
    assert r.main(["reuse", "--receipt", str(s.tmp / "missing-readiness.json"),
        "--expected-kind", "device-auth", "--workspace-binding-class", r.COMPANY_WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline, "--successor-request-id", SUCCESSOR_REQUEST_ID]) == 2
    assert "recovery_arguments_are_recovery_only" in capsys.readouterr().err


def test_review_expired_grant_does_not_destroy_target_reconstruction(qualified_state, monkeypatch):
    from control_plane import executive_privileged_broker as b
    from control_plane.executive_privileged_action import validate_request, canonical_request_bytes, REQUEST_SCHEMA
    s = qualified_state
    args = {"expected_credential_kind": "device-auth", "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
        "credential_expires_at": s.deadline, "recover_current_pin_grant_sha256": s.grant_digest,
        "successor_request_id": SUCCESSOR_REQUEST_ID}
    target = validate_request({"schema": REQUEST_SCHEMA, "request_id": SUCCESSOR_REQUEST_ID,
        "action": "executive.worker_auth.verify_ready", "args": args})
    original_read = rec.read_grant
    later = datetime.now(UTC) + timedelta(hours=2)
    def advanced(*args, **kwargs):
        kwargs.setdefault("now", later)
        return original_read(*args, **kwargs)
    monkeypatch.setattr(rec, "read_grant", advanced)
    raw = {**args, "target_request_id": SUCCESSOR_REQUEST_ID,
        "target_request_sha256": hashlib.sha256(canonical_request_bytes(target)).hexdigest(),
        "readiness_receipt_sha256": s.digest,
        "target_started_at": iso(datetime.now(UTC) - timedelta(minutes=1))}
    assert b._reconciliation_target(raw).to_dict() == target.to_dict()
    with pytest.raises(rec.RecoveryError, match="recovery_grant_expired"):
        rec.read_grant(expected_digest=s.grant_digest)


def test_review_expired_grant_reconciliation_remains_readable_without_refund(qualified_state, monkeypatch):
    original_read = rec.read_grant
    later = datetime.now(UTC) + timedelta(hours=2)
    def advanced(*args, **kwargs):
        kwargs.setdefault("now", later)
        return original_read(*args, **kwargs)
    monkeypatch.setattr(rec, "read_grant", advanced)
    # Exercises initial NOT_APPLIED, durable replay and replay after allocation.
    test_broker_reconciliation_binds_grant_successor_and_allocation(qualified_state, monkeypatch)
    with pytest.raises(rec.RecoveryError, match="recovery_grant_expired"):
        rec.read_grant(expected_digest=qualified_state.grant_digest)


@pytest.mark.parametrize("change", ["digest", "mode", "window", "extra", "duplicate"])
def test_review_historical_grant_still_requires_exact_immutable_evidence(qualified_state, change):
    s = qualified_state
    digest = s.grant_digest
    if change == "digest":
        digest = "f" * 64
    elif change == "mode":
        s.grant_path.chmod(0o600)
    elif change == "duplicate":
        raw = s.grant_path.read_text().rstrip()
        s.grant_path.chmod(0o600)
        s.grant_path.write_text(raw[:-1] + ', "budget": 1}')
        s.grant_path.chmod(0o400)
        digest = receipt_digest(s.grant_path)
    else:
        grant = copy.deepcopy(s.grant_document_for_qualified)
        if change == "window":
            grant["expires_at"] = grant["granted_at"]
        else:
            grant["allow_expired"] = True
        write_json(s.grant_path, grant)
        digest = receipt_digest(s.grant_path)
    with pytest.raises(rec.RecoveryError):
        rec._read_historical_grant(expected_digest=digest)


@pytest.mark.parametrize("value", [65, 0, True])
def test_review_canary_exit_is_not_broker_or_client_exit(recovery, value):
    cause = dict(recovery.cause, original_canary_exit_code=value)
    with pytest.raises(rec.RecoveryError, match="recovery_cause_outcome_malformed"):
        rec.validate_cause_document(cause)


@pytest.mark.parametrize("value", [1, 2, 64])
def test_review_broker_exit_joins_exact_canonical_terminal(recovery, value):
    cause = dict(recovery.cause, original_broker_exit_code=value)
    rec.validate_cause_document(cause)
    with pytest.raises(rec.RecoveryError, match="recovery_original_request_exit_mismatch"):
        rec.validate_original_terminal(cause)


@pytest.mark.parametrize("value", [0, -1, True])
def test_review_broker_exit_is_positive_strict_integer(recovery, value):
    with pytest.raises(rec.RecoveryError, match="recovery_cause_outcome_malformed"):
        rec.validate_cause_document(dict(recovery.cause, original_broker_exit_code=value))
