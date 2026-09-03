# Sol Capability Fabric — Strict GitHub Branch-Patch Design

**Date:** 2026-09-03  
**Owner:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Pickup source:** `mastermindx-market-intelligence/Mastermind@068b83883915919802894fc9c31e7e7757100eb9`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Parent architecture:** SCF-F0 and SCF-GH0  
**Current wave state:** `SOURCE_CANDIDATE / PRODUCTION_INERT`

## 1. Executive ruling

Mastermind needs to let Chat-native CEO Sol make a small, exact repair to a large existing source file without asking the model to reconstruct the complete file and without creating a generic shell, filesystem writer, GitHub proxy, second repository, second lifecycle, or model-selected branch writer.

The accepted solution is a narrow owner-preserving capability:

```text
model-authored bounded unified diff
-> exact operation/carrier and path authorization outside the model
-> owner-side fetch of the complete immutable Git blob
-> pure strict patch materialization over exact bytes
-> secret-free preview and prepared action
-> at most one expected-head GitHub branch commit
-> canonical GitHub read-back
-> NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
```

This wave implements only the pure strict materialization core. It performs no network call, GitHub read, GitHub write, credential selection, app publication, MCP registration, branch creation, PR mutation, lifecycle mutation, or production arming.

## 2. User and machine outcome

### Chairman / Sol job

When Sol knows the exact small repair, Sol should submit only the bounded patch and inspect a digest/count preview. Sol must not receive, recreate, or retransmit a 10,000-line file merely because the native connected surface exposes whole-file replacement.

### Machine job

Given exact server-fetched source bytes, an exact target path, an expected Git blob object ID, and one bounded canonical unified diff, deterministically produce the exact resulting bytes or a stable refusal. Never relocate a hunk, guess intent, merge, call Git, touch a worktree, or silently normalize source.

### Completion ruler

This capability becomes `PROVEN_LIVE` only after a later owner-app generation is installed and a real disposable non-protected branch proves:

1. a small patch to an existing source file with more than 10,000 lines commits once through the real ChatGPT custom-app path;
2. the model-visible response contains no complete source file, credential, private path, or raw secret;
3. stale head, stale blob, wrong path, protected branch, unowned path, malformed diff, secret-shaped addition, and ambiguous response cases all fail or reconcile exactly as designed;
4. canonical GitHub read-back proves the resulting commit and bytes;
5. no duplicate commit appears after a lost or repeated client response.

Green source CI or a merged materializer alone establishes at most `BUILT_NOT_PROVEN`.

## 3. Canonical ownership and no-rebuild boundary

| Fact or effect | Existing owner |
|---|---|
| repository, branch, commit, blob, PR and resulting source | GitHub |
| stable CEO Job/Attempt/Worker/Event lifecycle | Executive OS |
| durable workstream/decision/discovery/handoff | Agent OS |
| exact current writer and branch responsibility | accepted Git carrier / Agent OS / Executive evidence |
| capability profile and installed MCP/app generation | existing execution-capability and Business app owners |
| authentication and OAuth resource-server behavior | existing Business MCP auth stack |
| Chat-native reasoning and final acceptance | Sol under current Chairman intent |

The patch capability creates no durable state owner. Preparation is self-contained and expiring. Reconciliation reads GitHub. There is no patch database, operation database, retry queue, desired-state loop, worktree registry, branch registry, credential store, or shadow Git history.

## 4. Layering and dependency order

```text
GHP1  pure strict materializer (this wave)
  |
  +-> consumes bytes and policy facts supplied by a future owner adapter
  +-> returns result bytes internally and a secret-free deterministic receipt

SCF-GH1  pure release/collision assessment (existing separate carrier)
  |
  +-> remains the source of release/collision semantics

GHP2 / SCF-GH2 extension  owner-side GitHub read, prepare, commit, reconcile
  |
  +-> may start only after its accepted dependency gates
  +-> imports GHP1; never forks patch semantics

GHP3  Business custom-app packaging/auth/deployment generation

GHP4  disposable real-path production canary and promotion decision
```

GHP1 and the existing SCF-GH1 implementation are path-disjoint pure libraries. GHP1 grants no right to modify GH1, absorb its release law, or start live GH2 actions.

## 5. GHP1 closed interface

The pure module owns an interface equivalent to:

