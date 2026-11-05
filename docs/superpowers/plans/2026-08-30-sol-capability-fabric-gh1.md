# SCF-GH1 — Pure GitHub Release and Collision Assessment Plan

**Parent program:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**GH0 operation:** `mastermind-sol-capability-fabric-gh0-20260830-sol-001`  
**Future GH1 operation:** `mastermind-sol-capability-fabric-gh1-20260830-sol-001`  
**Protected source at freeze:** `mastermindx-market-intelligence/Mastermind@98bc7a71dcd70947c7a18eb5af7493a2f62a2571`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**GH0 state:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

> **For the future builder:** implement GH1 test-first on one new carrier after GH0 is protected. This
> plan is not receiver assignment and creates no START.

---

## 1. Route

```text
PREFERRED_AVENUE: CTO Sol
WHY: difficult but frozen deterministic release/collision/completion semantics with hostile source,
      identity and current-head cases.
WHY NOT FABLE: product, owner and no-rebuild architecture is closed by SCF-F0/GH0; no principal
               cross-system ambiguity remains inside GH1.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

A concrete receiver is assigned only through current lawful placement. Before START it must ACK the
exact operation/carrier, read current protected source and GH0, arm/reuse one lawful continuation
source, re-run collision archaeology and emit a separate START.

---

## 2. Observable mission

Given one immutable plain-data packet describing a GitHub release candidate and its current
Mastermind source/production facts, emit one deterministic, source-preserving assessment:

```text
ELIGIBLE | HELD | REFUSED | UNKNOWN
```

with exact issues, collisions, completion validity, expected-head eligibility and canonical digest.
The same input in any mapping/list order must produce the same semantic result and digest.

The engine is **pure**: no network, no mutation, no filesystem discovery, no credential, no GitHub
connector import, no subprocess, no current-time call inside adjudication and no persistent state.

---

## 3. Why GH1 matters

The current native GitHub connector can read and modify exact resources, but the company still spends
frontier cognition repeatedly reconstructing release law from raw PR, path, check, review, source and
production facts. That creates three recurring risks:

1. a green or mergeable PR is mistaken for release eligibility;
2. a moved head, stale source law or operation collision is missed;
3. a merged implementation is called `PROVEN_LIVE` without the real consumer/production proof.

GH1 makes those deterministic gates executable without giving the model a broader actuator. It is an
assessment capability, not a release authority.

---

## 4. Authority and precedence

At future pickup, precedence is:

1. current live Chairman intent for the GH1 build;
2. current protected Mastermind and atomically loaded Skillpack;
3. protected SCF-F0 architecture/catalog/prepared-token correction;
4. protected GH0 estate/reuse/semantic records;
5. current existing canonical owner code and tests;
6. this plan;
7. implementation choices that do not contradict 1–6.

GitHub owns implementation/evidence truth. Executive OS owns lifecycle/admission. Agent OS owns
organizational responsibility. Production owners own production evidence. GH1 owns only a pure
classification over facts supplied by the caller.

---

## 5. Current capability state

```text
Native GitHub resource reads/writes                    PROVEN_LIVE technical surface
Current GitHub operation evidence join                 NOT_BUILT
Current pure release/collision assessment              NOT_BUILT
Current GitHub live status composer                     NOT_BUILT
Current prepared GitHub action executor                 NOT_BUILT
Current runner observatory                              NOT_BUILT
SCF-GH0 records                                         SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT
```

No existing current module was found that owns the exact GH1 semantic job. Fresh archaeology is still
required before the first write; if a current owner appears, extend/factor it instead of creating a
semantic twin.

---

## 6. Exact default scope

Unless current archaeology proves an accepted owner with a better location, the exact GH1 carrier is:

```text
control_plane/github_release_assessment.py
tests/test_github_release_assessment.py
docs/superpowers/plans/2026-08-30-sol-capability-fabric-gh1.md
```

The plan file may be updated only to record proven implementation facts discovered during the wave.
No fourth path without Meta-CEO reconciliation.

Explicit protected/no-edit families:

```text
control_plane/executive_runtime.py
control_plane/executive_service.py
control_plane/executive_worker_broker.py
control_plane/session_targets.py
control_plane/wake_*.py
scripts/github_estate_governance.py
any connector, OAuth, credential, service, workflow or deployment file
```

GH1 must not modify GH0 records merely to make tests pass; current protected records are inputs to
archaeology, not runtime dependencies.

---

## 7. Closed Python interface

Preferred public interface:

```python
from control_plane.github_release_assessment import (
    AssessmentInput,
    AssessmentIssue,
    AssessmentVerdict,
    GithubReleaseAssessment,
    assess_github_release,
)

