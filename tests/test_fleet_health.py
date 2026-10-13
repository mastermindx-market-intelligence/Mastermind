"""Fleet diagnostics: real missingness, bounded history, no placement authority."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

try:
    from control_plane.fleet_health import compose_fleet_health, read_fleet_health
except ImportError:
    compose_fleet_health = read_fleet_health = None

NOW = 1_791_890_400.0  # a fixed minute boundary, not the running host clock
GIB = 1024 ** 3


def registry():
    return {"_doc": {"notes": "metadata is not a host"},
            "ubuntu2": {"platform": "linux", "ram_gb": 32, "ssh_alias": "ubuntu2",
                        "cpu_tctl_limit_c": 85, "roles": ["lanes"]}}


def sample(**changes):
    result = {"host": "ubuntu2", "ts": NOW, "reachable": True,
              "ncpu": 32, "load1": 2.0, "load5": 3.0,
              "mem_free_gb": 16, "disk_free_gb": 100,
              "active_lanes": 0, "active_lanes_status": "known",
              "lane_occupancy": {"active": 0}, "process_active_lanes": 7,
              "thermal": {"schema": "mastermind.fabric_host_thermal.v1",
                          "source": "linux_hwmon", "observed_at": NOW,
                          "cpu_sensor_kind": "amd_tctl", "cpu_tctl_c": 50,
                          "nvme_hottest_c": 35, "nvme_margin_crit_c": 40,
                          "cpu_fan_rpm": None},
              "granular": {"schema": "mastermind.fabric_host_granular.v1",
                           "source": "linux_procfs", "observed_at": NOW,
                           "cpu_busy_pct": 0, "mem_available_bytes": 16 * GIB,
                           "mem_total_bytes": 32 * GIB, "swap_used_bytes": 0}}
    result.update(changes)
    return result


def line(ts, values="tctl_c=90 cpu_busy_pct=99 load1=32 active_lanes=4", host="ubuntu2"):
    stamp = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return f"{stamp} [pull] host={host} rc=0 secs=1 reachable=true {values}\n"


def compose(s=None, log="", reg=None, **options):
    assert callable(compose_fleet_health), "Fleet diagnostics producer is not implemented"
    return compose_fleet_health(reg or registry(), {"ubuntu2": s or sample()}, log,
                               window=options.pop("window", "24h"), now=NOW, **options)


def test_measured_zero_is_not_unknown_and_lanes_are_not_process_totals():
    d = compose()
    h = d["hosts"][0]
    assert d["schema"] == "mastermind.fleet_health.v1"
    assert d["admission_authoritative"] is False
    assert h["state"] == "CURRENT"
    assert h["metrics"]["cpu_busy_pct"] == 0
    assert h["metrics"]["fabric_active_lanes"] == 0
    assert h["metrics"]["process_lane_candidates"] == 7
    assert "SUBAGENT_COVERAGE_PARTIAL" in h["coverage"]
    assert h["metrics"]["memory_used_pct"] == 50
    assert h["metrics"]["fan_rpm"] is None


def test_old_snapshot_remains_stale_even_when_reachable_was_true():
    d = compose(sample(ts=NOW - 1000))
    h = d["hosts"][0]
    assert d["availability"] == "PARTIAL"
    assert h["state"] == "STALE"
    assert h["metrics"]["cpu_temp_c"] is None  # nested epoch mismatch
    assert not any(f["category"] == "hardware" for f in h["findings"])


@pytest.mark.parametrize("stamp", [True, float("nan"), float("inf"), NOW + 1, -1, "1791890400"])
def test_bad_or_future_snapshot_time_does_not_expose_metrics(stamp):
    h = compose(sample(ts=stamp))["hosts"][0]
    assert h["state"] == "UNKNOWN"
    assert h["observed_at"] is None
    assert all(v is None for v in h["metrics"].values())


def test_missing_host_and_offline_do_not_become_zero():
    assert callable(compose_fleet_health)
    missing = compose_fleet_health(registry(), {}, "", window="1h", now=NOW)["hosts"][0]
    offline = compose(sample(reachable=False))["hosts"][0]
    assert missing["state"] == "UNKNOWN"
    assert offline["state"] == "OFFLINE"
    assert missing["metrics"]["fabric_active_lanes"] is None
    assert offline["metrics"]["fabric_active_lanes"] is None


def test_numeric_validation_and_occupancy_conflict_are_not_coerced():
    s = sample(active_lanes=True, load1=float("inf"))
    s["granular"]["cpu_busy_pct"] = 101
    s["thermal"]["cpu_tctl_c"] = float("nan")
    h = compose(s)["hosts"][0]
    for key in ("fabric_active_lanes", "load1", "cpu_busy_pct", "cpu_temp_c"):
        assert h["metrics"][key] is None
    s = sample(active_lanes=2)
    assert compose(s)["hosts"][0]["metrics"]["fabric_active_lanes"] is None


def test_total_memory_is_not_fabricated_from_registry_capacity():
    s = sample()
    del s["granular"]["mem_total_bytes"]
    h = compose(s)["hosts"][0]
    assert h["metrics"]["memory_available_bytes"] == 16 * GIB
    assert h["metrics"]["memory_total_bytes"] is None
    assert h["metrics"]["memory_used_pct"] is None
    assert "MEMORY_TOTAL_UNAVAILABLE" in h["coverage"]


def test_host_identity_mismatch_fails_closed():
    h = compose(sample(host="other"))["hosts"][0]
    assert h["state"] == "UNKNOWN"
    assert all(v is None for v in h["metrics"].values())


def test_registry_transport_aliases_do_not_double_count_a_computer():
    r = {"m1": {"platform": "darwin", "ssh_alias": "m1", "roles": ["ci-runner"]},
         "bm1": {"platform": "darwin", "ssh_alias": "m1", "roles": ["lanes-shadow"]},
         "_metadata": {"platform": "linux"}}
    d = compose(reg=r)
    assert [h["id"] for h in d["hosts"]] == ["m1"]
    assert "REGISTRY_ALIASES_GROUPED" in d["hosts"][0]["coverage"]


def test_high_cpu_alone_is_not_a_hardware_damage_finding():
    s = sample()
    s["granular"]["cpu_busy_pct"] = 100
    assert not any(f["category"] == "hardware" for f in compose(s)["hosts"][0]["findings"])


def test_sustained_thermal_condition_requires_ten_minutes_and_current_evidence():
    s = sample()
    s["thermal"]["cpu_tctl_c"] = 90
    log = "".join(line(NOW - n * 60) for n in range(12, -1, -1))
    findings = compose(s, log)["hosts"][0]["findings"]
    f = next(f for f in findings if f["code"] == "SUSTAINED_THERMAL_HEADROOM")
    assert f["severity"] == "warning"
    assert f["duration_seconds"] >= 600
    assert "operator" in f["detail"].lower()
    assert "damage" in f["detail"].lower()
    assert "manufacturer" in f["detail"].lower()


def test_gaps_future_rows_and_duplicates_cannot_manufacture_sustained_heat():
    s = sample()
    s["thermal"]["cpu_tctl_c"] = 90
    log = "".join(line(NOW - n * 60) for n in (30, 29, 28, 2, 1, 0))
    log += line(NOW) + line(NOW + 600)
    h = compose(s, log)["hosts"][0]
    assert not any(f["code"] == "SUSTAINED_THERMAL_HEADROOM" for f in h["findings"])
    assert any("cpu_temp_c" in p["gaps"] for p in h["history"][1:])
    assert all(p["timestamp"] <= NOW for p in h["history"])


def test_cpu_saturation_is_a_performance_recommendation_after_thirty_minutes():
    s = sample()
    s["granular"]["cpu_busy_pct"] = 99
    log = "".join(line(NOW - n * 60, "tctl_c=50 cpu_busy_pct=99 active_lanes=4")
                  for n in range(32, -1, -1))
    h = compose(s, log)["hosts"][0]
    f = next(f for f in h["findings"] if f["code"] == "SUSTAINED_CPU_PRESSURE")
    assert f["category"] == "performance"
    assert not any(f["category"] == "hardware" for f in h["findings"])


def test_ram_history_is_missing_when_the_source_never_recorded_it():
    h = compose(log=line(NOW - 60))["hosts"][0]
    assert "MEMORY_HISTORY_INCOMPLETE" in h["coverage"]
    assert h["history"][0]["memory_used_pct"] is None


def test_downsampling_preserves_peaks_and_raw_gaps_not_fake_continuity():
    rows = []
    for n in range(1000):
        ts = NOW - (999 - n) * 60
        temp = 97 if n == 321 else 50
        rows.append(line(ts, f"tctl_c={temp} cpu_busy_pct=1 active_lanes=2"))
    d = compose(log="".join(rows))
    h = d["hosts"][0]
    assert len(h["history"]) <= 360
    assert max(p["cpu_temp_c"] or 0 for p in h["history"]) == 97
    assert d["history_truncated"] is True
    assert h["history"][0]["timestamp"] == NOW - 999 * 60


def test_source_inputs_are_not_mutated():
    s, r = sample(), registry()
    old = copy.deepcopy((s, r))
    compose(s, line(NOW), reg=r)
    assert (s, r) == old


def test_read_adapter_uses_only_registry_hosts_and_does_not_modify_sources(tmp_path):
    assert callable(read_fleet_health), "Fleet file reader is not implemented"
    (tmp_path / "state/hosts").mkdir(parents=True)
    (tmp_path / "hosts.json").write_text(json.dumps(registry()))
    p = tmp_path / "state/hosts/ubuntu2.json"
    p.write_text(json.dumps(sample()))
    (tmp_path / "state/hosts/unknown-manifest.json").write_text('{"credentials":"never publish"}')
    (tmp_path / "state/host_pull.log").write_text(line(NOW - 60))
    before = {str(f): f.read_bytes() for f in tmp_path.rglob("*") if f.is_file()}
    d = read_fleet_health(tmp_path, window="24h", now=NOW)
    assert [h["id"] for h in d["hosts"]] == ["ubuntu2"]
    assert "credentials" not in json.dumps(d)
    assert before == {str(f): f.read_bytes() for f in tmp_path.rglob("*") if f.is_file()}
    p.unlink()
    p.symlink_to(tmp_path / "hosts.json")
    assert read_fleet_health(tmp_path, window="24h", now=NOW)["hosts"][0]["state"] == "UNKNOWN"


@pytest.mark.parametrize("reg", [{"../escape": {"platform": "linux"}},
                                 {f"h{i}": {"platform": "linux"} for i in range(33)}])
def test_unsafe_or_over_budget_registry_is_unavailable(reg):
    assert compose(reg=reg)["availability"] == "UNAVAILABLE"


def test_invalid_window_and_clock_are_rejected():
    assert callable(compose_fleet_health)
    with pytest.raises(ValueError):
        compose(window="../../secret")
    with pytest.raises(ValueError):
        compose_fleet_health(registry(), {}, "", window="1h", now=float("nan"))
