"""Host-generation evidence-lock composition outside the inert Agent Eval core.

This explicitly invoked bridge consumes finalized Agent Evaluation run receipts
plus the canonical Executive host-capacity snapshot. It lives OUTSIDE
``scripts.agent_eval`` so that package keeps its unconditional no-control-plane
import rule. Neither the core nor its CLI imports this bridge; do not add a
compatibility shim back into that package. The bridge imports only the two
pure Executive host-contract modules, covered by its own dependency/inertness
regressions.  It does not persist a new schema,
allocate hosts, choose routes, rank workers, or widen the evaluation lifecycle.

A run is *evidence-locked* to a host observation only when its immutable
``evidence.artifacts`` list binds the exact canonical Agent Evaluation
``sha256:<64 hex>`` digest of ``mastermind.host_capacity_snapshot/v1`` bytes.
A pair passes this verifier only when both bound snapshots validate under the
Executive owner and expose the same opaque ``host_ref`` and ``boot_ref``.

Important proof ceiling: this does **not** prove that either run's process
actually executed on the referenced host generation.  Current Agent Evaluation
run v1 does not bind an Executive Job/Attempt/Worker identity or another
owner-native process-to-host receipt strongly enough to make that causal claim.
A later producer integration must supply that evidence before a comparison may
claim full execution-host factor equality.

The resulting verdict is intentionally narrow.  It proves immutable run-to-
host-snapshot evidence binding plus snapshot identity parity.  It does not
prove process-to-host causality, provider-principal, harness, model, context,
tool, retry, or full environment parity and therefore cannot by itself
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

HOST_FACTOR_EVIDENCE_LOCK_SCOPE = "HOST_FACTOR_EVIDENCE_LOCK_VERIFIED"


def _refuse(path: str, code: str, message: str) -> None:
    raise ContractError([ContractDefect(path, code, message)])


def host_capacity_snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    """Return the canonical Agent Evaluation digest for one host snapshot.

    Agent Evaluation's persisted digest contract is ``sha256:<64 lower hex>``.
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
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _bound_host_evidence(
    run: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    side: str,
) -> dict[str, Any]:
    """Validate one run and prove it binds the supplied host snapshot bytes."""

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


def verify_host_factor_evidence_lock(
    left_run: Mapping[str, Any],
    left_snapshot: Mapping[str, Any],
    right_run: Mapping[str, Any],
    right_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove that two finalized runs bind the same host-generation evidence.

    This verifier is fail-closed.  A missing run-to-snapshot evidence binding,
    malformed owner snapshot, host mismatch, or boot mismatch refuses the
    evidence lock.  The returned projection deliberately omits artifact paths,
    any process-to-host assertion, and any routing/admission recommendation.
    """

    left = _bound_host_evidence(left_run, left_snapshot, side="left")
    right = _bound_host_evidence(right_run, right_snapshot, side="right")

    if left["run_id"] == right["run_id"]:
        _refuse(
            "$.runs",
            "HOST_FACTOR_RUN_DUPLICATE",
            "host-factor evidence lock requires two distinct finalized runs",
        )

    defects: list[ContractDefect] = []
    if left["host_ref"] != right["host_ref"]:
        defects.append(
            ContractDefect(
                "$.host_ref",
                "HOST_FACTOR_HOST_MISMATCH",
                "host-evidence-locked runs must reference the same opaque host_ref",
            )
        )
    if left["boot_ref"] != right["boot_ref"]:
        defects.append(
            ContractDefect(
                "$.boot_ref",
                "HOST_FACTOR_BOOT_MISMATCH",
                "host-evidence-locked runs must reference the same boot_ref generation",
            )
        )
    if defects:
        raise ContractError(defects)

    return {
        "scope": HOST_FACTOR_EVIDENCE_LOCK_SCOPE,
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
    "HOST_FACTOR_EVIDENCE_LOCK_SCOPE",
    "host_capacity_snapshot_digest",
    "verify_host_factor_evidence_lock",
]
