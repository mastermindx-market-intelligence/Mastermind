"""Original selected-child result content through the retained native read path."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json

import pytest

from control_plane.executive_terminal_return import (
    SELECTED_CHILD_RESULT_MAX_BYTES, selected_child_result_capsule,
    validate_selected_child_result_capsule,
)
from integrations.hermes_delegate.executive import (
    clear_selected_child_composition, selected_child_composition,
    validate_selected_child_envelope, validate_selected_child_ingress_envelope,
)
from integrations.hermes_harness import native_tool_registration as native
from integrations.hermes_harness.native_executive_consumer import NativeExecutiveTransport
from integrations.hermes_harness.tests.test_native_executive_consumer import (
    _McpLoop, _Owner, _Session, _Result, _publication,
)
from tests.test_executive_terminal_return_capsule_v2 import _candidate
from tests.test_hermes_selected_child_dispatch import (
    _selected_child_service, _admit_work_child, _install, _settle, _claim_events,
    short_socket_root,
)


def _observation(*, summary="Original worker finding. 日本語 ✓", actions=("Verify the original evidence.",)):
    publication = _publication()
    candidate = dataclasses.replace(
        _candidate(role="work", summary=summary, next_actions=actions),
        root_job_id=publication.root_job_id, job_id=publication.job_id)
    capsule = selected_child_result_capsule(candidate, command_id=publication.command)
    body = {
        "schema": native.SELECTED_CHILD_SCHEMA, "state": "COMPLETED", "reason": None,
        "command_id": publication.command, "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id, "root_job_id": candidate.root_job_id,
        "attempt_status": "COMPLETED", "job_status": "COMPLETED", "live_submit": True,
        "role": candidate.role, "result_status": "RESULT",
        "result_envelope_digest": candidate.result_envelope_digest,
        "terminal_evidence_digest": candidate.terminal_evidence_digest,
    }
    if capsule is not None:
        body["result_capsule"] = capsule
    return publication, candidate, body


class _Transport:
    def __init__(self, body, *, after=lambda: None):
        self.body, self.after, self.calls = body, after, []

    def submit_selected_child(self, command):
        self.calls.append(("submit", command))
        self.after()
        return copy.deepcopy(self.body)

    def selected_child_status(self, command):
        self.calls.append(("status", command))
        self.after()
        return copy.deepcopy(self.body)


def _handler(transport, publication, *, guard=lambda: True, session_key=None):
    return native.native_delegate_handler(native.NativeDelegateBinding(
        transport=transport, currentness_guard=guard, profile_id="mmsecretary",
        session_id="original-native-session", task_id="original-native-task",
        session_key=session_key, command=publication.command, job_id=publication.job_id))


def _invoke(handler, publication, *, action="selected_child_status",
            session_id="original-native-session", task_id="original-native-task"):
    return json.loads(handler({"action": action, "command": publication.command},
                             session_id=session_id, task_id=task_id))


@pytest.mark.parametrize("summary", ["", "  Original\n全文\t  "])
def test_capsule_preserves_canonical_empty_or_unicode_summary_and_exact_receipts(summary):
    publication, candidate, body = _observation(summary=summary)
    capsule = body["result_capsule"]
    assert capsule["summary"] == summary
    assert capsule["next_actions"] == list(candidate.next_actions)
    assert capsule["parent_consumed"] is False
    assert validate_selected_child_envelope(body, command_id=publication.command) == body
    joined = validate_selected_child_ingress_envelope(
        {**body, "target_digest": publication.target_digest},
        command_id=publication.command, job_id=publication.job_id,
        target_digest=publication.target_digest)
    assert joined["result_capsule"] == capsule
    assert "session_ref" not in capsule and "native_session_id" not in capsule


def test_oversize_valid_synopsis_is_omitted_without_slicing_or_losing_completion_metadata():
    publication, candidate, body = _observation(summary="界" * 8192, actions=("界" * 8192,))
    assert selected_child_result_capsule(candidate, command_id=publication.command) is None
    assert "result_capsule" not in body
    assert body["state"] == "COMPLETED" and body["result_status"] == "RESULT"
    small = _observation()[2]["result_capsule"]
    assert len(json.dumps(small, ensure_ascii=False).encode()) < SELECTED_CHILD_RESULT_MAX_BYTES


@pytest.mark.parametrize("mutation", [
    "job", "attempt", "root", "role", "result_digest", "terminal_digest", "receipt",
    "consumed", "extra", "missing", "empty_action", "duplicate_action",
    "summary_nul", "action_nul", "unicode", "oversize", "not_completed",
])
def test_malformed_or_foreign_result_withholds_content_and_keeps_original_command(mutation):
    publication, _, body = _observation()
    capsule = body["result_capsule"]
    if mutation in {"job", "attempt", "root"}:
        capsule[{"job": "job_id", "attempt": "attempt_id", "root": "root_job_id"}[mutation]] = "other"
    elif mutation == "role": capsule["role"] = []
    elif mutation == "result_digest": capsule["result_envelope_digest"] = "0" * 64
    elif mutation == "terminal_digest": capsule["terminal_evidence_digest"] = "0" * 64
    elif mutation == "receipt": capsule["artifact_receipt_digest"] = "bad"
    elif mutation == "consumed": capsule["parent_consumed"] = True
    elif mutation == "extra": capsule["authorization"] = "not authority"
    elif mutation == "missing": capsule.pop("summary")
    elif mutation == "empty_action": capsule["next_actions"] = [""]
    elif mutation == "duplicate_action": capsule["next_actions"] *= 2
    elif mutation == "summary_nul": capsule["summary"] = "bad\x00text"
    elif mutation == "action_nul": capsule["next_actions"] = ["bad\x00text"]
    elif mutation == "unicode": capsule["summary"] = "\ud800"
    elif mutation == "oversize":
        capsule["summary"] = "界" * 8192
        capsule["next_actions"] = ["界" * 8192]
    else: body["state"] = "ACTIVE"
    with pytest.raises(ValueError):
        validate_selected_child_result_capsule(capsule, observation=body)
    with pytest.raises(ValueError):
        validate_selected_child_envelope(body, command_id=publication.command)
    transport = _Transport(body)
    result = _invoke(_handler(transport, publication), publication)
    assert result["state"] == "UNAVAILABLE" and "result_capsule" not in result
    assert result["command_id"] == publication.command
    assert transport.calls == [("status", publication.command)]


@pytest.mark.parametrize("action,expected", [
    ("selected_child_submit", "EFFECT_UNKNOWN"), ("selected_child_status", "UNAVAILABLE"),
])
@pytest.mark.parametrize("drift", ["binding", "session_key"])
def test_native_read_rechecks_caller_after_rpc_before_exposing_result(monkeypatch, action, expected, drift):
    publication, _, body = _observation()
    state = {"current": True, "key": "original-key"}
    monkeypatch.setattr(native, "_bound_session_key", lambda: state["key"])
    def revoke():
        state["current"] = drift != "binding"
        state["key"] = "changed-key" if drift == "session_key" else "original-key"
    transport = _Transport(body, after=revoke)
    handler = _handler(transport, publication, guard=lambda: state["current"], session_key="original-key")
    result = _invoke(handler, publication, action=action)
    assert result["state"] == expected and "result_capsule" not in result
    assert result["command_id"] == publication.command and len(transport.calls) == 1


@pytest.mark.parametrize("session_id,task_id", [
    ("foreign-session", "original-native-task"), ("original-native-session", "foreign-task"),
])
def test_foreign_native_caller_cannot_read_original_result(session_id, task_id):
    publication, _, body = _observation()
    transport = _Transport(body)
    result = _invoke(_handler(transport, publication), publication,
                     session_id=session_id, task_id=task_id)
    assert result["state"] == "REFUSED" and "result_capsule" not in result
    assert transport.calls == []


def test_actual_native_mcp_transport_preserves_result_through_shared_ingress_decoder():
    publication, _, body = _observation()
    loop = _McpLoop()
    session = _Session([_Result(structured={**body, "target_digest": publication.target_digest})])
    owner = _Owner(session)
    try:
        transport = NativeExecutiveTransport(publication=publication, server=owner,
            session=session, loop=loop.loop, currentness=lambda: True, timeout=5)
        result = _invoke(_handler(transport, publication), publication)
        assert result["result_capsule"] == body["result_capsule"]
        assert session.calls == [("mmx_delegate", {
            "action": "selected_child_status", "command": publication.command})]
        assert result["result_capsule"]["parent_consumed"] is False
    finally:
        loop.close()


def test_retained_native_turn_reads_real_original_completion_without_another_dispatch(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="native-original-result") as (service, supervisor, root, received, gate):
            runtime = service.runtime
            work = _admit_work_child(service, root)
            command = _install(service, runtime, work)
            composition = selected_child_composition()
            class OriginalTransport:
                def submit_selected_child(self, original): return composition.submit(original)
                def selected_child_status(self, original): return composition.status(original)
            handler = native.native_delegate_handler(native.NativeDelegateBinding(
                transport=OriginalTransport(), currentness_guard=lambda: True,
                profile_id="mmsecretary", session_id="original-native-session",
                task_id="original-native-task", command=command, job_id=work.job_id))
            async def call(action):
                return json.loads(await asyncio.to_thread(handler,
                    {"action": action, "command": command},
                    session_id="original-native-session", task_id="original-native-task"))
            try:
                active = await call("selected_child_submit")
                assert active["state"] == "ACTIVE" and "result_capsule" not in active
                gate.set()
                await _settle(service)
                observed = await call("selected_child_status")
                material = runtime.validated_role_completion(work.job_id,
                    expected_attempt_id=active["attempt_id"])
                capsule = observed["result_capsule"]
                assert observed["state"] == "COMPLETED"
                assert capsule["summary"] == material.result_envelope["summary"]
                assert capsule["next_actions"] == material.result_envelope["next_actions"]
                assert capsule["job_id"] == work.job_id
                assert capsule["attempt_id"] == active["attempt_id"]
                assert capsule["command_id"] == command and capsule["parent_consumed"] is False
                again = await call("selected_child_status")
                assert again == observed
                assert len(_claim_events(runtime, work.job_id)) == 1
                assert len(received) == 1 and received[0].attempt_id == active["attempt_id"]
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())
