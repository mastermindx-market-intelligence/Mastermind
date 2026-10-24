# Beyond the flow score: identifying hidden pressure through resistance, cancellation and release

**MastermindX original research follow-up — October 14, 2026, New York.**

**Question:** How can Mastermind detect developing accumulation, distribution and rotation earlier without simply renaming momentum or inventing institutional inventories?

**Result:** Shift the inference target from “who secretly owns what?” to **which side of the market is becoming easier to move, under what next disturbance, and whether that change survives the withdrawal of temporary pressure**. This follow-up develops eight candidate patterns, derives identification limits, specifies genuinely sequence-sensitive measurements, and executes a new later-vintage experiment. The experiment rejects another tempting shortcut. None of the new candidates is represented as validated market alpha.

The ideas below are new proposals or substantial refinements **relative to this commission**, not assertions of worldwide priority. Where a component already appears in literature, it is attributed. Research prototypes do not change production, source-rights flags, schemas, rankings, alerts or trading authority. Original LP-ETF-01 and its negative verdict remain unchanged.

## 1. Why the original question needs a different observable target

A flat price is compatible with no interest, large opposing interests, deep mechanical liquidity or carefully sliced trading. We should not equate “little movement” with “nothing happening,” but the reverse inference—“there must be informed accumulation”—is equally unsupported.

Consider the deliberately simplified response equation

`r_t = lambda_t * (q_t + b_t - s_t) + e_t`.

Here `q` is observed signed aggressive flow; `b` and `s` are latent **reduced-form demand/supply pressures**, not extra executed share flows; `lambda` is impact sensitivity and `e` unmodeled response. Every actual trade still has both a buyer and seller. This equation is an identification thought experiment, not a literal accounting system.

Adding the same amount to `b` and `s` leaves all observables unchanged. With known `lambda` and no noise, only `b-s = r/lambda-q` can be recovered. Unknown sensitivity and noise add ambiguity. Statistical learning can exploit restrictions and extra observations, but cannot reconstruct information erased by the observation map without assumptions.

A constructed counterexample is stronger than a verbal warning. During a buying episode, set `q=1`, `lambda=1`, `e=0`. Both `(b,s)=(0,1)` and `(10,11)` produce exactly zero return. If pressure stops and both worlds follow the same decay rule—90% retention of b, 20% of s—the next response is −0.2 in the first and +6.8 in the second. Identical observed pressure-window data can precede opposite moves. Even observing the later direction does not identify actual owners.

**The constructive consequence is not to abandon inference. It is to estimate observable conditional behavior.** We can ask whether bids recover more slowly after comparable selling, whether the ask replenishes despite repeated buying, whether a move survives a detected flow pause, and whether the same pattern recurs across independently measured shocks. Those are testable even when ownership is unknown.

Keep two quantities separate:

1. The probability and severity distribution of the next disturbance.
2. The conditional response to that disturbance, given the currently observed market history.

A fragile book does not imply a crash if no adverse pressure arrives. A robust book can fail under an unusually large shock. Combining these quantities requires a joint conditional model, not multiplying unrelated “confidence” scores.

## 2. What newly inspected research changes

Several sources add more than another technical indicator:

- **Anonymous metaorder proxies:** Maitrier, Loeper and Bouchaud (April 2025 version) generate synthetic order programs from anonymous trades and recover aggregate impact patterns. These are intentionally not recovered true investors. Their experiments include EuroStoxx futures and seven Paris stocks. This supports affordable impact research, not ownership claims or forecast performance. [S1]
- **Behavioral decomposition:** ClusterLOB (2025 preprint) partitions order events using available book/event characteristics. Its experiment uses fifteen Nasdaq stocks in 2021, with a first-half/second-half split. Cluster names describe inferred behavior, not verified investor identity; its results are not our independent replication or an execution-cost guarantee. [S2]
- **Cancellation matters in hidden-order estimation:** Zotikov and Antonov's CME iceberg work uses specific order-depth/message behavior and survival estimation that accounts for partially executed cancellations. That capability is tied to source fields, not obtainable merely by labeling a large public print. [S3]
- **Response persistence is ambiguous:** studies of post-metaorder impact have to distinguish relaxation from correlated subsequent orders; long-run retained impact estimates differ across data and assumptions. A persistent price plateau is not automatically permanent information. [S4–S5]
- **Natural shocks are not automatically clean experiments:** He, Kondor and Li's July 2026 revision explains how a supply disturbance changes dynamic risk and thus the demand relation being measured. This directly cautions against treating index/fund flow as an unquestionable instrument for hidden demand. [S6]

