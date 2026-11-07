# Verification and limits

## Executed-check design

Run from this directory:

```sh
python3 verify_research.py
```

The script uses only the Python standard library and finite synthetic examples. It imports no Mastermind/Macro implementation, contacts no network service, reads no market outcomes and writes only its local research result file. Its 24 checks comprise **18 finite arithmetic/temporal counterexamples and 6 package-structure checks**. The actual latest result, timestamp, script digest, failures/errors/skips and per-test output are recorded in `CONSISTENCY_RESULTS.json`.

The examples cover proportional and custom-basket ETF changes; offsetting trades; net versus gross issuance; fund/security splits; observed versus issuer-basis concentration; unobserved holder distributions; overlapping claims; dilution; price-only allocation changes; value units; public versus actual-system timing; latest dependency; correction vintage; partial amendments; omission ambiguity; and date/timezone precision.

Package checks require all A–L sections, all 36 future fixture rows, all 36 audit rows, resolvable internal file/source-anchor links, no inherited chat-citation tokens, and correctly formatted exact-source acquisition metadata. External URLs are cited source references, **not** the subject of a blanket automated link-availability certification.

## What these checks do not prove

They are not native K1/K2 tests, implementation acceptance tests, a backtest, legal advice, vendor entitlement proof, statistical power analysis, browser verification or production qualification. The 36 T-cases in the report are a **future implementation specification**, not 36 executed tests. The six primary hypotheses are proposed for registration through the existing evaluation owner; no outcomes were opened or alpha claimed.

## Source-grounding verification

The original mounted attachment was independently hashed: 59,389 bytes, 708 physical lines, SHA-256 `1b4ebf1874b23980931145534d3c4e2f926153b17559a33859c6acce5873dd4d`.

Repository identity and branch metadata were read live. Exact-revision file acquisition produced 66 source records with byte hashes. Relevant complete Macro subtrees were obtained after detecting root-tree truncation. Source-law procedures, K1 README, relevant workstream sections, selected PR records and workflow metadata were inspected. **Acquired does not mean fully reviewed.** Two bounded source-extraction actions were refused before execution and were not retried or routed around. The current Quiver implementation, ETF proxy details, static census contents, full V3 runtime state and complete K2-C production receipt therefore remain unrecertified.

Primary SEC rule/form material was checked, including rendered PDF tables for beneficial ownership and N-PORT, Form 4 instructions and foreign-insider exemption conditions. Vendor capabilities are explicitly documentation claims, not observations of licensed feeds. Literature is hypothesis/mechanism evidence, not a current performance guarantee.

## Publication verification

Before source publication, run the research checker and `git diff --check`; inspect the exact file set and confirm that changes are confined to `research/ownership_positioning_hardening_2026_10_04/`. `PACKAGE_MANIFEST.json` contains SHA-256/byte counts of the other package files, avoiding a circular self-hash. Verify committed file blobs against the local candidate and verify the remote branch head after push. Record the final immutable commit and PR in the publication response/PR body, rather than embedding a self-referential commit hash in the same commit.

Publication means the research recommendation is durably available for review. It does not mean the relevant owners accepted implementation, hosted repository CI passed, a PR merged, a production service deployed or an evidence family gained authority. No automated merge or rollout is requested.

## Reproducibility boundary

Source pins describe the immutable research cut, not a claim that moving branches stopped advancing. The later implementation must re-pin and recensus its actual owner/contract/consumer seam. A changed unrelated branch head does not invalidate this historical audit, but a semantic change to the incumbent owner must be reconciled before implementation.
