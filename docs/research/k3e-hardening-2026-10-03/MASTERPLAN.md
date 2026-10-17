# K3E Priced-Expectations Gap Engine — end-to-end implementation masterplan

> **For agentic workers:** use the installed `superpowers:executing-plans` or `superpowers:subagent-driven-development` workflow as appropriate to the actual harness. Current Mastermind source custody, admission, review and authority laws prevail. This packet is a proposed build specification, not a runtime grant or permission to inspect held outcomes.

**Goal:** let an investor or machine consumer inspect, at an explicit cutoff, what observable forecasts said, which operating scenarios are consistent with valuation under stated assumptions, what qualified fundamental evidence supports, what derivatives price, and where those objects disagree—without pretending they are one identifiable market belief or prematurely granting trading authority.

**Architecture:** compose typed, point-in-time derived objects over current owner-native sources. Keep observed expectations, valuation-consistent scenarios, physical forecasts, risk-neutral derivative distributions, observed response and positioning context separate. Reuse the existing identity, financial, event, residual, evaluation, publication and consumer owners.

**Tech stack:** owner-native Python source/engine and evaluation components; existing Terminal frontend/server stack and existing Macro presentation components. Resolve exact libraries, versions and route insertion points at execution pickup. Do not introduce a new service, database or frontend platform for convenience.

**Spec and evidence:** [audit and census](AUDIT_AND_CENSUS.md), [source ledger](EVIDENCE_LEDGER.md), the immutable Macro K3E-0/SRC-A1/EVAL-0 contracts, and the current #8312 acceptance carrier. The original completed research report was not available; this plan must not be described as its unconditional certification.

**Status:** proposed architecture and sequencing, 2026-10-03. Product implementation, predictive validation and production promotion remain incomplete. Canonical K3E ownership stays in Macro / `WS:ALPHA-INTELLIGENCE-INTEGRATION`; this Mastermind packet is a cross-repository delivery artifact, not a new truth owner.

## Global constraints

- `K3E` means Expectation ↔ Market Dynamics; `K3-E` remains Opportunity Evidence Vector.
- No duplicate truth store, analyst-history store, identity plane, event system, residual engine, ranker, lifecycle, evaluation registry, notification queue, memory plane or publication authority.
- SRC-A1 raw observations and attempts remain in their existing owner; do not rewrite historical defects or accelerate collection to manufacture natural proof.
- No universal K3E scalar, hidden blend, implicit buy/sell label, or unvalidated Prophet ranking, admission, rejection, sizing or lifecycle influence.
- Preserve the existing EVAL-0 registration, activation and holdout. New targets require explicit versioning and consolidated trial accounting before outcome access.
- Rights, source clock, basis, identity, freshness and coverage failures remain visible. Missing is not neutral; `UNESTIMABLE` is a valid result.
- No procurement, new provider subscription, production configuration change or live-capital authority is supplied by this document.
- Existing #8312 and #8064 writers retain custody until lawful reconciliation. Do not reuse their branches or silently supersede their work.

## Review focus

The highest-risk inputs are future corrections appended after an earlier cutoff; fiscal rollover under an unchanged relative-horizon label; sparse or absent metadata concealed behind populated values; underidentified inverse valuation presented as a point forecast; and a missing/expired owner component silently changing a consumer's financial decision. The tests in sections 10–12 explicitly cover each.

## 1. Thesis, product promise and completion law

The defensible thesis is conditional: observable expectations, scenario requirements, fundamentals and market response may contain complementary decision information. Their disagreement might predict later outcomes in some constructions, but that must be demonstrated against matched-information baselines. A persuasive retrospective explanation is not evidence of forecasting skill. A valuation-consistent scenario is not evidence that a representative market participant actually believes it. [W01–W05](EVIDENCE_LEDGER.md)

The first product promise is narrower and immediately useful: a trustworthy expectations dossier that saves the investor from comparing incompatible periods, stale consensus, uncalibrated option probabilities or hidden assumptions. Scientific discovery is a second track; it must not prevent delivery of genuinely useful descriptive context, nor borrow descriptive acceptance as predictive validation.

End-to-end completion has separately reported dimensions. **Source acceptance** means the specific physical source contract is satisfied. **Descriptive product acceptance** means a real authorized user can finish the named workflow in the actual deployed consumer, with provenance, degradation and correction handling. **Scientific acceptance** means each admitted hypothesis receives its predeclared verdict, including valid rejection; an underpowered ongoing study remains unfinished. **Predictive promotion** means the existing evaluator and Conditional Fusion owner authorize a specific construction and consumer. These are not interchangeable badges.

A negative result can complete an experiment. It cannot be relabeled a promoted signal. A live descriptive view can be accepted while predictive research remains held. The full program must not be marked complete while a mandatory contracted capability remains missing or an unresolved study is represented as finished.

## 2. Starting state and immediate critical path

The August source ledger is stale as evidence of absent natural wraparound. The independent snapshot audit confirms 473,200 observations, 8,583 attempts, later unchanged/changed/rollover/partial witnesses and the retained historical defect population. However, all canonical identity, unit, currency, basis and source-publication fields are absent, all rights are UNKNOWN, and all median values are null. #8312 proposes physical-source acceptance but remains an unmerged candidate at this packet's refresh. EXP-1, MKT-1, CPL-1 and PHASE-1 are not built in the recovered K3E state.

The next action is not another collector, another research platform or an enormous factor search. Reconcile #8312's unchanged semantic head, actual writer and latest integration proof; complete its existing acceptance/publication path through the current owner. In parallel, finish a collision-free EXP-1 contract and fixtures, input-use eligibility decisions and the intended consumer adapter. Do not block independent specification or owner qualification on unrelated CI movement. Do not begin a duplicate EXP-1 if the incumbent has already started it.

The legacy freeze explicitly excludes a new valuation/fair-value plane and financial authority. Therefore the scenario-inference and fundamental-distribution branches below require a narrow, recorded owner amendment. That amendment must say exactly what new derived capability is permitted and what remains forbidden. It must not replace the entire K3E-0 law merely to add a scenario view.

## 3. Scientific ontology and representations

Every object binds issuer/security identity, metric and accounting basis, currency/units, fiscal period or market horizon, event identity where relevant, source/knowledge clocks, and its information measure. Comparing two objects requires an explicit compatibility check, not merely a shared ticker.

