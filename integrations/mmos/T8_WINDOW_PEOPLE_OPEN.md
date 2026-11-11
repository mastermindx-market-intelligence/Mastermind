# T8 — the window a person opens (runbook for the principal)

Lane T8 of program plan V4 (branch `t3/mmos-v4-t8`), with the panel-repair
round of lane T8b on top (branch `t3/mmos-v4-t8b`; what changed and why:
`integrations/mmos/T8B_PANEL_REPAIRS.md`). The goal: a person double-clicks
the Mastermind OS app and it opens on the Team project of its T3 server,
signed in, with no login step — the first time and after the session
expires. This file is the principal's switch-over runbook for the real team
server on `127.0.0.1:3780`. The lanes proved everything on a dev bundle
(`com.mastermind.os.dev.t8`) against private dev T3 servers; the team server
was never touched by the lanes.

How the app finds its server, in order: the `MM_SHELL_URL_FILE` environment
variable, then `MM_SHELL_URL`, then a fixed per-user config file. A person
launching from Finder or the Dock has no environment, so the fixed config is
what serves them:

| Bundle | Identifier | Config directory |
|---|---|---|
| Release (installed) | `com.mastermind.os` | `~/.mastermind/window` |
| Dev | `com.mastermind.os.dev` | `~/.mastermind/mmos_dev/window-dev` |
| T8/T8b proof | `com.mastermind.os.dev.t8` | `~/.mastermind/mmos_dev/window-dev-t8` |

Each directory holds two 0600 files: `shell-url` (one line: the loopback
thread address, never a pairing token) and `pair-helper` (one line: absolute
path to an executable that mints a fresh pairing URL — for a dev server,
a wrapper script; see below). No file means today's ordinary window with no
error. When the server answers with its pairing page — first run, or an
expired or cleared session cookie — the window's pairing watchdog (one per
app process, started only when the config names a helper) runs the helper,
loads the minted one-time address, and lands signed-in on the configured
thread. After a verified pairing the watchdog re-arms: a *later* `/pair`
arrival in the same launch (session revoked or expired mid-run) re-pairs
the same way, with no relaunch. It mints at most 3 addresses in any
10 minutes; past that it shows one plain rate-limit page (log record
`PAIRING.FAILED.rate_limited`) and mints nothing more until the window has
passed. After any pairing failure the window shows its one-sentence failure
page and the watchdog re-arms when the window is next seen on the
configured origin; `View > Go to Server` takes the window back to the
configured address at any time. The helper reuses `t3 pair`; its only
authority is being the macOS user who owns the server home's files. Nothing
is admitted over loopback TCP or a request header, and the token never
enters argv, a log, another process's environment, or evidence.

Only one instance of the app runs: a second launch focuses the first
window (rebuilding it like a Dock reopen if it was closed) and starts
nothing. The shell window also carries a navigation allowlist: exactly the
configured origin (scheme, host and port), the app's own inert blank page
and its failure page load in the window; any other http/https address is
refused in the window and opened in the person's default browser, and
everything else is refused and logged. The default-browser opens are
bounded by one throttle, a token bucket — three opens land back to back,
then one per minute; a sustained flood never re-arms the burst, and an
open past the cap is dropped (and logged), never queued — so a page that
keeps firing outside addresses cannot flood the person's browser with
tabs.

Because the window clears the helper's environment, `WINDOW_PAIR_T3_BIN` /
`WINDOW_PAIR_T3_HOME` cannot aim a config-named helper at a dev server. The
supported way is a wrapper script that exports those two variables and
execs `window_pair_helper.sh`, named in the config via
`window_config.sh write --pair-helper <wrapper>`.

## 1. Build the release bundle from this branch

Prerequisites, all real: `node_modules` installed in `app/mastermind_os`
(`npm ci` — the tauri CLI is `node_modules/.bin/tauri`), the
`/Volumes/Mastermind` build volume mounted (the command below puts both the
cargo cache and the bundle on it; unmounted, the build fails rather than
falling back to the internal disk), and whatever code signing this machine
does by default — an unconfigured Mac ad-hoc signs, which is enough to run
locally; a distribution certificate is only needed for handing the bundle
to another Mac.

