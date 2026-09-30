"""Model-free lifecycle proofs for the worker-local Operator Harness broker."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import sys
import stat
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

from control_plane import executive_worker_broker as broker_module
from control_plane import visible_turn_projection as visible_turn_projection_module
from control_plane.codex_worker import BinaryAttestation, CodexWorkerAdapter
from control_plane.worker_adapter import construct_reviewed_adapter
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.executive_orchestration_principal import (
    OSProcessCredentialObservation,
    ProviderHomeIdentityObservation,
)
from control_plane.executive_orchestration_result import RawRoleResultObservation
from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    BrokerPolicy,
    BrokerProtocolError,
    BrokerStateError,
    ExecutiveWorkerBroker,
    PeerCredentials,
    UIDSweepReceipt,
    UID_SWEEP_SCHEMA_VERSION,
    WorkerBrokerError,
)
from control_plane.operator_harness_contract import (
    AuthRealmFact,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    WorkspaceIdentity,
    compare_launch,
)
from control_plane.operator_harness_wire import to_wire
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_STATUS_SCHEMA,
    OperatorMaterializationReceiptError,
    canonical_json_bytes,
    materialization_receipt_path,
)
from control_plane.worker_browser_b1 import BrowserReviewReceipt
from control_plane.visible_turn_projection import (
    MAX_ENCODED_READ_BYTES,
    MAX_ITEM_BYTES,
    MAX_ITEMS_PER_TURN,
    MAX_PREBIND_ITEMS,
    ProjectionError,
    TurnKey,
    VisibleTurnProjection,
)


class _Sweeper:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.lifecycle: list[str] | None = None
        self.residual_pids_after: tuple[int, ...] = ()

    def sweep(self, reason: str) -> UIDSweepReceipt:
        self.calls.append(reason)
        if self.lifecycle is not None:
            self.lifecycle.append(f"uid_sweep:{reason}")
        return UIDSweepReceipt(
            schema_version=UID_SWEEP_SCHEMA_VERSION,
            observed_at="2026-08-24T00:00:00+00:00",
            reason=reason,
            worker_uid=os.geteuid(),
            broker_pid=os.getpid(),
            residual_pids_before=(),
            residual_pids_after=self.residual_pids_after,
            signal_name="SIGKILL",
            signal_sent=False,
            quiescent_observations=2,
        )


def _reviewed_codex_adapter(root: Path) -> CodexWorkerAdapter:
    root.mkdir(parents=True, exist_ok=True)
    binary = root / "fake-codex"
    if not binary.exists():
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o700)
    info = binary.lstat()
    attestation = BinaryAttestation(
        path=str(binary),
        real_path=str(binary.resolve()),
        version="test-0",
        sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        team_identifier=None,
        size=info.st_size,
        device=info.st_dev,
        inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
        gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )
    codex_home = root / "codex-home"
    codex_home.mkdir(mode=0o700, exist_ok=True)
    return construct_reviewed_adapter(  # type: ignore[return-value]
        "codex-cli",
        binary,
        codex_home=codex_home,
        binary_attestation=attestation,
        allowed_versions=frozenset({"test-0"}),
        required_team_identifier=None,
    )


class _OperatorAdapter:
    def __init__(
        self,
        requested: RequestedExecutionProfile,
        provider_home: Path,
        prompt_loader,
    ) -> None:
        self.requested = requested
        self.provider_home = provider_home
        self.prompt_loader = prompt_loader
        self.process = ProcessIdentityObservation(7001, 7001, "start-7001", "boot")
        self.turn: TurnRef | None = None
        self.prompts: list[str] = []
        self.lifecycle: list[str] = []
        self.resource = None
        self.visible_turn_projection = VisibleTurnProjection()
        self._generations = {}
        self.gate = threading.Event()
        self.gate.set()

    def bind_attempt_resource(self, resource, **_kwargs):
        self.lifecycle.append("resource_bind")
        self.resource = resource

    def validate_requested_profile(self, requested):
        return ProfileValidation(requested, requested == self.requested, ())

    def start_session(self, **_kwargs):
        self.lifecycle.append("provider_start")
        return SessionStartObservation("thread-1", self.process)

    def resume_session(self, *, provider_session, **_kwargs):
        self.lifecycle.append("provider_resume")
        return SessionStartObservation(provider_session.provider_session_id, self.process)

    def observed_attestation(self, _generation):
        return ObservedHarnessAttestation(
            served_model=self.requested.requested_model,
            harness_version=self.requested.harness_version,
            harness_binary_digest=self.requested.harness_binary_digest,
            capabilities=(),
            effective_skills=(),
            effective_mcp=(),
            effective_plugins_or_apps=(),
            sandbox_state="read-only",
            approval_state="never",
            network_state="disabled",
            effective_config_digest="d" * 64,
            auth=AuthRealmFact(
                worker_id=self.requested.worker_id,
                provider=self.requested.provider,
            ),
            workspace=self.requested.workspace,
            supports_subagent_capability_ceiling=ObservedTriState.FALSE,
        )

    def observe_process_credentials(self, _generation):
        return OSProcessCredentialObservation(
            process_identity={
                "pid": self.process.pid,
                "pgid": self.process.pgid,
                "process_start_identity": self.process.process_start_identity,
                "boot_id": self.process.boot_id,
            },
            os_principal_name="fixture-worker",
            os_principal_uid=os.geteuid(),
        )

    def observe_provider_home_identity(self, _generation):
        info = self.provider_home.lstat()
        return ProviderHomeIdentityObservation(
            {
                "path": str(self.provider_home),
                "device": info.st_dev,
                "inode": info.st_ino,
                "uid": info.st_uid,
                "gid": info.st_gid,
                "mode": stat.S_IMODE(info.st_mode),
            }
        )

    def begin_turn(self, *, turn, **_kwargs):
        self.turn = turn
        self.prompts.append(self.prompt_loader(turn))
        self._generations[turn.process_generation_id] = type(
            "GenerationState",
            (),
            {"turns": {turn.turn_id: "native-turn-1"}},
        )()
        return TurnStartObservation("native-turn-1", True)

    def mint_observer_grant(self, turn):
        return self.visible_turn_projection.mint_grant(
            TurnKey(
                turn.attempt_id,
                turn.session_epoch_id,
                turn.process_generation_id,
                1,
                "codex-01",
                turn.turn_id,
                self._generations[turn.process_generation_id].turns[turn.turn_id],
            )
        )

    def read_events(self, cursor, *, timeout_seconds):
        assert timeout_seconds > 0 and self.turn is not None
        self.gate.wait()
        return (
            (
                NormalizedEvent(
                    self.turn.attempt_id,
                    self.turn.session_epoch_id,
                    self.turn.process_generation_id,
                    self.turn.turn_id,
                    "turn.completed",
                    payload_redacted={"status": "complete"},
                ),
            ),
            EventCursor(
                cursor.attempt_id,
                cursor.session_epoch_id,
                cursor.process_generation_id,
                local_sequence=1,
                turn_id=cursor.turn_id,
            ),
        )

    def collect_candidate_result(self, turn):
        return CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "e" * 64,
            "bounded candidate",
        )

    def publish_visible(self, text, state, *, native_turn_id="native-turn-1"):
        turn = self.turn
        assert turn is not None
        key = TurnKey(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            1,
            "codex-01",
            turn.turn_id,
            native_turn_id,
        )
        self.visible_turn_projection.publish(
            key,
            method="item/completed",
            params={"item": {"id": text, "sequence": 1, "type": "agentMessage", "text": text}},
        )

    def observe_raw_role_result(self, turn):
        raw = "{}"
        return RawRoleResultObservation(
            attempt_id=turn.attempt_id,
            session_epoch_id=turn.session_epoch_id,
            process_generation_id=turn.process_generation_id,
            turn_id=turn.turn_id,
            provider_session_id="thread-1",
            provider_native_turn_id="native-turn-1",
            provider_turn_artifact_digest="e" * 64,
            canonical_result_json=raw,
            canonical_result_digest=hashlib.sha256(raw.encode()).hexdigest(),
            canonical_result_byte_length=len(raw),
        )

    def interrupt_turn(self, _turn, *, operation_id):
        assert operation_id.command_id.startswith("ohf-op:")

    def graceful_stop(self, _generation, **_kwargs):
        self.lifecycle.append("provider_stop")
        return ReconcileObservation(
            ProcessLiveness.PROVEN_DEAD,
            self.process,
            False,
            ProviderWriterState.RELEASED,
            "thread-1",
            "d" * 64,
        )

    cancel = graceful_stop

    def reconcile(self, _generation):
        return ReconcileObservation(
            ProcessLiveness.ALIVE,
            self.process,
            True,
            ProviderWriterState.HELD,
            "thread-1",
            "d" * 64,
        )


def _request(operation: str, payload: dict, suffix: str) -> dict:
    return {
        "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
        "request_id": f"req-{suffix}",
        "operation": operation,
        "payload": payload,
    }


def _materialization_payload(
    profile: RequestedExecutionProfile,
    epoch: SessionEpochRef,
    generation: ProcessGenerationRef,
    *,
    resume: bool = False,
    provider_session_id: str = "thread-1",
) -> dict:
    payload = {
        "operation_id": to_wire(
            OperationId(
                f"ohf-op:recover-resume:{epoch.attempt_id}"
                if resume
                else f"ohf-op:start:{epoch.attempt_id}"
            )
        ),
        "requested": to_wire(profile),
        "epoch": to_wire(epoch),
        "generation": to_wire(generation),
    }
    if resume:
        payload["provider_session"] = to_wire(
            ProviderSessionHandoff(provider_session_id, epoch.worker_id)
        )
    return payload


def _fixture(tmp_path: Path, *, armed: bool = True, autonomy_guard=None):
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "job-1"
    run_root = tmp_path / "runs"
    provider_home = tmp_path / "provider-home"
    for path in (workspace, run_root, provider_home):
        path.mkdir(parents=True, mode=0o700)
    info = workspace.lstat()
    profile = RequestedExecutionProfile(
        worker_id="codex-01",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=WorkspaceIdentity(
            str(workspace), "b" * 40, info.st_dev, info.st_ino, info.st_uid, info.st_gid
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
    )
    policy = BrokerPolicy(
        control_uid=os.geteuid() + 1000 if os.geteuid() != 0 else 501,
        worker_uid=os.geteuid(),
        worker_gid=os.getegid(),
        worker_user="fixture-worker",
        worker_id="codex-01",
        workspace_root=workspace_root,
        run_root=run_root,
        provider_home=provider_home,
        allowed_supplementary_gids=frozenset(set(os.getgroups()) - {os.getegid()}),
    )
    adapters: list[_OperatorAdapter] = []

    def factory(_workspace, prompt_loader, requested):
        assert requested == profile
        adapter = _OperatorAdapter(profile, provider_home, prompt_loader)
        adapters.append(adapter)
        return adapter

    sweeper = _Sweeper()
    broker = ExecutiveWorkerBroker(
        _reviewed_codex_adapter(tmp_path / "reviewed-adapter"),
        policy,
        sweeper,
        operator_adapter_factory=factory,
        operator_harness_armed=armed,
        autonomy_guard=(autonomy_guard if armed else None)
        if autonomy_guard is not None
        else (lambda: None if armed else None),
        autonomy_canary_factory=(lambda payload: {"bound": dict(payload)})
        if armed
        else None,
    )
    peer = PeerCredentials(policy.control_uid, policy.worker_gid, 100)
    return broker, peer, profile, sweeper, adapters


def _real_lc1_broker_turn(
    tmp_path: Path, gate: Path, *, item_gate: Path | None = None
):
    broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
    python = Path(sys.executable).resolve()
    provider_home = tmp_path / "provider-home"
    provider_home.chmod(0o700)
    (provider_home / "auth.json").write_text(
        "fixture credential bytes", encoding="utf-8"
    )
    (provider_home / "auth.json").chmod(0o600)
    gate_log = tmp_path / "gate.log"
    effect_log = tmp_path / "effects.log"
    adapter = CodexOperatorAdapter(
        binary_path=python,
        codex_home=provider_home,
        workspace_root=Path(profile.workspace.workspace_path),
        worker_id="codex-01",
        app_server_argv=(str(python), "-m", "scripts.ohf.fake_app_server"),
        expected_harness_version="ohf-fake-app-server/p0b",
        network_policy="disabled",
        turn_input_loader=lambda _turn: "LC1 real nonterminal turn",
        base_sha_resolver=lambda _path: profile.workspace.base_sha,
        process_identity_observer=lambda pid: ProcessIdentityObservation(
            pid, pid, f"start-{pid}", "boot"
        ),
        extra_env={
            "PYTHONPATH": str(REPO_ROOT),
            "OHF_FAKE_STATE": str(tmp_path / "fake-state.json"),
            "OHF_FAKE_WORKSPACE": str(Path(profile.workspace.workspace_path)),
            "OHF_FAKE_SKILL_ROOT": str(
                Path(profile.workspace.workspace_path) / ".agents" / "skills"
            ),
            "OHF_FAKE_MODEL": profile.requested_model,
            "OHF_FAKE_MCP_GONE": "1",
            "OHF_FAKE_BUNDLED_DISABLED": "1",
            "OHF_FAKE_GATE_MODE": "held",
            "OHF_FAKE_GATE_PATH": str(gate),
            "OHF_FAKE_GATE_LOG": str(gate_log),
            "OHF_FAKE_ITEM_GATE_PATH": (
                str(item_gate) if item_gate is not None else ""
            ),
            "OHF_FAKE_EFFECT_COUNTERS": str(effect_log),
            "OHF_FAKE_TURN_REPLY": '{"r623-r3":"complete"}',
            "OHF_FAKE_VISIBLE_UPDATES": ";".join(
                ("LC1 real partial", "LC1 real final")
            ),
        },
    )
    profile = dataclasses.replace(
        profile,
        harness_binary_digest=adapter.binary_digest,
        harness_version="ohf-fake-app-server/p0b",
    )
    adapters.append(adapter)
    broker.operator_adapter_factory = (
        lambda _workspace, _turn_loader, requested: adapter
    )
    return broker, peer, profile, adapter


def test_armed_operator_broker_requires_runtime_autonomy_guard(tmp_path: Path) -> None:
    broker, _peer, _profile, _sweeper, _adapters = _fixture(
        tmp_path,
        armed=False,
    )
    with pytest.raises(WorkerBrokerError, match="autonomy guard"):
        ExecutiveWorkerBroker(
            broker.adapter,
            broker.policy,
            broker.sweeper,
            operator_adapter_factory=broker.operator_adapter_factory,
            operator_harness_armed=True,
            autonomy_canary_factory=lambda payload: dict(payload),
        )


def test_armed_operator_broker_refuses_before_startup_sweep(tmp_path: Path) -> None:
    def refuse() -> None:
        raise RuntimeError("private receipt diagnostic")

    broker, _peer, _profile, sweeper, _adapters = _fixture(
        tmp_path,
        autonomy_guard=refuse,
    )
    with pytest.raises(BrokerStateError, match="autonomy receipt refused") as blocked:
        broker.initialize()
    assert "private receipt diagnostic" not in str(blocked.value)
    assert sweeper.calls == []


def test_operator_autonomy_guard_rechecks_before_each_provider_effect(tmp_path: Path) -> None:
    calls = 0

    def guard() -> None:
        nonlocal calls
        calls += 1
        if calls >= 4:
            raise RuntimeError("expired receipt detail")

    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(
            tmp_path,
            autonomy_guard=guard,
        )
        broker.initialize()
        epoch = SessionEpochRef("epoch-guard", "ATT-GUARD", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-guard", "epoch-guard", 1, "codex-01"
        )
        await broker.execute(
            _request(
                "ohf-start",
                {
                    "operation_id": to_wire(OperationId("ohf-op:start:ATT-GUARD")),
                    "requested": to_wire(profile),
                    "epoch": to_wire(epoch),
                    "generation": to_wire(generation),
                },
                "start-guard",
            ),
            peer=peer,
        )
        turn = TurnRef(
            "turn-guard", "epoch-guard", "generation-guard", "ATT-GUARD"
        )
        launch = compare_launch(
            profile,
            adapters[0].observed_attestation(generation),
        )
        with pytest.raises(BrokerStateError, match="autonomy receipt refused") as blocked:
            await broker.execute(
                _request(
                    "ohf-begin-turn",
                    {
                        "operation_id": to_wire(
                            OperationId("ohf-op:begin-turn-guard")
                        ),
                        "turn": to_wire(turn),
                        "generation": to_wire(generation),
                        "launch": to_wire(launch),
                        "prompt": "bounded prompt",
                    },
                    "begin-turn-guard",
                ),
                peer=peer,
            )
        assert "expired receipt detail" not in str(blocked.value)
        assert adapters[0].prompts == []

    asyncio.run(scenario())


def test_browser_resource_is_generation_bound_and_sealed_only_after_uid_sweep(
    tmp_path: Path,
) -> None:
    lifecycle: list[str] = []

    class Resource:
        def __init__(self, epoch, generation) -> None:
            self.epoch = epoch
            self.generation = generation

        def start(self) -> None:
            lifecycle.append("resource_start")

        def stop(self) -> None:
            lifecycle.append("resource_stop")

        def seal_after_uid_sweep(self, sweep):
            assert sweep.passed is True
            lifecycle.append("receipt_seal")
            return BrowserReviewReceipt(
                schema_version="mastermind.browser_review_receipt/v1",
                attempt_id=self.epoch.attempt_id,
                session_epoch_id=self.epoch.session_epoch_id,
                process_generation_id=self.generation.process_generation_id,
                workspace=WorkspaceIdentity("/tmp/browser", "a" * 40, 1, 2, 3, 4),
                devserver={"local_origin": "http://127.0.0.1:48101", "manifest_digest": "b" * 64},
                capability={"manifest_digest": "c" * 64, "profile_digest": "d" * 64, "profile_id": "operator.browser.local-review.v1"},
                playwright_mcp={"identity": "playwright", "tool_schema_digest": "e" * 64, "version": "1.63.0-alpha-2026-08-05"},
                    browser={
                        "executable": "/tmp/chromium",
                        "executable_sha256": "f" * 64,
                        "revision": "1237",
                        "runtime_manifest_digest": "7" * 64,
                    },
                viewports=({"width": 1440, "height": 900}, {"width": 390, "height": 844}),
                artifacts={
                    "screenshots": [
                        {"bytes": 10, "relative_path": "desktop.png", "sha256": "0" * 64, "viewport": {"width": 1440, "height": 900}},
                        {"bytes": 10, "relative_path": "mobile.png", "sha256": "1" * 64, "viewport": {"width": 390, "height": 844}},
                    ],
                    "console": {"bytes": 64, "observed": True, "rows": 1, "sha256": "2" * 64},
                    "mcp_guard": {
                        "bytes": 4096,
                        "relative_path": "browser-mcp-guard-evidence.json",
                        "schema_version": "mastermind.browser_mcp_guard_evidence/v2",
                        "sha256": "8" * 64,
                    },
                    "network": {"bytes": 64, "observed": True, "rows": 1, "sha256": "3" * 64},
                },
                egress_falsifiers={
                    "external_fetch": "REFUSED",
                    "external_http": "REFUSED",
                    "external_https": "REFUSED",
                    "external_redirect": "REFUSED",
                    "external_subresource": "REFUSED",
                    "external_websocket": "REFUSED",
                    "file_url": "REFUSED",
                    "proxy_override": "REFUSED",
                },
                external_egress_observed=False,
                visual_judgment={
                    "defective_variant": "B",
                    "fixture_nonce": "opaque-broker",
                    "image_sha256": ["4" * 64, "5" * 64],
                    "reason": "visible clipping",
                    "source": "model_image_content",
                },
                cleanup={
                    "browser_absent": True,
                    "devserver_absent": True,
                    "mcp_absent": True,
                    "proxy_absent": True,
                    "uid_sweep_digest": "6" * 64,
                    "uid_sweep_passed": True,
                },
                tracked_workspace_changes_after_review=False,
            )

    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)

        def resource_factory(_workspace, requested, epoch, generation):
            assert requested == profile
            adapters[-1].lifecycle = lifecycle
            return Resource(epoch, generation)

        broker.operator_resource_factory = resource_factory
        sweeper.lifecycle = lifecycle
        epoch = SessionEpochRef("epoch-browser", "ATT-BROWSER", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-browser", "epoch-browser", 1, "codex-01"
        )
        await broker.execute(
            _request(
                "ohf-start",
                {
                    "operation_id": to_wire(OperationId("ohf-op:start:ATT-BROWSER")),
                    "requested": to_wire(profile),
                    "epoch": to_wire(epoch),
                    "generation": to_wire(generation),
                },
                "start-browser",
            ),
            peer=peer,
        )
        stopped = await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(OperationId("ohf-op:stop-browser")),
                    "generation": to_wire(generation),
                },
                "stop-browser",
            ),
            peer=peer,
        )
        assert lifecycle == [
            "resource_start",
            "resource_bind",
            "provider_start",
            "provider_stop",
            "resource_stop",
            "uid_sweep:operator_terminal",
            "receipt_seal",
        ]
        assert sweeper.calls == ["operator_terminal"]
        assert stopped["result"]["artifact_receipt"]["attempt_id"] == "ATT-BROWSER"
        assert "receipt_digest" not in stopped["result"]["artifact_receipt"]

    asyncio.run(scenario())


def test_browser_receipt_is_not_sealed_when_uid_sweep_is_not_passing(
    tmp_path: Path,
) -> None:
    lifecycle: list[str] = []

    class Resource:
        def start(self) -> None:
            lifecycle.append("resource_start")

        def stop(self) -> None:
            lifecycle.append("resource_stop")

        def seal_after_uid_sweep(self, _sweep):
            lifecycle.append("receipt_seal")
            raise AssertionError("a nonpassing UID sweep must never seal evidence")

    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)
        sweeper.lifecycle = lifecycle
        sweeper.residual_pids_after = (9001,)
        broker.operator_resource_factory = (
            lambda _workspace, _requested, _epoch, _generation: Resource()
        )
        adapters.clear()
        epoch = SessionEpochRef("epoch-sweep-red", "ATT-SWEEP-RED", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-sweep-red", "epoch-sweep-red", 1, "codex-01"
        )
        await broker.execute(
            _request(
                "ohf-start",
                {
                    "operation_id": to_wire(OperationId("ohf-op:start:ATT-SWEEP-RED")),
                    "requested": to_wire(profile),
                    "epoch": to_wire(epoch),
                    "generation": to_wire(generation),
                },
                "start-sweep-red",
            ),
            peer=peer,
        )
        with pytest.raises(BrokerStateError, match="UID sweep"):
            await broker.execute(
                _request(
                    "ohf-stop",
                    {
                        "operation_id": to_wire(OperationId("ohf-op:stop-sweep-red")),
                        "generation": to_wire(generation),
                    },
                    "stop-sweep-red",
                ),
                peer=peer,
            )
        assert lifecycle == [
            "resource_start",
            "resource_stop",
            "uid_sweep:operator_terminal",
        ]

    asyncio.run(scenario())


def test_autonomy_canary_is_one_typed_idle_nonprovider_operation(tmp_path: Path) -> None:
    observed: list[dict] = []

    def factory(payload):
        observed.append(dict(payload))
        return {
            "schema_version": "mastermind.executive_secret_canary_envelope/v1",
            "secret_canary": {"passed": True},
            "control_environment_probe": {"passed": True},
            "control_environment_probe_sha256": "f" * 64,
        }

    async def scenario() -> None:
        broker, peer, _profile, _sweeper, adapters = _fixture(tmp_path)
        broker.autonomy_canary_factory = factory
        broker.initialize()
        attestation = {
            "schema_version": "mastermind.executive_control_environment_attestation/v1",
            "process_identity": {"pid": 1234},
        }
        response = await broker.execute(
            _request(
                "autonomy-canary",
                {"control_environment_attestation": attestation},
                "autonomy-canary",
            ),
            peer=peer,
        )
        assert response["result"]["envelope"]["control_environment_probe_sha256"] == (
            "f" * 64
        )
        assert observed == [{"control_environment_attestation": attestation}]
        assert adapters == []

        with pytest.raises(BrokerProtocolError, match="payload"):
            await broker.execute(
                _request("autonomy-canary", {"path": "/tmp/forbidden"}, "bad-canary"),
                peer=peer,
            )

    asyncio.run(scenario())


def test_operator_broker_runs_one_exact_generation_and_cleans_uid(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-1", "ATT-1", "codex-01", 1)
        generation = ProcessGenerationRef("generation-1", "epoch-1", 1, "codex-01")
        start = await broker.execute(
            _request(
                "ohf-start",
                {
                    "operation_id": to_wire(OperationId("ohf-op:start:ATT-1")),
                    "requested": to_wire(profile),
                    "epoch": to_wire(epoch),
                    "generation": to_wire(generation),
                },
                "start",
            ),
            peer=peer,
        )
        assert start["result"]["observation"]["provider_session_id"] == "thread-1"
        turn = TurnRef("turn-1", "epoch-1", "generation-1", "ATT-1")
        observed = adapters[-1].observed_attestation(generation)
        await broker.execute(
            _request(
                "ohf-begin-turn",
                {
                    "operation_id": to_wire(OperationId("ohf-op:turn-1")),
                    "turn": to_wire(turn),
                    "generation": to_wire(generation),
                    "launch": to_wire(compare_launch(profile, observed)),
                    "prompt": "Produce one bounded read-only plan.",
                },
                "turn",
            ),
            peer=peer,
        )
        with pytest.raises(BrokerProtocolError, match="cursor"):
            await broker.execute(
                _request(
                    "ohf-collect-turn",
                    {
                        "turn": to_wire(turn),
                        "cursor": to_wire(
                            EventCursor(
                                "ATT-OTHER",
                                "epoch-1",
                                "generation-1",
                                turn_id="turn-1",
                            )
                        ),
                        "timeout_seconds": 30.0,
                    },
                    "collect-wrong-cursor",
                ),
                peer=peer,
            )
        collected = await broker.execute(
            _request(
                "ohf-collect-turn",
                {
                    "turn": to_wire(turn),
                    "cursor": to_wire(
                        EventCursor("ATT-1", "epoch-1", "generation-1", turn_id="turn-1")
                    ),
                    "timeout_seconds": 30.0,
                },
                "collect",
            ),
            peer=peer,
        )
        assert collected["result"]["candidate"]["complete_job_permitted"] is False
        assert adapters[-1].prompts == ["Produce one bounded read-only plan."]
        grant = adapters[-1].mint_observer_grant(turn)
        observed = await broker.execute(
            _request(
                "ohf-observe-turn",
                {
                    "attempt": "ATT-1",
                    "epoch": "epoch-1",
                    "generation": "generation-1",
                    "turn": "turn-1",
                    "reader_grant": grant,
                    "cursor": None,
                    "max_items": 64,
                },
                "observe",
            ),
            peer=peer,
        )
        assert observed["result"]["items"] == []
        assert observed["result"]["terminal"] is False
        assert adapters[-1].lifecycle == ["provider_start"]
        stopped = await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(OperationId("ohf-op:stop-1")),
                    "generation": to_wire(generation),
                },
                "stop",
            ),
            peer=peer,
        )
        assert stopped["result"]["observation"]["process_liveness"] == "PROVEN_DEAD"
        assert sweeper.calls == ["operator_terminal"]
        status = await broker.execute(_request("status", {}, "status"), peer=peer)
        assert status["result"]["active_operator_attempt_id"] is None

    asyncio.run(scenario())


def test_operator_broker_refuses_unarmed_and_cross_attempt_session_reuse(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        unarmed, peer, profile, _sweeper, _adapters = _fixture(
            tmp_path / "unarmed", armed=False
        )
        epoch = SessionEpochRef("epoch-1", "ATT-1", "codex-01", 1)
        generation = ProcessGenerationRef("generation-1", "epoch-1", 1, "codex-01")
        payload = {
            "operation_id": to_wire(OperationId("ohf-op:start:ATT-1")),
            "requested": to_wire(profile),
            "epoch": to_wire(epoch),
            "generation": to_wire(generation),
        }
        with pytest.raises(BrokerStateError, match="not armed"):
            await unarmed.execute(_request("ohf-start", payload, "unarmed"), peer=peer)

        broker, peer, profile, _sweeper, _adapters = _fixture(tmp_path / "armed")
        armed_payload = {
            **payload,
            "requested": to_wire(profile),
        }
        await broker.execute(
            _request("ohf-start", armed_payload, "start"), peer=peer
        )
        await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(OperationId("ohf-op:stop-cross")),
                    "generation": to_wire(generation),
                },
                "stop",
            ),
            peer=peer,
        )
        epoch_two = SessionEpochRef("epoch-2", "ATT-2", "codex-01", 1)
        generation_two = ProcessGenerationRef(
            "generation-2", "epoch-2", 2, "codex-01"
        )
        with pytest.raises(BrokerStateError, match="across Executive Attempts"):
            await broker.execute(
                _request(
                    "ohf-resume",
                    {
                        "operation_id": to_wire(
                            OperationId("ohf-op:recover-resume:ATT-2")
                        ),
                        "requested": to_wire(profile),
                        "epoch": to_wire(epoch_two),
                        "generation": to_wire(generation_two),
                        "provider_session": to_wire(
                            ProviderSessionHandoff("thread-1", "codex-01")
                        ),
                    },
                    "resume",
                ),
                peer=peer,
            )

    asyncio.run(scenario())


def test_operator_restart_absence_uses_fresh_dedicated_uid_sweep(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, _profile, sweeper, _adapters = _fixture(tmp_path)
        generation = ProcessGenerationRef("generation-1", "epoch-1", 1, "codex-01")
        process = ProcessIdentityObservation(7001, 7001, "start-7001", "boot")
        result = await broker.execute(
            _request(
                "ohf-reconcile-absence",
                {
                    "generation": to_wire(generation),
                    "process": to_wire(process),
                    "provider_session_id": "thread-1",
                    "config_digest": "d" * 64,
                },
                "absence",
            ),
            peer=peer,
        )
        assert result["result"]["observation"]["process_liveness"] == "PROVEN_DEAD"
        assert result["result"]["observation"]["provider_writer_state"] == "RELEASED"
        assert result["result"]["uid_sweep"]["passed"] is True
        assert sweeper.calls == ["operator_reconcile_absence"]

    asyncio.run(scenario())


def test_materialization_exact_replay_returns_receipt_without_second_provider_call(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-replay", "ATT-REPLAY", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-replay", "epoch-replay", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)

        first = await broker.execute(
            _request("ohf-start", payload, "replay-first"), peer=peer
        )
        replay = await broker.execute(
            _request("ohf-start", payload, "replay-second"), peer=peer
        )

        assert first["result"] == replay["result"]
        assert first["result"]["materialization_receipt"]["operation_command_id"] == (
            "ohf-op:start:ATT-REPLAY"
        )
        assert adapters[0].lifecycle.count("provider_start") == 1

        status = await broker.execute(
            _request("ohf-materialization-status", payload, "replay-status"),
            peer=peer,
        )
        assert status["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "RECEIPT_CURRENT_IN_LIVE_BROKER",
            "receipt": first["result"]["materialization_receipt"],
        }

    asyncio.run(scenario())


def test_materialization_status_recovers_lost_response_after_broker_restart(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-lost", "ATT-LOST", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-lost", "epoch-lost", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)

        # The caller deliberately drops this successful response, modeling a
        # connection loss after the worker committed the receipt.
        await broker.execute(_request("ohf-start", payload, "lost"), peer=peer)
        assert adapters[0].lifecycle.count("provider_start") == 1

        restarted = ExecutiveWorkerBroker(
            broker.adapter,
            broker.policy,
            _Sweeper(),
            operator_adapter_factory=broker.operator_adapter_factory,
            operator_harness_armed=True,
            autonomy_guard=lambda: None,
            autonomy_canary_factory=lambda value: dict(value),
        )
        status = await restarted.execute(
            _request("ohf-materialization-status", payload, "restart-status"),
            peer=peer,
        )
        assert status["result"]["status"] == "RECEIPT_ONLY_AFTER_RESTART"
        assert status["result"]["receipt"]["provider_session_id"] == "thread-1"

        with pytest.raises(BrokerStateError, match="receipt-only"):
            await restarted.execute(
                _request("ohf-start", payload, "restart-retry"), peer=peer
            )
        assert len(adapters) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda attestation: {**attestation, "served_model": "gpt-cross-spliced"},
        lambda attestation: {
            **attestation,
            "auth": {**attestation["auth"], "provider": "other-provider"},
        },
        lambda attestation: {
            **attestation,
            "workspace": {
                **attestation["workspace"],
                "workspace_path": "/cross-spliced/workspace",
            },
        },
        lambda attestation: {
            **attestation,
            "capabilities": [
                {
                    "kind": "skill",
                    "name": "cross-spliced-capability",
                    "skill_content_digest": None,
                    "tool_schema_digest": None,
                    "mcp_server_identity": None,
                    "mcp_server_version": None,
                    "mcp_auth_status": None,
                    "resource_contract_digest": None,
                }
            ],
        },
    ],
)
def test_restarted_status_refuses_cross_spliced_typed_attestation(
    tmp_path: Path,
    mutate,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, _adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-splice", "ATT-SPLICE", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-splice", "epoch-splice", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        result = await broker.execute(
            _request("ohf-start", payload, "splice-start"), peer=peer
        )
        receipt = result["result"]["materialization_receipt"]
        receipt["observed_attestation"] = mutate(
            dict(receipt["observed_attestation"])
        )
        unsigned = {
            key: value for key, value in receipt.items() if key != "receipt_digest"
        }
        receipt["receipt_digest"] = hashlib.sha256(
            canonical_json_bytes(unsigned)
        ).hexdigest()
        path = materialization_receipt_path(tmp_path / "runs", f"ohf-op:start:{epoch.attempt_id}")
        path.write_bytes(canonical_json_bytes(receipt))
        path.chmod(0o600)

        restarted = ExecutiveWorkerBroker(
            broker.adapter,
            broker.policy,
            _Sweeper(),
            operator_adapter_factory=broker.operator_adapter_factory,
            operator_harness_armed=True,
            autonomy_guard=lambda: None,
            autonomy_canary_factory=lambda value: dict(value),
        )
        status = await restarted.execute(
            _request("ohf-materialization-status", payload, "splice-status"),
            peer=peer,
        )
        assert status["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "CONFLICT",
            "receipt": None,
        }

    asyncio.run(scenario())


def test_g2_resume_persists_the_exact_handoff_receipt(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-resume", "ATT-RESUME", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-resume", "epoch-resume", 2, "codex-01"
        )
        payload = _materialization_payload(
            profile,
            epoch,
            generation,
            resume=True,
            provider_session_id="thread-resume",
        )
        result = await broker.execute(
            _request("ohf-resume", payload, "resume-g2"), peer=peer
        )
        receipt = result["result"]["materialization_receipt"]
        assert receipt["operation_command_id"] == (
            "ohf-op:recover-resume:ATT-RESUME"
        )
        assert receipt["operation_kind"] == "resume_session"
        assert receipt["generation_number"] == 2
        assert receipt["provider_session_id"] == "thread-resume"
        assert adapters[0].lifecycle == ["provider_resume"]

    asyncio.run(scenario())


def test_materialization_status_is_absent_or_conflict_without_provider_io(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-status", "ATT-STATUS", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-status", "epoch-status", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        absent = await broker.execute(
            _request("ohf-materialization-status", payload, "status-absent"),
            peer=peer,
        )
        assert absent["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "ABSENT",
            "receipt": None,
        }
        assert adapters == []

        await broker.execute(_request("ohf-start", payload, "status-start"), peer=peer)
        drifted = {
            **payload,
            "requested": {**payload["requested"], "requested_model": "gpt-drift"},
        }
        conflict = await broker.execute(
            _request("ohf-materialization-status", drifted, "status-conflict"),
            peer=peer,
        )
        assert conflict["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "CONFLICT",
            "receipt": None,
        }
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def test_materialization_concurrency_allows_exactly_one_provider_call(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        entered = threading.Event()
        release = threading.Event()
        original_factory = broker.operator_adapter_factory

        def blocking_factory(*args):
            assert original_factory is not None
            adapter = original_factory(*args)

            def blocking_start(**_kwargs):
                adapter.lifecycle.append("provider_start")
                entered.set()
                assert release.wait(3)
                return SessionStartObservation("thread-1", adapter.process)

            adapter.start_session = blocking_start
            return adapter

        broker.operator_adapter_factory = blocking_factory
        epoch = SessionEpochRef("epoch-race", "ATT-RACE", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-race", "epoch-race", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        first = asyncio.create_task(
            broker.execute(_request("ohf-start", payload, "race-first"), peer=peer)
        )
        assert await asyncio.to_thread(entered.wait, 2)
        with pytest.raises(BrokerStateError, match="active work"):
            await broker.execute(
                _request("ohf-start", payload, "race-second"), peer=peer
            )
        release.set()
        await first
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def test_materialization_status_is_conflict_while_provider_dispatch_is_in_flight(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        entered = threading.Event()
        release = threading.Event()
        original_factory = broker.operator_adapter_factory

        def blocking_factory(*args):
            assert original_factory is not None
            adapter = original_factory(*args)

            def blocking_start(**_kwargs):
                adapter.lifecycle.append("provider_start")
                entered.set()
                assert release.wait(3)
                return SessionStartObservation("thread-1", adapter.process)

            adapter.start_session = blocking_start
            return adapter

        broker.operator_adapter_factory = blocking_factory
        epoch = SessionEpochRef("epoch-status-race", "ATT-STATUS-RACE", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-status-race", "epoch-status-race", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        start = asyncio.create_task(
            broker.execute(_request("ohf-start", payload, "status-race-start"), peer=peer)
        )
        assert await asyncio.to_thread(entered.wait, 2)

        status = await broker.execute(
            _request("ohf-materialization-status", payload, "status-race-read"),
            peer=peer,
        )
        assert status["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "CONFLICT",
            "receipt": None,
        }

        release.set()
        await start
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def test_post_effect_receipt_failure_quarantines_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-red", "ATT-RED", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-red", "epoch-red", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)

        def fail_persistence(*_args, **_kwargs):
            raise OperatorMaterializationReceiptError("private disk diagnostic")

        monkeypatch.setattr(
            broker_module,
            "persist_operator_materialization_receipt",
            fail_persistence,
        )
        with pytest.raises(BrokerStateError, match="effect is unknown") as failed:
            await broker.execute(_request("ohf-start", payload, "red-first"), peer=peer)
        assert "private disk diagnostic" not in str(failed.value)
        assert adapters[0].lifecycle.count("provider_start") == 1
        assert sweeper.calls == []

        status = await broker.execute(
            _request("ohf-materialization-status", payload, "red-status"),
            peer=peer,
        )
        assert status["result"]["status"] == "CONFLICT"
        assert status["result"]["receipt"] is None

        with pytest.raises(BrokerStateError, match="quarantined"):
            await broker.execute(_request("ohf-start", payload, "red-retry"), peer=peer)
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def test_ambiguous_provider_response_quarantines_and_never_retries(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)
        original_factory = broker.operator_adapter_factory

        def ambiguous_factory(*args):
            assert original_factory is not None
            adapter = original_factory(*args)

            def ambiguous_start(**_kwargs):
                adapter.lifecycle.append("provider_start")
                raise TimeoutError("private ambiguous provider diagnostic")

            adapter.start_session = ambiguous_start
            return adapter

        broker.operator_adapter_factory = ambiguous_factory
        epoch = SessionEpochRef("epoch-ambiguous", "ATT-AMBIGUOUS", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-ambiguous", "epoch-ambiguous", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)

        with pytest.raises(BrokerStateError, match="effect is unknown") as failed:
            await broker.execute(
                _request("ohf-start", payload, "ambiguous-first"), peer=peer
            )
        assert "private ambiguous provider diagnostic" not in str(failed.value)
        assert adapters[0].lifecycle.count("provider_start") == 1
        assert sweeper.calls == []

        status = await broker.execute(
            _request("ohf-materialization-status", payload, "ambiguous-status"),
            peer=peer,
        )
        assert status["result"]["status"] == "CONFLICT"
        assert status["result"]["receipt"] is None

        with pytest.raises(BrokerStateError, match="quarantined"):
            await broker.execute(
                _request("ohf-start", payload, "ambiguous-retry"), peer=peer
            )
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def test_cancelled_provider_dispatch_stays_quarantined_while_thread_unwinds(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, sweeper, adapters = _fixture(tmp_path)
        entered = threading.Event()
        release = threading.Event()
        original_factory = broker.operator_adapter_factory

        def cancellable_factory(*args):
            assert original_factory is not None
            adapter = original_factory(*args)

            def cancellable_start(**_kwargs):
                adapter.lifecycle.append("provider_start")
                entered.set()
                assert release.wait(3)
                return SessionStartObservation("thread-cancelled", adapter.process)

            adapter.start_session = cancellable_start
            return adapter

        broker.operator_adapter_factory = cancellable_factory
        epoch = SessionEpochRef("epoch-cancelled", "ATT-CANCELLED", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-cancelled", "epoch-cancelled", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        task = asyncio.create_task(
            broker.execute(
                _request("ohf-start", payload, "cancelled-first"), peer=peer
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        status = await broker.execute(
            _request("ohf-materialization-status", payload, "cancelled-status"),
            peer=peer,
        )
        assert status["result"]["status"] == "CONFLICT"
        assert status["result"]["receipt"] is None
        with pytest.raises(BrokerStateError, match="quarantined"):
            await broker.execute(
                _request("ohf-start", payload, "cancelled-retry"), peer=peer
            )
        release.set()
        await asyncio.sleep(0)
        assert adapters[0].lifecycle.count("provider_start") == 1
        assert sweeper.calls == []

    asyncio.run(scenario())


def test_same_process_terminal_generation_is_not_restart_only(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
        epoch = SessionEpochRef("epoch-terminal", "ATT-TERMINAL", "codex-01", 1)
        generation = ProcessGenerationRef(
            "generation-terminal", "epoch-terminal", 1, "codex-01"
        )
        payload = _materialization_payload(profile, epoch, generation)
        await broker.execute(
            _request("ohf-start", payload, "terminal-start"), peer=peer
        )
        await broker.execute(
            _request(
                "ohf-stop",
                {
                    "operation_id": to_wire(OperationId("ohf-op:stop-terminal")),
                    "generation": to_wire(generation),
                },
                "terminal-stop",
            ),
            peer=peer,
        )

        status = await broker.execute(
            _request("ohf-materialization-status", payload, "terminal-status"),
            peer=peer,
        )
        assert status["result"] == {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "CONFLICT",
            "receipt": None,
        }
        assert adapters[0].lifecycle.count("provider_start") == 1

    asyncio.run(scenario())


def _observer_payload(turn, grant, cursor=None, max_items=64, **overrides):
    payload = {
        "attempt": turn.attempt_id,
        "epoch": turn.session_epoch_id,
        "generation": turn.process_generation_id,
        "turn": turn.turn_id,
        "reader_grant": grant,
        "cursor": cursor,
        "max_items": max_items,
    }
    payload.update(overrides)
    return payload


async def _lc1_broker_turn(tmp_path, suffix, prompt, *, release_gate=False):
    broker, peer, profile, _sweeper, adapters = _fixture(tmp_path)
    epoch = SessionEpochRef(f"epoch-{suffix}", f"ATT-{suffix.upper()}", "codex-01", 1)
    generation = ProcessGenerationRef(
        f"generation-{suffix}", f"epoch-{suffix}", 1, "codex-01"
    )
    await broker.execute(
        _request(
            "ohf-start",
            _materialization_payload(profile, epoch, generation),
            f"{suffix}-start",
        ),
        peer=peer,
    )
    turn = TurnRef(
        "turn-1", f"epoch-{suffix}", f"generation-{suffix}", f"ATT-{suffix.upper()}"
    )
    attestation = adapters[-1].observed_attestation(generation)
    await broker.execute(
        _request(
            "ohf-begin-turn",
            {
                "operation_id": to_wire(OperationId(f"ohf-op:{suffix}-turn")),
                "turn": to_wire(turn),
                "generation": to_wire(generation),
                "launch": to_wire(compare_launch(profile, attestation)),
                "prompt": prompt,
            },
            f"{suffix}-turn",
        ),
        peer=peer,
    )
    if release_gate:
        adapters[-1].gate.set()
    return broker, peer, turn, adapters


def test_lc1_fixture_stays_busy_until_gate_released(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "lc1", "LC1 gate-held turn"
        )
        collecting = asyncio.Event()
        adapters[-1].gate.clear()

        async def collect_gate_held():
            collecting.set()
            return await broker.execute(
                _request(
                    "ohf-collect-turn",
                    {
                        "turn": to_wire(turn),
                        "cursor": to_wire(
                            EventCursor(
                                turn.attempt_id,
                                turn.session_epoch_id,
                                turn.process_generation_id,
                                turn_id=turn.turn_id,
                            )
                        ),
                        "timeout_seconds": 5.0,
                    },
                    "lc1-collect",
                ),
                peer=peer,
            )

        task = asyncio.create_task(collect_gate_held())
        await asyncio.wait_for(collecting.wait(), timeout=1)
        await asyncio.sleep(0)
        assert broker._operator_run is not None and broker._operator_run.busy
        adapters[-1].gate.set()
        baseline = await task
        assert baseline["result"]["candidate"]["complete_job_permitted"] is False
        assert broker._operator_run is not None and not broker._operator_run.busy

    asyncio.run(scenario())


def test_ohf_real_chain_publishes_visible_items_while_controller_nonterminal(
    tmp_path: Path,
) -> None:
    gate = tmp_path / "terminal-gate"
    gate.touch()
    item_gate = tmp_path / "item-notification-gate"
    item_gate.touch()
    broker, peer, profile, adapter = _real_lc1_broker_turn(
        tmp_path, gate, item_gate=item_gate
    )
    epoch = SessionEpochRef(
        "epoch-r623-r3", "ATT-R623-R3", "codex-01", 1
    )
    generation = ProcessGenerationRef(
        "generation-r623-r3", "epoch-r623-r3", 1, "codex-01"
    )

    async def scenario() -> None:
        await broker.execute(
            _request(
                "ohf-start",
                _materialization_payload(profile, epoch, generation),
                "r623-r3-start",
            ),
            peer=peer,
        )
        turn = TurnRef(
            "turn-r623-r3",
            "epoch-r623-r3",
            "generation-r623-r3",
            "ATT-R623-R3",
        )
        await broker.execute(
            _request(
                "ohf-begin-turn",
                {
                    "operation_id": to_wire(
                        OperationId("ohf-op:r623-r3-turn")
                    ),
                    "turn": to_wire(turn),
                    "generation": to_wire(generation),
                    "launch": to_wire(compare_launch(profile, adapter.observed_attestation(generation))),
                    "prompt": "LC1 real nonterminal turn",
                },
                "r623-r3-turn",
            ),
            peer=peer,
        )
        grant = adapter.mint_observer_grant(turn)
        collecting = asyncio.Event()

        async def collect_controller_terminal():
            collecting.set()
            return await broker.execute(
                _request(
                    "ohf-collect-turn",
                    {
                        "turn": to_wire(turn),
                        "cursor": to_wire(
                            EventCursor(
                                turn.attempt_id,
                                turn.session_epoch_id,
                                turn.process_generation_id,
                                turn_id=turn.turn_id,
                            )
                        ),
                        "timeout_seconds": 5.0,
                    },
                    "r623-r3-collect",
                ),
                peer=peer,
            )

        collector = asyncio.create_task(collect_controller_terminal())
        await asyncio.wait_for(collecting.wait(), timeout=1)
        await asyncio.sleep(0)
        assert broker._operator_run is not None and broker._operator_run.busy
        item_gate.unlink()
        nonterminal_read = None
        expected_items = ["LC1 real partial", "LC1 real final"]
        lawful_prefixes = ([], ["LC1 real partial"], expected_items)
        for attempt in range(100):
            candidate_read = await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, grant),
                    f"r623-r3-nonterminal-read-{attempt}",
                ),
                peer=peer,
            )
            observed_items = [
                item["text"] for item in candidate_read["result"]["items"]
            ]
            # The observer may lawfully expose the first streamed item before
            # the second on a slower runner.  Preserve the ordering/completeness
            # contract and wait for the exact complete prefix instead of treating
            # the first nonempty snapshot as terminal observer evidence.
            assert observed_items in lawful_prefixes
            assert candidate_read["result"]["terminal"] is False
            assert not collector.done()
            if observed_items == expected_items:
                nonterminal_read = candidate_read
                break
            await asyncio.sleep(0.01)
        assert nonterminal_read is not None
        assert [
            item["text"] for item in nonterminal_read["result"]["items"]
        ] == expected_items
        nonterminal_cursor = nonterminal_read["result"]["next_cursor"]
        assert nonterminal_read["result"]["terminal"] is False
        assert not collector.done()

        gate.unlink()
        collected = await collector
        assert [
            event["kind"] for event in collected["result"]["events"]
        ][-1:] == ["turn/completed"]
        terminal_read = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(
                    turn,
                    grant,
                    cursor=nonterminal_cursor,
                ),
                "r623-r3-terminal-read",
            ),
            peer=peer,
        )
        assert terminal_read["result"]["terminal"] is True
        assert adapter._state(generation).client._next_id > 0
        adapter.graceful_stop(generation, operation_id=OperationId("ohf-op:r623-r3-stop"))

    asyncio.run(scenario())


def test_ohf_observer_sees_items_while_controller_waits_then_terminal_once(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "obs", "LC1 observed turn"
        )
        grant = adapters[-1].mint_observer_grant(turn)
        mid_read = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant),
                "obs-mid",
            ),
            peer=peer,
        )
        assert mid_read["result"]["items"] == []
        assert mid_read["result"]["terminal"] is False
        collecting = asyncio.Event()
        adapters[-1].gate.clear()

        async def collect_controller_terminal():
            collecting.set()
            return await broker.execute(
                _request(
                    "ohf-collect-turn",
                    {
                        "turn": to_wire(turn),
                        "cursor": to_wire(
                            EventCursor(
                                turn.attempt_id,
                                turn.session_epoch_id,
                                turn.process_generation_id,
                                turn_id=turn.turn_id,
                            )
                        ),
                        "timeout_seconds": 5.0,
                    },
                    "obs-collect",
                ),
                peer=peer,
            )

        collector = asyncio.create_task(collect_controller_terminal())
        await asyncio.wait_for(collecting.wait(), timeout=1)
        await asyncio.sleep(0)
        assert broker._operator_run is not None and broker._operator_run.busy
        adapters[-1].publish_visible("LC1 completed item", "completed")
        completed_read = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(
                    turn, grant, cursor=mid_read["result"]["next_cursor"]
                ),
                "obs-completed",
            ),
            peer=peer,
        )
        assert [item["text"] for item in completed_read["result"]["items"]] == [
            "LC1 completed item"
        ]
        adapters[-1].gate.set()
        collected = await collector
        assert collected["result"]["candidate"]["summary"] == "bounded candidate"
        terminal_read = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(
                    turn, grant, cursor=completed_read["result"]["next_cursor"]
                ),
                "obs-terminal",
            ),
            peer=peer,
        )
        assert terminal_read["result"]["items"] == []

    asyncio.run(scenario())


def test_ohf_slow_viewer_resyncs_by_cursor_without_stalling_controller(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path,
            "slow",
            "LC1 slow viewer turn",
            release_gate=True,
        )
        grant = adapters[-1].mint_observer_grant(turn)
        adapters[-1].gate.set()
        first = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant, max_items=1),
                "slow-1",
            ),
            peer=peer,
        )
        adapters[-1].publish_visible("first", "partial")
        adapters[-1].publish_visible("second", "partial")
        stale = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant, max_items=1),
                "slow-2",
            ),
            peer=peer,
        )
        cursor = stale["result"]["next_cursor"]
        full = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant, cursor=None, max_items=64),
                "slow-full",
            ),
            peer=peer,
        )
        assert [item["text"] for item in full["result"]["items"]] == ["first", "second"]
        resumed = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant, cursor=cursor, max_items=64),
                "slow-resume",
            ),
            peer=peer,
        )
        assert [item["text"] for item in resumed["result"]["items"]] == ["second"]

        projection = adapters[-1].visible_turn_projection
        first_key = projection.check_grant(grant)
        assert first_key is not None
        projection.arm_prebind(99)
        dropped = projection.drop_prebind("test_whole_drop")
        assert dropped is not None and dropped.reason == "test_whole_drop"
        assert projection.active_prebind_request_id() is None

    asyncio.run(scenario())


def test_ohf_two_viewers_have_independent_cursors_and_zero_control_effects(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path,
            "two",
            "LC1 two viewers",
            release_gate=True,
        )
        first_grant = adapters[-1].mint_observer_grant(turn)
        second_grant = adapters[-1].mint_observer_grant(turn)
        adapters[-1].gate.set()
        adapters[-1].publish_visible("visible-one", "partial")
        first = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, first_grant, max_items=1),
                "two-first",
            ),
            peer=peer,
        )
        second = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, second_grant),
                "two-second",
            ),
            peer=peer,
        )
        assert first_grant != second_grant
        assert first["result"]["next_cursor"] == second["result"]["next_cursor"]
        assert [item["text"] for item in first["result"]["items"]] == ["visible-one"]
        assert [item["text"] for item in second["result"]["items"]] == ["visible-one"]
        assert adapters[-1].prompts == ["LC1 two viewers"]
        assert adapters[-1].lifecycle == ["provider_start"]

    asyncio.run(scenario())


def test_ohf_disconnected_viewer_causes_zero_worker_effects(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "disconnect", "LC1 disconnect"
        )
        grant = adapters[-1].mint_observer_grant(turn)
        first = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant),
                "disconnect-read",
            ),
            peer=peer,
        )
        adapters[-1].visible_turn_projection.revoke_grant(grant)
        with pytest.raises(BrokerStateError, match="READER_REVOKED"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(
                        turn, grant, cursor=first["result"]["next_cursor"]
                    ),
                    "disconnect-refused",
                ),
                peer=peer,
            )
        assert adapters[-1].prompts == ["LC1 disconnect"]
        assert adapters[-1].lifecycle == ["provider_start"]
        assert adapters[-1].visible_turn_projection.check_grant(grant) is None

    asyncio.run(scenario())


def test_ohf_parser_failure_records_gap_without_blocking_controller(
    tmp_path: Path,
) -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-PARSER", "epoch-parser", "generation-parser", 1, "codex-01",
        "turn-parser", "native-parser",
    )
    grant = projection.mint_grant(key)
    projection.publish(
        key,
        method="item/completed",
        params={"item": {"type": "agentMessage", "id": "missing-sequence"}},
    )
    projection.publish(
        key,
        method="item/completed",
        params={
            "item": {
                "id": "valid-item",
                "sequence": 1,
                "type": "agentMessage",
                "text": "valid",
            }
        },
    )
    result = projection.read(key, reader_grant=grant, cursor=None, max_items=64)
    assert [item.text for item in result.items] == ["valid"]
    assert [gap.reason for gap in result.gaps] == ["parser_failure"]
    assert projection.parser_gaps() == ()

    clock = iter([0.0, 0.0, 2.0]).__next__
    expired = VisibleTurnProjection(clock=clock)
    expired.arm_prebind(17)
    expired.prebind_frame(
        17,
        method="item/updated",
        params={
            "item": {
                "id": "early",
                "sequence": 1,
                "type": "agentMessage",
                "text": "early",
            }
        },
    )
    dropped = expired.drop_expired_prebind()
    assert dropped is not None and dropped.reason == "prebind_timeout"
    assert expired.active_prebind_request_id() is None


def test_ohf_completed_replacement_gets_new_publication_sequence() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-REPLACE", "epoch-replace", "generation-replace", 1, "codex-01",
        "turn-replace", "native-replace",
    )
    grant = projection.mint_grant(key)

    def emit(method: str, sequence: int, text: str) -> None:
        projection.publish(
            key,
            method=method,
            params={
                "item": {
                    "id": "A",
                    "type": "agentMessage",
                    "sequence": sequence,
                    "text": text,
                }
            },
        )

    emit("item/updated", 1, "draft")
    partial = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    emit("item/completed", 2, "final")
    completed = projection.read(
        key,
        reader_grant=grant,
        cursor=partial.next_cursor,
        max_items=64,
    )
    assert [(item.text, item.state) for item in completed.items] == [
        ("final", "completed")
    ]
    assert (
        partial.items[0].publication_sequence
        < completed.items[0].publication_sequence
    )
    assert projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    ).items == completed.items


def test_ohf_two_partial_replacements_retain_only_final_item() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-REPLACE-TWICE", "epoch-replace", "generation-replace", 1, "codex-01",
        "turn-replace", "native-replace",
    )
    grant = projection.mint_grant(key)

    def emit(method: str, text: str) -> None:
        projection.publish(
            key,
            method=method,
            params={
                "item": {
                    "id": "A",
                    "type": "agentMessage",
                    "sequence": 1,
                    "text": text,
                }
            },
        )

    emit("item/updated", "draft-one")
    emit("item/updated", "draft-two")
    emit("item/completed", "final")
    observed = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    assert [(item.text, item.state) for item in observed.items] == [
        ("final", "completed")
    ]


def test_ohf_prebind_items_get_distinct_monotonic_sequences() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-PREBIND", "epoch-prebind", "generation-prebind", 1, "codex-01",
        "turn-prebind", "native-prebind",
    )
    grant = projection.mint_grant(key)
    projection.arm_prebind(7)
    for index in (1, 2):
        projection.prebind_frame(
            7,
            method="item/updated",
            params={
                "item": {
                    "id": f"item-{index}",
                    "type": "agentMessage",
                    "sequence": index,
                    "text": f"prebind-{index}",
                }
            },
        )
    assert projection.commit_prebind(7, key, native_turn_id="native-prebind") is None
    first = projection.read(
        key, reader_grant=grant, cursor=None, max_items=1
    )
    second = projection.read(
        key, reader_grant=grant, cursor=first.next_cursor, max_items=1
    )
    assert [item.text for item in first.items] == ["prebind-1"]
    assert [item.text for item in second.items] == ["prebind-2"]
    assert (
        first.items[0].publication_sequence
        < second.items[0].publication_sequence
    )
    assert second.resync_required is False


def test_ohf_prebind_completion_replays_without_duplicate_item() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-REPLAY", "epoch-replay", "generation-replay", 1, "codex-01",
        "turn-replay", "native-replay",
    )
    grant = projection.mint_grant(key)
    projection.arm_prebind(7)

    def params(method: str, text: str) -> dict[str, object]:
        return {
            "turnId": key.native_turn_id,
            "item": {
                "id": "item-one",
                "type": "agentMessage",
                "sequence": 1,
                "text": text,
            },
            "method_sentinel": method,
        }

    projection.prebind_frame(
        7,
        method="item/updated",
        params=params("item/updated", "partial one"),
    )
    projection.prebind_frame(
        7,
        method="item/completed",
        params=params("item/completed", "final one"),
    )
    assert projection.commit_prebind(
        7, key, native_turn_id=key.native_turn_id
    ) is None
    partial = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    projection.publish_demultiplexed(
        8,
        payload={
            "method": "item/updated",
            "params": params("item/updated", "partial one"),
        },
    )
    projection.publish_demultiplexed(
        8,
        payload={
            "method": "item/completed",
            "params": params("item/completed", "final one"),
        },
    )
    replayed = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    assert [(item.text, item.state) for item in replayed.items] == [
        ("final one", "completed"),
    ]
    assert replayed.next_cursor == partial.next_cursor
    assert (
        partial.items[0].publication_sequence
        == replayed.items[0].publication_sequence
    )


def test_ohf_identical_prebind_replay_preserves_publication_order() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-REPLAY-ORDER", "epoch-replay", "generation-replay", 1, "codex-01",
        "turn-replay", "native-replay",
    )
    grant = projection.mint_grant(key)
    projection.arm_prebind(7)

    def params(
        item_id: str, source_sequence: int, method: str, text: str
    ) -> dict[str, object]:
        return {
            "turnId": key.native_turn_id,
            "item": {
                "id": item_id,
                "type": "agentMessage",
                "sequence": source_sequence,
                "text": text,
            },
            "method_sentinel": method,
        }

    committed_frames = [
        ("partial-one", 1, "item/updated", "partial one"),
        ("final-one", 2, "item/completed", "final one"),
        ("partial-two", 3, "item/updated", "partial two"),
        ("final-two", 4, "item/completed", "final two"),
    ]
    for item_id, source_sequence, method, text in committed_frames:
        projection.prebind_frame(
            7,
            method=method,
            params=params(item_id, source_sequence, method, text),
        )
    assert projection.commit_prebind(
        7, key, native_turn_id=key.native_turn_id
    ) is None
    before = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    assert [item.text for item in before.items] == [
        "partial one", "final one", "partial two", "final two"
    ]

    for item_id, source_sequence, method, text in committed_frames[:3]:
        projection.publish_demultiplexed(
            8,
            payload={
                "method": method,
                "params": params(item_id, source_sequence, method, text),
            },
        )
    after = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    assert [item.text for item in after.items] == [
        "partial one", "final one", "partial two", "final two"
    ]
    assert [item.publication_sequence for item in after.items] == [
        item.publication_sequence for item in before.items
    ]
    assert after.next_cursor == before.next_cursor
    assert projection.read(
        key, reader_grant=grant, cursor=before.next_cursor, max_items=64
    ).items == ()
    assert after == before

    projection.publish_demultiplexed(
        8,
        payload={
            "method": "item/updated",
            "params": params("partial-one", 1, "item/updated", "partial one"),
        },
    )
    stale = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    assert stale == after


def test_ohf_complete_page_without_gap_does_not_require_resync() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-PAGE", "epoch-page", "generation-page", 1, "codex-01",
        "turn-page", "native-page",
    )
    grant = projection.mint_grant(key)
    for index in (1, 2):
        projection.publish(
            key,
            method="item/updated",
            params={
                "item": {
                    "id": f"item-{index}",
                    "type": "agentMessage",
                    "sequence": index,
                    "text": f"page-{index}",
                }
            },
        )
    first = projection.read(
        key, reader_grant=grant, cursor=None, max_items=1
    )
    second = projection.read(
        key, reader_grant=grant, cursor=first.next_cursor, max_items=1
    )
    assert [item.text for item in first.items] == ["page-1"]
    assert [item.text for item in second.items] == ["page-2"]
    assert first.resync_required is False
    assert second.resync_required is False


def test_ohf_encoded_read_bound_covers_serialized_result() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-ENCODED", "epoch-encoded", "generation-encoded", 1, "codex-01",
        "turn-encoded", "native-encoded",
    )
    grant = projection.mint_grant(key)
    for index in range(40):
        projection.publish(
            key,
            method="item/updated",
            params={
                "item": {
                    "id": f"item-{index}",
                    "type": "agentMessage",
                    "sequence": index,
                    "text": '"' * 16_384,
                }
            },
        )
    result = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    encoded_size = len(
        json.dumps(dataclasses.asdict(result), separators=(",", ":")).encode()
    )
    assert encoded_size <= MAX_ENCODED_READ_BYTES
    assert len(result.items) < 40


def test_ohf_single_item_above_encoded_bound_is_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-ENCODED-ONE", "epoch-encoded-one", "generation-encoded-one", 1,
        "codex-01", "turn-encoded-one", "native-encoded-one",
    )
    grant = projection.mint_grant(key)
    projection.publish(
        key,
        method="item/updated",
        params={
            "item": {
                "id": "oversized",
                "type": "agentMessage",
                "sequence": 1,
                "text": '"' * MAX_ITEM_BYTES,
            }
        },
    )
    monkeypatch.setattr(
        visible_turn_projection_module,
        "MAX_ENCODED_READ_BYTES",
        MAX_ITEM_BYTES,
    )
    with pytest.raises(ProjectionError, match="OVER_BUDGET"):
        projection.read(key, reader_grant=grant, cursor=None, max_items=1)
    assert projection.refusal_receipts()[-1][1] == "OVER_BUDGET"


def test_ohf_retention_eviction_past_cursor_requires_resync() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-RESYNC", "epoch-resync", "generation-resync", 1, "codex-01",
        "turn-resync", "native-resync",
    )
    grant = projection.mint_grant(key)
    for index in range(MAX_ITEMS_PER_TURN + 1):
        projection.publish(
            key,
            method="item/updated",
            params={
                "item": {
                    "id": f"item-{index}",
                    "type": "agentMessage",
                    "sequence": index,
                    "text": str(index % 10),
                }
            },
        )
    first = projection.read(
        key, reader_grant=grant, cursor=None, max_items=1
    )
    resumed = projection.read(
        key, reader_grant=grant, cursor=first.next_cursor, max_items=64
    )
    assert resumed.resync_required is True
    assert [gap.reason for gap in resumed.gaps] == ["turn_item_overflow"]


def test_ohf_publication_epoch_change_requires_resync() -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-EPOCH", "epoch-change", "generation-change", 1, "codex-01",
        "turn-change", "native-change",
    )
    grant = projection.mint_grant(key)
    projection.publish(
        key,
        method="item/updated",
        params={
            "item": {
                "id": "item",
                "type": "agentMessage",
                "sequence": 1,
                "text": "before epoch change",
            }
        },
    )
    first = projection.read(
        key, reader_grant=grant, cursor=None, max_items=64
    )
    projection.invalidate_generation(key)
    with projection._lock:
        projection._turns.pop(key.native_turn_id, None)
        projection._viewers_by_turn[key] = {grant}
        projection._create_turn_locked(key)
    with pytest.raises(ProjectionError, match="RESYNC_REQUIRED"):
        projection.read(
            key, reader_grant=grant, cursor=first.next_cursor, max_items=64
        )
    assert projection.refusal_receipts()[-1][1] == "RESYNC_REQUIRED"


def test_ohf_demultiplexed_completion_matches_only_native_turn() -> None:
    projection = VisibleTurnProjection()
    bound_key = TurnKey(
        "ATT-DEMUX", "epoch-demux", "generation-demux", 1, "codex-01",
        "turn-demux", "native-demux",
    )
    foreign_key = TurnKey(
        "ATT-OTHER", "epoch-other", "generation-other", 1, "codex-01",
        "turn-other", "native-other",
    )
    bound_grant = projection.mint_grant(bound_key)
    foreign_grant = projection.mint_grant(foreign_key)
    projection.publish_demultiplexed(
        1,
        payload={"method": "turn/completed", "params": {"turn": {"id": "native-other"}}},
    )
    bound = projection.read(
        bound_key, reader_grant=bound_grant, cursor=None, max_items=64
    )
    foreign = projection.read(
        foreign_key, reader_grant=foreign_grant, cursor=None, max_items=64
    )
    assert bound.terminal is False
    assert foreign.terminal is True


def test_ohf_reader_revocation_stops_publication_and_clears_unsent_buffer(
    tmp_path: Path,
) -> None:
    projection = VisibleTurnProjection()
    key = TurnKey(
        "ATT-REVOKE", "epoch-revoke", "generation-revoke", 1, "codex-01",
        "turn-revoke", "native-revoke",
    )
    grant = projection.mint_grant(key)
    projection.arm_prebind(1)
    projection.prebind_frame(
        1,
        method="item/updated",
        params={
            "item": {
                "id": "unsent",
                "sequence": 1,
                "type": "agentMessage",
                "text": "unsent bytes",
            }
        },
    )
    projection.revoke_grant(grant)
    with pytest.raises(ProjectionError, match="READER_REVOKED"):
        projection.read(key, reader_grant=grant, cursor=None, max_items=64)
    assert projection.active_prebind_request_id() is None
    assert projection.check_grant(grant) is None

    overfull = VisibleTurnProjection()
    overfull_key = TurnKey(
        "ATT-OVER", "epoch-over", "generation-over", 1, "codex-01",
        "turn-over", "native-over",
    )
    overfull_grant = overfull.mint_grant(overfull_key)
    overfull.arm_prebind(1)
    for index in range(MAX_PREBIND_ITEMS + 1):
        overfull.prebind_frame(
            1,
            method="item/updated",
            params={
                "item": {
                    "id": f"item-{index}",
                    "sequence": index,
                    "type": "agentMessage",
                    "text": str(index),
                }
            },
        )
    assert overfull.active_prebind_request_id() is None
    assert overfull.check_grant(overfull_grant) is not None


def test_ohf_observer_wrong_generation_refused_before_content_release(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path, "wrong", "LC1 wrong identity"
        )
        grant = adapters[-1].mint_observer_grant(turn)
        for field, value in (
            ("attempt", "ATT-OTHER"),
            ("generation", "generation-other"),
        ):
            with pytest.raises(BrokerStateError, match="GENERATION_INVALID"):
                await broker.execute(
                    _request(
                        "ohf-observe-turn",
                        _observer_payload(turn, grant, **{field: value}),
                        f"wrong-{field}",
                    ),
                    peer=peer,
                )
        assert broker._observer_refusals[-2][1] == "GENERATION_INVALID"
        assert broker._observer_refusals[-1][1] == "GENERATION_INVALID"

    asyncio.run(scenario())


def test_ohf_observation_never_acquires_busy_or_calls_provider(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path,
            "busy",
            "LC1 busy proof",
            release_gate=True,
        )
        grant = adapters[-1].mint_observer_grant(turn)
        before = list(adapters[-1].lifecycle)
        observed = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, grant),
                "busy-observe",
            ),
            peer=peer,
        )
        assert observed["result"]["items"] == []
        assert broker._operator_run is not None and not broker._operator_run.busy
        assert adapters[-1].lifecycle == before
        assert set(observed["result"]) == {
            "items",
            "next_cursor",
            "gaps",
            "terminal",
            "publication_epoch",
            "retained_scope",
            "resync_required",
        }

    asyncio.run(scenario())


def test_ohf_effect_counter_is_zero_for_all_observer_paths(tmp_path: Path) -> None:
    async def scenario() -> None:
        broker, peer, turn, adapters = await _lc1_broker_turn(
            tmp_path,
            "effects",
            "LC1 effects",
            release_gate=True,
        )
        first_grant = adapters[-1].mint_observer_grant(turn)
        second_grant = adapters[-1].mint_observer_grant(turn)
        adapters[-1].publish_visible("observer-path-visible", "partial")
        provider_calls = []
        original_read_events = type(adapters[-1]).read_events
        original_collect = type(adapters[-1]).collect_candidate_result
        original_raw = type(adapters[-1]).observe_raw_role_result

        def counted_read_events(*args, **kwargs):
            provider_calls.append("read_events")
            return original_read_events(*args, **kwargs)

        def counted_collect(*args, **kwargs):
            provider_calls.append("candidate_collections")
            return original_collect(*args, **kwargs)

        def counted_raw(*args, **kwargs):
            provider_calls.append("raw_collections")
            return original_raw(*args, **kwargs)

        adapters[-1].read_events = counted_read_events
        adapters[-1].collect_candidate_result = counted_collect
        adapters[-1].observe_raw_role_result = counted_raw
        adapters[-1].gate.set()
        observed = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(turn, first_grant),
                "effects-read",
            ),
            peer=peer,
        )
        second = await broker.execute(
            _request(
                "ohf-observe-turn",
                _observer_payload(
                    turn,
                    second_grant,
                    cursor=observed["result"]["next_cursor"],
                    max_items=1,
                ),
                "effects-second",
            ),
            peer=peer,
        )
        assert second["result"]["items"] == []
        adapters[-1].visible_turn_projection.revoke_grant(second_grant)
        with pytest.raises(BrokerStateError, match="READER_REVOKED"):
            await broker.execute(
                _request(
                    "ohf-observe-turn",
                    _observer_payload(turn, second_grant),
                    "effects-revoked",
                ),
            peer=peer,
        )
        assert adapters[-1].lifecycle == ["provider_start"]
        assert adapters[-1].prompts == ["LC1 effects"]
        assert broker._operator_run.busy is False
        assert provider_calls == []
        assert broker._observer_refusals[-1][1] == "READER_REVOKED"
        assert adapters[-1].visible_turn_projection.check_grant(second_grant) is None
        assert observed["result"]["resync_required"] is False

    asyncio.run(scenario())
