"""Private Control issuer receipt producer mechanics.

FIXTURES DO NOT PROVE NATIVE QUALIFICATION. Kernel observation and installed
qualification are isolated seams. Existing capture/binding code stays real.
No live launchd/SecCode/service/account/provider/installed-file access.
No P1 source/probes/review recreation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import socket
import time
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from control_plane import executive_authority as authority
from control_plane import executive_installed_peer as installed_peer
from control_plane import executive_peer_identity as peer_identity
from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_release_contract import canonical_release_bytes
from ops.executive_os import release_owner_issuer_binding as m

OWNER = "11111111-1111-4111-8111-111111111111"
TARGET = "5" * 64
COMMIT = "1" * 40
TREE = "2" * 40
BOOT = "abcdef12-3456-4789-abcd-123456789abc"
CONFIG_DIGEST = "b" * 64
APP_UID = 458
ISSUED_MS = 2_000_000_000_000
ISSUED_NS = 1_000_000_000
EXPIRES_MS = ISSUED_MS + 600_000
DEADLINE_NS = ISSUED_NS + 30_000_000_000
NOW_MS = ISSUED_MS + 1_000
NOW_NS = ISSUED_NS + 1_000_000
AUDIT = b"K" * 32
PEER_PID = 1234
PEER_PV = 5678


def _policy_mapping():
    return {
        "schema": "mastermind.executive_release_controller_policy/v1",
        "policy_id": "release-policy",
        "generation": 7,
        "enabled": True,
        "issuer_digest": "1" * 64,
        "resource_digest": "2" * 64,
        "subject_digests": ["3" * 64],
        "client_refs": ["4" * 64],
        "required_scopes": ["mastermind.executive.intent.submit"],
        "actions": ["executive.release.upgrade"],
        "target_refs": [TARGET],
        "installer_profile_digests": ["6" * 64],
        "source_policy_modes": ["exact_protected_master"],
        "max_approval_lifetime_seconds": 300,
        "confirmation_requirement": "delegated",
    }


def _policy_source(mapping=None):
    value = _policy_mapping() if mapping is None else mapping
    lines = ["executive_release_controller_policy:"]
    for key, item in value.items():
        if type(item) is list:
            lines.append(f"  {key}:")
            lines.extend(f"    - {entry}" for entry in item)
        else:
            scalar = str(item).lower() if type(item) is bool else str(item)
            lines.append(f"  {key}: {scalar}")
    return ("\n".join(lines) + "\n").encode()


def _policy():
    return ReleaseControllerPolicy.from_bytes(_policy_source())


def _expectation(**changes):
    values = {
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "release_commit": COMMIT,
        "release_tree": TREE,
        "boot_id": BOOT,
        "control_config_digest": CONFIG_DIGEST,
        "app_peer_uid": APP_UID,
        "policy": _policy(),
        "issued_at_ms": ISSUED_MS,
        "issued_monotonic_ns": ISSUED_NS,
        "effect_expires_at_ms": EXPIRES_MS,
        "effect_deadline_monotonic_ns": DEADLINE_NS,
    }
    values.update(changes)
    return m._ReleaseOwnerExpectation(**values)


def _seam_kernel(monkeypatch, *, euid=450, pid=PEER_PID, pidversion=PEER_PV, audit=AUDIT):
    def fake_observe(connection):
        return peer_identity._KernelObservation(
            audit, euid, pid, pidversion, peer_identity._descriptor_identity(connection)
        )

    monkeypatch.setattr(peer_identity, "_observe_socket", fake_observe)


def _seam_clock(monkeypatch, *, wall_ms=NOW_MS, mono_ns=NOW_NS):
    state = {"wall_ms": wall_ms, "mono_ns": mono_ns}

    def fake_time():
        return state["wall_ms"] / 1000.0

    def fake_monotonic_ns():
        return state["mono_ns"]

    def fake_monotonic():
        return state["mono_ns"] / 1_000_000_000.0

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(time, "monotonic_ns", fake_monotonic_ns)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    return state


def _owner_observation(capture, *, boot_id=BOOT, release=COMMIT, config_digest=CONFIG_DIGEST, label=None):
    return peer_identity._QualifiedOwnerObservation(
        real_boot_id=boot_id,
        audit_identity_digest=capture.audit_identity_digest,
        service_label=label if label is not None else installed_peer._LAUNCHD_ROLES["control"].label,
        installed_release=release,
        config_digest=config_digest,
        connection_instance=capture.connection_instance,
        euid=capture.euid,
        pid=capture.pid,
        pidversion=capture.pidversion,
        plist_path="/Library/LaunchDaemons/com.mastermind.executive.control.plist",
        plist_uid=0,
        service_uid=450,
        argv=("/fixed/python", "-I", "-S", "-B", "/fixed/control.py"),
        python_provenance_digest="c" * 64,
        wrapper_digest="d" * 64,
        designated_requirement_digest="e" * 64,
        dynamic_code_identity_digest="f" * 64,
        dynamic_code_status=0,
    )


def _seam_qualify(monkeypatch, *, observe=None, calls=None, facts=None):
    """Isolated installed-qualification seam; capture/binding code stays real."""
    plan = dict(facts or {})

    def fake_qualify(peer_obj, *, role, deadline_monotonic_ns):
        if calls is not None:
            calls.append(deadline_monotonic_ns)
        if role != "control":
            raise peer_identity.PeerIdentityError("SERVICE_ROLE_UNSUPPORTED")
        peer_identity._current_capture(peer_obj)
        observation = _owner_observation(
            peer_obj,
            boot_id=plan.get("boot_id", BOOT),
            release=plan.get("release_commit", COMMIT),
            config_digest=plan.get("control_config_digest", CONFIG_DIGEST),
            label=plan.get("service_label"),
        )
        if observe is not None:
            observe(peer_obj, observation)
        return peer_identity._bind_qualified_owner_observation(
            peer_identity._OWNER_CAPABILITY,
            peer=peer_obj,
            observation=observation,
        )

    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", fake_qualify)


@pytest.fixture
def clocked(monkeypatch):
    return _seam_clock(monkeypatch)


@pytest.fixture
def captured(monkeypatch, clocked):
    """Real socketpair + isolated kernel observation; NOT native qualification."""
    _seam_kernel(monkeypatch)
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        yield first, second
    finally:
        first.close()
        second.close()


def test_expectation_type_is_frozen_closed_and_private():
    assert m._ReleaseOwnerExpectation.__dataclass_fields__.keys() == {
        "owner_installation_id",
        "target_ref",
        "release_commit",
        "release_tree",
        "boot_id",
        "control_config_digest",
        "app_peer_uid",
        "policy",
        "issued_at_ms",
        "issued_monotonic_ns",
        "effect_expires_at_ms",
        "effect_deadline_monotonic_ns",
    }
    expected = _expectation()
    with pytest.raises(AttributeError):
        expected.owner_installation_id = "other"


@pytest.mark.parametrize(
    "name,value",
    [
        ("owner_installation_id", None),
        ("owner_installation_id", "not-a-uuid"),
        ("owner_installation_id", "00000000-0000-0000-0000-000000000000"),
        ("target_ref", None),
        ("target_ref", "5" * 63),
        ("target_ref", "5" * 65),
        ("target_ref", "G" * 64),
        ("target_ref", "0" * 64),
        ("release_commit", None),
        ("release_commit", "1" * 39),
        ("release_commit", "0" * 40),
        ("release_tree", "2" * 41),
        ("boot_id", None),
        ("boot_id", "not-a-uuid"),
        ("control_config_digest", "b" * 63),
        ("control_config_digest", "0" * 64),
        ("app_peer_uid", None),
        ("app_peer_uid", True),
        ("app_peer_uid", False),
        ("app_peer_uid", 0),
        ("app_peer_uid", -1),
        ("app_peer_uid", "458"),
        ("issued_at_ms", True),
        ("issued_at_ms", 0),
        ("issued_monotonic_ns", False),
        ("effect_expires_at_ms", ISSUED_MS),
        ("effect_deadline_monotonic_ns", ISSUED_NS),
        ("policy", None),
        ("policy", object()),
    ],
)
def test_malformed_expectations_refuse(name, value):
    with pytest.raises(m.IssuerBindingError):
        _expectation(**{name: value})


def test_observation_constructors_refuse_public_data():
    with pytest.raises(TypeError):
        m._IssuerObservation()


def test_module_has_no_public_broker_surface():
    assert m.__all__ == []
    for name in ("produce", "consume", "dispatch", "main"):
        assert not hasattr(m, name)


def test_success_produces_canonical_receipt_and_consumes(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    calls: list[int] = []
    _seam_qualify(monkeypatch, calls=calls)
    observation = m._produce_issuer_receipt(first, expected)
    assert type(observation) is m._IssuerObservation
    assert type(observation.receipt_bytes) is bytes
    assert observation.receipt_bytes.endswith(b"\n")
    receipt = json.loads(observation.receipt_bytes)
    assert receipt["schema"] == "mastermind.executive_release_issuer_binding/v1"
    assert receipt["role"] == "control"
    assert receipt["control_uid"] == 450
    assert receipt["app_peer_uid"] == APP_UID
    assert receipt["boot_id"] == BOOT
    assert receipt["release_commit"] == COMMIT
    assert receipt["release_tree"] == TREE
    assert receipt["owner_installation_id"] == OWNER
    assert receipt["target_ref"] == TARGET
    assert set(receipt) == {
        "schema",
        "owner_installation_id",
        "target_ref",
        "release_commit",
        "release_tree",
        "boot_id",
        "role",
        "control_uid",
        "app_peer_uid",
        "policy",
        "binding_evidence_digest",
        "observed_at",
    }
    assert receipt["observed_at"] == datetime.fromtimestamp(
        NOW_MS // 1000, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    facts = observation.sealed_facts
    assert facts.audit_identity_digest == hashlib.sha256(AUDIT).hexdigest()
    assert facts.pid == PEER_PID
    assert facts.pidversion == PEER_PV
    assert facts.real_boot_id == BOOT
    assert facts.installed_release == COMMIT
    assert facts.config_digest == CONFIG_DIGEST
    evidence_doc = {
        "schema": "mastermind.executive_release_issuer_binding_evidence/v1",
        "audit_identity_digest": facts.audit_identity_digest,
        "pid": facts.pid,
        "pidversion": facts.pidversion,
        "real_boot_id": facts.real_boot_id,
        "service_label": facts.service_label,
        "installed_release": facts.installed_release,
        "config_digest": facts.config_digest,
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "release_commit": COMMIT,
        "release_tree": TREE,
        "control_config_digest": CONFIG_DIGEST,
        "app_peer_uid": APP_UID,
        "control_uid": 450,
        "role": "control",
    }
    assert facts.binding_evidence_digest == hashlib.sha256(
        canonical_release_bytes(evidence_doc)
    ).hexdigest()
    assert receipt["binding_evidence_digest"] == facts.binding_evidence_digest
    assert len(calls) >= 2
    assert all(endpoint == DEADLINE_NS for endpoint in calls)
    consumed = m._consume_issuer_receipt(observation, first, expected)
    assert consumed == observation.receipt_bytes


def test_produce_returns_fresh_private_objects_not_public_authority(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    for value in (observation, observation.capture, observation.binding):
        with pytest.raises(TypeError):
            copy.deepcopy(value)
    assert copy.deepcopy(observation.expectation) == expected  # data, not authority
    with pytest.raises(TypeError):
        pickle.loads(pickle.dumps(observation))


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        {},
        {"receipt": b"x"},
        b"serialized-receipt",
        450,
        "peer-pid",
        object(),
    ],
)
def test_consume_refuses_non_observation_inputs(captured, monkeypatch, value):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(value, first, expected)
    assert caught.value.code == "ISSUER_OBSERVATION_REQUIRED"


def test_forged_observation_with_dict_fields_refuses(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    forged = object.__new__(m._IssuerObservation)
    object.__setattr__(forged, "capture", {"euid": 450, "pid": PEER_PID})
    object.__setattr__(forged, "binding", observation.binding)
    object.__setattr__(forged, "expectation", expected)
    object.__setattr__(forged, "receipt_bytes", observation.receipt_bytes)
    object.__setattr__(forged, "sealed_facts", observation.sealed_facts)
    object.__setattr__(forged, "endpoint_monotonic_ns", observation.endpoint_monotonic_ns)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(forged, first, expected)
    assert caught.value.code == "ISSUER_CAPTURE_REQUIRED"


def test_altered_expected_context_refuses(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    for change in (
        {"target_ref": "9" * 64},
        {"release_commit": "a" * 40},
        {"boot_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
        {"control_config_digest": "c" * 64},
        {"app_peer_uid": APP_UID + 1},
        {"owner_installation_id": "22222222-2222-4222-8222-222222222222"},
    ):
        other = _expectation(**change)
        with pytest.raises(m.IssuerBindingError) as caught:
            m._consume_issuer_receipt(observation, first, other)
        assert caught.value.code == "ISSUER_EXPECTATION_MISMATCH"


def test_altered_receipt_bytes_refuse_consume(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    receipt = json.loads(observation.receipt_bytes)
    receipt["binding_evidence_digest"] = "0" * 64
    altered = (
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    forged = object.__new__(m._IssuerObservation)
    object.__setattr__(forged, "capture", observation.capture)
    object.__setattr__(forged, "binding", observation.binding)
    object.__setattr__(forged, "expectation", expected)
    object.__setattr__(forged, "receipt_bytes", altered)
    object.__setattr__(forged, "sealed_facts", observation.sealed_facts)
    object.__setattr__(forged, "endpoint_monotonic_ns", observation.endpoint_monotonic_ns)
    object.__setattr__(forged, "receipt_sha256", observation.receipt_sha256)
    object.__setattr__(forged, "expectation_sha256", observation.expectation_sha256)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(forged, first, expected)
    assert caught.value.code == "ISSUER_RECEIPT_MISMATCH"


def test_wrong_uid_role_boot_release_config_refuse(captured, monkeypatch):
    first, _second = captured
    cases = [
        ({"euid": 451}, "SERVICE_PEER_IDENTITY_MISMATCH"),
        ({"service_label": "com.mastermind.executive.gateway"}, "ISSUER_ROLE_LABEL_MISMATCH"),
        ({"boot_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}, "ISSUER_BOOT_MISMATCH"),
        ({"release_commit": "a" * 40}, "ISSUER_RELEASE_MISMATCH"),
        ({"control_config_digest": "c" * 64}, "ISSUER_CONFIG_MISMATCH"),
    ]
    for seam, code in cases:
        expected = _expectation()
        _seam_kernel(monkeypatch, euid=seam.get("euid", 450))
        _seam_qualify(monkeypatch, facts=seam)
        with pytest.raises(m.IssuerBindingError) as caught:
            m._produce_issuer_receipt(first, expected)
        assert caught.value.code == code, seam


def test_app_uid_invalid_refuses_expectation_and_join(captured, monkeypatch):
    first, _second = captured
    for bad in (0, -1, True, "458"):
        with pytest.raises(m.IssuerBindingError) as caught:
            _expectation(app_peer_uid=bad)
        assert caught.value.code == "ISSUER_EXPECTATION_APP_UID"
    same_uid = _expectation(app_peer_uid=450)
    _seam_qualify(monkeypatch)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, same_uid)
    assert caught.value.code == "ISSUER_APP_PEER_UID_INVALID"
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    object.__setattr__(observation.expectation, "app_peer_uid", 450)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, _expectation())
    assert caught.value.code == "ISSUER_EXPECTATION_MISMATCH"


def test_foreign_socket_refuses_consume(captured, monkeypatch):
    first, second = captured
    other_a, other_b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        expected = _expectation()
        _seam_qualify(monkeypatch)
        observation = m._produce_issuer_receipt(first, expected)
        with pytest.raises(m.IssuerBindingError) as caught:
            m._consume_issuer_receipt(observation, other_a, expected)
        assert caught.value.code == "ISSUER_SOCKET_MISMATCH"
    finally:
        for connection in (other_a, other_b, second):
            connection.close()


def test_closed_socket_refuses_consume(captured, monkeypatch):
    first, second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    first.close()
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code in {
        "PEER_CONNECTION_CLOSED",
        "PEER_KERNEL_IDENTITY_UNAVAILABLE",
        "ISSUER_CAPTURE_UNAVAILABLE",
    }


def test_receiver_pid_change_refuses_consume(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    receiver_pid = os.getpid()
    monkeypatch.setattr(peer_identity.os, "getpid", lambda: receiver_pid + 1)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code == "PEER_CAPTURE_PROCESS_CHANGED"


def test_changed_kernel_identity_on_second_qualification_refuses(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    calls = {"count": 0}
    original = peer_identity._observe_socket

    def drifting(connection):
        calls["count"] += 1
        if calls["count"] == 1:
            return peer_identity._KernelObservation(
                AUDIT, 450, PEER_PID, PEER_PV, peer_identity._descriptor_identity(connection)
            )
        return peer_identity._KernelObservation(
            b"J" * 32, 450, PEER_PID, PEER_PV, peer_identity._descriptor_identity(connection)
        )

    monkeypatch.setattr(peer_identity, "_observe_socket", drifting)
    _seam_qualify(monkeypatch)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code in {
        "PEER_IDENTITY_CHANGED",
        "PEER_AUDIT_IDENTITY_INCOMPLETE",
        "PEER_KERNEL_IDENTITY_UNAVAILABLE",
        "ISSUER_CAPTURE_UNAVAILABLE",
    }


def test_changed_pid_or_pidversion_refuses_second_qualification(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    calls = {"count": 0}

    def drifting(connection):
        calls["count"] += 1
        pid = PEER_PID if calls["count"] == 1 else PEER_PID + 1
        return peer_identity._KernelObservation(
            AUDIT, 450, pid, PEER_PV, peer_identity._descriptor_identity(connection)
        )

    monkeypatch.setattr(peer_identity, "_observe_socket", drifting)
    _seam_qualify(monkeypatch)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code in {
        "PEER_IDENTITY_CHANGED",
        "ISSUER_CAPTURE_UNAVAILABLE",
        "ISSUER_QUALIFICATION_DRIFT",
    }


def test_changed_source_config_on_second_qualification_refuses(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    calls = {"count": 0}

    def observe_drift(_peer_obj, _observation):
        calls["count"] += 1
        if calls["count"] == 2:
            raise AssertionError("config drift should change observation fields")

    def fake_qualify(peer_obj, *, role, deadline_monotonic_ns):
        peer_identity._current_capture(peer_obj)
        digest = CONFIG_DIGEST if calls["count"] < 1 else "c" * 64
        calls["count"] += 1
        observation = _owner_observation(peer_obj, config_digest=digest)
        return peer_identity._bind_qualified_owner_observation(
            peer_identity._OWNER_CAPABILITY,
            peer=peer_obj,
            observation=observation,
        )

    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", fake_qualify)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code in {"ISSUER_CONFIG_MISMATCH", "ISSUER_QUALIFICATION_DRIFT"}


def test_consume_fresh_qualification_fact_drift_refuses(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)

    calls = {"count": 0}

    def fake_qualify(peer_obj, *, role, deadline_monotonic_ns):
        peer_identity._current_capture(peer_obj)
        calls["count"] += 1
        digest = "c" * 64 if calls["count"] >= 1 else CONFIG_DIGEST
        observation_obj = _owner_observation(peer_obj, config_digest=digest)
        return peer_identity._bind_qualified_owner_observation(
            peer_identity._OWNER_CAPABILITY,
            peer=peer_obj,
            observation=observation_obj,
        )

    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", fake_qualify)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code == "ISSUER_CONFIG_MISMATCH"


def test_clock_before_issued_refuses_produce_and_consume(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    state = _seam_clock(monkeypatch, wall_ms=ISSUED_MS - 1, mono_ns=ISSUED_NS)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code == "ISSUER_CLOCK_BEFORE_ISSUED"
    state.update(wall_ms=ISSUED_MS, mono_ns=ISSUED_NS - 1)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code == "ISSUER_CLOCK_BEFORE_ISSUED"
    state.update(wall_ms=NOW_MS, mono_ns=NOW_NS)
    observation = m._produce_issuer_receipt(first, expected)
    state.update(wall_ms=ISSUED_MS - 1000, mono_ns=NOW_NS)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code == "ISSUER_CLOCK_BEFORE_ISSUED"


def test_clock_deadline_refuses_produce_and_consume(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    state = _seam_clock(monkeypatch, wall_ms=NOW_MS, mono_ns=DEADLINE_NS)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code == "ISSUER_CLOCK_DEADLINE"
    state.update(mono_ns=DEADLINE_NS - 1, wall_ms=NOW_MS)
    observation = m._produce_issuer_receipt(first, expected)
    state.update(mono_ns=DEADLINE_NS)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code == "ISSUER_CLOCK_DEADLINE"


def test_clock_drift_during_capture_and_qualification_refuses(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    state = _seam_clock(monkeypatch, wall_ms=NOW_MS, mono_ns=NOW_NS)
    original_observe = peer_identity._observe_socket

    def observe_with_drift(connection):
        state["mono_ns"] = DEADLINE_NS
        return original_observe(connection)

    monkeypatch.setattr(peer_identity, "_observe_socket", observe_with_drift)
    _seam_qualify(monkeypatch)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code in {
        "ISSUER_CLOCK_DEADLINE",
        "ISSUER_CAPTURE_UNAVAILABLE",
        "PEER_IDENTITY_CHANGED",
    }


def test_clock_drift_during_qualification_deadline_refuses(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    state = _seam_clock(monkeypatch, wall_ms=NOW_MS, mono_ns=NOW_NS)
    _seam_kernel(monkeypatch)

    def fake_qualify(peer_obj, *, role, deadline_monotonic_ns):
        peer_identity._current_capture(peer_obj)
        state["mono_ns"] = DEADLINE_NS
        observation = _owner_observation(peer_obj)
        return peer_identity._bind_qualified_owner_observation(
            peer_identity._OWNER_CAPABILITY,
            peer=peer_obj,
            observation=observation,
        )

    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", fake_qualify)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code == "ISSUER_CLOCK_DEADLINE"


def test_same_original_endpoint_on_every_qualification_call(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    calls: list[int] = []
    _seam_qualify(monkeypatch, calls=calls)
    observation = m._produce_issuer_receipt(first, expected)
    assert calls
    assert all(endpoint == DEADLINE_NS for endpoint in calls)
    produce_count = len(calls)
    m._consume_issuer_receipt(observation, first, expected)
    assert len(calls) > produce_count
    assert all(endpoint == DEADLINE_NS for endpoint in calls)


def test_reflective_capture_field_change_refuses_consume(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    object.__setattr__(observation.capture, "pid", observation.capture.pid + 1)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._consume_issuer_receipt(observation, first, expected)
    assert caught.value.code in {"PEER_CAPTURE_ALTERED", "ISSUER_CAPTURE_UNAVAILABLE"}


def test_wrong_role_label_in_expectation_join_refused_by_reality(
    captured, monkeypatch
):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch, facts={"service_label": "com.mastermind.executive.mcp"})
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code == "ISSUER_ROLE_LABEL_MISMATCH"


def test_receipt_schema_is_exactly_resident_validator_schema(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    receipt = json.loads(observation.receipt_bytes)
    from ops.executive_os.release_owner_resident_inputs import _ISSUER_FIELDS

    assert set(receipt) == set(_ISSUER_FIELDS)
    assert canonical_release_bytes(receipt) + b"\n" == observation.receipt_bytes


def test_produce_refuses_non_socket_and_non_expectation(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(object(), expected)
    assert caught.value.code == "ISSUER_SOCKET_REQUIRED"
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, None)
    assert caught.value.code == "ISSUER_EXPECTATION_REQUIRED"


def test_two_qualification_observations_must_agree(captured, monkeypatch):
    first, _second = captured
    expected = _expectation()
    calls = {"count": 0}

    def fake_qualify(peer_obj, *, role, deadline_monotonic_ns):
        peer_identity._current_capture(peer_obj)
        calls["count"] += 1
        release = COMMIT if calls["count"] == 1 else "a" * 40
        observation_obj = _owner_observation(peer_obj, release=release)
        return peer_identity._bind_qualified_owner_observation(
            peer_identity._OWNER_CAPABILITY,
            peer=peer_obj,
            observation=observation_obj,
        )

    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", fake_qualify)
    with pytest.raises(m.IssuerBindingError) as caught:
        m._produce_issuer_receipt(first, expected)
    assert caught.value.code in {
        "ISSUER_RELEASE_MISMATCH",
        "ISSUER_QUALIFICATION_DRIFT",
    }


@pytest.mark.parametrize("phase", ["before_produce", "during_capture", "during_qualification", "before_consume", "during_consume"])
def test_parent_original_wall_expiry_is_fenced(captured, monkeypatch, phase):
    first, _ = captured
    expected = _expectation()
    state = _seam_clock(monkeypatch)
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    if phase in {"before_produce", "before_consume"}:
        state["wall_ms"] = EXPIRES_MS
    elif phase == "during_capture":
        original = peer_identity._observe_socket
        def observe(connection):
            state["wall_ms"] = EXPIRES_MS
            return original(connection)
        monkeypatch.setattr(peer_identity, "_observe_socket", observe)
    else:
        original = installed_peer._qualify_installed_peer_with_deadline
        def qualify(*args, **kwargs):
            state["wall_ms"] = EXPIRES_MS
            return original(*args, **kwargs)
        monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", qualify)
    with pytest.raises(m.IssuerBindingError, match="^ISSUER_CLOCK_DEADLINE$"):
        if "consume" in phase:
            m._consume_issuer_receipt(observation, first, expected)
        else:
            m._produce_issuer_receipt(first, expected)


@pytest.mark.parametrize("field,value", [
    ("observed_at", "2026-01-01T00:00:00Z"),
    ("owner_installation_id", "22222222-2222-4222-8222-222222222222"),
    ("release_tree", "9" * 40),
    ("app_peer_uid", APP_UID+1),
    ("policy", {}),
])
def test_parent_non_digest_receipt_tampering_refuses(captured, monkeypatch, field, value):
    first, _ = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    receipt = json.loads(observation.receipt_bytes)
    receipt[field] = value
    object.__setattr__(observation, "receipt_bytes", canonical_release_bytes(receipt)+b"\n")
    with pytest.raises(m.IssuerBindingError, match="^ISSUER_RECEIPT_MISMATCH$"):
        m._consume_issuer_receipt(observation, first, expected)


def test_parent_same_expected_object_cannot_extend_wall_window(captured, monkeypatch):
    first, _ = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    object.__setattr__(expected, "effect_expires_at_ms", EXPIRES_MS+1000)
    with pytest.raises(m.IssuerBindingError, match="^ISSUER_EXPECTATION_MISMATCH$"):
        m._consume_issuer_receipt(observation, first, expected)


def test_parent_retained_binding_must_be_original_connection(captured, monkeypatch):
    first, second = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    other = m._produce_issuer_receipt(second, expected)
    object.__setattr__(observation, "binding", other.binding)
    with pytest.raises(m.IssuerBindingError, match="^SERVICE_CONNECTION_MISMATCH$"):
        m._consume_issuer_receipt(observation, first, expected)


@pytest.mark.parametrize("phase", ["produce", "consume"])
def test_parent_expectation_changed_during_qualification_refuses(captured, monkeypatch, phase):
    first, _ = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    original = installed_peer._qualify_installed_peer_with_deadline
    def changing(*args, **kwargs):
        object.__setattr__(expected, "effect_expires_at_ms", EXPIRES_MS+1000)
        return original(*args, **kwargs)
    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", changing)
    with pytest.raises(m.IssuerBindingError, match="^ISSUER_EXPECTATION_MISMATCH$"):
        if phase == "produce":
            m._produce_issuer_receipt(first, expected)
        else:
            m._consume_issuer_receipt(observation, first, expected)


def test_parent_receipt_changed_during_consume_qualification_refuses(captured, monkeypatch):
    first, _ = captured
    expected = _expectation()
    _seam_qualify(monkeypatch)
    observation = m._produce_issuer_receipt(first, expected)
    original = installed_peer._qualify_installed_peer_with_deadline
    def changing(*args, **kwargs):
        document = json.loads(observation.receipt_bytes)
        document["observed_at"] = "2026-01-01T00:00:00Z"
        object.__setattr__(observation, "receipt_bytes", canonical_release_bytes(document)+b"\n")
        return original(*args, **kwargs)
    monkeypatch.setattr(installed_peer, "_qualify_installed_peer_with_deadline", changing)
    with pytest.raises(m.IssuerBindingError, match="^ISSUER_RECEIPT_MISMATCH$"):
        m._consume_issuer_receipt(observation, first, expected)
