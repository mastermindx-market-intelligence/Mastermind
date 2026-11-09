"""Compose existing Linux facts into the canonical observation-only v2 wire.

Consumes already-captured source-stamped facts. No host reads, privilege
escalation, identity enrollment, provider admission, signing, network I/O or
physical reservation. The installed collector/identity owner must independently
authenticate source, origin, namespace, cgroup ancestry and qualified mount.
A valid structural envelope is not an attestation of those external claims.
"""
from __future__ import annotations

from typing import Any, Mapping

from control_plane.executive_host_capacity import build_native_host_capacity_snapshot
from ops.executive_os import linux_capacity_facts as facts


def compose_native_linux_capacity(
    reads: Mapping[str, facts.Read],
    *,
    scope: facts.CgroupScope,
    window: facts.Window,
    disk: facts.Disk,
    binding: Mapping[str, str],
    total_observation_window_ms: int,
) -> dict[str, Any]:
    """Compose the 35-key v2 envelope from owner-injected receipts, never admit.

    The Packet-D parser owns measurements and typed nulls; the canonical v2
    builder owns keys, units, missingness, cross-field checks and the admission
    ceiling. The additional pool-total is qualified with the SAME disk evidence
    as unprivileged disk-usable bytes, not a separate filesystem or mount.

    The total span is captured by the upstream owner, not fabricated from
    the narrower two-point CPU sample. The v2 builder rejects invalid duration.
    """
    measurements = facts.observe(reads, scope=scope, window=window, disk=disk)

    def pool_total() -> int:
        facts.disk_usable_bytes(disk)
        return facts.product(disk.blocks, disk.frsize)

    measurements["pool_total_bytes"] = facts.measured(pool_total)
    metrics = {
        key: {
            "value": metric.value,
            "null_reason": metric.null_reason.value if metric.null_reason is not None else None,
        }
        for key, metric in measurements.items()
    }
    return build_native_host_capacity_snapshot(
        metrics,
        binding=binding,
        observed_at_ms=window.observed_at_ms,
        sample_window_ms=window.monotonic_end_ms - window.monotonic_start_ms,
        total_observation_window_ms=total_observation_window_ms,
    )


__all__ = ["compose_native_linux_capacity"]
