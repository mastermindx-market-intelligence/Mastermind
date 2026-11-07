#!/usr/bin/env python3
"""S5 hermetic negative-evidence fixture for ops/fleet_storage_cleanup/linux_hygiene.py.

WHAT THIS IS
  A disposable, hermetic unittest fixture that executes the REAL pinned
  run()/main() from linux_hygiene.py with every OS observation injected and
  cache_cleanup replaced by a fake. It touches no host state, no /proc, no
  package manager and no live timer. Its only filesystem writes are inside a
  TemporaryDirectory (disposable state + disposable root).

WHAT IT PROVES
  1. CURRENT (characterization, expected GREEN):
     A CRITICAL / below-configured-floor observation (63.05 GiB available vs a
     75 GiB floor) with no qualifying cleanup currently yields degraded=false
     and CLI exit code 0 -- a "green" tick.
  2. DESIRED (expected RED against the unchanged pinned source):
     That same observation must report degraded=true and must not exit 0.
  3. CONTROLS that must keep holding (expected GREEN): CALM/no-pressure stays
     healthy, an explicit HELD_UNBOUND_CACHE_TARGET stays degraded, an
     unknown floor stays UNVERIFIED + degraded, and every scenario reports
     zero attributable bytes with fabric_admission UNVERIFIED.

  A REPRODUCED DEFECT IS NOT ACCEPTANCE OF DEGRADED HEALTH. The GREEN
  characterization in (1) records the defect; the RED in (2) is the missing
  behavior. Neither accepts the current health signal.

  Negative evidence only: no source modification, no publication, no new
  controller, no admission decision, no copied implementation.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPOSITORY_ROOT / "ops/fleet_storage_cleanup/linux_hygiene.py"
sys.path.insert(0, str(SOURCE.parent))

import linux_hygiene as lh  # noqa: E402

EXPECTED_SOURCE_SHA256 = "3f676c0075478029e5857f0a95cd4ba9ae0dba9221eab312b034f88bca2502e3"
SOURCE_REL_PATH = "ops/fleet_storage_cleanup/linux_hygiene.py"
PROTECTED_PIN = "5f8c13da926011fb5fdc8cea21287b532ac968db"

GIB = 1024 ** 3
CONFIGURED_FLOOR_GIB = 75.0
# Parent read-only actual Ubuntu1 observation, 2026-11-07T07:05:34Z:
# 63.050689697 GiB available against the configured 75 GiB floor.
OBSERVED_AVAILABLE_GIB = 63.050689697
NOMINAL_TOTAL_GIB = 464.0

# The two skipped outcomes in the original November 3 receipts. Neither label is in the
# source's degraded set; the fixture also proves the conclusion does not
# depend on which cache carries which label.
SKIPPED_OUTCOMES = (
    {"cache": "pip", "state": "SKIPPED_UNTRUSTED_CACHE_PATH"},
    {"cache": "uv", "state": "SKIPPED_UNAVAILABLE"},
)


def _snapshot(path, total_gib, available_gib, *, device=1001,
              inodes_total=100_000_000, inodes_available=50_000_000):
    """Same shape as the source's real volume() observation, from constants."""
    total = int(total_gib * GIB)
    available = int(available_gib * GIB)
    return {
        "path": str(path), "resolved": str(path), "state": "OK",
        "total_bytes": total, "available_bytes": available,
        "inodes_total": inodes_total, "inodes_available": inodes_available,
        "total_gib": round(total / GIB, 2),
        "free_gib": round(available / GIB, 2),
        "free_fraction": round(available / total, 4),
        "inodes_free_fraction": round(inodes_available / inodes_total, 4),
        "device": device,
    }


