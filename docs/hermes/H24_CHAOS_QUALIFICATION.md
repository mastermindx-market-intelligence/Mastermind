# H24-10 — deterministic offline chaos conformance

## Scope and authority

This packet adds an isolated source/test lane for original-effect, callback,
principal, source-identity and transaction invariants. It uses the incumbent
Runtime and integration owners against disposable fixtures. It does not add a
Runtime, retry controller, callback ledger, worker queue or publication owner.

- Implementation parent: [`b54cb10e4abdd3766c62d4088f6a576ecfe80437`](https://github.com/mastermindx-market-intelligence/Mastermind/commit/b54cb10e4abdd3766c62d4088f6a576ecfe80437).
- Isolated branch: `sol/h24-10-chaos-ci-20261106`.
- Governing protected-source pin: `88a8b103a5a69e4b4e870a184655dde9fd5875c3`
  (`docs/sol_skills/INDEX.md` and laws read at that same commit;
  skillpack 1.0.1, compatible with bootstrap major 1).
- Placement: the Chairman explicitly authorized concurrent H24-10 source work;
  no H24-01/H24-07 wave seal was used as an entry gate.
- Ownership: only the new `tests/hermes_contract_chaos/` files, this document,
  and `.github/workflows/hermes-upgrade-offline.yml`.
- PR #2120 integration files, incumbent workflows, C29–C34 exclusive owners,
  C26 security/probes, production Runtime and release controls are unchanged.

**Capability delta:** the immutable base's original-effect contracts can now be
exercised together through a focused, seeded offline lane, with durable SQL
cardinality/digest assertions and a runtime/exit-code receipt. This establishes
source conformance for the listed cases. It establishes no native startup,
provider, host-security, deployed-service or end-product acceptance.

## Frozen contracts and injectable boundaries

The implementation deliberately reuses the base's real owners:

| Owner | Contract retained | Injected boundary |
| --- | --- | --- |
| `ExecutiveSelectedChildComposition` and `ExecutiveControlService` | Exact original child/command; one Attempt; uncertain modifying return; immutable typed terminal result | Status barriers, lost dispatch return, duplicate/late terminal callback |
| `RuntimeSessionReturn` and `HermesNativeSession` | Principal-bound original operation, COMMIT_STARTED before native bytes, one native submission, original read recovery | Native transport observation/return hooks and source/read-guard loss |
| `Runtime`, its broker, jobs, OHF registry and `OperatorHarnessOrchestrator` | Eligibility checked at claim; cancellation fences; typed STOP intent/receipt; exact operation replay refusal | Worker/quota availability and lost STOP return |
| `FabricBindingSource` | Full pinned source identity, including replacement with identical bytes | Disposable-file replacement and ABA |
| `WakeLedgerRepository` / `wake_dispatcher` | Committed Event visibility; original nudge reconciliation; terminal phase protection | Uncommitted Event, reordered/duplicate obligations, delayed reconciliation return |
| `dialogue_wake_canary_control` | Same transaction recovery and exact configuration preimages | Return lost after publication receipt or bound-config proof |
| `HermesModelClient` / `executive_retry_safety` | Readonly-only outage fallback; no modifying replay; fail closed on unknown/live/stale evidence | Disconnect, 503, 429, 401 and manual wall-clock rollback |

`Schedule` releases explicit `asyncio.Event` barriers in the order produced by
`random.Random(seed)`. Tests do not use sleeps or timing races to choose the
interleaving. Five-second waits are deadlock watchdogs. The fixture permits at
most 64 pending barrier slots; tests also assert the real dispatch queue bounds
and the incumbent 64-child projection ceiling.

`FaultScript` consumes a finite script and fails on an extra effect. It records
safe model identifiers, never headers, prompts, credential values or raw error
text. `ManualClock` drives both wall timestamps and monotonic elapsed time;
rollback must still produce a 25 ms modeled attempt duration.

The offline guard rejects Internet connections, DNS/URL requests and external
processes. The only subprocess exception is local Git work inside the current
test's disposable directory, needed by the incumbent source-plan fixture.
This Python fixture guard is not an OS sandbox or a Landlock qualification.

## Coverage and exact assertions

| Requested interleaving/fault | Test(s) | Checked result |
| --- | --- | --- |
| Two parents select one original child | `test_two_parents_select_the_same_original_child` | Both observe unclaimed before release; one existing Job, exactly one new Attempt, at most one dispatch task; subsequent submits observe that Attempt |
| Concurrent valid/foreign principal status | `test_concurrent_principals_never_share_a_native_answer` | Foreign principal gets `BridgeError` before native read; valid principal gets the exact inert Unicode answer; Event digest unchanged |
| Many native senders, target drift and lost return together | `test_duplicate_native_sends_with_target_drift_keep_one_original` | 2 and 16 parents; one native write, two original-operation Events, one read reference, zero new Jobs/Attempts, all scheduled tasks drained |
| Lost modifying return | `test_lost_modifying_return_is_unknown_and_original_is_reconciled`, `test_unknown_native_return_retains_journal_without_job_or_attempt` | Selected child reports `EFFECT_UNKNOWN`/`live_submit=None`; native return retains COMMIT_STARTED and withholds answer/admission; recovery reads original, never resubmits |
| STOP before/after claim | `test_worker_stop_never_creates_a_replacement_attempt`, `test_typed_stop_after_claim_has_one_original_effect` | OFFLINE availability before claim prevents an Attempt; after claim preserves original identity. Actual OHF STOP succeeds or retains durable `EFFECT_UNKNOWN`; fresh orchestrator cannot repeat the operation; uncertain STOP retains writer custody |
| Original source replaced / ABA | `test_original_source_identity_survives_no_byte_equivalent_replacement` | Original descriptor retained, final bytes/SHA restored but inode changed; source validator and public native-send consumer refuse; zero native writes or ledger changes |
| Owner lost during capture | `test_owner_lost_during_original_capture_withholds_answer` | Read guard disappears after native bytes are captured; public owner withholds answer and leaves ledger immutable. This models owner-authority loss, not physical process death |
| Quota reaches zero after candidate projection | `test_quota_exhaustion_after_candidate_projection_refuses_claim` | Candidate first exists; public quota-class RATE_LIMITED state makes capacity unavailable before claim; no Attempt |
| Event delivery before commit | `test_event_delivery_before_commit_cannot_see_or_dispatch_it` | Separate SQLite connection cannot see uncommitted WAKE_REQUESTED; dispatch refuses; rollback leaves counts unchanged and zero transport calls |
| Duplicate/reordered wake | `test_reordered_duplicate_wakes_reconcile_the_original_nudge` | Duplicate group refused before provider read; reordered/replayed group preserves original nudge; one nudge and one reconciliation read |
| Late callback after terminal wake | `test_late_callback_cannot_replace_committed_terminal_wake` | DELIVERED and FAILED remain terminal when delayed accepted callback returns; result stays reconciliation-required |
| Duplicate callback / immutable terminal child return | `test_terminal_return_is_immutable_under_duplicate_and_late_callbacks` | Duplicate exact and foreign-Attempt callbacks cannot replace terminal result or Event digest; queues drained |
| Interrupted publication | `test_interrupted_publish_recovers_same_transaction_and_exact_preimages` | Lost returns at two real publication phases; recovery uses original transaction and exact control/worker preimages; no service restart |
| Cancellation before/after claim | `test_cancellation_before_or_after_claim_never_reclaims` | CANCELLED before claim; CANCEL_REQUESTED after claim; exact Attempt/fence retained; repetition cannot create Job/Attempt/Event |
| Readonly model fallback / modifying prohibition | `test_model_fault_fallback_is_readonly_and_secrets_stay_private`, `test_retry_classifier_never_turns_ambiguous_quota_into_replay` | Readonly disconnect/503 may fall back once; modifying, 401 and 429 do not; 429 backoff capped at 900 seconds; unknown/live/stale/modifying retry evidence needs reconciliation |
| Bounded projection | `test_selected_child_bound_refuses_oversized_projection_before_claim` | Oversized child set refused before claim with no ledger or task delta |
| CI invocation loss | `test_runner_cannot_reuse_old_success_after_invocation_loss` | Earlier passing JSON/JUnit cannot survive as the new run's result; launch failure produces nonzero exit, empty test summary and redacted exception type |

The credential checks use an inert sentinel. Model results, metering, captured
logs and relevant uncertainty receipts must not contain it. These assertions
do not claim a global credential scan or authorization-provider acceptance.

## Reproduction and recorded results

Use an existing Python environment with pytest, PyYAML and jsonschema. The lane
runner performs no installation. From the repository root:

```bash
python tests/hermes_contract_chaos/run_lane.py --lane concurrency --seeds 0,1,0x2410 --report /tmp/h24-concurrency.json
python tests/hermes_contract_chaos/run_lane.py --lane failures --seeds 0,1,0x2410 --report /tmp/h24-failures.json
```

For one seed, use `--seeds 0x2410`. For both files in one pytest process, use
`--lane all`. Seeds control release order, not random runtime IDs or Git commit
timestamps. The default regression set is decimal `0`, `1`, `9232` (`0x2410`).

The runner invokes only the two explicitly selected test files, disables
unrelated pytest plugin autoloading and stops conftest discovery at this owned
folder. It preserves the actual pytest exit status. A missing/invalid JUnit
receipt cannot produce success, and an earlier report is removed before a new
invocation. JSON records the exact Python/pytest command, test-file SHA256s,
seeds, counts, elapsed time, budget and `native_service_qualified=false`.

Final measurements and exact local commands are in the committed
[concurrency receipt](../../tests/hermes_contract_chaos/evidence/concurrency.json)
and [failure receipt](../../tests/hermes_contract_chaos/evidence/failures.json).
The commands use the already available interpreter
`/workspace/scratch/16d3df696438/qa-venv/bin/python`; no local package was installed.
Local environment: Linux, Python 3.12.14, pytest 9.2.0, PyYAML 6.0.3,
jsonschema 4.26.0. Python 3.13 and GitHub-hosted execution are not locally proven.

The final two lane processes were launched concurrently on 2026-11-06:

| Lane | Passed | Failures / errors / skips | Pytest duration | Measured process duration | Exit | 60 s budget |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| concurrency | 30 | 0 / 0 / 0 | 11.34 s | 11.751 s | 0 | within |
| failures | 33 | 0 / 0 / 0 | 6.96 s | 7.375 s | 0 | within |

Total: 63 passing cases. Python syntax, workflow YAML/matrix/trigger validation
and the base-relative ownership/diff checks also passed. No hosted CI or
Python 3.13 execution is included in these local receipts.

There are no unresolved failing conformance seeds in the recorded runs. A
failure names its seed in the pytest node ID; replay that seed and the named
test before expanding scope. Initial fixture setup could not bind an AF_UNIX
listener in this execution environment (`PermissionError`/EPERM). That action
was not retried. The lane now always uses an explicit in-process control
transport and makes no socket/startup qualification claim.

## Advisory CI and runtime budget

The new workflow has only `workflow_dispatch`; it has no push or pull-request
trigger, modifies no required check and cannot run because another packet
changed unrelated paths. It creates four independent jobs: concurrency and
failures on Python 3.12 and 3.13, with `fail-fast: false`.

The hosted setup prepares only exact test dependencies (pytest 9.2.0,
PyYAML 6.0.3, jsonschema 4.26.0). It does not install the project or any service,
load model keys, start workers or activate a host. Permissions are
`contents: read`; checkout does not persist credentials. No repository/branch
rule is altered. Actual test failure remains a failing job; advisory means
opt-in and non-required, not `continue-on-error`.

The measured test budget is 60 seconds per lane. `within_budget` is a reported
performance target, not a correctness bypass or a flaky timing assertion.
The job has a five-minute hard timeout including dependency setup and artifact
upload. Timing and JUnit artifacts are retained for seven days. Runs on the
same ref may replace an obsolete source-only run; matrix lanes do not cancel
each other on failure.

GitHub [requires the workflow on the default branch for manual triggering](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).
This packet delivers
the workflow source; it does not merge, dispatch or claim a hosted run.

## Integration ownership and limits

No production contract regression was found by these cases. For a future
failure, the H24-10 builder owns fixture, runner and new-workflow defects.
Route a reproduced contract failure to the existing integration owner below;
this packet does not acquire write authority over those files.

| Failure surface | Exact source owner / entry point |
| --- | --- |
| Duplicate claim / child outcome / callback | `control_plane/executive_service.py`: `dispatch_selected_child`, `selected_child_status`, `_project_terminal_return`; `integrations/hermes_delegate/executive.py`: `ExecutiveSelectedChildComposition` |
| Native principal, original journal or source capture | `integrations/session_bridge/runtime_return.py`: `RuntimeSessionReturn.send_hermes` / `read_hermes`; `integrations/session_bridge/hermes_native.py`: `HermesNativeSession`; `control_plane/native_continuation.py` |
| Pinned source replacement / ABA | `control_plane/executive_fabric_composition.py`: `FabricBindingSource.require_current` |
| Claim, quota or cancellation | `control_plane/executive_runtime.py`: `ResourceBroker.claim`, `WorkerRegistry.set_worker_status`, `JobRegistry.cancel_job` |
| STOP receipt / writer custody | `control_plane/operator_harness_orchestrator.py`: `OperatorHarnessOrchestrator.graceful_stop`; `control_plane/executive_operator_harness_port.py`; existing Runtime OHF registry |
| Wake ordering or terminal regression | `control_plane/wake_dispatcher.py`: `dispatch_persisted_nudge`, `reconcile_persisted_nudge`; `control_plane/wake_persist.py`: `WakeLedgerRepository` |
| Interrupted publication | `ops/executive_os/dialogue_wake_canary_control.py`: `execute_publication`, `ProductionDialogueCanaryHost.recover_publication`; transaction owner in `ops/executive_os/autonomy_control.py` |
| Model fallback / retry classification | `integrations/hermes_models/client.py`: `HermesModelClient.complete`; `control_plane/executive_retry_safety.py`: `classify_retry_safety` |

Principal fixtures bypass external credential verification. Native transport,
provider observations and STOP liveness facts are synthetic. Runtime/Event/
claim/operation/publication code is real, but no live provider or service is
called. Publication configuration is redirected to temporary files. Selected
child transport is in-process, so listener authentication and actual Hermes
startup remain separate acceptance surfaces. Physical owner death, kernel
namespace custody and real Linux Landlock remain unproven here.

The [parent C26 evidence](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2120#issuecomment-6679238494)
remains independent: C27-style fixtures cannot replace actual-unit/Linux
Landlock proof, and this packet does not upgrade the recorded C26 A1 result.

## Parent checkpoint and continuation

**Bounded H24-10 outcome:** source/test delivery with recorded offline evidence.
**Parent Hermes rollout:** not accepted or qualified by this packet.
No merge, approval, service install, activation or production-serving effect
is part of this delivery. There is no live runner, unknown external mutation
or watcher created by the harness.

The parent integration owner should inspect the exact isolated commit and its
base-relative owned diff, then integrate that commit through the existing
source workflow. Its parent must remain the immutable implementation base
above. Do not redo the passing local seed matrix without a material source,
authority, behavior or evidence change. Hosted 3.12/3.13 execution after
integration and real native/host acceptance belong to their respective
existing owners; neither blocks independent source work in other packets.
