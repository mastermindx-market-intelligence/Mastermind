# TSH — team server hardening: pinned Node and a packed build

The team server (`com.mastermind.t3-team`, 127.0.0.1:3780, root
`~/.mastermind/t3-team`) today runs the Node that Homebrew happens to
provide, from a binary inside the 4.3 GB source checkout
`~/.mastermind/t3-team-server/`. A routine `brew upgrade` or a moved
directory breaks it while nobody is looking. This lane replaces both halves
with artifacts under the server's own root:

- **Pinned Node v24.22.2** (official nodejs.org darwin-arm64 tarball,
  SHA-256 `aa9549…385a`, verified against SHASUMS256) at
  `<root>/runtime/node-v24.22.2-darwin-arm64/` — the exact pinned directory
  name, enforced at every resolve (item 12) — installed by
  `tools/mmos_team_server/node_install.py`. Review findings F1–F29 plus
  items 12/13 are fixed, each with a test in
  `tests/test_mmos_team_server_runtime.py`,
  `tests/test_mmos_team_server.py`, `tests/test_mmos_team_server_findings.py`,
  `tests/test_mmos_team_server_ops.py` and `tools/mmos_team_server/pack_server.test.mjs`.
- **Packed server build** (`pack_server.mjs`): the built server bundle, the
  history worker, the web client and the production externals in one
  self-contained directory `<root>/runtime/<release>/dist`, published by one
  rename with an in-tree `BUILD_RECEIPT.json` and a config receipt
  `config/server-runtime.json`. The source tree is not needed at runtime.

Both installers are single-writer (`flock` for the Node install, a pid-stamped
lock for packing), clean up a killed run's leftovers under their lock, publish
by one atomic rename after every check that can refuse has already passed, and
fail in one operator-readable line (`team_runtime: …`,
`doctor_error=…`) — never a Python traceback. Receipts are schema 2 (the tree
digest format changed). The interpreter that guards the runner is itself
pinned: `install` records the validated absolute path of the python3 it ran
under in `config/python3-path`, and `server_runner.sh` executes exactly that
path with `-I` — never a PATH search (item 13). Every start and every doctor
re-verifies the full pinned-Node tree digest: measured on the real 199 MB
tree, 1.22 s cold and 0.33–0.38 s warm — under the 2 s bar, so verification is
on by default (`--no-verify-tree` exists for emergencies only).

**Scope note (item 12):** the receipt/tree checks stop a *substituted or
tampered runtime* — a different `installDir`, a swapped `bin/node`, a tree
that no longer matches its recorded digest. A writer who can change the runner
script or the receipts themselves is outside what any such check can stop;
the defence against that writer is the 0700 root (proven by another lane),
which keeps every one of those files writable by the owner alone.

Proven on the dev root `~/.mastermind/mmos_dev/tsh/team-root` (label
`com.mastermind.t3-team-dev-tsh`, port 50809; evidence
`~/.mastermind/mmos_evidence/tsh-20261110/`): install; server answering under
the pinned Node with the packed build; `kill -9` and `launchctl kickstart -k`
each revive in ~3 s with the same thread id; with the whole source tree
moved aside the server restarts, answers, serves the web client (index +
hashed asset 200) and keeps the thread; `doctor` prints health metadata with
no credential. The hardening slice itself (lock, refusal-before-publish,
truthful stop, interrupted install, interpreter pinning) is proven on this
lane's own instance — evidence `~/.mastermind/mmos_evidence/tshc-20261111/`
(`LEDGER.md` indexes it).

**Not proven** (by design of this lane): logout/reboot behavior (RunAtLoad
starts the job at login; KeepAlive restarts the process if it dies or is
killed — neither is a reboot test), multi-day stability, and the real root
itself — every command below is the principal's act on the real server.

After the next reboot, the one command to run:

```
<repo>/tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

It must print `loaded=yes`, a pid, `answeringPort=3780`, `treeVerified=yes`
and exit 0. If it does not, run the same `team_server.sh start` command as in
rollback below.

## Runbook for the real team server

Work from a repo checkout that has this lane's branch `t3/mmos-v4-tshc`
merged. Prerequisites on this Mac (all already present):
`~/.mastermind/mmos_dev/tsh/downloads/` (verified Node tarball + SHASUMS256),
`~/.mastermind/mmos_dev/tsh/source/t3-pin0770446/` (pinned T3 source with
`node_modules` installed). Do the migration when the machine is not under
heavy load: step 6's first boot runs the state-DB migrations inside a 180 s
window, and a machine at load >100 (measured during this lane's own proof)
can stretch a healthy first boot past it — the install then reports the
failure truthfully and cleans up, and a re-run completes quickly because the
migrations already finished.

Every numbered step below states: what worked prints, what the server state
is when the step fails, and the exact recovery command. "Nothing is published
on a refusal" is now literally true for both installers: they stage
privately, run every check that can refuse, and only then perform the single
publishing rename.

### Step 0 — check no teammate run is live

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 ~/.t3/bin/t3 thread list
ps ax -o args= | grep -F '.mastermind/t3-team/claude-home' | grep -v grep
```

