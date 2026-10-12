"""Closed publication evidence for the one root-owned dialogue canary grant.

A receipt is evidence only when read from the fixed root-owned host file.
This value contract performs no publication, routing, scheduling, or I/O.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any

from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant, DialogueWakeCanaryCurrentFacts,
    IDENTITY_FIELDS, MAX_EPOCH_SECONDS, match_dialogue_wake_canary_activation,
)

PUBLICATION_SCHEMA = "mastermind.dialogue_wake_canary_publication/v1"
PUBLICATION_OPERATION = "DIALOGUE_WAKE_CANARY_PUBLISH"
_RECEIPT_PATTERNS = {
    "transaction_id": r"autonomy-[0-9a-f]{12}",
    "installed_release_sha": r"[0-9a-f]{40}",
    "grant_digest": r"[0-9a-f]{64}",
    "control_config_sha256": r"[0-9a-f]{64}",
    "worker_config_sha256": r"[0-9a-f]{64}",
    "source_read_ref": r"session-reply-[0-9a-f]{64}",
    "source_event_sha256": r"[0-9a-f]{64}",
    "facts_sha256": r"[0-9a-f]{64}",
}


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


@dataclasses.dataclass(frozen=True)
class DialogueWakeCanaryPublicationReceipt:
    schema: str
    operation: str
    transaction_id: str
    installed_release_sha: str
    grant_digest: str
    control_config_sha256: str
    worker_config_sha256: str
    source_read_ref: str
    source_event_sha256: str
    facts_sha256: str
    published_epoch_seconds: int

    def __post_init__(self):
        if (type(self.schema) is not str or type(self.operation) is not str
                or self.schema != PUBLICATION_SCHEMA or self.operation != PUBLICATION_OPERATION):
            raise ValueError("publication schema or operation is invalid")
        for field, pattern in _RECEIPT_PATTERNS.items():
            value = getattr(self, field)
            if type(value) is not str or re.fullmatch(pattern, value) is None:
                raise ValueError("publication identity is invalid")
        if (type(self.published_epoch_seconds) is not int
                or not 0 <= self.published_epoch_seconds <= MAX_EPOCH_SECONDS):
            raise ValueError("publication timestamp is invalid")

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in dataclasses.fields(cls)}:
            raise ValueError("publication receipt fields changed")
        return cls(**value)


def build_publication_receipt(
    *, grant: DialogueWakeCanaryActivationGrant, current: DialogueWakeCanaryCurrentFacts,
    transaction_id: str, control_config_sha256: str, worker_config_sha256: str,
    source_read_ref: str, source_event_sha256: str, published_epoch_seconds: int,
) -> DialogueWakeCanaryPublicationReceipt:
    match = match_dialogue_wake_canary_activation(
        grant, current=current, now_epoch_seconds=published_epoch_seconds,
    )
    if match is None:
        raise ValueError("publication requires a bounded grant")
    return DialogueWakeCanaryPublicationReceipt(
        schema=PUBLICATION_SCHEMA, operation=PUBLICATION_OPERATION,
        transaction_id=transaction_id, installed_release_sha=current.installed_release_sha,
        grant_digest=match.grant_digest,
        control_config_sha256=control_config_sha256,
        worker_config_sha256=worker_config_sha256,
        source_read_ref=source_read_ref, source_event_sha256=source_event_sha256,
        facts_sha256=canonical_digest(current.to_dict()),
        published_epoch_seconds=published_epoch_seconds,
    )


def verify_publication_receipt(
    receipt: DialogueWakeCanaryPublicationReceipt, *,
    grant: DialogueWakeCanaryActivationGrant, installed_release_sha: str,
    control_config_sha256: str, worker_config_sha256: str,
) -> None:
    """Check sealed publication provenance; the effect guard checks fresh facts."""
    if (type(receipt) is not DialogueWakeCanaryPublicationReceipt
            or type(grant) is not DialogueWakeCanaryActivationGrant):
        raise ValueError("typed publication evidence is required")
    current = DialogueWakeCanaryCurrentFacts(**{
        field: getattr(grant, field) for field in IDENTITY_FIELDS
    })
    # This is the archived publication fact tuple, not a live-current assertion.
    expected = build_publication_receipt(
        grant=grant, current=current, transaction_id=receipt.transaction_id,
        control_config_sha256=control_config_sha256,
        worker_config_sha256=worker_config_sha256,
        source_read_ref=receipt.source_read_ref, source_event_sha256=receipt.source_event_sha256,
        published_epoch_seconds=receipt.published_epoch_seconds,
    )
    if receipt != expected or receipt.installed_release_sha != installed_release_sha:
        raise ValueError("publication evidence disagrees with installed configuration")
