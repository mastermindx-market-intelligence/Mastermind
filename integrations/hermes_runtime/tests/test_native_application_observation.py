"""Actual pinned native worker and original APPLICATION adapter, without I/O.

The admitted owner and its immutable response type are explicit fixtures.
They do not qualify Broker behavior, credentials, a provider, or a live Trial.
"""
import copy
from dataclasses import dataclass
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest

from integrations.hermes_application_fabric import client as application
from integrations.hermes_runtime import native_application_observation as leaf
from integrations.hermes_runtime import native_eval_publication as publication
from integrations.hermes_runtime import native_request_observation as observation
from integrations.hermes_runtime import native_transport_observation as transport
from integrations.hermes_runtime.tests.test_native_transport_observation import (
    engine, native, module, run_admission, sdk, success,
)


@dataclass(frozen=True)
class OwnerObservationFixture:
    encoded: str

    @property
    def document(self):
        return json.loads(self.encoded)


def bound_fixture(monkeypatch, agent, *, exact=False, automatic=True, task="task-A", change=None):
    # Exact owner type is fixture-only; the original adapter still performs its
    # actual typed-return, currentness, identity, model and response checks.
    module(monkeypatch, "engine.fabric_inference_client", ApplicationObservation=OwnerObservationFixture)
    binding = object.__new__(application.ApplicationBinding)
    binding.operation_id = "original-operation"
    binding.session_id, binding.turn_id = agent.session_id, "turn-A"
    binding.model = "model-1" if exact or not automatic else None
    binding.requested_model = "model-1" if exact else "host-selection"
    binding.automatic, binding._max_output_tokens = automatic, 128
    binding._authorized = lambda _: True
    calls = []
    def create(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        scope = {"schema": "mastermind.application_route_scope.v1", "pools": ["go"]}
        receipt = {
            "schema": "mastermind.fabric_application_observation.v2",
            "disposition": "terminal", "effect_unknown": False,
            "turn_id": binding.operation_id, "request_id": kwargs["request_id"],
            "routing": {
                "schema": "mastermind.fabric_application_route.v2" if exact else "mastermind.fabric_application_route.v1",
                "requested_model": binding.model, "route_scope": scope,
                "route_scope_digest": transport._hash(scope),
                "selection_digest": "a" * 64, "request_digest": "b" * 64,
                "routed_request_digest": None if exact else "c" * 64,
                "pool": "go", "selected_model": "model-1", "mode": "native",
                "protocol": "chat", "driver": "fixture", "profile": "fixture",
                "source": "fixture", "recipe_digest": None,
                "output_contract": {"mode": "hard_maximum", "max_tokens": 128}},
            "serving_model": "model-1", "usage": {"input_tokens": 11, "output_tokens": 7},
        }
        response = SimpleNamespace(model="model-1", stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="PRIVATE_ANSWER")],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7))
        if change:
            change(binding, receipt, response)
        response.application_observation = OwnerObservationFixture(json.dumps(receipt))
        return response
    owner = SimpleNamespace(_closed=False, _timeout=5, messages=SimpleNamespace(create=create))
    binding._owner = owner
    call = application.NativeCall(agent.session_id, task, "turn-A", "request-A")
    request = {"model": binding.requested_model, "messages": [{"role": "user", "content": "PRIVATE_INPUT"}],
               "max_tokens": 128}
    return SimpleNamespace(binding=binding, call=call, request=request, calls=calls)


def invoke(engine, monkeypatch, *, after=None, before=None, **options):
    seen = {}
    async def handle(ref, row, agent):
        bound = bound_fixture(monkeypatch, agent, **options)
        seen.update(bound=bound, agent=agent)
        if before:
            before(bound, agent)
        with application.call_scope(bound.binding, bound.call):
            result = engine.invoke(agent, bound.request, application.HermesApplicationClient)
        seen["result"] = result
        if after:
            after(result, bound, agent)
        engine.results.execution_result.get()["result"] = {
            "final_response": "PRIVATE_ANSWER", "completed": True, "messages": []}
        return "PRIVATE_ANSWER"
    ref, row, agent, result = run_admission(engine, behavior=handle)
    seen["document"] = engine.authority.pending_results[row["admission_id"]].get(observation.RESULT_KEY)
    return SimpleNamespace(**seen)


