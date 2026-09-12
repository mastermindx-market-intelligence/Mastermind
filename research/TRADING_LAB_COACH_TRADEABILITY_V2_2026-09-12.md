# Mastermind Trading Lab — decision coaching and market tradeability v2

Date: 2026-09-12. Owner: Sol for Chairman Chris.
Existing carrier: Mastermind PR #566 / sol/paper-cash-trading-suite-20260911.
Operation: paper-cash-trading-suite-20260911-sol-001 / design-expansion-20260912.
Status: SPEC_ONLY / SOURCE_ONLY / PRODUCTION_INERT / DRAFT / HOLD.
Protected procedure and implementation read pin: Mastermind@57a2672af5b9dcea282e4bae01d1a0b9d10bb1cd. Skillpack 1.0.1 / bootstrap major 1; INDEX, COLD_START, RECONCILE_STATE and CLOSEOUT loaded at this same pin. Macro AI reads: 7f187f8c4cbf13f69c59625bcf45c7c9a4c39c19. Terminal copilot routing observed at a4be9a3f4b51246200cb1b7c4f1d44730066a9a9.

This is a proposal under the current live Chairman request for a complete personal training/AI/research expansion. It does not assert independent acceptance, implementation, installation, worker assignment, execution authority or production proof. No paper order, provider call, account migration, real-broker action or deployment was performed for this study.

## 1. Outcome and scope

Build one Trading Lab inside the existing Portfolio application: correct cash-equity paper execution, a structured decision workbench, private Mastermind AI coaching, shared market-conditions intelligence, evidence-qualified emergence/scenarios, and a longitudinal personal learning environment.

The promise is not AI approval. It is: know what you believe, what supports it, what would change it, what risk you chose, and whether the process improved independently of the outcome. Act, wait, reduce and pass must all be legitimate decisions. More trading, blocked trades, screen time, model agreement and raw P&L are not the product objective.

The original research/PAPER_CASH_TRADING_SUITE_ARCHITECTURE_2026-09-11.md remains the paper execution baseline. This companion adds learning/tradeability/forecast architecture, brings basic decision capture and reflection earlier in the sequence, and proposes a per-user persistence migration. It does not erase Market/Limit/Stop/Stop-Limit, DAY/GTC, reservations, activity, performance or migration requirements. Neither document is a production release grant.

## 2. Distinctions that must survive every UI and API

- Business-thesis support is not entry suitability or valuation attractiveness.
- Felt conviction is the user's subjective belief; earned conviction describes evidence, falsifiability and alternatives. Neither automatically determines position size.
- Win probability is not expected value. A high-frequency small win can be dominated by rare large losses.
- A calibrated forecast is not a user policy. A policy is not order execution permission.
- Process quality is not profit. A profitable deviation remains a deviation; a well-reasoned loss is not automatically a mistake.
- Market direction is not strategy-specific trading difficulty.
- New-risk posture is not held-position liquidation and is not personal readiness.
- A source, model or several agreeing models cannot promote their own authority.

Use explicit evidence-supported, partly supported, contradicted, unknown and user-assumption states. Never replace these with a fused Buy score. Review complete means the defined review ran, not that the thesis is correct. Policy compliant does not imply positive expected return. Uncalibrated scenarios must not acquire numeric confidence from LLM prose.

## 3. Current estate and material discoveries

The canonical user-driven paper facade is portfolio/self_directed.py. Keep its account lineage rather than creating another simulator. The separate app/pfolio.py and Supabase portfolio_positions are holdings/risk CRUD, not an order/fill engine. Actual/imported holdings and live-paper/replay/synthetic accounts must remain distinct.

Current Self-Directed source returns a fresh $1M account on corrupt load, uses direct file writes, silently clamps oversized fills and lacks durable reservations/order lifecycle. Treat this as a prototype with important reuse value, not a proven brokerage-grade engine. Review settlement side effects in history reads, queued-open semantics, timestamp ordering, nonfinite input, lost cancelled/rejected history and missing-mark NAV fallbacks.

