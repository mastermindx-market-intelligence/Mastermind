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
on by default (`--no-verify-tree` exists for emergencies only). The packed
**server** tree is verified the same way, against the
`file-digests.json` the packer writes beside `dist/` (panel R1): every
recorded file's size and sha256 re-checked, and any file in the tree that the
pack never recorded refuses — at every resolve, at runner boot, and in
`doctor`, which prints `treeVerified=node+server` and the verified file count
(`serverTreeFiles`). A real pack is ~4500 files / 344 MB and a full hash
measures ~15 s per pass, so after a file's digest matches the record once its
`(size, mtime_ns, ctime_ns)` triple is cached in
`verify-stat-cache.json` beside the record and later verifies skip re-hashing
it (install measured 2:39 → 51 s, doctor 15 s → 5 s). Any rewrite, truncate,
chmod or replace changes at least one of those three — ctime is kernel-set
and cannot be restored without root — so a changed file falls back to a full
digest and refuses; deleting the cache file only costs a slow pass.
`buildDir` is pinned to
`<root>/runtime/<release-ID>/dist` (panel R3), and with the receipts installed
`config/server-bin` is no longer an override — the runner refuses a
contradiction at boot (panel R2). `launchctl`, `curl`, `lsof`, `stat` and `ps`
are invoked by absolute path, like python3 (panel R8).

The **provider CLI is pinned the same way** (item F): after the switch the
server reported `Claude Agent CLI (claude) was not found on PATH` because the
runner's PATH was node + system dirs while `claude` lives in `~/.local/bin`.
`install` now discovers the provider CLI (`--provider-cli <absolute path>`,
or the `PROVIDER_CLI_BIN` operator knob, or `claude` on the installing
shell's PATH), validates it — an absolute regular executable whose folder
AND whose symlink-resolution target tree contain nothing a teammate can
write (group/other write refused on every ancestor unless the sticky bit is
set; owners must be root or this user; the stock install's
`~/.local/bin/claude -> ~/.local/share/claude/versions/<v>` symlink is
exactly why both trees are walked) — and records the binary's folder in
`config/provider-cli-dir` (0600, one atomic write, like
`config/python3-path`). Missing or invalid refuses the install with a named
reason; it is never silently dropped. The runner adds that folder to the
server's PATH (both the pre-resolve export and the packed-exec PATH rebuild
— the latter is the exact line the defect lived in) and refuses to boot
without the record, so a pre-item-F root fails loudly at `stage
refused-provider` instead of quietly serving a server whose teammates
cannot start a Claude run. `doctor` reports the record as
`providerCliFolder=<folder>`.

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

**Limits worth naming.** The production externals inside the packed tree are
fetched from the network at pack time and are pinned only by the
`file-digests.json` the pack itself writes — there is no independent upstream
digest pin for them (panel R1 stated limit). The digest record itself — and
its stat cache — is writable by the same macOS user the root belongs to: a
same-user writer who rewrites `file-digests.json` can bless a tampered tree,
exactly as it could rewrite the receipts or the runner; the 0700 root bounds
who that user-writer is, not what it could do. And any process running as the
same macOS user can read the pairing token in `run/server.log`; teammate read
limits are what protect it.

After the next reboot, the one command to run:

