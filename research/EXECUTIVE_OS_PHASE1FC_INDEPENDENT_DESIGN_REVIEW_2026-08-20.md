# Executive OS Phase 1F-C — independent post-P1B design review

**Date:** 2026-08-20
**Reviewer role:** independent architecture/security review
**Runtime design baseline:** merge commit `4f672b8f6b950010534390001f4a17ed232e0390`
**Delivery base at finalization:** `origin/master` `e61e48904302d0aae53baeab0e2681ee3fbec97d` (PR #91; documentation only, no Executive runtime/schema overlap)
**Reviewed commission:** `research/EXECUTIVE_OS_PHASE1FC_CEO_POLICY_AND_IMPLEMENTATION_COMMISSION_2026-08-20.md` at SHA-256 `a5629d0afde16f34109c94e47fb4b64102dd78f6ab8d486a919db381317c5187` (1,372 lines; 22 Markdown fence markers)
**Review mode:** read-only except for this one commissioned review artifact

## STATUS

**PASS FOR INERT IMPLEMENTATION ONLY.**

The exact revised commission identified above closes every design blocker from
the initial independent review and is internally sufficient to commission the
separate, unarmed Phase 1F-C implementation whose runtime design is anchored at
`4f672b8f6b950010534390001f4a17ed232e0390` and whose final delivery base is
`origin/master@e61e48904302d0aae53baeab0e2681ee3fbec97d`.

This is a source-law/design PASS, not an implementation, merge, provider,
host-acceptance, production-dispatch, live-planner, live-vertical, or production-
arming PASS. No Phase 1F-C code or schema-v4 migration exists at this review
point. Every implementation claim remains subject to the commission's
deterministic matrix, fresh implementation review, and the live gates in §11.

## EXACT-SHA RESOLUTION AUDIT

### Mechanical finalization re-attestation

The finalization edit does not reopen the design review. Reversing only the new
header lines reconstructs the previously reviewed 1,368-line commission at
SHA-256 `95c08643e31878181d13466df694febc07d831124c63559a96a9a36c0b39b159`
exactly. The forward diff changes only `Baseline` to `Runtime design baseline`
and adds the delivery-base paragraph; no normative clause, schema, wire,
reservation, state-machine, authority, replay, acceptance, or live-gate byte
changed.

The delivery-base range `4f672b8..e61e489` is the single squash commit for PR
#91 and adds exactly five files under `research/` (1,291 insertions, no deletions).
It changes no `control_plane/`, `config/`, `scripts/`, `tests/`, `ops/`, runtime
schema, provider, host, or acceptance surface. Therefore the exact-SHA source-law
PASS remains valid on the final delivery base.

### Closed initial findings

| Initial finding | Current resolution | Verdict |
|---|---|---|
| broad root grant versus read-only aggregation | Strict v2 roots must contain `READ`. Schema v4 seals a canonical per-Attempt effective grant at claim, constrained to the immutable Job grant. `plan` and `aggregation` are exactly `READ` with empty writes and validations. Claim event, supervisor packet/schema/spec, launch, receipts, and terminal transaction bind one effective-grant digest; the old policy hash cannot substitute. | **Closed in source law; implementation proof pending** |
| v1 CEO intent cannot identify a cycle or root impact | Committed strict v1 remains unchanged, role-null, legacy, and cycle-ineligible. New strict `mastermind.ceo_intent.v2` requires `intent_kind=executive_coo_cycle`, `business_impact`, `READ`, and attempt limit `1..2`; fingerprint, receipt/provenance, `JOB_CREATED`, and the role=`aggregation` root are created/bound atomically. | **Closed in source law; implementation proof pending** |
| provider/account identity lacked an immutable source | Claim now seals an immutable placement JSON/digest from database-immutable Worker/quota provider/account facts with canonical-value and provider-equality fences. Accepted launch then seals a separate execution-principal JSON/digest that references the placement digest and adds OS principal/UID, provider-home identity, and launch-attestation digest/time. No terminal-time Worker reread is evidence. | **Closed in source law; implementation proof pending** |
| plan/root adverse states and `RATE_LIMITED` did not converge | R1 freezes attempt ceilings (non-review orchestration Jobs at most two; review Job exactly one). State-machine classes 2–3 cover `RATE_LIMITED`, `FAILED`, `LOST`, `CANCELLED`, and exhausted plan/work/repair/review/root aggregation paths. Process-adverse review exhaustion maps to `review_jobs_exhausted`; VOID ceiling maps separately to `review_not_independent`. | **Closed in source law; implementation proof pending** |

### Closed consistency and implementability threats

| Threat | Exact revised law | Verdict |
|---|---|---|
| schema ownership/backfill drift | OHF P1B remains schema v3 at the exact baseline. Phase 1F-C must be additive schema v4 with exactly eight nullable Job columns and six paired Attempt columns, null legacy backfill, role/pair/write-once triggers, fresh-v4/migrated-v4 parity, and no inference from historical rows. | **Closed** |
| untyped/lossy plan and verdict wire | Orchestration uses one closed role-discriminated envelope plus five closed role bodies. The full raw role body and digest are preserved; generic `JobPayload` flattening is forbidden. `approve` requires zero blocking findings and empty outer errors; `reject` requires at least one blocking finding. | **Closed** |
| optimistic or under-counted fan-out | One transaction admits the exact completed plan, creates a content-addressed reservation event, and materializes the ordered initial work wave. A reviewed step reserves `3 * (1 revision + 2 review Jobs) = 9` slots; the planner is counted once; the total must be at most 16; slots are step-local and non-transferable. | **Closed** |
| lineage/revision non-convergence | Work round 0, repair rounds 1–2, immediate supersession, current-unsuperseded derivation, exact review pointers, stale-old-approval refusal, and one revision per root/plan/step/round are frozen across columns, indexes, triggers, Runtime predicates, and typed bodies. | **Closed** |
| command replay, concurrent cycles, or subtree escape | Every mutation class has a deterministic command binding over exact target and payload digest. Admission batches have a frozen member manifest. Dispatch binds `(cycle_command_id, exact_job_id)` to at most one Attempt; replay returns/resumes that Attempt or its terminal outcome; a semantic collision raises `StateConflict`; an unrelated sentinel must remain unchanged. | **Closed; crash/liveness behavior must be demonstrated, not inferred** |
| launch failure incorrectly promoted to identity/evidence | Effective grant and placement are required before `JOB_CLAIMED`; the execution-principal pair is required before RUNNING/checkpoint/validation/completion. A pre-launch failed/lost/rate-limited/cancelled Attempt may terminate without that pair but is explicitly barred from review, aggregation, completed-role, and live evidence. | **Closed** |
| attemptless or pseudo-worker root completion | Aggregation is a fresh, ordinary, command-bound root Attempt through the real supervisor, exact READ grant, frozen provider-neutral handoff, launch-attested principal, typed aggregate, terminal revalidation, and ordinary `complete_job`/`JOB_COMPLETED`. | **Closed** |
| planner principal contradiction | Fixture planning proves only the inert state machine. Live acceptance separately requires an independently reviewed Fable/COO planner binding. `frontier.orchestrator` is not silently relabeled and the cycle makes no in-process model call. | **Closed for inert implementation; remains a live gate** |
| production service conflated with inert CLI | The inert change may expose only explicit exact-ID test/CLI dispatch. A separately reviewed, post-Phase-1C-A production exact-ID service is G4 and may not be smuggled into this implementation. | **Closed as a phase boundary** |

### Implementation cautions that do not reopen the design gate

1. The Runtime—not only the cycle CLI—must refuse direct orchestration claims,
   child creation, completion, or requeue that lacks the required role,
   reservation/handoff, lineage, effective-grant, command, and principal
   predicates. In particular, a broad root must not be claimable before its
   current aggregation handoff.
2. A dispatch crash while the command-bound Attempt is active must reconcile
   only that exact Attempt under the accepted supervisor/lease/process-identity
   law. The COO cycle must not use a fleet scan, create a second Attempt, or add a
   liveness store. An in-progress replay may observe the existing binding; after
   ordinary reconciliation makes it terminal, the next governed action follows
   the closed adverse/requeue table.
3. The existing 128-character command-ID grammar means semantic keys and batch
   member suffixes must be deterministically digested/bounded; never truncate in
   a way that permits collision.
4. Worker/quota identity triggers must reject actual provider/account changes
   while permitting updates to unrelated mutable status/heartbeat fields.
   Historical noncanonical or empty identities stay orchestration-ineligible.
5. The exact six Attempt columns are exhaustive for schema v4. Raw result and
   supervisor receipt evidence must use the existing result/metadata/event
   surfaces without loss or author confusion; do not invent an unreviewed
   mutable receipt table or flatten the closed role body.
6. Independence has two explicitly separated claims: different completing
   worker IDs is the deterministic/runtime floor; a live qualifying review must
   also differ in accepted OS principal/UID, provider home, and account label.
   G6 must prove that live-invalid composition produces
   `review_not_independent` and cannot complete the parent; an external post-hoc
   warning after root completion is not that proof.
7. Migration failure must leave v3 logically intact, and the quiesced v3
   verified/restore-drilled backup precedes migration. After successful v4
   migration, recovery is forward-fix only and writers remain stopped until the
   immediate v4 backup/restore drill and schema/TX-9 checks pass.

## HISTORICAL INITIAL RESULT — PRESERVED, SUPERSEDED BY THE EXACT-SHA AUDIT ABOVE

The following findings record why the earlier presented commission was
NO-SHIP. They are intentionally retained as review history. Their requested
amendments are now normative in the exact revised commission and are closed by
the audit above; this historical section is not current implementation law.

### Prior-blocker adjudication

| Prior blocker | Updated verdict | Evidence / consequence |
|---|---|---|
| production depth was effectively 64 | **Closed in source law; implementation pending** | R1 defines root `0`, direct child `1`, no grandchildren, and Runtime-bound enforcement. `_MAX_JOB_DEPTH = 64` remains only a structural ceiling. |
| fan-out and 16-child budget were ambiguous | **Closed** | R1 distinguishes logical work-step fan-out from total direct Jobs and reserves `1 + R * (1 + V)` for a reviewed step. One reviewed step reserves nine children plus the planner. |
| supervisor could not carry review verdict or typed plan | **Closed in protocol design** | §3.1 mandates role-discriminated strict result schemas and lossless round-trip. Existing v1 remains for non-orchestration Jobs. |
| reject → repair could never converge | **Closed in lineage design** | R2/§3.2 define repair revisions, `supersedes_job_id`, current-unsuperseded selection, and stale old approvals. |
| aggregation was attemptless | **Closed** | §4 requires an ordinary fresh root Attempt, frozen handoff, fenced supervisor, and ordinary `complete_job`. |
| Fable planner could not use worker routing | **Closed for inert build; open for live gate** | §3 permits fixture completion, forbids false relabeling, and defers the accepted Fable principal. |
| service accepts only fixed proof Job | **Closed as an explicit phase boundary** | R5/§11 defer a separately reviewed exact-ID production service. |
| review identity was only worker alias | **Predicate closed; evidence source blocked** | R4 defines deterministic/live predicates, but current attestation cannot supply every ruled field without the amendment below. |
| command replay/concurrent creation underspecified | **Closed if implemented in one Runtime transaction** | The commission requires semantic reconciliation, one event/outcome, and atomic reservation plus child creation. |
| adverse non-reviewed child could be omitted | **Closed for work/repair** | §5 blocks exhausted/cancelled/fatal current work and repair revisions. Plan/root adverse states remain incomplete. |

### P0 — aggregation authority is internally contradictory

The root is both the parent grant from which all child authorities/paths shrink
and the Job claimed for the fresh aggregation Attempt. A useful child may need
`WRITE_BRANCH`, so the root must carry `WRITE_BRANCH` and its path superset.
Current claim/supervisor behavior then gives the aggregation Attempt that same
broad grant:

- `JobRegistry.create_job` persists Job authorities and paths;
- `AttemptRegistry.claim_job` re-authorizes the Job and persists only the common
  policy-file hash on the Attempt; and
- `ExecutiveSupervisor._launch_spec` passes `job.requested_authorities` and
  `job.allowed_write_paths` to the adapter.

The commission simultaneously requires only read-shaped aggregation access.
There is no immutable per-Attempt effective grant. An in-memory launch filter
would make durable Attempt evidence disagree with actual process authority.

**Required source-law amendment:**

1. the root remains the broad grant container;
2. every orchestration Attempt persists an immutable effective grant selected
   before claim commits and constrained to a subset of its Job;
3. aggregation v1 uses exactly `READ`, empty write paths, and no worker-authored
   validation commands; and
4. claim event, supervisor, launch attestation, terminal validator, and Attempt
   receipt bind the same effective-grant digest.

Cycle-root CEO intent must require `READ` even when it also grants
`WRITE_BRANCH` for descendants. No nullable bypass or post-claim mutation is
acceptable. A separate aggregation child would contradict §4 and requires a
different superseding ruling.

### P0 — CEO-intent v1 cannot express the ruled root

`mastermind.ceo_intent.v1` is exact-key and has no orchestration discriminator
or `business_impact`. The current adapter creates a generic Job and defaults its
impact to `routine`. The commission requires only typed CEO-intent creation of a
role=`aggregation` root and requires material/critical root impact to force
review.

Treating every historical v1 intent as an aggregation root silently changes a
versioned protocol. Inferring impact from priority, department, actor, prose,
or seat labels is prohibited. Adding optional keys without a version bump also
breaks v1's exact schema.

**Required source-law amendment:** authorize `mastermind.ceo_intent.v2` while
preserving v1 unchanged. V2 must require at minimum:

```text
orchestration_mode = "coo_cycle_v1"
business_impact in {routine, material, critical}
```

The v2 receipt/provenance binds both. Only v2 `coo_cycle_v1` creates an
aggregation root; v1 creates a role-null generic Job and is cycle-ineligible.

The amendment must also state validation semantics. The current parent contract
is only `list[list[str]]` and has no per-step/role mandatory marker. The smallest
safe v1 cycle rule is that every parent validation argv is mandatory for every
write-capable work/repair revision receiving `RUN_TESTS`. Optional or
step-specific commands require typed IDs/bindings in v2, never planner prose.

### P0 — principal snapshot has no lawful complete source

R4 requires worker ID, OS principal/UID, provider-home identity, provider,
`account_label`, launch-attestation digest, and timestamp. The accepted launch
attestation contains OS/process and provider-home identity, but not provider or
`account_label`. Those values currently live only in Worker/quota rows/config.
The commission forbids mutable-row substitution.

Copying a Worker row at result time is forbidden and TOCTOU-prone. Copying it at
claim time makes the copy immutable but not the source host-attested. Adding
strings to an attestation without binding accepted worker composition only
attests what the supervisor asserted.

**Required source-law amendment:** define a compound source:

1. worker/quota placement from the claimed Attempt;
2. OS identity and provider home from observed launch attestation;
3. provider and `account_label` from an immutable host-attested registration
   record/digest created before claim and referenced by launch attestation; and
4. one Attempt snapshot binds both source digests in the accepted-launch
   transaction.

V4 should make identity-bearing Worker fields database-immutable for new use,
but historical rows must not be retrospectively promoted to host-attested
identity. If claim-time Worker-row snapshotting is intended instead, R4 must
explicitly allow it and withdraw the categorical mutable-row prohibition.

### P1 — adverse planning and aggregation states do not converge

The state machine requeues only `work`/`repair` in `FAILED` or `LOST`. Current
Runtime requeue law also supports `RATE_LIMITED`. Missing cases include adverse
plan Jobs, adverse root aggregation Attempts, and review retry-vs-replacement
precedence.

Without a root retry branch, a valid handoff can leave the root `FAILED`
permanently. Without a plan branch, a terminal plan matches neither “no planning
child” nor “completed valid planning child.”

**Required source-law amendment:** add:

```text
plan or aggregation Job in FAILED/LOST/RATE_LIMITED, retry allowed
  -> ordinary same-Job requeue; STOP

plan Job CANCELLED/fatal/exhausted
  -> COO_CYCLE_BLOCKED(reason=plan_terminal_adverse); STOP

aggregation root CANCELLED/fatal/exhausted, or stale handoff after failure
  -> COO_CYCLE_BLOCKED(reason=aggregation_terminal_adverse or
     aggregation_handoff_invalid); STOP
```

For reviews, either set every v1 review Job `attempt_limit=1` so a process
failure consumes one of two review-Job placements, or explicitly exhaust
same-Job Attempts before replacement. The current prose permits both readings.
The former is smaller. Add the new adverse reasons to the closed vocabulary.

## EVIDENCE

Exact baseline:

```text
HEAD          4f672b8f6b950010534390001f4a17ed232e0390
origin/master 4f672b8f6b950010534390001f4a17ed232e0390
SCHEMA_VERSION = 3
```

Load-bearing current surfaces:

- `control_plane/executive_runtime.py:63` — schema version 3.
- `control_plane/executive_runtime.py:85` — structural depth 64.
- `control_plane/executive_runtime.py:328` — shrink omits attempt limit and
  validation narrowing and permits missing cost comparison.
- `control_plane/executive_runtime.py:430` — generic `JobPayload`.
- `control_plane/executive_runtime.py:521` / `:560` — no orchestration lineage,
  effective grant, or principal snapshot.
- `control_plane/executive_runtime.py:850` / `:911` — v2 hierarchy and v3 OHF
  migrations.
- `control_plane/executive_runtime.py:1735` — old aggregation gate lacks lineage
  and handoff binding.
- `control_plane/executive_runtime.py:2228` — one-Job creation; plan admission
  needs a single-transaction batch boundary.
- `control_plane/executive_runtime.py:2736` — claim has no effective Attempt
  grant.
- `control_plane/executive_runtime.py:3719` — terminal payload is normalized as
  generic `JobPayload` before role-aware validation.
- `control_plane/executive_supervisor.py:321` / `:429` — one generic strict
  schema and a mapper that drops orchestration fields.
- `control_plane/executive_supervisor.py:666` — schema selection has no Job role.
- `control_plane/executive_supervisor.py:732` — launch authorities/paths come
  directly from the Job.
- `control_plane/codex_worker.py:2864` — launch attestation lacks
  provider/account label.
- `control_plane/ceo_intent.py:83`, `:113`, `:491`, `:812` — strict v1, no
  impact/mode, generic Job creation.
- `control_plane/executive_service.py:1323` — production service remains proof-
  Job-only, correctly preserving the deferred boundary.
- `control_plane/executive_backup.py:309` / `:457` — backup and manifest require
  exact-current schema.

Focused regression command:

```bash
python3 -m pytest -q \
  tests/test_executive_authority.py \
  tests/test_executive_supervisor.py \
  tests/test_executive_backup.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_inbox_phase1fb.py \
  tests/test_executive_model_router.py \
  tests/test_ceo_intent.py \
  tests/test_executive_os_sqlite.py
```

Result: **178 passed**. This proves v3 baseline coherence, not the unimplemented
v4/Phase 1F-C contract.

## HISTORICAL V4 SHAPE REQUEST — SUPERSEDED BY COMMISSION §4.4

This was the initial review's minimum remedial sketch. The exact revised
commission now owns the normative v4 shape, including the placement-snapshot
pair omitted from this earlier sketch. A builder must implement commission §4.4,
not treat the historical sketch below as a column whitelist.

V4 is necessary. Reusing generic constraints/results, mutable Worker lookup, or
Event prose would not supply the immutable relational gates.

### Jobs: nullable for legacy, immutable when present

```text
orchestration_role TEXT NULL
  CHECK NULL or plan/work/review/repair/aggregation
orchestration_provenance_json TEXT NULL
orchestration_provenance_digest TEXT NULL
  CHECK NULL or 64 lowercase hex
plan_attempt_id TEXT NULL REFERENCES attempts(attempt_id) ON DELETE RESTRICT
plan_digest TEXT NULL CHECK NULL or 64 lowercase hex
plan_step_id TEXT NULL
repair_round INTEGER NULL CHECK NULL or 0..2
supersedes_job_id TEXT NULL REFERENCES jobs(job_id) ON DELETE RESTRICT
```

Reservation and aggregation handoff bodies should be immutable Event-plane
documents, not mutable root columns or a second state store. Add partial unique
indexes so one root has at most one `COO_PLAN_ADMITTED` and one
`COO_AGGREGATION_HANDOFF_READY`. Work insertion and plan-admitted event append
must share one `BEGIN IMMEDIATE` transaction.

Required partial indexes:

```text
UNIQUE(root_job_id, plan_digest, plan_step_id, repair_round)
  WHERE orchestration_role IN ('work','repair')
UNIQUE(supersedes_job_id) WHERE orchestration_role='repair'
UNIQUE(parent_job_id) WHERE orchestration_role='plan'
```

Triggers plus Runtime checks enforce role-specific nullability; root depth 0;
all children depth 1; exact plan Attempt/digest/step; work round 0; repair round
predecessor+1 and same root/plan/step; review pointer to exact same-lineage
revision with no write grant; no cycles/forks/cross-root references; and
write-once orchestration fields.

### Attempts: immutable effective grant and principal snapshot

```text
effective_grant_json TEXT NULL
effective_grant_digest TEXT NULL CHECK NULL or 64 lowercase hex
execution_principal_snapshot_json TEXT NULL
execution_principal_snapshot_digest TEXT NULL CHECK NULL or 64 lowercase hex
```

JSON columns require valid objects. Pair/immutability triggers reject
half-populated pairs or changes after first assignment. Completed orchestration
Attempts require both pairs. A failed-before-launch Attempt may lack a snapshot
and cannot supply review/aggregation evidence.

Effective grant is sealed in claim, is a Job subset, and enters `JOB_CLAIMED`.
Principal snapshot is sealed in the fenced accepted-launch boundary. Terminal
acceptance compares role, effective grant, snapshot, launch, and typed result in
one transaction.

### Typed result protocol

Keep `mastermind.executive_worker_result/v1` and generic `JobPayload`
byte-compatible for role-null Jobs. A non-null persisted role chooses its exact
strict schema. Preserve the canonical typed object; do not flatten through
`JobPayload`. Runtime completion repeats role/schema/job/attempt/lineage/handoff
checks so direct callers cannot bypass the supervisor.

Malformed role output fails the Attempt through ordinary fencing. It is not a
completed role result and never becomes review `reject`.

### Migration/backfill

Append migration 4 after v3 without editing migration 1–3 text/checksums. Run it
under the existing exclusive atomic migration.

- Existing v3 Jobs backfill all orchestration fields to null.
- Existing v3 Attempts backfill effective-grant/snapshot fields to null.
- Never infer role, lineage, principal, or eligibility from actor/seat text,
  reviews pointers, launch metadata, Worker rows, or old results.
- Old rows remain readable/compatible but never count as Phase 1F-C evidence.
- Fresh v4 and populated v3→v4 must have identical schema/index/trigger/FK
  results.
- Injected migration failure must roll back every v4 artifact and leave exact
  v3.

### Backup/restore implications

Current verification deliberately requires exact-current migrations and
`runtime_schema_version`; v4 therefore rejects a v3 manifest. Preserve the OHF
forward-fix precedent:

1. before first authoritative v4 open, quiesce under v3, create/drill a v3
   backup, and prove no unresolved writers;
2. migrate once; failure atomically leaves v3;
3. after success, immediately create/drill a v4 backup;
4. v3 refuses v4 and v4 may continue to refuse v3 backup;
5. after successful migration, rollback is forward-fix only—never delete v4 or
   OHF evidence; and
6. v4 restore preserves Phase 1F-C evidence and still performs OHF TX-9
   invalidation before service re-enable.

If v4 must restore v3 directly, separately review a staged prefix-migration
path: verify exact known v3 receipts, migrate an isolated copy, validate full
v4/hash/TX-9, then atomically swap. Never merely relax migration verification.

## HISTORICAL SHIP-BLOCKING TEST REQUESTS — NOW INCORPORATED

These initial requests remain useful regression names/themes. The revised
commission's §§4.5, 8, and 9 are the complete current acceptance law and add the
closed wire, reservation, command-collision, pre-launch-principal, and adverse-
state cases.

1. `test_ceo_intent_v1_remains_generic_and_cycle_ineligible`
2. `test_ceo_intent_v2_requires_cycle_mode_and_business_impact`
3. `test_material_root_forces_review_when_plan_says_false`
4. `test_aggregation_attempt_effective_grant_is_read_only_subset_of_broad_root`
5. `test_launch_spec_and_attempt_bind_same_effective_grant_digest`
6. `test_direct_claim_root_without_current_handoff_refuses`
7. `test_direct_complete_generic_payload_cannot_bypass_role_gate`
8. `test_snapshot_refuses_provider_or_account_from_unattested_mutable_row`
9. `test_snapshot_binds_registration_and_launch_attestation_digests`
10. `test_post_launch_worker_row_mutation_cannot_change_independence`
11. `test_v3_rows_backfill_null_and_never_become_orchestration_evidence`
12. `test_failed_v3_to_v4_migration_rolls_back_every_v4_artifact`
13. `test_fresh_v4_and_migrated_v4_have_identical_schema_contract`
14. `test_v4_backup_restore_preserves_lineage_snapshot_handoff_and_ohf`
15. `test_v4_code_refuses_v3_backup_under_exact_version_policy`
16. `test_plan_failed_lost_rate_limited_requeues_or_blocks_at_limit`
17. `test_aggregation_failed_lost_rate_limited_requeues_exact_root_same_handoff`
18. `test_cancelled_or_exhausted_aggregation_emits_one_adverse_block`
19. `test_review_process_failure_obeys_ruled_retry_replacement_policy`
20. `test_aggregation_worker_receives_only_materialized_provider_neutral_handoff`

Tests 4–7 must use a root that actually grants `WRITE_BRANCH`; a read-only root
hides the contradiction. Tests 8–10 must distinguish worker-ID-only runtime
minimum from the stronger live predicate. Migration fixtures must populate v3
OHF epochs/generations/operations, Jobs, Attempts, and immutable events; an
empty migration is insufficient.

## HISTORICAL GAPS — CLOSED OR DEFERRED BY THE EXACT REVISION

- Amend the four source-law gaps before implementation authority opens.
- Fable route, two-principal composition, Phase 1C-A exact-SHA acceptance, and
  production exact-ID service remain deliberate later live gates; they do not
  block an inert build after design closure.
- The commission was an untracked worktree artifact, not part of
  `origin/master@4f672b8`; this review assesses its presented bytes but does not
  claim the ruling is merged.
- No Phase 1F-C code or schema v4 exists to implementation-review.

## CURRENT GAPS AND REMAINING GATES

- **Implementation is still absent.** This PASS authorizes only the separately
  bounded inert build against the named baseline. It does not assert that schema
  v4, the cycle, role schemas, exact dispatch, migration, backup, or tests exist.
- **Implementation acceptance remains mandatory.** The builder must satisfy the
  full deterministic matrix, focused/full CI, migration and backup drills,
  golden role-schema digests, direct-Runtime bypass tests, and a fresh independent
  implementation review before merge.
- **The source-law artifacts are not merged.** At review time both the commission
  and this review are untracked in the worktree; the PASS applies to their exact
  reviewed bytes and does not claim `origin/master` contains them.
- **G0/G1 remain:** freeze a later exact merged release; install with services
  stopped; establish provider readiness; pass Gate B and receipt review; pass
  formal Phase 1C-A acceptance; and prove the exact v3→v4 quiesce/backup/
  restore/TX-9 sequence before orchestration writers run.
- **G2/G3/G4 remain:** accept distinct builder/reviewer worker composition,
  immutable live principal evidence, the truthful Fable/COO planner principal,
  and the separately reviewed production exact-ID dispatch service.
- **G5/G6/G7 remain:** run the Sol→COO→worker→independent-review→fresh-
  aggregation→readback live vertical and its adverse proof, obtain independent
  packet acceptance, and keep `production_armed=false` until a later explicit
  operating-envelope decision.

## DEVIATIONS

- No implementation/config/runtime/provider/credential/service/host/Git/deploy
  state changed.
- The only durable write is this explicitly commissioned review artifact.
- Tests used temporary local state only.

**Historical verdict (superseded):** materially stronger and close, but not yet
safe to authorize even an inert build. Amend the four gaps, retain the v4 shape
above, and rerun the independent design gate.

**Current final verdict on commission SHA-256
`a5629d0afde16f34109c94e47fb4b64102dd78f6ab8d486a919db381317c5187`: PASS FOR
INERT IMPLEMENTATION ONLY.** Every prior design blocker is closed. No host,
provider, production-dispatch, live-planner, live-vertical, or arming claim is
made.
