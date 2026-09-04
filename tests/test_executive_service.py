"""Model-free tests for the private Executive OS control service."""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import stat
import subprocess
import tempfile
import threading
import ast
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.redaction import TRUNCATION_MARKER
from control_plane import ceo_intent as ceo_intent_mod
from control_plane import executive_dialogue_observation as observation_mod
from control_plane import executive_ceo_ingress as ceo_ingress_mod
from control_plane.executive_runtime import (
    AttemptLease,
    AttemptStatus,
    JobPayload,
    JobStatus,
    OrchestrationDispatchOutcome,
    Runtime,
    StateConflict,
)
from control_plane.executive_canary import (
    PrincipalIdentity,
    SecretCanaryConfig,
    run_secret_canary,
)
from control_plane.executive_ambient_process import (
    AMBIENT_CODESIGN_IDENTIFIER,
    AMBIENT_LAUNCHD_LABEL,
    AMBIENT_PLIST_PATH,
    AMBIENT_PROGRAM_PATH,
    AmbientProcessIdentity,
)
from control_plane.executive_service import (
    CONTROL_PROTOCOL_VERSION,
    DialogueWakeTarget,
    DialogueWakeResult,
    ExecutiveDialogueWakeBridge,
    ExecutiveControlService,
    ServiceConfig,
    ServiceError,
    send_control_request,
)
from control_plane.executive_dialogue_observation import (
    RECONCILE_WAKE,
    REQUEST_SCHEMA as OBSERVATION_REQUEST_SCHEMA,
    RESPONSE_SCHEMA as OBSERVATION_RESPONSE_SCHEMA,
    SUBMIT_WAKE,
    WAKE_RESPONSE_SCHEMA,
    ActiveObservationFacts,
    CanonicalTerminalWakeCandidate,
    DialogueCandidateReference,
    DialogueObservationFacts,
    PublicRuntimeBindingFacts,
    reduce_dialogue_observation,
)
from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    TerminalReturnProjectionError,
    reduce_terminal_return,
)
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.session_targets import WakeRoute
from control_plane.wake_events import mint_obligation
from control_plane import executive_runtime as er_mod
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _cycle_through_completed_work,
    _review_body,
)
from control_plane.executive_workspace import (
    LAUNCH_CLEAN_STATUS_ARGS,
    LAUNCH_CLEAN_UNTRACKED_ARGS,
    WorkspaceError,
    prepare_credentialless_clone,
)
from control_plane import executive_service as es_mod
from integrations.slack_agent_dialogue.contract import validate_commission_ref
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY as COMPANY_DIALOGUE_SERVER_IDENTITY,
    SERVER_VERSION as COMPANY_DIALOGUE_SERVER_VERSION,
    TOOL_SCHEMA_DIGEST as COMPANY_DIALOGUE_TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ExecutiveTerminalReturnProjector,
)
from scripts import executive_os_phase1c as service_cli
from tests.test_company_dialogue_runtime_binding import parent as dialogue_parent


@dataclass
class _Active:
    lease: object


def _projection_receipt(
    candidate: TerminalReturnCandidate,
    *,
    action: str = "POSTED",
) -> dict[str, object]:
    return {
        "action": action,
        "message_key": candidate.message_key,
        "fingerprint": "f" * 64,
        "message_ts": "1787961600.000002",
        "duplicate_timestamps": [],
        "thread_ts": "1787961600.000001",
        "parent_author_user_id": "U0RELAY01",
        "parent_fingerprint": "a" * 64,
    }


def _capture_projection(
    received: list[TerminalReturnCandidate],
    candidate: TerminalReturnCandidate,
) -> dict[str, object]:
    received.append(candidate)
    return _projection_receipt(candidate)


class _FakeSupervisor:
    def __init__(self, runtime: Runtime, *, finish_gate: asyncio.Event | None = None) -> None:
        self.runtime = runtime
        self.finish_gate = finish_gate
        self.requeue_values: list[bool] = []
        self.started_jobs: list[str] = []

    def reconcile_restart(self, *, requeue_lost: bool = False):
        self.requeue_values.append(requeue_lost)
        return []

    async def start_job(self, job_id: str):
        lease = self.runtime.broker.claim(job_id, lease_owner="service-fixture")
        assert lease is not None
        attempt = lease.attempt
        self.runtime.attempts.record_process(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="fixture-provider-session",
            launch_metadata={"fixture": "redacted"},
        )
        self.runtime.attempts.mark_running(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
        )
        self.started_jobs.append(job_id)
        return _Active(lease=lease)

    async def start_cycle_job(self, job_id: str, *, command_id: str):
        outcome = self.runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            lease_owner="service-fixture",
        )
        if outcome is None:
            raise StateConflict(f"no eligible worker capacity for {job_id}")
        if (
            outcome.outcome == "TERMINAL"
            or outcome.attempt.status is not AttemptStatus.CLAIMED
        ):
            return outcome
        assert outcome.lease_token is not None
        lease = AttemptLease(
            attempt=outcome.attempt,
            lease_token=outcome.lease_token,
        )
        self.started_jobs.append(job_id)
        return _Active(lease=lease)

    async def finish_job(self, active: _Active):
        if self.finish_gate is not None:
            await self.finish_gate.wait()
        lease = active.lease
        attempt = lease.attempt
        job = self.runtime.jobs.get_job(attempt.job_id)
        assert job is not None
        if job.status is JobStatus.CANCEL_REQUESTED:
            return self.runtime.attempts.acknowledge_cancel(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
            )
        payload = JobPayload(
            summary="fixed proof complete",
            completed_steps=["fixture"],
            current_state="complete",
        )
        self.runtime.attempts.checkpoint_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=payload,
        )
        return self.runtime.attempts.complete_attempt(
            attempt.attempt_id,
            fence_generation=attempt.fence_generation,
            lease_token=lease.lease_token,
            payload=payload,
        )


class _FakeBackup:
    def __init__(self) -> None:
        self.created: list[Path] = []
        self.verified: list[tuple[Path, Path | None]] = []

    def create_online_backup(self, store, destination_dir: Path):
        path = destination_dir / "fixture.sqlite3"
        path.write_bytes(b"fixture-backup")
        path.chmod(0o600)
        manifest = path.with_suffix(".manifest.json")
        manifest.write_text("{}\n", encoding="utf-8")
        manifest.chmod(0o600)
        self.created.append(path)
        return {"database_path": path, "source": store.path.name}

    def verify_backup(self, database_path: Path, manifest_path: Path | None = None):
        self.verified.append((database_path, manifest_path))
        return {"ok": database_path.is_file(), "database_path": database_path}


@pytest.fixture
def short_socket_root():
    # Darwin's sockaddr_un path ceiling is only 104 bytes; pytest's native
    # temporary path is intentionally much longer than a production /var/run path.
    value = Path(tempfile.mkdtemp(prefix="mmx-es-", dir="/tmp"))
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _source_repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "proof-source"
    if not (source / ".git").is_dir():
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "Executive Fixture"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "config",
                "user.email",
                "executive-fixture@example.invalid",
            ],
            check=True,
        )
        (source / "README.md").write_text("# Exact proof base\n", encoding="utf-8")
        (source / ".codex").mkdir()
        (source / ".codex/config.toml").write_text(
            '[shell_environment_policy]\ninherit = "none"\n', encoding="utf-8"
        )
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-q", "-m", "proof base"],
            check=True,
        )
    base_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    return source, base_sha


def _config(tmp_path: Path, *, socket_root: Path | None = None, **overrides) -> ServiceConfig:
    source, base_sha = _source_repository(tmp_path)
    values = {
        "runtime_root": tmp_path / "runtime",
        "socket_path": (socket_root or tmp_path / "run") / "executive.sock",
        "proof_source_repository": source,
        "proof_workspace_root": tmp_path / "workspaces",
        "proof_base_sha": base_sha,
        "proof_shared_gid": os.getegid(),
        "backup_root": tmp_path / "backups",
        "allowed_peer_uids": (os.geteuid(),),
        "shutdown_grace_seconds": 0.1,
    }
    values.update(overrides)
    return ServiceConfig(**values)


def _service(
    tmp_path: Path,
    *,
    socket_root: Path | None = None,
    finish_gate: asyncio.Event | None = None,
    backup: _FakeBackup | None = None,
    config: ServiceConfig | None = None,
):
    holder = {}

    def factory(runtime: Runtime):
        supervisor = _FakeSupervisor(runtime, finish_gate=finish_gate)
        holder["supervisor"] = supervisor
        return supervisor

    service = ExecutiveControlService(
        config or _config(tmp_path, socket_root=socket_root),
        supervisor_factory=factory,
        backup_backend=backup,
        autonomy_guard=(
            (lambda: None)
            if (config is not None and config.coo_autonomy_armed)
            else None
        ),
    )
    return service, holder


def _pending_review(tmp_path: Path, *, intent_id: str):
    runtime, cycle, _dispatches, root, planner, work, work_seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime", intent_id=intent_id, review_workers=["worker-b"]
        )
    )
    review_created = cycle.run_once(root.job_id)
    assert review_created.action == "REVIEW_CREATED"
    review = runtime.jobs.get_job(str(review_created.selected_job_id))
    work_job = runtime.jobs.get_job(work.attempt.job_id)
    assert review is not None and work_job is not None
    return runtime, review, _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=str(work_job.plan_digest),
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )


def _first_dispatch_command(job) -> str:
    return f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:1"


def _delete_terminal_seal_event(runtime: Runtime, attempt_id: str) -> None:
    """Create one completed-looking but canonically invalid test fixture."""

    with runtime.store.transaction() as connection:
        trigger = connection.execute(
            """SELECT sql FROM sqlite_master
               WHERE type='trigger' AND name='events_are_immutable_delete'"""
        ).fetchone()
        assert trigger is not None and isinstance(trigger[0], str)
        connection.execute("DROP TRIGGER events_are_immutable_delete")
        removed = connection.execute(
            """DELETE FROM events
               WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'
                 AND attempt_id=?""",
            (attempt_id,),
        ).rowcount
        connection.execute(str(trigger[0]))
    assert removed == 1


def test_finish_pickup_projects_a_sealed_terminal_child_once(tmp_path: Path) -> None:
    async def exercise() -> None:
        config = _config(tmp_path)
        runtime, child, body = _pending_review(
            tmp_path, intent_id="CEO-SERVICE-TERMINAL-ONCE"
        )
        dispatch = runtime.attempts.dispatch_cycle_job(
            child.job_id,
            command_id=_first_dispatch_command(child),
            worker_id="worker-b",
        )
        assert dispatch is not None and dispatch.lease_token is not None
        received: list[TerminalReturnCandidate] = []

        class SealingSupervisor(_FakeSupervisor):
            async def finish_job(self, active: _Active):
                if not self.started_jobs:
                    self.started_jobs.append("finished")
                    return _complete_ohf_role(
                        self.runtime, dispatch, body, identity_seed=742
                    )
                return None

        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda opened: SealingSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
        )
        service.runtime = runtime
        service.supervisor = SealingSupervisor(runtime)
        try:
            active = _Active(lease=AttemptLease(dispatch.attempt, dispatch.lease_token))
            await service._finish_dispatched(child.job_id, active)
            await service._finish_dispatched(child.job_id, active)
            assert [candidate.attempt_id for candidate in received] == [
                dispatch.attempt.attempt_id
            ]
            terminal = service.runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
            assert terminal is not None and terminal.status is AttemptStatus.COMPLETED
            assert service.service_state == "READY"
        finally:
            await service.close()

    asyncio.run(exercise())


def _observation_facts(parent: dict) -> DialogueObservationFacts:
    return DialogueObservationFacts(
        active=(
            ActiveObservationFacts(
                root_job_id="JOB-100",
                job_id="JOB-101",
                attempt_id="ATT-201",
                worker_id="worker-01",
                attempt_status="RUNNING",
                worker_status="BUSY",
                execution_profile_id="profile-readonly",
                execution_profile_digest="1" * 64,
                capability_policy_digest="2" * 64,
                runtime_binding=PublicRuntimeBindingFacts(
                    session_alias="MM-COO-SEAT",
                    binding_id="bind-observation-0001",
                    binding_generation=7,
                    reasoning_surface="codex",
                ),
                parent_fingerprint=parent["fingerprint"],
                company_dialogue_server_identity=COMPANY_DIALOGUE_SERVER_IDENTITY,
                company_dialogue_server_version=COMPANY_DIALOGUE_SERVER_VERSION,
                company_dialogue_tool_schema_digest=COMPANY_DIALOGUE_TOOL_SCHEMA_DIGEST,
                company_dialogue_attested=True,
            ),
        )
    )


def _observation_request(parent: dict | None = None) -> bytes:
    parent = parent or dialogue_parent()
    return (
        json.dumps(
            {
                "schema": OBSERVATION_REQUEST_SCHEMA,
                "request_id": "observation-request-001",
                "parent": parent,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _dialogue_wake_request(operation: str) -> bytes:
    parent = dialogue_parent()
    source_response = reduce_dialogue_observation(
        parent=parent,
        thread_ts="1788000000.123456",
        facts=_observation_facts(parent),
    )
    observation = source_response["observation"]
    candidate = DialogueCandidateReference(
        mode=source_response["mode"],
        root_job_id=observation["root_job_id"],
        job_id=observation["job_id"],
        attempt_id=observation["attempt_id"],
        worker_id=observation["worker_id"],
        evidence_digest=observation["evidence_digest"],
    )
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "a" * 64,
        declared_target_seat="ceo",
        root_job_id="JOB-100",
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    route = WakeRoute(
        obligation_id=obligation.obligation_id,
        session_alias="EXECUTIVE-CEO-A",
        target_seat="ceo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        binding_id="bind-dialogue-wake-0001",
        binding_generation=7,
        route_digest="1" * 16,
        destination_digest="2" * 16,
        policy_digest="3" * 16,
        root_job_id="JOB-100",
        workstream=None,
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        requires_runtime_binding=True,
        binding_ready=True,
        human_required=False,
        policy_version="wake-policy-v1",
        interface_version="codex-app-server-wake/v1",
    )
    return json.dumps(
        {
            "schema": "mastermind.dialogue_wake_request/v1",
            "operation": operation,
            "parent": parent,
            "thread_ts": "1788000000.123456",
            "candidate": candidate.to_dict(),
            "obligation": obligation.to_dict(),
            "route": route.to_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_absent_dialogue_observation_has_no_listener_lifecycle_state(
    tmp_path: Path,
    short_socket_root: Path,
) -> None:
    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root / "operator"),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
    )

    assert service.dialogue_observation_socket_path is None
    assert service.dialogue_observation_ready is False
    for name in (
        "_dialogue_observation_server",
        "_dialogue_observation_tasks",
        "_dialogue_observation_inode",
    ):
        assert not hasattr(service, name)


def test_optional_dialogue_observation_is_third_listener_on_one_runtime_and_lock(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(es_mod, "_peer_uid", lambda _connection: 457)
    calls: list[tuple[Runtime, dict]] = []

    def provider(runtime: Runtime, parent: dict) -> DialogueObservationFacts:
        calls.append((runtime, parent))
        return _observation_facts(parent)

    async def exercise() -> None:
        socket_root = short_socket_root / "observation"
        observation_path = socket_root / "dialogue-observation.sock"
        holder: dict[str, object] = {}

        def factory(runtime: Runtime):
            holder["runtime"] = runtime
            return _FakeSupervisor(runtime)

        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root / "operator"),
            supervisor_factory=factory,
            dialogue_observation_socket_path=observation_path,
            dialogue_observation_peer_uid=457,
            dialogue_observation_group_gid=os.getegid(),
            dialogue_observation_facts_provider=provider,
        )
        assert service.dialogue_observation_ready is False
        await service.start()
        try:
            assert service.dialogue_observation_ready is True
            assert service.runtime is holder["runtime"]
            assert service._lock_fd is not None
            assert stat.S_IMODE(socket_root.lstat().st_mode) == 0o710
            assert stat.S_IMODE(observation_path.lstat().st_mode) == 0o660
            reader, writer = await asyncio.open_unix_connection(observation_path)
            writer.write(_observation_request())
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
            assert response["schema"] == OBSERVATION_RESPONSE_SCHEMA
            assert response["state"] == "RESOLVED"
            assert response["mode"] == "ACTIVE_CURRENT_WORKER"
            assert calls == [(service.runtime, dialogue_parent())]
        finally:
            await service.close()
        assert service.dialogue_observation_ready is False
        assert not observation_path.exists()

    asyncio.run(exercise())


def test_dialogue_observation_authenticates_before_parse_and_refuses_second_frame(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = 999
    calls: list[dict] = []
    monkeypatch.setattr(es_mod, "_peer_uid", lambda _connection: peer)

    def provider(_runtime: Runtime, parent: dict) -> DialogueObservationFacts:
        calls.append(parent)
        return _observation_facts(parent)

    async def exchange(path: Path, payload: bytes) -> dict:
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(payload)
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return response

    async def exercise() -> None:
        nonlocal peer
        observation_path = short_socket_root / "observation" / "dialogue-observation.sock"
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root / "operator"),
            supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
            dialogue_observation_socket_path=observation_path,
            dialogue_observation_peer_uid=457,
            dialogue_observation_group_gid=os.getegid(),
            dialogue_observation_facts_provider=provider,
        )
        await service.start()
        try:
            denied = await exchange(observation_path, b"not json\n")
            assert denied == {
                "schema": OBSERVATION_RESPONSE_SCHEMA,
                "state": "HELD",
                "reason": "PEER_UID_REFUSED",
            }
            assert calls == []

            peer = 457
            second = await exchange(
                observation_path,
                _observation_request() + _observation_request(),
            )
            assert second == {
                "schema": OBSERVATION_RESPONSE_SCHEMA,
                "state": "HELD",
                "reason": "MULTIPLE_REQUESTS_REFUSED",
            }
            assert calls == []

            malformed = await exchange(
                observation_path,
                b'{"schema":"x","schema":"y"}\n',
            )
            assert malformed == {
                "schema": OBSERVATION_RESPONSE_SCHEMA,
                "state": "HELD",
                "reason": "REQUEST_REFUSED",
            }
            assert calls == []

            oversized = await exchange(
                observation_path,
                b"x" * (64 * 1024 + 1) + b"\n",
            )
            assert oversized == {
                "schema": OBSERVATION_RESPONSE_SCHEMA,
                "state": "HELD",
                "reason": "REQUEST_REFUSED",
            }
            assert calls == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_dialogue_coordination_dispatches_closed_wake_operations_on_same_listener(
    tmp_path: Path,
    short_socket_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(es_mod, "_peer_uid", lambda _connection: 457)
    calls: list[tuple[Runtime, object]] = []

    async def wake_handler(runtime: Runtime, request: object) -> DialogueWakeResult:
        calls.append((runtime, request))
        if request.operation == RECONCILE_WAKE:
            return DialogueWakeResult("MISSING", "WAKE_NOT_RECORDED")
        return DialogueWakeResult("RECORDED", "WAKE_RECORDED")

    async def exchange(path: Path, payload: bytes) -> dict:
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(payload)
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return response

    async def exercise() -> None:
        observation_path = short_socket_root / "coordination" / "dialogue.sock"
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root / "operator"),
            supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
            dialogue_observation_socket_path=observation_path,
            dialogue_observation_peer_uid=457,
            dialogue_observation_group_gid=os.getegid(),
            dialogue_observation_facts_provider=(
                lambda _runtime, parent: _observation_facts(parent)
            ),
            dialogue_wake_handler=wake_handler,
        )
        await service.start()
        try:
            assert service.runtime is not None
            before = len(service.runtime.events.list_events())
            reconcile = await exchange(
                observation_path,
                _dialogue_wake_request(RECONCILE_WAKE) + b"\n",
            )
            submit = await exchange(
                observation_path,
                _dialogue_wake_request(SUBMIT_WAKE) + b"\n",
            )
            assert reconcile == {
                "schema": WAKE_RESPONSE_SCHEMA,
                "state": "MISSING",
                "reason": "WAKE_NOT_RECORDED",
            }
            assert submit == {
                "schema": WAKE_RESPONSE_SCHEMA,
                "state": "RECORDED",
                "reason": "WAKE_RECORDED",
            }
            assert len(calls) == 2
            assert all(runtime is service.runtime for runtime, _request in calls)
            assert [request.operation for _runtime, request in calls] == [
                RECONCILE_WAKE,
                SUBMIT_WAKE,
            ]
            assert len(service.runtime.events.list_events()) == before

            forged = json.loads(_dialogue_wake_request(SUBMIT_WAKE))
            forged["candidate"]["evidence_digest"] = "f" * 64
            refused_candidate = await exchange(
                observation_path,
                json.dumps(forged).encode("utf-8") + b"\n",
            )
            assert refused_candidate == {
                "schema": WAKE_RESPONSE_SCHEMA,
                "state": "MISSING",
                "reason": "CANDIDATE_BINDING_REQUIRED",
            }
            assert len(calls) == 2

            unknown = json.loads(_dialogue_wake_request(SUBMIT_WAKE))
            unknown["operation"] = "WAKE_FAILOVER"
            refused = await exchange(
                observation_path,
                json.dumps(unknown).encode("utf-8") + b"\n",
            )
            assert refused == {
                "schema": OBSERVATION_RESPONSE_SCHEMA,
                "state": "HELD",
                "reason": "REQUEST_REFUSED",
            }
            assert len(calls) == 2
        finally:
            await service.close()

    asyncio.run(exercise())


