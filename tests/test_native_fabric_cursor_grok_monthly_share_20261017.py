"""Hermetic approval gates for the opt-in Cursor Grok allocation overlay.

Only the historical source fixture is patched. This does not touch a live
controller, a host, a provider account, or an installed Fabric policy.
"""
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "research/fabric_bailian_host_eligibility_20261015/candidate/pick.py"
PATCH = ROOT / "ops/native_fabric/patches/pick_cursor_grok_monthly_share_20261017.patch"


class CursorMonthlyShareSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="fabric-cursor-share-")
        cls.workspace = Path(cls.temp.name)
        shutil.copyfile(ORIGINAL, cls.workspace / "pick.py")
        result = subprocess.run(
            ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(PATCH)],
            cwd=cls.workspace, capture_output=True, text=True, timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                "Cursor patch does not compose with its declared source fixture: "
                + result.stdout + result.stderr
            )
        cls.tree = ast.parse((cls.workspace / "pick.py").read_text(encoding="utf-8"))
        cls.helper = next(
            n for n in cls.tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "_cursor_grok_monthly_share"
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def policy(percent=15, enabled=True, classes=None):
        now = datetime.now(timezone.utc)
        return {"routing": {
            "cursor_grok_monthly_share": {
                "enabled": enabled,
                "percent": percent,
                "task_classes": classes if classes is not None
                else ["operator", "repair"],
                "cursor_entitlement": {
                    "plan_type": "legacy_independent_monthly",
                    "source": "account_dashboard_readback",
                    "on_demand_enabled": False,
                    "remaining_pct": 80.0,
                    "observed_at": (now - timedelta(minutes=2))
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reset_at": (now + timedelta(days=10))
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
        }}

    def choose(self, route_key, doc=None, task_class="operator", prefer=None,
               complexity="C2_COMPLEX_BOUNDED", exhausted=True):
        if doc is None:
            doc = self.policy()
        env = {
            "_routing": lambda d: d.get("routing") or {},
            "_grok_exhausted": lambda: exhausted,
            "hashlib": hashlib,
            "math": math,
            "datetime": datetime,
            "timezone": timezone,
            "re": re,
        }
        module = ast.Module(body=[self.helper], type_ignores=[])
        exec(compile(module, "<cursor-share-overlay>", "exec"), env)
        return env["_cursor_grok_monthly_share"](
            task_class, doc, route_key, prefer, complexity
        )

    def test_patch_uses_one_existing_picker_seam(self):
        picker = next(
            n for n in self.tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_format_pick"
        )
        calls = [
            n.func.id for n in ast.walk(picker)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        self.assertIn("_cursor_grok_monthly_share", calls)
        self.assertIn("_cursor_grok_after_quota", calls)
        self.assertIn("_pick_scored", calls)
        self.assertEqual(
            len([n for n in self.tree.body
                 if isinstance(n, ast.FunctionDef)
                 and n.name == "_cursor_grok_monthly_share"]), 1,
        )

    def test_15_percent_deterministic_scatter(self):
        chosen = [
            self.choose(f"fabric-judgment-{i}")
            for i in range(1000)
        ]
        self.assertEqual(chosen, [
            self.choose(f"fabric-judgment-{i}")
            for i in range(1000)
        ])
        self.assertGreaterEqual(sum(chosen), 100)
        self.assertLessEqual(sum(chosen), 200)

    def test_disabled_or_unknown_config_is_inert(self):
        for doc in ({}, {"routing": {}}, self.policy(enabled=False),
                    self.policy(percent=0), self.policy(percent=21),
                    self.policy(percent=True), self.policy(percent=3.5)):
            self.assertFalse(any(
                self.choose(f"t-{i}", doc) for i in range(60)
            ))

    def test_new_shared_weekly_plan_and_unknown_quota_fail_closed(self):
        now = datetime.now(timezone.utc)
        samples = [
            {"plan_type": "shared_weekly"},
            {"plan_type": "unknown"},
            {"source": "self_report_unverified"},
            {"on_demand_enabled": True},
            {"on_demand_enabled": None},
            {"remaining_pct": 19.9},
            {"remaining_pct": 0.0},
            {"remaining_pct": True},
            {"remaining_pct": float("nan")},
            {"observed_at": (now - timedelta(hours=7))
                .strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"observed_at": (now + timedelta(hours=1))
                .strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"reset_at": (now - timedelta(seconds=1))
                .strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"reset_at": (now + timedelta(days=40))
                .strftime("%Y-%m-%dT%H:%M:%SZ")},
            {"reset_at": "not-a-date"},
            {"reset_at": "2030-01-01T00:00:00+01:00"},
        ]
        for change in samples:
            doc = self.policy()
            doc["routing"]["cursor_grok_monthly_share"]["cursor_entitlement"].update(change)
            with self.subTest(change=change):
                self.assertFalse(any(
                    self.choose(f"quota-negative-{i}", doc)
                    for i in range(150)
                ))
        doc = self.policy()
        del doc["routing"]["cursor_grok_monthly_share"]["cursor_entitlement"]
        self.assertFalse(self.choose("absent-proof", doc))

    def test_no_share_without_confirmed_grok_exhaustion(self):
        self.assertFalse(any(
            self.choose(f"t-{i}", exhausted=False)
            for i in range(100)
        ))

    def test_no_labor_c3_or_manual_preference(self):
        for i in range(100):
            key = f"t-{i}"
            self.assertFalse(self.choose(key, task_class="mechanical"))
            self.assertFalse(self.choose(key, task_class="executor"))
            self.assertFalse(self.choose(key, task_class="audit"))
            self.assertFalse(self.choose(key, task_class="reviewer"))
            self.assertFalse(self.choose(key, task_class="review"))
            self.assertFalse(self.choose(key, task_class="verify"))
            self.assertFalse(self.choose(key, task_class="adjudicate"))
            self.assertFalse(self.choose(key, complexity="C3_FRONTIER_JUDGMENT"))
            self.assertFalse(self.choose(key, complexity="C1_ROUTINE_BOUNDED"))
            self.assertFalse(self.choose(key, complexity="C0_MECHANICAL"))
            self.assertFalse(self.choose(key, complexity=""))
            self.assertFalse(self.choose(key, prefer="glm"))

    def test_fail_closed_class_config_and_identity(self):
        self.assertFalse(self.choose(None))
        self.assertFalse(self.choose("a\\nnewline"))
        self.assertFalse(self.choose("X" * 129))
        for classes in ([], ["operator", "operator"], ["mechanical"],
                        ["operator", 17], "operator", ["reviewer"],
                        ["audit"], ["review"], ["verify"]):
            self.assertFalse(self.choose("t-1", self.policy(classes=classes)))

    def test_cohort_classes_are_reachable_judgment_not_reviews(self):
        identities = {"EXECUTE_CLASSES_DEFAULT", "JUDGMENT_CLASSES_R28",
                      "REVIEW_CLASSES_R33"}
        declared = {}
        for node in self.tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (isinstance(target, ast.Name) and target.id in identities
                        and isinstance(node.value, ast.Call)
                        and node.value.args):
                    declared[target.id] = ast.literal_eval(node.value.args[0])
        self.assertEqual(set(declared), identities)
        for task_class in ("operator", "repair"):
            self.assertIn(task_class, declared["JUDGMENT_CLASSES_R28"])
            self.assertNotIn(task_class, declared["EXECUTE_CLASSES_DEFAULT"])
            self.assertNotIn(task_class, declared["REVIEW_CLASSES_R33"])

    def test_grok_quota_native_gate_stays_in_control(self):
        picker = next(
            n for n in self.tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_format_pick"
        )
        # The new branch must run only inside judgment classes and must call
        # the existing full-qualification fallback, never direct _emit/claim.
        branch = next(
            n for n in ast.walk(picker)
            if isinstance(n, ast.If) and isinstance(n.test, ast.Call)
            and isinstance(n.test.func, ast.Name)
            and n.test.func.id == "is_judgment_class"
        )
        calls = [
            n.func.id for n in ast.walk(branch)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        self.assertIn("_cursor_grok_after_quota", calls)
        self.assertNotIn("_emit", calls)


    def test_native_failure_returns_original_judgment_route(self):
        picker = next(
            n for n in self.tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_format_pick"
        )
        branch = next(
            n for n in ast.walk(picker)
            if isinstance(n, ast.If) and isinstance(n.test, ast.Call)
            and isinstance(n.test.func, ast.Name)
            and n.test.func.id == "is_judgment_class"
        )
        wrapper = ast.parse("def probe():\n    pass\n")
        wrapper.body[0].body = [branch]
        base = {
            "is_judgment_class": lambda *args: True,
            "_cursor_grok_monthly_share": lambda *args: True,
            "_cursor_grok_after_quota": lambda *args, **kwargs:
                "NONE reason=cursor_at_capacity",
            "_pick_scored": lambda *args, **kwargs:
                "POOL=glm MODEL=glm-5.3",
            "tc": "operator", "doc": self.policy(),
            "route_key": "judgment-91", "prefer_c": None,
            "complexity": "C2_COMPLEX_BOUNDED",
            "needs": None, "subject_pool": None,
            "host_modes": None, "escalation_reason": "",
        }
        exec(compile(ast.fix_missing_locations(wrapper),
                     "<picker-judgment-branch>", "exec"), base)
        self.assertEqual(base["probe"](), "POOL=glm MODEL=glm-5.3")
        base["_cursor_grok_after_quota"] = lambda *args, **kwargs: (
            "POOL=cursor MODEL=cursor-grok-4.6-high"
        )
        self.assertEqual(
            base["probe"](),
            "POOL=cursor MODEL=cursor-grok-4.6-high"
            " ROUTE_ALLOC=cursor_grok_monthly_share",
        )
        base["_cursor_grok_monthly_share"] = lambda *args: False
        self.assertEqual(base["probe"](), "POOL=glm MODEL=glm-5.3")


if __name__ == "__main__":
    unittest.main()
