# Autonomy Release Compatibility and Review Reuse

**Status:** `SOURCE_LAW / PROCEDURAL ACCELERATION / PRODUCTION_INERT`  
**Date:** 2026-09-02  
**Owner:** Sol, AI CEO of Mastermind-X  
**Operation:** `autonomy-release-flow-acceleration-20260902-sol-001`  
**Protected pickup:** `mastermindx-market-intelligence/Mastermind@caa47c1e66fe36dc3521299c918f4b9e7b2a47ca`  
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1

## 1. Observable mission

Remove repeated branch joins, duplicate full CI runs and duplicate semantic reviews that are caused only by path-disjoint protected-master movement, while preserving every correctness property that matters:

- immutable candidate identity;
- current governing source;
- collision detection;
- latest-base integration proof;
- unresolved-review truth;
- expected-head release;
- effect reconciliation;
- production-proof honesty.

This law changes release procedure only. It creates no merge queue, state store, database, lifecycle, scheduler, retry plane, authority registry, provider action, deployment or production capability.

## 2. Problem being corrected

The current estate frequently applies this loop:

```text
candidate reviewed
-> protected master moves on unrelated paths
-> candidate branch joins protected master
-> candidate head changes
-> full CI reruns
-> prior review is treated as stale
-> full semantic review reruns
-> protected master moves again
-> repeat
```

The loop is rational when protected movement changes candidate code, dependencies, governing source, security assumptions or effect semantics. It is waste when the candidate-owned blobs and every material source/dependency remain identical.

A branch ancestry number is not a product capability. `behind_by=0 is not a release property`.

## 3. Two distinct receipts

Every release-sensitive carrier distinguishes two immutable concepts.

### 3.1 `SEMANTIC_HEAD`

`SEMANTIC_HEAD` is the exact candidate commit whose candidate-owned source/test/document blobs received substantive review.

It binds:

- repository and PR;
- operation key and carrier;
- exact candidate commit/tree;
- exact candidate-owned path list;
- blob identity for every candidate-owned path;
- exact governing source set and its blob/commit identities;
- declared dependency closure;
- capability and non-goal boundary;
- substantive review findings and disposition.

A semantic review is about those semantics. It is not automatically invalidated by an unrelated commit appearing on protected master.

### 3.2 `INTEGRATION_PROOF`

`INTEGRATION_PROOF` is the current proof that the exact `SEMANTIC_HEAD` composes safely with the latest protected base.

Preferred proof is the `latest protected-base merge ref` produced by GitHub for the PR, or an equivalent immutable integrated candidate when repository mechanics require one.

It binds:

- current protected-base commit;
- exact `SEMANTIC_HEAD`;
- integrated tree or merge-ref commit;
- protected-base movement path census;
- candidate-owned path/blob preservation;
- governing-source material comparison;
- dependency-closure intersection result;
- mergeability/conflict result;
- required repository and security checks on the integrated candidate;
- unresolved review/thread state;
- generated time and currentness.

`semantic review and integration proof are separate receipts`.

## 4. Closed compatibility outcomes

Current-base reconciliation produces exactly one conceptual result:

```text
REVIEW_REUSE_ALLOWED
FULL_REREVIEW_REQUIRED
RELEASE_BLOCKED
```

### 4.1 `REVIEW_REUSE_ALLOWED`

Review reuse is allowed only when all of the following are proven:

1. the exact PR, operation, carrier and `SEMANTIC_HEAD` are unchanged;
2. `candidate-owned blobs are byte-identical` to the reviewed semantic head;
3. the complete candidate-owned path set is unchanged;
4. the `governing source set is materially unchanged`, or a current Program-CEO comparison proves that movement is non-material to this carrier;
5. protected movement does not intersect candidate-owned paths;
6. the declared dependency closure does not intersect protected movement in a way that changes behavior, authority, security, build/runtime compatibility or proof meaning;
7. the candidate remains mergeable with the current protected base;
8. required repository/security checks pass on the latest protected-base merge ref or equivalent immutable integrated candidate;
9. no unresolved blocking review, review thread or known counterexample applies;
10. the capability boundary remains identical and no new production/live claim is introduced.

When those conditions hold:

```text
semantic review = reused
integration proof = refreshed
candidate branch = unchanged
```

A short current compatibility review records the comparison and release consequence. It does not re-perform the entire substantive semantic review.

### 4.2 `FULL_REREVIEW_REQUIRED`

Full substantive re-review is mandatory when any of the following is true:

- `candidate-owned blob changed`;
- candidate-owned path set changed;
- `governing source changed materially`;
- `dependency closure intersects protected movement` and compatibility cannot be proven mechanically or by bounded current review;
- `authority, identity, security, effect, retry, or persistence semantics changed`;
- an accepted review finding is touched, invalidated or newly reachable;
- a compiler/runtime/library/toolchain change materially affects the candidate;
- the candidate now claims a stronger capability state;
- `production or live proof is owed` and the evidence epoch changed;
- the prior review did not bind an immutable semantic head;
- there is an `unresolved blocking review` or a new counterexample.

Full re-review remains on the same logical operation/carrier unless the work itself changed into a new operation.

### 4.3 `RELEASE_BLOCKED`

Release is blocked, without branch replay or carrier failover, when:

