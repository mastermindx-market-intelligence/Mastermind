# PART D — Window switch: staging → real server, and the undo

PF-2 item 4. The principal's step list for pointing the window app
`com.mastermind.os.next` ("Mastermind OS Next") from staging
(T3 `127.0.0.1:3830`, board `127.0.0.1:3196`) to the real server
(T3 `127.0.0.1:3780`, board `127.0.0.1:3100`), and back. **One bundle
identifier never points at two servers: this is a switch, not a second
target.** Rehearsed end to end on 2026-11-14 against a throwaway HOME and a
throwaway T3 root (realshape, port 3832); every step ledgered with UTC/rc/
seconds in `~/.mastermind/mmos_evidence/pf-20261114/switch/LEDGER.md`.
No real root, frozen folder, placed app or window was touched; no request
was sent to 3830, 3196, 3780 or 3100.

## How it works (source facts, cited)

- **Fixed config folder per bundle id.** `shell_mode.rs::fixed_config_dir`
  (`app/mastermind_os/src-tauri/src/shell_mode.rs:442-460`):
  `com.mastermind.os.next` → `$HOME/.mastermind/mmos_dev/window-next`.
  Files: `shell-url` (one line, `http://127.0.0.1:<port>/<environmentId>/<threadId>`),
  `pair-helper` (one absolute path), `board-url` (origin only). Each 0600,
  folder 0700, user-owned, no symlinks (`shell_mode.rs:495-500` and the
  repair-N folder check). Writer: `tools/mmos_team_server/window_config.sh`
  (`next` → line 91; uses `$HOME`). A `write` without `--pair-helper`
  **removes** an existing helper (lines 27-28, 244-247) — always pass it.
- **Config is read once, at launch.** `main.rs:346`
  (`shell_url_from_env`, defined at `main.rs:92`) resolves the address
  before the Tauri builder exists; the board origin at `main.rs:350`.
  There is no config watcher in `shell_mode.rs`. A second launch while the
  app runs starts nothing: the single-instance plugin
  (`main.rs:375-393`) only brings the existing window forward using the
  URLs **captured at first launch** (`main.rs:364-365`,
  `reopen_main_window` `main.rs:313-334`). **A running window does NOT pick
  up a changed config — a relaunch (⌘Q, then open) is required.**
- **The check builds no window.** `--check-window-config`
  (`main.rs:343-345`) exits before any Tauri builder (`main.rs:366`) or
  single-instance code (`main.rs:375`); it runs the real loader
  (`run_window_config_check` `main.rs:221-229`, report `main.rs:233-300`)
  against `$HOME` (`main.rs:250-252`) and prints one `ok`/`refused` line
  per item: `config-dir`, `shell-url`, `pair-helper`, `board-url`
  (`absent` is normal for the optional board). Exit 0 only when all pass.
- **Pairing happens only when needed.** The watchdog mints only when the
  page the window loaded is the server's pairing page `/pair` without a
  token in flight: `shell_pairing.rs:725-733` (`Phase::Armed` → `Mint`
  only if `needs_pairing`), `needs_pairing` `shell_pairing.rs:186-188`,
  `is_pairing_page` `shell_pairing.rs:179-181`; module header
  `shell_pairing.rs:3-4` ("first run, expired or cleared session cookie").
  With a valid session cookie the window opens straight on the thread and
  the helper never runs. After a verified pairing it re-arms
  (`shell_pairing.rs:20-22`), so a later expiry re-pairs without relaunch.
  Mint budget: 3 helper runs per 10 min (`shell_pairing.rs:79-80`).
- **The window clears the helper's environment** (`run_pair_helper`
  `shell_pairing.rs:337`, `.env_clear()` at `shell_pairing.rs:346`), so
  `WINDOW_PAIR_T3_BIN`/`WINDOW_PAIR_T3_HOME` set in a shell never reach a
  config-named helper. A **wrapper script** is the supported way to aim the
  window at a dev server (staging's
  `~/.mastermind/mmos_dev/pf/staging/bin/pair_helper_staging.sh` is the
  shape). For the **real** target no wrapper is needed: the helper's
  defaults are exactly the real root
  (`window_pair_helper.sh:24-25`: `$HOME/.mastermind/t3-team-server/bin/t3`,
  `$HOME/.mastermind/t3-team/home`). The helper mints via `t3 pair
  --base-dir <home> --ttl 2m` (`window_pair_helper.sh:50`); its authority
  is being the macOS user who owns the server home's files. The URL
  (one-time token in the fragment) travels only through the helper's
  stdout pipe — never argv, a log, or evidence.