def test_executive_dialogue_wake_bridge_rederives_owners_and_deduplicates_submit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane.operator_harness_contract import AttentionTurnObservation
    from control_plane.runtime_binding_projection import project_runtime_binding
    from control_plane.session_targets import (
        SCHEMA as TARGET_SCHEMA,
        SessionTarget,
        SessionTargetRegistry,
        route_obligation,
    )
    from control_plane.wake_ledger import WakeRetryPolicy
    from control_plane.executive_dialogue_observation import (
        DialogueWakeRequest,
    )
    from tests.test_wake_ack_ingress import _admitted_runtime

    runtime, sealed, generation = _admitted_runtime(tmp_path / "wake-bridge")
    target = SessionTarget(
        session_alias="COO-CODEX",
        target_seat="coo",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        workstream=None,
        target_enabled=True,
    )
    registry = SessionTargetRegistry(
        schema=TARGET_SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=True,
        policy_version="dialogue-wake-test",
        default_alias_by_seat={"coo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={"JOB-100": {"coo": target.session_alias}},
        targets={target.session_alias: target},
    )
    binding = project_runtime_binding(runtime, sealed.attempt_id, target)
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "c" * 64,
        declared_target_seat="coo",
        job_id=sealed.job_id,
        attempt_id=sealed.attempt_id,
        root_job_id="JOB-100",
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:01Z",
    )
    route = route_obligation(obligation, registry, binding=binding)

    class OperatorAdapter:
        calls: list[dict[str, object]] = []

        def deliver_attention(self, **kwargs):
            self.calls.append(dict(kwargs))
            return AttentionTurnObservation(
                process_generation_id=generation.process_generation_id,
                provider_session_id=binding.native_handle,
                nudge_id=kwargs["nudge_id"],
                provider_native_turn_id="turn-dialogue-wake-001",
                accepted=True,
                delivered=True,
            )

    operator = OperatorAdapter()
    provider_calls = 0

    def target_provider(_runtime, _parent, _obligation):
        nonlocal provider_calls
        provider_calls += 1
        return DialogueWakeTarget(
            registry=registry,
            runtime_binding=binding,
            target_attempt_id=sealed.attempt_id,
            process_generation_id=generation.process_generation_id,
            operator_adapter=operator,
        )

    bridge = ExecutiveDialogueWakeBridge(
        target_provider=target_provider,
        carrier_factory=service_cli._build_executive_dialogue_wake_carrier,
        retry_policy=WakeRetryPolicy(
            max_delivery_attempts=1,
            retry_cooldown_s=1,
            accepted_ttl_s=60,
            target_unavailable_backoff_s=1,
            reenable_on_binding_rotation=False,
            armed=True,
        ),
    )
    request = DialogueWakeRequest(
        operation=SUBMIT_WAKE,
        parent=dialogue_parent(),
        thread_ts="1788000000.123456",
        candidate=DialogueCandidateReference(
            mode="ACTIVE_CURRENT_WORKER",
            root_job_id="JOB-100",
            job_id=sealed.job_id,
            attempt_id=sealed.attempt_id,
            worker_id="worker-a",
            evidence_digest="4" * 64,
        ),
        obligation=obligation,
        proposed_route=route,
    )

    first = asyncio.run(bridge(runtime, request))
    second = asyncio.run(bridge(runtime, request))

    assert first == DialogueWakeResult("RECORDED", "WAKE_RECORDED")
    assert second == DialogueWakeResult("RECORDED", "WAKE_RECORDED")
    assert provider_calls == 2
    assert len(operator.calls) == 1

    candidate_job = runtime.jobs.get_job(sealed.job_id)
    assert candidate_job is not None
    candidate_root = candidate_job.root_job_id
    production_registry = dataclasses.replace(
        registry,
        root_job_bindings={
            candidate_root: {"coo": target.session_alias},
        },
    )
    monkeypatch.setattr(
        "control_plane.session_targets.load_session_targets",
        lambda: production_registry,
    )
    with runtime.store.read() as connection:
        target_bindings = es_mod._dialogue_target_bindings_for_root(
            runtime,
            connection,
            root_job_id=candidate_root,
            registry=production_registry,
        )
    assert target_bindings["coo"] == PublicRuntimeBindingFacts(
        session_alias=binding.session_alias,
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
        reasoning_surface="codex",
    )
    assert target_bindings["ceo"] is None

    production_obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "d" * 64,
        declared_target_seat="coo",
        job_id=candidate_job.job_id,
        attempt_id=sealed.attempt_id,
        root_job_id=candidate_root,
        source_workstream="WS:CHAIRMAN-CONTROL-ROOM",
        source_created_at="2026-09-03T01:00:00Z",
        emitted_at="2026-09-03T01:00:02Z",
    )
    production_request = dataclasses.replace(
        request,
        candidate=dataclasses.replace(
            request.candidate,
            root_job_id=candidate_root,
            job_id=candidate_job.job_id,
            attempt_id=sealed.attempt_id,
        ),
        obligation=production_obligation,
        proposed_route=route_obligation(
            production_obligation,
            production_registry,
            binding=binding,
        ),
    )
    production_bridge = ExecutiveDialogueWakeBridge(
        target_provider=None,
        operator_adapter=operator,
        carrier_factory=service_cli._build_executive_dialogue_wake_carrier,
        retry_policy=bridge._retry_policy,
    )
    production_result = asyncio.run(
        production_bridge(runtime, production_request)
    )
    assert production_result == DialogueWakeResult("RECORDED", "WAKE_RECORDED")
    assert len(operator.calls) == 2

    moved = dataclasses.replace(
        request,
        proposed_route=dataclasses.replace(route, binding_generation=99),
    )
    refused = asyncio.run(bridge(runtime, moved))
    assert refused == DialogueWakeResult("MISSING", "WAKE_ROUTE_REFUSED")
    assert len(operator.calls) == 2

    stale_binding_bridge = ExecutiveDialogueWakeBridge(
        target_provider=lambda *_args: dataclasses.replace(
            target_provider(runtime, request.parent, obligation),
            runtime_binding=dataclasses.replace(
                binding,
                binding_generation=binding.binding_generation + 1,
            ),
        ),
        carrier_factory=service_cli._build_executive_dialogue_wake_carrier,
        retry_policy=bridge._retry_policy,
    )
    stale = asyncio.run(stale_binding_bridge(runtime, request))
    assert stale == DialogueWakeResult("MISSING", "CURRENT_BINDING_REFUSED")
    assert len(operator.calls) == 2

    monkeypatch.setattr(
        runtime.operator_harness,
        "current_writer_generation",
        lambda _epoch: dataclasses.replace(
            generation,
            generation_number=generation.generation_number + 1,
        ),
    )
    writer_refused = asyncio.run(bridge(runtime, request))
    assert writer_refused == DialogueWakeResult("MISSING", "CURRENT_WRITER_REFUSED")
    assert len(operator.calls) == 2


def test_dialogue_observation_shutdown_never_unlinks_replaced_inode(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(es_mod, "_peer_uid", lambda _connection: 457)

    async def exercise() -> None:
        observation_path = short_socket_root / "observation" / "dialogue-observation.sock"
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root / "operator"),
            supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
            dialogue_observation_socket_path=observation_path,
            dialogue_observation_peer_uid=457,
            dialogue_observation_group_gid=os.getegid(),
            dialogue_observation_facts_provider=lambda _runtime, parent: _observation_facts(parent),
        )
        await service.start()
        bound = observation_path.lstat()
        observation_path.unlink()
        observation_path.write_text("foreign", encoding="utf-8")
        await service.close()
        assert observation_path.read_text(encoding="utf-8") == "foreign"
        assert (bound.st_dev, bound.st_ino) != (
            observation_path.lstat().st_dev,
            observation_path.lstat().st_ino,
        )

    asyncio.run(exercise())


@pytest.mark.parametrize("failure_phase", ["chown", "chmod", "post_bind_validation"])
def test_dialogue_observation_bind_failure_cleans_only_its_owned_inode_and_lock(
    tmp_path: Path,
    short_socket_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    observation_root = short_socket_root / "observation-bind-failure"
    observation_root.mkdir(mode=0o710)
    os.chown(observation_root, os.geteuid(), os.getegid())
    observation_root.chmod(0o710)
    observation_path = observation_root / "dialogue-observation.sock"
    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root / "operator"),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        dialogue_observation_socket_path=observation_path,
        dialogue_observation_peer_uid=457,
        dialogue_observation_group_gid=os.getegid(),
        dialogue_observation_facts_provider=(
            lambda _runtime, parent: _observation_facts(parent)
        ),
    )

    if failure_phase == "chown":
        real_chown = es_mod.os.chown

        def fail_chown(path, *args, **kwargs):
            if Path(path) == observation_path:
                raise OSError("injected dialogue socket chown failure")
            return real_chown(path, *args, **kwargs)

        monkeypatch.setattr(es_mod.os, "chown", fail_chown)
    elif failure_phase == "chmod":
        real_chmod = Path.chmod

        def fail_chmod(path: Path, *args, **kwargs):
            if path == observation_path:
                raise OSError("injected dialogue socket chmod failure")
            return real_chmod(path, *args, **kwargs)

        monkeypatch.setattr(Path, "chmod", fail_chmod)
    else:
        real_lstat = Path.lstat
        calls = 0

        def fail_validation(path: Path, *args, **kwargs):
            nonlocal calls
            if path == observation_path:
                calls += 1
                if calls == 3:
                    raise OSError("injected post-bind validation failure")
            return real_lstat(path, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", fail_validation)

    with pytest.raises(ServiceError, match="CAPABILITY_NOT_READY"):
        asyncio.run(service.start())

    assert not observation_path.exists()
    assert service._dialogue_observation_server is None
    assert service._dialogue_observation_inode is None
    assert service._lock_fd is None


def test_dialogue_observation_parent_symlink_fails_capability_not_ready(
    tmp_path: Path, short_socket_root: Path,
) -> None:
    real = short_socket_root / "real-observation"
    real.mkdir()
    alias = short_socket_root / "observation-alias"
    alias.symlink_to(real, target_is_directory=True)
    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root / "operator"),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        dialogue_observation_socket_path=alias / "dialogue-observation.sock",
        dialogue_observation_peer_uid=457,
        dialogue_observation_group_gid=os.getegid(),
        dialogue_observation_facts_provider=lambda _runtime, parent: _observation_facts(parent),
    )
    with pytest.raises(ServiceError, match="CAPABILITY_NOT_READY"):
        asyncio.run(service.start())


def test_dialogue_observation_prefilters_exact_parent_before_candidate_bound(
    tmp_path: Path,
    short_socket_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root / "operator"),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        dialogue_observation_socket_path=(
            short_socket_root / "observation-filter" / "dialogue-observation.sock"
        ),
        dialogue_observation_peer_uid=457,
        dialogue_observation_group_gid=os.getegid(),
    )
    queries: list[tuple[str, tuple[object, ...]]] = []
    matching_count = 0

    class Cursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class Connection:
        def execute(self, sql, parameters=()):
            nonlocal matching_count
            normalized = " ".join(str(sql).split())
            values = tuple(parameters)
            queries.append((normalized, values))
            if "dialogue_source_digest" in normalized:
                return Cursor([{"job_id": "JOB-100"}])
            return Cursor([{} for _ in range(matching_count)])

    class ReadContext:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_args):
            return False

    fake_runtime = SimpleNamespace(store=SimpleNamespace(read=ReadContext))
    parent = dialogue_parent()
    requested_source = es_mod.normalize_executive_dialogue_source(
        {
            "schema_version": es_mod.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
            "work_ref": parent["work_ref"],
            "commission_ref": parent["commission_ref"],
            "watch_mode": parent["watch_mode"],
        }
    )
    monkeypatch.setattr(
        es_mod,
        "_dialogue_source_from_root_creation",
        lambda _connection, *, root_job_id: requested_source,
    )

    facts = service._runtime_dialogue_observation_facts(fake_runtime, parent)

    assert facts.complete is True
    assert facts.active == ()
    assert facts.terminal == ()
    sql, parameters = queries[0]
    assert "EXISTS" in sql
    assert "j.orchestration_role='aggregation'" in sql
    assert "j.root_job_id=j.job_id" in sql
    assert "$.provenance.dialogue_source_digest" in sql
    assert len(parameters) == 1
    assert isinstance(parameters[0], str)
    assert len(parameters[0]) == 64
    child_sql, child_parameters = queries[1]
    assert "j.root_job_id=?" in child_sql
    assert "('exec-' || lower(j.job_id))=?" in child_sql
    assert "('asd-session-exec-' || lower(j.job_id))=?" in child_sql
    assert "LIMIT 5" in child_sql
    assert child_parameters == (
        "JOB-100",
        parent["operation_key"],
        parent["session_ref"],
    )

    matching_count = 5
    overflow = service._runtime_dialogue_observation_facts(fake_runtime, parent)
    assert overflow.complete is False
    assert overflow.active == ()
    assert overflow.terminal == ()


def test_public_terminal_wake_read_reuses_real_service_projection_and_wake_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
    )
    from control_plane.wake_ledger import requested_record
    from control_plane.wake_persist import WakeLedgerRepository
    from tests import test_executive_os_phase1fc as phase1fc_fixtures

    original_submit = phase1fc_fixtures.submit_intent

    def sourced_submit(runtime, payload):
        return original_submit(
            runtime,
            {**payload, "workstream": "WS:EXECUTIVE-OS"},
            dialogue_source=_terminal_dialogue_source(),
            require_dialogue_source=True,
        )

    monkeypatch.setattr(phase1fc_fixtures, "submit_intent", sourced_submit)
    runtime, _cycle, _dispatches, _root, _planner, work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-SERVICE-CANONICAL-TERMINAL-WAKE-READ",
            review_workers=["worker-b"],
        )
    )
    observed: dict[str, object] = {}

    class ApplyingProjector:
        async def project(self, candidate, *, before_write):
            source = _terminal_dialogue_source()
            parent = build_parent_v2(
                {
                    "schema": PARENT_SCHEMA_V2,
                    "work_ref": source["work_ref"],
                    "commission_ref": source["commission_ref"],
                    "session_ref": candidate.session_ref,
                    "operation_key": candidate.operation_key,
                    "watch_mode": source["watch_mode"],
                    "allowed_sol_user_ids": ["U0BRETDUAS2"],
                    "created_at": "2026-09-03T01:00:00Z",
                }
            )
            observed["candidate"] = candidate
            observed["parent"] = parent
            before_write()
            return {
                **_projection_receipt(candidate),
                "thread_ts": "1787961600.000001",
                "parent_fingerprint": parent["fingerprint"],
            }

        async def reconcile(self, _candidate):
            raise AssertionError("fresh projection must not reconcile")

    service = ExecutiveControlService(
        _config(tmp_path / "service"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=ApplyingProjector(),
    )
    service.runtime = runtime
    asyncio.run(
        service._project_terminal_return(
            work.attempt.job_id,
            expected_attempt_id=work.attempt.attempt_id,
        )
    )
    terminal = observed["candidate"]
    parent = observed["parent"]
    original_read = runtime.store.read
    read_calls = 0

    def counted_read():
        nonlocal read_calls
        read_calls += 1
        return original_read()

    monkeypatch.setattr(runtime.store, "read", counted_read)
    terminal_facts = service._runtime_dialogue_observation_facts(runtime, parent)
    assert read_calls == 1
    assert len(terminal_facts.terminal) == 1
    assert terminal_facts.terminal[0].binding_revalidated is True
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref="agent_dialogue_attention:" + "e" * 64,
        declared_target_seat="ceo",
        job_id=terminal.job_id,
        attempt_id=terminal.attempt_id,
        root_job_id=terminal.root_job_id,
        source_workstream="WS:EXECUTIVE-OS",
        source_created_at="2026-09-03T01:00:02Z",
        emitted_at="2026-09-03T01:00:03Z",
    )
    WakeLedgerRepository(runtime).append_record(
        requested_record(obligation),
        obligation=obligation,
    )

    exact_candidate = CanonicalTerminalWakeCandidate(
        root_job_id=terminal.root_job_id,
        job_id=terminal.job_id,
        attempt_id=terminal.attempt_id,
        worker_id=terminal.worker_id,
    )
    direct_reader = getattr(
        observation_mod,
        "read_runtime_canonical_terminal_wake",
        None,
    )
    facts_owner = getattr(
        observation_mod,
        "runtime_canonical_terminal_facts",
        None,
    )
    assert callable(direct_reader), "standalone Runtime reader is not exposed"
    assert callable(facts_owner), "canonical Runtime facts owner is not exposed"
    owner_connections: list[sqlite3.Connection] = []

    def observed_owner(runtime_arg, candidate_arg, connection_arg):
        owner_connections.append(connection_arg)
        return facts_owner(runtime_arg, candidate_arg, connection_arg)

    monkeypatch.setattr(
        observation_mod,
        "runtime_canonical_terminal_facts",
        observed_owner,
    )

    result = service.read_canonical_dialogue_terminal_wake(
        source_root_job_id=terminal.root_job_id,
        candidate=exact_candidate,
    )
    with runtime.store.read() as connection:
        caller_connection = connection
        event_count_before = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )
        same_snapshot = service.read_canonical_dialogue_terminal_wake(
            source_root_job_id=terminal.root_job_id,
            candidate=exact_candidate,
            connection=connection,
        )
        direct_snapshot = direct_reader(
            runtime=runtime,
            source_root_job_id=terminal.root_job_id,
            candidate=exact_candidate,
            connection=connection,
        )
    replay = service.read_canonical_dialogue_terminal_wake(
        source_root_job_id=terminal.root_job_id,
        candidate=exact_candidate,
    )
    with runtime.store.read() as connection:
        event_count_after = int(
            connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )

    assert result.state == "RESOLVED"
    assert result.terminal_applied is True
    assert result.wake is not None
    assert result.wake.obligation_id == obligation.obligation_id
    assert result.wake.status == "PENDING_RETRYABLE"
    assert same_snapshot.to_dict() == result.to_dict()
    assert direct_snapshot.to_dict() == result.to_dict()
    assert replay.to_dict() == result.to_dict()
    assert caller_connection in owner_connections
    assert event_count_after == event_count_before


@pytest.mark.parametrize("node_kind", ["socket", "symlink"])
def test_dialogue_observation_foreign_or_symlink_socket_is_never_reclaimed(
    tmp_path: Path,
    short_socket_root: Path,
    node_kind: str,
) -> None:
    observation_root = short_socket_root / f"observation-{node_kind}"
    observation_root.mkdir(mode=0o710)
    os.chown(observation_root, os.geteuid(), os.getegid())
    observation_root.chmod(0o710)
    observation_path = observation_root / "dialogue-observation.sock"
    foreign: socket.socket | None = None
    if node_kind == "socket":
        foreign = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        foreign.bind(os.fspath(observation_path))
        observation_path.chmod(0o660)
    else:
        target = observation_root / "foreign.sock"
        target.write_text("foreign", encoding="utf-8")
        observation_path.symlink_to(target)

    service = ExecutiveControlService(
        _config(tmp_path, socket_root=short_socket_root / "operator"),
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        dialogue_observation_socket_path=observation_path,
        dialogue_observation_peer_uid=457,
        dialogue_observation_group_gid=os.getegid(),
        dialogue_observation_facts_provider=(
            lambda _runtime, parent: _observation_facts(parent)
        ),
    )
    try:
        with pytest.raises(ServiceError, match="CAPABILITY_NOT_READY"):
            asyncio.run(service.start())
        assert os.path.lexists(observation_path)
    finally:
        if foreign is not None:
            foreign.close()


