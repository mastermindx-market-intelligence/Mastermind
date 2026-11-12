"""Tests for the CLI front (tools/mmos_computer_use/cli.py).

The CLI must be a thin transport over the same server dispatch: identical
receipts, identical gates. These tests inject a fake context so no real
peekaboo, screen, or network is touched.

BCU R3 H2: there is no test-mode flag any more. make_ctx's 1 s thresholds
arrive by CONSTRUCTOR INJECTION (Presence(min_idle_seconds=...),
Pacer(seconds=...)) — the only sub-default path — so this suite runs the
same way in or outside pytest, and no environment variable can loosen a
floor:

    python3 -m pytest tests/test_mmos_bcu_cli.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

CHECKOUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL_DIR = os.path.join(CHECKOUT, "tools", "mmos_computer_use")
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
if CHECKOUT not in sys.path:
    sys.path.insert(0, CHECKOUT)

import cli  # noqa: E402
import server  # noqa: E402


class FakeAdapter(object):
    def __init__(self):
        self.calls = []

    def list_apps(self):
        return [{"app_name": "Fixtured", "bundle_id": "fix.tured"}]

    def list_windows(self, app):
        return [{"window_id": 11, "title": "Fixtured main"}]


# State dirs created by make_ctx (Lease/Pacer default to the REAL
# tools/mmos_computer_use/state — a live proof lease there must never be
# visible to, or mutated by, a unit test). Cleaned in tearDown.
_STATE_DIRS = []


def make_ctx():
    # H2: the runtime dict carries NO threshold keys — environment and
    # runtime.json values are unconditionally floored at 180 s. The 1 s
    # test thresholds arrive by constructor injection, the only
    # sub-default path (the absolute 1 s floor still applies there).
    runtime = {
        "peekaboo_bin": "/bin/true",
        "peekaboo_sha256": "0" * 64,
    }
    state = tempfile.mkdtemp(prefix="mmos-cu-cli-state-")
    _STATE_DIRS.append(state)
    deny = server.DenyList.load(os.path.join(TOOL_DIR, "deny.json"))
    lease = server.Lease(state_dir=state)
    presence = server.Presence(min_idle_seconds=1.0)
    pacer = server.Pacer(state_dir=state, seconds=1.0)
    adapter = FakeAdapter()
    vision = server.VisionClient()
    return server.ToolContext(runtime, deny, lease, presence, adapter,
                              vision, pacer)


class CliTests(unittest.TestCase):
    def tearDown(self):
        while _STATE_DIRS:
            shutil.rmtree(_STATE_DIRS.pop(), ignore_errors=True)

    def run_cli(self, argv, ctx):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = cli.main(argv, ctx=ctx)
        return code, out.getvalue()

    def test_usage_error_exit_2(self):
        code, out = self.run_cli([], ctx=make_ctx())
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_unknown_action_exit_2(self):
        # argparse reports unknown subcommands itself: usage on stderr,
        # SystemExit(2).
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err), \
                self.assertRaises(SystemExit) as caught:
            cli.main(["definitely-not-an-action"], ctx=make_ctx())
        self.assertEqual(caught.exception.code, 2)

    def test_receipt_json_on_stdout(self):
        code, out = self.run_cli(["windows", "--app", "Fixtured"],
                                 ctx=make_ctx())
        self.assertEqual(code, 0)
        receipt = json.loads(out.strip())
        self.assertEqual(receipt.get("op"), "windows")

    def test_window_id_parsed_as_int(self):
        # The CLI must hand the handler {"window_id": 11} (int), not "11".
        captured = {}

        def fake_handler(ctx, arguments):
            captured.update(arguments)
            return {"content": [{"type": "text", "text":
                    json.dumps({"status": "OK"})}], "isError": False}

        with mock.patch.object(server, "handle_tool_call", fake_handler):
            code, out = self.run_cli(["inspect", "--window-id", "11"],
                                     ctx=make_ctx())
        self.assertEqual(code, 0)
        self.assertEqual(captured.get("window_id"), 11)
        self.assertEqual(json.loads(out.strip())["status"], "OK")

    def test_slice_paste_text_flag_maps(self):
        # Text with spaces must arrive as ONE string argument.
        captured = {}

        def fake_handler(ctx, arguments):
            captured.update(arguments)
            return {"content": [{"type": "text", "text":
                    json.dumps({"status": "NOT_APPLIED",
                                "cause": "fake"})}], "isError": False}

        with mock.patch.object(server, "handle_tool_call", fake_handler):
            code, _ = self.run_cli(
                ["slice_paste", "--window-id", "11",
                 "--text", "hello world with spaces"], ctx=make_ctx())
        self.assertEqual(code, 0)
        self.assertEqual(captured.get("text"), "hello world with spaces")
        self.assertEqual(captured.get("window_id"), 11)
        self.assertEqual(captured.get("action"), "slice_paste")

    def test_lease_acquire_owner_flag(self):
        ctx = make_ctx()
        code, out = self.run_cli(
            ["lease_acquire", "--owner", "cli-test", "--ttl-seconds", "60"],
            ctx=ctx)
        self.assertEqual(code, 0)
        receipt = json.loads(out.strip())
        self.assertEqual(receipt.get("status"), "OK")
        self.run_cli(["lease_release", "--owner", "cli-test"], ctx=ctx)

    def test_lease_nonce_flag_maps(self):
        # M5: every act carries the acquisition nonce; the CLI flag must
        # reach the handler as lease_nonce, exactly once.
        captured = {}

        def fake_handler(ctx, arguments):
            captured.update(arguments)
            return {"content": [{"type": "text", "text":
                    json.dumps({"status": "NOT_APPLIED",
                                "cause": "fake"})}], "isError": False}

        with mock.patch.object(server, "handle_tool_call", fake_handler):
            code, _ = self.run_cli(
                ["keys", "--window-id", "11", "--chord", "return",
                 "--owner", "agent-a", "--lease-nonce", "abc123"],
                ctx=make_ctx())
        self.assertEqual(code, 0)
        self.assertEqual(captured.get("lease_nonce"), "abc123")
        self.assertEqual(captured.get("owner"), "agent-a")

    def test_allow_foreground_flag_maps(self):
        # M10 CLI gap (live proof red): --allow-foreground must be accepted
        # by the keys/press/scroll subparsers and reach the handler as a
        # real bool. It was missing from per_action, so the live CLI proof
        # died with "unrecognized arguments: --allow-foreground".
        captured = {}

        def fake_handler(ctx, arguments):
            captured.update(arguments)
            return {"content": [{"type": "text", "text":
                    json.dumps({"status": "NOT_APPLIED",
                                "cause": "fake"})}], "isError": False}

        for argv in (
                ["keys", "--window-id", "11", "--chord", "return",
                 "--owner", "agent-a", "--lease-nonce", "abc123",
                 "--allow-foreground"],
                ["press", "--window-id", "11", "--element-ref", "btn1",
                 "--owner", "agent-a", "--lease-nonce", "abc123",
                 "--allow-foreground"],
                ["scroll", "--window-id", "11", "--direction", "down",
                 "--amount", "3", "--owner", "agent-a",
                 "--lease-nonce", "abc123", "--allow-foreground"]):
            captured.clear()
            with mock.patch.object(server, "handle_tool_call",
                                   fake_handler):
                code, _ = self.run_cli(argv, ctx=make_ctx())
            self.assertEqual(code, 0, argv)
            self.assertIs(captured.get("allow_foreground"), True, argv)
            self.assertEqual(captured.get("action"), argv[0])

    def test_startup_refusal_exit_1(self):
        refuse = mock.patch.object(
            server, "build_context",
            side_effect=server.RefuseError("PIN_MISMATCH: test"))
        err = io.StringIO()
        with refuse, mock.patch.object(sys, "stderr", err):
            code = cli.main(["presence"])
        self.assertEqual(code, 1)
        self.assertIn("startup refused", err.getvalue())


if __name__ == "__main__":
    unittest.main()
