"""History selection must not read 30 days of source bytes for a 1h chart.

A larger bounded 30d read is needed at the current incumbent collector's
observed ~0.6 MB/day cadence, while short windows remain economical.
"""
import json

import pytest

from control_plane import fleet_health as collector


@pytest.mark.parametrize(("window", "limit"), [
    ("1h", 1 * 1024 * 1024),
    ("24h", 2 * 1024 * 1024),
    ("7d", 8 * 1024 * 1024),
    ("30d", 32 * 1024 * 1024),
])
def test_bounded_log_read_scales_with_requested_history_window(tmp_path, monkeypatch, window, limit):
    state = tmp_path / "state" / "hosts"
    state.mkdir(parents=True)
    (tmp_path / "hosts.json").write_text(json.dumps({"ubuntu2": {"platform": "linux"}}))
    (state / "ubuntu2.json").write_text(json.dumps({"host": "ubuntu2", "ts": 1791890400,
        "reachable": True, "ncpu": 32, "load1": 1.0, "active_lanes": 0, "active_lanes_status": "known"}))
    (tmp_path / "state" / "host_pull.log").write_text("")
    original = collector._read_at
    seen = []

    def observed(directory, filename, budget, **kwargs):
        if filename == "host_pull.log":
            seen.append((budget, kwargs.get("tail")))
        return original(directory, filename, budget, **kwargs)

    monkeypatch.setattr(collector, "_read_at", observed)
    result = collector.read_fleet_health(tmp_path, window=window, now=1791890400)
    assert result["availability"] == "AVAILABLE"
    assert seen == [(limit, True)]