```
<repo>/tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

It must print `loaded=yes`, a pid, `answeringPort=3780`,
`treeVerified=node+server` and exit 0. If it does not, run the same
`team_server.sh start` command as in rollback below.

## Runbook for the real team server

Work from a repo checkout that has this lane's branch `t3/mmos-v4-tshc`
merged. Prerequisites on this Mac (all already present):
`~/.mastermind/mmos_dev/tsh/downloads/` (verified Node tarball + SHASUMS256),
`~/.mastermind/mmos_dev/tsh/source/t3-pin0770446/` (pinned T3 source with
`node_modules` installed), and `curl` on PATH (`install`/`start` refuse in
one line without it rather than timing out).

Load guidance (round 3, measured): the first switch attempt ran during
ambient load 25–107 and took 22 minutes of downtime instead of 1–3. Cause,
found and fixed on this lane's dev instance: the plist declared no
`ProcessType`, so launchd ran the job in its background I/O band, and the
runner's two per-boot tree verifies (199 MB of pinned Node re-hashed from
scratch every time) starved at 2–4 % CPU for minutes. The plist now declares
`ProcessType=Interactive` and both trees verify through stat-tripwire caches
(one full digest on first sight, triples thereafter). Post-fix the same
sequence is minutes of work even at load ≈ 50, and install's wait no longer
gives up on a live boot: while `run/boot.status` shows a fresh pre-exec
stage, install keeps waiting (60 s extensions, 900 s cap) and prints
`still starting (verifying: …)`. Prefer a quiet machine anyway — step 3's
extraction and step 5's pack are plain disk work — but load is no longer a
correctness risk for step 6.

Every numbered step below states: what worked prints, what the server state
is when the step fails, and the exact recovery command. "Nothing is published
on a refusal" is now literally true for both installers: they stage
privately, run every check that can refuse, and only then perform the single
publishing rename.

### Preconditions — check these before step 1 (none prints a secret)

```
uptime                                                  # migrate when 1-min load < 50
cd <repo> && git merge-base --is-ancestor t3/mmos-v4-tshc HEAD && echo merged
ls ~/.mastermind/mmos_dev/tsh/downloads/                 # tarball + SHASUMS256
test -d ~/.mastermind/mmos_dev/tsh/source/t3-pin0770446/node_modules && echo deps-ok
command -v curl
test -x ~/.mastermind/t3-team-server/bin/t3 && echo rollback-binary-ok
test -f ~/.mastermind/t3-team/config/python3-path && echo interpreter-ok
```

`uptime`: record the load — the runbook's downtime statements assume it
(see the load guidance above; a loaded machine is no longer a correctness
risk for step 6, but the first boot after THIS paragraph's fix still pays
one full digest per tree on first sight, so expect the upper end of the
range when loaded). `rollback-binary-ok`: the
documented rollback boots that exact binary — no step touches it, but if it
is missing there is no going back. `interpreter-ok`: **if you abort between
step 1 and step 3's completion, re-run step 3 before rolling back** — the
rollback runner needs `config/python3-path`, which only step 3 writes (its
repair branch re-records it); `install --server-bin` now refuses up front,
naming step 3, instead of installing a job that crash-loops at runner
exit 78.

### Step 0 — check no teammate run is live

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 ~/.t3/bin/t3 thread list
ps ax -o args= | grep -F '.mastermind/t3-team/claude-home' | grep -v grep
```

Worked looks like: the thread list shows only terminal states (`done`,
`failed`, `idle` — nothing `running`), and the `ps` line prints nothing.
Downtime: none yet. If a thread is running: **default — wait up to 10
minutes for it to finish; if it is still running then, stop it through its
own client (the thread's stop control), never by killing the server
process.** Reason: a clean stop lets the thread record its final state; a
killed server loses nothing durable (state is in sqlite) but leaves untidy
history. Recovery: none needed; this step observes only.

### Part (a) — move to the pinned Node and the packed build

Downtime for the whole part: **about one minute of actual stop-to-answer
when steps 3–5 are done first** — step 3 (node install, ~4½ min measured)
and step 5 (pack, ~2½ min measured) do not need the server down and can be
run BEFORE step 1; the stop→reinstall→answer span itself measured 22 s from
a cold page cache at load ≈ 50 (282 s before the round-3 fixes at load ≈ 30;
see `~/.mastermind/mmos_evidence/tshc-20261111/probe-round3/`). If you run
the steps strictly in order instead, add the step-3/5 durations to the
downtime. Threads and history are preserved; the
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
- `STOPPED label=… (unloaded) but our server pid N is still closing port 3780`
  — the job is gone; its own process is still shutting its socket down after
  SIGTERM. Server: stopping. Recovery: none — re-check in a moment with
  `lsof -nP -iTCP:3780 -sTCP:LISTEN`; it frees the port as it exits.
- `STOPPED label=… (unloaded) but port 3780 is still held by another process
  (pid N)` — the label is gone and the holder is NOT our server (its pid is
  named). Server: stopped, port occupied. Recovery:
  `lsof -nP -iTCP:3780 -sTCP:LISTEN` to identify pid N, stop it, then re-run
  the stop command to see `… free`. **Default for the identified holder —
  `ps -p <pid> -o args=` it first: if it is a teammate session's own dev
  server, stop it through that session's tool; otherwise `kill <pid>` (plain
  TERM, not -9).** Reason: the tool names the pid, but only you can tell a
  teammate's live work from a stray listener; -9 denies it a clean shutdown.
