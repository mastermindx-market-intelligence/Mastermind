"""Model-free lifecycle proofs for the worker-local Operator Harness broker."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import threading
from pathlib import Path

import pytest

from control_plane import executive_worker_broker as broker_module
from control_plane.codex_worker import BinaryAttestation
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
)
from control_plane.worker_browser_b1 import BrowserReviewReceipt


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


class _SealedAdapter:
    def __init__(self) -> None:
        self.binary = BinaryAttestation(
            path="/fixture/codex",
            real_path="/fixture/codex",
            version="0.147.0",
            sha256="a" * 64,
            team_identifier="2DC432GLL2",
            size=1,
            device=1,
            inode=1,
            mode=0o555,
            uid=0,
            gid=0,
            mtime_ns=1,
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
        return TurnStartObservation("native-turn-1", True)

    def read_events(self, cursor, *, timeout_seconds):
        assert timeout_seconds > 0 and self.turn is not None
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
        _SealedAdapter(),  # type: ignore[arg-type]
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
        with pytest.raises(BrokerStateError, match="quarantined"):
            await broker.execute(
                _request("ohf-start", payload, "cancelled-retry"), peer=peer
            )
        release.set()
        await asyncio.sleep(0)
        assert adapters[0].lifecycle.count("provider_start") == 1
        assert sweeper.calls == []

    asyncio.run(scenario())
