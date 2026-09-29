"""Optional host composition for one admitted coordination work Job.

The existing ExecutiveSupervisor retains every lifecycle, launch, validation,
recovery and completion method. This subclass changes only task composition for
one host-selected Job. It is not installed, registered or started on import.
"""
from __future__ import annotations

import copy
import dataclasses
import re
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.chairman_coordination_work import (
    _artifact_path, read_coordination_work_request, read_coordination_work_return,
)
from control_plane.executive_runtime import Attempt, AttemptStatus, Job, JobStatus, Runtime, OrchestrationDispatchOutcome, _require_exact_worker_target
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError, SupervisorReceipt
from control_plane.fabric_result_projection import project_fabric_role_result

_ARTIFACT_BYTES_LIMIT = 128 * 1024


@dataclasses.dataclass(frozen=True, repr=False)
class CoordinationWorkSources:
    """Transient owner-acquired inputs, not credentials or durable project state.

    A trusted installed composition must supply these inputs and the revalidator.
    Constructing this object does not authenticate a source or grant authority.
    Revalidation must raise if its exact source observation is no longer current.
    """
    document: Mapping[str, Any]
    context: Mapping[str, Any]
    context_bundle: Mapping[str, Any]
    bundle_source_ref: str
    artifact_path: str
    revalidate: Callable[[], None]


def _freeze_sources(value: Any) -> CoordinationWorkSources:
    if type(value) is not CoordinationWorkSources or not callable(value.revalidate):
        raise SupervisorError("coordination source acquisition is unavailable")
    if not all(isinstance(item, Mapping) for item in (value.document, value.context, value.context_bundle)):
        raise SupervisorError("coordination source acquisition is malformed")
    # Keep the per-call inputs independent of a mutable provider cache. The
    # provider's own revalidator still decides freshness; copying is not proof.
    return dataclasses.replace(value, document=copy.deepcopy(dict(value.document)),
        context=copy.deepcopy(dict(value.context)), context_bundle=copy.deepcopy(dict(value.context_bundle)))


def _revalidate_sources(source: CoordinationWorkSources) -> None:
    if source.revalidate() is not None:
        raise SupervisorError("coordination source revalidation contract is invalid")


class CoordinationWorkSupervisor(ExecutiveSupervisor):
    """Specialize only the original prompt hook; all effect methods are inherited.

    The host selects one already-admitted work Job and supplies current read-only
    Runtime access and source acquisition. No prompt is injected into other Jobs.
    Missing selected-job sources refuse instead of falling back to a generic task.
    The original exact-target source fence remains the dispatch owner; a prompt
    snapshot is not a fence against later changes and grants no launch permission.
    """
    def __init__(self, *args: Any, coordination_job_id: str,
                 coordination_sources: Callable[[Job, Attempt], CoordinationWorkSources],
                 coordination_runtime: Runtime, **kwargs: Any) -> None:
        if (type(coordination_job_id) is not str or re.fullmatch(r"JOB-[0-9]{1,9}", coordination_job_id) is None
                or not callable(coordination_sources) or type(coordination_runtime) is not Runtime):
            raise SupervisorError("coordination host requires exact Job and owner providers")
        target_provider = kwargs.get("exact_target_provider")
        if not callable(target_provider):
            raise SupervisorError("coordination host requires the existing exact-target owner")
        def exact_target(job_id: str):
            if job_id != coordination_job_id:
                return target_provider(job_id)
            try:
                target = _require_exact_worker_target(target_provider(job_id))
                if target.definition["job_id"] != coordination_job_id:
                    raise SupervisorError("coordination target belongs to a different Job")
                return target
            except Exception as exc:
                raise SupervisorError("coordination exact target is unavailable") from exc
        kwargs["exact_target_provider"] = exact_target
        self._coordination_job_id = coordination_job_id
        self._coordination_sources = coordination_sources
        self._coordination_runtime = coordination_runtime
        super().__init__(*args, **kwargs)

    def _prompt(self, job: Job, attempt: Attempt,
                effective_grant: Mapping[str, Any] | None = None) -> str:
        original = super()._prompt(job, attempt, effective_grant)
        if job.job_id != self._coordination_job_id:
            return original
        try:
            if effective_grant is None or dict(effective_grant) != attempt.effective_grant:
                raise SupervisorError("coordination task requires original effective grant")
            sources = _freeze_sources(self._coordination_sources(job, attempt))
            _revalidate_sources(sources)
            request = read_coordination_work_request(
                sources.document, context=sources.context, context_bundle=sources.context_bundle,
                bundle_source_ref=sources.bundle_source_ref, runtime=self._coordination_runtime,
                root_job_id=job.root_job_id, job_id=job.job_id,
                expected_attempt_id=attempt.attempt_id,
                authority_decision=self._revalidate_authority(job, attempt),
                artifact_path=sources.artifact_path,
            )
            if (request["job_id"] != job.job_id or request["attempt_id"] != attempt.attempt_id
                    or request["effective_grant_digest"] != attempt.effective_grant_digest):
                raise SupervisorError("coordination assignment changed during composition")
            _revalidate_sources(sources)
        except Exception as exc:
            # Do not expose source-provider details or silently send a generic
            # prompt when a selected coordination request cannot be grounded.
            raise SupervisorError("coordination task composition refused") from exc
        return original + "\n\nAdditional task content for this exact admitted work Job:\n" + request["prompt"]


    async def run_coordination_once(
        self, *, command_id: str, artifact_reader: Callable[..., bytes],
    ) -> tuple[SupervisorReceipt | OrchestrationDispatchOutcome, dict[str, Any] | None]:
        """Advance one existing command and inspect its result, never its next_step.

        This invokes the inherited finite run_cycle_once exactly once. An active
        duplicate or non-successful terminal result is returned unchanged with
        no decision review. A completed replay reads the original result, not a
        new model turn. There is no automatic retry, loop, new command or queue.
        A post-completion source/artifact failure leaves canonical completion
        intact so the same command can later be inspected explicitly.
        """
        if not callable(artifact_reader):
            raise SupervisorError("coordination artifact reader is unavailable")
        execution = await self.run_cycle_once(self._coordination_job_id, command_id=command_id)
        if type(execution) is SupervisorReceipt:
            job, attempt = execution.job, execution.attempt
        elif type(execution) is OrchestrationDispatchOutcome:
            if execution.outcome != "TERMINAL" or execution.attempt.status is not AttemptStatus.COMPLETED:
                return execution, None
            job, attempt = self._job(self._coordination_job_id), execution.attempt
        else:
            raise SupervisorError("unexpected existing supervisor return type")
        if job.status is not JobStatus.COMPLETED or attempt.status is not AttemptStatus.COMPLETED:
            return execution, None
        try:
            sources = self._coordination_sources(job, attempt)
            review = _consume_job_result(job, attempt, sources=sources,
                runtime=self._coordination_runtime, artifact_reader=artifact_reader)
        except Exception as exc:
            raise SupervisorError("completed coordination work requires result reconciliation") from exc
        return execution, review


