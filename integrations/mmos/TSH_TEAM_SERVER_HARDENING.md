# TSH — team server hardening: pinned Node and a packed build

The team server (`com.mastermind.t3-team`, 127.0.0.1:3780, root
`~/.mastermind/t3-team`) today runs the Node that Homebrew happens to
provide, from a binary inside the 4.3 GB source checkout
`~/.mastermind/t3-team-server/`. A routine `brew upgrade` or a moved
directory breaks it while nobody is looking. This lane replaces both halves
with artifacts under the server's own root:

- **Pinned Node v24.22.2** (official nodejs.org darwin-arm64 tarball,
  SHA-256 `aa9549…385a`, verified against SHASUMS256) at
  `<root>/runtime/node-v24.22.2-darwin-arm64/`, installed by
  `tools/mmos_team_server/node_install.py` — whose review findings F1–F8 are
  all fixed, each with a test in `tests/test_mmos_team_server_runtime.py`.
- **Packed server build** (`pack_server.mjs`): the built server bundle, the
  history worker, the web client and the production externals in one
  self-contained directory `<root>/runtime/<release>/dist`, published by one
  rename with an in-tree `BUILD_RECEIPT.json` and a config receipt
  `config/server-runtime.json`. The source tree is not needed at runtime.

Proven on the dev root `~/.mastermind/mmos_dev/tsh/team-root` (label
`com.mastermind.t3-team-dev-tsh`, port 50809; evidence
`~/.mastermind/mmos_evidence/tsh-20261110/`): install; server answering under
the pinned Node with the packed build; `kill -9` and `launchctl kickstart -k`
each revive in ~3 s with the same thread id; with the whole source tree
moved aside the server restarts, answers, serves the web client (index +
hashed asset 200) and keeps the thread; `doctor` prints health metadata with
no credential.

**Not proven** (by design of this lane): logout/reboot behavior (RunAtLoad
starts the job at login; KeepAlive restarts the process if it dies or is
killed — neither is a reboot test), multi-day stability, and the real root
itself — every command below is the principal's act on the real server.

After the next reboot, the one command to run:

```
<repo>/tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

It must print `loaded=yes`, a pid, `answeringPort=3780` and exit 0. If it
does not, run the same `team_server.sh start` command as in rollback below.

## Runbook for the real team server

Work from a repo checkout that has this lane's branch `t3/mmos-v4-tshb`
merged. Prerequisites on this Mac (all already present):
`~/.mastermind/mmos_dev/tsh/downloads/` (verified Node tarball + SHASUMS256),
`~/.mastermind/mmos_dev/tsh/source/t3-pin0770446/` (pinned T3 source with
`node_modules` installed).

### Step 0 — check no teammate run is live

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 ~/.t3/bin/t3 thread list
ps ax -o args= | grep -F '.mastermind/t3-team/claude-home' | grep -v grep
```

Worked looks like: the thread list shows only terminal states (`done`,
`failed`, `idle` — nothing `running`), and the `ps` line prints nothing.
Downtime: none yet. If a thread is running, wait for it or stop it before
continuing — the migration restarts the server.

### Part (a) — move to the pinned Node and the packed build

Downtime for the whole part: about one to three minutes (stop → install →
pack → reinstall → server answers). Threads and history are preserved; the
pairing cookie in a paired browser keeps working (proven in T6: no re-pair
after restart).

```
cd <repo>
REPO=$PWD
tools/mmos_team_server/team_server.sh stop --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```
Worked prints: `STOPPED label=com.mastermind.t3-team port=3780 free`.

```
chmod 700 ~/.mastermind/t3-team
```
Worked prints nothing. (Required by the hardened installer, and a real
hardening: the root holds `fabric.env`, logs and thread state.)

```
/opt/homebrew/bin/python3.12 tools/mmos_team_server/node_install.py install \
  --root ~/.mastermind/t3-team \
  --archive ~/.mastermind/mmos_dev/tsh/downloads/node-v24.22.2-darwin-arm64.tar.gz \
  --checksum ~/.mastermind/mmos_dev/tsh/downloads/SHASUMS256-v24.22.2.txt
```
Worked prints: `NODE_INSTALLED version=v24.22.2 node=/Users/chriswong/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node sha256=aa9549…`
(~40 s: copy, hash, member check, extract, atomic publish.) Refuses and
prints `team_runtime: …` if anything is off; nothing is published on a
refusal. Server still down.

Build (only `apps/web/dist` can be reused if present; rebuild if in doubt):

```
cd ~/.mastermind/mmos_dev/tsh/source/t3-pin0770446
./node_modules/.bin/vp run --filter '@t3tools/web' build   # skip if apps/web/dist exists and is current
node apps/server/scripts/cli.ts build
```
Worked prints: `[cli] Bundled web app into dist/client`. Note:
`vp run --filter t3 build` does not exist in this pin (the server package
has no `build` script) — that command is the old failure, do not use it.
Server still down; this step does not touch it.

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
Refuses if a packed runtime or its receipt already exists — inspect before
retrying.

```
tools/mmos_team_server/team_server.sh install --replace \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team
```
Worked prints: `INSTALLED label=com.mastermind.t3-team … server_bin=/Users/chriswong/.mastermind/t3-team/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`
and `pairing access saved to ~/.mastermind/t3-team/run/access.txt (mode 0600; not printed)`.
The server is back up when this returns (it waits for HTTP on 3780; downtime
ends here).

```
tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```
Worked prints `loaded=yes`, a pid, `port=3780`, `answeringPort=3780`,
`nodePath=…/runtime/node-v24.22.2-darwin-arm64/bin/node`,
`nodeVersion=v24.22.2`, `buildPath=…/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`,
`migrationHead=80`, log size vs cap, pairing file age — and exits 0.

#### Going back (part a)

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
runner execs `config/server-bin` directly (pre-lane behavior). The pinned
Node and packed build stay on disk unused; delete
`~/.mastermind/t3-team/runtime/t3team-*` and
`runtime/node-v24.22.2-darwin-arm64` only once satisfied (a later re-migrate
must pick a new `--release-ID` or move them aside, because both tools refuse
to overwrite — by design). Down when `stop` runs, back when `INSTALLED`
prints: well under a minute. To also undo `chmod 700`:
`chmod 755 ~/.mastermind/t3-team` (not recommended; 0700 is the safer state).

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

`tools/mmos_team_server/node_install.py` (rewritten installer, F1–F8),
`pack_server.mjs` (unchanged this session, verified end-to-end),
`team_server.sh` (live-root probe now precedes packed-runtime resolution),
`server_runner.sh` (unchanged this session), `attack_tsh_node_install.py`
(unchanged), both test files, this document.
