"""Ubuntu4 central GLM-Codex first-worker qualification and auth-branch regressions.

This suite never launches a provider, reserves a lease, reads a credential,
touches a host registry or produces a remote effect. It exercises the existing
qualifier, the task adapter's option gate and the controller's GLM auth branch
through inert fixtures only.

Central GLM-Codex means: pool ``glm``, executor mode ``glm-codex``, exact host
``ubuntu4``, and the existing lease-v1 central capability as the only
credential. Local provider enrollment stays optional and adapter-specific.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "candidate/remote_sub.sh"
ADAPTER = ROOT / "candidate/fabric_task.py"

# Load the actual qualification source without overriding other test modules'
# pick/host_pick imports. These stubs are patched per test; no host I/O occurs.
_host = ModuleType("host_pick")
_host.load_registry = lambda: {}
_host.evaluate_hosts = lambda *_a, **_k: []
_host.refresh_stale = lambda _hosts: True
_host.HOSTS_STATE_DIR = "fixture-states"
_pick = ModuleType("pick")
_pick.format_pick = lambda *_a, **_k: "NONE reason=fixture"
_spec = importlib.util.spec_from_file_location(
    "ubuntu4_glm_central_source_under_test", ROOT / "candidate/fabric_host_qualification.py")
qualification = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"host_pick": _host, "pick": _pick}):
    _spec.loader.exec_module(qualification)


class Ubuntu4GlmCentralQualification(unittest.TestCase):
    """The explicit first-worker qualifier on the central GLM-Codex route."""

    def setUp(self):
        self.registry = {
            "ubuntu4": {"platform": "linux", "local": False, "roles": ["lanes"],
                        "allowed_modes": ["glm-codex", "minimax", "grok", "cursor"],
                        "qualification_only_modes": ["glm-codex", "glm", "minimax",
                                                    "grok", "cursor"]},
            "m1": {"platform": "darwin", "local": False, "roles": ["lanes"],
                   "allowed_modes": ["grok", "minimax", "glm"],
                   "qualification_only_modes": ["grok", "minimax"]},
            "mb": {"platform": "darwin", "local": False, "roles": ["candidate"],
                   "allowed_modes": [], "qualification_only_modes": ["grok", "minimax"]},
            "ubuntu1": {"platform": "linux", "local": False, "roles": ["lanes"],
                        "allowed_modes": ["minimax"], "qualification_only_modes": []},
        }

    def route(self, host, pool="glm", response=None, gates=None, registry=None):
        seen = []

        def evaluate(registry_view, state_dir, mode, **kwargs):
            seen.append((json.loads(json.dumps(registry_view)), state_dir, mode, kwargs))
            return [{"host": host, "eligible": gates is None,
                     "gates": gates or [{"gate": "fresh", "result": "PASS"}]}]

        answer = response or f"POOL={pool} KEY=- MODEL=fixture-model REASON=fixture"
        with patch.object(qualification.host_pick, "evaluate_hosts", side_effect=evaluate), \
             patch.object(qualification.pick, "format_pick", return_value=answer) as picker:
            result = qualification.qualification_route(
                host, pool=pool, task_class="fix_build",
                complexity="C1_ROUTINE_BOUNDED", reason="bounded first-worker qualification",
                root="legitimate-root", parent="legitimate-parent",
                registry=self.registry if registry is None else registry,
                state_dir="fixture-states")
        return result, seen, picker

    # --- positive -----------------------------------------------------------

    def test_glm_pool_qualifies_only_the_glm_codex_executor_mode(self):
        original = json.loads(json.dumps(self.registry))
        output, seen, picker = self.route("ubuntu4")
        self.assertTrue(output.startswith("POOL=glm "))
        self.assertIn("HOST=ubuntu4 MODE=glm-codex", output)
        self.assertNotIn("MODE=glm ", output)
        self.assertEqual(len(seen), 1)
        view, state_dir, mode, options = seen[0]
        self.assertEqual(mode, "glm-codex")
        self.assertEqual(state_dir, "fixture-states")
        self.assertEqual(options["max_age"], 30)
        self.assertEqual(options["excluded"], {"m1", "mb", "ubuntu1"})
        # Only the glm-codex hold is cleared; glm and every other hold remain.
        self.assertEqual(view["ubuntu4"]["qualification_only_modes"],
                         ["glm", "minimax", "grok", "cursor"])
        self.assertEqual(view["m1"]["qualification_only_modes"], ["grok", "minimax"])
        self.assertEqual(self.registry, original)
        self.assertEqual(picker.call_args.kwargs["pool"], "glm")

    def test_stale_host_refreshes_one_original_telemetry_probe(self):
        initial = [{"host": "ubuntu4", "eligible": False,
                    "gates": [{"gate": "fresh", "result": "FAIL"},
                              {"gate": "thermal", "result": "FAIL"},
                              {"gate": "pressure", "result": "FAIL"}]}]
        current = [{"host": "ubuntu4", "eligible": True,
                    "gates": [{"gate": "fresh", "result": "PASS"},
                              {"gate": "thermal", "result": "PASS"},
                              {"gate": "pressure", "result": "PASS"}]}]
        with (
            patch.object(qualification.host_pick, "evaluate_hosts",
                         side_effect=[initial, current]) as evaluate,
            patch.object(qualification.host_pick, "refresh_stale",
                         create=True, return_value=True) as refresh,
            patch.object(qualification.pick, "format_pick",
                         return_value="POOL=glm KEY=- MODEL=fixture") as picker,
        ):
            result = qualification.qualification_route(
                "ubuntu4", pool="glm", task_class="mechanical",
                complexity="C0_MECHANICAL", reason="read only",
                root="original-root", parent="original-parent", registry=self.registry)
        self.assertIn("HOST=ubuntu4 MODE=glm-codex", result)
        refresh.assert_called_once_with(["ubuntu4"])
        self.assertEqual(evaluate.call_count, 2)
        self.assertEqual([call.kwargs["max_age"] for call in evaluate.call_args_list], [30, 30])
        picker.assert_called_once()

    def test_reprobe_does_not_waive_a_real_thermal_failure(self):
        initial = [{"host": "ubuntu4", "eligible": False,
                    "gates": [{"gate": "fresh", "result": "FAIL"}]}]
        hot = [{"host": "ubuntu4", "eligible": False,
                "gates": [{"gate": "fresh", "result": "PASS"},
                          {"gate": "thermal", "result": "FAIL"}]}]
        with (
            patch.object(qualification.host_pick, "evaluate_hosts",
                         side_effect=[initial, hot]) as evaluate,
            patch.object(qualification.host_pick, "refresh_stale",
                         create=True, return_value=True) as refresh,
            patch.object(qualification.pick, "format_pick") as picker,
        ):
            with self.assertRaisesRegex(ValueError, "QUALIFICATION_PREREQUISITE_REFUSED:thermal"):
                qualification.qualification_route(
                    "ubuntu4", pool="glm", task_class="mechanical",
                    complexity="C0_MECHANICAL", reason="read only",
                    root="original-root", parent="original-parent", registry=self.registry)
        refresh.assert_called_once_with(["ubuntu4"])
        self.assertEqual(evaluate.call_count, 2)
        picker.assert_not_called()

    def test_failed_telemetry_probe_refuses_before_provider_selection(self):
        initial = [{"host": "ubuntu4", "eligible": False,
                    "gates": [{"gate": "fresh", "result": "FAIL"}]}]
        with (
            patch.object(qualification.host_pick, "evaluate_hosts",
                         return_value=initial) as evaluate,
            patch.object(qualification.host_pick, "refresh_stale",
                         create=True, return_value=False) as refresh,
            patch.object(qualification.pick, "format_pick") as picker,
        ):
            with self.assertRaisesRegex(ValueError, "QUALIFICATION_TELEMETRY_REFRESH_FAILED"):
                qualification.qualification_route(
                    "ubuntu4", pool="glm", task_class="mechanical",
                    complexity="C0_MECHANICAL", reason="read only",
                    root="original-root", parent="original-parent", registry=self.registry)
        refresh.assert_called_once_with(["ubuntu4"])
        evaluate.assert_called_once()
        picker.assert_not_called()

    def test_glm_route_still_requires_the_canonical_glm_pick_pool(self):
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_PROVIDER_REFUSED"):
            self.route("ubuntu4", response="POOL=grok KEY=- MODEL=grok-4.6 REASON=substitution")
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_PROVIDER_REFUSED"):
            self.route("ubuntu4", response="NONE reason=fixture")

    # --- refusals -----------------------------------------------------------

    def test_glm_is_not_widened_to_other_hosts_or_to_a_direct_mode(self):
        for host, pool in (("mb", "glm"), ("m1", "glm"), ("ubuntu1", "glm"),
                           ("ubuntu4", "glm-codex"), ("m1", "glm-codex"),
                           ("ubuntu4", "cursor"), ("ubuntu4", "qwen")):
            with self.subTest(host=host, pool=pool):
                with self.assertRaisesRegex(ValueError, "QUALIFICATION_SCOPE_REFUSED"):
                    qualification.qualification_route(
                        host, pool=pool, task_class="fix_build",
                        complexity="C1_ROUTINE_BOUNDED", reason="fixture",
                        root="root", parent="parent", registry=self.registry)

    def test_glm_requires_the_actual_glm_codex_qualification_hold(self):
        changed = json.loads(json.dumps(self.registry))
        changed["ubuntu4"]["qualification_only_modes"] = ["glm", "minimax", "grok", "cursor"]
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_NOT_PENDING"):
            qualification.qualification_route("ubuntu4", pool="glm", task_class="fix_build",
                complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                parent="parent", registry=changed)
        changed["ubuntu4"]["qualification_only_modes"] = ["glm-codex", "glm-codex"]
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_NOT_PENDING"):
            qualification.qualification_route("ubuntu4", pool="glm", task_class="fix_build",
                complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                parent="parent", registry=changed)

    def test_glm_refuses_malformed_holds_before_host_evaluation(self):
        malformed = ("glm-codex", None, ["glm-codex", []],
                     ["glm-codex", {}], ["glm-codex", 1],
                     ["glm-codex", "glm-codex"])
        for held in malformed:
            with self.subTest(held=held):
                changed = json.loads(json.dumps(self.registry))
                changed["ubuntu4"]["qualification_only_modes"] = held
                with patch.object(qualification.host_pick, "evaluate_hosts") as evaluate:
                    with self.assertRaisesRegex(ValueError, "QUALIFICATION_NOT_PENDING"):
                        qualification.qualification_route(
                            "ubuntu4", pool="glm", task_class="fix_build",
                            complexity="C1_ROUTINE_BOUNDED", reason="fixture",
                            root="root", parent="parent", registry=changed)
                    evaluate.assert_not_called()

    def test_glm_requires_the_correct_nonlocal_platform_and_a_remote_host(self):
        for override in ({"platform": "darwin"}, {"local": True}):
            changed = json.loads(json.dumps(self.registry))
            changed["ubuntu4"].update(override)
            with self.assertRaisesRegex(ValueError, "QUALIFICATION_HOST_REFUSED"):
                qualification.qualification_route("ubuntu4", pool="glm", task_class="fix_build",
                    complexity="C1_ROUTINE_BOUNDED", reason="fixture", root="root",
                    parent="parent", registry=changed)

    def test_glm_requires_root_and_parent(self):
        for root, parent in ((None, "parent"), ("root", None), ("", "parent"), ("root", "")):
            with self.subTest(root=root, parent=parent):
                with self.assertRaisesRegex(ValueError, "QUALIFICATION_SCOPE_REFUSED"):
                    qualification.qualification_route("ubuntu4", pool="glm", task_class="fix_build",
                        complexity="C1_ROUTINE_BOUNDED", reason="fixture", root=root,
                        parent=parent, registry=self.registry)

    def test_glm_keeps_the_physical_load_and_freshness_gates_fail_closed(self):
        for gate in ("physical", "load", "fresh", "disk", "lane-ceiling"):
            with self.subTest(gate=gate):
                with self.assertRaisesRegex(
                        ValueError, "QUALIFICATION_PREREQUISITE_REFUSED:" + gate):
                    self.route("ubuntu4", gates=[{"gate": gate, "result": "FAIL"}])
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_PREREQUISITE_REFUSED:"):
            self.route("ubuntu4", gates=[{"gate": "fresh", "result": "FAIL"}])

    def test_retained_grok_and_minimax_qualification_is_unchanged(self):
        original = json.loads(json.dumps(self.registry))
        output, seen, picker = self.route("ubuntu4", pool="grok")
        self.assertIn("HOST=ubuntu4 MODE=grok", output)
        self.assertEqual(seen[0][2], "grok")
        self.assertEqual(seen[0][0]["ubuntu4"]["qualification_only_modes"],
                         ["glm-codex", "glm", "minimax", "cursor"])
        self.assertEqual(picker.call_args.kwargs["pool"], "grok")
        output, seen, picker = self.route("m1", pool="minimax")
        self.assertIn("HOST=m1 MODE=minimax", output)
        self.assertEqual(seen[0][2], "minimax")
        self.assertEqual(seen[0][0]["m1"]["qualification_only_modes"], ["grok"])
        self.assertEqual(self.registry, original)


class Ubuntu4GlmCentralAdapter(unittest.TestCase):
    """The task adapter admits the central pool through the existing qualifier."""

    def test_cli_admits_pool_glm_through_the_existing_qualification_host(self):
        source = ADAPTER.read_text()
        parser = ast.parse(source)
        calls = [n for n in ast.walk(parser) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
                 and n.args and isinstance(n.args[0], ast.Constant)
                 and n.args[0].value == "--qualification-host"]
        self.assertEqual(len(calls), 1)
        opts = {k.arg: ast.literal_eval(k.value) for k in calls[0].keywords
                if k.arg in ("choices", "help")}
        self.assertEqual(opts["choices"], ("mb", "m1", "ubuntu4"))
        self.assertIn("GLM-Codex", opts["help"])
        self.assertIn("Ubuntu4", opts["help"])
        self.assertIn("MiniMax", opts["help"])
        # Admission stays in the qualifier, not in the parser choices.
        self.assertIn("qualification_host, pool=pool", source)

    def test_pool_glm_is_the_only_added_qualification_option(self):
        source = ADAPTER.read_text()
        self.assertIn(
            'if pool not in ("grok", "minimax", "glm") or artifact_names or native_return '
            'or requested_model or prefer:', source)
        # No generic mode/host override may appear beside the existing options.
        for forbidden in ('"--mode"', '"--host"', '"--qualification-mode"'):
            self.assertNotIn(forbidden, source)
        # The mutual exclusions stay in force for the central pool as well.
        for guard in ("FABRIC_NEW_MACRO_WORKTREE_SCOPE_REFUSED", "CPU_SCOPE_REQUEST_UNQUALIFIED",
                      "QUALIFICATION_OPTIONS_REFUSED", "NATIVE_RETURN_REQUIRES_CURRENT_ORIGINAL_PARENT"):
            self.assertIn(guard, source)

    def test_controller_typed_central_refusal_is_recognised_as_a_prelaunch_failure(self):
        source = ADAPTER.read_text()
        parser = ast.parse(source)
        node = next(n for n in parser.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "_GLM_AUTH_GUARD_RE"
                            for t in n.targets))
        pattern = eval(compile(ast.Expression(node.value), "<guard>", "eval"), {"re": re})
        prefix = ("2026-11-06T00:00Z [remote_sub id=run-1 host=ubuntu4] ")
        for token in ("GLM_REMOTE_AUTH_UNAVAILABLE", "GLM_CENTRAL_CAPABILITY_REQUIRED"):
            with self.subTest(token=token):
                self.assertIsNotNone(pattern.fullmatch(prefix + token + " host=ubuntu4"))
        self.assertIsNone(pattern.fullmatch(prefix + "GLM_CENTRAL_CAPABILITY_REQUIRED host=other"))
        self.assertIsNone(pattern.fullmatch(prefix + "SOME_OTHER_REFUSAL host=ubuntu4"))

    def test_source_preimages_stay_immutable(self):
        preimages = json.loads((ROOT / "rollout/native-preimages.json").read_text())["files"]
        for name in ("fabric_task.py", "fabric_host_qualification.py"):
            raw = (ROOT / "source" / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), preimages[name])


def _fake_transport(tmp_path: Path) -> Path:
    """A scripted SSH stand-in: capability probe, legacy credential probe, upload."""
    script = tmp_path / "fake_ssh.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, os, sys\n"
        "cmd = sys.argv[-1] if len(sys.argv) > 1 else ''\n"
        "trace = os.environ.get('TRACE')\n"
        "if trace:\n"
        "    open(trace, 'a').write(cmd + '\\n')\n"
        "if 'worker_capabilities' in cmd:\n"
        "    sys.exit(0 if os.environ.get('LEASE_V1_READY') == '1' else 1)\n"
        "if 'health >/dev/null &&' in cmd:\n"
        "    sys.exit(0 if os.environ.get('LEGACY_CREDENTIAL') == '1' else 1)\n"
        "if 'PY_GLM_REMOTE_META' in cmd:\n"
        "    data = open(os.path.join(os.environ['CAP_DIR'], 'uploaded.json'), 'rb').read()\n"
        "    print(hashlib.sha256(data).hexdigest())\n"
        "elif 'glm-cap.tmp' in cmd:\n"
        "    path = os.path.join(os.environ['CAP_DIR'], 'uploaded.json')\n"
        "    open(path, 'wb').write(sys.stdin.buffer.read())\n")
    script.chmod(0o700)
    return script


def _fake_ext(tmp_path: Path) -> Path:
    """Inert stand-ins for the controller-owned capability issuer and digest helper."""
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "glm_remote_capability.py").write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "out = sys.argv[sys.argv.index('--out') + 1]\n"
        "value = {'token': 'v1.fixture', 'expires_at': 4102444800.0,\n"
        "         'account': 'fixture-account', 'lease_id': 'fixture-lease',\n"
        "         'model': 'glm-5.3-flash', 'run_id': 'fixture-run',\n"
        "         'host': 'ubuntu4', 'root': 'fixture-root'}\n"
        "handle = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n"
        "with os.fdopen(handle, 'w') as stream:\n"
        "    json.dump(value, stream, sort_keys=True)\n")
    (ext / "remote_sub_helpers.py").write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, sys\n"
        "if sys.argv[1] == 'glm-cap-sha':\n"
        "    print(hashlib.sha256(open(sys.argv[2], 'rb').read()).hexdigest())\n"
        "    sys.exit(0)\n"
        "sys.exit(2)\n")
    return ext


class Ubuntu4GlmCentralControllerBranch(unittest.TestCase):
    """The controller's GLM auth branch on the exact central route."""

    def setUp(self):
        self.source = CONTROLLER.read_text()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.transport = _fake_transport(self.root)
        self.ext = _fake_ext(self.root)
        self.cap_dir = self.root / "caps"
        self.cap_dir.mkdir()

    def slice(self, start_marker, end_marker):
        """Slice one controller region. A missing region yields empty text.

        The empty result keeps the auth-branch fixtures runnable against the
        exact preimage, where the central route does not exist yet.
        """
        if start_marker not in self.source:
            return ""
        start = self.source.index(start_marker)
        end = self.source.index(end_marker, start)
        return self.source[start:end]

    def run_branch(self, *, mode, host, lease_v1, legacy):
        trace = self.root / "trace.txt"
        if trace.exists():
            trace.unlink()
        route = self.slice("# The central GLM-Codex route is exact:",
                           "# Central GLM route end:")
        branch = self.slice("# GLM-Codex remote workers prefer a short-lived capability",
                            "# A separate bounded operator capability travels only through the existing")
        script = (
            "set -u\n"
            "log() { printf '%s\\n' \"$*\"; }\n"
            "commission_run() { local label=\"$1\"; shift; \"$@\"; }\n"
            "commission_command() { local label=\"$1\"; local input=\"$2\"; shift 2;\n"
            "  if [ \"$input\" = - ]; then \"$@\"; else \"$@\" < \"$input\"; fi; }\n"
            "MODE=__MODE__\nHOST_ARG=__HOST__\nCANONICAL_PAID_ACTIVE=0\n"
            "PLAIN_PHYSICAL_OWNER=0\nREMOTE_LANES_Q='\"$HOME/lanes\"'\n"
            "ID=fixture-run\nLEASE_ID=fixture-lease\nORCH_ID=fixture-root\n"
            "POOL_ACCOUNT=fixture-account\nMODEL=glm-5.3-flash\nCHILD_TIMEOUT=1200\n"
            "SSH_CMD=__TRANSPORT__\nSSH_ALIAS=fixture-host\nHERE=__EXT__\nREMOTE_SUB_PYTHON=python3\n"
            "GLM_CAP_REMOTE=''\nGLM_CAP_LOCAL=''\nTEMP_FILES=()\nRC=0\n"
            "GLM_CENTRAL_ROUTE=0\nHOST_ENV=''\n"
            "__ROUTE__\n"
            "printf 'ROUTE=%s\\nHOST_ENV=%s\\n' \"$GLM_CENTRAL_ROUTE\" \"$HOST_ENV\"\n"
            "__BRANCH__\n"
            "printf 'REACHED_END\\n'\n"
            "exit \"${RC:-0}\"\n")
        script = (script.replace("__MODE__", mode).replace("__HOST__", host)
                  .replace("__TRANSPORT__", str(self.transport)).replace("__EXT__", str(self.ext))
                  .replace("__ROUTE__", route).replace("__BRANCH__", branch))
        env = dict(os.environ)
        env.update(TRACE=str(trace), CAP_DIR=str(self.cap_dir),
                   LEASE_V1_READY="1" if lease_v1 else "0",
                   LEGACY_CREDENTIAL="1" if legacy else "0",
                   TMPDIR=str(self.root))
        result = subprocess.run(["bash", "-c", script], cwd=self.root, env=env,
                                capture_output=True, timeout=30)
        calls = trace.read_text().splitlines() if trace.exists() else []
        return result, calls

    def test_ubuntu4_without_the_central_capability_refuses_before_any_credential_read(self):
        result, calls = self.run_branch(mode="glm-codex", host="ubuntu4",
                                        lease_v1=False, legacy=True)
        self.assertEqual(result.returncode, 78)
        out = result.stdout.decode()
        self.assertIn("GLM_CENTRAL_CAPABILITY_REQUIRED host=ubuntu4", out)
        self.assertNotIn("GLM_LEGACY_LOCAL_CREDENTIAL", out)
        self.assertNotIn("GLM_REMOTE_AUTH_UNAVAILABLE", out)
        self.assertNotIn("REACHED_END", out)
        # The legacy credential probe was never invoked on this exact route.
        self.assertFalse([c for c in calls if "health >/dev/null &&" in c])
        # The lease-v1 readiness probe was attempted and refused.
        self.assertTrue([c for c in calls if "worker_capabilities" in c])

    def test_ubuntu4_central_capability_success_uses_the_capsule_and_no_mutable_hook(self):
        result, calls = self.run_branch(mode="glm-codex", host="ubuntu4",
                                        lease_v1=True, legacy=True)
        self.assertEqual(result.returncode, 0)
        out = result.stdout.decode()
        self.assertIn("GLM_CAPABILITY_READY", out)
        self.assertNotIn("GLM_LEGACY_LOCAL_CREDENTIAL", out)
        self.assertNotIn("GLM_CENTRAL_CAPABILITY_REQUIRED", out)
        self.assertIn("REACHED_END", out)
        self.assertFalse([c for c in calls if "health >/dev/null &&" in c])
        uploaded = self.cap_dir / "uploaded.json"
        self.assertTrue(uploaded.is_file())
        capsule = json.loads(uploaded.read_text())
        self.assertEqual(capsule["lease_id"], "fixture-lease")
        self.assertEqual(capsule["host"], "ubuntu4")
        # The exact route never sources the mutable host hook.
        self.assertNotIn("HOST_ENV.sh", out.split("ROUTE=", 1)[1])

    def test_the_exact_route_drops_the_mutable_hook_and_keeps_the_frozen_path(self):
        result, calls = self.run_branch(mode="glm-codex", host="ubuntu4",
                                        lease_v1=False, legacy=False)
        out = result.stdout.decode()
        self.assertIn("ROUTE=1", out)
        host_env = out.split("HOST_ENV=", 1)[1].splitlines()[0]
        self.assertNotIn("HOST_ENV.sh", host_env)
        self.assertIn("unset GLM_SHIM_TOKEN", host_env)
        self.assertIn(".local/bin", host_env)
        self.assertIn("venv/bin", host_env)
        # Only the lease-v1 readiness probe ran; no legacy credential read.
        self.assertFalse([c for c in calls if "health >/dev/null &&" in c])
        self.assertTrue([c for c in calls if "worker_capabilities" in c])

    def test_other_hosts_keep_the_existing_legacy_credential_compatibility(self):
        result, calls = self.run_branch(mode="glm-codex", host="m1",
                                        lease_v1=False, legacy=True)
        self.assertEqual(result.returncode, 0)
        out = result.stdout.decode()
        self.assertIn("GLM_LEGACY_LOCAL_CREDENTIAL host=m1", out)
        self.assertNotIn("GLM_CENTRAL_CAPABILITY_REQUIRED", out)
        self.assertIn("REACHED_END", out)
        self.assertTrue([c for c in calls if "health >/dev/null &&" in c])

    def test_other_hosts_keep_the_existing_unavailable_refusal(self):
        result, calls = self.run_branch(mode="glm-codex", host="m1",
                                        lease_v1=False, legacy=False)
        self.assertEqual(result.returncode, 78)
        out = result.stdout.decode()
        self.assertIn("GLM_REMOTE_AUTH_UNAVAILABLE host=m1", out)
        self.assertNotIn("GLM_CENTRAL_CAPABILITY_REQUIRED", out)
        self.assertNotIn("REACHED_END", out)

    def test_other_hosts_keep_the_existing_central_capability_path(self):
        result, calls = self.run_branch(mode="glm-codex", host="m1",
                                        lease_v1=True, legacy=False)
        self.assertEqual(result.returncode, 0)
        out = result.stdout.decode()
        self.assertIn("GLM_CAPABILITY_READY", out)
        self.assertIn("REACHED_END", out)

    def test_the_glm_pool_mode_itself_is_not_a_central_route(self):
        result, calls = self.run_branch(mode="glm", host="ubuntu4",
                                        lease_v1=False, legacy=False)
        out = result.stdout.decode()
        self.assertIn("ROUTE=0", out)
        self.assertIn("HOST_ENV.sh", out.split("HOST_ENV=", 1)[1].splitlines()[0])

    def test_controller_shell_syntax_is_valid(self):
        subprocess.run(["bash", "-n", str(CONTROLLER)], check=True, capture_output=True)