class FixtureBase(unittest.TestCase):
    """Disposable temp state/root; every OS observation injected."""

    def scenario(self, *, available_gib=OBSERVED_AVAILABLE_GIB,
                 total_gib=NOMINAL_TOTAL_GIB, floor_gib=CONFIGURED_FLOOR_GIB,
                 cleanup=SKIPPED_OUTCOMES, apply_safe_caches=True, hold=False):
        tmp = tempfile.TemporaryDirectory(prefix="lh-fixture-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        root = base / "root"
        state = base / "state"
        (root / "lanes" / "wt").mkdir(parents=True)
        (root / ".cache").mkdir()
        state.mkdir(parents=True)
        if floor_gib is not None:
            (root / ".config" / "mastermind").mkdir(parents=True)
            (root / ".config" / "mastermind" / "fabric-storage-reserve.json").write_text(
                json.dumps({"internal_floor_gib": floor_gib}), encoding="utf-8")
        if hold:
            (state / lh.HOLD).write_text("fixture hold\n", encoding="utf-8")

        root_volume = _snapshot(Path("/"), total_gib, available_gib, device=1001)
        lanes_volume = _snapshot(root / "lanes", 64.0, 32.0, device=1002)

        def fake_volume(path):
            p = Path(path)
            if p == Path("/"):
                return dict(root_volume)
            if p == root / "lanes":
                return dict(lanes_volume)
            raise AssertionError(f"unexpected OS volume observation: {p!r}")

        def fake_memory(path=Path("/proc/meminfo")):
            # Disk/floor drives CRITICAL here; memory is deliberately CALM.
            return {"state": "OK", "total_gib": 16.0, "available_gib": 8.0,
                    "available_fraction": 0.5, "swap_used_gib": 0.0,
                    "pressure": "CALM"}

        calls = []

        def fake_cache_cleanup(root_arg, state_arg, mode):
            calls.append({"root": str(root_arg), "state": str(state_arg), "mode": mode})
            return [dict(row) for row in cleanup]

        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(lh, "volume", fake_volume))
            stack.enter_context(mock.patch.object(lh, "memory", fake_memory))
            stack.enter_context(mock.patch.object(lh, "cache_cleanup", fake_cache_cleanup))
            stack.enter_context(mock.patch.object(lh.socket, "gethostname",
                                                   lambda: "fixture-host"))
            stack.enter_context(mock.patch.object(Path, "home", return_value=root))
            report = lh.run(state, root, apply_safe_caches)
            argv = ["--state-dir", str(state)]
            if apply_safe_caches:
                argv.append("--apply-safe-caches")
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                cli_exit = lh.main(argv)

        text = out.getvalue() or err.getvalue()
        cli_report = json.loads(text) if text.strip() else {}
        return {"report": report, "cli_exit": cli_exit, "cli_report": cli_report,
                "calls": calls, "root": root, "state": state}


class TestPinnedSource(unittest.TestCase):
    def test_pinned_source_bytes_match_expected_installed_sha256(self):
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_SOURCE_SHA256,
                         f"fixture must execute the exact protected pin bytes of {SOURCE_REL_PATH}")


class TestCurrentSemantics(FixtureBase):
    """CHARACTERIZATION of the pinned (defective) behavior. Expected GREEN.

    These assertions record what the unchanged source does today. They are
    expected to invert if and when the source is fixed; they are not a
    statement that the current behavior is acceptable.
    """

    def test_critical_below_floor_without_qualifying_cleanup_reports_not_degraded(self):
        s = self.scenario()
        report = s["report"]
        self.assertEqual(report["mode"], "CRITICAL")
        self.assertEqual(report["fabric_reserve"]["state"], "CONFIGURED")
        self.assertEqual(report["fabric_reserve"]["floor_gib"], CONFIGURED_FLOOR_GIB)
        self.assertEqual([row["state"] for row in report["cleanup"]],
                         ["SKIPPED_UNTRUSTED_CACHE_PATH", "SKIPPED_UNAVAILABLE"])
        self.assertIs(report["degraded"], False,
                      "pinned source currently reports degraded=false here")
        self.assertEqual(s["cli_exit"], 0)
        self.assertIs(s["cli_report"]["degraded"], False)
        self.assertEqual(s["cli_report"]["schema"], "mastermind.fleet_linux_hygiene.v1")
        self.assertTrue((s["state"] / "linux-hygiene.jsonl").exists(),
                        "the real CLI ran and appended a receipt in the disposable state dir")

    def test_degraded_false_holds_for_any_injected_total_bytes(self):
        for total in (64.0, 128.0, 256.0, 464.0, 1024.0, 4096.0):
            with self.subTest(total_gib=total):
                s = self.scenario(total_gib=total)
                self.assertEqual(s["report"]["mode"], "CRITICAL")
                self.assertIs(s["report"]["degraded"], False)

    def test_degraded_false_is_invariant_to_the_skipped_label_mapping(self):
        variants = [
            list(SKIPPED_OUTCOMES),
            list(reversed(SKIPPED_OUTCOMES)),
            [SKIPPED_OUTCOMES[0]],
            [SKIPPED_OUTCOMES[1]],
            [SKIPPED_OUTCOMES[0], SKIPPED_OUTCOMES[1],
             {"cache": "npm", "state": "SKIPPED_CUSTOM_CACHE_PATH"}],
        ]
        for variant in variants:
            with self.subTest(variant=[row["state"] for row in variant]):
                s = self.scenario(cleanup=variant)
                self.assertEqual(s["report"]["mode"], "CRITICAL")
                self.assertIs(s["report"]["degraded"], False)


