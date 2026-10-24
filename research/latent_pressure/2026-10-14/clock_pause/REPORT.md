# Clock-pause continuation: distinguish missing observations from market pressure

## Decision and capability delta

The next executed research test found an important measurement failure mode: **a quiet price-qualified subset often still contains other displayed execution activity**. It also showed how an apparently better combined forecast can improve prediction of future observations while worsening price-direction prediction. Neither should be advertised as latent accumulation.

The new historical reader makes this distinction explicitly. A separate censoring-aware library improves the already-built synthetic recovery prototype. Neither introduces live signals or reconstructs the unverified DEEP+ order book.

This work continues the original Latent Capital Flow research commission on Mastermind PR #1470. Prior failed experiments are preserved. The research-only boundary remains: no purchases, production schemas, source-rights changes, deployments, live alerts, ranks, sizing or trades.

## 1. What changed in the experiment

Earlier LP-EVENT-03A made predictions at qualifying execution events. That cannot, by itself, test information contained in the absence of an event between trades. Its future-print requirement also selected cases where enough later observations arrived.

**LP-CLOCK-04 changes the observation origin and estimand**, rather than retuning that failed model. It samples every thirty seconds from 10:00 to 15:30 New York on the existing October 5, 2026 capture. At each cutoff it uses only previously disseminated L records. Eligibility requires at least twenty prior flag-0 records since 09:45 and a most-recent reference no more than five minutes old. The future never decides whether an origin qualifies.

The already-qualified source contains 39,763 displayed-execution L records in eight selected securities. Their time, price, quantity, order reference and stored flag byte were previously checked. Only flag 0 enters the conservative price-feature/outcome subset. All L records can be counted as observed displayed executions without interpreting the meanings of the other flag values. No unknown add/modify/delete fields, resting-side bits or aggressor identities were decoded.

For each cutoff t, the future window is the fixed inclusive interval [t+60 seconds,t+120 seconds]. Its outcome is:

- **NO_STANDARD_OBSERVATION:** no flag-0 print occurs in the complete observed window.
- **DOWN / SAME / UP:** the median future flag-0 price is below/equal/above the median of the five most recent qualifying prints at t.

The first is an outcome about the data stream, not proof of an unchanged or unobserved underlying market price. If the capture itself is not known to cover the complete horizon, the implementation returns HORIZON_NOT_FULLY_OBSERVED instead of inventing silence. Medians and equality use integer arithmetic; prices and identifiers are not rounded through floats for class labels.

The two-part model estimates the probability of an observed future standard print and direction conditional on such an observation. These combine into four coherent probabilities. Log loss is checked to decompose exactly into availability loss plus the observed cases' conditional-direction loss. This prevents an improvement in observation prediction from being confused with directional advantage.

This construction has precedent in duration/transaction-time research; it is not a claim of worldwide novelty. Engle and Russell's work motivates modeling transaction arrivals separately, while later duration econometrics emphasizes the random observation count and nontrivial inference assumptions. Our contribution here is a bounded Mastermind experiment and explicit measurement/consumer safeguards, not replication of those published models. [S1–S2]

## 2. Frozen design and data limitations

Protocol commit: `60fd199e9`. Source/test freeze before the new empirical run: `d072e53e8`. Source input SHA-256: `d967e15a6148b96d155f733b64154c2256df07cfb3443c62c2df3be8ca54afe1`.

Training origins begin at 10:00 and have their entire outcome windows finish strictly before noon. Evaluation is 13:00–15:30 inclusive. The last endpoint belongs to the final half-hour uncertainty block rather than an artificial singleton block.

The baseline includes conventional recent print momentum/volatility/volume, ticker, clock, print age and both filtered and all-L activity counts. The candidate adds incomplete-gap age relative to completed-gap history, gap/rate changes, filtered/all-activity divergence interactions and repeated-order-reference features. All transformations are prefix-causal. Both use fixed ridge coefficients and train-only standardization; there is no post-result threshold or model tuning.

**The source day and afternoon were already used by this mission.** A newly frozen protocol is not a pristine holdout. There is only one calendar day, one venue and eight selected securities. Prices are qualifying execution prints, not NBBO midpoints or executable quotes. IEX source-send timestamps do not establish historical end-user receipt or achievable latency. No population significance, independent-day replication, cost-adjusted trading return or live forecast qualification is claimed.

## 3. Actual results

