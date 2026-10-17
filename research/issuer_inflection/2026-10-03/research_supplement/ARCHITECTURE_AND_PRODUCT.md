# Canonical architecture, economic semantics and product specification

> **Same-program reconciliation:** this is a research/engineering supplement to the [audited masterplan](../../../../docs/superpowers/plans/2026-10-03-issuer-inflection-intelligence-program.md) and [single acceptance charter](../VALIDATION_AND_ACCEPTANCE.md), not a competing wave ledger. Existing CDV-1 economic interpretation, canonical baseline state, owner-native rights and controlled evidence-collection shadow are preserved. Numerical experiment suggestions require one W0 ratification; they are not extra authorized trials or substitutes for the primary release gates.

**Status:** recommended design for owner admission, not an implemented contract. Source facts are in the [census](CENSUS_AND_REUSE_MAP.md); external support and limitations are in the [research review](RESEARCH_AND_RIGHTS.md). Numerical admission defaults below are proposed engineering/product choices, not empirically established universal thresholds.

## 1. Choose derived composition, not a new truth plane

Three alternatives were considered. Extending the financial packet alone would place event language, capital state and mechanism hypotheses inside FIF's financial boundary. Extending the event workspace alone would force longitudinal, between-event economic comparisons into an event-specific source object. Building an independent economic-state database would duplicate facts, revisions, identity and timing. All are inferior to a **read-only, versioned composition projection** whose leaves reference existing owners.

Evaluate the existing proposal **`issuer_state_transition.v1`** as a narrow longitudinal relation, conditional on W0 comparing it with the existing event and `earnings.economic_interpretation/v1` contracts. Do not create it when an owner-native projection already serves the exact job. It is justified because the inspected contracts can represent financial revisions, event deltas and capital changes within their domains but do not jointly represent the comparability and cross-domain support/contradiction for an economic trajectory claim. Do not create a second `issuer_inflection_event`, evidence store or financial packet with overlapping authority.

A current issuer summary starts from explicit canonical baseline references and applies eligible derived transitions, preserving unchanged, unavailable and unsupported variables. A timeline alone cannot reconstruct a baseline. Both summary and timeline are read projections over existing owners. A regenerable cache is permitted only under existing storage, retention and publication mechanisms; it is never a new authoritative financial history. Consumers must be able to discard it and reconstruct the same result from the pinned inputs/rules.

```
FIF facts / statements / revisions / forensic findings -----+
Earnings event / guidance / source spans / accepted Q&A -----+--> qualified read adapters
Capital event / context / existing what_changed ------------+          |
Existing issuer identity / peers / themes / market ----------+          v
                                                         comparison eligibility
                                                                 |
                                                    deterministic change observations
                                                                 |
                                                   mechanism / support / contradiction
                                                                 |
                                                issuer_state_transition.v1 projection
                                                                 |
                         existing Terminal + dossier + research alerts + Neural Web / Ask
                                                                 |
                                            separately admitted individual Prophet shadow
```

FIF-7 owns financial comparability of non-GAAP, KPIs and normalized guidance. Earnings owns the original event statement and source span. Capital owns all financing calculations. The compiler may reject an unavailable bridge; it cannot invent the bridge.

## 2. Proposed contract boundary

