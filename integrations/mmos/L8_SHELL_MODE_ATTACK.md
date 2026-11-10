# L8 shell-mode diff — read-only attack pass

Target: `git diff 7c7491b16...HEAD -- app/mastermind_os/src-tauri/` at HEAD
`5664dce1812426235c207136aa878f9d8103c1e7` (branch `t3/mmos-v2-l8s`). Files:
`src/shell_mode.rs` (new), `src/main.rs` (modified), `tauri.conf.dev.json` (new).

Pinned dependency sources used as ground truth (local cargo registry):
`tauri-2.11.6`, `tauri-utils-2.9.3`, `tauri-runtime-wry-2.11.4`, `url-2.5.8`.

## Verdict

PASS — no frozen-spec defeat found: the URL gate holds against every exotic
spelling tried, the shell page has no native-IPC path, refusals never leak the
raw input, the unset path is a true no-op, and the bootstrap is inert; two LOW
hardening/coverage findings below (no gate bypass, no exploit).

## Findings

### 1. LOW — capability scan misses config-declared inline capabilities

**Where:** `app/mastermind_os/src-tauri/src/shell_mode.rs:358-382`
(`no_capability_grants_remote_origins`).

**Why it matters:** Spec 4's invariant is "no capability grants remote
origins". The test enforces it only over the `capabilities/*.json` directory.
Tauri also accepts capabilities declared inline in the merged config:
`app.security.capabilities: Vec<CapabilityEntry>`
(`tauri-utils-2.9.3/src/config.rs:2954`), whose entries may be inline
capability objects that can carry a `remote` block and are resolved into
`ExecutionContext::Remote` by the same code path
(`tauri-utils-2.9.3/src/acl/resolved.rs:217-229`). A future inline remote
capability — or one merged in via `tauri dev --config extra.json` — would grant
the shell page IPC while all six existing tests stay green. **The current tree
is clean** (see reproduction): both config files are free of any
`capabilities` block and the directory is free of `remote` keys, so this is a
latent coverage gap, not a live hole.

**Reproduction (shell, run from the repo root):**

```sh
# (a) nothing inline today — both greps must return nothing:
grep -n '"capabilities"' app/mastermind_os/src-tauri/tauri.conf.json \
                      app/mastermind_os/src-tauri/tauri.conf.dev.json
grep -rn '"remote"' app/mastermind_os/src-tauri/capabilities/
# (b) the test only reads the directory — see its only input:
sed -n '359p' app/mastermind_os/src-tauri/src/shell_mode.rs
#   -> let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("capabilities");
```

**Recommended fix — paste into `shell_mode.rs` `mod tests`:**

```rust
#[test]
fn merged_config_declares_no_inline_remote_capability() {
    // Inline capabilities under app.security.capabilities resolve through the
    // same ACL as capabilities/*.json (tauri-utils-2.9.3 config.rs:2954,
    // acl/resolved.rs ~217-229), so the configs must stay clean too.
    for name in ["tauri.conf.json", "tauri.conf.dev.json"] {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(name);
        let text = fs::read_to_string(&path).expect(name);
        let value: serde_json::Value = serde_json::from_str(&text).expect(name);
        let caps = &value["app"]["security"]["capabilities"];
        if let Some(entries) = caps.as_array() {
            for entry in entries {
                assert!(
                    entry.get("remote").is_none(),
                    "{name} must not declare an inline remote capability"
                );
            }
        }
    }
}
```

### 2. LOW — no navigation re-validation after load; module doc overstates the guarantee

