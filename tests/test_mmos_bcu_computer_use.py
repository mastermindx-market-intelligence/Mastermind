#!/usr/bin/env python3
"""Unit tests for tools/mmos_computer_use/server.py.

Pure unit tests: no screen access, no real peekaboo interaction, no network
beyond an in-process fake HTTP server. The peekaboo adapter is exercised
against a fake peekaboo shell script in a temp dir.

Run from the checkout root:
    python3 -m unittest tests/test_mmos_bcu_computer_use.py -v
"""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKOUT = os.path.dirname(HERE)
TOOL_DIR = os.path.join(CHECKOUT, "tools", "mmos_computer_use")
sys.path.insert(0, CHECKOUT)
sys.path.insert(0, TOOL_DIR)

import server as mmos  # noqa: E402


def write_runtime(tmp, bin_path, digest=None):
    if digest is None:
        digest = mmos.sha256_file(bin_path)
    path = os.path.join(tmp, "runtime.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"schema": mmos.RUNTIME_SCHEMA, "peekaboo_bin": bin_path,
                   "peekaboo_sha256": digest,
                   "input_strategy": "actionFirst"}, handle)
    return path


FAKE_PEEKABOO = r"""#!/bin/bash
# Fake peekaboo for unit tests. Logs argv (shell-quoted, one call per line),
# emits fixture JSON.
printf '%q ' "$@" >> "${FAKE_PEEKABOO_LOG:?}"
echo >> "${FAKE_PEEKABOO_LOG:?}"
ident="${FAKE_PEEKABOO_IDENTITY:-\"app\": \"UnknownApp\", \"bundle_id\": \"com.example.unknown\", \"window_title\": \"Untitled\"}"
ARGS=("$@")
has() {
  local needle="$1" a
  for a in "${ARGS[@]}"; do
    [ "$a" = "$needle" ] && return 0
  done
  return 1
}
# Optional extra snapshot elements (slice tests).
win_elem=""
chal_elem=""
if [ -n "${FAKE_PEEKABOO_WINDOW_ELEMENT:-}" ]; then
  win_elem=', {"id": "win1", "role": "Window", "label": "Untitled", "value": ""}'
fi
if [ -n "${FAKE_PEEKABOO_CHALLENGE:-}" ]; then
  chal_elem=', {"id": "chal1", "role": "StaticText", "label": "'"${FAKE_PEEKABOO_CHALLENGE}"'", "value": ""}'
fi
case "$1" in
  app)
    echo '{"success": true, "data": {"apps": [
      {"name": "TextEdit", "bundle_id": "com.apple.TextEdit", "pid": 101,
       "is_active": true, "is_hidden": false},
      {"name": "1Password", "bundle_id": "com.1password.1password", "pid": 102,
       "is_active": false, "is_hidden": false}]}}'
    ;;
  window)
    if [ -n "${FAKE_PEEKABOO_WINDOWS_JSON:-}" ]; then
      echo "{\"success\": true, \"data\": {\"windows\": ${FAKE_PEEKABOO_WINDOWS_JSON}}}"
    else
      echo '{"success": true, "data": {"windows": [
        {"window_id": 42, "title": "Untitled", "owner_pid": 101}]}}'
    fi
    ;;
  see)
    if has --tree; then
      echo "{\"success\": true, \"data\": {${ident}, \"snapshot_id\": \"snap-tree\", \"tree\": [
        {\"role\": \"Window\", \"label\": \"doc\", \"id\": \"w0\", \"children\": [
          {\"role\": \"Button\", \"label\": \"OK\", \"id\": \"btn1\", \"children\": []},
          {\"role\": \"TextField\", \"label\": \"Name\", \"id\": \"field1\", \"children\": []}]},
        {\"role\": \"Button\", \"label\": \"Cancel\", \"id\": \"btn2\", \"children\": []}],
        \"bounds\": {\"width\": 800, \"height\": 600}}}"
    elif has --path; then
      out=""
      prev=""
      for a in "${ARGS[@]}"; do
        [ "$prev" = "--path" ] && out="$a"
        prev="$a"
      done
      printf '\x89PNG\r\n\x1a\nFAKEPNGDATA' > "$out"
      echo "{\"success\": true, \"data\": {${ident}, \"bounds\": {\"width\": 800, \"height\": 600}}}"
    else
      echo "{\"success\": true, \"data\": {${ident}, \"snapshot_id\": \"snap-abc123\",
        \"ui_elements\": [
          {\"id\": \"btn1\", \"role\": \"Button\", \"label\": \"OK\", \"value\": \"\"},
          {\"id\": \"field1\", \"role\": \"TextField\", \"label\": \"Name\", \"value\": \"${FAKE_PEEKABOO_FIELD_VALUE:-}\"},
          {\"id\": \"scroll1\", \"role\": \"ScrollArea\", \"label\": \"Content\", \"value\": \"\"}${win_elem}${chal_elem}],
        \"coordinate_context\": {\"window_bounds\": {\"x\": 0, \"y\": 0,
          \"width\": 800, \"height\": 600}}}}"
    fi
    ;;
  paste)
    if [ -n "${FAKE_PEEKABOO_PASTE_FAIL:-}" ]; then
      echo '{"success": false, "errors": ["paste chord delivery failed mid-flight"]}'
      exit 0
    fi
    echo "{\"success\": true, \"data\": {\"result\": \"pasted\", \"clipboard_restored\": ${FAKE_PEEKABOO_CLIPBOARD_RESTORED:-true}}}"
    ;;
  action|set-value|press|scroll|click)
    if [ -n "${FAKE_PEEKABOO_FOREGROUND_REQUIRED:-}" ] && ! has --foreground; then
      echo '{"success": false, "errors": ["AXPress requires --foreground for this element"]}'
      exit 0
    fi
    echo "{\"success\": true, \"data\": {\"result\": \"$1 applied\"}}"
    ;;
  *)
    echo '{"success": false, "errors": ["unknown subcommand"]}' >&2
    exit 1
    ;;
esac
"""

IDENTITY_TEXTEDIT = '"app": "TextEdit", "bundle_id": "com.apple.TextEdit", ' \
    '"window_title": "Untitled"'
IDENTITY_ONepw = '"app": "1Password", "bundle_id": "com.1password.1password", ' \
    '"window_title": "1Password"'
IDENTITY_EMPTY = '"app": "", "bundle_id": "", "window_title": ""'


def _new_mmos_temp_dirs(tempdir, before):
    """New staging dirs left by THIS layer (prefix-filtered; the machine's
    shared temp dir may concurrently gain unrelated entries)."""
    return {name for name in set(os.listdir(tempdir)) - before
            if name.startswith("mmos-cu-")}

IOREG_FIXTURE = """+-o IOHIDSystem  <class IOHIDSystem, id 0x100000abc, registered, matched, active, busy 0 (0 ms), retain 8>
    {
      "HIDIdleTime" = 12345678901
      "HIDKeyboardScrollSwap" = No
    }
"""


def make_fake_peekaboo(tmp):
    bin_path = os.path.join(tmp, "peekaboo-fake.sh")
    with open(bin_path, "w", encoding="utf-8") as handle:
        handle.write(FAKE_PEEKABOO)
    os.chmod(bin_path, 0o755)
    return bin_path


def build_ctx(tmp, identity=IDENTITY_TEXTEDIT, deny=None, min_idle=8.0,
              presence_state={"human_idle_seconds": 30.0,
                              "human_active": False},
              presence_sequence=None, pacing_seconds=None):
    """A ToolContext wired to the fake peekaboo in `tmp`."""
    bin_path = make_fake_peekaboo(tmp)
    runtime = mmos.load_runtime(write_runtime(tmp, bin_path))
    adapter = mmos.PeekabooAdapter(runtime)
    deny = deny or mmos.DenyList(
        {"1password"}, {"com.1password.1password"}, [])
    lease = mmos.Lease(state_dir=os.path.join(tmp, "state"))
    presence = _StubPresence(min_idle, presence_state,
                             sequence=presence_sequence)
    vision = mmos.VisionClient(base_url="http://127.0.0.1:1", token="unused")
    pacer = mmos.Pacer(state_dir=os.path.join(tmp, "state"),
                       seconds=pacing_seconds)
    ctx = mmos.ToolContext(runtime, deny, lease, presence, adapter, vision,
                           pacer)
    os.environ["FAKE_PEEKABOO_IDENTITY"] = identity
    os.environ["FAKE_PEEKABOO_LOG"] = os.path.join(tmp, "calls.log")
    open(os.environ["FAKE_PEEKABOO_LOG"], "w").close()
    return ctx


class _StubPresence:
    """Presence with an injectable observation (no ioreg call).

    When `sequence` is given, gate_ok()/observe() consume one state per call
    in order and hold the last one — used to simulate a human becoming
    active mid slice sequence.
    """

    def __init__(self, min_idle=8.0, state=None, sequence=None):
        self.min_idle = min_idle
        self.state = state or {"human_idle_seconds": None,
                               "human_active": None}
        self._queue = [dict(s) for s in sequence] if sequence else []

    def _next(self):
        if len(self._queue) > 1:
            return self._queue.pop(0)
        if self._queue:
            return self._queue[0]
        return self.state

    def observe(self):
        return dict(self._next())

    def gate_ok(self):
        state = self._next()
        if state.get("human_active") is None:
            raise mmos.OpError("PRESENCE_UNKNOWN",
                               "HIDIdleTime not readable; ACT refused")
        return dict(state)


