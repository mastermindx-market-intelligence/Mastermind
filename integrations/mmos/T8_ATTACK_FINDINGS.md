# T8 attack review: unattended window pairing

Reviewed commit: `c74498596dc6682a91d845ea5e29b3d685aff1e7`.
The named files in this checkout matched that commit before this report was added.
Review was static plus synthetic shell reproductions in `/tmp`; no app, server,
desktop access, network request, or real credential was used.

The origin parser, file reader, helper output pipe, and failure log stop the
straightforward attacks. The issues below are narrower; their preconditions are
stated rather than treating the 0600 config file as a universal attacker.

## Findings

### 1. HIGH: same-origin page script can obtain the newly minted token

**Locations:**
`app/mastermind_os/src-tauri/src/shell_pairing.rs:52-60` and `:261-267`;
`app/mastermind_os/src-tauri/src/main.rs:109-117`.

Any script executing on the configured T3 origin can make the watchdog mint a
credential with `history.replaceState(null, "", "/pair")`. Detection requires
only the URL's origin and `/pair` path; it does not establish that the displayed
page is the genuine unauthenticated pairing page. The helper's address is then
loaded into the same window.

At this commit, `/pair` and `/pair#token=...` differ only in the fragment.
Fragment navigation retains the current document and its JavaScript. The
attacker's script therefore remains alive and can read `location.hash`, then send
it off-origin using an ordinary image or fetch request. A token that should
travel only through a pipe and a navigation becomes readable by page script.
The attacker can convert a transient same-origin script compromise into a
persistent T3 session. This requires script execution on the configured origin;
a remote page or a second macOS user cannot trigger it directly.

The same-document behavior is not speculation: the later local commit
`c4f3c91a7` records that this exact first-run navigation did not remount the
pairing page and its change inserts `about:blank` between the two loads. That
later live observation is cited, not claimed as a live reproduction in this
review.

Synthetic URL reproduction:

```sh
/opt/homebrew/bin/python3.12 -I - <<'PY'
from urllib.parse import urlsplit
before = urlsplit("http://127.0.0.1:3797/pair")
after = urlsplit("http://127.0.0.1:3797/pair#token=synthetic1234")
assert before._replace(fragment=after.fragment) == after
print("Only the fragment changes; the existing document and script survive.")
PY
```

The page-side reproducer, for an isolated future test page on that configured
origin, is:

```js
history.replaceState(null, "", "/pair");
// After shell_pairing.rs:263 navigates, the old script still runs:
const token = new URLSearchParams(location.hash.slice(1)).get("token");
// A malicious page can now exfiltrate token. No network request was made for this review.
```

Navigate through an inert, detached document before loading the token, then
load the token into a fresh document. Do not let page-controlled history alone
establish that re-pairing is needed.

### 2. MEDIUM: the executed helper is not protected by the config's file checks

**Locations:**
`app/mastermind_os/src-tauri/src/shell_mode.rs:262-267`;
`app/mastermind_os/src-tauri/src/shell_pairing.rs:104-120`;
`tools/mmos_team_server/window_config.sh:68-78`.

The 0600, ownership, regular-file, and no-symlink checks apply only to the text
file containing the helper's path. The absolute executable named by that text
is executed later with no metadata check, fixed installation directory,
canonicalization, or descriptor binding. `window_config.sh` accepts any
absolute executable path. Replacing a permitted helper with a symlink changes
what runs without changing the 0600 config.

This matters when a named helper or one of its ancestor directories is writable
by another user, for example a wrapper under a shared temporary directory. It
is not a bypass of a correctly installed user-owned helper in a 0700 directory;
the precondition is an unsafe named executable path. Nevertheless, the config
itself does not enforce the trust property its comments imply.

Harmless reproduction of executable substitution:

```sh
tmp=$(mktemp -d /tmp/mmos-t8-helper.XXXXXX) || exit 1
chmod 755 "$tmp"
cp /bin/echo "$tmp/helper"
chmod 755 "$tmp/helper"
mkdir "$tmp/attack"
printf '#!/bin/sh\nprintf substituted > "$1"\n' > "$tmp/attack/helper"
chmod 700 "$tmp/attack/helper"
ln -sf "$tmp/attack/helper" "$tmp/helper"
"$tmp/helper" "$tmp/marker"
printf 'marker='
tr -d '\n' < "$tmp/marker"
printf '\n'
```

The output is `marker=substituted`. The named path had a valid executable at
configuration time but invokes a different one later.

