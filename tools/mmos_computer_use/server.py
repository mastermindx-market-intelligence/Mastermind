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
  * A foreground-required refusal from peekaboo is returned as
    FOREGROUND_REQUIRED. It is NEVER escalated automatically and NEVER retried.
    Whether it is NOT_APPLIED or EFFECT_UNKNOWN is decided ONLY by peekaboo's
    structured result (mutation_dispatched / effect): a text-only mention of
    "foreground" never turns a possible dispatch into NOT_APPLIED (R-M1).
  * SLICE ops (slice_front/click/paste/send/look) drive ONE named window
    end-to-end (observe -> act -> confirm). They are foreground-class by
    design (AXRaise/AXPress-class/paste need the window exposed), which is
    lawful ONLY under the passed deny + lease + presence gates: the single
    dispatch carries --foreground directly, is never attempted in the
    background first, and is never retried.
  * Slice presence: the human-idle threshold default is 180 s for ALL acts
    (MMOS_CU_PRESENCE_MIN_IDLE env / runtime.json presence_min_idle_seconds).
    Outside the test harness 180 s is the FLOOR: no configuration source may
    lower it (the restrained session cannot loosen its own limits).
    Presence is re-checked before EVERY step and between steps of a slice
    sequence; a human becoming active mid-sequence aborts with NOT_APPLIED /
    HUMAN_ACTIVE_MID_SEQUENCE naming exactly which steps completed. Partial
    state is reported truthfully; nothing continues, nothing retries.
  * Slice pacing: per target (keyed by owning pid + exact window id, never by
    app name or window title — a title change must not reset the interval), a
    minimum interval (default and production floor 180 s;
    MMOS_CU_PACING_SECONDS env / runtime.json pacing_seconds) between two
    acts that can submit, persisted as
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
                                          no copy is kept and no image bytes
                                          ever enter a reply)
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

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

RUNTIME_SCHEMA = "mmos.computer_use.runtime/v1"
DENY_SCHEMA = "mmos.computer_use.deny/v1"
TOOL_NAME = "mmos_computer_use"
SERVER_NAME = "mmos-computer-use-mcp"
SERVER_VERSION = "0.3.0"
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
# Every op whose dispatch can change the page: once one of these has been
# handed to peekaboo, a failure is EFFECT_UNKNOWN unless the code is in the
# proven pre-dispatch set below (H1).
DISPATCH_ACT_OPS = ACT_OPS | {"slice_front", "slice_click", "slice_paste",
                              "slice_send"}
# Slice ops that pace per target window (one sequence per interval).
PACED_SLICE_OPS = {"slice_paste", "slice_send"}
# Failures that are PROVABLY pre-dispatch (nothing was sent, clipboard
# untouched) for EVERY act op, not just paste, and may be reported
# NOT_APPLIED. Every code here is raised by THIS layer's own gates BEFORE a
# dispatch, or typed from a structured peekaboo refusal that proves nothing
# ran. FOREGROUND_REQUIRED is deliberately NOT here (R-M1): it is classified
# from the error TEXT, so it only earns NOT_APPLIED when the structured
# result proves nothing was dispatched — that path arrives with
# dispatched=False and is handled by the receipt's typed list below.
ACT_CLEAN_PRE_DISPATCH_CODES = {
    "WINDOW_IDENTITY_UNKNOWN", "DENY_LISTED", "LEASE_NOT_HELD",
    "LEASE_NOT_OWNER", "LEASE_OWNER_REQUIRED", "LEASE_NONCE_INVALID",
    "PRESENCE_UNKNOWN", "HUMAN_ACTIVE",
    "HUMAN_ACTIVE_MID_SEQUENCE", "PACING_WAIT", "CHALLENGE_DETECTED",
    "ELEMENT_NOT_FOUND", "ELEMENT_REF_INVALID", "TEXT_REQUIRED",
    "WINDOW_ID_REQUIRED", "SNAPSHOT_UNAVAILABLE",
    "COORDS_REQUIRED", "WINDOW_BOUNDS_UNKNOWN", "POINT_OUTSIDE_WINDOW",
    "SLICE_TARGET_REQUIRED", "SLICE_TARGET_AMBIGUOUS",
    "SLICE_TARGET_NOT_FOUND", "WINDOW_APP_MISMATCH",
    "DENY_OVERLAY", "DENY_OVERLAY_UNVERIFIED", "WINDOW_NOT_FRONTMOST",
    "WINDOW_GONE", "PASTE_GATE_UNVERIFIED",
    # Proven pre-dispatch peekaboo refusals (typed from live captures —
    # see _typed_preflight_refusal): nothing was invoked, so NOT_APPLIED.
    "ELEMENT_NOT_ACTIONABLE", "SNAPSHOT_STALE",
}

MAX_TREELINES = 400
MAX_LINE_CHARS = 240
MAX_OBSERVED = 200
MAX_ERROR_TEXT = 240

DEFAULT_MIN_IDLE_SECONDS = 180.0
DEFAULT_PACING_SECONDS = 180.0
# ABSOLUTE floors: a threshold can never be zero/negative, even under the
# test harness (a broken test must not disable a gate silently).
MIN_IDLE_FLOOR_SECONDS = 1.0
PACING_FLOOR_SECONDS = 1.0
# BCU repair round 2 item 2 (ruling ESC 12), hardened by round 3 H2 (ruling
# ESC 14): the 180 s DEFAULTS are the PRODUCTION floors IN CODE. Every value
# arriving from the environment or from runtime.json is refused below them,
# UNCONDITIONALLY — there is no test-mode flag any more, because any flag a
# session can influence is a flag a session can forge (the old
# ``"pytest" in sys.modules`` check was defeatable via
# PYTHONPATH/sitecustomize). The only sub-default path left is an in-process
# constructor argument (unit-test injection), and it still never goes below
# the absolute 1 s floor. A subprocess test passes paths as launch
# ARGUMENTS, never as environment variables.
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
    "presence aborts, shared pre-act challenge + pacing gates, and a "
    "challenge stop on every input-delivering act. The keys op accepts "
    "an allowlist of navigation/editing chords only. vision_ask captures one "
    "window in memory and asks a vision model (loopback endpoint only) for a "
    "TEXT answer plus clickable elements with normalized 0-1000 "
    "coordinates; no operation ever returns image bytes. Every operation "
    "names exactly one window_id or app; "
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
        "question": {"type": "string", "description": "vision_ask question"},
        "element_hints": {"type": "array", "items": {"type": "string"}},
        "owner": {"type": "string", "description": "Lease owner id"},
        "lease_nonce": {"type": "string",
                        "description": "Random nonce returned by "
                                       "lease_acquire; REQUIRED on every act"},
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
    """Bounded, typed operation failure surfaced as a cause code.

    `dispatched` is set by the adapter to True for any failure raised AFTER
    the peekaboo subprocess was launched for an act/paste dispatch: from
    that point the event may have reached the app, so only a proven
    pre-dispatch refusal may be reported NOT_APPLIED (H1).
    """

    def __init__(self, code, detail=""):
        super().__init__(("%s: %s" % (code, detail)) if detail else code)
        self.code = code
        self.detail = detail[:MAX_ERROR_TEXT]
        self.dispatched = False
        # Optional truthful receipt fields for a proven pre-dispatch refusal
        # (e.g. the foreground-paste gate's clipboard_state). Merged into the
        # receipt by handle_tool_call; never overwrites an existing field.
        self.extra = None


# ── numeric + environment guards ─────────────────────────────────────────────

def _finite_number(value, code, detail, refuse=False):
    """float(value) requiring a finite number (M1: NaN/inf never disable a
    gate or lease bound). Raises RefuseError(code) when `refuse` (startup
    thresholds), OpError(code) otherwise (operation-time values)."""
    error_class = RefuseError if refuse else OpError
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise error_class(code, detail)
    if not math.isfinite(number):
        raise error_class(code, detail)
    return number


def _config_source_floor(value, default, code, label):
    """Refuse ANY configured threshold looser than the 180 s default.

    BCU R3 H2 (ruling ESC 14): UNCONDITIONAL — no test-mode flag exists any
    more. The R2 ``"pytest" in sys.modules`` check was forgeable (a session
    can load pytest into the server process via PYTHONPATH/sitecustomize),
    and any flag reachable from the environment is a flag a session can set.
    The floors hold IN CODE for every value arriving from the environment or
    from runtime.json. Unit tests use constructor injection (which never
    reaches this check) plus a fake clock; a subprocess test passes paths as
    launch ARGUMENTS (main() --state-dir/--runtime/--deny).
    """
    if value < default:
        raise RefuseError(
            code,
            "%s %r is looser than the %.0fs default; the default is the "
            "production floor for every environment/runtime.json value"
            % (label, value, default))


def _inside_layer(path):
    real = os.path.realpath(path)
    layer = os.path.realpath(HERE)
    return real == layer or real.startswith(layer.rstrip(os.sep) + os.sep)