Older session-decomposition work motivates looking inside daily returns, but it does not justify our own new feature without testing. Cross-market results also differ. The New York Fed's July 2026 analysis reports disappearance of a previously documented early-morning overnight drift after 2021, reinforcing the need to model the mechanism rather than hardcode a profitable clock window. [S7–S10]

### Novelty map: what actually changes from the first commission

| Previous approach | New research change | Why it is not merely another name |
|---|---|---|
| High volume with small displacement | Ordered recovery/fatigue under matched challenges | Adds event timing and conditional vulnerability, not only another daily ratio |
| Persistent signed flow | Pause survival and robustness across synthetic assignments | Separates continuing pressure from its aftermath and retains assignment ambiguity |
| One aggregate imbalance | Size/event-type opposition spectrum | Preserves disagreement hidden by aggregation; investor labels remain unknown |
| Raw breadth or generic down-day strength | Predetermined exposure-specific event response | Changes the comparison from any down day to the same kind of information shock |
| One thematic correlation graph | Dated co-ownership versus economic graphs | Tests mechanical demand spillover against fundamental transmission with graph placebos |
| Single confidence number | Competing explanations and discriminating observations | Separates model disagreement, quality, future shock arrival and conditional response |

No transform creates information absent from its inputs. A richer nonlinear transform can improve a restricted model, but that is not the same as observing an additional phenomenon. Here the strongest extensions require order timing, quote recovery, source-backed events or dated holdings. Our tested session split really adds opens to closes, yet still fails its forecasting test: more information alone is not enough.

## 3. Pattern A — support fatigue before support breaks

### Original proposal

**Measure the recovery process after repeated pressure, not just the fact that a level held.** A bid can survive several sell waves while becoming progressively less resilient. That deterioration may precede an obvious breakdown; the mirrored ask-side behavior can precede an upside release.

At each already observed pressure episode, record consumed displayed quantity, same-level replenishment, depth recovery delay, cancellation bursts, retreat in price levels and spread changes. Normalize comparisons for pressure size, initial depth, volatility, time of day and material news. Track bid and ask separately.

Useful candidate changes include longer recovery time, less replenishment per unit consumed, a rising cancellation-to-addition ratio, more levels traversed for comparable aggression and growing response asymmetry. No future quote lifetime is allowed in an as-of feature. An order that has not yet cancelled is censored, not assigned the lifetime eventually observed.

### A mechanistic proof of information loss

We executed a constructed reservoir example. Two histories have the same price change, four unit fills, four unit refills and ending depth of two units. In one, replenishment takes one time unit; in the other, eight. A subsequent burst at times 0, 2 and 4 breaches the slow reservoir once and the fast one zero times. Sparse future hits at 0, 10 and 20 breach neither.

This is not a backtest or a calibrated market model. It proves the narrower, useful point: **aggregate volumes and an identical current snapshot can conceal different responses to the same specified future challenge.** Recovery timing supplies information those summaries discard, conditional on behavior remaining stable.

### What is truly sequence-sensitive?

A sum of past signed flow is not order-sensitive within its window. One proposed algebraic measurement is

`A_t = sum_j [ C_(j-1) * DeltaR_j - R_(j-1) * DeltaC_j ]`,