- **Cookies: one WKWebView store, one cookie per port.** Web-mode loopback
  cookie name is `t3_session_<port>_<sha256(instanceKey)[:12]>`; desktop
  mode is `t3_session_<port>`
  (`pf-t3code/apps/server/src/auth/utils.ts:15-44`). Set with `expires`,
  `httpOnly`, `path /`, `SameSite lax`
  (`pf-t3code/apps/server/src/auth/http.ts:202-217`, applied at
  `http.ts:288`). So the 3830 and 3780 sessions are **two different
  cookies** in the one store of `com.mastermind.os.next`: switching does
  not overwrite or log out the other; switching back reuses the 3830
  cookie while unexpired. **The window clears no website data on config
  change**: there is no `WKWebsiteDataStore`/cookie-clearing call anywhere
  in `app/mastermind_os/src-tauri/src` (grep: only `env_clear` for the
  helper at `shell_pairing.rs:346` and `clear_executive` for the app's own
  auth state, unrelated to web cookies). Both boards run
  `deploymentMode local_trusted` (lead-verified via `GET /api/health`), so
  the board origin needs no cookie.
- **Session TTL: 30 days.** `DEFAULT_SESSION_TTL = Duration.days(30)`
  (`pf-t3code/apps/server/src/auth/SessionStore.ts:428`, applied at
  `SessionStore.ts:653`); the pairing exchange issues a
  `browser-session-cookie` session with no explicit ttl
  (`EnvironmentAuth.ts:884-897`), and the cookie's `expires` is that
  session's `expiresAt` (`http.ts:204`). A staging cookie is therefore
  good for 30 days from its issue; after that the window re-pairs once via
  the staging helper.
- **One bundle id, one target.** The config folder holds exactly one
  `shell-url`; `write` replaces it atomically (helper-first commit,
  `window_config.sh:223-254`). Never a second app, never a second
  instance: the single-instance plugin makes a second launch focus the
  existing window (`main.rs:375-393`). The release app
  (`com.mastermind.os` → `~/.mastermind/window`) is a different bundle and
  a different folder — untouched by all of this.

## Preconditions

1. **The Chairman agrees the time.** The switch ends with a ⌘Q + reopen of
   his window; do it when no run of his needs the window undisturbed.
2. **Real 3780 is up — part (b) matters and must be DONE.** Part (b) is the
   real-server install (release `t3team-0.1.7-pinf5248ab2`, ~10 s restart;
   `STATUS.md` "Reserved to principal"). The switch's target must be
   serving before the window is pointed at it. Verify read-only, e.g.
   `lsof -nP -iTCP:3780 -sTCP:LISTEN` (the principal's act).
3. **Part (c) (presentation) does not gate the switch.** It sets the
   product name, team mode, picker lock and the Work/Needs-you board links
   (`PART_C_PRESENTATION.md`), applies live without a server restart, and
   may be done before or after. If it is not done, the switch still works;
   the Chairman just sees default branding and no board links.
4. The placed app `~/Applications/Mastermind OS Next.app` exists (the
   principal placed it). Everything below that touches the real root, the
   placed app's binary, or the window is **the principal's act only**.

## Step list (all the principal's acts)

### 0. Read the real address parts (read-only)

```sh
cat ~/.mastermind/t3-team/home/userdata/environment-id
```

That is `<real env id>`. For `<thread id>`, pick the teammate the window
should open on and read its primary thread id from the roster state
(`~/.mastermind/t3-team/run/team_roster_state.json`,
`teammates.<Name>.threadId`), or use the T8 method
(`T8_WINDOW_PEOPLE_OPEN.md:106-112`: `open_team_window.sh --list`, then the
one address from `team_urls.json`). No request to 3780 is needed.

### 1. Back up the three files (sha256 only)

```sh
B=~/.mastermind/mmos_dev/pf/principal/window-next-backup-$(date -u +%Y%m%d)
mkdir -p "$B" && chmod 700 "$B"
cp -p ~/.mastermind/mmos_dev/window-next/shell-url \
      ~/.mastermind/mmos_dev/window-next/pair-helper \
      ~/.mastermind/mmos_dev/window-next/board-url "$B/"
shasum -a 256 "$B"/shell-url "$B"/pair-helper "$B"/board-url
```

Today's frozen staging shape (lead `show`, 09:5xZ; re-verified in the
rehearsal seed): `shell-url` →
`http://127.0.0.1:3830/9fb1b14c-d6f1-405d-bf04-193555cc2353/mcp:4ea4759b-dfef-4400-8144-c4b788017fb0`
(Scout), `pair-helper` →
`~/.mastermind/mmos_dev/pf/staging/bin/pair_helper_staging.sh`,
`board-url` → `http://127.0.0.1:3196`.

