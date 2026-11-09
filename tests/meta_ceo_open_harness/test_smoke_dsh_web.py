"""Offline real process/loopback tests for the isolated native DSH web probe.

The disposable Node web app below is a TEST DOUBLE, not a DeepSeek Harness
application. A passing test does not certify the actual donor app.
"""
from __future__ import annotations

import importlib.util
import io
import queue
import threading
import time
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

SCRIPT = Path(__file__).resolve().parents[2] / "experiments/meta_ceo_open_harness/smoke_dsh_web.py"
spec = importlib.util.spec_from_file_location("smoke_dsh_web", SCRIPT)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
NODE = Path(shutil.which("node") or "/not-installed/node").resolve()

NODE_APP = r'''
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const args = process.argv.slice(2);
if (!args.includes('web') || !args.includes('--no-open')) process.exit(11);
if (args[args.indexOf('--host')+1] !== '127.0.0.1') process.exit(12);
if (args[args.indexOf('--port')+1] !== '0') process.exit(13);
const bad = ['OPENAI_API_KEY','ANTHROPIC_API_KEY','ZAI_API_KEY','NODE_OPTIONS','HTTP_PROXY','HTTPS_PROXY','AWS_SECRET_ACCESS_KEY'];
if (bad.some(key => process.env[key]) || !process.env.DSH_HOME || !process.env.HOME) process.exit(14);
const mode = fs.readFileSync(path.join(__dirname,'mode.txt'),'utf8').trim();
const token = 'fixture_token_very_long_1234567890abcdef';
if (mode === 'exit') process.exit(15);
if (mode === 'hang') { setInterval(()=>{}, 9999); return; }
const server = http.createServer((req,res) => {
 const uri = new URL(req.url, 'http://127.0.0.1');
 if (mode !== 'badtoken' && uri.pathname === '/' && uri.searchParams.get('token') === token) {
   const target = mode.startsWith('redirect:') ? mode.slice('redirect:'.length) : './';
   res.writeHead(302, {'Set-Cookie':'dsh_session=fixture; HttpOnly; SameSite=Lax', 'Location':target});
   res.end(); return;
 }
 if (!(req.headers.cookie || '').includes('dsh_session=fixture')) {
   res.writeHead(401, {'Content-Type':'text/plain'}); res.end('Authentication required'); return;
 }
 if (mode === 'bad') {
   res.writeHead(200, {'Content-Type':'text/html'});
   res.end('<html><body>Missing app mount</body></html>');
 } else {
   res.writeHead(200, {'Content-Type':'text/html'});
   res.end('<!doctype html><html><body><div id="root"></div><script src="/assets/index.js"></script></body></html>');
 }
});
server.listen(0, '127.0.0.1', () => {
 const suffix = mode === 'bareorigin' ? '/' : '/?token='+token;
 const url = 'http://'+(mode==='wrongorigin'?'0.0.0.0':'127.0.0.1')+':'+server.address().port+suffix;
 console.log(url);
});
process.on('SIGTERM',()=>server.close(()=>process.exit(0)));
'''