@pytest.mark.parametrize("exact", [False, True])
def test_original_worker_detaches_owner_return_before_native_mutation(engine, monkeypatch, exact):
    def mutate(result, *_):
        result.application_observation.routing.request_digest = "f" * 64
        result.application_observation.usage.input_tokens = 999
    out = invoke(engine, monkeypatch, exact=exact, after=mutate)
    value = out.document["transport"]
    assert value["schema"] == transport.APPLICATION_SCHEMA
    assert transport.validate_document(value) == value
    row = value["application_attempts"][0]
    assert row["response"]["owner_request_sha256"] == "b" * 64
    assert row["response"]["usage"]["input_tokens"] == 11
    assert row["request"]["native_identity"]["task_id"] == "task-A"
    assert row["request"]["content_sha256"] != row["response"]["owner_request_sha256"]
    assert row["state"] == "returned" and value["attempts"] == []
    assert value["dispatches"][0]["client_binding"] == "qualified_application"
    assert value["dispatches"][0]["auth_client_check"] == "unavailable"
    assert value["errors"] == [] and len(out.bound.calls) == 1
    assert len(engine.factories) == len(engine.cleanups) == 1
    assert all(value[k] is False for k in ("complete_evaluation", "provider_delivery_proven", "model_identity_verified"))
    raw = json.dumps(out.document)
    assert "PRIVATE_INPUT" not in raw and "PRIVATE_ANSWER" not in raw and "host-selection" not in raw


@pytest.mark.parametrize("options", [{"task": "wrong-task"}, {"automatic": False}])
def test_original_success_with_unbound_or_missing_receipt_stays_successful(engine, monkeypatch, options):
    out = invoke(engine, monkeypatch, **options)
    value = out.document["transport"]
    assert out.result.choices[0].message.content == "PRIVATE_ANSWER"
    assert value["application_attempts"] == []
    assert "application_identity_unavailable" in value["errors"]
    assert len(out.bound.calls) == 1
    assert transport.validate_document(value) == value


@pytest.mark.parametrize("field,value", [
    ("request_id", "hermes:wrong"), ("turn_id", "wrong-operation"), ("serving_model", "wrong-model")
])
def test_original_adapter_rejects_foreign_receipt_without_replay(engine, monkeypatch, field, value):
    seen = []
    def change(binding, receipt, response):
        seen.append(receipt)
        receipt[field] = value
    from integrations.hermes_application_fabric.errors import HermesFabricError
    with pytest.raises(HermesFabricError):
        invoke(engine, monkeypatch, change=change)
    assert len(seen) == 1


def test_shape_failure_does_not_replace_original_result(engine, monkeypatch):
    def change(binding, receipt, response):
        receipt["routing"]["request_digest"] = "malformed"
    out = invoke(engine, monkeypatch, change=change)
    value = out.document["transport"]
    assert out.result.choices[0].message.content == "PRIVATE_ANSWER"
    assert value["application_attempts"][0]["state"] == "returned_unobserved"
    assert value["application_attempts"][0]["response"] is None
    assert value["errors"] == ["application_return_unavailable"]
    assert transport.validate_document(value) == value


def test_original_exception_identity_is_preserved(engine, monkeypatch):
    original_error = KeyboardInterrupt("synthetic original interruption")
    def change(*_):
        raise original_error
    with pytest.raises(KeyboardInterrupt) as caught:
        # Avoid a thread: a BaseException deliberately is not an SDK Exception.
        original_invoke = engine.invoke
        engine.invoke = lambda *args, **kw: original_invoke(*args, threaded=False, **kw)
        invoke(engine, monkeypatch, change=change)
    assert caught.value is original_error


def test_late_seal_does_not_add_return_evidence(engine, monkeypatch):
    seen = {}
    def change(binding, receipt, response):
        scope = observation._current.get()
        with scope.live.event_stream.lock, scope.lock:
            seen.update(scope=scope, before=scope.transport.document())
            scope.closed = True
    out = invoke(engine, monkeypatch, change=change)
    # The explicitly sealed fixture owner cannot later publish a new envelope.
    # Its original returned object is preserved and the in-flight span stays
    # unchanged; late observation does not manufacture a terminal receipt.
    assert out.result.choices[0].message.content == "PRIVATE_ANSWER"
    assert out.document is None
    assert seen["scope"].transport.document() == seen["before"]
    assert seen["before"]["application_attempts"][0]["state"] == "entered"