class Ubuntu4GlmCentralRequest(unittest.TestCase):
    """The adapter routes pool glm through the existing qualification host."""

    def setUp(self):
        import test_adapter_continuity as fixture
        self.api = fixture.api
        import fabric_host_qualification as qualifier_module
        import pool_ledger
        self.qualifier = qualifier_module
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = []
        self.sequence = 0
        self.evaluate_mode = None
        registry = {"ubuntu4": {"platform": "linux", "local": False, "roles": ["lanes"],
                                "allowed_modes": ["glm-codex"],
                                "qualification_only_modes": ["glm-codex"]}}

        def evaluate(_view, _state_dir, mode, **_kwargs):
            self.evaluate_mode = mode
            return [{"host": "ubuntu4", "eligible": True,
                     "gates": [{"gate": "fresh", "result": "PASS"}]}]

        def transport(argv, env):
            self.calls.append((argv, dict(env)))
            return type("Result", (), {"returncode": 0})()

        for target, name, value in (
            (self.api, "HERE", self.root),
            (self.api.pick, "launch_policy", lambda *_a, **_k: {"allowed": True}),
            (self.api.subprocess, "run", transport),
            (pool_ledger, "LEDGER_PATH", str(self.root / "ledger.jsonl")),
            (qualifier_module.pick, "format_pick",
             lambda *_a, **_k: "POOL=glm MODEL=glm-5.3-flash REASON=fixture"),
            (qualifier_module.host_pick, "load_registry", lambda *_a, **_k: registry),
            (qualifier_module.host_pick, "evaluate_hosts", evaluate),
        ):
            item = patch.object(target, name, value)
            item.start()
            self.addCleanup(item.stop)

    def request(self, **overrides):
        self.sequence += 1
        options = dict(cwd="~", packet=None, stdin_bytes=b"bounded central fixture\n",
                       pool="glm", qualification_host="ubuntu4",
                       root_id="original-root", parent_run_id="assigning-parent",
                       task_complexity="C0_MECHANICAL")
        options.update(overrides)
        run_id = "u4-glm-central-fixture-%d" % self.sequence
        return self.api.request(run_id, "mechanical", **options)

    def test_pool_glm_reaches_the_glm_codex_executor_on_ubuntu4(self):
        self.assertEqual(self.request(), 0)
        argv, env = self.calls[0]
        self.assertEqual(argv[2:4], ["ubuntu4", "glm-codex"])
        self.assertEqual(self.evaluate_mode, "glm-codex")
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "original-root")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "assigning-parent")

    def test_the_glm_qualification_keeps_every_mutual_exclusion(self):
        for override in ({"requested_model": "glm-5.3"},
                         {"prefer": "glm"},
                         {"artifact_names": ["central.bin"]},
                         {"native_return": True}):
            with self.subTest(override=sorted(override)):
                with self.assertRaisesRegex(self.api.FabricTaskError,
                                            "QUALIFICATION_OPTIONS_REFUSED"):
                    self.request(**override)
        self.assertEqual(self.calls, [])

    def test_another_qualification_host_stays_refused_for_pool_glm(self):
        with self.assertRaisesRegex(ValueError, "QUALIFICATION_SCOPE_REFUSED"):
            self.request(qualification_host="m1")
        self.assertEqual(self.calls, [])

    def test_a_new_macro_worktree_cannot_be_combined_with_the_central_qualification(self):
        with self.assertRaisesRegex(self.api.FabricTaskError,
                                    "FABRIC_NEW_MACRO_WORKTREE_SCOPE_REFUSED"):
            self.request(new_macro_worktree="a" * 40, cwd="~/lanes/repos/macro")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
