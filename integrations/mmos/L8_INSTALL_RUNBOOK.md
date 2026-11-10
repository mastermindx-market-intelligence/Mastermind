# L8 install runbook — production thin window

Audience: the principal, on the M2. Lane source landed on trunk at `07a6108f5`.
Shell mode behavior: `MM_SHELL_URL` set + valid (`http`, host exactly
`127.0.0.1` or `localhost`, any port) → the one window loads that origin with
zero native IPC. Unset or refused → the normal app, unchanged; refusals are
logged as `SHELL_URL_REFUSED.<subcode>` without the raw value.

## 1. Build (release profile)

```sh
cd <checkout>/app/mastermind_os
MM_SOURCE_REVISION=$(git rev-parse HEAD) \
MM_BUILD_IDENTITY=m2-prod-$(date +%Y%m%d) \
node_modules/.bin/tauri build
# bundle: src-tauri/target/release/bundle/macos/Mastermind OS.app
# (with CARGO_TARGET_DIR set, under <that>/release/bundle/macos/ instead)
```

`MM_SOURCE_REVISION` must be 40 hex chars; `MM_BUILD_IDENTITY` matches
`[A-Za-z0-9._:-]`, ≤160 chars (`build.rs` enforces both at compile time).

## 2. Verify the binary before installing

```sh
strings -a "<bundle>/Contents/MacOS/mastermind-os" | grep MM_RECEIPT
# prints the embedded source revision + build identity
cd app/mastermind_os && MM_SOURCE_REVISION=$(git rev-parse HEAD) \
  MM_BUILD_IDENTITY=check cargo test --manifest-path src-tauri/Cargo.toml shell_mode
# 8 tests: gate accept/refuse table, exotic spellings, refusal logging, no remote IPC
```

## 3. Install (manual act, principal only)

```sh
# quit the installed app first (Cmd-Q); lanes never touch it
mv ~/Applications/"Mastermind OS.app" ~/Applications/"Mastermind OS.app.bak-$(date +%Y%m%d)"
cp -R "<bundle>/Mastermind OS.app" ~/Applications/
```

## 4. Set the origin

GUI apps do not inherit shell environment. Either:

```sh
launchctl setenv MM_SHELL_URL http://127.0.0.1:<port>   # GUI launches, until reboot
launchctl unsetenv MM_SHELL_URL                          # back to the normal app
```

or launch the binary directly, which inherits the environment:

```sh
MM_SHELL_URL=http://127.0.0.1:<port> \
  ~/Applications/"Mastermind OS.app/Contents/MacOS/mastermind-os"
```

Refusal evidence: stderr (direct launch) and the dev log
`$MMOS_DEV_ROOT/app.log` (default `~/.mastermind/mmos_dev/app.log`).

## 5. Rollback

Quit, `mv` the `.bak` over `~/Applications/Mastermind OS.app`. With
`MM_SHELL_URL` unset the build is byte-identical in behavior to its base.

## Boundaries

Pairing the window to the Chairman's T3 servers (3773/3774) is the principal's
own act (PROGRAM_PLAN_V4 §6); no lane does it. Captures of this window are
window-scoped only.
