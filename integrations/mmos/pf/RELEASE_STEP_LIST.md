# PF release step list — T3 server 0.1.7, source `f5248ab2`

## Final source (lead update, 2026-11-14 09:00Z)

The rehearsal below was run with source `50f25c7f`. Three later client/server
commits on the same tree (`a3de16b5` lock refusal text for tool callers,
`bcbb5c4b` product name as reply author and sidebar mark, `f5248ab2` no pull
request list in team mode) change only web/server code behind the same
`presentation` key; the pack/install mechanics are unchanged. **Use source
`f5248ab2`** and these IDs:

- staging (a): `pfnext-0.1.7-pin0770446-f5248ab2` — ALREADY LOADED on live
  staging by the lead with exactly steps 0–6 of part (a), three times
  (`a3de16b5` 08:08Z, `bcbb5c4b` 08:15Z, `f5248ab2` 08:51Z): stop 1 s, pack 5–6 s,
  answer 4–8 s, threads intact each time (`staging_repack.log`). The current
  stowed receipts are `config/server-runtime.json.rel{985027f6,a3de16b5,bcbb5c4b}`.
  Rollback target is `pfnext-0.1.7-pin0770446-bcbb5c4b`.
- real (b): **`t3team-0.1.7-pinf5248ab2`** (new, never used). Everywhere part
  (b) below says `t3team-0.1.7-pin50f25c7f` / `.rel50f25c7f`, read
  `t3team-0.1.7-pinf5248ab2` / `.relf5248ab2`.
- Before packing for (b), rebuild dist at `f5248ab2` (web `npm run build` in
  `apps/web`, then `node scripts/cli.ts build` in `apps/server`); the current
  dist is already at `f5248ab2` (`build_*_f52.log`).
- **Re-rehearsed at `f5248ab2`** (B-REHEARSE2, 09:02–09:05Z, same scratch copy,
  fake launchd, port 3831): forward stop→installed **10 s**, rollback **7 s**,
  doctor green ×3, thread lists byte-identical before/after both switches and
  to the 07:39Z baseline; real launchctl count 0; live staging untouched.
  Ledger `~/.mastermind/mmos_evidence/pf-20261114/rehearse2/LEDGER.md`. The
  one harness-only snag (fake instant `sleep` shortening `start`'s wait) cannot
  occur on the real root.
- **What running sessions see on the real server (b):** the server is down for
  about 10 s (one announced restart). A turn in progress is interrupted by the
  stop; its thread and history stay; the Chairman's app and teammate threads
  reconnect when the server answers. The new `presentation` key is absent on
  the real server, so the real client looks and behaves exactly as before.


Builder B-REHEARSE, 2026-11-14. Rehearsed END TO END on a scratch copy under
the test harness's fake launchd (principal RELEASE REHEARSAL ruling,
2026-11-12). The real team server and the live PF staging root were never
touched; no real launchd job was ever created (`/bin/launchctl list` count for
`pf.rehearse` = 0 before and after; the fake's `invocations.log` shows all 3
bootstraps and 3 bootouts landed on the fake).

- Rehearsal evidence: `~/.mastermind/mmos_evidence/pf-20261114/rehearse/`
  (LEDGER.md with every command, rc and timing; thread lists before/after).
- Scratch copy: `~/.mastermind/mmos_dev/pf/rehearse/root` — release N =
  `pfnext-0.1.7-pin0770446-985027f6` (cloned from staging), release N+1 =
  `pfnext-0.1.7-pin0770446-50f25c7f` packed from
  `/Volumes/Mastermind/build-cache/pf-t3code` (dist current at `50f25c7f`).
- Tools used unmodified: `tools/mmos_team_server/{team_server.sh,
  pack_server.mjs, node_install.py, server_runner.sh}` at branch
  `t3/mmos-v4-pf`, commit `6f894b17c`.

## Rehearsal result

| Leg | Measured (stop → INSTALLED/answer) |
|---|---|
| Forward switch N → N+1 (launchd path) | **84 s** total; components: stop 1 s, pack 6 s, `install --replace` 20 s. The remaining ~57 s was diagnosing two scratch-environment refusals (below) that cannot occur on the real root. |
| Rollback N+1 → N (launchd path) | **8 s** (stop 1 s, receipt swap 0 s, `install --replace` 7 s) |
| Staging-style detached runner start (no launchd) | 6 s to HTTP 200 (3 s to `exec-server`) |
| Staging-style stop (TERM to `run/runner.pid`) | 1 s; pid, children and port all verified gone |

For comparison, the real `-3` switch
(`~/.mastermind/mmos_evidence/tshc-20261111/switch-rel3.log`) measured 147 s
(pack 55 s, install 65 s) at similar load. Plan for **1–3 minutes** of downtime
on the real server; the rehearsal's clean mechanical path was ~27 s.

