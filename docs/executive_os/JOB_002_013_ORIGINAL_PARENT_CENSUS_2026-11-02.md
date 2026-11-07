# JOB-002 / JOB-013 original-parent census (2026-11-02)

**Kind:** read-only source census. **Effect:** none. No host, daemon, database,
socket, Keychain, credential or network read was performed to write this
document. Every live-state statement below is taken from a dated, previously
recorded read and is marked as such. **Current live state is `UNKNOWN`.**

**Purpose.** Programme item R3/E8 asks for the historical queued roots JOB-002
and JOB-013 to be disposed of *through their original parents*: either placed and
completed with the result consumed, or lawfully cancelled with a reason. This
document records what the sources show about each root's original parent, its
last typed state, and what each lawful outcome requires. It does not perform
either outcome.

## 1. Sources

| Ref | Source | What it supplies |
| --- | --- | --- |
| L-E8 | `research/EXECUTIVE_ECOSYSTEM_COMPLETION_CAPABILITY_LEDGER_2026-10-17.md:101` | E8 row: identity, state, original parents, completion test |
| L-171 | same file `:171` | "recovered, never replaced" custody line |
| L-180 | same file `:180` (§5 evidence register, read-only, 2026-10-17) | date and method of the last recorded host read |
| S-JOBS | `control_plane/executive_runtime.py:2664-2710` | `jobs` table: status CHECK (`:2669-2671`), `requested_authorities_json` `:2680`, `allowed_write_paths_json` `:2683`, `result_json` `:2690`, `cancel_requested_at_ms` `:2696`, `CHECK(status != 'COMPLETED' OR result_json IS NOT NULL)` `:2710` |
| S-HIER | `control_plane/executive_runtime.py:2837-2841` | `parent_job_id`, `root_job_id`, `owner_seat`, `escalation_target` migrations |
| S-TERM | `control_plane/executive_runtime.py:469` | `_TERMINAL_JOB_STATUSES` (CANCEL_REQUESTED is not terminal) |
| S-CANCEL | `control_plane/executive_runtime.py:17198-17340` | `JobRegistry.cancel_job` |
| S-FINITE | `control_plane/executive_runtime.py:13294-13308` | `_finite_existing_effect` incumbent-mutation guard |
| S-CLAIM | `control_plane/executive_runtime.py:17668`, `:17807` | `claim_job`; container refused while children are living |
| S-AGG | `control_plane/executive_runtime.py:6293`, `:6334-6360` | `_living_child_rows`; `_assert_parent_aggregation_allowed` |
| S-SVC | `control_plane/executive_service.py:9142-9156` | service commands `ceo-intent-status` (read-back) and `cancel` (`{"job_id"}` only) |
| S-INTENT | `control_plane/ceo_intent.py:897-900`, `:1480-1499` | `command_id_for`; `resolve_intent` (read-back from the `JOB_CREATED` event) |
| S-ARM | `control_plane/executive_coo_cycle.py:732` | COO cycle requires `operator_harness_armed is True` in the root's constraints |
| C-P13 | charter `executive-os-bringup/TASKS.md:38` | P13: dispose JOB-002/003/013 through original parents |
| C-P5T2 | charter `executive-os-bringup/TASKS.md:67` | P5.T2 depends on P4.T3; "no QUEUED historical roots; no replacement roots" |
| C-P4T2 | charter `executive-os-bringup/TASKS.md:64` | P4.T2 independent arming review |
| C-AC7 | charter `executive-os-bringup/NORTH_STAR.md:13` | AC7: COMPLETED-and-consumed or lawfully cancelled with reason; no replacement roots |
| C-D3 | charter `executive-os-bringup/DECISIONS.md:17` | D3: JOB-002/025 `backend_unavailable` is release skew, not a code defect |
| R-P4T2 | `docs/executive_os/P4T2_ARMING_REVIEW_7f1242bfa90f.md` | P4.T2 verdict `ARM_ADMISSIBLE_WITH_CONDITIONS` (C1-C4) |

