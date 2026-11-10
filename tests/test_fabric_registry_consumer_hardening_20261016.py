"""Release-candidate contract for the existing Ubuntu Fabric registry repair.

This checks the GitHub source patch, not M2 host policy or a live lease.
It intentionally cannot install, increase capacity, dispatch, or seal a runtime.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "integrations" / "fleet" / "ubuntu_thermal_headroom_20261013"
AUDIT = FLEET / "FABRIC_REGISTRY_CONSUMER_HARDENING_20261015.patch"
COMBINED = FLEET / "FABRIC_COMBINED_SPARSE_AND_CPU_SCOPE_20261015.patch"
AUDIT_SHA256 = "7f80ddfd5a9bb6961e02c2a86bcc1866bd3e92ff4f4222c88fd2b7c5cd976e17"
OWNED_PATHS = {
    "host_pick.py",
    "pool_status.py",
    "host_pull_backend.py",
    "remote_lane_v8.sh",
    "lease_broker.py",
    "tests/test_hosts_registry.py",
    "tests/test_host_pull_selected.py",
    "tests/test_host_aware_pick.py",
    "tests/test_auto_host_pick.py",
    "tests/test_registry_metadata_filter.py",
    "tests/test_five_host_enrollment.py",
    "tests/test_sub_host_policy.py",
    "tests/test_host_admitted_grok_cursor_20261012.py",
}


def _patched_paths(data: str) -> list[str]:
    return re.findall(r"(?m)^\+\+\+ b/(.+)$", data)


def test_exact_installed_delta_is_preserved_as_source() -> None:
    data = AUDIT.read_bytes()
    assert hashlib.sha256(data).hexdigest() == AUDIT_SHA256
    paths = _patched_paths(data.decode("utf-8"))
    assert len(paths) == len(set(paths)) == 13
    assert set(paths) == OWNED_PATHS


def test_no_host_policy_or_native_worker_release_rewrite() -> None:
    # The historic 12/18/12/12 host caps, thermal gates, provider/lease
    # custody and current emergency derates are not authored by this patch.
    audit = AUDIT.read_text()
    paths = set(_patched_paths(audit))
    assert "hosts.json" not in paths
    assert not paths.intersection({"lane_runtime.py", "fabric_task.py",
                                    "remote_sub.sh", "remote_sub_exec.py",
                                    "support_bundle.py", "slot.py"})
    assert not re.search(r"(?m)^(?:--- a|\+\+\+ b)/hosts\.json$", audit)


def test_sparse_and_cpu_release_remains_a_distinct_combined_candidate() -> None:
    # Never compose the older standalone CPU/sparse patches over one another.
    # The installed registry-delta is compatible with their single combined
    # controller patch because there are no common changed source paths.
    audit = set(_patched_paths(AUDIT.read_text()))
    combined = set(_patched_paths(COMBINED.read_text()))
    assert combined == {"fabric_task.py", "remote_sub.sh",
                        "remote_sub_exec.py", "support_bundle.py",
                        "fabric_cpu_scope.py"}
    assert audit.isdisjoint(combined)


def test_pseudo_host_refused_and_local_readiness_still_fail_closed() -> None:
    data = AUDIT.read_text()
    assert data.count('+') > 0
    assert '+            if str(name).startswith("_") or not isinstance(entry, dict):' in data
    assert '+        if field == "max_active" and value > 32:' in data
    assert '-        if field == "max_active" and value > 8:' in data
    assert "test_metadata_cannot_multiply_host_admitted_fleet_capacity" in data
    assert "test_missing_account_validator_keeps_telemetry_but_grants_no_readiness" in data
    assert "ImportError):" in data
