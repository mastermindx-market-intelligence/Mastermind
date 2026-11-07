"""Select an existing execution owner after one canonical Runtime claim.

This in-process composition has no queue, lease store, admission or host grant.
The supplied Supervisors retain preparation, START, finishing and recovery.
Physical Fabric binding, foreground lifetime and host qualification remain
their existing owners' obligations; this module enables no execution profile.
"""
from __future__ import annotations

import asyncio
from types import MappingProxyType
from typing import Mapping

from control_plane.executive_runtime import AttemptLease, AttemptStatus, RuntimeProofError
from control_plane.executive_supervisor import (
    ActiveRun, ExecutiveSupervisor, ReconcileReceipt, ReconcileStatus,
    SupervisorError, _ACTIVE_ATTEMPT_STATUSES, _require_exact_worker_target,
)
from control_plane.worker_adapter import _implementation_adapter_id


async def _drain_original(task):
    """Retain one already owned operation through caller cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


class _ForegroundCustody:
    """Observe the actual origin; request only its canonical Attempt's cancel."""
    def __init__(self, runtime, operation, lease):
        self.runtime, self.operation, self.lease = runtime, operation, lease
        self.requested = False
        self.error = None
        self.monitor = asyncio.create_task(self._observe())

    def request_cancel(self):
        if self.requested:
            return
        self.requested = True
        attempt = self.lease.attempt
        try:
            self.runtime.jobs.cancel_job(attempt.job_id,
                expected_attempt_id=attempt.attempt_id,
                expected_fence_generation=attempt.fence_generation)
        except Exception as exc:
            # No alternate signal/lease action. The original owner must still
            # drain; its caller receives this unresolved cancellation after it.
            self.error = self.error or exc

    async def _observe(self):
        try:
            await self.operation.wait_closed()
        except Exception as exc:
            self.error = exc
        self.request_cancel()

    async def close(self):
        # This cancels only a liveness observer, never the controller/collector.
        self.monitor.cancel()
        values = await _drain_original(asyncio.ensure_future(
            asyncio.gather(self.monitor, return_exceptions=True)))
        if values and isinstance(values[0], Exception):
            self.error = self.error or values[0]

    def require_settled(self):
        if self.error is not None:
            raise SupervisorError("original foreground cancellation remains unresolved") from self.error