where C and R are cumulative consumption and replenishment. Consuming one unit then replenishing one produces +1; the reversed order produces −1, despite identical totals. This cross-sum is an original candidate application, not a claimed invention of order-sensitive mathematics. Weight recent events and stratify by pressure scale only under a frozen specification.

The research target is the hazard of **observable defense failure within the next specified pressure episode**, not hidden remaining inventory. Compare with current depth, spread, total flow, realized volatility, elapsed time and a matched-event baseline. A within-window event-order permutation should preserve totals while destroying timing information. Also test perturbations that preserve intraday seasonality and burst-size distributions; a naive global shuffle is too easy a null.

**Falsifier:** no forward gain after matching pressure and liquidity, effect disappears with quote-age/sequence cleaning, or future disturbance timing rather than recovery behavior explains the result. No conclusion about institutions follows even from a positive hazard forecast.

## 4. Pattern B — the opposition-withdrawal test

### Original proposal

The potentially informative transition may not be “buying increased,” but **“the force previously preventing movement weakened.”** Price is the outcome of competing pressures. A moderate new bid can matter much more after persistent supply has withdrawn than during the middle of a crowded buying wave.

A bullish candidate sequence is: sustained sell pressure; unexpectedly limited downside relative to comparable episodes; replenishing bids; a causally detected decline in selling; survival of the defended area through that pause; then upward movement requiring less aggressive buying than previously. A bearish candidate is the mirror, with apparent strength maintained by buying until bids weaken or the buyer stops.

Do not conflate these: heavy aggressive buying resisted by a replenishing ask is evidence of **resistance to buying**, not a bullish accumulation certificate. Heavy selling resisted by bids is potential absorption, but the bids can still fail.

Define a quiet-period stopping rule from trailing intensity and volume-time behavior, trained before evaluation. The decision timestamp occurs only after the qualifying pause is observed. Never timestamp the signal at the last trade of a program whose end becomes knowable only later. Incomplete episodes remain censored.

Measure the post-pause path against three rivals: residual aggressive flow, ordinary impact relaxation and independent information/events. Separate outcomes: continuation in the old aggressive direction; reversal; continued balance; and insufficient/censored observation. Low volume during a pause increases measurement uncertainty; it is not proof that opposition vanished.

**Falsifier:** the entire apparent edge is already captured by a price reversal/momentum baseline at the same decision time, or vanishes after conditioning on continuing correlated flow and new information. More delayed confirmation is useful only if it materially reduces false alarms while retaining actionable lead.

## 5. Pattern C — anonymous order-program ensembles without imaginary investors

### Practical breakthrough and original extension

Use anonymous trades to study **statistical execution patterns** without insisting on a single, false institutional identity. The 2025 synthetic-metaorder method creates plausible aggregate research populations, not actual investor assignments. [S1]

Our extension is to retain a small frozen set of admissible reconstructions and ask which observable predictions survive their disagreement. Each reconstruction groups events differently; it can imply a different current same-sign program duration, participation or cumulative pressure. Agreement is robustness to those assumptions, not a posterior probability that an institution exists.

The published offline algorithm uses whole-day quantities and completed program endpoints. Those are acceptable for retrospective measurement but cannot simply be carried into a live predictive feature. Our research prototype therefore uses only events already received, fixed mapping parameters, stable event identifiers and a prefix-only summary. No current-day final volume, final volatility, final duration, last child order or future profitability chooses an assignment.

The standard-library prototype includes three bucket counts and eight seeds, solely for a twenty-four-world sensitivity exercise. The mapping is deliberately synthetic. At each prefix, it tracks current same-sign runs; their final ends remain unknown. Prefix-invariance tests verify that appending future trades cannot change already emitted summaries. None of these checks establishes the original paper's empirical impact results or any financial advantage.

A useful prediction target would be the next sign/intensity distribution or subsequent impact conditional on comparable liquidity. Then ask separately whether that forecast improves future returns, defense hazards or trade-cost-aware timing. Predictable execution signs can coexist with efficient prices.