Install the helper in a private fixed directory and check the opened executable
and its parents for regular-file type, expected owner, and no group/other write
access. Merely checking `-x` is not a trust check.

### 3. MEDIUM: the config tool accepts and prints a query-string pairing token

**Locations:**
`tools/mmos_team_server/window_config.sh:58-70`, `:76`, and `:86-94`.

`write` rejects a fragment specifically to keep pairing tokens out of config,
but accepts the same credential in the query string. `show` then prints the
stored URL in full. This violates the lane rule that a pairing token never be
printed or logged. It also stores a credential in an address that the watchdog
treats as an ordinary configured origin. Forming a refusal URL from `--url` at
line 63 is another possible disclosure path for an invalid token-bearing URL.

Synthetic reproduction, keeping the displayed value hashed rather than printing
even the synthetic token:

```sh
tmp=$(mktemp -d /tmp/mmos-t8-config.XXXXXX) || exit 1
mkdir -p "$tmp"
chmod 700 "$tmp"
HOME="$tmp" sh tools/mmos_team_server/window_config.sh write \
  --bundle dev \
  --url 'http://127.0.0.1:3797/env/thread?token=synthetic1234' \
  --pair-helper /bin/echo
HOME="$tmp" sh tools/mmos_team_server/window_config.sh show --bundle dev |
  grep -q 'token=synthetic1234' && printf 'show printed the supplied query token\n'
```

The write exits 0, and the final check exits 0 because `show` prints the
supplied query token. Parsing the URL and rejecting a `token` query parameter,
and redacting rather than printing URL contents, closes this leak.

### 4. MEDIUM: any same-origin non-`/pair` URL is recorded as a successful exchange

**Location:**
`app/mastermind_os/src-tauri/src/shell_pairing.rs:277-284`.

After minting, `landed` means only “same origin and not exactly `/pair`.” There
is no check that the pairing endpoint accepted the token, that the server
issued the expected session, or that the window reached the configured thread.
Even navigating to a made-up path satisfies it. The watchdog then navigates to
`original`, ignores that navigation's result, logs `PAIRING.DONE`, and exits.

A same-origin script can change history to `/not-pair` while the helper runs or
before a token-consuming request happens, producing a success record without any
exchange. A user navigating during the helper wait also gets raced by the
watchdog. This is a false attestation and a navigation race, not a demonstrated
remote-origin pairing bypass.

Synthetic predicate reproduction:

```sh
/opt/homebrew/bin/python3.12 -I - <<'PY'
from urllib.parse import urlsplit
origin = urlsplit("http://127.0.0.1:3797/env/thread")
current = urlsplit("http://127.0.0.1:3797/not-pair")
same_origin = (current.scheme, current.hostname, current.port) == \
              (origin.scheme, origin.hostname, origin.port)
assert same_origin and current.path != "/pair"
print("The current landed predicate declares success without an exchange.")
PY
```

Track the intended token navigation through its actual document load, verify a
credential-free server outcome, and only then return to the original thread.
Do not infer success from a path inequality.

### 5. LOW: a substring such as `not-a-token=` suppresses re-pairing forever

**Location:**
`app/mastermind_os/src-tauri/src/shell_pairing.rs:52-60`.

`carries_pairing_token` searches for the byte substring `token=` anywhere in
the query or fragment, rather than parsing a `token` parameter. Thus a stale,
expired, or deliberately placed `not-a-token=` is treated as an in-flight
pairing. The watchdog remains `Armed`, never invokes the helper, and has no
armed-state timeout. A page can therefore suppress automatic recovery for the
lifetime of the process.

Synthetic reproduction:

```sh
/opt/homebrew/bin/python3.12 -I - <<'PY'
from urllib.parse import parse_qs, urlsplit
u = urlsplit("http://127.0.0.1:3797/pair#not-a-token=synthetic1234")
assert u.path == "/pair"
assert "token=" in (u.fragment or "")
assert "token" not in parse_qs(u.fragment)
print("The current substring test waits forever; parsed token is absent.")
PY
```

Parse the actual parameter name and value. A syntactically present but stale
or used token should not suppress recovery indefinitely.

## Answers for the requested attacker cases

- **Web page:** finding 1 is a token disclosure to same-origin page script;
  findings 4 and 5 are state-machine attacks. Page content does not supply an
  executable path. The helper's origin check prevents the helper from minting a
  navigation to a non-loopback place or a different loopback origin.
