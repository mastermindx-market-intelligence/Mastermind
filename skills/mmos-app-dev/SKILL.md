---
name: mmos-app-dev
description: Build, launch and prove the Mastermind OS thin-window dev bundle (shell mode).
---

# MMOS app development (thin window)

The Mastermind OS app is a thin native window. In shell mode its one window
loads a loopback origin; unset means the normal app. For Paperclip module work
use the `mmos-module-dev` skill instead — this skill is the native window only.

## The origin setting

`MM_SHELL_URL` — one environment variable, read once at startup
(`app/mastermind_os/src-tauri/src/shell_mode.rs`). Accepted:
`http://127.0.0.1[:port][/...]`, `http://localhost[:port][/...]`; exotic
loopback spellings (`127.1`, `2130706433`, `0x7f000001`) normalize to
`127.0.0.1` and stay loopback. Refused — logged without the raw value, app
starts in normal mode: https, `0.0.0.0`, `[::1]`, any other host, `file:`,
userinfo, unparseable. The loaded page gets no native IPC (no capability,
file or config-inline, carries a `remote` key). Proof:
`cargo test --manifest-path src-tauri/Cargo.toml shell_mode` — 12 tests at
the time of writing, run from `app/mastermind_os`.

## The T3 command line picks its own server

The `t3` CLI chooses its server from `T3CODE_HOME` and `T3CODE_PORT`, never
from any address inside your arguments — a helper pointed at a dev URL has
minted pairing codes on the Chairman's app (port 3773) this way. Set both to
the server you mean and confirm it answers before any pairing command. The
stock `~/.t3/bin/t3` wraps the Chairman's app and prints a warning line in
front of its JSON when aimed at a newer home, so scripts reading its JSON
fail — use the named server build's own binary (team server:
`~/.mastermind/t3-team-server/bin/t3`, `T3CODE_HOME=~/.mastermind/t3-team/home`).

## Pairing

Pair from a 0600 file at launch (`MM_SHELL_URL_FILE`). The one-time token in
the server's `run/access.txt` stops working about two minutes after the server
starts — pair with a freshly made code. Never take an accessibility dump or an
image of the pairing page: the page shows the token (`LANE_RULES_V4.md`).

## Build the dev bundle

```sh
cd app/mastermind_os
MM_SOURCE_REVISION=$(git rev-parse HEAD) MM_BUILD_IDENTITY=$(whoami)-dev \
  CARGO_TARGET_DIR=/Volumes/Mastermind/build-cache/t3-l8s-cargo-target \
  node_modules/.bin/tauri build --debug --config src-tauri/tauri.conf.dev.json
# bundle: $CARGO_TARGET_DIR/debug/bundle/macos/Mastermind OS Dev.app
```

`MM_SOURCE_REVISION` (40 hex) and `MM_BUILD_IDENTITY` (`[A-Za-z0-9._:-]`, ≤160)
are required by `build.rs`. The dev overlay gives the bundle its own identity
(`com.mastermind.os.dev`, "Mastermind OS Dev") so it cannot be confused with
the installed app.

## Launch in shell mode

```sh
MM_SHELL_URL=http://127.0.0.1:<port> MMOS_DEV_ROOT=$HOME/.mastermind/mmos_dev \
  "<target>/debug/bundle/macos/Mastermind OS Dev.app/Contents/MacOS/mastermind-os"
```

The dev log (JSONL, structurally redacted) is `$MMOS_DEV_ROOT/app.log`;
refusals also go to stderr. Read that log, never the T3 server's raw
`run/server.log` — its startup banner carries credentials (`LANE_RULES_V4.md`).

## Proof recipe (load only, window-scoped)

1. Serve any static page on your own port:
   `python3 -m http.server <port> --bind 127.0.0.1` from a scratch dir.
2. Launch as above with `MM_SHELL_URL=http://127.0.0.1:<port>`.
3. Accessibility text: `osascript -e 'tell application "System Events" to tell
   process "mastermind-os" to get entire contents of first window'`.
   Transient zero-element or no-composer reads happen on a live webview;
   retry once in the same bounded session before concluding the page is
   blank, and count a step done only once its evidence file exists.
4. Window capture: `peekaboo see --app "Mastermind OS Dev" --no-elements --path
   <file>.png` (peekaboo v4; the old `image` command was removed).

## Boundaries

- Never rebuild, replace, quit or drive the installed
  `~/Applications/Mastermind OS.app`.
- Never load, pair with or send to the T3 servers on ports 3773 and 3774.
- The default Paperclip instance on 127.0.0.1:3100 is read-only (GET only).
- Captures are scoped to the dev window; never full-screen. Kill the dev app
  and your proof server when done.
- Full safety and git rules: `integrations/mmos/LANE_RULES_V4.md`.
