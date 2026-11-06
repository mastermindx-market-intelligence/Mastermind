"""Public native evidence stays distinct from request/transport completion."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from control_plane.native_continuation import _digest, _request_key
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from integrations.session_bridge import hermes_native as native
from integrations.session_bridge.schemas import BridgeError
from tests.test_executive_fabric_composition import root_stats
from tests.test_hermes_secretary_composition import document, source_for


@pytest.fixture
def anyio_backend():
    return "asyncio"


def original():
    target_ref = "hermes_secretary:" + "a" * 64
    operation = "session-continue-" + _digest({
        "schema": "mastermind.session_bridge.hermes_secretary_operation.v1",
        "target_ref": target_ref,
    })
    key = _request_key(operation)
    request = {
        "target_ref": target_ref, "operation_key": operation,
        "read_ref": "session-reply-" + key, "native_input_sha256": "b" * 64,
        "binding": {"profile_id": "actual-profile", "session_id": "actual-session"},
    }
    event = SimpleNamespace(command_id="session-bridge-continue:" + key,
                            to_dict=lambda: {"event_id": 7, "payload": request})
    return event, request


def result(status="OBSERVED", **extra):
    value = {"schema": native.NATIVE_SCHEMA, "status": status}
    if status in {"OBSERVED", "ADMITTED"}:
        value["admission"] = {
            "admission_id": "original-admission",
            "ref": {"profile_id": "actual-profile", "session_id": "actual-session"},
            "sequence": 1, "status": "terminal", "outcome": "completed",
            "authority_epoch": 3, "execution_generation": 2,
        }
    value.update(extra)
    return value


def test_requested_and_unknown_are_distinct_from_native_admission():
    event, request = original()
    requested = native.public_result(event, request, commit_started=False)
    uncertain = native.public_result(event, request, commit_started=True)
    assert requested["native_status"] is uncertain["native_status"] is None
    assert requested["commit_started"] is False and uncertain["commit_started"] is True
    assert requested["parent_consumed"] is False
    with pytest.raises(ValueError):
        native.public_result(event, request, commit_started=False, native_result=result())


def test_terminal_answer_requires_actual_original_admission_and_preserves_unicode():
    event, request = original()
    value = native.public_result(event, request, commit_started=True,
        native_result=result(answer="Completed: 日本語 ✓\nNext line", successful=True))
    assert value["answer"] == "Completed: 日本語 ✓\nNext line"
    assert "ref" not in value["admission"]
    assert value["request_revision"] == _digest(event.to_dict())
    assert "message_key" not in value and "reply_committed" not in value
    assert native.validate_public_result(value) == value


@pytest.mark.parametrize("fault", ["session", "profile", "status", "sequence", "epoch",
                                   "generation", "success", "extra", "control"])
def test_unjoined_or_malformed_native_result_is_refused(fault):
    event, request = original()
    value = result(answer="original answer", successful=True)
    if fault in {"session", "profile"}:
        value["admission"]["ref"][fault + "_id"] = "foreign"
    elif fault == "status": value["admission"]["status"] = "queued"
    elif fault == "sequence": value["admission"]["sequence"] = True
    elif fault == "epoch": value["admission"]["authority_epoch"] = 0
    elif fault == "generation": value["admission"]["execution_generation"] = False
    elif fault == "success": value["successful"] = 1
    elif fault == "extra": value["private_policy"] = {}
    else: value["answer"] = "bad\x00answer"
    with pytest.raises(ValueError):
        native.public_result(event, request, commit_started=True, native_result=value)


@pytest.mark.parametrize("status", ["REFUSED", "NOT_SUBMITTED", "EFFECT_UNKNOWN", "UNAVAILABLE"])
def test_native_nonanswer_states_do_not_manufacture_admissions(status):
    event, request = original()
    value = native.public_result(event, request, commit_started=True,
                                native_result=result(status))
    assert value["native_status"] == status
    assert value["admission"] is value["answer"] is value["successful"] is None


@pytest.mark.parametrize("field", ["operation_key", "read_ref", "request_ref", "request_revision",
                                  "native_input_sha256", "target_ref", "parent_consumed"])
def test_public_original_identity_cannot_drift(field):
    event, request = original()
    value = native.public_result(event, request, commit_started=True, native_result=result())
    value[field] = True if field == "parent_consumed" else "foreign"
    with pytest.raises(ValueError):
        native.validate_public_result(value)


def test_complete_answer_overflow_is_explicit_and_not_truncated():
    event, request = original()
    text = "界" * 8000
    with pytest.raises(BridgeError) as error:
        native.public_result(event, request, commit_started=True,
                             native_result=result(answer=text, successful=True))
    assert error.value.code == "output_too_large"
    assert len(text) == 8000


@pytest.mark.anyio
async def test_adapter_uses_fixed_selection_and_rechecks_source_after_await(
        tmp_path, root_stats, monkeypatch):
    source = source_for(tmp_path, document(tmp_path))
    selected = source.hermes_secretary_selection()
    calls = []
    target = {key: getattr(selected, key) for key in ("profile_id", "session_id", "principal_id")}
    target.update(instance_id="instance", authority_epoch=1, revision=0, execution_generation=0)
    change = False
    class Client:
        async def request_secretary(self, request, *, before_write=None):
            calls.append(copy.deepcopy(request))
            if change:
                source.path.write_bytes(source.path.read_bytes() + b" ")
            return {"schema": native.NATIVE_SCHEMA, "status": "TARGET", "target": target}
    monkeypatch.setattr(RemoteWorkerBrokerClient, "for_secretary_conversation",
                        lambda *args, **kwargs: Client())
    adapter = native.HermesNativeSession(source, read_guard=lambda: None,
                                        submit_guard=lambda: None)
    binding = adapter.selected_binding()
    assert binding["composition_sha256"] == source.expected_sha256
    assert "transport" not in binding
    assert await adapter.observe(binding) == target
    assert calls == [{"operation": "observe", "session_id": selected.session_id}]
    change = True
    with pytest.raises(Exception):
        await adapter.observe(binding)


def test_current_admission_is_required_before_selected_native_access(tmp_path, root_stats):
    source = source_for(tmp_path, document(tmp_path))
    def refuse():
        raise BridgeError("ingress_unavailable", "closed")
    owner = native.HermesNativeSession(source, read_guard=refuse, submit_guard=refuse)
    with pytest.raises(BridgeError):
        owner.selected_binding()