| Object | Meaning | Permitted initial representation | Forbidden inference |
|---|---|---|---|
| Explicit expectation | A forecast or guidance value actually supplied by a named source | Point, source interval, individual forecasts when licensed, or aggregate snapshot with coverage | Consensus equals the market's belief; high/low equals standard deviation; analyst dispersion equals outcome uncertainty. |
| Valuation-consistent requirement | A set of operating and discount-rate assumptions consistent with observed equity/enterprise value in a specified model | Feasible region, scenario grid, conditional contour and sensitivity | A unique market revenue forecast, intrinsic fair-value gap or implied probability without a probabilistic model. |
| Fundamental state | Owner-native realized/reported operating facts and corrections | Comparable first-release and known-at-cutoff facts | A reported result equals a forecast distribution. |
| Fundamental forecast | A versioned model's conditional forecast of a specified future operating quantity | Point/quantiles first; density only if justified and calibrated | LLM-generated confidence bands or analyst-count-derived precision. |
| Derivative-implied state | Distribution or functional inferred under a stated pricing measure and instrument model | Risk-neutral return density/quantiles, implied move proxy, skew/term structure with quality bounds | Physical probability, future return direction or dealer exposure by default. |
| Market response | Owner-native raw/residual returns and observed repricing | Explicit windows, session/corporate-action basis and residual version | Residual equals mispricing, sponsorship, underownership or causal underreaction. |
| Positioning / market structure | Observed holdings, borrow, short interest, flow or model-based exposure proxy | Separately clocked context, proxy definition and uncertainty | A complete inventory of marginal investors or signed dealer positions from unsigned open interest. |
| Incorporation state | Descriptive relation or an explicitly specified response-model estimate | Interval-censored lead/lag, divergence, model-conditional response residual | Exact percentage of information already priced without a separately identified counterfactual. |

### 3.1 Inverse valuation is a set-identification problem

Let `theta` describe operating trajectories and `z` discount-rate/terminal/capital-structure assumptions. A qualified financial-model owner supplies `V(theta, z)`, expressed on the same equity or enterprise-value basis as the observed target. K3E may consume:

`A(t0) = {(theta, z): abs(V(theta, z) - observed_value(t0)) <= declared_tolerance, and owner financial constraints hold}`.

The output is a valuation-consistent region, not a probability distribution. The tolerance, financial species, price/share count/debt/cash timestamps, terminal economics, cash conversion, reinvestment, tax and dilution assumptions remain inspectable. An empty region means the selected model/assumption family cannot explain the observed value; it does not prove universal overvaluation. A very wide region is an identification warning, not a reason to select a convenient point.

Start with ordinary nonfinancial businesses for which a qualified cash-flow model is appropriate. Banks, insurers, REITs, early-stage binary-outcome firms, negative-cash-flow cases and major capital-structure discontinuities require an owner-approved species model or `MODEL_NOT_APPLICABLE`. Do not apply one EV/revenue-to-DCF conversion universally.

A posterior over scenarios is optional later work. It requires an explicit prior, likelihood/measurement model, model-discrepancy treatment, and sensitivity to all three. Normalizing a grid of feasible scenarios does not create a defensible posterior. The first release should prefer contours and ranges over an unjustified confidence score.

### 3.2 Fundamental probability is a forecasting deliverable

FIF and the relevant financial/earnings owner must own the modeled operating quantities and their semantics. Begin with transparent seasonal/no-change/history-only forecasts and a comparable latest-consensus baseline. A richer model must demonstrate improvement over the information it claims to add, including consensus when consensus is an input. It is not an independent fundamental view merely because a second model restates the same consensus.

Use first-available actuals with correction tracking, training-only preprocessing and uncertainty estimated from properly separated forecast errors. Hierarchical pooling can address sparse issuer samples, but must not conceal cross-firm heterogeneity or imply certainty for unsupported species. LLMs may extract structured claims with source citations and extraction tests; they do not manufacture calibrated numeric distributions. Historical LLM studies need a future-knowledge contamination assessment even when the supplied documents are dated.

### 3.3 Options quantities require the correct measure and horizon

The options owner supplies quote quality, expiry, underlying and forward/carry conventions, exercise style, dividends, stale/crossed/zero-bid handling, interpolation and no-arbitrage diagnostics. A risk-neutral density is a model-implied quantity; fit to current option prices is not calibration to physical outcomes. Sparse strikes and uncertain tails should produce interval bounds or abstention, not a smooth but unsupported distribution. [W02](EVIDENCE_LEDGER.md)

An ATM straddle-derived event-move proxy is not automatically a standard deviation or a physical confidence interval. Event variance isolation requires an explicit baseline non-event variance model and uncertainty; do not assume implied variance is additive across arbitrary horizons. American exercise and dividend effects cannot be ignored when applying a European density identity.

A fundamental-to-options disagreement is admissible only when both sides refer to the same return variable, horizon, event boundary and information set. A three-year revenue CAGR cannot be subtracted from a one-day option move. Converting an operating forecast into a physical return distribution is a separate, evaluated modeling step—not an automatic consequence of having a DCF.

### 3.4 Expectation velocity, acceleration and incorporation

For comparable same-period captures `C(t1)` and `C(t2)`, report the observed change and actual capture interval. With missing source-publication clocks, the underlying revision time is interval-censored; do not invent an analyst-issued timestamp or an intraday lead. Irregular sampling, analyst entry/exit and relative-horizon migration can create apparent acceleration. Require anchored periods, source comparability and enough observations before emitting a second difference.

Descriptive divergence can be useful without an exact incorporation fraction. A post-event response residual can be compared with a future, non-overlapping target; it cannot predict its own already-observed window. In a linear model, a residual constructed from response and features is an algebraic recombination of those inputs. Compare it against a benchmark with the same inputs and comparable capacity before claiming new information.

## 4. Family of estimands: no single gap score

Every emitted gap includes its operands, compatibility decision, horizon, units/measure, baseline and failure state. Use a named family rather than compressing incompatible values into one scalar.

| ID | Estimand and useful question | Initial horizon | Dominant falsifier or refusal |
|---|---|---|---|
| G1 | Fundamental forecast versus comparable explicit consensus | Fiscal quarter / year | No calibrated forecast, mismatched basis/period, or no improvement beyond consensus. |
| G2 | Management guidance versus comparable consensus | Named guided period | Qualitative guidance or non-comparable definition cannot become a numeric surprise. |
| G3 | Fundamental operating scenarios versus valuation-consistent region | Multi-quarter / multi-year | Region is too broad or unstable to distinguish scenarios; model not applicable. |
| G4 | Consensus operating trajectory versus valuation requirements | Multi-year with explicit bridge | Missing margin/reinvestment/capital assumptions; do not solve one dimension and hide others. |
| G5 | Physical event-return forecast versus derivative-implied event state | Exact event/expiry window | Different variables/measures, no physical calibration, poor option support. |
| G6 | First comparable actual versus pre-event explicit expectation | Event and reported period | Expectation captured after event, later actual substituted, or basis mismatch. |
| G7 | Observed response versus a predeclared expected-response model | Completed event window, then separate forward target | Circular endpoint, omitted-news explanation, or same-information baseline wins. |
| G8 | Same-period revision velocity/acceleration versus subsequent state | Capture-aware days/weeks/quarter | Rollover, analyst-mix change, timestamp uncertainty or no incremental value. |
| G9 | Gap-conditioned response modified by positioning context | Target-specific | Delayed/unsigned proxy, small interaction sample or main-effects model matches performance. |
| G10 | Persistent divergence / phase transitions | Registered K3E windows | Classification merely restates momentum or stale coverage; unstable prospective transitions. |