The new panel contains **1,511 training origins and 2,168 evaluation origins**. Of the evaluation windows, 867 contain no future standard observation; 565 are DOWN, 39 SAME and 697 UP. Thus only 1,301 have a conditional-direction outcome.

| Model | Four-class Brier, lower better | Availability Brier | Conditional-direction Brier | Direction accuracy |
|---|---:|---:|---:|---:|
| Training-frequency constant | **0.680540** | **0.247442** | **0.524033** | **53.57%** |
| Price/activity baseline | 0.701198 | 0.258445 | 0.551772 | 50.27% |
| Baseline + pause features | 0.695506 | 0.254438 | 0.553704 | 50.04% |

Relative to the richer baseline, the candidate improves joint Brier by **+0.005691**, but its conditional-direction gain is **−0.001931**. Its availability gain is +0.004007. **The attractive combined improvement does not establish better directional forecasting.** Furthermore, the simple training-frequency constant beats both learned models on these reported metrics, so this is not a claim that even the learned availability model is best available.

The descriptive thirty-minute-block intervals are [−0.000656,+0.011843] for joint gain and [−0.012608,+0.008189] for conditional-direction gain. There are only five blocks from one previously studied day. They are sensitivity summaries, not population confidence. Only MSFT, NVDA and SPY have positive directional point gains. The candidate fails the frozen joint-and-directional, cross-security gate. All forecast authority remains NONE.

No false-alarm/lead-time or profitable strategy claim is extracted from these results. Predicting whether the feed supplies a price observation is not predicting who is accumulating a security.

## 4. The strongest observed finding: filtered silence was usually not all-L inactivity

Of 2,168 eligible evaluation origins, **819** had no qualifying print for at least sixty seconds. At **737 of those origins (89.99%)**, other L records were nevertheless observed in the preceding minute. The exact-count check confirmed no sixty-second boundary equality cases and the same 737 cases when requiring all-L count to exceed standard count.

These are overlapping stock-clock observations under a chosen conservative filter. They are not independent market episodes, an estimate for all stocks/days, or proof that market-wide activity was quiet. The conclusion is narrower and directly useful: **do not infer withdrawal of selling or liquidity from silence in this filtered price stream**.

Even no L execution at all would not establish an empty order book, no hidden execution, no quote updates or no trading elsewhere. The observation process must be represented alongside any latent-pressure hypothesis.

## 5. A historical consumer now exposes the distinction

`clock_reader.py` uses the same qualified input and the same exact-prefix clock handling. It is a research CLI/read path, not a new production schema or competing rotation reader.

It distinguishes:

- STANDARD_SUBSET_ACTIVE.
- STANDARD_SUBSET_QUIET_OTHER_DISPLAYED_EXECUTIONS.
- NO_DISPLAYED_EXECUTION_RECORDS_IN_LAST60S.

Feature eligibility is separate. Even with insufficient standard-price history, the consumer can still report directly observed other L activity. A stale or sparse price reference does not erase that observation.

The actual 14:00 New York read produced eight records. MSFT, AMD, MU and XLV had zero flag-0 prints in the lookback but respectively 2,1,2 and12 other L execution records. Those are bounded historical observations, not present-market recommendations. The reader reports the last source time/sequence and record counts, while pressure direction, withdrawal of selling, quote recovery, institutional inventory and forecast probability remain null. All rotation-call, alert, rank and sizing permissions remain false.

This is the immediate verified product-research benefit: a downstream investigator can see why apparent silence does not justify an accumulation/withdrawal story.

## 6. Censoring-aware recovery measurement

The existing synthetic recovery engine already distinguishes recovery, displayed-level depletion, unresolved horizons and source-gap censoring. Its completed-recovery median is correctly labeled as such, but it cannot describe the full response population on its own.

The new `recovery_incidence.py` adds a descriptive competing-outcome calculation. At each observed duration u, with risk set n, it increments recovery incidence by S-before × recoveries/n and depletion incidence by S-before × depletions/n. Survival is multiplied by 1−(recoveries+depletions)/n. Tied events are processed before tied censoring. Pending responses contribute only the elapsed follow-up known at the cutoff.

For a constructed four-episode example—recoveries at1 and8, depletion at2 and censoring at3—the result at8 is recovery incidence0.75, depletion0.25, unresolved mass0. The completed-recovery median is4.5, but the recovery-incidence curve first reaches0.5 at8. These answer different questions. Treating depletion as ordinary censoring can also inflate recovery estimates: with recovery/depletion/recovery at1/2/3, recovery incidence is2/3, not1.

