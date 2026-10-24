"""Offline real process/loopback tests for the isolated native DSH web probe.

The disposable Node web app below is a TEST DOUBLE, not a DeepSeek Harness
application. A passing test does not certify the actual donor app.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

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
if (mode === 'exit') process.exit(15);
if (mode === 'hang') { setInterval(()=>{}, 9999); return; }
const server = http.createServer((req,res) => {
 if (mode === 'bad') {
   res.writeHead(200, {'Content-Type':'text/html'});
   res.end('<html><body>Missing app mount</body></html>');
 } else {
   res.writeHead(200, {'Content-Type':'text/html'});
   res.end('<!doctype html><html><body><div id="root"></div><script src="/assets/index.js"></script></body></html>');
 }
});
server.listen(0, '127.0.0.1', () => {
 const url = 'http://'+(mode==='wrongorigin'?'0.0.0.0':'127.0.0.1')+':'+server.address().port+'/';
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


if __name__ == "__main__":
    unittest.main()