A source-derived accounting discriminator is mandatory: buy 100 shares at $100 and 100 at $200, sell 100 at $180, mark the remaining 100 at $180. Economic gain is $6,000. FIFO realized is $8,000 and remaining unrealized must be -$2,000. Combining FIFO realized with an unchanged $150 average-cost position instead reports $11,000. The existing average-cost position and FIFO history paths need an executed reconciliation test. This example is a deduction from source, not an observed production incident.

portfolio/paper_account.py already contains transaction locking, atomic replacement/fsync and recoverable settlement patterns. Reuse relevant primitives/invariants, not the AI book's full-target rebalancing or omission-means-exit behavior for human manual orders.

The actual user-facing AI owner is Macro engine/neuralweb/brain_gateway.py with config/brain.yml. It already has configurable lanes, tool permissions, budgets, usage accounting and canonical brain_threads/brain_messages. Terminal's copilot route uses this gateway. Mastermind brain/mastermind_ai.py is a different, legacy portfolio-improvement coordinator; do not make it a second personal coach/router.

Macro engine/neuralweb/brain_user_memory.py already reads the user's OWN trade_episodes and chat sessions. engine/neuralweb/trade_memory.py is the current reflection/journal writer owner. Extend that estate, not another trade-journal/vector-memory database. Its strict whitelist and research_only autopsy framing matter: the internal evidence_packet is not approved raw model input. Expanded review evidence requires an explicit versioned private adapter.

Macro already has trend/chop research in scripts/research_trend_gate.py and compression-related source; engine/stock_technicals.py distinguishes close-only from genuine OHLCV capabilities. Existing recovery research such as reports/spvector-phase2.md should be assessed before adding another recovery detector. Research existence is not accepted live policy authority.

## 4. Product journey

Introduce Trading Lab alongside real/imported holdings and AI model books. Preserve prominent PAPER and mode identity throughout. Primary views: Decision Desk, Market Conditions, Thesis Workbench, Orders and Positions, Edge and Process, Training Grounds and Emergence Radar; Coach and Controls is a settings surface using the existing AI experience.

Before session: show conditions, material thesis changes and one selected practice rule. Optional readiness is self-reported, never diagnosed from losses or typing.

Before AI recommendation: record the user's independent thesis. Then assemble a claim-to-source map, strongest counter-case, entry trigger, valuation/expectations, horizon, invalidation, opportunity-cost alternative including cash and deterministic exposure preview.

At confirmation: bind account/mode, instrument identity, episode/thesis version, quote, market generation, forecast reference, user policy, account version, reviewer/model versions and expiry. The user confirms a precise paper action. Execution revalidates economic and freshness constraints. Quantity changes and materially changed inputs invalidate the relevant review/preview.

During holding: focus on material evidence and chosen review/trigger conditions, not compulsive tick-by-tick narrative. Risk-reducing/cancel actions use a separate path from slow deep AI review, without permitting overselling or stale-price fabrication.

After outcome: grade the original process without revealing the result, then evaluate assumption resolution, P&L, exposure and learning. Preserve passed/rejected/delayed decisions for later opportunity-cost review. No-trade decisions cannot become invisible sample selection.

## 5. Thesis and review contracts

Minimum thesis: instrument, playbook, horizon, mechanism, evidence, strongest counter-case, entry condition, thesis falsifier, risk mandate and review date. Advanced fields: priced expectations, valuation sensitivity, catalysts/dependencies and empirical reference class. Legitimate short-horizon strategies need precise setup/exit/execution/base-rate definitions rather than an invented long-term business story.

Every material claim has source identity, publication/first-known time, permitted evidence, correction relationship and support status. Distinguish independent sources from repeated headlines sourced to one announcement. Separate thesis invalidation from a price stop; a gap can exceed a planned risk unit.

A review emits separate evidence quality, mechanism assessment, entry fit, market/playbook fit, counter-case, missing facts, policy result, forecast references and conditional recommendation. Recommendations can be wait, revise, compare an alternative, review/reduce an exposure subject to user confirmation, or proceed to preview when requirements hold. A review does not execute.