Threads survived both legs: `thread list` before, after forward, and after
rollback are byte-identical (2 threads, `Scout — research`, `Writer — writing`,
both `completed`). `doctor` printed `loaded=yes`, `answeringProcess=ours`,
`treeVerified=node+server`, `serverTreeFiles=4498`, `migrationHead=80` on all
three boots.

### Refusals and surprises hit in the rehearsal (tools NOT patched)

1. **`pack_server.mjs` refuses under a HOME without `~/.t3`**: its containment
   check does `realpathSync(os.homedir() + "/.t3")` and dies
   `pack_server: ENOENT … lstat '<HOME>/.t3'` when that path is absent. The
   real operator HOME has `~/.t3`, so this never fires on the real server; it
   only bites harness/scratch HOMEs. Rehearsal fix: run pack with the real
   HOME (pack never touches launchd). No tool change.
2. **pack requires `<root>/runtime` mode 0700** (`private current-user-owned
   mode 0700 directory required`). A freshly `mkdir`-ed runtime dir is 0755
   under the default umask. The real root's runtime is already 0700.
   Rehearsal fix: `chmod 700 runtime`. No tool change.
3. **`t3 thread list` needs a project**: bare `thread list` refuses
   `No T3 Code project matches '.'`. Pass `--project <id or path>` (the
   runbook's step-0 form works when run from inside a registered project dir).
4. **`team_server.sh doctor` is launchd-specific** — on a plain nohup root
   (PF staging) it would report `label not loaded`. Staging verification is
   port probe + `boot.status` + `thread list` instead (part a).
5. Rehearsal-only adaptations, NOT part of the real steps: the copied
   receipts' absolute paths were rewritten staging→scratch (the resolver
   enforces `<root>/runtime/...` containment, so this was mandatory; real
   receipts already name their own root), and a dummy `fabric.env`
   (`ANTHROPIC_BASE_URL=http://127.0.0.1:1`, mode 0600) replaced the real one,
   which was never copied or opened.

## (b) Real team server — `~/.mastermind/t3-team`, port 3780

New release: source `/Volumes/Mastermind/build-cache/pf-t3code` at `50f25c7f`
(web and server dist already built — do NOT rebuild). Release ID
**`t3team-0.1.7-pin50f25c7f`** (the hardening runbook's default
`t3team-<version>-pin<short-source-sha>` for a new source pin; never reuse an
existing ID). Current real release is `t3team-0.1.7-pin0770446-3`; its receipt
is stowed as `.rel3` below. The rehearsal used the PF-lane ID
`pfnext-0.1.7-pin0770446-50f25c7f` for the same source; mechanics identical.

### Preconditions (none prints a secret)

```
uptime                                   # prefer 1-min load < 50
command -v curl
test -x ~/.mastermind/t3-team-server/bin/t3 && echo rollback-binary-ok
test -f ~/.mastermind/t3-team/config/python3-path && echo interpreter-ok
test -d ~/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64 && echo node-ok
test -f /Volumes/Mastermind/build-cache/pf-t3code/apps/server/dist/bin.mjs && echo dist-ok
stat -f '%Lp' ~/.mastermind/t3-team ~/.mastermind/t3-team/runtime   # both 700
```

All already hold on the real root (it runs the packed `-3` release today).
`rollback-binary-ok` matters only for the legacy pre-migration rollback; the
primary rollback here is to packed release `-3`, which stays on disk.

### Step 0 — no live teammate run

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 ~/.t3/bin/t3 thread list --project <team project id or path>
ps ax -o args= | grep -F '.mastermind/t3-team/claude-home' | grep -v grep
```

Worked: only terminal thread states (`done`/`failed`/`idle`/`completed`), the
`ps` line prints nothing. If a turn is running: wait up to 10 min, then stop
it through its own client's stop control — never by killing the server.
(Rehearsal: observed — baseline showed 2 completed threads, 0 teammate procs.)

### Step 1 — stop

```
cd <repo>
tools/mmos_team_server/team_server.sh stop --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Worked: `STOPPED label=com.mastermind.t3-team port=3780 free` (exit 0).
Failure states and recoveries: hardening runbook step 1 (three truthful
stop states; all rehearsed clean here). Downtime starts here.

### Step 2 — stow the current release receipt

```
mv ~/.mastermind/t3-team/config/server-runtime.json ~/.mastermind/t3-team/config/server-runtime.json.rel3
```