### 2. The switch write

```sh
sh tools/mmos_team_server/window_config.sh write --bundle next \
  --url "http://127.0.0.1:3780/<real env id>/<thread id>" \
  --pair-helper "$HOME/.mastermind/t3-team-server/bin/window-pair-helper.sh" \
  --board-url "http://127.0.0.1:3100"
```

**Pair-helper choice:** the installed real helper
`~/.mastermind/t3-team-server/bin/window-pair-helper.sh` — a 0700 copy of
`tools/mmos_team_server/window_pair_helper.sh` installed per
`T8_WINDOW_PEOPLE_OPEN.md:120-126`. Its defaults are exactly the real
server's `t3` and home, so **no wrapper is needed for the real target**.
If that copy is not installed yet, install it first with the four T8 lines
(mkdir/chmod/cp/chmod — the principal's act). A wrapper (the staging shape)
is only for dev servers. The helper path must stay non-group-writable in
non-group-writable directories: the window trust-walks every component
(`main.rs:280`, `shell_pairing.rs:30-33`).

`--board-url http://127.0.0.1:3100` is the real Paperclip board origin
(URL string only here; the window loads it after the switch, GET-only per
lane limits). The board is optional: omitting `--board-url` keeps the
existing one (`window_config.sh:29-30`), so pass it explicitly.

### 3. The check (builds no window, starts nothing)

```sh
"$HOME/Applications/Mastermind OS Next.app/Contents/MacOS/mastermind-os" \
  --check-window-config
```

The binary inside the placed bundle is `Contents/MacOS/mastermind-os`
(the cargo bin name; same pattern as `T8_WINDOW_PEOPLE_OPEN.md:159`).
This is the placed app's binary run **only** in check mode — it exits
before any window, server, helper or single-instance code
(`main.rs:343-345`). Expect exactly:

```
config-dir: ok
shell-url: ok
pair-helper: ok
board-url: ok
```

(Equivalently: `window_config.sh check --bundle next --app <that path>` —
the tool just execs the binary, `window_config.sh:266-272`.) Any `refused`
line stops the switch; fix the named item and re-check.

### 4. Relaunch (agreed time) and what the Chairman sees

⌘Q "Mastermind OS Next", then open it again. A second launch without
quitting would only focus the old window with the old address
(`main.rs:375-393`). On the first open at 3780 there is no 3780 cookie
yet: the server shows `/pair`, the watchdog runs the helper once, loads
the minted one-time address through a blank page, and lands signed-in on
the chosen thread — no typing anywhere. `PAIRING.DONE` increases by one in
`~/.mastermind/mmos_dev/app.log` (`shell_pairing.rs:682-688`; dev root =
`$HOME/.mastermind/mmos_dev`, `shell_mode.rs:594-602`). The board links
(Work / Needs you → 3100) appear per part (c). A failure writes exactly
one input-free `PAIRING.FAILED.<reason>` record and shows one plain
sentence (`shell_pairing.rs:10-13`).

### 5. Cookie store: what stays, what is added

- **Stays:** the staging cookie `t3_session_3830_<12hex>` — untouched.
- **Added:** `t3_session_3780_<12hex>` (web-mode loopback name,
  `utils.ts:43`), 30-day expiry (`SessionStore.ts:428`).
- **Cleared:** nothing. The window has no website-data clearing path
  (source grep above); the two cookies coexist in the one WKWebView store
  of `com.mastermind.os.next`.

### 6. UNDO — back to staging

```sh
sh tools/mmos_team_server/window_config.sh write --bundle next \
  --url "http://127.0.0.1:3830/9fb1b14c-d6f1-405d-bf04-193555cc2353/mcp:4ea4759b-dfef-4400-8144-c4b788017fb0" \
  --pair-helper "$HOME/.mastermind/mmos_dev/pf/staging/bin/pair_helper_staging.sh" \
  --board-url "http://127.0.0.1:3196"
```

Then the same check line (step 3), then ⌘Q + open. **No pairing is needed
while the 3830 cookie is valid** — 30 days from its issue
(`SessionStore.ts:428,653`; cookie `expires` = session expiry,
`http.ts:204`). The window opens straight on Scout; no new
`PAIRING.DONE`. If it has expired, the staging wrapper pairs once (same
mechanism as step 4, aimed at 3830). Restoring the step-1 backup copies
with `cp -p` is equivalent: the rehearsal proved the write round-trip is
byte-identical (cmp below).

### 7. One bundle id, one target

After either write, `window-next` holds exactly one `shell-url`. There is
no second app and no second instance: the bundle identifier is fixed at
build time, the config folder is derived from it
(`shell_mode.rs:442-460`), and the single-instance plugin refuses a second
session (`main.rs:375-393`). Switching is replacing one address, never
adding a target.

## Rehearsal result table (2026-11-14, UTC)

Throwaway HOME `~/.mastermind/mmos_dev/pf/switch-home` (0700); throwaway
"real" root = B-PRES's realshape (`~/.mastermind/mmos_dev/pf/realshape`,
label `com.mastermind.pf.realshape`, port 3832, fake-launchd harness
`env-rs.sh`, started/stopped with `team_server.sh start|stop` exactly as
B-PRES's presentation ledger). Realshape env id
`3d19fe13-3e50-45c5-b73e-fb75b9a3affa`; first primary thread (file order)
= Assurance `mcp:e2185ca0-5b21-443c-879d-87ef4173c15c`. Full ledger:
`~/.mastermind/mmos_evidence/pf-20261114/switch/LEDGER.md`.

| Step | UTC | rc | s |
|---|---|---|---|
| setup: switch-home + evidence dir 0700; 3832 free; only 3830 listening in PF range; build slot empty | 10:09:38–10:10:13 | 0 | ≤1 |
| SEED staging shape (`window_config.sh write`, HOME=switch-home) | 10:10:49 | 0 | 0 |
| BEFORE show + `cp -p` before copies | 10:10:50 | 0 | 1 |
| build: `cargo build --bin mastermind-os` (debug, `TAURI_CONFIG`=next overlay, `MM_BUILD_IDENTITY=pf-switch-test`, target `pf-next-cargo-target`) | 10:11:50 | 0 | 49 |
| BEFORE check (dev-built binary, HOME=switch-home): 4× ok | 10:12:16 | 0 | 1 |
| START realshape (`team_server.sh start`, harness); runner pid 84906 | 10:12:35 | 0 | 7 |
| SWITCH write → 3832/\<env\>/Assurance + realshape wrapper + board 3196 string | 10:12:48 | 0 | 0 |
| SWITCH show + check: 4× ok (incl. wrapper trust walk) | 10:12:48 | 0 | 0 |
| PAIR proof: wrapper → sanitizer; 1 line `http://127.0.0.1:3832/pair`, sha256 `a9f82423…c04c55`; token never printed; wrapper stderr empty | 10:13:00 | 0 | 1 |
| GET `http://127.0.0.1:3832/` → 200 (realshape only) | 10:13:00 | 0 | 0 |
| UNDO write back to staging shape (all three values) | 10:13:21 | 0 | 1 |
| UNDO show + check: 4× ok | 10:13:21 | 0 | 0 |
| UNDO cmp vs before copies: shell-url / pair-helper / board-url all **same** (byte-identical; sha256 equal to before) | 10:13:21 | 0 | 0 |
| STOP realshape (`team_server.sh stop`; bootout TERMs job pid = process-group leader) | 10:13:36 | 0 | 1 |
| post-stop: 3832 free; no stray realshape processes; staging 3830 STILL LISTEN (pid 59230, never stopped/sent to); launchd-state markers cleared | 10:13:36–10:14:39 | 0 | 0 |

Before/after sha256 (identical pairs): `shell-url`
`2ba9f939…c4e45b`, `pair-helper` `417bdda3…3244d4`, `board-url`
`6a37cce9…90277b` (full values in the ledger and `switch/before/`).

### Exact deviations from the real run

1. **Port 3832 (throwaway realshape) instead of 3780**; env/thread ids are
   realshape's, not the real root's. The real root was never read or sent
   to; the real env id read in step 0 is the principal's act.
2. **HOME override**: every `window_config.sh` call and every check ran
   with `HOME=~/.mastermind/mmos_dev/pf/switch-home`. The frozen
   `~/.mastermind/mmos_dev/window-next` was never written, cleared or
   checked. The real run uses the real HOME (no override).
3. **Check binary**: a dev-built debug binary
   (`/Volumes/Mastermind/build-cache/pf-next-cargo-target/debug/mastermind-os`)
   instead of the placed app's binary. A plain `cargo build` embeds
   `tauri.conf.json`'s identifier `com.mastermind.os` — the **release**
   folder — so the build used the same overlay mechanism as the wave-1/PF
   app build (`tauri build --config tauri.conf.next.json`, STATUS.md
   07:09Z/07:57Z): `TAURI_CONFIG="$(cat tauri.conf.next.json)"` (inline
   JSON merge, honored by tauri-build 2.6.3 `lib.rs:487-490` and
   tauri-codegen 2.6.3 `lib.rs:53-85` — the same merge the tauri CLI
   performs for `--config`). The check finding `window-next` under the
   throwaway HOME proves the embedded identifier was
   `com.mastermind.os.next`. Build env:
   `MM_SOURCE_REVISION=84148e4ce6920db57ad66bfe198adfc0f3fbc127`
   `MM_BUILD_IDENTITY=pf-switch-test`
   `CARGO_TARGET_DIR=/Volumes/Mastermind/build-cache/pf-next-cargo-target`.
4. **No window launch, no window driving.** Pairing was proven at the
   helper boundary (rc 0 + one well-formed `/pair` line + sha256), not by
   a cookie exchange in a webview; the minted token was not consumed.
   The in-window journey (first-open pairing, board links, undo reuse of
   the 3830 cookie) is the principal's window check at the agreed time.
5. **Board URL**: the rehearsal kept `http://127.0.0.1:3196` in both
   directions (URL string only; nothing sent). The real run writes
   `http://127.0.0.1:3100` on switch and `http://127.0.0.1:3196` on undo.
6. **Server lifecycle**: realshape ran under the fake-launchd harness
   (fake uid 59999; no real launchd job ever created). The real 3780 is
   launchd-kept-alive and is not stopped by any of this.

## Findings (rehearsal-only; no tool changed)

1. `/usr/bin/umask 077 sh …` via `env` was a silent no-op on this Mac
   (rc 0, nothing exec'd, nothing written). Use the shell builtin
   (`(umask 077; …)`); the ledger records the no-op and the redo.
2. `lsof -iTCP:3831-3839` (range syntax) returned nothing even with 3830
   listening — per-port checks are the reliable form.
3. A plain `cargo build` without the `TAURI_CONFIG` overlay would check
   the **release** config folder (`com.mastermind.os`), not `window-next`
   — always build the check binary with the next overlay (deviation 3).

## Evidence

- Ledger: `~/.mastermind/mmos_evidence/pf-20261114/switch/LEDGER.md`
- Outputs: `switch/{seed,before-show,before-check,switch-write,switch-show,switch-check,pair-proof,undo-write,undo-show,undo-check,start,stop,post-3832,post-stray,post-3830}.out`, `switch/build.log`
- Before copies (0600, in 0700 dir): `switch/before/{shell-url,pair-helper,board-url}`
- Wrapper: `~/.mastermind/mmos_dev/pf/switch-home/pair_helper_realshape.sh` (0700)
- Sanitizer: `switch/pair_sanitizer.py` (prints line count, scheme/host/port/path-to-`/pair`, sha256 only)
- Pairing proof sha256: `a9f82423c57aa5af9860b356e9a5988756a429a66b12caa8b758c214a8c04c55` (the full URL line; token never recorded)