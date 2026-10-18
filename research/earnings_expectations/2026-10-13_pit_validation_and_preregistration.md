# Earnings Expectations Research — Preregistered Point-in-Time Qualification and Evaluation Contract

**Date:** 2026-10-13. **Status:** research protocol candidate, no live source mutation, no predictive promotion.  
**Consumer:** existing earnings event workspace + C19 MAS-271 expectations qualification, MAS-118 market incorporation.  
**Read baseline:** Mastermind protected master at `54e8659730141fc130ebbeb214dbb50f3edb04a7`; Macro main at `0f8ecf0bd6bed323113283f9f5a454888865bf81` (observe/reconfirm writer before any implementation).  
**Non-goals:** no replacement SRC-A1/EXP-1, no new market-belief truth owner, no live data acquisition, no Prophet rank/gate/size influence, no revenue or EPS guess where baseline absent.

## A. Research question and estimands

**Primary (P):** Among eligible earnings events with genuine pre-event comparable forecast vintages, does adding *changes in pre-event expectations conditional on fundamental acceleration* improve the out-of-sample prediction of first-session **market-and-sector-adjusted returns** beyond a benchmark containing pre-event returns, forecast revision level, earnings surprise history and sector/era effects?

**Secondary (S1):** Does the same feature set improve prediction of standardized future fundamental surprise (EPS/revenue/guidance separately)?  
**Secondary (S2):** Can a distinct model predict post-first-session H5/H20 drift, after spread/slippage costs, beyond a momentum+factor+event-reaction benchmark?  
**Secondary (S3):** Do source-grounded customer/supplier/competitive read-through facts change the distribution of later peer surprises when measured before those peers report?

These are conditional prediction tests, **not identification of causal recency bias**. A significant interaction is not proof of the investors' mental state.

## B. Sampling and frozen cohort rules

1. **Discovery cohort:** The nine 2026 Alphabet/Amazon/Microsoft events in the companion casebook are explanatory examples only, excluded from confirmation-stage significance testing because their outcomes motivated this study.
2. **Main universe:** US common equity issuers with valid immutable economic issuer IDs, an actual first public earnings timestamp, split-adjusted regular-session bars, and enough contemporaneous source/forecast observations to qualify a fixed fiscal target. Historical membership must use PIT issuer security records, **not today's index constituents**.
3. **Observation unit:** one *issuer × fiscal quarter × first material earnings publication event*. GOOG and GOOGL collapse to the same economic issuer event; a corrected filing is a revision, not a second independent announcement.
4. **Exclusions specified before outcomes:** SPAC/de-SPAC until normal audited reporting, funds, duplicate share classes, unsupported currency/basis, source rights prohibiting modeling, primary release clock unknown for narrow-window price labels, or price corporate action unresolved. Emit exclusion reason; do not silently drop a losing event.
5. **Cohort coverage:** show eligible/all by fiscal year, sector, cap, release timing and baseline source; report whether source availability selects for large popular technology companies.
6. **Event grouping:** issuer-quarter unit for fundamentals; *calendar event-day clusters* for shared macro shock; issuer/industry blocking for cross-period validation. Event waves close in time are not independent price experiments.

## C. Historical knowability and fiscal identity

For every snapshot require `issuer_id, security_id, fiscal_period_end, fiscal_year/quarter_if_native, fiscal_target_identity, metric, unit, currency, basis, source, contributor_class, timestamp_public, timestamp_observed, rights, correction_version`. A vendor label `+1q` is not identity. Both source-public and platform-observed timestamps must be at or before the decision cutoff. Date-only analyst vintages cannot prove intraday ordering around an announcement.

Reject or mark `UNESTIMABLE` on these exact adversarial cases: (1) +1q changes quarter-end; (2) GAAP EPS vs non-GAAP; (3) basic vs diluted; (4) EPS unit or currency mismatch; (5) prior guidance midpoint vs analyst consensus; (6) post-event correction revised historical value; (7) source rights unavailable; (8) missing prior vintage; (9) contributor total masquerading as revision breadth; (10) timestamp only has calendar-day granularity overlapping release; (11) withdrawal/staleness; (12) analyst EPS includes non-operating investment gains on a different accounting basis.

The *same* fiscal target must be compared across vintages. For positive EPS level use signed absolute `delta_estimate = new - old` and, only with sufficiently nonzero positive denominator, a percent change. Near-zero/negative EPS should use absolute dollars/share and appropriate standardized units; never divide by tiny or negative values and call it growth.

## D. Public release clock and label contracts

Identify earliest timestamped company IR release, 8-K acceptance, and exchange-published earnings disclosure; use the **earliest actually public** release for decision-relative classification. Build labels:

- `P20`, `P10`, `P5`, `P1`: pre-release abnormal returns, cutoff at last regular-session close prior to public release; windows in **trading sessions**.
- `R1`: split-/dividend-consistent, issuer return from last unaffected regular close to first affected **regular-session close**, minus beta-adjusted market + industry/sector contribution measured on aligned sessions.
- `D5`, `D20`: return from the first genuinely tradable *post-announcement* regular-session entry (use conservative assumed opening fill) to 5/20 sessions later; include exposure to release gaps separately. Never claim that prior-close trade was available after seeing the report.
- `F`: actual financial metric versus eligible **pre-release** consensus, same basis and fiscal quarter. Historical SUE using trailing seasonal EPS differences is a distinct feature, not a valid analyst beat/miss comparator.
- `OVERNIGHT`: after close and pre-open handling distinct from intraday or weekend releases. Do not mislabel extended-session quote as next-day close.

