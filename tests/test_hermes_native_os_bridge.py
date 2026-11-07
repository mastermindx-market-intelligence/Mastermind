"""No network, model, credentials, service starts or real admissions."""
import asyncio
import importlib.util
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

PATH = Path(__file__).parents[1] / "app/mastermind_os/src-tauri/src/hermes_native/bridge.py"


def load():
    if not PATH.exists():
        return None
    spec = importlib.util.spec_from_file_location("thin_native_bridge", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identity():
    return {"ok": True, "protocol": 1, "result": {
        "kind": "hermes-gateway", "runtime_protocol": 1, "state": "ready",
        "hermes_home": "/fixture/hermes", "instance_id": "abc123",
        "authority_epoch": 2, "api_origin": "http://127.0.0.1:45678",
        "code_sha": "a" * 40, "code_version": "0.23.0",
        "capabilities": ["session-authority-v1", "durable-admission-v1", "event-replay-v1"],
    }}


def snapshot(sid="session-1"):
    return {"session_id": sid, "stored_session_id": sid, "messages": [
        {"role": "system", "content": "private prompt"},
        {"role": "user", "content": "Original\n  文本\t"},
        {"role": "assistant", "content": "A useful answer"},
        {"role": "tool", "content": "private tool trace"}],
        "message_count": 4, "running": False, "authority_epoch": 2,
        "execution_generation": 3, "pending": [], "prompts": [],
        "info": {"title": "Office", "source": "tool", "model": "configured-not-served", "credential_hint": "NEVER_EMIT",
                 "enabled_toolsets": [], "tool_count": 0,
                 "launch_request": {"toolsets": [], "safe_mode": False, "accept_hooks": False, "follow_profile_config": False}}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.assertIsNotNone(self.b, "The thin native OS adapter has not been implemented")

    def test_request_preserves_original_text_and_native_request_identity(self):
        text = "Original\n  中文\t\r"
        op, params = self.b.normalize_request({"operation": "send", "sessionId": "session-1",
            "requestId": "a" * 32, "text": text})
        self.assertEqual(op, "send")
        self.assertEqual(params["text"], text)
        self.assertEqual(params["submission_id"], "a" * 32)
        self.assertEqual(params["input_id"], "a" * 32)
        self.assertNotIn("surface", params)
        self.assertNotEqual(params.get("unattended"), True)

    def test_no_caller_authority_or_generic_rpc(self):
        for key in ("url", "profile", "model", "api_key", "cwd", "subject", "method", "toolsets"):
            with self.subTest(key=key), self.assertRaises(self.b.BridgeRefusal):
                self.b.normalize_request({"operation": "status", key: "attacker"})
        for value in ({"operation": "shell"}, [], {"operation": "send", "sessionId": "../other",
                       "requestId": "a" * 32, "text": "x"}):
            with self.assertRaises(self.b.BridgeRefusal):
                self.b.normalize_request(value)

    def test_create_is_no_tools_no_hooks_and_role_is_only_title(self):
        _, params = self.b.normalize_request({"operation": "create", "role": "secretary", "requestId": "b" * 32})
        self.assertEqual(params["source"], "tool")
        self.assertFalse(params["follow_profile_config"])
        self.assertEqual(params["toolsets"], [])
        self.assertFalse(params["safe_mode"])
        self.assertFalse(params["accept_hooks"])
        self.assertNotIn("model", params)
        self.assertNotIn("subject", params)
        _, other = self.b.normalize_request({"operation": "create", "role": "secretary", "requestId": "c" * 32})
        self.assertNotEqual(params["title"], other["title"])

    def test_text_and_request_id_bounds(self):
        good = {"operation": "send", "sessionId": "s1", "requestId": "f" * 32, "text": "x"}
        for change in ({"text": " "}, {"text": "a" * 32769}, {"text": "🦀" * 8193},
                       {"text": "x\x00y"}, {"requestId": "not-a-request"}, {"text": None}):
            with self.assertRaises(self.b.BridgeRefusal):
                self.b.normalize_request({**good, **change})

    def test_identity_accepts_protocol_not_a_hardcoded_port(self):
        endpoint, public = self.b.qualify_identity(identity(), Path("/fixture/hermes"))
        self.assertEqual(endpoint.api_origin, "http://127.0.0.1:45678")
        self.assertEqual(public["protocol"], 1)
        self.assertNotIn("api_origin", public)
        self.assertNotIn("profile_id", public)

    def test_remote_credential_origin_and_wrong_owner_are_refused(self):
        for origin in ("http://example.org:123", "http://127.0.0.1:123/x", "http://u:p@127.0.0.1:123",
                       "http://127.0.0.1:123?token=secret", "https://127.0.0.1:123", "http://127.0.0.1:123#x"):
            data = identity(); data["result"]["api_origin"] = origin
            with self.assertRaises(self.b.BridgeRefusal):
                self.b.qualify_identity(data, Path("/fixture/hermes"))
        for key, value in (("hermes_home", "/other"), ("runtime_protocol", 2), ("state", "draining"),
                           ("authority_epoch", True), ("capabilities", ["session-authority-v1"])):
            data = identity(); data["result"][key] = value
            with self.assertRaises(self.b.BridgeRefusal):
                self.b.qualify_identity(data, Path("/fixture/hermes"))

    def test_snapshot_excludes_system_tools_credentials_and_preserves_text(self):
        result = self.b.project_result("read", snapshot(), "session-1")
        self.assertEqual(result["session"]["messages"], [
            {"role": "user", "text": "Original\n  文本\t"},
            {"role": "assistant", "text": "A useful answer"}])
        self.assertEqual(result["session"]["requestedModel"], "configured-not-served")
        self.assertNotIn("NEVER_EMIT", str(result))
        self.assertNotIn("private prompt", str(result))
        self.assertNotIn("private tool", str(result))
        with self.assertRaises(self.b.BridgeRefusal):
            self.b.project_result("read", snapshot("wrong-session"), "session-1")

    def test_receipt_must_belong_to_original_session(self):
        receipt = {"admission_id": "admit-1", "ref": {"session_id": "session-1"}, "status": "queued",
                   "sequence": 1, "outcome": None, "authority_epoch": 2, "execution_generation": None}
        result = self.b.project_result("send", receipt, "session-1")
        self.assertEqual(result["receipt"]["status"], "queued")
        self.assertNotIn("accepted", result)
        with self.assertRaises(self.b.BridgeRefusal):
            self.b.project_result("send", receipt, "other")

    def test_projection_caps_history_explicitly(self):
        data = snapshot(); data["messages"] = [{"role": "assistant", "content": str(i)} for i in range(150)]
        view = self.b.project_result("read", data, "session-1")["session"]
        self.assertEqual(len(view["messages"]), 100)
        self.assertTrue(view["historyTruncated"])

    def test_status_does_not_connect_or_start_any_runtime(self):
        runtime = FakeRuntime()
        result = asyncio.run(self.b.execute_request({"operation": "status"}, runtime))
        self.assertEqual(result["state"], "READY")
        self.assertEqual(runtime.calls, [])
        self.assertEqual(result["delegation"], "NOT_ENABLED")

    def test_send_is_one_native_call_never_a_retry(self):
        runtime = FakeRuntime(error=TimeoutError("private bearer secret"))
        req = {"operation": "send", "sessionId": "session-1", "requestId": "c" * 32, "text": "original"}
        result = asyncio.run(self.b.execute_request(req, runtime))
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual([call[0] for call in runtime.calls], ["session.resume", "prompt.submit"])
        self.assertNotIn("secret", str(result))
        self.assertFalse(result["retryAllowed"])

    def test_received_owner_refusal_is_not_unknown_or_failover(self):
        runtime = FakeRuntime(error=self.b.OwnerRefusal("permission_denied", code=4001))
        req = {"operation": "create", "role": "meta-ceo", "requestId": "c" * 32}
        result = asyncio.run(self.b.execute_request(req, runtime))
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(len(runtime.calls), 1)
        self.assertFalse(result["retryAllowed"])

    def test_existing_tool_enabled_session_cannot_be_used_for_thin_send(self):
        runtime = FakeRuntime()
        async def tool_session(method, **params):
            runtime.calls.append((method, params))
            data = snapshot(); data["info"]["enabled_toolsets"] = ["terminal"]
            return data
        runtime.rpc = tool_session
        req = {"operation": "send", "sessionId": "session-1", "requestId": "c" * 32, "text": "original"}
        result = asyncio.run(self.b.execute_request(req, runtime))
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(result["code"], "NATIVE_SESSION_POLICY_UNQUALIFIED")
        self.assertEqual([call[0] for call in runtime.calls], ["session.resume"])

    def test_duplicate_json_keys_and_nonfinite_values_are_refused(self):
        for raw in ('{"operation":"status","operation":"send"}', '{"x":NaN}'):
            with self.assertRaises(self.b.BridgeRefusal):
                self.b.closed_json(raw)

    def test_readonly_capacity_requires_exact_effective_tool_scope_and_binding_proof(self):
        data = snapshot(); data["info"]["enabled_toolsets"] = ["mastermind-fabric-capacity"]
        data["info"]["tool_count"] = 3
        data["info"]["tools"] = {"other": ["tool_search", "tool_describe", "tool_call"]}
        self.assertFalse(self.b.project_result("read", data, "session-1")["session"]["canSend"])
        view = self.b.project_result("read", data, "session-1", readonly_capacity=True)["session"]
        self.assertTrue(view["canSend"])
        self.assertEqual(view["toolAccess"], "CAPACITY_READ_ONLY")
        data["info"]["enabled_toolsets"].append("terminal")
        self.assertFalse(self.b.project_result("read", data, "session-1", readonly_capacity=True)["session"]["canSend"])

    def test_omh_advice_is_a_distinct_exact_scope_not_an_ignored_extra_tool(self):
        data = snapshot()
        data["info"].update(enabled_toolsets=["mastermind-fabric-capacity", "mmx_omh"],
            tool_count=3, tools={"other": ["tool_search", "tool_describe", "tool_call"]})
        for capacity, omh in [(False, False), (True, False), (False, True)]:
            self.assertFalse(self.b.project_result("read", data, "session-1",
                readonly_capacity=capacity, readonly_omh=omh)["session"]["canSend"])
        qualified = self.b.project_result("read", data, "session-1",
            readonly_capacity=True, readonly_omh=True)["session"]
        self.assertTrue(qualified["canSend"])
        self.assertEqual(qualified["toolAccess"], "ADVISORY_READ_ONLY")
        for change in [{"enabled_toolsets": ["mastermind-fabric-capacity", "mmx_omh", "unknown"]},
                       {"enabled_toolsets": ["mmx_omh"]}, {"tool_count": 4},
                       {"tools": {"other": ["tool_search", "tool_describe", "terminal"]}},
                       {"launch_request": {**data["info"]["launch_request"], "accept_hooks": True}}]:
            with self.subTest(change=change):
                value = {**data, "info": {**data["info"], **change}}
                self.assertFalse(self.b.project_result("read", value, "session-1",
                    readonly_capacity=True, readonly_omh=True)["session"]["canSend"])

    def test_qualified_omh_preflight_allows_only_one_original_submit(self):
        for qualified in [False, True]:
            runtime = FakeRuntime()
            runtime.readonly_capacity_qualified = lambda: True
            runtime.readonly_omh_qualified = lambda: qualified
            original = runtime.rpc
            async def rpc(method, **params):
                result = await original(method, **params)
                if method == "session.resume":
                    result["info"].update(enabled_toolsets=["mastermind-fabric-capacity", "mmx_omh"],
                        tool_count=3, tools={"other": ["tool_search", "tool_describe", "tool_call"]})
                return result
            runtime.rpc = rpc
            result = asyncio.run(self.b.execute_request({"operation": "send", "sessionId": "session-1",
                "requestId": "c" * 32, "text": "original"}, runtime))
            self.assertEqual(result["state"], "ADMITTED" if qualified else "REFUSED")
            self.assertEqual(sum(method == "prompt.submit" for method, _ in runtime.calls), int(qualified))
            self.assertFalse(result["retryAllowed"])

    def test_invalid_request_never_reaches_runtime(self):
        runtime = FakeRuntime()
        result = asyncio.run(self.b.execute_request({"operation": "status", "token": "bad"}, runtime))
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(runtime.identifies, 0)


class OmhSourceQualificationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.b = load()
        self.directory = tempfile.TemporaryDirectory(prefix="native-omh-source-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name).resolve() / "user/.hermes"
        self.runtime = object.__new__(self.b.NativeRuntime)
        self.runtime.home = self.home
        self.runtime.observed_code = "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"
        self.paths = self.fixture()

    def fixture(self):
        import hashlib
        import json
        pins = dict(self.b.OMH_READONLY_PINS)
        def write(path, raw):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return hashlib.sha256(raw).hexdigest()
        plugin = self.home / "plugins/mastermind-omh"
        source = plugin / "_source" / pins["release"]
        # Executing any fixture package would fail. Qualification only reads it.
        inert = b"raise AssertionError('qualification must not import installed code')\n"
        paths = {}
        for name in ("plugin.yaml", "__init__.py"):
            paths[name] = plugin / name
            pins[name] = write(paths[name], inert)
        venv = self.home.parent / ".local/share/omh/venv"
        paths["python"] = venv / "bin/python"
        pins["python"] = write(paths["python"], b"fixture interpreter bytes")
        paths["pyvenv.cfg"] = venv / "pyvenv.cfg"
        pins["pyvenv.cfg"] = write(paths["pyvenv.cfg"], b"include-system-site-packages = false\n")
        paths["model_tools"] = self.home / "hermes-agent/model_tools.py"
        pins["model_tools"] = write(paths["model_tools"], inert)
        stdlib = venv / "lib/python3.14"
        paths["stdlib_sitecustomize"] = stdlib / "sitecustomize.py"
        pins["stdlib_sitecustomize"] = write(paths["stdlib_sitecustomize"], inert)
        site = stdlib / "site-packages"
        paths["metadata"] = site / "oh_my_hermes-4.0.6.dist-info/METADATA"
        pins["metadata"] = write(paths["metadata"], b"Name: oh-my-hermes\nVersion: 4.0.6\n")
        sources = {}
        for index in range(19):
            name = f"module{index}.py"
            sources[name] = write(source / name, inert)
        paths["adapter"] = source / "module0.py"
        package = site / "omh"
        for name in ("__init__.py", "helper.py"):
            write(package / name, inert)
        paths["dependency"] = package / "helper.py"
        digest = hashlib.sha256()
        for path in sorted(package.rglob("*.py")):
            digest.update(path.relative_to(package).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
        pins.update(dependency=digest.hexdigest(), dependency_files=2)
        descriptor = {
            "schema": "mastermind.hermes_omh.local_runtime/v1", "release_commit": pins["release"],
            "source_root": str(source), "profile_home": str(self.home),
            "omh_home": str(self.home.parent / ".omh"), "python_executable": str(paths["python"]),
            "source_files": sources,
        }
        paths["descriptor"] = plugin / "_runtime.json"
        pins["descriptor"] = write(paths["descriptor"], json.dumps(descriptor).encode())
        self.b.OMH_READONLY_PINS = pins
        return paths

    def test_exact_installed_source_is_recognized_without_loading_it(self):
        self.assertTrue(self.runtime.readonly_omh_qualified())
        self.runtime.observed_code = "f" * 40
        self.assertFalse(self.runtime.readonly_omh_qualified())

    def test_changed_descriptor_plugin_dependency_or_interpreter_removes_eligibility(self):
        for name, path in self.paths.items():
            with self.subTest(name=name):
                original = path.read_bytes()
                path.write_bytes(original + b"\n# changed")
                self.assertFalse(self.runtime.readonly_omh_qualified())
                path.write_bytes(original)
        self.assertTrue(self.runtime.readonly_omh_qualified())

    def test_startup_hooks_and_extension_shadows_are_refused_without_import(self):
        site = self.paths["metadata"].parent.parent
        for path in (site / "injected.pth", site / "sitecustomize.py",
                     self.paths["dependency"].with_suffix(".so"),
                     self.paths["adapter"].with_suffix(".so")):
            with self.subTest(path=path.name):
                path.write_text("raise AssertionError('must never execute')\n")
                self.assertFalse(self.runtime.readonly_omh_qualified())
                path.unlink()
        self.assertTrue(self.runtime.readonly_omh_qualified())

    def test_extra_dependency_source_and_symlink_or_writable_source_are_refused(self):
        extra = self.paths["dependency"].with_name("injected.py")
        extra.write_text("pass\n")
        self.assertFalse(self.runtime.readonly_omh_qualified())
        extra.unlink()
        source = self.paths["adapter"]
        original = source.read_bytes()
        target = source.with_name("outside.py")
        target.write_bytes(original)
        source.unlink()
        source.symlink_to(target)
        self.assertFalse(self.runtime.readonly_omh_qualified())
        source.unlink()
        target.unlink()
        source.write_bytes(original)
        source.chmod(0o666)
        self.assertFalse(self.runtime.readonly_omh_qualified())
        source.chmod(0o600)
        self.assertTrue(self.runtime.readonly_omh_qualified())


class OriginalSettlementTests(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.send = {"operation": "send", "sessionId": "session-1", "requestId": "a" * 32, "text": "original"}
        self.create = {"operation": "create", "role": "secretary", "requestId": "b" * 32}

    def test_direct_success_qualifies_original_native_identity_before_settlement(self):
        for request, lookup in [(self.create, ("create_identity", {"request_id": "b" * 32})),
                                (self.send, ("recover_send", {"session_id": "session-1", "request_id": "a" * 32}))]:
            runtime = FakeRuntime()
            result = asyncio.run(self.b.execute_request(request, runtime))
            self.assertEqual(result["state"], "OPENED" if request["operation"] == "create" else "ADMITTED")
            self.assertEqual(result["requestId"], request["requestId"])
            self.assertEqual(result.get("requestSessionId"), request.get("sessionId"))
            self.assertEqual(runtime.lookups, [lookup])
            self.assertEqual(sum(method in {"prompt.submit", "session.create"} for method, _ in runtime.calls), 1)

    def test_crossed_create_or_direct_send_result_remains_unknown(self):
        for request in [self.create, self.send]:
            runtime = FakeRuntime(); original_rpc = runtime.rpc
            async def crossed(method, **params):
                value = await original_rpc(method, **params)
                if method == "session.create":
                    value["session_id"] = value["stored_session_id"] = "different-create"
                if method == "prompt.submit":
                    value["admission_id"] = "different-admission"
                return value
            runtime.rpc = crossed
            result = asyncio.run(self.b.execute_request(request, runtime))
            self.assertEqual(result["state"], "EFFECT_UNKNOWN")
            self.assertEqual(result["requestId"], request["requestId"])
            self.assertNotIn("session", result); self.assertNotIn("receipt", result)

    def test_storage_internal_and_unknown_owner_errors_after_submit_never_claim_no_effect(self):
        for reason, code in [("storage_unavailable", 5001), ("request_failed", None),
                             ("permission_denied", 5001), ("admission_conflict", 4001),
                             ("future_reason", 4001), ("storage_unavailable", 4001)]:
            runtime = FakeRuntime(error=self.b.OwnerRefusal(reason, code=code))
            result = asyncio.run(self.b.execute_request(self.send, runtime))
            self.assertEqual(result["state"], "EFFECT_UNKNOWN", (reason, code))
            self.assertEqual(result["requestId"], self.send["requestId"])
            self.assertEqual([method for method, _ in runtime.calls], ["session.resume", "prompt.submit"])
            self.assertFalse(result["retryAllowed"])

    def test_lookup_failure_after_submit_holds_but_changed_source_blocks_before_send(self):
        runtime = FakeRuntime()
        def missing(operation, params):
            raise self.b.BridgeRefusal("NATIVE_RECOVERY_UNRESOLVED")
        runtime.resolve_original = missing
        result = asyncio.run(self.b.execute_request(self.send, runtime))
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual([method for method, _ in runtime.calls], ["session.resume", "prompt.submit"])
        runtime = FakeRuntime()
        def changed():
            raise self.b.BridgeRefusal("NATIVE_RECOVERY_SOURCE_CHANGED")
        runtime.require_recovery_source = changed
        result = asyncio.run(self.b.execute_request(self.send, runtime))
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(result["requestId"], self.send["requestId"])
        self.assertEqual(runtime.calls, [])


class PreDispatchFailureTests(unittest.TestCase):
    def setUp(self):
        self.b = load()

    def test_identify_connect_and_history_timeouts_are_not_sent_without_a_modifying_rpc(self):
        for operation in ("create", "send"):
            for stage in ("identify", "connect", "history"):
                if operation == "create" and stage == "history":
                    continue
                with self.subTest(operation=operation, stage=stage):
                    runtime = FakeRuntime()
                    async def fail_identify():
                        raise TimeoutError("private diagnostic")
                    @asynccontextmanager
                    async def fail_connect(endpoint):
                        raise ConnectionError("private diagnostic")
                        yield
                    async def fail_history(method, **params):
                        runtime.calls.append((method, params))
                        raise TimeoutError("private diagnostic")
                    if stage == "identify":
                        runtime.identify = fail_identify
                    elif stage == "connect":
                        runtime.connect = fail_connect
                    else:
                        runtime.rpc = fail_history
                    request = {"operation": operation, "requestId": "c" * 32}
                    request.update({"role": "secretary"} if operation == "create" else {"sessionId": "session-1", "text": "original"})
                    result = asyncio.run(self.b.execute_request(request, runtime))
                    self.assertEqual(result["state"], "NOT_SENT")
                    self.assertEqual(result["operation"], operation)
                    self.assertEqual(result["requestId"], request["requestId"])
                    self.assertEqual(result.get("requestSessionId"), request.get("sessionId"))
                    self.assertEqual(runtime.calls, [("session.resume", {"session_id": "session-1", "omit_messages": True})] if stage == "history" else [])
                    self.assertFalse(result["retryAllowed"])
                    self.assertNotIn("private", str(result))

    def test_runtime_initialization_failure_cannot_create_an_uncertain_new_request(self):
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        for request in ({"operation": "create", "role": "secretary", "requestId": "c" * 32},
                        {"operation": "send", "sessionId": "session-1", "requestId": "c" * 32, "text": "original"},
                        {"operation": "recover_send", "sessionId": "session-1", "requestId": "c" * 32}):
            output = io.BytesIO()
            with patch("sys.stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode()))), \
                 patch("sys.stdout", SimpleNamespace(buffer=output)), \
                 patch.object(self.b, "NativeRuntime", side_effect=RuntimeError("private dependency diagnostic")), \
                 patch.object(self.b, "execute_request") as execute:
                self.b.main()
            result = json.loads(output.getvalue())
            recovering = request["operation"].startswith("recover_")
            self.assertEqual(result["state"], "EFFECT_UNKNOWN" if recovering else "NOT_SENT")
            self.assertEqual(result["operation"], "recover" if recovering else request["operation"])
            self.assertEqual(result["requestId"], request["requestId"])
            self.assertEqual(result.get("requestSessionId"), request.get("sessionId"))
            self.assertFalse(result["retryAllowed"])
            self.assertNotIn("private", str(result))
            execute.assert_not_called()


class FakeRuntime:
    home = Path("/fixture/hermes")

    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.identifies = 0
        self.lookups = []
        self.reads = []

    def create_identity(self, request_id):
        self.lookups.append(("create_identity", {"request_id": request_id}))
        return {"session_id": "session-1"}

    def read_history(self, session_id, *, expected_request_id=None):
        self.reads.append((session_id, expected_request_id))
        result = load().project_result("read", getattr(self, "snapshot", snapshot()), session_id)
        result["session"].update(canSend=False, toolAccess="UNQUALIFIED", sendCheckRequired=True,
                                 running=None, promptsPending=None)
        return result

    def require_recovery_source(self):
        pass

    def resolve_original(self, operation, params):
        self.lookups.append((operation, params))
        return {"session_id": "session-1", "admission_id": "original-admission"}

    async def identify(self):
        self.identifies += 1
        return identity()

    @asynccontextmanager
    async def connect(self, endpoint):
        yield self

    async def rpc(self, method, **params):
        self.calls.append((method, params))
        if self.error and method != "session.resume":
            raise self.error
        if method == "prompt.submit":
            return {"admission_id": "original-admission", "ref": {"session_id": "session-1"},
                    "status": "terminal", "sequence": 1, "outcome": "completed", "execution_generation": 1}
        return snapshot()



class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.b = load()

    def test_recovery_accepts_only_original_identifiers_without_payload_or_authority(self):
        for operation in ("recover_create", "recover_send"):
            request = {"operation": operation, "requestId": "a" * 32}
            if operation == "recover_send":
                request["sessionId"] = "session-1"
            op, params = self.b.normalize_request(request)
            self.assertEqual(op, operation)
            self.assertEqual(params["request_id"], "a" * 32)
            for key in ("text", "role", "principal", "profile", "subject", "admissionId"):
                with self.subTest(operation=operation, key=key), self.assertRaises(self.b.BridgeRefusal):
                    self.b.normalize_request({**request, key: "not accepted"})

    def test_stable_local_scope_survives_auth_and_native_process_reopening(self):
        original = identity()
        _, first = self.b.qualify_identity(original, Path("/fixture/hermes"))
        original["result"].update(instance_id="new-instance", authority_epoch=15)
        _, reopened = self.b.qualify_identity(original, Path("/fixture/hermes"))
        self.assertEqual(first["localScope"], reopened["localScope"])
        self.assertRegex(first["localScope"], r"^[a-f0-9]{64}$")
        original["result"]["hermes_home"] = "/fixture/another"
        _, other = self.b.qualify_identity(original, Path("/fixture/another"))
        self.assertNotEqual(first["localScope"], other["localScope"])

    def test_terminal_receipt_recovery_does_not_depend_on_conversation_history(self):
        runtime = RecoveryRuntime()
        result = asyncio.run(self.b.execute_request({"operation": "recover_send",
            "sessionId": "session-1", "requestId": "a" * 32}, runtime))
        self.assertEqual(result["state"], "ADMITTED")
        self.assertEqual(result["operation"], "recover")
        self.assertEqual(result["receipt"]["status"], "terminal")
        self.assertEqual(result["receipt"]["id"], "original-admission")
        self.assertNotIn("session", result)
        self.assertEqual(runtime.lookups, [("recover_send", {"session_id": "session-1", "request_id": "a" * 32})])
        self.assertEqual(runtime.calls, [
            ("prompt.receipt", {"session_id": "session-1", "admission_id": "original-admission"})])
        self.assertFalse(result["retryAllowed"])
        self.assertNotIn("private tool", str(result))

    def test_uncertain_create_reads_only_the_original_identity(self):
        runtime = RecoveryRuntime()
        result = asyncio.run(self.b.execute_request({"operation": "recover_create", "requestId": "b" * 32}, runtime))
        self.assertEqual(result["state"], "OPENED")
        self.assertEqual(result["session"]["id"], "session-1")
        self.assertEqual(runtime.lookups, [("recover_create", {"request_id": "b" * 32})])
        self.assertEqual(runtime.calls, [])
        self.assertEqual(runtime.reads, [("session-1", "b" * 32)])

    def test_absence_failure_or_changed_source_is_not_permission_to_retry(self):
        errors = [self.b.BridgeRefusal("NATIVE_RECOVERY_UNRESOLVED"),
                  self.b.BridgeRefusal("NATIVE_RECOVERY_SOURCE_CHANGED"), TimeoutError("private secret")]
        for error in errors:
            runtime = RecoveryRuntime(lookup_error=error)
            result = asyncio.run(self.b.execute_request({"operation": "recover_send",
                "sessionId": "session-1", "requestId": "a" * 32}, runtime))
            self.assertEqual(result["state"], "EFFECT_UNKNOWN")
            self.assertEqual(result["operation"], "recover")
            self.assertEqual(runtime.calls, [])
            self.assertFalse(result["retryAllowed"])
            self.assertNotIn("secret", str(result))
        for error in [self.b.OwnerRefusal("not_found"), self.b.NotSent("not connected"), TimeoutError()]:
            runtime = RecoveryRuntime(receipt_error=error)
            result = asyncio.run(self.b.execute_request({"operation": "recover_send",
                "sessionId": "session-1", "requestId": "a" * 32}, runtime))
            self.assertEqual(result["state"], "EFFECT_UNKNOWN")
            self.assertEqual([method for method, _ in runtime.calls], ["prompt.receipt"])
        runtime = RecoveryRuntime()
        def missing_original(session_id, **params):
            runtime.reads.append((session_id, params.get("expected_request_id")))
            raise self.b.OwnerRefusal("session_not_found")
        runtime.read_history = missing_original
        result = asyncio.run(self.b.execute_request({"operation": "recover_create", "requestId": "a" * 32}, runtime))
        self.assertEqual(result["state"], "EFFECT_UNKNOWN")
        self.assertEqual(runtime.calls, [])
        self.assertEqual(runtime.reads, [("session-1", "a" * 32)])

    def test_crossed_receipt_never_settles_the_original(self):
        for change in ({"admission_id": "other-admission"}, {"ref": {"session_id": "other-session"}}):
            runtime = RecoveryRuntime(receipt_change=change)
            result = asyncio.run(self.b.execute_request({"operation": "recover_send",
                "sessionId": "session-1", "requestId": "a" * 32}, runtime))
            self.assertEqual(result["state"], "EFFECT_UNKNOWN")
            self.assertNotIn("receipt", result)

    def test_native_lookup_uses_upstream_readonly_api_and_exact_uid_session_request(self):
        import os
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory(prefix="native-hermes-readonly-") as directory:
            runtime = object.__new__(self.b.NativeRuntime)
            runtime.home = Path(directory)
            runtime.require_recovery_source = Mock()
            path = runtime.home / "state.db"
            path.write_bytes(b"fixture owned by this test only")
            path.chmod(0o600)
            db = SimpleNamespace(close=Mock())
            session_db = Mock(return_value=db)
            principal = f"uid:{os.getuid()}"
            row = {"principal_id": principal, "target_session_id": "session-1",
                   "request_id": "a" * 32, "admission_id": "original-admission",
                   "private": "not projected"}
            find = Mock(return_value=row)
            with patch.dict("sys.modules", {"hermes_state": SimpleNamespace(SessionDB=session_db),
                                          "hermes_state_runtime": SimpleNamespace(find_session_admission=find)}):
                result = runtime.resolve_original("recover_send", {"session_id": "session-1", "request_id": "a" * 32})
                self.assertEqual(result, {"session_id": "session-1", "admission_id": "original-admission"})
                session_db.assert_called_once_with(path, read_only=True)
                find.assert_called_once_with(db, principal_id=principal, session_id="session-1", request_id="a" * 32)
                db.close.assert_called_once_with()
                for wrong in (None, {**row, "principal_id": "uid:other"}, {**row, "target_session_id": "other"},
                              {**row, "request_id": "b" * 32}):
                    find.return_value = wrong
                    with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_UNRESOLVED"):
                        runtime.resolve_original("recover_send", {"session_id": "session-1", "request_id": "a" * 32})
                path.chmod(0o622)
                session_db.reset_mock()
                with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_UNAVAILABLE"):
                    runtime.resolve_original("recover_send", {"session_id": "session-1", "request_id": "a" * 32})
                session_db.assert_not_called()

    def test_new_create_expected_identity_reuses_upstream_pure_identity(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        runtime = object.__new__(self.b.NativeRuntime)
        runtime.home = Path("/fixture/hermes")
        runtime.require_recovery_source = Mock()
        identity_fn = Mock(return_value="the-original-created-session")
        with patch.dict("sys.modules", {"hermes_state_keys": SimpleNamespace(local_identity=identity_fn)}):
            self.assertEqual(runtime.create_identity("b" * 32),
                             {"session_id": "the-original-created-session"})
        identity_fn.assert_called_once_with("/fixture/hermes", f"uid:{os.getuid()}", "b" * 32)

    def test_upgrade_or_tampered_lookup_source_is_held_before_import_or_database_access(self):
        import tempfile
        runtime = object.__new__(self.b.NativeRuntime)
        runtime.home = Path("/nonexistent/native-fixture")
        runtime.observed_code = "f" * 40
        with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_SOURCE_CHANGED"):
            runtime.resolve_original("recover_send", {"session_id": "session-1", "request_id": "a" * 32})
        with tempfile.TemporaryDirectory(prefix="native-hermes-source-") as directory:
            runtime.home = Path(directory)
            runtime.observed_code = "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"
            (runtime.home / "hermes-agent").mkdir()
            (runtime.home / "hermes-agent/hermes_state_keys.py").write_text("changed upstream source")
            with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_SOURCE_CHANGED"):
                runtime.resolve_original("recover_create", {"request_id": "a" * 32})


class RecoveryRuntime(FakeRuntime):
    def __init__(self, lookup_error=None, receipt_error=None, receipt_change=None):
        super().__init__()
        self.lookup_error, self.receipt_error = lookup_error, receipt_error
        self.receipt_change = receipt_change or {}
        self.lookups = []
        self.snapshot = snapshot()

    def resolve_original(self, operation, params):
        self.lookups.append((operation, params))
        if self.lookup_error:
            raise self.lookup_error
        return {"session_id": "session-1", "admission_id": "original-admission"}

    async def rpc(self, method, **params):
        self.calls.append((method, params))
        if method == "session.resume":
            return self.snapshot
        if self.receipt_error:
            raise self.receipt_error
        if method != "prompt.receipt":
            raise AssertionError("Recovery must never mutate")
        return {"admission_id": "original-admission", "ref": {"session_id": "session-1"}, "status": "terminal",
                "sequence": 1, "outcome": "completed", "execution_generation": 1, **self.receipt_change}



class ExplicitSendPreflightTests(unittest.TestCase):
    def test_explicit_send_attaches_without_hydrating_history_and_refuses_positive_holds(self):
        b = load()
        changes = [{"running": True}, {"pending": [{"admission_id": "older", "status": "queued"}]},
                   {"pending": [{"admission_id": "older", "status": "unknown"}]},
                   {"prompts": [{"id": "approval"}]}, {"open_requests": [{"id": "clarification"}]},
                   {"pending_connection": {"server": "existing"}}]
        for change in changes:
            runtime = FakeRuntime()
            async def held(method, **params):
                runtime.calls.append((method, params))
                return {**snapshot(), **change}
            runtime.rpc = held
            result = asyncio.run(b.execute_request({"operation": "send", "sessionId": "session-1",
                "requestId": "c" * 32, "text": "original"}, runtime))
            self.assertEqual(result["state"], "REFUSED")
            self.assertIn(result["code"], {"NATIVE_SESSION_BUSY", "NATIVE_PROMPT_PENDING"})
            self.assertEqual(runtime.calls, [("session.resume", {"session_id": "session-1", "omit_messages": True})])
            self.assertFalse(result["retryAllowed"])
        runtime = FakeRuntime()
        result = asyncio.run(b.execute_request({"operation": "send", "sessionId": "session-1",
            "requestId": "c" * 32, "text": "original"}, runtime))
        self.assertEqual(result["state"], "ADMITTED")
        self.assertEqual(runtime.calls[0], ("session.resume", {"session_id": "session-1", "omit_messages": True}))
        self.assertEqual(sum(method == "prompt.submit" for method, _ in runtime.calls), 1)


if __name__ == "__main__":
    unittest.main()
