# mmos_computer_use — supervised macOS computer-use MCP server

A zero-dependency (Python 3 stdlib only, runs on `/usr/bin/python3`) stdio
MCP server that gives a session **window-scoped** computer use on macOS by
wrapping the [Peekaboo](https://github.com/steipete/peekaboo) CLI.

Design summary:

- **One MCP tool.** The server exposes exactly one tool, `mmos_computer_use`;
  its single `action` argument selects the operation, so registration stays
  one tool regardless of how many operations are supported.
- **Window-scoped only.** Every SEE/ACT/VISION operation names exactly one
  `window_id` (or, for the pure enumeration ops `apps` / `windows`, one app).
  No screen-wide, display-wide or all-windows parameter exists anywhere in
  the tool schema.
- **Deny list first.** Credential managers (Keychain Access, 1Password,
  Bitwarden, Dashlane, Proton Pass, Keeper, Enpass, Strongbox), password
  surfaces (Passwords), System Settings, terminal emulators (Terminal, iTerm,
  iTerm2) and Script Editor are deny-listed in `deny.json` (an arbitrary
  command surface is not a document window). Every operation that targets a
  window or an app checks the list first; a match refuses the operation
  (`DENY_LISTED`) before any content is read. The `windows` op additionally
  denies every resolved app identity present in the CLI result (the whole op
  refuses, zero results) and drops entries whose resolved app name is not
  exactly the requested app; the requested string is matched against app
  names AND bundle ids (exact-match semantics unchanged). Extra app names,
  bundle ids and window-title regexes can be added to the `extra_*` fields
  without touching the defaults.
- **Lease + presence before any ACT.** Acts (AX press, set-value text,
  keyboard chord, scroll, last-resort pointer click) and slice ops require
  1. a held lease (`lease_acquire`, file-backed, single holder, TTL, renewed
     on every act; `lease_status` reports the owner REDACTED — first 8 chars
     plus an ellipsis and `owner_redacted: true` — while acquire/release
     still require the exact owner string),
  2. a human-idle screen (`ioreg -c IOHIDSystem` HIDIdleTime >= threshold,
     default **180 s** for ALL acts, env `MMOS_CU_PRESENCE_MIN_IDLE` or
     runtime.json `presence_min_idle_seconds`; both sources refuse values
     below the 1 s floor at startup), and
  3. the deny-list pass on the window identity read by the act's own fresh
     snapshot.
  A blocked act is a `NOT_APPLIED` receipt with cause `LEASE_NOT_HELD` or
  `HUMAN_ACTIVE`; it is never queued or replayed.
- **Background by default; focus stealing prohibited.** Every act first takes
  its OWN fresh `see --window-id N --json` snapshot, resolves the caller's
  `element_ref` against that snapshot's `ui_elements`, and dispatches ONCE
  with `--snapshot <id> --on <elem> --input-strategy actionOnly --no-remote`.
  The act command carries no `--app`/`--pid`/`--window-id` (peekaboo rejects
  that combination) and no `--foreground`, so the user's frontmost app is
  never disturbed. A foreground-required refusal is returned as
  `NOT_APPLIED` / `FOREGROUND_REQUIRED` and is **never** escalated or retried.
  Only an explicit per-call `allow_foreground: true` (default false), with the
  lease held and the presence gate passing, may add `--foreground` as one
  fresh dispatch; that receipt carries `"foreground": true`.
- **Receipts, no retries.** Every ACT returns
  `{"target": {op, window_id, element_ref}, "status": "APPLIED" |
  "NOT_APPLIED" | "EFFECT_UNKNOWN", "cause"?: "CODE: bounded text",
  "observed": "..."}`. Dispatch is single-shot: one subprocess per operation,
  no retry loop anywhere. A timeout or unreadable outcome is reported
  `EFFECT_UNKNOWN` and left for human/next-session reconciliation.
- **Pinned runtime.** `runtime.json` (schema `mmos.computer_use.runtime/v1`)
  pins the peekaboo binary path and SHA-256; the digest is verified on every
  server start and a mismatch refuses startup (`PIN_MISMATCH`).
  `runtime.json.dev` is the dev config pointing at
  `/opt/homebrew/bin/peekaboo`. The server always passes `--no-remote` and
  `--input-strategy`, and never passes `--bridge-socket`. SEE uses
  `input_strategy` (default `actionFirst`); ACT always uses
  `act_input_strategy`, which must be `actionOnly` (any other value refuses
  startup with `RUNTIME_ACT_STRATEGY`) so acts are AX actions and never
  synthesized keystrokes.
- **Vision, in memory.** `vision_ask` captures one window into a private
  staging directory, sends the PNG (base64, in-process via `urllib.request`
  with headers — never curl/argv) to the configured Anthropic-protocol vision
  endpoint with the token read from `ANTHROPIC_AUTH_TOKEN` **at call time
  only**, and returns `{answer, elements, model}` where elements carry
  normalized 0–1000 image coordinates. The endpoint must be https, or plain
  http only on the loopback (`localhost` / `127.0.0.1` / `::1`); anything
  else is refused (`VISION_ENDPOINT_INSECURE`) — the captured window image
  and token must never travel an unencrypted link. Prompt text is capped:
  `question` ≤ 2000 chars (`QUESTION_TOO_LONG`), caller `element_hints` ≤ 20
  entries, 120 chars each, 1200 chars total (`HINTS_TOO_LONG`); over-limit
  input is refused before any capture or network dispatch. Image
  bytes/base64 never appear in logs, errors or files; staging directories
  are deleted in `finally`.
  Captures are only persisted when `keep_path` is given **and** lies under
  the caller scratch directory `MMOS_CU_SCRATCH`; anything else is refused
  (`KEEP_PATH_*`).
- **Slice ops: one named window, end-to-end.** `slice_front`, `slice_click`,
  `slice_paste`, `slice_send` and `slice_look` each drive ONE named window
  (observe → act → confirm) per `tools/call` and return the same receipt
  shape. They are foreground-class by design (AXRaise/AXPress-class/paste
  need the window exposed), lawful only under the passed deny + lease +
  presence gates: the single dispatch carries `--foreground` directly, is
  never attempted in the background first, and is never retried.
  - **Mid-sequence presence.** Presence is re-checked before EVERY step and
    between steps; a human becoming active mid-sequence aborts with
    `NOT_APPLIED` / `HUMAN_ACTIVE_MID_SEQUENCE` naming exactly which steps
    completed (truthful partial-state reporting — nothing continues,
    nothing retries).
  - **Pacing.** A minimum interval (default **180 s**, env
    `MMOS_CU_PACING_SECONDS` or runtime.json `pacing_seconds`; both sources
    refuse values below the 1 s floor at startup) between two `slice_paste`
    or `slice_send` sequences on the SAME window (keyed by window id,
    persisted as `pacing.json` under the state dir). Too soon →
    `NOT_APPLIED` / `PACING_WAIT` with the seconds remaining.
  - **Challenge stop.** Before ANY input-delivering dispatch, `slice_click`,
    `slice_paste` and `slice_send` each scan the window's AX text (and OCR
    text if present) for challenge patterns — captcha, are you a robot,
    verify you are human, sign in, log in, rate limit, too many requests,
    unusual activity, access denied (case-insensitive; extendable via
    runtime.json `challenge_patterns_extra`). A match is a terminal
    `NOT_APPLIED` / `CHALLENGE_DETECTED` with a bounded quote of what was
    seen. The layer stops and reports; it does not retry. `slice_front`
    raises without delivering input and keeps no scan.
  - **Paste failure truth table.** A `slice_paste` failure is either a
    provably pre-dispatch refusal — `WINDOW_IDENTITY_UNKNOWN`, `DENY_LISTED`,
    `LEASE_NOT_HELD`, `HUMAN_ACTIVE` / `HUMAN_ACTIVE_MID_SEQUENCE` /
    `PRESENCE_UNKNOWN`, `PACING_WAIT`, `CHALLENGE_DETECTED`,
    `ELEMENT_NOT_FOUND`, and validation errors (`TEXT_REQUIRED`,
    `ELEMENT_REF_INVALID`, `WINDOW_ID_REQUIRED`, `SNAPSHOT_UNAVAILABLE`) —
    reported `NOT_APPLIED` with certainty that nothing was sent, or any other
    dispatch-phase failure (`CLI_ERROR`, `FOREGROUND_REQUIRED`, unparseable
    CLI output, `DISPATCH_TIMEOUT`, `DISPATCH_UNAVAILABLE`), reported
    `EFFECT_UNKNOWN`: the clipboard may hold the caller text and the paste
    chord may have been delivered, so the receipt carries
    `"clipboard_state": "unknown"` and nothing is retried.
  - **Honest automation.** This layer performs ordinary, visible automation.
    It never imitates or disguises itself as a human: no randomized or
    human-like motion/timing, no fingerprint/user-agent/viewport changes are
    ever added to any dispatch (`FORBIDDEN_DISGUISE_FLAGS`, asserted by
    test). Pacing and presence gates are safety properties, never obstacles
    to route around.