def test_shared_metadata_limit_keeps_original_result(engine, monkeypatch):
    def before(bound, agent):
        scope = observation._current.get()
        scope.metadata_bytes = observation.MAX_METADATA_BYTES - 1
    out = invoke(engine, monkeypatch, before=before)
    assert out.result.choices[0].message.content == "PRIVATE_ANSWER"
    value = out.document["transport"]
    assert value["overflow"] and value["application_attempts"] == []
    assert len(json.dumps(out.document).encode()) <= observation.MAX_METADATA_BYTES


def test_closed_v4_rejects_cross_kind_identity_auth_and_commitment_changes(engine, monkeypatch):
    out = invoke(engine, monkeypatch)
    base = out.document["transport"]
    for change in (
        lambda v: v["dispatches"][0].update(client_binding="qualified_sync_httpx"),
        lambda v: v["dispatches"][0].update(auth_client_check="matched"),
        lambda v: v["application_attempts"][0]["request"]["native_identity"].update(task_id="other"),
        lambda v: v["application_attempts"][0]["response"].update(owner_routed_request_sha256=None),
        lambda v: v["application_attempts"][0].update(extra=True),
        lambda v: v.update(schema=transport.SCHEMA),
    ):
        value = copy.deepcopy(base)
        change(value)
        with pytest.raises(ValueError):
            transport.validate_document(value)


def test_mixed_original_paths_share_one_graph_and_publication_gate(engine, monkeypatch):
    seen = {}
    async def handle(ref, row, agent):
        bound = bound_fixture(monkeypatch, agent)
        with application.call_scope(bound.binding, bound.call):
            engine.invoke(agent, bound.request, application.HermesApplicationClient)
        engine.invoke(agent, bound.request, lambda: sdk(lambda _: httpx.Response(200, json=success())),
                      request_id="http-request")
        seen["bound"] = bound
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "done"}
        return "done"
    _, row, _, _ = run_admission(engine, behavior=handle)
    doc = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]
    value = doc["transport"]
    assert len(value["application_attempts"]) == len(value["attempts"]) == 1
    assert transport.validate_document(value) == value
    assert {v["client_binding"] for v in value["dispatches"]} == {"qualified_sync_httpx", "qualified_application"}
    # A missing assembly join prevents all request-scalar publication, while
    # timing/process evidence and honest partial provider coverage survive.
    draft = {"execution": {}, "timing": {}, "resources": {},
             "observation_availability": {"coverage": {}}, "_selected_model": "host-selection"}
    marker = {"source": {"release": "a" * 40}}
    publication._wire_observations(draft, {}, doc, marker, None)
    assert draft["observation_availability"]["coverage"]["provider_requests"]["status"] == "PARTIAL"
    assert "model_requested" not in draft["execution"] and "provider" not in draft["execution"]


@pytest.mark.parametrize("mutation", ["converter", "code", "defaults", "binding"])
def test_source_or_binding_drift_cannot_retain_success_evidence(engine, monkeypatch, mutation):
    def change(binding, receipt, response):
        if mutation == "converter":
            monkeypatch.setattr(application, "to_owner_request", lambda *a, **k: {})
        elif mutation == "code":
            original = application.to_owner_request
            monkeypatch.setattr(original, "__code__", (lambda *a, **k: {}).__code__)
        elif mutation == "defaults":
            monkeypatch.setattr(application.to_owner_request, "__defaults__", ("changed",))
        else:
            binding._authorized = lambda _: True
    out = invoke(engine, monkeypatch, change=change)
    assert out.result.choices[0].message.content == "PRIVATE_ANSWER"
    assert len(out.bound.calls) == 1
    row = out.document["transport"]["application_attempts"][0]
    assert row["state"] == "returned_unobserved" and row["response"] is None
    assert "application_return_unavailable" in out.document["transport"]["errors"]


def test_original_authorization_revocation_does_not_return_executable_result(engine, monkeypatch):
    calls = []
    def change(binding, receipt, response):
        calls.append(receipt["request_id"])
        binding._authorized = lambda _: False
    from integrations.hermes_application_fabric.errors import HermesFabricError
    with pytest.raises(HermesFabricError):
        invoke(engine, monkeypatch, change=change)
    assert len(calls) == 1