Use a clearly versioned benchmark (SPY, sector ETF or factor model) whose parameters are fit using data strictly before the event. Report benchmark sensitivity.

## E. Feature families and benchmarks

**Baseline B0:** sector × era × quarter-frequency return base rates and macro/volatility indicators.  
**B1:** prior 20-session relative return, 60-session realized vol, ticker/sector beta, valuation context known then.  
**B2:** B1 + last strictly PIT seasonal earnings momentum + available benchmark analyst revision change; no speculative narrative or options data.  
**Candidate C1:** B2 + expectation-ratchet features: fixed-horizon forecast delta and acceleration; pre-event price/estimate divergence; estimate dispersion; last report beat magnitude; interactions with measured fundamental acceleration.  
**Candidate C2:** C1 + quantitatively confirmed company guidance deltas on matching fiscal target.  
**Candidate C3:** C2 + source-cited financial claim-novelty features, independently available by cutoff; text embeddings must never include post-event call for a pre-event forecast.  
**Candidate C4:** C3 + options-implied move/skew when rights and timestamps are sufficient; missing surface explicit, never invented.

Require B0/B1/B2 comparisons on the **same eligible intersection** to avoid interpreting better-data subset selection as model improvement. Also report the broader-coverage B0/B1 universe separately.

**Primary null:** C1 does not improve chronological out-of-sample risk-adjusted predictive loss for R1 over B2. Primary metric: cross-validated/held-out mean squared error on market-adjusted return normalized by training-era volatility, with historical sample support; secondary proper calibration and directional log-loss under fixed bins. No changing primary metric after seeing results.

## F. Validation and stop rules

**Split plan:** development years through 2021, calibration 2022–2023, first frozen untouched holdout 2024–2025; 2026 nine-event discovery examples remain explanatory, with new events prospectively assessed only after model freeze. Treat model selection on 2024–25 as leakage; retrain once using selected specification only after holdout verdict recorded. Strictly embargo adjacent events as appropriate and group issuer/industry event sequences.

**Controls:** matched non-event sessions; matched normal earning events with similar size/sector/liquidity; event-date clustered block/bootstrap CIs; multiple-testing adjustment over all tested C1–C4/model/horizon searches, not just surviving ones; stock split/currency and affected event price-bar audit.

**Negative/hold cases:** if source rights or PIT comparison fails, no expected surprise target and no distribution forecast; continue deterministic event explanation. If C1 fails the holdout, do not promote event-prediction ranker. If C1 improves in-sample but not out-of-sample, classify discovery only. If post-announcement drift disappears net of costs, retain descriptive research and abandon trading edge claim. If company-specific residual vanishes after market/sector shocks, do not call the event 'sell-the-news' evidence.

**Success gate:** improvement over same-cohort B2 survives the untouched holdout, explicit economic uncertainty, reasonable calibration, material coverage and cost-aware usefulness; then enter a separately pre-registered **prospective shadow** period. Retrospective success alone never grants Prophet or trade authority.

## G. Concrete 12-fixture implementation acceptance pack

For the incumbent expectations/financial contract owner (not a new writer), supply cases and tests:
1. Same fiscal target, metric/basis/rights, two historic vintages → comparable delta.
2. Prior missing → typed unavailable, not zero.
3. Horizon rollover +1q to later fiscal end → no revision.
4. Same company multiple listing classes → one economic event.
5. Late discovered revision after event cutoff → invisible at T.
6. After-cutoff correction to earlier record → retain original as-known-at.
7. Stale/withdrawn forecast → explicit status.
8. GAAP vs adjusted EPS → refuse comparison.
9. Currency or unit mismatch → refuse comparison.
10. Guidance midpoint vs sell-side mean → separate channels.
11. Analyst count revision numerator vs covering population → don't infer breadth.
12. Misaligned after-hours release and 8-K acceptance → event price anchor earliest public time.

**Exit evidence:** owner-issued normalized-baseline comparability result *or* unestimable witness; caller-visible linked receipts in an existing consumer; exact source revision and recorded validation. No synthetic consensus value.

## H. Implementation sequencing and custody

- P0: reconcile accepted #1407 research packet with current C19 MAS-271 and Macro expectation owner; fresh source head at research date has advanced, so validate material code changes before implementation.
- P1: consume existing EXP-1/C19 WP09 to qualify one issuer, one target, two prior vintages. If no data, use the 12 tests on **lawfully invented synthetic fixtures** to prove refusals, but do not claim real comparability.
- P2: join earnings event, financial actual and named prior guidance plus owner-qualified consensus, each with clocks and source refs; research display only.
- P3: establish exact release clocks and exchange price/factor return labels. Quantitative event analysis remains unverified until this.
- P4: preregister and measure C1 vs B2 with adequate representative PIT data. Do not fabricate source rights or statistical power.
- P5: promote to shadow only when P4 pass; otherwise stop at an intelligible evidence-based product.

**No local/production files were changed or test suite run by this research document.** It is a falsifiable specification meant for consumption by existing owners. Existing implementation effects remain untouched.

## I. Explicit next action

Ask the current C19 MAS-271 owner to produce, through its already-authorized carrier, a real `issuer×period×metric` two-vintage comparability receipt or a precisely typed noncomparability reason, and have a single approved Terminal/integrated-answer consumer display its source evidence. **This is an owner action dependency, not new routing or a fresh job authorization.** In parallel, the research branch can continue public-event exact timestamp/price label reconstruction without modifying the incumbent source.