## Run

```sh
python3 tools/mmos_computer_use/server.py
```

Startup resolves the runtime descriptor as
`MMOS_CU_RUNTIME` > `runtime.json` > `runtime.json.dev`, verifies the binary
pin, and serves MCP over stdio (newline-delimited JSON-RPC 2.0:
`initialize`, `ping`, `tools/list`, `tools/call`).

### Environment

| Variable                   | Meaning                                        |
|----------------------------|------------------------------------------------|
| `MMOS_CU_RUNTIME`          | runtime.json path override                     |
| `MMOS_CU_STATE_DIR`        | lease + pacing directory (default `<here>/state/`) |
| `MMOS_CU_SCRATCH`          | caller scratch dir; only place `keep_path` may write |
| `MMOS_CU_PRESENCE_MIN_IDLE`| human-idle threshold seconds (default 180)     |
| `MMOS_CU_PACING_SECONDS`   | min interval between slice paste/send sequences on one window (default 180) |
| `MMOS_CU_DENY`             | deny.json path override                        |
| `MMOS_CU_VISION_MODEL`     | vision model (default `minimax-m3.1-flash`)    |
| `ANTHROPIC_BASE_URL`       | vision endpoint base URL                       |
| `ANTHROPIC_AUTH_TOKEN`     | vision token, read at call time only           |

