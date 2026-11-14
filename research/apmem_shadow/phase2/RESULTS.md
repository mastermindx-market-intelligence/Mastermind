# Volatility forecaster phase 2: results and decision

Research date: 2026-11-13 America/New_York; later execution receipts are 2026-11-14 UTC. Operation: volatility-forecast-phase2-20261113. Numerical evidence checkpoint: `935aa6f97d9dc19a940b9eef7515aada5b7e3bdf`. This is original research, not the external creator's private generator, production trading integration, or a certified live-performance comparison.

## Decision

Retain three separable capabilities for further qualification: (1) stronger common-target volatility forecasting; (2) empirically calibrated tail-risk context; and (3) strategy-specific, continuous risk overlays. Do not collapse raw return, risk-adjusted return and loss prevention into a single win/loss judgment. Do not promote a universal volatility-only trading system or a vote-count confluence score.

The deterministic APMEM forecast and the simpler delta=1 multiplicative-error model are useful research candidates. A fixed combination with IV-informed HAR adds complementary historical information on QQQ, SPY and IWM. Results remain retrospective, later extensions exploratory, and input-vintage/forward evidence incomplete. No ranking, sizing, trading, live-alert, collector or scheduler authority is enabled.

## Evidence scope

Eleven primary ETFs: QQQ, SPY, IWM, XLB, XLE, XLI, XLK, XLP, XLU, XLV and XLY. Each has 4,242 price observations from January 2010 through 2026-11-12. The main comparison begins January 2015. XLF is excluded because its 2016 in-kind XLRE distribution requires a separately qualified economic-return adapter, not because of performance. Five ordinary-split sectors passed issuer-event, independent raw-price and distribution-unit checks without double-adjusting prices.

The primary experiment has 13,164 selected fits and 4,224 portfolio scenarios. Later disclosed extensions include options ablations, calibration-only controls, pre-2010 SPY stress, numerical diagnosis and repair. The repair has 720 new fixed-power fits, 2,520 forecast-score rows, 7,020 utility scenarios and 432 numerical reference checks. These are not independent samples. All original and unfavorable results remain in evidence/.

95 dedicated tests passed in the principal container and actual empirical runtime. They verify future-data exclusion, matured labels, options timing, corporate actions, self-financing accounting, exact moment cases, analytical bounds, input digests and consumer clocks. Tests are not investment-performance validation. Empirical runtime: NumPy 2.4.6, pandas 3.0.3, SciPy 1.18.0, PyArrow 24.0.0; principal tests use a different recorded environment, with no bit-identical optimization claim.

## Identical independent targets

All models predict the same 1/5/20-session future mean daily variance proxy: distribution-aware overnight log-return squared plus intraday Parkinson range variance. The same forecasts are separately scored against future mean squared total close returns. These are noisy daily proxies, not observed high-frequency integrated variance. QLIKE and MSE are both reported; improvement on one is not automatically improvement on the other.

Direct-horizon training labels must have matured by fit time. The optional reconstructed options history ends 2026-11-05 and lacks verified original availability clocks. One-session lag and extra-lag tests are assumptions/sensitivities, not point-in-time certification. GEX uses assumed dealer signs, not observed dealer inventory.

### Main five-session QLIKE, lower is better

2,979 matched target observations per asset. This table is not the shorter options subset below.

| Asset | Existing estimator | EWMA94 | Deterministic APMEM | Reduction vs EWMA94 |
|---|---:|---:|---:|---:|
| QQQ | 0.610795 | 0.366398 | 0.283433 | 22.64% |
| SPY | 0.625321 | 0.384007 | 0.286778 | 25.32% |
| IWM | 0.483726 | 0.249598 | 0.196220 | 21.39% |

These are relative reductions in a historical forecast loss, not win rates, direction accuracy or trading returns. The corresponding reduction versus the incumbent is about 54%-59%. Chronological fitting does not make the already-inspected strategy-design history an untouched holdout.

