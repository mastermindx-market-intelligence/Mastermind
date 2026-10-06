"""Read-only proposal for the root-owned bounded dialogue grant publisher.

The original authenticated CONTINUE event selects the source. Existing Relay,
observation, turn-classifier and Runtime owners derive every admission identity.
No caller-supplied target tuple, provider effect, or grant publication lives here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Callable

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant, MAX_VALIDITY_SECONDS, SCHEMA,
)
from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER, DialogueWakeRequest, SUBMIT_WAKE,
    reduce_dialogue_observation,
)
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import (
    ExecutiveControlService, derive_dialogue_wake_canary_current_facts,
    resolve_current_dialogue_wake_target,
)
from control_plane import session_targets
from control_plane.session_targets import route_obligation
from control_plane.wake_events import mint_obligation
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.turn_routing_facts import resolve_turn_routing_facts
from integrations.slack_agent_dialogue.turn_wake_adapter import attention_to_wake_obligation
from integrations.slack_agent_dialogue.turn_watcher import classify_turn
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import resolve_company_dialogue_binding
from .runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from .runtime_return import RuntimeSessionReturn


@dataclasses.dataclass(frozen=True)
class CanaryGrantProposal:
    grant: DialogueWakeCanaryActivationGrant
    read_ref: str
    source_event_sha256: str
    facts_sha256: str


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


async def derive_canary_grant_proposal(
    runtime: Runtime, *, read_ref: str, socket_path: Path,
    installed_release_sha: str, validity_seconds: int, now_provider: Callable[[], int],
) -> CanaryGrantProposal:
    """Derive one active child continuation; returns evidence, never authority."""
    if type(validity_seconds) is not int or not 0 < validity_seconds <= MAX_VALIDITY_SECONDS:
        raise ValueError("invalid bounded grant interval")
    fabric = RuntimeFabricTargetProjector(runtime)
    # This reader never discovers/adopts a native session. Keep native discovery
    # explicitly unavailable; current identity is proven by the Runtime below.
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: False)
    source = await RuntimeSessionReturn(
        runtime, fabric=fabric, codex=codex, socket_path=socket_path,
    ).read_continuation_source(read_ref=read_ref)
    value, parent, message = source["request"], source["parent"], source["message"]
    with runtime.store.read() as connection:
        reader = object.__new__(ExecutiveControlService)
        response = reduce_dialogue_observation(
            parent=parent, thread_ts=value["thread_ts"],
            facts=reader._runtime_dialogue_observation_facts(runtime, parent, connection=connection),
        )
    if response.get("state") != "RESOLVED" or response.get("mode") != ACTIVE_CURRENT_WORKER:
        raise ValueError("one current child is required")
    observed = ExecutiveDialogueObservationClient._active(
        parent=parent, thread_ts=value["thread_ts"], observation=response["observation"],
        target_bindings=ExecutiveDialogueObservationClient._target_bindings(response["target_bindings"]),
    )
    candidate = observed.candidate
    if any(getattr(candidate, field) != value[field] for field in (
            "root_job_id", "job_id", "attempt_id", "worker_id")):
        raise ValueError("original child identity changed")
    registry = session_targets.load_session_targets()
    resolution = resolve_company_dialogue_binding(
        delegation_identity=observed.delegation_identity, dialogue_parent=parent,
        thread_ts=value["thread_ts"], current=observed.current_worker, actor=observed.actor,
    )
    routing = resolve_turn_routing_facts(
        dialogue_parent=parent, current_worker=observed.current_worker,
        binding_resolution=resolution, registry=registry,
        current_binding_for=lambda seat: observed.target_bindings.get(seat),
    )
    decision = classify_turn(parent=parent, messages=source["messages"], routing=routing)
    attention = decision.attention
    if (attention is None or attention.target_seat != "coo"
            or attention.message_key != message["message_key"]
            or attention.message_fingerprint != message["fingerprint"]):
        raise ValueError("original continuation is not the current child attention")
    original = attention_to_wake_obligation(attention)
    logical = correlated_source_ref(
        attention_source_ref=attention_source_ref(
            parent_fingerprint=parent["fingerprint"], message_key=message["message_key"],
            target_seat=attention.target_seat),
        parent_fingerprint=parent["fingerprint"], operation_key=parent["operation_key"],
        candidate=candidate.to_dict(),
    )
    obligation = mint_obligation(
        wake_kind=original.wake_kind, source_kind=original.source_kind, source_ref=logical,
        declared_target_seat=attention.target_seat,
        job_id=candidate.job_id, attempt_id=candidate.attempt_id,
        root_job_id=candidate.root_job_id, workstream=original.workstream,
        source_workstream=original.source_workstream,
        source_created_at=original.source_created_at, emitted_at=original.emitted_at,
    )
    observation = DialogueSourceObservation(
        **value["carrier"], predecessor_message_key=message["message_key"],
        predecessor_message_fingerprint=message["fingerprint"],
    )
    physical = PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical, obligation_id=obligation.obligation_id,
        observation=observation, parent_fingerprint=parent["fingerprint"],
        operation_key=parent["operation_key"], target_seat=attention.target_seat,
        candidate=candidate.to_dict(),
    )
    route = route_obligation(obligation, registry, binding=observed.target_bindings["coo"])
    request = DialogueWakeRequest(
        operation=SUBMIT_WAKE, parent=parent, thread_ts=value["thread_ts"],
        candidate=candidate, obligation=obligation, proposed_route=route,
        source_observation=observation, physical_source=physical,
    )
    target = resolve_current_dialogue_wake_target(runtime, request)
    if target is None or target.target_attempt_id != value["attempt_id"]:
        raise ValueError("original child is not the unique current writer")
    route = route_obligation(obligation, target.registry, binding=target.runtime_binding)
    request = dataclasses.replace(request, proposed_route=route)
    facts, now = derive_dialogue_wake_canary_current_facts(
        runtime, request, target, route,
        installed_release_sha=installed_release_sha, now_provider=now_provider,
    )
    grant = DialogueWakeCanaryActivationGrant(
        schema=SCHEMA, **facts.to_dict(), valid_from_epoch_seconds=now,
        expires_at_epoch_seconds=now + validity_seconds,
    )
    return CanaryGrantProposal(
        grant=grant, read_ref=read_ref, source_event_sha256=_digest(source["event"]),
        facts_sha256=_digest(facts.to_dict()),
    )


def installed_proposal_json(expected_sha: str, read_ref: str, validity_seconds: int) -> str:
    """Fixed UID450 read probe invoked by the existing root transaction owner."""
    import asyncio
    import time
    from scripts.executive_os_phase1c import load_control_config, _CANONICAL_AGENT_RELAY_SOCKET
    config = load_control_config(
        Path("/Library/Application Support/MastermindExecutive/config/control.json")
    )
    if config["proof_base_sha"] != expected_sha:
        raise ValueError("installed source release changed")
    runtime = Runtime.at(Path(config["runtime_root"]), create=False)
    proposal = asyncio.run(derive_canary_grant_proposal(
        runtime, read_ref=read_ref, socket_path=_CANONICAL_AGENT_RELAY_SOCKET,
        installed_release_sha=expected_sha, validity_seconds=validity_seconds,
        now_provider=lambda: int(time.time()),
    ))
    return json.dumps({
        "grant": proposal.grant.to_dict(), "read_ref": proposal.read_ref,
        "source_event_sha256": proposal.source_event_sha256,
        "facts_sha256": proposal.facts_sha256,
    }, sort_keys=True, separators=(",", ":"))