The user's original judgment and all thesis amendments are versioned. An after-loss horizon change and a revised falsifier remain visible. Missing historical decision context is marked retrospective, not reconstructed into apparent foresight.

## 6. AI coaching through the existing gateway

Use bounded duties: evidence analyst, independent challenger and teacher. The challenger initially sees the evidence without the advocate's persuasive conclusion. Deterministic tools calculate money, exposure, historical samples and rules. These are duties, not permanent new agents, services or identities.

Add purpose mapping in the current admin/gateway policy: thesis extraction, thesis challenge, scenario explanation and episode coaching. Route routine bounded work economically and escalate ambiguity/material disagreement to an approved deeper route. Record actual model/provider/prompt/tool/evidence versions. Do not copy current model IDs into the architecture or create another quota ledger. Multiple model agreement does not equal independent evidence or probability.

Initial AI authority: grounded critique, missing evidence, comparison, market explanation and conditional recommendations using accepted sources. No invented numeric forecast, binding market rank, autonomous order or policy bypass. Predictive influence requires later forecast-owner validation and explicit promotion, followed by opt-in paper policy. Real-money routing is a different program.

Deep review is asynchronous with evidence/challenge/validation/complete/unavailable states, using the existing run/stream lifecycle. Stateless chat fallback cannot claim a required decision review was saved. Strict practice retains the draft and refuses to mark an incomplete review complete; it does not trap cancels/reductions behind AI downtime.

Default requests minimize private information; use weights where adequate. Exact account values and optional readiness/notes require explicit contracts and provider privacy rules. No cross-user coaching corpus by default. Current per-user read/whitelist boundaries remain until deliberately reviewed.

## 7. User-selected discipline policy

Modes: Advisory (warnings and overrides), Deliberate Practice (predeclared requirements for new risk), Blind Replay (rationale before advancing). Policy is explicit, prospective, versioned and understandable. User-adjustable limits are not personalized numeric financial advice from this specification.

Observe actions rather than diagnosing a person: concentration increased outside plan; repeated attempts after rejection; a falsifier changed without evidence; horizon extended after a loss; a new position entered outside the chosen playbook. Say this differs from your recorded plan, not you are irrational or a gambler.

Support selected pauses/cooldowns, evidence requirements, event restrictions and mandate bounds. Preserve an advisory override record, a review/appeal path and clear mode changes. No shame, P&L leaderboards, leverage incentives, streaks or rewards for more trading. Also measure overcaution and false veto opportunity cost. A coach that blocks everything has not succeeded.

## 8. Process, outcome, skill and curriculum

Four review cells: sound process/profit, sound process/loss, process deviation/profit, process deviation/loss. These are rubric labels, not scientific proof that any single result was luck. Freeze process scoring before outcome reveal; swapping outcomes must not change that frozen judgment.

Unit of evidence: decision/market episode. Scale-ins, fills and correlated contemporaneous positions do not manufacture independent trials. Maintain order/fill/decision/session/effective-episode counts separately.

Three evaluation layers: exact economic reconciliation; model-dependent benchmark/exposure/timing attribution; repeated uncertainty-qualified evidence of persistent skill. A factor residual is not a skill measurement. An apparent streak does not prove edge. Process improvement can be observed before enough independent financial outcomes accrue.

Track adherence, unsupported claims, evidence completeness, proper forecast scores, risk units fixed at entry, MFE/MAE, turnover and predefined counterfactual opportunity cost. Excursion analysis cannot select an impossible best exit after the fact. Binary probability forecasts use Brier loss mean((p-y)^2), compared with a relevant base rate and reliability by horizon/regime. Appropriate multiclass/distribution scoring is separate.

Research trials remain in the existing experiment registry. Use time-split evaluation, purging/embargo where label overlap demands it, dependence-aware uncertainty, multiple-testing discipline and realistic cost assumptions. DSR is a relevant research safeguard, not a small-sample badge.