| Field group | Proposed contents | Law |
|---|---|---|
| Identity | Schema version; canonical issuer reference; deterministic transition content address; domain and canonical metric/state-variable reference | Reuse IssuerMaster/security bindings and existing addressing conventions. No ticker-only or CIK-derived new identity. |
| Method | Compiler/rule version, configuration digest, evidence class | A changed rule makes a distinguishable derived version. It does not rewrite historical system knowledge. |
| Query | Owner-native temporal policy and cutoff references; current/prior query receipts | Never flatten `as_reported`, `latest_known_as_of`, `latest_restated`, public and system replay into one generic `as_of`. |
| Inputs | Before/after refs, source/packet generation and digests, source/evidence span refs, required support-set references | Store references rather than duplicate raw facts. Bounded display values must exactly resolve to these refs and be discardable. |
| Eligibility | Period/basis/perimeter/unit/definition/rights/coverage states; typed refusal reasons | Preserve source-owner nonvalue states. A rejected pair cannot leak into materiality sorting as zero. |
| Observation | Level/growth/rate changes; natural units, percentage points/basis points where appropriate; family/type | No LLM arithmetic or invented financial formula. Financial formula leaves remain governed by FIF. |
| Economic interpretation | Candidate mechanism, support, contradictions, alternatives, next discriminator, falsifier | Explicitly inferred, never promoted into financial source authority. |
| Materiality | Transparent measured and categorical vector, plus policy version | Research attention is not bullishness, expected return, size or trade permission. |
| Correction | References to superseded derived versions and corrected owner receipts | Append/supersede under existing mechanisms; historical cutoff replay remains unchanged. |
| Delivery | Per-domain coverage, freshness, source rights, limitations and current evaluation state | A fresh generation cannot make stale event content current. |
| Authority | Existing `context_only` representation and false rank/gate/size/entry/Prophet authority as the consumer contract requires | Do not introduce `derived_research` as a new authority class. `derived` belongs to evidence-class metadata. |

The exact schema shape must be admitted with the owner; the fields above are semantic requirements, not a claim that these names already exist in production. Extend existing envelope/reference types. An adapter must map source-native authority conservatively, never broaden it.

## 3. Multiple clocks and the knowability claim

There are eight economically distinct clocks but **not eight new clock systems**. Represent them through existing source/temporal envelopes and optional interval metadata:

| Clock | Meaning | Forbidden shortcut |
|---|---|---|
| Operating/economic | When demand, pricing, capacity or behavior changed; often only an interval or unknown | Backdating from a later management description to a precise day |
| Accounting/reporting | Fiscal interval or balance-sheet instant represented by a fact | Treating quarter end as publication |
| Guidance/commitment | Issuance/revision time, target period and condition/deadline | Using achieved results to annotate the original promise |
| Expectations | Broker/vendor activation and target period | Today's consensus substituted into a historical event |
| Disclosure | Actual accepted/public source availability | Assigning SEC acceptance to a transcript with unknown publication time |
| Financing | Announcement, execution/effectiveness, filing and observation clocks | Treating registration authorization as issued shares |
| Market | Exchange-session/event time and executable observation time | Filling before publication, or using the announcement return as a pre-event feature |
| System | Source first observation/admission, correction/rule availability and actual delivery | Pretending a rule deployed today existed at a historical decision cutoff |

**Support-set rule.** For a claim requiring inputs A and B, its public support cannot be complete before both are available. For a fixed admissible support set, the lower bound is the maximum of required source-availability clocks, not the minimum source date. With alternative sufficient support sets, the earliest supported bound is the minimum over admissible complete sets, evaluated under the frozen rule. Every semantic/lineage/rights condition must also hold.

**Coverage rule.** An incomplete archive usually establishes 'earliest supported in admitted evidence,' not 'first time any investor could have known.' Use the former wording unless completeness is proven. Unknown source clocks yield an interval or unavailable state, never an invented timestamp.

**System rule.** Actual system knowability additionally requires source observation/admission and the implementation/lineage rule to be available. A4R's system-availability floor is inherited unchanged. A retrospective reconstruction made today can answer what disclosed evidence was available under a specified method; it cannot claim that Mastermind emitted or possessed that inference then.

Proposed display metadata therefore distinguishes `time_claim_kind = actual_system_observation | reconstructed_public_support | bounded_interval | unknown`, alongside owner-native clock references. These tags describe a claim; they are not replacement temporal-policy enums. Show actual alert delivery separately. For a multi-source contradiction, use the clock when the contradiction became supportable, not the earlier favorable finding's clock.

## 4. Economic-state ontology

