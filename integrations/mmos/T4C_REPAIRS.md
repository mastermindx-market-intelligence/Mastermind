# T4c repairs — the governed coding job made safe to build on

Lane T4c, 2026-11-11, branch `t3/mmos-v4-t4c`. Input: the R4b independent
review (`R4B_REVIEW_FINDINGS.md`, 15 findings) merged from lane T4b, plus
attack finding F8 from `T4B_ATTACK_FINDINGS.md`. Base commit `676786c71`
(the T4b final tree); every row below names its proving test and commit.

## Finding table (R4b unless noted)

| # | Finding (short) | Status | Proving test | Commit |
|---|---|---|---|---|
| 1 | same-instance deferred receipts re-adopted per reconcile pass | CLOSED | `tests/test_executive_supervisor_receipt_recovery_t4c.py::test_finding1_*` | `f31bf26b6` |
| 2 | unbound claim with durable receipt: adopted immediately, fencing a live launcher | CLOSED (defer at live lease; typed quarantine without the seam) | `…t4c.py::test_finding2_*`, `test_composed_supervisor_defers_a_live_receipt_claim…` | `f31bf26b6` |
| 3 | crash between seal commit and `sealed` save misreported EXECUTOR_FAILED | CLOSED (terminal row read first; seal finished; seam re-drive once) | `tests/test_mmos_coding_job_door.py::test_f3_*`; journey `crash-seal` | `e9d3fc858` |
| 4 | comment text unfenced (prompt injection into the task surface) | CLOSED (door) | `tests/test_mmos_coding_job_door_t4c.py::test_f4_*` | `e9d3fc858` |
| 5 | frozen.json non-atomic save could lose the last good state | CLOSED (Step 2, with F6) | `tests/test_mmos_coding_job_door.py::test_f5_*` | `e9d3fc858` |
| 6 | concurrent writers to frozen.json (no lock) | CLOSED | `…door.py::test_f6_*` | `e9d3fc858` |
| 7 | expired-lease + bound claim refused recovery (second launch) | CLOSED (recovers the same attempt via `adopt_expired_lease`) | `…t4c.py::test_finding7_*` | `f31bf26b6` |
| 8 | pairing CLI leg could fall back to the live T3 app | CLOSED | `tests/test_t3_live_proof_pairing_target.py` (11 tests) | `e7c57ef3a` |
| 9 | loopback check by string prefix; no host:port allowlist | CLOSED | `…door_t4c.py::test_f9_*` | `e9d3fc858` |
| 10 | intake/admit without the task showing its own request | CLOSED (enrolled-assignee + newest agent comment gate, typed refusals) | `…door_t4c.py::test_f10_*`; journeys `hash-refused`, `wait` (live) | `e9d3fc858` |
| 11 | world-readable frozen.json / census / run dirs | CLOSED (0600/0700) | `…door_t4c.py::test_f11_*` | `e9d3fc858` |
| 12 | WAIT never retried; refusals burned the wake | CLOSED (door retries WAIT itself; typed refusals burn nothing) | `…door_t4c.py::test_f12_*`; journey `wait-frees` (live) | `e9d3fc858` |
| 13 | launch-uncertain parks released the thread slot | CLOSED (slot held until terminal) | `…door_t4c.py::test_f13_*` | `e9d3fc858` |
| 14 | dev Paperclip comment paging could hide task state | CLOSED — NOT A DEFECT (live probe: the endpoint takes no paging parameters and returned all 61 rows; evidence `step4-journeys/f14-paging-probe.json`) | live probe (no code change warranted) | `d222e9d80` (evidence) |
| 15 | the door's own recovery path (record_process + adopt_attempt) was a second, weaker owner | CLOSED (DoorSupervisor deleted; the real composed engine owns recovery end to end) | `…door_t4c.py::test_step3_*` (10 tests); journeys `crash`, `lease-expiry` (live) | `9601419cf` |
| F8 (attack) | wedged claim could hold its quota class silently | CLOSED (typed `reconcile-quarantined` parks with slot HELD; real reconcile answers every wedged claim) | `…door_t4c.py::test_step3_engine_quarantine_parks…` | `9601419cf` |
| L1 (live, lease-expiry journey) | the launch spec named the REQUEST job while the attempt was claimed on the PLACEMENT job; the engine's receipt-adoption identity check refused the door's own durable receipt as a foreign execution, the service quarantined at startup and the recovery door died at `register-worker` | CLOSED (both launch sites build the spec with the job the attempt was CLAIMED on) | `…door_t4c.py::test_step4_launch_spec_carries_the_attempt_s_own_job` | this step |
| L2 (live, wait-frees journey) | the admission-ledger Job (a record of WHO ASKED) never left the runtime's ready count (`QUEUED`, never claimed) after its placement delivered, so fleet capacity never freed — the second task WAITed forever with the door faithfully re-asking every 30s | CLOSED (finishing a sealed entry retires its admission Job through the runtime's typed cancel seam, idempotently) | `…door_t4c.py::test_step4_a_terminal_placement_frees_the_admission_ready_slot` | this step |
| L3 (live, crash journey) | the launch spec carried NO authorities while `compose_child_execution`'s placement Job carries the runtime's default `["READ"]`; the receipt-adoption contract check refused ("launch contract differs from the durable Job") and the recovery looped `LIVE_QUARANTINED` forever | CLOSED (the launch spec carries the placement Job's own authority set) | `…door_t4c.py::test_step4_launch_spec_carries_the_attempt_s_own_job` (authorities leg) | this step |
| L4 (live, crash journey) | the engine's supervisor-boundary projection returns the recovered `ActiveRun` in the TWIN ref shape (pid/pgid/start-identity/boot-session None — the runtime's provider-managed recording shape), but the door seals through its own INNER adapter whose retained-ref check demands the DURABLE NEUTRAL ref (pid=0): `_require_run_state` refused the door's own recovered run ("ref does not match the retained original ref"), the entry froze at execute-failed and reconcile spun `ALREADY_RECOVERED` forever | CLOSED (the seal runs on the adapter's own durable ref, read through its fail-closed `retained_original_ref` accessor; an unreadable ref parks typed `RECOVERED_REF_UNREADABLE`, never a translated guess) | `…door_t4c.py::test_step4_a_recovered_run_seals_through_the_durable_neutral_ref` | this step |
| L5 (live, crash journey round 4) | the engine adopts the recovered attempt with a FRESH short lease, then the door honestly WAITS for the native run to finish — a wait longer than the lease made `complete_attempt` refuse (`StateConflict: attempt … lease has expired`) with the result in hand; the entry froze execute-failed | CLOSED (a live owner extends its lease while its execution runs: the door heartbeats through the terminal wait — before each poll and once more before the seal — through the runtime's typed `heartbeat_attempt` seam; a refusal propagates, the door no longer holds the attempt and must not seal it) | `…door_t4c.py::test_step5_a_wait_longer_than_the_lease_still_seals` | this step |
| L6 (live, lease-expiry journey round 4) | the ADOPTED attempt's bound-path recovery check compares `spec.workspace_path` with the placement Job's OWN worktree and `spec.result_schema_path` with the engine's canonical `worker-result.schema.json`; the door's spec named an attempt-scoped `{run_id}-ws` workspace and a bare `schema.json`, so the reconcile AFTER the successful adoption refused (`LIVE_QUARANTINED`, "worker recovery launch contract differs from durable Job") → whole-service quarantine → the recovery door died at `register-worker` | CLOSED (the spec names the placement Job's paths at BOTH launch sites: the first claim passes the workspace it just created and recorded on the Job; the F1 relaunch reads the attempt's job worktree from the durable Job) | `…door_t4c.py::test_step6_the_launch_spec_names_the_placement_jobs_own_paths` | this step |
| L7 (live, wait-frees journey round 4) | the census file is per-SCRATCH but `job_state` answered a command's "native launches" with the whole-file count: two tasks that each launched exactly once both reported 2, so the journey's per-task exactly-once proof could not pass (the door itself was correct — the census showed one launch per task) | CLOSED (the per-job launch port tags its census rows with the attempt it was composed for; a command's state counts only ITS attempt's tagged launches — untagged service-side rows never count, an attemptless entry answers 0) | `…door_t4c.py::test_step7_job_state_counts_native_launches_per_attempt` | this step |
| L8 (live, lease-expiry journey rounds 5–6; two parts) | with L6 fixed, the recovery door's startup reconcile ADOPTED at once (events 8–12: PROCESS_RECORDED → RECEIPT_ADOPTED → ADOPTED → RUNNING → CHECKPOINTED) — and the service's own recovered-run FINISHER then raised inside `finish_job`, so `_finish_dispatched` quarantined the whole service (`executive_service.py:10100`, the reason retained only in memory) and the door died at `register-worker`.  **Part a (round 5):** the t3 adapter's `CollectionReceipt` hardcoded `exit_code=None` (a provider-managed run has no OS process), while `_terminalize` demands a truthful exit code — `SupervisorError: recovered local worker has no truthful durable OS exit code`.  **Part b (round 6, L8b):** after part a, the finisher still died on its FIRST poll because `collect_result` refused a still-LIVE run (`run ... is not terminal; no final result to collect`) — but the supervisor's collection contract is "completes at terminal": process adapters await process exit inside collect_result, and `_collect_with_heartbeats` uses the collect call itself as its ONLY wait loop (verified `claude_worker.py:2107-2130` awaits a shared collection task).  The t3 read-adapter was the outlier; the whole service quarantined on the first poll.  Only the lease-expiry shape reaches this path: default/crash seal door-side, and in crash the service never adopts (it defers to the live lease) | CLOSED (a: the t3 adapter maps its durable provider verdict to the engine-uniform exit code exactly as the paid wire's reviewed law does — SUCCEEDED → 0, every failure verdict nonzero; the richer truth stays in `result.status`.  b: `collect_result` now polls the honest live `status` until the run is terminal and only then performs the ONE terminal read — audit #13 unchanged, the result never comes from the status cursor; the wait is a plain sleep so the engine loop can cancel it on ownership loss, and the ledger is untouched until the terminal read.  Probe on copied stores after both parts: reconcile → TERMINAL_RECOVERED → `finish_job` completes, no quarantine) | part a: `tests/test_t3_execution_adapter.py::T3CollectTests::test_collect_maps_the_provider_verdict_to_the_engine_uniform_exit_code`; part b: `tests/test_t3_execution_adapter.py::T3CollectTests::test_collect_waits_for_the_terminal_state_before_the_terminal_read` | this step |
| L9 (live, lease-expiry journey round 7; two parts) | with L8 both parts fixed the door SURVIVED register-worker — and a fence war killed the run: events 8–12 at 10:44:43 are the SERVICE startup reconcile's adoption (fence 2) with its finisher now healthily collecting (1s status polls, `collect_result` waiting on the live run), then event 13 at 10:44:47 is the DOOR's own cadence lane adopting the SAME attempt at fence 3 (its `_reconcile` drives a second supervisor instance on the shared store; the executor's engine-owned guard at door.py:1658 is bypassed whenever `_recovered` is already populated), and at 10:44:53 an untagged service-side census row records `t3_thread_interrupt` — the fenced-out finisher's ownership-loss cleanup (`executive_supervisor.py` `_collect_with_heartbeats` except-branch → `adapter.cancel(ref, "supervisor ownership lost")`) CANCELLED the still-live native run 46s into its ~2min execution.  The run died CANCELLED with no result; both collect paths lawfully refused the no-reference terminal read; `EXECUTOR_FAILED` surfaced and the door looped `ALREADY_RECOVERED` with nothing left to deliver.  **Part a:** the finisher's first heartbeat came only AFTER a full heartbeat interval, and an expired-lease adoption leaves the lease un-renewed — so the door's lawful cadence reconcile re-adopted inside that gap.  **Part b:** the ownership-loss cleanup treats a provider-managed run like a local orphan process; for a provider-managed ref there IS no orphan (the provider keeps executing; the next reconcile adopts it), so the cancel only destroys recoverable work | CLOSED (a: `_collect_with_heartbeats` renews the lease IMMEDIATELY on entry, before its first wait — the adoption→first-heartbeat gap no longer exists.  b: the except-branch cancels only the local collection task when the ref is provider-managed (pid None — the supervisor-boundary twin shape); a local process ref still gets the orphan cancel.  **Journey round 8 PASS on `aba13e7ef`:** the finisher's immediate heartbeat (event 13), the door lane's lawful fence-3 adoption, zero interrupts, one surviving owner delivering the recovered attempt) | `tests/test_executive_supervisor_receipt_recovery_t4c.py::test_recovered_run_finisher_renews_the_lease_before_its_first_wait`; `…::test_a_fenced_out_finisher_never_cancels_the_provider_run` | this step |

## Step-4 proof (dev instances)

Journey mechanics went live in `d222e9d80`: tasks are created with
`assigneeAgentId`, and the teammate's reply is posted **as the agent**
through the dev instance's own attribution law (a per-task `task_bridge`
agent key, an invoked heartbeat run, and the comment attributed via
`X-Paperclip-Run-Id`; the key is deleted after each reply and its secret
is never logged). The door's intake/admit gates read exactly what a real
task shows.

| scenario | proves | result |
|---|---|---|
| `default` | one task → one job → sealed → result comment on the same task | PASS (1 launch); PASS again on `5b3efef6f` (round 3) |
| `crash` | exit 90 at the receipt; fresh door recovers the SAME attempt through the engine's defer-then-adopt cadence | engine lane PASS live (defer → `RECEIPT_RECOVERED` → same run under fence 2, ONE native launch); seal refused by L4, then the seal's commit refused by L5 — re-running on the L4+L5 fixes |
| `crash-seal` | exit 91 after the seal commit; fresh door finishes the job, result comment EXACTLY once | PASS on `d222e9d80`; PASS on `5b3efef6f` (round 3) |
| `lease-expiry` | door down longer than its 20s lease; first reconcile adopts at once, no deferral round | FAILED on `deb89b5cd` — live defect L1; FAILED on `8da58b12d` (round 4) — live defect L6; FAILED on `8653bdcd2` (round 5b) — live defect L8 part a; FAILED on `f8ffd1117` (round 6) — live defect L8 part b; FAILED on `cbd98db80` (round 7) — live defect L9; **PASS on `aba13e7ef` (round 8)** — delivered, same attempt, 1 launch, `deferred == 0`; events show the finisher's IMMEDIATE heartbeat (L9a), the door lane's fence-3 adoption, ZERO interrupts in the census (20 reads + 1 launch), the fenced-out finisher exiting silently (L9b), and the door lane delivering from the recovered attempt |
| `wait` | fleet full: second task WAITs with the precise blocker | PASS |
| `wait-frees` | WAIT then live capacity: the door re-admits by itself | FAILED on `deb89b5cd` — live defect L2; L2 fix proven live (admission retired → task two admitted + launched) on `deb89b5cd`; round 4 FAILed only on L7's whole-file launch count (door correct); **PASS on `8653bdcd2` (round 5b): two tasks, ONE launch each, task two admitted by the door itself after the admission slot freed, both delivered** |
| `undeliverable` | refused receipt surfaced with its code | see below |
| `hash-refused` | hash-knowledge caller refused with typed TASK_REQUEST_MISSING, nothing burned | PASS |

(The rows marked "see below" fill in as their runs land; the full outputs
live in the T4c evidence ledger's `step4-journeys/` folder.)

### Live defects caught by the journeys

- **L1 (lease-expiry, 2026-11-11):** the recovery door exited rc=1 at
  `register-worker` — the whole Executive control service was QUARANTINED by
  its own startup reconciliation.  Reproduced read-only on a copy of the
  scratch runtime: the attempt row is claimed on the PLACEMENT job
  (`JOB-002`) while the door's durable launch spec carries the REQUEST job
  (`JOB-001`), so `_reconcile_receipt_claim`'s foreign-execution identity
  check (`spec.job_id != attempt.job_id`) returns `LIVE_QUARANTINED` —
  which `_reconciliation_requires_quarantine` escalates to a whole-service
  quarantine before the door can even register.  Fixed at both launch sites
  (the spec now names the job the attempt was claimed on); the earlier
  `crash` journey failure kept at `crash-20261110T204146` remains the
  OLD-tree reconcile-port evidence (defect of `d222e9d80`, fixed in
  `deb89b5cd`).
- **L2 (wait-frees, 2026-11-11):** task one delivered at 03:58 UTC; task
  two WAITed 35+ minutes with the door faithfully re-asking
  (`admit_last_ask` advancing every 30s — F12's retry works).  The runtime's
  fleet-ready count is `admission Jobs QUEUED, never claimed`, and nothing
  ever retired a finished request's admission Job: `JOB-001` sat QUEUED
  forever next to its COMPLETED placement `JOB-002`, so `fleet_ready`
  never dropped below the limit.  Fixed by retiring the admission Job at
  the end of `_finish_sealed` (both delivered and delivery-refused
  outcomes — the placement is terminal either way), through the runtime's
  own `cancel_job` seam, idempotently.
- **L3 (crash, 2026-11-11):** the round-3 crash journey got PAST L1's
  identity check (spec.job_id == attempt.job_id — the L1 fix works live)
  and died at the engine's contract check: the launch spec carried NO
  authorities while the placement Job carries the runtime's default
  `["READ"]` (`create_job`'s default).  `_reconcile_receipt_claim`'s
  launch-contract comparison refused (`LIVE_QUARANTINED`, "launch
  contract differs from the durable Job") on every cadence.  Fixed in
  `_launch_spec` (`authorities=("READ",)`), asserted in the L1 test's
  spec leg.
- **L4 (crash, 2026-11-11):** with L1+L3 fixed the engine lane itself
  worked end to end — defer to lease expiry, then `RECEIPT_RECOVERED`,
  the SAME native run adopted under fence 2, one native launch — but the
  seal refused: `T3ExecutionAdapterError: ref does not match the retained
  original ref`.  Root cause (read from the crash scratch's durable
  stores): the supervisor's `SupervisorBoundaryT3Adapter` projection
  returns the recovered `ActiveRun.process_ref` in the TWIN shape
  (pid/pgid/process_start_identity/boot_session_id all None — the
  runtime's provider-managed recording shape), while the door's seal runs
  on its OWN composed adapter, the reviewed inner adapter whose
  `start()`/`status()`/`collect_result()` all take the DURABLE NEUTRAL ref
  (pid=0/pgid=0, filled identity fields).  The first-launch flow never
  hits this because inner `start()` returns the neutral ref directly.
  Fixed door-side: the seal reads the adapter's own durable ref through
  its fail-closed `retained_original_ref` accessor; an unreadable ref
  parks typed `RECOVERED_REF_UNREADABLE` instead of sealing a translated
  or guessed ref.  The engine's projection and its twin checks stay
  exactly as reviewed.
- **L5 (crash round 4, 2026-11-11):** on the L4-fixed tree the recovered
  run sealed through the durable neutral ref, the native run went
  terminal `SUCCEEDED`, the result was collected — and then
  `complete_attempt` refused: `StateConflict: attempt … lease has
  expired`.  The engine adopts a recovered attempt with a FRESH lease
  (the canary's is 20s); the door's terminal wait then outlasted it.
  `_current_row` refuses every mutation at `timestamp >=
  lease_expires_at_ms` and an expired lease is unrenewable (only
  `adopt_attempt(adopt_expired_lease=True)` may take it).  A live owner
  extends its lease while its execution runs: the door now heartbeats
  through the wait (before each poll) and once more before the seal,
  through the runtime's own typed `heartbeat_attempt` seam (expiry =
  `max(existing, now+duration)`, monotonic forward).  A renewal refusal
  propagates — that door no longer holds the attempt and must not seal
  it; the engine's re-adoption owns the next one.
- **L6 (lease-expiry round 4, 2026-11-11):** the round-4 lease-expiry
  run died at `register-worker` with the service QUARANTINED — but this
  time by the BOUND-path check, not the receipt-path one (which L1/L3
  fixed).  A read-only probe on a copy of the scratch runtime reproduced
  it: `reconcile_restart` → `LIVE_QUARANTINED "worker recovery launch
  contract differs from durable Job"` from `_recover_existing_attempt`
  (the path taken once the attempt was already adopted and carries
  `worker_recovery_binding`).  The field dump isolated it: the door's
  durable launch spec named `workspace_path = …/run/jobs/ATT-…-ws`
  (attempt-scoped) while the placement Job's own worktree is
  `…/run/jobs/job-4924ab80-ws`, and `result_schema_path = …/schema.json`
  while the engine's canonical name is `worker-result.schema.json`;
  authorities, write-paths, base_sha and all three ids matched.  The
  engine's checks are correct — the door's independently built spec was
  the defect (as in L1 and L3).  Fixed at both launch sites: the first
  claim passes the workspace it just created and recorded on the Job;
  the F1 relaunch reads the attempt's job worktree from the durable Job
  itself, and the schema path uses the engine's canonical name.
- **L7 (wait-frees round 4, 2026-11-11):** the L2 fix works live — task
  two was admitted by the door itself (JOB-003) after task one's
  admission Job retired, both tasks delivered — but the journey FAILed
  on `native_launches == 1` per task: `job_state` counted the WHOLE
  per-scratch census, so each of two single-launch tasks reported 2 (the
  census itself showed exactly one `t3_thread_launch` per task — the
  door was correct, the answer was not per-command).  Fixed by
  per-attempt attribution: the per-job launch port tags its census rows
  with the attempt it was composed for, and a command's state counts
  only its own attempt's tagged launches.
- **L8 (lease-expiry round 5, 2026-11-11):** the round-5b recovery door
  died at `register-worker` with the whole Executive service
  QUARANTINED — yet the durable events show its own startup reconcile
  had ADOPTED the attempt cleanly at 02:38:19–20 (fence 2, binding
  written, `TERMINAL` native run later verified SUCCEEDED at 09:40:12Z).
  The quarantiner is `_finish_dispatched`
  (`executive_service.py:10095-10100`): the recovered run's finisher
  calls `supervisor.finish_job(active)`, and ANY exception records the
  reason only in the in-memory `_dispatch_errors` map (lost when the
  door process died — nothing durable says why) and quarantines the
  service before the door's `register-worker` lands.  Reproduced on
  copied stores (`/tmp/t4c-lex5-probe.py`): reconcile →
  `TERMINAL_RECOVERED`, then `finish_job` raised verbatim —
  `SupervisorError: recovered local worker has no truthful durable OS
  exit code` — because the t3 adapter's `_build_collection_receipt`
  hardcoded `exit_code=None` while `_terminalize`
  (`executive_supervisor.py:4443`) demands one.  A provider-managed run
  has no OS process; the durable provider verdict IS the exit evidence.
  Fixed at the adapter (`t3_execution_adapter.py`): the collection
  receipt maps the verdict to the engine-uniform exit code exactly as
  the paid wire's reviewed law does (`paid_fabric_wire.py:328`,
  SUCCEEDED → 0), keeping the richer truth in `result.status`.  Probe
  after the fix: `FINISH OK` end to end, no quarantine.  **Part b
  (round 6, L8b):** the journey STILL failed with the identical
  quarantine signature on the part-a tree, because the probe-5 copy had
  gone terminal by the time it finished — a now-terminal run was never
  the failing moment.  Probe 6 on a FRESH lease-expiry scratch isolated
  it: `finish_job` raised at the still-LIVE moment with
  `T3ExecutionAdapterError: run ... is not terminal; no final result to
  collect`.  The supervisor's collection contract is "completes at
  terminal" — process adapters block until exit inside collect_result
  (`claude_worker.py:2107-2130` awaits a shared collection task), and
  `_collect_with_heartbeats` (`executive_supervisor.py:3397`) uses
  `adapter.collect_result` as its ONLY wait mechanism; the t3
  read-adapter refused the live run and the finisher died on its first
  poll.  Fixed at the adapter: `collect_result` polls the honest live
  `status` until `_TERMINAL_STATES` (interval `collect_poll_seconds`,
  default 1.0s) and only then performs the ONE terminal read; the
  result never comes from the status cursor, the wait is a plain sleep
  (cancellable on ownership loss), and no ledger write happens until
  the terminal read.  Only the lease-expiry shape reaches this path —
  default/crash seal door-side, and in crash the service never adopts
  (it defers to the live lease while the door lane owns) — which is why
  every earlier journey passed around it.  Two observability notes
  recorded here: the finisher's quarantine reason is in-memory only,
  and the census showed exactly one service-side read before the
  failure (the raise was local, not a transport fault).
- **L9 (lease-expiry round 7, 2026-11-11):** with L8 both parts fixed,
  the recovery door SURVIVED `register-worker` for the first time — and
  exposed a fence war that destroyed the run.  Events 8–12 (10:44:43) are
  the service startup reconcile's adoption at fence 2; its finisher then
  collected healthily (untagged 1s status reads 10:44:48–52 — the L8b
  wait loop doing its job).  Event 13 (10:44:47) is the DOOR's own
  cadence lane adopting the same attempt at fence 3 — `_reconcile`
  drives a SECOND supervisor instance on the shared store, and the
  executor's engine-owned guard (door.py:1658) is bypassed whenever
  `_recovered` is already populated, so the door never defers to the
  in-process service finisher.  The finisher's next heartbeat was
  refused (fence moved), and its ownership-loss cleanup
  (`adapter.cancel(ref, "supervisor ownership lost")`) issued the
  census's untagged `t3_thread_interrupt` at 10:44:53 — cancelling the
  still-live native run 46s into its ~2min execution.  The run died
  CANCELLED with no result reference; both collect paths lawfully
  refused the no-reference terminal read; `EXECUTOR_FAILED` surfaced
  and the door looped `ALREADY_RECOVERED` with nothing left to deliver.
  Two root causes, both fixed engine-side: (a) the finisher's first
  heartbeat came only after a full heartbeat interval while an
  expired-lease adoption leaves the lease un-renewed — the door's
  LAWFUL cadence reconcile re-adopted inside that gap; the finisher now
  renews IMMEDIATELY on entry.  (b) the ownership-loss cleanup treated
  a provider-managed run like a local orphan process — for a
  provider-managed ref (pid None, the supervisor-boundary twin shape)
  there is no orphan hazard: the provider keeps executing and the next
  reconcile adopts it, so the cleanup now ends only the local
  collection task; a local process ref still gets the orphan cancel.
  With (a), the door's cadence pass sees a live lease and defers
  (`AWAITING_LEASE_EXPIRY`) exactly as the F15 lane was designed to.

## Attack round (Step 5)

One adversarial pass on the final diff (`676786c71..HEAD`) by a model that
wrote none of it — **deepseek-v4.1-flash at effort max** (per the
Chairman's 2026-11-11 rule; not Kimi, not gemini-4-argon, not grok-4.7).
Reviewed tree: branch `t3/mmos-v4-t4c` head `d57aad915` (the source files
byte-identical at `513449a36`, the branch head the attacker was given).
The pass returned **5 findings** (full text:
`T4C_ATTACK_FINDINGS.md`, committed on the attacker's own branch
`t3/mmos-v4-t4c-attack`; local copy `/tmp/t4c-attack-findings.md`).  All
five were adjudicated against the code in this lane before any repair.

| # | Severity | Finding (short) | Disposition | Proving test | Commit |
|---|---|---|---|---|---|
| F1 | HIGH | the BOUND recovery path adopted a LIVE lease (`_recover_existing_attempt`; `adopt_expired_lease=False` only refuses the expired shape), so the door's second supervisor instance fenced the service's in-process recovered-run finisher on the cadence reconcile — and the fenced finisher's `StateConflict` then quarantined the WHOLE Executive service (`_finish_dispatched` catches any exception), refusing every mutating lane until an operator restart | CLOSED, both halves: (a) the bound path defers at a live lease exactly like the identity-less receipt path — `AWAITING_LEASE_EXPIRY` while the lease is live, placed after binding validation and the reattach-capability check so every quarantine path is unchanged, the in-transaction expiry re-verify in `adopt_attempt` still refusing a lease renewed in between; (b) a `StateConflict` from a finisher is visibility (`_dispatch_errors`), never a service-wide poison — ownership loss is the engine's identity-safe answer and the next reconcile owns the recovery; unknown seal failures still quarantine | `tests/test_executive_supervisor_receipt_recovery_t4c.py::test_bound_recovery_defers_at_a_live_lease_and_adopts_at_expiry`, `…::test_a_stateconflict_finisher_is_visibility_not_a_service_quarantine`; 14 stale-law tests moved to clock+1s-lease+advance-past-expiry (`tests/test_executive_supervisor.py`) | `15f769d6c` |
| F2 | MED | the door's seal lane never branched on the native verdict — `complete_attempt` unconditionally sealed COMPLETED, so a FAILED/CANCELLED/TIMED_OUT run that still carried a terminal result ref (the worker's failure text) was delivered as a completed job's Result; the service-side finisher DOES branch (`_terminalize`), so the two lanes disagreed | CLOSED (the native verdict governs the seal: SUCCEEDED → `complete_attempt`, every other terminal verdict → `fail_attempt` with the verdict named in the payload — `fail_attempt` drives the same status-aware seam, so the failure text still delivers under an honest FAILED seal) | `tests/test_mmos_coding_job_door_t4c.py::test_step5_f2_a_failed_native_run_with_a_result_is_sealed_failed` | this step |
| F3 | MED | after `_wait_terminal`'s 1800s deadline it RETURNS non-terminal (does not raise) and `_seal_and_deliver` then called `collect_result` — which since L8b polls live status forever — so one orphaned native thread blocked the door's single executor thread indefinitely: no cadence reconcile, no other entry served, no typed blocker, the door's own lease lapsing mid-poll | CLOSED (a non-terminal wait parks the entry with a typed `NATIVE_RUN_TIMEOUT` blocker and HOLDS its thread slot (F13 law — the attempt is still live engine-side); `collect_result` is never entered on a non-terminal run; the wait reads the door's OWN `wait_deadline_seconds`/`poll_interval_seconds` config instead of hardcoded constants; the retry is cadence-paced (`run-timeout` → execute when reconcile is due, else skip), and a re-adopted run pops the surfaced-blocker record so the entry never strands) | `…door_t4c.py::test_step5_f3_a_never_terminal_run_parks_typed_never_polls_forever`, `…::test_step5_f3_the_wait_reads_the_doors_own_deadline_knobs` | this step |
| F4 | LOW, speculative | two collectors racing a provider terminal-write race could head-read different result refs → `T3ResultLedgerConflictError` (typed refusal, wrong-verdict-wins) | ACCEPTED AS DESIGNED — the write-once result ledger makes this a typed refusal, not corruption; the attacker's own text marks it SPECULATIVE (needs a provider-side terminal-write race to actually differ; the normal path is one immutable terminal row).  A wrong-verdict-wins would surface as an honest typed conflict on whichever lane polls second, and no lane silently upgrades.  Watch, no code change | — (documented here) | — |
| F5 | LOW | the F10 gate's "newest agent comment" degraded to ARRIVAL order when any comment lacked a timestamp — and the carrier lists newest first, so `[-1]` picked the OLDEST agent comment: a stale request block could authorize admission (fail-open in an authorization gate) | CLOSED (an agent row without a timestamp is a typed `TASK_STATE_UNREADABLE` refusal — the gate never admits on degraded ordering evidence; and the gate orders by the AGENT rows' OWN timestamps, so a timestamp-less board row degrades nothing) | `…door_t4c.py::test_step5_f5_the_request_gate_refuses_degraded_timestamps` | this step |

Notes on the adjudication: F1(a) was confirmed against `adopt_attempt`'s
refusal table (`executive_runtime.py:20451` — `adopt_expired_lease=False`
refuses the EXPIRED shape, never the live one) plus the caller routing
presence-LIVE bound attempts to adoption; F1(b) against
`_finish_dispatched`'s blanket quarantine.  The attacker's own "defused
candidates" list (startup race, exit-code mapping, cancel-mid-poll, cursor
advance, L9b pid-None misfire, secret surfaces, mint pinning, crash hooks)
was re-checked and stands.  The bounded cost of the F1(a) law: a restart
recovery now waits at most one lease window before adoption — the price of
never fencing a live owner, which is the diff's own claimed invariant 2.

## L10 — the recovered-run finisher sealed a SUCCEEDED provider run as FAILED

Found live in the round-9 lease-expiry journey (step 5): the first
exercise of the service-finisher-seals path (rounds 1–8 the door lane
owned the seal) showed the provider verdict SUCCEEDED, exit 0, canary
text delivered — and the attempt sealed FAILED with
`errors: ["worker result validations must be an array"]`, job
`JOB_FAILED {"status":"FAILED"}`.  The journey PASSed anyway: its
criteria assert delivery, same attempt, one launch — never the seal
verdict, which is exactly how the defect hid until the durable receipt
was inspected by hand.

Root cause: the t3 adapter passed the provider's natural terminal read
(`{"text", "item_id", "text_truncated"}`) straight through as
`WorkerResult.structured_output`, but the engine's worker contract is the
closed COMPLETED envelope — `_validate_output_scope` requires
`validations` to be an array and `_terminalize` gates every completion on
`str(output.get("status")) == "COMPLETED"`.  Every other adapter presents
the envelope (the claude/codex workers validate their structured output
against the job's result schema; the supervisor's commission prompt
demands it).  The door's own seal lane never runs `_terminalize`, so the
two lanes disagreed on the same receipt — and every prior
receipt-recovery test fed the finisher FakeAdapter's hand-built envelope,
so the real boundary's mismatch never met.

Repair (fail-first: the finisher-integration test reproduced the FAILED
seal from the REAL adapter's collected output before the fix):

- `control_plane/t3_execution_adapter.py` — a SUCCEEDED read is
  translated into the engine's closed envelope
  (`status: COMPLETED`, `validations: []`, the provider's final text in
  `summary`, `artifacts: []`, the read's provenance keys riding along);
  failure verdicts keep the natural read — the worker's own failure
  report, which no engine acceptance path consumes and the door's F2
  honest-failure seal quotes.  The natural read stays durable in the
  collection receipt and the write-once result ledger either way.
- `tools/mmos_coding_job/door.py` — the seal summary reads the envelope's
  `summary` first, the natural `text` second (failure verdicts).
- The engine's terminal law is unchanged: the envelope is the contract,
  the adapter is the translating boundary, and the worker prompt is
  untouched (a lane rule).

Two stale tests surfaced by the repair, both fixed:

- `tests/test_t3_native_composition.py::
  test_crash_before_the_running_ack_recovers_with_zero_native_launches`
  — stale law from F1(a) (`15f769d6c`, missed by the step-5 sweep: the
  file was not in any batch): reconcile at a LIVE lease now defers
  (`AWAITING_LEASE_EXPIRY`) and recovers the same execution with zero
  native launches only after expiry.  The test now proves both phases.
- `tests/test_t3_adapter_durability.py::
  test_collect_uses_a_terminal_read_not_the_status_cursor` — stale since
  L8b (`aba13e7ef`): collect lawfully POLLS STATUS until terminal
  (L8b's "completes at terminal" contract) and each status poll advances
  the read cursor as a side effect; the #13 invariant (the result comes
  only from the head read, never an incremental page) was and is the
  asserted line above it.  The "cursor untouched" over-specification now
  documents the one lawful status poll.

Proving tests:
`tests/test_t3_execution_adapter.py::
test_collect_presents_the_engine_closed_completed_envelope`,
`tests/test_executive_supervisor_receipt_recovery_t4c.py::
test_the_recovered_finisher_seals_a_succeeded_provider_run_completed`
(wires the REAL adapter's collected structured_output into the recovery
lane — RED on the FAILED seal before the fix, GREEN COMPLETED after).
