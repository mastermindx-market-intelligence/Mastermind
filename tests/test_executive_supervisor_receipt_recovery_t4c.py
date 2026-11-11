"""T4c step 1 (R4b findings 1, 2, 7): the engine's exactly-once receipt path.

Finding 1 — a receipt adoption must END WITH A RUN SOMEONE OWNS: reattach
through the adapter, persist a ``worker_recovery_binding`` in the same
adoption transaction, and hand the adopted lease to the recovered-runs list.
After it, later reconcile passes must never wedge in IDENTITY_AMBIGUOUS and
the attempt must still be able to heartbeat and complete.

Finding 2 — a reconcile pass must NEVER take a claim from a live launcher:
while the lease is unexpired (the claimant may be sitting between
``put_launch_receipt`` and ``record_process``) reconcile defers; the
launcher's ``record_process`` then succeeds on its ORIGINAL fence and token
and ``adapter.cancel`` is never called.

Finding 7 — ONE expired-lease recovery path, the same one, used by restart
recovery after long downtime: an expired lease is the engine's own proof the
claimant lost its rights, so reconcile adopts under the receipt (identity-
less crash window) or through the existing binding path (recorded identity)
— same attempt, no requeue, no second native launch.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_executive_supervisor_receipt_recovery_t4c.py
"""
import asyncio

import pytest

import control_plane.executive_supervisor as owner
from control_plane.executive_runtime import (
    JobPayload,
    JobStatus,
    Runtime,
    StateConflict,
)
from control_plane.executive_supervisor import (
    ExecutiveSupervisor,
    ProcessPresence,
    ReconcileStatus,
)
from control_plane.worker_execution_contract import WorkerRecoveryBinding

from tests.test_executive_supervisor import (
    FakeAdapter,
    FakeInspector,
    UnknownProcessController,
    _runtime_and_job,
    _supervisor,
)

# RECEIPT_RECOVERED does not exist before the fix; the getattr fallback keeps
# the pre-fix failure behavioural (the recovered-run assertions fail first)
# instead of an ImportError that proves nothing.
RECEIPT_RECOVERED = getattr(ReconcileStatus, "RECEIPT_RECOVERED",
                            ReconcileStatus.LIVE_QUARANTINED)