Training modes: live-forward paper, point-in-time historical replay and explicitly synthetic drills. Never mix them into live skill claims. Production replay must not deliver future bars/documents to browser or model. Historical LLM prior knowledge is a leakage risk even after timestamp filtering; forward data and appropriate masked/held-out cases remain important. Downloadable UI fixtures are not secure blind-testing harnesses.

Curriculum: observation versus story; mechanism and falsifier; base rates and alternatives; valuation versus company quality; entry versus horizon; risk/concentration; difficult-market fit; calibration; fair review. Select one practical lesson and test it on a new case. Provisional style profiles show horizon/environment/sample/uncertainty rather than fixing a personality from a few trades.

Evaluate the coach: factual grounding, citations, missing contradictions, false reassurance, false vetoes, opportunity costs, pressure-induced agreement, latency/cost and user dependence. The goal is better independent judgment. Optional consented single-user experiments can compare coaching formats on replay/synthetic tasks, never remove essential safeguards or randomize real-money risk.

## 9. Shared market tradeability

Definition: how navigable the opportunity set and price path are for a specified strategy, horizon and execution constraint. Not instrument eligibility/liquidity alone, not market direction, not maximum risk budget.

The Chairman's calm-index/hostile-internals observation is a hypothesis and acceptance scenario, not a verified diagnosis of current markets. A bearish market can trend cleanly; high dispersion can be useful when leadership persists; volatility is not universally bad. Start with long-only US cash equities and explicit short/swing horizons, with separate long-horizon interpretation.

Measure families, with nonredundant grouping and coverage:
1. Direction/path: net progress relative to total path, trend persistence, reversals and gaps.
2. Breadth/concentration: equal versus capitalization weighting, participation and highs/lows on a point-in-time universe.
3. Leadership stability: rank persistence, cohort survival and leader/laggard flips; distinguish stable dispersion from churn.
4. Setup realization: follow-through and failures under frozen playbook rules, using only matured outcomes already known.
5. Rotation/common shocks: sector/factor turnover, dispersion and dependence; avoid double-counting correlated momentum indicators.
6. Liquidity/execution: spreads, gaps, availability and versioned slippage on covered/entitled instruments.
7. Tail/events: downside asymmetry, event clusters and skew; risk-neutral option measures are not physical event probabilities.
8. Macro context: existing growth/inflation/liquidity/risk inputs; slow signals cannot erase fast evidence.

ER = absolute net change / sum of absolute bar changes over a declared window is a candidate path descriptor, not a standalone gate. Reuse and evaluate current Macro trend research instead of copying it. Normalization uses training-only data and declared venue/horizon populations.

Data tiers: D0 daily closes/breadth; D1 genuine OHLCV/session bars; D2 licensed intraday trades/quotes. D0 cannot claim intraday churn, ATR or actionable bid/ask fidelity. Rights must cover display, derived analytics, retention, simulation and model-input use. Missing essential inputs yield UNKNOWN; last-good remains visibly aged, not silently current.

Public packet includes universe, venue/session, horizon/style, observed_at, first_known_at, generated_at, source generations, data tier, coverage, missing families, expiry and authority state. It contains no private holdings, readiness or notes.

## 10. Pronounced but evidence-qualified posture changes

Separate continuous evidence from explicit transitions. Candidate new-risk states: PROTECT, SELECTIVE, EXPAND, UNKNOWN. Initial output is descriptive/shadow. A binding paper policy needs validated rules and user opt-in, not a UI rename.

Stages: early indication, corroborated confirmation, communication of the accepted state/policy change. Permit a jump to the correct confirmed state rather than a cosmetic one-notch-per-day warm-up. A separately validated shock rule may promptly reduce new-risk permission. Entry/exit thresholds can be asymmetric with hysteresis and a dwell condition that real shocks may override.

Compare existing behavior with simple threshold/hysteresis and EWMA/CUSUM; consider Bayesian online change-point detection only if it improves real lag/false-alarm performance. Literature existence is not market-edge evidence.

Transition record: old/new state, effective/detection time, changed evidence families, coverage/uncertainty, affected style/horizon/mandate, acknowledgement and correction/retraction lineage. Delivery, acknowledgement and actual action are distinct. Never equate new-entry risk-off with forced sale of every existing thesis.

