#!/usr/bin/env python3
"""mmos_computer_use — zero-dependency stdio MCP server for supervised macOS
window-level computer use, wrapping the Peekaboo CLI.

Protocol: MCP over stdio, newline-delimited JSON-RPC 2.0 (initialize, ping,
tools/list, tools/call), mirroring the framing used by the installed Mastermind
stdio MCP adapters. Exactly ONE tool, ``mmos_computer_use``, is exposed; its
single ``action`` argument selects the operation.

Operations
    SEE      apps | windows(app) | inspect(window_id) | capture(window_id, ocr)
    ACT      press(window_id, element_ref) | set_text(window_id, element_ref, text)
             keys(window_id, chord) | scroll(window_id, direction, amount,
             element_ref?) | pointer_click(window_id, element_ref? | x, y)
    SLICE    slice_front(app, window_id | title) — raise ONE named window
             slice_click(window_id, element_ref | x, y) — one click
             slice_paste(window_id, text, element_ref?) — paste, never typing
             slice_send(window_id, element_ref) — challenge-checked send click
             slice_look(window_id, question?) — AX text + capture + vision
    VISION   vision_ask(window_id, question, element_hints)
    LEASE    lease_acquire | lease_release | lease_status
    PRESENCE presence

Safety invariants (enforced in code, unit-tested in
tests/test_mmos_bcu_computer_use.py):
  * Every SEE/ACT/VISION op names exactly one window_id. No screen-wide,
    display-wide or all-windows parameter exists anywhere in the tool schema.
  * A deny list (deny.json) is checked on EVERY op that targets a window or
    app; a match refuses the op (cause DENY_LISTED) and no window content is
    read. Credential managers, password managers, System Settings, terminal
    emulators and Script Editor are denied by default. The windows op
    additionally denies every RESOLVED app identity in the CLI result and
    drops entries whose resolved app is not exactly the requested app.
  * Every ACT returns a receipt {target, status, cause?, observed}. ACT without
    the lease is NOT_APPLIED / LEASE_NOT_HELD; ACT while a human is actively
    using the machine is NOT_APPLIED / HUMAN_ACTIVE.
  * ACT requires: deny-list pass, held lease (renewed per act), and human idle
    >= threshold (ioreg HIDIdleTime).
  * Every ACT first takes its OWN fresh ``see`` snapshot of the target window,
    resolves the caller's element_ref against that snapshot's ui_elements, and
    then dispatches ONCE with ``--snapshot <id> --on <elem>``. The act command
    carries no --app/--pid/--window-id (peekaboo refuses that combination) and
    never carries --foreground unless the caller explicitly set
    allow_foreground=true AND the lease and presence gates both passed.
    Background delivery preserves the user's frontmost app; focus stealing is
    prohibited by default.
  * A foreground-required refusal from peekaboo is returned as NOT_APPLIED /
    FOREGROUND_REQUIRED. It is NEVER escalated automatically and NEVER retried.
  * SLICE ops (slice_front/click/paste/send/look) drive ONE named window
    end-to-end (observe -> act -> confirm). They are foreground-class by
    design (AXRaise/AXPress-class/paste need the window exposed), which is
    lawful ONLY under the passed deny + lease + presence gates: the single
    dispatch carries --foreground directly, is never attempted in the
    background first, and is never retried.
  * Slice presence: the human-idle threshold default is 180 s for ALL acts
    (MMOS_CU_PRESENCE_MIN_IDLE env / runtime.json presence_min_idle_seconds).
    Presence is re-checked before EVERY step and between steps of a slice
    sequence; a human becoming active mid-sequence aborts with NOT_APPLIED /
    HUMAN_ACTIVE_MID_SEQUENCE naming exactly which steps completed. Partial
    state is reported truthfully; nothing continues, nothing retries.
  * Slice pacing: per target window (keyed by window id), a minimum interval
    (default 180 s; MMOS_CU_PACING_SECONDS env / runtime.json pacing_seconds)
    between two slice_paste or slice_send sequences, persisted as
    pacing.json under the state dir. Too soon -> NOT_APPLIED / PACING_WAIT
    with the seconds remaining. The single-holder lease already guarantees
    one worker at a time.
  * Challenge stop: every input-delivering slice act (slice_click,
    slice_paste, slice_send) scans the window's AX text (and OCR text if
    present) for challenge patterns (captcha, sign in, rate limit, unusual
    activity, ...) BEFORE dispatching; a match is a terminal NOT_APPLIED /
    CHALLENGE_DETECTED with a bounded quote of what was seen. No retry after
    a challenge refusal. slice_front raises without input and keeps no scan.
  * Honest automation: this layer performs ordinary, visible automation. It
    never imitates or disguises itself as a human: no randomized or
    human-like motion/timing is synthesized and no fingerprint/user-agent/
    viewport changes are ever added to any dispatch
    (HONEST_AUTOMATION / FORBIDDEN_DISGUISE_FLAGS, asserted by test). Text
    entry in a slice is delivered with `peekaboo paste --text` (clipboard set,
    paste chord, previous clipboard restored) — never character keystrokes.
  * The layer never retries an act. Each peekaboo dispatch is a single
    subprocess.run call with no loop around it; an unreadable or timed-out
    dispatch is reported EFFECT_UNKNOWN, never replayed.
  * The peekaboo binary is pinned by path + SHA-256 in runtime.json
    (schema mmos.computer_use.runtime/v1); a mismatch refuses startup
    (PIN_MISMATCH). --no-remote is always passed; --bridge-socket is never
    passed; --input-strategy comes from runtime.json (default actionFirst for
    SEE; acts always use act_input_strategy, default and only accepted value
    actionOnly).

Peekaboo CLI surface chosen (evidence gathered 2026-11-11 from
``peekaboo <subcommand> --help``, ``peekaboo tools --json`` and live dispatch
against Peekaboo 4.2.2 at /opt/homebrew/bin/peekaboo, permissions all
Granted):
  * app list --json --no-remote        -> running GUI apps (name, bundle_id,
                                          pid, is_active, is_hidden)
  * window list --app X --json         -> windows of one app (window_id, title)
  * see --window-id N --json --tree
        --no-screenshot                -> accessibility tree of ONE window
                                          (read-only, no capture)
  * see --window-id N --json           -> fresh snapshot: data.snapshot_id,
                                          data.ui_elements[] (id/role/label/
                                          value) and data.coordinate_context
                                          with the window bounds. This is the
                                          observation every ACT dispatches on.
  * see --window-id N --json --path F  -> capture ONE window to a staging file
                                          (staging file is deleted in finally;
                                          kept only if keep_path is given and
                                          lies under MMOS_CU_SCRATCH)
  * action AXPress --snapshot S --on REF --input-strategy actionOnly --no-remote
        --json                         -> AX action, executed in BACKGROUND
  * action AXRaise --snapshot S [--on winElem] --foreground --json
                                       -> raise ONE window to the front
                                          (slice_front; AXRaise is
                                          foreground-class)
  * paste --text T --app A --window-id N [--focus-timeout MS] [--restore-delay MS]
        --no-remote --json             -> sets the clipboard, delivers the
                                          paste chord, restores the previous
                                          clipboard (slice_paste; NO typing,
                                          NO --input-strategy: the input is
                                          the paste chord, not element
                                          targeting)
  * set-value --snapshot S --on REF --value TXT --input-strategy actionOnly
        --no-remote --json             -> direct AX value set, no typing, no
                                          clipboard, background
  * press CHORD --snapshot S [--on REF] --input-strategy actionOnly --no-remote
        --json                         -> keyboard chord
  * scroll --direction D --amount K --snapshot S [--on REF] ...
                                       -> wheel scroll
  * click --snapshot S --on REF | --at x,y ...
                                       -> element-targeted click preferred;
                                          window-relative coordinate click is
                                          the last resort
Verified live 2026-11-11 (real window): the snapshot form above succeeded and
left the frontmost app unchanged, while the older ``--window-id`` form failed
with CAPTURE_FAILED (it tries its own capture). Passing --app/--pid/--window-id
together with --snapshot is rejected by the CLI. Window-chrome elements (e.g.
a close button) may still refuse background delivery; that surfaces as
FOREGROUND_REQUIRED rather than a silent focus steal. Window enumeration and
the AX tree ARE reachable via CLI flags, so the fallback of running
``peekaboo mcp serve`` and speaking MCP to it is NOT used.

Secrets: the vision call reads ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL from
the environment at call time only, uses urllib.request with headers (never
curl/argv), and never stores, logs or writes the token or image bytes. Child
peekaboo processes get an environment with ANTHROPIC_* variables stripped.

Run:      python3 tools/mmos_computer_use/server.py
Config:   tools/mmos_computer_use/runtime.json (or runtime.json.dev when
          runtime.json is absent; MMOS_CU_RUNTIME overrides the path).
Requires Python 3.9+ stdlib only.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

RUNTIME_SCHEMA = "mmos.computer_use.runtime/v1"
DENY_SCHEMA = "mmos.computer_use.deny/v1"
TOOL_NAME = "mmos_computer_use"
SERVER_NAME = "mmos-computer-use-mcp"
SERVER_VERSION = "0.2.0"
PROTOCOL_VERSION = "2025-06-18"

# Every operation the single tool exposes.
ACTIONS = [
    "apps", "windows", "inspect", "capture",
    "press", "set_text", "keys", "scroll", "pointer_click",
    "slice_front", "slice_click", "slice_paste", "slice_send", "slice_look",
    "vision_ask",
    "lease_acquire", "lease_release", "lease_status",
    "presence",
]

# Ops that require exactly one window_id (no screen-wide targeting exists).
WINDOW_OPS = {"inspect", "capture", "press", "set_text", "keys", "scroll",
              "pointer_click", "vision_ask", "slice_click", "slice_paste",
              "slice_send", "slice_look"}
ACT_OPS = {"press", "set_text", "keys", "scroll", "pointer_click"}
# Slice ops that pace per target window (one sequence per interval).
PACED_SLICE_OPS = {"slice_paste", "slice_send"}
# slice_paste failures that are PROVABLY pre-dispatch (nothing was sent,
# clipboard untouched) and may be reported NOT_APPLIED. Any other
# dispatch-phase failure maps to EFFECT_UNKNOWN (paste truthfulness).
PASTE_CLEAN_PRE_DISPATCH_CODES = {
    "WINDOW_IDENTITY_UNKNOWN", "DENY_LISTED", "LEASE_NOT_HELD",
    "LEASE_OWNER_REQUIRED", "PRESENCE_UNKNOWN", "HUMAN_ACTIVE",
    "HUMAN_ACTIVE_MID_SEQUENCE", "PACING_WAIT", "CHALLENGE_DETECTED",
    "ELEMENT_NOT_FOUND", "ELEMENT_REF_INVALID", "TEXT_REQUIRED",
    "WINDOW_ID_REQUIRED", "SNAPSHOT_UNAVAILABLE",
}

MAX_TREELINES = 400
MAX_LINE_CHARS = 240
MAX_OBSERVED = 200
MAX_ERROR_TEXT = 240

DEFAULT_MIN_IDLE_SECONDS = 180.0
DEFAULT_PACING_SECONDS = 180.0
# Runtime gate floors (security-fix pass): a presence or pacing threshold
# below these values would effectively disable the safety gate; both sources
# (runtime.json and the MMOS_CU_* env overrides) refuse at startup.
MIN_IDLE_FLOOR_SECONDS = 1.0
PACING_FLOOR_SECONDS = 1.0
DEFAULT_LEASE_TTL = 120
SEE_TIMEOUT_S = 30.0
ACT_TIMEOUT_S = 15.0
PASTE_TIMEOUT_S = 60.0
VISION_TIMEOUT_S = 90.0
DEFAULT_VISION_MODEL = "minimax-m3.1-flash"

# Honest automation: this layer performs ordinary, visible automation only.
# It never imitates or disguises itself as a human — no randomized or
# human-like motion/timing is synthesized and no fingerprint, user-agent or
# viewport change is ever added to any dispatch (asserted by test against
# every argv the builder emits). If a challenge, CAPTCHA, sign-in,
# rate-limit or "unusual activity" notice is seen, the layer STOPS, reports
# what it saw, and does not retry. Pacing and presence gates are safety
# properties, never obstacles to route around.
HONEST_AUTOMATION = True
FORBIDDEN_DISGUISE_FLAGS = (
    "--humanize", "--human-like", "--jitter", "--random-delay",
    "--user-agent", "--fingerprint", "--viewport", "--stealth",
    "--randomize",
)

# Challenge patterns for the slice_send pre-dispatch stop. Matched
# case-insensitively anywhere in the window's AX text (and OCR text if
# present); extendable via runtime.json challenge_patterns_extra.
DEFAULT_CHALLENGE_PATTERNS = (
    "captcha", "are you a robot", "verify you are human", "sign in",
    "log in", "rate limit", "too many requests", "unusual activity",
    "access denied",
)
CHALLENGE_QUOTE_CHARS = 160

# Keyboard chords that are system-global rather than targeted at a window.
GLOBAL_CHORDS = {
    "cmd+space", "cmd+tab", "cmd+grave", "ctrl+cmd+q", "cmd+ctrl+q",
    "shift+cmd+q", "cmd+option+escape", "ctrl+cmd+power",
}

# Keyboard chords the keys op may deliver at all: plain navigation/editing
# keys, plus shift modified on the four arrow keys only (checked AFTER the
# GLOBAL_CHORDS refusal, defense in depth). Everything else — chords with
# cmd/ctrl/option modifiers (save, quit, screenshot, app switcher, force
# quit, ...) — is refused with CHORD_NOT_ALLOWED; there is no escape hatch.
CHORD_ALLOWLIST = {
    "enter", "return", "escape", "tab", "space", "delete", "forwarddelete",
    "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
}
SHIFT_ARROW_CHORDS = {"shift+left", "shift+right", "shift+up", "shift+down"}

TOOL_DESCRIPTION = (
    "Supervised, window-scoped macOS computer use. SEE operations read one "
    "named window (app list, window list, accessibility tree, capture with "
    "optional OCR); ACT operations (press AX action, set_text via direct AX "
    "value, single keyboard chord, scroll, last-resort window-relative "
    "pointer click) require the caller to hold the lease first "
    "(lease_acquire) and a human-idle screen, and return a receipt instead of "
    "retrying. SLICE operations drive one named window end-to-end "
    "(slice_front raise, slice_click, slice_paste whole-text paste, "
    "slice_send, slice_look) with a 180 s human-idle default, mid-sequence "
    "presence aborts, per-window pacing between paste/send sequences, and a "
    "challenge stop on every input-delivering slice act. The keys op accepts "
    "an allowlist of navigation/editing chords only. vision_ask captures one "
    "window in memory and asks a vision model (https or loopback endpoint "
    "only) for an answer plus clickable elements with normalized 0-1000 "
    "coordinates. Every operation names exactly one window_id or app; "
    "credential/password managers, System Settings, terminal emulators and "
    "Script Editor are deny-listed and refuse all operations. The layer "
    "performs ordinary visible automation only: no human imitation, no "
    "fingerprint or user-agent changes; on a challenge it stops and reports."
)

TOOL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action"],
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "app": {"type": "string", "description": "Application name (windows op)"},
        "window_id": {"type": "integer",
                      "description": "CoreGraphics window id, from apps/windows"},
        "title": {"type": "string",
                  "description": "slice_front: window title substring selector "
                                 "(used with app when window_id is unknown)"},
        "element_ref": {"type": "string",
                        "description": "Accessibility element id from inspect"},
        "text": {"type": "string", "description": "Text for set_text"},
        "chord": {"type": "string",
                  "description": "Single keyboard chord, e.g. Return or cmd+s"},
        "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
        "amount": {"type": "integer", "minimum": 1, "maximum": 50},
        "x": {"type": "integer"}, "y": {"type": "integer"},
        "ocr": {"type": "boolean", "description": "capture: include OCR text"},
        "keep_path": {"type": "string",
                      "description": "capture: save PNG here; must be under "
                                     "the MMOS_CU_SCRATCH directory"},
        "question": {"type": "string", "description": "vision_ask question"},
        "element_hints": {"type": "array", "items": {"type": "string"}},
        "owner": {"type": "string", "description": "Lease owner id"},
        "ttl_seconds": {"type": "integer", "minimum": 5, "maximum": 3600},
        "allow_foreground": {
            "type": "boolean", "default": False,
            "description": "ACT: opt in to a single fresh foreground dispatch "
                           "if background delivery is refused. Default false; "
                           "foreground steals focus and is never automatic."},
    },
}


class RefuseError(Exception):
    """Startup refusal (config, pin or deny list problem)."""

    def __init__(self, code, detail=""):
        super().__init__(("%s: %s" % (code, detail)) if detail else code)
        self.code = code
        self.detail = detail[:MAX_ERROR_TEXT]


class OpError(Exception):
    """Bounded, typed operation failure surfaced as a cause code."""

    def __init__(self, code, detail=""):
        super().__init__(("%s: %s" % (code, detail)) if detail else code)
        self.code = code
        self.detail = detail[:MAX_ERROR_TEXT]


# ── runtime pin ──────────────────────────────────────────────────────────────

def sha256_file(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_runtime(path):
    """Load and VERIFY the pinned peekaboo runtime descriptor.

    Raises RefuseError("PIN_MISMATCH") when the binary's actual SHA-256 does
    not match the pinned digest, so a swapped binary never executes.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError:
        raise RefuseError("RUNTIME_UNREADABLE", path)
    except ValueError:
        raise RefuseError("RUNTIME_INVALID_JSON", path)
    if not isinstance(data, dict) or data.get("schema") != RUNTIME_SCHEMA:
        raise RefuseError("RUNTIME_SCHEMA", str(data.get("schema")))
    binary = data.get("peekaboo_bin")
    pinned = data.get("peekaboo_sha256")
    strategy = data.get("input_strategy", "actionFirst")
    act_strategy = data.get("act_input_strategy", "actionOnly")
    if not isinstance(binary, str) or not os.path.isabs(binary):
        raise RefuseError("RUNTIME_BIN_PATH", repr(binary))
    if not isinstance(pinned, str) or not re.fullmatch(r"[0-9a-f]{64}", pinned):
        raise RefuseError("RUNTIME_DIGEST", repr(pinned))
    if strategy not in ("actionFirst", "synthFirst", "actionOnly", "synthOnly"):
        raise RefuseError("RUNTIME_STRATEGY", repr(strategy))
    # Acts are background-only: AX actions, never synthesized keystrokes.
    if act_strategy != "actionOnly":
        raise RefuseError("RUNTIME_ACT_STRATEGY", repr(act_strategy))

    def _number(key, minimum):
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or value < minimum:
            raise RefuseError("RUNTIME_%s" % key.upper(), repr(value))
        return value

    presence_min_idle = _number("presence_min_idle_seconds",
                                MIN_IDLE_FLOOR_SECONDS)
    pacing = _number("pacing_seconds", PACING_FLOOR_SECONDS)
    paste_focus_ms = _number("paste_focus_timeout_ms", 0)
    paste_restore_ms = _number("paste_restore_delay_ms", 0)
    challenge_extra = data.get("challenge_patterns_extra")
    if challenge_extra is not None:
        if not isinstance(challenge_extra, list) or not all(
                isinstance(item, str) and item for item in challenge_extra):
            raise RefuseError("RUNTIME_CHALLENGE_PATTERNS_EXTRA",
                              repr(challenge_extra))
        challenge_extra = list(challenge_extra)
    if not os.path.isfile(binary):
        raise RefuseError("RUNTIME_BIN_MISSING", binary)
    try:
        actual = sha256_file(binary)
    except OSError as error:
        raise RefuseError("RUNTIME_BIN_UNREADABLE", str(error))
    if actual != pinned:
        raise RefuseError("PIN_MISMATCH",
                          "pinned %s actual %s" % (pinned[:12], actual[:12]))
    return {"peekaboo_bin": binary, "peekaboo_sha256": pinned,
            "input_strategy": strategy, "act_input_strategy": act_strategy,
            "presence_min_idle_seconds": presence_min_idle,
            "pacing_seconds": pacing,
            "paste_focus_timeout_ms": paste_focus_ms,
            "paste_restore_delay_ms": paste_restore_ms,
            "challenge_patterns_extra": challenge_extra or []}


