# RUNTIME domain ledger — pbr-runtime (W4; defects A04, A13)

Owner: `pbr-runtime` (Opus native suborchestrator, ROUTE: ORCHESTRATION) under the Fable seat.
Program: #1693 · carrier #1695 · masterplan `../../MASTERPLAN.md` (§10.1, §12.1).
Worktree: `/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/pbr-runtime-85f3de87bc7b8894`
(branch `claude/ssd-pbr-runtime-85f3de87bc7b8894`; ledger commits only). Orchestrator id for lanes: `pbr-runtime-ed665c78`.
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
| 10-22 08:05 | L-R1 failure-chain census | ubuntu0 / qwen3.8-flash | census C1 | pbr-rt-lr1-r3 | LAUNCHED (→ 08:23 row) | → `FAILURE_CHAIN.md` | budget 3600+600 s |
| 10-22 08:05 | L-R3 lifecycle projection | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr3-r3 | LAUNCHED (→ 08:27 row) | → `brain/management_lifecycle.py` + test | budget 5400+600 s |
| 10-22 08:06 | L-R4 retry negative tests | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr4-r3 | DEAD rc=1 | `.r3.out` | provider 429 on bailian key (cooldown 1800 s ⇒ ~08:36Z); worktree clean, no effect |
| 10-22 08:06 | L-R5 install-proof plan | ubuntu0 / qwen3.8-max | design C2 | pbr-rt-lr5-r3 | DEAD rc=1 | `.r3.out` | same 429; worktree clean |
| 10-22 08:09 | L-R4 relaunch | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr4-r4 | REFUSED (rc=75) | `.r4.out` | glm lease OK, then ubuntu0 admission `host_temperature_at_or_above_limit` (7 active fleet-wide on host) |
| 10-22 08:09 | L-R5 relaunch | ubuntu0 / glm-5.3 | design C2 | pbr-rt-lr5-r4 | REFUSED (rc=78) | launcher log | `ECONOMIC_POLICY_REFUSED bounded_complexity_requires_escalation`; effect ended, no escalation claimed (a 429 is not a quality failure) |
| 10-22 08:23 | L-R1 census | ubuntu0 / qwen3.8-flash | census C1 | pbr-rt-lr1-r3 | DELIVERED (accepted) | `FAILURE_CHAIN.md` (282 lines) · `returns/L-R1.r3.return.md` | ~4.15M tokens; collected by sha256-verified `cat`; lane tree removed same hour |
| 10-22 08:27 | L-R3 build | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr3-r3 | DELIVERED → PR #1711 | `returns/L-R3.r3.return.md`; head 6bbc7fe7 | ~4.14M tokens; local re-run 226 passed (lifecycle + scheduler_decision_outcomes + decision_rows); lane tree removed 08:32 |
| 10-22 08:28 | local baseline | Mac / venv 3.12.13 SDK 0.2.151 | probe | — | DONE | scratch `baseline-L-R2-suites.venv.txt` | system python lacks `claude_agent_sdk` (collection error, then 72F/10E env-only); venv + `vendor/macro_src` symlink ⇒ keep-green list 638 passed / 1 skipped. Lane hosts lack the SDK too ⇒ L-R2 packet Step 0 records a pristine baseline |
| 10-22 08:36 | L-R2 typed terminal | ubuntu0 / qwen3.8-flash | build C2 | pbr-rt-lr2 | DEAD rc=1 | `L-R2.launch.log` | bailian key Ryan 429 again (second equivalent 429 cycle on bailian) ⇒ tier changed, not retried on qwen; tree clean, no effect |
| 10-22 08:36 | L-R2 typed terminal | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr2-r2 | LAUNCHED (→ 08:57 row) | → `brain/provider_failure*` + cli_bridge/sdk_diagnostics (CR-RT-1) + thinking_log label (CR-RT-2) | `cheap_glm_executor`, LEASE_OK; budget 5400+600 s ⇒ classify by ~10:16Z |
| 10-22 08:37 | RV-L-R3 review of #1711 @ 6bbc7fe7 | ubuntu0 / glm-5.3 | review C2 | pbr-rt-rv-lr3 | REFUSED (rc=78) | `RV-L-R3.launch.log` | `bounded_complexity_requires_escalation` (pick.py: glm-5.3 at any bounded complexity needs an economic witness). No failed cheaper run exists to cite ⇒ no escalation claimed; reviewer moves to qwen3.8-max review (witness-free `economic_guard_permitted_class`) after the bailian cooldown (~09:06Z) |
| 10-22 08:39 | L-R4 relaunch | ubuntu1 / glm-5.3-flash | build C2 | pbr-rt-lr4-r5 | REFUSED (rc=75) | `L-R4.r5.out` | policy + LEASE_OK, then ubuntu1 admission `host_temperature_at_or_above_limit` (load1 5.3, 0 active) — second ubuntu1 temperature refusal ⇒ spill to ubuntu0 |
| 10-22 08:40 | lane trees | ubuntu0 | — | — | DONE | `~/lanes/wt/pbr-rt-lr{4,5}` @ d31aade9 (= origin/master); `~/lanes/tmp/pbr-rt-lr5/{INSTALLED_IDENTITY,SDK_EVIDENCE}.md` sha256 ad8efec0…/d6f32c40… (local copy retained `aux/INSTALLED_IDENTITY.md`) | ubuntu1 `pbr-rt-lr{4,5}` trees idle/clean ⇒ removed |
| 10-22 08:41 | L-R4 retry negative tests | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr4-r6 | LAUNCHED (→ 09:03 row) | → add-only `tests/test_retry_no_duplicate_effect.py` | `cheap_glm_executor`, LEASE_OK; budget 5400+600 s |
| 10-22 08:41 | L-R5 install-proof plan | ubuntu0 / glm-5.3-flash | doc-draft C2 | pbr-rt-lr5-r5 | LAUNCHED (→ 08:51 row) | → `INSTALL_PROOF_PLAN.md` | tier change after two no-delta rounds (r3 429, r4 refused); the plan is a draft from supplied evidence, adjudicated by pbr-runtime ⇒ `doc-draft` is the honest class; budget 3600+600 s |
| 10-22 08:45 | SDK pin (CR-RT-3) | Mac / pbr-runtime direct | build C1 | — | PR #1714 (draft, RESERVED) | head e0401e96; worktree `pbr-rt-sdkpin-9bc39835d293a39b`; scratch `sdkpin-suites.txt`, `sdkpin-mutation-0.2.110.txt` | direct: 2-file change, all 4 lane slots in use. `pyproject` floor `>=0.2.151` + 5 tests through the closed synthetic transport. Old pyproject ⇒ 1F/4P; 0.2.110 formula patched in ⇒ 4F/1P; head ⇒ 205 passed / 1 skipped on 8 SDK suites. Deploy rsyncs source and never installs deps ⇒ merging does NOT upgrade the VPS venv (release row). rwe-shadow (non-required) lock headers need regeneration; not hand-edited |
| 10-22 08:51 | L-R5 install-proof plan | ubuntu0 / glm-5.3-flash | doc-draft C2 | pbr-rt-lr5-r5 | DELIVERED (adjudicated) | `INSTALL_PROOF_PLAN.md` · `returns/L-R5.r5.return.md` | rc=0; USAGE_RECEIPT_MISSING (tokens unknown). Draft adjudicated and amended by pbr-runtime (SDK-pin release row, deploy-installs-no-deps, #1714 check). Lane tree removed 11:27Z |
| 10-22 08:52 | R1 alignment of #1711 | Mac / pbr-runtime direct | build C1 | — | PUSHED → #1711 head 2c787cf3 | `brain/management_lifecycle.py` `book_status()` | direct: seat-forwarded PRODUCT R1 names + nullability folded into the delivered PR (§Published interfaces); 96 passed (lifecycle + scheduler_decision_outcomes + decision_rows) |
| 10-22 08:57 | O-1 st_atime flake | Mac / pbr-runtime direct | build C1 | — | PR #1715 head 0bc5e3f3 | `tests/test_provider_incident_forward.py` | direct, tests-only (seat-forwarded wave-1 fix): `slot_identity()` = stat fields minus atime; atime-only case modelled field by field (`os.utime` moves ctime). 117 passed / 1 skipped |
| 10-22 08:57 | L-R2 typed terminal + label | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr2-r2 | DELIVERED → split into #1716 + #1718 | `returns/L-R2.r2.return.md`; host patch `~/lanes/tmp/pbr-rt-lr2.tracked.patch` | rc=0; USAGE_RECEIPT_MISSING. pbr-runtime split by merge authority: #1716 label (`brain/thinking_log.py`, head fa325317; old code 6F/7P on 13 new cases) and #1718 typed record (RESERVED draft, head 42ed995d; 18/19 new tests fail on old code; 657 passed / 1 skipped, keep-green 638/1 = base) |
| 10-22 09:03 | L-R4 retry negative tests | ubuntu0 / glm-5.3-flash | build C2 | pbr-rt-lr4-r6 | DELIVERED → PR #1734 head 65b70c76 | `returns/L-R4.r6.return.md` | rc=0; USAGE_RECEIPT_MISSING. 10 tests (fences A waterfall, B scheduler, C decision_rows, D settle); hermetic. Mutations run by pbr-runtime: oauth gate `if True` ⇒ A1 red; codex `_failure_kind` return `if False` ⇒ A3 red; scheduler retry `count = 0` ⇒ B2 red; barren protection `if False` ⇒ C2 red. D4 ⇒ CR-RT-5 |
| 10-22 09:06 | RV-L-R3 review of #1711 @ 2c787cf3 | ubuntu0 / qwen3.8-max | review C2 | pbr-rt-rv-lr3-r2 | DEAD rc=1 | `RV-L-R3.r2.out` | bailian key Ryan 429 (cooldown 1800 s); no review produced |
| 10-22 09:05–11:12 | pbr-runtime session | — | — | — | INTERRUPTED | — | Opus session limit; resumed 11:12Z from saved state. Every lane was terminal by 09:06Z ⇒ nothing orphaned |
| 10-22 11:16 | review trees | ubuntu1 | — | — | DONE | `~/lanes/wt/pbr-rt-rv-{lr3,typed,small}` at 2c787cf3 / 42ed995d / d31aade9; PR heads fetched as `origin/pr-N` and verified equal to GitHub heads | contract inputs copied ubuntu0→ubuntu1, sha256 equal (BUILD_PACKET ea6c9b33…, R1_CONTRACT cb82032b…, L-R2 packet 7951f212…) |
| 10-22 11:18 | RV-L-R3 | ubuntu0 / qwen3.8-max | review C2 | pbr-rt-rv-lr3-r3 | REFUSED (rc=75) | `RV-L-R3.r3.out` | admission `host_temperature_at_or_above_limit` (3 active) ⇒ spill to ubuntu1 |
| 10-22 11:20 | RV-L-R3 | ubuntu1 / qwen3.8-max | review C2 | pbr-rt-rv-lr3-r4 | DEAD rc=1 | `RV-L-R3.r4.out` | bailian key Ryan 429 with waited=0 (no local cooldown active) ⇒ second equivalent 429 on the qwen review route ⇒ tier change, no further qwen review launches |
| 10-22 11:21 | RV-L-R3 | ubuntu1 / glm-5.3 | review C2 | pbr-rt-rv-lr3-r5 | RUNNING | → `reviews/RV-L-R3.md` | `bounded_complexity_escalation_recorded`; POOL_ESCALATION_REASON cites the two failed qwen review run-ids (the 08:37 refusal had none to cite, so none was claimed then). LEASE_OK glm-frontier; budget 3600 s |
| 10-22 11:23 | RV-L-R2T review of #1718 @ 42ed995d | ubuntu1 / glm-5.3 | review C2 | pbr-rt-rv-typed | REFUSED (rc=75) | `RV-L-R2T.out` | admission `host_temperature_at_or_above_limit` (4 active) |
| 10-22 11:24 | RV-SMALL review of #1716/#1715/#1734 | ubuntu1 / glm-5.3 | review C2 | pbr-rt-rv-small | REFUSED (rc=75) | `RV-SMALL.out` | same thermal refusal |
| 10-22 11:28 | RV-L-R2T review of #1718 @ 42ed995d | ubuntu0 / glm-5.3 | review C2 | pbr-rt-rv-typed-r2 | RUNNING | `RV-L-R2T.r2.out` | tree minted on ubuntu0 (ubuntu1 at 82°C); ECONOMIC_POLICY bounded_complexity_escalation_recorded; LEASE_OK glm-frontier |
| 10-22 11:31 | RV-SMALL review of #1716/#1715/#1734 | ubuntu0 / glm-5.3 | review C2 | pbr-rt-rv-small-r2 | RUNNING | `RV-SMALL.r2.out` | tree minted on ubuntu0 at d31aade9 with the three PR heads fetched; LEASE_OK glm-frontier. Unused ubuntu1 trees rv-typed/rv-small removed 11:32Z |
| 10-22 11:32 | #1714 shadow-gate diagnosis | direct | diagnosis | run 39750205842 | DONE | `INSTALL_PROOF_PLAN.md` §8b | stale rwe lock header (pyproject sha256 cef07e7a… vs cf7ee101…); both gate locks already pin claude-agent-sdk==0.2.151; regeneration needs a PyPI download, held with the reserved PR |

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
| CR-RT-3 | seat (release) | `pyproject.toml` / VPS venv | SDK pin: VPS runs claude-agent-sdk 0.2.110 (`"; ".join(errors) or subtype` ⇒ "error result: success"); local venv 0.2.151 fixes the message; pin is `>=0.2` | SENT 08:12Z · RELEASE row in INSTALL_PROOF_PLAN; reserved draft PR #1714 opened 08:45Z (not merged by RUNTIME) |
| CR-RT-4 | seat (reserved) | `brain/provider_waterfall.py` failover semantics | typed-credential failover to the next rung only when no tool activity was observed is a retry/failover change ⇒ seat-reserved; L-R2 ships typing only | SENT 08:12Z · RESERVED (spec + negative tests only) |
| CR-RT-5 | ECON | `bot/settle.py`, `bot/decision_rows.py` | L-R4 found no duplicate-effect defect (no xfail). Observation for ECON (D4, `tests/test_retry_no_duplicate_effect.py`): when a later asof settles, an earlier-asof row still at `target_status: queued` stays `queued` indefinitely — never executed (correct: no duplicate fill) but never marked superseded either, so a reader cannot tell a live queued intent from a dead one. RUNTIME pins current behaviour only; whether `superseded` is a product state is ECON's call | SENT 11:33Z (ledger) |

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

## Contract requests received (forwarded by the seat) — answers
| from / id | request (short) | RUNTIME answer |
|---|---|---|
| PRODUCT R1 | one run-status summary per book | SHIPPED in #1711 @ 2c787cf3 — interface in §Published interfaces. Wiring into `app/web.py` is PRODUCT's |
| PRODUCT R2 | `next_eligible_session` `{session_open_at, market, reason}` for a queued target | wave 2: a read-only projection from the market calendar + scheduler state. Any scheduler change it needs is seat-reserved; not in wave 1 |
| PRODUCT R3 | provider and data-feed health `[{feed, status, asof, stale_after_s}]` | split: provider rows = RUNTIME wave 2 through `app/provider_diagnostic_read.py` (#1718's typed record is the input); data-feed rows ⇒ ECON (feed-health gate) |
| PRODUCT R4 | settlement receipt reference `{receipt_id, status, retained_reason}` per book | ECON (`bot/settle.py`); RUNTIME does not write it |
| PRODUCT R5 | scheduler wiring of `price_evidence` (ECON A02 caller, `app/scheduler.py:1300-1390`) | confirmed: RUNTIME is the caller once ECON's A02 merges. It changes the scheduled submission path ⇒ RUNTIME builds it, the seat merges |
| RESEARCH CR-R2 | provider-plan vs local-thesis status | accepted in part. The field is produced in `brain/portfolio_intelligence.py:512` (no family owner) and read by RUNTIME through `brain/autonomous_mcp.py:228-232`. Wave 2, reserved; proposed names `provider_plan_status` / `local_thesis_status` |
| RESEARCH CR-R3 (rev. 08:20) | retain the consumed decision-context snapshot per manager cycle and pass its digest to the decision writer | wave 2. The manager-cycle side lives in RUNTIME's `bot/{autonomous,china,hk}.py` family; the writer binding is the seat's (W5 live wiring) ⇒ reserved |
| RESEARCH CR-R5 | host retention policy for decision-context artifacts + snapshot store | accepted as a release row (`INSTALL_PROOF_PLAN.md` §Retention): path under `/opt/mastermind-live-data`, never pruned below the V3 evaluation horizon; the size cap is set when the store exists (wave 2). No RUNTIME install step prunes or rotates live data; RUNTIME never writes the VPS |
| seat O-1 | `st_atime` flake in `tests/test_provider_incident_forward.py` | PR #1715 (tests-only) |

## Published interfaces
**R1 per-book run status** (`brain/management_lifecycle.py`, PR #1711 @ 2c787cf3; pure, never raises):
`book_status(project_cycles(opportunities, run_events, decision_rows, now=..., evidence_by_run_id=None), book="us"|"cn"|"hk", halted_by=None)`
→ `{"schema": "mastermind.bot.book_run_status.v1", "book", "run_status", "last_decision_at", "last_attempt_at", "next_scheduled_at", "failure_reason_code", "halted_by", "basis_due_at"}`.
- `run_status` is never null: one of `ok | degraded | failed | halted | not_scheduled | unavailable` (`unavailable` = no disposition with an outcome yet).
- Timestamps are ISO-8601 UTC or null. `failure_reason_code` is non-null only for `failed`/`degraded`. `basis_due_at` names the deciding cycle.
- `halted_by` is caller-supplied halt evidence (clipped to 80 chars). When given, `run_status` is `halted`. Null means "no halt evidence supplied", not "running".
