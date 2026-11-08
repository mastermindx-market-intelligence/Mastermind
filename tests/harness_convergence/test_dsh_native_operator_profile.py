"""Actual full native process through the synchronous OHF adapter.

The attestation/current-authority callback is an explicit laboratory fixture.
This is not installed Executive, authenticated account or production acceptance.
"""
import asyncio
import json
from pathlib import Path

from control_plane.operator_harness_contract import (
    AuthRealmFact, CapabilityManifest, EventCursor, NativeHelperPolicy,
    ObservedHarnessAttestation, OperationId, ProcessGenerationRef,
    ProcessLiveness, ProviderSessionHandoff, ProviderWriterState,
    RequestedExecutionProfile, SessionEpochRef, TurnRef, WorkspaceIdentity, compare_launch,
)
from control_plane.worker_execution_contract import BinaryAttestation
from integrations.acp_worker.turn import AcpProfile
from integrations.deepseek_harness.operator_adapter import (
    DSH_NATIVE_HARNESS_KIND, NativeLaunchBinding, NativeOperatorAdapter,
)
from tests.harness_convergence.test_dsh_fullapp_company_profile import supplied, sha, COMPAT


async def generation(supply, node, state, mode, session_id=None):
    workspace = state/"workspace"
    node_info, work_info = node.stat(), workspace.stat()
    binary = BinaryAttestation(str(node), str(node), "26.5.0", sha(node), None,
        node_info.st_size, node_info.st_dev, node_info.st_ino, node_info.st_mode & 0o7777,
        node_info.st_uid, node_info.st_gid, node_info.st_mtime_ns)
    identity = WorkspaceIdentity(str(workspace), "b"*40, work_info.st_dev, work_info.st_ino,
                                 work_info.st_uid, work_info.st_gid)
    # Test-only authority input. Never asserts a production sandbox, account,
    # complete capability inventory or installed source/profile observation.
    requested = RequestedExecutionProfile(
        "fixture-dsh", "acp", "fixture", DSH_NATIVE_HARNESS_KIND,
        binary.sha256, binary.version, identity, "laboratory-unconfined",
        "laboratory-explicit", "laboratory-native-loopback",
        CapabilityManifest(), NativeHelperPolicy.DISABLED, "c"*64)
    report_path = state/("ohf-"+mode+".json")
    args = (str(node), str(COMPAT/"native-company-profile-fixture.mjs"),
            str(supply), str(state), str(report_path), mode)
    if session_id is not None:
        args += (session_id,)
    environment = {
        "PATH": str(node.parent)+":/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(state/"home"), "DSH_HOME": str(state/"dsh"),
        "DSH_AGENTS_HOME": str(state/"agents"), "DSH_TELEMETRY_DISABLED": "1",
        "LANG": "C", "MMX_NATIVE_ACP_EXERCISE": "ohf-claim-stop-resume",
    }
    expected_fixture = sha(COMPAT/"native-company-profile-fixture.mjs")
    def verify_source():
        assert sha(node) == binary.sha256
        assert sha(COMPAT/"native-company-profile-fixture.mjs") == expected_fixture
    async def fixture_attestation(native):
        assert native.initialization["agentInfo"]["name"] == "deepseek-harness-acp"
        assert native.provider_session_id
        observed = await native.observe()
        expected = ObservedHarnessAttestation(
            "fixture", binary.version, binary.sha256, (), (), (), (),
            "laboratory-unconfined", "laboratory-explicit", "laboratory-native-loopback",
            None, AuthRealmFact("fixture-dsh", "acp"), identity,
            unknown_fields=("installed_authority", "account", "production_capability_inventory"))
        assert observed == expected
        return observed
    epoch = SessionEpochRef("epoch-native-fixture", "attempt-native-fixture", "fixture-dsh", 1)
    generation = ProcessGenerationRef("generation-native-"+mode, epoch.session_epoch_id,
                                     1 if mode == "new" else 2, epoch.worker_id)
    calls = []
    def current(operation, observed_epoch, observed_generation, method, observed_session):
        assert observed_epoch == epoch and observed_generation == generation
        assert operation.command_id in {"ohf-op:fixture-"+mode, "ohf-op:fixture-native-turn-"+mode,
                                        "ohf-op:fixture-stop-"+mode}
        if session_id is not None:
            assert observed_session == session_id
        calls.append(method)
    binding = NativeLaunchBinding(binary, args, environment, state/"dsh", state/"captures",
        AcpProfile("deepseek-harness-acp", "0.0.1", model_option_provider="fixture"),
        verify_source, fixture_attestation, current)
    adapter = NativeOperatorAdapter(workspace, lambda _turn: "Exercise the original native conversation.",
                                    requested, binding)
    start = dict(operation_id=OperationId("ohf-op:fixture-"+mode),
                 requested=requested, epoch=epoch, generation=generation)
    async def report_when(predicate):
        deadline = asyncio.get_running_loop().time()+25
        while asyncio.get_running_loop().time() < deadline:
            try:
                report = json.loads(report_path.read_bytes())
            except (FileNotFoundError, json.JSONDecodeError):
                report = {}
            assert "failure" not in report, report.get("failure")
            if predicate(report):
                return report
            await asyncio.sleep(0.02)
        raise AssertionError("original native observation absent")
    closed = None
    try:
        if session_id is None:
            started = await asyncio.to_thread(adapter.start_session, **start)
        else:
            started = await asyncio.to_thread(adapter.resume_session, **start,
                provider_session=ProviderSessionHandoff(session_id, epoch.worker_id))
            await report_when(lambda row: row.get("recovered_interrupted") is True)
        original_id = started.provider_session_id
        assert session_id is None or session_id == original_id
        credentials = await asyncio.to_thread(adapter.observe_process_credentials, generation)
        home = await asyncio.to_thread(adapter.observe_provider_home_identity, generation)
        assert credentials.os_principal_uid == home.provider_home_identity["uid"]
        turn = TurnRef("turn-native-"+mode, epoch.session_epoch_id, generation.process_generation_id, epoch.attempt_id)
        observed = await asyncio.to_thread(adapter.observed_attestation, generation)
        ack = await asyncio.to_thread(adapter.begin_turn,
            operation_id=OperationId("ohf-op:fixture-native-turn-"+mode),
            turn=turn, generation=generation, launch=compare_launch(requested, observed))
        assert ack.acknowledged
        if mode == "new":
            await report_when(lambda row: row.get("stream_partial") is True)
            await asyncio.to_thread(adapter.interrupt_turn, turn,
                                    operation_id=OperationId("ohf-op:fixture-stop-"+mode))
        cursor = EventCursor(epoch.attempt_id, epoch.session_epoch_id, generation.process_generation_id, 0, turn.turn_id)
        events, cursor = await asyncio.to_thread(adapter.read_events, cursor, timeout_seconds=40)
        candidate = await asyncio.to_thread(adapter.collect_candidate_result, turn)
        result = await asyncio.to_thread(adapter.observe_native_conversation_result, turn)
        assert result.stop_reason == ("cancelled" if mode == "new" else "end_turn")
        assert ack.provider_native_turn_id == result.provider_native_turn_id
        assert candidate.artifact_digest == result.provider_turn_artifact_digest
        assert candidate.complete_job_permitted is False
        assert events and sum(item.kind == "native_terminal" for item in events) == 1
        held = await asyncio.to_thread(adapter.reconcile, generation)
        assert held.provider_writer_state is ProviderWriterState.HELD
        closed = await asyncio.to_thread(adapter.graceful_stop, generation,
                                        operation_id=OperationId("ohf-op:fixture-close-"+mode))
        assert closed.process_liveness is ProcessLiveness.PROVEN_DEAD
        assert closed.provider_writer_state is ProviderWriterState.RELEASED
        report = json.loads(report_path.read_bytes())
        assert report["model_calls"] == 1 and report["native_close_settled"] and report["root_teardown_settled"]
        assert report["native_observation_reads"] == 2  # after initialize and before the one original Send
        return original_id, {"native": report, "result": result.to_wire(),
            "actual_process": vars(started.process), "currentness_checks": len(calls),
            "turn_writer_state": held.provider_writer_state.value, "closed_writer_state": closed.provider_writer_state.value}
    finally:
        if closed is None and adapter.native is not None and adapter.native.resource is not None:
            if adapter.native._closing is None:
                await adapter.native.close("fixture failure cleanup")


def test_full_native_ohf_adapter_stream_stop_and_exact_resume(tmp_path):
    supply, node = supplied()
    state = tmp_path.resolve()
    for name in ("workspace", "home", "dsh", "agents", "captures"):
        (state/name).mkdir(mode=0o700)
    async def exercise():
        session_id, first = await generation(supply, node, state, "new")
        resumed_id, resumed = await generation(supply, node, state, "resume", session_id)
        assert session_id == resumed_id and resumed["native"]["recovered_interrupted"]
        return {"schema": "mastermind.dsh_native_ohf_adapter_fixture.v1",
                "production_armed": False, "provider_calls": 0,
                "authority": "explicit laboratory callbacks, not installed Executive",
                "new": first, "resume": resumed}
    proof = asyncio.run(exercise())
    (state/"native-ohf-adapter-proof.json").write_text(json.dumps(proof, indent=2)+"\n")