result = assess_github_release(input_packet)
```

Implementation may use frozen dataclasses/enums or one equivalently closed typed shape. It must reject
unknown privileged fields rather than silently accepting an open dict that later callers can widen.

### 7.1 Input facts

The input contains only caller-acquired immutable/plain facts:

```text
schema/version
operation_key
repository
protected_ref / protected_sha
candidate_branch / candidate_sha
base_ref / base_sha
merge_base_sha
ahead_by / behind_by
expected_head_sha
expected_paths / actual_paths
expected_semantic_owners / current owner facts
carrier state and writer evidence
required checks / observed check-run-attempt facts
review submissions / decision / unresolved thread facts
current source-law compatibility facts
production-proof requirement and observed proof state
claimed capability state
allowed merge method
source refs / coverage / freshness
```

The engine must not parse GitHub URLs, PR descriptions, Slack text or model prose to create these
privileged facts.

### 7.2 Output

The result follows `mastermind.github_release_assessment.v1`:

```text
verdict
operation/repository/protected/candidate/expected-head identities
merge context
path/semantic/carrier/writer/check/review/source/production/completion states
expected_head_merge_eligible
sorted issues
sorted source refs
canonical_digest
```

The result never includes credentials, raw logs, full patches, arbitrary exception text or private
host paths.

---

## 8. Deterministic method

Adjudication order is fixed so multiple blockers do not hide one another:

1. validate closed schema and source completeness;
2. validate operation/repository/candidate/protected identities;
3. classify operation carrier and current writer;
4. validate current head/base/merge context;
5. compare expected and actual paths;
6. adjudicate semantic-owner collisions;
7. adjudicate check applicability, attempt and terminal state;
8. adjudicate reviews and unresolved threads;
9. adjudicate current source-law compatibility;
10. adjudicate production-proof requirement;
11. validate the claimed capability state;
12. validate requested merge method/effect ceiling;
13. choose verdict from the complete issue set;
14. produce canonical sorted serialization and SHA-256 digest.

No score, probability, hidden weight or LLM ranking is used. Priority cannot override a refusal.

---

## 9. Verdict law

### `ELIGIBLE`

Every required predicate is affirmatively true for the requested release effect. An eligible
**records-only PR** remains `SPEC_ONLY`; eligibility does not promote capability state.

### `HELD`

The exact carrier is valid and no hard contradiction exists, but a satisfiable gate remains pending,
such as current checks, required review, dependency order or required production proof.

### `REFUSED`

A hard contradiction exists, including moved/unexpected head, forbidden path/semantic collision,
operation/writer conflict, stale material source law, failed required check, blocking review, invalid
completion claim or forbidden merge method.

### `UNKNOWN`

One or more load-bearing sources are incomplete, stale, truncated, contradictory or unavailable.
Unknown fails closed.

---

## 10. Data, time, null and correction law

- Timestamps are supplied observations; the pure engine does not call `now()`.
- Owner-relative freshness is supplied as an explicit adjudicated fact or accepted age/budget pair.
- Missing is never false, zero, success or no-collision.
- `None` is accepted only where the schema explicitly permits absence; otherwise input is invalid.
- Check/run attempt identity is explicit; an older green run cannot satisfy a newer head.
- A corrected source is additive/superseding evidence. The caller supplies the current compatibility
  fact and both source refs when a dispute matters.
- `behind_by > 0` is not automatically refusal when accepted source law permits path-disjoint drift;
  the input must explicitly prove current merge/source compatibility. Otherwise GH1 returns
  `HELD`, `REFUSED` or `UNKNOWN` under the accepted current-base rule.
- A moved `candidate_sha != expected_head_sha` is always a hard refusal for expected-head commit.
- Production proof state is independent from GitHub check state.

---

## 11. Failure states

Minimum typed issues:

```text
INPUT_SCHEMA_INVALID
SOURCE_INCOMPLETE
SOURCE_STALE
SOURCE_CONFLICT
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
SOURCE_LAW_INCOMPATIBLE
PRODUCTION_PROOF_MISSING
PRODUCTION_PROOF_UNKNOWN
COMPLETION_CLAIM_OVERSTATED
MERGE_METHOD_REFUSED
PRIOR_EFFECT_UNKNOWN
```

Unknown enum values and duplicate conflicting source/check/review identities fail closed. They do not
fall into an `OTHER` bucket.

---

## 12. TDD sequence

### Task 1 — RED: closed input and deterministic identity

- [ ] missing required operation/repository/head/source fields reject;
- [ ] unknown privileged fields reject;
- [ ] duplicate conflicting source IDs reject;
- [ ] canonical serialization is permutation-stable;
- [ ] digest changes for every load-bearing semantic change.

### Task 2 — GREEN: minimal parser and canonicalizer

- [ ] typed enums/dataclasses;
- [ ] closed normalization;
- [ ] secret/private-path scan;
- [ ] deterministic sorted output.

### Task 3 — RED: head/base/path/carrier falsifiers

- [ ] exact current-base exact-path green records PR is eligible but remains `SPEC_ONLY`;
- [ ] moved candidate head refuses;
- [ ] material protected/source movement refuses;
- [ ] incomplete merge-base evidence is `UNKNOWN`;
- [ ] expected/actual path mismatch refuses;
- [ ] exact path overlap and semantic-owner overlap are separately visible;
- [ ] multiple plausible carriers return `OPERATION_CARRIER_CONFLICT`;
- [ ] current writer conflict refuses.

### Task 4 — RED: checks/reviews/source proof

- [ ] pending required check holds;
- [ ] failed required check refuses;
- [ ] cancelled required check is not green;
- [ ] superseded check is not applicable;
- [ ] partial pagination is `UNKNOWN` when a missing job/check can change result;
- [ ] changes-requested review refuses;
- [ ] unresolved required review thread holds/refuses per current law;
- [ ] source-law incompatibility refuses.

### Task 5 — RED: completion honesty

- [ ] green CI without required production proof cannot validate `PROVEN_LIVE`;
- [ ] merged implementation without real consumer proof remains `BUILT_NOT_PROVEN`/`PARTIAL`;
- [ ] records-only PR may be eligible while capability state remains `SPEC_ONLY`;
- [ ] required production proof missing holds;
- [ ] unknown production proof makes the assessment `UNKNOWN`;
- [ ] precise real-path proof can validate only the exact claimed capability.

### Task 6 — GREEN: complete assessment

- [ ] all issue types preserved and sorted;
- [ ] verdict derives from the whole issue set;
- [ ] `expected_head_merge_eligible` is true only for `ELIGIBLE` and exact head;
- [ ] no network/mutation imports;
- [ ] no repository/branch/credential selection.

### Task 7 — mutation/adversarial review

Mutants that must die:

- [ ] treat cancelled as success;
- [ ] ignore moved head;
- [ ] ignore semantic collision;
- [ ] choose newest carrier on conflict;
- [ ] call mergeable=true sufficient;
- [ ] equate green CI with `PROVEN_LIVE`;
- [ ] convert missing source into empty list;
- [ ] make digest order-dependent;
- [ ] allow `EFFECT_UNKNOWN` release.

---

## 13. Local and hosted proof

Required exact-head proof:

```text
python -m pytest -q tests/test_github_release_assessment.py
python -m py_compile control_plane/github_release_assessment.py tests/test_github_release_assessment.py
full relevant Mastermind test suite
hosted repository test
hosted security/code analysis required by protected master
exact changed-file census
independent exact-head adversarial review
```

The worker must also prove source purity mechanically: monkeypatch or AST/import tests should make any
network, subprocess, connector, filesystem discovery, clock or random dependency fail.

No live GitHub canary is owed by GH1 because live acquisition/effects belong to `SCF-GH2`.

---

## 14. Stop condition

**Stop at `BUILT_NOT_PROVEN / PRODUCTION_INERT`** after one pure exact-head implementation passes its
focused/full/hosted proof and independent review.

Do not:

- call the GitHub connector;
- implement `mastermind.github_status.v1` live gathering;
- implement prepared action or effect commit;
- merge a real PR;
- rerun a workflow;
- inspect/control runners;
- add a service, plugin or MCP app;
- start `SCF-GH2` or `SCF-RUN1`.

The worker returns head SHA, exact paths, RED→GREEN receipts, mutation/adversarial results, hosted
checks, source/collision movement, capability truth and the exact next release gate. Sol reviews and
lands separately.

---

## 15. Continuation after protection

Only after GH1 is protected:

- `SCF-GH2` may implement live exact GitHub gathering, status composition and one separately prepared
  native review/rerun/expected-head canary;
- `SCF-RUN1` may independently build the read-only runner observatory on disjoint paths;
- GH2 must consume GH1 as a pure library and must not fork its release law;
- RUN1 must not infer runner state from GH1 or duplicate GitHub workflow truth.

No successor inherits START from GH1.