| Domain | Useful variables / mechanisms | Mandatory distinctions |
|---|---|---|
| Demand/activity | Units, orders, bookings, backlog, traffic, churn, utilization, sell-through | Sell-in versus end demand; gross versus net orders; cancellations; backlog conversion versus growth |
| Pricing/mix | ASP, discounts, take rate, ARPU, customer/product/geography mix | Price versus product mix; constant currency only if source-supported; promotion versus durable pricing |
| Growth | Revenue/units/organic/segment recurring growth and guidance | Acquired versus organic; base effects; annual, quarterly and YTD durations |
| Profitability | Gross/operating/contribution margin, incremental margins, unit economics | Basis/reconciliation; absorption; price-cost lag; mix; temporary input cost; underinvestment |
| Working capital/cash | Receivables, inventory, payables, deferred revenue, OCF/FCF | Stock versus flow; seasonality; acquisitions; receivable sales; tax timing; cash release from shrinking business |
| Investment/capacity | Capex, R&D, facilities, headcount, capacity, utilization | Commitment versus spend versus commissioning versus monetization; maintenance/growth only when disclosed |
| Balance sheet/financing | Cash/liquidity, maturities, leverage, capacity, issuance, buybacks | Canonical Capital ownership; gross/net shares; availability versus execution; contingent versus committed funding |
| Management/narrative | Guidance changes, assumptions, qualifications, commitments, Q&A topics | Quotation versus interpretation; removal versus absence; promise versus aspiration; role/source confidence |
| Reporting/accounting | Restatements, reclassifications, policy/estimate changes, KPI definitions, reconciliation items | Presentation change versus economic change; later known correction versus original state |
| Expectations/incorporation | Licensed revisions, dispersion, guidance gap, market reaction | Expectations are not operating facts; priced information is not disproven information; optional/rights-gated |

There is no universal working-capital template. Banks/insurers require their own financial/regulatory domain mappings. Unknown or inapplicable values remain distinct. A product-wide empty cell must distinguish missing source, missing history, unsupported metric, right-blocked, source-conflicted, stale, incomparable and not applicable using the appropriate owner-native state.

## 5. Operational definition of change and inflection

An **observed change** is a valid source-backed difference or explicit event transition. An **inflection candidate** is an observed change that could alter the economic trajectory but has not passed its family-specific durability/structural and alternative-explanation tests. An **evidence-supported economic transition** passes the frozen comparison, materiality, support and persistence/structural rules. A **predictive feature** is a separately defined, preregistered and validated research object. These labels must not collapse into each other.

Taxonomy has orthogonal axes rather than one giant bull/bear enum:

- Measurement shape: level shift; growth change; acceleration/deceleration; structural-break candidate; temporary volatility.
- Economic family: demand, pricing/mix, margin, cash/working capital, investment, financing, expectations, commitment or reporting.
- Evaluation: observed; candidate; supported; contradicted; mixed; unresolved; not evaluable.
- Relation to prior claim: confirmation; reversal; reacceleration; deterioration; recovery; supersession/correction.
- Explanation qualifiers: seasonal; base effect; FX; acquisition/perimeter; accounting translation; definition break; one-off; business-model transition.

These are **claim-evaluation states**, not a new operational job lifecycle. A single quarter cannot mechanically become an inflection. Conversely, an explicit guidance withdrawal or covenant event can be a material observed transition immediately; it need not wait two quarters to exist. 'Durable economic recovery' requires a different evidence rule from 'guidance withdrawn.'

### Deterministic comparison admission

