"""Actual installed binding compiler/registry; host source and provider are inert."""
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry, DSH_NATIVE_CONVERSATION_PROFILE_ID
from control_plane.model_router import ModelRouter
from control_plane.native_conversation_binding import (
    NativeConversationHostComposition, NativeConversationRegistration,
    bind_installed_native_conversation,
)
from tests.test_fresh_conversation import case

ROOT = Path(__file__).resolve().parents[1]
PROFILE = DSH_NATIVE_CONVERSATION_PROFILE_ID
ALIAS = "dsh.native.conversation"


def native_binding_case(tmp_path, monkeypatch, principal=None):
    """Default canonical policy/router and the original temporary Worker registry.

    No policy loader is patched: Runtime, Supervisor and binding consumers must
    agree on the same source. Physical host/provider fixtures remain inert.
    """
    router = ModelRouter.load()
    values = case(tmp_path, principal)
    service, runtime = values[:2]
    alias = router.model_aliases[ALIAS]
    selection = NativeConversationRegistration("native-fixture", "dsh-native", ALIAS, "host-" + "d" * 64, "e" * 64)
    metadata = {key: getattr(alias, key) for key in ("execution_profile_id", "execution_profile_digest",
        "capability_policy_version", "capability_policy_digest")}
    metadata.update(routing_policy_version=router.policy_version,
        harness_binary_digest="c" * 64, harness_version="native-test-only",
        capacity_join=dict(schema="mastermind.executive_capacity_join/v1", host_ref=selection.host_ref,
            capacity_capability_id="native-fixture-only", provider_capacity_schema="mastermind.provider_capacity.v1",
            worker_source_config_digest=selection.worker_source_config_digest))
    runtime.workers.register_worker(selection.worker_id, provider="acp", account_label="fixture-only",
        worker_type="fixture", capabilities=["read"], quota_classes={selection.quota_class: dict(provider="acp",
            model=alias.model, effort=alias.effort, cost_class=alias.cost_class,
            capabilities=list(alias.capabilities), metadata=metadata)})
    live = {"current": True}
    def current():
        if not live["current"]:
            raise ValueError("inert installed source retired")
    source = bind_installed_native_conversation(service, registration=selection, current=current)
    service._fixture_native_binding = SimpleNamespace(source=source, selection=selection,
        router=router, current=current, live=live)
    return values


def test_real_binding_joins_one_original_registration_without_registering_or_dispatching(tmp_path, monkeypatch):
    service, runtime, *_ = native_binding_case(tmp_path, monkeypatch)
    before = runtime.workers.list_workers()
    monkeypatch.setattr(runtime.workers, "register_worker", lambda *a, **k: pytest.fail("binding created another Worker"))
    source = service._fixture_native_binding.source
    value = service._require_current_native_conversation_binding()
    assert value == source.current_binding()
    assert value["operator_provider"] == "acp"
    assert value["operator_execution_profile_id"] == PROFILE
    assert value["operator_eligible_quota_classes"] == ["dsh-native"]
    assert value["operator_harness_armed"] is True
    assert runtime.workers.list_workers() == before
    assert service._native_conversation_binding_source is source


@pytest.mark.parametrize("field,value", [
    ("worker_id", "missing-original"), ("quota_class", "missing-quota"),
    ("model_alias", "coo.operator.native-return"), ("host_ref", "host-" + "f" * 64),
    ("worker_source_config_digest", "f" * 64),
])
def test_binding_refuses_mismatched_original_registration(tmp_path, monkeypatch, field, value):
    service, runtime, *_ = native_binding_case(tmp_path, monkeypatch)
    fixture = service._fixture_native_binding
    service._native_conversation_binding_source = None
    before = runtime.workers.list_workers()
    with pytest.raises((ValueError, KeyError)):
        bind_installed_native_conversation(service,
            registration=dataclasses.replace(fixture.selection, **{field: value}), current=fixture.current)
    assert service._native_conversation_binding_source is None
    assert runtime.workers.list_workers() == before


@pytest.mark.parametrize("drift", ["guard", "runtime", "source", "route", "profile"])
def test_bound_source_withdraws_on_original_owner_or_policy_drift(tmp_path, monkeypatch, drift):
    service, runtime, *_ = native_binding_case(tmp_path, monkeypatch)
    fixture = service._fixture_native_binding
    if drift == "guard":
        fixture.live["current"] = False
    elif drift == "runtime":
        service.runtime = object()
    elif drift == "source":
        service._native_conversation_binding_source = object()
    elif drift == "route":
        monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls: fixture.router))
        fixture.router.model_aliases[ALIAS] = dataclasses.replace(fixture.router.model_aliases[ALIAS], model="different-model")
    else:
        monkeypatch.setattr(ModelRouter, "load", classmethod(lambda cls: fixture.router))
        registry = fixture.router.capability_registry
        registry.profiles[PROFILE] = dataclasses.replace(registry.profiles[PROFILE], enabled=False)
    with pytest.raises((ValueError, RuntimeError)):
        fixture.source.current_binding()


def test_binding_cannot_replace_the_current_source(tmp_path, monkeypatch):
    service, *_ = native_binding_case(tmp_path, monkeypatch)
    fixture = service._fixture_native_binding
    with pytest.raises(ValueError, match="already bound"):
        bind_installed_native_conversation(service, registration=fixture.selection, current=fixture.current)
    assert service._native_conversation_binding_source is fixture.source


def test_nominal_host_composition_rejects_async_or_noncurrent_sources():
    selection = NativeConversationRegistration("native-fixture", "dsh-native", ALIAS, "host-" + "d" * 64, "e" * 64)
    async def asynchronous():
        return None
    class AsyncSource:
        async def __call__(self):
            return None
    for current in (asynchronous, AsyncSource(), object()):
        with pytest.raises(ValueError):
            NativeConversationHostComposition(selection, current)
    with pytest.raises(ValueError):
        NativeConversationHostComposition(SimpleNamespace(**dataclasses.asdict(selection)), lambda: None)
    for value in (True, False, "current", asynchronous()):
        composed = NativeConversationHostComposition(selection, lambda: value)
        with pytest.raises(ValueError):
            composed.require_current()
    NativeConversationHostComposition(selection, lambda: None).require_current()
