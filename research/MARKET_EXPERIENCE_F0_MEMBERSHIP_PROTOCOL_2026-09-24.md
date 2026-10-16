# F0 historical membership recovery protocol

Status: frozen before decoding upstream data in this unit. Internal source qualification only.
Operation: market-experience-direction-20260924-astra-001; existing Mastermind #967.
Procedure pin: a29161fa0a44cca9927afe042b5f7ea25aae1736. Native GitHub reads returned the same full-file blob identities for the loaded COLD_START, ACTIVE_EXECUTION, WEB_CEO_DELEGATION, RECONCILE_STATE, CLOSEOUT and DELIVERY_WORKFLOW procedures. The refused compound host recovery command is not retried.

## Question and owner
Does the upstream used by the existing Macro historical-membership collector supply a recoverable, internally consistent development input for 2019-2023? This does not select a stock cohort or accept production/PIT/training rights.
Existing owner: Macro scripts/residual_alpha_pit.py at 5600bb63b27978031769eb428911fe9b46572a92, blob cc3bd319a1c00fabba5e8d95df176be7402aedc7. It names fja05680/sp500/sp500_ticker_start_end.csv and data/breadth/sp500_pit_membership.parquet. The exact output object is absent at that Macro commit and at the checked macro-main local path. No collector is run and no source store is created or changed.
Existing consumer semantics inspected: scripts/s13_reversal_phase0.py::_eligible at the same Macro commit, blob dadcb0043ba5ed380f4984ea4e2bf360a1ebd72f, uses inclusive start/end with null end open. Its evaluator and TrialLedger must NOT be imported or run by this audit. This audit compares representations; it is not a new production reader.

## Fixed external inputs
Repository fja05680/sp500, commit a2430f2af0c79ddf0748e91de11bdeb1616ab5a7:
- sp500_ticker_start_end.csv: Git blob 3ed3b0e8d9e6e63730c153ee1f13ddaf6ed281bb, 28058 bytes.
- S&P 500 Historical Components & Changes (Updated).csv: Git blob 656b033be9418db272f1903f4f8e79a2a8664e6a, 5530907 bytes.
- LICENSE: Git blob 1702a4df51e2c2a0a96ede6b10afeb880b976bbd, 1100 bytes.
- README.md: Git blob 43072b7901eaaedbc63a523a1040ac91b5c65dbb, 4847 bytes.
Check exact bytes and Git object hashes before parsing. Maximum input 8 MiB each; no moving-master read or source substitution. Container copies are temporary analysis inputs, not another canonical market-data store. Only code, provenance, bounded aggregate results and digests may be published; no bulk membership tables.

## Fixed structural tests
Inspect schemas, strict date validity, interval inversion, duplicate/overlapping intervals, symbol-normalization collisions and source date bounds. Never drop malformed rows to make a source pass. Expose absent publication/acquisition clocks; effective membership is not historical operational possession.
Compare the two representations at every quarter-end from 2019-03-31 through 2023-12-31 (20 calendar dates, not claims about trading-session closes). Compare inclusive and exclusive end-date interpretations as explicitly separate diagnostics. Any inspected boundary mismatch is development evidence, not an excuse to silently change native semantics. Also test the first and last observed snapshot dates as coverage-boundary diagnostics, reporting their source-dependent identities.
Emit aggregate set differences and member-set digests, not stock outcomes, return calculations or an issuer-mapped cohort. Keep all expected dates in the denominator. Dates outside recorded snapshot bounds are uncovered; never extrapolate open intervals past the source coverage boundary. Source completeness is not established merely by member counts near 500.

## Source limitations and rights
The upstream README describes a book-associated historical seed plus later Wikipedia/manual changes, warns selected changes are incomplete, and discloses potential missing early members. It treats symbols as tickers, not durable issuers. The repository LICENSE is MIT; record it and attribution, but do not equate that file with accepted downstream ML, index-data, display or redistribution entitlement. A later review must settle permitted uses and canonical historical identity mapping. No inference/model spending, training, promotion, production-data admission or forecast trial is authorized by this protocol.

## Outputs and stop boundary
Produce a tested offline source-comparison utility and an exact source-recovery receipt, with execution environment and uncertainty. If representations disagree, retain both hashes and the failed dates; select neither silently. Next action belongs to the existing universe/Data OS owner: correct or qualify the existing acquisition/normalization path and join only through native historical identity. The 50-issuer/five-year pilot remains unadmitted until source quality, rights and event joins pass.