runtime.json (schema `mmos.computer_use.runtime/v1`) additionally accepts the
optional keys `presence_min_idle_seconds`, `pacing_seconds`,
`paste_focus_timeout_ms`, `paste_restore_delay_ms` and
`challenge_patterns_extra` (list of extra case-insensitive challenge
patterns); a wrong-typed value refuses startup.

## Registration (MCP client config)

```json
{
  "mcpServers": {
    "mmos_computer_use": {
      "command": "/usr/bin/python3",
      "args": ["tools/mmos_computer_use/server.py"]
    }
  }
}
```

## Tool actions → peekaboo commands

All invocations additionally receive `--input-strategy <mode> --no-remote`;
`--bridge-socket` is never passed.

Every act is preceded by its own `see --window-id N --json` (the observation
that yields `snapshot_id`, `ui_elements[]` and `coordinate_context`), and the
act dispatch itself carries `--snapshot <id>` and **no** `--app`/`--pid`/
`--window-id` and **no** `--foreground` unless `allow_foreground: true` was
explicitly passed and both gates passed. Slice ops follow the same
observe-then-dispatch shape but add `--foreground` directly to their single
dispatch (they are foreground-class by design); `slice_paste`'s paste
dispatch additionally targets `--app/--window-id` per peekaboo's paste
interface and carries no `--input-strategy`.