1. Resolve issuer, metric definition/version, consolidation/segment, unit/currency, fiscal interval and source policy on both sides.
2. Reject unknown or incompatible perimeter/definition/basis unless the canonical owner supplies a valid bridge.
3. Use fiscal-calendar adjacency, never dataframe row adjacency. Missing Q4 remains missing. Q4 inferred as FY minus 9M is allowed only through an owner-approved formula with compatible vintages, scope and units and the later availability clock.
4. For level change, preserve natural units. For a margin change, use percentage points/basis points, not ambiguous percent growth. Growth across zero or negative denominators requires a named approved transformation or remains N/E; a loss narrowing is not ordinary positive revenue growth.
5. YoY quarterly growth requires matching fiscal quarters. Acceleration in YoY growth needs the relevant values for t, t−4, t−1 and t−5, with their own knowability checks. Missing required quarters disqualify the calculation.
6. A reported constant-currency/organic bridge is labeled separately from reported change. No silent analyst reconstruction of a missing bridge.
7. Test changes against magnitude and persistence rules defined per family before outcome access. Store the measured values even when the hypothesis remains unresolved.

## 6. Materiality, corroboration and mechanism

Use a vector, not a score. Deterministic values include natural-unit delta, margin basis points, comparable growth-rate change, number of consecutive supporting fiscal observations, elapsed periods, source age and mechanically verifiable commitment revisions. Categorical values include comparability, source-quality limitations, rights, accounting/perimeter breaks and evidence-family coverage. Peer rarity, statistical break probability and inferred market incorporation are research-only until validated.

A research inbox may sort lexicographically by explicit user-selected criteria—such as new guidance withdrawals, then cash consequence, then age—with displayed ordering policy. It must not relabel that priority as expected return. Missing dimensions never take the neutral value or improve a rank.

Evidence independence is assessed by **underlying fact and mechanism**, not document count. A press release, its 8-K exhibit, prepared remarks quoting it and an AI summary are one originating fact. A later receivables disclosure is distinct but not automatically statistically independent of revenue. Track source-lineage clusters and accounting dependencies. Corroboration requires new information, not a second citation to the same claim.

A mechanism record contains: proposition; supporting references; contradictory references; unresolved alternatives; next observable discriminator; falsifier; test horizon/condition; and the inference method/version. Never require an LLM to fill a mechanism field with certainty when evidence is insufficient. Empty inference is better than invented causality.

**Illustrative, non-issuer example:** comparable revenue growth rises from 10% to 15%, while receivables grow faster and cash conversion deteriorates. The observed acceleration is +5 percentage points. Possible explanations include genuine demand with collection timing, channel fill, changed terms, acquisition mix or aggressive recognition. The system must not say 'demand reaccelerated' solely from revenue. Next-quarter collections, disclosed sell-through, returns and terms can discriminate. These numbers are synthetic, not Mastermind empirical evidence.

## 7. Peer and common-driver decomposition

Reuse existing Group Reads/themes/relationships; no new peer graph. First compare prior self; then admit direct peers with as-of membership, comparable metric definition, fiscal window, currency and business perimeter. Show the eligible denominator and reasons for exclusions. A proposed descriptive minimum of five eligible peers prevents a percentile based on one or two names; it is a product default requiring review, not a statistical guarantee. Below it, show individual peers and 'insufficient comparable group,' not a fake percentile.

A robust peer median or exposure-conditioned residual can describe relative movement. It does not identify causality. Industry pricing, input costs, macro conditions, product cycles, regulation, customer demand and supplier constraints remain candidate shared drivers. Regressions must be trained only on past eligible observations with parameter/version receipts. Leave unresolved attribution explicit; a small residual does not prove execution quality.

## 8. Product acceptance specification

### Existing company workspace / Terminal

The default lens has three information levels. The first view gives a plain-language trajectory statement, the most material supported changes, a cutoff and per-domain coverage. The second exposes before → after, units, period, first-supported-time claim, comparison rule and confirmation/contradiction. The third opens original evidence and the owner receipt, including correction history and source limitations.

Keep existing company navigation, issuer identity, event selector, design tokens and layout conventions. Reuse the incumbent CDV-1/shared foundation host and rights seams after their own gates clear; private PG content is not automatically public. Design work belongs in the existing approved Paper files/token system; this research turn did not create visual designs. Avoid a standalone financial app and avoid a wall of diagnostic badges as the main experience.

