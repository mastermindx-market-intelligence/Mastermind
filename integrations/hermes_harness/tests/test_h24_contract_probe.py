"""H24-01 fixture matrix. No provider, credential or installed service is used.

Protocol doubles prove validation only. Receiving-owner tests reuse C17's real
disposable Runtime/claim/result fixture. Native tests reuse C28's pinned upstream
PluginContext fixture and Hermes' actual in-flight RPC cancellation boundary.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import subprocess
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from integrations.hermes_delegate.executive import (
    ExecutiveChildSelection, ExecutiveSelectedChild, ExecutiveSelectedChildComposition,
)
from integrations.hermes_harness import native_tool_registration as c28
from integrations.hermes_harness.contract_probe import (
    AuthenticatedHostFixture, CONTRACT_BASE_SHA, ContractProbe, MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES, ProbeViolation, SourceGeneration, TOOL_CATALOG_SHA256,
    canonical_json, strict_object,
)
from integrations.hermes_runtime.constants import PINNED_UPSTREAM_SHA
from integrations.mastermind_executive_app.gateway import (
    CeoIngressResponse, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK, TRANSPORT_SENT_UNKNOWN,
)

COMMAND = "coo-cycle:JOB-ROOT-001:dispatch:JOB-CHILD-002:attempt:1"


def selected():
    return ExecutiveSelectedChild(ExecutiveChildSelection(
        root_job_id="JOB-ROOT-001", parent_job_id="JOB-ROOT-001",
        job_id="JOB-CHILD-002", plan_attempt_id="PLAN-ATTEMPT-001",
        plan_digest="d" * 64, plan_step_id="PLAN-STEP-001",
        repair_round=0, expected_current_attempt_id=None,
    ), 1)


def host_fixture(**changes):
    target = dict(profile_id="default", session_id="sess-1", principal_id="fixture-principal",
                  instance_id="fixture-instance", authority_epoch=1, revision=0,
                  execution_generation=0)
    host = AuthenticatedHostFixture(
        native_target_json=canonical_json(target),
        principal_context=PrincipalAdmissionContext(
            "WS:H24-CONFORMANCE", "a" * 64, "mission:h24", "b" * 64),
        target_digest="c" * 64, registration_lease="c28-fixture-lease-1",
    )
    return replace(host, **changes)


def envelope(child=None, **changes):
    child = selected() if child is None else child
    body = dict(
        schema=c28.SELECTED_CHILD_SCHEMA, state="ACTIVE", reason=None,
        command_id=child.command_id, job_id=child.selection.job_id,
        root_job_id=child.selection.root_job_id, attempt_id="ATT-001",
        attempt_number=child.attempt_ordinal, attempt_status="CLAIMED",
        job_status="RUNNING", live_submit=True,
    )
    body.update(changes)
    return body


def request(action="selected_child_submit", **changes):
    return dict(action=action, command=COMMAND, **changes)


class RecordingTransport:
    def __init__(self, response=None, error=None):
        self.response = envelope() if response is None else response
        self.error = error
        self.calls = []

    def _call(self, action, command):
        self.calls.append((action, command))
        if self.error is not None:
            raise self.error
        return self.response

    def submit_selected_child(self, command):
        return self._call("submit", command)

    def selected_child_status(self, command):
        return self._call("status", command)


def probe_for(response=None, *, original=None, error=None, host=None, observe=None,
              child=None, original_attempt=None):
    child = selected() if child is None else child
    host = host_fixture() if host is None else host
    response = envelope(child) if response is None else response
    original = copy.deepcopy(response) if original is None and type(response) is dict else original
    original = envelope(child) if original is None else original
    transport = RecordingTransport(response, error=error)
    reads = []

    def read(command):
        reads.append(command)
        return original

    probe = ContractProbe(child, host, transport, observe or (lambda: host),
                          read, original_attempt)
    return probe, transport, reads


@pytest.mark.parametrize("action", ["selected_child_submit", "selected_child_status"])
@pytest.mark.parametrize("wire", [False, True])
def test_valid_submit_status_exact_original_and_deterministic_report(action, wire):
    response = envelope()
    probe, transport, reads = probe_for(json.dumps(response) if wire else response)
    first = probe.run(request(action))
    second = probe.run(request(action))
    assert first.outcome == "CONFORMANT"
    assert first.to_json() == second.to_json()
    assert first.attempt_id == "ATT-001"
    assert reads == [COMMAND, COMMAND]
    assert transport.calls == [(action.removeprefix("selected_child_"), COMMAND)] * 2
    assert first.as_dict()["production_execution_proven"] is False
    assert first.as_dict()["evidence"] == "SOURCE_ONLY"


def test_original_completed_result_is_compared_not_synthesized():
    body = envelope(state="COMPLETED", attempt_status="COMPLETED", job_status="COMPLETED",
                    result_status="RESULT", role="implementation",
                    operation_key="op-fixture", session_ref="session-fixture",
                    result_envelope_digest="e" * 64, terminal_evidence_digest="f" * 64)
    probe, _, _ = probe_for(body)
    result = probe.run(request("selected_child_status"))
    assert result.outcome == "CONFORMANT"
    assert result.as_dict()["envelope"] == body


def test_original_can_advance_without_retargeting_same_attempt():
    probe, _, _ = probe_for(envelope(), original=envelope(
        state="COMPLETED", attempt_status="COMPLETED", job_status="COMPLETED",
        result_status="RESULT", result_envelope_digest="e" * 64,
        terminal_evidence_digest="f" * 64))
    result = probe.run(request())
    assert result.outcome == "CONFORMANT"
    assert result.as_dict()["envelope"]["state"] == "COMPLETED"


@pytest.mark.parametrize("value", [[], {}, None, True, 1, 1.0])
def test_malformed_action_is_normal_refusal(value):
    probe, transport, reads = probe_for()
    result = probe.run(dict(action=value, command=COMMAND))
    assert result.outcome == "REFUSED"
    assert transport.calls == reads == []


@pytest.mark.parametrize("extra", [
    "work_ref", "principal", "root_job_id", "job_id", "attempt_id",
    "idempotency_key", "replay_of", "target_digest", "schema", "version",
])
def test_extra_request_fields_never_reach_transport(extra):
    probe, transport, _ = probe_for()
    result = probe.run({**request(), extra: "forged"})
    assert result.outcome == "REFUSED"
    assert result.reason == "REQUEST_FIELDS"
    assert transport.calls == []


@pytest.mark.parametrize("value", [
    {}, [], None, True, 0, '[]', 'null', '{', '{"action":',
    b"\xff", '{"action":"selected_child_submit"}',
    '{"action":"selected_child_submit","command":null}',
    '{"action":"cancel","command":"unused"}',
])
def test_non_object_missing_invalid_or_legacy_arguments(value):
    probe, transport, _ = probe_for()
    assert probe.run(value).outcome == "REFUSED"
    assert transport.calls == []


def test_tool_name_and_foreign_command_refuse_without_reselection():
    probe, transport, _ = probe_for()
    assert probe.run(request(), tool_name="delegate_task").outcome == "REFUSED"
    assert probe.run({**request(), "command": COMMAND[:-1] + "2"}).outcome == "REFUSED"
    assert transport.calls == []


def test_reordered_json_has_identical_report():
    probe, _, _ = probe_for()
    first = '{"action":"selected_child_submit","command":' + json.dumps(COMMAND) + '}'
    second = '{"command":' + json.dumps(COMMAND) + ',"action":"selected_child_submit"}'
    assert probe.run(first).to_json() == probe.run(second).to_json()


@pytest.mark.parametrize("duplicate", [
    '"action":"selected_child_submit","action":"selected_child_submit"',
    '"action":"selected_child_submit","act\\u0069on":"selected_child_status"',
])
def test_duplicate_request_keys_even_equal_or_escaped_are_refused(duplicate):
    probe, transport, _ = probe_for()
    result = probe.run("{" + duplicate + ',"command":' + json.dumps(COMMAND) + "}")
    assert result.reason == "JSON_DUPLICATE_KEY"
    assert result.outcome == "REFUSED"
    assert transport.calls == []


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_request_and_response(token):
    probe, transport, _ = probe_for()
    result = probe.run('{"action":' + token + ',"command":' + json.dumps(COMMAND) + '}')
    assert result.outcome == "REFUSED"
    assert result.reason == "JSON_NONFINITE"
    assert transport.calls == []
    bad = json.dumps(envelope()).replace('"reason": null', '"reason": ' + token)
    probe, transport, reads = probe_for(bad)
    assert probe.run(request()).outcome == "EFFECT_UNKNOWN"
    assert transport.calls == [("submit", COMMAND)]
    assert reads == []


def test_duplicate_response_keys_are_uncertain_after_one_send():
    body = json.dumps(envelope()).replace('"state": "ACTIVE"', '"state":"ACTIVE","state":"ACTIVE"')
    probe, transport, reads = probe_for(body)
    result = probe.run(request())
    assert (result.outcome, result.reason) == ("EFFECT_UNKNOWN", "JSON_DUPLICATE_KEY")
    assert transport.calls == [("submit", COMMAND)]
    assert reads == []


@pytest.mark.parametrize("raw", [
    {"x": (1, 2)}, {1: "value"}, {"x": float("inf")}, {"x": "\ud800"},
])
def test_python_coercions_and_invalid_unicode_are_rejected(raw):
    with pytest.raises(ProbeViolation):
        strict_object(raw, limit=100)


def test_exact_types_reject_python_subclasses():
    class Text(str):
        pass
    class Object(dict):
        pass
    for value in (Object(request()), {**request(), "command": Text(COMMAND)}):
        probe, transport, _ = probe_for()
        assert probe.run(value).outcome == "REFUSED"
        assert transport.calls == []


def test_utf8_byte_limits_and_bounded_nesting():
    raw = canonical_json({"x": "é" * 20})
    size = len(raw.encode("utf-8"))
    assert strict_object(raw, limit=size) == {"x": "é" * 20}
    with pytest.raises(ProbeViolation, match="JSON_TOO_LARGE"):
        strict_object(raw, limit=size - 1)
    deep = '{"x":' + '[' * 40 + '0' + ']' * 40 + '}'
    with pytest.raises(ProbeViolation, match="JSON_COMPLEXITY"):
        strict_object(deep, limit=1024)
    for data, limit in ((request(), MAX_REQUEST_BYTES), (envelope(), MAX_RESPONSE_BYTES)):
        data["reason" if "schema" in data else "command"] = "é" * limit
        with pytest.raises(ProbeViolation, match="JSON_TOO_LARGE"):
            strict_object(data, limit=limit)


@pytest.mark.parametrize("field,value", [
    ("schema", "mastermind.hermes_delegate.selected_child/v2"),
    ("state", []), ("state", "STARTED"), ("reason", {}),
    ("command_id", COMMAND[:-1] + "2"), ("job_id", "JOB-WRONG"),
    ("root_job_id", "JOB-WRONG"), ("attempt_number", True), ("attempt_number", 2),
    ("attempt_id", 7), ("attempt_status", "UNKNOWN_ENUM"), ("attempt_status", True),
    ("job_status", "UNKNOWN_ENUM"), ("live_submit", 1),
    ("result_envelope_digest", "G" * 64), ("terminal_evidence_digest", "a" * 63),
    ("target_digest", "c" * 64), ("unexpected", None),
])
def test_bad_envelope_after_possible_send_retains_original_identity(field, value):
    probe, transport, reads = probe_for({**envelope(), field: value}, original=envelope())
    result = probe.run(request())
    assert result.outcome == "EFFECT_UNKNOWN"
    assert (result.command_id, result.job_id) == (COMMAND, "JOB-CHILD-002")
    assert result.attempt_id is None
    assert result.envelope_json is None
    assert transport.calls == [("submit", COMMAND)]
    assert reads == []


@pytest.mark.parametrize("field", sorted([
    "schema", "state", "reason", "command_id", "job_id", "attempt_id",
    "attempt_status", "job_status", "live_submit",
]))
def test_missing_response_field_is_uncertain(field):
    body = envelope()
    del body[field]
    probe, _, _ = probe_for(body, original=envelope())
    assert probe.run(request()).outcome == "EFFECT_UNKNOWN"


@pytest.mark.parametrize("state,live", [
    ("NOT_CLAIMED", False), ("REFUSED", False),
    ("EFFECT_UNKNOWN", None), ("UNAVAILABLE", None),
])
def test_three_valued_effect_semantics_remain_canonical(state, live):
    body = envelope(state=state, attempt_id=None, attempt_status=None,
                    job_status=None, live_submit=live)
    probe, _, _ = probe_for(body)
    assert probe.run(request()).outcome == "CONFORMANT"
    probe, _, _ = probe_for({**body, "live_submit": True}, original=body)
    assert probe.run(request()).outcome == "EFFECT_UNKNOWN"


@pytest.mark.parametrize("delta", [
    {"attempt_id": "ATT-OTHER"},
    {"command_id": COMMAND[:-1] + "2"}, {"job_id": "JOB-WRONG"},
    {"root_job_id": "JOB-WRONG"},
    {"result_envelope_digest": "f" * 64},
])
def test_wrong_original_owner_readback_never_validates_response(delta):
    body = envelope(state="COMPLETED", attempt_status="COMPLETED", job_status="COMPLETED",
                    result_status="RESULT", result_envelope_digest="e" * 64,
                    terminal_evidence_digest="f" * 64)
    probe, transport, reads = probe_for(body, original={**body, **delta})
    result = probe.run(request())
    assert result.outcome == "EFFECT_UNKNOWN"
    assert result.envelope_json is None
    assert transport.calls == [("submit", COMMAND)] and reads == [COMMAND]


@pytest.mark.parametrize("action", ["selected_child_submit", "selected_child_status"])
@pytest.mark.parametrize("original", [
    envelope(), envelope(state="FAILED", attempt_status="FAILED", job_status="FAILED"),
])
def test_terminal_response_cannot_outrun_or_contradict_original(action, original):
    body = envelope(state="COMPLETED", attempt_status="COMPLETED", job_status="COMPLETED",
                    result_status="RESULT", result_envelope_digest="e" * 64,
                    terminal_evidence_digest="f" * 64)
    probe, transport, reads = probe_for(body, original=original)
    result = probe.run(request(action))
    assert result.outcome == ("EFFECT_UNKNOWN" if action.endswith("submit") else "UNAVAILABLE")
    assert result.reason == "ORIGINAL_STATE_MISMATCH" and result.envelope_json is None
    assert len(transport.calls) == 1 and reads == [COMMAND]


def test_completed_without_sealed_result_and_active_with_terminal_status_are_invalid():
    for body in (
        envelope(state="COMPLETED", attempt_status="COMPLETED", job_status="COMPLETED"),
        envelope(attempt_status="COMPLETED", job_status="COMPLETED"),
    ):
        probe, transport, reads = probe_for(body, original=body)
        assert probe.run(request()).outcome == "EFFECT_UNKNOWN"
        assert transport.calls == [("submit", COMMAND)] and reads == []


def test_injected_contract_exception_text_is_not_disclosed():
    from integrations.hermes_delegate.schema import SubmissionError
    for error in (ProbeViolation("private-authority-material"),
                  SubmissionError("private-authority-material")):
        probe, transport, _ = probe_for(error=error)
        result = probe.run(request())
        assert result.outcome == "EFFECT_UNKNOWN"
        assert result.reason == "CONTRACT_INVALID"
        assert "private-authority-material" not in result.to_json()
        assert len(transport.calls) == 1


def test_coroutine_transport_result_is_closed_and_retains_uncertainty():
    async def response():
        return envelope()
    value = response()
    probe, transport, reads = probe_for(value)
    result = probe.run(request())
    assert result.outcome == "EFFECT_UNKNOWN"
    assert result.reason == "SYNCHRONOUS_RESULT_REQUIRED"
    assert value.cr_frame is None
    assert len(transport.calls) == 1 and reads == []


def test_unavailable_status_after_lost_submit_never_clears_original_uncertainty():
    probe, transport, reads = probe_for(error=EOFError("lost"), original_attempt="ATT-001")
    lost = probe.run(request())
    observed = probe.run(request("selected_child_status"))
    assert (lost.outcome, observed.outcome) == ("EFFECT_UNKNOWN", "UNAVAILABLE")
    assert (lost.command_id, lost.attempt_id) == (observed.command_id, observed.attempt_id)
    assert transport.calls == [("submit", COMMAND), ("status", COMMAND)] and reads == []


def test_known_original_attempt_is_not_replaced_by_later_job_attempt():
    probe, _, _ = probe_for(envelope(attempt_id="ATT-002"),
                             original_attempt="ATT-001")
    result = probe.run(request("selected_child_status"))
    assert result.outcome == "UNAVAILABLE"
    assert result.attempt_id == "ATT-001"


@pytest.mark.parametrize("error", [
    TimeoutError("private timeout"), EOFError("private EOF"),
    ConnectionResetError("private disconnect"), asyncio.CancelledError("private cancellation"),
])
@pytest.mark.parametrize("action", ["selected_child_submit", "selected_child_status"])
def test_lost_response_is_uncertain_or_unavailable_never_replayed(error, action):
    probe, transport, reads = probe_for(error=error, original_attempt="ATT-001")
    result = probe.run(request(action))
    assert result.outcome == ("EFFECT_UNKNOWN" if action.endswith("submit") else "UNAVAILABLE")
    assert len(transport.calls) == 1 and reads == []
    assert result.attempt_id == "ATT-001"
    assert "private" not in result.to_json()


@pytest.mark.parametrize("action", ["selected_child_submit", "selected_child_status"])
def test_proven_not_sent_requires_actual_transport_receipt(action):
    receipt = CeoIngressResponse(TRANSPORT_NOT_SENT, detail="private detail")
    probe, transport, reads = probe_for(receipt)
    result = probe.run(request(action))
    assert result.outcome == ("REFUSED" if action.endswith("submit") else "UNAVAILABLE")
    assert result.reason == "TRANSPORT_NOT_SENT"
    assert result.transport_called and not result.modifying_send_possible
    assert len(transport.calls) == 1 and reads == []
    assert "private detail" not in result.to_json()


@pytest.mark.parametrize("receipt", [
    {"transport": TRANSPORT_NOT_SENT},
    CeoIngressResponse(TRANSPORT_SENT_UNKNOWN),
    CeoIngressResponse(TRANSPORT_NOT_SENT, result=envelope()),
    CeoIngressResponse(TRANSPORT_SENT_OK, ok=False, error={"private": "message"}),
])
def test_unproven_not_sent_cannot_clear_uncertainty(receipt):
    probe, transport, reads = probe_for(receipt)
    assert probe.run(request()).outcome == "EFFECT_UNKNOWN"
    assert len(transport.calls) == 1 and reads == []


def test_actual_sent_ok_transport_receipt_is_unwrapped():
    probe, _, _ = probe_for(CeoIngressResponse(TRANSPORT_SENT_OK, ok=True, result=envelope()))
    assert probe.run(request()).outcome == "CONFORMANT"


def stale_host(host, kind):
    if kind == "session":
        target = json.loads(host.native_target_json)
        target["revision"] += 1
        return replace(host, native_target_json=canonical_json(target))
    if kind == "lease":
        return replace(host, registration_lease="another-lease")
    if kind == "lease_expired":
        return replace(host, lease_current=False)
    if kind == "source":
        return replace(host, source=replace(host.source, mastermind_sha="0" * 40))
    if kind == "catalog_source":
        return replace(host, source=replace(host.source, catalog_source_sha="0" * 40))
    if kind == "catalog":
        return replace(host, source=replace(host.source, catalog_sha256="0" * 64))
    if kind == "upstream":
        return replace(host, source=replace(host.source, upstream_sha="0" * 40))
    if kind == "digest":
        return replace(host, target_digest="0" * 64)
    if kind == "principal":
        return replace(host, principal_context=replace(
            host.principal_context, authority_generation_digest="0" * 64))
    return replace(host, authenticated=False)


@pytest.mark.parametrize("kind", [
    "session", "lease", "lease_expired", "source", "catalog_source",
    "catalog", "upstream", "digest", "principal", "auth",
])
@pytest.mark.parametrize("phase", ["before", "after_send", "after_readback"])
def test_stale_host_generation_never_retakes_target(kind, phase):
    host = host_fixture()
    stale = stale_host(host, kind)
    values = iter({"before": [stale], "after_send": [host, stale],
                   "after_readback": [host, host, stale]}[phase])
    probe, transport, reads = probe_for(host=host, observe=lambda: next(values))
    result = probe.run(request())
    assert result.outcome == ("REFUSED" if phase == "before" else "EFFECT_UNKNOWN")
    assert len(transport.calls) == (0 if phase == "before" else 1)
    assert len(reads) == (1 if phase == "after_readback" else 0)
    assert result.envelope_json is None


def test_tool_catalog_is_pinned_not_recomputed_as_new_expectation(monkeypatch):
    assert hashlib.sha256(canonical_json(c28.NATIVE_TOOL_SCHEMA).encode()).hexdigest() == TOOL_CATALOG_SHA256
    probe, transport, _ = probe_for()
    monkeypatch.setitem(c28.NATIVE_TOOL_SCHEMA, "name", "replacement-tool")
    assert probe.run(request()).reason == "SOURCE_PIN_MISMATCH"
    assert transport.calls == []


def test_replaced_catalog_object_cannot_hide_behind_a_cached_import(monkeypatch):
    probe, transport, _ = probe_for()
    changed = copy.deepcopy(c28.NATIVE_TOOL_SCHEMA)
    changed["parameters"]["additionalProperties"] = True
    monkeypatch.setattr(c28, "NATIVE_TOOL_SCHEMA", changed)
    assert probe.run(request()).reason == "SOURCE_PIN_MISMATCH"
    assert transport.calls == []


def test_admission_closed_status_unchanged_and_submit_refused():
    host = host_fixture()
    closed = replace(host, admission_open=False)
    probe, transport, reads = probe_for(host=host, observe=lambda: closed)
    assert probe.run(request()).reason == "ADMISSION_CLOSED"
    first = probe.run(request("selected_child_status"))
    second = probe.run(request("selected_child_status"))
    assert first.outcome == "CONFORMANT"
    assert first.to_json() == second.to_json()
    assert transport.calls == [("status", COMMAND)] * 2
    assert reads == [COMMAND] * 2


def test_admission_closing_after_send_does_not_invent_no_effect():
    host = host_fixture()
    values = iter([host, replace(host, admission_open=False), replace(host, admission_open=False)])
    probe, transport, _ = probe_for(host=host, observe=lambda: next(values))
    assert probe.run(request()).outcome == "CONFORMANT"
    assert transport.calls == [("submit", COMMAND)]


@pytest.mark.parametrize("counter", ["authority_epoch", "revision", "execution_generation"])
def test_native_session_target_uses_actual_strict_counter_schema(counter):
    target = json.loads(host_fixture().native_target_json)
    target[counter] = True
    with pytest.raises(ProbeViolation, match="NATIVE_TARGET_INVALID"):
        host_fixture(native_target_json=json.dumps(target))


def test_immutable_fixture_and_detached_arguments():
    host = host_fixture()
    with pytest.raises(FrozenInstanceError):
        host.target_digest = "0" * 64
    with pytest.raises(FrozenInstanceError):
        host.source.mastermind_sha = "0" * 40
    with pytest.raises(FrozenInstanceError):
        selected().attempt_ordinal = 2
    raw = request()
    detached = strict_object(raw, limit=MAX_REQUEST_BYTES)
    raw["command"] = "forged"
    assert detached["command"] == COMMAND


@pytest.mark.parametrize("value", [True, object(), None])
def test_invalid_host_observer_is_not_truthy_authority(value):
    probe, transport, _ = probe_for(observe=lambda: value)
    assert probe.run(request()).outcome == "REFUSED"
    assert transport.calls == []


def test_async_guard_is_not_completed_authentication():
    async def observe():
        return host_fixture()
    probe, transport, _ = probe_for(observe=observe)
    assert probe.run(request()).reason == "HOST_OBSERVATION_INVALID"
    assert transport.calls == []


# Real C17 receiving owner, with its existing disposable storage and fake provider.
@pytest.fixture
def c17(monkeypatch):
    # Its incumbent helpers use both package and historical bare test imports.
    monkeypatch.syspath_prepend(str(Path(c28.__file__).resolve().parents[2] / "tests"))
    from tests import test_hermes_selected_child_dispatch as fixture
    return fixture


def composition(service, work, *, guard=lambda: None):
    from tests.test_hermes_selected_child_dispatch import _selection
    return ExecutiveSelectedChildComposition(
        service=service, runtime=service.runtime,
        children=(ExecutiveSelectedChild(_selection(work), 1),),
        loop=asyncio.get_running_loop(),
        authority=service._selected_child_fixture[0],
        context=service._selected_child_fixture[3]["context"],
        capability_profile_digest=service._selected_child_fixture[3]["capability_profile_digest"],
        receiving_request_guard=guard,
    )


class OwnerTransport:
    def __init__(self, owner):
        self.owner = owner
        self.submit_calls = 0
        self.status_calls = 0
        self.lose_response = False

    def submit_selected_child(self, command):
        self.submit_calls += 1
        value = self.owner.submit(command)
        if self.lose_response:
            raise EOFError("disconnect after receiving claim")
        return value

    def selected_child_status(self, command):
        self.status_calls += 1
        return self.owner.status(command)


def owner_probe(owner, transport, *, host=None):
    host = host_fixture() if host is None else host
    return ContractProbe(owner.children[0], host, transport, lambda: host, owner.status)


def test_concurrent_identical_commands_use_one_real_receiving_claim(tmp_path, c17):

    async def run():
        import tempfile
        with tempfile.TemporaryDirectory(prefix="h24-claim-", dir="/tmp") as sockets:
            async with c17._selected_child_service(
                    tmp_path, Path(sockets), name="h24-concurrent",
                    supervisor_factory=c17._ContendedAmbiguousSupervisor,
            ) as (service, supervisor, root, received, gate):
                work = c17._admit_work_child(service, root)
                owner = composition(service, work)
                transport = OwnerTransport(owner)
                probe = owner_probe(owner, transport)
                arguments = dict(action="selected_child_submit", command=owner.children[0].command_id)
                # Both callers must have observed NOT_CLAIMED and qualified
                # before either enters the REAL receiving-owner claim. This
                # fixture barrier is not a probe lock or a fake claim owner.
                dispatch = service.dispatch_selected_child
                status = service.selected_child_status
                observations = []
                entered_dispatch = []
                both_dispatches = asyncio.Event()

                async def observe_original(**kwargs):
                    result = await status(**kwargs)
                    observations.append((kwargs["command_id"], result["state"]))
                    return result

                async def compete_at_claim(**kwargs):
                    entered_dispatch.append(kwargs["command_id"])
                    if len(entered_dispatch) == 2:
                        both_dispatches.set()
                    await both_dispatches.wait()
                    return await dispatch(**kwargs)

                service.selected_child_status = observe_original
                service.dispatch_selected_child = compete_at_claim
                first = asyncio.create_task(asyncio.to_thread(probe.run, arguments))
                second = asyncio.create_task(asyncio.to_thread(probe.run, arguments))
                await asyncio.wait_for(both_dispatches.wait(), timeout=10)
                await asyncio.wait_for(supervisor.entered.wait(), timeout=10)
                assert transport.submit_calls == 2
                assert observations[:2] == [(arguments["command"], "NOT_CLAIMED")] * 2
                assert entered_dispatch == [arguments["command"]] * 2
                supervisor.release.set()
                results = await asyncio.wait_for(asyncio.gather(first, second), timeout=10)
                assert all(r.outcome == "CONFORMANT" for r in results), results
                assert {r.as_dict()["envelope"]["state"] for r in results} == {"EFFECT_UNKNOWN"}
                claims = c17._claim_events(service.runtime, work.job_id)
                assert len(claims) == 1
                assert supervisor.start_calls == 1
                assert {r.attempt_id for r in results} == {claims[0]["attempt_id"]}
                assert service.runtime.jobs.get_job(work.job_id).attempt_count == 1
    asyncio.run(run())


def test_lost_result_recovers_original_and_status_survives_closed_admission(tmp_path, c17):

    async def run():
        import tempfile
        with tempfile.TemporaryDirectory(prefix="h24-recover-", dir="/tmp") as sockets:
            async with c17._selected_child_service(
                    tmp_path, Path(sockets), name="h24-original",
            ) as (service, supervisor, root, received, gate):
                work = c17._admit_work_child(service, root)
                owner = composition(service, work)
                transport = OwnerTransport(owner)
                probe = owner_probe(owner, transport)
                command = owner.children[0].command_id
                transport.lose_response = True
                lost = await asyncio.to_thread(probe.run, dict(action="selected_child_submit", command=command))
                assert lost.outcome == "EFFECT_UNKNOWN" and not lost.original_readback_called
                claims = c17._claim_events(service.runtime, work.job_id)
                assert len(claims) == transport.submit_calls == 1
                attempt = claims[0]["attempt_id"]
                gate.set()
                await c17._settle(service)
                assert [item.attempt_id for item in received] == [attempt]

                def closed_guard():
                    raise AssertionError("fresh admission must not run during original status")

                closed_owner = replace(owner, receiving_request_guard=closed_guard)
                transport.owner = closed_owner
                transport.lose_response = False
                service._service_state = "QUARANTINED"
                closed_host = host_fixture(admission_open=False)
                reader = replace(owner_probe(closed_owner, transport, host=closed_host),
                                 original_attempt_id=attempt)
                status = dict(action="selected_child_status", command=command)
                first = await asyncio.to_thread(reader.run, status)
                second = await asyncio.to_thread(reader.run, status)
                assert first.outcome == "CONFORMANT", first
                assert first.to_json() == second.to_json()
                body = first.as_dict()["envelope"]
                assert body["state"] == "COMPLETED" and body["attempt_id"] == attempt
                assert body["result_status"] == "RESULT"
                assert len(body["result_envelope_digest"]) == 64
                assert len(c17._claim_events(service.runtime, work.job_id)) == 1
                assert transport.submit_calls == 1 and transport.status_calls == 2
                # C17's explicit replay path also observes before the fresh guard.
                replay = await closed_owner.submit_async(command)
                assert replay["attempt_id"] == attempt
                assert len(c17._claim_events(service.runtime, work.job_id)) == 1
    asyncio.run(run())


@pytest.fixture
def pinned_native():
    from integrations.hermes_harness.tests import test_native_tool_registration as fixture
    root = fixture._vendor_root()
    if root is None:
        pytest.skip("MASTERMIND_HERMES_VENDOR_ROOT required for actual pinned native API proof")
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True, timeout=15)
    assert head.stdout.strip() == PINNED_UPSTREAM_SHA
    for path in ("tools/mcp_tool.py", "tools/mcp_tool_health.py", "tools/mcp_tool_handlers.py",
                 "hermes_cli/plugins.py", "tools/registry.py", "registration_lifecycle.py"):
        expected = subprocess.run(["git", "-C", str(root), "show", f"{PINNED_UPSTREAM_SHA}:{path}"],
                                  check=True, capture_output=True, timeout=15).stdout
        assert (root / path).read_bytes() == expected
    return fixture, root, fixture._Upstream(root)


@pytest.mark.parametrize("method", [
    "test_registration_reads_back_through_the_owner_api",
    "test_the_owner_unload_removes_the_entry",
    "test_readback_failure_disposes_only_the_captured_native_lease",
    "test_a_raising_owner_registration_preserves_uncertainty",
])
def test_actual_c28_registration_fixture(pinned_native, method):
    fixture, root, upstream = pinned_native
    case = fixture.NativePluginApiTests(method)
    case.root, case.upstream = root, upstream
    case.setUp()
    try:
        getattr(case, method)()
    finally:
        case.doCleanups()


def test_actual_hermes_disconnect_during_model_tool_call_never_replays(pinned_native):
    from tools.mcp_tool import MCPServerTask
    from tools.mcp_tool_handlers import _track_inflight_rpc, _call_tool_racing_stdio_death

    async def run():
        entered = asyncio.Event()
        calls = []
        server = MCPServerTask("h24-fixture")

        class Session:
            async def call_tool(self, name, *, arguments, **kwargs):
                calls.append((name, copy.deepcopy(arguments)))
                entered.set()
                await asyncio.Event().wait()

        server.session = Session()
        server._config = {"url": "fixture://never-connected"}
        loop = asyncio.get_running_loop()

        async def native_call(command):
            async with server._rpc_lock, _track_inflight_rpc(
                    server, "h24-fixture", "tools/call", retry_safe=False):
                return await _call_tool_racing_stdio_death(
                    server, "h24-fixture", c28.TOOL_NAME,
                    dict(action="selected_child_submit", command=command))

        class Transport(RecordingTransport):
            def submit_selected_child(self, command):
                self.calls.append(("submit", command))
                return asyncio.run_coroutine_threadsafe(native_call(command), loop).result(timeout=10)

        transport = Transport()
        host = host_fixture()
        probe = ContractProbe(selected(), host, transport, lambda: host, lambda _: envelope())
        pending = asyncio.create_task(asyncio.to_thread(probe.run, request()))
        await asyncio.wait_for(entered.wait(), timeout=10)
        assert len(server._inflight_tasks) == 1
        server._fail_inflight_calls("h24 fixture disconnect")
        result = await asyncio.wait_for(pending, timeout=10)
        assert result.outcome == "EFFECT_UNKNOWN"
        assert result.command_id == COMMAND and not result.original_readback_called
        assert len(calls) == len(transport.calls) == 1
        assert server._inflight_tasks == set()
        assert server._reconnecting and server._teardown_race
    asyncio.run(run())