def test_finish_pickup_provider_silence_and_failure_do_not_rewrite_lifecycle(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        for mode in ("silent", "definite", "effect_unknown", "raises"):
            root = tmp_path / mode
            config = _config(root)
            runtime, child, body = _pending_review(
                root, intent_id=f"CEO-SERVICE-TERMINAL-{mode.upper()}"
            )
            dispatch = runtime.attempts.dispatch_cycle_job(
                child.job_id,
                command_id=_first_dispatch_command(child),
                worker_id="worker-b",
            )
            assert dispatch is not None and dispatch.lease_token is not None

            class SealingSupervisor(_FakeSupervisor):
                async def finish_job(self, active: _Active):
                    return _complete_ohf_role(
                        self.runtime, dispatch, body, identity_seed=743
                    )

            async def raises(_candidate: TerminalReturnCandidate) -> None:
                raise RuntimeError("effect unknown")

            async def definite(_candidate: TerminalReturnCandidate) -> None:
                raise TerminalReturnProjectionError(
                    "DIALOGUE_BINDING_UNAVAILABLE"
                )

            async def effect_unknown(_candidate: TerminalReturnCandidate) -> None:
                raise TerminalReturnProjectionError("EFFECT_UNKNOWN")

            projectors = {
                "silent": None,
                "definite": definite,
                "effect_unknown": effect_unknown,
                "raises": raises,
            }

            service = ExecutiveControlService(
                config,
                supervisor_factory=lambda opened: SealingSupervisor(opened),
                terminal_return_projector=projectors[mode],
            )
            service.runtime = runtime
            service.supervisor = SealingSupervisor(runtime)
            try:
                active = _Active(lease=AttemptLease(dispatch.attempt, dispatch.lease_token))
                await service._finish_dispatched(child.job_id, active)
                terminal = service.runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
                job = service.runtime.jobs.get_job(child.job_id)
                assert terminal is not None and terminal.status is AttemptStatus.COMPLETED
                assert job is not None and job.status is JobStatus.COMPLETED
                assert service.service_state == "READY"
                assert service._terminal_return_last_diagnostic == (
                        {
                            "silent": "terminal-return:PROJECTOR_UNBOUND",
                            # Legacy injected callables expose no exact write
                            # boundary, so every post-invocation refusal is
                            # conservatively possible-effect state.
                            "definite": "terminal-return:EFFECT_UNKNOWN",
                            "effect_unknown": "terminal-return:EFFECT_UNKNOWN",
                            "raises": "terminal-return:EFFECT_UNKNOWN:RuntimeError",
                        }[mode]
                )
            finally:
                await service.close()

    asyncio.run(exercise())


def test_cycle_immediate_terminal_outcome_uses_the_same_projection_pickup(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        config = _config(tmp_path)
        runtime, receipt, body = _pending_review(
            tmp_path, intent_id="CEO-SERVICE-IMMEDIATE-TERMINAL"
        )
        received: list[TerminalReturnCandidate] = []

        class ImmediateTerminalSupervisor(_FakeSupervisor):
            async def start_cycle_job(self, job_id: str, *, command_id: str):
                dispatched = self.runtime.attempts.dispatch_cycle_job(
                    job_id, command_id=command_id, worker_id="worker-b"
                )
                assert dispatched is not None and dispatched.lease_token is not None
                _complete_ohf_role(
                    self.runtime, dispatched, body, identity_seed=746
                )
                terminal = self.runtime.attempts.get_attempt(dispatched.attempt.attempt_id)
                assert terminal is not None
                return OrchestrationDispatchOutcome(
                    command_id=command_id,
                    job_id=job_id,
                    attempt=terminal,
                    outcome="TERMINAL",
                )

        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda opened: ImmediateTerminalSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
        )
        service.runtime = runtime
        service.supervisor = ImmediateTerminalSupervisor(runtime)
        try:
            # This test targets only the immediate-terminal post-dispatch seam;
            # the host-profile guard has independent coverage in this module.
            service._require_bound_coo_job = lambda job: job
            service._require_coo_workspace = lambda job: {}
            outcome = await service._dispatch_cycle_job_exact(
                receipt.job_id, _first_dispatch_command(receipt)
            )
            assert outcome.outcome == "TERMINAL"
            assert [candidate.attempt_id for candidate in received] == [
                outcome.attempt.attempt_id
            ]
            assert service.service_state == "READY"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_startup_reconstructs_a_missed_terminal_projection_from_runtime_truth(
    tmp_path: Path,
    short_socket_root: Path,
) -> None:
    """Deleting startup terminal-fact recovery must strand this result."""

    async def exercise() -> None:
        runtime, cycle, dispatches, root, planner, work, work_seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-RESTART-RECOVERY",
                review_workers=["worker-b", "worker-b"],
            )
        )
        assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
        assert cycle.run_once(root.job_id).action == "DISPATCHED"
        rejecting_review = dispatches[-1]
        work_job = runtime.jobs.get_job(work.attempt.job_id)
        assert work_job is not None
        reject_body = _review_body(
            root_id=root.job_id,
            plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=str(work_job.plan_digest),
            target_job_id=work.attempt.job_id,
            target_attempt_id=work.attempt.attempt_id,
            target_result_digest=work_seal["role_result_digest"],
            repair_round=0,
            verdict="reject",
        )
        reject_seal, _ = _complete_ohf_role(
            runtime,
            rejecting_review,
            reject_body,
            identity_seed=748,
        )

        assert cycle.run_once(root.job_id).action == "REPAIR_CREATED"
        assert cycle.run_once(root.job_id).action == "DISPATCHED"
        repair = dispatches[-1]
        repair_body = {
            "schema_version": "mastermind.repair_result/v1",
            "root_job_id": root.job_id,
            "plan_attempt_id": planner.attempt.attempt_id,
            "plan_digest": str(work_job.plan_digest),
            "plan_step_id": "step-1",
            "repair_round": 1,
            "supersedes_job_id": work.attempt.job_id,
            "rejected_review_job_id": rejecting_review.attempt.job_id,
            "rejected_review_result_digest": reject_seal["role_result_digest"],
            "artifacts": [],
            "evidence_digests": [],
        }
        repair_seal, _ = _complete_ohf_role(
            runtime,
            repair,
            repair_body,
            identity_seed=749,
        )

        valid_by_job_id = {
            planner.job_id: ("plan", planner.attempt.attempt_id),
            work.attempt.job_id: ("work", work.attempt.attempt_id),
            rejecting_review.attempt.job_id: (
                "review",
                rejecting_review.attempt.attempt_id,
            ),
            repair.attempt.job_id: ("repair", repair.attempt.attempt_id),
        }
        expected = tuple(
            valid_by_job_id[job.job_id]
            for job in runtime.jobs.list_jobs()
            if job.job_id in valid_by_job_id
        )
        assert {role for role, _attempt_id in expected} == {
            "plan",
            "work",
            "review",
            "repair",
        }
        before_events = tuple(runtime.events.list_events())

        received: list[TerminalReturnCandidate] = []
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
        )
        await service.start()
        try:
            # The prior process could have exited after Runtime committed the
            # terminal transaction but before the projector callback.  A fresh
            # service must recover that durable fact without another provider
            # finish, Job transition, or caller-supplied job/attempt identity.
            assert tuple(
                (candidate.role, candidate.attempt_id) for candidate in received
            ) == expected
            after_events = tuple(service.runtime.events.list_events())
            assert after_events[: len(before_events)] == before_events
            projection_events = after_events[len(before_events) :]
            assert len(projection_events) == 3 * len(expected)
            assert [event.event_type for event in projection_events] == [
                event_type
                for _role, _attempt_id in expected
                for event_type in (
                    "EXECUTIVE_TERMINAL_RETURN_PREPARED",
                    "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
                    "EXECUTIVE_TERMINAL_RETURN_APPLIED",
                )
            ]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_startup_does_not_project_terminal_returns_while_awaiting_canary(
    tmp_path: Path,
    short_socket_root: Path,
) -> None:
    """AWAITING_CANARY must not emit reconstructed external projections."""

    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-CANARY-HOLD",
                review_workers=["worker-b"],
            )
        )
        before_events = tuple(runtime.events.list_events())
        received: list[TerminalReturnCandidate] = []
        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
            service_state="AWAITING_CANARY",
        )
        await service.start()
        try:
            assert planner.attempt.attempt_id not in {
                candidate.attempt_id for candidate in received
            }
            assert received == []
            assert tuple(service.runtime.events.list_events()) == before_events
        finally:
            await service.close()

    asyncio.run(exercise())


def test_canary_activation_replays_preexisting_sourced_terminal_once(
    tmp_path: Path,
    short_socket_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import test_executive_os_phase1fc as phase1fc_fixtures

    original_submit = phase1fc_fixtures.submit_intent

    def sourced_submit(runtime, payload):
        return original_submit(
            runtime,
            {**payload, "workstream": "WS:EXECUTIVE-OS"},
            dialogue_source=_terminal_dialogue_source(),
            require_dialogue_source=True,
        )

    monkeypatch.setattr(phase1fc_fixtures, "submit_intent", sourced_submit)

    async def exercise() -> None:
        config = dataclasses.replace(
            _config(tmp_path, socket_root=short_socket_root),
            terminal_return_armed=True,
            terminal_return_socket_path=tmp_path / "agent-relay.sock",
        )
        runtime, _cycle, _dispatches, _root, planner, work, _seal = (
            _cycle_through_completed_work(
                config.runtime_root,
                intent_id="CEO-SERVICE-CANARY-TERMINAL-REPLAY",
                review_workers=["worker-b"],
            )
        )

        class ApplyingProjector:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def project(self, candidate, *, before_write):
                self.calls.append(candidate.attempt_id)
                before_write()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                raise AssertionError("an APPLIED candidate must not reconcile")

        # Leave exactly the planner unresolved so activation has one observable
        # obligation while startup also audits an existing APPLIED family.
        setup_projector = ApplyingProjector()
        setup = ExecutiveControlService(
            _config(tmp_path / "setup"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=setup_projector,
        )
        setup.runtime = runtime
        await setup._project_terminal_return(
            work.attempt.job_id,
            expected_attempt_id=work.attempt.attempt_id,
        )
        assert setup_projector.calls == [work.attempt.attempt_id]

        activated_projector = ApplyingProjector()

        def factory(opened):
            supervisor = _FakeSupervisor(opened)
            supervisor.secret_canary_verdict = {}
            supervisor.require_complete_launch_attestation = False
            return supervisor

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            terminal_return_projector_factory=(
                lambda _runtime_provider, _socket_path: activated_projector
            ),
            service_state="AWAITING_CANARY",
        )
        await service.start()
        assert activated_projector.calls == []
        verdict = {
            "schema_version": "mastermind.executive_secret_canary/v1",
            "passed": True,
            "checks": {
                "control_service_environment": "DENIED",
                "administrative_checkout": "DENIED",
                "executive_database": "DENIED",
                "other_worker_home": "DENIED",
                "forbidden_production_path": "DENIED",
            },
            "receipt_sha256": "b" * 64,
            "control_environment_probe_sha256": "c" * 64,
            "observed_at": "2026-08-11T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
        }
        await service.activate_canary(verdict)
        assert service.service_state == "READY"
        assert activated_projector.calls == [planner.attempt.attempt_id]
        await service.close()

        restart_projector = ApplyingProjector()
        restarted = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            terminal_return_projector_factory=(
                lambda _runtime_provider, _socket_path: restart_projector
            ),
        )
        await restarted.start()
        try:
            assert restart_projector.calls == []
            assert restarted._terminal_return_last_diagnostic == (
                "terminal-return:ALREADY_APPLIED"
            )
        finally:
            await restarted.close()

    asyncio.run(exercise())


def test_startup_bound_counts_only_unresolved_source_eligible_obligations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep the algorithmic boundary small while using complete canonical
    # Runtime graphs.  The production ceiling itself remains frozen at 256.
    assert es_mod._TERMINAL_RETURN_STARTUP_REPLAY_LIMIT == 256
    assert es_mod._TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT == 4096
    monkeypatch.setattr(es_mod, "_TERMINAL_RETURN_STARTUP_REPLAY_LIMIT", 2)

    from tests import test_executive_os_phase1fc as phase1fc_fixtures

    original_register = phase1fc_fixtures._register

    def register_once(runtime: Runtime, worker_id: str = "worker-1") -> None:
        try:
            original_register(runtime, worker_id)
        except StateConflict as exc:
            if "already registered" not in str(exc):
                raise

    monkeypatch.setattr(phase1fc_fixtures, "_register", register_once)
    original_complete = phase1fc_fixtures._complete_ohf_role
    completion_ordinal = 0

    def complete_once(runtime, outcome, role_result, *, identity_seed: int):
        nonlocal completion_ordinal
        completion_ordinal += 1
        return original_complete(
            runtime,
            outcome,
            role_result,
            identity_seed=identity_seed + completion_ordinal * 10_000,
        )

    monkeypatch.setattr(
        phase1fc_fixtures,
        "_complete_ohf_role",
        complete_once,
    )

    def completed_planners(root: Path, prefix: str, count: int):
        cycles = [
            _cycle_through_completed_work(
                root,
                intent_id=f"{prefix}-{index}",
                review_workers=["worker-b"],
            )
            for index in range(count)
        ]
        return cycles[0][0], [role for cycle in cycles for role in cycle[4:6]]

    async def exercise() -> None:
        applied_runtime, applied_planners = completed_planners(
            tmp_path / "applied-runtime",
            "CEO-SERVICE-HISTORICAL-APPLIED",
            3,
        )

        class ApplyingProjector:
            calls = 0

            async def project(self, candidate, *, before_write):
                self.calls += 1
                before_write()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                raise AssertionError("fresh projection must not reconcile")

        applying = ApplyingProjector()
        initial = ExecutiveControlService(
            _config(tmp_path / "initial"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=applying,
        )
        initial.runtime = applied_runtime
        for planner in applied_planners:
            await initial._project_terminal_return(
                planner.job_id,
                expected_attempt_id=planner.attempt.attempt_id,
            )
        assert applying.calls == 6

        class CountingProjector:
            calls = 0

            async def project(self, _candidate, *, before_write):
                del before_write
                self.calls += 1
                raise AssertionError("historical rows must not be replayed")

            async def reconcile(self, _candidate):
                self.calls += 1
                raise AssertionError("historical rows must not be reconciled")

        applied_counter = CountingProjector()
        applied_restart = ExecutiveControlService(
            _config(tmp_path / "applied-restart"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=applied_counter,
        )
        applied_restart.runtime = applied_runtime
        await applied_restart._replay_terminal_returns_on_startup()
        assert applied_restart.service_state == "READY"
        assert applied_counter.calls == 0

        before_audit = tuple(applied_runtime.events.list_events())
        monkeypatch.setattr(
            es_mod,
            "_TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT",
            2,
        )
        audit_counter = CountingProjector()
        audit_restart = ExecutiveControlService(
            _config(tmp_path / "audit-restart"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=audit_counter,
        )
        audit_restart.runtime = applied_runtime
        await audit_restart._replay_terminal_returns_on_startup()
        assert audit_restart.service_state == "QUARANTINED"
        assert audit_restart._terminal_return_last_diagnostic == (
            "terminal-return:STARTUP_PHASE_AUDIT_LIMIT_EXCEEDED"
        )
        assert audit_counter.calls == 0
        assert tuple(applied_runtime.events.list_events()) == before_audit
        monkeypatch.setattr(
            es_mod,
            "_TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT",
            4096,
        )

        source_free_runtime, _source_free_planners = completed_planners(
            tmp_path / "source-free-runtime",
            "CEO-SERVICE-HISTORICAL-SOURCE-FREE",
            3,
        )
        armed_config = dataclasses.replace(
            _config(tmp_path / "source-free-restart"),
            terminal_return_armed=True,
            terminal_return_socket_path=tmp_path / "agent-relay.sock",
        )
        source_free_counter = CountingProjector()
        source_free_restart = ExecutiveControlService(
            armed_config,
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector_factory=(
                lambda _runtime_provider, _socket_path: source_free_counter
            ),
        )
        source_free_restart.runtime = source_free_runtime
        await source_free_restart._replay_terminal_returns_on_startup()
        assert source_free_restart.service_state == "READY"
        assert source_free_counter.calls == 0
        assert source_free_restart._terminal_return_last_diagnostic == (
            "terminal-return:SKIPPED_SOURCE_FREE"
        )

        unresolved_runtime, _unresolved_planners = completed_planners(
            tmp_path / "unresolved-runtime",
            "CEO-SERVICE-HISTORICAL-UNRESOLVED",
            3,
        )
        unresolved_counter = CountingProjector()
        unresolved_restart = ExecutiveControlService(
            _config(tmp_path / "unresolved-restart"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=unresolved_counter,
        )
        unresolved_restart.runtime = unresolved_runtime
        before = tuple(unresolved_runtime.events.list_events())
        await unresolved_restart._replay_terminal_returns_on_startup()
        assert unresolved_restart.service_state == "QUARANTINED"
        assert unresolved_restart._terminal_return_last_diagnostic == (
            "terminal-return:STARTUP_REPLAY_LIMIT_EXCEEDED"
        )
        assert unresolved_counter.calls == 0
        assert tuple(unresolved_runtime.events.list_events()) == before

    asyncio.run(exercise())


def test_startup_quarantines_malformed_applied_namespace_before_relay(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-MALFORMED-APPLIED-STARTUP",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id
        with runtime.store.transaction() as connection:
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=attempt_id,
                event_type="EXECUTIVE_TERMINAL_RETURN_APPLIED",
                actor="foreign-writer",
                job_id=planner.job_id,
                attempt_id=attempt_id,
                worker_id=planner.attempt.worker_id,
                payload={},
                command_id=f"terminal-return:{attempt_id}:foreign:applied",
            )

        class RefusingProjector:
            calls = 0

            async def project(self, _candidate, *, before_write):
                del before_write
                self.calls += 1
                raise AssertionError("malformed APPLIED must fail before Relay")

            async def reconcile(self, _candidate):
                self.calls += 1
                raise AssertionError("malformed APPLIED must fail before Relay")

        projector = RefusingProjector()
        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=projector,
        )
        service.runtime = runtime
        before = tuple(runtime.events.list_events())
        await service._replay_terminal_returns_on_startup()
        assert service.service_state == "QUARANTINED"
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:EVIDENCE_REFUSED"
        )
        assert projector.calls == 0
        assert tuple(runtime.events.list_events()) == before

    asyncio.run(exercise())


def test_startup_validates_every_fresh_candidate_before_first_relay_write(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-FRESH-PROOF-STARTUP",
                review_workers=["worker-b"],
            )
        )
        _delete_terminal_seal_event(runtime, work.attempt.attempt_id)

        class RefusingProjector:
            calls = 0

            async def project(self, _candidate, *, before_write):
                del before_write
                self.calls += 1
                raise AssertionError("proof census must finish before Relay")

            async def reconcile(self, _candidate):
                self.calls += 1
                raise AssertionError("proof census must finish before Relay")

        projector = RefusingProjector()
        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=projector,
        )
        service.runtime = runtime
        before = tuple(runtime.events.list_events())
        await service._replay_terminal_returns_on_startup()
        assert service.service_state == "QUARANTINED"
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:EVIDENCE_REFUSED"
        )
        assert projector.calls == 0
        assert tuple(runtime.events.list_events()) == before
        assert planner.attempt.attempt_id != work.attempt.attempt_id

    asyncio.run(exercise())


