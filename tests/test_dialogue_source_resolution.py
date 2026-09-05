from __future__ import annotations

import dataclasses

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    DialogueSourceResolutionError,
    PhysicalDialogueSourceIdentity,
    attention_source_ref,
    correlated_source_ref,
)
from control_plane.wake_events import mint_obligation_id


PARENT = "a" * 64
CANDIDATE = {
    "mode": "ACTIVE_CURRENT_WORKER",
    "root_job_id": "JOB-100",
    "job_id": "JOB-101",
    "attempt_id": "ATT-" + "2" * 32,
    "worker_id": "worker-01",
    "evidence_digest": "b" * 64,
}


def _identity(candidate: dict[str, str] | None = None) -> PhysicalDialogueSourceIdentity:
    observation = DialogueSourceObservation(
        workspace_id="T0BRD2AQXQV",
        channel_id="C0BSBM78V1N",
        thread_ts="1788000000.123456",
        predecessor_message_key="asd-progress-001",
        predecessor_message_fingerprint="c" * 64,
    )
    attention = attention_source_ref(
        parent_fingerprint=PARENT,
        message_key=observation.predecessor_message_key,
        target_seat="ceo",
    )
    logical = correlated_source_ref(
        attention_source_ref=attention,
        parent_fingerprint=PARENT,
        operation_key="runtime-continuity-r2",
        candidate=candidate or CANDIDATE,
    )
    return PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical,
        obligation_id=mint_obligation_id(
            source_kind="agent_dialogue_attention",
            source_ref=logical,
            wake_kind="dialogue_turn_pending",
        ),
        observation=observation,
        parent_fingerprint=PARENT,
        operation_key="runtime-continuity-r2",
        target_seat="ceo",
        candidate=CANDIDATE,
    )


def test_physical_identity_is_deeply_immutable_and_returns_detached_wire() -> None:
    candidate = dict(CANDIDATE)
    identity = _identity(candidate)
    candidate["worker_id"] = "forged-worker"
    wire = identity.to_dict()
    wire["candidate"]["worker_id"] = "forged-worker"

    assert identity.to_dict()["candidate"]["worker_id"] == "worker-01"
    assert identity.candidate.worker_id == "worker-01"
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.candidate.worker_id = "forged-worker"


def test_physical_identity_rederives_logical_reference_and_obligation_id() -> None:
    wire = _identity().to_dict()
    wire["logical_source_ref"] = "agent_dialogue_attention:" + "d" * 64
    wire["obligation_id"] = mint_obligation_id(
        source_kind="agent_dialogue_attention",
        source_ref=wire["logical_source_ref"],
        wake_kind="dialogue_turn_pending",
    )
    material = {key: value for key, value in wire.items() if key != "digest"}
    from control_plane.dialogue_source_resolution import canonical_bytes
    import hashlib
    wire["digest"] = hashlib.sha256(canonical_bytes(material)).hexdigest()

    with pytest.raises(DialogueSourceResolutionError, match="logical source"):
        PhysicalDialogueSourceIdentity.from_dict(wire)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema", "mastermind.dialogue_physical_source/v3"),
        ("logical_source_ref", "agent_dialogue_attention:" + "d" * 64),
        ("obligation_id", "WAKE-" + "d" * 32),
        ("workspace_id", "T0BRD2AQXQW"),
        ("channel_id", "C0BSBM78V1P"),
        ("thread_ts", "1788000001.123456"),
        ("parent_fingerprint", "d" * 64),
        ("operation_key", "runtime-continuity-r2-other"),
        ("predecessor_message_key", "asd-progress-002"),
        ("predecessor_message_fingerprint", "d" * 64),
        ("target_seat", "coo"),
        ("candidate", {**CANDIDATE, "worker_id": "worker-02"}),
        ("digest", "d" * 64),
    ],
)
def test_every_physical_identity_field_is_integrity_checked(
    field: str,
    replacement: object,
) -> None:
    wire = _identity().to_dict()
    wire[field] = replacement

    with pytest.raises(DialogueSourceResolutionError):
        PhysicalDialogueSourceIdentity.from_dict(wire)


@pytest.mark.parametrize("mutation", ["omit", "add"])
def test_physical_identity_wire_is_closed(mutation: str) -> None:
    wire = _identity().to_dict()
    if mutation == "omit":
        del wire["workspace_id"]
    else:
        wire["carrier_alias"] = "forbidden"

    with pytest.raises(DialogueSourceResolutionError, match="fields drifted"):
        PhysicalDialogueSourceIdentity.from_dict(wire)
