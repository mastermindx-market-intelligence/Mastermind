"""Actual CIO/client -> loaded Macro owner -> shared wrapper -> gateway proof.

The required paired CI step supplies a temporary copy of the actual Macro
checkout, marked by MM_FABRIC_FIXTURE_ROOT. Only that copy's configuration and
the external provider response are synthetic. Normal discovery retains the
dispatcher tests but skips the cross-repository class without the required flag.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain import client, cli_bridge, fabric_inference, thinking_log

MODEL = "composition-text-model"
PROXY_TOKEN = "synthetic-composition-proxy-token"
# Exact candidate gateway; the paired test executes its legacy-compatible path.
GATEWAY_BLOB = "a898910e838ec9c3f9389abaa91cad8d350095a7"


class DispatcherTests(unittest.TestCase):
    def test_missing_owner_is_exclusive(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "fabric"}), \
                patch.object(fabric_inference, "_owner", side_effect=ImportError("absent")), \
                patch.object(cli_bridge, "reason_sync", side_effect=AssertionError("legacy")), \
                patch.object(client, "api_available", side_effect=AssertionError("legacy")):
            self.assertFalse(client.available())
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_owner_unavailable"))

    def test_invalid_request_stops_before_owner(self):
        with patch.object(fabric_inference, "_owner", side_effect=AssertionError("owner")):
            for limit in (True, 0, -1, 32769, "1"):
                self.assertEqual(fabric_inference.call_model("s", "u", max_tokens=limit),
                                 (None, "fabric_invalid_request"))

    def test_cli_selector_presence_and_unknown_backends_are_closed(self):
        for backend in ("", "fabric", "fabric_typo", "production_mode"):
            with self.subTest(backend=backend), patch.dict(os.environ, {"BOT_LLM_BACKEND": backend}), \
                    patch.object(cli_bridge, "_cfg", side_effect=AssertionError("config fallback")), \
                    patch.object(cli_bridge, "cli_path", side_effect=AssertionError("CLI discovery")), \
                    patch.object(cli_bridge, "_subscription_env", side_effect=AssertionError("credential")):
                self.assertEqual(cli_bridge._selected_backend(), backend)
                self.assertFalse(cli_bridge.available())
                self.assertFalse(asyncio.run(cli_bridge._reason("u"))["ok"])

                async def events():
                    return [event async for event in cli_bridge.chat_stream("u", resume="old-session")]

                self.assertEqual(asyncio.run(events()),
                                 [{"type": "error", "error": "backend_chat_unsupported"}])
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "waterfall"}):
            self.assertEqual(cli_bridge._selected_backend(""), "")

    def test_log_writer_preserves_unknown_and_trusted_provider(self):
        row = thinking_log.build_row(question="q", answer="a", model="claude-looking-alias",
                                     backend="fabric", provider="actual-pool-provider",
                                     input_tokens=None, output_tokens=None)
        self.assertEqual(row["provider"], "actual-pool-provider")
        self.assertIsNone(json.loads(json.dumps(row))["input_tokens"])
        self.assertEqual(thinking_log.build_row(question="q", answer="a")["input_tokens"], 0)


@contextmanager
def gateway_surface(module, root, dispatches, next_response):
    import httpx
    from fastapi.testclient import TestClient

    class Body(httpx.AsyncByteStream):
        def __init__(self, data):
            self.data = data

        async def __aiter__(self):
            yield self.data

    async def upstream(request):
        dispatches.append({"body": json.loads(request.content), "headers": dict(request.headers)})
        result = next_response()
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        if json.loads(request.content).get("stream"):
            message = result["choices"][0]["message"]
            delta = {"content": message.get("content")}
            if message.get("tool_calls"):
                delta["tool_calls"] = [{"index": i, **item}
                                       for i, item in enumerate(message["tool_calls"])]
            frames = [{"model": result["model"], "choices": [{"index": 0, "delta": delta,
                "finish_reason": result["choices"][0]["finish_reason"]}], "usage": None}]
            if result.get("usage") is not None:
                frames.append({"model": result["model"], "choices": [], "usage": result["usage"]})
            body = b"".join(b"data: " + json.dumps(frame).encode() + b"\n\n" for frame in frames)
            return httpx.Response(200, stream=Body(body + b"data: [DONE]\n\n"),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, stream=Body(json.dumps(result).encode()),
                              headers={"content-type": "application/json"})

    app = module.create_app(module.Settings(
        api_keys=("synthetic-upstream-key",), proxy_token=PROXY_TOKEN,
        state_dir=root / "gateway", safe_rpm_shared=20,
    ), transport=httpx.MockTransport(upstream))
    with TestClient(app, client=("127.0.0.1", 44111)) as asgi:
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_POST(self):
                data = self.rfile.read(int(self.headers["Content-Length"]))
                response = asgi.post(self.path, content=data, headers=dict(self.headers), follow_redirects=False)
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                self.send_header("Content-Length", str(len(response.content)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(response.content)
                self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/v1"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


class FabricCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MM_REQUIRE_FABRIC_COMPOSITION") != "1":
            raise unittest.SkipTest("Run in the required paired Fabric composition step")
        cls.owner, cls.shared, cls.macro_root = fabric_inference._owner()
        expected_root = Path(os.environ["MM_FABRIC_FIXTURE_ROOT"]).resolve()
        if cls.macro_root != expected_root or not (expected_root / ".fabric-composition-fixture").is_file():
            raise AssertionError("A disposable actual Macro source copy is required")
        import bot
        if bot._VENDOR.resolve() != expected_root:
            raise AssertionError("The actual bot vendor bootstrap must resolve the paired source")
        cls.config_paths = [expected_root / "config" / name for name in (
            "provider_production_modes.v1.json", "provider_workloads.v1.json", "capability_manifest.yml")]
        cls.originals = {path: path.read_bytes() if path.exists() else None for path in cls.config_paths}
        path = Path(__file__).resolve().parents[2] / "ops/native_fabric/experiential_proxy/gateway.py"
        raw = path.read_bytes()
        if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != GATEWAY_BLOB:
            raise AssertionError("Pinned gateway source mismatch")
        spec = importlib.util.spec_from_file_location("_mastermind_text_owner_gateway", path)
        cls.gateway = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.gateway
        spec.loader.exec_module(cls.gateway)

    @classmethod
    def tearDownClass(cls):
        for path, original in cls.originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        sys.modules.pop("_mastermind_text_owner_gateway", None)

    def start(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def setUp(self):
        import yaml

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dispatches, self.rows = [], []
        self.response = {"model": MODEL, "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "Grounded CIO narration."},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 19, "completion_tokens": 7}}
        surface = gateway_surface(self.gateway, self.root, self.dispatches, lambda: self.response)
        url = surface.__enter__()
        self.addCleanup(surface.__exit__, None, None, None)
        transport = self.owner._ApplicationFabricTransport(
            url, "TEST_FABRIC_PROXY_TOKEN", "actual-fixture-provider", MODEL, "unknown",
            "fabric:text-fixture", "text_fixture", qualified=True, application_allowed=True,
        )
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS, {"text_fixture_v1": transport}))
        self.document = json.loads(self.originals[self.config_paths[0]])
        self.mode = {key: getattr(transport, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        self.mode.update(transport_id="text_fixture_v1", enabled=True, application_allowed=True,
                         qualification=self.owner.PROFILE_QUALIFIED_CANARY,
                         qualification_ref="fixture:source-only", qualified_until=time.time()+3600)
        self.document["application_fabric_modes"] = {"shared_fabric": self.mode}
        self.manifest = {"capabilities": [{"capability_id": "text_fixture", "secret_ref": "TEST_FABRIC_PROXY_TOKEN",
                                          "kill_state": "active", "allowed_lanes": ["mastermind-text"]}]}
        self.save()
        self.config_paths[1].write_bytes(self.originals[self.config_paths[1]])
        self.start(patch.dict(os.environ, {
            "BOT_LLM_BACKEND": "fabric", "MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
            "MM_PROVIDER_WORKLOAD_PROFILE": "site_batch", "TEST_FABRIC_PROXY_TOKEN": PROXY_TOKEN,
            "PROVIDER_HEALTH_PATH": str(self.root / "health.jsonl"),
            "AI_COSTS_STATE_ROOT": str(self.root / "costs"),
        }, clear=True))
        self.start(patch.object(thinking_log, "log_turn_async", side_effect=lambda **kw: self.rows.append(thinking_log.build_row(**kw))))
        for target, attr in ((client.cli_bridge, "reason_sync"), (client.codex_bridge, "reason_sync"),
                             (client, "api_available"), (self.shared, "_oauth_pool_candidates")):
            self.start(patch.object(target, attr, side_effect=AssertionError("legacy discovery/dispatch")))

    def save(self):
        import yaml
        self.config_paths[0].write_text(json.dumps(self.document))
        self.config_paths[2].write_text(yaml.safe_dump(self.manifest))

    def costs(self):
        return [json.loads(line) for path in (self.root / "costs").rglob("*.jsonl")
                for line in path.read_text().splitlines()]

    def test_actual_cio_uses_loaded_owner_gateway_and_one_usage_writer(self):
        from brain import cio
        answer = cio._narrate({"as_of": "2026-11-04", "iso_week": "2026-W45",
                               "per_seat": {}, "book_summary": {}})
        self.assertEqual(answer, "Grounded CIO narration.")
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.dispatches[0]["body"]["model"], MODEL)
        self.assertIn("2026-W45", json.dumps(self.dispatches[0]["body"]))
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual((self.costs()[0]["provider"], self.costs()[0]["cost_basis"],
                          self.costs()[0]["input_tokens"]), ("actual-fixture-provider", "unknown", 19))
        self.assertEqual((self.rows[0]["seat"], self.rows[0]["book"], self.rows[0]["provider"]),
                         ("cio", "system", "actual-fixture-provider"))

    def test_unknown_usage_is_neither_zero_nor_free(self):
        self.response["usage"] = None
        self.assertEqual(client.call_model("s", "u"), ("Grounded CIO narration.", None))
        self.assertIsNone(json.loads(json.dumps(self.rows[0]))["input_tokens"])
        self.assertIsNone(self.rows[0]["output_tokens"])
        self.assertEqual(self.costs(), [])

    def test_fresh_revocation_after_readiness(self):
        self.assertTrue(client.available())
        self.manifest["capabilities"][0]["kill_state"] = "killed"
        self.save()
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("secret read")):
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
        self.assertEqual(self.dispatches, [])

    def test_held_expired_or_malformed_owner_never_dispatches(self):
        for key, value in (("enabled", False), ("qualified_until", 1),
                           ("application_allowed", False), ("model", "forged")):
            old = self.mode[key]
            self.mode[key] = value
            self.save()
            with self.subTest(key=key), patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("secret read")):
                self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
            self.mode[key] = old
        self.config_paths[0].write_text("{malformed")
        self.assertFalse(client.available())
        self.assertEqual(self.dispatches, [])

    def test_absent_or_invalid_selection_and_missing_credential_are_exclusive(self):
        del os.environ["MM_PROVIDER_APPLICATION_MODE"]
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_not_selected"))
        os.environ["MM_PROVIDER_APPLICATION_MODE"] = ""
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
        os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
        del os.environ["TEST_FABRIC_PROXY_TOKEN"]
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_binding_unavailable"))
        self.assertEqual(self.dispatches, [])

    def test_transport_timeout_is_one_uncertain_inference(self):
        import httpx
        self.response = httpx.ReadTimeout("private transport detail")
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_effect_unknown"))
        self.assertEqual(len(self.dispatches), 1)
        self.assertIsNone(self.rows[0]["input_tokens"])

    def test_empty_and_unsolicited_tools_do_not_recover(self):
        self.response["choices"][0]["message"]["content"] = ""
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_unavailable"))
        self.assertEqual(len(self.dispatches), 1)

    def test_unsolicited_tools_are_not_executed_or_returned_as_prose(self):
        self.response["choices"][0]["message"]["tool_calls"] = [{"id": "call-1", "type": "function",
            "function": {"name": "write_action", "arguments": "{}"}}]
        self.response["choices"][0]["finish_reason"] = "tool_calls"
        self.assertEqual(client.call_model("s", "u"), (None, "fabric_unavailable"))
        self.assertEqual(len(self.dispatches), 1)

    def test_callback_type_error_after_response_cannot_replay(self):
        real = self.shared._FabricMessages.create

        def broken(instance, **kwargs):
            real(instance, **kwargs)
            raise TypeError("callback bug after dispatch")

        with patch.object(self.shared._FabricMessages, "create", broken):
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_unavailable"))
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.costs()), 1)

    def test_logging_failure_keeps_answer_without_replay(self):
        with patch.object(thinking_log, "log_turn_async", side_effect=RuntimeError("log unavailable")):
            self.assertEqual(client.call_model("s", "u"), ("Grounded CIO narration.", None))
        self.assertEqual(len(self.dispatches), 1)

    def test_mixed_macro_source_is_unavailable(self):
        with patch.object(self.shared, "__file__", "/another-checkout/engine/llm_auth.py"):
            self.assertEqual(client.call_model("s", "u"), (None, "fabric_owner_unavailable"))
        self.assertEqual(self.dispatches, [])


if __name__ == "__main__":
    unittest.main()