```python
materialize_strict_patch(
    *,
    operation_key: str,
    path: str,
    expected_blob_oid: str,
    original: bytes,
    unified_diff: str,
    limits: PatchLimits = DEFAULT_LIMITS,
) -> PatchMaterialization
```

`PatchMaterialization` carries the resulting bytes for the trusted owner adapter and a model-safe receipt containing only identities, object/digest values, sizes and counts. It must not expose original source, resulting source, the raw patch, added lines, removed lines, exception text, credentials, or host paths in the public receipt.

The model-facing app will never accept `original`; it resolves/fetches the exact blob outside model arguments and invokes the pure function internally.

## 6. V1 accepted source shape

V1 deliberately supports only:

- one already-existing regular UTF-8 text file;
- LF line endings;
- a final newline;
- one exact relative POSIX repository path;
- one canonical single-file unified diff;
- unchanged old/new file path;
- bounded context, additions and deletions;
- exact declared hunk positions and exact context/removal bytes.

V1 refuses:

- file creation, deletion, rename or mode change;
- binary patch data, NUL, invalid UTF-8 or CRLF;
- symlink/submodule/nonregular targets as adjudicated by the owner adapter;
- multiple files;
- path traversal, absolute paths, backslashes or `.git` control paths;
- fuzzy hunk relocation;
- three-way merge;
- automatic conflict resolution;
- patch normalization;
- secret-shaped additions;
- empty or semantic no-op patches;
- output beyond reviewed limits.

This is a capability ceiling, not an inconvenience to be silently bypassed through another actuator.

## 7. Strict application law

For every hunk:

1. parse the declared old/new ranges without guessing omitted semantics;
2. require hunks to be ordered and non-overlapping;
3. require old and new body counts to match the header exactly;
4. require the declared old location to match the current source cursor;
5. require every context and removed line to match exact source text at that location;
6. require the declared new location to equal the output position implied by prior exact changes;
7. copy context, omit removals and append additions exactly;
8. preserve all untouched bytes and the final newline;
9. refuse if the result is byte-identical to the original.

A matching context sequence elsewhere in the file is irrelevant. GHP1 never searches for a better location.

## 8. Identity and digest law

The caller supplies `expected_blob_oid`. GHP1 recomputes the Git object ID from the exact original bytes and refuses on mismatch before patch application. Current SHA-1 and SHA-256 object-ID lengths may be accepted; the algorithm is selected only by the exact validated OID length.

The result includes:

```text
schema = mastermind.github_branch_patch_materialization.v1
operation_key
path
old_blob_oid
new_blob_oid
original_sha256
result_sha256
patch_sha256
original_size
result_size
hunk_count
addition_count
deletion_count
changed_line_count
```

Digests support equality and evidence; they do not replace canonical GitHub read-back.

## 9. Limits

Default reviewed ceilings:

```text
original bytes        <= 4 MiB
result bytes          <= 4 MiB
unified diff bytes    <= 128 KiB
patch lines           <= 4096
hunks                 <= 16
added lines           <= 512
deleted lines         <= 512
changed lines total   <= 768
path bytes            <= 240
operation key bytes   <= 192
individual text line  <= 64 KiB
```

A later generation may change limits only through a reviewed schema/policy generation. The model cannot request larger limits.

## 10. Stable failure vocabulary

GHP1 raises only stable typed failures equivalent to:

```text
INPUT_INVALID
OPERATION_KEY_INVALID
PATH_INVALID
BLOB_OID_INVALID
BLOB_MISMATCH
ORIGINAL_TOO_LARGE
RESULT_TOO_LARGE
PATCH_TOO_LARGE
TEXT_ENCODING_UNSUPPORTED
LINE_ENDING_UNSUPPORTED
LINE_TOO_LONG
PATCH_FORMAT_INVALID
MULTI_FILE_PATCH_REFUSED
FILE_OPERATION_REFUSED
PATH_MISMATCH
HUNK_LIMIT_EXCEEDED
CHANGE_LIMIT_EXCEEDED
HUNK_RANGE_INVALID
HUNK_COUNT_MISMATCH
HUNK_ORDER_INVALID
CONTEXT_MISMATCH
SECRET_SHAPED_ADDITION
NO_CHANGE
```

Messages are payload-free and must not include source lines, patch lines, secret material, local paths or arbitrary parser exceptions.