class ReceiptCapableAdapter(FakeAdapter):
    """A provider-managed adapter with the T3 adapter's durability shape.

    ``start`` persists the launch receipt (spec + original provider ref +
    provider session id) in its own durable store BEFORE the start ACK, the
    way ``put_launch_receipt`` does.  The crash window under test is between
    that persistence and the supervisor's ``record_process``.
    """

    adapter_id = "receipt-fixture"

    def __init__(self, inspector: FakeInspector) -> None:
        super().__init__(inspector)
        self.start_calls = 0
        self.cancel_calls: list[str] = []
        self.reattach_calls: list[tuple[object, object]] = []
        self.binding_calls: list[str] = []
        # run_id -> {"spec", "ref", "session"}: the durable receipt store
        self.durable: dict[str, dict] = {}

    async def start(self, spec):
        self.start_calls += 1
        logs = spec.run_dir / "logs"
        output = spec.run_dir / "output"
        logs.mkdir(mode=0o700, parents=True, exist_ok=True)
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        stdout = logs / "stdout.jsonl"
        stderr = logs / "stderr.log"
        result = output / "result.json"
        for path, payload in (
            (stdout, b'{"type":"turn.completed"}\n'),
            (stderr, b""),
            (result, b"{}\n"),
        ):
            path.write_bytes(payload)
            path.chmod(0o600)
        session = f"mcp:launch:{spec.run_id[:16]}"
        ref = self._provider_ref(spec, session)
        # the durable receipt: persisted BEFORE the start ACK returns
        self.durable[spec.run_id] = {"spec": spec, "ref": ref, "session": session}
        self.spec = spec
        self.ref = ref
        return ref

    def _provider_ref(self, spec, session):
        import os

        from control_plane.codex_worker import ProcessRef

        return ProcessRef(
            run_id=spec.run_id,
            pid=None,
            pgid=None,
            process_start_identity=None,
            boot_session_id=None,
            launch_nonce=f"nonce-{spec.run_id[:12]}",
            provider_session_id=session,
            stdout_path=str(spec.run_dir / "logs" / "stdout.jsonl"),
            stderr_path=str(spec.run_dir / "logs" / "stderr.log"),
            result_path=str(spec.run_dir / "output" / "result.json"),
            started_at="2026-11-11T00:00:00+00:00",
            binary=self.ref_binary(),
            base_sha="b" * 40,
            effective_uid=os.geteuid(),
            effective_gid=os.getegid(),
            real_uid=os.geteuid(),
            real_gid=os.getegid(),
        )

    @staticmethod
    def ref_binary():
        from control_plane.codex_worker import BinaryAttestation

        return BinaryAttestation(
            path="/fixture/codex", real_path="/fixture/codex",
            version="fixture-1", sha256="a" * 64, team_identifier="2DC432GLL2",
            size=1, device=1, inode=1, mode=0o755, uid=1, gid=1, mtime_ns=1,
        )

    def launch_receipt(self, run_id: str):
        entry = self.durable.get(str(run_id))
        if entry is None:
            return None
        class _Receipt:
            thread_id = entry["session"]
        return _Receipt()

    def receipt_recovery_binding(self, run_id: str, *, prompt_path):
        """The new adapter seam: rebuild the durable binding from the store."""
        self.binding_calls.append(str(run_id))
        entry = self.durable.get(str(run_id))
        if entry is None:
            return None
        return WorkerRecoveryBinding.bind(
            adapter_id=self.adapter_id,
            spec=entry["spec"],
            process_ref=entry["ref"],
            prompt_path=prompt_path,
        )

    def reattach(self, spec, binding):
        self.reattach_calls.append((spec, binding))
        assert binding.recover_launch_spec() == spec
        self.spec = spec
        self.ref = binding.process_ref
        return self.ref

    async def cancel(self, ref, reason):
        self.cancel_calls.append(reason)
        return await super().cancel(ref, reason)


def _receipt_reader(adapter: ReceiptCapableAdapter):
    def reader(attempt_id: str):
        entry = adapter.durable.get(str(attempt_id))
        if entry is None:
            return None
        return {"provider_session_id": entry["session"]}

    return reader


class ComposedBoundaryAdapter(ReceiptCapableAdapter):
    """The composed adapter surface the boundary projection wraps: the T3
    adapter's durable neutral refs plus an ASYNC reattach (the real adapter's
    shape; ``SupervisorBoundaryT3Adapter`` bridges sync-supervisor calls onto
    it) and ``retained_original_ref`` (the twin check's durable source).  The
    ref carries NO local identity (uid/gid included) — the real T3 shape the
    boundary's nulled attestation identity is compared against."""

    adapter_id = "t3-native"

    def _provider_ref(self, spec, session):
        import dataclasses

        return dataclasses.replace(
            super()._provider_ref(spec, session),
            effective_uid=None, effective_gid=None,
            real_uid=None, real_gid=None,
        )

    def retained_original_ref(self, run_id: str):
        entry = self.durable.get(str(run_id))
        return entry["ref"] if entry is not None else None

    async def reattach(self, spec, binding):
        ref = ReceiptCapableAdapter.reattach(self, spec, binding)
        assert ref == self.retained_original_ref(spec.run_id), (
            "the boundary must substitute the neutral retained ref")
        return ref


class _ComposedPresenceController(UnknownProcessController):
    """Mirrors T3NativeProcessController's presence law for this harness: an
    attempt carrying a durable ``worker_recovery_binding`` is TERMINAL_OWNED
    (recover through reattach); anything else is UNKNOWN."""

    def presence(self, attempt):
        if isinstance(attempt.launch_metadata.get("worker_recovery_binding"),
                      dict):
            return ProcessPresence.TERMINAL_OWNED
        return ProcessPresence.UNKNOWN