Required visible states: loading; no comparable prior event; source unavailable; rights blocked; partial domains; stale event; definition/perimeter break; active correction; mixed/contradictory evidence; no material observed change; supported transition. 'No material observed change' requires coverage, not empty data. Never show issuer-wide LIVE because a fresh generation exists.

### Event comparison and commitments

Compare current versus previous **comparable** event, previous guidance, explicit commitments, accepted Q&A, periodic filing and financing state. A commitment carries issuer/event/source speaker, exact target/condition, deadline/horizon, metric definition, original range and every explicit revision. 'Off track' requires a frozen rule and currently observable evidence; 'missed' requires the deadline/result to be knowable. Silence is not withdrawal. Incompatible guidance ranges are not midpoint-compared. Losing access to a transcript is a rights change, not management dropping a topic.

### Discovery, watchlists and alerts

Saved research filters use explicit transition types and constraints, with criterion/basis/cutoff preserved. Examples: revenue acceleration with cash contradiction; margin improvement without demand confirmation; new financing obligation; guidance withdrawal; definition change invalidating prior comparison. These are research views, not stock recommendations.

Use the existing alert delivery/deduplication framework. The idempotency key includes transition content version and subscriber policy. Suppress duplicate alerts for an unchanged transition republished in a new generation. Issue a linked correction/reversal alert when a previously delivered claim changes; retain what the subscriber originally saw. Rights revocation and unsupported evidence must remove current exposure without destroying lawful audit history. No new queue or watchlist identity plane.

### Ask Mastermind, Brain and Neural Web

Return compact structured context: issuer, cutoff, time-claim type, material changes, contradictory evidence, limitations, next discriminators and canonical references. The answerer may explain but must not add uncited numeric facts or infer hidden consensus. Queries such as 'what changed since I last looked?' use a durable last-viewed version/cutoff through existing user state, not an invented previous observation.

### End-to-end journeys that must be demonstrated

A production user opens a company, changes cutoff/prior event, reads a supported transition, follows both supporting and contradictory source links, views a correction without losing the historical state, saves an explicit filter, receives one nonduplicated transition alert, and asks for a cited explanation. Repeat on mobile and on a partial/rights-blocked issuer. Browser proof must bind deployment SHA and actual source generation. Schema tests alone do not satisfy this journey.

## 9. Authority fence

All outputs begin as context-only. A compiler, user preference, new prose field, successful backtest or graph insertion cannot expand authority. Prophet may receive individual safe frozen features through an explicitly isolated observation-only shadow after source, rights, reconstruction and leakage gates. Prior demonstrated predictability is not required to collect shadow evidence. Any decision-path promotion additionally requires prospective evaluation and the existing explicit authority decision. A total 'Issuer Inflection Score' is explicitly out of scope. The product remains useful even if every return-predictive candidate fails.

## 10. Reconciled incumbent: economic interpretation is not missing wholesale

Independent source inspection during this continuation confirmed `engine/company_intelligence/economic_observations.py` and `engine/earnings_narrative/economic_interpretation.py` at Macro `bebcb24db8707f93c3acca470590fead13e78dbd`. The latter exports `build_economic_interpretation(workspace, *, source_texts, fiscal_scope, selection, semantic_revision, code_revision)` and `validate_economic_interpretation(payload, *, workspaces, source_texts, fiscal_scope)`. Its schema is `earnings.economic_interpretation/v1`; it already carries observations, comparisons, findings, missing_context, next_evidence, quality, clocks and false authority flags.

Its supported PG findings include reported-versus-organic growth, positive organic with nonpositive pure volume, reported-versus-core earnings disagreement and an incomplete margin-to-cash bridge. These are exactly the kinds of economic interpretation this program must reuse, not rebuild. The current implementation is bounded to validated PG observations; it is not a universal issuer engine. New issuer/economic semantics go through its owner, with FIF-7 retaining financial comparability. The composer only relates accepted outputs across time/domains and may attach clearly separated research hypotheses. Frozen source/probe suites remain untouched; private/publication gates and shared foundation #7870 remain controlling.