Validate missed opportunity during cautious delay, premature risk-on losses, false risk-off churn, turnover costs, notification burden and net utility. Permanent cash must not win merely by reducing drawdown; premature expansion must not win merely by catching one rebound.

## 11. Macro and Terminal integration

Use one additive projection through existing Macro market-state publication and change events. Macro dashboard, bot and Terminal show the same source generation/semantics; no three local scoring engines or clocks.

Macro top card: direction, strategy/horizon-specific difficulty, breadth/leadership, last transition and freshness. Detail reveals causes and missing coverage. Portfolio privately joins holdings/playbook/policy; Terminal contextualizes charts. User overlays never enter the public artifact.

Existing signal/risk/forecast consumers receive no stronger authority merely from the new label. Versioned contracts and explicit accepted consumer opt-in govern any predictive/policy effect.

## 12. Emergence and scenarios

Reuse current company/event/identity/graph sources. Join qualitative events (adoption, orders, pricing, capex, inventories, policy) with quantitative confirmation (cohort persistence, breadth, revisions, valuation, costs). Research object: event -> economic driver -> exposed entities -> potential cash-flow consequences -> expectations/valuation -> testable catalyst. Edges retain support, alternative explanations and known time; co-movement is not causation.

Visible states include early narrative, corroborated mechanism, quantitative confirmation, supported but extended/crowded, and rejected/disproven. Keep failed hypotheses in history. Research priority is not trade ranking.

Define forecast targets first: fixed-horizon return distribution, a specified barrier-first outcome or a business-event resolution are different targets. Start with base rates, shrinkage and interpretable conditional models; require incremental holdout improvement before advanced ensembles. No custom LLM pretraining or GPU fleet is a prerequisite.

Numeric scenarios must partition the target or expose residual mass. Do not multiply correlated bullish indicators as independent probabilities. LLMs can propose mechanisms and explain estimates; quantitative models own calibrated probabilities. User-entered odds stay labeled user assumptions. Unsupported horizons, stale inputs and out-of-distribution cases abstain.

Show net expected payoff, tail risk, costs and sensitivity. Probability of a small win alone is insufficient. Promotion: research -> offline evidence -> forward shadow -> limited opt-in paper policy -> repeated production proof. Demote on drift/data correction; never silently retune history. No live-capital permission follows.

## 13. Canonical infrastructure and migration proposal

Keep the existing FastAPI/Python product, Self-Directed facade, Terminal chart engine, Macro AI gateway/config/allowlist/cost/quota owner, private chat tables and journal owner. No second event/identity/auth/retry/queue/model router/graph/memory plane.

Proposed production personal-paper persistence is the existing Supabase/PostgreSQL estate, with one transaction owner per user/account. Narrow paper accounts/orders/transitions/fills/lot allocations/cash events are new domain records, not another holdings store. Reuse trade_episodes for the private decision root with explicit account/mode and versioned children where necessary. Keep brain_threads/messages for chat, not another coach transcript database.

Reuse existing file transaction primitives for bounded internal proofs where suitable, but do not run a permanent file+database dual-write architecture. At accepted cutover the old Self-Directed files become validated import/archive evidence, not a second writable authority. Existing AI-managed book storage is outside the migration scope.

Atomic account transactions couple reservations, transitions, fills, lots and cash. Decimal precision/rounding explicit. Unique user/account request keys provide idempotency; changed payload under the same key conflicts. Timeout means same-key reconciliation, no blind second order. Account-version/locking prevents two-tab overspend.

Matching belongs to existing scheduler/market event operations and runs with the browser closed. GET, history rendering and model calls never fill orders. No standalone universal review/matching scheduler or broker is added. Executive OS remains company-worker lifecycle, not the customer order ledger.

Authentication proves ownership; subscription tier is not identity. Server resolves user context, keys remain server-side, RLS/scoping cover API/cache/stream/export/AI tools. Private exposure and readiness are never public telemetry. No vector database is necessary before demonstrated retrieval need.

