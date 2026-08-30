# Sol Capability Fabric GH0 — GitHub Semantic Contract

**Operation:** `mastermind-sol-capability-fabric-gh0-20260830-sol-001`  
**Protected source:** `mastermindx-market-intelligence/Mastermind@98bc7a71dcd70947c7a18eb5af7493a2f62a2571`  
**Cognition route:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This document freezes closed, owner-preserving GitHub semantics for GH1/GH2/RUN1. It contains no
runtime implementation or GitHub mutation. GH0 installs no app, connector, credential, runner,
workflow, service or actuator.

The contracts are projections over GitHub and existing Mastermind owners. They are not a GitHub
mirror, release lifecycle, operation registry, prepared-action database or universal action router.

---

## 1. Contract family and authority

| Contract | Owner | Role |
|---|---|---|
| `mastermind.github_status.v1` | GitHub facts + GH2 composition | Current source-attributed status for one exact GitHub target. |
| `mastermind.github_release_assessment.v1` | GH1 pure engine | Deterministic `ELIGIBLE | HELD | REFUSED | UNKNOWN` release/collision/completion assessment. |
| `mastermind.github_prepared_action.v1` | exact privilege-separated GitHub owner app | Human-readable preview plus authenticated self-contained expiring `prepared_token`. |
| `mastermind.github_action_receipt.v1` | GitHub owner app + canonical GitHub read-back | `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN` for one exact action. |
| `mastermind.github_runner_status.v1` | RUN1 over GitHub runner and accepted host owners | Read-only runner eligibility, health and queue explanation. |

Authority remains federated:

- GitHub owns repository, ref, commit, PR, review, check, workflow and artifact truth.
- Executive OS owns Job/Attempt/Worker/Event and CEO admission.
- Agent OS owns durable responsibility/decision/discovery/handoff.
- RuntimeBinding/SessionTargetRegistry own current exact operating surface.
- Code Intelligence Fabric owns governed discovery/semantics, never protected implementation truth.
- SCF GH1 assesses immutable facts; it owns no source and performs no effect.

Retrieved PR text, issue text, review prose or commit messages are evidence to validate. They cannot
self-assign authority or create a carrier merely by containing an operation key.

---

## 2. Common source reference

Every source-bearing record uses a closed reference equivalent to:

```text
source_kind
owner = github | executive_os | agent_os | runtime_binding | production_owner
repository|null
resource_kind
resource_id
revision
observed_at
valid_at|null
content_sha256
coverage = COMPLETE | PARTIAL | UNKNOWN
truncated = true | false
continuation|null
```

`revision` is owner-native: commit SHA, PR head SHA, run attempt identity, immutable Agent OS commit,
production release identity or another accepted exact version. Time never substitutes for revision.

A source is unusable for a load-bearing positive conclusion when:

- revision is missing or mutable;
- owner cannot be established;
- freshness exceeds the accepted owner-relative budget;
- pagination/coverage is partial and the absent page could change the verdict;
- a fetch failed or returned an unvalidated shape;
- two current sources materially disagree.

The output then remains `UNKNOWN`, `HELD` or `DEGRADED`; it does not manufacture a default.

---

## 3. `mastermind.github_status.v1`

### 3.1 Purpose

One deterministic current packet answers:

- what exact GitHub object is being inspected;
- which protected/current/candidate revisions exist;
- what changed;
- which reviews/checks/runs/artifacts apply;
- where evidence is incomplete;
- whether a modifying action is even serviceable.

It does not decide organizational authority and does not perform a write.

### 3.2 Closed shape