Some G1/G6/G8/G10 constructions may map to existing EVAL-0 targets only after exact semantic comparison. G3/G4/G5/G9 are not automatically covered by the old registration. A new label is not a license to reuse an exposed holdout or reset the trial budget.

## 5. Data and source-use ledger

The owner must complete a machine-checkable eligibility record for each family: source and exact version; earliest trustworthy system/public availability; effective/collection/publication clocks; temporal depth; cadence and gaps; identity/corporate-action treatment; correction semantics; universe and survivorship; permitted internal/display/derived/commercial uses; cost; and actual accepted consumers. Unknown stays unknown.

| Family | Current evidence | What to build or qualify | License decision |
|---|---|---|---|
| Prospective aggregate EPS/revenue estimates | Independently checked August–October SRC-A1 snapshot; averages/ranges/counts, no medians or contributor identity | Owner-side use/basis/identity attestation; anchored, cutoff-safe read model; honest stale/coverage outputs | Reuse held source only within established permission; UNKNOWN is not a grant. |
| Analyst-level estimates / historical consensus | VEND-0 sample-required; no entitled dataset verified here | Vintage, contributor entry/exit, split/currency/correction, publication-time and delisted-name tests | License only after a bounded sample materially improves attainable product/validation. No procurement authorized here. |
| Guidance / KPI estimates | Existing earnings/FIF ownership; no K3E-qualified join | Comparable metric definitions, effective/activation clocks, ranges/text distinction | Evaluate incremental coverage and rights by product, not brand. |
| Financial statements / actuals | Existing financial/earnings owners | First-release and as-known-at-cutoff views, fiscal basis, segments, restatements, shares and capital structure | Reuse; route missing capability to owner. |
| Prices / corporate actions / residuals | Existing price, identity and residual source paths | Exact session windows, splits/dividends, benchmark and pre-event estimation receipts | Reuse owner data and terms; no residual reimplementation. |
| Options / ThetaData | Existing surface/skew/NBBO/episode source paths | Entitlement and historical quote sample, timestamps, quality, expiry/carry, risk-neutral derivation | Existing subscription presence does not prove every historical/display right. |
| Ownership / short interest / borrow / flows | Potential source families, not qualified here | Release delays, reporting scope, proxy direction/sign and revision history | Gate each variable; do not buy a positioning feed before a testable estimand. |
| Macro curves / cross-asset constraints | Relevant existing owners, not K3E-qualified here | Same-cutoff term structures and clearly modeled equity transmission | Later context; no generic macro-belief score. |
| Themes / peers / relationships | Existing GMI/K3-D/F04 and identity ownership | Point-in-time membership, disclosed links versus co-movement, historical universe | Reuse; evaluate incremental value beyond sector/momentum. |
| Event / episode / evaluation history | Existing Earnings, Market Memory, Eval OS / QLedger | Stable event IDs, overlap/censoring, trial access and publication receipts | No second registry, event database or research source of truth. |

Institutional estimates may materially change the feasible research because the current native source cannot populate the old 2012–2026 historical evaluation eras. That is a reason for a sample-based decision, not an assumed purchase. Compare separately FactSet estimates, LSEG I/B/E/S, and S&P estimates/Visible Alpha; the latter belongs to S&P, not FactSet. Bloomberg/AlphaSense and options specialists remain comparison targets, not verified equivalent substitutes or winners. [W06–W09](EVIDENCE_LEDGER.md)

The vendor acceptance sample is a **proposed data-quality test**, not a statistical power claim: select twelve issuers outcome-blind across at least three supported species/coverage conditions, including one delisted or identifier-changed case where available; require anchored estimates spanning pre/post events, a correction, a split/currency case and contributor changes. Test exact historical snapshot reproduction and delivery latency against claimed clocks. Obtain written rights for intended internal, user-display and derived-output use, plus total costs. If a mandatory case is unavailable, record the missing capability rather than quietly replacing the case. Do not contact vendors or commit spend without the existing authorization.

## 6. Owner-native architecture and typed contracts

The production flow is owner observations → eligibility/as-of selection → separate expectation/market/fundamental/scenario/positioning components → compatible gap objects → explained context → existing consumer adapters. Evaluation branches consume frozen versions through Eval OS, not a parallel research database.

The following names are **proposed local interface names**, not claims that a universal schema already exists. MAS-119 retains cross-domain federation ownership; compatible shared fields should be imported once that owner supplies them.

`ExpectationQuery`: canonical security or explicitly scoped provider identity; metric; period anchor; horizon; decision cutoff; `as_known` versus `known_now` mode; requested use; requested components. Do not accept user-supplied flags that widen authority.

`ExpectationSurface`: chosen native observation IDs, provider/aggregation, value or typed absence, range only when supported, coverage counts, capture interval, stale state, eligibility and exclusion reasons, correction lineage, identity/basis/rights receipts and immutable query version.

`MarketResponseContext`: owner-native price/residual/option references; instrument/session/return basis; exact windows and quote time; measurement type; quality and availability. K3E does not recompute residuals or normalize away owner semantics.

`ValuationRequirementsSurface`: owner financial-model version; applicable species; observed equity/EV target and its components; parameter domain and exclusions; feasible region/contours; numerical tolerance; sensitivity and identifiability classification; scenario/assumption IDs. Probability fields are absent unless a separately accepted probabilistic model supplies them.

`FundamentalForecast`: target definition, forecast origin and target period; training cutoff; model/prompt/data versions; point/quantiles/distribution type; calibration evidence reference and limitations; source coverage. `UNCALIBRATED` cannot be rendered as a validated probability.

`PositioningContext`: source-native metric, effective/released/known clocks, scope, sign observability, proxy model and uncertainty. No single crowding score is required.

`ExpectationGap`: named estimand G1–G10; compatible operand IDs; units/measure/horizon; difference or set relationship; uncertainty type; information-set boundary; strongest rival explanation; next falsifying observation; descriptive/shadow/promoted state; degradation. It is evidence, never a portfolio instruction.

`ExpectationContextView`: a projection onto the existing security/Company Intelligence consumer. It carries component availability, top-line explanatory text generated from emitted facts, source links, assumptions and next observable. Server-side permissions and owner-issued authority remain authoritative; UI state cannot promote a field.