Sixteen focused tests verify exact rational-reference arithmetic, tied censoring, mass conservation, empty data, unfinished tails, side separation, future-state rejection, nonmutation and source-gap handling. All-censored data do not become a claim of zero future risk; no extrapolation beyond observed follow-up is returned.

These are **synthetic-cohort descriptive estimates under censoring assumptions**, not calibrated probabilities for the actual market. Source-gap censoring can be informative and episodes can be dependent. The full real DEEP+ adapter remains unchanged and refuses operation. No book fields were guessed to connect these calculations to real orders.

## 7. New timestamp defect found and repaired before this experiment

A one-nanosecond boundary fixture exposed a real search-type problem in the installed numerical environment. For an unsigned-64 timestamp array containing `1791208740000000000`, searching with the ordinary Python-integer query `1791208739999999999` using the right boundary returned index1, incorrectly including the later record. Searching with an explicitly matched unsigned-64 query returned the correct index0.

All new array-bound queries now use the matching integer type. Tests cover future-window endpoints, one-nanosecond exclusions, history/cutoff inclusion, incomplete gaps, source horizons, exact median ties and prefix invariance. Eighteen experiment tests and eleven reader tests pass, in addition to the sixteen incidence tests: **45 new focused tests**. Prior suites were not needlessly rerun or claimed as newly executed.

The older event-study helper uses the same untyped-search pattern. A proposed all-record impact audit of that older experiment was blocked before execution. **Its actual effect on the earlier labels is not known from this turn.** Original results are preserved with that qualification; no “zero impact” or successful requalification is fabricated. The new pipeline only reuses the helper's existing loader/names/clock and does not call its old feature/label search function.

## 8. Review, effect boundaries and unfinished work

A GLM design-review leaf, `lp-clock04-design-review`, was admitted through the existing M2 Fabric under the original root `latent-pressure-research-20261014-chatgpt4-001`. Its last successfully observed state was ACTIVE_OR_WAITING with no available result. A later compound call requesting its status/result and the legacy timestamp audit was explicitly blocked by the platform before dispatch. It was not retried or rerouted.

Therefore worker-return verification remains unresolved; no independent approval or terminal state is claimed. The original identifier and durable return path are preserved; no duplicate worker was launched. Principal mathematical and implementation tests are not mislabeled as independent review.

The older action-specific PDF inspection gate also remains. Full quote-recovery/fatigue research still needs permitted verified add/modify/delete, side, priority, reset and update-boundary semantics, followed by real order-conservation replay and independent-day testing. This work does not bypass that gate or treat the execution-only experiments as tests of the richer hypothesis.

Completed independent results are the fixed-clock study, the visibility reader, the censoring-aware synthetic summary and the repaired new timestamp searches. The blocked legacy audit and unresolved worker return are additional explicit obligations. No automatic background continuation, new watcher or scheduled action was created.

## 9. Research decision

**Do not promote the pause candidate.** A positive combined data/price score is insufficient when directional quality deteriorates and a simpler constant is better. Retain the explicit observation mask and the measured distinction between filtered silence and observed activity.

**Retain the competing-outcome summary for prototype measurement.** It makes incomplete/depleted responses visible without claiming market validation.

**The next meaningful signal test remains ordered real-book recovery under qualified source semantics**, not another relabeling of execution-only features. It must measure earlier warnings at a matched false-alarm budget, preserve no-response/censored cases, survive realistic delay and independent days, and show incremental value beyond current book/flow/price baselines. Until then the broader earlier-warning outcome remains unfinished.

## Primary sources and attribution

S1. Engle & Russell, *Forecasting Transaction Rates: The Autoregressive Conditional Duration Model*, NBER Working Paper4966, December1994; published as the 1998 Econometrica ACD study. Primary abstract inspected for duration clustering and separate arrival modeling, not replicated. https://www.nber.org/papers/w4966

S2. Cavaliere, Mikosch, Rahbek & Vilandt, *The Econometrics of Financial Duration Modeling*, arXiv:2208.02098, August2022. Primary abstract inspected; random event counts and tail behavior limit simplistic inference. https://arxiv.org/abs/2208.02098

Research-original formulas, fixtures and this experiment are distinguished from those sources. Previously qualified IEX L and transport documentation are recorded in the adjacent `event_recovery/QUALIFICATION.json`; no blocked material was re-accessed.

Data provided for free by IEX. Use of IEX Historical Data is subject to its Historical Data Terms of Use. https://www.iex.io/legal/hist-data-terms
