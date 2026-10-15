"""A sanitized one-file Fleet export crosses OS UIDs, never private observer paths."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from control_plane.fleet_health_handoff import (
    HANDOFF_FILE, publish_fleet_health_handoff, read_fleet_health_handoff,
)

NOW = 1_791_890_400


def roots(tmp_path: Path) -> tuple[Path, Path]:
    observer = tmp_path / "private-fabric"
    state = observer / "state" / "hosts"
    state.mkdir(parents=True)
    (observer / "hosts.json").write_text(json.dumps({
        "ubuntu2": {"platform": "linux", "ram_gb": 32,
                    "ssh_alias": "PRIVATE_FABRIC_ALIAS", "roles": ["lanes"]}}))
    (state / "ubuntu2.json").write_text(json.dumps({
        "host": "ubuntu2", "ts": NOW, "reachable": True, "ncpu": 32,
        "active_lanes": 1, "active_lanes_status": "known",
        "lane_occupancy": {"active": 1}, "load1": 1.5,
        "thermal": {"schema": "mastermind.fabric_host_thermal.v1",
                    "source": "linux_hwmon", "observed_at": NOW,
                    "cpu_sensor_kind": "amd_tctl", "cpu_tctl_c": 55}}))
    stamp = datetime.fromtimestamp(NOW - 60, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    (observer / "state" / "host_pull.log").write_text(
        f"{stamp} [pull] host=ubuntu2 rc=0 secs=1 reachable=true tctl_c=55 active_lanes=1\n")
    shared = tmp_path / "shared-export"
    shared.mkdir(mode=0o700)
    return observer, shared


def test_publisher_sanitizes_all_windows_and_reader_never_accesses_private_root(tmp_path):
    observer, shared = roots(tmp_path)
    receipt = publish_fleet_health_handoff(observer, shared, now=NOW)
    assert receipt["published"] is True
    assert receipt["host_count"] == 1
    export = shared / HANDOFF_FILE
    assert export.is_file()
    assert export.stat().st_mode & 0o777 == 0o644
    assert shared.stat().st_mode & 0o777 == 0o700
    public_bytes = export.read_bytes()
    assert b"PRIVATE_FABRIC_ALIAS" not in public_bytes
    assert str(observer).encode() not in public_bytes
    assert b"ssh_alias" not in public_bytes
    for window in ("1h", "24h", "7d", "30d"):
        result = read_fleet_health_handoff(shared, window=window, now=NOW + 60)
        assert result["schema"] == "mastermind.fleet_health.v1"
        assert result["availability"] == "AVAILABLE"
        assert result["admission_authoritative"] is False
        assert result["window"] == window
        assert result["hosts"][0]["metrics"]["cpu_temp_c"] == 55
        assert result["hosts"][0]["metrics"]["fabric_active_lanes"] == 1
        assert len(result["hosts"][0]["history"]) >= 1
        assert result["hosts"][0]["history"][0]["cpu_temp_c"] == 55
    # Reader is only given the shared directory; private source may disappear.
    (observer / "hosts.json").unlink()
    assert read_fleet_health_handoff(shared, window="24h", now=NOW + 60)["hosts"][0]["id"] == "ubuntu2"


def test_expired_or_future_export_is_unavailable_not_stale_success(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    for clock in (NOW - 1, NOW + 181):
        response = read_fleet_health_handoff(shared, window="24h", now=clock)
        assert response["availability"] == "UNAVAILABLE"
        assert response["hosts"] == []


def test_tampered_bundle_never_leaks_private_or_invalid_fields(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    filename = shared / HANDOFF_FILE
    base = json.loads(filename.read_text())
    for mutate in (
        lambda x: x.update(private_path="/Users/private"),
        lambda x: x["windows"]["24h"]["hosts"][0]["metrics"].update(cpu_temp_c=float("nan")),
        lambda x: x["windows"].pop("7d"),
        lambda x: x["windows"]["1h"].update(admission_authoritative=True),
        lambda x: x["windows"]["30d"].update(window="1h"),
    ):
        bad = json.loads(json.dumps(base))
        mutate(bad)
        filename.write_text(json.dumps(bad))
        result = read_fleet_health_handoff(shared, window="24h", now=NOW + 60)
        assert result["availability"] == "UNAVAILABLE"
        assert "private_path" not in json.dumps(result)


def test_symlink_handoff_is_refused_without_following(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    published = shared / HANDOFF_FILE
    original = shared / "existing.json"
    published.rename(original)
    published.symlink_to(original)
    assert read_fleet_health_handoff(shared, window="24h", now=NOW)["availability"] == "UNAVAILABLE"


def test_untrusted_export_dir_permissions_or_missing_directory_fail_closed(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    shared.chmod(0o777)
    assert read_fleet_health_handoff(shared, window="24h", now=NOW)["availability"] == "UNAVAILABLE"
    with pytest.raises(ValueError):
        publish_fleet_health_handoff(observer, shared, now=NOW + 60)
    shared.chmod(0o700)
    link = tmp_path / "symlink-shared"
    link.symlink_to(shared, target_is_directory=True)
    assert read_fleet_health_handoff(link, window="24h", now=NOW)["availability"] == "UNAVAILABLE"


def test_failed_publisher_does_not_relabel_prior_export_fresh(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    prior = (shared / HANDOFF_FILE).read_bytes()
    (observer / "hosts.json").unlink()
    with pytest.raises(ValueError):
        publish_fleet_health_handoff(observer, shared, now=NOW + 120)
    assert (shared / HANDOFF_FILE).read_bytes() == prior
    assert read_fleet_health_handoff(shared, window="1h", now=NOW + 181)["availability"] == "UNAVAILABLE"


def test_shared_export_is_single_latest_file_without_full_private_log(tmp_path):
    observer, shared = roots(tmp_path)
    first = publish_fleet_health_handoff(observer, shared, now=NOW)
    second = publish_fleet_health_handoff(observer, shared, now=NOW + 60)
    assert first["sha256"] != second["sha256"]
    assert {p.name for p in shared.iterdir()} == {HANDOFF_FILE}
    assert second["windows"] == ["1h", "24h", "7d", "30d"]
    assert second["admission_authoritative"] is False


def test_reader_rejects_non_enum_window(tmp_path):
    _, shared = roots(tmp_path)
    with pytest.raises(ValueError):
        read_fleet_health_handoff(shared, window="../hidden", now=NOW)


def test_atomic_replace_failure_keeps_prior_handoff_and_cleans_staging(tmp_path, monkeypatch):
    from control_plane import fleet_health_handoff as handoff
    observer, shared = roots(tmp_path)
    handoff.publish_fleet_health_handoff(observer, shared, now=NOW)
    prior = (shared / HANDOFF_FILE).read_bytes()

    def reject_replace(*args, **kwargs):
        raise OSError("simulated atomic publication refusal")

    monkeypatch.setattr(handoff.os, "replace", reject_replace)
    with pytest.raises(OSError):
        handoff.publish_fleet_health_handoff(observer, shared, now=NOW + 60)
    assert (shared / HANDOFF_FILE).read_bytes() == prior
    assert {p.name for p in shared.iterdir()} == {HANDOFF_FILE}


def test_world_writable_report_and_duplicate_json_fields_fail_closed(tmp_path):
    observer, shared = roots(tmp_path)
    publish_fleet_health_handoff(observer, shared, now=NOW)
    report = shared / HANDOFF_FILE
    report.chmod(0o666)
    assert read_fleet_health_handoff(shared, window="24h", now=NOW)["availability"] == "UNAVAILABLE"
    report.chmod(0o644)
    contents = report.read_text()
    report.write_text(contents.replace('"generated_at":', '"generated_at":0,"generated_at":', 1))
    assert read_fleet_health_handoff(shared, window="24h", now=NOW)["availability"] == "UNAVAILABLE"