@unittest.skipUnless(NODE.exists(), "Node executable required for real process fixture")
class NativeAppSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = tempfile.TemporaryDirectory(prefix="mmx-dsh-smoke-fixture-")
        self.root = Path(self.work.name)
        self.donor = self.root / "donor"
        self.donor.mkdir()
        entry = self.donor / "apps/cli/lib"
        entry.mkdir(parents=True)
        (self.donor / "node_modules").mkdir()
        (entry / "bin.js").write_text(NODE_APP)
        (entry / "mode.txt").write_text("good\n")
        self._git("init", "-q")
        self._git("add", ".")
        self._git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "test fixture")
        self.pin = self._git("rev-parse", "HEAD").strip()

    def tearDown(self) -> None:
        self.work.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.donor, check=True,
                              capture_output=True, text=True).stdout

    def _set_mode(self, mode: str) -> None:
        (self.donor / "apps/cli/lib/mode.txt").write_text(mode + "\n")
        self._git("add", "apps/cli/lib/mode.txt")
        self._git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "change fixture mode")
        self.pin = self._git("rev-parse", "HEAD").strip()

    def _run(self, *, pin: str | None = None, timeout: float = 2) -> dict:
        return smoke.execute(self.donor, self.pin if pin is None else pin, NODE, timeout)

    def test_valid_live_process_and_real_loopback_html(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY":"should-not-leak",
                                          "NODE_OPTIONS":"--definitely-invalid-option",
                                          "HTTPS_PROXY":"http://untrusted.invalid"}):
            result = self._run()
        self.assertEqual(result["status"], "NATIVE_WEB_SHELL_PASS", result)
        self.assertTrue(result["owned_process_stopped"])
        self.assertTrue(result["url"].startswith("http://127.0.0.1:"))
        self.assertEqual(result["http_status"], 200)
        self.assertNotIn("token=", json.dumps(result), "launch bearer must never reach receipt")
        self.assertFalse(result["native_chat_tested"])
        self.assertEqual(result["provider_requests_observed"], "NOT_INSTRUMENTED")
        opener = build_opener(ProxyHandler({}))
        with self.assertRaises(URLError):
            opener.open(result["url"], timeout=.15)

    def test_wrong_donor_revision_refuses_before_spawn(self) -> None:
        result = self._run(pin="0" * 40)
        self.assertEqual(result["status"], "PIN_MISMATCH")
        self.assertNotIn("owned_process_stopped", result)

    def test_dirty_tracked_source_refuses_before_spawn(self) -> None:
        with (self.donor / "apps/cli/lib/bin.js").open("a") as f:
            f.write("// unreviewed mutation\n")
        self.assertEqual(self._run()["status"], "SOURCE_DIRTY")

    def test_missing_built_binary_refuses(self) -> None:
        (self.donor / "apps/cli/lib/bin.js").unlink()
        self._git("add", "-u")
        self._git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-qm", "remove generated CLI binary")
        self.pin = self._git("rev-parse", "HEAD").strip()
        self.assertEqual(self._run()["status"], "BUILD_MISSING")

    def test_missing_dependencies_refuses(self) -> None:
        (self.donor / "node_modules").rmdir()
        self.assertEqual(self._run()["status"], "DEPENDENCIES_MISSING")

    def test_fake_app_without_mount_is_not_accepted(self) -> None:
        self._set_mode("bad")
        result = self._run()
        self.assertEqual(result["status"], "INVALID_WEB_RESPONSE", result)
        self.assertTrue(result["owned_process_stopped"])

    def test_exited_process_is_not_web_ready(self) -> None:
        self._set_mode("exit")
        result = self._run()
        self.assertEqual(result["status"], "STARTUP_EXITED", result)
        self.assertTrue(result["owned_process_stopped"])

    def test_hung_process_times_out_and_is_reaped(self) -> None:
        self._set_mode("hang")
        result = self._run(timeout=.35)
        self.assertEqual(result["status"], "STARTUP_NO_LOOPBACK_URL", result)
        self.assertTrue(result["owned_process_stopped"])

    def test_nonloopback_url_is_not_followed(self) -> None:
        self._set_mode("wrongorigin")
        result = self._run(timeout=.35)
        self.assertEqual(result["status"], "STARTUP_NO_LOOPBACK_URL", result)
        self.assertTrue(result["owned_process_stopped"])

    def test_bare_url_cannot_bypass_token_exchange(self) -> None:
        self._set_mode("bareorigin")
        result = self._run(timeout=.35)
        self.assertEqual(result["status"], "STARTUP_NO_LOOPBACK_URL", result)
        self.assertTrue(result["owned_process_stopped"])

    def test_broken_token_exchange_never_claims_success(self) -> None:
        self._set_mode("badtoken")
        result = self._run(timeout=2)
        # A broken token exchange must never be reported as a pass. The fixture
        # app announces a loopback origin but never completes the token exchange,
        # so a bounded probe that has observed the announcement refuses with
        # HTTP_NOT_READY. If the fixture's announcement does not reach the probe
        # window in time (slow/loaded runner), the probe instead refuses with
        # STARTUP_NO_LOOPBACK_URL. Both are non-success refusals; the invariant
        # under test is "never NATIVE_WEB_SHELL_PASS", so accept either ordering.
        self.assertIn(result["status"], ("HTTP_NOT_READY", "STARTUP_NO_LOOPBACK_URL"), result)
        self.assertTrue(result["owned_process_stopped"])

    def test_invalid_expected_pin_is_rejected(self) -> None:
        self.assertEqual(self._run(pin="HEAD")["status"], "INVALID_INPUT")

    def test_receipt_is_private_and_no_overwrite(self) -> None:
        filename = self.root / "evidence" / "smoke.json"
        def call() -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(SCRIPT), "--donor", str(self.donor),
                                   "--node", str(NODE), "--expected-sha", self.pin,
                                   "--timeout", "2", "--receipt", str(filename)],
                                   cwd=self.root, capture_output=True, text=True, timeout=8)
        first = call()
        self.assertEqual(first.returncode, 0, first.stderr)
        data = json.loads(filename.read_text())
        self.assertEqual(data["status"], "NATIVE_WEB_SHELL_PASS")
        self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
        second = call()
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(json.loads(filename.read_text()), data)
        self.assertIn("RECEIPT_NOT_PERSISTED", second.stderr)


    def test_foreign_port_redirect_sends_no_request_or_cookie(self) -> None:
        captured = []
        class Capture(BaseHTTPRequestHandler):
            def do_GET(self):
                captured.append({"path": self.path, "cookie": self.headers.get("Cookie")})
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b'<html><div id="root"></div><script></script></html>')

            def log_message(self, *args):
                pass

        foreign = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
        thread = threading.Thread(target=foreign.serve_forever, daemon=True)
        thread.start()
        try:
            self._set_mode(f"redirect:http://127.0.0.1:{foreign.server_port}/foreign")
            result = self._run()
        finally:
            foreign.shutdown()
            foreign.server_close()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(captured), 0, "a redirected request reached the foreign port")
        self.assertEqual(result["status"], "UNTRUSTED_ORIGIN", result)
        self.assertTrue(result["owned_process_stopped"])
        self.assertNotIn("fixture_token", json.dumps(result))
        self.assertNotIn("dsh_session", json.dumps(result))

    def test_malformed_raw_location_refuses_before_normalization(self) -> None:
        self._set_mode("redirect:./\tmalformed")
        result = self._run()
        self.assertEqual(result["status"], "UNTRUSTED_ORIGIN", result)
        self.assertTrue(result["owned_process_stopped"])

    def _uncertain_cleanup(self, real_terminate, *, error=None):
        def stop_then_report_uncertain(process):
            self.assertTrue(real_terminate(process), "fixture child must actually be reaped")
            self.assertIsNotNone(process.poll())
            if error is not None:
                raise error
            return False
        return stop_then_report_uncertain

    def test_probe_refusal_cannot_hide_uncertain_cleanup(self) -> None:
        real_terminate = smoke.terminate_own_process
        with patch.object(smoke, "wait_for_web", side_effect=smoke.Refused(
                "FIXTURE_REFUSED", "controlled probe refusal")), patch.object(
                smoke, "terminate_own_process",
                side_effect=self._uncertain_cleanup(real_terminate)):
            result = self._run()
        self.assertEqual(result["status"], "CLEANUP_UNKNOWN", result)
        self.assertFalse(result["owned_process_stopped"])
        self.assertEqual(result["probe_status"], "FIXTURE_REFUSED")
        self.assertEqual(result["probe_reason"], "controlled probe refusal")

    def test_os_and_value_errors_cannot_hide_uncertain_cleanup(self) -> None:
        real_terminate = smoke.terminate_own_process
        for error in (OSError("controlled probe error"), ValueError("controlled probe error")):
            with self.subTest(kind=type(error).__name__), patch.object(
                    smoke, "wait_for_web", side_effect=error), patch.object(
                    smoke, "terminate_own_process",
                    side_effect=self._uncertain_cleanup(real_terminate)):
                result = self._run()
            self.assertEqual(result["status"], "CLEANUP_UNKNOWN", result)
            self.assertFalse(result["owned_process_stopped"])
            self.assertEqual(result["probe_status"], "INPUT_UNAVAILABLE")
            self.assertEqual(result["probe_reason"], type(error).__name__)

    def test_success_cannot_hide_uncertain_cleanup(self) -> None:
        real_terminate = smoke.terminate_own_process
        with patch.object(smoke, "terminate_own_process",
                          side_effect=self._uncertain_cleanup(real_terminate)):
            result = self._run()
        self.assertEqual(result["status"], "CLEANUP_UNKNOWN", result)
        self.assertFalse(result["owned_process_stopped"])
        self.assertEqual(result["probe_status"], "WEB_HTML_READ")
        self.assertEqual(result["http_status"], 200)

    def test_cleanup_error_preserves_primary_probe_refusal(self) -> None:
        real_terminate = smoke.terminate_own_process
        with patch.object(smoke, "wait_for_web", side_effect=smoke.Refused(
                "FIXTURE_REFUSED", "controlled probe refusal")), patch.object(
                smoke, "terminate_own_process", side_effect=self._uncertain_cleanup(
                    real_terminate, error=OSError("controlled cleanup error"))):
            result = self._run()
        self.assertEqual(result["status"], "CLEANUP_UNKNOWN", result)
        self.assertFalse(result["owned_process_stopped"])
        self.assertEqual(result["probe_status"], "FIXTURE_REFUSED")
        self.assertEqual(result["probe_reason"], "controlled probe refusal")

    def test_cli_persists_uncertain_cleanup_and_returns_nonzero(self) -> None:
        filename = self.root / "evidence" / "cleanup.json"
        real_terminate = smoke.terminate_own_process
        argv = [str(SCRIPT), "--donor", str(self.donor), "--node", str(NODE),
                "--expected-sha", self.pin, "--timeout", "2", "--receipt", str(filename)]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(sys, "stdout", output), patch.object(
                smoke, "wait_for_web", side_effect=smoke.Refused(
                    "FIXTURE_REFUSED", "controlled probe refusal")), patch.object(
                smoke, "terminate_own_process",
                side_effect=self._uncertain_cleanup(real_terminate)):
            status = smoke.main()
        self.assertEqual(status, 2)
        result = json.loads(filename.read_text())
        self.assertEqual(result["status"], "CLEANUP_UNKNOWN")
        self.assertEqual(result["probe_status"], "FIXTURE_REFUSED")
        self.assertFalse(result["owned_process_stopped"])
        self.assertEqual(json.loads(output.getvalue())["status"], "CLEANUP_UNKNOWN")


