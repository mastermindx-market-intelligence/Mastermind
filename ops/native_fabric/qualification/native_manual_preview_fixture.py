import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ["MMX_NATIVE_PREVIEW_CANDIDATE"])
sys.path.insert(0, str(ROOT / "ext"))
import fabric_task as task

SYNTHETIC = "POOL=grok MODEL=grok-4.7 HOST=ubuntu1 MODE=grok REASON=synthetic_only"

class NativeManualPreviewTest(unittest.TestCase):
    def preview(self, line=SYNTHETIC, allowed=True, **options):
        with patch.object(task.pick, "format_pick", return_value=line) as selection:
            with patch.object(task.pick, "launch_policy", return_value={"allowed":allowed, "reason":"policy_denied"}) as policy:
                result = task.preview_route("manual-fixture-001", "review", pool="grok", model="grok-4.7", task_complexity="C2_COMPLEX_BOUNDED", **options)
        self.assertEqual(selection.call_count, 1)
        self.assertEqual(policy.call_count, 1)
        return result

    def test_exact_grok_pin_is_synthetic_and_no_reservation(self):
        result=self.preview()
        self.assertEqual((result["pool"], result["model"]),("grok","grok-4.7"))
        self.assertTrue(result["strict_pin_enforced_at_request"])
        self.assertTrue(result["selection_rechecked_at_request"])
        self.assertEqual(result["state"],"PREVIEW_ONLY")
        self.assertIs(result["reserved"],False)

    def test_model_mismatch_fails_before_economic_admission(self):
        with patch.object(task.pick, "format_pick", return_value="POOL=grok MODEL=grok-4.6 HOST=ubuntu1 MODE=grok"), patch.object(task.pick, "launch_policy") as policy:
            with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_MODEL_ROUTE_MISMATCH"):
                task.preview_route("manual-fixture-001","review",pool="grok",model="grok-4.7")
            policy.assert_not_called()

    def test_provider_mismatch_fails_closed(self):
        with patch.object(task.pick, "format_pick", return_value="POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm"):
            with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_POOL_ROUTE_MISMATCH"):
                task.preview_route("manual-fixture-001","review",pool="grok")

    def test_unscoped_model_pin_and_malformed_model_refused(self):
        with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_MODEL_REQUIRES_POOL"):
            task.preview_route("manual-fixture-001","review",model="grok-4.7")
        with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_SELECTOR_INVALID"):
            task.preview_route("manual-fixture-001","review",pool="grok",model="grok-4.7; rm")

    def test_auto_select_keeps_existing_router(self):
        with patch.object(task.pick, "format_pick",return_value="POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm") as selection, patch.object(task.pick,"launch_policy",return_value={"allowed":True}):
            result=task.preview_route("manual-fixture-001","review",pool="AUTO",model="auto")
        self.assertFalse(result["strict_pin_enforced_at_request"])
        self.assertIsNone(selection.call_args.kwargs["requested_model"])
        self.assertIsNone(selection.call_args.kwargs["pool"])

    def test_economic_gate_remains_final_owner(self):
        with self.assertRaisesRegex(task.FabricTaskError,"ECONOMIC_POLICY_REFUSED"):
            self.preview(allowed=False)

    def test_cli_supports_explicit_strict_contract(self):
        env={**os.environ,"PYTHONPATH":os.pathsep.join(sys.path)}
        commands=[["preview","--help"],["request","--help"]]
        for args in commands:
            p=subprocess.run([sys.executable,str(ROOT/"ext"/"fabric_task.py"),*args],env=env,text=True,capture_output=True,check=True)
            self.assertIn("--pool",p.stdout)
        self.assertIn("--strict-manual-pin",subprocess.run([sys.executable,str(ROOT/"ext"/"fabric_task.py"),"request","--help"],env=env,text=True,capture_output=True,check=True).stdout)

    def test_picker_accepts_exact_worker_default_with_unchanged_eligibility_guards(self):
        policy={"pools":{"grok":{"default_model":"grok-4.6"}}}
        from contextlib import ExitStack
        with ExitStack() as guards:
            for key,result in {
                "load_pools":policy, "_glm_models":{"reviewer":"glm-5.3","executor":"glm-5.3-flash"},
                "policy_allows":(True,"admitted"), "_needs_ok":(True,"admitted"),
                "_subject_ok":(True,"admitted"), "floor_demotes":False,
                "hard_filter":(True,"admitted"), "is_execute_class":False,
                "_emit":"POOL=grok MODEL=grok-4.6 HOST=ubuntu1 MODE=grok",
            }.items():
                guards.enter_context(patch.object(task.pick,key,return_value=result))
            allowed=task.pick._format_pick("review",pool="grok",requested_model="grok-4.6")
            self.assertTrue(allowed.startswith("POOL=grok"),allowed)
            denied=task.pick._format_pick("review",pool="grok",requested_model="grok-4.7")
            self.assertIn("not admitted for selected pool/task",denied)
            unscoped=task.pick._format_pick("review",requested_model="grok-4.6")
            self.assertIn("requires provider pool",unscoped)

    def test_future_catalog_default_pins_only_after_catalog_owner_promotes_it(self):
        policy={"pools":{"grok":{"default_model":"grok-4.7"}}}
        with patch.object(task.pick,"load_pools",return_value=policy), patch.object(task.pick,"_glm_models",return_value={}):
            with patch.object(task.pick,"policy_allows",return_value=(True,"admitted")),patch.object(task.pick,"_needs_ok",return_value=(True,"admitted")),patch.object(task.pick,"_subject_ok",return_value=(True,"admitted")),patch.object(task.pick,"floor_demotes",return_value=False),patch.object(task.pick,"hard_filter",return_value=(True,"admitted")),patch.object(task.pick,"is_execute_class",return_value=False),patch.object(task.pick,"_emit",return_value="POOL=grok MODEL=grok-4.7 HOST=ubuntu1 MODE=grok"):
                allowed=task.pick._format_pick("review",pool="grok",requested_model="grok-4.7")
                self.assertTrue(allowed.startswith("POOL=grok"),allowed)

    def test_no_manual_continuity_and_direct_strict_route_helper(self):
        task._enforce_manual_route({"POOL":"grok","MODEL":"grok-4.7"},"grok","grok-4.7")
        with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_MODEL_ROUTE_MISMATCH"):
            task._enforce_manual_route({"POOL":"grok","MODEL":"grok-4.6"},"grok","grok-4.7")

if __name__=="__main__":
    unittest.main()