def _env_path_override(env_name, value):
    """Validate an MMOS_CU_* path override: it may only point INSIDE the
    layer's own folder (tools/mmos_computer_use/ or a subdir); anything
    outside refuses at startup (M2).

    BCU R3 H2: UNCONDITIONAL — the former MMOS_CU_TEST_MODE escape is gone
    (a session-settable flag can never loosen a rule). A harness subprocess
    that needs scratch paths passes them as launch ARGUMENTS instead
    (main() --state-dir/--runtime/--deny)."""
    if not _inside_layer(value):
        raise RefuseError(
            "ENV_PATH_OUTSIDE_LAYER",
            "%s must point inside %s" % (env_name, os.path.realpath(HERE)))
    return value


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
                or not math.isfinite(value) or value < minimum:
            raise RefuseError("RUNTIME_%s" % key.upper(), repr(value))
        return value

    # BCU R3 H2: runtime.json is a file source — its thresholds carry the
    # UNCONDITIONAL 180 s production floor already at load time (the
    # Presence/Pacer runtime-dict paths re-check it independently).
    presence_min_idle = _number("presence_min_idle_seconds",
                                DEFAULT_MIN_IDLE_SECONDS)
    pacing = _number("pacing_seconds", DEFAULT_PACING_SECONDS)
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
        return _env_path_override("MMOS_CU_RUNTIME", override)
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
        # M6: further password managers and the system credential prompts.
        "KeePassXC", "LastPass", "SecurityAgent", "System Preferences",
        # Terminal emulators and the script editor: a shell or script window
        # is an arbitrary-command surface, not a document window.
        "Terminal", "iTerm", "iTerm2", "Script Editor",
    ],
    "bundle_ids": [
        "com.apple.KeychainAccess", "com.apple.Passwords",
        "com.apple.systempreferences", "com.apple.SystemPreferences",
        "com.1password.1password", "com.agilebits.onepassword7",
        "com.bitwarden.desktop",
        "org.keepassxc.keepassxc", "com.lastpass.LastPass",
        "com.apple.SecurityAgent", "me.proton.pass",
        "com.km.keeperdesktop", "in.sinew.enpass",
        "com.strongbox.lukilabs", "com.markmcguill.strongbox",
        "com.dashlane.dashlane",
        "com.apple.Terminal", "com.apple.ScriptEditor.id",
    ],
    # Case-insensitive window-title patterns (M6): a credential entry field
    # in ANY app is refused, not only in a known password-manager process.
    "title_regexes": [
        "password", "passkey", "saved passwords", "settings/passwords",
    ],
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
                # M6 merge semantics: the file ADDS to the built-in defaults
                # (union), it never replaces them. An empty file means the
                # defaults only.
                entries[key] = entries[key] + value
        merged_names = entries["app_names"] + entries["extra_app_names"]
        merged_bundles = entries["bundle_ids"] + entries["extra_bundle_ids"]
        merged_titles = entries["title_regexes"] + entries["extra_title_regexes"]
        patterns = []
        for pattern in merged_titles:
            try:
                patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                raise RefuseError("DENY_LIST_REGEX", pattern)
        return cls({_canonical(n) for n in merged_names},
                   {_canonical(b) for b in merged_bundles}, patterns)

    def matches(self, app_name, bundle_id, window_title=None):
        if app_name and _canonical(app_name) in self.app_names:
            return "app_name"
        if bundle_id and _canonical(bundle_id) in self.bundle_ids:
            return "bundle_id"
        if window_title:
            title = unicodedata.normalize("NFC", window_title)
            for pattern in self.title_regexes:
                if pattern.search(title):
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

    BCU R3 H2: 180 s is an UNCONDITIONAL floor for every value arriving from
    the environment or runtime.json — no flag switches it off. The only
    sub-default path is an in-process constructor argument (unit-test
    injection), and it never goes below the absolute 1 s floor.
    """

    def __init__(self, min_idle_seconds=None, ioreg_bin=None, runtime=None):
        raw = os.environ.get("MMOS_CU_PRESENCE_MIN_IDLE")
        runtime_value = runtime.get("presence_min_idle_seconds") \
            if isinstance(runtime, dict) else None
        if min_idle_seconds is not None:
            # Constructor injection: the test path (H2). Not reachable from
            # a session's environment or any file; still never below the
            # absolute floor (a broken test must not disable the gate).
            self.min_idle = _finite_number(min_idle_seconds,
                                           "PRESENCE_MIN_IDLE_INVALID",
                                           repr(min_idle_seconds),
                                           refuse=True)
            if self.min_idle < MIN_IDLE_FLOOR_SECONDS:
                raise RefuseError(
                    "PRESENCE_MIN_IDLE_FLOOR",
                    "min_idle_seconds %r is below the %.0fs floor"
                    % (min_idle_seconds, MIN_IDLE_FLOOR_SECONDS))
        elif raw:
            self.min_idle = _finite_number(
                raw, "PRESENCE_MIN_IDLE_INVALID",
                "MMOS_CU_PRESENCE_MIN_IDLE %r is not a finite number" % raw,
                refuse=True)
            # UNCONDITIONAL: any env value below the 180 s default refuses
            # (this also covers the absolute floor: 1 s < 180 s).
            _config_source_floor(self.min_idle, DEFAULT_MIN_IDLE_SECONDS,
                                 "PRESENCE_MIN_IDLE_STRICTER_ONLY",
                                 "MMOS_CU_PRESENCE_MIN_IDLE %r" % raw)
        elif runtime_value is not None:
            self.min_idle = _finite_number(
                runtime_value, "PRESENCE_MIN_IDLE_INVALID",
                repr(runtime_value), refuse=True)
            # UNCONDITIONAL for runtime.json values (H2).
            _config_source_floor(self.min_idle, DEFAULT_MIN_IDLE_SECONDS,
                                 "PRESENCE_MIN_IDLE_STRICTER_ONLY",
                                 "runtime presence_min_idle_seconds %r"
                                 % (runtime_value,))
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


def _owner_digest(owner):
    """Unrecoverable digest of a lease owner id (status output only)."""
    return hashlib.sha256((owner or "").encode("utf-8")).hexdigest()[:12]


# A lease.lock older than this (or whose recorded pid is gone) is treated as
# abandoned by a crashed holder and may be recovered (M4).
STALE_LOCK_SECONDS = 60.0


def _lock_holder_alive(info):
    """True when the pid recorded in a lockfile still exists on this host."""
    pid = info.get("pid") if isinstance(info, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return True
    return True


def _lease_clocks(lease):
    """(mono_at, mono_expires_at) when usable on this boot, else (None, None).

    Persisted lease timestamps are wall-clock for cross-process/restart
    readability; the monotonic pair is preferred for the expiry gate so a
    wall-clock jump cannot extend or shorten a hold. A sample from a previous
    boot (mono in the future) is ignored.
    """
    mono_at = lease.get("mono_at")
    mono_exp = lease.get("mono_expires_at")
    if isinstance(mono_at, (int, float)) and isinstance(mono_exp, (int, float)) \
            and math.isfinite(mono_at) and math.isfinite(mono_exp):
        if 0.0 <= mono_at <= time.monotonic() + 1.0:
            return mono_at, mono_exp
    return None, None


def _lease_active(lease, now_wall, now_mono):
    """True while the persisted lease is unexpired (monotonic preferred)."""
    _, mono_exp = _lease_clocks(lease)
    if mono_exp is not None:
        return mono_exp > now_mono
    expires = lease.get("expires_at")
    if not isinstance(expires, (int, float)):
        return False
    return expires > now_wall


def _lease_remaining(lease, now_wall, now_mono):
    mono_at, mono_exp = _lease_clocks(lease)
    if mono_exp is not None:
        return max(0.0, mono_exp - now_mono)
    expires = lease.get("expires_at")
    if isinstance(expires, (int, float)):
        return max(0.0, expires - now_wall)
    return None


class Lease:
    """Single-holder advisory lease persisted as JSON next to a lock file.

    Acquire is atomic: an O_CREAT|O_EXCL lockfile serializes contenders, then
    the holder writes lease.json. A lease whose expires_at is in the past is
    treated as abandoned by a crashed holder and may be taken over. Every ACT
    re-checks ownership AND the per-acquisition nonce, then renews the expiry
    (heartbeat): the owner string is unauthenticated (same-machine trust), so
    every act must carry the nonce handed out by lease_acquire
    (LEASE_NONCE_INVALID otherwise).
    """

    def __init__(self, state_dir=None):
        override = os.environ.get("MMOS_CU_STATE_DIR")
        if override:
            override = _env_path_override("MMOS_CU_STATE_DIR", override)
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

    def _stale_lock(self):
        """True when lease.lock is abandoned (dead pid or old age)."""
        try:
            with open(self.lock_path, "r", encoding="utf-8") as handle:
                info = json.load(handle)
        except (OSError, ValueError):
            info = None
        if isinstance(info, dict):
            created = info.get("created_at")
            if isinstance(created, (int, float)) and \
                    time.time() - created > STALE_LOCK_SECONDS:
                return True
            return not _lock_holder_alive(info)
        # Unparseable lock content: recover only by age.
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return False
        return age > STALE_LOCK_SECONDS

    def _acquire_lock(self):
        """Take lease.lock with O_CREAT|O_EXCL.

        A pre-existing lock is LEASE_CONTENDED (typed, never FileExistsError/
        INTERNAL). If it is provably stale (recorded pid gone, or older than
        STALE_LOCK_SECONDS) it is recovered once and the exclusivity retried.
        """
        os.makedirs(self.state_dir, exist_ok=True)
        for attempt in (0, 1):
            try:
                fd = os.open(self.lock_path,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if attempt == 0 and self._stale_lock():
                    try:
                        os.unlink(self.lock_path)
                    except OSError:
                        pass
                    continue
                raise OpError("LEASE_CONTENDED",
                              "lease.lock is held by another acquire")
            payload = json.dumps({"pid": os.getpid(),
                                  "created_at": time.time()})
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return
        raise OpError("LEASE_CONTENDED",
                      "lease.lock contention; single-shot acquire")

    @contextlib.contextmanager
    def _critical(self):
        """The O_EXCL critical section: read+check+write all happen inside."""
        self._acquire_lock()
        try:
            yield
        finally:
            try:
                os.unlink(self.lock_path)
            except OSError:
                pass

    def _write_locked(self, payload):
        """Write lease.json; caller MUST already hold lease.lock."""
        _atomic_write(self.lease_path, payload)

    def _verify_write(self, owner, nonce):
        """Re-read after writing: a non-cooperating writer that landed a
        different hold is detected here rather than silently accepted (M3)."""
        check = self._read()
        if not check or check.get("owner") != owner or \
                check.get("nonce") != nonce:
            raise OpError("LEASE_CONTENDED",
                          "lease.json changed under the critical section; "
                          "refused")
        return check

    def acquire(self, owner, ttl_seconds=DEFAULT_LEASE_TTL):
        if not owner or not isinstance(owner, str):
            raise OpError("LEASE_OWNER_REQUIRED", "owner id missing")
        ttl = _finite_number(ttl_seconds, "LEASE_TTL_INVALID",
                             repr(ttl_seconds))
        if ttl < 5 or ttl > 3600:
            raise OpError("LEASE_TTL_INVALID", repr(ttl_seconds))
        os.makedirs(self.state_dir, exist_ok=True)
        now = time.time()
        now_mono = time.monotonic()
        nonce = secrets.token_hex(16)
        with self._critical():
            existing = self._read()
            if existing and _lease_active(existing, now, now_mono):
                if existing.get("owner") == owner:
                    # Already held by this owner: refresh the heartbeat
                    # and return the SAME nonce (the live acquisition's).
                    nonce = existing.get("nonce") or nonce
                    self._write_locked({
                        "owner": owner,
                        "nonce": nonce,
                        "acquired_at": existing.get("acquired_at", now),
                        "expires_at": now + ttl,
                        "heartbeat_at": now,
                        "mono_at": now_mono,
                        "mono_expires_at": now_mono + ttl})
                    self._verify_write(owner, nonce)
                    return {"held": True, "owner": owner,
                            "renewed": True, "nonce": nonce,
                            "expires_at": now + ttl}
                remaining = _lease_remaining(existing, now, now_mono) or 0.0
                raise OpError("LEASE_HELD",
                              "owner=%s expires_in=%.0fs" % (
                                  _owner_digest(existing.get("owner")),
                                  remaining))
            # Expired lease: prior holder crashed or let it lapse.
            payload = {"owner": owner, "nonce": nonce, "acquired_at": now,
                       "expires_at": now + ttl, "heartbeat_at": now,
                       "mono_at": now_mono,
                       "mono_expires_at": now_mono + ttl}
            self._write_locked(payload)
            self._verify_write(owner, nonce)
        return {"held": True, "owner": owner, "took_over": bool(existing),
                "nonce": nonce, "expires_at": now + ttl}

    def release(self, owner):
        """Release takes the SAME critical section as acquire/renew."""
        with self._critical():
            lease = self._read()
            if not lease:
                return {"released": True, "note": "no lease"}
            if lease.get("owner") != owner:
                raise OpError("LEASE_NOT_OWNER",
                              "held by %s"
                              % _owner_digest(lease.get("owner")))
            try:
                os.unlink(self.lease_path)
            except OSError:
                pass
            return {"released": True}

    def status(self):
        lease = self._read()
        if not lease:
            return {"held": False}
        remaining = _lease_remaining(lease, time.time(), time.monotonic())
        if remaining is not None:
            remaining = round(remaining, 3)
        owner = lease.get("owner")
        out = {"held": bool(remaining), "expires_in_seconds": remaining}
        if isinstance(owner, str) and owner:
            # Owner id is redacted to an unrecoverable sha256 digest (M5);
            # acquire/release still require the EXACT owner string.
            out["owner"] = _owner_digest(owner)
            out["owner_redacted"] = True
        return out

    def require_and_renew(self, owner, ttl_seconds=None, nonce=None):
        """Gate for ACT ops: verifies ownership AND the acquisition nonce,
        then renews the expiry in place.

        The TTL is preserved from the acquisition unless an explicit
        ttl_seconds is given (renewal never silently resets the hold to the
        default).

        M3: read + ownership/nonce checks + write happen INSIDE the O_EXCL
        critical section, and the write is verified by re-read. A takeover
        interleaved between the read and the write is detected and refused
        (LEASE_CONTENDED) instead of being silently overwritten."""
        with self._critical():
            lease = self._read()
            now = time.time()
            now_mono = time.monotonic()
            if not lease or lease.get("owner") != owner:
                raise OpError("LEASE_NOT_HELD",
                              "acquire the lease with lease_acquire first")
            if not _lease_active(lease, now, now_mono):
                raise OpError("LEASE_NOT_HELD", "lease expired; re-acquire")
            expires = lease.get("expires_at")
            if not nonce or not isinstance(nonce, str) \
                    or lease.get("nonce") != nonce:
                raise OpError(
                    "LEASE_NONCE_INVALID",
                    "act must carry the nonce returned by lease_acquire")
            acquired_at = lease.get("acquired_at", now)
            if ttl_seconds is not None:
                ttl = _finite_number(ttl_seconds, "LEASE_TTL_INVALID",
                                     repr(ttl_seconds))
                if ttl < 5 or ttl > 3600:
                    raise OpError("LEASE_TTL_INVALID", repr(ttl_seconds))
            elif _lease_clocks(lease)[1] is not None:
                # Preserve the acquired TTL (never reset to the default),
                # measured on the monotonic pair when available.
                mono_at, mono_exp = _lease_clocks(lease)
                ttl = max(5.0, mono_exp - mono_at)
            elif isinstance(expires, (int, float)) and \
                    isinstance(acquired_at, (int, float)):
                ttl = max(5.0, expires - acquired_at)
            else:
                ttl = DEFAULT_LEASE_TTL
            self._write_locked({
                "owner": owner, "nonce": nonce, "acquired_at": acquired_at,
                "expires_at": now + ttl, "heartbeat_at": now,
                "mono_at": now_mono, "mono_expires_at": now_mono + ttl})
            self._verify_write(owner, nonce)
        return True


# ── pacing ───────────────────────────────────────────────────────────────────

def _monotonic_elapsed(entry, now_wall, now_mono):
    """Seconds elapsed since a persisted {"at", "mono"} pacing entry.

    Prefers the monotonic sample (a wall-clock jump must not shorten or
    lengthen a gate). The monotonic value is only trusted when it is
    plausible for THIS boot (0 < mono <= now); after a reboot the persisted
    sample can be larger than the fresh counter, and the wall clock is the
    safe fallback.
    """
    mono = entry.get("mono")
    if isinstance(mono, (int, float)) and math.isfinite(mono) and \
            0.0 < mono <= now_mono + 1.0:
        return now_mono - mono
    at = entry.get("at")
    if isinstance(at, (int, float)) and math.isfinite(at):
        return now_wall - at
    return None


def _canonical(text):
    """NFC-normalize, trim and casefold a string for deny/pacing matching."""
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFC", text).strip().casefold()


def pacing_key(window_id, pid=None):
    """R-M3 pacing identity: owning pid + exact window id.

    The key deliberately carries NO app name and NO window title: a title
    change (tab switch, new message, a spinner) must not reset the interval,
    or a caller could send twice inside the 3-minute rule by changing the
    page title first. The owning pid binds the id to one process, so a window
    id recycled by another app cannot inherit (or escape) a pace record.

    An unreadable window id is refused, typed — a pace record with no target
    identity would silently allow everything, which is exactly the hole this
    closes. An unresolvable pid falls back to the exact id alone.
    """
    if not isinstance(window_id, int) or isinstance(window_id, bool):
        raise OpError("WINDOW_ID_REQUIRED",
                      "pacing needs an exact integer window_id, got %r"
                      % (window_id,))
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        return "pid:%d|window:%d" % (pid, window_id)
    return "window:%d" % window_id


def target_receipt_pid(meta):
    """THE one pid resolver, used by BOTH pacing and paste targeting
    (BCU R3 H1). No subprocess reads, no app-list/window-list walk: the
    handler already holds `meta` — the payload of its own fresh snapshot.

    The pid is the one peekaboo itself bound to the window it resolved:
    the `see` envelope's target_receipt.pid first (real capture
    see_fixture_window.json: {pid, window_id} as a sibling of "data",
    preserved into the payload by run_json), falling back to
    target_application_info.pid (real `window list --pid` envelopes carry
    the pid only there — window_list_fixture.json; real window ROWS carry
    no pid at all, which is why the old row-walking resolver could never
    find one). Returns None when neither holds a positive int."""
    if not isinstance(meta, dict):
        return None
    for container in (meta.get("target_receipt"),
                      meta.get("target_application_info")):
        if isinstance(container, dict):
            pid = container.get("pid")
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                return pid
    return None


class Pacer:
    """Pacing between acts that can change a page or send, keyed by the R-M3
    identity (owning pid + exact window id), never the app name or title.

    The last dispatch time for a key is persisted in pacing.json under the
    state dir; a second act on the SAME key inside the configured interval
    is refused with PACING_WAIT (seconds remaining). The interval defaults
    to 180 s — an UNCONDITIONAL floor for every environment/runtime.json
    value (BCU R3 H2); priority: explicit constructor argument (the test
    injection path) > MMOS_CU_PACING_SECONDS env > runtime.json
    pacing_seconds > DEFAULT_PACING_SECONDS. One worker at a time is
    already guaranteed by the lease; pacing additionally spaces repeated
    acts on the same target.
    """

    def __init__(self, state_dir=None, seconds=None, runtime=None):
        override = os.environ.get("MMOS_CU_STATE_DIR")
        if override:
            override = _env_path_override("MMOS_CU_STATE_DIR", override)
        self.state_dir = state_dir or override or os.path.join(HERE, "state")
        self.path = os.path.join(self.state_dir, "pacing.json")
        raw = os.environ.get("MMOS_CU_PACING_SECONDS")
        runtime_value = runtime.get("pacing_seconds") \
            if isinstance(runtime, dict) else None
        if seconds is not None:
            # Constructor injection: the test path (H2). Not reachable from
            # a session's environment or any file; still never below the
            # absolute floor (a broken test must not disable the gate).
            self.seconds = _finite_number(seconds, "PACING_SECONDS_INVALID",
                                          repr(seconds), refuse=True)
            if self.seconds < PACING_FLOOR_SECONDS:
                raise RefuseError(
                    "PACING_SECONDS_FLOOR",
                    "pacing seconds %r is below the %.0fs floor"
                    % (seconds, PACING_FLOOR_SECONDS))
        elif raw:
            self.seconds = _finite_number(
                raw, "PACING_SECONDS_INVALID",
                "MMOS_CU_PACING_SECONDS %r is not a finite number" % raw,
                refuse=True)
            # UNCONDITIONAL: any env value below the 180 s default refuses
            # (this also covers the absolute floor: 1 s < 180 s).
            _config_source_floor(self.seconds, DEFAULT_PACING_SECONDS,
                                 "PACING_SECONDS_STRICTER_ONLY",
                                 "MMOS_CU_PACING_SECONDS %r" % raw)
        elif runtime_value is not None:
            self.seconds = _finite_number(
                runtime_value, "PACING_SECONDS_INVALID",
                repr(runtime_value), refuse=True)
            # UNCONDITIONAL for runtime.json values (H2).
            _config_source_floor(self.seconds, DEFAULT_PACING_SECONDS,
                                 "PACING_SECONDS_STRICTER_ONLY",
                                 "runtime pacing_seconds %r"
                                 % (runtime_value,))
        else:
            self.seconds = DEFAULT_PACING_SECONDS

    def _read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def check(self, key):
        """Refuse with PACING_WAIT when the last act on this key is still
        inside the interval. No write, no dispatch."""
        last = self._read().get(str(key))
        now_wall = time.time()
        now_mono = time.monotonic()
        if isinstance(last, dict):
            elapsed = _monotonic_elapsed(last, now_wall, now_mono)
        elif isinstance(last, (int, float)):
            # Legacy entry (bare wall-clock timestamp).
            elapsed = now_wall - last
        else:
            elapsed = None
        if elapsed is not None:
            remaining = self.seconds - elapsed
            if remaining > 0:
                raise OpError("PACING_WAIT",
                              "%.0fs remaining until the next act may target "
                              "%s" % (remaining, key))

    def record(self, key, window_id=None):
        """Record the dispatch attempt time for this key (atomic write).

        Raises OSError from the write; callers AFTER a dispatch must swallow
        it and report state_write:"failed" on the act receipt (M9).
        """
        data = self._read()
        entry = {"at": time.time(), "mono": time.monotonic()}
        if window_id is not None:
            entry["window_id"] = window_id
        data[str(key)] = entry
        os.makedirs(self.state_dir, exist_ok=True)
        _atomic_write(self.path, data)


# ── peekaboo adapter ─────────────────────────────────────────────────────────

def _child_env():
    """Environment for peekaboo children with ANTHROPIC_* (secrets) stripped."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith("ANTHROPIC_")}


