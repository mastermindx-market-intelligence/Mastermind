# SCF-GHP1 — Release and Continuation Plan

**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Authority:** current live Chairman directive to drive the bounded patch capability toward completion  
**Architecture:** `docs/superpowers/specs/2026-09-02-sol-capability-fabric-github-branch-patch.md`  
**Capability ceiling for this carrier:** `BUILT_NOT_PROVEN / PRODUCTION_INERT`

## Observable mission

Protect one pure, deterministic kernel that can apply a tiny exact unified diff to server-materialized
full GitHub blob content without returning that full file to ChatGPT, and leave the exact live-owner
continuation recoverable without creating a generic shell, generic GitHub proxy, second lifecycle, or
second carrier.

## Exact source scope

```text
control_plane/github_branch_patch.py
tests/test_github_branch_patch.py
docs/superpowers/specs/2026-09-02-sol-capability-fabric-github-branch-patch.md
docs/superpowers/plans/2026-09-02-sol-capability-fabric-github-branch-patch.md
```

No existing runtime, MCP server, OAuth client, credential path, Executive/Agent OS lifecycle, Wake,
RuntimeBinding, Capacity, browser, Slack, Linear, deployment, protected-branch, or production file is
modified.

## Ordered release work

1. Run focused tests and Python compile on the exact branch head.
2. Compare protected `master` to the exact head; require only the four paths above.
3. Run full hosted repository and security checks on the exact head.
4. Obtain one independent exact-head review focused on strict patch parsing/application, Git object
   verification, bounded output, secret non-reflection, purity, and no duplicate owner.
5. Reconcile current protected source. If master moved on disjoint paths, compose history-preservingly;
   never reset, rebase, force-push, regenerate, or create a replacement carrier.
6. Sol reviews against the Chairman outcome and, only after every release gate is true, performs a
   separate expected-head release adjudication.

## Acceptance tests

The exact-head proof must include:

```text
python3 -m pytest -q tests/test_github_branch_patch.py
python3 -m py_compile control_plane/github_branch_patch.py tests/test_github_branch_patch.py
git diff --check
full repository test workflow
required security/code analysis
exact changed-path census
independent exact-head review
```

The hostile matrix must prove the >10,000-line interior edit, no public full-file projection,
order-stable effect identity, protected/unowned/unsafe path refusal, exact blob identity, zero-fuzz
context behavior, malformed/overlapping hunk refusal, text/binary ambiguity refusal, bounded ceilings,
secret-shaped addition refusal, and no I/O/network/subprocess/clock dependency.

## Explicit non-goals

This carrier does not implement or claim:

- a live ChatGPT Business app or custom MCP installation;
- OAuth/GitHub App enrollment or token minting;
- live operation/carrier resolution;
- a real GitHub write using the new capability;
- branch creation, protected-branch write, merge, force push, reset, rebase, rename, delete, binary,
  symlink, mode, submodule, or generic endpoint support;
- CI/review/merge/production acceptance merely because the pure kernel tests pass.

## Stop condition

Stop GHP1 at `BUILT_NOT_PROVEN / PRODUCTION_INERT` after exact-head source proof and release review. A
merge protects only the strict kernel and contract.

## Required continuation handoff

The next independent operation is:

```text
operation_key: mastermind-sol-capability-fabric-ghp2-20260902-sol-001
mission: build the production-disarmed privilege-separated GitHub owner app exposing only
         prepare_branch_patch, commit_branch_patch, and reconcile_branch_patch
preferred_avenue: CTO Sol
receiver_binding_mode: CAPACITY_SELECTABLE
placement_state: WAITING_DEPENDENCY
why_not_fable: the product, authority, method, schemas, limits, failure law, and canary are frozen;
               remaining work is difficult but bounded engineering
```

GHP2 must consume this kernel and the protected SCF-GH1 release/collision engine. It must reuse the
accepted Business OAuth/resource-server stack, accept no arbitrary repository/branch/URL/credential,
remain production-disarmed, and return to Sol with exact source/test/security evidence. No successor
inherits START from this plan.
