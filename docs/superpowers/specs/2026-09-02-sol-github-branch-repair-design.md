# Sol GitHub Exact Branch Repair — Architecture and Source Contract

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@068b83883915919802894fc9c31e7e7757100eb9`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1 from the same protected commit  
**Parent architecture:** Sol Capability Fabric F0 / GH0  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**Source state after this carrier:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

This carrier implements the pure exact-edit compiler and freezes the smallest live-app contract needed
to make a surgical repair to a large existing source file from ChatGPT. It creates no deployed MCP
app, GitHub App, credential, installation token, tunnel, Executive Job, worker, branch commit through
the new capability, protected-branch effect, or production proof.

---

## 1. Executive ruling

Add one narrow capability to the existing Sol Capability Fabric GitHub owner:

```text
EXACT_BRANCH_REPAIR
```

It is **not** a generic `apply_patch`, shell, filesystem writer, Git endpoint proxy, repository worker,
or universal action router. It exists for one job:

> Given one already-bound, open, non-protected GitHub pull-request branch and one or more exact unique
> old/new text replacements inside files that already belong to that PR, build the complete post-image
> server-side, preview it, and commit it once against the exact expected branch head.

The model never reconstructs the whole file. The model supplies only the exact local edit. The trusted
GitHub owner fetches the complete current file, compiles the post-image, and performs the owner-native
commit after a prepared-action gate.

This removes the current failure mode where ChatGPT knows the precise repair but can only call a
whole-file replacement action whose source response may be truncated.

---

## 2. Outcome and completion ruler

### Chairman/user job

From a ChatGPT Sol conversation, repair a small, unambiguous defect in a large in-flight source file
without copying a 10,000-line file into the model context or dispatching a repository worker solely to
obtain a patch primitive.

### Machine job

Convert a bounded exact replacement request into deterministic full-file post-images under exact
operation, carrier, branch-head, blob, path, size, encoding, and effect fences.

### 10/10 end state

```text
Sol inspects an exact PR target and nearby source context
-> proposes one or more exact old/new text replacements
-> receives a bounded preview and immutable compilation digest
-> confirms one prepared branch repair
-> owner app revalidates every source and authority predicate
-> one expected-head GitHub commit is attempted
-> canonical GitHub readback proves APPLIED, NOT_APPLIED, or EFFECT_UNKNOWN
-> CI/review proceeds on the normal PR carrier
```

Completion requires a real ChatGPT Business conversation to modify one unique line inside an existing
>10,000-line UTF-8 file on a disposable non-protected PR branch, prove byte-for-byte preservation of
all unrelated content, reject a stale-head control, and reconcile an injected ambiguous transport
control without a duplicate commit.

A pure compiler, green repository CI, published MCP schema, GitHub App installation, or successful
OAuth connection alone is not `PROVEN_LIVE`.

---

## 3. Current capability ledger

| Capability | Current state at pickup | This carrier |
|---|---|---|
| Native GitHub resource/PR/branch reads | `PROVEN_LIVE` technical surface | reused |
| Native connected whole-file UTF-8 update | `PROVEN_LIVE` technical surface / `PARTIAL` for large-file repair | not changed |
| SCF GH1 pure release/collision assessment | `BUILT_NOT_PROVEN / OPEN DRAFT CARRIER` | path-disjoint; not modified |
| Server-side exact replacement compiler | `NOT_BUILT` | implemented, `BUILT_NOT_PROVEN / PRODUCTION_INERT` |
| GitHub exact-repair prepared action | `NOT_BUILT` | contract frozen; runtime not built |
| GitHub expected-head exact-repair actuator | `NOT_BUILT` | contract frozen; runtime not built |
| ChatGPT custom MCP write action | `NOT_BUILT` | not installed or published |
| End-to-end large-file proof | `NOT_BUILT` | still owed |

The active GH1 carrier owns `control_plane/github_release_assessment.py` and
`tests/test_github_release_assessment.py`. This operation owns new, disjoint paths and does not modify
or bypass GH1.

---

## 4. One experience, federated authority

The capability extends existing owners only:

| Fact/effect | Owner |
|---|---|
| Chairman intent and Sol organizational authority | current live interaction + accepted company law |
| Job/Attempt/Worker/Event lifecycle | Executive OS |
| organizational workstream/decision/handoff | Agent OS |
| repository, PR, branch, blob, commit, checks | GitHub |
| operation-to-GitHub carrier assessment | SCF GitHub semantic owner |
| exact edit compilation | `control_plane.github_exact_edit` pure library |
| app identity/OAuth/resource authentication | existing Business MCP auth stack |
| GitHub technical credential and request | privilege-separated GitHub owner app |
| ChatGPT action confirmation | ChatGPT app action policy/runtime |
| merge/release/final acceptance | existing GitHub release and Sol acceptance path |

No owner is copied into a new lifecycle or database. The compiler stores nothing and performs no I/O.
The future MCP app is transport plus owner-specific policy; it never becomes repository truth.

---

## 5. Product flow

```text
ChatGPT Sol
  |
  | inspect operation / PR target and exact source range
  v