class OriginBoundaryTests(unittest.TestCase):
    PORT = 31871
    TOKEN = "fixture_token_very_long_1234567890abcdef"

    def _lines(self, *ports):
        lines = queue.Queue()
        for port in ports:
            lines.put(f"http://127.0.0.1:{port}/?token={self.TOKEN}")
        return lines

    def test_redirect_handler_refuses_foreign_and_malformed_origins_before_dispatch(self):
        handler = smoke.OriginBoundRedirectHandler(self.PORT)
        request = Request(f"http://127.0.0.1:{self.PORT}/?token={self.TOKEN}")
        urls = (
            f"http://127.0.0.1:{self.PORT + 1}/",
            f"https://127.0.0.1:{self.PORT}/",
            f"http://localhost:{self.PORT}/",
            f"http://127.0.0.2:{self.PORT}/",
            f"http://user:secret@127.0.0.1:{self.PORT}/",
            "http://127.0.0.1:invalid/",
            f"http://127.0.0.1:{self.PORT}:80/",
            "http://127.0.0.1:65536/",
            f"http://[::1]:{self.PORT}/",
            "file:///fixture",
            f"http://127.0.0.1:{self.PORT}/\r\nmalformed",
        )
        for url in urls:
            with self.subTest(url=url), self.assertRaises(smoke.Refused) as caught:
                handler.redirect_request(request, None, 302, "Found", {}, url)
            self.assertEqual(caught.exception.status, "UNTRUSTED_ORIGIN")
            self.assertNotIn("secret", str(caught.exception))
            self.assertNotIn(self.TOKEN, str(caught.exception))

    def test_every_redirect_status_checks_raw_location_or_uri_and_closes_response(self):
        for code in (301, 302, 303, 307, 308):
            for field in ("Location", "URI"):
                with self.subTest(code=code, field=field):
                    handler = smoke.OriginBoundRedirectHandler(self.PORT)
                    handler.parent = Mock()
                    request = Request(f"http://127.0.0.1:{self.PORT}/?token={self.TOKEN}")
                    request.timeout = .45
                    headers = Message()
                    headers[field] = "./\tmalformed"
                    response = Mock()
                    with self.assertRaises(smoke.Refused) as caught:
                        getattr(handler, f"http_error_{code}")(
                            request, response, code, "Redirect", headers)
                    self.assertEqual(caught.exception.status, "UNTRUSTED_ORIGIN")
                    handler.parent.open.assert_not_called()
                    response.close.assert_called_once_with()

    def test_relative_same_origin_redirect_remains_valid(self):
        handler = smoke.OriginBoundRedirectHandler(self.PORT)
        request = Request(f"http://127.0.0.1:{self.PORT}/?token={self.TOKEN}")
        redirected = handler.redirect_request(request, None, 302, "Found", {}, "./")
        self.assertEqual(redirected.full_url, f"http://127.0.0.1:{self.PORT}/")

    def test_final_response_origin_is_checked_before_reading_or_accepting_html(self):
        headers = Message()
        headers["Content-Type"] = "text/html"
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = headers
        response.geturl.return_value = f"http://127.0.0.1:{self.PORT + 1}/"
        response.read.return_value = b'<html><div id="root"></div><script></script></html>'
        opener = Mock()
        opener.open.return_value = response
        with patch.object(smoke, "build_opener", return_value=opener):
            with self.assertRaises(smoke.Refused) as caught:
                smoke.wait_for_web(Mock(poll=Mock(return_value=None)),
                                   self._lines(self.PORT), time.monotonic() + 1)
        self.assertEqual(caught.exception.status, "UNTRUSTED_ORIGIN")
        response.read.assert_not_called()

    def test_later_announcement_cannot_rebind_admitted_origin(self):
        opener = Mock()
        opener.open.side_effect = [URLError("controlled not ready"),
                                   AssertionError("must not dispatch to a rebound origin")]
        with patch.object(smoke, "build_opener", return_value=opener):
            with self.assertRaises(smoke.Refused) as caught:
                smoke.wait_for_web(Mock(poll=Mock(return_value=None)),
                                   self._lines(self.PORT, self.PORT + 1),
                                   time.monotonic() + 1)
        self.assertEqual(caught.exception.status, "UNTRUSTED_ORIGIN")
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