Every derived record includes the exact source/model/query version, generation time, cutoff, source/knowledge clocks, owner IDs, native row/artifact references and the provenance of inferred fields. A content hash identifies bytes; publication/capture attestation requires actual owner receipts as well. Cached output is reconstructible and versioned under the current publication/cache owner, not a new primary store.

### Two time views, never an accidental blend

`as_known(t0)` uses only observations and metadata admissible at the cutoff. Appending a later correction must not alter that frozen answer. `known_now_about(t0)` may show subsequent corrections, explicitly labeled with their later knowledge time. These are separate query modes. A provider-effective date alone cannot backdate knowledge; a current Git snapshot cannot certify an earlier public-information history.

Eligibility is component-specific. A source-only inspector may show permitted raw metadata while a numeric economic gap abstains. A valid price component does not make an incompatible consensus value comparable. Source failure, unsupported basis and rights denial must not be converted into zero gap or neutral phase.

## 7. Product architecture: useful before predictive authority

The initial home is the existing security / Company Intelligence experience, not a new standalone application or competing Security State. The exact route and component files must be inspected at implementation pickup. Keep the current design system and responsive behavior; do not redesign the entire Terminal to ship this feature.

The overview answers six questions: what explicit forecasts were available at the cutoff; what changed for the same fiscal period; what the observed valuation requires under declared assumptions; what the qualified fundamental model supports; what options and positioning actually show; and what next observation could invalidate the interpretation. Unavailable components are visible, not omitted to make the dossier appear complete.

Use four progressively richer surfaces. **Overview** shows a compact component summary, coverage and strongest rival explanation. **Expectations and timeline** shows source averages/ranges, same-period changes, capture intervals and corrections without pretending unavailable medians exist. **Scenario requirements** shows a growth/margin contour or scenario table with explicit discount-rate/reinvestment settings; changing an assumption creates a new scenario identity, not a rewritten fact. **Evidence and methods** exposes source rows/receipts, model version, use rights, eligibility, distribution measure and next observable.

The server owns calculations and eligibility; the browser renders typed results. A capture timestamp is labeled capture age, not the age of individual analyst forecasts. After a new missing/partial observation, an older good value may remain visible as `last_good` with its age and current degraded status; it must not masquerade as a fresh current estimate. At a historical cutoff, later information does not leak into the chart or explanatory text.

Separate plots for incompatible units are preferable to a visually persuasive dual-axis overlay. A consensus point/range, fundamental quantiles, valuation contours and an option-implied return distribution must be labeled differently. Never draw an invented Gaussian around a point estimate. Show event/expiry and fiscal horizons adjacent to values, not only in a tooltip.

### Consumer progression

Terminal and Macro may first consume descriptive evidence under their existing publication permissions. Prophet may show a separately accepted context component after its own adapter contract is reviewed, without changing candidate ordering, admission, rejection, lifecycle or allocation. Shadow studies retain both affected and unaffected candidates and their counterfactual evidence. Only existing Eval OS / Conditional Fusion promotion can grant a specific later predictive influence.

Risk Radar, Market Tide, Live Entry, theme intelligence and portfolio-management integrations each need their own evidence-to-decision contract. K3E supplies expectation-gap evidence and limitations; it does not become any of those systems. Initial alerts are descriptive changes through the existing alert owner, with source deduplication and retraction. No unvalidated gap may escalate a financial-risk level or imply an order.

The first live vertical is accepted only when a user can select a covered security and cutoff, see the supported expectation state and actual source lineage, distinguish stale/unsupported fields, and reopen the same snapshot reproducibly. A JSON schema or an isolated attractive mockup does not satisfy this criterion.

## 8. Hypothesis and experiment matrix

These are proposed experiments, not permission to start them or implied additions to EVAL-0. The evaluator must map each construction to an existing registered target or approve a new prospective protocol first. Every row requires a data-use/coverage admission receipt, a frozen event/issuer population, exact target cutoff, and a predeclared minimum useful effect. No row is retained merely because its story sounds valuable.

| Experiment | Mechanism / target | Required data and horizon | Strong baseline | Negative control / falsifier | Primary evaluation |
|---|---|---|---|---|---|
| H01 — comparable revision persistence | Same-period estimate change predicts later comparable estimate direction/magnitude | Anchored SRC-A1 or licensed vintages; capture-aware registered horizon | No change, latest comparable consensus, registered revision summaries | Horizon-rollover placebo; future timestamp must be rejected; effect vanishes after stale/mix controls | Direction/loss, coverage, episode-clustered uncertainty |
| H02 — revision acceleration | Change in revision pace adds information beyond level and first difference | At least the admissible repeated captures; exact intervals and source mix | H01 plus momentum and first difference | Irregular-sampling controls; shuffled within eligible calendar blocks; no increment | Incremental loss / registered target metric, not attractive curves |
| H03 — guidance/actual versus consensus | Comparable expectation surprise predicts a later target or clarifies event state | First guidance/actual, pre-event consensus, canonical event/session | Raw surprise and price/sector/momentum controls | Deliberate basis/period mismatch rejected; event-clock placebo | Surprise calibration and separately admitted future-response loss |
| H04 — fundamental forecast increment | Owner forecast adds operating-outcome information beyond consensus/history | PIT fundamentals and first-release targets; quarter/year | Seasonal/no-change and comparable consensus | Model only restates consensus; text-shuffle where text used | Point/quantile loss, interval calibration, sharpness and abstention |
| H05 — valuation requirements context | Scenario region provides stable, useful constraints and possibly later outcome information | Qualified cash-flow model and contemporaneous EV inputs; multi-year | Standard valuation variables plus momentum/fundamentals | Conclusion flips under plausible nuisance assumptions; equal-information model matches | Identification width and sensitivity first; forecast loss only under new registration |
| H06 — derivative event uncertainty | Qualified option features improve event risk forecasts | Pre-event quote surface and exact event/expiry window | Historical conditional event move, ATM move proxy, volatility/skew separately | Stale/sparse surface; improvement absent out of time | Risk-neutral fit diagnostics separately from physical Brier/log/quantile loss |
| H07 — fundamental/options disagreement | A comparable physical forecast adds to options-only risk context | Accepted H04-to-return mapping and H06; same return variable/window | Options plus fundamental components with comparable capacity | Q/P or horizon mismatch; same-information benchmark eliminates gain | Proper score improvement and calibration; tail capture with false-alarm rate |
| H08 — post-event response gap | Completed response residual forecasts a later disjoint window | Native residual and comparable surprise; decision after response observed | Response plus all residual-model inputs; nonlinear control of matched capacity | Algebraic recombination only; shifted endpoint / overlapping target | Future abnormal-return distribution and incremental loss; costs later |
| H09 — positioning amplification | A qualified proxy modifies gap-conditioned response | Released holdings/borrow/short/flow data; target-specific | Gap and positioning main effects, plus liquidity | Signed exposure unobserved; interaction unstable; reporting-delay placebo | Incremental interaction value, subgroup uncertainty and false warnings |
| H10 — incorporation / phases | Descriptive state improves next-state or admitted later-target forecast | EXP-1/MKT-1 compatible history; registered windows | Momentum, revisions, volatility and prior phase separately | Merely renames momentum or missingness; label instability | Transition/discrimination/calibration with abstention and state persistence |
| H11 — theme-relative extension | Pre-existing economic links add beyond ordinary co-movement | PIT GMI/K3-D links and upstream/downstream events | Sector/peer/own/upstream return controls | Randomized links, disclosed-after-event links rejected | Incremental registered loss, episode and common-shock controls |
| H12 — consumer usefulness | Dossier improves a defined decision without hiding information | Versioned descriptive view and matched user/machine cases | Existing Company Intelligence / Prophet context | Same acceptance-rate and information controls; more refusals alone cannot win | Task accuracy, correction detection, confidence calibration, coverage, latency |