The charter files are outside this repository (operator charter tree
`gwcap/project-charters/executive-os-bringup/`). They are cited by line, not
copied.

## 2. Census

### JOB-002

| Field | Recorded value | Source | Confidence |
| --- | --- | --- | --- |
| Objective class | Phase 1C-A proof receipt | L-E8 | recorded 2026-10-17 |
| Placement | codex-native | L-E8 | recorded |
| Attempt history | attempt 1 of 3, after a LOST attempt | L-E8 | recorded |
| Last typed state | `QUEUED` since 2026-10-03/10-04 | L-E8, L-180 | recorded 2026-10-17; **live now: UNKNOWN** |
| Read-path note | `backend_unavailable` on read is release skew, not a defect | C-D3 | ruling 2026-10-24 |
| Original parent | one of the CEO intents `auto-84df0a25…` / `auto-640728df…` | L-E8 | **per-job mapping UNVERIFIED** (see §4) |

### JOB-013

| Field | Recorded value | Source | Confidence |
| --- | --- | --- | --- |
| Objective class | read-only SUMMON / post-#1191 acceptance-review aggregation root | L-E8 | recorded 2026-10-17 |
| Placement | codex-coo | L-E8 | recorded |
| Placement blocker | `operator_harness_armed false` blocks codex-coo placement | L-E8, S-ARM | recorded; source-confirmed |
| Last typed state | `QUEUED` since 2026-10-03/10-04 | L-E8, L-180 | recorded 2026-10-17; **live now: UNKNOWN** |
| Original parent | one of the CEO intents `auto-84df0a25…` / `auto-640728df…` | L-E8 | **per-job mapping UNVERIFIED** (see §4) |

### JOB-003 (context only, not in disposal scope)

JOB-003 is bound to the prepared `91c1cac5` acceptance (E6) and is consumed by
that acceptance. It is **never cancelled** (L-E8). Nothing in this document
applies to it.

### Custody

The ledger records all three roots as "recovered, never replaced" (L-171). The
host that holds the runtime database has since passed to the live root
`01a15741` (Agent OS checkpoint, macro commit `d1240079`, 2026-10-30). Any
read or mutation of JOB-002/JOB-013 is therefore a host effect inside that
root's custody. This lane performs neither.

## 3. Lawful outcomes and what each requires

Exactly two outcomes are lawful (L-E8 completion test; C-P13; C-AC7). A
replacement root for the same objective is forbidden in every case (L-E8:
"creating a replacement root duplicates work the brief forbids"; C-P5T2).

### 3a. Placement: COMPLETED, consumed by the original parent

1. **Armed harness.** Placement of JOB-013 needs `operator_harness_armed true`
   (L-E8). The COO cycle refuses a root whose constraints do not carry
   `operator_harness_armed is True` (S-ARM). The arm sequence is P4. P4.T2 now has
   an independent verdict `ARM_ADMISSIBLE_WITH_CONDITIONS` (R-P4T2). P5.T2 depends on
   P4.T3 (C-P5T2), and P4.T3 has not been observed.
