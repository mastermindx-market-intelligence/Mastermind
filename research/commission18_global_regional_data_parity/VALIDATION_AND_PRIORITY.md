# H-K — Validation, Risks, Priority and Phased Recommendation

## H. Empirical validation program

No regional data family should gain decision authority because it sounds institutionally sophisticated.

### Experimental unit and horizons

Use security × decision-time observations, with the decision date/session as the principal independent unit. Do not pretend many names observed on one day are independent macro environments.

Evaluate at least:
- 5 sessions: tactical/event reaction;
- 20 sessions: roughly one month;
- 60 sessions: medium-horizon continuation;
- 120 sessions where enough non-overlapping history exists;
- event-relative windows around earnings, filings and material disclosures.

### Baselines

Every proposed family needs nested comparisons:

~~~text
current regional pipeline
vs.
current + candidate family
vs.
current + candidate family residualized
against already-live correlated evidence
~~~

For estimates:

~~~text
price + momentum + sector + fundamentals
vs.
baseline + current consensus level
vs.
baseline + revision breadth/magnitude
vs.
baseline + revision acceleration/dispersion
~~~

This tests independent information rather than repackaged price momentum or earnings surprise.

### Controls and metrics

Minimum controls: trailing momentum, size, liquidity, beta, realized volatility, industry/sector, valuation, market regime and local calendar. HK should control global-risk beta. China should control suspension/limit-lock and other local microstructure states.

Predictive metrics:
- rank IC and residual rank IC;
- monotonic bucket behavior;
- directional Brier/calibration;
- event-surprise discrimination;
- forward maximum adverse excursion;
- stability across eras.

Economic translation:
- gross and cost-adjusted long-short/top-bottom spreads;
- turnover;
- capacity;
- drawdown.

Prophet-specific:
- candidate recall;
- precision of promoted/featured candidates;
- rate enriched evidence changes enter/wait/hold geometry;
- outcomes conditional on those changes;
- reduction in price_only decisions;
- whether confidence caps improve calibration rather than merely reducing participation.

### Coverage calibration

Coverage itself must be tested. If fully_evidenced, reduced_evidence and price_only states do not show meaningful calibration differences for strategies that supposedly depend on omitted families, the proposed confidence penalty should be killed.

### Independence and leakage

A revisions signal that disappears after earnings surprise and momentum controls is not an independent confirmation. A CCASS feature that merely identifies mega-cap liquidity is not institutional-flow alpha. A news feature adding nothing after known filings is narrative duplication.

Historical admissibility rules:
- observation.available_at <= decision_time;
- identity and theme membership must be effective at decision_time;
- select the latest correction generation that was itself available by decision_time;
- use embargoed walk-forward folds for overlapping horizons;
- use HAC/Newey-West or block/date-aware inference where labels overlap or names cluster by date.

### Vendor bake-off

A global-estimates trial should include US, HK and mainland-linked names, cross-listed cases, suspended/delisted names, non-USD reporting, local holidays and periods with multiple visible consensus changes.

A vendor must prove that Mastermind can retrieve or reconstruct the exact vintage available at historical decision time. A feed that provides only today's cleaned historical consensus fails the PIT gate.

## I. Risks and failure modes

1. **False parity:** unified schemas can make jurisdictions appear informationally identical when they are not.
2. **Hidden coverage alpha:** commercial coverage is often best for large/liquid names; “has revisions” can proxy for size/liquidity.
3. **Correction leakage:** current cleaned histories may contain values corrected years later.
4. **Correlated evidence:** news, revisions, options, targets and price may all respond to one event.
5. **Vendor lock-in:** unstable IDs or unavailable vintages make research irreproducible after cancellation.
6. **Rights drift:** a public webpage is not automatically a production dataset.
7. **Semantic overreach:** CCASS ≠ 13F; Connect ≠ beneficial ownership; margin financing ≠ US short interest.
8. **Stale observability:** a months-old census cannot be current truth.
9. **Overbuilding collectors before consumption:** more sources can worsen complexity without improving decisions.
10. **Parallel-control-plane creep:** regional coverage must feed V3's eventual owner, not create a second Decision Snapshot system.