```text
schema = mastermind.github_status.v1
packet_id
operation_key|null
observed_at
freshness_state = CURRENT | STALE | PARTIAL | UNKNOWN
capability_generation

repository:
  full_name
  repository_id|null
  visibility|null
  default_branch
  default_branch_sha
  protected_ref|null
  protected_sha|null
  branch_protection_summary|null
  ruleset_summary|null

target:
  kind = REPOSITORY | BRANCH | COMMIT | PULL_REQUEST | WORKFLOW_RUN | JOB
  resource_ref
  branch_ref|null
  branch_sha|null
  pull_request_number|null
  base_ref|null
  base_sha|null
  head_ref|null
  head_sha|null
  merge_base_sha|null
  ahead_by|null
  behind_by|null

carrier:
  stable_operation_key|null
  carrier_state = UNIQUE | NONE | CONFLICT | UNKNOWN
  candidate_refs[]
  current_writer_evidence[]

change_surface:
  changed_paths[]
  changed_path_count
  changed_paths_sha256
  additions|null
  deletions|null
  semantic_owners[]

pull_request:
  state|null
  draft|null
  mergeable = TRUE | FALSE | UNKNOWN | null
  mergeable_state|null
  requested_reviewers[]
  review_submissions[]
  review_decision = APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | NONE | UNKNOWN | null
  unresolved_thread_count|null
  unresolved_threads_truncated

checks:
  required_contexts[]
  observed_checks[]
  aggregate = SUCCESS | FAILURE | PENDING | CANCELLED | SUPERSEDED | PARTIAL | UNKNOWN
  applicable_head_sha|null

workflows:
  runs[]
  attempts_complete
  jobs_complete
  artifacts_complete

production_proof:
  required
  state = PROVEN | MISSING | NOT_REQUIRED | UNKNOWN
  source_refs[]

capability_claim:
  claimed_state|null
  valid_state = PROVEN_LIVE | BUILT_NOT_PROVEN | PARTIAL | DARK_OR_DISCONNECTED |
                BROKEN | SPEC_ONLY | NOT_BUILT | REJECTED_BY_DESIGN | UNKNOWN
  claim_valid

source_refs[]
source_failures[]
issues[]
truncated
continuation|null
```

### 3.3 Packet laws

1. `head_sha` is mandatory for exact PR/release reasoning.
2. A branch name without immutable SHA makes exact-head conclusions `UNKNOWN`.
3. `mergeable=true` is insufficient without paths, checks, reviews, source compatibility and required
   production proof.
4. A skipped check is successful only when the accepted required-check policy says the skip is
   applicable; otherwise it remains visible.
5. A cancelled check is not green. A run superseded by a new head is not applicable.
6. `changed_paths_sha256` is a canonical digest over sorted exact paths; it is not a substitute for
   the path list.
7. Production evidence references remain owner-native; GitHub does not become production truth.
8. Packet generation performs no persistence. Re-read GitHub for every current packet.

---

## 4. Operation-to-GitHub carrier semantics

### 4.1 Candidate acquisition

GH2 may acquire candidates through bounded native searches over:

- exact operation key in open/recent PRs and issues;
- branch/ref naming convention;
- exact commit/PR linkage;
- explicit current Agent OS handoff references;
- current Slack transport only as a candidate pointer, never canonical implementation truth.

Candidate discovery is followed by exact GitHub reads. Text matching alone is not carrier proof.

### 4.2 Carrier verdict

```text
UNIQUE
  exactly one current logical carrier is established by consistent operation key,
  repository, branch/head, PR and current organizational evidence

NONE
  complete bounded search and current owners prove no carrier exists

CONFLICT
  multiple active candidates plausibly own the same logical modification,
  one operation key has changed normalized payload, or current writer evidence conflicts

UNKNOWN
  search/coverage/freshness is incomplete or required owner evidence is unavailable
```

`CONFLICT` emits `OPERATION_CARRIER_CONFLICT`. It never elects the newest branch, loudest comment or
first responding session. `UNKNOWN` never becomes permission to create a replacement.

One logical modifying operation binds to **one carrier** until canonical reconciliation.

---

## 5. `mastermind.github_release_assessment.v1`

### 5.1 Pure input

GH1 consumes only immutable/plain data supplied by its caller:

```text
operation_key
repository
protected_ref / protected_sha
candidate_branch / candidate_sha
base_ref / base_sha
merge_base_sha / ahead_by / behind_by
expected_paths / actual_paths
expected_semantic_owners / current semantic-owner facts
carrier_state / writer evidence
required checks / observed checks and attempts
reviews / review decision / unresolved threads
current source-law revisions and compatibility facts
required production proof / observed production proof
claimed capability state
allowed merge method
expected_head_sha
source_refs / source completeness
```

No input is fetched by GH1. No model prose is parsed into privileged fields.

