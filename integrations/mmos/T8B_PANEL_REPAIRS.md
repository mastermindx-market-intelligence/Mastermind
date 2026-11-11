# T8b — panel repairs on the window pairing watchdog

Lane T8b of program plan V4 (branch `t3/mmos-v4-t8b`, cut from `9d80379ba`).
The second review panel scored the lane-T8 pairing watchdog
(`~/.mastermind/mmos_evidence/t8-20261110/panel/SCORE.md`); this lane fixed
every confirmed finding and re-proved the behaviour live on a private dev
T3 server. Evidence for this lane: `~/.mastermind/mmos_evidence/t8b-20261111/`.

Each repair below names its fail-first test (tests were run against the
pre-fix commit export to show they fail there, then against the branch).

## A — one watchdog per app process, following the window instance

`WatchdogCore` (in `shell_pairing.rs`) wraps the pure `decide()` state
machine with a generation counter and a mint budget. Every window build and
every Dock reopen go through the single shared `create_main_window`
(`main.rs`), which bumps the generation; when the watchdog sees a window
absent, or a different generation than the one its current phase began on,
it drops any minted address and returns to Armed. After a verified pairing
it logs `PAIRING.DONE` and re-arms — a later `/pair` arrival (expired
session) re-pairs without a relaunch. After a failure it shows the failure
page, logs once, and re-arms when the window is next seen on the configured
origin. The watchdog thread is started exactly once, in `setup`, only when
the config names a helper. Mint limit: at most 3 mints in any 10 minutes;
past it, exactly one `PAIRING.FAILED.rate_limited` page per episode and no
mint until the window has passed. `View > Go to Server` (`shell_menu.rs`,
enabled only when a shell origin is configured) takes the window back to
the configured address.

Tests: `watchdog_core_follows_the_window_and_rearms`,
`watchdog_core_rate_limits_the_fourth_mint_with_one_page`,
`mint_budget_allows_three_mints_in_any_ten_minutes`,
`window_generation_increments_on_each_bump`.

## B — navigation allowlist on the shell window

`navigation_allowed(url, origin, failure_page)` allows exactly: the
configured origin (scheme, host and port exact), the inert blank page, and
the app's own failure-page constant. Every other http/https address is
refused in the window and opened in the person's default browser through
the maintained `tauri-plugin-opener` (which this app already ships);
everything else is refused and logged. The allowlist is installed in
`create_main_window`, so both the first build and the reopen carry it.

Tests: `navigation_allowlist_permits_only_the_configured_origin_and_two_constants`.

## C — one deadline for read and exit; process group; helper exit status

`run_pair_helper` computes one deadline that covers both reading the URL
and the child's exit, runs the helper in its own process group
(`process_group(0)`, killed with `kill(-pid, SIGKILL)`), and always joins
the reader thread. `window_pair_helper.sh` captures the minting command's
output before printing the one URL line, so `t3 pair`'s non-zero exit
becomes the helper's non-zero exit (`helper_exit` is reachable).

Tests: `run_pair_helper_deadline_covers_read_and_exit_together`, the
grandchild-killing sleeper case, and
`test_failing_t3_exits_nonzero_and_produces_no_url` (python).

## D — minted address shape

A helper output is accepted only from the same origin with path exactly
`/pair`, no query, and a fragment starting `token=`.

Test: `run_pair_helper_requires_the_minted_address_shape` (5 cases).

## E — the spent one-time address in the back list (LOW)