def read_calls(ctx):
    import shlex
    with open(os.environ["FAKE_PEEKABOO_LOG"], encoding="utf-8") as handle:
        return [shlex.split(line) for line in handle.read().splitlines()
                if line.strip()]


class TestLease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-test-")
        self.lease = mmos.Lease(state_dir=os.path.join(self.tmp, "state"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_acquire_status_release(self):
        self.assertFalse(self.lease.status()["held"])
        result = self.lease.acquire("agent-a", ttl_seconds=60)
        self.assertTrue(result["held"])
        status = self.lease.status()
        # FIX 4: owner is redacted in status output (first 8 chars + ellipsis;
        # a 7-char owner is not shortened, it only gains the ellipsis marker).
        self.assertEqual(status["owner"], "agent-a…")
        self.assertTrue(status["owner_redacted"])
        self.assertGreater(status["expires_in_seconds"], 0)
        self.assertEqual(self.lease.release("agent-a"), {"released": True})
        self.assertFalse(self.lease.status()["held"])

    def test_second_owner_refused_while_held(self):
        self.lease.acquire("agent-a", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.acquire("agent-b", ttl_seconds=60)
        self.assertEqual(caught.exception.code, "LEASE_HELD")

    def test_expired_lease_taken_over(self):
        self.lease.acquire("agent-a", ttl_seconds=5)
        with open(self.lease.lease_path, "r", encoding="utf-8") as handle:
            lease = json.load(handle)
        lease["expires_at"] = time.time() - 1  # crashed holder
        with open(self.lease.lease_path, "w", encoding="utf-8") as handle:
            json.dump(lease, handle)
        result = self.lease.acquire("agent-b", ttl_seconds=60)
        self.assertTrue(result["took_over"])
        self.assertEqual(self.lease.status()["owner"], "agent-b…")

    def test_release_by_wrong_owner_refused(self):
        self.lease.acquire("agent-a", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.release("agent-b")
        self.assertEqual(caught.exception.code, "LEASE_NOT_OWNER")

    def test_require_and_renew_renews_expiry(self):
        self.lease.acquire("agent-a", ttl_seconds=5)
        with open(self.lease.lease_path) as handle:
            before = json.load(handle)
        self.lease.require_and_renew("agent-a", ttl_seconds=60)
        with open(self.lease.lease_path) as handle:
            after = json.load(handle)
        self.assertGreater(after["expires_at"], before["expires_at"])
        self.assertEqual(after["owner"], "agent-a")

    def test_require_by_non_owner_not_held(self):
        self.lease.acquire("agent-a", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.require_and_renew("agent-b")
        self.assertEqual(caught.exception.code, "LEASE_NOT_HELD")

    def test_ttl_bounds_enforced(self):
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.acquire("agent-a", ttl_seconds=1)
        self.assertEqual(caught.exception.code, "LEASE_TTL_INVALID")


class TestPresenceParser(unittest.TestCase):
    def test_parses_nanoseconds_to_seconds(self):
        idle = mmos.parse_ioreg_idle(IOREG_FIXTURE)
        self.assertAlmostEqual(idle, 12.345678901, places=6)

    def test_missing_field_returns_none(self):
        self.assertIsNone(mmos.parse_ioreg_idle("no HIDIdleTime here"))
        self.assertIsNone(mmos.parse_ioreg_idle(""))

    def test_active_below_threshold(self):
        presence = mmos.Presence(min_idle_seconds=8.0)
        self.assertEqual(presence.min_idle, 8.0)


class TestDenyList(unittest.TestCase):
    def _deny(self, tmp, extra=None):
        path = os.path.join(tmp, "deny.json")
        data = dict(mmos.DEFAULT_DENY)
        data["schema"] = mmos.DENY_SCHEMA
        if extra:
            data.update(extra)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return mmos.DenyList.load(path)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-deny-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_name_match(self):
        deny = self._deny(self.tmp)
        self.assertEqual(deny.matches("Keychain Access", None, None),
                         "app_name")
        self.assertEqual(deny.matches("1password", None, None), "app_name")
        self.assertEqual(deny.matches("System Settings", None, None),
                         "app_name")

    def test_default_bundle_match(self):
        deny = self._deny(self.tmp)
        self.assertEqual(deny.matches(None, "com.1password.1password", None),
                         "bundle_id")
        self.assertEqual(deny.matches(None, "com.apple.Passwords", None),
                         "bundle_id")

    def test_nonlisted_app_passes(self):
        deny = self._deny(self.tmp)
        self.assertIsNone(deny.matches("TextEdit", "com.apple.TextEdit",
                                       "Untitled"))

    def test_extra_entries_and_title_regex(self):
        deny = self._deny(self.tmp, extra={
            "extra_app_names": ["Secrets Editor"],
            "extra_bundle_ids": ["com.example.vault"],
            "extra_title_regexes": ["master.?password"]})
        self.assertEqual(deny.matches("secrets editor", None, None),
                         "app_name")
        self.assertEqual(deny.matches(None, "com.example.vault", None),
                         "bundle_id")
        self.assertEqual(deny.matches(None, None, "Enter Master Password!"),
                         "title_regex")

    def test_bad_regex_refused_at_load(self):
        with open(os.path.join(self.tmp, "deny.json"), "w") as handle:
            json.dump({"schema": mmos.DENY_SCHEMA,
                       "extra_title_regexes": ["([bad"]}, handle)
        with self.assertRaises(mmos.RefuseError):
            mmos.DenyList.load(os.path.join(self.tmp, "deny.json"))


class TestReceiptBuilder(unittest.TestCase):
    def test_applied_receipt_shape(self):
        receipt = mmos.receipt("press", 42, "btn1", "APPLIED",
                               observed="AXPress applied")
        self.assertEqual(receipt["target"],
                         {"op": "press", "window_id": 42, "element_ref": "btn1"})
        self.assertEqual(receipt["status"], "APPLIED")
        self.assertNotIn("cause", receipt)
        self.assertEqual(receipt["observed"], "AXPress applied")

    def test_cause_code_and_bounded_detail(self):
        cause = mmos.OpError("LEASE_NOT_HELD", "x" * 500)
        receipt = mmos.receipt("press", 42, None, "NOT_APPLIED", cause=cause)
        self.assertEqual(receipt["status"], "NOT_APPLIED")
        self.assertTrue(receipt["cause"].startswith("LEASE_NOT_HELD: "))
        self.assertLessEqual(len(receipt["cause"]),
                             len("LEASE_NOT_HELD: ") + mmos.MAX_ERROR_TEXT)


class TestRuntimePin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-pin-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_pin_loads(self):
        bin_path = make_fake_peekaboo(self.tmp)
        runtime = mmos.load_runtime(write_runtime(self.tmp, bin_path))
        self.assertEqual(runtime["peekaboo_bin"], bin_path)
        self.assertEqual(runtime["input_strategy"], "actionFirst")

    def test_mismatched_digest_refused(self):
        bin_path = make_fake_peekaboo(self.tmp)
        path = write_runtime(self.tmp, bin_path,
                             digest="0" * 64)
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.load_runtime(path)
        self.assertEqual(caught.exception.code, "PIN_MISMATCH")

    def test_missing_binary_refused(self):
        path = write_runtime(self.tmp, os.path.join(self.tmp, "nope.sh"),
                             digest="0" * 64)
        with self.assertRaises(mmos.RefuseError):
            mmos.load_runtime(path)

    def test_wrong_schema_refused(self):
        bin_path = make_fake_peekaboo(self.tmp)
        path = os.path.join(self.tmp, "runtime.json")
        with open(path, "w") as handle:
            json.dump({"schema": "other/v1", "peekaboo_bin": bin_path,
                       "peekaboo_sha256": mmos.sha256_file(bin_path)}, handle)
        with self.assertRaises(mmos.RefuseError):
            mmos.load_runtime(path)


class TestPeekabooAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-adapter-")
        self.ctx = build_ctx(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_remote_always_passed_and_bridge_socket_never(self):
        self.ctx.adapter.list_apps()
        self.ctx.adapter.list_windows("TextEdit")
        calls = read_calls(self.ctx)
        self.assertEqual(len(calls), 2)
        for argv in calls:
            self.assertIn("--no-remote", argv)
            self.assertNotIn("--bridge-socket", argv)
            self.assertIn("--input-strategy", argv)
            self.assertEqual(argv[argv.index("--input-strategy") + 1],
                             "actionFirst")

    def test_list_apps(self):
        apps = self.ctx.adapter.list_apps()
        names = [app["name"] for app in apps]
        self.assertIn("TextEdit", names)
        self.assertIn("1Password", names)

    def test_list_windows(self):
        windows = self.ctx.adapter.list_windows("TextEdit")
        self.assertEqual(windows[0]["window_id"], 42)
        self.assertEqual(windows[0]["title"], "Untitled")

    def test_inspect_renders_bounded_tree(self):
        meta = self.ctx.adapter.inspect_window(42)
        tree = mmos.render_tree(meta)
        self.assertIn("Button: OK", tree)
        self.assertIn("[@btn1]", tree)
        self.assertLessEqual(len(tree.splitlines()), mmos.MAX_TREELINES)

    def test_capture_returns_png_bytes(self):
        png, meta, staging = self.ctx.adapter.capture_window(42, ocr=False)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIsNotNone(staging)
        shutil.rmtree(staging, ignore_errors=True)

    def test_single_shot_no_retry(self):
        # Exactly one subprocess dispatch per operation, verified by the
        # fake peekaboo's argv log.
        ctx = self.ctx
        ctx.adapter.act(["action", "AXPress", "--on", "btn1",
                         "--snapshot", "snap-abc123", "--json"])
        self.assertEqual(len(read_calls(ctx)), 1)
        ctx.adapter.act(["scroll", "--direction", "down", "--amount", "3",
                         "--snapshot", "snap-abc123", "--json"])
        calls = read_calls(ctx)
        self.assertEqual(len(calls), 2)  # still one per act, no retries

    def test_act_uses_action_only_strategy(self):
        self.ctx.adapter.act(["action", "AXPress", "--on", "btn1",
                              "--snapshot", "snap-abc123", "--json"])
        argv = read_calls(self.ctx)[0]
        self.assertEqual(argv[argv.index("--input-strategy") + 1],
                         "actionOnly")

    def test_snapshot_window_returns_elements_and_bounds(self):
        snap = self.ctx.adapter.snapshot_window(42)
        self.assertEqual(mmos.snapshot_id_of(snap), "snap-abc123")
        self.assertEqual(len(mmos.snapshot_elements(snap)), 3)
        self.assertEqual(mmos.window_bounds(snap), (800.0, 600.0))
        argv = read_calls(self.ctx)[0]
        self.assertEqual(argv[:4], ["see", "--window-id", "42", "--json"])
        self.assertNotIn("--tree", argv)
        self.assertNotIn("--path", argv)

    def test_cli_failure_raises_bounded(self):
        with self.assertRaises(mmos.OpError) as caught:
            self.ctx.adapter.run_json(["bogus"], 5)
        self.assertEqual(caught.exception.code, "CLI_ERROR")


class TestWindowBoundValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-win-")
        self.ctx = build_ctx(self.tmp)
        self.ctx.lease.acquire("agent-a", ttl_seconds=60)

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_window_id_refused(self):
        result = mmos.handle_tool_call(self.ctx, {"action": "inspect"})
        self.assertTrue(result["isError"])
        self.assertIn("WINDOW_ID_REQUIRED",
                      result["content"][0]["text"])

    def test_screen_wide_params_absent_from_schema(self):
        schema = json.dumps(mmos.TOOL_SCHEMA)
        for forbidden in ("screen", "display", "all_windows", "region",
                          "screen_index"):
            self.assertNotIn(forbidden, schema)
        self.assertNotIn("all", mmos.ACTIONS)

    def test_pointer_click_requires_coords(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "pointer_click", "window_id": 42,
            "owner": "agent-a"})
        self.assertIn("COORDS_REQUIRED", result["content"][0]["text"])

    def test_pointer_click_outside_window_bounds(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "pointer_click", "window_id": 42, "x": 2000, "y": 10,
            "owner": "agent-a"})
        self.assertIn("POINT_OUTSIDE_WINDOW", result["content"][0]["text"])

    def test_pointer_click_inside_bounds_applied(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        # Coordinate click is the last resort and keeps --window-id so the
        # point stays window-relative; it still carries the fresh snapshot.
        click = [c for c in read_calls(self.ctx) if c[0] == "click"][0]
        self.assertIn("--snapshot", click)
        self.assertIn("--window-id", click)
        self.assertNotIn("--foreground", click)


class TestActGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-act-")

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def test_act_without_lease_not_applied(self):
        ctx = build_ctx(self.tmp)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_NOT_HELD", payload["cause"])

    def test_act_deny_listed_refused_before_dispatch(self):
        ctx = self._ctx(identity=IDENTITY_ONepw)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("DENY_LISTED", payload["cause"])
        # No AX dispatch was ever made: only the read-only identity probe.
        calls = read_calls(ctx)
        self.assertTrue(all(call[0] != "action" for call in calls))

    def test_act_while_human_active_not_applied(self):
        ctx = self._ctx(presence_state={"human_idle_seconds": 1.0,
                                        "human_active": True})
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "Return",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE", payload["cause"])

    def test_act_renews_lease(self):
        ctx = self._ctx()
        with open(ctx.lease.lease_path) as handle:
            before = json.load(handle)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        with open(ctx.lease.lease_path) as handle:
            after = json.load(handle)
        self.assertGreaterEqual(after["expires_at"], before["expires_at"])

    def test_global_chord_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "cmd+space",
            "owner": "agent-a"})
        self.assertIn("CHORD_GLOBAL", result["content"][0]["text"])

    def test_multi_chord_sequence_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "ctrl+a Delete",
            "owner": "agent-a"})
        self.assertIn("CHORD_INVALID", result["content"][0]["text"])

    def test_window_identity_unknown_refused(self):
        ctx = self._ctx(identity=IDENTITY_EMPTY)
        result = mmos.handle_tool_call(ctx, {
            "action": "set_text", "window_id": 42, "element_ref": "field1",
            "text": "hello", "owner": "agent-a"})
        self.assertIn("WINDOW_IDENTITY_UNKNOWN", result["content"][0]["text"])

    def test_dispatch_timeout_is_effect_unknown(self):
        ctx = self._ctx()
        # Point the adapter's internal timeout at zero so the fake script is
        # killed mid-run; outcome unconfirmable => EFFECT_UNKNOWN, no retry.
        ctx.adapter.act = None  # guard against accidental direct use
        original_run_json = mmos.PeekabooAdapter.run_json

        def slow_run_json(self_adapter, args, timeout):  # noqa: ARG001
            raise mmos.OpError("DISPATCH_TIMEOUT", "peekaboo action exceeded 0s")

        mmos.PeekabooAdapter.run_json = slow_run_json
        try:
            result = mmos.handle_tool_call(ctx, {
                "action": "press", "window_id": 42, "element_ref": "btn1",
                "owner": "agent-a"})
        finally:
            mmos.PeekabooAdapter.run_json = original_run_json
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN")
        self.assertIn("DISPATCH_TIMEOUT", payload["cause"])


class TestActDispatch(unittest.TestCase):
    """The proven act shape: own fresh `see` snapshot, then ONE background
    dispatch with --snapshot/--on and no --foreground/--app/--window-id."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-dispatch-")
        os.environ.pop("FAKE_PEEKABOO_FOREGROUND_REQUIRED", None)

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_FOREGROUND_REQUIRED", None)
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _act_calls(self, ctx):
        return [c for c in read_calls(ctx)
                if c[0] in ("action", "set-value", "press", "scroll", "click")]

    def _assert_background_shape(self, argv, require_on=True):
        self.assertIn("--snapshot", argv)
        self.assertEqual(argv[argv.index("--snapshot") + 1], "snap-abc123")
        if require_on:
            self.assertIn("--on", argv)
        self.assertNotIn("--foreground", argv)
        self.assertNotIn("--app", argv)
        self.assertNotIn("--pid", argv)
        self.assertNotIn("--window-id", argv)
        self.assertIn("--json", argv)
        self.assertIn("--no-remote", argv)
        self.assertEqual(argv[argv.index("--input-strategy") + 1],
                         "actionOnly")

    def test_press_dispatches_on_snapshot(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertNotIn("foreground", payload)
        self.assertIn("snapshot=snap-abc123", payload["observed"])
        self.assertIn("role=Button", payload["observed"])
        self.assertIn("label=OK", payload["observed"])
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self._assert_background_shape(calls[0])
        self.assertEqual(calls[0][:2], ["action", "AXPress"])
        self.assertEqual(calls[0][calls[0].index("--on") + 1], "btn1")

    def test_set_text_dispatches_on_snapshot(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "set_text", "window_id": 42, "element_ref": "field1",
            "text": "hello", "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self._assert_background_shape(calls[0])
        self.assertEqual(calls[0][0], "set-value")
        self.assertEqual(calls[0][calls[0].index("--value") + 1], "hello")
        self.assertEqual(calls[0][calls[0].index("--on") + 1], "field1")

    def test_keys_dispatches_on_snapshot(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "Return",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        # A chord targets no element: the fresh exact-window snapshot alone
        # authorizes background delivery (peekaboo refuses targetless press).
        self._assert_background_shape(calls[0], require_on=False)
        self.assertEqual(calls[0][:2], ["press", "Return"])

    def test_scroll_targets_scrollable_element(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "scroll", "window_id": 42, "direction": "down",
            "amount": 3, "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self._assert_background_shape(calls[0])
        self.assertEqual(calls[0][calls[0].index("--on") + 1], "scroll1")

    def test_pointer_click_prefers_element_target(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42,
            "element_ref": "btn1", "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self._assert_background_shape(calls[0])
        self.assertEqual(calls[0][0], "click")
        self.assertEqual(calls[0][calls[0].index("--on") + 1], "btn1")

    def test_unknown_element_ref_refused_without_dispatch(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "nope",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("ELEMENT_NOT_FOUND", payload["cause"])
        self.assertEqual(self._act_calls(ctx), [])

    def test_foreground_required_is_not_applied_and_not_retried(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("FOREGROUND_REQUIRED", payload["cause"])
        self.assertNotIn("foreground", payload)
        # Exactly one act dispatch: the refusal is terminal, never escalated.
        self.assertEqual(len(self._act_calls(ctx)), 1)
        self.assertNotIn("--foreground", self._act_calls(ctx)[0])

    def test_allow_foreground_opt_in_dispatches_once_with_flag(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        calls = self._act_calls(ctx)
        # Two dispatches total: the refused background act, then ONE new
        # foreground act. Neither is a retry of the other.
        self.assertEqual(len(calls), 2)
        self.assertNotIn("--foreground", calls[0])
        self.assertIn("--foreground", calls[1])
        self.assertIn("--snapshot", calls[1])

    def test_allow_foreground_without_lease_not_applied(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = build_ctx(self.tmp)  # no lease acquired
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_NOT_HELD", payload["cause"])
        self.assertEqual(self._act_calls(ctx), [])

    def test_allow_foreground_while_human_active_not_applied(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = self._ctx(presence_state={"human_idle_seconds": 1.0,
                                        "human_active": True})
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE", payload["cause"])
        self.assertEqual(self._act_calls(ctx), [])

    def test_allow_foreground_ignored_when_background_succeeds(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertNotIn("foreground", payload)
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--foreground", calls[0])

    def test_allow_foreground_defaults_false_in_schema(self):
        prop = mmos.TOOL_SCHEMA["properties"]["allow_foreground"]
        self.assertEqual(prop["type"], "boolean")
        self.assertFalse(prop["default"])


class TestCaptureKeepPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-cap-")
        self.ctx = build_ctx(self.tmp)
        self.scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(self.scratch, exist_ok=True)
        os.environ["MMOS_CU_SCRATCH"] = self.scratch
        self.ctx.lease.acquire("agent-a", ttl_seconds=60)

    def tearDown(self):
        os.environ.pop("MMOS_CU_SCRATCH", None)
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_keep_path_outside_scratch_refused(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": False,
            "keep_path": "/tmp/elsewhere.png", "owner": "agent-a"})
        self.assertIn("KEEP_PATH_OUTSIDE_SCRATCH", result["content"][0]["text"])
        # Refusal happens BEFORE any capture dispatch.
        calls = read_calls(self.ctx)
        self.assertEqual(calls, [])

    def test_keep_path_inside_scratch_saved(self):
        keep = os.path.join(self.scratch, "shot.png")
        result = mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": False,
            "keep_path": keep, "owner": "agent-a"})
        self.assertFalse(result["isError"])
        with open(keep, "rb") as handle:
            self.assertTrue(handle.read().startswith(b"\x89PNG"))
        self.assertEqual(os.stat(keep).st_mode & 0o777, 0o600)

    def test_keep_path_without_scratch_env_refused(self):
        os.environ.pop("MMOS_CU_SCRATCH", None)
        result = mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": False,
            "keep_path": os.path.join(self.tmp, "shot.png"),
            "owner": "agent-a"})
        self.assertIn("KEEP_PATH_NO_SCRATCH", result["content"][0]["text"])

    def test_capture_without_keep_path_writes_no_persistent_file(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": False,
            "owner": "agent-a"})
        self.assertFalse(result["isError"])
        self.assertEqual(os.listdir(self.scratch), [])

    def test_capture_no_staging_dirs_left_behind(self):
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": True,
            "owner": "agent-a"})
        after = set(os.listdir(tempdir))
        self.assertEqual(_new_mmos_temp_dirs(tempdir, before), set())

    def test_apps_filters_denied_apps(self):
        result = mmos.handle_tool_call(self.ctx, {"action": "apps"})
        payload = json.loads(result["content"][0]["text"])
        names = [app["name"] for app in payload["apps"]]
        self.assertIn("TextEdit", names)
        self.assertNotIn("1Password", names)
        textedit = next(app for app in payload["apps"]
                        if app["name"] == "TextEdit")
        self.assertEqual(textedit["windows"][0]["window_id"], 42)

    def test_windows_deny_listed_app_refused(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "windows", "app": "1Password"})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])


class FakeVisionHandler(BaseHTTPRequestHandler):
    """Records headers/body, returns an Anthropic-protocol response."""

    seen = {}

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)
        FakeVisionHandler.seen = {
            "path": self.path,
            "x_api_key": self.headers.get("x-api-key"),
            "version": self.headers.get("anthropic-version"),
            "body": json.loads(body.decode("utf-8")),
        }
        response = {"content": [{"type": "text", "text": json.dumps({
            "answer": "The OK button is at the top right.",
            "elements": [{"label": "OK", "x": 800, "y": 50},
                         {"label": "Cancel", "x": 700, "y": 50}]})}]}
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence
        pass


class TestVisionClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-vision-")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVisionHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.old_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "test-vision-token"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.old_token is None:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        else:
            os.environ["ANTHROPIC_AUTH_TOKEN"] = self.old_token
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ask_round_trip(self):
        client = mmos.VisionClient(base_url="http://127.0.0.1:%d" % self.port)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
            "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        result = client.ask(png, "Where is the OK button?")
        self.assertEqual(result["model"], mmos.DEFAULT_VISION_MODEL)
        self.assertIn("OK button", result["answer"])
        self.assertEqual(result["elements"][0]["label"], "OK")
        self.assertEqual(FakeVisionHandler.seen["x_api_key"],
                         "test-vision-token")
        self.assertEqual(FakeVisionHandler.seen["path"], "/v1/messages")
        self.assertEqual(FakeVisionHandler.seen["version"], "2023-06-01")
        body = FakeVisionHandler.seen["body"]
        self.assertEqual(body["model"], mmos.DEFAULT_VISION_MODEL)
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["media_type"], "image/png")

    def test_ask_accepts_small_hints(self):
        client = mmos.VisionClient(base_url="http://127.0.0.1:%d" % self.port)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
            "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        result = client.ask(png, "Where is the OK button?",
                            ["OK button", "Cancel button"])
        self.assertEqual(result["elements"][0]["label"], "OK")

    def test_missing_token_refused_without_network(self):
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        client = mmos.VisionClient(base_url="http://127.0.0.1:%d" % self.port)
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "question")
        self.assertEqual(caught.exception.code, "VISION_UNCONFIGURED")

    def test_vision_ask_no_file_writes_and_staging_cleaned(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port)
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?", "owner": "agent-a"})
        self.assertFalse(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["elements"][0]["label"], "OK")
        self.assertEqual(_new_mmos_temp_dirs(tempdir, before), set())
        # Image bytes never persisted anywhere in the tool dir.
        self.assertEqual(sorted(os.listdir(self.tmp)),
                         ["calls.log", "peekaboo-fake.sh", "runtime.json",
                          "state"])

    def test_image_never_in_result_text(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port)
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?", "owner": "agent-a"})
        self.assertNotIn("FAKEPNGDATA", result["content"][0]["text"])


class TestMcpFraming(unittest.TestCase):
    """Round trip over pipes against the real server process."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-mcp-")
        bin_path = make_fake_peekaboo(self.tmp)
        os.environ["FAKE_PEEKABOO_IDENTITY"] = IDENTITY_TEXTEDIT
        log = os.path.join(self.tmp, "calls.log")
        open(log, "w").close()
        deny = os.path.join(self.tmp, "deny.json")
        with open(deny, "w") as handle:
            json.dump(mmos.DEFAULT_DENY, handle)
        self.env = dict(os.environ)
        self.env.update({
            "MMOS_CU_RUNTIME": write_runtime(self.tmp, bin_path),
            "MMOS_CU_STATE_DIR": os.path.join(self.tmp, "state"),
            "MMOS_CU_DENY": deny,
            "FAKE_PEEKABOO_LOG": log,
            "FAKE_PEEKABOO_IDENTITY": IDENTITY_TEXTEDIT,
        })
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(TOOL_DIR, "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self.env, text=True, bufsize=1)

    def tearDown(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        err = self.proc.stderr.read()
        self.proc.stderr.close()
        self.assertIn("ready", err)
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rpc(self, payload):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line.strip())
        return json.loads(line)

    def test_initialize_tools_list_and_call(self):
        response = self._rpc({"id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18"}})
        self.assertEqual(response["id"], 1)
        self.assertEqual(
            response["result"]["serverInfo"]["name"], mmos.SERVER_NAME)
        response = self._rpc({"id": 2, "method": "tools/list", "params": {}})
        tools = response["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "mmos_computer_use")
        actions = tools[0]["inputSchema"]["properties"]["action"]["enum"]
        self.assertIn("inspect", actions)
        self.assertIn("lease_acquire", actions)
        response = self._rpc({"id": 3, "method": "tools/call", "params": {
            "name": "mmos_computer_use",
            "arguments": {"action": "apps"}}})
        payload = json.loads(response["result"]["content"][0]["text"])
        names = [app["name"] for app in payload["apps"]]
        self.assertIn("TextEdit", names)
        self.assertNotIn("1Password", names)

    def test_lease_round_trip(self):
        response = self._rpc({"id": 4, "method": "tools/call", "params": {
            "name": "mmos_computer_use", "arguments": {
                "action": "lease_acquire", "owner": "framing-test",
                "ttl_seconds": 60}}})
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        response = self._rpc({"id": 5, "method": "tools/call", "params": {
            "name": "mmos_computer_use", "arguments": {
                "action": "lease_status"}}})
        payload = json.loads(response["result"]["content"][0]["text"])
        # FIX 4: the full owner id never appears in lease_status output.
        self.assertNotIn("framing-test", json.dumps(payload))
        self.assertEqual(payload["owner"], "framing-…")
        self.assertTrue(payload["owner_redacted"])
        response = self._rpc({"id": 6, "method": "tools/call", "params": {
            "name": "mmos_computer_use", "arguments": {
                "action": "lease_release", "owner": "framing-test"}}})
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")

    def test_parse_error_and_unknown_method(self):
        self.proc.stdin.write("not json\n")
        self.proc.stdin.flush()
        response = json.loads(self.proc.stdout.readline())
        self.assertEqual(response["error"]["code"], -32700)
        response = self._rpc({"id": 7, "method": "bogus/method"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_and_unknown_action(self):
        response = self._rpc({"id": 8, "method": "tools/call", "params": {
            "name": "other_tool", "arguments": {}}})
        self.assertTrue(response["result"]["isError"])
        response = self._rpc({"id": 9, "method": "tools/call", "params": {
            "name": "mmos_computer_use", "arguments": {
                "action": "reboot_machine"}}})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("UNKNOWN_ACTION",
                      response["result"]["content"][0]["text"])


class TestServeInProcess(unittest.TestCase):
    def test_serve_via_stringio(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-serve-")
        try:
            bin_path = make_fake_peekaboo(tmp)
            os.environ["FAKE_PEEKABOO_IDENTITY"] = IDENTITY_TEXTEDIT
            log = os.path.join(tmp, "calls.log")
            open(log, "w").close()
            old_env = {k: os.environ.get(k)
                       for k in ("MMOS_CU_RUNTIME", "MMOS_CU_STATE_DIR",
                                 "MMOS_CU_DENY", "FAKE_PEEKABOO_LOG",
                                 "FAKE_PEEKABOO_IDENTITY")}
            os.environ["MMOS_CU_RUNTIME"] = write_runtime(tmp, bin_path)
            os.environ["MMOS_CU_STATE_DIR"] = os.path.join(tmp, "state")
            os.environ["FAKE_PEEKABOO_LOG"] = log
            requests = io.StringIO(json.dumps({
                "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"}}) + "\n" +
                json.dumps({"id": 2, "method": "ping"}) + "\n" +
                json.dumps({"id": 3, "method": "tools/call", "params": {
                    "name": "mmos_computer_use", "arguments": {
                        "action": "windows", "app": "TextEdit"}}}) + "\n" +
                json.dumps({"id": 4, "method": "tools/call", "params": {
                    "name": "mmos_computer_use", "arguments": {
                        "action": "windows", "app": "1Password"}}}) + "\n")
            captured = io.StringIO()
            rc = mmos.serve(stdin=requests, stdout=captured)
            self.assertEqual(rc, 0)
            lines = [json.loads(line) for line in
                     captured.getvalue().splitlines() if line.strip()]
            self.assertEqual(lines[0]["result"]["protocolVersion"],
                             "2025-06-18")
            self.assertEqual(lines[1]["result"], {})
            payload = json.loads(lines[2]["result"]["content"][0]["text"])
            self.assertEqual(payload["windows"][0]["window_id"], 42)
            payload = json.loads(lines[3]["result"]["content"][0]["text"])
            self.assertIn("DENY_LISTED", payload["cause"])
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
            shutil.rmtree(tmp, ignore_errors=True)


class TestSlicePresenceDefaults(unittest.TestCase):
    """180 s is the single default idle threshold for ALL acts (slice and
    non-slice); env and runtime.json keys configure it."""

    def setUp(self):
        self.saved = os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        else:
            os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = self.saved

    def test_default_is_180_seconds(self):
        self.assertEqual(mmos.DEFAULT_MIN_IDLE_SECONDS, 180.0)
        self.assertEqual(mmos.Presence().min_idle, 180.0)

    def test_env_override(self):
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "45"
        self.assertEqual(mmos.Presence().min_idle, 45.0)

    def test_runtime_key_override(self):
        presence = mmos.Presence(runtime={"presence_min_idle_seconds": 90})
        self.assertEqual(presence.min_idle, 90.0)

    def test_env_beats_runtime_key(self):
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "45"
        presence = mmos.Presence(runtime={"presence_min_idle_seconds": 90})
        self.assertEqual(presence.min_idle, 45.0)

    def test_runtime_rejects_bad_presence_value(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-rt-")
        try:
            bin_path = make_fake_peekaboo(tmp)
            path = os.path.join(tmp, "runtime.json")
            with open(path, "w") as handle:
                json.dump({"schema": mmos.RUNTIME_SCHEMA,
                           "peekaboo_bin": bin_path,
                           "peekaboo_sha256": mmos.sha256_file(bin_path),
                           "presence_min_idle_seconds": "soon"}, handle)
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.load_runtime(path)
            self.assertEqual(caught.exception.code,
                             "RUNTIME_PRESENCE_MIN_IDLE_SECONDS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPacer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-pacer-")
        self.saved = os.environ.pop("MMOS_CU_PACING_SECONDS", None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("MMOS_CU_PACING_SECONDS", None)
        else:
            os.environ["MMOS_CU_PACING_SECONDS"] = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pacer(self, **kwargs):
        return mmos.Pacer(state_dir=os.path.join(self.tmp, "state"), **kwargs)

    def test_check_passes_with_no_record(self):
        self._pacer().check(42)

    def test_record_then_wait_then_allowed(self):
        pacer = self._pacer(seconds=180)
        pacer.record(42)
        with self.assertRaises(mmos.OpError) as caught:
            pacer.check(42)
        self.assertEqual(caught.exception.code, "PACING_WAIT")
        self.assertIn("remaining", caught.exception.detail)
        # Simulate the interval elapsing by rewinding the recorded time.
        with open(pacer.path) as handle:
            data = json.load(handle)
        data["42"] = time.time() - 181
        with open(pacer.path, "w") as handle:
            json.dump(data, handle)
        pacer.check(42)  # allowed now

    def test_pacing_is_per_window(self):
        pacer = self._pacer()
        pacer.record(42)
        pacer.check(43)  # a different window is unaffected

    def test_env_seconds(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "5"
        self.assertEqual(self._pacer().seconds, 5.0)

    def test_runtime_seconds(self):
        pacer = self._pacer(runtime={"pacing_seconds": 60})
        self.assertEqual(pacer.seconds, 60.0)

    def test_env_beats_runtime_seconds(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "5"
        pacer = self._pacer(runtime={"pacing_seconds": 60})
        self.assertEqual(pacer.seconds, 5.0)

    def test_default_is_180_seconds(self):
        self.assertEqual(mmos.DEFAULT_PACING_SECONDS, 180.0)
        self.assertEqual(self._pacer().seconds, 180.0)


class TestSliceFront(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-front-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOW_ELEMENT",
                    "FAKE_PEEKABOO_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _front(self, ctx, **extra):
        args = {"action": "slice_front", "app": "TextEdit", "owner": "agent-a"}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_raises_window_with_single_foreground_raise(self):
        os.environ["FAKE_PEEKABOO_WINDOW_ELEMENT"] = "1"
        ctx = self._ctx()
        payload = json.loads(self._front(ctx, window_id=42)["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        self.assertEqual(payload["target"]["window_id"], 42)
        self.assertIn("window_id=42", payload["observed"])
        self.assertIn("title=Untitled", payload["observed"])
        raises = [c for c in read_calls(ctx) if c[0] == "action"]
        # ONE foreground dispatch; never attempted in the background first.
        self.assertEqual(len(raises), 1)
        argv = raises[0]
        self.assertEqual(argv[:2], ["action", "AXRaise"])
        self.assertIn("--foreground", argv)
        self.assertIn("--snapshot", argv)
        self.assertEqual(argv[argv.index("--on") + 1], "win1")
        self.assertNotIn("--app", argv)
        self.assertNotIn("--pid", argv)
        self.assertNotIn("--window-id", argv)

    def test_title_substring_selection(self):
        ctx = self._ctx()
        payload = json.loads(self._front(ctx, title="Unti")["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertEqual(payload["target"]["window_id"], 42)
        self.assertEqual(payload["target"]["title_selector"], "Unti")

    def test_ambiguous_title_refused(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = json.dumps([
            {"window_id": 42, "title": "Untitled A"},
            {"window_id": 43, "title": "Untitled B"}])
        ctx = self._ctx()
        result = self._front(ctx, title="Untitled")
        self.assertIn("SLICE_TARGET_AMBIGUOUS", result["content"][0]["text"])

    def test_no_match_refused(self):
        ctx = self._ctx()
        result = self._front(ctx, title="zzz-not-there")
        self.assertIn("SLICE_TARGET_NOT_FOUND", result["content"][0]["text"])

    def test_both_selectors_refused(self):
        ctx = self._ctx()
        result = self._front(ctx, window_id=42, title="Unti")
        self.assertIn("SLICE_TARGET_AMBIGUOUS", result["content"][0]["text"])

    def test_deny_listed_app_refused_before_any_dispatch(self):
        ctx = self._ctx(identity=IDENTITY_ONepw)
        result = self._front(ctx, window_id=42, app="1Password")
        self.assertIn("DENY_LISTED", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_lease_required(self):
        ctx = build_ctx(self.tmp)
        result = self._front(ctx, window_id=42)
        self.assertIn("LEASE_NOT_HELD", result["content"][0]["text"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "action"], [])

    def test_human_active_at_start_refused(self):
        ctx = self._ctx(presence_state={"human_idle_seconds": 1.0,
                                        "human_active": True})
        result = self._front(ctx, window_id=42)
        self.assertIn("HUMAN_ACTIVE", result["content"][0]["text"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "action"], [])


class TestSliceClick(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-click-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def test_element_click_dispatches_foreground(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        clicks = [c for c in read_calls(ctx) if c[0] == "click"]
        self.assertEqual(len(clicks), 1)
        argv = clicks[0]
        self.assertIn("--snapshot", argv)
        self.assertIn("--on", argv)
        self.assertEqual(argv[argv.index("--on") + 1], "btn1")
        self.assertIn("--foreground", argv)
        self.assertNotIn("--app", argv)
        self.assertNotIn("--window-id", argv)

    def test_coordinate_click_keeps_window_id_and_foreground(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        argv = [c for c in read_calls(ctx) if c[0] == "click"][0]
        # --window-id is kept ONLY in the coordinate form (--at is global
        # without a window target); --foreground added for the slice op.
        self.assertIn("--window-id", argv)
        self.assertEqual(argv[argv.index("--at") + 1], "10,20")
        self.assertIn("--foreground", argv)

    def test_human_active_mid_sequence_refused_before_act(self):
        ctx = self._ctx(presence_sequence=[
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 1.0, "human_active": True}])
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE_MID_SEQUENCE", payload["cause"])
        self.assertIn("observe", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])


class TestSlicePaste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-paste-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_FIELD_VALUE",
                    "FAKE_PEEKABOO_CLIPBOARD_RESTORED"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _paste(self, ctx, **extra):
        args = {"action": "slice_paste", "window_id": 42, "owner": "agent-a",
                "text": "hello world"}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_paste_dispatch_shape_no_keystrokes(self):
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx, element_ref="field1")["content"]
                             [0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)
        argv = pastes[0]
        self.assertEqual(argv[0], "paste")
        self.assertIn("--text", argv)
        self.assertEqual(argv[argv.index("--text") + 1], "hello world")
        self.assertEqual(argv[argv.index("--app") + 1], "TextEdit")
        self.assertEqual(argv[argv.index("--window-id") + 1], "42")
        self.assertIn("--json", argv)
        self.assertIn("--no-remote", argv)
        # paste is not an element-targeted act: no --input-strategy.
        self.assertNotIn("--input-strategy", argv)
        # The paste chord is the ONLY key event: no character keystrokes.
        self.assertNotIn("press", argv)
        self.assertNotIn("type", argv)
        self.assertNotIn("key", argv)
        self.assertNotIn("--foreground", argv)
        # A named field is focused by one element click first.
        focus = [c for c in read_calls(ctx) if c[0] == "click"]
        self.assertEqual(len(focus), 1)
        self.assertEqual(focus[0][focus[0].index("--on") + 1], "field1")
        self.assertIn("--foreground", focus[0])

    def test_paste_confirm_and_restore_fields(self):
        os.environ["FAKE_PEEKABOO_FIELD_VALUE"] = "prefix hello world suffix"
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx, element_ref="field1")["content"]
                             [0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["paste_confirmed"])
        self.assertTrue(payload["restored"])
        self.assertNotIn("restore_reported", payload)

    def test_paste_confirm_false_when_value_differs(self):
        ctx = self._ctx()  # field value stays empty
        payload = json.loads(self._paste(ctx, element_ref="field1")["content"]
                             [0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertFalse(payload["paste_confirmed"])
        self.assertTrue(payload["restored"])

    def test_paste_restored_false_when_not_reported(self):
        os.environ["FAKE_PEEKABOO_CLIPBOARD_RESTORED"] = "null"
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx, element_ref="field1")["content"]
                             [0]["text"])
        self.assertFalse(payload["restored"])
        self.assertFalse(payload["restore_reported"])

    def test_text_required(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "owner": "agent-a"})
        self.assertIn("TEXT_REQUIRED", result["content"][0]["text"])

    def test_pacing_wait_then_allowed(self):
        ctx = self._ctx()  # default 180 s pacing
        self.assertEqual(ctx.pacer.seconds, 180.0)
        payload = json.loads(self._paste(ctx)["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        # Second sequence on the same window inside the interval: refused
        # before any dispatch.
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("PACING_WAIT", payload["cause"])
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)  # only the first dispatch exists
        # After the interval elapses (simulated), the paste is allowed again.
        with open(ctx.pacer.path) as handle:
            data = json.load(handle)
        data["42"] = time.time() - 181
        with open(ctx.pacer.path, "w") as handle:
            json.dump(data, handle)
        payload = json.loads(self._paste(ctx)["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertEqual(len([c for c in read_calls(ctx)
                              if c[0] == "paste"]), 2)

    def test_human_active_mid_sequence_before_paste(self):
        ctx = self._ctx(presence_sequence=[
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 1.0, "human_active": True}])
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE_MID_SEQUENCE", payload["cause"])
        self.assertIn("observe", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "paste"], [])
        # No pacing record was left behind by the refused sequence.
        self.assertEqual(json.load(open(ctx.pacer.path))
                         if os.path.exists(ctx.pacer.path) else {}, {})


class TestSliceSend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-send-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_CHALLENGE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _send(self, ctx, **extra):
        args = {"action": "slice_send", "window_id": 42,
                "element_ref": "btn1", "owner": "agent-a"}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_challenge_refused_with_zero_send_dispatches(self):
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security notice: unusual activity detected on your account"
        ctx = self._ctx()
        result = self._send(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHALLENGE_DETECTED", payload["cause"])
        self.assertIn("unusual activity", payload["cause"])
        self.assertLessEqual(len(payload["cause"]),
                             len("CHALLENGE_DETECTED: ")
                             + mmos.MAX_ERROR_TEXT)
        clicks = [c for c in read_calls(ctx) if c[0] == "click"]
        self.assertEqual(clicks, [])
        # No pacing record: nothing was dispatched.
        self.assertFalse(os.path.exists(ctx.pacer.path))

    def test_send_dispatches_foreground_and_records_pacing(self):
        ctx = self._ctx()
        payload = json.loads(self._send(ctx)["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        clicks = [c for c in read_calls(ctx) if c[0] == "click"]
        self.assertEqual(len(clicks), 1)
        argv = clicks[0]
        self.assertEqual(argv[argv.index("--on") + 1], "btn1")
        self.assertIn("--foreground", argv)
        self.assertIn("--snapshot", argv)
        self.assertTrue(os.path.exists(ctx.pacer.path))

    def test_pacing_applies_to_send(self):
        ctx = self._ctx()
        self.assertEqual(json.loads(self._send(ctx)["content"][0]["text"])
                         ["status"], "APPLIED")
        payload = json.loads(self._send(ctx)["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("PACING_WAIT", payload["cause"])
        self.assertEqual(len([c for c in read_calls(ctx)
                              if c[0] == "click"]), 1)

    def test_element_ref_required(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_send", "window_id": 42, "owner": "agent-a"})
        self.assertIn("ELEMENT_REF_REQUIRED", result["content"][0]["text"])


class TestSliceLook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-look-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def test_look_returns_tree_and_capture_without_vision(self):
        ctx = self._ctx()
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a"})
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(result["content"][1]["type"], "image")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertIn("Button: OK", payload["tree"])
        self.assertNotIn("answer", payload)
        self.assertEqual(_new_mmos_temp_dirs(tempdir, before), set())

    def test_look_deny_listed_refused(self):
        ctx = self._ctx(identity=IDENTITY_ONepw)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a"})
        self.assertTrue(result["isError"])
        self.assertIn("DENY_LISTED", result["content"][0]["text"])

    def test_lease_required(self):
        ctx = build_ctx(self.tmp)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a"})
        self.assertIn("LEASE_NOT_HELD", result["content"][0]["text"])


class TestSliceLookVision(unittest.TestCase):
    """slice_look includes the vision relay when a vision model is
    configured (fake Anthropic-protocol endpoint)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-lookv-")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVisionHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_look_includes_vision_when_configured(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "question": "Where is OK?",
            "owner": "agent-a"})
        self.assertFalse(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertIn("OK button", payload["answer"])
        self.assertEqual(payload["elements"][0]["label"], "OK")
        self.assertEqual(result["content"][1]["type"], "image")


class TestHonestAutomation(unittest.TestCase):
    """The layer performs ordinary visible automation: no dispatch ever
    carries a human-imitation or disguise option."""

    def test_constants_declared(self):
        self.assertTrue(mmos.HONEST_AUTOMATION)
        self.assertGreaterEqual(len(mmos.FORBIDDEN_DISGUISE_FLAGS), 5)
        self.assertIn("captcha", mmos.DEFAULT_CHALLENGE_PATTERNS)
        self.assertIn("unusual activity", mmos.DEFAULT_CHALLENGE_PATTERNS)

    def test_no_disguise_flags_in_any_dispatch(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-honest-")
        try:
            ctx = build_ctx(tmp)
            ctx.lease.acquire("agent-a", ttl_seconds=60)
            # Mixed session: act, slice front/click/paste/send.
            mmos.handle_tool_call(ctx, {"action": "press", "window_id": 42,
                                        "element_ref": "btn1",
                                        "owner": "agent-a"})
            mmos.handle_tool_call(ctx, {"action": "slice_front",
                                        "app": "TextEdit", "window_id": 42,
                                        "owner": "agent-a"})
            mmos.handle_tool_call(ctx, {"action": "slice_click",
                                        "window_id": 42, "x": 10, "y": 20,
                                        "owner": "agent-a"})
            mmos.handle_tool_call(ctx, {"action": "slice_paste",
                                        "window_id": 42,
                                        "text": "hello world",
                                        "owner": "agent-a"})
            # A second paste would hit pacing; pace-check still exercises
            # the builder via a fresh window id.
            mmos.handle_tool_call(ctx, {"action": "slice_paste",
                                        "window_id": 43,
                                        "text": "more text",
                                        "owner": "agent-a"})
            all_argv = " ".join(" ".join(c) for c in read_calls(ctx))
            for flag in mmos.FORBIDDEN_DISGUISE_FLAGS:
                self.assertNotIn(flag, all_argv)
            self.assertNotIn("--humanize", all_argv)
            self.assertNotIn("--stealth", all_argv)
        finally:
            for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG"):
                os.environ.pop(key, None)
            shutil.rmtree(tmp, ignore_errors=True)


class TestLeaseStatusRedaction(unittest.TestCase):
    """FIX 4: lease_status redacts the owner; acquire/release still need the
    exact owner string."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-redact-")
        self.lease = mmos.Lease(state_dir=os.path.join(self.tmp, "state"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_owner_redacted(self):
        self.lease.acquire("owner-agent-1234567890", ttl_seconds=60)
        status = self.lease.status()
        self.assertEqual(status["owner"], "owner-ag…")
        self.assertTrue(status["owner_redacted"])
        self.assertIn("expires_in_seconds", status)
        self.assertNotIn("owner-agent-1234567890", json.dumps(status))

    def test_acquire_still_needs_exact_owner(self):
        self.lease.acquire("owner-agent-1234567890", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.release("owner-age…")  # the redacted form must fail
        self.assertEqual(caught.exception.code, "LEASE_NOT_OWNER")

    def test_lease_held_error_redacts_other_owner(self):
        self.lease.acquire("owner-agent-1234567890", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.acquire("agent-b", ttl_seconds=60)
        self.assertNotIn("owner-agent-1234567890",
                         caught.exception.detail)


class TestKeysAllowlist(unittest.TestCase):
    """FIX 1: only navigation/editing chords and shift+arrow pass the keys
    op; every modifier chord is refused with CHORD_NOT_ALLOWED."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-keys-")

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _keys(self, ctx, chord):
        return mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": chord,
            "owner": "agent-a"})

    def test_plain_key_allowed(self):
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "return")["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        presses = [c for c in read_calls(ctx) if c[0] == "press"]
        self.assertEqual(len(presses), 1)

    def test_shift_arrow_allowed(self):
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "shift+right")["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertEqual(len([c for c in read_calls(ctx)
                              if c[0] == "press"]), 1)

    def test_shift_return_refused(self):
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "shift+return")["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHORD_NOT_ALLOWED", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "press"], [])

    def test_cmd_s_refused(self):
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "cmd+s")["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHORD_NOT_ALLOWED", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "press"], [])

    def test_screenshot_chord_refused(self):
        # shift+cmd+3 is the screenshot chord; the allowlist refuses it.
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "shift+cmd+3")["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHORD_NOT_ALLOWED", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "press"], [])

    def test_cmd_q_refused(self):
        ctx = self._ctx()
        payload = json.loads(self._keys(ctx, "cmd+q")["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHORD_NOT_ALLOWED", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "press"], [])


class TestChallengeScanSliceOps(unittest.TestCase):
    """FIX 2: every input-delivering slice act challenge-scans before
    dispatch; slice_front (raise-only) keeps no scan."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-chalscan-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_CHALLENGE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def test_slice_click_challenge_refused_zero_dispatches(self):
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security check: verify you are human"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42,
            "element_ref": "btn1", "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHALLENGE_DETECTED", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])
        self.assertFalse(os.path.exists(ctx.pacer.path))

    def test_slice_paste_challenge_refused_zero_dispatches(self):
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security check: verify you are human"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "text": "hello",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("CHALLENGE_DETECTED", payload["cause"])
        calls = read_calls(ctx)
        self.assertEqual([c for c in calls if c[0] == "click"], [])
        self.assertEqual([c for c in calls if c[0] == "paste"], [])
        self.assertFalse(os.path.exists(ctx.pacer.path))

    def test_slice_front_keeps_no_scan(self):
        # slice_front raises without delivering input: a challenge string in
        # the AX tree does NOT refuse it.
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security check: verify you are human"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_front", "app": "TextEdit", "window_id": 42,
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")


class TestDenyHardening(unittest.TestCase):
    """FIX 3: terminal emulators and Script Editor are denied by default."""

    NEW_NAMES = ("Terminal", "iTerm", "iTerm2", "Script Editor")
    NEW_BUNDLES = ("com.apple.Terminal", "com.apple.ScriptEditor.id")

    def test_defaults_and_shipped_deny_json_carry_new_entries(self):
        for name in self.NEW_NAMES:
            self.assertIn(name, mmos.DEFAULT_DENY["app_names"])
        for bundle in self.NEW_BUNDLES:
            self.assertIn(bundle, mmos.DEFAULT_DENY["bundle_ids"])
        with open(os.path.join(TOOL_DIR, "deny.json"),
                  encoding="utf-8") as handle:
            shipped = json.load(handle)
        for name in self.NEW_NAMES:
            self.assertIn(name, shipped["app_names"])
        for bundle in self.NEW_BUNDLES:
            self.assertIn(bundle, shipped["bundle_ids"])

    def test_new_names_refused_on_window_op(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-denyh-")
        try:
            ctx = build_ctx(tmp)
            ctx.deny = mmos.DenyList(
                {"terminal", "iterm", "iterm2", "script editor", "1password"},
                {"com.apple.terminal", "com.apple.scripteditor.id",
                 "com.1password.1password"}, [])
            for name in self.NEW_NAMES:
                result = mmos.handle_tool_call(ctx, {
                    "action": "windows", "app": name})
                self.assertIn("DENY_LISTED", result["content"][0]["text"])
            # Exact-match semantics unchanged: lookalikes pass.
            result = mmos.handle_tool_call(ctx, {
                "action": "windows", "app": "TerminalTwo"})
            payload = json.loads(result["content"][0]["text"])
            self.assertEqual(payload["status"], "OK")
        finally:
            os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
            os.environ.pop("FAKE_PEEKABOO_LOG", None)
            shutil.rmtree(tmp, ignore_errors=True)


class TestWindowsDenyResolution(unittest.TestCase):
    """FIX 8: the windows op denies the requested string against bundle ids,
    denies every resolved app identity in the result, and drops foreign-app
    entries."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-windeny-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        return ctx

    def test_bundle_id_string_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "windows", "app": "com.1password.1password"})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_denied_resolved_app_refused_whole_op(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = json.dumps([
            {"window_id": 42, "title": "Secret", "app": "1Password",
             "bundle_id": "com.1password.1password"}])
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "windows", "app": "TextEdit"})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])
        payload = json.loads(result["content"][0]["text"])
        self.assertNotIn("windows", payload)

    def test_foreign_app_entry_filtered(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = json.dumps([
            {"window_id": 42, "title": "a", "app": "TextEdit",
             "bundle_id": "com.apple.TextEdit"},
            {"window_id": 43, "title": "b", "app": "SneakyApp",
             "bundle_id": "com.example.sneaky"}])
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "windows", "app": "TextEdit"})
        payload = json.loads(result["content"][0]["text"])
        ids = [w["window_id"] for w in payload["windows"]]
        self.assertEqual(ids, [42])

    def test_slice_front_bundle_id_string_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_front", "app": "com.1password.1password",
            "window_id": 42, "owner": "agent-a"})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])


class TestCaptureIdentityBeforeCapture(unittest.TestCase):
    """FIX 9: capture resolves the window identity screenshot-less and
    deny-gates it BEFORE the pixel capture dispatch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-capid-")

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_denied_window_never_captured(self):
        ctx = build_ctx(self.tmp, identity=IDENTITY_ONepw)
        result = mmos.handle_tool_call(ctx, {
            "action": "capture", "window_id": 42, "ocr": True,
            "owner": "agent-a"})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])
        calls = read_calls(ctx)
        # The screenshot-less identity observe may run; no capture dispatch.
        for argv in calls:
            self.assertNotIn("--path", argv)


class TestWindowIdentityBoundsPreference(unittest.TestCase):
    """FIX 7/13: coordinate-context window bounds and payload-level identity
    outrank nested element bounds / decoy keys; deep scan only as fallback."""

    def test_element_bounds_do_not_shrink_window(self):
        meta = {
            "ui_elements": [{"role": "Button",
                             "bounds": {"width": 100, "height": 50}}],
            "coordinate_context": {"window_bounds": {"x": 0, "y": 0,
                                                     "width": 800,
                                                     "height": 600}},
        }
        self.assertEqual(mmos.window_bounds(meta), (800.0, 600.0))

    def test_deep_scan_fallback_without_coordinate_context(self):
        meta = {"bounds": {"width": 640, "height": 480}}
        self.assertEqual(mmos.window_bounds(meta), (640.0, 480.0))

    def test_nested_decoy_app_does_not_beat_coordinate_context(self):
        meta = {
            "ui_elements": [{"app": "Decoy", "role": "Button"}],
            "coordinate_context": {"app": "TextEdit",
                                   "bundle_id": "com.apple.TextEdit",
                                   "window_title": "Real"},
        }
        identity = mmos.window_identity(meta)
        self.assertEqual(identity["app_name"], "TextEdit")
        self.assertEqual(identity["bundle_id"], "com.apple.TextEdit")
        self.assertEqual(identity["window_title"], "Real")

    def test_toplevel_identity_beats_nested_decoy(self):
        meta = {"app": "TextEdit", "ui_elements": [{"app": "Decoy"}]}
        self.assertEqual(mmos.window_identity(meta)["app_name"], "TextEdit")


class TestPasteTruthfulness(unittest.TestCase):
    """FIX 10: a dispatch-phase paste failure that is not a clean
    pre-dispatch refusal is EFFECT_UNKNOWN (never NOT_APPLIED), and the
    timeout receipt carries clipboard_state "unknown"."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-ptruth-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_PASTE_FAIL"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def _paste(self, ctx, **extra):
        args = {"action": "slice_paste", "window_id": 42, "owner": "agent-a",
                "text": "hello world"}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_paste_cli_error_is_effect_unknown(self):
        os.environ["FAKE_PEEKABOO_PASTE_FAIL"] = "1"
        ctx = self._ctx()
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN")
        self.assertIn("EFFECT_UNKNOWN", payload["cause"])
        self.assertIn("mid-flight", payload["cause"])
        self.assertEqual(payload["clipboard_state"], "unknown")
        # The attempt consumed the pacing window (record in finally).
        self.assertTrue(os.path.exists(ctx.pacer.path))

    def test_paste_timeout_is_effect_unknown_with_clipboard_unknown(self):
        ctx = self._ctx()

        def boom(_argv):
            raise mmos.OpError("DISPATCH_TIMEOUT",
                               "peekaboo paste exceeded 60s")

        ctx.adapter.paste = boom
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN")
        self.assertIn("DISPATCH_TIMEOUT", payload["cause"])
        self.assertEqual(payload["clipboard_state"], "unknown")
        self.assertTrue(os.path.exists(ctx.pacer.path))

    def test_clean_pre_dispatch_refusal_stays_not_applied(self):
        ctx = self._ctx()
        ctx.pacer.record(42)  # force PACING_WAIT before any dispatch
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("PACING_WAIT", payload["cause"])
        self.assertNotIn("clipboard_state", payload)


class TestRuntimeGateFloors(unittest.TestCase):
    """FIX 11: presence and pacing floors (>= 1 s) refuse at startup for
    runtime.json AND env overrides."""

    def test_runtime_presence_floor_refused(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-floor-")
        try:
            bin_path = make_fake_peekaboo(tmp)
            path = os.path.join(tmp, "runtime.json")
            with open(path, "w") as handle:
                json.dump({"schema": mmos.RUNTIME_SCHEMA,
                           "peekaboo_bin": bin_path,
                           "peekaboo_sha256": mmos.sha256_file(bin_path),
                           "presence_min_idle_seconds": 0.5}, handle)
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.load_runtime(path)
            self.assertEqual(caught.exception.code,
                             "RUNTIME_PRESENCE_MIN_IDLE_SECONDS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_runtime_pacing_floor_refused(self):
        tmp = tempfile.mkdtemp(prefix="mmos-cu-floor-")
        try:
            bin_path = make_fake_peekaboo(tmp)
            path = os.path.join(tmp, "runtime.json")
            with open(path, "w") as handle:
                json.dump({"schema": mmos.RUNTIME_SCHEMA,
                           "peekaboo_bin": bin_path,
                           "peekaboo_sha256": mmos.sha256_file(bin_path),
                           "pacing_seconds": 0.5}, handle)
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.load_runtime(path)
            self.assertEqual(caught.exception.code,
                             "RUNTIME_PACING_SECONDS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_env_presence_floor_refused(self):
        saved = os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        try:
            os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "0.5"
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.Presence()
            self.assertEqual(caught.exception.code, "PRESENCE_MIN_IDLE_FLOOR")
        finally:
            if saved is None:
                os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
            else:
                os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = saved

    def test_env_pacing_floor_refused(self):
        saved = os.environ.pop("MMOS_CU_PACING_SECONDS", None)
        try:
            os.environ["MMOS_CU_PACING_SECONDS"] = "0.5"
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.Pacer()
            self.assertEqual(caught.exception.code, "PACING_SECONDS_FLOOR")
        finally:
            if saved is None:
                os.environ.pop("MMOS_CU_PACING_SECONDS", None)
            else:
                os.environ["MMOS_CU_PACING_SECONDS"] = saved

    def test_runtime_dict_presence_floor_refused(self):
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(runtime={"presence_min_idle_seconds": 0.5})
        self.assertEqual(caught.exception.code, "PRESENCE_MIN_IDLE_FLOOR")

    def test_runtime_dict_pacing_floor_refused(self):
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Pacer(runtime={"pacing_seconds": 0.5})
        self.assertEqual(caught.exception.code, "PACING_SECONDS_FLOOR")


class TestVisionEndpointScheme(unittest.TestCase):
    """FIX 6: the vision endpoint must be https or loopback http."""

    def setUp(self):
        self.old_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "test-vision-token"

    def tearDown(self):
        if self.old_token is None:
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        else:
            os.environ["ANTHROPIC_AUTH_TOKEN"] = self.old_token

    def test_plain_http_remote_refused(self):
        client = mmos.VisionClient(base_url="http://example.com",
                                   token="t")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "question")
        self.assertEqual(caught.exception.code, "VISION_ENDPOINT_INSECURE")

    def test_loopback_and_https_allowed(self):
        for url in ("http://127.0.0.1:8080", "http://localhost:9000",
                    "http://[::1]:9", "https://example.com"):
            client = mmos.VisionClient(base_url=url, token="t")
            client._require_secure_endpoint()  # must not raise


class TestVisionPromptCaps(unittest.TestCase):
    """FIX 12: element_hints (20 entries / 120 chars each / 1200 total) and
    question (2000 chars) caps refuse over-limit input before any capture or
    network dispatch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-caps-")

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        ctx.lease.acquire("agent-a", ttl_seconds=60)
        return ctx

    def test_too_many_hints_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["hint-%d" % i for i in range(21)],
            "owner": "agent-a"})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_overlong_hint_entry_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["x" * 130],
            "owner": "agent-a"})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_total_hint_budget_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["y" * 110 for _ in range(12)],
            "owner": "agent-a"})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_question_too_long_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "q" * 2100, "owner": "agent-a"})
        self.assertTrue(result["isError"])
        self.assertIn("QUESTION_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_ask_enforces_question_cap(self):
        client = mmos.VisionClient(base_url="http://127.0.0.1:1", token="t")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "q" * 2100)
        self.assertEqual(caught.exception.code, "QUESTION_TOO_LONG")


if __name__ == "__main__":
    unittest.main()
