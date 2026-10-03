"""Stateless Runtime-owned fabric targets for installed Session Bridge.

The Runtime, immutable dialogue source, and Wake ledger remain the canonical
owners. This module derives an opaque target reference from their current facts
and persists nothing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import JobStatus
from integrations.workspace_agent_return import WorkspaceReturnError
from integrations.workspace_agent_runtime_binding import (
    WorkspaceReturnPhysicalSource,
    WorkspaceReturnTargetEpoch,
    _read_current_target,
    _read_dialogue_source,
    _read_physical_source,
)
from .schemas import BridgeError

_TARGET_REF = re.compile(r"^fabric_attempt:[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


@dataclasses.dataclass(frozen=True)
class RuntimeFabricTarget:
    target_ref: str
    operation_key: str
    epoch: WorkspaceReturnTargetEpoch
    source: Any
    physical: WorkspaceReturnPhysicalSource
    generation: str

    def public_projection(self) -> dict[str, Any]:
        return {
            "target_ref": self.target_ref,
            "kind": "fabric_attempt",
            "generation": self.generation,
            "addressable": True,
            "continuation_operation_key": self.reply_binding().continuation_operation_key,
        }

    def reply_binding(self):
        from .dialogue_reply import ExecutiveReplyBinding
        epoch, source = self.epoch, self.source
        commission = (source.commission_ref.to_dict()
                      if callable(getattr(source.commission_ref, "to_dict", None))
                      else dict(source.commission_ref))
        return ExecutiveReplyBinding(
            target_ref=self.target_ref,
            target_generation=self.generation,
            current_writer={"kind": "worker_attempt", "job_id": epoch.job_id,
                            "attempt_id": epoch.attempt_id, "worker_id": epoch.worker_id},
            work_ref=source.work_ref, commission_ref=commission,
            session_ref=epoch.session_ref, dialogue_operation_key=self.operation_key,
            watch_mode=source.watch_mode,
            applies_to={"kind": "executive_attempt", "job_id": epoch.job_id,
                        "attempt_id": epoch.attempt_id, "worker_id": epoch.worker_id},
            thread_ts=self.physical.identity.thread_ts,
            reply_to_message_key=self.physical.identity.predecessor_message_key,
        )


class RuntimeFabricTargetProjector:
    """Reconstruct current active fabric targets without a target registry."""

    def __init__(
        self,
        runtime: Any,
        *,
        job_reader: Callable[[], Any] | None = None,
        identity_resolver: Callable[[Any], Any] = derive_delegation_identity,
        target_reader: Callable[[str], WorkspaceReturnTargetEpoch] | None = None,
        dialogue_source_reader: Callable[[str], Any] | None = None,
        physical_source_reader: Callable[[str, str, str], WorkspaceReturnPhysicalSource] | None = None,
    ) -> None:
        if runtime is None:
            raise TypeError("Runtime is required")
        self._runtime = runtime
        self._job_reader = job_reader or runtime.jobs.list_jobs
        self._identity_resolver = identity_resolver
        self._target_reader = target_reader or (
            lambda operation_key: _read_current_target(runtime, operation_key)
        )
        self._source_reader = dialogue_source_reader or (
            lambda root_job_id: _read_dialogue_source(runtime, root_job_id)
        )
        self._physical_reader = physical_source_reader or (
            lambda operation_key, job_id, attempt_id: _read_physical_source(
                runtime, operation_key, job_id, attempt_id
            )
        )
        if any(
            not callable(value)
            for value in (
                self._job_reader,
                self._identity_resolver,
                self._target_reader,
                self._source_reader,
                self._physical_reader,
            )
        ):
            raise TypeError("fabric target readers must be callable")

    def _candidate(self, job: Any) -> RuntimeFabricTarget | None:
        if (
            getattr(job, "status", None) not in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}
            or not getattr(job, "current_attempt_id", None)
        ):
            return None
        try:
            identity = self._identity_resolver(job)
            operation_key = str(identity.operation_key)
            first = self._target_reader(operation_key)
            if (
                type(first) is not WorkspaceReturnTargetEpoch
                or first.job_id != getattr(job, "job_id", None)
                or first.attempt_id != job.current_attempt_id
            ):
                return None
            source = self._source_reader(first.root_job_id)
            physical = self._physical_reader(
                operation_key, first.job_id, first.attempt_id
            )
            if (
                type(physical) is not WorkspaceReturnPhysicalSource
                or physical.source_workstream != source.work_ref
                or physical.identity.operation_key != operation_key
                or physical.identity.candidate.root_job_id != first.root_job_id
                or physical.identity.candidate.job_id != first.job_id
                or physical.identity.candidate.attempt_id != first.attempt_id
                or physical.identity.candidate.worker_id != first.worker_id
            ):
                return None
            second = self._target_reader(operation_key)
            if type(second) is not WorkspaceReturnTargetEpoch or second != first:
                return None
            commission = (
                source.commission_ref.to_dict()
                if callable(getattr(source.commission_ref, "to_dict", None))
                else dict(source.commission_ref)
            )
            p = physical.identity
            document = {
                "operation_key": operation_key,
                "root_job_id": first.root_job_id,
                "job_id": first.job_id,
                "attempt_id": first.attempt_id,
                "worker_id": first.worker_id,
                "session_ref": first.session_ref,
                "fence_generation": first.fence_generation,
                "harness_session_epoch_id": first.harness_session_epoch_id,
                "harness_generation_number": first.harness_generation_number,
                "harness_provider_session_id": first.harness_provider_session_id,
                "harness_provider": first.harness_provider,
                "harness_account_label": first.harness_account_label,
                "harness_owner_seat": first.harness_owner_seat,
                "work_ref": source.work_ref,
                "commission_ref": commission,
                "watch_mode": source.watch_mode,
                "workspace_id": p.workspace_id,
                "channel_id": p.channel_id,
                "thread_ts": p.thread_ts,
                "parent_fingerprint": p.parent_fingerprint,
            }
            digest = hashlib.sha256(_canonical(document)).hexdigest()
            return RuntimeFabricTarget(
                target_ref=f"fabric_attempt:{digest}",
                operation_key=operation_key,
                epoch=first,
                source=source,
                physical=physical,
                generation=digest[:24],
            )
        except (WorkspaceReturnError, AttributeError, TypeError, ValueError, KeyError):
            return None
        except Exception:
            return None

    def list_targets(self) -> list[RuntimeFabricTarget]:
        try:
            jobs = self._job_reader()
        except Exception:
            raise BridgeError(
                "backend_unavailable", "fabric target projection is unavailable"
            ) from None
        if not isinstance(jobs, list) or len(jobs) > 4096:
            raise BridgeError(
                "backend_unavailable", "fabric target projection is unavailable"
            )
        result = []
        refs: set[str] = set()
        for job in jobs:
            target = self._candidate(job)
            if target is None:
                continue
            if target.target_ref in refs:
                raise BridgeError(
                    "backend_unavailable", "fabric target projection is ambiguous"
                )
            refs.add(target.target_ref)
            result.append(target)
        return sorted(result, key=lambda item: item.target_ref)

    def project(self) -> list[dict[str, Any]]:
        return [target.public_projection() for target in self.list_targets()]

    def resolve(self, target_ref: str) -> RuntimeFabricTarget:
        if not isinstance(target_ref, str) or _TARGET_REF.fullmatch(target_ref) is None:
            raise BridgeError(
                "native_target_stale", "fabric target is no longer current"
            )
        matches = [
            target for target in self.list_targets()
            if target.target_ref == target_ref
        ]
        if len(matches) != 1:
            raise BridgeError(
                "native_target_stale", "fabric target is no longer current"
            )
        return matches[0]


@dataclasses.dataclass(frozen=True)
class RuntimeCodexTarget:
    """Native view of one incumbent fabric target; owns no discovery or state."""

    fabric: RuntimeFabricTarget

    @property
    def target_ref(self) -> str:
        return "codex:" + self.fabric.target_ref.removeprefix("fabric_attempt:")

    def reply_binding(self):
        return dataclasses.replace(
            self.fabric.reply_binding(), target_ref=self.target_ref
        )

    def public_projection(self) -> dict[str, Any]:
        return {
            "target_ref": self.target_ref,
            "kind": "codex",
            "generation": self.fabric.generation,
            "addressable": True,
            "continuation_operation_key": self.reply_binding().continuation_operation_key,
        }


class RuntimeCodexTargetProjector:
    """Fail-closed Codex/COO view over the existing Runtime projector."""

    def __init__(
        self, base: RuntimeFabricTargetProjector, *,
        owner_configured: Callable[[], bool] | None = None,
    ) -> None:
        if not isinstance(base, RuntimeFabricTargetProjector):
            raise TypeError("the incumbent Runtime projector is required")
        if owner_configured is not None and not callable(owner_configured):
            raise TypeError("native owner capability must be callable")
        self._base = base
        self._owner_configured = owner_configured

    def _enabled(self) -> bool:
        try:
            return self._owner_configured is not None and self._owner_configured() is True
        except Exception:
            return False

    @staticmethod
    def _eligible(target: RuntimeFabricTarget) -> bool:
        return (
            target.epoch.harness_provider == "openai-codex"
            and target.epoch.harness_owner_seat == "coo"
        )

    def project(self) -> list[dict[str, Any]]:
        if not self._enabled():
            return []
        values = [
            RuntimeCodexTarget(target).public_projection()
            for target in self._base.list_targets() if self._eligible(target)
        ]
        return values if self._enabled() else []

    def resolve(self, target_ref: str) -> RuntimeCodexTarget:
        if (
            not self._enabled()
            or not isinstance(target_ref, str)
            or re.fullmatch(r"codex:[0-9a-f]{64}", target_ref) is None
        ):
            raise BridgeError("native_target_stale", "native Codex target is no longer current")
        target = self._base.resolve("fabric_attempt:" + target_ref.removeprefix("codex:"))
        if not self._eligible(target) or not self._enabled():
            raise BridgeError("native_target_stale", "native Codex target is no longer current")
        return RuntimeCodexTarget(target)


class RuntimeExecutiveReplyBindingResolver:
    """Recompute from incumbent Runtime/source/Wake owners on every lookup."""

    def __init__(self, projector: RuntimeFabricTargetProjector | RuntimeCodexTargetProjector):
        self._projector = projector

    def resolve(self, target_ref: str):
        return self._projector.resolve(target_ref).reply_binding()


__all__ = [
    "RuntimeCodexTarget",
    "RuntimeCodexTargetProjector",
    "RuntimeFabricTarget",
    "RuntimeExecutiveReplyBindingResolver",
    "RuntimeFabricTargetProjector",
]