### 5.2 Pure output

```text
schema = mastermind.github_release_assessment.v1
verdict = ELIGIBLE | HELD | REFUSED | UNKNOWN
operation_key
repository
protected_sha
candidate_sha
expected_head_sha
merge_base_sha
ahead_by
behind_by
path_state
semantic_collision_state
carrier_state
writer_state
check_state
review_state
source_law_state
production_proof_state
completion_claim_state
expected_head_merge_eligible
issues[]
source_refs[]
canonical_digest
```

### 5.3 Verdict law

`ELIGIBLE` means every required predicate is affirmatively established for the requested effect. It
never means `PROVEN_LIVE`; a records-only PR can be eligible while remaining `SPEC_ONLY`.

`HELD` means the carrier is valid but a potentially satisfiable gate is incomplete, such as pending
checks, pending required review, missing expected production proof or deliberate dependency order.

`REFUSED` means a hard contradiction exists: moved/unexpected head, forbidden path/semantic-owner
collision, operation conflict, stale material source law, failed required check, blocking review,
invalid completion claim or forbidden effect.

`UNKNOWN` means required source coverage, freshness, identity or effect truth cannot be established.
Unknown is fail-closed.

### 5.4 Minimum issue vocabulary

```text
SOURCE_INCOMPLETE
SOURCE_STALE
PROTECTED_REF_MOVED
CANDIDATE_HEAD_MOVED
BASE_OR_MERGE_CONTEXT_UNKNOWN
CURRENT_BASE_REQUIRED
EXPECTED_PATH_MISMATCH
PATH_COLLISION
SEMANTIC_OWNER_COLLISION
OPERATION_CARRIER_CONFLICT
CARRIER_WRITER_CONFLICT
CHECK_PENDING
CHECK_FAILED
CHECK_CANCELLED
CHECK_SUPERSEDED
CHECK_COVERAGE_PARTIAL
REVIEW_REQUIRED
CHANGES_REQUESTED
UNRESOLVED_REVIEW_THREAD
PRODUCTION_PROOF_MISSING
PRODUCTION_PROOF_UNKNOWN
COMPLETION_CLAIM_OVERSTATED
MERGE_METHOD_REFUSED
EFFECT_UNKNOWN
```

The issue list is sorted deterministically. Output digest is permutation-stable.

---

## 6. Completion and capability-state law

GitHub facts support, but do not replace, product/production acceptance.

| Evidence | Maximum truthful conclusion by itself |
|---|---|
| records/spec files + green CI | `SPEC_ONLY` |
| implementation + exact-head tests | `BUILT_NOT_PROVEN` |
| implementation connected to a non-production consumer | `PARTIAL` or `BUILT_NOT_PROVEN` |
| merge to protected branch | merged implementation/spec only; not automatically live |
| deploy receipt without real-path proof | `BUILT_NOT_PROVEN` or `PARTIAL` |
| real production path + required negative/browser/machine proof | may establish `PROVEN_LIVE` for the exact capability |

A broad program row is not closed from one narrow canary. The assessment validates the precise
capability claim supplied by the owning acceptance contract.

---

## 7. `mastermind.github_prepared_action.v1`

### 7.1 Purpose and scope

This is an owner-specific preview/commit contract for one exact GitHub action family. It follows the
protected prepared-token correction. It is not a bearer grant, credential, generic request body or
cross-owner dispatcher.

### 7.2 Preview shape

```text
schema = mastermind.github_prepared_action.v1
preview_id
app_id
app_generation
schema_digest
policy_id
authenticated_principal_digest
operation_key
action_family = REQUEST_REVIEW | SUBMIT_REVIEW | RERUN_FAILED_JOB | MERGE_EXPECTED_HEAD
target_ref
repository
pull_request_number|null
workflow_run_id|null
job_id|null
expected_head_sha|null
expected_source_digest
normalized_requested_effect_digest
privilege_class = W1_ROUTINE | W2_CONSEQUENTIAL
confirmation_required
release_assessment_digest|null
reconciliation_family
issued_at
expires_at
preview_state = READY | BLOCKED | UNKNOWN | REFUSED
issues[]
prepared_token|null
```