## 14. Cash and execution fidelity

Market/Limit/Stop/Stop-Limit, DAY/GTC, reservations, partial/filled/cancelled/rejected/expired lifecycle, replace history and explicit fractional policy are required. Brackets/OCO, trailing and extended sessions are later accepted extensions. These should not enlarge the first PR.

Separate execution from settlement. Expose settled/unsettled/reserved/available cash under a venue-effective-dated simulation profile. US T+1 is a relevant baseline subject to current-rule verification. Simplified immediate reuse must be explicitly labeled; do not borrow margin/PDT behavior blindly into a cash simulator.

Buys prefer entitled ask evidence and sells bid evidence. Last-trade fallback is labeled lower fidelity and source-aged. A matcher waking late cannot retroactively receive an opening fill without proof the order was working at that eligible event. If stop and target touch within one bar, chronology is unknown unless finer data establishes it; use declared conservative policy or report ambiguity, not best-case execution.

Partial fills need supported evidence or a versioned explicit model, not randomness for visual realism. Fees, spread, latency, liquidity participation and impact assumptions stay separate. Cover halts, holidays, early closes, DST, splits/dividends, ticker changes/delistings and reset epochs. A reset cannot delete bad performance from a purported verified track record.

## 15. Delivery waves and exact acceptance

PT-0B: current design/contract proposal on #566; independent architecture and current deployed/data-coverage audit remain owed.
PT-1: real authenticated market buy/sell/cancel -> persistent activity under correct cash/lot/order economics, decision identity, restart/concurrency and migration safety.
PT-2: capture thesis versions and pass decisions through the existing journal owner; visible after reconnect, no economic mutation from reads.
AI-1: real structured evidence review through the existing gateway with citations, contradiction, private scoping and outage paths.
MC-1: same-generation descriptive conditions visible Macro+bot, explicit null/coverage, no new gate authority.
PT-3: limit/stop/stop-limit/DAY/GTC through the existing matcher; closed-browser, gap/expiry and cancel/fill race proof.
LP-1: blinded process and reconciled outcome review; swapped outcome cannot rewrite frozen process judgment.
TG-1: point-in-time replay and new-case drills; future data refused before browser/model delivery.
EM-1: real source -> mechanism -> counter-evidence -> visible research lead; no hidden trading authority.
FC-1: fixed-target scenario forecasts in shadow; baseline, purged walk-forward, trial ledger and immutable forward forecasts.
MC-2: transition alerts and later opt-in paper posture; measured lag/false-alarm/opportunity/whipsaw tradeoff.
LP-2: transparent personalized lessons/style evidence with prospective tests and uncertainty, not small-sample skill labels.
PT-4: cash settlement and corporate-action lifecycle correct in UI/export.
REL-1: coherent private alpha, complete real/degraded journeys, identity isolation, observability and rollback proof.

PT-1 and MC-1 may prepare in parallel only after actual path/authority collision checks. Useful AI critique and descriptive conditions do not wait for a new predictive model. Each wave needs a real consumer and observable capability, not an infrastructure-only completion claim.

## 16. Mandatory falsifiers

Corrupt account must not reset; concurrent tabs must not overbook; timeout must not duplicate; interrupted account/fill projection must recover or block; FIFO/average-cost example must reconcile; reads must not settle; stale/wrong-session quotes must not fill; cancel/fill and bracket races must retain one economic result; cross-user API/cache/stream/export/AI access must fail; source prompt injection must not grant authority; pressure for agreement must not erase critique; unsupported numerical probabilities must be rejected; outcome swap must preserve process judgment; replay future data must be refused; correlated fills must not inflate independent samples; calm index/hostile internals must remain expressible; strong confirmation must not be hidden by slow UI smoothing; source correction must preserve original evidence; AI outage must preserve drafts and separate risk-reducing paths; rejected plans that later work must remain in opportunity-cost evaluation.

These are required tests, not completed production receipts.

