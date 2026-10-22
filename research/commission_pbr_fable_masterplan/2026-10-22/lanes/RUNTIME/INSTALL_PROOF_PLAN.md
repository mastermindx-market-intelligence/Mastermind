# INSTALL_PROOF_PLAN — C2 runtime (lane L-R5, specification only)

Commission: PBR runtime W4/A13 · 2026-10-22. **This document is a plan; this lane executes nothing.**
Baseline (orchestrator-verified, `INSTALLED_IDENTITY.md`): installed = ff16c192 (#1682); `origin/master` =
d31aade9 (230e9a301 at commissioning); manager-path delta = **#1614 only** (price/fx evidence +
`paper_account`/`settle`/`polygon`/`fx`). `/opt/mastermind` is not a git checkout; `data/deploy_lag.json`
is stale and never used as identity. `.deployed_git_sha` / `.deploy_prev/` are deploy **claims**
(corroboration), never proof. Live data root `/opt/mastermind-live-data` is bind-mounted at
`/opt/mastermind/data`; every verifier is read-only; no rsync/scp toward the VPS outside the accepted
deploy script; no account reset, seed rewrite, balancing fill or repair trade; rollback never restores an
old account file. Every §6 mitigation is a **PROPOSAL** requiring seat approval.

## 1. Identity definition — "installed" = tuple T1–T4, all four must PASS

| # | element | exact definition | proof artifact |
|---|---------|------------------|----------------|
| T1 | Source blobs | Every non-excluded path on the host has `git hash-object` blob == the accepted commit's blob (`git ls-tree -r <sha>`). Deploy-script exclusion list (verbatim from `scripts/deploy_code_to_vps.sh` `EXC`): `.git .github .worktrees .venv venv data vendor vendor_* __pycache__ *.pyc *.pyo node_modules *.sqlite *.sqlite-* *.db *.log .DS_Store *.lock .pytest_cache .mypy_cache .ruff_cache .env .env.* tmp catboost_info {_DB} tests .deploy_prev .deployed_git_sha`. Paths in the commit but absent on the host must ALL be explained by this filter — 0 unexplained absences. | `identity_manifest.tsv` (path, expected blob, installed blob, status) |
| T2 | Dependency lock | `/opt/mastermind/.venv/bin/pip freeze` matches the accepted dependency manifest; gated at minimum on `claude-agent-sdk==<expected>` and `anthropic==<expected>`. The repo has `claude-agent-sdk>=0.2` in `pyproject.toml` (floor only; `*.lock` is rsync-excluded), so T2 is the *only* real dependency identity. A dependency change is a distinct installed version. | `pip_freeze.txt` + accepted manifest diff |
| T3 | Unit identity | `systemctl show mastermind -p FragmentPath -p DropInPaths` — record the fragment/drop-in **names** (e.g. `authoritative.conf` with `BindPaths=/opt/mastermind-live-data`) and the **sha256 of each file**; never their contents. EnvironmentFile **names only**, never contents. | `unit_identity.txt` (paths + hashes) |
| T4 | Loaded-process identity | Process `ActiveEnterTimestamp` (systemd MainPID start) is **newer than the newest mtime** among installed T1 files and newer than `.deployed_git_sha` mtime (proves the process started after the rsync — Python imports are memory-pinned after that). `/health` returns `commit == <expected sha>`, `reasoning_policy_ok: true`, `scheduled_runtime_ok: true`. | `process_identity.txt` + `/health` body |

Note: `/health.commit` is read from `.deployed_git_sha` at startup (`app/main.py::_resolve_deployed_git_sha`)
— a claim that becomes proof only in combination with T1 (on-disk tree == commit tree) and T4 (ordering).
Job `run_events` carry `git_sha: "unknown"` on the host (`control_plane/run_ledger.py` shells out to
`git rev-parse`, impossible off a checkout); only the `app_started` event carries the sha. Never cite a
job event's git_sha as identity.

## 2. Pre-change capture (§12.1 steps 1–2)

Read-only, executed before the window opens; artifacts stored per §7.

