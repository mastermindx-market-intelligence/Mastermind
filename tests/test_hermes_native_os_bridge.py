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
        runtime = FakeRuntime(error=self.b.OwnerRefusal("permission_denied"))
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

    def test_invalid_request_never_reaches_runtime(self):
        runtime = FakeRuntime()
        result = asyncio.run(self.b.execute_request({"operation": "status", "token": "bad"}, runtime))
        self.assertEqual(result["state"], "REFUSED")
        self.assertEqual(runtime.identifies, 0)


class FakeRuntime:
    home = Path("/fixture/hermes")

    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.identifies = 0

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
        return snapshot()


if __name__ == "__main__":
    unittest.main()