class MixedExecutionOwnerSupervisor:
    def __init__(self, primary: ExecutiveSupervisor,
                 owners: Mapping[str, ExecutiveSupervisor], *, initial_admission=None):
        if type(primary) is not ExecutiveSupervisor or not owners:
            raise SupervisorError("mixed composition requires existing Supervisors")
        if any(type(key) is not str or not key or type(owner) is not ExecutiveSupervisor
               or owner.runtime is not primary.runtime
               or owner.instance_id != primary.instance_id
               for key, owner in owners.items()):
            raise SupervisorError("mixed owners must share the exact Runtime and service instance")
        if not any(owner is primary for owner in owners.values()):
            raise SupervisorError("mixed composition must retain its original planner owner")
        from control_plane.finite_initial_admission import FiniteInitialAdmission
        if initial_admission is not None and type(initial_admission) is not FiniteInitialAdmission:
            raise SupervisorError('finite initial source must be the actual typed owner')
        self._initial_admission = initial_admission
        self.primary = primary
        self.runtime = primary.runtime
        self.instance_id = primary.instance_id
        self.owners = MappingProxyType(dict(owners))
        # Transient ActiveRun custody, not a second execution lifecycle. Durable
        # restart authority remains the canonical Attempt/recovery binding.
        self._active: dict[str, tuple[ExecutiveSupervisor, ActiveRun, _ForegroundCustody | None]] = {}
        self._starting: set[str] = set()
        self._unsettled: dict[str, tuple[ExecutiveSupervisor, ActiveRun]] = {}
        self._pending_recovery: dict[str, tuple[ExecutiveSupervisor, ActiveRun]] = {}

    def activate_primary_canary(self, verdict):
        """Qualify only the dedicated primary; Fabric probes remain per Attempt."""
        from control_plane.codex_worker import validate_secret_canary_verdict
        validated = validate_secret_canary_verdict(verdict, require_passed=True)
        self.primary.secret_canary_verdict = validated
        self.primary.require_complete_launch_attestation = True

    def _select(self, attempt) -> ExecutiveSupervisor:
        owner = self.owners.get(attempt.worker_id)
        worker = self.runtime.workers.get_worker(attempt.worker_id)
        quota = self.runtime.workers.get_quota_class(attempt.worker_id, attempt.quota_class)
        job = self.runtime.jobs.get_job(attempt.job_id)
        if (owner is None or worker is None or quota is None or job is None
                or job.current_attempt_id != attempt.attempt_id
                or quota.active_attempt_id != attempt.attempt_id
                or attempt.execution_mode == "OPERATOR_HARNESS"):
            raise SupervisorError("claimed Attempt has no exact execution owner")
        if (worker.worker_type != _implementation_adapter_id(owner.adapter)
                or quota.provider != worker.provider
                or job.constraints.get("provider", worker.provider) != worker.provider):
            raise SupervisorError("claimed Worker/provider differs from execution owner")
        for key in ("execution_profile_id", "execution_profile_digest",
                    "capability_policy_version", "capability_policy_digest"):
            if job.constraints.get(key) != quota.metadata.get(key):
                raise SupervisorError("claimed quota execution profile drifted")
        return owner

    def _foreground(self, job_id):
        job = self.runtime.jobs.get_job(job_id)
        if job is None:
            raise SupervisorError("mixed dispatch Job is unavailable")
        if "attended_route" not in job.constraints:
            return None
        # This lazy import intentionally refuses until the separately reviewed
        # native source is composed. A bool/caller DTO is never a substitute.
        try:
            from control_plane.foreground_operation import current_foreground_operation
            operation = current_foreground_operation()
            operation.require_root(job.root_job_id)
            if not callable(getattr(operation, "wait_closed", None)):
                raise SupervisorError("attended execution lacks its originating close signal")
        except ImportError as exc:
            raise SupervisorError("attended foreground source is not composed") from exc
        return operation

    def _retain(self, owner, active, custody=None):
        if type(active) is not ActiveRun:
            raise SupervisorError("execution owner returned no canonical ActiveRun")
        key = active.lease.attempt.attempt_id
        if key in self._active:
            raise SupervisorError("the original Attempt already has a retained finisher")
        self._active[key] = (owner, active, custody)
        return active

    async def _start(self, owner, job_id, lease, operation, *, target=None):
        key = lease.attempt.attempt_id
        if (lease.attempt.status is not AttemptStatus.CLAIMED
                or key in self._active or key in self._starting or key in self._unsettled):
            raise SupervisorError("original Attempt already has a launch or finisher owner")
        self._starting.add(key)
        try:
            return await self._start_owned(owner, job_id, lease, operation, target=target)
        finally:
            self._starting.discard(key)

    async def _start_owned(self, owner, job_id, lease, operation, *, target=None):
        if operation is not None:
            operation.require_root(self.runtime.jobs.get_job(job_id).root_job_id)
        custody = (_ForegroundCustody(self.runtime, operation, lease)
                   if operation is not None else None)
        start = owner._start_claimed_job(job_id, lease,
            **({"exact_target": target} if target is not None else {}))
        if custody is None:
            return self._retain(owner, await start)
        task = asyncio.create_task(start)
        active = None
        try:
            active = await asyncio.shield(task)
            return self._retain(owner, active, custody)
        except asyncio.CancelledError:
            # START may already have crossed its effect boundary. Keep its
            # original response/containment owner; never cancel or replace it.
            custody.request_cancel()
            try:
                active = await _drain_original(task)
                await _drain_original(asyncio.create_task(owner.finish_job(active)))
            finally:
                await custody.close()
            raise
        except BaseException:
            if type(active) is ActiveRun:
                self._unsettled[lease.attempt.attempt_id] = (owner, active)
                custody.request_cancel()
                try:
                    await _drain_original(asyncio.create_task(owner.finish_job(active)))
                finally:
                    await custody.close()
            else:
                await custody.close()
            raise

    async def start_cycle_job(self, job_id: str, *, command_id: str):
        job = self.runtime.jobs.get_job(job_id)
        initial = (self._initial_admission if job is not None and "attended_route" in job.constraints else None)
        operation = self._foreground(job_id) if initial is None else None
        target = (self.primary._exact_target_provider(job_id)
                  if self.primary._exact_target_provider is not None else None)
        if target is not None:
            target = _require_exact_worker_target(target)
        if initial is not None:
            outcome = await initial.dispatch(self.runtime,job_id,command_id,lease_owner=self.instance_id,exact_target=target)
        else:
            outcome = self.runtime.attempts.dispatch_cycle_job(
                job_id, command_id=command_id, lease_owner=self.instance_id,
                **({"exact_target": target} if target is not None else {}))
        if outcome is None:
            raise SupervisorError(f"no eligible worker capacity for {job_id}")
        # In particular, a CLAIMED replay without an exact target must not
        # invoke START again. Only the original fresh claim can reach it.
        if (not outcome.claimed_now or outcome.outcome == "TERMINAL"
                or outcome.attempt.status is not AttemptStatus.CLAIMED):
            return outcome
        if outcome.lease_token is None:
            raise SupervisorError("active dispatch lost its original lease")
        if initial is not None:
            operation = self._foreground(job_id)
        owner = self._select(outcome.attempt)
        return await self._start(owner, job_id,
            AttemptLease(outcome.attempt, outcome.lease_token), operation, target=target)

    async def start_job(self, job_id: str):
        operation = self._foreground(job_id)
        lease = self.runtime.broker.claim(job_id, lease_owner=self.instance_id)
        if lease is None:
            raise SupervisorError(f"no eligible worker capacity for {job_id}")
        owner = self._select(lease.attempt)
        return await self._start(owner, job_id, lease, operation)

    async def finish_job(self, active: ActiveRun):
        key = active.lease.attempt.attempt_id
        retained = self._active.get(key)
        if retained is None or retained[1] is not active:
            raise SupervisorError("finisher must use its original owner and ActiveRun")
        # Remove before await: concurrent/failed retries cannot recollect. A
        # failed original finisher keeps its canonical Attempt for recovery.
        owner, _, custody = self._active.pop(key)
        if custody is None:
            try:
                return await owner.finish_job(active)
            except BaseException:
                self._unsettled[key] = (owner, active)
                raise
        task = asyncio.create_task(owner.finish_job(active))
        try:
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                custody.request_cancel()
                await _drain_original(task)
                raise
        except BaseException:
            self._unsettled[key] = (owner, active)
            raise
        finally:
            await custody.close()
        custody.require_settled()
        return result

    def reconcile_restart(self, *, requeue_lost: bool = True):
        outcomes = []
        scopes: dict[ExecutiveSupervisor, set[str]] = {}
        for attempt in self.runtime.attempts.list_attempts():
            if (attempt.status not in _ACTIVE_ATTEMPT_STATUSES
                    or attempt.execution_mode == "OPERATOR_HARNESS"):
                continue
            try:
                owner = self._select(attempt)
                job = self.runtime.jobs.get_job(attempt.job_id)
                if "attended_route" in job.constraints:
                    # A restart cannot restore the originating live request.
                    # Existing recovery owns containment, never resumed work.
                    self.runtime.jobs.cancel_job(attempt.job_id,
                        expected_attempt_id=attempt.attempt_id,
                        expected_fence_generation=attempt.fence_generation)
            except (SupervisorError, ValueError, RuntimeProofError) as exc:
                outcomes.append(ReconcileReceipt(attempt_id=attempt.attempt_id,
                    job_id=attempt.job_id, status=ReconcileStatus.IDENTITY_AMBIGUOUS,
                    process_was_live=False, error=str(exc)))
                continue
            scopes.setdefault(owner, set()).add(attempt.attempt_id)
        for owner, ids in scopes.items():
            outcomes.extend(owner.reconcile_restart(requeue_lost=requeue_lost,
                                                    attempt_ids=frozenset(ids)))
        return outcomes

    def take_recovered_runs(self):
        for owner in dict.fromkeys(self.owners.values()):
            for active in owner.take_recovered_runs():
                key = active.lease.attempt.attempt_id
                # Retain before validation. One bad later row must not discard
                # earlier drained handles when the caller quarantines startup.
                existing = self._pending_recovery.get(key)
                if existing is not None and (existing[0] is not owner or existing[1] is not active):
                    raise SupervisorError("conflicting recovered Attempt owners")
                self._pending_recovery[key] = (owner, active)
        for key, (owner, active) in self._pending_recovery.items():
            if self._select(active.lease.attempt) is not owner or key in self._active:
                raise SupervisorError("recovered Attempt changed execution owner")
        result = [self._retain(owner, active) for owner, active in self._pending_recovery.values()]
        self._pending_recovery.clear()
        return tuple(result)