Worked looks like: the thread list shows only terminal states (`done`,
`failed`, `idle` — nothing `running`), and the `ps` line prints nothing.
Downtime: none yet. If a thread is running, wait for it or stop it before
continuing — the migration restarts the server. Recovery: none needed; this
step observes only.

### Part (a) — move to the pinned Node and the packed build

Downtime for the whole part: about one to three minutes (stop → install →
pack → reinstall → server answers). Threads and history are preserved; the
pairing cookie in a paired browser keeps working (proven in T6: no re-pair
after restart).

### Step 1 — stop the server

```
cd <repo>
REPO=$PWD
tools/mmos_team_server/team_server.sh stop --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Worked prints: `STOPPED label=com.mastermind.t3-team port=3780 free` (exit 0).

Failure states (all truthful, exit 1):
- `STOP_FAILED label=… still loaded` — launchd did not boot the job out.
  Server: still running under launchd. Recovery:
  `launchctl bootout gui/$(id -u)/com.mastermind.t3-team` then re-run the stop
  command.
- `STOPPED label=… (unloaded) but port 3780 is still held by another process
  (unknown owner)` — the label is gone but something else holds 3780. Server:
  stopped, port occupied. Recovery: `lsof -nP -iTCP:3780 -sTCP:LISTEN` to
  identify the holder, stop it, then re-run the stop command to see
  `… free`.

### Step 2 — tighten the root

```
chmod 700 ~/.mastermind/t3-team
```

Worked prints nothing. (Required by the hardened installer and by
`team_server.sh install`, and a real hardening: the root holds `fabric.env`,
logs and thread state.) The root's existing subdirs (`home/ run/ bin/ config/`
…) do not need manual chmods: the tools tighten the ones they own to 0700, and
`install` refuses any symlinked subdir before writing through it. Failure
state: server still down; recovery: none needed — chmod either worked or
reported its own error.

### Step 3 — install the pinned Node

```
/opt/homebrew/bin/python3.12 tools/mmos_team_server/node_install.py install \
  --root ~/.mastermind/t3-team \
  --archive ~/.mastermind/mmos_dev/tsh/downloads/node-v24.22.2-darwin-arm64.tar.gz \
  --checksum ~/.mastermind/mmos_dev/tsh/downloads/SHASUMS256-v24.22.2.txt
```

Worked prints: `NODE_INSTALLED version=v24.22.2 node=/Users/chriswong/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node sha256=aa9549…`
(~40 s: copy, hash, member check, extract, atomic publish; plus one pass of
the tree digest for the receipt.) It also records this run's validated
absolute python3 into `config/python3-path` — the interpreter the runner will
execute with `-I` (item 13). Idempotent: with the tree already installed and
intact it verifies and prints the same line.

Failure states (server still down, nothing published — the extract happens in
a private staging directory and every refusal fires before the publish
rename):
- Any refusal prints one line `team_runtime: <reason>` (bad checksum, unsafe
  root, conflicting receipt — the message names the exact
  `mv … .conflict` recovery when an outside receipt conflicts). Recovery:
  fix the named condition, re-run this step.
- **Killed mid-extract** (power loss, Ctrl-C): a dead run's staging
  directories and receipt temps are cleaned automatically under the install
  lock. Recovery: re-run this exact command; it succeeds.
- A second concurrent installer prints `another install is already running
  for this root; let it finish before retrying`. Recovery: wait, re-run.

### Step 4 — build the server bundle

Build (only `apps/web/dist` can be reused if present; rebuild if in doubt):

```
cd ~/.mastermind/mmos_dev/tsh/source/t3-pin0770446
./node_modules/.bin/vp run --filter '@t3tools/web' build   # skip if apps/web/dist exists and is current
node apps/server/scripts/cli.ts build
```

Worked prints: `[cli] Bundled web app into dist/client`. Note:
`vp run --filter t3 build` does not exist in this pin (the server package
has no `build` script) — that command is the old failure, do not use it.
Server still down; this step does not touch it. Recovery: re-run; a partial
`dist/` is rebuilt in place by the same commands.

### Step 5 — pack the release

```
cd "$REPO"
~/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node \
  tools/mmos_team_server/pack_server.mjs \
  --source ~/.mastermind/mmos_dev/tsh/source/t3-pin0770446 \
  --root ~/.mastermind/t3-team \
  --release-ID t3team-0.1.7-pin0770446
