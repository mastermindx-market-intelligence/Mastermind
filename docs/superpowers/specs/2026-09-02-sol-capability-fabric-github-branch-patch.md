# SCF-GHP1 — Strict GitHub Branch-Patch Capability

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Sole source carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Protected pickup basis:** `mastermindx-market-intelligence/Mastermind@068b83883915919802894fc9c31e7e7757100eb9`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Parent:** protected Sol Capability Fabric F0/GH0; consume SCF-GH1 when protected  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**Source capability after this wave:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

This wave closes the source-side kernel and freezes the live owner contract for surgical repair of an
already-bound GitHub feature branch. It creates no installed ChatGPT app, OAuth client, GitHub App,
credential, tunnel, Executive Job, worker, RuntimeBinding, Wake obligation, branch commit through the
new capability, deployment, or production write capability.

---

## 1. Chairman outcome and user job

A Chat-native CEO Sol that can identify a precise five-line repair in a 10,000-line source file should
not have to reconstruct the complete file from a truncated connector response or dispatch a repository
worker solely for access to a safe editing primitive.

The target journey is:

```text
Sol identifies a bounded repair on an existing operation-owned feature branch
-> owner resolves exact repository / PR / branch / writer / allowed paths
-> owner fetches exact full blobs outside model context
-> strict pure kernel applies the tiny patch with zero fuzz
-> Sol receives a bounded preview and confirms one prepared effect
-> GitHub owner atomically commits against the exact expected branch head
-> canonical GitHub read-back returns APPLIED | NOT_APPLIED | EFFECT_UNKNOWN
-> CI/review/production acceptance remain separate gates
```

The capability supplies **surgical hands, not an ambient terminal**. Complex implementation,
diagnosis, refactoring, broad multi-file work, or any operation that cannot satisfy the narrow patch
fence continues through a repository-native worker and the existing Executive/Capacity fabric.

---

## 2. Current-state ruling

```text
Native GitHub repository/file/PR reads              PROVEN_LIVE technical surface
Native complete-file create/update                  PROVEN_LIVE technical surface
Safe model-side large-file reconstruction           REJECTED_BY_DESIGN
Direct write-side unified-diff application          NOT_BUILT before GHP1
SCF-GH0 contracts                                    SPEC_ONLY / PROTECTED
SCF-GH1 pure release assessment                      BUILT_NOT_PROVEN / OPEN DRAFT carrier
GHP1 strict patch kernel                             BUILT_NOT_PROVEN / PRODUCTION_INERT after source proof
Live owner prepare/commit/reconcile adapter          NOT_BUILT in GHP1
Installed ChatGPT Business GitHub action app         NOT_BUILT in GHP1
Real >10,000-line branch canary                       NOT_BUILT in GHP1
```

The current connected GitHub update-file action requires complete replacement content. That is useful
for small fully observed files but unsafe when the model has only a truncated representation. The
missing capability is not more context and not a generic shell. It is server-side exact-blob
materialization plus a bounded owner-native branch commit.

---

## 3. Canonical ownership and no-rebuild boundary

| Fact/effect | Canonical owner |
|---|---|
| operation, Job, Attempt, Worker, Event, lease/fence, retry | Executive OS |
| durable workstream/decision/discovery/handoff | Agent OS |
| repository, branch, blob, commit, PR, review, check and diff truth | GitHub |
| operation-to-carrier and current-writer interpretation | accepted SCF GitHub semantic owner |
| exact model-facing Sol action target when required | existing Sol action-target owner |
| OAuth/resource authentication | accepted Business auth stack |
| patch preparation/commit/reconciliation | privilege-separated GitHub owner app |
| worker placement | Capacity / Model Router |
| production evidence | the relevant production owner |

GHP1 creates no database, queue, scheduler, branch registry, operation registry, retry service,
prepared-action store, GitHub mirror, second PR store, second lifecycle, model-selected credential, or
model-selected branch writer.

The following remain `REJECTED_BY_DESIGN`:

- arbitrary shell, Git command, filesystem root, HTTP method/URL/body, SQL, browser command, or generic
  GitHub endpoint actuator;
- patching protected/default branches;
- branch creation, reset, force push, rebase, merge, rename, delete, mode change, symlink, submodule,
  binary file, archive, generated-data dump, or credential file through V1;
- fuzzy hunk placement, offset search, three-way merge, automatic conflict resolution, or silent base
  chase;