- `STOP_FAILED no port file and …/run/home.lock is HELD` — there is no port
  file (or the label was never loaded) but a server is still serving this
  root outside launchd. Server: running. Recovery: the printed `ps` line
  names it; stop that process, re-run stop.

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
intact it re-verifies the whole tree against the official archive and prints
the same line with the suffix `(activation repaired; tree verified)` — and
that repair completes the ENTIRE activation, re-recording the interpreter
too, so a retry after any interruption leaves a startable runtime.

Failure states (server still down):
- Any refusal prints one line `team_runtime: <reason>` (bad checksum, unsafe
  root, conflicting receipt — the message names the exact
  `mv … .conflict` recovery when an outside receipt conflicts). On a
  refusal **nothing is published**: the extract happens in a private staging
  directory and every check that can refuse fires before the publish rename.
  Recovery: fix the named condition, re-run this step.
- **Killed mid-extract** (power loss, Ctrl-C): a dead run's staging
  directories and receipt temps (including `config/python3-path.tmp`) are
  cleaned automatically under the install lock. Recovery: re-run this exact
  command; it succeeds.
- **Killed (or an OS error) in the instant after the publish rename**: the
  tree is left on disk with some activation markers missing — that is not a
  refusal and not a broken state; nothing else was published. Recovery:
  re-run this exact command; the repair branch verifies the tree against the
  archive and completes the whole activation, then prints the
  `(activation repaired; tree verified)` line above.
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

**Dist-reuse default:** rebuild unless the bundle is provably current —

```
find apps/web/src apps/web/index.html -newer apps/web/dist | head
```

prints nothing. Reason: a stale client bundle serves an old UI silently;
the rebuild costs seconds, the doubt costs a confused teammate.

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

**Release-ID default:** `t3team-<server-version>-pin<short-source-sha>` for
the first pack of a source pin; a re-pack of the same source appends `-2`,
`-3`, … — never reuse an existing release-ID, because both installers
refuse to overwrite by design. (The digest list beside `dist/` makes every
later resolve verify exactly this pack, panel R1.)

Failure states (server still down; every pack refusal prints exactly ONE
stderr line, `pack_server: <reason>` — never a Node stack trace):
- `packed runtime or its receipt already exists; …` — one line. If a previous
  pack published the tree but crashed before its config receipt landed, the
  NEXT pack finishes that publish automatically first (`PACKFinishedInterruptedPublish=…`
  on stdout, validated against the release it names) and then still refuses
  the re-pack; there is no manual `mv` any more. The receipt travels inside
  the release (`PUBLISH_RECEIPT.json`), so the publishing rename publishes
  tree and receipt together; the config copy after it is idempotent.
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

Item F: this step also records the provider CLI's folder
(`config/provider-cli-dir`) — `claude` is discovered on the installing
shell's PATH (`~/.local/bin`); pass `--provider-cli <absolute path>` to name
it explicitly. If no `claude` is found, or the folder fails the
teammate-writability validation, install refuses in one line naming the
condition and the flag; fix and re-run.