```

Worked prints: `PACKInstallingProductionExternals=N` then
`PACKED version=0.1.7 server=/Users/chriswong/.mastermind/t3-team/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs files=…`
(~20–90 s, needs the network for production externals; ~345 MB on disk.)

Failure states (server still down):
- `packed runtime or its receipt already exists; …` — one line. If a previous
  pack published the tree but crashed before its config receipt landed, the
  same message names the exact `mv` that finishes the job; otherwise inspect
  before retrying (both tools refuse to overwrite — by design). Nothing new
  is published on the refusal: the receipt is staged at
  `config/server-runtime.json.new` before the publishing rename.
- **Killed mid-pack**: `.packing-*` staging from a dead run is cleaned
  automatically under the packing lock. Recovery: re-run this exact command
  with the same `--release-ID`.
- `another pack is already running for this root; let it finish before
  retrying` — a live packer holds the lock. Recovery: wait, re-run.
- `production dependency install failed (exit N): <path>` — the log path is
  unique per failure (`…-install-failure-2.log`, `-3.log`, …); read it, fix
  the cause, re-run. Nothing is published.

### Step 6 — reinstall and restart under the new runtime

```
tools/mmos_team_server/team_server.sh install --replace \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team
```

Worked prints: `INSTALLED label=com.mastermind.t3-team … server_bin=/Users/chriswong/.mastermind/t3-team/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`
and then one of exactly two truthful lines:
- `pairing access saved to ~/.mastermind/t3-team/run/access.txt (mode 0600; not printed)` — banner captured; or
- `pairing access was NOT captured (server is up; banner not in log yet) — to retry: tools/mmos_team_server/team_server.sh capture --root ~/.mastermind/t3-team --label com.mastermind.t3-team`
  — the server IS up and INSTALLED stands; only the convenience copy of the
  pairing banner is missing. Recovery is the printed `capture` command
  itself. (F29: install must never report failure for a server that is up.)

**server.log truncation at this step, and why rollback needs nothing from
it:** install truncates `run/server.log` before starting the new server so a
stale multi-GB log can never wedge the restart. What that discards is old
startup output only: each server start mints a *fresh one-time* pairing
token (the old token is dead whether or not the log survives), and a paired
browser keeps working through its session cookie, which lives in the
browser, not in the log. The rollback path below (stop → move receipts →
`install --server-bin`) reads no bytes from `server.log`. Truncation is
therefore safe for both forward operation and going back.

Failure states (checked cleanup — F15): if the server fails to come up,
install boots the label out again and verifies it; it prints either
`unloaded (cleanup verified) — fix the cause and re-run this step` (server:
down, clean; recovery: re-run this step) or
`STILL LOADED … run: launchctl bootout gui/$(id -u)/com.mastermind.t3-team`
(server: crash-looping under KeepAlive; recovery: the printed bootout, then
re-run).

### Step 7 — doctor

```
tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Worked prints `loaded=yes`, a pid, `port=3780`, `answeringPort=3780`,
`nodePath=…/runtime/node-v24.22.2-darwin-arm64/bin/node`,
`nodeVersion=v24.22.2`, `nodeExecCheck=skipped-receipt-attested`,
`treeVerified=yes`, `buildPath=…/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`,
`migrationHead=80`, log size vs cap, pairing file age — and exits 0.
`treeVerified=yes` is a full re-digest of the pinned tree against the receipt
(F23; measured cost above). `doctor` deliberately never executes the
installed Node (attesting provenance must not run the bytes under
inspection): the version line is receipt-attested, and the receipt's
`treeSha256` bound the published tree to the verified official archive at
install time — and still binds it now, re-checked. Failure prints one line
`doctor_error=<reason>` (exit 1); recovery: fix the named condition (usually
step 1 + step 6) and re-run. For one live check after migrating:

```
~/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node --version
```

Worked prints `v24.22.2`.

### Going back (part a)

