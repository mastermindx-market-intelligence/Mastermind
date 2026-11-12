# mmos_computer_use — supervised macOS computer-use MCP server

A zero-dependency (Python 3 stdlib only, runs on `/usr/bin/python3`) stdio
MCP server that gives a session **window-scoped** computer use on macOS by
wrapping the [Peekaboo](https://github.com/steipete/peekaboo) CLI.

**Interface version 0.3.0 — breaking change.** Every act must now present the
`lease_nonce` returned by `lease_acquire`; `keep_path` is gone and no reply
ever contains image bytes.

Design summary:

- **One MCP tool.** The server exposes exactly one tool, `mmos_computer_use`;
  its single `action` argument selects the operation, so registration stays
  one tool regardless of how many operations are supported.
- **Window-scoped only.** Every SEE/ACT/VISION operation names exactly one
  `window_id` (or, for the pure enumeration ops `apps` / `windows`, one app).
  No screen-wide, display-wide or all-windows parameter exists anywhere in
  the tool schema.
- **Deny list first.** Credential managers (Keychain Access, 1Password,
  Bitwarden, Dashlane, Proton Pass, Keeper, Enpass, Strongbox, KeePassXC,
  LastPass), password surfaces (Passwords, SecurityAgent), Settings (System
  Settings, System Preferences), terminal emulators (Terminal, iTerm, iTerm2)
  and Script Editor are deny-listed (an arbitrary command surface is not a
  document window). The built-in defaults ship in `DEFAULT_DENY` and in
  `deny.json`; a configured file is **unioned** with the defaults, never a
  replacement — an empty file means defaults only. `title_regexes`
  (`password`, `passkey`, `saved passwords`, `settings/passwords`,
  case-insensitive) are matched against every window title the layer reads,
  including the `windows` op and the `slice_front` target, so a credential
  field inside an otherwise innocuous app is refused too. Every operation
  that targets a window or an app checks the list first; a match refuses the
  operation (`DENY_LISTED`) before any content is read. App names and bundle
  ids are compared after Unicode NFC normalization and casefolding. The
  `windows` op additionally denies every resolved app identity present in the
  CLI result (the whole op refuses, zero results) and drops entries whose
  resolved app name is not exactly the requested app.
  **Coordinate-click frontmost gate (H6).** Before a coordinate
  `pointer_click`/`slice_click` (no `element_ref`), the target window must
  be the **globally frontmost window** at click time: `window list` reports
  per-window `is_frontmost`, and a window with anything above it in z-order
  reports `is_frontmost:false` (real capture:
  `tests/fixtures/peekaboo/window_list_fixture.json`), so `is_frontmost:true`
  proves no window can cover the point. Otherwise the click is refused
  (`WINDOW_NOT_FRONTMOST` with the observed index; a vanished window is
  `WINDOW_GONE`; a list row without the field fails closed). Element-targeted
  clicks are unaffected — the element is pinned through the snapshot, not
  the screen point.
  **Coordinate-click overlay gate.** Additionally, the layer lists the
  visible apps; if ANY deny-listed app currently has an on-screen window, the
  click is refused (`DENY_OVERLAY`, naming the app) because that window may
  float over the coordinate. Unreadable evidence fails closed
  (`DENY_OVERLAY_UNVERIFIED`). Element-targeted clicks are unaffected.
- **Lease + presence before any ACT.** Acts (AX press, set-value text,
  keyboard chord, scroll, last-resort pointer click) and slice ops require
  1. a held lease (`lease_acquire`, file-backed, single holder, TTL renewed
     on every act). Each acquisition returns a random **nonce**; EVERY act
     must carry `lease_nonce` with that value (`LEASE_NONCE_INVALID` on a
     missing or wrong nonce). `lease_status` reports only
     `sha256(owner)[:12]` (`owner_redacted: true`); acquire/release still
     require the exact owner string. All lease mutations (acquire, renew,
     release) run inside one `O_CREAT|O_EXCL` critical section; a lock left
     by a dead pid or older than 60 s is recovered, any other contention is
     the typed `LEASE_CONTENDED` (never `INTERNAL`). Renewal preserves the
     acquired TTL (it never silently resets to the default).
  2. a human-idle screen (`ioreg -c IOHIDSystem` HIDIdleTime >= threshold,
     default **180 s** for ALL acts, env `MMOS_CU_PRESENCE_MIN_IDLE` or
     runtime.json `presence_min_idle_seconds`; both sources UNCONDITIONALLY
     refuse values below the 180 s default — there is no test-mode flag), and
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
  no retry loop anywhere. **After a dispatch has started, any failure that is
  not a proven pre-dispatch refusal is `EFFECT_UNKNOWN` for every act op**
  (press, set_text, keys, scroll, pointer_click, slice_front, slice_click,
  slice_send, slice_paste), because the event may have landed even when the
  CLI failed. Pre-dispatch refusal codes (deny, lease, presence, pacing,
  challenge, validation) remain `NOT_APPLIED`. A timeout or unreadable
  outcome is `EFFECT_UNKNOWN` and left for human/next-session reconciliation.
  Slice receipts carry the completed `steps`; if persisting `pacing.json` /
  `lease.json` fails AFTER a dispatched act, the act receipt is still returned
  with `state_write: "failed"` (never `REFUSED`/`INTERNAL`).
- **No image leaves the layer.** `capture` returns metadata (`window_id`,
  byte count, `image_returned: false`) plus optional OCR text;
  `slice_look` / `vision_ask` return the vision model's TEXT answer and
  `elements`, never the PNG. The image exists only in memory / a staging file
  deleted in `finally`. There is no `keep_path` parameter.
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
  with headers — never curl/argv) to the Anthropic-protocol vision endpoint
  with the token read from `ANTHROPIC_AUTH_TOKEN` **at call time only**, and
  returns `{answer, elements, model}` where elements carry normalized
  0–1000 image coordinates. **The endpoint is pinned in code to the local
  router** (`DEFAULT_VISION_BASE_URL`, BCU R3 L6); the sha-pinned runtime
  descriptor may name it explicitly via a loopback-only `vision_base_url`
  key (any other value refuses startup with `RUNTIME_VISION_BASE_URL`). The
  environment never supplies the endpoint: an `ANTHROPIC_BASE_URL` that
  differs from the pin refuses `VISION_ENDPOINT_INSECURE` before any
  request — **even another loopback port**, so a session that controls the
  server env cannot redirect captures to its own listener. The endpoint
  must in any case be loopback (`localhost` / `127.0.0.1` / `::1`, http or
  https); any other host is refused `VISION_ENDPOINT_INSECURE` even with
  https. Prompt text is capped:
  `question` ≤ 2000 chars (`QUESTION_TOO_LONG`), caller `element_hints` ≤ 20
  entries, 120 chars each, 1200 chars total (`HINTS_TOO_LONG`); over-limit
  input is refused before any capture or network dispatch. Image
  bytes/base64 never appear in logs, errors, replies or persistent files;
  staging directories are deleted in `finally`.
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
    nothing retries). If the act has already completed and the person becomes
    active only before the CONFIRM readback, the receipt is `APPLIED` with
    `confirm_skipped: "HUMAN_ACTIVE"` (or `EFFECT_UNKNOWN`) — never
    `NOT_APPLIED`.
  - **Shared pre-act gate.** One function runs the challenge scan and the
    pacing check for every act that can change a page or send: `keys`,
    `set_text`, `press`, `pointer_click`, `slice_click`, `slice_paste`,
    `slice_send`. `keys` is paced at minimum for `enter`/`return`; every
    press/click/set_text is paced too. The check runs AFTER the lease check,
    so an unleased caller gets `LEASE_NOT_HELD` and cannot read pacing state.
  - **Pacing identity.** A minimum interval (default **180 s**, env
    `MMOS_CU_PACING_SECONDS` or runtime.json `pacing_seconds`; env values
    below the default UNCONDITIONALLY refuse at startup — no test-mode flag)
    between two input-delivering acts. The key is `pid:<owning
    pid>|window:<exact window id>` — never the app name or title, so a
    title change (tab switch, new message) cannot reset the interval, and
    the pid binds the record to one process, so a window id recycled by
    another app cannot inherit (or escape) it. The pid comes from ONE
    resolver (`target_receipt_pid`): the act's own fresh snapshot carries
    peekaboo's `target_receipt` (falling back to
    `target_application_info.pid`); no extra window-list read is made, and
    paste targeting uses the same resolver. Too soon → `NOT_APPLIED` /
    `PACING_WAIT` with the seconds remaining. The interval is measured on a
    monotonic clock where available, so a wall-clock jump cannot shorten
    or extend it.
  - **Challenge stop.** Before ANY input-delivering dispatch, the shared gate
    scans the window's AX text (and OCR text if present) for challenge
    patterns — captcha, are you a robot, verify you are human, sign in, log
    in, rate limit, too many requests, unusual activity, access denied
    (case-insensitive; extendable via runtime.json
    `challenge_patterns_extra`). A match is a terminal `NOT_APPLIED` /
    `CHALLENGE_DETECTED` with a bounded quote of what was seen; zero
    dispatches. The layer stops and reports; it does not retry.
    `slice_front` raises without delivering input and keeps no scan.
  - **Dispatch failure truth table (all acts).** A failure is either a
    provably pre-dispatch refusal — `WINDOW_IDENTITY_UNKNOWN`, `DENY_LISTED`,
    `DENY_OVERLAY`, `DENY_OVERLAY_UNVERIFIED`, `LEASE_NOT_HELD`,
    `LEASE_NONCE_INVALID`, `LEASE_CONTENDED`, `HUMAN_ACTIVE` /
    `HUMAN_ACTIVE_MID_SEQUENCE` / `PRESENCE_UNKNOWN`, `PACING_WAIT`,
    `CHALLENGE_DETECTED`, `ELEMENT_NOT_FOUND`, `WINDOW_APP_MISMATCH`,
    `FOREGROUND_REQUIRED` from the explicit background attempt, and
    validation errors — reported `NOT_APPLIED` with certainty that nothing
    was sent, or any other dispatch-phase failure (`CLI_ERROR`, unparseable
    CLI output, `DISPATCH_TIMEOUT`, `DISPATCH_UNAVAILABLE`), reported
    `EFFECT_UNKNOWN`: for `slice_paste` the clipboard may hold the caller
    text and the paste chord may have been delivered, so that receipt also
    carries `"clipboard_state": "unknown"`. Nothing is retried.
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
| `MMOS_CU_RUNTIME`          | runtime.json path override (must be inside this tool's folder) |
| `MMOS_CU_STATE_DIR`        | **REMOVED (BCU R3 M5) — ignored entirely.** Lease + pacing state lives in the fixed 0700 folder `~/.mastermind/mmos_computer_use`, outside the checkout; only the `--state-dir` launch argument (harness path) redirects it |
| `MMOS_CU_PRESENCE_MIN_IDLE`| human-idle threshold seconds; default 180, values below it refuse UNCONDITIONALLY |
| `MMOS_CU_PACING_SECONDS`   | minimum interval between input-delivering acts; default 180, values below it refuse UNCONDITIONALLY |
| `MMOS_CU_DENY`             | deny.json path override (must be inside this tool's folder) |
| `MMOS_CU_VISION_MODEL`     | vision model (default `minimax-m3.1-flash`)    |
| `ANTHROPIC_BASE_URL`       | **NOT an endpoint source** (BCU R3 L6): the endpoint is pinned in code to the router (`DEFAULT_VISION_BASE_URL`, optionally named by the runtime descriptor's loopback-only `vision_base_url` key). A set value that differs from the pin refuses every vision call `VISION_ENDPOINT_INSECURE` — even another loopback port |
| `ANTHROPIC_AUTH_TOKEN`     | vision token, read at call time only           |

`MMOS_CU_DENY` and `MMOS_CU_RUNTIME` are layer-scoped: they must resolve
inside `tools/mmos_computer_use/` (or a subdirectory). Anything outside
refuses at startup UNCONDITIONALLY, so an environment change cannot
silently move the deny list or pinned binary out from under the layer. The
lease + pacing state is not env-configurable at all (BCU R3 M5): it lives
in the fixed **0700** folder `~/.mastermind/mmos_computer_use`, OUTSIDE the
checkout, so a `git clean` or branch switch can never wipe it and a
worktree copy can never fork it; the former `MMOS_CU_STATE_DIR` variable is
ignored. A harness subprocess that needs scratch paths passes them as
server launch ARGUMENTS (`--state-dir`, `--runtime`, `--deny`), never as
environment variables. Known limit of a same-uid layer (runbook): a session
with a shell can still read/write that folder, and a missing pacing file
reads as "no record".

runtime.json (schema `mmos.computer_use.runtime/v1`) additionally accepts the
optional keys `presence_min_idle_seconds`, `pacing_seconds`,
`paste_focus_timeout_ms`, `paste_restore_delay_ms` and
`challenge_patterns_extra` (list of extra case-insensitive challenge
patterns); a wrong-typed value refuses startup. The two threshold keys obey
the same unconditional 180 s floor as their environment counterparts: a
runtime.json value below the default refuses startup
(`RUNTIME_PRESENCE_MIN_IDLE_SECONDS` / `RUNTIME_PACING_SECONDS`).

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
| `windows(app)`    | `window list --app=<app> --json` (title regexes applied to every returned window) |
| `inspect(window_id)` | `see --window-id N --json --tree --no-screenshot` (AX tree, bounded to 400 lines) |
| `capture(window_id, ocr)` | `see --window-id N --json --path <staging>/window.png [--ocr]` (staging dir deleted in `finally`; reply is metadata + optional OCR text only) |
| `press(window_id, element_ref)` | `see --window-id N --json` then `action AXPress --on <elem> --snapshot <id> --json` |
| `set_text(window_id, element_ref, text)` | `see --window-id N --json` then `set-value --value=<text> --on <elem> --snapshot <id> --json` (equal-sign form so a leading `-` is never a flag; direct AX value, never typing, never clipboard) |
| `keys(window_id, chord)` | `see --window-id N --json` then `press <chord> --snapshot <id> --json` (single chord only, from the navigation/editing allowlist — return, escape, tab, space, delete, forwarddelete, home, end, pageup, pagedown, arrows — plus shift+arrow; system-global chords like `cmd+space`/`cmd+tab` and ALL cmd/ctrl/option modifier chords are refused with `CHORD_NOT_ALLOWED`) |
| `scroll(window_id, direction, amount, element_ref?)` | `see --window-id N --json` then `scroll --direction D --amount K --snapshot <id> [--on <scrollable-elem>] --json` |
| `pointer_click(window_id, element_ref? \| x, y)` | element form: `see` then `click --snapshot <id> --on <elem> --json`. Coordinate form (last resort): bounds validated from the snapshot's `coordinate_context`, then `click --window-id N --at x,y --snapshot <id> --json` — `--window-id` is kept only here because peekaboo treats `--at` as global without a window target |
| `slice_front(app, window_id \| title)` | deny gate on the app, window resolved by id or unique case-insensitive title substring; a given `window_id` must appear in that app's window list (`WINDOW_APP_MISMATCH` otherwise), and no window of the app may carry a deny-listed title. Then `see --window-id N --json` and ONE `action AXRaise --snapshot <id> [--on <window-elem>] --foreground --json`; the receipt observes the window's title + window_id after raising (or reports `confirm_skipped` if a human became active) |
| `slice_click(window_id, element_ref \| x, y)` | `see` then ONE `click --snapshot <id> --on <elem> --foreground --json` (element form) or `click --window-id N --at x,y --snapshot <id> --foreground --json` (coordinate last resort, deny-overlay gated) |
| `slice_paste(window_id, text, element_ref?)` | optional focus: `click --on <field> --foreground`; then ONE `paste --text=<text> --app=<app> --window-id N --json` (equal-sign forms; sets clipboard, delivers the paste chord, restores the previous clipboard — never typing, no `--input-strategy`); confirm reads the target field's AX value back via a fresh `see` (`paste_confirmed`; `restored` comes only from the documented top-level `clipboard_restored` receipt field) |
| `slice_send(window_id, element_ref)` | challenge scan of the window's AX text (+ OCR if present) BEFORE dispatch; then ONE `click --snapshot <id> --on <send-elem> --foreground --json`; a challenge match is a terminal `CHALLENGE_DETECTED` refusal with zero dispatches. `slice_click` and `slice_paste` run the same scan before their input-delivering dispatch |
| `slice_look(window_id, question?)` | `see --tree --no-screenshot` + `see --path <staging>` → accessibility text (and the vision model's TEXT answer when a loopback relay is configured); the PNG itself is never returned |
| `vision_ask(window_id, question)` | `see --tree --no-screenshot` + `see --path <staging>` then an in-memory HTTP call to a LOOPBACK vision endpoint; returns text + elements only |
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
python3 -m unittest tests/test_mmos_bcu_computer_use.py tests/test_mmos_bcu_cli.py
/usr/bin/python3 -m unittest tests/test_mmos_bcu_computer_use.py tests/test_mmos_bcu_cli.py
```

The tests are pure unit tests: no screen access, no real peekaboo interaction,
no network beyond an in-process fake HTTP server. The adapter is exercised
against a fake peekaboo shell script in a temp dir (asserting `--no-remote`
is always passed, the SHA-256 pin is enforced, and dispatch call counts stay
at exactly one — the no-retry property). When
`FAKE_PEEKABOO_FIXTURES=<dir>` is set, the fake replays the **real** captures
in `tests/fixtures/peekaboo/*.json` (see that directory's README); without
the directory it falls back to the inline fakes. Both interpreters are
supported (stdlib only).

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
- Pacing is counted from the dispatch attempt (conservative): a dispatch
  that times out still consumes the pacing window, because its effect is
  unknown and must not be retried quickly.
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
- The coordinate-click deny-overlay gate checks whether a deny-listed app
  has an on-screen window, not its live z-order over the click point; live
  z-order proof is follow-up work.
- The challenge scan is AX-text-only on peekaboo 4.2.2 (no `--ocr` flag
  exists on `see`): a pixel-rendered challenge (image CAPTCHA) is NOT
  machine-detected — callers must `slice_look` the window and inspect the
  returned accessibility/vision text before any send.
- The peekaboo engine persists its own snapshot directory
  (`~/.peekaboo/snapshots`) per `see` call — an engine property outside this
  layer's cleanup; the deny gating still prevents window content returning
  to callers for denied windows.
- The advisory lease is spoofable by a same-machine process that writes the
  expected owner string — the trust domain is the single machine, not
  cross-machine security. The per-acquisition nonce raises the bar against
  an accidental second holder, not against a hostile same-machine process.
