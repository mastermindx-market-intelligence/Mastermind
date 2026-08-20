# Executive OS Phase 1F-C — CEO policy ruling and implementation commission

**Date:** 2026-08-20

**Authority:** AI CEO Sol, acting under the Chairman's Executive OS completion
directive and the hierarchy in `AGENTS.md` / `CLAUDE.md`

**Runtime design baseline:** Mastermind merge commit
`4f672b8f6b950010534390001f4a17ed232e0390` (OHF P1B PR #93; descends from
provider-readiness PR #92)

**Delivery base at finalization:** Mastermind `origin/master`
`e61e48904302d0aae53baeab0e2681ee3fbec97d` (docs-only Pro Sol Slack ingress
PR #91; no Executive runtime/schema overlap with the reviewed baseline)

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
`worker_id` values. Identity is read from immutable execution-principal snapshots
sealed on the two completing Attempts from supervisor launch attestation, never
from a terminal-time mutable Worker/config lookup. Provider/account placement is
copied at claim only from the v4 database-immutable registration rows in §4.4 and
then bound into the launch attestation. The snapshot contains at minimum
`worker_id`, OS-principal name and numeric UID, provider-home identity, provider,
`account_label`, launch-attestation digest, and snapshot timestamp. Result
acceptance refuses a missing or post-launch-mutated snapshot.

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
   launch-attested principal snapshots. Phase 1F-C therefore **must** add schema
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
digest input. The supervisor derives and persists the full raw `role_result`, its
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
   read-shaped evidence access needed to aggregate, then seal the Attempt's
   execution-principal snapshot from the accepted launch attestation before
   RUNNING;
3. require `mastermind.aggregation_result/v1` tied byte-for-byte to the handoff
   digest and current lineage;
4. run the role-specific validation and re-read the runtime aggregation
   conditions; and
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
effective grant, placement, and launch-attested identity. Phase 1F-C therefore
**must set `SCHEMA_VERSION = 4`** and perform exactly the additive migration below.
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
and one `COO_AGGREGATION_HANDOFF_READY` event per root. The two event indexes use
the event row's root `job_id`, not an unindexed prose field. Command ID remains
globally unique. Replacement reviews intentionally remain separate Job records
and are limited transactionally to two per exact current revision.

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
effective-grant and placement pairs must be non-null. Before it may enter
`RUNNING`, checkpoint, validate, or complete, its launch-attested
execution-principal pair must also be non-null. An Attempt that fails, is lost,
is rate-limited, or is cancelled before accepted launch may terminate without the
launch pair; it retains its effective-grant and placement evidence but cannot
supply a completed role result, review authority, aggregation evidence, or live
acceptance. Historical or unattested rows remain valid legacy evidence but never
satisfy independence, orchestration result, aggregation, or live acceptance.

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
orchestration-ineligible. The launch snapshot references the exact placement
digest and adds the attested OS-principal name, numeric UID, provider-home
identity, provider, account label, launch-attestation digest, and attestation time.
It must equal the placement provider/account/worker and is sealed before RUNNING.

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

The v3→v4 transaction follows the OHF backup constitution: quiesce all v3 writers;
take, verify, and restore-drill a v3 backup; perform the atomic migration on the
quiesced store; and leave the original v3 database untouched if any migration or
integrity check fails. After success, immediately take, verify, and restore-drill
a v4 backup before writers resume. Rollback is forward-fix only—never delete v4
evidence or downgrade the live file. Every existing row, ID, foreign key, index,
trigger, JSON payload, event, OHF epoch/generation/operation record, and version is
preserved, including OHF TX-9 restore invalidation semantics. A fresh-v4 database
and a populated-v3→v4 database must have byte-equivalent normalized schema,
indexes, and triggers. Backup/restore tests prove both paths and the v3-untouched
failure path.

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
  before any create/dispatch; cancellation/exhaustion maps plan, work/repair,
  review, and root aggregation to the exact state-machine action/reason with no
  untyped fatal branch;
- all nine policy bounds enforce non-review attempt limits <=2, review limit=1,
  and the exact mandatory validation-list inheritance;
- every orchestration claim/launch/result/terminal path binds one effective grant,
  placement, launch snapshot, and closed raw role result under the author
  boundaries in §3.2/§4.4;
- valid command replay and supervisor crash/retry do not duplicate a handoff,
  Job, Attempt, result, or event, while semantic command collision refuses;
- exact v3 quiesce/backup/restore-drill, failure-untouched behavior, immediate
  v4 backup/restore-drill, OHF TX-9 invalidation, and populated-v3→v4 versus
  fresh-v4 schema parity; and
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
   `RATE_LIMITED`, `FAILED`, or `LOST` with remaining same-Job Attempt budget and
   otherwise eligible under the existing runtime refusal law, invoke exactly one
   command-aware same-Job requeue and stop. A root aggregation requeue first
   revalidates the immutable handoff and current lineage. It never fabricates a
   replacement Job.
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
form of the existing ordinary same-Job requeue transition and the immutable
role-specific Attempt ceilings. One cycle invocation may requeue or later
dispatch, never both. Cancellation or exhausted attempts cannot be reinterpreted
as a repair verdict, successful terminal child, omitted step, or aggregation
input.

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
  effective-grant/placement/launch-snapshot gates, immutable admission/handoff
  events, role/lineage/reservation refusals, command-aware requeue and dispatch
  binding, and the §4.4 migration/backup law. Preserve ordinary
  aggregation-Attempt `complete_job`, enforce depth/capacity/current-revision rules
  at direct runtime boundaries, and expose only narrowly required tree/evidence
  reads.
- `control_plane/executive_supervisor.py` — executable closed result-schema
  constructors, golden digests, exact-Job-ID/command-bound dispatch, immutable
  effective-grant and launch-principal binding, supervisor-authored receipts, and
  lossless raw plan/verdict/lineage/handoff round-trip before terminal acceptance.
- `control_plane/worker_adapter.py` — only if the merged P1B adapter contract needs
  a narrow provider-neutral typed-result hook; no provider-specific Phase 1F logic.
- `control_plane/executive_coo_cycle.py` — new deterministic state-machine and
  policy enforcement module.
- `scripts/executive_os_coo_cycle.py` — new explicit run-once CLI.
- `scripts/executive_os_phase1b.py` — add only an explicit exact-Job-ID inert/test
  supervisor entry if no already-merged P1B entry satisfies the requirement. No
  service, selector, loop, timer, or production scheduling is commissioned.

### Expected tests

- `tests/test_executive_os_phase1fc.py` — new load-bearing cycle and refusal
  battery.
- `tests/test_executive_supervisor.py` — exact-ID command/Attempt containment,
  effective-grant and launch-principal binding, closed discriminators, golden
  schema digests, all five raw role-result round trips, author-boundary refusals,
  and crash recovery without duplicate Attempt.
- `tests/test_executive_authority.py` — policy parser/hash/fail-closed coverage.
- `tests/test_ceo_intent.py` — v1 remains byte/behavior compatible and
  cycle-ineligible; strict v2 binds impact/kind/fingerprint/receipt/JOB_CREATED and
  atomically creates the eligible immutable aggregation root; generic,
  retrofitted, wrong-role, or provenance-missing roots are refused.
- `tests/test_executive_os_phase1fb.py` — direct `create_job` depth and preserved
  1F-B invariants, only where the boundary belongs there.
- `tests/test_executive_os_sqlite.py` — exact v4 columns, foreign keys, unique
  indexes, immutability/role/pair triggers, provider/account constraints, legacy
  null eligibility, and command-aware requeue/claim transactions.
- `tests/test_executive_backup.py` — mandatory fresh-v4 and populated-v3→v4
  parity; v3 and v4 verified restore drills; migration-failure leaves v3
  untouched; forward-fix/TX-9 preservation.
- `tests/test_executive_wake_persist.py` — only a mechanical schema-v4
  compatibility assertion; no Wake behavior or contract change is commissioned.
- `tests/test_executive_model_router.py` — only if a planner-routing seam is
  introduced in the same reviewed PR; fixture-only core work must preserve the
  current frontier-lead refusal.
- merged OHF P1B tests — run unchanged as regression proof; edit only if a
  mechanical schema-version assertion is unavoidable and independently reviewed.

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
| effective grant | claim persists the exact canonical subset; plan/aggregation are READ-only with empty writes/validations; claim/packet/spec/launch/receipts/terminal all bind one digest | broad Job/root grant use, `authority_policy_hash` substitution, post-claim widening, or digest mismatch refuses |
| result wire | immutable role selects the exact closed envelope/body; worker validations are []; supervisor preserves raw body/digest and authors artifact/validation/principal receipts; five golden schema digests and round trips are frozen | unknown/dropped field, wrong discriminator/identity/lineage, generic flatten, worker-authored receipt, NaN/noncanonical JSON, or executable advisory text refuses |
| mandatory review derivation | review is required when the typed plan requests it or root impact is material/critical or step impact is material/critical; routine may be promoted | planner false/omission/malformed impact cannot downgrade a mandatory review |
| lineage | each role follows exact immutable plan Attempt/digest/step, round, supersession, review pointer, and provenance rules; one current revision is derived | fork/cycle/cross-root/drift/skipped round or approval of a rejected/superseded revision cannot satisfy aggregation |
| one COO action | one invocation takes the first ordered mutation class and lowest specified tie-break tuple; derived approval may flow directly to handoff | row/time/inbox ordering, approval marker write, or two top-level mutations refuses |
| command replay | every create/batch/block/handoff/dispatch/requeue reconciles command ID, exact target, and payload digest | identical crash replay duplicates nothing; same command with different semantics raises `StateConflict` |
| exact dispatch | `(cycle_command_id, exact_job_id)` binds at most one Attempt; subordinate supervisor lifecycle resumes that Attempt/outcome | fleet scan, fallback claim, second Job/Attempt on recovery, or unrelated sentinel mutation refuses |
| review/reject | review points to current sibling revision, is read-only, attempt_limit=1; approve is derived; reject creates only next reserved repair | review-of-review, old-revision approve, unknown verdict, process failure treated as reject, or repair beyond round 2 refuses |
| independence/starvation | completing snapshots differ by worker; live proof also differs by OS principal/UID, provider home, account; second VOID review blocks `review_not_independent` | mutable Worker row, same identity, extra review record/Attempt, impact, actor, or self-waiver cannot satisfy aggregation |
| adverse precedence | recoverable RATE_LIMITED/FAILED/LOST of any role requeues one same Job first; plan/work-repair/root exhaustion maps to its exact adverse reason; review failure uses one replacement or exhausts | omitted/repaired/aggregated adverse child, stale root handoff requeue, undefined fatal branch, or new dispatch before eligible requeue refuses |
| blocked event | every block is one idempotent `COO_CYCLE_BLOCKED` from the exact closed reason enum, including plan/child/aggregation adverse, review exhaustion, and repair exhaustion | prose/inbox selection or same command with another reason cannot alter transition |
| aggregation handoff | one immutable content-addressed provider-neutral event freezes current revisions, supervisor receipts, grants, and qualifying approvals while root remains queued | living/adverse child, missing approval, stale lineage/grant/handoff, mutable identity, or partial repair blocks handoff/dispatch |
| aggregation Attempt | exact root runs as a fresh command-bound real Attempt with exact READ grant; ordinary `complete_job`/`JOB_COMPLETED` follows terminal revalidation | pseudo-worker, cycle-authored result, no lease/snapshot, wrong handoff, or runtime-refusal bypass refuses |
| v4 backup/migration | quiesced verified+drilled v3 backup precedes atomic migration; v3 stays untouched on failure; immediate verified+drilled v4 backup follows; TX-9 and forward-fix hold | in-place partial migration, downgrade/deletion rollback, writer race, undrilled backup, OHF-state loss, or parity mismatch refuses resume |
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
  tests/test_ceo_intent.py
python3 scripts/ci_pytest.py
python3 -m compileall -q control_plane scripts
git diff --check
```

A fresh independent reviewer must first re-review these exact bytes and write
`PASS`, explicitly closing every design blocker. Implementation review must then
inspect authority parsing, direct Runtime bypass
attempts, role-result discrimination, revision lineage, reservation arithmetic,
launch-attested principal snapshots, crash boundaries, batch atomicity, exact-ID
containment, and the absence of model/provider/host side effects. Green happy-path
tests alone are insufficient.

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
5. every real supervisor Attempt seals its immutable effective grant, placement,
   and fixture launch-attested principal snapshots; the supervisor preserves the
   full raw role body/digest and authors validation/artifact receipts;
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
12. the fresh-v4 and populated-v3→v4 paths, pre/post verified restore drills,
    failure-untouched v3, forward-fix, and OHF TX-9 behavior pass.

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
  including effective-grant/placement/principal, admission, handoff, and
  command-replay digests;
- verified/drilled pre-migration v3 and post-migration v4 backup receipts, fresh
  versus migrated schema parity, failure-untouched proof, and OHF TX-9 proof;
- explicit confirmation that no host/provider/Wake/MCP/OHF-activation/production
  dispatch action ran;
- explicit remaining gates from §11; and
- rollback: revert the Phase 1F-C commit and keep the cycle uninvoked/unarmed;
  no data migration rollback may delete existing runtime evidence.

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
- the exact release's v3→v4 quiesce, pre/post verified restore drills, schema
  parity, and OHF TX-9 evidence pass before orchestration writers run.

### G2 — live worker composition

- builder and reviewer worker IDs are registered through reviewed host config;
- each has a distinct accepted OS principal, provider home, and account label;
- immutable worker/quota provider/account triggers and provider-equality checks
  are installed and proven;
- their completing Attempts contain immutable launch-attested execution-principal
  snapshots matching placement snapshots and those accepted identities;
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
   placement snapshot, and launch-attested principal snapshot
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
