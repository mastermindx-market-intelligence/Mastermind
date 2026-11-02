"""Bounded advisory-only Jev decisions at the native task boundary.

Every case here is offline and inert. The advisory transport is injected, so
no provider, account, credential, lease, runner or worker is touched. These
cases qualify the advisory contract only: default-off at the request
boundary, exactly one bounded POST per evaluation, no retry or account
rotation, no override of an explicit complexity, and error codes that never
carry a credential or the request text.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from urllib import error

import _offline_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
SOURCE = ROOT / "source"
ROLLOUT = ROOT / "rollout"
KEY_ENV = ("EXPERIENTIAL_API_KEY", "EXPLABS_API_KEY", "EXPLABS_KEY_1")
sys.path[:0] = [str(CANDIDATE), str(SOURCE)]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _task_answers(choice="C2_COMPLEX_BOUNDED", confidence=.95, ambiguity=.1):
    return {
        "complexity": {"type": "choice", "choice": choice, "confidence": confidence},
        "architecture_ambiguity": {"type": "noul", "noul": ambiguity},
        "independent_review": {"type": "noul", "noul": .2},
        "execution_risk": {"type": "score", "score": 1},
    }


class OfflineBoundary(unittest.TestCase):
    """Hold the inert boundary so an accidental provider call fails the case."""

    def setUp(self):
        boundary.acquire()
        self.addCleanup(boundary.release)


class JevAdvisoryContract(OfflineBoundary):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="jev-advisory-")
        built = Path(cls.temp.name) / "built"
        result = subprocess.run(
            [sys.executable, str(ROLLOUT / "build_review_stage.py"), "--output", str(built)],
            text=True, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        cls.ext = built / "native-code-stage" / "ext"
        cls.task = cls.ext / "fabric_task.py"
        cls.jev = _load("staged_jev_advisory", cls.ext / "jev_advisory.py")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _transport(self, **kwargs):
        calls = []

        def transport(body, key, timeout):
            calls.append((body, key, timeout))
            return {"answers": _task_answers(**kwargs), "model": "jev-latest",
                    "usage": {"input_tokens": 10, "output_tokens": 5}}

        return calls, transport

    def _advice(self, **kwargs):
        calls, transport = self._transport(**kwargs)
        advice = self.jev.evaluate("task", {"task_class": "domain_orchestration",
                                            "work_packet": "bounded packet"},
                                   api_key="offline-fixture-key", transport=transport)
        return calls, advice

    def test_evaluation_posts_exactly_once_and_stays_advisory_only(self):
        calls, advice = self._advice()
        self.assertEqual(len(calls), 1, "the advisory must post exactly once")
        body, key, timeout = calls[0]
        self.assertLessEqual(len(body), self.jev.MAX_BODY_BYTES)
        self.assertEqual(key, "offline-fixture-key")
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 15)
        self.assertEqual(advice["authority"], "ADVISORY_ONLY")
        self.assertEqual(advice["kind"], "task")
        self.assertEqual(advice["schema"], "mastermind.fabric_jev_advisory/v1")
        self.assertEqual(advice["values"]["complexity"], "C2_COMPLEX_BOUNDED")

    def test_a_refused_call_is_not_retried_and_never_rotates_an_account(self):
        calls = []

        def transport(body, key, timeout):
            calls.append(key)
            raise error.URLError("offline fixture")

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x", "work_packet": "y"},
                              api_key="offline-fixture-key", transport=transport)
        self.assertEqual(caught.exception.code, "TRANSPORT")
        self.assertEqual(len(calls), 1, "a refused advisory must not be retried")
        self.assertEqual(set(calls), {"offline-fixture-key"})

    def test_error_codes_never_carry_the_credential_or_the_request_text(self):
        secret = "offline-fixture-key"

        def transport(body, key, timeout):
            raise error.URLError("offline fixture")

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x",
                                       "work_packet": "private-packet-text"},
                              api_key=secret, transport=transport)
        self.assertEqual(str(caught.exception), "JEV_TRANSPORT")
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn(secret, repr(caught.exception))
        self.assertNotIn("private-packet-text", str(caught.exception))

    def test_an_explicit_complexity_is_never_overridden_by_the_advisory(self):
        _, advice = self._advice(choice="C2_COMPLEX_BOUNDED", confidence=1.0)
        self.assertEqual(self.jev.select_complexity(advice, "C0_MECHANICAL"), "C0_MECHANICAL")
        self.assertEqual(self.jev.select_complexity(advice, "C1_ROUTINE_BOUNDED"), "C1_ROUTINE_BOUNDED")

    def test_a_frontier_answer_asks_the_parent_instead_of_deciding(self):
        _, advice = self._advice(choice="C3_FRONTIER_JUDGMENT", confidence=1.0)
        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.select_complexity(advice, "")
        self.assertEqual(caught.exception.code, "FRONTIER_NEEDS_EXPLICIT_REASON")

    def test_a_missing_complexity_is_filled_only_above_the_confidence_threshold(self):
        _, confident = self._advice(choice="C2_COMPLEX_BOUNDED", confidence=.95)
        self.assertEqual(self.jev.select_complexity(confident, ""), "C2_COMPLEX_BOUNDED")
        _, weak = self._advice(choice="C2_COMPLEX_BOUNDED", confidence=.5)
        self.assertEqual(self.jev.select_complexity(weak, ""), "")

    def test_malformed_and_oversize_answers_fail_closed_with_a_bounded_code(self):
        def transport(body, key, timeout):
            return {"model": "jev-latest", "usage": {}}

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x", "work_packet": "y"},
                              api_key="offline-fixture-key", transport=transport)
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")

        def malformed(body, key, timeout):
            return {"answers": _task_answers(choice="C9_NOT_A_CLASS")}

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x", "work_packet": "y"},
                              api_key="offline-fixture-key", transport=malformed)
        self.assertEqual(caught.exception.code, "MALFORMED_ANSWER")

        def out_of_range(body, key, timeout):
            return {"answers": _task_answers(confidence=2.0)}

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x", "work_packet": "y"},
                              api_key="offline-fixture-key", transport=out_of_range)
        self.assertEqual(caught.exception.code, "MALFORMED_ANSWER")

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x",
                                       "work_packet": "y" * (self.jev.MAX_STATE_BYTES + 1)},
                              api_key="offline-fixture-key", transport=transport)
        self.assertEqual(caught.exception.code, "STATE_TOO_LARGE")

    def test_the_request_boundary_keeps_the_advisory_off_by_default(self):
        tree = ast.parse(self.task.read_text())
        request = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == "request")
        parents = {}
        for node in ast.walk(request):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        imports = [node for node in ast.walk(request)
                   if isinstance(node, ast.Import)
                   and any(alias.name == "jev_advisory" for alias in node.names)]
        self.assertTrue(imports, "the request boundary never imports the advisory")
        for node in imports:
            guarded = False
            current = parents.get(node)
            while current is not None:
                if isinstance(current, ast.If):
                    test = ast.dump(current.test)
                    if "jev_mode" in test and "'off'" in test:
                        guarded = True
                        break
                current = parents.get(current)
            self.assertTrue(guarded, "the advisory import is not behind the default-off guard")
        defaults = [node for node in ast.walk(request)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "FABRIC_JEV_MODE"]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(len(defaults[0].args), 2)
        self.assertEqual(defaults[0].args[1].value, "off")

    def test_the_cli_is_read_only_and_reports_a_bounded_code_without_a_key(self):
        code = ('import runpy, sys\n'
                'sys.argv = ' + repr([str(self.task), "jev-advice", "--kind", "task", "--stdin"]) + '\n'
                'sys.path.insert(0, ' + repr(str(self.ext)) + ')\n'
                'runpy.run_path(' + repr(str(self.task)) + ', run_name="__main__")\n')
        argv = [sys.executable, "-c", boundary.guarded_python_child(code)]
        env = {key: value for key, value in os.environ.items() if key not in KEY_ENV}
        result = subprocess.run(argv, input="bounded packet", env=env,
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 78, result.stdout + result.stderr)
        self.assertIn("JEV_UNAVAILABLE=NOT_CONFIGURED", result.stderr)
        self.assertEqual(result.stdout, "", "an advisory miss must not emit a result payload")

    def test_the_closure_ships_the_advisory_module_from_the_candidate(self):
        manifest = json.loads((ROLLOUT / "native-manifest.json").read_bytes())
        self.assertIn("ext/jev_advisory.py", manifest)
        staged = (self.ext / "jev_advisory.py").read_bytes()
        self.assertEqual(manifest["ext/jev_advisory.py"], hashlib.sha256(staged).hexdigest())
        self.assertEqual(staged, (CANDIDATE / "jev_advisory.py").read_bytes())
        inventory = json.loads((ROLLOUT / "native-source-inventory.json").read_bytes())
        entry = inventory["files"]["ext/jev_advisory.py"]
        self.assertEqual(entry["source"], "candidate/jev_advisory.py")
        self.assertIsNone(entry["installed_preimage_sha256"])
