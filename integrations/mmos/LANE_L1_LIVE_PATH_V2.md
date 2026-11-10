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