def _restart_supervisor(runtime, tmp_path, adapter, *, instance_id):
    supervisor = _supervisor(
        runtime, tmp_path, adapter,
        require_complete_launch_attestation=False,
        provider_receipt_reader=_receipt_reader(adapter),
    )
    supervisor.process_controller = _ComposedPresenceController()
    # a restarted door process composes a NEW supervisor instance; the claim
    # under reconciliation belongs to the dead predecessor
    supervisor.instance_id = instance_id
    return supervisor


def _crash_between_receipt_and_record(tmp_path, monkeypatch, *, lease_seconds=1,
                                      adapter_factory=ReceiptCapableAdapter,
                                      launcher_factory=None):
    """The L1B3-5 crash window, through the REAL start path.

    ``start_job`` claims, writes the prompt, calls ``adapter.start`` (the
    receipt is persisted), and dies — hard, BaseException-style — exactly at
    ``record_process``: no cancel, no failure terminal, identity-less claim.
    ``launcher_factory(runtime)`` overrides the crashing supervisor (the
    composed test passes the production composition, as the real door does).
    """
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(
        tmp_path, clock=clock, lease_seconds=lease_seconds)
    adapter = adapter_factory(FakeInspector())
    launcher = (
        launcher_factory(runtime) if launcher_factory is not None
        else _supervisor(runtime, tmp_path, adapter,
                         require_complete_launch_attestation=False)
    )

    def die_at_record_process(*_args, **_kwargs):
        raise SystemExit("door died between put_launch_receipt and record_process")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runtime.attempts, "record_process", die_at_record_process)
        with pytest.raises(SystemExit):
            asyncio.run(launcher.start_job(job_id))

    attempt = None
    for row in runtime.attempts.list_attempts():
        if row.job_id == job_id:
            attempt = row
    assert attempt is not None and attempt.status is owner.AttemptStatus.CLAIMED
    assert attempt.pid is None and attempt.provider_session_id is None
    assert adapter.start_calls == 1, "exactly one native launch happened"
    assert adapter.cancel_calls == [], "a hard crash must not cancel the run"
    return runtime, job_id, attempt.attempt_id, adapter, now


# ---------------------------------------------------------------------------
# finding 2: a live launcher is never fenced
# ---------------------------------------------------------------------------

class _CountingCancelAdapter(FakeAdapter):
    def __init__(self, inspector):
        super().__init__(inspector)
        self.cancel_calls: list[str] = []

    async def cancel(self, ref, reason):
        self.cancel_calls.append(reason)
        return await super().cancel(ref, reason)


def test_reconcile_between_receipt_and_record_never_fences_a_live_launcher(
        tmp_path):
    """The reviewer's finding-2 reproduction, asserting the fixed law: a
    foreign claimant's unexpired lease is deferred, the launcher's
    record_process succeeds on its ORIGINAL fence and token, and the only
    native run is never cancelled."""
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="live-launcher")
    adapter = _CountingCancelAdapter(FakeInspector())
    adapter.presence = lambda _a: ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _a: False
    supervisor = _supervisor(
        runtime, tmp_path, adapter,
        require_complete_launch_attestation=False,
        provider_receipt_reader=lambda _a: {"provider_session_id": "mcp:s"},
    )

    first = supervisor.reconcile_restart(requeue_lost=True)
    # the claim's lease belongs to a possibly-live launcher: deferred, never
    # rotated, never cleaned up, never requeued
    assert [item.status for item in first] == [ReconcileStatus.AWAITING_LEASE_EXPIRY]
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.fence_generation == lease.attempt.fence_generation
    assert row.lease_owner == "live-launcher"
    assert row.provider_session_id is None
    assert runtime.jobs.get_job(job_id).status is JobStatus.RUNNING

    # the launcher finishes normally: record_process under its own lease
    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="mcp:s",
    )
    assert adapter.cancel_calls == [], "the only native run must never be cancelled"