```sh
git -C <your checkout of t3/mmos-v4-t8b> rev-parse HEAD   # record it
cd <your checkout>/app/mastermind_os
MM_SOURCE_REVISION=$(git rev-parse HEAD) \
MM_BUILD_IDENTITY=$(whoami)-release \
CARGO_TARGET_DIR=/Volumes/Mastermind/build-cache/t8-release-cargo-target \
  node_modules/.bin/tauri build
```

The bundle lands at
`/Volumes/Mastermind/build-cache/t8-release-cargo-target/release/bundle/macos/Mastermind OS.app`
with identifier `com.mastermind.os`, so it reads `~/.mastermind/window`. Use
a target directory of your own; never `t3-t1w-cargo-target` (another lane's)
or `t8b-cargo-target` (this lane's debug artifacts).

Honesty note: this lane proved the code on the dev/t8 bundle, not on a
release build. The release mapping itself (`com.mastermind.os` reading
`~/.mastermind/window`) is covered by the loader's unit tests in
`shell_mode.rs` and the tool mapping tests in
`tests/test_mmos_window_config.py`. If the release profile trips a signing
or notarization gate your machine does not have credentials for, that is a
build-config question, not a regression in this lane.

## 2. Write the config that points it at the team server

Pick the thread the window should open on. The roster file is read-only for
you (never send a request to port 3780), and it prints as instance id and
name only — the addresses stay out of your terminal scrollback. To get the
one address you are about to write into the config, print it for that one
teammate:

```sh
sh tools/mmos_team_server/open_team_window.sh --list   # instance ids and names
/usr/bin/python3 -I -c 'import json,sys
ts = json.load(open(sys.argv[1]))["teammates"]
print(next(t["url"] for t in ts if t["instanceId"] == sys.argv[2]))' \
  "$HOME/.mastermind/t3-team/run/team_urls.json" <instance-id>
```

Put the pairing helper somewhere stable (a checkout path dies with the
worktree). It needs no environment overrides — its defaults are exactly the
team server's own `t3` and home. Create the directory first, and keep it
0700: the app's helper trust walk requires no group/other write on every
directory the resolved helper path passes through:

```sh
mkdir -p ~/.mastermind/t3-team-server/bin
chmod 700 ~/.mastermind/t3-team-server/bin
cp tools/mmos_team_server/window_pair_helper.sh \
   ~/.mastermind/t3-team-server/bin/window-pair-helper.sh
chmod 700 ~/.mastermind/t3-team-server/bin/window-pair-helper.sh
```

Write the config (release bundle, thread address of your chosen teammate):

```sh
sh tools/mmos_team_server/window_config.sh write --bundle release \
  --url http://127.0.0.1:3780/<env>/<thread> \
  --pair-helper "$HOME/.mastermind/t3-team-server/bin/window-pair-helper.sh"
```

The tool refuses non-loopback, https, bare-origin, fragment-carrying,
`localhost`-spelled and `/pair`-path URLs (the server root, `/pair` and
anything under it belong to the pairing flow, never to a saved config), and
non-executable, relative, symlinked or group-writable helper paths. A
`write` without `--pair-helper` **removes** an existing helper (pass
`--keep-pair-helper` to keep one), so an edit meant to withdraw minting
actually withdraws it. Files are staged in 0600 temporaries under `umask
077` (a trap removes them on any exit) and committed helper-first into the
0700 directory.

## 3. Check it

Quit any running copy of Mastermind OS first (⌘Q, or Activity Monitor):
the single-instance plugin makes a second launch focus the existing window
and start nothing, so an old running copy would mask the new bundle
entirely.

Verify the config with the same judge the app itself runs — it prints one
line per item (`shell-url`, `pair-helper`, `config-dir`), never an address,
and exits non-zero on any refusal:

```sh
sh tools/mmos_team_server/window_config.sh check --bundle release \
  --app "/Volumes/Mastermind/build-cache/t8-release-cargo-target/release/bundle/macos/Mastermind OS.app/Contents/MacOS/mastermind-os"
open "/Volumes/Mastermind/build-cache/t8-release-cargo-target/release/bundle/macos/Mastermind OS.app"
```

Within a few seconds the window should sit on the Team thread you chose,
signed in, with no typing anywhere. Two checks that need no screenshots:

- `grep -c PAIRING.DONE ~/.mastermind/mmos_dev/app.log` increases by one on
  a first open or after cookie expiry (the release bundle logs to the same
  dev root). A failure writes exactly one input-free record like
  `PAIRING.FAILED.helper_output` instead, and the window shows one plain
  sentence asking whoever set up the Mac to re-pair the app.
- Quit and reopen the app: the session cookie is still valid, so no second
  `PAIRING.DONE` appears and the window opens straight on the thread.

To prove expiry the lane's way, delete the bundle's cookie container
(`~/Library/WebKit/com.mastermind.os` for release) and reopen: the window
re-pairs itself once and is signed in again with no typing.

## 4. Go back

```sh
sh tools/mmos_team_server/window_config.sh clear --bundle release   # today's ordinary window
```

`clear` removes exactly the two config files and leaves everything else.
What is left on the Mac afterwards, and how to remove each if you want a
full cleanup:

| Leftover | Where | Remove with |
|---|---|---|
| Helper copy | `~/.mastermind/t3-team-server/bin/window-pair-helper.sh` | `rm` it (the dir is yours to keep or `rmdir`) |
| Config directory | `~/.mastermind/window` — present but empty, still 0700 | `rmdir ~/.mastermind/window` |
| Cookie store | `~/Library/WebKit/com.mastermind.os` and `~/Library/HTTPStorages/com.mastermind.os*` | delete those folders once (also the right move before pointing one bundle at a different server — see §7) |
| The app itself | the running copy, if any, plus the built bundle | quit it (⌘Q) and delete the `.app` |

A cleared config is the pre-T8 behaviour on any bundle: the app never read
the file, so nothing else needs restoring.

## 5. What was proved and what was not

Proved, live, on the dev/t8 bundle against a private dev T3 server
(127.0.0.1:3797), evidence in `~/.mastermind/mmos_evidence/t8-20261110/`:

- First open with no environment and no cookie store: the window read the
  address from its fixed 0600 config, detected the pairing page, minted a
  fresh one-time address through the configured helper, and landed signed-in
  on the Team thread with no typing (`01-first-open`, `PAIRING.DONE`).
- Session-expiry equivalent: the dev bundle's cookie container deleted, the
  app reopened — a second `PAIRING.DONE` and the signed-in thread again with
  no typing (`02-reopen-after-cookie-delete`), re-proved on the final
  binary after the View-menu fix
  (`02-reopen-after-cookie-delete/final-binary/keep-final-binary.png`).
- The View menu items this lane added (Reload, Zoom In/Out, Actual Size,
  Back) are present and registered with their key equivalents on the final
  binary (`03-typing/task4/menus-final-binary.json`); see section 6 for
  which of them were proven to take effect.
- The failure path, live: before the fragment-navigation fix the exchange
  timed out; the window showed the plain one-sentence page and the log
  gained exactly one input-free `PAIRING.FAILED.exchange_timeout` record.
  Re-proved on the final binary with a failing helper: the window's own
  accessibility text is exactly one sentence — "Mastermind OS could not
  sign in to the team server automatically — ask whoever set up this Mac
  to re-pair the app." — and the log grew by exactly one input-free
  `PAIRING.FAILED.helper_exit` record (`04-pair-failure/`, read as text,
  never the pairing page).
- No config = today's ordinary window: with the t8 config cleared, the
  relaunch shows the standard product window ("Sign in to account",
  "Private workspace"), no Team thread and no error
  (`05-no-config/ax-plain-window.json`). Caveat recorded in the ledger:
  the child's cookie-delete step aborted on a zsh glob, so this ran with
  the previous launch's cookie stores — with no config the app never
  consults a server, so cookies cannot change this path.
- Every helper failure shape (missing, non-zero exit, empty, multiline,
  off-origin, remote, hung), the tokenless-page detection rules, the
  watchdog's whole state machine, and token-free logging are unit-tested in
  `shell_pairing.rs` and `tests/test_mmos_window_config.py`.

### T8b — re-proof on the repaired binary (2026-11-11)

The second review panel's findings were fixed on branch `t3/mmos-v4-t8b`
(repairs A–P plus an attack round; see
`integrations/mmos/T8B_PANEL_REPAIRS.md`), and the good path and failure
path were re-proved live on the rebuilt dev bundle against the private
dev T3 server (127.0.0.1:3790). Evidence:
`~/.mastermind/mmos_evidence/t8b-20261111/`.

- The app starts. The first live-proof round of this lane could not even
  launch: the watchdog's URL poll hit wry's nil-URL unwrap before the
  first load committed and the app died at every launch
  (`01-dead-helper/launch3-backtrace.log`). Fixed with a committed-load
  gate keyed to the window generation; the smoke launch then ran the full
  mint→verify cycle (`00-smoke-fixed/`).
- First open pairs with no typing (`PAIRING.DONE`; `02-good-path/`).
- A session revoked mid-launch re-pairs through View > Go to Server in
  the same launch — a second `PAIRING.DONE` ~8 s later, no relaunch
  (`02-good-path/`, steps 8).
- Closing the window exits this single-window app (§6 already records
  this for Close Window); opening the app again pairs again
  (`02-good-path/`, steps 9–10).
- A second launch while the first runs starts nothing: the second process
  exits immediately, exactly one process remains (`02-good-path/`,
  launch3).
- The failure path with a dead helper (`03-dead-helper/*-r2`): exactly
  three helper runs, one input-free `PAIRING.FAILED.helper_exit` record
  per attempt and the one-sentence page each time (View > Back and View >
  Go to Server each re-engage it); past the budget the helper runs zero
  times and one input-free `PAIRING.FAILED.rate_limited` record is
  written. The rate-limit page shows the same sentence as the
  helper-failure page — the log, not the page wording, distinguishes
  them. One more Go to Server after the rate-limited page lands on the
  server's own pairing page (the pre-watchdog baseline behaviour; the
  helper still runs zero times).
- Outside link: pressing a link to `https://example.com/…` inside the
  thread left the window on the thread page and wrote no navigation
  record — the thread page's `target="_blank"` link takes WebKit's
  new-window path, which funnels into the app's own opener arm (the
  default browser did come forward). Since repair round 2 every open path
  is bounded by one opener throttle, a token bucket (three opens back to
  back, then one per minute; a dropped open is logged, never queued).
  Either path leaves the window never loading an outside origin.
