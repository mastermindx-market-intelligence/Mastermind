"""Actual disk probe blocks and host selection with inert filesystem telemetry.

Only df is replaced. Bash and awk run the template's original disk statements;
thermal probes, process census, credentials, provider calls and live state do not
run. The selector consumes explicit in-memory host state and unchanged policy.
"""
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
import host_pick

ORIGINAL = ROOT / "source" / "host_pull_probe.template"
CANDIDATE = ROOT / "candidate" / "host_pull_probe.template"
NOW = datetime(2026, 10, 18, 13, 16, tzinfo=timezone.utc)
KIB_PER_GIB = 1048576
FLOOR_KIB = 315 * KIB_PER_GIB
OBSERVED_KIB = 330253288

DF_FIXTURE = r'''
df() {
    case "$*" in
        '-Pk /fixture/worktree') available="$FIXTURE_WORKTREE_KIB" ;;
        '-Pk /System/Volumes/Data') available="$FIXTURE_DATA_KIB" ;;
        '-Pk /') available="$FIXTURE_ROOT_KIB" ;;
        *) printf 'unexpected df arguments\n' >&2; return 64 ;;
    esac
    printf '%s\n' 'Filesystem 1024-blocks Used Available Capacity Mounted on'
    printf '/fixture/disk 999999999 1 %s 1%% /fixture/mount\n' "$available"
}
disk=''
'''


def disk_probe(platform, worktree_kib, *, data_kib=None, root_kib=None,
               template=CANDIDATE):
    """Extract complete disk-only statements, never rewrite their arithmetic."""
    text = template.read_text(encoding="utf-8")
    if platform == "Darwin":
        start = text.index('    dk_wr=$(df -Pk "@@WR@@"')
        end = text.index('    if command -v pmset', start)
    elif platform == "Linux":
        start = text.index('    dk=$(df -Pk "@@WR@@"', text.index('  Linux)'))
        end = text.index('    ;;', start)
    else:
        raise ValueError("unsupported fixture platform")
    block = text[start:end].replace("@@WR@@", "/fixture/worktree")
    if data_kib is None:
        data_kib = worktree_kib
    if root_kib is None:
        root_kib = data_kib
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eu", "-c",
         DF_FIXTURE + block + '\nprintf "%s\\n" "$disk"\n'],
        env={"PATH": os.defpath, "LC_ALL": "C",
             "FIXTURE_WORKTREE_KIB": str(worktree_kib),
             "FIXTURE_DATA_KIB": str(data_kib), "FIXTURE_ROOT_KIB": str(root_kib)},
        text=True, capture_output=True, timeout=5, check=True,
    )
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def host_fixture(disk, *, base=300):
    registry = {
        "roles": ["lanes"], "allowed_modes": ["minimax"],
        "ssh_alias": "fixture-host", "cores": 32, "load_gate": 4,
        "lane_ceiling": 12, "max_active": 12,
        "min_free_gb": base, "checkout_reserve_gb": 15,
    }
    state = {"ts": NOW.timestamp(), "reachable": True, "load1": 0,
             "active_lanes": 0, "ncpu": 32, "tools": ["claude"],
             "disk_free_gb": float(disk)}
    return registry, state


def evaluate(disk):
    registry, state = host_fixture(disk)
    return host_pick.evaluate_hosts(
        {"ubuntu3": registry}, "/fixture/no-state-reads", "minimax",
        states={"ubuntu3": state}, now=NOW, max_age=30,
    )[0]


class DiskTelemetry(unittest.TestCase):
    def test_observed_incident_original_admits_candidate_refuses(self):
        self.assertLess(Fraction(OBSERVED_KIB, KIB_PER_GIB), 315)
        for platform in ("Darwin", "Linux"):
            with self.subTest(platform=platform):
                old = disk_probe(platform, OBSERVED_KIB, template=ORIGINAL)
                new = disk_probe(platform, OBSERVED_KIB)
                self.assertEqual(old, "315.0")
                self.assertEqual(new, "314.9")
                self.assertTrue(evaluate(old)["eligible"])
                row = evaluate(new)
                self.assertFalse(row["eligible"])
                self.assertEqual([g["gate"] for g in row["gates"]
                                  if g["result"] == "FAIL"], ["disk"])

    def test_real_selector_preserves_exact_below_and_above_315_boundary(self):
        cases = ((OBSERVED_KIB, "314.9", False),
                 (FLOOR_KIB - 1, "314.9", False),
                 (FLOOR_KIB, "315.0", True),
                 (FLOOR_KIB + 1, "315.0", True))
        for platform in ("Darwin", "Linux"):
            for kib, expected, eligible in cases:
                with self.subTest(platform=platform, available_kib=kib):
                    value = disk_probe(platform, kib)
                    self.assertEqual(value, expected)
                    self.assertEqual(evaluate(value)["eligible"], eligible)

    def test_actual_formatters_never_overstate_and_keep_one_decimal(self):
        values = (-KIB_PER_GIB - 1, -1, 0, 1, KIB_PER_GIB - 1,
                  KIB_PER_GIB, OBSERVED_KIB, FLOOR_KIB - 1, FLOOR_KIB,
                  FLOOR_KIB + 1, FLOOR_KIB + 104857,
                  FLOOR_KIB + 104858, 8192 * KIB_PER_GIB - 1)
        for platform in ("Darwin", "Linux"):
            for kib in values:
                with self.subTest(platform=platform, available_kib=kib):
                    value = disk_probe(platform, kib)
                    self.assertRegex(value, r"^-?[0-9]+\.[0-9]$")
                    emitted = Fraction(value)
                    actual = Fraction(kib, KIB_PER_GIB)
                    self.assertLessEqual(emitted, actual)
                    self.assertLess(actual - emitted, Fraction(1, 10))

    def test_darwin_preserves_lower_volume_and_root_fallback(self):
        roomy = 400 * KIB_PER_GIB
        cases = ((OBSERVED_KIB, roomy, roomy),
                 (roomy, OBSERVED_KIB, roomy),
                 (roomy, 0, OBSERVED_KIB),
                 (0, OBSERVED_KIB, roomy))
        for worktree, data, root in cases:
            with self.subTest(worktree=worktree, data=data, root=root):
                value = disk_probe("Darwin", worktree, data_kib=data, root_kib=root)
                self.assertEqual(value, "314.9")
                self.assertFalse(evaluate(value)["eligible"])

    def test_real_selection_can_choose_healthy_existing_host(self):
        bad_entry, bad_state = host_fixture(disk_probe("Linux", OBSERVED_KIB))
        good_entry, good_state = host_fixture(disk_probe("Linux", 241 * KIB_PER_GIB), base=150)
        rows = host_pick.evaluate_hosts(
            {"ubuntu3": bad_entry, "ubuntu1": good_entry},
            "/fixture/no-state-reads", "minimax", states={"ubuntu3": bad_state, "ubuntu1": good_state},
            now=NOW, max_age=30,
        )
        selected = host_pick.choose_host(rows, prefer_remote=True,
                                         placement_key="disk-boundary-regression")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["host"], "ubuntu1")
        self.assertEqual([r["host"] for r in rows if r["eligible"]], ["ubuntu1"])


if __name__ == "__main__":
    unittest.main()