Promotion requires the conjunctive gates in section 9, not a universal target such as AUC 0.7 or a convenient standalone p-value. H05 can succeed as honest scenario context without predictive alpha. H12 can establish usability without granting a financial model permission. Predictive claims must identify exactly which construction, horizon, population and consumer passed.

## 9. Evaluation architecture and promotion law

### Preserve the registered experiment, then version genuine extensions

The recovered EVAL-0 contract registers eight target families, nine baselines, a 64-challenger-trial family, dependent-test BY-FDR at q=0.10, 63-session purge/embargo, and minimum distinct-issuer-episode/coverage conditions. The #8312 summary reports 100 episodes overall, 25 per claimed subgroup and 60% coverage; the immutable JSON's exact denominator, target definitions and motivating-case conditions remain controlling, not this shorthand. Existing development is 2012–2018, validation 2019–2022, locked holdout 2023-01-03 through 2026-08-21, with prospective activation thereafter. [S04](EVIDENCE_LEDGER.md)

The current native source begins in August 2026. It cannot populate the earlier eras, and a present snapshot cannot be placed into them. Retrospective data are admissible only when their vintage/knowledge history and rights satisfy the owner protocol. If no such data exist, the relevant historical study is unavailable; a newly preregistered prospective study is the lawful alternative, not silently changed dates under the old name.

Before new inverse/physical/positioning work, record a versioned protocol with its own target definitions, reasoning, unseen evaluation boundary and relationship to the existing family. Preserve all earlier trial and outcome-access records. Do not reset 64 trials per worker, market, seed or new filename. A new registration does not make already-inspected data unseen. The live remaining budget must be read from the existing evaluator before any admission.

### Freeze what could otherwise be selected after the result

Freeze universe/membership, issuer/episode definition, event clocks, label horizon, entry convention, missingness treatment, preprocessing, normalization, model class/capacity, hyperparameter search, primary metric, baseline selection, subgroup claims, multiple-testing treatment, confidence procedure and stopping rule. Record data/model/prompt hashes and actual access times. Use source-before-outcome extraction where the governing family requires it.

All feature clocks are at or before the decision cutoff; actuals and return targets occur strictly afterward unless the object is explicitly descriptive. Correction-aware joins must preserve first-known values. Do not use today's fiscal mapping, consolidated accounting basis, constituents, revised macro series or final actuals as though historically available. Pre-event residual sensitivities and peer memberships are estimated from admissible earlier data only.

Temporal separation must cover target overlap and feature construction. Preserve EVAL-0's 63-session rule where applicable; a new longer-horizon construction may require a larger gap. An overlapping training label cannot cross a supposedly held boundary merely because the feature timestamp is earlier. Purge by issuer episode and common event/calendar exposure as the protocol specifies.

### Count information, not rows

473,200 source rows contain repeated captures, seven observation types and multiple horizons. They are not 473,200 independent earnings events. Report unique issuers, episodes, event dates, market regimes, overlapping windows and information clusters. Existing minimum episode counts are floors, not power proofs. Predeclare a useful effect and estimate detectable power using appropriate clustering/dependence assumptions before opening the held outcomes.

Use matched-information ablations. Compare each proposed composite with its ingredients, and compare nonlinear challengers with similarly capable baselines. Include exclusion/abstention denominators and selection effects. A model that looks accurate only by refusing difficult cases must be compared at matched coverage, not celebrated for its conditional hit rate.

### Metrics must match the object

For operating point forecasts use an appropriate scale-aware loss; for quantiles use quantile loss and interval coverage; for genuine distributions use proper scores and calibration/sharpness diagnostics. For event probabilities use Brier/log loss and reliability; for rank/return targets use the registered discrimination and abnormal-return metrics. A fitted Q density is checked against option prices and no-arbitrage constraints; physical calibration is a separate test against realized outcomes.

For risk claims report warning lead time, false-alarm/miss rates, tail coverage and uncertainty. For phases report coverage, state stability, transition quality and explanatory fidelity. P&L is a later consumer outcome with feasible latency, bid/ask, turnover, borrow, slippage, impact and capacity; it is not a replacement for validating the inferred state.

### Conjunctive promotion gate

A construction is eligible for promotion only when its data/use and semantic contracts pass; target/experiment access was lawful; the predeclared incremental metric exceeds its minimum useful effect with the registered uncertainty/multiplicity treatment; calibration and claimed subgroups satisfy their gates; performance survives matched-information ablations and relevant costs; a genuinely prospective observation corroborates the claimed capability; independent exact-version review closes blockers; and the existing consumer authority explicitly accepts the construction. Failure at any required gate means hold, repair or rejection—not a hidden low-confidence production weight.

Preserve negative results. Stop a construction when the preregistered futility/invalidity condition fires, when plausible nuisance assumptions make the inference unusable, when a strong eligible baseline wins, or when the required data cannot be acquired lawfully. Reopening requires a new substantive hypothesis and appropriate registration, not renamed thresholds.

## 10. Sequenced implementation and exact work packages

The dependency graph is source acceptance + eligibility → EXP-1 → MKT-1 → CPL-1 → PHASE-1. The scenario, fundamental and positioning extensions branch only after their owner/authority decisions and join the compatible gap layer when qualified. Evaluation is a parallel governance dependency before any outcome-bearing experiment, not a final retrospective paperwork step. A descriptive consumer accompanies the earliest usable surface rather than being deferred until every advanced model exists.

The file names below marked **proposed** are an implementation map, not evidence of existing files. Before touching them, compare current equivalents and active branches. If an owner already supplies the same interface, extend that interface and update the map instead of creating a duplicate. Resolve actual consumer and financial-model owner paths in the first pickup receipt.

### Wave 0 — source acceptance, custody and semantic amendment

