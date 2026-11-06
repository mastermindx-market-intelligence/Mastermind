# Source Continuity Moving-Collider Evidence Successor

## Delivery amendment — 2026-11-06

The current Chairman authorized source-only completion when task qualification cannot be completed. This amendment supersedes the historical requirement below to finish a live Macro canary and a separate independent review before this bounded source merge. The current Web review policy and any actual repository approval/security/release rules still govern.

The original combined local pytest invocation was refused before dispatch by the platform safety layer. It remains unexecuted and must not be retried through a shorter command, different harness or different carrier. This source recovery uses syntax, exact-diff and static custody/resource review; natural hosted source and merge-group CI remain authoritative. Earlier test/cost figures below are historical evidence, not fresh execution receipts.

This amendment changes source-delivery sequencing only. The real high-churn Macro canary, canonical remote-complete acceptance, writer release and structural-scale product acceptance remain unproven. Macro #8312 and existing runtime/publication holds stay frozen. The 490-PR, 1,152-call, 128-MiB, 300-second and 5,000,000-byte limits remain unchanged; no scalar ceiling increase or new access/merge/trading authority is granted. Source incorporation is not runtime acceptance.

### Ordinary collider identity correction

Static review found that a PR could move during either ordinary files-read window, leaving the receipt's roster identity paired with another head's files. The existing collision owner now reads the PR detail after ordinary collider files and requires the PR to remain open at the exact observed number, head, base and repository identities. Initial and nonconditional second censuses apply this check; conditional revalidation applies it to freshly proved moved colliders. A changed identity refuses without following the newer head or repeating the census. Stable conditional identities retain their first checked evidence, and saturated immutable tree evidence retains its existing path.

The additional detail reads share the existing call, byte and time budget. For the historical one-moved-collider example, two extra detail reads imply 1,000 calls and 152 calls of headroom; this is static arithmetic, not a fresh measured result. Collision-heavy cases still refuse on the existing ceiling. These checks establish bounded observations, without an atomic GitHub snapshot or a writer lock; the protected disjoint-classification behavior is unchanged. Added fixture cases cover movement, closure and malformed identity in both read windows and both transport paths. Their execution is left to natural hosted CI.

**Operation:** `source-continuity-moving-collider-evidence-successor-20260924-sol-001`
**Canonical owner:** Mastermind #346
**Protected pickup:** `819abc8c23609cdded2b33f6e1bfc7854bd5c847`
**Predecessor semantic owner:** protected #860 / `5f62e9f6119cc3e3bc542a793ba96731e063e3a1`

## Goal

Remove Source Continuity starvation when an already-colliding foreign PR moves its head but, after fresh proof, still contends for exactly the same target-owned path set. Preserve one verifier, existing budgets, fail-closed custody, and explicit downstream evidence freshness.

## Trigger

Macro #7797 owns `.github/ci/legacy-jobs.yml`. Unrelated active PRs repeatedly move that same shared manifest while #7797's 2–3 minute collision proof runs. Three protected remote-complete attempts refused `REMOTE_PROOF_CHANGED`; concrete colliding heads moved during every proof window. Hosted/review/current-main evidence for #7797 is otherwise green.

## Accepted design

For an identity-complete first-pass collider:

1. stable identity reuses first evidence;
2. moved identity is freshly re-proved by the incumbent collision evidence owner;
3. derive `overlap_projection = sorted(intersection(target owned paths, foreign changed paths))` for ordinary PRs;
4. for saturated PRs derive the sorted owned paths whose existing tree evidence has `base_entry != head_entry`;
5. movement passes only if the old and new non-empty overlap projections are exactly equal;
6. growth, shrink, substitution, disappearance, new collision, malformed evidence or incomplete census refuses.

Legacy identity-less injected transports retain protected #860 exact-snapshot behavior.

## Receipt binding

Source receipts gain additive `collision_evidence_fingerprint`, a SHA-256 over canonical sorted current collider evidence including PR number, available immutable identity, exact overlap projection, and existing saturated evidence where applicable. Any moved collider therefore changes the receipt fingerprint even when its overlap projection is safely equivalent. Downstream collision adjudication binds to this fingerprint and may not silently reuse a prior adjudication when it changes.

Source receipt payload version becomes `v2`; writer-gate remains `v1`. Existing schema envelope strings stay unchanged.

## Frozen resource and authority boundaries

Unchanged:

- max open PRs: 490 (inherited from protected Macro-490 scale successor #982)
- max HTTP calls: 1,152
- normalized bytes: 128 MiB
- cooperative read budget: 300 s
- per-response body cap: 5,000,000 bytes
- combined 490-estate moved-collider proof: 998 calls / 154 calls headroom, 332,297 normalized bytes
- protected Macro-490 adverse scale proof remains the tighter envelope: 1,140 calls / 12 calls headroom
- subject PR / branch / source / base revalidation
- dirt/unpushed/effect rules
- no cache, cursor, retry service, GraphQL/POST path, lock, queue, persistence, lifecycle, receiver-transfer or merge authority.

## Exact source ceiling

1. `control_plane/source_continuity.py`
2. `scripts/source_continuity.py`
3. `tests/test_source_continuity_relevant_collision_semantics.py`
4. `tests/test_source_continuity.py`
5. `tests/test_source_continuity_census_budget.py`
6. this plan

## TDD / completion

RED before production code for same-projection moved collider, saturated same-projection movement, source-v2/writer-v1 version isolation and collision evidence binding. Safety tests for swapped/grown overlap remain green.

Then require focused GREEN, complete `tests/test_source_continuity*.py`, D8, compile/diff/exact-scope, existing resource ceilings, independent exact-head review, current-base integration, canonical remote-complete and one real high-churn Macro canary before protected release. Source merge alone remains `BUILT_NOT_PROVEN` until the real canary succeeds.