def test_application_and_httpx_share_attempt_cap(engine, monkeypatch):
    monkeypatch.setattr(transport, "MAX_ATTEMPTS", 1)
    async def handle(ref, row, agent):
        bound = bound_fixture(monkeypatch, agent)
        with application.call_scope(bound.binding, bound.call):
            engine.invoke(agent, bound.request, application.HermesApplicationClient)
        result = engine.invoke(agent, bound.request, lambda: sdk(lambda _: httpx.Response(200, json=success())),
                               request_id="second-request")
        assert result.choices[0].message.content == "PRIVATE_OUTPUT"
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "done"}
        return "done"
    _, row, _, _ = run_admission(engine, behavior=handle)
    value = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]["transport"]
    assert len(value["application_attempts"]) == 1 and value["attempts"] == []
    assert value["overflow"] is True
    assert transport.validate_document(value) == value


@pytest.fixture
def assembled_application_projection(engine, monkeypatch):
    # Actual pinned assembly and dispatch; selected-input delivery below is an
    # explicit projection fixture, not a live admitted EVAL configuration.
    monkeypatch.setattr(engine.lifecycle, "has_hook", lambda _: False)
    monkeypatch.setattr(engine.middleware, "apply_llm_request_middleware",
        lambda payload, **_: SimpleNamespace(payload=payload, original_payload=dict(payload), trace=[]))
    def run(*, exact=True, mixed=False, unbound=None):
        selected = {}
        async def handle(ref, row, agent):
            bound = bound_fixture(monkeypatch, agent, exact=exact)
            if unbound is not None:
                selected["unbound"] = make_unbound_call(monkeypatch, agent, unbound)
                selected["unbound"].returned(selected["unbound"].invoke())
            agent._build_api_kwargs = lambda messages, **_: {
                "model": bound.binding.requested_model, "messages": messages, "max_tokens": 128}
            def assembled(request_id):
                return engine.build(agent, api_messages=copy.deepcopy(bound.request["messages"]),
                    api_request_id=request_id, effective_task_id="task-A", turn_id="turn-A").api_kwargs
            with application.call_scope(bound.binding, bound.call):
                engine.invoke(agent, assembled("request-A"), application.HermesApplicationClient)
            if mixed:
                engine.invoke(agent, assembled("http-request"),
                    lambda: sdk(lambda _: httpx.Response(200, json=success("model-1"))),
                    request_id="http-request")
            selected["provider"] = agent.provider
            engine.results.execution_result.get()["result"] = {
                "final_response": "done", "completed": True, "messages": []}
            return "done"
        _, row, _, _ = run_admission(engine, behavior=handle)
        doc = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]
        assert transport.validate_document(doc["transport"]) == doc["transport"]
        assert not doc["metadata_overflow"] and not doc["transport"]["overflow"]
        from integrations.hermes_runtime.native_eval_inputs import PREVIOUS_RESULT_SCHEMA
        inputs = {"schema": PREVIOUS_RESULT_SCHEMA, "errors": [], "assemblies": [
            {key: event[key] for key in ("agent_session_id", "turn_id", "api_request_id",
                 "api_call_count", "retry_count", "content_sha256")} for event in doc["observations"]]}
        marker = {"source": {"release": "a" * 40, "profile_id": "fixture"},
                  "configuration": {"execution": {"provider": selected["provider"]}}}
        def build(model, *, document=None):
            draft = {"execution": {"model_served": None}, "timing": {}, "resources": {},
                     "randomness": {}, "_selected_model": model,
                     "observation_availability": {"coverage": {}}}
            unavailable = {"execution.model_served": "NOT_OBSERVED"}
            publication._wire_observations(draft, unavailable, document or doc, marker, inputs)
            return draft, unavailable
        return SimpleNamespace(document=doc, build=build, unbound=selected.get("unbound"))
    return run


@pytest.mark.parametrize("exact,mixed,frozen,expected,reason", [
    (True, False, "model-1", "model-1", "NOT_OBSERVED"),
    (True, False, "other-model", None, "OBSERVATION_CONFLICT"),
    (False, False, "host-selection", None, "OBSERVATION_CONFLICT"),
    (True, True, "model-1", None, "NOT_OBSERVED"),
])
def test_serving_label_requires_every_original_qualified_return(
        assembled_application_projection, exact, mixed, frozen, expected, reason):
    out = assembled_application_projection(exact=exact, mixed=mixed)
    draft, unavailable = out.build(frozen)
    assert draft["execution"]["model_served"] == expected
    assert unavailable["execution.model_served"] == reason
    assert draft["execution"].get("model_requested") == (frozen if frozen != "other-model" else None)
    assert draft["observation_availability"]["coverage"]["provider_requests"]["status"] == "PARTIAL"
    value = out.document["transport"]
    assert all(value[k] is False for k in ("complete_evaluation", "provider_delivery_proven", "model_identity_verified"))


