"""Real ingress/sink custody; host providers are inert and provider-free."""
from __future__ import annotations
import asyncio
import copy
import pytest
from control_plane import executive_ceo_ingress as ingress
from control_plane.executive_runtime import Runtime
from control_plane.executive_inbox import ceo_intent_provenance
from tests.test_executive_ceo_ingress_admission_hook import (
    _strict_v2_frame, _dialogue_source, _OrderingGrounding, _workspace_root,
)
from tests.test_executive_ceo_ingress import GROUNDING_A
from tests.test_executive_os_phase1fc import _register_placement_union, _v3_execution_binding
from test_frontier_selection_custody import _selection


def setup(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    _register_placement_union(runtime)
    frame = _strict_v2_frame()
    frame["request"]["frontier_model_alias"] = "frontier.orchestrator"
    log = []
    def resolver(alias):
        assert alias == "frontier.orchestrator"
        log.append("selection")
        return _selection()
    kwargs = dict(
        runtime=runtime, grounding_provider=_OrderingGrounding([GROUNDING_A], log),
        workspace_root=_workspace_root(tmp_path), service_state="READY",
        ceo_ingress_armed=True, strict_v2_admission=True,
        execution_binding_provider=_v3_execution_binding,
        dialogue_source_provider=lambda *_: _dialogue_source(),
        frontier_selection_provider=resolver,
    )
    return runtime, frame, kwargs, log


def test_real_ingress_selection_is_immutable_and_replay_bypasses_current_providers(tmp_path):
    runtime, frame, kwargs, log = setup(tmp_path)
    def guard(envelope):
        log.append("guard")
        envelope["frontier_model_alias"] = "mutated.alias"
    kwargs["admission_guard"] = guard
    first = asyncio.run(ingress.handle_frame(frame, **kwargs))
    assert log == ["grounding", "selection", "grounding", "selection", "guard"]
    def unavailable(*_):
        raise AssertionError("replay called a fresh-only provider")
    kwargs.update(frontier_selection_provider=unavailable,
                  execution_binding_provider=unavailable,
                  dialogue_source_provider=unavailable, admission_guard=unavailable)
    kwargs["grounding_provider"] = type("Unavailable", (), {"observe": unavailable})()
    replay = asyncio.run(ingress.handle_frame(frame, **kwargs))
    provenance, warning = ceo_intent_provenance(runtime, first["job_id"])
    assert warning is None
    assert provenance["frontier_selection"] == _selection()
    assert replay["duplicate"] is True and replay["job_id"] == first["job_id"]
    assert runtime.attempts.list_attempts() == []


@pytest.mark.parametrize("kind", ["absent", "malformed", "moved", "nonstrict"])
def test_fresh_selection_failure_has_zero_root_effect(tmp_path, kind):
    runtime, frame, kwargs, _ = setup(tmp_path)
    if kind == "absent":
        kwargs["frontier_selection_provider"] = None
    elif kind == "malformed":
        kwargs["frontier_selection_provider"] = lambda _: {"model": "untrusted"}
    elif kind == "moved":
        records = iter([_selection("first-model"), _selection("second-model")])
        kwargs["frontier_selection_provider"] = lambda _: next(records)
    else:
        kwargs["strict_v2_admission"] = False
    with pytest.raises(ingress.CeoIngressError) as refused:
        asyncio.run(ingress.handle_frame(frame, **kwargs))
    expected = {"absent": "backend_unavailable", "malformed": "backend_refused",
                "moved": "operation_conflict", "nonstrict": "invalid_input"}
    assert refused.value.code == expected[kind]
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []


def test_authenticated_app_composition_preserves_selection_to_actual_root(tmp_path, monkeypatch):
    from integrations.mastermind_executive_app import admission
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK, SUBMIT_SCOPE, READ_SCOPE
    from tests.test_mastermind_executive_app_admission import _principal
    runtime, frame, kwargs, _ = setup(tmp_path)
    monkeypatch.setattr(admission, "observe_trusted_grounding", lambda **_: dict(GROUNDING_A))
    sent = []
    class Client:
        async def send_frame(self, socket_path, actual_frame):
            sent.append(copy.deepcopy(actual_frame))
            receipt = await ingress.handle_frame(actual_frame, **kwargs)
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True, result=receipt)
    payload = {**frame["request"], "operation_key": "ceo-selection-app-001"}
    request = admission.AdmissionRequest(
        payload=payload, principal=_principal(scopes=(READ_SCOPE, SUBMIT_SCOPE)),
        ceo_ingress_socket_path=tmp_path / "inert.sock", mastermind_root=tmp_path,
        macro_root_flag=None, environ={}, client=Client(),
    )
    result = asyncio.run(admission.compose_admission(request))
    assert result.status == admission.STATUS_ACCEPTED
    provenance, warning = ceo_intent_provenance(runtime, result.receipt["job_id"])
    assert warning is None and provenance["frontier_selection"] == _selection()
    assert sent[0]["request"]["frontier_model_alias"] == "frontier.orchestrator"
    assert "operation_key" not in sent[0]["request"]
    assert result.receipt["dispatched"] is False
    assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []
