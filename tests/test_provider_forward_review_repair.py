"""Principal falsifiers for the original independent forward-core review.

These tests reproduce, against the unchanged core, the five confirmed parent
findings (uniform original-digest substitution, dormant-policy allocation
readability, ordinary v1 forward-module import, empty-evidence occupant
classification, unbound forward status terminal) and the accepted lower
findings (client forward response validation, typed guard readback, closed
status wire naming, unused ordinary connection parameter).  All fixtures are
private offline collaborators; nothing here is production permission,
activation, authority or readiness.
"""
from __future__ import annotations

import builtins
import hashlib
import inspect
import json
import os
from pathlib import Path

import pytest

from ops.executive_os import provider_recovery as rec
from ops.executive_os import provider_incident_forward as fwd
from ops.executive_os.provider_incident_forward import ForwardRecoveryError
from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    EffectUnknownError,
    serve_connection,
)
from control_plane.executive_privileged_client import (
    validate_forward_status_response,
)
from tests.test_provider_incident_forward import (
    FORWARD_I,
    ORIGINAL_D,
    _MemoryConnection,
    assert_no_forward_effects,
    forward_args,
    forward_paths,
    run_forward,
)
from tests.test_provider_incident_forward import (
    forward_env,  # noqa: F401 - pytest fixture import
)
from tests.test_provider_incident_recovery import (
    ISSUER_REQUEST_ID,
    custody_root,  # noqa: F401 - pytest fixture import
    issue_incident,
    read_custody,
    receipt_digest,
    recovery,  # noqa: F401 - pytest fixture import
    rewrite_custody,
    state,  # noqa: F401 - pytest fixture import
)


_BLOCKED = "ops.executive_os.provider_incident_forward"


_REAL_IMPORT = builtins.__import__


def _no_forward_import(name, *args, **kwargs):
    if name == _BLOCKED:
        raise ImportError("injected unavailable dormant forward module")
    return _REAL_IMPORT(name, *args, **kwargs)


def _no_forward_import_strong(name, globals=None, locals=None, fromlist=(), level=0):
    # "from ops.executive_os import provider_incident_forward" reaches
    # __import__ with the package name and a fromlist tuple, so a faithful
    # unavailability injection must refuse that form too.
    if name == _BLOCKED or (
        name == "ops.executive_os"
        and fromlist
        and "provider_incident_forward" in tuple(fromlist)
    ):
        raise ImportError("injected unavailable dormant forward module")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


def _receipt(**changes):
    value = {
        "schema": broker_module.RECEIPT_SCHEMA,
        "request_id": FORWARD_I,
        "request_sha256": "0" * 64,
        "action": fwd.FORWARD_RECOVERY_ACTION,
        "effect_class": fwd.FORWARD_EFFECT_CLASS,
        "started_at": "2026-10-13T21:00:00Z",
        "finished_at": "2026-10-13T21:00:01Z",
        "exit_code": 0,
        "outcome": "SUCCEEDED",
        "release_sha": "a" * 40,
        "broker_version": "test",
        "stdout_bytes": 0,
        "stdout_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_excerpt": "",
        "stderr_bytes": 0,
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stderr_excerpt": "",
    }
    value.update(changes)
    return value


# ---------------------------------------------------------------------------
# 1. Uniform original-digest substitution can never satisfy the join.
# ---------------------------------------------------------------------------


def test_uniform_original_digest_cannot_replace_forward_digest(forward_env):
    s = forward_env
    run_forward(s)
    rp = fwd.reservation_path(s.fwd_broker.receipt_root)
    reservation = read_custody(rp)
    reservation["forward_request_sha256"] = ORIGINAL_D
    rewrite_custody(rp, reservation)
    cp = rec.RECOVERY_INCIDENT_COMMITMENT_PATH
    commitment = read_custody(cp)
    commitment["forward_recovery"]["forward_request_sha256"] = ORIGINAL_D
    commitment["forward_recovery"]["reservation_sha256"] = receipt_digest(rp)
    rewrite_custody(cp, commitment)
    tp = fwd.terminal_path(s.fwd_broker.receipt_root)
    terminal = read_custody(tp)
    terminal["request_sha256"] = ORIGINAL_D
    terminal["stdout_sha256"] = receipt_digest(cp)
    rewrite_custody(tp, terminal)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


