# Prophet Global Upgrade — research pass 02

**Date:** 2026-09-16. **Owner:** Sol, under the Chairman's current cross-market upgrade instruction.
**Status:** RESEARCH / DIAGNOSTIC EVIDENCE / PROPOSED DESIGN. Not architecture freeze, model promotion, deployment, or investment-performance acceptance.
**Operation:** `prophet-global-upgrade-research-20260916-sol-001`.
**Macro implementation/data pin:** `11485597cc53b3137346084aae4623cceed28a3f`.
**Protected Mastermind/Skillpack pin:** `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, Skillpack 1.0.1 / bootstrap major 1.

This artifact coordinates research across the existing Prophet owners. It creates no new workstream registry, lifecycle, grader, rank authority, identity spine, or publication plane. Macro `agentos/` remains organizational authority; this directory is a research artifact, not an Agent OS mirror. Existing market workstreams and live champions are unchanged.

## 1. Outcome and scope

The user job is to receive a small, useful daily set of stock opportunities with a clear answer to: what is attractive, why now, whether entry is valid, what can go wrong, and what would invalidate it. The intelligence job is to search the investable population, identify the applicable alpha mechanism, distinguish market/sector exposure from company-specific opportunity, forecast upside and downside separately, and abstain when evidence is insufficient. The moat is the combination of market-native sensing, exact timing/identity, useful selection, risk-aware delivery, and honest prospective learning—not the number of models or feeds.

The 10/10 outcome remains a materially better Prophet across US, mainland China, HK and Canada, visible through the real product. This pass completes a bounded diagnosis and research design increment, not that parent delivery program. No guarantee of profitable daily buys, a particular win rate, or world-leading performance is made.

This pass read immutable production-artifact candidates and current source, decomposed published outcomes without changing their rules, executed an exact pure-function defect probe, reconciled original board fossils, reviewed primary research, and mapped collisions with ongoing repairs. It did not train a model, read the locked W3 comparative outcomes, run a nightly producer, or alter customer signals. Artifact freshness is reported as observed; repository bytes are not substituted for a fresh authenticated production-browser acceptance.

## 2. Corrected baseline: the four headline percentages describe different things

Source: four `site/factordata/*_track_ledger.json` files at the Macro pin. `evidence.json` records their SHA-256 hashes, counts, and untruncated state. `reproduce.py` checks these immutable inputs independently.

| Population | Artifact date | Matured rows | Origin dates / distinct names | Published or reconstructed win meaning | Diagnostic result |
|---|---|---:|---|---|---|
| US all recorded definitions | Sep 11 | 843 episodes | 29 / 642 | Positive modeled P&L | Published 50.8%; mean +0.11% |
| **US current-definition v3 subset** | Sep 11 | **209 episodes** | **8 / 181** | Positive modeled P&L; state `up` | **73 wins, 34.93%; mean P&L about -2.01%, SPY excess about -1.83%** |
| China v4 | Sep 14 | 159 episodes | 11 / 143 | Positive benchmark excess, 10-session ruler | Published 44.0%; mean excess -0.60%; positive rounded absolute P&L 32.7% |
| HK v2 | Sep 15 | 95 board-day rows | 9 / 33 | Positive benchmark excess, 21-session ruler | 42 beats / 53 lags, 44.2%; mean excess about -1.59% |
| Canada Branch B | Sep 11 | 0 matured 21-session rows | Not yet applicable | Positive benchmark excess, 21-session ruler | Lawfully accruing at this date; see maturity calculation |

Means derived from compact row fields use already-rounded published values and are labeled accordingly. The source headline uses its own unrounded upstream values. For US wins use the published `st == up` classification, not `p > 0` on rounded rows, which would turn tiny positive returns rounded to zero into false losses. These are modeled ledger outcomes, not fills executed in a user's brokerage account. Net transaction-cost performance has not been established by this pass.

### 2.1 The previous US headline is not the live-v3 efficacy estimate

The 843 matured US rows span five definitions:

| Definition | Matured episodes | Origin dates | Positive outcomes | Win rate | Mean P&L, rounded-row diagnostic |
|---|---:|---:|---:|---:|---:|
| bottoming-alignment | 174 | 8 | 101 | 58.05% | +0.303% |
| confluence | 280 | 9 | 179 | 63.93% | +2.374% |
| us_prophet_v1 | 68 | 1 | 39 | 57.35% | +1.778% |
| us_prophet_v2 | 112 | 3 | 36 | 32.14% | -2.885% |
| us_prophet_v3 | 209 | 8 | 73 | 34.93% | -2.014% |

The current-v3 matured origins run from August 17 through August 26. V3 exits in this subset are 162 horizon verdicts, 37 oscillator targets, and 10 stops. This motivates examining the interaction of selection, tape and holding policy; it does not prove which caused the loss.

**Do not infer that v3 caused deterioration or that reverting to an earlier era would restore its past win rate.** These are different historical periods, not matched same-date interventions. Eight dates with overlapping holdings are not 209 independent regime observations. The registered paired W3 race remains its own evidence owner, including its minimum-maturity restriction. No W3 comparative outcome was read here.

### 2.2 Preserve the actual fill and exit definitions

US `scripts/grade_us_board.py::emit_ledger` uses next-session close and the first of its oscillator target, 90-session-trough-based stop, or ten-session deadline. China uses the existing T+1 fill hierarchy and a ten-session forced verdict; latched fallback prices retain their provenance. HK/Canada use the next available close and 21 strictly forward sessions in `engine/grading.py::forward_metrics`.

A harmonized research comparison must retain these legacy records, distinguish gross absolute return from market/sector excess, and version any new prospective policy. It must not relabel one metric or silently rescore old records into the most flattering ruler.

The China `capture=-0.33` field is **not runner-discovery recall**. In `engine/track_scoring.py::summarize` it is the median ratio of realized absolute P&L to positive maximum favorable excursion. It says something about keeping a favorable price excursion, not whether the system found the universe's biggest future winners.

### 2.3 Canada: correct the earlier premature diagnosis

The first current-era signal is August 19. The canonical next-bar-close fill is August 20. Using TSX sessions and excluding Labour Day on September 7, only 15 forward sessions exist by the September 11 artifact. The earliest 21-session endpoint is **September 21, 2026**, assuming the instrument and reference calendar supply the requisite valid bars. Zero matured H21 rows is therefore expected in the inspected snapshot; it is not proof of a stalled grader. The TSX official calendar supplies the holiday.[R8]

Freshness and shorter-horizon coverage remain separate audit questions. The displayed `first_read_est` must not substitute for an actual calendar/grader calculation. The earlier chat's suggestion that zero matured rows by itself proved Canadian evaluation failure is withdrawn.

## 3. Two verified measurement hazards

### 3.1 Historical popup rank is not admission-time rank

`emit_ledger` constructs `meta_by_tk` from the latest board appearance of each ticker, then places that rank/tier on historical episodes. The board definition is separately keyed by admission date. Therefore a current popup can be legitimate display metadata but an invalid historical learning input.

I streamed the original `data/us_board_ledger/snapshots.jsonl`, bounded to 80 MB/500 records. Actual input: 57,157,509 bytes, 38 snapshots, SHA-256 `0b58bb38d292ec34737d2886134b1d32177493912171e35889ee4931c0b5fed4`. Original `buy[]` order was normalized exactly as the owner's `_board_to_record`: zero-based lane position, where rank zero is valid.

All 209 matured v3 episodes matched an origin snapshot. **149 had a popup rank different from their admission rank.** Sector values happened to agree for all 209; this does not turn latest sector metadata into a generally point-in-time contract. Examples on August 26: AEO popup 37 versus admission 21; AGCO 23 versus 34; AM 17 versus 36; BGC 4 versus 6.

Consequences: do not calculate historical Top-5 quality, train rankers, or assign admission-time tier from the popup's latest fields. Use the existing fossils and canonical episode/candidate keys. Also do not compute Top-5 only among newly originated episodes and call it the full daily board Top-5: continuing candidates and repeated board-day outcomes have a different grain.

### 3.2 HK/Canada suspension classification confuses insufficient history with suspension

The exact function at `engine/board_ledger.py:749-761` returns `len(close[close.index > fill_date]) < 5`. It does not inspect whether five exchange sessions have elapsed, whether observed values are finite, or how long the first subsequent print was delayed.

Three executions of the pinned pure function, without importing the producer:

| Input | Returned `suspended` | What the probe establishes |
|---|---|---|
| Fill followed by one healthy next-day print, evaluated immediately | True | Ordinary immature history can be classified as suspended |
| Fill followed a month later by five prints | False | The function does not implement the documented within-five-session deadline |
| Fill followed by five NaN rows | False | Row count alone does not validate prints; upstream loader behavior still needs separate review |

The current HK artifact flags 81 rows, exactly all rows from its last five origin dates. Canada flags 87 rows, again all rows from its last five origin dates. This is consistent with the time-window defect. It is not an independent confirmation of the true exchange-halt status of every flagged instrument.

Repair belongs inside the existing board-ledger/grading owner. Distinguish not-yet-matured, missing price/data gap, confirmed trading halt, delisting, unfillable signal and completed outcome. Preserve unresolved and adverse outcomes rather than manufacturing prices or discarding inconvenient losses. Fixing a false suspension label is measurement repair, not evidence of improved stock selection. No fix was applied here.

## 4. What is actually controlling selection

### 4.1 US: four-family unfitted vote, with important intelligence absent

The September 11 board names `us_prophet_v3`, 52 buy rows and 48 watch rows. Its own fusion receipt says: within-night oriented percentiles, mean within evidence family, equal mean across a name's present families. It is not a calibrated forecast and contains no learned context interaction.

Voting families: F1 technical confluence, F2 momentum/extension, F4 catalysts, F5 flow/positioning. Abstaining families: F3 theme, F6 macro, F7 fundamental quality, F8 attention. F6 is structurally excluded because a common macro value cannot order a cross-section by itself; the receipt explicitly reserves router/interaction use. F3 and F7 are absent from the relevant board representation; the attention member is constant. Thirty names have four voting families, twenty-two have three.

This is a direct answer to the regime-awareness complaint: a common risk label needs either stock-exposure interactions to change relative order, or a separate absolute-risk decision to change purchase permission. Simply adding the same regime points to every stock cannot distinguish them. Missing-family renormalization also changes the implicit mixture across names; coverage/uncertainty must be tested rather than mistaken for positive evidence.

The old five-leg US score is not today's live C1 formula. It remains important as a retired/shadow baseline and shared machinery used by HK; changing its constants globally is not an isolated US upgrade.

### 4.2 China: deterministic interest is not expected return

`engine/china_intel_interest.py::interest_score` uses signal core, falsifier penalty, remaining edge and leading-gap multiplier. This is useful structured evidence, but its 0–100 result is not a probability of profit. The existing China separation of Reality, Professional Belief, Market Recognition and Prophet/Path should survive. The upgrade should test which evidence adds predictive information conditional on path, sector, recognition and market state—not reward the mere presence of more narratives.

### 4.3 HK and Canada already contain contextual machinery

HK `engine/hk_stock_signals.py` already has a hand-set regime switch over Southbound, A/H valuation, beta-neutral relative strength and regime fit. For example, the risk-off row is 0.34/0.32/0.10/0.24 and risk-on is 0.26/0.18/0.36/0.20. It is explicitly a screen, not a validated learned alpha blend. Thus “HK has no regime awareness at all” was too broad. The correct comparison is a challenger versus that actual conditional baseline.

Canada has macro/commodity overlays and a deliberately honest Branch-B screen, `official_pick_authority=false`. Its next step is not borrowing US weights or declaring the screen a proven alpha ranker.

The HK/Canada board-ledger source documents absent point-in-time own-market regime stamps because historical local labels were rebuilt from latest state. That is an explicit training-data limitation, not neutral regime evidence. Audit actual availability clocks before any historical global-to-local joins; a same-calendar-date US close must not leak into an earlier HK decision.

## 5. Discovery, timing and conversion need different experiments

The existing September 14 miss audit chooses the prior 63-session top 150 runners retrospectively. It reports 26 never eligible, 124 sighted at least once, only 21 of those 124 represented in the plan universe, and a median six eligible days out of 63. Today only four are stream-eligible, while 143 carry a not-topped veto.

These numbers justify a failure-attribution investigation, **not deletion of those 143 vetoes**. A stock being overextended after a large move can be a correct refusal. The audit's eligibility-stream basis is not identical to its stricter universe-today basis or the complete live board gate. The price-through and board cutoffs also differ. True runner recall must be measured at the first actionable point before the subsequent move, with outcomes hidden from nomination logic.

The full-population evaluation report carries 18,816 grade rows across only eleven stamp dates. Only 709 have the incumbent priority score; off-board null scores are not zero scores. All 18,816 rows lack the curated/scan cohort in that report, so it cannot support a claimed cohort-specific result. Raw feature coverage may still support properly registered alternative models; lack of an old score is not a reason to discard the population.

The zero basket-miss count is also non-informative here: zero baskets met its top-decile activation condition, although nineteen of forty-nine were unrepresented. Never turn a zero with no qualifying opportunities into a perfect detection claim.

The candidate funnel to reconstruct is: eligible investable universe; expert nomination; lawful data/time eligibility; timing/admission; rank; entry availability; actual publication; plan origination; fill; exit. Every exclusion needs its original reason, context and observable consequence. New candidate nomination does not itself acquire buy authority.

## 6. Primary research and transfer limits

These are research priors, not demonstrations that a proposed Prophet model works.

| Source | Useful result or method | Proposed consequence and explicit limit |
|---|---|---|
| Gu, Kelly & Xiu, RFS 2020 [R1] | Comparative empirical asset-pricing study; nonlinear interactions help trees and neural nets. Full paper uses a long US monthly panel with characteristics, macro interactions and industry information. | Race regularized interactions and shallow boosted trees. Monthly US evidence does not prove daily swing alpha or transport to HK/China/Canada. More depth is not a default improvement. |
| Moskowitz & Grinblatt, JF 1999 [R2] | Industry momentum explains a substantial part of intermediate-horizon stock momentum. | Separate sector opportunity from within-sector selection. A 6–12-month result does not establish a short-horizon entry rule. |
| Asness, Porter & Stevens, working paper 2000 [R3] | Decomposes within-industry and across-industry characteristics; their short-horizon effects can differ. | Test both components rather than subtracting all sector return and discarding rotation alpha. Historical US study is not a market-wide authorization. |
| Daniel & Moskowitz, JFE 2016 [R4] | Momentum crash behavior depends on adverse market states and rebounds. | Test state-by-expert interactions and recovery transitions. Long-short strategy crash evidence is not a blanket ban on all long candidates during weak markets. |
| DeMiguel, Martin-Utrera & Uppal, JF 2024 [R5] | Cost-aware multifactor allocation changes the conclusions drawn from simple volatility-managed factor strategies. | Keep selection and exposure policy separate; compare net performance. Portfolio-allocation results do not prove single-stock ranking. |
| Gibbs & Candes, JMLR 2024 [R6] | Adaptive online conformal inference addresses shifting predictive distributions. | Research calibrated uncertainty/abstention with delayed stock labels. Coverage control is not a profit guarantee or automatically a conditional probability for every ticker. |
| Bailey & Lopez de Prado, JPM 2014 [R7] | Deflated Sharpe ratio addresses selection bias, multiple trials and non-normality. | Count experiments across all agents, not just the winning run. DSR does not repair leakage, execution errors or an invalid denominator. |
| Liu, Luo, Wang & Zhang, January 2026 preprint [R9] | Uncertainty-adjusted prediction-bound sorting rather than point predictions alone. | Exploratory challenger to confidence-blind ranking; not production-ready proof. Test the trade-off between avoiding uncertain losers and missing early runners. |
| Lin, Su & Yang, May 2026 preprint [R10] | LambdaRankIC directly targets full cross-sectional rank correlation. | Optional later objective comparison; Prophet needs top-K, tail-risk and runner capture, not merely full-order IC. Do not replace the ordinary ranker baseline with this by default. |

The stronger near-term choice is a **small conditional model race**, not immediate commitment to the most complicated architecture. Contextual routing remains the full-scale vision; its first useful implementation can be explicit, regularized interactions rather than a large neural gate.

## 7. Proposed algorithm and engine upgrade architecture

Three alternatives were considered. Four independent country stacks allow specialization but duplicate controls and fragment evidence. One global black-box ranker maximizes pooling but can confuse market mechanics, data coverage and economic meaning. The preferred design is **shared contracts and evaluation, with market-native experts and controlled partial pooling**. Existing owners implement the parts; no new all-powerful master score is introduced.

### 7.1 Wide nomination, independent buyability

Extend existing candidate and expert-event planes so continuation, pullback, reversal, catalyst, sector-rotation and idiosyncratic-strength experts can nominate into a measurable research population. Preserve each expert's identity and refusal history. The current confluence cascade becomes an explicit baseline/expert in a tested challenger, not something silently removed.

The user should see a compact actionable shortlist plus a distinct developing/opportunity view. A strong research candidate is not labeled “buy” until the existing timing/execution owner permits it. A weak market may still contain an unusual stock opportunity; it may also produce no net-positive buyable candidate. The system must support both outcomes without filling a quota.

### 7.2 Context is a vector, not one binary banner

Proposed contextual inputs: market trend and acceleration, cap-weighted versus equal-weight participation, breadth, volatility and its change, liquidity, rates/FX, dispersion, sector leadership and deterioration, crowding, and scheduled-event proximity. Reuse existing regime/sector owners and original decision-time vintages. No competing regime truth store.

Compare explicit stock-exposure-by-context interactions against the incumbent. Soft state probabilities and transition features are candidates, not guaranteed improvements. Hidden-state models must use causal filtered states at the decision time; retrospective smoothed states are prohibited in forecasts. Sparse market-state cells should shrink toward broader estimates rather than independently fit tiny samples.

### 7.3 Separate sector opportunity from stock-specific alpha

Estimate two complementary views: whether the sector/theme environment is favorable, and whether this stock is an attractive implementation relative to peers. Retain market/sector exposures so the system can distinguish a genuine stock-specific opportunity from high beta in a rally. Preserve useful sector rotation instead of neutralizing it away by construction.

A sector cap controls concentration; it does not perform this analysis. Similarly, SPY excess alone does not resolve hidden weakness in equal-weight breadth or sector composition. Benchmark checks should include the market, a contemporaneous sector reference, and predeclared size/volatility/exposure controls where data permit.

### 7.4 Race models in increasing complexity

The proposed sequence is incumbent and simpler repair baselines; regularized linear/logistic or generalized-additive interactions; shallow gradient-boosted return models plus date-grouped learning-to-rank; distinct return/upside/downside/path heads; and a soft mixture-of-experts only if it adds value over the best simpler survivor.

Reuse the existing Conditional Fusion C2–C5 arena and its admission/promotion rules. A new name for the same construction cannot bypass a data-depth gate. A justified new study requires a prospective registered question and authorized amendment, not after-the-fact threshold relaxation. Deep models remain an option when data, reproducibility and measured benefit justify them; they are neither the default nor permanently excluded.

Train decision outputs for different jobs: expected net absolute return; expected market/sector excess; probability and magnitude of a tradable runner; downside/stop or fragility; expected time-to-opportunity; confidence and coverage. A single 0–100 interest score cannot replace these. Candidate order is composed through the existing deterministic product/authority contract, not an LLM narrative.

### 7.5 Runner capture and avoiding losers are joint objectives

Define runner discovery prospectively at an actionable reference point and use the existing path grader to distinguish a clean expansion from a move requiring an intolerable drawdown or impossible fill. Selection, entry and exit policies must be separately ablated. Do not improve hit rate by taking tiny profits and retaining rare catastrophic losses, and do not improve displayed recall by surfacing stocks only after they ran.

Uncertainty can reduce trade size or support abstention only under the relevant tested policy. Keep a high-upside but uncertain watch cohort measurable so conservative ranking does not silently eliminate all early opportunities. Opportunity ranking can remain active even when purchase permission is withheld.

## 8. Market-native priorities

**US:** first repair the information path into selection, not the headline score alone. Build decision-time family/context coverage, broaden the shadow candidate intake through existing B1/Radar interfaces, and race conditional sector/breadth/volatility interactions against C1 and simple baselines. Add event/fundamental families only with usable decision-time evidence. Preserve the existing W3 restrictions and the active freshness/source-clock repairs.

**Mainland China:** preserve the four-model architecture, existing lawful timing and limit/fill behavior, and the v4 champion while testing an outcome-linked conditional replacement for interest ordering. Separate early fundamental/operational discovery from already-recognized attention, failed continuation and post-event exhaustion. Apply only source-supported features available through owned providers. Audit effective-dated trading mechanics: the SSE's April 24, 2026 notice changed main-board risk-warning price limits from 5% to 10% effective July 6.[R11] This is not a finding that Prophet currently has an ST-limit bug; it is a concrete reason rules cannot be copied from stale webpages or transported between exchanges without checking scope and dates.

**Hong Kong:** build on the existing `hk_discovery_v1` shadow population rather than adding a new discovery store. Compare the current hand-regime switch against conditional Southbound, A/H, global-risk exposure, local liquidity and sector-relative candidates. Flow presence and attention are not automatically a positive sign; preserve the house tests that rejected specific unconditional constructions. Repair the ledger's maturity/suspension distinction. Verify local/global availability timestamps before training.

**Canada:** keep Branch-B's screen disclosure until an alpha model earns authority. Test sector/name decomposition and company-specific exposure to commodity, rates and currency contexts using sufficiently granular sectors and businesses, rather than calling all energy or mining stocks the same trade. A Bank of Canada inventory-news study finds time-dependent oil-shock equity responses on a US equity sample, not a Canadian stock-selection guarantee.[R12] It supports shock/context distinctions as hypotheses only. H21 maturity is expected September 21 for the first inspected current-era cohort; investigate H5/H10 and historical point-in-time coverage meanwhile rather than waiting idly or inventing matured observations.

## 9. Experiment design and acceptance

Freeze the research unit before model outcomes: market, decision timestamp, canonical security/listing and episode identity, candidate-universe definition, selection/ranking version, feature-vintage bundle, fill convention, horizon, benchmark and costs. Keep publication and market-session clocks separate. Never replace missing inputs with current observations, or use today's sector membership/identity without a dated source.

There are four separable experiments. First, a same-pool ranking race prices incremental ordering value. Second, a discovery race prices new candidate recall with an unchanged evaluation rule. Third, an availability/entry race prices execution permission and false starts. Fourth, a hold/exit race measures retained upside and tail loss. Only then test the complete deployed composition. Otherwise one subsystem can be credited for another subsystem's change.

Use purged chronological folds, embargo aligned with overlapping label windows, fold-local transforms, truly unavailable-period exclusions, and date/episode-aware uncertainty. Record numbers of dates and unique names, not just rows. Compare matched data coverage and model complexity. Predeclare primary endpoints and multiplicity treatment. Do not add hand-picked regime slices after seeing where an arm won.

A deep price/technical history may support reconstructable core features sooner than a young intelligence tape. Audit survivorship, corporate actions, historical listing coverage and original observation clocks before using it. Young mutable intelligence snapshots remain forward-accrual-only. This permits useful progress without pretending that every lobe has ten years of lawful history.

Required outcome views: top-1/3/5/10 precision and net return; market and sector excess; large-winner recall before the move; large-loser rate and expected shortfall; adverse/favorable path excursions; fillability; turnover/cost sensitivity; confidence calibration; abstention coverage; and stability across predeclared market/sector states. The existing registered primary tuple remains controlling for its own race. Broader diagnostics are not a back door to promotion.

Acceptance sequence: exact-source data and mechanism proof; frozen shadow experiment; out-of-sample economic evidence; independent adversarial review; explicit owner promotion with a new version and reversible incumbent shadow; real production input through the serving path; browser proof of the user's shortlist/entry/risk journey. Research, CI, merge and production efficacy remain distinct. No numerical lift is promised before measurement.

## 10. Collision map and continuation

Observed open work at this pass, not accepted here:

| Existing carrier | Observed head | Scope preserved |
|---|---|---|
| Macro #7187 | `c21c9be04bbf983bc22f8e3fe6075339bbc9ebef` | US tracked-price cache and source-date recovery; draft |
| Macro #7180 | `99b9bc18ded963ed5e9b9a4864bfff88a8e1d5ba` | Completed-session clipping and exact-source-bound US picks |
| Macro #7174 | `effdbd13cb78f2da3770733e85f64c93d395eb0d` | Existing admin rotation diagnostics, research-only UI; draft/hold |
| Macro #7018 | `1c0a0434d9ec74df86339145eae75d5007a2df82` | Canada opportunity-map presentation, not new alpha authority; draft/hold |
| Macro #6871 / issue #6866 | `51ddb898ff0c130910f9f3f4266727905826a92d` | Existing China R0 safety replay; draft/request changes, original writer already started |

Do not duplicate or reassign the China R0 writer. Do not restart accepted US A1/B1 work. Do not alter live C1/v4 formulas, shared US/HK constants, canonical grades or old fossils based on this diagnostic. Do not claim current production merely from the repository snapshots. Fable is not the default for bounded data inventory; reserve principal orchestration for genuinely coupled implementation waves after research contracts are frozen.

**Exact next action:** recover and specify the point-in-time all-candidate failure-attribution dataset through existing Macro episode/candidate/fossil/grader owners, using this pass's source/time/metadata corrections. Produce a frozen loss-and-missed-runner casebook that assigns failures to discovery, ranking, availability, publication or exit without hindsight. Consume the active source-clock repairs by reference. In parallel, inventory the market-native data depth needed to select the first legal baseline/challenger race in each country. No model starts from an unverified summary table or an unconsumed worker handoff.

The next bounded proof is not another generic masterplan. It is a reproducible candidate-level attribution on original decision-time evidence, followed by the first frozen conditional ranking experiment that the data can actually support. This report is the current research continuation reference; runtime and organizational statuses were not changed.

## Sources and reproducibility

Internal source paths below resolve to Macro commit `11485597cc53b3137346084aae4623cceed28a3f`:

- [US ledger](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/site/factordata/us_track_ledger.json), [CN ledger](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/site/factordata/cn_track_ledger.json), [HK ledger](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/site/factordata/hk_track_ledger.json), [CA ledger](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/site/factordata/ca_track_ledger.json).
- [US ledger emitter and latest metadata](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/scripts/grade_us_board.py#L2565-L2756); [original board normalization](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/scripts/grade_us_board.py#L794-L910).
- [HK/CA suspension and grading](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/board_ledger.py#L749-L885); [next-close/horizon convention](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/grading.py#L166-L245); [capture meaning](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/track_scoring.py#L330-L425).
- [US C1 arithmetic](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/us_prophet_fusion.py#L592-L733); [HK regime switch](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/hk_stock_signals.py#L1-L84); [China interest score](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/engine/china_intel_interest.py#L284-L340).
- [Miss audit](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/data/prophet_miss_audit/latest.json); [Conditional Fusion owner](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md); [US V4 owner](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md); [HK/CA owner](https://github.com/mastermindx-market-intelligence/macro/blob/11485597cc53b3137346084aae4623cceed28a3f/agentos/workstreams/WS-PROPHET-HK-CA-REVAMP.md).

[R1]: https://dachxiu.chicagobooth.edu/download/ML.pdf "Gu, Kelly, Xiu: Empirical Asset Pricing via Machine Learning; RFS 2020. Full paper and Table 1 inspected."
[R2]: https://www.aqr.com/Insights/Research/Journal-Article/Do-Industries-Explain-Momentum "Moskowitz and Grinblatt; JF 1999. Author research summary."
[R3]: https://www.aqr.com/Insights/Research/Working-Paper/Predicting-Stock-Returns-Using-IndustryRelative-Firm-Characteristics "Asness, Porter, Stevens; 2000 working paper. Author research summary."
[R4]: https://www.nber.org/papers/w20439 "Daniel and Moskowitz: Momentum Crashes; NBER 2014, JFE 2016. Abstract."
[R5]: https://onlinelibrary.wiley.com/doi/10.1111/jofi.13395 "DeMiguel, Martin-Utrera, Uppal; A Multifactor Perspective on Volatility-Managed Portfolios; JF 2024. Full primary article inspected."
[R6]: https://jmlr.org/beta/papers/v25/22-1218.html "Gibbs and Candes; Conformal Inference for Online Prediction with Arbitrary Distribution Shifts; JMLR 2024. Abstract."
[R7]: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf "Bailey and Lopez de Prado; Deflated Sharpe Ratio; JPM 2014. Primary full paper and formula/example pages inspected."
[R8]: https://www.tsx.com/en/trading/calendars-and-trading-hours/calendar "Official 2026 TSX calendar; September 7 Labour Day."
[R9]: https://arxiv.org/abs/2601.00593 "Liu, Luo, Wang, Zhang; January 2026 preprint. Abstract only; exploratory."
[R10]: https://arxiv.org/abs/2605.00501 "Lin, Su, Yang; LambdaRankIC; May 2026 preprint. Abstract only; exploratory."
[R11]: https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml "SSE April 24, 2026 trading-rule notice; effective July 6, 2026."
[R12]: https://www.bankofcanada.ca/2020/03/staff-working-paper-2020-8/ "The Effect of Oil Price Shocks on Asset Markets: Evidence from Oil Inventory News; BoC 2020; US equity sample, not Canadian pick validation."

Reproduction: run `python reproduce.py --fossil-ranks` in this directory. It verifies immutable ledger hashes, current-v3 counts, exact suspension probes, the bounded TSX maturity calculation, and all 209 original-rank matches. It outputs JSON to stdout and writes no production data. Full original board fossils are read transiently and are not copied into this research directory. `evidence.json` is the measured research receipt, not a new state store.

Fresh-process verification is preserved in `verification.json`; it records the command, actual exit code, tested inputs, script hash and results. This is research reproducibility proof, not independent model validation or production acceptance.

## Continuation addendum — existing W2 linkage proposal recovered

Before closeout, a fresh read of Macro PR7174 identified its companion research carrier, **PR7168**, at `f2fc5e224799fff8c10eb3438867b176319bf74b`. Its [Rotation W2 clock-and-episode integration proposal](https://github.com/mastermindx-market-intelligence/macro/blob/f2fc5e224799fff8c10eb3438867b176319bf74b/research/prophet_us_audit/ROTATION_W2_CLOCK_AND_EPISODE_INTEGRATION_2026-09-16.md) is explicitly **proposed / NOT_BUILT**, not a production capability or new worker assignment.

That proposal already addresses exact candidate-episode -> plan -> private served-version binding. It distinguishes a plan's reference date, the public health receipt's preparation time, and actual authenticated serving observation. It rejects ticker/nearest-date conversion joins, invented midnight timestamps and using an unrelated closed plan as successful delivery. These are the same boundaries needed by this pass's failure-attribution work.

**Integration ruling for this research:** consume and reconcile the existing W2 proposal and its producer/publication owners before implementing any episode-to-plan or delivery-clock attribution. Do not create a competing linkage contract, plan ledger, publication receipt store or runtime. The current W1 implementation's release gates remain its owner's responsibility; this reference neither accepts nor expands it. Rank-at-admission must still come from the original fossils, not latest popup metadata.

The W2 proposal also identifies the existing Leadership Persistence research (PR7095/RPH-1), Temporal Grain, Technical Opportunity session-data, and Entry Radar owners. Treat those as coordination pointers, not acceptance claims. Market-grain comparisons must use compatible calendars and original information cutoffs; do not refit frozen RPH-1 choices after reading outcomes. This addendum changes only continuation routing. The empirical inputs, reproduction script and its verification receipt are unchanged.
