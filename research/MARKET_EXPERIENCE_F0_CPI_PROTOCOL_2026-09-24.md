# F0 CPI source-component protocol

Status: frozen before this operation reads CPI values. Internal technical validation,
not a stock-universe pilot, source admission, forecast experiment, or training grant.
Parent: market-experience-direction-20260924-astra-001 / Mastermind #967.
Direct work: PRINCIPAL_JUDGMENT on source/temporal integration; no worker launched.
Protected procedure pin: 819abc8c23609cdded2b33f6e1bfc7854bd5c847 (1.0.1).

## Fixed source and selection

Use only Macro commit b9d23ca4bce4308fa7466c4e0f5d318168a50f6f:
- Collector manifest: data/fred_vintage/release_targets/manifest.json,
  Git blob b4fe4314097c93847b691060beeb8adc35a79546.
- Artifact: data/fred_vintage/release_targets/CPIAUCSL_all_vintages.parquet,
  expected 134327 bytes, SHA-256 abc6b65a873a3d6de63d85379c86b61f71f99480354f46915c391d506970718b.
- Native normalization/reconstruction: engine/release_target_truth.py,
  Git blob c9da53421cc8ab2ed7cdef2f3097a64f5e8ee222.

CPI is selected because it is the existing Market Memory W1B.0 intake source,
not because of a measured predictive result or convenient realized return.
The six other manifest series are excluded from this unit. No replacement source.
No earnings/GMI held body, holdout, stock outcome, model or provider is accessed.
Metadata seen before freezing: collector claims 292553 rows, 955 periods,
376 vintage dates, period range 1947-01-01 to 2026-08-01, requested vintage
start 1997-01-01, completed_at 2026-09-23T21:19:16+00:00.
These are claims to verify, not proof of historical operational possession.

## Fixed checks and measurements

Verify commit-addressed manifest bytes, declared artifact hash/size, parquet footer
row count, exact series and output_type=2, normalized rows/periods/vintage count/range.
Report any normalization reduction explicitly; a silent denominator change fails.
Use native normalize_full_vintage_frame, never copied financial calculations.
Invoke native reconstruct_release_target for January of 2019, 2020, 2021, 2022,
2023, each with April 1 of that year as the as_of bound. These five evenly spaced
technical cases are not a predictive sample. One negative case: January 2019
with as_of 2018-12-31 must be unavailable. Selection is fixed before value reads.
Only status, date/provenance integrity and timings leave the local process; do not
publish levels, computed release targets, source rows or original data bytes.
Measure read/decode/normalization/reconstruction wall and process CPU time;
report process-lifetime peak RSS and dataframe bytes separately. One pass per
stage/case; no p95, fleet throughput, repeated-trial alpha or acceptance-rate claim.

## Boundaries

Read existing immutable Git objects into memory; never run the source intake,
write private Market Memory state, alter Macro, fetch a new vendor dataset,
create a source store or publish user-facing intelligence. Training eligibility,
promotion, ranking, sizing and action remain false. Legal ML/redistribution rights
remain unestablished; the collector manifest is not a license. This uses existing
company-held data for internal technical validation only. The output is a research
measurement receipt, not another registry or admission decision.

A valid source component does not supply a 50-issuer/five-year universe, historical
membership, event-source coverage, acquisition/served receipts or a learner.
This entire inspected vintage artifact is development-visible for this programme;
it must not later be advertised as an untouched evaluation set. Date-only vintage
metadata is not intraday release timing. Original-source/canonical rights and
actual-output owners still control any later product or learning use.