```
tools/mmos_team_server/team_server.sh stop --root ~/.mastermind/t3-team --label com.mastermind.t3-team
mv ~/.mastermind/t3-team/config/node-runtime.json  ~/.mastermind/t3-team/config/node-runtime.json.migrated
mv ~/.mastermind/t3-team/config/server-runtime.json ~/.mastermind/t3-team/config/server-runtime.json.migrated
tools/mmos_team_server/team_server.sh install --replace \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team \
  --server-bin ~/.mastermind/t3-team-server/bin/t3
```

Worked prints `INSTALLED … server_bin=/Users/chriswong/.mastermind/t3-team-server/bin/t3`
— the exact pre-migration binary. Without the two runtime receipts the
runner execs `config/server-bin` directly (pre-lane behavior). **Note
(principal ruling): `--server-bin` accepts whatever executable the operator
names — it is the operator's own argument and the designed way back, not a
pinned or verified path.** The pinned Node and packed build stay on disk
unused; delete `~/.mastermind/t3-team/runtime/t3team-*` and
`runtime/node-v24.22.2-darwin-arm64` only once satisfied (a later re-migrate
must pick a new `--release-ID` or move them aside, because both tools refuse
to overwrite — by design). Down when `stop` runs (same three truthful states
as step 1), back when `INSTALLED` prints: well under a minute. To also undo
`chmod 700`: `chmod 755 ~/.mastermind/t3-team` (not recommended; 0700 is the
safer state).

### Part (b) — apply the short names with `team_roster.py apply`

Commits `859282b2f`/`9b733b1d7` (teammate thread recovery + short names)
must be merged. Apply is idempotent and drives renames of saved threads to
the canonical titles `Assurance — quality` and `Design Lead — product`:

```
cd "$REPO"
TEAM_ROSTER_NODE=~/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node \
/opt/homebrew/bin/python3.12 tools/mmos_team_server/team_roster.py apply \
  tools/mmos_team_server/specs/team_roster.json
```

Worked prints a JSON report (`project`, per-teammate state with thread ids
and titles, and a `pin` note) and exits 0. If the spec has no paired
`browser_profile`, stale titles cannot be renamed headlessly: apply prints
`title renames pending: browser_profile is not configured` and exits 1
without claiming convergence — then either set `browser_profile` to a
private, already-paired profile directory under the server root and re-run,
or rename the two threads in the web client by hand. The server can be
running; `apply` also works while it is stopped. Going back: the previous
titles live in the thread records and `team_roster_state.json`; re-running
apply with the old spec text restores them the same way (rename is the only
mutation — no thread is deleted).

## What this lane changed in the repo

`tools/mmos_team_server/node_install.py` (rewritten installer: F1–F8,
F22–F23, F27–F28, F29-adjacent one-line errors, item 12 pinned resolve with
in-tree receipt cross-check, item 13 interpreter recording, install lock +
dead-leftover cleanup, schema-2 tree digest over every entry, refusal before
publish), `pack_server.mjs` (containment scope check; corrected `stateDbPath`
in the receipt; F12 staged config receipt before the publishing rename; F24
unique failure logs; F25 packing lock + leftover cleanup; schema 2),
`team_server.sh` (live-root probe before packed-runtime resolution; label
validation on every command; fixed-string plist scan; byte-offset pairing
capture with checked mv; symlinked-subdir refusal and owned-subdir
tightening; 0700 root requirement; private umask; F9 honest selftest; F10
canonical ports; F14 truthful three-state stop; F15 checked failed-start
cleanup; F18–F21 checked writes and atomic port files; F29 INSTALLED +
capture subcommand; explicit absolute interpreter), `server_runner.sh`
(F13 PATH order; F21/F28 one-line refusals instead of tracebacks; item 13
recorded-interpreter execution with `-I`), `tools/mmos_dev/t3_dev.sh`
(fail-closed single port probe; canonical ports; honest selftest; F16
non-destructive banner capture), the test files (runtime, ops, findings,
node pack suite), this document. A second attack round (14 findings, all
in-scope ones fixed with tests) also drove: receipt-bound `treeSha256` tree
verification on the installer's repair branch, no-`~/.t3`-creation on a scope
refusal, and a doctor that never executes the installed Node. This hardening
slice (tshc) closed reviewer findings F1–F29 and items 12/13; the TSHc
attack round's verdicts are recorded in
`~/.mastermind/mmos_evidence/tshc-20261111/LEDGER.md`.
