"""Join coordination membership to the existing Executive Runtime identities.

The authenticated composition owner supplies membership and consultation-party
readers. This adapter does not issue roles/grants, add a registry, register a
worker, enable a target, or publish a message. It rejects membership that does
not match the current admitted Job/Attempt/OHF binding and immutable lineage.
Native provider/transport eligibility remains with the incumbent binding owner.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
import hashlib
import json
from typing import Any

from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import Runtime
from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationRefused, CoordinationSnapshot,
)
from control_plane.operator_harness_contract import runtime_binding_id_for
from control_plane.runtime_binding_projection import reasoning_surface_for_provider
from integrations.fabric_coordination import (
    CoordinationConsultationParties, CoordinationObservation,
    HierarchyCompanyConsultationGateway, HierarchyScopedPeerResolver,
)
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import ConsultationPeer


class RuntimeCoordinationUnavailable(CoordinationRefused):
    """No raw runtime, SQL, native handle or account data is disclosed."""


def _refuse() -> None:
    raise RuntimeCoordinationUnavailable("RUNTIME_COORDINATION_UNAVAILABLE")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _peer_ref(identity: CoordinationIdentity) -> str:
    return "peer-" + _digest([
        identity.job_id, identity.attempt_id, identity.worker_id,
        identity.binding_id, identity.binding_generation,
    ])[:32]


class RuntimeCoordinationObservationSource:
    """Read-only runtime join; organizational membership stays owner-supplied.

    ``membership_reader`` must come from the authenticated host's admitted scope
    owner, never model arguments or a JSON file selected by a worker. Scope is
    reread after the Runtime read snapshot. An unsupported or changed binding
    refuses the observation, rather than manufacturing a replacement recipient.
    This read is not the effect owner's transaction fence.
    """

    def __init__(self, runtime: Runtime, *,
                 membership_reader: Callable[[], CoordinationSnapshot]) -> None:
        if not isinstance(runtime, Runtime) or not callable(membership_reader):
            raise TypeError("existing Runtime and owner membership reader are required")
        self.runtime = runtime
        self._memberships = membership_reader

    def now(self) -> int:
        milliseconds = self.runtime.store.now_ms()
        if type(milliseconds) is not int or milliseconds < 0:
            _refuse()
        return milliseconds // 1000

    def _current_peer(self, participant, connection) -> tuple[ConsultationPeer, dict[str, Any]]:
        expected = participant.identity
        job = self.runtime.jobs.get_job(expected.job_id)
        if job is None:
            _refuse()
        lineage = derive_delegation_identity(job)
        row = connection.execute(
            "SELECT j.job_id,j.current_attempt_id,j.root_job_id,j.parent_job_id,"
            "j.owner_seat,j.status AS job_status,j.constraints_json,"
            "a.attempt_id,a.worker_id,a.status AS attempt_status "
            "FROM jobs j JOIN attempts a ON a.attempt_id=j.current_attempt_id "
            "AND a.job_id=j.job_id WHERE j.job_id=?",
            (expected.job_id,),
        ).fetchone()
        if row is None or (
            row["current_attempt_id"] != expected.attempt_id
            or row["worker_id"] != expected.worker_id
            or row["job_status"] not in {"RUNNING", "CHECKPOINTED"}
            or row["attempt_status"] not in {"RUNNING", "CHECKPOINTED"}
            or row["root_job_id"] != job.root_job_id
            or row["parent_job_id"] != job.parent_job_id
            or row["owner_seat"] != job.owner_seat
            or row["current_attempt_id"] != job.current_attempt_id
            or row["job_status"] != job.status.value
            or json.loads(row["constraints_json"]) != job.constraints
            or participant.parent_job_id != job.parent_job_id
            or participant.program_ref != f"{lineage.root_job_id}/{lineage.operation_key}"
        ):
            _refuse()
        # This public Runtime reader checks the current admitted process/epoch.
        # A caller-supplied binding is never substituted for its observation.
        facts = self.runtime.current_harness_binding_source(
            expected.attempt_id, connection=connection,
        )
        binding_id = runtime_binding_id_for(facts.attempt_id, facts.session_epoch_id)
        if (facts.attempt_id != expected.attempt_id
                or binding_id != expected.binding_id
                or facts.generation_number != expected.binding_generation):
            _refuse()
        surface = reasoning_surface_for_provider(facts.provider)
        peer = ConsultationPeer(
            _peer_ref(expected), participant.role.value, participant.program_ref,
            {"kind": "worker_attempt", "job_id": expected.job_id,
             "attempt_id": expected.attempt_id, "worker_id": expected.worker_id},
            {"binding_id": binding_id, "binding_generation": facts.generation_number,
             "reasoning_surface": surface},
        )
        # Hash evidence instead of exposing native handles or account labels.
        stamp = {
            "identity": [expected.job_id, expected.attempt_id, expected.worker_id,
                         binding_id, facts.generation_number],
            "root": row["root_job_id"], "parent": row["parent_job_id"],
            "job_status": row["job_status"], "attempt_status": row["attempt_status"],
            "surface": surface,
        }
        return peer, stamp

    def observe(self) -> CoordinationObservation:
        try:
            snapshot = self._memberships()
            if type(snapshot) is not CoordinationSnapshot:
                _refuse()
            now = self.now()
            if not snapshot.observed_at <= now < snapshot.valid_until:
                _refuse()
            peers, evidence = [], []
            with self.runtime.store.read() as connection:
                for participant in snapshot.participants:
                    if not participant.active:
                        continue
                    peer, stamp = self._current_peer(participant, connection)
                    peers.append(peer)
                    evidence.append(stamp)
            current_scope = self._memberships()
            if type(current_scope) is not CoordinationSnapshot or (
                current_scope.revision != snapshot.revision
                or current_scope.participants != snapshot.participants
                or current_scope.grants != snapshot.grants
            ):
                _refuse()
            checked_at = self.now()
            if (not snapshot.observed_at <= checked_at < snapshot.valid_until
                    or not current_scope.observed_at <= checked_at < current_scope.valid_until):
                _refuse()
            # A fresh timestamp is not a scope mutation and cannot prolong the
            # first observation's expiry. Hash the full scope, not just its label.
            joined = replace(snapshot, revision="runtime-" + _digest({
                "membership_revision": snapshot.revision,
                "participants": [asdict(member) for member in snapshot.participants],
                "grants": [asdict(grant) for grant in snapshot.grants],
                "current": sorted(evidence, key=lambda value: value["identity"]),
            }), valid_until=min(snapshot.valid_until, current_scope.valid_until))
            return CoordinationObservation(joined, tuple(peers))
        except RuntimeCoordinationUnavailable:
            raise
        except Exception:
            _refuse()

    def verify_parties(self, parties: CoordinationConsultationParties) -> CoordinationConsultationParties:
        """Check owner-supplied parties against the incumbent consultation INTENT."""
        try:
            if type(parties) is not CoordinationConsultationParties:
                _refuse()
            events = self.runtime.events.list_events(
                aggregate_type="consultation", aggregate_id=parties.consultation_ref,
            )
            intents = [event for event in events if event.event_type == "INTENT"]
            if len(intents) != 1:
                _refuse()
            payload = intents[0].payload
            # Both consultation actors must retain their ORIGINAL current
            # Harness bindings, not just stable Job/Attempt/Worker triples.
            # The incumbent INTENT persists BOTH binding snapshots; verify
            # them against current Runtime owner facts in ONE read transaction.
            # A requester rearm/provider remap must never claim an old answer.
            with self.runtime.store.read() as connection:
                for prefix, identity in (
                    ("requester", parties.requester),
                    ("recipient", parties.recipient),
                ):
                    if payload.get(prefix + "_actor_ref") != {
                        "kind": "worker_attempt", "job_id": identity.job_id,
                        "attempt_id": identity.attempt_id,
                        "worker_id": identity.worker_id,
                    }:
                        _refuse()
                    pinned = payload.get(prefix + "_binding")
                    if (
                        type(pinned) is not dict
                        or set(pinned) != {
                            "binding_id", "binding_generation", "reasoning_surface",
                        }
                        or pinned.get("binding_id") != identity.binding_id
                        or type(pinned.get("binding_generation")) is not int
                        or pinned["binding_generation"] != identity.binding_generation
                    ):
                        _refuse()
                    facts = self.runtime.current_harness_binding_source(
                        identity.attempt_id, connection=connection,
                    )
                    if (
                        facts.attempt_id != identity.attempt_id
                        or runtime_binding_id_for(
                            facts.attempt_id, facts.session_epoch_id,
                        ) != identity.binding_id
                        or facts.generation_number != identity.binding_generation
                        or reasoning_surface_for_provider(facts.provider)
                        != pinned["reasoning_surface"]
                    ):
                        _refuse()
            return parties
        except RuntimeCoordinationUnavailable:
            raise
        except Exception:
            _refuse()


def build_runtime_coordination_gateway(
    *, runtime: Runtime, caller: CoordinationIdentity,
    membership_reader: Callable[[], CoordinationSnapshot],
    consultation_parties: Callable[[str], CoordinationConsultationParties],
    topic_ref: str, dispatcher: Callable, utc_now: Callable[[], str],
    observed_tool_schema_digest: str,
) -> HierarchyCompanyConsultationGateway:
    """Host composition seam, not a public identity or enrollment API.

    Caller identity must already be authenticated by the incumbent host. This
    builder proves its Runtime binding; it does not authenticate a caller or
    attest the upstream role assignment. The dispatcher retains effect fencing.
    """
    if type(caller) is not CoordinationIdentity or not callable(consultation_parties):
        raise TypeError("authenticated caller and consultation owner are required")
    source = RuntimeCoordinationObservationSource(runtime, membership_reader=membership_reader)
    observed = source.observe()
    participant = observed.snapshot.participant(caller, now=source.now())

    def parties(reference: str) -> CoordinationConsultationParties:
        value = source.verify_parties(consultation_parties(reference))
        if value.consultation_ref != reference:
            _refuse()
        return value

    resolver = HierarchyScopedPeerResolver(
        caller=caller, program_ref=participant.program_ref, topic_ref=topic_ref,
        observe=source.observe, consultation_parties=parties, now=source.now,
    )
    return HierarchyCompanyConsultationGateway(
        peer_resolver=resolver, dispatcher=dispatcher,
        observed_tool_schema_digest=observed_tool_schema_digest,
        utc_now=utc_now,
    )
