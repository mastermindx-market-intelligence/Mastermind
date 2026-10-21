# Financial and data contracts: implementation guidance

These are logical requirements and testable calculations for the existing owners, not a new canonical schema, semantic engine or database. The source owner decides the exact versioned wire mapping. Reuse qualified existing financial definitions and calculation modules. Sources: S01, S22-S26, S31; arithmetic examples below are original illustrative calculations, not empirical findings.

## 1. Minimal claim-bearing evidence contract

A material claim must have an exact subject and scope; a native source occurrence or admissible input reference; the selected revision; the economic period/effective date; the clocks relevant to the requested view; unit/currency/accounting/share basis; source-use status; evidence span or deterministic calculation reference; correction/supersession ancestry; and the actual output disposition.

A calculation additionally identifies the formula and code/model version, input selection, assumptions, range/scenario choices and output units. A model-inferred assumption is not recorded as a source fact. Missing values carry reason and scope, not invented zero. A quote, event, annual filing and aggregate statistic need not share one timestamp or frequency.

A served answer must identify its build time separately from its evidence cutoffs and current constituent source clocks. Its selected generations must be replayable or honestly marked unsupported. Bind exact read receipts at consumption, not a later reconstructed observation.

## 2. Four time views, four different promises

| View | Required meaning | What cannot stand in for it |
|---|---|---|
| Recorded-decision replay | Exact packet, source generations and method actually consumed for that recorded decision | A latest rebuilt answer with a past date |
| Operational-as-known | Inputs actually received, durably retained/admitted by the system at the cutoff | Earlier public publication alone |
| Source/market-as-known reconstruction | Source version demonstrably available through the declared channel by the cutoff | A later corrected download or guessed reporting lag |
| Latest-revised/current-rule calculation | Current admissible revisions and method, clearly labeled current recomputation | A claim about actual past possession or decision behavior |

When an availability timestamp is an interval [earliest, latest], an interval wholly before the cutoff may establish eligibility for the relevant view; one that straddles the cutoff cannot prove it. A future scheduled event can be known before its effective date. That is different from using a future observation.

Retain original source precision. A date-only value may be appropriate for a date-scoped report, but cannot be promoted to midnight-UTC intraday certainty. Every timezone conversion needs a specified source timezone/offset. Unknown remains unknown.

Corrections to source facts, identity aliases, mappings, parser/model methods and financial definitions can invalidate different descendants. Rebuild affected current views through existing owners; never rewrite sealed prior decisions or reset trial exposure.

## 3. Financial driver calculation patterns

### Volume and price

For a matched operating segment and period, a conditional revenue model may use:

`revenue = delivered_units * realized_price_per_unit`

A clean decomposition of the scenario change can use quantity effect, price effect and their interaction, with a declared convention. For baseline (q0,p0) and scenario (q1,p1):

`delta_revenue = (q1-q0)*p0 + q0*(p1-p0) + (q1-q0)*(p1-p0)`.

The interaction term must not be accidentally omitted or counted twice. Units shipped, units recognized as revenue, booked orders and total addressable demand are not interchangeable. Segment totals must not double count intersegment revenue.

### Margin and operating cost

`gross_profit = comparable_revenue * gross_margin_fraction`

`delta_operating_profit = delta_gross_profit - delta_operating_expense`

Margin is not markup. Basis, currency and period must match. A margin scenario remains an assumption unless it is itself a qualified observed value. Fixed versus variable costs, mix and capacity constraints may invalidate a simple linear extrapolation; state such limitations rather than invent a complex coefficient.

### Net income, shares and cash

Under explicitly stated incremental financing and tax assumptions:

`delta_net_income = (delta_operating_profit - incremental_net_interest_cost) * (1 - incremental_tax_rate)`.

This simplified scenario is not a universal accounting identity for all issuers. If taxes, nonoperating items or minority interests materially matter, use the qualified owner model or bound the result. EPS requires an appropriate separately qualified denominator and any share-count change; never divide by public-float dollars or substitute current outstanding shares for a weighted-average diluted denominator without justification.

Cash flow needs its own working-capital, cash-tax, capital-expenditure and other relevant inputs. Do not equate an earnings delta with free cash flow. Valuation and share-price effects are a further conditional model, not a direct consequence of revenue arithmetic.

