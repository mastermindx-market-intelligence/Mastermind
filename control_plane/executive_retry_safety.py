"""Pure, fail-closed retry-safety classification for Executive Attempts.

This module has no Runtime dependency and owns no lifecycle state.  Callers must
re-derive the immutable evidence from the existing Executive Job, Attempt, Event,
and Operator Harness owners before requesting a classification.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from typing import Any


_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class RetrySafety(str, enum.Enum):
    """Closed evidence causes accepted by the retry-safety fence."""

    SAFE_PRE_EFFECT_INFRASTRUCTURE = "SAFE_PRE_EFFECT_INFRASTRUCTURE"
    SAFE_NON_MODIFYING_QUOTA_ROLLOVER = "SAFE_NON_MODIFYING_QUOTA_ROLLOVER"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    GENERIC_FAILED = "GENERIC_FAILED"
    SEMANTIC_FAILED = "SEMANTIC_FAILED"
    UNKNOWN = "UNKNOWN"


class RetrySafetyDecision(str, enum.Enum):
    """The complete closed decision set; only one value permits requeue."""

    SAFE_REQUEUE = "SAFE_REQUEUE"
    NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
    NEEDS_SOL = "NEEDS_SOL"
    TERMINAL_NO_RETRY = "TERMINAL_NO_RETRY"


@dataclasses.dataclass(frozen=True)
class RetrySafetyEvidence:
    """Immutable, transport-free evidence for one current Executive Attempt."""

    retry_safety: RetrySafety
    terminal_status: str
    job_id: str
    attempt_id: str
    attempt_job_id: str
    current_attempt_id: str | None
    provenance_digest: str | None
    retry_lineage_available: bool
    effect_unknown: bool
    writer_or_provider_generation_live: bool
    candidate_present: bool
    result_present: bool
    seal_present: bool
    effective_grant_non_modifying: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the closed canonical payload used solely for its digest."""

        value = dataclasses.asdict(self)
        safety = value["retry_safety"]
        value["retry_safety"] = (
            safety.value if isinstance(safety, RetrySafety) else str(safety)
        )
        return value

    @property
    def evidence_digest(self) -> str:
        """Stable digest of all classification inputs, including ignored status text."""

        encoded = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _attempt_is_current(evidence: RetrySafetyEvidence) -> bool:
    return bool(
        isinstance(evidence.job_id, str)
        and evidence.job_id
        and isinstance(evidence.attempt_id, str)
        and evidence.attempt_id
        and evidence.attempt_job_id == evidence.job_id
        and evidence.current_attempt_id == evidence.attempt_id
    )


def _has_exact_provenance(evidence: RetrySafetyEvidence) -> bool:
    return bool(
        isinstance(evidence.provenance_digest, str)
        and _DIGEST_RE.fullmatch(evidence.provenance_digest)
    )


def _has_unresolved_effect_evidence(evidence: RetrySafetyEvidence) -> bool:
    return bool(
        evidence.effect_unknown is not False
        or evidence.writer_or_provider_generation_live is not False
        or evidence.candidate_present is not False
        or evidence.result_present is not False
        or evidence.seal_present is not False
    )


def classify_retry_safety(evidence: RetrySafetyEvidence) -> RetrySafetyDecision:
    """Classify one exact Attempt without reading state or trusting error strings.

    The two safe paths intentionally require both a closed typed cause and every
    shared integrity predicate.  All other causes are conservative holds or an
    explicit terminal no-retry decision.
    """

    if evidence.retry_lineage_available is not True:
        return RetrySafetyDecision.TERMINAL_NO_RETRY
    if not _attempt_is_current(evidence):
        return RetrySafetyDecision.NEEDS_RECONCILIATION
    if not _has_exact_provenance(evidence):
        return RetrySafetyDecision.NEEDS_SOL
    if _has_unresolved_effect_evidence(evidence):
        return RetrySafetyDecision.NEEDS_RECONCILIATION
    if evidence.retry_safety is RetrySafety.SAFE_PRE_EFFECT_INFRASTRUCTURE:
        if evidence.terminal_status == "LOST":
            return RetrySafetyDecision.SAFE_REQUEUE
        return RetrySafetyDecision.NEEDS_SOL
    if evidence.retry_safety is RetrySafety.SAFE_NON_MODIFYING_QUOTA_ROLLOVER:
        if (
            evidence.terminal_status == "RATE_LIMITED"
            and evidence.effective_grant_non_modifying is True
        ):
            return RetrySafetyDecision.SAFE_REQUEUE
        return RetrySafetyDecision.NEEDS_RECONCILIATION
    if evidence.retry_safety is RetrySafety.EFFECT_UNKNOWN:
        return RetrySafetyDecision.NEEDS_RECONCILIATION
    return RetrySafetyDecision.NEEDS_SOL


__all__ = [
    "RetrySafety",
    "RetrySafetyDecision",
    "RetrySafetyEvidence",
    "classify_retry_safety",
]