Cheapest sound handling chosen: returning the window to the configured
address uses `location.replace()`, so the spent `/pair#token=…` address
never enters the session history — Back cannot walk to it, and no extra
blanking navigation is needed. Cosmetic cost: Back from the thread lands on
`about:blank` (the window's first inert load) instead of nothing; a person
can leave it with Go to Server. Accepted over history-clearing JavaScript
(which WKWebView applies inconsistently) or a new webview per pairing
(which would fight the generation-following design).

## F — window_config.sh

`write` without `--pair-helper` removes an existing helper unless
`--keep-pair-helper` is given, and the removal happens before the address
is committed. `localhost` is refused (the server prints `127.0.0.1`; the
spellings must not diverge). The path is extracted with sed and checked
exactly: the server root `/`, `/pair` and anything under `/pair` are
refused. Both files are staged in mode-0600 temporaries under `umask 077`
with a trap that removes them on any exit, then committed helper-first: a
crash between the two renames leaves at most the old address beside the new
helper (the helper only ever mints a fresh one-time address), never a fresh
address beside a withdrawn helper. Residual: the two renames are not one
atomic operation — a crash in the microsecond window between them can
leave the pair half-committed in the safe direction above.

Tests: `test_write_without_helper_removes_an_existing_helper`,
`test_write_keep_pair_helper_preserves_an_existing_helper`,
`test_write_refuses_localhost_and_pair_paths`,
`test_write_leaves_no_temporaries_and_files_are_0600`,
`test_source_stages_under_umask_077_with_a_removing_trap`.

## G — single instance

The maintained `tauri-plugin-single-instance` v2 (official plugins
workspace, matching the locked Tauri 2.11 line) is a declared dependency
and the first registered plugin. A second launch focuses the first window
(rebuilding it through the shared builder exactly like a Dock reopen if the
person had closed it) and starts nothing — no second watchdog, auth restore
or pairing. Chosen over a hand-rolled lock file because the plugin owns the
platform races; nothing smaller is sound.

Test: `test_single_instance_plugin_is_a_dependency_and_registered_first`
(python, source-level; live behaviour proven in this lane's evidence).

## H — open_team_window.sh header/code agreement

The header claimed the env-launched flow "keeps its old behaviour" of never
re-pairing. In truth the watchdog is started whenever the fixed config
names a helper — env launch included — and the window clears the helper's
environment, so `WINDOW_PAIR_T3_BIN`/`WINDOW_PAIR_T3_HOME` cannot aim an
env-launched window's re-pairing at a dev server. Header, helper header and
this runbook now agree: the supported way is a small wrapper script that
exports those two variables and execs `window_pair_helper.sh`, named in the
fixed config via `--pair-helper`.

Tests: `test_open_team_window_header_matches_the_config_helper_behaviour`,
`test_helper_header_documents_the_env_cleared_wrapper_route`.

## I — no-remote-capability test scans by glob

`merged_config_declares_no_inline_remote_capability` globs every
`tauri.conf*.json` in the manifest directory (failing on any that is
unreadable or unparseable) instead of a fixed two-file list, so a future
variant config cannot silently escape the scan.

## J — the failure page's own failure is logged

`fail()` logs one input-free `PAIRING.FAILED_PAGE.refused` record when the
navigation to the failure page itself is refused (e.g. the allowlist
changed and the constant fell out of it); the person sees whatever the
webview last showed, and the log still carries the one-line reason.

Test: `failure_page_refusal_is_logged_input_free`.

## K — helper trust walk on the resolved path

`helper_is_trusted` now walks twice. First the path as written: every
component via `symlink_metadata`; a symlink component is trusted only when
owned by the user or root. Then the resolved path (`canonicalize`): every
component must be a real directory (a symlink anywhere in the resolved
chain is refused), owned by the user or root, with no group/other write;
the leaf must additionally be a regular file owned likewise, mode without
group/other write and with some execute bit. A helper planted behind an
own symlink into a 0777 directory is therefore refused even though every
name typed into the config is itself clean.

Tests: `helper_trust_path_refuses_substitutable_locations` (rust),
`test_write_refuses_substitutable_pair_helpers` (python, tool side).

## L — no address is ever echoed raw

Refusals name the reason only — `window_config: refusing the address:
<code>` — never the value. `show` prints the scheme/host/port/path of an
acceptable address and, for anything carrying a query, fragment or
userinfo, prints `(not shown: carries a query, fragment or userinfo)`. The
old `redact()` helper is gone: there is no partially-masked address left
to build.

Tests: `test_refusals_name_the_reason_only_never_the_value`,
`test_show_prints_scheme_host_port_path_and_never_the_rest`,
`test_write_refuses_token_bearing_urls_without_echoing_them`.

## M — one judge: `--check-window-config`

The app binary accepts `--check-window-config`, builds no window, helper
or watchdog, and runs the same loader the real launch runs (address file,
helper file, helper trust walk, config-folder check). It prints one line
per item — `shell-url: ok` / `shell-url: refused <code>`, the same for
`pair-helper` and `config-dir` — exits 0 only when all pass, and never
prints an address or file contents. `window_config.sh check --bundle <b>
--app <path>` runs exactly this mode, so the tool and the app cannot
disagree about what a good config is. The write side keeps its exact early
refusals (scheme http, host exactly 127.0.0.1, port all digits 1–65535,
no userinfo/query/fragment/control/newline, path not `/pair` nor under
it, helper absolute with no `..`).

Tests: `window_config_check_judges_the_real_loader_outcomes` (rust — the
check output follows the real loader through a symlinked-folder attack),
`test_check_command_runs_the_app_judge_and_propagates_it`,
`test_write_exact_shape_rules_ports_and_paths`.

## N — the config folder itself is checked

The loader refuses a config folder that is a symlink, not a directory,
not owned by the user, or not mode 0700 — its own refusal codes
(`config_dir_symlink`, `config_dir_not_dir`, `config_dir_wrong_owner`,
`config_dir_wrong_permissions`), applied to both the address and helper
reads. The tool refuses to write into a symlinked folder and creates the
folder 0700.

Tests: `config_folder_itself_is_checked_for_both_files` (rust),
`test_write_creates_0600_files_and_show_round_trips` + the umask/trap
source test (python).

## O — roster ids parsed, addresses parsed

`open_team_window.sh` validates the typed instance id
(`^[A-Za-z0-9._-]+$`, no `..`) *and* re-validates the roster entry's own
id before it becomes a file name; the roster address is parsed with
`urlsplit` under the same exact rule as `window_config.sh` (scheme http,
host exactly 127.0.0.1, real port, no userinfo/query/fragment, path
neither root nor `/pair` nor under it) instead of prefix-matched. The
thread file is written 0600 with O_EXCL after removing any stale file.

Tests: `test_instance_ids_are_validated_typed_and_from_the_roster`,
`test_roster_addresses_are_parsed_not_prefix_matched`.

## P — runbook made true

§3 tells the person to quit a running copy first (the single-instance
plugin focuses it otherwise); §4 lists exactly what `clear` leaves (the
helper copy, an empty 0700 folder, the cookie store, a possibly running
copy) and how to remove each, and no longer offers "restore the previous
bundle"; §1 carries the real prerequisites (npm ci, the build volume) and
signing; §2 `mkdir -p` before copy and the roster printed as id and name
only; `usage()` prints only the help text. §3 verifies with
`window_config.sh check`, not `show`.

Test: `test_usage_prints_only_the_help_text` (source-level guard); the
rest is documentation verified by reading against the scripts.

## Live-proof round 1 — the app could not start (fixed)

The first live-proof child could not prove any pairing behaviour: the app
**crashed at every launch** (4/4, ~3–4 s in, zero `PAIRING.*` records —
`01-dead-helper/launch3-backtrace.log`). wry 0.55.1's url getter unwraps
`WKWebView.URL`, which is nil until the webview's first load commits — and
the window's initial `tauri://` frontend load is refused by the navigation
allowlist, so nothing commits until the configured address does. The
watchdog's first `WebviewWindow::url()` poll (750 ms in) therefore hit the
unwrap and the panic landed on the event loop, taking the app down.

Fix: the watchdog polls the URL only behind `url_poll_is_safe(generation)`
— a gate that opens when the window's `on_page_load` callback reports
`PageLoadEvent::Finished` for the generation captured at build time. A
stale commit from a closed window cannot open the gate for its successor,
and before the first commit the watchdog simply waits (the window has
nothing to observe yet). Tests:
`url_polling_waits_for_the_window_generation_to_commit_a_load` (rust;
fail-first evidence is the crash itself plus
`failfirst2-python-urlgate.txt`),
`test_watchdog_never_polls_the_url_before_a_committed_load` (python,
source-level, failed on the pre-fix commit export).

## Live-proof rounds 2–4 on the fixed binary

All evidence under `~/.mastermind/mmos_evidence/t8b-20261111/`
(`00-smoke-fixed/`, `02-good-path/`, `03-dead-helper/`; the blocked third
round's files are kept under `03-dead-helper/` without the `-r2` suffix).

- **The app starts and pairs** (smoke, then `02-good-path/`): first open
  with no session → `PAIRING.DONE`, signed-in thread, no typing.
- **A later `/pair` arrival re-pairs in the same launch**: session
  revoked mid-launch, View > Go to Server → second `PAIRING.DONE` in ~8 s
  (repair A's re-arm).
- **Closed → reopened pairs again**: closing the window exits this
  single-window app (incumbent Tauri behaviour, already recorded in the
  runbook §6); the relaunch pairs (third `DONE`).
- **Single instance** (repair G): a second launch while the first runs
  exits immediately; exactly one process remains; the good-path child
  proved it against a live first instance.
- **Dead helper → failure page, budget enforced**: three helper runs
  (initial arrival, Back, Go to Server), one input-free
  `PAIRING.FAILED.helper_exit` per attempt and the one-sentence page each
  time; past the budget the helper runs zero times and exactly one
  input-free `PAIRING.FAILED.rate_limited` record is written
  (`03-dead-helper/*-r2`).
- **Outside link never loads in the window**: pressing an example.com
  link in the thread left the window on the thread page; the page's
  `target="_blank"` link takes WebKit's new-window path, which hands such
  links to the default browser without the navigation callback (the
  default browser came forward). The navigation-allowlist half is
  unit-tested; the new-window half is this live observation.

Recorded as-is (not defects, not reopened): the rate-limit page reuses
the helper-failure sentence — the log's input-free codes distinguish
them; a fifth arrival after the rate-limited page shows the server's own
pairing page (the pre-watchdog baseline; the helper still runs zero
times); Zoom Out / Actual Size pressed via AXPress produced no measured
scale change (the runbook §6 zoom rows stand); Copy/Paste were verified
present and enabled only, never pressed.

## Attack round (two effort-max children on the part-1 export)

Two children worked the exported part-1 commit (`/tmp/t8b-atk/src`): one
mapped reachable states, one attacked the config and helper surface. Eight
findings came back; seven were fixed, one was judged not a defect in this
app's threat model.

1. **Dot-segment disguises reach the loader** (`/a/../pair`, `%2e`
   spellings, `//pair`, `/PAIR`): the shell writers refused them, but the
   app's url parser normalizes dot segments, so a hand-edited config could
   smuggle the pairing flow in as the "thread" address. Fixed: the loader
   (`parse_shell_url`) now applies the writers' exact rule — no query, no
   fragment, path neither the server root nor `/pair` nor under it, after
   normalization. Tests: `config_lines_follow_the_writers_exact_rule`,
   `url_file_follows_the_writers_exact_rule`,
   `test_write_refuses_dot_segment_disguised_pair_paths`.
2. **`window_config.sh` port arithmetic overflow**: a 19-digit port made
   shell arithmetic error out with an unnamed refusal. Fixed: length
   bounded before any numeric test (`test_write_refuses_oversized_ports_with_a_named_reason`).
3. **`show` missed single-digit ports** (`http://127.0.0.1:1/...` printed
   "unrecognized"). Fixed: port pattern `[0-9]*`
   (`test_show_prints_single_digit_ports`).
4. **Symlinked config directory**: `write` created/chmodded through a
   planted symlink before refusing (target touched); `show`/`clear`
   followed it. Fixed: all three refuse a symlinked `$DIR` first — `write`
   before mkdir/chmod (`test_write_never_touches_a_symlinked_config_directory`,
   `test_show_and_clear_refuse_a_symlinked_config_directory`).
5. **`open_team_window.sh` roster validation gaps**: control characters
   (stripped silently by `urlsplit`), uppercase scheme, raw `#`/`?`, `//`,
   dot segments and `%2e` spellings passed the old prefix rule. Fixed: the
   raw string is checked for control characters and exact `http://` prefix
   before parsing, then urlsplit with the same exact rule as
   `window_config.sh`, path compared lowercased
   (`test_roster_refuses_dot_segments_control_chars_and_uppercase`).
6. **The blanking gate accepted any `about:` URL** — `about:error` would
   have passed as the blank page. Fixed: exact `BLANK_PAGE` constant match
   (assert added to the `decide()` test).
7. **The helper-output parser enforced config-line rules on the minted
   address** whose shape is `/pair#token=` *by design* — split into
   `parse_loopback_http` (structure) vs `parse_shell_url` (config-line
   rule), so the two contracts can no longer collide (repair D intact).
8. **Minted-address shape vs config rules** (states child): the empty
   `token=` fragment passes the shape check but the exchange then records
   `no_session` — no trust is granted and nothing is written. Documented,
   not changed.

**Documented boundaries (not defects, recorded so they are choices):**
the write-side helper checks (regular file, no group/other write on
helper or parent) are weaker than the runtime trust walk — the runbook's
answer is `window_config.sh check`, which runs the app's own judge, after
any write; macOS ACLs are invisible to mode bits and outside what either
side checks; `check --bundle` trusts the caller to pass the matching app
binary (it runs what it is given); and the helper runs before any
origin check — the origin check happens at mint time on the helper's
output, as the panel accepted ("By design" below).

## Panel "By design" items, now written down

Accepted risk: whatever actually listens on the configured port receives
the window's requests and its cookie values. The config pins the address
and the allowlist pins the origin; the port's owner is whatever the person
(or their setup tool) last started there — one bundle identifier per
server (runbook §7) is the mitigation. The config names the helper: the
app has no other pairing route, and the helper's only authority is being
the macOS user who owns the server home's files.