**Owner:** Astra as the assigned program principal, with the incumbent integration/source owner and required independent reviewer. **Existing surfaces:** Macro #8312/#8309; #8064; K3E `CURRENT_CAPABILITY_LEDGER.md`, freeze, current EXP-1 contract/carrier, data-clock/rights matrix and EVAL-0 records. Recover the actual current handoff rather than assuming a filename or creating a duplicate.

- [ ] Read the latest cumulative checkpoint and exact current heads/custody; determine whether #8312 is still open, has merged, changed semantics or received a blocker. Preserve any live writer or unknown effect.
- [ ] Compare the exact acceptance evidence to its physical-source completion law. Reuse unchanged semantic review where permitted; obtain latest-base integration proof instead of restarting the audit merely because main advanced.
- [ ] Record the bounded source-state transition only through the existing accepted carrier. Retain historical exclusions, natural-versus-synthetic proof limits, and metadata/rights limitations.
- [ ] Resolve local source-use, identity and measurement-basis eligibility with their owners. Define a local EXP-1 envelope without waiting for a nonexistent universal MAS-119 implementation or taking over that program.
- [ ] Record a narrow proposed/accepted amendment permitting owner-native valuation-requirements and fundamental-forecast projections. Preserve the ban on intrinsic fair-value claims, new truth planes and financial authority. Until accepted, keep these extension implementations held.
- [ ] Recover the original completed K3E report if it becomes available and audit its exact claims against this evidence. Missing-report certification remains visibly unresolved; it does not authorize another Deep Research run.

**Completion evidence:** exact source acceptance/release receipt or precise remaining gate; custody decision; owner interface map; source-use decision by component; preserved EVAL-0 identity; explicit extension disposition. No new collector or outcome study is required for this wave.

### EXP-1 — deterministic cutoff-query surface plus first consumer

**Owner:** revisions/read-model builder, with identity/financial/use owners and Terminal or Macro consumer builder. **Proposed local files in Macro:** `engine/k3e/expectation_surface.py`, `engine/k3e/eligibility.py`, `contracts/research/k3e_expectation_surface.v1.schema.json`, `tests/test_k3e_expectation_surface.py`, and `tests/fixtures/k3e/`. Reuse incumbent equivalents if present. **Existing read-only inputs:** the two SRC-A1 parquet artifacts; owner-issued identity/basis/use receipts. Do not edit `collectors/equity_revisions.py`, the incumbent W2A suite, legacy revision artifacts or `engine/theme_revisions.py` in this wave.

**Proposed interface:** `build_expectation_surface(query: ExpectationQuery, observations: ObservationRead, attempts: AttemptRead, eligibility: EligibilityRead) -> ExpectationSurface`. Inputs are read capabilities/typed owner results, not caller-controlled filesystem paths or authority booleans. `select_as_known` is deterministic and side-effect free. A later corrected view uses an explicitly different query mode.

- [ ] Write failing tests for the contract and the ten named adverse cases in section 11. Each refusal must preserve a typed reason and cannot silently return neutral data.
- [ ] Implement the minimum selector/eligibility projection: select compatible source observations at the cutoff, preserve native IDs and lineage, keep last-good separate from latest observation status, and label capture age accurately.
- [ ] Emit only supported fields. Averages/ranges require qualified semantics; all-null median remains unavailable. Source-relative horizons must be anchored before computing same-period changes.
- [ ] Implement one read-only adapter into an existing security/Company Intelligence consumer. Record its actual source path and URL in the wave receipt before claiming integration. A cross-repository consumer change may use a second bounded PR, but the vertical is not accepted until producer and consumer are proven together.
- [ ] Run isolated contract/property tests, repository-native validation and actual consumer scenarios on a permitted realistic source sample. Do not publish values beyond their source-use grant.
- [ ] Obtain independent exact-head review, current integration proof and required release authorization; install through the existing deployment owner and verify the real consumer.

**Acceptance:** selecting a covered security/cutoff yields source-backed values or honest refusal, not a placeholder; later appends do not change prior `as_known` output; rollover does not fabricate a revision; no median is invented; a current missing capture cannot refresh an old good value; no protected legacy behavior changes; actual consumer proof is recorded. Rights-blocked metadata-only behavior can pass its negative test but cannot be called a completed numeric expectations product.

**Run target after implementation:** `python -m pytest -q tests/test_k3e_expectation_surface.py`, plus the current owner's required schema/consumer checks. This is a planned command, not a test executed by this audit.

### MKT-1 — owner-native event and market-response composition

**Owner:** market-response adapter builder with Earnings/Identity/options/residual owners. **Proposed local files:** `engine/k3e/market_context.py`, `contracts/research/k3e_market_context.v1.schema.json`, `tests/test_k3e_market_context.py`. **Existing candidate owners to qualify:** `engine/residual_alpha.py`, `engine/residual_momentum.py`, `engine/price_pressure/`, `engine/earnings_release/`, `engine/options_surface.py`, `engine/options_skew.py`. File presence does not identify the right residual semantics; the owner must supply the intended result contract.

**Interface:** `compose_market_context(query: MarketContextQuery, event: EventRead, price: PriceRead, residual: ResidualRead | None, options: OptionContextRead | None) -> MarketResponseContext`.

- [ ] Write failing tests for mismatched event/security/return basis, unavailable residuals, incorrect market-session boundaries, stale option timestamps and risk-neutral-to-physical relabeling.
- [ ] Import approved owner outputs; preserve versions, benchmark/universe, corporate-action basis, cutoff and exact windows. Do not calculate a replacement residual because an import is inconvenient.
- [ ] Emit `RAW_ONLY` or the accepted degradation when optional components are absent. An unsupported event window cannot be silently substituted by a convenient calendar return.
- [ ] Extend the same consumer with separate price/response/options context and explicit horizon labels. Verify raw-only and partial-output behavior.
- [ ] Run the owner-native integration tests and independent review; record installed/consumer proof separately from source merge.

**Acceptance:** all displayed market components are attributable to compatible owner results; no post-cutoff import, fabricated residual, event identity or implied physical probability; the real consumer works under missing-source conditions.

### VAL-1 — conditional valuation-requirements surface (new, gated extension)

**Owner:** existing financial/valuation model owner for the economics; K3E for the derived requirements projection. If the needed financial evaluator does not exist, commission that missing capability in its proper owner rather than constructing a competing K3E valuation engine. **Proposed K3E files:** `engine/k3e/valuation_requirements.py`, local requirements schema and `tests/test_k3e_valuation_requirements.py`.

**Interface:** `build_valuation_requirements(request: ValuationScenarioRequest, evaluated_grid: OwnerValuationGrid) -> ValuationRequirementsSurface`. The financial owner evaluates cash flows/capital structure; the K3E projection classifies and presents scenario compatibility. Persist assumptions/results only through the existing artifact/publication owner.