def resolve_runtime_path():
    override = os.environ.get("MMOS_CU_RUNTIME")
    if override:
        return override
    primary = os.path.join(HERE, "runtime.json")
    if os.path.isfile(primary):
        return primary
    return os.path.join(HERE, "runtime.json.dev")


# ── deny list ────────────────────────────────────────────────────────────────

DEFAULT_DENY = {
    "schema": DENY_SCHEMA,
    "app_names": [
        "Keychain Access", "1Password", "Bitwarden", "Dashlane",
        "Proton Pass", "Keeper", "Enpass", "Strongbox", "System Settings",
        "Passwords",
        # Terminal emulators and the script editor: a shell or script window
        # is an arbitrary-command surface, not a document window.
        "Terminal", "iTerm", "iTerm2", "Script Editor",
    ],
    "bundle_ids": [
        "com.apple.KeychainAccess", "com.apple.Passwords",
        "com.apple.systempreferences", "com.1password.1password",
        "com.bitwarden.desktop",
        "com.apple.Terminal", "com.apple.ScriptEditor.id",
    ],
    "title_regexes": [],
    "extra_app_names": [],
    "extra_bundle_ids": [],
    "extra_title_regexes": [],
}


class DenyList:
    def __init__(self, app_names, bundle_ids, title_regexes):
        self.app_names = app_names
        self.bundle_ids = bundle_ids
        self.title_regexes = title_regexes

    @classmethod
    def load(cls, path):
        entries = {k: list(v) for k, v in DEFAULT_DENY.items()
                   if isinstance(DEFAULT_DENY[k], list)}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                raise RefuseError("DENY_LIST_UNREADABLE", path)
            if not isinstance(data, dict) or data.get("schema") != DENY_SCHEMA:
                raise RefuseError("DENY_LIST_SCHEMA", path)
            for key in ("app_names", "bundle_ids", "title_regexes",
                        "extra_app_names", "extra_bundle_ids",
                        "extra_title_regexes"):
                value = data.get(key)
                if value is None:
                    continue
                if not isinstance(value, list) or \
                        not all(isinstance(item, str) for item in value):
                    raise RefuseError("DENY_LIST_FIELD", key)
                entries[key] = value
        merged_names = entries["app_names"] + entries["extra_app_names"]
        merged_bundles = entries["bundle_ids"] + entries["extra_bundle_ids"]
        merged_titles = entries["title_regexes"] + entries["extra_title_regexes"]
        patterns = []
        for pattern in merged_titles:
            try:
                patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                raise RefuseError("DENY_LIST_REGEX", pattern)
        return cls({n.lower() for n in merged_names},
                   {b.lower() for b in merged_bundles}, patterns)

    def matches(self, app_name, bundle_id, window_title):
        if app_name and app_name.lower() in self.app_names:
            return "app_name"
        if bundle_id and bundle_id.lower() in self.bundle_ids:
            return "bundle_id"
        if window_title:
            for pattern in self.title_regexes:
                if pattern.search(window_title):
                    return "title_regex"
        return None


# ── presence ─────────────────────────────────────────────────────────────────

def parse_ioreg_idle(text):
    """Parse `ioreg -c IOHIDSystem` output, returning idle seconds (float) or
    None when HIDIdleTime is absent."""
    if not isinstance(text, str):
        return None
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', text)
    if not match:
        return None
    return int(match.group(1)) / 1e9