Worked prints: `INSTALLED label=com.mastermind.t3-team … server_bin=/Users/chriswong/.mastermind/t3-team/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`
and then one of exactly two truthful lines:
- `pairing access saved to ~/.mastermind/t3-team/run/access.txt (mode 0600; not printed)` — banner captured; or
- `pairing access was NOT captured (server is up; banner not in log yet) — to retry: tools/mmos_team_server/team_server.sh capture --root ~/.mastermind/t3-team --label com.mastermind.t3-team`
  — the server IS up and INSTALLED stands; only the convenience copy of the
  pairing banner is missing. Recovery is the printed `capture` command
  itself, run while the server is running: `capture` saves only a banner it
  sees appended live, or — when the server was already up before the call —
  the last logged banner of a server it verifies is loaded AND answering
  HTTP 200 right now **from this job's own process** (panel R4: a foreign
  loopback listener answering 200 is named and never passes). On a stopped
  server it refuses: that banner's one-time token is dead and is never saved
  as the credential. (F29: install must never report failure for a server
  that is up.)

  Missed-banner retry cadence (default): a healthy boot appends the banner
  within seconds. Run the printed `capture` command once after ~30 s and once
  more after 2 minutes; if it still reports not captured, the banner never
  came — open the web client for the live pairing URL instead of waiting
  longer.

The success line itself is attributed (panel R4): `INSTALLED` prints only
when the HTTP 200 on the port comes from the launchd job's own pid (or its
direct child). A same-user impostor holding the port refuses the install with
the impostor's pid named and the label booted out again; `doctor` names the
same state `answeringProcess=foreign(...)`.

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
re-run). A failed `team_server.sh start` does the same (panel R7): the label
is booted out and verified — `START_FAILED … (label unloaded, cleanup
verified)` — instead of being left crash-looping every 10 s.

**What a slow first boot looks like now (round 3 B).** The runner announces
every boot stage as it happens — on screen via install's wait and in
`<root>/run/boot.status` as `stage=<name> <epoch>` lines
(`pre-flight`, `resolve-node`, `verify-node`, `resolve-server`,
`verify-server`, `lock-port`, `exec-server`; the verify stages heartbeat
every 500 files while hashing; and the terminal refusal stages
`refused-python3` / `refused-provider` for a missing interpreter or provider
record). While the wait window runs you see a line
every ~15 s: `waiting for first answer on 127.0.0.1:3780 — Ns elapsed, boot
stage: verify-node`. If the base 180 s window expires while the LAST stage
is still pre-exec, fresh (<30 s since its last heartbeat) and the job pid is
alive, install does NOT boot the job out — it prints `still starting
(verifying: <stage>; Ns since its last progress, job pid P alive) —
extending the wait 60s` and keeps waiting (extensions capped at 900 s
total). This is what the real switch needed and did not have: both failed
installs killed a job that was still hashing its trees. A boot that reached
`exec-server` and still does not answer gets NO extension — the server
itself owns the answer past that line, and the R7 cleanup fires exactly as
before, with the failure now naming the last stage and its age: `server did
not answer on 127.0.0.1:3780 (last stage: exec-server, Ns ago; see
~/.mastermind/t3-team/run/boot.status)`. An empty `server.log` therefore
never again reads as "working": the stage lines land in it (via stderr) and
in boot.status from the first second. A `refused-*` stage is terminal: the
wait never extends into a config refusal crash-loop — install/start fail
immediately with `last stage: refused-provider, Ns ago` (item F) and the
runner's one-line reason (with its recovery) is the line before it in
`server.log`.

### Step 7 — doctor

