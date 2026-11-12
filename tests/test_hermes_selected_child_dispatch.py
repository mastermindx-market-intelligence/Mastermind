"""Compose the Hermes selected-child tool with the incumbent Executive owner.

Only physical provider execution is inert. The Job/Attempt claim, the plan
admission, the typed role seal, the terminal-return reduction and the frozen
selection re-proof all use the real Runtime and the real service owner.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from control_plane.executive_runtime import (
    AttemptStatus,
    JobRegistry,
    JobStatus,
    PersistenceError,
    Runtime,
    RuntimeStore,
    StateConflict,
    expected_child_selection,
)
from control_plane.executive_service import ExecutiveControlService
from control_plane.executive_terminal_return import TerminalReturnCandidate
from integrations.hermes_delegate.executive import (
    ExecutiveChildSelection,
    ExecutiveSelectedChild,
    ExecutiveSelectedChildComposition,
    clear_selected_child_composition,
    install_selected_child_composition,
    selected_child_composition,
)
from integrations.hermes_delegate.tool import dispatch
from tests.test_executive_coo_hierarchy_service import _complete, _plan_body
from tests.test_executive_coo_ready_frontier_service import _register_peer
from tests.test_executive_os_phase1fc import _complete_ohf_role
from tests.test_executive_service import (
    _capture_projection,
    _config,
    _coo_intent,
    _request,
    _FakeSupervisor,
)
from tests.selected_child_mission import SelectedChildMission, WORK_REF, continuation_source


async def _admit_work_child(service, root):
    """Admit one plan whose single step is a direct work child of the root."""

    runtime = service.runtime
    planner = runtime.jobs.create_cycle_planner(
        root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0"
    )
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id=service.config.worker_id,
    )
    _complete(runtime, dispatch, _plan_body(dispatch, root))
    children = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}",
    )
    await _qualify_planner_continuation(service, runtime.jobs.get_job(planner.job_id))
    return children[0]


async def _qualify_planner_continuation(service, planner):
    """Publish the real prior return and keep its separate receiver explicit."""
    from control_plane.coo_principal_mandate import _mission_state
    from tests.test_joint_api_project_owner import publish_planner_return_async
    runtime = service.runtime
    mission = service._selected_child_mission
    mission.publish()
    try:
        initial = _mission_state(mission.workspace.read_mission_for_work_ref(WORK_REF),
            expected_work_ref=WORK_REF)
    except ValueError as error:
        assert str(error) == "source_unavailable"
    else:
        assert initial.qualified is False
    before = {job.job_id for job in runtime.jobs.list_jobs()}
    await publish_planner_return_async(service, planner)
    receiver_jobs = [job for job in runtime.jobs.list_jobs() if job.job_id not in before]
    assert len(receiver_jobs) == 2
    assert len({job.root_job_id for job in receiver_jobs}) == 1
    assert receiver_jobs[0].root_job_id != mission.root.job_id
    mission.receiver_job_ids = frozenset(job.job_id for job in receiver_jobs)
    mission.publish()
    mission.require_current()


@pytest.fixture
def short_socket_root():
    value = Path(tempfile.mkdtemp(prefix="mmx-c17-", dir="/tmp"))
    try:
        yield value
    finally:
        import shutil

        shutil.rmtree(value, ignore_errors=True)


class _SealingSupervisor(_FakeSupervisor):
    """Seal the real role result; only the provider process is inert."""

    async def finish_job(self, active):
        if self.finish_gate is not None:
            await self.finish_gate.wait()
        dispatch_receipt = SimpleNamespace(
            attempt=active.lease.attempt, lease_token=active.lease.lease_token,
        )
        job = self.runtime.jobs.get_job(dispatch_receipt.attempt.job_id)
        body = {
            "schema_version": "mastermind.work_result/v1",
            "root_job_id": job.root_job_id,
            "plan_attempt_id": job.plan_attempt_id,
            "plan_digest": job.plan_digest,
            "plan_step_id": job.plan_step_id,
            "repair_round": job.repair_round,
            "artifacts": [], "evidence_digests": [],
        }
        return _complete_ohf_role(
            self.runtime, dispatch_receipt, body,
            identity_seed=51000 + int(job.job_id.split("-")[1]),
        )


class _AmbiguousSupervisor(_FakeSupervisor):
    """Fail after the durable claim, so the effect stays unknown."""

    async def start_cycle_job(self, job_id: str, *, command_id: str):
        await super().start_cycle_job(job_id, command_id=command_id)
        raise RuntimeError("provider start is ambiguous after the durable claim")


def _ambiguous_factory(runtime: Runtime, *, finish_gate: asyncio.Event):
    return _AmbiguousSupervisor(runtime, finish_gate=finish_gate)


@asynccontextmanager
async def _selected_child_service(tmp_path, short_socket_root, *, name,
                                   supervisor_factory=_SealingSupervisor):
    config = _config(
        tmp_path, socket_root=short_socket_root, coo_autonomy_armed=True,
        coo_tick_interval_seconds=3600.0,
    )
    config, source = continuation_source(config)
    received: list[TerminalReturnCandidate] = []
    holder: dict[str, Any] = {"finish_gate": asyncio.Event(), "planner_returns": []}

    def factory(runtime: Runtime):
        supervisor = supervisor_factory(runtime, finish_gate=holder["finish_gate"])
        holder["supervisor"] = supervisor
        return supervisor

    def project(candidate):
        job = service.runtime.jobs.get_job(candidate.job_id)
        target = holder["planner_returns"] if job.orchestration_role == "plan" else received
        return _capture_projection(target, candidate)

    service = ExecutiveControlService(
        config,
        supervisor_factory=factory,
        autonomy_guard=(lambda: None),
        terminal_return_projector=project,
        ceo_ingress_dialogue_source_provider=lambda _intent, _work: source,
    )
    await service.start()
    try:
        assert (await _request(service, "register-worker"))["ok"] is True
        _register_peer(service)
        intent = _coo_intent(config, name)
        intent["workstream"] = WORK_REF
        receipt = service._submit_service_intent(intent)
        root = service.runtime.jobs.get_job(receipt["job_id"])
        # Source/parser, current Mission and live claim share this exact owner.
        authority_dir = tmp_path / "selected-child-authority"
        authority_dir.mkdir()
        mission = SelectedChildMission(service, root, authority_dir)
        service._selected_child_mission = mission
        service._selected_child_fixture = (mission.provider, mission.config, None, mission.facts)
        yield service, holder["supervisor"], root, received, holder["finish_gate"]
    finally:
        await service.close()


def _selection(job) -> ExecutiveChildSelection:
    return ExecutiveChildSelection(
        root_job_id=job.root_job_id,
        parent_job_id=job.parent_job_id,
        job_id=job.job_id,
        plan_attempt_id=job.plan_attempt_id,
        plan_digest=job.plan_digest,
        plan_step_id=job.plan_step_id,
        repair_round=job.repair_round,
        expected_current_attempt_id=job.current_attempt_id,
    )


def _command(job, ordinal: int = 1) -> str:
    return (
        f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:{ordinal}"
    )


def _install(service, runtime, job, *, ordinal: int = 1,
             selection: ExecutiveChildSelection | None = None) -> str:
    command = _command(job, ordinal)
    install_selected_child_composition(ExecutiveSelectedChildComposition(
        service=service,
        runtime=runtime,
        children=(ExecutiveSelectedChild(
            selection=selection if selection is not None else _selection(job),
            attempt_ordinal=ordinal,
        ),),
        loop=asyncio.get_running_loop(),
        authority=service._selected_child_fixture[0],
        context=service._selected_child_fixture[3]["context"],
        capability_profile_digest=service._selected_child_fixture[3]["capability_profile_digest"],
        receiving_request_guard=lambda: None,
    ))
    return command


async def _call(arguments: dict[str, Any]) -> dict[str, Any]:
    """The model-facing handler runs off the loop that owns the service."""

    raw = await asyncio.to_thread(lambda: dispatch(arguments))
    return json.loads(raw)


async def _settle(service) -> None:
    tasks = tuple(service._dispatch_tasks.values())
    if tasks:
        await asyncio.gather(*tasks)


def _claim_events(runtime: Runtime, job_id: str) -> list[Any]:
    with runtime.store.read() as connection:
        return list(connection.execute(
            "SELECT * FROM events WHERE event_type='JOB_CLAIMED' AND job_id=?"
            " ORDER BY event_id",
            (job_id,),
        ).fetchall())


def test_selected_child_submit_claims_completes_and_returns(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child",
        ) as (service, _supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                submitted = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert submitted["state"] == "ACTIVE", submitted
                assert submitted["job_id"] == work.job_id
                assert submitted["command_id"] == command
                attempt_id = submitted["attempt_id"]
                assert isinstance(attempt_id, str) and attempt_id

                # The Runtime really owns the claim under the exact command.
                claims = _claim_events(runtime, work.job_id)
                assert len(claims) == 1
                assert claims[0]["command_id"] == command
                assert claims[0]["attempt_id"] == attempt_id
                claimed = runtime.attempts.get_attempt(attempt_id)
                assert claimed is not None
                assert claimed.status is AttemptStatus.CLAIMED
                assert runtime.jobs.get_job(work.job_id).attempt_count == 1

                gate.set()
                await _settle(service)

                completed = runtime.attempts.get_attempt(attempt_id)
                assert completed is not None
                assert completed.status is AttemptStatus.COMPLETED
                # The incumbent terminal-return owner delivered exactly once.
                assert [item.attempt_id for item in received] == [attempt_id]

                observed = await _call({
                    "action": "selected_child_status", "command": command,
                })
                assert observed["state"] == "COMPLETED", observed
                assert observed["attempt_id"] == attempt_id
                assert observed["result_status"] == "RESULT"
                assert len(observed["result_envelope_digest"]) == 64
                # A status read never delivers a second message.
                assert len(received) == 1
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_repeated_submit_observes_the_same_command_and_attempt(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-replay",
        ) as (service, _supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                first = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert first["state"] == "ACTIVE", first
                attempt_id = first["attempt_id"]

                # A repeated submit before completion observes that exact
                # command and Attempt; it never claims a second one.
                again = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert again["attempt_id"] == attempt_id, again
                assert again["state"] == "ACTIVE", again
                assert runtime.jobs.get_job(work.job_id).attempt_count == 1
                assert len(_claim_events(runtime, work.job_id)) == 1

                gate.set()
                await _settle(service)

                # A repeated submit after completion observes the same
                # Attempt; it never recomputes attempt_count + 1.
                after = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert after["attempt_id"] == attempt_id, after
                assert after["state"] == "COMPLETED", after
                assert runtime.jobs.get_job(work.job_id).attempt_count == 1
                assert len(_claim_events(runtime, work.job_id)) == 1
                # The terminal return is delivered exactly once, by the
                # incumbent finisher. A repeated submit never projects again.
                assert len(received) == 1
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_frozen_ordinal_is_never_recomputed(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-ordinal",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            # A frozen ordinal that is not the next Attempt refuses before
            # any effect; it never becomes a fresh Attempt.
            command = _install(service, runtime, work, ordinal=2)
            try:
                refused = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert refused["state"] == "REFUSED", refused
                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
                assert _claim_events(runtime, work.job_id) == []
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


@pytest.mark.parametrize("patch,reason", [
    ({"plan_attempt_id": "attempt-wrong"}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"plan_digest": "0" * 64}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"plan_step_id": "STEP-WRONG"}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"repair_round": 1}, "EXECUTIVE_PLAN_SELECTION_CHANGED"),
    ({"expected_current_attempt_id": "attempt-wrong"}, "EXECUTIVE_CURRENT_ATTEMPT_CHANGED"),
])
def test_stale_selection_refuses_before_effect(tmp_path, short_socket_root, patch, reason):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-stale",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            stale = ExecutiveChildSelection(**{
                **_selection(work).__dict__, **patch,
            })
            command = _install(service, runtime, work, selection=stale)
            try:
                refused = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert refused["state"] == "REFUSED", refused
                assert refused["reason"] == reason, refused
                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
                assert _claim_events(runtime, work.job_id) == []
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_wrong_authority_refuses_without_effect(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-authority",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)

            # The aggregation root is not a dispatchable selected child. The
            # service owner refuses it before any claim exists.
            root_expected = ExecutiveSelectedChild(
                selection=ExecutiveChildSelection(
                    root_job_id=root.job_id,
                    parent_job_id=root.job_id,
                    job_id=root.job_id,
                    plan_attempt_id=root.plan_attempt_id or "none",
                    plan_digest=root.plan_digest or "none",
                    plan_step_id=root.plan_step_id or "none",
                    repair_round=root.repair_round,
                    expected_current_attempt_id=root.current_attempt_id,
                ),
                attempt_ordinal=1,
            ).expected_selection()
            with pytest.raises(StateConflict, match="not dispatchable"):
                await service.dispatch_selected_child(
                    job_id=root.job_id,
                    command_id=root_expected.command_id,
                    expected_selection=root_expected,
                )
            assert runtime.jobs.get_job(root.job_id).attempt_count == 0
            assert runtime.jobs.get_job(work.job_id).attempt_count == 0

            # A planner Job is not a dispatchable selected child either.
            planner = next(
                job for job in runtime.jobs.list_jobs()
                if job.orchestration_role == "plan"
            )
            planner_expected = ExecutiveSelectedChild(
                selection=ExecutiveChildSelection(
                    root_job_id=root.job_id,
                    parent_job_id=planner.parent_job_id,
                    job_id=planner.job_id,
                    plan_attempt_id=planner.plan_attempt_id or "none",
                    plan_digest=planner.plan_digest or "none",
                    plan_step_id=planner.plan_step_id or "none",
                    repair_round=planner.repair_round,
                    expected_current_attempt_id=planner.current_attempt_id,
                ),
                attempt_ordinal=1,
            ).expected_selection()
            with pytest.raises(StateConflict):
                await service.dispatch_selected_child(
                    job_id=planner.job_id,
                    command_id=planner_expected.command_id,
                    expected_selection=planner_expected,
                )
            assert runtime.jobs.get_job(planner.job_id).attempt_count == 1
            assert runtime.jobs.get_job(work.job_id).attempt_count == 0

            # A command the host never froze is not selectable by the model.
            command = _install(service, runtime, work)
            try:
                unknown = await _call({
                    "action": "selected_child_submit",
                    "command": _command(work, ordinal=7),
                })
                assert unknown["state"] == "REFUSED", unknown
                assert unknown["reason"] == "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND"
                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_model_cannot_author_selection_authority(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-model",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                # A request key never selects or replaces a canonical Attempt.
                keyed = await _call({
                    "action": "selected_child_submit", "command": command,
                    "idempotency_key": "model-request-0001",
                })
                assert keyed["state"] == "REFUSED", keyed
                assert keyed["reason"] == "UNKNOWN_FIELD", keyed

                # The model cannot name a Job, root, carrier, or acceptance.
                for extra in (
                    {"job_id": work.job_id},
                    {"root_id": root.job_id},
                    {"carrier": "fabric"},
                    {"objective": "do something else"},
                ):
                    refused = await _call({
                        "action": "selected_child_submit", "command": command, **extra,
                    })
                    assert refused["state"] == "REFUSED", refused
                    assert refused["reason"] == "UNKNOWN_FIELD", refused

                # Owner operations stay outside the model-facing action set.
                for action in ("review", "consume", "cancel"):
                    refused = await _call({
                        "action": action, "command": command,
                    })
                    assert refused["state"] == "REFUSED", refused

                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_unbound_default_refuses_the_selected_child_branch(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-unbound",
        ) as (service, _supervisor, root, _received, gate):
            work = await _admit_work_child(service, root)
            clear_selected_child_composition()
            refused = await _call({
                "action": "selected_child_submit", "command": _command(work),
            })
            assert refused["state"] == "REFUSED", refused
            assert refused["reason"] == "EXECUTIVE_SELECTED_CHILD_NOT_BOUND", refused
            assert service.runtime.jobs.get_job(work.job_id).attempt_count == 0

    asyncio.run(exercise())


def test_unknown_post_claim_effect_stays_on_its_original_command(tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-unknown",
            supervisor_factory=_ambiguous_factory,
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                unknown = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert unknown["state"] == "EFFECT_UNKNOWN", unknown
                assert unknown["command_id"] == command
                attempt_id = unknown["attempt_id"]
                assert isinstance(attempt_id, str) and attempt_id
                # The uncertainty stays on the original command and Attempt.
                assert len(_claim_events(runtime, work.job_id)) == 1
                assert runtime.jobs.get_job(work.job_id).attempt_count == 1
                marker = runtime.events.get_event_by_command_id(
                    f"{command}:effect-unknown"
                )
                assert marker is not None
                # No retry, no second carrier, no new selection. The
                # uncertainty stays on the original command even though the
                # service can no longer act.
                repeated = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert repeated["state"] == "EFFECT_UNKNOWN", repeated
                assert repeated["attempt_id"] == attempt_id, repeated
                assert repeated["command_id"] == command
                assert len(_claim_events(runtime, work.job_id)) == 1
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_claim_boundary_re_proves_the_frozen_selection(tmp_path):
    """The Runtime re-proves the frozen selection inside the claim."""

    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, Path(tempfile.mkdtemp(prefix="mmx-c17-claim-", dir="/tmp")),
            name="selected-child-claim",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            selection = _selection(work)
            command = _command(work)
            expected = ExecutiveSelectedChild(
                selection=selection, attempt_ordinal=1,
            ).expected_selection()
            assert expected.command_id == command
            assert expected.attempt_ordinal == 1

            # A frozen selection that no longer names this Job refuses at the
            # canonical claim, before any Attempt exists.
            stale = type(expected)(
                **{**expected.__dict__, "plan_step_id": "STEP-WRONG"}
            )
            with pytest.raises(StateConflict, match="plan step drifted"):
                runtime.attempts.dispatch_cycle_job(
                    work.job_id,
                    command_id=command,
                    expected_selection=stale,
                )
            # The task-scoped binding is the same claim-boundary enforcement.
            with pytest.raises(StateConflict, match="plan step drifted"):
                with expected_child_selection(stale):
                    runtime.attempts.dispatch_cycle_job(
                        work.job_id, command_id=command,
                    )
            # A frozen ordinal that is not the next Attempt refuses too. The
            # incumbent pre-claim ordinal guard answers first; the
            # claim-boundary ordinal check is the in-transaction backstop.
            with pytest.raises(StateConflict, match="ordinal"):
                runtime.attempts.dispatch_cycle_job(
                    work.job_id,
                    command_id=_command(work, ordinal=2),
                    expected_selection=type(expected)(
                        **{
                            **expected.__dict__,
                            "attempt_ordinal": 2,
                            "command_id": _command(work, ordinal=2),
                        }
                    ),
                )
            assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            assert _claim_events(runtime, work.job_id) == []

    asyncio.run(exercise())


def test_explicit_selection_that_names_another_claim_is_refused(tmp_path, short_socket_root):
    """An explicit expected selection must name the claim it guards."""

    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-mismatch",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            expected = ExecutiveSelectedChild(
                selection=_selection(work), attempt_ordinal=1,
            ).expected_selection()
            command = _command(work)
            other = _command(work, ordinal=2)
            # A selection for a different command is a caller error, never an
            # unchecked Attempt.
            with pytest.raises(StateConflict, match="does not name this claim"):
                runtime.attempts.dispatch_cycle_job(
                    work.job_id, command_id=other, expected_selection=expected,
                )
            with pytest.raises(StateConflict, match="does not name this claim"):
                runtime.attempts.dispatch_cycle_job(
                    root.job_id, command_id=command, expected_selection=expected,
                )
            assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            assert _claim_events(runtime, work.job_id) == []

    asyncio.run(exercise())


def test_reconciled_effect_is_no_longer_reported_as_unknown(tmp_path, short_socket_root):
    """The canonical resolution event closes the ambiguity."""

    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-reconciled",
            supervisor_factory=_ambiguous_factory,
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                unknown = await _call({
                    "action": "selected_child_submit", "command": command,
                })
                assert unknown["state"] == "EFFECT_UNKNOWN", unknown
                attempt_id = unknown["attempt_id"]

                receipt = runtime.attempts.dispatch_cycle_job(
                    work.job_id, command_id=command, lease_owner="service-fixture",
                )
                assert receipt is not None and receipt.attempt.attempt_id == attempt_id
                runtime.jobs.reconcile_cycle_dispatch_effect(
                    root.job_id,
                    selected_job_id=work.job_id,
                    dispatch_command_id=command,
                    receipt=receipt,
                )
                observed = await _call({
                    "action": "selected_child_status", "command": command,
                })
                assert observed["state"] != "EFFECT_UNKNOWN", observed
                assert observed["attempt_id"] == attempt_id
                assert len(_claim_events(runtime, work.job_id)) == 1
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def test_same_loop_invocation_refuses_instead_of_deadlocking(tmp_path, short_socket_root):
    """The handler may not wait on the loop that owns the service."""

    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="selected-child-loop",
        ) as (service, _supervisor, root, _received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            try:
                refused = composition_submit_on_this_loop(service, runtime, work)
                assert refused["state"] == "REFUSED", refused
                assert refused["reason"] == (
                    "EXECUTIVE_SELECTED_CHILD_LOOP_REENTRANT"
                ), refused
                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
            finally:
                clear_selected_child_composition()

    asyncio.run(exercise())


def composition_submit_on_this_loop(service, runtime, work) -> dict:
    """Call the composition from inside the loop that owns the service."""

    from integrations.hermes_delegate.executive import (
        ExecutiveSelectedChildComposition,
        selected_child_composition,
    )

    composition = selected_child_composition()
    assert isinstance(composition, ExecutiveSelectedChildComposition)
    command = _command(work)
    return composition.submit(command)



def test_bound_identity_never_degrades_to_unconstrained_claim(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="bound-identity") as (service, supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            expected = ExecutiveSelectedChild(_selection(work), 1).expected_selection()
            with expected_child_selection(expected):
                with pytest.raises(StateConflict, match="does not name this claim"):
                    runtime.attempts.dispatch_cycle_job(root.job_id, command_id=expected.command_id)
                with pytest.raises(StateConflict, match="does not name this claim"):
                    runtime.attempts.dispatch_cycle_job(work.job_id, command_id=_command(work, 2))
                with pytest.raises(StateConflict, match="explicit and bound"):
                    runtime.attempts.dispatch_cycle_job(work.job_id, command_id=expected.command_id,
                        expected_selection=replace(expected, plan_step_id="foreign-step"))
            assert _claim_events(runtime, work.job_id) == []
            claimed = runtime.attempts.dispatch_cycle_job(work.job_id,
                command_id=expected.command_id, expected_selection=expected)
            with expected_child_selection(expected):
                replay = runtime.attempts.dispatch_cycle_job(work.job_id, command_id=expected.command_id)
            assert replay.attempt.attempt_id == claimed.attempt.attempt_id
            assert len(_claim_events(runtime, work.job_id)) == 1
    asyncio.run(exercise())


class _ContendedAmbiguousSupervisor(_AmbiguousSupervisor):
    def __init__(self, runtime, *, finish_gate):
        super().__init__(runtime, finish_gate=finish_gate)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.start_calls = 0

    async def start_cycle_job(self, job_id, *, command_id):
        self.start_calls += 1
        self.entered.set()
        await self.release.wait()
        return await super().start_cycle_job(job_id, command_id=command_id)


def test_concurrent_selected_submits_never_reenter_ambiguous_start(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="concurrent-original", supervisor_factory=_ContendedAmbiguousSupervisor
                ) as (service, supervisor, root, received, gate):
            work = await _admit_work_child(service, root)
            command = _install(service, service.runtime, work)
            composition = selected_child_composition()
            try:
                first = asyncio.create_task(composition.submit_async(command))
                await supervisor.entered.wait()
                second = asyncio.create_task(composition.submit_async(command))
                await asyncio.sleep(0)
                supervisor.release.set()
                results = await asyncio.gather(first, second)
                assert {r["state"] for r in results} == {"EFFECT_UNKNOWN"}, results
                assert results[0]["attempt_id"] == results[1]["attempt_id"]
                assert supervisor.start_calls == 1
                assert len(_claim_events(service.runtime, work.job_id)) == 1
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


def test_timeout_keeps_original_identity_and_does_not_cancel_scheduled_submit(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="scheduled-timeout") as (service, supervisor, root, received, gate):
            work = await _admit_work_child(service, root)
            command = _install(service, service.runtime, work)
            composition = replace(selected_child_composition(), timeout=0.01)
            original = service.dispatch_selected_child
            release, completed = asyncio.Event(), asyncio.Event()
            async def delayed(**arguments):
                await release.wait()
                try:
                    return await original(**arguments)
                finally:
                    completed.set()
            service.dispatch_selected_child = delayed
            try:
                timed_out = await asyncio.to_thread(composition.submit, command)
                assert timed_out["state"] == "EFFECT_UNKNOWN", timed_out
                assert timed_out["command_id"] == command
                assert timed_out["job_id"] == work.job_id
                assert timed_out["live_submit"] is None
                assert _claim_events(service.runtime, work.job_id) == []
                release.set()
                await completed.wait()
                observed = await composition.status_async(command)
                assert observed["state"] == "ACTIVE", observed
                assert len(_claim_events(service.runtime, work.job_id)) == 1
                gate.set()
                await _settle(service)
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["exception", "wrong_identity"])
def test_post_dispatch_failure_never_becomes_no_effect(tmp_path, short_socket_root, failure):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="post-dispatch-result") as (service, supervisor, root, received, gate):
            work = await _admit_work_child(service, root)
            command = _install(service, service.runtime, work)
            composition = selected_child_composition()
            original = service.dispatch_selected_child
            async def failed_reply(**arguments):
                result = await original(**arguments)
                if failure == "exception":
                    raise StateConflict("private owner failed after claim")
                return {**result, "command_id": "foreign-original"}
            service.dispatch_selected_child = failed_reply
            try:
                result = await composition.submit_async(command)
                assert result["state"] == "EFFECT_UNKNOWN", result
                assert (result["command_id"], result["job_id"]) == (command, work.job_id)
                assert result["live_submit"] is None
                observed = await composition.status_async(command)
                assert observed["state"] == "ACTIVE", observed
                assert len(_claim_events(service.runtime, work.job_id)) == 1
                gate.set()
                await _settle(service)
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


def test_missing_unknown_marker_does_not_clear_incumbent_uncertainty(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="marker-write-failure", supervisor_factory=_ambiguous_factory
                ) as (service, supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            def unavailable(*args, **kwargs):
                raise PersistenceError("marker storage unavailable")
            runtime.jobs.record_cycle_dispatch_effect_unknown = unavailable
            try:
                composition = selected_child_composition()
                first = await composition.submit_async(command)
                repeated = await composition.submit_async(command)
                observed = await composition.status_async(command)
                assert {r["state"] for r in (first, repeated, observed)} == {"EFFECT_UNKNOWN"}
                assert len({r["attempt_id"] for r in (first, repeated, observed)}) == 1
                assert runtime.events.get_event_by_command_id(command + ":effect-unknown") is None
                assert service._service_state == "QUARANTINED"
                assert len(_claim_events(runtime, work.job_id)) == 1
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


def test_real_principal_revocation_inside_claim_rolls_back_all_claim_facts(tmp_path, short_socket_root):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="claim-authority-race") as (service, supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            original = runtime.attempts._claim_job_in_transaction
            authority_config = service._selected_child_fixture[1]
            checked = []
            def revoke_after_insert(*args, **kwargs):
                result = original(*args, **kwargs)
                checked.append(result.attempt.attempt_id)
                authority_config["missions"][0]["enabled"] = False
                return result
            runtime.attempts._claim_job_in_transaction = revoke_after_insert
            try:
                result = await selected_child_composition().submit_async(command)
                assert result["state"] == "REFUSED", result
                assert len(checked) == 1
                assert _claim_events(runtime, work.job_id) == []
                assert runtime.jobs.get_job(work.job_id).attempt_count == 0
                assert runtime.attempts.get_attempt(checked[0]) is None
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


@pytest.mark.parametrize("case", ["role_string", "async_guard", "non_none_guard", "revoked"])
def test_private_authority_cannot_be_model_role_or_async_guard(tmp_path, short_socket_root, case):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name="private-authority") as (service, supervisor, root, received, gate):
            runtime = service.runtime
            work = await _admit_work_child(service, root)
            command = _install(service, runtime, work)
            composition = selected_child_composition()
            if case == "role_string":
                composition = replace(composition, context={"role": "mmsecretary"})
            elif case == "async_guard":
                async def invalid():
                    return None
                composition = replace(composition, receiving_request_guard=invalid)
            elif case == "non_none_guard":
                composition = replace(composition, receiving_request_guard=lambda: False)
            else:
                service._selected_child_fixture[1]["missions"][0]["enabled"] = False
            try:
                result = await composition.submit_async(command)
                assert result["state"] == "REFUSED", result
                assert result["live_submit"] is False
                assert _claim_events(runtime, work.job_id) == []
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# WO-13: idempotent ChildExecutionRequest.v1 admission + bounded ready queue
# ---------------------------------------------------------------------------


def _child_request_envelope(root_ref, parent_ref, key, *, complexity="C2_COMPLEX_BOUNDED",
                            task_kind="research", brief_digest="a" * 64):
    """One wire-shaped ChildExecutionRequest.v1 with its verified digest."""

    from control_plane.child_execution_contracts import ChildExecutionRequest

    request = ChildExecutionRequest(
        root_ref=root_ref, immediate_parent_run_ref=parent_ref,
        logical_child_key=key, task_kind=task_kind,
        requested_complexity=complexity, brief_digest=brief_digest,
    )
    return request.to_dict()


def _child_request_events(runtime, command_id: str) -> list[Any]:
    with runtime.store.read() as connection:
        return list(connection.execute(
            "SELECT * FROM events WHERE command_id=? ORDER BY event_id",
            (command_id,),
        ).fetchall())


def _child_request_job_count(runtime) -> int:
    with runtime.store.read() as connection:
        return int(connection.execute(
            "SELECT COUNT(*) FROM events e JOIN jobs j ON j.job_id=e.job_id "
            "WHERE e.event_type='JOB_CREATED' AND json_extract(e.payload_json,"
            " '$.provenance.child_request.schema') = 'ChildExecutionRequest.v1'"
        ).fetchone()[0])


def test_child_request_duplicate_key_replay_returns_the_same_job(
        tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="child-request-replay",
        ) as (service, _supervisor, root, _received, _gate):
            runtime = service.runtime
            envelope = _child_request_envelope(
                root.job_id, root.job_id, "reconcile-digest-0001")

            first = await service.admit_child_execution_request(envelope)
            assert first["schema"] == "mastermind.child_request_admission/v1"
            assert first["state"] == "ADMITTED", first
            assert isinstance(first["job_id"], str) and first["job_id"]
            command_id = first["command_id"]
            assert command_id.startswith("child-request:")

            job = runtime.jobs.get_job(first["job_id"])
            assert job.status.value == "QUEUED"
            assert job.attempt_count == 0
            # Admission selects nothing (OQ-9): no worker, provider or
            # placement decision rides on the admitted Job.
            constraints = job.constraints or {}
            assert "provider" not in constraints and "worker" not in constraints

            # A duplicate delivery of the same key + digest replays to the
            # SAME Job — exactly one durable admission, not two.
            replay = await service.admit_child_execution_request(envelope)
            assert replay["state"] == "REPLAY", replay
            assert replay["job_id"] == first["job_id"]
            assert replay["command_id"] == command_id
            assert replay["request_digest"] == first["request_digest"]
            events = _child_request_events(runtime, command_id)
            assert len(events) == 1
            assert events[0]["event_type"] == "JOB_CREATED"
            assert events[0]["job_id"] == first["job_id"]
            assert _child_request_job_count(runtime) == 1

    asyncio.run(exercise())


def test_child_request_key_with_different_digest_is_a_conflict(
        tmp_path, short_socket_root):
    async def exercise() -> None:
        from control_plane.executive_runtime import StateConflict

        async with _selected_child_service(
            tmp_path, short_socket_root, name="child-request-conflict",
        ) as (service, _supervisor, root, _received, _gate):
            runtime = service.runtime
            admitted = await service.admit_child_execution_request(
                _child_request_envelope(
                    root.job_id, root.job_id, "conflicting-key-001"))
            assert admitted["state"] == "ADMITTED", admitted

            # Same idempotency triple, different goal digest: a conflict,
            # never a second Job and never a silent re-admission.
            with pytest.raises(StateConflict, match="CHILD_REQUEST_DIGEST_CONFLICT"):
                await service.admit_child_execution_request(
                    _child_request_envelope(
                        root.job_id, root.job_id, "conflicting-key-001",
                        brief_digest="b" * 64))
            assert _child_request_job_count(runtime) == 1

            # A genuinely different key is ordinary new work.
            other = await service.admit_child_execution_request(
                _child_request_envelope(
                    root.job_id, root.job_id, "conflicting-key-002"))
            assert other["state"] == "ADMITTED", other
            assert other["job_id"] != admitted["job_id"]
            assert _child_request_job_count(runtime) == 2

    asyncio.run(exercise())


def test_child_request_root_cap_32_returns_precise_wait_reason(
        tmp_path, short_socket_root):
    async def exercise() -> None:
        async with _selected_child_service(
            tmp_path, short_socket_root, name="child-request-root-cap",
        ) as (service, _supervisor, root, _received, _gate):
            runtime = service.runtime
            for index in range(32):
                outcome = await service.admit_child_execution_request(
                    _child_request_envelope(
                        root.job_id, root.job_id, f"root-cap-key-{index:03d}"))
                assert outcome["state"] == "ADMITTED", (index, outcome)

            # The 33rd distinct key hits the durable per-root cap and is
            # returned to the parent planner with a precise wait reason.
            # One synchronous decision: no job, no retry.
            wait = await service.admit_child_execution_request(
                _child_request_envelope(
                    root.job_id, root.job_id, "root-cap-key-032"))
            assert wait["state"] == "WAIT", wait
            assert wait["wait_reason"] == "CHILD_QUEUE_ROOT_READY_FULL", wait
            assert wait["job_id"] is None
            assert wait["wait_detail"]["root_ready"] == 32
            assert wait["wait_detail"]["root_limit"] == 32
            assert wait["wait_detail"]["root_ref"] == root.job_id
            assert _child_request_job_count(runtime) == 32

            # A replay still outranks the caps: a lost-response retry of
            # an admitted key recovers its handle even with a full queue.
            replay = await service.admit_child_execution_request(
                _child_request_envelope(
                    root.job_id, root.job_id, "root-cap-key-000"))
            assert replay["state"] == "REPLAY", replay
            assert _child_request_job_count(runtime) == 32

    asyncio.run(exercise())


def test_child_request_fleet_cap_is_configurable_backpressure(
        tmp_path, short_socket_root, monkeypatch):
    async def exercise() -> None:
        monkeypatch.setenv("MMOS_CHILD_FLEET_READY_LIMIT", "2")
        monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "32")
        async with _selected_child_service(
            tmp_path, short_socket_root, name="child-request-fleet-cap",
        ) as (service, _supervisor, root, _received, _gate):
            runtime = service.runtime
            other_root = "ROOT-OTHER-0001"
            first = await service.admit_child_execution_request(
                _child_request_envelope(root.job_id, root.job_id, "fleet-key-001"))
            second = await service.admit_child_execution_request(
                _child_request_envelope(other_root, other_root, "fleet-key-002"))
            assert first["state"] == "ADMITTED" and second["state"] == "ADMITTED"

            # The fleet cap is configured at two: a third request from a
            # third root is backpressured with the fleet reason, even
            # though neither root has reached its per-root cap.
            wait = await service.admit_child_execution_request(
                _child_request_envelope("ROOT-THIRD-0001", "ROOT-THIRD-0001",
                                        "fleet-key-003"))
            assert wait["state"] == "WAIT", wait
            assert wait["wait_reason"] == "CHILD_QUEUE_FLEET_READY_FULL", wait
            assert wait["wait_detail"]["fleet_ready"] == 2
            assert wait["wait_detail"]["fleet_limit"] == 2
            assert wait["wait_detail"]["root_ready"] == 0
            assert _child_request_job_count(runtime) == 2

            # The durable queue orders by priority, then bounded aging,
            # with root fairness and skip-ineligible behaviour.
            ordered, skipped = runtime.jobs.child_request_ready_queue(
                now_ms=int(runtime.store.now_ms()))
            assert [item.job_id for item in ordered] == [
                first["job_id"], second["job_id"]]
            assert skipped == ()

    asyncio.run(exercise())


# ---------------------------------------------------------------------------
# REVIEW_2317 F1/F2 hardening.
#
# F1: the ready-queue caps are re-checked inside the SAME ``BEGIN IMMEDIATE``
# transaction that inserts the Job and its JOB_CREATED receipt, so two
# concurrent admissions of DISTINCT keys cannot both observe a free slot and
# overshoot the bound.  These tests use a real durable store with one
# connection per admission, i.e. the exact read-then-write window the review's
# probe P2 exploited.
#
# F2: the idempotency triple's three fields are a fenced identifier charset,
# so a field carrying the "\x1f" join separator cannot collapse two DISTINCT
# triples onto one durable command id (a spurious digest conflict).
# ---------------------------------------------------------------------------


def _child_request_value(
        root_ref, immediate_parent_run_ref, logical_child_key, *,
        brief_digest="a" * 64):
    """One ``ChildExecutionRequest.v1`` value object, without a service."""

    from control_plane.child_execution_contracts import ChildExecutionRequest

    return ChildExecutionRequest(
        root_ref=root_ref, immediate_parent_run_ref=immediate_parent_run_ref,
        logical_child_key=logical_child_key, task_kind="research",
        requested_complexity="C2_COMPLEX_BOUNDED", brief_digest=brief_digest)


def _race_admissions(registry, requests):
    """Admit one request per thread against one store; (outcomes, errors)."""

    outcomes: list[Any] = [None] * len(requests)
    errors: list[Any] = [None] * len(requests)
    barrier = threading.Barrier(len(requests))

    def admit(index, request):
        barrier.wait()
        try:
            outcomes[index] = registry.admit_child_execution_request(request)
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
            errors[index] = exc

    threads = [
        threading.Thread(target=admit, args=(index, request), daemon=True)
        for index, request in enumerate(requests)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads), "admission deadlock"
    return outcomes, errors


def test_child_request_concurrent_distinct_keys_hold_the_root_ready_cap(
        tmp_path, monkeypatch):
    """Two threads, two DISTINCT keys, root limit 1: exactly one ADMITTED."""

    monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "1")
    monkeypatch.delenv("MMOS_CHILD_FLEET_READY_LIMIT", raising=False)
    registry = JobRegistry(RuntimeStore(tmp_path))

    outcomes, errors = _race_admissions(registry, [
        _child_request_value("ROOT-RACE-1", "ROOT-RACE-1", "race-key-a"),
        _child_request_value("ROOT-RACE-1", "ROOT-RACE-1", "race-key-b"),
    ])
    assert errors == [None, None], errors
    assert sorted(outcome.state for outcome in outcomes) == ["ADMITTED", "WAIT"]

    admitted = next(o for o in outcomes if o.state == "ADMITTED")
    wait = next(o for o in outcomes if o.state == "WAIT")
    # The loser is a precise backpressure decision, not an error and not a
    # retry: no handle, the root bound named, and the counts that produced it.
    assert wait.job_id is None
    assert wait.wait_reason == "CHILD_QUEUE_ROOT_READY_FULL"
    assert wait.wait_detail["reason"] == "CHILD_QUEUE_ROOT_READY_FULL"
    assert wait.wait_detail["root_ref"] == "ROOT-RACE-1"
    assert wait.wait_detail["root_ready"] == 1
    assert wait.wait_detail["root_limit"] == 1

    # Durable truth: one ready job under a limit of one, and the loser left
    # no event of its own behind.
    assert _child_request_job_count(registry) == 1
    with registry.store.read() as connection:
        loser_events = connection.execute(
            "SELECT event_id FROM events WHERE command_id=?",
            (wait.command_id,),
        ).fetchall()
    assert loser_events == []

    # The winner's handle is the one durable admission.
    job = registry.get_job(admitted.job_id)
    assert job is not None
    assert job.status == JobStatus.QUEUED
    assert job.attempt_count == 0


def test_child_request_concurrent_distinct_roots_hold_the_fleet_ready_cap(
        tmp_path, monkeypatch):
    """Four threads, four roots, fleet limit 2: exactly two ADMITTED."""

    monkeypatch.setenv("MMOS_CHILD_FLEET_READY_LIMIT", "2")
    monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "32")
    registry = JobRegistry(RuntimeStore(tmp_path))

    roots = ("ROOT-FLEET-A", "ROOT-FLEET-B", "ROOT-FLEET-C", "ROOT-FLEET-D")
    outcomes, errors = _race_admissions(registry, [
        _child_request_value(root, root, f"fleet-race-key-{index}")
        for index, root in enumerate(roots)
    ])
    assert errors == [None, None, None, None], errors
    states = [outcome.state for outcome in outcomes]
    assert states.count("ADMITTED") == 2
    assert states.count("WAIT") == 2

    waits = [o for o in outcomes if o.state == "WAIT"]
    for wait in waits:
        assert wait.job_id is None
        assert wait.wait_reason == "CHILD_QUEUE_FLEET_READY_FULL"
        assert wait.wait_detail["fleet_ready"] == 2
        assert wait.wait_detail["fleet_limit"] == 2
        # Per-root caps were never the binding constraint here.
        assert wait.wait_detail["root_ready"] == 0

    assert _child_request_job_count(registry) == 2


def test_child_request_concurrent_replay_recovers_its_handle_under_a_full_queue(
        tmp_path, monkeypatch):
    """Replay outranks the caps even while a rival race fills the queue."""

    monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "1")
    monkeypatch.delenv("MMOS_CHILD_FLEET_READY_LIMIT", raising=False)
    registry = JobRegistry(RuntimeStore(tmp_path))

    first = registry.admit_child_execution_request(
        _child_request_value("ROOT-RACE-2", "ROOT-RACE-2", "race-known-key"))
    assert first.state == "ADMITTED", first

    outcomes, errors = _race_admissions(registry, [
        _child_request_value("ROOT-RACE-2", "ROOT-RACE-2", "race-known-key"),
        _child_request_value("ROOT-RACE-2", "ROOT-RACE-2", "race-new-key"),
    ])
    assert errors == [None, None], errors
    replay, rival = outcomes
    assert replay.state == "REPLAY", replay
    assert replay.job_id == first.job_id
    assert replay.command_id == first.command_id
    assert rival.state == "WAIT", rival
    assert rival.job_id is None
    assert _child_request_job_count(registry) == 1


def test_child_request_concurrent_digest_conflict_never_creates_a_second_job(
        tmp_path):
    """Same triple, different digest, racing: one Job and one conflict."""

    registry = JobRegistry(RuntimeStore(tmp_path))
    outcomes, errors = _race_admissions(registry, [
        _child_request_value("ROOT-RACE-3", "ROOT-RACE-3", "race-digest-key"),
        _child_request_value(
            "ROOT-RACE-3", "ROOT-RACE-3", "race-digest-key",
            brief_digest="b" * 64),
    ])
    admitted = [o for o in outcomes if o is not None and o.state == "ADMITTED"]
    conflicts = [e for e in errors if isinstance(e, StateConflict)]
    assert len(admitted) == 1, (outcomes, errors)
    assert len(conflicts) == 1, (outcomes, errors)
    assert "CHILD_REQUEST_DIGEST_CONFLICT" in str(conflicts[0])
    assert _child_request_job_count(registry) == 1


def test_child_request_idempotency_fields_are_a_fenced_identifier_charset():
    """F2: the triple cannot carry the join separator or unbounded text."""

    from control_plane.child_execution_contracts import (
        BOUNDED_IDENTIFIER_MAX_LENGTH,
    )

    # The reviewer's probe P3 pair: distinct triples, one command id, because
    # "\x1f" moved across the field boundary.  Both are now refused outright.
    for root_ref, parent_ref, key in (
        ("a", "b\x1fc", "d"),
        ("a", "b", "c\x1fd"),
    ):
        with pytest.raises(ValueError, match="printable identifier"):
            _child_request_value(root_ref, parent_ref, key)

    for field in ("root_ref", "immediate_parent_run_ref", "logical_child_key"):
        for bad in ("x\x00y", "x\ty", "x\x1fy", "x\x7fy"):
            kwargs = {
                "root_ref": "ROOT-FENCE", "immediate_parent_run_ref": "RUN-FENCE",
                "logical_child_key": "key-fence",
            }
            kwargs[field] = bad
            with pytest.raises(ValueError, match="printable identifier"):
                _child_request_value(**kwargs)
        kwargs = {
            "root_ref": "ROOT-FENCE", "immediate_parent_run_ref": "RUN-FENCE",
            "logical_child_key": "key-fence",
        }
        kwargs[field] = "x" * (BOUNDED_IDENTIFIER_MAX_LENGTH + 1)
        with pytest.raises(ValueError, match="at most 256 characters"):
            _child_request_value(**kwargs)

    # Ordinary host identifiers are untouched, including ones at the bound.
    valid = _child_request_value(
        "hermes-root-1", "hermes-run-7", "k" * BOUNDED_IDENTIFIER_MAX_LENGTH)
    assert valid.idempotency_key() == (
        "hermes-root-1", "hermes-run-7", "k" * BOUNDED_IDENTIFIER_MAX_LENGTH)
    assert len(valid.request_digest) == 64

