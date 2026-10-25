# W-LIQ.3 canonical producer adapter: implementation plan

**Goal:** the existing research lab can consume the repaired Macro producer without inventing clocks, values, quality, or trading authority.
**Carrier:** existing Mastermind PR #124; no replacement lab or PR.
**Architecture:** one pure adapter validates the frozen raw producer contract and copies its event reference into the existing SourceStateRef. Existing eventization and ledgers remain the only episode path.
**Scope authority:** Chairman's 2026-09-15 Aion integration continuation; #123 sequencing; #6296 acceptance comment 5539622225; #124 review comment 5385315696.
**Source pin:** Mastermind 8de062fb3b5a327466cd98cda0dc7d44b8fd229d integrated with #124 head 7bd6dbbc8d93bf2063a820cb93fa5c3cf92ce9da. Producer sample blob 89a1ac142d4c9545b8ef1a1237430cf2cd7b35bd from macro 67c0fc151bffa8729610707979916a9855b36b0e.
**Direct execution reason:** PRINCIPAL_JUDGMENT / CRITICAL_PATH_SHORTCUT: the unresolved issue is the exact semantic boundary; no other original worker binding is proven. No provider worker is spawned.

## Contract and non-goals
- API: adapt_producer_state(payload, *, as_of) -> SourceStateRef | None; explicit timezone-aware evaluation cutoff, no wall clock.
- Copy evidence_available_at into observed_at and first_known_at into known_at. Validate every carried evidence date and duplicate clock; never repair/backdate the supplied clock.
- Require explicit canonical magnitude_z field/unit. Raw monetary_impulse and its sign remain distinct from standardized deviation; their signs need not agree.
- Copy event-reference freshness, data confidence, coverage, quality, conditions and component receipts. Global quality.status is a separate diagnostic, not a replacement classifier.
- Preserve valid null/zero-direction observations as no event reference; malformed or internally inconsistent evidence raises ContractError. Flat direction labels may still have a nonzero raw sign.
- No empirical study, threshold selection, probability, future-liquidity forecast, UI, scheduler, publication, new ledger, or Prophet authority is introduced.
- Historical reconstruction remains separate from original-hypothesis case studies and genuinely prospective first-known observations.

## Test-first sequence
1. Run the five existing lab suites on the integrated tree (baseline: 19 tests pass).
2. Preserve the exact producer JSON as a repository-owned fixture with blob provenance; it is an old sample, not live proof.
3. Add discriminating adapter tests: clocks/aliases/contributions, units/values, two label vocabularies, identity, finite numeric types, nulls, stale data, copied-data isolation, and explicit as-of cutoff. Observe failure before implementation.
4. Implement only the pure adapter; require a real sample through adapter -> existing eventize. Synthetic material events are labeled as synthetic.
5. Add a regression proving stale/low-coverage/low-confidence low-z observations cannot reset an existing episode. Repair the existing eventizer only if the regression fails.
6. Run focused and adjoining suites; inspect diff and compare exact remote head before a normal fast-forward push to #124. Keep draft and no auto-merge.
7. Record exact evidence, remaining gates and continuation in this owning research directory and #123/#124. Independent review and current-head CI precede acceptance. No production claim.
