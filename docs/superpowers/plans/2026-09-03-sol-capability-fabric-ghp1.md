# SCF-GHP1 — Strict GitHub Branch-Patch Materializer Plan

**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Branch:** `sol/sol-capability-fabric-ghp1-20260902`  
**Pickup source:** `Mastermind@068b83883915919802894fc9c31e7e7757100eb9`  
**Architecture:** `docs/superpowers/specs/2026-09-03-sol-capability-fabric-github-branch-patch-design.md`  
**Cognition:** `COGNITION_ROUTE: CHAT_PRO_DEFAULT`  
**PREFERRED_AVENUE:** `CTO Sol` for repair/review work after the initial bounded source candidate  
**WHY:** the capability is narrow but correctness- and security-sensitive; exact diff semantics, leak resistance and hostile mutation review require a strong bounded engineering lane.  
**WHY NOT FABLE:** product, owner, authority and no-rebuild boundaries are frozen; no principal-level cross-repository ambiguity remains in GHP1.  
**RECEIVER_BINDING_MODE:** `CAPACITY_SELECTABLE`  
**Current capability ceiling:** `BUILT_NOT_PROVEN / PRODUCTION_INERT` after exact-head proof; no live GitHub action.

## 1. Observable mission

A trusted server-side caller can supply a complete exact existing-file blob and a small canonical unified diff and receive exact resulting bytes plus a secret-free deterministic receipt, while stale blobs, fuzzy placement, multiple files, file operations, malformed ranges, secret-shaped additions and oversized inputs are refused.

## 2. Why this is the next dependency

The native ChatGPT GitHub surface can replace a complete UTF-8 file, but a model response is not a safe carrier for reconstructing a large existing source file. GHP1 removes that source-materialization hazard without widening GitHub authority. The later owner app can fetch the full blob outside model context, call this pure core, then use one prepared expected-head mutation and canonical reconciliation.

Without GHP1, every future adapter would either duplicate patch semantics, shell out to an ambient worktree, trust fuzzy patch tooling, or continue forcing large-file repair through repository-native workers solely for tool access.

## 3. Authority and precedence

At every substantive action, use this order:

1. current live Chairman intent;
2. current protected Mastermind Skillpack loaded atomically from one exact protected commit;
3. protected SCF-F0 and SCF-GH0 architecture/contracts;
4. the current protected GHP design after release;
5. current GitHub carrier/head/path/check/review truth;
6. this implementation plan;
7. implementation choices consistent with 1–6.

If protected source moves materially or another active carrier appears for these paths, stop and reconcile. Never reset, rebase, force-update or create a replacement operation to hide movement.

## 4. Verified pickup state

At the initial source write:

```text
protected pickup       068b83883915919802894fc9c31e7e7757100eb9
carrier branch         sol/sol-capability-fabric-ghp1-20260902
prior carrier effect   branch creation only
same-name PR           none found at pickup
same-path GHP source   none found at pickup
SCF-GH1 carrier        PR #295, separate two-path pure release engine
live branch patch app  NOT_BUILT
write-side apply_patch NOT_BUILT on the connected native surface
```

The implementation must be reconciled to current protected source before release. Pickup identity is evidence, not a promise that protected master remains unchanged.

## 5. Exact scope

Expected GHP1 paths:

```text
control_plane/github_branch_patch.py
tests/test_github_branch_patch.py
docs/superpowers/specs/2026-09-03-sol-capability-fabric-github-branch-patch-design.md
docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1.md
```

No other path may enter this source wave without Sol reconciliation.

Protected/no-edit families:

```text
control_plane/github_release_assessment.py
tests/test_github_release_assessment.py
integrations/**
config/**
ops/**
.github/**
plugins/**
docs/sol_skills/**
Executive OS lifecycle, Capacity, RuntimeBinding, Wake and Agent OS source
```

## 6. Exact implementation sequence

1. Freeze the GHP design and no-rebuild boundary.
2. Add RED tests for a generated source with more than 10,000 lines and all hostile cases.
3. Implement the pure materializer with closed types and stable payload-free errors.
4. Run focused tests and Python compilation.
5. Run the full repository test harness and security/static analysis.
6. Compare exact protected source to exact candidate head and verify only the four declared paths.
7. Reconcile any protected-source movement history-preservingly; do not regenerate reviewed feature bytes unnecessarily.
8. Obtain a genuinely independent exact-head adversarial review.
9. Sol reviews against the Chairman outcome and source/proof honesty.
10. Keep Draft/Hold until every release gate is affirmatively true.

## 7. Discriminating test matrix

### Positive

- exact 12,050-line source, one replacement around line 6,000;
- ordered non-overlapping multi-hunk patch;
- exact zero-count insertion and deletion range semantics;
- SHA-1 and SHA-256 Git object identities;
- deterministic bytes and canonical receipt;
- complete preservation of untouched prefix/suffix bytes.

### Identity and placement

- malformed operation key;
- path traversal, backslash, absolute, `.git` and wrong diff path;
- stale expected blob;
- mismatched optional index prefix;
- declared position wrong while identical context exists elsewhere;
- wrong new-range position;
- overlapping/reordered hunks.

### Shape and file effects