def _bounded(text, limit=MAX_ERROR_TEXT):
    return (text or "").strip().replace("\n", " ")[:limit]


def _stdout_error_message(data):
    """The real peekaboo error shape: ``error: {code, message}`` (an object
    on stdout) — distinct from the legacy ``errors: [...]`` list. Returns
    the message string for CLASSIFICATION only (never quoted verbatim into
    a receipt, which may carry window content)."""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return ""


def _is_foreground_required(text):
    """True when a peekaboo failure TEXT says the element/action needs the app
    to be frontmost. Detection is intentionally narrow: the message must name
    foreground AND a requirement/refusal.

    R-M1: this classifies which typed CODE to report. It never decides the
    receipt status — whether anything was dispatched is read ONLY from
    peekaboo's structured result (_refusal_proven_no_mutation). It never
    triggers an automatic escalation either; the caller decides whether to
    re-dispatch opt-in foreground."""
    low = (text or "").lower()
    if "foreground" not in low:
        return False
    # "require" subsumes require/requires/required — the real capture's
    # message is "Raw key presses require explicit foreground consent ..."
    # (press_foreground_required_error.json).
    return any(marker in low for marker in (
        "require", "refused", "refusal", "only", "needs"))


def _refusal_proven_no_mutation(data):
    """True when peekaboo's own structured output proves NOTHING was
    dispatched for this refusal: ``error.mutation_dispatched`` (or
    ``outcome.mutation_dispatched``) is literally false, or the top-level
    ``effect`` is "refused" (peekaboo's explicit pre-dispatch refusal
    marker — real capture: click_snapshot_stale_refused.json). Such a
    receipt may be reported NOT_APPLIED; an unparseable/absent payload
    stays conservative (may have dispatched → EFFECT_UNKNOWN, H1)."""
    if not isinstance(data, dict):
        return False
    for source in (data.get("error"), data.get("outcome"), data):
        if isinstance(source, dict) and \
                source.get("mutation_dispatched") is False:
            return True
    if data.get("effect") == "refused":
        return True
    return False


