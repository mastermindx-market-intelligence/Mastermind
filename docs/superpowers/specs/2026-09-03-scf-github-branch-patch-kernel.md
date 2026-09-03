# SCF-GHP1 — Strict GitHub Branch-Patch Kernel

**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Parent:** Mastermind Sol Capability Fabric / SCF GitHub domain  
**Capability:** `SPEC_ONLY / PRODUCTION_INERT` until implementation and proof pass  
**Owner:** GitHub facts and effects remain owned by GitHub; GHP1 owns only pure patch planning.

## Outcome

A GitHub owner adapter can fetch a complete large UTF-8 source file outside model context, pass the exact bytes and one small unified diff through a deterministic no-fuzz kernel, and receive complete resulting bytes plus a content-free preview. ChatGPT therefore never has to reconstruct or replace a 10,000-line file from a truncated connector response.

This is a narrow addition to the existing Sol Capability Fabric. It is not a repository MCP, generic filesystem writer, shell, HTTP proxy, GitHub mirror, lifecycle, queue, retry plane, branch allocator, credential owner, or release authority.

## V1 contract

`control_plane.github_branch_patch.apply_branch_patch` accepts one closed packet containing:

- stable operation identity;
- exact repository, already-bound target branch and expected branch head;
- exact existing target path and Git blob identity;
- SHA-256 of the complete server-fetched source bytes;
- complete source text and a bounded unified diff;
- owner-supplied exact allowed paths and protected branches.

It accepts only one ordinary existing `100644` UTF-8/LF text file with a final newline. V1 refuses new/delete/rename/copy/mode/binary operations, quoted or unsafe paths, CR/NUL text, no-newline markers, fuzzy placement, out-of-order or overlapping hunks, inconsistent old/new positions, stale source bytes, protected branches, unowned paths, zero-effect diffs, and all configured size/count ceilings.

The result contains server-private complete result bytes and a model-visible preview containing only exact identities, byte/count metrics, SHA-256 digests and a canonical plan digest. Source lines, added text, deleted text and result text are not present in the preview.

## Deterministic and authority boundary

The kernel performs no I/O and imports no GitHub, MCP, network, filesystem, clock, random, subprocess, credential, Executive OS, Agent OS, RuntimeBinding, Wake, Capacity or provider component. Model output supplies proposed patch text only. It never supplies authority.

A future owner-specific GHP2 adapter must:

1. resolve the existing operation/carrier and current writer through accepted owners;
2. select repository, branch, installation and credential server-side;
3. prove the branch is non-protected and the path belongs to the current write set;
4. fetch the exact branch head, blob identity and complete bytes from GitHub;
5. call GHP1 and return only its content-free preview;
6. bind the complete result digest into an authenticated, expiring, owner-local prepared token;
7. on commit, reauthenticate and re-read every load-bearing predicate;
8. issue at most one expected-head GitHub mutation;
9. read canonical GitHub state and return `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`;
10. reconcile ambiguous effects without resubmission or cross-carrier failover.

GHP2 must not expose repository, branch, URL, HTTP method, credential, installation, force behavior, arbitrary commit content or full-file replacement as model-selected fields.

## Proof ruler

GHP1 source is accepted only after:

- a generated source with more than 10,000 lines receives the exact intended two-hunk edit;
- stale digest, wrong path, unowned path, protected branch, stale/moved context, repeated context, inconsistent positions/counts, multiple files and nonordinary operations all fail closed;
- changed-line and byte ceilings are discriminated;
- preview output is proven content-free and deterministic;
- AST/import purity checks pass;
- focused and full repository tests, hosted checks and independent exact-head review pass.

Even after protection, GHP1 remains `BUILT_NOT_PROVEN / PRODUCTION_INERT`. No custom app, GitHub credential, branch commit, ChatGPT tool, deployment or live large-file repair is created by this wave. GHP2 and a disposable end-to-end canary require separately authorized operations after their dependencies are protected.
