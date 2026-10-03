# C2 R1 — exact numeric policy candidate and reproducible correction

**Status: candidate repair implemented; external confirmation and W0 source-owner admission remain open.** C2's return is #1183 comment 5972911613, explicitly consumed in comment 5973159076. C2 independently checked owner receipt integrity; neither that check nor this correction is independent whole-program approval.

## Defect and preserved RED evidence

The previous comparator definition said “Decimal” and “unrounded result” without a fixed context or exact representation. For the same owner-backed values, caller precision 4 produced display **6.40**, while precision 28/100 produced **6.43**. No I3 engine existed to fail: this was a real proposed-contract defect before freeze.

`evidence/R1-red-test.json` retains the old comparator/schema hashes, test-driver hash recorded before execution, command result and both expected failures: no frozen context-independent arithmetic policy and no distinct exact-rational field. The test-only witness also reproduces the old Decimal-context divergence. No owner test or CDV-1 code was changed.

## Bounded exact representation

The candidate now specifies base-10 finite string parsing to integer coefficient/scale, exact aligned subtraction and a reduced fraction for `100*(after-before)/before`. The denominator must be positive; a nonpositive baseline has no percentage and an explicit reason. Original owner value strings and receipts stay unchanged. The exact zero fraction is `0/1`.

Input bounds are 96 characters, 64 coefficient digits and 24 fractional digits. Each rational numerator/denominator has at most 128 digits; derived finite/display decimal strings have at most 96 characters. Exponent notation, nonfinite values, floats, noncanonical spellings and size violations are refused. These limits are computation/resource bounds, not economic materiality or near-zero eligibility rules.

`relative_change_exact` contains the exact reduced numerator and positive denominator. `relative_change_percent` is only a two-decimal display string, produced by one integer half-even rounding step. No repeating rational is labeled an exact decimal expansion. There is no Decimal context, exponent range or trap to inherit; input/output limits are explicit instead. Negative rounded zero is canonically `0.00`.

For the already exposed AAPL input pair, the test-only arithmetic witness produces exact difference **25126000000 USD**, exact percentage **502520/78207**, and display **6.43%**. This remains review arithmetic, not an I3 emission, admitted comparable-state result, organic-growth claim, materiality classification or predictive evidence.

## Executable discriminators

`test_comparator_policy.py` is an isolated W0 specification witness, not a runtime module or an owner substitute. It verifies the fixed policy/field contract, the original context-leak reproducer, the exact AAPL arithmetic, hostile Decimal contexts (precision/rounding/tiny exponent bounds/all traps), positive/negative half-even ties, both sides of a boundary, canonical zero, exact fractional absolute change, nonpositive baselines, invalid/bounded inputs, independent Fraction equality and display error bounds. It has no issuer/metric/source/basis/rights resolution or emission function, and production code must not import it.

The candidate JSON schema now distinguishes exact versus display representation and enforces their null coupling. Shape tests cover missing exact fractions, forbidden refusal numerics, nonpositive denominators, non-two-decimal display and negative zero. Semantic admission must still prove actual numeric equality, gcd reduction, owner references, rights and time ordering; schema validation alone does not establish any of them.

This is a change only to the unregistered W0 candidate and its tests. FIF/CDV-1/Earnings/Capital implementations, accepted published schemas, original audit files, trial registries, runtime state and source custody are unchanged. All W0 review/owner gates and parent W1–W11 obligations remain in force.