def _typed_preflight_refusal(data):
    """Typed clean refusal for structured errors peekaboo raised BEFORE any
    dispatch, proven by live captures (tests/fixtures/peekaboo/):

    - INTERNAL_SWIFT_ERROR "No accessibility element is available for
      action invocation" (click_actiononly_no_ax_element.json): the target
      element is AX-VISIBLE but not AX-ACTIONABLE (Tk buttons); peekaboo
      found nothing to invoke → nothing dispatched → ELEMENT_NOT_ACTIONABLE.
    - SNAPSHOT_STALE with effect "refused"
      (click_snapshot_stale_refused.json): the click never ran.

    Returns an OpError (dispatched=False) or None when the payload is not
    one of these proven shapes."""
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    message = str(error.get("message", "")).lower()
    if code == "INTERNAL_SWIFT_ERROR" and \
            "no accessibility element is available" in message:
        refused = OpError(
            "ELEMENT_NOT_ACTIONABLE",
            "target element is AX-visible but not AX-actionable; nothing "
            "was invoked")
        refused.dispatched = False
        return refused
    if code == "SNAPSHOT_STALE" and data.get("effect") == "refused":
        refused = OpError("SNAPSHOT_STALE",
                          "snapshot invalidated by an earlier command; "
                          "nothing was dispatched")
        refused.dispatched = False
        return refused
    return None


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
            error = OpError("DISPATCH_TIMEOUT",
                            "peekaboo %s exceeded %.0fs" % (args[0], timeout))
            error.dispatched = True  # the subprocess ran; effect unknown (H1)
            raise error
        except OSError as error:
            raise OpError("DISPATCH_UNAVAILABLE", str(error))
        stdout = result.stdout or ""
        try:
            data = json.loads(stdout) if stdout.strip() else None
        except ValueError:
            data = None
        if result.returncode != 0 or not isinstance(data, dict):
            # Detail carries stderr only; stdout may embed window content and
            # must never flow into a receipt or error message. The real CLI
            # reports its refusal reason as a structured error object on
            # stdout (real capture: press_foreground_required_error.json),
            # so classification (never quoted verbatim) reads it too.
            message = _stdout_error_message(data)
            if _is_foreground_required(result.stderr) or \
                    _is_foreground_required(message):
                error = OpError("FOREGROUND_REQUIRED",
                                _bounded(result.stderr) or _bounded(message))
                # R-M1: the CODE comes from the text; whether NOTHING was
                # dispatched comes ONLY from peekaboo's structured result
                # (error/outcome mutation_dispatched false, or effect
                # "refused"). A text-only mention of foreground leaves
                # dispatched=True, so the receipt is EFFECT_UNKNOWN and never
                # a false NOT_APPLIED.
                error.dispatched = not _refusal_proven_no_mutation(data)
                raise error
            preflight = _typed_preflight_refusal(data)
            if preflight is not None:
                raise preflight
            error = OpError("CLI_ERROR", "rc=%s %s" % (
                result.returncode, _bounded(result.stderr)))
            error.dispatched = not _refusal_proven_no_mutation(data)
            raise error
        if data.get("success") is False:
            errors = data.get("errors")
            message = ""
            if isinstance(errors, list) and errors:
                first = errors[0]
                message = first if isinstance(first, str) else json.dumps(first)
            if not message:
                message = _stdout_error_message(data)
            # stdout may embed window content; the receipt quotes stderr
            # first and falls back to the structured error message only when
            # stderr says nothing.
            detail = _bounded(result.stderr) or _bounded(message) or \
                "peekaboo failed"
            if _is_foreground_required(message):
                error = OpError("FOREGROUND_REQUIRED", detail)
                # R-M1: structured result only (see the rc!=0 branch above).
                error.dispatched = not _refusal_proven_no_mutation(data)
                raise error
            preflight = _typed_preflight_refusal(data)
            if preflight is not None:
                raise preflight
            error = OpError("CLI_ERROR", detail)
            error.dispatched = not _refusal_proven_no_mutation(data)
            raise error
        payload = data.get("data", data)
        # BCU R3 H1: the real `see` envelope carries a top-level
        # target_receipt ({pid, window_id}) as a SIBLING of "data" — the
        # one identity peekaboo itself bound to the window it resolved
        # (real capture see_fixture_window.json). run_json must not throw
        # it away: merge it into the returned payload, setdefault-only so
        # a key the payload itself carries always wins.
        receipt = data.get("target_receipt")
        if isinstance(receipt, dict) and isinstance(payload, dict):
            payload.setdefault("target_receipt", receipt)
        return payload

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

    def _map_windows(self, data):
        windows = data.get("windows") if isinstance(data, dict) else None
        if not isinstance(windows, list):
            raise OpError("CLI_OUTPUT_INVALID", "window list: no windows array")
        info = data.get("target_application_info")
        if not isinstance(info, dict):
            info = {}
        out = []
        for window in windows:
            if not isinstance(window, dict):
                continue
            out.append({
                "window_id": window.get("window_id", window.get("windowID")),
                "title": window.get("title", window.get("window_title")),
                "owner_pid": window.get("owner_pid", window.get("pid")),
                # H6: real peekaboo reports is_frontmost per window; true
                # means the window is the topmost on screen (nothing can
                # cover it). Kept verbatim; absent stays absent (fail-closed
                # consumers treat missing as not-frontmost).
                "is_frontmost": window.get("is_frontmost"),
                "window_index": window.get("window_index"),
                # Resolved app identity when the CLI reports it per window
                # (real peekaboo reports it once, in target_application_info);
                # the windows op deny-checks and filters on it (FIX 8).
                "app": window.get("app", window.get("app_name",
                                                    info.get("app_name"))),
                "bundle_id": window.get("bundle_id",
                                        window.get("app_bundle_id",
                                                   info.get("bundle_id"))),
            })
        return out

    def list_windows(self, app):
        data = self.run_json(["window", "list", "--app=%s" % app, "--json"],
                             SEE_TIMEOUT_S)
        return self._map_windows(data)

    def owning_pid(self, window_id, app):
        """The pid that owns window_id, or None when unresolvable.

        Enumerates `app list` rows matching the app name and lists each
        pid's windows until the owner is found. This is the stable
        targeting form on this host: `--app NAME` is ambiguous across
        same-name processes (AMBIGUOUS_APP_IDENTIFIER, real captures) and
        plain `see` carries no pid — paste and other window-targeted
        dispatches resolve the pid once, here, before dispatch.
        """
        try:
            apps = self.run_json(["app", "list", "--json"], SEE_TIMEOUT_S)
        except OpError:
            return None
        rows = apps.get("apps") if isinstance(apps, dict) else None
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict) or row.get("name") != app:
                continue
            pid = row.get("pid")
            if not isinstance(pid, int) or isinstance(pid, bool):
                continue
            try:
                data = self.run_json(
                    ["window", "list", "--pid=%d" % pid, "--json"],
                    SEE_TIMEOUT_S)
            except OpError:
                continue
            windows = data.get("windows") \
                if isinstance(data, dict) else None
            if isinstance(windows, list) and any(
                    isinstance(w, dict) and w.get("window_id") == window_id
                    for w in windows):
                return pid
        return None

    def windows_of_window(self, window_id, app):
        """Window list for the app that owns window_id.

        `window list --app NAME` fails when several processes share the app
        name (two Chromes, several Pythons on this host — real captures),
        which would make every frontmost check fail closed on unreadable
        evidence. Fallback: resolve the owning pid (see owning_pid) and
        return only that pid's rows (the ambiguity stays resolved).
        """
        try:
            return self.list_windows(app)
        except OpError:
            pid = self.owning_pid(window_id, app)
            if pid is None:
                raise
            data = self.run_json(
                ["window", "list", "--pid=%d" % pid, "--json"],
                SEE_TIMEOUT_S)
            return self._map_windows(data)

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
        and is never returned to the session.
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

        Dispatch marking lives in run_json (it sees the structured payload):
        a refusal peekaboo proves dispatched nothing stays NOT_APPLIED-
        eligible; every other post-spawn failure is `dispatched` so the
        caller reports EFFECT_UNKNOWN (H1).
        """
        return self.run_json(args, timeout, strategy=self.act_input_strategy)

    def paste(self, args, timeout=PASTE_TIMEOUT_S):
        """Single dispatch of `peekaboo paste`; outcome read back once.

        paste is NOT an element-targeted AX act: it carries --text plus
        --pid/--window-id targeting and is dispatched WITHOUT
        --input-strategy (the input is the paste chord itself, not element
        targeting). Still exactly one subprocess, --no-remote always,
        ANTHROPIC_* stripped from the child environment, never retried.
        The command sets the clipboard, delivers the paste chord, and
        restores the previous clipboard. Dispatch marking: run_json.
        """
        return self.run_json(args, timeout, with_strategy=False)

    def press_chord(self, args, timeout=ACT_TIMEOUT_S):
        """Single dispatch of `peekaboo press <chord>`; outcome read back once.

        A chord press is synthetic key delivery, not an element-targeted AX
        action: like paste it is dispatched WITHOUT --input-strategy. Under
        the runtime's actionOnly strategy a chord has no delivery mechanism
        (live red: rc=1, unparseable stdout, empty stderr); without the flag
        peekaboo delivers the chord background on an exact window selector
        (real capture press_chord_window_background.json). Still one
        subprocess, --no-remote always, never retried; dispatch marking in
        run_json (H1).
        """
        return self.run_json(args, timeout, with_strategy=False)

    def window_focus(self, window_id, timeout=ACT_TIMEOUT_S):
        """Focus (raise) ONE window by exact id; outcome read back once.

        The window-level raise op (live A/B 2026-11-11): `window focus
        --window-id N` returns rc=0 with {action, app_name, window_title,
        new_bounds}; an elementless `action AXRaise` is ALWAYS refused
        ("--on is required") and `window focus` takes neither
        --input-strategy nor --foreground (both refused). One subprocess,
        --no-remote always, never retried; dispatch marking in run_json.
        """
        return self.run_json(
            ["window", "focus", "--window-id", str(window_id), "--json"],
            timeout, with_strategy=False)


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


_IDENTITY_APP_KEYS = ["app", "app_name", "application",
                      "application_name"]
_IDENTITY_BUNDLE_KEYS = ["bundle_id", "app_bundle_id",
                         "application_bundle_id"]
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
    stable element paths usable as act targets.

    A plain `see` (no --tree) carries no tree object — but its flat
    ui_elements list is the same accessibility content; it renders as
    bounded flat lines so look/vision prompts still carry AX text (live
    slice_look red: Tk window, plain see, tree empty → empty answer)."""
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
        for element in snapshot_elements(data):
            if len(lines) >= max_lines:
                break
            if not isinstance(element, dict):
                continue
            role = str(element.get("role", "element"))
            label = str(element.get("label", ""))[:60]
            element_id = element_id_of(element)
            text = "%s: %s" % (role, label)
            if element_id:
                text += "  [@%s]" % element_id
            lines.append(text[:MAX_LINE_CHARS])
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
        """The vision endpoint is LOOPBACK ONLY (H4 principal ruling).

        The captured window image and the bearer token may leave the process
        only toward localhost / 127.0.0.1 / ::1, over http or https. Any
        other host is refused even over https, so a misconfigured router
        cannot exfiltrate window captures.
        """
        try:
            parsed = urllib.parse.urlparse(self.base_url or "")
        except ValueError:
            raise OpError("VISION_ENDPOINT_INSECURE",
                          "endpoint URL unparseable; refused")
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or \
                host not in ("localhost", "127.0.0.1", "::1"):
            raise OpError("VISION_ENDPOINT_INSECURE",
                          "endpoint must be loopback (localhost/127.0.0.1/"
                          "::1, http or https); refused")

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


