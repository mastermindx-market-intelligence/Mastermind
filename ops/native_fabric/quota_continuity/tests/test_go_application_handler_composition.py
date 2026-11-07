"""Actual nested Go handler + A broker/SQLite + loopback-only fake upstream.

No provider, production credential or installed config is used. The startup
proof calls main() with the actual lifecycle helpers explicitly isolated. The
unavailable GLM import supplies seven explicitly synthetic support functions;
the Go router, HTTP handler, A gateway/codec and admission/effects are real.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import socketserver
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

from test_application_turn_admission import ApplicationFixture, ROOT
import pool_status
from go_lease_gateway import GoLeaseGateway, LeaseGatewayError


SERVICE_TOKEN = "fixture-application-service-credential-0123456789"
CONTROLLER_TOKEN = "fixture-controller-credential-0123456789"


class NativeApplicationHTTPFixture(ApplicationFixture):
    def setUp(self):
        # Keep the incumbent status enrichment inert, exactly as the existing
        # broker fixture does. HTTP tests intentionally permit only numeric
        # loopback sockets; the all-network-denying unit boundary is unchanged.
        status_patch = patch.object(pool_status, "build_status", return_value={"pools": {}})
        status_patch.start()
        self.addCleanup(status_patch.stop)
        original_connect, original_bind = socket.socket.connect, socket.socket.bind
        def local_connect(sock, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                raise AssertionError("non-loopback network in application fixture")
            return original_connect(sock, address)
        def local_bind(sock, address):
            if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                raise AssertionError("non-loopback listener in application fixture")
            return original_bind(sock, address)
        for target, replacement in (("connect", local_connect), ("bind", local_bind)):
            guard = patch.object(socket.socket, target, replacement)
            guard.start()
            self.addCleanup(guard.stop)
        proxy_patch = patch.dict(os.environ, {"http_proxy": "", "https_proxy": "", "all_proxy": "",
            "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        proxy_patch.start()
        self.addCleanup(proxy_patch.stop)
        super().setUp()
        self.posts, self.gets, self.pending_at_send = [], [], []
        self.response_status = 200
        self.response = {"id": "fixture-completion", "model": "fixture-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Fixture answer."}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
        self.partial = self.reset = self.redirect = self.slow = self.slow_headers = False
        self.quota_override = None
        self.block = None
        self.arrived = threading.Event()
        self.on_upstream = None
        fixture = self

        class Upstream(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *args):
                pass
            def do_GET(self):
                fixture.gets.append(self.path)
                body = json.dumps(fixture.quota_override if fixture.quota_override is not None else {"usage": {w: {"status": "ok", "percent": 1} for w in ("rolling", "weekly", "monthly")}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                fixture.posts.append((self.path, raw, self.headers.get("Authorization")))
                fixture.pending_at_send.append(fixture.rows("application_requests"))
                fixture.arrived.set()
                if fixture.on_upstream:
                    fixture.on_upstream()
                if fixture.block is not None:
                    if not fixture.block.wait(3):
                        raise AssertionError("fixture upstream was not released")
                if fixture.reset:
                    self.close_connection = True
                    self.connection.close()
                    return
                if fixture.slow_headers:
                    try:
                        self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Trickle: ")
                        self.wfile.flush()
                        for _ in range(100):
                            self.wfile.write(b"x")
                            self.wfile.flush()
                            threading.Event().wait(0.02)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    self.close_connection = True
                    return
                body = fixture.response if isinstance(fixture.response, bytes) else json.dumps(fixture.response).encode()
                self.send_response(302 if fixture.redirect else fixture.response_status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body) + (40 if fixture.partial else 0)))
                if fixture.redirect:
                    self.send_header("Location", "http://127.0.0.1:" + str(self.server.server_port) + "/must-not-follow")
                self.end_headers()
                try:
                    if fixture.slow:
                        for start in range(0, len(body), 4):
                            self.wfile.write(body[start:start + 4])
                            self.wfile.flush()
                            threading.Event().wait(0.02)
                    else:
                        self.wfile.write(body)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                if fixture.partial:
                    self.close_connection = True

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self._serve(self.upstream)
        ext = self.directory / "ext"
        nested = ext / "go_shim"
        nested.mkdir(parents=True)
        handler_file = nested / "go_shim.py"
        handler_file.write_bytes((ROOT / "candidate/go_shim.py").read_bytes())
        glm = types.ModuleType("glm_shim")
        def unused(*args, **kwargs):
            raise AssertionError("main/stream/singleton helper unexpectedly invoked")
        for name in ("acquire_singleton_lock", "format_sse", "iter_sse_chunks", "write_pid"):
            setattr(glm, name, unused)
        glm.check_auth = lambda header, token: hmac.compare_digest(header or "", "Bearer " + token)
        glm.ensure_token = lambda path: CONTROLLER_TOKEN
        glm.redact_secrets = lambda text, secrets: text
        helper_patch = patch.dict(sys.modules, {"glm_shim": glm})
        helper_patch.start()
        self.addCleanup(helper_patch.stop)
        before_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), before_path))
        name = "fixture_go_application_" + self.directory.name.replace("-", "_")
        spec = importlib.util.spec_from_file_location(name, handler_file)
        self.go = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.go
        self.addCleanup(lambda: sys.modules.pop(name, None))
        spec.loader.exec_module(self.go)
        credentials = self.directory / "credentials"
        credentials.mkdir(mode=0o700)
        credentials.chmod(0o700)
        account_file = credentials / "go.json"
        account_file.write_text(json.dumps({"account-a": {"api_key": "fixture-provider-a"}, "account-b": {"api_key": "fixture-provider-b"}}))
        account_file.chmod(0o600)
        prices = self.directory / "prices.json"
        prices.write_text(json.dumps({"models": {m: {"rows": [{"monthly_usd": "20", "in": "1", "out": "1", "cached_read": "0", "cache_write": "0"}]} for m in ("fixture-model", "other-model")}, "unpriced": []}))
        wire = self.directory / "wire.json"
        wire.write_text("{}")
        tiers = self.directory / "tiers.json"
        tiers.write_text(json.dumps({"models": {"fixture-model": {"weight": 1}, "other-model": {"weight": 1}}}))
        self.router = self.go.Router(str(account_file), "http://127.0.0.1:" + str(self.upstream.server_port) + "/v1",
            str(nested), prices_path=str(prices), clock=lambda: self.clock[0],
            env={"GO_WIRE_COMPAT_PATH": str(wire), "GO_WIRE_MATRIX_PATH": str(wire),
                 "GO_MODEL_TIERS_PATH": str(tiers), "GO_WEIGHTS_PATH": str(self.directory / "weights.jsonl")})
        self.service = self.go.ApplicationServiceBinding("macro", "vps", "site_interactive", "MACRO_APPLICATION_TOKEN", SERVICE_TOKEN)
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(self.service,))
        self.server.handle_error = lambda *args: None  # Expected downstream disconnect fixtures.
        self._serve(self.server)
        self.payload = {"model": "fixture-model", "messages": [{"role": "user", "content": "fixture"}], "stream": False}

    def _serve(self, server):
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(stop)

    def request(self, *, turn="turn-1", step="step-1", payload=None, path="/v1/chat/completions", token=SERVICE_TOKEN, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(payload if payload is not None else self.payload).encode()
        supplied = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Connection": "close"}
        if path != "/application-turns/close":
            supplied.update({"X-MM-Application-Turn-ID": turn, "Idempotency-Key": step})
        supplied.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", path, body, supplied)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data), dict(response.getheaders())
        finally:
            connection.close()

    def usage_rows(self):
        path = Path(self.router.usage_path)
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class ApplicationCompositionTests(NativeApplicationHTTPFixture):
    def test_actual_nested_handler_commits_before_one_frozen_upstream_post(self):
        status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body["choices"][0]["message"]["content"], "Fixture answer.")
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.pending_at_send[0][0]["state"], "pending")
        raw = self.posts[0][1]
        self.assertEqual(raw, json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        self.assertEqual(self.posts[0][2], "Bearer fixture-provider-a")
        row = self.rows("application_requests")[0]
        receipt = json.loads(row["terminal_receipt"])
        self.assertEqual(receipt["usage"], {"input_tokens": 11, "output_tokens": 7})
        self.assertEqual(len(self.rows("leases")), 1)
        self.assertEqual(len(self.usage_rows()), 1)
        self.assertEqual(self.usage_rows()[0]["model"], "fixture-model")
        self.assertIsNone(self.usage_rows()[0]["est_usd"])
        self.assertTrue(all(count == 0 for count in self.router.in_flight.values()))

    def test_original_terminal_recovery_precedes_revoked_config_quota_and_secret_paths(self):
        self.assertEqual(self.request()[0], 200)
        before = (len(self.gets), len(self.posts), len(self.usage_rows()))
        self.accounts.unlink()
        self.clock[0] = 3000
        self.router.prices["models"].clear()
        with patch.object(self.router, "reserve_application_account", side_effect=AssertionError("mutable selection on replay")):
            status, body, _ = self.request()
        self.assertEqual(status, 409)
        self.assertEqual(body["application"]["disposition"], "terminal_receipt_only")
        self.assertNotIn("usage", body["application"])
        self.assertEqual((len(self.gets), len(self.posts), len(self.usage_rows())), before)

    def test_two_intentional_steps_keep_the_original_lease_and_account_then_explicit_close(self):
        self.assertEqual(self.request()[0], 200)
        original = self.rows("application_turns")[0]
        self.assertEqual(self.request(step="step-2")[0], 200)
        self.assertEqual(self.rows("application_turns")[0]["lease_id"], original["lease_id"])
        self.assertEqual(self.posts[0][2], self.posts[1][2])
        status, body, _ = self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})
        self.assertEqual(status, 200)
        self.assertEqual(body["application"]["disposition"], "closed")
        self.assertEqual(self.rows("leases")[0]["state"], "released")
        self.assertEqual(len(self.posts), 2)

    def test_concurrent_duplicate_has_one_dispatch_and_no_second_usage_row(self):
        self.block = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            original = pool.submit(self.request)
            self.assertTrue(self.arrived.wait(2))
            duplicate = pool.submit(self.request).result(2)
            self.assertEqual(duplicate[1]["application"]["disposition"], "pending")
            self.block.set()
            self.assertEqual(original.result(3)[0], 200)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.usage_rows()), 1)

    def test_unknown_response_survives_close_expiry_and_new_step_without_replay(self):
        self.partial = True
        status, body, _ = self.request()
        self.assertEqual(status, 503)
        self.assertTrue(body["application"]["effect_unknown"])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.clock[0] = 3000
        self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "turn-1"})[1]["application"]["disposition"], "effect_unknown")
        self.request()
        self.request(step="step-2")
        self.assertEqual(len(self.posts), 1)
        self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))
        self.assertEqual(self.usage_rows(), [])

    def test_complete_upstream_error_is_terminal_once_and_redirect_is_not_followed(self):
        for i, status_code in enumerate((429, 500, 503, 302)):
            with self.subTest(status=status_code):
                self.response_status = status_code
                self.redirect = status_code == 302
                status, body, _ = self.request(turn="turn-" + str(i))
                self.assertEqual(status, status_code)
                self.assertEqual(body["application"]["disposition"], "terminal")
                self.request(turn="turn-" + str(i))
                self.request(path="/application-turns/close", payload={"turn_id": "turn-" + str(i)})
        self.assertEqual(len(self.posts), 4)
        self.assertTrue(all(path == "/v1/chat/completions" for path, *_ in self.posts))
        self.assertEqual(len(self.usage_rows()), 4)

    def test_missing_and_partial_usage_remain_nullable_with_no_cost_fabrication(self):
        for i, usage in enumerate((None, {"prompt_tokens": 9}, {"prompt_tokens": True, "completion_tokens": 4})):
            with self.subTest(usage=usage):
                self.response["usage"] = usage
                self.assertEqual(self.request(turn="usage-" + str(i))[0], 200)
                receipt = json.loads(self.rows("application_requests")[-1]["terminal_receipt"])
                expected = {"input_tokens": None if usage is None or usage.get("prompt_tokens") is True else 9,
                            "output_tokens": 4 if usage and usage.get("completion_tokens") == 4 else None}
                self.assertEqual(receipt["usage"], expected)
                self.assertIsNone(self.usage_rows()[-1]["est_usd"])
                self.request(path="/application-turns/close", payload={"turn_id": "usage-" + str(i)})

    def test_model_mismatch_is_terminal_and_records_actual_model_separately(self):
        self.response["model"] = "other-model"
        status, body, _ = self.request()
        self.assertEqual(status, 502)
        self.assertEqual(body["application"]["disposition"], "terminal")
        self.assertEqual(body["application"]["serving_model"], "other-model")
        row = self.usage_rows()[0]
        self.assertEqual((row["model"], row["binding_model"]), ("other-model", "fixture-model"))
        self.assertEqual(len(self.posts), 1)

    def test_expired_permit_and_lost_intent_ack_never_send_or_invent_terminal(self):
        prepare = self.gateway.prepare_application
        def expire_after_intent(*args, **kwargs):
            permit = prepare(*args, **kwargs)
            self.clock[0] = 3000
            return permit
        with patch.object(self.gateway, "prepare_application", side_effect=expire_after_intent):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.assertIsNone(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")

    def test_committed_intent_ack_loss_leaves_pending_for_original_recovery(self):
        prepare = self.gateway.prepare_application
        def lose_ack(*args, **kwargs):
            prepare(*args, **kwargs)
            raise OSError("fixture intent ack lost")
        with patch.object(self.gateway, "prepare_application", side_effect=lose_ack):
            self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.rows("application_requests")[0]["state"], "pending")
        self.assertEqual(self.posts, [])
        self.assertEqual(self.request()[1]["application"]["disposition"], "pending")
        self.assertEqual(self.posts, [])

    def test_router_refusal_keeps_exact_admitted_account_and_does_not_fall_back(self):
        self.router.auth_failed["account-a"] = True
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(self.rows("application_turns")[0]["account"], "account-a")
        self.assertEqual((self.gets, self.posts), ([], []))
        self.assertEqual(self.rows("application_requests"), [])

    def test_transport_reset_and_invalid_success_are_unknown_not_zero_cost_success(self):
        self.reset = True
        self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.assertEqual(self.usage_rows(), [])
        self.assertEqual(self.request()[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(len(self.posts), 1)

    def test_slow_response_cannot_extend_the_absolute_read_deadline(self):
        self.slow = True
        started = time.monotonic()
        with patch.object(self.go, "APPLICATION_IO_TIMEOUT_S", 0.08):
            status, body, _ = self.request()
        self.assertEqual(status, 503)
        self.assertTrue(body["application"]["effect_unknown"])
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.usage_rows(), [])

    def test_slow_headers_share_the_absolute_deadline_before_any_body(self):
        self.slow_headers = True
        started = time.monotonic()
        with patch.object(self.go, "APPLICATION_IO_TIMEOUT_S", 0.08):
            status, body, _ = self.request()
        self.assertEqual(status, 503)
        self.assertTrue(body["application"]["effect_unknown"])
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")

    def test_dns_deadline_cannot_leave_a_late_resolver_able_to_send(self):
        original = socket.getaddrinfo
        release, finished = threading.Event(), threading.Event()
        def resolution(*args, **kwargs):
            if threading.current_thread().name == "application-dns":
                release.wait(2)
                try:
                    return original(*args, **kwargs)
                finally:
                    finished.set()
            return original(*args, **kwargs)
        quota = {"usage": {w: {"status": "ok", "percent": 1} for w in self.go.WINDOWS}}
        started = time.monotonic()
        try:
            with patch.object(self.router, "_get_json", return_value=quota), patch.object(socket, "getaddrinfo", side_effect=resolution), patch.object(self.go, "APPLICATION_IO_TIMEOUT_S", 0.08):
                self.assertEqual(self.request()[0], 503)
        finally:
            release.set()
        self.assertTrue(finished.wait(1))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")

    def test_stalled_tls_handshake_is_bounded_without_an_http_post(self):
        release = threading.Event()
        class Stall(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(4096)
                release.wait(2)
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Stall)
        self._serve(server)
        self.router.upstream_base = "https://127.0.0.1:" + str(server.server_address[1]) + "/v1"
        quota = {"usage": {w: {"status": "ok", "percent": 1} for w in self.go.WINDOWS}}
        started = time.monotonic()
        try:
            with patch.object(self.router, "_get_json", return_value=quota), patch.object(self.go, "APPLICATION_IO_TIMEOUT_S", 0.08):
                self.assertEqual(self.request()[0], 503)
        finally:
            release.set()
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests")[0]["state"], "unknown")

    def test_required_refresh_failure_cannot_reuse_old_ok_snapshots(self):
        for account in self.router.accounts:
            self.router.snapshots[account] = {w: {"status": "ok", "percent": 1} for w in self.go.WINDOWS}
            self.router.snapshot_at[account] = self.clock[0] - 1000
        with patch.object(self.router, "_get_json", side_effect=OSError("fixture usage unavailable")):
            self.assertEqual(self.request()[0], 429)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests"), [])

    def test_unknown_frontier_percentage_is_not_zero_or_admission_permission(self):
        self.router.model_tiers["models"]["fixture-model"]["weight"] = 4
        self.quota_override = {"usage": {w: {"status": "ok", "percent": 1} for w in self.go.WINDOWS}}
        self.quota_override["usage"]["monthly"].pop("percent")
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.rows("application_requests"), [])

    def test_native_receipt_token_bound_keeps_oversized_count_unknown_but_terminal(self):
        self.response["usage"] = {"prompt_tokens": 10 ** 12, "completion_tokens": 10 ** 12 + 1}
        self.assertEqual(self.request()[0], 200)
        receipt = json.loads(self.rows("application_requests")[0]["terminal_receipt"])
        self.assertEqual(receipt["usage"], {"input_tokens": 10 ** 12, "output_tokens": None})
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")

    def test_settlement_ack_loss_recovers_original_and_usage_ack_loss_never_rewrites(self):
        complete = self.gateway.complete_application
        append = self.router._append_usage
        def commit_then_lose_ack(*args, **kwargs):
            complete(*args, **kwargs)
            raise OSError("fixture commit ack lost")
        def append_then_lose_ack(row):
            append(row)
            raise OSError("fixture usage ack lost")
        with patch.object(self.gateway, "complete_application", side_effect=commit_then_lose_ack), patch.object(self.router, "_append_usage", side_effect=append_then_lose_ack):
            self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[1]["application"]["disposition"], "terminal_receipt_only")
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(len(self.usage_rows()), 1)

    def test_downstream_disconnect_does_not_erase_late_original_completion(self):
        self.block = threading.Event()
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request("POST", "/v1/chat/completions", json.dumps(self.payload),
            {"Authorization": "Bearer " + SERVICE_TOKEN, "Idempotency-Key": "step-1", "X-MM-Application-Turn-ID": "turn-1", "Connection": "close"})
        self.assertTrue(self.arrived.wait(2))
        connection.close()
        self.clock[0] = 3000
        completed = threading.Event()
        original = self.gateway.complete_application
        def settle(*args, **kwargs):
            result = original(*args, **kwargs)
            completed.set()
            return result
        with patch.object(self.gateway, "complete_application", side_effect=settle):
            self.block.set()
            self.assertTrue(completed.wait(3))
        self.assertEqual(self.rows("application_requests")[0]["state"], "terminal")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.request()[1]["application"]["disposition"], "terminal_receipt_only")


if __name__ == "__main__":
    unittest.main()