@pytest.mark.parametrize("defect", ["assembly", "overflow", "unfinished", "missing_attempt"])
def test_serving_label_cannot_hide_incomplete_call_coverage(assembled_application_projection, defect):
    out = assembled_application_projection()
    doc = copy.deepcopy(out.document)
    if defect == "assembly":
        doc["observations"][0]["content_sha256"] = "e" * 64
    elif defect == "overflow":
        doc["transport"]["overflow"] = True
    elif defect == "unfinished":
        doc["transport"]["application_attempts"][0].update(state="entered", response=None)
    else:
        doc["transport"]["application_attempts"] = []
    draft, unavailable = out.build("model-1", document=doc)
    assert draft["execution"]["model_served"] is None
    assert unavailable["execution.model_served"] == "NOT_OBSERVED"


def make_unbound_call(monkeypatch, agent, kind, *, failure=None):
    """Original transports with only their external I/O edges replaced."""
    if kind == "httpx":
        calls = []
        original_response = httpx.Response(200, json={"private": "UNBOUND_ANSWER"})
        request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions",
            json={"model": "UNBOUND_MODEL", "messages": [
                {"role": "user", "content": "UNBOUND_PRIVATE_INPUT"}], "seed": 987})
        def handler(actual_request):
            assert actual_request is request
            calls.append(actual_request)
            if failure is not None:
                raise failure
            return original_response
        def invoke():
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                return client._send_single_request(request)
        def returned(value):
            assert value is original_response
    else:
        def change(*_):
            if failure is not None:
                raise failure
        bound = bound_fixture(monkeypatch, agent, exact=True, change=change)
        bound.request["messages"][0]["content"] = "UNBOUND_PRIVATE_INPUT"
        calls = bound.calls
        def invoke():
            client = application.HermesApplicationClient()
            try:
                with application.call_scope(bound.binding, bound.call):
                    return client.create(**bound.request)
            finally:
                client.close()
        def returned(value):
            assert value.choices[0].message.content == "PRIVATE_ANSWER"
    return SimpleNamespace(invoke=invoke, calls=calls, returned=returned)


def exercise_unbound(call, failure, invoke=None):
    invoke = call.invoke if invoke is None else invoke
    if failure is None:
        call.returned(invoke())
    else:
        with pytest.raises(KeyboardInterrupt) as caught:
            invoke()
        assert caught.value is failure
    assert len(call.calls) == 1


@pytest.mark.parametrize("kind", ["httpx", "application"])
@pytest.mark.parametrize("raises", [False, True], ids=["returned", "raised"])
@pytest.mark.parametrize("scope_state", [
    "current", "no_scope", "closed", "stale", "guard_error", "classification_error",
])
def test_unbound_original_transport_preserves_outcome_and_scope(
        engine, monkeypatch, kind, raises, scope_state):
    failure = KeyboardInterrupt("UNBOUND_PRIVATE_FAILURE") if raises else None
    seen = {}
    async def handle(ref, row, agent):
        owner = observation._current.get()
        call = make_unbound_call(monkeypatch, agent, kind, failure=failure)
        with monkeypatch.context() as patch:
            token = None
            if scope_state == "no_scope":
                token = observation._current.set(None)
            elif scope_state == "closed":
                patch.setattr(owner, "closed", True)
            elif scope_state == "stale":
                patch.setitem(owner.authority.executing, owner.session_id, owner.generation + 1)
            elif scope_state == "guard_error":
                def unavailable(_):
                    raise RuntimeError("UNBOUND_PRIVATE_OBSERVER_FAILURE")
                patch.setattr(transport.Contribution, "observe_unbound_transport", unavailable, raising=False)
            elif scope_state == "classification_error":
                class BadContext:
                    @property
                    def contribution(self):
                        raise RuntimeError("UNBOUND_PRIVATE_CONTEXT_FAILURE")
                token = transport._dispatch_context.set(BadContext())
            try:
                exercise_unbound(call, failure)
            finally:
                if token is not None:
                    variable = observation._current if scope_state == "no_scope" else transport._dispatch_context
                    variable.reset(token)
        seen["owner"] = owner
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "done"}
        return "done"
    _, row, _, _ = run_admission(engine, behavior=handle)
    value = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]["transport"]
    assert value["errors"] == (["unsupported_dispatch"] if scope_state == "current" else [])
    assert value["calls"] == value["dispatches"] == value["attempts"] == []
    assert value.get("application_attempts", []) == []
    assert transport.validate_document(value) == value
    assert "UNBOUND_" not in json.dumps(value)
    assert seen["owner"].closed


