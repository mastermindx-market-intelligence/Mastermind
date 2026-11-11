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
| `crash` | exit 90 at the receipt; fresh door recovers the SAME attempt through the engine's defer-then-adopt cadence | engine lane PASS live (defer → `RECEIPT_RECOVERED` → same run under fence 2, ONE native launch); seal refused by L4 — re-running on the L4 fix |
| `crash-seal` | exit 91 after the seal commit; fresh door finishes the job, result comment EXACTLY once | PASS on `d222e9d80`; PASS on `5b3efef6f` (round 3) |
| `lease-expiry` | door down longer than its 20s lease; first reconcile adopts at once, no deferral round | FAILED on `deb89b5cd` — live defect L1; re-running on the fixed tree |
| `wait` | fleet full: second task WAITs with the precise blocker | PASS |
| `wait-frees` | WAIT then live capacity: the door re-admits by itself | FAILED on `deb89b5cd` — live defect L2; L2 fix proven live (admission retired → task two admitted + launched) on `deb89b5cd`; full re-run on the fixed tree |
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

## Attack round (Step 5)

One adversarial pass on the final diff (`676786c71..HEAD`) by a model that
wrote none of it — **deepseek-v4.1-flash at effort max** (per the
Chairman's 2026-11-11 rule; not Kimi, not gemini-4-argon, not grok-4.7).
Findings and dispositions are appended below when the pass returns.