- choosing a repository, PR, branch, technical principal, installation, token, or writer from model
  text, title similarity, newest activity, or responsiveness;
- automatic fallback from the GitHub owner to a worker, CLI, browser, or another app after an uncertain
  effect.

---

## 4. Experience contract

### 4.1 Model-visible prepare input

The future tool is owner-specific:

```text
prepare_branch_patch(
  operation_key,
  expected_head_oid,
  files[] = {
    path,
    expected_blob_oid,
    unified_diff
  }
)
```

The model does **not** supply repository, branch, installation, credential, API URL, commit author,
worktree, local path, merge method, force flag, or allowed-path policy. The GitHub owner resolves those
from the exact accepted operation/carrier and current writer evidence, then injects them into the pure
kernel.

Preparation has no GitHub effect. It returns a secret-free bounded preview:

```text
schema = mastermind.github_branch_patch_preview.v1
operation_key
repository
branch
expected_head_oid
files[]:
  path
  expected_blob_oid
  before_sha256
  after_sha256
  patch_sha256
  before_bytes
  after_bytes
  additions
  deletions
  hunk_count
total_additions
total_deletions
normalized_effect_digest
preview_state = READY | BLOCKED | UNKNOWN | REFUSED
issues[]
prepared_token | null
expires_at | null
```

Raw full-file content is never returned to the model merely to support the write. The exact patch is
already caller-authored and bounded; receipts carry only metadata/digests unless an independently
approved inspection tool returns a small source range.

### 4.2 Prepared token

The live GitHub owner app issues an authenticated self-contained expiring token only for `READY`.
It binds at least:

```text
owner app id / generation / schema digest / policy id
authenticated principal digest
current Chairman-intent/action-target evidence digest when required
operation key and exact carrier identity
repository / PR / feature branch
protected/default branch identity
expected branch head OID
exact allowed paths
per-file expected blob OID
canonical bounded unified diffs and patch digests
before/result content SHA-256 digests
normalized effect digest
privilege = W2_CONSEQUENTIAL
issued_at / expires_at
reconciliation family
```

There is no prepared-action database. Commit re-fetches current owner facts and blobs, reruns the pure
kernel, and requires exact equality with every token-bound digest before one native request.

### 4.3 Commit input

```text
commit_branch_patch(prepared_token)
```

Commit accepts no replacement target or patch fields. The owner:

1. reauthenticates the same principal and verifies app/policy generation;
2. re-establishes current Chairman intent and exact Sol action target where required;
3. re-resolves the same unique operation/carrier/current writer;
4. proves the target is the same non-protected feature branch;
5. proves current branch head and every blob OID equal the token;
6. reruns strict patch preparation and verifies result/effect digests;
7. proves no prior unresolved effect for the same operation/effect;
8. obtains required native ChatGPT confirmation;
9. issues at most one owner-native atomic branch commit guarded by the expected head;
10. performs canonical read-back.

The preferred GitHub actuator is the owner-native atomic create-commit-on-branch operation with an
expected-head predicate and complete server-materialized resultant file contents. If the accepted
native connector later exposes an equivalent atomic primitive, reuse it. Do not add a generic GraphQL
or REST proxy.

### 4.4 Reconciliation

```text
reconcile_branch_patch(operation_key, normalized_effect_digest)
```

Reconciliation reads only. It checks the exact branch, commit/tree and target file digests and emits:

```text
NOT_APPLIED
  canonical evidence proves the expected old head still applies and no exact effect exists

APPLIED
  canonical GitHub evidence proves the exact resulting commit/tree/file digests

EFFECT_UNKNOWN
  a request may have crossed the effect boundary and current GitHub evidence cannot prove either state
```

`EFFECT_UNKNOWN` binds the same operation/carrier and blocks resend, worker dispatch, alternate app,
manual CLI repair, branch reset, or account failover until resolved. A timeout or client cancellation is
never proof of `NOT_APPLIED`.

---

## 5. GHP1 pure kernel contract

`control_plane/github_branch_patch.py` is deliberately pure. Its public entry point is:

```python
prepare_branch_patch(
    request: BranchPatchInput,
    materialized_files: Mapping[str, MaterializedFile],
    *,
    allowed_paths: Iterable[str],
    protected_branches: Iterable[str],
) -> BranchPatchPreparation
```

The live owner supplies exact full text and observed Git blob OIDs after canonical GitHub reads. The
kernel:

