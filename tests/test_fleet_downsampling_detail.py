"""Bounded trend charts retain time-shape and true extrema across long periods."""
from control_plane.fleet_health import _downsample, HISTORY_METRICS


def test_long_constant_history_retains_regular_shape_samples_not_only_endpoints():
    rows = [{"timestamp": i * 60 + 1, **{k: 0 for k in HISTORY_METRICS}}
            for i in range(1000)]
    retained = _downsample(rows)
    assert len(retained) <= 360
    assert len(retained) >= 100
    assert retained[0]["timestamp"] == rows[0]["timestamp"]
    assert retained[-1]["timestamp"] == rows[-1]["timestamp"]
    assert max(b["timestamp"] - a["timestamp"] for a, b in zip(retained, retained[1:])) <= 15 * 60
    assert not any(item["gaps"] for item in retained)
