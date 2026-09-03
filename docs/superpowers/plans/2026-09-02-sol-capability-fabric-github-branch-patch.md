# SCF-GHP1 — Strict Large-File Branch Patch Kernel

**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Parent:** `mastermind-sol-capability-fabric-20260830-sol-001`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Capability after this wave:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`

## Observable mission

Given a complete exact Git blob acquired outside model context plus a tiny exact-path unified diff,
materialize the complete replacement bytes deterministically for a file larger than 10,000 lines,
while refusing stale blobs, wrong paths, fuzzy context, malformed ranges, unsupported files, secret-
shaped additions and oversized changes.

This closes only the pure patch-materialization gap. It does not expose a model-facing write tool,
call GitHub, create a commit, publish an MCP app, install a GitHub App, arm production or establish
`PROVEN_LIVE`.

## Why this is the next vertical

The connected GitHub surface can replace a UTF-8 file only when the caller supplies its complete new
contents. A Chat surface that receives a truncated large-file representation cannot safely construct
that replacement. The missing deterministic seam is therefore:

```text
owner-acquired complete exact blob
+ bounded model-authored semantic diff
-> strict full-file materialization outside model context
```

A generic repository shell, filesystem writer or super-MCP would solve a larger problem by creating a
larger authority and blast radius. GHP1 instead produces one pure internal primitive that a later
owner-specific GitHub action app can consume.

## Authority and no-rebuild boundary

- GitHub remains repository, branch, blob, commit and pull-request truth.
- GH1 remains the pure release/collision assessment owner; GHP1 does not fork it.
- A later GH2/GHP2 owner app resolves the exact operation, carrier, repository, branch, current writer,
  allowed paths, app generation, principal, credential and action authority.
- Executive OS remains Job/Attempt/Worker/Event and CEO-admission owner.
- Agent OS remains durable workstream/decision/discovery/handoff owner.
- The patch kernel owns no lifecycle, queue, branch election, credential, prepared-action store,
  idempotency database, retry, merge, release or production acceptance.

The following remain rejected: generic shell, generic Git/HTTP/filesystem actuator, arbitrary URL,
model-selected repository or branch writer, force/reset/rebase, automatic base chase, fuzzy hunk
placement, three-way merge, and blind retry after an ambiguous write.

## Exact source scope

```text
control_plane/github_branch_patch.py
tests/test_github_branch_patch.py
docs/superpowers/plans/2026-09-02-sol-capability-fabric-github-branch-patch.md
```

The active SCF-GH1 carrier owns `control_plane/github_release_assessment.py` and
`tests/test_github_release_assessment.py`; GHP1 does not touch either path and may proceed in parallel
only while that path separation remains true.

## Closed V1 contract

`apply_strict_unified_patch(BranchPatchInput)` consumes:

```text
schema
operation_key
repository
branch
path
expected_head_sha
expected_blob_sha
complete source_bytes
one exact-path unified patch
```

It returns an internal `BranchPatchMaterialization` containing complete result bytes plus a bounded
`public_receipt()` with only identities, counts and cryptographic digests. The full source and result
bytes are never part of the model-facing preview.

V1 supports only an existing ordinary UTF-8 file using LF endings and a final newline. The unified
patch must contain exactly one `--- a/<path>` / `+++ b/<path>` pair and one or more ordered,
non-overlapping hunks. It supports context, additions and removals; it does not support create/delete,
rename, mode change, binary patch, no-final-newline marker, CRLF conversion, metadata preambles,
offset search, fuzz or merge.

Fixed ceilings:

```text
source/result bytes     8 MiB
patch bytes             128 KiB
hunks                   32
added + removed lines   512
```

## Deterministic method

1. Validate the closed identities and exact relative POSIX path.
2. Validate source type/size/UTF-8/LF/final-newline constraints.
3. Compute the canonical Git blob SHA-1 and require exact equality with `expected_blob_sha`.
4. Parse the strict unified-diff grammar without shelling out or importing Git/MCP/network code.
5. Apply each hunk at its declared zero-offset source/result coordinates.
6. Require every context/removal line to match exact source bytes.
7. Refuse unsorted/overlapping hunks, bad counts, bad coordinates and high-confidence credential
   material introduced by additions.
8. Emit complete result bytes internally and a deterministic digest-only public preview.

No statistical or model-generated judgment exists inside this method. The diff may be model-authored,
but it grants no authority; all results are mechanical and fail closed.

## Failure states

Typed payload-free refusals include:

```text
INPUT_SCHEMA_INVALID
INPUT_INVALID
PATH_INVALID
PATH_MISMATCH
SOURCE_LIMIT_EXCEEDED
SOURCE_FORMAT_UNSUPPORTED
SOURCE_BLOB_MISMATCH
PATCH_LIMIT_EXCEEDED
PATCH_FORMAT_INVALID
HUNK_LIMIT_EXCEEDED
CHANGED_LINE_LIMIT_EXCEEDED
HUNK_ORDER_INVALID
HUNK_RANGE_INVALID
HUNK_CONTEXT_MISMATCH
SECRET_SHAPED_ADDITION
RESULT_LIMIT_EXCEEDED
NO_CHANGE
```

The later owner app must separately handle stale branch head, protected branch, unowned path,
nonregular Git object, operation/carrier conflict, authority refusal, prepared-token expiry, GitHub
request uncertainty and `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN` reconciliation.

## Acceptance proof

GHP1 is accepted as source only after:

- a generated 12,050-line source receives a one-line replacement without putting complete contents in
  the public receipt;
- wrong blob, wrong path, moved context, hunk count/range error, overlap/order error, CRLF, NUL,
  missing final newline, rename/delete/metadata/no-newline patch forms, high-confidence secret addition
  and no-op are discriminating refusals;
- start/end zero-length insertion ranges work exactly;
- outputs and digests are deterministic;
- AST/import proof establishes no network, MCP, filesystem I/O, subprocess, clock or random dependency;
- focused tests, compile, full repository CI, security checks and independent exact-head review pass;
- the changed-path census remains exactly the three declared paths.

## Stop condition and continuation

Stop at `BUILT_NOT_PROVEN / PRODUCTION_INERT`. Do not add GitHub transport, credentials, HMAC prepared
tokens, MCP schema/server, deployment, workspace installation or a live canary to this PR.

After GHP1 and SCF-GH1 are protected, GHP2 may build one owner-specific prepare/commit/reconcile action
vertical. It must resolve repository/branch/current-writer/allowed-path facts outside model input, bind
this materialization into a self-contained expiring prepared token, issue at most one expected-head
GitHub mutation and reconcile from canonical GitHub truth without resubmission.