GitHub owner app — R0 read
  |
  | exact operation carrier, open PR, current writer, head, changed paths, blobs
  v
prepare_exact_branch_repair — W1 routine
  |
  | exact old_text/new_text blocks only
  v
pure exact-edit compiler
  |
  | complete source bytes stay server-side
  | unique exact match, no fuzz, deterministic full post-images
  v
prepared preview + owner-local expiring token
  |
  v
commit_exact_branch_repair(prepared_token)
  |
  | re-auth + re-read + revalidate
  | one GitHub createCommitOnBranch(expectedHeadOid=...)
  v
GitHub branch + PR
  |
  v
readback receipt: APPLIED | NOT_APPLIED | EFFECT_UNKNOWN
```

The branch repair is `W1_ROUTINE` because V1 is limited to an existing non-protected PR branch,
existing changed files, bounded exact replacements, no new/delete/rename/mode change, and a separate
merge/release gate. The app may still present a platform confirmation because it is a write action.

---

## 6. Why exact replacements, not an open patch language

V1 accepts closed records:

```text
path
expected_blob_oid
replacements[]:
  old_text
  new_text
```

Every `old_text` must be non-empty and occur exactly once in the complete current file. Replacements
must not overlap. All replacements are located against the same immutable original bytes and applied
from highest to lowest byte offset.

This is deliberately stricter than unified-diff or `git apply` semantics:

- no fuzzy context;
- no offset guessing;
- no three-way merge;
- no line-number-only targeting;
- no path headers interpreted from arbitrary patch text;
- no rename/delete/create/mode syntax;
- no shell or local worktree;
- no dependence on truncated model-visible file content.

Insertions use a unique surrounding block whose `new_text` includes the insertion. Deletions replace a
unique block with empty text. If the anchor is missing or non-unique, preparation refuses and Sol reads
more context before proposing a new zero-effect preparation.

---

## 7. Pure compiler contract implemented by this carrier

### Inputs

`ExactEditAuthority` is trusted, source-owned input and cannot be inferred from the edit request:

```text
operation_key
carrier_ref / source_ref
repository
short default branch / exact candidate branch
pull_request_number / OPEN state
branch_protected = false
carrier_state = EXACT
writer_state = EXACT
observed_head_oid
allowed_paths[] / allowed_paths_complete = true
```

`ExactEditRequest` is the bounded proposed effect:

```text
schema = mastermind.github_exact_edit.input.v1
operation_key
expected_head_oid
files[1..3]:
  path
  expected_blob_oid
  replacements[1..10]: old_text, new_text
```

`ExactFileSnapshot` is complete immutable source fetched by the owner:

```text
path
blob_oid
mode = 100644
content = complete bytes
```

The snapshot path set must exactly equal the request path set. Extra snapshots are refused so an
adapter cannot accidentally ingest unrelated source or secrets.

### Output

```text
schema = mastermind.github_exact_edit.compilation.v1
operation/carrier/repository/branch/PR identities
expected and observed head OIDs
files[]:
  path
  before blob/content digest and byte count
  after content digest and byte count
  canonical replacement ranges and digests
  bounded unified preview
  internal complete post-image