def test_close_drains_terminal_flight_created_by_dispatch_shutdown_race(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-CLOSE-TERMINAL-RACE",
                review_workers=["worker-b"],
            )
        )
        finish_release = asyncio.Event()
        projector_entered = asyncio.Event()
        projector_release = asyncio.Event()

        class FinishingSupervisor(_FakeSupervisor):
            async def finish_job(self, _active):
                await finish_release.wait()

        class BlockingProjector:
            async def project(self, candidate, *, before_write):
                before_write()
                projector_entered.set()
                await projector_release.wait()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                raise AssertionError("fresh projection must not reconcile")

        config = _config(tmp_path / "service", shutdown_grace_seconds=0.1)
        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda opened: FinishingSupervisor(opened),
            terminal_return_projector=BlockingProjector(),
        )
        service.runtime = runtime
        service.supervisor = FinishingSupervisor(runtime)
        active = _Active(lease=SimpleNamespace(attempt=planner.attempt))
        dispatch_task = asyncio.create_task(
            service._finish_dispatched(planner.job_id, active)
        )
        service._dispatch_tasks[planner.job_id] = dispatch_task

        close_task = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        finish_release.set()
        await asyncio.wait_for(projector_entered.wait(), timeout=1)
        await asyncio.sleep(0.15)
        assert close_task.done() is False

        projector_release.set()
        await asyncio.wait_for(close_task, timeout=1)
        assert service._terminal_return_flights == {}
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=f"terminal-return:{planner.attempt.attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_cancelled_close_shields_attempted_terminal_flight_through_cleanup(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-CANCELLED-CLOSE-TERMINAL-FLIGHT",
                review_workers=["worker-b"],
            )
        )
        projector_entered = asyncio.Event()
        projector_release = asyncio.Event()
        sends = 0

        class BlockingProjector:
            async def project(self, candidate, *, before_write):
                nonlocal sends
                before_write()
                sends += 1
                projector_entered.set()
                await projector_release.wait()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                raise AssertionError("fresh projection must not reconcile")

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=BlockingProjector(),
        )
        service.runtime = runtime
        projection_task = asyncio.create_task(
            service._project_terminal_return(
                planner.job_id,
                expected_attempt_id=planner.attempt.attempt_id,
            )
        )
        await asyncio.wait_for(projector_entered.wait(), timeout=1)

        close_task = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        close_task.cancel()
        await asyncio.sleep(0)
        assert close_task.done() is False
        assert sends == 1

        projector_release.set()
        with pytest.raises(asyncio.CancelledError):
            await close_task
        await projection_task
        assert service._terminal_return_flights == {}
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

        class NoSecondSendProjector:
            async def project(self, _candidate, *, before_write):
                del before_write
                raise AssertionError("restart must not send an applied result")

            async def reconcile(self, _candidate):
                raise AssertionError("restart must not reconcile an applied result")

        restarted = ExecutiveControlService(
            _config(tmp_path / "restarted"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=NoSecondSendProjector(),
        )
        restarted.runtime = runtime
        await restarted._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )
        assert restarted._terminal_return_last_diagnostic == (
            "terminal-return:ALREADY_APPLIED"
        )

    asyncio.run(exercise())


def test_effect_unknown_restart_reconciles_read_only_and_never_sends_twice(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-EFFECT-UNKNOWN-RESTART",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id

        class EffectUnknownProjector:
            def __init__(self) -> None:
                self.project_calls = 0
                self.reconcile_calls = 0

            async def project(self, _candidate):
                self.project_calls += 1
                raise TerminalReturnProjectionError("EFFECT_UNKNOWN")

            async def reconcile(self, _candidate):
                self.reconcile_calls += 1
                return None

            async def __call__(self, candidate):
                return await self.project(candidate)

        first_projector = EffectUnknownProjector()
        first = ExecutiveControlService(
            _config(tmp_path / "first"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=first_projector,
        )
        first.runtime = runtime
        await first._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert first_projector.project_calls == 1
        assert first._terminal_return_last_diagnostic == (
            "terminal-return:EFFECT_UNKNOWN"
        )

        restarted_projector = EffectUnknownProjector()
        restarted = ExecutiveControlService(
            _config(tmp_path / "restarted"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=restarted_projector,
        )
        restarted.runtime = runtime
        await restarted._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )

        assert restarted_projector.project_calls == 0
        assert restarted_projector.reconcile_calls == 1
        assert restarted._terminal_return_last_diagnostic == (
            "terminal-return:EFFECT_UNKNOWN"
        )
        projection_events = runtime.events.list_events(
            attempt_id=attempt_id,
            command_id_prefix=f"terminal-return:{attempt_id}:",
        )
        assert [event.event_type for event in projection_events] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN",
        ]

        class RecoveredProjector(EffectUnknownProjector):
            async def reconcile(self, candidate):
                self.reconcile_calls += 1
                return _projection_receipt(candidate, action="RECOVERED")

        recovered_projector = RecoveredProjector()
        recovered = ExecutiveControlService(
            _config(tmp_path / "recovered"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=recovered_projector,
        )
        recovered.runtime = runtime
        await recovered._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert recovered_projector.project_calls == 0
        assert recovered_projector.reconcile_calls == 1
        assert recovered._terminal_return_last_diagnostic == "terminal-return:APPLIED"

        already_applied_projector = EffectUnknownProjector()
        already_applied = ExecutiveControlService(
            _config(tmp_path / "already-applied"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=already_applied_projector,
        )
        already_applied.runtime = runtime
        await already_applied._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert already_applied_projector.project_calls == 0
        assert already_applied_projector.reconcile_calls == 0
        assert already_applied._terminal_return_last_diagnostic == (
            "terminal-return:ALREADY_APPLIED"
        )
        projection_events = runtime.events.list_events(
            attempt_id=attempt_id,
            command_id_prefix=f"terminal-return:{attempt_id}:",
        )
        assert [event.event_type for event in projection_events] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_pre_submit_refusal_is_durable_and_recoverable(
    tmp_path: Path,
) -> None:
    """A proven no-send refusal may retry; a possible dispatch may not."""

    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-PRE-SUBMIT-REFUSAL",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id

        class PreSubmitRefusal:
            project_calls = 0
            reconcile_calls = 0

            async def project(self, _candidate, *, before_write):
                self.project_calls += 1
                raise TerminalReturnProjectionError("DIALOGUE_BINDING_UNAVAILABLE")

            async def reconcile(self, _candidate):
                self.reconcile_calls += 1
                raise AssertionError("a proven pre-submit refusal must not reconcile")

        refused_projector = PreSubmitRefusal()
        refused = ExecutiveControlService(
            _config(tmp_path / "refused"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=refused_projector,
        )
        refused.runtime = runtime
        await refused._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert refused._terminal_return_last_diagnostic == (
            "terminal-return:PRE_SUBMIT_REFUSED:DIALOGUE_BINDING_UNAVAILABLE"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
        ]

        class RecoveredProjector:
            project_calls = 0
            reconcile_calls = 0

            async def project(self, candidate, *, before_write):
                self.project_calls += 1
                before_write()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                self.reconcile_calls += 1
                raise AssertionError("recoverable pre-submit state must retry project")

        recovered_projector = RecoveredProjector()
        recovered = ExecutiveControlService(
            _config(tmp_path / "recovered-pre-submit"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=recovered_projector,
        )
        recovered.runtime = runtime
        await recovered._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert recovered_projector.project_calls == 1
        assert recovered_projector.reconcile_calls == 0
        assert recovered._terminal_return_last_diagnostic == "terminal-return:APPLIED"
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_projection_is_single_flight_per_service(
    tmp_path: Path,
) -> None:
    """Concurrent offers of one durable candidate may cross Relay only once."""

    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-SINGLE-FLIGHT",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id

        class BlockingProjector:
            def __init__(self) -> None:
                self.project_calls = 0
                self.entered = asyncio.Event()
                self.release = asyncio.Event()

            async def project(self, candidate, *, before_write):
                self.project_calls += 1
                self.entered.set()
                await self.release.wait()
                before_write()
                return _projection_receipt(candidate)

        projector = BlockingProjector()
        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=projector,
        )
        service.runtime = runtime
        assert not hasattr(service, "_terminal_return_candidates")

        first = asyncio.create_task(
            service._project_terminal_return(
                planner.job_id,
                expected_attempt_id=attempt_id,
            )
        )
        await asyncio.wait_for(projector.entered.wait(), timeout=1)
        second = asyncio.create_task(
            service._project_terminal_return(
                planner.job_id,
                expected_attempt_id=attempt_id,
            )
        )
        await asyncio.sleep(0)
        projector.release.set()
        await asyncio.gather(first, second)

        assert projector.project_calls == 1
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_prepared_material_conflict_refuses_across_restart(
    tmp_path: Path,
) -> None:
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-SERVICE-TERMINAL-DURABLE-CANDIDATE-CONFLICT",
            review_workers=["worker-b"],
        )
    )
    attempt_id = planner.attempt.attempt_id
    material = runtime.validated_role_completion(
        planner.job_id,
        expected_attempt_id=attempt_id,
    )
    candidate = reduce_terminal_return(material=material)

    first = ExecutiveControlService(
        _config(tmp_path / "first"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=lambda _candidate: None,
    )
    first.runtime = runtime
    phase, _applied_command, _event_material = (
        first._begin_terminal_return_projection(candidate)
    )
    assert phase == "PREPARED"

    alternate_digest = (
        "0" * 64 if candidate.terminal_digest != "0" * 64 else "1" * 64
    )
    conflicting = dataclasses.replace(
        candidate,
        terminal_evidence_digest=alternate_digest,
        message_key=f"asd-exec-result-{alternate_digest}",
    )
    restarted = ExecutiveControlService(
        _config(tmp_path / "restarted"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=lambda _candidate: None,
    )
    restarted.runtime = runtime

    with pytest.raises(StateConflict, match="projection event drifted"):
        restarted._begin_terminal_return_projection(conflicting)

    prepared = [
        event
        for event in runtime.events.list_events(
            attempt_id=attempt_id,
            aggregate_type="terminal_return_projection",
            aggregate_id=attempt_id,
        )
        if event.event_type == "EXECUTIVE_TERMINAL_RETURN_PREPARED"
    ]
    assert len(prepared) == 1


def test_terminal_return_tick_does_not_automatically_reoffer_pre_submit_refusal(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-PRE-SUBMIT-TICK",
                review_workers=["worker-b"],
            )
        )

        class RecoveringProjector:
            def __init__(self) -> None:
                self.available = False
                self.project_calls = 0

            async def project(self, candidate, *, before_write):
                self.project_calls += 1
                if not self.available:
                    raise TerminalReturnProjectionError("SERVICE_UNAVAILABLE")
                before_write()
                return _projection_receipt(candidate)

        projector = RecoveringProjector()
        service = ExecutiveControlService(
            _config(
                tmp_path / "service",
                coo_tick_interval_seconds=1.0,
            ),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=projector,
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:PRE_SUBMIT_REFUSED:SERVICE_UNAVAILABLE"
        )

        projector.available = True
        service._coo_shutdown_event = asyncio.Event()
        tick = asyncio.create_task(service._coo_tick_loop())
        await asyncio.sleep(1.1)
        service._coo_shutdown_event.set()
        await tick

        assert projector.project_calls == 1
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:PRE_SUBMIT_REFUSED:SERVICE_UNAVAILABLE"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
        ]

    asyncio.run(exercise())


def test_terminal_return_result_without_dispatch_boundary_is_typed_refusal(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-PROTOCOL-REFUSED",
                review_workers=["worker-b"],
            )
        )

        class InvalidProjector:
            async def project(self, candidate, *, before_write):
                del before_write
                return _projection_receipt(candidate, action="POSTED")

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=InvalidProjector(),
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert service._terminal_return_last_diagnostic == (
            "terminal-return:PRE_SUBMIT_REFUSED:PRE_SUBMIT_PROTOCOL_REFUSED"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
        ]

    asyncio.run(exercise())


def test_terminal_return_applied_requires_atomic_action_predecessor(
    tmp_path: Path,
) -> None:
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-SERVICE-TERMINAL-ATOMIC-PREDECESSOR",
            review_workers=["worker-b"],
        )
    )
    material = runtime.validated_role_completion(
        planner.job_id,
        expected_attempt_id=planner.attempt.attempt_id,
    )
    candidate = reduce_terminal_return(material=material)
    service = ExecutiveControlService(
        _config(tmp_path / "service"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=lambda _candidate: None,
    )
    service.runtime = runtime
    phase, applied_command, event_material = (
        service._begin_terminal_return_projection(candidate)
    )
    assert phase == "PREPARED"

    with pytest.raises(StateConflict, match="phase order drifted"):
        service._complete_terminal_return_projection(
            candidate,
            applied_command=applied_command,
            material=event_material,
            projection_receipt=_projection_receipt(candidate, action="POSTED"),
        )
    assert [
        event.event_type
        for event in runtime.events.list_events(
            attempt_id=planner.attempt.attempt_id,
            command_id_prefix=f"terminal-return:{planner.attempt.attempt_id}:",
        )
    ] == ["EXECUTIVE_TERMINAL_RETURN_PREPARED"]


def test_terminal_return_phase_write_revalidates_every_predecessor(
    tmp_path: Path,
) -> None:
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-SERVICE-TERMINAL-PHASE-RACE-DRIFT",
            review_workers=["worker-b"],
        )
    )
    material = runtime.validated_role_completion(
        planner.job_id,
        expected_attempt_id=planner.attempt.attempt_id,
    )
    candidate = reduce_terminal_return(material=material)
    service = ExecutiveControlService(
        _config(tmp_path / "service"),
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        terminal_return_projector=lambda _candidate: None,
    )
    service.runtime = runtime
    phase, applied_command, event_material = (
        service._begin_terminal_return_projection(candidate)
    )
    assert phase == "PREPARED"
    command_base, _ = service._terminal_return_event_material(candidate)
    drifted = {**event_material, "root_job_id": "JOB-FOREIGN"}
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="terminal_return_projection",
            aggregate_id=candidate.attempt_id,
            event_type="EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
            actor="foreign-writer",
            job_id=candidate.job_id,
            attempt_id=candidate.attempt_id,
            worker_id=candidate.worker_id,
            payload=drifted,
            command_id=f"{command_base}:pre-submit-refused",
        )

    with pytest.raises(StateConflict, match="projection event drifted"):
        service._record_terminal_return_phase(
            candidate,
            phase="ATTEMPTED",
            material=event_material,
        )
    with pytest.raises(StateConflict, match="projection event drifted"):
        service._complete_terminal_return_projection(
            candidate,
            applied_command=applied_command,
            material=event_material,
            projection_receipt=_projection_receipt(candidate, action="DUPLICATE"),
        )
    assert [
        event.event_type
        for event in runtime.events.list_events(
            attempt_id=candidate.attempt_id,
            command_id_prefix=f"terminal-return:{candidate.attempt_id}:",
        )
    ] == [
        "EXECUTIVE_TERMINAL_RETURN_PREPARED",
        "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
    ]


def test_terminal_return_phase_race_quarantines_without_provider_commit_or_append(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-PHASE-RACE-QUARANTINE",
                review_workers=["worker-b"],
            )
        )
        provider_commits = 0

        class RacingProjector:
            async def project(self, candidate, *, before_write):
                nonlocal provider_commits
                command_base, material = service._terminal_return_event_material(
                    candidate
                )
                drifted = {**material, "root_job_id": "JOB-FOREIGN"}
                with runtime.store.transaction() as connection:
                    runtime.store.append_event(
                        connection,
                        aggregate_type="terminal_return_projection",
                        aggregate_id=candidate.attempt_id,
                        event_type=(
                            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED"
                        ),
                        actor="foreign-writer",
                        job_id=candidate.job_id,
                        attempt_id=candidate.attempt_id,
                        worker_id=candidate.worker_id,
                        payload=drifted,
                        command_id=f"{command_base}:pre-submit-refused",
                    )
                before_write()
                provider_commits += 1
                return _projection_receipt(candidate)

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=RacingProjector(),
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert provider_commits == 0
        assert service.service_state == "QUARANTINED"
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:EVIDENCE_REFUSED"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_PRE_SUBMIT_REFUSED",
        ]
        assert service._terminal_return_flights == {}

    asyncio.run(exercise())


def test_terminal_return_known_zero_after_commit_remains_retryable(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-PROVEN-NO-EFFECT",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id

        class KnownZeroProjector:
            async def project(self, _candidate, *, before_write):
                before_write()
                raise TerminalReturnProjectionError("TRANSPORT_UNAVAILABLE")

        first = ExecutiveControlService(
            _config(tmp_path / "first"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=KnownZeroProjector(),
        )
        first.runtime = runtime
        await first._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert first._terminal_return_last_diagnostic == (
            "terminal-return:PROVEN_NO_EFFECT:TRANSPORT_UNAVAILABLE"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_PROVEN_NO_EFFECT",
        ]

        class RecoveredProjector:
            async def project(self, candidate, *, before_write):
                before_write()
                # A commissioned retry may discover that another exact actor
                # already posted the immutable message after the prior proven
                # no-effect attempt.  DUPLICATE is a valid terminal receipt.
                return _projection_receipt(candidate, action="DUPLICATE")

        restarted = ExecutiveControlService(
            _config(tmp_path / "restarted"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=RecoveredProjector(),
        )
        restarted.runtime = runtime
        await restarted._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert restarted._terminal_return_last_diagnostic == "terminal-return:APPLIED"
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_PROVEN_NO_EFFECT",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_exact_duplicate_applies_without_false_attempt(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-EXACT-DUPLICATE",
                review_workers=["worker-b"],
            )
        )

        class DuplicateProjector:
            async def project(self, candidate, *, before_write):
                del before_write
                return _projection_receipt(candidate, action="DUPLICATE")

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=DuplicateProjector(),
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert service._terminal_return_last_diagnostic == "terminal-return:APPLIED"
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_post_commit_duplicate_applies_after_attempted_boundary(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-POST-COMMIT-DUPLICATE",
                review_workers=["worker-b"],
            )
        )

        class DuplicateAfterCommitProjector:
            async def project(self, candidate, *, before_write):
                before_write()
                return _projection_receipt(candidate, action="DUPLICATE")

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=DuplicateAfterCommitProjector(),
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert service.service_state == "READY"
        assert service._terminal_return_last_diagnostic == "terminal-return:APPLIED"
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_APPLIED",
        ]

    asyncio.run(exercise())


def test_terminal_return_refuses_malformed_applied_receipt_as_effect_unknown(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-MALFORMED-RECEIPT",
                review_workers=["worker-b"],
            )
        )

        class MalformedReceiptProjector:
            async def project(self, _candidate, *, before_write):
                before_write()
                return {
                    "action": "POSTED",
                    "message_key": "asd-exec-result-wrong",
                    "fingerprint": "f" * 64,
                    "message_ts": "1787961600.000002",
                    "duplicate_timestamps": [],
                }

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=MalformedReceiptProjector(),
        )
        service.runtime = runtime
        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert service._terminal_return_last_diagnostic == (
            "terminal-return:EFFECT_UNKNOWN:StateConflict"
        )
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=planner.attempt.attempt_id,
                command_id_prefix=(
                    f"terminal-return:{planner.attempt.attempt_id}:"
                ),
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN",
        ]

    asyncio.run(exercise())