2. **Claim gate.** A root that already has children cannot be claimed while any
   child is living ("container job cannot be claimed while child job(s) are
   living", S-CLAIM `:17807`). Whether JOB-013 has children is not recorded in
   L-E8. A host read by the custodian is needed.
3. **Aggregation gate.** If the root has `review_required` children, it can
   complete only after each one has a COMPLETED independent review with verdict
   `approve` from a different worker, and only once no descendant is living
   (S-AGG `:6334-6360`). `tests/test_executive_journeys_offline.py` (H3, H7) shows
   both gates in-process.
4. **Typed completion.** `COMPLETED` requires a non-null `result_json`
   (S-JOBS `:2710`).
5. **Consumption by the original parent.** The parent CEO intent resolves to its
   root through its `JOB_CREATED` event (`command_id_for(intent_id)`,
   S-INTENT). The read-back for this is the service command `ceo-intent-status`
   (S-SVC `:9142-9153`). Consumption means that intent's owner reads the
   COMPLETED root's `result_json`. No new store is introduced.

### 3b. Lawful cancellation with a reason

1. **Mechanism.** Service command `cancel` with exactly `{"job_id"}` (S-SVC
   `:9154-9156`) calls `JobRegistry.cancel_job` (S-CANCEL). For a `QUEUED` job
   this sets `status='CANCELLED'` and appends one `JOB_CANCELLED` event whose
   payload is `{"previous_status": "QUEUED"}` (S-CANCEL `:17234-17239`,
   `:17327-17336`). A non-exact cancel is lawful for a QUEUED root. An exact
   cancel (`expected_attempt_id` + `expected_fence_generation`) needs the job's
   `current_attempt_id` to match. JOB-002 carries a LOST prior attempt, so the
   custodian must read it first if the exact form is used.
2. **Finite-context guard.** Inside a finite control context, a mutation of
   incumbent work is refused unless the context is `bound` and the job belongs to
   that context's root (S-FINITE). A cancel of JOB-002/JOB-013 must not be issued
   from inside another root's finite context.
3. **Reason: SOURCE GAP.** The L-E8 completion test requires "a recorded lawful
   disposition (`cancel_requested_at_ms` + reason)". The current source cannot
   produce that record for a QUEUED root:
   - The QUEUED branch does **not** set `cancel_requested_at_ms`. Only the
     RUNNING/CHECKPOINTED (`:17265`) and RATE_LIMITED/FAILED/LOST (`:17318`)
     branches set it.
   - `cancel_job` takes **no reason parameter** (`:17198-17201`).
   - The event payload carries only `previous_status`.

   So the completion test as written cannot be met by the existing QUEUED-cancel
   path. One of two things is required before a cancel can count:
   - (i) The original parent records the reason in a durable, reviewed record
     (an Agent OS decision or the PR/issue that issues the cancel). That record is
     bound to the `JOB_CANCELLED` event id, and the ledger test is restated to
     accept that pair.
   - (ii) A reviewed source change adds a typed reason and timestamp to the QUEUED
     cancel. This touches cancellation semantics, so it falls under
     review-by-consequence.

   Choosing between them is a programme decision. This document does not make it.

## 4. Unresolved facts (named, not assumed)

| Gap | Why it matters | Reachable resolution |
| --- | --- | --- |
| Per-job original parent | L-E8 lists two intents for three roots, with truncated ids. Which intent owns JOB-002 and which owns JOB-013 is not in the source. | The custodian (root `01a15741`) runs `ceo-intent-status` for each full intent id, or a read-only query of the `JOB_CREATED` events for JOB-002/JOB-013. |
| Live typed state | The last read was 2026-10-17 (L-180). The host has since changed custody. | Same custodian read. Until then, treat the state as `UNKNOWN`, not `QUEUED`. |
| JOB-013 children | The claim and aggregation gates depend on them. | Same custodian read (`parent_job_id = 'JOB-013'`). |
| Cancel reason record | §3b.3 | Programme decision between (i) and (ii). |
| P4.T3 | P5.T2 depends on it (C-P5T2) | Arm sequence owner, after the R-P4T2 conditions C1-C4. |

## 5. Receiver checklist (for the custodian, not this lane)

1. Read back both intents and both roots. Record the exact parent mapping and the
   typed status, attempt and children.
2. If a root is no longer `QUEUED`, stop and reconcile from the observed state.
   Never repeat an effect blindly.
3. For placement: confirm the armed harness and the P4.T3 completion, the claim
   and aggregation gates, then `COMPLETED` with `result_json`, read by the
   original intent's owner.
4. For cancellation: settle the §3b.3 reason path first. Then issue one
   non-finite-context `cancel` and record the `JOB_CANCELLED` event id together
   with the reason in the original parent's record.
5. In every case, create no replacement root and do not touch JOB-003.
