# SignalsEngine → Mastermind
# Public-system census, comparative assessment, and integration masterplan

**Research date:** 22 October 2026, UTC  
**Purpose:** Turn the useful ideas exposed by SignalsEngine into an original, better-integrated Mastermind product.  
**Status:** Completed research assessment and proposed implementation program. Public/backend limits and production-verification questions are stated explicitly.

## Executive assessment

The strongest opportunity is to make Mastermind's intelligence easier to use as one continuous workflow: understand the market, identify a conditional setup, inspect its evidence, track what changes, evaluate the issued claim, and learn from the result.

SignalsEngine offers a useful product reference for that workflow. Public evidence does **not** establish that it has a uniquely predictive engine, a verified trading edge, or a fully operational version of every screen shipped in its client. Our research found a mixture of substantive consumer interfaces, educational descriptions, alternate implementations, and prototypes.

Mastermind already has substantial prediction, outcome, calibration, and memory implementations. The separately verified Prophet path also supplies shared plans, targets, invalidation, stable identity, source snapshots, corrections, management, and a forward ledger consumed by Dashboard and Terminal. The highest-value program starts by tracing that existing user journey, repairing demonstrated inconsistencies, and adding only the missing references or calculations.

The most concrete follow-up findings are a possible same-build closed-state publication lag, a confidence-field handoff discrepancy to verify, different entry-zone and ledger-trigger semantics to reconcile, and a documented cross-batch sweep-grouping limitation. These are source-level findings; the first three require focused reproduction or owner adjudication. The confluence discovery process also consumes its test half for selection, so final predictive claims need an independent outer evaluation. Sections 8–9 provide the pinned evidence and Section 14 assigns the work.

The proposed competitive advantage is a combination of:

- Broad native macro, cross-asset, breadth, sector, earnings, and memory context.
- Interpretable price, volume, profile, options, and qualified flow evidence.
- Explicit disagreement, missingness, latency, and data provenance.
- Conditional setups with clear trigger, horizon, invalidation, and outcome rules.
- One traceable connection from original evidence to the eventual recap.
- Prospective evaluation that measures incremental usefulness over the incumbent system.

This is a research and design deliverable. It does not claim that any proposed engine has been implemented, validated, or deployed.

## 1. Scope, method, and evidence strength

### 1.1 What was inspected

