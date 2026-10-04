# Verification and evidence limits

## Executed mathematical verification

Command, run against this package's source:

```sh
python verify_mathematics.py --output verification_results.json
```

**Result: 18 tests passed; 0 failures; 0 errors; 0 skipped.** The exact script SHA-256 and Python version are recorded in `verification_results.json`. `mathematics_run.txt` preserves the run output. A second verification should execute the script, not merely read this statement.

The checks use finite synthetic populations, exact rational arithmetic where applicable, and elementary linear algebra. They demonstrate:

- zero correlation with nonlinear dependence, and pairwise independence without joint independence;
- highly correlated features retaining target-relevant differences, and independent noise adding no necessary predictive value;
- positive/negative clones, invertible transformations and false confidence from copied likelihood contributions;
- different meanings of spectral participation ratio and variance-equivalent count;
- undefined constant-feature correlations, an invalid pairwise matrix, nontransitive correlation thresholds and out-of-sample reappearance of covariance.

**They do not implement or test Mastermind's production validator.** No market observations, historical labels, model training, independence-testing library, real-source reader, portfolio, runtime or paid service was used. The tests are mathematical counterexamples, not an end-to-end feature or backtest. They are author-run, not an independent human/agent acceptance review.

## Repository inspection

The audit used immutable source pins:

- Mastermind: `a2646f458f9ff41ddcedd89b338be4a4349e6cd6`.
- Macro: `d2904d45fb2bbaf12d3dae4a35eacaaefcc8bad3`.

Observed evidence includes the full K1 contract README, selected native workstream and earlier recommendation passages, relevant path inventories, validator function inventory and both native test-function inventories. Those sources support the documented contract and ownership findings, not a claim that deployed producers satisfy them.

A subsequent deeper selected read of implementation/test/workstream ranges was blocked by the tool's safety check. No result was returned, and that action was not retried or moved to another carrier. Therefore:

- no full line-by-line implementation audit is claimed;
- no fresh execution of the two native K1 suites is claimed;
- no runtime liveness, source lease, historical data completeness or production consumer result is certified.

The 24-case acceptance matrix in the final report is a future implementation specification. Those cases are **not** falsely reported as passed by the 18 mathematical checks.

## Original and package integrity

Original filename: `deep-research-report (8).md`.

Original bytes: **25,833**. Original lines: **175**.

Original SHA-256: `be9d6bd856b59f8bdb4fca54c36dd7c18740732c0b18b36d0185c14ead0080b5`.

`source_report.original.md` preserves those exact bytes. `MANIFEST.json` identifies the final report, audit, script and receipts individually. Only report/publication files belong to this change. No existing protected contract, native source file, test, identity guard or workflow is weakened.

## Publication verification boundary

The Git commit and PR are the publication carrier, not research-policy acceptance. Final chat/PR receipts must state the actual commit, remote readback and observed hosted-check state; this package does not predict those results in advance. No merge or deployment is part of this audit commission.