- malformed/short/overrun hunk counts;
- second file after the first;
- create/delete/rename/copy/mode/binary metadata;
- empty/no-op change;
- result that would violate final-newline policy.

### Encoding and leak resistance

- CRLF source or patch;
- missing final newline;
- NUL and invalid UTF-8;
- overlong source or patch line;
- high-confidence secret-shaped additions;
- stable exception contains only the failure code;
- public receipt contains no source, result, raw patch or changed lines.

### Resource ceilings

- original, result, patch, patch-line, hunk, added, deleted and total changed-line limits;
- call-time malformed/zero limits fail closed.

### Purity

- AST/import test rejects filesystem, network, subprocess, clock, randomness, GitHub, integration or credential dependencies;
- no persistence, retry, branch selection or model-facing full-file interface.

## 8. Required local and hosted proof

```text
python -m pytest -q tests/test_github_branch_patch.py
python -m py_compile control_plane/github_branch_patch.py tests/test_github_branch_patch.py
python scripts/ci_pytest.py
git diff --check <protected>...<candidate>
GitHub hosted required test check
GitHub hosted security/code analysis
exact changed-path census
independent exact-head adversarial review
```

A failed hosted test must be diagnosed from exact logs and repaired on the same carrier. A green run on an older head does not transfer.

## 9. Adversarial review mission

The independent reviewer must attempt to prove at least one of:

- a hunk can be relocated or partially applied;
- old/new range arithmetic accepts an incorrect patch;
- a second path or file operation can be smuggled;
- a source or patch byte is normalized unexpectedly;
- a stale blob can pass;
- a secret-shaped added line or source text leaks through a receipt/error;
- a limit can be bypassed by Unicode, omitted counts, zero ranges or metadata shape;
- a forbidden I/O or mutable owner concern entered the pure module;
- the source claim exceeds `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

Review must be anchored to the immutable candidate head and performed by a non-author identity. Approval does not merge or make the capability live.

## 10. Stop condition

Stop GHP1 when one exact current-base four-path candidate has terminal hosted checks, independent exact-head approval and Sol acceptance. Merge/protection establishes only:

```text
GHP1 = BUILT_NOT_PROVEN / PRODUCTION_INERT
```

Do not in GHP1:

- add an MCP server or custom app;
- add Business OAuth or GitHub credentials;
- call GitHub;
- create a prepared-token signer;
- commit a live patch;
- patch a protected/default branch;
- implement release assessment again;
- modify SCF-GH1;
- start GHP2, GHP3 or GHP4 under this operation.

## 11. Continuation handoff — GHP2

A fresh, separately authorized operation after GHP1 and required SCF-GH1 gates should implement one independently useful vertical:

```text
owner-resolved exact target
-> GitHub exact branch/blob read
-> GHP1 materialization
-> secret-free preview + owner-local prepared token
-> one expected-head non-protected branch commit
-> canonical APPLIED/NOT_APPLIED/EFFECT_UNKNOWN reconciliation
```

Recommended default paths, subject to fresh owner archaeology:

```text
integrations/mastermind_github_app/schemas.py
integrations/mastermind_github_app/adapter.py
integrations/mastermind_github_app/server.py
integrations/mastermind_github_app/__init__.py
tests/test_mastermind_github_app.py
```

The adapter must reuse the existing Business MCP authentication/resource-server stack. Only `server.py` may import the MCP SDK. The model never selects repository, branch, installation, credential, writer or arbitrary URL. GHP2 remains production-disarmed until a later installation/canary wave.

## 12. GHP2 minimum prepared-action identity

The owner-local token binds at least:

```text
app_id / app_generation / schema_digest / policy_id
principal digest
operation_key / action family / logical target
resolved repository ID and branch ref
expected branch head OID
path and expected blob OID
patch SHA-256 and result SHA-256
new Git blob OID
normalized commit-message digest
current-writer and allowed-path evidence digest
issued_at / expires_at
```

Commit rechecks every load-bearing predicate and makes at most one request. Same key plus changed normalized effect is conflict. A timeout is never proof of failure.

## 13. GHP4 production proof

The first live canary must use a disposable, non-protected branch and an allowlisted harmless existing fixture file with more than 10,000 lines. It must prove:

1. exact successful patch and one resulting commit;
2. stale head refusal with zero commit;
3. stale blob refusal with zero commit;
4. wrong/unowned/protected path refusal with zero commit;
5. secret-shaped addition refusal with zero reflected secret;
6. lost-response reconciliation without second commit;
7. duplicate same-effect call returns the original effect;
8. changed payload under the same operation key is refused;
9. model-visible source exposure stays bounded to the intended context/read contract;
10. exact resulting GitHub bytes and commit actor are canonical.

Only this real path can support `PROVEN_LIVE` for the exact enrolled repository/action generation.

## 14. Required return packet

Every builder/reviewer return must include:

```text
operation key
protected/base/candidate SHA and merge base
exact changed paths and blobs
focused/full/hosted checks
RED-to-GREEN evidence
mutation/adversarial findings
review identity and exact reviewed head
current capability state
open source/collision/effect uncertainty
what was not made live
exact next action
```

A return remains nonterminal until Sol emits an explicit CONTINUE/REQUEST_REPAIR or ACCEPTED/STOP on the lawful carrier when a watcher-enabled dialogue exists.
