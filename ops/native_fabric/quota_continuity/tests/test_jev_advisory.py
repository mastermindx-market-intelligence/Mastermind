"""Bounded advisory-only Jev decisions at the native task boundary.

Every case here is offline and inert. The advisory transport is injected, so
no provider, account, credential, lease, runner or worker is touched. These
cases qualify the advisory contract only: default-off at the request
boundary, exactly one bounded POST per evaluation, no retry or account
rotation, no override of an explicit complexity, and error codes that never
carry a credential or the request text.
"""
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib import error

import _offline_boundary as boundary

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
SOURCE = ROOT / "source"
ROLLOUT = ROOT / "rollout"
KEY_ENV = ("EXPERIENTIAL_API_KEY", "EXPLABS_API_KEY", "EXPLABS_KEY_1")
TRANSPORT_ENV = ("JEV_TRANSPORT", "JEV_GATEWAY_ENDPOINT", "JEV_GATEWAY_TOKEN")
sys.path[:0] = [str(CANDIDATE), str(SOURCE)]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _build_stage():
    """Assemble the reviewed native stage in a disposable directory."""
    temp = tempfile.TemporaryDirectory(prefix="jev-advisory-")
    built = Path(temp.name) / "built"
    result = subprocess.run(
        [sys.executable, str(ROLLOUT / "build_review_stage.py"), "--output", str(built)],
        text=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        temp.cleanup()
        raise AssertionError(result.stdout + result.stderr)
    return temp, built / "native-code-stage" / "ext"


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
        cls.temp, cls.ext = _build_stage()
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

        malformed_calls = []

        def malformed(body, key, timeout):
            malformed_calls.append(key)
            return None

        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self.jev.evaluate("task", {"task_class": "x", "work_packet": "y"},
                              api_key="offline-fixture-key", transport=malformed)
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")
        self.assertEqual(len(malformed_calls), 1, "a malformed advisory must not be retried")

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
        env = {key: value for key, value in os.environ.items()
               if key not in KEY_ENV and key not in TRANSPORT_ENV}
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


class _FixtureResponse:
    """A bounded reply body for the injected opener; it never opens a socket."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, size: int) -> bytes:
        return self.payload[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _RecordingOpener:
    """Replace only the urllib opener and record the exact wire request."""

    def __init__(self, payload: bytes | None = None, failure: BaseException | None = None):
        self.requests: list[dict] = []
        self.payload = payload if payload is not None else json.dumps(
            {"answers": _task_answers(), "model": "jev-latest",
             "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()
        self.failure = failure

    def open(self, http_request, timeout=None):
        self.requests.append({
            "url": http_request.full_url,
            "method": http_request.get_method(),
            "headers": {key.lower(): value for key, value in http_request.headers.items()},
            "body": http_request.data,
            "timeout": timeout,
        })
        if self.failure is not None:
            raise self.failure
        return _FixtureResponse(self.payload)


class SharedGatewayTransport(OfflineBoundary):
    """The optional shared-gateway client binding is opt-in and fails closed.

    Every case injects the urllib opener, so no socket is opened, no vendor
    request is made and no credential is read from disk. The real endpoint,
    headers, redirect refusal and error mapping stay under qualification.
    """

    ENDPOINT = "http://127.0.0.1:8731/v1/systemone"
    TOKEN = "offline-fixture-scoped-proxy-token"

    @classmethod
    def setUpClass(cls):
        cls.temp, cls.ext = _build_stage()
        cls.task = cls.ext / "fabric_task.py"
        cls.jev = _load("staged_jev_advisory", cls.ext / "jev_advisory.py")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @contextmanager
    def _owner_env(self, **overrides):
        """Install exactly the owner-selected transport environment."""
        env = {"JEV_TRANSPORT": "shared_gateway",
               "JEV_GATEWAY_ENDPOINT": self.ENDPOINT,
               "JEV_GATEWAY_TOKEN": self.TOKEN}
        env.update(overrides)
        removed = {name: os.environ.pop(name) for name in TRANSPORT_ENV if name in os.environ}
        os.environ.update(env)
        try:
            yield
        finally:
            for name in TRANSPORT_ENV:
                os.environ.pop(name, None)
            os.environ.update(removed)

    def _advice(self, opener, **overrides):
        with self._owner_env(**overrides):
            return self.jev.evaluate("task", {"task_class": "domain_orchestration",
                                               "work_packet": "bounded packet"},
                                      timeout_s=2.0, opener=opener)

    def test_the_shared_gateway_posts_once_to_the_exact_loopback_route(self):
        opener = _RecordingOpener()
        advice = self._advice(opener)
        self.assertEqual(len(opener.requests), 1, "the advisory must post exactly once")
        sent = opener.requests[0]
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["url"], self.ENDPOINT)
        self.assertEqual(sent["headers"]["authorization"], "Bearer " + self.TOKEN)
        self.assertEqual(sent["headers"]["content-type"], "application/json")
        body = json.loads(sent["body"])
        self.assertEqual(body["model"], "jev-latest",
                         "the shared gateway must never rewrite the provider slug")
        self.assertGreater(sent["timeout"], 0)
        self.assertLessEqual(sent["timeout"], 15)
        self.assertEqual(advice["authority"], "ADVISORY_ONLY")
        self.assertEqual(advice["values"]["complexity"], "C2_COMPLEX_BOUNDED")

    def test_a_refused_gateway_call_is_sanitized_and_never_replayed(self):
        for code in (402, 403, 429):
            opener = _RecordingOpener(failure=error.HTTPError(
                url=self.ENDPOINT, code=code, msg="offline fixture refusal", hdrs={}, fp=None))
            with self.assertRaises(self.jev.JevUnavailable) as caught:
                self._advice(opener)
            self.assertEqual(caught.exception.code, "HTTP_" + str(code))
            self.assertEqual(len(opener.requests), 1,
                             "a refused advisory must not be replayed against the gateway")
            self.assertNotIn(self.TOKEN, str(caught.exception))
            self.assertNotIn(self.TOKEN, repr(caught.exception))

    def test_a_gateway_redirect_is_refused_and_never_followed(self):
        opener = _RecordingOpener(failure=error.HTTPError(
            url=self.ENDPOINT, code=302, msg="offline fixture redirect", hdrs={}, fp=None))
        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self._advice(opener)
        self.assertEqual(caught.exception.code, "HTTP_302")
        self.assertEqual(len(opener.requests), 1,
                         "a redirected advisory must not be sent to the redirect target")

    def test_a_gateway_timeout_is_sanitized_and_never_replayed(self):
        opener = _RecordingOpener(failure=TimeoutError("offline fixture timeout"))
        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self._advice(opener)
        self.assertEqual(caught.exception.code, "TRANSPORT")
        self.assertEqual(len(opener.requests), 1,
                         "a timed out advisory must not be replayed against the gateway")
        self.assertNotIn(self.TOKEN, str(caught.exception))

    def test_an_unusable_shared_gateway_never_reaches_the_vendor(self):
        cases = (
            ("GATEWAY_NOT_CONFIGURED", {"JEV_GATEWAY_ENDPOINT": "", "JEV_GATEWAY_TOKEN": ""}),
            ("GATEWAY_NOT_CONFIGURED", {"JEV_GATEWAY_TOKEN": ""}),
            ("GATEWAY_NOT_CONFIGURED", {"JEV_GATEWAY_ENDPOINT": ""}),
            ("GATEWAY_TOKEN_INVALID", {"JEV_GATEWAY_TOKEN": "too-short"}),
            ("GATEWAY_TOKEN_INVALID", {"JEV_GATEWAY_TOKEN": "offline-token-with\nnewline"}),
            ("GATEWAY_TOKEN_INVALID", {"JEV_GATEWAY_TOKEN": "offline-token-with\rreturn"}),
        )
        for code, overrides in cases:
            opener = _RecordingOpener()
            with self.assertRaises(self.jev.JevUnavailable) as caught:
                self._advice(opener, **overrides)
            self.assertEqual(caught.exception.code, code, overrides)
            self.assertEqual(opener.requests, [],
                             "an unusable shared gateway must not send anything at all")

    def test_the_shared_gateway_never_borrows_the_direct_vendor_key(self):
        opener = _RecordingOpener()
        with mock.patch.dict(os.environ, {"EXPERIENTIAL_API_KEY": "offline-vendor-key"}):
            advice = self._advice(opener)
        self.assertEqual(len(opener.requests), 1)
        sent = opener.requests[0]
        self.assertEqual(sent["headers"]["authorization"], "Bearer " + self.TOKEN)
        self.assertNotIn("offline-vendor-key", sent["headers"]["authorization"])
        self.assertNotIn("offline-vendor-key", sent["body"].decode("utf-8"))
        self.assertEqual(advice["authority"], "ADVISORY_ONLY")

    def test_a_refused_shared_gateway_does_not_fall_back_to_the_vendor(self):
        opener = _RecordingOpener()
        with mock.patch.dict(os.environ, {"EXPERIENTIAL_API_KEY": "offline-vendor-key"}):
            with self.assertRaises(self.jev.JevUnavailable) as caught:
                self._advice(opener, JEV_GATEWAY_ENDPOINT="https://api.experientiallabs.ai/v1/systemone")
        self.assertEqual(caught.exception.code, "GATEWAY_ENDPOINT_INVALID")
        self.assertEqual(opener.requests, [],
                         "a refused endpoint must not fall back to the direct vendor key")

    def test_an_endpoint_outside_loopback_is_refused_before_sending(self):
        refused = (
            "https://api.experientiallabs.ai/v1/systemone",
            "http://10.0.0.5:8731/v1/systemone",
            "http://0.0.0.0:8731/v1/systemone",
            "http://169.254.169.254:8731/v1/systemone",
            "http://example.invalid:8731/v1/systemone",
            "http://127.0.0.1.nip.io:8731/v1/systemone",
            "http://127.0.0.1:8731/v1/chat/completions",
            "http://127.0.0.1:8731/v1/systemone/extra",
            "http://127.0.0.1:8731/v1/systemone?key=value",
            "http://127.0.0.1:8731/v1/systemone#fragment",
            "http://user:pass@127.0.0.1:8731/v1/systemone",
            "http://127.0.0.1:8731",
            "http://127.0.0.1/v1/systemone",
            "http://127.0.0.1:80/v1/systemone",
            "ftp://127.0.0.1:8731/v1/systemone",
            "file:///etc/passwd",
        )
        for endpoint in refused:
            opener = _RecordingOpener()
            with self.assertRaises(self.jev.JevUnavailable) as caught:
                self._advice(opener, JEV_GATEWAY_ENDPOINT=endpoint)
            self.assertEqual(caught.exception.code, "GATEWAY_ENDPOINT_INVALID", endpoint)
            self.assertEqual(opener.requests, [], endpoint)

    def test_the_loopback_gateway_endpoint_is_accepted_in_its_exact_shape(self):
        for endpoint, expected in (
            ("http://127.0.0.1:8731/v1/systemone", "http://127.0.0.1:8731/v1/systemone"),
            ("http://localhost:8731/v1/systemone", "http://127.0.0.1:8731/v1/systemone"),
            ("http://127.0.0.2:8731/v1/systemone", "http://127.0.0.2:8731/v1/systemone"),
            ("http://[::1]:8731/v1/systemone", "http://[::1]:8731/v1/systemone"),
            ("https://127.0.0.1:8731/v1/systemone", "https://127.0.0.1:8731/v1/systemone"),
        ):
            self.assertEqual(self.jev.gateway_endpoint(endpoint), expected)

    def test_the_shared_gateway_is_off_by_default(self):
        opener = _RecordingOpener()
        removed = {name: os.environ.pop(name) for name in TRANSPORT_ENV if name in os.environ}
        try:
            advice = self.jev.evaluate("task", {"task_class": "domain_orchestration",
                                                "work_packet": "bounded packet"},
                                       api_key="offline-fixture-key", timeout_s=2.0,
                                       opener=opener)
        finally:
            os.environ.update(removed)
        self.assertEqual(len(opener.requests), 1)
        sent = opener.requests[0]
        self.assertEqual(sent["url"], "https://api.experientiallabs.ai/v1/systemone",
                         "an unselected transport must stay on the incumbent direct endpoint")
        self.assertEqual(sent["headers"]["authorization"], "Bearer offline-fixture-key")
        self.assertEqual(advice["authority"], "ADVISORY_ONLY")

    def test_an_unknown_transport_name_is_refused_instead_of_defaulting(self):
        opener = _RecordingOpener()
        with self.assertRaises(self.jev.JevUnavailable) as caught:
            self._advice(opener, JEV_TRANSPORT="gateway")
        self.assertEqual(caught.exception.code, "TRANSPORT_INVALID")
        self.assertEqual(opener.requests, [],
                         "an unknown transport name must not silently use the direct vendor")

    def test_an_explicit_complexity_survives_a_shared_gateway_advisory(self):
        opener = _RecordingOpener()
        with self._owner_env():
            advice = self.jev.evaluate("task", {"task_class": "domain_orchestration",
                                                "work_packet": "bounded packet"},
                                       timeout_s=2.0, opener=opener)
        self.assertEqual(self.jev.select_complexity(advice, "C0_MECHANICAL"), "C0_MECHANICAL")
        self.assertEqual(self.jev.select_complexity(advice, "C1_ROUTINE_BOUNDED"),
                         "C1_ROUTINE_BOUNDED")

    def test_the_cli_reports_one_bounded_shared_gateway_refusal(self):
        code = ('import runpy, sys\n'
                'sys.argv = ' + repr([str(self.task), "jev-advice", "--kind", "task", "--stdin"]) + '\n'
                'sys.path.insert(0, ' + repr(str(self.ext)) + ')\n'
                'runpy.run_path(' + repr(str(self.task)) + ', run_name="__main__")\n')
        argv = [sys.executable, "-c", boundary.guarded_python_child(code)]
        env = {key: value for key, value in os.environ.items()
               if key not in KEY_ENV and key not in TRANSPORT_ENV}
        env["JEV_TRANSPORT"] = "shared_gateway"
        result = subprocess.run(argv, input="bounded packet", env=env,
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 78, result.stdout + result.stderr)
        self.assertIn("JEV_UNAVAILABLE=GATEWAY_NOT_CONFIGURED", result.stderr)
        self.assertEqual(result.stderr.count("JEV_UNAVAILABLE="), 1,
                         "the native boundary must emit exactly one advisory trace")
        self.assertEqual(result.stdout, "", "an advisory miss must not emit a result payload")

    def test_the_shared_gateway_binding_is_shipped_by_the_reviewed_closure(self):
        staged = (self.ext / "jev_advisory.py").read_text()
        self.assertIn('"JEV_TRANSPORT"', staged)
        self.assertIn('"JEV_GATEWAY_ENDPOINT"', staged)
        self.assertIn('"JEV_GATEWAY_TOKEN"', staged)
        source = (CANDIDATE / "jev_advisory.py").read_text()
        self.assertIn("SHARED_GATEWAY_TRANSPORT", source)
        self.assertIn("GATEWAY_ENDPOINT_INVALID", source)
        self.assertIn("GATEWAY_NOT_CONFIGURED", source)
        self.assertIn("GATEWAY_TOKEN_INVALID", source)
        self.assertIn("TRANSPORT_INVALID", source)