Required: `pack_server.mjs` refuses while `config/server-runtime.json` exists
(`packed runtime or its receipt already exists`). This is the exact order the
real `-3` switch used. Leave `config/node-runtime.json` in place — the pinned
Node is unchanged. Worked: no output, exit 0. (Rehearsal: observed.)

### Step 3 — pack the new release

```
~/.mastermind/t3-team/runtime/node-v24.22.2-darwin-arm64/bin/node \
  tools/mmos_team_server/pack_server.mjs \
  --source /Volumes/Mastermind/build-cache/pf-t3code \
  --root ~/.mastermind/t3-team \
  --release-ID t3team-0.1.7-pin50f25c7f
```

Worked: `PACKInstallingProductionExternals=10` then
`PACKED version=0.1.7 server=~/.mastermind/t3-team/runtime/t3team-0.1.7-pin50f25c7f/dist/bin.mjs files=4498`
(rehearsal: 6 s with warm caches; `-3` real: 55 s; needs network for
production externals). Refusals are one `pack_server: <reason>` line; killed
mid-pack → re-run the same command (staging debris auto-cleans under the
lock). Nothing is published on a refusal. (Rehearsal: observed, including the
two environment refusals listed above.)

### Step 4 — reinstall and restart

```
tools/mmos_team_server/team_server.sh install --replace \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team
```

Worked: `INSTALLED label=com.mastermind.t3-team … server_bin=…/t3team-0.1.7-pin50f25c7f/dist/bin.mjs`
plus `pairing access saved to …/run/access.txt (mode 0600; not printed)`.
`INSTALLED` prints only when the HTTP 200 comes from the job's own pid.
If the banner is not captured the server is still up — retry with the printed
`capture` command (~30 s, then ~2 min). Failed boot → checked cleanup, exact
recovery printed (hardening runbook step 6). Rehearsal: 20 s, banner captured
every time. **Downtime ends at `INSTALLED`.**

### Step 5 — doctor

```
tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Worked: `loaded=yes`, a pid, `answeringPort=3780`, `answeringProcess=ours`,
`buildPath=…/t3team-0.1.7-pin50f25c7f/dist/bin.mjs`, `treeVerified=node+server`,
`migrationHead=80`, exit 0. If attribution says `unknown(...)` on a loaded
machine, re-run once (real `-3` hit this; a minute later it said `ours`).
Optional `doctor --full` re-hashes both trees past the stat caches.

### Step 6 — continuity check

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 ~/.t3/bin/t3 thread list --project <team project>
```

Worked: the same threads and titles as step 0. (Rehearsal: observed —
byte-identical lists across forward and rollback.) The principal may then run
the usual one-turn canary through a teammate, as the `-3` switch did.

### Rollback (to packed release `-3`)

```
tools/mmos_team_server/team_server.sh stop --root ~/.mastermind/t3-team --label com.mastermind.t3-team
mv ~/.mastermind/t3-team/config/server-runtime.json ~/.mastermind/t3-team/config/server-runtime.json.rel50f25c7f
mv ~/.mastermind/t3-team/config/server-runtime.json.rel3 ~/.mastermind/t3-team/config/server-runtime.json
tools/mmos_team_server/team_server.sh install --replace \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team
tools/mmos_team_server/team_server.sh doctor --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

Rehearsal measurement: **8 s** stop→INSTALLED, doctor green, threads intact.
Both release trees stay on disk; keep them ≥48 h (hardening runbook default).
The legacy `--server-bin ~/.mastermind/t3-team-server/bin/t3` rollback (both
receipts stowed) remains available exactly as in the hardening runbook's
"Going back (part a)"; it needs `config/python3-path` present.

### What running sessions see

| Effect | Status |
|---|---|
| A running teammate turn is cut off by the stop | From the `-3` runbook/design — the rehearsal had no running turn (step 0 verified). Step 0 exists to avoid this. |
| A paired window keeps its cookie and reconnects when the server answers again | From T6 proof cited in the hardening runbook and the `-3` switch — not re-observed here (no browser in the rehearsal). Each start mints a fresh one-time pairing token; the old banner token is dead, the session cookie is not. |
| Threads and history survive (sqlite in `home/userdata`) | **Observed in the rehearsal**: identical `thread list` before/after forward and after rollback. |
| Settings are re-read at boot | From the `-3` log (settings restored and re-read after its switch). The rehearsal booted with the copied settings and `migrationHead=80`; it did not mutate settings. |
| New `presentation` settings key | Read by this release (`packages/contracts/src/settings.ts`: `ServerSettings.presentation`, decoded with a default from `{}`). Fields: `productName` (""), `teamMode` (false), `lockedProviderProjectIds` ([]), `links` ([]). **Inert when absent** — the real server behaves exactly as before unless the key is set. Verified in source at `50f25c7f`; not exercised by the rehearsal. |

## (a) PF staging — `~/.mastermind/mmos_dev/pf/staging`, port 3830

Staging runs as a **plain detached runner process, not launchd**: `run/runner.pid`
holds the server pid, `run/port` holds 3830, and `bin/server_runner.sh` +
`bin/node_install.py` are in-root copies. Layout observed (names only):
`bin/{server_runner.sh,node_install.py,t3,…}`,
`config/{node-runtime.json,server-runtime.json,python3-path,provider-cli-dir,teammate-gate}`,
`run/{runner.pid,port,home.lock,boot.status,runner.out,…}`,
`runtime/{node-v24.22.2-darwin-arm64,pfnext-0.1.7-pin0770446-985027f6}`, `home/`,
`fabric.env`. Current release: `pfnext-0.1.7-pin0770446-985027f6`.

**Another builder is live on staging — the principal picks the moment; this
lane never touched it.** The pack/receipt mechanics below are the same ones
rehearsed on the copy; the detached start/stop was ALSO rehearsed on the copy
(6 s to answer; 1 s stop with pid, children and port verified gone). The only
unrehearsed detail is staging's exact original launch invocation, which is
not recorded in the root; the start command below follows `server_runner.sh`'s
contract (`/bin/sh <root>/bin/server_runner.sh <root>`, needs `run/port`,
`fabric.env`, `config/python3-path`, `config/provider-cli-dir` — all present).

New release ID: `pfnext-0.1.7-pin0770446-50f25c7f` (the exact ID rehearsed).

```
# 0. check no live turn
T3CODE_HOME=~/.mastermind/mmos_dev/pf/staging/home T3CODE_PORT=3830 \
  ~/.mastermind/mmos_dev/pf/staging/bin/t3 thread list --project ~/.mastermind/mmos_dev/pf/staging/team-project
