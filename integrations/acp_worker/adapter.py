"""ACP-to-common-worker binding; native process ownership stays with the broker.

The trusted host composition supplies open_run at construction, never in a Job.
This module does not launch, signal, select accounts, register routes or persist
another lifecycle. Its native resource factory remains an installation gate.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from control_plane.codex_worker import (
    _MAX_SCHEMA_BYTES, _git_changed_paths, _git_snapshot, _read_limited, validate_json_schema,
)
from control_plane.executive_worker_broker import (
    BrokerEffectUnknownError, BrokerProtocolError, BrokerStateError,
)
from control_plane.worker_execution_contract import (
    CancelReceipt, CollectionReceipt, ProcessInspector, ValidationReceipt,
    WorkerLaunchSpec, WorkerProcessRef, WorkerResult, WorkerRunStatus,
)
from integrations.acp_worker.turn import (
    AcpCandidate, AcpProfile, AcpReadOnlyTurn, _nonfinite, _object_pairs,
)
from scripts.ohf.acp_probe_boundary import ProbeClient, ProbeLimits

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUN_LIMIT = 32


class _TurnFrameGuard(ProbeClient):
    def __init__(self, turn: AcpReadOnlyTurn) -> None:
        super().__init__(ProbeLimits())
        self._turn = turn

    def poison(self, reason: str) -> None:
        super().poison(reason)
        self._turn._refuse("ACP_FRAME_BOUNDARY_REFUSED")

    def _callback_allowed(self, session_id: str) -> bool:
        if self.violation is not None:
            return False
        if session_id != self.session_id:
            self.poison("SESSION_MISMATCH")
            return False
        if not self._active:
            caller = inspect.currentframe()
            caller = caller.f_back if caller is not None else None
            setup_update = (
                self._turn._phase == "setup"
                and caller is not None
                and (
                    caller.f_code.co_name == "session_update"
                    or caller.f_locals.get("method") == "session/update"
                )
            )
            if not setup_update:
                self.poison("CALLBACK_OUTSIDE_PROMPT")
                return False
        return True

    def admit_update(self, update: Any) -> int:
        # Structural bounds remain in StrictFrameReader. The typed production
        # turn applies the phase/session-aware read-only policy below.
        self._turn.validate_update(update, commit=False)
        if self._turn._error:
            raise ValueError(self._turn._error)
        return 0


@dataclasses.dataclass(frozen=True)
class AcpProcessCompletion:
    """Trusted source-owner observation, never provider/wire supplied.

    Settled requires original process, captured pipes and owned tasks to settle
    under the existing process owner's law. Protocol completion is insufficient.
    Hashes describe that owner's captured stdout/stderr, not parsed result JSON.
    """
    process_ref: WorkerProcessRef
    exit_code: int | None
    finished_at: str
    stdout_sha256: str
    stderr_sha256: str
    settled: bool
    cancellation: CancelReceipt | None = None


@dataclasses.dataclass(frozen=True)
class AcpRunResources:
    """Exclusive generation resources from an admitted native owner.

    Finish is that owner's bounded settlement operation, not a shell command.
    This value does not implement or grant native launch/isolation authority.
    """
    process_ref: WorkerProcessRef
    writer: asyncio.StreamWriter
    reader: asyncio.StreamReader
    launch_attestation: Any
    result_schema: Any
    finish: Callable[[str | None], Awaitable[AcpProcessCompletion]]


@dataclasses.dataclass
class _Run:
    spec: WorkerLaunchSpec
    resources: AcpRunResources
    baseline: Any
    schema: Any
    turn: AcpReadOnlyTurn
    cancelled: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    cancel_reason: str | None = None
    task: asyncio.Task[CollectionReceipt] | None = None
    finish_task: asyncio.Task[AcpProcessCompletion] | None = None
    completion: AcpProcessCompletion | None = None
    candidate: AcpCandidate | None = None
    receipt: CollectionReceipt | None = None
    uncertain: bool = False


class AcpWorkerAdapter:
    """Common broker operations for one fixed, privately constructed ACP lane.

    The native production factory and provider qualification remain prerequisites.
    Tests may inject a fixture owner without registering a production descriptor.
    """
    def __init__(self, profile: AcpProfile, *, inspector: ProcessInspector,
                 open_run: Callable[[WorkerLaunchSpec], Awaitable[AcpRunResources]]) -> None:
        if not callable(open_run):
            raise ValueError("ACP native resource owner is required")
        self.profile, self.inspector, self._open_run = profile, inspector, open_run
        self._runs: dict[str, _Run] = {}
        self._opening: asyncio.Task[AcpRunResources] | None = None
        self._active: str | None = None
        self._quarantined = False

    @property
    def unsettled_tasks(self) -> tuple[asyncio.Task[Any], ...]:
        tasks = [self._opening] if self._opening is not None else []
        for run in self._runs.values():
            tasks.extend(t for t in (run.task, run.finish_task) if t is not None)
            tasks.extend(run.turn.unsettled_tasks)
        return tuple(t for t in tasks if not t.done())

    @staticmethod
    def _observe(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()

    @staticmethod
    async def _bounded(task: asyncio.Task[Any], seconds: float) -> Any:
        done, _ = await asyncio.wait({task}, timeout=seconds)
        if not done:
            raise BrokerEffectUnknownError("ACP owner settlement remains unresolved")
        return task.result()

    def _run_for(self, ref: WorkerProcessRef) -> _Run:
        run = self._runs.get(ref.run_id)
        if run is None or run.resources.process_ref != ref:
            raise BrokerStateError("unknown or altered ACP process reference")
        return run

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef:
        AcpReadOnlyTurn.validate_spec(spec)
        if (self._quarantined or self._opening is not None or self._active is not None
                or spec.run_id in self._runs or len(self._runs) >= _RUN_LIMIT):
            raise BrokerStateError("ACP lane is busy, previously used, or unresolved")
        try:
            baseline = _git_snapshot(spec.workspace_path, require_clean=True)
        except Exception:
            raise BrokerProtocolError("ACP workspace preflight refused") from None
        if spec.expected_base_sha is None or baseline.head != spec.expected_base_sha:
            raise BrokerProtocolError("ACP workspace base is not exactly bound")
        try:
            if not spec.result_schema_path.resolve(strict=True).is_relative_to(spec.run_dir.resolve(strict=True)):
                raise ValueError
            schema = json.loads(_read_limited(spec.result_schema_path, _MAX_SCHEMA_BYTES),
                object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
            if not isinstance(schema, (dict, bool)):
                raise ValueError
        except Exception:
            raise BrokerProtocolError("ACP admitted result schema is invalid") from None
        task = asyncio.create_task(self._open_run(spec))
        task.add_done_callback(self._observe)
        self._opening = task
        try:
            resources = await self._bounded(task, min(30.0, spec.timeout_seconds))
            if not isinstance(resources, AcpRunResources):
                raise BrokerProtocolError("ACP native resource shape is invalid")
            ref = resources.process_ref
            if (not isinstance(ref, WorkerProcessRef)
                    or ref.run_id != spec.run_id or ref.base_sha != baseline.head
                    or ref.provider_session_id is not None
                    or (spec.expected_worker_uid is not None and ref.effective_uid != spec.expected_worker_uid)
                    or (spec.expected_worker_gid is not None and ref.effective_gid != spec.expected_worker_gid)
                    or not callable(resources.finish) or resources.launch_attestation is None
                    or resources.result_schema != schema):
                raise BrokerProtocolError("ACP native resources do not match admission")
            run = _Run(spec, resources, baseline, schema, AcpReadOnlyTurn(self.profile))
            self._runs[spec.run_id] = run
            self._active = spec.run_id
            run.task = asyncio.create_task(self._execute(run))
            run.task.add_done_callback(self._observe)
            self._opening = None
            return ref
        except BaseException:
            # Retain the original open task. A lost response never proves no effect.
            self._quarantined = True
            raise

    def launch_attestation(self, ref: WorkerProcessRef) -> Any:
        return self._run_for(ref).resources.launch_attestation

    async def _execute(self, run: _Run) -> CollectionReceipt:
        resources, spec = run.resources, run.spec
        driver_error: BaseException | None = None
        try:
            run.candidate = await run.turn.run(
                spec, resources.writer, resources.reader, cancelled=run.cancelled,
                validate_output=lambda value: validate_json_schema(value, run.schema),
                frame_guard=_TurnFrameGuard(run.turn),
            )
        except BaseException as exc:
            driver_error = exc
            run.candidate = run.turn.last_candidate
        finally:
            # Exactly one native-owner finish, shared by collect/cancel callers.
            try:
                run.finish_task = asyncio.create_task(resources.finish(run.cancel_reason))
                run.finish_task.add_done_callback(self._observe)
                run.completion = await self._bounded(run.finish_task, spec.cancel_grace_seconds)
            except BaseException:
                run.uncertain = self._quarantined = True
                raise BrokerEffectUnknownError("ACP native cleanup is unresolved") from None
        candidate, completion = run.candidate, run.completion
        if (driver_error is not None or candidate is None or candidate.effect_unknown
                or run.turn.unsettled_tasks):
            run.uncertain = self._quarantined = True
            raise BrokerEffectUnknownError("ACP original operation is unresolved") from None
        try:
            receipt = self._collection(run, candidate, completion)
        except Exception:
            run.uncertain = self._quarantined = True
            raise BrokerEffectUnknownError("ACP terminal observation is unresolved") from None
        run.receipt = receipt
        if self._active == spec.run_id:
            self._active = None
        return receipt

    def _collection(self, run: _Run, candidate: AcpCandidate,
                    completion: AcpProcessCompletion) -> CollectionReceipt:
        spec, ref = run.spec, run.resources.process_ref
        if (not isinstance(completion, AcpProcessCompletion)
                or completion.process_ref != ref or completion.settled is not True
                or type(completion.exit_code) is not int
                or not _SHA256.fullmatch(completion.stdout_sha256)
                or not _SHA256.fullmatch(completion.stderr_sha256)):
            raise BrokerEffectUnknownError("ACP native terminal evidence is incomplete")
        try:
            end, begin = datetime.fromisoformat(completion.finished_at), datetime.fromisoformat(ref.started_at)
            if end.tzinfo is None or begin.tzinfo is None or end < begin:
                raise ValueError
        except (TypeError, ValueError):
            raise BrokerEffectUnknownError("ACP terminal clock is invalid") from None
        if (candidate.run_id, candidate.job_id, candidate.worker_id) != (spec.run_id, spec.job_id, spec.worker_id):
            raise BrokerEffectUnknownError("ACP candidate identity changed")
        error, status = candidate.error, WorkerRunStatus.INVALID_RESULT
        output = result_hash = None
        git_manifest: dict[str, Any] = {
            "base_sha": run.baseline.head, "head_sha": None, "status_sha256": None, "changed_paths": [],
        }
        if candidate.cancellation_observed:
            status = WorkerRunStatus.TIMED_OUT if error == "ACP_TURN_DEADLINE" else WorkerRunStatus.CANCELLED
        elif error is None and completion.exit_code != 0:
            status, error = WorkerRunStatus.FAILED, "ACP_PROCESS_FAILED"
        elif error is None:
            try:
                if (candidate.stop_reason != "end_turn" or candidate.observed_model != spec.model
                        or not candidate.session_id or candidate.output_json is None
                        or hashlib.sha256(candidate.output_json.encode()).hexdigest() != candidate.output_sha256):
                    raise ValueError
                output = json.loads(candidate.output_json)
                validate_json_schema(output, run.schema)
                for key, expected in (("run_id", spec.run_id), ("job_id", spec.job_id), ("worker_id", spec.worker_id)):
                    if key in output and output[key] != expected:
                        raise ValueError
                if output.get("artifacts") not in (None, []):
                    raise ValueError
                after = _git_snapshot(spec.workspace_path, require_clean=False)
                changed = _git_changed_paths(spec.workspace_path)
                if after.head != run.baseline.head or after.status != run.baseline.status or changed:
                    raise ValueError
                git_manifest.update(head_sha=after.head, status_sha256=hashlib.sha256(after.status).hexdigest())
                result_hash, status = candidate.output_sha256, WorkerRunStatus.SUCCEEDED
            except Exception:
                output, result_hash, error = None, None, "ACP_CANONICAL_RESULT_REFUSED"
        return CollectionReceipt(
            process_ref=dataclasses.replace(ref, provider_session_id=candidate.session_id),
            result=WorkerResult(spec.job_id, spec.run_id, spec.worker_id, status, output,
                (), git_manifest, candidate.usage, candidate.session_id, completion.exit_code,
                ref.started_at, completion.finished_at, error),
            stdout_sha256=completion.stdout_sha256, stderr_sha256=completion.stderr_sha256,
            result_sha256=result_hash,
        )

    async def status(self, ref: WorkerProcessRef) -> WorkerRunStatus:
        run = self._run_for(ref)
        if run.receipt is not None:
            return run.receipt.result.status
        return WorkerRunStatus.CANCELLING if run.cancelled.is_set() or run.uncertain else WorkerRunStatus.RUNNING

    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt:
        run = self._run_for(ref)
        assert run.task is not None
        return await asyncio.shield(run.task)

    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt:
        run = self._run_for(ref)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise BrokerProtocolError("ACP cancellation reason is invalid")
        if run.cancel_reason is not None and run.cancel_reason != reason.strip():
            raise BrokerStateError("ACP cancellation already has a different reason")
        run.cancel_reason = reason.strip()
        run.cancelled.set()
        assert run.task is not None
        await asyncio.shield(run.task)
        if (run.candidate is None or not run.candidate.cancellation_observed
                or run.completion is None or run.completion.cancellation is None):
            raise BrokerStateError("ACP original prompt did not confirm cancellation")
        receipt = run.completion.cancellation
        if receipt.run_id != ref.run_id or receipt.reason != run.cancel_reason:
            raise BrokerEffectUnknownError("ACP cancellation evidence does not match request")
        return receipt

    async def run_validation_argv(self, spec: WorkerLaunchSpec, argv, *,
                                  timeout_seconds: float = 300.0) -> ValidationReceipt:
        raise BrokerProtocolError("ACP read-only profile does not grant native validation")
