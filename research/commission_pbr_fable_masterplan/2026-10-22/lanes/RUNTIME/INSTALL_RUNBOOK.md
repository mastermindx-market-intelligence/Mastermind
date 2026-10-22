# INSTALL_RUNBOOK: W1 release (Option A), Fri 2026-10-23 04:10–05:40Z

PBR #1693, RUNTIME lane. **Commands only.** RUNTIME executed nothing on the host while writing this runbook.

| | |
|---|---|
| Approval | Seat ruling 2026-10-22: Option A, conditional; needrestart exclusion approved as a release-row item; the SDK pin is NOT in this window. |
| Executor | The seat. The deploy key is Mac-held. |
| Inputs | `INSTALL_PROOF_PLAN.md` §1 (T1–T4), §2, §4, §5 and §7. |
| Driver | `runbook/install_w1.sh`. One subcommand per step. State lives in `$PBR_EV/state.env`, so every step runs from a fresh, stateless shell. |

## 0. What is installed, and what must not move

| Item | Value |
|---|---|
| OLD (installed now) | `ff16c192cc7b932e59c28c4fe30aeaf27bcb7595`. s1 proves it with T1(pre). |
| SHA (to install) | `origin/master` at window open. s0 fixes it, and G8 re-proves it at s2 and s3. On 2026-10-22 13:10Z master was `3a6d165fe398507bac179ab76b4ee01aa13116db`: 181 changed paths vs OLD, no deletions. That is the wave-1 merges (#1711 #1715 #1716 #1718 #1734 and ECON/RESEARCH merges) plus, since `fc4db8de`, non-bot `ops/native_fabric/grok47`, Executive OS edge/assets and docs. At 14:27Z master was `3d1cd77dfe84fee87922eb970e1a84cfdd9a0555` (+4 paths: #1719, the Self-Directed `unavailable` rendering in `app/web.py` and `app/static/index.html`, plus its test and evidence): 184 paths vs OLD, no deletions, G7a/G7b still empty. The SHA keeps moving until the hold; only G7a/G7b decide eligibility. |
| G7a (deploy/runtime mechanics drift OLD→SHA) | Empty (re-checked at `3d1cd77d`): `scripts/deploy_code_to_vps.sh`, `deploy_from_git.sh`, `refresh_datadog_release_tag.sh`, `app/main.py`, `portfolio/forward_evaluation.py`, `app/scheduler.py`. |
| G7b (dependency drift) | Empty, so `T2_MODE=equal`. If #1714 lands first: `T2_MODE=floor_pending`. The venv is still not upgraded in this window (separate T2 step), and T2 must show an unchanged venv. |
| Forward-evaluation marker | Active: `start.json`, `deployment_sha=3c4ef7f8…`, `evaluation_start=2026-08-11`. G6 passes. The deploy takes the FORWARD_START_ACTIVE path (no init/finalize), and the marker must stay byte-identical (checked in s4). |
| Merge-queue hold | **No merge to `master` from 03:30Z until s3 has launched (to be safe, until 05:40Z).** Master is shared with non-PBR work (fabric and Executive OS merged at ~13:00Z on 10-22). If master moves after s0, G8 fails at s2/s3, and the wrapper would refuse anyway (rc 2). Recovery before 05:20Z: a new `s0` (new evidence dir), `s1`, then `s2`. |
| Never | Touch `/opt/mastermind-live-data`; rsync/scp toward the VPS outside the repo's deploy script; re-run s3; deploy a third SHA; copy `.env`/keys; run the SDK pin. |

## 1. Bootstrap, pins and conventions

### Pins

These are sha256 values. s0 re-verifies the three helpers; a mismatch aborts.

| File | sha256 |
|---|---|
| `runbook/install_w1.sh` | `2de95021c61fc27ed349155cccd21f7f963dbed7a50c0de026f56f9b05328f11` |
| `runbook/pbr_rb.py` | `536e038bb357e88926edf2613840b5d74431ccfb63c88dbe08a889f3abfa14ac` |
| `runbook/remote_blob_manifest.py` | `49b3ca7d8b53074f1b6491eccc6371c8b214c75f86c6b75c6f126a6dcd4852bf` |
| `runbook/remote_dists.py` | `b15841d63d3480ea5b8af68ab2d321f2f65d546fa74365153979e127c32776e0` |

### Bootstrap

Run this in bash or zsh; it is plain POSIX.

```sh
SEAT_WT=/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/mastermind-fable-ceo-rebuild-421ce3-1c9d9c6b5d77a525
RB=research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/runbook
B=$(mktemp -d)
git -C "$SEAT_WT" fetch -q origin claude/ssd-pbr-runtime-85f3de87bc7b8894
git -C "$SEAT_WT" show "FETCH_HEAD:$RB/install_w1.sh" > "$B/install_w1.sh"
echo "2de95021c61fc27ed349155cccd21f7f963dbed7a50c0de026f56f9b05328f11  $B/install_w1.sh" | shasum -a 256 -c -      # expect: <path>: OK   (anything else: STOP)
env -u PBR_EV OPERATOR_SESSION_ID=<executing session id> /opt/homebrew/bin/bash --noprofile --norc "$B/install_w1.sh" s0
# s0's last line prints:  export PBR_EV=/Volumes/Mastermind/evidence/pbr/install-<UTCyyyymmddThhmmZ>_<sha8>
```

### Every later step

```sh
PBR_EV=<dir printed by s0> /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" <step>
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Step PASS (`GATE <x> PASS` / `<step> PASS` lines). |
| `1` | ABORT. The reason is on stdout and appended to `$PBR_EV/logs/stops.log`. Nothing after an ABORT ran. |
| `2` | Usage error. |
| `4` | The deploy (or R-c) is still running. |
| `5` | HOLD (s4a only). Report the listed evidence to the seat. A HOLD is not a rollback trigger by itself. |

### Conventions

**Host contact.** Every host contact is `ssh -o BatchMode=yes` to `root@146.190.142.17` with the deploy key, pipe-only.

**Read and write steps.**
- Read-only steps: s1, s2, s3-result, s4, s4a, s6, cycle, restart-check, needrestart-check, proof-old, status.
- Steps that change the host:
  - **s3**: the repo's deploy wrapper.
  - **s5 / s5-revert**: `/etc/needrestart` only.
  - **rollback-b / rollback-c**: seat-gated.

**Environment guard.** s0, s3 and rollback-c refuse when any `MASTERMIND_VPS_*`, `MASTERMIND_SERVE_ONLY`, `MASTERMIND_GIT_REMOTE`, `MASTERMIND_BASE_BRANCH` or `MASTERMIND_DEPLOY_*` variable is set, because the deploy scripts would honour it.

**Tool limits.** Each step finishes well inside the seat's 600 s tool timeout. The deploy is launched detached (`setsid` + `nohup`), so it survives the calling shell. It records its rc atomically in `logs/deploy.rc`.

## 2. Timeline (UTC, Fri 2026-10-23)

| When | Step | Host effect |
|---|---|---|
| 03:30 | Merge-queue hold begins | none |
| 03:40–04:05 | `s0` (local only: worktree at origin/master, evidence dir, pins, G7/G7a/G7b) | none |
| right after s0 | `s1` pre-change capture | read |
| 04:10, then every 10 min until PASS (last attempt 05:20) | `s2` gates | read |
| immediately after an s2 PASS, **before 05:30** | `s3` deploy (exactly once) | **write (deploy wrapper)** |
| every 60–90 s until exit ≠ 4 (expect 2–6 min) | `s3-result` | read |
| right after s3-result PASS | `s4` T1–T4 + /health + app_started + snapshot + marker | read |
| right after s4 PASS | `s4a` account-load check (D-ACCT-1), label `post-restart` | read |
| after s4 PASS (or after proof-old if the seat wants the row anyway), before 05:40 | `s5` needrestart row | **write (/etc/needrestart)** |
| after s5 | `s6` close (manifest + redaction scan) | none |
| 06:15, then every ~15 min while it says "not yet" (apt-daily-upgrade fires 06:00–07:00 and runs ~5–10 min) | `needrestart-check` | read |
| 07:05 | `cycle watch_us_overnight 06:20 autonomous`, then `s4a after-watch_us_overnight` | read |
| 08:40 | `restart-check 08:30` | read |
| 08:45 | `cycle china_daily 08:00 china`, then `s4a after-china_daily` | read |
| 09:45 | `cycle hk_daily 09:00 hk`, then `s4a after-hk_daily` | read |
| 15:45 | `cycle settle_pending 15:00 autonomous` (+G4 read) | read |
| 23:55 | `cycle autonomous_daily 23:10 autonomous` | read |
| Mon 10-26 02:20 | `cycle settle_brain_asia 01:35 china 2026-10-26` and `… hk 2026-10-26` | read |
| Mon 10-26 15:45 | `cycle settle_pending 15:00 autonomous 2026-10-26` (closes the US chain) | read |

If s2 has not passed by 05:20Z, the window is lost. Do not run s3. Report to the seat. A new window needs a new s0, because each evidence dir is spent per deploy attempt.

## 3. Steps

### s0: compose (03:40Z, local)

```sh
env -u PBR_EV OPERATOR_SESSION_ID=<id> /opt/homebrew/bin/bash --noprofile --norc "$B/install_w1.sh" s0
```

**What it does**
1. Runs the environment guard. Requires `OPERATOR_SESSION_ID`. `PBR_DAY` defaults to `2026-10-23` and must be a weekday. Runs the epoch self-check (04:10 = `1792728600`, 05:30 = `1792733400`). Checks for the deploy key and the tools.
2. Creates a fresh worktree from `origin/master` via `worktree_storage.py create` (external SSD policy). HEAD must equal `git ls-remote origin refs/heads/master`, and the tree must be clean.
3. Creates `$EV=/Volumes/Mastermind/evidence/pbr/install-<cid>` and records `CAPTURE_ID`, `SHA`, `WT` and `DAY`.
4. Extracts the three helpers from `origin/claude/ssd-pbr-runtime-85f3de87bc7b8894` and runs `shasum -a 256 -c` against the pins. Copies the driver to `$EV/tools/`.
5. Records tool versions and runs a local-only rsync flag probe.
6. Runs the composition gates:
   - **G7**: OLD is an ancestor of SHA.
   - **G7a**: the mechanics diff is empty.
   - **G7b**: dependency drift is empty, or exactly the #1714 trio with only the `claude-agent-sdk>=0.2` floor changed. This sets `T2_MODE`.
7. Writes `identity/old_to_sha.name-status.txt`.

**PASS output**

```
GATE G7 PASS
s0 PASS: SHA=<40 hex> T2_MODE=equal|floor_pending WT=<path>
export PBR_EV=<path>
```

Check that SHA equals the master the seat expects at the hold. Check that `$PBR_EV/identity/old_to_sha.name-status.txt` has no `D` rows. Then skim its `bot/ brain/ app/*.py portfolio/ data_layer/ config/` rows for anything beyond the merges the seat has accepted. (On 13:10Z the count was 181 paths.) An unexpected runtime path is a seat question before s3, not a driver failure.

**ABORT conditions**

| Condition | Action |
|---|---|
| Environment override, missing session id, weekend day | Fix and re-run s0. |
| Worktree creation failed, or HEAD != remote master (master moved during s0) | Remove the new worktree and re-run s0. |
| Helper pin mismatch | STOP, ask RUNTIME. |
| G7a non-empty | Seat ruling. The runbook's mirrors of the deploy mechanics would be stale. |
| G7b drift beyond the trio | STOP, seat. |

### s1: pre-change capture (read-only)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s1
```

**What it reads (§2)**

| Read | Saved as |
|---|---|
| `systemctl show mastermind.service` (12 props) | `captures/pre/systemctl_show.txt` |
| The ExecStart path, and the EnvironmentFiles **names only** | |
| T3: sha256 of the unit fragment + drop-ins | `identity/pre/unit_sha256.txt` |
| T2: venv dist list | `identity/pre/dists.txt`; must contain `claude-agent-sdk==` and `anthropic==` |
| T1: blob manifest of `/opt/mastermind`, compared with `git ls-tree OLD` | `rb t1 … --sha OLD` must PASS with `marker_claim_matches: true` |
| T1 against SHA, as a prediction | `identity/pre_vs_sha/` (expected FAIL: differing+missing are the paths the deploy will write) |
| Book state: sha256/stat of account, fills, decisions, pending_target and paper_transaction for autonomous/china/hk, plus receipt counts | `captures/pre/book_state.txt` |
| `start.json` sha256 + mtime (never its content) | |
| `.deploy_prev` snapshot listing | |
| `df` under `/opt/mastermind` (≥ 1 GiB free) | |
| pending_target per book | |
| Decisions in the last 48 h, trimmed | |
| run_events tail (20000 lines, `extra.flags` dropped) | |
| pid-1 journal for the unit (24 h) | |
| `systemctl list-timers --all` | |

**PASS output**

```
GATE PRE PASS
s1 PASS: pre-change capture complete; predicted deploy delta: {...}
```

**ABORT conditions**

| Condition | Action |
|---|---|
| Service not active | Seat. |
| T1(pre) vs OLD FAIL, or the marker does not claim OLD | Seat; the host is not OLD (see `identity/pre/identity_manifest.tsv`). |
| SDK/anthropic dists missing | Seat. |
| Less than 1 GiB free | Seat. |
| ssh failure | Fix the transport only; never switch key/host. |

### s2: gates (read-only, repeat until PASS)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s2
```

| Gate | PASS condition | On fail |
|---|---|---|
| G5 | Host clock in `[04:10, 05:30)` | Wait (before 04:10) or abandon the window (after 05:30). |
| G8 | `ls-remote origin master == SHA` | Seat. Hold, or start over from s0 with a new evidence dir. |
| G1 | `watch_us_overnight` 02:20 has `run_finished`. The run_events tail must cover the window, and every row must parse. | Hold and re-run s2 every 10 min. **Seat-only waiver:** `PBR_WAIVE_G1='<ruling ref>'` (written to `gates/G1.WAIVER`). |
| G2E | No `run_started` without `run_finished` since the service's `ActiveEnterTimestamp` | Hold and re-run. `prewarm_marks` is ledgered and fires every 2 min (`*/2`, hours 1–9 and 13–21 UTC, mon–fri), so an open `prewarm_marks` run is the expected cause of a G2E hold in the window: re-run s2 after ~2 min instead of 10. A row older than its job's normal duration is a ledger anomaly. **Seat-only waiver:** `PBR_WAIVE_G2E='<ruling ref>'` (`gates/G2E.WAIVER`). The cgroup check below still applies. |
| G2 | No `claude`/`node`/`codex` process in the service cgroup (no LLM run in flight) | Hold and re-check. Not waivable. |
| G3 | `apt-daily`/`apt-daily-upgrade` inactive or failed; 0 unattended-upgrade/needrestart/apt/dpkg processes; `fuser` lock holders = no; `apt-daily-upgrade.timer` next elapse ≥ 05:55Z, read as the raw D-Bus property `NextElapseUSecRealtime` (`busctl get-property … Timer NextElapseUSecRealtime` → `t <µs>`), because systemd 255 prints `systemctl show` timer values as dates even with `--timestamp=unix` | Hold and re-check. If the next elapse is < 05:55, 0 or unknown: seat ruling. |
| G4 | Settlement state `clean` (a read-only mirror of the deploy's rc 21/22/23 checks: no `paper_transaction.json`, no `settlement_receipts/*.json`) | Seat ruling. **Never "repair" live data.** |
| G6 | `python3 -B -m portfolio.forward_evaluation status` rc 0 against the live root, and the `start.json` marker present | Seat. The deploy would init/finalize a marker. |

**PASS output:** `GATE G5 … G6 PASS`, then `s2 PASS: all gates clear - run s3 now`.

Waivers are environment variables read at gate time. If the seat waived a gate at s2, the same variable must be set again for **s3**, which re-runs every gate.

### s3: the deploy (exactly once)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s3
```

The step:
1. Refuses if `logs/deploy.started` exists.
2. Runs the environment guard.
3. Re-runs every s2 gate.
4. Records `DEPLOY_T0` from the host clock, which must be before 05:30.
5. Launches, detached, exactly this command (do not type it by hand):

```sh
cd "$WT" && MASTERMIND_DEPLOY_LOG="$PBR_EV/logs/deploy.log" ./scripts/deploy_from_git.sh <SHA>
# stdout/stderr -> $PBR_EV/logs/deploy.stdout ; rc -> $PBR_EV/logs/deploy.rc ; pid -> $PBR_EV/logs/deploy.pid
```

**Expected output:** `deploy LAUNCHED pid=<n> DEPLOY_T0=<epoch> sha=<SHA> - expect 2-6 min; poll with s3-result; never interrupt`.

`deploy.log` timestamps are Mac local time. The evidence uses UTC everywhere else.

### s3-result: classify the deploy (read-only; poll)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s3-result
```

Foreground sleep is blocked, so the seat can wait between polls with a `Monitor` until-loop on `test -f "$PBR_EV/logs/deploy.rc"`.

| Evidence | Verdict | Next |
|---|---|---|
| No rc file, pid alive | exit 4 `deploy still running` | Poll again. Never interrupt. |
| No rc file, pid gone | **EFFECT UNKNOWN** | Do not re-run. Read `logs/deploy.log`. Seat decides R-b (§4). |
| rc 0 + `deploy OK: mastermind.service healthy at commit <SHA>` | `GATE DEPLOY PASS` | s4 |
| rc 0 + `deploy no-op` | ABORT: host already at SHA although T1(pre) said OLD | Seat |
| rc 2 | Refused before any host change | Nothing touched. Seat decides retry/next window (new s0). |
| rc 1/130/143, no `; rolling back` line | Failed before the service stop | Nothing touched. Seat. |
| rc 1/130/143 + `code rollback verified; health returned …; runtime data retained` | **R-a**: automatic rollback verified | `proof-old`, then the seat |
| rc 1/130/143 otherwise | Rollback INCOMPLETE | R-b decision table (§4) |

### s4: post-install proof (read-only; §4 of the plan)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4
```

| Check | PASS condition |
|---|---|
| **T1** | The blob manifest equals `git ls-tree SHA`, and `.deployed_git_sha` claims SHA (`identity/post/t1_verdict.json`). |
| **T2** | `identity/pre/dists.txt` == `identity/post/dists.txt`. The deploy never touches `.venv`. |
| **T3** | Unit and drop-in hashes are unchanged, except `81-datadog-version.conf`. That file must hash to `[Service]\nEnvironment=DD_VERSION=<SHA>\n` (when `80-datadog.conf` exists). `NeedDaemonReload=no`. |
| **T4** | The loaded process started at or after `DEPLOY_T0`, from the T1-proven tree (`rb t4`). |
| /health | Reports SHA. |
| app_started | A `startup/app_started` run_event with `git_sha=SHA` since `DEPLOY_T0`, plus the cutover preflight rows. |
| Snapshot | Exactly one new `.deploy_prev/snapshot.*`, `complete=1`, `sha=OLD`. It is recorded as `SNAP` for R-b. |
| Forward marker | `start.json` sha256 unchanged, and `forward_evaluation status` rc 0. |

**PASS output:** `GATE PROOF PASS` and `s4 PASS: installed = <SHA> …`. `INSTALLED=<SHA>` is recorded.

**ABORT conditions**

| Condition | Action |
|---|---|
| app_started not yet visible | Re-run s4 once after 60 s. |
| T2 FAIL | **STOP**. The venv changed outside the deploy; no rollback without the seat. |
| Any other FAIL | R-b decision table (§4) with the seat. |

A `quarantined` cutover preflight is printed as an INCIDENT. It does not fail the proof; report it to the seat.

### s4a: account-load check (D-ACCT-1; read-only)

Run this right after s4 PASS, and again after each book's first natural cycle (see s7):

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4a                        # label: post-restart
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4a after-china_daily      # one new label per read
```

**Why.** #1747 (D-ACCT-1, `portfolio/paper_account.py`) makes an existing-but-invalid `account.json` fail closed. The load raises `AccountStateInvalid`. Before raising, it does three things:
- writes a byte-for-byte copy `account.quarantine.<sha16>.json` beside the original;
- appends one row to `account_quarantine.jsonl`;
- emits one `account_state_invalid` run_event.

If #1747 lands before s0, the install carries this behaviour. The proof is that the active books load without `AccountStateInvalid`.

**Scope.** Four books are active. Three of them (autonomous, china, hk) load through `paper_account`. **self_directed does not.** It has its own engine and account file (`portfolio/self_directed.py`, `data/portfolio/self_directed/account.json`). `app/scheduler.py` excludes it from the paper_account books (the `_MARK_BOOK_IDS` note). `AccountStateInvalid` therefore cannot arise for it, and s4a reports it as `self_directed=n/a(own-engine)`.

| Check | PASS condition |
|---|---|
| Quarantine census | No `account.quarantine.*.json` and no `account_quarantine.jsonl` in any paper_account data dir. The dirs scanned are the legacy `/opt/mastermind-live-data/portfolio/` and every `/opt/mastermind-live-data/portfolios/*/`, archived books included, because a load quarantines beside the original. Only `test`, `sha256sum` and `stat` run. The census must finish (`census_done`) and must list autonomous, china and hk. |
| run_events | No `kind=account_state_invalid` row with `ts ≥ DEPLOY_T0`. An unparseable `ts` counts as after the deploy. |
| Journal | No `account_state_invalid` / `AccountStateInvalid` line in the unit journal since `DEPLOY_T0`. |
| Classification | autonomous, china and hk each classify VALID. INVALID is a HOLD. MISSING is also a HOLD, because the next load of an active book would seed a fresh one. |

**How classification works.**
- It runs only when SHA contains `class AccountStateInvalid`.
- It uses SHA's own read-only `account_file_status(path=…)`, run on the Mac from `git archive SHA`.
- Each `account.json` is read over ssh into a 0600 temp file and deleted right after classification.
- Nothing is imported on the host, so the host `.env` is never loaded.
- `status.<book>.json` holds only the status, sha256, size and problem codes (ticker labels at most).

If SHA does not contain #1747, s4a prints `classification skipped` and runs the other three checks.

**PASS output:** `GATE ACCT_<label> PASS` and `s4a PASS (<label>): no quarantine file, no account_state_invalid event/journal line since DEPLOY_T0; autonomous=VALID china=VALID hk=VALID self_directed=n/a(own-engine)`.

**HOLD (exit 5).** Any quarantine file, event, journal line, or INVALID/MISSING classification writes `gates/ACCT_<label>.HOLD`. The expected result is that no book is quarantined.

A HOLD is **not a rollback trigger by itself**:
- Report `proof/account_load/<label>/` to the seat.
- The affected book stays halted by design. Do not "repair" the account, reset it, or delete the quarantine file.
- Clearing the quarantine is a human action outside this runbook.
- s5/s6 may proceed unless the seat says otherwise.

**ABORT (exit 1).** Any of the following is a read failure, not a verdict; re-run s4a with a new label:
- the census, run_events, journal or `account.json` read fails;
- the census is incomplete or lacks an active paper_account book's dir;
- the run_events tail is empty;
- the label already exists.

### s5: needrestart release row (writes `/etc/needrestart` only)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s5
```

**Order of operations**
1. Requires `PROOF` or `PROOF_OLD`.
2. Confirms that `needrestart.conf` includes `conf.d/*.conf`.
3. `verify_before` must be rc 3 (no mastermind override).
4. Backup (host): `cp -a /etc/needrestart /root/needrestart.backup.<CAPTURE_ID>`, followed by `diff -r` and a sha256 list, saved to `needrestart/backup_sha256.txt`. It refuses if the backup path already exists.
5. Writes the drop-in. This is the exact content of `/etc/needrestart/conf.d/99-mastermind-no-autorestart.conf`, mode 0644, written atomically via `mktemp` + `mv`. It refuses if the file or a symlink already exists.

   ```perl
   # PBR #1693 W1 release row (seat-approved 2026-10-22): needrestart must never auto-restart mastermind.service.
   # Restarts happen only via the deploy script or mastermind-restart.timer. Revert: rm this file.
   # Backup of /etc/needrestart: /root/needrestart.backup.<CAPTURE_ID>
   $nrconf{override_rc}{qr(^mastermind(?:\.service)?$)} = 0;
   ```

6. The hash read back must equal the local file.
7. `verify_after` must be rc 0. The verify loads the real `needrestart.conf` (with its `conf.d` loop) in perl and checks that `mastermind.service` matches an `override_rc` key with value 0. The key matches `mastermind.service` and `mastermind`, but not `mastermind-restart.service`. If verify_after is not rc 0, the drop-in is removed automatically and the step ABORTs.

**PASS output:** `GATE NEEDRESTART PASS` and `s5 PASS: restart_mode=<…> override=(?^:^mastermind(?:\.service)?$) value=0`.

**Revert**

```sh
PBR_EV=… …/install_w1.sh s5-revert
```

This runs `rm -f /etc/needrestart/conf.d/99-mastermind-no-autorestart.conf` and then verifies rc 3. Full restore from the backup, by hand and seat only:

```sh
ssh … 'rsync -a --delete /root/needrestart.backup.<CAPTURE_ID>/ /etc/needrestart/'
```

Apt-timer bounding is **deferred** (not in this window).

### s6: close (local)

```sh
PBR_EV=… …/install_w1.sh s6
```

This writes `manifest.json` (the sha256 of every evidence file) and runs a redaction scan. `tools/` is hashed only. **PASS output:** `s6 PASS: {"check": "close", …}`. On a redaction hit, redact the listed files before sharing anything.

### s7: first natural cycles (read-only)

```sh
PBR_EV=… …/install_w1.sh cycle <job> <HH:MM> [book] [YYYY-MM-DD]
PBR_EV=… …/install_w1.sh restart-check [HH:MM] [YYYY-MM-DD]
PBR_EV=… …/install_w1.sh needrestart-check [YYYY-MM-DD]
```

`cycle` refuses before fire + 45 min. It writes `cycles/<day>T<HHMM>Z_<job>[_<book>]/`, containing:
- the run_events tail and the cycle verdict (`rb cycle --since fire-5min`): run_started/run_finished, `extra.target_status`, `restarts_in_window`, `disposition_hint`;
- the trimmed decision rows for the book;
- `/health` vs `INSTALLED`;
- the pid-1 journal since `DEPLOY_T0`;
- for `settle_*` jobs, the G4 settlement read.

Every due cycle maps to exactly one §5 disposition: `not_due`, `disabled`, `started`, `accepted_no_change`, `accepted_change`, `rejected`, `failed` or `incomplete_uncertain`. The hint is the RUNTIME reading; the seat records the final disposition. An `incomplete_uncertain` requires an incident note naming the missing evidence.

**Known hazard:** the 08:30Z `mastermind-restart.timer` can cut an in-flight `china_daily` (fired at 08:00). If `restarts_in_window>0`, record it.

**Account load at the cycle.** A book's `account.json` is definitively loaded by its first natural cycle, not necessarily at startup. After each first cycle read (`watch_us_overnight` for autonomous, `china_daily`, `hk_daily`), run `s4a after-<job>`. self_directed is outside D-ACCT-1 (own engine). An s4a HOLD is reported to the seat; it is not a rollback trigger by itself.

`restart-check` refuses before fire + 10 min. It requires an `app_started` with `INSTALLED` after the timer, plus /health. A failure is an incident; it does not trigger a rollback.

**needrestart-check (§6 #1, first real proof of the s5 row).** It refuses unless `NEEDRESTART.PASS` exists and s5 was not reverted. Its baseline is `rollback/proof/systemctl_show.txt` when `PROOF_OLD.PASS` exists, else s4's `captures/post/systemctl_show.txt`. The cut is `<day>T05:40Z`. It stops with exit 1 and "not yet" until `apt-daily-upgrade.service` has started after the cut and finished (`ActiveState` inactive/failed with an exit time); re-run it. It also stops if the host clock is not `+0000`, because the dpkg log is in host local time. It then reads, all pipe-only:
- `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log`, where needrestart writes its report (on 10-22 the journal carried none; see §6 #1). The driver keeps only the `Log started:` blocks at or after the cut.
- `unattended-upgrades.log` since the cut, the journal since the cut filtered to `needrestart` (normally empty), and the pid-1 journal for `mastermind.service` since cut − 5 min.
- `systemctl show mastermind.service` and the s5 perl verify.

Matching is by exact token (`(^|\s)mastermind\.service(\s|$)`), so `mastermind-restart.service` and `mastermind-control-room-remote.service` never count. Verdicts:

| Verdict | Exit | Meaning |
|---|---|---|
| `PROVEN` | 0 | `mastermind.service` is under `Service restarts being deferred:` and nothing restarted it. §6 #1 is proven. |
| `LISTED` | 0 | Only under `Services to be restarted:` (list mode) and nothing restarted it. The restart-mode override was not exercised. |
| `VACUOUS` | 0 | No needrestart block since the cut names `mastermind.service` (no relevant library upgrade). §6 #1 is still unproven; re-run on a later day with `needrestart-check <day>` (each run covers from that day's 05:40Z). |
| `FAIL` | 1 | Any of: `mastermind.service` under `Restarting services...`; a pid-1 Stopping/Stopped/Starting/Started/Deactivated/Killing/Scheduled-restart line inside an unattended-upgrade interval (`[apt start − 5 s, apt exit + 120 s]` and each dpkg block `[start − 5 s, end + 120 s]`, so a run outside apt-daily-upgrade counts too); `ActiveEnterTimestamp` inside such an interval or unreadable; `NRestarts` higher than the baseline or unreadable; `ActiveState` not active; the s5 verify not rc 0. |

A FAIL is an **INCIDENT**: report it to the seat with the evidence dir. It is not a rollback trigger, and s5-revert does not undo a restart that already happened. Notes (not failures) record an `InvocationID` change, an `NRestarts` decrease (a manual restart resets it) and an interval overlapping the 08:30Z `mastermind-restart.timer`.

## 4. Rollback decision table

This follows the seat's rule: rollback = the deploy script's `rollback_release` to the `.deploy_prev` snapshot, and never touches `/opt/mastermind-live-data`.

| Situation | Route | Commands |
|---|---|---|
| s3-result says R-a (automatic rollback verified) | **R-a**: nothing more on the host | `…/install_w1.sh proof-old` (read-only: T1 vs OLD + marker, T4, /health=OLD, app_started=OLD, start.json unchanged), then report to the seat. |
| Rollback incomplete, EFFECT UNKNOWN, or s4 FAIL (not T2) and the seat says roll back | **R-b**: manual mirror of `rollback_release` (lines 205–229 of `deploy_code_to_vps.sh`) | `PBR_CONFIRM=R-b PBR_EV=… …/install_w1.sh rollback-b`, then ≥ 60 s later `…/install_w1.sh proof-old` |
| No usable snapshot (R-b preconditions fail) and the seat rules OLD must be restored | **R-c**: transactional re-deploy of OLD through `deploy_code_to_vps.sh` from `git archive OLD` | `PBR_SEAT_RULING='<ref>' PBR_EV=… …/install_w1.sh rollback-c`, poll `…/install_w1.sh rollback-c-result` (exit 4 = running), then `proof-old` |
| T2 FAIL | **STOP**: no rollback without the seat | none |

### R-b preconditions (enforced)

R-b runs only when all of the following hold:
- exactly one new snapshot, `complete=1`, `sha=OLD`;
- G4 `clean` (new code wrote no v2 WAL/receipts; otherwise a seat ruling is required);
- no open run since `DEPLOY_T0`. `prewarm_marks` (every 2 min, ledgered) can be the open run at the instant of the check. That stop happens before any host change, so re-run `rollback-b` after ~2 min;
- `EXC` parsed from `$WT/scripts/deploy_code_to_vps.sh` has 29 entries, including `data` and `.deploy_prev`.

### R-b host commands, as sent

`<snap>` = `/opt/mastermind/.deploy_prev/snapshot.<id>`. `$EXC` = the deploy's 29 `--exclude=` args, shell-quoted.

```sh
systemctl stop mastermind.service; systemctl show mastermind.service -p ActiveState -p MainPID   # must be inactive|failed and MainPID=0, else ABORT (source NOT restored)
set -e
rsync -ac --delete $EXC '<snap>/tree/' '/opt/mastermind/'
difference=$(rsync -acn --delete --itemize-changes $EXC '<snap>/tree/' '/opt/mastermind/'); [ -z "$difference" ]
# restore .deployed_git_sha from <snap>/deployed_git_sha (or remove it if <snap>/deployed_git_sha.absent)
# if <snap>/datadog.enabled: restore 81-datadog-version.conf from <snap>/datadog_version (or remove it), then systemctl daemon-reload
echo restore_verified
systemctl restart mastermind.service
```

If the restore verification fails, the service is left **stopped** (never boot a mixed tree), and the seat decides.

### R-c host effect

R-c runs:

```sh
MASTERMIND_DEPLOY_SOURCE=<archive of OLD>/ MASTERMIND_DEPLOY_EXPECT_SHA=ff16c192… <archive>/scripts/deploy_code_to_vps.sh
```

It is launched detached and logs to `rollback/rc.deploy.log`. It is classified like s3: `deploy OK … ff16c192…`, R-a or incomplete.

## 5. Evidence layout (`$PBR_EV` = `/Volumes/Mastermind/evidence/pbr/install-<UTCyyyymmddThhmmZ>_<sha8>/`)

```
state.env                    CAPTURE_ID SHA WT DAY T2_MODE DEPLOY_T0 DEPLOY_RC SNAP INSTALLED ROLLED_BACK
tools/                       install_w1.sh + the 3 pinned helpers
logs/                        runbook.log stops.log pins.txt tools.txt rsync_flag_check.txt
                             deploy.log deploy.stdout deploy.rc deploy.pid deploy.started close_verdict.json
gates/                       <G>.PASS markers, G1_G2.json, run_events.gates.jsonl, G2_cgroup.txt, G3_apt.txt,
                             G4_settlement.txt, G5_host_epoch.txt, G6_forward_status.json, G6_marker.txt, G8_origin_master.txt, *.WAIVER
identity/old_to_sha.name-status.txt
identity/pre/                installed_manifest.jsonl t1_verdict.json t1_summary.json identity_manifest.tsv dists.txt dists_key.txt unit_sha256.txt
identity/pre_vs_sha/         predicted deploy delta (T1 vs SHA before the change)
identity/post/               installed_manifest.jsonl t1_verdict.json t4_verdict.json dists.txt dists.diff unit_sha256.txt unit.diff
captures/pre/                systemctl_show execstart_path environment_file_names book_state forward_marker deploy_prev df
                             pending_target.<book>.json decisions.<book>.trimmed.jsonl run_events.tail.jsonl journal_pid1_unit timers
captures/post/               systemctl_show health.json health_verdict app_started_verdict run_events.tail deploy_prev forward_marker forward_status
needrestart/                 conf_include verify_before backup_sha256 99-mastermind-no-autorestart.conf dropin_sha256 verify_after [verify_after_revert]
cycles/<day>T<HHMM>Z_<job>[_<book>]/  run_events.tail cycle.json decisions.trimmed health(+verdict) journal_pid1_unit [settlement_state]
cycles/<day>T0540Z_needrestart/  host_clock apt_upgrade_show systemctl_show nr_verify_now dpkg_needrestart_blocks uu_log
                             journal_needrestart journal_pid1_unit verdict.json   (raw log copies are deleted after judging)
proof/account_load/<label>/  quarantine_census.txt run_events.tail.jsonl account_state_invalid_events.jsonl journal_hits.txt
                             status.<book>.json src/ (SHA's paper_account.py + package inits; account bytes deleted)
gates/ACCT_<label>.PASS|HOLD  s4a verdict per label
rollback/                    rb_* / rc.* / proof/ (only if used)
manifest.json                sha256 of every file (s6)
```

**Redaction.** Account content appears only as hashes/stats. EnvironmentFiles are recorded by name only. `extra.flags` is dropped from run_events. `start.json` is recorded by hash only. Raw captures stay in the evidence tree, never in git; commit only the capture-id.

## 6. Uncertainties and residual risks (read before 03:30Z)

1. **needrestart host semantics are unverified until `needrestart-check` returns PROVEN.** The perl verify proves the config parses and the key matches. It does not prove that the installed needrestart (3.6-7ubuntu4.5; apt hook `/usr/lib/needrestart/apt-pinvoke -m u`) honours `override_rc` in its configured restart mode. Host facts from read-only observation on 10-22, which shape the s7 step:
   - **The report is not in the journal.** It is written to `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log` (root:adm 0644, rotated monthly) inside each `Log started: …` / `Log ended: …` block, under flush-left `Restarting services...` / `Service restarts being deferred:` headings, one indented line per command. The journal had 0 needrestart lines 05:40–06:30Z.
   - **It restarted the bot on 10-22.** The 06:01:57 block lists `systemctl restart … mastermind.service …` under `Restarting services...`; pid 1 logged Stopping at 06:02:14.33Z and Started at 06:02:15.68Z. A second block (06:07:19) restarted nothing, and unattended-upgrades started again at 06:24:31 outside the apt-daily-upgrade run (06:01:03–06:07:38Z), so runs are not confined to that unit.
   - **`NRestarts` does not see it.** It counts only `Restart=` auto-restarts; it stayed 0 across the 06:02 restart. A check of "no needrestart lines in the journal and `NRestarts` unchanged" would therefore have PASSed on 10-22. `needrestart-check` gates on the dpkg log, the pid-1 journal and `ActiveEnterTimestamp` instead, and keeps `NRestarts` as a secondary check. Replayed read-only against the real host for 10-22, it returns FAIL naming the 06:01:57Z block and the four pid-1 lines.
2. **Timer next-elapse values are redrawn every 3 minutes.** NextElapseUSecRealtime includes the `RandomizedDelaySec` draw (observed: `apt-daily-upgrade.timer` `t 1792737190710641` = Fri 06:33:10Z at 14:21Z for `OnCalendar=6:00`, `RandomizedDelaySec=60m`). The host's `macro-update` cron job runs `systemctl daemon-reload` 10 times every 3 minutes (2857 reloads 00:00–14:25Z on 10-22), and each reload redraws the delay (`FixedRandomDelay` unset): the same timer read 06:53:33Z at 14:24Z. Two consequences:
   - G3's ≥ 05:55Z test stays sound: every draw for apt-daily-upgrade lies in `[06:00, 07:00]` Fri.
   - The delay collapses toward the calendar time. Once a draw lands in the past, the timer fires, so apt-daily-upgrade (unattended-upgrade, then needrestart) is expected at ~06:00–06:10Z, about 20 min after the window closes; on 10-22 it started at 06:01:02Z. `apt-daily` (`6,18:00`, 12 h delay; update/download only, no install) is expected to fire soon after 18:00Z Thu, so it is unlikely to land in W1. If it does run at s2, the G3 idle check holds; re-check.
3. **#1714 pre-landing.** If #1714 lands before s0, `T2_MODE=floor_pending`. The installed venv still holds the old SDK, and the pyproject floor is pending until the separate T2 step. Its linux gate lock was generated on Darwin with pip-tools for linux/x86_64 py3.12; it is unexercised on the host.
4. **Master moving** between s0 and s3 makes G8, or the wrapper (rc 2), refuse. Hence the merge-queue hold.
5. **Preflight quarantine** at startup is possible (`pending_target_cutover_preflight` = `quarantined`). It is reported as an incident and is not a proof failure.
6. **Authority-bytes hazard.** The deploy re-hashes the live authority files under its flock. A startup-time write to an autonomous account/fills between the baseline and the re-hash fails safe into the automatic rollback (R-a). `prewarm_marks` never writes `account.json` (with G4 clean there is no transaction to recover). With #1747 in SHA, an INVALID account makes its load write the quarantine copy, one `account_quarantine.jsonl` row and one run_events entry beside it, once; s4a reports that as a HOLD.
7. **R-b after a v2 settle** (WAL/receipts written by the new code) is refused by the precondition. It needs a seat ruling.
8. **Schedule hours are env-overridable.** The timeline assumes defaults (`US_WATCH_UTC_HOURS=2,6,11`, `CHINA_DAILY_UTC_HOUR=8`, …). s1's `timers.txt` and the run_events tail are the check.
9. **Snapshots accumulate.** Each deploy adds a full code snapshot under `.deploy_prev`. s1 requires ≥ 1 GiB free.
10. **Tail coverage.** G1/G2E and the cycle reads use a 20000-line run_events tail. If it does not reach back to the process start or fire time, the step ABORTs (G1/G2E) or the cycle is read once more and otherwise recorded as `incomplete_uncertain`.
11. **run_id formats** differ between decision rows and run_events (handed to RESEARCH). RUNTIME passes run identity. `replace_for_asof` identity loss is ruled correction-as-new-record, owned by RESEARCH as a wave-2 P0.
12. **Seat-tool kill.** The detach (`setsid` + `nohup`) is tested locally. If it fails anyway, s3-result classifies "pid gone, no rc" as EFFECT UNKNOWN; it never re-runs the deploy.
13. **Forward marker** is active (deployment_sha `3c4ef7f8…`). G6 re-proves it at the gate time; a different status means STOP, not init.
14. **Host import loads `.env`.** s4's `forward_evaluation status` (and G6) runs `python -m portfolio.forward_evaluation` on the host. `portfolio/__init__.py` imports `bot`, and `bot/__init__.py` loads `.env`/`.env.local` into that process's environment. Nothing is printed or captured, but the process does hold them. s4a deliberately classifies on the Mac to avoid a second host import.
15. **D-ACCT-1 timing.** s4a's classification needs #1747 in SHA. If #1747 lands after s0, the window installs the old load path; s4a then only runs the census/event/journal checks, and the fail-closed behaviour arrives with the next release.
16. **self_directed is not covered by D-ACCT-1.** It keeps its own lenient loader (`portfolio/self_directed.py` `_load_account`), which falls back to a fresh $1M book on a bad file. A corrupt self_directed account would not fail closed and is not detected by s4a. #1719 (in master since `3d1cd77d`) already makes `/api/self_directed` render `unavailable` on a read failure. The engine's fallback is tracked as ECON E13. It is not a W1 proof item.

## 7. Verification of this runbook (offline, by RUNTIME)

**Checks run**
- `bash -n`.
- s0 refusals: environment override, missing session id, `PBR_EV` set, weekend day. Also step-without-`PBR_EV` and bad step (rc 2). All were verified to refuse before any side effect.
- s3 refuses on an environment override before writing `deploy.started`.
- `classify`: all branches, against fake deploy logs/rcs.
- `launch_detached`: survival of the parent, atomic rc, and that the environment prefix reaches the child.
- needrestart verify: a fake conf gives rc 3 before, rc 0 after, rc 4 on a parse error. The regex matches `mastermind(.service)`, not `mastermind-restart.service`.
- `pbr_rb` gates/app-started/t1/t4/health/cycle/close against dated fixtures.
- G1/G2E waiver paths.
- G3 against a fake host with systemd-255-shaped stubs (`systemctl show` prints a date whatever the flags; `busctl` prints `t <µs>`), 9/9 cases plus 4 assertions:
  - the observed 14:21Z value (06:33:10Z) → PASS; the redrawn 14:24Z value (06:53:33Z) → PASS; exactly 05:55:00Z → PASS;
  - 05:54:59.999Z → stop; 04:40Z (inside W1) → stop; `t 0` → stop; a `busctl` error → stop; a non-`t` reply → stop;
  - `apt-daily.service` activating → stop on the idle check;
  - the evidence file carries both the µs and the date lines; `G3.PASS` is written only on a pass; the stop message names the 05:55Z floor.
  - Teeth: the reviewed driver (`ec8b5db9`) fails the three PASS cases (always `unknown`), reproducing review MAJOR-1 offline.
- s4a against a fake host (`VPS=(fakessh)` rewriting the live-data root, fake `journalctl`), 16/16 cases:
  - clean (3 VALID, self_directed n/a) → 0, with no account bytes retained;
  - a quarantine file in an archived book's dir → 5, and in the legacy `portfolio/` → 5;
  - an active book's dir absent → 1, and its `account.json` MISSING → 5;
  - a reused label → 1;
  - a quarantine file → 5;
  - an `account_state_invalid` event after `DEPLOY_T0` → 5, and one before `DEPLOY_T0` → 0;
  - an unparseable `account.json` → 5, naming the book;
  - a journal hit → 5, and a journal read failure → 1;
  - SHA without #1747 (`3a6d165f`) → classification skipped, 0;
  - no `PROOF.PASS` → 1;
  - a bad label → 1;
  - the `after-china_daily` label → 0.

- needrestart-check against a fake host (fake `date`/`systemctl`/`journalctl`/`perl`, synthetic dpkg and unattended-upgrades logs), 42/42 assertions over 23 cases:
  - PROVEN (deferred, with the 10-22 restart block before the cut excluded) → 0, keeping only the blocks since the cut, cutting the uu log, deleting the raw copies, an exact evidence file list and no restart hit from `mastermind-restart.service`/`mastermind-control-room-remote.service` lines; an InvocationID change near 08:30 → 0 with a note; VACUOUS, an absent dpkg log, LISTED, a failed apt-daily-upgrade, an `NRestarts` decrease (note) and the proof-old baseline → 0;
  - `mastermind.service` under `Restarting services...` → 1; the same in a 06:24 block outside the apt-daily-upgrade run → 1; a pid-1 Stopping/Started inside an interval → 1; `ActiveEnterTimestamp` inside an interval → 1; `NRestarts` going 0 → 1 → 1; inactive → 1; s5 verify rc 3 → 1;
  - apt-daily-upgrade not started since the cut, or still running → 1 "not yet"; host offset `+0800` → 1; a journal read failure → 1; no `NEEDRESTART.PASS`, s5 reverted, a bad day → 1; dispatch reaches the step.
  - Every failing case was checked to fail for its own reason. Teeth: the previous driver (`37d67e70`, @ 6ba45237) answers `needrestart-check` with usage (rc 2) and fails 41 of the 42 assertions.
  - Real-host replay (read-only, scratch evidence dir, 10-22 at 14:48Z): FAIL, as it must be: restart hit at the 06:01:57Z block, four pid-1 lines 06:02:14–06:02:15Z, and the s5 verify rc 3 (no drop-in yet). `journal_needrestart` was empty.
- The G3 and s4a fixtures were re-run against this driver: G3 9/9 (+4 assertions), s4a 16/16.

**Read-only host observations (2026-10-22):** 13:41Z, the forward marker is active. 14:21–14:27Z, systemd 255.4-1ubuntu8.18, TZ `Etc/UTC`; the new G3 timer probe returns `upgrade_timer_next_usec=1792738413683088` (Fri 06:53:33Z, a PASS); the reload churn in §6 #2 is from `journalctl _PID=1` and the cron journal.

14:30–14:48Z, needrestart 3.6-7ubuntu4.5, the dpkg-log report format and the 10-22 06:02 restart in §6 #1 (`dpkg -s`, `unattended-upgrades-dpkg.log`, `unattended-upgrades.log`, `journalctl _PID=1`, `systemctl show`).

**Not tested:** anything on the real host beyond those reads. The first live run is the seat's s0/s1; the first PROVEN needs a library upgrade that touches a library the bot maps.