- verifies closed operation/repository/branch/head/file identities;
- refuses protected branches and paths outside the owner-supplied exact allowlist;
- verifies the observed Git object ID against both the expected OID and supplied bytes;
- accepts only existing non-empty UTF-8/LF text with a final newline;
- accepts only minimal exact-path unified diffs;
- applies hunks at the declared line with exact old/context equality;
- performs no fuzzy search, offset, three-way merge, or conflict repair;
- rejects malformed counts, mismatched new positions, overlapping hunks, pure unanchored insertions,
  no-op patches, high-confidence secret-shaped additions and every bounded-limit breach;
- returns complete resultant content only to the owner process and a model-safe metadata projection;
- produces deterministic order-stable SHA-256 effect identity.

### V1 ceilings

```text
files per effect                    3
patch bytes per file                65,536
patch bytes total                   131,072
source/result bytes per file        4 MiB
hunks per file                      100
changed lines per file              2,000
changed lines total                 4,000
path ownership                      exact owner-supplied files only
source kind                         existing UTF-8 LF regular file with final newline
branch                              existing non-protected feature branch only
native mutation attempts            0 during prepare; at most 1 during commit
```

These are ceilings, not targets. The live owner may apply stricter operation-specific limits.

---

## 6. Data, time, null and correction law

- GitHub OIDs and branch heads are immutable identity predicates, not advisory labels.
- SHA-256 content/effect digests supplement GitHub identity; they never replace canonical GitHub refs.
- Repository/branch/allowed-path facts are server-resolved; missing or conflicting facts are not empty
  defaults.
- `None`, truncated source, partial file coverage, unknown object kind, unavailable branch protection,
  or ambiguous writer/carrier yields `UNKNOWN`/refusal and zero mutation.
- The pure kernel has no clock. The live owner supplies current observations and enforces token expiry
  with a monotonic/server clock.
- Corrected source is re-read from GitHub. The owner never edits a prepared envelope to chase a moved
  head; a changed semantic effect requires a new explicit operation/effect preparation after the old
  effect is proven `NOT_APPLIED` or otherwise reconciled.
- Same operation key plus same normalized effect is duplicate reconciliation, not another commit.
- Same operation key plus changed normalized effect is `OPERATION_KEY_CONFLICT`.

---

## 7. Failure vocabulary

Minimum stable failures for the live family:

```text
CAPABILITY_UNAVAILABLE
PRODUCTION_DISARMED
AUTHENTICATION_REFUSED
ORGANIZATIONAL_AUTHORITY_REFUSED
ACTION_TARGET_UNRESOLVED
OPERATION_NOT_FOUND
OPERATION_CARRIER_CONFLICT
CARRIER_WRITER_CONFLICT
PATCH_TARGET_NOT_OWNED
PROTECTED_BRANCH_REFUSED
BRANCH_HEAD_MOVED
BLOB_OID_MOVED
SOURCE_TRUNCATED_OR_UNAVAILABLE
SOURCE_KIND_REFUSED
PATCH_SCHEMA_INVALID
PATCH_LIMIT_EXCEEDED
PATCH_CONTEXT_MISMATCH
PATCH_NO_EFFECT
PATCH_SECRET_SHAPE_REFUSED
PREPARED_TOKEN_INVALID
PREPARED_ACTION_EXPIRED
APP_GENERATION_MISMATCH
PRECONDITION_CHANGED
PRIOR_EFFECT_UNKNOWN
NATIVE_REQUEST_REFUSED
EFFECT_UNKNOWN
RECONCILIATION_REQUIRED
```

Errors never reflect full source, credentials, opaque GitHub responses, authorization headers,
tracebacks, private host paths, or arbitrary exception text to the model.

---

## 8. Security/threat model

The main threats are:

1. truncated source causing destructive whole-file replacement;
2. stale head/blob causing a correct patch to hit the wrong revision;
3. LLM-supplied path or branch escaping the commissioned surface;
4. fuzzy application changing a similar but incorrect block;
5. prompt-injected PR text widening repository/branch/authority;
6. a patch smuggling credentials or unsupported binary/mode changes;
7. lost response causing duplicate commit through retry/failover;
8. a generic API client becoming ambient GitHub administration;
9. a technically valid patch being called accepted/live without CI, review or production proof.

