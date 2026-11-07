"""Ordinary source-bound remote operator recovery on the selected host.

These tests prove the ordinary (noncancel, no PREPARE, same-realm) recovery of
one commission-bound remote planner Attempt through the existing reconcile and
real role/result lifecycle of
:meth:`control_plane.executive_operator_supervisor.ExecutiveOperatorSupervisor._recover_one`.

Everything here is real: the private Executive Runtime, the durable
Job/Attempt/worker assignment, the strict-v2 commission verifier, the harness
admission/lease/G1 owners and the operation port.  Only two boundaries are
fixtures, exactly as allowed: the native adapter
(``claimed_adapter_factory`` with ``recovery=True``) and the canonical remote
byte transport (``_fetch_remote_commission``).  The remote workspace is
removed locally before recovery so any local stat, resolve or Git read fails
loudly, and ``_commission_git_probe`` is patched to raise on every test, so a
remote recovery can never borrow Control-local source.

The selected-host workspace identity is never re-observed during recovery:
the ``workspace_identity_source`` sentinel below records and refuses any call,
and the positive proof asserts it stayed empty.  Recovery may only reuse the
canonical Runtime-sealed ``session.launch.requested.workspace`` of the exact
current G1 writer under the exact recovery lease.

TEST FIRST: before the production change the positive proof fails with exactly
the ``workspace=None``/no-owner-identity refusal of
``verify_commission_for_job`` (``commission-bound Job has no assigned
workspace``), re-demonstrated in-process by the real verifier; no
source-validator or Runtime mock is installed on the pass path.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from control_plane import executive_supervisor as executive_supervisor_mod
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
)
from control_plane.executive_runtime import AttemptStatus, JobStatus
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ReconcileStatus,
    SupervisorError,
    verify_commission_for_job,
)
from control_plane.operator_harness_contract import (
    OperationReceiptKind,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
)
from test_executive_operator_supervisor import (
    _RecoveryAdapter,
    _seed_commission_bound_legacy_turn,
)

_RECOVERY_READY_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
}


class _RemoteRecoveryAdapter(_RecoveryAdapter):
    """The existing fake adapter pinned to the seeded G1 process identity."""

    def __init__(self, runtime, profile, loader, *, live_existing: bool) -> None:
        super().__init__(runtime, profile, loader, live_existing=live_existing)
        self.process = ProcessIdentityObservation(4101, 4101, "start-4101", "boot-test")
        self.recovery = False

    def reconcile(self, _generation):
        return ReconcileObservation(
            ProcessLiveness.ALIVE,
            self.process,
            True,
            ProviderWriterState.HELD,
            self.provider_session_id,
            self.profile.expected_config_digest,
        )


def _recovery_factory(runtime, profile, registry: list):
    def factory(_attempt, requested, loader, *, recovery: bool):
        adapter = _RemoteRecoveryAdapter(
            runtime, requested, loader, live_existing=True
        )
        adapter.recovery = bool(recovery)
        registry.append(adapter)
        return adapter

    return factory


def _forbidden_observation(recorder: list):
    """Sentinel proving the selected-host observer is never re-dispatched."""

    def observe(_attempt, _job):
        recorder.append("workspace-observation")
        raise AssertionError("recovery must not re-dispatch the selected-host observer")

    return observe


def _forbid_local_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("remote recovery must not run local Git")

    monkeypatch.setattr(
        executive_supervisor_mod, "_commission_git_probe", forbidden
    )


def _install_remote_bytes(monkeypatch: pytest.MonkeyPatch, *, content: bytes, mutate=None):
    calls = []

    def reader(*, repository: str, commit: str, path: str) -> bytes:
        calls.append({"repository": repository, "commit": commit, "path": path})
        if mutate is not None:
            mutate()
        return content

    monkeypatch.setattr(
        executive_supervisor_mod, "_fetch_remote_commission", reader
    )
    return calls


def _detach_workspace(planner) -> None:
    """Remove the local copy: the real workspace lives on the selected host."""

    shutil.rmtree(str(planner.worktree))
    assert not Path(str(planner.worktree)).exists()


def _corrupt_private_row(runtime, sql: str, params: tuple) -> None:
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute(sql, params)
        connection.commit()
    finally:
        connection.close()


def _strip_durable_base_sha(runtime, planner) -> None:
    connection = sqlite3.connect(runtime.store.path)
    try:
        row = connection.execute(
            "SELECT constraints_json FROM jobs WHERE job_id=?",
            (planner.job_id,),
        ).fetchone()
        assert row is not None
        constraints = json.loads(str(row[0]))
        constraints.pop("base_sha", None)
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (
                json.dumps(constraints, sort_keys=True, separators=(",", ":")),
                planner.job_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _require_recovered_or_baseline_refusal(recovered, runtime, planner, adapters):
    """Pass only after real recovery; on regression re-show the exact refusal."""

    if [item.status for item in recovered] == [ReconcileStatus.OPERATOR_RECOVERED]:
        assert adapters, "recovery must run through the claimed recovery adapter"
        return
    assert adapters == [], "a refused remote recovery must stay before the adapter"
    with pytest.raises(
        SupervisorError, match="commission-bound Job has no assigned workspace"
    ):
        # The exact pre-fix call shape: workspace=None, no owner identity.
        verify_commission_for_job(runtime, planner, None)
    pytest.fail(
        "ordinary remote recovery refused before the adapter: "
        "verify_commission_for_job received workspace=None with no owner "
        "workspace identity"
    )


def _remote_recovery_supervisor(runtime, profile, *, registry, observations):
    return ExecutiveOperatorSupervisor(
        runtime,
        claimed_adapter_factory=_recovery_factory(runtime, profile, registry),
        workspace_identity_source=_forbidden_observation(observations),
        prompt_source=ExecutiveSupervisor(
            runtime,
            object(),  # type: ignore[arg-type]
            inspector=object(),  # type: ignore[arg-type]
            process_controller=object(),  # type: ignore[arg-type]
        ),
    )


def test_ordinary_remote_commission_recovery_completes_without_local_source_or_reobservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)
    calls = _install_remote_bytes(monkeypatch, content=commission)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    _require_recovered_or_baseline_refusal(recovered, runtime, planner, adapters)
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.COMPLETED
    assert len(adapters) == 1
    assert adapters[0].recovery is True
    assert adapters[0].resume_calls == 0
    assert adapters[0].begin_turn_calls == 0
    assert adapters[0].read_calls == 1
    assert adapters[0].cancel_calls == 0
    assert observations == [], "recovery must not re-dispatch the selected-host observer"
    assert calls == [
        {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": planner.constraints["base_sha"],
            "path": "research/operator-commission.md",
        }
    ]
    with runtime.store.read() as connection:
        turns = connection.execute(
            """SELECT payload_json FROM events
               WHERE attempt_id=? AND aggregate_type='operator_operation'
                 AND event_type=? ORDER BY event_id""",
            (dispatch.attempt.attempt_id, OperationReceiptKind.INTENT.value),
        ).fetchall()
        epoch = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        ).fetchone()
    begin_turns = [
        json.loads(str(row["payload_json"]))
        for row in turns
        if json.loads(str(row["payload_json"])).get("operation_kind") == "begin_turn"
    ]
    assert len(begin_turns) == 1, "exactly the original turn must remain"
    assert len(runtime.attempts.list_attempts()) == 1
    assert epoch["state"] == "ABANDONED"


def test_remote_recovery_refuses_lease_rebind_during_source_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)

    def rebind() -> None:
        _corrupt_private_row(
            runtime,
            "UPDATE attempts SET lease_owner='remote-rebind',"
            " fence_generation=fence_generation+1 WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        )

    calls = _install_remote_bytes(monkeypatch, content=commission, mutate=rebind)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    assert [item.status for item in recovered] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert adapters == [], "drifted lease must refuse before any adapter or resumed turn"
    assert len(calls) == 1
    assert observations == []
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status in _RECOVERY_READY_STATUSES
    with runtime.store.read() as connection:
        epoch = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        ).fetchone()
    assert epoch["state"] == "CURRENT"


def test_remote_recovery_refuses_worker_rebind_during_source_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)

    def rebind() -> None:
        _corrupt_private_row(
            runtime,
            "UPDATE attempts SET worker_id='worker-b' WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        )

    calls = _install_remote_bytes(monkeypatch, content=commission, mutate=rebind)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    assert [item.status for item in recovered] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert adapters == [], "rebound worker must refuse before any adapter or resumed turn"
    assert len(calls) == 1
    assert observations == []
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None
    job = runtime.jobs.get_job(planner.job_id)
    assert job is not None and job.status is not JobStatus.COMPLETED


def test_remote_recovery_refuses_sealed_workspace_drift_before_source_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)
    calls = _install_remote_bytes(monkeypatch, content=commission)
    _strip_durable_base_sha(runtime, planner)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    assert [item.status for item in recovered] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert adapters == [], "sealed workspace drift must refuse before any adapter"
    assert calls == [], "sealed workspace drift must refuse before the blocking fetch"
    assert observations == []
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status in _RECOVERY_READY_STATUSES
    with runtime.store.read() as connection:
        epoch = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        ).fetchone()
    assert epoch["state"] == "CURRENT"


def test_remote_recovery_refuses_writer_move_during_source_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)

    def move_writer() -> None:
        _corrupt_private_row(
            runtime,
            "UPDATE harness_session_epochs SET state='ABANDONED' WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        )

    calls = _install_remote_bytes(monkeypatch, content=commission, mutate=move_writer)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    assert [item.status for item in recovered] == [ReconcileStatus.IDENTITY_AMBIGUOUS]
    assert adapters == [], "moved current writer must refuse before any adapter"
    assert len(calls) == 1
    assert observations == []
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status in _RECOVERY_READY_STATUSES


def test_remote_recovery_cancellation_still_wins_without_commission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, runtime, planner, dispatch, profile, commission, _turn = (
        _seed_commission_bound_legacy_turn(
            tmp_path,
            legacy_operation=False,
            production_prompt_source=True,
        )
    )
    _forbid_local_source(monkeypatch)
    calls = _install_remote_bytes(monkeypatch, content=commission)
    _detach_workspace(planner)
    observations: list = []
    adapters: list = []
    supervisor = _remote_recovery_supervisor(
        runtime, profile, registry=adapters, observations=observations
    )
    cancelled = runtime.jobs.cancel_job(planner.job_id)
    assert cancelled.status is JobStatus.CANCEL_REQUESTED
    clock.advance(3)

    recovered = supervisor.reconcile_restart()

    assert [item.status for item in recovered] == [ReconcileStatus.MISSING_CANCELLED]
    assert len(adapters) == 1
    assert adapters[0].recovery is True
    assert adapters[0].cancel_calls == 1
    assert adapters[0].resume_calls == 0
    assert adapters[0].begin_turn_calls == 0
    assert calls == [], "cancellation containment must not fetch the commission"
    assert observations == []
    attempt = runtime.attempts.get_attempt(dispatch.attempt.attempt_id)
    assert attempt is not None and attempt.status is AttemptStatus.CANCELLED
    job = runtime.jobs.get_job(planner.job_id)
    assert job is not None and job.status is JobStatus.CANCELLED
    with runtime.store.read() as connection:
        epoch = connection.execute(
            "SELECT state FROM harness_session_epochs WHERE attempt_id=?",
            (dispatch.attempt.attempt_id,),
        ).fetchone()
    assert epoch["state"] == "ABANDONED"
    assert supervisor.reconcile_restart() == []


from control_plane import executive_operator_supervisor as owner

@pytest.mark.parametrize('drift', ['prepare', 'expiry', 'generation', 'cancel', 'attestation'])
def test_blocking_source_fetch_rechecks_current_owner_and_continuation_hold(tmp_path, monkeypatch, drift):
    clock, runtime, planner, dispatch, profile, content, turn = _seed_commission_bound_legacy_turn(
        tmp_path, legacy_operation=False, production_prompt_source=True)
    shutil.rmtree(planner.worktree)
    fetches, adapters = [], []
    def fetch(**kwargs):
        fetches.append(kwargs)
        if drift == 'prepare':
            # This is deliberately only a hold marker, never valid PREPARE/ACK authority.
            with runtime.store.transaction() as connection:
                runtime.store.append_event(connection, aggregate_type='inert_test_hold',
                    aggregate_id=dispatch.attempt.attempt_id, event_type='INERT_HOLD_MARKER',
                    attempt_id=dispatch.attempt.attempt_id,
                    command_id=f'operator-continuation:prepare:{dispatch.attempt.attempt_id}')
        elif drift == 'expiry':
            clock.advance(361)
        elif drift == 'generation':
            runtime.operator_harness.invalidate_after_restore()
        elif drift == 'attestation':
            # Private-store fault injection: the old G1 refs/PID remain equal,
            # and compare_launch still ALLOWs this version-only metadata drift.
            with runtime.store.transaction() as connection:
                row = connection.execute("SELECT process_generation_id,observed_attestation_json FROM process_generations WHERE executive_writer_held=1").fetchone()
                data = json.loads(row['observed_attestation_json'])
                data['harness_version'] = 'inert-post-fetch-drift'
                connection.execute("UPDATE process_generations SET observed_attestation_json=? WHERE process_generation_id=?", (json.dumps(data), row['process_generation_id']))
        elif drift == 'cancel':
            runtime.jobs.cancel_job(dispatch.attempt.job_id)
        return content
    monkeypatch.setattr(executive_supervisor_mod, '_fetch_remote_commission', fetch)
    def no_local(*args, **kwargs):
        raise AssertionError('remote recovery must not read local Git')
    monkeypatch.setattr(executive_supervisor_mod, '_commission_git_probe', no_local)
    def construct(*args, **kwargs):
        adapters.append(True)
        raise AssertionError('stale/held owner must refuse before adapter access')
    prompt = ExecutiveSupervisor(runtime, object(), inspector=object(), process_controller=object())
    sup = owner.ExecutiveOperatorSupervisor(runtime, claimed_adapter_factory=construct,
        workspace_identity_source=no_local, prompt_source=prompt)
    clock.advance(3)
    receipts = sup.reconcile_restart()
    assert len(fetches) == 1, 'must exercise the blocking actual canonical source fetch'
    assert not adapters
    expected = (ReconcileStatus.LIVE_QUARANTINED if drift == 'prepare'
                else ReconcileStatus.IDENTITY_AMBIGUOUS)
    assert [r.status for r in receipts] == [expected]