ps ax -o args= | grep -F 'mmos_dev/pf/staging/claude-home' | grep -v grep

# 1. stop: TERM the pid file (team_server.sh stop does NOT kill a non-launchd server)
kill -TERM "$(head -1 ~/.mastermind/mmos_dev/pf/staging/run/runner.pid)"
# wait until the port is free and the pid is gone:
lsof -nP -iTCP:3830 -sTCP:LISTEN        # prints nothing when free

# 2. stow the receipt (pack refuses while it exists)
mv ~/.mastermind/mmos_dev/pf/staging/config/server-runtime.json \
   ~/.mastermind/mmos_dev/pf/staging/config/server-runtime.json.rel985027f6

# 3. pack (real HOME; runtime/ must be 0700)
~/.mastermind/mmos_dev/pf/staging/runtime/node-v24.22.2-darwin-arm64/bin/node \
  <repo>/tools/mmos_team_server/pack_server.mjs \
  --source /Volumes/Mastermind/build-cache/pf-t3code \
  --root ~/.mastermind/mmos_dev/pf/staging \
  --release-ID pfnext-0.1.7-pin0770446-50f25c7f

# 4. restart the runner detached (new session so it survives the shell), record the pid
nohup /bin/sh ~/.mastermind/mmos_dev/pf/staging/bin/server_runner.sh \
  ~/.mastermind/mmos_dev/pf/staging >> ~/.mastermind/mmos_dev/pf/staging/run/runner.out 2>&1 &
echo $! > ~/.mastermind/mmos_dev/pf/staging/run/runner.pid
# (the runner execs node in place, so $! stays the server pid)

# 5. verify: boot.status reaches exec-server, port answers, threads intact
tail -1 ~/.mastermind/mmos_dev/pf/staging/run/boot.status
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3830/    # 200
T3CODE_HOME=~/.mastermind/mmos_dev/pf/staging/home T3CODE_PORT=3830 \
  ~/.mastermind/mmos_dev/pf/staging/bin/t3 thread list --project ~/.mastermind/mmos_dev/pf/staging/team-project

# 6. point the CLI wrapper at the new release (bin/t3 hardcodes the release path)
#    rewrite bin/t3's release component to pfnext-0.1.7-pin0770446-50f25c7f
```

`doctor` does not apply (no launchd label). Expected downtime: the rehearsal's
detached leg answered in 6 s; with pack done after the stop, expect well under
a minute plus pack time.

Rollback: same stop (step 1), then
`mv config/server-runtime.json config/server-runtime.json.rel50f25c7f`,
`mv config/server-runtime.json.rel985027f6 config/server-runtime.json`,
restart (step 4), verify (step 5), restore `bin/t3` to `…-985027f6`.
Rehearsal equivalent on the copy: 8 s via the launchd path; the detached
stop/start legs measured 1 s / 6 s.