- **Planted file on disk:** a user-owned, regular, exact-0600 config is trusted;
  that trust is intended for the same macOS user. The executable named by it
  lacks equivalent validation (finding 2). A token-bearing query is mishandled
  by the config UI (finding 3).
- **Symlink:** a symlink at the config file is refused by `O_NOFOLLOW`. A
  symlink at the separately named helper path is followed (finding 2).
- **Second local macOS user:** that user cannot directly replace a correctly
  installed config in a user-owned 0700 directory. The loader also demands
  `metadata.uid() == getuid()` and exact 0600, so another user's file is not
  accepted. Finding 2 applies only when the configured helper's path is in a
  location writable by that other user.
- **Stale or already-used token:** loading the supplied token does not create
  a new helper invocation because `token=` suppresses detection. It cannot
  redirect the helper or write a log through this code. Failure to recover and
  false substring handling are described in findings 4 and 5.

## Not a finding: attempted attacks already stopped

- A planted symlink as `shell-url` or `pair-helper` fails the no-follow open at
  `shell_mode.rs:129-139`; post-open metadata, not a racy prior `stat`, supplies
  the checks at `:140-150`. Another user's ownership, non-regular files, wrong
  modes, embedded newline/NUL, and oversized contents are refused at `:140-165`.
- Replacing a config leaf after it is opened does not change the inspected file
  description. Config-file checks are made on `file.metadata()` obtained from
  the opened descriptor, eliminating the usual stat-then-read pathname TOCTOU.
- A hardlink needs the same inode and therefore the same owner and mode. It
  cannot turn `/etc/passwd` into a user-owned 0600 file or give a second user
  write authority to a first user's file. A same-user hardlink adds no authority
  that same user does not already have.
- `http://evil.example/...`, other ports, `https`, userinfo, IPv6, and host
  lookalikes cannot pass `parse_shell_url`. The `url` crate normalizes IPv4
  shorthand to the same loopback host before the origin comparison. The numeric
  host and `port_or_known_default` comparison is at `shell_pairing.rs:37-42`.
- The helper cannot contribute shell syntax: `Command::new(helper)` receives no
  arguments and no page input (`shell_pairing.rs:104-120`). Paths with spaces
  are not re-parsed as commands. Config-script expansions of `$URL`, `$HELPER`,
  `$DIR`, and `$1.tmp.$$` are quoted in their value contexts.
- The token does not enter helper argv. The token also does not pass through
  the caller's environment into an unrelated process: the caller clears the
  environment and supplies only `HOME`, a fixed `PATH`, and `TMPDIR`
  (`shell_pairing.rs:106-119`). The shell helper passes only the server home,
  TTL, and fixed label in argv, at `window_pair_helper.sh:39-40`. A helper that
  deliberately stores its own stdout remains outside this guarantee.
- Additional stdout text is stripped by `sed` and `head`. Neither the helper
  nor the Rust caller forwards the pairing URL to its own stderr; the Rust
  caller discards child stderr. Any diagnostic emitted by the wrapper rather
  than by `t3 pair` could still reach the launcher's stderr, so suppressing
  only `t3 pair`'s stderr must not be described as making all wrapper stderr
  secret-safe.
  Multiple output lines, non-HTTP output, and cross-origin output fail at
  `shell_pairing.rs:168-176`; the real helper's synthetic extraction test passed.
- The failure page incorporates no input and percent-encodes fixed markup at
  `shell_pairing.rs:180-203`. Failure logs contain fixed codes only, at
  `:205-215`; neither a rejected URL nor helper stderr is copied into them.
- `HOME` and `MMOS_DEV_ROOT` are ordinary process launch configuration, not
  remote inputs. `HOME` changes both config lookup and the helper's default
  home consistently; `MMOS_DEV_ROOT` selects a diagnostic root but does not
  select a helper or URL. `T3CODE_HOME` cannot override the explicit
  `--base-dir "$T3_HOME"` in `window_pair_helper.sh:39`.
- `/pair/`, `/pairing`, another loopback port, and another host do not trigger
  minting. The original origin is retained separately from page-controlled
  helper output and rechecked before navigation.

## Verification

```sh
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider tests/test_mmos_window_config.py
```

Last output line: `.............                                                            [100%]`
All 13 focused tests passed. Rust and live-window reproduction were not run,
as required by the review brief. The later `c4f3c91a7` change was inspected
only to corroborate the same-document navigation defect; this report targets
`c74498596` throughout.
