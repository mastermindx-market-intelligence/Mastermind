"""No-spend qualification routes: narrowly add MiniMax first workers on held hosts.

This test never launches a provider, grants a lease, reads credentials, or changes
host registry. It tests the existing host gate and picker delegation boundaries.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Load the actual qualification source without overriding other test modules'
# pick/host_pick imports. These stubs are patched per test; no host I/O occurs.
_host = ModuleType("host_pick")
_host.load_registry = lambda: {}
_host.evaluate_hosts = lambda *_a, **_k: []
_host.HOSTS_STATE_DIR = "fixture-states"
_pick = ModuleType("pick")
_pick.format_pick = lambda *_a, **_k: "NONE reason=fixture"
_spec = importlib.util.spec_from_file_location(
    "minimax_first_worker_source_under_test", ROOT / "candidate/fabric_host_qualification.py")
qualification = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"host_pick": _host, "pick": _pick}):
    _spec.loader.exec_module(qualification)


class MiniMaxFirstWorkerQualification(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "m1": {"platform": "darwin", "local": False, "roles": ["lanes"],
                   "allowed_modes": ["minimax", "grok", "glm"],
                   "qualification_only_modes": ["minimax", "grok"]},
            "ubuntu4": {"platform": "linux", "local": False, "roles": ["lanes"],
                        "allowed_modes": ["minimax", "cursor"],
                        "qualification_only_modes": ["minimax", "cursor"]},
            "mb": {"platform": "darwin", "local": False, "roles": ["candidate"],
                   "allowed_modes": [], "qualification_only_modes": ["grok", "minimax"]},
            "ubuntu1": {"platform": "linux", "local": False, "roles": ["lanes"],
                        "allowed_modes": ["minimax"], "qualification_only_modes": []},
        }

    def route(self, host, pool="minimax", response=None, gates=None):
        seen = []
        def evaluate(registry, state_dir, mode, **kwargs):
            seen.append((deepcopy(registry), state_dir, mode, kwargs))
            return [{"host": host, "eligible": gates is None,
                     "gates": gates or [{"gate": "fresh", "result": "PASS"}]}]
        answer = response or f"POOL={pool} KEY=- MODEL={'MiniMax-M3' if pool == 'minimax' else 'grok-4.6'} REASON=fixture"
        with patch.object(qualification.host_pick, "evaluate_hosts", side_effect=evaluate), \
             patch.object(qualification.pick, "format_pick", return_value=answer) as picker:
            result = qualification.qualification_route(
                host, pool=pool, task_class="fix_build" if pool == "minimax" else "reviewer",
                complexity="C1_ROUTINE_BOUNDED" if pool == "minimax" else "C3_FRONTIER_JUDGMENT",
                reason="bounded first-worker qualification", root="legitimate-root",
                parent="legitimate-parent", registry=self.registry, state_dir="fixture-states")
        return result, seen, picker

    def test_m1_minimax_clears_only_the_exact_hold_in_a_transient_view(self):
        original = deepcopy(self.registry)
        output, seen, picker = self.route("m1")
        self.assertEqual(output, "POOL=minimax KEY=- MODEL=MiniMax-M3 REASON=fixture HOST=m1 MODE=minimax")
        view, state_dir, mode, kwargs = seen[0]
        self.assertEqual(mode, "minimax")
        self.assertEqual(state_dir, "fixture-states")
        self.assertEqual(kwargs["max_age"], 30)
        self.assertEqual(kwargs["excluded"], {"ubuntu1", "ubuntu4", "mb"})
        self.assertEqual(view["m1"]["qualification_only_modes"], ["grok"])
        self.assertEqual(view["ubuntu4"]["qualification_only_modes"], ["minimax", "cursor"])
        self.assertEqual(self.registry, original)
        self.assertEqual(picker.call_args.kwargs["pool"], "minimax")

    def test_ubuntu4_minimax_keeps_cursor_held(self):
        original = deepcopy(self.registry)
        output, seen, _ = self.route("ubuntu4")
        self.assertIn("HOST=ubuntu4 MODE=minimax", output)
        self.assertEqual(seen[0][0]["ubuntu4"]["qualification_only_modes"], ["cursor"])
        self.assertEqual(seen[0][0]["m1"]["qualification_only_modes"], ["minimax", "grok"])
        self.assertEqual(self.registry, original)

    def test_old_grok_route_remains_supported(self):
        output, seen, _ = self.route("m1", "grok")
        self.assertIn("HOST=m1 MODE=grok", output)
        self.assertEqual(seen[0][0]["m1"]["qualification_only_modes"], ["minimax"])

    def test_no_widening_to_macbook_other_hosts_or_other_pools(self):
        for host, pool in (("mb", "minimax"), ("ubuntu1", "minimax"),
                           ("ubuntu4", "grok"), ("m1", "cursor"),
                           ("arbitrary", "minimax")):
            with self.subTest(host=host, pool=pool):
                with self.assertRaisesRegex(ValueError, "QUALIFICATION_SCOPE_REFUSED"):
                    qualification.qualification_route(
                        host, pool=pool, task_class="fix_build", complexity="C1_ROUTINE_BOUNDED",
                        reason="fixture", root="root", parent="parent", registry=self.registry)

    def test_missing_root_or_parent_always_refuses(self):
        for root, parent in ((None, "parent"), ("root", None), ("", "parent"), ("root", "")):
            with self.subTest(root=root, parent=parent):
                with self.assertRaisesRegex(ValueError, "QUALIFICATION_SCOPE_REFUSED"):
                    qualification.qualification_route("m1", pool="minimax", task_class="fix_build",
                        complexity="C1_ROUTINE_BOUNDED", reason="fixture", root=root,
                        parent=parent, registry=self.registry)

    def test_only_the_named_pending_mode_can_be_temporarily_cleared(self):
        changed = deepcopy(self.registry)
        changed["m1"]["qualification_only_modes"] = ["grok"]
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_NOT_PENDING"):
            qualification.qualification_route("m1", pool="minimax", task_class="fix_build",
                complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                parent="parent", registry=changed)
        changed["m1"]["qualification_only_modes"] = ["minimax", "minimax"]
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_NOT_PENDING"):
            qualification.qualification_route("m1", pool="minimax", task_class="fix_build",
                complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                parent="parent", registry=changed)

    def test_wrong_platform_or_local_seat_never_qualifies(self):
        for override in ({"platform": "linux"}, {"local": True}):
            changed = deepcopy(self.registry)
            changed["m1"].update(override)
            with self.assertRaisesRegex(ValueError, "QUALIFICATION_HOST_REFUSED"):
                qualification.qualification_route("m1", pool="minimax", task_class="fix_build",
                    complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                    parent="parent", registry=changed)

    def test_host_gates_and_provider_substitution_still_fail_closed(self):
        failure = [{"gate": "disk", "result": "FAIL"},
                   {"gate": "automatic-qualification", "result": "PASS"}]
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_PREREQUISITE_REFUSED:disk"):
            self.route("ubuntu4", gates=failure)
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_PROVIDER_REFUSED"):
            self.route("m1", response="POOL=glm MODEL=glm-5.3-flash REASON=fallback")

    def test_request_cli_reaches_ubuntu4_but_keeps_normal_host_gates(self):
        # Parse the real CLI call site without dispatching a worker or reading credentials.
        import ast
        source = (ROOT / "candidate/fabric_task.py").read_text()
        parser = ast.parse(source)
        calls = [n for n in ast.walk(parser) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
                 and n.args and isinstance(n.args[0], ast.Constant)
                 and n.args[0].value == "--qualification-host"]
        self.assertEqual(len(calls), 1)
        opts = {k.arg: ast.literal_eval(k.value) for k in calls[0].keywords
                if k.arg in ("choices", "help")}
        self.assertEqual(opts["choices"], ("mb", "m1", "ubuntu4"))
        self.assertIn("MiniMax", opts["help"])
        self.assertIn("Ubuntu4", opts["help"])
        # Admission remains in qualification_route, not in the parser choices.
        self.assertIn("qualification_host, pool=pool", source)

    def test_candidate_task_entrypoint_routes_minimax_without_mutating_source_preimage(self):
        candidate = (ROOT / "candidate/fabric_task.py").read_text()
        source = (ROOT / "source/fabric_task.py").read_text()
        self.assertIn('if pool not in ("grok", "minimax") or artifact_names or native_return or requested_model or prefer:', candidate)
        self.assertIn('qualification_host, pool=pool, task_class=task_class, complexity=complexity,', candidate)
        self.assertEqual(candidate.count('qualification_host, pool=pool, task_class=task_class, complexity=complexity,'), 1)
        self.assertIn('if pool != "grok" or artifact_names or native_return or requested_model or prefer:', source)
        self.assertNotIn('qualification_host, pool=pool, task_class=task_class, complexity=complexity,', source)
        # The immutable source preimages stay intact for the native staging owner.
        import hashlib
        import json
        preimages = json.loads((ROOT / "rollout/native-preimages.json").read_text())["files"]
        for name in ("fabric_task.py", "fabric_host_qualification.py"):
            raw = (ROOT / "source" / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), preimages[name])


if __name__ == "__main__":
    unittest.main()
