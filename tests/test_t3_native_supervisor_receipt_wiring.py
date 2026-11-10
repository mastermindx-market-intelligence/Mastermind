"""F12 (attack review): the L1B3-5 provider-receipt reattach path is real in
the COMPOSED supervisor, not only in tests.

``compose_t3_native_supervisor`` must wire a ``provider_receipt_reader`` over
the composed adapter's durable launch receipts, so an identity-less claim
left by a crash between the persisted receipt and ``record_process`` is
adopted under its receipt by the production composition — never expired and
requeued into a second launch.

Run: TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
     -p no:cacheprovider tests/test_t3_native_supervisor_receipt_wiring.py
"""
from types import SimpleNamespace

import control_plane.executive_supervisor as owner
from control_plane.t3_native_composition import compose_t3_native_supervisor
from tests.test_executive_supervisor import (
    FakeAdapter,
    FakeInspector,
    FakeProcessController,
    _runtime_and_job,
    _supervisor,
)

RECEIPT_SESSION = "mcp:launch:9f31c0d2ae45b7c8d1e6f0a3b2c4d5e6f7a8b9c0"


def _primary(runtime, tmp_path):
    """The composed supervisor's primary: a real same-runtime supervisor
    (project_input_owner is validated to be the original same-service
    owner)."""
    return _supervisor(runtime, tmp_path, FakeAdapter(FakeInspector()))


class _ReceiptAdapter:
    """The composed adapter's durable surface: launch receipts + the
    presence probes reconcile uses (all UNKNOWN for an identity-less row)."""

    def __init__(self, receipts: dict[str, str]):
        self._receipts = receipts
        self.inspector = FakeInspector()

    def launch_receipt(self, run_id: str):
        session = self._receipts.get(str(run_id))
        if not session:
            return None
        return SimpleNamespace(thread_id=session)

    def presence(self, _attempt):
        return owner.ProcessPresence.UNKNOWN

    def absence_verified(self, _attempt) -> bool:
        return False

    def terminate(self, _attempt):
        raise AssertionError("an identity-less claim must not be signalled")


def test_composed_supervisor_adopts_an_identity_less_claim_under_its_receipt(
        tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="dead-original-owner")
    attempt_id = lease.attempt.attempt_id
    assert lease.attempt.provider_session_id is None  # the L1B3-5 window

    composition = SimpleNamespace(
        composed=True,
        adapter=_ReceiptAdapter({attempt_id: RECEIPT_SESSION}),
    )
    primary = _primary(runtime, tmp_path)
    supervisor = compose_t3_native_supervisor(
        primary, composition,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        process_controller=FakeProcessController(FakeInspector()),
    )
    outcomes = supervisor.reconcile_restart(requeue_lost=True)

    # with the wiring: adopted under the receipt, execution preserved
    assert [item.status for item in outcomes] == [
        owner.ReconcileStatus.LIVE_QUARANTINED]
    row = runtime.attempts.get_attempt(attempt_id)
    assert row.provider_session_id == RECEIPT_SESSION
    assert row.lease_owner == supervisor.instance_id
    # the one-initiator invariant: one attempt, job RUNNING, no requeue
    assert runtime.jobs.get_job(job_id).status is owner.JobStatus.RUNNING
    attempts = [a for a in runtime.attempts.list_attempts()
                if a.job_id == job_id]
    assert len(attempts) == 1


def test_the_wired_reader_ignores_an_unreadable_or_absent_receipt(tmp_path):
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="dead-original-owner")
    attempt_id = lease.attempt.attempt_id

    class _ExplodingAdapter(_ReceiptAdapter):
        def launch_receipt(self, run_id: str):
            raise RuntimeError("store unreadable")

    composition = SimpleNamespace(composed=True,
                                  adapter=_ExplodingAdapter({}))
    primary = _primary(runtime, tmp_path)
    supervisor = compose_t3_native_supervisor(
        primary, composition,
        runs_root=tmp_path / "runs",
        isolation_roots=(tmp_path / "workspaces", tmp_path / "runs"),
        process_controller=FakeProcessController(FakeInspector()),
    )
    outcomes = supervisor.reconcile_restart(requeue_lost=True)
    # an unreadable receipt is NO receipt: the pre-existing quarantine holds
    assert [item.status for item in outcomes] == [
        owner.ReconcileStatus.IDENTITY_AMBIGUOUS]
    row = runtime.attempts.get_attempt(attempt_id)
    assert row.provider_session_id is None
    assert row.lease_owner == "dead-original-owner"