Controls are exact owner resolution, closed schemas, full server-side blob reads, Git object verification,
strict context application, protected-branch refusal, owner-supplied exact path allowlists, bounded
inputs/outputs, app-generation attestation, prepared tokens, expected-head atomic commit, canonical
read-back, effect reconciliation, and separate release/production acceptance.

---

## 9. Discriminating source tests

GHP1 must prove at least:

- a tiny interior repair applies exactly inside a source file exceeding 10,000 lines;
- prefix/suffix and full resultant content remain exact;
- full source/result content is absent from the public receipt;
- file ordering cannot alter the normalized effect digest;
- protected branch, traversal, backslash, `.git`, unowned path and duplicate path refuse;
- expected/observed/computed blob disagreement refuses;
- wrong context or line offset never fuzz-applies;
- malformed counts, new position mismatch, overlapping hunks and unanchored insertion refuse;
- CRLF, NUL, missing final newline, unsupported header/path and no-op patch refuse;
- high-confidence secret-shaped added material refuses without reflection;
- size/hunk/change ceilings fail closed;
- AST/import proof establishes no filesystem, network, subprocess or clock dependency.

Green source tests establish only `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

---

## 10. Fastest completion DAG

### GHP1 — this carrier: strict kernel + architecture freeze

Expected paths:

```text
control_plane/github_branch_patch.py
tests/test_github_branch_patch.py
docs/superpowers/specs/2026-09-02-sol-capability-fabric-github-branch-patch.md
```

Stop after exact-head tests, repository/security CI and independent review. Do not install or arm an
app in this source carrier.

### GHP2 — live GitHub owner app source

After SCF-GH1 is protected or current Sol adjudication proves its consumed interface stable, extend the
accepted Business OAuth/app stack with one privilege-separated GitHub app generation:

```text
integrations/mastermind_github_app/schemas.py
integrations/mastermind_github_app/adapter.py
integrations/mastermind_github_app/github_port.py
integrations/mastermind_github_app/server.py
tests/test_mastermind_github_app.py
```

Implement only `prepare_branch_patch`, `commit_branch_patch`, and
`reconcile_branch_patch`. Consume GHP1 as the sole patch law and GH1 as the sole release/collision law;
do not fork either. Use an injected short-lived GitHub installation-token provider hidden from model
arguments/results. Remain production-disarmed.

### GHP3 — isolated app enrollment and proof

Create/install the exact app generation with minimum repository contents/metadata permission required
for the bounded owner. Keep administration in the isolated A3 path. Prove schema/app/build/policy
digests, principal/scopes, secret-free model results, protected-branch denial and production-disarmed
refusal.

### GHP4 — real >10,000-line branch canary

On one disposable non-protected branch and test-only file:

1. prepare and commit a tiny interior repair;
2. prove unchanged prefix/suffix and exact result/tree digests;
3. prove stale expected head and stale blob both produce zero effect;
4. inject a lost-response case and prove reconciliation without resend;
5. repeat the same operation/effect and prove duplicate reconciliation, not a second commit;
6. prove unowned/protected/binary/symlink/secret-shaped cases refuse;
7. run exact CI and independent review;
8. remove/close the disposable carrier without rewriting history.

Only this real ChatGPT -> app -> GitHub path may promote the exact bounded branch-patch capability to
`PROVEN_LIVE`. It does not make arbitrary coding, merge, release, or production deployment live.

---

## 11. Routing and continuation

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: GHP2 is difficult, bounded, architecture-sensitive GitHub/OAuth/effect engineering after the
     product and authority boundaries are frozen.
WHY NOT FABLE: no principal-level product ambiguity remains; the source and adversarial contract are
               explicit and independently reviewable.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_DEPENDENCY until GHP1 release and GH1 interface reconciliation
```

No worker/session is assigned by this document. A later concrete placement requires fresh current
source, exact operation identity/carrier, pickup ACK, separate START, and reciprocal continuation. A
terminal result requires explicit Sol CONTINUE/REPAIR/STOP; silence is never terminal.

---

## 12. GHP1 stop and return contract

GHP1 is complete only when the three-path candidate has:

- exact current-base/collision reconciliation;
- focused tests and Python compile success;
- full hosted repository/security checks on the exact head;
- independent exact-head review validating strictness, purity, bounded limits and no duplicate owner;
- final Sol review against the Chairman outcome.

Merge protects source only. It does not install the app, authenticate a principal, mint a GitHub token,
perform a branch write, prove a canary, make a worker unnecessary for broad coding, or establish
`PROVEN_LIVE`.
