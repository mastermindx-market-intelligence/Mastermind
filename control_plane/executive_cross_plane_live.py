"""Read-only live-owner-to-cockpit composition for an already authorized caller.

This module introduces no route, credential, source client, polling loop, cache,
identity decision or lifecycle plane. The surrounding authenticated Control
Room owner, when available, supplies the existing injected owner read ports.
Canonical live acquisition, Session Truth and the existing cockpit projector
retain all normalization, identity, admission and freshness decisions.

Source-only until the original Control Room owner mounts it and demonstrates
signed-in, end-to-end application proof.
"""

from __future__ import annotations

from typing import Any

from control_plane.executive_cross_plane_view import build_cross_plane_view
from control_plane.session_truth import build_receipt
from control_plane.session_truth_live_acquire import (
    LiveOwnerPorts,
    LiveScope,
    acquire_live_session_truth_inputs,
)


async def acquire_live_cross_plane_view(
    *,
    scope: LiveScope,
    ports: LiveOwnerPorts,
    observed_started_at: str,
    observed_ended_at: str,
    stale_after_seconds: float | None = None,
) -> dict[str, Any]:
    """Acquire exactly once through injected owners; return one strict read-only view.

    The caller owns the observation clock and the security context. Source
    exceptions propagate rather than becoming success-shaped empty documents.
    No receipt is stored or published by this function.
    """

    inputs = await acquire_live_session_truth_inputs(scope=scope, ports=ports)
    receipt = build_receipt(
        inputs,
        observed_started_at=observed_started_at,
        observed_ended_at=observed_ended_at,
    )
    return build_cross_plane_view(
        receipt,
        evaluated_at=observed_ended_at,
        stale_after_seconds=stale_after_seconds,
        strict=True,
    )


__all__ = ["acquire_live_cross_plane_view"]
