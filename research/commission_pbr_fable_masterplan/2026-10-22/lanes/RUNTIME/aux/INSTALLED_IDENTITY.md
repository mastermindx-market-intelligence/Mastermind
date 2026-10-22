# INSTALLED_IDENTITY — VPS /opt/mastermind (pbr-runtime, W4 / A13)

Observed 2026-10-22 07:31–08:05Z, read-only over ssh (`root@146.190.142.17`). Identity proof = git-blob
comparison (`git hash-object`) of installed files against commit trees. `data/deploy_lag.json` is NOT used.

## 1. Release matched: ff16c192cc7b932e59c28c4fe30aeaf27bcb7595 (#1682)
- Six code dirs (portfolio, bot, brain, app, bridge, data_layer): **205/205 `.py` blobs equal ff16c192**
  (`installed_blobs.txt`, `INSTALLED_IDENTITY.json`).
- Whole deployable tree (2989 files; excludes data, .venv, vendor, .deploy_prev, .worktrees, tests, __pycache__, .env*):
  **2988/2989 equal ff16c192**; the one extra is `.deployed_git_sha`. The 53 paths in ff16c192 but absent on the host are
  all excluded by the rsync filter in `scripts/deploy_code_to_vps.sh` (0 unexplained) (`installed_tree_blobs.txt`,
  `whole_tree_compare.json`).
- Deploy-mechanism corroboration (evidence, not the identity proof): `/opt/mastermind/.deployed_git_sha` =
  `ff16c192…`, mtime 2026-10-21 15:32:17Z; `.deploy_prev/snapshot.uxoZ28` 15:32:15Z; unit restart 15:32:10→15:32:20Z.
- `131290a0` (deploy_lag claim) matches only 77/205 → stale metadata.

## 2. Files differing from origin/master 230e9a301 (ff16c192 is 4 commits behind)
Six code dirs — exactly the #1614 delta:
| path | installed blob | master blob | installed blob last written by |
|---|---|---|---|
| bot/settle.py | abfe4b92 | 3268a23d | 18375e9fe (#41) |
| data_layer/polygon.py | a06577e4 | 1756a1bb | 0e96e3392 (#50) |
| portfolio/fx.py | a30c6dc1 | 36bcc298 | 37d145222 (#13) |
| portfolio/paper_account.py | ee795ccb | 391e4058 | 8faf504f9 (#1608) |
| portfolio/price_evidence.py | absent | present | — (#1614) |
| portfolio/fx_evidence.py | absent | present | — (#1614) |
Whole tree additionally differs on ops/native_fabric/quota_continuity, integrations/session_bridge, a research handoff doc and
`scripts/ci_pytest.py` (from #1674 c9cbee556, #1687 0454ada03, #1689 230e9a301) — none on the portfolio/manager path.

## 3. Renewal PRs (`renewal_prs_installed.json`)
| PR | commit | ancestor of ff16 | deployable files installed |
|---|---|---|---|
| #1572 | a0faf7e44 | yes | 7/7 (=ff16 blob) |
| #1580 | 677f4ff2a | yes | 7/7 |
| #1586 | 1b9dc45a2 | yes | 1/1 |
| #1599 | 4e3000045 | yes | 4/4 |
| #1608 | 8faf504f9 | yes | 1/1 |
| **#1614** | 43f83e068 (merged 15:51:59Z) | **no** | **0/6 — NOT installed** |

## 4. Restart 2026-10-22 06:02:15Z — cause: unattended-upgrades + needrestart (NOT a deploy)
`restart_and_deploy_evidence.txt`:
- `apt-daily-upgrade.service` started 06:01:02Z → `unattended-upgrade` upgraded `liblzma5`/`xz-utils`
  (5.4.5-1ubuntu0.3 → 0.4) 06:02:00–06:02:09Z (`/var/log/apt/history.log`), then `ca-certificates` 06:07:22Z.
- At 06:02:14Z systemd stopped a batch of ~20 units that map liblzma (admin, macro-api, macro-ticker-news,
  marketing-press-feeds, mastermind-control-room-remote, **mastermind**, journald, networkd, resolved, udisks2, polkit …) — the
  needrestart signature. mastermind stopped cleanly ("Application shutdown complete") and restarted 06:02:15Z (PID 876885).
- No code change: `.deployed_git_sha` and every blob unchanged since 2026-10-21 15:32:17Z; no deploy snapshot after 15:32.
- Other restart sources on this host: `mastermind-restart.timer` nightly 08:30Z ±120s (`systemctl restart mastermind`, memory
  hygiene); deploys via `scripts/deploy_code_to_vps.sh`. The 10-21 15:54:35Z restart (PID 179202, the one the audit saw) followed
  a root ssh session at 15:54:28Z; its command is not recorded (no auditd) → cause UNKNOWN beyond "remote operator/agent".
- Operational consequence: an unattended OS update can restart the authoritative scheduler mid-day; with
  `MASTERMIND_JOBSTORE=memory` any in-flight job is lost. Install-proof plan must treat this as a restart source.

## 5. Real deploy mechanism (read-only reading of `scripts/deploy_code_to_vps.sh`, `scripts/deploy_from_git.sh`)
Mac-side push: `deploy_from_git.sh` → `deploy_code_to_vps.sh` with `MASTERMIND_DEPLOY_SOURCE` (clean archive) and
`MASTERMIND_DEPLOY_EXPECT_SHA` (40-hex). Steps: stop service → settlement gate (WAL / unfinalized receipts refuse) →
forward-evaluation baseline sha256 of autonomous account/fills → verified snapshot `.deploy_prev/snapshot.XXXXXX` →
`rsync -azc --delete` with exclusions (.git, data, vendor, tests, .env*, __pycache__, .deploy_prev, .deployed_git_sha …) →
write `.deployed_git_sha` → Datadog tag → forward_evaluation init/finalize under flock → restart → `/health` probe
(`reasoning_policy_ok`, `scheduled_runtime_ok`, `commit`) → rollback on failure. `/opt/mastermind` is not a git checkout.

## 6. Adjacent facts
- Live data root = `/opt/mastermind-live-data` bind-mounted at `/opt/mastermind/data` inside the unit
  (`authoritative.conf BindPaths=`); the host-visible `/opt/mastermind/data` is a stale July copy.
- **Journal retention starts 2026-10-21 12:31Z** (`SystemMaxUse=300M`): the 10-09→10-21 manager-cycle history is NOT in
  journald; the failure chain must be reconstructed from on-disk records.
- Disclosure: during blob hashing one transient file `/tmp/.pbr_h.<pid>` was written on the VPS and deleted (verified absent).
  All later VPS access was pipe-only reads.
