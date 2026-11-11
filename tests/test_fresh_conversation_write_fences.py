"""Actual proxy write callbacks; no provider/IPC operation is performed."""
import copy

import pytest

from control_plane.operator_harness_contract import OperationId
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from control_plane.executive_worker_broker import BrokerProtocolError
from tests.test_remote_operator_harness_adapter import _capabilities, _Client
from tests.test_native_continuation_ack_ingress import native_case, submit
from tests.test_session_bridge_parenting_composition import NATIVE


def adapter():
    return RemoteOperatorHarnessAdapter(_Client(), turn_input_loader=lambda _: "", capabilities=_capabilities())


def payload(command):
    return {"operation_id": {"command_id": command},
        "turn": {"attempt_id": "ATTEMPT-one", "session_epoch_id": "EPOCH-one", "process_generation_id": "GEN-one"},
        "generation": {"session_epoch_id": "EPOCH-one", "process_generation_id": "GEN-one"}}


@pytest.mark.parametrize("fault", ["request_closed", "principal_expired", "permission_revoked"])
def test_initial_request_checked_at_actual_write_callback(fault):
    a = adapter()
    state = {"live": True}
    def guard():
        if not state["live"]: raise ValueError(fault)
    a.bind_fresh_effect_guard(guard, attempt_id="ATTEMPT-one")
    p = payload("ohf-op:original-first-turn")
    options = a._fresh_write_options("ohf-begin-turn", p)
    state["live"] = False
    with pytest.raises(ValueError, match=fault): options["before_write"]("ohf-begin-turn", p)


def test_created_session_does_not_authorize_a_future_turn_or_start():
    a = adapter()
    live = {"create": True, "ack": False}
    def creation():
        if not live["create"]: raise ValueError("original request closed")
    def retained():
        if not live["ack"]: raise ValueError("no current writer and persisted ACK")
    a.bind_fresh_effect_guard(creation, attempt_id="ATTEMPT-one")
    command = "ohf-op:native-continuation:" + "a" * 64
    p = payload(command)
    live["create"] = False
    with pytest.raises(ValueError, match="closed"):
        a._fresh_write_options("ohf-begin-turn", p)["before_write"]("ohf-begin-turn", p)
    with pytest.raises(ValueError, match="ACK"):
        a.bind_native_continuation_guard(retained, attempt_id="ATTEMPT-one", operation_id=OperationId(command))
    live["ack"] = True
    a.bind_native_continuation_guard(retained, attempt_id="ATTEMPT-one", operation_id=OperationId(command))
    callback = a._fresh_write_options("ohf-begin-turn", p)["before_write"]
    callback("ohf-begin-turn", p)
    live["ack"] = False
    with pytest.raises(ValueError, match="ACK"): callback("ohf-begin-turn", p)
    live["ack"] = True
    for changed in (payload("ohf-op:other-turn"), payload(command + "x")):
        with pytest.raises(ValueError, match="closed"):
            a._fresh_write_options("ohf-begin-turn", changed)["before_write"]("ohf-begin-turn", changed)
    start = {"epoch": {"attempt_id": "ATTEMPT-one", "session_epoch_id": "EPOCH-one"},
        "generation": {"session_epoch_id": "EPOCH-one"}}
    with pytest.raises(ValueError, match="closed"):
        a._fresh_write_options("ohf-start", start)["before_write"]("ohf-start", start)
    changed = copy.deepcopy(p)
    changed["turn"]["attempt_id"] = "ATTEMPT-foreign"
    with pytest.raises(BrokerProtocolError): a._fresh_write_options("ohf-begin-turn", changed)
    changed = copy.deepcopy(p)
    changed["generation"]["process_generation_id"] = "GEN-foreign"
    with pytest.raises(BrokerProtocolError): a._fresh_write_options("ohf-begin-turn", changed)
    with pytest.raises(BrokerProtocolError): callback("ohf-begin-turn", changed)


def test_future_write_rechecks_actual_persisted_original_native_ack(native_case):
    """Real Runtime/Wake ACK ingress, same original parent/Attempt; no turn I/O."""
    s = native_case
    binding = s.owner.resolve(native_session_id=NATIVE, operation_key=s.args["operation_key"],
        in_reply_to=s.request["message_key"])
    def current_ack():
        return s.owner.require_native_ack(binding, workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N")
    a = adapter()
    command = "ohf-op:native-continuation:" + "a" * 64
    attempt = s.f.sealed.attempt_id
    with pytest.raises(Exception):
        a.bind_native_continuation_guard(current_ack, attempt_id=attempt, operation_id=OperationId(command))
    actual = submit(s)
    assert actual[0].inserted
    a.bind_native_continuation_guard(current_ack, attempt_id=attempt, operation_id=OperationId(command))
    p = payload(command)
    p["turn"]["attempt_id"] = attempt
    callback = a._fresh_write_options("ohf-begin-turn", p)["before_write"]
    callback("ohf-begin-turn", p)
    # A persisted ACK for another original native identity cannot substitute.
    from dataclasses import replace
    foreign = replace(s.trusted, provider_session_id="foreign-native-parent")
    with pytest.raises(Exception): submit(s, foreign)
