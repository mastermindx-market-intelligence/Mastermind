"""Host-generation factor-lock verification for Agent Evaluation.

This module consumes existing finalized Agent Evaluation run receipts plus the
canonical Executive host-capacity snapshot.  It does not persist a new schema,
allocate hosts, choose routes, rank workers, or widen the evaluation lifecycle.

A run proves a host observation only when its immutable ``evidence.artifacts``
list already binds the exact SHA-256 digest of the canonical host-capacity
snapshot bytes.  A pair is host-factor-locked only when both bound snapshots
validate under the Executive owner and expose the same opaque ``host_ref`` and
``boot_ref``.

The resulting verdict is intentionally narrow: it proves host/boot identity
parity for the pair.  It does not prove provider-principal, harness, model,
context, tool, retry, or full environment parity and therefore cannot by itself
establish a MODEL_EFFECT or HARNESS_EFFECT claim.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from control_plane.executive_host_capacity import (
    HostCapacityContractError,
    canonical_host_capacity_json,
    validate_host_capacity_snapshot,
)
from scripts.agent_eval import contracts
from scripts.agent_eval.errors import ContractDefect, ContractError

HOST_FACTOR_LOCK_SCOPE = "HOST_FACTOR_LOCK_VERIFIED"


def _refuse(path: str, code: str, message: str) -> None:
    raise ContractError([ContractDefect(path, code, message)])


def host_capacity_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Return the digest of one valid canonical host-capacity snapshot.

    The Executive host-capacity owner remains authoritative for snapshot shape
    and normalization.  Hostile snapshot values are never echoed into Agent
    Evaluation errors.
    """

    try:
        payload = canonical_host_capacity_json(snapshot)
    except (HostCapacityContractError, TypeError, AttributeError) as exc:
        raise ContractError(
            [
                ContractDefect(
                    "$.host_capacity_snapshot",
                    "HOST_CAPACITY_SNAPSHOT_INVALID",
                    "host-capacity snapshot failed the canonical Executive contract",
                )
            ]
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _bound_host_identity(
    run: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    """Validate one run and prove it binds the supplied host snapshot."""

    contracts.validate_run_shape(run)
    try:
        normalized = validate_host_capacity_snapshot(snapshot)
    except (HostCapacityContractError, TypeError, AttributeError) as exc:
        raise ContractError(
            [
                ContractDefect(
                    f"$.{side}.host_capacity_snapshot",
                    "HOST_CAPACITY_SNAPSHOT_INVALID",
                    "host-capacity snapshot failed the canonical Executive contract",
                )
            ]
        ) from exc

    digest = host_capacity_snapshot_digest(normalized)
    artifacts = run["evidence"]["artifacts"]
    matches = [item for item in artifacts if item["digest"] == digest]
    if not matches:
        _refuse(
            f"$.{side}.run.evidence.artifacts",
            "HOST_CAPACITY_EVIDENCE_MISSING",
            "run does not bind the supplied canonical host-capacity snapshot digest",
        )
    if len(matches) != 1:
        _refuse(
            f"$.{side}.run.evidence.artifacts",
            "HOST_CAPACITY_EVIDENCE_AMBIGUOUS",
            "run binds the supplied host-capacity digest more than once",
        )

    return {
        "run_id": run["run_id"],
        "run_digest": run["run_digest"],
        "host_ref": normalized["host_ref"],
        "boot_ref": normalized["boot_ref"],
        "snapshot_digest": digest,
        "observed_at_ms": normalized["observed_at_ms"],
    }


def verify_host_factor_lock(
    left_run: Mapping[str, Any],
    left_snapshot: Mapping[str, Any],
    right_run: Mapping[str, Any],
    right_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove that two finalized runs used the same opaque host generation.

    This verifier is fail-closed.  A missing run-to-snapshot evidence binding,
    malformed owner snapshot, host mismatch, or boot mismatch refuses the
    factor lock.  The returned projection deliberately omits artifact paths and
    any routing/admission recommendation.
    """

    left = _bound_host_identity(left_run, left_snapshot, side="left")
    right = _bound_host_identity(right_run, right_snapshot, side="right")

    defects: list[ContractDefect] = []
    if left["host_ref"] != right["host_ref"]:
        defects.append(
            ContractDefect(
                "$.host_ref",
                "HOST_FACTOR_HOST_MISMATCH",
                "factor-locked runs must use the same opaque host_ref",
            )
        )
    if left["boot_ref"] != right["boot_ref"]:
        defects.append(
            ContractDefect(
                "$.boot_ref",
                "HOST_FACTOR_BOOT_MISMATCH",
                "factor-locked runs must use the same boot_ref generation",
            )
        )
    if defects:
        raise ContractError(defects)

    return {
        "scope": HOST_FACTOR_LOCK_SCOPE,
        "host_ref": left["host_ref"],
        "boot_ref": left["boot_ref"],
        "left": {
            "run_id": left["run_id"],
            "run_digest": left["run_digest"],
            "snapshot_digest": left["snapshot_digest"],
            "observed_at_ms": left["observed_at_ms"],
        },
        "right": {
            "run_id": right["run_id"],
            "run_digest": right["run_digest"],
            "snapshot_digest": right["snapshot_digest"],
            "observed_at_ms": right["observed_at_ms"],
        },
    }


__all__ = [
    "HOST_FACTOR_LOCK_SCOPE",
    "host_capacity_snapshot_digest",
    "verify_host_factor_lock",
]
