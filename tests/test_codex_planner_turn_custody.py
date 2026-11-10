"""Codex request custody through actual owners, without live provider dispatch.

The native integration uses the existing stdio fake App Server. Runtime tests
use disposable SQLite owners and explicit inert result fixtures. No production
profile, provider credential, grant, model, service or admission is enabled.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from control_plane.claude_operator_helper_protocol import native_plan_schema
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ExecutiveOperatorSupervisorError
from control_plane.executive_orchestration_result import PLAN_SCHEMA_V5, RESULT_SCHEMA, canonical_bytes, canonical_digest
from control_plane.executive_runtime import AttemptLease, AttemptStatus, StateConflict
from control_plane.executive_worker_broker import RemoteBrokerError
from control_plane.operator_harness_contract import (
    EventCursor, OperationId, OperationKind, OperationReceiptKind, ProcessGenerationRef, ProcessIdentityObservation,
    SessionEpochRef, TurnRef, TurnStartObservation, compare_launch,
    operation_receipt_command_id,
)
from control_plane.operator_harness_wire import (
    OperatorHarnessWireError, build_planner_turn_custody, planner_turn_custody,
    to_wire, turn_start_observation,
)
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_RECEIPT_SCHEMA_V3, OperatorMaterializationReceiptError,
    build_operator_materialization_receipt, canonical_json_bytes,
    load_operator_materialization_receipt,
)
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from scripts.ohf.laboratory import AppServerClient
from test_executive_operator_broker import _fixture
from test_executive_operator_supervisor import _Clock, _PromptSource
from test_operator_materialization_receipt import _inputs
from test_planner_producer_binding import _VersionedAdapter
from test_remote_planner_producer_custody import LocalBrokerClient, runtime_case, selection


def _wire_case():
    selected = selection()
    turn = TurnRef("turn-one", "epoch-one", "generation-one", selected["attempt_id"])
    operation = OperationId("ohf-op:turn-one")
    request = {"threadId": "native-session", "input": [{"type": "text", "text": "bounded"}],
               "outputSchema": native_plan_schema("executive-plan-v5")}
    proof = build_planner_turn_custody(producer=selected, operation_id=operation, turn=turn,
        provider_session_id="native-session", provider_native_turn_id="native-turn", native_request=request)
    return selected, turn, operation, request, proof


def test_legacy_observation_omits_optional_extension_byte_for_byte():
    encoded = to_wire(TurnStartObservation("native-turn", True))
    assert encoded == {"provider_native_turn_id": "native-turn", "acknowledged": True}
    assert to_wire(turn_start_observation(encoded)) == encoded
    with pytest.raises(OperatorHarnessWireError):
        turn_start_observation({**encoded, "planner_custody": None})


@pytest.mark.parametrize("fault", [
    "extra", "missing", "null", "different_operation", "different_attempt", "different_turn",
    "different_session", "different_native_turn", "different_producer", "different_schema",
    "digest_shape", "whitespace", "echo_claim", "unacknowledged", "missing_native_id",
])
def test_closed_ack_rejects_splicing_or_invented_schema_observation(fault):
    selected, turn, operation, _, proof = _wire_case()
    if fault == "extra": proof["authority"] = "WRITE"
    elif fault == "missing": proof.pop("native_request_digest")
    elif fault == "null": proof = None
    elif fault == "different_operation": proof["operation_id"] = "ohf-op:other"
    elif fault == "different_attempt": proof["attempt_id"] = "ATT-OTHER"
    elif fault == "different_turn": proof["turn_id"] = "turn-other"
    elif fault == "different_session": proof["provider_session_id"] = "native-other"
    elif fault == "different_native_turn": proof["provider_native_turn_id"] = "native-other"
    elif fault == "different_producer": proof["planner_producer_binding_digest"] = "f" * 64
    elif fault == "different_schema": proof["native_result_contract"]["schema_digest"] = "f" * 64
    elif fault == "digest_shape": proof["native_request_digest"] = "not-a-digest"
    elif fault == "whitespace": proof["job_id"] = " "
    elif fault == "echo_claim": proof["evidence_kind"] = "NATIVE_SCHEMA_OBSERVED"
    if fault in {"unacknowledged", "missing_native_id"}:
        with pytest.raises(OperatorHarnessWireError):
            turn_start_observation({"provider_native_turn_id": None if fault == "missing_native_id" else "native-turn",
                "acknowledged": fault != "unacknowledged", "planner_custody": proof})
    else:
        with pytest.raises(OperatorHarnessWireError):
            planner_turn_custody(proof, producer=selected, operation_id=operation, turn=turn,
                provider_session_id="native-session", provider_native_turn_id="native-turn")


@pytest.mark.parametrize("fault", [None, "observed_schema", "missing_producer", "resume", "other_provider"])
def test_v3_materialization_retains_intent_without_initialization_schema_claim(fault):
    values = _inputs(resume=fault == "resume")
    values.pop("expected_provider_session_id")
    selected = selection(attempt=values["attempt_id"])
    extra = {"schema": MATERIALIZATION_RECEIPT_SCHEMA_V3, "planner_producer": selected}
    if fault == "observed_schema":
        extra["observed_planner_contract"] = selected["planner_producer_binding"]["native_result_contract"]
    elif fault == "missing_producer": extra.pop("planner_producer")
    elif fault == "other_provider": values["observed_attestation"]["auth"]["provider"] = "claude"
    if fault is not None:
        with pytest.raises(OperatorMaterializationReceiptError):
            build_operator_materialization_receipt(**values, **extra)
        return
    receipt = build_operator_materialization_receipt(**values, **extra)
    assert receipt.planner_producer == selected
    assert receipt.observed_planner_contract is None
    assert "observed_planner_contract" not in receipt.to_dict()
    assert load_operator_materialization_receipt(canonical_json_bytes(receipt.to_dict())) == receipt


def _plan_result(selected, worker):
    binding = selected["planner_producer_binding"]
    return {
        "schema_version": RESULT_SCHEMA, "job_id": selected["job_id"], "run_id": selected["attempt_id"],
        "worker_id": worker, "role": "plan", "status": "COMPLETED",
        "role_result": {"schema_version": PLAN_SCHEMA_V5, "root_job_id": binding["root_job_id"],
            "coordinator_job_id": binding["coordinator_job_id"], "plan_attempt_id": selected["attempt_id"],
            "steps": [{"ordinal": 0, "step_id": "step-1", "objective": "Bounded read-only follow-up",
                "business_impact": "routine", "review_required": False, "requested_authorities": ["READ"],
                "allowed_write_paths": [], "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
                "prerequisite_step_ids": [], "delegation": None}]},
        "summary": "Bounded plan", "current_state": "complete", "next_actions": [], "errors": [], "validations": [],
    }


@pytest.fixture
def codex_chain(tmp_path):
    """Actual broker/proxy/Codex owners and local fake stdio transport only."""
    broker, peer, requested, _, _ = _fixture(tmp_path / "broker")
    python = Path(sys.executable).resolve()
    requested = dataclasses.replace(requested, harness_binary_digest=hashlib.sha256(python.read_bytes()).hexdigest(),
                                    harness_version="ohf-fake-app-server/p0b")
    home = broker.policy.provider_home
    home.chmod(0o700)
    (home / "auth.json").write_text("fixture credential bytes")
    (home / "auth.json").chmod(0o600)
    epoch = SessionEpochRef("epoch-native", "ATT-NATIVE", requested.worker_id, 1)
    generation = ProcessGenerationRef("generation-native", epoch.session_epoch_id, 1, requested.worker_id)
    selected = selection(attempt=epoch.attempt_id)
    result = _plan_result(selected, requested.worker_id)
    native_requests, native_clients, adapters = [], [], []
    faults = {"lose_turn_reply": False, "bad_result": False}

    def client_factory(argv, env, cwd):
        client = AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)
        original = client.request
        def request(method, params, **kwargs):
            native_requests.append((method, copy.deepcopy(params)))
            value = original(method, params, **kwargs)
            if method == "turn/start" and faults["lose_turn_reply"]:
                raise TimeoutError("fixture lost original native turn ACK")
            return value
        client.request = request
        native_clients.append(client)
        return client

    def factory(workspace, loader, profile, *, planner_producer=None):
        assert profile == requested and planner_producer == selected
        adapter = CodexOperatorAdapter(binary_path=python, codex_home=home, workspace_root=workspace,
            worker_id=requested.worker_id, app_server_argv=(str(python), "-m", "scripts.ohf.fake_app_server"),
            expected_harness_version=requested.harness_version, turn_input_loader=loader,
            base_sha_resolver=lambda _p: requested.workspace.base_sha,
            process_identity_observer=lambda pid: ProcessIdentityObservation(pid, pid, f"start-{pid}", "boot"),
            client_factory=client_factory, planner_producer=planner_producer,
            extra_env={"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                "OHF_FAKE_STATE": str(tmp_path / "native-state.json"), "OHF_FAKE_WORKSPACE": str(workspace),
                "OHF_FAKE_SKILL_ROOT": str(workspace / ".agents" / "skills"),
                "OHF_FAKE_MODEL": requested.requested_model, "OHF_FAKE_MCP_GONE": "1",
                "OHF_FAKE_BUNDLED_DISABLED": "1",
                "OHF_FAKE_TURN_REPLY": canonical_bytes({"invalid": True} if faults["bad_result"] else result).decode()})
        adapters.append(adapter)
        return adapter

    broker.operator_adapter_factory = factory
    client = LocalBrokerClient(broker, peer)
    capabilities = dataclasses.replace(codex_remote_capabilities(), supports_native_resume=False, supported_optional_operations=())
    def proxy():
        return RemoteOperatorHarnessAdapter(client, turn_input_loader=lambda _t: "bounded plan input — 原本",
                                            capabilities=capabilities, planner_producer=selected)
    value = SimpleNamespace(broker=broker, client=client, requested=requested, epoch=epoch, generation=generation,
                            selected=selected, proxy=proxy, adapters=adapters, native_requests=native_requests,
                            faults=faults, result=result)
    try:
        yield value
    finally:
        for native in native_clients:
            native.close()


def _native_start(chain, proxy):
    return proxy.start_session(operation_id=OperationId(f"ohf-op:start:{chain.epoch.attempt_id}"),
        requested=chain.requested, epoch=chain.epoch, generation=chain.generation)


def _native_turn(chain, proxy):
    turn = TurnRef("turn-native", chain.epoch.session_epoch_id, chain.generation.process_generation_id, chain.epoch.attempt_id)
    operation = OperationId("ohf-op:turn-native")
    return turn, operation, proxy.begin_turn(operation_id=operation, turn=turn, generation=chain.generation,
        launch=compare_launch(chain.requested, proxy.observed_attestation(chain.generation)))


def test_actual_codex_remote_turn_requests_v5_and_seals_only_observed_ack(codex_chain):
    chain, proxy = codex_chain, codex_chain.proxy()
    started = _native_start(chain, proxy)
    receipt = proxy._planner_receipts[chain.generation.process_generation_id]
    assert receipt.schema == MATERIALIZATION_RECEIPT_SCHEMA_V3
    assert receipt.observed_planner_contract is None
    assert chain.adapters[0].retained_planner_producer(chain.generation) == chain.selected
    assert not hasattr(chain.adapters[0], "observed_planner_contract")
    assert all("outputSchema" not in params for method, params in chain.native_requests)
    turn, operation, observation = _native_turn(chain, proxy)
    native_request, = [params for method, params in chain.native_requests if method == "turn/start"]
    assert native_request["outputSchema"] == native_plan_schema("executive-plan-v5")
    assert native_request["threadId"] == started.provider_session_id
    assert observation.planner_custody["native_request_digest"] == canonical_digest(native_request)
    assert observation.planner_custody["evidence_kind"] == "NATIVE_REQUEST_ACK"
    proxy.read_events(EventCursor(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                turn_id=turn.turn_id), timeout_seconds=2)
    candidate = proxy.collect_candidate_result(turn)
    raw = proxy.observe_raw_role_result(turn)
    assert json.loads(raw.canonical_result_json) == chain.result
    assert raw.provider_turn_artifact_digest == candidate.artifact_digest
    assert raw.provider_native_turn_id == observation.provider_native_turn_id


def test_native_request_ack_does_not_validate_an_invalid_result(codex_chain):
    chain, proxy = codex_chain, codex_chain.proxy()
    chain.faults["bad_result"] = True
    _native_start(chain, proxy)
    turn, _, observation = _native_turn(chain, proxy)
    assert observation.acknowledged and observation.planner_custody["evidence_kind"] == "NATIVE_REQUEST_ACK"
    with pytest.raises(RemoteBrokerError, match="MODEL_OR_WORK_RESULT_FAILURE"):
        proxy.read_events(EventCursor(turn.attempt_id, turn.session_epoch_id, turn.process_generation_id,
                                    turn_id=turn.turn_id), timeout_seconds=2)


def test_lost_native_ack_never_resends_original_or_replacement_turn(codex_chain):
    chain, proxy = codex_chain, codex_chain.proxy()
    _native_start(chain, proxy)
    chain.faults["lose_turn_reply"] = True
    with pytest.raises(RemoteBrokerError): _native_turn(chain, proxy)
    chain.faults["lose_turn_reply"] = False
    with pytest.raises(RemoteBrokerError, match="ACTIVE_WRITER_CONFLICT"): _native_turn(chain, proxy)
    replacement = TurnRef("turn-replacement", chain.epoch.session_epoch_id,
                          chain.generation.process_generation_id, chain.epoch.attempt_id)
    with pytest.raises(RemoteBrokerError, match="ACTIVE_WRITER_CONFLICT"):
        proxy.begin_turn(operation_id=OperationId("ohf-op:replacement"), turn=replacement,
            generation=chain.generation,
            launch=compare_launch(chain.requested, proxy.observed_attestation(chain.generation)))
    assert sum(method == "turn/start" for method, _ in chain.native_requests) == 1
    state = chain.adapters[0]._state(chain.generation)
    assert len(state.planner_turn_dispatches) == 1 and state.planner_turn_custodies == {}


def test_native_result_custody_still_matches_the_actual_dispatched_request(codex_chain):
    from control_plane.codex_operator_adapter import CodexAdapterError
    chain, proxy = codex_chain, codex_chain.proxy()
    _native_start(chain, proxy)
    turn, _, _ = _native_turn(chain, proxy)
    adapter = chain.adapters[0]
    adapter.collect_candidate_result(turn)
    adapter._state(chain.generation).planner_turn_custodies[turn.turn_id]["native_request_digest"] = "f" * 64
    with pytest.raises(CodexAdapterError, match="raw result canonical validation failed"):
        adapter.observe_raw_role_result(turn)


def test_lost_initialization_reply_recovers_same_v3_materialization(codex_chain):
    chain, proxy = codex_chain, codex_chain.proxy()
    chain.client.lose_start_reply = True
    with pytest.raises(TimeoutError): _native_start(chain, proxy)
    recovered = chain.proxy()
    recovered.qualify_existing_planner_generation(requested=chain.requested, epoch=chain.epoch, generation=chain.generation)
    assert recovered._planner_receipts[chain.generation.process_generation_id].schema == MATERIALIZATION_RECEIPT_SCHEMA_V3
    assert sum(method == "initialize" for method, _ in chain.native_requests) == 1
    assert not any(method == "turn/start" for method, _ in chain.native_requests)


@pytest.mark.parametrize("after_start", [False, True])
def test_codex_keeps_original_foreground_guard_before_native_effect(codex_chain, after_start):
    chain, proxy = codex_chain, codex_chain.proxy()
    open_source = [True]
    def guard():
        if not open_source[0]: raise ValueError("original source closed")
    proxy.bind_fresh_effect_guard(guard, attempt_id=chain.epoch.attempt_id)
    if after_start: _native_start(chain, proxy)
    prior = len(chain.native_requests)
    open_source[0] = False
    with pytest.raises(ValueError, match="original source closed"):
        _native_turn(chain, proxy) if after_start else _native_start(chain, proxy)
    assert len(chain.native_requests) == prior


def test_actual_enabled_codex_worker_factory_retains_native_grant_and_account_scope(tmp_path, monkeypatch):
    from control_plane import codex_worker
    from control_plane.codex_account_environment import CodexAccountError, native_codex_account_scope
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from scripts import executive_os_phase1c_worker as worker
    from test_codex_account_environment import auth, private
    from test_executive_codex_attestation_receipt import _fixture as attested_binary_fixture
    from test_native_worker_factory import native_config
    binary, receipt = attested_binary_fixture(tmp_path, monkeypatch)
    os.chown(receipt, -1, os.getegid())
    config = native_config(tmp_path.resolve())
    config.update(control_uid=os.geteuid() + 1000, allowed_supplementary_gids=[],
                  codex_binary=str(binary), codex_attestation_receipt=str(receipt))
    for field in ("workspace_root", "run_root", "provider_home"):
        Path(config[field]).mkdir(mode=0o700)
    private(Path(config["provider_home"]) / "auth.json", auth())
    monkeypatch.setattr(worker, "load_codex_attestation_receipt",
        lambda path, **kwargs: codex_worker.load_codex_attestation_receipt(path, **kwargs, expected_owner_uid=os.geteuid()))
    profile = ExecutionCapabilityRegistry.load().resolve("operator.appserver.readonly.docs-mcp.native-helper.v1")
    requested = SimpleNamespace(harness_binary_digest=hashlib.sha256(binary.read_bytes()).hexdigest(),
        sandbox_policy=profile.sandbox_policy, approval_policy=profile.approval_policy,
        network_policy=profile.network_policy, write_capable=profile.write_capable,
        native_helper_policy=profile.native_helper_policy, expected_config_digest=profile.expected_config_digest)
    requested.capabilities = profile.capability_manifest(harness_binary_digest=requested.harness_binary_digest)
    constructors = []
    def construct(**kwargs):
        constructors.append(kwargs)
        return CodexOperatorAdapter(**kwargs, base_sha_resolver=lambda _path: "b" * 40)
    monkeypatch.setattr(worker, "CodexOperatorAdapter", construct)
    selected = selection()
    with native_codex_account_scope(Path(config["provider_home"])) as account:
        broker = worker._build_broker(config, native_account=account)
        adapter = broker.operator_adapter_factory(Path(config["workspace_root"]), lambda t: "not dispatched",
                                                 requested, planner_producer=selected)
        assert type(adapter) is CodexOperatorAdapter and adapter._generations == {}
        assert adapter.plan_contract == "executive-plan-v5"
        assert constructors[0]["planner_producer"] == selected
        assert constructors[0]["native_helper_grant"] == profile.native_helper
        assert constructors[0]["app_server_config_overrides"] == profile.app_server_config_overrides()
    with pytest.raises(CodexAccountError):
        broker.operator_adapter_factory(Path(config["workspace_root"]), lambda t: "not dispatched",
                                        requested, planner_producer=selected)
    assert len(constructors) == 1


class _CrashAfterAck(BaseException):
    pass


def _runtime_after_ack(tmp_path, monkeypatch, *, nested=False, lose_runtime_ack=False):
    clock = _Clock()
    runtime, root, coordinator, planner, lease, _, _ = runtime_case(tmp_path, monkeypatch, native=False, nested=nested, clock=clock)
    adapters = []
    def factory(_attempt, _requested, loader, **_kwargs):
        adapter = _VersionedAdapter(runtime, loader, PLAN_SCHEMA_V5)
        adapter.provider_session_id = f"SESSION-{_attempt.attempt_id}"
        adapter.native_turn_id = f"NATIVE-{_attempt.attempt_id}"
        original = adapter.begin_turn
        def begin(**kwargs):
            adapter.saved_turn, adapter.saved_operation = kwargs["turn"], kwargs["operation_id"]
            adapter.saved_observation = original(**kwargs)
            return adapter.saved_observation
        adapter.begin_turn = begin
        adapter.read_events = lambda *a, **k: (_ for _ in ()).throw(_CrashAfterAck())
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=factory,
        prompt_source=_PromptSource(), plan_schema_version=PLAN_SCHEMA_V5)
    if lose_runtime_ack:
        monkeypatch.setattr(runtime.operator_harness, "acknowledge_turn",
                            lambda **kwargs: (_ for _ in ()).throw(_CrashAfterAck()))
    with pytest.raises(_CrashAfterAck): supervisor._run_claimed(planner, lease)
    lease = AttemptLease(runtime.attempts.get_attempt(lease.attempt.attempt_id), lease.lease_token)
    adapter, = adapters
    return SimpleNamespace(runtime=runtime, root=root, coordinator=coordinator, planner=planner, lease=lease,
                           adapter=adapter, supervisor=supervisor, clock=clock,
                           turn=adapter.saved_turn, operation=adapter.saved_operation,
                           observation=adapter.saved_observation)


@pytest.mark.parametrize("nested", [False, True])
def test_real_runtime_v2_ack_retains_root_parent_but_cannot_admit_children(tmp_path, monkeypatch, nested):
    case = _runtime_after_ack(tmp_path, monkeypatch, nested=nested)
    intent = case.runtime.events.get_event_by_command_id(case.operation.command_id)
    applied = case.runtime.events.get_event_by_command_id(operation_receipt_command_id(case.operation, OperationReceiptKind.APPLIED))
    assert intent.payload["schema_version"] == "mastermind.operator_harness_turn_intent/v2"
    assert applied.payload["schema_version"] == "mastermind.operator_harness_turn_applied/v2"
    binding = intent.payload["planner_producer"]["planner_producer_binding"]
    assert binding["root_job_id"] == case.root.job_id and binding["coordinator_job_id"] == case.coordinator.job_id
    assert (case.root.job_id != case.coordinator.job_id) is nested
    assert applied.payload["planner_custody"] == case.observation.planner_custody
    with pytest.raises(StateConflict):
        case.runtime.jobs.admit_cycle_plan(case.coordinator.job_id,
            command_id=f"coo-cycle:{case.coordinator.job_id}:admit-plan:{case.turn.attempt_id}")
    assert case.runtime.events.get_event_by_command_id(f"orchestration-result-seal:{case.turn.attempt_id}") is None
    session, recovered_turn, recovered_operation = case.supervisor._recovery_session(case.lease)
    assert recovered_turn == case.turn and recovered_operation == case.operation
    assert session.generation.generation_number == 1


def test_runtime_lost_ack_is_original_unknown_effect_without_replacement_dispatch(tmp_path, monkeypatch):
    case = _runtime_after_ack(tmp_path, monkeypatch, lose_runtime_ack=True)
    assert case.adapter.begin_turn_calls == 1
    applied_id = operation_receipt_command_id(case.operation, OperationReceiptKind.APPLIED)
    assert case.runtime.events.get_event_by_command_id(applied_id) is None
    with pytest.raises(ExecutiveOperatorSupervisorError, match="no exact acknowledged receipt"):
        case.supervisor._recovery_session(case.lease)
    assert case.runtime.operator_harness.commit_provider_dispatch(attempt_id=case.turn.attempt_id,
        operation_id=case.operation, operation_kind=OperationKind.BEGIN_TURN,
        fence_generation=case.lease.attempt.fence_generation, lease_token=case.lease.lease_token) is False
    unknown = case.runtime.events.get_event_by_command_id(operation_receipt_command_id(case.operation, OperationReceiptKind.EFFECT_UNKNOWN))
    assert unknown is not None and case.adapter.begin_turn_calls == 1
    assert case.runtime.events.get_event_by_command_id(f"orchestration-result-seal:{case.turn.attempt_id}") is None


@pytest.mark.parametrize("fault", ["missing", "native_turn", "extra", "downgrade"])
def test_runtime_candidate_revalidates_original_ack_instead_of_trusting_its_presence(tmp_path, monkeypatch, fault):
    case = _runtime_after_ack(tmp_path, monkeypatch)
    event_id = operation_receipt_command_id(case.operation, OperationReceiptKind.APPLIED)
    payload = copy.deepcopy(case.runtime.events.get_event_by_command_id(event_id).payload)
    if fault == "missing": payload.pop("planner_custody")
    elif fault == "native_turn": payload["planner_custody"]["provider_native_turn_id"] = "native-other"
    elif fault == "extra": payload["planner_custody"]["authority"] = "WRITE"
    else:
        payload["schema_version"] = "mastermind.operator_harness_turn_applied/v1"
        payload.pop("planner_custody")
    # Only the fixture can model corrupted retained bytes; restore the real
    # immutable Event trigger in the same transaction before exercising owners.
    with case.runtime.store.transaction() as connection:
        trigger = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='events_are_immutable_update'").fetchone()[0]
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute("UPDATE events SET payload_json=? WHERE command_id=?", (canonical_bytes(payload).decode(), event_id))
        connection.execute(trigger)
    with pytest.raises(StateConflict):
        case.runtime.operator_harness.record_candidate_evidence(turn=case.turn,
            candidate=case.adapter.collect_candidate_result(case.turn), events=(),
            cursor=EventCursor(case.turn.attempt_id, case.turn.session_epoch_id, case.turn.process_generation_id, turn_id=case.turn.turn_id),
            fence_generation=case.lease.attempt.fence_generation, lease_token=case.lease.lease_token)
    assert case.runtime.events.get_event_by_command_id(f"ohf-candidate:{case.turn.turn_id}") is None


@pytest.mark.parametrize("fault", ["missing_ack", "spliced_ack", "wrong_version", "wrong_root", "wrong_parent"])
def test_real_runtime_refuses_unqualified_ack_or_result_before_seal(tmp_path, monkeypatch, fault):
    case = _runtime_after_ack(tmp_path, monkeypatch)
    kwargs = {"fence_generation": case.lease.attempt.fence_generation, "lease_token": case.lease.lease_token}
    if fault in {"missing_ack", "spliced_ack"}:
        proof = None if fault == "missing_ack" else {**case.observation.planner_custody, "provider_session_id": "other"}
        with pytest.raises(StateConflict):
            case.runtime.operator_harness.acknowledge_turn(turn=case.turn, operation_id=case.operation,
                observation=dataclasses.replace(case.observation, planner_custody=proof), **kwargs)
    else:
        candidate = case.adapter.collect_candidate_result(case.turn)
        case.runtime.operator_harness.record_candidate_evidence(turn=case.turn, candidate=candidate, events=(),
            cursor=EventCursor(case.turn.attempt_id, case.turn.session_epoch_id, case.turn.process_generation_id,
                               turn_id=case.turn.turn_id), **kwargs)
        observation = case.adapter.observe_raw_role_result(case.turn)
        envelope = json.loads(observation.canonical_result_json)
        if fault == "wrong_version": envelope["role_result"]["schema_version"] = "mastermind.execution_plan/v4"
        elif fault == "wrong_root": envelope["role_result"]["root_job_id"] = "JOB-OTHER"
        else: envelope["role_result"]["coordinator_job_id"] = "JOB-OTHER"
        encoded = canonical_bytes(envelope)
        observation = dataclasses.replace(observation, canonical_result_json=encoded.decode(),
            canonical_result_digest=canonical_digest(envelope), canonical_result_byte_length=len(encoded))
        with pytest.raises(StateConflict):
            case.runtime.operator_harness.seal_orchestration_role_result(turn=case.turn, observation=observation, **kwargs)
    assert case.runtime.events.get_event_by_command_id(f"orchestration-result-seal:{case.turn.attempt_id}") is None
    assert case.runtime.attempts.get_attempt(case.turn.attempt_id).status is AttemptStatus.RUNNING
    assert len(case.runtime.jobs.list_jobs()) == 2
