# Coding-job reuse map — Paperclip task as origin and return (for L10)

Date: 2026-11-10. Owner: L1 driver (lane `t3/mmos-v2-l1r`). Basis: trunk
`feat/mmos-v1-integration-t3` at the L1R landings; plan V3 decisions 6/9 and §8a.

A coding job whose origin and return target is a **Paperclip task** reuses the
engine L1 proved live (R3/R4 canary). Nothing below is new machinery; it is the
checklist of what is reused **as is**, and the seams where task-origin pieces plug in.

## Reused as-is (do not rebuild)

| Piece | Entry point | What it already does |
|---|---|---|
| Host tool: admit by frozen command | `integrations/mastermind_executive_app/coo.py:659` `CooApp.child_request_admit` | Trusted-host caller names one host-frozen admission command; the App proves principal/work-ref (incl. the L1B3-1 refusal), builds the private frame from its own providers, sends once, maps every owner answer honestly |
| Control frame lane | `control_plane/executive_service.py:6915` dispatch, `:6963` `_handle_child_request_admit_frame` | Same installed-facts proof as status/result before dispatch (L1B3-1), command-id identity check, idempotent admission, precise conflict/wait |
| Admission idempotency | `control_plane/child_request_admission.py:198` `admission_command_id`; `control_plane/executive_runtime.py:16702` `admit_child_execution_request` | One Job per `(root_ref, immediate_parent_run_ref, logical_child_key)` + digest; replay returns the first handle, drift is a precise conflict |
| Admission → placement Job | `control_plane/child_request_execution_composition.py:70` `compose_child_execution` | Admits + creates the placement Job (one Job per logical key; `placement_command_id` at `:43`) |
| Claim | `control_plane/executive_runtime.py:19649` `claim_job` | Placement + quota + fenced `ExecutionBinding`; per-attempt `operation_key` stamped here |
| T3 native execution | `control_plane/t3_native_composition.py:608` `compose_t3_native_adapter` | Enrolled token file → attested namespace → port with launch arguments; typed refusals for broken enrollment |
| Durable adapter state | `control_plane/t3_execution_adapter.py:1354` `SQLiteT3AdapterStateStore` (`put_launch_receipt` `:1668`, `launch_thread` `:1865`) | Intent + receipt + original ref committed before ACK (the R4 crash window) |
| Reattach / adopt | `control_plane/t3_execution_adapter.py:2713` `T3ExecutionAdapter.reattach`; `control_plane/executive_runtime.py:20451` `adopt_attempt`, `:20882` `record_process` | Cold-process recovery of the SAME attempt: zero native launches, fence bump, `T3LaunchClaimConflictError` on any second start |
| Execution return | `control_plane/execution_return_wiring.py:100` `ExecutionReturnWiring`, `:478` `install_execution_return_seam` | `execution_return/v1` with real GitHub evidence; one receipt per attempt, ever (`execution_return_receipt_command_id` dedupe, `:304`) |
| Return routing (new, landed L1R) | `control_plane/result_delivery.py` (`OriginRef`, `ResultDeliveryRegistry`, `HermesResultDeliveryTransport`) | kind → transport; unknown kind is a typed `ORIGIN_KIND_UNKNOWN` refusal; retry delivers exactly once (tests `tests/test_result_delivery_pluggable.py`) |

## Seams the task-origin pieces plug into

1. **Request origin ids.** `ChildExecutionRequest` v1.2 already carries
   `original_requester` (`control_plane/child_execution_contracts.py:795-814`):
   `teammate_id`/`conversation_id`/`project_id` are opaque bounded ids and
   `carrier_kind` is free-form. A Paperclip origin = `carrier_kind:
   "paperclip_task"` + the task's ids in those fields (the wiring routes on
   `requester_block["carrier_kind"]`, `execution_return_wiring.py` `_deliver`).
   The triple `(root_ref, immediate_parent_run_ref, logical_child_key)` becomes
   task-derived company ids (e.g. `roots/<task-id>`, `parents/<task-tab-origin>`,
   `key=coding-job-1`). Slash-free token law applies (canary deviation note).
2. **Return transport.** Register one `paperclip_task` transport in the
   `ResultDeliveryRegistry` at the seam install site (where the composing
   supervisor calls `install_execution_return_seam`). The transport receives
   `(OriginRef, execution_return/v1 payload)` and writes to the task. The
   registry refuses unknown kinds — a task whose transport is missing gets an
   honest `ORIGIN_KIND_UNKNOWN` receipt, never a silent drop and never a
   Hermes mis-delivery.