class Presence:
    """Human-presence gate derived from the macOS HID idle time.

    Threshold priority: explicit constructor argument > MMOS_CU_PRESENCE_MIN_IDLE
    env > runtime.json presence_min_idle_seconds > DEFAULT_MIN_IDLE_SECONDS
    (180 s for ALL acts, slice and non-slice alike).
    """

    def __init__(self, min_idle_seconds=None, ioreg_bin=None, runtime=None):
        raw = os.environ.get("MMOS_CU_PRESENCE_MIN_IDLE")
        runtime_value = runtime.get("presence_min_idle_seconds") \
            if isinstance(runtime, dict) else None
        if min_idle_seconds is not None:
            self.min_idle = float(min_idle_seconds)
        elif raw:
            try:
                self.min_idle = float(raw)
            except ValueError:
                self.min_idle = DEFAULT_MIN_IDLE_SECONDS
            else:
                if self.min_idle < MIN_IDLE_FLOOR_SECONDS:
                    raise RefuseError(
                        "PRESENCE_MIN_IDLE_FLOOR",
                        "MMOS_CU_PRESENCE_MIN_IDLE %r is below the %.0fs "
                        "floor" % (raw, MIN_IDLE_FLOOR_SECONDS))
        elif runtime_value is not None:
            self.min_idle = float(runtime_value)
            if self.min_idle < MIN_IDLE_FLOOR_SECONDS:
                raise RefuseError(
                    "PRESENCE_MIN_IDLE_FLOOR",
                    "runtime presence_min_idle_seconds %r is below the "
                    "%.0fs floor" % (runtime_value, MIN_IDLE_FLOOR_SECONDS))
        else:
            self.min_idle = DEFAULT_MIN_IDLE_SECONDS
        self.ioreg_bin = ioreg_bin or "/usr/sbin/ioreg"

    def observe(self):
        """Single-shot ioreg call; no retry."""
        try:
            result = subprocess.run(
                [self.ioreg_bin, "-c", "IOHIDSystem"], capture_output=True,
                text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return {"human_idle_seconds": None, "human_active": None}
        idle = parse_ioreg_idle(result.stdout or "")
        if idle is None:
            return {"human_idle_seconds": None, "human_active": None}
        return {"human_idle_seconds": round(idle, 3),
                "human_active": idle < self.min_idle}

    def gate_ok(self):
        state = self.observe()
        if state["human_active"] is None:
            raise OpError("PRESENCE_UNKNOWN",
                          "HIDIdleTime not readable; ACT refused")
        return state


# ── lease ────────────────────────────────────────────────────────────────────

def _atomic_write(path, payload):
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".lease-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Lease:
    """Single-holder advisory lease persisted as JSON next to a lock file.

    Acquire is atomic: an O_CREAT|O_EXCL lockfile serializes contenders, then
    the holder writes lease.json. A lease whose expires_at is in the past is
    treated as abandoned by a crashed holder and may be taken over. Every ACT
    re-checks ownership and renews the expiry (heartbeat).
    """

    def __init__(self, state_dir=None):
        override = os.environ.get("MMOS_CU_STATE_DIR")
        self.state_dir = state_dir or override or os.path.join(HERE, "state")
        self.lease_path = os.path.join(self.state_dir, "lease.json")
        self.lock_path = os.path.join(self.state_dir, "lease.lock")

    def _read(self):
        try:
            with open(self.lease_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _write_locked(self, payload):
        lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                          0o600)
        try:
            _atomic_write(self.lease_path, payload)
        finally:
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass

    def acquire(self, owner, ttl_seconds=DEFAULT_LEASE_TTL):
        if not owner or not isinstance(owner, str):
            raise OpError("LEASE_OWNER_REQUIRED", "owner id missing")
        try:
            ttl = float(ttl_seconds)
        except (TypeError, ValueError):
            raise OpError("LEASE_TTL_INVALID", repr(ttl_seconds))
        if ttl < 5 or ttl > 3600:
            raise OpError("LEASE_TTL_INVALID", repr(ttl_seconds))
        os.makedirs(self.state_dir, exist_ok=True)
        now = time.time()
        existing = self._read()
        if existing:
            expires = existing.get("expires_at")
            if isinstance(expires, (int, float)) and expires > now:
                if existing.get("owner") == owner:
                    # Already held by this owner: refresh the heartbeat.
                    self._write_locked({
                        "owner": owner, "acquired_at":
                            existing.get("acquired_at", now),
                        "expires_at": now + ttl, "heartbeat_at": now})
                    return {"held": True, "owner": owner, "renewed": True,
                            "expires_at": now + ttl}
                raise OpError("LEASE_HELD", "owner=%s expires_in=%.0fs" % (
                    (existing.get("owner") or "")[:8] + "…", expires - now))
            # Expired lease: prior holder crashed or let it lapse; take over.
        payload = {"owner": owner, "acquired_at": now,
                   "expires_at": now + ttl, "heartbeat_at": now}
        try:
            self._write_locked(payload)
        except FileExistsError:
            raise OpError("LEASE_CONTENDED",
                          "another acquire holds the lockfile; single-shot")
        return {"held": True, "owner": owner, "took_over": bool(existing),
                "expires_at": now + ttl}

    def release(self, owner):
        lease = self._read()
        if not lease:
            return {"released": True, "note": "no lease"}
        if lease.get("owner") != owner:
            raise OpError("LEASE_NOT_OWNER",
                          "held by %s" % ((lease.get("owner") or "")[:8] + "…"))
        try:
            os.unlink(self.lease_path)
        except OSError:
            pass
        return {"released": True}

    def status(self):
        lease = self._read()
        if not lease:
            return {"held": False}
        expires = lease.get("expires_at")
        remaining = None
        if isinstance(expires, (int, float)):
            remaining = round(max(0.0, expires - time.time()), 3)
        owner = lease.get("owner")
        out = {"held": bool(remaining), "expires_in_seconds": remaining}
        if isinstance(owner, str) and owner:
            # Owner id is redacted in status output (first 8 chars + ellipsis);
            # acquire/release still require the EXACT owner string.
            out["owner"] = owner[:8] + "…"
            out["owner_redacted"] = True
        return out

    def require_and_renew(self, owner, ttl_seconds=DEFAULT_LEASE_TTL):
        """Gate for ACT ops: verifies ownership, renews expiry in place."""
        lease = self._read()
        now = time.time()
        if not lease or lease.get("owner") != owner:
            raise OpError("LEASE_NOT_HELD",
                          "acquire the lease with lease_acquire first")
        expires = lease.get("expires_at")
        if not isinstance(expires, (int, float)) or expires <= now:
            raise OpError("LEASE_NOT_HELD", "lease expired; re-acquire")
        self._write_locked({
            "owner": owner,
            "acquired_at": lease.get("acquired_at", now),
            "expires_at": now + float(ttl_seconds), "heartbeat_at": now})
        return True


# ── pacing ───────────────────────────────────────────────────────────────────

class Pacer:
    """Per-target-window pacing between slice_paste / slice_send sequences.

    The completion time of the last paste/send sequence on a window id is
    persisted in pacing.json under the state dir; a second paste/send on the
    SAME window inside the configured interval is refused with PACING_WAIT
    (seconds remaining). The interval defaults to 180 s; priority:
    explicit constructor argument > MMOS_CU_PACING_SECONDS env >
    runtime.json pacing_seconds > DEFAULT_PACING_SECONDS. One worker at a
    time is already guaranteed by the lease; pacing additionally spaces
    repeated sequences on the same window.
    """

    def __init__(self, state_dir=None, seconds=None, runtime=None):
        override = os.environ.get("MMOS_CU_STATE_DIR")
        self.state_dir = state_dir or override or os.path.join(HERE, "state")
        self.path = os.path.join(self.state_dir, "pacing.json")
        raw = os.environ.get("MMOS_CU_PACING_SECONDS")
        runtime_value = runtime.get("pacing_seconds") \
            if isinstance(runtime, dict) else None
        if seconds is not None:
            self.seconds = float(seconds)
        elif raw:
            try:
                self.seconds = float(raw)
            except ValueError:
                self.seconds = DEFAULT_PACING_SECONDS
            else:
                if self.seconds < PACING_FLOOR_SECONDS:
                    raise RefuseError(
                        "PACING_SECONDS_FLOOR",
                        "MMOS_CU_PACING_SECONDS %r is below the %.0fs floor"
                        % (raw, PACING_FLOOR_SECONDS))
        elif runtime_value is not None:
            self.seconds = float(runtime_value)
            if self.seconds < PACING_FLOOR_SECONDS:
                raise RefuseError(
                    "PACING_SECONDS_FLOOR",
                    "runtime pacing_seconds %r is below the %.0fs floor"
                    % (runtime_value, PACING_FLOOR_SECONDS))
        else:
            self.seconds = DEFAULT_PACING_SECONDS

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def check(self, window_id):
        """Refuse with PACING_WAIT when the last paste/send sequence on this
        window is still inside the interval. No write, no dispatch."""
        last = self._read().get(str(window_id))
        if isinstance(last, (int, float)):
            remaining = self.seconds - (time.time() - last)
            if remaining > 0:
                raise OpError("PACING_WAIT",
                              "%.0fs remaining until the next slice paste/send "
                              "sequence may target window %s"
                              % (remaining, window_id))

    def record(self, window_id):
        """Record the dispatch attempt time for this window (atomic write)."""
        data = self._read()
        data[str(window_id)] = time.time()
        os.makedirs(self.state_dir, exist_ok=True)
        _atomic_write(self.path, data)


# ── peekaboo adapter ─────────────────────────────────────────────────────────

def _child_env():
    """Environment for peekaboo children with ANTHROPIC_* (secrets) stripped."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith("ANTHROPIC_")}


def _bounded(text, limit=MAX_ERROR_TEXT):
    return (text or "").strip().replace("\n", " ")[:limit]


def _is_foreground_required(text):
    """True when a peekaboo failure says the element/action needs the app to
    be frontmost. Detection is intentionally narrow: the message must name
    foreground AND a requirement/refusal. It never triggers an automatic
    escalation; the caller decides whether to re-dispatch opt-in foreground."""
    low = (text or "").lower()
    if "foreground" not in low:
        return False
    return any(marker in low for marker in (
        "required", "requires", "refused", "refusal", "only", "needs"))


def _deep_find(obj, keys):
    """Depth-first search for the first dict entry whose key is in `keys`."""
    if isinstance(obj, dict):
        lowered = {k.lower(): v for k, v in obj.items()}
        for key in keys:
            if key in lowered:
                return lowered[key]
        for value in obj.values():
            found = _deep_find(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _deep_find(value, keys)
            if found is not None:
                return found
    return None


def _deep_collect_strings(obj, keys, out):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys and isinstance(value, str):
                out.append(value)
            elif key.lower() in keys and isinstance(value, list):
                out.extend(item for item in value if isinstance(item, str))
            else:
                _deep_collect_strings(value, keys, out)
    elif isinstance(obj, list):
        for value in obj:
            _deep_collect_strings(value, keys, out)


class PeekabooAdapter:
    """Single-shot peekaboo CLI wrapper. One subprocess per operation, no
    retry loop anywhere; a timeout or unreadable outcome is surfaced as
    EFFECT_UNKNOWN by the caller."""

    def __init__(self, runtime):
        self.bin = runtime["peekaboo_bin"]
        self.input_strategy = runtime["input_strategy"]
        self.act_input_strategy = runtime.get("act_input_strategy", "actionOnly")

    def _argv(self, args, strategy=None, with_strategy=True):
        argv = [self.bin] + list(args)
        if with_strategy:
            argv += ["--input-strategy", strategy or self.input_strategy]
        argv += ["--no-remote"]
        # --bridge-socket is deliberately never emitted (force local service).
        return argv

    def run_json(self, args, timeout, strategy=None, with_strategy=True):
        """Run one peekaboo command expecting JSON; NEVER retried."""
        argv = self._argv(args, strategy, with_strategy)
        try:
            result = subprocess.run(argv, capture_output=True, text=True,
                                    timeout=timeout, check=False,
                                    env=_child_env())
        except subprocess.TimeoutExpired:
            raise OpError("DISPATCH_TIMEOUT",
                          "peekaboo %s exceeded %.0fs" % (args[0], timeout))
        except OSError as error:
            raise OpError("DISPATCH_UNAVAILABLE", str(error))
        stdout = result.stdout or ""
        try:
            data = json.loads(stdout) if stdout.strip() else None
        except ValueError:
            data = None
        if result.returncode != 0 or not isinstance(data, dict):
            # Detail carries stderr only; stdout may embed window content and
            # must never flow into a receipt or error message.
            if _is_foreground_required(result.stderr):
                raise OpError("FOREGROUND_REQUIRED", _bounded(result.stderr))
            raise OpError("CLI_ERROR", "rc=%s %s" % (
                result.returncode, _bounded(result.stderr)))
        if data.get("success") is False:
            errors = data.get("errors")
            message = ""
            if isinstance(errors, list) and errors:
                first = errors[0]
                message = first if isinstance(first, str) else json.dumps(first)
            if _is_foreground_required(message):
                raise OpError("FOREGROUND_REQUIRED", _bounded(message))
            raise OpError("CLI_ERROR", _bounded(message or "peekaboo failed"))
        return data.get("data", data)

    # ── SEE ──

    def list_apps(self):
        data = self.run_json(["app", "list", "--json"], SEE_TIMEOUT_S)
        apps = data.get("apps") if isinstance(data, dict) else None
        if not isinstance(apps, list):
            raise OpError("CLI_OUTPUT_INVALID", "app list: no apps array")
        out = []
        for app in apps:
            if not isinstance(app, dict):
                continue
            out.append({
                "name": app.get("name"),
                "bundle_id": app.get("bundle_id"),
                "pid": app.get("pid"),
                "is_active": bool(app.get("is_active")),
                "is_hidden": bool(app.get("is_hidden")),
            })
        return out

    def list_windows(self, app):
        data = self.run_json(["window", "list", "--app", app, "--json"],
                             SEE_TIMEOUT_S)
        windows = data.get("windows") if isinstance(data, dict) else None
        if not isinstance(windows, list):
            raise OpError("CLI_OUTPUT_INVALID", "window list: no windows array")
        out = []
        for window in windows:
            if not isinstance(window, dict):
                continue
            out.append({
                "window_id": window.get("window_id", window.get("windowID")),
                "title": window.get("title"),
                "owner_pid": window.get("owner_pid", window.get("pid")),
                # Resolved app identity when the CLI reports it per window;
                # the windows op deny-checks and filters on it (FIX 8).
                "app": window.get("app", window.get("app_name")),
                "bundle_id": window.get("bundle_id",
                                        window.get("app_bundle_id")),
            })
        return out

    def inspect_window(self, window_id):
        """Accessibility tree of ONE window as bounded indented text."""
        data = self.run_json(["see", "--window-id", str(window_id), "--json",
                              "--tree", "--no-screenshot"], SEE_TIMEOUT_S)
        return data

    def snapshot_window(self, window_id):
        """Fresh snapshot of ONE window: snapshot_id, ui_elements and
        coordinate_context. This is the observation every ACT dispatches on
        (``--snapshot <id> --on <elem>``); it never passes --app/--pid and
        never raises foreground UI."""
        data = self.run_json(["see", "--window-id", str(window_id), "--json"],
                             SEE_TIMEOUT_S)
        return data

    def capture_window(self, window_id, ocr=False):
        """Capture ONE window into a private staging directory.

        Returns (png_bytes, meta, staging_dir). The caller MUST remove
        staging_dir in a finally block. The image never outlives the call
        unless keep_path (validated against MMOS_CU_SCRATCH) is supplied.
        """
        staging = tempfile.mkdtemp(prefix="mmos-cu-")
        target = os.path.join(staging, "window.png")
        args = ["see", "--window-id", str(window_id), "--json", "--path",
                target]
        if ocr:
            args.append("--ocr")
        try:
            data = self.run_json(args, SEE_TIMEOUT_S)
            with open(target, "rb") as handle:
                png = handle.read()
            if not png:
                raise OpError("CAPTURE_EMPTY", "no bytes captured")
            return png, data, staging
        except BaseException:
            try:
                import shutil
                shutil.rmtree(staging, ignore_errors=True)
            except Exception:
                pass
            raise

    # ── ACT ──

    def act(self, args, timeout=ACT_TIMEOUT_S):
        """Single dispatch of one act; outcome read back once.

        Acts always use the runtime's act_input_strategy (actionOnly) so AX
        actions are preferred and no synthetic keystrokes are generated.
        """
        data = self.run_json(args, timeout, strategy=self.act_input_strategy)
        return data

    def paste(self, args, timeout=PASTE_TIMEOUT_S):
        """Single dispatch of `peekaboo paste`; outcome read back once.

        paste is NOT an element-targeted AX act: it carries --text plus
        --app/--window-id targeting and is dispatched WITHOUT
        --input-strategy (the input is the paste chord itself, not element
        targeting). Still exactly one subprocess, --no-remote always,
        ANTHROPIC_* stripped from the child environment, never retried.
        The command sets the clipboard, delivers the paste chord, and
        restores the previous clipboard.
        """
        return self.run_json(args, timeout, with_strategy=False)


def _top_find(obj, keys):
    """Case-insensitive TOP-LEVEL key lookup in a dict; None otherwise.

    Used by the identity/bounds resolvers so payload-level and
    coordinate-context values win over any nested decoy key found by the
    deep scan (identity-before-decoy, security-fix pass)."""
    if isinstance(obj, dict):
        lowered = {k.lower(): v for k, v in obj.items()}
        for key in keys:
            if key in lowered:
                return lowered[key]
    return None


_IDENTITY_APP_KEYS = ["app", "app_name", "application"]
_IDENTITY_BUNDLE_KEYS = ["bundle_id", "app_bundle_id"]
_IDENTITY_TITLE_KEYS = ["window_title", "title"]


def window_identity(meta):
    """Best-effort {app_name, bundle_id, window_title} from peekaboo JSON.

    Order: payload top level, then coordinate_context, and only then the
    deep scan as a last fallback — a nested decoy "app" key (e.g. inside a
    ui_element) must never outrank the payload-level identity."""
    app = _top_find(meta, _IDENTITY_APP_KEYS)
    bundle = _top_find(meta, _IDENTITY_BUNDLE_KEYS)
    title = _top_find(meta, _IDENTITY_TITLE_KEYS)
    coord = _top_find(meta, ["coordinate_context"])
    if isinstance(coord, dict):
        if app is None:
            app = _top_find(coord, _IDENTITY_APP_KEYS)
        if bundle is None:
            bundle = _top_find(coord, _IDENTITY_BUNDLE_KEYS)
        if title is None:
            title = _top_find(coord, _IDENTITY_TITLE_KEYS)
    if app is None:
        app = _deep_find(meta, _IDENTITY_APP_KEYS)
    if bundle is None:
        bundle = _deep_find(meta, _IDENTITY_BUNDLE_KEYS)
    if title is None:
        title = _deep_find(meta, ["window_title", "window", "title"])
    return {"app_name": app if isinstance(app, str) else None,
            "bundle_id": bundle if isinstance(bundle, str) else None,
            "window_title": title if isinstance(title, str) else None}


def window_bounds(meta):
    """Best-effort (width, height) of the captured window from peekaboo JSON.

    Prefers the coordinate-context window-level logical bounds of a fresh
    `see` receipt; the deep scan (element-level bounds/frame dicts, CG-style
    {origin, size} rects) runs only as a fallback so a smaller nested
    "bounds" (e.g. of one ui_element) can never shrink the window frame.
    """
    coord = _top_find(meta, ["coordinate_context"])
    if coord is not None:
        result = _window_bounds_walk(coord)
        if result:
            return result
    return _window_bounds_deep(meta)


def _window_bounds_from_dict(value):
    if not isinstance(value, dict):
        return None
    width = value.get("width", value.get("w"))
    height = value.get("height", value.get("h"))
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        return float(width), float(height)
    size = value.get("size")
    if isinstance(size, dict):
        width = size.get("width", size.get("w"))
        height = size.get("height", size.get("h"))
        if isinstance(width, (int, float)) and \
                isinstance(height, (int, float)):
            return float(width), float(height)
    return None


def _window_bounds_walk(value, depth=0):
    if depth > 4:
        return None
    result = _window_bounds_from_dict(value)
    if result:
        return result
    if isinstance(value, dict):
        for key in ("window_bounds", "bounds", "frame", "content_bounds",
                    "size", "coordinate_context", "window"):
            if key in value:
                result = _window_bounds_walk(value[key], depth + 1)
                if result:
                    return result
    return None


def _window_bounds_deep(meta):
    candidates = []
    for keys in (["window_bounds", "bounds", "frame", "content_bounds"],):
        found = _deep_find(meta, keys)
        if found is not None:
            candidates.append(found)

    for candidate in candidates:
        result = _window_bounds_walk(candidate)
        if result:
            return result
        if isinstance(candidate, list) and len(candidate) >= 4 and all(
                isinstance(v, (int, float)) for v in candidate[:4]):
            return float(candidate[2]), float(candidate[3])
    return None


def snapshot_id_of(snap):
    """snapshot_id from a `see --json` payload, or None."""
    value = _deep_find(snap, ["snapshot_id", "snapshotid"])
    return value if isinstance(value, str) and value else None


def snapshot_elements(snap):
    """ui_elements[] from a `see --json` payload (empty list if absent)."""
    value = _deep_find(snap, ["ui_elements", "uielements", "elements"])
    return value if isinstance(value, list) else []


def resolve_element(snap, element_ref):
    """Resolve a caller element_ref against the fresh snapshot's ui_elements.

    Exact element id first (the id shown by inspect / see), then a UNIQUE
    label match. Ambiguous or absent refs refuse with ELEMENT_NOT_FOUND; the
    act is never dispatched against a guessed element.
    """
    elements = [e for e in snapshot_elements(snap) if isinstance(e, dict)]
    for element in elements:
        ident = element.get("id", element.get("element_id"))
        if ident is not None and str(ident) == element_ref:
            return element
    matches = [e for e in elements
               if str(e.get("label", e.get("text", ""))) == element_ref]
    if len(matches) == 1:
        return matches[0]
    raise OpError("ELEMENT_NOT_FOUND",
                  "element_ref %r not in the fresh snapshot" % element_ref)


def element_id_of(element):
    ident = element.get("id", element.get("element_id"))
    return str(ident) if ident is not None else None


def render_tree(data, max_lines=MAX_TREELINES):
    """Render a peekaboo `see --tree` payload as bounded indented text with
    stable element paths usable as act targets."""
    lines = []
    tree = _deep_find(data, ["tree", "text_tree", "accessibility_tree"])
    if isinstance(tree, str):
        lines = tree.splitlines()
    elif isinstance(tree, list):
        stack = []

        def walk(nodes, depth):
            for node in nodes:
                if len(lines) >= max_lines:
                    return
                if not isinstance(node, dict):
                    continue
                path = ".".join(stack + [str(len(lines))])
                role = str(node.get("role", node.get("type", "node")))
                label = node.get("label", node.get("text", node.get("name", "")))
                element_id = node.get("id", node.get("element_id"))
                text = "%s%s: %s" % ("  " * depth, role, label)
                if element_id:
                    text += "  [@%s]" % element_id
                text += "  (path %s)" % path
                lines.append(text[:MAX_LINE_CHARS])
                children = node.get("children")
                if isinstance(children, list):
                    walk(children, depth + 1)

        walk(tree, 0)
    if not lines:
        return "(accessibility tree unavailable for this window)"
    lines = lines[:max_lines]
    if len(lines) == max_lines:
        lines.append("... (tree truncated at %d lines)" % max_lines)
    return "\n".join(lines)


def extract_ocr(meta):
    strings = []
    _deep_collect_strings(meta, {"ocr", "ocr_text", "text", "lines"}, strings)
    return "\n".join(strings)[:8000]


def slice_window_text(snap):
    """Bounded corpus of ONE window's AX text (+ OCR text if present in the
    snapshot payload) for the slice_send challenge scan. Labels and values
    of the fresh snapshot's ui_elements, the window title, and any OCR-ish
    text fields. The corpus itself is never returned to the caller."""
    parts = []
    identity = window_identity(snap)
    if identity["window_title"]:
        parts.append(identity["window_title"])
    for element in snapshot_elements(snap):
        if isinstance(element, dict):
            for key in ("label", "value"):
                value = element.get(key)
                if isinstance(value, str) and value:
                    parts.append(value)
    ocr = extract_ocr(snap)
    if ocr:
        parts.append(ocr)
    return "\n".join(parts)[:20000]


def scan_challenge_text(text, extra_patterns=()):
    """Scan window text for challenge patterns (case-insensitive).

    Returns {"pattern", "quote"} with a bounded quote of the surrounding
    text when a pattern matches, else None. The caller must STOP: no
    dispatch, no retry after a challenge refusal."""
    if not text:
        return None
    lowered = text.lower()
    patterns = [p.lower() for p in DEFAULT_CHALLENGE_PATTERNS]
    patterns += [p.lower() for p in extra_patterns
                 if isinstance(p, str) and p]
    for pattern in patterns:
        idx = lowered.find(pattern)
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(pattern) + 60)
            quote = text[start:end].replace("\n", " ")
            return {"pattern": pattern,
                    "quote": _bounded(quote, CHALLENGE_QUOTE_CHARS)}
    return None


# ── receipts ─────────────────────────────────────────────────────────────────

def receipt(op, window_id, element_ref, status, cause=None, observed="",
            foreground=False, extra=None, target_extra=None):
    target = {"op": op, "window_id": window_id, "element_ref": element_ref}
    if target_extra:
        target.update(target_extra)
    out = {"target": target,
           "status": status,
           "observed": _bounded(observed, MAX_OBSERVED)}
    if foreground:
        out["foreground"] = True
    if cause:
        out["cause"] = "%s: %s" % (cause.code, cause.detail) \
            if isinstance(cause, OpError) else str(cause)
    if extra:
        out.update(extra)
    return out


# ── vision ───────────────────────────────────────────────────────────────────

VISION_PROMPT = (
    "You are analyzing a screenshot of ONE macOS application window to help "
    "an operator drive its UI. Answer the question, then list the on-screen "
    "elements relevant to it. Respond with ONLY a JSON object, no markdown "
    "fence, of the form:\n"
    '{"answer": "<short answer>", "elements": [{"label": "<visible text>", '
    '"x": <0-1000>, "y": <0-1000>}]}\n'
    "Coordinates x,y are normalized 0-1000 relative to the image (0,0 top "
    "left, 1000,1000 bottom right). Omit elements you cannot see."
)

# Vision prompt caps: a caller may not smuggle unbounded text into the
# vision prompt via question or element_hints. Over-limit input is refused
# (QUESTION_TOO_LONG / HINTS_TOO_LONG), never silently truncated.
VISION_QUESTION_MAX_CHARS = 2000
VISION_HINT_MAX_ENTRIES = 20
VISION_HINT_MAX_CHARS = 120
VISION_HINTS_MAX_TOTAL_CHARS = 1200


class VisionClient:
    """Anthropic-protocol vision request over urllib. The token is read from
    the environment at CALL time only and never stored, logged or passed on
    argv. Image bytes/base64 never appear in logs, errors or files."""

    def __init__(self, model=None, base_url=None, token=None, timeout=VISION_TIMEOUT_S):
        self.model = model or os.environ.get("MMOS_CU_VISION_MODEL") \
            or DEFAULT_VISION_MODEL
        self.base_url = (base_url if base_url is not None
                         else os.environ.get("ANTHROPIC_BASE_URL"))
        self.token = token  # injected only by tests; production reads env
        self.timeout = timeout

    def _resolve_token(self):
        token = self.token if self.token is not None \
            else os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not token:
            raise OpError("VISION_UNCONFIGURED",
                          "ANTHROPIC_AUTH_TOKEN not set in this process")
        if not self.base_url:
            raise OpError("VISION_UNCONFIGURED",
                          "ANTHROPIC_BASE_URL not set in this process")
        return token

    def configured(self):
        """True when a vision relay can actually be attempted (token +
        endpoint resolvable right now). slice_look falls back to
        accessibility text alone when this is False."""
        token = self.token if self.token is not None \
            else os.environ.get("ANTHROPIC_AUTH_TOKEN")
        return bool(token and self.base_url)

    def _require_secure_endpoint(self):
        """The vision endpoint must be https, or plain http only on the
        loopback (localhost / 127.0.0.1 / ::1); anything else would send the
        captured window image and token over an unencrypted link."""
        try:
            parsed = urllib.parse.urlparse(self.base_url or "")
        except ValueError:
            raise OpError("VISION_ENDPOINT_INSECURE",
                          "endpoint URL unparseable; refused")
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" and \
                host not in ("localhost", "127.0.0.1", "::1"):
            raise OpError("VISION_ENDPOINT_INSECURE",
                          "endpoint scheme/host refused; https or loopback "
                          "http only")

    def ask(self, png_bytes, question, element_hints=None):
        if not question or not isinstance(question, str):
            raise OpError("VISION_QUESTION_REQUIRED", "question missing")
        if len(question) > VISION_QUESTION_MAX_CHARS:
            raise OpError("QUESTION_TOO_LONG",
                          "question exceeds %d chars"
                          % VISION_QUESTION_MAX_CHARS)
        token = self._resolve_token()
        self._require_secure_endpoint()
        prompt = VISION_PROMPT
        if element_hints:
            # Bounded final assembly: per-entry/total caps are enforced on
            # caller-supplied hints at the op boundary (_validate_vision_hints).
            prompt += "\nHints from the accessibility tree: %s" % \
                ("; ".join(str(h) for h in element_hints[:20])
                 [:VISION_HINTS_MAX_TOTAL_CHARS])
        prompt += "\n\nQuestion: %s" % question
        import base64
        encoded = base64.b64encode(png_bytes).decode("ascii")
        body = {
            "model": self.model,
            "max_tokens": 300,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png",
                                "data": encoded}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        url = self.base_url.rstrip("/") + "/v1/messages"
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={
                "x-api-key": token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            })
        # Single-shot HTTP dispatch; no retry.
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) \
                    as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as error:
            raise OpError("VISION_UNAVAILABLE", _bounded(str(error), 120))
        text = ""
        content = payload.get("content") if isinstance(payload, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
        parsed = _parse_vision_json(text)
        elements = parsed.get("elements") if isinstance(parsed, dict) else None
        answer = parsed.get("answer") if isinstance(parsed, dict) else None
        if not isinstance(elements, list):
            elements = []
        elements = [{"label": str(e.get("label", ""))[:120],
                     "x": e.get("x"), "y": e.get("y")}
                    for e in elements if isinstance(e, dict)][:30]
        if answer is None:
            answer = text[:1000]
        return {"answer": answer, "elements": elements, "model": self.model}


def _parse_vision_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def _validate_vision_hints(hints):
    """Cap the caller-supplied element_hints (count, per-entry length, total
    length) at the op boundary, BEFORE any capture or network dispatch.

    The layer-generated tree hint added afterwards is internally bounded and
    is not subject to the caller caps."""
    if not isinstance(hints, list):
        return
    lengths = [len(str(h)) for h in hints]
    if len(hints) > VISION_HINT_MAX_ENTRIES:
        raise OpError("HINTS_TOO_LONG",
                      "element_hints exceeds %d entries"
                      % VISION_HINT_MAX_ENTRIES)
    if any(length > VISION_HINT_MAX_CHARS for length in lengths):
        raise OpError("HINTS_TOO_LONG",
                      "an element_hints entry exceeds %d chars"
                      % VISION_HINT_MAX_CHARS)
    if sum(lengths) > VISION_HINTS_MAX_TOTAL_CHARS:
        raise OpError("HINTS_TOO_LONG",
                      "element_hints total length exceeds %d chars"
                      % VISION_HINTS_MAX_TOTAL_CHARS)


# ── keep_path guard ──────────────────────────────────────────────────────────

def validate_keep_path(keep_path):
    """keep_path must be absolute and inside MMOS_CU_SCRATCH, else refuse."""
    if not keep_path or not isinstance(keep_path, str):
        raise OpError("KEEP_PATH_REQUIRED", "keep_path missing")
    if not os.path.isabs(keep_path):
        raise OpError("KEEP_PATH_NOT_ABSOLUTE", keep_path)
    scratch = os.environ.get("MMOS_CU_SCRATCH")
    if not scratch:
        raise OpError("KEEP_PATH_NO_SCRATCH",
                      "MMOS_CU_SCRATCH is not set; keeping captures is off")
    real_keep = os.path.realpath(keep_path)
    real_scratch = os.path.realpath(scratch)
    if real_keep != real_scratch and not real_keep.startswith(
            real_scratch.rstrip(os.sep) + os.sep):
        raise OpError("KEEP_PATH_OUTSIDE_SCRATCH", keep_path)
    return keep_path


# ── tool dispatch ────────────────────────────────────────────────────────────

class ToolContext:
    def __init__(self, runtime, deny, lease, presence, adapter, vision,
                 pacer=None):
        self.runtime = runtime
        self.deny = deny
        self.lease = lease
        self.presence = presence
        self.adapter = adapter
        self.vision = vision
        self.pacer = pacer if pacer is not None else Pacer()


def _require_window_id(args):
    window_id = args.get("window_id")
    if not isinstance(window_id, int) or isinstance(window_id, bool):
        raise OpError("WINDOW_ID_REQUIRED",
                      "exactly one integer window_id is required for this op")
    return window_id


def _deny_gate(ctx, app_name, bundle_id, window_title):
    matched = ctx.deny.matches(app_name, bundle_id, window_title)
    if matched:
        raise OpError("DENY_LISTED",
                      "matched by %s" % matched)


def _deny_gate_window(ctx, meta):
    identity = window_identity(meta)
    matched = ctx.deny.matches(identity["app_name"], identity["bundle_id"],
                               identity["window_title"])
    if matched:
        raise OpError("DENY_LISTED", "matched by %s" % matched)
    if not identity["app_name"] and not identity["bundle_id"]:
        raise OpError("WINDOW_IDENTITY_UNKNOWN",
                      "owning application not resolvable; refused")
    return identity


def _act_gate(ctx, args, window_id):
    """Deny list, then lease (renewed), then human-presence gate.

    Returns the identity/bounds metadata from the read-only window probe so
    callers needing window geometry do not dispatch a second probe.
    """
    meta = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, meta)
    ctx.lease.require_and_renew(args.get("owner"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; act refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    return meta


def _foreground_gate(ctx, args):
    """Re-check lease + human presence for an opt-in foreground dispatch."""
    ctx.lease.require_and_renew(args.get("owner"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; foreground refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    return state


def _act_observe(ctx, args, window_id):
    """Gate, then take the FRESH snapshot every ACT dispatches on.

    Order: lease + presence (local, no read), then one ``see --window-id N
    --json`` (identity, ui_elements, coordinate_context), then the deny list
    on that read. Returns (snapshot, snapshot_id).
    """
    ctx.lease.require_and_renew(args.get("owner"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; act refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    snap = ctx.adapter.snapshot_window(window_id)
    _deny_gate_window(ctx, snap)
    snapshot_id = snapshot_id_of(snap)
    if not snapshot_id:
        raise OpError("SNAPSHOT_UNAVAILABLE",
                      "peekaboo see returned no snapshot_id; act refused")
    return snap, snapshot_id


def _dispatch_act(ctx, args, base_argv):
    """One background dispatch. A foreground-required refusal is a terminal
    NOT_APPLIED unless the caller opted in, in which case it becomes ONE NEW
    act after the gates are re-checked. Never a retry of the same dispatch.

    Returns (result_meta, used_foreground).
    """
    allow = bool(args.get("allow_foreground"))
    try:
        return ctx.adapter.act(list(base_argv)), False
    except OpError as error:
        if error.code != "FOREGROUND_REQUIRED" or not allow:
            raise
    _foreground_gate(ctx, args)
    return ctx.adapter.act(list(base_argv) + ["--foreground"]), True


def _act_receipt(ctx, args, window_id, op, element_ref, result_meta,
                 snapshot_id, element=None, foreground=False):
    parts = ["snapshot=%s" % snapshot_id]
    if element is not None:
        parts.append("element=%s role=%s label=%s" % (
            element_id_of(element), str(element.get("role", ""))[:40],
            str(element.get("label", ""))[:60]))
    if isinstance(result_meta, dict):
        summary = {k: result_meta[k] for k in list(result_meta)[:4]
                   if isinstance(result_meta[k], (str, int, float, bool))}
        if summary:
            parts.append(_bounded(json.dumps(summary), 80))
    return receipt(op, window_id, element_ref, "APPLIED",
                   observed=" ".join(parts) or "peekaboo reported success",
                   foreground=foreground)


def handle_tool_call(ctx, args):
    """Dispatch one tools/call. Returns an MCP result dict."""
    if not isinstance(args, dict):
        return _error_result("INVALID_ARGUMENTS", "arguments must be an object")
    action = args.get("action")
    if action not in ACTIONS:
        return _error_result("UNKNOWN_ACTION", repr(action))
    handler = _HANDLERS[action]
    try:
        return handler(ctx, args)
    except OpError as error:
        if error.code in ("LEASE_NOT_HELD", "LEASE_HELD", "LEASE_NOT_OWNER",
                          "LEASE_OWNER_REQUIRED", "LEASE_TTL_INVALID",
                          "HUMAN_ACTIVE", "PRESENCE_UNKNOWN", "DENY_LISTED",
                          "WINDOW_IDENTITY_UNKNOWN", "KEEP_PATH_NOT_ABSOLUTE",
                          "KEEP_PATH_NO_SCRATCH", "KEEP_PATH_OUTSIDE_SCRATCH",
                          "CHORD_GLOBAL", "CHORD_INVALID",
                          "CHORD_NOT_ALLOWED",
                          "COORDS_REQUIRED", "WINDOW_BOUNDS_UNKNOWN",
                          "POINT_OUTSIDE_WINDOW", "APP_REQUIRED",
                          "WINDOW_ID_REQUIRED", "VISION_QUESTION_REQUIRED",
                          "VISION_UNCONFIGURED", "KEEP_PATH_REQUIRED",
                          "CLI_OUTPUT_INVALID", "CAPTURE_EMPTY",
                          "ELEMENT_REF_REQUIRED", "ELEMENT_REF_INVALID",
                          "ELEMENT_NOT_FOUND", "SNAPSHOT_UNAVAILABLE",
                          "FOREGROUND_REQUIRED", "TEXT_REQUIRED",
                          "DIRECTION_INVALID", "AMOUNT_INVALID",
                          "HUMAN_ACTIVE_MID_SEQUENCE", "PACING_WAIT",
                          "CHALLENGE_DETECTED", "SLICE_TARGET_REQUIRED",
                          "SLICE_TARGET_AMBIGUOUS", "SLICE_TARGET_NOT_FOUND",
                          "VISION_ENDPOINT_INSECURE", "HINTS_TOO_LONG",
                          "QUESTION_TOO_LONG"):
            payload = receipt(str(action), args.get("window_id"),
                              args.get("element_ref"), "NOT_APPLIED",
                              cause=error)
            return {"content": [{"type": "text",
                                 "text": json.dumps(payload)}],
                    "isError": True}
        if error.code in ("DISPATCH_TIMEOUT", "DISPATCH_UNAVAILABLE",
                          "VISION_UNAVAILABLE", "EFFECT_UNKNOWN"):
            payload = receipt(str(action), args.get("window_id"),
                              args.get("element_ref"), "EFFECT_UNKNOWN",
                              cause=error)
            if str(action) == "slice_paste":
                # Paste truthfulness: after a paste dispatch attempt the
                # clipboard state is unconfirmable (text may be sitting in
                # the clipboard, or the restore may not have run).
                payload["clipboard_state"] = "unknown"
            return {"content": [{"type": "text",
                                 "text": json.dumps(payload)}],
                    "isError": True}
        # CLI_ERROR and anything else: bounded refusal, no replay.
        payload = receipt(str(action), args.get("window_id"),
                          args.get("element_ref"), "NOT_APPLIED",
                          cause=error)
        return {"content": [{"type": "text", "text": json.dumps(payload)}],
                "isError": True}


def _error_result(code, detail):
    return {"content": [{"type": "text",
                         "text": json.dumps({"status": "REFUSED",
                                             "cause": "%s: %s" % (code, detail)})}],
            "isError": True}


# ── SEE handlers ─────────────────────────────────────────────────────────────

def _op_apps(ctx, args):
    apps = ctx.adapter.list_apps()
    visible = []
    for app in apps:
        if ctx.deny.matches(app.get("name"), app.get("bundle_id"), None):
            continue  # denied apps are omitted entirely
        windows = []
        try:
            windows = ctx.adapter.list_windows(app["name"] or "")
        except OpError:
            windows = []
        app = dict(app)
        app["windows"] = windows
        visible.append(app)
    return _text_result({"op": "apps", "status": "OK", "apps": visible})


def _op_windows(ctx, args):
    app = args.get("app")
    if not app or not isinstance(app, str):
        raise OpError("APP_REQUIRED", "app name required for the windows op")
    # Deny the REQUESTED string against both app names and bundle ids (a
    # bundle-id string for a denied app must refuse, not fuzz its way in).
    _deny_gate(ctx, app, app, None)
    windows = ctx.adapter.list_windows(app)
    # Deny-check every RESOLVED app identity present in the result before
    # anything is returned; any match denies the whole op (zero results).
    for window in windows:
        if not isinstance(window, dict):
            continue
        matched = ctx.deny.matches(window.get("app"), window.get("bundle_id"),
                                   None)
        if matched:
            raise OpError("DENY_LISTED",
                          "resolved window entry matched by %s" % matched)
    # Drop entries whose resolved app name is not exactly (case-insensitive)
    # the requested app — a fuzzy `window list --app` must not leak foreign
    # windows.
    filtered = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        entry_name = window.get("app") or window.get("app_name")
        if isinstance(entry_name, str) and entry_name and \
                entry_name.lower() != app.lower():
            continue
        filtered.append(window)
    return _text_result({"op": "windows", "status": "OK", "app": app,
                         "windows": filtered})


def _op_inspect(ctx, args):
    window_id = _require_window_id(args)
    meta = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, meta)
    return _text_result({"op": "inspect", "status": "OK",
                         "window_id": window_id,
                         "tree": render_tree(meta)})


def _op_capture(ctx, args):
    window_id = _require_window_id(args)
    ocr = bool(args.get("ocr"))
    keep_path = args.get("keep_path")
    if keep_path is not None:
        validate_keep_path(keep_path)  # refuse BEFORE capturing
    # Identity BEFORE capture: resolve the window's owning app with the
    # screenshot-less observe and deny-gate it BEFORE the pixel capture is
    # dispatched. A denied window is never captured, not even into staging.
    observe_meta = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, observe_meta)
    staging = None
    try:
        png, meta, staging = ctx.adapter.capture_window(window_id, ocr=ocr)
        # Deny check on the freshly captured window's identity, before the
        # bytes leave the process.
        _deny_gate_window(ctx, meta)
        import base64
        content = [{"type": "text",
                    "text": json.dumps({
                        "op": "capture", "status": "OK",
                        "window_id": window_id,
                        "bytes": len(png),
                        "ocr_text": extract_ocr(meta) if ocr else None})}]
        content.append({"type": "image",
                        "data": base64.b64encode(png).decode("ascii"),
                        "mimeType": "image/png"})
        if keep_path:
            with open(keep_path, "wb") as handle:
                handle.write(png)
            try:
                os.chmod(keep_path, 0o600)
            except OSError:
                pass
        return {"content": content, "isError": False}
    finally:
        if staging:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)


# ── ACT handlers ─────────────────────────────────────────────────────────────

def _op_press(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    if not element_ref or not isinstance(element_ref, str):
        raise OpError("ELEMENT_REF_REQUIRED",
                      "element_ref from inspect is required")
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    element = resolve_element(snap, element_ref)
    element_id = element_id_of(element)
    if not element_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    meta, foreground = _dispatch_act(ctx, args, [
        "action", "AXPress", "--on", element_id,
        "--snapshot", snapshot_id, "--json"])
    return _text_result(_act_receipt(ctx, args, window_id, "press",
                                     element_ref, meta, snapshot_id,
                                     element, foreground))


def _op_set_text(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    text = args.get("text")
    if not element_ref or not isinstance(element_ref, str):
        raise OpError("ELEMENT_REF_REQUIRED",
                      "element_ref from inspect is required")
    if not isinstance(text, str):
        raise OpError("TEXT_REQUIRED", "text must be a string")
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    element = resolve_element(snap, element_ref)
    element_id = element_id_of(element)
    if not element_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    meta, foreground = _dispatch_act(ctx, args, [
        "set-value", "--value", text, "--on", element_id,
        "--snapshot", snapshot_id, "--json"])
    return _text_result(_act_receipt(ctx, args, window_id, "set_text",
                                     element_ref, meta, snapshot_id,
                                     element, foreground))


def _op_keys(ctx, args):
    window_id = _require_window_id(args)
    chord = args.get("chord")
    if not chord or not isinstance(chord, str):
        raise OpError("CHORD_INVALID", "chord missing")
    if re.search(r"\s", chord):
        raise OpError("CHORD_INVALID",
                      "exactly one chord per call; no sequences")
    if chord.lower() in GLOBAL_CHORDS:
        raise OpError("CHORD_GLOBAL",
                      "system-global chord refused; window-targeted keys only")
    # Keys allowlist (security-fix pass): after the GLOBAL_CHORDS refusal,
    # only plain navigation/editing keys and shift+arrow are deliverable.
    # Modifier chords (cmd/ctrl/option — save, quit, screenshot, app
    # switcher, force quit, ...) are refused with CHORD_NOT_ALLOWED.
    lowered = chord.lower()
    if lowered not in CHORD_ALLOWLIST and lowered not in SHIFT_ARROW_CHORDS:
        raise OpError(
            "CHORD_NOT_ALLOWED",
            "chord %r not allowed; single keys from %s or shift+ one of "
            "left/right/up/down only" % (
                chord, "{" + ", ".join(sorted(CHORD_ALLOWLIST)) + "}"))
    # press takes no element; the fresh exact-window snapshot is the receipt
    # that authorizes background key delivery.
    _snap, snapshot_id = _act_observe(ctx, args, window_id)
    meta, foreground = _dispatch_act(ctx, args, [
        "press", chord, "--snapshot", snapshot_id, "--json"])
    return _text_result(_act_receipt(ctx, args, window_id, "keys", None, meta,
                                     snapshot_id, None, foreground))


SCROLLABLE_ROLE_HINTS = ("scrollarea", "scrollview", "scrollbar", "webarea",
                         "list", "outline", "table", "textview")


def _scroll_target(snap, element_ref):
    """Element to scroll on, from the fresh snapshot.

    An explicit element_ref must resolve. Otherwise the first scrollable-role
    element is used; if none exists the dispatch still carries the snapshot
    without --on (peekaboo scroll accepts a snapshot-only target).
    """
    if element_ref is not None:
        if not isinstance(element_ref, str) or not element_ref:
            raise OpError("ELEMENT_REF_INVALID", repr(element_ref))
        element = resolve_element(snap, element_ref)
        element_id = element_id_of(element)
        if not element_id:
            raise OpError("ELEMENT_NOT_FOUND",
                          "resolved element has no id in the fresh snapshot")
        return element, element_id
    for element in snapshot_elements(snap):
        if not isinstance(element, dict):
            continue
        role = str(element.get("role", "")).lower()
        if any(hint in role for hint in SCROLLABLE_ROLE_HINTS):
            element_id = element_id_of(element)
            if element_id:
                return element, element_id
    return None, None


def _op_scroll(ctx, args):
    window_id = _require_window_id(args)
    direction = args.get("direction")
    amount = args.get("amount", 3)
    if direction not in ("up", "down", "left", "right"):
        raise OpError("DIRECTION_INVALID", repr(direction))
    if not isinstance(amount, int) or isinstance(amount, bool) \
            or not 1 <= amount <= 50:
        raise OpError("AMOUNT_INVALID", repr(amount))
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    element, element_id = _scroll_target(snap, args.get("element_ref"))
    argv = ["scroll", "--direction", direction, "--amount", str(amount),
            "--snapshot", snapshot_id]
    if element_id:
        argv += ["--on", element_id]
    argv.append("--json")
    meta, foreground = _dispatch_act(ctx, args, argv)
    return _text_result(_act_receipt(ctx, args, window_id, "scroll",
                                     args.get("element_ref"), meta,
                                     snapshot_id, element, foreground))


def _op_pointer_click(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    x, y = args.get("x"), args.get("y")
    has_coords = isinstance(x, int) and isinstance(y, int) and \
        not isinstance(x, bool) and not isinstance(y, bool)
    if element_ref is not None:
        if not isinstance(element_ref, str) or not element_ref:
            raise OpError("ELEMENT_REF_INVALID", repr(element_ref))
        snap, snapshot_id = _act_observe(ctx, args, window_id)
        element = resolve_element(snap, element_ref)
        element_id = element_id_of(element)
        if not element_id:
            raise OpError("ELEMENT_NOT_FOUND",
                          "resolved element has no id in the fresh snapshot")
        meta, foreground = _dispatch_act(ctx, args, [
            "click", "--snapshot", snapshot_id, "--on", element_id,
            "--json"])
        return _text_result(_act_receipt(ctx, args, window_id,
                                         "pointer_click", element_ref, meta,
                                         snapshot_id, element, foreground))
    if not has_coords:
        raise OpError("COORDS_REQUIRED",
                      "element_ref, or integer x,y required")
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    bounds = window_bounds(snap)
    if not bounds:
        raise OpError("WINDOW_BOUNDS_UNKNOWN",
                      "window size not resolvable; coordinate click refused")
    width, height = bounds
    if not (0 <= x < width and 0 <= y < height):
        raise OpError("POINT_OUTSIDE_WINDOW",
                      "(%d,%d) outside %dx%d" % (x, y, width, height))
    # Last resort. --window-id is kept ONLY here: peekaboo documents click
    # `--at` as global unless a window target is given (its own example is
    # `click --window-id N --at x,y --snapshot S`), so dropping it would click
    # at absolute screen coordinates. Background delivery, no --foreground.
    meta, foreground = _dispatch_act(ctx, args, [
        "click", "--window-id", str(window_id), "--at", "%d,%d" % (x, y),
        "--snapshot", snapshot_id, "--json"])
    return _text_result(_act_receipt(ctx, args, window_id, "pointer_click",
                                     None, meta, snapshot_id, None,
                                     foreground))


# ── SLICE ops ────────────────────────────────────────────────────────────────
#
# One named window driven end-to-end per tools/call, each returning a
# receipt {target, status APPLIED|NOT_APPLIED|EFFECT_UNKNOWN, cause?,
# observed}. Slice ops are foreground-class by design (AXRaise/AXPress-class/
# paste need the window exposed); that is lawful ONLY under the passed deny +
# lease + presence gates, so the single dispatch carries --foreground
# directly and is never attempted in the background first and never retried.


def _challenge_scan(ctx, snap, args, op):
    """Pre-dispatch challenge scan for every input-delivering slice act
    (slice_click / slice_paste / slice_send).

    Scans the fresh snapshot's window text (AX + OCR if present) for
    challenge patterns; a match raises the terminal CHALLENGE_DETECTED
    refusal BEFORE any dispatch (zero peekaboo act calls). The receipt's op
    field names the refused op. slice_front (raise only, no input delivered)
    keeps no scan."""
    corpus = slice_window_text(snap)
    extra_patterns = ctx.runtime.get("challenge_patterns_extra") \
        if isinstance(ctx.runtime, dict) else ()
    hit = scan_challenge_text(corpus, extra_patterns or ())
    if hit:
        raise OpError("CHALLENGE_DETECTED",
                      "pattern %r matched window text; quote: %s"
                      % (hit["pattern"], hit["quote"]))


def _slice_sequence_gate(ctx, completed, step):
    """Presence check before ONE named step of a slice sequence.

    Before the first step a plain HUMAN_ACTIVE refusal is returned. Once any
    step has completed, a newly active human aborts with
    HUMAN_ACTIVE_MID_SEQUENCE and the cause names exactly which steps
    completed (truthful partial-state reporting). Nothing continues, nothing
    retries.
    """
    state = ctx.presence.gate_ok()
    if not state["human_active"]:
        return state
    if completed:
        raise OpError("HUMAN_ACTIVE_MID_SEQUENCE",
                      "human became active before step %r; completed steps: %s"
                      % (step, ", ".join(completed) or "none"))
    raise OpError("HUMAN_ACTIVE",
                  "human idle %.1fs < %.1fs threshold; %s refused"
                  % (state["human_idle_seconds"], ctx.presence.min_idle, step))


def _slice_observe(ctx, args, window_id, completed):
    """Slice observe step: lease renew + presence + ONE fresh snapshot +
    deny list on the window identity. Appends the completed step."""
    ctx.lease.require_and_renew(args.get("owner"))
    _slice_sequence_gate(ctx, completed, "observe")
    snap = ctx.adapter.snapshot_window(window_id)
    _deny_gate_window(ctx, snap)
    snapshot_id = snapshot_id_of(snap)
    if not snapshot_id:
        raise OpError("SNAPSHOT_UNAVAILABLE",
                      "peekaboo see returned no snapshot_id; slice op refused")
    completed.append("observe:snapshot %s" % snapshot_id)
    return snap, snapshot_id


def _slice_act(ctx, args, argv, completed, label):
    """Slice act step: lease renew + presence re-check, then ONE dispatch
    with --foreground appended. No background attempt first, no retry."""
    ctx.lease.require_and_renew(args.get("owner"))
    _slice_sequence_gate(ctx, completed, "act")
    meta = ctx.adapter.act(list(argv) + ["--foreground"])
    completed.append("act:%s" % label)
    return meta


def _slice_front_select(ctx, args):
    """Resolve the slice_front target: app name + exactly one of window_id
    or a case-insensitive window title substring. Deny list applies to the
    app before any window content is read."""
    app = args.get("app")
    if not app or not isinstance(app, str):
        raise OpError("APP_REQUIRED", "app name required for slice_front")
    # Deny the requested string against app names AND bundle ids.
    _deny_gate(ctx, app, app, None)
    window_id = args.get("window_id")
    title = args.get("title")
    has_wid = isinstance(window_id, int) and not isinstance(window_id, bool)
    has_title = isinstance(title, str) and bool(title.strip())
    if has_wid and has_title:
        raise OpError("SLICE_TARGET_AMBIGUOUS",
                      "give window_id OR a title substring, not both")
    if not has_wid and not has_title:
        raise OpError("SLICE_TARGET_REQUIRED",
                      "one of window_id or title (substring) is required")
    if not has_wid:
        windows = ctx.adapter.list_windows(app)
        needle = title.strip().lower()
        matches = [w for w in windows
                   if isinstance(w.get("title"), str)
                   and needle in w["title"].lower()]
        if not matches:
            raise OpError("SLICE_TARGET_NOT_FOUND",
                          "no window of %r has a title containing %r"
                          % (app, title))
        if len(matches) > 1:
            raise OpError("SLICE_TARGET_AMBIGUOUS",
                          "%d windows of %r match %r; pass window_id"
                          % (len(matches), app, title))
        window_id = matches[0].get("window_id")
        if not isinstance(window_id, int) or isinstance(window_id, bool):
            raise OpError("WINDOW_IDENTITY_UNKNOWN",
                          "window list returned no integer window_id")
    return app, window_id, (title if has_title else None)


def _op_slice_front(ctx, args):
    app, window_id, title = _slice_front_select(ctx, args)
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Target the Window-role element when the snapshot exposes one.
    elem_id = None
    for element in snapshot_elements(snap):
        if isinstance(element, dict) and \
                "window" in str(element.get("role", "")).lower():
            elem_id = element_id_of(element)
            if elem_id:
                break
    argv = ["action", "AXRaise", "--snapshot", snapshot_id, "--json"]
    if elem_id:
        argv += ["--on", elem_id]
    _slice_act(ctx, args, argv, completed,
               "AXRaise window_id=%s%s" % (
                   window_id, " elem=%s" % elem_id if elem_id else ""))
    # Confirm: observe the window's title + window_id after raising.
    _slice_sequence_gate(ctx, completed, "confirm")
    observed_title = None
    try:
        for window in ctx.adapter.list_windows(app):
            if window.get("window_id") == window_id:
                observed_title = window.get("title")
                break
        if observed_title is None:
            observed_title = "(not found in post-raise window list)"
    except OpError as error:
        observed_title = "(readback failed: %s)" % error.code
    observed = "raised window_id=%s title=%s" % (window_id, observed_title)
    target_extra = {"app": app}
    if title:
        target_extra["title_selector"] = title
    return _text_result(receipt("slice_front", window_id, None, "APPLIED",
                                observed=observed, foreground=True,
                                target_extra=target_extra))


def _op_slice_click(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    x, y = args.get("x"), args.get("y")
    has_coords = isinstance(x, int) and isinstance(y, int) and \
        not isinstance(x, bool) and not isinstance(y, bool)
    if element_ref is None and not has_coords:
        raise OpError("COORDS_REQUIRED", "element_ref, or integer x,y required")
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Challenge scan BEFORE any click dispatch (a click is an input too).
    _challenge_scan(ctx, snap, args, "slice_click")
    if element_ref is not None:
        if not isinstance(element_ref, str) or not element_ref:
            raise OpError("ELEMENT_REF_INVALID", repr(element_ref))
        element = resolve_element(snap, element_ref)
        elem_id = element_id_of(element)
        if not elem_id:
            raise OpError("ELEMENT_NOT_FOUND",
                          "resolved element has no id in the fresh snapshot")
        argv = ["click", "--on", elem_id, "--snapshot", snapshot_id, "--json"]
        label = "click elem=%s" % elem_id
        ref = element_ref
    else:
        # Last resort: window-relative coordinate click. --window-id is kept
        # ONLY here (peekaboo treats --at as global without a window target).
        bounds = window_bounds(snap)
        if not bounds:
            raise OpError("WINDOW_BOUNDS_UNKNOWN",
                          "window size not resolvable; coordinate click refused")
        width, height = bounds
        if not (0 <= x < width and 0 <= y < height):
            raise OpError("POINT_OUTSIDE_WINDOW",
                          "(%d,%d) outside %dx%d" % (x, y, width, height))
        argv = ["click", "--window-id", str(window_id),
                "--at", "%d,%d" % (x, y), "--snapshot", snapshot_id, "--json"]
        label = "click at=(%d,%d)" % (x, y)
        ref = None
    _slice_act(ctx, args, argv, completed, label)
    return _text_result(receipt("slice_click", window_id, ref, "APPLIED",
                                observed=label, foreground=True))


def _paste_argv(ctx, text, app_name, window_id):
    """paste dispatch: --text + --app/--window-id targeting, no
    --input-strategy (the adapter's paste() path omits it). Optional
    --focus-timeout/--restore-delay come from runtime.json only."""
    argv = ["paste", "--text", text, "--app", app_name,
            "--window-id", str(window_id), "--json"]
    runtime = ctx.runtime if isinstance(ctx.runtime, dict) else {}
    focus_ms = runtime.get("paste_focus_timeout_ms")
    if isinstance(focus_ms, int) and not isinstance(focus_ms, bool) \
            and focus_ms >= 0:
        argv += ["--focus-timeout", str(focus_ms)]
    restore_ms = runtime.get("paste_restore_delay_ms")
    if isinstance(restore_ms, int) and not isinstance(restore_ms, bool) \
            and restore_ms >= 0:
        argv += ["--restore-delay", str(restore_ms)]
    return argv


def _op_slice_paste(ctx, args):
    window_id = _require_window_id(args)
    text = args.get("text")
    if not isinstance(text, str) or not text:
        raise OpError("TEXT_REQUIRED", "a non-empty text string is required")
    element_ref = args.get("element_ref")
    if element_ref is not None and (not isinstance(element_ref, str)
                                    or not element_ref):
        raise OpError("ELEMENT_REF_INVALID", repr(element_ref))
    ctx.pacer.check(window_id)  # PACING_WAIT between paste/send sequences
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Challenge scan BEFORE any dispatch (the focus click is an input too).
    _challenge_scan(ctx, snap, args, "slice_paste")
    app_name = window_identity(snap)["app_name"]
    if not app_name:
        raise OpError("WINDOW_IDENTITY_UNKNOWN",
                      "owning application not resolvable; paste refused")
    # Optional focus step: paste delivers to the FOCUSED field of the
    # window, so a named field is focused with one element click first.
    if element_ref is not None:
        element = resolve_element(snap, element_ref)
        elem_id = element_id_of(element)
        if not elem_id:
            raise OpError("ELEMENT_NOT_FOUND",
                          "resolved element has no id in the fresh snapshot")
        _slice_act(ctx, args,
                   ["click", "--on", elem_id, "--snapshot", snapshot_id,
                    "--json"], completed, "focus_click:%s" % elem_id)
    # The paste chord is the ONLY key event in the slice; never character
    # keystrokes. Pacing is counted from the dispatch attempt onward.
    ctx.lease.require_and_renew(args.get("owner"))
    _slice_sequence_gate(ctx, completed, "act")
    try:
        paste_meta = ctx.adapter.paste(
            _paste_argv(ctx, text, app_name, window_id))
    except OpError as error:
        # Failure truthfulness (security-fix pass): once the paste dispatch
        # has been ATTEMPTED, only the clean pre-dispatch refusal codes are
        # provably "nothing happened". Any other dispatch-phase failure
        # (CLI_ERROR, FOREGROUND_REQUIRED, ...) may have set the clipboard
        # and/or delivered the paste chord — report EFFECT_UNKNOWN, never
        # NOT_APPLIED. DISPATCH_TIMEOUT / DISPATCH_UNAVAILABLE already map
        # to EFFECT_UNKNOWN in the handler and pass through unchanged.
        if error.code in ("DISPATCH_TIMEOUT", "DISPATCH_UNAVAILABLE"):
            raise
        if error.code not in PASTE_CLEAN_PRE_DISPATCH_CODES:
            raise OpError("EFFECT_UNKNOWN",
                          "paste dispatch failed in flight; effect unknown "
                          "(%s: %s)" % (error.code, error.detail))
        raise
    finally:
        ctx.pacer.record(window_id)
    completed.append("act:paste window_id=%s" % window_id)
    restored_raw = _deep_find(paste_meta, ["clipboard_restored", "restored",
                                           "previous_clipboard_restored"])
    restored = bool(restored_raw)
    restore_reported = restored_raw is not None
    # Confirm: fresh see, read the target field's AX value back.
    _slice_sequence_gate(ctx, completed, "confirm")
    paste_confirmed = False
    note = ""
    try:
        fresh = ctx.adapter.snapshot_window(window_id)
        _deny_gate_window(ctx, fresh)
        if element_ref is not None:
            element = resolve_element(fresh, element_ref)
            value = element.get("value")
            paste_confirmed = isinstance(value, str) and text in value
        else:
            paste_confirmed = any(
                isinstance(e.get("value"), str) and text in e["value"]
                for e in snapshot_elements(fresh) if isinstance(e, dict))
    except OpError as error:
        paste_confirmed = False
        note = " (confirm read failed: %s)" % error.code
    observed = ("paste dispatched; field AX value read back; "
                "paste_confirmed=%s restored=%s%s") % (
        paste_confirmed, restored, note)
    if not restore_reported:
        observed += " (restore not reported by peekaboo)"
    extra = {"paste_confirmed": bool(paste_confirmed), "restored": restored}
    if not restore_reported:
        extra["restore_reported"] = False
    return _text_result(receipt("slice_paste", window_id, element_ref,
                                "APPLIED", observed=observed, foreground=True,
                                target_extra={"app": app_name}, extra=extra))


def _op_slice_send(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    if not element_ref or not isinstance(element_ref, str):
        raise OpError("ELEMENT_REF_REQUIRED",
                      "the send control's element_ref is required")
    ctx.pacer.check(window_id)  # PACING_WAIT between paste/send sequences
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Challenge check BEFORE any send dispatch, on the window's AX text (and
    # OCR text if present in the snapshot). A match STOPS the layer:
    # terminal NOT_APPLIED, bounded quote, no retry.
    _challenge_scan(ctx, snap, args, "slice_send")
    element = resolve_element(snap, element_ref)
    elem_id = element_id_of(element)
    if not elem_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    ctx.lease.require_and_renew(args.get("owner"))
    _slice_sequence_gate(ctx, completed, "act")
    try:
        ctx.adapter.act(["click", "--on", elem_id, "--snapshot",
                         snapshot_id, "--json"] + ["--foreground"])
    finally:
        ctx.pacer.record(window_id)
    completed.append("act:send_click:%s" % elem_id)
    return _text_result(receipt("slice_send", window_id, element_ref,
                                "APPLIED",
                                observed="send control %s clicked" % elem_id,
                                foreground=True))


def _op_slice_look(ctx, args):
    window_id = _require_window_id(args)
    question = args.get("question")
    tree_meta = _act_gate(ctx, args, window_id)  # deny, lease, presence gate
    tree_text = render_tree(tree_meta)
    staging = None
    try:
        png, meta, staging = ctx.adapter.capture_window(window_id, ocr=False)
        _deny_gate_window(ctx, meta)
        payload = {"op": "slice_look", "status": "OK", "window_id": window_id,
                   "bytes": len(png), "tree": tree_text}
        # Vision relay only when a vision model is actually configured;
        # accessibility text alone is acceptable otherwise.
        if isinstance(question, str) and question and ctx.vision.configured():
            try:
                answer = ctx.vision.ask(png, question, [tree_text[:600]])
                payload["answer"] = answer["answer"]
                payload["elements"] = answer["elements"]
                payload["model"] = answer["model"]
            except OpError as error:
                if error.code not in ("VISION_UNCONFIGURED",
                                      "VISION_UNAVAILABLE"):
                    raise
                payload["vision_note"] = "%s: accessibility text only" \
                    % error.code
        import base64
        content = [{"type": "text", "text": json.dumps(payload)}]
        content.append({"type": "image",
                        "data": base64.b64encode(png).decode("ascii"),
                        "mimeType": "image/png"})
        return {"content": content, "isError": False}
    finally:
        if staging:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)


# ── VISION handler ───────────────────────────────────────────────────────────

def _op_vision_ask(ctx, args):
    window_id = _require_window_id(args)
    question = args.get("question")
    hints = args.get("element_hints")
    # Prompt caps BEFORE any gate, capture or network dispatch.
    if isinstance(question, str) and \
            len(question) > VISION_QUESTION_MAX_CHARS:
        raise OpError("QUESTION_TOO_LONG",
                      "question exceeds %d chars" % VISION_QUESTION_MAX_CHARS)
    _validate_vision_hints(hints)
    tree_meta = _act_gate(ctx, args, window_id)  # deny, lease, presence gate
    hints = list(hints or [])
    tree_text = render_tree(tree_meta, max_lines=60)
    if tree_text and tree_text != "(accessibility tree unavailable for this window)":
        hints.append(tree_text)
    staging = None
    try:
        png, meta, staging = ctx.adapter.capture_window(window_id, ocr=False)
        _deny_gate_window(ctx, meta)
        answer = ctx.vision.ask(png, question, hints)
    finally:
        if staging:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
    return _text_result({"op": "vision_ask", "status": "OK",
                         "window_id": window_id, "answer": answer["answer"],
                         "elements": answer["elements"],
                         "model": answer["model"]})


# ── LEASE / PRESENCE handlers ────────────────────────────────────────────────

def _op_lease_acquire(ctx, args):
    result = ctx.lease.acquire(args.get("owner"),
                               args.get("ttl_seconds", DEFAULT_LEASE_TTL))
    return _text_result({"op": "lease_acquire", "status": "OK", **result})


def _op_lease_release(ctx, args):
    result = ctx.lease.release(args.get("owner"))
    return _text_result({"op": "lease_release", "status": "OK", **result})


def _op_lease_status(ctx, args):
    return _text_result({"op": "lease_status", "status": "OK",
                         **ctx.lease.status()})


def _op_presence(ctx, args):
    state = ctx.presence.observe()
    return _text_result({"op": "presence", "status": "OK",
                         "min_idle_seconds": ctx.presence.min_idle,
                         **state})


_HANDLERS = {
    "apps": _op_apps,
    "windows": _op_windows,
    "inspect": _op_inspect,
    "capture": _op_capture,
    "press": _op_press,
    "set_text": _op_set_text,
    "keys": _op_keys,
    "scroll": _op_scroll,
    "pointer_click": _op_pointer_click,
    "slice_front": _op_slice_front,
    "slice_click": _op_slice_click,
    "slice_paste": _op_slice_paste,
    "slice_send": _op_slice_send,
    "slice_look": _op_slice_look,
    "vision_ask": _op_vision_ask,
    "lease_acquire": _op_lease_acquire,
    "lease_release": _op_lease_release,
    "lease_status": _op_lease_status,
    "presence": _op_presence,
}


def _text_result(payload, is_error=False):
    return {"content": [{"type": "text", "text": json.dumps(payload)}],
            "isError": is_error}


# ── MCP stdio server ─────────────────────────────────────────────────────────

def build_context():
    runtime = load_runtime(resolve_runtime_path())
    deny_path = os.environ.get("MMOS_CU_DENY") or os.path.join(HERE, "deny.json")
    deny = DenyList.load(deny_path)
    lease = Lease()
    presence = Presence(runtime=runtime)
    pacer = Pacer(runtime=runtime)
    adapter = PeekabooAdapter(runtime)
    vision = VisionClient()
    return ToolContext(runtime, deny, lease, presence, adapter, vision, pacer)


def serve(stdin=None, stdout=None):
    """MCP loop. Readable/writable streams are injectable for tests."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    try:
        ctx = build_context()
    except RefuseError as error:
        sys.stderr.write("%s: startup refused: %s\n" % (SERVER_NAME, error))
        return 1

    sys.stderr.write("%s: ready (%s, pin %s)\n" % (
        SERVER_NAME, ctx.runtime["peekaboo_bin"],
        ctx.runtime["peekaboo_sha256"][:12]))

    def send(object_):
        stdout.write(json.dumps({**object_, "jsonrpc": "2.0"}) + "\n")
        stdout.flush()

    def handle(message):
        if not isinstance(message, dict):
            send({"id": None, "error": {"code": -32600,
                                        "message": "Invalid Request"}})
            return
        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        if not isinstance(method, str):
            send({"id": msg_id if msg_id is not None else None,
                  "error": {"code": -32600, "message": "Invalid Request"}})
            return
        if msg_id is None:
            return  # notification: no response
        if method == "initialize":
            requested = params.get("protocolVersion")
            send({"id": msg_id, "result": {
                "protocolVersion": requested if isinstance(requested, str)
                else PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME,
                               "version": SERVER_VERSION}}})
            return
        if method == "ping":
            send({"id": msg_id, "result": {}})
            return
        if method == "tools/list":
            send({"id": msg_id, "result": {"tools": [{
                "name": TOOL_NAME, "description": TOOL_DESCRIPTION,
                "inputSchema": TOOL_SCHEMA}]}})
            return
        if method == "tools/call":
            name = params.get("name")
            if name != TOOL_NAME:
                send({"id": msg_id, "result": {
                    "content": [{"type": "text",
                                 "text": "Unknown tool: %s" % str(name)}],
                    "isError": True}})
                return
            try:
                result = handle_tool_call(ctx, params.get("arguments") or {})
            except Exception as error:  # never leak internals without a cause
                result = _error_result("INTERNAL", _bounded(str(error), 160))
            send({"id": msg_id, "result": result})
            return
        if method in ("resources/list", "prompts/list"):
            send({"id": msg_id, "result": {method.split("/")[0]: []}})
            return
        send({"id": msg_id, "error": {"code": -32601,
                                      "message": "Method not found: %s" % method}})

    buffer = ""
    stream = stdin
    read_line = getattr(stream, "readline", None)
    if read_line is not None:
        while True:
            line = read_line()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                send({"id": None, "error": {"code": -32700,
                                            "message": "Parse error"}})
                continue
            handle(message)
    return 0


def main():
    return serve()


if __name__ == "__main__":
    sys.exit(main())