class TestControls(FixtureBase):
    """Invariants that must hold before AND after any future fix. Expected GREEN."""

    def test_calm_no_pressure_is_healthy_not_degraded(self):
        s = self.scenario(available_gib=200.0)
        self.assertEqual(s["report"]["mode"], "CALM")
        self.assertIs(s["report"]["degraded"], False)
        self.assertEqual(s["cli_exit"], 0)
        self.assertEqual(s["calls"], [], "CALM must not invoke any cleanup path")

    def test_report_only_calm_is_healthy_not_degraded(self):
        s = self.scenario(available_gib=200.0, apply_safe_caches=False)
        self.assertEqual(s["report"]["mode"], "CALM")
        self.assertEqual([row["state"] for row in s["report"]["cleanup"]], ["REPORT_ONLY"])
        self.assertIs(s["report"]["degraded"], False)
        self.assertEqual(s["cli_exit"], 0)

    def test_existing_held_unbound_cache_target_stays_degraded(self):
        s = self.scenario(cleanup=[{"cache": "pip", "state": "HELD_UNBOUND_CACHE_TARGET",
                                     "reason": "manager_target_handoff_unproven",
                                     "effect_state": "NOT_APPLIED"}])
        self.assertEqual(s["report"]["mode"], "CRITICAL")
        self.assertIs(s["report"]["degraded"], True)
        self.assertEqual(s["cli_exit"], 1)

    def test_existing_effect_hold_stays_degraded(self):
        s = self.scenario(hold=True)
        self.assertEqual(s["report"]["effect_hold"], "PRESENT")
        self.assertEqual([row["state"] for row in s["report"]["cleanup"]],
                         ["HELD_EFFECT_UNVERIFIED"])
        self.assertIs(s["report"]["degraded"], True)
        self.assertEqual(s["cli_exit"], 1)
        self.assertEqual(s["calls"], [])

    def test_unknown_floor_stays_unverified_and_degraded(self):
        s = self.scenario(floor_gib=None)
        self.assertEqual(s["report"]["fabric_reserve"]["state"], "UNVERIFIED")
        self.assertIs(s["report"]["degraded"], True)
        self.assertEqual([row["state"] for row in s["report"]["cleanup"]],
                         ["SKIPPED_MANDATORY_OBSERVATION_UNVERIFIED"])
        self.assertEqual(s["cli_exit"], 1)
        self.assertEqual(s["calls"], [])

    def test_zero_attributable_bytes_and_unverified_admission_in_every_scenario(self):
        scenarios = {
            "critical_no_qualifying_cleanup": {},
            "calm": {"available_gib": 200.0},
            "held_unbound": {"cleanup": [{"cache": "pip",
                                          "state": "HELD_UNBOUND_CACHE_TARGET"}]},
            "effect_hold": {"hold": True},
            "unknown_floor": {"floor_gib": None},
        }
        for name, kwargs in scenarios.items():
            with self.subTest(scenario=name):
                report = self.scenario(**kwargs)["report"]
                self.assertEqual(report["attributable_reclaimed_bytes"], 0)
                self.assertEqual(report["reclaim_attribution"],
                                 "NO_VERIFIED_MANAGER_SPECIFIC_BYTE_EVIDENCE")
                self.assertEqual(report["fabric_admission"], "UNVERIFIED")


class TestDesiredSemantics(FixtureBase):
    """DESIRED behavior. Expected RED against the unchanged pinned source.

    This is the defect proof. It asserts the behavior the assignment calls
    for; the pinned source does not implement it, so this test fails on the
    exact protected bytes.
    """

    def test_desired_degraded_true_and_nonzero_exit_for_critical_below_floor_without_qualifying_cleanup(self):
        s = self.scenario()
        report, cli_exit = s["report"], s["cli_exit"]
        self.assertEqual(report["mode"], "CRITICAL")
        self.assertTrue(
            report["degraded"] and cli_exit != 0,
            "DESIRED (not implemented in the pinned source): a CRITICAL below-floor "
            "observation with no qualifying cleanup must report degraded=true and "
            "must not exit 0. observed degraded="
            f"{report['degraded']} cli_exit={cli_exit} "
            f"cleanup={[row['state'] for row in report['cleanup']]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