**Falsifier:** only one arbitrary mapping works, assignment parameters selected on the test period determine the result, or shuffled/price-only controls perform as well. A successful recovery of an average square-root impact pattern is not a successful accumulation signal.

## 6. Pattern D — pressure disagreement across event types and size scales

### Original proposal

A single signed-volume number can erase disagreement between numerous small events, a few large events, replenishment and cancellations. Preserve a small **pressure spectrum**, then condition it on actual subsequent response.

For trades with inferred sign epsilon and size v, compare

`I_a = sum(epsilon * v^a) / sum(v^a)`, for frozen a in {0, 0.5, 1}.

These are count, square-root-size and volume imbalance. They are not “retail,” “algorithmic” and “institutional” labels. One hundred one-share buys and one hundred-share sell have net volume imbalance zero, count imbalance approximately +0.98 and root-size imbalance approximately +0.82. Our constructed test verifies this arithmetic. Fragmentation, reporting conventions or deliberate slicing can explain it without any informational edge.

Add separate observable channels for limit additions, cancellations and queue retreat. A candidate distribution pattern is positive trade-count pressure combined with replenishing supply, weakening bid recovery and poor price response. A candidate accumulation pattern is negative trade pressure resisted by persistent bids, improving recovery and less downside response to comparable disturbances.

ClusterLOB motivates differentiating event behavior rather than treating all order flow as homogeneous. The proposed spectrum is a simpler, interpretable challenger, not a replication of its clustering result. [S2]

**Falsifier:** advantages disappear after controlling venue, trade-condition eligibility, typical event size, spread and time of day; or depend on fragile inferred signs. Unknown aggressor direction must be preserved or integrated over plausible assignments, not force-filled with a confident sign.

## 7. Pattern E — mechanical-pressure resistance and two different propagation graphs

### Original proposal

Instead of asking “where is money flowing?” ask **“what should have been forced to move, and what conspicuously did not?”** Predicted fund/index pressure can supply a conditional benchmark against which unusual resilience is measured.

A research-only pressure estimate might combine previously known holdings/weights, a measured or preannounced flow shock, and a liquidity scale. A negative expected demand disturbance paired with unexpectedly strong relative response is a candidate for countervailing demand. It could also reflect incorrect weights, in-kind transfers, prepositioning, cash buffers or new fundamentals; it is not evidence of a named buyer.

Coval and Stafford document flow-related pressure on commonly held securities in historical mutual-fund data. That provides mechanism evidence, not today's exact forecast coefficient or a guarantee that every fund sells proportionally. [S11]

Maintain two conceptually distinct graphs **inside the existing graph owners**:

- A co-ownership/constraint graph: positions likely to be affected by the same investors, index rules or portfolio constraints.
- An economic graph: supplier/customer, substitution, capex and bottleneck relationships supported by dated evidence.

If unrelated companies co-move immediately along a shared-owner graph, a mechanical demand shock is a plausible explanation. If a response follows dated customer or supplier news along economically relevant edges, delayed fundamental transmission is another. The same event can activate both. Lag is evidence to compare, not proof of causality.

Measure neighbor residual response, transfer direction and the order in which affected nodes change. Compare real edges with degree-preserving rewired edges, reversed economic edges and factor/industry controls. Do not infer dollar conservation between sector returns: market capitalization changes and trade values do not reveal the same investors transferring money.

A July 2026 demand-system critique is directly relevant: absorbing a supply shock can change dynamic risk and the demand relation itself. Consequently, we should predict **conditional resistance**, while labeling structural demand-slope estimates as assumption-dependent. [S6]

**Falsifier:** the signal vanishes with genuinely dated holdings/membership, placebo networks behave similarly, or responses are explained by common factors and news. Known future delistings must not be used to prune historical observations; retain exits and handle missing outcomes honestly.

## 8. Pattern F — event-response fingerprints, not generic down-day strength

### Original proposal