def _deny_overlay_gate(ctx):
    """H6-INTERIM: refuse a coordinate click while ANY deny-listed app has an
    on-screen window.

    Evidence is read at click time: app list (visible apps only), then the
    window list of each deny-matched app. A window of a deny-listed app may
    float over the target, so a blind coordinate click could land inside a
    password manager. Unreadable evidence fails closed
    (DENY_OVERLAY_UNVERIFIED). Element-targeted clicks are unaffected.
    """
    try:
        apps = ctx.adapter.list_apps()
    except OpError as error:
        raise OpError("DENY_OVERLAY_UNVERIFIED",
                      "app list unavailable (%s); coordinate click refused"
                      % error.code)
    for app in apps:
        if not isinstance(app, dict) or app.get("is_hidden"):
            continue
        name = app.get("name")
        bundle = app.get("bundle_id")
        if not ctx.deny.matches(name, bundle, None):
            continue
        ident = name or bundle or "deny-listed app"
        try:
            windows = ctx.adapter.list_windows(name or bundle or "")
        except OpError as error:
            raise OpError("DENY_OVERLAY_UNVERIFIED",
                          "%s window list unavailable (%s); coordinate click "
                          "refused" % (ident, error.code))
        if windows:
            raise OpError("DENY_OVERLAY",
                          "%s has an on-screen window; coordinate click "
                          "refused" % ident)
    return True


def _frontmost_gate(ctx, snap, window_id):
    """H6: a coordinate click requires the target window to be the globally
    frontmost window at click time.

    `window list` reports per-window `is_frontmost`; the real capture
    (tests/fixtures/peekaboo/window_list_fixture.json) shows a window with
    anything above it in z-order has is_frontmost:false while is_key stays
    true, so is_frontmost:true proves this window is the topmost on screen
    and NOTHING can cover the click point. Evidence is read fresh at click
    time; a missing window, unreadable list, or absent is_frontmost field
    fails closed. Element-targeted clicks are unaffected (the element is
    pinned through the snapshot, not the screen point).
    """
    identity = window_identity(snap)
    app = identity["app_name"] or identity["bundle_id"] or ""
    if not app:
        raise OpError("WINDOW_NOT_FRONTMOST",
                      "owning application unresolvable; coordinate click "
                      "refused")
    try:
        resolve = getattr(ctx.adapter, "windows_of_window", None)
        windows = (resolve(window_id, app) if callable(resolve)
                   else ctx.adapter.list_windows(app))
    except OpError as error:
        raise OpError("WINDOW_NOT_FRONTMOST",
                      "window list unavailable (%s); coordinate click refused"
                      % error.code)
    row = None
    for candidate in windows:
        if isinstance(candidate, dict) and \
                candidate.get("window_id") == window_id:
            row = candidate
            break
    if row is None:
        raise OpError("WINDOW_GONE",
                      "window %s no longer present in %s's window list"
                      % (window_id, app))
    if row.get("is_frontmost") is not True:
        raise OpError("WINDOW_NOT_FRONTMOST",
                      "window %s is not the frontmost window "
                      "(is_frontmost=%r, window_index=%r); a window above it "
                      "could intercept a coordinate click"
                      % (window_id, row.get("is_frontmost"),
                         row.get("window_index")))
    return True


