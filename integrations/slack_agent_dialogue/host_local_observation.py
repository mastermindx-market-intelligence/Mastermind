"""Read-only observation within the existing Control process.

Control UID 450 must not connect as Agent Relay UID 457. This reader uses the
same service-owned Runtime snapshot/reducer and closed response decoder without
opening that socket or exposing the client's Wake/reconciliation operations.
It is selected only by trusted host composition, never by a wire argument.
"""
from __future__ import annotations

import hashlib

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from control_plane.executive_dialogue_observation import (
    parse_observation_request, reduce_dialogue_observation, response_bytes,
    REQUEST_SCHEMA,
)
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import ExecutiveControlService
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveDialogueObservationClient, ExecutiveObservationClientError,
    ResolvedDialogueObservation, _canonical_json, _strict_json,
    _validated_parent, _validated_thread_ts,
)


@dataclass(frozen=True)
class HostLocalDialogueObservationReader:
    service: ExecutiveControlService
    runtime: Runtime

    def __post_init__(self):
        if (type(self.service) is not ExecutiveControlService
                or type(self.runtime) is not Runtime
                or self.service.runtime is not self.runtime):
            raise ValueError("host-local observation requires the existing Control Runtime")
        self._require_canonical_provider()

    def _require_canonical_provider(self):
        selected = getattr(self.service, "_dialogue_observation_facts_provider", None)
        if selected is not None and selected != self.service._runtime_dialogue_observation_facts:
            raise ExecutiveObservationClientError("UNAVAILABLE_ZERO_EFFECT")

    def _require_current(self):
        self._require_canonical_provider()
        if (self.service.runtime is not self.runtime or self.service._closing
                or not self.service._ceo_ingress_ready
                or self.service._service_state not in {"READY", "AWAITING_CANARY"}):
            raise ExecutiveObservationClientError("UNAVAILABLE_ZERO_EFFECT")

    async def resolve(self, *, parent: Mapping[str, Any], thread_ts: str) -> ResolvedDialogueObservation:
        self._require_current()
        parent = _validated_parent(parent)
        thread_ts = _validated_thread_ts(thread_ts)
        # Parse the same closed read-only request before touching Runtime.
        request = parse_observation_request(_canonical_json({
            "schema": REQUEST_SCHEMA,
            "request_id": "observation-" + hashlib.sha256(_canonical_json(parent)).hexdigest()[:32],
            "parent": dict(parent),
        }))
        facts = await self.service._run_physical(
            self.service._runtime_dialogue_observation_facts, self.runtime, request.parent)
        self._require_current()
        # Reuse both canonical selection and bounded serialization; no second
        # facts store, source cache, mode selector or response interpretation.
        response = _strict_json(response_bytes(reduce_dialogue_observation(
            parent=request.parent, facts=facts)))
        return ExecutiveDialogueObservationClient.decode_response(
            response, parent=request.parent, thread_ts=thread_ts)