The research covered the public website, all 26 linked Signalpedia articles, public legal and commercial pages, the normally served application bundle, and selected consumer modules discovered from that bundle. The main application asset references 144 distinct page/component paths, including education, authentication, administrative pages, archived versions, and alternative dashboards. That count is a coverage clue, not 144 functioning features. [Application bundle](https://signalsengine.com/build/assets/app-CDapMUlI.js)

The investigation also searched public GitHub repositories and code for the exact domain and product name; checked market-data assumptions against FINRA, SEC, Cboe, Massive, and primary statistical sources; and commissioned separate source censuses of the Mastermind, Macro, and Terminal repositories.

| Evidence class | What it establishes | What it does not establish |
|---|---|---|
| Public page rendered content | What the company currently exposes or claims publicly | Actual predictive performance or implementation completeness |
| Public educational article | Definitions and a described methodology | That the same formula is executed in production |
| Public compiled consumer module | UI logic, expected fields, referenced routes, client calculations, prototype behavior | Backend availability, access permissions, database schema, or deployment history |
| Public architecture diagram shipped in client | The architecture the vendor describes | Infrastructure actually running |
| Pinned internal source | Implementation and static wiring at a reproducible revision | Deployment, data freshness, runtime correctness, or a completed customer journey |
| Test-file inventory | Named test files exist; clues about intended coverage | Their assertions, execution, adequacy, or production behavior |
| Inspected test implementation | Particular assertions and fixtures exist | Successful execution or production correctness |
| Open PR | Work underway and possible ownership collisions | Merged behavior or operational capability |

No authenticated SignalsEngine session, private source, model artifact, database, production prediction ledger, or customer account was inspected. Normal unauthenticated dashboard access led to login. Publicly referenced screenshot assets were unavailable through the permitted retrieval path; no claims here depend on visually inspecting them. Referenced API routes were inventoried as client expectations; their responses and backend authorization were not tested.

### 1.2 Reproducible internal source pins

| Repository | Inspected revision |
|---|---|
| Mastermind | 05a9eb52a54e29fb7bbd0d40813ed12623b176c7 |
| Macro | 01c966b177ce9425030eac8a337352ee2842daed |
| mastermind-terminal | 942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e |

These are independently pinned repositories. A comment in Mastermind's .gitmodules does not prove the effective Macro version used by a live service. A symbolic link is not a Git submodule commit. Deployment parity remains a separate verification task.

Capability labels in this report mean:

- **BUILT_NOT_PROVEN:** implementation observed; live product behavior not established in this research.
- **PARTIAL:** a specific missing connection, input, or consumer remains.
- **SPEC_ONLY:** a proposal without corresponding implementation evidence.
- **NOT OBSERVED:** absent from the stated search scope; not an assertion of universal absence.
- **PROVEN_LIVE:** reserved for actual runtime and user-path evidence. Source presence alone does not earn it.

## 2. What SignalsEngine is building

SignalsEngine presents itself as an invite-only educational market-intelligence product. Its main concept joins volume-price analysis, order flow, options, and machine learning, then presents a directional setup with levels and a confidence-style score. The homepage advertises 300+ data points per symbol, a 73.2% win rate, and 1,247+ signals; the research did not find the underlying complete evaluation ledger needed to verify those performance figures. [Homepage](https://signalsengine.com/)

The public navigation describes Dashboard, Signals, Realtime, Symbol Breakdown, Briefs, Recaps, Ask AI, and Charting. [Navigation module](https://signalsengine.com/build/assets/app-sidebar-header-DW3fKPpH.js)

The product is aimed at a trader who wants fewer disconnected screens and more explanation: a morning view, a shortlist, a deeper symbol analysis, and a subsequent account of what happened. That is a product-design inference from the consumer interfaces, not evidence of commercial traction. Public examples include historical sample dates in December 2025 and January 2026; they were not treated as current market observations or evidence of present data freshness.

### Commercial and organizational footprint

The footer identifies SignalsEngine LLC, but no corporate registry verification was established. The site provides an invitation contact and support address and links a branded X account. Exact-domain and product-name searches did not establish attributable public funding, team size, customer count, or an official source repository.

Pricing presentation requires care: the page displays $170 per month alongside $2,040 annually and a $360 saving. That is consistent with an annual effective monthly price compared with a $200 monthly plan, but the billing transaction was not inspected. The affiliate page advertises 15% recurring commissions and a $30 monthly referral example, which is also consistent with $200 monthly. Treat these as public marketing displays, not verified checkout terms. [Affiliates](https://signalsengine.com/affiliates)

Terms describe educational use and assert intellectual-property restrictions. This plan recreates general analytical ideas with original code, original explanations, and appropriately licensed data. It does not propose copying the vendor's code, content, or assets. [Terms](https://signalsengine.com/terms) · [Privacy](https://signalsengine.com/privacy)

### GitHub finding

No attributable official public repository was found in the inspected searches. A similarly named C++ repository and other token-matched code results did not establish a connection to the domain. “No attributable repository found” is the defensible conclusion; “they have no GitHub” or “their backend is open source” would not be.

Search coverage included the repository name, exact domain in repository metadata, exact-domain GitHub code search, the publicly named contact in combination with the product, and broader exact-domain web searches. Results from similarly named sales-intelligence, crypto, radio, and other products were excluded.

## 3. Publicly observable implementation and backend clues

### 3.1 Client technology

The served HTML and bundle are consistent with a React/Inertia application built with Vite. Laravel-style page state, CSRF conventions, and the Laravel Cloud asset host support a Laravel-stack inference. The client includes prediction-event broadcasting and Polygon/Massive WebSocket configuration. These observations establish a client integration pattern; they do not prove the deployed database, server topology, job reliability, or feed entitlement. [Application bundle](https://signalsengine.com/build/assets/app-CDapMUlI.js)

### 3.2 Vendor-described pipeline

A shipped pipeline diagram describes this sequence:

1. Collect historical OHLC, tick data, options information, sentiment measures, and Massive fundamentals after market close.
2. Compute VPA, lit flow, off-exchange flow, gamma, technical, sentiment, and structure components.
3. Generate tiered VPA/LSTM/blended forecasts over multiple horizons.
4. Persist snapshots, predictions, and order-flow records.
5. Optimize target, stop, and exit timing with local LSTM models.
6. Generate market and symbol briefs using language models; evaluate and recap afterward.

The same module contains MySQL Aurora and Lambda/SageMaker descriptions alongside local inline-model language. Their operational relationship is unresolved. Its named table families and field counts are architecture claims, not a database census. [Pipeline module](https://signalsengine.com/build/assets/PipelineFlow-Cq0sncBE.js)

### 3.3 Client-described API families

| Consumer | Referenced route family | Meaning and limit |
|---|---|---|
| Dashboard | /api/v2/dashboard/market-overview, active-signals, top-signals, indices, performance | A consumer contract for overview, ranking, and performance; no live response inspected |
| Symbol analysis | /api/v2/symbol/{symbol}/overview, predictions, options | Symbol-level data expected by the client |
| Signals explorer | /api/v2/dashboard/all-signals | Filtering, sorting, and pagination for issued signals |
| Older trading dashboard | /api/trading-dashboard/{symbol}/… | Active/evaluated signals, disagreements, system performance, export |
| Volumetric chart | /api/charts/volumetric-dates/{symbol} and volumetric/{symbol} | Date/interval-dependent chart data |
| Broadcasting | predictions / PredictionAlertEvent | Client-side event subscription, not delivery proof |

Sources: [Dashboard hook](https://signalsengine.com/build/assets/useV5Dashboard-31M1Co8B.js), [Symbol hook](https://signalsengine.com/build/assets/useV5SymbolData-U85cZhJw.js), [Signals explorer](https://signalsengine.com/build/assets/Index-uXeJQRFV.js), [Historical consumer](https://signalsengine.com/build/assets/Historical-cc8pl1Fn.js), [Charting](https://signalsengine.com/build/assets/Charting-x9cMuOBc.js).

### 3.4 Additional collection, quality, and evaluation clues

The public asset map includes administrative consumers for snapshot completeness, missing/orphaned pipeline tables, prediction analytics, scoring analysis, and system comparisons. These were inspected as normally served client files. No administrative API or data-collection action was called.

| Public client module | What it describes | What we can learn |
|---|---|---|
| Snapshot validation | Missing, invalid, and critical fields by date/symbol/table | Make completeness observable at the same grain as the decision |
| Lookback analysis | Pipeline references to order flow, profile, OHLC, expiry, technical, and prediction tables | Audit missing joins and orphaned outputs before trusting a combined signal |
| Prediction analytics | Price error, direction, target/stop outcomes by symbol, horizon, and confidence | Separate forecast tasks and expose cohort definitions |
| Scoring analysis | Component/system comparisons, MFE/MAE, expected value, profit factor, recommendations | Connect a score to complete issued cohorts; proposed thresholds still need independent validation |
| Signal-system analysis | VPA, LSTM, blended, and AI systems; delta/options alignment; expired win/loss/no-data states | Preserve model identity, missing outcomes, and disagreements |
| DXLink collection interface | Underlying quotes, option chains, Trade/Quote/Summary/Greeks/Profile event types, periodic capture, historical candles, and CSV import/export | An additional vendor-integration clue beyond the Massive connection; operational status and entitlement remain unknown |

Sources: [Snapshot validation](https://signalsengine.com/build/assets/SnapshotValidation-CIxM-hwF.js), [Lookback analysis](https://signalsengine.com/build/assets/LookbackAnalysis-_zVZ_n4j.js), [Prediction analytics](https://signalsengine.com/build/assets/Index-CtaDKMYh.js), [Scoring analysis](https://signalsengine.com/build/assets/Index-ClQ_pQJb.js), [System analysis](https://signalsengine.com/build/assets/Index-BhkqLrKt.js), [Collection interface](https://signalsengine.com/build/assets/CollectFinal-6bovGf7y.js).

The DXLink client is a concrete architectural clue, not proof of a production broker integration. dxFeed documents DXLink as a streaming market-data protocol; the exact account arrangement, rights, collection success, and usage by SignalsEngine were not established. [dxFeed DXLink documentation](https://kb.dxfeed.com/en/market-data-api/dxlink.html)

Different shipped consumers label the top tier at 80, 90, or 95 points. Together with the directional versus unsigned score descriptions, this indicates version or meaning differences that public material does not resolve. The useful idea is an inspectable score decomposition; copying a threshold would import ambiguity.

### 3.5 What remains unknowable from these sources

Private feature calculations, exact aggressor classification, venue mappings, trade correction handling, option-position assumptions, model training data, training windows, label definitions, validation splits, class balance, probability calibration, operational cadence, retention, backend authorization, and paid-user execution quality remain unverified. Client field names are useful for reconstructing an interface contract, but insufficient for reconstructing these mechanisms exactly.

## 4. Observed public feature census by family

The tables cover all 26 inspected educational articles and the substantive selected client modules. “Client” means the shipped consumer contains the relevant interface or field, not that its backend was tested. Value judgments concern usefulness when correctly implemented; they are not claims of predictive edge or the build sequence.

### 4.1 Market and technical context

| Capability | Public evidence | Value for Mastermind | Qualification |
|---|---|---|---|
| VIX context | Dedicated article | Useful volatility context | Measures expected volatility, not direction |
| Broad and symbol put/call ratios | Separate articles | Positioning context and anomaly baselines | Product, volume/OI, and horizon must be explicit |
| Candlestick anatomy and patterns | OHLC article | Explainable price-action vocabulary | Pattern occurrence does not establish alpha |
| Moving-average structure | MA article | Trend and distance features | Multiple averages are related evidence |
| RSI and CCI | Oscillator article | Momentum/mean-reversion context | Extremes can persist in trends |
| Bollinger width and position | Bollinger article | Compression/expansion conditions | A squeeze does not identify direction |
| Ichimoku | Dedicated article | Optional composite trend display | Displaced plot coordinates require careful replay semantics |
| ATR and volatility-normalized levels | ATR article | Comparable risk distances | Historical range is not a guaranteed future bound |

Sources: [VIX](https://signalsengine.com/signalpedia/market-sentiment/vix-volatility-index), [Market PCR](https://signalsengine.com/signalpedia/market-sentiment/put-call-ratios), [OHLC](https://signalsengine.com/signalpedia/technical-analysis/ohlc-candlesticks), [Moving averages](https://signalsengine.com/signalpedia/technical-analysis/moving-averages), [RSI/CCI](https://signalsengine.com/signalpedia/technical-analysis/rsi-cci-oscillators), [Bollinger](https://signalsengine.com/signalpedia/technical-analysis/bollinger-bands), [Ichimoku](https://signalsengine.com/signalpedia/technical-analysis/ichimoku-cloud), [ATR](https://signalsengine.com/signalpedia/technical-analysis/atr-volatility).

### 4.2 Volume-price analysis

| Family | Patterns and mechanism described | Original implementation opportunity |
|---|---|---|
| Accumulation | Selling climax, stopping behavior, tests, springs, strength after a range | Detect an observable sequence of price, range, volume, and confirmation events; do not assert trader identity |
| Distribution | Buying climax, upthrust, failed demand, weakness after a range | Express deterioration and failed-breakout conditions with structural invalidation |
| Continuation | Flags, pennants, rectangles, re-accumulation/re-distribution, low-volume pullbacks followed by expansion | Combine trend context with an explicit continuation trigger |
| Candle-feature scoring | Body, wick, spread, close location, volume and confluence inputs appear in AI data selection | Store component evidence alongside the resulting pattern label |
| Entry zones | Signal detail exposes a zone, reasoning, target, stop, and conflicts | Make a setup conditional and inspectable before treating it as an issued forecast |

Sources: [Accumulation](https://signalsengine.com/signalpedia/vpa-signals/accumulation-signals), [Distribution](https://signalsengine.com/signalpedia/vpa-signals/distribution-signals), [Continuation](https://signalsengine.com/signalpedia/vpa-signals/continuation-signals), [AI workspace](https://signalsengine.com/build/assets/AIEngine-Uq7GvHZQ.js), [Signal detail](https://signalsengine.com/build/assets/SignalDetailsModal-BEbdfUC1.js).

These are recognizable market-analysis concepts. Their usefulness depends on reproducible definitions, context, and incremental validation. Generic educational confidence stars are not empirical probabilities.

### 4.3 Order flow and off-exchange activity

| Capability | Evidence | Assessment |
|---|---|---|
| Cumulative delta | Educational bid/ask-volume description | Valuable if classification and timestamp alignment are credible |
| Price/delta divergence and absorption | Documentation and symbol fields | Useful hypotheses; require an explicit classifier and confirmation rule |
| Session comparison | Education plus consumer buckets | Opening/midday/closing context can be useful; normalize intraday seasonality |
| Large blocks and trade clusters | Symbol consumer | Descriptive size/cluster observations; participant identity is inferred |
| Lit/off-exchange splits | Pipeline and symbol consumer | Useful market-structure context, subject to classification limits |
| Off-exchange price levels | Dark-pool article and symbol consumer | Possible reference zones; avoid treating every print as new demand |
| Institutional/retail labels | Public interface | Weak unless the classification method and uncertainty are exposed |
| Iceberg and stealth labels | Consumer fields | Particularly conditional: public trade prints alone may not identify hidden orders |

Sources: [Cumulative delta](https://signalsengine.com/signalpedia/order-flow/cumulative-delta), [Session analysis](https://signalsengine.com/signalpedia/order-flow/session-analysis), [Institutional flow](https://signalsengine.com/signalpedia/order-flow/institutional-flow), [Dark-pool activity](https://signalsengine.com/signalpedia/order-flow/dark-pool-activity), [Symbol consumer](https://signalsengine.com/build/assets/V5SymbolDeepDive-C_rPXZeK.js).

The session education includes substantial foreign-exchange session discussion. It should not be mistaken for evidence of an implemented US-equity session model.

### 4.4 Options and volatility

| Capability | Mechanism or consumer expectation | Potential product value |
|---|---|---|
| GEX and gamma flip | Estimated exposure and regime context | High as qualified context |
| Call/put walls | Strike concentration references | High if units, population, and assumptions are clear |
| Expiry-aware views | Weekly/monthly/quarterly/special expiry, days remaining | High for event and horizon alignment |
| IV rank and percentile | Current IV relative to past range or observations | High; keep the two definitions distinct |
| Skew and term structure | Relative option pricing across strikes/tenors | High for scenarios and event context |
| Volume and OI PCR | Different positioning/activity measures | Moderate; use instrument-specific baselines |
| Sweeps, blocks, unusual premium | Size, execution style, volume/OI and premium anomalies | Conditional on source quality |
| Max pain | Expiry-level aggregate payoff heuristic | Lower; contextual display before signal authority |
| Squeeze/flush probability | Screener and market-flush consumer outputs | Unverified probability semantics |
| VPA/LSTM/blended options-informed targets | Signal consumer | Interesting interface; model benefit unproven |

Sources: [GEX](https://signalsengine.com/signalpedia/options-analytics/gamma-exposure-gex), [IV/skew](https://signalsengine.com/signalpedia/options-analytics/implied-volatility-skew), [PCR](https://signalsengine.com/signalpedia/options-analytics/options-put-call-ratio), [Unusual activity](https://signalsengine.com/signalpedia/options-analytics/unusual-options-activity), [Max pain](https://signalsengine.com/signalpedia/options-analytics/max-pain-theory), [Expiration predictions](https://signalsengine.com/build/assets/ExpirationPredictions-BscKnkgw.js), [Screener](https://signalsengine.com/build/assets/Screener-DDeqpR0A.js), [Market flushes](https://signalsengine.com/build/assets/MarketFlushes-CyRFtS-q.js).

### 4.5 Volume profile and auction structure

| Capability | Described function | Integration value |
|---|---|---|
| Point of control | Highest-volume price area; session and composite context | Shared reference level for charts, setups, and explanations |
| Value-area high/low | Boundaries of a selected concentration of traded volume | Acceptance/rejection and range-versus-trend scenarios |
| High/low-volume nodes | Congestion and relatively thin-volume zones | Structural targets and invalidation context |
| POC/value migration | Change across sessions | A compact way to show changing accepted prices |
| Unrevisited POCs and clusters | Multi-session references in symbol consumer | Useful optional overlays, subject to original definitions |

Sources: [POC](https://signalsengine.com/signalpedia/volume-profile/point-of-control), [Value area](https://signalsengine.com/signalpedia/volume-profile/value-area), [Volume nodes](https://signalsengine.com/signalpedia/volume-profile/volume-nodes), [Symbol consumer](https://signalsengine.com/build/assets/V5SymbolDeepDive-C_rPXZeK.js).

A profile built from actual trades and one approximated by distributing bar volume are different products. The implementation should identify which is being displayed.

### 4.6 Signal production, explanation, and evaluation

| Capability | Observed consumer or documented behavior | Assessment |
|---|---|---|
| Unified score | Multiple public score definitions | Useful compression only when semantics are stable |
| Conviction tiers | ULTIMATE/HIGH/MEDIUM/LOW filters; education uses stars | Presentation vocabulary, not proven probability |
| Entry/target/stop/R:R | Signals explorer fields | High-value common setup contract |
| Multiple horizons | Pipeline and expiry consumers | Useful if outcomes and overlap are handled correctly |
| VPA/LSTM/blended comparisons | Separate systems and disagreement view | High-value transparency; blending is not an independent vote |
| Supersession chain | Older/newer prediction links | Valuable auditability for changing forecasts |
| Active/evaluated/history filters | Signal and historical consumers | Necessary lifecycle visibility |
| AI trade explanation | Outcome summary, successes, failures, lesson | Valuable if grounded in immutable evidence |
| MFE/MAE and expected-value metrics | Daily-results fields | Better evaluation breadth than win rate alone |
| Data-selectable AI research | Date/symbol, selected feature groups, chart upload, saved history/favorites | Useful research workflow; generated text needs source links |
| Morning brief | Regime, scenarios, levels, setups, risks | High-value product integration |
| Evening recap | Grading, performance and lessons | Highest value when every issued setup is accounted for |
| Pattern education | 26 linked articles | Link explanations directly from signal evidence |
| War-room heatmap | Gamma ranking and horizon matrix | Optional visualization after coherent records exist |

Sources: [Scoring](https://signalsengine.com/signalpedia/prediction-system/unified-scoring), [Targets/stops](https://signalsengine.com/signalpedia/prediction-system/target-stop-calculation), [Conviction](https://signalsengine.com/signalpedia/prediction-system/conviction-levels), [Explorer](https://signalsengine.com/build/assets/Index-uXeJQRFV.js), [Disagreements](https://signalsengine.com/build/assets/Signals-CPyIk_da.js), [Prediction chain](https://signalsengine.com/build/assets/PredictionDetailsModal-CdGUHiw7.js), [Daily results](https://signalsengine.com/build/assets/DailyResults-CAC8sFre.js), [Daily brief](https://signalsengine.com/build/assets/DailyBrief-MMXEgeTU.js), [AI workspace](https://signalsengine.com/build/assets/AIEngine-Uq7GvHZQ.js), [War room](https://signalsengine.com/build/assets/WarRoom-CeGVLISM.js).

### 4.7 Fundamental and short-position context

The pipeline also describes float analysis, short interest, short-sale volume, days to cover, and a squeeze/retail-trap interpretation. A days-to-cover threshold of three is presented as part of a described setup. These are vendor-described enrichment and heuristics, not recovered production logic or validated participant classifications. They should be separated into observable data, delayed positioning estimates, and interpreted patterns. Section 6 explains why short-sale volume cannot substitute for short interest. [Pipeline module](https://signalsengine.com/build/assets/PipelineFlow-Cq0sncBE.js)

## 5. Important findings that change how we should interpret the product

### 5.1 A shipped realtime page is simulated

The inspected Realtime module creates and periodically updates trades, whale prints, options activity, anomalies, and aggregate flow using random values. This is direct client-code evidence of a simulated implementation in that module. It is not proof that every SignalsEngine data path is simulated or that an authenticated user currently lands on that exact version. [Realtime module](https://signalsengine.com/build/assets/Realtime-BTfLD7jr.js)

**Mastermind implication:** all fixture/demo data must carry an unmistakable mode label and be excluded from production signals and evaluation. A plausible-looking moving feed is insufficient evidence of a functioning data engine.

### 5.2 Connection status and data freshness are conflated in chart presentation

The charting module explicitly describes a 15-minute-delayed Massive feed while using LIVE for connection status. Its volumetric interface identifies an uptick-rule classification. Connected, current, and real-time are distinct states. [Charting module](https://signalsengine.com/build/assets/Charting-x9cMuOBc.js)

**Mastermind implication:** display transport health, source timestamp, observed delay, classification method, and last successful calculation separately. Delayed data may support research, but should not silently produce an immediate execution claim.

### 5.3 Alerts and watchlists include descriptive shells

The inspected Alerts and Watchlists page modules render descriptive cards without functional alert configuration or watchlist controls in those files. Other modules may implement related functionality; these particular pages are not evidence of a complete feature. [Alerts](https://signalsengine.com/build/assets/Alerts-C6jp6tkE.js) · [Watchlists](https://signalsengine.com/build/assets/Watchlists-D44SEpvP.js)

**Mastermind implication:** measure completion by actions the user can finish—create, edit, persist, trigger, acknowledge, revisit—not by visible navigation items.

### 5.4 Score descriptions are inconsistent

The educational scoring page describes a directional −100 to +100 score built from roughly equal technical, options, flow, and profile categories, with regime adaptation and confluence. Other product surfaces use a 0–100-style score, and the pipeline names a different weighting scheme. These may reflect different versions or different estimands; the public material does not reconcile them. [Scoring article](https://signalsengine.com/signalpedia/prediction-system/unified-scoring)

**Mastermind implication:** every score needs a name, range, meaning, version, and evaluation target. Avoid one unlabeled number that alternately means direction, quality, confidence, and probability.

### 5.5 Targets and conviction are heuristic descriptions, not a recovered model

Education proposes structural/ATR targets and stops, several risk/reward preferences, and star-based sizing suggestions. Those descriptions do not recover the production model or establish their appropriateness for Mastermind. [Targets/stops](https://signalsengine.com/signalpedia/prediction-system/target-stop-calculation) · [Conviction](https://signalsengine.com/signalpedia/prediction-system/conviction-levels)

**Mastermind implication:** adopt the explicitness of levels and invalidation, then define and evaluate our own rules. Keep personal portfolio sizing in the existing risk owner.

### 5.6 Advertised performance remains unverified

A win-rate claim needs an issuance ledger, sampling period, eligible universe, outcome definition, entry rule, competing stop/target order, costs, unresolved cases, and correction policy. None was established sufficiently to reproduce the advertised result.

This is an evidence gap, not proof of misconduct. It is also a practical lesson: our public performance presentation should link each aggregate to a reproducible cohort and evaluation method.

## 6. Market-data interpretation: requirements for a stronger implementation

### 6.1 Off-exchange is not synonymous with institutional buying

FINRA distinguishes ATS and non-ATS OTC activity and publishes transparency information with reporting delays. A trade location does not reveal the beneficial owner, the reason for the trade, or whether a large participant is accumulating. [FINRA OTC transparency](https://www.finra.org/filing-reporting/otc-transparency)

Preserve a chain of evidence:

1. Observed print and its reporting venue.
2. Any vendor classification and its definition.
3. Estimated aggressor side and uncertainty.
4. Aggregated imbalance.
5. A pattern interpretation.
6. A separately evaluated forecast.

Do not collapse all six into “institutions buying.”

### 6.2 Short-sale volume is not short interest

FINRA explicitly distinguishes daily short-sale transaction volume from outstanding short positions. These datasets answer different questions and have different coverage and publication timing. [FINRA explanation](https://syndication.finra.org/content/short-interest-what-it-what-it-not)

A squeeze feature should preserve short-interest observation date, publication date, float denominator, average-volume window, corporate actions, and borrow data availability. A high short-volume fraction alone should not become a squeeze probability.

### 6.3 Dealer gamma requires assumptions

Gamma exposure estimates depend on the option population, open-interest timing, multiplier, Greek model, and assumptions about who holds which side. Cboe's discussion emphasizes net risk and participant positions rather than equating gross options volume with hedging demand. [Cboe gamma analysis](https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/)

Use gamma as conditional market-structure context. State units explicitly—for example a chosen delta-notional change per specified spot shock—and retain the sign convention. A positive-gamma estimate is not itself a bullish forecast.

### 6.4 Trade-side classification must be named

Massive's trade stream supplies trades, exchanges, conditions, and timestamps; quote data supplies bid/ask information. A quote-matched classifier requires temporal alignment and an explicit treatment of ambiguous prints. An uptick classifier estimates a different quantity and cannot silently inherit the label “buy at ask minus sell at bid.” [Trades](https://massive.com/docs/websocket/stocks/trades) · [Quotes](https://massive.com/docs/websocket/stocks/quotes)

Store unclassified volume. Validate sequencing, late reports, corrections, auction prints, and session boundaries. Never allocate every ambiguous print to a side merely to complete a chart.

### 6.5 Rights and latency are part of feasibility

Massive distinguishes delayed and real-time connections and requires suitable commercial rights for redistribution. An individual plan price is not a commercial deployment estimate; derived outputs may also require contractual review. [WebSocket quickstart](https://massive.com/docs/websocket/quickstart) · [Redistribution guidance](https://massive.com/knowledge-base/article/how-can-i-redistribute-massives-market-data)

The first build should reuse already-admitted data. New stock-tick, NBBO, options, historical depth, or redistribution rights become justified only when the proposed feature has a clear user job and measurable incremental value.

### 6.6 Expectations and ownership data are delayed observations

SEC Form 13F reports quarter-end holdings and generally has a filing deadline up to 45 days later. It is useful ownership context, not a real-time tape. [SEC 13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f)

The same available-at discipline applies to revised macro series, earnings consensus, open interest, analyst changes, and corporate actions. Historical joins must use what was available then.

## 7. Mastermind source census: verified reusable substrate

The following findings are from the pinned Mastermind repository. They establish source implementation and static connections. No production data accrual or full customer journey was tested.

| Existing owner | What is present | Integration implication |
|---|---|---|
| brain/market_view.py | Deterministic aggregation, per-plane freshness, explicit absent/advisory states, disagreement handling | Reuse for market-wide context; do not turn every ticker feature into another global plane |
| brain/decision_context.py | Typed context over the market view, with authority restrictions | Keep consumer contracts consistent with the existing view |
| brain/signal_history.py | Point-in-time decision/lens archive; keep-first per date and ticker | Preserve its daily-snapshot grain; link event-level plans through the existing plan/episode owner |
| brain/decision.py | Typed thesis, evidence, dissent, entry levels, engine-derived falsifier | Reuse appropriate fields; its existing longer-horizon semantics are not an intraday trade contract |
| portfolio/predictions.py | Per-ticker/horizon prediction records, forward labeling, date-clustered scorecard | Extend the incumbent forecast owner and preserve its existing cohort semantics |
| brain/outcome_ledger.py | Thesis outcomes joined to decision-time lens snapshots | Add explicit setup/prediction references where required; do not double-count one outcome |
| brain/thesis_store.py | Thesis episodes and non-retroactive amendments | Keep thesis identity distinct from setup and observation identity |
| brain/calibration.py | Reliability-based de-confidencing | Trace its estimand and use before introducing another adjustment |
| portfolio/forward_evaluation.py | Forward evaluation and cohort controls | Reuse for prospective comparison where its contract fits |
| loop/holdout.py and loop/pbo.py | Holdout-use and backtest-overfitting infrastructure | Reuse methods; specify task-appropriate gates |
| brain/student.py | Optional CatBoost student with chronological evaluation; injection off by default | A native modeling baseline already exists; LSTM is not a prerequisite |
| brain/portfolio_learning.py | Observational lessons and typed context requests | Feed reviewed findings into existing learning ownership |
| app/scheduler.py | Daily maintenance calls prediction recording, grading, calibration, and learning | Static wiring exists; new work should follow the appropriate cadence and owner |

Primary source anchors: [Market view](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/market_view.py), [Decision context](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/decision_context.py), [Signal history](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/signal_history.py), [Decision](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/decision.py), [Predictions](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/portfolio/predictions.py), [Outcome ledger](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/outcome_ledger.py), [Student](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/student.py), [Learning](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/brain/portfolio_learning.py), [Scheduler](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/app/scheduler.py).

### 7.1 Daily snapshot identity boundary

The current signal-history archive keeps the first record for a ticker on a given date. That is a boundary of its daily-snapshot job, not evidence that the product lacks event-level plan identity. Adding a signal_id field alone would not change its deduplication. Preserve the archive's semantics and connect event-level plans through their incumbent owner, including the existing Prophet path discussed below.

The outcome ledger joins a thesis to a date/ticker lens snapshot. This is a useful incumbent connection; it is not proof that every future setup, every horizon, and every revision is already represented.

### 7.2 A concrete outcome-semantics limitation

The existing DecisionDoc derives a relative-return falsifier and constrains its horizon to a longer-term range. The outcome ledger evaluates that falsifier. This is not equivalent to a trade hitting its target before its stop, nor to a positive absolute return.

Preserve the existing thesis definition. Use and, where necessary, extend the incumbent plan/episode outcome method for conditional setups rather than relabeling existing thesis grades as trading wins.

### 7.3 Scope-sensitive gaps

Executable earnings research, replay components, and tests are present in Mastermind's research area; their existence should not be mislabeled “specification only.” Production integration requires separate evidence.

A branded morning-brief/evening-recap feature was not observed in the inspected Mastermind source scope. That is not a product-wide absence claim: Macro and Terminal have their own producers and consumers, and active PRs already reference briefs, options intelligence, and earnings.

### 7.4 Architecture rules for the integration

- Observations, setups, forecasts, theses, and outcomes are different entities. Link their identities; do not collapse them.
- A daily market-context freshness threshold cannot govern intraday flow.
- A probability clamp is not calibration.
- Small operational sample floors do not establish statistical adequacy.
- Options risk-severity ownership does not imply ownership of every options display or calculation.
- Existing null planes have specific meanings; they are not arbitrary slots for new features.
- A second calibration multiplier may or may not double-count evidence. Trace the current inputs and estimands before deciding.

## 8. Macro source census: considerable native analytical breadth

All implementation findings in this section mean **BUILT_NOT_PROVEN** unless a narrower state is stated. The research did not execute the engines, their tests, or a production customer journey. The table cites the pinned source, which is the basis for the inventory.

### 8.1 Reusable owners and the remaining work

| Capability | Existing source implementation | Remaining work justified by this research |
|---|---|---|
| Canonical technical features | [tech_catalog.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/tech_catalog.py) catalogs event/state features, direction, dependency family, and context/setup/trigger/participation/risk roles | Register any new deterministic pattern in this owner; avoid a competing indicator list |
| Technical confluence discovery | [tech_confluence.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/tech_confluence.py) searches combinations and handles completed-week features, duplicate patterns, and cohort statistics | Treat its ranked test half as selection data; evaluate chosen recipes on an untouched outer period |
| Trend, momentum, compression, relative strength | Catalog and its existing indicator modules | Reuse and explain; another RSI/MACD/MA engine adds little |
| Volume-price behavior | [volume_signature.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/volume_signature.py) describes up/down-volume and OBV behavior; [bottom_radar.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/bottom_radar.py) includes climax/dry-up and washout/reclaim ideas | Inspect semantic overlap before adding named VPA sequences; current labels are not demonstrated alpha |
| VWAP and profile | [indicators_m2.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/indicators_m2.py) implements daily-bar approximations, AVWAP, POC, value area, and retest events | Align with Terminal's chart implementations; distinguish daily approximations from intraday observations |
| Entry plans | [entry_signal.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/entry_signal.py) already emits buy zone, chase boundary, stop, timing window, and horizon context | Link an issued conditional setup to evidence, revisions, and the appropriate outcome method; do not rebuild these fields |
| Selection versus timing | [setups.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/setups.py) distinguishes selection/timing and context confirmers | Preserve the different jobs; do not let every context label alter ranking |
| Entry radar | [entry_radar](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/entry_radar/__init__.py) has nomination/provenance/TTL/deduplication, readings, episodes, replay, and evaluation components | Reuse attention and episode infrastructure while preserving its explicit lack of ranking, sizing, gating, origination, or escalation authority |
| Gamma structure | [gex_engine.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/gex_engine.py), [gex_model.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/gex_model.py), and [gex_state.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/gex_state.py) contain exposure, walls, flip, expiry surfaces, and persistence | Expose source population, freshness, units, and positioning assumptions; reuse conditional context |
| Volatility analytics | [options_hub.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/options_hub.py) and gex_model contain IV history/rank, skew, term structure, and expected-move calculations | Preserve history coverage and distinguish observed option prices from model-derived measures |
| Put/call and max pain | Existing GEX/options owners | Present as context; max pain and heuristic pin estimates should not gain forecast authority through UI wording |
| Intraday options flow | [live_flow.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/live_flow.py), [live_flow_poller.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/live_flow_poller.py) | Verify current delivery; reconcile current trade-plus-quote logic with older descriptions and consumers |
| Unusual options and sweeps | live_flow includes unusual-name premium measures and a multi-print/multi-venue sweep-like classifier | Repair the documented cross-batch grouping gap if the consumer needs it; label execution style as inferred |
| Session flow | [options_flow.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/options_flow.py) includes opening/middle/closing profiles; live flow has intraday time/DTE/root views | Standardize session calendars and baselines; this is not a missing platform-wide concept |
| Intraday participation | [intraday_flow.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/intraday_flow.py) contains NCP, relative volume by time, and durability features; radar consumes flow context | Verify cadence, source semantics, and the distinction between attention and investment merit |
| Off-exchange participation | [darkpool_signals.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/darkpool_signals.py), venue concentration, and short-volume owners | Do not equate participation ratios with dark-pool volume-at-price levels or institutional buying |
| Equity pressure-response research | [market_microstructure](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/market_microstructure/README.md) contains a research implementation with synthetic-test limits | Establish actual feed coverage and prospective evidence before any production interpretation |
| Trade-sign uncertainty | [flow_sign_uncertainty.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/flow_sign_uncertainty.py) implements research logic and refuses unsupported calibrated aggressor probabilities | Reuse the uncertainty discipline; lack of independent labels does not erase the executable research |
| Macro regime | [regime.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/regime.py), axes and transition/coherence modules | Reuse broad context and transitions; avoid counting the same macro input repeatedly through correlated outputs |
| Breadth and cross-asset context | [advanced_breadth.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/advanced_breadth.py), basket divergence, sector and cross-asset owners | A native differentiator for interpreting a local price pattern |
| Earnings | [earnings_narrative](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/earnings_narrative/), release binding, blackout and catalyst owners | Join genuinely available expectations and released facts to price response; do not invent an expectations gap from missing consensus |
| News | [news_common.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/news_common.py) and news-impact owners | Use source-quality and context rules; a headline's presence is not automatically a signal |
| Daily/portfolio briefs | [briefing.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/briefing.py), [portfolio_brief.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/portfolio_brief.py) | Reuse existing calculations and their explanatory projection; portfolio brief explicitly originates no new signal or number |
| Recurring delivery | [recurring_briefs.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/recurring_briefs.py) has daily-after-close and weekly subscription slots | Add a linked setup/recap presentation through this owner where appropriate; do not add another scheduler |
| Alerts | [alerts.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/alerts.py), triage, and delivery owners | Reuse change-triggered, idempotent delivery; workflow severity does not confer risk authority |
| Market Memory | [neuralweb](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/neuralweb/) and [market_memory contracts](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/contracts/market_memory/) include observations, forecasts, outcomes, lineage, retrieval, and revisions | Link qualified setup evidence and permitted outcomes; preserve training/promotion eligibility per record |
| Calibration and learning | [calibration_hub.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/calibration_hub.py), desk scoring, and [metabolism](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/metabolism/) | Reuse evaluation and observational learning; diagnostics do not automatically change production rules |

### 8.2 Four important implementation details

**Entry levels and invalidation already exist.** entry_signal emits a buy zone and stop. Its range estimate in the inspected path uses close-to-close changes as a proxy because the necessary low/high input is absent there. The integration must retain the method label or obtain appropriate OHLC for a true range calculation. Calling the existing field ATR does not make the underlying measurement equivalent to conventional true range. A future setup must not silently inherit a different risk distance merely because it shares a field name.

**Sweep-like events already exist.** live_flow groups at least three prints across at least two exchanges within a two-second window. That is an execution-pattern heuristic, not direct knowledge of an investor's intent or a guaranteed parent order. The code explicitly documents a cross-batch gap: retained cluster state does not participate in the current grouping calculation. Boundary-aware grouping, correction handling, and duplicate prevention are a specific repair; a new sweep engine is not justified. [Entry source](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/entry_signal.py) · [Live-flow source](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/live_flow.py)

**There are multiple data generations.** A daily indicator module's statement that its store lacks intraday data does not establish that the entire platform lacks an intraday feed. Current live-flow code expects options trades with NBBO, while older flow-signing descriptions refer to an earlier entitlement state. The production path, effective feed, freshness, and consumer must be traced before any procurement decision. [Poller](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/live_flow_poller.py) · [Legacy/current flow context](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/options_flow.py)

**Profile precision depends on input granularity.** The inspected Macro daily profile assigns each daily bar's volume to its typical-price bin. POC and a 70% value area are useful descriptive approximations, but they are not an observed distribution of every trade in that session. Better node labels do not repair coarse input data. Chart and signal consumers should show the same basis and resolve which owner supplies the required resolution. [Daily profile implementation](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/indicators_m2.py)

### 8.3 Validation limits that the masterplan must preserve

The confluence discovery code ranks candidates using its test half. Once selected on that period, those results are part of development. Wilson bounds, monthly aggregation, and duplicate filtering do not restore an untouched final test. Selected recipes need a frozen specification and a fresh outer holdout or chronological walk-forward evaluation. Forward labels crossing a split and cross-sectional market dependence also require explicit handling. [Confluence implementation](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/tech_confluence.py) · [Backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

Market Memory's Q18 close-ratio outcome is an exact arithmetic measurement under a restricted contract. The inspected contract explicitly marks the measurement as raw/unadjusted, not an economic return, and ineligible for training or promotion. It is not a probability-calibration result. Likewise, a fitted score-to-probability function in bottom_radar establishes implementation; its empirical calibration requires a separate artifact and evaluation review. [Memory outcome contract](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/contracts/market_memory/spy_experience_outcome_revision.v1.schema.json) · [Bottom radar](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/bottom_radar.py)

### 8.4 Candidate gaps, not blanket absence claims

No complete implementation of the competitor's exact named VPA suite was established in the inspected Macro modules. However, washout/reclaim, climax/dry-up, volume signatures, and other patterns overlap with some of those jobs. A naming mismatch is not a capability gap. The same caution applies to opening-range, divergence, and volume-node functionality, which can exist in the separate Terminal chart layer.

The highest-priority verification target is continuity across existing owners: whether a user can follow the evidence available at issuance through the conditional plan, its revisions, its appropriate outcome, and the complete recap. Where that trace fails, the failure defines the integration work. Unverified continuity is not evidence that the common plan or lifecycle is missing.

## 9. Terminal and the shared Prophet plan path

The separate Terminal census and targeted follow-up reads change the assessment materially. A common plan and outcome workflow already exists in source. It must anchor the integration.

### 9.1 Prophet already supplies the central plan object

Terminal's [SignalCard](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/prophet/SignalCard.tsx) defines PlanSummary with an ID, asset, direction, entry, targets, invalidation, horizon, minimum hold, lifecycle phase, management confidence, entry zone/state, optional option contract, and reconstruction disclosure. Its comments and the Macro publisher identify the same producer-owned rows as the source for Dashboard and Terminal.

Targeted inspection of Macro found these incumbent owners:

| Owner | Existing responsibility |
|---|---|
| [prophet_bridge.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_bridge.py) | Candidate admission, stable formation-based plan ID, geometry, entry zones, provenance clocks, source binding and origination |
| [options_structure.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/options_structure.py) | prophet.trade_plan/v1 and prophet.management_state/v1 contracts and validators |
| [prophet_integrity.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_integrity.py) | Append-only corrections, quarantine and effective reader projections |
| [prophet_management.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_management.py) | Management phase, components, excursion state, descriptive action projection and stale-price handling |
| [build_prophet.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/build_prophet.py) | Frozen source-board snapshots, plan/state/index publication, forward ledger and outcome summary |
| [prophet_arena.py](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_arena.py) | Frozen champion/challenger shadow evaluation, including a closure-policy challenger |

Plan identity is based on ticker, direction, and formation date. Existing IDs suppress duplicates, and an existing open plan for the same ticker/direction suppresses another formation under the current policy. Additional evidence can attach to that plan without creating a duplicate economic opportunity. Changing that policy to support many recipes or horizons is a deliberate product and evaluation decision, not a routine schema cleanup.

The inspected geometry derives a risk unit from entry and invalidation, with targets at 1.5R and 3R and a default 45-calendar-day horizon subject to existing extension logic. These are implemented rules, not verified predictive price targets. Plans are preserved while management state evolves. Correction overlays cannot be used to silently rewrite identity or trade geometry. Source-board bytes are frozen for provenance. [Bridge](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_bridge.py) · [Integrity](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_integrity.py) · [Publisher](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/build_prophet.py)

The current forward ledger already waits for trigger confirmation, scans daily closes strictly after the plan's price-basis date, and records invalidation, T2, T1, expiry or NO_ENTRY. Horizon expiry and reported holding duration use that declared plan clock; they do not reset at later trigger confirmation. Untriggered plans are excluded from the scored win-rate denominator. The first terminal close ends that ledger episode; T1 followed later by T2 remains T1. Returns are measured from the original stated entry even when trigger confirmation comes later, and option P&L is not supplied by this path. These are essential measurement semantics, not a missing outcome engine. [Outcome evaluator](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/build_prophet.py)

### 9.2 Concrete review findings to resolve before expansion

These findings come from pinned source inspection. Candidate defects require focused reproduction; no runtime bug is claimed as proven here.

| Finding | Evidence and implication | Acceptance criterion for follow-up |
|---|---|---|
| Same-build closure projection may lag | build_prophet constructs rows using an earlier closed-outcome read, advances the ledger afterward, and then publishes counts from those rows | A newly closed plan appears consistently closed in that build's index, counts, instructions and recap |
| Entry-zone state and ledger activation use different rules | Zone evaluation derives fill/expiry/conversion separately; the ledger reads the scalar trigger and daily closes | Displayed instructions, zone state, activation and evaluation either implement the same policy or explicitly explain their different purposes |
| Existing return is not executable trade P&L | The current ruler uses original entry, daily-close outcomes and first T1 termination; trigger-time fill and costs are not its measurement | Preserve the historical ruler; evaluate an execution-aware or eventual-target challenger under an explicit new method/version |
| A confidence input appears not to reach management | Origination computes a local confidence and emits conviction metadata; management reads confidence with a default of 60 | Reproduce the handoff and determine intended policy with the owner before changing the value |
| Live and Arena closure logic have separate implementations | Arena's replay closure mirrors the live evaluator | Equivalent observations produce equivalent outcomes for the same method/version; intentional challenger differences remain named |
| Generalized bearish/multiple-plan behavior is not established | Current bridge origination is BULL-focused; some schemas/evaluators support BEAR, while return reporting uses underlying price change | Verify directional returns, eligibility, identity and portfolio policy before expanding the product claim |

Sources: [Publisher](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/scripts/build_prophet.py), [Bridge](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_bridge.py), [Management](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_management.py), [Arena](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/prophet_arena.py).

Additional zone cases deserve explicit tests: pre-publication bars, a gap below the entire entry band, a touch after expiry, and the order in which fill and expiry are evaluated. Passing those tests is more valuable than introducing another set of plan fields.

### 9.3 Terminal's reusable consumer and calculation surfaces

All rows describe source implementations, not independently verified deployment.

| Surface | Pinned implementation | Reuse and qualification |
|---|---|---|
| Shared market read | [readingPayloads.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/shared-shell/readingPayloads.ts) | Existing Today/shared-shell consumer; verify actual payload freshness |
| Symbol investigation | [AnalysisWorkspace.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/workspaces/AnalysisWorkspace.tsx) | Extend the current symbol context and navigation |
| Plan stream and levels | [SignalCard.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/prophet/SignalCard.tsx) | Existing plan entry, targets, invalidation, progress and phase presentation |
| Chart indicator registry | [indicators.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/indicators.ts) | MA, RSI, MACD, Ichimoku, VWAP variants, profile, day-trade studies and large trades already registered |
| Session VWAP/opening range/RVOL | [intradayMath.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/intradayMath.ts) | Implemented chart calculations; check actual input/session basis before server promotion |
| Chart CVD | intradayMath.cvdApprox | OHLCV candle-shape approximation, not observed aggressor tape |
| Chart volume profile | [indicatorMath.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/indicatorMath.ts) | POC/VAH/VAL over bar-volume bins; no inference of per-trade detail |
| Money-flow profile | [moneyFlowProfile.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/suites/structure/moneyFlowProfile.ts) | Alternate profile display explicitly labels its candle-shape buy/sell estimate |
| Swing-failure pattern | [sfp.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/suites/structure/sfp.ts) | Confirmed swing breach/reclaim with volume/reclaim-speed descriptor; overlaps part of spring/upthrust analysis |
| Price/oscillator divergence | [shared/divergence.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/suites/shared/divergence.ts) | Regular/hidden bullish/bearish divergence, with pivot-confirmation timing |
| Larger indicator suites | [suites catalog](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/suites/catalog.ts) | Existing momentum, flow, structure, trend and multi-timeframe chart studies |
| Transaction-based large trades | [largeTrades/engine.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/largeTrades/engine.ts) | Validates trade/cancel records, side-method, provenance, availability, corrections and coverage; source data mode is explicit |
| Futures footprint/profile | [FuturesMicrostructureChart.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/futures/FuturesMicrostructureChart.tsx), [futuresVolumeProfile.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/futuresVolumeProfile.ts) | Observed capture-window profile retains buy/sell/unknown quantities; do not generalize to complete US-equity coverage |
| Options workspace | [OptionsHubView.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/OptionsHubView.tsx), levels/structure/exposure-map components | Reuse existing GEX, expiry, IV and flow consumers |
| Screeners | [ScreenerView.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/ScreenerView.tsx), [smartScreen/review.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/smartScreen/review.ts) | Existing screens and reproducible definition/generation review references |
| Watchlists | [watchlists.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/watchlists.ts) | Existing persistence/API; some review marks have separate client-only scope |
| Alert cockpit and receipts | [AlertsCockpit.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/alerts/AlertsCockpit.tsx), [alerts route](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/app/api/alerts/route.ts) | Existing user alert workflow and fire-receipt history; delivery status is not an economic outcome |
| Investigation review | [investigationReview.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/investigationReview.ts) | User assessments of saved evidence/receipts with revisions; not an automatic trading grader |
| Recurring briefs | [BriefsInbox.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/briefs/BriefsInbox.tsx), [briefs.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/briefs.ts) | Existing subscribed-delivery inbox with missing/degraded handling and external producer |
| Portfolio brief | [PortfolioBriefPanel.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/PortfolioBriefPanel.tsx) | Reuse the existing portfolio projection |
| AI research | [BrainWidget.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/BrainWidget.tsx) and its gateway proxy | Existing reasoning interface; add reproducible references through current owners |
| Earnings interpretation | [EarningsRepricingEvidence.tsx](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/components/fin/EarningsRepricingEvidence.tsx), [earningsExpectationBoundary.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/terminal/lib/earningsExpectationBoundary.ts) | Separates released facts, guidance, estimates and reaction; refuses unsupported priced-in inference |
| Existing signal research | [signal_layer](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/signal_layer/) and backtest contracts | Additional forward/replay research exists; provenance and eligibility must be traced before reuse |

The chart layer alone overturns proposed platform-wide gaps for opening range, divergence, profile, and large trades. However, a display calculation is not automatically an admitted server signal. Where a recipe needs it, compare its timing, parameters, missingness and units with the server owner and promote an exact, versioned definition through the normal process.

The census found limited or old committed sample payloads in some surfaces. Those samples establish repository contents, not current production coverage. The report does not infer that only two symbols work live from two committed examples. Migration files likewise show intended schema; deployment acceptance must be checked separately.

The personal-accuracy user_claims store is for user-authored calls. It should not be populated automatically with model-issued plans merely because it has a resolution field. Investigation review records user assessments, and alert_outbox records firings/delivery. Preserve those separate jobs and reference the existing Prophet or other appropriate economic outcome owner. [Personal accuracy contract](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/942eeb526b4fd64b17aa66042c0d0ec2c3a5b94e/supabase/migrations/0017_personal_accuracy_ledger.sql)

### 9.4 Comparative gap disposition

This matrix governs build recommendations. “Reuse” means source capability is present; it does not claim runtime acceptance.

| SignalsEngine idea or requested capability | Native finding | Disposition |
|---|---|---|
| Market dashboard and symbol deep dive | Macro context plus Terminal investigation surfaces | Reuse; verify cohesive navigation and shared references |
| Technical indicator suite | Macro catalog and Terminal chart suites | Reuse; avoid another registry |
| Named accumulation/distribution/continuation patterns | Native volume/bottom/reclaim/compression and Terminal swing-failure overlap | Verify semantic gaps, then add only specific missing sequences |
| Opening-range analysis | Terminal implementation exists | Reuse; server use needs explicit admission and timing parity |
| Multi-timeframe momentum/divergence | Both native confluence and Terminal studies exist | Reuse; preserve completed-bar/confirmation timing |
| POC/value area/AVWAP | Native implementations exist at different data granularities | Reconcile basis and consumer meaning |
| Explicit HVN/LVN and unrevisited-node recipes | No equivalent exact descriptor established in inspected profile functions | Candidate extension; node definitions and incremental value still required |
| Stock CVD/absorption | Chart approximation and pressure-response research exist; operational exact stock-tape path not established here | Data/path verification before a new engine or feed |
| Futures footprint | Existing capture/replay consumer and observed volume arithmetic | Reuse within its actual coverage |
| Large trades/blocks | Existing transaction-based Terminal engine and native flow features | Verify coverage and classification; do not infer institution identity |
| Unusual options and sweep-like events | Existing live_flow implementation | Targeted boundary/correction repair and integration |
| Off-exchange participation | Existing FINRA/off-exchange analytics | Reuse; not equivalent to dark-pool price-level demand |
| Gamma/flip/walls/expiry surface | Existing native options stack and UI | Reuse with assumptions and freshness |
| IV rank/skew/term/PCR/max pain | Existing options owners | Reuse; improve interpretability where needed |
| Unified entry/target/stop/horizon plan | Prophet contracts, bridge and Terminal consumer exist | Reconcile semantics and trace the actual journey |
| Plan identity and corrections | Existing immutable plans, provenance, integrity overlays | Extend references while preserving current formation/open-plan policy |
| Forecast/thesis/outcome records | Existing Mastermind and Macro owners | Link exact semantics; do not collapse them |
| Model comparisons | Existing student, replay and Prophet Arena | Reuse; LSTM is optional research, not a missing prerequisite |
| Confidence tiers | Existing scores/management confidence and calibration code | Audit meaning and handoffs; probability validity remains separate |
| Active/history/evaluated views | Existing plan/ledger/consumer components | Verify completeness and same-build consistency |
| Alerts/watchlists | More substantial native implementations than the inspected competitor shells | Reuse; avoid a replacement workflow |
| Morning/recurring/portfolio briefs | Existing producers, scheduling and inbox | Verify and extend referenced plan coverage/cadence |
| Complete daily setup recap | Related grading, briefs, plan ledger and review owners exist | Product-path verification; add a projection only where missing |
| AI explanation/research workspace | Existing Brain and evidence consumers | Add snapshot/prompt/answer reproducibility through current interfaces |
| Pattern education | Existing technical definitions and playbooks | Add concise in-context explanations for admitted methods |
| Signal-linked memory | Extensive native memory, outcome and learning owners | Preserve eligibility and link original evidence/outcome IDs |
| Advertised high win rate | No verified competitor ledger or native claim justified by this research | Do not copy; publish reproducible cohorts only |
| Institutional/iceberg certainty or automatic conviction sizing | Public claims do not establish observability or validity | Do not adopt as facts or authority |

## 10. Integration design: one continuous product workflow

This section is a proposed design, not a claim of implementation. Its purpose is to connect existing capabilities while preserving their distinct meanings and authorities.

### 10.1 The user journey to complete

The product should answer six connected questions:

1. **What changed in the market?** Macro provides regime, breadth, rates, credit, liquidity, volatility, sector rotation, and event context, with data coverage.
2. **Where should I investigate?** Existing discovery, screeners, watchlists, and advisory radar surface relevant observations.
3. **What is the actual conditional plan?** The incumbent plan producer supplies entry conditions, levels, horizon, invalidation, scenarios, and provenance.
4. **Why does it exist, and what disagrees?** Terminal exposes component evidence, source time, model assumptions, and conflicting information.
5. **What changed after issuance?** Existing lifecycle records, alerts, and briefs show transitions without rewriting the original claim.
6. **What happened, and what should we learn?** The appropriate outcome owner grades the specified claim; the recap accounts for the whole issued population, and learning stays within existing promotion rules.

SignalsEngine's public consumers make this sequence understandable. Mastermind can make the evidence behind it broader and the accounting more rigorous.

### 10.2 Ownership map

| Layer | Reuse the incumbent owner | Proposed integration responsibility |
|---|---|---|
| Acquisition | Existing Macro collectors, admitted feeds, pollers, source storage | Attach actual observation/availability timing, coverage, units, corrections, and rights |
| Features | Macro tech_catalog, options/GEX, flow, breadth, regime, earnings owners; appropriate chart studies | Reuse definitions and register narrowly missing calculations; distinguish server research features from display studies |
| Attention | Entry radar, existing screeners and watchlists | Surface observations with their current authority limits |
| Selection and plans | Existing setup, Prophet/plan, prediction, and thesis owners | Preserve their identities and meanings; expose a common read model instead of introducing another registry |
| Market context | Existing Macro regime and Mastermind market-view contracts | Provide context and conflicts at the right horizon |
| Consumer projections | Macro Dashboard, Terminal, existing brief and alert APIs | Render the same plan version and provenance; do not recalculate authoritative values in each UI |
| Evaluation | Existing episode, forecast, thesis, replay, scoring, and outcome owners | Use an explicit evaluation method for each claim; cross-reference, do not merge incompatible results |
| Learning | Existing experiment/holdout/calibration/Market Memory/metabolism owners | Record lessons, retrieve comparable prior cases, and propose separately reviewed changes |
| Operations | Existing scheduler, delivery, telemetry and release procedures | Prove freshness, idempotency, recoverability, and the actual user journey |

An API projection may join records for convenience without becoming a second source of truth. The same distinction applies to a Terminal detail drawer or a daily recap: a convenient presentation does not own the underlying forecast.

### 10.3 Identity and provenance contract

Inventory these fields in the current contracts first, retain existing definitions, and add only the missing relationships:

| Entity | Identity and minimum semantics |
|---|---|
| Observation | Source/provider, instrument identity, event timestamp, publication/availability timestamp, ingest time, units, method, correction/version, coverage, observation reference |
| Feature | Canonical feature identifier/version, parameters, input references, computation time, lookback, dependency family, role, and missingness reason |
| Setup/plan | Incumbent plan ID, recipe/version, instrument, direction/scenario, issuance time, trigger, horizon, validity window, original evidence, level basis, authority and mode |
| Forecast | Its own forecast ID, exact target variable, horizon, benchmark, issue-time data, optional calibrated probability/model version |
| Thesis | Its own thesis ID and stated proposition/falsifier, linked to related forecasts or plans |
| Episode | The actual trigger/activation time and supported observed path for a setup; repeated episodes need explicit identity |
| Outcome | Outcome ID, evaluated object ID/version, evaluation method/version, horizon/session basis, observation references, status, cost assumptions, revision chain |
| Delivery | Existing delivery ID, channel/subscription, referenced object/version, slot, acknowledgement or honest failure state |

One ticker/date can have a daily market snapshot, several analytical setup observations, three forecast horizons, an earnings thesis, and multiple revisions. Those must remain distinguishable. Under Prophet's current single-open-plan policy, multiple observations can reference one economic plan; do not originate extra plans merely to preserve evidence. A combined presentation reference cannot replace individual identities or their cohort rules.

Historical records should retain what was known at issuance. A corrected source can produce a new revision with a reason and availability time. It must not silently improve the original evidence retrospectively. Reconstructed and prospective records need separate cohort treatment.

### 10.4 Time, missingness, and calculation basis

A single as-of field is insufficient for many combined-data decisions. Keep the economically relevant event time, the provider's publication time where available, system availability/ingestion, computation time, and expiration. A macro release can be observed at one time, revised later, and used by a model after that; the backtest must respect those differences.

The consumer should show:

- Data cutoff and session/calendar.
- Source latency and whether the current value is stale.
- Coverage of required inputs and why a component is missing.
- Calculation basis: observed trade/quote, daily-bar approximation, vendor field, heuristic, model estimate, or language-model explanation.
- Mode: production observation, replay, prospective shadow, reconstructed history, or fixture.

Missing options data cannot become a neutral options vote. A delayed quote cannot support an immediate trigger unless the plan's semantics explicitly tolerate that delay. Calendar logic must account for holidays and early closes; a weekday offset alone is inadequate for every use.

### 10.5 Lifecycle and outcome states

Use the incumbent lifecycle where it fits and map the following distinctions explicitly. This table is a taxonomy across object types, not a grant of new Prophet transitions. Current Prophet preserves the originated plan's identity and geometry; management projections and permitted integrity overlays may change. A different trigger, geometry, or economic evaluation rule requires an explicitly admitted candidate or versioned challenger. It is not an integrity correction and must not bypass the current single-open-plan policy. Alternative grading is a new measurement method, not a correction to a previously valid historical result.

| State or transition | Meaning |
|---|---|
| Observed condition | Something worth inspecting; may remain advisory |
| Issued conditional plan | A versioned plan exists under its legitimate owner |
| Awaiting trigger | The entry/activation condition has not occurred |
| Activated episode | The trigger occurred under declared price-path and timing rules |
| Untriggered expiry | No supported activation before the validity window ended |
| Pre-entry invalidation | The setup ceased to be valid before activation |
| Active revision | A new version is issued with a reason; the original remains available |
| Superseded | A later plan/version replaces the current presentation; historical evaluation policy remains explicit |
| Resolved | The appropriate outcome can be measured: target/stop, horizon return, event occurrence, or thesis result |
| Ambiguous/unresolved | Observations cannot determine the path or the horizon has not matured |
| Corrected outcome | An append-only correction references the prior result and explains the change |

An untriggered setup is neither a successful trade nor a losing trade. A warning that never specified an entry should not be forced into a trade-return table. A fixed-horizon options episode that is explicitly not target-aligned must not be relabeled as target-before-stop success.

### 10.6 Replace the overloaded confidence number with separate meanings

| Display concept | Question answered | Required discipline |
|---|---|---|
| Direction/scenario | Which outcome or branch is described? | Not itself a probability |
| Signal strength | How unusual or pronounced is the measured condition? | State the comparison population and scale |
| Management score | How does the incumbent policy describe the current plan's management state? | Neither calibrated success probability nor automatic pick rank |
| Agreement | Which distinct evidence families support or oppose it? | Do not count correlated transforms as independent votes |
| Data quality | Are the observations complete, timely, and fit for this use? | Missingness and inference uncertainty remain visible |
| Probability | How often does this precisely defined outcome occur under the model? | Calibrate and evaluate for the specific event, horizon and cohort |
| Readiness | Is the plan triggered, waiting, blocked, expired, or only observational? | Preserve the existing authority and state machine |

A composite score can help sort a list where the existing ranking owner authorizes that use, but it needs one documented meaning. If its calibration is not established, show a score or evidence summary, not a percentage that looks like a chance of success.

### 10.7 Combine engines without counting the same information repeatedly

A moving average, MACD, momentum model, and price-based regime classifier may all reuse the same price history. An option-flow model may also incorporate gamma and IV features. A blended model trained on those features is not another independent confirmation.

Use the catalog's dependency-family metadata and preserve a component graph. Separate relatively distinct questions: market regime, broad participation, symbol price/volume behavior, derivative positioning/activity, event expectations, and data quality. Regime can condition which setup is applicable without automatically contributing an extra bullish vote.

The first production candidate should use transparent, bounded composition over current features. Then compare nested systems: incumbent native baseline; baseline plus a specific price/volume condition; plus options context; plus adequately measured flow. Keep a new component only if it improves a declared user or forecasting objective after costs, latency, abstention, and uncertainty.

An LSTM is one possible later experiment. The public evidence does not establish a reason to favor it over Mastermind's existing student or simpler models. The language model should explain referenced measurements, identify missing evidence, and support research; it should not manufacture a numeric signal from unavailable data.

## 11. Original signal and warning recipes

These are research hypotheses for Mastermind, not recovered SignalsEngine formulas or validated trading recommendations. Start with a small liquid universe already covered by admitted sources. Freeze the exact thresholds, eligibility, outcome, and evaluation period before testing. Horizon ranges below indicate an initial research scope, not optimized settings.

### 11.1 Regime-supported pullback recovery

**User job:** distinguish an ordinary pullback in a supported trend from deteriorating structure.

**Inputs:** native trend and relative strength, sector/breadth context, volatility/regime, an existing AVWAP or profile reference with a declared basis, volume contraction during the pullback, and a confirmed recovery event. Options structure can supply a conflict or scenario constraint.

**Conditional plan:** in prospective shadow, define and record the reclaim or acceptance event under the recipe's frozen activation rule. Reuse the existing plan and evaluation owners. Retain current Prophet trigger and closure semantics unless a separately evaluated, versioned policy is admitted. Structural failure, time limit, and any stop/target hypothesis must follow declared rules rather than retrospective chart selection. Initial research can focus on several sessions to a few weeks.

**Abstain when:** the reference is stale, the volume history is inadequate, the event has already moved beyond the allowed zone, or the macro/event context violates the recipe's predeclared scope.

**Comparison:** native trend/relative-strength baseline, then add the pullback sequence and each context family separately. Reuse tech_catalog, existing entry/plan owners, and the appropriate episode evaluator.

### 11.2 Breadth-supported expansion

**User job:** identify an expansion supported by participation rather than a narrow price move.

**Inputs:** compression or range structure, a completed breakout/acceptance event, time-normalized volume where appropriate, sector leadership and breadth, with regime and upcoming events as context.

**Conditional plan:** require a defined price acceptance condition, not merely an intrabar touch. Track failure back into the prior range and a finite observation window. Begin with daily/confirmed-bar horizons that existing data can support; an intraday variant is a separate recipe.

**Abstain when:** breadth coverage or membership is stale, the breakout price is outside the allowed chase boundary, or the bar/session is incomplete.

**Comparison:** simple breakout, breakout plus volume, and then breadth/sector context. Preserve warning versus actionable-plan authority.

### 11.3 Deterioration beneath index strength

**User job:** warn that index-level strength is becoming less representative.

**Inputs:** existing breadth divergence, participation concentration, sector dispersion, volatility/credit context, and optionally failed advances or distribution-like price/volume behavior.

**Output:** a risk-context warning with the supporting changes, counterevidence, and what would resolve it. It does not automatically originate a short or reduce position size.

**Abstain when:** the underlying constituent population changes without a comparable history or required breadth observations are missing.

**Evaluation:** warning recall before a defined deterioration event, lead time, false-alert burden, persistence, and usefulness relative to a simple breadth baseline. Trading P&L alone is the wrong primary measure for this job.

### 11.4 Post-earnings expectation reset

**User job:** determine whether verified new results and guidance support a changed interpretation after a release.

**Inputs:** actual released figures and publication times, previously available consensus where rights and vintage permit it, company guidance, event-linked price/volume acceptance, and comparable episodes from existing memory.

**Conditional plan:** a research-only event interpretation precedes any separately admitted plan. The plan needs an explicit post-release observation window and a structural or thesis falsifier. Consider the first several sessions separately from longer-term fundamental outcomes.

**Abstain when:** prior estimates are unavailable, vintages cannot be established, the reported metric is not comparable, or the event association is uncertain. Show “expectations not established” instead of inventing a priced-in score.

**Comparison:** simple post-event price response, verified-results-only context, and then genuinely available expectations. Respect the existing earnings boundary and active related work.

### 11.5 Gamma-conditioned auction scenario

**User job:** understand whether current option structure is consistent with a range/mean-reversion scenario or an expansion scenario.

**Inputs:** existing GEX model and its assumptions, open-interest age, expiry distribution, skew/term structure, spot relative to reference levels, and observed price acceptance or rejection.

**Output:** conditional branches. A range scenario and an expansion scenario each specify confirming evidence and invalidation. Gamma sign alone does not select a bullish direction. Walls and flips remain reference levels unless an independently defined plan uses them.

**Abstain when:** the chain is thin, OI is stale for the intended horizon, gamma assumptions dominate the result, or relevant expiry exposure is unobserved.

**Comparison:** price/volatility baseline versus the same rule conditioned on the declared gamma estimate. Evaluate realized range/volatility and branch outcomes before presenting directional forecasts.

### 11.6 Persistent flow with accepted repricing

**User job:** investigate sustained activity that accompanies durable repricing.

**Inputs:** existing qualified options-flow events and session baselines, explicit sign uncertainty, unusual activity persistence, underlying price/volume acceptance, and event context. A US-equity-tape variant requires its own proven data path.

**Conditional plan:** repetition alone is insufficient; require a separately defined price response and avoid interpreting a multi-leg or hedging transaction as certain directional intent.

**Abstain when:** quote alignment fails, the classified share is too low, session coverage is incomplete, corrections are unresolved, or the data cannot distinguish the claimed phenomenon.

**Comparison:** underlying price response alone, then unsigned activity, then the proposed sign/persistence information. Defer this recipe until it demonstrates value beyond cheaper native inputs.

### 11.7 Macro-shock dislocation and recovery

**User job:** connect a macro surprise to its cross-asset transmission and subsequent stabilization.

**Inputs:** point-in-time release/surprise data, native rates/FX/credit/sector responses, volatility and breadth, price acceptance around a clearly specified reference, and analogues retrieved with the correct historical availability.

**Conditional plan:** define the shock, transmission window, and recovery condition in advance. Separate same-session dislocation from a multi-session recovery thesis; they require different data and outcome rules.

**Abstain when:** release timing or revision history is uncertain, historical analogues are sparse or regime-incompatible, or a key transmission market is unavailable.

**Comparison:** simple shock-plus-price response, then cross-asset context and memory retrieval. Similar historical stories do not substitute for a prospective test.

### Recipe sequencing

Begin with recipes 11.1–11.3 because they can reuse broad native coverage and have clear baseline comparisons. Add 11.4, 11.5, and 11.7 only after their specific data and evaluation requirements are satisfied. Recipe 11.6 is conditional on flow quality and incremental usefulness. None requires copying the competitor's weights, tier names, model architecture, or sizing suggestions.

## 12. Product integration across Macro Dashboard, Terminal, and Mastermind

### Macro Dashboard: market context and investigation priorities

The dashboard should show the current regime and changes, breadth/sector participation, volatility and event context, then a concise set of observations or eligible plans. Each item needs its actual state, horizon, source freshness, and reason for appearing. Rank only where the current owner permits ranking; advisory radar remains an attention surface.

An evidence breakdown should make disagreements legible. For example, broad participation can improve while an individual stock remains below its trigger; favorable market context should not turn “waiting” into “active.” Clicking a plan should open the same ID/version in Terminal.

Coverage belongs beside the information it qualifies. A stale options snapshot should appear as stale options evidence, not as a platform-wide green health badge.

### Terminal: complete investigation without losing context

Extend existing symbol, chart, plan, options, earnings, watchlist, and alert surfaces. A useful detail view contains:

- The precise plan or observation and its current state.
- The original trigger, zone, horizon, optional targets, stop/invalidation, and allowed revisions.
- A chart overlay drawn from producer-owned levels, with data basis and timestamps.
- Supporting and opposing evidence grouped by dependency family.
- A timeline of issuance, triggers, alerts, amendments, and outcomes.
- Links to source observations and an explanation of each method.
- Related historical cases, including failures and unresolved observations, with similarity limitations.
- Actions through current watchlist and alert owners.

Preserve existing language/localization and responsive behavior. A descriptive analytical level, a proposed plan, and a personal portfolio action should remain distinguishable in copy and interaction.

Do not make users decode infrastructure terms. Show “options data through yesterday's close” or “direction estimated from trade and quote” with a deeper provenance view available.

### Briefs and recap: two views of the same records

The morning or pre-session brief should use the latest permitted context and a frozen list of referenced plans/observations. It should distinguish an existing active plan from a new candidate, state the event risks, and identify what would change the interpretation. Cadence must use the existing scheduling owner and the appropriate market calendar.

The intraday update should report meaningful transitions and explain why they matter. Threshold jitter must not create repeated identical alerts. Existing suppression, deduplication, user preferences, and delivery receipts should remain authoritative.

The after-session recap should include every issued item in its stated cohort: activated, untriggered, invalidated, expired, still active, missing-data, ambiguous, corrected, and resolved. It should compare the original claim with observed evidence rather than rewriting the thesis after the result. Longer-horizon items remain pending until their evaluation matures.

The strongest useful lesson is often a boundary: a recipe failed in a particular regime, a key source was unavailable, or an apparent success depends on an optimistic fill convention. The recap should record those facts before asking an AI to explain them.

### Mastermind reasoning and memory

The assistant can answer “why this setup,” “what changed,” “what conflicts,” and “what happened to similar cases” by retrieving existing record references. Explanations should distinguish observations from interpretations and reveal when no supported answer exists.

Learning should produce a typed research question or proposed change through the existing experiment and review process. A generated post-mortem must not alter production weights, promote a recipe, or repurpose a memory outcome that is explicitly training-ineligible.

### Reproducible AI research sessions

Adapt the useful date/symbol/field-selection idea through the existing research assistant. Freeze the selected snapshot and availability cutoff, selected fields and exclusions, prompt/template version, model/version, and generated answer. Link factual numeric claims to source fields. Deterministic owners calculate prices, scores, and outcomes; the language model explains them. Preserve contradictory evidence and failed hypotheses in later recap generation. This creates a reproducible research session rather than an untraceable chat about the latest chart.

## 13. Validation and acceptance design

### 13.1 Evaluate the actual claim

| Product object | Appropriate primary outcome | Common invalid substitution |
|---|---|---|
| Relative forecast | Specified return relative to the named benchmark over the defined horizon | Calling any positive absolute return a correct relative forecast |
| Directional forecast | Defined direction/threshold over a specific observation window | Mixing all horizons or using a favorable intraday extreme |
| Conditional plan | Trigger/activation, declared path rule, terminal state, and return under its measurement convention | Treating an untriggered plan as a winning trade |
| Legacy Prophet ledger | Its first-observable-daily-close ruler and original-entry basis | Calling its T2 rate eventual T2 attainment or its return executable P&L |
| Execution-aware challenger | Fill convention, spread, slippage, fees, gap behavior and path ordering | Reusing the original-entry result after a later trigger without disclosure |
| Market warning | Recall, lead time, false-alert burden, persistence and resolution | Requiring every warning to be a profitable short |
| Volatility/range scenario | Realized volatility/range and the stated conditional branch | Converting positive gamma into bullish directional probability |
| Research explanation | Source faithfulness, numerical accuracy, contradiction coverage, reproducibility | Eloquence or a selected successful anecdote |
| Workflow improvement | Completed investigation, meaningful alert, time to evidence, recap completeness | Counting newly visible cards as feature completion |

The current Prophet ruler should remain reproducible as a historical method. A better or different ruler is a versioned experiment, not a retrospective replacement that improves yesterday's scorecard.

### 13.2 Price-path and execution controls

For any target/stop evaluation, specify when the entry becomes knowable and executable, whether a limit or confirmation is assumed, and what happens at gaps. If both barriers occur within an OHLC bar and sequence is unknown, record ambiguity or use a predeclared conservative analysis convention. Do not choose the favorable ordering.

Record MFE and MAE against a stated activation and price basis. A time-to-target calculation starts from its declared clock, not whichever timestamp makes it shorter. Separate underlying performance from option performance; an underlying target does not determine an option's realized return without contract/price data.

Use market calendars and corporate-action policy consistently. Delisted symbols and changing membership must not disappear from historical eligibility. If the chosen universe is deliberately restricted to current large-cap names, state that boundary and do not claim a broader population result.

### 13.3 Selection and final evaluation

Use existing discovery and replay tools, with a clearly separated sequence:

1. **Data and identity gate:** correct available-at joins, corporate actions, calendars, revisions, missingness, and cohort membership.
2. **Simple baseline:** define what the current native system or a simpler price-only rule already achieves.
3. **Discovery:** explore candidate recipes/thresholds with logged trials and dependency groups.
4. **Freeze:** lock eligibility, features, thresholds, horizon, costs, abstention rules, and target definition.
5. **Final chronological evaluation:** use a period not consumed by candidate ranking, or an outer walk-forward process with explicitly separated fitting/selection/evaluation.
6. **Prospective shadow:** issue immutable observations/plans as they become available and account for all outcomes.
7. **Narrow acceptance:** approve only the tested use, universe, horizon, and authority; broader application is another claim.

Purge or otherwise handle training labels whose future windows overlap the evaluation boundary. Report dependence-aware uncertainty across time and instruments rather than assuming every same-day ticker is independent. Record the number of attempted variants. Existing holdout, trial-ledger, PBO and forward-evaluation owners are the correct places to implement these controls. [Mastermind holdout](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/loop/holdout.py) · [Forward evaluation](https://github.com/mastermindx-market-intelligence/Mastermind/blob/05a9eb52a54e29fb7bbd0d40813ed12623b176c7/portfolio/forward_evaluation.py) · [Macro confluence](https://github.com/mastermindx-market-intelligence/macro/blob/01c966b177ce9425030eac8a337352ee2842daed/engine/tech_confluence.py)

### 13.4 Probability calibration and abstention

Calibrate only against the exact outcome the displayed probability names. Fit calibration on data separated from model fitting and final evaluation. Assess reliability curves, proper scoring rules such as Brier/log loss where appropriate, and support by horizon/regime. A clipped score, a fitted curve without evaluation, or precise decimal arithmetic is insufficient evidence. [scikit-learn calibration documentation](https://scikit-learn.org/stable/modules/calibration.html)

A sparse cohort should show insufficient evidence. Preserve abstentions and their reasons; a system that only reports its easiest few cases should disclose that coverage. Compare quality and coverage together. Sample support should depend on uncertainty and the decision being made, not a universal small minimum count.

Do not multiply every available calibration adjustment together. Trace which target and evidence each uses, then evaluate the composed output. Several legitimate estimands may coexist, but their product need not have an interpretable probability meaning.

### 13.5 Product-path acceptance

For each released slice, verify one actual chain from admitted source through the authoritative plan/observation, API, chart/detail, alert or brief, outcome, and recap. Include stale input, missing component, duplicate delivery, correction, supersession, and unresolved outcome cases.

A green unit suite proves only its assertions. Static artifact presence proves only that an artifact exists. A complete acceptance record needs the deployed revision, real input provenance, user-visible output, and the connection to the original ID/version. Existing review and telemetry procedures should capture this proof.

## 14. Complete work program

This is a proposed implementation commission, not work already performed. The sequence favors the smallest coherent improvement over a broad replacement. Effort bands are relative: **S** is a bounded owner-level change; **M** crosses a few contracts/consumers; **L** requires multi-owner work or meaningful data accrual. They are not calendar estimates. Assign duration after the first trace and owner review.

### 14.1 Work packages

| ID / priority | Scope and owner | Dependencies | Acceptance / expected output | Effort |
|---|---|---|---|---|
| WP01 · P0 | Trace a real existing Prophet plan across bridge, source snapshot, management, ledger, Dashboard and Terminal | Current deployed access and source pins | A reproducible lineage and consumer trace; every break becomes a specific issue, not a presumed missing subsystem | M |
| WP02 · P0 | Verify and repair same-build closed-state projection in build_prophet if reproduced | WP01; current publisher owner | A plan closing in this build is closed in index, counts, instructions and recap; quarantine/correction behavior remains correct | S–M |
| WP03 · P0 | Reconcile entry-zone, scalar-trigger, clock and outcome semantics in Prophet bridge/publisher/Arena | WP01 | Written method contract and tests for pre-publication data, gaps, expiry, trigger timing and T1/T2 interpretation; no rewrite of historical geometry | M |
| WP04 · P0 | Verify conviction-to-management confidence handoff and score meanings | WP01; bridge/management owners | Establish intended input policy, reproduce any field mismatch, and correct only that policy; no new probability claim | S |
| WP05 · P0 | Audit data basis and existing cross-record references | WP01; current feed/catalog/plan/outcome owners | Required source/availability times, units, inference method, missingness and IDs reach the consumer; daily snapshots retain their intended grain | M |
| WP06 · P1 | Repair cross-batch sweep-like grouping in existing live_flow and retained state | Event sequencing/corrections from WP05 | Same event sequence produces the same finalized groups regardless of batch boundaries, under declared late-arrival, correction, retention and restart rules | S–M |
| WP07 · P1 | Reconcile legacy/current flow and profile consumers | WP05; Macro flow and Terminal chart owners | Session totals and field meanings reconcile; quote-rule, candle-shape, daily-bin and observed-tape quantities remain distinct | M |
| WP08 · P1 | Make final evaluation independent of confluence selection; preserve live/Arena parity | Stable recipe/method IDs; WP03 | Logged trials, frozen candidates, untouched final evaluation, parity tests for shared rules and named challenger differences | M, plus data |
| WP09 · P1 | Complete the existing plan detail, evidence/conflict view and revision/outcome links | WP01–05; Terminal and Dashboard owners | User moves from market context to the exact plan, original evidence, current state and outcome without ambiguous numbers | M |
| WP10 · P1 | Extend existing briefs/alerts/recap projections only where WP01 finds a missing path | WP03, WP05, WP09 | One existing delivery pipeline; meaningful change alerts; complete issued-cohort recap including pending, NO_ENTRY and ambiguous cases | M |
| WP11 · P1 | First original recipe cohort: pullback recovery, breadth expansion, deterioration warnings | WP03, WP05, WP08; legitimate origination owner | Frozen specs and baselines, prospective shadow records, separate warning/plan outcomes, no expansion of radar authority | M–L |
| WP12 · P2 | Targeted pattern/profile descriptors and chart/server parity | Semantic gap proof from WP07/11 | Add only non-duplicate VPA sequences or node descriptors; declare input resolution and confirmation timing | S–M per gap |
| WP13 · P2 | Reproducible AI explanation and memory retrieval | WP05, WP09; existing Brain/memory contracts | Frozen field selection and prompt/model references, numeric citations, failures/counterevidence, eligibility preserved | M |
| WP14 · P2 | Second recipe cohort and optional modeling | WP08, WP11 prospective evidence; event/flow rights and data | Earnings, gamma and macro-shock hypotheses evaluated; flow/model complexity admitted only for demonstrated incremental value | L, plus data |
| WP15 · Per release | Real-path proof, operational acceptance, rollback and monitoring | Dependencies of that slice | Deployed source-to-consumer-to-outcome evidence, honest degraded states, idempotent delivery and recoverable failure | M |

WP02 and WP04 are **candidate-defect verification tasks**, not permission to change scoring or lifecycle policy based on this report alone. If the focused test disproves a candidate, close it with evidence. WP03 may reveal legitimate distinct semantics rather than a defect; then the required change is clear labeling and comparison, not forcing all views to use one rule.

### 14.2 Delivery waves

**Wave A — establish the actual path and fix demonstrable inconsistencies.** WP01–05, with the bounded sweep repair prepared where sequencing is already established. Deliver a source/consumer trace, focused issues, and clarified outcome definitions. This wave can improve correctness without adding any indicator.

**Wave B — complete one coherent user workflow.** WP06–10. Reuse the current plan detail and publish a complete cohort recap through existing delivery owners. A first usable slice should involve a limited set of currently admitted instruments and the existing plan ruler, not all asset classes at once.

**Wave C — establish incremental analytical value.** WP11–13 under frozen evaluation rules. Add only the pattern descriptors needed by the selected hypotheses. Measure whether the new context helps beyond native baselines and whether users can complete the intended investigation.

**Wave D — expand selectively.** WP14 and subsequent narrow releases. New data feeds, intraday stock-tape features, additional forecast models, and broader universes require their own value case and acceptance evidence.

The first completion milestone is a trustworthy existing-plan journey, not a count of newly written engines. The second is a prospectively evaluated improvement over the incumbent baseline.

### 14.3 Work already underway: avoid parallel ownership

The inspected open-PR lists are a snapshot, not an exhaustive inventory or a statement that the work has merged. Recheck them when commissioning implementation.

| Area | Related work observed | Coordination rule |
|---|---|---|
| Portfolio/bot architecture | [Mastermind #1695](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1695), program carrier with ECON/RUNTIME/RESEARCH/PRODUCT domains | Route ledger/replay/learning changes through its existing ownership; do not create a competing overhaul |
| Signal publication/reasons | [Macro #10067](https://github.com/mastermindx-market-intelligence/macro/pull/10067), [#9957](https://github.com/mastermindx-market-intelligence/macro/pull/9957), marked held in inspected state | Respect the current gate; a competitor study does not activate held changes |
| Live-flow price inputs | [Macro #9808](https://github.com/mastermindx-market-intelligence/macro/pull/9808) | Coordinate data-basis repair before changing dependent consumers |
| Options exposure map | [Macro #9713](https://github.com/mastermindx-market-intelligence/macro/pull/9713), plan | Reuse the planned owner; do not infer a joint strike/expiry distribution from separate marginals |
| Option-expression history | [Macro #9682](https://github.com/mastermindx-market-intelligence/macro/pull/9682) | Preserve first-publication/history semantics and activation gates |
| Earnings continuation | [Macro #9613](https://github.com/mastermindx-market-intelligence/macro/pull/9613) | Use existing earnings/Terminal path; consensus/rights limits remain material |
| Brief provenance | [Macro #9642](https://github.com/mastermindx-market-intelligence/macro/pull/9642) and [Terminal #1033](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1033) | Extend existing source/language handling |
| News and shared briefs | [Terminal #1081](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1081) | Distinguish current news changes from its future brief-endpoint plan |
| Native charts and chart AI | [Terminal #1064](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1064), [#1048](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1048) | Coordinate existing rollout and layer ownership |
| Watchlists and large trades | [Terminal #1034](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1034), [#1031](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1031) | Add references through incumbent import/export and persistence contracts |

### 14.4 Data and operating economics

No credible commercial budget can be inferred from SignalsEngine's subscription price or an individual feed plan. The incremental cost depends on actual entitlements, redistribution and derived-data terms, symbols, asset classes, historical depth, update cadence, tick/quote retention, corrections, and concurrent consumer demand.

Use a staged business case:

| Investment | First question | Proceed only when |
|---|---|---|
| Existing licensed OHLC/option/macro data | Can current coverage support the first recipes and journey? | Provenance and timing pass acceptance |
| Additional history | Which evaluation period or regime is currently impossible? | It changes a named validation decision |
| Equity trades/NBBO | Which user job requires exact trade/quote classification? | Existing feed audit shows a real gap and a prospective pilot shows value |
| More options depth/frequency | Which expiry/contract behavior is otherwise unobservable? | Rights, coverage, latency and cost support the intended consumer |
| Larger storage/replay | Which audit/correction/replay obligation needs raw retention? | Retention is scoped and recoverable through current owners |
| More language-model calls | Does the existing assistant fail a reproducible explanation job? | Deterministic calculations remain outside narrative generation and cached source snapshots can be reused |
| New ML architecture | Does it outperform the native/simple baseline after selection controls? | Incremental results survive independent and prospective evaluation |

Avoid pricing a commercial feed from public retail tiers. Massive's own redistribution guidance requires appropriate business arrangements. [Commercial-data guidance](https://massive.com/knowledge-base/article/how-can-i-redistribute-massives-market-data)

### 14.5 Measures of success

**Correctness:** no silent source-basis changes, identity loss, retrospective plan edits, duplicate outcomes, or ambiguity hidden as certainty.

**Product utility:** users can inspect a plan, understand its state and conflicts, save or watch it through current controls, and find its later outcome. Measure completion and time to supporting evidence before optimizing the number of alerts.

**Analytical utility:** a recipe's incremental value is measured against its native baseline for its exact task. Report coverage, abstention, uncertainty, regimes, costs where applicable, and complete cohorts.

**Operating reliability:** source age, failed calculations, missing artifacts, stale consumers, duplicated delivery and correction lag are visible through existing telemetry.

**Learning quality:** post-mortems retain failed and unresolved cases, produce reproducible research questions, and obey existing eligibility/promotion boundaries.

## 15. What to adopt, what to defer, and what not to copy

**Adopt the product ideas:** a concise signal explorer, legible symbol deep dive, visible component disagreement, explicit conditional levels, immutable revisions, complete recaps, and context-linked education. Much of the necessary native implementation already exists.

**Prioritize native strengths:** macro/cross-asset context, breadth, sector behavior, earnings evidence, ownership/provenance discipline, point-in-time memory, and prospective evaluation. Their value comes from explaining when a local setup is relevant, not from adding more votes to a confidence badge.

**Defer until demonstrated:** new LSTM infrastructure, additional feed purchases, stock-tape absorption/iceberg inference, many simultaneous recipes, and broad all-market expansion. Each needs a defined user job and incremental evidence.

**Do not copy as facts:** the advertised win rate, tier thresholds, “institutional” labels, gross-gamma interpretations, max-pain forecasts, star-based position sizing, or a visually moving demo feed. Do not copy proprietary code, assets, or article prose.

The recommended end product is the existing Mastermind system made more coherent: original observations and hypotheses, explicit conditions, broad native context, inspectable evidence, correct state transitions, and honest outcomes. The work program begins with verifying and repairing the incumbent path, then adds only what improves that product.

## 16. Research limits and completion record

The public portion covers all 26 linked educational articles, the public business/legal surface, a complete list of page references recovered from the main bundle, and selected substantive consumer and administrative client modules. It is not a private-backend audit. No account creation, administrative action, private endpoint retrieval, credential acquisition, or contact with the company was performed.

The internal portion is a pinned source census across three repositories, supplemented by targeted principal reads and independent critical review. Broad searches in the large/blobless repositories had limitations; negative findings were narrowed accordingly. No percentage of product completeness is asserted. Test files and repository evidence were not represented as freshly executed tests or current production proof.

No tracked source implementation, merge, deployment, or production configuration change was made for this research. One retrieval worker disclosed a local repository gc.auto setting change; that had no tracked-source or deployment effect. The work delivered here is the census, assessment and proposed implementation plan.

The original three bounded census returns were consumed and reviewed. Their unsupported broad absence claims were rejected where targeted source reads found existing functionality. The final recommendations in this document supersede those raw search-based conclusions.

### Most important unresolved verification questions

1. Does the deployed Prophet path match the inspected revisions, and do all consumers show the same current plan state?
2. Can the same-build closure and confidence-handoff candidates be reproduced?
3. Which entry-zone versus scalar-trigger semantics are intended for the user-facing plan?
4. Which exact outcome ruler should each recap and performance label name?
5. Which existing licensed feeds actually supply the required intraday coverage at runtime?
6. Do chart/server definitions match when used for the same analytical claim?
7. Is the proposed recipe's value incremental after independent and prospective evaluation?
8. Which existing brief/review surfaces already complete the desired daily workflow, and where does a real user-path trace fail?

These questions define the next implementation commission; they do not prevent completing this research assessment.

## 17. Public coverage appendix

### 17.1 Educational coverage

All 26 linked Signalpedia articles were inspected: market sentiment (2), technical analysis (6), options analytics (5), order flow (4), volume profile (3), VPA (3), and prediction system (3). Their direct URLs are cited in Section 4. Educational descriptions are not evidence that identical formulas run in production.

### 17.2 Page/component references recovered from the public bundle

The following is a factual index of all 144 page/component references recovered from the inspected main asset. These are source component paths and their public build assets, not a list of tested URL routes. Administrative, archived, alternate, and prototype components are included. A reference does not establish authorization, functionality, deployment currency, or data availability. The substantive modules inspected are discussed in Sections 3–5. [Source bundle](https://signalsengine.com/build/assets/app-CDapMUlI.js)

#### Top-level pages

| Component reference | Referenced asset |
|---|---|
| AIEngine.tsx | [AIEngine-Uq7GvHZQ.js](https://signalsengine.com/build/assets/AIEngine-Uq7GvHZQ.js) |
| Affiliates.tsx | [Affiliates-DwhlYPYY.js](https://signalsengine.com/build/assets/Affiliates-DwhlYPYY.js) |
| Alerts.tsx | [Alerts-C6jp6tkE.js](https://signalsengine.com/build/assets/Alerts-C6jp6tkE.js) |
| Charting.tsx | [Charting-x9cMuOBc.js](https://signalsengine.com/build/assets/Charting-x9cMuOBc.js) |
| Charts.tsx | [Charts-DG5-cMv2.js](https://signalsengine.com/build/assets/Charts-DG5-cMv2.js) |
| ComponentsDemo.tsx | [ComponentsDemo-D8k57hY-.js](https://signalsengine.com/build/assets/ComponentsDemo-D8k57hY-.js) |
| DailyBrief.tsx | [DailyBrief-MMXEgeTU.js](https://signalsengine.com/build/assets/DailyBrief-MMXEgeTU.js) |
| DailyResults.tsx | [DailyResults-CAC8sFre.js](https://signalsengine.com/build/assets/DailyResults-CAC8sFre.js) |
| Disclaimer.tsx | [Disclaimer-BQOT3Ku1.js](https://signalsengine.com/build/assets/Disclaimer-BQOT3Ku1.js) |
| Engine.tsx | [Engine-DI7Rby5i.js](https://signalsengine.com/build/assets/Engine-DI7Rby5i.js) |
| ExpirationPredictions.tsx | [ExpirationPredictions-BscKnkgw.js](https://signalsengine.com/build/assets/ExpirationPredictions-BscKnkgw.js) |
| Live.tsx | [Live-D5PoFJ1g.js](https://signalsengine.com/build/assets/Live-D5PoFJ1g.js) |
| MarketFlushes.tsx | [MarketFlushes-CyRFtS-q.js](https://signalsengine.com/build/assets/MarketFlushes-CyRFtS-q.js) |
| MassiveTest.tsx | [MassiveTest-BcX7ktRL.js](https://signalsengine.com/build/assets/MassiveTest-BcX7ktRL.js) |
| Options.tsx | [Options-5HH5tZ5O.js](https://signalsengine.com/build/assets/Options-5HH5tZ5O.js) |
| PipelineFlow.tsx | [PipelineFlow-Cq0sncBE.js](https://signalsengine.com/build/assets/PipelineFlow-Cq0sncBE.js) |
| Privacy.tsx | [Privacy-CR3B6O7l.js](https://signalsengine.com/build/assets/Privacy-CR3B6O7l.js) |
| Realtime.tsx | [Realtime-BTfLD7jr.js](https://signalsengine.com/build/assets/Realtime-BTfLD7jr.js) |
| Results.tsx | [Results-CEvQcbr2.js](https://signalsengine.com/build/assets/Results-CEvQcbr2.js) |
| Screener.tsx | [Screener-DDeqpR0A.js](https://signalsengine.com/build/assets/Screener-DDeqpR0A.js) |
| SignalAnalysis.tsx | [SignalAnalysis-ed3QqL7p.js](https://signalsengine.com/build/assets/SignalAnalysis-ed3QqL7p.js) |
| SignalResults.tsx | [SignalResults-DSGIFRok.js](https://signalsengine.com/build/assets/SignalResults-DSGIFRok.js) |
| Signalpedia.tsx | [Signalpedia-CB7cuJ2z.js](https://signalsengine.com/build/assets/Signalpedia-CB7cuJ2z.js) |
| Signals.tsx | [Signals-Yr___x1O.js](https://signalsengine.com/build/assets/Signals-Yr___x1O.js) |
| Streamer.tsx | [Streamer-CM9Pa1tx.js](https://signalsengine.com/build/assets/Streamer-CM9Pa1tx.js) |
| Symbol.tsx | [Symbol-CG9IfnXW.js](https://signalsengine.com/build/assets/Symbol-CG9IfnXW.js) |
| SymbolDeepDive.tsx | [SymbolDeepDive-Bc4771ZM.js](https://signalsengine.com/build/assets/SymbolDeepDive-Bc4771ZM.js) |
| SymbolPage.tsx | [SymbolPage-DgsPdo4r.js](https://signalsengine.com/build/assets/SymbolPage-DgsPdo4r.js) |
| Terms.tsx | [Terms-C6DbtXaA.js](https://signalsengine.com/build/assets/Terms-C6DbtXaA.js) |
| TradingDashboard.tsx | [TradingDashboard-93LO_Iz2.js](https://signalsengine.com/build/assets/TradingDashboard-93LO_Iz2.js) |
| V5Dashboard.tsx | [V5Dashboard-PQ5EIeRw.js](https://signalsengine.com/build/assets/V5Dashboard-PQ5EIeRw.js) |
| WarRoom.tsx | [WarRoom-CeGVLISM.js](https://signalsengine.com/build/assets/WarRoom-CeGVLISM.js) |
| Watchlists.tsx | [Watchlists-D44SEpvP.js](https://signalsengine.com/build/assets/Watchlists-D44SEpvP.js) |
| index.tsx | [index-BAlgNqzG.js](https://signalsengine.com/build/assets/index-BAlgNqzG.js) |

#### Admin

| Component reference | Referenced asset |
|---|---|
| Admin/Dashboard.tsx | [Dashboard-CWv9VEkC.js](https://signalsengine.com/build/assets/Dashboard-CWv9VEkC.js) |
| Admin/DataCollection/CollectFinal.tsx | [CollectFinal-6bovGf7y.js](https://signalsengine.com/build/assets/CollectFinal-6bovGf7y.js) |
| Admin/DataDump.tsx | [DataDump-Cq7JPWOR.js](https://signalsengine.com/build/assets/DataDump-Cq7JPWOR.js) |
| Admin/DataViewer/Index.tsx | [Index-BHnmZZqM.js](https://signalsengine.com/build/assets/Index-BHnmZZqM.js) |
| Admin/Debug/ApiTest.tsx | [ApiTest-B5NE9pmu.js](https://signalsengine.com/build/assets/ApiTest-B5NE9pmu.js) |
| Admin/Debug/Step3Test.tsx | [Step3Test-C6M7XIHF.js](https://signalsengine.com/build/assets/Step3Test-C6M7XIHF.js) |
| Admin/HistoricalData/Index.tsx | [Index-xUk53uOn.js](https://signalsengine.com/build/assets/Index-xUk53uOn.js) |
| Admin/LevelsData/Index.tsx | [Index-BUSYcETF.js](https://signalsengine.com/build/assets/Index-BUSYcETF.js) |
| Admin/LookbackAnalysis.tsx | [LookbackAnalysis-_zVZ_n4j.js](https://signalsengine.com/build/assets/LookbackAnalysis-_zVZ_n4j.js) |
| Admin/MarketAnalysis/Index.tsx | [Index-BzzxTAay.js](https://signalsengine.com/build/assets/Index-BzzxTAay.js) |
| Admin/MarketDataUpload/Index.tsx | [Index-_ClErbvs.js](https://signalsengine.com/build/assets/Index-_ClErbvs.js) |
| Admin/OptionsSnapshots/Index.tsx | [Index-vaxpsO42.js](https://signalsengine.com/build/assets/Index-vaxpsO42.js) |
| Admin/ParquetViewer/Index.tsx | [Index-ByUPE_vF.js](https://signalsengine.com/build/assets/Index-ByUPE_vF.js) |
| Admin/PredictionAnalytics/Index.tsx | [Index-CtaDKMYh.js](https://signalsengine.com/build/assets/Index-CtaDKMYh.js) |
| Admin/PredictionTester/Index.tsx | [Index-BZyra2W9.js](https://signalsengine.com/build/assets/Index-BZyra2W9.js) |
| Admin/Roles/Index.tsx | [Index-BPI3no_d.js](https://signalsengine.com/build/assets/Index-BPI3no_d.js) |
| Admin/ScoringAnalysis/Index.tsx | [Index-ClQ_pQJb.js](https://signalsengine.com/build/assets/Index-ClQ_pQJb.js) |
| Admin/SignalSystemAnalysis/Index.tsx | [Index-BhkqLrKt.js](https://signalsengine.com/build/assets/Index-BhkqLrKt.js) |
| Admin/SnapshotValidation.tsx | [SnapshotValidation-CIxM-hwF.js](https://signalsengine.com/build/assets/SnapshotValidation-CIxM-hwF.js) |
| Admin/StreamingTest/Index.tsx | [Index-b07dGHo9.js](https://signalsengine.com/build/assets/Index-b07dGHo9.js) |
| Admin/Users/Create.tsx | [Create-BhfUXiYJ.js](https://signalsengine.com/build/assets/Create-BhfUXiYJ.js) |
| Admin/Users/Edit.tsx | [Edit-CGbkLJx3.js](https://signalsengine.com/build/assets/Edit-CGbkLJx3.js) |
| Admin/Users/Index.tsx | [Index-OEkELG1V.js](https://signalsengine.com/build/assets/Index-OEkELG1V.js) |
| Admin/Users/Show.tsx | [Show-BRrNMGZs.js](https://signalsengine.com/build/assets/Show-BRrNMGZs.js) |

#### Billing

| Component reference | Referenced asset |
|---|---|
| Billing/Index.tsx | [Index-3GcfupYY.js](https://signalsengine.com/build/assets/Index-3GcfupYY.js) |
| Billing/Success.tsx | [Success-B0FqN4iK.js](https://signalsengine.com/build/assets/Success-B0FqN4iK.js) |

#### Briefs

| Component reference | Referenced asset |
|---|---|
| Briefs/sev2_Briefs.tsx | [sev2_Briefs-DAzDJhka.js](https://signalsengine.com/build/assets/sev2_Briefs-DAzDJhka.js) |

#### Dashboard

| Component reference | Referenced asset |
|---|---|
| Dashboard/SymbolDeepDive.tsx | [SymbolDeepDive-BcbmyJaG.js](https://signalsengine.com/build/assets/SymbolDeepDive-BcbmyJaG.js) |
| Dashboard/V5Dashboard-old.tsx | [V5Dashboard-old-CHb24RCV.js](https://signalsengine.com/build/assets/V5Dashboard-old-CHb24RCV.js) |
| Dashboard/V5Dashboard.tsx | [V5Dashboard-BLYNSz3F.js](https://signalsengine.com/build/assets/V5Dashboard-BLYNSz3F.js) |
| Dashboard/_archived/Components/ActiveSignalsGrid.tsx | [ActiveSignalsGrid-Bi00bfqm.js](https://signalsengine.com/build/assets/ActiveSignalsGrid-Bi00bfqm.js) |
| Dashboard/_archived/Components/GammaExposureChart.tsx | [GammaExposureChart-CR3_DdrV.js](https://signalsengine.com/build/assets/GammaExposureChart-CR3_DdrV.js) |
| Dashboard/_archived/Components/GexStrikeHeatmap.tsx | [GexStrikeHeatmap-Cw4LzH_o.js](https://signalsengine.com/build/assets/GexStrikeHeatmap-Cw4LzH_o.js) |
| Dashboard/_archived/Components/LiveOrderFlowTracker.tsx | [LiveOrderFlowTracker-BfwcnBYR.js](https://signalsengine.com/build/assets/LiveOrderFlowTracker-BfwcnBYR.js) |
| Dashboard/_archived/Components/MarketBriefSummary.tsx | [MarketBriefSummary-CvU4E088.js](https://signalsengine.com/build/assets/MarketBriefSummary-CvU4E088.js) |
| Dashboard/_archived/Components/MarketStatusCards.tsx | [MarketStatusCards-Bege07Pm.js](https://signalsengine.com/build/assets/MarketStatusCards-Bege07Pm.js) |
| Dashboard/_archived/Components/OptionsFlowCard.tsx | [OptionsFlowCard-B5BNBJaU.js](https://signalsengine.com/build/assets/OptionsFlowCard-B5BNBJaU.js) |
| Dashboard/_archived/Components/SignalConfidenceBreakdown.tsx | [SignalConfidenceBreakdown-B9HvLK39.js](https://signalsengine.com/build/assets/SignalConfidenceBreakdown-B9HvLK39.js) |
| Dashboard/_archived/Components/SymbolCard.tsx | [SymbolCard-DvOf_VwK.js](https://signalsengine.com/build/assets/SymbolCard-DvOf_VwK.js) |
| Dashboard/_archived/Components/TechnicalIndicatorsCard.tsx | [TechnicalIndicatorsCard-B9vEsuB0.js](https://signalsengine.com/build/assets/TechnicalIndicatorsCard-B9vEsuB0.js) |
| Dashboard/_archived/Components/VolatilityMetricsCard.tsx | [VolatilityMetricsCard-Bh3H-XsF.js](https://signalsengine.com/build/assets/VolatilityMetricsCard-Bh3H-XsF.js) |
| Dashboard/_archived/Components/VolumeProfileChart.tsx | [VolumeProfileChart-CGRBHnKT.js](https://signalsengine.com/build/assets/VolumeProfileChart-CGRBHnKT.js) |
| Dashboard/_archived/Components/WatchlistSection.tsx | [WatchlistSection-d-PyLYeE.js](https://signalsengine.com/build/assets/WatchlistSection-d-PyLYeE.js) |
| Dashboard/_archived/MarketOverview.tsx | [MarketOverview-BSuP9dhx.js](https://signalsengine.com/build/assets/MarketOverview-BSuP9dhx.js) |
| Dashboard/_archived/SymbolDeepDive.tsx | [SymbolDeepDive-DSgBDhIO.js](https://signalsengine.com/build/assets/SymbolDeepDive-DSgBDhIO.js) |
| Dashboard/_archived/TradingDashboard.tsx | [TradingDashboard-B5PnyoHS.js](https://signalsengine.com/build/assets/TradingDashboard-B5PnyoHS.js) |
| Dashboard/_archived/TradingSignalsDashboard.tsx | [TradingSignalsDashboard-CM4W3k0b.js](https://signalsengine.com/build/assets/TradingSignalsDashboard-CM4W3k0b.js) |
| Dashboard/_archived/UltraTradingDashboard.tsx | [UltraTradingDashboard-C8htN0KD.js](https://signalsengine.com/build/assets/UltraTradingDashboard-C8htN0KD.js) |
| Dashboard/_archived/UserDashboard.tsx | [UserDashboard-CAlSon3D.js](https://signalsengine.com/build/assets/UserDashboard-CAlSon3D.js) |
| Dashboard/_archived/UserDashboardVisual.tsx | [UserDashboardVisual-C1VsSI73.js](https://signalsengine.com/build/assets/UserDashboardVisual-C1VsSI73.js) |
| Dashboard/_archived/V3Dashboard.tsx | [V3Dashboard-B7hu-ms2.js](https://signalsengine.com/build/assets/V3Dashboard-B7hu-ms2.js) |
| Dashboard/_archived/sev2_Dashboard.tsx | [sev2_Dashboard-Dx7mIqW8.js](https://signalsengine.com/build/assets/sev2_Dashboard-Dx7mIqW8.js) |
| Dashboard/_archived/sev2_SystemComparison.tsx | [sev2_SystemComparison-DqsXab8G.js](https://signalsengine.com/build/assets/sev2_SystemComparison-DqsXab8G.js) |

#### Demo

| Component reference | Referenced asset |
|---|---|
| Demo/Index.tsx | [Index-DwOrEwwq.js](https://signalsengine.com/build/assets/Index-DwOrEwwq.js) |

#### Live

| Component reference | Referenced asset |
|---|---|
| Live/Index.tsx | [Index-cldb10Os.js](https://signalsengine.com/build/assets/Index-cldb10Os.js) |

#### Signalpedia

| Component reference | Referenced asset |
|---|---|
| Signalpedia/components.tsx | [components-BL-zHM6T.js](https://signalsengine.com/build/assets/components-BL-zHM6T.js) |
| Signalpedia/content/AccumulationContent.tsx | [AccumulationContent-M7Q2NnSi.js](https://signalsengine.com/build/assets/AccumulationContent-M7Q2NnSi.js) |
| Signalpedia/content/AtrContent.tsx | [AtrContent-DjDXTZFK.js](https://signalsengine.com/build/assets/AtrContent-DjDXTZFK.js) |
| Signalpedia/content/BollingerContent.tsx | [BollingerContent-Snp-2VCN.js](https://signalsengine.com/build/assets/BollingerContent-Snp-2VCN.js) |
| Signalpedia/content/ContinuationContent.tsx | [ContinuationContent-Bk-LIjXz.js](https://signalsengine.com/build/assets/ContinuationContent-Bk-LIjXz.js) |
| Signalpedia/content/ConvictionLevelsContent.tsx | [ConvictionLevelsContent-DZPzPRSI.js](https://signalsengine.com/build/assets/ConvictionLevelsContent-DZPzPRSI.js) |
| Signalpedia/content/CumulativeDeltaContent.tsx | [CumulativeDeltaContent-DqXzDR7y.js](https://signalsengine.com/build/assets/CumulativeDeltaContent-DqXzDR7y.js) |
| Signalpedia/content/DarkPoolsContent.tsx | [DarkPoolsContent-C0foa1M0.js](https://signalsengine.com/build/assets/DarkPoolsContent-C0foa1M0.js) |
| Signalpedia/content/DistributionContent.tsx | [DistributionContent-B14C09jS.js](https://signalsengine.com/build/assets/DistributionContent-B14C09jS.js) |
| Signalpedia/content/GexContent.tsx | [GexContent-DDvjoYUY.js](https://signalsengine.com/build/assets/GexContent-DDvjoYUY.js) |
| Signalpedia/content/HvnLvnContent.tsx | [HvnLvnContent-4qXB8byT.js](https://signalsengine.com/build/assets/HvnLvnContent-4qXB8byT.js) |
| Signalpedia/content/IchimokuContent.tsx | [IchimokuContent-DoL0bPX3.js](https://signalsengine.com/build/assets/IchimokuContent-DoL0bPX3.js) |
| Signalpedia/content/InstitutionalFlowContent.tsx | [InstitutionalFlowContent-DMwhWdfe.js](https://signalsengine.com/build/assets/InstitutionalFlowContent-DMwhWdfe.js) |
| Signalpedia/content/IvSkewContent.tsx | [IvSkewContent-BIqe1KIc.js](https://signalsengine.com/build/assets/IvSkewContent-BIqe1KIc.js) |
| Signalpedia/content/MaxPainContent.tsx | [MaxPainContent-Bp9PPR2b.js](https://signalsengine.com/build/assets/MaxPainContent-Bp9PPR2b.js) |
| Signalpedia/content/MovingAveragesContent.tsx | [MovingAveragesContent-DNH5dghw.js](https://signalsengine.com/build/assets/MovingAveragesContent-DNH5dghw.js) |
| Signalpedia/content/OhlcContent.tsx | [OhlcContent-m70dEX8o.js](https://signalsengine.com/build/assets/OhlcContent-m70dEX8o.js) |
| Signalpedia/content/OptionsPcrContent.tsx | [OptionsPcrContent-BhaAO81i.js](https://signalsengine.com/build/assets/OptionsPcrContent-BhaAO81i.js) |
| Signalpedia/content/OscillatorsContent.tsx | [OscillatorsContent-BIi0ogRo.js](https://signalsengine.com/build/assets/OscillatorsContent-BIi0ogRo.js) |
| Signalpedia/content/PocContent.tsx | [PocContent-IXr1BgdT.js](https://signalsengine.com/build/assets/PocContent-IXr1BgdT.js) |
| Signalpedia/content/PutCallContent.tsx | [PutCallContent-DEgPDB__.js](https://signalsengine.com/build/assets/PutCallContent-DEgPDB__.js) |
| Signalpedia/content/SessionAnalysisContent.tsx | [SessionAnalysisContent-7CRijE89.js](https://signalsengine.com/build/assets/SessionAnalysisContent-7CRijE89.js) |
| Signalpedia/content/TargetStopContent.tsx | [TargetStopContent-C44G0_Wn.js](https://signalsengine.com/build/assets/TargetStopContent-C44G0_Wn.js) |
| Signalpedia/content/UnifiedScoringContent.tsx | [UnifiedScoringContent-waZe6M9l.js](https://signalsengine.com/build/assets/UnifiedScoringContent-waZe6M9l.js) |
| Signalpedia/content/UnusualActivityContent.tsx | [UnusualActivityContent-D0EeCQro.js](https://signalsengine.com/build/assets/UnusualActivityContent-D0EeCQro.js) |
| Signalpedia/content/ValueAreaContent.tsx | [ValueAreaContent-C77NNZvg.js](https://signalsengine.com/build/assets/ValueAreaContent-C77NNZvg.js) |
| Signalpedia/content/VixContent.tsx | [VixContent-B9V_ID_C.js](https://signalsengine.com/build/assets/VixContent-B9V_ID_C.js) |

#### Symbol

| Component reference | Referenced asset |
|---|---|
| Symbol/Components/AIAnalysis.tsx | [AIAnalysis-BD5b3Ds0.js](https://signalsengine.com/build/assets/AIAnalysis-BD5b3Ds0.js) |
| Symbol/Components/MACDChart.tsx | [MACDChart-Btj8XGaM.js](https://signalsengine.com/build/assets/MACDChart-Btj8XGaM.js) |
| Symbol/Components/OptionsMetrics.tsx | [OptionsMetrics-uUeUxnXd.js](https://signalsengine.com/build/assets/OptionsMetrics-uUeUxnXd.js) |
| Symbol/Components/OrderFlowMetrics.tsx | [OrderFlowMetrics-Qn323FMO.js](https://signalsengine.com/build/assets/OrderFlowMetrics-Qn323FMO.js) |
| Symbol/Components/PredictionsList.tsx | [PredictionsList-Ka1wrxbH.js](https://signalsengine.com/build/assets/PredictionsList-Ka1wrxbH.js) |
| Symbol/Components/PriceChart.tsx | [PriceChart-BqInvkl4.js](https://signalsengine.com/build/assets/PriceChart-BqInvkl4.js) |
| Symbol/Components/RSIChart.tsx | [RSIChart-FDGpqooy.js](https://signalsengine.com/build/assets/RSIChart-FDGpqooy.js) |
| Symbol/Components/SymbolHeader.tsx | [SymbolHeader-CtZsfbLZ.js](https://signalsengine.com/build/assets/SymbolHeader-CtZsfbLZ.js) |
| Symbol/Components/VolumeProfileMetrics.tsx | [VolumeProfileMetrics-BI7DWbHo.js](https://signalsengine.com/build/assets/VolumeProfileMetrics-BI7DWbHo.js) |
| Symbol/Index.tsx | [Index-Bwv2KoNl.js](https://signalsengine.com/build/assets/Index-Bwv2KoNl.js) |
| Symbol/SymbolDeepDive.tsx | [SymbolDeepDive-CJAxvsHE.js](https://signalsengine.com/build/assets/SymbolDeepDive-CJAxvsHE.js) |
| Symbol/V5SymbolDeepDive.tsx | [V5SymbolDeepDive-C_rPXZeK.js](https://signalsengine.com/build/assets/V5SymbolDeepDive-C_rPXZeK.js) |

#### TradingDashboard

| Component reference | Referenced asset |
|---|---|
| TradingDashboard/Analytics.tsx | [Analytics-DjTY7sqH.js](https://signalsengine.com/build/assets/Analytics-DjTY7sqH.js) |
| TradingDashboard/Historical.tsx | [Historical-cc8pl1Fn.js](https://signalsengine.com/build/assets/Historical-cc8pl1Fn.js) |
| TradingDashboard/Signals.tsx | [Signals-CPyIk_da.js](https://signalsengine.com/build/assets/Signals-CPyIk_da.js) |

#### TradingSignals

| Component reference | Referenced asset |
|---|---|
| TradingSignals/Index.tsx | [Index-uXeJQRFV.js](https://signalsengine.com/build/assets/Index-uXeJQRFV.js) |

#### auth

| Component reference | Referenced asset |
|---|---|
| auth/confirm-password.tsx | [confirm-password-CqnjkyOU.js](https://signalsengine.com/build/assets/confirm-password-CqnjkyOU.js) |
| auth/forgot-password.tsx | [forgot-password-DpO9d_xi.js](https://signalsengine.com/build/assets/forgot-password-DpO9d_xi.js) |
| auth/login.tsx | [login-D5-d3xLh.js](https://signalsengine.com/build/assets/login-D5-d3xLh.js) |
| auth/register.tsx | [register-C5yFENvA.js](https://signalsengine.com/build/assets/register-C5yFENvA.js) |
| auth/reset-password.tsx | [reset-password-DKnqMwmL.js](https://signalsengine.com/build/assets/reset-password-DKnqMwmL.js) |
| auth/two-factor-challenge.tsx | [two-factor-challenge-4PxocWDc.js](https://signalsengine.com/build/assets/two-factor-challenge-4PxocWDc.js) |
| auth/verify-email.tsx | [verify-email-CgvzByZw.js](https://signalsengine.com/build/assets/verify-email-CgvzByZw.js) |

#### settings

| Component reference | Referenced asset |
|---|---|
| settings/appearance.tsx | [appearance-QbO6reeA.js](https://signalsengine.com/build/assets/appearance-QbO6reeA.js) |
| settings/password.tsx | [password-D0Q8D890.js](https://signalsengine.com/build/assets/password-D0Q8D890.js) |
| settings/profile.tsx | [profile-DFpGFi8R.js](https://signalsengine.com/build/assets/profile-DFpGFi8R.js) |
| settings/sessions.tsx | [sessions-BM-ZrCkV.js](https://signalsengine.com/build/assets/sessions-BM-ZrCkV.js) |
| settings/two-factor.tsx | [two-factor-CnEClDAI.js](https://signalsengine.com/build/assets/two-factor-CnEClDAI.js) |

### 17.3 Source interpretation key

Public SignalsEngine links establish exposed claims, definitions, or client code. FINRA/SEC/Cboe/Massive/dxFeed links support market-data interpretation and vendor capability, not SignalsEngine's entitlement or operations. Commit-pinned GitHub links establish internal source at the revisions listed in Section 1. Open-PR links identify adjacent work at research time and must be rechecked before implementation.

The evidence supports an original integration program. It does not reproduce a private backend, validate a competitor's investment performance, or establish production acceptance for every native source implementation.