def _act_gate(ctx, args, window_id):
    """Deny list, then lease (renewed), then human-presence gate.

    Returns the identity/bounds metadata from the read-only window probe so
    callers needing window geometry do not dispatch a second probe.
    """
    meta = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, meta)
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; act refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    return meta


def _foreground_gate(ctx, args):
    """Re-check lease + human presence for an opt-in foreground dispatch."""
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; foreground refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    return state


PASTE_GATE_UNPASTED = ("nothing was pasted; the pasteboard is unchanged "
                       "(this layer never writes it — peekaboo's paste is the "
                       "only clipboard writer and it never ran)")


def _paste_foreground_gate(ctx, args, snap, window_id):
    """R-H1 (BCU R2 item 5): the two checks that run IMMEDIATELY before the
    opt-in foreground paste chord.

    ``paste --foreground`` delivers Cmd+V to whichever window holds focus, so
    a deny-listed window — the target itself, or a floating password-manager
    or Keychain panel above it — could receive text meant for the target.

    Order, both on FRESH reads at this instant:
      1. DENY   — the target's identity on a screenshot-less observe
                  (``see --tree --no-screenshot``; no pixels are taken on a
                  refused window), then no deny-listed app may hold an
                  on-screen window.
      2. FRONTMOST — the target window must be the topmost window right now
                  (``is_frontmost`` true); slice_front raises it when needed.

    Either failure refuses BEFORE the paste subprocess starts: nothing is
    pasted, the previous pasteboard contents are still in place (the layer
    never sets the clipboard itself), and the receipt carries
    ``pasted: false`` / ``clipboard_state: unchanged``. There is no retry and
    no fallback to a background paste.
    """
    def _refuse(code, detail):
        wrapped = OpError(code, "%s; %s" % (detail, PASTE_GATE_UNPASTED))
        wrapped.extra = {"pasted": False, "clipboard_state": "unchanged"}
        return wrapped

    gate_codes = {"DENY_LISTED", "DENY_OVERLAY", "DENY_OVERLAY_UNVERIFIED",
                  "WINDOW_NOT_FRONTMOST", "WINDOW_GONE",
                  "WINDOW_IDENTITY_UNKNOWN"}
    try:
        fresh = ctx.adapter.inspect_window(window_id)
        _deny_gate_window(ctx, fresh)          # 1. deny
        _deny_overlay_gate(ctx)                # 1. deny (floating panels)
        _frontmost_gate(ctx, fresh, window_id)  # 2. frontmost
    except OpError as error:
        if error.code in gate_codes:
            raise _refuse(error.code, error.detail)
        # The evidence that would prove the two checks could not be read:
        # refuse the paste pre-dispatch (typed, never a text heuristic).
        raise _refuse("PASTE_GATE_UNVERIFIED",
                      "deny/frontmost evidence unreadable (%s: %s)"
                      % (error.code, error.detail))
    return fresh


def _act_observe(ctx, args, window_id):
    """Gate, then take the FRESH snapshot every ACT dispatches on.

    Order (D-H2): lease + presence (local, no read), then the deny list on
    a read that takes NO screenshot (``see --tree --no-screenshot``, the
    same pattern as _op_capture), and only then one pixel-taking
    ``see --window-id N --json`` (identity, ui_elements,
    coordinate_context) whose identity is deny-checked again. A refused
    window is never photographed — peekaboo persists every pixel-taking
    ``see`` under ~/.peekaboo/snapshots, so the deny must precede pixels.
    Returns (snapshot, snapshot_id).
    """
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    state = ctx.presence.gate_ok()
    if state["human_active"]:
        raise OpError("HUMAN_ACTIVE",
                      "human idle %.1fs < %.1fs threshold; act refused"
                      % (state["human_idle_seconds"], ctx.presence.min_idle))
    pre = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, pre)
    snap = ctx.adapter.snapshot_window(window_id)
    _deny_gate_window(ctx, snap)
    snapshot_id = snapshot_id_of(snap)
    if not snapshot_id:
        raise OpError("SNAPSHOT_UNAVAILABLE",
                      "peekaboo see returned no snapshot_id; act refused")
    return snap, snapshot_id


def _dispatch_act(ctx, args, base_argv, dispatcher=None):
    """ONE dispatch whose mode comes from the explicit caller flag ONLY.

    M10-CODE: there is no error-text-driven escalation. allow_foreground is
    false by default -> one background dispatch. A FOREGROUND_REQUIRED
    failure is terminal (never retried) and its receipt status is decided
    ONLY by peekaboo's structured result: NOT_APPLIED when the result proves
    nothing was dispatched (mutation_dispatched false / effect refused),
    EFFECT_UNKNOWN otherwise (R-M1). allow_foreground=true -> the lease and
    presence gates are re-run and the SINGLE dispatch carries --foreground
    (never a background attempt first, never a retry).

    `dispatcher` selects the adapter entry (act vs press_chord: a chord is
    synthetic delivery and must not carry the actionOnly strategy).

    Returns (result_meta, used_foreground).
    """
    dispatch = dispatcher or ctx.adapter.act
    if bool(args.get("allow_foreground")):
        _foreground_gate(ctx, args)
        return dispatch(list(base_argv) + ["--foreground"]), True
    return dispatch(list(base_argv)), False


def _act_receipt(ctx, args, window_id, op, element_ref, result_meta,
                 snapshot_id, element=None, foreground=False, extra=None):
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
                   foreground=foreground, extra=extra)


def handle_tool_call(ctx, args):
    """Dispatch one tools/call. Returns an MCP result dict."""
    if not isinstance(args, dict):
        return _error_result("INVALID_ARGUMENTS", "arguments must be an object")
    # The schema declares additionalProperties:false; enforce it here too so
    # a removed field (notably keep_path, H4) is a typed refusal and never
    # silently ignored.
    unknown = sorted(set(args) - set(TOOL_SCHEMA["properties"]))
    if unknown:
        return _error_result("INVALID_ARGUMENTS",
                             "unknown argument(s): %s" % ", ".join(unknown))
    action = args.get("action")
    if action not in ACTIONS:
        return _error_result("UNKNOWN_ACTION", repr(action))
    handler = _HANDLERS[action]
    try:
        return handler(ctx, args)
    except OpError as error:
        if (getattr(error, "dispatched", False)
                and str(action) in DISPATCH_ACT_OPS
                and error.code not in ACT_CLEAN_PRE_DISPATCH_CODES):
            # H1: the dispatch STARTED, so the event may have landed. Only
            # a proven pre-dispatch refusal may claim NOT_APPLIED.
            payload = receipt(str(action), args.get("window_id"),
                              args.get("element_ref"), "EFFECT_UNKNOWN",
                              cause=error)
            if str(action) == "slice_paste":
                payload["clipboard_state"] = "unknown"
            return {"content": [{"type": "text",
                                 "text": json.dumps(payload)}],
                    "isError": True}
        if error.code in ("LEASE_NOT_HELD", "LEASE_HELD", "LEASE_NOT_OWNER",
                          "LEASE_OWNER_REQUIRED", "LEASE_TTL_INVALID",
                          "LEASE_NONCE_INVALID",
                          "LEASE_CONTENDED",
                          "HUMAN_ACTIVE", "PRESENCE_UNKNOWN", "DENY_LISTED",
                          "WINDOW_IDENTITY_UNKNOWN",
                          "CHORD_GLOBAL", "CHORD_INVALID",
                          "CHORD_NOT_ALLOWED",
                          "COORDS_REQUIRED", "WINDOW_BOUNDS_UNKNOWN",
                          "POINT_OUTSIDE_WINDOW", "APP_REQUIRED",
                          "WINDOW_ID_REQUIRED", "VISION_QUESTION_REQUIRED",
                          "VISION_UNCONFIGURED",
                          "CLI_OUTPUT_INVALID", "CAPTURE_EMPTY",
                          "ELEMENT_REF_REQUIRED", "ELEMENT_REF_INVALID",
                          "ELEMENT_NOT_FOUND", "SNAPSHOT_UNAVAILABLE",
                          "FOREGROUND_REQUIRED", "TEXT_REQUIRED",
                          "DIRECTION_INVALID", "AMOUNT_INVALID",
                          "HUMAN_ACTIVE_MID_SEQUENCE", "PACING_WAIT",
                          "CHALLENGE_DETECTED", "SLICE_TARGET_REQUIRED",
                          "SLICE_TARGET_AMBIGUOUS", "SLICE_TARGET_NOT_FOUND",
                          "VISION_ENDPOINT_INSECURE", "HINTS_TOO_LONG",
                          "QUESTION_TOO_LONG",
                          "DENY_OVERLAY", "DENY_OVERLAY_UNVERIFIED",
                          "WINDOW_NOT_FRONTMOST", "WINDOW_GONE",
                          "PASTE_GATE_UNVERIFIED"):
            payload = receipt(str(action), args.get("window_id"),
                              args.get("element_ref"), "NOT_APPLIED",
                              cause=error)
            gate_extra = getattr(error, "extra", None)
            if isinstance(gate_extra, dict) and gate_extra:
                # Truthful pre-dispatch facts only (never a status override).
                for key, value in gate_extra.items():
                    payload.setdefault(key, value)
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
                                   window.get("title"))
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
    """Capture returns METADATA + AX/OCR text only (H4 principal ruling).

    The PNG never enters an MCP/CLI reply and is never persisted by this
    layer: the image is held in memory just long enough to measure it and is
    deleted with the staging directory before the receipt is returned.
    """
    window_id = _require_window_id(args)
    ocr = bool(args.get("ocr"))
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
        return _text_result({
            "op": "capture", "status": "OK",
            "window_id": window_id,
            "bytes": len(png),
            "image_returned": False,
            "ocr_text": extract_ocr(meta) if ocr else None})
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
    key = _shared_act_gate(ctx, snap, window_id, "press")
    element = resolve_element(snap, element_ref)
    element_id = element_id_of(element)
    if not element_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    meta, foreground = _dispatch_act(ctx, args, [
        "action", "AXPress", "--on", element_id,
        "--snapshot", snapshot_id, "--json"])
    state_write = _pace_record(ctx, key, window_id)
    return _text_result(_act_receipt(
        ctx, args, window_id, "press", element_ref, meta, snapshot_id,
        element, foreground,
        extra={"state_write": state_write} if state_write else None))


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
    key = _shared_act_gate(ctx, snap, window_id, "set_text")
    element = resolve_element(snap, element_ref)
    element_id = element_id_of(element)
    if not element_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    meta, foreground = _dispatch_act(ctx, args, [
        "set-value", "--value=%s" % text, "--on", element_id,
        "--snapshot", snapshot_id, "--json"])
    state_write = _pace_record(ctx, key, window_id)
    return _text_result(_act_receipt(
        ctx, args, window_id, "set_text", element_ref, meta, snapshot_id,
        element, foreground,
        extra={"state_write": state_write} if state_write else None))


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
    # that authorizes background key delivery. The dispatch carries BOTH the
    # exact --window-id selector and the snapshot receipt (the proven form:
    # press_chord_window_background.json delivered background on --window-id;
    # a 16:08Z probe showed --snapshot alone also delivers once the strategy
    # flag is gone — the live rc=1 refusal was the actionOnly strategy, which
    # leaves a synthetic chord with no delivery mechanism). A chord is
    # synthetic key delivery: it goes through press_chord (no
    # --input-strategy, same as paste).
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    key = _shared_act_gate(ctx, snap, window_id, "keys", chord=lowered)
    meta, foreground = _dispatch_act(ctx, args, [
        "press", chord, "--window-id", str(window_id),
        "--snapshot", snapshot_id, "--json"],
        dispatcher=ctx.adapter.press_chord)
    state_write = _pace_record(ctx, key, window_id)
    return _text_result(_act_receipt(
        ctx, args, window_id, "keys", None, meta, snapshot_id, None,
        foreground, extra={"state_write": state_write} if state_write else None))


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
    _shared_act_gate(ctx, snap, window_id, "scroll")
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
        key = _shared_act_gate(ctx, snap, window_id, "pointer_click")
        element = resolve_element(snap, element_ref)
        element_id = element_id_of(element)
        if not element_id:
            raise OpError("ELEMENT_NOT_FOUND",
                          "resolved element has no id in the fresh snapshot")
        meta, foreground = _dispatch_act(ctx, args, [
            "click", "--snapshot", snapshot_id, "--on", element_id,
            "--json"])
        state_write = _pace_record(ctx, key, window_id)
        return _text_result(_act_receipt(
            ctx, args, window_id, "pointer_click", element_ref, meta,
            snapshot_id, element, foreground,
            extra={"state_write": state_write} if state_write else None))
    if not has_coords:
        raise OpError("COORDS_REQUIRED",
                      "element_ref, or integer x,y required")
    snap, snapshot_id = _act_observe(ctx, args, window_id)
    _frontmost_gate(ctx, snap, window_id)  # H6: coordinate click only
    _deny_overlay_gate(ctx)  # H6-INTERIM: coordinate click only
    key = _shared_act_gate(ctx, snap, window_id, "pointer_click")
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
    state_write = _pace_record(ctx, key, window_id)
    return _text_result(_act_receipt(
        ctx, args, window_id, "pointer_click", None, meta, snapshot_id, None,
        foreground, extra={"state_write": state_write} if state_write else None))


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


