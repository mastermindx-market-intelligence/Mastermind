"""Read-only direct service answer projection using the existing Runtime owner.

No new Runtime, store, queue, SQL access, provider result writer, auth plane or
completion path is created here. A test-owned namespace can prove SAME, but
installed custody and raw-provider/collection attestation are separate gates.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from control_plane.executive_inference_contract import DIRECT_RESULT_VIEW_SCHEMA, MAX_RESULT_BYTES
from control_plane.executive_inference_io import canonical_bytes
from control_plane.executive_runtime import Runtime, StateConflict


def _observe(runtime: Runtime, operation_key: str, reference: Mapping[str, Any] | None,
             *, include_receipt: bool = False):
    if not isinstance(runtime, Runtime):
        raise StateConflict("canonical Runtime owner is required")
    with runtime.observe_bounded_read() as observation:
        material = observation.read_service_inference_bounded(
            operation_key, reference=reference, include_receipt=include_receipt
        )
    generation = observation.receipt.to_dict()
    if generation["state"] != "SAME":
        raise StateConflict("service result generation is not qualified for publication")
    if material is not None:
        if material.get("observation_source_identity") != generation["source_identity"]:
            raise StateConflict("service result observation identity does not match finalized receipt")
        material = {key: value for key, value in material.items()
                    if key != "observation_source_identity"}
    return material, generation


def terminal_status_from_runtime(runtime: Runtime, operation_key: str) -> dict | None:
    """Read the original fingerprint and reference in ONE source observation."""
    material, _generation = _observe(runtime, operation_key, None, include_receipt=True)
    if material is None:
        return None
    return {"receipt": material["receipt"],
            "reference": (dict(material["reference"])
                          if material["reference"] is not None else None)}


def terminal_reference_from_runtime(runtime: Runtime, operation_key: str) -> dict | None:
    """Resolve only an already-committed service result's exact reference.

    QUEUED, RUNNING, missing and failed services yield no terminal reference.
    This must not be interpreted as service completion or execution authority.
    """
    material, _generation = _observe(runtime, operation_key, None)
    return dict(material["reference"]) if material is not None else None


def direct_result_from_runtime(
    runtime: Runtime,
    operation_key: str,
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a complete direct result; refuse any unknown or changed generation.

    The result reader does not vouch for how the direct document was written.
    Production publication additionally needs the Supervisor's validated
    collector/terminal writer and the existing authenticated service App.
    """
    material, generation = _observe(runtime, operation_key, reference)
    if material is None or "document" not in material:
        raise StateConflict("original service operation is not complete")
    result = {
        "schema": DIRECT_RESULT_VIEW_SCHEMA,
        "operation_ref": material["intent_id"],
        "reference": material["reference"],
        "request_fingerprint": material["request_fingerprint"],
        "generation": generation,
        "availability": "AVAILABLE",
        "execution_status": "COMPLETED",
        "content_complete": True,
        "acceptance": "NOT_PROJECTED",
        "document": material["document"],
    }
    if len(canonical_bytes(result)) > MAX_RESULT_BYTES:
        raise StateConflict("direct result exceeds the existing I/O budget")
    return result
