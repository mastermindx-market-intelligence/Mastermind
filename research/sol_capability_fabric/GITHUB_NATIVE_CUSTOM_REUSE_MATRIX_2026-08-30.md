# Sol Capability Fabric GH0 — GitHub Native / Custom / Never-Build Matrix

**Operation:** `mastermind-sol-capability-fabric-gh0-20260830-sol-001`  
**Protected source:** `mastermindx-market-intelligence/Mastermind@98bc7a71dcd70947c7a18eb5af7493a2f62a2571`  
**Cognition route:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`

This matrix decides where Mastermind should reuse the **Native GitHub connector**, where it needs one
small custom semantic owner, and what it must never build. GH0 installs no app, connector, credential,
runner, workflow, service or actuator and contains no runtime implementation or GitHub mutation.

GitHub remains implementation/evidence truth. Mastermind adds company semantics around GitHub; it does
not copy GitHub into another truth store.

---

## 1. Decision rule

Use the native GitHub actuator when all of the following hold:

1. GitHub already owns the fact or effect;
2. the target is exact and closed;
3. the native function exposes the required precondition or read-back;
4. no cross-owner semantic join is needed to understand the result;
5. current organizational authority is independently established.

Add a custom Mastermind semantic layer only when the missing capability is one of:

- stable operation-to-GitHub identity;
- source-attributed multi-resource composition;
- company release/collision/completion law;
- current-source revalidation;
- owner-specific prepared-action validation;
- effect reconciliation;
- runner/host explanation through existing owners.

A custom layer may not become a second lifecycle, repository, PR, check, review, action, credential,
runner or audit-log store.

---

## 2. Reuse matrix

| Job | Native GitHub connector | Mastermind custom semantics | Ruling |
|---|---|---|---|
| Read repository/default branch/protected SHA | yes | source attribution, freshness and operation relation | Native read + thin status projection. |
| Read branch/head/base/compare | yes | exact carrier and current-writer interpretation | Native read + GH1 assessment. |
| Read commit/file/diff/patch | yes | expected-path and owner collision law | Native read; do not duplicate content. |
| Search PRs/issues/commits/code | yes | completeness/truncation and operation-carrier conflict | Native search + explicit `PARTIAL/UNKNOWN` when coverage is incomplete. |
| Read PR reviews/threads/comments | yes | exact-head binding and unresolved-blocker interpretation | Native read + GH1. |
| Read checks/runs/jobs/logs/artifacts | yes, bounded | required-check, supersession, attempt and pagination semantics | Native read + GH2 gather; do not mirror Actions. |
| Request reviewers | yes | current authority and exact-head/role separation | Native W1 action. |
| Submit PR review | yes | prepared exact-head review contract | Native W1/W2 action. |
| Rerun one failed job | yes | workflow diagnosis, accepted retry unit and effect reconciliation | Native W1 action after GH2 preparation. |
| Merge a PR | yes, with `expected_head_sha` | complete release assessment, prepared token, current-source reread and post-effect reconciliation | Native expected-head merge; never generic auto-merge. |
| Draft-to-ready | exposed but currently broken | detect connector defect and select a separately approved native route | Do not call the broken connector path repeatedly. |
| Repository merge policy | native/admin endpoint exists | reuse `scripts/github_estate_governance.py` closed interlock | A3-only, one exact family. |
| Actions default permissions | native/admin endpoint exists | reuse existing stateless ETag/`If-Match` helper | A3-only, one exact family. |
| Secret scanning enablement | native/admin endpoint exists | reuse existing bounded helper | A3-only; no secret value enters model context. |
| App installation/audit/credential administration | not safely exposed | future isolated A3 owner if explicitly approved | Assessment-only now. |
| Runner inventory/group/label/busy state | not exposed by current connector | SCF-RUN1 joins GitHub runner metadata with accepted host owners | Separate read-only observatory. |
| Stable operation evidence | no closed semantic join | GH2 `operation_evidence` over GitHub facts | Custom pure composition, no store. |
| Collision/release classification | no | GH1 pure engine | Custom pure deterministic assessment. |
| Production proof/completion validity | GitHub alone is insufficient | GH1 consumes explicit production-proof facts from canonical owners | Never infer `PROVEN_LIVE` from merge/CI. |

---

## 3. Existing owners to extend, not replace

### 3.1 Native GitHub connector

The Native GitHub connector remains the preferred transport for repository, PR, review, check,
workflow and expected-head merge operations. GH2 should call native functions rather than building a
parallel GitHub client unless a specific required native function is absent and the accepted app
owner supplies a narrower reviewed endpoint.

Technical permission is not organizational authority. Connector app identity, user identity, OAuth
scope and repository access are input evidence; none elects Sol, assigns a worker or authorizes a
release.

### 3.2 Existing administration interlock

Reuse:

```text
scripts/github_estate_governance.py
tests/test_github_estate_governance.py
```

The helper is valuable because it already provides:

- three exact allowlisted administration families;
- full before-document digest;
- strong ETag and `If-Match` precondition;
- at-most-one mutation;
- fixed read-back;
- idempotent `ALREADY_CONFIGURED`;
- `EFFECT_UNKNOWN` without blind retry;
- secret-shaped field rejection.

Do not move this logic into GH1. GH1 has no network or mutation. Do not expand the helper into generic
GitHub administration, desired-state reconciliation or a policy database.

### 3.3 Code Intelligence Fabric

The protected **Code Intelligence Fabric** owns company-wide discovery and exact-worktree semantics.
Its accepted composition is:

```text
codeDiscovery / codeSemantics
-> exact local Git
-> GitHub canonical verification
```

SCF GitHub work must preserve that boundary:

- CodeIntel may locate likely files, symbols and owners;
- exact local Git verifies candidate bytes/worktree state;
- GitHub verifies protected/default/candidate refs, PRs, reviews and checks;
- neither system absorbs the other;
- negative discovery is never authoritative without coverage/freshness proof.

Do not build another global index, semantic search plane or worker-wide GitHub MCP inside GH1/GH2.

### 3.4 Executive OS, Agent OS and RuntimeBinding

- Executive OS owns Job/Attempt/Worker/Event and CEO admission.
- Agent OS owns durable responsibility/decision/discovery/handoff.
- RuntimeBinding/SessionTargetRegistry own current exact reasoning/worker surface.
- GitHub owns implementation/evidence.

An operation-to-GitHub join references these owners; it does not copy their state into GitHub or let a
PR title create a lifecycle.

---

## 4. Native action contract

### 4.1 Expected-head merge

The native merge actuator is retained. The accepted flow is:

```text
GH2 current read
-> GH1 assessment = ELIGIBLE
-> owner-specific prepared action
-> current-source and expected-head reread
-> one native expected-head merge request
-> read merged PR/resulting commit
-> APPLIED | NOT_APPLIED | EFFECT_UNKNOWN
```

A moved head, changed source law, new blocking review/thread, failed/cancelled/superseded check,
material path collision, missing production proof or unknown source blocks commit.

### 4.2 Review and reviewer requests

Use native reviewer request and review submission. A requested reviewer is not an approval. A review
must carry the exact head/commit identity. Builder, reviewer, landing coordinator and final acceptance
remain distinct responsibilities.

### 4.3 Workflow rerun

Use the native exact-job or failed-jobs rerun only when `workflow_diagnosis` proves:

- the exact current head still owns the run;
- the retry unit is terminal and retry-permitted;
- the failure is not caused by supersession/current-source movement;
- no prior retry effect is unknown;
- one retry is within current operation authority.

Read canonical run/job state after the request. Never rerun merely because a check is red or queued.

### 4.4 Read-back reconciliation

Every modifying action uses GitHub canonical state for read-back reconciliation. A client timeout,
connector exception or malformed response is not proof of failure. The same carrier remains bound
while the effect is `EFFECT_UNKNOWN`; no second actuator or manual failover is allowed until
reconciled.

---

## 5. Custom semantic responsibilities

### GH1 — pure release/collision assessment

A pure deterministic function consumes already-acquired immutable facts and emits
`ELIGIBLE | HELD | REFUSED | UNKNOWN`, exact issues, source references and a canonical digest. It has
no network, mutation, credential or persistent state.

### GH2 — live composition and guarded native actions

GH2 gathers GitHub facts, emits `mastermind.github_status.v1`, invokes GH1 and, only under a separate
prepared contract, performs one native action. It does not become a generic action router.

### RUN1 — runner observatory

RUN1 reads exact runner metadata through approved GitHub/host owners and explains eligibility,
pressure and queue state. It performs no registration, deletion, relabeling, regrouping, token
generation, host enrollment or scheduler work.

---

## 6. Never-build ledger

The following surfaces are `REJECTED_BY_DESIGN`:

- a **super GitHub MCP** exposing arbitrary endpoint families;
- a **generic GitHub endpoint actuator** accepting method/URL/body;
- a second PR database;
- a second issue database;
- a second review or reviewer registry;
- a second check-run store;
- a second workflow/run/job/artifact store;
- a second runner inventory or scheduler database;
- a durable cross-owner prepared-action database;
- a universal action router shared by incompatible owners;
- a plugin credential or installation-token store;
- a model-selected repository;
- a model-selected branch writer;
- a model-selected credential, installation, technical principal or runner token;
- a branch election service based on recency, title or prose;
- an automatic base-chase loop;
- an auto-merge path that bypasses current-source adjudication;
- a GitHub-derived Executive lifecycle;
- a CodeIntel duplicate index/search/semantic plane.

---

## 7. Deletion and subtraction rule

A future custom component survives only if it supplies a proven semantic or safety capability that
native GitHub cannot. After GH2/CANARY evidence:

- delete wrappers that only rename native GitHub fields;
- keep pure GH1 only if it catches real release/collision/completion errors;
- keep prepared/effect wrappers only for consequential actions that demonstrate reduced ambiguity;
- keep RUN1 only if it explains real queues better than raw job state;
- never retain a custom service merely because it was expensive to build.

The target is a smaller, safer control surface: native GitHub for GitHub facts/effects, Mastermind only
for the missing company semantics.
