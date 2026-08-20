# Executive OS Phase 1F-C — CEO policy ruling and implementation commission

**Date:** 2026-08-20

**Authority:** AI CEO Sol, acting under the Chairman's Executive OS completion
directive and the hierarchy in `AGENTS.md` / `CLAUDE.md`

**Runtime design baseline:** Mastermind merge commit
`4f672b8f6b950010534390001f4a17ed232e0390` (OHF P1B PR #93; descends from
provider-readiness PR #92)

**Current amendment delivery base:** Mastermind `origin/master`
`a790fb56c1c557197927dee9a76356a47188191b` (Phase 1F-C source-law PR #94;
the Executive runtime remains byte-identical to the reviewed OHF P1B baseline)

**Status:** **SOURCE-LAW REMEDIATION REVISED ON THE EXACT MERGED OHF P1B
BASELINE. IMPLEMENTATION REMAINS UNAUTHORIZED UNTIL AN INDEPENDENT REVIEWER
RE-REVIEWS THIS REVISION AND WRITES PASS. NOT HOST-ACCEPTED. NOT
PRODUCTION-ARMED.**

**Closes:** all six questions in
`research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md` §6

**Preserves:** that contract's laws L1–L10 and its §3.4 requirement that an
ordinary, fenced worker Attempt completes the parent through `complete_job` only
after the runtime's aggregation refusals pass. The OHF constitution's §4 and §11
fresh-Attempt law is binding. This revision withdraws the earlier proposed
attemptless container transition in full. It does not supersede the Executive
authority map, the Phase 1C-A host/acceptance contract, the OHF constitution, or
any higher source of truth.

This document is the canonical CEO ruling needed by §6's “do not build past
these” barrier and the remediated commission for the Phase 1F-C builder. The
commission is conditional: OHF P1B owns runtime schema version 3 and has merged
at the exact baseline above; this revision now freezes the Phase 1F-C schema-v4,
wire, grant, reservation, state-machine, replay, and backup law on top of it.
Until an independent reviewer re-reviews these exact bytes and writes PASS, no
implementation is authorized. This document grants no runtime, host, provider,
merge, deployment, service-control, credential, or production-arm authority.

---

## 1. Outcome and truthful completion boundary

Phase 1F-C is commissioned to add one explicit, deterministic COO bookkeeping
command after the implementation gate above opens:

```text
scripts/executive_os_coo_cycle.py run-once --parent JOB-nnn
```

One invocation reads canonical Executive OS state, performs at most one eligible
state-machine step, writes through the existing Runtime APIs, emits durable
receipts, and stops. It does not remain alive, poll, schedule, select company
priority, call a model in-process, or own state outside the existing Executive
SQLite store.

There are three separate completion claims:

1. **Implemented and deterministically accepted:** the bounded code, refusals,
   fixtures, documentation, and adversarial review are merged on
   `origin/master`. No host or provider claim follows.
2. **Phase 1C-A host accepted:** the eventual frozen exact SHA has passed
   install, provider readiness, Git handoff Gate B, and the formal one-worker
   Phase 1C-A acceptance procedure. This proves the execution substrate, not the
   COO vertical.
3. **Phase 1F-C live vertical accepted:** on an exact host-accepted release, a
   receipted Sol intent is planned through an accepted Fable/COO planner
   principal, executed by a bounded worker, independently reviewed when required,
   aggregated, and read back by Sol. Only this third receipt proves the live
   organizational loop.

Merging the build is not activation. Phase 1F-C must remain unarmed until the
separate live gates in §11 pass.

---

## 2. CEO rulings that close §6

### R1 — policy home and exact schema-v1 bounds

The sole reviewed home is a new `coo_cycle_policy` block in
`config/authority_map.yml`. No duplicate YAML, environment override, CLI
override, database setting, or cycle-local default may alter these values:

```yaml
coo_cycle_policy:
  schema_version: 1
  max_fan_out_per_parent: 8
  max_depth: 1
  max_repair_rounds: 2
  max_review_attempts_per_job: 2
  max_children_total: 16
  max_attempts_per_orchestration_job: 2
  review_job_attempt_limit: 1
  allowed_child_cost_classes: [default, small]
```

The semantics are binding:

- A root Job has `depth=0`.
- Planning, execution, review, and repair Jobs created for the v1 cycle are
  direct children at `depth=1`.
- Grandchildren (`depth=2`) are prohibited. Nested decomposition needs a new CEO
  ruling and reviewed policy revision.
- `max_fan_out_per_parent` is the maximum number of **logical work-plan steps**
  admitted from one validated plan. Planning, review, replacement-review, and
  repair Jobs do not consume this logical-step counter; they consume the absolute
  child budget below. A value of `8` is a ceiling, not a promise that eight steps
  can fit after review and repair capacity is reserved.
- `max_children_total` counts every direct non-root Job in the root tree:
  planning, initial work, every review or replacement-review Job, and every
  repair revision. Because v1 permits depth `1` only, there are no deeper Jobs to
  exclude. The total is checked against existing children and reserved future
  children, never only against the batch currently being inserted.
- A repair round is a cycle-authored replacement-work wave after a completed
  `reject` verdict. The initial work is round zero; at most rounds one and two may
  be created.
- `max_review_attempts_per_job` is a legacy policy-field name. It caps review
  **Job records per work revision**, including the initial reviewer Job and any
  replacement reviewer Job after a rate-limited, failed, lost, cancelled, or void
  review. It
  does not cap Attempts within one review Job. Every review Job has immutable
  `attempt_limit=review_job_attempt_limit=1`; creating a different review Job
  does not reset the two-record per-revision cap.
- `max_attempts_per_orchestration_job=2` is the hard same-Job Attempt ceiling for
  the root aggregation Job and every `plan`, `work`, `repair`, or `aggregation`
  Job. The strict v2 root intent must request `attempt_limit <= 2`; every derived
  non-review Job must have an explicit limit no greater than the root and no
  greater than `2`. A review Job is always exactly `1`. These are ceilings, not
  retry promises: a denied, cancelled, fenced, or otherwise ineligible transition
  may stop before the numeric ceiling is consumed.
- Provider lifecycle cardinality is a separate non-configurable protocol ceiling:
  `MAX_ORCHESTRATION_EPOCHS_PER_ATTEMPT=1`,
  `MAX_ORCHESTRATION_TX5_PER_GENERATION=1`, and
  `MAX_ORCHESTRATION_TX5_PER_ATTEMPT=2`. A same-OperationId TX-5 replay that
  reconciles the already allocated `TurnRef` under the frozen dispatch-marker law
  consumes no new slot. A different TX-5 OperationId in the same generation
  always refuses. The only possible second distinct turn in one Attempt is on the
  same epoch's freshly TX-4-admitted G2 after the closed G1 pre-candidate process-
  loss state in §4.4; a G1 candidate, checkpoint, result observation/seal,
  effect-unknown ambiguity, or invalid result leaves no second-turn path. Frozen
  P1B has no G3. An orchestration Attempt may allocate only E1; an abandoned,
  poisoned, failed, or unrecoverable epoch cannot be replaced inside that Attempt,
  even when no TX-5 occurred. Thus one Attempt causes at most one provider session
  start, one same-epoch resume, and two provider work-turn calls, and no cost/
  Attempt ceiling can be bypassed by repeated start, epoch, generation, or turn
  operations.
- Every child has `requested_authorities` no wider than its parent,
  `allowed_write_paths` no wider than its parent, `attempt_limit` no greater than
  its parent, and an explicit `cost_class` in both the parent's allowed set and
  `[default, small]`. Every child's `attempt_limit` and cost class must be
  persisted explicitly; a caller or schema default is not proof of shrinkage.
- The strict v2 root intent's ordered `validation_commands` list is the one
  reviewed validation set. Every cycle-created `work`, `repair`, or `review` role
  carrying `RUN_TESTS` inherits that exact ordered list: no subset, reordering,
  addition, or planner downgrade is valid. Each command is named in the plan by
  `validation_id = sha256(canonical_json(argv))`; because every root validation
  is mandatory, the selected ordered IDs must equal the root-derived ordered IDs.
  A role without `RUN_TESTS` has an empty validation list. `plan` and
  `aggregation` never carry `RUN_TESTS` and always have empty validation lists.
  Validation argv is data, never a free-form command inferred from prose.
- Review Jobs are strictly read-only over the reviewed tree: their authorities
  are limited to `READ` and, when explicitly allowed, `RUN_TESTS`; their
  `allowed_write_paths` is empty.
- A missing, duplicated, malformed, unknown-schema, or out-of-range policy block
  fails closed before hierarchical Job creation or cycle action.

Plan admission is a single atomic reservation event, not optimistic fan-out. It
is eligible only when the root has exactly one completed, schema-valid `plan`
child and no other child. Let `R = 1 + max_repair_rounds` and
`V = max_review_attempts_per_job`. For each admitted logical step:

```text
step_slots = 1                                      if review is not required
step_slots = R * (1 work/repair revision + V review Jobs) = 9  if required
reserved_children_total = 1 + sum(step_slots)
```

The leading `1` is the already persisted planning Job and is not added a second
time. With the fixed v1 values, one reviewed step therefore reserves exactly ten
direct-child slots total; an unreviewed step reserves two total. In one
transaction, before any work Job is materialized, the runtime validates the typed
plan, derives review requirements, verifies the exact existing-child precondition,
and appends one immutable content-addressed `COO_PLAN_ADMITTED` event containing
the plan Attempt ID/digest, root/policy digest, ordered `(step ordinal, step_id,
step_slots)` entries, `reserved_children_total`, and event digest. It rejects the
whole plan if the total exceeds `16`. Plan admission/reservation is an event, not
a mutable table or mutable Job field. Any unexpected or pre-admission child
refuses admission. Unused slots are non-transferable; every later child creation
atomically checks its step-local remaining slots and the tree-wide reserved total.
There is no partial admission and no promise that eight logical steps fit.

The current code's `_MAX_JOB_DEPTH = 64` is only an absolute structural sanity
ceiling. It is not policy and may never be the effective Phase 1F-C ceiling.
`Runtime.jobs.create_job`, not merely the CLI or cycle script, must enforce the
reviewed `max_depth=1` so a direct caller cannot bypass it. Keeping 64 as a
secondary internal corruption guard is allowed only when the policy ceiling is
also applied and wins.

### R2 — binary review verdicts

Version 1 has exactly two non-empty review verdicts:

```text
approve
reject
```

`request_changes` is not a third verdict. A review that runs successfully and
finds defective work completes with `verdict=reject` and at least one
`severity=blocking` finding in the closed review role body. An `approve` result
requires no blocking finding and an empty outer `errors` array. Failure of the
review process itself remains an Attempt failure and is not converted into a
verdict. Non-review role bodies have no `verdict` field at all; an empty, missing,
or unknown review verdict is a result-protocol refusal, never review evidence.

The COO cycle interprets `reject` as permission to create only the next bounded
repair round. It does not mutate the rejected Job, broaden the parent, or
reinterpret failure as success.

`review_required` is derived fail-closed, not accepted from the planner as a
downgrade. For every v1 logical step the runtime computes:

```text
typed_plan_requests_review
OR parent/root business_impact in {material, critical}
OR step business_impact in {material, critical}
```

The planner may promote a `routine` step to reviewed by requesting review. It may
never turn review off when either the root or step impact makes it mandatory.
Missing, unknown, malformed, or contradictory impact/review fields refuse plan
admission rather than defaulting to unreviewed work.

A reject and its evidence remain immutable. The repair child is a new revision
with `orchestration_role=repair`, the same logical `plan_step_id`, the next
`repair_round`, and `supersedes_job_id` pointing at the rejected current revision.
A later review points to that repair revision, not the rejected predecessor. Only
an independent `approve` of the current, unsuperseded revision can satisfy the
step. An approval created later for an old rejected revision is stale evidence
and cannot waive, erase, or outrank the repair lineage.

### R3 — no executive-seat registry in Phase 1F-C

Do not add `seats.yml`, a database seat table, or any other machine-readable seat
registry. `chairman`, `ceo`, and `coo` remain provenance-fenced descriptive
vocabulary under the hierarchy in `AGENTS.md` / `CLAUDE.md`; they grant no
capability. `config/agents.yml` remains model-role routing, not organizational
identity.

Runtime `worker_id` identifies execution capacity, not an executive seat. A
future Wake phase may propose the contract's smallest `authority: none` seat
mapping inside `config/authority_map.yml`, but that is outside this commission.

### R4 — production independent-review bar

The deterministic/runtime minimum remains different completing-attempt
`worker_id` values. Identity is read from the immutable, stable Attempt-level
`mastermind.execution_principal_snapshot/v1` objects in §4.4, never from a
terminal-time mutable Worker/config lookup. Each snapshot contains exactly
`schema_version`, `attempt_id`, `worker_id`, `quota_class`, `provider`,
`account_label`, `placement_snapshot_digest`, `os_principal_name`,
`os_principal_uid`, and `provider_home_identity`. Provider/account placement is
copied at claim only from v4 database-immutable registration rows and joined to
the supervisor-authored principal facts inside the Runtime's accepted launch/
admission transaction. It is not inserted into or inferred from the frozen
`ObservedHarnessAttestation`.

For `OPERATOR_HARNESS`, every qualifying process generation separately persists
its exact observed-attestation digest, raw typed principal observation (including
`observed_at_ms`), and stable snapshot digest in
`ORCHESTRATION_WORK_ADMITTED`. G1 and G2 may therefore prove the same stable
principal while retaining different generation/attestation/time evidence.
Independence and result acceptance require both the stable completing-Attempt
snapshot and the exact qualifying-generation admission/result binding defined in
§4.4; a missing, stale, later-generation-superseded, or mutable-row-derived value
refuses.

Live production acceptance requires all of the following:

1. reviewer completing-attempt `worker_id` differs from the reviewed work's
   completing-attempt `worker_id`;
2. the two worker IDs are host-attested to different OS principals;
3. the two worker IDs are host-attested to different provider homes and different
   `account_label` values; and
4. the reviewer has only read-shaped authority over the reviewed tree: `READ`
   and, when declared, `RUN_TESTS`, never `WRITE_BRANCH` on that tree.

Different provider vendors are not required. Two separately accepted Codex
worker slots may qualify. A missing, equal, stale, mutable-row-derived, or
unattested OS-principal, provider-home, or account binding makes the review
**VOID for live acceptance**.
The review Attempt may be honest and terminal; it simply supplies no aggregation
authority.

Review is a sibling Job with `reviews_job_id` pointing at the work Job. A review
Job may not itself require review. Independence is adjudicated after claim and
completion because worker assignment does not exist at creation time.

### R5 — delivery and host sequence

The sequence is:

1. Phase 1F-B hierarchy, aggregation refusals, and inbox-v2 evidence kinds —
   already accepted and merged.
2. This CEO ruling.
3. OHF P1B has merged first and owns Executive runtime schema version `3`.
4. Rebase the Phase 1F-C commission and implementation branch on the exact OHF
   P1B merge. The merged v3 shape has now been inspected: it cannot represent the
   required immutable orchestration lineage, effective grant, placement, and
   execution-principal snapshots/generation-bound admission and result seals.
   Phase 1F-C
   therefore **must** add schema
   version `4` exactly as frozen in §4.4. It must not renumber, fork, overwrite,
   reclassify, or backfill v1-v3 rows.
5. A fresh independent threat review of these exact revised bytes must write
   `PASS` and state that every design blocker is closed. Only then is the separate
   inert Phase 1F-C implementation authorized.
6. Build and merge Phase 1F-C with deterministic acceptance and independent
   implementation review.
7. Merge all code and acceptance-harness changes intended for the next runtime,
   then freeze one exact `origin/master` SHA.
8. On that exact SHA: install with services stopped, establish provider readiness,
   pass Git handoff Gate B, stop for receipt review, then pass formal Phase 1C-A
   acceptance.
9. Separately accept the worker-capacity composition and Fable/COO planner
   principal required by the live vertical.
10. Separately review and accept a production exact-ID dispatch service boundary;
    the inert/test explicit supervisor CLI is not operational dispatch proof.
11. Run the Phase 1F-C live vertical acceptance on an exact accepted release.
12. Consider production arming only in a separate explicit decision.

Phase 1C-A formal acceptance is therefore a prerequisite for **live execution,
the production dispatch boundary, and live Phase 1F-C acceptance**, not for the
post-P1B inert build. Accepting an intermediate SHA and immediately changing the
runtime would prove only the superseded bytes and is not the chosen sequence.

### R6 — independence starvation always escalates; it never self-waives

Each completed VOID/non-independent review creates at most one replacement under
the two-review-Job ceiling. If another VOID is encountered when no review-record
slot remains, the cycle surfaces `review_not_independent`. A review process that
ends `RATE_LIMITED`, `FAILED`, `LOST`, or `CANCELLED` is not an independence
verdict; when that adverse Job has no remaining Attempt or replacement-record
slot, the cycle instead surfaces `review_jobs_exhausted`. In every case the parent
remains incomplete.

There is no waiver for `routine`, `material`, or `critical` impact. No CEO chat
sentence, actor label, provenance note, impact downgrade, cycle flag, or direct
`complete_job` call may convert missing independent evidence into success. The
CEO may commission accepted capacity, cancel the objective, or submit a newly
bounded objective. A future waiver would require a new schema vocabulary, a
  superseding CEO decision, and independent security review; the Phase 1F-C v1
  policy/result vocabulary contains no waiver field or path.

---

## 3. Fable/COO planner contradiction — binding resolution

The existing contract requires the cycle to create and dispatch a planning child,
but the current router returns `planning` as `frontier_lead` and refuses to turn
frontier-lead work into worker Job constraints. `frontier.orchestrator` is also
`worker_eligible=false`. Renaming a generic worker or treating a model alias as
the COO would be a false resolution.

The ruling is:

- The COO cycle itself is deterministic bookkeeping and makes **no in-process
  model call**.
- Planning is a bounded, durable Job in the same Executive OS lifecycle. It has
  a Job ID, Attempt ID, claim, worker/process identity, exact input provenance,
  result, and terminal receipt.
- Before live acceptance, that Job must route through an explicitly reviewed
  Fable/COO planner principal. The binding must say which logical planner role,
  model/provider, OS principal, provider home, account label, capabilities, and
  policy version completed the Attempt.
- The planner receives the typed CEO parent intent and returns a schema-valid
  `mastermind.execution_plan/v1` result or content-addressed artifact. It proposes
  decomposition only. It cannot dispatch, widen authorities, write outside the
  parent grant, merge, deploy, change strategic state, or arm itself.
- The cycle validates the plan against the parent and `coo_cycle_policy`, then
  instantiates it. It never parses free-form prose or `next_actions` into
  executable Jobs without a schema-valid plan contract.
- Deterministic Phase 1F-C tests may complete the planning Job with a fixture
  `mastermind.execution_plan/v1` result. Fixture completion proves the state
  machine, not the live Fable route.
- The inert core implementation may merge before the live planner binding exists,
  but it must report `LIVE_PLANNER_NOT_ACCEPTED` and refuse a live-acceptance claim.
  A separate reviewed planner-routing change is allowed; silently changing the
  meaning of `frontier.orchestrator` is not.

No new seat registry follows from this. The Fable/COO principal binding is an
execution-routing and receipt contract, not an organizational authority map.

### 3.1 Strict CEO-intent version boundary

The committed `mastermind.ceo_intent.v1` contract remains byte-semantically
unchanged. Its required/optional keys, validation, canonical fingerprint, receipt,
and existing Job creation behavior may not be retrofitted. Every v1-created Job
has `orchestration_role=NULL`, is legacy, and is cycle-ineligible.

Phase 1F-C adds a separate strict `mastermind.ceo_intent.v2` discriminator. Its
top-level required keys are exactly the v1 required keys plus `intent_kind` and
`business_impact`; `workstream` remains the sole optional top-level key. All
existing nested v1 grounding and execution-contract key fences remain closed.
Its `schema` field is the string constant `mastermind.ceo_intent.v2`. The two new
required fields are:

- `intent_kind`: string constant `executive_coo_cycle`; and
- `business_impact`: one of `routine`, `material`, or `critical`.

Unknown keys or another schema/intent-kind/impact refuse before fingerprinting.
The v2 `execution_contract.requested_authorities` must contain `READ`; its
`attempt_limit` is required, integer, and `1..2`. Its optional ordered
`validation_commands` is still validated by the existing argv fence and becomes
the mandatory root validation set under R1. Validation of the strict v2 object,
its canonical fingerprint, the stored receipt, and `JOB_CREATED` provenance must
all bind the same exact input bytes/digest. In the same transaction as intent
deduplication and Job creation, v2 creates a root Job with
`orchestration_role=aggregation`, the exact submitted `business_impact`, and
paired immutable cycle provenance JSON/digest.
There is no post-creation role patch and no path by which v1 or a generic Job
becomes eligible.

### 3.2 Normative closed orchestration-result wire appendix

Legacy Jobs (`orchestration_role IS NULL`) keep the committed
`mastermind.executive_worker_result/v1` schema and behavior unchanged. Every
orchestration Job uses the new, closed
`mastermind.executive_orchestration_result/v1` envelope. There is no heuristic
upgrade between the two.

All schemas in this appendix use JSON Schema 2020-12, list every property in
`required`, and set `additionalProperties:false` on the envelope, every role
body, and every nested object. `id` means a non-empty UTF-8 string of at most 128
characters using the runtime's canonical identifier grammar; `digest` means
exactly 64 lowercase hexadecimal SHA-256 characters; `text` means a UTF-8 string
of at most 8,192 characters; and `path` means a non-empty canonical path of at
most 1,024 characters accepted by the existing reviewed path fence. Unless a
smaller limit is stated, ordered string/digest/object arrays contain at most 64
items and no duplicate item. JSON numbers in these bodies are integers only. In
the role definitions below, every field whose name ends in `_id` has type `id`,
every field whose name ends in `_digest` and `policy_sha` has type `digest`, and
every stated equality is an additional constant/relational constraint.

The exact envelope fields are:

| Field | Required type and value |
|---|---|
| `schema_version` | string constant `mastermind.executive_orchestration_result/v1` |
| `job_id` | `id`, constant equal to the persisted Job ID |
| `run_id` | `id`, constant equal to the active Attempt ID |
| `worker_id` | `id`, constant equal to the Attempt placement snapshot worker ID |
| `role` | exactly the persisted role: `plan`, `work`, `review`, `repair`, or `aggregation` |
| `status` | string constant `COMPLETED`; worker/process failure uses the fenced failure API and is never accepted as a completed result |
| `role_result` | exactly one closed role body selected by `role`; no union fallback |
| `summary` | advisory `text` |
| `current_state` | advisory `text` |
| `next_actions` | ordered array of at most 16 advisory `text` items |
| `errors` | ordered array of at most 16 advisory `text` items |
| `validations` | exact empty array `[]` |

The worker never authors a validation receipt, effective-grant receipt,
placement/principal receipt, or claim about passing a supervisor validation.
`validations=[]` preserves that author boundary. `summary`, `current_state`,
`next_actions`, and `errors` are never executable. In particular,
`next_actions` is not a plan, command, path, Job specification, repair
instruction, or cycle input.

The role bodies have exactly these fields and nested shapes:

**`plan` — `mastermind.execution_plan/v1`.** Required fields are
`schema_version` (that constant), `root_job_id` (`id` equal to the parent root),
`plan_attempt_id` (`id` equal to outer `run_id`), and `steps` (ordered array of
1..8 step objects). Each step contains exactly:

| Step field | Type/rule |
|---|---|
| `ordinal` | integer `0..7`, equal to its zero-based array position |
| `step_id` | `id`, unique within the plan |
| `objective` | non-empty `text` |
| `business_impact` | `routine`, `material`, or `critical` |
| `review_required` | boolean planner request; runtime derives the mandatory value under R2 |
| `requested_authorities` | ordered unique array of 1..16 canonical authority strings, subset of root |
| `allowed_write_paths` | ordered unique array of 0..32 canonical `path` values, subset of root |
| `validation_ids` | ordered unique digest array; exact root-derived list when the step requests `RUN_TESTS`, otherwise `[]` |
| `attempt_limit` | integer `1..2`, no greater than root |
| `cost_class` | exactly `default` or `small` |

The planning Job itself has effective authority `READ`, empty writes, and empty
validation argv; the step fields are proposals, not the planner's execution
grant. `validation_ids` are derived as
`sha256(canonical_json(root_validation_argv))`; all root validations are mandatory,
so a RUN_TESTS step cannot select a subset. The worker does not self-author
`plan_digest`; the supervisor-derived digest of the complete raw canonical plan
role body is the authoritative `plan_digest` used by admission and descendants.

**`work` — `mastermind.work_result/v1`.** Required fields are
`schema_version` (that constant), `root_job_id`, `plan_attempt_id`, `plan_digest`,
`plan_step_id`, `repair_round` (integer constant `0`), `artifacts` (ordered array
of 0..64 closed objects containing exactly `path` and `digest`), and
`evidence_digests` (ordered unique digest array). Every lineage value must equal
the Job and admitted-plan event.

**`review` — `mastermind.review_result/v1`.** Required fields are
`schema_version` (that constant), `root_job_id`, `plan_attempt_id`, `plan_digest`,
`plan_step_id`, `reviewed_job_id`, `reviewed_attempt_id`,
`reviewed_result_digest`, `repair_round` (integer `0..2`), `verdict` (exactly
`approve` or `reject`), `evidence_digests` (ordered unique digest array), and
`findings` (ordered array of 0..64 closed objects containing exactly `code`
(`id`), `severity` (`info`, `warning`, or `blocking`), `message` (`text`), and
`evidence_digests` (ordered unique digest array)). The reviewed IDs/digest/round
must equal the exact current revision. `approve` requires zero `blocking`
findings and an empty outer `errors` array; `reject` requires at least one
`blocking` finding. A worker-provided principal identity or validation receipt is
an unknown field and refuses.

**`repair` — `mastermind.repair_result/v1`.** Required fields are
`schema_version` (that constant), `root_job_id`, `plan_attempt_id`, `plan_digest`,
`plan_step_id`, `repair_round` (integer `1..2`), `supersedes_job_id`,
`rejected_review_job_id`, `rejected_review_result_digest`, `artifacts` (the same
closed 0..64 `path`/`digest` array as work), and `evidence_digests` (ordered unique
digest array). All predecessor and round values must equal persisted current
lineage.

**`aggregation` — `mastermind.aggregation_result/v1`.** Required fields are
`schema_version` (that constant), `root_job_id` (equal outer `job_id`),
`handoff_digest`, `policy_sha`, `plan_attempt_id`, `plan_digest`, `revisions`
(ordered 1..8 array), `aggregate_summary` (`text`), and `evidence_digests`
(ordered unique digest array). Each revision object contains exactly `ordinal`,
`plan_step_id`, `current_job_id`, `current_attempt_id`, `current_result_digest`,
`repair_round`, `review_required` (boolean), and nullable
`qualifying_review_job_id`, `qualifying_review_attempt_id`, and
`qualifying_review_result_digest`. The three review fields are all null iff
review is not required and all non-null iff it is required. The ordered revision
set and every non-null approval must equal the immutable current handoff; no
worker-selected omission or substitution is valid.

Canonical bytes for every role body and persisted envelope are UTF-8 JSON with
sorted keys, compact separators `(',', ':')`, `ensure_ascii=false`, and rejected
NaN/Infinity. A content digest is lowercase SHA-256 over those canonical bytes;
when an owning object has a digest field, that field is excluded from its own
digest input. The complete canonical envelope is additionally bounded to at most
`8_388_608` UTF-8 bytes. That byte ceiling is part of the closed schema, applies
after every field/array/character constraint above, and is the one transport,
validator, and persistence ceiling; no adapter-local 4,000-character truncation
or smaller implicit limit is permitted. Executable boundary tests must prove that
the largest accepted bodies remain within this ceiling and that an otherwise
well-shaped envelope above it refuses before provider-result persistence.

The supervisor derives and persists the full raw `role_result`, its
raw canonical digest, its own verified artifact and validation receipts, the
Attempt effective-grant digest, and execution-principal-snapshot digest. It never
generic-flattens the result into `JobPayload` or trusts worker-authored receipts.
The Runtime terminal transaction independently repeats the envelope/body,
identity, role, lineage, effective-grant, supervisor-receipt, and (for
aggregation) current-handoff predicates; a direct caller cannot bypass them with
a generic `JobPayload`.

`control_plane/executive_supervisor.py` must own executable schema constructors
for this exact appendix. Golden tests freeze the canonical schema digests and
round-trip all five bodies without field loss; the implementation PR records the
five golden schema digests. Schema mismatch, wrong role/Job/Attempt/worker,
lineage drift, unknown field, unverified artifact, missing supervisor receipt, or
dropped verdict/plan field refuses before `complete_job`.

### 3.3 Immutable revision lineage

The Job schema persists immutable lineage metadata:

- `orchestration_role`;
- `plan_attempt_id` and `plan_digest`;
- `plan_step_id` for every logical work/review/repair lineage;
- `repair_round` (`0` for initial work, then `1..2` for repairs);
- `supersedes_job_id` for a repair revision, otherwise null; and
- cycle provenance containing the exact parent/root and deterministic creation
  `command_id`.

The runtime validates role-specific nullability and makes every populated value
write-once. The root is born with role `aggregation` and root/cycle provenance;
its later plan binding lives in the immutable aggregation handoff rather than by
mutating the root. The planning Job is born with role `plan` and creation
provenance; its completing Attempt ID and plan digest become the source values for
all children. Every work/review/repair Job is created only after the plan completes
and therefore must carry non-null `plan_attempt_id`, `plan_digest`, and
`plan_step_id`. Initial work has round `0`; repair has a positive round and
non-null supersession pointer; review carries the exact reviewed revision through
`reviews_job_id` and matching plan/step provenance. Branching, cycles, cross-root
references, skipped rounds, role mutation, post-creation lineage mutation, or
plan-digest drift are refused.

An eligible Phase 1F-C root is created only through the strict v2 CEO-intent boundary,
which must persist `orchestration_role=aggregation` and immutable cycle/root
provenance in the same transaction as the intent-derived Job. The cycle refuses
an arbitrary pre-existing root, a generic queued Job retrofitted with actor text,
or a root missing that provenance. No role or provenance may be patched onto a Job
after creation.

Aggregation derives one current revision per plan step: the unique revision not
superseded by another valid revision. Only approvals of that current revision
count. A later approval of a rejected or superseded old revision is stale and can
never satisfy the step, release reserved capacity, or waive the repair.

---

## 4. Fresh aggregation Attempt — OHF/source-law reconciliation

### 4.1 Withdrawal and binding law

The prior attemptless-container proposal is withdrawn in full. There is no
attemptless terminal transition, no container-completion mode, and no synthetic
container-completed event. Current `complete_job` / `fail_job` remain ordinary
leased worker-Attempt APIs without a skip-lease flag, nullable token, magic
worker, or COO bypass.

The OHF constitution is binding: after the bounded planning leader is released,
Phase 1F aggregation is a `NEW_ATTEMPT`. This is a real execution placement that
consumes the root Job's ordinary Attempt budget. It is not a worker claim made for
deterministic bookkeeping. The aggregation worker actually reads the frozen
provider-neutral handoff, produces the typed aggregation result, and is fenced by
the accepted supervisor like any other worker.

### 4.2 Immutable provider-neutral aggregation handoff

When all logical work has a valid current revision and every review-required
current revision has an independent `approve`, one cycle invocation constructs
exactly one immutable `mastermind.aggregation_handoff/v1` and appends one
`COO_AGGREGATION_HANDOFF_READY` event. The handoff/event contains:

- exact root Job ID, policy hash, plan Attempt ID/digest, and reservation digest;
- ordered plan-step IDs and their current unsuperseded work/repair Job, Attempt,
  raw role-result, effective-grant, artifact-receipt, validation-receipt, placement,
  and principal-snapshot digests;
- exact qualifying review Job/Attempt/result IDs and immutable execution-principal
  snapshot and effective-grant digests;
- every rejected, superseded, void, or failed revision/review needed to prove why
  it does not count;
- aggregate result schema version and allowed evidence reads; and
- the deterministic `coo-cycle:<root>:aggregation-handoff:<ordinal>` command ID
  and complete handoff digest.

The handoff contains no provider-native handle, prompt transcript, credential,
mutable Worker-row lookup, or asserted success. It is created and evented in one
transaction. Identical command replay returns the same event and digest; any
command/root/content collision raises `StateConflict`. Creating the handoff does
not claim, run, complete, or fail the root.

### 4.3 Exact-root supervisor execution

A later cycle invocation performs exactly one dispatch transition: it passes the
exact queued root Job ID, whose immutable role is `aggregation`, to the accepted
supervisor. The supervisor must:

1. claim that exact root as a fresh aggregation Attempt through the ordinary
   runtime lease/fence path while atomically persisting/binding its exact effective
   grant (`READ`, empty writes, empty validations) and placement snapshot;
2. launch a real worker with only the immutable provider-neutral handoff and
   read-shaped evidence access needed to aggregate, then satisfy the derived
   active-work admission gate in §4.4 from an accepted launch attestation. A sealed
   worker may satisfy it before or with `RUNNING`. For an OHF operator-harness
   Attempt, frozen P1B order is binding: TX-3 may set `RUNNING` while the principal
   pair is still null; only the later TX-4 `ALLOW` decision may atomically seal the
   pair and satisfy active-work admission before the first meaningful turn;
3. require `mastermind.aggregation_result/v1` tied byte-for-byte to the handoff
   digest and current lineage. An OHF worker schema-seals that exact admitted
   generation's raw result before shutdown, then satisfies the frozen P1B no-
   current/no-writer proof and §4.4 terminal-evidence qualification; a sealed
   worker uses its existing immutable supervisor collection/result receipt and
   process-death proof under the equivalent §4.4 gates;
4. run the role-specific validation against the sealed result and re-read the
   runtime aggregation conditions; and
5. invoke ordinary `complete_job(root, typed_payload)` only after
   `_assert_parent_aggregation_allowed` or its reviewed successor passes inside
   the terminal transaction.

That ordinary terminal path completes the Attempt, root Job, worker quota, and
`JOB_COMPLETED` event truthfully. A failed worker uses the ordinary fenced failure
path. No cycle code writes a terminal root, impersonates a worker, or supplies a
fake result.

The runtime refusal must additionally require: no living child; every plan step
has exactly one current unsuperseded completed revision; every required current
revision has a qualifying approval; the typed aggregate names exactly those
revisions; the plan/reservation/policy/handoff digests still match; and every
non-review current revision is completed. Old approvals, partial repairs, stale
handoffs, or caller-asserted summaries cannot pass.

### 4.4 Schema coordination

OHF P1B owns schema version `3` at exact baseline
`4f672b8f6b950010534390001f4a17ed232e0390`. Inspection of that baseline proves
that its Job and Attempt rows cannot carry this commission's immutable lineage,
effective grant, placement/execution-principal identity, generation-bound work
admission, and terminal result qualification. Phase 1F-C therefore **must set
`SCHEMA_VERSION = 4`** and perform exactly the additive migration below.
It may not claim v3, reuse an OHF column, or defer these fields to untyped event
payloads.

The v4 `jobs` table adds exactly these columns, all SQL-nullable solely so v1-v3
rows remain byte-semantically legacy:

```text
orchestration_role TEXT
orchestration_provenance_json TEXT
orchestration_provenance_digest TEXT
plan_attempt_id TEXT REFERENCES attempts(attempt_id) ON DELETE RESTRICT
plan_digest TEXT
plan_step_id TEXT
repair_round INTEGER
supersedes_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT
```

The runtime, triggers, and row decoder enforce these role rules:

- `orchestration_role IS NULL` means legacy/cycle-ineligible and requires all
  seven other new Job columns null. No v1-v3 row is backfilled, reclassified, or
  made cycle-eligible.
- Any non-null role is one of `plan|work|review|repair|aggregation` and requires
  non-null, canonical, digest-matching
  `orchestration_provenance_json`/`orchestration_provenance_digest` at insertion;
  the pair and role are write-once.
- `aggregation` root and `plan` child require the four plan/repair lineage fields
  `plan_attempt_id`, `plan_digest`, `plan_step_id`, and `repair_round` null and
  require `supersedes_job_id` null. The root's admitted plan is bound by the
  immutable admission/handoff events, never a later Job-row update.
- `work` requires non-null plan Attempt/digest/step, `repair_round=0`, and null
  `supersedes_job_id`; `review` requires matching non-null plan Attempt/digest/step
  and `repair_round=0..2`, null `supersedes_job_id`, and the committed non-null
  `reviews_job_id`; `repair` requires matching non-null plan Attempt/digest/step,
  `repair_round=1..2`, and non-null same-root predecessor
  `supersedes_job_id`.
- Cross-root references, a superseded predecessor that is not the immediately
  current revision, skipped/duplicate rounds, partial provenance pairs, mutation,
  or role-nullability drift aborts the transaction.

V4 also creates database uniqueness fences, with Runtime checks supplying the
cross-row semantic proof: at most one role=`plan` child per root; one
`work|repair` revision per `(root, plan_digest, plan_step_id, repair_round)`; one
repair per non-null `supersedes_job_id`; one `COO_PLAN_ADMITTED` event per root;
one `COO_AGGREGATION_HANDOFF_READY` event per root; one
`ORCHESTRATION_WORK_ADMITTED` event per OHF process generation; and one
`ORCHESTRATION_ROLE_RESULT_SEALED` event per OHF orchestration Attempt. The root-
event indexes use
the event row's root `job_id`, the admission index uses its exact
`aggregate_type='process_generation'`/`aggregate_id`, and the result-seal index
uses the Event row's non-null `attempt_id`; none trusts an unindexed prose field.
Command ID remains globally unique. Replacement reviews
intentionally remain separate Job records and are limited transactionally to two
per exact current revision.

The v4 `attempts` table adds exactly these paired columns:

```text
effective_grant_json TEXT
effective_grant_digest TEXT
placement_snapshot_json TEXT
placement_snapshot_digest TEXT
execution_principal_snapshot_json TEXT
execution_principal_snapshot_digest TEXT
```

Each JSON/digest pair is both-null or both-non-null, canonical/digest-matching,
and write-once once populated. A legacy Attempt for a role-null Job leaves all six
columns null. Before an orchestration Attempt may append `JOB_CLAIMED`, its
effective-grant and placement pairs must be non-null. `RUNNING` is a process/
provider-session lifecycle state, not Phase 1F-C work authority.

The execution-principal snapshot is the stable, Attempt-level identity object
`mastermind.execution_principal_snapshot/v1`. It contains exactly
`schema_version`, `attempt_id`, `worker_id`, `quota_class`, `provider`,
`account_label`, `placement_snapshot_digest`, `os_principal_name`,
`os_principal_uid`, and `provider_home_identity`. `provider_home_identity` is the
closed secret-free object with exactly `path`, `device`, `inode`, `uid`, `gid`,
and `mode` under the same types and `0700` constraint frozen below.
`os_principal_name` is a non-empty canonical host-account string and
`os_principal_uid` is a non-negative integer. The
snapshot does **not** contain a process generation, provider-session handle,
TX-3 command, observed-attestation digest, or attestation time: those facts vary
across a lawful same-Attempt OHF recovery and are bound per generation by the
admission event below. Provider/account/worker/quota come only from the immutable
placement pair. No constructor assertion, mutable Worker-row reread, worker
result, prompt, or provider-native prose is an identity source.

The typed supervisor-authored input for an OHF launch is the new closed,
secret-free `mastermind.operator_principal_observation/v1` object. It contains
exactly `schema_version`, `attempt_id`, `worker_id`, `process_generation_id`,
`provider_session_id`, `process_identity`, `os_principal_name`,
`os_principal_uid`, `provider_home_identity`, and `observed_at_ms` (a non-negative
integer Unix-epoch millisecond timestamp).
`process_identity` contains exactly non-null `pid` (positive integer), `pgid`
(positive integer), `process_start_identity` (non-empty string), and `boot_id`
(non-empty string). `provider_home_identity` contains exactly `path` (canonical
absolute string), `device`, `inode`, `uid`, `gid`, and `mode` (non-negative
integers, with mode exactly decimal `448`, i.e. Python octal `0o700`).

Immediately before TX-4, the accepted Codex adapter exposes two typed read-only
observations for the exact launched PID: (a) an OS process-credential observation
whose PID/start/boot identity must equal the TX-3-bound
`ProcessIdentityObservation` and whose numeric effective UID resolves through
the host account database (`pwd.getpwuid(uid).pw_name`) to the same non-empty
canonical OS-principal name; and (b) a fresh
symlink-safe `lstat` identity of the explicit dedicated `CODEX_HOME`. The
`OperatorHarnessOrchestrator`, acting as supervisor, joins those facts to the
Executive-issued Attempt/worker/generation and TX-3-bound provider session,
authors the closed principal observation, and passes it to the Runtime port. The
provider-home owner UID must equal the observed process UID. `account_label` is
deliberately absent and is joined only inside the Runtime transaction from the
immutable placement snapshot. `ObservedHarnessAttestation` remains byte- and
interface-semantically frozen; it is not widened or relabeled as OS-principal or
provider-home evidence.

Schema v4 commissions one narrow additive seam across
`CodexOperatorAdapter`/`OperatorHarnessOrchestrator.RuntimePort`/
`ExecutiveOperatorHarnessPort`/`OperatorHarnessRegistry.seal_attestation`: the
orchestrator passes the typed principal observation alongside the unchanged
`ObservedHarnessAttestation`; the Executive port and Runtime, not the adapter or
caller, independently derive `compare_launch`. For an orchestration Attempt, the
single existing TX-4 `BEGIN IMMEDIATE` transaction must revalidate the exact
leased Attempt, fence, orchestration role, effective-grant and placement pairs,
current epoch/generation/writer, TX-3 applied receipt, provider session/process
identity, requested profile, unchanged attestation digest, and the typed
principal observation. When the derived decision is `REFUSE`, the unchanged
ordinary TX-4 attestation and `OHF_LAUNCH_DECISION(REFUSE)` evidence commits and
principal/admission remains absent. When the derived decision is exactly
`ALLOW`, that same transaction must validate the complete principal observation,
seal the null execution-principal pair—or require an already sealed pair to match
on recovery—and append the ordinary `OHF_LAUNCH_DECISION(ALLOW)` plus one
`ORCHESTRATION_WORK_ADMITTED` Event. An `ALLOW` with missing, forged, or
mismatched principal facts rolls back the entire TX-4 transaction, including the
ordinary attestation/decision; an orchestration generation can never expose a
durable `ALLOW` without its matching admission. Thus the `ALLOW` path commits all
TX-4 attestation, decision, principal, and admission evidence or writes none.

`ORCHESTRATION_WORK_ADMITTED` is the closed
`mastermind.orchestration_work_admission/v1` payload with exactly
`schema_version`, `job_id`, `attempt_id`, `worker_id`, `quota_class`,
`orchestration_role`, `process_generation_id`, `provider_session_id`,
`tx3_applied_command_id`, `observed_attestation_digest`,
`principal_observation`, `principal_observation_digest`,
`execution_principal_snapshot_digest`,
`placement_snapshot_digest`, `effective_grant_digest`, `policy_sha`, and
`launch_decision`. `principal_observation` uses the canonical JSON law in §3.2
and must match `principal_observation_digest`; `launch_decision` is exactly
`ALLOW`. The Event actor is `supervisor`, its aggregate is the exact process
generation, and its deterministic command ID is
`ohf-work-admit:<process_generation_id>`. A partial unique index permits at most
one such Event per generation. Identical replay returns/reconciles the same
Event. Any different target, generation, session, principal, placement, grant,
policy, or attestation conflicts. Non-orchestration P1B event payloads and TX
semantics remain unchanged.

A same-generation replay first reconciles the durable TX-4/admission Events and
reuses their persisted raw principal observation; it does not call the provider,
reread a new wall-clock time, or author a replacement observation. Only a new
process generation may author a fresh observation/time, and it must prove the
same stable Attempt-level principal identity.

The derived **active-work admission** predicate is mode-specific and true only
when the Attempt's immutable principal pair is complete. For `SEALED_WORKER`, the
complete accepted `mastermind.executive_launch_attestation/v1`, durable Attempt
process identity, placement digest, principal digest, effective-grant digest,
and policy SHA must agree. For `OPERATOR_HARNESS`, an active-work operation must
name the exact current Executive-writer process generation. Its epoch must be
`CURRENT`, the generation must be unended and the greatest allocated
`(epoch_number,generation_number)` tuple for the Attempt, and it must have both an
`OHF_LAUNCH_DECISION(ALLOW)` and `ORCHESTRATION_WORK_ADMITTED` Event whose exact
generation, attestation digest, `principal_observation_digest`,
`execution_principal_snapshot_digest`, placement digest, grant digest, and policy
SHA agree. This predicate is recomputed from immutable evidence; it is not a
mutable boolean, new status, new table, or seventh Attempt column. A successor
generation never inherits its predecessor's decision/admission; TX-10/TX-11
recovery must repeat TX-4, prove the same stable principal snapshot, and append a
fresh current-generation admission before work.

For `SEALED_WORKER`, the accepted-launch transaction may seal the equivalent
stable principal pair and satisfy active-work admission before or atomically with
the existing transition to `RUNNING`, using the supervisor's complete typed
launch attestation as its source. For `OPERATOR_HARNESS`, P1B TX-3/TX-4 semantics
are preserved exactly: TX-3 `bind_start_result` sets the Attempt `RUNNING`;
between TX-3 and TX-4 the principal pair may remain null and active-work
admission is false; TX-4 owns the atomic comparison/principal/admission boundary
above. `REFUSE`,
comparison error, effect-unknown, a missing/mismatched generation, forged or
mismatched principal facts, or a null/mismatched pair never creates the admission
Event and permits cleanup/fenced adverse termination only.

No orchestration Attempt may reserve or begin an OHF turn, checkpoint, collect or
publish provider output, or seal an accepted completed role result unless the
operation names and revalidates the exact active-work-admitted generation in the
same fenced transaction. Active-work admission is necessary but not sufficient:
the direct turn-reservation, turn-acknowledgement, checkpoint, collection, and
publication boundaries must also prove that no
`ORCHESTRATION_ROLE_RESULT_SEALED` Event exists for the Attempt. `RUNNING` alone
is never sufficient.

The direct TX-2 `reserve_start` transaction enforces
`MAX_ORCHESTRATION_EPOCHS_PER_ATTEMPT=1` before a dispatch marker, process launch,
or provider call. With no epoch it may allocate E1/G1. The same OperationId may
reconcile that exact still-replayable E1/G1 under the frozen P1B pre-dispatch law
without another epoch or duplicate provider call. Once any epoch row exists, a
different TX-2 OperationId or any E2/replacement-epoch allocation for the
orchestration Attempt refuses, regardless of whether E1 reached TX-3, TX-4, or
TX-5. An abandoned, poisoned, failed, or unrecoverable E1 therefore terminates the
Attempt adversely; another session start requires a fresh governed Attempt. This
additive refusal is orchestration-qualified, so ordinary P1B replacement-epoch
behavior remains unchanged.

The direct TX-5 `reserve_turn` transaction enforces both provider-turn constants
above before it writes a dispatch marker or permits an adapter call. It counts
distinct durable BEGIN_TURN INTENT command IDs across the Attempt and within the
named generation. An identical OperationId may return only its exact existing
`TurnRef` under the P1B proven-pre-dispatch replay rule; APPLIED, EFFECT_UNKNOWN,
or a changed target never replays. Any different second OperationId for the same
generation refuses, including concurrent reservations. A first G1 turn may be
followed by one G2 turn only from the derived **G1 pre-candidate process-loss**
state. That state requires all of these durable facts simultaneously: the sole G1
TX-5 has exact matching INTENT and APPLIED receipts; it has no EFFECT_UNKNOWN
receipt; no checkpoint or `OHF_CANDIDATE_RESULT_RECORDED`, raw-result seal, or
competing result Event exists anywhere on the Attempt; G1 is proven dead and its
provider writer state is `RELEASED`; its epoch remains the same bound `CURRENT`
epoch; and ordinary P1B `resume_safe` independently permits TX-10. Only then may
lawful TX-10/TX-11 create/bind G2 on that same epoch, after which G2 must provide
fresh process identity, fresh TX-4 ALLOW, and fresh work admission before its one
TX-5. The G2 reservation transaction re-proves the complete predicate and the
absence of another turn; no model prose or supervisor flag can assert it.

A G1 candidate Event—even one whose body is invalid, secret-triggering, or
unsealable—closes this recovery exception and ends the Attempt adversely. So do a
G1 checkpoint, effect-unknown receipt/ambiguity, non-dead process, non-RELEASED
provider writer, abandoned/new epoch, failed TX-10/TX-11, G2 failure, invalid G2
result, or inability to seal. There is no G3 or third-turn path, and TX-2
replacement-epoch allocation already refuses after E1 exists, before work-closed
and whether or not TX-5 occurred. Another provider attempt then requires a fresh
governed Job Attempt and its own ceilings.

Merged P1B `CandidateResult.summary` remains advisory, bounded, redacted evidence;
it is not and cannot be a lossless orchestration result source. Phase 1F-C instead
adds a separate optional, provider-neutral extension protocol in
`control_plane/executive_orchestration_result.py`. The frozen P1B
`OperatorHarnessAdapter`, `CandidateResult`, `NormalizedEvent`, operation list,
and non-orchestration Event payloads do not change. An adapter used for an
orchestration Attempt must also implement exactly one additive operation,
`observe_raw_role_result(turn)`, returning a closed immutable
`mastermind.operator_raw_role_result_observation/v1` value with exactly:

- `schema_version` equal to that constant;
- `attempt_id`, `session_epoch_id`, `process_generation_id`, and `turn_id`, equal
  to the supplied durable `TurnRef`;
- `provider_session_id` and `provider_native_turn_id`, equal to the TX-3 session
  and TX-5 APPLIED receipt for that turn;
- `provider_turn_artifact_digest`, equal to the unchanged P1B
  `CandidateResult.artifact_digest` derived from the complete matching provider
  turn row;
- `canonical_result_json`, the complete, untruncated canonical UTF-8 JSON text of
  one `mastermind.executive_orchestration_result/v1` envelope under §3.2;
- `canonical_result_digest`, SHA-256 of those exact UTF-8 bytes; and
- `canonical_result_byte_length`, the exact integer byte length in
  `1..8_388_608`.

The existing `AppServerClient.request()` cannot source this observation because
it deliberately applies `redact_evidence` in its stdout reader before returning
any JSON-RPC result. Phase 1F-C therefore commissions one narrower transport
primitive in `scripts/ohf/laboratory.py`: `request_raw_turn_page(...)`. It is
hard-wired to `thread/turns/list`, requires an exact thread ID, native turn ID,
`itemsView=full`, page limit `1`, and an optional opaque cursor from its own prior
page; it cannot request account, config, notification, stderr, or another method.
Ordinary `request()`, `wait_notification()`, `drain_notifications()`, malformed-
frame evidence, and every existing P1B call continue to receive only the current
redacted values.

The JSON-RPC reader gains one global
`APP_SERVER_MAX_FRAME_BYTES=67_108_864` limit and reads at most that value plus
one byte before declaring an oversized line, draining/terminating the compromised
transport without retaining, parsing, logging, or echoing the frame, and failing
all pending requests with a constant secret-free error. The 64 MiB ceiling is
the closed transport bound for both ordinary and raw responses; it covers the
8 MiB canonical result, JSON string escaping, duplicate direct-text/content
representations, and bounded turn metadata. A larger provider turn refuses and
cannot complete; no unbounded `for raw in stdout` line allocation is permitted.
Invalid UTF-8 or malformed JSON on a response reserved for the raw-result path
likewise fails that request with a constant error and never enters a redacted
fallback as proposed result bytes.

For only a request ID reserved by `request_raw_turn_page`, the reader routes the
unredacted parsed response into a one-element private queue instead of the
ordinary redacted response/notification collections. The result is wrapped in a
one-shot opaque value whose `repr`/`str` reveal only a constant placeholder and
whose sole consume operation releases the wrapper's reference. It is consumed
immediately inside `observe_raw_role_result`; neither the client, adapter,
exception, notification list, stderr buffer, Event, log, test failure message,
nor receipt retains the raw provider response. The response queue is removed in
a `finally` block. Raw JSON-RPC errors are converted through the existing
redactor and raised without attaching the raw payload. All nonmatching response
IDs and every notification are redacted before routing exactly as in P1B. This is
containment, not a general unredacted request API; code search and tests must show
that the sole production caller is the exact orchestration-result adapter method.

The observation has no timestamp, mutable cursor, redacted alternate, worker
identity claim, completion permission, or executable instruction. Its canonical
observation digest is derived over the complete closed observation. The Codex
implementation retrieves the exact native turn with `itemsView=full`, follows a
closed cursor chain. The exact bounds are
`MAX_RAW_TURN_PAGES=128`,
`MAX_RAW_TURN_CUMULATIVE_FRAME_BYTES=134_217_728`, and
`RAW_TURN_TOTAL_TIMEOUT_SECONDS=120`, measured with one monotonic deadline across
all calls and parsing. Every request uses `sortDirection=desc`, page limit `1`,
and only the immediately returned `nextCursor`; repeated, empty, wrong-type, or
non-advancing cursors, a missing cursor before the target is found, any bound or
deadline exhaustion, zero/multiple matching native turns, partial page content,
missing full item content, or conflicting duplicate representations refuses.
The one-shot raw wrapper reports its exact received frame byte length solely for
this cumulative bound and never exposes frame bytes through `repr` or an error.

The extractor selects exactly one logical final agent message under one of two
closed phase cohorts. Either every agent message has a recognized phase, exactly
one is `final_answer`, and every other is `commentary`; or every agent message is
unphased and there is exactly one message total. A mixed phased/unphased set, an
unknown phase, multiple/no final answers, or multiple unphased messages refuses.
Recognized commentary is ignored, never concatenated into the result. The
selected message must contain either one complete `text` string or one or more
ordered `output_text`/text content blocks; blocks are concatenated in order with
**no inserted delimiter**. If both representations are present, the direct text
must equal the block concatenation byte-for-byte. A turn top-level summary,
notification, tool-call text, reasoning item, or `turn_texts(...)[-1]` is never a
substitute. Multiple text blocks therefore round-trip one JSON document;
non-text result content, invalid UTF-8, a BOM, or any transport ambiguity refuses.
The provider-turn artifact digest is still computed by the
unchanged P1B rule over the complete matching turn row, so the typed observation
and ordinary candidate evidence are cryptographically tied to the same native
turn without changing the candidate schema.

The orchestration-only caller invokes this extension after the ordinary P1B
candidate Event is durably recorded and before TX-6/TX-8 shutdown. The
supervisor-owned result validator uses a duplicate-key-refusing JSON parser,
requires the returned text to equal byte-for-byte its own §3.2 canonicalization,
recomputes byte length and both result/observation digests, validates the complete
closed envelope/body and all persisted Job/Attempt/worker/role/lineage identities,
and applies the reviewed finished-evidence sensitive-content detector to the
complete parsed value. If `redact_evidence` would change any key or value, or
`evidence_contains_secret` is true, collection refuses before persistence; the
system never redacts/sanitizes the value and then calls it lossless. No
`CandidateResult.summary`, `NormalizedEvent`, worker prose, or digest without the
actual complete bytes may populate the role result.

In one fenced Runtime transaction, the supervisor then revalidates the exact
active-work-admitted greatest generation, TX-5 native turn, existing
`OHF_CANDIDATE_RESULT_RECORDED` Event and its complete payload digest, equality of
its candidate artifact digest to `provider_turn_artifact_digest`, and all typed
observation bindings. That transaction also proves the target is the latest
qualifying completed turn and that no later or concurrent TX-5 INTENT/APPLIED,
turn, checkpoint, candidate, or result seal exists for
the Attempt, then atomically appends exactly one immutable
`ORCHESTRATION_ROLE_RESULT_SEALED` Event for the Attempt. Its closed
`mastermind.orchestration_role_result_seal/v1` payload contains exactly
`schema_version`, `job_id`, `attempt_id`, `worker_id`, `quota_class`,
`orchestration_role`, `session_epoch_id`, `process_generation_id`, `turn_id`,
`provider_session_id`, `provider_native_turn_id`,
`provider_turn_artifact_digest`, `raw_result_observation_digest`,
`canonical_result_byte_length`, `candidate_event_command_id`,
`candidate_event_digest`, `result_envelope`, `result_envelope_digest`,
`role_result_digest`, `work_admission_command_id`,
`observed_attestation_digest`, `execution_principal_snapshot_digest`,
`placement_snapshot_digest`, `effective_grant_digest`, and `policy_sha`. The
Event's stored complete `result_envelope` reconstructs exactly the observation's
`canonical_result_json` bytes under §3.2 and its digest equals both
`canonical_result_digest` and `result_envelope_digest`; no outer identity or
advisory field is discarded. The stored `role_result_digest`, including the
authoritative `plan_digest` for a planning body, is derived independently from
the validated inner `role_result`, never substituted with the envelope or
provider-turn digest.

The existence of that unique Event is the derived **work-closed** predicate. It
is recomputed from immutable evidence, not stored as a mutable flag. After it
commits, every direct TX-5 reservation/acknowledgement, checkpoint, provider
collection/publication, second result observation/seal, TX-10/TX-11 successor
generation/resume, TX-2 `reserve_start`/new-epoch allocation, or other meaningful-
work boundary for the Attempt refuses even while its old epoch/generation remains
CURRENT and writer-held. The only additional lease operations permitted are the
existing holder's fenced `heartbeat_attempt`/lease extension and
`takeover_expired_operator_harness` CAS, each with `lease_seconds` or
`extend_seconds` resolved to `1..210` (an omitted argument may use the configured
store duration only when that resolved value is within the same bound), solely to
preserve authority long enough to run
cleanup/reconciliation/validation/terminalization. Heartbeat/takeover never
reopens TX-2, TX-5, checkpoint, candidate/raw-result collection, TX-10/TX-11, or
any work authority. Otherwise only TX-6/TX-7/TX-8 stop/cancel/reconcile cleanup,
fenced adverse termination, post-shutdown supervisor validation, and terminal-
evidence/terminal transitions remain legal. The seal and TX-5 paths serialize
through the same SQLite write boundary: if a later TX-5 INTENT/APPLIED wins first,
sealing the earlier result refuses; if the seal wins first, TX-5 refuses before
any provider call. A sealed G1 cannot start or resume G2 or allocate a new epoch;
allocation of G2/a later epoch before the G1 seal instead makes G1 stale and unable
to seal, with no fallback.

The deterministic command ID is `orchestration-result-seal:<attempt_id>`; a
partial unique index permits one per Attempt. Recovery is Event-first. If that
command already exists, the Runtime validates its complete stored Event/payload,
Attempt/turn/generation, candidate/admission/principal/grant/policy, envelope and
all digests and returns the identical receipt with **zero provider call**; a
competing existing seal conflicts. Only when the candidate Event exists and the
seal is absent after a pre-seal crash may the caller re-read the same completed
native turn and recompute the observation. A raw read begun before another caller
commits the seal may finish in memory, but its following transaction must return
the already identical Event or conflict and must persist nothing new. Any changed
bytes, competing envelope, redaction-triggering value, wrong Attempt/epoch/
generation/turn/session/native-turn, stale or successor generation, missing
candidate bytes, artifact/observation/result digest mismatch, or different seal
conflicts. If the provider cannot reproduce the exact complete turn in the
seal-absent pre-seal window, the Attempt fails closed; a digest is never treated
as recoverable content.

This pre-shutdown schema validation proves only the closed result wire and source
binding. It is not the role's filesystem/artifact/test validation command; those
supervisor-authored validations run against the sealed immutable result after
provider shutdown and bind their receipts to the result-seal command/digest.

After that seal, P1B shutdown may end the generation, release its writer, and
abandon/terminate its epoch. The historical admission then becomes **terminal
evidence only**; it never authorizes another turn, checkpoint, collection, or
work. The derived **terminal-evidence qualification** predicate requires: the
ordinary P1B terminal proof that no epoch is `CURRENT` and no generation holds
Executive writer authority; the exact immutable role-result seal and its
matching admission/principal/placement/grant/attestation/policy evidence; all
required supervisor-authored validation/artifact receipts bound to that result
seal; and proof that no later epoch, generation, turn, candidate, or competing
result exists. The sealed generation need not remain current after lawful
shutdown, but it must remain the greatest tuple ever allocated for the Attempt.
If G2 or any later epoch/generation exists, G1 can never be substituted even when
the later generation refused launch or failed; the Attempt must terminate
adversely and follow the governed requeue path.

For `OPERATOR_HARNESS`, validation after provider shutdown, review qualification,
aggregation-handoff construction, aggregation evidence, and ordinary terminal
completion each independently require terminal-evidence qualification in their
own fenced/read-consistent transaction. For `SEALED_WORKER`, the existing
immutable supervisor collection/result receipt and proven-dead durable process
identity replace the OHF generation/result-seal Events, but the same closed role-
result, stable principal, placement, grant, validation, no-live-process, and
no-competing-result facts are mandatory. An Attempt that fails, is lost, is rate-
limited, or is cancelled before accepted launch/result evidence may terminate
without the principal or result evidence, but cannot supply a completed role
result, review authority, aggregation evidence, or live acceptance. Historical
or unattested rows never qualify. A crash before/after TX-3, TX-4, result seal,
TX-6, TX-8, sealed-worker collection, validation, or terminal commit replays from
the exact immutable boundary and cannot duplicate evidence or bypass either
mode's predicate.

The immutable placement snapshot is sealed transactionally at claim and contains
exactly the selected `worker_id`, `quota_class`, `provider`, canonical non-empty
`account_label`, and snapshot time. To make that snapshot lawful rather than a
copy of mutable identity, v4 adds database immutability triggers that reject any
change to `workers.provider`, `workers.account_label`, or
`worker_quota_classes.provider` after insertion. New/eligible worker registrations
require canonical non-empty values: provider is unchanged by `strip().lower()`
and matches `^[a-z0-9][a-z0-9._-]{0,63}$`; account label is unchanged by
`strip().lower()` and matches `^[a-z0-9][a-z0-9._@+:-]{0,127}$`. Each selected
worker's provider must equal the selected quota class's provider at registration
and claim. Historical rows missing these values are not backfilled and are
orchestration-ineligible. The execution-principal snapshot references the exact
placement digest and must equal its provider/account/worker/quota facts. It is
sealed only at the mode-specific accepted-launch boundary above; per-generation
admission binds launch-attestation and process/session identity separately, and
OHF TX-3 `RUNNING` never self-attests or substitutes for TX-4.

The Attempt effective grant is canonical
`mastermind.executive_effective_grant/v1` with exactly
`schema_version`, ordered unique `authorities`, ordered unique `write_paths`,
ordered `validation_argv` (an array of argv arrays), `policy_sha`, `job_id`, and
`role`. It uses the exact UTF-8/sorted-key/compact/no-NaN canonical encoding in
§3.2. At claim it is derived from reviewed policy and persisted atomically as a
strict subset of or equality with the immutable Job grant. It cannot be broadened
after placement. `plan` has exactly `READ`, empty writes, and empty validations;
`aggregation` has exactly `READ`, empty writes, and empty validations. A
work/repair/review Attempt carrying `RUN_TESTS` has the exact ordered root
validation argv; one without it has none. Review always has empty writes.

`JOB_CLAIMED`, the supervisor packet and selected executable role schema/spec,
launch metadata, launch attestation, checkpoints, supervisor-authored validation
and artifact receipts, and the terminal transaction must all bind the same
effective-grant digest. The supervisor consumes the Attempt's effective grant,
never the broader root/Job grant. The pre-v4 `authority_policy_hash` remains
required historical policy evidence but is not an effective-grant digest and
cannot substitute for one.

`COO_PLAN_ADMITTED` reservation and `COO_AGGREGATION_HANDOFF_READY` remain
immutable, content-addressed events. No reservation or handoff table, mutable
counter, or Job-row cache is authorized.

#### Mandatory offline v3→v4 upgrade gate

Appending `_MIGRATION_4` to the ordinary `RuntimeStore` migration loop is
forbidden. Under v4 code, a normal writable open may create the complete v4
schema only when the authoritative database path does not exist. It may open an
existing exact-v4 store only when no upgrade barrier is present. Every writable
entry, including the current `create=True` and `existing_writable=True` paths,
must first perform this mutation-free inspection. A normal open of any existing
v1-v3 database must raise the typed `ExecutiveSchemaUpgradeRequired`; it must not
set WAL mode, create a table, invoke `_migrate`, alter a sidecar, or otherwise
advance the file. Existing v1 or v2 stores must first be advanced to exact v3
under the separately frozen pre-v4 procedure; Phase 1F-C's offline upgrader
accepts exact v3 only.

`executive_backup` becomes explicitly version-aware. Its verifier takes a closed
expected schema version (`3` or `4`) and compares the exact ordered migration
prefix, names, and checksums for that version. Its restore drill copies the
backup and opens the copy read-only/immutable, runs integrity, foreign-key,
migration, normalized-schema, and required-table checks for that exact version,
and never constructs `RuntimeStore(create=True)` or invokes migration code. A v3
drill that returns v4, writes a sidecar, changes the copied database hash, or
contains any v4 column/index/trigger/event fails.

The one content-preservation proof used before, inside, and after migration is
the versioned canonical
`mastermind.executive_legacy_content_projection/v1`. It contains exactly
`schema_version="mastermind.executive_legacy_content_projection/v1"`,
`source_schema_version=3`, `tables`, and
`legacy_migration_vector`. `tables` is an ordered array of exactly eight objects
named, in order, `workers`, `worker_quota_classes`, `jobs`, `attempts`, `events`,
`sqlite_sequence`, `harness_session_epochs`, `process_generations`. Each object
contains exactly `name`, `columns`, `primary_key`, and `rows`; `columns` and
`primary_key` are ordered arrays of strings and `rows` is an ordered array of row
arrays. The literal v3 column vectors are:

- `workers`: `worker_id,provider,account_label,worker_type,identity_status,metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms,version`;
- `worker_quota_classes`: `worker_id,quota_class,status,provider,model,effort,cost_class,capabilities_json,metadata_json,held_attempt_id,fence_counter,last_seen_at_ms,created_at_ms,updated_at_ms,version`;
- `jobs`: `job_id,objective,department,priority,status,assigned_worker_id,assigned_quota_class,current_attempt_id,authority_level,branch,worktree,constraints_json,requested_authorities_json,authority_policy_hash,allowed_write_paths_json,validation_commands_json,checkpoint_json,result_json,attempt_count,attempt_limit,available_at_ms,cancel_requested_at_ms,created_at_ms,updated_at_ms,version,parent_job_id,root_job_id,depth,owner_seat,escalation_target,business_impact,review_required,reviews_job_id`;
- `attempts`: `attempt_id,job_id,attempt_number,worker_id,quota_class,status,fence_generation,authority_policy_hash,lease_token,lease_owner,lease_expires_at_ms,heartbeat_at_ms,checkpoint_sequence,checkpoint_json,result_json,error_json,pid,pgid,process_start_identity,boot_id,provider_session_id,stdout_path,stderr_path,result_path,exit_code,launch_metadata_json,started_at_ms,finished_at_ms,created_at_ms,updated_at_ms,version,execution_mode,requested_execution_profile_json,requested_execution_profile_digest`;
- `events`: `event_id,aggregate_type,aggregate_id,sequence,event_type,command_id,actor,job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms`;
- `sqlite_sequence`: `name,seq`;
- `harness_session_epochs`: `session_epoch_id,attempt_id,worker_id,epoch_number,provider_session_id,state,created_at_ms,ended_at_ms,abandonment_class`; and
- `process_generations`: `process_generation_id,session_epoch_id,worker_id,provider_session_id,generation_number,pid,pgid,process_start_identity,boot_id,started_at_ms,last_observed_at_ms,ended_at_ms,termination_class,exit_code,executive_writer_held,provider_writer_state,observed_attestation_json,observed_attestation_digest,created_at_ms`.

These strings are individual ordered vector items, not one comma-delimited
value. The eight v4 Job columns and six v4 Attempt columns are therefore excluded
after migration. `sqlite_sequence` preserves the `events` AUTOINCREMENT
next-identity state. The literal `primary_key` vectors in the same table order are
`["worker_id"]`, `["worker_id","quota_class"]`, `["job_id"]`,
`["attempt_id"]`, `["event_id"]`, logical-unique `["name"]`,
`["session_epoch_id"]`, and `["process_generation_id"]`. `rows` is ordered by
that complete vector under SQLite BINARY collation with no locale or timestamp
fallback, and a duplicate logical `sqlite_sequence.name` refuses.
`legacy_migration_vector` is an ordered array of row arrays with the frozen
column vector exactly `["version","name","checksum","applied_at_ms"]`. It
contains every exact v1-v3 `schema_migrations` row, ordered by INTEGER `version`
ascending with no duplicate version, excludes only the expected migration-4 row,
and uses the identical tagged SQLite storage-class cell representation defined
below. It is not a map, object array, parsed receipt, or implementation-selected
column order. Every preflight, in-transaction, post-migration, completion,
backup, and drill equality site serializes this one literal representation.

Every projected row is an array in the frozen column order. Every cell preserves
SQLite storage class and value exactly as one of `["null"]`,
`["integer","<base-10 integer>"]`, or `["text","<exact UTF-8 text>"]`; any REAL,
BLOB, invalid UTF-8, missing/extra column, duplicate key, or non-v3 migration
receipt refuses projection. In particular, JSON text, Event payloads/command
identities, OHF facts, paths, timestamps, counters, and nulls are not parsed,
reformatted, canonicalized, redacted, or defaulted. The complete projection uses
the canonical JSON law in §3.2 and its SHA-256 is the **legacy-content digest**.
This closed projection covers every v1-v3 logical row/column/payload and the
legacy AUTOINCREMENT identity while excluding only reviewed v4 schema objects/
columns and migration receipt; row counts, IDs, or parsed-JSON equality cannot
substitute.

The only authorized populated-store transition is an explicit offline
`upgrade_v3_to_v4` command/API. Before it can touch schema, it must:

1. acquire the existing owner-controlled Executive service/restore lock at the
   runtime-state root under the invoking control principal
   (`lock.st_uid == os.geteuid()`) and persist a private, durable
   `executive-schema-upgrade.in-progress.json` barrier that normal writers refuse;
2. prove the Executive service is stopped and an independent process/file-lock
   census finds no runtime, supervisor, harness, backup, or SQLite writer;
3. checkpoint/truncate any quiesced WAL, then verify the authoritative source as
   exact v3 with the v3-aware read-only verifier;
4. take a private v3 backup, verify it as exact v3, and complete the exact-v3
   read-only restore drill; and
5. durably write a closed
   `mastermind.executive_schema_upgrade_preflight/v1` receipt binding the
   canonical database path/device/inode/size/SHA-256, exact v1-v3 migration
   vector, normalized-schema digest, canonical pre-v4 legacy-content digest,
   backup database/manifest hashes, restore-drill receipt/digest, quiesce/writer-
   census digest, tool/source release SHA, and timestamp.

The migration command revalidates every preflight field against the same file
and release, then opens the database without the normal auto-migration path and
executes exactly one `BEGIN EXCLUSIVE` transaction. Inside it, the command
rechecks the v3 migration vector and logical/schema fingerprint, applies only the
reviewed v4 DDL/triggers/indexes, inserts the exact v4 migration receipt, and
recomputes the same closed legacy projection over the v3 columns/rows. Before
commit it must prove foreign-key and SQLite integrity, normalized fresh-v4 schema
parity, absence of an uncommitted writer, and exact digest equality
`post_v4_legacy_content_digest == preflight.pre_v4_legacy_content_digest`. Any
row, ID, JSON/Event payload, command identity, OHF epoch/generation/operation
fact, migration-v1-v3 receipt, or other projected value change rolls back the
transaction even when counts and IDs match. After rollback, an exact-v3 read-only
verification must reproduce the preflight migration vector, normalized-schema
digest, legacy-content digest, and absence of all v4 objects; otherwise the
database is quarantined and no writer may resume. This transaction-plus-exact-
guard design—not a multi-file rename—is the binding meaning of “v3 remains
untouched on migration failure.”

After the v4 commit, the durable in-progress barrier remains. Before removing it,
the same exact release must verify the authoritative database as v4, take and
verify an immediate v4 backup, complete an exact-v4 read-only restore drill, and
durably write
`mastermind.executive_schema_upgrade_completion/v1` binding the preflight
receipt digest, authoritative v4 database/schema/migration digests,
`pre_v4_legacy_content_digest`, `post_v4_legacy_content_digest`, explicit
`legacy_content_equal=true`, v4 backup and drill digests, TX-9 preservation
proof, release SHA, and timestamp. The immediate v4 backup verifier and read-only
restore drill independently recompute the same legacy projection and must equal
both recorded digests. Only then is the barrier removed and normal writers are
eligible to open. A mismatch found after commit leaves the barrier, quarantines
the database, and requires a v4-compatible forward fix. Any other crash or
failure after the v4 commit but before completion likewise leaves schema v4 and
the barrier in place; recovery is disable/unarm plus v4-compatible forward-fix,
never a v3 restore or binary downgrade.

Every existing row, ID, foreign key, index, trigger, JSON payload, event, OHF
epoch/generation/operation record, and version is preserved, including OHF TX-9
restore invalidation semantics. A fresh-v4 database and a populated-v3→v4
database have byte-equivalent normalized schema, indexes, and triggers. Backup/
restore tests prove both paths, the normal-open refusal, exact-version drill, the
transactional v3-untouched failure path, injected legacy-payload mutation with
unchanged IDs/counts, pre/post legacy-content equality, the post-commit writer
barrier/quarantine, and post-v4 forward-fix law.

TX-9 itself remains byte- and behavior-semantically unchanged. It truthfully
abandons every current epoch, clears every Executive writer, marks the active OHF
Attempt and its Job `LOST`, clears the Attempt lease, detaches the invalidated
Attempt from its quota, leaves that quota `ERROR`, and appends
`OHF_RESTORE_INVALIDATED`. Because this exact detached state intentionally cannot
satisfy the ordinary `LOST` requeue predicate that requires the terminal Attempt
still to be held, v4 adds one command-aware **TX-9-detached same-Job requeue**
branch to `requeue_job`. It is available only to a Job with a non-null Phase 1F-C
`orchestration_role` and an exact current `OPERATOR_HARNESS` Attempt, and in one
fenced Runtime transaction it must prove all of the following:

- the Job and its `current_attempt_id` Attempt are both `LOST`, the Attempt is
  terminal with `lease_token IS NULL`, and the Job has remaining same-Job Attempt
  budget;
- exactly one immutable `OHF_RESTORE_INVALIDATED` Event has the frozen command
  ID `ohf-restore:<attempt_id>`, binds that exact Job, Attempt, worker, and quota,
  and has the exact payload `{"transaction_group":"TX-9"}`;
- every harness epoch for that Attempt is `ABANDONED`, none is `CURRENT`, and no
  process generation for the Attempt has `executive_writer_held=1`; and
- the matching quota row is still exactly `ERROR` with
  `held_attempt_id IS NULL`, its `updated_at_ms` equals the matching TX-9 Event's
  `created_at_ms`, and no later Event row by `event_id` for that exact worker and
  quota exists before this requeue transaction. This conservative Event-history
  cutoff covers the shipped event-bearing status-change, release, claim,
  adoption, heartbeat, takeover, and terminal paths. The exact TX-9 status/holder/
  timestamp predicate makes the legacy compatibility holder-clearing paths
  ineligible before this special requeue; after it, the closed version/fence/
  update snapshot below detects every shipped lawful quota mutation. Together,
  the scoped cutoff and snapshot reject a later harmless-looking or flip-back
  transition without letting an unrelated fleet Event block recovery.

The matching Event is canonicalized for this decision as exactly:

```json
{
  "schema_version": "mastermind.executive_tx9_requeue_evidence/v1",
  "event_id": 1,
  "aggregate_type": "attempt",
  "aggregate_id": "ATT-...",
  "sequence": 1,
  "event_type": "OHF_RESTORE_INVALIDATED",
  "command_id": "ohf-restore:ATT-...",
  "actor": "restore",
  "job_id": "JOB-...",
  "attempt_id": "ATT-...",
  "worker_id": "worker-...",
  "quota_class": "main",
  "payload": {"transaction_group": "TX-9"},
  "created_at_ms": 0
}
```

`event_id` and `sequence` are the exact positive SQLite integers and
`created_at_ms` is the exact non-negative SQLite integer from the matching Event
row; every string is its exact non-empty row value, and the illustrative `...`
carries no wildcard meaning. No additional or omitted key is accepted. The evidence digest is
`sha256(canonical_json(this_object))` using the existing Executive canonical JSON
rules.

The transaction also derives the closed quota snapshot exactly as:

```json
{
  "schema_version": "mastermind.tx9_invalidated_quota_snapshot/v1",
  "worker_id": "worker-...",
  "quota_class": "main",
  "status": "ERROR",
  "held_attempt_id": null,
  "fence_counter": 0,
  "version": 1,
  "updated_at_ms": 0
}
```

The worker/quota values are the exact invalidated Attempt identities;
`fence_counter` is a non-negative integer, `version` is a positive integer, and
`updated_at_ms` is the exact non-negative quota-row value already required to
equal the TX-9 Event's `created_at_ms`. No additional or omitted key is accepted.
`invalidated_quota_snapshot_digest` is lowercase
`sha256(canonical_json(this_object))`.

If and only if those predicates hold, the transaction clears only the Job's
assigned-worker, assigned-quota, and current-Attempt projections, preserves the
trusted Job checkpoint, returns that same Job to `QUEUED`, and appends or
reconciles exactly one command-bound `JOB_REQUEUED` Event whose payload is
exactly:

```json
{
  "previous_status": "LOST",
  "requeue_kind": "TX9_DETACHED",
  "invalidated_attempt_id": "ATT-...",
  "invalidated_worker_id": "worker-...",
  "invalidated_quota_class": "main",
  "tx9_evidence_digest": "<lowercase sha256 hex>",
  "invalidated_quota_snapshot": {
    "schema_version": "mastermind.tx9_invalidated_quota_snapshot/v1",
    "worker_id": "worker-...",
    "quota_class": "main",
    "status": "ERROR",
    "held_attempt_id": null,
    "fence_counter": 0,
    "version": 1,
    "updated_at_ms": 0
  },
  "invalidated_quota_snapshot_digest": "<lowercase sha256 hex>"
}
```

The illustrative Attempt, worker, and quota values are the exact invalidated
Attempt-row identities, and the digest is the exact evidence digest defined
above. Identical command replay revalidates this full semantic target and returns
the same durable outcome, while target, payload, or evidence drift is a
`StateConflict`. The old Attempt, lease-null fact, epochs, generations, provider
session facts, and quota row remain byte/state-identical through requeue: this
branch never restores, releases, adopts, repairs, or re-enables capacity. Missing,
duplicate, forged, mismatched, non-`ERROR`, old-Attempt-held, current-epoch, live-
writer, or exhausted-budget evidence refuses atomically and changes nothing; a
quota that has been changed or now holds an unrelated Attempt is likewise
untouched. Ordinary non-TX-9 `LOST` requeue retains its existing holder-equality
law without relaxation.

Every direct candidate selection for a Job with a non-null Phase 1F-C
`orchestration_role` first derives the immutable set of **Phase 1F-C TX-9-
quarantined workers** inside its claim transaction. A worker is quarantined when
any Event row with `event_type='OHF_RESTORE_INVALIDATED'` names that `worker_id`
or names an Attempt whose immutable `attempts.worker_id` is that worker. A valid
TX-9 Event must have both identities equal; any missing/mismatched Attempt/Event
identity is invalid state and refuses the orchestration claim rather than being
ignored. Because v1 defines no typed process-absence or slot/host-reset receipt,
this immutable history is never cleared or overridden: **every quota class** of
every quarantined worker is excluded before normal capacity routing, regardless
of current Worker/quota status, `QUOTA_RELEASED`, provider/account metadata, or
which Job suffered the restore. This is an additive Phase 1F-C orchestration
claim fence only; it does not claim to repair or authorize generic role-null P1B
continuation.

The following exact-ID claim for the detached Job is a second direct Runtime
boundary, not an ordinary unqualified candidate scan. When a queued Phase 1F-C orchestration Job has
`current_attempt_id IS NULL` and its last consumed Attempt number equals its
`attempt_count`, Runtime must inspect that immutable terminal Attempt and the
unique command-bound `JOB_REQUEUED` Event that produced the current queued
projection. If its `requeue_kind` is `TX9_DETACHED`, the claim transaction must
rederive and validate the complete TX-9 Event/evidence digest, requeue payload,
and invalidated-quota snapshot/digest. The current invalidated quota row must
equal that snapshot field-for-field—not merely return to `ERROR`+null—and the
global quarantine rule above must exclude the invalidated worker and any other
candidate worker with its own TX-9 history before normal routing. Only a different,
non-quarantined accepted worker with an independently `AVAILABLE` matching quota
may be selected; the transaction then creates an ordinary fresh Attempt whose
local lifecycle begins at E1/G1. It leaves the old Attempt, epochs, generations,
provider session facts, and invalidated quota unchanged. The snapshot comparison,
global worker-quarantine derivation, capacity selection, and exclusion proof occur
inside the same SQLite claim transaction before an Attempt row, dispatch marker,
process launch, or provider call.

A bare quota status change, flip-away-and-back, `QUOTA_RELEASED`, already-
`AVAILABLE` alternate quota on the invalidated worker, different target Job,
caller assertion, mutable Worker metadata, or provider prose is not process-
absence or slot-reset proof. This v1 commissions no typed reset/absence receipt,
so any TX-9-quarantined worker is always refused for every Phase 1F-C
orchestration claim. If the invalidated quota no longer matches the complete
persisted snapshot at claim, the detached Job's claim refuses without an Attempt
or provider call even when another non-quarantined worker is available. Replaying
the already committed detached-requeue command after a later fresh claim is
Event-first historical reconciliation: it returns the original `JOB_REQUEUED`
outcome and can never queue the running/completed Job, replace its current
Attempt, or touch either worker's quota. Repairing generic role-null P1B TX-9
continuation or defining a reviewed same-worker reset receipt is outside this
commission.

### 4.5 Additional mandatory tests

Tests must prove:

- the handoff event is atomic, immutable, provider-neutral, content-addressed,
  idempotent, and leaves the root queued/unclaimed;
- the exact root is later claimed by the real supervisor as a fresh Attempt;
- the aggregation worker receives the frozen handoff, returns the typed aggregate,
  and ordinary `complete_job` emits the ordinary worker-bound `JOB_COMPLETED`;
- direct `complete_job(root)` without a real leased aggregation Attempt refuses;
- a pseudo-worker, cycle-written terminal result, stale handoff, wrong root,
  incomplete child, superseded-revision approval, lineage fork, missing snapshot,
  mutable Worker-row identity substitution, or malformed role result refuses;
- material/critical root or step impact forces review even when a plan says false,
  while a routine step may be promoted to reviewed but never used to downgrade its
  parent;
- an eligible root exists only when strict v2 CEO intent created its immutable
  aggregation role/provenance; arbitrary queued roots refuse;
- recoverable adverse state in every role uses one command-aware same-Job requeue
  before any create/dispatch; an exact remaining-budget TX-9-detached
  orchestration `LOST` state takes only the evidence-bound branch above, preserves
  the old quota's full continuity snapshot unchanged, and later continues through
  a fresh Attempt only after the direct claim matches that snapshot and selects a
  non-quarantined accepted worker; every Phase 1F-C orchestration claim globally
  excludes every quota on any worker with TX-9 history;
  cancellation/exhaustion maps plan, work/repair, review, and root aggregation to
  the exact state-machine action/reason with no untyped fatal branch;
- all nine policy bounds enforce non-review attempt limits <=2, review limit=1,
  and the exact mandatory validation-list inheritance;
- every orchestration claim/launch/result/terminal path binds one effective grant,
  placement, execution-principal snapshot, exact active-generation admission,
  immutable result seal, shutdown proof, terminal-evidence qualification, and
  closed raw role result under the author boundaries in §3.2/§4.4;
- frozen OHF TX-3 still sets `RUNNING` before TX-4 while the principal pair is
  null and all work/evidence boundaries refuse; TX-4 `ALLOW` atomically seals or
  matches the pair and admission Event, while TX-4 `REFUSE`/error seals neither;
- the typed supervisor observation uses the exact launched process credentials
  and fresh provider-home identity, excludes `account_label`, leaves
  `ObservedHarnessAttestation` unchanged, and refuses forged/mutable-row/worker-
  text substitutions before any turn;
- a crash before the TX-4 commit persists no partial principal/admission, a crash
  after commit replays without another provider call or duplicate Event, and a
  successor generation cannot inherit the predecessor's admission;
- G1 followed by G2/later can never use G1 admission/result evidence; G2 REFUSE or
  failure cannot fall back; an admitted greatest generation can schema-seal its
  exact candidate/result, pass TX-6/TX-8 shutdown, validate, and complete from
  terminal evidence without treating historical admission as new work authority;
- crashes before/after result seal, TX-6, TX-8, validation, and ordinary terminal
  commit reconcile without duplicate seal/admission/result/terminal evidence;
- valid command replay and supervisor crash/retry do not duplicate a handoff,
  Job, Attempt, result, or event, while semantic command collision refuses;
- existing-v3 normal-open refusal; exact-version read-only v3/v4 verification and
  restore drills with no migration/sidecar; quiesce/preflight/barrier enforcement;
  one exclusive transactional v3→v4 migration; exact pre/post legacy-content
  equality; injected JSON/Event mutation with unchanged IDs/counts refuses;
  failure-untouched behavior; post-commit writer refusal/quarantine until
  immediate v4 backup/drill completion; OHF TX-9 invalidation followed by exact
  detached requeue, Event-first replay, pre-requeue Event-history cutoff, full
  quota-snapshot continuity, worker-wide/cross-Job TX-9 quarantine, non-
  quarantined fresh-Attempt continuation, and forged/mismatched/live-writer/quota-
  state refusal; and populated-v3→v4 versus fresh-v4 schema parity; and
- all ordinary non-orchestration worker results remain behavior-compatible.

---

## 5. Required cycle state machine

Each invocation receives exactly one `--parent JOB-nnn`, verifies that the Job is
the root of the selected tree, was created by strict v2 CEO intent with immutable
`orchestration_role=aggregation` and cycle provenance, and is otherwise eligible;
it recomputes state from durable records and chooses the first applicable
**mutation class** in the ordered precedence below. Within one class it selects
the lowest tuple
`(role_precedence, plan_step_ordinal, repair_round, job_id)`, where
`plan=0, work=1, repair=2, review=3, aggregation=4`, a root/plan with no step uses
ordinal `-1`, and a null repair round compares as `0`. That total order is the
only tie-breaker; SQLite row order, timestamps, worker availability, and inbox
order never choose work.

1. **Refuse invalid authority/state.** Invalid root provenance, policy, schema,
   grant, lineage, reservation, or a prior semantic command collision appends the
   one typed block event and stops.
2. **Requeue one recoverable exact Job before any create or dispatch.** For any
   `plan`, `work`, `repair`, `review`, or root `aggregation` Job in
   `RATE_LIMITED`, `FAILED`, or `LOST` with remaining same-Job Attempt budget,
   invoke exactly one command-aware same-Job requeue and stop. Ordinary adverse
   states must remain eligible under the existing Runtime refusal law. The sole
   exception is an orchestration `OPERATOR_HARNESS` `LOST` Job in the exact TX-9-
   detached state defined in §4.4: it must use that narrow evidence-bound branch,
   queue the same Job while leaving the old `ERROR` quota untouched, and stop.
   The following invocation may dispatch it only by exact Job ID to a fresh
   Attempt after the direct claim transaction revalidates the TX-9/requeue chain,
   proves the invalidated quota still matches its complete requeue-time snapshot,
   derives the global TX-9-quarantined worker set, and selects a non-quarantined
   accepted worker's independently `AVAILABLE` capacity. The same worker filter
   applies to every Phase 1F-C orchestration candidate scan, including unrelated
   Jobs and a nominally different worker with its own TX-9 history. Missing or
   mismatched TX-9 evidence, old-quota snapshot drift, or quarantined-worker
   capacity is invalid state, not permission to relax the ordinary holder
   predicate. An exhausted TX-9 Job takes the same role-specific adverse mapping
   as any other exhausted Job. A root aggregation requeue first revalidates the
   immutable handoff and current lineage. No branch fabricates a replacement Job.
3. **Resolve one adverse terminal/review verdict.** Apply the following closed
   mapping, select one candidate by the total tie-breaker, perform its one action,
   and stop:

   - `CANCELLED` or Attempt-exhausted `plan` -> block
     `plan_terminal_adverse`;
   - `CANCELLED` or Attempt-exhausted `work`/`repair` -> block
     `child_terminal_adverse`;
   - `CANCELLED` or Attempt-exhausted root `aggregation` -> block
     `aggregation_terminal_adverse`;
   - a `CANCELLED` review Job, or a `RATE_LIMITED`/`FAILED`/`LOST` review Job with
     no remaining Attempt (review Job `attempt_limit=1`) -> create one new review
     Job for the same current revision when fewer than two review Job records
     exist, otherwise block `review_jobs_exhausted`;
   - a completed but VOID/non-independent review -> create one replacement review
     Job when fewer than two review Job records exist, otherwise block
     `review_not_independent`;
   - an independent completed `reject` of the current revision -> create exactly
     the next reserved repair revision when `repair_round < 2`, otherwise block
     `repair_rounds_exhausted`.

   There is no separate “fatal” prose category. Every terminal runtime state is
   classified by the predicates above or refuses as `result_protocol_invalid` /
   `lineage_invalid`.
4. **Create the planner.** If the eligible root has no child and no plan-admission
   event, create exactly one role=`plan` child with immutable provenance and stop.
5. **Dispatch one queued non-root Job.** Select the exact eligible queued
   `plan|work|repair|review` Job by the total order, dispatch only that ID through
   the accepted supervisor under one command binding, and stop.
6. **Admit one completed plan and its initial work wave.** Admission requires
   exactly one completed valid planner child, no other child, and no prior
   admission event. Validate the closed plan and derived review requirements,
   reserve the exact §R1 footprint, append `COO_PLAN_ADMITTED`, and create the
   ordered initial work Jobs in one atomic command transaction; then stop. If any
   child already exists or any check fails, create none and emit the corresponding
   typed block.
7. **Create one missing review.** For the lowest current completed revision whose
   derived review is required and has no review Job, create one bounded sibling
   review pointing to that exact revision and stop.
8. **Create the aggregation handoff.** A qualifying independent `approve` is
   derived evidence, not a write and not a STOP branch. If all current revisions
   are completed, all mandatory approvals qualify, and no handoff exists, the next
   actual mutation in the same invocation may therefore be the one immutable
   handoff/event; append it and stop.
9. **Dispatch the exact aggregation root.** If a valid handoff exists and the root
   is eligible and queued, dispatch that exact role=`aggregation` root as a fresh
   Attempt and stop.

If no mutation class applies, the command returns an idempotent `NO_ACTION`
observation and writes nothing. A successful approval is never “marked
satisfied”; history remains immutable and the predicate is recomputed.

The cycle reads the Executive runtime store and runtime APIs directly. It never
reads the Executive inbox, Wake projection, generated state, or chat state as an
input; the inbox is downstream projection only. The exact internal decomposition
may use pure functions plus a thin writer, but there is no cycle-local durable
state. Every decision is reconstructible from canonical runtime state.

“At most one transition” means one top-level COO action, not one internal worker
lifecycle write. Every cycle-authored create (including an atomic admission
batch), block, handoff, dispatch, or requeue receives a deterministic
`command_id = coo-cycle:<root>:<action>:<semantic-key>`. Each runtime API, including
an extended `requeue_job`, reconciles `(command_id, exact semantic target,
canonical payload digest)`: an identical replay returns the original durable
Job/event/Attempt/outcome, while reuse with another target or payload raises
`StateConflict`. An atomic admission batch has one top-level command and a frozen
ordered member manifest; each required `JOB_CREATED` event uses the deterministic
derived ID `<command_id>:member:<step-ordinal>`. Replay reconciles the entire
manifest and cannot accept or expose a partial batch.

Subtree scoping is load-bearing. Every dispatch phase names exactly one persisted
queued Job ID. The supervisor must claim only that ID or refuse; it may not scan,
select, or claim another eligible Job. Exact dispatch is command-aware: the
runtime binds `(cycle_command_id, exact_job_id)` to at most one Attempt in the
claim transaction. Replay or crash recovery returns/resumes that same Attempt or
its already terminal outcome and never creates another Job or Attempt. Under that
single top-level dispatch action, the supervisor may perform the ordinary claim,
launch, RUNNING, checkpoint, validation, and terminal subordinate transitions for
the bound Attempt; each remains lease/fence/grant-digest protected. The inert
implementation/test lane may use an explicit supervisor CLI for that exact ID.
Production dispatch requires a separately reviewed service boundary after Phase
1C-A; the CLI and deterministic fixture prove neither operational scheduling nor
service readiness.

“Ordinary subordinate transitions” does not mean an open-ended provider
conversation. For an orchestration Attempt, every `run_turn` entry reaches the
direct Runtime TX-5 cardinality gate in §4.4 before dispatch. One distinct turn per
generation and at most the G1/G2 pair under the exact pre-candidate process-loss
predicate per Attempt are absolute; the supervisor,
adapter, cycle, CLI, replay, timeout, retry, checkpoint, invalid result, or model
prose cannot widen them. Further useful work consumes a fresh governed Attempt,
not another OperationId, G3, or replacement epoch inside the old Attempt. TX-2
likewise permits only E1: failed/abandoned pre-turn start cycles cannot mint E2,
another session, or another process launch inside the Attempt.

`COO_CYCLE_BLOCKED` has exactly this closed reason vocabulary in v1:

```text
invalid_root | invalid_policy | invalid_plan | plan_capacity_exceeded |
fan_out_exceeded | children_total_exceeded | depth_exceeded |
unexpected_pre_admission_child | lineage_invalid | effective_grant_invalid |
validation_contract_invalid | principal_snapshot_invalid |
result_protocol_invalid | plan_terminal_adverse | child_terminal_adverse |
review_not_independent | review_jobs_exhausted | repair_rounds_exhausted |
aggregation_handoff_invalid | aggregation_terminal_adverse |
exact_dispatch_unavailable | state_conflict
```

The event binds root/selected Job, command ID, policy/plan/handoff digests, relevant
Job/Attempt/revision IDs, the one enum reason, and evidence hashes. Free-form prose
may explain the reason but cannot select a transition. Identical state/command
replay is one event; a different reason under the same command conflicts.

Retry is never synthesized by the cycle: it uses only the extended command-aware
form of the existing ordinary same-Job requeue transition, including the exact
TX-9-detached branch above, and the immutable role-specific Attempt ceilings. One
cycle invocation may requeue or later dispatch, never both. TX-9 requeue never
recovers capacity or resumes the old Attempt/session; only a later ordinary claim
with exact quota-snapshot continuity and the global non-quarantined-worker
predicate can create the next Attempt. Cancellation or exhausted attempts cannot
be reinterpreted as a repair verdict, successful terminal child, omitted step, or
aggregation input.

---

## 6. Changed-file commission for the inert implementation PR

After the required independent re-review of these exact bytes writes PASS, the
builder is commissioned to change only the smallest subset of these paths that
the accepted implementation requires:

### Expected production/config paths

- `config/authority_map.yml` — add only the exact `coo_cycle_policy` block.
- `control_plane/executive_authority.py` — fail-closed standard-library parsing
  and validation for that block, or an equivalently narrow reader in the new COO
  module; do not widen worker capabilities.
- `control_plane/ceo_intent.py` — preserve strict v1 unchanged; add strict v2 and
  atomically create its eligible Phase 1F-C root with
  `orchestration_role=aggregation` and paired cycle/root provenance; do not
  retrofit arbitrary queued Jobs.
- `control_plane/executive_runtime.py` — on the exact merged OHF schema-v3
  baseline, implement mandatory schema v4, exact Job/Attempt pairs and triggers,
  effective-grant/placement/principal/active-admission and terminal-evidence
  gates, immutable admission/result-seal/handoff events, role/lineage/reservation
  refusals, command-aware requeue and dispatch binding including the exact TX-9-
  detached orchestration branch, canonical quota-continuity snapshot/Event cutoff,
  and the subsequent global TX-9-worker quarantine/direct claim gate, existing-v3
  normal-open refusal, and the §4.4 explicit offline migration/legacy-content law. Preserve ordinary
  aggregation-Attempt `complete_job`, every non-TX-9 requeue predicate, generic
  role-null P1B behavior, and TX-9 itself; enforce depth/capacity/current-revision
  rules at direct runtime boundaries, and expose only narrowly required tree/
  evidence reads.
- `control_plane/executive_orchestration_principal.py` — new closed, secret-free
  placement/principal observation and snapshot schemas plus canonical digest
  helpers; it is not a second identity store and has no I/O.
- `control_plane/executive_orchestration_result.py` — new closed optional OHF
  raw-role-result observation protocol/type, the exact 8 MiB transport cap,
  canonical bytes/digest helpers, and duplicate-key/secret-refusal primitives;
  it is not a second result store and performs no provider or database I/O.
- `control_plane/operator_harness_orchestrator.py`,
  `control_plane/executive_operator_harness_port.py`, and
  `control_plane/codex_operator_adapter.py` — only the narrow additive v4 seams
  that (a) observe and pass typed principal facts into the existing TX-4 Runtime
  transaction and (b) collect the complete typed raw orchestration result from
  the exact completed native turn and pass it to the supervisor-owned validator/
  Runtime seal before shutdown. Preserve TX-3/TX-4 ordering, pure Runtime-owned
  comparison, all ordinary `run_turn`/`CandidateResult` behavior, every
  non-orchestration P1B payload, and the frozen `ObservedHarnessAttestation` and
  `OperatorHarnessAdapter` protocols.
- `scripts/ohf/laboratory.py` — only the fixed-method, one-shot in-memory raw-turn
  page primitive and the exact 64 MiB frame bound above. Preserve redaction for
  every ordinary response, notification, error, stderr, and P1B caller; no general
  raw request, raw logging, raw persistence, or raw exception payload.
- `control_plane/executive_backup.py` — exact-version v3/v4 read-only verification
  and restore drill, canonical legacy-content projection/digest, and preflight/
  completion receipt support; no restore drill may construct a writable/auto-
  migrating RuntimeStore.
- `control_plane/executive_supervisor.py` — executable closed result-schema
  constructors, golden digests, exact-Job-ID/command-bound dispatch, immutable
  effective-grant and launch-principal binding, pre-shutdown role-result seal,
  terminal-evidence qualification, supervisor-authored receipts, and lossless raw
  plan/verdict/lineage/handoff round-trip before terminal acceptance.
- `control_plane/worker_adapter.py` — only if the existing `SEALED_WORKER` path
  needs a narrow provider-neutral typed-result hook. It cannot carry or substitute
  for the separate OHF observation above; no provider-specific Phase 1F logic.
- `control_plane/executive_coo_cycle.py` — new deterministic state-machine and
  policy enforcement module.
- `scripts/executive_os_coo_cycle.py` — new explicit run-once CLI.
- `scripts/executive_os_migrate.py` — explicit offline exact-v3→v4 preflight,
  exclusive transactional migration, and post-v4 backup/drill completion CLI;
  normal runtime startup never invokes it.
- `scripts/executive_os_phase1b.py` — add only an explicit exact-Job-ID inert/test
  supervisor entry if no already-merged P1B entry satisfies the requirement. No
  service, selector, loop, timer, or production scheduling is commissioned.

### Expected tests

- `tests/test_executive_os_phase1fc.py` — new load-bearing cycle and refusal
  battery.
- `tests/test_executive_supervisor.py` — exact-ID command/Attempt containment,
  effective-grant and launch-principal binding, closed discriminators, golden
  schema digests, all five raw role-result round trips including a valid envelope
  over 4,000 characters, multi-block byte-for-byte reconstruction, author-boundary
  and secret-shaped/redaction-trigger refusal, and crash recovery without
  duplicate Attempt.
- `tests/test_executive_authority.py` — policy parser/hash/fail-closed coverage.
- `tests/test_ceo_intent.py` — v1 remains byte/behavior compatible and
  cycle-ineligible; strict v2 binds impact/kind/fingerprint/receipt/JOB_CREATED and
  atomically creates the eligible immutable aggregation root; generic,
  retrofitted, wrong-role, or provenance-missing roots are refused.
- `tests/test_executive_os_phase1fb.py` — direct `create_job` depth and preserved
  1F-B invariants, only where the boundary belongs there.
- `tests/test_executive_os_sqlite.py` — exact v4 columns, foreign keys, unique
  indexes, immutability/role/pair triggers, provider/account constraints, legacy
  null eligibility, active-admission/result-seal/terminal direct-boundary
  refusals, existing-v3 normal-open refusal, command-aware requeue/claim
  transactions, the evidence-bound TX-9-detached requeue without quota mutation,
  the pre-requeue Event cutoff and full quota-snapshot continuity, and worker-wide
  cross-Job TX-9 exclusion in every Phase 1F-C orchestration direct claim.
- `tests/test_executive_backup.py` — mandatory fresh-v4 and populated-v3→v4
  parity; exact-version non-migrating v3/v4 verification and restore drills;
  closed legacy-content projection and pre/post/backup/drill equality; injected
  payload drift; preflight/barrier/exclusive-migration behavior; migration-failure
  leaves v3 exact; post-commit writers remain refused/quarantined through v4
  completion; forward-fix/TX-9 preservation.
- `tests/test_ohf_p1b_restore_adversarial.py` — preserve the exact frozen TX-9
  invalidation assertions and add TX-9→detached command replay→same Job queued→
  non-quarantined-worker fresh Attempt/E1 coverage; prove the old Attempt/lease/
  epochs/generations and complete quota snapshot remain unchanged, any later
  Event by `event_id` naming the exact invalidated worker/quota before requeue
  refuses while an unrelated worker/quota Event does not,
  `ERROR→AVAILABLE→ERROR` with optional intervening
  claim/release fails snapshot continuity, an unrelated Phase 1F-C Job cannot use
  the re-enabled invalidated quota or any already-available alternate quota on
  that worker, the detached Job cannot choose a different worker that has its own
  TX-9 history, a worker with no TX-9 history succeeds, two-connection races
  serialize before Attempt/provider contact, post-claim replay cannot roll back
  the Job, missing/wrong/duplicate evidence, non-`ERROR` or unrelated-held quota,
  current epoch/writer, command collision, and exhausted budget refuse without
  mutation, and ordinary non-TX-9/role-null P1B behavior is unchanged.
- `tests/test_executive_wake_persist.py` — only a mechanical schema-v4
  compatibility assertion; no Wake behavior or contract change is commissioned.
- `tests/test_ohf_app_server_client.py` — new transport containment tests proving
  the ordinary request/notification paths still redact; only the fixed raw-turn
  method can receive a one-shot unredacted page; `repr`/errors/logs/stderr never
  reveal it; a secret-shaped raw envelope reaches the supervisor detector and
  refuses rather than arriving pre-sanitized; invalid UTF-8, malformed, oversized,
  non-turn, reused, wrong-ID, and post-consume access refuse without persistence
  or unbounded allocation; phase-cohort mixing/unknown phases and every exact page,
  cumulative-byte, cursor, and total-deadline bound are exercised.
- `tests/test_executive_model_router.py` — only if a planner-routing seam is
  introduced in the same reviewed PR; fixture-only core work must preserve the
  current frontier-lead refusal.
- `tests/test_ohf_p1b_orchestrator.py`, `tests/test_codex_operator_adapter.py`, and
  the merged OHF Runtime suites — preserve every existing P1B test/assertion and
  add only independently reviewed v4 orchestration cases for typed principal
  observation, same-TX4 atomic admission, forged-principal refusal, exact greatest-
  generation result seal, complete result over 4,000 characters, ordered
  multi-text-block round trip, unknown/dropped field, invalid canonical bytes,
  digest/candidate-artifact mismatch, wrong turn/generation, redaction-triggering
  content, latest-turn/no-later-TX5 sealing, seal-vs-TX5 concurrent ordering in
  both directions, same-OperationId proven-pre-dispatch TurnRef replay without a
  new slot or duplicate provider call, different same-generation OperationId refusal before dispatch,
  exactly one freshly admitted G2 turn only after the complete G1 pre-candidate
  process-loss predicate, refusal of G2 when G1 has candidate/checkpoint/effect-
  unknown/non-dead/non-RELEASED/new-epoch facts, no G3/third-turn or post-turn
  replacement-epoch path, post-seal direct turn/checkpoint/collection/resume refusal,
  same-TX2 pre-dispatch replay without a new epoch/duplicate provider call,
  different/pre-turn replacement TX-2 refusal after E1 exists, post-seal TX-2/
  new-epoch refusal, cleanup-only bounded heartbeat and expired-
  lease CAS takeover, Event-first post-seal replay with zero provider call,
  TX-6/TX-8 terminal qualification, no G1 fallback, seal-absent pre-seal crash/
  provider reread, fresh admission per lawful successor generation, and byte/
  behavior-identical ordinary P1B candidates and Events. No existing P1B assertion
  may be weakened or deleted; unrelated schema-version assertions may change only
  mechanically.

### Expected documentation

- `research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md` — mark §6 closed by
  this ruling and update implementation status after evidence exists; do not
  rewrite historical review findings.
- `docs/EXECUTIVE_WORKER_ROUTING.md` — describe the new unarmed run-once cycle,
  exact limitations, and acceptance state.

Any additional production/config path requires a written justification in the PR
body showing why the paths above cannot carry the change. The builder must stop
rather than opportunistically refactor adjacent Executive OS code.

No generated state, runtime database, receipt, credential, host configuration,
production dispatch service, or Agent OS record belongs in this implementation
PR.

---

## 7. Prohibited surfaces

The implementation must not:

- create a second database, queue, scheduler, lease table, liveness store,
  dedupe store, reviewer registry, or seat registry;
- add a daemon, interval, polling loop, launchd unit, tmux controller, persistent
  Sol/Fable process, automatic parent selector, or company priority ranking;
- call any model from inside the COO cycle process;
- claim a real, fixture, magic, or pseudo-worker merely to complete/fail a parent
  container, or weaken worker Attempt fencing with a bypass flag;
- create an attemptless parent completion or let the cycle author a worker result;
- add or arm Wake delivery, ACK, Slack, chat, notification, or GUI automation;
- add or arm EXEC-MCP-B or any remote/production CEO write surface;
- renumber, fork, reinterpret, or weaken merged OHF P1B schema v3, adapter,
  session, writer-lease, restore, Attempt-boundary, or activation law;
- add the production exact-ID dispatch service, daemon, timer, or selector in the
  inert implementation PR;
- change provider auth, readiness, install, Gate B, acceptance, LaunchDaemon, OS
  principal, Keychain, credential-home, or host-service code;
- enable a disabled provider or set `production_armed=true`;
- grant OPEN_PR, PUSH_BRANCH, MERGE, DEPLOY, SERVICE_CONTROL,
  CREDENTIAL_ADMIN, CROSS_REPO_PUBLISH, portfolio, billing, deletion, or capital
  authority;
- write Agent OS, strategic state, the Improvement Agenda, portfolio state, Macro,
  Terminal, or another repository;
- infer authority from `owner_seat`, `escalation_target`, `business_impact`,
  actor text, provider/model name, or a Fable label;
- accept a free-form plan, a builder self-report, a void review, or a missing
  receipt as successful aggregation; or
- describe merged code, fixture execution, green CI, provider readiness, or a
  Phase 1C-A PASS as a live Phase 1F-C vertical.

Merged OHF P1B is the prerequisite baseline, not a Phase 1F-C deliverable. Wake,
EXEC-MCP-B, OHF activation/provider-specific expansion, the production dispatch
service, external providers, multi-repository execution, and production arming
are separately governed later surfaces. They are not hidden deliverables of this
inert build and may not be smuggled into it.

---

## 8. Deterministic acceptance matrix

The inert implementation is accepted only when every applicable row passes:

| Area | Required proof | Fail-closed/adverse proof |
|---|---|---|
| policy/attempts | all nine exact schema-v1 fields load from `authority_map.yml`; non-review orchestration Jobs are `<=2` Attempts and review Jobs exactly `1` | missing/duplicate/malformed/overridden policy, root/non-review limit >2, review limit !=1, or extra cost class refuses |
| depth | root=0 and every cycle child=1 | direct Runtime and CLI creation of depth=2 is refused; `_MAX_JOB_DEPTH=64` cannot bypass policy |
| fan-out/reservation | at most eight logical steps; admission begins with exactly one completed plan child/no other child; per-step slots are exactly 1 unreviewed or 9 reviewed; event total is `1+sum(step_slots)` and includes the existing planner once | unexpected child, double-counted planner, total >16, partial admission, slot transfer, or child creation outside the reserved step/total refuses atomically |
| shrink/validation | child authority/path/cost/Attempt limits are explicit subsets; every RUN_TESTS work/repair/review role inherits the exact ordered mandatory root argv and IDs; other roles have none; review writes are empty | subset/reorder/extra argv, planner omission, defaulted limit/cost, review write, or other widening refuses before persistence |
| CEO intent versions | committed strict v1 remains unchanged, role-null, and ineligible; strict v2 requires cycle kind, impact, READ, limit<=2 and atomically binds fingerprint/receipt/JOB_CREATED to a role=aggregation root | v1 retrofit, unknown v2 key, missing READ/impact, generic/retrofitted/wrong-role/provenance-missing root, or digest drift refuses before child/event |
| schema v4/legacy | exact eight Job and six Attempt columns, paired/write-once gates, role nullability, and no v1-v3 backfill are identical on fresh-v4 and migrated stores | role-null legacy row becomes eligible, partial pair, role/lineage mutation, historical unattested identity, or fresh/migrated schema drift refuses |
| worker placement | immutable Worker/quota provider/account triggers hold; claim snapshots worker/quota/provider/account and enforces provider equality/canonical account | mutable-row substitution, mismatched provider, missing account, or historical unqualified row cannot produce an orchestration claim |
| TX-9 worker quarantine | every Phase 1F-C orchestration claim derives all workers named by any immutable `OHF_RESTORE_INVALIDATED` history and excludes all their quota classes; detached continuation also matches the complete invalidated-quota snapshot | unrelated Job, re-enabled invalidated quota, same-worker alternate quota, different candidate worker with its own TX-9, `ERROR→AVAILABLE→ERROR` flip-back, snapshot/version/fence/update drift, or malformed identity reaches Attempt/provider contact |
| effective grant | claim persists the exact canonical subset; plan/aggregation are READ-only with empty writes/validations; claim/packet/spec/launch/receipts/terminal all bind one digest | broad Job/root grant use, `authority_policy_hash` substitution, post-claim widening, or digest mismatch refuses |
| OHF admission/result/terminal qualification | TX-3 preserves process-bound `RUNNING` with principal null; typed supervisor process/provider-home observation plus placement and unchanged attestation enter the single TX-4 transaction; derived `ALLOW`, principal pair, decision, and exact-generation admission commit atomically; live work names the current greatest writer generation; its canonical role result seals before shutdown; after TX-6/TX-8, validation/completion use immutable terminal evidence and no-later-generation proof | TX-3-only RUNNING, caller comparison, widened attestation, forged principal, mutable Worker/result identity, REFUSE/error, partial commit, stale generation/admission, unsealed/competing result, live work after shutdown, digest mismatch, or G1 evidence after G2/later refuses while cleanup/adverse termination remains legal |
| result wire | immutable role selects the exact closed envelope/body; worker validations are []; supervisor preserves raw body/digest and authors artifact/validation/principal receipts; five golden schema digests and round trips are frozen | unknown/dropped field, wrong discriminator/identity/lineage, generic flatten, worker-authored receipt, NaN/noncanonical JSON, or executable advisory text refuses |
| mandatory review derivation | review is required when the typed plan requests it or root impact is material/critical or step impact is material/critical; routine may be promoted | planner false/omission/malformed impact cannot downgrade a mandatory review |
| lineage | each role follows exact immutable plan Attempt/digest/step, round, supersession, review pointer, and provenance rules; one current revision is derived | fork/cycle/cross-root/drift/skipped round or approval of a rejected/superseded revision cannot satisfy aggregation |
| one COO action | one invocation takes the first ordered mutation class and lowest specified tie-break tuple; derived approval may flow directly to handoff | row/time/inbox ordering, approval marker write, or two top-level mutations refuses |
| command replay | every create/batch/block/handoff/dispatch/requeue reconciles command ID, exact target, and payload digest | identical crash replay duplicates nothing; same command with different semantics raises `StateConflict` |
| exact dispatch | `(cycle_command_id, exact_job_id)` binds at most one Attempt; subordinate supervisor lifecycle resumes that Attempt/outcome | fleet scan, fallback claim, second Job/Attempt on recovery, or unrelated sentinel mutation refuses |
| provider lifecycle cardinality | TX-2 permits only E1 per Attempt; TX-5 permits one distinct turn per generation; a second exists only on freshly admitted same-epoch G2 after the exact G1 APPLIED/no-candidate/no-checkpoint/no-effect-unknown/dead+RELEASED recovery predicate; same pre-dispatch OperationId only reconciles its exact epoch/TurnRef | E2 or repeated start/session, second same-generation op, candidate/invalid-result continuation, ambiguous or live G1, G3/third turn, or provider call before the direct Runtime predicate/count refuses |
| review/reject | review points to current sibling revision, is read-only, attempt_limit=1; approve is derived; reject creates only next reserved repair | review-of-review, old-revision approve, unknown verdict, process failure treated as reject, or repair beyond round 2 refuses |
| independence/starvation | completing snapshots differ by worker; live proof also differs by OS principal/UID, provider home, account; second VOID review blocks `review_not_independent` | mutable Worker row, same identity, extra review record/Attempt, impact, actor, or self-waiver cannot satisfy aggregation |
| adverse precedence | recoverable RATE_LIMITED/FAILED/LOST of any role requeues one same Job first; exact TX-9-detached orchestration LOST evidence queues the same Job with a canonical quota snapshot, then only a later direct claim that matches that full snapshot and globally excludes every worker with TX-9 history creates a fresh Attempt; an unrelated worker/quota Event does not block that requeue; plan/work-repair/root exhaustion maps to its exact adverse reason; review failure uses one replacement or exhausts | generic LOST+null-holder relaxation, missing/mismatched TX-9 evidence, any later Event naming the exact invalidated worker/quota before requeue, quota flip-back/version/fence/update drift, any quota on any TX-9-quarantined candidate worker, old Attempt/session adoption, omitted/repaired/aggregated adverse child, stale root handoff requeue, undefined fatal branch, or new dispatch before eligible requeue refuses |
| blocked event | every block is one idempotent `COO_CYCLE_BLOCKED` from the exact closed reason enum, including plan/child/aggregation adverse, review exhaustion, and repair exhaustion | prose/inbox selection or same command with another reason cannot alter transition |
| aggregation handoff | one immutable content-addressed provider-neutral event freezes current revisions, supervisor receipts, grants, and qualifying approvals while root remains queued | living/adverse child, missing approval, stale lineage/grant/handoff, mutable identity, or partial repair blocks handoff/dispatch |
| aggregation Attempt | exact root runs as a fresh command-bound real Attempt with exact READ grant; ordinary `complete_job`/`JOB_COMPLETED` follows terminal revalidation | pseudo-worker, cycle-authored result, no lease/snapshot, wrong handoff, or runtime-refusal bypass refuses |
| v4 backup/migration | existing-v3 normal open is mutation-free and refuses; explicit offline lock/barrier plus exact-v3 version-aware verify/backup/read-only drill and canonical legacy-content digest precede one exclusive migration transaction; same closed projection is equal inside v4, backup, and drill; exact guard proves v3 after rollback; committed v4 stays barred until completion | auto-migration, writable/migrating drill, stale/missing preflight, writer race, legacy payload drift despite equal IDs/counts, partial v4 after rollback, barrier/quarantine bypass, post-commit writer resume without completion, downgrade/deletion, OHF-state loss, or parity mismatch refuses |
| exception/inbox | bound/repair/independence exceptions remain incomplete and project downstream through existing evidence kinds | cycle never reads inbox/Wake/generated state to start, widen, rank, or choose work |
| regression/inertness | existing 1F-B, v1 intent, router, inbox, authority, supervisor, readiness, OHF, and backup tests remain green; import/help/preview and explicit test CLI are inert | service/timer/selector, production flag, provider call, host claim, operational dispatch claim, or changed legacy result behavior fails acceptance |

The new `tests/test_executive_os_phase1fc.py` name is protected by the repository's
discovery-first `tests/test_executive_*` CI rule and must not be added to an
exclusion manifest.

Required focused verification at minimum:

```bash
python3 -m pytest -q \
  tests/test_executive_authority.py \
  tests/test_executive_supervisor.py \
  tests/test_executive_backup.py \
  tests/test_executive_os_sqlite.py \
  tests/test_executive_os_phase1fb.py \
  tests/test_executive_os_phase1fc.py \
  tests/test_executive_inbox_phase1fb.py \
  tests/test_executive_model_router.py \
  tests/test_ceo_intent.py \
  tests/test_ohf_p1b_runtime.py \
  tests/test_ohf_p1b_runtime_adversarial.py \
  tests/test_ohf_p1b_runtime_orchestrator.py \
  tests/test_ohf_p1b_orchestrator.py \
  tests/test_ohf_p1b_restore_adversarial.py \
  tests/test_ohf_app_server_client.py \
  tests/test_codex_operator_adapter.py
python3 scripts/ci_pytest.py
python3 -m compileall -q control_plane scripts
git diff --check
```

A fresh independent reviewer must first re-review these exact bytes and write
`PASS`, explicitly closing every design blocker. Implementation review must then
inspect authority parsing, direct Runtime bypass
attempts, role-result discrimination, revision lineage, reservation arithmetic,
typed principal sources and same-TX4 work admission, offline migration barriers,
crash boundaries, batch atomicity, exact-ID containment, and the absence of model/
provider/host side effects. Green happy-path tests alone are insufficient.

---

## 9. Minimum deterministic demonstration

The deterministic acceptance fixture contains:

```text
CEO parent root depth=0
├── role=plan child depth=1 (fixture Fable/COO typed plan result)
├── role=work revision 0 depth=1, review_required=1
├── role=review depth=1, reviews_job_id -> work revision 0
├── optional role=repair revision 1 depth=1, supersedes revision 0
└── optional replacement role=review -> repair revision 1

unrelated queued sentinel in a different root
```

The demonstration must show:

1. strict v1 remains role-null/ineligible while strict v2 binds kind, impact,
   READ, fingerprint, receipt, `JOB_CREATED`, parent role/provenance, and stops
   without dispatch;
2. successive explicit cycle invocations take the ordered first mutation and at
   most one top-level COO action; a derived qualifying approval may proceed to the
   next actual handoff write without an invented approval marker;
3. the typed fixture plan is losslessly round-tripped without using
   `next_actions`, names every mandatory root validation ID in exact order,
   persists `COO_PLAN_ADMITTED` with one reviewed step's nine step slots and ten
   total direct-child slots (planner counted once), and creates exactly one bounded
   initial work revision;
4. each dispatch binds command plus exact Job ID to one Attempt, crash/replay
   returns/resumes that same Attempt/outcome, and the sentinel remains
   byte/state-identical;
5. every real supervisor Attempt seals its immutable effective grant and
   placement; for the OHF fixture, TX-3 proves process-bound `RUNNING` is not work
   authority, then same-TX4 accepted principal/admission evidence gates the first
   turn. Receipt-backed direct Runtime evidence proves that same-OperationId TX-2
   pre-dispatch replay returns the same E1/G1 without a provider call, another
   TX-2 OperationId/E2 refuses before launch, and a different same-generation
   TX-5 refuses before provider dispatch. Separate fixtures prove that the exact
   G1 TX-5 `INTENT`+`APPLIED`, no-candidate/no-checkpoint/no-`EFFECT_UNKNOWN`,
   `PROVEN_DEAD`+provider-`RELEASED` state alone permits same-epoch G2; any G1
   candidate or `EFFECT_UNKNOWN` refuses G2; fresh G2 TX-4 admission permits its
   one turn; and G3 or a third Attempt turn refuses before provider contact. The
   successful result path's typed observation round-trips the full canonical
   envelope (including an ordered multi-block result over 4,000 characters), ties
   it to the unchanged candidate artifact digest, and lets the exact greatest
   generation seal that envelope and independently derived raw role-body digest
   before TX-6/TX-8 shutdown. Post-shutdown validation/terminal completion use
   only terminal-evidence qualification; the supervisor authors validation/
   artifact receipts, and a redaction-triggering envelope refuses rather than
   being silently rewritten;
6. a different fixture worker snapshot completes the sibling review with typed
   `approve`;
7. an adverse branch rejects revision 0, creates repair revision 1, and proves a
   late approval of revision 0 cannot satisfy the repaired step;
8. the runtime refuses a handoff before the current-revision approval, then emits
   exactly one immutable provider-neutral handoff/event after approval;
9. a later invocation dispatches the exact root through the real supervisor as a
   fresh aggregation Attempt; ordinary `complete_job` and `JOB_COMPLETED` finish
   the typed aggregate only after runtime refusals pass;
10. the inbox/readback reconciles the tree while never supplying cycle input;
11. replaying every create/block/handoff/requeue command changes nothing, while
    reuse with different semantics refuses; and
12. the fresh-v4 path and explicit populated-v3 offline-upgrade path prove
    existing-v3 normal-open refusal, preflight receipt, exact-version pre/post
    restore drills, transaction-rollback exact-v3 guard, identical closed legacy-
    content digests in live v4/backup/drill, injected payload-drift refusal, post-
    commit writer barrier/quarantine, forward-fix boundary, and frozen OHF TX-9
    behavior; a separate active orchestration fixture is restore-invalidated to
    exact `LOST`/abandoned/writer-free/`ERROR`+null-holder state, command-requeues
    that same Job exactly once without changing its old Attempt or quota, and
    later claims a fresh Attempt/E1 only when the invalidated quota still matches
    its complete requeue-time snapshot and the selected worker has no TX-9
    history. A later Event by `event_id` naming the exact invalidated worker/quota
    before requeue refuses, while an unrelated worker/quota Event is proven not to
    block it. `ERROR→AVAILABLE→ERROR` (with or
    without intervening claim/release), an unrelated Job using the re-enabled
    quota or an already-`AVAILABLE` alternate quota on that worker, and selecting
    a different worker with its own TX-9 history all refuse before Attempt/provider
    contact; a non-quarantined worker succeeds and leaves the old snapshot
    unchanged; replaying the old requeue command afterward cannot roll the Job
    back. Wrong/missing TX-9 evidence, live writer/current epoch, non-`ERROR` or
    held quota, exhausted budget, and command collision each refuse without
    mutation.

This is `DETERMINISTIC_ACCEPTANCE_PASS`, not provider, host, Fable-principal, or
live-vertical proof.

---

## 10. Required delivery packet

The implementation PR must state separately:

- base SHA and head SHA;
- exact OHF P1B merge SHA, proof that it owns schema v3, the Phase 1F-C rebase
  SHA, and the exact mandatory v4 migration/schema diff;
- exact changed paths and why each was required;
- policy values and policy-file SHA-256;
- focused and full CI commands/results;
- updated rebased-design review verdict explicitly closing every design blocker,
  followed by the implementation-review verdict and every repaired finding;
- the five closed role-schema golden digests, canonicalization implementation,
  and proof that legacy result v1 is unchanged;
- deterministic acceptance Job/Attempt/Event IDs or fixture manifest hashes,
  including effective-grant/placement/principal, per-generation admission,
  immutable role-result seal, terminal-evidence, handoff, and command-replay
  digests, plus the complete derived TX-9-quarantined worker set for every
  orchestration claim fixture;
- exact-version preflight and completion receipt schemas/digests, verified/drilled
  pre-migration v3 and post-migration v4 backups, normal-open/barrier refusal,
  fresh-versus-migrated schema parity, exact pre/post/backup/drill legacy-content
  equality, injected payload-drift refusal, transaction-rollback exact-v3 proof,
  and OHF TX-9 proof, including the command/evidence digest for exact detached
  same-Job requeue, Event-history cutoff, canonical quota snapshot/digest and
  uninterrupted equality, unchanged old Attempt/epoch/generation/quota, global
  cross-Job/all-quota quarantined-worker exclusion, post-claim historical replay,
  and the non-quarantined-worker fresh Attempt/E1;
- explicit confirmation that no host/provider/Wake/MCP/OHF-activation/production
  dispatch action ran;
- explicit remaining gates from §11; and
- the exact rollback side of the release boundary:
  - **pre-migration/revertible:** while no authoritative Executive database has
    successfully committed schema v4, keep the cycle uninvoked/unarmed and the
    service stopped; the Phase 1F-C code/commission commit may be reverted. A
    failed exclusive migration whose rollback passes the exact-v3 guard remains
    on this side;
  - **post-migration/forward-fix-only:** after any authoritative database commits
    schema v4, no v3 binary, schema downgrade, v3 restore over the authoritative
    v4 store, deletion of v4 columns/events/evidence, or commit revert that makes
    installed code v3-only is permitted. Disable/unarm Phase 1F-C, stop affected
    writers, preserve the v4 database, any extant barrier, backups, and receipts,
    and ship a reviewed v4-compatible forward fix.

The PR may be delivered and merged through the normal repository workflow. It
must not install or activate itself. After merge, `origin/master` remains the
only candidate source for the later exact-SHA host transaction.

---

## 11. Live vertical gates

No one may claim `PHASE1FC_LIVE_ACCEPTANCE_PASS` until all gates below pass on a
named exact release:

### G0 — exact release freeze

- clean `HEAD == origin/master == <release-sha>`;
- release descends from the named OHF P1B schema-v3 merge and the independent
  PASS on this revised source law, and contains the mandatory reviewed schema-v4
  migration;
- all intended Phase 1F-C code and its acceptance harness are merged;
- no uncommitted or alternate-checkout bytes enter the release.

### G1 — Phase 1C-A substrate

- exact-SHA install with reviewed config and services initially stopped;
- provider-readiness v2 PASS for the dedicated company-bound credential;
- Git handoff Gate B PASS for the same installed SHA and independent receipt
  review releases the STOP;
- formal Phase 1C-A acceptance PASS for that SHA, including success,
  interruption/requeue, UID cleanup/seal, backup/restore, and no-public-listener
  evidence;
- the exact release's explicit v3→v4 offline preflight, quiesce/census, mutation-
  free normal-open refusal, exact-version pre/post restore drills, exclusive
  migration/schema parity, pre/post/backup/drill legacy-content equality, durable
  completion receipt, barrier removal with no quarantine, frozen OHF TX-9
  evidence, and exact detached-requeue/quota-continuity/global-worker-quarantine/
  non-quarantined fresh-Attempt recovery proof pass before orchestration writers
  run.

### G2 — live worker composition

- builder and reviewer worker IDs are registered through reviewed host config;
- each has a distinct accepted OS principal, provider home, and account label;
- neither worker appears in any immutable `OHF_RESTORE_INVALIDATED` history; v1
  has no reset receipt that can waive this worker-wide Phase 1F-C exclusion;
- immutable worker/quota provider/account triggers and provider-equality checks
  are installed and proven;
- their completing Attempts contain immutable execution-principal snapshots
  matching placement snapshots plus qualifying final-generation accepted launch/
  admission, immutable result seal, P1B shutdown, and terminal-evidence proof for
  those identities;
- each orchestration Attempt binds the exact effective-grant digest through claim,
  launch, result schema, supervisor receipts, and terminal event;
- route/capability/policy-version bindings are current and receipted;
- no new authority beyond the existing Executive worker allow-list.

### G3 — Fable/COO planner principal

- an independently reviewed planner route/adapter exists without changing seat
  authority or calling a model inside the cycle;
- one bounded planning Job completes with authenticated Fable/COO provenance,
  exact model/provider/process/session identity, policy version, and
  `mastermind.execution_plan/v1` result hash;
- planner authority cannot dispatch, merge, deploy, arm, or widen its parent.

### G4 — production exact-ID dispatch boundary

- after Phase 1C-A PASS, a separate security review accepts the smallest service
  boundary that receives one exact queued Job ID and invokes the accepted
  supervisor;
- it cannot scan the fleet, select company priority, fall back to another Job,
  loop, or treat inbox/Wake state as dispatch authority;
- service identity, config, kill switch, failure/restart behavior, and exact-SHA
  deployment are independently receipted.

The inert/test supervisor CLI is not evidence for this gate.

### G5 — Sol-to-COO-to-worker live receipt

One low-risk dedicated-worktree objective proves:

```text
Sol strict v2 typed intent
-> durable root Job
-> Fable/COO planning Job and validated immutable plan
-> bounded work Job through the accepted supervisor
-> supervisor validation, closed typed work result, immutable effective grant,
   placement/execution-principal snapshots, qualifying-generation admission,
   immutable result seal, P1B shutdown, and terminal-evidence qualification
-> distinct-principal/provider-home sibling review with typed approve
-> immutable provider-neutral aggregation handoff/event
-> exact root dispatched as a fresh real aggregation Attempt
-> typed aggregate completed through ordinary complete_job/JOB_COMPLETED
-> Sol inbox/state/result readback
```

The receipt names release/config/policy hashes, every Job/Attempt/worker ID,
provider process/session identities, OS UIDs, provider-home identities, command
IDs, validation results, artifact hashes, event sequences, and readback hash. An
unrelated queued sentinel proves subtree containment. A cycle crash/replay proves
idempotency; the exact-release Phase 1C-A receipt may supply the worker-process
failover proof by reference.

### G6 — adverse live proof

- same-worker, same-OS-principal, same-provider-home, or same-account review is
  VOID;
- two void review Jobs for the current revision produce
  `review_not_independent` and no parent completion;
- reject creates only a bounded repair;
- approval of the rejected predecessor remains stale after repair;
- recoverable adverse states requeue the same command-bound Job before new work;
  exact TX-9-detached LOST requeues only with matching immutable restore evidence,
  leaves the old Attempt/session/epoch/generation and `ERROR` quota untouched, and
  reaches any continuation only through a later direct claim that matches the
  complete quota-continuity snapshot and creates a fresh Attempt on an accepted
  worker with no TX-9 history; every Phase 1F-C orchestration claim, including an
  unrelated Job, excludes every quota of every TX-9-quarantined worker;
  plan, child, review, repair, and aggregation exhaustion each emits its exact
  typed `COO_CYCLE_BLOCKED` reason and stops;
- mutable Worker-row changes cannot alter snapshot-based independence;
- broad/fallback dispatch cannot touch the unrelated sentinel; dispatch crash and
  replay cannot create a second Attempt;
- no waiver, unrelated dispatch, service expansion, public listener, Wake, MCP-B,
  OHF activation/provider expansion, merge, deploy, cross-repo, portfolio, or
  capital effect occurs.

### G7 — acceptance and arming separation

An independent reviewer adjudicates the complete live packet. A PASS proves the
bounded vertical only. `production_armed` remains false until a later explicit
CEO/Chairman decision names the accepted release, operating envelope, kill
switch, rollback, monitoring, and expiry/review condition.

---

## 12. Deferred surfaces and next boundary

OHF P1B is merged and this commission is on its exact baseline. This revision now
waits for a fresh independent review PASS. Once that PASS authorizes a separate
builder, the commission ends when the inert Phase 1F-C build is merged with
deterministic acceptance and the live gates are truthfully listed. The same
implementation session does not expand into:

- Wake admission repair, delivery, ACK, retry, or arming;
- EXEC-MCP-B trusted production writes;
- OHF activation, provider-specific expansion, or changes to merged P1B
  session/writer/restore/Attempt-boundary semantics;
- the separately reviewed post-Phase1C-A production exact-ID dispatch service;
- external providers;
- multi-repository execution;
- automatic scheduling, CEO invocation, PR/merge/deploy, or capital authority.

Those may consume the accepted Executive OS later. None may become a prerequisite
invented by the Phase 1F-C builder, and none may be represented as already
delivered by this ruling.

---

## 13. Final ruling

The six Phase 1F-C questions are closed exactly as follows:

| Question | Binding answer |
|---|---|
| policy home and bounds | `config/authority_map.yml`; schema v1; at most 8 logical work-plan steps; depth 1/direct children only; repairs 2; review Job records per revision 2; non-review orchestration Job Attempts <=2; review Job Attempt exactly 1; every direct child within total 16 after exact worst-case reservation; cost classes default/small |
| verdict vocabulary | binary `approve` / `reject`; repair is workflow, not a third verdict |
| seat registry | deferred; prose hierarchy and descriptive vocabulary remain; no new registry |
| independent review | compare immutable completing-Attempt snapshots: different worker ID always; live acceptance additionally requires different OS principal/UID, provider home, and account label |
| sequencing | accepted 1F-B; OHF P1B/schema v3 merged first at `4f672b8`; mandatory additive schema v4 is frozen here; fresh independent PASS next; then separate inert 1F-C; Phase 1C-A plus separately accepted production dispatch before live 1F-C |
| starvation | typed escalation after two review Job records for the current revision; no self-waiver at any impact level |

The CEO source-law remediation is **revised**, not implementation-authorized. OHF
P1B is merged and this commission is based on its exact squash merge. A separate
builder may begin only after a fresh independent reviewer re-reviews these exact
bytes and writes `PASS`. Even then, the builder may not claim a live COO, a live
Fable planner, production dispatch,
provider readiness, host acceptance, production activation, or end-to-end
Executive OS completion without the corresponding receipts in §11.