| MCP action        | peekaboo command                                                                  |
|-------------------|------------------------------------------------------------------------------------|
| `apps`            | `app list --json` (+ `window list --app <name> --json` per non-denied app)         |
| `windows(app)`    | `window list --app <app> --json`                                                    |
| `inspect(window_id)` | `see --window-id N --json --tree --no-screenshot` (AX tree, bounded to 400 lines) |
| `capture(window_id, ocr)` | `see --window-id N --json --path <staging>/window.png [--ocr]` (staging dir deleted in `finally`) |
| `press(window_id, element_ref)` | `see --window-id N --json` then `action AXPress --on <elem> --snapshot <id> --json` |
| `set_text(window_id, element_ref, text)` | `see --window-id N --json` then `set-value --value <text> --on <elem> --snapshot <id> --json` (direct AX value; never typing, never clipboard) |
| `keys(window_id, chord)` | `see --window-id N --json` then `press <chord> --snapshot <id> --json` (single chord only, from the navigation/editing allowlist — return, escape, tab, space, delete, forwarddelete, home, end, pageup, pagedown, arrows — plus shift+arrow; system-global chords like `cmd+space`/`cmd+tab` and ALL cmd/ctrl/option modifier chords are refused with `CHORD_NOT_ALLOWED`) |
| `scroll(window_id, direction, amount, element_ref?)` | `see --window-id N --json` then `scroll --direction D --amount K --snapshot <id> [--on <scrollable-elem>] --json` |
| `pointer_click(window_id, element_ref? \| x, y)` | element form: `see` then `click --snapshot <id> --on <elem> --json`. Coordinate form (last resort): bounds validated from the snapshot's `coordinate_context`, then `click --window-id N --at x,y --snapshot <id> --json` — `--window-id` is kept only here because peekaboo treats `--at` as global without a window target |
| `slice_front(app, window_id \| title)` | deny gate on the app, window resolved by id or unique case-insensitive title substring, then `see --window-id N --json` and ONE `action AXRaise --snapshot <id> [--on <window-elem>] --foreground --json`; the receipt observes the window's title + window_id after raising |
| `slice_click(window_id, element_ref \| x, y)` | `see` then ONE `click --snapshot <id> --on <elem> --foreground --json` (element form) or `click --window-id N --at x,y --snapshot <id> --foreground --json` (coordinate last resort) |
| `slice_paste(window_id, text, element_ref?)` | optional focus: `click --on <field> --foreground`; then ONE `paste --text <text> --app <app> --window-id N --json` (sets clipboard, delivers the paste chord, restores the previous clipboard — never typing, no `--input-strategy`); confirm reads the target field's AX value back via a fresh `see` (`paste_confirmed`/`restored` in the receipt) |
| `slice_send(window_id, element_ref)` | challenge scan of the window's AX text (+ OCR if present) BEFORE dispatch; then ONE `click --snapshot <id> --on <send-elem> --foreground --json`; a challenge match is a terminal `CHALLENGE_DETECTED` refusal with zero dispatches. `slice_click` and `slice_paste` run the same scan before their input-delivering dispatch |
| `slice_look(window_id, question?)` | `see --tree --no-screenshot` + `see --path <staging>` → accessibility text + capture; the vision relay is included when configured, accessibility text alone is acceptable when it is not |
| `vision_ask(window_id, question)` | `see --tree --no-screenshot` + `see --path <staging>` then in-memory HTTP vision call |
| `lease_*` / `presence` | no peekaboo call (file lease / `ioreg -c IOHIDSystem`)                         |

Verified live 2026-11-11 against Peekaboo 4.2.2 on a real window: the
`--snapshot` form succeeded with `actionName AXSetValue`, executed in the
background with the frontmost app unchanged, while the older `--window-id`
form failed with `CAPTURE_FAILED` (it tries its own capture). Window-chrome
elements (e.g. a close button) may still refuse background delivery; that is
reported as `FOREGROUND_REQUIRED`, never silently escalated.

## Why the CLI surface (not `peekaboo mcp serve`)