- [ ] Require the accepted narrow amendment, applicable species and owner-versioned economic evaluator.
- [ ] Write tests where two different growth/margin/discount-rate combinations fit the same price; both must remain visible. Test empty/wide regions, invalid terminal economics, incompatible EV/equity bases, future share counts and unsupported species.
- [ ] Implement deterministic region construction and sensitivity summaries with declared tolerances. Expose all nuisance assumptions and model-discrepancy limits.
- [ ] Add scenario controls and provenance to the existing consumer without target-price, buy/sell or probability copy.
- [ ] Validate numerical stability and regression cases independently of future returns. Any predictive use requires its separate registered experiment.

**Acceptance:** the feature refuses a unique forecast when not identified, remains reproducible under the same assumptions, exposes sensitivity, and makes no intrinsic-fair-value or forecast-probability claim from geometry alone.

### FUND-1 — qualified operating forecasts (new, gated extension)

**Owner:** financial/earnings forecasting owner; K3E consumes its typed output. **Proposed K3E file:** `engine/k3e/fundamental_forecast_adapter.py` with corresponding contract/conformance tests; actual training/model paths belong to the current financial owner and must be resolved before implementation.

- [ ] Freeze the target, first-actual/correction convention, source history, training/validation access and naive/consensus baselines through the evaluator.
- [ ] Write leakage tests for late filings/restatements, changed fiscal mappings and future model inputs. Test that absent calibration cannot populate a validated-probability field.
- [ ] Implement the smallest owner-native baseline; add complexity only within an admitted comparison. Preserve predictions issued before outcomes and the exact model/data versions.
- [ ] Evaluate point/quantile/distribution quality as appropriate, by supported species and coverage. Retain adverse results and uncertainty.
- [ ] Wire qualified forecasts into the consumer with explicit calibration status. Uncalibrated scenarios may be shown only under an approved scenario label, never as physical probability.

**Acceptance:** a reproducible, properly evaluated operating forecast exists or the family receives an honest negative/insufficient-data verdict. A point estimate is not upgraded to a distribution by visual design.

### OPT-1 and POS-1 — qualified uncertainty and transmission context

**Owners:** current options and positioning/source owners. These are separately accepted bounded increments, not one new market-structure service. K3E adds only adapters/conformance tests in its existing module.

For OPT-1, require a quote/history/use qualification; exercise sparse strikes, crossing/staleness, dividend/exercise-style differences, event/expiry mismatch and unstable tails; import a named implied-move proxy or Q distribution with correct labels. A physical transform is a separate outcome-bearing experiment. For POS-1, require released/known clocks, scope and sign observability; test delayed holdings, missing borrow, changing reporting universe and unsigned open interest. Do not infer hidden positions to fill missing source coverage.

**Acceptance:** every component states what is observed and inferred; uncertain/missing inputs abstain; source entitlements and actual consumer behavior are qualified. Neither increment independently creates predictive influence.

### CPL-1 and PHASE-1 — compatible gaps and explained states

**Owner:** K3E read-model builder with the incorporation/evaluation owner. **Proposed files:** `engine/k3e/gaps.py`, `engine/k3e/phases.py`, local gap/phase schemas, `tests/test_k3e_gaps.py`, `tests/test_k3e_phases.py`. Reuse existing accepted implementations if one has appeared.

**Interfaces:** `derive_gap(spec: GapSpec, left: TypedComponent, right: TypedComponent, context: GapContext) -> ExpectationGap`; `describe_phase(components: PhaseInputs, rule_version: str) -> DescriptivePhase`.

- [ ] Freeze compatible estimands, descriptive thresholds/denominators and rule versions before outcomes can choose the story. Preserve the existing component-first phase law.
- [ ] Write tests for incompatible currencies/bases/horizons, Q/P mismatch, stale operands, near-zero/negative EPS, missing denominator and arithmetic/algebraic circularity.
- [ ] Implement named component gaps and uncertainty/abstention. Do not collapse them to a universal score or attach unapproved weight/rank fields.
- [ ] Emit explanation, strongest rival, failed gates and next observable from the actual components. Generative text cannot add unsupported numerical or causal claims.
- [ ] Integrate with the same consumer and verify healthy, partial, correction, mixed and unestimable cases. If the question requires an absent component, abstain rather than substitute a different question.

**Acceptance:** a state never appears without its supporting components and coverage; no exact priced-in percentage, hidden aggregate or financial decision authority is inferred. Predictive experiments remain separate from descriptive conformance.

### EVAL-1 — admitted retrospective/prospective experiments and negative results

**Owner:** current Eval OS / QLedger and family-science owner; Astra adjudicates the research question within current authority. **Existing records:** `eval0_preregistration.v1.json`, `eval0_activation_receipt.v1.json`, evaluation schema and owner experiment artifacts. Amend/version lawfully; do not rewrite the original registration.

- [ ] Map each experiment to an exact registered target or obtain a new prospective protocol; read remaining budget and exposure history before dispatch.
- [ ] Admit only rights/clock/identity/basis-qualified inputs. Prove that the evaluation's actual temporal eras are supported; otherwise emit the appropriate unestimability decision.
- [ ] Run boring baselines first, then bounded challengers with purging, episode/common-shock dependence, negative controls and matched-information ablations.
- [ ] Consume fixed-version results, including failed trials; apply the declared uncertainty, multiplicity, power/coverage and futility rules without moving the goalposts.
- [ ] Accrue prospective outputs through the existing scheduled owner, with actual accepted execution and return receipts. A chat checkpoint is not a daemon.
- [ ] Produce construction-specific PASS/HOLD/REJECT results, a reproducible evidence package and an explicit next gate. Do not label a study complete while required natural outcomes are still accruing.

### CONSUMER-1 — optional predictive promotion, rollout and operational closure

**Owners:** existing Conditional Fusion, Prophet/lifecycle and product/deployment owners. The actual implementation paths remain theirs. This wave is optional in outcome: failure of scientific promotion preserves the accepted descriptive product and rejects the unsupported signal.

- [ ] Obtain a construction- and consumer-specific promotion decision. Define allowed effect, scope, calibration/coverage requirements, feature flag and rollback. No generic “K3E passed” permission exists.
- [ ] Test unchanged candidate order/admission/lifecycle while descriptive or shadow-only. For promoted behavior, prove only the approved decision changes and retain the old path for rollback.
- [ ] Deploy by current release law, validate real authenticated user/machine paths, and exercise degradation/retraction and restart/replay behavior.
- [ ] Expand market/species coverage only after repeating source/clock/basis/rights and evaluation qualifications; do not project US source proof globally.
- [ ] Update the canonical capability ledger and Agent OS handoff; repair Linear projection only after evidence. Close each child explicitly without abandoning a live watcher or writer.

## 11. Discriminating verification matrix

