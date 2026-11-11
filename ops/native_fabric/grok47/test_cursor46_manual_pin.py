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
# The AUTO pre-release busy picker is a busy-scoped source; the reviewed
# default candidate keeps the pre-busy application picker.
BUSY_PICKER = ROOT / "quota_continuity" / "candidate" / "broker_busy_2121" / "pick.py"
ALIAS = "cursor-grok-4.6-high"
POLICY = {
    "pools": {
        "cursor": {"task_classes": ["review", "audit", "high_level"]},
        "grok": {"task_classes": ["review", "audit", "high_level"]},
    }
}


QUALIFIER_PATH = ROOT / "grok47" / "qualify_cursor46_current.py"
_qspec = importlib.util.spec_from_file_location("cursor46_qualifier_tests", QUALIFIER_PATH)
qualifier = importlib.util.module_from_spec(_qspec)
assert _qspec.loader is not None
_qspec.loader.exec_module(qualifier)


def load(path: Path):
    """Execute the reviewed minimal delta in memory; never edit accepted files."""
    spec = importlib.util.spec_from_file_location("offline_" + path.parent.name + "_pick", path)
    module = importlib.util.module_from_spec(spec)
    patched_source = qualifier.apply_reviewed_hunks(path.read_bytes())
    exec(compile(patched_source, str(path), "exec"), module.__dict__)
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

    def test_r30_labor_only_uses_legacy_exhaustion_exception(self):
        # Manual monthly Cursor is independent for *judgment* work, but must
        # not widen the historical quota-only labor exception (R30).
        task_classes = ["review", "high_level", "execute", "fix_build",
                        "mechanical", "census", "extract"]
        policy = {"pools": {p: {"task_classes": task_classes}
                            for p in ("grok", "cursor")}}
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                with patch.object(pick, "_grok_exhausted", return_value=False):
                    for task in ("execute", "fix_build", "mechanical", "census", "extract"):
                        with self.subTest(task=task, exhausted=False):
                            self.assertFalse(pick._cursor_grok_quota_affinity(
                                ALIAS, task, policy))
                            self.assertFalse(pick.policy_allows(
                                "cursor", task, policy, model=ALIAS)[0])
                    self.assertTrue(pick.policy_allows(
                        "cursor", "review", policy, model=ALIAS)[0])
                    self.assertTrue(pick.policy_allows(
                        "cursor", "high_level", policy, model=ALIAS)[0])
                # Under a genuine Grok exhausted marker, preserve the exact
                # original quota-only labor failover for eligible Grok classes.
                with patch.object(pick, "_grok_exhausted", return_value=True):
                    for task in ("execute", "fix_build", "mechanical", "census", "extract"):
                        with self.subTest(task=task, exhausted=True):
                            self.assertTrue(pick._cursor_grok_quota_affinity(
                                ALIAS, task, policy))
                            self.assertTrue(pick.policy_allows(
                                "cursor", task, policy, model=ALIAS)[0])

    def test_signed_role_reclassification_cannot_disable_r30_hard_boundary(self):
        # Role-class YAML can change independently. It is not permission to
        # reinterpret fixed labor roles as Cursor monthly judgment capacity.
        for source in PICKERS:
            with self.subTest(source=str(source)):
                pick = load(source)
                for registered_execute in (["review", "audit", "execute", "fix_build"],
                                           ["review", "audit"]):
                    with self.subTest(source=str(source), execute=registered_execute):
                        policy = {
                            "pools": {pool: {"task_classes": [
                                "review", "audit", "high_level", "execute", "fix_build"]}
                                for pool in ("grok", "cursor")},
                            "routing": {
                                "execute_classes": registered_execute,
                                "operator_classes": ["high_level", "fix_build", "execute"],
                            },
                        }
                        with patch.object(pick, "_grok_exhausted", return_value=False):
                            for task in ("execute", "fix_build"):
                                # Signed YAML can independently reclassify the
                                # generic execute role. The *strict alias*
                                # must still fail both source admission gates.
                                self.assertFalse(pick._cursor_grok_quota_affinity(
                                    ALIAS, task, policy),
                                    f"{source} reclassified {task} bypassed R30")
                                self.assertFalse(pick.launch_policy(
                                    "cursor", task, ALIAS, doc=policy)["allowed"])
                                with patch.object(pick, "load_pools", return_value=policy):
                                    route = pick._format_pick(
                                        task, pool="cursor", requested_model=ALIAS)
                                self.assertTrue(route.startswith("NONE reason="), route)
                            self.assertTrue(pick.policy_allows(
                                "cursor", "review", policy, model=ALIAS)[0])
                            self.assertTrue(pick.policy_allows(
                                "cursor", "high_level", policy, model=ALIAS)[0])

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
        # The released source fixture is intentionally historical. It cannot
        # impersonate the exact sealed native gen27 selected on the host.
        stale = (ROOT / "quota_continuity" / "source" / "pick.py").read_bytes()
        current = "8cefc4b27b2036f86bcec1d626e864f45f792e2c290ab8de56fbde89f78ac94a"
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            qualifier.patched(stale, current)
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            qualifier.patched(b"arbitrary source containing a Grok marker", current)
        with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
            qualifier.patched(stale, "0" * 64)

    def test_current_application_branch_preserves_explicit_observation_and_no_ambient_read(self):
        path = PICKERS[-1]
        raw = path.read_bytes()
        self.assertEqual(qualifier.sha(raw), qualifier.APPLICATION_PICKER_SHA256)
        qualified = load(path)
        spec = importlib.util.spec_from_file_location("original_application_picker", path)
        original = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(path), "exec"), original.__dict__)
        for model in (ALIAS, "composer-2.5"):
            for task in ("review", "high_level", "fix_build", "orchestration"):
                for exhausted in (None, False, True):
                    with self.subTest(model=model, task=task, exhausted=exhausted):
                        with patch.object(original, "_grok_exhausted", side_effect=AssertionError("ambient observation")), \
                             patch.object(qualified, "_grok_exhausted", side_effect=AssertionError("ambient observation")):
                            self.assertEqual(
                                qualified._cursor_grok_quota_affinity(model, task, POLICY,
                                    exhausted=exhausted, application=True),
                                original._cursor_grok_quota_affinity(model, task, POLICY,
                                    exhausted=exhausted, application=True))

    def test_current_application_qualification_refuses_source_drift_and_sealed_relabel(self):
        raw = PICKERS[-1].read_bytes()
        with self.assertRaisesRegex(ValueError, "reviewed_selector_hunk_identity_mismatch"):
            qualifier.apply_reviewed_hunks(raw + b"\n# unqualified change\n")
        for predecessor in qualifier.SEALED_PREDECESSORS:
            with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
                qualifier.patched(raw, predecessor)

    def test_canonical_historical_picker_is_not_mutated_by_in_memory_candidate(self):
        for source in PICKERS:
            with self.subTest(source=str(source)):
                raw = source.read_bytes()
                candidate = qualifier.apply_reviewed_hunks(raw)
                self.assertNotEqual(candidate, raw)
                self.assertEqual(source.read_bytes(), raw)
                self.assertIn(b"cursor-grok-4.6-high", candidate)
                if qualifier.sha(raw) == qualifier.APPLICATION_PICKER_SHA256:
                    self.assertIn(qualifier.APPLICATION_AFFINITY_BEFORE.encode(), raw)
                    self.assertIn(qualifier.APPLICATION_AFFINITY_AFTER.encode(), candidate)
                else:
                    self.assertIn(b"and _grok_exhausted()", raw)


    # Converge 2121 broker-busy epoch coverage (relocated per probe law: the
    # upstream application-picker tests above stay byte-identical to master).
    def test_broker_busy_branch_preserves_explicit_observation_and_no_ambient_read(self):
        path = BUSY_PICKER
        raw = path.read_bytes()
        self.assertEqual(qualifier.sha(raw), qualifier.BROKER_BUSY_PICKER_SHA256)
        qualified = load(path)
        spec = importlib.util.spec_from_file_location("original_busy_picker", path)
        original = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(path), "exec"), original.__dict__)
        for model in (ALIAS, "composer-2.5"):
            for task in ("review", "high_level", "fix_build", "orchestration"):
                for exhausted in (None, False, True):
                    with self.subTest(model=model, task=task, exhausted=exhausted):
                        with patch.object(original, "_grok_exhausted", side_effect=AssertionError("ambient observation")), \
                             patch.object(qualified, "_grok_exhausted", side_effect=AssertionError("ambient observation")):
                            self.assertEqual(
                                qualified._cursor_grok_quota_affinity(model, task, POLICY,
                                    exhausted=exhausted, application=True),
                                original._cursor_grok_quota_affinity(model, task, POLICY,
                                    exhausted=exhausted, application=True))

    def test_broker_busy_qualification_refuses_source_drift_and_sealed_relabel(self):
        raw = BUSY_PICKER.read_bytes()
        with self.assertRaisesRegex(ValueError, "reviewed_selector_hunk_identity_mismatch"):
            qualifier.apply_reviewed_hunks(raw + b"\n# unqualified change\n")
        for predecessor in qualifier.SEALED_PREDECESSORS:
            with self.assertRaisesRegex(ValueError, "sealed_picker_preimage_changed"):
                qualifier.patched(raw, predecessor)

    def test_broker_busy_picker_takes_application_affinity_transform(self):
        raw = BUSY_PICKER.read_bytes()
        candidate = qualifier.apply_reviewed_hunks(raw)
        self.assertNotEqual(candidate, raw)
        self.assertEqual(BUSY_PICKER.read_bytes(), raw)
        self.assertIn(qualifier.APPLICATION_AFFINITY_BEFORE.encode(), raw)
        self.assertIn(qualifier.APPLICATION_AFFINITY_AFTER.encode(), candidate)


if __name__ == "__main__":
    unittest.main()
