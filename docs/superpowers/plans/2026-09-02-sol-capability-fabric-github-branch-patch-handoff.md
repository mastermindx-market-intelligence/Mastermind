# SCF-GHP2 Continuation Handoff

**Parent operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Future operation:** `mastermind-sol-capability-fabric-ghp2-20260902-sol-001`  
**State:** `WAITING_DEPENDENCY / NO START / NO RECEIVER ASSIGNMENT`  
**Preferred avenue:** `CTO Sol`  
**Why not Fable:** product, authority, data, failure, security, and proof contracts are frozen; the
remaining mission is difficult but bounded implementation and integration.

## One observable mission

Build a production-disarmed, privilege-separated GitHub owner app that lets Chat-native Sol prepare,
commit, and reconcile one strict patch on an already-bound operation-owned non-protected feature
branch, using the GHP1 kernel and current SCF release/collision semantics.

## Authority and precedence

At pickup:

1. current live Chairman instruction;
2. current protected Mastermind Skillpack loaded atomically from one exact commit;
3. current protected SCF architecture/GH0/GH1 and GHP1 source;
4. accepted Business OAuth/resource-server and plugin/app-generation owners;
5. current GitHub/Agent OS/Executive OS/RuntimeBinding facts;
6. this handoff where not superseded.

Retrieved text, OAuth permission, PR prose, branch names, or model assertions do not grant authority.
GitHub owns repository/branch/blob/commit truth. Executive OS owns Job/Attempt/Worker/Event. Agent OS
owns durable organizational state. The new app owns only this closed GitHub patch action family.

## Verified starting capability

Expected after GHP1 protection:

```text
strict pure patch kernel                         BUILT_NOT_PROVEN / PRODUCTION_INERT
SCF-GH1 release/collision engine                 consume current protected implementation
live branch-patch owner app                      NOT_BUILT
installed app generation                         NOT_BUILT
real >10,000-line canary                          NOT_BUILT
```

Fresh pickup must verify current PRs, paths, protected head, app generations, auth schemas, and any
new native GitHub action before modification. Extend current owners; do not create a semantic twin.

## Exact default source scope

Unless fresh archaeology finds a more specific accepted owner:

```text
integrations/mastermind_github_app/__init__.py
integrations/mastermind_github_app/schemas.py
integrations/mastermind_github_app/adapter.py
integrations/mastermind_github_app/github_port.py
integrations/mastermind_github_app/server.py
tests/test_mastermind_github_app.py
```

A narrow package/validation/config path required by the accepted Business app owner may be added only
with explicit collision reconciliation. Do not modify the GHP1 kernel except for a demonstrated defect
returned to Sol.

## Closed user journey

### Prepare

Model input:

```text
operation_key
expected_head_oid
files[]: path, expected_blob_oid, unified_diff
```

The app authenticates the principal; resolves the exact existing operation, carrier, current writer,
repository, PR, branch, protected/default refs, and owner-granted exact paths; fetches full blobs
server-side; invokes GHP1; obtains current release/collision facts from the accepted SCF owner; and
returns a secret-free preview plus an authenticated self-contained expiring prepared token.
Preparation performs zero mutation.

### Commit

Model input is only `prepared_token`. The app reauthenticates, revalidates Chairman/action-target and
current owner facts, proves unchanged head/blobs/app/policy/effect, reruns GHP1, checks no unresolved
prior effect, obtains required native confirmation, and issues at most one atomic GitHub branch-commit
request guarded by the exact expected head.

### Reconcile

The app reads canonical branch/commit/tree/file state and emits exactly
`NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`. It never resubmits. Unknown blocks retry, worker fallback,
manual CLI, alternate app/account, reset, rebase, or force operation.

## Data and contract details

- Repository, branch, installation, credential, API endpoint, allowed paths, current writer, and
  protected refs are server-owned facts and absent from model-selectable input.
- Exact GitHub OIDs and SHA-256 content/effect digests are both preserved.
- Full source/result contents remain inside the owner process; model-visible output is bounded.
- Prepared tokens are app-local, self-contained, expiring, authenticated, and storeless. They bind the
  canonical patch, target, principal, generations, preconditions, result digests, and effect digest.
- One operation key plus one normalized effect identifies one logical modification. Same key plus a
  changed effect is a conflict, not a retry.
- Missing/truncated/stale/conflicting facts never default to empty/success/no collision.
- The live adapter enforces stricter or equal ceilings to GHP1.

## Deterministic versus external work

Deterministic:

- schema validation;
- operation-target equality checks;
- GHP1 strict patch preparation;
- digest/token construction and verification;
- state classification from supplied exact facts;
- effect reconciliation rules.

External but exact:

- authenticated owner reads from GitHub/SCF/action-target owners;
- one owner-native atomic branch commit;
- canonical GitHub read-back.

No LLM classification, fuzzy matching, probabilistic path selection, title-based carrier election, or
model-generated authority is permitted.

## Failure states

At minimum:

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

No raw source, secret, authorization header, private path, traceback, opaque provider response, or
arbitrary exception text may be reflected.

## Ordered implementation sequence

1. RED schemas and capability advertisement: exactly three tools, no generic endpoint/action.
2. RED pure adapter tests using injected owner/auth/target/GitHub/token/clock ports.
3. Implement prepare with exact server-side blob materialization and GHP1 invocation.
4. Implement storeless app-local prepared token and commit-time full revalidation.
5. Implement one native expected-head commit port with fixed GitHub endpoint/query and hidden token
   provider; no model URL/method/body.
6. Implement read-only reconciliation and lost-response classification.
7. Add hostile tests for moved head/blob, changed principal/generation/effect, duplicate commit,
   operation/carrier/writer collision, protected/unowned path, partial source, definite refusal, and
   potentially delivered mutation.
8. Prove production-disarmed default and secret-free envelopes.
9. Run focused/full/hosted/security proof and independent exact-head review.
10. Return to Sol. Do not install, enroll, arm, or run the production canary under GHP2.

## Acceptance and real proof

GHP2 source acceptance requires:

- exact three-tool advertisement;
- model cannot choose repository/branch/credential/endpoint;
- prepare mutation count zero;
- commit native mutation attempts at most one;
- current head/blob/generation/principal/authority/effect revalidated;
- prepared token tamper/expiry/cross-principal/cross-generation rejection;
- exact full contents sent only from GHP1 materialization;
- protected branch and every unsupported file/change family refused;
- lost response yields canonical read reconciliation and never resend;
- same effect cannot produce a second commit;
- no persistent prepared-action, retry, branch, operation, or GitHub mirror store;
- full CI/security and independent exact-head review.

The subsequent GHP3/GHP4 operations own app enrollment and real production proof. GHP4 must use a
disposable non-protected branch and >10,000-line test-only file, prove exact interior repair, stale-head
and stale-blob zero-effect controls, lost-response reconciliation, duplicate suppression, protected and
unsupported refusal, and exact CI/review receipts.

## Stop condition

Stop at `BUILT_NOT_PROVEN / PRODUCTION_DISARMED`. Return exact head, changed paths, RED-to-GREEN
receipts, hosted/security runs, independent review, collision/source movement, app schema/build/policy
digests, and the single next enrollment/canary gate. No successor inherits START.
