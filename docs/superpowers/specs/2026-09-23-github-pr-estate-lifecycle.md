# GitHub PR Estate Lifecycle Contract — 2026-09-23

## Owner and purpose

This is a bounded extension of the existing Sol Capability Fabric GitHub semantics. It does **not** create a second lifecycle, queue, database, registry, sweeper, retry plane, release owner, or GitHub control plane.

The job is narrow:

> classify one exact pull request from immutable current facts so an authorized caller can distinguish live work, legitimate gated work, safely closable historical carriers, and cases that require reconciliation.

The pure implementation is:

- `control_plane/github_pr_lifecycle.py`
- `tests/test_github_pr_lifecycle.py`

Original authoring procedure pin:

`mastermindx-market-intelligence/Mastermind@a7d2b3049e5cdc523e91e61a6e9d70a1cb911157`

Current release-compatibility review pin:

`mastermindx-market-intelligence/Mastermind@1a7d400294b0d37c460b963b8865b40a23173b58`

Both provide compatible `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1. The authoring pin is historical provenance, not release authority; action-time release must always re-pin current protected procedure and material-source compatibility.

## Estate invariant

An **open** PR should mean one of two things:

1. `KEEP_ACTIVE` — live future work remains and the carrier is still expected to advance; or
2. `KEEP_GATED` — live future work is deliberately parked behind a concrete owner, gate, and release condition.

Everything else must either:

- become a separately authorized `CLOSE_CANDIDATE`, or
- remain `RECONCILE_REQUIRED` until source truth is sufficient.

The classifier never closes, merges, deletes a branch, arms auto-merge, changes review state, mutates labels, or grants action authority.

## Binding safety rules

1. **Age is never closure authority.** Staleness can trigger reconciliation only.
2. **HOLD is not dead work.** An active hold/gate with owner + exact gate + release condition stays `KEEP_GATED`.
3. **Incomplete gate identity fails closed.** A hold missing owner/gate/release condition is `RECONCILE_REQUIRED`, never a close candidate.
4. **EFFECT_UNKNOWN is sticky.** A PR with unresolved prior effect uncertainty is `RECONCILE_REQUIRED`.
5. **Partial source coverage fails closed.** Missing current state, carrier, preservation, or source facts cannot be promoted into closure.
6. **Unique unpreserved truth stays open for reconciliation.** A records/research PR is not disposable merely because it is old.
7. **Explicit disposable/never-merge carriers may become close candidates only after current work is terminal/nonexistent and preservation is proven or legitimately not required.**
8. **Integrated/superseded terminal carriers may become close candidates only when the displaced truth is preserved.**
9. **CLOSE_CANDIDATE is evidence, not authority.** GitHub mutation still requires present action authority, current-source revalidation, one effect attempt, and readback reconciliation.
10. **KEEP_OPEN is evidence, not authority.** It may reinforce an independently established `ACTIVE` state or a fully identified `GATED` state. It cannot convert `UNKNOWN`, `TERMINAL`, or `NONE` work into active work; those contradictions require reconciliation.
11. **Free-text gate facts are bounded and secret-safe.** Owner, gate, and release-condition strings are bounded and refuse common credential/token material. A future gatherer should prefer typed identities/digests over copying arbitrary PR prose.

## Why this is required

The estate currently mixes materially different meanings inside the single GitHub state `OPEN`: active implementation, release-gated work, research, records, experiments, synthetic canaries, scratch harnesses, obsolete carriers, and historical evidence.

That ambiguity increases:

- duplicate-work and stale-owner risk;
- accidental merge/revival risk;
- CI/review inventory and search noise;
- recovery archaeology for every new Sol/Fable/worker session;
- pressure to treat age, title markers, or generic HOLD prose as authority.

The correct fix is semantic subtraction, not a vanity PR-count target.

## Real cases anchoring the contract

### Scratch replay carrier

Macro PR #6051 explicitly stated `DO NOT MERGE` / `Never merge this PR`, changed only scratch/workflow support, had completed exact-head CI, and its temporary Actions artifacts had expired. Its history remains preserved by GitHub after closure.

Disposition shape:

- work state: terminal/no live continuation;
- explicit disposition: never merge / close unmerged;
- preservation obligation: not required beyond immutable Git history;
- result: `CLOSE_CANDIDATE`.

### Parked continuity canary

Macro PR #6802 is also disposable/unmerged-only, but its exact carrier remains parked after Stage 1 and requires a specific same-carrier terminal Sol edge before cleanup.

Disposition shape:

- work state: gated;
- explicit future disposition: close unmerged;
- owner/gate/release condition: concrete and still outstanding;
- result: `KEEP_GATED`.

This distinction is load-bearing: the word "disposable" does not itself authorize closure.

## Follow-on composition

A later bounded Sol Capability Fabric GitHub composition may gather live facts and feed this pure classifier. That gatherer must reuse existing GitHub/native connector and release-assessment ownership. It must bind observations to current source identity/freshness, fail closed on contradictory source views, and pass only bounded secret-free facts into this classifier; the classifier deliberately does not become a gatherer.

Any close action must remain a separate, prepared, current-source-revalidated mutation with readback. No autonomous stale-PR sweeper is authorized by this contract.

## Initial drain law

For the current estate-reduction mission:

- close only high-confidence carriers that satisfy the contract;
- do not mass-close HOLD, draft, old, research, or records PRs;
- do not delete branches as part of ordinary closure;
- record the exact reason before closure;
- preserve canonical successors/evidence;
- leave ambiguous or unique-state PRs open and classify them for reconciliation rather than guessing.

Success is not "get below N PRs." Success is:

> every remaining open PR denotes live future work or a specific unresolved gate, while historical/disposable carriers no longer masquerade as WIP.