The same negative return can mean different things after different news. Define what a stock was exposed to **before** an event, estimate its normal response to that shock, and measure persistent deviations across comparable events.

Examples are a supplier unusually resilient to a customer's capex disappointment, a rate-sensitive group ceasing to respond negatively to rate surprises, or a prior leader failing repeatedly to benefit from favorable sector news. These are hypotheses, not claims about a current company.

Unlike the prior daily downside-resilience feature, this needs a source-backed event, pre-event exposure, surprise direction/magnitude and precise available-at time. Price-neutral news classification is frozen before examining the response. Event significance cannot be assigned using the subsequent stock move.

Construct an observable response fingerprint across several challenge types. Gradual changes in that fingerprint may be more informative than a high current relative-strength rank. Cross-event agreement should be discounted when all events express the same underlying risk factor.

The first use is evidence prioritization: “This name no longer reacts as its previously measured exposure predicts; investigate why.” Only a subsequent out-of-sample event study could support a pivot probability.

**Falsifier:** hindsight exposure, changing surprise distributions, omission of concurrent information or selection of convenient events explains the anomaly. A failure to fall is not automatically hidden accumulation; the market may already have discounted the event.

## 9. Pattern G — overnight/intraday cancellation: tested rather than merely proposed

### Why test it?

Close-to-close log return equals overnight plus intraday log return. The mapping `(O,D) -> O+D` loses the contrast `(O-D)`. An −80-basis-point overnight move followed by +80 intraday is indistinguishable in the daily net from the opposite sequence. Those are not identical observations once opens are available.

The general decomposition has precedent. Lou, Polk and Skouras discuss persistent components and cross-period reversal; Akbas and coauthors test a different overnight-reversal frequency measure, and international evidence is mixed. This follow-up does **not** claim to invent the decomposition or replicate those published tests. [S7–S9]

Our original candidate asks whether sizeable opposing residual components and a recent change in their balance add information after a strong close-based baseline.

### Actual LP-NOVEL-02 experiment

We inspected existing normalized Tiingo snapshots and chose ACN and AMAT, with SPY as benchmark, from a bounded metadata census before inspecting outcomes. These are two convenient long-history names, not a representative stock universe or an institution-level test. No data purchase or vendor call was made.

The source records explicitly retain `source_rights_admitted=false`, `dataos_identity_admitted=false` and `pit_backtest_eligible=false`. Their adjustment description is later-vintage vendor data. The experiment is an exploratory feasibility calculation under the existing research assignment and previously stated Tiingo rights, **not a Data OS admission, rights adjudication or point-in-time acceptance**. No flags or rights were changed, and reconstructive series remain private.

Data span 2005–2025; training begins in 2006. Annual expanding fits are evaluated in 2018–2022 and 2023–2025. At session t close, the target is positive stock-versus-SPY log return from the next session's open through the fifth later session's close. Training labels end before each test year. Fixed ridge, train-only standardization and a common complete-case panel are used. The protocol and source were committed before new outcomes. The old ETF test was not rerun.

The baseline includes price/relative momentum, trend, volatility, conventional volume, lagged beta, market context and ticker identity. The first addition decomposes lagged-beta-adjusted overnight/intraday performance over five and twenty sessions. The second adds opposing-component mass and a five-session balance-change interaction. These remain coarse daily proxies, not quote-level event sequences.

**Results: 4,012 total predictions; 1,494 evaluation predictions over 747 dates.**

| Model | 2023–2025 Brier, lower better | AUC |
|---|---:|---:|
| Per-ticker historical constant | 0.252256 | 0.4614 |
| Close/volume/market baseline | 0.255788 | 0.4577 |
| Baseline + session components | 0.256717 | 0.4470 |
| Above + cancellation/balance interaction | 0.256986 | 0.4434 |

The combined addition's mean Brier gain is **−0.001199**, with a 60-date block-bootstrap interval **[−0.002157,−0.000309]** and Holm-adjusted p approximately **0.022**. Both candidate arms are numerically worse in every evaluation year and in each of the two names. Development results do not supply a compensating positive finding. None passes the frozen positive-gain gate.