| Test ID | Owning wave | Required assertion |
|---|---|---|
| T01 future-append invariance | EXP-1 | Appending any later observation/correction/metadata receipt leaves earlier `as_known(t0)` output unchanged. |
| T02 explicit corrected view | EXP-1 | `known_now_about(t0)` exposes later knowledge and cannot be confused with the original snapshot. |
| T03 rollover and horizon stability | EXP-1 | Same relative label with a new absolute period creates a different node, not a same-period revision. |
| T04 partial/null after good | EXP-1 | Prior good evidence remains; current missing status remains; old value is not refreshed or overwritten. |
| T05 genuine zero versus uncovered zero | EXP-1 | A covered genuine zero is retained; empty-consensus measurement is excluded with a reason, not retro-deleted. |
| T06 no imaginary statistics | EXP-1 | Null median stays null; high/low is not standard deviation; reviser counts do not replace analyst coverage; capture age is not analyst age. |
| T07 identity/basis/use refusal | EXP-1 | Ticker-only alias, unknown currency/unit/basis or missing use rights cannot produce an economic comparison or unauthorized raw-value display. |
| T08 owner import integrity | MKT-1 | Event/session/security/benchmark/return-basis mismatch fails; missing residual stays missing; no local recomputation fallback. |
| T09 underidentification | VAL-1 | Multiple fitting scenarios stay multiple; broad/empty regions are labeled; no synthetic posterior or target-price authority. |
| T10 forecast leakage/calibration | FUND-1 | Later actuals/restatements/model inputs are rejected; uncalibrated outputs cannot populate validated-probability fields. |
| T11 derivative measure/horizon | OPT-1 / gaps | Q cannot become P through relabeling; different expiry/event windows cannot be compared; quote-quality failure propagates. |
| T12 positioning observability | POS-1 | Unsigned/open-interest and delayed report inputs cannot become verified signed current positions. |
| T13 circularity / same information | EVAL-1 | A response residual is not evaluated against its own completed window; ingredient/capacity-matched controls are included. |
| T14 multiple-testing continuity | EVAL-1 | Trial identity and exposure persist across workers, markets, retries and renamed models; no new filename resets budget. |
| T15 authority containment | All consumers | Missing, partial, descriptive and shadow states cannot affect rank/admission/gate/size/lifecycle unless separately promoted. |
| T16 actual user proof | Consumer waves | Real route loads, sources resolve, correct cutoff survives reload, keyboard/mobile behavior works and stale/denied states remain understandable. |
| T17 rollback/retraction | CONSUMER-1 | Source correction or revoked qualification retracts current derived claims through existing owners without rewriting prior as-known history or creating duplicate alerts. |
| T18 scalability and determinism | EXP-1 onward | Repeated identical queries yield stable results; bounded owner reads meet the predeclared dataset/latency target without unbounded per-row history scans. |

For each code task, follow a red/green cycle: write the named failing test against the smallest fixture; observe the intended failure; implement the minimal behavior; rerun the test and relevant existing suite; inspect the bounded diff; commit through current source-custody law. A test failing for an import or unrelated cleanup is not a semantic mutation kill. Published test counts bind exact code/input versions. An unrun planned command is never a pass receipt.

## 12. Operations, cost, failure handling and provenance

Keep a single action-authoritative principal for the mission and one source writer per bounded change. Delegate independently executable outcomes through the existing admitted fabric, not command-by-command micromanagement or a new orchestration system. Good parallel boundaries are input-use/identity qualification, a frozen consumer contract, scientific protocol review and disjoint owner adapters. Collector/source-acceptance work, common schema changes and shared consumer files require coordinated custody.

Use current capacity and budget law; this plan does not allocate unlimited workers or a fresh trial budget to each child. Prefer deterministic source analysis and baseline tests before expensive model searches. No `codex/work` use is authorized by this packet. Resolve actual tool capability instead of assuming a named model or app is available; missing tools do not justify fabricated execution receipts.

Track operational quality through existing owners: capture age versus forecast age, source availability, eligible coverage, correction/retraction rates, component-level abstention, assumption/model version, quote quality, query latency and current consumer release. Track scientific quality separately: prediction calibration, trial count, shift, subgroup coverage and realized outcomes after their horizons mature. Do not turn this into a new telemetry truth store.

Define release-specific budgets before deployment from the actual production path. A useful performance acceptance test must state dataset size, cold/warm cache, hardware/service context and percentile target. This packet intentionally does not invent an unsupported production latency SLA. The source-performance lane #8064 must be reconciled before proposing overlapping history-scan optimizations.

Failure policy is explicit. Input degradation yields a typed partial/unestimable component and cannot silently fall back to an old fresh-looking value. Source corrections create a new current derived version and a visible correction path while preserving historical knowledge. Qualification expiry or rights revocation blocks the affected use through its owner. Prediction drift can disable the specific promoted construction without removing the descriptive dossier. Rollback uses the existing flag/release/publication path; it does not create a second policy engine.

Every accepted wave leaves one current cumulative checkpoint in the existing owner: immutable code/input/result identities, accepted and rejected approaches, outstanding gates, current custody, active child/effect state, actual tests and exact next action. A handoff document does not prove receiver pickup, a queued Job does not prove execution, and a source merge does not prove installation or product use.

## 13. Final acceptance and Astra's continuation obligation

The program's final review must answer the original investor questions, not merely count modules. Demonstrate the real end-to-end dossier for representative healthy, stale, missing, rollover, corrected, underidentified and rights-denied cases. Show which components are descriptive, scenario-only, calibrated, shadow-only, rejected and promoted. Explain why each displayed probability is a probability of the named target and why each unavailable inference abstains. Show the exact canonical source/consumer/evaluator paths and prove no duplicate authority plane was introduced.

For each hypothesis, preserve its estimand, mechanism, data, horizon, strongest baseline, negative control, falsifier, episode coverage, metric, threshold and actual verdict. For each feature, preserve source/contract tests, independent review, current-base integration, installed release and user/machine proof when owed. A named extension can be rejected on evidence without being hidden; an unresolved mandatory deliverable remains incomplete.

Astra must continue beyond the first accepted module into the next unblocked dependency. A blocked provider purchase does not stop source semantics or an already authorized consumer adapter. A pending merge does not justify repeated status-only turns when a disjoint contract/test lane remains open. Conversely, no amount of elapsed effort justifies opening held outcomes, taking an active branch, changing cadence for proof, or promoting an unvalidated score.

**Exact first pickup:** consume [ASTRA_CEO_HANDOFF.md](ASTRA_CEO_HANDOFF.md), refresh current protected law and #8312/#8064/EXP-1 custody, then advance the existing source acceptance plus the disjoint EXP-1 cutoff-query/consumer vertical. Preserve all later scientific and authority gates. Do not rerun Deep Research.