| capture | source (all under `/opt/mastermind-live-data` unless noted) | why |
|---|---|---|
| Pending targets | `portfolios/<book>/pending_target.json` for china/hk/autonomous — copy + sha256 | §12.1 step 1: what the next settle would execute |
| Unfinalized receipts / WAL | presence of `portfolios/<book>/paper_transaction.json` (WAL) and any `*.json` in `portfolios/<book>/settlement_receipts/` | the deploy script's settlement gate refuses (exit 21/22/23) across pending state — know it before, not during |
| Scheduled jobs | `GET /api/scheduler` (operator auth) — next_run_time + last status per job; tail of `data/governance/run_events.jsonl` | proves no run is in flight at window open |
| Current blob manifest | T1 procedure (§4) against ff16c192 | immutable pre-change source state |
| Dependency + unit | T2 freeze + T3 unit paths/hashes | pre-change T2/T3 |
| Forward-eval marker | `portfolio_forward_evaluation/start.json` sha256 (read-only) | deploy transaction binds to it; rollback must reconcile |

**Rollback route.** In-transaction: the deploy script's own `rollback_release` (verified `.deploy_prev/snapshot.XXXXXX/tree`
restore + marker restore + restart + health probe against the *previous* sha). Post-transaction: re-run
`scripts/deploy_code_to_vps.sh` directly with `MASTERMIND_DEPLOY_SOURCE` = clean `git archive` of the
previous accepted commit and `MASTERMIND_DEPLOY_EXPECT_SHA` = that sha. (`deploy_from_git.sh` cannot
back-deploy: it refuses anything that is not current `origin/master`.) Rollback = stop new challenger
decisions + restore the accepted software route. Rollback must **NOT** touch: the live data root
(accounts, fills, receipts, WAL, locks), `portfolio_forward_evaluation/start.json` (never deleted or
rewound), `run_events`/`governance.jsonl`, `.env*`, and the T3 unit files (observed, not edited). It does
not reverse already-recorded fills by restoring an old account file.

## 3. Install window rule

Rule: deploy only in a gap where (a) the previous manager/settlement window's job is observed
`run_finished` (not merely past its minute), (b) the next window's fire is ≥ 30 min after the deploy's
health-200 moment, (c) no `run_started` is open at window open, (d) `apt-daily-upgrade.service` /
`needrestart` are not active, and (e) completion is ≥ 15 min before `mastermind-restart.timer` (08:30Z).
Deploy budget: stop → gates → snapshot → rsync → restart → health ≈ 2–6 min; the 90-min windows below
absorb job-duration overrun and retries.

Manager/settlement windows to avoid (Mon–Fri UTC; `app/scheduler.py` + fact 6): watch_asia 00:20 / 14:20 / 20:20 ·
settle_brain_asia 01:35 · watch_us 02:20 / 06:20 / 11:20 · china_daily 08:00 · hk_daily 09:00 ·
settle_pending 15:00 · autonomous_daily 23:10. Auxiliary process jobs (cheap but share the process):
macro_refresh hourly*/3 at :30 · publish_macro_snapshot 12:25 / 22:25 · daily_mark 22:35 ·
loop_maintenance 23:45 · experiment_maturity 23:50 · derisk_us 14–20h :00/:30 · prewarm_marks 01–09/13–21h.

| window | when (UTC) | clearance | preconditions |
|---|---|---|---|
| **W1 (primary)** | Mon–Fri **04:10–05:40** | after macro_refresh 03:30 (done ≤03:40) and watch_us 02:20; before watch_us 06:20 (~40 min) and the observed ~06:00 apt activity; 2h50m before china_daily 08:00 | watch_us 02:20 `run_finished`; no open `run_started`; apt/needrestart idle |
| **W2 (weekend)** | Sat–Sun **04:10–05:40** | no manager jobs on weekends (macro_refresh 03:30/06:30 only; 08:30 restart timer respected) | same checks; first natural cycle = next Monday — use only when same-day observation is not required |

Conditional weekday fallback: 10:05–10:50 UTC only if hk_daily's `run_finished` is already observed (hk
LLM runs can overrun); closes 30 min before watch_us 11:20.

## 4. Post-install proof (§12.1 step 3)

Blob comparison — pipe-only, no temp files on the host (the 10-22 `/tmp/.pbr_h.<pid>` disclosure must not
recur). Orchestrator side, per path from `git ls-tree -r <sha>`:
`ssh <host> 'cat /opt/mastermind/<path>' | git hash-object --stdin` → compare; absence checked with
`test -e` and must be explained by the §1 exclusion filter. Counters: `equal / differing /
missing_explained / missing_unexplained`.

