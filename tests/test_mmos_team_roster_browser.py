"""Lane TSR/RL: static and node-level guards for roster_browser.js (no
browser launched).

The rename mode was written with unit tests only and first run against a
real dev server by this lane: it died with ``CSS is not defined`` because
``CSS.escape`` (a browser global) was called in Node context while building
a locator. These tests pin the fix.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "tools" / "mmos_team_server" / "roster_browser.js"


class TestRosterBrowserDriver:
    def test_no_browser_only_globals_in_node_context(self):
        code = "\n".join(line.split("//")[0] for line in DRIVER.read_text()
                         .splitlines())
        assert "CSS.escape" not in code, (
            "CSS.escape is a browser global; in Node it throws "
            "'CSS is not defined' and every rename fails (seen live on the "
            "TSR dev server). Escape attribute values in Node instead."
        )

    def test_node_syntax_ok(self):
        node = shutil.which("node")
        if not node:
            return  # browser tooling absent in this checkout; live runs need it
        proc = subprocess.run([node, "--check", str(DRIVER)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr


class TestPairingUrlCheck:
    """Review R2a finding 14: ``pair`` used to open whatever URL its input
    file named. The URL is now parsed (never prefix-compared) and must be
    exactly the loopback team server on the expected port. These tests need
    Node but no browser and no playwright install."""

    def check(self, url, port="3780"):
        node = shutil.which("node")
        if not node:
            pytest.skip("node absent in this checkout")
        script = ("const rb = require(%s);"
                  "const r = rb.checkPairingUrl(%s, %s);"
                  "console.log(r.ok ? 'OK' : 'NO ' + r.reason);"
                  % (json.dumps(str(DRIVER)), json.dumps(url),
                     json.dumps(port)))
        proc = subprocess.run([node, "-e", script], capture_output=True,
                              text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:3780/pair",
        "http://127.0.0.1:3780/pair#one-time-fragment",
        "http://localhost:3780/pair",
        "http://127.0.0.1:3780",
    ])
    def test_loopback_team_server_accepted(self, url):
        assert self.check(url) == "OK"

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:3780@example.com/",      # userinfo smuggles a host
        "http://127.0.0.1.example.com:3780/",      # host is a subdomain
        "http://127.0.0.1:3780@127.0.0.1:9999/",   # userinfo hides other port
        "https://127.0.0.1:3780/pair",             # not http
        "http://127.0.0.1:3773/pair",              # the Chairman's app, not ours
        "http://127.0.0.1/pair",                   # no port at all
        "http://[::1]:3780/pair",
        "http://0.0.0.0:3780/pair",
        "file:///etc/passwd",
        "not a url",
        "",
    ])
    def test_everything_else_refused(self, url):
        out = self.check(url)
        assert out.startswith("NO "), out

    def test_refusal_reason_never_carries_the_url(self):
        # the pairing URL can carry the one-time token; the reason must name
        # only what was wrong, never echo the input
        out = self.check("http://127.0.0.1:3780@example.com/pair#s3cret")
        assert "s3cret" not in out
        assert "example.com" not in out

    def test_pair_mode_validates_before_launch(self):
        # static guard: modePair calls checkPairingUrl and dies on refusal
        # before any browser is launched
        code = DRIVER.read_text()
        body = code[code.index("async function modePair"):code.index(
            "async function modePin")]
        assert "checkPairingUrl" in body
        assert body.index("checkPairingUrl") < body.index("launch(")