@pytest.mark.parametrize("kind", ["httpx", "application"])
@pytest.mark.parametrize("raises", [False, True], ids=["returned", "raised"])
@pytest.mark.parametrize("context_state", ["foreign_dispatch", "copied_old_scope"])
def test_unbound_transport_cannot_borrow_another_admissions_identity(
        engine, monkeypatch, kind, raises, context_state):
    import contextvars
    old = {}
    async def first(ref, row, agent):
        old.update(scope=observation._current.get(), context=contextvars.copy_context())
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "first"}
        return "first"
    run_admission(engine, behavior=first)
    assert old["scope"].closed
    before = copy.deepcopy(old["scope"].transport.document())
    failure = KeyboardInterrupt("UNBOUND_PRIVATE_FAILURE") if raises else None
    async def second(ref, row, agent):
        current = observation._current.get()
        assert current is not old["scope"]
        call = make_unbound_call(monkeypatch, agent, kind, failure=failure)
        if context_state == "foreign_dispatch":
            token = transport._dispatch_context.set(SimpleNamespace(contribution=old["scope"].transport))
            try:
                exercise_unbound(call, failure)
            finally:
                transport._dispatch_context.reset(token)
        else:
            exercise_unbound(call, failure, lambda: old["context"].run(call.invoke))
        assert old["scope"].transport.document() == before
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "second"}
        return "second"
    _, row, _, _ = run_admission(engine, behavior=second)
    value = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]["transport"]
    assert value["errors"] == (["unsupported_dispatch"] if context_state == "foreign_dispatch" else [])
    assert value["calls"] == value["dispatches"] == value["attempts"] == []
    assert value.get("application_attempts", []) == []
    assert transport.validate_document(value) == value
    assert old["scope"].transport.document() == before


@pytest.mark.parametrize("kind", ["httpx", "application"])
def test_repeated_unbound_calls_keep_one_bounded_gap_without_payload(engine, monkeypatch, kind):
    async def handle(ref, row, agent):
        owner = observation._current.get()
        before = owner.metadata_bytes
        for _ in range(8):
            exercise_unbound(make_unbound_call(monkeypatch, agent, kind), None)
        assert owner.metadata_bytes == before
        assert owner.transport.errors == {"unsupported_dispatch"}
        engine.results.execution_result.get()["result"] = {"completed": True, "messages": [], "final_response": "done"}
        return "done"
    _, row, _, _ = run_admission(engine, behavior=handle)
    value = engine.authority.pending_results[row["admission_id"]][observation.RESULT_KEY]["transport"]
    assert value["errors"] == ["unsupported_dispatch"]
    assert value["calls"] == value["dispatches"] == value["attempts"] == []
    assert value.get("application_attempts", []) == []
    assert "UNBOUND_" not in json.dumps(value)
    assert transport.validate_document(value) == value


@pytest.mark.parametrize("kind", ["httpx", "application"])
def test_unbound_original_call_blocks_subset_scalar_publication(assembled_application_projection, kind):
    out = assembled_application_projection(unbound=kind)
    assert len(out.unbound.calls) == 1
    value = out.document["transport"]
    draft, unavailable = out.build("model-1")
    assert draft["execution"]["model_served"] is None
    assert value["errors"] == ["unsupported_dispatch"]
    assert len(value["calls"]) == len(value["dispatches"]) == len(value["application_attempts"]) == 1
    assert value["attempts"] == []
    assert "model_requested" not in draft["execution"]
    assert "provider" not in draft["execution"]
    assert "native_session_fingerprint" not in draft["execution"]
    assert unavailable["execution.model_served"] == "NOT_OBSERVED"
    assert draft["observation_availability"]["coverage"]["provider_requests"]["status"] == "PARTIAL"
    assert "UNBOUND_" not in json.dumps(value)
    assert all(value[k] is False for k in ("complete_evaluation", "provider_delivery_proven", "model_identity_verified"))