### Kill criteria

Do not build or promote a family when:
- historical available_at cannot be reconstructed for the intended backtest;
- the vendor supplies retrospectively cleaned history without vintages;
- rights prohibit required storage/model use/derived output;
- identifier resolution is unreliable;
- incremental value vanishes after size/liquidity/momentum/sector controls;
- performance depends on one era/theme/sector without a predeclared explanation;
- cost/latency eliminates economic value;
- the family duplicates live evidence;
- local evidence cannot validly answer the intended question;
- the source requires prohibited scraping/login-cookie practices;
- correction behavior is opaque.

## J. Build priority

### P0

- Canonical coverage/clock/rights/equivalence contracts.
- Automated current census and regional coverage report.
- Global historical PIT analyst-estimates/revisions bake-off.
- Append-only prospective PIT capture for existing HK/CN fundamentals and HK consensus.
- Authoritative HK/CN filing/disclosure adapters in shadow mode.
- Shadow DecisionCoverageReceipt wired into existing data-quality/read surfaces.

### P1

- HK Part XV / CCASS / SFC-short family with strict semantic separation.
- Mainland director/major-holder/shareholder/interaction evidence where official rights permit.
- Consume existing CN/HK native news and policy artifacts in Mastermind research paths.
- Region-appropriate derivatives adapters.
- Prospective effective-dated theme membership.

### P2

- Issuer credit / financing-condition enrichment.
- Supplier/customer/network and procurement deepening.
- Exchange full-book/tick acquisition only after a narrower feature family proves expected incremental value.
- Additional alternative datasets only after current evidence consumption is measurable.

### Defer

- Broad geographic expansion beyond currently evidenced regions.
- Large paid full-book programs before PIT/expectation gaps are resolved.

### Reject

- One opaque global regional-confidence score.
- Zero-imputation for missing evidence.
- Back-projecting today's themes or consensus.
- Treating CCASS/Connect/margin data as 13F equivalents.
- A new independent outcome/Decision Snapshot/control plane.
- Production use of a source with unknown rights.

The P0 ranking is deliberately biased toward Prophet and portfolio quality: expectations/revisions improve the model of **what the market expects**; PIT filings/fundamentals improve the model of **what is actually happening**; coverage receipts state how much of each question Mastermind actually knows.

## K. Proposed implementation phases

1. **Coverage foundation.** Establish canonical contracts, equivalence registry, automated regional census and daily coverage matrices. Instrument existing US/HK/CN sources without changing portfolio behavior.

2. **Prospective Asia PIT capture.** Convert current HK/CN fundamentals and HK consensus refreshes into append-only observation generations. Preserve current consumer-compatible materialized views.

3. **Expectations parity experiment.** Conduct a provider-neutral I/B/E/S, FactSet and Visible Alpha bake-off or equivalent current finalists. No procurement without separate authority.

4. **Authoritative disclosure parity.** Add HK and mainland official filing/disclosure adapters with original/amendment relation and exact public availability times.

5. **Region-native positioning.** Add HK Part XV/CCASS/SFC-short observations and mainland ownership/financing equivalents only after equivalence rules prevent false cross-market aliases.

6. **Shadow decision integration.** Attach DecisionCoverageReceipt to the existing research/prediction/outcome loop. When V3's canonical Decision Snapshot owner exists, feed that owner rather than creating a substitute. No sizing/eligibility changes.

7. **Empirical promotion.** Run preregistered walk-forward and family-ablation tests. Promote each evidence family independently. A family that improves drawdown prediction but not return ranking earns only risk authority. A family with no independent information remains context-only.

### Open limitations

The repository census was sufficient to identify active US/HK/China structures and adjacent Canada work, but the static Mastermind census is stale and cannot prove runtime health of every source.

Exact 2026 commercial vendor prices were not established. Exact retention, derived-data, model-training, correction and historical-vintage rights require contract review.

No region should be called “parity complete” until Mastermind can reproduce, for a historical decision timestamp, both **the evidence it possessed and the evidence it knew it did not possess**.

The exact bounded follow-on implementation commission is in [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md). Do not execute it merely because this research exists.