def test_reconcile_never_takes_its_own_in_flight_launch(tmp_path):
    """Finding 2's same-instance race: a periodic reconcile of THIS supervisor
    while its own start_job sits in the receipt/record_process window must
    defer, so the in-flight launch completes normally."""
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    # the supervisor claims with lease_owner=self.instance_id ("supervisor-fixture")
    lease = runtime.broker.claim(job_id, lease_owner="supervisor-fixture")
    adapter = _CountingCancelAdapter(FakeInspector())
    adapter.presence = lambda _a: ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _a: False
    supervisor = _supervisor(
        runtime, tmp_path, adapter,
        require_complete_launch_attestation=False,
        provider_receipt_reader=lambda _a: {"provider_session_id": "mcp:s"},
    )

    outcomes = supervisor.reconcile_restart(requeue_lost=True)
    assert [item.status for item in outcomes] == [ReconcileStatus.AWAITING_LEASE_EXPIRY]
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.fence_generation == lease.attempt.fence_generation
    assert row.lease_owner == "supervisor-fixture"

    runtime.attempts.record_process(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="mcp:s",
    )
    assert adapter.cancel_calls == []


def test_live_launcher_heartbeat_renews_the_lease_and_beats_expiry_adoption(
        tmp_path):
    """The deferral is bounded by the lease: a launcher that keeps heartbeating
    keeps its claim; the expired-lease adoption variant refuses a renewed
    lease (the in-transaction liveness proof)."""
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(tmp_path, clock=clock, lease_seconds=1)
    lease = runtime.broker.claim(job_id, lease_owner="live-launcher")
    now[0] += 800  # still inside the original window: the live launcher renews
    runtime.attempts.heartbeat_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    now[0] += 900  # past the ORIGINAL expiry, inside the renewed window

    with pytest.raises(StateConflict, match="renewed"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation,
            lease_owner="restart-supervisor",
            reattach_provider_session_id="mcp:s",
            adopt_expired_lease=True,
        )
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.lease_owner == "live-launcher"


# ---------------------------------------------------------------------------
# finding 1 + 7 (identity-less): full recovery under the receipt
# ---------------------------------------------------------------------------

def test_receipt_recovery_ends_with_a_run_somebody_owns(
        tmp_path, monkeypatch):
    """Finding 1: after the crash window and lease expiry, reconcile adopts
    under the receipt THROUGH THE FULL PATH — binding persisted in the same
    transaction, adapter reattach called, an ActiveRun handed out — and the
    attempt can still heartbeat and complete."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch)
    now[0] += 2_000  # door down longer than the lease (finding 7's premise)

    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")

    first = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in first] == [RECEIPT_RECOVERED]

    # a run somebody owns: the adopted lease was NOT dropped
    recovered = restarted.take_recovered_runs()
    assert len(recovered) == 1
    active = recovered[0]
    assert restarted.take_recovered_runs() == ()

    row = reopened.attempts.get_attempt(attempt_id)
    assert row.provider_session_id == adapter.durable[attempt_id]["session"]
    assert row.lease_owner == "supervisor-restarted"
    assert row.fence_generation > 1  # rotated to the recovering supervisor
    assert row.status is owner.AttemptStatus.CHECKPOINTED  # normalised
    binding = row.launch_metadata.get("worker_recovery_binding")
    assert isinstance(binding, dict), "the binding must land in the SAME transaction"
    assert binding["adapter_id"] == "receipt-fixture"
    assert row.stdout_path == adapter.durable[attempt_id]["ref"].stdout_path

    # the adapter reattached the SAME execution: zero new native launches
    assert adapter.start_calls == 1
    assert len(adapter.reattach_calls) == 1
    spec, passed_binding = adapter.reattach_calls[0]
    assert passed_binding.recover_launch_spec() == spec
    assert spec.run_id == attempt_id

    # the one-initiator invariant: same attempt, no requeue; the job stays
    # active in the recovered state (CHECKPOINTED) and completes below
    assert reopened.jobs.get_job(job_id).status is JobStatus.CHECKPOINTED
    attempts = [a for a in reopened.attempts.list_attempts() if a.job_id == job_id]
    assert len(attempts) == 1

    # the recovered lease is live: it can heartbeat and complete
    reopened.attempts.heartbeat_attempt(
        attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
    )
    reopened.attempts.complete_attempt(
        attempt_id,
        fence_generation=active.lease.attempt.fence_generation,
        lease_token=active.lease.lease_token,
        payload=JobPayload(summary="receipt-recovered run completed",
                           current_state="done"),
    )
    assert reopened.jobs.get_job(job_id).status is JobStatus.COMPLETED


def test_second_and_third_reconcile_passes_never_wedge(tmp_path, monkeypatch):
    """Finding 1's wedge: after receipt recovery, later passes of the SAME
    supervisor return ALREADY_RECOVERED — never IDENTITY_AMBIGUOUS."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch)
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")

    first = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in first] == [RECEIPT_RECOVERED]
    second = restarted.reconcile_restart(requeue_lost=True)
    third = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in second] == [ReconcileStatus.ALREADY_RECOVERED]
    assert [item.status for item in third] == [ReconcileStatus.ALREADY_RECOVERED]