## 11. Future GHP2 owner-app contract

The future privilege-separated GitHub owner app exposes exactly:

```text
prepare_branch_patch
commit_branch_patch
reconcile_branch_patch
```

### Prepare

The model supplies a stable operation key, an owner-resolved logical target reference, the bounded unified diff, and the expected current source identity already displayed by a trusted read. The owner app:

- authenticates the accepted principal and app generation;
- resolves the repository, branch, PR, current writer and allowed paths outside model choice;
- refuses protected/default branches;
- reads exact branch head, target entry kind and complete blob from GitHub;
- invokes GHP1;
- returns a bounded preview plus an authenticated self-contained expiring prepared token;
- performs zero GitHub mutation.

### Commit

Commit accepts only the prepared token. It reauthenticates, re-resolves the same owner target, rechecks current Chairman/organizational authority, app/schema/policy generation, branch head, blob, path ownership, prior effect and result digest, then issues at most one owner-native expected-head branch-commit request.

### Reconcile

Reconciliation accepts the stable operation/action/target identity, reads canonical branch/commit/tree/blob facts, and returns:

```text
NOT_APPLIED | APPLIED | EFFECT_UNKNOWN
```

It never resubmits. `EFFECT_UNKNOWN` blocks another patch, worker failover, browser fallback and native connector fallback for that logical effect.

## 12. GitHub commit effect ceiling

The live owner may modify only one existing authorized text path on one existing non-protected operation branch in V1. It cannot:

- select or create a repository;
- select or create a branch;
- modify the protected/default branch;
- add/delete/rename files;
- force-update a ref;
- merge, mark Ready, request review or rerun CI as part of patch commit;
- write outside the already-authorized operation surface;
- use a generic method/URL/body proxy;
- fall back to shell, browser, Git CLI or another GitHub principal.

The commit message and canonical resulting commit carry the stable operation key and effect digest needed for read-back reconciliation, but prose alone never proves the effect.

## 13. Threat model

Required hostile cases include:

- stale branch head or blob;
- repeated context elsewhere causing a fuzzy implementation to patch the wrong site;
- malformed hunk counts/ranges;
- overlapping/reordered hunks;
- a second file smuggled after the first patch;
- rename/delete/create/mode headers;
- path traversal or `.git` targeting;
- CRLF/NUL/invalid UTF-8;
- secret-shaped content in added lines;
- oversized source, output, patch, line, hunk or change set;
- prepared-token replay after a successful effect;
- same operation key with changed normalized effect;
- network loss before request, during request and after GitHub accepted it;
- forged commit prose from an unrelated actor;
- branch movement by the legitimate current writer between prepare and commit;
- prompt injection inside source, PR or commit text;
- an app or OAuth scope being mistaken for organizational authority.

## 14. Acceptance for this wave

GHP1 source acceptance requires:

- RED-first tests covering a generated source with more than 10,000 lines;
- exact middle-of-file repair with byte-preservation proof;
- all V1 refusal cases above;
- deterministic permutation/repeat behavior;
- public receipt leak checks;
- AST/import proof of no filesystem, network, subprocess, clock, randomness, GitHub or integration dependency;
- focused tests, full relevant repository tests, compile, diff check and hosted security checks;
- exact changed-path census;
- genuinely independent exact-head adversarial review.

The wave stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT`. It does not publish or arm a custom app and does not patch a real GitHub branch.

## 15. No-rebuild ledger

`REJECTED_BY_DESIGN`:

- generic repository MCP;
- generic shell/Git/worktree tool;
- generic filesystem write;
- generic GitHub method/URL/body proxy;
- model-selected repository, branch, credential, installation or writer;
- patch queue or retry daemon;
- durable prepared-action or patch store;
- second operation/lifecycle/branch/PR database;
- automatic branch election, base chase, rebase, reset or force push;
- fuzzy/three-way patching;
- hidden fallback to the native connector, browser or worker after uncertainty;
- treating CI or merge as production proof.

## 16. Exact next action after GHP1 source protection

Only after GHP1 and the required SCF-GH1 dependency are protected may a fresh operation implement GHP2 as the narrow GitHub owner-app vertical. It must reuse the existing Business authentication/resource-server stack and SCF prepared/effect contracts, consume this pure module, and prove one disposable W1 branch-patch canary before any broader path or repository enrollment.