# The minimum pacing set from the brief: every act that can change a page
# or send, plus keys enter/return (other plain navigation keys are not paced).
PACED_ACT_OPS = {"press", "set_text", "pointer_click", "slice_click",
                 "slice_paste", "slice_send"}
PACED_KEY_CHORDS = {"enter", "return"}


def _shared_act_gate(ctx, snap, window_id, op, chord=None):
    """THE single pre-act gate for every act that can change a page or send
    (H3): challenge scan on the fresh snapshot, then pacing on the R-M3
    key (pid + exact window id, resolved by target_receipt_pid — H1).

    Returns the pacing key when this act is paced (the caller records it
    after the dispatch), else None. A challenge hit or PACING_WAIT raises
    BEFORE any dispatch. Never duplicated per handler.
    """
    _challenge_scan(ctx, snap, None, op)
    paced = op in PACED_ACT_OPS or (
        op == "keys" and _canonical(chord) in PACED_KEY_CHORDS)
    if not paced:
        return None
    # R-M3 / BCU R3 H1: pid + exact window id, from THE one resolver — the
    # target_receipt this act's own fresh snapshot already carries. No
    # window-list subprocess read. A title change never resets the
    # interval; a window id recycled by another process cannot inherit a
    # pace record (different pid).
    pid = target_receipt_pid(snap)
    key = pacing_key(window_id, pid)
    ctx.pacer.check(key)
    return key


def _pace_record(ctx, key, window_id=None):
    """Record the dispatch attempt for `key`; None on success, "failed" when
    the state write raises OSError (M9: never turns a completed act into a
    refusal)."""
    if key is None:
        return None
    try:
        ctx.pacer.record(key, window_id)
    except OSError:
        return "failed"
    return None


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


def _confirm_skipped(ctx):
    """Post-dispatch CONFIRM-step presence check (H2).

    The act has ALREADY completed when this runs. A human who became
    active (or an unreadable idle state) must skip the confirm read, never
    turn the completed act into NOT_APPLIED: the caller returns APPLIED with
    confirm_skipped naming why. Returns None when the confirm may proceed.
    """
    try:
        state = ctx.presence.gate_ok()
    except OpError as error:
        return error.code
    return "HUMAN_ACTIVE" if state.get("human_active") else None


def _slice_observe(ctx, args, window_id, completed):
    """Slice observe step: lease renew + presence + deny list on a read
    that takes NO screenshot (D-H2) + ONE fresh pixel snapshot whose
    identity is deny-checked again. A refused window is never
    photographed. Appends the completed step."""
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    _slice_sequence_gate(ctx, completed, "observe")
    pre = ctx.adapter.inspect_window(window_id)
    _deny_gate_window(ctx, pre)
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
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    _slice_sequence_gate(ctx, completed, "act")
    meta = ctx.adapter.act(list(argv) + ["--foreground"])
    completed.append("act:%s" % label)
    return meta


def _slice_focus_act(ctx, args, window_id, completed):
    """Window-level focus (raise) step: lease renew + presence re-check,
    then ONE `window focus --window-id` dispatch (adapter.window_focus).
    No --foreground (the focus op IS the raise; the flag is refused), no
    --input-strategy, no background attempt first, no retry."""
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    _slice_sequence_gate(ctx, completed, "act")
    meta = ctx.adapter.window_focus(window_id)
    completed.append("act:window focus window_id=%s" % window_id)
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
    # M6: the named app must actually own the requested window, and no
    # window of that app may carry a deny-listed title. A caller cannot
    # smuggle "window 999 of TextEdit" past the app identity check.
    try:
        windows = ctx.adapter.list_windows(app)
    except OpError:
        windows = []
    target = None
    for window in windows:
        if not isinstance(window, dict):
            continue
        if window.get("window_id") == window_id:
            target = window
        matched = ctx.deny.matches(window.get("app") or app,
                                   window.get("bundle_id"),
                                   window.get("title"))
        if matched:
            raise OpError("DENY_LISTED",
                          "window entry matched by %s" % matched)
    if target is None:
        raise OpError("WINDOW_APP_MISMATCH",
                      "window_id %s is not a window of %r"
                      % (window_id, app))
    return app, window_id, (title if has_title else None)


def _op_slice_front(ctx, args):
    app, window_id, title = _slice_front_select(ctx, args)
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Raise via the WINDOW-LEVEL focus op, never an element action: an
    # elementless `action AXRaise` is always refused by peekaboo
    # ("--on is required", live rc=1 real capture raise_a/b) and Tk-host
    # snapshots expose no Window-role element to target. `window focus
    # --window-id N` is exact, needs no element, and takes neither
    # --input-strategy nor --foreground (live A/B 2026-11-11 focus_c/d).
    _slice_focus_act(ctx, args, window_id, completed)
    # Confirm: observe the window's title + window_id after raising. The
    # raise already completed, so an active human only SKIPS the readback.
    target_extra = {"app": app}
    if title:
        target_extra["title_selector"] = title
    skipped = _confirm_skipped(ctx)
    if skipped:
        observed = ("raised window_id=%s; confirm skipped (%s)"
                    % (window_id, skipped))
        return _text_result(receipt("slice_front", window_id, None, "APPLIED",
                                    observed=observed, foreground=True,
                                    target_extra=target_extra,
                                    extra={"confirm_skipped": skipped,
                                           "steps": list(completed)}))
    observed_title = None
    try:
        resolve = getattr(ctx.adapter, "windows_of_window", None)
        windows = (resolve(window_id, app) if callable(resolve)
                   else ctx.adapter.list_windows(app))
        for window in windows:
            if window.get("window_id") == window_id:
                observed_title = window.get("title")
                break
        if observed_title is None:
            observed_title = "(not found in post-raise window list)"
    except OpError as error:
        observed_title = "(readback failed: %s)" % error.code
    observed = "raised window_id=%s title=%s" % (window_id, observed_title)
    return _text_result(receipt("slice_front", window_id, None, "APPLIED",
                                observed=observed, foreground=True,
                                target_extra=target_extra,
                                extra={"steps": list(completed)}))


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
    if element_ref is None:
        _frontmost_gate(ctx, snap, window_id)  # H6: coordinate click only
        _deny_overlay_gate(ctx)  # H6-INTERIM: coordinate click only
    # Shared pre-act gate BEFORE any click dispatch (challenge + pacing).
    key = _shared_act_gate(ctx, snap, window_id, "slice_click")
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
    state_write = _pace_record(ctx, key, window_id)
    extra = {"steps": list(completed)}
    if state_write:
        extra["state_write"] = state_write
    return _text_result(receipt("slice_click", window_id, ref, "APPLIED",
                                observed=label, foreground=True, extra=extra))