def test_join_reconstructs_canonical_forward_request_from_reservation_source(
    forward_env,
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    joined = rec.validate_incident_issuance_join(grant, grant_sha256=digest)
    forward_digest = fwd.validate_forward_request(forward_args())[1]
    assert forward_digest != ORIGINAL_D
    assert joined["terminal"]["request_sha256"] == forward_digest
    # Substituting the outer evidence-file digest W anywhere F is claimed
    # refuses, because F is compared to the recomputed canonical preimage.
    rp = fwd.reservation_path(s.fwd_broker.receipt_root)
    reservation = read_custody(rp)
    reservation["forward_request_sha256"] = (
        "465c6b4a35cfbf9f1d31255c48ab11a13851a471ec5fb99baafa79600af2f7d4")
    rewrite_custody(rp, reservation)
    with pytest.raises(rec.RecoveryError):
        rec.validate_incident_issuance_join(grant, grant_sha256=digest)


# ---------------------------------------------------------------------------
# 2. Client-side closed forward response validation.
# ---------------------------------------------------------------------------


def test_forward_effect_response_validation_binds_request_digest_and_release():
    # Imported lazily: the closed forward-response validator is itself part of
    # the reviewed repair and is absent from the unchanged core.
    from control_plane.executive_privileged_client import (
        validate_forward_recovery_response,
    )

    request = forward_args()
    _validated, forward_digest = fwd.validate_forward_request(request)
    response = {
        "schema": broker_module.WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "replayed": False,
        "receipt": _receipt(request_sha256=forward_digest),
    }
    validated = validate_forward_recovery_response(
        response, request, expected_release_sha="a" * 40)
    assert validated["replayed"] is False
    assert validated["receipt"]["request_sha256"] == forward_digest
    # The original digest D is never accepted as F on the receipt.
    original_digest = json.loads(json.dumps(response))
    original_digest["receipt"]["request_sha256"] = ORIGINAL_D
    with pytest.raises(broker_module.BrokerTrustError):
        validate_forward_recovery_response(original_digest, request)
    # A release the caller did not expect refuses.
    other_release = json.loads(json.dumps(response))
    other_release["receipt"]["release_sha"] = "e" * 40
    with pytest.raises(broker_module.BrokerTrustError):
        validate_forward_recovery_response(
            other_release, request, expected_release_sha="a" * 40)
    # A non-success forward receipt refuses.
    failed = json.loads(json.dumps(response))
    failed["receipt"]["outcome"] = "FAILED"
    failed["receipt"]["exit_code"] = 1
    with pytest.raises(RuntimeError):
        validate_forward_recovery_response(failed, request)
    # Refusal envelopes pass through unchanged; no effect or retry authority.
    refusal = {
        "schema": broker_module.WIRE_RESPONSE_SCHEMA,
        "ok": False,
        "error": "FORWARD_REFUSED",
        "detail": "forward_policy_dormant",
    }
    assert validate_forward_recovery_response(refusal, request) == refusal
    # Ordinary validate_request cannot even validate this closed schema.
    with pytest.raises(Exception):
        validate_request(request)


def test_wire_forward_response_validates_against_the_exact_request(forward_env):
    from control_plane.executive_privileged_client import (
        validate_forward_recovery_response,
    )

    s = forward_env
    payload = (json.dumps(forward_args(), sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    connection = _MemoryConnection(payload)
    serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is True
    validated = validate_forward_recovery_response(response, forward_args())
    forward_digest = fwd.validate_forward_request(forward_args())[1]
    assert validated["receipt"]["request_sha256"] == forward_digest
    assert validated["receipt"]["action"] == fwd.FORWARD_RECOVERY_ACTION


def test_status_binds_embedded_terminal_to_envelope_and_expected_request(
    forward_env,
):
    s = forward_env
    run_forward(s)
    projection = s.fwd_broker.forward_status(
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I},
        peer_uid=501)
    wire = broker_module._wire_forward_status(projection)
    forward_digest = fwd.validate_forward_request(forward_args())[1]
    ok = validate_forward_status_response(
        wire, expected_forward_request_sha256=forward_digest)
    assert ok["forward"]["terminal"]["request_sha256"] == forward_digest
    wrong_forward_digest = json.loads(json.dumps(wire))
    wrong_forward_digest["forward"]["terminal"]["request_sha256"] = "9" * 64
    with pytest.raises(RuntimeError):
        validate_forward_status_response(
            wrong_forward_digest,
            expected_forward_request_sha256=forward_digest)
    # The release binding to the envelope is unconditional.
    drifted = json.loads(json.dumps(wire))
    drifted["installed_release_sha"] = "e" * 40
    with pytest.raises(RuntimeError):
        validate_forward_status_response(drifted)


def test_status_rejects_terminal_release_different_from_envelope(forward_env):
    s = forward_env
    run_forward(s)
    status = s.fwd_broker.forward_status(
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I},
        peer_uid=501)
    wire = broker_module._wire_forward_status(status)
    wire["forward"]["terminal"]["release_sha"] = "c" * 40
    with pytest.raises((RuntimeError, broker_module.BrokerTrustError)):
        validate_forward_status_response(wire)


def test_success_status_requires_trusted_forward_digest_context(forward_env):
    s = forward_env
    run_forward(s)
    status = s.fwd_broker.forward_status(
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I},
        peer_uid=501)
    wire = broker_module._wire_forward_status(status)
    for invalid_expected in (None, "", "a" * 63, True):
        with pytest.raises(RuntimeError, match="requires the expected request digest"):
            validate_forward_status_response(
                wire, expected_forward_request_sha256=invalid_expected)
    wire["forward"]["terminal"]["request_sha256"] = "a" * 64
    with pytest.raises(RuntimeError):
        validate_forward_status_response(wire)