The component-only interval slightly crosses zero while its centered-bootstrap p is near 0.046; those are different finite-bootstrap summaries, not permission to cherry-pick stronger harm language. The decision does not depend on that boundary: neither candidate demonstrates benefit. No claim of universal absence of information follows from two convenience names and unqualified historical vintages.

A descriptive observation does survive: **239 of 1,494 evaluation windows (about 16%)** show at least 80% cancellation between opposing twenty-session residual components with gross magnitude at least 2 log-percent. These are overlapping stock-date windows—not 239 independent hidden institutional positions. Cancellation is observable; **our attempt to turn it into a five-session directional forecast failed**.

Checks include actual open/close return decomposition, equal within-day raw/adjusted price multipliers, prefix invariance, duplicate-date checks, strict training-label purging and stable input hashes. They do not qualify every historical corporate action, source right or original-availability clock.

### Decision

Keep the decomposition as a diagnostic; do not promote this predictive implementation. Do not optimize its windows on these results. A genuinely different future experiment would need a justified event-conditioned or cross-sectional population, independent evaluation and qualified data—not a cosmetic renamed score. The NY Fed's 2026 disappearing-drift evidence strengthens the case against fixed-clock folklore, not against all session research. [S10]

## 10. Pattern H — robust hypotheses and the next discriminating observation

### Original proposal

Retain competing explanations explicitly and choose the next **read-only observation** that most separates them. Do not collapse ambiguity into a single “accumulation confidence.”

For a stock resisting selling, plausible explanations include persistent countervailing demand, transient market-making capacity, offsetting information, mechanical basket arbitrage or bad coverage. The most informative next observation may be another comparable sell challenge, a quote-recovery measurement, the response after forced flow ends, or a source-backed event—not an additional momentum indicator.

A research posterior or likelihood ratio can be updated only when the corresponding model has been specified and calibrated. Until then, report scenario compatibility and falsifiers. Across plausible trade-sign assignments, impact scales, venue omissions and proxy-program mappings, require the forecast to be robust enough for its intended action. A range across scenarios is **not** automatically a statistical confidence interval.

This turns “unknown” into a useful research state: explain exactly what cannot yet be distinguished and which observed event would discriminate. There is no need for a second watcher, database or decision lifecycle; existing evidence/episode and replay owners can retain the relevant records.

### Options extension: test the hedging explanation rather than assume the dealer book

An additional original proposal is a **hedging-explanation envelope**. Under explicitly stated, finite scenarios for dealer positions, participation in hedging, instrument substitution and available option sensitivities, calculate a range of stock-pressure paths that mechanical hedging could explain. Compare the observed pressure and price response with that range. Do not present a selected scenario as the actual dealer inventory.

If every plausible scenario accommodates the observation, the options evidence does not distinguish informed accumulation from hedging. If none does, the result is only “these modeled hedge explanations are inadequate”: missing positions, futures/ETF substitution and model error remain rivals. This is a model-checking device, not proof of informed direction. The envelope may be so wide that it is useless; that is a valid rejection of the proposed measurement at the available data resolution. No options envelope was empirically tested in this follow-up.

## 11. A decisive next experiment, rather than an open-ended model search

### Research target

**Does the ordered recovery history improve the predicted response to the next naturally occurring pressure episode, beyond the current book snapshot, recent flow and price baselines?**

This is materially different from predicting a twenty-day ETF relative return using transformed daily bars. It directly tests information lost by aggregation.

### Smallest credible vertical

Use an already authorized source with eligible trades, explicit or uncertain aggressor direction, ordered book updates and sequence-gap detection. First prove the exact fields and venue scope on a bounded sample. A source lacking additions/cancellations cannot test quote recovery; a one-venue archive cannot claim consolidated-market inference. Current archive existence is not decoder/coverage proof.

