"""Regression for Linux hygiene receipts under unresolved physical disk pressure.

All observations and state are simulated. No cleanup manager, host service,
Fabric worker, lease or real filesystem deletion is exercised.
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "ops/fleet_storage_cleanup/linux_hygiene.py"
spec = importlib.util.spec_from_file_location("fleet_hygiene_pressure_receipt", SOURCE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def snapshot(free_gib):
    return {
        "state": "OK", "total_gib": 900.0, "free_gib": float(free_gib),
        "inodes_free_fraction": 0.5, "available_bytes": int(free_gib * h.GIB),
        "inodes_available": 500_000, "device": 7,
    }


class CriticalDiskHealthReceiptTests(unittest.TestCase):
    def _sources(self, observations):
        return (
            patch.object(h, "volume", side_effect=observations),
            patch.object(h, "memory", return_value={"state": "OK"}),
            patch.object(h, "reserve", return_value={
                "state": "CONFIGURED", "floor_gib": 75.0,
            }),
            patch.object(h, "candidates", return_value={"state": "OBSERVED_ONLY"}),
            patch.object(h, "package_busy", return_value=True),
        )

    def test_critical_pressure_with_skipped_cleanup_is_degraded_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / "state"
            sources = self._sources(lambda _: snapshot(63))
            with sources[0], sources[1], sources[2], sources[3], sources[4], \
                    patch.object(h.Path, "home", return_value=root), \
                    patch.object(h.subprocess, "run", side_effect=AssertionError("no purge")):
                rc = h.main(["--state-dir", str(state), "--apply-safe-caches"])
            self.assertEqual(rc, 1)
            receipts = (state / h.LEDGER).read_text().splitlines()
            self.assertEqual(len(receipts), 1)
            recorded = json.loads(receipts[0])
            self.assertEqual(recorded["mode"], "CRITICAL")
            self.assertEqual(recorded["cleanup"], [{"state": "SKIPPED_PACKAGE_ACTIVITY"}])
            self.assertTrue(recorded["degraded"])
            self.assertEqual(recorded["attributable_reclaimed_bytes"], 0)
            self.assertEqual(recorded["fabric_admission"], "UNVERIFIED")

    def test_verified_post_pressure_recovery_does_not_inherit_initial_critical_flag(self):
        with tempfile.TemporaryDirectory() as d:
            sources = self._sources([snapshot(63), snapshot(63), snapshot(130)])
            with sources[0], sources[1], sources[2], sources[3], sources[4]:
                result = h.run(Path(d), Path(d), True)
            self.assertEqual(result["mode"], "CRITICAL")
            self.assertEqual(result["cleanup"], [{"state": "SKIPPED_PACKAGE_ACTIVITY"}])
            self.assertFalse(result["degraded"])
            self.assertEqual(result["attributable_reclaimed_bytes"], 0)
            self.assertEqual(result["fabric_admission"], "UNVERIFIED")

    def test_missing_post_pressure_measurement_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            incomplete = {"state": "OK", "device": 7,
                          "inodes_free_fraction": 0.5,
                          "available_bytes": int(63 * h.GIB)}
            sources = self._sources([snapshot(63), snapshot(63), incomplete])
            with sources[0], sources[1], sources[2], sources[3], sources[4]:
                result = h.run(Path(d), Path(d), True)
            self.assertTrue(result["degraded"])
            self.assertEqual(result["attributable_reclaimed_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