The primary paired inference retains the original 2,000-resample results and a disclosed 20,000-resample resolution improvement with 63-session blocks and Holm adjustment across the complete 264-comparison family. Some comparisons do not survive multiplicity adjustment. Correlated assets, overlapping labels, nonstationarity and current-vintage inputs limit interpretation. A trailing matured-error scalar control is retained to distinguish dynamic skill from removable level bias.

## Confluence attribution

IV alone supplies most of the improvement over price-history HAR. GEX alone adds little in some comparisons and worsens others; adding it to IV is not uniformly helpful. An extra input lag degrades results, reinforcing the timeliness requirement rather than proving availability. IV is not treated as a physical probability; its relationship to the physical proxy is estimated by the forecasting model.

The final numerical-repair comparison has 1,959 common rows for QQQ/IWM and 1,960 for SPY. Fixed combination weights were not optimized to maximize returns.

| Asset | APMEM | IV-informed HAR | Half APMEM / half IV-HAR | Half exact MEM / half IV-HAR |
|---|---:|---:|---:|---:|
| QQQ | 0.204573 | 0.197667 | 0.188327 | 0.189240 |
| SPY | 0.266500 | 0.266418 | 0.251017 | 0.251608 |
| IWM | 0.202931 | 0.200877 | 0.191086 | 0.191353 |

The fixed APMEM/IV blend lowers five-session QLIKE by about 5.8%-7.9% versus APMEM and 4.7%-5.8% versus IV-informed HAR in these matched subsets. The simpler exact-model blend is competitive. This is explicitly exploratory after the original joint-options result, not prospective evidence.

Adverse counterevidence: improved QLIKE can accompany worse variance MSE, notably on QQQ/SPY, so the blend is not uniformly best at extreme spikes. Also, QQQ's lowest-disagreement group among EWMA/APMEM/HAR had QLIKE 0.32024 versus 0.26464 for its highest-disagreement group. Agreement is not calibrated confidence; no agreement-count market gate was promoted.

## Numerical robustness repair

The initial 256-path multi-step APMEM experiment showed seed sensitivity at predetermined annual-spaced origins. One H20 estimate differed by about 205% from a larger-path reference. H1 remained exact. This is a defect discovered in OUR initial experimental implementation, not an allegation about the creator's private code. Original outcomes are preserved.

Define X=mu^delta, p=1/delta and A=alpha*[epsilon*(1-gamma*sign)]^delta+beta. Under the stated independent empirical transition assumption, X_next=omega+A*X. First and second powered-state moments have exact deterministic recursions:

```
m1_next = omega + E[A]*m1
m2_next = omega^2 + 2*omega*E[A]*m1 + E[A^2]*m2
```

For fractional p, E[X^p] uses a separately identified lognormal two-moment approximation with analytical Jensen/moment bounds. At p=1 or p=2 the relevant moment is exact. A separate delta=1 control has exact finite-horizon empirical conditional means without simulation or fractional-moment closure. Parameter fitting remains statistical and market accuracy is not guaranteed.

The deterministic method removes seed noise. Against a 65,536-path diagnostic reference, median absolute approximation differences are about 0.10% for H5 and 0.18% for H20; 95th percentiles about 0.80% and 2.09%. One difficult monthly case is still about 23% different, with wide approximation bounds. The Monte Carlo reference is not exact truth.

The analytical bounds concern conditional expected forecasts under the empirical recursion; THEY ARE NOT FUTURE MARKET-OUTCOME INTERVALS. Some fitted coefficient diagnostics also fail a long-run-mean condition. Finite-horizon numerical stability, approximation width, stationarity diagnostics and real-market calibration are separately reported.

## Economic outcomes: protection is not free alpha

Execution is next-open, unlevered, long/cash, with distributions and actual drifted-weight rebalancing costs plus terminal liquidation. Sensitivities retain an extra open delay, 5/20 bp one-way costs and zero/constant 3% cash rates. Constant cash rates are assumptions, not historical Treasury returns. Maximum drawdown is open-mark only; intraday losses may be worse. A 15% volatility target is NOT a loss cap.

