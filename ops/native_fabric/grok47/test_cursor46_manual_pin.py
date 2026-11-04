"""Offline, no-provider-effect regression for the already allowed Cursor Grok 4.6 alias.

Exact manual pins may use independent Cursor monthly capacity without a Grok 402.
Automatic Grok-to-Cursor fallback remains exhaustion-only. Cursor 4.7 stays closed.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "quota_continuity" / "source"
for folder in (SOURCE, ROOT / "grok47" / "overlay"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

PICKERS = (
    ROOT / "grok47" / "overlay" / "pick.py",
    SOURCE / "pick.py",
    ROOT / "quota_continuity" / "candidate" / "pick.py",
)
ALIAS = "cursor-grok-4.6-high"
POLICY = {
    "pools": {
        "cursor": {"task_classes": ["review", "audit", "high_level"]},
        "grok": {"task_classes": ["review", "audit", "high_level"]},
    }
}


def load(path: Path):
    spec = importlib.util.spec_from_file_location("offline_" + path.parent.name + "_pick", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Cursor46ExplicitPin(unittest.TestCase):
    def test_exact_alias_respects_grok_role_without_exhaustion(self):
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                with patch.object(pick, "_grok_exhausted", return_value=False):
                    self.assertTrue(pick._cursor_grok_quota_affinity(ALIAS, "review", POLICY))
                    self.assertFalse(pick._cursor_grok_quota_affinity("grok-4.7-high", "review", POLICY))
                    self.assertTrue(pick.policy_allows("cursor", "review", POLICY, model=ALIAS)[0])
                    self.assertTrue(pick.launch_policy("cursor", "review", ALIAS, doc=POLICY)["allowed"])
                    with patch.object(pick, "load_pools", return_value=POLICY), \
                         patch.object(pick, "_slot_concurrent", return_value=0), \
                         patch.object(pick, "_pool_cap", return_value=8), \
                         patch.object(pick, "floor_demotes", return_value=False), \
                         patch.object(pick, "hard_filter", return_value=(True, "ok")):
                        # The independent quota/broker gate is tested by its owner;
                        # this unit isolates exact model/role selection only.
                        route = pick._format_pick("review", pool="cursor", requested_model=ALIAS)
                    self.assertIn("POOL=cursor ", route)
                    self.assertIn("MODEL=" + ALIAS, route)

    def test_automatic_grok_affinity_stays_on_direct_pool_when_healthy(self):
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                calls = []
                def fake(_task_class, **options):
                    calls.append((options.get("pool"), options.get("requested_model")))
                    return "POOL=grok KEY=- MODEL=grok-4.7 REASON=fixture"
                with patch.object(pick, "_grok_exhausted", return_value=False), \
                     patch.object(pick, "_format_pick_host", side_effect=fake):
                    result = pick.format_pick("review", pool="grok")
                self.assertIn("MODEL=grok-4.7", result)
                self.assertEqual(calls, [("grok", None)])

    def test_cursor_47_remains_unadmitted(self):
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                with patch.object(pick, "load_pools", return_value=POLICY):
                    result = pick._format_pick(
                        "review", pool="cursor", requested_model="grok-4.7-high")
                self.assertTrue(result.startswith("NONE reason="), result)

    def test_grok_class_policy_and_alias_identity_are_still_binding(self):
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                with patch.object(pick, "_grok_exhausted", return_value=False):
                    self.assertFalse(pick._cursor_grok_quota_affinity(
                        "composer-2.5", "review", POLICY))
                    self.assertFalse(pick._cursor_grok_quota_affinity(
                        ALIAS, "orchestration", POLICY))
                    self.assertFalse(pick.policy_allows(
                        "cursor", "orchestration", POLICY, model=ALIAS)[0])
                    self.assertFalse(pick.launch_policy(
                        "cursor", "orchestration", ALIAS, doc=POLICY)["allowed"])

    def test_high_level_manual_pin_does_not_inherit_auto_preference_veto(self):
        # The production quota/broker check is not skipped. This test supplies
        # a qualified healthy broker response and isolates only the preference.
        available = {
            "lease_broker": SimpleNamespace(default_broker=lambda: object()),
            "quota_circuit": SimpleNamespace(pool_blocked=lambda *_: False),
        }
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                with patch.dict(sys.modules, available), \
                     patch.object(pick, "_grok_exhausted", return_value=False), \
                     patch.object(pick, "_slot_concurrent", return_value=0), \
                     patch.object(pick, "_pool_cap", return_value=8):
                    permitted, reason = pick.hard_filter(
                        "cursor", "high_level", POLICY, model=ALIAS)
                    self.assertTrue(permitted, reason)
                    ordinary, ordinary_reason = pick.hard_filter(
                        "cursor", "high_level", POLICY, model="composer-2.5")
                    self.assertFalse(ordinary)
                    self.assertEqual(ordinary_reason, "grok_before_cursor policy")

    def test_current_generation_qualification_requires_exact_sealed_picker(self):
        qualifier_path = ROOT / "grok47" / "qualify_cursor46_current.py"
        spec = importlib.util.spec_from_file_location("cursor46_sealed_qualifier", qualifier_path)
        qualifier = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(qualifier)
        # Neither an old source copy nor an arbitrary staged payload can be
        # promoted as generation26 code merely by containing matching hunks.
        stale = (ROOT / "quota_continuity" / "source" / "pick.py").read_bytes()
        with self.assertRaisesRegex(ValueError, "native_gen26_picker_preimage_changed"):
            qualifier.patched(stale)
        with self.assertRaisesRegex(ValueError, "native_gen26_picker_preimage_changed"):
            qualifier.patched(b"arbitrary source containing a Grok marker")


if __name__ == "__main__":
    unittest.main()
