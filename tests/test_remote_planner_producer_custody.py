"""Retained planner custody across real receipt/broker/proxy/native owners.

Native process and network I/O are inert fixtures. Runtime/COO tests use their
own disposable store; these tests neither enable the held Claude profile nor
claim installed planner admission, credentials or provider execution.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
import os

import pytest

from control_plane.claude_operator_adapter import ClaudeOperatorAdapter
from control_plane.claude_operator_helper_protocol import native_plan_contract_for_version
from control_plane.executive_orchestration_principal import OSProcessCredentialObservation
from control_plane.executive_orchestration_result import PLAN_SCHEMA_V5, canonical_digest
from control_plane.executive_worker_broker import BrokerProtocolError, RemoteBrokerError, WorkerBrokerError
from control_plane.operator_harness_contract import OperationId, TurnRef, compare_launch
from control_plane.operator_harness_wire import to_wire
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_RECEIPT_SCHEMA, MATERIALIZATION_RECEIPT_SCHEMA_V2,
    OperatorMaterializationReceiptError, build_operator_materialization_receipt,
    canonical_json_bytes, load_operator_materialization_receipt,
    persist_operator_materialization_receipt, planner_producer_selection,
    read_operator_materialization_receipt,
)
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from control_plane.remote_worker_transport import payload_retargets_authority
from test_claude_operator_adapter import configured
from test_executive_operator_broker import _fixture, _materialization_payload, _request
from test_operator_materialization_receipt import _inputs, _receipt


def selection(*, attempt="attempt", job="JOB-PLANNER", root="JOB-ROOT", coordinator="JOB-COORDINATOR"):
    binding = {
        "schema_version": "mastermind.planner_producer_binding/v1",
        "root_job_id": root, "coordinator_job_id": coordinator,
        "planner_job_id": job, "plan_schema_version": PLAN_SCHEMA_V5,
        "native_result_contract": native_plan_contract_for_version(PLAN_SCHEMA_V5),
        "execution_binding_digest": "e" * 64,
    }
    return {"job_id": job, "attempt_id": attempt,
            "planner_producer_binding": binding,
            "planner_producer_binding_digest": canonical_digest(binding)}


def versioned_receipt(selected=None):
    values = _inputs()
    values.pop("expected_provider_session_id")
    selected = selected or selection(attempt=values["attempt_id"])
    return build_operator_materialization_receipt(
        **values, planner_producer=selected,
        observed_planner_contract=selected["planner_producer_binding"]["native_result_contract"])


def test_v2_receipt_retains_custody_while_v1_bytes_stay_exact(tmp_path):
    legacy = _receipt()
    assert legacy.schema == MATERIALIZATION_RECEIPT_SCHEMA
    assert "planner_producer" not in legacy.to_dict()
    legacy_bytes = canonical_json_bytes(legacy.to_dict())
    assert canonical_json_bytes(load_operator_materialization_receipt(legacy_bytes).to_dict()) == legacy_bytes
    current = versioned_receipt()
    assert current.schema == MATERIALIZATION_RECEIPT_SCHEMA_V2
    encoded = canonical_json_bytes(current.to_dict())
    assert load_operator_materialization_receipt(encoded) == current
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    persist_operator_materialization_receipt(root, current, expected_owner_uid=os.geteuid())
    assert read_operator_materialization_receipt(root, current.operation_command_id,
        expected_owner_uid=os.geteuid()) == current


@pytest.mark.parametrize("fault", [
    "extra", "missing", "wrong_job", "wrong_attempt", "binding_extra",
    "binding_digest", "native_schema_digest", "wrong_version", "non_v5_nested",
])
def test_closed_selection_rejects_spliced_or_malformed_identity(fault):
    value = selection()
    b = value["planner_producer_binding"]
    if fault == "extra": value["grant"] = True
    elif fault == "missing": value.pop("attempt_id")
    elif fault == "wrong_job": b["planner_job_id"] = "JOB-FOREIGN"
    elif fault == "wrong_attempt": value["attempt_id"] = "ATT-FOREIGN"
    elif fault == "binding_extra": b["authority"] = "WRITE"
    elif fault == "binding_digest": value["planner_producer_binding_digest"] = "a" * 64
    elif fault == "native_schema_digest": b["native_result_contract"]["schema_digest"] = "a" * 64
    elif fault == "wrong_version": b["schema_version"] = "invented/v1"
    else:
        b["plan_schema_version"] = "mastermind.execution_plan/v1"
        b["native_result_contract"] = native_plan_contract_for_version(b["plan_schema_version"])
    if fault != "binding_digest":
        value["planner_producer_binding_digest"] = canonical_digest(b)
    with pytest.raises(OperatorMaterializationReceiptError):
        planner_producer_selection(value, job_id="JOB-PLANNER", attempt_id="attempt")


@pytest.mark.parametrize("fault", ["missing_observation", "wrong_observation", "legacy_schema", "extra_observation"])
def test_v2_receipt_cannot_invent_or_drop_native_observation(fault):
    raw = versioned_receipt().to_dict()
    if fault == "missing_observation": raw.pop("observed_planner_contract")
    elif fault == "wrong_observation": raw["observed_planner_contract"]["schema_digest"] = "a" * 64
    elif fault == "legacy_schema": raw["schema"] = MATERIALIZATION_RECEIPT_SCHEMA
    else: raw["observed_planner_contract"]["configured"] = True
    unsigned = {k: v for k, v in raw.items() if k != "receipt_digest"}
    raw["receipt_digest"] = canonical_digest(unsigned)
    with pytest.raises(OperatorMaterializationReceiptError):
        load_operator_materialization_receipt(canonical_json_bytes(raw))


def test_wrapper_joins_existing_remote_authority_validation():
    identity = {"host_ref": "host-" + "a" * 64, "job_id": "JOB-PLANNER", "attempt_id": "attempt",
                "worker_id": "worker", "operation_id": "attempt"}
    payload = {"planner_producer": selection()}
    assert payload_retargets_authority("ohf-validate", payload, identity) is False
    payload["planner_producer"]["job_id"] = "JOB-OTHER"
    assert payload_retargets_authority("ohf-validate", payload, identity) is True


class LocalBrokerClient:
    """Only transport is inert; execute uses the real closed broker owner."""
    def __init__(self, broker, peer):
        self.broker, self.peer = broker, peer
        self.calls = []
        self.lose_start_reply = False

    def request_sync(self, operation, payload, **options):
        if options.get("before_write") is not None:
            options["before_write"](operation, payload)
        self.calls.append((operation, copy.deepcopy(payload)))
        try:
            result = asyncio.run(self.broker.execute(_request(operation, payload, str(len(self.calls))), peer=self.peer))
        except WorkerBrokerError as exc:
            raise RemoteBrokerError(type(exc).__name__, str(exc)) from exc
        if not result["ok"]:
            raise RemoteBrokerError(result["error"]["code"], result["error"]["message"])
        if operation == "ohf-start" and self.lose_start_reply:
            self.lose_start_reply = False
            raise TimeoutError("fixture lost original initialization reply")
        return result["result"]


def native_chain(configured, tmp_path, *, selected=True):
    original, native, requested, epoch, generation = configured
    broker, peer, broker_profile, _, _ = _fixture(tmp_path / "broker")
    requested = dataclasses.replace(requested, workspace=dataclasses.replace(
        broker_profile.workspace, base_sha=requested.workspace.base_sha))
    broker.policy = dataclasses.replace(broker.policy, worker_id=requested.worker_id,
        provider_home=original.provider_home)
    adapters, received = [], []

    def factory(workspace, loader, profile, *, planner_producer=None):
        assert str(workspace) == requested.workspace.workspace_path and profile == requested
        received.append(copy.deepcopy(planner_producer))
        options = ({} if planner_producer is None else {
            "plan_contract": planner_producer["planner_producer_binding"]["native_result_contract"]["name"]})
        adapter = ClaudeOperatorAdapter(
            binary_path=original.binary_path, provider_home=original.provider_home,
            workspace_root=workspace, worker_id=profile.worker_id,
            expected_harness_version=profile.harness_version,
            expected_config_digest=profile.expected_config_digest,
            network_policy=profile.network_policy, turn_input_loader=loader,
            policy_observer=original.policy_observer, client_factory=lambda *args: native,
            process_identity_observer=original.process_identity_observer,
            base_sha_resolver=original.base_sha_resolver, **options)
        # Only process identity is fixture evidence; native initialization and
        # its returned schema contract run through the actual adapter/observer.
        def credentials(ref):
            process = adapter._state(ref).process
            return OSProcessCredentialObservation(to_wire(process), "fixture-worker", os.geteuid())
        adapter.observe_process_credentials = credentials
        adapters.append(adapter)
        return adapter

    broker.operator_adapter_factory = factory
    client = LocalBrokerClient(broker, peer)
    producer = selection(attempt=epoch.attempt_id) if selected else None
    capabilities = dataclasses.replace(codex_remote_capabilities(), supports_native_resume=False,
                                       supported_optional_operations=())
    def proxy():
        return RemoteOperatorHarnessAdapter(client, turn_input_loader=lambda turn: "bounded planner input",
                                            capabilities=capabilities, planner_producer=producer)
    return broker, native, requested, epoch, generation, producer, client, proxy, adapters, received


def start_proxy(chain, proxy):
    _, _, requested, epoch, generation, *_ = chain
    return proxy.start_session(operation_id=OperationId(f"ohf-op:start:{epoch.attempt_id}"),
                               requested=requested, epoch=epoch, generation=generation)


def test_native_initialized_v5_reaches_digest_bound_receipt(configured, tmp_path):
    chain = native_chain(configured, tmp_path)
    broker, native, requested, epoch, generation, selected, client, make_proxy, adapters, received = chain
    proxy = make_proxy()
    binding = selected["planner_producer_binding"]
    proxy.require_planner_producer(binding)
    with pytest.raises(BrokerProtocolError, match="initialized"):
        proxy.require_planner_producer(binding, generation=generation)
    assert proxy.validate_requested_profile(requested).accepted
    start_proxy(chain, proxy)
    proxy.require_planner_producer(binding, generation=generation)
    assert received == [selected, selected]
    assert native.plan_contract == "executive-plan-v5"
    receipt = broker._operator_run.materialization_receipt
    assert receipt.schema == MATERIALIZATION_RECEIPT_SCHEMA_V2
    assert receipt.planner_producer == selected
    assert receipt.observed_planner_contract == binding["native_result_contract"]
    assert len([m for m, _ in native.calls if m == "initialize"]) == 1
    # A changed configured attribute is not a changed native observation.
    adapters[-1].plan_contract = "executive-plan-v1"
    assert adapters[-1].observed_planner_contract(generation) == binding["native_result_contract"]


@pytest.mark.parametrize("fault", ["old_contract", "wrong_digest"])
def test_failed_native_initialization_stays_unknown_without_useful_turn(configured, tmp_path, fault):
    chain = native_chain(configured, tmp_path)
    broker, native, _, _, _, _, client, make_proxy, *_ = chain
    original = native.request
    def wrong(method, fields, **kwargs):
        result = original(method, fields, **kwargs)
        if method == "initialize":
            result["result_contract"] = (native_plan_contract_for_version("mastermind.execution_plan/v1")
                if fault == "old_contract" else {"name": "executive-plan-v5", "schema_digest": "a" * 64})
        return result
    native.request = wrong
    with pytest.raises(RemoteBrokerError, match="effect is unknown"):
        start_proxy(chain, make_proxy())
    assert broker._quarantined_reason == "operator materialization effect unknown"
    assert all(m != "begin_turn" for m, _ in native.calls)
    with pytest.raises(RemoteBrokerError):
        start_proxy(chain, make_proxy())
    assert len([m for m, _ in native.calls if m == "initialize"]) == 1


def test_exact_replay_and_changed_producer_use_original_materialization(configured, tmp_path):
    chain = native_chain(configured, tmp_path)
    broker, native, requested, epoch, generation, selected, client, make_proxy, *_ = chain
    first = start_proxy(chain, make_proxy())
    assert start_proxy(chain, make_proxy()) == first
    payload = _materialization_payload(requested, epoch, generation)
    changed = selection(root="JOB-FOREIGN-ROOT")
    payload["planner_producer"] = changed
    with pytest.raises(RemoteBrokerError, match="conflicts"):
        client.request_sync("ohf-start", payload)
    status = client.request_sync("ohf-materialization-status", payload)
    assert status["status"] == "CONFLICT" and status["receipt"] is None
    assert len([m for m, _ in native.calls if m == "initialize"]) == 1


@pytest.mark.parametrize("legacy_first", [False, True])
def test_legacy_and_versioned_receipts_cannot_cross_adopt(configured, tmp_path, legacy_first):
    chain = native_chain(configured, tmp_path, selected=not legacy_first)
    _, native, requested, epoch, generation, _, client, make_proxy, *_ = chain
    start_proxy(chain, make_proxy())
    payload = _materialization_payload(requested, epoch, generation)
    if legacy_first: payload["planner_producer"] = selection()
    result = client.request_sync("ohf-materialization-status", payload)
    assert result["status"] == "CONFLICT"
    with pytest.raises(RemoteBrokerError, match="conflicts"):
        client.request_sync("ohf-start", payload)
    assert len([m for m, _ in native.calls if m == "initialize"]) == 1


@pytest.mark.parametrize("lost_reply", [False, True])
def test_recovery_reads_original_initialized_custody_before_first_turn(configured, tmp_path, lost_reply):
    chain = native_chain(configured, tmp_path)
    broker, native, requested, epoch, generation, _, client, make_proxy, *_ = chain
    client.lose_start_reply = lost_reply
    if lost_reply:
        with pytest.raises(TimeoutError): start_proxy(chain, make_proxy())
    else:
        start_proxy(chain, make_proxy())
    recovered = make_proxy()
    recovered.qualify_existing_planner_generation(requested=requested, epoch=epoch, generation=generation)
    turn = TurnRef("turn", epoch.session_epoch_id, generation.process_generation_id, epoch.attempt_id)
    launch = compare_launch(requested, broker._operator_run.adapter.observed_attestation(generation))
    assert recovered.begin_turn(operation_id=OperationId("ohf-op:recover-first-turn:attempt"),
                                turn=turn, generation=generation, launch=launch).acknowledged
    assert len([m for m, _ in native.calls if m == "initialize"]) == 1
    assert len([m for m, _ in native.calls if m == "begin_turn"]) == 1
    assert [op for op, _ in client.calls].count("ohf-materialization-status") == 1


def test_receipt_only_restart_cannot_qualify_live_planner(configured, tmp_path):
    chain = native_chain(configured, tmp_path)
    broker, native, requested, epoch, generation, _, _, make_proxy, *_ = chain
    start_proxy(chain, make_proxy())
    broker._operator_run = None
    recovered = make_proxy()
    with pytest.raises(BrokerProtocolError, match="current initialized custody"):
        recovered.qualify_existing_planner_generation(requested=requested, epoch=epoch, generation=generation)
    assert all(m != "begin_turn" for m, _ in native.calls)
    assert recovered._planner_receipts == {}


def test_foreground_guard_fences_native_initialization_before_transmission(configured, tmp_path):
    chain = native_chain(configured, tmp_path)
    _, native, _, epoch, _, _, client, make_proxy, *_ = chain
    proxy = make_proxy()
    state = {"open": True}
    def guard():
        if not state["open"]: raise ValueError("original source closed")
    proxy.bind_fresh_effect_guard(guard, attempt_id=epoch.attempt_id)
    state["open"] = False
    with pytest.raises(ValueError, match="source closed"):
        start_proxy(chain, proxy)
    assert client.calls == [] and native.calls == []


def runtime_case(tmp_path, monkeypatch, *, native=True, nested=False, clock=None):
    """Real Runtime/COO lineage, with explicit inert Claude admission fixture.

    This mirrors the existing native consumer test's synthetic policy fixture.
    No production policy file is changed; its disabled native lane remains held.
    """
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from control_plane.executive_coo_cycle import CooCycle
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane.executive_runtime import WorkerRegistry
    from control_plane.model_router import ModelRouter
    from control_plane import remote_attempt_transport as rt
    from test_executive_agent_capabilities import _claude_candidate_policy, _write
    from test_executive_operator_supervisor import _PromptSource, _seed_dispatchable_operator_planner
    from test_planner_producer_binding import _VersionedAdapter, _claim
    from test_remote_attempt_transport import _host_binding, _join

    if native:
        router = ModelRouter.load()
        registry = ExecutionCapabilityRegistry.load(_write(tmp_path, _claude_candidate_policy()))
        profile = dataclasses.replace(registry.profiles["operator.claude.readonly.v1"], enabled=True)
        registry = dataclasses.replace(registry, profiles={**registry.profiles, profile.profile_id: profile})
        router.capability_registry = registry
        router.model_aliases = {key: dataclasses.replace(alias,
            capability_policy_version=registry.policy_version, capability_policy_digest=registry.policy_digest)
            for key, alias in router.model_aliases.items()}
        router.model_aliases["coo.operator.readonly"] = dataclasses.replace(
            router.model_aliases["coo.operator.readonly"], provider_alias="claude",
            execution_profile_id=profile.profile_id, execution_profile_digest=profile.profile_digest,
            model="claude-fixture-exact", adapter_id="claude-code")
        monkeypatch.setattr(ModelRouter, "load", lambda *a, **k: router)
        monkeypatch.setattr(ExecutionCapabilityRegistry, "load", lambda *a, **k: registry)

    # Add the trusted host join at the ordinary Worker owner's first creation,
    # never by rewriting the claimed Worker's policy or retained Job binding.
    register = WorkerRegistry.register_worker
    def joined_registration(owner, worker_id, **kwargs):
        if worker_id == "worker-a":
            kwargs = copy.deepcopy(kwargs)
            kwargs["quota_classes"]["codex-coo-operator"]["metadata"]["capacity_join"] = _join()
        return register(owner, worker_id, **kwargs)
    monkeypatch.setattr(WorkerRegistry, "register_worker", joined_registration)
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path / "job", plan_schema_version=PLAN_SCHEMA_V5, routing_capacity=True, clock=clock)
    coordinator = root
    if nested:
        supervisor = ExecutiveOperatorSupervisor(runtime,
            claimed_adapter_factory=lambda attempt, requested, loader, **kw:
                _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V5,
                    delegation={"descendant_limit": 8, "max_depth": 3}),
            prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5)
        outcome = asyncio.run(supervisor.start_cycle_job(planner.job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
        coordinator, = runtime.jobs.admit_cycle_plan(root.job_id,
            command_id=f"coo-cycle:{root.job_id}:admit-plan:{outcome.attempt.attempt_id}")
        CooCycle(runtime, planner_plan_schema_version=PLAN_SCHEMA_V5).run_once(coordinator.job_id)
        planner, = [job for job in runtime.jobs.list_jobs()
            if job.parent_job_id == coordinator.job_id and job.orchestration_role == "plan"]
    lease = _claim(runtime, coordinator, planner)
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=lambda *a, **k: None, prompt_source=_PromptSource())
    requested = supervisor._requested_profile(planner, lease)
    flat = _host_binding(tmp_path, worker_id=lease.attempt.worker_id)
    capabilities = codex_remote_capabilities()
    if native:
        capabilities = dataclasses.replace(capabilities,
            supports_native_resume=False, supported_optional_operations=())
    binding = rt.RemoteOperatorHostBinding(host_ref=flat.host_ref, worker_id=flat.worker_id,
        transport=flat.transport, worker_source_config_digest="c" * 64,
        provider=requested.provider, harness_kind=requested.harness_kind,
        harness_binary_digest=requested.harness_binary_digest, harness_version=requested.harness_version,
        expected_config_digest=requested.expected_config_digest, workspace=requested.workspace,
        capabilities=capabilities)
    return runtime, root, coordinator, planner, lease, requested, binding


def reserve_runtime_generation(runtime, lease, requested):
    sealed = runtime.operator_harness.seal_operator_harness_attempt(
        lease.attempt.attempt_id, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, requested=requested)
    operation = OperationId(f"ohf-op:start:{sealed.attempt_id}")
    epoch, generation = runtime.operator_harness.reserve_start(sealed.attempt_id,
        fence_generation=sealed.fence_generation, lease_token=lease.lease_token,
        operation_id=operation)
    return operation, epoch, generation


@pytest.mark.parametrize("nested", [False, True])
def test_real_runtime_claim_carries_original_root_and_immediate_parent_to_wire(tmp_path, monkeypatch, nested):
    from control_plane import remote_attempt_transport as rt
    from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
    runtime, root, coordinator, planner, lease, requested, binding = runtime_case(
        tmp_path, monkeypatch, nested=nested)
    reads, calls = [], []
    def source(host, worker):
        reads.append((host, worker))
        return binding
    adapter = rt.build_claimed_remote_operator_factory(runtime, source)(
        lease.attempt, requested, lambda t: "bounded", recovery=False)
    expected = runtime.jobs.get_planner_producer_binding(planner.job_id)
    assert expected["root_job_id"] == root.job_id
    assert expected["coordinator_job_id"] == coordinator.job_id
    assert planner.parent_job_id == coordinator.job_id
    assert (coordinator.job_id != root.job_id) is nested
    assert reads == [(binding.host_ref, lease.attempt.worker_id)]
    operation, epoch, generation = reserve_runtime_generation(runtime, lease, requested)
    class TransportReached(Exception): pass
    def trap(client, name, payload, **kwargs):
        if kwargs.get("before_write"): kwargs["before_write"](name, payload)
        assert payload_retargets_authority(name, payload, client.identity) is False
        calls.append((name, copy.deepcopy(payload), client.bound_payload_identity))
        raise TransportReached()
    monkeypatch.setattr(RemoteWorkerBrokerClient, "request_sync", trap)
    with pytest.raises(TransportReached):
        adapter.start_session(operation_id=operation, requested=requested, epoch=epoch, generation=generation)
    assert len(calls) == 1 and calls[0][0] == "ohf-start"
    transported = calls[0][1]["planner_producer"]
    assert transported == {"job_id": planner.job_id, "attempt_id": lease.attempt.attempt_id,
        "planner_producer_binding": expected, "planner_producer_binding_digest": canonical_digest(expected)}
    assert calls[0][2] == {"session_epoch_id": epoch.session_epoch_id,
                          "process_generation_id": generation.process_generation_id}


def test_unqualified_codex_versioned_producer_refuses_before_transport(tmp_path, monkeypatch):
    from control_plane import remote_attempt_transport as rt
    runtime, _, _, _, lease, requested, binding = runtime_case(tmp_path, monkeypatch, native=False)
    with pytest.raises(rt.RemoteAttemptTransportError, match="HOST_BINDING_MISMATCH"):
        rt.build_claimed_remote_operator_factory(runtime, lambda *a: binding)(
            lease.attempt, requested, lambda t: "bounded", recovery=False)


@pytest.mark.parametrize("moment", ["host_read", "before_start"])
def test_runtime_producer_drift_refuses_before_initialization(tmp_path, monkeypatch, moment):
    from control_plane import remote_attempt_transport as rt
    from test_planner_producer_binding import _created, _replace_created
    runtime, _, _, planner, lease, requested, binding = runtime_case(tmp_path, monkeypatch)
    def corrupt():
        raw = _created(runtime, planner)
        raw["planner_producer_binding"]["execution_binding_digest"] = "f" * 64
        raw["planner_producer_binding_digest"] = canonical_digest(raw["planner_producer_binding"])
        _replace_created(runtime, planner, raw)
    def source(*args):
        if moment == "host_read": corrupt()
        return binding
    factory = rt.build_claimed_remote_operator_factory(runtime, source)
    if moment == "host_read":
        with pytest.raises(rt.RemoteAttemptTransportError, match="STATE_MOVED"):
            factory(lease.attempt, requested, lambda t: "bounded", recovery=False)
    else:
        adapter = factory(lease.attempt, requested, lambda t: "bounded", recovery=False)
        operation, epoch, generation = reserve_runtime_generation(runtime, lease, requested)
        corrupt()
        with pytest.raises(rt.RemoteAttemptTransportError, match="STATE_MOVED"):
            adapter.start_session(operation_id=operation, requested=requested, epoch=epoch, generation=generation)


def test_cancellation_contains_original_runtime_generation_without_producer_lookup(tmp_path, monkeypatch):
    from control_plane import remote_attempt_transport as rt
    runtime, _, _, planner, lease, requested, binding = runtime_case(tmp_path, monkeypatch)
    _, epoch, generation = reserve_runtime_generation(runtime, lease, requested)
    runtime.jobs.cancel_job(planner.job_id)
    current = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    def forbidden(*args): pytest.fail("containment fetched a fresh planner producer")
    monkeypatch.setattr(runtime.jobs, "get_planner_producer_binding", forbidden)
    adapter = rt.build_claimed_remote_operator_factory(runtime, lambda *a: binding)(
        current, requested, forbidden, recovery=True)
    assert adapter._planner_producer is None
    assert adapter.client.bound_payload_identity == {"session_epoch_id": epoch.session_epoch_id,
        "process_generation_id": generation.process_generation_id}
    assert "ohf-start" not in adapter.client.allowed_operations


def test_sealed_result_contains_original_runtime_generation_without_producer_lookup(tmp_path, monkeypatch):
    from control_plane import remote_attempt_transport as rt
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from test_executive_operator_supervisor import _PromptSource
    from test_planner_producer_binding import _VersionedAdapter
    runtime, _, _, planner, lease, requested, binding = runtime_case(tmp_path, monkeypatch)
    retained = {}
    class CrashAfterSeal(BaseException): pass
    supervisor = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=lambda a, r, loader, **kw: _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V5),
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5)
    def stop_after_seal(**kwargs):
        retained.update(kwargs)
        raise CrashAfterSeal()
    monkeypatch.setattr(supervisor, "_complete_after_stop", stop_after_seal)
    with pytest.raises(CrashAfterSeal): supervisor._run_claimed(planner, lease)
    current = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert runtime.events.get_event_by_command_id(f"orchestration-result-seal:{current.attempt_id}")
    def forbidden(*args): pytest.fail("sealed containment fetched a fresh planner producer")
    monkeypatch.setattr(runtime.jobs, "get_planner_producer_binding", forbidden)
    adapter = rt.build_claimed_remote_operator_factory(runtime, lambda *a: binding)(
        current, requested, forbidden, recovery=True)
    session = retained["session"]
    assert adapter._planner_producer is None
    assert adapter.client.bound_payload_identity == {"session_epoch_id": session.epoch.session_epoch_id,
        "process_generation_id": session.generation.process_generation_id}
    assert "ohf-start" not in adapter.client.allowed_operations


def test_control_accepts_versioned_claim_aware_remote_owner_without_arming(tmp_path, monkeypatch):
    from control_plane.executive_runtime import Runtime
    from test_claimed_operator_control_composition import capture
    runtime = Runtime.at(tmp_path / "runtime")
    def source(*args): pytest.fail("Control construction resolved a worker before claim")
    _, supervisor, _ = capture(tmp_path, monkeypatch, runtime=runtime,
        remote_operator_binding_source=source, plan_schema_version=PLAN_SCHEMA_V5)
    assert callable(supervisor._claimed_adapter_factory)
    assert runtime.jobs.list_jobs() == []


def test_actual_worker_factory_selects_retained_contract_before_native_initialization(tmp_path, monkeypatch):
    from pathlib import Path
    from scripts import executive_os_phase1c_worker as worker
    from test_native_claude_worker_factory import prepared
    value, _, _, requested, calls = prepared(tmp_path, monkeypatch)
    broker = worker._build_broker(value, autonomy_guard=lambda: None)
    broker.operator_adapter_factory(Path(value["workspace_root"]), lambda t: "not dispatched",
        requested, planner_producer=selection())
    assert len(calls) == 1 and calls[0]["plan_contract"] == "executive-plan-v5"


@pytest.mark.parametrize("with_turn", [False, True])
def test_real_runtime_live_recovery_requires_custody_before_first_or_existing_result(
    tmp_path, monkeypatch, with_turn,
):
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
    from control_plane.executive_runtime import AttemptStatus
    from control_plane.executive_supervisor import ReconcileStatus
    from test_executive_operator_supervisor import _Clock, _PromptSource
    from test_planner_producer_binding import _VersionedAdapter
    clock = _Clock()
    runtime, _, _, planner, lease, _, _ = runtime_case(tmp_path, monkeypatch, clock=clock)
    initialized = []
    class CrashAfterNativeEffect(BaseException): pass
    def factory(_attempt, _requested, loader, **kwargs):
        adapter = _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V5)
        initialized.append(adapter)
        if with_turn:
            def after_begin(*args, **kwargs): raise CrashAfterNativeEffect()
            adapter.read_events = after_begin
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=factory,
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5)
    if not with_turn:
        original_require = supervisor._require_adapter_contract
        def after_init(job, adapter, *, initialized_generation=None):
            original_require(job, adapter, initialized_generation=initialized_generation)
            if initialized_generation is not None: raise CrashAfterNativeEffect()
        monkeypatch.setattr(supervisor, "_require_adapter_contract", after_init)
    with pytest.raises(CrashAfterNativeEffect):
        supervisor._run_claimed(planner, lease)
    current = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert current.status is AttemptStatus.RUNNING
    assert initialized[0].begin_turn_calls == int(with_turn)
    clock.advance(1000)
    selected = selection(attempt=current.attempt_id, job=planner.job_id,
        root=planner.root_job_id, coordinator=planner.parent_job_id)
    selected["planner_producer_binding"] = runtime.jobs.get_planner_producer_binding(planner.job_id)
    selected["planner_producer_binding_digest"] = canonical_digest(selected["planner_producer_binding"])
    operations = []
    class MissingMaterialization:
        def request_sync(self, operation, payload, **kwargs):
            operations.append(operation)
            if operation == "ohf-reconcile":
                return {"observation": to_wire(initialized[0].reconcile(None))}
            if operation == "ohf-materialization-status":
                assert payload["operation_id"]["command_id"] == f"ohf-op:start:{current.attempt_id}"
                assert payload["planner_producer"] == selected
                return {"schema_version": "mastermind.operator_materialization_status/v1",
                        "status": "ABSENT", "receipt": None}
            pytest.fail(f"recovery reached useful or replacement operation {operation}")
    recovered = ExecutiveOperatorSupervisor(runtime,
        claimed_adapter_factory=lambda a, r, loader, **kw: RemoteOperatorHarnessAdapter(
            MissingMaterialization(), turn_input_loader=loader, capabilities=dataclasses.replace(
                codex_remote_capabilities(), supports_native_resume=False, supported_optional_operations=()),
            planner_producer=selected), prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5)
    assert [item.status for item in recovered.reconcile_restart()] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert operations == ["ohf-reconcile", "ohf-materialization-status"]
    assert runtime.attempts.get_attempt(current.attempt_id).status is AttemptStatus.RUNNING
    assert runtime.events.get_event_by_command_id(f"orchestration-result-seal:{current.attempt_id}") is None
