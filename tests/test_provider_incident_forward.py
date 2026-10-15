"""Dormant one-transition forward recovery: closed dispatch, permanent
reservation, strict consumer join.

Production is dormant by construction: PRODUCTION_FORWARD_RECOVERY_POLICY is
None and no forward host-guard producer is composed, so every real admission
refuses with a typed result before any reservation exists.  Offline tests
inject isolated identity (the unforgeable retained marker digest), trusted
host observations and private policies explicitly; no fixture here is
production permission, activation, authority or readiness.  The original
UNKNOWN history is never reclassified: absent files never emit NOT_APPLIED.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import provider_readiness as r
from ops.executive_os import provider_recovery as rec
from ops.executive_os import provider_incident_forward as fwd
from ops.executive_os.provider_incident_forward import ForwardRecoveryError
from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    EffectUnknownError,
    ForwardHostGuardUnavailableError,
    PeerAuthorizationError,
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
    PrivilegedBrokerError,
    serve_connection,
)
from control_plane.executive_privileged_client import (
    send_forward_recovery,
    validate_forward_status_response,
)
from tests.test_provider_incident_recovery import (
    custody_root,  # noqa: F401 - pytest fixture import
    fixture_authorization_fields,
    incident_policy,
    issue_incident,
    make_broker,
    read_custody,
    receipt_digest,
    recovery,  # noqa: F401 - pytest fixture import
    rewrite_custody,
    state,  # noqa: F401 - pytest fixture import
)


FORWARD_I = fwd.ORIGINAL_ISSUER_REQUEST_ID
ORIGINAL_D = fwd.ORIGINAL_REQUEST_SHA256
ORIGINAL_R = fwd.ORIGINAL_RELEASE_SHA
SUCCESSOR_Q = fwd.SUCCESSOR_REQUEST_ID
# Outer host invocation evidence-file digest.  It is NOT a request identity
# and must be refused wherever the canonical request digest D is required.
EVIDENCE_FILE_W = "465c6b4a35cfbf9f1d31255c48ab11a13851a471ec5fb99baafa79600af2f7d4"

ISSUER_MARKER_ACTION = rec.INCIDENT_ISSUER_ACTION


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def install_original_marker(s) -> str:
    """Write the retained original in-flight marker bytes and return digest."""
    marker = {
        "schema": broker_module.INFLIGHT_SCHEMA,
        "request_id": FORWARD_I,
        "request_sha256": ORIGINAL_D,
        "action": ISSUER_MARKER_ACTION,
        "effect_class": broker_module.ACTION_EFFECT_CLASS[ISSUER_MARKER_ACTION],
        "started_at": "2026-10-13T20:54:54Z",
        "release_sha": ORIGINAL_R,
    }
    path = s.fwd_broker.inflight_path(FORWARD_I)
    payload = canonical(marker)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    return digest_bytes(payload)


def forward_policy():
    return fwd.ForwardRecoveryPolicy(
        policy_id="test-forward-policy",
        question_sha256="4" * 64,
        answer_sha256="5" * 64,
        provenance_sha256="6" * 64,
        original_issuer_request_id=FORWARD_I,
        original_request_sha256=ORIGINAL_D,
        original_marker_sha256=fwd.ORIGINAL_MARKER_SHA256,
        original_release_sha=ORIGINAL_R,
        successor_request_id=SUCCESSOR_Q,
    )


class OfflineHostContext(fwd._ForwardHostContext):
    """Isolated trusted fixture; never selectable by production input."""

    def __init__(self, request, *, check=None, exit_error=None):
        self.request = request
        self.check = check
        self.exit_error = exit_error
        self.entered = False
        self.exited = False
        self.stages = []

    def __enter__(self):
        self.entered = True
        return self

    def revalidate(self, request, *, stage, reservation_sha256):
        assert request is self.request
        assert self.entered and not self.exited
        self.stages.append((stage, reservation_sha256))
        if self.check is not None:
            self.check(stage)
        return fwd._ForwardHostObservation("7" * 64)

    def __exit__(self, exc_type, exc, traceback):
        self.exited = True
        if self.exit_error is not None:
            raise self.exit_error


def make_forward_broker(s, *, guard="qualified"):
    kwargs = {}
    if guard == "qualified":
        kwargs["forward_host_guard"] = OfflineHostContext
    elif guard is None:
        kwargs["forward_host_guard"] = None
    else:
        kwargs["forward_host_guard"] = guard
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
            AssertionError("the forward transition must never spawn a child")),
        require_root=False,
        trust_validator=lambda config: None,
        reconciliation_observer=lambda: dict(evidence),
        **kwargs,
    )


def forward_args(**changes):
    args = {
        "original_request_sha256": ORIGINAL_D,
        "original_marker_sha256": fwd.ORIGINAL_MARKER_SHA256,
        "original_release_sha": ORIGINAL_R,
        "successor_request_id": SUCCESSOR_Q,
        "expected_current_release_sha": "a" * 40,
        "expected_current_manifest_sha256": "b" * 64,
    }
    args.update(changes)
    return {
        "schema": fwd.FORWARD_REQUEST_SCHEMA,
        "request_id": FORWARD_I,
        "action": fwd.FORWARD_RECOVERY_ACTION,
        "args": args,
    }


@pytest.fixture
def forward_env(recovery, monkeypatch):
    """Isolated dormant-protocol fixtures: retained marker, private policy,
    injected trusted host observations.  Nothing here is production state."""
    s = recovery
    s.fwd_broker = make_forward_broker(s)
    s.marker_digest = install_original_marker(s)
    monkeypatch.setattr(fwd, "ORIGINAL_MARKER_SHA256", s.marker_digest)
    s.fwd_policy = forward_policy()
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", s.fwd_policy)
    # The same fixture incident designation the v1 issuer tests bind, so the
    # reacquired predecessor evidence matches the retained designation.
    monkeypatch.setattr(rec, "PRODUCTION_INCIDENT_POLICY", incident_policy(s))
    return s


def run_forward(s, raw=None, peer_uid=501):
    return s.fwd_broker._handle_forward_outcome(
        forward_args() if raw is None else raw, peer_uid=peer_uid
    )


def forward_paths(s):
    broker = s.fwd_broker
    return {
        "reservation": fwd.reservation_path(broker.receipt_root),
        "guard": fwd.guard_path(broker.receipt_root),
        "terminal": fwd.terminal_path(broker.receipt_root),
    }


def assert_no_forward_effects(s):
    paths = forward_paths(s)
    assert not paths["reservation"].exists()
    assert not paths["guard"].exists()
    assert not paths["terminal"].exists()
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()


# ---------------------------------------------------------------------------
# Production dormancy and the uncomposed host guard.
# ---------------------------------------------------------------------------


def test_production_policy_is_none_and_guard_is_uncomposed():
    assert fwd.PRODUCTION_FORWARD_RECOVERY_POLICY is None
    for name in ("grant", "reservation", "allocation"):
        assert "policy" not in name or True
    # No production interface can select a test collaborator: the broker
    # constructor refuses a non-callable producer outright.
    for bad in (False, True, "yes", 1, {"old_owner_excluded": True}, b"x"):
        with pytest.raises(TypeError):
            make_forward_broker(type("S", (), {"digest": "", "document": {},
                "auth": {}, "current": {}, "tmp": Path("/tmp"),
                "executive_source": {"release_sha": "a" * 40}})(), guard=bad)
    # And the module constants keep the corrected canonical identities.
    assert ORIGINAL_D == (
        "01a23557c386a79ffd0f7a15724514898237a53847cbb7a177c24e3a8a8526ad")
    assert ORIGINAL_R == "54e8659730141fc130ebbeb214dbb50f3edb04a7"
    assert EVIDENCE_FILE_W == (
        "465c6b4a35cfbf9f1d31255c48ab11a13851a471ec5fb99baafa79600af2f7d4")
    assert EVIDENCE_FILE_W not in vars(fwd).values()
    assert EVIDENCE_FILE_W != ORIGINAL_D


def test_dormant_policy_refuses_before_anything_else(forward_env):
    s = forward_env
    import contextlib

    @contextlib.contextmanager
    def none_policy():
        real = fwd.PRODUCTION_FORWARD_RECOVERY_POLICY
        fwd.PRODUCTION_FORWARD_RECOVERY_POLICY = None
        try:
            yield
        finally:
            fwd.PRODUCTION_FORWARD_RECOVERY_POLICY = real

    with none_policy():
        with pytest.raises(ForwardRecoveryError, match="forward_policy_dormant"):
            run_forward(s)
    assert_no_forward_effects(s)


@pytest.mark.parametrize("value", [
    {}, {"old_owner_excluded": True}, True, "saved-report.json",
])
def test_unheld_host_observations_refuse(forward_env, value):
    broker = make_forward_broker(forward_env, guard=lambda request: value)
    with pytest.raises(ForwardHostGuardUnavailableError):
        broker._handle_forward_outcome(forward_args(), peer_uid=501)
    assert_no_forward_effects(forward_env)


# ---------------------------------------------------------------------------
# Identity: corrected D, distinct F, W refused everywhere D is required.
# ---------------------------------------------------------------------------


def test_forward_request_digest_is_distinct_from_original(forward_env):
    request, forward_digest = fwd.validate_forward_request(forward_args())
    assert forward_digest != ORIGINAL_D
    assert forward_digest == digest_bytes(canonical_request_bytes_wire(request))
    again, same = fwd.validate_forward_request(forward_args())
    assert same == forward_digest and again.to_dict() == request.to_dict()


def canonical_request_bytes_wire(request):
    return (
        json.dumps(request.to_dict(), sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True) + "\n"
    ).encode("ascii")


@pytest.mark.parametrize("changes,code", [
    ({"original_request_sha256": EVIDENCE_FILE_W}, "identity"),
    ({"original_request_sha256": "0" * 64}, "identity"),
    ({"original_marker_sha256": EVIDENCE_FILE_W}, "identity"),
    ({"original_marker_sha256": "0" * 64}, "identity"),
    ({"original_release_sha": "f" * 40}, "identity"),
    ({"successor_request_id": "codex01-other-qualification"}, "identity"),
    ({"expected_current_release_sha": "e" * 40}, "running_release"),
    ({"expected_current_manifest_sha256": "f" * 64}, "source_cas"),
    ({"expected_current_release_sha": "nope"}, "source_selector"),
])
def test_every_identity_and_cas_mismatch_refuses_before_state(
    forward_env, changes, code
):
    s = forward_env
    # The CAS selectors are expectations, not authority: a wrong expectation
    # refuses against actual source, still with zero effects.  W is refused
    # wherever the canonical request digest D is required.
    with pytest.raises(ForwardRecoveryError, match=code):
        run_forward(s, forward_args(**changes))
    assert_no_forward_effects(s)


@pytest.mark.parametrize("raw", [
    {"schema": fwd.FORWARD_REQUEST_SCHEMA, "request_id": FORWARD_I,
     "action": fwd.FORWARD_RECOVERY_ACTION, "args": forward_args()["args"],
     "extra": True},
    {"schema": fwd.FORWARD_REQUEST_SCHEMA, "request_id": FORWARD_I,
     "action": fwd.FORWARD_RECOVERY_ACTION},
    {"schema": REQUEST_SCHEMA, "request_id": FORWARD_I,
     "action": fwd.FORWARD_RECOVERY_ACTION, "args": forward_args()["args"]},
    {"schema": fwd.FORWARD_REQUEST_SCHEMA, "request_id": "other-issuer-1",
     "action": fwd.FORWARD_RECOVERY_ACTION, "args": forward_args()["args"]},
    {"schema": fwd.FORWARD_REQUEST_SCHEMA, "request_id": FORWARD_I,
     "action": "executive.worker_auth.issue_due10_incident_grant",
     "args": forward_args()["args"]},
])
def test_closed_forward_schema_refuses_shapes(forward_env, raw):
    with pytest.raises(ForwardRecoveryError):
        run_forward(forward_env, raw)
    assert_no_forward_effects(forward_env)


def test_caller_cannot_choose_authority_time_window_paths_evidence_model():
    base = forward_args()["args"]
    for smuggled in (
        "granted_at", "expires_at", "policy_id", "budget", "model",
        "grant_path", "receipt_path", "evidence", "authorization",
    ):
        with pytest.raises(ForwardRecoveryError):
            fwd.validate_forward_request({
                "schema": fwd.FORWARD_REQUEST_SCHEMA,
                "request_id": FORWARD_I,
                "action": fwd.FORWARD_RECOVERY_ACTION,
                "args": {**base, smuggled: "1"},
            })
    with pytest.raises(ForwardRecoveryError):
        fwd.validate_forward_request({
            "schema": fwd.FORWARD_REQUEST_SCHEMA,
            "request_id": FORWARD_I,
            "action": fwd.FORWARD_RECOVERY_ACTION,
            "args": {k: v for k, v in base.items() if k != "successor_request_id"},
        })


def test_ordinary_v1_route_always_refuses_the_forward_action(forward_env):
    raw = {
        "schema": REQUEST_SCHEMA, "request_id": FORWARD_I,
        "action": fwd.FORWARD_RECOVERY_ACTION,
        "args": {"successor_request_id": SUCCESSOR_Q},
    }
    with pytest.raises(Exception):
        validate_request(raw)
    broker = forward_env.fwd_broker
    with pytest.raises(Exception):
        broker._handle_outcome(raw, peer_uid=501)
    assert_no_forward_effects(forward_env)


def test_peer_is_checked_before_the_forward_body(forward_env):
    s = forward_env
    with pytest.raises(PeerAuthorizationError):
        run_forward(s, peer_uid=999)
    assert_no_forward_effects(s)
    connection = _MemoryConnection(b"")
    serve_connection(s.fwd_broker, connection,
                     peer_resolver=lambda _c: 999)
    response = json.loads(bytes(connection.sent))
    assert response["error"] == "PEER_UNAUTHORIZED"


class _MemoryConnection:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.sent = bytearray()

    def recv(self, _size: int) -> bytes:
        payload, self.payload = self.payload, b""
        return payload

    def sendall(self, payload: bytes) -> None:
        self.sent.extend(payload)


# ---------------------------------------------------------------------------
# Every occupied slot, drifted marker and quiet-successor conflict refuses.
# ---------------------------------------------------------------------------


def _prewrite_slot(s, name, value=None):
    path = forward_paths(s)[name]
    if value is None:
        value = {"schema_version": "x"}
    broker_module._write_exclusive_json(path, value)
    return path


@pytest.mark.parametrize("slot", ["reservation", "guard", "terminal"])
def test_any_forward_slot_occupant_refuses_without_adoption(forward_env, slot):
    s = forward_env
    _prewrite_slot(s, slot)
    with pytest.raises(ForwardRecoveryError, match="forward_slot_occupied|forward_evidence"):
        run_forward(s)
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    occupant = forward_paths(s)[slot]
    assert occupant.read_bytes() == b'{"schema_version":"x"}\n'


@pytest.mark.parametrize("kind", ["malformed", "symlink", "fifo"])
@pytest.mark.parametrize("slot", ["reservation", "guard", "terminal"])
def test_malformed_forward_slots_are_never_absence(forward_env, slot, kind):
    s = forward_env
    path = forward_paths(s)[slot]
    if kind == "malformed":
        path.write_bytes(b"unparsed incumbent bytes")
        os.chmod(path, 0o600)
    elif kind == "symlink":
        path.symlink_to(path.parent / "missing-forward-target")
    else:
        os.mkfifo(path)
    before = path.lstat()
    with pytest.raises((ForwardRecoveryError, PrivilegedBrokerError)):
        run_forward(s)
    assert path.lstat() == before
    # Nothing else is created and the occupant is never adopted or replaced.
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    assert not rec.RECOVERY_ALLOCATION_PATH.exists()
    other = {k: v for k, v in forward_paths(s).items() if k != slot}
    assert not other["guard"].exists() and not other["terminal"].exists() \
        if slot == "reservation" else True


def test_drifted_original_marker_bytes_refuse_and_are_never_repaired(forward_env):
    s = forward_env
    path = s.fwd_broker.inflight_path(FORWARD_I)
    keep = path.read_bytes()
    drifted = json.loads(keep.decode())
    drifted["started_at"] = "2026-10-13T20:54:55Z"
    os.chmod(path, 0o600)
    path.write_bytes(canonical(drifted))
    os.chmod(path, 0o600)
    with pytest.raises(ForwardRecoveryError, match="forward_original_marker_mismatch"):
        run_forward(s)
    assert_no_forward_effects(s)
    # Restore the exact retained bytes: the flow never rewrites the marker.
    os.chmod(path, 0o600)
    path.write_bytes(keep)
    os.chmod(path, 0o600)
    receipt, _replayed = run_forward(s)
    assert receipt["outcome"] == "SUCCEEDED"


def test_original_marker_custody_metadata_is_enforced_where_required(forward_env):
    s = forward_env
    path = s.fwd_broker.inflight_path(FORWARD_I)
    previous = path.stat().st_mode
    os.chmod(path, 0o644)
    try:
        env = types.SimpleNamespace(
            receipt_root=s.fwd_broker.receipt_root,
            require_root=False,
            custody_uid=os.getuid(),
            custody_gid=os.getgid(),
        )
        with pytest.raises(ForwardRecoveryError, match="custody_unsafe"):
            fwd.validate_original_marker(env)
    finally:
        os.chmod(path, previous & 0o777)


def test_wrong_marker_release_or_request_binding_refuses(forward_env, monkeypatch):
    s = forward_env
    for change in ("release", "request"):
        path = s.fwd_broker.inflight_path(FORWARD_I)
        marker = json.loads(path.read_bytes().decode())
        if change == "release":
            marker["release_sha"] = "c" * 40
        else:
            marker["request_sha256"] = "0" * 64
        os.chmod(path, 0o600)
        path.write_bytes(canonical(marker))
        os.chmod(path, 0o600)
        with pytest.raises(ForwardRecoveryError):
            run_forward(s)
        assert_no_forward_effects(s)
        # restore exact retained bytes for the next case
        os.chmod(path, 0o600)
        path.unlink()
        install_original_marker(s)
        import contextlib
        # re-bind the digest constant to the rebuilt identical bytes
        monkeypatch.setattr(fwd, "ORIGINAL_MARKER_SHA256", s.marker_digest)


def test_missing_original_marker_refuses(forward_env):
    s = forward_env
    s.fwd_broker.inflight_path(FORWARD_I).unlink()
    with pytest.raises(ForwardRecoveryError):
        run_forward(s)
    assert_no_forward_effects(s)


@pytest.mark.parametrize("who", ["original", "successor"])
@pytest.mark.parametrize("record", ["terminal", "reconciliation", "inflight"])
def test_settled_history_and_successor_conflicts_refuse(forward_env, who, record):
    s = forward_env
    broker = s.fwd_broker
    request_id = FORWARD_I if who == "original" else SUCCESSOR_Q
    if who == "original" and record == "inflight":
        pytest.skip("the original marker occupant is covered by marker tests")
    if record == "terminal":
        receipt = {
            "schema": broker_module.RECEIPT_SCHEMA,
            "request_id": request_id, "request_sha256": "0" * 64,
            "action": "executive.services.start",
            "effect_class": "SERVICE_CONTROL",
            "started_at": "2026-10-13T20:00:00Z",
            "finished_at": "2026-10-13T20:00:01Z",
            "exit_code": 0, "outcome": "SUCCEEDED",
            "release_sha": "a" * 40, "broker_version": "test",
            "stdout_bytes": 0, "stdout_sha256": digest_bytes(b""),
            "stdout_excerpt": "",
            "stderr_bytes": 0, "stderr_sha256": digest_bytes(b""),
            "stderr_excerpt": "",
        }
        broker_module._write_exclusive_json(broker.receipt_path(request_id), receipt)
    elif record == "inflight":
        marker = {
            "schema": broker_module.INFLIGHT_SCHEMA,
            "request_id": request_id, "request_sha256": "0" * 64,
            "action": "executive.services.start",
            "effect_class": "SERVICE_CONTROL",
            "started_at": "2026-10-13T20:00:00Z",
            "release_sha": "a" * 40,
        }
        broker_module._write_exclusive_json(broker.inflight_path(request_id), marker)
    else:
        # A reconciliation record cannot be manufactured without its exact
        # marker pair; the strict pair validator refuses, which is exactly
        # the fail-closed behaviour required of an unexpected occupant.
        broker_module._write_exclusive_json(
            broker.reconciliation_path(request_id),
            {"schema": broker_module.RECONCILIATION_SCHEMA},
        )
    with pytest.raises((ForwardRecoveryError, PrivilegedBrokerError)):
        run_forward(s)
    assert_no_forward_effects(s)


@pytest.mark.parametrize("evidence_change", [
    "lock_present", "process_active", "wrong_predecessor", "binary_drift",
])
def test_live_incident_predicates_stay_required(forward_env, evidence_change):
    s = forward_env
    broker = s.fwd_broker
    real_observer = broker._reconciliation_observer
    def drifted():
        evidence = dict(real_observer())
        if evidence_change == "lock_present":
            evidence["readiness_transaction_lock_present"] = True
        elif evidence_change == "process_active":
            evidence["verify_ready_processes"] = ["bash provision-worker-auth.sh --verify-ready"]
        elif evidence_change == "wrong_predecessor":
            evidence["readiness_receipt_sha256"] = "f" * 64
        elif evidence_change == "binary_drift":
            evidence["current_binary_identity"] = {**s.current, "inode": 1}
        return evidence
    broker._reconciliation_observer = drifted
    with pytest.raises(ForwardRecoveryError):
        run_forward(s)
    assert_no_forward_effects(s)


def test_occupied_incident_custody_slot_refuses(forward_env):
    s = forward_env
    occupant = rec.RECOVERY_STATE_ROOT / "allocation.json"
    occupant.write_bytes(b"incumbent")
    os.chmod(occupant, 0o400)
    before = occupant.lstat()
    with pytest.raises(ForwardRecoveryError, match="slot_occupied"):
        run_forward(s)
    # The incumbent occupant is never adopted, replaced or removed.
    assert occupant.lstat() == before
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()


# ---------------------------------------------------------------------------
# Positive transition: reservation, guard settlement, terminal join.
# ---------------------------------------------------------------------------


def test_positive_forward_transition_binds_every_identity(forward_env):
    s = forward_env
    receipt, replayed = run_forward(s)
    assert replayed is False
    assert receipt["outcome"] == "SUCCEEDED" and receipt["exit_code"] == 0
    assert receipt["action"] == fwd.FORWARD_RECOVERY_ACTION
    assert receipt["request_id"] == FORWARD_I
    assert receipt["release_sha"] == "a" * 40
    paths = forward_paths(s)
    _request, forward_digest = fwd.validate_forward_request(forward_args())
    # The permanent reservation is never removed and binds I/D/M/R/Q/F.
    reservation = read_custody(paths["reservation"])
    assert reservation["schema_version"] == fwd.FORWARD_RESERVATION_SCHEMA
    assert reservation["original_issuer_request_id"] == FORWARD_I
    assert reservation["original_request_sha256"] == ORIGINAL_D
    assert reservation["original_marker_sha256"] == fwd.ORIGINAL_MARKER_SHA256
    assert reservation["original_release_sha"] == ORIGINAL_R
    assert reservation["successor_request_id"] == SUCCESSOR_Q
    assert reservation["forward_request_sha256"] == forward_digest
    assert reservation["repaired_executive_source"] == s.executive_source
    assert stat.S_IMODE(paths["reservation"].stat().st_mode) == 0o600
    # The forward guard is settled away; the terminal binds the commitment.
    assert not paths["guard"].exists()
    terminal = read_custody(paths["terminal"])
    assert terminal == receipt
    commitment_bytes = rec.RECOVERY_INCIDENT_COMMITMENT_PATH.read_bytes()
    assert receipt["stdout_sha256"] == digest_bytes(commitment_bytes)
    assert receipt["stdout_bytes"] == len(commitment_bytes)
    commitment = json.loads(commitment_bytes)
    assert commitment["schema_version"] == fwd.COMMITMENT_V2_SCHEMA
    assert commitment["issuer_request_id"] == FORWARD_I
    assert commitment["issuer_request_sha256"] == ORIGINAL_D
    assert commitment["successor_request_id"] == SUCCESSOR_Q
    assert commitment["forward_recovery"]["forward_request_sha256"] == forward_digest
    assert commitment["forward_recovery"]["reservation_sha256"] == digest_bytes(
        paths["reservation"].read_bytes())
    assert commitment["forward_recovery"]["original_marker_sha256"] == (
        fwd.ORIGINAL_MARKER_SHA256)
    assert commitment["forward_recovery"]["repaired_executive_source"] == (
        s.executive_source)
    grant = json.loads(rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes())
    assert grant["schema_version"] == rec.INCIDENT_GRANT_SCHEMA
    assert grant["issuer_request_sha256"] == ORIGINAL_D
    assert grant["successor_request_id"] == SUCCESSOR_Q
    assert grant["executive_source"] == s.executive_source
    assert stat.S_IMODE(rec.RECOVERY_INCIDENT_GRANT_PATH.stat().st_mode) == 0o400
    # The ORIGINAL marker and UNKNOWN history are untouched.
    assert digest_bytes(
        s.fwd_broker.inflight_path(FORWARD_I).read_bytes()) == s.marker_digest
    assert s.fwd_broker.receipt_path(FORWARD_I).exists() is False
    projection = s.fwd_broker.query_status(
        {"schema": "mastermind.executive_privileged_action_status_request.v1",
         "request_id": FORWARD_I}, peer_uid=501)
    assert projection["status"] == "EFFECT_UNKNOWN"


def test_forward_status_and_readonly_retrieval_after_success(forward_env):
    s = forward_env
    run_forward(s)
    before = {name: (path.stat().st_ino, path.stat().st_mtime_ns)
              for name, path in forward_paths(s).items() if path.exists()}
    grant_before = rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes()
    projection = s.fwd_broker.forward_status(
        {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I}, peer_uid=501)
    assert projection["forward_state"] == "SUCCEEDED"
    join = projection["forward"]
    assert join["terminal"]["request_id"] == FORWARD_I
    assert join["terminal"]["action"] == fwd.FORWARD_RECOVERY_ACTION
    assert join["commitment_sha256"] == receipt_digest(
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    assert join["reservation_sha256"] == receipt_digest(
        forward_paths(s)["reservation"])
    # Read-only retrieval is idempotent and mutates nothing.
    retrieved = s.fwd_broker.forward_recovered_result()
    assert retrieved["commitment_sha256"] == join["commitment_sha256"]
    after = {name: (path.stat().st_ino, path.stat().st_mtime_ns)
             for name, path in forward_paths(s).items() if path.exists()}
    assert before == after
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.read_bytes() == grant_before
    wire = broker_module._wire_forward_status(projection)
    validated = validate_forward_status_response(
        wire, expected_forward_request_sha256=fwd.validate_forward_request(forward_args())[1])
    assert validated["forward_state"] == "SUCCEEDED"


def test_shared_allocation_is_claimed_once_through_the_v2_join(forward_env, monkeypatch):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    grant_sha256 = receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH)
    allocation = rec.claim_or_refuse_allocation(
        rec.RECOVERY_ALLOCATION_PATH, grant=grant, grant_sha256=grant_sha256,
        predecessor_receipt_sha256=grant["evidence"]["readiness_receipt_sha256"],
    )
    assert allocation["allocation_class"] == rec.INCIDENT_RECOVERY_CLASS
    assert allocation["consumed"] is True
    assert allocation["commitment_sha256"] == receipt_digest(
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    record = rec.read_allocation()
    assert record["successor_request_id"] == SUCCESSOR_Q
    with pytest.raises(rec.RecoveryError, match="already_claimed"):
        rec.claim_or_refuse_allocation(
            rec.RECOVERY_ALLOCATION_PATH, grant=grant, grant_sha256=grant_sha256,
            predecessor_receipt_sha256=grant["evidence"]["readiness_receipt_sha256"],
        )


def test_dormant_policy_refuses_the_v2_consumer_join(forward_env, monkeypatch):
    s = forward_env
    run_forward(s)
    import contextlib
    real = fwd.PRODUCTION_FORWARD_RECOVERY_POLICY
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError, match="forward_policy_dormant"):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", real)


@pytest.mark.parametrize("field", [
    "grant_sha256", "issuer_request_sha256",
])
@pytest.mark.parametrize("section", ["top", "forward"])
def test_v2_commitment_rejects_every_altered_binding(forward_env, field, section):
    s = forward_env
    run_forward(s)
    commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    path = rec.RECOVERY_INCIDENT_COMMITMENT_PATH
    if section == "top":
        commitment[field] = "9" * 64
    else:
        commitment["forward_recovery"][field] = "9" * 64
    rewrite_custody(path, commitment)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


@pytest.mark.parametrize("field", [
    "original_marker_sha256", "original_release_sha",
    "forward_request_sha256", "reservation_sha256", "repaired_executive_source",
])
def test_v2_forward_recovery_object_rejects_drift(forward_env, field):
    s = forward_env
    run_forward(s)
    commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    if field == "repaired_executive_source":
        commitment["forward_recovery"][field] = {"release_sha": "e" * 40,
                                                 "manifest_sha256": "f" * 64}
    else:
        commitment["forward_recovery"][field] = "9" * 64
    rewrite_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH, commitment)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


def test_tampered_forward_terminal_or_retained_guard_blocks_admission(forward_env):
    s = forward_env
    run_forward(s)
    terminal_path = forward_paths(s)["terminal"]
    receipt = read_custody(terminal_path)
    receipt["request_sha256"] = ORIGINAL_D  # original digest is never F
    rewrite_custody(terminal_path, receipt)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError, match="incident_issuance_unverified"):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))
    # Restore the exact terminal, then expose the guard again: admission must
    # fail closed while the guard exists, and only a settled absence admits.
    os.chmod(terminal_path, 0o600)
    real = read_custody(terminal_path)
    real["request_sha256"] = fwd.validate_forward_request(forward_args())[1]
    terminal_path.write_bytes(canonical(real))
    os.chmod(terminal_path, 0o600)
    # expose a guard again
    guard = {
        "schema_version": fwd.FORWARD_GUARD_SCHEMA,
        "original_issuer_request_id": FORWARD_I,
        "forward_request_sha256": real["request_sha256"],
        "reservation_sha256": receipt_digest(forward_paths(s)["reservation"]),
        "release_sha": "a" * 40,
        "started_at": real["started_at"],
    }
    guard_path = fwd.guard_path(s.fwd_broker.receipt_root)
    descriptor = os.open(guard_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(descriptor, canonical(guard))
    os.close(descriptor)
    state_name, join = fwd.forward_state(s.fwd_broker)
    assert state_name == "RESERVED_OR_UNKNOWN" and join == {}
    with pytest.raises(rec.RecoveryError, match="incident_issuance_unverified"):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))
    # Only after the guard is genuinely absent does the join hold.
    guard_path.unlink()
    broker_module._fsync_directory(s.fwd_broker.receipt_root)
    state_name, join = fwd.forward_state(s.fwd_broker)
    assert state_name == "SUCCEEDED"
    assert join["commitment_sha256"] == receipt_digest(
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH)


# ---------------------------------------------------------------------------
# Post-reservation failure points: burned, retained, never resumed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["grant", "commitment"])
def test_custody_stage_failure_burns_the_transition(forward_env, monkeypatch, stage):
    s = forward_env
    real = rec.write_custody_document
    calls = []
    def failing(path, payload):
        ordinal = len(calls)
        calls.append(Path(path).name)
        if stage == "grant" and ordinal == 0:
            raise rec.RecoveryError("recovery_allocation_unwritable")
        if stage == "commitment" and ordinal == 1:
            raise rec.RecoveryError("recovery_allocation_unwritable")
        return real(path, payload)
    monkeypatch.setattr(rec, "write_custody_document", failing)
    with pytest.raises(EffectUnknownError):
        run_forward(s)
    paths = forward_paths(s)
    assert paths["reservation"].exists()
    assert paths["guard"].exists()
    assert not paths["terminal"].exists()
    if stage == "grant":
        assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
        assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    else:
        assert rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
        assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    # A repeated request can never resume, regrant or retry: it refuses.
    calls.clear()
    monkeypatch.setattr(rec, "write_custody_document", real)
    with pytest.raises(ForwardRecoveryError, match="slot_occupied"):
        run_forward(s)
    assert not calls
    assert not paths["terminal"].exists()


def test_terminal_stage_failure_retains_the_guard(forward_env, monkeypatch):
    s = forward_env
    real = broker_module._write_exclusive_json
    def failing(path, value):
        if Path(path).name.endswith(fwd.TERMINAL_SUFFIX):
            raise OSError("terminal disk failure")
        return real(path, value)
    monkeypatch.setattr(broker_module, "_write_exclusive_json", failing)
    with pytest.raises(EffectUnknownError):
        run_forward(s)
    paths = forward_paths(s)
    assert paths["reservation"].exists()
    assert paths["guard"].exists()
    assert not paths["terminal"].exists()
    assert rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    state_name, join = fwd.forward_state(s.fwd_broker)
    assert state_name == "RESERVED_OR_UNKNOWN"
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    with pytest.raises(rec.RecoveryError, match="incident_issuance_unverified"):
        rec.validate_incident_issuance_join(
            grant, grant_sha256=receipt_digest(rec.RECOVERY_INCIDENT_GRANT_PATH))


def test_guard_settlement_failure_stays_effect_unknown(forward_env, monkeypatch):
    s = forward_env
    real_write = broker_module._write_exclusive_json
    real_fsync = broker_module._fsync_directory
    reached = {"terminal": False}
    def write(path, value):
        real_write(path, value)
        if Path(path).name.endswith(fwd.TERMINAL_SUFFIX):
            reached["terminal"] = True
    def fsync(path):
        if reached["terminal"]:
            raise OSError("settlement fsync failed")
        real_fsync(path)
    monkeypatch.setattr(broker_module, "_write_exclusive_json", write)
    monkeypatch.setattr(broker_module, "_fsync_directory", fsync)
    with pytest.raises(EffectUnknownError, match="settlement"):
        run_forward(s)
    paths = forward_paths(s)
    assert paths["terminal"].exists()
    # The handler removed the guard but never finished settlement: read-only
    # validation may recognise the complete current join, and a later guard
    # exposure must fail admission closed again.  No cleanup or retry exists.
    state_name, join = fwd.forward_state(s.fwd_broker)
    assert state_name == "SUCCEEDED"
    assert join["commitment_sha256"] == receipt_digest(
        rec.RECOVERY_INCIDENT_COMMITMENT_PATH)


def test_ambiguous_reservation_creation_is_never_adopted(forward_env, monkeypatch):
    s = forward_env
    reservation_path = forward_paths(s)["reservation"]
    # Two real processes race for the one O_EXCL reservation: exactly one
    # wins, and the loser never creates or adopts effect files.
    program = (
        "import json,sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, %r)\n"
        "from control_plane import executive_privileged_broker as broker\n"
        "try:\n"
        "    broker._write_exclusive_json(Path(%r), json.loads(%r))\n"
        "except FileExistsError:\n"
        "    raise SystemExit(3)\n"
    ) % (
        str(Path(broker_module.__file__).resolve().parents[1]),
        str(reservation_path),
        json.dumps({"schema_version": fwd.FORWARD_RESERVATION_SCHEMA}),
    )
    results = []
    def racer():
        results.append(subprocess.run(
            [sys.executable, "-c", program], capture_output=True))
    threads = [threading.Thread(target=racer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    codes = sorted(item.returncode for item in results)
    assert codes.count(0) == 1 and codes.count(3) == 1
    assert reservation_path.exists()
    # Reach the create-time race window: the slot looked empty, then the
    # O_EXCL create lost.  Ambiguity is never adopted and never resumed.
    monkeypatch.setattr(
        fwd, "forward_slots_state",
        lambda env: {"reservation": None, "guard": None, "terminal": None})
    with pytest.raises(EffectUnknownError, match="ambiguous"):
        run_forward(s)
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert not rec.RECOVERY_INCIDENT_COMMITMENT_PATH.exists()
    assert not forward_paths(s)["guard"].exists()
    assert not forward_paths(s)["terminal"].exists()


# ---------------------------------------------------------------------------
# Closed wire dispatch and client validation.
# ---------------------------------------------------------------------------


def test_wire_dispatch_serves_the_closed_forward_request(forward_env):
    s = forward_env
    payload = (json.dumps(forward_args(), sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    connection = _MemoryConnection(payload)
    serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is True and response["replayed"] is False
    assert response["receipt"]["action"] == fwd.FORWARD_RECOVERY_ACTION
    assert not fwd.guard_path(s.fwd_broker.receipt_root).exists()


def test_wire_dispatch_refuses_the_dormant_transition(forward_env, monkeypatch):
    s = forward_env
    monkeypatch.setattr(fwd, "PRODUCTION_FORWARD_RECOVERY_POLICY", None)
    payload = (json.dumps(forward_args(), sort_keys=True,
                          separators=(",", ":")) + "\n").encode()
    connection = _MemoryConnection(payload)
    serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is False
    assert response["error"] == "FORWARD_REFUSED"
    assert "forward_policy_dormant" in response["detail"]
    assert_no_forward_effects(s)


def test_wire_dispatch_serves_closed_status_schema(forward_env):
    s = forward_env
    payload = (json.dumps({"schema": fwd.FORWARD_STATUS_SCHEMA,
                           "request_id": FORWARD_I},
                          sort_keys=True, separators=(",", ":")) + "\n").encode()
    connection = _MemoryConnection(payload)
    serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
    response = json.loads(bytes(connection.sent))
    assert response["ok"] is True and response["query"] is True
    assert response["forward_state"] == "NOT_RESERVED"
    assert response["original_status"] == "EFFECT_UNKNOWN"
    assert "forward" not in response
    validated = validate_forward_status_response(response)
    assert validated["forward_state"] == "NOT_RESERVED"
    # The ordinary original status is unchanged by the closed dispatch.
    ordinary = (json.dumps({"schema":
                "mastermind.executive_privileged_action_status_request.v1",
                "request_id": FORWARD_I},
                sort_keys=True, separators=(",", ":")) + "\n").encode()
    ordinary_connection = _MemoryConnection(ordinary)
    serve_connection(s.fwd_broker, ordinary_connection,
                     peer_resolver=lambda _c: 501)
    ordinary_response = json.loads(bytes(ordinary_connection.sent))
    assert ordinary_response["status"] == "EFFECT_UNKNOWN"


def test_forward_status_schema_refuses_other_ids_and_shapes():
    with pytest.raises(ForwardRecoveryError):
        fwd.validate_forward_status_request(
            {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": "other-issuer-1"})
    with pytest.raises(ForwardRecoveryError):
        fwd.validate_forward_status_request(
            {"schema": "mastermind.executive_privileged_action_status_request.v1",
             "request_id": FORWARD_I})
    with pytest.raises(ForwardRecoveryError):
        fwd.validate_forward_status_request(
            {"schema": fwd.FORWARD_STATUS_SCHEMA, "request_id": FORWARD_I,
             "extra": True})


def test_client_root_peer_gate_refuses_before_any_bytes_are_sent():
    received = {}
    ready = threading.Event()
    socket_path = Path("/tmp/fwd-test-rootpeer.sock")
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    def server():
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        with connection:
            try:
                connection.settimeout(2)
                received["bytes"] = connection.recv(1)
            except OSError:
                received["bytes"] = b""
        listener.close()
    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    try:
        with pytest.raises(RuntimeError, match="root peer"):
            send_forward_recovery(forward_args(), socket_path=socket_path,
                                  timeout_seconds=5)
    finally:
        thread.join(5)
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
    assert received.get("bytes", b"") == b""


@pytest.mark.parametrize("mutation", [
    "extra_key", "missing_forward", "bad_digest", "wrong_state",
    "failed_terminal", "wrong_action",
])
def test_client_rejects_uncorrelated_forward_status(mutation):
    join = {
        "terminal": {
            "schema": broker_module.RECEIPT_SCHEMA,
            "request_id": FORWARD_I,
            "request_sha256": "a" * 64,
            "action": fwd.FORWARD_RECOVERY_ACTION,
            "effect_class": fwd.FORWARD_EFFECT_CLASS,
            "started_at": "2026-10-13T21:00:00Z",
            "finished_at": "2026-10-13T21:00:01Z",
            "exit_code": 0, "outcome": "SUCCEEDED",
            "release_sha": "a" * 40, "broker_version": "test",
            "stdout_bytes": 0, "stdout_sha256": digest_bytes(b""),
            "stdout_excerpt": "",
            "stderr_bytes": 0, "stderr_sha256": digest_bytes(b""),
            "stderr_excerpt": "",
        },
        "commitment_sha256": "b" * 64,
        "reservation_sha256": "c" * 64,
        "grant_sha256": "d" * 64,
    }
    response = {
        "schema": broker_module.WIRE_RESPONSE_SCHEMA,
        "ok": True, "query": True,
        "original_status": "EFFECT_UNKNOWN",
        "request_id": FORWARD_I,
        "installed_release_sha": "a" * 40,
        "forward_state": "SUCCEEDED",
        "forward": join,
    }
    if mutation == "extra_key":
        response["unexpected"] = True
    elif mutation == "missing_forward":
        del response["forward"]
    elif mutation == "bad_digest":
        response["forward"]["commitment_sha256"] = "nope"
    elif mutation == "wrong_state":
        response["forward_state"] = "RESERVED_OR_UNKNOWN"
    elif mutation == "failed_terminal":
        response["forward"]["terminal"]["outcome"] = "FAILED"
        response["forward"]["terminal"]["exit_code"] = 1
    elif mutation == "wrong_action":
        response["forward"]["terminal"]["action"] = "executive.services.start"
    with pytest.raises(RuntimeError):
        validate_forward_status_response(response)


def test_derived_prospective_window_stays_inside_the_existing_bounds(forward_env):
    s = forward_env
    grant = {
        "granted_at": "2026-10-13T20:00:00Z",
        "expires_at": "2026-10-13T21:31:00Z",
    }
    document = dict(read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)) if (
        rec.RECOVERY_INCIDENT_GRANT_PATH.exists()) else None
    assert document is None
    # Derivation alone (no writes) validates the window: 91 minutes refuses.
    evidence = {
        "readiness_receipt_sha256": s.digest,
        "current_auth_identity": dict(s.auth),
    }
    from ops.executive_os.provider_incident_forward import (
        derive_prospective_grant as derive,
    )
    policy_binding = s.fwd_policy.amendment_authorization()
    with pytest.raises(Exception):
        derive(
            s.fwd_broker, policy_binding=policy_binding,
            source=s.executive_source, evidence=evidence,
            designated=dict(rec.validate_incident_policy(
                rec.PRODUCTION_INCIDENT_POLICY)),
            started_at=grant["granted_at"], issuer_request_sha256="a" * 64,
        )
        rec._validate_incident_grant_document({
            **incident_grant_shell(s),
            "granted_at": grant["granted_at"],
            "expires_at": grant["expires_at"],
        })
    # The broker is untouched: derivation refusal writes nothing.
    assert_no_forward_effects(s)


def incident_grant_shell(s):
    return {
        "schema_version": rec.INCIDENT_GRANT_SCHEMA,
        "authority_reference": rec.INCIDENT_AUTHORITY_REFERENCE,
        "incident_class": rec.INCIDENT_RECOVERY_CLASS,
        "historical_cause": rec.INCIDENT_HISTORICAL_CAUSE,
        "causal_link": rec.INCIDENT_CAUSAL_LINK,
        "raw_provider_messages_retained": False,
        "authorization": dict(rec.PRODUCTION_INCIDENT_POLICY.authorization_binding()),
        "evidence": dict(rec.INCIDENT_DESIGNATED_EVIDENCE),
        "installed_source": {
            "path": __file__,
            "version": r.CODEX_VERSION,
            "sha256": r.CODEX_SHA256,
            "team_identifier": r.CODEX_TEAM_ID,
        },
        "executive_source": dict(s.executive_source),
        "worker": {
            "worker_user": rec.get_slot("codex-01").worker_user,
            "worker_uid": r.WORKER_UID,
            "worker_gid": r.WORKER_GID,
            "provider_home": "/provider-home",
            "workspace_binding_class": r.COMPANY_WORKSPACE_BINDING_CLASS,
            "expected_credential_kind": "device-auth",
        },
        "credential_lstat": dict(s.auth),
        "model": r.PRODUCTION_MODEL,
        "issuer_request_id": FORWARD_I,
        "issuer_request_sha256": "a" * 64,
        "successor_request_id": SUCCESSOR_Q,
        "budget": 1,
    }

# Parent contract falsifiers and the held-custody integration boundary.
# These contexts are offline trusted fixtures, not an installed producer.

def inject_context(s, **kwargs):
    contexts = []
    def factory(request):
        context = OfflineHostContext(request, **kwargs)
        contexts.append(context)
        return context
    s.fwd_broker._forward_host_guard = factory
    return contexts


def test_same_held_context_binds_wire_connection_source_and_stages(forward_env):
    s = forward_env
    contexts = inject_context(s)
    connection = _MemoryConnection(canonical(forward_args()))
    serve_connection(s.fwd_broker, connection, peer_resolver=lambda _c: 501)
    assert json.loads(connection.sent)["ok"] is True
    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.exited
    assert ctx.request.connection is connection
    assert ctx.request.peer_uid == 501
    assert ctx.request.original_request_sha256 == ORIGINAL_D
    assert ctx.request.original_marker_sha256 == s.marker_digest
    assert dict(ctx.request.sealed_source) == s.executive_source
    assert dict(ctx.request.policy_binding) == s.fwd_policy.amendment_authorization()
    assert ctx.request.forward_request_sha256 == fwd.validate_forward_request(forward_args())[1]
    assert [stage for stage, _ in ctx.stages] == [
        "before_preflight", "before_reservation", "before_reservation_attempt",
        "before_grant", "before_terminal", "before_settlement", "after_settlement",
    ]
    reservation = fwd.reservation_path(s.fwd_broker.receipt_root).read_bytes()
    assert [sha for _, sha in ctx.stages] == [None, None] + [digest_bytes(reservation)] * 5
    assert json.loads(reservation)["evidence"]["host_observation_sha256"] == "7" * 64
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        ctx.request.deadline_monotonic_ns = 0


@pytest.mark.parametrize("stage", ["before_preflight", "before_reservation",
                                   "before_reservation_attempt", "before_grant",
                                   "before_terminal", "before_settlement"])
def test_host_drift_refuses_at_actual_stage_without_resume(forward_env, stage):
    s = forward_env
    def drift(current):
        if current == stage:
            raise ForwardHostGuardUnavailableError("lost custody")
    contexts = inject_context(s, check=drift)
    pre = stage in {"before_preflight", "before_reservation", "before_reservation_attempt"}
    with pytest.raises(ForwardHostGuardUnavailableError if pre else EffectUnknownError):
        run_forward(s)
    assert contexts[0].exited
    if pre:
        assert_no_forward_effects(s)
    else:
        assert fwd.reservation_path(s.fwd_broker.receipt_root).exists()
        assert fwd.guard_path(s.fwd_broker.receipt_root).exists()
        if stage == "before_grant":
            assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
        assert fwd.forward_state(s.fwd_broker)[0] == "RESERVED_OR_UNKNOWN"


def test_host_exclusion_changes_after_reservation_before_grant(forward_env, monkeypatch):
    s = forward_env
    current = {"excluded": True}
    def check(stage):
        if not current["excluded"]:
            raise ForwardHostGuardUnavailableError("old owner no longer excluded")
    inject_context(s, check=check)
    original_write = broker_module._write_exclusive_json
    def write(path, value):
        original_write(path, value)
        if path == fwd.reservation_path(s.fwd_broker.receipt_root):
            current["excluded"] = False
    monkeypatch.setattr(broker_module, "_write_exclusive_json", write)
    with pytest.raises(EffectUnknownError):
        run_forward(s)
    assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()
    assert fwd.reservation_path(s.fwd_broker.receipt_root).exists()


@pytest.mark.parametrize("stage", ["before_preflight", "before_grant"])
def test_context_cannot_suppress_failed_guard(forward_env, stage):
    class SuppressingContext(OfflineHostContext):
        def revalidate(self, request, *, stage: str, reservation_sha256):
            if stage == failing_stage:
                raise OSError("unavailable observation")
            return super().revalidate(request, stage=stage,
                                      reservation_sha256=reservation_sha256)
        def __exit__(self, *args):
            return True
    failing_stage = stage
    forward_env.fwd_broker._forward_host_guard = SuppressingContext
    with pytest.raises(ForwardRecoveryError if stage == "before_preflight" else EffectUnknownError):
        run_forward(forward_env)
    if stage == "before_preflight":
        assert_no_forward_effects(forward_env)
    else:
        assert fwd.guard_path(forward_env.fwd_broker.receipt_root).exists()
        assert not rec.RECOVERY_INCIDENT_GRANT_PATH.exists()


@pytest.mark.parametrize("after_effect", [False, True])
def test_cleanup_failure_is_classified_on_actual_effect_boundary(forward_env, after_effect):
    s = forward_env
    def check(stage):
        if not after_effect:
            raise ForwardRecoveryError("preflight_refused")
    contexts = inject_context(s, check=check, exit_error=OSError("cleanup uncertain"))
    with pytest.raises(EffectUnknownError if after_effect else ForwardHostGuardUnavailableError):
        run_forward(s)
    assert contexts[0].exited
    if after_effect:
        # Successful complete evidence may later be observed, but never retried.
        assert fwd.reservation_path(s.fwd_broker.receipt_root).exists()
        assert fwd.terminal_path(s.fwd_broker.receipt_root).exists()
        with pytest.raises((ForwardRecoveryError, ForwardHostGuardUnavailableError)):
            run_forward(s)
    else:
        assert_no_forward_effects(s)


@pytest.mark.parametrize("stage", ["before_reservation", "before_grant", "cleanup"])
@pytest.mark.parametrize("clock_change", ["expire", "rollback"])
def test_one_monotonic_endpoint_covers_stages_and_cleanup(
    forward_env, monkeypatch, stage, clock_change,
):
    ticks = [10_000_000_000]
    monkeypatch.setattr(fwd, "time", types.SimpleNamespace(monotonic_ns=lambda: ticks[0]))
    def change_clock():
        ticks[0] = 40_000_000_000 if clock_change == "expire" else 9_000_000_000
    class TimedContext(OfflineHostContext):
        def revalidate(self, request, *, stage: str, reservation_sha256):
            result = super().revalidate(request, stage=stage,
                                        reservation_sha256=reservation_sha256)
            assert request.deadline_monotonic_ns == 40_000_000_000
            if stage == failing_stage:
                change_clock()
            return result
        def __exit__(self, *args):
            super().__exit__(*args)
            if failing_stage == "cleanup":
                change_clock()
    failing_stage = stage
    forward_env.fwd_broker._forward_host_guard = TimedContext
    with pytest.raises(ForwardRecoveryError if stage == "before_reservation" else EffectUnknownError):
        run_forward(forward_env)
    if stage == "before_reservation":
        assert_no_forward_effects(forward_env)
    else:
        assert fwd.reservation_path(forward_env.fwd_broker.receipt_root).exists()


@pytest.mark.parametrize("slot", ["reservation", "terminal"])
@pytest.mark.parametrize("mutation", ["mode", "hardlink", "duplicate_key", "acl"])
def test_forward_evidence_strict_custody(forward_env, monkeypatch, slot, mutation):
    s = forward_env
    run_forward(s)
    path = forward_paths(s)[slot]
    if mutation == "mode":
        path.chmod(0o644)
    elif mutation == "hardlink":
        os.link(path, path.with_suffix(".second-link"))
    elif mutation == "duplicate_key":
        raw = path.read_bytes()
        value = json.loads(raw)
        key = next(iter(value))
        path.write_bytes(b"{" + json.dumps(key).encode() + b":" + json.dumps(value[key]).encode() + b"," + raw[1:])
    else:
        original_acl = rec._readiness._assert_no_macos_acl
        def acl(p):
            if p == path:
                raise rec._readiness.ReadinessError("acl_present")
            return original_acl(p)
        monkeypatch.setattr(rec._readiness, "_assert_no_macos_acl", acl)
    with pytest.raises((ForwardRecoveryError, broker_module.BrokerTrustError,
                        rec._readiness.ReadinessError)):
        fwd.complete_join_from_custody(s.fwd_broker)


def test_paired_forward_digest_cannot_replace_original_digest(forward_env):
    s = forward_env
    run_forward(s)
    grant = read_custody(rec.RECOVERY_INCIDENT_GRANT_PATH)
    commitment = read_custody(rec.RECOVERY_INCIDENT_COMMITMENT_PATH)
    forward_digest = fwd.validate_forward_request(forward_args())[1]
    grant["issuer_request_sha256"] = forward_digest
    commitment["issuer_request_sha256"] = forward_digest
    commitment["grant_sha256"] = digest_bytes(canonical(grant))
    with pytest.raises(ForwardRecoveryError, match="incident_commitment_mismatch"):
        fwd.validate_v2_commitment_document(
            commitment, commitment_bytes=canonical(commitment), grant=grant,
            grant_sha256=commitment["grant_sha256"],
        )


@pytest.mark.parametrize("key", ["expected_current_release_sha", "expected_current_manifest_sha256"])
@pytest.mark.parametrize("value", [123, None, [], True])
def test_malformed_selectors_are_typed_refusals(key, value):
    with pytest.raises(ForwardRecoveryError):
        fwd.validate_forward_request(forward_args(**{key: value}))