`peekaboo --help`, per-subcommand `--help` and `peekaboo tools --json`
(verified 2026-11-11, Peekaboo 4.2.2) show that app enumeration, per-app
window listing, exact-window AX tree (`see --window-id N --tree
--no-screenshot`), exact-window capture (`see --window-id N --path`),
named AX actions (`action`), direct AX value set (`set-value`), chords
(`press`), scroll and window-relative clicks (`click --at`) are all reachable
through plain CLI flags with `--json` output. The documented fallback —
spawning `peekaboo mcp serve` and speaking MCP to it — was therefore not
needed. (A vendored Peekaboo 4.9.8 binary exists elsewhere on this machine as
a read-only reference only; it is never executed and no path in code points
at it.)

## Tests

```sh
python3 -m unittest tests.test_mmos_bcu_computer_use -v
```

(or `python3 -m unittest tests/test_mmos_bcu_computer_use.py -v`). The tests
are pure unit tests: no screen access, no real peekaboo interaction, no
network beyond an in-process fake HTTP server. The adapter is exercised
against a fake peekaboo shell script in a temp dir (asserting `--no-remote`
is always passed, the SHA-256 pin is enforced, and dispatch call counts stay
at exactly one — the no-retry property).

## Known gaps / open questions

- `set-value` is rejected by elements that do not expose a settable AX value;
  there is no fallback typing path by design.
- `AXPress` on in-window buttons is expected to work in the background but was
  not yet observed live (only a window-chrome close button was tested, and it
  refused). A refusal surfaces as `FOREGROUND_REQUIRED`; the caller may then
  opt in with `allow_foreground: true`.
- `scroll` uses background wheel delivery; if a target app ignores it in
  practice, the observed readback will show it — there is no retry.
- Window identity for the deny gate is parsed from `see --json` metadata; a
  window whose owning application cannot be resolved refuses ACT/SEE on it
  (`WINDOW_IDENTITY_UNKNOWN`) rather than guessing.
- OCR text extraction is tolerant (it walks the `see` JSON for `ocr`/`text`
  fields); exact field shape may differ slightly across peekaboo versions.
- `slice_front` targets the Window-role element from the fresh snapshot; if
  an app's `see` payload exposes no Window element, the AXRaise dispatch
  falls back to snapshot-only (no `--on`) — unverified live against 4.2.2.
- `slice_paste`'s confirm reads the field's AX `value`; fields that do not
  expose their content as an AX value will report `paste_confirmed: false`
  even when the paste visually landed.
- `slice_paste`/`slice_send` pacing is counted from the dispatch attempt
  (conservative): a dispatch that times out still consumes the pacing
  window, because its effect is unknown and must not be retried quickly.
- Text passed to `paste --text` and `set-value --value` is visible in the
  child process argv to any same-machine observer — same-machine trust
  domain, accepted for this supervised local tool.
- During `slice_paste` the caller's text transits the system clipboard
  (peekaboo restores the previous clipboard afterwards; `restored` in the
  receipt reports whether that was verified). If the paste process dies
  mid-flight, the clipboard may still hold the caller text — the timeout
  receipt flags `clipboard_state: "unknown"`.
- Presence has a TOCTOU window: the human-idle check precedes each step but
  the human may become active between the check and the dispatch; slices
  re-check between steps to narrow, not eliminate, the window.
- A capture staging directory under /tmp can be left behind if the process
  is SIGKILLed between creation and the `finally` cleanup.
- `keep_path` validation and the subsequent write are a TOCTOU pair
  (symlink swap between the realpath check and the write is not excluded).
- General-op pacing (non-slice ACT ops) has no per-window interval yet;
  pacing covers slice paste/send only. Follow-up candidate.
- The challenge scan is AX-text-only on peekaboo 4.2.2 (no `--ocr` flag
  exists on `see`): a pixel-rendered challenge (image CAPTCHA) is NOT
  machine-detected — callers must `slice_look` the window and inspect the
  capture themselves before any send.
- The peekaboo engine persists its own snapshot directory
  (`~/.peekaboo/snapshots`) per `see` call — an engine property outside this
  layer's cleanup; the deny gating still prevents window content returning
  to callers for denied windows.
- Pacing is keyed on window ids: window churn (close + reopen) resets the
  interval for the new id.
- The advisory lease is spoofable by a same-machine process that writes the
  expected owner string — the trust domain is the single machine, not
  cross-machine security.
