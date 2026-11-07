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
            admitted=task.pick._format_pick("review",pool="grok",requested_model="grok-4.7")
            self.assertTrue(admitted.startswith("POOL=grok"),admitted)
            denied=task.pick._format_pick("review",pool="grok",requested_model="grok-4.8")
            self.assertIn("not admitted for selected pool/task",denied)
            native_grok_affinity=task.pick._format_pick("review",requested_model="grok-4.6")
            self.assertTrue(native_grok_affinity.startswith("POOL=grok"),native_grok_affinity)

    def test_current_default_model_pin_admits_only_named_provider(self):
        # Provider-free regression: an explicitly named default is not an
        # arbitrary model promotion, and an unscoped pin cannot choose a pool.
        policy={"pools":{"bailian":{"default_model":"qwen3.8-max"}}}
        from contextlib import ExitStack
        with ExitStack() as guards:
            for key,result in {
                "load_pools":policy, "_glm_models":{},
                "policy_allows":(True,"admitted"), "_needs_ok":(True,"admitted"),
                "_subject_ok":(True,"admitted"), "floor_demotes":False,
                "hard_filter":(True,"admitted"), "is_execute_class":False,
                "_selection_model":("qwen3.8-max","admitted"),
                "_emit":"POOL=bailian MODEL=qwen3.8-max HOST=ubuntu1 MODE=qwen",
            }.items():
                guards.enter_context(patch.object(task.pick,key,return_value=result))
            admitted=task.pick._format_pick("review",pool="bailian",requested_model="qwen3.8-max")
            self.assertTrue(admitted.startswith("POOL=bailian"),admitted)
            mismatch=task.pick._format_pick("review",pool="bailian",requested_model="qwen3.8-flash")
            self.assertIn("not admitted for selected pool/task",mismatch)
            unscoped=task.pick._format_pick("review",requested_model="qwen3.8-max")
            self.assertIn("requires provider pool",unscoped)

    def test_future_catalog_default_pins_only_after_catalog_owner_promotes_it(self):
        policy={"pools":{"grok":{"default_model":"grok-4.7"}}}
        with patch.object(task.pick,"load_pools",return_value=policy), patch.object(task.pick,"_glm_models",return_value={}):
            with patch.object(task.pick,"policy_allows",return_value=(True,"admitted")),patch.object(task.pick,"_needs_ok",return_value=(True,"admitted")),patch.object(task.pick,"_subject_ok",return_value=(True,"admitted")),patch.object(task.pick,"floor_demotes",return_value=False),patch.object(task.pick,"hard_filter",return_value=(True,"admitted")),patch.object(task.pick,"is_execute_class",return_value=False),patch.object(task.pick,"_emit",return_value="POOL=grok MODEL=grok-4.7 HOST=ubuntu1 MODE=grok"):
                allowed=task.pick._format_pick("review",pool="grok",requested_model="grok-4.7")
                self.assertTrue(allowed.startswith("POOL=grok"),allowed)

    def test_no_manual_continuity_and_direct_strict_route_helper(self):
        task._enforce_manual_route({"POOL":"grok","MODE":"grok","MODEL":"grok-4.7"},"grok","grok-4.7")
        with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_MODEL_ROUTE_MISMATCH"):
            task._enforce_manual_route({"POOL":"grok","MODE":"grok","MODEL":"grok-4.6"},"grok","grok-4.7")

    def test_strict_pool_pin_rejects_cross_provider_execution_mode(self):
        for pool,mode in [("grok","grok"),("glm","glm"),("glm","glm-codex"),
                          ("bailian","qwen"),("minimax","minimax"),("cursor","cursor"),
                          ("ocfree","oc-free"),("go","go-codex")]:
            task._enforce_manual_route({"POOL":pool,"MODE":mode,"MODEL":"synthetic"},pool,None)
        for pool,wrong_mode in [("grok","cursor"),("grok","unknown"),
                                ("glm","qwen"),("bailian","glm"),("ocfree","go-codex")]:
            with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_POOL_MODE_MISMATCH"):
                task._enforce_manual_route({"POOL":pool,"MODE":wrong_mode,"MODEL":"synthetic"},pool,None)
        with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_POOL_MODE_MISMATCH"):
            task._enforce_manual_route({"POOL":"grok","MODEL":"synthetic"},"grok",None)

    def test_request_auto_tokens_normalized_before_any_persistence(self):
        # The intercepted original-root resolution happens BEFORE state dirs,
        # retained packets, leases or worker dispatch. Verify the actual request
        # call frame rather than pretending that preview covers request.
        class PreEffectStop(Exception):
            pass

        cases=(
            ("minimax", "auto", "AUTO", "minimax", None, None),
            ("AUTO", "auto", "auto", None, None, None),
            ("minimax", "MiniMax-M3", None, "minimax", "MiniMax-M3", None),
        )
        for provider, model, preference, want_pool, want_model, want_prefer in cases:
            captured=[]
            def inspect_original_request(root, env):
                caller=sys._getframe(1)
                self.assertEqual(caller.f_code.co_name, "request")
                values=caller.f_locals
                captured.append((values["pool"],values["requested_model"],values["prefer"]))
                raise PreEffectStop("intercepted_before_native_storage")

            with self.subTest(pool=provider, model=model):
                with patch.object(task,"resolve_request_root",new=inspect_original_request):
                    with self.assertRaises(PreEffectStop):
                        task.request("manual-auto-f1-fixture", "review",
                                     packet=ROOT/"no-production-packet", cwd="~", stdin_bytes=None,
                                     pool=provider, requested_model=model,
                                     prefer=preference)
                self.assertEqual(captured,[(want_pool,want_model,want_prefer)])

    def test_request_rejects_malformed_selector_before_root_or_storage(self):
        with patch.object(task,"resolve_request_root") as resolver:
            with self.assertRaisesRegex(task.FabricTaskError,"MANUAL_SELECTOR_INVALID"):
                task.request("manual-invalid-f1-fixture","review",
                             packet=ROOT/"no-production-packet", cwd="~", stdin_bytes=None,
                             pool="minimax", requested_model="MiniMax-M3;evil")
            resolver.assert_not_called()

if __name__=="__main__":
    unittest.main()