- current protected source cannot be read;
- merge-ref/integrated-candidate identity is unavailable or ambiguous;
- candidate blob preservation cannot be established;
- collision or dependency impact is unknown;
- required latest-base checks are unavailable/nonterminal/failed;
- review state is ambiguous;
- effect state is unknown;
- expected-head or current protected-base identity moves during the release action.

## 5. Branch movement law

`No branch join is permitted solely to refresh ancestry`.

Specifically:

- Do not merge protected master into the carrier merely to make `behind_by=0`.
- Do not rebase/reset/force-update a reviewed semantic branch for currentness cosmetics.
- Do not create a second PR because the base moved.
- Do not regenerate byte-identical candidate source on a new head merely to obtain fresh review timestamps.
- Do not require an independent reviewer to restate an unchanged semantic verdict after every path-disjoint base movement.

A history-preserving branch join remains valid only when it is actually needed to compose source, resolve a real collision, consume a changed dependency, repair the candidate or produce an integrated artifact that GitHub cannot otherwise test.

When no semantic join is needed, the source branch stays frozen and GitHub's current merge ref carries integration proof.

## 6. Latest-base CI law

This law removes duplicate proof, not proof itself.

Required current integration checks still run against the latest protected-base merge ref or equivalent immutable integrated candidate.

The release packet must not count both of these as separately necessary when they prove the same composition:

```text
manual current-base join + full CI
synthetic latest-base merge ref + full CI
```

Use one current integration candidate.

If protected base moves after a successful integration proof:

1. recompute protected movement and material/dependency intersection;
2. obtain a fresh integration proof against the new base;
3. reuse the semantic review when Section 4.1 remains satisfied;
4. require full re-review only when Section 4.2 is triggered.

The final release still requires an `expected-head merge` and an action-time read of the protected base used by the passing integration proof.

## 7. Review identity and findings

A review is reusable only when it is anchored to the immutable `SEMANTIC_HEAD` and names its scope.

Findings remain attached to the candidate semantics that caused them.

- A fixed candidate requires a new semantic review.
- A path-disjoint protected change does not dismiss or recreate findings.
- An unresolved blocker remains a blocker regardless of green integration CI.
- A dismissed review is not silently resurrected as approval.
- A reviewer identity/account is evidence of independence, not authority by itself.

Records-only source law may use direct Program-CEO acceptance when its governing wave does not specifically require an independent technical reviewer and exact source-law tests discriminate the boundaries. Executable implementation receives independent semantic challenge where its governing law requires it. Neither case requires a second reviewer merely because protected ancestry moved.

## 8. Material-source comparison

Current compatibility review compares the sources that can change the meaning of the candidate, not arbitrary repository volume.

The material set includes as applicable:

- current Skillpack procedure used for the release;
- governing architecture/spec/plan and narrow precedence amendments;
- authority/policy contracts;
- schemas and interfaces imported or consumed by the candidate;
- installers/runtime manifests/closed path allowlists affected by the candidate;
- production-proof or evidence contracts claimed by the wave;
- explicit no-rebuild and effect boundaries.

Generated views, unrelated tests, unrelated product source, research prose outside the authority chain, and path-disjoint program releases do not automatically invalidate semantic review.

Unknown materiality fails closed. It does not justify a blind current-base join.

## 9. Release action

A lawful release using review reuse performs:

```text
read protected master + current Skillpack
read PR + exact SEMANTIC_HEAD
verify candidate-owned paths/blobs
compare protected movement with owned paths and dependency closure
compare governing material source
read latest-base INTEGRATION_PROOF and required checks
read reviews + unresolved threads
classify REVIEW_REUSE_ALLOWED | FULL_REREVIEW_REQUIRED | RELEASE_BLOCKED
Program-CEO acceptance when allowed
expected-head merge
post-merge protected readback
truthful capability-state update
```

Any mutation ambiguity is `EFFECT_UNKNOWN` and reconciles through the same PR/operation. No duplicate merge, carrier, branch or failover is permitted.

## 10. Explicit non-waivers

The following statements are forbidden and must remain false:

- `green CI grants merge authority`;
- `path-disjoint means production-proven`;
- `review reuse grants execution authority`.

Review reuse also does not waive:

- current source pinning;
- latest-base integration checks;
- expected-head protection;
- unresolved blocker handling;
- effect reconciliation;
- production/browser/provider proof when owed;
- capability honesty;
- post-merge readback;
- durable closeout.

## 11. Current Autonomy application

After this law is protected, Autonomy carriers should stop spending worker/reviewer/CI cycles on ancestry-only joins.

For each open carrier:

1. identify the last substantively reviewed semantic head;
2. freeze its owned blob set and material-source set;
3. use the current GitHub merge ref for integrated proof;
4. run a bounded current compatibility review;
5. reuse or re-run semantic review according to Section 4;
6. release or hold without creating replacement carriers.

This law does not itself release any current carrier. Every carrier still satisfies its own substantive implementation, proof and production gates.

## 12. Acceptance

This source-law wave passes when:

- the test-first contract is green;
- `REVIEW_RETURN.md` and `RECONCILE_STATE.md` encode the same separation;
- no source path outside the five-path ceiling changes;
- current repository/security checks pass;
- a fresh Program-CEO review finds no merge-safety, authority, effect or proof-honesty regression;
- the PR remains production inert;
- expected-head release and protected readback are separately performed.

Protecting this law establishes `PROCEDURE_READY / PRODUCTION_INERT`. Its value is realized when the next path-disjoint base movement refreshes integration proof without moving the semantic branch or repeating semantic review.