def test_a_fresh_supervisor_recovers_the_receipt_adopted_attempt_normally(
        tmp_path, monkeypatch):
    """Finding 1's second wedge half: a THIRD supervisor (the door restarted
    again) must recover the receipt-adopted attempt through the ordinary
    binding path — TERMINAL_OWNED presence, full validation, no ambiguity."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch)
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")
    assert [item.status for item in restarted.reconcile_restart()] == [
        RECEIPT_RECOVERED]
    restarted.take_recovered_runs()

    # a later door restart: brand-new supervisor over the same durable state
    reopened2 = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    third = _supervisor(
        reopened2, tmp_path, adapter,
        require_complete_launch_attestation=False,
        provider_receipt_reader=_receipt_reader(adapter),
    )
    third.process_controller = _ComposedPresenceController()
    third.instance_id = "supervisor-third"
    outcomes = third.reconcile_restart(requeue_lost=True)
    assert [item.status for item in outcomes] == [
        ReconcileStatus.TERMINAL_RECOVERED], "never IDENTITY_AMBIGUOUS"
    recovered = third.take_recovered_runs()
    assert len(recovered) == 1
    assert adapter.start_calls == 1, "still exactly one native launch"
    assert len(adapter.reattach_calls) == 2  # restarted + third


def test_receipt_recovery_persists_binding_and_paths_atomically(
        tmp_path, monkeypatch):
    """Finding 1's evidence shape: the adoption transaction writes the
    provider identity, the recovery binding, the process paths and the launch
    metadata together — one fence rotation, typed events, nothing dropped."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch)
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")
    restarted.reconcile_restart(requeue_lost=True)

    row = reopened.attempts.get_attempt(attempt_id)
    ref = adapter.durable[attempt_id]["ref"]
    assert row.provider_session_id == ref.provider_session_id
    assert row.stdout_path == ref.stdout_path
    assert row.stderr_path == ref.stderr_path
    assert row.result_path == ref.result_path
    binding = row.launch_metadata["worker_recovery_binding"]
    stored = WorkerRecoveryBinding.from_dict(binding)
    assert stored.process_ref == ref
    attestation = row.launch_metadata["launch_attestation"]
    assert attestation["process_identity"]["pid"] is None
    events = reopened.store.list_events(attempt_id=attempt_id)
    types = [event.event_type for event in events]
    assert "ATTEMPT_PROCESS_RECORDED" in types
    assert "ATTEMPT_RECEIPT_ADOPTED" in types
    adopted_events = [event for event in events
                      if event.event_type == "ATTEMPT_RECEIPT_ADOPTED"]
    payload = dict(adopted_events[0].payload)
    assert payload["provider_session_id"] == ref.provider_session_id
    assert payload["previous_lease_owner"] == "supervisor-fixture"
    assert payload["lease_expired"] is True