# ---------------------------------------------------------------------------
# 3. No v1 route imports the optional forward module.
# ---------------------------------------------------------------------------


def test_ordinary_refusal_does_not_import_dormant_forward_module(
    forward_env, monkeypatch
):
    monkeypatch.setattr(builtins, "__import__", _no_forward_import)
    raw = {"schema": REQUEST_SCHEMA, "request_id": "ordinary-invalid-1",
           "action": "unsupported", "args": {}}
    connection = _MemoryConnection((json.dumps(raw) + "\n").encode())
    serve_connection(forward_env.fwd_broker, connection,
                     peer_resolver=lambda c: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is False and response["error"] == "REFUSED"
    assert_no_forward_effects(forward_env)


def test_v1_effect_dispatch_and_commitment_reading_import_no_forward_module(
    forward_env, monkeypatch
):
    s = forward_env
    broker, receipt = issue_incident(s, monkeypatch)
    assert receipt["outcome"] == "SUCCEEDED"
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    monkeypatch.setattr(builtins, "__import__", _no_forward_import_strong)
    commitment, _raw = rec.read_incident_commitment()
    assert commitment["schema_version"] == rec.INCIDENT_COMMITMENT_SCHEMA
    joined = rec.validate_incident_issuance_join(grant, grant_sha256=digest)
    assert joined["commitment_sha256"] == receipt_digest(
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    assert not broker.inflight_path(ISSUER_REQUEST_ID).exists()


def test_unavailable_forward_module_typed_refuses_forward_only_frames(
    forward_env, monkeypatch
):
    s = forward_env
    monkeypatch.setattr(builtins, "__import__", _no_forward_import_strong)
    for payload in (
        forward_args(),
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I},
    ):
        connection = _MemoryConnection(
            (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode())
        serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
        response = json.loads(bytes(connection.sent))
        assert response["ok"] is False
        assert response["error"] == "FORWARD_REFUSED"
    assert_no_forward_effects(s)


def test_unavailable_forward_module_typed_refuses_v2_commitment_reading(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    monkeypatch.setattr(builtins, "__import__", _no_forward_import_strong)
    with pytest.raises(rec.RecoveryError):
        rec.read_incident_commitment()
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


# ---------------------------------------------------------------------------
# 4. A vanished guard readback is typed effect-unknown, never a NoneType.
# ---------------------------------------------------------------------------


def test_missing_guard_readback_is_typed_effect_unknown_without_retry(
    forward_env, monkeypatch
):
    s = forward_env
    real = fwd._strict_forward_document

    def lose_guard(path):
        result = real(path)
        if Path(path).name.endswith(fwd.GUARD_SUFFIX):
            return None
        return result

    monkeypatch.setattr(fwd, "_strict_forward_document", lose_guard)
    with pytest.raises(EffectUnknownError, match="forward_guard_lost"):
        run_forward(s)
    paths = forward_paths(s)
    assert paths["reservation"].exists()
    assert paths["guard"].exists()
    assert not paths["terminal"].exists()
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    # No retry: the burned transition only refuses on the occupied slot.
    monkeypatch.setattr(fwd, "_strict_forward_document", real)
    with pytest.raises(ForwardRecoveryError, match="slot_occupied"):
        run_forward(s)


# ---------------------------------------------------------------------------
# 5. Existing-but-unreadable forward evidence refuses before any reservation.
# ---------------------------------------------------------------------------


def test_empty_forward_occupant_is_evidence_refusal_not_missing_producer(
    forward_env,
):
    path = fwd.reservation_path(forward_env.fwd_broker.receipt_root)
    path.write_bytes(b"")
    os.chmod(path, 0o600)
    with pytest.raises(ForwardRecoveryError):
        run_forward(forward_env)
    assert path.read_bytes() == b""
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()


def test_oversize_and_unreadable_parent_occupants_refuse_as_evidence(
    forward_env,
):
    s = forward_env
    oversized = fwd.terminal_path(s.fwd_broker.receipt_root)
    oversized.write_bytes(b"x" * (65 * 1024))
    os.chmod(oversized, 0o600)
    with pytest.raises(ForwardRecoveryError):
        run_forward(s)
    assert oversized.stat().st_size == 65 * 1024
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    os.chmod(oversized, 0o600)
    oversized.unlink()
    # A drifted forward-evidence parent refuses as unsafe custody, never as an
    # absent host-guard producer.
    broker_module._write_exclusive_json(fwd.guard_path(s.fwd_broker.receipt_root),
                                        {"schema_version": "x"})
    with pytest.raises((ForwardRecoveryError, broker_module.BrokerTrustError)):
        run_forward(s)
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()


# ---------------------------------------------------------------------------
# 6. Historical consumed evidence stays readable; live admission stays shut.
# ---------------------------------------------------------------------------


def test_historical_consumed_allocation_remains_readable_after_deactivation(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    rec.claim_or_refuse_allocation(
        rec.RECOVERY_ALLOCATION_PATH, grant=grant,
        grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH),
        predecessor_receipt_sha256=grant["evidence"]["readiness_receipt_sha256"])
    before = rec.RECOVERY_ALLOCATION_PATH.read_bytes()
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    assert rec.read_allocation()["consumed"] is True
    assert rec.RECOVERY_ALLOCATION_PATH.read_bytes() == before
    with pytest.raises(rec.RecoveryError, match="forward_policy_dormant"):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


def test_deactivated_policy_still_blocks_reclaim_and_never_refunds(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    predecessor = grant["evidence"]["readiness_receipt_sha256"]
    rec.claim_or_refuse_allocation(
        rec.RECOVERY_ALLOCATION_PATH, grant=grant, grant_sha256=digest,
        predecessor_receipt_sha256=predecessor)
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    with pytest.raises(rec.RecoveryError, match="already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=grant, grant_sha256=digest,
            predecessor_receipt_sha256=predecessor)
    assert rec.RECOVERY_ALLOCATION_PATH.exists()
    assert rec.read_allocation()["consumed"] is True


def test_fresh_allocation_revalidates_policy_after_prior_admission(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    rec.validate_incident_issuance_join(grant, grant_sha256=digest)
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    with pytest.raises(rec.RecoveryError, match="forward_policy_dormant"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=grant, grant_sha256=digest,
            predecessor_receipt_sha256=grant["evidence"]["readiness_receipt_sha256"])
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


def test_losing_exclusive_allocation_race_classifies_history_without_refund(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    original_write = rec.write_custody_document
    winner = {}

    def competing_create(path, payload):
        original_write(path, payload)
        winner["bytes"] = path.read_bytes()
        winner["inode"] = path.stat().st_ino
        monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
        return original_write(path, payload)

    monkeypatch.setattr(rec, "write_custody_document", competing_create)
    with pytest.raises(rec.RecoveryError, match="already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=grant,
            grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH),
            predecessor_receipt_sha256=grant["evidence"]["readiness_receipt_sha256"])
    assert rec.RECOVERY_ALLOCATION_PATH.read_bytes() == winner["bytes"]
    assert rec.RECOVERY_ALLOCATION_PATH.stat().st_ino == winner["inode"]
    assert rec.read_allocation()["consumed"] is True


def test_historical_verifier_is_private_and_matches_live_join_shape(
    forward_env, monkeypatch
):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    digest = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    live = rec.validate_incident_issuance_join(grant, grant_sha256=digest)
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    historical = rec._validate_incident_issuance_join_historical(
        grant, grant_sha256=digest)
    assert historical == live
    with pytest.raises(rec.RecoveryError, match="forward_policy_dormant"):
        rec.validate_incident_issuance_join(grant, grant_sha256=digest)


# ---------------------------------------------------------------------------
# 7. Closed forward status wire names original_status; ordinary is unchanged.
# ---------------------------------------------------------------------------


def test_forward_status_wire_uses_original_status_and_ordinary_is_unchanged(
    forward_env,
):
    s = forward_env
    run_forward(s)
    projection = s.fwd_broker.forward_status(
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I},
        peer_uid=501)
    wire = broker_module._wire_forward_status(projection)
    assert wire["original_status"] == "EFFECT_UNKNOWN"
    assert "status" not in wire
    ordinary = s.fwd_broker.query_status(
        {"schema": "mastermind.executive_privileged_action_status_request.v1",
         "request_id": FORWARD_I}, peer_uid=501)
    assert ordinary["status"] == "EFFECT_UNKNOWN"
    ordinary_wire = broker_module._wire_status(ordinary)
    assert ordinary_wire["status"] == "EFFECT_UNKNOWN"
    assert "original_status" not in ordinary_wire


# ---------------------------------------------------------------------------
# 8. The unused ordinary connection parameter is gone; forward keeps its own.
# ---------------------------------------------------------------------------


def test_closed_schema_constants_have_a_single_source_of_law():
    # The commitment schema is owned by the recovery module; the optional
    # forward module re-exports it, and the broker dispatch literals mirror
    # the forward wire schemas without importing them on any v1 path.
    assert fwd.COMMITMENT_V2_SCHEMA is rec.COMMITMENT_V2_SCHEMA
    assert broker_module.FORWARD_STATUS_REQUEST_SCHEMA == fwd.FORWARD_STATUS_SCHEMA
    assert broker_module.FORWARD_ACTION_REQUEST_SCHEMA == fwd.FORWARD_REQUEST_SCHEMA


def test_ordinary_outcome_handler_has_no_connection_parameter():
    ordinary = inspect.signature(
        broker_module.PrivilegedActionBroker._handle_outcome).parameters
    assert "connection" not in ordinary
    forward = inspect.signature(
        broker_module.PrivilegedActionBroker._handle_forward_outcome).parameters
    assert "connection" in forward