def _paste_argv(ctx, text, app_name, window_id, pid):
    """paste dispatch: --text + --pid/--window-id targeting, no
    --input-strategy (the adapter's paste() path omits it). Targeting is by
    PID, never `--app NAME` (ambiguous across same-name processes — the
    live rc=1 paste refusal; the M11 captures all delivered with --pid).
    Optional --focus-timeout/--restore-delay come from runtime.json only."""
    argv = ["paste", "--text=%s" % text, "--pid=%d" % pid,
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
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Shared pre-act gate BEFORE any dispatch (the focus click is an input
    # too): challenge + PACING_WAIT at the M8 key.
    key = _shared_act_gate(ctx, snap, window_id, "slice_paste")
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
    # Targeting uses THE one resolver (BCU R3 H1): the target_receipt pid
    # from the slice's own fresh snapshot — the same pid the pacing key
    # used, no app-list/window-list subprocess walk (--app is ambiguous on
    # same-name hosts; unresolvable identity refuses).
    pid = target_receipt_pid(snap)
    if pid is None:
        raise OpError("WINDOW_IDENTITY_UNKNOWN",
                      "owning pid not resolvable for window %s; paste "
                      "refused (--app targeting is ambiguous)" % window_id)
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    _slice_sequence_gate(ctx, completed, "act")
    # M10 law for paste: background is the default single dispatch; the
    # opt-in flag (and only the flag) adds --foreground. On this host a
    # background paste into a Tk window returns the unconfirmed-outcome
    # refusal with mutation_dispatched:true → honest EFFECT_UNKNOWN (real
    # capture paste_background_unconfirmed.json); the foreground paste
    # delivers (paste_foreground_unconfirmed_but_delivered.json + fixture
    # FIELD line).
    allow_fg = bool(args.get("allow_foreground"))
    paste_argv = _paste_argv(ctx, text, app_name, window_id, pid)
    if allow_fg:
        _foreground_gate(ctx, args)
        # R-H1 (BCU R2 item 5): deny, then frontmost — both on fresh reads
        # immediately before the chord. A failure here refuses BEFORE the
        # paste subprocess starts: nothing pasted, pasteboard unchanged.
        _paste_foreground_gate(ctx, args, snap, window_id)
        paste_argv = paste_argv + ["--foreground"]
    state_write = None
    try:
        paste_meta = ctx.adapter.paste(paste_argv)
    except OpError as error:
        # Failure truthfulness (security-fix pass): once the paste dispatch
        # has been ATTEMPTED (run_json marked it dispatched=True), only a
        # refusal peekaboo proved dispatched nothing (mutation_dispatched
        # false, or a clean pre-dispatch code) may report NOT_APPLIED.
        # Any other dispatch-phase failure may have set the clipboard
        # and/or delivered the paste chord — report EFFECT_UNKNOWN.
        # DISPATCH_TIMEOUT / DISPATCH_UNAVAILABLE already map correctly in
        # the handler and pass through unchanged.
        if error.code in ("DISPATCH_TIMEOUT", "DISPATCH_UNAVAILABLE"):
            raise
        if getattr(error, "dispatched", False) and \
                error.code not in ACT_CLEAN_PRE_DISPATCH_CODES:
            raise OpError("EFFECT_UNKNOWN",
                          "paste dispatch failed in flight; effect unknown "
                          "(%s: %s)" % (error.code, error.detail))
        raise
    finally:
        state_write = _pace_record(ctx, key, window_id)
    completed.append("act:paste window_id=%s" % window_id)
    # `restored` comes from the documented receipt key only (top level or
    # inside coordinate_context); a nested decoy inside a ui_element must
    # never be read as the clipboard confirmation.
    restored_raw = _top_find(paste_meta, ["clipboard_restored"])
    if restored_raw is None:
        coord = _top_find(paste_meta, ["coordinate_context"])
        if isinstance(coord, dict):
            restored_raw = _top_find(coord, ["clipboard_restored"])
    restored = bool(restored_raw)
    restore_reported = restored_raw is not None
    # Confirm: fresh see, read the target field's AX value back. The paste
    # already dispatched, so an active human only SKIPS this readback (H2).
    skipped = _confirm_skipped(ctx)
    paste_confirmed = False
    note = ""
    if skipped:
        note = " (confirm skipped: %s)" % skipped
    else:
        try:
            # D-H2: the confirm read deny-checks on a screenshot-less read
            # first; a window that became deny-listed after the paste is
            # never photographed again.
            pre = ctx.adapter.inspect_window(window_id)
            _deny_gate_window(ctx, pre)
            fresh = ctx.adapter.snapshot_window(window_id)
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
    extra = {"paste_confirmed": bool(paste_confirmed), "restored": restored,
             "steps": list(completed),
             # Stated explicitly both ways (unlike other receipts, which
             # only mark foreground=True): a background paste may come back
             # unconfirmed (EFFECT_UNKNOWN) while a foreground paste is a
             # consented steal-focus — the caller must see which one ran.
             "foreground": allow_fg}
    if skipped:
        extra["confirm_skipped"] = skipped
    if state_write:
        extra["state_write"] = state_write
    if not restore_reported:
        extra["restore_reported"] = False
    return _text_result(receipt("slice_paste", window_id, element_ref,
                                "APPLIED", observed=observed,
                                target_extra={"app": app_name}, extra=extra))


def _op_slice_send(ctx, args):
    window_id = _require_window_id(args)
    element_ref = args.get("element_ref")
    if not element_ref or not isinstance(element_ref, str):
        raise OpError("ELEMENT_REF_REQUIRED",
                      "the send control's element_ref is required")
    completed = []
    snap, snapshot_id = _slice_observe(ctx, args, window_id, completed)
    # Shared pre-act gate BEFORE any send dispatch: challenge scan + pacing.
    # A match STOPS the layer: terminal NOT_APPLIED, bounded quote, no retry.
    key = _shared_act_gate(ctx, snap, window_id, "slice_send")
    element = resolve_element(snap, element_ref)
    elem_id = element_id_of(element)
    if not elem_id:
        raise OpError("ELEMENT_NOT_FOUND",
                      "resolved element has no id in the fresh snapshot")
    ctx.lease.require_and_renew(args.get("owner"),
                                   nonce=args.get("lease_nonce"))
    _slice_sequence_gate(ctx, completed, "act")
    state_write = None
    try:
        ctx.adapter.act(["click", "--on", elem_id, "--snapshot",
                         snapshot_id, "--json"] + ["--foreground"])
    finally:
        state_write = _pace_record(ctx, key, window_id)
    completed.append("act:send_click:%s" % elem_id)
    extra = {"steps": list(completed)}
    if state_write:
        extra["state_write"] = state_write
    return _text_result(receipt("slice_send", window_id, element_ref,
                                "APPLIED",
                                observed="send control %s clicked" % elem_id,
                                foreground=True, extra=extra))


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
        # H4: AX text + the vision model's TEXT answer only; the PNG never
        # enters the reply.
        payload["image_returned"] = False
        return _text_result(payload)
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

def build_context(state_dir=None, runtime_path=None, deny_path=None):
    """Assemble the production context.

    BCU R3 H2: the optional arguments are LAUNCH-argument injection
    (main() --state-dir/--runtime/--deny) — the only path-override
    mechanism left, used by the harness round-trip test and an explicit
    operator launch line. Environment variables still select only among
    IN-LAYER paths (MMOS_CU_DENY/MMOS_CU_RUNTIME) and can never lower a
    floor; nothing a session can set by environment or file loosens a rule.
    """
    runtime = load_runtime(runtime_path or resolve_runtime_path())
    if deny_path is None:
        deny_path = os.environ.get("MMOS_CU_DENY")
        if deny_path:
            deny_path = _env_path_override("MMOS_CU_DENY", deny_path)
        else:
            deny_path = os.path.join(HERE, "deny.json")
    deny = DenyList.load(deny_path)
    lease = Lease(state_dir=state_dir)
    presence = Presence(runtime=runtime)
    pacer = Pacer(state_dir=state_dir, runtime=runtime)
    adapter = PeekabooAdapter(runtime)
    vision = VisionClient()
    return ToolContext(runtime, deny, lease, presence, adapter, vision, pacer)


def serve(stdin=None, stdout=None, state_dir=None, runtime_path=None,
          deny_path=None):
    """MCP loop. Readable/writable streams are injectable for tests; the
    path arguments are the launch-argument injection path (H2)."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    try:
        ctx = build_context(state_dir=state_dir, runtime_path=runtime_path,
                            deny_path=deny_path)
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


def main(argv=None):
    """Entry point.

    BCU R3 H2: launch ARGUMENTS (never environment variables) are the only
    path-override mechanism. --state-dir/--runtime/--deny exist for the
    harness round-trip test (which passes its scratch state path as an
    argument) and for an explicit operator launch line; the 180 s floors and
    the in-layer env-path rule hold unconditionally either way.
    """
    parser = argparse.ArgumentParser(
        prog=SERVER_NAME,
        description="Restrained computer-use MCP server (stdio).")
    parser.add_argument("--state-dir", default=None,
                        help="lease/pacing state folder (default: the "
                             "built-in state folder)")
    parser.add_argument("--runtime", default=None,
                        help="runtime descriptor path (default: the pinned "
                             "in-layer runtime.json / runtime.json.dev)")
    parser.add_argument("--deny", default=None,
                        help="deny-list path (default: the in-layer "
                             "deny.json)")
    args = parser.parse_args(argv)
    return serve(state_dir=args.state_dir, runtime_path=args.runtime,
                 deny_path=args.deny)


if __name__ == "__main__":
    sys.exit(main())
