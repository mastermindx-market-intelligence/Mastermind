# T6 — Mastermind team T3 server

An always-on, headless, loopback-only T3 server owned by Mastermind, kept
alive by launchd, completely separate from the Chairman's T3 Code app
(different home, different port, different label). Plain-English summary of
what was built and proven on 2026-11-10; evidence in
`~/.mastermind/mmos_evidence/t6-20261110/`.

## What it is

- `tools/mmos_team_server/team_server.sh` — `install | start | stop | status
  | uninstall | selftest` with `--root`, `--port`, `--label` (plus
  `--server-bin`, `--replace`). Reuses `tools/mmos_dev/t3_dev.sh` guards via
  its `T3_DEV_LIB_ONLY` opt-in.
- `tools/mmos_team_server/server_runner.sh` — what launchd runs: loopback
  bind, one-server-per-home via an flock held across exec, route keys only
  from the root's 0600 `fabric.env`, capped log (50 MiB or
  `<root>/config/log-cap`), minimal env.
- A user LaunchAgent plist (KeepAlive, ThrottleInterval 10): no secrets, no
  environment block. Pairing credential goes to `run/access.txt` (0600),
  never printed, logged, or put in the plist.

Refusals (23 tests in `tests/test_mmos_team_server.py`, no server started):
ports 3773/3774; root at/inside/linked-into `~/.t3`; loaded label or existing
plist without `--replace`; second label per root (plist dir and the real
`~/Library/LaunchAgents` both scanned); a root whose `home.lock` is held by
a live server; missing/wrong-mode `fabric.env`; missing server binary.

## Exact commands for the principal (real install)

```
python3 tools/mmos_dev/t3/seed_dev_home.py   # with MMOS_T3_DEV_ROOT=~/.mastermind/t3-team
tools/mmos_team_server/team_server.sh install \
  --root ~/.mastermind/t3-team --port 3780 --label com.mastermind.t3-team
tools/mmos_team_server/team_server.sh status \
  --root ~/.mastermind/t3-team --label com.mastermind.t3-team
# stop / start / remove:
tools/mmos_team_server/team_server.sh stop    --root ~/.mastermind/t3-team --label com.mastermind.t3-team
tools/mmos_team_server/team_server.sh start   --root ~/.mastermind/t3-team --label com.mastermind.t3-team
tools/mmos_team_server/team_server.sh uninstall --root ~/.mastermind/t3-team --label com.mastermind.t3-team
```

## How a window pairs; what restart does

Open `run/access.txt` (0600) and paste its Pairing URL into a browser on the
same Mac: a one-time token in the URL fragment pairs the browser, which then
holds a cookie. Proven live: `kill -9` → launchd revived the server in ~2–4s
with the same home; threads and messages survived; the cookie kept working
after restart (no re-pair needed); the pairing token itself rotates on every
server start. Off-loopback access (LAN + tailnet) is refused.

## Stock or patched server, one switch

`--server-bin` (default stock `~/.t3/bin/t3`) selects the server; stored in
`<root>/config/server-bin`, so `install --replace` with the other binary
switches one home both ways. Proven stock→patched→stock on one home
(evidence 05): same thread list, new turns worked both ways. The patched
build (T1s streaming, sha256 `37271af3a1c6…`, 8,307,715 bytes, esbuild from
a private copy of `src-textdelta`) logged a database migration-history
divergence warning against the newer stock schema (migration 80 skipped, not
reconciled — no hand-migration attempted) and still read/wrote the home
correctly. With the patched server, a six-paragraph turn showed 13 live
text changes in the browser (stock reveals the answer only at completion).

## Can one app see two servers? (item 6)

Not the desktop app: it talks to its own server; there is no "add second
environment" for another *server* connection. The supported mechanism is
`t3 environment link` (peer links, `PeerLinks.ts`; Labs setting
`linkedEnvironmentsEnabled` on both sides): pair with a code from `t3 pair`
at the peer, and the peer's threads appear grouped in the sidebar — agents
here can drive threads there. Exercised live between the two dev servers
(evidence 08) without touching the Chairman's app.

## Attack results (five attempts, evidence 09)

| # | attempt | pass 1 | pass 2 (after fix) |
|---|---------|--------|--------------------|
| 1 | credential hunt | HELD | HELD (secrets only in 0600 by-design files) |
| 2 | non-loopback reach | BYPASS* | DEFEAT (0/6; HTTP+TCP refused) |
| 3 | hostile install into ~/.t3 / 3773/3774 | DEFEAT | DEFEAT (5/5 refused) |
| 4 | two servers on one home | DEFEAT† | DEFEAT (lock + label guard) |
| 5 | crash-loop disk fill | HELD | HELD (~10 KiB/min, capped) |

\* pass-1 false positive in the attack script's curl handling (double `000`),
not a tool leak — direct probes were refused.
† pass 1 hid a real defect: an install whose plist dir was overridden
mutated a live root before failing. Fixed in e8d17a419 (dual-dir label scan
+ `home.lock` probe before any write); replay clean. The attack script child
died on a router outage after writing but before committing; the driver
reviewed, committed and patched it (63c179525) — disclosed here.

## Not proven

- Multiple concurrent teammates over days (long-run stability, memory).
- macOS restart / login-window behavior beyond RunAtLoad+KeepAlive semantics.
- The real install at `~/.mastermind/t3-team`, port 3780 — principal's to
  run; everything above was proven on dev roots 3805/3806.
- Patched build carries a known migration-history divergence vs newer stock
  schema; safe switch proven, long-term mixed use not assessed.