### Contract and capital-action events

Separate maximum framework ceiling, committed obligation, delivered service, recognized revenue, backlog and received cash. A government contract candidate is not an award probability. Buyback authorization is not executed repurchase. Contingent warrants/convertibles require explicit state and share-basis treatment; avoid double counting claims.

### Numeric safeguards

Reject nonfinite numbers, invalid units, inconsistent scale/currency/period and unsupported financial scope. Decimal or equivalently tested deterministic arithmetic should preserve contractual rounding. Test negative/near-zero denominators and EPS sign changes; do not print a persuasive percentage when an absolute comparison is more meaningful. Large scenario ranges should expose sensitivity, not be disguised as calibrated uncertainty.

## 4. Toy calculation with verified arithmetic

**Every input here is invented for a test fixture. This is not a real company, observed event or trading forecast.**

Baseline: 1,000,000 units at $100 gives $100,000,000 revenue. Scenario: 1,050,000 units at $102 gives $107,100,000 revenue. Revenue increases $7,100,000.

Baseline gross margin is assumed 40%; scenario margin is assumed 41%. Gross profit changes from $40,000,000 to $43,911,000, a $3,911,000 increase. After an assumed $1,000,000 incremental operating cost, operating profit increases $2,911,000. With assumed incremental net interest of $200,000 and a 25% incremental tax rate, the conditional net-income increase is $2,033,250.

Only under a separately stipulated unchanged, appropriate 10,000,000-share denominator does the toy EPS increase equal $0.203325. In real execution that denominator must be qualified; otherwise EPS remains unavailable. Free-cash-flow and stock-price effects remain null because this fixture provides no corresponding model inputs.

`verification/toy_scenario_arithmetic.json` records Decimal arithmetic assertions for these numbers. It demonstrates arithmetic and explanatory format only. Actual source fact selection, model validity, accounting completeness, rights and useful predictive performance are entirely different proof obligations.

## 5. Expectations and market response

A named absolute expectation gap is `reported_or_scenario_value - qualified_baseline_value` only after subject, period, unit and basis match. The baseline's exact pre-event source generation and availability are part of the comparison. Guidance-versus-prior-guidance, actual-versus-analyst-consensus and actual-versus-model-nowcast are separately named measures.

Do not create a universal z-score or residual engine while C6's original method remains unaccepted. Use existing family-specific standardized measures only under their own qualification. A revision delta needs no claim about expected revision; a revision surprise does.

Observed event-time price and benchmark-relative movement are context, with their actual price-source and session clocks. Reuse the incumbent residual/market-response owner. Do not equate reaction size to degree priced in, identify a marginal buyer from price alone, or use a favorable subsequent return to validate the narrative that selected the case.

## 6. Consumer consistency, cache and corrections

The same underlying answer selection must remain consistent across the company and Terminal views. Use existing identity/generation/entitlement contracts for cache keys and read receipts; a ticker-only key is insufficient where user access, cutoff or source generations differ. A later response must not overwrite a newer ticker/request.

Cache invalidation follows the actual changed source or model dependency through the existing projection owners. Do not create a new global dependency graph to implement this rule. A correction may invalidate one financial sentence but not a separate historical source claim. On partial source failure, retain prior evidence only with its actual age and the new attempt's degraded status; do not stamp it fresh.

No public or lower-entitlement cache may expose private source text, forbidden metadata or higher-tier model-derived content. An attested publication receipt does not itself prove access to every company or every downstream use. Verify the exact subject and rights/entitlement path.

## 7. Evidence-to-value measurement

Distinguish four endpoints: correct source extraction/semantics; improved operating-KPI or expectation information; useful user decision support; and separately validated trading value. Freeze the appropriate baseline and meaningful-effect threshold for each. A source can be worth retaining for reference or substitution even when it adds no return prediction.

Shared data lineage, issuer/event dependence and repeated trials affect evidence interpretation. Require common keyed support and explicit missingness, not comparisons over different convenient subsets. Evaluate entire source-family removal with information descendants, not just deletion of the final visible feature. Preserve null/negative studies and exposure history.