def test_terminal_return_attempted_then_unknown_is_reconcile_only_after_restart(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-ATTEMPTED-UNKNOWN",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id

        class PossibleDispatch:
            def __init__(self) -> None:
                self.project_calls = 0
                self.reconcile_calls = 0

            async def project(self, _candidate, *, before_write):
                self.project_calls += 1
                before_write()
                raise TerminalReturnProjectionError("EFFECT_UNKNOWN")

            async def reconcile(self, _candidate):
                self.reconcile_calls += 1
                return None

        first_projector = PossibleDispatch()
        first = ExecutiveControlService(
            _config(tmp_path / "first-attempted"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=first_projector,
        )
        first.runtime = runtime
        await first._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert first._terminal_return_last_diagnostic == "terminal-return:EFFECT_UNKNOWN"

        restarted_projector = PossibleDispatch()
        restarted = ExecutiveControlService(
            _config(tmp_path / "restart-attempted"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=restarted_projector,
        )
        restarted.runtime = runtime
        await restarted._project_terminal_return(
            planner.job_id,
            expected_attempt_id=attempt_id,
        )
        assert restarted_projector.project_calls == 0
        assert restarted_projector.reconcile_calls == 1
        assert [
            event.event_type
            for event in runtime.events.list_events(
                attempt_id=attempt_id,
                command_id_prefix=f"terminal-return:{attempt_id}:",
            )
        ] == [
            "EXECUTIVE_TERMINAL_RETURN_PREPARED",
            "EXECUTIVE_TERMINAL_RETURN_ATTEMPTED",
            "EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN",
        ]

    asyncio.run(exercise())


def test_pickup_reuses_runtime_terminal_validation_after_seal_event_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A projector-local receipt checker must not accept a lost Runtime seal."""

    async def exercise() -> None:
        runtime, _cycle, _dispatches, root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-TERMINAL-CANONICAL-VALIDATOR",
                review_workers=["worker-b"],
            )
        )
        attempt_id = planner.attempt.attempt_id
        _delete_terminal_seal_event(runtime, attempt_id)
        before_projection_events = tuple(runtime.events.list_events())
        canonical_calls: list[tuple[str, str, str]] = []
        actual_validator = er_mod._validated_role_completion_material

        def observed_validator(connection, *, job_row, expected_role, root_job_id):
            canonical_calls.append(
                (str(job_row["current_attempt_id"]), expected_role, root_job_id)
            )
            return actual_validator(
                connection,
                job_row=job_row,
                expected_role=expected_role,
                root_job_id=root_job_id,
            )

        monkeypatch.setattr(
            er_mod,
            "_validated_role_completion_material",
            observed_validator,
        )

        received: list[TerminalReturnCandidate] = []
        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
        )
        service.runtime = runtime
        try:
            await service._project_terminal_return(
                planner.job_id,
                expected_attempt_id=attempt_id,
            )

            assert canonical_calls == [(attempt_id, "plan", root.job_id)]
            assert received == []
            assert service._terminal_return_last_diagnostic == (
                "terminal-return:EVIDENCE_REFUSED"
            )
            assert tuple(runtime.events.list_events()) == before_projection_events
            assert runtime.jobs.get_job(planner.job_id).status is JobStatus.COMPLETED
            assert (
                runtime.attempts.get_attempt(attempt_id).status
                is AttemptStatus.COMPLETED
            )
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_pickup_refuses_unvalidated_sealed_worker_terminal_receipt_shape(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, child, body = _pending_review(
            tmp_path, intent_id="CEO-SERVICE-SEALED-WORKER"
        )
        dispatch = runtime.attempts.dispatch_cycle_job(
            child.job_id,
            command_id=_first_dispatch_command(child),
            worker_id="worker-b",
        )
        assert dispatch is not None and dispatch.lease_token is not None
        _complete_ohf_role(runtime, dispatch, body, identity_seed=747)
        job = runtime.jobs.get_job(child.job_id)
        attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
        worker = runtime.workers.get_worker("worker-b")
        assert job is not None and attempt is not None and worker is not None
        receipt = dict(attempt.result)
        receipt["execution_mode"] = "SEALED_WORKER"
        receipt["result_seal_command_id"] = f"sealed-worker-result:{attempt.attempt_id}"
        receipt["result_evidence"] = {
            "schema_version": "fixture",
            "secret": "must-not-project",
        }
        unsigned = dict(receipt)
        unsigned.pop("terminal_evidence_digest")
        receipt["terminal_evidence_digest"] = canonical_digest(unsigned)
        sealed_job = dataclasses.replace(job, result=receipt)
        sealed_attempt = dataclasses.replace(
            attempt, execution_mode="SEALED_WORKER", result=receipt
        )
        received: list[TerminalReturnCandidate] = []
        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=lambda candidate: _capture_projection(
                received, candidate
            ),
        )
        service.runtime = SimpleNamespace(
            validated_role_completion=lambda *_args, **_kwargs: (
                _ for _ in ()
            ).throw(StateConflict("unvalidated SEALED_WORKER receipt")),
        )
        await service._project_terminal_return(
            child.job_id, expected_attempt_id=attempt.attempt_id
        )
        assert received == []
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:EVIDENCE_REFUSED"
        )
        await service.close()

    asyncio.run(exercise())


def test_armed_service_requires_an_explicit_autonomy_guard(
    tmp_path: Path, short_socket_root: Path
) -> None:
    config = _config(
        tmp_path,
        socket_root=short_socket_root,
        coo_autonomy_armed=True,
    )
    with pytest.raises(ValueError, match="autonomy guard"):
        ExecutiveControlService(
            config,
            supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        )


def test_armed_startup_guard_refuses_before_runtime_or_socket_mutation(
    tmp_path: Path, short_socket_root: Path
) -> None:
    config = _config(
        tmp_path,
        socket_root=short_socket_root,
        coo_autonomy_armed=True,
    )
    calls = []

    def guard() -> None:
        calls.append("guard")
        raise RuntimeError("expired receipt details must not escape")

    def runtime_factory(_root):
        calls.append("runtime")
        raise AssertionError("runtime must not open after guard refusal")

    service = ExecutiveControlService(
        config,
        runtime_factory=runtime_factory,
        supervisor_factory=lambda runtime: _FakeSupervisor(runtime),
        autonomy_guard=guard,
    )
    with pytest.raises(StateConflict, match="autonomy receipt refused"):
        asyncio.run(service.start())
    assert calls == ["guard"]
    assert service.service_state == "QUARANTINED"
    assert not config.socket_path.exists()


def test_guard_runs_again_before_each_explicit_coo_cycle(
    tmp_path: Path, short_socket_root: Path
) -> None:
    async def exercise() -> None:
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=3600.0,
        )
        calls = []

        def guard() -> None:
            calls.append("guard")
            if len(calls) == 3:
                raise RuntimeError("receipt expired")

        holder = {}

        def factory(runtime):
            holder["supervisor"] = _FakeSupervisor(runtime)
            return holder["supervisor"]

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            autonomy_guard=guard,
        )
        await service.start()
        try:
            assert calls == ["guard"]
            assert (await _request(service, "register-worker"))["ok"] is True
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "guarded")},
            )
            root_id = submitted["result"]["job_id"]
            first = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert first["ok"] is True
            assert calls == ["guard", "guard"]

            refused = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert refused["ok"] is False
            assert "autonomy receipt refused" in refused["error"]["message"]
            assert "expired" not in json.dumps(refused)
            assert service.service_state == "QUARANTINED"
        finally:
            await service.close()

    asyncio.run(exercise())


async def _request(service: ExecutiveControlService, command: str, args=None):
    return await send_control_request(service.socket_path, command, args or {})


async def _raw_request(path: Path, raw: bytes) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(raw)
        await writer.drain()
        response = await reader.readline()
        return json.loads(response)
    finally:
        writer.close()
        await writer.wait_closed()


def _coo_intent(config: ServiceConfig, name: str) -> dict:
    workspace_name = f"coo-{name.lower()}"
    branch = f"codex/coo-fixture-{name.lower()}"
    receipt = prepare_credentialless_clone(
        config.proof_source_repository,
        config.proof_workspace_root,
        job_id=workspace_name,
        base_sha=config.proof_base_sha,
        branch=branch,
        shared_gid=config.proof_shared_gid,
    )
    return {
        "schema": "mastermind.ceo_intent.v2",
        "intent_id": f"CEO-G1-{name.upper()}",
        "actor": "ceo-sol",
        "objective": f"Execute one bounded G1 cycle fixture {name}.",
        "department": "executive-infrastructure",
        "priority": 9,
        "grounding": {
            "mastermind_sha": config.proof_base_sha,
            "macro_sha": "b" * 40,
        },
        "execution_contract": {
            "requested_authorities": ["READ"],
            "branch": branch,
            "worktree": receipt.workspace_path,
            "attempt_limit": 2,
        },
        "intent_kind": "executive_coo_cycle",
        "business_impact": "routine",
    }


def _terminal_dialogue_source() -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": "WS:EXECUTIVE-OS",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "c" * 40,
            "path": "docs/commissions/executive-terminal-return.md",
            "content_sha256": "d" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }


def test_v2_public_dialogue_source_is_rejected_before_admission(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    intent = _coo_intent(config, "dialogue-source")
    intent["workstream"] = "WS:EXECUTIVE-OS"
    intent["dialogue_source"] = _terminal_dialogue_source()

    with pytest.raises(ceo_intent_mod.CeoIntentError, match="unexpected key"):
        ceo_intent_mod.validate_intent(intent)
    assert runtime.jobs.list_jobs() == []


def test_v2_trusted_host_dialogue_source_is_immutable_in_root_creation(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    source_state: list[dict[str, object] | None] = [_terminal_dialogue_source()]
    provider_calls: list[tuple[str, str]] = []

    def source_provider(intent_id: str, workstream: str):
        provider_calls.append((intent_id, workstream))
        return source_state[0]

    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=source_provider,
    )
    service.runtime = runtime
    intent = _coo_intent(config, "dialogue-source")
    intent["workstream"] = "WS:EXECUTIVE-OS"

    receipt = service._submit_service_intent(intent)
    duplicate = service._submit_service_intent(intent)
    event = runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(intent["intent_id"])
    )
    assert event is not None
    assert event["payload"]["provenance"]["dialogue_source"] == source_state[0]
    expected_source_digest = hashlib.sha256(
        json.dumps(
            source_state[0],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert event["payload"]["provenance"]["dialogue_source_digest"] == expected_source_digest
    assert event["payload"]["provenance"]["fingerprint"] == (
        ceo_intent_mod.intent_fingerprint(intent)
    )
    assert "dialogue_source" not in intent
    assert duplicate["duplicate"] is True
    assert duplicate["job_id"] == receipt["job_id"]
    # Admission observes and immediately re-observes one deep-frozen source.
    # Durable replay is source-provider independent.
    assert provider_calls == [(intent["intent_id"], intent["workstream"])] * 2

    original_source = _terminal_dialogue_source()
    source_state[0] = {
        **original_source,
        "commission_ref": {
            **original_source["commission_ref"],
            "commit": "e" * 40,
        },
    }
    replay_after_provider_drift = service._submit_service_intent(intent)
    assert replay_after_provider_drift["duplicate"] is True

    source_state[0] = None
    replay_during_provider_outage = service._submit_service_intent(intent)
    assert replay_during_provider_outage["duplicate"] is True
    assert provider_calls == [(intent["intent_id"], intent["workstream"])] * 2
    assert [job.job_id for job in runtime.jobs.list_jobs()] == [receipt["job_id"]]


def test_v2_dialogue_source_digest_drift_refuses_replay_and_status(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    source = _terminal_dialogue_source()
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=(
            lambda _intent_id, _workstream: source
        ),
    )
    service.runtime = runtime
    intent = _coo_intent(config, "dialogue-source-digest-drift")
    intent["workstream"] = "WS:EXECUTIVE-OS"
    service._submit_service_intent(intent)

    command_id = ceo_intent_mod.command_id_for(intent["intent_id"])
    event = runtime.store.find_event_by_command_id(command_id)
    assert event is not None
    payload = event["payload"]
    payload["provenance"]["dialogue_source_digest"] = "0" * 64
    # Simulate out-of-band disk corruption by bypassing the normal immutable
    # Event API. The production writer can never perform this update.
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute("DROP TRIGGER events_are_immutable_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                command_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ceo_intent_mod.CeoIntentError, match="drifted"):
        service._submit_service_intent(intent)
    with pytest.raises(ceo_intent_mod.CeoIntentError, match="drifted"):
        ceo_intent_mod.resolve_intent(
            runtime,
            intent["intent_id"],
        )


def test_v2_dialogue_source_reobservation_drift_refuses_before_root_creation(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    first_source = _terminal_dialogue_source()
    second_source = {
        **first_source,
        "commission_ref": {
            **first_source["commission_ref"],
            "commit": "e" * 40,
        },
    }
    source_iterator = iter((first_source, second_source))

    def source_provider(_intent_id: str, _workstream: str):
        return next(source_iterator)

    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=source_provider,
    )
    service.runtime = runtime
    intent = _coo_intent(config, "dialogue-source-concurrent-divergence")
    intent["workstream"] = "WS:EXECUTIVE-OS"

    with pytest.raises(ceo_intent_mod.CeoIntentConflict, match="changed"):
        service._submit_service_intent(intent)
    assert runtime.jobs.list_jobs() == []
    assert runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(intent["intent_id"])
    ) is None


@pytest.mark.parametrize(
    "provider",
    [
        pytest.param(
            lambda _intent_id, _workstream: {
                **_terminal_dialogue_source(),
                "work_ref": "WS:FOREIGN",
            },
            id="work-ref-mismatch",
        ),
        pytest.param(
            lambda _intent_id, _workstream: {"schema_version": "malformed"},
            id="malformed",
        ),
        pytest.param(
            lambda _intent_id, _workstream: (_ for _ in ()).throw(
                RuntimeError("provider unavailable")
            ),
            id="provider-error",
        ),
        pytest.param(
            lambda _intent_id, _workstream: None,
            id="missing",
        ),
    ],
)
def test_invalid_trusted_dialogue_source_refuses_before_root_creation(
    tmp_path: Path,
    provider,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=provider,
    )
    service.runtime = runtime
    intent = _coo_intent(config, "invalid-dialogue-source")
    intent["workstream"] = "WS:EXECUTIVE-OS"

    with pytest.raises(ceo_intent_mod.CeoIntentError):
        service._submit_service_intent(intent)

    assert runtime.jobs.list_jobs() == []
    assert runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(intent["intent_id"])
    ) is None


def test_v2_ingress_public_frame_refuses_dialogue_source_before_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def should_not_submit(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ceo_ingress_mod, "_handle_submit_v2", should_not_submit)
    frame = {
        "schema": ceo_ingress_mod.SUBMIT_SCHEMA_V2,
        "request_ref": "req-r2-public-source-refusal-20260903-001",
        "observed_grounding": {"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        "request": {
            "objective": "Run one bounded Executive terminal-return fixture.",
            "department": "executive-infrastructure",
            "priority": 9,
            "execution_profile": "research_only",
            "workstream": "WS:EXECUTIVE-OS",
            "attempt_limit": 2,
        },
        "dialogue_source": _terminal_dialogue_source(),
    }

    with pytest.raises(ceo_ingress_mod.CeoIngressError) as refused:
        asyncio.run(
            ceo_ingress_mod.handle_frame(
                frame,
                runtime=object(),
                grounding_provider=object(),
                workspace_root=tmp_path,
                service_state="READY",
                ceo_ingress_armed=True,
            )
        )
    assert refused.value.code == "invalid_input"
    assert called is False

    nested = dict(frame["request"])
    nested["dialogue_source"] = _terminal_dialogue_source()
    with pytest.raises(ceo_ingress_mod.ceo_request.CeoRequestInvalid):
        ceo_ingress_mod.ceo_request.normalize_automated_request(nested)


def test_v2_ingress_builds_a_source_free_strict_v2_envelope(tmp_path: Path) -> None:
    normalized = ceo_ingress_mod.ceo_request.normalize_automated_request(
        {
            "objective": "Run one bounded Executive terminal-return fixture.",
            "department": "executive-infrastructure",
            "priority": 9,
            "execution_profile": "research_only",
            "workstream": "WS:EXECUTIVE-OS",
            "attempt_limit": 2,
        }
    )
    envelope = ceo_ingress_mod._build_envelope(
        normalized,
        intent_id="auto-" + "1" * 32,
        workspace_root=tmp_path,
        grounding={"mastermind_sha": "a" * 40, "macro_sha": "b" * 40},
        strict_v2=True,
    )

    assert envelope["schema"] == ceo_intent_mod.INTENT_SCHEMA_V2
    assert "dialogue_source" not in envelope
    assert ceo_intent_mod.validate_intent(envelope) == envelope


def test_v2_ingress_host_source_provider_selects_source_free_strict_root(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    provider_calls: list[tuple[str, str]] = []

    def source_provider(intent_id: str, workstream: str):
        provider_calls.append((intent_id, workstream))
        return _terminal_dialogue_source()

    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=source_provider,
    )
    service.runtime = runtime
    grounding = {
        "mastermind_sha": config.proof_base_sha,
        "macro_sha": "b" * 40,
        "boot_packet_schema": ceo_ingress_mod.BOOT_PACKET_SCHEMA,
    }

    class GroundingProvider:
        def observe(self):
            return dict(grounding)

    frame = {
        "schema": ceo_ingress_mod.SUBMIT_SCHEMA_V2,
        "request_ref": "req-r2-host-source-20260903-001",
        "observed_grounding": grounding,
        "request": {
            "objective": "Run one bounded Executive terminal-return fixture.",
            "department": "executive-infrastructure",
            "priority": 9,
            "execution_profile": "research_only",
            "workstream": "WS:EXECUTIVE-OS",
            "attempt_limit": 2,
        },
    }

    async def submit_twice():
        async def submit():
            return await ceo_ingress_mod.handle_frame(
                frame,
                runtime=runtime,
                grounding_provider=GroundingProvider(),
                workspace_root=config.proof_workspace_root,
                service_state="READY",
                ceo_ingress_armed=True,
                strict_v2_admission=True,
                execution_binding_provider=service._require_current_coo_binding,
                dialogue_source_provider=source_provider,
            )

        return [await submit(), await submit()]

    receipts = asyncio.run(submit_twice())
    receipt = receipts[0]

    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    assert root.orchestration_role == "aggregation"
    assert root.orchestration_provenance["creator"] == "ceo_intent"
    event = runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(receipt["intent_id"])
    )
    assert event is not None
    assert event["payload"]["provenance"]["dialogue_source"] == (
        _terminal_dialogue_source()
    )
    assert {item["job_id"] for item in receipts} == {receipt["job_id"]}
    assert sorted(item["duplicate"] for item in receipts) == [False, True]
    assert provider_calls == [
        (receipt["intent_id"], "WS:EXECUTIVE-OS"),
        (receipt["intent_id"], "WS:EXECUTIVE-OS"),
    ]


def test_terminal_return_production_composition_is_explicit_and_complete(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="terminal-return"):
        dataclasses.replace(config, terminal_return_armed=True)

    armed = dataclasses.replace(
        config,
        terminal_return_armed=True,
        terminal_return_socket_path=tmp_path / "agent-relay.sock",
    )

    class GroundingProvider:
        def observe(self):
            return {
                "mastermind_sha": armed.proof_base_sha,
                "macro_sha": "b" * 40,
                "boot_packet_schema": ceo_ingress_mod.BOOT_PACKET_SCHEMA,
            }

    class Projector:
        async def project(self, _candidate, *, before_write=None):
            if before_write is not None:
                before_write()

        async def reconcile(self, _candidate):
            return None

    def projector_factory(_runtime_getter, _socket_path):
        return Projector()

    with pytest.raises(ValueError, match="terminal-return.*CeoIngress"):
        ExecutiveControlService(
            armed,
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            ceo_ingress_socket_path=armed.terminal_return_socket_path,
            ceo_ingress_peer_uid=os.geteuid(),
            ceo_ingress_grounding_provider=GroundingProvider(),
            terminal_return_projector_factory=projector_factory,
        )

    # Terminal-only recovery is a startup capability even while the trusted
    # admission-source provider is unavailable.  A new strict-v2 admission
    # will refuse dynamically; construction must not disable durable replay.
    outage_service = ExecutiveControlService(
        armed,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_socket_path=tmp_path / "ceo-ingress.sock",
        ceo_ingress_peer_uid=os.geteuid(),
        ceo_ingress_grounding_provider=GroundingProvider(),
        ceo_ingress_armed=True,
        terminal_return_projector_factory=projector_factory,
    )
    assert outage_service._terminal_return_projector is not None
    outage_runtime = Runtime.at(armed.runtime_root)
    outage_service.runtime = outage_runtime
    outage_intent = _coo_intent(armed, "armed-source-outage")
    outage_intent["workstream"] = "WS:EXECUTIVE-OS"
    with pytest.raises(
        ceo_intent_mod.CeoIntentError,
        match="trusted host dialogue source is unavailable",
    ):
        outage_service._submit_service_intent(outage_intent)
    assert outage_runtime.jobs.list_jobs() == []
    assert outage_runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(outage_intent["intent_id"])
    ) is None

    service = ExecutiveControlService(
        armed,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=(
            lambda _intent_id, _workstream: _terminal_dialogue_source()
        ),
        terminal_return_projector_factory=projector_factory,
    )
    runtime = Runtime.at(armed.runtime_root)
    service.runtime = runtime
    intent = _coo_intent(armed, "armed-dialogue-source")
    intent["workstream"] = "WS:EXECUTIVE-OS"

    receipt = service._submit_service_intent(intent)

    event = runtime.store.find_event_by_command_id(
        ceo_intent_mod.command_id_for(intent["intent_id"])
    )
    assert receipt["job_id"]
    assert event is not None
    assert event["payload"]["provenance"]["dialogue_source"] == {
        **_terminal_dialogue_source(),
    }
    assert service._terminal_return_projector is not None


def test_armed_terminal_return_skips_source_free_history_without_phase_events(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-SOURCE-FREE-HISTORY",
                review_workers=["worker-b"],
            )
        )
        called = False

        class Projector:
            async def project(self, _candidate, *, before_write=None):
                nonlocal called
                called = True

            async def reconcile(self, _candidate):
                nonlocal called
                called = True

        config = dataclasses.replace(
            _config(tmp_path / "service"),
            terminal_return_armed=True,
            terminal_return_socket_path=tmp_path / "agent-relay.sock",
        )
        service = ExecutiveControlService(
            config,
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector_factory=lambda _runtime, _path: Projector(),
        )
        service.runtime = runtime

        await service._project_terminal_return(
            planner.job_id,
            expected_attempt_id=planner.attempt.attempt_id,
        )

        assert called is False
        assert service._terminal_return_last_diagnostic == (
            "terminal-return:SKIPPED_SOURCE_FREE"
        )
        assert runtime.events.list_events(
            attempt_id=planner.attempt.attempt_id,
            aggregate_type="terminal_return_projection",
        ) == []

    asyncio.run(exercise())


def test_terminal_return_independent_candidates_do_not_share_an_io_lock(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        runtime, _cycle, _dispatches, _root, planner, work, _seal = (
            _cycle_through_completed_work(
                tmp_path / "runtime",
                intent_id="CEO-SERVICE-INDEPENDENT-TERMINALS",
                review_workers=["worker-b"],
            )
        )
        both_entered = asyncio.Event()
        release = asyncio.Event()
        entered: list[str] = []

        class Projector:
            async def project(self, candidate, *, before_write):
                entered.append(candidate.attempt_id)
                if len(entered) == 2:
                    both_entered.set()
                await release.wait()
                before_write()
                return _projection_receipt(candidate)

            async def reconcile(self, _candidate):
                raise AssertionError("a fresh candidate must not reconcile")

        service = ExecutiveControlService(
            _config(tmp_path / "service"),
            supervisor_factory=lambda opened: _FakeSupervisor(opened),
            terminal_return_projector=Projector(),
        )
        service.runtime = runtime
        tasks = [
            asyncio.create_task(
                service._project_terminal_return(
                    item.job_id,
                    expected_attempt_id=item.attempt.attempt_id,
                )
            )
            for item in (planner, work)
        ]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        release.set()
        await asyncio.gather(*tasks)
        assert set(entered) == {
            planner.attempt.attempt_id,
            work.attempt.attempt_id,
        }

    asyncio.run(exercise())


def test_private_unix_service_round_trip_and_fixed_proof_lifecycle(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)

        async def tcp_must_not_start(*args, **kwargs):  # pragma: no cover - assertion hook
            raise AssertionError("Executive service must never create a TCP listener")

        monkeypatch.setattr(asyncio, "start_server", tcp_must_not_start)
        await service.start()
        try:
            assert service._server is not None
            assert service._server.sockets
            assert all(item.family == socket.AF_UNIX for item in service._server.sockets)
            assert stat.S_IMODE(service.socket_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(service.socket_path.parent.stat().st_mode) == 0o700
            assert service.running_marker_path.is_file()
            assert service.service_lock_path.is_file()
            assert stat.S_IMODE(service.running_marker_path.stat().st_mode) == 0o600
            assert stat.S_IMODE(service.service_lock_path.stat().st_mode) == 0o600

            status = await _request(service, "status")
            assert status["ok"] is True
            assert status["result"]["protocol"] == CONTROL_PROTOCOL_VERSION
            assert status["result"]["startup_reconciliation"] == []
            assert holder["supervisor"].requeue_values == [False]

            health = await _request(service, "health")
            assert health["result"]["ok"] is True
            assert health["result"]["journal_mode"].lower() == "wal"
            assert health["result"]["foreign_key_violations"] == 0

            registered = await _request(service, "register-worker")
            assert registered["result"]["worker_id"] == "codex-01"
            # Registration is idempotent only for the exact configured identity.
            assert (await _request(service, "register-worker"))["ok"] is True

            created = await _request(service, "create-proof-job")
            assert created["ok"] is True, created
            job_id = created["result"]["job_id"]
            first_workspace = Path(created["result"]["worktree"])
            assert first_workspace.parent == service.config.proof_workspace_root
            assert first_workspace.name.startswith("proof-")
            assert created["result"]["branch"].endswith(first_workspace.name[6:])
            assert subprocess.run(
                ["git", "-C", str(first_workspace), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip() == service.config.proof_base_sha
            assert subprocess.run(
                ["git", "-C", str(first_workspace), "remote"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert stat.S_IMODE((first_workspace / ".git").stat().st_mode) & 0o020 == 0
            assert (
                stat.S_IMODE((first_workspace / ".codex/config.toml").stat().st_mode)
                & 0o020
                == 0
            )
            proof_parent = (
                first_workspace / "research/executive_os_phase1c_worker_proof"
            )
            assert stat.S_IMODE(proof_parent.stat().st_mode) == 0o770
            assert created["result"]["requested_authorities"] == [
                "READ",
                "RESEARCH",
                "RUN_TESTS",
                "WRITE_BRANCH",
            ]
            assert created["result"]["allowed_write_paths"] == [
                "research/executive_os_phase1c_worker_proof/receipt.md"
            ]
            assert len(created["result"]["validation_commands"]) == 1

            dispatched = await _request(service, "dispatch", {"job_id": job_id})
            assert dispatched["ok"] is True, dispatched
            attempt_id = dispatched["result"]["attempt"]["attempt_id"]
            for _ in range(100):
                inspected = await _request(service, "job", {"job_id": job_id})
                if inspected["result"]["status"] == "COMPLETED":
                    break
                await asyncio.sleep(0.01)
            assert inspected["result"]["status"] == "COMPLETED"
            attempt = await _request(service, "attempt", {"attempt_id": attempt_id})
            assert attempt["result"]["status"] == "COMPLETED"
            assert "lease_token" not in json.dumps(attempt, sort_keys=True)

            # A successful worker leaves its proof artifact behind.  A second
            # proof must receive a fresh workspace rather than inherit it.
            first_artifact = (
                first_workspace
                / "research/executive_os_phase1c_worker_proof/receipt.md"
            )
            first_artifact.parent.mkdir(parents=True, exist_ok=True)
            first_artifact.write_text("completed first proof\n", encoding="utf-8")
            second = await _request(service, "create-proof-job")
            assert second["ok"] is True
            second_workspace = Path(second["result"]["worktree"])
            assert second_workspace != first_workspace
            assert not (second_workspace / first_artifact.relative_to(first_workspace)).exists()
            assert subprocess.run(
                ["git", "-C", str(second_workspace), "status", "--porcelain=v1"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert (await _request(service, "workers"))["result"][0]["worker_id"] == "codex-01"
            assert (await _request(service, "jobs"))["result"][0]["job_id"] == job_id
        finally:
            await service.close()
        assert not service.socket_path.exists()
        assert not service.running_marker_path.exists()

    asyncio.run(exercise())


def test_host_bound_v2_cycle_uses_exact_profile_and_replays_one_attempt(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=3600.0,
        )
        service, holder = _service(
            tmp_path,
            finish_gate=finish_gate,
            config=config,
        )
        await service.start()
        try:
            registered = await _request(service, "register-worker")
            assert registered["ok"] is True
            assert set(registered["result"]["quota_classes"]) == {
                "codex-native",
                "codex-coo",
                "codex-coo-default",
            }
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "one")},
            )
            assert submitted["ok"] is True
            assert submitted["result"]["dispatched"] is False
            root_id = submitted["result"]["job_id"]
            root = service.runtime.jobs.get_job(root_id)
            assert root is not None
            assert root.constraints["routing_policy_version"] == "2026-08-24.stage4"
            assert root.constraints["execution_profile_id"] == (
                "sealed.worker.write.no-extensions.v1"
            )
            assert root.constraints["eligible_quota_classes"] == [
                "codex-coo",
                "codex-coo-default",
            ]
            assert root.constraints["base_sha"] == config.proof_base_sha

            created = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert created["ok"] is True
            assert created["result"]["action"] == "PLANNER_CREATED"
            planner_id = created["result"]["selected_job_id"]

            dispatched = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert dispatched["ok"] is True, dispatched
            assert dispatched["result"]["action"] == "DISPATCHED"
            attempt_id = dispatched["result"]["receipt"]["attempt"]["attempt_id"]
            assert "lease_token" not in json.dumps(dispatched, sort_keys=True)
            assert holder["supervisor"].started_jobs == [planner_id]

            replay = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert replay["ok"] is True
            assert replay["result"]["action"] == "DISPATCHED"
            assert replay["result"]["receipt"]["attempt"]["attempt_id"] == attempt_id
            assert len(service.runtime.attempts.list_attempts(planner_id)) == 1

            submitted_two = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "two")},
            )
            root_two = submitted_two["result"]["job_id"]
            refused = await _request(
                service, "run-coo-cycle", {"root_job_id": root_two}
            )
            assert refused["ok"] is False
            assert "serialized worker" in refused["error"]["message"]
            assert [
                job
                for job in service.runtime.jobs.list_jobs()
                if job.parent_job_id == root_two
            ] == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_armed_operator_lane_binds_read_only_planner_and_not_sealed_worker(
    tmp_path: Path, short_socket_root: Path
) -> None:
    async def exercise() -> None:
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_operator_harness_armed=True,
            coo_tick_interval_seconds=3600.0,
            operator_harness_binary_digest="a" * 64,
            operator_harness_version="0.147.0",
        )
        holder: dict[str, object] = {"verified": 0}

        def sealed_factory(runtime: Runtime):
            supervisor = _FakeSupervisor(runtime)
            holder["sealed"] = supervisor
            return supervisor

        class Operator:
            def __init__(self, runtime: Runtime) -> None:
                self.runtime = runtime
                self.started_jobs: list[str] = []

            def reconcile_restart(self, *, requeue_lost: bool = False):
                assert requeue_lost is False
                return []

            async def start_cycle_job(self, job_id: str, *, command_id: str):
                self.started_jobs.append(job_id)
                outcome = self.runtime.attempts.dispatch_cycle_job(
                    job_id,
                    command_id=command_id,
                    lease_owner="operator-service-fixture",
                )
                assert outcome is not None
                return outcome

        def operator_factory(runtime: Runtime, _sealed):
            operator = Operator(runtime)
            holder["operator"] = operator
            return operator

        async def verify_identity() -> None:
            holder["verified"] = int(holder["verified"]) + 1

        service = ExecutiveControlService(
            config,
            supervisor_factory=sealed_factory,
            operator_supervisor_factory=operator_factory,
            operator_identity_verifier=verify_identity,
            autonomy_guard=lambda: None,
        )
        await service.start()
        try:
            assert holder["verified"] == 1
            assert (await _request(service, "register-worker"))["ok"] is True
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "operator")},
            )
            assert submitted["ok"] is True
            root_id = submitted["result"]["job_id"]
            root = service.runtime.jobs.get_job(root_id)
            assert root is not None
            assert root.constraints["operator_harness_armed"] is True
            assert root.constraints["operator_harness_binary_digest"] == "a" * 64

            created = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert created["ok"] is True, created
            planner_id = created["result"]["selected_job_id"]
            planner = service.runtime.jobs.get_job(planner_id)
            assert planner is not None
            assert planner.constraints["execution_profile_id"] == (
                "operator.appserver.readonly.docs-mcp.native-helper.v1"
            )
            assert planner.constraints["eligible_quota_classes"] == [
                "codex-coo-operator"
            ]
            assert planner.constraints["harness_binary_digest"] == "a" * 64
            assert planner.requested_authorities == ["READ"]
            assert planner.allowed_write_paths == []

            dispatched = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert dispatched["ok"] is True
            assert dispatched["result"]["action"] == "DISPATCHED"
            operator = holder["operator"]
            sealed = holder["sealed"]
            assert operator.started_jobs == [planner_id]
            assert sealed.started_jobs == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_bounded_service_tick_advances_only_one_bound_root_action(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=1.0,
        )
        service, _holder = _service(
            tmp_path,
            finish_gate=finish_gate,
            config=config,
        )
        await service.start()
        try:
            await _request(service, "register-worker")
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "tick")},
            )
            root_id = submitted["result"]["job_id"]
            submitted_two = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "tick-two")},
            )
            root_two = submitted_two["result"]["job_id"]
            children = []
            for _ in range(60):
                children = [
                    job
                    for job in service.runtime.jobs.list_jobs()
                    if job.parent_job_id == root_id
                ]
                if children:
                    break
                await asyncio.sleep(0.025)
            assert len(children) == 1
            assert children[0].orchestration_role == "plan"
            assert service.runtime.attempts.list_attempts(children[0].job_id) == []
            assert [
                job
                for job in service.runtime.jobs.list_jobs()
                if job.parent_job_id == root_two
            ] == []
            assert len(
                [
                    job
                    for job in service.runtime.jobs.list_jobs()
                    if job.orchestration_role == "plan"
                ]
            ) == 1
            status = await _request(service, "status")
            assert status["result"]["coo_autonomy"]["armed"] is True
            assert status["result"]["coo_autonomy"]["last_outcome"]["action"] == (
                "PLANNER_CREATED"
            )
        finally:
            await service.close()

    asyncio.run(exercise())


def test_bounded_service_tick_persists_one_refusal_without_mutating_root(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        config = _config(
            tmp_path,
            socket_root=short_socket_root,
            coo_autonomy_armed=True,
            coo_tick_interval_seconds=1.0,
        )
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "tick-refusal")},
            )
            assert submitted["ok"] is True
            root_id = submitted["result"]["job_id"]

            refusal_events = []
            for _ in range(80):
                refusal_events = [
                    event
                    for event in service.runtime.events.list_events(job_id=root_id)
                    if event.event_type == "COO_SERVICE_TICK_REFUSED"
                ]
                if refusal_events:
                    break
                await asyncio.sleep(0.025)
            assert len(refusal_events) == 1
            assert refusal_events[0].payload["reason_code"] == (
                "bounded_cycle_action_refused"
            )
            assert refusal_events[0].payload["error_type"] == "StateConflict"
            assert [
                job
                for job in service.runtime.jobs.list_jobs()
                if job.parent_job_id == root_id
            ] == []

            await asyncio.sleep(1.1)
            assert len(
                [
                    event
                    for event in service.runtime.events.list_events(job_id=root_id)
                    if event.event_type == "COO_SERVICE_TICK_REFUSED"
                ]
            ) == 1
            status = await _request(service, "status")
            assert "reviewed COO worker identity" in status["result"][
                "coo_autonomy"
            ]["last_error"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_unarmed_service_admits_but_cannot_advance_bound_v2_root(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        config = _config(tmp_path, socket_root=short_socket_root)
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            await _request(service, "register-worker")
            submitted = await _request(
                service,
                "submit-ceo-intent",
                {"intent": _coo_intent(config, "held")},
            )
            root_id = submitted["result"]["job_id"]
            refused = await _request(
                service, "run-coo-cycle", {"root_job_id": root_id}
            )
            assert refused["ok"] is False
            assert "not armed" in refused["error"]["message"]
            assert service._coo_tick_task is None
            assert [
                job
                for job in service.runtime.jobs.list_jobs()
                if job.parent_job_id == root_id
            ] == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_adds_exact_coo_capacity_to_existing_legacy_worker(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        config = _config(tmp_path, socket_root=short_socket_root)
        runtime = Runtime.at(config.runtime_root)
        runtime.workers.register_worker(
            config.worker_id,
            provider=config.provider,
            account_label=config.worker_account_label,
            worker_type=config.worker_type,
            capabilities=["code", "research", "tests"],
            quota_classes={
                config.quota_class: {
                    "provider": config.provider,
                    "model": config.model,
                    "effort": config.effort,
                    "cost_class": config.cost_class,
                    "capabilities": ["code", "research", "tests"],
                }
            },
            metadata={"service_managed": True},
        )
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            registered = await _request(service, "register-worker")
            assert registered["ok"] is True
            assert set(registered["result"]["quota_classes"]) == {
                config.quota_class,
                config.coo_quota_class,
                config.coo_default_quota_class,
            }
            events = [
                event
                for event in service.runtime.events.list_events()
                if event.event_type == "WORKER_QUOTA_REGISTERED"
                and event.worker_id == config.worker_id
            ]
            assert {event.quota_class for event in events} == {
                config.coo_quota_class,
                config.coo_default_quota_class,
            }
            assert (await _request(service, "register-worker"))["ok"] is True
            assert len(
                [
                    event
                    for event in service.runtime.events.list_events()
                    if event.event_type == "WORKER_QUOTA_REGISTERED"
                    and event.worker_id == config.worker_id
                ]
            ) == 2
        finally:
            await service.close()

    asyncio.run(exercise())


def test_caller_cannot_override_reviewed_v2_host_execution_binding(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        config = _config(tmp_path, socket_root=short_socket_root)
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            intent = _coo_intent(config, "binding-conflict")
            intent["execution_contract"]["constraints"] = {
                "cost_class": "default"
            }
            refused = await _request(
                service, "submit-ceo-intent", {"intent": intent}
            )
            assert refused["ok"] is False
            assert "conflicts with reviewed host composition" in refused["error"][
                "message"
            ]
            assert service.runtime.jobs.list_jobs() == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_creation_cannot_cross_manifest_to_worker_start_window(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise() -> None:
        finish_gate = asyncio.Event()
        start_release = asyncio.Event()
        start_entered = asyncio.Event()
        service, holder = _service(
            tmp_path,
            socket_root=short_socket_root,
            finish_gate=finish_gate,
        )
        await service.start()
        try:
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            job_id = proof["result"]["job_id"]
            supervisor = holder["supervisor"]
            original_start = supervisor.start_job

            async def paused_start(value: str):
                # This point represents the interval after the control-side
                # manifest snapshot has begun but before broker start/spawn has
                # returned.  The service lifecycle lock must remain held.
                start_entered.set()
                await start_release.wait()
                return await original_start(value)

            supervisor.start_job = paused_start
            dispatch_task = asyncio.create_task(
                _request(service, "dispatch", {"job_id": job_id})
            )
            await asyncio.wait_for(start_entered.wait(), timeout=1)
            assert service._workspace_lock.locked() is True

            before = sorted(
                path.name for path in service.config.proof_workspace_root.iterdir()
            )
            create_task = asyncio.create_task(
                _request(service, "create-proof-job")
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert create_task.done() is False

            start_release.set()
            dispatched = await asyncio.wait_for(dispatch_task, timeout=1)
            assert dispatched["ok"] is True
            refused = await asyncio.wait_for(create_task, timeout=1)
            assert refused["ok"] is False
            assert "while a worker dispatch is active" in refused["error"]["message"]
            assert sorted(
                path.name for path in service.config.proof_workspace_root.iterdir()
            ) == before
        finally:
            start_release.set()
            finish_gate.set()
            await service.close()

    asyncio.run(exercise())


def test_protocol_rejects_malformed_oversized_unknown_and_argument_injection(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        config = _config(tmp_path, socket_root=short_socket_root, max_request_bytes=1024)
        service, _holder = _service(tmp_path, config=config)
        await service.start()
        try:
            malformed = await _raw_request(service.socket_path, b"{not-json}\n")
            assert malformed["error"]["code"] == "invalid_json"

            wrong_shape = await _raw_request(
                service.socket_path,
                json.dumps({"command": "status"}).encode() + b"\n",
            )
            assert wrong_shape["error"]["code"] == "request_failed"

            unknown = await _request(service, "execute-shell", {"argv": ["/bin/sh"]})
            assert unknown["ok"] is False
            assert "unknown control command" in unknown["error"]["message"]

            injected = await _request(
                service,
                "create-proof-job",
                {"objective": "run arbitrary command", "validation_command": ["/bin/sh"]},
            )
            assert injected["ok"] is False
            assert "exactly these arguments: none" in injected["error"]["message"]

            oversized = await _raw_request(service.socket_path, b"x" * 2048 + b"\n")
            assert oversized["error"]["code"] == "request_too_large"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_dispatch_and_requeue_refuse_nonproof_jobs(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            foreign = runtime.jobs.create_job(
                "Unreviewed operator-created job",
                constraints={
                    "provider": "codex",
                    "eligible_quota_classes": ["codex-native"],
                },
                requested_authorities=["READ"],
            )
            denied = await _request(service, "dispatch", {"job_id": foreign.job_id})
            assert denied["ok"] is False
            assert "fixed harmless proof job" in denied["error"]["message"]

            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            proof_workspace = Path(proof["result"]["worktree"])
            interrupted_artifact = (
                proof_workspace
                / "research/executive_os_phase1c_worker_proof/receipt.md"
            )
            interrupted_artifact.parent.mkdir(parents=True, exist_ok=True)
            interrupted_artifact.write_text(
                "interrupted evidence must survive\n", encoding="utf-8"
            )
            interrupted_inode = proof_workspace.stat().st_ino
            lease = runtime.broker.claim(proof_id, lease_owner="lost-fixture")
            assert lease is not None
            runtime.attempts.record_process(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                provider_session_id="missing-provider-session",
            )
            runtime.attempts.mark_running(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
            )
            runtime.attempts.mark_lost(
                lease.attempt.attempt_id,
                fence_generation=lease.attempt.fence_generation,
                lease_token=lease.lease_token,
                reason="verified fixture absence",
                verified_process_absent=True,
            )
            proof_workspace.chmod(0o700)
            requeued = await _request(service, "requeue", {"job_id": proof_id})
            assert requeued["result"]["status"] == "QUEUED"
            assert requeued["result"]["checkpoint"] is None
            rotation = requeued["result"]["workspace_rotation"]
            archive = Path(rotation["archive_path"])
            receipt_path = Path(rotation["receipt_path"])
            assert archive.parent.parent.parent == service.config.proof_workspace_root
            assert archive.name == lease.attempt.attempt_id
            assert (
                archive / interrupted_artifact.relative_to(proof_workspace)
            ).read_text(encoding="utf-8") == "interrupted evidence must survive\n"
            assert proof_workspace.is_dir()
            assert proof_workspace.stat().st_ino != interrupted_inode
            assert stat.S_IMODE(proof_workspace.stat().st_mode) & 0o070 == 0o050
            assert stat.S_IMODE(archive.stat().st_mode) == 0o700
            index = proof_workspace / ".git" / "index"
            index_mode = stat.S_IMODE(index.stat().st_mode)
            assert index.stat().st_gid == os.getegid()
            assert index_mode & stat.S_IRGRP
            assert not index_mode & stat.S_IWGRP
            assert not index_mode & stat.S_IRWXO
            assert not (proof_workspace / ".git" / "index.lock").exists()
            assert subprocess.run(
                ["git", "-C", str(proof_workspace), "status", "--porcelain=v1"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout == ""
            assert subprocess.run(
                ["git", "-C", str(proof_workspace), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip() == service.config.proof_base_sha
            assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
            receipt_bytes = receipt_path.read_bytes()
            assert hashlib.sha256(receipt_bytes).hexdigest() == rotation["receipt_sha256"]
            receipt = json.loads(receipt_bytes)
            assert receipt["old_workspace"]["inode"] == interrupted_inode
            assert receipt["old_workspace"]["status_dirty"] is True
            assert receipt["new_workspace"]["head"] == service.config.proof_base_sha
            assert receipt["new_workspace"]["status_dirty"] is False
            assert receipt["new_workspace"]["all_untracked_dirty"] is False
            assert receipt["new_workspace"]["launch_clean"] is True
            assert receipt["new_workspace"]["remote_count"] == 0
            assert receipt["new_workspace"]["branch"] == proof["result"]["branch"]
            events = runtime.events.list_events(job_id=proof_id)
            rotation_event = next(
                item for item in events if item.event_type == "PROOF_WORKSPACE_ROTATED"
            )
            assert rotation_event.attempt_id == lease.attempt.attempt_id
            assert rotation_event.payload["receipt_sha256"] == rotation["receipt_sha256"]
            assert events[-1].event_type == "JOB_REQUEUED"

            denied_requeue = await _request(service, "requeue", {"job_id": foreign.job_id})
            assert denied_requeue["ok"] is False
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_reason_reaches_client_as_request_failed(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Real-host repro: ``create-proof-job`` fails inside
    ``prepare_credentialless_clone`` with a ``WorkspaceError``.  That error is
    a bare ``RuntimeError`` (see control_plane/executive_workspace.py), so
    before this fix it fell through to the generic ``internal_error`` handler
    and the operator got only ``WorkspaceError: Executive request failed`` --
    the real reason existed in no channel.  It must now reach the client
    under the EXISTING ``request_failed`` code, carrying the actual reason.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            reason = (
                "source repository is not a directory: "
                "/var/db/nonexistent-mastermind-source"
            )

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(reason)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert failed["error"]["message"] == reason
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_redacts_secret_shaped_material(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Secret-shaped text embedded in a WorkspaceError is redacted before it
    crosses the socket.  common/redaction.py has NO git-object-id exemption
    -- unlike ops/executive_os/acceptance.py's refusal sanitizer, which
    exempts exactly-40 lowercase hex to keep release SHAs comparable/readable
    on that proof path.  This service is not that path, so a 40-hex git
    object id is expected to redact here too; this test pins that divergence
    rather than fighting it.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            token_64_hex = "a" * 64
            git_object_id_40_hex = "b" * 40
            raw = (
                f"workspace clone failed: token={token_64_hex} "
                f"object={git_object_id_40_hex} done"
            )

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(raw)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            message = failed["error"]["message"]
            assert token_64_hex not in message
            assert git_object_id_40_hex not in message
            assert message == (
                "workspace clone failed: token=<redacted> object=<redacted> done"
            )
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_text_is_bounded_at_service_boundary(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """An oversized WorkspaceError message is bounded at the service
    boundary rather than forwarded verbatim.  The explicit ceiling is the
    sanitizer's ``limit=1000`` plus the length of its truncation marker.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            oversized = "workspace clone failed while copying repository object " * 40
            assert len(oversized) > 1000

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError(oversized)

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            message = failed["error"]["message"]
            ceiling = 1000 + len(TRUNCATION_MARKER)
            assert len(message) == ceiling
            assert len(message) <= ceiling
            assert message.endswith(TRUNCATION_MARKER)
        finally:
            await service.close()

    asyncio.run(exercise())


def test_workspace_error_empty_after_sanitization_falls_back_to_fixed_message(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """A WorkspaceError whose text sanitizes to nothing (an empty message)
    falls back to the fixed string -- the client must never see an empty
    ``request_failed`` reason.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            def fail_workspace(*args, **kwargs):
                raise WorkspaceError("")

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_workspace,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert failed["error"]["message"] == "workspace preparation failed"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_generic_runtime_error_still_opaque_and_unwidened(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """A plain RuntimeError -- NOT a WorkspaceError, RuntimeProofError, or
    ValueError -- must still land on the generic ``internal_error`` handler
    with its reason withheld, exactly as before this change.  Pins that the
    new WorkspaceError branch did not widen generic exception disclosure.
    """

    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")

            def fail_generic(*args, **kwargs):
                raise RuntimeError("sensitive internal reason")

            monkeypatch.setattr(
                "control_plane.executive_service.prepare_credentialless_clone",
                fail_generic,
            )

            failed = await _request(service, "create-proof-job")
            assert failed["ok"] is False
            assert failed["error"]["code"] == "internal_error"
            assert failed["error"]["message"] == "RuntimeError: Executive request failed"
            assert "sensitive internal reason" not in failed["error"]["message"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_cancel_clean_shutdown_and_manual_reconcile_never_auto_requeue(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        gate = asyncio.Event()
        service, holder = _service(
            tmp_path, socket_root=short_socket_root, finish_gate=gate
        )
        await service.start()
        await _request(service, "register-worker")
        created = await _request(service, "create-proof-job")
        job_id = created["result"]["job_id"]
        dispatched = await _request(service, "dispatch", {"job_id": job_id})
        assert dispatched["ok"] is True

        sibling = await _request(service, "create-proof-job")
        assert sibling["ok"] is False
        assert "sibling proof workspace" in sibling["error"]["message"]

        reconcile_while_live = await _request(service, "reconcile")
        assert reconcile_while_live["ok"] is False
        assert "active dispatch" in reconcile_while_live["error"]["message"]

        cancelled = await _request(service, "cancel", {"job_id": job_id})
        assert cancelled["result"]["status"] == "CANCEL_REQUESTED"
        gate.set()
        for _ in range(100):
            job = service.runtime.jobs.get_job(job_id)  # type: ignore[union-attr]
            if job is not None and job.status is JobStatus.CANCELLED:
                break
            await asyncio.sleep(0.01)
        assert job is not None and job.status is JobStatus.CANCELLED

        reconciled = await _request(service, "reconcile")
        assert reconciled["ok"] is True
        assert holder["supervisor"].requeue_values == [False, False]
        await service.close()
        assert not service.socket_path.exists()

    asyncio.run(exercise())


def test_backup_commands_are_confined_to_configured_root(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        backend = _FakeBackup()
        service, _holder = _service(
            tmp_path, socket_root=short_socket_root, backup=backend
        )
        await service.start()
        try:
            created = await _request(service, "backup")
            assert created["ok"] is True
            assert Path(created["result"]["database_path"]).parent == service.config.backup_root
            assert stat.S_IMODE(backend.created[0].stat().st_mode) == 0o600

            verified = await _request(service, "verify-backup", {"name": "fixture.sqlite3"})
            assert verified["result"]["ok"] is True
            assert backend.verified[0][0] == service.config.backup_root / "fixture.sqlite3"
            assert backend.verified[0][1] == service.config.backup_root / "fixture.manifest.json"

            (service.config.backup_root / "fixture.manifest.json").unlink()
            unrestorable = await _request(
                service, "verify-backup", {"name": "fixture.sqlite3"}
            )
            assert unrestorable["ok"] is False
            assert "no canonical manifest" in unrestorable["error"]["message"]

            escaped = await _request(
                service, "verify-backup", {"name": "../executive.sqlite3"}
            )
            assert escaped["ok"] is False
            assert "simple .sqlite3 file name" in escaped["error"]["message"]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_peer_uid_is_checked_when_kernel_credentials_are_available(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid",
                lambda _connection: os.geteuid() + 1,
            )
            denied = await _request(service, "status")
            assert denied["ok"] is False
            assert denied["error"]["code"] == "peer_denied"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_missing_kernel_peer_credentials_fail_closed(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            monkeypatch.setattr(
                "control_plane.executive_service._peer_uid", lambda _connection: None
            )
            denied = await _request(service, "status")
            assert denied["ok"] is False
            assert denied["error"]["code"] == "peer_credentials_unavailable"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_launchd_activated_unix_socket_is_reused_and_not_unlinked(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        socket_path = short_socket_root / "activated.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(16)
        socket_path.chmod(0o660)
        config = _config(tmp_path, socket_root=short_socket_root)
        config = ServiceConfig(
            **{
                **config.__dict__,
                "socket_path": socket_path,
            }
        )
        holder = {}

        def factory(runtime):
            holder["supervisor"] = _FakeSupervisor(runtime)
            return holder["supervisor"]

        wrong_path = short_socket_root / "wrong-activated.sock"
        wrong_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        wrong_listener.bind(str(wrong_path))
        wrong_listener.listen(1)
        with pytest.raises(ValueError, match="does not match"):
            ExecutiveControlService(
                config,
                supervisor_factory=factory,
                activated_socket=wrong_listener,
            )
        wrong_listener.close()

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            activated_socket=listener,
        )
        await service.start()
        assert (await _request(service, "status"))["ok"] is True
        await service.close()
        # launchd, not the daemon, owns removal of an activated socket node.
        assert socket_path.exists() and stat.S_ISSOCK(socket_path.stat().st_mode)

    asyncio.run(exercise())


def test_production_config_composes_remote_broker_and_launchd_socket(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        socket_path = short_socket_root / "production.sock"
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(16)
        socket_path.chmod(0o660)
        canary = tmp_path / "canary.json"
        canary.write_text(
            json.dumps(
                {
                    "schema_version": "mastermind.executive_secret_canary/v1",
                    "passed": True,
                    "checks": {
                        "control_service_environment": "DENIED",
                        "administrative_checkout": "DENIED",
                        "executive_database": "DENIED",
                        "other_worker_home": "DENIED",
                        "forbidden_production_path": "DENIED",
                    },
                    "receipt_sha256": "a" * 64,
                    "control_environment_probe_sha256": "c" * 64,
                    "observed_at": "2026-08-11T00:00:00+00:00",
                    "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
                }
            ),
            encoding="utf-8",
        )
        canary.chmod(0o400)
        proof_source, proof_base_sha = _source_repository(tmp_path)
        raw = {
            "schema_version": service_cli.CONTROL_CONFIG_SCHEMA_VERSION,
            "runtime_root": str(tmp_path / "runtime"),
            "control_socket_path": str(socket_path),
            "launchd_socket_name": "Operator",
            "worker_broker_socket_path": str(short_socket_root / "worker.sock"),
            "worker_provider_home": str(tmp_path / "provider-home"),
            "worker_runs_root": str(tmp_path / "runs"),
            "receipts_root": str(tmp_path / "receipts"),
            "proof_source_repository": str(proof_source),
            "proof_workspace_root": str(tmp_path / "workspaces"),
            "proof_base_sha": proof_base_sha,
            "backup_root": str(tmp_path / "backups"),
            "control_uid": os.geteuid(),
            "worker_uid": os.geteuid() + 1,
            "worker_gid": os.getegid() + 1,
            "worker_user": "_mastermind_worker",
            "shared_run_gid": os.getegid() + 1,
            "allowed_peer_uids": [os.geteuid()],
            "secret_canary_receipt_path": str(canary),
            "control_environment_attestation_path": str(
                tmp_path / "control-environment-attestation.json"
            ),
        }
        unarmed_path = tmp_path / "control-unarmed.json"
        unarmed_path.write_text(json.dumps(raw), encoding="utf-8")
        unarmed_path.chmod(0o400)
        unarmed = service_cli.load_control_config(unarmed_path)
        assert not (
            {
                "terminal_return_armed",
                "terminal_return_socket_path",
            }
            & set(unarmed)
        )
        observation_keys = {
            "dialogue_observation_socket_path",
            "dialogue_observation_launchd_socket_name",
            "dialogue_observation_peer_uid",
            "dialogue_bridge_armed",
            "dialogue_wake_retry_policy",
        }
        unarmed_wake_policy = {
            "max_delivery_attempts": None,
            "retry_cooldown_s": None,
            "accepted_ttl_s": None,
            "target_unavailable_backoff_s": None,
            "reenable_on_binding_rotation": True,
            "armed": False,
        }
        observation_fields = {
            "dialogue_observation_socket_path": (
                "/var/run/mastermind-dialogue-observation/"
                "dialogue-observation.sock"
            ),
            "dialogue_observation_launchd_socket_name": "DialogueObservation",
            "dialogue_observation_peer_uid": 457,
            "dialogue_bridge_armed": False,
            "dialogue_wake_retry_policy": unarmed_wake_policy,
        }
        assert not (observation_keys & set(unarmed))
        for missing in observation_keys:
            partial_path = tmp_path / f"control-observation-missing-{missing}.json"
            partial = {
                **raw,
                **observation_fields,
            }
            partial.pop(missing)
            partial_path.write_text(json.dumps(partial), encoding="utf-8")
            partial_path.chmod(0o400)
            with pytest.raises(ServiceError, match="must be supplied together"):
                service_cli.load_control_config(partial_path)

        observation_path = tmp_path / "control-observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    **raw,
                    **observation_fields,
                }
            ),
            encoding="utf-8",
        )
        observation_path.chmod(0o400)
        observation_loaded = service_cli.load_control_config(observation_path)
        assert observation_loaded["dialogue_observation_socket_path"] == Path(
            "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
        ).resolve(strict=False)
        assert observation_loaded["dialogue_observation_peer_uid"] == 457
        assert observation_loaded["dialogue_bridge_armed"] is False

        armed_observation_path = tmp_path / "control-observation-armed.json"
        armed_observation_path.write_text(
            json.dumps(
                {
                    **raw,
                    **observation_fields,
                    "dialogue_bridge_armed": True,
                    "dialogue_wake_retry_policy": {
                        "max_delivery_attempts": 1,
                        "retry_cooldown_s": 15,
                        "accepted_ttl_s": 300,
                        "target_unavailable_backoff_s": 60,
                        "reenable_on_binding_rotation": True,
                        "armed": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        armed_observation_path.chmod(0o400)
        armed_observation_loaded = service_cli.load_control_config(
            armed_observation_path
        )

        terminal_return_path = tmp_path / "control-terminal-return.json"
        terminal_return_path.write_text(
            json.dumps(
                {
                    **raw,
                    "terminal_return_armed": True,
                    "terminal_return_socket_path": (
                        "/var/run/mastermind-agent-relay/agent-relay.sock"
                    ),
                }
            ),
            encoding="utf-8",
        )
        terminal_return_path.chmod(0o400)
        terminal_loaded = service_cli.load_control_config(terminal_return_path)
        assert terminal_loaded["terminal_return_armed"] is True
        assert terminal_loaded["terminal_return_socket_path"] == Path(
            "/var/run/mastermind-agent-relay/agent-relay.sock"
        ).resolve(strict=False)
        terminal_unarmed_path = tmp_path / "control-terminal-return-unarmed.json"
        terminal_unarmed_path.write_text(
            json.dumps(
                {
                    **raw,
                    "terminal_return_armed": False,
                    "terminal_return_socket_path": (
                        "/var/run/mastermind-agent-relay/agent-relay.sock"
                    ),
                }
            ),
            encoding="utf-8",
        )
        terminal_unarmed_path.chmod(0o400)
        terminal_unarmed_loaded = service_cli.load_control_config(
            terminal_unarmed_path
        )

        stale_policy_path = tmp_path / "control-stale-policy.json"
        stale_policy_path.write_text(
            json.dumps(
                {
                    **raw,
                    "terminal_return_allowed_sol_user_ids": ["U0BRETDUAS2"],
                    "terminal_return_relay_bot_user_id": "U0RELAY001",
                }
            ),
            encoding="utf-8",
        )
        stale_policy_path.chmod(0o400)
        with pytest.raises(ServiceError, match="unknown=.*terminal_return_allowed"):
            service_cli.load_control_config(stale_policy_path)

        config_path = tmp_path / "control.json"
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        config_path.chmod(0o400)
        loaded = service_cli.load_control_config(config_path)
        monkeypatch.setattr(
            service_cli, "activate_launchd_socket", lambda _name: listener
        )
        captured: dict[str, object] = {}

        def capture_service(config, **kwargs):
            captured["config"] = config
            captured["kwargs"] = kwargs
            return object()

        with monkeypatch.context() as composition_patch:
            composition_patch.setattr(
                service_cli, "activate_launchd_socket", lambda _name: listener
            )
            composition_patch.setattr(
                service_cli, "ExecutiveControlService", capture_service
            )
            service_cli._service_from_config(
                terminal_loaded,
                initial_canary=json.loads(canary.read_text(encoding="utf-8")),
            )
        composed_config = captured["config"]
        composed_kwargs = captured["kwargs"]
        assert isinstance(composed_config, ServiceConfig)
        assert composed_config.terminal_return_armed is True
        assert isinstance(composed_kwargs, dict)
        projector_factory = composed_kwargs["terminal_return_projector_factory"]
        projector = projector_factory(
            lambda: object(), composed_config.terminal_return_socket_path
        )
        assert isinstance(projector, ExecutiveTerminalReturnProjector)

        captured.clear()
        activated_names: list[str] = []
        with monkeypatch.context() as composition_patch:
            composition_patch.setattr(
                service_cli,
                "activate_launchd_socket",
                lambda name: (activated_names.append(name), listener)[1],
            )
            composition_patch.setattr(
                service_cli, "ExecutiveControlService", capture_service
            )
            service_cli._service_from_config(
                observation_loaded,
                initial_canary=json.loads(canary.read_text(encoding="utf-8")),
            )
        observation_kwargs = captured["kwargs"]
        assert activated_names == ["Operator"]
        assert "dialogue_observation_socket_path" not in observation_kwargs
        assert "dialogue_wake_handler" not in observation_kwargs

        captured.clear()
        activated_names.clear()
        with monkeypatch.context() as composition_patch:
            composition_patch.setattr(
                service_cli,
                "activate_launchd_socket",
                lambda name: (activated_names.append(name), listener)[1],
            )
            composition_patch.setattr(
                service_cli, "ExecutiveControlService", capture_service
            )
            service_cli._service_from_config(
                armed_observation_loaded,
                initial_canary=json.loads(canary.read_text(encoding="utf-8")),
            )
        observation_kwargs = captured["kwargs"]
        assert activated_names == ["Operator", "DialogueObservation"]
        assert observation_kwargs["dialogue_observation_peer_uid"] == 457
        assert observation_kwargs["dialogue_observation_group_gid"] == 457
        assert observation_kwargs["dialogue_observation_socket_path"] == Path(
            "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
        ).resolve(strict=False)
        assert isinstance(
            observation_kwargs["dialogue_wake_handler"],
            ExecutiveDialogueWakeBridge,
        )

        captured.clear()
        with monkeypatch.context() as composition_patch:
            composition_patch.setattr(
                service_cli, "activate_launchd_socket", lambda _name: listener
            )
            composition_patch.setattr(
                service_cli, "ExecutiveControlService", capture_service
            )
            service_cli._service_from_config(
                terminal_unarmed_loaded,
                initial_canary=json.loads(canary.read_text(encoding="utf-8")),
            )
        unarmed_composed_config = captured["config"]
        unarmed_composed_kwargs = captured["kwargs"]
        assert isinstance(unarmed_composed_config, ServiceConfig)
        assert unarmed_composed_config.terminal_return_armed is False
        assert unarmed_composed_config.terminal_return_socket_path == Path(
            "/var/run/mastermind-agent-relay/agent-relay.sock"
        ).resolve(strict=False)
        assert isinstance(unarmed_composed_kwargs, dict)
        assert "terminal_return_projector_factory" not in unarmed_composed_kwargs

        with pytest.raises(ValueError, match="coo_tick_interval_seconds"):
            service_cli._service_from_config(
                {**loaded, "coo_tick_interval_seconds": 0}
            )
        service = service_cli._service_from_config(
            loaded,
            initial_canary=json.loads(canary.read_text(encoding="utf-8")),
        )
        assert service.config.terminal_return_armed is False
        assert service.config.terminal_return_socket_path is None
        await service.start()
        try:
            from control_plane.executive_worker_broker import (
                RemoteCodexWorkerAdapter,
                RemoteWorkerProcessController,
            )

            assert isinstance(service.supervisor.adapter, RemoteCodexWorkerAdapter)
            assert isinstance(
                service.supervisor.process_controller, RemoteWorkerProcessController
            )
            assert service.supervisor.require_complete_launch_attestation is True
            assert service.supervisor.isolation_roots == (
                Path(raw["proof_workspace_root"]).resolve(),
                Path(raw["worker_runs_root"]).resolve(),
            )
            status = await _request(service, "status")
            assert status["ok"] is True
            assert status["result"]["service_state"] == "READY"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_canary_envelope_binds_live_control_probe_and_inner_receipt(tmp_path: Path):
    host_root = tmp_path / "host"
    runtime_root = host_root / "control" / "db"
    proof_source = host_root / "control" / "admin-checkout" / ("a" * 40)
    codex_home = host_root / "workers" / "codex-01" / "provider-home"
    raw = {
        "runtime_root": runtime_root,
        "proof_source_repository": proof_source,
        "worker_provider_home": codex_home,
        "control_uid": os.geteuid(),
        "worker_uid": os.geteuid() + 1000,
        "worker_gid": os.getegid() + 1000,
    }
    control_identity = {
        "pid": 4242,
        "pgid": 4242,
        "session_id": 4242,
        "start_identity": "fixture-start",
        "boot_id": "fixture-boot",
        "effective_uid": os.geteuid(),
        "effective_gid": os.getegid(),
        "real_uid": os.getuid(),
        "real_gid": os.getgid(),
    }
    control_attestation = {
        "process_identity": control_identity,
        "config_sha256": "1" * 64,
        "release_manifest_sha256": "2" * 64,
        "sentinel_value_sha256": "3" * 64,
    }
    worker_principal = {
        "real_uid": raw["worker_uid"],
        "effective_uid": raw["worker_uid"],
        "real_gid": raw["worker_gid"],
        "effective_gid": raw["worker_gid"],
    }
    probe = {
        "schema_version": service_cli.CONTROL_ENVIRONMENT_PROBE_SCHEMA_VERSION,
        "passed": True,
        "control_process_identity": control_identity,
        "worker_principal": worker_principal,
        "config_sha256": control_attestation["config_sha256"],
        "release_manifest_sha256": control_attestation[
            "release_manifest_sha256"
        ],
        "sentinel_value_sha256": control_attestation["sentinel_value_sha256"],
        "process_identity_sha256": service_cli._canonical_sha256(control_identity),
        "checks": {
            "launchctl": "ABSENT",
            "ps": "DENIED",
            "kern_procargs2": "DENIED",
        },
    }
    probe_sha256 = service_cli._canonical_sha256(probe)
    canary_config = SecretCanaryConfig(
        expected_worker_uid=raw["worker_uid"],
        expected_worker_gid=raw["worker_gid"],
        control_uid=raw["control_uid"],
        control_gid=os.getegid(),
        control_environment_sentinel="EXECUTIVE_CONTROL_CANARY_VALUE",
        control_environment_probe_sha256=probe_sha256,
        administrative_checkout_sentinel=(
            proof_source / ".git" / "executive-secret-canary"
        ),
        executive_database=(
            runtime_root / "data" / "control_plane" / "executive.sqlite3"
        ),
        other_worker_home_sentinel=(
            host_root / "canary-fixtures" / "other-worker-home" / "sentinel"
        ),
        forbidden_production_sentinel=(
            host_root / "canary-fixtures" / "production-like" / "sentinel"
        ),
        codex_home=codex_home,
    )

    def opener(path: Path, _flags: int) -> int:
        if path == codex_home / "auth.json":
            return 19
        raise PermissionError(errno.EACCES, "denied")

    inner = run_secret_canary(
        canary_config,
        opener=opener,
        closer=lambda _descriptor: None,
        environment={},
        principal=PrincipalIdentity(**worker_principal),
    )
    envelope = {
        "schema_version": service_cli.SECRET_CANARY_ENVELOPE_SCHEMA_VERSION,
        "secret_canary": inner,
        "control_environment_probe": probe,
        "control_environment_probe_sha256": probe_sha256,
    }
    path = tmp_path / "secret-canary.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    path.chmod(0o400)

    assert service_cli._load_canary_envelope(
        path,
        raw=raw,
        control_attestation=control_attestation,
    ) == inner

    class _BootClient:
        async def request(self, operation, payload):
            assert operation == "autonomy-canary"
            assert payload == {"control_environment_attestation": control_attestation}
            return {"envelope": envelope}

    assert asyncio.run(
        service_cli._request_boot_autonomy_canary(
            raw,
            control_attestation,
            client=_BootClient(),
        )
    ) == inner
    tmp_path.chmod(0o700)
    persisted = tmp_path / "boot-secret-canary.json"
    persisted.write_text('{"stale":true}\n', encoding="utf-8")
    persisted.chmod(0o400)
    assert asyncio.run(
        service_cli._request_boot_autonomy_canary(
            raw,
            control_attestation,
            client=_BootClient(),
            persist_path=persisted,
        )
    ) == inner
    assert stat.S_IMODE(persisted.stat().st_mode) == 0o400
    assert json.loads(persisted.read_text(encoding="utf-8")) == envelope

    stale = dict(control_attestation)
    stale["process_identity"] = {**control_identity, "pid": 9999}
    with pytest.raises(service_cli.ServiceError, match="identity is stale"):
        service_cli._load_canary_envelope(
            path,
            raw=raw,
            control_attestation=stale,
        )


def test_awaiting_canary_quarantine_allows_only_readiness_and_activation(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        config = _config(tmp_path, socket_root=short_socket_root)
        holder = {}
        verdict = {
            "schema_version": "mastermind.executive_secret_canary/v1",
            "passed": True,
            "checks": {
                "control_service_environment": "DENIED",
                "administrative_checkout": "DENIED",
                "executive_database": "DENIED",
                "other_worker_home": "DENIED",
                "forbidden_production_path": "DENIED",
            },
            "receipt_sha256": "b" * 64,
            "control_environment_probe_sha256": "c" * 64,
            "observed_at": "2026-08-11T00:00:00Z",
            "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
        }
        loader_calls = []

        def load_canary():
            loader_calls.append(True)
            return verdict

        def factory(runtime):
            holder["supervisor"] = _FakeSupervisor(runtime)
            holder["supervisor"].secret_canary_verdict = {}
            holder["supervisor"].require_complete_launch_attestation = False
            return holder["supervisor"]

        service = ExecutiveControlService(
            config,
            supervisor_factory=factory,
            service_state="AWAITING_CANARY",
            canary_loader=load_canary,
        )
        await service.start()
        try:
            status = await _request(service, "status")
            assert status["result"]["service_state"] == "AWAITING_CANARY"
            assert (await _request(service, "health"))["result"]["ok"] is True
            denied = await _request(service, "register-worker")
            assert denied["ok"] is False
            assert "AWAITING_CANARY" in denied["error"]["message"]
            assert holder["supervisor"].requeue_values == []
            rejected = await _request(
                service, "activate-canary", {"receipt_path": "/unreviewed"}
            )
            assert rejected["ok"] is False
            assert loader_calls == []
            activated = await _request(service, "activate-canary")
            assert activated["result"] == {"service_state": "READY"}
            ready = await _request(service, "status")
            assert ready["result"]["service_state"] == "READY"
            assert loader_calls == [True]
            assert holder["supervisor"].secret_canary_verdict == verdict
            assert holder["supervisor"].require_complete_launch_attestation is True
            assert holder["supervisor"].requeue_values == [False]
            repeated = await _request(service, "activate-canary")
            assert repeated["ok"] is False
            assert loader_calls == [True]
        finally:
            await service.close()

    asyncio.run(exercise())


def test_canary_activation_fails_closed_without_loader(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, _holder = _service(
            tmp_path,
            socket_root=short_socket_root,
        )
        service._service_state = "AWAITING_CANARY"
        await service.start()
        try:
            response = await _request(service, "activate-canary")
            assert response["ok"] is False
            assert "no canary loader" in response["error"]["message"]
            status = await _request(service, "status")
            assert status["result"]["service_state"] == "AWAITING_CANARY"
        finally:
            await service.close()

    asyncio.run(exercise())


def test_service_config_rejects_relative_paths_and_unbounded_inputs(tmp_path: Path):
    absolute = _config(tmp_path)
    assert absolute.socket_path.is_absolute()
    with pytest.raises(ValueError, match="socket_path must be absolute"):
        ServiceConfig(
            runtime_root=tmp_path,
            socket_path=Path("relative.sock"),
            proof_source_repository=absolute.proof_source_repository,
            proof_workspace_root=tmp_path / "workspaces",
            proof_base_sha=absolute.proof_base_sha,
        )
    with pytest.raises(ValueError, match="proof_base_sha"):
        _config(tmp_path / "bad-sha", proof_base_sha="main")
    with pytest.raises(ValueError, match="codex/"):
        _config(tmp_path / "bad-branch", proof_branch="main")


def test_cli_exposes_configured_serve_and_offline_restore_only():
    serve = service_cli._parser().parse_args(
        ["serve", "--config", "/etc/mastermind-executive/control.json"]
    )
    assert serve.command == "serve" and serve.config.is_absolute()
    restore = service_cli._parser().parse_args(
        [
            "restore-backup",
            "--config",
            "/etc/mastermind-executive/control.json",
            "executive-proof.sqlite3",
        ]
    )
    assert restore.command == "restore-backup"
    cycle = service_cli._parser().parse_args(["run-coo-cycle", "JOB-001"])
    assert cycle.command == "run-coo-cycle" and cycle.root_job_id == "JOB-001"
    # The live JSON protocol deliberately has no restore verb.
    assert "restore" not in {
        "status",
        "health",
        "workers",
        "jobs",
        "job",
        "attempt",
        "register-worker",
        "create-proof-job",
        "dispatch",
        "run-coo-cycle",
        "cancel",
        "reconcile",
        "requeue",
        "backup",
        "verify-backup",
    }


def test_service_surface_has_no_financial_app_or_scheduler_integration():
    root = Path(__file__).resolve().parents[1]
    executive_sources = [
        root / "control_plane" / "executive_service.py",
        root / "control_plane" / "executive_worker_broker.py",
        root / "scripts" / "executive_os_phase1c.py",
        root / "scripts" / "executive_os_phase1c_worker.py",
    ]
    forbidden_roots = {
        "app",
        "apscheduler",
        "bot",
        "brain",
        "bridge",
        "loop",
        "portfolio",
    }
    for source in executive_sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert imported.isdisjoint(forbidden_roots), (source, imported & forbidden_roots)

    service_names = {
        path.relative_to(root).as_posix()
        for path in executive_sources
    }
    for package in ("app", "bot", "brain", "bridge", "loop", "portfolio"):
        package_root = root / package
        for source in package_root.rglob("*.py"):
            content = source.read_text(encoding="utf-8", errors="replace")
            assert "control_plane.executive_service" not in content, (
                source.relative_to(root).as_posix(),
                service_names,
            )


def _mark_proof_lost(runtime: Runtime, proof_id: str, proof_workspace: Path):
    lease = runtime.broker.claim(proof_id, lease_owner="lost-fixture")
    assert lease is not None
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="missing-provider-session",
    )
    runtime.attempts.mark_running(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    runtime.attempts.mark_lost(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="verified fixture absence",
        verified_process_absent=True,
    )
    proof_workspace.chmod(0o700)
    return lease


def test_service_git_observer_uses_optional_locks_and_refuses_mutation(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, _holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            await _request(service, "register-worker")
            created = await _request(service, "create-proof-job")
            workspace = Path(created["result"]["worktree"])
            recorded_env: list[dict[str, str]] = []
            recorded_argv: list[tuple[str, ...]] = []
            real_run = es_mod.subprocess.run

            def observed_run(*args, **kwargs):
                argv = args[0] if args else kwargs.get("args")
                env = kwargs.get("env") or {}
                recorded_argv.append(tuple(argv))
                recorded_env.append(dict(env))
                return real_run(*args, **kwargs)

            monkeypatch.setattr(es_mod.subprocess, "run", observed_run)
            service._observe_git(workspace, ["rev-parse", "--verify", "HEAD^{commit}"])
            service._observe_git(workspace, list(LAUNCH_CLEAN_STATUS_ARGS))
            service._observe_git(workspace, list(LAUNCH_CLEAN_UNTRACKED_ARGS))
            assert recorded_argv == [
                ("git", "-C", str(workspace), "rev-parse", "--verify", "HEAD^{commit}"),
                ("git", "-C", str(workspace), *LAUNCH_CLEAN_STATUS_ARGS),
                ("git", "-C", str(workspace), *LAUNCH_CLEAN_UNTRACKED_ARGS),
            ]
            assert recorded_env
            assert all(item.get("GIT_OPTIONAL_LOCKS") == "0" for item in recorded_env)

            spawned: list[object] = []

            def refuse_spawn(*args, **kwargs):
                spawned.append(args[0] if args else kwargs.get("args"))
                raise AssertionError("mutating Git must not spawn")

            monkeypatch.setattr(es_mod.subprocess, "run", refuse_spawn)
            for forbidden in (
                ["checkout", "HEAD"],
                ["switch", "main"],
                ["update-index", "--refresh"],
                ["add", "."],
                ["config", "safe.directory", "*"],
                ["remote", "add", "origin", "https://example.invalid/repo.git"],
                ["reset", "--hard"],
            ):
                with pytest.raises(ServiceError, match="refuses mutating"):
                    service._observe_git(workspace, forbidden)
            assert spawned == []
        finally:
            await service.close()

    asyncio.run(exercise())


def test_requeue_refuses_simulated_0600_index_after_service_observation(
    tmp_path: Path, short_socket_root: Path, monkeypatch: pytest.MonkeyPatch
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            proof_workspace = Path(proof["result"]["worktree"])
            _mark_proof_lost(runtime, proof_id, proof_workspace)
            real_observe = service._observe_git

            def corrupt_after_status(workspace: Path, arguments: list[str]) -> bytes:
                result = real_observe(workspace, arguments)
                if tuple(arguments) == LAUNCH_CLEAN_STATUS_ARGS:
                    (workspace / ".git" / "index").chmod(0o600)
                return result

            monkeypatch.setattr(service, "_observe_git", corrupt_after_status)
            failed = await _request(service, "requeue", {"job_id": proof_id})
            assert failed["ok"] is False
            assert failed["error"]["code"] == "request_failed"
            assert ".git/index" in failed["error"]["message"]
            job = runtime.jobs.get_job(proof_id)
            assert job is not None
            assert job.status is JobStatus.LOST
            assert holder["supervisor"].started_jobs == []
            rotation_root = service.config.proof_workspace_root / ".lost-attempts" / proof_id
            assert not any(rotation_root.glob("*.rotation.json"))
            assert runtime.attempts.list_attempts(job_id=proof_id)
            current = runtime.jobs.get_job(proof_id)
            assert current is not None and current.current_attempt_id is not None
        finally:
            await service.close()

    asyncio.run(exercise())


def test_dispatch_refuses_queued_workspace_with_0600_index(
    tmp_path: Path, short_socket_root: Path
):
    async def exercise():
        service, holder = _service(tmp_path, socket_root=short_socket_root)
        await service.start()
        try:
            runtime = service.runtime
            assert runtime is not None
            await _request(service, "register-worker")
            proof = await _request(service, "create-proof-job")
            proof_id = proof["result"]["job_id"]
            workspace = Path(proof["result"]["worktree"])
            (workspace / ".git" / "index").chmod(0o600)
            denied = await _request(service, "dispatch", {"job_id": proof_id})
            assert denied["ok"] is False
            assert denied["error"]["code"] == "request_failed"
            assert ".git/index" in denied["error"]["message"]
            job = runtime.jobs.get_job(proof_id)
            assert job is not None
            assert job.status is JobStatus.QUEUED
            assert job.current_attempt_id is None
            assert holder["supervisor"].started_jobs == []
            assert stat.S_IMODE((workspace / ".git" / "index").stat().st_mode) == 0o600
        finally:
            await service.close()

    asyncio.run(exercise())


def test_ambient_process_and_invalid_provider_result_fail_job_keep_service_ready(
    tmp_path: Path, short_socket_root: Path
) -> None:
    """Dispatch + INVALID_RESULT + ambient PID must FAIL the Job, not quarantine."""

    class _InvalidResultSupervisor(_FakeSupervisor):
        def __init__(self, runtime: Runtime, *, evidence_root: Path) -> None:
            super().__init__(runtime)
            self.evidence_root = evidence_root

        async def finish_job(self, active: _Active):
            lease = active.lease
            attempt = lease.attempt
            result_path = self.evidence_root / "result.json"
            result_path.write_text("{}\n", encoding="utf-8")
            self.runtime.attempts.record_process_exit(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
                exit_code=1,
                result_path=str(result_path),
            )
            receipt_dir = self.evidence_root / attempt.attempt_id
            receipt_dir.mkdir(parents=True, exist_ok=True)
            uid_sweep = {
                "schema_version": "mastermind.executive_uid_sweep/v2",
                "observed_at": "2026-08-11T00:00:01+00:00",
                "reason": "run_terminal",
                "worker_uid": 451,
                "broker_pid": 42419,
                "residual_pids_before": [],
                "residual_pids_after": [],
                "signal_name": "SIGKILL",
                "signal_sent": False,
                "quiescent_observations": 2,
                "ambient_pids": [88688],
                "ambient_identities": [
                    AmbientProcessIdentity(
                        pid=88688,
                        uid=451,
                        launchd_domain="user/451",
                        launchd_label=AMBIENT_LAUNCHD_LABEL,
                        launchd_reported_pid=88688,
                        plist_path=AMBIENT_PLIST_PATH,
                        program_path=AMBIENT_PROGRAM_PATH,
                        executable_path=AMBIENT_PROGRAM_PATH,
                        executable_device=1,
                        executable_inode=1,
                        codesign_identifier=AMBIENT_CODESIGN_IDENTIFIER,
                        codesign_verified=True,
                    ).to_dict()
                ],
                "ambient_attribution": "attested",
                "passed": True,
                "found_residuals": False,
            }
            (receipt_dir / "collection-receipt.json").write_text(
                json.dumps(
                    {
                        "schema_version": "mastermind.executive_collection_evidence/v1",
                        "collection": {
                            "result": {"status": "INVALID_RESULT", "exit_code": 1}
                        },
                        "uid_sweep": uid_sweep,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (receipt_dir / "assignment-seal-receipt.json").write_text(
                json.dumps({"passed": True, "uid_sweep": uid_sweep}) + "\n",
                encoding="utf-8",
            )
            return self.runtime.attempts.fail_attempt(
                attempt.attempt_id,
                fence_generation=attempt.fence_generation,
                lease_token=lease.lease_token,
                payload=JobPayload(
                    summary="Codex worker did not return an accepted result",
                    errors=["INVALID_RESULT"],
                ),
            )

    async def exercise():
        evidence_root = tmp_path / "evidence"
        evidence_root.mkdir()
        holder = {}

        def factory(runtime: Runtime):
            supervisor = _InvalidResultSupervisor(runtime, evidence_root=evidence_root)
            holder["supervisor"] = supervisor
            return supervisor

        service = ExecutiveControlService(
            _config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=factory,
        )
        await service.start()
        try:
            registered = await _request(service, "register-worker")
            assert registered["ok"] is True
            created = await _request(service, "create-proof-job")
            job_id = created["result"]["job_id"]
            dispatched = await _request(service, "dispatch", {"job_id": job_id})
            assert dispatched["ok"] is True
            attempt_id = dispatched["result"]["attempt"]["attempt_id"]
            inspected = None
            for _ in range(100):
                inspected = await _request(service, "job", {"job_id": job_id})
                if inspected["result"]["status"] == "FAILED":
                    break
                await asyncio.sleep(0.01)
            assert inspected is not None
            assert inspected["result"]["status"] == "FAILED"
            attempt = await _request(service, "attempt", {"attempt_id": attempt_id})
            assert attempt["result"]["status"] == "FAILED"
            assert attempt["result"]["exit_code"] == 1
            status = await _request(service, "status")
            assert status["result"]["service_state"] == "READY"
            assert status["result"]["dispatch_errors"] == {}
            collection = evidence_root / attempt_id / "collection-receipt.json"
            seal = evidence_root / attempt_id / "assignment-seal-receipt.json"
            assert collection.is_file()
            assert seal.is_file()
            payload = json.loads(collection.read_text(encoding="utf-8"))
            assert payload["uid_sweep"]["ambient_pids"] == [88688]
            assert payload["collection"]["result"]["status"] == "INVALID_RESULT"
        finally:
            await service.close()

    asyncio.run(exercise())