- Menus on the repaired binary: View > Reload keeps the signed-in thread
  and adds no pairing record; View > Back from the thread lands on the
  inert blank page; Copy/Paste present and enabled on both the thread and
  failure pages (not pressed); Zoom Out and Actual Size pressed via
  AXPress produced no measured scale change and Actual Size never
  disabled — the §6 zoom rows stand.

Not proved by this lane: the release bundle build and the real team server
on 3780 (forbidden to the lane; that is exactly what sections 1–3 hand
you), a real multi-day session expiry (cookie deletion is the stand-in),
and multi-user Macs (authority is file ownership by the server home's
owner; a second local user gets the plain failure page, which is tested,
but no live second-user run happened).

## 6. Typing and keyboard table

Typing was proven by a `kimi-k3.1-pro` child (three dispatches; two died
on gateway/router errors); keyboard verdicts come from its accessibility
receipts plus one lane keystroke run, all under
`~/.mastermind/mmos_evidence/t8-20261110/03-typing/` (the child's own
narrative: `KEYBOARD_TABLE.md`; final-binary shortcut receipts: `task5/`).

What a person experiences when typing:

- Type a message, press Enter: the reply arrives while writing (exact
  request `T8 typing check one: reply with exactly the word ACK.` →
  exact reply `ACK` in ~2 s). Proven via the child's approved headless
  browser fallback against the signed-in thread; native per-PID typing
  of the message itself was refused by the desktop tooling, and message
  *content* typing into the composer by synthetic keystrokes is not a
  proven native path.
