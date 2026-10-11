"""Exact Linux v2 structural composition; fixtures only, never host reads."""
from __future__ import annotations

from dataclasses import replace
import pytest

from control_plane import executive_host_capacity as hc
from ops.executive_os import linux_capacity_facts as lf
from ops.executive_os.linux_native_capacity_composition import compose_native_linux_capacity
import test_executive_native_host_capacity as reference
import test_linux_capacity_facts as fx


def composed(**overrides):
    params = {
        "reads": fx.inputs(),
        "scope": fx.scope(),
        "window": fx.window(),
        "disk": fx.disk(),
        "binding": reference.binding(),
        "total_observation_window_ms": 1000,
    }
    params.update(overrides)
    return compose_native_linux_capacity(**params)


def test_exact_reference_wire_and_observation_only_read_model():
    actual = composed()
    assert hc.canonical_native_host_capacity_json(actual) == (
        hc.canonical_native_host_capacity_json(reference.snapshot())
    )
    assert len(actual["metrics"]) == 35
    assert actual["unknown_fields"] == []
    assert actual["telemetry_status"] == "COMPLETE"
    observed = hc.project_native_host_capacity(
        actual, expected_binding=reference.binding(), now_ms=100100, max_age_ms=5000
    )
    assert observed["capability"] == "OBSERVATION_ONLY"
    assert observed["admission_state"] == "NOT_EVALUATED"
    assert observed["can_place_work"] is False
    assert observed["metrics"]["pool_total_bytes"]["value"] == 10000 * 4096
    assert observed["metrics"]["disk_usable_bytes"]["value"] == 5000 * 4096


def test_source_reads_and_binding_are_not_mutated():
    reads = fx.inputs()
    binding = reference.binding()
    prior_reads, prior_binding = dict(reads), dict(binding)
    composed(reads=reads, binding=binding)
    assert (reads, binding) == (prior_reads, prior_binding)


@pytest.mark.parametrize("kind", ["missing", "permission_denied"])
def test_missing_kernel_psi_stays_typed_partial(kind):
    reads = fx.inputs()
    reads["pressure_memory"] = lf.Read(
        None, failure=lf.Reason.MISSING if kind == "missing" else lf.Reason.PERMISSION_DENIED
    )
    value = composed(reads=reads)
    affected = sorted(
        key for key in value["metrics"]
        if key.startswith("memory_") and ("some_" in key or "full_" in key)
    )
    assert value["telemetry_status"] == "PARTIAL"
    assert value["unknown_fields"] == affected
    reason = "MISSING" if kind == "missing" else "PERMISSION_DENIED"
    for key in affected:
        assert value["metrics"][key] == {"value": None, "null_reason": reason}
    assert hc.project_native_host_capacity(
        value, expected_binding=reference.binding(), now_ms=100100, max_age_ms=5000
    )["can_place_work"] is False


@pytest.mark.parametrize(
    "disk,reason",
    [
        (replace(fx.disk(), qualified_local_mount=False), "SCOPE_UNQUALIFIED"),
        (replace(fx.disk(), after=(8, 1, 51)), "SOURCE_MOVED"),
        (replace(fx.disk(), expected=(8, 1, 51)), "MOUNT_MISMATCH"),
    ],
)
def test_disk_and_pool_share_same_qualified_mount(disk, reason):
    value = composed(disk=disk)
    for field in ("disk_usable_bytes", "pool_total_bytes"):
        assert value["metrics"][field] == {"value": None, "null_reason": reason}
    assert value["telemetry_status"] == "PARTIAL"
    assert {"disk_usable_bytes", "pool_total_bytes"} <= set(value["unknown_fields"])


@pytest.mark.parametrize("total", [0, True, 999, 5001, 1.25, "1000"])
def test_total_window_is_explicit_and_bounded(total):
    with pytest.raises(hc.HostCapacityContractError, match="NATIVE_WINDOW_INVALID"):
        composed(total_observation_window_ms=total)


@pytest.mark.parametrize(
    "window,reason",
    [
        (replace(fx.window(), boot_after="aaaaaaaa-2222-3333-4444-555555555555"), lf.Reason.BOOT_DRIFT),
        (replace(fx.window(), max_age_ms=1000), lf.Reason.STALE),
        (replace(fx.window(), source_after=2), lf.Reason.SOURCE_MOVED),
    ],
)
def test_entire_snapshot_refuses_untrusted_window(window, reason):
    with pytest.raises(lf.ObservationError) as failure:
        composed(window=window)
    assert failure.value.reason is reason


def test_owner_binding_is_validated_but_does_not_claim_authenticity():
    malformed = reference.binding()
    malformed["source_generation_sha256"] = "not-a-digest"
    with pytest.raises(hc.HostCapacityContractError):
        composed(binding=malformed)
    value = composed()
    other = reference.binding()
    other["namespace_sha256"] = "8" * 64
    with pytest.raises(hc.HostCapacityContractError, match="NATIVE_BINDING_MISMATCH"):
        hc.project_native_host_capacity(
            value, expected_binding=other, now_ms=100100, max_age_ms=5000
        )


def test_extra_untrusted_capture_field_does_not_enter_closed_wire():
    reads = fx.inputs()
    reads["provider_credentials"] = lf.Read(b"secret\n")
    with pytest.raises(lf.ObservationError):
        composed(reads=reads)
