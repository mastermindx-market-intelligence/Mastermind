# RUNTIME domain ledger — pbr-runtime (W4; defects A04, A13)

Owner: `pbr-runtime` (Opus native suborchestrator, ROUTE: ORCHESTRATION) under the Fable seat.
Program: #1693 · carrier #1695 · masterplan `../../MASTERPLAN.md` (§10.1, §12.1).
Worktree: `/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/pbr-runtime-85f3de87bc7b8894`
(branch `claude/ssd-pbr-runtime-85f3de87bc7b8894` @ 230e9a301). Orchestrator id for lanes: `pbr-runtime-ed665c78`.
Sole-writer family: `brain/provider_waterfall.py`, `brain/autonomous_mcp.py`, `app/scheduler.py`,
`app/provider_diagnostic_read.py`, manager-cycle lifecycle/disposition in `bot/{autonomous,china,hk}.py`, `ops/` install proof.

Verdict scope: operational correctness only. Economic qualification and investment value are not judged here.

## Evidence roots
- Capture (read-only VPS observation 2026-10-22 07:31Z): `/Volumes/Mastermind/evidence/pbr/runtime-capture-20261022T073127Z/`
  (`identity/INSTALLED_IDENTITY.{md,json}`, `records/` 81 files, `MANIFEST.json` 94 files).
- Trimmed, secret-scanned census inputs: `./aux/` (attempts, decisions, run events, run-log excerpts, SDK 0.2.110 excerpt,
  redacted journal excerpt). Token scan (sk-ant / ghp_ / xox / JWT / Bearer / operator email): 0 hits.

