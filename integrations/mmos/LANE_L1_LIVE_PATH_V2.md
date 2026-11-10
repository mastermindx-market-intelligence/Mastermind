# Lane L1 — live path ledger (V2, 2026-11-09)

Lead: Opus 5.5 L1 lane lead (T3 thread, capacity_fabric). Branch `t3/mmos-v2-l1`, trunk
`feat/mmos-v1-integration-t3` from `85f0f91af`. Method: `OPERATING_METHOD_V2.md`.
Goal: DONE_WHEN rows 1-5 live on ONE Hermes-origin request (handoff V2 §0).

## 1. Live census (read-only, 2026-11-09, deepseek-v4.1-flash leaf; full table kept at
`/tmp/l1_live_census_20261109.md`, summarised here)

| Component | Live fact | Consequence |
|---|---|---|
| Executive Control/Worker | root-owned launchd, unix sockets `/var/run/mastermind-executive/{control,ceo-ingress,worker,workspace-control-room}.sock`; generation **`dd45d111`** (master, 25 behind origin/master, no lane code); 4 distinct shas across 7 loaded jobs, no `current` symlink | the trunk's t3-native composition, execution-return seam and v1.2 requester carriage are NOT in any running process |
| Executive state | `/var/db/mastermind-executive/control/db/data/control_plane/executive.sqlite3`; 1 worker (`codex-01`, last_seen 2026-10-03), 27 jobs, newest write 2026-11-03 | job plane idle 6 days; no t3-native worker registered; no `t3_adapter_state.sqlite3` anywhere |
| Executive MCP | **127.0.0.1:8443** (pid 46497); 8444 user adapter | :8731 / :8748 are not the live ports (8748 = Hermes web UI per source census); nothing to revive there |
| Model Router / Capacity Fabric | unified router :8313 (release `88bc2054…-drain1`), gateways :8312/:8311 | serving; fabric-peak-router/watchdog installed-not-running (not this lane's) |
| Hermes | gateway pid 75879 (`~/.hermes/gateway.sock`, :9120), second gateway pid 36658, slack :8791, dashboard :9119; engineering profile enables `omh, advanced-delegation, hermes-experientiallabs, mmx-router, model-routes`; `mmx-mastermind`, `mmx-t3`, `mmx-teamlink` present NOT enabled; `mcp_servers.mmx-executive → http://127.0.0.1:8443/mcp`; config mtime 2026-11-09 17:32 > gateway start 2026-11-08 14:33 (reload state UNKNOWN) | Hermes has no tool that reaches Executive child admission today; enabling it is a profile-config + gateway-reload act (Hermes-owned; L1 NEVER restarts the gateway) |
| T3 Code | pid 17210, 127.0.0.1:3773 HTTP 200, env m2studio, 0.1.7 | real native thread path available now |

## 2. Activation ladder

Each rung: one reversible act · rollback · owner · proof. Ordered so the earliest end-to-end canary
runs with the fewest acts; the hops that need a NEVER-line act are isolated so only they stay unproven.

| # | Rung | Owner | Rollback | Proof | State |
|---|---|---|---|---|---|
| R0 | Lane branch on origin, ledger | L1 | delete branch | `git ls-remote origin t3/mmos-v2-l1` | DONE |
| R1 | Dedicated T3 OAuth client for the canary (`t3 auth pairing create` → loopback OAuth, token in 0600 scratch file outside `~/.hermes`) | L1 | `t3 auth session` revoke of that client; delete scratch file | port attests `client:<sid>` (sha256 only in receipt) | see §3 |
| R2 | Scratch route config = live `executive_worker_routes.json` + proposed `t3` row (verbatim, enabled=false) loaded by the real `ModelRouter.load(path)` | L1 | delete scratch file (live file never written) | router loads; t3 descriptor resolves | see §3 |
| R3 | **Admitted canary, admission boundary inward**: real `Runtime.at(scratch)` → v1.2 `ChildExecutionRequest` with `original_requester` → `compose_child_execution` (admission + placement Job) → real `claim_job` (placement + quota + fenced `ExecutionBinding`) → `compose_t3_native_adapter` over the R1 token file (`MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE`) → ONE real T3 thread doing a real coding change → `collect_result` → `complete_attempt` → `_terminal` → `execution_return/v1` (real `GhCliEvidencePort`) → `HermesExecutionReturnDeliverer` | L1 (glm-5.3 worker) | scratch dir delete; T3 thread stays (T3 owns lifecycle; never deleted); pushed canary branch deletable | receipt `integrations/t3/live_proof/t3_admitted_canary_receipt.json` | see §3 |
| R4 | Restart safety on the SAME attempt: P1 hard-exits after the durable launch receipt, before ACK; cold P2 (same token file = same OAuth namespace, same store) reattaches with zero native launches, collects, seals; wrong-namespace client refused with zero calls; exact-run interrupt on a sibling child of the same root, requested vs settled recorded | L1 | as R3 | same receipt, scenario block `restart` | see §3 |
| R5 | Apply the `t3` provider row to `config/executive_worker_routes.json` (enabled=false) | protected-change path with Hermes at publication (file carries #2177 hunks) | revert commit | `ModelRouter.load()` on the live file | STAGED (proposal doc + scratch proof R2) |
| R6 | Install a trunk-generation Executive (Control + Worker) containing t3-native composition, execution-return seam, v1.2 carriage | Executive Control release owner via `ops/executive_os/control_component_update.py` | prior release dir pinned in plist | `plan-control-component --expected-sha` ACCEPT + live sha | BLOCKED: protected-result hold #1893 + `control_component_worker_live`; release path is root-owned; never stop/disarm the Worker to make it eligible |
| R7 | Enroll T3 token on the installed Executive host: token file root-readable, `MASTERMIND_T3_MCP_ACCESS_TOKEN_FILE` in the Control plist; register `t3-native` worker | Executive Control owner (after R6) | remove env key + `workers` row disable | `compose_t3_native_owners_for_service` → 1 owner | BLOCKED on R6 |
| R8 | Hermes engineering profile: enable `mmx-mastermind` (delegation backend → Executive `selected_child_submit` over :8443) and reload at Hermes's own maintenance boundary | Hermes engineering seat (live writer of `config.yaml`) | disable plugin line; reload | Hermes `mmx_delegate selected_child_submit` returns an admission receipt | BLOCKED: L1 NEVER restarts the gateway; profile config is Hermes-owned |
| R9 | Return delivery into the Hermes teammate conversation via installed Secretary `HermesNativeSession` | Executive (R6) + Hermes (R8) | n/a (one receipt per attempt, never retried) | `EXECUTION_RETURN_DELIVERY` event DELIVERED at the original conversation | BLOCKED on R6+R8 |

## 3. Results

### R8 source gap found and closed in source (2026-11-09)

The Hermes `mmx-mastermind` transport (`plugins/mmx-mastermind/transport.py:74,423-439`, read-only)
admits through the Executive host tool `child_request_admit {work_ref, command}`. No installed
release and no origin branch implemented it: the producer
(`integrations/executive_mcp/hermes_host.py`, `coo.py` +181, `hermes_delegate/executive.py` +60,
`scripts/dev_hermes_child_request_mcp.py`, 18 tests) existed only as the unpushed local commit
`4915d0f4` in the Hermes lane worktree, which its ledger (`~/.hermes/.../mmos/LANE_HERMES.md`
"push/PR belongs to the integrator") handed to the integrator. L1 extracted it read-only
(`git format-patch`, that worktree untouched) and landed it with authorship kept
(`git am -3`, applies cleanly to the trunk) as lane commit `2c54c99f6`. CRITICAL surface
(trusted-host admission tool): listed under OPEN for the release-candidate review.
Live owner acts for R8 (Hermes seat, exact commands): `/tmp/l1_owner_acts_20261109.md` §A —
copied into §4 below. Enabling the plugin alone is NOT enough: the installed Executive MCP
(:8443, `dd45d111`) mounts neither `child_request_admit` nor `/mcp/coo`, so R8 also waits on R6.

### R1-R4 live admitted canary — PASS (2026-11-10 02:19-02:24 UTC)

Harness `integrations/t3/live_proof/t3_admitted_canary.py` (glm-5.3 worker, commit `baa3ab409`), receipt
`integrations/t3/live_proof/t3_admitted_canary_receipt.json` (secret-free; pinned by
`tests/test_t3_admitted_canary_receipt.py`). Scratch root `~/.cache/mmos-l1-canary` (outside `~/.hermes`).
Executive generation: trunk source in-process over a scratch data dir; installed Executive `dd45d111` untouched.

| Rung | Result | Decisive evidence |
|---|---|---|
| R1 | DONE | two dedicated T3 OAuth clients (`mmos-l1-admitted-canary-client-{a,b}`), tokens 0600 in scratch; namespaces distinct (sha256 only in receipt) |
| R2 | DONE | scratch copy of routes + proposal `t3` row → real `ModelRouter.load(path)` + `explain_route` recorded; live file untouched; t3 aliases honestly empty |
| R3 | DONE (live, scratch Executive) | v1.2 request (requester `hermes:engineering` / `slack:1794196323.978899` / `mmos-rev5`, basis recorded: not a live Hermes tool call) → `compose_child_execution` ADMITTED → `claim_job` → attempt `ATT-f0a189d3dedd4bce9758fad90466842f` (job `JOB-002`) → production `compose_t3_native_adapter` over the token file → ONE T3 thread `mcp:launch:980f38b7…c4dce` (capacity_fabric / glm-5.3-flash, `runCount 1`, T3-managed worktree) → commit `e25a5a5cf10d` pushed as `t3/mmos-l1-canary-eaacc05d` → reply `L1-CANARY-OK ATT-f0a189d3… e25a5a5c…` → `collect_result` → `complete_attempt` COMPLETED → `execution_return/v1` (real `GhCliEvidencePort`, stage `branch_pushed`, acceptance `not_accepted`) → `HermesExecutionReturnDeliverer` honest REFUSED `NATIVE_SESSION_UNAVAILABLE` (R9) |
| R4 | DONE (live) | P1 `os._exit(90)` after intent+receipt+original ref COMMITTED, before ACK; cold P2 reattach **0 native calls**, second start refused `T3LaunchClaimConflictError` with 0 calls, `adopt_attempt` fence 2, RUNNING→SUCCEEDED, `recentRuns == 1`; client b reattach/start refused `PRINCIPAL_MISMATCH` with 0 calls, no thread; sibling child `ATT-51996ea6…` thread `mcp:launch:1a178e15…1f05` exact-run interrupt (thread+run echo verified) requested 02:21:21.470 unsettled → observed CANCELLED 02:21:26.542 |

Thread budget 2/2, reserved durably before each mint; no retry/delete/archive. Lead verified the
thread, run count, model, branch and remote sha directly in T3/GitHub.

Production gaps the canary exposed (fixing on `t3/mmos-v2-l1-gaps`): G1 `compose_t3_native_adapter`
passes no launch arguments (projectId/workspaceStrategy) — the installed service could not launch;
G2 no Model-Router-route → T3 `modelSelection` derivation (model harness-fixed, disclosed);
G3 `execution_return_wiring.py:347` projects `root_id = JOB-002` rather than the request root (contract check).
Deviations recorded in the receipt: branch derives from the request digest (Job.branch fixed at create_job);
placement-intent ids strip `roots/`/`parents/` prefixes (slash-free token law).

## 4. L1R close-out: fresh-hunt status table (2026-11-10, trunk `3b344ce12`)

Lane `t3/mmos-v2-l1r` (branch on origin). Every row verified by reading trunk code, not by trusting the finding text.

| Finding | Status on trunk `3b344ce12` | Where read |
|---|---|---|
| L1B3-1 CRITICAL: admit frame skips the principal/work-ref proof; App authorizes caller work_ref; no command-id check | **OPEN** (fixed this lane, §5) | dispatch-before-proof `control_plane/executive_service.py:6816-6824`; proof only at `:6866-6906`; caller-supplied `work_ref` authorized with no `target.work_ref` comparison `integrations/mastermind_executive_app/coo.py:682,710`; no `admission_command_id` check before `runtime.jobs.admit_child_execution_request` `executive_service.py:6994` |
| L1B3-2 HIGH: ambient `MASTERMIND_T3_LAUNCH_ARGUMENTS_FILE` refuses explicit args | **FIXED** — `d6e6f266d` (verified in code; ancestor of trunk) | both-explicit-only refusal + explicit-mapping-wins `control_plane/t3_native_composition.py:705-720`; tests in `tests/test_t3_native_composition.py` |
| L1B3-3 MEDIUM: `port_factory` silently drops launch args | **FIXED** — `d6e6f266d` | typed contradictory-call refusal; ambient file never read under `port_factory` `control_plane/t3_native_composition.py:653-668,721-737` |
| L1B3-4 MEDIUM: `attempt.idempotency_key` prefers job-level `command_id` | **OPEN on trunk**; fix reviewed on local `t3/l1b-pluggable-return-2` commit `6ff1cb10f` (landed this lane, §6) | command_id-first chain still at `control_plane/execution_return_wiring.py:309-311` |
| L1B3-5 MEDIUM: supervisor cannot adopt a launch that crashed between `put_launch_receipt` and `record_process` | **OPEN — recorded, not fixed here** (see §7 for the reason) | `AWAITING_LEASE_EXPIRY` branch `control_plane/executive_supervisor.py:5490-5503`; `adopt_attempt` refuses `pid IS NULL AND provider_session_id IS NULL` `control_plane/executive_runtime.py:20527-20532` |
| L1B3-6 LOW: tautological receipt assertions | **PARTLY FIXED → closed this lane**; the quoted `or True` forms are gone, but the same class remained | dead asserts at `tests/test_t3_admitted_canary_receipt.py:166` (`x == (a and x)`) and `:209` (`x[-8:] == x[-8:]`) |
