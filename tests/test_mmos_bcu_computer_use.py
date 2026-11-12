#!/usr/bin/env python3
"""Unit tests for tools/mmos_computer_use/server.py.

Pure unit tests: no screen access, no real peekaboo interaction, no network
beyond an in-process fake HTTP server. The peekaboo adapter is exercised
against a fake peekaboo shell script in a temp dir.

Run from the checkout root:
    python3 -m pytest tests/test_mmos_bcu_computer_use.py

BCU R3 H2: the server has NO test-mode flag any more — the 180 s floors are
unconditional in code for every environment/runtime.json value. Sub-default
thresholds in these tests come from constructor injection (Presence/
Pacer/_StubPresence arguments), and the subprocess round trip passes its
scratch paths as server launch ARGUMENTS (--state-dir/--runtime/--deny),
never as environment variables.
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
# M7-PREP: when FAKE_PEEKABOO_FIXTURES names a directory of real captures,
# replay the matching capture (cat it verbatim); otherwise the inline
# fixtures below are used. Missing files always fall through.
fixtures="${FAKE_PEEKABOO_FIXTURES:-}"
replay() {
  [ -n "$fixtures" ] && [ -f "$fixtures/$1" ] || return 1
  cat "$fixtures/$1"
  exit 0
}
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
    replay app_list_sanitized.json
    echo '{"success": true, "data": {"apps": [
      {"name": "TextEdit", "bundle_id": "com.apple.TextEdit", "pid": 101,
       "is_active": true, "is_hidden": false},
      {"name": "1Password", "bundle_id": "com.1password.1password", "pid": 102,
       "is_active": false, "is_hidden": false}]}}'
    ;;
  window)
    if [ "$2" = "focus" ]; then
      if [ -n "${FAKE_PEEKABOO_ACT_FAIL:-}" ]; then
        echo "simulated focus dispatch failure" >&2
        exit 1
      fi
      # window focus --window-id N: rc=0 shape (real capture focus_c).
      echo '{"success": true, "data": {"action": "focus", "app_name": "TextEdit", "window_title": "Untitled", "new_bounds": {"x": 0, "y": 0, "width": 800, "height": 600}}}'
      exit 0
    fi
    replay window_list_fixture.json
    # Find the --app value (both "--app X" and "--app=X" forms).
    wapp=""
    prev=""
    for a in "${ARGS[@]}"; do
      case "$a" in
        --app=*) wapp="${a#--app=}" ;;
        *) [ "$prev" = "--app" ] && wapp="$a" ;;
      esac
      prev="$a"
    done
    if [ -n "${FAKE_PEEKABOO_APP_AMBIGUOUS:-}" ] && \
       [ "$wapp" = "${FAKE_PEEKABOO_APP_AMBIGUOUS_APP:-TextEdit}" ]; then
      # Real shape: --app NAME with several same-name processes fails.
      echo '{"success": false, "error": {"code": "AMBIGUOUS_APP_IDENTIFIER",
        "message": "Multiple applications match"}}' >&2
      exit 1
    fi
    pid_seen=0
    for a in "${ARGS[@]}"; do
      case "$a" in --pid=*) pid_seen=1 ;; esac
    done
    if [ -n "${FAKE_PEEKABOO_PID_WINDOWS_JSON:-}" ] && [ "$pid_seen" = "1" ]; then
      echo "{\"success\": true, \"data\": {\"target_application_info\": {\"app_name\": \"TextEdit\", \"pid\": 101}, \"windows\": ${FAKE_PEEKABOO_PID_WINDOWS_JSON}}}"
      exit 0
    fi
    if [ "$wapp" = "1Password" ]; then
      # H6-INTERIM: a deny-listed app's windows; empty unless the test asks.
      echo "{\"success\": true, \"data\": {\"windows\": ${FAKE_PEEKABOO_ONPW_WINDOWS_JSON:-[]}}}"
    elif [ -n "${FAKE_PEEKABOO_WINDOWS_JSON:-}" ]; then
      echo "{\"success\": true, \"data\": {\"windows\": ${FAKE_PEEKABOO_WINDOWS_JSON}}}"
    else
      echo '{"success": true, "data": {"windows": [
        {"window_id": 42, "title": "Untitled", "owner_pid": 101,
         "is_frontmost": true, "window_index": 0, "is_key": true}]}}'
    fi
    ;;
  see)
    # Round-2 D-H2 knob: count see calls; from the 3rd onward an optional
    # FAKE_PEEKABOO_IDENTITY_2 replaces the identity (simulate a window
    # that becomes deny-listed between the observe and the confirm read).
    if [ -n "${FAKE_PEEKABOO_SEE_COUNT:-}" ]; then
      see_n=0
      [ -f "${FAKE_PEEKABOO_SEE_COUNT}" ] && read -r see_n < "${FAKE_PEEKABOO_SEE_COUNT}"
      see_n=$((see_n+1))
      printf '%s' "$see_n" > "${FAKE_PEEKABOO_SEE_COUNT}"
      if [ "$see_n" -ge 3 ] && [ -n "${FAKE_PEEKABOO_IDENTITY_2:-}" ]; then
        ident="${FAKE_PEEKABOO_IDENTITY_2}"
      fi
    fi
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
      replay see_fixture_window.json
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
    if has --foreground; then
      replay paste_foreground_unconfirmed_but_delivered.json
    else
      replay paste_background_unconfirmed.json
    fi
    if [ -n "${FAKE_PEEKABOO_PASTE_FAIL:-}" ]; then
      echo '{"success": false, "errors": ["paste chord delivery failed mid-flight"]}'
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_PASTE_DECOY:-}" ]; then
      # A nested "restored" key must never be read as the documented field.
      echo '{"success": true, "data": {"result": "pasted", "ui_elements": [{"restored": true}]}}'
      exit 0
    fi
    echo "{\"success\": true, \"data\": {\"result\": \"pasted\", \"clipboard_restored\": ${FAKE_PEEKABOO_CLIPBOARD_RESTORED:-true}}}"
    ;;
  action|set-value|press|scroll|click)
    if [ "$1" = "press" ] && ! has --foreground; then
      replay press_foreground_required_error.json
    fi
    if [ -n "${FAKE_PEEKABOO_NO_AX_ACTION:-}" ]; then
      # Real capture (click_actiononly_no_ax_element.json): a Tk button is
      # AX-VISIBLE but not AX-ACTIONABLE; peekaboo found nothing to invoke.
      # Pre-dispatch -> typed ELEMENT_NOT_ACTIONABLE / NOT_APPLIED.
      echo '{"success": false, "error": {"code": "INTERNAL_SWIFT_ERROR", "message": "No accessibility element is available for action invocation"}, "effect": "unverifiable", "data": null}'
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_SNAPSHOT_STALE:-}" ]; then
      # Real capture (click_snapshot_stale_refused.json): effect "refused"
      # is peekaboo's explicit pre-dispatch refusal marker.
      echo '{"success": false, "error": {"code": "SNAPSHOT_STALE", "message": "Snapshot is stale: the most recent UI snapshot was invalidated because an earlier command changed the desktop. Re-run peekaboo see to refresh."}, "effect": "refused", "data": null}'
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_REFUSAL_NO_MUTATION:-}" ]; then
      # Real refusal shape (raise_a capture): peekaboo PROVES nothing was
      # dispatched (mutation_dispatched false) — the receipt may say
      # NOT_APPLIED, never EFFECT_UNKNOWN.
      echo '{"success": false, "error": {"code": "INTERACTION_FAILED", "message": "refused before any dispatch", "mutation_dispatched": false}, "outcome": {"state": "refused", "mutation_dispatched": false}}'
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_ACT_FAIL:-}" ]; then
      echo "simulated dispatch failure after the event was attempted" >&2
      exit 1
    fi
    if [ -n "${FAKE_PEEKABOO_CLI_STDOUT_ERROR:-}" ]; then
      # The failure text on stdout may embed window content; the receipt must
      # quote stderr instead.
      echo '{"success": false, "errors": ["'"${FAKE_PEEKABOO_CLI_STDOUT_ERROR}"'"]}'
      echo "stderr-detail-marker" >&2
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_FOREGROUND_REFUSED:-}" ] && ! has --foreground; then
      # Structured refusal (real capture press_foreground_required_error.json):
      # peekaboo PROVES nothing was dispatched. Only this shape may become
      # NOT_APPLIED (BCU R2 item 3 / R-M1).
      echo '{"success": false, "effect": "refused", "data": null, "outcome": {"state": "refused", "effect": "refused", "mutation_dispatched": false, "dispatch_state": "none", "evidence": "request_refused"}, "error": {"code": "INTERACTION_FAILED", "message": "Raw key presses require explicit foreground consent unless a fresh exact receipt pins background delivery.", "mutation_dispatched": false}}'
      exit 0
    fi
    if [ -n "${FAKE_PEEKABOO_FOREGROUND_REQUIRED:-}" ] && ! has --foreground; then
      # TEXT-ONLY refusal: no structured mutation_dispatched field. A text
      # mention must never turn a possible dispatch into NOT_APPLIED.
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
    ctx.lease_nonce = None  # set by acquire_lease(); every act carries it
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


def acquire_lease(ctx, owner="agent-a", ttl_seconds=60):
    """Acquire the lease and stash the per-acquisition nonce on the ctx
    (M5: every act call site must carry it as `lease_nonce`)."""
    result = ctx.lease.acquire(owner, ttl_seconds=ttl_seconds)
    ctx.lease_nonce = result["nonce"]
    return result


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
        # M5: only sha256(owner)[:12] is ever shown by lease_status.
        import hashlib
        self.assertEqual(status["owner"],
                         hashlib.sha256(b"agent-a").hexdigest()[:12])
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
        # The monotonic pair is the preferred expiry gate; expire it too so
        # the simulated crash is complete on every clock.
        lease["mono_expires_at"] = time.monotonic() - 1
        with open(self.lease.lease_path, "w", encoding="utf-8") as handle:
            json.dump(lease, handle)
        result = self.lease.acquire("agent-b", ttl_seconds=60)
        self.assertTrue(result["took_over"])
        import hashlib
        self.assertEqual(self.lease.status()["owner"],
                         hashlib.sha256(b"agent-b").hexdigest()[:12])

    def test_release_by_wrong_owner_refused(self):
        self.lease.acquire("agent-a", ttl_seconds=60)
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.release("agent-b")
        self.assertEqual(caught.exception.code, "LEASE_NOT_OWNER")

    def test_require_and_renew_renews_expiry(self):
        result = self.lease.acquire("agent-a", ttl_seconds=5)
        with open(self.lease.lease_path) as handle:
            before = json.load(handle)
        self.lease.require_and_renew("agent-a",
                                     nonce=result["nonce"])
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
        # BCU R3 H2: sub-180 s thresholds come from constructor injection
        # (the in-process test path); no env marker exists or is needed.
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
        acquire_lease(self.ctx)

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
            "owner": "agent-a", "lease_nonce": self.ctx.lease_nonce})
        self.assertIn("COORDS_REQUIRED", result["content"][0]["text"])

    def test_pointer_click_outside_window_bounds(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "pointer_click", "window_id": 42, "x": 2000, "y": 10,
            "owner": "agent-a", "lease_nonce": self.ctx.lease_nonce})
        self.assertIn("POINT_OUTSIDE_WINDOW", result["content"][0]["text"])

    def test_pointer_click_inside_bounds_applied(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": self.ctx.lease_nonce})
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
        acquire_lease(ctx)
        return ctx

    def test_act_without_lease_not_applied(self):
        ctx = build_ctx(self.tmp)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_NOT_HELD", payload["cause"])

    def test_act_deny_listed_refused_before_dispatch(self):
        ctx = self._ctx(identity=IDENTITY_ONepw)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE", payload["cause"])

    def test_act_renews_lease(self):
        ctx = self._ctx()
        with open(ctx.lease.lease_path) as handle:
            before = json.load(handle)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        with open(ctx.lease.lease_path) as handle:
            after = json.load(handle)
        self.assertGreaterEqual(after["expires_at"], before["expires_at"])

    def test_global_chord_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "cmd+space",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertIn("CHORD_GLOBAL", result["content"][0]["text"])

    def test_multi_chord_sequence_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "ctrl+a Delete",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertIn("CHORD_INVALID", result["content"][0]["text"])

    def test_window_identity_unknown_refused(self):
        ctx = self._ctx(identity=IDENTITY_EMPTY)
        result = mmos.handle_tool_call(ctx, {
            "action": "set_text", "window_id": 42, "element_ref": "field1",
            "text": "hello", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
                "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        os.environ.pop("FAKE_PEEKABOO_FOREGROUND_REFUSED", None)

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_FOREGROUND_REQUIRED", None)
        os.environ.pop("FAKE_PEEKABOO_FOREGROUND_REFUSED", None)
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        acquire_lease(ctx)
        return ctx

    def _act_calls(self, ctx):
        return [c for c in read_calls(ctx)
                if c[0] in ("action", "set-value", "press", "scroll", "click")]

    def _assert_background_shape(self, argv, require_on=True,
                                 require_window_id=False,
                                 require_strategy=True):
        self.assertIn("--snapshot", argv)
        self.assertEqual(argv[argv.index("--snapshot") + 1], "snap-abc123")
        if require_on:
            self.assertIn("--on", argv)
        self.assertNotIn("--foreground", argv)
        self.assertNotIn("--app", argv)
        self.assertNotIn("--pid", argv)
        if require_window_id:
            self.assertIn("--window-id", argv)
        else:
            self.assertNotIn("--window-id", argv)
        self.assertIn("--json", argv)
        self.assertIn("--no-remote", argv)
        if require_strategy:
            self.assertEqual(argv[argv.index("--input-strategy") + 1],
                             "actionOnly")
        else:
            # A chord is synthetic delivery: no --input-strategy (actionOnly
            # leaves it undeliverable — live rc=1 red).
            self.assertNotIn("--input-strategy", argv)

    def test_press_dispatches_on_snapshot(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "text": "hello", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self._assert_background_shape(calls[0])
        self.assertEqual(calls[0][0], "set-value")
        self.assertIn("--value=hello", calls[0])
        self.assertEqual(calls[0][calls[0].index("--on") + 1], "field1")

    def test_keys_dispatches_on_snapshot(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "Return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        # A chord targets no element, but the dispatch still carries the
        # exact --window-id: peekaboo refuses a targetless background press
        # (live rc=1, no structured error) and delivers background only for
        # an exact window selector (press_chord_window_background.json).
        # No --input-strategy: a chord is synthetic delivery (actionOnly
        # leaves it undeliverable — live rc=1 red).
        self._assert_background_shape(calls[0], require_on=False,
                                      require_window_id=True,
                                      require_strategy=False)
        self.assertEqual(calls[0][:2], ["press", "Return"])

    def test_scroll_targets_scrollable_element(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "scroll", "window_id": 42, "direction": "down",
            "amount": 3, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "element_ref": "btn1", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("ELEMENT_NOT_FOUND", payload["cause"])
        self.assertEqual(self._act_calls(ctx), [])

    def test_foreground_required_text_only_is_effect_unknown_and_not_retried(self):
        # BCU R2 item 3 (R-M1): the fake emits only a TEXT mention of
        # "foreground" — no structured mutation_dispatched. Text is evidence of
        # a failure, never proof that nothing was dispatched, so the receipt is
        # EFFECT_UNKNOWN. It is still terminal: exactly one dispatch, no retry.
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN", payload)
        self.assertIn("FOREGROUND_REQUIRED", payload["cause"])
        self.assertNotIn("foreground", payload)
        # Exactly one act dispatch: the refusal is terminal, never escalated.
        self.assertEqual(len(self._act_calls(ctx)), 1)
        self.assertNotIn("--foreground", self._act_calls(ctx)[0])

    def test_foreground_required_structured_refusal_is_not_applied(self):
        # BCU R2 item 3 (R-M1): with peekaboo's structured proof
        # (mutation_dispatched false / effect refused) the same failure IS a
        # NOT_APPLIED — derived from the field, not from the wording.
        os.environ["FAKE_PEEKABOO_FOREGROUND_REFUSED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("FOREGROUND_REQUIRED", payload["cause"])
        self.assertEqual(len(self._act_calls(ctx)), 1)
        self.assertNotIn("--foreground", self._act_calls(ctx)[0])

    def test_allow_foreground_opt_in_dispatches_once_with_flag(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
            "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        calls = self._act_calls(ctx)
        # M10: foreground is chosen up front from the explicit flag — ONE
        # dispatch carrying --foreground, never a background attempt first.
        self.assertEqual(len(calls), 1)
        self.assertIn("--foreground", calls[0])
        self.assertIn("--snapshot", calls[0])

    def test_allow_foreground_without_lease_not_applied(self):
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"
        ctx = build_ctx(self.tmp)  # no lease acquired
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce, "allow_foreground": True})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce, "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("HUMAN_ACTIVE", payload["cause"])
        self.assertEqual(self._act_calls(ctx), [])

    def test_allow_foreground_dispatches_foreground_directly(self):
        # The opt-in selects foreground up front; it is not a fallback chosen
        # from peekaboo's error text (M10-CODE).
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
            "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertTrue(payload["foreground"])
        calls = self._act_calls(ctx)
        self.assertEqual(len(calls), 1)
        self.assertIn("--foreground", calls[0])

    def test_allow_foreground_defaults_false_in_schema(self):
        prop = mmos.TOOL_SCHEMA["properties"]["allow_foreground"]
        self.assertEqual(prop["type"], "boolean")
        self.assertFalse(prop["default"])


class TestCaptureMetadataOnly(unittest.TestCase):
    """H4: capture persists nothing and returns metadata + AX/OCR text only
    (keep_path was removed entirely)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-cap-")
        self.ctx = build_ctx(self.tmp)
        self.scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(self.scratch, exist_ok=True)
        acquire_lease(self.ctx)

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_capture_writes_no_persistent_file(self):
        result = mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": False,
            "owner": "agent-a", "lease_nonce": self.ctx.lease_nonce})
        self.assertFalse(result["isError"])
        self.assertEqual(os.listdir(self.scratch), [])

    def test_capture_no_staging_dirs_left_behind(self):
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        mmos.handle_tool_call(self.ctx, {
            "action": "capture", "window_id": 42, "ocr": True,
            "owner": "agent-a", "lease_nonce": self.ctx.lease_nonce})
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
        acquire_lease(ctx)
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port)
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        acquire_lease(ctx)
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port)
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        # BCU R3 H2: NO MMOS_CU_* path/threshold env for the child — a
        # subprocess test passes its scratch paths as launch ARGUMENTS. The
        # only env the child gets is the fake-peekaboo harness plumbing.
        for key in ("MMOS_CU_TEST_MODE", "MMOS_CU_RUNTIME",
                    "MMOS_CU_STATE_DIR", "MMOS_CU_DENY",
                    "MMOS_CU_PRESENCE_MIN_IDLE", "MMOS_CU_PACING_SECONDS"):
            self.env.pop(key, None)
        self.env.update({
            "FAKE_PEEKABOO_LOG": log,
            "FAKE_PEEKABOO_IDENTITY": IDENTITY_TEXTEDIT,
        })
        server_py = os.path.join(TOOL_DIR, "server.py")
        self.proc = subprocess.Popen(
            [sys.executable, server_py,
             "--runtime", write_runtime(self.tmp, bin_path),
             "--state-dir", os.path.join(self.tmp, "state"),
             "--deny", deny],
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
        import hashlib
        self.assertEqual(payload["owner"],
                         hashlib.sha256(b"framing-test").hexdigest()[:12])
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
                                 "FAKE_PEEKABOO_IDENTITY",
                                 "MMOS_CU_TEST_MODE")}
            for key in ("MMOS_CU_TEST_MODE", "MMOS_CU_RUNTIME",
                        "MMOS_CU_STATE_DIR", "MMOS_CU_DENY"):
                os.environ.pop(key, None)  # BCU R3 H2: no env path escapes
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
            # BCU R3 H2: scratch paths arrive as launch-argument injection,
            # never as environment variables.
            rc = mmos.serve(stdin=requests, stdout=captured,
                            runtime_path=write_runtime(tmp, bin_path),
                            state_dir=os.path.join(tmp, "state"))
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
        self.saved_test_mode = os.environ.pop("MMOS_CU_TEST_MODE", None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        else:
            os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = self.saved
        if self.saved_test_mode is None:
            os.environ.pop("MMOS_CU_TEST_MODE", None)
        else:
            os.environ["MMOS_CU_TEST_MODE"] = self.saved_test_mode

    def test_default_is_180_seconds(self):
        self.assertEqual(mmos.DEFAULT_MIN_IDLE_SECONDS, 180.0)
        self.assertEqual(mmos.Presence().min_idle, 180.0)

    def test_env_override(self):
        # BCU R3 H2: env may only make the gate STRICTER (>= 180 s).
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "300"
        self.assertEqual(mmos.Presence().min_idle, 300.0)
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "45"
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence()
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_runtime_key_override(self):
        # BCU R3 H2: runtime.json may only make the gate STRICTER.
        presence = mmos.Presence(runtime={"presence_min_idle_seconds": 300})
        self.assertEqual(presence.min_idle, 300.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(runtime={"presence_min_idle_seconds": 90})
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_env_beats_runtime_key(self):
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "300"
        presence = mmos.Presence(runtime={"presence_min_idle_seconds": 240})
        self.assertEqual(presence.min_idle, 300.0)

    def test_constructor_injection_is_the_sub_default_path(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): the constructor argument is
        # the ONLY sub-default path — no marker, no pytest check, in code.
        self.assertEqual(mmos.Presence(min_idle_seconds=8.0).min_idle, 8.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(min_idle_seconds=0.5)
        self.assertEqual(caught.exception.code, "PRESENCE_MIN_IDLE_FLOOR")

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
        self.saved_test_mode = os.environ.pop("MMOS_CU_TEST_MODE", None)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("MMOS_CU_PACING_SECONDS", None)
        else:
            os.environ["MMOS_CU_PACING_SECONDS"] = self.saved
        if self.saved_test_mode is None:
            os.environ.pop("MMOS_CU_TEST_MODE", None)
        else:
            os.environ["MMOS_CU_TEST_MODE"] = self.saved_test_mode
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
        # BCU R3 H2: env may only make pacing STRICTER (>= 180 s).
        os.environ["MMOS_CU_PACING_SECONDS"] = "300"
        self.assertEqual(self._pacer().seconds, 300.0)
        os.environ["MMOS_CU_PACING_SECONDS"] = "5"
        with self.assertRaises(mmos.RefuseError) as caught:
            self._pacer()
        self.assertEqual(caught.exception.code, "PACING_SECONDS_STRICTER_ONLY")

    def test_runtime_seconds(self):
        # BCU R3 H2: runtime.json may only make pacing STRICTER.
        pacer = self._pacer(runtime={"pacing_seconds": 300})
        self.assertEqual(pacer.seconds, 300.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            self._pacer(runtime={"pacing_seconds": 60})
        self.assertEqual(caught.exception.code, "PACING_SECONDS_STRICTER_ONLY")

    def test_env_beats_runtime_seconds(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "300"
        pacer = self._pacer(runtime={"pacing_seconds": 240})
        self.assertEqual(pacer.seconds, 300.0)

    def test_constructor_injection_is_the_sub_default_path(self):
        # BCU R3 H2: the constructor argument is the ONLY sub-default path;
        # the absolute 1 s floor still holds even for it.
        self.assertEqual(self._pacer(seconds=5.0).seconds, 5.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            self._pacer(seconds=0.5)
        self.assertEqual(caught.exception.code, "PACING_SECONDS_FLOOR")

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
        acquire_lease(ctx)
        return ctx

    def _front(self, ctx, **extra):
        args = {"action": "slice_front", "app": "TextEdit",
                "owner": "agent-a", "lease_nonce": ctx.lease_nonce}
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
        raises = [c for c in read_calls(ctx) if c[:2] == ["window", "focus"]]
        # ONE focus dispatch; never attempted in the background first.
        self.assertEqual(len(raises), 1)
        argv = raises[0]
        self.assertEqual(argv[argv.index("--window-id") + 1], "42")
        # Window ops take neither --input-strategy nor --foreground (live
        # A/B focus_c/d: focus rc=0; both flags refused).
        self.assertNotIn("--foreground", argv)
        self.assertNotIn("--input-strategy", argv)
        self.assertNotIn("--app", argv)
        self.assertNotIn("--pid", argv)
        self.assertEqual(
            [c for c in read_calls(ctx) if c[0] == "action"], [])

    def test_raise_without_window_element_targets_window_id(self):
        """Real Tk-host shape (see captures): the snapshot exposes no
        Window-role element — and an elementless `action AXRaise` is ALWAYS
        refused by peekaboo ("--on is required", live rc=1), element or
        not. The raise must go through `window focus --window-id`."""
        ctx = self._ctx()  # no FAKE_PEEKABOO_WINDOW_ELEMENT
        payload = json.loads(self._front(ctx, window_id=42)["content"][0]
                             ["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        raises = [c for c in read_calls(ctx) if c[:2] == ["window", "focus"]]
        self.assertEqual(len(raises), 1)
        argv = raises[0]
        self.assertEqual(argv[argv.index("--window-id") + 1], "42")
        self.assertNotIn("--foreground", argv)
        self.assertNotIn("--input-strategy", argv)
        self.assertEqual(
            [c for c in read_calls(ctx) if c[0] == "action"], [])

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
        acquire_lease(ctx)
        return ctx

    def test_element_click_dispatches_foreground(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        acquire_lease(ctx)
        return ctx

    def _paste(self, ctx, **extra):
        args = {"action": "slice_paste", "window_id": 42,
                "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
                "text": "hello world"}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_paste_dispatch_shape_no_keystrokes(self):
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx, element_ref="field1")["content"]
                             [0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        # Default paste is ONE background dispatch; the receipt says so.
        self.assertFalse(payload["foreground"])
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)
        argv = pastes[0]
        self.assertEqual(argv[0], "paste")
        # M11: the value travels in the equal-sign form, one token.
        self.assertIn("--text=hello world", argv)
        # Targeting is by owning PID, never --app NAME (ambiguous across
        # same-name processes — the live rc=1 paste refusal; the fake app
        # list maps TextEdit -> pid 101).
        self.assertIn("--pid=101", argv)
        self.assertNotIn("--app", argv)
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

    def test_paste_opt_in_adds_single_foreground_dispatch(self):
        # M10 law for paste: default is ONE background dispatch; the
        # allow_foreground flag (and only the flag) adds --foreground to
        # that single dispatch. Live basis: background paste into the Tk
        # fixture returns the unconfirmed refusal (EFFECT_UNKNOWN honest);
        # the foreground paste delivers (fixture FIELD line).
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx, element_ref="field1",
                                         allow_foreground=True)["content"]
                             [0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertTrue(payload["foreground"])
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)
        self.assertIn("--foreground", pastes[0])

    def test_paste_default_is_background_single_dispatch(self):
        ctx = self._ctx()
        payload = json.loads(self._paste(ctx)["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertFalse(payload["foreground"])
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)
        self.assertNotIn("--foreground", pastes[0])

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
            "action": "slice_paste", "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        # M8: entries are keyed by app identity + title, not window id.
        with open(ctx.pacer.path) as handle:
            data = json.load(handle)
        data = {key: time.time() - 181 for key in data}
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
        acquire_lease(ctx)
        return ctx

    def _send(self, ctx, **extra):
        args = {"action": "slice_send", "window_id": 42,
                "element_ref": "btn1", "owner": "agent-a",
                "lease_nonce": ctx.lease_nonce}
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
            "action": "slice_send", "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        acquire_lease(ctx)
        return ctx

    def test_look_returns_tree_and_capture_without_vision(self):
        ctx = self._ctx()
        tempdir = tempfile.gettempdir()
        before = set(os.listdir(tempdir))
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertFalse(result["isError"])
        # H4: AX text only — no image content block ever.
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "text")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertIn("Button: OK", payload["tree"])
        self.assertNotIn("answer", payload)
        self.assertEqual(_new_mmos_temp_dirs(tempdir, before), set())

    def test_look_deny_listed_refused(self):
        ctx = self._ctx(identity=IDENTITY_ONepw)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertTrue(result["isError"])
        self.assertIn("DENY_LISTED", result["content"][0]["text"])

    def test_lease_required(self):
        ctx = build_ctx(self.tmp)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        acquire_lease(ctx)
        # TEST-INDEPENDENCE: inject the token explicitly; never rely on an
        # ambient ANTHROPIC_AUTH_TOKEN.
        ctx.vision = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port,
            token="injected-look-token")
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42, "question": "Where is OK?",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        self.assertFalse(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertIn("OK button", payload["answer"])
        self.assertEqual(payload["elements"][0]["label"], "OK")
        # H4(d): the vision model's TEXT answer only, never the image.
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertNotIn(PNG_B64_PREFIX, result["content"][0]["text"])


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
            acquire_lease(ctx)
            # Mixed session: act, slice front/click/paste/send.
            mmos.handle_tool_call(ctx, {"action": "press", "window_id": 42,
                                        "element_ref": "btn1",
                                        "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
            mmos.handle_tool_call(ctx, {"action": "slice_front",
                                        "app": "TextEdit", "window_id": 42,
                                        "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
            mmos.handle_tool_call(ctx, {"action": "slice_click",
                                        "window_id": 42, "x": 10, "y": 20,
                                        "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
            mmos.handle_tool_call(ctx, {"action": "slice_paste",
                                        "window_id": 42,
                                        "text": "hello world",
                                        "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
            # A second paste would hit pacing; pace-check still exercises
            # the builder via a fresh window id.
            mmos.handle_tool_call(ctx, {"action": "slice_paste",
                                        "window_id": 43,
                                        "text": "more text",
                                        "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        import hashlib
        self.assertEqual(status["owner"],
                         hashlib.sha256(b"owner-agent-1234567890")
                         .hexdigest()[:12])
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
        acquire_lease(ctx)
        return ctx

    def _keys(self, ctx, chord):
        return mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": chord,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})

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
        acquire_lease(ctx)
        return ctx

    def test_slice_click_challenge_refused_zero_dispatches(self):
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security check: verify you are human"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42,
            "element_ref": "btn1", "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "window_id": 42, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
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
        acquire_lease(ctx)
        return ctx

    def _paste(self, ctx, **extra):
        args = {"action": "slice_paste", "window_id": 42,
                "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
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
        # BCU R2 item 4: the pace is keyed on the owning pid + exact window id
        # (the fake window list reports owner_pid 101 for window 42).
        ctx.pacer.record(mmos.pacing_key(42, 101))
        result = self._paste(ctx)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("PACING_WAIT", payload["cause"])
        self.assertNotIn("clipboard_state", payload)


class TestRuntimeGateFloors(unittest.TestCase):
    """FIX 11: presence and pacing floors (>= 1 s) refuse at startup for
    runtime.json AND env overrides."""

    def setUp(self):
        self.saved_test_mode = os.environ.pop("MMOS_CU_TEST_MODE", None)

    def tearDown(self):
        if self.saved_test_mode is None:
            os.environ.pop("MMOS_CU_TEST_MODE", None)
        else:
            os.environ["MMOS_CU_TEST_MODE"] = self.saved_test_mode

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
        # BCU R3 H2: unconditional — a sub-default env value is refused with
        # STRICTER_ONLY (the 180 s floor fires long before the 1 s floor).
        saved = os.environ.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        try:
            os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "0.5"
            with self.assertRaises(mmos.RefuseError) as caught:
                mmos.Presence()
            self.assertEqual(caught.exception.code,
                             "PRESENCE_MIN_IDLE_STRICTER_ONLY")
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
            self.assertEqual(caught.exception.code,
                             "PACING_SECONDS_STRICTER_ONLY")
        finally:
            if saved is None:
                os.environ.pop("MMOS_CU_PACING_SECONDS", None)
            else:
                os.environ["MMOS_CU_PACING_SECONDS"] = saved

    def test_runtime_dict_presence_floor_refused(self):
        # BCU R3 H2: unconditional for the runtime-dict path too.
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(runtime={"presence_min_idle_seconds": 0.5})
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_runtime_dict_pacing_floor_refused(self):
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Pacer(runtime={"pacing_seconds": 0.5})
        self.assertEqual(caught.exception.code, "PACING_SECONDS_STRICTER_ONLY")

    def test_runtime_file_below_default_refused(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): a runtime.json FILE carrying a
        # below-default-but-above-1s threshold (90/60) must refuse at load —
        # the old code accepted anything >= 1.0 from the file.
        tmp = tempfile.mkdtemp(prefix="mmos-cu-rtfile-")
        try:
            bin_path = make_fake_peekaboo(tmp)
            for key, value, code in (
                    ("presence_min_idle_seconds", 90,
                     "RUNTIME_PRESENCE_MIN_IDLE_SECONDS"),
                    ("pacing_seconds", 60, "RUNTIME_PACING_SECONDS")):
                path = os.path.join(tmp, "runtime-%s.json" % key)
                with open(path, "w") as handle:
                    json.dump({"schema": mmos.RUNTIME_SCHEMA,
                               "peekaboo_bin": bin_path,
                               "peekaboo_sha256": mmos.sha256_file(bin_path),
                               key: value}, handle)
                with self.assertRaises(mmos.RefuseError) as caught:
                    mmos.load_runtime(path)
                self.assertEqual(caught.exception.code, code)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestVisionEndpointScheme(unittest.TestCase):
    """H4(c): the vision endpoint is LOOPBACK ONLY (http or https); any other
    host is refused even over https."""

    def test_plain_http_remote_refused(self):
        client = mmos.VisionClient(base_url="http://example.com",
                                   token="injected-token")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "question")
        self.assertEqual(caught.exception.code, "VISION_ENDPOINT_INSECURE")

    def test_https_remote_refused(self):
        client = mmos.VisionClient(base_url="https://example.com",
                                   token="injected-token")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "question")
        self.assertEqual(caught.exception.code, "VISION_ENDPOINT_INSECURE")

    def test_loopback_allowed(self):
        for url in ("http://127.0.0.1:8080", "http://localhost:9000",
                    "http://[::1]:9", "https://127.0.0.1:8443"):
            client = mmos.VisionClient(base_url=url, token="injected-token")
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
        acquire_lease(ctx)
        return ctx

    def test_too_many_hints_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["hint-%d" % i for i in range(21)],
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_overlong_hint_entry_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["x" * 130],
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_total_hint_budget_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "Where is OK?",
            "element_hints": ["y" * 110 for _ in range(12)],
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertTrue(result["isError"])
        self.assertIn("HINTS_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_question_too_long_refused(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "vision_ask", "window_id": 42,
            "question": "q" * 2100, "owner": "agent-a", "lease_nonce": ctx.lease_nonce, "lease_nonce": ctx.lease_nonce})
        self.assertTrue(result["isError"])
        self.assertIn("QUESTION_TOO_LONG", result["content"][0]["text"])
        self.assertEqual(read_calls(ctx), [])

    def test_ask_enforces_question_cap(self):
        client = mmos.VisionClient(base_url="http://127.0.0.1:1", token="t")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNG", "q" * 2100)
        self.assertEqual(caught.exception.code, "QUESTION_TOO_LONG")


class TestLeaseNonce(unittest.TestCase):
    """M5: lease_acquire returns a random nonce; EVERY act must carry it
    (wrong/missing nonce -> LEASE_NONCE_INVALID); lease_status shows only
    sha256(owner)[:12]."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-nonce-")

    def tearDown(self):
        os.environ.pop("FAKE_PEEKABOO_IDENTITY", None)
        os.environ.pop("FAKE_PEEKABOO_LOG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lease(self):
        return mmos.Lease(state_dir=os.path.join(self.tmp, "state"))

    def test_acquire_returns_random_nonce(self):
        lease = self._lease()
        first = lease.acquire("agent-a", ttl_seconds=60)
        self.assertTrue(first.get("nonce"))
        lease.release("agent-a")
        second = lease.acquire("agent-a", ttl_seconds=60)
        self.assertNotEqual(first["nonce"], second["nonce"])

    def test_status_shows_owner_digest_only(self):
        import hashlib
        lease = self._lease()
        lease.acquire("agent-a", ttl_seconds=60)
        status = lease.status()
        expected = hashlib.sha256(b"agent-a").hexdigest()[:12]
        self.assertEqual(status["owner"], expected)
        self.assertNotIn("agent-a", json.dumps(status))

    def test_act_without_nonce_refused(self):
        ctx = build_ctx(self.tmp)
        nonce = acquire_lease(ctx)["nonce"]
        # Wrong nonce: refused, no dispatch.
        bad = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": "wrong"})
        payload = json.loads(bad["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_NONCE_INVALID", payload["cause"])
        self.assertEqual(read_calls(ctx), [])
        # Missing nonce: refused too.
        missing = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a"})
        self.assertIn("LEASE_NONCE_INVALID",
                      missing["content"][0]["text"])
        # Correct nonce: applied.
        good = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": nonce})
        payload = json.loads(good["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")

    def test_version_bumped_to_0_3_0(self):
        self.assertEqual(mmos.SERVER_VERSION, "0.3.0")

    def test_schema_has_lease_nonce(self):
        prop = mmos.TOOL_SCHEMA["properties"].get("lease_nonce")
        self.assertIsInstance(prop, dict)
        self.assertEqual(prop.get("type"), "string")


class TestFiniteNumbers(unittest.TestCase):
    """M1: math.isfinite on every numeric gate threshold and lease TTL;
    NaN/inf never switch a gate off."""

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("MMOS_CU_PRESENCE_MIN_IDLE", "MMOS_CU_PACING_SECONDS",
                       "MMOS_CU_TEST_MODE")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_env_presence_nan_refused(self):
        for bad in ("nan", "inf", "-inf", "NaN", "Infinity"):
            os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = bad
            with self.assertRaises(mmos.RefuseError):
                mmos.Presence()

    def test_env_pacing_nan_refused(self):
        for bad in ("nan", "inf", "-inf"):
            os.environ["MMOS_CU_PACING_SECONDS"] = bad
            with self.assertRaises(mmos.RefuseError):
                mmos.Pacer()

    def test_runtime_nan_presence_refused(self):
        with self.assertRaises(mmos.RefuseError):
            mmos.Presence(runtime={"presence_min_idle_seconds": float("nan")})

    def test_runtime_nan_pacing_refused(self):
        with self.assertRaises(mmos.RefuseError):
            mmos.Pacer(runtime={"pacing_seconds": float("inf")})

    def test_ttl_nan_refused(self):
        lease = mmos.Lease(state_dir=os.path.join(self.tmpdir()))
        for bad in (float("nan"), float("inf"), "nan", "inf"):
            with self.assertRaises(mmos.OpError) as caught:
                lease.acquire("agent-a", ttl_seconds=bad)
            self.assertEqual(caught.exception.code, "LEASE_TTL_INVALID")

    def tmpdir(self):
        if not hasattr(self, "_tmp"):
            self._tmp = tempfile.mkdtemp(prefix="mmos-cu-finite-")
        return self._tmp


class TestEnvStrictness(unittest.TestCase):
    """M2 + BCU R3 H2: gate env vars may only make gates STRICTER than the
    180 s defaults — UNCONDITIONALLY, with no test-mode escape; state/deny/
    runtime env paths may only point inside the layer's own folder."""

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("MMOS_CU_PRESENCE_MIN_IDLE", "MMOS_CU_PACING_SECONDS",
                       "MMOS_CU_TEST_MODE", "MMOS_CU_STATE_DIR",
                       "MMOS_CU_DENY", "MMOS_CU_RUNTIME")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_presence_below_default_refused(self):
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "90"
        with self.assertRaises(mmos.RefuseError):
            mmos.Presence()

    def test_marker_and_pytest_do_not_unlock_env_floors(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): the R2 "harness" was
        # MMOS_CU_TEST_MODE=1 AND pytest-in-sys.modules — and THIS test runs
        # inside pytest, i.e. in exactly the context the old escape treated
        # as the harness (a session can forge it via PYTHONPATH/
        # sitecustomize). The floor must hold anyway: no flag unlocks it.
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "90"
        os.environ["MMOS_CU_TEST_MODE"] = "1"
        self.assertIn("pytest", sys.modules)  # the old decisive condition
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence()
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_pacing_below_default_refused(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "90"
        with self.assertRaises(mmos.RefuseError):
            mmos.Pacer()

    def test_pacing_at_or_above_default_ok(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "180"
        self.assertEqual(mmos.Pacer().seconds, 180.0)

    def test_state_dir_outside_layer_refused(self):
        os.environ["MMOS_CU_STATE_DIR"] = "/tmp/mmos-cu-outside-state"
        with self.assertRaises(mmos.RefuseError):
            mmos.Lease()

    def test_state_dir_inside_layer_ok(self):
        os.environ["MMOS_CU_STATE_DIR"] = os.path.join(
            mmos.HERE, "state-test")
        lease = mmos.Lease()
        self.assertTrue(lease.state_dir.startswith(mmos.HERE))
        shutil.rmtree(lease.state_dir, ignore_errors=True)

    def test_deny_outside_layer_refused(self):
        os.environ["MMOS_CU_DENY"] = "/tmp/other-deny.json"
        with self.assertRaises(mmos.RefuseError):
            mmos.build_context()


class TestConfirmAfterHumanActive(unittest.TestCase):
    """H2: once the act has completed, a human becoming active before the
    CONFIRM step must never turn the receipt into NOT_APPLIED. It is APPLIED
    with confirm_skipped="HUMAN_ACTIVE" (or EFFECT_UNKNOWN)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-confirm-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOW_ELEMENT",
                    "FAKE_PEEKABOO_FIELD_VALUE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        acquire_lease(ctx)
        return ctx

    def test_slice_paste_human_active_at_confirm_is_applied(self):
        os.environ["FAKE_PEEKABOO_FIELD_VALUE"] = "hello there"
        ctx = self._ctx(presence_sequence=[
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 1.0, "human_active": True}])
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "text": "hello there",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertNotEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(payload.get("confirm_skipped"), "HUMAN_ACTIVE")
        # The paste itself did dispatch exactly once; confirm was skipped.
        self.assertEqual(len([c for c in read_calls(ctx) if c[0] == "paste"]),
                         1)

    def test_slice_front_human_active_at_confirm_is_applied(self):
        os.environ["FAKE_PEEKABOO_WINDOW_ELEMENT"] = "1"
        ctx = self._ctx(presence_sequence=[
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 30.0, "human_active": False},
            {"human_idle_seconds": 1.0, "human_active": True}])
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_front", "app": "TextEdit", "window_id": 42,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(payload.get("confirm_skipped"), "HUMAN_ACTIVE")
        self.assertEqual(
            len([c for c in read_calls(ctx)
                 if c[:2] == ["window", "focus"]]), 1)


class TestSharedActGate(unittest.TestCase):
    """H3: ONE shared pre-act gate runs the challenge scan AND pacing for
    every act that can change a page or send."""

    ACT_CASES = {
        "press": {"window_id": 42, "element_ref": "btn1"},
        "set_text": {"window_id": 42, "element_ref": "field1",
                     "text": "hello"},
        "keys": {"window_id": 42, "chord": "return"},
        "scroll": {"window_id": 42, "direction": "down", "amount": 2},
        "pointer_click": {"window_id": 42, "element_ref": "btn1"},
        "slice_click": {"window_id": 42, "element_ref": "btn1"},
        "slice_paste": {"window_id": 42, "text": "hello there"},
        "slice_send": {"window_id": 42, "element_ref": "btn1"},
    }
    DISPATCH_COMMANDS = {"click", "press", "action", "set-value", "paste",
                         "scroll"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-ga-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_CHALLENGE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self, **kwargs):
        ctx = build_ctx(self.tmp, **kwargs)
        acquire_lease(ctx)
        return ctx

    def _call(self, ctx, op, extra):
        args = {"action": op, "owner": "agent-a",
                "lease_nonce": ctx.lease_nonce}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def test_challenge_refuses_every_act_with_zero_dispatches(self):
        os.environ["FAKE_PEEKABOO_CHALLENGE"] = \
            "Security notice: verify unusual activity on your account"
        for op, extra in self.ACT_CASES.items():
            ctx = self._ctx()
            payload = json.loads(self._call(ctx, op, extra)["content"][0]
                                 ["text"])
            self.assertEqual(payload["status"], "NOT_APPLIED",
                             "%s: %r" % (op, payload))
            self.assertIn("CHALLENGE_DETECTED", payload["cause"],
                          "%s: %r" % (op, payload))
            dispatched = [c for c in read_calls(ctx)
                          if c[0] in self.DISPATCH_COMMANDS]
            self.assertEqual(dispatched, [], "%s dispatched: %r"
                             % (op, dispatched))

    def test_two_keys_return_inside_interval_waits(self):
        ctx = self._ctx(pacing_seconds=180.0)
        first = json.loads(self._call(ctx, "keys", {
            "window_id": 42, "chord": "return"})["content"][0]["text"])
        self.assertEqual(first["status"], "APPLIED", first)
        second = json.loads(self._call(ctx, "keys", {
            "window_id": 42, "chord": "return"})["content"][0]["text"])
        self.assertEqual(second["status"], "NOT_APPLIED", second)
        self.assertIn("PACING_WAIT", second["cause"])
        self.assertEqual(len([c for c in read_calls(ctx) if c[0] == "press"]),
                         1)

    def test_two_presses_inside_interval_waits(self):
        ctx = self._ctx(pacing_seconds=180.0)
        first = json.loads(self._call(ctx, "press", {
            "window_id": 42, "element_ref": "btn1"})["content"][0]["text"])
        self.assertEqual(first["status"], "APPLIED", first)
        second = json.loads(self._call(ctx, "press", {
            "window_id": 42, "element_ref": "btn1"})["content"][0]["text"])
        self.assertEqual(second["status"], "NOT_APPLIED", second)
        self.assertIn("PACING_WAIT", second["cause"])
        self.assertEqual(len([c for c in read_calls(ctx)
                              if c[0] == "action"]), 1)


PNG_MAGIC = "\x89PNG"
PNG_B64_PREFIX = "iVBORw0KGgo"


class TestNoImageInReplies(unittest.TestCase):
    """H4 (principal ruling): NO image bytes in any MCP/CLI reply. capture and
    slice_look return metadata + AX text only; keep_path is gone from the
    schema and refused as an argument."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-h4-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOW_ELEMENT"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def _assert_text_only(self, result, label):
        self.assertNotIsInstance(result.get("content"), type(None))
        for block in result["content"]:
            self.assertEqual(block.get("type"), "text",
                             "%s: non-text content block %r" % (label, block))
        dumped = json.dumps(result)
        self.assertNotIn('"type": "image"', dumped, label)
        self.assertNotIn(PNG_MAGIC, dumped, label)
        self.assertNotIn(PNG_B64_PREFIX, dumped, label)

    def test_capture_returns_metadata_only(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {"action": "capture",
                                             "window_id": 42})
        self.assertFalse(result["isError"], result)
        self._assert_text_only(result, "capture")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["bytes"], 19)  # PNG length only, not bytes
        self.assertFalse(payload["image_returned"])

    def test_slice_look_returns_ax_text_only(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_look", "window_id": 42,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        self.assertFalse(result["isError"], result)
        self._assert_text_only(result, "slice_look")
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertIn("tree", payload)

    def test_every_op_reply_is_text_only(self):
        os.environ["FAKE_PEEKABOO_WINDOW_ELEMENT"] = "1"
        cases = [
            ("apps", {}),
            ("windows", {"app": "TextEdit"}),
            ("inspect", {"window_id": 42}),
            ("capture", {"window_id": 42}),
            ("press", {"window_id": 42, "element_ref": "btn1"}),
            ("set_text", {"window_id": 42, "element_ref": "field1",
                          "text": "hi"}),
            ("keys", {"window_id": 42, "chord": "down"}),
            ("scroll", {"window_id": 42, "direction": "down"}),
            ("pointer_click", {"window_id": 42, "element_ref": "btn1"}),
            ("slice_front", {"app": "TextEdit", "window_id": 42}),
            ("slice_click", {"window_id": 42, "element_ref": "btn1"}),
            ("slice_send", {"window_id": 42, "element_ref": "btn1"}),
            ("slice_look", {"window_id": 42}),
            ("presence", {}),
        ]
        for op, extra in cases:
            tmp = tempfile.mkdtemp(prefix="mmos-cu-h4-%s-" % op)
            try:
                ctx = build_ctx(tmp)
                acquire_lease(ctx)
                args = {"action": op, "owner": "agent-a",
                        "lease_nonce": ctx.lease_nonce}
                args.update(extra)
                result = mmos.handle_tool_call(ctx, args)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            self._assert_text_only(result, op)

    def test_keep_path_removed_from_schema(self):
        self.assertNotIn("keep_path", mmos.TOOL_SCHEMA["properties"])
        self.assertFalse(hasattr(mmos, "validate_keep_path"))

    def test_keep_path_argument_refused_before_capture(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "capture", "window_id": 42, "keep_path": "/tmp/x.png"})
        self.assertTrue(result["isError"], result)
        text = result["content"][0]["text"]
        self.assertIn("INVALID_ARGUMENTS", text)
        self.assertIn("keep_path", text)
        # Nothing was captured (no see --path dispatch).
        self.assertEqual([c for c in read_calls(ctx) if "--path" in c], [])


class TestVisionEndpointLoopbackOnly(unittest.TestCase):
    """H4(c): the vision endpoint must be loopback (localhost / 127.0.0.1 /
    ::1); any other host is refused even over https."""

    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeVisionHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_https_remote_host_refused(self):
        client = mmos.VisionClient(base_url="https://example.com",
                                   token="injected-token")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNGfake", "question")
        self.assertEqual(caught.exception.code, "VISION_ENDPOINT_INSECURE")

    def test_http_remote_host_refused(self):
        client = mmos.VisionClient(base_url="http://example.com",
                                   token="injected-token")
        with self.assertRaises(mmos.OpError) as caught:
            client.ask(b"\x89PNGfake", "question")
        self.assertEqual(caught.exception.code, "VISION_ENDPOINT_INSECURE")

    def test_loopback_http_accepted(self):
        client = mmos.VisionClient(
            base_url="http://127.0.0.1:%d" % self.port,
            token="injected-token")
        result = client.ask(b"\x89PNGfake", "Where is OK?")
        self.assertIn("OK", result["answer"])
        self.assertEqual(FakeVisionHandler.seen["x_api_key"],
                         "injected-token")


class TestDenyListNewEntries(unittest.TestCase):
    """M6: the built-in list gains the named password managers and settings
    surfaces (names + bundle ids), title_regexes match window titles, and a
    deny.json file ADDS to the defaults instead of replacing them."""

    NEW_NAMES = ["KeePassXC", "LastPass", "SecurityAgent",
                 "System Preferences", "Proton Pass", "Keeper", "Enpass",
                 "Strongbox", "Dashlane"]
    NEW_BUNDLES = ["org.keepassxc.keepassxc", "com.lastpass.LastPass",
                   "com.agilebits.onepassword7", "com.apple.SecurityAgent",
                   "me.proton.pass", "com.km.keeperdesktop",
                   "in.sinew.enpass", "com.dashlane.dashlane"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-deny-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self, payload=None, name="deny.json"):
        path = os.path.join(self.tmp, name)
        if payload is not None:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        else:
            path = os.path.join(TOOL_DIR, "deny.json")
        return mmos.DenyList.load(path), path

    def test_each_new_name_is_denied(self):
        deny, _ = self._load()
        for name in self.NEW_NAMES:
            self.assertEqual(deny.matches(name, None, None), "app_name", name)

    def test_each_new_bundle_is_denied(self):
        deny, _ = self._load()
        for bundle in self.NEW_BUNDLES:
            self.assertEqual(deny.matches(None, bundle, None), "bundle_id",
                             bundle)

    def test_title_regexes_refuse(self):
        deny, _ = self._load()
        for title in ("Passwords", "SAVED PASSWORDS", "Unlock with passkey",
                      "Settings/Passwords"):
            self.assertEqual(deny.matches("TextEdit", None, title),
                             "title_regex", title)

    def test_shipped_deny_json_present(self):
        deny, path = self._load()
        self.assertIsInstance(deny, mmos.DenyList)
        self.assertTrue(os.path.isfile(path))

    def test_file_adds_to_defaults_union(self):
        deny, _ = self._load({
            "schema": mmos.DENY_SCHEMA,
            "app_names": ["CustomApp"],
            "bundle_ids": ["com.example.custom"],
            "title_regexes": ["vault code"],
        })
        self.assertEqual(deny.matches("CustomApp", None, None), "app_name")
        self.assertEqual(deny.matches(None, "com.example.custom"),
                         "bundle_id")
        self.assertEqual(deny.matches(None, None, "Vault Code"), "title_regex")
        # Defaults are still present.
        self.assertEqual(deny.matches("1Password", None, None), "app_name")
        self.assertEqual(deny.matches("KeePassXC", None, None), "app_name")
        self.assertEqual(deny.matches(None, None, "Saved Passwords"),
                         "title_regex")

    def test_empty_file_means_defaults_only(self):
        deny, _ = self._load({"schema": mmos.DENY_SCHEMA})
        self.assertEqual(deny.matches("1Password", None, None), "app_name")
        self.assertEqual(deny.matches("SomeDocument", None, "Notes"), None)

    def test_matching_normalizes_unicode_nfc_and_case(self):
        deny, _ = self._load({
            "schema": mmos.DENY_SCHEMA,
            "app_names": ["Café"],
        })
        # NFD spelling of the same string must match the NFC entry.
        self.assertEqual(deny.matches("Café", None, None), "app_name")
        self.assertEqual(deny.matches("CAFÉ", None, None), "app_name")

    def test_windows_op_applies_title_regexes(self):
        ctx = build_ctx(self.tmp, deny=mmos.DenyList.load(
            os.path.join(TOOL_DIR, "deny.json")))
        acquire_lease(ctx)
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Saved Passwords", "owner_pid": 101}]'
        try:
            result = mmos.handle_tool_call(ctx, {"action": "windows",
                                                 "app": "TextEdit"})
        finally:
            os.environ.pop("FAKE_PEEKABOO_WINDOWS_JSON", None)
        self.assertIn("DENY_LISTED", result["content"][0]["text"])

    def test_slice_front_applies_title_regexes(self):
        ctx = build_ctx(self.tmp, deny=mmos.DenyList.load(
            os.path.join(TOOL_DIR, "deny.json")), identity=(
            '"app": "TextEdit", "bundle_id": "com.apple.TextEdit", '
            '"window_title": "Passwords"'))
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_front", "app": "TextEdit", "window_id": 42,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        self.assertIn("DENY_LISTED", result["content"][0]["text"])

    def test_slice_front_window_id_app_mismatch(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        # window list --app TextEdit only knows window 42.
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_front", "app": "TextEdit", "window_id": 999,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        text = result["content"][0]["text"]
        self.assertIn("WINDOW_APP_MISMATCH", text)


class TestLeaseCriticalSection(unittest.TestCase):
    """M3/M4: read+check+write happen inside the O_EXCL critical section; a
    takeover interleaved between read and write is detected and refused, and
    a pre-existing lock is a typed LEASE_CONTENDED (never INTERNAL) while a
    stale lock (dead owner or old age) is recovered."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-lock-")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)
        self.lease = mmos.Lease(state_dir=self.state)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _acquired(self):
        result = self.lease.acquire("agent-a", ttl_seconds=60)
        return result["nonce"]

    def test_takeover_between_read_and_write_detected(self):
        nonce = self._acquired()
        real_write = mmos._atomic_write

        def sabotaged(path, payload):
            real_write(path, payload)
            if payload.get("owner") == "agent-a":
                # A non-cooperating writer lands a foreign hold right after
                # our write (simulated interleave inside the section).
                real_write(path, {"owner": "agent-b", "nonce": "foreign",
                                  "acquired_at": time.time(),
                                  "expires_at": time.time() + 60})

        mmos._atomic_write = sabotaged
        try:
            with self.assertRaises(mmos.OpError) as caught:
                self.lease.require_and_renew("agent-a", nonce=nonce)
        finally:
            mmos._atomic_write = real_write
        self.assertEqual(caught.exception.code, "LEASE_CONTENDED")

    def test_renewal_holds_lock_across_read_and_write(self):
        nonce = self._acquired()
        seen = []
        real_read = self.lease._read

        def recording_read():
            seen.append(os.path.exists(self.lease.lock_path))
            return real_read()

        self.lease._read = recording_read
        try:
            self.lease.require_and_renew("agent-a", nonce=nonce)
        finally:
            self.lease._read = real_read
        self.assertTrue(seen and all(seen),
                        "read must happen under the lease.lock: %r" % seen)
        self.assertFalse(os.path.exists(self.lease.lock_path))

    def _write_lock(self, payload):
        with open(self.lease.lock_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_existing_live_lock_is_typed_contention(self):
        self._write_lock({"pid": os.getpid(), "created_at": time.time()})
        with self.assertRaises(mmos.OpError) as caught:
            self.lease.acquire("agent-a", ttl_seconds=60)
        self.assertEqual(caught.exception.code, "LEASE_CONTENDED")
        # And through the handler this is a typed receipt, never INTERNAL.
        ctx = build_ctx(self.tmp)
        ctx.lease = self.lease
        payload = json.loads(mmos.handle_tool_call(
            ctx, {"action": "lease_acquire", "owner": "agent-a",
                  "ttl_seconds": 60})["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_CONTENDED", payload["cause"])

    def test_stale_lock_dead_owner_recovered(self):
        self._write_lock({"pid": 999999, "created_at": time.time()})
        result = self.lease.acquire("agent-a", ttl_seconds=60)
        self.assertTrue(result["held"])
        self.assertFalse(os.path.exists(self.lease.lock_path))

    def test_stale_lock_by_age_recovered(self):
        self._write_lock({"pid": os.getpid(),
                          "created_at": time.time() - 3600})
        result = self.lease.acquire("agent-a", ttl_seconds=60)
        self.assertTrue(result["held"])

    def test_unparseable_old_lock_recovered(self):
        with open(self.lease.lock_path, "w", encoding="utf-8") as handle:
            handle.write("not json")
        old = time.time() - 3600
        os.utime(self.lease.lock_path, (old, old))
        result = self.lease.acquire("agent-a", ttl_seconds=60)
        self.assertTrue(result["held"])

    def test_release_takes_the_lock(self):
        self._acquired()
        seen = []
        real_read = self.lease._read

        def recording_read():
            seen.append(os.path.exists(self.lease.lock_path))
            return real_read()

        self.lease._read = recording_read
        try:
            self.lease.release("agent-a")
        finally:
            self.lease._read = real_read
        self.assertTrue(seen and all(seen))
        self.assertFalse(os.path.exists(self.lease.lease_path))


class TestEqualSignValues(unittest.TestCase):
    """M11-CODE: values travel in the option form --text=<v> / --value=<v> /
    --app=<v>, so a leading "-" can never be parsed as a flag."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-m11-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def test_paste_text_leading_dash_is_one_token(self):
        ctx = self._ctx()
        mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "text": "-rf /",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        paste = [c for c in read_calls(ctx) if c[0] == "paste"][0]
        self.assertIn("--text=-rf /", paste)
        self.assertNotIn("-rf /", paste)  # never a bare token
        self.assertNotIn("--text", paste)

    def test_set_text_value_leading_dash_is_one_token(self):
        ctx = self._ctx()
        mmos.handle_tool_call(ctx, {
            "action": "set_text", "window_id": 42, "element_ref": "field1",
            "text": "-rf /", "owner": "agent-a",
            "lease_nonce": ctx.lease_nonce})
        call = [c for c in read_calls(ctx) if c[0] == "set-value"][0]
        self.assertIn("--value=-rf /", call)
        self.assertNotIn("-rf /", call)
        self.assertNotIn("--value", call)

    def test_app_leading_dash_is_one_token(self):
        ctx = self._ctx()
        mmos.handle_tool_call(ctx, {"action": "windows", "app": "-x"})
        call = [c for c in read_calls(ctx) if c[0] == "window"][0]
        self.assertIn("--app=-x", call)
        self.assertNotIn("-x", call)
        self.assertNotIn("--app", call)


class TestForegroundOptInOnly(unittest.TestCase):
    """M10-CODE: no automatic foreground fallback chosen by error-text
    matching. Foreground is dispatched only because the caller opted in, and
    then as the ONE dispatch; with the flag unset a FOREGROUND_REQUIRED
    failure is terminal after exactly one dispatch, and its receipt status
    comes ONLY from peekaboo's structured result (BCU R2 item 3):
    NOT_APPLIED when nothing was provably dispatched, else EFFECT_UNKNOWN."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-fg-")
        os.environ["FAKE_PEEKABOO_FOREGROUND_REQUIRED"] = "1"

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_FOREGROUND_REQUIRED",
                    "FAKE_PEEKABOO_FOREGROUND_REFUSED",
                    "FAKE_PEEKABOO_FIXTURES"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def test_unset_flag_is_one_dispatch_effect_unknown(self):
        # BCU R2 item 3: the legacy `errors` list carries no structured
        # mutation_dispatched field, so this is EFFECT_UNKNOWN (terminal, one
        # dispatch). test_keys_real_error_shape_is_clean_refusal below covers
        # the structured case that still yields NOT_APPLIED.
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN", payload)
        self.assertIn("FOREGROUND_REQUIRED", payload["cause"])
        actions = [c for c in read_calls(ctx) if c[0] == "action"]
        self.assertEqual(len(actions), 1)  # exactly ONE dispatch, no retry
        self.assertNotIn("--foreground", actions[0])

    def test_opt_in_dispatches_foreground_directly(self):
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
            "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertTrue(payload.get("foreground"))
        actions = [c for c in read_calls(ctx) if c[0] == "action"]
        self.assertEqual(len(actions), 1)  # one foreground dispatch only
        self.assertIn("--foreground", actions[0])

    def test_keys_dispatch_carries_window_selector(self):
        # Targetless background press is refused by peekaboo (rc=1, no
        # structured error — M10 live red); the keys dispatch must carry the
        # exact --window-id alongside the snapshot receipt. BCU R2 item 3:
        # the refusal here is the STRUCTURED shape (mutation_dispatched
        # false), so the terminal receipt is NOT_APPLIED; the text-only shape
        # is EFFECT_UNKNOWN (test_unset_flag_is_one_dispatch_effect_unknown).
        os.environ["FAKE_PEEKABOO_FOREGROUND_REFUSED"] = "1"
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertIn(payload["status"], ("APPLIED", "NOT_APPLIED"), payload)
        presses = [c for c in read_calls(ctx) if c[0] == "press"]
        self.assertEqual(len(presses), 1)
        argv = presses[0]
        i = argv.index("--window-id")
        self.assertEqual(argv[i + 1], "42")
        self.assertIn("--snapshot", argv)

    def test_keys_real_error_shape_is_clean_refusal(self):
        # M10 live root cause: the real CLI reports a foreground refusal as
        # success:false + error:{code,message} (an OBJECT, not the legacy
        # errors list) — real capture press_foreground_required_error.json.
        # Classification must read that message and return a clean
        # FOREGROUND_REQUIRED/NOT_APPLIED after ONE dispatch, never
        # EFFECT_UNKNOWN.
        os.environ["FAKE_PEEKABOO_FIXTURES"] = FIXTURE_DIR
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("FOREGROUND_REQUIRED", payload["cause"])
        presses = [c for c in read_calls(ctx) if c[0] == "press"]
        self.assertEqual(len(presses), 1)  # one dispatch, no retry
        self.assertNotIn("--foreground", presses[0])

    def test_keys_real_shape_opt_in_dispatches_foreground_once(self):
        # With the opt-in flag the ONE dispatch carries --foreground (the
        # fixture replay only fires without it) and reports APPLIED.
        os.environ["FAKE_PEEKABOO_FIXTURES"] = FIXTURE_DIR
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce,
            "allow_foreground": True})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertTrue(payload.get("foreground"))
        presses = [c for c in read_calls(ctx) if c[0] == "press"]
        self.assertEqual(len(presses), 1)
        self.assertIn("--foreground", presses[0])


class TestDenyOverlayGate(unittest.TestCase):
    """H6-INTERIM: a coordinate click is refused whenever any deny-listed app
    has ANY on-screen window (checked via app list + window list at click
    time), with the cause naming that app."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-overlay-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_ONPW_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def test_coordinate_click_refused_when_denied_app_has_window(self):
        os.environ["FAKE_PEEKABOO_ONPW_WINDOWS_JSON"] = \
            '[{"window_id": 99, "title": "Vault", "owner_pid": 102}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("DENY_OVERLAY", payload["cause"])
        self.assertIn("1Password", payload["cause"])
        # Zero click dispatch: the refusal is pre-dispatch.
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_slice_click_coordinate_refused_same(self):
        os.environ["FAKE_PEEKABOO_ONPW_WINDOWS_JSON"] = \
            '[{"window_id": 99, "title": "Vault", "owner_pid": 102}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("DENY_OVERLAY", payload["cause"])
        self.assertIn("1Password", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_coordinate_click_proceeds_when_denied_app_absent(self):
        # Default fake: 1Password has no windows.
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(len([c for c in read_calls(ctx) if c[0] == "click"]),
                         1)

    def test_element_click_is_not_overlay_gated(self):
        os.environ["FAKE_PEEKABOO_ONPW_WINDOWS_JSON"] = \
            '[{"window_id": 99, "title": "Vault", "owner_pid": 102}]'
        ctx = self._ctx()
        payload = json.loads(mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42,
            "element_ref": "btn1", "owner": "agent-a",
            "lease_nonce": ctx.lease_nonce})["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)


class TestH6FrontmostGate(unittest.TestCase):
    """H6 (full): a coordinate click requires the target window to be the
    globally frontmost window at click time — any window above it could
    intercept the click. `window list` reports per-window `is_frontmost`;
    the real capture (tests/fixtures/peekaboo/window_list_fixture.json)
    shows is_frontmost:false whenever a window sits above, so
    is_frontmost:true proves no window can cover the point. Missing
    evidence fails closed. Element-targeted clicks are unaffected."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-h6full-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOWS_JSON",
                    "FAKE_PEEKABOO_APP_AMBIGUOUS",
                    "FAKE_PEEKABOO_APP_AMBIGUOUS_APP",
                    "FAKE_PEEKABOO_PID_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def test_coordinate_click_refused_when_not_frontmost(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101,' \
            ' "is_frontmost": false, "window_index": 14, "is_key": true}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_NOT_FRONTMOST", payload["cause"])
        # Zero click dispatch: the refusal is pre-dispatch.
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_slice_click_coordinates_refused_when_not_frontmost(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101,' \
            ' "is_frontmost": false, "window_index": 14, "is_key": true}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_NOT_FRONTMOST", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_coordinate_click_dispatches_when_frontmost(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101,' \
            ' "is_frontmost": true, "window_index": 0, "is_key": true}]'
        ctx = self._ctx()
        payload = json.loads(mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
            ["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(len([c for c in read_calls(ctx) if c[0] == "click"]),
                         1)

    def test_coordinate_click_refused_when_window_missing(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 7, "title": "Other", "owner_pid": 101,' \
            ' "is_frontmost": true, "window_index": 0}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_GONE", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_frontmost_missing_fails_closed(self):
        # Real capture shape always carries is_frontmost; a row without it
        # (unexpected adapter) must not silently pass the gate.
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_NOT_FRONTMOST", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_ambiguous_app_resolves_via_pid_fallback(self):
        """Real-host shape: several processes share the app name, so
        `window list --app` fails (AMBIGUOUS_APP_IDENTIFIER); the gate must
        resolve the owning pid via app list + per-pid window list and still
        decide on is_frontmost evidence."""
        os.environ["FAKE_PEEKABOO_IDENTITY"] = \
            '"app": "TextEdit", "bundle_id": "com.apple.TextEdit", ' \
            '"window_title": "Untitled"'
        os.environ["FAKE_PEEKABOO_APP_AMBIGUOUS"] = "1"
        os.environ["FAKE_PEEKABOO_PID_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101,' \
            ' "is_frontmost": false, "window_index": 7}]'
        ctx = self._ctx()
        result = mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42, "x": 10, "y": 20,
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_NOT_FRONTMOST", payload["cause"])
        self.assertIn("is_frontmost=False", payload["cause"])
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "click"], [])

    def test_element_click_not_frontmost_gated(self):
        # Element resolution pins the target through the snapshot; the
        # frontmost gate is coordinate-path only (as with DENY_OVERLAY).
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = \
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101,' \
            ' "is_frontmost": false, "window_index": 14}]'
        ctx = self._ctx()
        payload = json.loads(mmos.handle_tool_call(ctx, {
            "action": "pointer_click", "window_id": 42,
            "element_ref": "btn1", "owner": "agent-a",
            "lease_nonce": ctx.lease_nonce})["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED", payload)


class TestPacingKeyIdentity(unittest.TestCase):
    """BCU R2 item 4 (R-M3): the pacing key is (owning pid + exact window id),
    never app name or window title. A title change on the SAME window must not
    reset the interval, and an unreadable window id is refused, typed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-m8-")
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOWS_JSON"):
            os.environ.pop(key, None)

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp, pacing_seconds=180.0)
        acquire_lease(ctx)
        return ctx

    def _keys(self, ctx, window_id):
        return json.loads(mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": window_id, "chord": "return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})["content"][0]
            ["text"])

    def test_title_change_does_not_reset_the_interval(self):
        os.environ["FAKE_PEEKABOO_IDENTITY"] = IDENTITY_TEXTEDIT
        ctx = self._ctx()
        first = self._keys(ctx, 42)
        self.assertEqual(first["status"], "APPLIED", first)
        # Same pid + same window id, DIFFERENT title (the document was saved
        # under a new name). The pace target did not change.
        os.environ["FAKE_PEEKABOO_IDENTITY"] = (
            '"app": "TextEdit", "bundle_id": "com.apple.TextEdit", '
            '"window_title": "Report.rtf"')
        second = self._keys(ctx, 42)
        self.assertEqual(second["status"], "NOT_APPLIED", second)
        self.assertIn("PACING_WAIT", second["cause"])
        self.assertEqual(len([c for c in read_calls(ctx) if c[0] == "press"]),
                         1)

    def test_a_different_window_is_a_different_pace_target(self):
        os.environ["FAKE_PEEKABOO_WINDOWS_JSON"] = (
            '[{"window_id": 42, "title": "Untitled", "owner_pid": 101, '
            '"is_frontmost": true, "window_index": 0, "is_key": true}, '
            '{"window_id": 43, "title": "Untitled", "owner_pid": 101, '
            '"is_frontmost": true, "window_index": 1, "is_key": false}]')
        ctx = self._ctx()
        self.assertEqual(self._keys(ctx, 42)["status"], "APPLIED")
        # Exact window id is part of the identity: a different window of the
        # same app is a different target, so it is not paced against 42.
        self.assertEqual(self._keys(ctx, 43)["status"], "APPLIED")

    def test_key_is_owning_pid_plus_exact_window_id(self):
        self.assertEqual(mmos.pacing_key(42, 101), "pid:101|window:42")
        self.assertNotEqual(mmos.pacing_key(42, 101),
                            mmos.pacing_key(43, 101))
        self.assertNotEqual(mmos.pacing_key(42, 101),
                            mmos.pacing_key(42, 102))

    def test_unreadable_window_id_is_refused_typed(self):
        for bad in (None, "42", 42.0, True):
            with self.assertRaises(mmos.OpError) as caught:
                mmos.pacing_key(bad, 101)
            self.assertEqual(caught.exception.code, "WINDOW_ID_REQUIRED",
                             "for %r" % (bad,))


class TestSliceStepsAndStateWrite(unittest.TestCase):
    """M9: every slice receipt carries completed steps; a pacing/lease state
    write OSError AFTER a dispatched act still returns the APPLIED act
    receipt with state_write:"failed" (never REFUSED/INTERNAL)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-m9-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOW_ELEMENT",
                    "FAKE_PEEKABOO_FIELD_VALUE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def _call(self, ctx, op, extra):
        args = {"action": op, "owner": "agent-a",
                "lease_nonce": ctx.lease_nonce}
        args.update(extra)
        result = mmos.handle_tool_call(ctx, args)
        return result, json.loads(result["content"][0]["text"])

    def _fail_record(self, ctx):
        def boom(*_a, **_k):
            raise OSError("cannot write pacing.json (disk full)")
        ctx.pacer.record = boom

    def test_every_slice_receipt_carries_steps(self):
        os.environ["FAKE_PEEKABOO_WINDOW_ELEMENT"] = "1"
        os.environ["FAKE_PEEKABOO_FIELD_VALUE"] = "hello there"
        cases = {
            "slice_front": {"app": "TextEdit", "window_id": 42},
            "slice_click": {"window_id": 42, "element_ref": "btn1"},
            "slice_paste": {"window_id": 42, "text": "hello there"},
            "slice_send": {"window_id": 42, "element_ref": "btn1"},
        }
        for op, extra in cases.items():
            # Fresh state dir per op: one paced act per identity (M8).
            tmp = tempfile.mkdtemp(prefix="mmos-cu-m9-%s-" % op)
            try:
                ctx = build_ctx(tmp)
                acquire_lease(ctx)
                _result, payload = self._call(ctx, op, extra)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            self.assertEqual(payload["status"], "APPLIED", "%s: %r"
                             % (op, payload))
            steps = payload.get("steps")
            self.assertIsInstance(steps, list, "%s: %r" % (op, payload))
            self.assertTrue(any(s.startswith("observe") for s in steps),
                            "%s: %r" % (op, steps))
            self.assertTrue(any(s.startswith("act") for s in steps),
                            "%s: %r" % (op, steps))

    def test_press_state_write_failure_keeps_applied(self):
        ctx = self._ctx()
        self._fail_record(ctx)
        result, payload = self._call(ctx, "press", {
            "window_id": 42, "element_ref": "btn1"})
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(payload.get("state_write"), "failed")
        self.assertFalse(result["isError"])

    def test_slice_paste_state_write_failure_keeps_applied(self):
        ctx = self._ctx()
        self._fail_record(ctx)
        _result, payload = self._call(ctx, "slice_paste", {
            "window_id": 42, "text": "hello there"})
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(payload.get("state_write"), "failed")

    def test_slice_send_state_write_failure_keeps_applied(self):
        ctx = self._ctx()
        self._fail_record(ctx)
        _result, payload = self._call(ctx, "slice_send", {
            "window_id": 42, "element_ref": "btn1"})
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertEqual(payload.get("state_write"), "failed")


class TestDispatchFailureEffectUnknown(unittest.TestCase):
    """H1: once a dispatch has STARTED, a failure is EFFECT_UNKNOWN for EVERY
    act op (never NOT_APPLIED), unless it is a proven pre-dispatch refusal."""

    ACT_CASES = {
        "press": {"window_id": 42, "element_ref": "btn1"},
        "set_text": {"window_id": 42, "element_ref": "field1",
                     "text": "hello"},
        "keys": {"window_id": 42, "chord": "return"},
        "scroll": {"window_id": 42, "direction": "down", "amount": 2},
        "pointer_click": {"window_id": 42, "element_ref": "btn1"},
        "slice_front": {"app": "TextEdit", "window_id": 42},
        "slice_click": {"window_id": 42, "element_ref": "btn1"},
        "slice_send": {"window_id": 42, "element_ref": "btn1"},
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-h1-")
        os.environ["FAKE_PEEKABOO_ACT_FAIL"] = "1"

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_ACT_FAIL", "FAKE_PEEKABOO_PASTE_FAIL",
                    "FAKE_PEEKABOO_REFUSAL_NO_MUTATION",
                    "FAKE_PEEKABOO_NO_AX_ACTION",
                    "FAKE_PEEKABOO_SNAPSHOT_STALE"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ax_visible_but_not_actionable_is_typed_not_applied(self):
        # Live red (rehearsal round 3, 2026-11-12): the Tk Send button is
        # AX-VISIBLE but not AX-ACTIONABLE; peekaboo returns rc=1
        # INTERNAL_SWIFT_ERROR "No accessibility element is available for
        # action invocation" — nothing was invoked. The receipt said
        # EFFECT_UNKNOWN (uncertain effect for a refusal that dispatched
        # nothing); it must be a typed ELEMENT_NOT_ACTIONABLE NOT_APPLIED.
        os.environ.pop("FAKE_PEEKABOO_ACT_FAIL", None)
        os.environ["FAKE_PEEKABOO_NO_AX_ACTION"] = "1"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_send", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertTrue(payload["cause"].startswith(
            "ELEMENT_NOT_ACTIONABLE"), payload["cause"])

    def test_snapshot_stale_effect_refused_is_clean_not_applied(self):
        # Live red (rehearsal round 3): click with a stale snapshot returns
        # rc=1 SNAPSHOT_STALE and effect "refused" — peekaboo's explicit
        # pre-dispatch refusal marker (capture
        # click_snapshot_stale_refused.json). A clean NOT_APPLIED, never
        # EFFECT_UNKNOWN.
        os.environ.pop("FAKE_PEEKABOO_ACT_FAIL", None)
        os.environ["FAKE_PEEKABOO_SNAPSHOT_STALE"] = "1"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_click", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertTrue(payload["cause"].startswith("SNAPSHOT_STALE"),
                        payload["cause"])

    def test_structured_refusal_proven_no_mutation_is_not_applied(self):
        # Live red (rehearsal 16:22): peekaboo refused the elementless
        # AXRaise with a structured payload proving mutation_dispatched
        # false — but the receipt said EFFECT_UNKNOWN, forcing an uncertain
        # effect reconciliation on a refusal that dispatched nothing. A
        # proven pre-dispatch refusal must report NOT_APPLIED.
        os.environ.pop("FAKE_PEEKABOO_ACT_FAIL", None)
        os.environ["FAKE_PEEKABOO_REFUSAL_NO_MUTATION"] = "1"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "btn1",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("CLI_ERROR", payload["cause"])

    def test_every_act_op_cli_failure_is_effect_unknown(self):
        for action, extra in self.ACT_CASES.items():
            with self.subTest(action=action):
                ctx = build_ctx(self.tmp)
                acquire_lease(ctx)
                args = {"action": action, "owner": "agent-a",
                        "lease_nonce": ctx.lease_nonce}
                args.update(extra)
                result = mmos.handle_tool_call(ctx, args)
                payload = json.loads(result["content"][0]["text"])
                self.assertEqual(payload["status"], "EFFECT_UNKNOWN",
                                 "%s: %r" % (action, payload))
                self.assertIn("CLI_ERROR", payload["cause"])
                # Exactly one act dispatch: never retried.
                act_calls = [c for c in read_calls(ctx)
                             if c[0] in ("action", "set-value", "press",
                                         "scroll", "click", "paste")
                             or c[:2] == ["window", "focus"]]
                self.assertEqual(len(act_calls), 1, action)

    def test_slice_paste_cli_failure_is_effect_unknown(self):
        os.environ.pop("FAKE_PEEKABOO_ACT_FAIL", None)
        os.environ["FAKE_PEEKABOO_PASTE_FAIL"] = "1"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "text": "hello",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "EFFECT_UNKNOWN")
        self.assertEqual(payload["clipboard_state"], "unknown")

    def test_pre_dispatch_refusal_stays_not_applied(self):
        os.environ.pop("FAKE_PEEKABOO_ACT_FAIL", None)
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "press", "window_id": 42, "element_ref": "nope",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("ELEMENT_NOT_FOUND", payload["cause"])


class TestLowHardening(unittest.TestCase):
    """Panel LOWs: renewal keeps the acquired TTL, pacing runs after the
    lease, gates use a monotonic clock, `restored` comes from the documented
    key only, and CLI_ERROR detail comes from stderr."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-low-")
        self.state = os.path.join(self.tmp, "state")
        os.makedirs(self.state)

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_PASTE_DECOY",
                    "FAKE_PEEKABOO_CLI_STDOUT_ERROR"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_renewal_preserves_acquired_ttl(self):
        lease = mmos.Lease(state_dir=self.state)
        result = lease.acquire("agent-a", ttl_seconds=30)
        lease.require_and_renew("agent-a", nonce=result["nonce"])
        held = lease.status()
        self.assertLessEqual(held["expires_in_seconds"], 31)
        self.assertGreater(held["expires_in_seconds"], 20)

    def test_pacing_check_runs_after_lease_check(self):
        ctx = build_ctx(self.tmp)
        key = mmos.pacing_key(42, 101)
        ctx.pacer.record(key, 42)
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "return",
            "owner": "agent-a"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("LEASE_NOT_HELD", payload["cause"])
        self.assertNotIn("PACING_WAIT", payload["cause"])

    def test_pacer_interval_uses_monotonic_clock(self):
        pacer = mmos.Pacer(state_dir=self.state, seconds=180)
        key = mmos.pacing_key(42, 101)
        pacer.record(key, 42)
        real_time = mmos.time.time
        mmos.time.time = lambda: real_time() + 10000  # wall clock jumps ahead
        try:
            with self.assertRaises(mmos.OpError) as caught:
                pacer.check(key)
        finally:
            mmos.time.time = real_time
        self.assertEqual(caught.exception.code, "PACING_WAIT")

    def test_lease_expiry_ignores_wall_clock_jump(self):
        lease = mmos.Lease(state_dir=self.state)
        result = lease.acquire("agent-a", ttl_seconds=60)
        real_time = mmos.time.time
        mmos.time.time = lambda: real_time() + 10000  # wall clock jumps fwd
        try:
            renewed = lease.require_and_renew("agent-a",
                                              nonce=result["nonce"])
        finally:
            mmos.time.time = real_time
        self.assertTrue(renewed)

    def test_restored_ignores_nested_decoy_key(self):
        os.environ["FAKE_PEEKABOO_PASTE_DECOY"] = "1"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "slice_paste", "window_id": 42, "text": "hello",
            "element_ref": "field1", "owner": "agent-a",
            "lease_nonce": ctx.lease_nonce})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertFalse(payload["restored"])
        self.assertFalse(payload["restore_reported"])

    def test_cli_error_detail_prefers_stderr(self):
        os.environ["FAKE_PEEKABOO_CLI_STDOUT_ERROR"] = "STDOUT-ONLY-LEAK"
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        result = mmos.handle_tool_call(ctx, {
            "action": "keys", "window_id": 42, "chord": "return",
            "owner": "agent-a", "lease_nonce": ctx.lease_nonce})
        text = result["content"][0]["text"]
        self.assertIn("stderr-detail-marker", text)
        self.assertNotIn("STDOUT-ONLY-LEAK", text)


FIXTURE_DIR = os.path.join(CHECKOUT, "tests", "fixtures", "peekaboo")


class TestPeekabooFixtureReplay(unittest.TestCase):
    """M7-PREP: the fake peekaboo replays the real captures in
    tests/fixtures/peekaboo when FAKE_PEEKABOO_FIXTURES points at that
    directory. Missing/empty fixture dirs keep the old inline fakes, and
    nothing here invents a capture that was not recorded."""

    CAPTURES = ("app_list_sanitized.json", "window_list_fixture.json",
                "see_fixture_window.json")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-fixture-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_FIXTURES"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_captures_are_present(self):
        for name in self.CAPTURES:
            self.assertTrue(
                os.path.isfile(os.path.join(FIXTURE_DIR, name)), name)

    def test_apps_replay_real_capture(self):
        ctx = build_ctx(self.tmp)
        os.environ["FAKE_PEEKABOO_FIXTURES"] = FIXTURE_DIR
        payload = json.loads(mmos.handle_tool_call(
            ctx, {"action": "apps"})["content"][0]["text"])
        self.assertEqual(payload["status"], "OK")
        self.assertEqual([app["name"] for app in payload["apps"]],
                         ["Finder", "Preview", "Python"])

    def test_window_list_replays_real_capture(self):
        ctx = build_ctx(self.tmp)
        os.environ["FAKE_PEEKABOO_FIXTURES"] = FIXTURE_DIR
        windows = ctx.adapter.list_windows("Python")
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["window_id"], 98889)
        self.assertEqual(windows[0]["title"], "BCU slice fixture")

    def test_snapshot_replays_real_capture(self):
        ctx = build_ctx(self.tmp)
        os.environ["FAKE_PEEKABOO_FIXTURES"] = FIXTURE_DIR
        snap = ctx.adapter.snapshot_window(98889)
        identity = mmos.window_identity(snap)
        self.assertEqual(identity["app_name"], "Python")
        self.assertEqual(identity["window_title"], "BCU slice fixture")
        self.assertEqual(mmos.snapshot_id_of(snap), "1794404855625-2444")

    def test_empty_fixture_dir_keeps_inline_fakes(self):
        ctx = build_ctx(self.tmp)
        empty = os.path.join(self.tmp, "no-fixtures")
        os.makedirs(empty)
        os.environ["FAKE_PEEKABOO_FIXTURES"] = empty
        windows = ctx.adapter.list_windows("TextEdit")
        self.assertEqual(windows[0]["window_id"], 42)


class TestDenyBeforePixels(unittest.TestCase):
    """Round 2, D-H2: for EVERY path that can produce an image (act
    observe, slice observe, post-paste confirm, capture), the deny check
    runs FIRST on a read that takes no screenshot (``see --tree
    --no-screenshot``). A refused window leaves no captured pixels
    anywhere — including peekaboo's own ~/.peekaboo/snapshots folder, where
    every pixel-taking ``see`` persists an image."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-pixels-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_IDENTITY_2", "FAKE_PEEKABOO_SEE_COUNT"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot_dir_listing(self):
        """File list of the real ~/.peekaboo/snapshots folder (or a marker
        when absent) — a denied act must leave it byte-for-byte the same."""
        path = os.path.expanduser("~/.peekaboo/snapshots")
        if not os.path.isdir(path):
            return ("<absent>",)
        return ("<present>", tuple(sorted(os.listdir(path))))

    def _ctx_denied(self):
        ctx = build_ctx(self.tmp, identity=IDENTITY_ONepw)
        acquire_lease(ctx)
        return ctx

    def _act(self, ctx, action, extra):
        args = {"action": action, "window_id": 42,
                "owner": "agent-a", "lease_nonce": ctx.lease_nonce}
        args.update(extra)
        return mmos.handle_tool_call(ctx, args)

    def _assert_no_pixel_read(self, ctx):
        sees = [c for c in read_calls(ctx) if c[0] == "see"]
        self.assertTrue(sees, "expected the screenshot-less deny read")
        for argv in sees:
            self.assertIn(
                "--no-screenshot", argv,
                "pixel-taking see on a denied window: %r" % (argv,))
        # And the peekaboo snapshot folder is untouched by the refusal.
        self.assertEqual(self._snapshot_dir_listing(), self._before)

    def test_press_on_denied_window_takes_no_pixels(self):
        self._before = self._snapshot_dir_listing()
        ctx = self._ctx_denied()
        payload = json.loads(self._act(ctx, "press",
                                       {"element_ref": "btn1"})
                             ["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("DENY_LISTED", payload["cause"])
        self._assert_no_pixel_read(ctx)

    def test_keys_on_denied_window_takes_no_pixels(self):
        self._before = self._snapshot_dir_listing()
        ctx = self._ctx_denied()
        payload = json.loads(self._act(ctx, "keys", {"chord": "return"})
                             ["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("DENY_LISTED", payload["cause"])
        self._assert_no_pixel_read(ctx)

    def test_slice_click_on_denied_window_takes_no_pixels(self):
        self._before = self._snapshot_dir_listing()
        ctx = self._ctx_denied()
        payload = json.loads(self._act(ctx, "slice_click",
                                       {"element_ref": "btn1"})
                             ["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("DENY_LISTED", payload["cause"])
        self._assert_no_pixel_read(ctx)

    def test_slice_paste_on_denied_window_takes_no_pixels(self):
        self._before = self._snapshot_dir_listing()
        ctx = self._ctx_denied()
        payload = json.loads(self._act(ctx, "slice_paste",
                                       {"text": "hello"})
                             ["content"][0]["text"])
        self.assertEqual(payload["status"], "NOT_APPLIED")
        self.assertIn("DENY_LISTED", payload["cause"])
        # No paste dispatch may run for a denied window.
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "paste"], [])
        self._assert_no_pixel_read(ctx)

    def test_paste_confirm_read_denies_before_pixels(self):
        # Allowed window at observe time, deny-listed by the confirm read
        # (title/app changed to 1Password): the confirm must refuse on a
        # screenshot-less read; exactly ONE pixel see (the observe) exists.
        self._before = self._snapshot_dir_listing()
        ctx = build_ctx(self.tmp)  # TextEdit identity: allowed at observe
        acquire_lease(ctx)
        os.environ["FAKE_PEEKABOO_IDENTITY_2"] = IDENTITY_ONepw
        os.environ["FAKE_PEEKABOO_SEE_COUNT"] = os.path.join(
            self.tmp, "see-count")
        payload = json.loads(self._act(ctx, "slice_paste",
                                       {"element_ref": "field1",
                                        "text": "hello"})["content"][0]["text"])
        self.assertEqual(payload["status"], "APPLIED")
        self.assertIn("confirm read failed: DENY_LISTED", payload["observed"])
        plain = [c for c in read_calls(ctx) if c[0] == "see"
                 and "--tree" not in c]
        self.assertEqual(len(plain), 1,
                         "confirm must deny on a --no-screenshot read "
                         "before any second pixel capture: %r" % (plain,))
        tree = [c for c in read_calls(ctx) if c[0] == "see"
                and "--tree" in c]
        self.assertTrue(any("--no-screenshot" in c for c in tree))
        self.assertEqual(self._snapshot_dir_listing(), self._before)


class TestSessionCannotLoosenFloors(unittest.TestCase):
    """BCU R2 item 2 (R-M4 / ESC 12) + BCU R3 H2 (ESC 14): 180 s is a
    PRODUCTION FLOOR in code, UNCONDITIONALLY.

    runtime.json or an MMOS_CU_* env value may make a threshold STRICTER,
    never looser — no flag switches that off any more (the R2 pytest-module
    check was forgeable). The only sub-default path is an in-process
    constructor argument (unit-test injection), still bounded by the
    absolute 1 s floor.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-floors-")
        self.saved = {key: os.environ.pop(key, None)
                      for key in ("MMOS_CU_TEST_MODE",
                                  "MMOS_CU_PRESENCE_MIN_IDLE",
                                  "MMOS_CU_PACING_SECONDS")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _state(self):
        return os.path.join(self.tmp, "state")

    def test_defaults_are_the_floor(self):
        self.assertEqual(mmos.DEFAULT_MIN_IDLE_SECONDS, 180.0)
        self.assertEqual(mmos.DEFAULT_PACING_SECONDS, 180.0)
        self.assertEqual(mmos.Presence().min_idle, 180.0)
        self.assertEqual(mmos.Pacer(state_dir=self._state()).seconds, 180.0)

    def test_presence_runtime_key_cannot_lower_the_floor(self):
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(runtime={"presence_min_idle_seconds": 90})
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_presence_env_cannot_lower_the_floor(self):
        os.environ["MMOS_CU_PRESENCE_MIN_IDLE"] = "45"
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence()
        self.assertEqual(caught.exception.code,
                         "PRESENCE_MIN_IDLE_STRICTER_ONLY")

    def test_presence_constructor_is_the_injected_test_path(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): constructor injection is the
        # sanctioned sub-default path — the old code refused it without the
        # forgeable flag. The absolute 1 s floor still holds for it.
        self.assertEqual(mmos.Presence(min_idle_seconds=8.0).min_idle, 8.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Presence(min_idle_seconds=0.5)
        self.assertEqual(caught.exception.code, "PRESENCE_MIN_IDLE_FLOOR")

    def test_pacer_runtime_cannot_lower_the_floor(self):
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Pacer(state_dir=self._state(),
                       runtime={"pacing_seconds": 60})
        self.assertEqual(caught.exception.code, "PACING_SECONDS_STRICTER_ONLY")

    def test_pacer_env_cannot_lower_the_floor(self):
        os.environ["MMOS_CU_PACING_SECONDS"] = "1"
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Pacer(state_dir=self._state())
        self.assertEqual(caught.exception.code, "PACING_SECONDS_STRICTER_ONLY")

    def test_pacer_constructor_is_the_injected_test_path(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): see the Presence twin above.
        self.assertEqual(
            mmos.Pacer(state_dir=self._state(), seconds=10).seconds, 10.0)
        with self.assertRaises(mmos.RefuseError) as caught:
            mmos.Pacer(state_dir=self._state(), seconds=0.5)
        self.assertEqual(caught.exception.code, "PACING_SECONDS_FLOOR")

    def test_stricter_values_are_still_accepted(self):
        self.assertEqual(mmos.Presence(min_idle_seconds=300).min_idle, 300.0)
        self.assertEqual(
            mmos.Pacer(state_dir=self._state(), seconds=600).seconds, 600.0)

    def test_env_marker_alone_does_not_unlock_the_layer(self):
        # A real server child: no pytest in its process, so MMOS_CU_TEST_MODE=1
        # (which any session could set) must NOT be test mode. The child's
        # scratch paths are outside the layer, so startup has to refuse.
        bin_path = make_fake_peekaboo(self.tmp)
        runtime = write_runtime(self.tmp, bin_path)
        env = dict(os.environ)
        env.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        env.pop("MMOS_CU_PACING_SECONDS", None)
        env.update({
            "MMOS_CU_TEST_MODE": "1",
            "MMOS_CU_RUNTIME": runtime,
            "MMOS_CU_STATE_DIR": os.path.join(self.tmp, "state"),
            "MMOS_CU_DENY": os.path.join(self.tmp, "deny.json"),
        })
        proc = subprocess.run(
            [sys.executable, os.path.join(TOOL_DIR, "server.py")],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("startup refused", proc.stderr)
        self.assertIn("ENV_PATH_OUTSIDE_LAYER", proc.stderr)
        self.assertNotIn("ready", proc.stderr)

    def test_forged_harness_bootstrap_does_not_unlock_the_layer(self):
        # BCU R3 H2 (fail-first on 1ae3e29e6): the FULL R2 forgery — a child
        # that imports pytest before executing server.py (as a session could
        # arrange via PYTHONPATH/sitecustomize) plus MMOS_CU_TEST_MODE=1 and
        # out-of-layer env paths. The old harness check treated exactly this
        # child as the test harness and started READY; the floors and the
        # in-layer path rule must now hold in code, with no flag at all.
        bin_path = make_fake_peekaboo(self.tmp)
        runtime = write_runtime(self.tmp, bin_path)
        env = dict(os.environ)
        env.pop("MMOS_CU_PRESENCE_MIN_IDLE", None)
        env.pop("MMOS_CU_PACING_SECONDS", None)
        env.update({
            "MMOS_CU_TEST_MODE": "1",
            "MMOS_CU_RUNTIME": runtime,
            "MMOS_CU_STATE_DIR": os.path.join(self.tmp, "state"),
            "MMOS_CU_DENY": os.path.join(self.tmp, "deny.json"),
        })
        server_py = os.path.join(TOOL_DIR, "server.py")
        bootstrap = (
            "import pytest, sys\n"
            "path = sys.argv[1]\n"
            "sys.argv = [path]\n"
            "__file__ = path\n"
            "exec(compile(open(path).read(), path, 'exec'))\n")
        proc = subprocess.run(
            [sys.executable, "-c", bootstrap, server_py],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, text=True, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("startup refused", proc.stderr)
        self.assertIn("ENV_PATH_OUTSIDE_LAYER", proc.stderr)
        self.assertNotIn("ready", proc.stderr)


class TestForegroundPasteGate(unittest.TestCase):
    """BCU R2 item 5 (R-H1): the opt-in foreground paste re-checks DENY and
    then FRONTMOST on fresh reads immediately before the chord.

    ``paste --foreground`` delivers Cmd+V to whichever window holds focus, so
    a deny-listed window (the target itself, or a floating password-manager
    panel above it) could receive text meant for the target. If either check
    fails the paste subprocess never starts: nothing is pasted and the
    pasteboard is unchanged.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mmos-cu-fgpaste-")

    def tearDown(self):
        for key in ("FAKE_PEEKABOO_IDENTITY", "FAKE_PEEKABOO_LOG",
                    "FAKE_PEEKABOO_WINDOWS_JSON"):
            os.environ.pop(key, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ctx(self):
        ctx = build_ctx(self.tmp)
        acquire_lease(ctx)
        return ctx

    def _paste(self, ctx, **extra):
        args = {"action": "slice_paste", "window_id": 42,
                "text": "hello world", "owner": "agent-a",
                "lease_nonce": ctx.lease_nonce, "allow_foreground": True}
        args.update(extra)
        return json.loads(mmos.handle_tool_call(ctx, args)["content"][0]
                          ["text"])

    def test_deny_after_the_observe_refuses_before_the_chord(self):
        ctx = self._ctx()
        real = ctx.adapter.inspect_window
        calls = []

        def became_denied(window_id):
            # The slice's opening observe (call 1) succeeds; the window only
            # turns deny-listed by the gate's FRESH read (call 2) immediately
            # before the chord — exactly the race the gate exists for.
            calls.append(window_id)
            data = real(window_id)
            if len(calls) == 1:
                return data
            out = dict(data) if isinstance(data, dict) else {}
            out["app"] = "1Password"
            out["bundle_id"] = "com.1password.1password"
            return out

        ctx.adapter.inspect_window = became_denied
        payload = self._paste(ctx)
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("DENY_LISTED", payload["cause"])
        self.assertIs(payload["pasted"], False)
        self.assertEqual(payload["clipboard_state"], "unchanged")
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "paste"], [])
        self.assertGreaterEqual(len(calls), 2, "the gate never re-read")

    def test_frontmost_lost_refuses_before_the_chord(self):
        ctx = self._ctx()

        def covered(window_id, app):
            return [{"window_id": 42, "title": "Untitled", "owner_pid": 101,
                     "is_frontmost": False, "window_index": 1,
                     "is_key": True}]

        ctx.adapter.windows_of_window = covered
        payload = self._paste(ctx)
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("WINDOW_NOT_FRONTMOST", payload["cause"])
        self.assertIs(payload["pasted"], False)
        self.assertEqual(payload["clipboard_state"], "unchanged")
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "paste"], [])

    def test_unreadable_gate_evidence_is_a_typed_refusal(self):
        ctx = self._ctx()
        real = ctx.adapter.inspect_window
        calls = []

        def unreadable(window_id):
            # The observe read works; only the gate's fresh read (call 2+)
            # comes back unreadable — the paste must then refuse pre-dispatch
            # with the typed PASTE_GATE_UNVERIFIED, never dispatch blind.
            calls.append(window_id)
            if len(calls) == 1:
                return real(window_id)
            raise mmos.OpError("DISPATCH_UNAVAILABLE", "see failed")

        ctx.adapter.inspect_window = unreadable
        payload = self._paste(ctx)
        self.assertEqual(payload["status"], "NOT_APPLIED", payload)
        self.assertIn("PASTE_GATE_UNVERIFIED", payload["cause"])
        self.assertIs(payload["pasted"], False)
        self.assertEqual(payload["clipboard_state"], "unchanged")
        self.assertEqual([c for c in read_calls(ctx) if c[0] == "paste"], [])
        self.assertGreaterEqual(len(calls), 2, "the gate never re-read")

    def test_background_paste_is_not_gated_on_frontmost(self):
        # The gate is scoped to the foreground chord: the background paste is
        # targeted by pid + exact window id and needs no frontmost window.
        ctx = self._ctx()

        def covered(window_id, app):
            return [{"window_id": 42, "title": "Untitled", "owner_pid": 101,
                     "is_frontmost": False, "window_index": 1,
                     "is_key": True}]

        ctx.adapter.windows_of_window = covered
        payload = self._paste(ctx, allow_foreground=False)
        self.assertEqual(payload["status"], "APPLIED", payload)
        self.assertNotIn("clipboard_state", payload)
        self.assertNotIn("pasted", payload)
        pastes = [c for c in read_calls(ctx) if c[0] == "paste"]
        self.assertEqual(len(pastes), 1)
        self.assertNotIn("--foreground", pastes[0])


if __name__ == "__main__":
    unittest.main()