3. **Job/attempt ids a task tab shows.** The task tab reads Runtime
   projections (job_id from the admission projection; attempt_id, status
   sequence, fence generation from attempt events; `execution_return/v1` and
   `EXECUTION_RETURN_DELIVERY` events for the return states). No new ledger:
   the tab is a reader over the existing store.

## What the canary already proves (`integrations/t3/live_proof/t3_admitted_canary.py`)

- The full chain v1.2 request → admission → placement Job → claim → T3 native
  launch → ONE real thread → collect → complete → `execution_return/v1` with
  real GitHub evidence → delivery attempt (honest REFUSED, R9) — R3.
- Restart safety on the same attempt: crash after durable receipt before ACK;
  cold process reattaches with **zero native calls**, second start refused,
  `adopt_attempt` fence 2, exactly one upstream run — R4.
- Wrong-namespace client refused with zero calls; exact-run interrupt settles.

## What DONE_WHEN 5 and 9 still need

- **5** (task becomes one coding job; verified GitHub result returns to the
  task): the two seams above — a task-origin `original_requester` block, and a
  `paperclip_task` transport registered at install. Engine side is done.
- **9** (works with the window closed; interrupted job recovered by a fresh
  process as the original job, no second launch): the R4 mechanism is proved,
  but **L1B3-5 is open**: `ExecutiveSupervisor` classifies an attempt that
  crashed between `put_launch_receipt` and `record_process` as
  `AWAITING_LEASE_EXPIRY` (`control_plane/executive_supervisor.py:5490`) and
  `adopt_attempt` refuses `pid IS NULL AND provider_session_id IS NULL`
  (`executive_runtime.py:20527`). The canary works around it with a test-only
  sidecar lease file. Production recovery of that window needs the supervisor
  fix (build-list item 8) — it blocks DONE_WHEN 9, not 5.

## One-initiator rule (plan V3 §8a, binding)

Paperclip holds the work item (owner, objective, discussion, blockers, outputs)
and **never admits, schedules, retries or accepts the job**. The Executive is
the only admission owner; T3 executes; acceptance is a human/owner act recorded
on the task, read from the return states. A module tab that shows a job starts
nothing. One work item may have several jobs; identities join explicitly.

## Build list for L10 (each item + its check)

1. **Task-origin envelope builder** (module tool): builds the v1.2 request with
   `carrier_kind: "paperclip_task"` + task ids; the host freezes it as
   `child_request_material`. *Check:* envelope validates; forwarding test proves
   the envelope never travels through the caller.
2. **`paperclip_task` return transport** registered at the seam install site.
   *Check:* pluggable-delivery tests green incl. exactly-once retry; unknown
   kind refuses honestly.
3. **Admission call from the task tab**: one call to `child_request_admit`
   naming the frozen command. *Check:* ADMIT/REPLAY/conflict/WAIT round-trip on
   a scratch Executive (reuse the ingress tests' `_admission_material` shape).
4. **Task tab reader**: job/attempt/status/fence + the four return states
   (produced/delivered/reviewed/accepted) from Runtime events. *Check:* widget
   test over a real store fixture; a refused delivery shows its refusal code.
5. **Durable-state continuity for the task-origin job**: scratch-root canary of
   the R4 shape re-run with Paperclip ids. *Check:* cold P2 recovery, zero
   native launches, receipt on the task.
6. **Blocker surfacing**: queue-full WAIT and `ORIGIN_KIND_UNKNOWN` appear as
   blockers with reason/age on the task (DONE_WHEN 10's coding-job half).
   *Check:* module test feeds a WAIT projection and a refused receipt.
7. **Scratch/dev boundary**: dev instance + scratch Executive root only
   (`~/.cache` scratch pattern; default Paperclip instance and production
   Executive untouched). *Check:* no write outside the dev data dir; negative
   matrix for a non-peer uid on the local door.
8. **L1B3-5 supervisor adopt** (engine fix L1 recorded OPEN): startup
   reconciliation, when `pid IS NULL AND provider_session_id IS NULL` and a
   persisted adapter receipt exists, reattaches under a new fence instead of
   `AWAITING_LEASE_EXPIRY` → `EXPIRED_LOST`. *Check:* supervisor test with the
   canary's crash window; DONE_WHEN 9 unblocked.

— L1 closes here. The engine pieces above are on trunk; the map is L10's input.