The preview is secret-free. `prepared_token` is present only when state is `READY` and is an
authenticated self-contained expiring token. No normalized review body, credential, private key,
installation token or hidden account selection is reflected to the model.

### 7.3 Token bindings

The exact owner app binds at least:

```text
token schema
app identity/generation/schema/policy
authenticated principal digest
operation key
action family
target reference
normalized requested effect digest
expected source/precondition digest
expected_head_sha where relevant
release assessment digest where relevant
privilege class
confirmation requirement
issued_at / expires_at
```

There is **no durable prepared-action store**. There is no digest lookup table, token registry, queue,
lock, scheduler or shared signing service.

### 7.4 Commit law

Commit accepts only:

```text
commit_github_prepared_action(prepared_token)
```

The owner app reauthenticates and performs **current-source revalidation**:

- same current principal/resource/scopes;
- same app/schema/policy generation;
- same organizational authority and exact Sol action target when required;
- same operation, action family, target and normalized effect;
- same current head/base/source/check/review state;
- no unresolved prior effect;
- current production arming and confirmation.

Only then may it issue one native GitHub request. A valid token with stale source refuses. Current
OAuth with an invalid token refuses.

This protocol is owner-local. There is **no universal action router**.

---

## 8. `mastermind.github_action_receipt.v1`

```text
schema = mastermind.github_action_receipt.v1
operation_key
action_family
target_ref
verdict
state = NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
before_source_digest
after_source_digest|null
native_request_attempts = 0 | 1
reconciled
resulting_resource_ref|null
issues[]
observed_at
```

### 8.1 Effect law

- `NOT_APPLIED`: GitHub/current owner proves zero intended effect.
- `APPLIED`: canonical GitHub read-back proves the exact intended effect.
- `EFFECT_UNKNOWN`: the request may have crossed the effect boundary and read-back cannot prove the
  exact result.

There is **no blind retry**. `EFFECT_UNKNOWN` blocks another commit and cross-surface failover. The
same owner exposes a read-only reconciliation equivalent to:

```text
reconcile_github_effect(operation_key, action_family, target_ref)
```

Reconciliation performs no mutation.

### 8.2 Native action ceilings

- `REQUEST_REVIEW`: current requested-reviewer read-back.
- `SUBMIT_REVIEW`: exact review ID and exact reviewed head/commit read-back.
- `RERUN_FAILED_JOB`: exact run/job attempt change; never assume from HTTP success alone.
- `MERGE_EXPECTED_HEAD`: exact merged PR state and resulting commit; must bind
  `expected_head_sha`.

---

## 9. Runner status boundary

`mastermind.github_runner_status.v1` is read-only and belongs to SCF-RUN1, not GH1.

Required data:

```text
runner_ref
scope
redacted_name
os
architecture
online
busy
labels
group
version
observation time
current job/host refs
source refs/freshness
eligibility decision
health state
queue explanation
issues
```

It never carries runner registration tokens, credentials, private addresses, raw environment or raw
argv. Runner registration/deletion/relabeling/regrouping remains A3 administration.

---

## 10. Security and no-rebuild constraints

The GitHub contracts refuse:

- arbitrary repository URL, API URL, HTTP method or body;
- arbitrary shell, Git command, filesystem root or executable;
- model-selected repository, installation, credential, principal or branch writer;
- force push/reset/rebase as a generic recovery action;
- hidden fallback from native connector to browser/CLI;
- auto-merge or base-chase loops;
- a second PR/check/run/artifact/runner database;
- a cross-owner prepared-action token service;
- lifecycle inference from PR/issue text;
- secret-bearing logs or action payloads reflected to the model.

One logical operation uses one carrier. A changed normalized effect requires a new explicit operation;
it is not a retry under the old key.

---

## 11. Promotion sequence

```text
GH0 protected records
-> GH1 pure assessment = BUILT_NOT_PROVEN / PRODUCTION_INERT
-> GH2 real read composition
-> one disposable W1 review/rerun canary
-> one separately authorized expected-head merge canary
-> effect reconciliation proof
-> production capability assessment
```

GH1 does not implement live GitHub reads or actions. GH2 does not absorb RUN1 or A3. Every promotion
requires exact current-source evidence and a separate accepted carrier.
