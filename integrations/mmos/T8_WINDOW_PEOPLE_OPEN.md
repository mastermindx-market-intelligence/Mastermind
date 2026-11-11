# T8 — the window a person opens (runbook for the principal)

Lane T8 of program plan V4 (branch `t3/mmos-v4-t8`). The goal: a person
double-clicks the Mastermind OS app and it opens on the Team project of its
T3 server, signed in, with no login step — the first time and after the
session expires. This file is the principal's switch-over runbook for the
real team server on `127.0.0.1:3780`. The lane itself proved everything on a
dev bundle (`com.mastermind.os.dev.t8`) against a private dev T3 server on
port 3797; the team server was never touched by the lane.

How the app finds its server, in order: the `MM_SHELL_URL_FILE` environment
variable, then `MM_SHELL_URL`, then a fixed per-user config file. A person
launching from Finder or the Dock has no environment, so the fixed config is
what serves them:

| Bundle | Identifier | Config directory |
|---|---|---|
| Release (installed) | `com.mastermind.os` | `~/.mastermind/window` |
| Dev | `com.mastermind.os.dev` | `~/.mastermind/mmos_dev/window-dev` |
| T8 proof | `com.mastermind.os.dev.t8` | `~/.mastermind/mmos_dev/window-dev-t8` |

Each directory holds two 0600 files: `shell-url` (one line: the loopback
thread address, never a pairing token) and `pair-helper` (one line: absolute
path to an executable that mints a fresh pairing URL). No file means today's
ordinary window with no error. When the server answers with its pairing
page — first run, or an expired or cleared session cookie — the window runs
the helper once, loads the minted one-time address, and lands signed-in on
the configured thread. The helper reuses `t3 pair`; its only authority is
being the macOS user who owns the server home's files. Nothing is admitted
over loopback TCP or a request header, and the token never enters argv, a
log, another process's environment, or evidence.

## 1. Build the release bundle from this branch

```sh
git -C <your checkout of t3/mmos-v4-t8> rev-parse HEAD   # record it
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
or `t3-t8-cargo-target` (this lane's debug artifacts).

Honesty note: this lane proved the code on the dev/t8 bundle, not on a
release build. The release mapping itself (`com.mastermind.os` reading
`~/.mastermind/window`) is covered by the loader's unit tests in
`shell_mode.rs` and the tool mapping tests in
`tests/test_mmos_window_config.py`. If the release profile trips a signing
or notarization gate your machine does not have credentials for, that is a
build-config question, not a regression in this lane.

## 2. Write the config that points it at the team server

Pick the thread the window should open on. The roster file is read-only for
you (never send a request to port 3780):

```sh
sh tools/mmos_team_server/open_team_window.sh --list   # instance ids and names
/usr/bin/python3 -I -c 'import json;[print(t["instanceId"],t["url"]) for t in json.load(open("'$HOME'/.mastermind/t3-team/run/team_urls.json"))["teammates"]]'
```

Put the pairing helper somewhere stable (a checkout path dies with the
worktree). It needs no environment overrides — its defaults are exactly the
team server's own `t3` and home:

```sh
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

The tool refuses non-loopback, https, bare-origin and fragment-carrying
URLs, and non-executable or relative helper paths. Files are written 0600
into a 0700 directory.

## 3. Check it

```sh
sh tools/mmos_team_server/window_config.sh show --bundle release
open -n "/Volumes/Mastermind/build-cache/t8-release-cargo-target/release/bundle/macos/Mastermind OS.app"
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

and restore the previous `Mastermind OS.app` bundle from wherever you keep
it (the lane's `INSTALL_RECEIPTS_AND_ROLLBACK.md` records the install
receipts pattern). A cleared config plus an old bundle is exactly the
pre-T8 state: the old app never read the file, so leaving it would also be
harmless — but clearing it removes the temptation.

## 5. What was proved and what was not

Proved, live, on the dev/t8 bundle against a private dev T3 server
(127.0.0.1:3797), evidence in `~/.mastermind/mmos_evidence/t8-20261110/`:

- First open with no environment and no cookie store: the window read the
  address from its fixed 0600 config, detected the pairing page, minted a
  fresh one-time address through the configured helper, and landed signed-in
  on the Team thread with no typing (`01-first-open`, `PAIRING.DONE`).
- Session-expiry equivalent: the dev bundle's cookie container deleted, the
  app reopened — a second `PAIRING.DONE` and the signed-in thread again with
  no typing (`02-reopen-after-cookie-delete`).
- The failure path, live: before the fragment-navigation fix the exchange
  timed out; the window showed the plain one-sentence page and the log
  gained exactly one input-free `PAIRING.FAILED.exchange_timeout` record.
- Every helper failure shape (missing, non-zero exit, empty, multiline,
  off-origin, remote, hung), the tokenless-page detection rules, the
  watchdog's whole state machine, and token-free logging are unit-tested in
  `shell_pairing.rs` and `tests/test_mmos_window_config.py`.

Not proved by this lane: the release bundle build and the real team server
on 3780 (forbidden to the lane; that is exactly what sections 1–3 hand
you), a real multi-day session expiry (cookie deletion is the stand-in),
and multi-user Macs (authority is file ownership by the server home's
owner; a second local user gets the plain failure page, which is tested,
but no live second-user run happened).

## 6. Keyboard table

Filled from the typing child's run against the dev bundle on the dev
server; raw captures and its own table live in
`~/.mastermind/mmos_evidence/t8-20261110/03-typing/`.

<!-- T8-TYPING-TABLE: inserted from the child's KEYBOARD_TABLE.md when it returns -->

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