```
tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Worked prints `loaded=yes`, a pid, `port=3780`, `answeringPort=3780`,
`answeringProcess=ours`, `jobPlist=~/Library/LaunchAgents/com.mastermind.t3-team.plist`,
`nodePath=…/runtime/node-v24.22.2-darwin-arm64/bin/node`,
`nodeVersion=v24.22.2`, `nodeExecCheck=skipped-receipt-attested`,
`buildPath=…/runtime/t3team-0.1.7-pin0770446/dist/bin.mjs`,
`treeVerified=node+server` with `serverTreeFiles=<N>` (both trees re-verified
against their receipts, F23 + panel R1 — freshly hashed or tripwire-cached as
above), `providerCliFolder=/Users/chriswong/.local/bin` (item F: the folder
install recorded; a pre-item-F root prints
`providerCliFolder=missing (pre-item-F root; re-run install to record it)`),
`migrationHead=80`, log size vs cap,
pairing file age — and exits 0. On a rollback root (receipts moved aside) the
same block prints `treeVerified=none(rollback)` and the operator-named
binary as `buildPath`, instead of refusing. `doctor` deliberately never
executes the installed Node (attesting provenance must not run the bytes
under inspection): the version line is receipt-attested, and the receipt's
`treeSha256` bound the published tree to the verified official archive at
install time — and still binds it now, re-checked. `answeringProcess=ours`
means the HTTP 200 came from this job's own pid or its direct child; a
foreign responder, or a job loaded from a foreign plist (a /tmp squat,
panel atk-7), prints its own `doctor_error=` naming it and exits 1. Round 3
C: an lsof that returns NOTHING (a loaded machine can be that slow) is
reported as what it is — attribution UNKNOWN, never "foreign":
`answeringProcess=unknown(no listener identified by lsof; job pid N — retry
doctor, or probe: lsof -a -p N -tP -iTCP:3780 -sTCP:LISTEN -n)` with exit 1
and `health is unverified until attribution says ours`. During the real
switch the first doctor call wrongly said foreign for exactly this reason;
the re-run a minute later said ours. Failure
prints the metadata block and then one line `doctor_error=<reason>` (exit 1)
— including the two down states `doctor_error=label not loaded` and
`doctor_error=port N not answering`, each naming runbook step 6 as the
recovery — and on a rollback root that recovery line names the rollback
binary with the full argument set (`install --replace --root … --label …
--port … --server-bin …`), so it is runnable exactly as printed (panel
LOW 13). Two flags round out the tool (round 3): `doctor --full` re-hashes
both trees in full, past the stat caches, when a cached verdict is not
enough; `doctor --port N` checks a named port when `run/port` is unreadable.
For one live check after
migrating:

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
runner execs `config/server-bin` directly (pre-lane behavior). With the
receipts still in place `config/server-bin` is NOT an override: the runner
refuses at boot if it contradicts the receipts (panel R2) — moving both
receipts aside, as above, is the supported way to run another binary.
**Note (principal ruling): `--server-bin` accepts whatever executable the
operator names — it is the operator's own argument and the designed way back,
not a pinned or verified path.** `install --server-bin` also refuses up
front when `config/python3-path` is missing, naming runbook step 3 (panel
R5): the rollback runner needs that interpreter record, and only step 3
writes it — if you aborted before step 3 completed, re-run step 3 first
(its repair branch re-records the interpreter), then roll back. The pinned
Node and packed build stay on disk
unused; delete `~/.mastermind/t3-team/runtime/t3team-*` and
`runtime/node-v24.22.2-darwin-arm64` only once satisfied (a later re-migrate
must pick a new `--release-ID` or move them aside, because both tools refuse
to overwrite — by design). **Cleanup default: keep both trees for 48 hours
of confirmed rollback use, then delete; a later re-migrate picks a NEW
release-ID either way.** Reason: deleting early forces a full re-download and
re-pack under time pressure; keeping them longer costs only disk. Down when
`stop` runs (same three truthful states
as step 1), back when `INSTALLED` prints: well under a minute. To also undo
`chmod 700`: `chmod 755 ~/.mastermind/t3-team` — **default: leave it at
0700.** Reason: the root holds `fabric.env`, logs and thread state; 0755
exposes them to every other local account for no operational gain.

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
without claiming convergence — **default: rename the two threads by hand in
the web client (two clicks) and move on.** Configure a private,
already-paired `browser_profile` under the server root only if you will keep
using `apply` repeatedly. Reason: pairing a profile is more setup than a
one-time rename of two threads. The server can be
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

Repair round 2 (panel `…/panel/SCORE.md` on `c89427598`, all findings
addressed with a failing test first): R1 server-tree digest verification at
resolve/runner-boot/doctor with the `verify-stat-cache.json` tripwire so a
real 4500-file/344 MB pack boots in seconds instead of paying three 15 s
hash passes; R2 `config/server-bin` boots only in rollback mode (receipts
present → a contradiction refuses at boot); R3 `buildDir` pinned to
`<root>/runtime/<release-ID>/dist`; R4 the HTTP-200 answer attributed to the
launchd job's pid at install/doctor/capture/start (`answeringProcess`,
`jobPlist`); R5 install refuses a `--server-bin` root without a valid
`config/python3-path`, naming runbook step 3; R6 uninstall refuses to print
UNINSTALLED while the label is still loaded; R7 a failed start boots the
label out and verifies, naming the recovery; R8 `launchctl`/`curl`/`lsof`/
`stat`/`ps` by absolute, env-seam-testable path; LOW 3 static refusals
before the bootout (the home.lock pre-check keeps attack-a4 semantics with
holder attribution), LOW 4 plist written temp+rename, LOW 10 run-file
symlink refusals, LOW 13 doctor's recovery line carries the full argument
set and is runnable verbatim. Probes on this lane's own instance:
atk-7 label squat from a `/tmp` plist — doctor prints `jobPlist=<foreign>`
with a foreign-plist `doctor_error` (exit 1) and stop acts on the label,
booting the squatter out; q4-9 the home.lock fd is held on the exec'd node
pid by design (fd 3, inheritable so it survives execve) and at idle the
server has no children inheriting it — a surviving inheritor would be caught
fail-closed by stop/install's lock re-check. Evidence:
`~/.mastermind/mmos_evidence/tshc-20261111/probe-round2/`.

Repair round 3 (the real switch on `3f79ffc40` was switch-ready but took 22
minutes of downtime instead of 1–3; cause found on this lane's dev instance
before any fix): A the plist now declares `ProcessType=Interactive` (launchd
had put the job in its background I/O band, where the runner's two per-boot
tree verifies starved) and the pinned Node tree verifies through a
`runtime/node-tree-stat-cache.json` tripwire exactly like the server tree's,
so a healthy warm boot hashes nothing (the receipt stays the anchor: any
mismatch falls back to the full digest and refuses on difference); B the
runner records every boot stage to stderr AND `run/boot.status`
(`stage=<name> <epoch>`, verify heartbeats every 500 files) and install's
wait extends past the base window while the last stage is pre-exec, fresh
and alive — printing `still starting (verifying: …)` — instead of booting a
working job out (a post-`exec-server` silence still gets the R7 cleanup,
now naming the last stage and its age); C attribution treats an empty lsof
as UNKNOWN with a retry hint, never "foreign" (doctor exits 1 on unknown:
health unverified); D this runbook's downtime and load statements above now
match the post-fix measurements. Follow-ups from the round-2 panel's tail:
FU1 the `load -w`/`unload` fallbacks run `env -i` too; FU2/FU4 every
`MMOS_*`/`TEAM_SERVER_LAUNCHAGENTS_DIR` test seam is refused unless
`MMOS_TEST_SEAMS=1` (PYTHON3_BIN stays an operator knob; the one seam the
RUNNER honors — the slow-verify valve used to test install's wait — travels
as `<root>/config/verify-delay`, because launchd starts the runner with no
environment at all); FU3 `doctor
--full`; FU5 the runner's exit-78 recovery names runbook step 3; FU6 a
failed `kickstart` dies truthfully naming the untouched running job; FU7
`doctor --port N`; FU8 a failed plist heredoc dies at once (temp+rename
kept); FU9 uninstall verifies the root is actually down before printing
UNINSTALLED; FU10 pack embeds `PUBLISH_RECEIPT.json` in the release so the
publishing rename carries tree and receipt together, and the next pack
auto-finishes an interrupted publish (no manual `mv`).
Evidence: `~/.mastermind/mmos_evidence/tshc-20261111/probe-round3/`.
