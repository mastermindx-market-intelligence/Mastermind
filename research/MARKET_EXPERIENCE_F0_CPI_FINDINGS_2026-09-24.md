# F0 real-input CPI component: measured findings and integration decision

Scope: internal source-component validation, not the stock pilot or a forecast.
Parent operation/carrier: market-experience-direction-20260924-astra-001 / #967.
Procedure pin: Mastermind 819abc8c23609cdded2b33f6e1bfc7854bd5c847, Skillpack 1.0.1.
Protocol: MARKET_EXPERIENCE_F0_CPI_PROTOCOL_2026-09-24.md, frozen before value reads.
Protocol SHA-256: 306325a2b3d8a6bd5fd612745a71cf49065cb15bd58da3787d73ca664c780ad8.
Receipt: MARKET_EXPERIENCE_F0_CPI_RECEIPT_2026-09-24.json.
Probe SHA-256: 9714a987b81d2b46325c113786c4294181a4066195d99380bbd332f2ef1f1dc7.

## What became proven

The exact company-held CPIAUCSL artifact at Macro
b9d23ca4bce4308fa7466c4e0f5d318168a50f6f matches its collector manifest:
134327 bytes, SHA-256
abc6b65a873a3d6de63d85379c86b61f71f99480354f46915c391d506970718b.
The manifest Git blob is b4fe4314097c93847b691060beeb8adc35a79546.
The unmodified native normalizer/reconstructor in engine/release_target_truth.py
is Git blob c9da53421cc8ab2ed7cdef2f3097a64f5e8ee222.
All bytes were read from immutable Git objects; mutable checkout data was not used.

The real input contains 292553 rows, 955 distinct observation periods and 376
vintage dates. Native normalization retained every row: reduction=0. Observation
periods span 1947-01-01 through 2026-08-01; actual vintage dates span 1997-01-01
through 2026-09-11. The collector completed at 2026-09-23T21:19:16+00:00.

The five predeclared January cases for 2019-2023 reconstructed with their own
eligible native release vintage by their April 1 cutoff. All preserved the native
same-vintage provenance, no cross-vintage fallback and the non-official-proxy flag.
The negative January 2019 case at cutoff 2018-12-31 returned the expected
current_period_not_available_by_as_of absence. No levels or target values were
printed or published. These are structural checks, not independent forecast trials.

## Measured resource use

One real-input pass per stage/case; no p95 or throughput extrapolation:

| Stage | Wall seconds | Python process CPU seconds |
|---|---:|---:|
| Read pinned Git artifact | 0.077315 | 0.004452 |
| Decode parquet | 0.018023 | 0.014365 |
| Native normalization of 292553 rows | 0.331002 | 0.308874 |

Six native reconstruction calls each took approximately 0.295-0.352 seconds.
They use the existing public native API, which normalizes within each call; no
bespoke cached-vintage selector was invented for this benchmark.
Raw dataframe deep bytes: 25744796; normalized dataframe deep bytes: 25781366.
Process-lifetime peak RSS: 240779264 bytes (about 240.8 decimal MB). This includes
imports and all stages, not per-stage incremental memory. Parent Python CPU time
excludes subprocess CPU, including Git, and is not a total-host cost measurement.
Darwin; Python 3.14.7; pandas 3.0.5; pyarrow 25.0.1. Thread environment capped
OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1; parquet decode explicitly nonthreaded.
The complete probe host process 18940 exited 0 in 3.79 seconds. Instrumentation
suite: 49 tests passed in 2.99 seconds, host process 18146 exit 0.

## Integration ruling

Observation-history length and vintage-history length are separate coverage axes.
This artifact does NOT establish knowledge of 1947 information as it stood in
1947. It contains later vintages of older observations. Date-only vintages also
cannot prove intraday publication timing. Collector completion in 2026 cannot
prove Mastermind's possession or served output in a historical year.

Extend the existing F0 crosswalk to cite this verified source component. Keep
Market Memory operational/actual-output receipt requirements intact. The W1B.0
source module remains context-only with training/promotion disabled; this audit
never calls its intake or writes its store. The collector manifest is not a
license. Legal model-training/redistribution entitlements remain unestablished.

This workload fits a small fraction of the observed Studio memory, but no mini
was benchmarked here. No claim about text extraction, stock panels, graphs,
training, full-fleet capacity or hardware purchase follows from this result.
No model call or provider spend occurred. Production records admitted=0.

## Remaining exact frontier

F0 is PARTIAL. The CPI source component is verified for these internal structural
checks only. The 50-issuer/five-year pilot still lacks an admitted historical
universe/membership manifest, event-source revisions and clocks, permitted-use
receipts and an explicit missingness denominator. No stock cohort was selected.
This CPI unit is not a substitute for those dependencies or an equity forecast.

Next: recover a metadata-only issuer/universe/event manifest through the existing
identity and earnings owners; bind its source/rights/cutoffs before any bodies or
outcomes. Then select the first existing-consumer historical-context adapter.
Do not rerun this source audit unless its source, code or proof is invalidated.
The inspected CPI artifact is development-visible, not an untouched holdout.

Release: at ca04e2876ff52a2490e7b3383a825a793678917d, #967 still reported test FAILURE,
security checks SUCCESS and zero reviews. Prior exact-date/source-custody denied
actions remain held; no denied action was repeated, no test gate bypassed, and
no merge is claimed. A new source head requires its own CI and independent review.