canonical_digest
```

`to_public_dict()` never includes a full post-image. `post_images()` is an in-process immutable mapping
for the owner-native commit adapter. The canonical digest binds all model-visible semantics and every
before/after content digest.

### Reviewed bounds

```text
files                         <= 3
replacements per file         <= 10
total replacements            <= 16
allowed PR paths              <= 256
source file                   <= 4 MiB
total source                  <= 8 MiB
one old-text anchor           <= 64 KiB
one new-text replacement      <= 128 KiB
total edit payload            <= 256 KiB
model-visible preview         <= 128 KiB
```

V1 accepts only existing `100644`, NUL-free, valid UTF-8 files with portable ASCII repository paths.
This covers the target large source-file repair while keeping the first actuator narrow.

---

## 8. Path and authority floor

The future live app resolves repository, branch, PR, technical principal, and credential from the
accepted operation/carrier owner. Those fields are not free model-selected tool arguments.

Every requested path must already appear in the open PR's complete current changed-path set. V1 is a
**repair path**, not a way to widen PR scope.

The compiler hard-refuses:

```text
.git/**
.github/**
docs/sol_skills/**
config/authority_map.yml
config/executive_agent_capabilities.json
.env / .env.*
credential/secret/private-key filename families
```

This prevents the repair tool from changing its constitutional procedure, capability grant, GitHub
workflow/administration, or obvious credential material. A later reviewed generation may add a closed
family; it must not silently loosen V1.

The following also refuse:

- default branch;
- protected branch;
- closed/merged/unknown PR;
- non-exact or conflicting carrier/current writer;
- incomplete changed-path coverage;
- moved branch head;
- moved target blob;
- path traversal, backslash, duplicate, absolute or noncanonical path;
- binary, symlink, executable, submodule, invalid UTF-8 or oversized file;
- secret-shaped old/new content or preview;
- empty, no-op, missing, non-unique, overlapping or oversized replacements.

---

## 9. Live prepared-action contract

The future owner app exposes three modifying-family tools and may reuse SCF R0 evidence reads:

```text
prepare_exact_branch_repair(request)
commit_exact_branch_repair(prepared_token)
reconcile_exact_branch_repair(operation_key, carrier_ref)
```

Preparation performs zero GitHub mutation. It resolves and re-reads the exact carrier, fetches full
blobs, calls the pure compiler, and returns:

```text
schema = mastermind.github_exact_branch_repair_preview.v1
preview_id
app_id / app_generation / schema_digest / policy_id
principal_digest
operation_key / carrier_ref
repository / branch / pull_request_number
expected_head_oid
per-file before_blob_oid / before_sha256 / after_sha256
bounded patch previews and stats
compilation_digest
privilege_class = W1_ROUTINE
confirmation_required
issued_at / expires_at
preview_state = READY | BLOCKED | UNKNOWN | REFUSED
issues[]
prepared_token|null
```

The token is authenticated, self-contained, owner-local, expiring, and secret-free. There is no token
registry, prepared-action database, lock, queue, scheduler, lifecycle, or shared company signing
service.

The token binds at least:

```text
app/schema/policy generation
principal digest
operation/action/carrier identity
repository / branch / PR
expected head OID
complete current PR changed-path digest
per-file path / before blob / before and after content digests
normalized exact replacements and compilation digest
commit message digest
privilege/confirmation requirements
issued-at / expiry
```

Commit accepts only the token. It does not accept a second patch payload that could differ from the
preview.

---

## 10. One owner-native commit

After revalidation, the preferred actuator is GitHub GraphQL `createCommitOnBranch`:

```text
branch.repositoryNameWithOwner = server-resolved repository
branch.branchName              = server-resolved short branch
expectedHeadOid                = token-bound current head
fileChanges.additions[]        = exact path + full base64 post-image
message                        = bounded token-bound commit message
```

GitHub documents that `expectedHeadOid` binds the prior branch head and that each file addition carries
the complete file contents. This is precisely why the app compiles the full post-image server-side.

Official references:

- https://docs.github.com/en/graphql/reference/commits
- https://docs.github.com/en/graphql/reference/git

There is no hidden fallback to REST Git Database, browser automation, local shell, another GitHub
principal, or a repository worker. If this mutation is unavailable, the action returns
`CAPABILITY_UNAVAILABLE` or the exact owner-native failure. A different actuator requires a separately
reviewed generation.

GitHub App installation authentication is preferred for the owner service. The installation must be
restricted to the intended repository and minimum required repository permissions; short-lived
installation access tokens remain server-side and never enter ChatGPT, logs, receipts, command argv,
or GitHub content.

---

## 11. Effect and reconciliation law

The receipt remains closed:

```text
schema = mastermind.github_exact_branch_repair_receipt.v1
operation_key / carrier_ref
expected_head_oid
resulting_head_oid|null
resulting_commit_oid|null
compilation_digest
native_request_attempts = 0 | 1
state = NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
reconciled
issues[]
observed_at
```

### `NOT_APPLIED`

Canonical GitHub state proves the exact commit did not occur—for example, precondition rejection while
the expected old head remains current and no commit carrying the operation/client mutation identity or
post-image digests exists.

### `APPLIED`

Canonical readback proves the branch advanced to the returned commit and every target path has the
exact token-bound post-image digest.

### `EFFECT_UNKNOWN`

The request may have crossed the effect boundary but exact branch/commit/blob readback is unavailable
or inconclusive. The operation remains bound to the same carrier and principal. No retry, browser/CLI
fallback, worker handoff, alternate credential, or second prepared commit is allowed until read-only
reconciliation resolves the first attempt.

`clientMutationId` and commit message metadata are correlation evidence, not the sole proof. Final
proof comes from canonical branch/commit/tree/blob state.

---

## 12. ChatGPT app deployment boundary

OpenAI's current platform contract makes full custom MCP write/modify actions available on ChatGPT
Business and Enterprise/Edu web workspaces. Custom app actions are reviewed/published by workspace
admins/owners and may trigger ChatGPT confirmation. Pro-only custom MCP connections remain read/fetch
for this purpose.

Official reference:

- https://help.openai.com/en/articles/12584461

Therefore the production path is a privilege-separated **Business GitHub repair app**, not a Personal
Pro-only MCP write path. Personal Pro remains the default Sol cognition plane; a Business app call is
a bounded execution companion, not a replacement cognition surface or another executive.

For the Business launch generation:

- enable developer mode only for the admin/owner doing the canary;
- keep the app private/draft until exact source and security proof passes;
- publish only the closed repair tools, not a generic GitHub endpoint;
- connect through the existing Business MCP auth/resource-server architecture;
- use the accepted remote deployment or Secure MCP Tunnel path;
- recreate/republish the Business app if its frozen tool schema changes;
- record exact app generation, schema digest, server build, policy, and GitHub App installation identity.

---

## 13. Failure vocabulary

Pure compiler failures are stable `ExactEditIssue` values including:

```text
INPUT_SCHEMA_INVALID
OPERATION_IDENTITY_INVALID
AUTHORITY_IDENTITY_INVALID
CARRIER_NOT_EXACT
WRITER_NOT_EXACT
PULL_REQUEST_NOT_OPEN
DEFAULT_BRANCH_REFUSED
PROTECTED_BRANCH_REFUSED
ALLOWED_PATH_COVERAGE_INCOMPLETE
HEAD_MOVED
FILE_COUNT_INVALID
REPLACEMENT_COUNT_INVALID
PATH_INVALID
PATH_PROTECTED
PATH_NOT_ALLOWED
DUPLICATE_PATH
SNAPSHOT_SET_MISMATCH
BLOB_MOVED
FILE_MODE_REFUSED
FILE_TOO_LARGE
TOTAL_SOURCE_TOO_LARGE
INVALID_UTF8
BINARY_REFUSED
EMPTY_ANCHOR
NOOP_REPLACEMENT
EDIT_TOO_LARGE
TOTAL_EDIT_TOO_LARGE
SECRET_SHAPED_CONTENT
ANCHOR_NOT_FOUND
ANCHOR_NOT_UNIQUE
EDIT_OVERLAP
POST_IMAGE_TOO_LARGE
PREVIEW_TOO_LARGE
```

The live owner adds transport/action failures without collapsing them into compiler errors:

```text
CAPABILITY_UNAVAILABLE
APP_GENERATION_MISMATCH
SCOPE_REFUSED
ORGANIZATIONAL_AUTHORITY_REFUSED
ACTION_TARGET_UNRESOLVED
OPERATION_CARRIER_CONFLICT
CARRIER_WRITER_CONFLICT
SOURCE_INCOMPLETE
SOURCE_MOVED
PREPARED_ACTION_EXPIRED
PRECONDITION_CHANGED
PRIOR_EFFECT_UNKNOWN
GITHUB_AUTH_UNAVAILABLE
GITHUB_RATE_LIMITED
GITHUB_REQUEST_REFUSED
EFFECT_UNKNOWN
RECONCILIATION_REQUIRED
```

Raw exception text, tokens, response headers, GraphQL variables containing file contents, full
post-images, and private host paths never enter model-visible failures.

---

## 14. Threat model and controls

| Threat | Control |
|---|---|
| prompt injection in PR/source text | source is data; authority comes from current law and server-owned carrier resolution |
| model chooses another repository/branch | repository/branch/PR/credential are owner-resolved, not free arguments |
| stale context corrupts current file | expected head + expected blob + unique exact anchor |
| fuzzy patch hits wrong block | no fuzzy/offset/three-way matching; non-unique anchors refuse |
| PR scope silently widens | path must already be in complete current PR changed-path set |
| constitutional self-amendment | hard protected path floor |
| token or key appears in patch/preview | secret-shaped input/preview refusal; credentials never model-visible |
| large payload denial | strict file/edit/preview bounds |
| binary/symlink/submodule corruption | V1 regular 100644 UTF-8 only |
| duplicate network delivery | one token-bound mutation; expected head; effect reconciliation |
| app update silently widens tools | immutable app/schema/policy generation and workspace re-review |
| green CI mistaken for completion | production canary and normal release review remain separate |

---

## 15. Implementation and promotion sequence

This operation removes a separate records-only GHP0 ceremony. Architecture and the first executable
pure capability land together.

```text
GHP1 — this carrier
  pure exact-edit compiler + hostile tests + live contract
  state: BUILT_NOT_PROVEN / PRODUCTION_INERT

GHP2 — one bounded source vertical
  operation evidence -> full blob gather -> prepare/token -> GraphQL actuator -> reconciliation
  closed MCP schemas/adapter + fake GitHub integration proof
  state: BUILT_NOT_PROVEN / PRODUCTION_DISARMED

GHP3 — install and prove
  GitHub App + Business MCP app generation + remote/tunnel deployment
  disposable >10k-line PR canary + stale-head and effect-unknown controls
  state after accepted proof: PROVEN_LIVE for exact branch repair only
```

GHP2 may consume protected GH1/GH2 semantics, but it may not fork release law or wait for a giant
all-purpose GitHub app. The minimum vertical may implement only the operation-evidence fields required
to prove one exact open PR repair and must leave merge/review/rerun actions to their existing owners.

GHP3 is the only wave that performs the new capability's first real GitHub mutation.

---

## 16. Production canary

Create a disposable, non-protected feature branch and draft PR whose setup commit already changes one
UTF-8 `100644` fixture with more than 10,000 lines. Then:

1. inspect one exact unique target line through the app;
2. prepare a one-line replacement;
3. verify bounded preview and no full-file model output;
4. confirm and commit once;
5. prove the new branch head, commit, target blob digest, and unchanged prefix/suffix/full-file control
   digest outside the replacement;
6. run a stale-head control and require `HEAD_MOVED` / `PRECONDITION_CHANGED` with zero effect;
7. inject a response-loss-after-send condition, require `EFFECT_UNKNOWN`, then reconcile without
   issuing a second mutation;
8. verify the PR path set did not widen and protected/default branches did not move;
9. close the disposable PR and remove the branch through a separate cleanup action after proof.

The accepted proof packet records exact app generation, server build, policy, OAuth principal digest,
GitHub App/installation digest, PR/branch/head/commit/blob identities, compilation digest, action
receipt, negative controls, and cleanup state. It contains no credential or complete file content.

---

## 17. No-rebuild / explicit non-goals

This program does not build or permit:

- a super-MCP or generic GitHub endpoint proxy;
- arbitrary unified diff, `git apply`, shell, SSH, filesystem root, executable, HTTP method/URL/body;
- model-selected repository, branch writer, credential, installation, host, provider, or account;
- default/protected branch write;
- file create/delete/rename/mode change in V1;
- PR creation, Ready transition, review, merge, deploy, release, or auto-merge through the repair tool;
- a second PR/commit/check database;
- a prepared-action/token registry;
- a Job/Attempt/Worker lifecycle or queue;
- automatic retry, base chase, rebase, reset, force push, or cross-surface failover;
- a substitute for repository-native workers when the change is broad, ambiguous, or exploratory.

The capability is successful precisely when it makes small exact repairs cheap while continuing to
route real implementation work to governed repository-native workers.
