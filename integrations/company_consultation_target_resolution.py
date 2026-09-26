"""Read-only exact consultation target reconstruction from existing owners.

Executive owns Job/Attempt/Worker identity and immutable root dialogue source;
Consultation Runtime owns admitted parties; Wake owns physical parent identity.
The same verified root/physical readers used by Workspace returns are reused,
without importing Workspace's RESULT-only grant or creating another registry.

A new QUESTION requires a double-read current target. After INTENT, the exact
admitted Attempt is sticky even when the stable peer's current Attempt changes.
This resolver performs no permission expansion, body storage, send, or wake.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from common.agent_dialogue_consultation_contract import (
    canonical_consultation_json,
    validate_consultation,
)
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import Runtime, StateConflict
from integrations.company_consultation_dispatch import (
    ConsultationPacketCarrierUnknown,
    _find_consultation_event,
)
from integrations.company_consultation_targets import (
    ConsultationDeliveryTarget,
    ConsultationPacketAccess,
    TargetedAgentDialogueConsultationPacketCarrier,
    _actor,
)
from integrations.workspace_agent_runtime_binding import (
    _read_current_target,
    _read_dialogue_source,
    _read_physical_source,
)


class ExecutiveConsultationPacketTargetResolver:
    """Host-scoped fact reader. Constructor scope must match the Relay service.

    The host supplies the service's workspace/channel; neither is a tool input.
    A physical source from another Slack scope is refused, never reinterpreted
    against an identically numbered thread in the host's configured channel.
    """

    def __init__(self, runtime: Runtime, *, workspace_id: str, channel_id: str) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        if (
            not isinstance(workspace_id, str)
            or re.fullmatch(r"T[A-Z0-9]{8,31}", workspace_id) is None
            or not isinstance(channel_id, str)
            or re.fullmatch(r"[CG][A-Z0-9]{8,31}", channel_id) is None
        ):
            raise ValueError("exact Relay workspace and channel are required")
        self._runtime = runtime
        self._workspace_id = workspace_id
        self._channel_id = channel_id

    def _exact_identity(self, actor: Mapping[str, Any]):
        """Validate durable identity, deliberately not historical liveness."""
        job = self._runtime.jobs.get_job(actor["job_id"])
        attempt = self._runtime.attempts.get_attempt(actor["attempt_id"])
        worker = self._runtime.workers.get_worker(actor["worker_id"])
        if (
            job is None or attempt is None or worker is None
            or job.job_id != actor["job_id"]
            or attempt.attempt_id != actor["attempt_id"]
            or attempt.job_id != actor["job_id"]
            or attempt.worker_id != actor["worker_id"]
            or worker.worker_id != actor["worker_id"]
        ):
            raise StateConflict("exact consultation target lineage is unavailable")
        return derive_delegation_identity(job)

    @staticmethod
    def _parties(payload: Mapping[str, Any]):
        return (
            _actor(payload.get("requester_actor_ref")),
            _actor(payload.get("recipient_actor_ref")),
        )

    def resolve(
        self,
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None = None,
    ) -> ConsultationPacketAccess:
        try:
            return self._resolve(consultation_id, purpose=purpose, frame=frame)
        except (StateConflict, ConsultationPacketCarrierUnknown):
            raise
        except Exception:
            # Preserve missing/ambiguous owner evidence as unknown, not absence;
            # do not expose SQL, provider identifiers, or dependency diagnostics.
            raise ConsultationPacketCarrierUnknown(
                "canonical consultation target evidence is unavailable"
            ) from None

    def _resolve(
        self,
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None,
    ) -> ConsultationPacketAccess:
        TargetedAgentDialogueConsultationPacketCarrier._identity(consultation_id, purpose)
        item = validate_consultation(frame) if frame is not None else None
        if item is not None and (
            item["consultation_id"] != consultation_id or item["purpose"] != purpose
        ):
            raise StateConflict("consultation target request identity disagrees")
        intent = _find_consultation_event(self._runtime, consultation_id, "INTENT")
        if intent is None:
            if item is None or purpose != "QUESTION":
                raise StateConflict("consultation target has no admitted party facts")
            parties = self._parties(item)
        else:
            parties = self._parties(intent.payload)
            if item is not None and self._parties(item) != parties:
                raise StateConflict("candidate disagrees with admitted consultation parties")

        actor = parties[1 if purpose == "QUESTION" else 0]
        identity = self._exact_identity(actor)
        current = None
        if intent is None:
            current = _read_current_target(self._runtime, identity.operation_key)
            if (
                current.root_job_id != identity.root_job_id
                or current.job_id != actor["job_id"]
                or current.attempt_id != actor["attempt_id"]
                or current.worker_id != actor["worker_id"]
                or current.session_ref != identity.session_ref
            ):
                raise StateConflict("new consultation target is not the exact current Attempt")

        source = _read_dialogue_source(self._runtime, identity.root_job_id)
        physical_source = _read_physical_source(
            self._runtime, identity.operation_key, actor["job_id"], actor["attempt_id"],
        )
        physical = physical_source.identity
        if (
            physical_source.source_workstream != source.work_ref
            or physical.workspace_id != self._workspace_id
            or physical.channel_id != self._channel_id
            or physical.operation_key != identity.operation_key
            or physical.candidate.root_job_id != identity.root_job_id
            or physical.candidate.job_id != actor["job_id"]
            or physical.candidate.attempt_id != actor["attempt_id"]
            or physical.candidate.worker_id != actor["worker_id"]
        ):
            raise StateConflict("physical consultation source disagrees with exact target")
        if self._exact_identity(actor) != identity:
            raise StateConflict("consultation target lineage changed during reconstruction")
        if current is not None and _read_current_target(self._runtime, identity.operation_key) != current:
            raise StateConflict("current consultation target changed during reconstruction")
        latest_intent = _find_consultation_event(self._runtime, consultation_id, "INTENT")
        if (intent is not None and latest_intent is None) or (
            latest_intent is not None and self._parties(latest_intent.payload) != parties
        ):
            raise StateConflict("consultation parties changed during reconstruction")

        facts = {
            "actor_ref": dict(actor),
            "work_ref": source.work_ref,
            "commission_ref": source.commission_ref.to_dict(),
            "session_ref": identity.session_ref,
            "operation_key": identity.operation_key,
            "watch_mode": source.watch_mode,
            "thread_ts": physical.thread_ts,
        }
        # Hash destination identity, not a particular attention event. Multiple
        # valid Wake events for one exact parent must not manufacture rotation.
        evidence = {
            **facts,
            "root_job_id": identity.root_job_id,
            "workspace_id": physical.workspace_id,
            "channel_id": physical.channel_id,
            "parent_fingerprint": physical.parent_fingerprint,
        }
        target = ConsultationDeliveryTarget(
            **facts,
            evidence_digest=hashlib.sha256(canonical_consultation_json(evidence).encode()).hexdigest(),
        )
        return ConsultationPacketAccess(
            target=target, requester_actor_ref=parties[0], recipient_actor_ref=parties[1],
        )