Freeze a modest liquid-stock cohort and a calendar split before fitting. Engineering quantities below are proposed research choices, not a claim that the necessary sample is already qualified. Start with two source-qualification sessions; only then run a preregistered multiweek, multistock study with an untouched later segment. Do not buy a new premium feed merely because a paper used it.

Compare four nested arms on identical decision times:

1. Current spread/depth, recent returns/volatility, time of day and market context.
2. Those controls plus conventional signed trade/book imbalance.
3. Those controls plus response-recovery order, fatigue and observed pause survival.
4. The previous arm plus the fixed anonymous-program/size-spectrum robustness features.

Choose one primary target, such as a defined defended-level failure before recovery over the next event horizon, with a fixed maximum clock horizon and explicit censoring. Forward mid-price and cost-aware returns are separate secondary targets. Do not grade only episodes that eventually break.

Evaluation must include ordinary competing outcomes, no-shock intervals, false alerts, action delay, spread costs, quote staleness and missingness. Use whole-day/date-grouped splits across names; purge overlapping outcome windows. Compare lead time at the **same false-alarm budget**, not by counting more early alerts. Evaluate both sides and report a coverage/abstention curve.

Negative controls: within-regime event-order permutations preserving totals, lagged/shifted signing, plausible signing-error perturbations, reversed economic edges, and candidate features constructed from already shuffled inputs. Keep the perturbation family and all hyperparameters fixed before the final test.

A pilot pass can justify a larger replication, not production. If recovery history has no additional forward value, retain descriptive measures and stop promotion. If it works only for instantaneous impact, do not claim swing timing. If apparent gains disappear after sequence-quality filtering or realistic delay, classify the operational edge as absent.

## 12. Integration and decisions

The most useful user-facing result would be an **explainable vulnerability/response assessment**: observed pressure, which side resists, whether resistance is strengthening or tiring, what happened after pressure weakened, how sensitive the inference is to missing data, and the next falsifier.

The same evidence can support Prophet timing research, Sector/Theme investigation, Options interpretation and Risk Radar without each recomputing a contradictory score. No new production schema is installed here. Existing source owners, Market Memory/replay and the `rotation_calls.v1` identification-to-consumption seam remain controlling. The new research cannot upgrade EARLY/TURNING/CONFIRMED, rank opportunities or size positions on its own.

| Direction | Decision now | What would change the decision |
|---|---|---|
| Ordered recovery/fatigue and pause survival | GO for a bounded source-qualified prototype | Forward value at matched alert rates across names/days after delay and data-quality controls |
| Anonymous-program ensembles | GO for research measurement and robustness tests | Benefit beyond aggregate imbalance without future endpoints or arbitrary-mapping dependence |
| Mechanical-pressure resistance and two graphs | CONDITIONAL | Dated holdings/edges, defensible shock controls and success over placebo graphs |
| Source-backed event-response fingerprints | CONDITIONAL | Pre-event exposures, surprise-time integrity and independent-event transfer |
| Session-cancellation directional pilot | NO-GO for this implementation | A materially different justified experiment and new evaluation, not retuning the failed run |
| Unique institutional inventory from anonymous prints | Not supported by these observations | An actual identifying dataset or explicit defensible restrictions; rhetoric is not identification |

**The strongest next hypothesis is: the direction of the next meaningful move is partly encoded in how one side's resistance changes under repeated pressure and after that pressure pauses—not merely in the amount of current activity.** This is plausible, testable and supported by the information-loss counterexamples, but its market forecast value remains unproven. The completed follow-up narrows the problem to a more informative observation process instead of claiming an invented alpha breakthrough.

## 13. Verification, review and reproducibility

LP-NOVEL-02 protocol commit: `571b5619c329c9aeba09de50c501c55b4758be21`. Source freeze: `5a1f4a7c2722d981c91a29f75bf034048c2826ac`. `SESSION_PILOT_RESULTS.json` contains exact safe aggregates, hashes and fit boundaries. The full date-level forecast series remains in ignored `private_results/`.