- Send a second message while the first is generating: accepted as a
  *steer*; the second answer arrives but the first answer stops
  mid-sentence and stays incomplete. Two independently completed
  answers from one queued pair is NOT what happens.
- Answer one pending request (a shell-command approval card): NOT
  TESTED. In the dev session shell commands ran without any permission
  card (4.4 s, output visible); the retry set the thread control to
  "Supervised" (projection eventually read `approval-required`) and a
  second identical command still produced no card in 90 s, so there was
  no card to answer.

Keyboard table (menu items added by this lane are marked T8; all other
rows were measured on the shipped menu):

| Action | Verdict | Evidence and limitation |
|---|---|---|
| Copy — ⌘C | does-not-work | Key event delivered to the exact PID with the draft selected; system pasteboard unchanged. Menu item `Edit > Copy` exists, enabled on the thread and failure pages (T8b, not pressed). |
| Paste — ⌘V | does-not-work | Pasteboard set to a known marker; ⌘V left the draft unchanged, marker still on pasteboard. Menu item exists, enabled on the thread and failure pages (T8b, not pressed). |
| Select all — ⌘A | works | Draft range `17,0` → `0,17` after the key (`task4`, `task5` receipts). |
| Undo — ⌘Z | works | Lane keystroke run: draft typed with real per-PID keystrokes, ⌘Z reverted the field to empty (`task4-lane/edit-run-final2.txt`). |
| Find — ⌘F | works | Opens the in-window "Find in thread" field (web-side control; there is no Find menu item — noted, not fixed: it already works). |
| Reload — ⌘R (T8) | works via menu | View > Reload pressed (AXPress) on the signed-in thread: page intact, no new pairing record (T8b `02-good-path/`). The ⌘R key itself was not fired. |
| Close window — ⌘W | works via menu | `File > Close Window` terminated the single-window app; the ⌘W key itself was not separately fired. |
| Quit — ⌘Q | not-tested | Menu advertises ⌘Q; every attempt found the process already gone (close had terminated it). |
| Zoom in — ⌘= (T8) | works | AX element sizes grew 28→32 px / 239→264 px after the key (`task5/zoom-*-verified-ax.json`). |
| Zoom out — ⌘- (T8) | does-not-work | Dispatch receipt present; AX sizes unchanged from the zoomed state across two passes. T8b: menu item enabled and pressed via AXPress — no measured scale change; still not working by any tested path. |
| Actual size — ⌘0 (T8) | does-not-work | Dispatch receipt present; AX sizes unchanged from the zoomed state across two passes. T8b: menu item enabled and pressed via AXPress at all zoom states (never disabled); still not working by any tested path. |
| Back — ⌘[ (T8) | works via menu | View > Back pressed from the signed-in thread: the window lands on the inert blank page ("Mastermind OS", 11 nodes), as the location.replace design predicts (T8b `02-good-path/window8`). The ⌘[ key itself was not fired. |
| Reopen after close | works | 30 s after verified process exit, `open -n` returned exactly one instance, signed in on the same thread, no pairing. |

Honest caveat on the T8 zoom rows: all shortcuts were driven by synthetic
per-PID CGEvents, not a human keyboard. ⌘= took effect through exactly the
path ⌘- and ⌘0 did not, so the asymmetry is real as measured, but a human
pressing the keys may see different routing; if the principal sees the same
failure by hand, the fix belongs in `shell_menu.rs` (the handlers exist for
all three). Copy/paste failing while select-all and undo work points at the
page's own clipboard handling, not the menu.

## 7. Two T3 servers on one Mac: the cookie hazard

HTTP cookies are scoped by host name, not port. The dev server (3797) and
the team server (3780) are both `127.0.0.1`, so one webview cookie store
cannot hold sessions for both: whichever server the store last paired with
owns the cookie, and the other server sees a foreign session value, treats
it as unauthenticated, and shows the pairing page — which the window then
solves by re-pairing, silently invalidating the first server's session.
Switching one bundle back and forth between servers therefore means a
re-pair on every switch, and each server's cookie value is disclosed to the
other server's process (both loopback and the same user, so this is
hygiene, not a boundary break).

The mitigation already in place: one bundle identifier per server. Each
bundle gets its own WebKit container, so the installed release app
(`com.mastermind.os`, pointed at 3780) and the t8 proof bundle
(`com.mastermind.os.dev.t8`, pointed at 3797) never share a cookie. Keep
that rule when adding more windows: never point one bundle identifier at
two T3 servers on this Mac, and when a bundle must move servers, delete its
cookie container (`~/Library/WebKit/<bundle-id>` and any
`~/Library/HTTPStorages/<bundle-id>*`) once, then let it re-pair.
