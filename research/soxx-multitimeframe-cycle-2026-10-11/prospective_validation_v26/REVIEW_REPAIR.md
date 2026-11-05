# V26 independent-code-review adjudication and verified repair

This supplement is current after the initial V26 publication `524e923d12cd2aeca21e4b9303fb0392d8654288`. It changes only the new offline validation component and adds tests; all v2–v24 source/results and the original thirty-one V26 tests remain byte-identical.

## The returned PASS was not accepted

Fabric task `soxx1338-v26-code-review-20261013b`, original root and parent `soxx1338-web-resume-20261013`, used the normal router's `minimax`/`mb` placement. It returned terminal rc 0 with a 742-byte PASS summary. It claimed both source SHA256s matched and thirty-one existing plus eighty-five additional tests passed, but supplied no retained falsifier artifacts. The eighty-five-test claim is **not counted as independently verified proof**.

Parent adjudication found reproducible defects in the exact reviewed source:

1. **UTC causality failed at a DST fold.** A November 1, 2026 New York fold-1 outcome at 01:30 is 06:30 UTC, later than a fold-0 fit at 01:45 (05:45 UTC). The original helper nevertheless admitted the future label. Equal-zone Python datetime comparisons ignore fold when comparing local fields. Paired-path completion, order/fill clocks and exposure clustering had the same weakness.
2. **Finite inputs could produce nonfinite accounting.** Opposing very large paired returns could cancel in the headline while loss-reduction/profit-surrender components overflowed to infinity. Equal benefit/harm values of `1e308` also produced break-even share zero because the denominator overflowed, rather than the correct one-half.

These are synthetic deterministic counterexamples, not newly observed trades or a claim that a historical SOXX bar occurred during a DST fold. Python's documented comparison semantics corroborate the clock mechanism: https://docs.python.org/3/library/datetime.html .

## Narrow repair and proof

The new helper normalizes aware clocks to UTC before any ordering. This does not introduce a venue calendar or reinterpret a source timestamp. Numeric validation rejects non-representable input and nonfinite derived accounting; scaled break-even arithmetic avoids overflowing its numerator and denominator.

Eight new tests were observed failing on the prior source (seven assertion failures and one overflow exception), then passing after the change. The final two-module discovery ran **39 distinct synthetic tests, all PASS**. Initial tests retained unchanged: git blob `48495ab5993fdd9feb6e5e04c8dc5c1efe8bf11d`. New clock/math falsifiers: git blob `9835eca63dca325ff79c366f0f51ac5cb66e9a06`, SHA256 `66f9f359e3f3957f0d7c3aa2a3cb9bab4e34b2d240b055c15744643609241d3e`. Repaired source: git blob `7e3f9d52cc85ad3236e388877ebd8131ece5c198`, SHA256 `92c8f202fc43ec173da966228a5b21668fe8abf47337deb8b190653750443362`.

Run: `python -m unittest discover -s tests -p 'test_soxx_v26_*.py' -v`.

The prior review is **REJECTED_AS_ACCEPTANCE**, not silently converted into a positive receipt. The repaired candidate requires its own independent review and hosted CI. The former v21–v24 accounting reviewer remains unresolved on its original carrier and was not duplicated or touched by this code-audit task.

## Research and source continuation

`PROSPECTIVE_ANALYSIS_CONTRACT.md` specifies the unchanged parent entry/control comparison, the two separate checkpoints, complete entry-universe requirements, whole-cohort unknown-fill treatment, exact profit/loss decomposition, dependence/multiplicity and fixed-window stopping. It provides a synthetic clipping-target sign reversal, not fitted market evidence. It explicitly withholds unqualified confidence, power, portfolio-performance and trading claims.

A new bounded M2 pathname-only check of `/Volumes/Mastermind/market-data/tiingo/receipts/boats-bars` returned just the two original October 11 receipt paths with prefixes `ae742fbb3d8427d25c200104` and `e279bcc1ffe5230a5d1bdb40`. No new SOXX historical receipt appeared in that check. It did not repeat raw/L1 qualification or inspect other archive families. Macro #8698 / comment 6137771857 remains the existing source-owner request; there was no new provider authentication, source collector, market-data export, schedule, order or deployment.

**Research remains incomplete.** These repairs improve trustworthy evaluation; they do not validate any cycle-failure exit's performance on independent market data.