| check | pass criterion |
|---|---|
| T1 blobs | `differing == 0` and `missing_unexplained == 0` |
| T2 deps | `pip freeze` matches accepted manifest; `claude-agent-sdk` and `anthropic` exact-equal |
| T4 loaded | `ActiveEnterTimestamp` > max installed-file mtime **and** > `.deployed_git_sha` mtime |
| `/health` | `commit == <expected>` ∧ `reasoning_policy_ok: true` ∧ `scheduled_runtime_ok: true` |
| run_events | one `app_started` with `extra.git_sha == <expected>` after the restart |

**PASS = all five.** Any FAIL: do not count subsequent cycles as install-proof; route = §2 rollback.

**Renewal-PR proof.** A renewal PR (e.g. #1614's 43f83e068, or a future W4 PR) is proven installed when:
`git diff --name-only <installed-base>..<pr-merge>` filtered through the §1 exclusion list yields paths
whose installed blobs **all** equal the PR's blobs ("n/n installed", as in `renewal_prs_installed.json`),
with no non-PR path differing from the base commit, and T2–T4 re-verified. 0/n means **not installed**
regardless of what `.deployed_git_sha` claims.

## 5. First natural cycle (§12.1 step 4)

Observe the next three cycles after a PASS — natural cron fires only; no manual trigger, no API ack
counts as completion:

| cycle | fire (UTC) | observe, in order |
|---|---|---|
| CN | china_daily 08:00 → settle_brain_asia 01:35 next day | `run_started`(china) → `run_finished` with `extra.target_status` → decision row incl. packet-gate identity (`packet_id` SHA + gate mode, or a `packet_rejected` run_event) → queued target filled at 01:35 → settlement receipt finalized + ACK (`settlement_receipt_finalization.ok/receipt_acknowledged`) |
| HK | hk_daily 09:00 → settle_brain_asia 01:35 | same chain for book `hk` |
| US | autonomous_daily 23:10 → settle_pending 15:00 next day | same chain for book `autonomous` (settle_us), incl. mark/NAV row from daily_mark 22:35 |

Disposition taxonomy — every due cycle maps to exactly one (§10.1: timely visible outcome or explicit incident):
`not_due` (venue/calendar closed, evidenced by the venue gate) · `disabled` (archived/flag-gated off) ·
`started` (`run_started` without `run_finished` inside the observation window) · `accepted_no_change`
(target_status accepted, decision_effective, no fills) · `accepted_change` (accepted + fills + receipt) ·
`rejected` (`rejected_*` target_status / packet_rejected) · `failed` (`step_failed`/error/HARD_STOP) ·
`incomplete_uncertain` (evidence gap — e.g. journal retention — or a restart mid-run). Any
`incomplete_uncertain` requires an explicit incident note naming the missing evidence.

## 6. Restart hazards (all mitigations are PROPOSALS — seat approval; none executed here)

`MASTERMIND_JOBSTORE=memory` ⇒ **any** restart loses the in-flight job and retry counters; the only
record is whatever run_events/decision rows were already written (2026-10-16 CN/HK cycles left no
`run_started` at all).

| source | risk | detection evidence | proposed mitigation (PROPOSAL) |
|---|---|---|---|
| Deploy script restart (controlled) | none if in-window; loses in-flight job otherwise | deploy log, new `.deploy_prev/snapshot.*`, `.deployed_git_sha` mtime | keep the §3 window rule (in-plan, no host change) |
| `mastermind-restart.timer` nightly 08:30Z ±120s | can kill an in-flight china_daily (fired 08:00; LLM runs may exceed 30 min) | `systemctl list-timers`, unit `OnCalendar`, journal stop/start pair | move `OnCalendar` into W1 (e.g. 04:30Z) — seat via VPS ops |
| unattended-upgrades + needrestart (liblzma case 10-22 06:02:15Z) | any library-mapped unit batch stops ~20 services incl. mastermind, mid-day, mid-run | `/var/log/apt/history.log` + journalctl batch-stop signature (clean "Application shutdown complete" then restart, no deploy snapshot) | needrestart exclusion/`l`-mode for `mastermind.service` and/or bounding apt timers away from manager windows — seat |
| unexplained operator restart (10-21 15:54:35Z after root ssh; cause UNKNOWN, no auditd) | arbitrary-timing restart; undetectable in advance | currently none — that is the finding | enable auditd / session-command recording for root ssh — seat |
| memory jobstore (amplifier of all of the above) | in-flight job + schedule silently lost; cycle becomes `incomplete_uncertain` | gap analysis: cron expectation vs `run_started` presence | durable jobstore on the live-data root with the 2026-07-06 readonly-sqlite failure mode addressed (watchdog → fall back to memory + alert), or explicitly accept and document — seat |

## 7. Evidence layout

Root: `/Volumes/Mastermind/evidence/pbr/<capture-id>/` on the orchestrator host, where
`<capture-id>` = `<UTCyyyymmddThhmmZ>_<composition-sha8>` (e.g. `20261022T0512Z_ff16c192`). Subdirs:
`identity/` (blob manifests, `whole_tree_compare.json`, T2 freeze, T3 unit hashes), `captures/`
(§2 pre-change snapshots), `cycles/` (one subdir per cycle: run_events excerpts, decision row, receipt),
`logs/` (deploy-log transcript), plus `manifest.json` listing sha256 of every artifact. **Redaction:** no
tokens, no emails, no env-file contents (names only), no credential material of any kind; account content
only as needed for the cycle proof. Committed to the repo: this plan, lane outputs, and DEC/DSC pointers
that reference a capture-id; raw VPS captures stay in the evidence tree, never in git.

## 8. What this plan does not prove

It proves **operational installation and accountability**: exact installed composition, that the loaded
process is that composition, and that every due cycle produces a visible outcome or explicit incident.
It does **not** prove: economic qualification or investment value of any decision (that is forward
evaluation + grading, separately owned); correctness of the #1614 price/fx logic itself; provider
failover correctness (W4's scope); data-feed quality; or any live-trading safety property — the bot is
paper-only and never auto-executes. "Installed and accountable" ≠ "correct and worth running".

## 8b. Release row — provider SDK pin (seat ruling CR-RT-3, RESERVED)

Evidence (`SDK_EVIDENCE.md`): `pyproject.toml` @ d31aade9 L14 pins `claude-agent-sdk>=0.2` — floor only,
no lock file (`*.lock` is deploy-excluded, so T2 freeze is the only lock). VPS runs **0.2.110**, whose
`_internal/query.py` (L304–344) builds `"; ".join(errors) or str(subtype)`, so an API failure arriving as
`{subtype:"success", is_error:true, errors:[]}` raises plain `Exception("Claude Code returned an error
result: success")` — the text on all 18 credential + 2 quota failures 10-12..10-21. **0.2.151**
(`_error_result_text`) prefers `errors[]`, then `result` prose, then a non-success subtype, then
`API error (HTTP <status>)`, and raises a typed `ResultError` carrying the result frame in `.data`.

| field | value |
|---|---|
| Change | raise the pin (floor and/or exact lock) so ≥ 0.2.151 installs |
| Identity impact | a pin change is a **distinct installed version** — part of tuple T2; it re-runs §4 with the new T2 manifest |
| Authority | **RESERVED to the seat** (CR-RT-3); no lane may bump it |
| Required regression test (rides in the same PR) | feed a synthetic `{"type":"result","subtype":"success","is_error":true,"errors":[],"result":"API Error: 401 ..."}` frame; assert the produced message is **not** `"Claude Code returned an error result: success"` and surfaces the result prose; **skip with an explicit reason** when the installed SDK is < 0.2.151 |
| What `brain/cli_bridge.py` (W4 L-R2) still needs from the SDK on *either* version | read `AssistantMessage.error` (already delivered at 0.2.110, unread at ff16c192/d31aade9 — the earliest truthful failure signal); on 0.2.151 additionally `ResultMessage.subtype` / `.is_error` / `.api_error_status` and typed `ResultError.data`, so `brain/key_rotor.classify_failure` can cool keys on API/credential failures instead of returning `None` on the "success" text and stopping the waterfall at the first OAuth rung |

**Carrier: PR #1714 (draft, RESERVED to the seat), head e0401e96.** `pyproject.toml` floor raised to
`claude-agent-sdk>=0.2.151` plus 5 tests through the closed synthetic transport. Old pyproject ⇒ 1 failed /
4 passed; the 0.2.110 formula patched in ⇒ 4 failed / 1 passed; head ⇒ 205 passed / 1 skipped on 8 SDK suites.
Merging it does **not** change T2 on the VPS: `scripts/deploy_code_to_vps.sh` rsyncs a git archive and never
installs dependencies. The upgrade is a separate seat-approved venv step in a W1 window, followed by a §4
re-proof with the new T2 manifest. #1714 check status: see the line below (one diagnosis read, no loop).

**#1714 `shadow-gate` diagnosis (one read, run 39750205842 job 119728578448, 11:32Z).** `rwe_env realize refused: stale lock -- regenerate`: the two hash-locked gate locks (`requirements/gate-linux-x86_64-py312.lock`, `requirements/gate-macos-arm64-py312.lock`) carry a `# pyproject.toml sha256: cef07e7a…` header that `scripts/rwe_env.py:376 check_pyproject_not_stale` compares with the current file; the PR's one-line floor change makes it `cf7ee101…`. It is not a code or test defect. Both locks at d31aade9 **already pin `claude-agent-sdk==0.2.151`**, so a pip-compile regeneration (pip-tools 7.6.1, isolated index, the command recorded in each lock header) is expected to change only the header digest. The regeneration needs a PyPI download, so it was not run here; it rides with #1714 when the seat schedules the pin. Side fact: CI's gate already tests 0.2.151 while the installed VPS venv runs 0.2.110, so the green CI suites do not exercise the production SDK version.

## 8c. Retention row — decision-context artifacts (RESEARCH CR-R5)

| field | value |
|---|---|
| Path | under the live data root `/opt/mastermind-live-data` (BindPaths mount); exact subdirectory is fixed when the content-addressed snapshot store exists (W5) |
| Floor | never pruned below the V3 evaluation horizon |
| Size cap | set with the store (wave 2); until then nothing in RUNTIME's install or restart procedure prunes, rotates or rewrites anything under the live data root |
| Authority | the policy is a release-plan row; RUNTIME never writes the VPS |

## Open questions (carried to the orchestrator)

1. Does the #1614 delta trip the deploy script's receipt-v2 settlement gate while a WAL/unfinalized
   receipt is pending? Needs a fresh gate read at window open.
2. Exact needrestart suppression mechanism on this host (conf.d blacklist vs `$nrconf{restart}` mode)
   and whether unattended-upgrades can be time-bounded — unverified on-host.
3. Can a durable jobstore be made safe given the 2026-07-06 readonly-sqlite incident (placement on the
   live-data root, corruption watchdog)? Unproven.
4. Is auditd (or equivalent root-session command recording) installable within the no-unscheduled-
   modification rule — itself a seat-approved change?

## Seat decision

ONE decision: **which composition to install next, and when.**
- **Option A (recommended): approve install of current `origin/master` (d31aade9 when drafted = ff16c192 + #1614 on
  the manager path; dce821e0 at 11:28Z, 6 commits later, none touching the provider files or `pyproject.toml`;
  the exact sha is fixed and blob-proven at window open) in the next W1 window (Mon–Fri 04:10–05:40 UTC), then run the §4 proof and §5 cycle
  observation. SDK stays 0.2.110 — the CR-RT-3 pin is a separate, later T2 change.**
  Consequence: §12.1 steps 3–4 and every W4 evaluation lane measure against the composition that will
  actually run (settle/price/fx-evidence path included); W4 PRs land afterwards as renewal installs,
  each provable by §4's renewal procedure. Cost: one extra managed restart now.
- Option B: hold at ff16c192 until the W4 PRs merge, then one combined cutover.
  Consequence: fewer restarts, but the accountable-cycle proof (§10.1) stays on a composition lacking the
  receipt/price-fx evidence path downstream work assumes, and the runtime lane is coupled to W4's
  schedule.

Why A: it is the single decision that unblocks the most downstream work — the first-natural-cycle proof,
the receipt-path evaluation, and W4's baseline all wait on it, while W4's own changes remain cleanly
provable as renewals afterwards.