Primary table: 2015-01-02 through 2026-11-12, five basis points per side, zero cash return. The exact model is the separately fitted delta=1 MEM.

| Asset / policy | CAGR | Sharpe | Maximum drawdown | Mean worst-5% daily return |
|---|---:|---:|---:|---:|
| QQQ fully invested | 18.02% | 0.874 | -36.69% | -3.34% |
| QQQ exact model, 15% target | 12.90% | 0.903 | -28.61% | -2.20% |
| SPY fully invested | 13.37% | 0.830 | -32.05% | -2.64% |
| SPY exact model, 15% target | 10.57% | 0.877 | -22.45% | -1.92% |
| IWM fully invested | 8.81% | 0.492 | -41.47% | -3.26% |
| IWM exact model, 15% target | 4.88% | 0.399 | -28.11% | -2.08% |

Across all eleven ETFs, the repaired equal blend and exact model both reduce drawdown and worst-5% average daily loss. Sharpe improves in four assets for the blend and seven for the exact model; neither improves CAGR in this primary fully-invested comparison. These descriptive counts are not independent statistical trials. IWM is an important negative risk-adjusted result.

### Exposure-matched diagnostic

QQQ, 2021-01-04 to 2026-11-10, same conventions:

| Policy | CAGR | Sharpe | Drawdown | Mean worst-5% day |
|---|---:|---:|---:|---:|
| Fully invested | 14.47% | 0.717 | -36.69% | -3.30% |
| Exact MEM + IV, 15% target | 10.01% | 0.722 | -27.47% | -2.19% |
| Same average exposure, static diagnostic | 11.62% | 0.733 | -28.83% | -2.51% |

Both reduced-risk versions have 75.70% average equity exposure. Dynamic timing modestly improves drawdown and tail losses but sacrifices about 1.61 CAGR points versus the static diagnostic. The hindsight exposure match is NOT a deployable learned rule; the separate training-era static comparator also remains in evidence.

### Earlier-regime stress

Fixed 1998-2009 SPY: full investment CAGR 2.91%, drawdown -55.44%, Sharpe 0.241. Repaired equal blend at 15% target: CAGR 1.53%, drawdown -43.41%, Sharpe 0.180. Loss mitigation persists, but there is no universal Sharpe gain, even in a severe bear-market era. No parameter was retuned to this earlier period.

## Tail calibration and execution clocks

A close-t forecast applied to an open t+1 to open t+2 holding interval admits calibration residuals only after the endpoint is observed. Its tail test is separate from close-to-close calibration.

For the exact MEM/IV candidate, nominal 1% lower-tail breaches were QQQ 12/1,462 (0.82%), SPY 16/1,463 (1.09%), IWM 18/1,463 (1.23%). Gaussian versions had respectively 29/1,462 (1.98%), 29/1,463 (1.98%), 22/1,463 (1.50%). Small event counts, retrospective calibration and nonstationarity preclude a future coverage guarantee. SPY still has violation clustering (asymptotic diagnostic p about 0.0106). Coverage frequency alone is not crisis safety; pinball loss, interval sharpness and dependence also matter.

## External-creator comparison limit

The public retrospective forecast snapshot was checked under both plausible date alignments and an assumed annualization convention. The original direct-target H1 result looked better under those assumptions, but target identity, actual timestamps, fit vintages and original publication history remain unknown. This is not a certified live head-to-head victory. His strategy outputs, our forecasts and our portfolio overlays remain distinct objects.

## Consumer and forward record

The pure research consumer now distinguishes parameter fit cutoff from latest filtered state; it no longer incorrectly requires every parameter fit to end on the latest observation. Input capture, forecast computation, training cutoff and state origin are checked independently. A real reconstructed QQQ context passes as RESEARCH_ONLY with all ranking/sizing/trading flags false. Supplied clocks still need external provenance.