def test_receipt_deferral_without_lease_expiry_never_requeues(tmp_path,
                                                              monkeypatch):
    """Finding 2 + 7 boundary: while the lease is fresh the receipt-bearing
    claim is deferred; the receipt still forbids expiry-requeue (one launch
    total), and adoption happens at expiry through the full path."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch, lease_seconds=30)

    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=30)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")
    early = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in early] == [ReconcileStatus.AWAITING_LEASE_EXPIRY]
    row = reopened.attempts.get_attempt(attempt_id)
    assert row.provider_session_id is None, "no adoption before expiry"
    attempts = [a for a in reopened.attempts.list_attempts() if a.job_id == job_id]
    assert len(attempts) == 1, "no requeue while deferred"

    now[0] += 31_000  # the lease expires; adoption becomes lawful
    late = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in late] == [RECEIPT_RECOVERED]
    assert adapter.start_calls == 1
    attempts = [a for a in reopened.attempts.list_attempts() if a.job_id == job_id]
    assert len(attempts) == 1, "expiry of a receipt claim never requeues"


def test_adapter_without_the_binding_seam_quarantines_typed(tmp_path,
                                                            monkeypatch):
    """An adapter that cannot reconstruct a recovery binding from its receipt
    fails typed and conservative: quarantined, owned, never requeued."""
    (runtime, job_id, attempt_id, adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch)
    monkeypatch.delattr(ReceiptCapableAdapter, "receipt_recovery_binding")
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    restarted = _restart_supervisor(
        reopened, tmp_path, adapter, instance_id="supervisor-restarted")
    outcomes = restarted.reconcile_restart(requeue_lost=True)
    assert [item.status for item in outcomes] == [ReconcileStatus.LIVE_QUARANTINED]
    assert "receipt_recovery_binding" in (outcomes[0].error or "")
    row = reopened.attempts.get_attempt(attempt_id)
    assert row.provider_session_id is None  # no partial adoption
    attempts = [a for a in reopened.attempts.list_attempts() if a.job_id == job_id]
    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# finding 7 (recorded identity): one expired-lease recovery path
# ---------------------------------------------------------------------------

def test_bound_attempt_with_expired_lease_recovers_the_same_attempt(
        tmp_path):
    """Finding 7 for a recorded attempt (crash AFTER record_process): door
    down longer than the lease; restart reconcile recovers the SAME attempt
    through the existing binding path — no quarantine, no requeue, no second
    launch."""
    from tests.test_executive_supervisor import RestartCapableFakeAdapter

    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(tmp_path, clock=clock, lease_seconds=1)
    inspector = FakeInspector()
    first_adapter = RestartCapableFakeAdapter(inspector)
    active = asyncio.run(
        _supervisor(runtime, tmp_path, first_adapter).start_job(job_id))
    now[0] += 2_000  # door down past the lease

    reopened = Runtime.at(tmp_path, clock=clock, lease_seconds=1)
    second_adapter = RestartCapableFakeAdapter(inspector)
    restarted = _supervisor(reopened, tmp_path, second_adapter)
    outcomes = restarted.reconcile_restart(requeue_lost=True)

    assert [item.status for item in outcomes] == [ReconcileStatus.LIVE_RECOVERED]
    assert restarted.process_controller.terminated_attempt_ids == []
    recovered = restarted.take_recovered_runs()
    assert len(recovered) == 1
    assert second_adapter.start_calls == 0, "the same attempt, no relaunch"
    persisted = reopened.attempts.get_attempt(active.lease.attempt.attempt_id)
    assert persisted is not None
    assert persisted.status is owner.AttemptStatus.CHECKPOINTED
    assert persisted.attempt_id == recovered[0].lease.attempt.attempt_id
    attempts = [a for a in reopened.attempts.list_attempts() if a.job_id == job_id]
    assert len(attempts) == 1, "no requeue after long downtime"
    receipt = asyncio.run(restarted.finish_job(recovered[0]))
    assert receipt.job.status is JobStatus.COMPLETED
    assert second_adapter.start_calls == 0


# ---------------------------------------------------------------------------
# the runtime primitive: the expired-lease variant and the named owner
# ---------------------------------------------------------------------------

def test_expired_lease_adoption_still_refuses_by_default(tmp_path):
    """The pre-existing refusal is not weakened: without the explicit expired
    variant, adopt_attempt refuses an expired lease."""
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(tmp_path, clock=clock, lease_seconds=1)
    lease = runtime.broker.claim(job_id, lease_owner="dead")
    now[0] += 2_000  # the lease expires
    with pytest.raises(StateConflict, match="lease has expired; reconcile it first"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation,
            lease_owner="restart-supervisor",
            reattach_provider_session_id="mcp:s",
        )


def test_expired_lease_variant_adopts_and_renews(tmp_path):
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(tmp_path, clock=clock, lease_seconds=1)
    lease = runtime.broker.claim(job_id, lease_owner="dead")
    now[0] += 2_000
    adopted = runtime.attempts.adopt_attempt(
        lease.attempt.attempt_id,
        expected_fence_generation=lease.attempt.fence_generation,
        lease_owner="restart-supervisor",
        reattach_provider_session_id="mcp:s",
        expected_lease_owner="dead",
        adopt_expired_lease=True,
    )
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert row.lease_owner == "restart-supervisor"
    assert row.provider_session_id == "mcp:s"
    from datetime import datetime, timezone

    assert datetime.fromisoformat(
        row.lease_expires_at.replace("Z", "+00:00")
    ) > datetime.fromtimestamp(now[0] / 1000, tz=timezone.utc)
    assert adopted.lease_token != lease.lease_token


def test_adoption_names_the_displaced_owner(tmp_path):
    """The receipt path names the owner it displaces; a different actual owner
    is a typed refusal (nobody adopts a claim that changed hands)."""
    now = [1_800_000_000_000]
    clock = lambda: now[0]
    runtime, job_id, _ = _runtime_and_job(tmp_path, clock=clock, lease_seconds=1)
    lease = runtime.broker.claim(job_id, lease_owner="dead")
    now[0] += 2_000
    with pytest.raises(StateConflict, match="owner"):
        runtime.attempts.adopt_attempt(
            lease.attempt.attempt_id,
            expected_fence_generation=lease.attempt.fence_generation,
            lease_owner="restart-supervisor",
            reattach_provider_session_id="mcp:s",
            expected_lease_owner="someone-else",
            adopt_expired_lease=True,
        )


# ---------------------------------------------------------------------------
# the composed production owner recovers the same way
# ---------------------------------------------------------------------------

def test_the_composed_t3_native_supervisor_recovers_the_receipt_claim(
        tmp_path, monkeypatch):
    """The composed production owner (``compose_t3_native_supervisor``:
    boundary projection + T3NativeProcessController + the wired receipt
    reader) recovers an identity-less receipt claim end-to-end — defer while
    the lease is live, adopt at expiry THROUGH the boundary seam, and a later
    door restart recovers the SAME attempt through the ordinary binding path.
    """
    from types import SimpleNamespace

    from control_plane.t3_native_composition import compose_t3_native_supervisor

    adapter = ComposedBoundaryAdapter(FakeInspector())
    composed = None

    def _compose(runtime_handle, *, instance_id):
        nonlocal composed
        primary = _supervisor(runtime_handle, tmp_path, adapter,
                              require_complete_launch_attestation=False)
        composed = compose_t3_native_supervisor(
            primary, SimpleNamespace(composed=True, adapter=adapter),
            runs_root=tmp_path / "runs",
            isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        )
        composed.instance_id = instance_id
        return composed

    # the crash: the DOOR's own composed supervisor dies in the window (the
    # production shape — launch and reconcile go through the same composition)
    (runtime, job_id, attempt_id, _adapter, now) = _crash_between_receipt_and_record(
        tmp_path, monkeypatch,
        adapter_factory=lambda _inspector: adapter,
        launcher_factory=lambda runtime_handle: _compose(
            runtime_handle, instance_id="composed-launcher"),
    )
    assert _adapter is adapter

    # while the lease is live the composed owner defers (finding 2)
    live = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    assert [item.status for item in
            _compose(live, instance_id="composed-live").reconcile_restart(
                requeue_lost=True)] == [ReconcileStatus.AWAITING_LEASE_EXPIRY]

    # door down longer than the lease: adopt through the boundary seam
    now[0] += 2_000
    reopened = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    first = _compose(reopened, instance_id="composed-restart").reconcile_restart(
        requeue_lost=True)
    assert [item.status for item in first] == [RECEIPT_RECOVERED]
    recovered = composed.take_recovered_runs()
    assert len(recovered) == 1
    assert adapter.start_calls == 1, "still exactly one native launch"
    assert len(adapter.reattach_calls) == 1
    row = reopened.attempts.get_attempt(attempt_id)
    persisted_binding = row.launch_metadata.get("worker_recovery_binding")
    assert persisted_binding["adapter_id"] == "t3-native"
    assert row.provider_session_id == adapter.durable[attempt_id]["session"]

    # a later door restart: the T3NativeProcessController answers
    # TERMINAL_OWNED for the bound row and the ordinary path recovers it
    reopened2 = Runtime.at(tmp_path, clock=lambda: now[0], lease_seconds=1)
    outcomes = _compose(reopened2, instance_id="composed-third").reconcile_restart(
        requeue_lost=True)
    assert [item.status for item in outcomes] == [
        ReconcileStatus.TERMINAL_RECOVERED], "never IDENTITY_AMBIGUOUS"
    assert len(composed.take_recovered_runs()) == 1
    assert adapter.start_calls == 1
    assert len(adapter.reattach_calls) == 2
    attempts = [a for a in reopened2.attempts.list_attempts()
                if a.job_id == job_id]
    assert len(attempts) == 1, "no requeue, no second attempt"


def test_boundary_projection_twins_and_refuses_a_foreign_receipt_binding(
        tmp_path):
    """The boundary wrapper is fail-closed: it hands the supervisor the twin
    of the durable retained ref, and a receipt binding whose ref is NOT the
    retained one refuses typed, never translates."""
    import dataclasses
    from pathlib import Path

    from control_plane.t3_native_composition import (
        SupervisorBoundaryT3Adapter,
        T3NativeCompositionError,
    )
    from control_plane.worker_execution_contract import WorkerLaunchSpec

    run_dir = tmp_path / "run-b"
    (run_dir / "input").mkdir(parents=True)
    prompt_path = run_dir / "input" / "worker-prompt.txt"
    prompt_path.write_text("do the work")
    prompt_path.chmod(0o600)
    spec = WorkerLaunchSpec(
        run_id="run-b", job_id="jobs/77", worker_id="workers/12",
        workspace_path=tmp_path / "ws", run_dir=run_dir,
        prompt="do the work", model="glm-5.3",
        result_schema_path=run_dir / "input" / "schema.json",
    )

    def _populate(adapter):
        ref = adapter._provider_ref(spec, "mcp:s")
        adapter.durable["run-b"] = {"spec": spec, "ref": ref, "session": "mcp:s"}
        return ref

    honest = ComposedBoundaryAdapter(FakeInspector())
    retained = _populate(honest)
    boundary = SupervisorBoundaryT3Adapter(honest)
    assert boundary.receipt_recovery_binding(
        "run-never", prompt_path=str(prompt_path)) is None
    binding = boundary.receipt_recovery_binding(
        "run-b", prompt_path=str(prompt_path))
    assert binding.process_ref == retained

    class _LyingInner(ComposedBoundaryAdapter):
        def receipt_recovery_binding(self, run_id, *, prompt_path):
            built = ComposedBoundaryAdapter.receipt_recovery_binding(
                self, run_id, prompt_path=prompt_path)
            if built is None:
                return None
            forged = dataclasses.replace(
                self.durable[str(run_id)]["ref"], launch_nonce="nonce-forged")
            return dataclasses.replace(built, process_ref=forged)

    lying = _LyingInner(FakeInspector())
    _populate(lying)
    with pytest.raises(T3NativeCompositionError, match="retained"):
        SupervisorBoundaryT3Adapter(lying).receipt_recovery_binding(
            "run-b", prompt_path=str(prompt_path))
