"""C1 actual owner/Runtime/broker integration; synthetic trust is NOT live proof."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import socket
import threading

import pytest

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from control_plane import executive_release_consumer as consumer
from control_plane import executive_release_owner as owner
from control_plane import executive_privileged_client as client
from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_authority import ReleaseControllerPolicy
from control_plane.executive_release_token import _OwnerReleaseCodec
from control_plane.executive_runtime import Runtime
from tests.test_executive_release_controller_policy import inputs, source
from tests.test_executive_release_contract import precondition_fixture
from tests.test_executive_privileged_broker import _broker


def digest(value):
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


@pytest.fixture
def installed(tmp_path, monkeypatch, inputs):
    principal, effect, policy = inputs
    effect = contract.validate_normalized_effect(effect)
    policy = ReleaseControllerPolicy.from_bytes(source(policy))
    owner_id = "11111111-1111-4111-8111-111111111111"
    codec = _OwnerReleaseCodec(key=bytes(range(32)), key_id="test-key",
                              trust_generation=1, owner_installation_id=owner_id)
    preconditions = precondition_fixture()
    preconditions.update(owner_installation_id=owner_id, target_ref="5" * 64,
                         authority_policy_hash=policy.sha256, admission_contract_digest="a" * 64)
    for key in ("from_installed_manifest_digest", "staged_artifact_digest", "staged_content_metadata_digest",
                "compatibility_proof_digest", "preservation_plan_digest"):
        preconditions[key] = effect[key]
    for key in ("grant_digest", "approval_evidence_digest"):
        del preconditions[key]
    state = owner.ReleaseOwnerSnapshot(policy=policy, codec=codec, owner_installation_id=owner_id,
        target_ref="5" * 64, boot_id=preconditions["boot_id"], key_id="test-key", trust_generation=1,
        app_generation=1, schema_digest="a" * 64, admission_contract_digest="a" * 64,
        effect=effect, preconditions=preconditions)
    states = [state]
    now = [200_000]
    monkeypatch.setattr(owner.time, "time_ns", lambda: now[0] * 1_000_000)
    peer_calls = []
    def qualify(connection, role):
        # The qualification primitive is the sole synthetic boundary. Real
        # socket lifetime/PID are asserted; installed negatives belong to A2.
        assert type(connection) is socket.socket and connection.fileno() >= 0
        peer_calls.append((role, os.getpid()))
    monkeypatch.setattr(consumer, "_qualify_connection", qualify)
    monkeypatch.setattr(owner, "_qualify_connection", qualify)
    def snapshot(transition):
        assert transition == digest(states[0].effect)
        return states[0]
    root_owner = owner.ReleaseBrokerOwner(snapshot, history_trust=lambda: owner.ReleaseHistoryTrust(
        states[0].codec, states[0].owner_installation_id, states[0].target_ref))
    root_broker = _broker(tmp_path)
    root_broker._release_owner = root_owner
    transport_calls = []
    def transport(payload, *, socket_path, timeout_seconds, require_root_peer=False):
        assert socket_path == client.DEFAULT_SOCKET and require_root_peer is True
        transport_calls.append(copy.deepcopy(payload))
        serving, requesting = socket.socketpair()
        def serve():
            with serving:
                broker_module.serve_connection(root_broker, serving, peer_resolver=lambda _: 450)
        thread = threading.Thread(target=serve)
        thread.start()
        try:
            with requesting:
                requesting.settimeout(2)
                requesting.sendall(json.dumps(payload).encode() + b"\n")
                result = client._read_response(requesting)
        finally:
            thread.join(3)
            assert not thread.is_alive()
        return result
    monkeypatch.setattr(client, "_send_one_frame", transport)
    runtime = Runtime.at(tmp_path / "runtime")
    control = consumer.ReleaseControlConsumer(runtime)
    gateway, control_socket = socket.socketpair()
    def call(operation, arguments, *, as_principal=None):
        frame = ingress.project_frame(operation, arguments, principal=as_principal or principal)
        return control.handle(ingress.encode_frame(frame), control_socket)
    result = dict(runtime=runtime, control=control, call=call, states=states, now=now,
                  principal=principal, peer_calls=peer_calls, transport_calls=transport_calls,
                  root_owner=root_owner, root_broker=root_broker, socket=control_socket)
    try:
        yield result
    finally:
        gateway.close()
        control_socket.close()


def approve_arguments(installed, op="release-c1-proof"):
    effect = installed["states"][0].effect
    return {"operation_key": op, "action": effect["action"], "transition_digest": digest(effect)}


def counts(runtime):
    with runtime.store.read() as connection:
        return tuple(connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
                     for table in ("events", "jobs", "attempts"))


def test_approval_replay_prepare_history_and_commit_disarming(installed):
    call = installed["call"]
    before = counts(installed["runtime"])
    args = approve_arguments(installed)
    approved = call("approve_release_transition", args)
    assert approved["ok"] is True
    original = installed["control"]._read(args["operation_key"])
    installed["now"][0] += 1000
    assert call("approve_release_transition", args) == approved
    assert installed["control"]._read(args["operation_key"]) == original
    after = counts(installed["runtime"])
    assert after == (before[0] + 1, before[1], before[2])
    prepared = call("prepare_release_transition", {"operation_key": args["operation_key"],
                     "approved_transition_ref": approved["approved_transition_ref"]})
    state = installed["states"][0]
    payload = state.codec.decode_prepared(prepared["prepared_token"], now_ms=installed["now"][0],
                                         monotonic_ns=owner.time.monotonic_ns(), boot_id=state.boot_id)
    assert payload["approval_evidence_digest"] == digest(original)
    assert payload["request_fingerprint"] == contract.request_fingerprint_for(original)
    assert payload["expires_at_ms"] == original["expires_at_ms"]
    blocked = call("commit_prepared_release_transition", {"prepared_token": prepared["prepared_token"]})
    assert blocked["error"]["code"] == "RELEASE_COMMIT_DISARMED"
    history = call("reconcile_release_transition", {"operation_key": args["operation_key"]})
    assert history["approval"] == original.to_dict()
    assert history["broker_status"]["status"] == "NOT_FOUND"
    assert history["broker_status"]["request_id"] == contract.broker_request_id_for(payload["request_fingerprint"])
    assert counts(installed["runtime"]) == after
    assert set(role for role, _ in installed["peer_calls"]) == {"control", "gateway"}
    assert all(pid == os.getpid() for _, pid in installed["peer_calls"])
    assert installed["root_broker"]._executor.calls == []


def test_reconcile_expired_approval_needs_no_staging_and_no_new_event(installed):
    args = approve_arguments(installed)
    installed["call"]("approve_release_transition", args)
    original = installed["control"]._read(args["operation_key"])
    installed["now"][0] = original["expires_at_ms"] + 1
    installed["root_owner"]._snapshot = lambda _: pytest.fail("history must not read staged release")
    before = counts(installed["runtime"])
    result = installed["call"]("reconcile_release_transition", {"operation_key": args["operation_key"]})
    assert result["approval"] == original.to_dict()
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("operation", ["approve_release_transition", "prepare_release_transition"])
def test_expired_approval_never_renews(installed, operation):
    args = approve_arguments(installed)
    result = installed["call"]("approve_release_transition", args)
    installed["now"][0] += 300001
    if operation.startswith("prepare"):
        args = {"operation_key": args["operation_key"], "approved_transition_ref": result["approved_transition_ref"]}
    before = counts(installed["runtime"])
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"](operation, args)
    assert counts(installed["runtime"]) == before


def test_changed_effect_same_operation_refuses(installed):
    args = approve_arguments(installed)
    installed["call"]("approve_release_transition", args)
    args["transition_digest"] = "f" * 64
    before = counts(installed["runtime"])
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"]("approve_release_transition", args)
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("field,value", [("subject_digest", "c" * 64), ("client_ref", "c" * 64),
                                        ("expires_at", 199), ("issued_at", 201)])
def test_wrong_or_expired_principal_cannot_write(installed, field, value):
    principal = dataclasses.replace(installed["principal"], **{field: value})
    before = counts(installed["runtime"])
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"]("approve_release_transition", approve_arguments(installed), as_principal=principal)
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("role", ["gateway", "control"])
def test_unqualified_peer_has_zero_writes(installed, monkeypatch, role):
    def reject(connection, observed_role):
        if role == observed_role:
            raise consumer.ReleaseConsumerError("RELEASE_PEER_REFUSED")
    monkeypatch.setattr(consumer, "_qualify_connection", reject)
    monkeypatch.setattr(owner, "_qualify_connection", reject)
    before = counts(installed["runtime"])
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"]("approve_release_transition", approve_arguments(installed))
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("mutation", ["key", "policy", "precondition", "target"])
def test_change_between_snapshot_and_seal_refuses(installed, mutation):
    original = installed["states"][0]
    if mutation == "key":
        changed = dataclasses.replace(original, key_id="rotated", trust_generation=2)
    elif mutation == "policy":
        changed = dataclasses.replace(original, policy=ReleaseControllerPolicy.from_bytes(b"# revoked\n"))
    elif mutation == "target":
        changed = dataclasses.replace(original, target_ref="9" * 64)
    else:
        changed = dataclasses.replace(original, preconditions={**original.preconditions,
                                      "installed_configuration_digest": "b" * 64})
    values = iter([original, changed])
    installed["root_owner"]._snapshot = lambda _: next(values)
    before = counts(installed["runtime"])
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"]("approve_release_transition", approve_arguments(installed))
    assert counts(installed["runtime"]) == before


def test_edited_approval_seal_rejected_before_prepare_or_history(installed, monkeypatch):
    args = approve_arguments(installed)
    result = installed["call"]("approve_release_transition", args)
    original = installed["control"]._read(args["operation_key"]).to_dict()
    original["owner_seal"]["mac"] = "A" * 43
    forged = contract.validate_approval_evidence(original)
    monkeypatch.setattr(installed["control"], "_read", lambda _: forged)
    before = counts(installed["runtime"])
    for operation, arguments in (
        ("prepare_release_transition", {"operation_key": args["operation_key"],
          "approved_transition_ref": result["approved_transition_ref"]}),
        ("reconcile_release_transition", {"operation_key": args["operation_key"]}),
    ):
        with pytest.raises(consumer.ReleaseConsumerError):
            installed["call"](operation, arguments)
    assert counts(installed["runtime"]) == before


@pytest.mark.parametrize("extra", ["principal", "grant", "policy", "path", "argv", "approved"])
def test_public_arguments_cannot_supply_authority(installed, extra):
    args = {**approve_arguments(installed), extra: "forged"}
    with pytest.raises(ingress.ReleaseIngressError):
        installed["call"]("approve_release_transition", args)
    assert not installed["transport_calls"]


def test_protocol_duplicate_fields_and_noncanonical_numbers_refuse(installed):
    frame = ingress.project_frame("approve_release_transition", approve_arguments(installed),
                                  principal=installed["principal"])
    raw = ingress.encode_frame(frame)
    for malformed in (raw.replace(b'"issued_at":100', b'"issued_at":100,"issued_at":100'),
                      raw.replace(b'"issued_at":100', b'"issued_at":100.0'),
                      raw.replace(b'"issued_at":100', b'"issued_at":NaN')):
        with pytest.raises(ingress.ReleaseIngressError):
            ingress.decode_frame(malformed)


def test_unconfigured_broker_and_commit_cannot_reach_executor(installed):
    installed["root_broker"]._release_owner = None
    with pytest.raises(consumer.ReleaseConsumerError):
        installed["call"]("approve_release_transition", approve_arguments(installed))
    result = installed["call"]("commit_prepared_release_transition", {"prepared_token": "x"})
    assert result["error"]["code"] == "RELEASE_COMMIT_DISARMED"
    assert installed["root_broker"]._executor.calls == []


def test_historical_p2_id_collision_cannot_attest_p4_fingerprint(installed):
    args = approve_arguments(installed)
    installed["call"]("approve_release_transition", args)
    approval = installed["control"]._read(args["operation_key"])
    request_id = contract.broker_request_id_for(contract.request_fingerprint_for(approval))
    from tests.test_executive_privileged_broker import _raw
    installed["root_broker"].handle(_raw(request_id=request_id), peer_uid=450)
    before = counts(installed["runtime"])
    calls = len(installed["root_broker"]._executor.calls)
    result = installed["call"]("reconcile_release_transition", {"operation_key": args["operation_key"]})
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["error"]["code"] == "RELEASE_HISTORY_FAMILY_UNQUALIFIED"
    assert counts(installed["runtime"]) == before
    assert len(installed["root_broker"]._executor.calls) == calls


@pytest.mark.parametrize("uid", [450, 501])
def test_root_peer_checked_before_any_wire_bytes(monkeypatch, uid):
    class Connection:
        def settimeout(self, value):
            pass
        def connect(self, path):
            assert path == str(client.DEFAULT_SOCKET)
        def getpeereid(self):
            return uid, 0
        def sendall(self, raw):
            pytest.fail("untrusted root peer received principal bytes")
        def close(self):
            pass
    monkeypatch.setattr(client.socket, "socket", lambda *args: Connection())
    with pytest.raises(RuntimeError, match="root peer"):
        client._send_one_frame({}, socket_path=client.DEFAULT_SOCKET,
                               timeout_seconds=1, require_root_peer=True)