Readiness distinguishes process/API, matcher, account store, quote freshness, market generation, review and projection lag. Initial engineering targets (not measured promises): cached private read p95 <500ms and deterministic preview p95 <250ms at agreed load. Deep review progress/latency is visible and not synchronous cancellation. Measure alpha workload before adding infrastructure; CPU baselines and existing services first.

Release requires exact source/deployment, independent semantic/security review, authorized test-account browser proof, migration/restore rehearsal and no real-broker path. Rollback pauses new orders, reconciles accepted effects and restores compatible projections without deleting transactions. Test on an authorized isolated account, not Chris's real holdings.

## 17. Continuation handoff

Completed now: source/research expansion and original design prototypes. The design set covers Decision Desk, Market Conditions and confirmed-expansion alternative, Thesis Workbench, Orders/Positions, Edge/Process, Training Grounds, Emergence Radar and Coach/Controls, with dark/light/mobile variants. All data and AI replies are explicitly synthetic; prototype runs without network requests or account writes. Design rendering is not production proof or Figma-native delivery.

Source access established the existing correct owners and new accounting/decision-safety concerns. Production browser/release/data entitlement, deployed private identity, full read-side settlement behavior and source-writer collision census for implementation remain unresolved gates. Do not mint an approximate Agent OS workstream from similar titles. No independent worker was commissioned or watcher armed by this records wave.

Next primary action: independent review of this expanded same-PR architecture and a bounded deployed-account/data-coverage audit, then freeze PT-1's exact owner/paths/economic contract. The first implementation must deliver the authenticated, correct market-order/cancel/activity journey with stable decision identity and visible restart/migration proof. Do not start a broad rewrite, probability gate or multiuser rollout from this document alone.

Preserve current Chairman direction/protected procedure, canonical source owners, original paper-only boundary, existing journal/gateway, and explicit source-versus-live capability vocabulary. Return to Sol for source ownership conflict, identity ambiguity, unsupported rights, irreconcilable money/history, required-review failure or effect uncertainty. No blind retry, worker/worktree takeover or second carrier.

## 18. Primary evidence references

Repository paths at the pins above: portfolio/self_directed.py; portfolio/paper_account.py; app/pfolio.py; engine/neuralweb/brain_gateway.py; config/brain.yml; engine/neuralweb/brain_user_memory.py; scripts/research_trend_gate.py; engine/stock_technicals.py; engine/compression_signals.py; Terminal terminal/app/api/copilot/route.ts. PR #566 original head 5a0899e98f1f9327117dbabf29892c133e7e5776 remains historical PT-0 source.

Barber and Odean (2000), Trading Is Hazardous to Your Wealth: https://doi.org/10.1111/0022-1082.00226 — historical overtrading evidence, not a verdict about Chris.
Baron and Hershey (1988), Outcome Bias in Decision Evaluation: https://doi.org/10.1037/0022-3514.54.4.569 — motivates outcome-blind process review.
Anthropic (2023), Towards Understanding Sycophancy: https://www.anthropic.com/news/towards-understanding-sycophancy-in-language-models — motivates pressure/agreeability tests, not confidence in any named current model.
Gneiting and Raftery (2007), Strictly Proper Scoring Rules: https://doi.org/10.1198/016214506000001437 — forecast evaluation.
Bailey and Lopez de Prado (2014), Deflated Sharpe Ratio: https://doi.org/10.3905/jpm.2014.40.5.094 — trial-selection/non-normality safeguards.
Adams and MacKay (2007), Bayesian Online Changepoint Detection: https://arxiv.org/abs/0710.3742 — candidate change detector, not proven financial policy.
Alpaca paper limitations: https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading — simulation is not actual liquidity/execution.
TraderSync replay: https://tradersync.com/market-replay-simulator/ — masking/playlists as competitor workflow, not efficacy proof.
Edgewonk: https://edgewonk.zendesk.com/hc/en-us/articles/360010150259-The-Tiltmeter — self-rated process comments, not inferred diagnosis.
SEC T+1 bulletin: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/new-t1-settlement-cycle-what-investors-need-know-investor-bulletin — current venue/rule verification remains an implementation gate.