A fresh frozen forward attempt after the November 13 session FAILED CLOSED: Yahoo's long-window OHLC response had NaN latest closes for QQQ/SPY/IWM; a bounded five-day query confirmed those NaNs; independent approved Massive snapshots still ended November 12. No missing close was filled, no after-hours quote substituted, and no stale origin passed off as fresh. The child process exit 1 is recorded separately from its controller's normal exit.

The initial `ABSTAIN_INPUT_UNAVAILABLE` attempt remains immutable with zero predictions. A separate bounded recovery through the existing approved Tiingo EOD reader then supplied complete single-provider raw OHLC/divCash panels through November 13. The new adapter verifies exact request, digest, instruments, dates, split encoding and finite prices; it does not splice providers, impute closes, use adjusted predictors or expose credentials. Ninety-five tests passed in both numerical and principal environments. Cross-source historical OHLC differences remain disclosed in FORWARD_RECOVERY.md and the source receipts; the original historical experiments were not reselected using Tiingo.

**Actual forward result: three instruments, five fixed models each, three horizons each = 45 frozen forecast values.** The complete record was published at GitHub commit `3de620818a38a599d6e6d0addf5050736920980f`, timestamp `2026-11-14T01:56:28Z`, exact-byte SHA256 `76a33f4f05d1cba899da059a91e7bd77637e83727385b6159b6ad1419c590776`, with readback verified. All predictions concern observations strictly after origin November 13, 2026; there are zero matured outcomes in this delivery. The original generated record's awaiting-publication status is reconciled by the separate publication receipt, not retrospectively rewritten. Raw inputs remain private, not bundled as public historical datasets.

| Instrument | Exact MEM H1 annualized volatility | H5 | H20 |
|---|---:|---:|---:|
| QQQ | 31.28% | 30.94% | 29.83% |
| SPY | 20.09% | 20.03% | 19.82% |
| IWM | 21.78% | 22.01% | 22.49% |

These are annualized volatility estimates, not predicted returns, loss limits or a selected winning model. The other four frozen model outputs remain in the same record. The options-enhanced extension was not fabricated from the stale reconstructed options archive; it remains explicitly unavailable for this observation. No recurring collector, grader, watcher or trading service was installed.

The next scientific gate is matching the frozen predictions to genuinely later outcomes under the predeclared target/clock, retaining failures and coverage. Publication proves pre-outcome existence, not future accuracy.

## Delivery and integration boundary

The architecture direction is opportunity/strategy evidence -> separate volatility/tail-risk context -> existing portfolio/risk owner. A volatility component can help control loss without predicting direction. Low forecast volatility does not make a weak opportunity attractive. Portfolio covariance, cross-strategy dependence, production consumer qualification and forward performance remain unproven here; no rival owner/store was created.

The normal Fabric route was unavailable. The principal performed implementation, numerical research, tests and self-review. No full subagent-team execution or independent source-code approval is claimed. Closed prior worker attempts were not replayed, and runtime/provider controls were not changed. Current source delivery, required CI, protected merge and any production acceptance are separate receipts.

Evidence: original primary tables, all disclosed extensions, hashes and run receipts under evidence/; extended file hashes in EXTENDED_MANIFEST.json. README.md gives reproducible offline commands using separately accessible licensed snapshots. Raw vendor histories are not published.

Primary references: NYU APMEM https://vlab.stern.nyu.edu/docs/volatility/APMEM ; Moreira/Muir https://www.nber.org/papers/w22208 ; Cederburg et al. https://www.sciencedirect.com/science/article/pii/S0304405X2030132X ; Patton https://www.sciencedirect.com/science/article/pii/S030440761000076X . These references motivate methods/limitations; they do not validate this specific implementation.


## Exact evidence locations after source-check repair

The compact summary was moved byte-identically to `research/evidence/apmem_shadow_phase2/DELIVERY_SUMMARY_COMPACT.json`, the repository's existing structurally checked record plane. Scientific counts were not disguised; real peer/owner identity negative controls still fail. The forward observation and publication/recovery records use that same plane. Other aggregate tables remain under this directory's `evidence/`. The protected guard implementation and permissions were not changed.