## Ledger rows
| when (UTC) | unit | host/model | class | run-id | state | artifact | note |
|---|---|---|---|---|---|---|---|
| 10-22 07:31 | Step 1a installed identity | VPS read-only / pbr-runtime | census | — | DONE | capture `identity/INSTALLED_IDENTITY.md` | blob proof: installed = ff16c192 (#1682); #1614 not installed |
| 10-22 07:31 | Step 1b records capture | VPS read-only / pbr-runtime | census | — | DONE | capture `records/`, `MANIFEST.json` | pipe-only reads after one transient `/tmp/.pbr_h.<pid>` (deleted, verified absent) |
| 10-22 07:50 | deploy-window analysis | VPS read-only / pbr-runtime | census | — | DONE | this ledger §Deploy windows | `.deploy_prev` snapshots are claims; blobs prove them |
| 10-22 07:58 | aux census inputs | local / pbr-runtime | extract | — | DONE | `aux/` | 32 attempts, 29 decision rows, 401 run events (flags stripped) |
| 10-22 08:02 | L-R1/L-R3/L-R4/L-R5 launch r1 | ubuntu1 / qwen | census,build,design | pbr-rt-lr{1,3,4,5} | REFUSED | launcher logs | `ECONOMIC_POLICY_REFUSED unknown_task_complexity` (bare `C1`/`C2`); fixed to `C1_ROUTINE_BOUNDED`/`C2_COMPLEX_BOUNDED` |
| 10-22 08:03 | wave-1 launch r2 | ubuntu1 / qwen | census,build,design | pbr-rt-lr{1,3,4,5}-r2 | REFUSED (rc=75) | launcher logs | remote admission `host_temperature_at_or_above_limit` (ubuntu1 83 °C ≥ 80); spilled to ubuntu0 per brief |
| 10-22 08:05 | L-R1 failure-chain census | ubuntu0 / qwen3.8-flash | census C1 | pbr-rt-lr1-r3 | RUNNING | → `FAILURE_CHAIN.md` | budget 3600+600 s |
| 10-22 08:05 | L-R3 lifecycle projection | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr3-r3 | RUNNING | → `brain/management_lifecycle.py` + test | budget 5400+600 s |
| 10-22 08:06 | L-R4 retry negative tests | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr4-r3 | DEAD rc=1 | `.r3.out` | provider 429 on bailian key (cooldown 1800 s ⇒ ~08:36Z); worktree clean, no effect |
| 10-22 08:06 | L-R5 install-proof plan | ubuntu0 / qwen3.8-max | design C2 | pbr-rt-lr5-r3 | DEAD rc=1 | `.r3.out` | same 429; worktree clean |
| 10-22 08:09 | L-R4 relaunch | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr4-r4 | REFUSED (rc=75) | `.r4.out` | glm lease OK, then ubuntu0 admission `host_temperature_at_or_above_limit` (7 active fleet-wide on host) |
| 10-22 08:09 | L-R5 relaunch | ubuntu0 / glm-5.3 | design C2 | pbr-rt-lr5-r4 | REFUSED (rc=78) | launcher log | `ECONOMIC_POLICY_REFUSED bounded_complexity_requires_escalation`; effect ended, no escalation claimed (a 429 is not a quality failure) |
| 10-22 08:23 | L-R1 census | ubuntu0 / qwen3.8-flash | census C1 | pbr-rt-lr1-r3 | DELIVERED (accepted) | `FAILURE_CHAIN.md` (282 lines) · `returns/L-R1.r3.return.md` | ~4.15M tokens; collected by sha256-verified `cat`; lane tree removed same hour |
| 10-22 08:27 | L-R3 build | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr3-r3 | DELIVERED → PR #1711 | `returns/L-R3.r3.return.md`; head 6bbc7fe7 | ~4.14M tokens; local re-run 226 passed (lifecycle + scheduler_decision_outcomes + decision_rows); lane tree removed 08:32 |
| 10-22 08:28 | local baseline | Mac / venv 3.12.13 SDK 0.2.151 | probe | — | DONE | scratch `baseline-L-R2-suites.venv.txt` | system python lacks `claude_agent_sdk` (collection error, then 72F/10E env-only); venv + `vendor/macro_src` symlink ⇒ keep-green list 638 passed / 1 skipped. Lane hosts lack the SDK too ⇒ L-R2 packet Step 0 records a pristine baseline |
| 10-22 08:36 | L-R2 typed terminal | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr2 | DEAD rc=1 | `L-R2.launch.log` | bailian key Ryan 429 again (second equivalent 429 cycle on bailian) ⇒ tier changed, not retried on qwen; tree clean, no effect |
| 10-22 08:36 | L-R2 typed terminal | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr2-r2 | RUNNING | → `brain/provider_failure*` + cli_bridge/sdk_diagnostics (CR-RT-1) + thinking_log label (CR-RT-2) | `cheap_glm_executor`, LEASE_OK; budget 5400+600 s ⇒ classify by ~10:16Z |
| 10-22 08:37 | RV-L-R3 review of #1711 @ 6bbc7fe7 | ubuntu0 / glm-5.3 | review C2 | pbr-rt-rv-lr3 | REFUSED (rc=78) | `RV-L-R3.launch.log` | `bounded_complexity_requires_escalation` (pick.py: glm-5.3 at any bounded complexity needs an economic witness). No failed cheaper run exists to cite ⇒ no escalation claimed; reviewer moves to qwen3.8-max review (witness-free `economic_guard_permitted_class`) after the bailian cooldown (~09:06Z) |
| 10-22 08:39 | L-R4 relaunch | ubuntu1 / glm-5.3-flash | build C2 | pbr-rt-lr4-r5 | REFUSED (rc=75) | `L-R4.r5.out` | policy + LEASE_OK, then ubuntu1 admission `host_temperature_at_or_above_limit` (load1 5.3, 0 active) — second ubuntu1 temperature refusal ⇒ spill to ubuntu0 |
| 10-22 08:40 | lane trees | ubuntu0 | — | — | DONE | `~/lanes/wt/pbr-rt-lr{4,5}` @ d31aade9 (= origin/master); `~/lanes/tmp/pbr-rt-lr5/{INSTALLED_IDENTITY,SDK_EVIDENCE}.md` sha256 ad8efec0…/d6f32c40… (local copy retained `aux/INSTALLED_IDENTITY.md`) | ubuntu1 `pbr-rt-lr{4,5}` trees idle/clean ⇒ removed |
| 10-22 08:41 | L-R4 retry negative tests | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr4-r6 | RUNNING | → add-only `tests/test_retry_no_duplicate_effect.py` | `cheap_glm_executor`, LEASE_OK; budget 5400+600 s |
| 10-22 08:41 | L-R5 install-proof plan | ubuntu0 / glm-5.3-flash | doc-draft C2 | pbr-rt-lr5-r5 | RUNNING | → `INSTALL_PROOF_PLAN.md` | tier change after two no-delta rounds (r3 429, r4 refused); the plan is a draft from supplied evidence, adjudicated by pbr-runtime ⇒ `doc-draft` is the honest class; budget 3600+600 s |

## Deploy windows (from `/opt/mastermind/.deploy_prev/snapshot.*` + `.deployed_git_sha`; blob-verified provider files)
| Window | Installed composition | Evidence |
|---|---|---|
| 10-09 01:03 → 10-20 10:54 | 732cf7be (#1285) | `snapshot.6HOxWn` (created 10-20 10:54) preserved tree claiming 732cf7be; app_started git_sha 732cf7be 10-09 01:03 |
| 10-20 10:54 → 10-21 12:40 | fe7afd01 (#1618) | `snapshot.ZmUsWg` (created 10-21 12:40) |
| 10-21 12:40 → 15:32 | 7ab47f0b (#1666) | `snapshot.uxoZ28` (created 10-21 15:32; tree mtime 14:22) |
| 10-21 15:32:17 → now | ff16c192 (#1682) | `.deployed_git_sha` + full blob comparison |
Provider files compared by blob in each window: `brain/cli_bridge.py`, `brain/provider_waterfall.py`, `brain/codex_bridge.py`,
`bot/china.py`, `bot/hk.py`, `bot/autonomous.py`, `app/scheduler.py`, `brain/sdk_diagnostics.py`. `brain/key_rotor.py`,
`brain/autonomous_mcp.py`, `brain/thinking_log.py` unchanged across all windows. `git diff 732cf7be fe7afd01` touches none of
these files, so every CN/HK/US failure 10-12 → 10-21 09:00 (and US 10-20 23:10) ran on provider code byte-identical to 732cf7be.
7ab47f0b changed cli_bridge/codex_bridge/scheduler/book lifecycle; ff16c192 added `sdk_diagnostics.py` (#1590). The first US
success after the outage (10-21 23:10) ran on ff16c192.
Restart sources: deploys (`scripts/deploy_code_to_vps.sh`), `mastermind-restart.timer` 08:30Z nightly, unattended-upgrades +
needrestart (10-22 06:02:15Z, liblzma5). `MASTERMIND_JOBSTORE=memory` ⇒ an in-flight job is lost on restart.

## Contract requests (outside the RUNTIME family — written here, then stop at the boundary)
| id | to | artifact | request | status |
|---|---|---|---|---|
| CR-RT-1 | seat | `brain/cli_bridge.py`, `brain/sdk_diagnostics.py` (unowned) | narrow writer grant so L-R2 can capture the SDK `AssistantMessage.error` literal (allowlist: authentication_failed, billing_error, rate_limit, invalid_request, server_error, unknown) and tool-activity-observed into the typed provider-failure record | SENT 08:12Z · GRANTED narrow 08:13Z (see §Seat rulings) |
| CR-RT-2 | seat | `brain/thinking_log.py` (unowned) | provider label bug: model "opus" + backend "none" is labelled provider "openai" on every failed CN/HK/US attempt | SENT 08:12Z · GRANTED 08:13Z |
| CR-RT-3 | seat (release) | `pyproject.toml` / VPS venv | SDK pin: VPS runs claude-agent-sdk 0.2.110 (`"; ".join(errors) or subtype` ⇒ "error result: success"); local venv 0.2.151 fixes the message; pin is `>=0.2` | SENT 08:12Z · RELEASE row in INSTALL_PROOF_PLAN; reserved PR allowed |
| CR-RT-4 | seat (reserved) | `brain/provider_waterfall.py` failover semantics | typed-credential failover to the next rung only when no tool activity was observed is a retry/failover change ⇒ seat-reserved; L-R2 ships typing only | SENT 08:12Z · RESERVED (spec + negative tests only) |
| CR-RT-5 | ECON | `bot/settle.py`, `portfolio/paper_account.py` | any defect found by L-R4 ambiguous-retry negative tests is reported here, never patched by RUNTIME | OPEN (pending L-R4) |

## Seat rulings (received 10-22 08:13Z)
- CR-RT-1 **GRANTED (narrow)**: RUNTIME may edit `brain/cli_bridge.py` + `brain/sdk_diagnostics.py` only to surface the SDK
  `AssistantMessage.error` literal (allowlist) and `tool_activity_observed` into the typed provider-failure record. No change to
  invocation, retry, auth or env handling; never log token/credential material; tests must fail on old code.
- CR-RT-2 **GRANTED**: fix the provider label in `brain/thinking_log.py` (model opus + backend none must not read "openai"),
  diagnostic only, regression test. Both ride in L-R2's PR or a sibling PR; same merge rules (label-only/diagnostic may be merged
  by RUNTIME; the typed-terminal change stays reserved).
- CR-RT-3 **RELEASE decision**: SDK evidence (0.2.110 join bug vs 0.2.151, exact message each produces, test pinned to the SDK
  message shape) goes into `INSTALL_PROOF_PLAN.md` as a release-row item; a separate reserved PR raising pyproject to `>=0.2.151`
  may be opened, not merged by RUNTIME.
- CR-RT-4 **RESERVED**: L-R2 ships typing only. Failover-on-typed-credential-failure = spec + negative tests (no duplicate
  submission, no retry when tool activity was observed) for the acceptance row; no behaviour change in wave 1.
- Lanes: ≤4 concurrent; no qwen relaunch before the bailian cooldown expires (~08:36Z).