The local standard-library `mechanistic_tests.py` has nine passing tests for exact counterexamples, order sensitivity, parameter bounds, input validity and prefix behavior. Constructed outputs are not market data or statistical evidence of profit. `prototype_checks.py` in the repository preserves a compact independently executable set of the same critical invariants.

The admitted external audit `lp-novel-identifiability-r1` returned useful additive/scale equivalence and opposite post-pause counterexamples, but **was not accepted as a complete review**. Its proposed sum-of-flows statistic was falsely called order-sensitive; its suggestion to exclude future delistings would introduce selection bias; and its in-kind-flow shortcut was unsupported. The principal rejected those recommendations and checked the corrected mathematics directly. Uncorrelated noise is also insufficient to identify a realized latent path. No reviewer approval of market alpha is asserted.

All research children are terminal. The work remains on the original PR #1470 and root `latent-pressure-research-20261014-chatgpt4-001`. No new data purchase, production change, order submission, live watcher or autonomous trading action was made.

## Primary source register

Accessed October 14–15, 2026. Primary-source research is distinct from the original proposals and our own experiments. Abstract-only readings are labeled. No source study was independently replicated here.

- **S1.** Maitrier, Loeper & Bouchaud (2025), *Generating realistic metaorders from public data*, arXiv:2503.18199v2, April 5 version. Full HTML. https://arxiv.org/html/2503.18199v2
- **S2.** Zhang, Cucuringu, Shestopaloff & Zohren (2025), *ClusterLOB: Enhancing Trading Strategies by Clustering Orders in Limit Order Books*, arXiv:2504.20349v2. Full HTML. https://arxiv.org/html/2504.20349v2
- **S3.** Zotikov & Antonov (2019 preprint; 2021 journal publication), *CME Iceberg Order Detection and Prediction*. Primary abstract; no new numerical accuracy claim. https://arxiv.org/abs/1909.09495
- **S4.** Brokmann, Serie, Kockelkoren & Bouchaud (2014), *Slow decay of impact in equity markets*, arXiv:1407.3390. Primary abstract. https://arxiv.org/abs/1407.3390
- **S5.** Bucci, Benzaquen, Lillo & Bouchaud (2019 preprint), *Slow decay of impact in equity markets: insights from the ANcerno database*, arXiv:1901.05332. Primary abstract. https://arxiv.org/abs/1901.05332
- **S6.** He, Kondor & Li (2025, revised July 2026), *Demand Elasticity in Dynamic Asset Pricing*, NBER 34450. Primary abstract/record. https://www.nber.org/papers/w34450
- **S7.** Lou, Polk & Skouras (2019), *A tug of war: Overnight versus intraday expected returns*, JFE 134(1), 192–213. Primary abstract/introduction. https://doi.org/10.1016/j.jfineco.2019.03.011
- **S8.** Akbas, Boehmer, Jiang & Koch (2022), *Overnight returns, daytime reversals, and future stock returns*, JFE 145(3), 850–875. Primary abstract. https://doi.org/10.1016/j.jfineco.2021.09.019
- **S9.** Hajiyev, Keiber & Luczak (2024), *Tug of war with noise traders? Evidence from the G7 stock markets*, QREF 95, 234–243. Primary abstract. https://doi.org/10.1016/j.qref.2024.03.011
- **S10.** New York Fed original-author research discussion, July 1, 2026, *The Disappearing Overnight Drift*. Full official article. https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
- **S11.** Coval & Stafford (2005 NBER; 2007 JFE), *Asset Fire Sales (and Purchases) in Equity Markets*, NBER 11357. Primary abstract/record. https://www.nber.org/papers/w11357
- **S12.** Donier, Bonart, Mastromatteo & Bouchaud (2014 preprint), *A fully consistent, minimal model for non-linear market impact*, arXiv:1412.0141. Theory, not alpha validation. https://arxiv.org/abs/1412.0141