**Where:** claim at `app/mastermind_os/src-tauri/src/shell_mode.rs:8-10`
("Only `http://127.0.0.1` and `http://localhost` are accepted, so the window
can never be steered at a remote origin by an environment variable") vs
`app/mastermind_os/src-tauri/src/main.rs:101-117` (`build_shell_window`
installs only `initialization_script` + `navigate`; no `.on_navigation`).

**Why it matters:** Not a spec violation — the frozen spec gates only
`MM_SHELL_URL` at startup, and the doc sentence is literally about the env
var. But the runtime guarantee is weaker than a reader would infer: nothing in
the diff (or in Tauri's defaults — `navigation_handler: None` at
`tauri-2.11.6/src/webview/mod.rs:353,432`) re-validates navigation. Once the
loopback page is loaded, that page — or anything it redirects through — can
navigate the window to any origin. IPC is still denied to non-local origins
(see vector-c evidence below), so this is a display/phishing surface inside a
chrome-less app window, not an IPC bypass. Navigating to `tauri://localhost`
would load the bundled app frontend (the normal app, not attacker content).

**Reproduction (shell):**

```sh
git diff 7c7491b16...HEAD -- app/mastermind_os/src-tauri/ | grep -c on_navigation
# -> 0  (no navigation handler anywhere in the diff)
```

**Optional hardening:** add `.on_navigation(|url| url == shell_url ||
is_app_origin(url))` to the builder in `build_shell_window`, and soften the
doc comment to "by the environment variable at startup".

## Vector coverage (evidence for the PASS)

**(a) Gate bypass via odd URL spellings — none found.** Decisions rest on the
pinned `url-2.5.8` source, not on another language's parser:

- `http://127.1`, `http://2130706433`, `http://0x7f000001`,
  `http://127.000.000.001`, `http://127.0.0.1.` — host ends in a number, so
  `parse_ipv4addr` (`url-2.5.8/src/host.rs:297-360`) normalizes them to
  `Ipv4(127.0.0.1)`; `host_str()` then returns exactly `"127.0.0.1"` and the
  gate at `shell_mode.rs:89` accepts. Still loopback — consistent with spec 2
  ("host exactly 127.0.0.1" after normalization). No off-loopback outcome is
  reachable this way.
- `http://127.0.0.1.evil.com`, `http://127.1.evil.com`,
  `http://0x7f000001.evil.com`, `http://localhost.evil.com` — last label is
  not a number, so they stay `Domain(...)` and `host_str()` ≠ the two allowed
  literals → refused (`HostNotLoopback`).
- `http://localhost.` — IDNA (`host.rs:109`) keeps the trailing dot;
  `host_str()` = `"localhost."` → refused.
- Percent-encoded hosts (`%6coc%61lhost`, `%2E` tricks) — the parser
  percent-decodes before IDNA, so they either normalize to the literal
  loopback string (accepted, still loopback) or are refused.
- `http://localhost@evil.com` / any `user:pass@` — userinfo is checked FIRST
  (`shell_mode.rs:82-84`) → `UserInfo` refusal before the host is even
  looked at. `http://evil.com#@127.0.0.1` — fragment ignored, host is
  `evil.com` → refused. `[::1]`, `[::ffff:127.0.0.1]` — `host_str()` includes
  brackets → refused. Tab/newline tricks (`http://127.0.0.1\t.evil.com`) —
  parser strips ASCII tab/newline → becomes the `.evil.com` domain → refused.

The writer's test table (`shell_mode.rs:282-298`) lacks these exotic forms.
Recommended paste-ready addition:

```rust
#[test]
fn gate_handles_exotic_loopback_spellings() {
    // url-2.5.8 normalizes IPv4 shorthands to Ipv4(127.0.0.1): accepted, still loopback.
    for accepted in [
        "http://127.1",
        "http://127.0.0.1.",
        "http://2130706433",
        "http://0x7f000001",
        "http://127.000.000.001",
    ] {
        let parsed = parse_shell_url(accepted)
            .unwrap_or_else(|r| panic!("{accepted} refused as {}", r.subcode()));
        assert_eq!(parsed.host_str(), Some("127.0.0.1"), "{accepted}");
    }
    // Lookalikes that are not loopback must all be refused.
    for refused in [
        "http://127.0.0.1.evil.com",
        "http://127.1.evil.com",
        "http://0x7f000001.evil.com",
        "http://localhost.",
        "http://localhost.evil.com",
        "http://LOCALHOST%2Eevil.com",
        "http://localhost@evil.com",
        "http://evil.com#@127.0.0.1",
        "http://[::1]",
        "http://[::ffff:127.0.0.1]",
        "http://127.0.0.1\t.evil.com",
    ] {
        assert!(parse_shell_url(refused).is_err(), "{refused} must be refused");
    }
}
```

**(b) Post-load navigation** — see Finding 2. No re-validation exists; IPC
privilege does not follow the navigation (origin is taken from the page's own
Origin header at invoke time, `tauri-2.11.6/src/ipc/protocol.rs:489-496`, and
re-checked per request in `on_message`, `webview/mod.rs:1744`).

**(c) IPC from the shell page — blocked.** The decisive chain, all pinned
source:

1. `is_local_url` (`tauri-2.11.6/src/webview/mod.rs:1698-1737`): local iff the
   tauri protocol URL, **or** `get_app_url().make_relative(current_url)`
   succeeds, or a registered custom scheme. `get_app_url`
   (`tauri-2.11.6/src/manager/mod.rs:353-367`) is `devUrl`
   (`http://localhost:5173`) in `tauri dev` builds and `tauri://localhost` in
   release. `make_relative` (`url-2.5.8/src/lib.rs:516-528`) returns `None`
   unless scheme **and** host **and** port all match. Therefore
   `http://127.0.0.1:<any>` is never local, and `http://localhost:<port>` is
   local only when port 5173 in a `tauri dev` build — i.e. the app's own vite
   dev-server origin, which is the pre-existing dev frontend, not the shell
   page. So the shell page is `Origin::Remote` in every configuration.
2. Remote contexts exist only for capabilities with a `remote` block
   (`tauri-utils-2.9.3/src/acl/resolved.rs:217-229`); none exists
   (`capabilities/main.json` has no `remote` key; asserted by test). With no
   matching context, `resolve_access` (`tauri-2.11.6/src/ipc/authority.rs:439-466`)
   returns `None` → every command denied.
3. App (non-plugin) commands are NOT exempt: upstream's own pinned test
   `remote_origin_blocked_for_custom_commands_without_app_manifest`
   (`tauri-2.11.6/src/webview/mod.rs:2421-2466`) asserts custom commands are
   rejected from remote origins even with no manifest. So the long
   `invoke_handler!` list in `main.rs:206-287` is unreachable from the shell
   page.
4. The invoke key is injected via initialization script into every page the
   webview loads (so a remote page holds it), but it is not the boundary — the
   ACL is, and it holds. The only capability in the tree
   (`core:event:allow-listen/unlisten`, windows `["main"]`) grants Local
   contexts only.

**(d) Raw-input leak — none.** `log_refusal` (`shell_mode.rs:112-123`) writes
only `refusal.code()` / `check()` / `subcode()`; `ShellUrlRefusal`
(`shell_mode.rs:25-37`) is a unit-like enum that structurally cannot carry the
input. `redact()` interaction: the stored code is
`SHELL_URL_REFUSED.host_not_loopback`; the longest `[A-Za-z0-9_-]` run is 17
bytes ("host_not_loopback"), under the 20-byte threshold of
`redact_b64_runs` (`src/dev_log.rs:206-229`), so the code survives intact and
greppable — no over-redaction, and nothing to leak. No
`bearer`/`authorization`/`subject` substring interactions. Verified live: the
existing `refusal_logging_writes_one_parseable_record_without_the_input` test
passed in the run below.

**(e) Unset behaviour — true no-op.** `main.rs:168-179`: the `create = false`
mutation is guarded by `shell_url.is_some()`; `setup` calls
`build_shell_window` only `if let Some(url)` (`main.rs:201-203`); the run
closure passes `shell_url.as_ref()` = `None` into `reopen_main_window`, whose
`None` arm (`main.rs:139-160`) performs the identical builder sequence as the
pre-diff code (only the `if shell.is_some()` blocks are new). Tauri honors
`create` via `app.rs:2524` (`filter(|w| w.create)`), default `true`
(`tauri-utils-2.9.3/src/config.rs:1936,2299`). Set-but-empty (`MM_SHELL_URL=""`)
is a refusal (`Unparseable`) then treated as unset — spec-3 compliant.

**(f) Bootstrap JS — inert as specified.** `SHELL_PAGE_BOOTSTRAP`
(`shell_mode.rs:132-252`): the whole body is one `try { … } catch {}`
envelope (lines 134/250) with every entry point additionally wrapped; no
timers, no network calls of its own, no credentials; wrappers return the
original results (`fetch` 168-177, XHR 183-193, `console.error` 153-158); no
`Object.prototype` writes — only `defineProperty` on `window` (246-249) and
`data-mm-ref` attributes on queried elements (211). It exposes nothing that
reaches native code: `MMShellPage.refs/text/click/type` operate on the DOM of
the page itself.

## Unverified suspicions

- **Bootstrap follows redirects.** WRY initialization scripts run on every
  page the webview loads, including pages the shell server redirects to and
  the local app frontend. If the loopback server ever redirects off-loopback,
  the bootstrap will still instrument that page (wrap its fetch/XHR/console,
  record its fetch URLs — which may embed tokens in query strings — into the
  in-memory `__mmShell.buffer`, set `data-mm-ref` on its DOM). In-memory,
  same-page, no network: still spec-5 "inert", but a runtime fact worth
  knowing. Not verified at runtime (GUI runs were out of scope).
- **Subcode mislabel.** `parse_shell_url` checks userinfo before scheme
  (`shell_mode.rs:82-87`), so `https://user:pass@evil.com` reports `userinfo`
  rather than `wrong_scheme`. Cosmetic only; refused either way.
- **`tauri.conf.dev.json` is referenced by nothing yet** (repo-wide grep finds
  no consumer). Its deep-link scheme `com.mastermind.os.dev` will not match
  `terminal_callback_owner` (`main.rs:119-121`, scheme
  `com.mastermind.os`), so dev-scheme Terminal links would route to the auth
  owner. Dev-only, outside the frozen spec, and the consuming harness does not
  exist in this diff.
- **Port 0** (`http://127.0.0.1:0`) passes the gate ("any port"); the
  navigation itself would fail to load. Harmless.

## What I ran

1. The one permitted test command (run #1 of max 2; the second was not
   needed — no finding required a live run beyond this):

   ```
   MM_SOURCE_REVISION=$(git -C /Users/chriswong/.t3/worktrees/Mastermind/t3-b6530e3a rev-parse HEAD) \
   MM_BUILD_IDENTITY=l8s-attack \
   CARGO_TARGET_DIR=/Volumes/Mastermind/build-cache/t3-l8s-cargo-target \
   cargo test --manifest-path app/mastermind_os/src-tauri/Cargo.toml shell_mode
   ```

   Outcome: exit 0 — `shell_mode::tests`: 6 passed, 0 failed
   (`accepts_loopback_http_urls`, `refuses_everything_but_loopback_http`,
   `refusal_subcodes_are_distinct`,
   `refusal_logging_writes_one_parseable_record_without_the_input`,
   `no_capability_grants_remote_origins`,
   `bootstrap_installs_the_page_api_and_carries_no_credentials`).

2. Read-only inspection only: `git diff/rev-parse/branch`, `cat/grep/sed`
   over repo files and over the pinned crate sources in
   `~/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/`
   (`tauri-2.11.6`, `tauri-utils-2.9.3`, `url-2.5.8`,
   `tauri-runtime-wry-2.11.4`); one `python3 - <<PY` block using
   `urllib.parse` as a *cross-check table* for candidate spellings (decisions
   rest on the `url-2.5.8` source read, not on Python).

3. Not done, per instructions: no GUI/app launch, no npm, no screenshots, no
   worktree or branch switch, no tracked-file edit, no second build, no
   commit/push. This report file is the only new file created.