def consume_coordination_completion(
    completion: SupervisorReceipt, *, sources: CoordinationWorkSources,
    runtime: Runtime,
    artifact_reader: Callable[..., bytes],
) -> dict[str, Any]:
    """Collect one proposal after canonical completion, without executing it.

    The artifact reader is the existing authorized acquisition owner. It receives
    canonical Job/Attempt objects, exact path/hash and a fixed byte ceiling, never
    a user URL or a name-based substitute. No file is opened by this composition.
    One bounded read authorizes the requested evidence; another verifies the same
    exact selector after artifact acquisition. Neither observation asserts an
    ongoing write exclusion. Failure never triggers a new Job, read target or retry.
    """
    if type(completion) is not SupervisorReceipt:
        raise SupervisorError("coordination completion requires an existing supervisor receipt")
    return _consume_job_result(completion.job, completion.attempt, sources=sources,
        runtime=runtime, artifact_reader=artifact_reader)


def _consume_job_result(
    job: Job, attempt: Attempt, *, sources: CoordinationWorkSources,
    runtime: Runtime, artifact_reader: Callable[..., bytes],
) -> dict[str, Any]:
    if type(runtime) is not Runtime or not callable(artifact_reader):
        raise SupervisorError("coordination completion requires existing owner readers")
    if (type(job) is not Job or type(attempt) is not Attempt
            or job.status is not JobStatus.COMPLETED or attempt.status is not AttemptStatus.COMPLETED
            or job.job_id != attempt.job_id or job.current_attempt_id != attempt.attempt_id
            or job.orchestration_role != "work" or not isinstance(job.result, Mapping)):
        raise SupervisorError("coordination completion is not the exact completed work")
    selected_digest = job.result.get("result_envelope_digest")
    if type(selected_digest) is not str or re.fullmatch(r"[0-9a-f]{64}", selected_digest) is None:
        raise SupervisorError("coordination completion lacks the exact result selector")
    try:
        current = _freeze_sources(sources)
        _revalidate_sources(current)
        path = _artifact_path(current.artifact_path)
        with runtime.observe_bounded_read() as observation:
            snapshot = observation.read_role_result_bounded(
                job.root_job_id, job.job_id, expected_attempt_id=attempt.attempt_id,
                expected_result_envelope_digest=selected_digest,
            )
        projected = project_fabric_role_result(snapshot, observation.receipt).complete
        if (snapshot.root_metadata.work_ref != current.context.get("project_ref")
                or projected["role"] != "work" or snapshot.completion.result_envelope["errors"]):
            raise SupervisorError("coordination return does not match the project contract")
        matches = [item for item in projected["content"]["role_result"]["artifacts"] if item["path"] == path]
        if len(matches) != 1:
            raise SupervisorError("coordination artifact selection is absent or ambiguous")
        payload = artifact_reader(snapshot.completion.job, snapshot.completion.attempt, path,
            expected_sha256=matches[0]["digest"], max_bytes=_ARTIFACT_BYTES_LIMIT)
        _revalidate_sources(current)
        result = read_coordination_work_return(
            current.document, context=current.context, runtime=runtime,
            root_job_id=job.root_job_id, job_id=job.job_id,
            expected_attempt_id=attempt.attempt_id,
            expected_result_envelope_digest=selected_digest,
            artifact_path=path, artifact_bytes=payload,
        )
        _revalidate_sources(current)
        return result
    except Exception as exc:
        raise SupervisorError("coordination completion acquisition refused") from exc
